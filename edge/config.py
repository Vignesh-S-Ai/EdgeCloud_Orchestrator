"""Central configuration for the Edge Node.

All values can be overridden through environment variables prefixed with
``EDGE_`` (e.g. ``EDGE_CAMERA_SOURCE``, ``EDGE_MODEL_CONFIDENCE``) or via a
``.env`` file. This keeps the node deployable across Docker, K3s and KubeEdge
without any code changes.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EDGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Service
    # ------------------------------------------------------------------
    service_name: str = "edge-node"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # Camera / video source
    # ------------------------------------------------------------------
    # "0" (webcam index), "rtsp://user:pass@host/stream", or a local file path.
    camera_source: str = "0"
    # Optional override: "webcam" | "rtsp" | "file".
    # When None it is auto-detected from camera_source.
    camera_type: Optional[Literal["webcam", "rtsp", "file"]] = None
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    # OpenCV blocks when a device index has no camera; abort after this long.
    camera_open_timeout_sec: float = 5.0

    # ------------------------------------------------------------------
    # YOLO model
    # ------------------------------------------------------------------
    model_path: str = "yolov8n.pt"
    model_confidence: float = 0.5
    model_iou: float = 0.45
    model_device: str = "cpu"
    model_img_size: int = 640
    # Optional comma separated COCO class ids, e.g. "0,2,5". None = all classes.
    model_classes: Optional[str] = None

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------
    monitor_interval_sec: float = 1.0

    # ------------------------------------------------------------------
    # Local decision engine (scheduler)
    # ------------------------------------------------------------------
    scheduler_enabled: bool = True
    scheduler_cpu_threshold: float = 80.0
    scheduler_ram_threshold: float = 80.0
    scheduler_priority: str = "medium"

    # ------------------------------------------------------------------
    # API limits
    # ------------------------------------------------------------------
    max_upload_bytes: int = 200 * 1024 * 1024
    max_detect_bytes: int = 10 * 1024 * 1024

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def resolve_camera_type(self) -> str:
        """Auto-detect the video source kind when it is not explicit."""
        if self.camera_type:
            return self.camera_type
        source = self.camera_source.strip()
        if source.isdigit():
            return "webcam"
        if source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://")):
            return "rtsp"
        return "file"

    def parse_model_classes(self) -> Optional[list[int]]:
        """Parse the comma separated class list into ints, or None."""
        if not self.model_classes or not self.model_classes.strip():
            return None
        try:
            return [int(part.strip()) for part in self.model_classes.split(",") if part.strip()]
        except ValueError:
            return None


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (immutable configuration)."""
    return Settings()
