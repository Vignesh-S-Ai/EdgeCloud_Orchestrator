"""Tests for the rule-based placement policy.

Covers the eight required decision scenarios plus boundary conditions. All
decisions must be deterministic and carry an explanatory reason.
"""

from datetime import datetime, timezone

import pytest

from scheduler.config import SchedulerSettings
from scheduler.models import (
    CloudMetrics,
    EdgeMetrics,
    NetworkMetrics,
    Priority,
    Target,
    Workload,
)
from scheduler.policies import RuleBasedPolicy


def _settings(**overrides) -> SchedulerSettings:
    defaults = dict(
        edge_cpu_threshold=70.0,
        edge_ram_threshold=70.0,
        edge_disk_threshold=85.0,
        cloud_cpu_threshold=80.0,
        cloud_ram_threshold=80.0,
        cloud_disk_threshold=90.0,
        max_latency_ms=200.0,
        high_priority_latency_ms=50.0,
    )
    defaults.update(overrides)
    return SchedulerSettings(_env_file=None, **defaults)


def _workload(
    priority: Priority = Priority.MEDIUM,
    latency: float = 200.0,
    wid: str = "w1",
) -> Workload:
    return Workload(
        workload_id=wid,
        priority=priority,
        latency_requirement_ms=latency,
    )


def _edge(cpu: float, ram: float, disk: float) -> EdgeMetrics:
    return EdgeMetrics(
        cpu_percent=cpu, ram_percent=ram, disk_percent=disk,
        timestamp=datetime.now(timezone.utc),
    )


def _cloud(cpu: float, ram: float, disk: float) -> CloudMetrics:
    return CloudMetrics(
        cpu_percent=cpu, ram_percent=ram, disk_percent=disk,
        timestamp=datetime.now(timezone.utc),
    )


def _network(latency: float) -> NetworkMetrics:
    return NetworkMetrics(latency_ms=latency)


def _decide(workload, edge, cloud, network, **settings):
    policy = RuleBasedPolicy(_settings(**settings))
    return policy.decide(workload, edge, cloud, network)


# ----------------------------------------------------------------------
# The eight required scenarios
# ----------------------------------------------------------------------
def test_healthy_edge_runs_locally():
    d = _decide(
        _workload(),
        _edge(20.0, 30.0, 40.0),
        _cloud(30.0, 40.0, 50.0),
        _network(10.0),
    )
    assert d.target is Target.EDGE
    assert d.score > 50.0
    assert "within capacity" in d.reason


def test_overloaded_edge_offloads():
    d = _decide(
        _workload(),
        _edge(95.0, 90.0, 80.0),
        _cloud(40.0, 40.0, 50.0),
        _network(20.0),
    )
    assert d.target is Target.CLOUD
    assert "offload" in d.reason


def test_high_latency_high_priority_stays_edge():
    d = _decide(
        _workload(priority=Priority.HIGH, latency=50.0),
        _edge(50.0, 50.0, 50.0),
        _cloud(40.0, 40.0, 50.0),
        _network(500.0),  # far above max_latency_ms
    )
    assert d.target is Target.EDGE


def test_low_priority_overloaded_edge_offloads():
    d = _decide(
        _workload(priority=Priority.LOW),
        _edge(90.0, 85.0, 80.0),
        _cloud(40.0, 40.0, 50.0),
        _network(20.0),
    )
    assert d.target is Target.CLOUD


def test_both_unhealthy_returns_error():
    d = _decide(
        _workload(),
        _edge(95.0, 95.0, 90.0),
        _cloud(90.0, 90.0, 95.0),
        _network(20.0),
    )
    assert d.target is Target.ERROR
    assert "both saturated" in d.reason


def test_edge_cpu_boundary():
    edge = _edge(70.0, 40.0, 40.0)  # exactly at LOW-priority CPU threshold
    at_threshold = _decide(_workload(priority=Priority.LOW), edge, _cloud(40.0, 40.0, 50.0), _network(20.0))
    assert at_threshold.target is Target.EDGE

    edge_over = _edge(70.1, 40.0, 40.0)
    over = _decide(_workload(priority=Priority.LOW), edge_over, _cloud(40.0, 40.0, 50.0), _network(20.0))
    assert over.target is Target.CLOUD


def test_edge_ram_boundary():
    edge = _edge(40.0, 70.0, 40.0)
    at_threshold = _decide(_workload(priority=Priority.LOW), edge, _cloud(40.0, 40.0, 50.0), _network(20.0))
    assert at_threshold.target is Target.EDGE

    edge_over = _edge(40.0, 70.1, 40.0)
    over = _decide(_workload(priority=Priority.LOW), edge_over, _cloud(40.0, 40.0, 50.0), _network(20.0))
    assert over.target is Target.CLOUD


def test_latency_boundary():
    overloaded_edge = _edge(90.0, 90.0, 80.0)
    at_max = _decide(
        _workload(priority=Priority.LOW), overloaded_edge, _cloud(40.0, 40.0, 50.0), _network(200.0)
    )
    assert at_max.target is Target.CLOUD

    above_max = _decide(
        _workload(priority=Priority.LOW), overloaded_edge, _cloud(40.0, 40.0, 50.0), _network(200.1)
    )
    assert above_max.target is Target.QUEUE


# ----------------------------------------------------------------------
# Extra scenarios
# ----------------------------------------------------------------------
def test_edge_overloaded_poor_network_high_priority_runs_edge():
    d = _decide(
        _workload(priority=Priority.HIGH),
        _edge(95.0, 90.0, 80.0),
        _cloud(40.0, 40.0, 50.0),
        _network(500.0),
    )
    assert d.target is Target.EDGE
    assert "best effort" in d.reason


def test_edge_overloaded_poor_network_low_priority_queued():
    d = _decide(
        _workload(priority=Priority.LOW),
        _edge(95.0, 90.0, 80.0),
        _cloud(40.0, 40.0, 50.0),
        _network(500.0),
    )
    assert d.target is Target.QUEUE
    assert "queued" in d.reason


def test_cloud_overloaded_healthy_edge_stays_local():
    d = _decide(
        _workload(),
        _edge(40.0, 40.0, 50.0),
        _cloud(95.0, 95.0, 95.0),
        _network(20.0),
    )
    assert d.target is Target.EDGE


def test_missing_metrics_returns_error():
    policy = RuleBasedPolicy(_settings())
    d = policy.decide(_workload(), None, _cloud(40.0, 40.0, 50.0), _network(20.0))
    assert d.target is Target.ERROR
    assert "unavailable" in d.reason


def test_unknown_latency_blocks_offload():
    d = _decide(
        _workload(priority=Priority.LOW),
        _edge(90.0, 90.0, 80.0),
        _cloud(40.0, 40.0, 50.0),
        None,
    )
    assert d.target is Target.QUEUE


def test_thresholds_are_configurable():
    d = _decide(
        _workload(priority=Priority.LOW),
        _edge(75.0, 40.0, 40.0),
        _cloud(40.0, 40.0, 50.0),
        _network(20.0),
        edge_cpu_threshold=80.0,
    )
    assert d.target is Target.EDGE


def test_decisions_are_deterministic():
    args = (
        _workload(),
        _edge(95.0, 90.0, 80.0),
        _cloud(40.0, 40.0, 50.0),
        _network(20.0),
    )
    first = _decide(*args)
    second = _decide(*args)
    assert first.target is second.target is Target.CLOUD
    assert first.score == second.score
    assert first.reason == second.reason
