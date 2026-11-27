"""Tests for the Edge Node API.

These tests avoid a real YOLO model and camera by monkeypatching the app
state with fakes, so they run in CI without hardware or network access.
"""

import base64
from datetime import datetime, timezone

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from edge.ai.models import BBox, Detection, DetectionResult
from edge.api.app import create_app
from edge.config import Settings


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


@pytest.fixture()
def client():
    settings = Settings(
        _env_file=None,
        camera_source="99",  # unlikely device -> camera starts degraded
        camera_type="webcam",
        scheduler_enabled=False,
    )
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
    assert body["service"] == "edge-node"
    assert "endpoints" in body
    assert body["scheduler"]["run_locally"] is True


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_loaded"] is True
    assert body["camera_open"] is False
    assert body["camera_status"] == "not_connected"
    assert body["status"] == "ok"


def test_metrics(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("cpu_percent", "ram_percent", "disk_percent", "timestamp"):
        assert key in body
    assert 0.0 <= body["cpu_percent"] <= 100.0


def test_detect_invalid_base64(client):
    resp = client.post("/detect", json={"image_base64": "not-valid-base64!"})
    assert resp.status_code == 400


def test_detect_valid_image(client):
    resp = client.post("/detect", json={"image_base64": _jpeg_base64()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["detections"][0]["class_name"] == "person"


def test_detect_rejects_bad_type(client):
    resp = client.post(
        "/detect/video", files={"file": ("x.txt", b"hello", "text/plain")}
    )
    assert resp.status_code == 415


def test_detect_video_empty_upload(client):
    resp = client.post(
        "/detect/video", files={"file": ("x.mp4", b"", "video/mp4")}
    )
    assert resp.status_code == 400


def _make_video(n_frames: int, width: int = 64, height: int = 64) -> bytes:
    """Encode an in-memory MP4 with n_frames distinct frames."""
    import io

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    buf = io.BytesIO()
    # cv2.VideoWriter needs a filename; use a temp file to keep portability.
    import tempfile, os

    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        writer = cv2.VideoWriter(path, fourcc, 10.0, (width, height))
        for i in range(n_frames):
            frame = np.full((height, width, 3), i % 255, dtype=np.uint8)
            writer.write(frame)
        writer.release()
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(path):
            os.remove(path)


class CountingDetector(FakeDetector):
    def __init__(self):
        self.calls = 0

    def predict(self, frame, confidence=None, classes=None):
        self.calls += 1
        return super().predict(frame, confidence, classes)


@pytest.mark.parametrize("frame_step,expected", [(1, 6), (2, 3), (3, 2), (5, 2)])
def test_detect_video_frame_step(client, frame_step, expected):
    video = _make_video(6)
    counting = CountingDetector()
    client.app.state.detector = counting
    resp = client.post(
        "/detect/video?frame_step=%d" % frame_step,
        files={"file": ("x.mp4", video, "video/mp4")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_frames"] == 6
    assert body["frames_processed"] == expected
    assert counting.calls == expected
    assert body["detections"] == {"person": expected}


@pytest.mark.parametrize("bad", ["0", "-1", "-5", "abc", "1.5"])
def test_detect_video_frame_step_invalid(client, bad):
    video = _make_video(2)
    resp = client.post(
        "/detect/video?frame_step=%s" % bad,
        files={"file": ("x.mp4", video, "video/mp4")},
    )
    assert resp.status_code == 422


def test_health_degraded_when_model_not_loaded(client):
    class UnloadedDetector(FakeDetector):
        def is_loaded(self):
            return False

    client.app.state.detector = UnloadedDetector()
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_loaded"] is False
    assert body["camera_status"] == "not_connected"
    assert body["status"] == "degraded"