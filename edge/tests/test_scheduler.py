"""Tests for the local decision engine (scheduler)."""

from datetime import datetime, timezone

import pytest

from edge.monitoring.metrics import SystemMetrics
from edge.scheduler.local_scheduler import LocalScheduler


def _metrics(cpu: float, ram: float, disk: float = 50.0) -> SystemMetrics:
    return SystemMetrics(
        cpu_percent=cpu,
        ram_percent=ram,
        ram_used_gb=4.0,
        ram_total_gb=8.0,
        disk_percent=disk,
        disk_used_gb=100.0,
        disk_total_gb=250.0,
        timestamp=datetime.now(timezone.utc),
    )


def test_idle_node_runs_locally():
    scheduler = LocalScheduler(cpu_threshold=80.0, ram_threshold=80.0, priority="medium")
    decision = scheduler.decide(_metrics(cpu=20.0, ram=30.0))
    assert decision.run_locally is True
    assert decision.engine == "local"


def test_loaded_node_offloads():
    scheduler = LocalScheduler(cpu_threshold=80.0, ram_threshold=80.0, priority="medium")
    decision = scheduler.decide(_metrics(cpu=95.0, ram=90.0))
    assert decision.run_locally is False


def test_high_priority_keeps_local():
    scheduler = LocalScheduler(cpu_threshold=80.0, ram_threshold=80.0, priority="high")
    # 85% composite is above the 80 threshold, but the high-priority bias
    # (+15) pushes the offload threshold to 95 -> still local.
    decision = scheduler.decide(_metrics(cpu=85.0, ram=85.0), priority="high")
    assert decision.run_locally is True


def test_disabled_scheduler_pins_local():
    scheduler = LocalScheduler(enabled=False)
    decision = scheduler.decide(_metrics(cpu=99.0, ram=99.0))
    assert decision.run_locally is True
    assert "disabled" in decision.reason.lower()


def test_score_bounds():
    scheduler = LocalScheduler()
    decision = scheduler.decide(_metrics(cpu=0.0, ram=0.0))
    assert 0.0 <= decision.score <= 100.0
