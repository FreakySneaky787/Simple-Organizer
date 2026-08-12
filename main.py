# main.py

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Any

from organizer import (
    FilePlan,
    ScanResult,
    commit_staging,
    has_last_run,
    has_staging,
    has_undo_history,
    list_undo_history,
    organise_files,
    revert_staging,
    scan_folder,
    undo_last_run,
    undo_specific_run,
)
from utils import DARK_THEME, LIGHT_THEME, safe_expanduser
from config import load_settings, save_settings
from rules import Rule, CONDITION_TYPES, CONDITION_LABELS, load_rules, save_rules
from scheduler import OrganizerScheduler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_TITLE    = "Simple Organizer"
APP_VERSION  = "3.2.2"
MIN_W, MIN_H = 980, 720

_FONT_UI     = ("Segoe UI", 10)
_FONT_BOLD   = ("Segoe UI", 10, "bold")
_FONT_TITLE  = ("Segoe UI", 15, "bold")
_FONT_HEADER = ("Segoe UI", 9, "bold")
# "Courier New" renders correctly on both Windows and Linux
_FONT_MONO   = ("Courier New", 9)

_BTN_W = 14


# ---------------------------------------------------------------------------
# Lightweight tooltip
# ---------------------------------------------------------------------------

class _Tooltip:
    _DELAY_MS = 600

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text   = text
        self._id: str | None = None
        self._win: tk.Toplevel | None = None
        widget.bind("<Enter>",       self._schedule, add="+")
        widget.bind("<Leave>",       self._cancel,   add="+")
        widget.bind("<ButtonPress>", self._cancel,   add="+")

    def _schedule(self, _event: Any = None) -> None:
        self._cancel()
        self._id = self._widget.after(self._DELAY_MS, self._show)

    def _cancel(self, _event: Any = None) -> None:
        if self._id:
            self._widget.after_cancel(self._id)
            self._id = None
        if self._win:
            self._win.destroy()
            self._win = None

    def _show(self) -> None:
        try:
            x = self._widget.winfo_rootx() + 20
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
            self._win = tk.Toplevel(self._widget)
            self._win.wm_overrideredirect(True)
            self._win.wm_geometry(f"+{x}+{y}")
            tk.Label(
                self._win, text=self._text,
                background="#ffffe0", foreground="#333333",
                relief="solid", borderwidth=1,
                font=("Segoe UI", 9), padx=6, pady=3,
                justify="left", wraplength=320,
            ).pack()
        except Exception:
            # Widget may have been destroyed before the timer fired.
            self._win = None


# ---------------------------------------------------------------------------
# Undo history dialog
# ---------------------------------------------------------------------------

class _HistoryDialog(tk.Toplevel):
    def __init__(self, parent: "SimpleOrganizerApp") -> None:
        super().__init__(parent)
        self._app = parent
        self.title("Undo History")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._build()
        self._load()
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _build(self) -> None:
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Select a run to undo:", font=_FONT_BOLD).pack(anchor="w", pady=(0, 6))
        lf = ttk.Frame(f)
        lf.pack(fill="both", expand=True)
        self._lb = tk.Listbox(lf, width=46, height=10, font=_FONT_UI, selectmode="single")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._lb.yview)
        self._lb.configure(yscrollcommand=sb.set)
        self._lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(10, 0))
        self._undo_btn = ttk.Button(bf, text="Undo Selected",
                                    style="Accent.TButton", command=self._on_undo)
        self._undo_btn.pack(side="left", padx=(0, 6))
        ttk.Button(bf, text="Close", command=self.destroy).pack(side="left")
        ttk.Label(
            f,
            text="Note: undoing an older run may partially fail if files have moved since.",
            font=("Segoe UI", 8, "italic"),
        ).pack(anchor="w", pady=(8, 0))

    def _load(self) -> None:
        self._entries = list_undo_history()
        self._lb.delete(0, "end")
        if not self._entries:
            self._lb.insert("end", "No history available.")
            self._undo_btn.configure(state="disabled")
        else:
            for e in self._entries:
                self._lb.insert("end", f"  {e['label']}")
            self._lb.selection_set(0)

    def _on_undo(self) -> None:
        sel = self._lb.curselection()
        if not sel or not self._entries:
            return
        entry = self._entries[sel[0]]
        self.destroy()
        self._app._undo_specific(entry["file_path"])


# ---------------------------------------------------------------------------
# Rule add/edit dialog
# ---------------------------------------------------------------------------

class _RuleDialog(tk.Toplevel):
    def __init__(self, parent: "SimpleOrganizerApp", rule: Rule | None = None) -> None:
        super().__init__(parent)
        self._rule  = rule
        self.result: Rule | None = None
        self.title("Edit Rule" if rule else "Add Rule")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._build(rule)
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _build(self, rule: Rule | None) -> None:
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        def lbl(r: int, text: str) -> None:
            ttk.Label(f, text=text, anchor="e", width=16).grid(
                row=r, column=0, sticky="e", padx=(0, 8), pady=4)

        lbl(0, "Name:")
        self._name_var = tk.StringVar(value=rule.name if rule else "")
        ttk.Entry(f, textvariable=self._name_var, width=28).grid(row=0, column=1, sticky="ew")

        lbl(1, "Condition:")
        self._ctype_var = tk.StringVar(value=rule.condition_type if rule else CONDITION_TYPES[0])
        cb = ttk.Combobox(f, textvariable=self._ctype_var, values=CONDITION_TYPES,
                          state="readonly", width=26)
        cb.grid(row=1, column=1, sticky="ew")
        cb.bind("<<ComboboxSelected>>", self._update_hint)

        lbl(2, "Value:")
        self._val_var = tk.StringVar(value=rule.condition_value if rule else "")
        ttk.Entry(f, textvariable=self._val_var, width=28).grid(row=2, column=1, sticky="ew")

        self._hint_var = tk.StringVar()
        ttk.Label(f, textvariable=self._hint_var,
                  font=("Segoe UI", 8, "italic")).grid(row=3, column=1, sticky="w")
        self._update_hint()

        lbl(4, "Target Folder:")
        self._folder_var = tk.StringVar(value=rule.target_folder if rule else "")
        ttk.Entry(f, textvariable=self._folder_var, width=28).grid(row=4, column=1, sticky="ew")
        ttk.Label(f, text="Subfolder name inside scan root",
                  font=("Segoe UI", 8, "italic")).grid(row=5, column=1, sticky="w")

        self._enabled_var = tk.BooleanVar(value=rule.enabled if rule else True)
        ttk.Checkbutton(f, text="Enabled", variable=self._enabled_var).grid(
            row=6, column=1, sticky="w", pady=(8, 0))

        bf = ttk.Frame(f)
        bf.grid(row=7, column=0, columnspan=2, pady=(12, 0), sticky="e")
        ttk.Button(bf, text="OK", style="Accent.TButton", command=self._ok).pack(side="left", padx=(0, 6))
        ttk.Button(bf, text="Cancel", command=self.destroy).pack(side="left")

    def _update_hint(self, _event: Any = None) -> None:
        self._hint_var.set(CONDITION_LABELS.get(self._ctype_var.get(), ""))

    def _ok(self) -> None:
        name   = self._name_var.get().strip()
        folder = self._folder_var.get().strip()
        value  = self._val_var.get().strip()
        ctype  = self._ctype_var.get()

        if not name or not folder or not value:
            messagebox.showwarning("Incomplete",
                                   "Name, Value, and Target Folder are required.", parent=self)
            return

        numeric_types = {"min_size_mb", "max_size_mb", "older_than_days", "newer_than_days"}
        if ctype in numeric_types:
            try:
                parsed = float(value)
                if parsed < 0:
                    raise ValueError("negative")
            except ValueError:
                messagebox.showwarning(
                    "Invalid value",
                    f'"{value}" is not a valid number for "{ctype}".\nPlease enter a positive number (e.g. 100).',
                    parent=self,
                )
                return

        self.result = Rule(
            name=name,
            enabled=self._enabled_var.get(),
            condition_type=ctype,
            condition_value=value,
            target_folder=folder,
        )
        self.destroy()


# ---------------------------------------------------------------------------
# Theme helpers
# ---------------------------------------------------------------------------

def _adjust_colour(hex_colour: str, amount: int) -> str:
    """Lighten a hex colour by brightening each RGB channel by amount."""
    hex_colour = hex_colour.lstrip("#")
    r, g, b = (int(hex_colour[i:i+2], 16) for i in (0, 2, 4))
    r = min(255, r + amount)
    g = min(255, g + amount)
    b = min(255, b + amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _apply_ttk_theme(style: ttk.Style, theme: dict[str, str]) -> None:
    style.theme_use("clam")

    bg     = theme["bg"]
    fg     = theme["fg"]
    accent = theme["accent"]
    acc_fg = theme["accent_fg"]
    entry  = theme["entry_bg"]
    sel_bg = theme["list_sel_bg"]
    sel_fg = theme["list_sel_fg"]
    border = theme["border"]
    frame  = theme["frame_bg"]
    header_fg = theme.get("header_fg", accent)
    accent_hover = _adjust_colour(accent, 20)

    style.configure(".", background=bg, foreground=fg, font=_FONT_UI,
                    borderwidth=0, relief="flat")
    for cls in ("TFrame", "TLabelframe", "TLabelframe.Label"):
        style.configure(cls, background=bg, foreground=fg)

    style.configure("TLabel",        background=bg, foreground=fg, font=_FONT_UI)
    style.configure("Title.TLabel",  background=bg, foreground=fg, font=_FONT_TITLE)
    style.configure("Status.TLabel", background=bg, foreground=fg, font=_FONT_UI)
    style.configure("Header.TLabel", background=bg, foreground=header_fg, font=_FONT_HEADER)
    style.configure("Hint.TLabel",   background=bg, foreground=border,
                    font=("Segoe UI", 8, "italic"))

    style.configure("TButton",
        background=accent, foreground=acc_fg, font=_FONT_UI, padding=(10, 5), relief="flat")
    style.map("TButton",
        background=[("active", accent_hover), ("disabled", border)],
        foreground=[("disabled", border)])
    style.configure("Accent.TButton",
        background=accent, foreground=acc_fg, font=_FONT_BOLD, padding=(10, 6), relief="flat")
    style.map("Accent.TButton",
        background=[("active", accent_hover), ("disabled", border)],
        foreground=[("disabled", border)])
    style.configure("Warn.TButton",
        background="#e67e22", foreground="#ffffff", font=_FONT_UI, padding=(10, 5), relief="flat")
    style.map("Warn.TButton",
        background=[("active", "#d35400"), ("disabled", border)],
        foreground=[("disabled", border)])

    style.configure("TEntry",
        fieldbackground=entry, foreground=fg, insertcolor=fg, borderwidth=1, relief="flat")
    style.configure("TCheckbutton", background=bg, foreground=fg, font=_FONT_UI)
    style.map("TCheckbutton",
        background=[("active", bg)],
        foreground=[("disabled", border)])
    style.configure("TCombobox", fieldbackground=entry, foreground=fg)
    style.configure("TProgressbar",
        troughcolor=frame, background=accent, thickness=10, borderwidth=0)
    style.configure("TNotebook", background=bg, borderwidth=0, tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab",
        background=frame, foreground=fg, font=_FONT_UI, padding=(14, 6))
    style.map("TNotebook.Tab",
        background=[("selected", bg), ("active", entry)],
        foreground=[("selected", accent)],
        expand=[("selected", [1, 1, 1, 0])])
    style.configure("Treeview",
        background=theme["list_bg"], foreground=theme["list_fg"],
        fieldbackground=theme["list_bg"], font=_FONT_MONO, rowheight=24, borderwidth=0)
    style.configure("Treeview.Heading",
        background=frame, foreground=header_fg, font=_FONT_BOLD, relief="flat", padding=(6, 4))
    style.map("Treeview",
        background=[("selected", sel_bg)],
        foreground=[("selected", sel_fg)])
    style.map("Treeview.Heading", background=[("active", entry)])
    style.configure("TSeparator", background=border)
    style.configure("TScrollbar",
        background=frame, troughcolor=bg, arrowcolor=fg, borderwidth=0, relief="flat")
    style.map("TScrollbar", background=[("active", border)])
    style.configure("TSpinbox",
        fieldbackground=entry, foreground=fg, insertcolor=fg, borderwidth=1)


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class SimpleOrganizerApp(tk.Tk):
    """Root window that owns all widgets and orchestrates background threads."""

    def __init__(self) -> None:
        super().__init__()

        # Load window icon — works for both PyInstaller binary and source mode
        try:
            if getattr(sys, "frozen", False):
                _base = Path(sys._MEIPASS)          # type: ignore[attr-defined]
            else:
                _base = Path(__file__).resolve().parent
            self._icon = tk.PhotoImage(file=str(_base / "icon.png"))
            self.iconphoto(True, self._icon)
        except Exception:
            self._icon = None  # silently skip if icon is missing

        self._settings: dict = load_settings()

        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.minsize(MIN_W, MIN_H)
        self.resizable(True, True)

        w = max(self._settings["window_width"],  MIN_W)
        h = max(self._settings["window_height"], MIN_H)
        self.geometry(f"{w}x{h}")

        # ── State ─────────────────────────────────────────────────────────────
        _saved_folder = self._settings.get("last_folder", "")
        if _saved_folder and Path(_saved_folder).is_dir():
            self._folder = Path(_saved_folder)
        else:
            self._folder = safe_expanduser("~/Downloads")

        self._scan_result:    ScanResult | None = None
        self._dark_mode:      bool              = bool(self._settings["dark_mode"])
        self._auto_mode:      bool              = False
        self._busy_flag:      bool              = False   # M5 fix — initialised here

        self._recursive:      tk.BooleanVar = tk.BooleanVar(
            value=bool(self._settings.get("recursive", False)))
        self._include_hidden: tk.BooleanVar = tk.BooleanVar(
            value=bool(self._settings.get("include_hidden", False)))
        self._use_staging:    tk.BooleanVar = tk.BooleanVar(
            value=bool(self._settings["staging_mode"]))
        self._use_subcats:    tk.BooleanVar = tk.BooleanVar(
            value=bool(self._settings.get("use_subcategories", False)))
        self._max_depth:      tk.IntVar    = tk.IntVar(value=int(self._settings.get("max_depth", 5)))
        self._max_dirs:       tk.IntVar    = tk.IntVar(value=int(self._settings.get("max_dirs", 10_000)))
        self._scan_timeout:   tk.DoubleVar = tk.DoubleVar(value=float(self._settings.get("scan_timeout", 30.0)))

        self._schedule_enabled:  tk.BooleanVar = tk.BooleanVar(
            value=bool(self._settings.get("schedule_enabled", False)))
        self._schedule_interval: tk.IntVar = tk.IntVar(
            value=int(self._settings.get("schedule_interval_minutes", 60)))
        self._schedule_status_var: tk.StringVar = tk.StringVar(value="Disabled")

        self._theme:       dict[str, str]              = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._style        = ttk.Style(self)
        self._resize_job:  str | None = None

        # S1 fix: pass log_callback to scheduler so errors surface in the UI
        self._scheduler = OrganizerScheduler(
            callback=self._on_schedule_fire,
            log_callback=lambda msg: self._event_queue.put({"type": "log", "value": msg}),
        )

        # ── Build & configure ─────────────────────────────────────────────────
        self._build_ui()
        self._apply_theme()
        self._theme_btn.configure(
            text="☀  Light Mode" if self._dark_mode else "🌙  Dark Mode"
        )
        self._bind_shortcuts()
        self._try_register_dnd()
        self._refresh_persistent_buttons()
        self._apply_schedule_settings()

        # M2 fix — stop scheduler cleanly on window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_configure)
        self._poll_queue()

    def _on_close(self) -> None:
        """Save settings, stop background scheduler, then destroy the window."""
        self._save_settings()
        self._scheduler.stop()
        self.destroy()

    # =========================================================================
    # UI construction
    # =========================================================================

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(16, 14, 16, 10))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        self._top = top

        ttk.Label(top, text=APP_TITLE, style="Title.TLabel").grid(
            row=0, column=0, columnspan=7, sticky="w", pady=(0, 12))

        # ── Folder Selection ──────────────────────────────────────────────────
        ttk.Label(top, text="Folder Selection", style="Header.TLabel").grid(
            row=1, column=0, columnspan=7, sticky="w", pady=(0, 4))

        self._folder_var   = tk.StringVar(value=str(self._folder))
        self._folder_entry = ttk.Entry(
            top, textvariable=self._folder_var, state="readonly", font=_FONT_MONO)
        self._folder_entry.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 6))

        self._browse_btn = ttk.Button(top, text="Browse...", width=_BTN_W,
                                      command=self._browse_folder)
        self._browse_btn.grid(row=2, column=2, padx=(0, 20))

        # ── Organisation ──────────────────────────────────────────────────────
        ttk.Label(top, text="Organisation", style="Header.TLabel").grid(
            row=3, column=0, columnspan=7, sticky="w", pady=(10, 4))

        action_frame = ttk.Frame(top)
        action_frame.grid(row=4, column=0, columnspan=7, sticky="w")

        self._scan_btn = ttk.Button(
            action_frame, text="Scan", style="Accent.TButton",
            width=_BTN_W, command=self._start_scan)
        self._scan_btn.pack(side="left", padx=(0, 6))

        self._organize_btn = ttk.Button(
            action_frame, text="Organize", style="Accent.TButton",
            width=_BTN_W, command=self._confirm_and_organize, state="disabled")
        self._organize_btn.pack(side="left", padx=(0, 6))

        self._undo_btn = ttk.Button(
            action_frame, text="Undo Last", width=_BTN_W,
            command=self._confirm_and_undo, state="disabled")
        self._undo_btn.pack(side="left", padx=(0, 6))

        self._history_btn = ttk.Button(
            action_frame, text="History", width=_BTN_W,
            command=self._open_history_dialog, state="disabled")
        self._history_btn.pack(side="left", padx=(0, 6))

        _Tooltip(self._scan_btn,     "Scan the selected folder and preview planned moves. (Ctrl+R)")
        _Tooltip(self._organize_btn, "Move files into category subfolders. Shows total size first. (Ctrl+O)")
        _Tooltip(self._undo_btn,     "Restore all files moved in the last organise run. (Ctrl+Z)")
        _Tooltip(self._history_btn,  "Browse and undo any of the last 20 organise runs.")

        # ── Scan Options ──────────────────────────────────────────────────────
        ttk.Label(top, text="Scan Options", style="Header.TLabel").grid(
            row=5, column=0, columnspan=7, sticky="w", pady=(10, 4))

        opts = ttk.Frame(top)
        opts.grid(row=6, column=0, columnspan=7, sticky="w")

        self._recursive_cb = ttk.Checkbutton(
            opts, text="Scan subdirectories", variable=self._recursive,
            command=self._save_settings)
        self._recursive_cb.pack(side="left")

        self._hidden_cb = ttk.Checkbutton(
            opts, text="Include hidden files", variable=self._include_hidden,
            command=self._save_settings)
        self._hidden_cb.pack(side="left", padx=(20, 0))

        self._staging_cb = ttk.Checkbutton(
            opts, text="Use staging mode", variable=self._use_staging,
            command=self._on_staging_toggle)
        self._staging_cb.pack(side="left", padx=(20, 0))
        _Tooltip(self._staging_cb,
                 "Move files to a temporary staging area first.\n"
                 "Use Commit Staging to finalise, or Revert Staging to cancel.")

        self._subcats_cb = ttk.Checkbutton(
            opts, text="Use sub-categories", variable=self._use_subcats,
            command=self._on_subcats_toggle)
        self._subcats_cb.pack(side="left", padx=(20, 0))
        _Tooltip(
            self._subcats_cb,
            "Sort files into sub-folders inside each category.\n"
            "Examples:\n"
            "  Images/Photos/    Images/Editing/    Images/Raw/\n"
            "  Documents/PDFs/   Documents/Word/    Documents/Spreadsheets/\n"
            "  Music/Lossless/   Code/Python/       Code/JavaScript/\n\n"
            "Off by default. Does not affect custom Rules."
        )

        limits = ttk.Frame(top)
        limits.grid(row=7, column=0, columnspan=7, sticky="w", pady=(6, 0))

        ttk.Label(limits, text="Max depth:").pack(side="left", padx=(0, 4))
        self._max_depth_spin = ttk.Spinbox(limits, from_=1, to=50, width=5,
                                           textvariable=self._max_depth)
        self._max_depth_spin.pack(side="left", padx=(0, 16))

        ttk.Label(limits, text="Max dirs:").pack(side="left", padx=(0, 4))
        self._max_dirs_spin = ttk.Spinbox(limits, from_=100, to=500_000, increment=1000,
                                          width=8, textvariable=self._max_dirs)
        self._max_dirs_spin.pack(side="left", padx=(0, 16))

        ttk.Label(limits, text="Timeout (s):").pack(side="left", padx=(0, 4))
        self._timeout_spin = ttk.Spinbox(limits, from_=5, to=300, increment=5, width=5,
                                         textvariable=self._scan_timeout)
        self._timeout_spin.pack(side="left")

        # ── Staging ───────────────────────────────────────────────────────────
        ttk.Label(top, text="Staging", style="Header.TLabel").grid(
            row=8, column=0, columnspan=7, sticky="w", pady=(10, 4))

        staging_btns = ttk.Frame(top)
        staging_btns.grid(row=9, column=0, columnspan=7, sticky="w")

        self._commit_btn = ttk.Button(
            staging_btns, text="Commit Staging",
            width=_BTN_W, command=self._confirm_and_commit, state="disabled")
        self._commit_btn.pack(side="left", padx=(0, 6))

        self._revert_btn = ttk.Button(
            staging_btns, text="Revert Staging",
            style="Warn.TButton", width=_BTN_W,
            command=self._confirm_and_revert, state="disabled")
        self._revert_btn.pack(side="left")

        # ── Auto-Organize ─────────────────────────────────────────────────────
        ttk.Label(top, text="Auto-Organize", style="Header.TLabel").grid(
            row=10, column=0, columnspan=7, sticky="w", pady=(10, 4))

        sched_frame = ttk.Frame(top)
        sched_frame.grid(row=11, column=0, columnspan=7, sticky="w")

        self._sched_cb = ttk.Checkbutton(
            sched_frame, text="Enable -- every",
            variable=self._schedule_enabled, command=self._on_schedule_toggle)
        self._sched_cb.pack(side="left")
        _Tooltip(self._sched_cb,
                 "Automatically scan and organise the selected folder on the set interval.\n"
                 "Runs silently without confirmation dialogs.")

        self._sched_spin = ttk.Spinbox(
            sched_frame, from_=1, to=1440, increment=15, width=5,
            textvariable=self._schedule_interval, command=self._on_schedule_toggle)
        self._sched_spin.pack(side="left", padx=(6, 4))
        ttk.Label(sched_frame, text="minutes    ").pack(side="left")
        ttk.Label(sched_frame, textvariable=self._schedule_status_var,
                  style="Hint.TLabel").pack(side="left")

        # ── Progress ──────────────────────────────────────────────────────────
        prog_frame = ttk.Frame(top)
        prog_frame.grid(row=12, column=0, columnspan=7, sticky="ew", pady=(12, 0))
        prog_frame.columnconfigure(0, weight=1)

        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress = ttk.Progressbar(
            prog_frame, variable=self._progress_var, maximum=100.0, mode="determinate")
        self._progress.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._pct_var = tk.StringVar(value="0%")
        ttk.Label(prog_frame, textvariable=self._pct_var, width=5, anchor="e").grid(row=0, column=1)

        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(top, textvariable=self._status_var, style="Status.TLabel").grid(
            row=13, column=0, columnspan=7, sticky="w", pady=(4, 0))

        ttk.Separator(self, orient="horizontal").grid(row=0, column=0, sticky="sew")

        # ── Notebook ──────────────────────────────────────────────────────────
        nb_frame = ttk.Frame(self, padding=(16, 8, 16, 0))
        nb_frame.grid(row=1, column=0, sticky="nsew")
        nb_frame.columnconfigure(0, weight=1)
        nb_frame.rowconfigure(0, weight=1)

        self._notebook = ttk.Notebook(nb_frame)
        self._notebook.grid(row=0, column=0, sticky="nsew")

        # Tab 0 — Preview (M4 fix: store index dynamically)
        preview_tab = ttk.Frame(self._notebook, padding=(4, 4))
        preview_tab.columnconfigure(0, weight=1)
        preview_tab.rowconfigure(0, weight=1)
        self._notebook.add(preview_tab, text="  Preview  ")
        self._preview_tab_idx = 0   # stored to avoid hardcoded index throughout

        preview_cols = ("file", "category", "destination")
        self._preview_tree = ttk.Treeview(
            preview_tab, columns=preview_cols, show="headings", selectmode="browse")
        self._preview_tree.heading("file",        text="File")
        self._preview_tree.heading("category",    text="Category")
        self._preview_tree.heading("destination", text="Destination Folder")
        self._preview_tree.column("file",        width=240, anchor="w",      stretch=True)
        self._preview_tree.column("category",    width=140, anchor="center", stretch=False)
        self._preview_tree.column("destination", width=340, anchor="w",      stretch=True)

        pv_vsb = ttk.Scrollbar(preview_tab, orient="vertical",   command=self._preview_tree.yview)
        pv_hsb = ttk.Scrollbar(preview_tab, orient="horizontal", command=self._preview_tree.xview)
        self._preview_tree.configure(yscrollcommand=pv_vsb.set, xscrollcommand=pv_hsb.set)
        self._preview_tree.grid(row=0, column=0, sticky="nsew")
        pv_vsb.grid(row=0, column=1, sticky="ns")
        pv_hsb.grid(row=1, column=0, sticky="ew")
        self._preview_tree.bind("<Button-3>", self._on_preview_context)

        # Tab 1 — Duplicates
        dup_tab = ttk.Frame(self._notebook, padding=(4, 4))
        dup_tab.columnconfigure(0, weight=1)
        dup_tab.rowconfigure(0, weight=1)
        self._notebook.add(dup_tab, text="  Duplicates  ")
        self._dup_tab_idx = 1   # stored to avoid hardcoded index throughout

        dup_cols = ("file", "size", "location")
        self._dup_tree = ttk.Treeview(
            dup_tab, columns=dup_cols, show="tree headings", selectmode="browse")
        self._dup_tree.heading("file",     text="File")
        self._dup_tree.heading("size",     text="Size")
        self._dup_tree.heading("location", text="Folder")
        self._dup_tree.column("#0",        width=100, anchor="w", stretch=False)
        self._dup_tree.column("file",      width=220, anchor="w", stretch=True)
        self._dup_tree.column("size",      width=80,  anchor="e", stretch=False)
        self._dup_tree.column("location",  width=380, anchor="w", stretch=True)

        dup_vsb = ttk.Scrollbar(dup_tab, orient="vertical",   command=self._dup_tree.yview)
        dup_hsb = ttk.Scrollbar(dup_tab, orient="horizontal", command=self._dup_tree.xview)
        self._dup_tree.configure(yscrollcommand=dup_vsb.set, xscrollcommand=dup_hsb.set)
        self._dup_tree.grid(row=0, column=0, sticky="nsew")
        dup_vsb.grid(row=0, column=1, sticky="ns")
        dup_hsb.grid(row=1, column=0, sticky="ew")
        self._dup_tree.bind("<Button-3>", self._on_dup_context)
        ttk.Label(
            dup_tab,
            text="Duplicates are listed for reference only -- nothing is deleted automatically.",
            font=("Segoe UI", 9, "italic"),
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # Tab 2 — Log
        log_tab = ttk.Frame(self._notebook, padding=(4, 4))
        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(0, weight=1)
        self._notebook.add(log_tab, text="  Log  ")
        self._log_tab_idx = 2   # stored to avoid hardcoded index throughout

        log_vsb = ttk.Scrollbar(log_tab, orient="vertical")
        self._log_box = tk.Text(
            log_tab, wrap="word", font=_FONT_MONO,
            state="disabled", borderwidth=0, relief="flat",
            yscrollcommand=log_vsb.set)
        log_vsb.configure(command=self._log_box.yview)
        self._log_box.grid(row=0, column=0, sticky="nsew")
        log_vsb.grid(row=0, column=1, sticky="ns")
        ttk.Button(log_tab, text="Clear Log", command=self._clear_log).grid(
            row=1, column=0, sticky="e", pady=(6, 0))

        # Tab 3 — Rules
        self._build_rules_tab()

        # ── Bottom panel ──────────────────────────────────────────────────────
        ttk.Separator(self, orient="horizontal").grid(row=2, column=0, sticky="ew")

        bottom = ttk.Frame(self, padding=(16, 6, 16, 10))
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=0)

        ttk.Label(
            bottom,
            text="Ctrl+R: Scan  Ctrl+O: Organize  Ctrl+Z: Undo  Ctrl+Q: Quit",
            font=("Segoe UI", 8),
        ).grid(row=0, column=0, sticky="w")

        self._theme_btn = ttk.Button(
            bottom, text="🌙  Dark Mode", command=self._toggle_dark_mode)
        self._theme_btn.grid(row=0, column=1, sticky="e")

    def _build_rules_tab(self) -> None:
        rules_tab = ttk.Frame(self._notebook, padding=(4, 4))
        rules_tab.columnconfigure(0, weight=1)
        rules_tab.rowconfigure(0, weight=1)
        self._notebook.add(rules_tab, text="  Rules  ")

        cols = ("enabled", "name", "condition", "value", "target")
        self._rules_tree = ttk.Treeview(
            rules_tab, columns=cols, show="headings", selectmode="browse")
        self._rules_tree.heading("enabled",   text="On")
        self._rules_tree.heading("name",      text="Name")
        self._rules_tree.heading("condition", text="Condition")
        self._rules_tree.heading("value",     text="Value")
        self._rules_tree.heading("target",    text="Target Folder")
        self._rules_tree.column("enabled",   width=40,  anchor="center", stretch=False)
        self._rules_tree.column("name",      width=140, anchor="w",      stretch=True)
        self._rules_tree.column("condition", width=140, anchor="w",      stretch=False)
        self._rules_tree.column("value",     width=110, anchor="w",      stretch=False)
        self._rules_tree.column("target",    width=140, anchor="w",      stretch=True)

        rv_sb = ttk.Scrollbar(rules_tab, orient="vertical", command=self._rules_tree.yview)
        self._rules_tree.configure(yscrollcommand=rv_sb.set)
        self._rules_tree.grid(row=0, column=0, sticky="nsew")
        rv_sb.grid(row=0, column=1, sticky="ns")

        rb = ttk.Frame(rules_tab)
        rb.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Button(rb, text="Add",      command=self._rule_add).pack(side="left", padx=(0, 6))
        ttk.Button(rb, text="Edit",     command=self._rule_edit).pack(side="left", padx=(0, 6))
        ttk.Button(rb, text="Toggle",   command=self._rule_toggle).pack(side="left", padx=(0, 6))
        ttk.Button(rb, text="Delete",   style="Warn.TButton",
                   command=self._rule_delete).pack(side="left", padx=(0, 6))
        ttk.Button(rb, text="Move Up",  command=lambda: self._rule_move(-1)).pack(side="left", padx=(0, 6))
        ttk.Button(rb, text="Move Down",command=lambda: self._rule_move(1)).pack(side="left")

        ttk.Label(
            rules_tab,
            text="Rules run before extension-based categorisation. First match wins.",
            font=("Segoe UI", 8, "italic"),
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self._refresh_rules_tree()

    # =========================================================================
    # Theme
    # =========================================================================

    def _apply_theme(self) -> None:
        t = self._theme
        self.configure(bg=t["bg"])
        _apply_ttk_theme(self._style, t)
        self._log_box.configure(
            bg=t["log_bg"], fg=t["log_fg"],
            insertbackground=t["fg"],
            selectbackground=t["list_sel_bg"],
            selectforeground=t["list_sel_fg"],
        )

    def _toggle_dark_mode(self) -> None:
        self._dark_mode = not self._dark_mode
        self._theme = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._theme_btn.configure(
            text="☀  Light Mode" if self._dark_mode else "🌙  Dark Mode")
        self._apply_theme()
        self._save_settings()

    # =========================================================================
    # Keyboard shortcuts & DnD
    # =========================================================================

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-r>", lambda e: self._start_scan())
        self.bind_all("<Control-o>", lambda e: self._confirm_and_organize())
        self.bind_all("<Control-z>", lambda e: self._confirm_and_undo())
        self.bind_all("<Control-q>", lambda e: self._on_close())

    def _try_register_dnd(self) -> None:
        try:
            self.tk.call("package", "require", "tkdnd")
            self._folder_entry.drop_target_register("DND_Files")  # type: ignore
            self._folder_entry.dnd_bind("<<Drop>>", self._on_dnd_drop)  # type: ignore
        except Exception:
            pass

    def _on_dnd_drop(self, event: Any) -> None:
        """Handle drag-and-drop. tkdnd may return one path or multiple.

        Single path with spaces : wrapped in {braces}
        Multiple paths          : space-separated, each optionally in {braces}
        We use the first valid directory found.
        """
        raw: str = event.data.strip()  # type: ignore

        # Parse all tokens — each may be bare or {brace-wrapped}
        tokens: list[str] = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                end = raw.find("}", i)
                if end == -1:
                    tokens.append(raw[i + 1:])
                    break
                tokens.append(raw[i + 1:end])
                i = end + 1
            elif raw[i] == " ":
                i += 1
            else:
                end = raw.find(" ", i)
                if end == -1:
                    tokens.append(raw[i:])
                    break
                tokens.append(raw[i:end])
                i = end

        for token in tokens:
            if not token:
                continue
            path = Path(token)
            if path.is_dir():
                self._set_folder(path)
                return
            if path.is_file():
                self._set_folder(path.parent)
                return

    def _set_folder(self, path: Path) -> None:
        self._folder = path.resolve()
        self._folder_var.set(str(self._folder))
        self._scan_result = None
        self._organize_btn.configure(state="disabled")
        self._clear_preview()
        self._notebook.tab(self._preview_tab_idx, text="  Preview  ")  # reset badge
        self._log(f"Folder set: {self._folder}")
        self._save_settings()

    # =========================================================================
    # Folder browsing
    # =========================================================================

    def _browse_folder(self) -> None:
        initial = str(self._folder) if self._folder.exists() else str(Path.home())
        chosen  = filedialog.askdirectory(title="Select folder to organise", initialdir=initial)
        if chosen:
            self._set_folder(Path(chosen))

    # =========================================================================
    # Toggles
    # =========================================================================

    def _on_staging_toggle(self) -> None:
        self._refresh_persistent_buttons()
        self._save_settings()

    def _on_subcats_toggle(self) -> None:
        self._save_settings()

    def _refresh_persistent_buttons(self) -> None:
        undo_state    = "normal" if has_last_run()     else "disabled"
        staging_state = "normal" if has_staging()      else "disabled"
        history_state = "normal" if has_undo_history() else "disabled"
        self._undo_btn.configure(state=undo_state)
        self._commit_btn.configure(state=staging_state)
        self._revert_btn.configure(state=staging_state)
        self._history_btn.configure(state=history_state)

    # =========================================================================
    # Schedule
    # =========================================================================

    def _apply_schedule_settings(self) -> None:
        self._scheduler.configure(
            interval_minutes=self._schedule_interval.get(),
            enabled=self._schedule_enabled.get(),
        )
        self._update_schedule_status()

    def _on_schedule_toggle(self) -> None:
        self._apply_schedule_settings()
        self._save_settings()

    def _update_schedule_status(self) -> None:
        if self._schedule_enabled.get():
            mins = self._schedule_interval.get()
            self._schedule_status_var.set(f"Active -- runs every {mins} min")
        else:
            self._schedule_status_var.set("Disabled")

    def _on_schedule_fire(self) -> None:
        self._event_queue.put({"type": "schedule_fire"})

    def _run_scheduled_organize(self) -> None:
        if self._busy_flag:
            self._log("[SCHEDULE]  Skipped -- app is busy.")
            return
        self._log(f"[SCHEDULE]  Auto-organize triggered for: {self._folder}")
        self._auto_mode = True
        self._start_scan()

    # =========================================================================
    # Rules UI
    # =========================================================================

    def _refresh_rules_tree(self) -> None:
        self._rules_tree.delete(*self._rules_tree.get_children())
        for rule in load_rules():
            self._rules_tree.insert("", "end", values=(
                "Y" if rule.enabled else "N",
                rule.name, rule.condition_type,
                rule.condition_value, rule.target_folder,
            ))

    def _selected_rule_index(self) -> int | None:
        sel = self._rules_tree.selection()
        if not sel:
            return None
        return list(self._rules_tree.get_children()).index(sel[0])

    def _rule_add(self) -> None:
        dlg = _RuleDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            rules = load_rules()
            rules.append(dlg.result)
            save_rules(rules)
            self._refresh_rules_tree()

    def _rule_edit(self) -> None:
        idx = self._selected_rule_index()
        if idx is None:
            messagebox.showinfo("No selection", "Select a rule to edit.", parent=self)
            return
        rules = load_rules()
        dlg   = _RuleDialog(self, rules[idx])
        self.wait_window(dlg)
        if dlg.result:
            rules[idx] = dlg.result
            save_rules(rules)
            self._refresh_rules_tree()

    def _rule_toggle(self) -> None:
        idx = self._selected_rule_index()
        if idx is None:
            return
        rules = load_rules()
        rules[idx].enabled = not rules[idx].enabled
        save_rules(rules)
        self._refresh_rules_tree()

    def _rule_delete(self) -> None:
        idx = self._selected_rule_index()
        if idx is None:
            return
        rules = load_rules()
        if not messagebox.askyesno("Delete Rule",
                                   f"Delete rule '{rules[idx].name}'?", parent=self):
            return
        del rules[idx]
        save_rules(rules)
        self._refresh_rules_tree()

    def _rule_move(self, direction: int) -> None:
        idx = self._selected_rule_index()
        if idx is None:
            return
        rules   = load_rules()
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(rules):
            return
        rules[idx], rules[new_idx] = rules[new_idx], rules[idx]
        save_rules(rules)
        self._refresh_rules_tree()
        children = self._rules_tree.get_children()
        if children:
            self._rules_tree.selection_set(children[new_idx])

    # =========================================================================
    # Undo history
    # =========================================================================

    def _open_history_dialog(self) -> None:
        _HistoryDialog(self)

    def _undo_specific(self, run_file: Path) -> None:
        self._set_busy(True)
        self._set_progress(0.0)
        self._status(f"Undoing {run_file.stem}...")
        self._notebook.select(self._log_tab_idx)
        t = threading.Thread(target=self._undo_specific_worker,
                             args=(run_file,), daemon=True)
        t.start()

    def _undo_specific_worker(self, run_file: Path) -> None:
        def progress(c: int, t: int) -> None:
            self._event_queue.put({"type": "progress",
                                   "value": (c / t * 100) if t else 0})
        def log_msg(msg: str) -> None:
            self._event_queue.put({"type": "log", "value": msg})
        try:
            errors = undo_specific_run(run_file, progress_callback=progress,
                                       log_callback=log_msg)
            self._event_queue.put({"type": "undo_done", "errors": errors})
        except Exception as exc:  # noqa: BLE001
            self._event_queue.put({"type": "error", "value": str(exc)})

    # =========================================================================
    # Settings persistence
    # =========================================================================

    def _save_settings(self) -> None:
        self._settings.update({
            "last_folder":               str(self._folder),
            "staging_mode":              self._use_staging.get(),
            "dark_mode":                 self._dark_mode,
            "window_width":              self.winfo_width(),
            "window_height":             self.winfo_height(),
            "schedule_enabled":          self._schedule_enabled.get(),
            "schedule_interval_minutes": self._schedule_interval.get(),
            "use_subcategories":         self._use_subcats.get(),
            "recursive":                 self._recursive.get(),
            "include_hidden":            self._include_hidden.get(),
            "max_depth":                 self._max_depth.get(),
            "max_dirs":                  self._max_dirs.get(),
            "scan_timeout":              self._scan_timeout.get(),
        })
        if not save_settings(self._settings):
            self._log("[WARN]  Settings could not be saved — check disk space and permissions.")

    def _on_configure(self, event: Any) -> None:
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(400, self._save_settings)

    # =========================================================================
    # Scanning
    # =========================================================================

    def _start_scan(self) -> None:
        self._save_settings()   # persist current scan options before running
        self._set_busy(True)
        self._clear_preview()
        self._clear_duplicates()
        self._scan_result = None
        self._organize_btn.configure(state="disabled")
        self._notebook.tab(self._preview_tab_idx, text="  Preview  ")  # M4 fix
        self._set_progress(0.0)
        self._status("Scanning...")

        t = threading.Thread(
            target=self._scan_worker,
            args=(
                self._folder,
                self._recursive.get(),
                self._include_hidden.get(),
                self._max_depth.get(),
                self._max_dirs.get(),
                self._scan_timeout.get(),
                self._use_subcats.get(),
            ),
            daemon=True,
        )
        t.start()

    def _scan_worker(
        self,
        folder: Path, recursive: bool, include_hidden: bool,
        max_depth: int, max_dirs: int, scan_timeout: float,
        use_subcategories: bool,
    ) -> None:
        def progress(c: int, t: int) -> None:
            self._event_queue.put({"type": "progress",
                                   "value": (c / t * 100) if t else 0})
        def status(msg: str) -> None:
            self._event_queue.put({"type": "status", "value": msg})
        try:
            result = scan_folder(
                folder=folder, recursive=recursive,
                include_hidden=include_hidden, max_depth=max_depth,
                max_dirs=max_dirs, scan_timeout=scan_timeout,
                use_subcategories=use_subcategories,
                progress_callback=progress, status_callback=status,
            )
            self._event_queue.put({"type": "scan_done", "result": result})
        except Exception as exc:  # noqa: BLE001
            self._event_queue.put({"type": "error", "value": str(exc)})

    def _handle_scan_done(self, result: ScanResult) -> None:
        self._scan_result = result
        self._set_busy(False)
        self._set_progress(100.0)

        for err in result.errors:
            self._log(f"[WARN]  {err}")

        actionable = [p for p in result.plans if not p.skipped]
        skipped    = [p for p in result.plans if p.skipped]

        self._log(
            f"Scan complete -- {result.total_files} file(s) found, "
            f"{len(actionable)} to move, {len(skipped)} already placed."
        )

        self._clear_preview()
        for plan in actionable:
            self._preview_tree.insert("", "end",
                values=(plan.source.name, plan.category, str(plan.destination.parent)),
                tags=(str(plan.source),)   # source path stored for context menu
            )

        # Preview tab badge (M4 fix: use named index)
        count = len(actionable)
        badge = f"  Preview ({count})  " if count else "  Preview  "
        self._notebook.tab(self._preview_tab_idx, text=badge)

        self._clear_duplicates()
        dup_msg = ""
        if result.duplicate_groups:
            dup_count = sum(len(g) for g in result.duplicate_groups)
            dup_msg = (
                f"  |  {len(result.duplicate_groups)} duplicate group(s) "
                f"({dup_count} file(s)) — see Duplicates tab"
            )
            self._log(
                f"Found {len(result.duplicate_groups)} duplicate group(s) "
                f"({dup_count} file(s) total)."
            )
            for group_idx, group in enumerate(result.duplicate_groups, start=1):
                node = self._dup_tree.insert("", "end", text=f"Group {group_idx}",
                                             values=("", "", ""), open=True)
                for dup in group:
                    self._dup_tree.insert(node, "end",
                                          values=(dup.name, _human_size(dup), str(dup.parent)))
        else:
            self._log("No duplicate files detected.")

        if actionable:
            self._organize_btn.configure(state="normal")
            self._status(f"Ready -- {len(actionable)} file(s) to organise.{dup_msg}")
            self._notebook.select(self._preview_tab_idx)
        else:
            self._status(f"Nothing to organise.{dup_msg}")
            if result.duplicate_groups:
                self._notebook.select(self._dup_tab_idx)

        if self._auto_mode:
            self._auto_mode = False
            if actionable:
                self._log("[SCHEDULE]  Auto-organizing now...")
                self._run_auto_organize(list(actionable))

    def _run_auto_organize(self, plans: list[FilePlan]) -> None:
        staging = self._use_staging.get()
        self._set_busy(True)
        self._set_progress(0.0)
        self._status("Auto-organizing...")
        self._notebook.select(self._log_tab_idx)
        t = threading.Thread(target=self._organize_worker,
                             args=(plans, staging), daemon=True)
        t.start()

    # =========================================================================
    # Organise
    # =========================================================================

    def _confirm_and_organize(self) -> None:
        if not self._scan_result:
            return

        actionable = [p for p in self._scan_result.plans if not p.skipped]
        if not actionable:
            messagebox.showinfo("Nothing to do", "All files are already organised.", parent=self)
            return

        total_bytes = 0
        for p in actionable:
            try:
                total_bytes += p.source.stat().st_size
            except OSError:
                pass
        size_str = _fmt_size(total_bytes)

        staging = self._use_staging.get()
        dest_label = (
            "the staging area" if staging else "categorised sub-folders"
        )
        confirmed = messagebox.askyesno(
            title="Confirm Organize",
            message=(
                f"Move {len(actionable)} file(s) -- {size_str} total -- "
                f"into {dest_label}?\n\n"
                "- Files are MOVED, not copied.\n"
                "- Nothing will be deleted.\n"
                "- Name conflicts are resolved with a _1, _2 suffix."
            ),
            parent=self,
        )
        if not confirmed:
            return

        self._set_busy(True)
        self._set_progress(0.0)
        self._status("Organising...")
        self._notebook.select(self._log_tab_idx)

        t = threading.Thread(target=self._organize_worker,
                             args=(list(actionable), staging), daemon=True)
        t.start()

    def _organize_worker(self, plans: list[FilePlan], staging: bool) -> None:
        def progress(c: int, t: int) -> None:
            self._event_queue.put({"type": "progress",
                                   "value": (c / t * 100) if t else 0})
        def log_msg(msg: str) -> None:
            self._event_queue.put({"type": "log", "value": msg})
        try:
            errors = organise_files(plans=plans, progress_callback=progress,
                                    log_callback=log_msg, staging=staging)
            self._event_queue.put({"type": "organize_done", "errors": errors,
                                   "staging": staging})
        except Exception as exc:  # noqa: BLE001
            self._event_queue.put({"type": "error", "value": str(exc)})

    def _handle_organize_done(self, errors: list[str], staging: bool) -> None:
        self._set_busy(False)
        self._set_progress(100.0)
        self._organize_btn.configure(state="disabled")
        self._scan_result = None
        self._clear_preview()
        self._notebook.tab(self._preview_tab_idx, text="  Preview  ")
        self._refresh_persistent_buttons()

        if errors:
            self._log(f"Finished with {len(errors)} error(s). See log.")
            self._status(f"Done -- {len(errors)} error(s).")
        elif staging:
            self._log("Files staged. Use Commit or Revert to finalise.")
            self._status("Staging complete -- commit or revert when ready.")
        else:
            self._log("All files organised successfully.")
            self._status("Done -- all files organised.")

    # =========================================================================
    # Undo last run
    # =========================================================================

    def _confirm_and_undo(self) -> None:
        confirmed = messagebox.askyesno(
            title="Undo Last Organize",
            message=(
                "Restore all files moved in the last organize run "
                "to their original locations?\n\n"
                "- Nothing will be deleted.\n"
                "- Name conflicts get a _1, _2 suffix.\n\nContinue?"
            ),
            parent=self,
        )
        if not confirmed:
            return
        self._set_busy(True)
        self._set_progress(0.0)
        self._status("Undoing last run...")
        self._notebook.select(self._log_tab_idx)
        t = threading.Thread(target=self._undo_worker, daemon=True)
        t.start()

    def _undo_worker(self) -> None:
        def progress(c: int, t: int) -> None:
            self._event_queue.put({"type": "progress",
                                   "value": (c / t * 100) if t else 0})
        def log_msg(msg: str) -> None:
            self._event_queue.put({"type": "log", "value": msg})
        try:
            errors = undo_last_run(progress_callback=progress, log_callback=log_msg)
            self._event_queue.put({"type": "undo_done", "errors": errors})
        except Exception as exc:  # noqa: BLE001
            self._event_queue.put({"type": "error", "value": str(exc)})

    def _handle_undo_done(self, errors: list[str]) -> None:
        self._set_busy(False)
        self._set_progress(100.0)
        self._refresh_persistent_buttons()
        if errors:
            self._log(f"Undo finished with {len(errors)} error(s). See log.")
            self._status(f"Undo done -- {len(errors)} error(s).")
        else:
            self._log("Undo complete -- files restored to original locations.")
            self._status("Undo complete.")

    # =========================================================================
    # Staging commit / revert
    # =========================================================================

    def _confirm_and_commit(self) -> None:
        confirmed = messagebox.askyesno(
            title="Commit Staging",
            message=(
                "Move all staged files to their final category folders?\n\n"
                "- Files are MOVED, not copied.\n"
                "- Nothing will be deleted.\n"
                "- This action can be undone with Undo Last Run."
            ),
            parent=self,
        )
        if not confirmed:
            return
        self._set_busy(True)
        self._set_progress(0.0)
        self._status("Committing staging...")
        self._notebook.select(self._log_tab_idx)
        t = threading.Thread(target=self._commit_worker, daemon=True)
        t.start()

    def _commit_worker(self) -> None:
        def progress(c: int, t: int) -> None:
            self._event_queue.put({"type": "progress",
                                   "value": (c / t * 100) if t else 0})
        def log_msg(msg: str) -> None:
            self._event_queue.put({"type": "log", "value": msg})
        try:
            errors = commit_staging(progress_callback=progress, log_callback=log_msg)
            self._event_queue.put({"type": "commit_done", "errors": errors})
        except Exception as exc:  # noqa: BLE001
            self._event_queue.put({"type": "error", "value": str(exc)})

    def _handle_commit_done(self, errors: list[str]) -> None:
        self._set_busy(False)
        self._set_progress(100.0)
        self._refresh_persistent_buttons()
        if errors:
            self._log(f"Commit finished with {len(errors)} error(s). See log.")
            self._status(f"Commit done -- {len(errors)} error(s).")
        else:
            self._log("Staging committed -- all files moved to final destinations.")
            self._status("Commit complete.")

    def _confirm_and_revert(self) -> None:
        confirmed = messagebox.askyesno(
            title="Revert Staging",
            message=(
                "Move all staged files back to their original locations?\n\n"
                "- Nothing will be deleted.\n"
                "- The staging area will be cleared."
            ),
            parent=self,
        )
        if not confirmed:
            return
        self._set_busy(True)
        self._set_progress(0.0)
        self._status("Reverting staging...")
        self._notebook.select(self._log_tab_idx)
        t = threading.Thread(target=self._revert_worker, daemon=True)
        t.start()

    def _revert_worker(self) -> None:
        def progress(c: int, t: int) -> None:
            self._event_queue.put({"type": "progress",
                                   "value": (c / t * 100) if t else 0})
        def log_msg(msg: str) -> None:
            self._event_queue.put({"type": "log", "value": msg})
        try:
            errors = revert_staging(progress_callback=progress, log_callback=log_msg)
            self._event_queue.put({"type": "revert_done", "errors": errors})
        except Exception as exc:  # noqa: BLE001
            self._event_queue.put({"type": "error", "value": str(exc)})

    def _handle_revert_done(self, errors: list[str]) -> None:
        self._set_busy(False)
        self._set_progress(100.0)
        self._refresh_persistent_buttons()
        if errors:
            self._log(f"Revert finished with {len(errors)} error(s). See log.")
            self._status(f"Revert done -- {len(errors)} error(s).")
        else:
            self._log("Staging reverted -- all files returned to original locations.")
            self._status("Revert complete.")

    # =========================================================================
    # Thread-safe queue polling
    # =========================================================================

    def _poll_queue(self) -> None:
        try:
            while True:
                event = self._event_queue.get_nowait()
                etype = event["type"]
                if etype == "progress":
                    self._set_progress(event["value"])
                elif etype == "status":
                    self._status(event["value"])
                elif etype == "log":
                    self._log(event["value"])
                elif etype == "scan_done":
                    self._handle_scan_done(event["result"])
                elif etype == "organize_done":
                    self._handle_organize_done(event["errors"], event["staging"])
                elif etype == "undo_done":
                    self._handle_undo_done(event["errors"])
                elif etype == "commit_done":
                    self._handle_commit_done(event["errors"])
                elif etype == "revert_done":
                    self._handle_revert_done(event["errors"])
                elif etype == "schedule_fire":
                    self._run_scheduled_organize()
                elif etype == "error":
                    self._set_busy(False)
                    self._status("Error -- see log.")
                    self._log(f"[ERROR]  {event['value']}")
                    messagebox.showerror("Error", event["value"], parent=self)
        except queue.Empty:
            pass
        finally:
            self.after(50, self._poll_queue)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _set_busy(self, busy: bool) -> None:
        self._busy_flag = busy
        state = "disabled" if busy else "normal"
        for w in (
            self._scan_btn, self._browse_btn, self._recursive_cb,
            self._hidden_cb, self._staging_cb, self._subcats_cb,
            self._max_depth_spin, self._max_dirs_spin, self._timeout_spin,
            self._sched_cb, self._sched_spin,
        ):
            w.configure(state=state)
        self.configure(cursor="watch" if busy else "")
        if not busy:
            self._refresh_persistent_buttons()

    def _set_progress(self, value: float) -> None:
        self._progress_var.set(value)
        self._pct_var.set(f"{int(value)}%")

    def _log(self, message: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", message + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _clear_preview(self) -> None:
        self._preview_tree.delete(*self._preview_tree.get_children())

    def _clear_duplicates(self) -> None:
        self._dup_tree.delete(*self._dup_tree.get_children())

    def _status(self, message: str) -> None:
        self._status_var.set(message)

    # =========================================================================
    # Context menus
    # =========================================================================

    def _open_folder(self, path_str: str) -> None:
        """Open a folder in the system file manager. Cross-platform."""
        folder = Path(path_str)
        if not folder.exists():
            messagebox.showwarning("Not found",
                                   f"Folder does not exist:\n{folder}", parent=self)
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open folder:\n{exc}", parent=self)

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to the system clipboard."""
        self.clipboard_clear()
        self.clipboard_append(text)

    def _on_preview_context(self, event: Any) -> None:
        """Right-click on the Preview tree — show context menu."""
        item = self._preview_tree.identify_row(event.y)
        if not item:
            return
        self._preview_tree.selection_set(item)

        vals  = self._preview_tree.item(item, "values")
        tags  = self._preview_tree.item(item, "tags")
        if not vals:
            return

        # Source path is stored in tags; destination folder is in values[2]
        source_path  = Path(tags[0]) if tags else None
        dest_folder  = vals[2] if len(vals) > 2 else ""

        menu = tk.Menu(self, tearoff=0)
        has_open  = False
        has_copy  = False

        if source_path and source_path.parent.exists():
            menu.add_command(
                label="Open source folder",
                command=lambda: self._open_folder(str(source_path.parent))
            )
            has_open = True
        if dest_folder:
            menu.add_command(
                label="Open destination folder",
                command=lambda: self._open_folder(dest_folder)
            )
            has_open = True

        if source_path:
            has_copy = True
        if dest_folder:
            has_copy = True

        if has_open and has_copy:
            menu.add_separator()

        if source_path:
            menu.add_command(
                label="Copy source path",
                command=lambda: self._copy_to_clipboard(str(source_path))
            )
        if dest_folder:
            menu.add_command(
                label="Copy destination path",
                command=lambda: self._copy_to_clipboard(dest_folder)
            )

        if not has_open and not has_copy:
            return

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_dup_context(self, event: Any) -> None:
        """Right-click on the Duplicates tree — show context menu."""
        item = self._dup_tree.identify_row(event.y)
        if not item:
            return
        self._dup_tree.selection_set(item)

        vals = self._dup_tree.item(item, "values")
        # Group header rows have empty values — skip them
        if not vals or not any(vals):
            return

        filename    = vals[0]
        folder_path = vals[2] if len(vals) > 2 else ""
        full_path   = str(Path(folder_path) / filename) if filename and folder_path else ""

        menu = tk.Menu(self, tearoff=0)

        if folder_path:
            menu.add_command(
                label="Open containing folder",
                command=lambda: self._open_folder(folder_path)
            )

        if full_path or folder_path:
            if folder_path:  # only add separator when there's an item above it
                menu.add_separator()
            if full_path:
                menu.add_command(
                    label="Copy file path",
                    command=lambda: self._copy_to_clipboard(full_path)
                )
            if folder_path:
                menu.add_command(
                    label="Copy folder path",
                    command=lambda: self._copy_to_clipboard(folder_path)
                )
        else:
            return

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _human_size(path: Path) -> str:
    try:
        return _fmt_size(path.stat().st_size)
    except OSError:
        return "?"


def _fmt_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = SimpleOrganizerApp()
    app.mainloop()
