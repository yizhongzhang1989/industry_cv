import runpy

import pytest

from industry_cv import BatteryDetector, VisionPipeline
from tests.helpers import ROOT, frame

build_requests = runpy.run_path(str(ROOT / "examples/button_battery/site_integration.py"))[
    "target_requests"
]


def test_camera_frame_to_parent_pick_proposal_uses_estimated_coordinates():
    vision = VisionPipeline(BatteryDetector(), estimate_diameter_mm=7.9, estimated_height_mm=3.6)
    assert build_requests(vision.process(frame(1)))["proposals"] == []
    vision.process(frame(2))
    result = vision.process(frame(3))
    message = build_requests(result)
    assert message["execution_mode"] == "preview"
    assert len(message["proposals"]) == 1
    proposal = message["proposals"][0]
    assert proposal["position_source"] == "estimated"
    assert proposal["contact"]["frame_id"] == "work_surface_estimated"
    assert proposal["contact"]["z_mm"] == 3.6
    assert proposal["approach"]["z_mm"] == 23.6
    assert proposal["contact"]["quaternion_xyzw"] == [1, 0, 0, 0]
    assert proposal["contact"]["x_mm"] == result["targets"][0]["position"]["x_mm"]
    with pytest.raises(ValueError):
        build_requests(result, approach_mm=float("nan"))
