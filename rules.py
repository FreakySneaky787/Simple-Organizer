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
import re
import time
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from utils import atomic_write_text, get_config_dir


def _rules_path() -> Path:
    """Return the platform-appropriate path to rules.json."""
    return get_config_dir() / "rules.json"


RULES_FILE: Path = _rules_path()

# Human-readable labels for the UI
CONDITION_LABELS: dict[str, str] = {
    "extension":       "Extension (e.g. pdf or tar.gz)",
    "name_pattern":    "Filename pattern (e.g. *.log)",
    "min_size_mb":     "Min size (MB, e.g. 100)",
    "max_size_mb":     "Max size (MB, e.g. 10)",
    "older_than_days": "Older than (days, e.g. 365)",
    "newer_than_days": "Newer than (days, e.g. 7)",
}

CONDITION_TYPES = list(CONDITION_LABELS.keys())


class RulesReadError(OSError):
    """rules.json exists but could not be read (locked, no permission, I/O error).

    Callers must not treat this as "no rules": saving afterwards would wipe the
    file, and scanning would sort files without the user's rules.
    """


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
            enabled=raw["enabled"] is True,
            condition_type=str(raw["condition_type"]),
            condition_value=str(raw["condition_value"]),
            target_folder=str(raw["target_folder"]),
        )
    except Exception:
        return None


def _backup_corrupt_file() -> None:
    """Move an unparseable rules.json aside (never overwriting an older backup).

    Raises RulesReadError if that is not possible: returning "no rules" while
    the corrupt file is still in place would let the next save overwrite it.
    """
    stamp  = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = RULES_FILE.with_name(f"rules_corrupt_{stamp}.json")
    counter = 1
    while backup.exists():
        backup = RULES_FILE.with_name(f"rules_corrupt_{stamp}_{counter}.json")
        counter += 1
    try:
        RULES_FILE.replace(backup)
    except OSError as exc:
        raise RulesReadError(
            f"{RULES_FILE} is damaged and could not be backed up ({exc}); "
            "it is left untouched") from exc


def load_rules() -> list[Rule]:
    """Load rules from disk. Invalid entries are skipped one by one.

    If the file is not valid JSON (or not a list) it is backed up to
    rules_corrupt_<time>.json before returning [], so the next save does not
    silently destroy it. If the file exists but cannot be read, or a damaged
    file cannot be backed up, RulesReadError is raised instead -- that must
    never look like "no rules".
    """
    if not RULES_FILE.exists():
        return []
    text: str | None = None
    for attempt in range(3):
        try:
            text = RULES_FILE.read_text(encoding="utf-8")
            break
        except FileNotFoundError:
            return []
        except OSError as exc:
            if attempt == 2:
                raise RulesReadError(f"Could not read {RULES_FILE}: {exc}") from exc
            time.sleep(0.1)
    try:
        data = json.loads(text or "")
    except (ValueError, UnicodeDecodeError):
        _backup_corrupt_file()
        return []
    if not isinstance(data, list):
        _backup_corrupt_file()
        return []
    rules = [_rule_from_dict(r) for r in data if isinstance(r, dict)]
    return [r for r in rules if r is not None]


def save_rules(rules: list[Rule]) -> bool:
    """Persist rules to disk. Returns False on any write error."""
    try:
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(RULES_FILE, json.dumps([asdict(r) for r in rules], indent=2))
        return True
    except Exception:
        return False


_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def is_safe_target_folder(target: str) -> bool:
    """Return True if target is a relative sub-path with no '..' parts.

    Rejects absolute paths, drive letters and UNC paths on every platform so a
    rule can never move files outside the scanned folder. Also rejects names
    Windows cannot create (reserved characters, CON/NUL/COM1..., trailing dots
    or spaces), so a rule never fails file by file at organise time.
    """
    target = target.strip()
    if not target:
        return False
    win, posix = PureWindowsPath(target), PurePosixPath(target)
    if win.anchor or win.drive or posix.is_absolute():
        return False
    parts = [p for p in win.parts if p not in ("", ".")]
    if not parts or ".." in parts:
        return False
    for part in parts:
        if _INVALID_CHARS.search(part) or part != part.rstrip(" ."):
            return False
        if part.split(".")[0].upper() in _RESERVED_NAMES:
            return False
    return True


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
            # endswith instead of comparing .suffix, so "tar.gz" works as well as "gz".
            ext = cv.lstrip(".").lower()
            return bool(ext) and file_path.name.lower().endswith("." + ext)

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
