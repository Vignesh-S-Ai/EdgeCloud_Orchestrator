"""System metrics collection.

The metrics exposed here (CPU, RAM, disk) are the inputs consumed by the
:mod:`edge.scheduler` decision engine and later by the cloud dashboard.
"""

import logging
from datetime import datetime, timezone

import psutil
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SystemMetrics(BaseModel):
    """Snapshot of node resource utilisation at a point in time."""

    cpu_percent: float = Field(ge=0.0, le=100.0)
    ram_percent: float = Field(ge=0.0, le=100.0)
    ram_used_gb: float
    ram_total_gb: float
    disk_percent: float = Field(ge=0.0, le=100.0)
    disk_used_gb: float
    disk_total_gb: float
    timestamp: datetime


class MetricsCollector:
    """Collects current system metrics from psutil."""

    def __init__(self, interval_sec: float = 1.0) -> None:
        self._interval = max(0.05, float(interval_sec))
        # Warm up the CPU percent counter (psutil measures a delta).
        psutil.cpu_percent(interval=None)

    def collect(self) -> SystemMetrics:
        """Return a fresh snapshot of system utilisation."""
        cpu = psutil.cpu_percent(interval=self._interval)
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        metrics = SystemMetrics(
            cpu_percent=round(cpu, 2),
            ram_percent=round(vm.percent, 2),
            ram_used_gb=round(vm.used / (1024**3), 2),
            ram_total_gb=round(vm.total / (1024**3), 2),
            disk_percent=round(disk.percent, 2),
            disk_used_gb=round(disk.used / (1024**3), 2),
            disk_total_gb=round(disk.total / (1024**3), 2),
            timestamp=datetime.now(timezone.utc),
        )
        logger.debug("Metrics collected: cpu=%.1f%% ram=%.1f%%", metrics.cpu_percent, metrics.ram_percent)
        return metrics
