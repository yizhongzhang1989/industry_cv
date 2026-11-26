"""JSON / JSONL interface for Python, ROS adapters and other languages."""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from ..acquisition.rtsp import CameraConfig, RTSPCamera
from ..detectors.button_battery import BatteryDetector, DetectorConfig
from ..geometry.planar import PlanarCalibration
from ..pipelines.button_battery import ButtonBatteryPipeline
from ..profiles import list_profiles, load_profile
from ..visualization import annotate


def _write_json(value, path=None):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text + "\n")
    else:
        print(text, flush=True)


def _save_image(path, image):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise ValueError(f"Cannot write image: {path}")


def _estimate(detector, image, detections, diameter_mm, height_mm):
    h, w = image.shape[:2]
    roi = detector.config.roi or [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]
    return PlanarCalibration.from_nominal_diameter(
        [2 * d.radius_px for d in detections],
        [w, h],
        roi,
        diameter_mm=diameter_mm,
        plane_z_mm=height_mm,
    )


def _dimensions(part_profile, diameter, height):
    part = load_profile(part_profile) if part_profile else {}
    if part_profile and "nominal_diameter_mm" not in part:
        raise ValueError("--part-profile must select a part specification")
    return (
        diameter if diameter is not None else part.get("nominal_diameter_mm"),
        height if height is not None else part.get("nominal_thickness_mm", 0.0),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reusable industrial vision tools")
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot", help="Save a fresh RTSP frame; credentials from environment")
    snap.add_argument("--output", required=True)
    detect = sub.add_parser("detect", help="Detect cells in an image")
    detect.add_argument("image")
    detect.add_argument("--config")
    detect.add_argument("--profile", default="button_battery/default")
    detect.add_argument("--part-profile")
    detect.add_argument("--output")
    detect.add_argument("--annotated")
    detect.add_argument("--calibration")
    detect.add_argument("--estimate-diameter-mm", type=float)
    detect.add_argument("--estimated-height-mm", type=float)
    stream = sub.add_parser("stream", help="Fresh tracked detections as JSONL on stdout")
    stream.add_argument("--config")
    stream.add_argument("--profile", default="button_battery/default")
    stream.add_argument("--part-profile")
    stream.add_argument("--calibration")
    stream.add_argument("--estimate-diameter-mm", type=float)
    stream.add_argument("--estimated-height-mm", type=float)
    stream.add_argument("--frames", type=int, default=0, help="0 runs until interrupted")
    stream.add_argument("--save-dir", help="Save raw frames, overlays and JSONL for evaluation")
    cal = sub.add_parser("calibrate", help="Fit planar image->robot XY mapping in millimeters")
    cal.add_argument("points", help="JSON with pixels, xy_mm, image_size, frame_id, plane_z_mm")
    cal.add_argument("--output", required=True)
    validation = sub.add_parser("validate-calibration", help="Measure independent point errors")
    validation.add_argument("points", help="JSON with measured holdout point correspondences")
    validation.add_argument("--calibration", required=True)
    validation.add_argument("--output", help="Save report JSON; exit 3 if validation fails")
    estimate = sub.add_parser(
        "estimate-calibration", help="Estimate work-plane scale from part size"
    )
    estimate.add_argument("image")
    estimate.add_argument("--config")
    estimate.add_argument("--profile", default="button_battery/default")
    estimate.add_argument("--part-profile")
    estimate.add_argument("--diameter-mm", type=float)
    estimate.add_argument("--height-mm", type=float, help="Surface above work plane")
    estimate.add_argument("--output", required=True)
    profiles = sub.add_parser("profiles", help="List or export packaged reusable presets")
    profiles.add_argument("name", nargs="?")
    profiles.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "profiles":
            _write_json(
                load_profile(args.name) if args.name else {"profiles": list_profiles()}, args.output
            )
            return 0
        if args.command == "validate-calibration":
            calibration = PlanarCalibration.load(args.calibration)
            report = calibration.validate(**json.loads(Path(args.points).read_text()))
            _write_json(report, args.output)
            return 0 if report["passed"] else 3
        if args.command == "calibrate":
            data = json.loads(Path(args.points).read_text())
            calibration = PlanarCalibration.fit(**data)
            calibration.save(args.output)
            _write_json(
                {
                    "rmse_mm": calibration.rmse_mm,
                    "max_error_mm": calibration.max_error_mm,
                    "note": "Fit residual only; validate independent measured points",
                }
            )
            return 0
        if args.command == "snapshot":
            with RTSPCamera(CameraConfig.from_env()) as camera:
                frame = camera.read()
                _save_image(args.output, frame.image)
                _write_json(
                    {
                        "image_size": list(frame.image.shape[1::-1]),
                        "received_at_unix": frame.received_at_unix,
                        "output": args.output,
                    }
                )
            return 0
        detector_settings = load_profile(args.profile)
        if args.config:
            detector_settings.update(json.loads(Path(args.config).read_text()))
        detector = BatteryDetector(DetectorConfig(**detector_settings))
        if args.command == "estimate-calibration":
            diameter, height = _dimensions(args.part_profile, args.diameter_mm, args.height_mm)
            if diameter is None:
                raise ValueError("Provide --diameter-mm or --part-profile for size estimation")
            image = cv2.imread(args.image)
            if image is None:
                raise ValueError("Cannot read input image")
            calibration = _estimate(detector, image, detector.detect(image), diameter, height)
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            calibration.save(args.output)
            _write_json(calibration.summary())
            return 0
        args.estimate_diameter_mm, args.estimated_height_mm = _dimensions(
            args.part_profile, args.estimate_diameter_mm, args.estimated_height_mm
        )
        if args.calibration and args.estimate_diameter_mm is not None:
            raise ValueError("Provide --calibration or --estimate-diameter-mm, not both")
        if args.estimate_diameter_mm is not None and (
            not np.isfinite(args.estimate_diameter_mm)
            or args.estimate_diameter_mm <= 0
            or not np.isfinite(args.estimated_height_mm)
        ):
            raise ValueError("Estimated diameter must be positive and height finite")
        calibration = PlanarCalibration.load(args.calibration) if args.calibration else None
        if args.command == "detect":
            image = cv2.imread(args.image)
            if image is None:
                raise ValueError("Cannot read input image")
            detections = detector.detect(image)
            if args.estimate_diameter_mm is not None and detections:
                calibration = _estimate(
                    detector, image, detections, args.estimate_diameter_mm, args.estimated_height_mm
                )
            targets = [d.to_dict() for d in detections]
            for target in targets:
                target.update(position=None, pickable=False)
                target["blocked_reasons"].append("single_frame")
                if calibration:
                    try:
                        target["position"] = calibration.project(
                            target["center_px"], image.shape[1::-1]
                        )
                    except ValueError:
                        target["blocked_reasons"].append("outside_calibration")
                else:
                    target["blocked_reasons"].append("uncalibrated")
                target["position_source"] = calibration.source if target["position"] else None
            result = {
                "schema_version": "1.1",
                "image_size": list(image.shape[1::-1]),
                "targets": targets,
                "diagnostics": detector.last_diagnostics,
                "calibration": calibration.summary() if calibration else None,
            }
            _write_json(result, args.output)
            if args.annotated:
                _save_image(args.annotated, annotate(image, targets, detector.config.roi))
            return 0
        if args.frames < 0:
            raise ValueError("--frames must be >= 0")
        pipeline = ButtonBatteryPipeline(
            detector,
            calibration,
            estimate_diameter_mm=args.estimate_diameter_mm,
            estimated_height_mm=args.estimated_height_mm,
        )
        folder = Path(args.save_dir) if args.save_dir else None
        if folder:
            folder.mkdir(parents=True, exist_ok=True)
        with RTSPCamera(CameraConfig.from_env()) as camera:
            sequence, count = 0, 0
            while args.frames == 0 or count < args.frames:
                frame = camera.read(after_sequence=sequence)
                sequence = frame.sequence
                result = pipeline.process(frame)
                _write_json(result)
                if folder:
                    stem = f"{count:06d}"
                    _save_image(folder / f"{stem}.jpg", frame.image)
                    _save_image(
                        folder / f"{stem}.overlay.jpg",
                        annotate(frame.image, result["targets"], detector.config.roi),
                    )
                    _write_json(result, folder / f"{stem}.json")
                count += 1
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, TypeError, OSError, RuntimeError, cv2.error) as exc:
        # All our camera exceptions are credential-free; configuration errors are actionable.
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
