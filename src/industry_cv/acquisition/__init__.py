"""Frame sources; no detector or robot dependencies."""

from .rtsp import CameraConfig, RTSPCamera

__all__ = ["CameraConfig", "RTSPCamera"]
