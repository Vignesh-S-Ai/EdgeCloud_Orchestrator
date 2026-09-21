"""Central configuration for the Edge-Cloud Orchestrator.

All values can be overridden through environment variables prefixed with
``ORCHESTRATOR_`` (e.g. ``ORCHESTRATOR_EDGE_URL``,
``ORCHESTRATOR_CLOUD_URL``, ``ORCHESTRATOR_SCHEDULER_URL``) or via a ``.env``
file. The URLs are the public API base URLs of the Edge Node, Cloud Node and
Decision Engine respectively.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Service
    # ------------------------------------------------------------------
    service_name: str = "orchestrator"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8003
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # Upstream service URLs (public APIs only)
    # ------------------------------------------------------------------
    edge_url: str = "http://localhost:8000"
    cloud_url: str = "http://localhost:8001"
    scheduler_url: str = "http://localhost:8002"

    # HTTP timeout for each upstream call (scheduler decision, inference).
    timeout_sec: float = 30.0


@lru_cache
def get_orchestrator_settings() -> OrchestratorSettings:
    """Return a cached OrchestratorSettings instance (immutable configuration)."""
    return OrchestratorSettings()
