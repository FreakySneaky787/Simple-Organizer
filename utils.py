"""
utils.py — Shared constants, category mappings, and helper utilities.
"""

import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# File category → extension mapping
# ---------------------------------------------------------------------------

CATEGORY_MAP: dict[str, list[str]] = {
    "Images":    ["jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif",
                  "svg", "ico", "psd", "xcf", "kra", "raw", "cr2", "nef", "arw", "dng"],
    "Documents": ["pdf", "docx", "doc", "txt", "odt", "rtf", "xlsx", "xls",
                  "ods", "pptx", "ppt", "odp", "pps", "ppsx", "csv", "md"],
    "Archives":  ["zip", "tar", "gz", "rar", "7z", "bz2", "xz", "tgz"],
    "Videos":    ["mp4", "mkv", "mov", "avi", "wmv", "flv", "webm", "m4v", "mpeg", "mpg"],
    "Music":     ["mp3", "wav", "flac", "aac", "ogg", "wma", "m4a", "opus", "aiff"],
    "Code":      ["py", "ipynb", "js", "ts", "jsx", "tsx", "html", "htm", "css",
                  "cpp", "c", "h", "java", "rb", "go", "rs", "php", "sh", "bash",
                  "json", "yaml", "yml", "toml", "xml", "sql", "r", "swift", "kt", "dart"],
    "Others":    [],  # catch-all — any extension not matched above
}

# Build reverse lookup: extension → category
EXT_TO_CATEGORY: dict[str, str] = {}
for _category, _extensions in CATEGORY_MAP.items():
    if _category == "Others":
        continue
    for _ext in _extensions:
        EXT_TO_CATEGORY[_ext.lower()] = _category


# ---------------------------------------------------------------------------
# Sub-category mapping  (category → extension → sub-folder name)
# Applies only when the user enables "Use sub-categories" in the UI.
# ---------------------------------------------------------------------------

SUBCATEGORY_MAP: dict[str, dict[str, str]] = {
    "Images": {
        # Standard photos / raster
        "jpg":  "Photos", "jpeg": "Photos", "png":  "Photos",
        "webp": "Photos", "bmp":  "Photos", "tiff": "Photos", "tif": "Photos",
        # Animated
        "gif":  "GIFs",
        # Vector
        "svg":  "Vector",
        # Icons
        "ico":  "Icons",
        # Editing / layered (Photoshop, GIMP, Krita, Paint.NET)
        "psd":  "Editing", "xcf": "Editing", "kra": "Editing",
        # Camera raw formats
        "raw":  "Raw", "cr2": "Raw", "nef": "Raw", "arw": "Raw", "dng": "Raw",
    },
    "Documents": {
        "pdf":  "PDFs",
        # Word processing
        "docx": "Word",  "doc": "Word",  "odt": "Word",  "rtf": "Word",
        # Spreadsheets
        "xlsx": "Spreadsheets", "xls": "Spreadsheets",
        "ods":  "Spreadsheets", "csv": "Spreadsheets",
        # Presentations
        "pptx": "Presentations", "ppt":  "Presentations",
        "odp":  "Presentations", "pps":  "Presentations", "ppsx": "Presentations",
        # Plain text
        "txt":  "Text", "md": "Text",
    },
    "Archives": {
        "zip": "ZIP",
        "rar": "RAR",
        "7z":  "7Zip",
        "tar": "TAR", "gz": "TAR", "tgz": "TAR", "bz2": "TAR", "xz": "TAR",
    },
    "Videos": {
        "mp4":  "MP4",  "m4v":  "MP4",
        "mkv":  "MKV",
        "avi":  "AVI",
        "mov":  "MOV",
        "wmv":  "WMV",
        "webm": "WebM",
        "flv":  "FLV",
        "mpeg": "MPEG", "mpg": "MPEG",
    },
    "Music": {
        # Lossless
        "flac": "Lossless", "wav": "Lossless", "aiff": "Lossless",
        # Lossy
        "mp3":  "MP3",
        "aac":  "AAC",  "m4a":  "AAC",
        "ogg":  "OGG",  "opus": "OGG",
        "wma":  "WMA",
    },
    "Code": {
        "py": "Python", "ipynb": "Python",
        "js": "JavaScript", "ts": "JavaScript",
        "jsx": "JavaScript", "tsx": "JavaScript",
        "html": "Web", "htm": "Web", "css": "Web",
        "java": "Java", "kt": "Java",
        "cpp": "C_CPP", "c": "C_CPP", "h": "C_CPP",
        "go":    "Go",
        "rs":    "Rust",
        "rb":    "Ruby",
        "php":   "PHP",
        "swift": "Swift",
        "dart":  "Dart",
        "sh": "Shell", "bash": "Shell",
        "json": "Config", "yaml": "Config", "yml": "Config",
        "toml": "Config", "xml": "Config",
        "sql":   "SQL",
        "r":     "R",
    },
}

# Flat set of all subcategory folder names (used to avoid re-processing).
ALL_SUBCATEGORY_NAMES: frozenset[str] = frozenset(
    sub for subs in SUBCATEGORY_MAP.values() for sub in subs.values()
)


def get_category(file_path: Path) -> str:
    """Return the top-level target category name for a given file path."""
    suffix = file_path.suffix.lstrip(".").lower()
    if not suffix:
        return "Others"
    return EXT_TO_CATEGORY.get(suffix, "Others")


def get_subcategory(file_path: Path, category: str) -> str:
    """Return the sub-folder name within category, or '' if none defined."""
    suffix = file_path.suffix.lstrip(".").lower()
    return SUBCATEGORY_MAP.get(category, {}).get(suffix, "")


# Default directory names excluded from recursive scanning at all depths.
# /proc and /sys are excluded by absolute path in the scanner, not by name,
# so user folders that happen to be called "proc" or "sys" are still scanned.
DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".cache", ".local", ".git", "node_modules",
})

# Files that are never moved: OS metadata that breaks folder views when moved.
ALWAYS_SKIPPED_FILES: frozenset[str] = frozenset({
    "desktop.ini", "thumbs.db", "ehthumbs.db", ".ds_store", ".directory",
})

# Downloads that are still running and temporary files that a program has open.
IN_PROGRESS_SUFFIXES: frozenset[str] = frozenset({
    ".crdownload", ".part", ".partial", ".download", ".opdownload",
    ".tmp", ".temp", ".!ut", ".!qb",
})


def is_transient_file(name: str) -> bool:
    """Return True for files that must be left alone: OS metadata, downloads
    still in progress, temp files and Office lock files (~$Report.docx)."""
    lower = name.lower()
    if lower in ALWAYS_SKIPPED_FILES or lower.startswith("~$"):
        return True
    return Path(lower).suffix in IN_PROGRESS_SUFFIXES


def atomic_write_text(path: Path, text: str, retries: int = 5) -> None:
    """Write text so readers see either the old or the new file, never half of it.

    Retries the final rename briefly: on Windows a virus scanner or sync client
    can hold the target open for a moment.
    """
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == retries - 1:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05 * (attempt + 1))


def resolve_conflict(destination: Path, max_retries: int = 1000) -> Path:
    """If destination already exists, append _1, _2 … until a free name is found.

    Raises RuntimeError if max_retries is exceeded (avoids an infinite loop on
    broken or adversarial filesystems).
    """
    if not destination.exists():
        return destination

    stem    = destination.stem
    suffix  = destination.suffix
    parent  = destination.parent

    for counter in range(1, max_retries + 1):
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate

    raise RuntimeError(
        f"resolve_conflict: could not find a free name for {destination.name} "
        f"after {max_retries} attempts."
    )


def safe_expanduser(path_str: str) -> Path:
    """Expand ~ and return an absolute Path."""
    return Path(path_str).expanduser().resolve()


# ---------------------------------------------------------------------------
# Platform-aware data directory
# ---------------------------------------------------------------------------

def xdg_base_dir(env_var: str, default: Path) -> Path:
    """Return $env_var if it holds an absolute path, else default.

    The XDG Base Directory spec says relative values must be ignored.
    """
    value = os.environ.get(env_var, "")
    return Path(value) if value and os.path.isabs(value) else default


def _xdg_app_dir(env_var: str, default_base: Path) -> Path:
    """simple_organizer folder under an XDG base directory.

    Up to v3.4.2 the XDG variables were ignored. If the user has set one and
    the old folder exists while the new one does not, the old folder keeps
    being used: its history and staging manifest hold absolute paths, so
    moving it behind the user's back could orphan staged files.
    """
    legacy    = default_base / "simple_organizer"
    preferred = xdg_base_dir(env_var, default_base) / "simple_organizer"
    if preferred != legacy and not preferred.exists() and legacy.exists():
        return legacy
    return preferred


def get_data_dir() -> Path:
    """Return the OS-appropriate data directory for Simple Organizer.

    Linux/macOS : $XDG_DATA_HOME/simple_organizer (default ~/.local/share/...)
    Windows     : %APPDATA%/simple_organizer
    """
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "simple_organizer"
    return _xdg_app_dir("XDG_DATA_HOME", Path.home() / ".local" / "share")


def get_config_dir() -> Path:
    """Return the directory holding settings.json and rules.json.

    Linux/macOS : $XDG_CONFIG_HOME/simple_organizer (default ~/.config/...)
    Windows     : %APPDATA%/simple_organizer
    """
    if sys.platform == "win32":
        return get_data_dir()
    return _xdg_app_dir("XDG_CONFIG_HOME", Path.home() / ".config")


def protected_dirs() -> list[Path]:
    """Folders that are never organised and never entered by a scan.

    Always: the folders holding settings, rules, history and staging.
    Source mode: the folder with the .py files -- it *is* the program.
    Frozen build: only the bundle folder (sys._MEIPASS). The folder that
    merely contains the exe belongs to the user and is organised normally;
    the exe itself is protected through protected_files().
    """
    candidates = [get_data_dir(), get_config_dir()]
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            candidates.append(Path(bundle))
    else:
        candidates.append(Path(__file__).parent)
    dirs: list[Path] = []
    for d in candidates:
        try:
            d = d.resolve()
        except OSError:
            pass
        if d not in dirs:
            dirs.append(d)
    return dirs


def protected_files() -> frozenset[str]:
    """Single files that are never moved (os.path.normcase'd): the running executable."""
    if not getattr(sys, "frozen", False):
        return frozenset()
    try:
        exe = Path(sys.executable).resolve()
    except OSError:
        exe = Path(sys.executable)
    return frozenset({os.path.normcase(str(exe))})


def is_inside(path: Path, folder: Path) -> bool:
    """Return True if path is folder itself or anywhere below it."""
    return path == folder or folder in path.parents


def risky_folder_reason(folder: Path) -> str | None:
    """Explain why organising folder could break something, or None if it looks safe.

    Flags drive roots, the home folder itself and the folder holding all home
    folders (C:\\Users, /home), program/system folders, the folders where
    programs keep their settings, and Git repositories.
    """
    try:
        p = folder.resolve()
    except OSError:
        p = folder
    if p.parent == p:
        return "is the root of a drive"
    if (p / ".git").exists():
        return "is a Git repository -- organising it would move its source files"

    home = Path.home()
    try:
        home = home.resolve()
    except OSError:
        pass
    if p == home:
        return "is your home folder"
    if p == home.parent:
        return "contains the home folders of all users"
    if home in p.parents:
        for name in (".config", ".local", ".cache", "AppData"):
            d = home / name
            if is_inside(p, d):
                return f"is inside {d}, where programs keep their settings and data"
        return None

    if sys.platform == "win32":
        candidates = [os.environ.get(v) for v in (
            "SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData")]
    else:
        # /run and /media are left out on purpose: removable drives are mounted there.
        candidates = ["/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/opt",
                      "/proc", "/root", "/sbin", "/sys", "/usr", "/var"]
        # Fedora Atomic / Bazzite keep /home and /mnt under /var.
        for allowed in ("/var/home", "/var/mnt", "/var/media"):
            if is_inside(p, Path(allowed)):
                return None
    for c in candidates:
        if not c:
            continue
        try:
            cp = Path(c).resolve()
        except OSError:
            continue
        if is_inside(p, cp):
            return f"is inside the system folder {cp}"
    return None

# ---------------------------------------------------------------------------
# Light / Dark colour palettes
# ---------------------------------------------------------------------------

LIGHT_THEME: dict[str, str] = {
    "bg":            "#f4f4f5",
    "surface":       "#ffffff",
    "surface_alt":   "#f8f8f9",
    "field":         "#f4f4f5",
    "button":        "#ffffff",
    "hover":         "#ececef",
    "border":        "#e2e2e6",
    "border_strong": "#bdbdc6",
    "fg":            "#18181b",
    "fg_dim":        "#52525b",
    "fg_muted":      "#8e8e97",
    "accent":        "#2f6db3",
    "accent_hover":  "#255c99",
    "accent_fg":     "#ffffff",
    "selection":     "#dbe7f5",
    "selection_fg":  "#18181b",
    "success":       "#1a7f37",
    "warning":       "#9a6700",
    "danger":        "#cf222e",
}

DARK_THEME: dict[str, str] = {
    "bg":            "#111113",
    "surface":       "#1a1a1d",
    "surface_alt":   "#212125",
    "field":         "#111113",
    "button":        "#26262b",
    "hover":         "#303036",
    "border":        "#2b2b30",
    "border_strong": "#3c3c43",
    "fg":            "#e4e4e7",
    "fg_dim":        "#a1a1aa",
    "fg_muted":      "#6b6b74",
    "accent":        "#3778bf",
    "accent_hover":  "#4589d4",
    "accent_fg":     "#ffffff",
    "selection":     "#1f3550",
    "selection_fg":  "#ffffff",
    "success":       "#3fb950",
    "warning":       "#d29922",
    "danger":        "#f85149",
}
