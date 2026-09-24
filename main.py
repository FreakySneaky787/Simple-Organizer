# main.py

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
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
    trash_files,
    undo_last_run,
    undo_specific_run,
)
from utils import DARK_THEME, LIGHT_THEME, safe_expanduser
from theme import FONTS, apply_ttk_theme, float_key, load_fonts, set_titlebar_theme
from icons import badge, icon
from config import load_settings, save_settings
from rules import Rule, CONDITION_TYPES, CONDITION_LABELS, load_rules, save_rules
from scheduler import OrganizerScheduler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_TITLE    = "Simple Organizer"
APP_VERSION  = "3.3.1"
MIN_W, MIN_H = 980, 720
SIDEBAR_W    = 268

_LOG_TAGS = {
    "[ERROR]":     "error",
    "[WARN]":      "warn",
    "[LIMIT]":     "warn",
    "[TIMEOUT]":   "warn",
    "[DEPTH]":     "muted",
    "[SKIP]":      "muted",
    "[MOVED]":     "ok",
    "[STAGED]":    "ok",
    "[UNDONE]":    "ok",
    "[COMMITTED]": "ok",
    "[REVERTED]":  "ok",
    "[TRASHED]":   "ok",
    "[SCHEDULE]":  "info",
}


# ---------------------------------------------------------------------------
# Small widgets
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
            border = ttk.Frame(self._win, style="Tooltip.TFrame", padding=1)
            border.pack()
            ttk.Label(border, text=self._text, style="Tooltip.TLabel",
                      justify="left", wraplength=320).pack()
        except Exception:
            # Widget may have been destroyed before the timer fired.
            self._win = None


class _AutoScrollbar(ttk.Scrollbar):
    """Scrollbar that hides itself while everything fits."""

    def set(self, first: float | str, last: float | str) -> None:
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        super().set(first, last)


class _Stepper(ttk.Frame):
    """Numeric input with − and + buttons. Also steps with the mouse wheel and arrow keys."""

    def __init__(self, parent: tk.Misc, variable: tk.IntVar | tk.DoubleVar,
                 low: float, high: float, step: float, width: int = 6,
                 command: Any = None) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self._var, self._low, self._high, self._step = variable, low, high, step
        self._command = command

        app: SimpleOrganizerApp = self._root()  # type: ignore[assignment]
        side = app._px(26)

        def square_button(glyph: str, direction: int) -> ttk.Button:
            holder = ttk.Frame(self, style="Panel.TFrame", width=side, height=side)
            holder.pack_propagate(False)
            holder.pack(side="left")
            button = ttk.Button(holder, style="Step.TButton",
                                command=lambda: self._nudge(direction))
            button.pack(fill="both", expand=True)
            return app._with_icon(button, glyph)

        self._minus = square_button("minus", -1)
        self._entry = ttk.Entry(self, textvariable=variable, width=width,
                                justify="center", style="Step.TEntry")
        self._entry.pack(side="left", fill="y", padx=4)
        self._plus = square_button("plus", 1)

        self._entry.bind("<Up>",         lambda _e: self._nudge(1))
        self._entry.bind("<Down>",       lambda _e: self._nudge(-1))
        self._entry.bind("<MouseWheel>", lambda e: self._nudge(1 if e.delta > 0 else -1))
        self._entry.bind("<Button-4>",   lambda _e: self._nudge(1))
        self._entry.bind("<Button-5>",   lambda _e: self._nudge(-1))
        self._entry.bind("<Return>",     lambda _e: self._nudge(0))
        self._entry.bind("<FocusOut>",   lambda _e: self._nudge(0))

    def _nudge(self, direction: int) -> str:
        if str(self._entry.cget("state")) == "disabled":
            return "break"
        try:
            value = self._var.get()
        except tk.TclError:
            value = self._low
        value = min(self._high, max(self._low, value + direction * self._step))
        self._var.set(int(value) if isinstance(self._var, tk.IntVar) else value)
        if self._command:
            self._command()
        return "break"

    def configure(self, cnf: Any = None, **kw: Any) -> Any:
        state = kw.pop("state", None)
        if state is not None:
            for widget in (self._minus, self._entry, self._plus):
                widget.configure(state=state)
        if cnf or kw:
            return super().configure(cnf, **kw)
        return None

    config = configure


# ---------------------------------------------------------------------------
# In-app dialogs
# ---------------------------------------------------------------------------

def _chroma_key(window: tk.Toplevel, theme: dict[str, str]) -> None:
    """Make the square corners around a Float.TFrame card see-through (Windows only)."""
    key = float_key(theme)
    window.configure(bg=key)
    if sys.platform == "win32":
        window.attributes("-transparentcolor", key)


def _set_alpha(window: tk.Toplevel, alpha: float) -> None:
    try:
        window.attributes("-alpha", alpha)
    except tk.TclError:
        pass


class _Overlay(tk.Toplevel):
    """Modal card centred over the main window, with a title bar, body and footer."""

    _FADE_STEPS = 5

    def __init__(self, parent: tk.Misc, title: str) -> None:
        app: SimpleOrganizerApp = parent._root()  # type: ignore[attr-defined]
        self._app = app

        super().__init__(app)
        self.overrideredirect(True)
        _set_alpha(self, 0.0)
        _chroma_key(self, app._theme)

        card = ttk.Frame(self, style="Float.TFrame", padding=3)
        card.pack(fill="both", expand=True)

        head = ttk.Frame(card, style="Panel.TFrame", padding=(18, 10, 10, 10))
        head.pack(fill="x")
        ttk.Label(head, text=title, style="DialogTitle.TLabel").pack(side="left")
        ttk.Button(
            head, style="Card.Ghost.TButton", command=self.destroy,
            image=(icon(self, "x", app._px(14), app._theme["fg_dim"]),
                   "active", icon(self, "x", app._px(14), app._theme["fg"])),
        ).pack(side="right")
        ttk.Frame(card, style="Rule.TFrame", height=1).pack(fill="x")

        self.body = ttk.Frame(card, style="Panel.TFrame", padding=(20, 16, 20, 18))
        self.body.pack(fill="both", expand=True)

        ttk.Frame(card, style="Rule.TFrame", height=1).pack(fill="x")
        self.footer = ttk.Frame(card, style="Panel.TFrame", padding=(18, 12))
        self.footer.pack(fill="x")

        self.bind("<Escape>", lambda _e: self.destroy())

    def button(self, text: str, command: Any, primary: bool = False) -> ttk.Button:
        """Add a footer button; buttons are laid out right to left."""
        btn = ttk.Button(self.footer, text=text, command=command,
                         style="Card.Primary.TButton" if primary else "Card.TButton")
        btn.pack(side="right", padx=(8, 0))
        return btn

    def show(self, focus: tk.Widget | None = None) -> None:
        self._app._overlays.append(self)
        self.follow()
        self.grab_set()
        (focus or self).focus_force()
        self._fade(1)

    def follow(self) -> None:
        """Centre the card on the main window."""
        app = self._app
        # Raise first: raising an unmapped borderless window on Windows resets it to 0,0.
        self.lift()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        self.update_idletasks()
        cw, ch = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"{cw}x{ch}+{x + (w - cw) // 2}+{y + (h - ch) // 2}")
        # Changing the alpha before the geometry is applied snaps the window back to 0,0.
        self.update_idletasks()

    def _fade(self, step: int) -> None:
        if not self.winfo_exists():
            return
        _set_alpha(self, step / self._FADE_STEPS)
        if step < self._FADE_STEPS:
            self.after(15, self._fade, step + 1)

    def destroy(self) -> None:
        if self in self._app._overlays:
            self._app._overlays.remove(self)
        super().destroy()


class _HistoryDialog(_Overlay):
    def __init__(self, parent: "SimpleOrganizerApp") -> None:
        super().__init__(parent, "Undo history")
        self._build()
        self._load()
        self.show(self._tree)

    def _build(self) -> None:
        f = self.body
        ttk.Label(f, text="Pick a run to restore. Newest first.",
                  style="CardHint.TLabel").pack(anchor="w", pady=(0, 10))

        box = ttk.Frame(f, style="Panel.TFrame")
        box.pack(fill="both", expand=True)
        box.columnconfigure(0, weight=1)
        self._tree = ttk.Treeview(box, show="tree", selectmode="browse", height=9)
        self._tree.column("#0", width=420)
        sb = _AutoScrollbar(box, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<Double-1>", lambda _e: self._on_undo())
        self._tree.bind("<Return>",   lambda _e: self._on_undo())
        self._tree.tag_configure("empty", foreground=self._app._theme["fg_muted"])

        ttk.Label(
            f,
            text="Undoing an older run may partially fail if files have moved since.",
            style="CardHint.TLabel",
        ).pack(anchor="w", pady=(10, 0))

        self.button("Close", self.destroy)
        self._undo_btn = self.button("Undo selected", self._on_undo, primary=True)

    def _load(self) -> None:
        self._entries = list_undo_history()
        self._tree.delete(*self._tree.get_children())
        if not self._entries:
            self._tree.insert("", "end", text="No history available.", tags=("empty",))
            self._undo_btn.configure(state="disabled")
            return
        for i, e in enumerate(self._entries):
            self._tree.insert("", "end", iid=str(i), text=e["label"])
        self._tree.selection_set("0")
        self._tree.focus("0")

    def _on_undo(self) -> None:
        sel = self._tree.selection()
        if not sel or not self._entries:
            return
        entry = self._entries[int(sel[0])]
        self.destroy()
        self._app._undo_specific(entry["file_path"])


class _RuleDialog(_Overlay):
    def __init__(self, parent: "SimpleOrganizerApp", rule: Rule | None = None) -> None:
        super().__init__(parent, "Edit rule" if rule else "New rule")
        self._rule  = rule
        self.result: Rule | None = None
        name_entry = self._build(rule)
        self.show(name_entry)

    def _build(self, rule: Rule | None) -> ttk.Entry:
        f = self.body
        f.columnconfigure(0, weight=1)

        def label(r: int, text: str) -> None:
            ttk.Label(f, text=text, style="CardDim.TLabel").grid(
                row=r, column=0, sticky="w", pady=(0 if r == 0 else 10, 3))

        def hint(r: int, text: str | None = None, var: tk.StringVar | None = None) -> None:
            ttk.Label(f, text=text or "", textvariable=var or "", style="CardHint.TLabel").grid(
                row=r, column=0, sticky="w", pady=(3, 0))

        label(0, "Name")
        self._name_var = tk.StringVar(value=rule.name if rule else "")
        name_entry = ttk.Entry(f, textvariable=self._name_var, width=38, style="Card.TEntry")
        name_entry.grid(row=1, column=0, sticky="ew")

        label(2, "Condition")
        self._ctype_var = tk.StringVar(value=rule.condition_type if rule else CONDITION_TYPES[0])
        cb = ttk.Combobox(f, textvariable=self._ctype_var, values=CONDITION_TYPES,
                          state="readonly", width=36, style="Card.TCombobox")
        cb.grid(row=3, column=0, sticky="ew")
        cb.bind("<<ComboboxSelected>>", self._update_hint)

        label(4, "Value")
        self._val_var = tk.StringVar(value=rule.condition_value if rule else "")
        ttk.Entry(f, textvariable=self._val_var, width=38, style="Card.TEntry").grid(
            row=5, column=0, sticky="ew")
        self._hint_var = tk.StringVar()
        hint(6, var=self._hint_var)
        self._update_hint()

        label(7, "Target folder")
        self._folder_var = tk.StringVar(value=rule.target_folder if rule else "")
        ttk.Entry(f, textvariable=self._folder_var, width=38, style="Card.TEntry").grid(
            row=8, column=0, sticky="ew")
        hint(9, "Subfolder name inside the scanned folder.")

        self._enabled_var = tk.BooleanVar(value=rule.enabled if rule else True)
        ttk.Checkbutton(f, text="Enabled", variable=self._enabled_var,
                        style="Card.TCheckbutton").grid(row=10, column=0, sticky="w", pady=(14, 0))

        self.button("Cancel", self.destroy)
        self.button("Save", self._ok, primary=True)
        self.bind("<Return>", lambda _e: self._ok())
        return name_entry

    def _update_hint(self, _event: Any = None) -> None:
        self._hint_var.set(CONDITION_LABELS.get(self._ctype_var.get(), ""))

    def _ok(self) -> None:
        name   = self._name_var.get().strip()
        folder = self._folder_var.get().strip()
        value  = self._val_var.get().strip()
        ctype  = self._ctype_var.get()

        if not name or not folder or not value:
            _showwarning("Incomplete",
                         "Name, Value, and Target Folder are required.", parent=self)
            return

        numeric_types = {"min_size_mb", "max_size_mb", "older_than_days", "newer_than_days"}
        if ctype in numeric_types:
            try:
                parsed = float(value)
                if parsed < 0:
                    raise ValueError("negative")
            except ValueError:
                _showwarning(
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


class _MessageDialog(_Overlay):
    KINDS = {
        "question": ("question", "accent"),
        "info":     ("info",     "accent"),
        "success":  ("check",    "success"),
        "warning":  ("warning",  "warning"),
        "error":    ("x-circle", "danger"),
    }

    def __init__(self, parent: tk.Misc, title: str, message: str, kind: str) -> None:
        super().__init__(parent, title)
        self.result = False
        app = self._app

        glyph, colour = self.KINDS[kind]
        ttk.Label(self.body, style="Card.TLabel",
                  image=icon(self, glyph, app._px(26), app._theme[colour])).grid(
            row=0, column=0, sticky="n", padx=(0, 14))
        ttk.Label(self.body, text=message, style="Card.TLabel", wraplength=app._px(400),
                  justify="left").grid(row=0, column=1, sticky="w")

        if kind == "question":
            self.button("Cancel", self.destroy)
            default = self.button("Continue", self._accept, primary=True)
        else:
            default = self.button("OK", self._accept, primary=True)

        self.bind("<Return>", lambda _e: self._accept())
        self.show(default)
        self.wait_window(self)

    def _accept(self) -> None:
        self.result = True
        self.destroy()


def _askyesno(title: str, message: str, parent: tk.Misc) -> bool:
    return _MessageDialog(parent, title, message, "question").result


def _showinfo(title: str, message: str, parent: tk.Misc) -> None:
    _MessageDialog(parent, title, message, "info")


def _showwarning(title: str, message: str, parent: tk.Misc) -> None:
    _MessageDialog(parent, title, message, "warning")


def _showerror(title: str, message: str, parent: tk.Misc) -> None:
    _MessageDialog(parent, title, message, "error")


class _Toast(tk.Toplevel):
    """Short notification that drops in at the top of the main window and fades out."""

    _SHOW_MS = {"success": 3000, "info": 3000, "warning": 4500, "error": 5500}

    def __init__(self, app: "SimpleOrganizerApp", title: str, message: str, kind: str) -> None:
        super().__init__(app)
        self._app = app
        self.overrideredirect(True)
        _set_alpha(self, 0.0)
        _chroma_key(self, app._theme)

        t = app._theme
        glyph, colour = _MessageDialog.KINDS[kind]
        card = ttk.Frame(self, style="Float.TFrame", padding=(14, 10, 8, 10))
        card.pack(fill="both", expand=True)
        card.columnconfigure(1, weight=1)
        ttk.Label(card, style="Card.TLabel",
                  image=badge(self, glyph, app._px(32), app._px(18), t[colour], t["accent_fg"])).grid(
            row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(card, text=title, style="ToastTitle.TLabel").grid(row=0, column=1, sticky="sw")
        ttk.Label(card, text=message, style="CardDim.TLabel",
                  wraplength=app._px(320)).grid(row=1, column=1, sticky="nw")
        ttk.Button(
            card, style="Card.Ghost.TButton", command=self.destroy,
            image=(icon(self, "x", app._px(12), t["fg_muted"]),
                   "active", icon(self, "x", app._px(12), t["fg"])),
        ).grid(row=0, column=2, rowspan=2, sticky="n", padx=(10, 0))

        self.update_idletasks()
        self._width = max(self.winfo_reqwidth(), app._px(360))
        self._slide(0)
        self.after(self._SHOW_MS[kind], self._fade_out, 0)

    def _place(self, offset: int) -> None:
        app = self._app
        x = app.winfo_rootx() + (app.winfo_width() - self._width) // 2
        y = app.winfo_rooty() + app._px(14) - offset
        self.geometry(f"{self._width}x{self.winfo_reqheight()}+{x}+{y}")
        self.update_idletasks()

    def _slide(self, step: int) -> None:
        if not self.winfo_exists():
            return
        progress = 1 - (1 - step / 8) ** 3
        self._place(round(self._app._px(16) * (1 - progress)))
        _set_alpha(self, progress)
        if step < 8:
            self.after(16, self._slide, step + 1)

    def _fade_out(self, step: int) -> None:
        if not self.winfo_exists():
            return
        _set_alpha(self, 1 - step / 6)
        if step < 6:
            self.after(20, self._fade_out, step + 1)
        else:
            self.destroy()

    def destroy(self) -> None:
        if self._app._toast is self:
            self._app._toast = None
        super().destroy()


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class SimpleOrganizerApp(tk.Tk):
    """Root window that owns all widgets and orchestrates background threads."""

    def __init__(self) -> None:
        super().__init__()
        load_fonts(self)

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
        self._busy_flag:      bool              = False
        self._dup_groups:     dict[str, list[str]] = {}  # group_node -> [file_iids]   # M5 fix — initialised here

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
        self._schedule_status_var: tk.StringVar = tk.StringVar(value="Off")

        self._theme:       dict[str, str]              = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._style        = ttk.Style(self)
        self._resize_job:  str | None = None
        self._icon_widgets: list[tuple[ttk.Widget, str, str]] = []
        self._overlays:     list[_Overlay] = []
        self._toast:        _Toast | None = None

        # S1 fix: pass log_callback to scheduler so errors surface in the UI
        self._scheduler = OrganizerScheduler(
            callback=self._on_schedule_fire,
            log_callback=lambda msg: self._event_queue.put({"type": "log", "value": msg}),
        )

        # ── Build & configure ─────────────────────────────────────────────────
        self._build_ui()
        self._apply_theme()
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

        self._build_header()

        body = ttk.Frame(self, padding=(16, 0, 16, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_sidebar(body)
        self._build_workspace(body)

        self._build_status_bar()

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(16, 14, 16, 14))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)

        ttk.Label(header, text=APP_TITLE.upper(), style="Brand.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text=f"v{APP_VERSION}", style="Version.TLabel").grid(
            row=0, column=1, sticky="w", padx=(8, 24), pady=(2, 0))

        self._folder_var   = tk.StringVar(value=str(self._folder))
        self._folder_entry = ttk.Entry(
            header, textvariable=self._folder_var, state="readonly", font=FONTS["mono"])
        self._folder_entry.grid(row=0, column=2, sticky="ew", ipady=1)
        _Tooltip(self._folder_entry, "Folder to organise. You can also drop a folder here.")

        self._browse_btn = self._with_icon(
            ttk.Button(header, text="Browse…", command=self._browse_folder), "folder-open")
        self._browse_btn.grid(row=0, column=3, padx=(8, 0))

        self._theme_btn = ttk.Button(header, style="Ghost.TButton",
                                     command=self._toggle_dark_mode)
        self._theme_btn.grid(row=0, column=4, padx=(8, 0))
        _Tooltip(self._theme_btn, "Switch between light and dark theme.")

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        side = ttk.Frame(parent, width=SIDEBAR_W)
        side.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        side.pack_propagate(False)

        scan = self._card(side, "Scan")

        self._recursive_cb = ttk.Checkbutton(
            scan, text="Scan subdirectories", variable=self._recursive,
            style="Card.TCheckbutton", command=self._save_settings)
        self._recursive_cb.pack(anchor="w")

        self._hidden_cb = ttk.Checkbutton(
            scan, text="Include hidden files", variable=self._include_hidden,
            style="Card.TCheckbutton", command=self._save_settings)
        self._hidden_cb.pack(anchor="w")

        self._subcats_cb = ttk.Checkbutton(
            scan, text="Use sub-categories", variable=self._use_subcats,
            style="Card.TCheckbutton", command=self._on_subcats_toggle)
        self._subcats_cb.pack(anchor="w")
        _Tooltip(
            self._subcats_cb,
            "Sort files into sub-folders inside each category.\n"
            "Examples:\n"
            "  Images/Photos/    Images/Editing/    Images/Raw/\n"
            "  Documents/PDFs/   Documents/Word/    Documents/Spreadsheets/\n"
            "  Music/Lossless/   Code/Python/       Code/JavaScript/\n\n"
            "Off by default. Does not affect custom Rules."
        )

        limits = ttk.Frame(scan, style="Panel.TFrame")
        limits.pack(fill="x", pady=(10, 0))
        limits.columnconfigure(0, weight=1)
        self._max_depth_spin = self._limit_row(
            limits, 0, "Max depth", self._max_depth, 1, 50, 1)
        self._max_dirs_spin = self._limit_row(
            limits, 1, "Max folders", self._max_dirs, 100, 500_000, 1000)
        self._timeout_spin = self._limit_row(
            limits, 2, "Timeout (s)", self._scan_timeout, 5, 300, 5)

        staging = self._card(side, "Staging")

        self._staging_cb = ttk.Checkbutton(
            staging, text="Use staging mode", variable=self._use_staging,
            style="Card.TCheckbutton", command=self._on_staging_toggle)
        self._staging_cb.pack(anchor="w")
        _Tooltip(self._staging_cb,
                 "Move files to a temporary staging area first.\n"
                 "Use Commit to finalise, or Revert to cancel.")

        staging_btns = ttk.Frame(staging, style="Panel.TFrame")
        staging_btns.pack(fill="x", pady=(10, 0))
        staging_btns.columnconfigure((0, 1), weight=1, uniform="staging")

        self._commit_btn = self._with_icon(ttk.Button(
            staging_btns, text="Commit", style="Card.TButton",
            command=self._confirm_and_commit, state="disabled"), "check")
        self._commit_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        _Tooltip(self._commit_btn, "Move staged files to their final category folders.")

        self._revert_btn = self._with_icon(ttk.Button(
            staging_btns, text="Revert", style="Card.Danger.TButton",
            command=self._confirm_and_revert, state="disabled"), "arrow-u-up-left", "danger")
        self._revert_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        _Tooltip(self._revert_btn, "Send staged files back to where they came from.")

        sched = self._card(side, "Auto-organize")

        self._sched_cb = ttk.Checkbutton(
            sched, text="Run on a schedule",
            variable=self._schedule_enabled, style="Card.TCheckbutton",
            command=self._on_schedule_toggle)
        self._sched_cb.pack(anchor="w")
        _Tooltip(self._sched_cb,
                 "Automatically scan and organise the selected folder on the set interval.\n"
                 "Runs silently without confirmation dialogs.")

        every = ttk.Frame(sched, style="Panel.TFrame")
        every.pack(fill="x", pady=(8, 0))
        ttk.Label(every, text="Every", style="CardDim.TLabel").pack(side="left")
        self._sched_spin = _Stepper(
            every, self._schedule_interval, 1, 1440, 15, width=5,
            command=self._on_schedule_toggle)
        self._sched_spin.pack(side="left", padx=8)
        ttk.Label(every, text="minutes", style="CardDim.TLabel").pack(side="left")

        ttk.Label(sched, textvariable=self._schedule_status_var,
                  style="CardHint.TLabel").pack(anchor="w", pady=(8, 0))

    def _card(self, parent: ttk.Frame, title: str) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(14, 12, 14, 14))
        card.pack(fill="x", pady=(0, 12))
        ttk.Label(card, text=title.upper(), style="CardTitle.TLabel").pack(
            anchor="w", pady=(0, 8))
        return card

    def _limit_row(self, parent: ttk.Frame, row: int, text: str,
                   var: tk.IntVar | tk.DoubleVar, low: float, high: float,
                   step: float) -> _Stepper:
        ttk.Label(parent, text=text, style="CardDim.TLabel").grid(
            row=row, column=0, sticky="w", pady=3)
        stepper = _Stepper(parent, var, low, high, step)
        stepper.grid(row=row, column=1, sticky="e", pady=3)
        return stepper

    def _build_workspace(self, parent: ttk.Frame) -> None:
        work = ttk.Frame(parent)
        work.grid(row=0, column=1, sticky="nsew")
        work.columnconfigure(0, weight=1)
        work.rowconfigure(1, weight=1)

        bar = ttk.Frame(work)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self._scan_btn = self._with_icon(ttk.Button(
            bar, text="Scan", style="Primary.TButton", command=self._start_scan),
            "magnifying-glass", "primary")
        self._scan_btn.pack(side="left", padx=(0, 8))

        self._organize_btn = self._with_icon(ttk.Button(
            bar, text="Organize", style="Primary.TButton",
            command=self._confirm_and_organize, state="disabled"), "folders", "primary")
        self._organize_btn.pack(side="left")

        ttk.Frame(bar, style="Rule.TFrame", width=1).pack(side="left", fill="y", padx=12, pady=4)

        self._undo_btn = self._with_icon(ttk.Button(
            bar, text="Undo last", command=self._confirm_and_undo, state="disabled"),
            "arrow-counter-clockwise")
        self._undo_btn.pack(side="left", padx=(0, 8))

        self._history_btn = self._with_icon(ttk.Button(
            bar, text="History…", command=self._open_history_dialog, state="disabled"),
            "clock-counter-clockwise")
        self._history_btn.pack(side="left")

        _Tooltip(self._scan_btn,     "Scan the selected folder and preview planned moves. (Ctrl+R)")
        _Tooltip(self._organize_btn, "Move files into category subfolders. Shows total size first. (Ctrl+O)")
        _Tooltip(self._undo_btn,     "Restore all files moved in the last organise run. (Ctrl+Z)")
        _Tooltip(self._history_btn,  "Browse and undo any of the last 20 organise runs.")

        panel = ttk.Frame(work, style="Card.TFrame", padding=3)
        panel.grid(row=1, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        self._tab_strip = ttk.Frame(panel, style="Panel.TFrame")
        self._tab_strip.grid(row=0, column=0, sticky="ew")
        self._summary_var = tk.StringVar()
        ttk.Label(self._tab_strip, textvariable=self._summary_var,
                  style="Summary.TLabel").pack(side="right", padx=14)
        ttk.Frame(panel, style="Rule.TFrame", height=1).grid(row=1, column=0, sticky="ew")

        self._notebook = ttk.Notebook(panel, style="Bare.TNotebook")
        self._notebook.grid(row=2, column=0, sticky="nsew")
        self._notebook.bind("<<NotebookTabChanged>>", lambda _e: self._sync_tabs())
        self._tabs: list[tuple[ttk.Label, ttk.Label, ttk.Frame, str]] = []

        self._build_preview_tab()
        self._build_duplicates_tab()
        self._build_log_tab()
        self._build_rules_tab()

    def _build_preview_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="Panel.TFrame")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._preview_tab_idx = self._add_tab(tab, "Preview", "eye")

        self._preview_tree = self._make_table(tab, ("file", "category", "destination"))
        self._preview_tree.heading("file",        text="FILE",        anchor="w")
        self._preview_tree.heading("category",    text="CATEGORY",    anchor="w")
        self._preview_tree.heading("destination", text="DESTINATION", anchor="w")
        self._preview_tree.column("file",        width=260, anchor="w", stretch=True)
        self._preview_tree.column("category",    width=130, anchor="w", stretch=False)
        self._preview_tree.column("destination", width=320, anchor="w", stretch=True)
        self._preview_tree.bind("<Button-3>", self._on_preview_context)

        self._preview_empty = self._with_icon(ttk.Label(
            tab, text="Pick a folder and press Scan to see what would move.",
            style="Empty.TLabel", compound="top"), "folder-dashed", "empty")
        self._sync_empty(self._preview_tree, self._preview_empty)

    def _build_duplicates_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="Panel.TFrame")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._dup_tab_idx = self._add_tab(tab, "Duplicates", "copy")

        self._dup_tree = self._make_table(
            tab, ("file", "size", "location"), show="tree headings", selectmode="extended")
        self._dup_tree.heading("#0",       text="GROUP",  anchor="w")
        self._dup_tree.heading("file",     text="FILE",   anchor="w")
        self._dup_tree.heading("size",     text="SIZE",   anchor="e")
        self._dup_tree.heading("location", text="FOLDER", anchor="w")
        self._dup_tree.column("#0",        width=110, anchor="w", stretch=False)
        self._dup_tree.column("file",      width=220, anchor="w", stretch=True)
        self._dup_tree.column("size",      width=90,  anchor="e", stretch=False)
        self._dup_tree.column("location",  width=360, anchor="w", stretch=True)
        self._dup_tree.bind("<Button-3>", self._on_dup_context)
        self._dup_tree.bind("<<TreeviewSelect>>", self._on_dup_select)
        self._dup_tree.bind("<Button-1>", self._on_dup_click)

        self._dup_empty = self._with_icon(ttk.Label(
            tab, text="No duplicates found yet.", style="Empty.TLabel", compound="top"),
            "copy", "empty")
        self._sync_empty(self._dup_tree, self._dup_empty)

        ttk.Frame(tab, style="Rule.TFrame", height=1).grid(
            row=2, column=0, columnspan=2, sticky="ew")
        action = ttk.Frame(tab, style="Panel.TFrame", padding=(12, 10))
        action.grid(row=3, column=0, columnspan=2, sticky="ew")

        self._trash_btn = self._with_icon(ttk.Button(
            action, text="Move selected to Trash",
            style="Card.Danger.TButton", command=self._confirm_and_trash,
            state="disabled",
        ), "trash", "danger")
        self._trash_btn.pack(side="left")
        _Tooltip(
            self._trash_btn,
            "Move selected duplicate files to the system Trash/Recycle Bin.\n"
            "Files can be restored from Trash.\n"
            "Select files with click / Ctrl+click / Shift+click.\n"
            "At least one file per group must remain unselected."
        )

        self._dup_sel_var = tk.StringVar(value="")
        ttk.Label(action, textvariable=self._dup_sel_var,
                  style="CardDim.TLabel").pack(side="left", padx=(12, 0))
        ttk.Label(action, text="Keep at least one file in every group.",
                  style="CardHint.TLabel").pack(side="right")

    def _build_log_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="Panel.TFrame")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self._log_tab_idx = self._add_tab(tab, "Log", "terminal-window")

        log_vsb = _AutoScrollbar(tab, orient="vertical")
        self._log_box = tk.Text(
            tab, wrap="word", font=FONTS["mono"], state="disabled",
            borderwidth=0, relief="flat", highlightthickness=0,
            padx=14, pady=10, spacing1=2, spacing3=2,
            yscrollcommand=log_vsb.set)
        log_vsb.configure(command=self._log_box.yview)
        self._log_box.grid(row=0, column=0, sticky="nsew")
        log_vsb.grid(row=0, column=1, sticky="ns")

        ttk.Frame(tab, style="Rule.TFrame", height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew")
        action = ttk.Frame(tab, style="Panel.TFrame", padding=(12, 10))
        action.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._with_icon(ttk.Button(action, text="Clear log", style="Card.TButton",
                                   command=self._clear_log), "eraser").pack(side="right")

    def _build_rules_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="Panel.TFrame")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        self._add_tab(tab, "Rules", "funnel")

        bar = ttk.Frame(tab, style="Panel.TFrame", padding=(12, 10))
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._with_icon(ttk.Button(bar, text="Add rule", style="Card.Primary.TButton",
                                   command=self._rule_add), "plus", "primary").pack(
            side="left", padx=(0, 8))
        self._with_icon(ttk.Button(bar, text="Edit", style="Card.TButton",
                                   command=self._rule_edit), "pencil-simple").pack(
            side="left", padx=(0, 8))
        up = self._with_icon(ttk.Button(bar, style="Card.TButton",
                                        command=lambda: self._rule_move(-1)), "arrow-up")
        up.pack(side="left", padx=(0, 4))
        down = self._with_icon(ttk.Button(bar, style="Card.TButton",
                                          command=lambda: self._rule_move(1)), "arrow-down")
        down.pack(side="left")
        _Tooltip(up,   "Move rule up. Rules are checked top to bottom.")
        _Tooltip(down, "Move rule down.")
        self._with_icon(ttk.Button(bar, text="Delete", style="Card.Danger.TButton",
                                   command=self._rule_delete), "trash", "danger").pack(side="right")

        ttk.Frame(tab, style="Rule.TFrame", height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew")

        cols = ("enabled", "name", "condition", "value", "target")
        self._rules_tree = self._make_table(tab, cols, row=2)
        self._rules_tree.heading("enabled",   text="")
        self._rules_tree.heading("name",      text="NAME",          anchor="w")
        self._rules_tree.heading("condition", text="CONDITION",     anchor="w")
        self._rules_tree.heading("value",     text="VALUE",         anchor="w")
        self._rules_tree.heading("target",    text="TARGET FOLDER", anchor="w")
        self._rules_tree.column("enabled",   width=40,  anchor="center", stretch=False)
        self._rules_tree.column("name",      width=160, anchor="w",      stretch=True)
        self._rules_tree.column("condition", width=140, anchor="w",      stretch=False)
        self._rules_tree.column("value",     width=120, anchor="w",      stretch=False)
        self._rules_tree.column("target",    width=160, anchor="w",      stretch=True)
        self._rules_tree.bind("<Button-1>", self._on_rules_click)
        self._rules_tree.bind("<Double-1>", self._on_rules_double_click)
        self._rules_tree.bind("<space>",    lambda _e: self._toggle_selected_rule())

        self._rules_empty = self._with_icon(ttk.Label(
            tab, text="No rules yet. Rules send files to a folder by extension, name, size or age.",
            style="Empty.TLabel", compound="top"), "funnel", "empty")

        ttk.Frame(tab, style="Rule.TFrame", height=1).grid(
            row=4, column=0, columnspan=2, sticky="ew")
        ttk.Label(
            tab,
            text="Rules run before extension-based categorisation. First match wins. "
                 "Click the dot to turn a rule on or off.",
            style="CardHint.TLabel", padding=(12, 10),
        ).grid(row=5, column=0, columnspan=2, sticky="w")

        self._refresh_rules_tree()

    def _build_status_bar(self) -> None:
        ttk.Frame(self, style="Rule.TFrame", height=1).grid(row=2, column=0, sticky="ew")

        bar = ttk.Frame(self, style="Bar.TFrame", padding=(16, 5))
        bar.grid(row=3, column=0, sticky="ew")
        bar.columnconfigure(2, weight=1)

        self._state_dot = ttk.Label(bar, text="●", style="Idle.TLabel")
        self._state_dot.grid(row=0, column=0)
        self._state_var = tk.StringVar(value="READY")
        ttk.Label(bar, textvariable=self._state_var, style="BarState.TLabel").grid(
            row=0, column=1, padx=(6, 14))

        self._status_var = tk.StringVar(value="Pick a folder and press Scan.")
        ttk.Label(bar, textvariable=self._status_var, style="Bar.TLabel").grid(
            row=0, column=2, sticky="w")

        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress = ttk.Progressbar(
            bar, variable=self._progress_var, maximum=100.0, mode="determinate", length=160)
        self._progress.grid(row=0, column=3, padx=(14, 8))

        self._pct_var = tk.StringVar(value="0%")
        ttk.Label(bar, textvariable=self._pct_var, style="Pct.TLabel",
                  width=4, anchor="e").grid(row=0, column=4)

        ttk.Label(
            bar,
            text="Ctrl+R scan   Ctrl+O organize   Ctrl+Z undo   Ctrl+Q quit",
            style="BarMuted.TLabel",
        ).grid(row=0, column=5, padx=(20, 0))

    def _make_table(self, parent: ttk.Frame, columns: tuple[str, ...], row: int = 0,
                    show: str = "headings", selectmode: str = "browse") -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show=show, selectmode=selectmode)
        vsb = _AutoScrollbar(parent, orient="vertical",   command=tree.yview)
        hsb = _AutoScrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=row, column=0, sticky="nsew")
        vsb.grid(row=row, column=1, sticky="ns")
        hsb.grid(row=row + 1, column=0, sticky="ew")
        return tree

    def _sync_empty(self, tree: ttk.Treeview, label: ttk.Label) -> None:
        if tree.get_children():
            label.place_forget()
        else:
            label.place(in_=tree, relx=0.5, rely=0.45, anchor="center")

    # =========================================================================
    # Tabs
    # =========================================================================

    def _add_tab(self, frame: ttk.Frame, title: str, glyph: str) -> int:
        idx = len(self._tabs)
        self._notebook.add(frame)

        tab = ttk.Frame(self._tab_strip, style="Panel.TFrame", cursor="hand2")
        tab.pack(side="left")
        inner = ttk.Frame(tab, style="Panel.TFrame", padding=(14, 8, 14, 6))
        inner.pack()
        label = ttk.Label(inner, text=title.upper(), style="Tab.TLabel", compound="left")
        label.pack(side="left")
        badge = ttk.Label(inner, style="Badge.TLabel")
        line = ttk.Frame(tab, style="TabLine.TFrame", height=2)
        line.pack(fill="x")

        for widget in (tab, inner, label, badge):
            widget.bind("<Button-1>", lambda _e, i=idx: self._notebook.select(i))
        self._tabs.append((label, badge, line, glyph))
        return idx

    def _set_tab_count(self, idx: int, count: int) -> None:
        badge = self._tabs[idx][1]
        if count:
            badge.configure(text=str(count))
            badge.pack(side="left", padx=(7, 0))
        else:
            badge.pack_forget()

    def _sync_tabs(self) -> None:
        current = self._notebook.index("current")
        t = self._theme
        for i, (label, badge, line, glyph) in enumerate(self._tabs):
            active = i == current
            label.configure(style="TabActive.TLabel" if active else "Tab.TLabel",
                            image=icon(self, glyph, self._px(14),
                                       t["accent"] if active else t["fg_muted"],
                                       gap=self._px(6)))
            badge.configure(style="BadgeActive.TLabel" if active else "Badge.TLabel")
            line.configure(style="TabLineActive.TFrame" if active else "TabLine.TFrame")

    # =========================================================================
    # Theme
    # =========================================================================

    def _apply_theme(self) -> None:
        t = self._theme
        self.configure(bg=t["bg"])
        apply_ttk_theme(self._style, t)

        self.option_add("*TCombobox*Listbox.background",       t["surface"])
        self.option_add("*TCombobox*Listbox.foreground",       t["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", t["selection"])
        self.option_add("*TCombobox*Listbox.selectForeground", t["selection_fg"])
        self.option_add("*TCombobox*Listbox.font",             FONTS["ui"])

        self._log_box.configure(
            bg=t["surface"], fg=t["fg_dim"],
            insertbackground=t["fg"],
            selectbackground=t["selection"],
            selectforeground=t["selection_fg"],
        )
        for tag, key in (("time", "fg_muted"), ("muted", "fg_muted"), ("ok", "success"),
                         ("warn", "warning"), ("error", "danger"), ("info", "accent")):
            self._log_box.tag_configure(tag, foreground=t[key])

        self._dup_tree.tag_configure("group", background=t["surface_alt"],
                                     foreground=t["fg_dim"], font=FONTS["caption"])
        self._rules_tree.tag_configure("off", foreground=t["fg_muted"])

        self._apply_icons()
        glyph = "sun" if self._dark_mode else "moon"
        self._theme_btn.configure(image=(
            icon(self, glyph, self._px(16), t["fg_dim"]),
            "active", icon(self, glyph, self._px(16), t["fg"])))
        self._sync_tabs()
        set_titlebar_theme(self, self._dark_mode)

    def _toggle_dark_mode(self) -> None:
        self._dark_mode = not self._dark_mode
        self._theme = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._apply_theme()
        self._save_settings()

    def _px(self, size: int) -> int:
        """Scale a 96-dpi pixel size to the current display."""
        return round(size * float(self.tk.call("tk", "scaling")) / (96 / 72))

    _ICON_ROLES = {
        "button":  ("fg_dim",    "fg",        16),
        "primary": ("accent_fg", "accent_fg", 16),
        "danger":  ("danger",    "accent_fg", 16),
        "empty":   ("fg_muted",  "fg_muted",  40),
    }

    def _with_icon(self, widget: Any, glyph: str, role: str = "button") -> Any:
        """Remember the widget so its icon is redrawn in the right colours on theme changes."""
        self._icon_widgets.append((widget, glyph, role))
        return widget

    def _apply_icons(self) -> None:
        t = self._theme
        for widget, glyph, role in self._icon_widgets:
            normal, over, size = self._ICON_ROLES[role]
            beside_text = bool(widget.cget("text")) and role != "empty"
            size = self._px(size if beside_text or role == "empty" else 14)
            gap  = self._px(6) if beside_text else 0
            widget.configure(image=(
                icon(self, glyph, size, t[normal], gap),
                "disabled", icon(self, glyph, size, t["fg_muted"], gap),
                "active",   icon(self, glyph, size, t[over], gap),
            ))
            if beside_text:
                widget.configure(compound="left")

    def _notify(self, title: str, message: str, kind: str = "success") -> None:
        if self._toast:
            self._toast.destroy()
        self._toast = _Toast(self, title, message, kind)

    def _menu(self) -> tk.Menu:
        t = self._theme
        return tk.Menu(
            self, tearoff=0, font=FONTS["ui"], relief="flat", borderwidth=1,
            bg=t["surface_alt"], fg=t["fg"],
            activebackground=t["accent"], activeforeground=t["accent_fg"],
            activeborderwidth=0,
        )


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
            self._schedule_status_var.set(f"Active, runs every {mins} min")
        else:
            self._schedule_status_var.set("Off")

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
                "●" if rule.enabled else "○",
                rule.name, rule.condition_type,
                rule.condition_value, rule.target_folder,
            ), tags=() if rule.enabled else ("off",))
        self._sync_empty(self._rules_tree, self._rules_empty)

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
            _showinfo("No selection", "Select a rule to edit.", parent=self)
            return
        rules = load_rules()
        dlg   = _RuleDialog(self, rules[idx])
        self.wait_window(dlg)
        if dlg.result:
            rules[idx] = dlg.result
            save_rules(rules)
            self._refresh_rules_tree()

    def _on_rules_click(self, event: Any) -> str | None:
        row = self._rules_tree.identify_row(event.y)
        if not row or self._rules_tree.identify_column(event.x) != "#1":
            return None
        self._rules_tree.selection_set(row)
        self._toggle_selected_rule()
        return "break"

    def _on_rules_double_click(self, event: Any) -> None:
        if self._rules_tree.identify_column(event.x) != "#1":
            self._rule_edit()

    def _toggle_selected_rule(self) -> None:
        idx = self._selected_rule_index()
        self._rule_toggle()
        children = self._rules_tree.get_children()
        if idx is not None and idx < len(children):
            self._rules_tree.selection_set(children[idx])
            self._rules_tree.focus(children[idx])

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
        if not _askyesno("Delete Rule",
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
        for overlay in self._overlays:
            overlay.follow()
        if self._toast:
            self._toast._place(0)
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

        self._set_tab_count(self._preview_tab_idx, len(actionable))
        self._sync_empty(self._preview_tree, self._preview_empty)

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
            # _dup_groups: group_node_iid -> list of file iids in that group
            self._dup_groups: dict[str, list[str]] = {}
            for group_idx, group in enumerate(result.duplicate_groups, start=1):
                node = self._dup_tree.insert("", "end", text=f"Group {group_idx}",
                                             values=("", "", ""), open=True,
                                             tags=("group",))
                file_iids: list[str] = []
                for dup in group:
                    iid = self._dup_tree.insert(
                        node, "end",
                        values=(dup.name, _human_size(dup), str(dup.parent)),
                        tags=("file", str(dup)),   # full path in tags
                    )
                    file_iids.append(iid)
                self._dup_groups[node] = file_iids
            self._set_tab_count(self._dup_tab_idx, len(result.duplicate_groups))
            self._sync_empty(self._dup_tree, self._dup_empty)
        else:
            self._log("No duplicate files detected.")

        summary = f"{len(actionable)} to move  ·  {len(skipped)} in place"
        if result.duplicate_groups:
            summary += f"  ·  {len(result.duplicate_groups)} duplicate groups"
        self._summary_var.set(summary)

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
            _showinfo("Nothing to do", "All files are already organised.", parent=self)
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
        confirmed = _askyesno(
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
        self._refresh_persistent_buttons()

        if errors:
            self._log(f"Finished with {len(errors)} error(s). See log.")
            self._status(f"Done -- {len(errors)} error(s).")
            self._notify("Organize finished with errors",
                         f"{len(errors)} file(s) could not be moved. See the log.", "warning")
        elif staging:
            self._log("Files staged. Use Commit or Revert to finalise.")
            self._status("Staging complete -- commit or revert when ready.")
            self._notify("Files staged", "Commit or revert when you are ready.", "info")
        else:
            self._log("All files organised successfully.")
            self._status("Done -- all files organised.")
            self._notify("Folder organised", "All files were moved into their categories.")

    # =========================================================================
    # Undo last run
    # =========================================================================

    def _confirm_and_undo(self) -> None:
        confirmed = _askyesno(
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
            self._notify("Undo finished with errors",
                         f"{len(errors)} file(s) could not be restored. See the log.", "warning")
        else:
            self._log("Undo complete -- files restored to original locations.")
            self._status("Undo complete.")
            self._notify("Undo complete", "Files are back where they were.")

    # =========================================================================
    # Staging commit / revert
    # =========================================================================

    def _confirm_and_commit(self) -> None:
        confirmed = _askyesno(
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
            self._notify("Commit finished with errors",
                         f"{len(errors)} file(s) could not be moved. See the log.", "warning")
        else:
            self._log("Staging committed -- all files moved to final destinations.")
            self._status("Commit complete.")
            self._notify("Staging committed", "Staged files are in their final folders.")

    def _confirm_and_revert(self) -> None:
        confirmed = _askyesno(
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
            self._notify("Revert finished with errors",
                         f"{len(errors)} file(s) could not be restored. See the log.", "warning")
        else:
            self._log("Staging reverted -- all files returned to original locations.")
            self._status("Revert complete.")
            self._notify("Staging reverted", "Staged files are back where they were.")

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
                elif etype == "trash_done":
                    self._handle_trash_done(event["errors"], event["count"])
                elif etype == "schedule_fire":
                    self._run_scheduled_organize()
                elif etype == "error":
                    self._set_busy(False)
                    self._status("Error -- see log.")
                    self._log(f"[ERROR]  {event['value']}")
                    _showerror("Error", event["value"], parent=self)
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
        self._state_var.set("WORKING" if busy else "READY")
        self._state_dot.configure(style="Busy.TLabel" if busy else "Idle.TLabel")
        if not busy:
            self._refresh_persistent_buttons()

    def _set_progress(self, value: float) -> None:
        self._progress_var.set(value)
        self._pct_var.set(f"{int(value)}%")

    def _log(self, message: str) -> None:
        prefix = message.lstrip().split("]", 1)[0] + "]"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", time.strftime("%H:%M:%S  "), "time")
        self._log_box.insert("end", message + "\n", _LOG_TAGS.get(prefix, ""))
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _clear_preview(self) -> None:
        self._preview_tree.delete(*self._preview_tree.get_children())
        self._set_tab_count(self._preview_tab_idx, 0)
        self._summary_var.set("")
        self._sync_empty(self._preview_tree, self._preview_empty)

    def _clear_duplicates(self) -> None:
        self._dup_tree.delete(*self._dup_tree.get_children())
        self._dup_groups = {}
        self._dup_sel_var.set("")
        self._trash_btn.configure(state="disabled")
        self._set_tab_count(self._dup_tab_idx, 0)
        self._sync_empty(self._dup_tree, self._dup_empty)

    def _status(self, message: str) -> None:
        self._status_var.set(message)

    # =========================================================================
    # Duplicate trash
    # =========================================================================

    def _on_dup_click(self, event: Any) -> str | None:
        """Clicking anywhere on a group row opens or closes it."""
        row = self._dup_tree.identify_row(event.y)
        if not row or "group" not in self._dup_tree.item(row, "tags"):
            return None
        self._dup_tree.item(row, open=not self._dup_tree.item(row, "open"))
        return "break"

    def _on_dup_select(self, _event: Any = None) -> None:
        """Update selection label and Trash button state when selection changes."""
        file_iids = self._get_selected_file_iids()
        count     = len(file_iids)
        if count == 0:
            self._dup_sel_var.set("")
            self._trash_btn.configure(state="disabled")
        else:
            self._dup_sel_var.set(f"{count} file(s) selected")
            # Enable only if the selection is valid (not wiping a whole group)
            if self._selection_is_valid(file_iids):
                self._trash_btn.configure(state="normal")
            else:
                self._dup_sel_var.set(f"{count} selected — keep at least 1 per group")
                self._trash_btn.configure(state="disabled")

    def _get_selected_file_iids(self) -> list[str]:
        """Return selected iids that are file rows (not group headers)."""
        return [
            iid for iid in self._dup_tree.selection()
            if "file" in self._dup_tree.item(iid, "tags")
        ]

    def _selection_is_valid(self, file_iids: list[str]) -> bool:
        """Return True if at least one file per group remains unselected."""
        selected_set = set(file_iids)
        for group_node, members in self._dup_groups.items():
            if all(m in selected_set for m in members):
                return False
        return True

    def _confirm_and_trash(self) -> None:
        """Confirm then move selected duplicates to Trash."""
        file_iids = self._get_selected_file_iids()
        if not file_iids:
            return
        if not self._selection_is_valid(file_iids):
            _showwarning(
                "Invalid selection",
                "At least one file per duplicate group must remain.\n"
                "Deselect one file from each fully-selected group.",
                parent=self,
            )
            return

        # Build path list from tags
        paths: list[Path] = []
        for iid in file_iids:
            tags = self._dup_tree.item(iid, "tags")
            for t in tags:
                if t != "file":
                    paths.append(Path(t))
                    break

        # Build preview list for the dialog
        preview = "\n".join(f"  • {p.name}  ({p.parent})" for p in paths[:10])
        if len(paths) > 10:
            preview += f"\n  … and {len(paths) - 10} more"

        confirmed = _askyesno(
            title="Move to Trash",
            message=(
                f"Move {len(paths)} file(s) to the system Trash?\n\n"
                f"{preview}\n\n"
                "Files can be restored from your Trash / Recycle Bin."
            ),
            parent=self,
        )
        if not confirmed:
            return

        self._set_busy(True)
        self._set_progress(0.0)
        self._status(f"Moving {len(paths)} file(s) to Trash...")
        self._notebook.select(self._log_tab_idx)

        t = threading.Thread(target=self._trash_worker, args=(paths,), daemon=True)
        t.start()

    def _trash_worker(self, paths: list[Path]) -> None:
        def progress(c: int, t: int) -> None:
            self._event_queue.put({"type": "progress",
                                   "value": (c / t * 100) if t else 0})
        def log_msg(msg: str) -> None:
            self._event_queue.put({"type": "log", "value": msg})
        try:
            errors = trash_files(paths, log_callback=log_msg,
                                 progress_callback=progress)
            self._event_queue.put({"type": "trash_done", "errors": errors,
                                   "count": len(paths)})
        except Exception as exc:  # noqa: BLE001
            self._event_queue.put({"type": "error", "value": str(exc)})

    def _handle_trash_done(self, errors: list[str], count: int) -> None:
        self._set_busy(False)
        self._set_progress(100.0)
        # Refresh the duplicates view — re-scan to get updated state
        self._clear_duplicates()
        if errors:
            self._log(f"Trash finished with {len(errors)} error(s). See log.")
            self._status(f"Trash done — {len(errors)} error(s).")
            self._notify("Some files were not trashed",
                         f"{len(errors)} file(s) failed. See the log.", "warning")
        else:
            self._log(f"{count} file(s) moved to Trash successfully.")
            self._status(f"Done — {count} file(s) moved to Trash.")
            self._notify("Moved to Trash", f"{count} duplicate file(s) can be restored from the Trash.")

    # =========================================================================
    # Context menus
    # =========================================================================

    def _open_folder(self, path_str: str) -> None:
        """Open a folder in the system file manager. Cross-platform."""
        folder = Path(path_str)
        if not folder.exists():
            _showwarning("Not found",
                                   f"Folder does not exist:\n{folder}", parent=self)
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            _showerror("Error", f"Could not open folder:\n{exc}", parent=self)

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

        menu = self._menu()
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

        menu = self._menu()

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
