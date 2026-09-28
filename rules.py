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
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath, PureWindowsPath


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

_RULE_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(Rule))


def _rule_from_dict(raw: dict) -> Rule | None:
    """Build a Rule from one JSON entry, or None if the entry is invalid.

    Unknown keys are ignored; missing keys make the entry invalid.
    """
    if not all(k in raw for k in _RULE_FIELDS):
        return None
    try:
        return Rule(
            name=str(raw["name"]),
            enabled=bool(raw["enabled"]),
            condition_type=str(raw["condition_type"]),
            condition_value=str(raw["condition_value"]),
            target_folder=str(raw["target_folder"]),
        )
    except Exception:
        return None


def load_rules() -> list[Rule]:
    """Load rules from disk. Invalid entries are skipped one by one.

    If the file cannot be parsed at all it is backed up to rules.json.bak
    before returning [], so the next save does not silently destroy it.
    """
    if not RULES_FILE.exists():
        return []
    try:
        data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    except Exception:
        try:
            RULES_FILE.replace(RULES_FILE.with_suffix(".json.bak"))
        except OSError:
            pass
        return []
    if not isinstance(data, list):
        return []
    rules = [_rule_from_dict(r) for r in data if isinstance(r, dict)]
    return [r for r in rules if r is not None]


def save_rules(rules: list[Rule]) -> bool:
    """Persist rules to disk. Returns False on any write error."""
    try:
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        RULES_FILE.write_text(
            json.dumps([asdict(r) for r in rules], indent=2), encoding="utf-8"
        )
        return True
    except Exception:
        return False


def is_safe_target_folder(target: str) -> bool:
    """Return True if target is a relative sub-path with no '..' parts.

    Rejects absolute paths, drive letters and UNC paths on every platform so a
    rule can never move files outside the scanned folder.
    """
    target = target.strip()
    if not target:
        return False
    win, posix = PureWindowsPath(target), PurePosixPath(target)
    if win.anchor or win.drive or posix.is_absolute():
        return False
    parts = [p for p in win.parts if p not in ("", ".")]
    return bool(parts) and ".." not in parts


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
