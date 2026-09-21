"""Local scheduler (decision engine) for Module 3 groundwork.

This is the first, single-node implementation of the orchestration decision.
In the full platform this logic is replicated on the cloud side, but the
interface (``decide(metrics, priority) -> SchedulingDecision``) is kept
identical so it can be swapped for the distributed KubeEdge scheduler later.

Rule of thumb:
  * Any resource saturated past its threshold -> offload to cloud.
  * High priority workloads get a local bias (low latency wins).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import psutil
from pydantic import BaseModel, Field

from ..monitoring.metrics import SystemMetrics

logger = logging.getLogger(__name__)

# Priority key -> how strongly "keep it local" raises the allowed thresholds.
PRIORITY_LOCAL_BIAS = {"low": 0.0, "medium": 5.0, "high": 15.0}

# Relative importance of each signal in the reported pressure score.
WEIGHT_CPU = 0.5
WEIGHT_RAM = 0.3
WEIGHT_LOAD = 0.2


class SchedulingDecision(BaseModel):
    """Outcome of the edge-vs-cloud decision for a workload."""

    run_locally: bool
    score: float = Field(ge=0.0, le=100.0)
    engine: str = "local"
    priority: str
    reason: str
    timestamp: datetime


class LocalScheduler:
    """Decides whether a workload runs on this node or should be offloaded."""

    def __init__(
        self,
        cpu_threshold: float = 80.0,
        ram_threshold: float = 80.0,
        enabled: bool = True,
        priority: str = "medium",
    ) -> None:
        self._cpu_threshold = float(cpu_threshold)
        self._ram_threshold = float(ram_threshold)
        self._enabled = bool(enabled)
        self._priority = priority

    def decide(
        self, metrics: SystemMetrics, priority: Optional[str] = None
    ) -> SchedulingDecision:
        """Compute a scheduling decision from a metrics snapshot."""
        prio = (priority or self._priority).lower()
        bias = PRIORITY_LOCAL_BIAS.get(prio, PRIORITY_LOCAL_BIAS["medium"])

        if not self._enabled:
            return SchedulingDecision(
                run_locally=True,
                score=0.0,
                engine="local",
                priority=prio,
                reason="Scheduler disabled - workload pinned to local execution.",
                timestamp=datetime.now(timezone.utc),
            )

        load = psutil.getloadavg()[0] / max(1, psutil.cpu_count()) * 100.0
        load_threshold = min(self._cpu_threshold, self._ram_threshold)

        # Hard gate: offload as soon as any resource crosses its threshold
        # (raised by the priority bias).
        checks = {
            "CPU": (metrics.cpu_percent, self._cpu_threshold + bias),
            "RAM": (metrics.ram_percent, self._ram_threshold + bias),
            "LOAD": (load, load_threshold + bias),
        }
        violations = [name for name, (value, limit) in checks.items() if value > limit]
        run_locally = not violations

        # Pressure score (0-100) for reporting: 100 == at capacity.
        def _pressure(value: float, limit: float) -> float:
            return min(100.0, value / max(1.0, limit) * 100.0)

        score = round(
            WEIGHT_CPU * _pressure(metrics.cpu_percent, self._cpu_threshold)
            + WEIGHT_RAM * _pressure(metrics.ram_percent, self._ram_threshold)
            + WEIGHT_LOAD * _pressure(load, load_threshold),
            2,
        )

        if run_locally:
            reason = (
                f"All resources within capacity (CPU {metrics.cpu_percent}% "
                f"<= {self._cpu_threshold + bias}%, RAM {metrics.ram_percent}% "
                f"<= {self._ram_threshold + bias}%, LOAD {load:.1f}%)."
            )
        else:
            parts = [
                f"{name} {value:.1f}% > {limit:.1f}%" for name, (value, limit) in checks.items()
            ]
            reason = f"Resource overload: {', '.join(parts)}. Offloading to cloud."

        logger.debug(
            "Decision: local=%s score=%s (%s)", run_locally, score, reason
        )

        return SchedulingDecision(
            run_locally=run_locally,
            score=score,
            engine="local",
            priority=prio,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
        )
