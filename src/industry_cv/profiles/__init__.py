"""Read portable, site-independent presets from either checkout or installed wheel."""

import json
from importlib.resources import files

_PROFILES = ("button_battery/default", "parts/lr41")


def list_profiles() -> tuple[str, ...]:
    return _PROFILES


def load_profile(name: str) -> dict:
    """Return a fresh JSON object; caller changes never mutate the packaged preset."""
    if name not in _PROFILES:
        raise ValueError(f"Unknown profile: {name}. Available: {', '.join(_PROFILES)}")
    return json.loads(files(__package__).joinpath(f"{name}.json").read_text(encoding="utf-8"))
