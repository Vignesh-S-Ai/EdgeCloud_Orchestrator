"""Central configuration for the Edge-Cloud Decision Engine.

All values can be overridden through environment variables prefixed with
``SCHEDULER_`` (e.g. ``SCHEDULER_EDGE_CPU_THRESHOLD``,
``SCHEDULER_MAX_LATENCY_MS``) or via a ``.env`` file. No policy value is
hardcoded in the decision logic.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCHEDULER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Service
    # ------------------------------------------------------------------
    service_name: str = "scheduler"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8002
    log_level: str = "INFO"

    # Which policy implementation to use (only "rule_based" ships in M3).
    policy: str = "rule_based"

    # ------------------------------------------------------------------
    # Edge resource thresholds (percent)
    # ------------------------------------------------------------------
    edge_cpu_threshold: float = 70.0
    edge_ram_threshold: float = 70.0
    edge_disk_threshold: float = 85.0

    # ------------------------------------------------------------------
    # Cloud resource thresholds (percent)
    # ------------------------------------------------------------------
    cloud_cpu_threshold: float = 80.0
    cloud_ram_threshold: float = 80.0
    cloud_disk_threshold: float = 90.0

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------
    # Max acceptable edge->cloud latency for offloading (ms).
    max_latency_ms: float = 200.0
    # Latency budget (ms) that marks a workload as strict-latency (high prio).
    high_priority_latency_ms: float = 50.0

    # ------------------------------------------------------------------
    # Local-run bias per priority: raises the edge thresholds by this amount
    # so higher-priority workloads are more willing to stay on the edge.
    # ------------------------------------------------------------------
    priority_edge_bias_low: float = 0.0
    priority_edge_bias_medium: float = 5.0
    priority_edge_bias_high: float = 15.0

    # ------------------------------------------------------------------
    # Metrics client
    # ------------------------------------------------------------------
    metrics_timeout_sec: float = 2.0
    # TTL (seconds) for caching repeated live node /metrics fetches. 0 disables
    # caching (always-fresh probes). A small positive value removes the dominant
    # recurring metric-fetch cost within the window; the /health latency probe is
    # always measured live regardless of this setting.
    metrics_ttl_sec: float = 0.0


@lru_cache
def get_scheduler_settings() -> SchedulerSettings:
    """Return a cached SchedulerSettings instance (immutable configuration)."""
    return SchedulerSettings()
