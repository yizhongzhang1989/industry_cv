"""Stable public API for reusable industrial vision; no robot orchestration."""

from .acquisition.rtsp import CameraConfig, RTSPCamera
from .core.frame import Frame
from .detectors.button_battery import BatteryDetector, Detection, DetectorConfig
from .geometry.planar import PlanarCalibration
from .pipelines.button_battery import ButtonBatteryPipeline
from .profiles import list_profiles, load_profile

# Preserve the original public name; the canonical name now states the pipeline's scope.
VisionPipeline = ButtonBatteryPipeline

__all__ = [
    "BatteryDetector",
    "ButtonBatteryPipeline",
    "CameraConfig",
    "Detection",
    "DetectorConfig",
    "Frame",
    "PlanarCalibration",
    "RTSPCamera",
    "VisionPipeline",
    "list_profiles",
    "load_profile",
]
