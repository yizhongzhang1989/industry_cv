import json

import pytest

from industry_cv.cli import main
from tests.helpers import ROOT


def test_image_cli_json_and_overlay(tmp_path):
    result, overlay = tmp_path / "result.json", tmp_path / "overlay.jpg"
    assert (
        main(
            [
                "detect",
                str(ROOT / "tests/data/button_battery/button_cells_100.jpg"),
                "--config",
                str(ROOT / "examples/button_battery/configs/vision.json"),
                "--output",
                str(result),
                "--annotated",
                str(overlay),
            ]
        )
        == 0
    )
    data = json.loads(result.read_text())
    assert len(data["targets"]) == 100 and overlay.stat().st_size > 0
    assert all(not t["pickable"] for t in data["targets"])
    assert all(t["position"] is None for t in data["targets"])


def test_cli_error_returns_nonzero(capsys):
    assert main(["detect", "missing-file.jpg"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_calibration_cli(tmp_path, capsys):
    source, output = tmp_path / "points.json", tmp_path / "cal.json"
    source.write_text(
        json.dumps(
            {
                "pixels": [[0, 0], [99, 0], [99, 99], [0, 99]],
                "xy_mm": [[0, 0], [99, 0], [99, 99], [0, 99]],
                "image_size": [100, 100],
                "frame_id": "base",
                "plane_z_mm": 10,
            }
        )
    )
    assert main(["calibrate", str(source), "--output", str(output)]) == 0
    assert output.exists()
    assert json.loads(capsys.readouterr().out)["rmse_mm"] < 1e-5


def test_calibration_validation_reports_failure_with_nonzero_exit(tmp_path):
    from industry_cv import PlanarCalibration

    cal = PlanarCalibration.fit(
        [[0, 0], [99, 0], [99, 99], [0, 99]],
        [[0, 0], [99, 0], [99, 99], [0, 99]],
        [100, 100],
        "base",
        10,
    )
    plane, points, report = (
        tmp_path / "plane.json",
        tmp_path / "points.json",
        tmp_path / "report.json",
    )
    cal.save(plane)
    data = {
        "pixels": [[40, 40]],
        "xy_mm": [[45, 40]],
        "image_size": [100, 100],
        "frame_id": "base",
        "plane_z_mm": 10,
        "max_error_mm": 0.5,
    }
    points.write_text(json.dumps(data))
    args = [
        "validate-calibration",
        str(points),
        "--calibration",
        str(plane),
        "--output",
        str(report),
    ]
    assert main(args) == 3
    assert json.loads(report.read_text())["max_error_mm"] == pytest.approx(5)
    data["xy_mm"] = [[40, 40]]
    points.write_text(json.dumps(data))
    assert main(args) == 0
    assert json.loads(report.read_text())["passed"]


def test_estimation_cli_and_reusable_file(tmp_path, capsys):
    image = str(ROOT / "tests/data/button_battery/button_cells_100.jpg")
    config = str(ROOT / "examples/button_battery/configs/vision.json")
    estimated, result = tmp_path / "estimate.json", tmp_path / "result.json"
    assert (
        main(
            [
                "estimate-calibration",
                image,
                "--part-profile",
                "parts/lr41",
                "--config",
                config,
                "--output",
                str(estimated),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["source"] == "estimated"
    assert (
        main(
            [
                "detect",
                image,
                "--config",
                config,
                "--calibration",
                str(estimated),
                "--output",
                str(result),
            ]
        )
        == 0
    )
    data = json.loads(result.read_text())
    assert len(data["targets"]) == 100
    assert all(
        t["position"] is not None and t["position_source"] == "estimated" for t in data["targets"]
    )
    assert (
        main(
            [
                "detect",
                image,
                "--config",
                config,
                "--estimate-diameter-mm",
                "7.9",
                "--output",
                str(result),
            ]
        )
        == 0
    )
    assert json.loads(result.read_text())["calibration"]["source"] == "estimated"


def test_cli_exports_profiles_and_applies_part_dimensions(tmp_path, capsys):
    assert main(["profiles"]) == 0
    assert "parts/lr41" in json.loads(capsys.readouterr().out)["profiles"]
    preset = tmp_path / "part.json"
    assert main(["profiles", "parts/lr41", "--output", str(preset)]) == 0
    assert json.loads(preset.read_text())["nominal_diameter_mm"] == 7.9
    output = tmp_path / "detections.json"
    assert (
        main(
            [
                "detect",
                str(ROOT / "tests/data/button_battery/button_cells_98.jpg"),
                "--config",
                str(ROOT / "examples/button_battery/configs/vision.json"),
                "--part-profile",
                "parts/lr41",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    data = json.loads(output.read_text())
    assert len(data["targets"]) == 98
    assert all(t["position"]["z_mm"] == 3.6 for t in data["targets"])
