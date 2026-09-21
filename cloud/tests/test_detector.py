"""Unit tests for the Cloud YOLODetector.

The ``ultralytics`` module is faked (``sys.modules``) so no model download,
GPU or internet is required. Tests cover loading, prediction, annotation,
JPEG encoding and the model-load error path.
"""

import sys
import types

import numpy as np
import pytest

from cloud.ai.detector import ModelLoadError, YOLODetector
from cloud.ai.models import BBox, Detection


class _Tensor:
    """Minimal stand-in for a torch tensor exposing cpu()/numpy()."""

    def __init__(self, array):
        self._array = np.asarray(array, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self._array


class _FakeBoxes:
    def __init__(self, xyxy, conf, cls):
        self.xyxy = _Tensor(xyxy)
        self.conf = _Tensor(conf)
        self.cls = _Tensor(cls)

    def __len__(self):
        return len(self.xyxy.numpy())


class _FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class _FakeYOLO:
    names = {0: "person", 1: "bicycle", 2: "car"}

    def __init__(self, path):
        self.path = path

    def predict(self, source, conf, iou, imgsz, device, classes, verbose):
        assert source is not None
        boxes = _FakeBoxes(
            xyxy=[[10.0, 20.0, 50.0, 60.0], [100.0, 110.0, 200.0, 220.0]],
            conf=[0.9, 0.7],
            cls=[0, 2],
        )
        return [_FakeResult(boxes)]


class _EmptyYOLO(_FakeYOLO):
    def predict(self, source, conf, iou, imgsz, device, classes, verbose):
        boxes = _FakeBoxes(xyxy=[], conf=[], cls=[])
        return [_FakeResult(boxes)]


class _BoomYOLO(_FakeYOLO):
    def __init__(self, path):
        raise RuntimeError("fake constructor failure")


@pytest.fixture()
def fake_ultralytics(monkeypatch):
    module = types.ModuleType("ultralytics")
    module.YOLO = _FakeYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", module)
    return module


@pytest.fixture()
def empty_ultralytics(monkeypatch):
    module = types.ModuleType("ultralytics")
    module.YOLO = _EmptyYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", module)
    return module


def test_is_loaded_false_before_load(fake_ultralytics):
    detector = YOLODetector()
    assert detector.is_loaded() is False


def test_load_sets_loaded_state(fake_ultralytics):
    detector = YOLODetector(model_path="yolov8n.pt")
    detector.load()
    assert detector.is_loaded() is True


def test_predict_returns_detections(fake_ultralytics):
    detector = YOLODetector(model_path="yolov8n.pt")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = detector.predict(frame)

    assert result.count == 2
    assert result.frame_width == 640
    assert result.frame_height == 480
    assert result.inference_ms >= 0.0
    assert result.detections[0].class_name == "person"
    assert result.detections[0].confidence == pytest.approx(0.9)
    assert result.detections[1].class_name == "car"
    assert result.detections[1].bbox.width == pytest.approx(100.0)


def test_predict_no_detections(empty_ultralytics):
    detector = YOLODetector()
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    result = detector.predict(frame)
    assert result.count == 0
    assert result.detections == []


def test_predict_none_frame_raises(fake_ultralytics):
    detector = YOLODetector()
    with pytest.raises(ValueError):
        detector.predict(None)


def test_model_load_error_when_ultralytics_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "ultralytics", None)
    detector = YOLODetector()
    with pytest.raises(ModelLoadError):
        detector.load()


def test_model_load_error_when_constructor_fails(monkeypatch):
    module = types.ModuleType("ultralytics")
    module.YOLO = _BoomYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", module)
    detector = YOLODetector()
    with pytest.raises(ModelLoadError):
        detector.load()


def test_annotate_draws_boxes(fake_ultralytics):
    detector = YOLODetector()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    detections = [
        Detection(
            bbox=BBox(x1=10, y1=10, x2=50, y2=50),
            confidence=0.9,
            class_id=0,
            class_name="person",
        )
    ]
    out = detector.annotate(frame, detections)
    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)


def test_frame_to_base64_jpeg(fake_ultralytics):
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    encoded = YOLODetector.frame_to_base64_jpeg(frame)
    assert isinstance(encoded, str)
    assert len(encoded) > 0
