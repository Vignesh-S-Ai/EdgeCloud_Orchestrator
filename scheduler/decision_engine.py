"""Decision engine facade.

Separates the placement logic (policy) from metric acquisition
(:class:`MetricsClient`). The engine is the single entry point the
orchestration layer will call; the policy underneath can be swapped without
touching the engine or the API.
"""

import logging
from typing import Optional

import anyio

from .config import SchedulerSettings
from .metrics_client import MetricsClient
from .models import (
    CloudMetrics,
    Decision,
    EdgeMetrics,
    NetworkMetrics,
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
        decision = self._policy.decide(workload, edge, cloud, network)
        logger.debug(
            "workload=%s target=%s score=%s (%s)",
            workload.workload_id,
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
