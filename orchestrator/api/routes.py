"""HTTP routes for the Edge-Cloud Orchestrator.

Exposes ``POST /orchestrate`` (the single end-to-end entry point) and the
standard ``GET /`` / ``GET /health`` service endpoints.
"""

import logging
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..models import OrchestrateRequest, OrchestrationResult

logger = logging.getLogger(__name__)

router = APIRouter()


class ServiceInfo(BaseModel):
    service: str
    version: str
    uptime_sec: float
    endpoints: list[str]
    edge_url: str
    cloud_url: str
    scheduler_url: str


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
        endpoints=["/health", "/orchestrate", "/docs"],
        edge_url=settings.edge_url,
        cloud_url=settings.cloud_url,
        scheduler_url=settings.scheduler_url,
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


@router.post("/orchestrate", response_model=OrchestrationResult, tags=["orchestration"])
async def orchestrate(payload: OrchestrateRequest, request: Request) -> OrchestrationResult:
    """Place the workload via the scheduler and run inference on the chosen node."""
    return await request.app.state.service.orchestrate(payload)
