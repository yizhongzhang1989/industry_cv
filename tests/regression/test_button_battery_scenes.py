import json

import cv2
import numpy as np
import pytest

from industry_cv import BatteryDetector, DetectorConfig
from tests.helpers import ROOT


@pytest.mark.parametrize("gain,offset", [(1, 0), (0.65, 10), (1.2, 12)])
def test_real_scene(gain, offset):
    im = cv2.imread(str(ROOT / "tests/data/button_battery/button_cells_100.jpg"))
    im = np.clip(im.astype(float) * gain + offset, 0, 255).astype(np.uint8)
    cfg = DetectorConfig(
        **json.loads((ROOT / "examples/button_battery/configs/vision.json").read_text())
    )
    truth = json.loads((ROOT / "tests/data/button_battery/button_cells_100.json").read_text())[
        "centers_px"
    ]
    cells = BatteryDetector(cfg).detect(im)
    assert len(cells) == len(truth) == 100
    # One-to-one matching to visually reviewed, approximate centers, not predicted float centers.
    remaining = list(cells)
    for point in truth:
        distances = [np.linalg.norm(np.array(c.center_px) - point) for c in remaining]
        i = int(np.argmin(distances))
        assert distances[i] < 3
        remaining.pop(i)


def test_edge_marking_does_not_split_one_battery_into_two():
    im = cv2.imread(str(ROOT / "tests/data/button_battery/button_cells_edge_marking.jpg"))
    cfg = DetectorConfig(
        **json.loads((ROOT / "examples/button_battery/configs/vision.json").read_text())
    )
    cells = BatteryDetector(cfg).detect(im)
    assert len(cells) == 100
    near = [c for c in cells if np.linalg.norm(np.array(c.center_px) - [958, 199]) < 10]
    assert len(near) == 1
    assert np.linalg.norm(np.array(near[0].center_px) - [958, 199]) < 1


def test_real_scene_after_two_cells_removed():
    im = cv2.imread(str(ROOT / "tests/data/button_battery/button_cells_98.jpg"))
    cfg = DetectorConfig(
        **json.loads((ROOT / "examples/button_battery/configs/vision.json").read_text())
    )
    cells = BatteryDetector(cfg).detect(im)
    assert len(cells) == 98
    for removed in ([1300, 766], [1294, 818]):
        assert all(np.linalg.norm(np.array(c.center_px) - removed) > 30 for c in cells)


@pytest.mark.parametrize(
    "fixture", ["button_cells_side_light.jpg", "button_cells_shadow_flicker.jpg"]
)
def test_side_light_scene_keeps_all_100_batteries(fixture):
    im = cv2.imread(str(ROOT / "tests/data/button_battery" / fixture))
    cfg = DetectorConfig(
        **json.loads((ROOT / "examples/button_battery/configs/vision.json").read_text())
    )
    cells = BatteryDetector(cfg).detect(im)
    truth = json.loads((ROOT / "tests/data/button_battery/button_cells_100.json").read_text())[
        "centers_px"
    ]
    # Same board under side light; small camera shift, plus the two replaced bottom-right cells.
    truth = [[1289, 845] if p == [1294, 818] else p for p in truth]
    assert len(cells) == len(truth) == 100
    remaining = list(cells)
    for point in truth:
        distances = [np.linalg.norm(np.array(c.center_px) - point) for c in remaining]
        i = int(np.argmin(distances))
        assert distances[i] < 12  # association bound, not physical localization accuracy
        remaining.pop(i)
