"""FastAPI application factory for the Edge-Cloud Orchestrator.

Run with:
    uvicorn orchestrator.api.app:create_app --factory --host 0.0.0.0 --port 8003
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import OrchestratorSettings, get_orchestrator_settings
from ..service import OrchestrationService
from .routes import router

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def create_app(settings: Optional[OrchestratorSettings] = None) -> FastAPI:
    """Build and configure the Orchestrator FastAPI application."""
    settings = settings or get_orchestrator_settings()
    _configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = OrchestrationService(settings)
        app.state.started_at = time.time()
        logger.info(
            "Orchestrator '%s' started (edge=%s cloud=%s scheduler=%s)",
            settings.service_name,
            settings.edge_url,
            settings.cloud_url,
            settings.scheduler_url,
        )
        yield

    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
        description="Edge-Cloud Orchestration - end-to-end workload orchestration entry point",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    return app
