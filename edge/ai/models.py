"""Typed data models for inference results.

Kept independent of the ML framework so the API and scheduler layers never
import ``ultralytics`` / ``torch`` directly.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field


class BBox(BaseModel):
    """Axis-aligned bounding box in pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float

    @computed_field
    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @computed_field
    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)


class Detection(BaseModel):
    """A single object detection."""

    bbox: BBox
    confidence: float = Field(ge=0.0, le=1.0)
    class_id: int
    class_name: str


class DetectionResult(BaseModel):
    """Result of running inference on one frame."""

    source: str
    timestamp: datetime
    frame_width: int
    frame_height: int
    inference_ms: float
    detections: List[Detection] = Field(default_factory=list)
    annotated_image_base64: Optional[str] = None

    @computed_field
    @property
    def count(self) -> int:
        return len(self.detections)

    @classmethod
    def empty(cls, source: str, width: int, height: int) -> "DetectionResult":
        return cls(
            source=source,
            timestamp=datetime.now(timezone.utc),
            frame_width=width,
            frame_height=height,
            inference_ms=0.0,
        )
