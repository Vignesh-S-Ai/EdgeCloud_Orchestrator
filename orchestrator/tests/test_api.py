"""Tests for the Orchestrator API and orchestration flow.

The three upstream clients are replaced with fakes so the tests exercise the
orchestration logic (scheduling, routing, fallback, latency breakdown) without
running Edge/Cloud/Scheduler servers.
"""

import base64
from typing import Optional

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from orchestrator.api.app import create_app
from orchestrator.clients import UpstreamError
from orchestrator.config import OrchestratorSettings
from orchestrator.service import OrchestrationService

EDGE_DECISION = {
    "workload_id": "w1",
    "target": "edge",
    "score": 80.0,
    "reason": "Edge node healthy; keeping workload local",
    "priority": "high",
    "timestamp": "2026-08-16T10:00:00Z",
}

CLOUD_DECISION = {
    "workload_id": "w1",
    "target": "cloud",
    "score": 20.0,
    "reason": "Edge node overloaded; offloading to cloud",
    "priority": "high",
    "timestamp": "2026-08-16T10:00:00Z",
}

DETECTION_RESULT = {
    "source": "fake",
    "timestamp": "2026-08-16T10:00:00Z",
    "frame_width": 640,
    "frame_height": 480,
    "inference_ms": 1.5,
    "detections": [
        {
            "bbox": {"x1": 10.0, "y1": 20.0, "x2": 50.0, "y2": 60.0},
            "confidence": 0.9,
            "class_id": 0,
            "class_name": "person",
        }
    ],
    "annotated_image_base64": None,
    "count": 1,
}


class FakeSchedulerClient:
    def __init__(self, decision=None, error=None):
        self.decision = decision or EDGE_DECISION
        self.error = error
        self.calls = []

    async def decide(
        self,
        workload,
        edge_url,
        cloud_url,
        edge_metrics=None,
        cloud_metrics=None,
        network_metrics=None,
    ):
        if self.error:
            raise self.error
        self.calls.append(
            {
                "workload": workload,
                "edge_url": edge_url,
                "cloud_url": cloud_url,
                "edge_metrics": edge_metrics,
                "cloud_metrics": cloud_metrics,
                "network_metrics": network_metrics,
            }
        )
        return self.decision


class FakeEdgeClient:
    def __init__(self, result=None, error=None, health_error=None):
        self.result = result or dict(DETECTION_RESULT)
        self.error = error
        self.health_error = health_error
        self.detect_calls = []
        self.health_calls = []

    async def detect(
        self, image_base64, confidence=None, annotated=False, classes=None
    ):
        self.detect_calls.append(
            {
                "image_base64": image_base64,
                "confidence": confidence,
                "annotated": annotated,
                "classes": classes,
            }
        )
        if self.error:
            raise self.error
        return self.result

    async def health(self):
        self.health_calls.append(1)
        if self.health_error:
            raise self.health_error
        return {"status": "ok", "service": "edge-node"}


class FakeCloudClient:
    def __init__(self, result=None, error=None, health_error=None):
        self.result = result or dict(DETECTION_RESULT)
        self.error = error
        self.health_error = health_error
        self.infer_calls = []
        self.health_calls = []

    async def health(self):
        self.health_calls.append(1)
        if self.health_error:
            raise self.health_error
        return {"status": "ok", "service": "cloud-node"}

    async def infer(
        self, image_base64, confidence=None, annotated=False, classes=None
    ):
        self.infer_calls.append(
            {
                "image_base64": image_base64,
                "confidence": confidence,
                "annotated": annotated,
                "classes": classes,
            }
        )
        if self.error:
            raise self.error
        return self.result


@pytest.fixture()
def client():
    settings = OrchestratorSettings(_env_file=None)
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _install(client, scheduler=None, edge=None, cloud=None):
    settings = OrchestratorSettings(_env_file=None)
    client.app.state.service = OrchestrationService(
        settings,
        edge_client=edge or FakeEdgeClient(),
        cloud_client=cloud or FakeCloudClient(),
        scheduler_client=scheduler or FakeSchedulerClient(),
    )
    return client.app.state.service


def _jpeg_base64() -> str:
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _metrics(prefix: str, cpu: float):
    return {
        "cpu_percent": cpu,
        "ram_percent": 40.0,
        "disk_percent": 50.0,
        "timestamp": "2026-08-16T10:00:00Z",
    }


def _body(priority="high", include_metrics=False, image: Optional[str] = None):
    payload = {
        "workload": {
            "workload_id": "w1",
            "priority": priority,
            "workload_type": "object_detection",
            "latency_requirement_ms": 100.0,
        },
        "image_base64": image or _jpeg_base64(),
    }
    if include_metrics:
        payload["edge_metrics"] = _metrics("edge", 20.0)
        payload["cloud_metrics"] = _metrics("cloud", 30.0)
        payload["network_metrics"] = {"latency_ms": 10.0}
    return payload


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "orchestrator"


def test_service_info(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "/orchestrate" in body["endpoints"]
    assert body["edge_url"] == "http://localhost:8000"
    assert body["scheduler_url"] == "http://localhost:8002"


def test_unified_response_format(client):
    edge = FakeEdgeClient()
    _install(client, edge=edge)
    resp = client.post("/orchestrate", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "workload_id",
        "priority",
        "selected_target",
        "actual_target",
        "decision_score",
        "decision_reason",
        "fallback_used",
        "fallback_reason",
        "inference_result",
        "scheduler_latency_ms",
        "inference_latency_ms",
        "total_latency_ms",
        "timestamp",
    }
    assert body["workload_id"] == "w1"
    assert body["actual_target"] == "edge"
    assert body["fallback_used"] is False
    assert body["scheduler_latency_ms"] >= 0.0
    assert body["inference_latency_ms"] >= 0.0
    assert body["total_latency_ms"] >= body["scheduler_latency_ms"]


def test_orchestrate_routes_to_edge(client):
    scheduler = FakeSchedulerClient(decision=EDGE_DECISION)
    edge = FakeEdgeClient()
    _install(client, scheduler=scheduler, edge=edge)
    resp = client.post("/orchestrate", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["selected_target"] == "edge"
    assert body["actual_target"] == "edge"
    assert body["decision_reason"] == EDGE_DECISION["reason"]
    assert body["inference_result"]["detections"][0]["class_name"] == "person"
    assert len(edge.detect_calls) == 1
    assert len(edge.detect_calls[0]["image_base64"]) >= 16


def test_orchestrate_routes_to_cloud(client):
    scheduler = FakeSchedulerClient(decision=CLOUD_DECISION)
    cloud = FakeCloudClient()
    _install(client, scheduler=scheduler, cloud=cloud)
    resp = client.post("/orchestrate", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["selected_target"] == "cloud"
    assert body["actual_target"] == "cloud"
    assert body["fallback_used"] is False
    assert len(cloud.infer_calls) == 1


def test_cloud_failure_falls_back_to_edge(client):
    scheduler = FakeSchedulerClient(decision=CLOUD_DECISION)
    cloud = FakeCloudClient(error=UpstreamError(503, "cloud unavailable"))
    edge = FakeEdgeClient()
    _install(client, scheduler=scheduler, cloud=cloud, edge=edge)
    resp = client.post("/orchestrate", json=_body(priority="high"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["selected_target"] == "cloud"
    assert body["actual_target"] == "edge"
    assert body["fallback_used"] is True
    assert "fallback to edge" in body["fallback_reason"]
    assert len(cloud.infer_calls) == 1
    assert len(edge.detect_calls) == 1
    assert body["inference_result"]["detections"][0]["class_name"] == "person"


def test_cloud_failure_no_fallback_for_low_priority(client):
    scheduler = FakeSchedulerClient(decision=CLOUD_DECISION)
    cloud = FakeCloudClient(error=UpstreamError(503, "cloud unavailable"))
    edge = FakeEdgeClient()
    _install(client, scheduler=scheduler, cloud=cloud, edge=edge)
    resp = client.post("/orchestrate", json=_body(priority="low"))
    assert resp.status_code == 503
    assert len(edge.detect_calls) == 0


def test_cloud_failure_no_fallback_when_edge_down(client):
    scheduler = FakeSchedulerClient(decision=CLOUD_DECISION)
    cloud = FakeCloudClient(error=UpstreamError(503, "cloud unavailable"))
    edge = FakeEdgeClient(health_error=UpstreamError(0, "edge unreachable"))
    _install(client, scheduler=scheduler, cloud=cloud, edge=edge)
    resp = client.post("/orchestrate", json=_body(priority="high"))
    assert resp.status_code == 503
    assert len(edge.detect_calls) == 0


def test_edge_failure_returns_503_for_medium_priority(client):
    edge = FakeEdgeClient(error=UpstreamError(503, "edge overloaded"))
    cloud = FakeCloudClient()
    _install(client, edge=edge, cloud=cloud)
    resp = client.post("/orchestrate", json=_body(priority="medium"))
    assert resp.status_code == 503
    assert len(cloud.infer_calls) == 0


def test_invalid_image_returns_400(client):
    edge = FakeEdgeClient(
        error=UpstreamError(400, "Base64 payload is not a decodable image")
    )
    _install(client, edge=edge)
    resp = client.post("/orchestrate", json=_body())
    assert resp.status_code == 400
    assert "decodable" in resp.json()["detail"]


def test_invalid_workload_returns_422(client):
    body = _body()
    body["workload"].pop("latency_requirement_ms")
    resp = client.post("/orchestrate", json=body)
    assert resp.status_code == 422


def test_partial_metrics_snapshot_rejected(client):
    body = _body()
    body["edge_metrics"] = _metrics("edge", 20.0)
    resp = client.post("/orchestrate", json=body)
    assert resp.status_code == 422


def test_scheduler_unavailable_returns_503(client):
    scheduler = FakeSchedulerClient(error=UpstreamError(0, "connection refused"))
    _install(client, scheduler=scheduler)
    resp = client.post("/orchestrate", json=_body())
    assert resp.status_code == 503
    assert "Scheduler unavailable" in resp.json()["detail"]


def test_metrics_snapshot_passed_to_scheduler(client):
    scheduler = FakeSchedulerClient(decision=EDGE_DECISION)
    _install(client, scheduler=scheduler, edge=FakeEdgeClient())
    resp = client.post("/orchestrate", json=_body(include_metrics=True))
    assert resp.status_code == 200
    call = scheduler.calls[0]
    assert call["edge_metrics"].cpu_percent == 20.0
    assert call["cloud_metrics"] is not None
    assert call["network_metrics"].latency_ms == 10.0
    assert call["edge_url"] is not None  # still configured for fallback use


def test_live_urls_passed_when_no_metrics(client):
    scheduler = FakeSchedulerClient()
    _install(client, scheduler=scheduler)
    resp = client.post("/orchestrate", json=_body())
    assert resp.status_code == 200
    call = scheduler.calls[0]
    assert call["edge_metrics"] is None
    assert call["cloud_metrics"] is None
    assert call["network_metrics"] is None
    assert call["edge_url"] == "http://localhost:8000"
    assert call["cloud_url"] == "http://localhost:8001"

def test_edge_failure_falls_back_to_cloud_for_high_priority(client):
    scheduler = FakeSchedulerClient(decision=EDGE_DECISION)
    edge = FakeEdgeClient(error=UpstreamError(503, "edge overloaded"))
    cloud = FakeCloudClient()
    _install(client, scheduler=scheduler, edge=edge, cloud=cloud)

    resp = client.post("/orchestrate", json=_body(priority="high"))

    assert resp.status_code == 200
    body = resp.json()
    assert body["selected_target"] == "edge"
    assert body["actual_target"] == "cloud"
    assert body["fallback_used"] is True
    assert "fallback to cloud" in body["fallback_reason"]
    assert len(edge.detect_calls) == 1
    assert len(cloud.health_calls) == 1
    assert len(cloud.infer_calls) == 1


def test_edge_failure_does_not_fall_back_for_medium_priority(client):
    scheduler = FakeSchedulerClient(decision=EDGE_DECISION)
    edge = FakeEdgeClient(error=UpstreamError(503, "edge overloaded"))
    cloud = FakeCloudClient()
    _install(client, scheduler=scheduler, edge=edge, cloud=cloud)

    resp = client.post("/orchestrate", json=_body(priority="medium"))

    assert resp.status_code == 503
    assert len(cloud.health_calls) == 0
    assert len(cloud.infer_calls) == 0


def test_edge_failure_does_not_fall_back_when_cloud_is_unhealthy(client):
    scheduler = FakeSchedulerClient(decision=EDGE_DECISION)
    edge = FakeEdgeClient(error=UpstreamError(503, "edge overloaded"))
    cloud = FakeCloudClient(
        health_error=UpstreamError(0, "cloud health check failed")
    )
    _install(client, scheduler=scheduler, edge=edge, cloud=cloud)

    resp = client.post("/orchestrate", json=_body(priority="high"))

    assert resp.status_code == 503
    assert len(cloud.health_calls) == 1
    assert len(cloud.infer_calls) == 0


def test_edge_client_error_does_not_trigger_cloud_fallback(client):
    scheduler = FakeSchedulerClient(decision=EDGE_DECISION)
    edge = FakeEdgeClient(
        error=UpstreamError(400, "invalid image payload")
    )
    cloud = FakeCloudClient()
    _install(client, scheduler=scheduler, edge=edge, cloud=cloud)

    resp = client.post("/orchestrate", json=_body(priority="high"))

    assert resp.status_code == 400
    assert len(cloud.health_calls) == 0
    assert len(cloud.infer_calls) == 0


def test_edge_to_cloud_fallback_failure_returns_503(client):
    scheduler = FakeSchedulerClient(decision=EDGE_DECISION)
    edge = FakeEdgeClient(error=UpstreamError(503, "edge overloaded"))
    cloud = FakeCloudClient(error=UpstreamError(503, "cloud inference failed"))
    _install(client, scheduler=scheduler, edge=edge, cloud=cloud)

    resp = client.post("/orchestrate", json=_body(priority="high"))

    assert resp.status_code == 503
    assert "fallback to cloud failed" in resp.json()["detail"]
