"""FastAPI application factory for the Edge Node.

Run with:
    uvicorn edge.api.app:create_app --factory --host 0.0.0.0 --port 8000

The factory pattern keeps the app stateless at import time and makes testing
trivial (each test can build its own app with a dedicated Settings object).
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..ai.camera import CameraCapture, CameraError
from ..ai.detector import ModelLoadError, YOLODetector
from ..config import Settings, get_settings
from ..monitoring.metrics import MetricsCollector
from ..scheduler.local_scheduler import LocalScheduler
from .routes import router

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build and configure the Edge Node FastAPI application."""
    settings = settings or get_settings()
    _configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- Camera (best effort: an edge node can run without a camera) ---
        camera: Optional[CameraCapture] = None
        try:
            camera = CameraCapture(
                settings.camera_source,
                source_type=settings.resolve_camera_type(),
                width=settings.camera_width,
                height=settings.camera_height,
                fps=settings.camera_fps,
                open_timeout_sec=settings.camera_open_timeout_sec,
            )
            logger.info("Camera source initialised: %s", settings.camera_source)
        except CameraError as exc:
            logger.warning("Camera unavailable - continuing without it: %s", exc)
        app.state.camera = camera

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

        # --- Monitoring + scheduling ---
        app.state.metrics = MetricsCollector(settings.monitor_interval_sec)
        app.state.scheduler = LocalScheduler(
            cpu_threshold=settings.scheduler_cpu_threshold,
            ram_threshold=settings.scheduler_ram_threshold,
            enabled=settings.scheduler_enabled,
            priority=settings.scheduler_priority,
        )
        app.state.started_at = time.time()
        logger.info("Edge Node '%s' started", settings.service_name)

        yield

        if camera is not None:
            camera.release()
            logger.info("Camera released")

    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
        description="Edge-Cloud Orchestration - Edge Node workload host",
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
