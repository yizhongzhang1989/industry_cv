"""Parent-repository integration example with LR41 defaults.

Prints stable pick targets and approach/contact poses in the declared work frame.
The parent robot adapter owns base-frame conversion, dispatch and pick verification.
Run: python examples/button_battery/site_integration.py --frames 120 > artifacts/target_requests.jsonl
Replace estimated geometry: add --calibration /path/to/site/plane.json
"""

import argparse
import json
import math
from pathlib import Path

from industry_cv import (
    BatteryDetector,
    CameraConfig,
    DetectorConfig,
    PlanarCalibration,
    RTSPCamera,
    VisionPipeline,
    load_profile,
)


def target_requests(result, approach_mm=20.0, quaternion_xyzw=(1.0, 0.0, 0.0, 0.0)):
    """Construct parent-facing proposals; repeated proposals are not new work orders."""
    if not math.isfinite(approach_mm) or approach_mm <= 0:
        raise ValueError("Approach offset must be positive")
    if (
        len(quaternion_xyzw) != 4
        or not all(math.isfinite(v) for v in quaternion_xyzw)
        or abs(sum(v * v for v in quaternion_xyzw) - 1) > 1e-6
    ):
        raise ValueError("TCP quaternion must be a finite unit quaternion")
    proposals = []
    for target in result["targets"]:
        if not target["pickable"]:
            continue
        position = target["position"]
        pose = {**position, "quaternion_xyzw": list(quaternion_xyzw)}
        proposals.append(
            {
                "track_id": target["track_id"],
                "frame_sequence": result["frame_sequence"],
                "received_at_unix": result["received_at_unix"],
                "position_source": target["position_source"],
                "tool_orientation_source": "default_downward",
                "approach": {**pose, "z_mm": position["z_mm"] + approach_mm},
                "contact": pose,
            }
        )
    return {
        "schema_version": "1.0",
        "message_type": "pick_target_proposals",
        "execution_mode": "preview",
        "calibration": result["calibration"],
        "frame_sequence": result["frame_sequence"],
        "proposals": proposals,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "configs/vision.json"),
    )
    parser.add_argument("--calibration")
    parser.add_argument("--part-config", help="Optional measured part JSON overriding nominal data")
    parser.add_argument(
        "--integration-config",
        default=str(Path(__file__).resolve().parent / "configs/integration.json"),
    )
    parser.add_argument("--diameter-mm", type=float)
    parser.add_argument("--height-mm", type=float)
    parser.add_argument("--frames", type=int, default=0)
    args = parser.parse_args(argv)
    if args.frames < 0:
        parser.error("--frames must be >= 0")
    detector = BatteryDetector(DetectorConfig(**json.loads(Path(args.config).read_text())))
    integration = json.loads(Path(args.integration_config).read_text())
    part = (
        json.loads(Path(args.part_config).read_text())
        if args.part_config
        else load_profile(integration["part_profile"])
    )
    diameter = args.diameter_mm if args.diameter_mm is not None else part["nominal_diameter_mm"]
    height = args.height_mm if args.height_mm is not None else part["nominal_thickness_mm"]
    calibration = PlanarCalibration.load(args.calibration) if args.calibration else None
    pipeline = VisionPipeline(
        detector,
        calibration,
        estimate_diameter_mm=None if calibration else diameter,
        estimated_height_mm=height,
    )
    with RTSPCamera(CameraConfig.from_env()) as camera:
        sequence, count = 0, 0
        while args.frames == 0 or count < args.frames:
            frame = camera.read(after_sequence=sequence)
            sequence = frame.sequence
            result = pipeline.process(frame)
            proposals = target_requests(
                result, integration["approach_offset_mm"], integration["tcp_quaternion_xyzw"]
            )
            print(json.dumps(proposals, allow_nan=False), flush=True)
            count += 1
            # Parent: reserve ONE proposal, transform to the configured robot frame,
            # revalidate freshness, execute with robot library, then reacquire and verify.
            # track_id is local to this vision session, not a persistent work-order ID.


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
