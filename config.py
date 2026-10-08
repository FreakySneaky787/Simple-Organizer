# config.py
"""Persistent user settings for Simple Organizer.

Storage:
  Linux/macOS : ~/.config/simple_organizer/settings.json
  Windows     : %APPDATA%/simple_organizer/settings.json

Falls back to DEFAULT_SETTINGS silently on any error.
"""

import copy
import json
import math
from pathlib import Path
from typing import Any

from utils import atomic_write_text, get_config_dir

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict = {
    "last_folder":               "",      # last selected directory (str path)
    "staging_mode":              False,   # staging checkbox state
    "dark_mode":                 False,   # theme toggle state
    "window_width":              980,     # saved window width (normal, not maximised)
    "window_height":             720,     # saved window height (normal, not maximised)
    "window_x":                  None,    # saved window position, None = let the OS decide
    "window_y":                  None,
    "window_maximized":          False,   # window was maximised when the app closed
    "approved_folders":          [],      # unusual folders the user agreed to organise
    "schedule_enabled":          False,   # auto-organise on/off
    "schedule_interval_minutes": 60,      # auto-organise interval in minutes
    "use_subcategories":         False,   # granular sub-folder sorting
    "recursive":                 False,   # scan subdirectories
    "include_hidden":            False,   # include hidden files
    "max_depth":                 5,       # max recursion depth
    "max_dirs":                  10000,   # max directories before abort
    "scan_timeout":              30.0,    # scan wall-clock timeout in seconds
}


# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------

def get_settings_path() -> Path:
    """Return the platform-appropriate path to settings.json."""
    cfg_dir = get_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "settings.json"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def _coerce(key: str, value: Any) -> Any:
    """Return value if it has the type of the default for key, else the default.

    Protects the app from hand-edited files: "max_depth": "x" or
    "dark_mode": "false" must not crash the start or flip a switch.
    """
    default = DEFAULT_SETTINGS[key]
    if default is None:   # optional whole number (window position)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        return int(value)
    if isinstance(default, list):   # list of strings
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            return list(value)
        return []
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, (int, float)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        if not math.isfinite(value):
            return default
        return int(value) if isinstance(default, int) else float(value)
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    return value


def load_settings() -> dict:
    """Load settings from disk. Returns defaults on missing or corrupted file."""
    # deepcopy: the defaults contain a list that must never be shared or mutated.
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        path = get_settings_path()
        if not path.exists():
            return merged
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return merged
        for key, value in data.items():
            merged[key] = _coerce(key, value) if key in DEFAULT_SETTINGS else value
    except Exception:  # noqa: BLE001
        return copy.deepcopy(DEFAULT_SETTINGS)
    return merged


def save_settings(settings: dict) -> bool:
    """Write settings dict to disk. Returns False on any write error."""
    try:
        atomic_write_text(get_settings_path(), json.dumps(settings, indent=2))
        return True
    except Exception:  # noqa: BLE001
        return False
