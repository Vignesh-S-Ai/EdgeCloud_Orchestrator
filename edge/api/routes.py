"""HTTP routes for the Edge Node.

Everything the outside world (cloud, dashboard, KubeEdge) can do with the node
flows through these endpoints. The AI layer is never reached directly.
"""

import base64
import logging
import os
import tempfile
import time
from collections import Counter
from typing import Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..ai.detector import ModelLoadError
from ..ai.models import DetectionResult
from ..monitoring.metrics import SystemMetrics
from ..scheduler.local_scheduler import SchedulingDecision

logger = logging.getLogger(__name__)

router = APIRouter()

_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}


# ----------------------------------------------------------------------
# Request / response schemas
# ----------------------------------------------------------------------
class DetectRequest(BaseModel):
    """Base64 JPEG image to run inference on."""

    image_base64: str = Field(min_length=16)
    confidence: Optional[float] = Field(default=None, ge=0.05, le=0.95)
    annotated: bool = False
    classes: Optional[List[int]] = None


class VideoResult(BaseModel):
    """Summary of a batch video-processing job."""

    source: str
    total_frames: int
    frames_processed: int
    elapsed_ms: float
    effective_fps: float
    detections: Dict[str, int]
    annotated_sample_base64: Optional[str] = None


class ServiceInfo(BaseModel):
    service: str
    version: str
    uptime_sec: float
    endpoints: List[str]
    scheduler: SchedulingDecision


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str
    model_loaded: bool
    camera_open: bool
    camera_status: str
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
    """Service metadata plus the latest scheduling decision."""
    settings = request.app.state.settings
    scheduler: LocalScheduler = request.app.state.scheduler
    metrics = request.app.state.metrics.collect()
    decision = scheduler.decide(metrics)

    return ServiceInfo(
        service=settings.service_name,
        version=settings.version,
        uptime_sec=round(time.time() - request.app.state.started_at, 2),
        endpoints=[
            "/health",
            "/metrics",
            "/detect",
            "/detect/video",
            "/docs",
        ],
        scheduler=decision,
    )


@router.get("/health", response_model=HealthStatus, tags=["service"])
def health(request: Request) -> HealthStatus:
    """Liveness/readiness probe for Docker and KubeEdge."""
    detector = request.app.state.detector
    camera = getattr(request.app.state, "camera", None)
    settings = request.app.state.settings

    model_loaded = detector.is_loaded()
    camera_open = bool(camera and camera.is_open())

    # Camera input is optional: the primary Edge API accepts uploaded images.
    # Report inference readiness separately from the optional camera attachment.
    status = "ok" if model_loaded else "degraded"
    camera_status = "connected" if camera_open else "not_connected"

    return HealthStatus(
        status=status,
        service=settings.service_name,
        version=settings.version,
        model_loaded=model_loaded,
        camera_open=camera_open,
        camera_status=camera_status,
        timestamp=str(time.time()),
    )


@router.get("/metrics", response_model=SystemMetrics, tags=["monitoring"])
def metrics(request: Request) -> SystemMetrics:
    """Current CPU, RAM and disk utilisation."""
    return request.app.state.metrics.collect()


@router.post("/detect", response_model=DetectionResult, tags=["inference"])
def detect(payload: DetectRequest, request: Request) -> DetectionResult:
    """Run YOLOv8 inference on a base64-encoded image.

    The model is never downloaded on the inference hot path; it is loaded once
    at startup (or lazily on first call) and reused.
    """
    settings = request.app.state.settings
    if len(payload.image_base64) > settings.max_detect_bytes:
        raise HTTPException(status_code=413, detail="Image payload too large")

    frame = _decode_image(payload.image_base64)
    detector = request.app.state.detector

    try:
        result = detector.predict(frame, confidence=payload.confidence, classes=payload.classes)
    except ModelLoadError as exc:
        logger.error("Detection failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if payload.annotated:
        annotated = detector.annotate(frame, result.detections)
        result.annotated_image_base64 = detector.frame_to_base64_jpeg(annotated)

    return result


@router.post("/detect/video", response_model=VideoResult, tags=["inference"])
async def detect_video(
    request: Request,
    file: UploadFile = File(...),
    frame_step: int = Query(default=5, ge=1, le=100),
    confidence: Optional[float] = Query(default=None, ge=0.05, le=0.95),
    return_sample: bool = Query(default=False),
) -> VideoResult:
    """Batch-process an uploaded video file.

    Frames are streamed off disk (not loaded into memory) and only every
    ``frame_step``-th frame is passed to the detector, which makes the
    endpoint safe for large files.
    """
    settings = request.app.state.settings
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported video type '{ext}'")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Video payload too large")

    detector = request.app.state.detector
    totals: Counter = Counter()
    frame_counter = 0
    frames_processed = 0
    annotated_sample: Optional[str] = None
    source_name = file.filename or "upload"

    fd, path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)

        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Cannot decode uploaded video")

        start = time.perf_counter()
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frame_counter += 1
                if (frame_counter - 1) % frame_step != 0:
                    continue
                try:
                    result = await run_in_threadpool(detector.predict, frame, confidence)
                except ModelLoadError as exc:
                    raise HTTPException(status_code=503, detail=str(exc)) from exc
                frames_processed += 1
                for det in result.detections:
                    totals[det.class_name] += 1
                if return_sample and annotated_sample is None:
                    annotated = await run_in_threadpool(
                        detector.annotate, frame, result.detections
                    )
                    annotated_sample = await run_in_threadpool(
                        detector.frame_to_base64_jpeg, annotated
                    )
        finally:
            cap.release()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
    finally:
        os.remove(path)

    effective_fps = (frames_processed / elapsed_ms * 1000.0) if elapsed_ms > 0 else 0.0

    return VideoResult(
        source=source_name,
        total_frames=frame_counter,
        frames_processed=frames_processed,
        elapsed_ms=round(elapsed_ms, 2),
        effective_fps=round(effective_fps, 2),
        detections=dict(totals),
        annotated_sample_base64=annotated_sample,
    )
