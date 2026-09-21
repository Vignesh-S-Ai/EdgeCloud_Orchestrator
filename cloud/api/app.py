"""FastAPI application factory for the Cloud Node.

Run with:
    uvicorn cloud.api.app:create_app --factory --host 0.0.0.0 --port 8001

The factory pattern keeps the app stateless at import time and makes testing
trivial (each test can build its own app with a dedicated Settings object).
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..ai.detector import ModelLoadError, YOLODetector
from ..config import Settings, get_settings
from ..monitoring.metrics import MetricsCollector
from .routes import router

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build and configure the Cloud Node FastAPI application."""
    settings = settings or get_settings()
    _configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- Detector (lazy; model download may need network) ---
        detector = YOLODetector(
            model_path=settings.model_path,
            device=settings.model_device,
            img_size=settings.model_img_size,
            confidence=settings.model_confidence,
            iou=settings.model_iou,
            classes=settings.parse_model_classes(),
        )
        try:
            detector.load()
        except ModelLoadError as exc:
            logger.warning("Model not loaded at startup (will retry on demand): %s", exc)
        app.state.detector = detector

        # --- Monitoring ---
        app.state.metrics = MetricsCollector(settings.monitor_interval_sec)
        app.state.started_at = time.time()
        logger.info("Cloud Node '%s' started", settings.service_name)

        yield

    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
        description="Edge-Cloud Orchestration - Cloud Node inference service",
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
