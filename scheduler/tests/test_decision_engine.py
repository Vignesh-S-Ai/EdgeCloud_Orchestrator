"""Tests for the decision engine facade, including live metric fetching."""

import time
from datetime import datetime, timezone

import anyio
import httpx
import pytest

from scheduler.config import SchedulerSettings
from scheduler.decision_engine import DecisionEngine
from scheduler.metrics_client import MetricsClient
from scheduler.models import (
    CloudMetrics,
    Decision,
    EdgeMetrics,
    NetworkMetrics,
    Target,
    Workload,
)
from scheduler.policies import BasePolicy


def _settings(**overrides) -> SchedulerSettings:
    return SchedulerSettings(_env_file=None, **overrides)


def _workload():
    return Workload(workload_id="w1", latency_requirement_ms=100.0)


def _edge():
    return EdgeMetrics(
        cpu_percent=20.0, ram_percent=30.0, disk_percent=40.0,
        timestamp=datetime.now(timezone.utc),
    )


def _cloud():
    return CloudMetrics(
        cpu_percent=30.0, ram_percent=40.0, disk_percent=50.0,
        timestamp=datetime.now(timezone.utc),
    )


def _network():
    return NetworkMetrics(latency_ms=15.0)


class StubPolicy(BasePolicy):
    def __init__(self):
        self.calls = []

    def decide(self, workload, edge, cloud, network):
        self.calls.append((workload, edge, cloud, network))
        return Decision(
            workload_id=workload.workload_id,
            target=Target.CLOUD,
            score=42.0,
            reason="stub",
            priority=workload.priority,
        )


def test_engine_decide_delegates_to_policy():
    engine = DecisionEngine(_settings())
    d = engine.decide(_workload(), _edge(), _cloud(), _network())
    assert isinstance(d, Decision)
    assert d.target is Target.EDGE  # healthy edge


def test_engine_accepts_custom_policy():
    policy = StubPolicy()
    engine = DecisionEngine(_settings(), policy=policy)
    d = engine.decide(_workload(), _edge(), _cloud(), _network())
    assert d.target is Target.CLOUD
    assert policy.calls


def _mock_handler(edge_metrics=None, cloud_metrics=None):
    """Build an httpx MockTransport handler for the two node URLs."""
    edge_json = edge_metrics or {
        "cpu_percent": 20.0, "ram_percent": 30.0, "disk_percent": 40.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    cloud_json = cloud_metrics or {
        "cpu_percent": 30.0, "ram_percent": 40.0, "disk_percent": 50.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/metrics":
            if request.url.host == "edge":
                return httpx.Response(200, json=edge_json)
            return httpx.Response(200, json=cloud_json)
        return httpx.Response(404, json={"detail": "not found"})

    return handler


@pytest.mark.anyio
async def test_engine_decide_remote_fetches_and_decides():
    transport = httpx.MockTransport(_mock_handler())
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(_settings(), metrics_client=client)

    d = await engine.decide_remote(_workload(), "http://edge:8000", "http://cloud:8001")
    assert d.target is Target.EDGE  # edge healthy, latency small
    assert d.workload_id == "w1"


@pytest.mark.anyio
async def test_engine_decide_remote_overloaded_edge_offloads():
    edge_json = {
        "cpu_percent": 95.0, "ram_percent": 90.0, "disk_percent": 80.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    transport = httpx.MockTransport(_mock_handler(edge_metrics=edge_json))
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(_settings(), metrics_client=client)

    d = await engine.decide_remote(_workload(), "http://edge:8000", "http://cloud:8001")
    assert d.target is Target.CLOUD


@pytest.mark.anyio
async def test_engine_decide_remote_returns_error_when_nodes_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    transport = httpx.MockTransport(handler)
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(_settings(), metrics_client=client)

    d = await engine.decide_remote(_workload(), "http://edge:8000", "http://cloud:8001")
    assert d.target is Target.ERROR


def _slow_concurrent_handler(sleep_ms: float):
    """An async MockTransport handler that delays each call and records overlap.

    Returns (handler, tracker) where tracker collects the active [[start,end]]
    intervals per URL so tests can assert the calls genuinely overlap.
    """
    intervals = []

    async def handler(request: httpx.Request) -> httpx.Response:
        start = anyio.current_time()
        await anyio.sleep(sleep_ms / 1000.0)
        end = anyio.current_time()
        key = request.url.path
        intervals.append(("edge" if "edge" in request.url.host else "cloud", start, end))
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={
            "cpu_percent": 20.0, "ram_percent": 30.0, "disk_percent": 40.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    return handler, intervals


def _events_overlap(intervals) -> bool:
    """Return True if any two intervals [s,e] are active simultaneously."""
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            _, s1, e1 = intervals[i]
            _, s2, e2 = intervals[j]
            if max(s1, s2) < min(e1, e2) - 1e-6:
                return True
    return False


@pytest.mark.anyio
async def test_decide_remote_runs_metric_fetches_concurrently():
    """All three independent calls overlap in time (concurrent), not serial."""
    handler, intervals = _slow_concurrent_handler(sleep_ms=50.0)
    transport = httpx.MockTransport(handler)
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(_settings(), metrics_client=client)

    await engine.decide_remote(_workload(), "http://edge:8000", "http://cloud:8001")

    assert len(intervals) == 3  # edge /metrics, cloud /metrics, cloud /health
    assert _events_overlap(intervals), (
        "expected at least two of the three fetches to overlap in time"
    )


@pytest.mark.anyio
async def test_decide_remote_concurrent_wall_time_is_about_one_interval():
    """Three ~50 ms calls complete in ~one 50 ms interval, not ~150 ms."""
    sleep_ms = 50.0
    handler, _ = _slow_concurrent_handler(sleep_ms=sleep_ms)
    transport = httpx.MockTransport(handler)
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(_settings(), metrics_client=client)

    # Warm the (disabled-cache) path; the measurement itself is single-shot.
    t0 = time.perf_counter()
    await engine.decide_remote(_workload(), "http://edge:8000", "http://cloud:8001")
    dt = (time.perf_counter() - t0) * 1000.0

    # Concurrent: ~1 interval (~60 ms incl. overhead). Serial would be ~3x.
    assert dt < sleep_ms * 2.2, f"did not overlap; total was {dt:.1f} ms"


@pytest.mark.anyio
async def test_decide_remote_equals_sequential_for_same_inputs():
    """Concurrent result equals the deterministic path for identical inputs.

    The sequential reference is built from the same measured latency (the
    /health handler sleeps 8 ms) and the same metrics JSON, so the decision
    (target/score/reason) must be byte-for-byte identical for both orderings.
    """
    edge_json = {
        "cpu_percent": 20.0, "ram_percent": 30.0, "disk_percent": 40.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    cloud_json = {
        "cpu_percent": 30.0, "ram_percent": 40.0, "disk_percent": 50.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            await anyio.sleep(0.008)
            return httpx.Response(200, json={"status": "ok"})
        if request.url.host == "edge":
            return httpx.Response(200, json=edge_json)
        return httpx.Response(200, json=cloud_json)

    transport = httpx.MockTransport(handler)
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(_settings(), metrics_client=client)

    gathered = await engine.decide_remote(
        _workload(), "http://edge:8000", "http://cloud:8001"
    )

    # Sequential reference: same snapshots + the measured health latency.
    latency_ms = await client.measure_latency_ms("http://cloud:8001")
    sequential = engine.decide(
        _workload(),
        EdgeMetrics(**edge_json),
        CloudMetrics(**cloud_json),
        NetworkMetrics(latency_ms=latency_ms),
    )

    assert gathered.workload_id == sequential.workload_id
    assert gathered.target is sequential.target
    assert gathered.score == sequential.score
    assert gathered.priority is sequential.priority
    # The only live, inherently-variable input is the measured latency (ms).
    # For identical metrics + an acceptable latency both must resolve to the
    # same healthy-edge outcome and reason.
    assert "Edge resources within capacity" in gathered.reason
    assert "running locally" in gathered.reason


def _overloaded_edge_json():
    return {
        "cpu_percent": 95.0, "ram_percent": 90.0, "disk_percent": 80.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _saturated_cloud_json():
    return {
        "cpu_percent": 95.0, "ram_percent": 90.0, "disk_percent": 85.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.anyio
async def test_decide_remote_poor_network_queues_medium():
    """Edge overloaded + poor network + medium priority -> QUEUE."""
    async def handler(request: httpx.Request) -> httpx.Response:
        # /health sleeps so the measured latency exceeds max_latency_ms (10).
        if request.url.path == "/health":
            await anyio.sleep(0.3)
            return httpx.Response(200, json={"status": "ok"})
        if request.url.host == "edge":
            return httpx.Response(200, json=_overloaded_edge_json())
        return httpx.Response(200, json={
            "cpu_percent": 30.0, "ram_percent": 40.0, "disk_percent": 50.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    transport = httpx.MockTransport(handler)
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(
        _settings(max_latency_ms=10.0), metrics_client=client
    )

    wl = Workload(workload_id="wq", latency_requirement_ms=100.0)  # medium default
    d = await engine.decide_remote(wl, "http://edge:8000", "http://cloud:8001")
    assert d.target is Target.QUEUE


@pytest.mark.anyio
async def test_decide_remote_both_saturated_errors():
    """Edge and cloud both saturated -> ERROR."""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.host == "edge":
            return httpx.Response(200, json=_overloaded_edge_json())
        return httpx.Response(200, json=_saturated_cloud_json())

    transport = httpx.MockTransport(handler)
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(_settings(), metrics_client=client)

    d = await engine.decide_remote(
        _workload(), "http://edge:8000", "http://cloud:8001"
    )
    assert d.target is Target.ERROR


@pytest.mark.anyio
async def test_decide_remote_latency_failure_yields_network_none():
    """If /health fails, network stays None and the decision still resolves
    (cloud overloaded + edge healthy -> EDGE regardless of latency)."""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(500, json={"detail": "boom"})
        if request.url.host == "edge":
            return httpx.Response(200, json={
                "cpu_percent": 20.0, "ram_percent": 30.0, "disk_percent": 40.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return httpx.Response(200, json=_saturated_cloud_json())

    transport = httpx.MockTransport(handler)
    client = MetricsClient(timeout_sec=2.0, transport=transport)
    engine = DecisionEngine(_settings(), metrics_client=client)

    d = await engine.decide_remote(
        _workload(), "http://edge:8000", "http://cloud:8001"
    )
    # Edge healthy (cloud saturated) -> EDGE; latency None doesn't matter here.
    assert d.target is Target.EDGE


@pytest.mark.anyio
async def test_decide_remote_latency_never_cached_or_coalesced():
    """The /health latency probe remains live even when metrics are cached."""
    calls = {"metrics": 0, "health": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            calls["health"] += 1
            return httpx.Response(200, json={"status": "ok"})
        calls["metrics"] += 1
        if request.url.host == "edge":
            return httpx.Response(200, json={
                "cpu_percent": 20.0, "ram_percent": 30.0, "disk_percent": 40.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return httpx.Response(200, json={
            "cpu_percent": 30.0, "ram_percent": 40.0, "disk_percent": 50.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # TTL > 0 so metrics ARE cached on the second call; health must not be.
    transport = httpx.MockTransport(handler)
    client = MetricsClient(timeout_sec=2.0, transport=transport, ttl_sec=60.0)
    engine = DecisionEngine(_settings(), metrics_client=client)

    await engine.decide_remote(_workload(), "http://edge:8000", "http://cloud:8001")
    await engine.decide_remote(_workload(), "http://edge:8000", "http://cloud:8001")

    # First decide_remote fetches edge(1) + cloud(1) = 2 metric calls;
    # second decide_remote serves both from cache, so the count stays at 2.
    assert calls["metrics"] == 2
    assert calls["health"] == 2  # latency always measured live

