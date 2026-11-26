import numpy as np
import pytest

from industry_cv import PlanarCalibration

PIXELS = [[20, 20], [280, 20], [280, 200], [20, 200], [150, 100], [90, 160]]
XY = [[x * 0.2 + 100, y * 0.3 - 40] for x, y in PIXELS]


def fitted(**kwargs):
    return PlanarCalibration.fit(PIXELS, XY, [320, 220], "robot_base", 12, **kwargs)


def test_projection_units_roundtrip_and_bounds(tmp_path):
    cal = fitted()
    cal.save(tmp_path / "plane.json")
    cal = PlanarCalibration.load(tmp_path / "plane.json")
    p = cal.project([100, 100], [320, 220])
    assert p["x_mm"] == pytest.approx(120, abs=1e-5)
    assert p["y_mm"] == pytest.approx(-10, abs=1e-5)
    assert p["z_mm"] == 12
    assert p["frame_id"] == "robot_base"
    with pytest.raises(ValueError, match="outside"):
        cal.project([0, 0], [320, 220])
    with pytest.raises(ValueError, match="resolution"):
        cal.project([100, 100], [640, 480])


def test_reject_bad_measurement_and_degenerate_calibration():
    wrong = np.array(XY)
    wrong[-1] += 20
    with pytest.raises(ValueError, match="residual"):
        PlanarCalibration.fit(PIXELS, wrong, [320, 220], "base", 12)
    with pytest.raises(ValueError, match="collinear"):
        PlanarCalibration.fit([[0, 0], [1, 1], [2, 2], [3, 3]], XY[:4], [320, 220], "base", 12)
    with pytest.raises(ValueError, match="Duplicate"):
        PlanarCalibration.fit(PIXELS[:3] + [PIXELS[0]], XY[:4], [320, 220], "base", 12)


def test_lens_distortion_roundtrip():
    import cv2

    k = np.array([[500.0, 0, 160], [0, 500, 110], [0, 0, 1]])
    d = np.array([0.12, -0.04, 0, 0, 0])
    ideal = np.array(PIXELS, dtype=float)
    xyz = np.c_[(ideal - [160, 110]) / 500, np.ones(len(ideal))]
    distorted, _ = cv2.projectPoints(xyz, np.zeros(3), np.zeros(3), k, d)
    cal = PlanarCalibration.fit(
        distorted.reshape(-1, 2),
        XY,
        [320, 220],
        "base",
        12,
        camera_matrix=k.tolist(),
        distortion=d.tolist(),
    )
    q, _ = cv2.projectPoints(np.array([[-0.12, -0.02, 1.0]]), np.zeros(3), np.zeros(3), k, d)
    assert cal.project(q.reshape(2), [320, 220])["x_mm"] == pytest.approx(120, abs=0.001)


def test_invalid_lens_and_singular_homography():
    with pytest.raises(ValueError):
        fitted(camera_matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    with pytest.raises(ValueError, match="singularity"):
        PlanarCalibration(
            [[1, 0, 0], [0, 1, 0], [0.01, 0, -1]], [320, 220], PIXELS[:4], "base", 12, 0, 0
        )


def test_holdout_validation_measures_unseen_points_without_refitting(tmp_path):
    cal = fitted()
    cal.save(tmp_path / "plane.json")
    cal = PlanarCalibration.load(tmp_path / "plane.json")
    original = np.asarray(cal.homography).copy()
    pixels = [[70, 60], [240, 130], [70, 180]]
    measured = [[114.3, -22.4], [148, -1], [114, 14]]
    report = cal.validate(pixels, measured, [320, 220], "robot_base", 12, max_error_mm=0.6)
    assert report["passed"]
    assert report["sample_count"] == 3
    assert report["max_error_mm"] == pytest.approx(0.5, abs=1e-5)
    assert report["rmse_mm"] == pytest.approx(0.5 / np.sqrt(3), abs=1e-5)
    np.testing.assert_array_equal(cal.homography, original)
    report = cal.validate(pixels, measured, [320, 220], "robot_base", 12, max_error_mm=0.4)
    assert not report["passed"]
    assert report["failure_reasons"] == ["error_exceeds_tolerance"]


def test_training_points_cannot_pass_as_holdout_validation():
    report = fitted().validate(PIXELS, XY, [320, 220], "robot_base", 12)
    assert not report["passed"]
    assert report["reused_point_indices"] == list(range(len(PIXELS)))
    assert "validation_reuses_fit_locations" in report["failure_reasons"]


def test_legacy_calibration_can_project_but_cannot_claim_distinct_validation():
    cal = fitted()
    cal.fit_pixels = None
    report = cal.validate([[100, 100]], [[120, -10]], [320, 220], "robot_base", 12)
    assert not report["passed"]
    assert report["failure_reasons"] == ["fit_points_unavailable"]


@pytest.mark.parametrize(
    "override, message",
    [
        ({"frame_id": "another_robot"}, "coordinate frame"),
        ({"plane_z_mm": 13}, "plane height"),
        ({"image_size": [640, 480]}, "resolution"),
        ({"pixels": [[0, 0]]}, "outside"),
        ({"max_error_mm": float("nan")}, "tolerance"),
    ],
)
def test_holdout_validation_rejects_wrong_coordinate_context(override, message):
    data = {
        "pixels": [[100, 100]],
        "xy_mm": [[120, -10]],
        "image_size": [320, 220],
        "frame_id": "robot_base",
        "plane_z_mm": 12,
    }
    data.update(override)
    with pytest.raises(ValueError, match=message):
        fitted().validate(**data)


def test_lr41_size_estimate_has_known_scale_and_explicit_unknown_accuracy(tmp_path):
    cal = PlanarCalibration.from_nominal_diameter(
        [47, 48, 49],
        [320, 220],
        [[10, 10], [310, 10], [310, 210], [10, 210]],
        diameter_mm=7.9,
        plane_z_mm=3.6,
    )
    assert cal.source == "estimated"
    assert cal.rmse_mm is None and cal.max_error_mm is None
    assert cal.estimation["mm_per_pixel"] == pytest.approx(7.9 / 48)
    p = cal.project([208, 62], [320, 220])
    assert p["x_mm"] == pytest.approx(7.9)
    assert p["y_mm"] == pytest.approx(7.9)
    assert p["z_mm"] == 3.6
    assert p["frame_id"] == "work_surface_estimated"
    cal.save(tmp_path / "estimate.json")
    loaded = PlanarCalibration.load(tmp_path / "estimate.json")
    assert loaded.summary() == cal.summary()
    report = loaded.validate([[208, 62]], [[7.9, 7.9]], [320, 220], p["frame_id"], 3.6)
    assert not report["passed"]
    assert "estimated_calibration" in report["failure_reasons"]


@pytest.mark.parametrize("diameters", [[], [0], [-1], [float("nan")], [[48]]])
def test_size_estimation_rejects_invalid_observations(diameters):
    with pytest.raises(ValueError):
        PlanarCalibration.from_nominal_diameter(
            diameters, [320, 220], [[0, 0], [319, 0], [319, 219], [0, 219]], diameter_mm=7.9
        )
