# rules.py
"""File-matching rules engine for Simple Organizer.

Rules are evaluated before extension-based categorisation.
The first matching enabled rule wins.

Storage:
  Linux/macOS : ~/.config/simple_organizer/rules.json
  Windows     : %APPDATA%/simple_organizer/rules.json
"""

import json
import re
import time
from dataclasses import asdict, dataclass, field
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
    # Further conditions as {"type": ..., "value": ...}; a rule matches only
    # if ALL its conditions match. Kept separate from the first condition so
    # rules.json stays readable for older versions.
    more_conditions: list[dict[str, str]] = field(default_factory=list)

    def conditions(self) -> list[tuple[str, str]]:
        """All conditions of the rule as (type, value) pairs, first one first."""
        return [(self.condition_type, self.condition_value)] + [
            (c["type"], c["value"]) for c in self.more_conditions]

    def describe(self) -> str:
        """The conditions as text for the Rules tab, e.g. "extension pdf + older_than_days 365"."""
        return "  +  ".join(f"{t} {v}" for t, v in self.conditions())


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_RULE_FIELDS: tuple[str, ...] = (
    "name", "enabled", "condition_type", "condition_value", "target_folder")


def _rule_from_dict(raw: dict) -> Rule | None:
    """Build a Rule from one JSON entry, or None if the entry is invalid.

    Unknown keys are ignored; missing keys make the entry invalid. A damaged
    more_conditions list also makes the entry invalid: dropping a condition
    would make the rule match more files than the user wanted.
    """
    if not all(k in raw for k in _RULE_FIELDS):
        return None
    more = raw.get("more_conditions", [])
    if not isinstance(more, list) or not all(
            isinstance(c, dict) and isinstance(c.get("type"), str) and isinstance(c.get("value"), str)
            for c in more):
        return None
    try:
        return Rule(
            name=str(raw["name"]),
            enabled=raw["enabled"] is True,
            condition_type=str(raw["condition_type"]),
            condition_value=str(raw["condition_value"]),
            target_folder=str(raw["target_folder"]),
            more_conditions=[{"type": c["type"], "value": c["value"]} for c in more],
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

    The file is read as UTF-8; a byte order mark (Notepad, PowerShell) is
    accepted. If the file is not valid UTF-8 JSON (or not a list) it is backed
    up to rules_corrupt_<time>.json before returning [], so the next save does
    not silently destroy it. If the file exists but cannot be read, or a
    damaged file cannot be backed up, RulesReadError is raised instead -- that
    must never look like "no rules".
    """
    if not RULES_FILE.exists():
        return []
    raw = b""
    for attempt in range(3):
        try:
            raw = RULES_FILE.read_bytes()
            break
        except FileNotFoundError:
            return []
        except OSError as exc:
            if attempt == 2:
                raise RulesReadError(f"Could not read {RULES_FILE}: {exc}") from exc
            time.sleep(0.1)
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError:   # also UnicodeDecodeError: e.g. saved as ANSI or UTF-16
        _backup_corrupt_file()
        return []
    if not isinstance(data, list):
        _backup_corrupt_file()
        return []
    rules = [_rule_from_dict(r) for r in data if isinstance(r, dict)]
    return [r for r in rules if r is not None]


def _rule_to_dict(rule: Rule) -> dict:
    """JSON entry for rule. more_conditions is only written when a rule has
    further conditions: v3.4.0 and older reject unknown keys and would lose
    every rule, even the simple ones, after going back to such a version."""
    data = asdict(rule)
    if not data["more_conditions"]:
        del data["more_conditions"]
    return data


def save_rules(rules: list[Rule]) -> bool:
    """Persist rules to disk. Returns False on any write error."""
    try:
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(RULES_FILE, json.dumps([_rule_to_dict(r) for r in rules], indent=2))
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


def normalize_extension(value: str) -> str:
    """"pdf", ".pdf" and "*.pdf" all mean the extension "pdf"."""
    return value.strip().lstrip("*").lstrip(".").lower()


def is_valid_extension(value: str) -> bool:
    """True for one extension such as "pdf" or "tar.gz" (not "pdf, docx")."""
    ext = normalize_extension(value)
    return bool(ext) and not any(c in ext for c in ' ,;/\\*?"<>|') and ".." not in ext


NUMERIC_CONDITIONS = frozenset({"min_size_mb", "max_size_mb", "older_than_days", "newer_than_days"})


def condition_problem(ctype: str, value: str) -> str | None:
    """Why value is not valid for the condition ctype, or None if it is."""
    value = value.strip()
    if ctype not in CONDITION_LABELS:
        return f'"{ctype}" is not a known condition.'
    if not value:
        return f'"{ctype}" needs a value.'
    if ctype == "extension" and not is_valid_extension(value):
        return (f'"{value}" is not a single file extension. Enter one extension such as '
                "pdf or tar.gz -- use one condition per extension.")
    if ctype in NUMERIC_CONDITIONS:
        try:
            number = float(value)
        except ValueError:
            number = float("nan")
        if not (number >= 0 and number != float("inf")):
            return f'"{value}" is not a valid number for "{ctype}". Enter zero or a positive number (e.g. 100).'
    return None


def normalize_condition_value(ctype: str, value: str) -> str:
    value = value.strip()
    return normalize_extension(value) if ctype == "extension" else value


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def name_pattern_matches(name: str, pattern: str) -> bool:
    """Filename pattern match, ignoring case. Only * (any text) and ? (one
    character) are wildcards; everything else -- also [ and ] -- matches
    itself, so "[Draft]*" finds "[Draft] report.docx" (#96)."""
    regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
    return re.fullmatch(regex, name, re.IGNORECASE | re.DOTALL) is not None


def match_rule(file_path: Path, rule: Rule) -> bool:
    """Return True if file_path satisfies every condition of rule."""
    if not rule.enabled:
        return False
    return all(_match_condition(file_path, ct, cv) for ct, cv in rule.conditions())


def _match_condition(file_path: Path, ct: str, cv: str) -> bool:
    try:
        cv = cv.strip()

        if ct == "extension":
            # endswith instead of comparing .suffix, so "tar.gz" works as well as "gz".
            ext = normalize_extension(cv)
            return bool(ext) and file_path.name.lower().endswith("." + ext)

        elif ct == "name_pattern":
            return name_pattern_matches(file_path.name, cv)

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
