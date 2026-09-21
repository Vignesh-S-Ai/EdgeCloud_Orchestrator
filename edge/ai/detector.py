"""YOLOv8 detector.

The heavyweight dependencies (``ultralytics``, ``torch``) are imported lazily
inside :meth:`YOLODetector.load`, so importing the Edge Node application does
not pay the cost (or the failure risk) of loading the model. The detector is
safe for concurrent use because inference is serialized with a lock.
"""

import base64
import logging
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

import cv2
import numpy as np

from .models import BBox, Detection, DetectionResult

logger = logging.getLogger(__name__)


class ModelLoadError(RuntimeError):
    """Raised when the YOLO model cannot be loaded."""


class YOLODetector:
    """Thin, framework-agnostic wrapper around Ultralytics YOLOv8."""

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        device: str = "cpu",
        img_size: int = 640,
        confidence: float = 0.5,
        iou: float = 0.45,
        classes: Optional[List[int]] = None,
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._img_size = img_size
        self._confidence = confidence
        self._iou = iou
        self._classes = classes

        self._model = None
        self._names: Optional[List[str]] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def load(self) -> "YOLODetector":
        """Load (or download on first use) the YOLO weights.

        ``yolov8n.pt`` is fetched automatically by Ultralytics if missing.
        """
        if self._model is not None:
            return self

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ModelLoadError(
                "ultralytics is not installed. Run: pip install -r requirements.txt"
            ) from exc

        try:
            logger.info("Loading model %s on device=%s ...", self._model_path, self._device)
            self._model = YOLO(self._model_path)
            self._names = self._model.names
        except Exception as exc:
            raise ModelLoadError(f"Failed to load model '{self._model_path}': {exc}") from exc

        logger.info("Model loaded: %d classes", len(self._names))
        return self

    def is_loaded(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def predict(
        self,
        frame: np.ndarray,
        confidence: Optional[float] = None,
        classes: Optional[List[int]] = None,
    ) -> DetectionResult:
        """Run detection on a single BGR frame."""
        if frame is None:
            raise ValueError("Cannot run inference on an empty frame")

        if self._model is None:
            self.load()

        conf = confidence if confidence is not None else self._confidence
        cls = classes if classes is not None else self._classes

        start = time.perf_counter()
        with self._lock:
            results = self._model.predict(
                source=frame,
                conf=conf,
                iou=self._iou,
                imgsz=self._img_size,
                device=self._device,
                classes=cls,
                verbose=False,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        detections: List[Detection] = []
        boxes = results[0].boxes
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            for box, conf_val, cls_id in zip(xyxy, confs, cls_ids):
                x1, y1, x2, y2 = box.tolist()
                detections.append(
                    Detection(
                        bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
                        confidence=float(conf_val),
                        class_id=int(cls_id),
                        class_name=str(self._names[cls_id]),
                    )
                )

        height, width = frame.shape[:2]
        return DetectionResult(
            source=self._model_path,
            timestamp=datetime.now(timezone.utc),
            frame_width=width,
            frame_height=height,
            inference_ms=round(elapsed_ms, 2),
            detections=detections,
        )

    # ------------------------------------------------------------------
    # Visualization helpers
    # ------------------------------------------------------------------
    def annotate(self, frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
        """Draw bounding boxes and labels on a copy of the frame."""
        out = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = (
                int(det.bbox.x1),
                int(det.bbox.y1),
                int(det.bbox.x2),
                int(det.bbox.y2),
            )
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{det.class_name} {det.confidence:.2f}"
            cv2.putText(
                out,
                label,
                (x1, max(0, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2,
            )
        return out

    @staticmethod
    def frame_to_base64_jpeg(frame: np.ndarray, quality: int = 80) -> str:
        """Encode a BGR frame to a base64 JPEG string."""
        ok, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
        if not ok:
            raise ValueError("Failed to encode frame as JPEG")
        return base64.b64encode(buffer.tobytes()).decode("ascii")
