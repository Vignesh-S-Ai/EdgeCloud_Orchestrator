"""Camera / video source abstraction.

Supports three source types, auto-detected by the Settings helper:
  * ``webcam`` - an integer device index (``cv2.VideoCapture(0)``)
  * ``rtsp``   - a network stream (reconnecting background capture thread)
  * ``file``   - a local video file (sequential reads)

Webcam and RTSP sources are read in a dedicated thread and keep only the
latest frame in a small buffer, so slow inference never blocks the capture
pipeline and stale frames are dropped instead of queued.
"""

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Raised when a video source cannot be opened or is invalid."""


class CameraCapture:
    """Threaded, reconnecting video source wrapper."""

    def __init__(
        self,
        source: str | int,
        source_type: str = "webcam",
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        buffer_size: int = 2,
        open_timeout_sec: float = 5.0,
    ) -> None:
        self._source = str(source)
        self._type = source_type
        self._width = width
        self._height = height
        self._fps = fps
        self._buffer_size = max(1, int(buffer_size))
        self._open_timeout = max(0.5, float(open_timeout_sec))

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None

        self._open()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _resolve_device(self) -> str | int:
        """Return the integer index for webcams, the URL/path otherwise."""
        if self._type == "webcam":
            try:
                return int(self._source)
            except ValueError as exc:
                raise CameraError(
                    f"Webcam source must be an integer index, got '{self._source}'"
                ) from exc
        return self._source

    def _open_device(self, device: str | int) -> cv2.VideoCapture:
        """Open the capture, aborting if it blocks longer than the timeout.

        ``cv2.VideoCapture`` can hang for a long time when the requested
        device index has no camera attached. We attempt the open in a daemon
        thread so a missing camera degrades the node instead of freezing it.
        """
        holder: dict[str, cv2.VideoCapture] = {}

        def _open() -> None:
            holder["cap"] = cv2.VideoCapture(device)

        thread = threading.Thread(target=_open, name="camera-open", daemon=True)
        thread.start()
        thread.join(self._open_timeout)
        if thread.is_alive() or "cap" not in holder:
            raise CameraError(
                f"Timed out opening video source '{self._source}' after "
                f"{self._open_timeout:.1f}s"
            )
        return holder["cap"]

    def _open(self) -> None:
        device = self._resolve_device()
        self._cap = self._open_device(device)

        if not self._cap.isOpened():
            raise CameraError(
                f"Cannot open video source '{self._source}' (type={self._type})"
            )

        if self._type != "file":
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            self._cap.set(cv2.CAP_PROP_FPS, self._fps)

        if self._type in ("webcam", "rtsp"):
            self._start_capture_thread()

        logger.info(
            "Opened %s source '%s' (%.0fx%.0f @%.0ffps)",
            self._type,
            self._source,
            self._cap.get(cv2.CAP_PROP_FRAME_WIDTH),
            self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
            self._cap.get(cv2.CAP_PROP_FPS),
        )

    def _start_capture_thread(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, name="camera-capture", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Capture loop (webcam / RTSP)
    # ------------------------------------------------------------------
    def _capture_loop(self) -> None:
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                with self._lock:
                    self._frame = frame
            else:
                if self._type == "rtsp":
                    logger.warning("Frame read failed, reconnecting to %s", self._source)
                    self._cap.release()
                    time.sleep(0.5)
                    self._cap = cv2.VideoCapture(self._source)
                else:
                    time.sleep(0.01)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def read(self) -> Optional[np.ndarray]:
        """Return the next frame (BGR) or None when the source is exhausted."""
        if self._type == "file":
            ok, frame = self._cap.read()
            return frame if ok else None
        with self._lock:
            frame = self._frame
        return frame.copy() if frame is not None else None

    def is_open(self) -> bool:
        """True when the underlying capture is available."""
        return bool(self._cap is not None and self._cap.isOpened())

    def release(self) -> None:
        """Stop the capture thread and release the underlying device."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "CameraCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.release()
