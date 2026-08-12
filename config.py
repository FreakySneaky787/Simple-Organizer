# config.py
"""Persistent user settings for Simple Organizer.

Storage:
  Linux/macOS : ~/.config/simple_organizer/settings.json
  Windows     : %APPDATA%/simple_organizer/settings.json

Falls back to DEFAULT_SETTINGS silently on any error.
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict = {
    "last_folder":               "",      # last selected directory (str path)
    "staging_mode":              False,   # staging checkbox state
    "dark_mode":                 False,   # theme toggle state
    "window_width":              980,     # saved window width
    "window_height":             720,     # saved window height
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
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        cfg_dir = base / "simple_organizer"
    else:
        cfg_dir = Path.home() / ".config" / "simple_organizer"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "settings.json"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    """Load settings from disk. Returns defaults on missing or corrupted file."""
    path = get_settings_path()
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a dict")
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> bool:
    """Write settings dict to disk. Returns False on any write error."""
    try:
        path = get_settings_path()
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False
