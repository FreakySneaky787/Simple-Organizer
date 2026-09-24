"""
utils.py — Shared constants, category mappings, and helper utilities.
"""

import sys
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
DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".cache", ".local", ".git", "node_modules", "proc", "sys",
})


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

def get_data_dir() -> Path:
    """Return the OS-appropriate data directory for Simple Organizer.

    Linux/macOS : ~/.local/share/simple_organizer
    Windows     : %APPDATA%/simple_organizer
    """
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".local" / "share"
    return base / "simple_organizer"


def get_app_dir() -> Path:
    """Return the directory containing the running application.

    PyInstaller frozen build : directory of the .exe / binary
    Source mode              : directory containing this utils.py file

    Used by the scanner to ensure the app never moves its own files.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


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
