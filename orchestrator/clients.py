"""HTTP clients for the Edge, Cloud and Scheduler services.

Each client talks only to the public API of the target service
(``/detect``, ``/infer``, ``/decision``, ``/health``) - never to module
internals. A ``transport`` can be injected for tests, matching the pattern used
by :class:`scheduler.metrics_client.MetricsClient`.
"""

import logging
from typing import Optional

import httpx
from pydantic import BaseModel

from scheduler.models import (
    CloudMetrics,
    EdgeMetrics,
    NetworkMetrics,
    Workload,
)

logger = logging.getLogger(__name__)


class UpstreamError(Exception):
    """An upstream service call failed.

    ``status_code`` is the HTTP status when the service answered with an error,
    or ``0`` for transport-level failures (timeout, connection refused, ...).
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class _BaseClient:
    def __init__(self, base_url: str, timeout_sec: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = max(0.5, float(timeout_sec))

    def _url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"

    async def _request_json(self, method: str, path: str, payload=None) -> dict:
        url = self._url(path)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.request(method, url, json=payload)
            except httpx.HTTPError as exc:
                raise UpstreamError(0, f"Connection error to {url}: {exc}") from exc
        if resp.status_code >= 400:
            detail = _extract_detail(resp)
            raise UpstreamError(resp.status_code, detail)
        try:
            return resp.json()
        except ValueError as exc:
            raise UpstreamError(resp.status_code, f"Non-JSON response from {url}") from exc

    async def health(self) -> dict:
        return await self._request_json("GET", "/health")


class EdgeClient(_BaseClient):
    """Client for the Edge Node public API (``/detect``, ``/health``)."""

    async def detect(
        self,
        image_base64: str,
        confidence: Optional[float] = None,
        annotated: bool = False,
        classes: Optional[list[int]] = None,
    ) -> dict:
        payload = {
            "image_base64": image_base64,
            "confidence": confidence,
            "annotated": annotated,
            "classes": classes,
        }
        return await self._request_json("POST", "/detect", payload)


class CloudClient(_BaseClient):
    """Client for the Cloud Node public API (``/infer``, ``/health``)."""

    async def infer(
        self,
        image_base64: str,
        confidence: Optional[float] = None,
        annotated: bool = False,
        classes: Optional[list[int]] = None,
    ) -> dict:
        payload = {
            "image_base64": image_base64,
            "confidence": confidence,
            "annotated": annotated,
            "classes": classes,
        }
        return await self._request_json("POST", "/infer", payload)


class SchedulerClient(_BaseClient):
    """Client for the Decision Engine public API (``/decision``)."""

    async def decide(
        self,
        workload: Workload,
        edge_url: str,
        cloud_url: str,
        edge_metrics: Optional[EdgeMetrics] = None,
        cloud_metrics: Optional[CloudMetrics] = None,
        network_metrics: Optional[NetworkMetrics] = None,
    ) -> dict:
        """Ask the scheduler for a placement decision.

        With a full metrics snapshot the decision is deterministic; otherwise
        ``edge_url``/``cloud_url`` make the scheduler fetch live metrics and
        measure latency itself.
        """
        body: dict = {"workload": workload.model_dump(mode="json")}
        if (
            edge_metrics is not None
            or cloud_metrics is not None
            or network_metrics is not None
        ):
            body["edge_metrics"] = edge_metrics.model_dump(mode="json")
            body["cloud_metrics"] = cloud_metrics.model_dump(mode="json")
            body["network_metrics"] = network_metrics.model_dump(mode="json")
        else:
            body["edge_url"] = edge_url
            body["cloud_url"] = cloud_url
        return await self._request_json("POST", "/decision", body)


def _extract_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and "detail" in data:
            return str(data["detail"])
    except ValueError:
        pass
    return f"Upstream error {resp.status_code}"
