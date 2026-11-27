"""Decision engine facade.

Separates the placement logic (policy) from metric acquisition
(:class:`MetricsClient`). The engine is the single entry point the
orchestration layer will call; the policy underneath can be swapped without
touching the engine or the API.
"""

import logging
import threading
import time
from typing import Optional

import anyio

from .config import SchedulerSettings
from .metrics_client import MetricsClient
from .models import (
    CloudMetrics,
    Decision,
    EdgeMetrics,
    NetworkMetrics,
    Target,
    Workload,
)
from .policies import BasePolicy, RuleBasedPolicy

logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(
        self,
        settings: SchedulerSettings,
        policy: Optional[BasePolicy] = None,
        metrics_client: Optional[MetricsClient] = None,
    ) -> None:
        self._settings = settings
        self._policy = policy or RuleBasedPolicy(settings)
        self._metrics = metrics_client or MetricsClient(
            timeout_sec=settings.metrics_timeout_sec,
            ttl_sec=settings.metrics_ttl_sec,
        )
        # Per-process placement memory. The lock makes lookup -> decision ->
        # update atomic for concurrent requests handled by this engine.
        self._placement_lock = threading.RLock()
        self._placement_state: dict[str, tuple[Target, float]] = {}

    @property
    def policy(self) -> BasePolicy:
        return self._policy

    def decide(
        self,
        workload: Workload,
        edge: Optional[EdgeMetrics],
        cloud: Optional[CloudMetrics],
        network: Optional[NetworkMetrics],
    ) -> Decision:
        """Decide placement from explicit metrics snapshots."""
        with self._placement_lock:
            now = time.monotonic()
            ttl = max(0.0, self._settings.placement_state_ttl_sec)
            # Expire stale workload identities before reading or writing state.
            if ttl == 0.0:
                self._placement_state.clear()
            else:
                expired = [
                    key for key, (_, updated_at) in self._placement_state.items()
                    if now - updated_at > ttl
                ]
                for key in expired:
                    self._placement_state.pop(key, None)

            previous_target = None
            state = self._placement_state.get(workload.workload_id)
            if state is not None:
                previous_target = state[0]

            if isinstance(self._policy, RuleBasedPolicy):
                decision = self._policy.decide(
                    workload, edge, cloud, network, previous_target=previous_target
                )
            else:
                decision = self._policy.decide(workload, edge, cloud, network)

            # Only stable execution placements are remembered. QUEUE/ERROR do
            # not erase the last known placement; expiry handles abandoned IDs.
            if decision.target in (Target.EDGE, Target.CLOUD) and ttl > 0.0:
                self._placement_state[workload.workload_id] = (decision.target, now)
                max_entries = max(1, self._settings.placement_state_max_entries)
                if len(self._placement_state) > max_entries:
                    oldest = sorted(
                        self._placement_state.items(), key=lambda item: item[1][1]
                    )
                    for key, _ in oldest[: len(self._placement_state) - max_entries]:
                        self._placement_state.pop(key, None)

        logger.debug(
            "workload=%s previous_target=%s target=%s score=%s (%s)",
            workload.workload_id,
            previous_target.value if previous_target else None,
            decision.target.value,
            decision.score,
            decision.reason,
        )
        return decision

    async def decide_remote(
        self, workload: Workload, edge_url: str, cloud_url: str
    ) -> Decision:
        """Fetch live edge/cloud metrics and edge->cloud latency, then decide.

        The three probes (edge ``/metrics``, cloud ``/metrics``, cloud
        ``/health`` latency) are independent and run concurrently so the two
        dominant ~1 s metric samples overlap instead of serializing. The policy
        still receives the same three inputs, evaluated only after they are all
        collected. Uses an ``anyio`` task group so concurrency works unchanged
        on both the asyncio and trio backends (the project runs ``pytest`` on
        both).
        """
        edge, cloud, latency_ms = await self._fetch_all(edge_url, cloud_url)
        network = (
            NetworkMetrics(latency_ms=latency_ms) if latency_ms is not None else None
        )
        return self.decide(workload, edge, cloud, network)

    async def _fetch_all(
        self, edge_url: str, cloud_url: str
    ):
        """Run the three independent probes concurrently and return their results."""
        results: dict = {}

        async def capture(name, coro):
            results[name] = await coro

        async with anyio.create_task_group() as tg:
            tg.start_soon(capture, "edge", self._metrics.fetch_edge(edge_url))
            tg.start_soon(capture, "cloud", self._metrics.fetch_cloud(cloud_url))
            tg.start_soon(
                capture, "latency", self._metrics.measure_latency_ms(cloud_url)
            )
        return results["edge"], results["cloud"], results["latency"]
