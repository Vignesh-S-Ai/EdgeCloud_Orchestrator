"""FastAPI application factory for the Edge-Cloud Decision Engine.

Run with:
    uvicorn scheduler.api.app:create_app --factory --host 0.0.0.0 --port 8002
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import SchedulerSettings, get_scheduler_settings
from ..decision_engine import DecisionEngine
from .routes import router

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def create_app(settings: Optional[SchedulerSettings] = None) -> FastAPI:
    """Build and configure the Decision Engine FastAPI application."""
    settings = settings or get_scheduler_settings()
    _configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = DecisionEngine(settings)
        app.state.started_at = time.time()
        logger.info(
            "Decision Engine '%s' started (policy=%s)",
            settings.service_name,
            settings.policy,
        )
        yield

    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
        description="Edge-Cloud Orchestration - latency/resource-aware placement engine",
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
