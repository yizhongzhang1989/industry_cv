"""Latest-frame RTSP reader using OpenCV's FFmpeg backend over TCP.

One worker continuously drains the stream. Timestamps are host decode receipt
(times of exposure are unavailable from this camera interface).
"""

import os
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import cv2
import numpy as np

from ..core.frame import Frame


@dataclass(frozen=True)
class CameraConfig:
    host: str
    username: str = ""
    password: str = field(default="", repr=False)
    port: int = 554
    path: str = "/"
    open_timeout_ms: int = 5000
    read_timeout_ms: int = 3000
    reconnect_delay_s: float = 0.5

    def __post_init__(self):
        if not self.host or any(c in self.host for c in "/@?#"):
            raise ValueError("Invalid camera host")
        if not 1 <= self.port <= 65535 or not self.path.startswith("/"):
            raise ValueError("Invalid RTSP port/path")
        if min(self.open_timeout_ms, self.read_timeout_ms) <= 0:
            raise ValueError("Timeouts must be positive")
        if not np.isfinite(self.reconnect_delay_s) or self.reconnect_delay_s < 0:
            raise ValueError("Invalid reconnect delay")

    @classmethod
    def from_env(cls):
        host = os.environ.get("INDUSTRY_CV_CAMERA_HOST")
        if not host:
            raise ValueError("Set INDUSTRY_CV_CAMERA_HOST for this site")
        return cls(
            host=host,
            username=os.getenv("INDUSTRY_CV_CAMERA_USERNAME", ""),
            password=os.getenv("INDUSTRY_CV_CAMERA_PASSWORD", ""),
            port=int(os.getenv("INDUSTRY_CV_CAMERA_PORT", "554")),
            path=os.getenv("INDUSTRY_CV_CAMERA_PATH", "/"),
        )

    def url(self):
        auth = (
            f"{quote(self.username, safe='')}:{quote(self.password, safe='')}@"
            if self.username or self.password
            else ""
        )
        return f"rtsp://{auth}{self.host}:{self.port}{self.path}"


class RTSPCamera:
    def __init__(self, config: CameraConfig):
        self.config = config
        self._stop = threading.Event()
        self._condition = threading.Condition()
        self._thread = None
        self._frame = None
        self._sequence = 0
        self._connection = 0
        self.last_error = None

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Camera is already started")
        # FFmpeg options are process global in OpenCV; all instances use TCP.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="industry-cv-rtsp", daemon=True)
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            cap = None
            try:
                c = self.config
                cap = cv2.VideoCapture(
                    c.url(),
                    cv2.CAP_FFMPEG,
                    [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                        c.open_timeout_ms,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                        c.read_timeout_ms,
                    ],
                )
                if not cap.isOpened():
                    raise RuntimeError(
                        "RTSP connection failed; check network, credentials and path"
                    )
                self._connection += 1
                while not self._stop.is_set():
                    ok, image = cap.read()
                    if not ok:
                        raise RuntimeError("RTSP frame read failed; reconnecting")
                    with self._condition:
                        self._sequence += 1
                        self._frame = Frame(
                            image, self._sequence, time.time(), time.monotonic(), self._connection
                        )
                        self.last_error = None
                        self._condition.notify_all()
            except (cv2.error, OSError, RuntimeError):
                # Do not echo backend exception text, which may contain credentials.
                with self._condition:
                    self.last_error = "RTSP unavailable; check camera connection and settings"
                    self._frame = None
                    self._condition.notify_all()
            finally:
                if cap is not None:
                    cap.release()
            self._stop.wait(self.config.reconnect_delay_s)

    def read(self, *, after_sequence=0, timeout_s=8.0, max_age_s=0.5):
        if not all(np.isfinite(v) and v > 0 for v in (timeout_s, max_age_s)):
            raise ValueError("Timeout and max age must be positive")
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while not self._stop.is_set():
                if self._thread is None:
                    raise RuntimeError("Camera is not started")
                f = self._frame
                if (
                    f is not None
                    and f.sequence > after_sequence
                    and time.monotonic() - f.received_monotonic <= max_age_s
                ):
                    return Frame(
                        f.image.copy(),
                        f.sequence,
                        f.received_at_unix,
                        f.received_monotonic,
                        f.connection_id,
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(self.last_error or "No fresh camera frame before deadline")
                self._condition.wait(remaining)
        raise RuntimeError("Camera is closed")

    def close(self):
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(
                (self.config.open_timeout_ms + self.config.read_timeout_ms) / 1000 + 1
            )
            if self._thread.is_alive():
                raise RuntimeError("Camera backend did not stop within configured timeouts")
            self._thread = None
        self._frame = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()
