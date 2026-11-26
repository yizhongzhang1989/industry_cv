import pytest

from industry_cv import BatteryDetector, PlanarCalibration, VisionPipeline
from tests.helpers import frame


def pipeline(calibrate=True):
    cal = PlanarCalibration.fit(
        [[0, 0], [319, 0], [319, 219], [0, 219]],
        [[0, 0], [319, 0], [319, 219], [0, 219]],
        [320, 220],
        "base",
        10,
    )
    return VisionPipeline(BatteryDetector(), cal if calibrate else None)


def test_only_fresh_stable_calibrated_targets_are_pickable():
    p = pipeline()
    assert not p.process(frame(1))["targets"][0]["pickable"]
    p.process(frame(2))
    t = p.process(frame(3))["targets"][0]
    assert t["pickable"] and t["position"]["x_mm"] == pytest.approx(90, abs=0.1)
    with pytest.raises(ValueError, match="Duplicate"):
        p.process(frame(3))
    with pytest.raises(ValueError, match="Stale"):
        p.process(frame(4, age=2))
    assert not p.process(frame(5))["targets"][0]["stable"]


def test_uncalibrated_never_pickable():
    p = pipeline(False)
    for i in range(1, 5):
        t = p.process(frame(i))["targets"][0]
        assert not t["pickable"] and t["position"] is None
        assert "uncalibrated" in t["blocked_reasons"]


def test_disappearance_reconnect_and_motion_reset_stability():
    p = pipeline()
    for i in range(1, 4):
        result = p.process(frame(i))
    tid = result["targets"][0]["track_id"]
    assert p.process(frame(4, []))["targets"] == []
    t = p.process(frame(5))["targets"][0]
    assert t["track_id"] != tid and not t["stable"]
    p.process(frame(6))
    p.process(frame(7))
    assert not p.process(frame(8, connection=2))["targets"][0]["stable"]
    p.process(frame(9, connection=2))
    assert not p.process(frame(10, [(95, 90, 24)], connection=2))["targets"][0]["stable"]


def test_neighbor_targets_blocked_with_valid_calibration():
    p = pipeline()
    for i in range(1, 4):
        r = p.process(frame(i, [(90, 90, 24), (137, 90, 24)]))
    assert len(r["targets"]) == 2
    assert all(not t["pickable"] for t in r["targets"])
    assert all("neighbor_clearance" in t["blocked_reasons"] for t in r["targets"])


def test_estimated_pipeline_bootstraps_once_and_emits_usable_work_targets():
    p = VisionPipeline(BatteryDetector(), estimate_diameter_mm=7.9, estimated_height_mm=3.6)
    assert p.process(frame(1, []))["calibration"] is None
    first = p.process(frame(2))
    assert first["calibration"]["source"] == "estimated"
    estimate = p.calibration
    p.process(frame(3))
    final = p.process(frame(4))
    assert p.calibration is estimate
    target = final["targets"][0]
    assert target["pickable"] and target["stable"]
    assert target["position_source"] == "estimated"
    assert target["position"]["frame_id"] == "work_surface_estimated"
    assert target["position"]["z_mm"] == 3.6
    assert final["calibration"]["rmse_mm"] is None
    with pytest.raises(ValueError, match="both"):
        VisionPipeline(
            BatteryDetector(), estimate, estimate_diameter_mm=7.9, estimated_height_mm=3.6
        )
