import pytest

from industry_cv import BatteryDetector, DetectorConfig, PlanarCalibration, load_profile


def test_presets_are_site_independent_and_return_owned_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = load_profile("button_battery/default")
    assert "roi" not in settings and "image_size" not in settings
    BatteryDetector(DetectorConfig(**settings))
    part = load_profile("parts/lr41")
    part["nominal_diameter_mm"] = -1
    assert load_profile("parts/lr41")["nominal_diameter_mm"] > 0
    with pytest.raises(ValueError, match="Unknown profile"):
        load_profile("../../examples/button_battery/configs/vision")


def test_geometry_uses_callers_part_dimensions_without_lr41_height():
    cal = PlanarCalibration.from_nominal_diameter(
        [20, 20, 20],
        [100, 100],
        [[0, 0], [99, 0], [99, 99], [0, 99]],
        diameter_mm=5.5,
        origin_px=[40, 40],
    )
    point = cal.project([60, 40], [100, 100])
    assert point["x_mm"] == pytest.approx(5.5)
    assert point["z_mm"] == 0
