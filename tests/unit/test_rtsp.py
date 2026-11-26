import time
from urllib.parse import urlsplit

import numpy as np
import pytest

from industry_cv import CameraConfig, RTSPCamera


def test_credentials_encoded_and_repr_hidden():
    config = CameraConfig(host="camera.example.test", username="u@x", password="secret:/@")
    assert "secret" not in repr(config)
    assert urlsplit(config.url()).hostname == "camera.example.test"
    assert "secret%3A%2F%40" in config.url()


def test_reconnect_freshness_and_shutdown(monkeypatch):
    import industry_cv.acquisition.rtsp as module

    instances = []

    class Capture:
        def __init__(self, *args):
            self.reads = 0
            self.released = False
            instances.append(self)

        def isOpened(self):
            return True

        def read(self):
            time.sleep(0.01)
            self.reads += 1
            if len(instances) == 1 and self.reads > 2:
                return False, None
            return True, np.zeros((10, 10, 3), np.uint8)

        def release(self):
            self.released = True

    monkeypatch.setattr(module.cv2, "VideoCapture", Capture)
    with RTSPCamera(CameraConfig(host="camera.example.test", reconnect_delay_s=0.001)) as camera:
        first = camera.read(timeout_s=1)
        latest = first
        deadline = time.monotonic() + 1
        while latest.connection_id == first.connection_id:
            latest = camera.read(after_sequence=latest.sequence, timeout_s=0.5)
            assert time.monotonic() < deadline
        assert latest.sequence > first.sequence
        latest.image[:] = 255
        assert camera.read().image.max() == 0  # caller cannot mutate shared frame
    assert all(c.released for c in instances)
    with pytest.raises(RuntimeError, match="closed"):
        camera.read()


def test_failed_connection_has_bounded_timeout(monkeypatch):
    import industry_cv.acquisition.rtsp as module

    class Closed:
        def __init__(self, *args):
            pass

        def isOpened(self):
            return False

        def release(self):
            pass

    monkeypatch.setattr(module.cv2, "VideoCapture", Closed)
    with RTSPCamera(
        CameraConfig(
            host="camera.example.test", password="never-print-this", reconnect_delay_s=0.01
        )
    ) as camera:
        with pytest.raises(TimeoutError) as error:
            camera.read(timeout_s=0.05)
        assert "never-print-this" not in str(error.value)


def test_environment_requires_site_host_and_supports_anonymous_camera(monkeypatch):
    for key in ["HOST", "PORT", "USERNAME", "PASSWORD", "PATH"]:
        monkeypatch.delenv("INDUSTRY_CV_CAMERA_" + key, raising=False)
    with pytest.raises(ValueError, match="HOST"):
        CameraConfig.from_env()
    monkeypatch.setenv("INDUSTRY_CV_CAMERA_HOST", "camera-a.example.test")
    first = CameraConfig.from_env()
    assert first.url() == "rtsp://camera-a.example.test:554/"
    monkeypatch.setenv("INDUSTRY_CV_CAMERA_HOST", "camera-b.example.test")
    monkeypatch.setenv("INDUSTRY_CV_CAMERA_PORT", "8554")
    monkeypatch.setenv("INDUSTRY_CV_CAMERA_PATH", "/video")
    assert CameraConfig.from_env().url() == "rtsp://camera-b.example.test:8554/video"
    assert first.host == "camera-a.example.test"
