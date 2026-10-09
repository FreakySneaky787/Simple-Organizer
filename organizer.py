# organizer.py

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Generator
from urllib.parse import quote

# All local imports at the top (fixes O4)
from utils import (
    CATEGORY_MAP,
    DEFAULT_EXCLUDED_DIRS,
    atomic_write_text,
    get_category,
    get_subcategory,
    get_data_dir,
    is_cloud_placeholder,
    is_inside,
    is_transient_file,
    protected_dirs,
    protected_files,
    resolve_conflict,
    safe_move,
    xdg_base_dir,
)
from rules import RulesReadError, load_rules, apply_rules, is_safe_target_folder

# ---------------------------------------------------------------------------
# Paths  (cross-platform via get_data_dir())
# ---------------------------------------------------------------------------

DATA_DIR              = get_data_dir()
STAGING_DIR           = DATA_DIR / "staging"
LAST_RUN_FILE         = DATA_DIR / "last_run.json"
STAGING_MANIFEST_FILE = DATA_DIR / "staging_manifest.json"
HISTORY_DIR           = DATA_DIR / "history"
# Runs dropped from the undo list are kept here for a while, so undoing an
# older run can still follow a file that one of them moved again.
TRIMMED_DIR           = HISTORY_DIR / "trimmed"
MAX_HISTORY           = 20    # undoable runs kept -- separately for manual and scheduled runs
MAX_TRIMMED           = 200

# Journals (history run / staging manifest) are rewritten at most this often
# while files are being moved, so a crash or power cut mid-run still leaves a
# record of every file moved up to that point.
JOURNAL_FLUSH_SECONDS = 2.0

# Category folders are only excluded directly inside the scanned folder --
# that is the only place the organiser creates them. Sub-category folders
# (Photos, PDFs, Python...) live inside those and are therefore never reached,
# and a user's own "Projects/Images" or "Code/Python" folder is still scanned.
_CATEGORY_NAMES: frozenset[str] = frozenset(CATEGORY_MAP.keys())

_ALWAYS_EXCLUDED_ABS: frozenset[str] = frozenset({"/proc", "/sys"})


def _is_safe_rule_target(root_resolved: Path, target: str) -> bool:
    """Return True if target is a relative sub-path that stays inside root.

    Second line of defence behind the rule dialog: also catches rules.json
    edited by hand and symlinks pointing out of the scanned folder.
    """
    if not is_safe_target_folder(target):
        return False
    try:
        resolved = (root_resolved / target).resolve()
    except (OSError, RuntimeError):
        return False
    return resolved != root_resolved and root_resolved in resolved.parents


def _target_problem(root: Path, target_dir: Path) -> str | None:
    """Why files must not be moved into target_dir (a folder below root), or None.

    Checks every folder between root and target_dir: a *file* with a folder's
    name makes creating the folder fail for every single file, and a link or
    junction that leads outside root would move the files out of the scanned
    folder -- possibly onto another drive.
    """
    rel = target_dir.relative_to(root)
    current = root
    for part in rel.parts:
        current = current / part
        if current.exists() and not current.is_dir():
            return (f"a file named '{current.name}' blocks the folder '{rel.as_posix()}' "
                    "-- rename or move that file")
    try:
        resolved = target_dir.resolve()
    except (OSError, RuntimeError) as exc:
        return f"the folder '{rel.as_posix()}' cannot be resolved ({exc})"
    if not is_inside(resolved, root):
        return (f"the folder '{rel.as_posix()}' is a link that points outside the scanned "
                f"folder ({resolved})")
    return None


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    skipped_large: list[Path] | None = None,
    deadline: float | None = None,
    log_callback: Callable[[str], None] | None = None,
    skipped_cloud: list[Path] | None = None,
    hard_links: list[Path] | None = None,
) -> list[list[Path]]:
    """Return groups of byte-identical files (2+ members each).

    Two-stage: size buckets first (cheap), then SHA-256 for matches only.
    Empty files are ignored: they are all "identical", and offering to trash
    e.g. empty __init__.py files would break projects. Cloud placeholders
    (OneDrive "online-only" etc.) are never read -- that would download them --
    and are appended to skipped_cloud. Files larger than max_hash_size are
    skipped and appended to skipped_large. Hard links of one file are the same
    file, not duplicates: only the first path is checked, the others are
    appended to hard_links. Hashing stops at deadline (time.monotonic()
    value); groups found so far are still correct.
    """
    size_buckets: dict[int, list[Path]] = defaultdict(list)
    seen_files: set[tuple[int, int]] = set()
    for f in files:
        try:
            st = f.stat()
        except (OSError, PermissionError):
            continue
        sz = st.st_size
        if sz == 0:
            continue
        if st.st_ino:   # 0 on file systems without file IDs: cannot tell, keep it
            file_id = (st.st_dev, st.st_ino)
            if file_id in seen_files:
                if hard_links is not None:
                    hard_links.append(f)
                continue
            seen_files.add(file_id)
        if is_cloud_placeholder(st):
            if skipped_cloud is not None:
                skipped_cloud.append(f)
            continue
        if sz > max_hash_size:
            if skipped_large is not None:
                skipped_large.append(f)
            continue
        size_buckets[sz].append(f)

    candidates: list[tuple[int, Path]] = [
        (sz, f) for sz, group in size_buckets.items() if len(group) > 1 for f in group
    ]

    hash_buckets: dict[tuple[int, str], list[Path]] = defaultdict(list)
    total = len(candidates)

    for current, (sz, f) in enumerate(candidates, start=1):
        if deadline is not None and time.monotonic() >= deadline:
            if log_callback:
                log_callback(f"[TIMEOUT]  Duplicate check stopped after {current - 1} of "
                             f"{total} files -- the duplicate list may be incomplete.")
            break
        digest = _sha256(f)
        if progress_callback:
            progress_callback(current, total)
        if digest is None:
            continue
        hash_buckets[(sz, digest)].append(f)

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
    size:        int  = 0
    root:        Path | None = None   # the scanned folder the plan belongs to


@dataclass
class ScanResult:
    plans:            list[FilePlan]   = field(default_factory=list)
    duplicate_groups: list[list[Path]] = field(default_factory=list)
    errors:           list[str]        = field(default_factory=list)  # problems, shown as warnings
    notes:            list[str]        = field(default_factory=list)  # tagged info lines for the log
    total_files:      int              = 0
    total_bytes:      int              = 0   # size of all files that would move


# ---------------------------------------------------------------------------
# Safeguarded file iteration
# ---------------------------------------------------------------------------

def _entry_flags(entry: os.DirEntry) -> tuple[bool, bool]:
    """Return (hidden, system) for a directory entry.

    Hidden means a dot name, or on Windows the Hidden attribute. System means
    the Windows System attribute (desktop.ini, $RECYCLE.BIN, ...). On Windows
    os.scandir already has the attributes, so this costs no extra system call.
    """
    hidden = entry.name.startswith(".")
    system = False
    if sys.platform == "win32":
        try:
            attrs = entry.stat(follow_symlinks=False).st_file_attributes
        except OSError:
            attrs = 0
        hidden = hidden or bool(attrs & stat.FILE_ATTRIBUTE_HIDDEN)
        system = bool(attrs & stat.FILE_ATTRIBUTE_SYSTEM)
    return hidden, system


def _is_link(entry: os.DirEntry) -> bool:
    """True for symlinks and Windows junctions -- neither is ever followed."""
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)
    return bool(is_junction and is_junction())


def _keep_file(entry: os.DirEntry, include_hidden: bool, counter: list[int]) -> bool:
    """Decide whether a regular file entry is organised; counts the ones left alone."""
    hidden, system = _entry_flags(entry)
    if hidden and not include_hidden:
        return False
    if system or is_transient_file(entry.name):
        counter[0] += 1
        return False
    return True


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _iter_files_recursive(
    root:               Path,
    include_hidden:     bool                         = False,
    max_depth:          int                          = 5,
    max_dirs:           int                          = 10_000,
    scan_timeout:       float                        = 30.0,
    excluded_dirs:      frozenset[str] | None        = None,
    excluded_abs_paths: frozenset[str]               = frozenset(),
    log_callback:       Callable[[str], None] | None = None,
    left_alone:         list[int] | None             = None,
) -> Generator[Path, None, None]:
    """Yield every regular file under root subject to hard safety limits.

    Symlinks and junctions are never followed. /proc and /sys are
    unconditionally excluded. Category folders directly inside root are
    skipped to prevent re-processing organised files. Sub-folders that are Git
    repositories are left alone as a whole. excluded_abs_paths: absolute
    directory paths (compared case-insensitively on Windows) that are always
    skipped -- used to protect the app's own folders.
    """
    if excluded_dirs is None:
        excluded_dirs = DEFAULT_EXCLUDED_DIRS
    if left_alone is None:
        left_alone = [0]

    abs_excluded = {os.path.normcase(p) for p in _ALWAYS_EXCLUDED_ABS | excluded_abs_paths}

    deadline:     float                  = time.monotonic() + scan_timeout
    dirs_visited: int                    = 0
    too_deep:     int                    = 0
    repos:        list[str]              = []
    stack:        list[tuple[str, int]]  = [(str(root.resolve()), 0)]

    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    try:
        while stack:
            if time.monotonic() >= deadline:
                log(f"[TIMEOUT]  Scan stopped after {scan_timeout:.0f}s -- "
                    f"{_plural(dirs_visited, 'folder', 'folders')} scanned. "
                    "Files in the remaining folders are not part of this run.")
                return

            current_str, depth = stack.pop()
            dirs_visited += 1

            if dirs_visited > max_dirs:
                log(f"[LIMIT]  More than {max_dirs:,} folders -- scan stopped. "
                    "Files in the remaining folders are not part of this run.")
                return

            try:
                with os.scandir(current_str) as it:
                    entries = list(it)
            except PermissionError:
                log(f"[SKIP]  Permission denied: {current_str}")
                continue
            except OSError as exc:
                log(f"[SKIP]  OS error reading {current_str}: {exc}")
                continue

            for entry in entries:
                try:
                    if _is_link(entry):
                        continue
                    is_file = entry.is_file(follow_symlinks=False)
                    is_dir  = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue

                if is_file:
                    if _keep_file(entry, include_hidden, left_alone):
                        yield Path(entry.path)
                elif is_dir:
                    hidden, system = _entry_flags(entry)
                    # Hidden+system folders are OS internals ($RECYCLE.BIN, System
                    # Volume Information). System alone is set on ordinary folders
                    # with a custom icon, so that is not a reason to skip.
                    if hidden and (system or not include_hidden):
                        continue
                    if entry.name in excluded_dirs:
                        continue
                    if depth == 0 and entry.name in _CATEGORY_NAMES:
                        continue
                    if os.path.normcase(entry.path) in abs_excluded:
                        continue
                    if os.path.exists(os.path.join(entry.path, ".git")):
                        repos.append(entry.name)
                        continue
                    if depth + 1 > max_depth:
                        too_deep += 1
                        continue
                    stack.append((entry.path, depth + 1))
    finally:
        # Summaries instead of one log line per folder.
        if too_deep:
            log(f"[DEPTH]  {_plural(too_deep, 'folder', 'folders')} deeper than "
                f"max depth {max_depth} were not scanned.")
        if repos:
            shown = ", ".join(repos[:5]) + (" ..." if len(repos) > 5 else "")
            log(f"[SKIP]  {_plural(len(repos), 'Git repository', 'Git repositories')} "
                f"left alone: {shown}")


def _iter_files_top_level(
    root: Path, include_hidden: bool, left_alone: list[int],
) -> Generator[Path, None, None]:
    """Yield the regular files directly inside root (no recursion)."""
    with os.scandir(str(root)) as it:
        for entry in it:
            try:
                if _is_link(entry) or not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if _keep_file(entry, include_hidden, left_alone):
                yield Path(entry.path)


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
    """Scan folder and return a ScanResult with file plans and duplicate groups.

    progress_callback receives (done, 1000): planning is the first 30 %,
    duplicate detection the remaining 70 %.
    """
    result = ScanResult()

    if not folder.exists():
        result.errors.append(f"Folder does not exist: {folder}")
        return result
    if not folder.is_dir():
        result.errors.append(f"Path is not a directory: {folder}")
        return result

    # Work on the resolved path throughout, so "already placed" comparisons and
    # destinations agree with the paths the scanner yields (junctions, subst
    # drives, relative or differently spelled paths).
    try:
        root = folder.resolve()
    except OSError as exc:
        result.errors.append(f"Could not resolve {folder}: {exc}")
        return result

    # Self-protection: settings, history, staging and the program code are never
    # touched. A folder that merely contains the exe is organised normally; only
    # the exe itself is skipped (protected_files below).
    protected = protected_dirs()
    for d in protected:
        if is_inside(root, d):
            result.errors.append(
                f"{root} belongs to Simple Organizer itself (program, settings or "
                "history) and is never organised.")
            return result

    try:
        active_rules = load_rules()
    except RulesReadError as exc:
        result.errors.append(
            f"{exc} -- scan stopped so no file is sorted without your rules. "
            "Try again in a moment.")
        return result

    def report(fraction: float) -> None:
        if progress_callback:
            progress_callback(round(fraction * 1000), 1000)

    def note(msg: str) -> None:
        result.notes.append(msg)
        if status_callback:
            status_callback(msg)

    if status_callback:
        status_callback("Collecting files...")

    left_alone = [0]
    try:
        if recursive:
            all_files: list[Path] = list(
                _iter_files_recursive(
                    root=root,
                    include_hidden=include_hidden,
                    max_depth=max_depth,
                    max_dirs=max_dirs,
                    scan_timeout=scan_timeout,
                    excluded_dirs=excluded_dirs,
                    excluded_abs_paths=frozenset(str(d) for d in protected),
                    log_callback=note,
                    left_alone=left_alone,
                )
            )
        else:
            all_files = list(_iter_files_top_level(root, include_hidden, left_alone))
    except PermissionError as exc:
        result.errors.append(f"Permission denied reading {root}: {exc}")
        return result
    except OSError as exc:
        result.errors.append(f"Could not read {root}: {exc}")
        return result

    own_files = protected_files()
    if own_files:
        all_files = [f for f in all_files if os.path.normcase(str(f)) not in own_files]

    if left_alone[0]:
        result.notes.append(
            f"[SKIP]  {_plural(left_alone[0], 'file', 'files')} left alone: system files, "
            "shortcuts, temporary files or downloads that are still in progress.")

    result.total_files = len(all_files)
    if result.total_files == 0:
        return result

    unsafe_targets: set[str] = set()
    # target folder -> problem (None = fine); checked once per folder, not per file
    target_problems: dict[Path, str | None] = {}
    blocked: dict[Path, int] = defaultdict(int)
    last_pct = -1

    for idx, file_path in enumerate(all_files, start=1):
        pct = idx * 100 // result.total_files
        if pct != last_pct:   # at most ~100 UI updates, however many files there are
            last_pct = pct
            report(0.3 * idx / result.total_files)
            if status_callback:
                status_callback(f"Scanning: {idx} / {result.total_files} files ({pct}%)")

        try:
            rule_category = apply_rules(file_path, active_rules) if active_rules else None
            if rule_category and not _is_safe_rule_target(root, rule_category):
                if rule_category not in unsafe_targets:
                    unsafe_targets.add(rule_category)
                    result.errors.append(
                        f"Rule target '{rule_category}' is not a valid folder inside the "
                        f"scanned folder -- rule ignored.")
                rule_category = None
            category = rule_category if rule_category else get_category(file_path)

            if use_subcategories and not rule_category:
                sub = get_subcategory(file_path, category)
                if sub:
                    target_dir  = root / category / sub
                    display_cat = f"{category}/{sub}"
                else:
                    target_dir  = root / category
                    display_cat = category
            else:
                target_dir  = root / category
                display_cat = category

            if target_dir not in target_problems:
                target_problems[target_dir] = _target_problem(root, target_dir)
            if target_problems[target_dir]:
                blocked[target_dir] += 1
                continue

            destination    = target_dir / file_path.name
            already_placed = (file_path.parent == target_dir)
            try:
                size = file_path.stat().st_size
            except OSError:
                size = 0
            if not already_placed:
                result.total_bytes += size

            result.plans.append(FilePlan(
                source=file_path,
                destination=destination,
                category=display_cat,
                skipped=already_placed,
                size=size,
                root=root,
            ))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Error processing {file_path.name}: {exc}")

    for target_dir, count in blocked.items():
        result.errors.append(
            f"{_plural(count, 'file', 'files')} not planned: {target_problems[target_dir]}.")

    if status_callback:
        status_callback("Detecting duplicates...")
    report(0.3)

    skipped_large: list[Path] = []
    skipped_cloud: list[Path] = []
    hard_links:    list[Path] = []
    dup_last = [-1]

    def dup_progress(current: int, total: int) -> None:
        pct = current * 100 // total if total else 100
        if pct != dup_last[0]:
            dup_last[0] = pct
            report(0.3 + 0.7 * current / total if total else 1.0)

    try:
        result.duplicate_groups = find_duplicates(
            files=all_files,
            progress_callback=dup_progress,
            skipped_large=skipped_large,
            deadline=time.monotonic() + max(60.0, scan_timeout * 10),
            log_callback=note,
            skipped_cloud=skipped_cloud,
            hard_links=hard_links,
        )
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Duplicate detection error: {exc}")
    if skipped_cloud:
        result.notes.append(
            f"[SKIP]  {_plural(len(skipped_cloud), 'online-only cloud file', 'online-only cloud files')} "
            "(e.g. OneDrive) not checked for duplicates, so nothing is downloaded.")
    if skipped_large:
        result.notes.append(
            f"[SKIP]  {_plural(len(skipped_large), 'file', 'files')} larger than "
            f"{DEFAULT_MAX_HASH_SIZE // (1024 * 1024)} MB not checked for duplicates.")
    if hard_links:
        result.notes.append(
            f"[SKIP]  {_plural(len(hard_links), 'hard link', 'hard links')} to a file already "
            "checked -- the same file, not a duplicate.")

    report(1.0)
    if status_callback:
        status_callback("Scan complete.")

    return result


# ---------------------------------------------------------------------------
# Organising
# ---------------------------------------------------------------------------

def _mkdir_tracked(directory: Path, created: list[str]) -> None:
    """mkdir -p that records every folder it had to create (for a clean undo)."""
    missing: list[Path] = []
    p = directory
    while not p.exists() and p.parent != p:
        missing.append(p)
        p = p.parent
    directory.mkdir(parents=True, exist_ok=True)
    for d in reversed(missing):
        s = str(d)
        if s not in created:
            created.append(s)


def _remove_created_dirs(dirs: object) -> None:
    """Remove folders a run created, deepest first, if they are empty again.

    os.rmdir only ever succeeds on an empty folder, so no file can be lost.
    """
    if not isinstance(dirs, list):
        return
    for d in sorted({str(x) for x in dirs}, key=len, reverse=True):
        try:
            os.rmdir(d)
        except OSError:
            pass


def organise_files(
    plans:             list[FilePlan],
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
    staging:           bool = False,
    scheduled:         bool = False,
) -> list[str]:
    """Execute planned file moves. Files are NEVER deleted or overwritten.

    scheduled marks the history run as an automatic one; automatic and manual
    runs are limited separately, so the scheduler cannot push manual runs out
    of the undo history.
    """
    _ensure_data_dir()

    errors:       list[str]           = []
    actionable                        = [p for p in plans if not p.skipped]
    total                             = len(actionable)
    timestamp                         = _now_iso()
    move_log:     list[dict[str, str]] = []
    created_dirs: list[str]           = []

    # Journal: written every JOURNAL_FLUSH_SECONDS and at the end.
    run_path: Path | None = None
    if staging:
        manifest_ts, staged_before = _read_staging_manifest(log_callback)
        manifest_ts = manifest_ts or timestamp
    journal_failed = False

    def write_journal() -> None:
        nonlocal run_path, journal_failed
        if not move_log:
            return
        if staging:
            try:
                _write_staging_manifest(manifest_ts, staged_before + move_log)
            except Exception as exc:  # noqa: BLE001
                if not journal_failed:
                    journal_failed = True
                    err = (f"[ERROR]  Could not write the staging manifest ({exc}). "
                           f"Staged files are in {STAGING_DIR}.")
                    errors.append(err)
                    if log_callback:
                        log_callback(err)
        else:
            run_path = _write_history_run({
                "timestamp":    timestamp,
                "scheduled":    scheduled,
                "moves":        [{"src": m["src"], "dst": m["dst"]} for m in move_log],
                "created_dirs": created_dirs,
            }, log_callback, path=run_path, scheduled=scheduled)

    last_flush = time.monotonic()
    left_in_cloud = 0

    for idx, plan in enumerate(actionable, start=1):
        if progress_callback:
            progress_callback(idx, total)

        try:
            if staging:
                # The staging area is outside the scanned folder. Moving an
                # online-only cloud file (OneDrive...) out of its sync folder
                # makes Windows download it first, so such files stay put.
                if is_cloud_placeholder(plan.source.stat()):
                    left_in_cloud += 1
                    if log_callback:
                        log_callback(f"[SKIP]  {plan.source.name} is online-only (e.g. OneDrive) "
                                     "-- not staged, so it is not downloaded.")
                    continue
                actual_dest = STAGING_DIR / Path(plan.category) / plan.source.name
                actual_dest.parent.mkdir(parents=True, exist_ok=True)
            else:
                actual_dest = plan.destination
                _mkdir_tracked(actual_dest.parent, created_dirs)

            safe_dest = resolve_conflict(actual_dest)
            safe_move(plan.source, safe_dest)

            move_log.append({
                "src":       str(plan.source),
                "dst":       str(safe_dest),
                "final_dst": str(plan.destination),
                "root":      str(plan.root) if plan.root else "",
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
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Unexpected error for {plan.source.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)

        if time.monotonic() - last_flush >= JOURNAL_FLUSH_SECONDS:
            write_journal()
            last_flush = time.monotonic()

    # Only written when at least one file was actually moved / staged.
    write_journal()
    if left_in_cloud and log_callback:
        log_callback(f"[WARN]  {_plural(left_in_cloud, 'online-only file was', 'online-only files were')} "
                     "not staged. Organise without staging mode to sort them without downloading.")
    return errors


# ---------------------------------------------------------------------------
# Undo history
# ---------------------------------------------------------------------------

# The newest history/run_*.json is "the last run" -- there is no separate
# last_run.json any more, so "Undo last" and History can never disagree.
#
# Since v3.4.4 run files are named run_<sequence>_<UTC time>[_auto].json and
# ordered by the sequence number, never by the clock: a wrong or jumping system
# clock (e.g. dual boot) cannot make "Undo last" pick an older run. Files from
# older versions (run_<UTC time>.json) sort before all numbered ones.

_SEQ_NAME = re.compile(r"^(?:run|undone)_(\d{8})_")


def _run_seq(path: Path) -> int | None:
    match = _SEQ_NAME.match(path.name)
    return int(match.group(1)) if match else None


def _run_sort_key(path: Path) -> tuple[int, int, str]:
    seq = _run_seq(path)
    return (1, seq, path.name) if seq is not None else (0, 0, path.name)


def _sorted_runs(directory: Path | None = None, prefix: str = "run_") -> list[Path]:
    """History files in directory (default HISTORY_DIR), oldest first."""
    directory = directory or HISTORY_DIR
    return sorted(directory.glob(f"{prefix}*.json"), key=_run_sort_key)


def _is_scheduled_run(path: Path) -> bool:
    return path.stem.endswith("_auto")


def _next_seq() -> int:
    seqs = [_run_seq(f) for f in (*HISTORY_DIR.glob("run_*.json"), *HISTORY_DIR.glob("undone_*.json"),
                                  *TRIMMED_DIR.glob("run_*.json"))]
    return max((s for s in seqs if s is not None), default=0) + 1


def _trim_runs(log_callback: Callable[[str], None] | None = None) -> None:
    """Keep the newest MAX_HISTORY manual and MAX_HISTORY scheduled runs undoable.

    Older runs are moved to TRIMMED_DIR rather than deleted, so undoing a
    remaining run can still follow a file that one of them moved again; only
    the oldest beyond MAX_TRIMMED are deleted.
    """
    runs = _sorted_runs()
    for scheduled in (False, True):
        excess = [r for r in runs if _is_scheduled_run(r) == scheduled][:-MAX_HISTORY]
        for old in excess:
            try:
                TRIMMED_DIR.mkdir(parents=True, exist_ok=True)
                old.replace(TRIMMED_DIR / old.name)
            except OSError as exc:
                if log_callback:
                    log_callback(f"[WARN]  Could not trim old history file: {exc}")
        if excess and not scheduled and log_callback:
            log_callback(f"[WARN]  {_plural(len(excess), 'old run', 'old runs')} dropped from the "
                         f"undo history -- the newest {MAX_HISTORY} manual runs stay undoable.")
    if TRIMMED_DIR.exists():
        for old in _sorted_runs(TRIMMED_DIR)[:-MAX_TRIMMED]:
            try:
                old.unlink()
            except OSError:
                pass


def _write_history_run(
    run_data: dict,
    log_callback: Callable[[str], None] | None = None,
    when: datetime | None = None,
    path: Path | None = None,
    scheduled: bool = False,
) -> Path | None:
    """Write a history run file and return its path.

    Without path a new numbered file is created and old runs are trimmed; with
    path that file is rewritten (journal flush). when is only given when a
    run from an old version is migrated: it keeps the old naming so it sorts
    among the old runs.
    """
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        new = path is None
        if path is None:
            ts = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S_%f")
            if when is not None:
                path = resolve_conflict(HISTORY_DIR / f"run_{ts}.json")
            else:
                suffix = "_auto" if scheduled else ""
                path = resolve_conflict(HISTORY_DIR / f"run_{_next_seq():08d}_{ts}{suffix}.json")
        atomic_write_text(path, json.dumps(run_data, indent=2))
        if new:
            _trim_runs(log_callback)
        return path
    except Exception as exc:
        if log_callback:
            log_callback(f"[WARN]  Failed to write history: {exc}")
        return None if path is None or not path.exists() else path


_legacy_migrated = False


def _migrate_legacy_last_run() -> None:
    """Fold a last_run.json written by v3.4.0 or older into history, then remove it.

    Older versions wrote every run to both files, so usually the run is already
    in history and the legacy file can simply be dropped. Also removes stale
    undone_*.json files that older versions left in the data directory.
    Only old versions create these files, so this runs once per app start.
    """
    global _legacy_migrated
    if _legacy_migrated:
        return
    _legacy_migrated = True
    for stale in DATA_DIR.glob("undone_*.json"):
        try:
            stale.unlink()
        except OSError:
            pass
    if not LAST_RUN_FILE.exists():
        return
    try:
        data = json.loads(LAST_RUN_FILE.read_text(encoding="utf-8"))
        ts   = data.get("timestamp", "")
        known = False
        # Also check undone_* so a run already undone via History is not revived.
        for f in [*HISTORY_DIR.glob("run_*.json"), *HISTORY_DIR.glob("undone_*.json")]:
            try:
                if json.loads(f.read_text(encoding="utf-8")).get("timestamp") == ts:
                    known = True
                    break
            except Exception:  # noqa: BLE001
                continue
        if not known and data.get("moves"):
            try:
                when = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                when = None
            _write_history_run(data, when=when)
        LAST_RUN_FILE.unlink()
    except Exception:  # noqa: BLE001
        pass


def _trim_undone_history() -> None:
    """Keep only the newest MAX_HISTORY undone_*.json files."""
    for old in _sorted_runs(prefix="undone_")[:-MAX_HISTORY]:
        try:
            old.unlink()
        except OSError:
            pass


def _newest_run_file() -> Path | None:
    _migrate_legacy_last_run()
    if not HISTORY_DIR.exists():
        return None
    runs = _sorted_runs()
    return runs[-1] if runs else None


def list_undo_history() -> list[dict]:
    """Return metadata for all undoable runs, newest first."""
    _migrate_legacy_last_run()
    if not HISTORY_DIR.exists():
        return []
    runs   = list(reversed(_sorted_runs()))
    result: list[dict] = []
    for f in runs:
        try:
            data  = json.loads(f.read_text(encoding="utf-8"))
            ts    = data.get("timestamp", "")
            count = len(data.get("moves", []))
            scheduled = _is_scheduled_run(f)
            try:
                # Stored in UTC; shown in the computer's local time.
                dt  = datetime.fromisoformat(ts).astimezone()
                lbl = dt.strftime("%b %d %H:%M") + f"  -  {count} file(s)"
            except Exception:
                lbl = f"{f.stem}  -  {count} file(s)"
            if scheduled:
                lbl += "  -  automatic"
            result.append({
                "id":         f.stem,
                "timestamp":  ts,
                "move_count": count,
                "file_path":  f,
                "label":      lbl,
                "scheduled":  scheduled,
            })
        except Exception:
            pass
    return result


def _later_moves(run_file: Path) -> dict[str, str]:
    """Map source -> destination of every move recorded by runs newer than run_file.

    Keys are os.path.normcase'd. If several newer runs moved a file away from
    the same path, the earliest of them wins -- that is the move that took the
    file away from where run_file left it.
    """
    later: dict[str, str] = {}
    own_key = _run_sort_key(run_file)
    newer = [f for f in (*_sorted_runs(), *_sorted_runs(TRIMMED_DIR)) if _run_sort_key(f) > own_key]
    for f in sorted(newer, key=_run_sort_key):
        try:
            moves = json.loads(f.read_text(encoding="utf-8")).get("moves", [])
        except Exception:  # noqa: BLE001
            continue
        for m in moves:
            try:
                later.setdefault(os.path.normcase(str(m["src"])), str(m["dst"]))
            except (KeyError, TypeError):
                continue
    return later


def _follow_moves(path: Path, later: dict[str, str]) -> Path | None:
    """Return where the file that was at path is now, following newer runs."""
    seen: set[str] = set()
    current = path
    while not current.exists():
        key = os.path.normcase(str(current))
        if key in seen or key not in later:
            return None
        seen.add(key)
        current = Path(later[key])
    return current


def _undo_run_file(
    run_file:          Path,
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
) -> list[str]:
    """Reverse all moves in run_file.

    When everything is restored the file is renamed to undone_*. Moves that
    failed stay in the run file, so the user can fix the cause and undo again.
    A file that a newer run has moved on is followed to where it is now and
    restored from there, so runs can be undone in any order.
    """
    errors: list[str] = []
    later: dict[str, str] | None = None   # built only when a file is missing

    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    try:
        data  = json.loads(run_file.read_text(encoding="utf-8"))
        moves = list(reversed(data.get("moves", [])))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Failed to read {run_file.name}: {exc}")
        log(f"[ERROR]  {errors[-1]}")
        return errors

    total = len(moves)
    failed: list[dict] = []

    for idx, entry in enumerate(moves, start=1):
        if progress_callback:
            progress_callback(idx, total)

        try:
            src_path = Path(entry["src"])
            dst_path = Path(entry["dst"])
        except (KeyError, TypeError):
            log(f"[SKIP]  Unreadable history entry skipped: {entry!r}")
            continue

        followed = False
        if not dst_path.exists():
            if later is None:
                later = _later_moves(run_file)
            current = _follow_moves(dst_path, later)
            if current is None:
                log(f"[SKIP]  {dst_path.name} not found at {dst_path.parent} -- it was moved "
                    "or deleted outside Simple Organizer; skipping.")
                continue
            dst_path, followed = current, True

        try:
            src_path.parent.mkdir(parents=True, exist_ok=True)
            safe_src = resolve_conflict(src_path)
            safe_move(dst_path, safe_src)
            msg = f"[UNDONE]  {dst_path.name}  ->  {safe_src.parent.name}/"
            if safe_src.name != src_path.name:
                msg += f"  (renamed -> {safe_src.name})"
            if followed:
                msg += "  (found where a newer run had moved it)"
            log(msg)
            continue
        except PermissionError as exc:
            err = f"[ERROR]  Permission denied restoring {dst_path.name}: {exc}"
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Unexpected error restoring {dst_path.name}: {exc}"
        errors.append(err)
        failed.append(entry)
        log(err)

    # Category folders this run created are removed again if they are empty now.
    _remove_created_dirs(data.get("created_dirs"))

    if failed:
        data["moves"] = list(reversed(failed))
        try:
            atomic_write_text(run_file, json.dumps(data, indent=2))
            log(f"[WARN]  {_plural(len(failed), 'file', 'files')} could not be restored and "
                "stay in the history -- fix the problem and undo this run again.")
        except Exception as exc:  # noqa: BLE001
            log(f"[WARN]  Could not update {run_file.name}: {exc}")
        return errors

    # Keeps the run's number, so the sequence never goes backwards.
    undone_path = resolve_conflict(run_file.with_name("undone_" + run_file.name[len("run_"):]))
    try:
        run_file.rename(undone_path)
    except Exception as exc:  # noqa: BLE001
        log(f"[WARN]  Could not rename {run_file.name}: {exc}")
    _trim_undone_history()

    return errors


def undo_last_run(
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
) -> list[str]:
    """Reverse every move of the newest history run. Files are NEVER deleted."""
    run_file = _newest_run_file()
    if run_file is None:
        if log_callback:
            log_callback("[WARN]  No last run record found.")
        return ["No run history found -- nothing to undo."]
    return _undo_run_file(run_file, progress_callback, log_callback)


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

def _write_staging_manifest(timestamp: str, entries: list[dict]) -> None:
    STAGING_MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        STAGING_MANIFEST_FILE,
        json.dumps({"timestamp": timestamp, "entries": entries}, indent=2),
    )


def _staged_file_exists(entry: object) -> bool:
    return isinstance(entry, dict) and bool(entry.get("dst")) and Path(entry["dst"]).exists()


def _read_staging_manifest(
    log_callback: Callable[[str], None] | None = None,
) -> tuple[str | None, list[dict]]:
    """Return (timestamp, entries) of the current manifest, or (None, []) if there is none.

    Entries whose staged file no longer exists are dropped. An unreadable
    manifest is moved aside instead of being overwritten.
    """
    if not STAGING_MANIFEST_FILE.exists():
        return None, []
    try:
        data = json.loads(STAGING_MANIFEST_FILE.read_text(encoding="utf-8"))
        entries = [e for e in data.get("entries", []) if _staged_file_exists(e)]
        return data.get("timestamp"), entries
    except Exception as exc:  # noqa: BLE001
        backup = STAGING_MANIFEST_FILE.with_name(
            f"staging_manifest_corrupt_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json")
        try:
            STAGING_MANIFEST_FILE.replace(backup)
        except OSError:
            pass
        if log_callback:
            log_callback(f"[WARN]  Staging manifest was unreadable ({exc}); "
                         f"backed up to {backup.name}.")
        return None, []


def _finish_staging(
    timestamp:    str,
    failed:       list[dict],
    log_callback: Callable[[str], None] | None = None,
) -> None:
    """Delete the manifest if everything succeeded, else keep only failed entries."""
    try:
        if failed:
            _write_staging_manifest(timestamp, failed)
            if log_callback:
                log_callback(f"[WARN]  {len(failed)} file(s) are still staged -- "
                             "fix the problem and try again.")
        else:
            STAGING_MANIFEST_FILE.unlink(missing_ok=True)
        _remove_empty_staging_dirs()
    except Exception as exc:  # noqa: BLE001
        if log_callback:
            log_callback(f"[WARN]  Could not clean staging area: {exc}")


def commit_staging(
    progress_callback: Callable[[int, int], None] | None = None,
    log_callback:      Callable[[str], None]       | None = None,
) -> list[str]:
    """Move staged files to final destinations. Writes a history run for undo."""
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

    total        = len(entries)
    timestamp    = _now_iso()
    move_log:     list[dict[str, str]] = []
    failed:       list[dict]           = []
    created_dirs: list[str]            = []
    run_path:     Path | None          = None
    last_flush   = time.monotonic()

    def write_journal() -> None:
        nonlocal run_path
        if move_log:
            run_path = _write_history_run(
                {"timestamp": timestamp, "moves": move_log, "created_dirs": created_dirs},
                log_callback, path=run_path)

    for idx, entry in enumerate(entries, start=1):
        if progress_callback:
            progress_callback(idx, total)

        try:
            staged_path = Path(entry["dst"])
            final_dst   = Path(entry["final_dst"])
            original    = entry["src"]
        except (KeyError, TypeError):
            if log_callback:
                log_callback(f"[SKIP]  Unreadable staging entry skipped: {entry!r}")
            continue

        if not staged_path.exists():
            if log_callback:
                log_callback(f"[SKIP]  {staged_path.name} not in staging -- skipping.")
            continue

        root = entry.get("root") if isinstance(entry, dict) else None
        if root and not Path(root).is_dir():
            err = (f"[ERROR]  {staged_path.name}: the folder {root} no longer exists "
                   "(renamed, moved or deleted) -- the file stays staged.")
            errors.append(err)
            failed.append(entry)
            if log_callback:
                log_callback(err)
            continue

        try:
            _mkdir_tracked(final_dst.parent, created_dirs)
            safe_final = resolve_conflict(final_dst)
            safe_move(staged_path, safe_final)
            move_log.append({"src": original, "dst": str(safe_final)})
            msg = f"[COMMITTED]  {staged_path.name}  ->  {safe_final.parent.name}/"
            if safe_final.name != staged_path.name:
                msg += f"  (renamed -> {safe_final.name})"
            if log_callback:
                log_callback(msg)
        except PermissionError as exc:
            err = f"[ERROR]  Permission denied committing {staged_path.name}: {exc}"
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Unexpected error committing {staged_path.name}: {exc}"
        else:
            err = ""
        if err:
            errors.append(err)
            failed.append(entry)
            if log_callback:
                log_callback(err)

        if time.monotonic() - last_flush >= JOURNAL_FLUSH_SECONDS:
            write_journal()
            last_flush = time.monotonic()

    # Only written when at least one file was actually moved.
    write_journal()

    _finish_staging(data.get("timestamp", timestamp), failed, log_callback)
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
    failed: list[dict] = []

    for idx, entry in enumerate(entries, start=1):
        if progress_callback:
            progress_callback(idx, total)

        try:
            staged_path  = Path(entry["dst"])
            original_src = Path(entry["src"])
        except (KeyError, TypeError):
            if log_callback:
                log_callback(f"[SKIP]  Unreadable staging entry skipped: {entry!r}")
            continue

        if not staged_path.exists():
            if log_callback:
                log_callback(f"[SKIP]  {staged_path.name} not in staging -- skipping.")
            continue

        root = entry.get("root") if isinstance(entry, dict) else None
        if root and not Path(root).is_dir():
            err = (f"[ERROR]  {staged_path.name}: the folder {root} no longer exists "
                   "(renamed, moved or deleted) -- the file stays staged.")
            errors.append(err)
            failed.append(entry)
            if log_callback:
                log_callback(err)
            continue

        try:
            original_src.parent.mkdir(parents=True, exist_ok=True)
            safe_src = resolve_conflict(original_src)
            safe_move(staged_path, safe_src)
            msg = f"[REVERTED]  {staged_path.name}  ->  {safe_src.parent}/"
            if safe_src.name != original_src.name:
                msg += f"  (renamed -> {safe_src.name})"
            if log_callback:
                log_callback(msg)
            continue
        except PermissionError as exc:
            err = f"[ERROR]  Permission denied reverting {staged_path.name}: {exc}"
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Unexpected error reverting {staged_path.name}: {exc}"
        errors.append(err)
        failed.append(entry)
        if log_callback:
            log_callback(err)

    # entries were processed newest-first; store the remainder in original order.
    timestamp = data.get("timestamp", _now_iso())
    _finish_staging(timestamp, list(reversed(failed)), log_callback)
    return errors


def _remove_empty_staging_dirs() -> None:
    """Remove empty directories under STAGING_DIR, bottom-up. Never removes files."""
    if not STAGING_DIR.exists():
        return
    # topdown=False visits children before parents, so nested empty folders
    # (e.g. staging/Images/Photos/) are removed before their parent is tried.
    for dirpath, _dirnames, _filenames in os.walk(STAGING_DIR, topdown=False):
        try:
            os.rmdir(dirpath)   # fails harmlessly if the folder is not empty
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Duplicate trash
# ---------------------------------------------------------------------------

def _existing_ancestor(path: Path) -> Path:
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def _mount_point(path: Path) -> Path:
    """Return the top directory of the file system that holds path."""
    dev = path.stat().st_dev
    current = path.parent
    while current.parent != current:
        try:
            if current.parent.stat().st_dev != dev:
                break
        except OSError:
            break
        current = current.parent
    return current


def _trash_candidates(resolved: Path) -> list[tuple[Path, Path | None]]:
    """Trash folders to try for resolved, best first, as (trash_dir, topdir).

    topdir is None for the home trash. Following the freedesktop.org Trash
    spec, a file on another file system (USB stick, second partition) goes to
    that volume's own trash -- $topdir/.Trash/$uid if an admin prepared a
    shared .Trash (directory, sticky bit, not a symlink), else
    $topdir/.Trash-$uid -- so it is never copied across devices. The home
    trash is the last resort, as the spec allows.
    """
    home_trash = xdg_base_dir("XDG_DATA_HOME", Path.home() / ".local" / "share") / "Trash"
    try:
        same_device = resolved.stat().st_dev == _existing_ancestor(home_trash).stat().st_dev
    except OSError:
        same_device = True
    if same_device:
        return [(home_trash, None)]

    top = _mount_point(resolved)
    uid = getattr(os, "getuid", lambda: 0)()
    candidates: list[tuple[Path, Path | None]] = []
    shared = top / ".Trash"
    try:
        st = os.lstat(shared)
        if stat.S_ISDIR(st.st_mode) and st.st_mode & stat.S_ISVTX:
            candidates.append((shared / str(uid), top))
    except OSError:
        pass
    candidates.append((top / f".Trash-{uid}", top))
    candidates.append((home_trash, None))
    return candidates


def _trash_xdg(resolved: Path) -> None:
    """Move a file into an XDG Trash (freedesktop.org Trash spec 1.0).

    The .trashinfo file is created first with O_EXCL, as the spec requires, so
    two programs can never claim the same name; Path= is percent-encoded so
    names with spaces or umlauts can be restored by file managers.
    """
    last_error: OSError | None = None
    for trash_dir, top in _trash_candidates(resolved):
        try:
            trash_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            (trash_dir / "files").mkdir(mode=0o700, exist_ok=True)
            (trash_dir / "info").mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:   # read-only volume, no permission: try the next trash
            last_error = exc
            continue
        # A volume trash stores the path relative to the volume, so the entry
        # still restores when the drive is mounted somewhere else next time.
        original = resolved.relative_to(top).as_posix() if top else str(resolved)
        _trash_into(resolved, trash_dir, original)
        return
    raise OSError(f"no usable Trash folder: {last_error}")


def _trash_into(resolved: Path, trash_dir: Path, original: str) -> None:
    files_dir = trash_dir / "files"
    info_dir  = trash_dir / "info"
    stem, suffix = resolved.stem, resolved.suffix
    for counter in range(1000):
        name = resolved.name if counter == 0 else f"{stem}_{counter}{suffix}"
        info = info_dir / f"{name}.trashinfo"
        try:
            fd = os.open(info, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        dest = files_dir / name
        if dest.exists():
            os.close(fd)
            info.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("[Trash Info]\n"
                     f"Path={quote(original, safe='/')}\n"
                     f"DeletionDate={datetime.now():%Y-%m-%dT%H:%M:%S}\n")
        try:
            safe_move(resolved, dest)
        except Exception:
            info.unlink(missing_ok=True)
            raise
        return
    raise OSError("could not find a free name in the Trash")


def _trash_file_platform(path: Path, hwnd: int | None = None) -> None:
    """Move a single file to the system Trash/Recycle Bin.

    Uses platform-native methods only — no external packages required.
    hwnd (Windows) owns any dialog Windows shows, e.g. "too big for the
    Recycle Bin, delete permanently?", so it opens above the app instead of
    possibly behind it. Raises OSError or subprocess.CalledProcessError on failure.
    """
    if sys.platform == "win32":
        # Windows: SHFileOperation with FOF_ALLOWUNDO sends to Recycle Bin.
        import ctypes
        import ctypes.wintypes
        SHFileOperationW = ctypes.windll.shell32.SHFileOperationW  # type: ignore[attr-defined]

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd",                  ctypes.wintypes.HWND),
                ("wFunc",                 ctypes.wintypes.UINT),
                ("pFrom",                 ctypes.c_wchar_p),
                ("pTo",                   ctypes.c_wchar_p),
                ("fFlags",                ctypes.wintypes.WORD),
                ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
                ("hNameMappings",         ctypes.c_void_p),
                ("lpszProgressTitle",     ctypes.c_wchar_p),
            ]

        FO_DELETE           = 0x0003
        FOF_ALLOWUNDO       = 0x0040
        FOF_NOCONFIRMATION  = 0x0010
        FOF_SILENT          = 0x0004
        FOF_WANTNUKEWARNING = 0x4000
        DRIVE_REMOTE        = 4

        resolved = path.resolve()

        # Network shares / mapped drives have no Recycle Bin: Windows would
        # delete permanently. Refuse instead of breaking the "never delete" promise.
        root = resolved.anchor
        if root.startswith("\\\\?\\") and not root.upper().startswith("\\\\?\\UNC\\"):
            root = root[4:]   # long-path prefix on a local drive, e.g. \\?\C:\
        if root.startswith("\\\\") or \
                ctypes.windll.kernel32.GetDriveTypeW(root) == DRIVE_REMOTE:  # type: ignore[attr-defined]
            raise OSError("network drive has no Recycle Bin -- file left in place")

        # pFrom must be double-null-terminated
        src = str(resolved) + "\0\0"
        op  = SHFILEOPSTRUCTW()
        op.hwnd   = hwnd
        op.wFunc  = FO_DELETE
        op.pFrom  = src
        # FOF_WANTNUKEWARNING overrides FOF_NOCONFIRMATION when the file would be
        # destroyed instead of recycled (e.g. USB sticks without a Recycle Bin),
        # so the user gets a chance to cancel.
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_WANTNUKEWARNING
        result = SHFileOperationW(ctypes.byref(op))
        if result != 0:
            raise OSError(f"SHFileOperation failed with code {result}")
        if op.fAnyOperationsAborted:
            raise OSError("operation was cancelled -- file left in place")

    else:
        # Linux / macOS: try gio trash first (GNOME), then trash-put (trash-cli),
        # then fall back to a manual XDG Trash implementation.
        resolved = path.resolve()
        for command in (["gio", "trash"], ["trash-put"]):
            try:
                subprocess.run([*command, str(resolved)], check=True, capture_output=True)
                return
            except Exception:  # noqa: BLE001 -- tool missing or refused: try the next way
                pass
        _trash_xdg(resolved)


def trash_files(
    paths:         list[Path],
    log_callback:  Callable[[str], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    hwnd:          int | None = None,
) -> tuple[list[str], int]:
    """Move a list of files to the system Trash/Recycle Bin.

    Files are NEVER permanently deleted. hwnd: see _trash_file_platform.
    Returns (errors, trashed_count); files skipped as "not found" count as neither.
    """
    errors: list[str] = []
    total   = len(paths)
    trashed = 0

    for idx, path in enumerate(paths, start=1):
        if progress_callback:
            progress_callback(idx, total)

        if not path.exists():
            msg = f"[SKIP]  {path.name} — not found, already moved or deleted."
            if log_callback:
                log_callback(msg)
            continue

        try:
            _trash_file_platform(path, hwnd)
            trashed += 1
            if log_callback:
                log_callback(f"[TRASHED]  {path.name}  ({path.parent})")
        except Exception as exc:  # noqa: BLE001
            err = f"[ERROR]  Could not trash {path.name}: {exc}"
            errors.append(err)
            if log_callback:
                log_callback(err)

    return errors, trashed


def has_last_run() -> bool:
    """True if there is a run to undo. Only lists file names -- the UI calls
    this after every task, so it must not read the history files themselves."""
    return _newest_run_file() is not None


# (mtime_ns, size) of the manifest -> its entries; the UI asks after every task.
_manifest_cache: tuple[tuple[int, int], list] | None = None


def has_staging() -> bool:
    """True if at least one staged file is still waiting for Commit or Revert."""
    global _manifest_cache
    try:
        st = STAGING_MANIFEST_FILE.stat()
    except OSError:
        return False
    key = (st.st_mtime_ns, st.st_size)
    if _manifest_cache is None or _manifest_cache[0] != key:
        try:
            data = json.loads(STAGING_MANIFEST_FILE.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
            if not isinstance(entries, list):
                raise ValueError("entries is not a list")
        except Exception:  # noqa: BLE001
            return True   # unreadable: keep Commit/Revert enabled so the error is shown
        _manifest_cache = (key, entries)
    return any(_staged_file_exists(e) for e in _manifest_cache[1])
