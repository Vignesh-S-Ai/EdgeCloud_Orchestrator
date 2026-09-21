"""Tests for the Cloud Node API.

These tests avoid a real YOLO model by monkeypatching the app state with a
fake detector, so they run in CI without GPU or network access.
"""

import base64
from datetime import datetime, timezone

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from cloud.ai.models import BBox, Detection, DetectionResult
from cloud.api.app import create_app
from cloud.ai.detector import ModelLoadError
from cloud.config import Settings


class FakeDetector:
    def is_loaded(self):
        return True

    def predict(self, frame, confidence=None, classes=None):
        return DetectionResult(
            source="fake",
            timestamp=datetime.now(timezone.utc),
            frame_width=640,
            frame_height=480,
            inference_ms=1.5,
            detections=[
                Detection(
                    bbox=BBox(x1=10.0, y1=20.0, x2=50.0, y2=60.0),
                    confidence=0.9,
                    class_id=0,
                    class_name="person",
                )
            ],
        )

    def annotate(self, frame, detections):
        return frame

    @staticmethod
    def frame_to_base64_jpeg(frame, quality=80):
        return "fake-annotation"


class FailingDetector(FakeDetector):
    def predict(self, frame, confidence=None, classes=None):
        raise ModelLoadError("model unavailable")


@pytest.fixture()
def client():
    settings = Settings(_env_file=None)
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.app.state.detector = FakeDetector()
        yield test_client


def _jpeg_base64() -> str:
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")


def test_service_info(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "cloud-node"
    assert "endpoints" in body
    assert "/infer" in body["endpoints"]


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_loaded"] is True
    assert body["status"] == "ok"


def test_metrics(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("cpu_percent", "ram_percent", "disk_percent", "timestamp"):
        assert key in body
    assert 0.0 <= body["cpu_percent"] <= 100.0


def test_infer_rejects_missing_field(client):
    resp = client.post("/infer", json={})
    assert resp.status_code == 422


def test_infer_invalid_base64(client):
    resp = client.post("/infer", json={"image_base64": "not-valid-base64!"})
    assert resp.status_code == 400


def test_infer_not_an_image(client):
    payload = base64.b64encode(b"hello world").decode("ascii")
    resp = client.post("/infer", json={"image_base64": payload})
    assert resp.status_code == 400


def test_infer_valid_image(client):
    resp = client.post("/infer", json={"image_base64": _jpeg_base64()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["detections"][0]["class_name"] == "person"
    assert body["detections"][0]["confidence"] == 0.9
    assert "bbox" in body["detections"][0]
    assert body["inference_ms"] >= 0.0


def test_infer_returns_annotated_image(client):
    resp = client.post(
        "/infer", json={"image_base64": _jpeg_base64(), "annotated": True}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["annotated_image_base64"] == "fake-annotation"


def test_infer_payload_too_large():
    settings = Settings(_env_file=None, max_infer_bytes=50)
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.app.state.detector = FakeDetector()
        resp = test_client.post("/infer", json={"image_base64": "A" * 80})
    assert resp.status_code == 413


def test_infer_model_load_error():
    settings = Settings(_env_file=None)
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.app.state.detector = FailingDetector()
        resp = test_client.post("/infer", json={"image_base64": _jpeg_base64()})
    assert resp.status_code == 503
