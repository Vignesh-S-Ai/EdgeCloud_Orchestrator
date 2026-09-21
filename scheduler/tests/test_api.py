"""Tests for the scheduler HTTP API (POST /decision, GET /health)."""

import pytest
from fastapi.testclient import TestClient

from scheduler.api.app import create_app
from scheduler.config import SchedulerSettings
from scheduler.models import Priority, Target, Workload


@pytest.fixture()
def client():
    settings = SchedulerSettings(_env_file=None)
    with TestClient(create_app(settings)) as c:
        yield c


def _workload_json(priority: str = "medium", latency: float = 100.0):
    return {
        "workload_id": "w1",
        "priority": priority,
        "latency_requirement_ms": latency,
    }


def _metrics(prefix: str, cpu: float, ram: float, disk: float):
    return {
        "cpu_percent": cpu,
        "ram_percent": ram,
        "disk_percent": disk,
        "timestamp": "2026-08-16T10:00:00Z",
    }


def _body(priority="medium", edge_cpu=20.0, cloud_cpu=30.0, latency=15.0):
    return {
        "workload": _workload_json(priority),
        "edge_metrics": _metrics("edge", edge_cpu, 30.0, 40.0),
        "cloud_metrics": _metrics("cloud", cloud_cpu, 40.0, 50.0),
        "network_metrics": {"latency_ms": latency},
    }


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "scheduler"


def test_service_info(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "/decision" in body["endpoints"]
    assert body["policy"] == "rule_based"


def test_decision_returns_edge(client):
    resp = client.post("/decision", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["target"] == "edge"
    assert body["workload_id"] == "w1"
    assert "reason" in body and body["reason"]
    assert "score" in body


def test_decision_returns_cloud_when_edge_overloaded(client):
    resp = client.post("/decision", json=_body(edge_cpu=95.0))
    assert resp.status_code == 200
    assert resp.json()["target"] == "cloud"


def test_decision_requires_metrics(client):
    resp = client.post(
        "/decision",
        json={"workload": _workload_json()},
    )
    assert resp.status_code == 400


def test_decision_requires_both_urls(client):
    body = _body()
    body.pop("edge_metrics")
    body.pop("cloud_metrics")
    body.pop("network_metrics")
    body["edge_url"] = "http://edge:8000"
    resp = client.post("/decision", json=body)
    assert resp.status_code == 400
