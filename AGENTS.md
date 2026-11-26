# Repository guidance

This repository owns reusable industrial vision algorithms, acquisition, geometry, skills and
knowledge. Read `docs/architecture.md` before structural changes. Keep site orchestration,
robot motion, credentials and measured site calibration in the parent repository.

Public API: exports from `industry_cv`, CLI commands and documented JSON fields. Keep source
adapters independent of detectors; use `core.Frame` as their shared contract. Runtime resources
must be packaged under `src/industry_cv/profiles`, never loaded from repo-relative examples.
Preserve coordinate units and distinguish estimated work frames from measured robot transforms.

For button-cell work, read `skills/button-battery-vision/SKILL.md` and linked evidence. Estimates
may be used when authorized by task context; do not let a particular site's defaults leak into
unrelated capabilities. Put reusable learning in `knowledge/cases/` with minimal regression data.

Run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`, `ruff check src tests examples scripts`, and
`ruff format --check src tests examples scripts`. The pytest setting avoids unrelated ROS plugins.
For packaging changes, build/install the wheel and run `scripts/check_installation.py` with the
installation's Python. Update CHANGELOG for changed public defaults or import locations.
