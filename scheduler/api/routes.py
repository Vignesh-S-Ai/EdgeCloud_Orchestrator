"""HTTP routes for the Edge-Cloud Decision Engine.

The scheduler API is intentionally small: ``POST /decision`` (the single
placement decision entry point for the orchestration layer) and ``GET /health``.
It is not coupled to KubeEdge yet.
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..models import CloudMetrics, Decision, EdgeMetrics, NetworkMetrics, Workload

logger = logging.getLogger(__name__)

router = APIRouter()


class DecisionRequest(BaseModel):
    """Either supply metrics snapshots, or the node URLs to fetch them live."""

    workload: Workload
    edge_metrics: Optional[EdgeMetrics] = None
    cloud_metrics: Optional[CloudMetrics] = None
    network_metrics: Optional[NetworkMetrics] = None
    edge_url: Optional[str] = None
    cloud_url: Optional[str] = None


class ServiceInfo(BaseModel):
    service: str
    version: str
    uptime_sec: float
    endpoints: list[str]
    policy: str


class ServiceHealth(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


@router.get("/", response_model=ServiceInfo, tags=["service"])
def service_info(request: Request) -> ServiceInfo:
    settings = request.app.state.settings
    return ServiceInfo(
        service=settings.service_name,
        version=settings.version,
        uptime_sec=round(time.time() - request.app.state.started_at, 2),
        endpoints=["/health", "/decision", "/docs"],
        policy=settings.policy,
    )


@router.get("/health", response_model=ServiceHealth, tags=["service"])
def health(request: Request) -> ServiceHealth:
    settings = request.app.state.settings
    return ServiceHealth(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        timestamp=str(time.time()),
    )


@router.post("/decision", response_model=Decision, tags=["scheduler"])
async def decision(payload: DecisionRequest, request: Request) -> Decision:
    """Return a placement decision for a workload.

    Provide ``edge_metrics``/``cloud_metrics``/``network_metrics`` for an
    offline/deterministic decision, or ``edge_url``/``cloud_url`` to fetch the
    metrics and latency live from the running nodes.
    """
    engine = request.app.state.engine

    if payload.edge_url or payload.cloud_url:
        if not (payload.edge_url and payload.cloud_url):
            raise HTTPException(
                status_code=400,
                detail="Both edge_url and cloud_url are required to fetch live metrics",
            )
        return await engine.decide_remote(
            payload.workload, payload.edge_url, payload.cloud_url
        )

    if (
        payload.edge_metrics is None
        or payload.cloud_metrics is None
        or payload.network_metrics is None
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide edge_metrics, cloud_metrics and network_metrics "
            "(or edge_url/cloud_url to fetch them live)",
        )

    return engine.decide(
        payload.workload,
        payload.edge_metrics,
        payload.cloud_metrics,
        payload.network_metrics,
    )
