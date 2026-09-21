"""Central configuration for the Cloud Node.

All values can be overridden through environment variables prefixed with
``CLOUD_`` (e.g. ``CLOUD_MODEL_PATH``, ``CLOUD_MODEL_CONFIDENCE``) or via a
``.env`` file. The Cloud Node shares the model vocabulary with the Edge Node
(``CLOUD_*`` vs ``EDGE_*``) so inference benchmarks are directly comparable.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLOUD_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Service
    # ------------------------------------------------------------------
    service_name: str = "cloud-node"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # YOLO model (same vocabulary as the Edge Node)
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
    # API limits
    # ------------------------------------------------------------------
    max_infer_bytes: int = 10 * 1024 * 1024

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def parse_model_classes(self) -> Optional[list[int]]:
        """Parse the comma separated class list into ints, or None."""
        if not self.model_classes or not self.model_classes.strip():
            return None
        try:
            return [
                int(part.strip())
                for part in self.model_classes.split(",")
                if part.strip()
            ]
        except ValueError:
            return None


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (immutable configuration)."""
    return Settings()
