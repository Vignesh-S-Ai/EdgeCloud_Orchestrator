"""HTTP client for fetching node metrics and measuring latency.

Uses httpx (already a project dependency). The metrics JSON produced by the
Edge/Cloud Node ``/metrics`` endpoints parses directly into
:class:`EdgeMetrics` / :class:`CloudMetrics`.
"""

import logging
import time
from typing import Optional

import anyio
import httpx

from .models import CloudMetrics, EdgeMetrics

logger = logging.getLogger(__name__)

#: Hard upper bound on the metrics cache TTL (seconds). Even if a larger
#: ``SCHEDULER_METRICS_TTL_SEC`` is configured, the effective TTL is clamped to
#: this value so a misconfiguration can never produce unbounded staleness.
MAX_METRICS_TTL_SEC = 60.0


class _Inflight:
    """Shared marker for an in-flight single-flight metrics fetch.

    The first concurrent caller owns the fetch; later callers await
    :attr:`event` and read :attr:`payload` (set before the event is fired) so
    every caller shares the same network result without a request stampede.
    It is backend-agnostic (works on both asyncio and trio event loops).
    """

    def __init__(self) -> None:
        self.event = anyio.Event()
        self.payload: Optional[dict] = None


class MetricsClient:
    """Small, injected HTTP client for the Edge and Cloud Node APIs.

    A short in-memory TTL cache can be enabled (``ttl_sec > 0``) so repeated
    ``/metrics`` fetches to the same URL within the TTL window are served from
    cache instead of re-hitting the network. This cuts the dominant live-probe
    cost of live-metrics decisioning. The ``/health`` latency probe is always
    fetched live (never cached) so the network latency used by the placement
    policy stays an honest, fresh measurement.
    """

    def __init__(
        self,
        timeout_sec: float = 2.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        ttl_sec: float = 0.0,
    ) -> None:
        self._timeout = max(0.5, float(timeout_sec))
        self._transport = transport
        # TTL is explicitly bounded (never below 0, never above the cap) so a
        # misconfiguration cannot yield negative or unbounded staleness.
        self._ttl = min(MAX_METRICS_TTL_SEC, max(0.0, float(ttl_sec)))
        self._cache: dict[str, tuple[float, Optional[dict]]] = {}
        # Single-flight registry: url -> in-flight _Inflight marker. Coalesces
        # concurrent cache misses for the same URL so we do not fan out one
        # request per caller (no uncontrolled request stampede).
        self._inflight: dict[str, _Inflight] = {}

    async def _do_fetch(self, url: str) -> Optional[dict]:
        """Perform a single uncached HTTP GET for ``url`` and return its JSON.

        Never raises: transport/HTTP/parse errors are logged and translated to
        ``None`` so a failed fetch degrades to the scheduler's existing
        "metrics unavailable" path instead of surfacing as an error.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Request to %s failed: %s", url, exc)
            return None

    async def _get_json(
        self, url: str, use_cache: bool = True
    ) -> Optional[dict]:
        now = time.monotonic()
        if use_cache and self._ttl > 0:
            hit = self._cache.get(url)
            if hit is not None and now < hit[0] and hit[1] is not None:
                logger.debug("metrics cache hit: %s", url)
                return hit[1]
            # Cache miss (or expired): coalesce concurrent misses for this URL
            # into a single in-flight fetch instead of one request per caller.
            inflight = self._inflight.get(url)
            if inflight is not None:
                logger.debug("metrics cache wait (in-flight): %s", url)
                await inflight.event.wait()
                # The fetching caller set payload and fired the event before
                # removing the marker, so this value is always populated.
                return inflight.payload
            inflight = _Inflight()
            self._inflight[url] = inflight
            payload: Optional[dict] = None
            try:
                payload = await self._do_fetch(url)
            finally:
                inflight.payload = payload
                if payload is not None:
                    self._cache[url] = (time.monotonic() + self._ttl, payload)
                    logger.debug("metrics cache store: %s", url)
                else:
                    logger.debug("metrics cache failure (not stored): %s", url)
                inflight.event.set()
                # Release the marker only if it is still ours (a later caller
                # may have already re-fetched after an expiry).
                if self._inflight.get(url) is inflight:
                    self._inflight.pop(url, None)
            return payload
        # Cache disabled (ttl == 0) or non-cachable (latency /health): always
        # fetch live and never coalesce, so latency stays a real measurement.
        return await self._do_fetch(url)

    async def fetch_edge(self, base_url: str) -> Optional[EdgeMetrics]:
        data = await self._get_json(f"{base_url.rstrip('/')}/metrics")
        if not data:
            return None
        try:
            return EdgeMetrics(**data)
        except Exception as exc:
            logger.warning("Invalid edge metrics from %s: %s", base_url, exc)
            return None

    async def fetch_cloud(self, base_url: str) -> Optional[CloudMetrics]:
        data = await self._get_json(f"{base_url.rstrip('/')}/metrics")
        if not data:
            return None
        try:
            return CloudMetrics(**data)
        except Exception as exc:
            logger.warning("Invalid cloud metrics from %s: %s", base_url, exc)
            return None

    async def measure_latency_ms(self, base_url: str) -> Optional[float]:
        """Measure an HTTP round trip to the node's /health endpoint (ms)."""
        url = f"{base_url.rstrip('/')}/health"
        start = time.perf_counter()
        data = await self._get_json(url, use_cache=False)
        if data is None:
            return None
        return round((time.perf_counter() - start) * 1000.0, 2)
