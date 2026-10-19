# main.py

import csv
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from typing import Any, Callable, Iterator

from organizer import (
    FilePlan,
    ScanResult,
    commit_staging,
    has_last_run,
    has_staging,
    list_undo_history,
    organise_files,
    revert_staging,
    scan_folder,
    trash_files,
    undo_last_run,
    undo_specific_run,
)
from utils import (
    DARK_THEME, LIGHT_THEME, acquire_instance_lock, append_error_log, csv_delimiter,
    get_downloads_dir, risky_folder_reason, safe_expanduser,
)
from theme import FONTS, apply_ttk_theme, float_key, load_fonts, set_titlebar_theme
from icons import badge, icon
from config import DEFAULT_SETTINGS, load_settings, save_settings
from rules import (
    Rule, CONDITION_TYPES, CONDITION_LABELS, RulesReadError, condition_problem,
    is_safe_target_folder, load_rules, normalize_condition_value, save_rules,
)
from scheduler import OrganizerScheduler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_TITLE    = "Simple Organizer"
APP_VERSION  = "3.5.2"
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
    "[SCHEDULE ERROR]": "error",
}

# Allowed range for every numeric setting: (low, high, step of the − / + buttons).
_LIMITS: dict[str, tuple[float, float, float]] = {
    "max_depth":                 (1,   50,      1),
    "max_dirs":                  (100, 500_000, 1000),
    "scan_timeout":              (5,   300,     5),
    "schedule_interval_minutes": (1,   1440,    15),
}

# Longest time _poll_queue may spend on queued events before letting Tk redraw.
_POLL_BUDGET_S = 0.03

# Longest time one slice of filling the Preview / Duplicates trees may take.
_RENDER_BUDGET_S = 0.02

# Pause between two slices of work. Tk redraws only when no timer is due, so
# rescheduling with after(1) would keep the window from repainting.
_YIELD_MS = 10

# The Log tab keeps at most this many lines; older lines are dropped.
_LOG_MAX_LINES = 5000


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
        try:
            self._value: float = self._clamp(variable.get())
        except (tk.TclError, ValueError):
            self._value = low

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
        self._entry.bind("<MouseWheel>", lambda e: self._wheel(1 if e.delta > 0 else -1))
        self._entry.bind("<Button-4>",   lambda _e: self._wheel(1))
        self._entry.bind("<Button-5>",   lambda _e: self._wheel(-1))
        self._entry.bind("<Return>",     lambda _e: self._nudge(0))
        self._entry.bind("<FocusOut>",   lambda _e: self._nudge(0))

    def sync(self) -> None:
        """Adopt the variable's current value as the committed one. Called after
        the app itself corrected the value, so leaving the field next time does
        not count as a change (and, e.g., does not restart the schedule timer)."""
        try:
            self._value = self._clamp(float(self._var.get()))
        except (tk.TclError, ValueError):
            pass

    def _clamp(self, value: float) -> float:
        value = min(self._high, max(self._low, value))
        return int(round(value)) if isinstance(self._var, tk.IntVar) else value

    def _wheel(self, direction: int) -> str | None:
        # Only a focused field reacts, so scrolling past it never changes a value.
        if self.focus_get() is not self._entry:
            return None
        return self._nudge(direction)

    def _nudge(self, direction: int) -> str:
        """Step up/down (direction ±1) or just validate the typed value (0).

        Steps snap to multiples of the step size (1 -> 15 -> 30 ...). An empty
        or invalid field falls back to the last valid value. The command only
        runs when the value really changed, so leaving the field does not, for
        example, restart the auto-organise timer.
        """
        if str(self._entry.cget("state")) == "disabled":
            return "break"
        try:
            value = float(self._var.get())
            if not math.isfinite(value):
                raise ValueError
        except (tk.TclError, ValueError):
            value = self._value
        if direction > 0:
            value = (math.floor(value / self._step + 1e-9) + 1) * self._step
        elif direction < 0:
            value = (math.ceil(value / self._step - 1e-9) - 1) * self._step
        value = self._clamp(value)
        self._var.set(value)
        if value != self._value:
            self._value = value
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


def _own_window(window: tk.Toplevel, owner: tk.Misc) -> None:
    """Keep window above owner: owned on Windows, transient elsewhere.

    An owned window always stays above its owner and is minimised with it.
    Tk's `wm transient` does not set an owner for borderless (overrideredirect)
    windows on Windows, so the owner is set directly. Call it once the window
    has been laid out (its frame handle exists after update_idletasks).
    """
    if sys.platform != "win32":
        window.transient(owner)
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        window.update_idletasks()
        GWLP_HWNDPARENT = -8   # on a top-level window: its owner
        user32.SetWindowLongPtrW(int(window.wm_frame(), 16), GWLP_HWNDPARENT,
                                 int(owner.wm_frame(), 16))
    except Exception:  # noqa: BLE001 -- cosmetic, must never break a dialog
        pass


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
        # Owned by the main window, so activating the main window (e.g. from the
        # taskbar) can never cover the dialog that holds the input grab.
        _own_window(self, self._app)
        self._grab()
        (focus or self).focus_force()
        self._fade(1)

    def _grab(self, tries: int = 25) -> None:
        """Make the dialog modal. On X11 a window that is not mapped yet refuses
        the grab ("window not viewable"), so retry briefly instead of crashing."""
        try:
            self.grab_set()
        except tk.TclError:
            if tries and self.winfo_exists():
                self.after(20, self._grab, tries - 1)

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
        was_open = self in self._app._overlays
        if was_open:
            self._app._overlays.remove(self)
        super().destroy()
        # Tk keeps only one grab: closing a message shown on top of another
        # dialog would leave that dialog without one, and the main window
        # would accept clicks behind it.
        if was_open and self._app._overlays:
            under = self._app._overlays[-1]
            try:
                if under.winfo_exists():
                    under._grab()
                    under.focus_force()
            except tk.TclError:
                pass


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
        self._tree = ttk.Treeview(box, columns=("when", "files", "folder"), show="headings",
                                  selectmode="browse", height=9)
        for col, text, width, anchor in (("when", "WHEN", 170, "w"), ("files", "FILES", 60, "e"),
                                         ("folder", "FOLDER", 380, "w")):
            self._tree.heading(col, text=text, anchor=anchor)
            self._tree.column(col, width=self._app._px(width), anchor=anchor,
                              stretch=col == "folder")
        sb = _AutoScrollbar(box, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<Double-1>", lambda _e: self._on_undo())
        self._tree.bind("<Return>",   lambda _e: self._on_undo())
        self._tree.tag_configure("empty", foreground=self._app._theme["fg_muted"])

        ttk.Label(
            f,
            text="All folders share one history. Files that a newer run moved again are "
                 "followed and restored too.",
            style="CardHint.TLabel",
        ).pack(anchor="w", pady=(10, 0))

        self.button("Close", self.destroy)
        self._undo_btn = self.button("Undo selected", self._on_undo, primary=True)
        self._open_btn = self.button("Open folder", self._on_open)

    def _load(self) -> None:
        self._entries = list_undo_history()
        self._tree.delete(*self._tree.get_children())
        if not self._entries:
            self._tree.insert("", "end", values=("No history available.", "", ""), tags=("empty",))
            self._undo_btn.configure(state="disabled")
            self._open_btn.configure(state="disabled")
            return
        for i, e in enumerate(self._entries):
            when = e["label"].split("  -  ")[0] + ("  · automatic" if e["scheduled"] else "")
            self._tree.insert("", "end", iid=str(i),
                              values=(when, str(e["move_count"]), e["folder"] or "?"))
        self._tree.selection_set("0")
        self._tree.focus("0")

    def _selected(self) -> dict | None:
        sel = self._tree.selection()
        if not sel or not self._entries or not sel[0].isdigit():
            return None
        return self._entries[int(sel[0])]

    def _on_open(self) -> None:
        entry = self._selected()
        if entry and entry["folder"]:
            self._app._open_folder(entry["folder"].split(" (+")[0])

    def _on_undo(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        app = self._app
        self.destroy()
        if _askyesno(title="Undo this run?", message=_undo_question(entry), parent=app):
            app._undo_specific(entry["file_path"], entry["folder"])


class _RuleDialog(_Overlay):
    _MAX_CONDITIONS = 5

    def __init__(self, parent: "SimpleOrganizerApp", rule: Rule | None = None) -> None:
        super().__init__(parent, "Edit rule" if rule else "New rule")
        self._rule  = rule
        self.result: Rule | None = None
        self._rows: list[dict[str, Any]] = []
        name_entry = self._build(rule)
        self.show(name_entry)

    def _build(self, rule: Rule | None) -> ttk.Entry:
        f = self.body
        f.columnconfigure(0, weight=1)

        def label(r: int, text: str) -> None:
            ttk.Label(f, text=text, style="CardDim.TLabel").grid(
                row=r, column=0, sticky="w", pady=(0 if r == 0 else 10, 3))

        label(0, "Name")
        self._name_var = tk.StringVar(value=rule.name if rule else "")
        name_entry = ttk.Entry(f, textvariable=self._name_var, width=38, style="Card.TEntry")
        name_entry.grid(row=1, column=0, sticky="ew")

        label(2, "Conditions — all must match")
        self._cond_box = ttk.Frame(f, style="Panel.TFrame")
        self._cond_box.grid(row=3, column=0, sticky="ew")
        self._cond_box.columnconfigure(1, weight=1)
        for ctype, value in (rule.conditions() if rule else [(CONDITION_TYPES[0], "")]):
            self._add_row(ctype, value)
        self._add_btn = ttk.Button(f, text="Add condition", style="Card.TButton",
                                   command=self._add_condition)
        self._add_btn.grid(row=4, column=0, sticky="w", pady=(8, 0))
        self._layout_rows()

        label(5, "Target folder")
        self._folder_var = tk.StringVar(value=rule.target_folder if rule else "")
        ttk.Entry(f, textvariable=self._folder_var, width=38, style="Card.TEntry").grid(
            row=6, column=0, sticky="ew")
        ttk.Label(f, text="Subfolder name inside the scanned folder.",
                  style="CardHint.TLabel").grid(row=7, column=0, sticky="w", pady=(3, 0))

        self._enabled_var = tk.BooleanVar(value=rule.enabled if rule else True)
        ttk.Checkbutton(f, text="Enabled", variable=self._enabled_var,
                        style="Card.TCheckbutton").grid(row=8, column=0, sticky="w", pady=(14, 0))

        self.button("Cancel", self.destroy)
        self.button("Save", self._ok, primary=True)
        self.bind("<Return>", lambda _e: self._ok())
        # The first condition, also used by older code and tests.
        self._ctype_var = self._rows[0]["type"]
        self._val_var   = self._rows[0]["value"]
        return name_entry

    def _add_row(self, ctype: str, value: str) -> ttk.Entry:
        app, box = self._app, self._cond_box
        row: dict[str, Any] = {
            "type":  tk.StringVar(value=ctype if ctype in CONDITION_TYPES else CONDITION_TYPES[0]),
            "value": tk.StringVar(value=value),
            "hint":  tk.StringVar(),
        }
        row["combo"] = ttk.Combobox(box, textvariable=row["type"], values=CONDITION_TYPES,
                                    state="readonly", width=17, style="Card.TCombobox")
        row["entry"] = ttk.Entry(box, textvariable=row["value"], width=18, style="Card.TEntry")
        row["remove"] = ttk.Button(
            box, style="Card.Ghost.TButton", command=lambda: self._remove_row(row),
            image=(icon(self, "x", app._px(12), app._theme["fg_dim"]),
                   "active", icon(self, "x", app._px(12), app._theme["fg"])))
        row["label"] = ttk.Label(box, textvariable=row["hint"], style="CardHint.TLabel")
        row["combo"].bind("<<ComboboxSelected>>", lambda _e: self._update_hint(row))
        self._rows.append(row)
        self._update_hint(row)
        return row["entry"]

    def _layout_rows(self) -> None:
        several = len(self._rows) > 1
        for i, row in enumerate(self._rows):
            top = 0 if i == 0 else 8
            row["combo"].grid(row=2 * i, column=0, sticky="w", pady=(top, 0))
            row["entry"].grid(row=2 * i, column=1, sticky="ew", padx=(8, 0), pady=(top, 0))
            if several:
                row["remove"].grid(row=2 * i, column=2, padx=(4, 0), pady=(top, 0))
            else:
                row["remove"].grid_remove()
            row["label"].grid(row=2 * i + 1, column=0, columnspan=3, sticky="w", pady=(3, 0))
        if hasattr(self, "_add_btn"):
            self._add_btn.configure(
                state="normal" if len(self._rows) < self._MAX_CONDITIONS else "disabled")
        if self.winfo_ismapped():
            self.follow()

    def _add_condition(self) -> None:
        if len(self._rows) >= self._MAX_CONDITIONS:
            return
        entry = self._add_row(CONDITION_TYPES[0], "")
        self._layout_rows()
        entry.focus_set()

    def _remove_row(self, row: dict[str, Any]) -> None:
        if len(self._rows) <= 1:
            return
        for key in ("combo", "entry", "remove", "label"):
            row[key].destroy()
        self._rows.remove(row)
        self._layout_rows()

    def _update_hint(self, row: dict[str, Any]) -> None:
        row["hint"].set(CONDITION_LABELS.get(row["type"].get(), ""))

    def _ok(self) -> None:
        name   = self._name_var.get().strip()
        folder = self._folder_var.get().strip()

        if not name or not folder:
            _showwarning("Incomplete", "Name and Target folder are required.", parent=self)
            return

        if not is_safe_target_folder(folder):
            _showwarning(
                "Invalid target folder",
                f'"{folder}" is not allowed.\n'
                "Enter a subfolder name inside the scanned folder: no absolute "
                "paths, drive letters or '..', none of the characters < > : \" | ? *, "
                "no names like CON or NUL, and no trailing dot or space.",
                parent=self,
            )
            return

        conditions: list[tuple[str, str]] = []
        for row in self._rows:
            ctype, value = row["type"].get(), row["value"].get()
            problem = condition_problem(ctype, value)
            if problem:
                _showwarning("Invalid condition", problem, parent=self)
                row["entry"].focus_set()
                return
            conditions.append((ctype, normalize_condition_value(ctype, value)))

        (first_type, first_value), *more = conditions
        self.result = Rule(
            name=name,
            enabled=self._enabled_var.get(),
            condition_type=first_type,
            condition_value=first_value,
            target_folder=folder,
            more_conditions=[{"type": t, "value": v} for t, v in more],
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

    def __init__(self, parent: tk.Misc, title: str, message: str, kind: str,
                 yes: str = "Continue", no: str = "Cancel") -> None:
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
            self.button(no, self.destroy)
            default = self.button(yes, self._accept, primary=True)
        else:
            default = self.button("OK", self._accept, primary=True)

        self.bind("<Return>", lambda _e: self._accept())
        self.show(default)
        self.wait_window(self)

    def _accept(self) -> None:
        self.result = True
        self.destroy()


def _askyesno(title: str, message: str, parent: tk.Misc,
              yes: str = "Continue", no: str = "Cancel") -> bool:
    return _MessageDialog(parent, title, message, "question", yes, no).result


def _undo_question(entry: dict) -> str:
    """Confirmation text naming exactly the run that will be undone."""
    when = entry["label"].split("  -  ")[0]
    kind = "automatic run" if entry.get("scheduled") else "run"
    return (
        f"Restore the {entry['move_count']} file(s) moved in the {kind} of {when} "
        "to their original locations?\n\n"
        f"Folder: {entry.get('folder') or 'unknown'}\n\n"
        "- Nothing will be deleted.\n"
        "- Name conflicts get a _1, _2 suffix."
    )


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
        _own_window(self, app)   # stays above the app and is hidden with it when minimised
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

        self._settings: dict = load_settings()
        self._load_window_icon()

        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.minsize(MIN_W, MIN_H)
        self.resizable(True, True)
        self._restore_geometry()

        # ── State ─────────────────────────────────────────────────────────────
        # A saved folder is kept even if it is not reachable right now (drive
        # unplugged): falling back to Downloads would let Auto-organize sort a
        # folder the user never chose, and forget the real one on close.
        _saved_folder = self._settings.get("last_folder", "")
        if _saved_folder:
            try:
                self._folder = safe_expanduser(_saved_folder)
            except (OSError, RuntimeError, ValueError):
                self._folder = Path(_saved_folder)
        else:
            self._folder = get_downloads_dir().resolve()

        self._scan_result:    ScanResult | None = None
        self._dark_mode:      bool              = bool(self._settings["dark_mode"])
        self._auto_mode:      bool              = False
        self._busy_flag:      bool              = False
        self._dup_groups:     dict[str, list[str]] = {}  # group_node -> [file_iids]   # M5 fix — initialised here
        # Paths behind the tree rows, kept in Python instead of in Treeview
        # values/tags, which Tcl may reinterpret (numbers, braces, spaces).
        self._preview_items:  dict[str, FilePlan] = {}   # preview iid -> plan
        self._dup_paths:      dict[str, Path]     = {}   # duplicate file iid -> path
        self._schedule_pending: bool = False   # a scheduled run is waiting for the app to be idle
        self._close_requested:  bool = False   # window closed while a task was running
        self._native_dialog:    bool = False   # the system folder picker is open
        self._dnd_enabled:      bool = False
        self._render_gen:       int  = 0       # bumped to cancel an unfinished tree fill
        self._task_moves_files: bool = False   # the running task moves files (not a scan)
        self._schedule_notified: set[str] = set()   # folders whose "paused" toast was shown
        self._steppers: dict[str, _Stepper] = {}     # settings key -> its number field
        self._settings_save_failed: bool = False
        self._instance_lock: object | None = None   # kept alive while the app runs
        self._preview_gen:   int = 0                # bumped to cancel an unfinished Preview fill
        self._preview_sort:  tuple[str, bool] = ("", False)   # column, descending
        self._filter_job:    str | None = None
        self._undo_folder:   str = ""               # folder of the run being undone
        self._plan_outdated: bool = False           # rules changed while a scan was running
        # Files set to "Don't move" (normcase'd paths). Kept for later scans of
        # the same folder -- also automatic ones, and after a restart -- until
        # another folder is picked. Saved paths outside the folder are dropped.
        _folder_prefix = os.path.join(os.path.normcase(str(self._folder)), "")
        self._excluded_keys: set[str] = {
            k for k in self._settings.get("excluded_files", [])
            if k.startswith(_folder_prefix)}

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
        if not self._folder.is_dir():
            self._log(f"[WARN]  The last folder {self._folder} is not available right now "
                      "(drive unplugged or disconnected?).")

    # =========================================================================
    # Window geometry
    # =========================================================================

    def _work_area(self, x: int, y: int) -> tuple[int, int, int, int]:
        """Usable area (left, top, right, bottom) of the monitor nearest to x, y.

        On Windows this is the monitor's work area (without the taskbar), so a
        window saved on a monitor that is gone or smaller is moved and shrunk
        to fit. Elsewhere Tk only knows the whole screen.
        """
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                user32.MonitorFromPoint.restype = wintypes.HMONITOR
                user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
                monitor = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(info)
                if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    r = info.rcWork
                    return r.left, r.top, r.right, r.bottom
            except Exception:  # noqa: BLE001
                pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _keeps_position(self) -> bool:
        """Only Windows reports and restores window positions reliably. X11
        window managers disagree on whether +x+y means the frame or the client
        area, so a restored window would creep down by the title bar height on
        every start; there (and on Wayland) the window manager places it."""
        return self.tk.call("tk", "windowingsystem") == "win32"

    def _restore_geometry(self) -> None:
        """Restore size, position and maximised state, always fitting the screen."""
        s = self._settings
        x, y = s.get("window_x"), s.get("window_y")
        if not self._keeps_position():
            x = y = None
        left, top, right, bottom = self._work_area(
            x if x is not None else 0, y if y is not None else 0)
        area_w, area_h = max(1, right - left), max(1, bottom - top)
        # On a screen smaller than the minimum size, the minimum gives way.
        self.minsize(min(MIN_W, area_w), min(MIN_H, area_h))
        w = min(max(s["window_width"],  MIN_W), area_w)
        h = min(max(s["window_height"], MIN_H), area_h)
        geometry = f"{w}x{h}"
        if x is not None and y is not None:
            x = min(max(x, left), right - w)
            y = min(max(y, top), bottom - h)
            geometry += f"+{x}+{y}"
        self.geometry(geometry)
        if s.get("window_maximized"):
            self._set_zoomed()

    def _set_zoomed(self) -> None:
        try:
            self.state("zoomed")                 # Windows
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)  # X11
            except tk.TclError:
                pass

    def _is_zoomed(self) -> bool:
        try:
            if self.state() == "zoomed":
                return True
        except tk.TclError:
            pass
        try:
            return bool(int(self.attributes("-zoomed")))
        except (tk.TclError, ValueError):
            return False

    def _geometry_settings(self) -> dict[str, Any]:
        """Window values to save. While maximised only the flag changes, so the
        normal size is not overwritten with the size of the whole screen."""
        try:
            if self.state() in ("iconic", "withdrawn"):
                return {}
        except tk.TclError:
            return {}
        if self._is_zoomed():
            return {"window_maximized": True}
        match = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", self.wm_geometry())
        if not match:
            return {"window_maximized": False}
        w, h, x, y = (int(v) for v in match.groups())
        if w <= 1 or h <= 1:   # not mapped yet
            return {}
        values: dict[str, Any] = {"window_width": w, "window_height": h,
                                  "window_maximized": False}
        if self._keeps_position():
            values.update(window_x=x, window_y=y)
        return values

    def _native_handle(self) -> int | None:
        """Window handle of the main window's frame (Windows), else None."""
        if sys.platform != "win32":
            return None
        try:
            return int(self.wm_frame(), 16)
        except (tk.TclError, ValueError):
            return None

    def _load_window_icon(self) -> None:
        """Use icon.png when it ships with the app, otherwise draw one."""
        try:
            if getattr(sys, "frozen", False):
                _base = Path(sys._MEIPASS)          # type: ignore[attr-defined]
            else:
                _base = Path(__file__).resolve().parent
            self._icon = tk.PhotoImage(file=str(_base / "icon.png"))
        except Exception:
            try:
                t = DARK_THEME if self._settings.get("dark_mode") else LIGHT_THEME
                self._icon = badge(self, "folders", 64, 36, t["accent"], t["accent_fg"])
            except Exception:
                self._icon = None
        if self._icon is not None:
            try:
                self.iconphoto(True, self._icon)
            except tk.TclError:
                pass

    def report_callback_exception(self, exc: type[BaseException], val: BaseException,
                                  tb: Any) -> None:
        """Tk calls this for an exception in any callback (click, timer, ...).

        The default prints to sys.stderr, which does not exist in the windowed
        exe, so the error would vanish without a trace. Write it to error.log,
        the Log tab and a notification instead.
        """
        details = "".join(traceback.format_exception(exc, val, tb))
        path = append_error_log(f"Simple Organizer v{APP_VERSION} -- unexpected error\n{details}")
        try:
            self._log(f"[ERROR]  Unexpected error: {val!r}")
            where = f"Details were written to {path}." if path else "See the log."
            self._notify("Something went wrong", where, "error")
        except Exception:  # noqa: BLE001 -- reporting must never raise
            pass

    def _on_close(self) -> None:
        """Save settings, stop background scheduler, then destroy the window.

        While a task is moving files the window stays open and closes as soon
        as the task has finished: killing the worker thread mid-run would leave
        moved files without an undo record.
        """
        if self._overlays:
            self._overlays[-1].lift()
            self._overlays[-1].focus_force()
            return
        if self._busy_flag:
            if not self._close_requested:
                self._close_requested = True
                self._status("Closing as soon as the current task has finished...")
                self._log("[WARN]  Close requested -- waiting for the current task to "
                          "finish so no file is left without an undo record.")
            return
        try:
            self._save_settings()
        except Exception:  # noqa: BLE001 — closing must never be blocked
            pass
        finally:
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
        # The drop hint is only added once drag-and-drop is known to work.
        self._folder_tip = _Tooltip(self._folder_entry, "Folder to organise.")

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
            style="Card.TCheckbutton", command=self._on_scan_option_changed)
        self._recursive_cb.pack(anchor="w")

        self._hidden_cb = ttk.Checkbutton(
            scan, text="Include hidden files", variable=self._include_hidden,
            style="Card.TCheckbutton", command=self._on_scan_option_changed)
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
            limits, 0, "Max depth", self._max_depth, *_LIMITS["max_depth"])
        self._max_dirs_spin = self._limit_row(
            limits, 1, "Max folders", self._max_dirs, *_LIMITS["max_dirs"])
        self._timeout_spin = self._limit_row(
            limits, 2, "Timeout (s)", self._scan_timeout, *_LIMITS["scan_timeout"])

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
            every, self._schedule_interval, *_LIMITS["schedule_interval_minutes"], width=5,
            command=self._on_schedule_toggle)
        self._sched_spin.pack(side="left", padx=8)
        ttk.Label(every, text="minutes", style="CardDim.TLabel").pack(side="left")

        ttk.Label(sched, textvariable=self._schedule_status_var, style="CardHint.TLabel",
                  wraplength=self._px(SIDEBAR_W - 48), justify="left").pack(
            anchor="w", pady=(8, 0))

        self._steppers = {
            "max_depth":                 self._max_depth_spin,
            "max_dirs":                  self._max_dirs_spin,
            "scan_timeout":              self._timeout_spin,
            "schedule_interval_minutes": self._sched_spin,
        }

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
        stepper = _Stepper(parent, var, low, high, step, command=self._on_limit_changed)
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
        _Tooltip(self._history_btn,  "Browse and undo any of the last 20 manual and 20 automatic runs.")

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
        tab.rowconfigure(2, weight=1)
        self._preview_tab_idx = self._add_tab(tab, "Preview", "eye")

        bar = ttk.Frame(tab, style="Panel.TFrame", padding=(12, 8))
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._with_icon(ttk.Label(bar, style="Card.TLabel"), "magnifying-glass").pack(
            side="left", padx=(0, 6))
        self._filter_var = tk.StringVar()
        self._filter_entry = ttk.Entry(bar, textvariable=self._filter_var, width=34,
                                       style="Card.TEntry")
        self._filter_entry.pack(side="left")
        self._filter_entry.bind("<Escape>", self._on_filter_escape)
        self._filter_var.trace_add("write", self._on_filter_changed)
        _Tooltip(self._filter_entry, "Show only files whose name, category or destination "
                                     "contains this text. (Ctrl+F, Esc to clear)\n"
                                     "Organize still moves every file that is not set to "
                                     "\u201cDon't move\u201d.")
        self._filter_info_var = tk.StringVar()
        ttk.Label(bar, textvariable=self._filter_info_var, style="CardHint.TLabel").pack(
            side="left", padx=(10, 0))
        self._export_btn = self._with_icon(ttk.Button(
            bar, text="Export CSV…", style="Card.TButton", command=self._export_csv),
            "arrow-down")
        self._export_btn.pack(side="right")
        _Tooltip(self._export_btn, "Save the scan result as a CSV file (opens in Excel or LibreOffice).")
        ttk.Frame(tab, style="Rule.TFrame", height=1).grid(row=1, column=0, columnspan=2, sticky="ew")

        self._preview_tree = self._make_table(tab, ("file", "category", "destination"), row=2,
                                              selectmode="extended")
        for col, text in self._PREVIEW_HEADINGS.items():
            self._preview_tree.heading(col, text=text, anchor="w",
                                       command=lambda c=col: self._sort_preview(c))
        self._preview_tree.column("file",        width=260, anchor="w", stretch=True)
        self._preview_tree.column("category",    width=130, anchor="w", stretch=False)
        self._preview_tree.column("destination", width=320, anchor="w", stretch=True)
        self._preview_tree.bind("<Button-3>", self._on_preview_context)
        self._preview_tree.bind("<space>",    self._toggle_excluded)
        self._preview_tree.bind("<Delete>",   self._toggle_excluded)

        self._preview_empty = self._with_icon(ttk.Label(
            tab, text=self._PREVIEW_EMPTY,
            style="Empty.TLabel", compound="top"), "folder-dashed", "empty")
        self._sync_empty(self._preview_tree, self._preview_empty)
        ttk.Label(
            tab,
            text="Right-click, Space or Delete: don't move the selected files. "
                 "Click a column heading to sort.",
            style="CardHint.TLabel", padding=(12, 8),
        ).grid(row=4, column=0, columnspan=2, sticky="w")

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

        cols = ("enabled", "name", "conditions", "target")
        self._rules_tree = self._make_table(tab, cols, row=2)
        self._rules_tree.heading("enabled",    text="")
        self._rules_tree.heading("name",       text="NAME",                          anchor="w")
        self._rules_tree.heading("conditions", text="CONDITIONS (ALL MUST MATCH)",   anchor="w")
        self._rules_tree.heading("target",     text="TARGET FOLDER",                 anchor="w")
        self._rules_tree.column("enabled",    width=40,  anchor="center", stretch=False)
        self._rules_tree.column("name",       width=160, anchor="w",      stretch=True)
        self._rules_tree.column("conditions", width=280, anchor="w",      stretch=True)
        self._rules_tree.column("target",     width=160, anchor="w",      stretch=True)
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
            text="Rules run before extension-based categorisation. First match wins; a rule "
                 "matches when all its conditions match. Click the dot to turn a rule on or off.",
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
            text="Ctrl+R scan   Ctrl+O organize   Ctrl+Z undo   Ctrl+1-4 tabs   Ctrl+Q quit",
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
        for i, (label, count_label, line, glyph) in enumerate(self._tabs):
            active = i == current
            label.configure(style="TabActive.TLabel" if active else "Tab.TLabel",
                            image=icon(self, glyph, self._px(14),
                                       t["accent"] if active else t["fg_muted"],
                                       gap=self._px(6)))
            count_label.configure(style="BadgeActive.TLabel" if active else "Badge.TLabel")
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
        self._preview_tree.tag_configure("excluded", foreground=t["fg_muted"])

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

    def _typing_in_field(self) -> bool:
        try:
            return isinstance(self.focus_get(), (tk.Entry, tk.Text))   # ttk.Entry is a tk.Entry
        except (KeyError, tk.TclError):   # focus in a Tk-internal widget (e.g. a dropdown)
            return False

    def _bind_shortcuts(self) -> None:
        def shortcut(action: Callable[[], Any], not_in_fields: bool = False
                     ) -> Callable[[Any], str | None]:
            # Shortcuts obey the same rules as the buttons: nothing starts while a
            # task is running or a dialog is open.
            def handler(_event: Any) -> str | None:
                if not_in_fields and self._typing_in_field():
                    return None   # Ctrl+Z while typing means "undo typing", not "undo run"
                if not self._busy_flag and not self._modal_open():
                    action()
                return "break"
            return handler

        def close(_event: Any) -> str:
            self._on_close()
            return "break"

        def select_tab(index: int) -> Callable[[Any], str]:
            def handler(_event: Any) -> str:
                if not self._modal_open():
                    self._notebook.select(index)
                return "break"
            return handler

        def find(_event: Any) -> str:
            if not self._modal_open():
                self._notebook.select(self._preview_tab_idx)
                self._filter_entry.focus_set()
                self._filter_entry.select_range(0, "end")
            return "break"

        # Both cases: with Caps Lock on, Tk reports Control-R instead of Control-r.
        for key, handler in (("r", shortcut(self._start_scan)),
                             ("o", shortcut(self._confirm_and_organize)),
                             ("z", shortcut(self._confirm_and_undo, not_in_fields=True)),
                             ("f", find),
                             ("q", close)):
            self.bind_all(f"<Control-{key}>", handler)
            self.bind_all(f"<Control-{key.upper()}>", handler)
        self.bind_all("<F5>", shortcut(self._start_scan))
        for number in range(1, len(self._tabs) + 1):
            self.bind_all(f"<Control-Key-{number}>", select_tab(number - 1))

    def _modal_open(self) -> bool:
        return bool(self._overlays) or self._native_dialog

    def _try_register_dnd(self) -> None:
        """Enable dropping a folder on the path field when tkdnd is available.

        tkdnd is not part of Python. It is found either through the tkinterdnd2
        package (pip install tkinterdnd2), which bundles it, or as a Tcl package
        installed on the system. Without it the feature stays off and the
        tooltip does not mention it.
        """
        try:
            try:
                from tkinterdnd2 import TkinterDnD  # type: ignore[import-not-found]
                TkinterDnD._require(self)
            except Exception:  # noqa: BLE001
                self.tk.call("package", "require", "tkdnd")
            widget = self._folder_entry._w
            self.tk.call("tkdnd::drop_target", "register", widget, ("DND_Files",))
            command = self.register(self._on_dnd_drop)
            self.tk.call("bind", widget, "<<Drop>>", f"{command} %D")
        except Exception:  # noqa: BLE001
            return
        self._dnd_enabled = True
        self._folder_tip._text = "Folder to organise. You can also drop a folder here."

    def _on_dnd_drop(self, data: str) -> str:
        """Handle a drop from tkdnd. data is a Tcl list of one or more paths;
        the first folder (or the folder of the first file) is used."""
        if self._busy_flag or self._modal_open():
            return "refuse_drop"
        try:
            tokens = self.tk.splitlist(data)
        except tk.TclError:
            tokens = (data,)
        for token in tokens:
            if not token:
                continue
            path = Path(token)
            if path.is_dir():
                self._set_folder(path)
                return "copy"
            if path.is_file():
                self._set_folder(path.parent)
                return "copy"
        return "refuse_drop"

    def _set_folder(self, path: Path) -> None:
        if self._busy_flag:
            self._notify("Folder not changed",
                         "Wait until the current task has finished.", "warning")
            return
        self._folder = path.resolve()
        self._folder_var.set(str(self._folder))
        self._excluded_keys.clear()
        self._scan_result = None
        self._render_scan_result()   # clears Preview and Duplicates of the old folder
        self._log(f"Folder set: {self._folder}")
        self._update_schedule_status()
        self._save_settings()

    # =========================================================================
    # Folder browsing
    # =========================================================================

    def _browse_folder(self) -> None:
        if self._busy_flag or self._modal_open():
            return
        initial = str(self._folder) if self._folder.exists() else str(Path.home())
        # Scheduled runs wait while the system dialog is open (see _run_scheduled_organize).
        self._native_dialog = True
        try:
            chosen = filedialog.askdirectory(title="Select folder to organise",
                                             initialdir=initial, parent=self)
        finally:
            self._native_dialog = False
        if chosen:
            self._set_folder(Path(chosen))

    # =========================================================================
    # Toggles
    # =========================================================================

    def _on_staging_toggle(self) -> None:
        self._refresh_persistent_buttons()
        self._save_settings()

    def _on_subcats_toggle(self) -> None:
        self._on_scan_option_changed()

    def _on_scan_option_changed(self) -> None:
        self._save_settings()
        self._invalidate_plan("The scan options changed")

    def _on_limit_changed(self) -> None:
        # The limits only matter for recursive scans.
        if self._recursive.get():
            self._invalidate_plan("The scan limits changed")

    def _invalidate_plan(self, why: str) -> None:
        """Drop a plan that no longer matches the options or rules (#73):
        Organize must never move files according to an outdated preview."""
        if self._busy_flag:
            # The Rules tab stays usable during a scan: its result is based on
            # the old rules and is discarded when it arrives.
            if not self._task_moves_files:
                self._plan_outdated = True
            return
        if self._scan_result is None:
            return
        self._scan_result = None
        self._render_scan_result()
        self._status(f"{why} -- press Scan to update the preview.")
        self._log(f"[WARN]  {why} -- the preview was cleared. Scan again before organizing.")

    def _refresh_persistent_buttons(self) -> None:
        """Set every action button from the current state. While a task runs
        all of them are disabled, so no second task can touch the same files."""
        if self._busy_flag:
            for w in (self._organize_btn, self._undo_btn, self._history_btn,
                      self._commit_btn, self._revert_btn, self._trash_btn):
                w.configure(state="disabled")
            return
        history_state = "normal" if has_last_run() else "disabled"
        staging_state = "normal" if has_staging()  else "disabled"
        self._undo_btn.configure(state=history_state)
        self._history_btn.configure(state=history_state)
        self._commit_btn.configure(state=staging_state)
        self._revert_btn.configure(state=staging_state)
        self._organize_btn.configure(
            state="normal" if self._actionable_plans() else "disabled")
        self._on_dup_select()

    def _actionable_plans(self) -> list[FilePlan]:
        if not self._scan_result:
            return []
        return [p for p in self._scan_result.plans if not p.skipped and not p.excluded]

    # =========================================================================
    # Schedule
    # =========================================================================

    def _apply_schedule_settings(self) -> None:
        self._scheduler.configure(
            interval_minutes=self._num(self._schedule_interval, "schedule_interval_minutes",
                                       commit=True),
            enabled=self._schedule_enabled.get(),
        )
        self._update_schedule_status()

    def _on_schedule_toggle(self) -> None:
        self._apply_schedule_settings()
        self._save_settings()

    def _update_schedule_status(self) -> None:
        if not self._schedule_enabled.get():
            self._schedule_status_var.set("Off")
        elif not self._folder.is_dir():
            self._schedule_status_var.set(
                "Paused: the folder was not found (drive unplugged or disconnected?).")
        elif risky_folder_reason(self._folder) and not self._is_approved(self._folder):
            self._schedule_status_var.set(
                "Paused: this folder needs one manual scan and confirmation first.")
        else:
            mins = self._num(self._schedule_interval, "schedule_interval_minutes")
            self._schedule_status_var.set(f"Active, runs every {mins} min")

    def _schedule_paused(self, kind: str, log_line: str, message: str) -> None:
        """Report a skipped scheduled run: log line, status card, and one
        notification per reason and folder until the reason goes away."""
        self._log(f"[SCHEDULE]  Skipped -- {log_line}")
        self._update_schedule_status()
        key = f"{kind}:{os.path.normcase(str(self._folder))}"
        if key not in self._schedule_notified:
            self._schedule_notified.add(key)
            self._notify("Auto-organize paused", message, "warning")

    # Unusual folders (see risky_folder_reason) the user agreed to organise.
    # Stored in settings.json, so automatic runs keep working after a restart.

    def _is_approved(self, folder: Path) -> bool:
        key = os.path.normcase(str(folder))
        return any(os.path.normcase(f) == key for f in self._settings.get("approved_folders", []))

    def _approve(self, folder: Path) -> None:
        if not self._is_approved(folder):
            self._settings["approved_folders"] = [
                *self._settings.get("approved_folders", []), str(folder)]
        self._update_schedule_status()

    def _on_schedule_fire(self) -> None:
        self._event_queue.put({"type": "schedule_fire"})

    def _run_scheduled_organize(self, retry: bool = False) -> None:
        """Start a scheduled scan + organise.

        While a task runs or any dialog is open the run waits (re-checked every
        2 s) instead of starting underneath it: a scan in the background would
        replace the results a confirmation dialog is about to act on.
        """
        if retry:
            self._schedule_pending = False
        elif self._schedule_pending:
            return   # an earlier run is already waiting
        if self._close_requested or not self._schedule_enabled.get():
            return
        if self._busy_flag or self._modal_open():
            if not retry:
                self._log("[SCHEDULE]  Postponed -- waiting for the current task "
                          "or dialog to finish.")
            self._schedule_pending = True
            self.after(2000, self._run_scheduled_organize, True)
            return

        if not self._folder.is_dir():
            self._schedule_paused(
                "missing", f"{self._folder} was not found.",
                "The folder was not found -- is the drive unplugged or disconnected?")
            return
        reason = risky_folder_reason(self._folder)
        if reason and not self._is_approved(self._folder):
            self._schedule_paused(
                "unusual", f"{self._folder} {reason}. "
                "Scan it once by hand and confirm to allow automatic runs.",
                "This folder needs one manual scan and confirmation first.")
            return

        # Running again: a later pause for the same reason is reported anew.
        folder_key = os.path.normcase(str(self._folder))
        self._schedule_notified -= {f"missing:{folder_key}", f"unusual:{folder_key}"}
        self._update_schedule_status()
        self._log(f"[SCHEDULE]  Auto-organize triggered for: {self._folder}")
        self._auto_mode = True
        try:
            self._start_scan(confirmed=True)
        except Exception as exc:  # noqa: BLE001
            # Never leave auto-mode on: the next manual scan would skip confirmation.
            self._auto_mode = False
            self._set_busy(False)
            self._log(f"[ERROR]  Scheduled scan failed: {exc}")
        if not self._busy_flag:
            # No scan started (e.g. the folder vanished a moment ago): the
            # next manual scan must not organise without asking.
            self._auto_mode = False

    # =========================================================================
    # Rules UI
    # =========================================================================

    def _load_rules_checked(self) -> list[Rule] | None:
        """load_rules() for the Rules tab. Returns None (after telling the user)
        when rules.json exists but cannot be read right now -- editing would
        then save an empty list over the user's rules."""
        try:
            return load_rules()
        except RulesReadError as exc:
            self._log(f"[WARN]  {exc}")
            self._notify("Rules not available",
                         "rules.json could not be read. Try again in a moment.", "warning")
            return None
        except Exception as exc:  # noqa: BLE001 -- a bad rules file must never stop the app
            self._log(f"[WARN]  rules.json could not be loaded: {exc}")
            self._notify("Rules not available",
                         "rules.json could not be loaded. See the log.", "warning")
            return None

    def _refresh_rules_tree(self) -> None:
        rules = self._load_rules_checked()
        if rules is None:
            return
        self._rules_tree.delete(*self._rules_tree.get_children())
        for rule in rules:
            self._rules_tree.insert("", "end", values=(
                "●" if rule.enabled else "○",
                rule.name, rule.describe(), rule.target_folder,
            ), tags=() if rule.enabled else ("off",))
        self._sync_empty(self._rules_tree, self._rules_empty)

    def _persist_rules(self, rules: list[Rule]) -> None:
        if not save_rules(rules):
            self._log("[WARN]  Rules could not be saved — check disk space and permissions.")
            self._notify("Rules not saved",
                         "Your rule changes could not be written to disk.", "warning")
            return
        self._invalidate_plan("The rules changed")

    def _selected_rule_index(self) -> int | None:
        sel = self._rules_tree.selection()
        if not sel:
            return None
        return list(self._rules_tree.get_children()).index(sel[0])

    def _rule_add(self) -> None:
        dlg = _RuleDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            rules = self._load_rules_checked()
            if rules is None:
                return
            rules.append(dlg.result)
            self._persist_rules(rules)
            self._refresh_rules_tree()

    def _rule_edit(self) -> None:
        idx = self._selected_rule_index()
        if idx is None:
            _showinfo("No selection", "Select a rule to edit.", parent=self)
            return
        rules = self._load_rules_checked()
        if rules is None or idx >= len(rules):
            return
        dlg   = _RuleDialog(self, rules[idx])
        self.wait_window(dlg)
        if dlg.result:
            # Re-read: the file may have changed while the dialog was open.
            rules = self._load_rules_checked()
            if rules is None or idx >= len(rules):
                return
            rules[idx] = dlg.result
            self._persist_rules(rules)
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
        rules = self._load_rules_checked()
        if rules is None or idx >= len(rules):
            return
        rules[idx].enabled = not rules[idx].enabled
        self._persist_rules(rules)
        self._refresh_rules_tree()

    def _rule_delete(self) -> None:
        idx = self._selected_rule_index()
        if idx is None:
            return
        rules = self._load_rules_checked()
        if rules is None or idx >= len(rules):
            return
        if not _askyesno("Delete Rule",
                                   f"Delete rule '{rules[idx].name}'?", parent=self):
            return
        rules = self._load_rules_checked()
        if rules is None or idx >= len(rules):
            return
        del rules[idx]
        self._persist_rules(rules)
        self._refresh_rules_tree()

    def _rule_move(self, direction: int) -> None:
        idx = self._selected_rule_index()
        if idx is None:
            return
        rules   = self._load_rules_checked()
        if rules is None:
            return
        new_idx = idx + direction
        if idx >= len(rules) or new_idx < 0 or new_idx >= len(rules):
            return
        rules[idx], rules[new_idx] = rules[new_idx], rules[idx]
        self._persist_rules(rules)
        self._refresh_rules_tree()
        children = self._rules_tree.get_children()
        if children:
            self._rules_tree.selection_set(children[new_idx])

    # =========================================================================
    # Undo history
    # =========================================================================

    def _open_history_dialog(self) -> None:
        if self._busy_flag or self._modal_open():
            return
        _HistoryDialog(self)

    def _undo_specific(self, run_file: Path, folder: str = "") -> None:
        if self._busy_flag:
            return
        self._undo_folder = folder
        self._start_task(
            f"Undoing {run_file.stem}...",
            lambda progress, log: {
                "type": "undo_done",
                "errors": undo_specific_run(run_file, progress_callback=progress,
                                            log_callback=log),
            })

    # =========================================================================
    # Background tasks
    # =========================================================================

    def _start_task(
        self,
        status: str,
        work: Callable[[Callable[[int, int], None], Callable[[str], None]], dict[str, Any]],
        log_tab: bool = True,
        moves_files: bool = True,
    ) -> None:
        """Run work(progress, log) on a worker thread and queue its result event.

        progress only queues an event when the whole percentage changes, so a
        run over 100 000 files sends ~100 progress events instead of 100 000.
        moves_files tells the error handler whether a crash may have left the
        shown scan result out of date.
        """
        self._task_moves_files = moves_files
        self._set_busy(True)
        self._set_progress(0.0)
        self._status(status)
        if log_tab:
            self._notebook.select(self._log_tab_idx)

        def progress(current: int, total: int) -> None:
            pct = current * 100 // total if total else 0
            if pct != last[0]:
                last[0] = pct
                self._event_queue.put({"type": "progress", "value": pct})
        last = [-1]

        def log(msg: str) -> None:
            self._event_queue.put({"type": "log", "value": msg})

        def run() -> None:
            try:
                event = work(progress, log)
            except Exception as exc:  # noqa: BLE001
                event = {"type": "error", "value": str(exc),
                         "details": traceback.format_exc()}
            self._event_queue.put(event)

        threading.Thread(target=run, daemon=True).start()

    # =========================================================================
    # Settings persistence
    # =========================================================================

    def _num(self, var: tk.IntVar | tk.DoubleVar, key: str, commit: bool = False) -> Any:
        """Read a numeric setting, clamped to its allowed range.

        An empty or invalid field falls back to the last saved value (or the
        default). With commit=True the field is updated to the value actually
        used; without it the field is left alone, so a settings save that
        happens while the user is still typing does not rewrite the field.
        """
        default = DEFAULT_SETTINGS[key]
        try:
            value = var.get()
            if not math.isfinite(value):
                raise ValueError
        except (tk.TclError, ValueError):
            value = self._settings.get(key, default)
        low, high, _step = _LIMITS[key]
        value = min(high, max(low, value))
        value = int(round(value)) if isinstance(default, int) else float(value)
        if commit:
            var.set(value)
            if key in self._steppers:
                self._steppers[key].sync()
        return value

    def _save_settings(self) -> None:
        self._settings.update(self._geometry_settings())
        self._settings.update({
            "last_folder":               str(self._folder),
            "staging_mode":              self._use_staging.get(),
            "dark_mode":                 self._dark_mode,
            "schedule_enabled":          self._schedule_enabled.get(),
            "schedule_interval_minutes": self._num(self._schedule_interval, "schedule_interval_minutes"),
            "use_subcategories":         self._use_subcats.get(),
            "recursive":                 self._recursive.get(),
            "include_hidden":            self._include_hidden.get(),
            "max_depth":                 self._num(self._max_depth, "max_depth"),
            "max_dirs":                  self._num(self._max_dirs, "max_dirs"),
            "scan_timeout":              self._num(self._scan_timeout, "scan_timeout"),
            "excluded_files":            sorted(self._excluded_keys),
        })
        if save_settings(self._settings):
            self._settings_save_failed = False
        elif not self._settings_save_failed:   # once, not on every resize and click
            self._settings_save_failed = True
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

    def _start_scan(self, confirmed: bool = False) -> None:
        if self._busy_flag:
            return
        folder = self._folder
        if not folder.is_dir():
            self._auto_mode = False
            self._status("Folder not found.")
            self._log(f"[WARN]  {folder} was not found -- nothing scanned.")
            if not confirmed:
                _showwarning("Folder not found",
                             f"{folder} was not found.\n\nIs the drive connected? "
                             "Connect it, or pick another folder with Browse.", parent=self)
            return
        reason = risky_folder_reason(folder)
        if reason and not self._is_approved(folder) and not confirmed:
            if not _askyesno(
                title="Unusual folder",
                message=(
                    f"{folder} {reason}.\n\n"
                    "Organising it can move files that programs or the system rely on. "
                    "Everything can be undone, but programs may misbehave until then.\n\n"
                    "Scan this folder anyway? Your answer is remembered for this folder, "
                    "also for automatic runs."
                ),
                parent=self,
            ) or self._busy_flag:
                return
            self._approve(folder)

        self._save_settings()   # persist current scan options before running
        self._plan_outdated = False
        self._scan_result = None
        self._render_scan_result()   # also cancels a tree fill that is still running

        recursive      = self._recursive.get()
        include_hidden = self._include_hidden.get()
        max_depth      = self._num(self._max_depth, "max_depth", commit=True)
        max_dirs       = self._num(self._max_dirs, "max_dirs", commit=True)
        scan_timeout   = self._num(self._scan_timeout, "scan_timeout", commit=True)
        use_subcats    = self._use_subcats.get()

        def status(msg: str) -> None:
            self._event_queue.put({"type": "status", "value": msg})

        self._start_task(
            "Scanning...",
            lambda progress, _log: {
                "type": "scan_done",
                "result": scan_folder(
                    folder=folder, recursive=recursive,
                    include_hidden=include_hidden, max_depth=max_depth,
                    max_dirs=max_dirs, scan_timeout=scan_timeout,
                    use_subcategories=use_subcats,
                    progress_callback=progress, status_callback=status,
                ),
            },
            log_tab=False,
            moves_files=False,
        )

    def _handle_scan_done(self, result: ScanResult) -> None:
        # Consume the auto-mode flag first so it can never leak into a manual scan.
        auto_mode, self._auto_mode = self._auto_mode, False
        if self._plan_outdated:
            self._plan_outdated = False
            self._set_busy(False)
            self._set_progress(100.0)
            self._scan_result = None
            self._render_scan_result()
            self._status("The rules changed during the scan -- press Scan again.")
            self._log("[WARN]  The rules changed while scanning -- the result was discarded"
                      + (" and the automatic run skipped." if auto_mode else "."))
            return
        self._scan_result = result
        kept = 0
        if self._excluded_keys:
            for plan in result.plans:
                if not plan.skipped and os.path.normcase(str(plan.source)) in self._excluded_keys:
                    plan.excluded = True
                    kept += 1
        self._set_busy(False)
        self._set_progress(100.0)

        for note in result.notes:
            self._log(note)
        for err in result.errors:
            self._log(f"[WARN]  {err}")

        actionable = self._actionable_plans()
        skipped    = [p for p in result.plans if p.skipped]

        self._log(
            f"Scan complete -- {result.total_files} file(s) found, "
            f"{len(actionable)} to move, {len(skipped)} already placed."
            + (f" {kept} file(s) stay where they are (Don't move)." if kept else "")
        )
        self._render_scan_result()

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
        else:
            self._log("No duplicate files detected.")

        if actionable:
            self._status(f"Ready -- {len(actionable)} file(s) to organise.{dup_msg}")
            self._notebook.select(self._preview_tab_idx)
        else:
            self._status(f"Nothing to organise.{dup_msg}")
            if result.duplicate_groups:
                self._notebook.select(self._dup_tab_idx)

        if auto_mode and not self._close_requested:
            if actionable:
                self._log("[SCHEDULE]  Auto-organizing now...")
                self._run_auto_organize(list(actionable))

    def _render_scan_result(self) -> None:
        """Fill the Preview and Duplicates tabs from self._scan_result.

        The rows are inserted in slices of _RENDER_BUDGET_S, so even a scan of
        100 000 files never freezes the window. Every call cancels a fill that
        is still running from an earlier call.
        """
        self._render_gen += 1
        result = self._scan_result
        self._clear_preview()
        self._clear_duplicates()
        if result is None:
            self._refresh_persistent_buttons()
            return

        self._set_tab_count(self._dup_tab_idx, len(result.duplicate_groups))
        self._fill_trees(self._render_gen, self._dup_rows(result))
        self._render_preview()

    def _dup_rows(self, result: ScanResult) -> Iterator[None]:
        """Insert the Duplicates rows one by one, yielding after each."""
        # _dup_groups: group_node_iid -> list of file iids in that group
        for group_idx, group in enumerate(result.duplicate_groups, start=1):
            node = self._dup_tree.insert("", "end", text=f"Group {group_idx}",
                                         values=("", "", ""), open=True,
                                         tags=("group",))
            file_iids: list[str] = []
            # Registered before its rows exist: while a group is half filled,
            # selecting its visible rows already counts as "whole group", so
            # Trash can only become stricter, never let a whole group go.
            self._dup_groups[node] = file_iids
            for dup in group:
                iid = self._dup_tree.insert(
                    node, "end",
                    values=(dup.name, _human_size(dup), str(dup.parent)),
                    tags=("file",),
                )
                self._dup_paths[iid] = dup
                file_iids.append(iid)
                yield

    def _fill_trees(self, gen: int, rows: Iterator[None], preview: bool = False) -> None:
        """Insert rows for at most _RENDER_BUDGET_S, then continue on the next tick.

        Preview and Duplicates are filled separately (preview=True/False), so
        filtering the Preview never cancels a Duplicates fill.
        """
        if gen != (self._preview_gen if preview else self._render_gen):
            return   # a newer result or filter replaced this one
        deadline = time.monotonic() + _RENDER_BUDGET_S
        for _ in rows:
            if time.monotonic() >= deadline:
                # The gap lets Tk redraw: a timer that is already due would
                # always run before the (idle) redraw and starve it.
                self.after(_YIELD_MS, self._fill_trees, gen, rows, preview)
                break
        self._sync_empty(self._preview_tree, self._preview_empty)
        self._sync_empty(self._dup_tree, self._dup_empty)

    # ---- Preview: filter, sort, "Don't move" (#77, #78) --------------------

    _PREVIEW_HEADINGS = {"file": "FILE", "category": "CATEGORY", "destination": "DESTINATION"}
    _PREVIEW_EMPTY = "Pick a folder and press Scan to see what would move."

    def _preview_plans(self) -> list[FilePlan]:
        """Rows of the Preview: every file that is not already in place."""
        if not self._scan_result:
            return []
        return [p for p in self._scan_result.plans if not p.skipped]

    def _preview_values(self, plan: FilePlan) -> tuple[str, str, str]:
        if plan.excluded:
            return (plan.source.name, plan.category, "—  not moved")
        return (plan.source.name, plan.category, str(plan.destination.parent))

    def _render_preview(self) -> None:
        """Fill the Preview from the plan, applying the filter and the sort order."""
        self._preview_gen += 1
        self._preview_tree.delete(*self._preview_tree.get_children())
        self._preview_items = {}
        plans = self._preview_plans()
        needle = self._filter_var.get().strip().lower()
        if needle:
            plans = [p for p in plans if needle in p.source.name.lower()
                     or needle in p.category.lower() or needle in str(p.destination.parent).lower()]
        column, descending = self._preview_sort
        if column:
            index = ("file", "category", "destination").index(column)
            plans = sorted(plans, key=lambda p: self._preview_values(p)[index].lower(),
                           reverse=descending)
        total = len(self._preview_plans())
        self._filter_info_var.set(f"{len(plans)} of {total} shown" if needle else "")
        if not total:
            self._preview_empty.configure(
                text="Nothing to move -- every file is already in its folder."
                if self._scan_result and self._scan_result.plans else
                "No files to organise in this folder.")
        elif not plans:
            self._preview_empty.configure(text="No file matches the search.")

        def rows() -> Iterator[None]:
            for plan in plans:
                iid = self._preview_tree.insert("", "end", values=self._preview_values(plan),
                                                tags=("excluded",) if plan.excluded else ())
                self._preview_items[iid] = plan
                yield
        self._fill_trees(self._preview_gen, rows(), preview=True)
        self._update_plan_counts()

    def _update_plan_counts(self) -> None:
        result = self._scan_result
        if result is None:
            self._summary_var.set("")
            self._set_tab_count(self._preview_tab_idx, 0)
            self._refresh_persistent_buttons()
            return
        actionable = self._actionable_plans()
        excluded   = sum(1 for p in result.plans if p.excluded and not p.skipped)
        in_place   = sum(1 for p in result.plans if p.skipped)
        summary = f"{len(actionable)} to move"
        if excluded:
            summary += f"  ·  {excluded} not moved"
        summary += f"  ·  {in_place} in place"
        if result.duplicate_groups:
            summary += f"  ·  {len(result.duplicate_groups)} duplicate groups"
        self._summary_var.set(summary)
        self._set_tab_count(self._preview_tab_idx, len(actionable))
        self._refresh_persistent_buttons()

    def _on_filter_changed(self, *_args: Any) -> None:
        if self._filter_job:
            self.after_cancel(self._filter_job)
        self._filter_job = self.after(150, self._apply_filter)

    def _apply_filter(self) -> None:
        self._filter_job = None
        if self._scan_result is not None:
            self._render_preview()

    def _on_filter_escape(self, _event: Any = None) -> str:
        self._filter_var.set("")
        self._preview_tree.focus_set()
        return "break"

    def _sort_preview(self, column: str) -> None:
        current, descending = self._preview_sort
        self._preview_sort = (column, not descending if current == column else False)
        for col, text in self._PREVIEW_HEADINGS.items():
            arrow = ""
            if col == column:
                arrow = "  ▼" if self._preview_sort[1] else "  ▲"
            self._preview_tree.heading(col, text=text + arrow)
        if self._scan_result is not None:
            self._render_preview()

    def _toggle_excluded(self, _event: Any = None) -> str | None:
        """Don't move / move again the selected Preview rows."""
        if self._busy_flag:
            return "break"
        iids = [i for i in self._preview_tree.selection() if i in self._preview_items]
        if not iids:
            return None
        plans = [self._preview_items[i] for i in iids]
        exclude = not all(p.excluded for p in plans)
        for iid, plan in zip(iids, plans):
            plan.excluded = exclude
            key = os.path.normcase(str(plan.source))
            if exclude:
                self._excluded_keys.add(key)
            else:
                self._excluded_keys.discard(key)
            self._preview_tree.item(iid, values=self._preview_values(plan),
                                    tags=("excluded",) if exclude else ())
        self._save_settings()   # kept after a restart, also for automatic runs (#82)
        self._update_plan_counts()
        excluded = (sum(1 for p in self._scan_result.plans if p.excluded and not p.skipped)
                    if self._scan_result else 0)
        self._status(f"Ready -- {len(self._actionable_plans())} file(s) to organise"
                     + (f", {excluded} set to Don't move." if excluded else "."))
        return "break"

    def _export_csv(self) -> None:
        """Save the scan result as CSV (#80)."""
        if self._busy_flag or self._modal_open():
            return
        result = self._scan_result
        if result is None:
            _showinfo("Nothing to export", "Scan a folder first.", parent=self)
            return
        start = Path.home() / "Documents"
        name = f"simple_organizer_{self._folder.name or 'scan'}_{time.strftime('%Y-%m-%d_%H%M')}.csv"
        self._native_dialog = True
        try:
            target = filedialog.asksaveasfilename(
                parent=self, title="Export scan result", defaultextension=".csv",
                initialdir=str(start if start.is_dir() else Path.home()), initialfile=name,
                filetypes=[("CSV file", "*.csv"), ("All files", "*.*")])
        finally:
            self._native_dialog = False
        if not target:
            return
        rows: list[list[str]] = []
        for p in result.plans:
            status = ("already in place" if p.skipped else "don't move" if p.excluded else "move")
            rows.append([status, p.source.name, p.category, str(p.source.parent),
                         "" if p.skipped or p.excluded else str(p.destination.parent), str(p.size)])
        for number, group in enumerate(result.duplicate_groups, start=1):
            for path in group:
                try:
                    size = str(path.stat().st_size)
                except OSError:
                    size = ""
                rows.append([f"duplicate (group {number})", path.name, "", str(path.parent), "", size])
        try:
            # utf-8-sig and the system's list separator: Excel opens it correctly.
            with open(target, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh, delimiter=csv_delimiter())
                writer.writerow(["Status", "File", "Category", "Source folder",
                                 "Destination folder", "Size (bytes)"])
                writer.writerows([[_csv_text(c) for c in r] for r in rows])
        except OSError as exc:
            _showerror("Export failed", f"Could not write {target}:\n{exc.strerror or exc}", parent=self)
            return
        self._log(f"Scan result exported to {target} ({len(rows)} rows).")
        replaced = sum(1 for r in rows if _printable(r[1]) != r[1])
        if replaced:
            self._log(f"[WARN]  {replaced} file name(s) are not valid UTF-8 -- "
                      "shown with � in the CSV file.")
        self._notify("Exported", f"{Path(target).name} -- {len(rows)} rows.", "success")

    def _prune_scan_result(self, gone: list[Path]) -> None:
        """Drop the files in gone (e.g. just trashed) from the scan result and
        redraw it, so Organize never works on stale paths. gone is worked out
        by the task thread: checking every file here would freeze the window."""
        result = self._scan_result
        if result is None or not gone:
            return
        gone_keys = {os.path.normcase(str(p)) for p in gone}
        def kept(p: Path) -> bool:
            return os.path.normcase(str(p)) not in gone_keys
        result.plans = [p for p in result.plans if kept(p.source)]
        result.total_bytes = sum(p.size for p in result.plans if not p.skipped)
        groups = [[f for f in g if kept(f)] for g in result.duplicate_groups]
        result.duplicate_groups = [g for g in groups if len(g) > 1]
        self._render_scan_result()

    def _run_auto_organize(self, plans: list[FilePlan]) -> None:
        self._start_organize(plans, self._use_staging.get(), "Auto-organizing...",
                             scheduled=True)

    # =========================================================================
    # Organise
    # =========================================================================

    def _confirm_and_organize(self) -> None:
        if self._busy_flag:
            return
        result = self._scan_result
        if not result:
            return

        actionable = self._actionable_plans()
        if not actionable:
            if any(p.excluded for p in result.plans):
                _showinfo("Nothing to do", "Every file is set to \u201cDon't move\u201d.", parent=self)
            else:
                _showinfo("Nothing to do", "All files are already organised.", parent=self)
            return

        size_str = _fmt_size(sum(p.size for p in actionable))

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
        # The dialog runs a nested event loop: make sure nothing else started
        # or replaced the scan result while it was open.
        if self._busy_flag or self._scan_result is not result:
            self._notify("Not organised",
                         "The scan changed while the dialog was open. Please check "
                         "the preview and try again.", "warning")
            return

        self._start_organize(actionable, staging, "Organising...")

    def _start_organize(self, plans: list[FilePlan], staging: bool, status: str,
                        scheduled: bool = False) -> None:
        self._start_task(
            status,
            lambda progress, log: {
                "type": "organize_done",
                "errors": organise_files(plans=list(plans), progress_callback=progress,
                                         log_callback=log, staging=staging,
                                         scheduled=scheduled),
                "staging": staging,
            })

    def _handle_organize_done(self, errors: list[str], staging: bool) -> None:
        self._scan_result = None   # listed paths are stale once files have moved
        self._set_busy(False)
        self._set_progress(100.0)
        self._render_scan_result()

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
        if self._busy_flag:
            return
        if not has_last_run():
            self._notify("Nothing to undo", "There is no organise run in the history.", "info")
            return
        entries = list_undo_history(limit=1)
        if entries:
            # Name the run in the question and undo exactly that run.
            entry = entries[0]
            if _askyesno(title="Undo Last Organize", message=_undo_question(entry),
                         parent=self) and not self._busy_flag:
                self._undo_specific(entry["file_path"], entry["folder"])
            return
        self._undo_folder = ""
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
        if not confirmed or self._busy_flag:
            return
        self._start_task(
            "Undoing last run...",
            lambda progress, log: {
                "type": "undo_done",
                "errors": undo_last_run(progress_callback=progress, log_callback=log),
            })

    def _handle_undo_done(self, errors: list[str]) -> None:
        self._set_busy(False)
        self._set_progress(100.0)
        # Files moved back: a preview from before the undo no longer matches.
        self._scan_result = None
        self._render_scan_result()
        if errors:
            self._log(f"Undo finished with {len(errors)} error(s). See log.")
            self._status(f"Undo done -- {len(errors)} error(s).")
            self._notify("Undo finished with errors",
                         f"{len(errors)} file(s) could not be restored. See the log.", "warning")
        else:
            self._log("Undo complete -- files restored to original locations.")
            self._status("Undo complete.")
            self._notify("Undo complete", "Files are back where they were.")
        folder, self._undo_folder = self._undo_folder, ""
        if self._schedule_enabled.get() and self._is_current_folder(folder):
            # Outside the queue handler: the question runs its own event loop.
            self.after_idle(self._offer_schedule_pause)

    def _is_current_folder(self, folder: str) -> bool:
        if not folder:
            return False
        current = os.path.normcase(str(self._folder))
        run = os.path.normcase(folder.split(" (+")[0])
        return run == current or run.startswith(os.path.join(current, ""))

    def _offer_schedule_pause(self) -> None:
        """Auto-organize would sort the restored files again at its next run (#75)."""
        if not self._schedule_enabled.get() or self._busy_flag or self._close_requested:
            return
        if _askyesno(
            title="Pause Auto-organize?",
            message=("Auto-organize is on for this folder and would sort the restored files "
                     "again at its next run.\n\nPause it? You can turn it on again in the "
                     "sidebar at any time."),
            parent=self, yes="Pause", no="Keep running",
        ):
            self._schedule_enabled.set(False)
            self._on_schedule_toggle()
            self._log("[SCHEDULE]  Auto-organize paused after an undo.")

    # =========================================================================
    # Staging commit / revert
    # =========================================================================

    def _confirm_and_commit(self) -> None:
        if self._busy_flag:
            return
        confirmed = _askyesno(
            title="Commit Staging",
            message=(
                "Move all staged files to their final category folders?\n\n"
                "- Files are MOVED, not copied.\n"
                "- Nothing will be deleted.\n"
                "- This can be undone with Undo last or History."
            ),
            parent=self,
        )
        if not confirmed or self._busy_flag:
            return
        self._start_task(
            "Committing staging...",
            lambda progress, log: {
                "type": "commit_done",
                "errors": commit_staging(progress_callback=progress, log_callback=log),
            })

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
        if self._busy_flag:
            return
        confirmed = _askyesno(
            title="Revert Staging",
            message=(
                "Move all staged files back to their original locations?\n\n"
                "- Nothing will be deleted.\n"
                "- The staging area will be cleared."
            ),
            parent=self,
        )
        if not confirmed or self._busy_flag:
            return
        self._start_task(
            "Reverting staging...",
            lambda progress, log: {
                "type": "revert_done",
                "errors": revert_staging(progress_callback=progress, log_callback=log),
            })

    def _handle_revert_done(self, errors: list[str]) -> None:
        self._set_busy(False)
        self._set_progress(100.0)
        # Files are back in the scanned folder: an older preview is stale.
        self._scan_result = None
        self._render_scan_result()
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
        # Handle events for at most _POLL_BUDGET_S, then let Tk redraw; if more
        # are waiting, come back after a short redraw gap instead of after 50 ms.
        deadline = time.monotonic() + _POLL_BUDGET_S
        delay    = 50
        try:
            while True:
                if time.monotonic() >= deadline:
                    delay = _YIELD_MS
                    break
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
                    self._handle_trash_done(event["errors"], event["count"], event["gone"])
                elif etype == "schedule_fire":
                    self._run_scheduled_organize()
                elif etype == "error":
                    self._auto_mode = False
                    self._status("Error -- see log.")
                    self._log(f"[ERROR]  {event['value']}")
                    append_error_log(f"Simple Organizer v{APP_VERSION} -- task failed\n"
                                     f"{event.get('details') or event['value']}")
                    closing = self._close_requested
                    if self._task_moves_files:
                        # Some files may have moved before the crash: the plan
                        # shown is out of date and must not be organised again.
                        self._scan_result = None
                        self._render_scan_result()
                    self._set_busy(False)
                    if not closing:   # the window is about to close: log only
                        _showerror("Error", event["value"], parent=self)
        except queue.Empty:
            pass
        finally:
            try:
                self.after(delay, self._poll_queue)
            except tk.TclError:
                pass   # window already destroyed

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
            self._sched_cb, self._sched_spin, self._export_btn,
        ):
            w.configure(state=state)
        self.configure(cursor="watch" if busy else "")
        self._state_var.set("WORKING" if busy else "READY")
        self._state_dot.configure(style="Busy.TLabel" if busy else "Idle.TLabel")
        self._refresh_persistent_buttons()
        if not busy and self._close_requested:
            # Close after the current handler has finished updating the window.
            self.after_idle(self._on_close)

    def _set_progress(self, value: float) -> None:
        self._progress_var.set(value)
        self._pct_var.set(f"{int(value)}%")

    def _log(self, message: str) -> None:
        prefix = message.lstrip().split("]", 1)[0] + "]"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", time.strftime("%H:%M:%S  "), "time")
        self._log_box.insert("end", message + "\n", _LOG_TAGS.get(prefix, ""))
        # With the scheduler running for days the log would grow forever.
        excess = int(self._log_box.index("end-1c").split(".")[0]) - 1 - _LOG_MAX_LINES
        if excess > 0:
            self._log_box.delete("1.0", f"{excess + 1}.0")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _clear_preview(self) -> None:
        self._preview_gen += 1
        self._preview_empty.configure(text=self._PREVIEW_EMPTY)
        self._preview_tree.delete(*self._preview_tree.get_children())
        self._preview_items = {}
        self._set_tab_count(self._preview_tab_idx, 0)
        self._summary_var.set("")
        self._filter_info_var.set("")
        self._sync_empty(self._preview_tree, self._preview_empty)

    def _clear_duplicates(self) -> None:
        self._dup_tree.delete(*self._dup_tree.get_children())
        self._dup_groups = {}
        self._dup_paths = {}
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
        if count == 0 or self._busy_flag:
            self._dup_sel_var.set(f"{count} file(s) selected" if count else "")
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
        if self._busy_flag:
            return
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

        paths: list[Path] = [self._dup_paths[iid] for iid in file_iids if iid in self._dup_paths]
        if not paths:
            return
        # The copies the user keeps, per selected file: trash_files re-checks
        # that one of them still exists before it trashes anything.
        selected = set(file_iids)
        keep: dict[Path, list[Path]] = {}
        for members in self._dup_groups.values():
            kept = [self._dup_paths[m] for m in members if m not in selected and m in self._dup_paths]
            for m in members:
                if m in selected and m in self._dup_paths:
                    keep[self._dup_paths[m]] = kept

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
        if not confirmed or self._busy_flag:
            return

        # Owner for dialogs Windows may show (e.g. "too big for the Recycle Bin"),
        # read here on the GUI thread so they open above the app, not behind it.
        hwnd = self._native_handle()

        def work(progress: Callable[[int, int], None], log: Callable[[str], None]) -> dict:
            errors, trashed = trash_files(paths, log_callback=log, progress_callback=progress,
                                          hwnd=hwnd, keep=keep)
            gone = [p for p in paths if not p.exists()]
            return {"type": "trash_done", "errors": errors, "count": trashed, "gone": gone}

        self._start_task(f"Moving {len(paths)} file(s) to Trash...", work)

    def _handle_trash_done(self, errors: list[str], count: int, gone: list[Path]) -> None:
        self._set_busy(False)
        self._set_progress(100.0)
        # Trashed files leave the duplicate groups and the organise plan, so
        # Organize never tries to move a file that is in the Trash now.
        self._prune_scan_result(gone)
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
        if item not in self._preview_tree.selection():
            self._preview_tree.selection_set(item)

        plan = self._preview_items.get(item)
        if plan is None:
            return
        source_path  = plan.source
        dest_folder  = str(plan.destination.parent)

        menu = self._menu()
        selected = [self._preview_items[i] for i in self._preview_tree.selection()
                    if i in self._preview_items]
        count = f" ({len(selected)} files)" if len(selected) > 1 else ""
        if all(p.excluded for p in selected):
            menu.add_command(label="Move again" + count, command=self._toggle_excluded)
        else:
            menu.add_command(label="Don't move" + count, command=self._toggle_excluded)
        if self._busy_flag:
            menu.entryconfigure(0, state="disabled")
        menu.add_separator()
        has_open  = False
        has_copy  = False

        if source_path and source_path.parent.exists():
            menu.add_command(
                label="Open source folder",
                command=lambda: self._open_folder(str(source_path.parent))
            )
            has_open = True
        # Before Organize the category folder usually does not exist yet.
        if dest_folder and Path(dest_folder).is_dir():
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

        # Group header rows have no path — skip them
        path = self._dup_paths.get(item)
        if path is None:
            return

        folder_path = str(path.parent)
        full_path   = str(path)

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

def _csv_text(value: str) -> str:
    """A CSV cell that Excel and LibreOffice show as text, never run as a formula.

    A file may be called "=1+1.txt" or "-draft.docx"; a cell that starts with
    = + - or @ would be evaluated (CSV injection), so it gets a leading '.
    A name that is not valid UTF-8 (Linux: "caf\\udce9.txt") cannot be written
    to a UTF-8 file; its bad bytes become the replacement character (#97).
    """
    value = _printable(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _printable(value: str) -> str:
    """value with the undecodable bytes of a file name replaced by U+FFFD."""
    try:
        value.encode("utf-8")
        return value
    except UnicodeEncodeError:
        pass
    try:   # Linux: undecodable bytes
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    except UnicodeEncodeError:   # Windows: a lone UTF-16 surrogate in the name
        return value.encode("utf-8", "replace").decode("utf-8")


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

def _bring_running_instance_to_front() -> bool:
    """Show the window of the instance that is already running (Windows only)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        found: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd: int, _lparam: int) -> bool:
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            if title.value.startswith(f"{APP_TITLE}  v") and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(visit, 0)
        if not found:
            return False
        user32.ShowWindow(found[0], 9)          # SW_RESTORE
        user32.SetForegroundWindow(found[0])
        return True
    except Exception:  # noqa: BLE001
        return False


def _message_without_app(title: str, message: str, error: bool = False) -> None:
    """Native message box for the moments before (or instead of) the main window."""
    try:
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        (messagebox.showerror if error else messagebox.showinfo)(title, message, parent=root)
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    # Only one instance: two would share and overwrite the staging manifest and
    # the history. The lock is released by the OS when this process ends.
    lock = acquire_instance_lock()
    if lock is None:
        if not _bring_running_instance_to_front():
            _message_without_app(APP_TITLE, "Simple Organizer is already running.\n\n"
                                            "Switch to the open window instead.")
        return

    def thread_crash(args: threading.ExceptHookArgs) -> None:
        append_error_log(f"Simple Organizer v{APP_VERSION} -- error in thread "
                         f"{getattr(args.thread, 'name', '?')}\n"
                         + "".join(traceback.format_exception(
                             args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = thread_crash

    try:
        app = SimpleOrganizerApp()
    except Exception:  # noqa: BLE001
        path = append_error_log(f"Simple Organizer v{APP_VERSION} -- failed to start\n"
                                + traceback.format_exc())
        _message_without_app(APP_TITLE, "Simple Organizer could not start."
                             + (f"\n\nDetails: {path}" if path else ""), error=True)
        return
    app._instance_lock = lock
    app.mainloop()


if __name__ == "__main__":
    main()
