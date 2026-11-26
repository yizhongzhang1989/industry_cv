"""Track static pick targets and expose eligibility without issuing robot commands."""

import math
import time

import numpy as np

from ..core.frame import Frame
from ..detectors.button_battery import BatteryDetector
from ..geometry.planar import PlanarCalibration


class ButtonBatteryPipeline:
    def __init__(
        self,
        detector: BatteryDetector,
        calibration: PlanarCalibration | None = None,
        stable_frames=3,
        max_jitter_px=1.0,
        match_distance_px=10.0,
        max_age_s=0.5,
        max_gap_s=1.0,
        estimate_diameter_mm=None,
        estimated_height_mm=0.0,
    ):
        if not isinstance(stable_frames, int) or stable_frames < 2:
            raise ValueError("stable_frames must be an integer >= 2")
        if not all(
            math.isfinite(v) and v > 0
            for v in (max_jitter_px, match_distance_px, max_age_s, max_gap_s)
        ):
            raise ValueError("Tracking limits must be positive and finite")
        self.detector, self.calibration = detector, calibration
        if estimate_diameter_mm is not None:
            if calibration is not None:
                raise ValueError("Provide calibration or size estimation, not both")
            if not math.isfinite(estimate_diameter_mm) or estimate_diameter_mm <= 0:
                raise ValueError("Estimated part diameter must be positive")
        if not math.isfinite(estimated_height_mm):
            raise ValueError("Estimated height must be finite")
        self.estimate_diameter_mm, self.estimated_height_mm = (
            estimate_diameter_mm,
            estimated_height_mm,
        )
        self.stable_frames, self.max_jitter_px = stable_frames, max_jitter_px
        self.match_distance_px = match_distance_px
        self.max_age_s, self.max_gap_s = max_age_s, max_gap_s
        self._tracks = {}
        self._next_id = 1
        self._last_sequence = 0
        self._last_time = None
        self._connection = None

    def process(self, frame: Frame):
        now = time.monotonic()
        if not math.isfinite(frame.received_monotonic) or not math.isfinite(frame.received_at_unix):
            raise ValueError("Invalid frame timestamp")
        if frame.sequence <= self._last_sequence:
            raise ValueError("Duplicate or out-of-order frame")
        if now - frame.received_monotonic > self.max_age_s or frame.received_monotonic > now:
            self._tracks.clear()
            raise ValueError("Stale or future frame")
        if (
            self._last_time is not None
            and (
                frame.received_monotonic <= self._last_time
                or frame.received_monotonic - self._last_time > self.max_gap_s
            )
        ) or (frame.connection_id != self._connection):
            self._tracks.clear()
        self._last_sequence, self._last_time = frame.sequence, frame.received_monotonic
        self._connection = frame.connection_id
        detections = self.detector.detect(frame.image)
        # Estimate once from the first nonempty frame, then freeze the coordinate frame.
        # Refitting every frame would move otherwise stationary target coordinates.
        if self.calibration is None and self.estimate_diameter_mm is not None and detections:
            h, w = frame.image.shape[:2]
            polygon = self.detector.config.roi or [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
            self.calibration = PlanarCalibration.from_nominal_diameter(
                [2 * d.radius_px for d in detections],
                [w, h],
                polygon,
                diameter_mm=self.estimate_diameter_mm,
                plane_z_mm=self.estimated_height_mm,
            )
        pairs = sorted(
            (math.dist(d.center_px, history[-1]), tid, i)
            for tid, history in self._tracks.items()
            for i, d in enumerate(detections)
        )
        assigned, used = {}, set()
        for distance, tid, i in pairs:
            if distance <= self.match_distance_px and tid not in used and i not in assigned:
                assigned[i] = tid
                used.add(tid)
        current = {}
        targets = []
        for i, detection in enumerate(detections):
            tid = assigned.get(i)
            if tid is None:
                tid, self._next_id = self._next_id, self._next_id + 1
            history = (self._tracks.get(tid, []) + [detection.center_px])[-self.stable_frames :]
            current[tid] = history
            jitter = float(
                np.max(np.linalg.norm(np.asarray(history) - np.mean(history, axis=0), axis=1))
            )
            stable = len(history) >= self.stable_frames and jitter <= self.max_jitter_px
            reasons = list(detection.blocked_reasons)
            if not stable:
                reasons.append("unstable")
            position = None
            if self.calibration is None:
                reasons.append("uncalibrated")
            else:
                try:
                    position = self.calibration.project(
                        detection.center_px, frame.image.shape[1::-1]
                    )
                except ValueError:
                    reasons.append("outside_calibration")
            target = detection.to_dict()
            target.update(
                track_id=tid,
                stable=stable,
                jitter_px=jitter,
                position=position,
                blocked_reasons=reasons,
                pickable=not reasons,
                position_source=self.calibration.source if position is not None else None,
            )
            targets.append(target)
        self._tracks = current  # disappearance resets consecutive-frame evidence
        age = time.monotonic() - frame.received_monotonic
        if age > self.max_age_s:
            for t in targets:
                t["pickable"] = False
                t["blocked_reasons"].append("stale")
        return {
            "schema_version": "1.1",
            "frame_sequence": frame.sequence,
            "connection_id": frame.connection_id,
            "received_at_unix": frame.received_at_unix,
            "timestamp_source": "host_decode_receipt",
            "frame_age_s": age,
            "image_size": list(frame.image.shape[1::-1]),
            "targets": targets,
            "diagnostics": dict(self.detector.last_diagnostics),
            "calibration": self.calibration.summary() if self.calibration else None,
        }
