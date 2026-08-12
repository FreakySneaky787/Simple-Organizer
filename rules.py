# rules.py
"""File-matching rules engine for Simple Organizer.

Rules are evaluated before extension-based categorisation.
The first matching enabled rule wins.

Storage:
  Linux/macOS : ~/.config/simple_organizer/rules.json
  Windows     : %APPDATA%/simple_organizer/rules.json
"""

import fnmatch
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


def _rules_path() -> Path:
    """Return the platform-appropriate path to rules.json."""
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "simple_organizer" / "rules.json"
    return Path.home() / ".config" / "simple_organizer" / "rules.json"


RULES_FILE: Path = _rules_path()

# Human-readable labels for the UI
CONDITION_LABELS: dict[str, str] = {
    "extension":       "Extension (e.g. pdf)",
    "name_pattern":    "Filename pattern (e.g. *.log)",
    "min_size_mb":     "Min size (MB, e.g. 100)",
    "max_size_mb":     "Max size (MB, e.g. 10)",
    "older_than_days": "Older than (days, e.g. 365)",
    "newer_than_days": "Newer than (days, e.g. 7)",
}

CONDITION_TYPES = list(CONDITION_LABELS.keys())


@dataclass
class Rule:
    name:            str
    enabled:         bool
    condition_type:  str   # one of CONDITION_TYPES
    condition_value: str   # string representation of threshold / pattern
    target_folder:   str   # destination subfolder name


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_rules() -> list[Rule]:
    """Load rules from disk. Returns empty list on any error."""
    if not RULES_FILE.exists():
        return []
    try:
        data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [Rule(**r) for r in data if isinstance(r, dict)]
    except Exception:
        return []


def save_rules(rules: list[Rule]) -> None:
    """Persist rules to disk. Silently ignores write errors."""
    try:
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        RULES_FILE.write_text(
            json.dumps([asdict(r) for r in rules], indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match_rule(file_path: Path, rule: Rule) -> bool:
    """Return True if file_path satisfies rule's condition."""
    if not rule.enabled:
        return False
    try:
        ct = rule.condition_type
        cv = rule.condition_value.strip()

        if ct == "extension":
            return file_path.suffix.lstrip(".").lower() == cv.lstrip(".").lower()

        elif ct == "name_pattern":
            return fnmatch.fnmatch(file_path.name.lower(), cv.lower())

        elif ct in ("min_size_mb", "max_size_mb"):
            size_mb = file_path.stat().st_size / (1024 * 1024)
            thr = float(cv)
            return size_mb >= thr if ct == "min_size_mb" else size_mb <= thr

        elif ct in ("older_than_days", "newer_than_days"):
            age_days = (time.time() - file_path.stat().st_mtime) / 86400
            days = float(cv)
            return age_days >= days if ct == "older_than_days" else age_days <= days

    except (OSError, ValueError):
        pass
    return False


def apply_rules(file_path: Path, rules: list[Rule]) -> str | None:
    """Return the first matching rule's target_folder, or None."""
    for rule in rules:
        if match_rule(file_path, rule):
            return rule.target_folder
    return None
