"""Tests for the metrics HTTP client."""

from datetime import datetime, timezone

import anyio
import httpx
import pytest

from scheduler.metrics_client import MetricsClient
from scheduler.models import EdgeMetrics


def _metrics_json(cpu=20.0, ram=30.0, disk=40.0):
    return {
        "cpu_percent": cpu,
        "ram_percent": ram,
        "disk_percent": disk,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _client(handler) -> MetricsClient:
    return MetricsClient(
        timeout_sec=2.0, transport=httpx.MockTransport(handler)
    )


@pytest.mark.anyio
async def test_fetch_edge_parses_metrics():
    client = _client(lambda r: httpx.Response(200, json=_metrics_json()))
    metrics = await client.fetch_edge("http://edge:8000")
    assert isinstance(metrics, EdgeMetrics)
    assert metrics.cpu_percent == 20.0
    assert metrics.disk_percent == 40.0


@pytest.mark.anyio
async def test_fetch_edge_returns_none_on_http_error():
    client = _client(lambda r: httpx.Response(500, json={}))
    assert await client.fetch_edge("http://edge:8000") is None


@pytest.mark.anyio
async def test_fetch_cloud_returns_none_on_invalid_payload():
    bad = {"cpu_percent": "not-a-number"}
    client = _client(lambda r: httpx.Response(200, json=bad))
    assert await client.fetch_cloud("http://cloud:8001") is None


@pytest.mark.anyio
async def test_measure_latency_returns_round_trip_ms():
    client = _client(lambda r: httpx.Response(200, json={"status": "ok"}))
    latency = await client.measure_latency_ms("http://cloud:8001")
    assert latency is not None
    assert latency >= 0.0


@pytest.mark.anyio
async def test_measure_latency_returns_none_on_failure():
    client = _client(lambda r: httpx.Response(503, json={}))
    assert await client.measure_latency_ms("http://cloud:8001") is None


@pytest.mark.anyio
async def test_ttl_cache_serves_repeated_metrics_fetches():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_metrics_json(cpu=20.0 + calls["n"]))

    client = MetricsClient(
        timeout_sec=2.0, transport=httpx.MockTransport(handler), ttl_sec=60.0
    )
    first = await client.fetch_edge("http://edge:8000")
    second = await client.fetch_edge("http://edge:8000")
    assert calls["n"] == 1  # second fetch served from cache
    assert first.cpu_percent == second.cpu_percent


@pytest.mark.anyio
async def test_ttl_disabled_fetches_every_time():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_metrics_json())

    client = MetricsClient(
        timeout_sec=2.0, transport=httpx.MockTransport(handler), ttl_sec=0.0
    )
    await client.fetch_edge("http://edge:8000")
    await client.fetch_edge("http://edge:8000")
    assert calls["n"] == 2  # no cache -> both hit the wire


@pytest.mark.anyio
async def test_health_latency_not_cached():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"status": "ok"})

    client = MetricsClient(
        timeout_sec=2.0, transport=httpx.MockTransport(handler), ttl_sec=60.0
    )
    await client.measure_latency_ms("http://cloud:8001")
    await client.measure_latency_ms("http://cloud:8001")
    assert calls["n"] == 2  # latency probe is always live


@pytest.mark.anyio
async def test_ttl_cache_expires_after_window():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_metrics_json())

    client = MetricsClient(
        timeout_sec=2.0, transport=httpx.MockTransport(handler), ttl_sec=0.01
    )
    first = await client.fetch_edge("http://edge:8000")
    await anyio.sleep(0.02)
    second = await client.fetch_edge("http://edge:8000")
    assert calls["n"] == 2  # cache expired -> refetched
    assert first is not None and second is not None


@pytest.mark.anyio
async def test_fetch_failure_does_not_poison_cache():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={})
        return httpx.Response(200, json=_metrics_json())

    client = MetricsClient(
        timeout_sec=2.0, transport=httpx.MockTransport(handler), ttl_sec=60.0
    )
    assert await client.fetch_edge("http://edge:8000") is None  # failure
    assert calls["n"] == 1
    # Failure must NOT have poisoned the cache: the next fetch goes to the wire.
    metrics = await client.fetch_edge("http://edge:8000")
    assert metrics is not None
    assert calls["n"] == 2


@pytest.mark.anyio
async def test_concurrent_misses_are_coalesced_single_flight():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        await anyio.sleep(0.05)  # allow concurrent callers to overlap the miss
        return httpx.Response(200, json=_metrics_json())

    client = MetricsClient(
        timeout_sec=2.0, transport=httpx.MockTransport(handler), ttl_sec=60.0
    )

    results = []

    async def fetch():
        results.append(await client.fetch_edge("http://edge:8000"))

    # 8 concurrent callers on the same cold URL must share ONE network fetch.
    async with anyio.create_task_group() as tg:
        for _ in range(8):
            tg.start_soon(fetch)
    assert all(r is not None for r in results)
    assert len(results) == 8
    assert calls["n"] == 1  # single-flight: one fetch, not 8
    # Subsequent in-TTL fetch is a cache hit (still only one network call).
    await client.fetch_edge("http://edge:8000")
    assert calls["n"] == 1


@pytest.mark.anyio
async def test_ttl_is_explicitly_bounded():
    from scheduler.metrics_client import MAX_METRICS_TTL_SEC

    client = MetricsClient(
        timeout_sec=2.0,
        ttl_sec=MAX_METRICS_TTL_SEC * 100,  # absurd config cannot exceed cap
    )
    assert client._ttl == MAX_METRICS_TTL_SEC


@pytest.mark.anyio
async def test_latency_measurement_never_coalesced():
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        await anyio.sleep(0.02)
        return httpx.Response(200, json={"status": "ok"})

    client = MetricsClient(
        timeout_sec=2.0, transport=httpx.MockTransport(handler), ttl_sec=60.0
    )

    results = []

    async def measure():
        results.append(await client.measure_latency_ms("http://cloud:8001"))

    # Concurrent latency probes must each hit the network (never coalesced).
    async with anyio.create_task_group() as tg:
        for _ in range(4):
            tg.start_soon(measure)
    assert all(r is not None for r in results)
    assert len(results) == 4
    assert calls["n"] == 4
