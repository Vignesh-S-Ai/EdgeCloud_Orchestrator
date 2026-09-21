"""Tests for the scheduler data models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from scheduler.models import (
    CloudMetrics,
    Decision,
    EdgeMetrics,
    NetworkMetrics,
    Priority,
    Target,
    Workload,
    WorkloadType,
)


def _metrics(cls):
    return cls(
        cpu_percent=20.0,
        ram_percent=30.0,
        disk_percent=40.0,
        timestamp=datetime.now(timezone.utc),
    )


def test_workload_defaults():
    w = Workload(workload_id="w1", latency_requirement_ms=100.0)
    assert w.priority is Priority.MEDIUM
    assert w.workload_type is WorkloadType.GENERIC
    assert w.estimated_compute is None


def test_workload_accepts_priority_strings():
    w = Workload(workload_id="w1", priority="high", latency_requirement_ms=50.0)
    assert w.priority is Priority.HIGH


def test_workload_rejects_unknown_priority():
    with pytest.raises(ValidationError):
        Workload(workload_id="w1", priority="urgent", latency_requirement_ms=50.0)


def test_workload_rejects_non_positive_latency():
    with pytest.raises(ValidationError):
        Workload(workload_id="w1", latency_requirement_ms=0.0)


def test_metrics_validation():
    with pytest.raises(ValidationError):
        EdgeMetrics(
            cpu_percent=101.0, ram_percent=30.0, disk_percent=40.0,
            timestamp=datetime.now(timezone.utc),
        )
    assert _metrics(EdgeMetrics).cpu_percent == 20.0
    assert _metrics(CloudMetrics).ram_percent == 30.0


def test_network_metrics_validation():
    with pytest.raises(ValidationError):
        NetworkMetrics(latency_ms=-1.0)
    n = NetworkMetrics(latency_ms=42.5, bandwidth_mbps=100.0)
    assert n.latency_ms == 42.5


def test_decision_serializes_with_required_fields():
    d = Decision(
        workload_id="w1",
        target=Target.EDGE,
        score=88.0,
        reason="test reason",
        priority=Priority.HIGH,
    )
    data = d.model_dump()
    assert data["target"] == "edge"
    assert data["reason"] == "test reason"
    assert data["score"] == 88.0
    assert "timestamp" in data
