"""HTTP routes for the Cloud Node.

Everything the outside world (Edge nodes, dashboard) can do with the cloud
service flows through these endpoints. The AI layer is never reached directly.
"""

import base64
import logging
import time
from typing import List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..ai.detector import ModelLoadError
from ..ai.models import DetectionResult
from ..monitoring.metrics import SystemMetrics

logger = logging.getLogger(__name__)

router = APIRouter()


# ----------------------------------------------------------------------
# Request / response schemas
# ----------------------------------------------------------------------
class InferRequest(BaseModel):
    """Base64 JPEG image to run cloud inference on.

    The payload format matches the Edge Node ``/detect`` endpoint so an Edge
    Node can send the exact same ``image_base64`` it receives from its camera.
    """

    image_base64: str = Field(min_length=16)
    confidence: Optional[float] = Field(default=None, ge=0.05, le=0.95)
    annotated: bool = False
    classes: Optional[List[int]] = None


class ServiceInfo(BaseModel):
    service: str
    version: str
    uptime_sec: float
    endpoints: List[str]


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str
    model_loaded: bool
    timestamp: str


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _decode_image(image_base64: str) -> np.ndarray:
    """Decode a base64 string into a BGR numpy frame."""
    try:
        raw = base64.b64decode(image_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 payload") from exc
    buffer = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Base64 payload is not a decodable image")
    return frame


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@router.get("/", response_model=ServiceInfo, tags=["service"])
def service_info(request: Request) -> ServiceInfo:
    """Service metadata."""
    settings = request.app.state.settings
    return ServiceInfo(
        service=settings.service_name,
        version=settings.version,
        uptime_sec=round(time.time() - request.app.state.started_at, 2),
        endpoints=["/health", "/metrics", "/infer", "/docs"],
    )


@router.get("/health", response_model=HealthStatus, tags=["service"])
def health(request: Request) -> HealthStatus:
    """Liveness/readiness probe for Docker and later KubeEdge/EC2."""

    settings = request.app.state.settings
    model_loaded = request.app.state.detector.is_loaded()

    return HealthStatus(
        status="ok" if model_loaded else "degraded",
        service=settings.service_name,
        version=settings.version,
        model_loaded=model_loaded,
        timestamp=str(time.time()),
    )


@router.get("/metrics", response_model=SystemMetrics, tags=["monitoring"])
def metrics(request: Request) -> SystemMetrics:
    """Current CPU, RAM and disk utilisation."""
    return request.app.state.metrics.collect()


@router.post("/infer", response_model=DetectionResult, tags=["inference"])
def infer(payload: InferRequest, request: Request) -> DetectionResult:
    """Run YOLOv8 inference on a base64-encoded image.

    The model is never downloaded on the inference hot path; it is loaded once
    at startup (or lazily on first call) and reused.
    """
    settings = request.app.state.settings
    if len(payload.image_base64) > settings.max_infer_bytes:
        raise HTTPException(status_code=413, detail="Image payload too large")

    frame = _decode_image(payload.image_base64)
    detector = request.app.state.detector

    try:
        result = detector.predict(frame, confidence=payload.confidence, classes=payload.classes)
    except ModelLoadError as exc:
        logger.error("Inference failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if payload.annotated:
        annotated = detector.annotate(frame, result.detections)
        result.annotated_image_base64 = detector.frame_to_base64_jpeg(annotated)

    return result
