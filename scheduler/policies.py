"""Rule-based placement policy.

Deliberately deterministic and free of any ML dependency. Implements the
Module 3 strategy with configurable thresholds from SchedulerSettings:

    * healthy edge                                   -> EDGE
    * edge overloaded, network usable                -> CLOUD
    * edge overloaded, poor network, HIGH priority   -> EDGE (best effort)
    * edge overloaded, poor network, LOW/MEDIUM      -> QUEUE (defer)
    * edge and cloud both saturated                  -> ERROR
    * missing metrics                                -> ERROR

Subclass :class:`BasePolicy` to swap in an ML/RL policy later without touching
the decision engine or the rest of the project.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from .config import SchedulerSettings
from .models import (
    CloudMetrics,
    Decision,
    EdgeMetrics,
    NetworkMetrics,
    Priority,
    Target,
    Workload,
)

logger = logging.getLogger(__name__)

# Score weights (share of each resource in the reported edge pressure).
WEIGHT_CPU = 0.5
WEIGHT_RAM = 0.3
WEIGHT_DISK = 0.2


class BasePolicy:
    """Interface for placement policies.

    Implement :meth:`decide` to plug in another policy (e.g. an RL agent).
    """

    def decide(
        self,
        workload: Workload,
        edge: Optional[EdgeMetrics],
        cloud: Optional[CloudMetrics],
        network: Optional[NetworkMetrics],
        previous_target: Optional[Target] = None,
    ) -> Decision:
        raise NotImplementedError


class RuleBasedPolicy(BasePolicy):
    def __init__(self, settings: SchedulerSettings) -> None:
        self._s = settings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _edge_bias(self, priority: Priority) -> float:
        if priority is Priority.HIGH:
            return self._s.priority_edge_bias_high
        if priority is Priority.LOW:
            return self._s.priority_edge_bias_low
        return self._s.priority_edge_bias_medium

    @staticmethod
    def _overloaded(
        cpu: float, ram: float, disk: float,
        cpu_thr: float, ram_thr: float, disk_thr: float,
    ) -> List[str]:
        """Return the list of violated thresholds (empty == within capacity).

        Boundaries are inclusive: a value exactly at the threshold is fine.
        """
        violations: List[str] = []
        if cpu > cpu_thr:
            violations.append(f"CPU {cpu:.1f}% > {cpu_thr:.1f}%")
        if ram > ram_thr:
            violations.append(f"RAM {ram:.1f}% > {ram_thr:.1f}%")
        if disk > disk_thr:
            violations.append(f"DISK {disk:.1f}% > {disk_thr:.1f}%")
        return violations

    def _edge_fitness(self, edge: EdgeMetrics) -> float:
        """Edge suitability score 0-100 (100 = completely available)."""
        cpu_p = min(100.0, edge.cpu_percent / max(1.0, self._s.edge_cpu_threshold) * 100.0)
        ram_p = min(100.0, edge.ram_percent / max(1.0, self._s.edge_ram_threshold) * 100.0)
        disk_p = min(100.0, edge.disk_percent / max(1.0, self._s.edge_disk_threshold) * 100.0)
        pressure = WEIGHT_CPU * cpu_p + WEIGHT_RAM * ram_p + WEIGHT_DISK * disk_p
        return round(100.0 - pressure, 2)

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------
    def decide(
        self,
        workload: Workload,
        edge: Optional[EdgeMetrics],
        cloud: Optional[CloudMetrics],
        network: Optional[NetworkMetrics],
        previous_target: Optional[Target] = None,
    ) -> Decision:
        s = self._s
        now = datetime.now(timezone.utc)

        if edge is None or cloud is None:
            return Decision(
                workload_id=workload.workload_id,
                target=Target.ERROR,
                score=0.0,
                priority=workload.priority,
                reason=(
                    f"Required metrics are unavailable (edge={'missing' if edge is None else 'ok'}, "
                    f"cloud={'missing' if cloud is None else 'ok'}); cannot decide placement."
                ),
                timestamp=now,
            )

        bias = self._edge_bias(workload.priority)
        edge_violations = self._overloaded(
            edge.cpu_percent, edge.ram_percent, edge.disk_percent,
            s.edge_cpu_threshold + bias,
            s.edge_ram_threshold + bias,
            s.edge_disk_threshold,
        )
        cloud_violations = self._overloaded(
            cloud.cpu_percent, cloud.ram_percent, cloud.disk_percent,
            s.cloud_cpu_threshold, s.cloud_ram_threshold, s.cloud_disk_threshold,
        )
        latency_ok = network is not None and network.latency_ms <= s.max_latency_ms
        latency_note = (
            f"latency {network.latency_ms:.1f}ms <= {s.max_latency_ms:.1f}ms"
            if latency_ok
            else (
                f"latency {network.latency_ms:.1f}ms > {s.max_latency_ms:.1f}ms"
                if network is not None
                else "latency unknown"
            )
        )

        edge_ok = not edge_violations
        cloud_ok = not cloud_violations
        score = self._edge_fitness(edge)

        # Both sides saturated (or offload impossible because cloud is down).
        if not edge_ok and not cloud_ok:
            return Decision(
                workload_id=workload.workload_id,
                target=Target.ERROR,
                score=score,
                priority=workload.priority,
                reason=(
                    f"Edge and cloud both saturated "
                    f"(edge: {', '.join(edge_violations)}; "
                    f"cloud: {', '.join(cloud_violations)}); no healthy placement available."
                ),
                timestamp=now,
            )

        # Hysteresis: once a workload has moved to CLOUD, do not immediately
        # bounce it back at the ordinary overload threshold. Require every Edge
        # resource to clear a lower recovery threshold. Priority bias is retained.
        recovery_margin = max(0.0, s.hysteresis_margin_percent)
        recovery_ready = (
            edge.cpu_percent <= s.edge_cpu_threshold + bias - recovery_margin
            and edge.ram_percent <= s.edge_ram_threshold + bias - recovery_margin
            and edge.disk_percent <= s.edge_disk_threshold - recovery_margin
        )
        if (
            previous_target is Target.CLOUD
            and edge_ok
            and not recovery_ready
            and cloud_ok
            and latency_ok
        ):
            return Decision(
                workload_id=workload.workload_id,
                target=Target.CLOUD,
                score=score,
                priority=workload.priority,
                reason=(
                    f"Edge is below placement thresholds but has not cleared the "
                    f"{recovery_margin:.1f}-point recovery margin; retaining cloud placement "
                    f"(CPU {edge.cpu_percent:.1f}%, RAM {edge.ram_percent:.1f}%, "
                    f"DISK {edge.disk_percent:.1f}%)."
                ),
                timestamp=now,
            )

        # Healthy edge: run locally.
        if edge_ok:
            return Decision(
                workload_id=workload.workload_id,
                target=Target.EDGE,
                score=score,
                priority=workload.priority,
                reason=(
                    f"Edge resources within capacity "
                    f"(CPU {edge.cpu_percent:.1f}% <= {s.edge_cpu_threshold + bias:.1f}%, "
                    f"RAM {edge.ram_percent:.1f}% <= {s.edge_ram_threshold + bias:.1f}%, "
                    f"DISK {edge.disk_percent:.1f}% <= {s.edge_disk_threshold:.1f}%) "
                    f"and network {latency_note}; running locally."
                ),
                timestamp=now,
            )

        # Edge overloaded: offload to a healthy cloud over a usable network.
        if cloud_ok and latency_ok:
            return Decision(
                workload_id=workload.workload_id,
                target=Target.CLOUD,
                score=score,
                priority=workload.priority,
                reason=(
                    f"Edge resource overload ({', '.join(edge_violations)}) "
                    f"and network {latency_note}; offloading to cloud."
                ),
                timestamp=now,
            )

        # Edge overloaded and offload not viable (poor network / bad cloud).
        if workload.priority is Priority.HIGH:
            return Decision(
                workload_id=workload.workload_id,
                target=Target.EDGE,
                score=score,
                priority=workload.priority,
                reason=(
                    f"Edge resource overload ({', '.join(edge_violations)}) but cloud offload "
                    f"not viable ({latency_note}); high-priority workload pinned to edge (best effort)."
                ),
                timestamp=now,
            )

        return Decision(
            workload_id=workload.workload_id,
            target=Target.QUEUE,
            score=score,
            priority=workload.priority,
            reason=(
                f"Edge resource overload ({', '.join(edge_violations)}) and cloud offload not "
                f"viable ({latency_note}); {workload.priority.value}-priority workload queued for retry."
            ),
            timestamp=now,
        )
