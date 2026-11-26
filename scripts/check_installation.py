"""Smoke-check an installed wheel outside the checkout (after installing the wheel).

Run with the target environment's Python: python scripts/check_installation.py
No camera/network access. Test images/config are explicit caller inputs, not library resources.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="industry-cv-install-") as folder:
        verify = """
import json
from pathlib import Path
import industry_cv
from industry_cv import BatteryDetector, DetectorConfig, Frame, ButtonBatteryPipeline, VisionPipeline
from industry_cv import load_profile
assert "site-packages" in Path(industry_cv.__file__).parts, industry_cv.__file__
assert VisionPipeline is ButtonBatteryPipeline
assert "roi" not in load_profile("button_battery/default")
assert load_profile("parts/lr41")["nominal_diameter_mm"] == 7.9
BatteryDetector(DetectorConfig(**load_profile("button_battery/default")))
print(industry_cv.__file__)
"""
        subprocess.run([sys.executable, "-I", "-c", verify], cwd=folder, env=env, check=True)
        result = subprocess.run(
            [sys.executable, "-I", "-m", "industry_cv", "profiles"],
            cwd=folder,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "parts/lr41" in json.loads(result.stdout)["profiles"]
        output = Path(folder) / "result.json"
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "industry_cv",
                "detect",
                str(root / "tests/data/button_battery/button_cells_side_light.jpg"),
                "--config",
                str(root / "examples/button_battery/configs/vision.json"),
                "--part-profile",
                "parts/lr41",
                "--output",
                str(output),
            ],
            cwd=folder,
            env=env,
            check=True,
        )
        data = json.loads(output.read_text())
        assert len(data["targets"]) == 100
        assert data["calibration"]["source"] == "estimated"
        assert all(t["position"]["z_mm"] == 3.6 for t in data["targets"])
    print("Installed package, packaged presets and CLI passed outside checkout.")


if __name__ == "__main__":
    main()
