import cv2
import numpy as np
import pytest

from industry_cv import BatteryDetector, DetectorConfig
from tests.helpers import scene


def test_cells_touching_and_separate():
    truth = [(60, 60, 24), (107, 60, 24), (210, 130, 22)]
    cells = BatteryDetector().detect(scene(truth))
    assert len(cells) == 3
    for x, y, radius in truth:
        cell = min(cells, key=lambda d: np.linalg.norm(np.array(d.center_px) - [x, y]))
        assert np.linalg.norm(np.array(cell.center_px) - [x, y]) < 1
        assert abs(cell.radius_px - radius) < 1
    assert sum("neighbor_clearance" in c.blocked_reasons for c in cells) == 2


def test_empty_dark_holes_and_rectangles_are_not_cells():
    im = np.full((220, 320, 3), 170, np.uint8)
    cv2.circle(im, (60, 60), 24, (20, 20, 20), -1)
    assert BatteryDetector().detect(im) == []
    im[:] = 30
    cv2.rectangle(im, (40, 40), (88, 88), (180, 180, 180), -1)
    cv2.rectangle(im, (130, 50), (240, 75), (180, 180, 180), -1)
    assert BatteryDetector().detect(im) == []
    for value in (0, 30, 255):
        assert BatteryDetector().detect(np.full_like(im, value)) == []


def test_roi_excludes_other_disks_and_resolution_guard():
    cfg = DetectorConfig(roi=[[10, 10], [140, 10], [140, 190], [10, 190]], image_size=[320, 220])
    im = scene([(60, 60, 24), (210, 130, 24)])
    assert len(BatteryDetector(cfg).detect(im)) == 1
    with pytest.raises(ValueError, match="resolution"):
        BatteryDetector(cfg).detect(im[:100])


def test_border_object_is_not_eligible():
    cfg = DetectorConfig(roi=[[40, 10], [300, 10], [300, 200], [40, 200]], image_size=[320, 220])
    cells = BatteryDetector(cfg).detect(scene([(60, 60, 24)]))
    assert len(cells) == 1
    assert "roi_border" in cells[0].blocked_reasons


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_radius_px": -1},
        {"max_radius_px": float("nan")},
        {"roi": [[0, 0], [20, 0], [20, 20]]},
        {"clearance_px": -1},
        {"threshold": 300},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        DetectorConfig(**kwargs)
