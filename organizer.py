# organizer.py

import hashlib
import json
import os
import shutil
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Generator

# All local imports at the top (fixes O4)
from utils import (
    CATEGORY_MAP,
    ALL_SUBCATEGORY_NAMES,
    DEFAULT_EXCLUDED_DIRS,
    get_category,
    get_subcategory,
    get_data_dir,
    get_app_dir,
    resolve_conflict,
)
from rules import load_rules, apply_rules

# ---------------------------------------------------------------------------
# Paths  (cross-platform via get_data_dir())
# ---------------------------------------------------------------------------

DATA_DIR              = get_data_dir()
STAGING_DIR           = DATA_DIR / "staging"
LAST_RUN_FILE         = DATA_DIR / "last_run.json"
STAGING_MANIFEST_FILE = DATA_DIR / "staging_manifest.json"
HISTORY_DIR           = DATA_DIR / "history"
MAX_HISTORY           = 20

# Only top-level category folder names are always excluded.
# Sub-category names (Photos, PDFs, Python…) are added dynamically inside
# scan_folder when use_subcategories=True so they don't accidentally block
# legitimate user folders with the same name when sub-categories is OFF.
_CATEGORY_NAMES: frozenset[str] = frozenset(CATEGORY_MAP.keys())


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

_CHUNK_SIZE:           int = 65_536
DEFAULT_MAX_HASH_SIZE: int = 500 * 1024 * 1024


def _sha256(path: Path) -> str | None:
    """Return SHA-256 hex digest of path, or None on any read error."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while chunk := fh.read(_CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def find_duplicates(
    files: list[Path],
    progress_callback: Callable[[int, int], None] | None = None,
    max_hash_size: int = DEFAULT_MAX_HASH_SIZE,
) -> list[list[Path]]:
    """Return groups of byte-identical files (2+ members each).

    Two-stage: size buckets first (cheap), then SHA-256 for matches only.
    Files larger than max_hash_size are skipped entirely.
    """
    size_buckets: dict[int, list[Path]] = defaultdict(list)
    for f in files:
        try:
            sz = f.stat().st_size
            if sz <= max_hash_size:
                size_buckets[sz].append(f)
        except (OSError, PermissionError):
            pass

    candidates: list[Path] = [
        f for group in size_buckets.values() if len(group) > 1 for f in group
    ]

    hash_buckets: dict[tuple[int, str], list[Path]] = defaultdict(list)
    total   = len(candidates)
    current = 0

    for f in candidates:
        digest = _sha256(f)
        current += 1
        if progress_callback:
            progress_callback(current, total)
        if digest is None:
            continue
        try:
            hash_buckets[(f.stat().st_size, digest)].append(f)
        except (OSError, PermissionError):
            pass

    return [g for g in hash_buckets.values() if len(g) > 1]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FilePlan:
    source:      Path
    destination: Path
    category:    str   # may be "Images/Photos" when subcategories are on
    skipped:     bool = False


@dataclass
class ScanResult:
    plans:            list[FilePlan]   = field(default_factory=list)
    duplicate_groups: list[list[Path]] = field(default_factory=list)
    errors:           list[str]        = field(default_factory=list)
    total_files:      int              = 0


# ---------------------------------------------------------------------------
# Safeguarded recursive file iterator
# ---------------------------------------------------------------------------

def _iter_files_recursive(
    root:               Path,
    include_hidden:     bool                         = False,
    max_depth:          int                          = 5,
    max_dirs:           int                          = 10_000,
    scan_timeout:       float                        = 30.0,
    excluded_dirs:      frozenset[str] | None        = None,
    excluded_abs_paths: frozenset[str]               = frozenset(),
    log_callback:       Callable[[str], None] | None = None,
) -> Generator[Path, None, None]:
    """Yield every regular file under root subject to hard safety limits.

    Symlinks are never followed. /proc and /sys are unconditionally excluded.
    Category folders are skipped to prevent re-processing organised files.
    excluded_abs_paths: resolved absolute directory paths that are always
    skipped regardless of name — used to protect the app's own directory.
    """
    if excluded_dirs is None:
        excluded_dirs = DEFAULT_EXCLUDED_DIRS

    all_excluded: frozenset[str] = excluded_dirs | _CATEGORY_NAMES

    # Merge hard-coded absolute exclusions with caller-supplied ones.
    abs_excluded: frozenset[str] = frozenset({"/proc", "/sys"}) | excluded_abs_paths

    deadline:     float              = time.monotonic() + scan_timeout
    dirs_visited: int                = 0
    stack: list[tuple[str, int]]     = [(str(root.resolve()), 0)]

    while stack:
        if time.monotonic() >= deadline:
            if log_callback:
                log_callback(
                    f"[TIMEOUT]  Scan aborted after {scan_timeout:.0f}s — "
                    f"{dirs_visited} director{'y' if dirs_visited == 1 else 'ies'} visited."
                )
            return

        current_str, depth = stack.pop()
        dirs_visited += 1

        if dirs_visited > max_dirs:
            if log_callback:
                log_callback(f"[LIMIT]  Directory count exceeded {max_dirs:,} — scan aborted.")
            return

        try:
            with os.scandir(current_str) as it:
                entries = list(it)
        except PermissionError:
            if log_callback:
                log_callback(f"[SKIP]  Permission denied: {current_str}")
            continue
        except OSError as exc:
            if log_callback:
                log_callback(f"[SKIP]  OS error reading {current_str}: {exc}")
            continue

        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            try:
                if entry.is_symlink():
                    continue
                is_file = entry.is_file(follow_symlinks=False)
                is_dir  = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue

            if is_file:
                yield Path(entry.path)
            elif is_dir:
                if entry.name in all_excluded:
                    continue
                if entry.path in abs_excluded:
                    continue
                next_depth = depth + 1
                if next_depth > max_depth:
                    if log_callback:
                        log_callback(
                            f"[DEPTH]  Max depth {max_depth} reached, skipping: {entry.path}"
                        )
                    continue
                stack.append((entry.path, next_depth))


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_folder(
    folder:            Path,
    recursive:         bool                          = False,
    include_hidden:    bool                          = False,
    max_depth:         int                           = 5,
    max_dirs:          int                           = 10_000,
    scan_timeout:      float                         = 30.0,
    use_subcategories: bool                          = False,
    excluded_dirs:     frozenset[str] | None         = None,
    progress_callback: Callable[[int, int], None] | None = None,
    status_callback:   Callable[[str], None]       | None = None,
) -> ScanResult:
    """Scan folder and return a ScanResult with file plans and duplicate groups."""
    result = ScanResult()

    if not folder.exists():
        result.errors.append(f"Folder does not exist: {folder}")
        return result
    if not folder.is_dir():
        result.errors.append(f"Path is not a directory: {folder}")
        return result

    # Build effective exclusion set.
    # Sub-category folder names are only excluded when use_subcategories=True
    # so common folder names like "Python", "Photos", "Web" are not silently
    # skipped when the user has sub-categories turned off.
    base_excl = excluded_dirs if excluded_dirs is not None else DEFAULT_EXCLUDED_DIRS
    eff_excluded: frozenset[str] = (
        base_excl | ALL_SUBCATEGORY_NAMES if use_subcategories else base_excl
    )

    # Self-protection: resolve the app's own directory once and never touch it.
    app_dir: Path = get_app_dir()
    app_dir_str: str = str(app_dir)

    if status_callback:
        status_callback("Collecting files...")

    def _log_warning(msg: str) -> None:
        result.errors.append(msg)
        if status_callback:
            status_callback(msg)

    try:
        if recursive:
            all_files: list[Path] = list(
                _iter_files_recursive(
                    root=folder,
                    include_hidden=include_hidden,
                    max_depth=max_depth,
                    max_dirs=max_dirs,
                    scan_timeout=scan_timeout,
                    excluded_dirs=eff_excluded,
                    excluded_abs_paths=frozenset({app_dir_str}),
                    log_callback=_log_warning,
                )
            )
        else:
            all_files = []
            try:
                with os.scandir(str(folder)) as it:
                    for entry in it:
                        if not include_hidden and entry.name.startswith("."):
                            continue
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_file(follow_symlinks=False):
                                # Self-protection: skip files inside the app dir
                                if str(Path(entry.path).resolve().parent) == app_dir_str:
                                    continue
                                all_files.append(Path(entry.path))
                        except OSError:
                            continue
            except PermissionError as exc:
                result.errors.append(f"Permission denied reading {folder}: {exc}")
                return result
    except PermissionError as exc:
        result.errors.append(f"Permission denied reading {folder}: {exc}")
        return result

    result.total_files = len(all_files)
    if result.total_files == 0:
        return result

    if status_callback:
        status_callback(f"Scanning: 0 / {result.total_files} files (0%)")

    active_rules = load_rules()

    for idx, file_path in enumerate(all_files, start=1):
        pct = int(idx / result.total_files * 100)
        if progress_callback:
            progress_callback(idx, result.total_files)
        if status_callback:
            status_callback(f"Scanning: {idx} / {result.total_files} files ({pct}%)")

        try:
            # Self-protection: resolve once, check once.
            # app_dir in .parents covers files at any depth inside the app dir,
            # including direct children — the .parent == app_dir check is redundant.
            resolved = file_path.resolve()
            if app_dir in resolved.parents:
                continue

            rule_category = apply_rules(file_path, active_rules) if active_rules else None
            category      = rule_category if rule_category else get_category(file_path)

            if use_subcategories and not rule_category:
                sub = get_subcategory(file_path, category)
                if sub:
                    target_dir  = folder / category / sub
                    display_cat = f"{category}/{sub}"
                else:
                    target_dir  = folder / category
                    display_cat = category
            else:
                target_dir  = folder / category
                display_cat = category

            destination    = target_dir / file_path.name
            already_placed = (file_path.parent == target_dir)

            result.plans.append(FilePlan(
                source=file_path,
                destination=destination,
                category=display_cat,
                skipped=already_placed,
            ))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Error processing {file_path.name}: {exc}")

    if status_callback:
        status_callback("Detecting duplicates...")

    # Only pass files that are not inside the app directory to duplicate detection.
    # all_files may still contain app-dir files that were skipped during planning.
    dup_candidates = [f for f in all_files if app_dir not in f.resolve().parents]

    try:
        result.duplicate_groups = find_duplicates(
            files=dup_candidates,
            progress_callback=progress_callback,
        )
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Duplicate detection error: {exc}")

    if status_callback:
        status_callback("Scan complete.")

    return result


# ---------------------------------------------------------------------------
# Organising
# ---------------------------------------------------------------------------

def organise_files(
    plans:             list[FilePlan],
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
    staging:           bool = False,
) -> list[str]:
    """Execute planned file moves. Files are NEVER deleted or overwritten."""
    _ensure_data_dir()

    errors:    list[str]           = []
    actionable                     = [p for p in plans if not p.skipped]
    total                          = len(actionable)
    timestamp                      = datetime.now(timezone.utc).isoformat()
    move_log: list[dict[str, str]] = []

    for idx, plan in enumerate(actionable, start=1):
        if progress_callback:
            progress_callback(idx, total)

        try:
            if staging:
                actual_dest = STAGING_DIR / Path(plan.category) / plan.source.name
            else:
                actual_dest = plan.destination

            actual_dest.parent.mkdir(parents=True, exist_ok=True)
            safe_dest = resolve_conflict(actual_dest)
            shutil.move(str(plan.source), str(safe_dest))

            move_log.append({
                "src":       str(plan.source),
                "dst":       str(safe_dest),
                "final_dst": str(plan.destination),
            })

            tag = "[STAGED]" if staging else "[MOVED]"
            msg = f"{tag}  {plan.source.name}  ->  {plan.category}/"
            if safe_dest.name != plan.source.name:
                msg += f"  (renamed -> {safe_dest.name})"
            if log_callback:
                log_callback(msg)

        except PermissionError as exc:
            err = f"[ERROR]  Permission denied moving {plan.source.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)
        except shutil.Error as exc:
            err = f"[ERROR]  shutil error for {plan.source.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Unexpected error for {plan.source.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)

    if staging:
        if move_log:
            # Only write manifest when at least one file was actually staged.
            STAGING_MANIFEST_FILE.write_text(
                json.dumps({"timestamp": timestamp, "entries": move_log}, indent=2),
                encoding="utf-8",
            )
    else:
        if move_log:
            # Only write history when at least one file was actually moved.
            run_data = {
                "timestamp": timestamp,
                "moves": [{"src": m["src"], "dst": m["dst"]} for m in move_log],
            }
            LAST_RUN_FILE.write_text(json.dumps(run_data, indent=2), encoding="utf-8")
            _write_history_run(run_data, log_callback)

    return errors


# ---------------------------------------------------------------------------
# Undo history
# ---------------------------------------------------------------------------

def _write_history_run(
    run_data: dict,
    log_callback: Callable[[str], None] | None = None,
) -> None:
    """Write a timestamped history file and trim oldest beyond MAX_HISTORY."""
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
        path = HISTORY_DIR / f"run_{ts}.json"
        path.write_text(json.dumps(run_data, indent=2), encoding="utf-8")
        runs = sorted(HISTORY_DIR.glob("run_*.json"))
        for old in runs[:-MAX_HISTORY]:
            try:
                old.unlink()
            except Exception as exc:
                if log_callback:
                    log_callback(f"[WARN]  Could not trim old history file: {exc}")
    except Exception as exc:
        if log_callback:
            log_callback(f"[WARN]  Failed to write history: {exc}")


def list_undo_history() -> list[dict]:
    """Return metadata for all undoable runs, newest first."""
    if not HISTORY_DIR.exists():
        return []
    runs   = sorted(HISTORY_DIR.glob("run_*.json"), reverse=True)
    result: list[dict] = []
    for f in runs:
        try:
            data  = json.loads(f.read_text(encoding="utf-8"))
            ts    = data.get("timestamp", "")
            count = len(data.get("moves", []))
            try:
                dt  = datetime.fromisoformat(ts)  # O3 fix: no re-import needed
                lbl = dt.strftime("%b %d %H:%M") + f"  -  {count} file(s)"
            except Exception:
                lbl = f"{f.stem}  -  {count} file(s)"
            result.append({
                "id":         f.stem,
                "timestamp":  ts,
                "move_count": count,
                "file_path":  f,
                "label":      lbl,
            })
        except Exception:
            pass
    return result


def _undo_run_file(
    run_file:          Path,
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
) -> list[str]:
    """Reverse all moves in run_file. Renames it to undone_* when done."""
    errors: list[str] = []

    try:
        data  = json.loads(run_file.read_text(encoding="utf-8"))
        moves = list(reversed(data.get("moves", [])))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Failed to read {run_file.name}: {exc}")
        if log_callback:
            log_callback(f"[ERROR]  {errors[-1]}")
        return errors

    total = len(moves)

    for idx, entry in enumerate(moves, start=1):
        if progress_callback:
            progress_callback(idx, total)

        src_path = Path(entry["src"])
        dst_path = Path(entry["dst"])

        if not dst_path.exists():
            if log_callback:
                log_callback(f"[SKIP]  {dst_path.name} not found -- skipping.")
            continue

        try:
            src_path.parent.mkdir(parents=True, exist_ok=True)
            safe_src = resolve_conflict(src_path)
            shutil.move(str(dst_path), str(safe_src))
            msg = f"[UNDONE]  {dst_path.name}  ->  {safe_src.parent.name}/"
            if safe_src.name != src_path.name:
                msg += f"  (renamed -> {safe_src.name})"
            if log_callback:
                log_callback(msg)
        except PermissionError as exc:
            err = f"[ERROR]  Permission denied restoring {dst_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)
        except shutil.Error as exc:
            err = f"[ERROR]  shutil error restoring {dst_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Unexpected error restoring {dst_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)

    ts_safe     = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    undone_path = run_file.parent / f"undone_{ts_safe}.json"
    try:
        run_file.rename(undone_path)
    except Exception as exc:  # noqa: BLE001
        if log_callback:
            log_callback(f"[WARN]  Could not rename {run_file.name}: {exc}")

    return errors


def undo_last_run(
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
) -> list[str]:
    """Reverse every move in last_run.json. Files are NEVER deleted."""
    if not LAST_RUN_FILE.exists():
        if log_callback:
            log_callback("[WARN]  No last run record found.")
        return ["No last_run.json found -- nothing to undo."]
    return _undo_run_file(LAST_RUN_FILE, progress_callback, log_callback)


def undo_specific_run(
    run_file:          Path,
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
) -> list[str]:
    """Undo any specific history run_*.json file."""
    if not run_file.exists():
        return [f"Run file not found: {run_file.name}"]
    return _undo_run_file(run_file, progress_callback, log_callback)


# ---------------------------------------------------------------------------
# Staging commit / revert
# ---------------------------------------------------------------------------

def commit_staging(
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
) -> list[str]:
    """Move staged files to final destinations. Writes last_run for undo."""
    _ensure_data_dir()
    errors: list[str] = []

    if not STAGING_MANIFEST_FILE.exists():
        if log_callback:
            log_callback("[WARN]  No staging manifest found.")
        return ["No staging manifest found -- nothing to commit."]

    try:
        data    = json.loads(STAGING_MANIFEST_FILE.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to read staging manifest: {exc}"
        if log_callback:
            log_callback(f"[ERROR]  {err}")
        return [err]

    total     = len(entries)
    timestamp = datetime.now(timezone.utc).isoformat()
    move_log: list[dict[str, str]] = []

    for idx, entry in enumerate(entries, start=1):
        if progress_callback:
            progress_callback(idx, total)

        staged_path = Path(entry["dst"])
        final_dst   = Path(entry["final_dst"])

        if not staged_path.exists():
            if log_callback:
                log_callback(f"[SKIP]  {staged_path.name} not in staging -- skipping.")
            continue

        try:
            final_dst.parent.mkdir(parents=True, exist_ok=True)
            safe_final = resolve_conflict(final_dst)
            shutil.move(str(staged_path), str(safe_final))
            move_log.append({"src": entry["src"], "dst": str(safe_final)})
            msg = f"[COMMITTED]  {staged_path.name}  ->  {safe_final.parent.name}/"
            if safe_final.name != staged_path.name:
                msg += f"  (renamed -> {safe_final.name})"
            if log_callback:
                log_callback(msg)
        except PermissionError as exc:
            err = f"[ERROR]  Permission denied committing {staged_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)
        except shutil.Error as exc:
            err = f"[ERROR]  shutil error committing {staged_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Unexpected error committing {staged_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)

    run_data = {"timestamp": timestamp, "moves": move_log}
    if move_log:
        # Only write history when at least one file was actually moved.
        LAST_RUN_FILE.write_text(json.dumps(run_data, indent=2), encoding="utf-8")
        _write_history_run(run_data, log_callback)

    try:
        STAGING_MANIFEST_FILE.unlink(missing_ok=True)
        _remove_empty_staging_dirs()
    except Exception as exc:  # noqa: BLE001
        if log_callback:
            log_callback(f"[WARN]  Could not clean staging area: {exc}")

    return errors


def revert_staging(
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
) -> list[str]:
    """Move staged files back to original locations. Never deletes."""
    errors: list[str] = []

    if not STAGING_MANIFEST_FILE.exists():
        if log_callback:
            log_callback("[WARN]  No staging manifest found.")
        return ["No staging manifest found -- nothing to revert."]

    try:
        data    = json.loads(STAGING_MANIFEST_FILE.read_text(encoding="utf-8"))
        entries = list(reversed(data.get("entries", [])))
    except Exception as exc:  # noqa: BLE001
        err = f"Failed to read staging manifest: {exc}"
        if log_callback:
            log_callback(f"[ERROR]  {err}")
        return [err]

    total = len(entries)

    for idx, entry in enumerate(entries, start=1):
        if progress_callback:
            progress_callback(idx, total)

        staged_path  = Path(entry["dst"])
        original_src = Path(entry["src"])

        if not staged_path.exists():
            if log_callback:
                log_callback(f"[SKIP]  {staged_path.name} not in staging -- skipping.")
            continue

        try:
            original_src.parent.mkdir(parents=True, exist_ok=True)
            safe_src = resolve_conflict(original_src)
            shutil.move(str(staged_path), str(safe_src))
            msg = f"[REVERTED]  {staged_path.name}  ->  {safe_src.parent}/"
            if safe_src.name != original_src.name:
                msg += f"  (renamed -> {safe_src.name})"
            if log_callback:
                log_callback(msg)
        except PermissionError as exc:
            err = f"[ERROR]  Permission denied reverting {staged_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)
        except shutil.Error as exc:
            err = f"[ERROR]  shutil error reverting {staged_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Unexpected error reverting {staged_path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)

    try:
        STAGING_MANIFEST_FILE.unlink(missing_ok=True)
        _remove_empty_staging_dirs()
    except Exception as exc:  # noqa: BLE001
        if log_callback:
            log_callback(f"[WARN]  Could not clean staging area: {exc}")

    return errors


def _remove_empty_staging_dirs() -> None:
    """Remove empty subdirectories under STAGING_DIR. Never removes files."""
    if not STAGING_DIR.exists():
        return
    for sub in list(STAGING_DIR.iterdir()):
        if sub.is_dir():
            try:
                sub.rmdir()
            except OSError:
                pass
    try:
        STAGING_DIR.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def has_last_run() -> bool:
    return LAST_RUN_FILE.exists()


def has_staging() -> bool:
    return STAGING_MANIFEST_FILE.exists()


def has_undo_history() -> bool:
    """Return True if there is at least one undoable history entry."""
    return bool(list_undo_history())
