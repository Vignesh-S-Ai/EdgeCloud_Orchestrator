"""Stateful placement hysteresis and workload isolation tests."""

import time
from datetime import datetime, timezone

from scheduler.config import SchedulerSettings
from scheduler.decision_engine import DecisionEngine
from scheduler.models import CloudMetrics, EdgeMetrics, NetworkMetrics, Priority, Target, Workload


def settings(**overrides):
    return SchedulerSettings(_env_file=None, **overrides)


def workload(wid="w1", priority=Priority.MEDIUM):
    return Workload(workload_id=wid, priority=priority, latency_requirement_ms=100.0)


def edge(cpu, ram=40.0, disk=40.0):
    return EdgeMetrics(
        cpu_percent=cpu, ram_percent=ram, disk_percent=disk,
        timestamp=datetime.now(timezone.utc),
    )


def cloud():
    return CloudMetrics(
        cpu_percent=30.0, ram_percent=40.0, disk_percent=50.0,
        timestamp=datetime.now(timezone.utc),
    )


def network():
    return NetworkMetrics(latency_ms=20.0)


def test_cloud_to_edge_requires_full_recovery_margin():
    engine = DecisionEngine(settings(hysteresis_margin_percent=5.0))
    wl = workload()
    assert engine.decide(wl, edge(76.0), cloud(), network()).target is Target.CLOUD
    # Medium priority threshold is 75%; ordinary healthy is not enough.
    held = engine.decide(wl, edge(74.9), cloud(), network())
    assert held.target is Target.CLOUD
    assert "recovery margin" in held.reason
    recovered = engine.decide(wl, edge(70.0), cloud(), network())
    assert recovered.target is Target.EDGE


def test_overload_transition_to_cloud_is_immediate():
    engine = DecisionEngine(settings())
    wl = workload()
    assert engine.decide(wl, edge(70.0), cloud(), network()).target is Target.EDGE
    assert engine.decide(wl, edge(75.1), cloud(), network()).target is Target.CLOUD


def test_hysteresis_stops_threshold_jitter_oscillation():
    engine = DecisionEngine(settings(hysteresis_margin_percent=5.0))
    wl = workload()
    targets = [
        engine.decide(wl, edge(cpu), cloud(), network()).target
        for cpu in (75.1, 74.9, 75.1, 74.9, 75.0, 74.8, 70.0)
    ]
    assert targets == [
        Target.CLOUD, Target.CLOUD, Target.CLOUD, Target.CLOUD,
        Target.CLOUD, Target.CLOUD, Target.EDGE,
    ]


def test_workloads_keep_independent_placement_state():
    engine = DecisionEngine(settings())
    a, b = workload("a"), workload("b")
    assert engine.decide(a, edge(80.0), cloud(), network()).target is Target.CLOUD
    assert engine.decide(b, edge(60.0), cloud(), network()).target is Target.EDGE
    # Workload B's prior EDGE placement must not inherit A's CLOUD hysteresis.
    assert engine.decide(b, edge(74.9), cloud(), network()).target is Target.EDGE
    assert engine.decide(a, edge(74.9), cloud(), network()).target is Target.CLOUD


def test_priority_change_uses_current_priority_recovery_threshold():
    engine = DecisionEngine(settings(hysteresis_margin_percent=5.0))
    wl = workload(priority=Priority.LOW)
    assert engine.decide(wl, edge(71.0), cloud(), network()).target is Target.CLOUD
    # High priority threshold rises to 85, but recovery threshold is 80.
    high = workload(priority=Priority.HIGH)
    assert engine.decide(high, edge(82.0), cloud(), network()).target is Target.CLOUD
    assert engine.decide(high, edge(80.0), cloud(), network()).target is Target.EDGE


def test_state_expires_and_does_not_pin_abandoned_workload():
    engine = DecisionEngine(settings(placement_state_ttl_sec=0.01))
    wl = workload()
    assert engine.decide(wl, edge(80.0), cloud(), network()).target is Target.CLOUD
    time.sleep(0.02)
    # Expired history means the ordinary healthy-edge decision applies.
    assert engine.decide(wl, edge(74.9), cloud(), network()).target is Target.EDGE


def test_cloud_unavailable_does_not_force_hysteresis():
    engine = DecisionEngine(settings())
    wl = workload()
    assert engine.decide(wl, edge(80.0), cloud(), network()).target is Target.CLOUD
    saturated_cloud = CloudMetrics(
        cpu_percent=95.0, ram_percent=95.0, disk_percent=95.0,
        timestamp=datetime.now(timezone.utc),
    )
    # Edge is healthy under ordinary thresholds; cloud is not a viable hold.
    assert engine.decide(wl, edge(74.9), saturated_cloud, network()).target is Target.EDGE
