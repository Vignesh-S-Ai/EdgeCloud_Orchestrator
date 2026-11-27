"""Orchestration service.

Ties the scheduler decision to an actual inference run on the Edge or Cloud
node and enriches the result with end-to-end latency breakdowns.

Flow (``orchestrate``):
    1. Ask the scheduler for a placement decision.
    2. Forward the image to the chosen node (edge ``/detect`` or cloud ``/infer``).
    3. On cloud failure: fall back to the edge for high-priority workloads if
       the edge is healthy, and mark the response with ``fallback_used``.
    4. Return the unified :class:`OrchestrationResult`.
"""

import logging
import time
from typing import Optional, Tuple

from fastapi import HTTPException

from .clients import CloudClient, EdgeClient, SchedulerClient, UpstreamError
from .config import OrchestratorSettings
from .models import OrchestrateRequest, OrchestrationResult

logger = logging.getLogger(__name__)


class OrchestrationService:
    def __init__(
        self,
        settings: OrchestratorSettings,
        edge_client: Optional[EdgeClient] = None,
        cloud_client: Optional[CloudClient] = None,
        scheduler_client: Optional[SchedulerClient] = None,
    ) -> None:
        self._settings = settings
        self._edge = edge_client or EdgeClient(
            settings.edge_url, timeout_sec=settings.timeout_sec
        )
        self._cloud = cloud_client or CloudClient(
            settings.cloud_url, timeout_sec=settings.timeout_sec
        )
        self._scheduler = scheduler_client or SchedulerClient(
            settings.scheduler_url, timeout_sec=settings.timeout_sec
        )

    async def orchestrate(self, req: OrchestrateRequest) -> OrchestrationResult:
        """Run one workload end to end and return the unified result."""
        start = time.perf_counter()

        try:
            decision = await self._scheduler.decide(
                req.workload,
                self._settings.edge_url,
                self._settings.cloud_url,
                req.edge_metrics,
                req.cloud_metrics,
                req.network_metrics,
            )
        except UpstreamError as exc:
            logger.error("Scheduler decision failed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=f"Scheduler unavailable: {exc.message}",
            ) from exc
        scheduler_ms = round((time.perf_counter() - start) * 1000.0, 2)

        target = decision.get("target", "error")
        score = float(decision.get("score", 0.0))
        reason = str(decision.get("reason", ""))
        priority = req.workload.priority.value

        fallback_used = False
        fallback_reason: Optional[str] = None
        actual_target: Optional[str] = None
        inference_result: Optional[dict] = None
        inference_ms: Optional[float] = None

        try:
            if target == "edge":
                actual_target = "edge"
                inference_result, inference_ms = await self._run_edge(req)
            elif target == "cloud":
                actual_target = "cloud"
                inference_result, inference_ms = await self._run_cloud(req)
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Workload not executed now: target={target} ({reason})",
                )
        except UpstreamError as exc:
            # 4xx from the node is a client error (e.g. undecodable image):
            # never fall back, surface it as-is.
            if exc.status_code and 400 <= exc.status_code < 500:
                raise HTTPException(
                    status_code=exc.status_code, detail=exc.message
                ) from exc
            # Node failure (5xx / transport): fall back to edge only when the
            # cloud was selected, the workload is high priority and the edge
            # node is healthy.
            if (
                target == "cloud"
                and priority == "high"
                and await self._edge_available()
            ):
                logger.warning(
                    "Cloud inference failed (%s); falling back to edge", exc
                )
                fallback_used = True
                fallback_reason = (
                    f"Cloud inference failed ({exc.message}); fallback to edge"
                )
                actual_target = "edge"
                inference_result, inference_ms = await self._run_edge(req)
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Inference failed: {exc.message}",
                ) from exc

        total_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return OrchestrationResult(
            workload_id=req.workload.workload_id,
            priority=priority,
            selected_target=target,
            actual_target=actual_target,
            decision_score=score,
            decision_reason=reason,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            inference_result=inference_result,
            scheduler_latency_ms=scheduler_ms,
            inference_latency_ms=inference_ms,
            total_latency_ms=total_ms,
        )

    async def _run_edge(self, req: OrchestrateRequest) -> Tuple[dict, float]:
        t0 = time.perf_counter()
        result = await self._edge.detect(
            image_base64=req.image_base64,
            confidence=req.confidence,
            annotated=req.annotated,
            classes=req.classes,
        )
        return result, round((time.perf_counter() - t0) * 1000.0, 2)

    async def _run_cloud(self, req: OrchestrateRequest) -> Tuple[dict, float]:
        t0 = time.perf_counter()
        result = await self._cloud.infer(
            image_base64=req.image_base64,
            confidence=req.confidence,
            annotated=req.annotated,
            classes=req.classes,
        )
        return result, round((time.perf_counter() - t0) * 1000.0, 2)

    async def _edge_available(self) -> bool:
        try:
            await self._edge.health()
            return True
        except UpstreamError:
            return False
