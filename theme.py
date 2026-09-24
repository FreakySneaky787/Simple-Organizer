# theme.py
"""ttk styling for Simple Organizer.

Rounded controls are drawn as small anti-aliased PNGs generated at runtime and
used as ttk image elements, so no image files or extra packages are needed.
Palettes live in utils.py (LIGHT_THEME / DARK_THEME).
"""

import base64
import struct
import sys
import tkinter as tk
import zlib
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Callable

_UI_FAMILIES   = ("Segoe UI", "Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans")
_MONO_FAMILIES = ("Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono",
                  "Liberation Mono", "Courier New")

RADIUS      = 4   # buttons, inputs
CARD_RADIUS = 8   # cards and panels

FONTS: dict[str, tuple[Any, ...]] = {}

# Images must outlive the elements that use them; ttk only keeps the name.
_IMAGES: dict[str, list[tk.PhotoImage]] = {}


# ---------------------------------------------------------------------------
# Fonts / window chrome
# ---------------------------------------------------------------------------

def load_fonts(root: tk.Misc) -> None:
    """Pick the first installed UI and monospace families. Needs a live Tk root."""
    available = set(tkfont.families(root))
    ui   = next((f for f in _UI_FAMILIES if f in available),
                tkfont.nametofont("TkDefaultFont").actual("family"))
    mono = next((f for f in _MONO_FAMILIES if f in available),
                tkfont.nametofont("TkFixedFont").actual("family"))
    FONTS.update({
        "ui":      (ui, 10),
        "small":   (ui, 9),
        "bold":    (ui, 10, "bold"),
        "caption": (ui, 8, "bold"),
        "tab":     (ui, 9, "bold"),
        "brand":   (ui, 11, "bold"),
        "step":    (ui, 11),
        "mono":    (mono, 9),
        "mono_sm": (mono, 8),
    })


def float_key(t: dict[str, str]) -> str:
    """Colour keyed out around floating cards (dialogs, toasts) on Windows.

    It is a near twin of the surface colour, so the anti-aliased edge pixels of the
    rounded corners blend towards the card instead of leaving a dark fringe.
    """
    last = int(t["surface"][5:7], 16)
    return f"{t['surface'][:5]}{last - 1 if last else 1:02x}"


def set_titlebar_theme(window: tk.Misc, dark: bool) -> None:
    """Match the native Windows 10/11 title bar to the app theme. No-op elsewhere."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd  = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20; Windows 10 builds before 20H1 used 19.
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tiny rasteriser
# ---------------------------------------------------------------------------

Shape = Callable[[float, float], bool]


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return int(hex_colour[1:3], 16), int(hex_colour[3:5], 16), int(hex_colour[5:7], 16)


def _round_rect(x0: float, y0: float, x1: float, y1: float, r: float) -> Shape:
    def hit(px: float, py: float) -> bool:
        if not (x0 <= px <= x1 and y0 <= py <= y1):
            return False
        cx = min(max(px, x0 + r), x1 - r)
        cy = min(max(py, y0 + r), y1 - r)
        return (px - cx) ** 2 + (py - cy) ** 2 <= r * r
    return hit


def _stroke(points: list[tuple[float, float]], width: float) -> Shape:
    segments = list(zip(points, points[1:]))
    limit = (width / 2) ** 2

    def hit(px: float, py: float) -> bool:
        for (ax, ay), (bx, by) in segments:
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            if (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2 <= limit:
                return True
        return False
    return hit


def _png(width: int, height: int, rows: list[bytes]) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def _render(root: tk.Misc, width: int, height: int, layers: list[tuple[Shape, str]],
            samples: int = 3, grow: tuple[int, int] = (0, 0)) -> tk.PhotoImage:
    """Composite shapes back to front with supersampled coverage.

    grow widens/heightens the result by repeating the middle column/row. ttk tiles
    the centre of a 9-sliced image, so a tiny centre means thousands of alpha blits
    per redraw; a large one keeps big cards cheap to paint.
    """
    offsets = [(i + 0.5) / samples for i in range(samples)]
    total   = samples * samples
    colours = [(shape, _rgb(colour)) for shape, colour in layers]
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            r = g = b = a = 0.0
            for shape, (cr, cg, cb) in colours:
                cov = sum(shape(x + ox, y + oy) for ox in offsets for oy in offsets) / total
                if cov:
                    r = cr * cov + r * (1 - cov)
                    g = cg * cov + g * (1 - cov)
                    b = cb * cov + b * (1 - cov)
                    a = cov + a * (1 - cov)
            if a:
                row += bytes((round(r / a), round(g / a), round(b / a), round(a * 255)))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))

    extra_w, extra_h = grow
    if extra_w:
        mid = (width // 2) * 4
        rows = [row[:mid] + row[mid:mid + 4] * extra_w + row[mid:] for row in rows]
    if extra_h:
        mid = height // 2
        rows = rows[:mid] + [rows[mid]] * extra_h + rows[mid:]
    return rgba_image(root, width + extra_w, height + extra_h, rows)


def rgba_image(root: tk.Misc, width: int, height: int, rows: list[bytes]) -> tk.PhotoImage:
    """Build a PhotoImage from rows of RGBA bytes (keeps real alpha, unlike put())."""
    return tk.PhotoImage(master=root, data=base64.b64encode(_png(width, height, rows)))


def _box(root: tk.Misc, size: int, radius: int, fill: str, edge: str,
         grow: int = 160) -> tk.PhotoImage:
    """Rounded rectangle with a 1px border, meant to be 9-sliced by ttk."""
    return _render(root, size, size, [
        (_round_rect(0, 0, size, size, radius), edge),
        (_round_rect(1, 1, size - 1, size - 1, radius - 1), fill),
    ], grow=(grow, grow))


# ---------------------------------------------------------------------------
# Image elements
# ---------------------------------------------------------------------------

def _create_elements(style: ttk.Style, key: str, t: dict[str, str]) -> None:
    """Create this palette's image elements once; they are reused on later toggles."""
    if key in _IMAGES:
        return
    root   = style.master
    images = _IMAGES.setdefault(key, [])

    def box(size: int, radius: int, fill: str, edge: str, grow: int = 160) -> tk.PhotoImage:
        img = _box(root, size, radius, fill, edge, grow)
        images.append(img)
        return img

    def element(name: str, normal: tk.PhotoImage, states: list[tuple[str, tk.PhotoImage]],
                border: int | tuple[int, ...], base: tuple[int, int] | None = None) -> None:
        """base is the unstretched image size, used as the element's minimum size."""
        options: dict[str, Any] = {"border": border, "sticky": "nsew", "padding": 0}
        if base:
            options.update(width=base[0], height=base[1])
        style.element_create(f"{key}.{name}", "image", normal, *states, **options)

    r, b = RADIUS, RADIUS + 2
    size = 2 * b + 4
    button, hover, field = t["button"], t["hover"], t["field"]
    border, strong, accent = t["border"], t["border_strong"], t["accent"]

    # Buttons: (normal fill, edge), hover, pressed
    variants = {
        "btn":     ((button, strong),        (hover, strong),              (border, strong)),
        "primary": ((accent, accent),        (t["accent_hover"],) * 2,     (t["accent_hover"],) * 2),
        "danger":  ((button, strong),        (t["danger"],) * 2,           (t["danger"],) * 2),
        "ghost":   ((t["bg"], t["bg"]),      (t["surface_alt"],) * 2,      (hover, hover)),
        "flat":    ((t["surface"],) * 2,     (t["surface_alt"],) * 2,      (hover, hover)),
    }
    for name, (normal, over, down) in variants.items():
        element(name, box(size, r, *normal), [
            ("disabled", box(size, r, button, border)),
            ("pressed",  box(size, r, *down)),
            ("active",   box(size, r, *over)),
            ("focus",    box(size, r, normal[0], accent)),
        ], border=b, base=(size, size))

    element("field", box(size, r, field, border), [
        ("disabled", box(size, r, t["surface"], border)),
        ("focus",    box(size, r, field, accent)),
        ("hover",    box(size, r, field, strong)),
    ], border=b, base=(size, size))

    card = 2 * (CARD_RADIUS + 2) + 4
    element("card", box(card, CARD_RADIUS, t["surface"], border, grow=640), [],
            border=CARD_RADIUS + 2, base=(card, card))

    # Check box: 16px box plus an 8px transparent gap before the label.
    def check(fill: str, edge: str, mark: str | None) -> tk.PhotoImage:
        layers = [(_round_rect(0, 0, 16, 16, 3), edge),
                  (_round_rect(1, 1, 15, 15, 2), fill)]
        if mark:
            layers.append((_stroke([(4.2, 8.4), (6.8, 11.0), (11.8, 5.4)], 1.9), mark))
        img = _render(root, 24, 16, layers)
        images.append(img)
        return img

    element("check", check(field, strong, None), [
        ("disabled selected", check(strong, strong, t["fg_muted"])),
        ("disabled",          check(t["surface"], border, None)),
        ("selected",          check(accent, accent, t["accent_fg"])),
        ("active",            check(field, accent, None)),
    ], border=0)

    # Scrollbar thumbs: pill inside a 1px transparent margin.
    def thumb(w: int, h: int, colour: str) -> tk.PhotoImage:
        img = _render(root, w, h, [(_round_rect(1, 1, w - 1, h - 1, min(w, h) / 2 - 1), colour)],
                      grow=(0, 160) if h > w else (160, 0))
        images.append(img)
        return img

    element("vthumb", thumb(10, 24, strong), [("active", thumb(10, 24, t["fg_muted"]))],
            border=5, base=(10, 24))
    element("hthumb", thumb(24, 10, strong), [("active", thumb(24, 10, t["fg_muted"]))],
            border=5, base=(24, 10))

    def pill(w: int, h: int, colour: str) -> tk.PhotoImage:
        img = _render(root, w, h, [(_round_rect(0, 0, w, h, h / 2), colour)], grow=(240, 0))
        images.append(img)
        return img

    element("trough", pill(16, 6, border), [], border=(3, 0, 3, 0), base=(16, 6))
    element("pbar", pill(16, 6, accent), [], border=(3, 0, 3, 0), base=(6, 6))

    def chevron(colour: str) -> tk.PhotoImage:
        img = _render(root, 22, 16, [(_stroke([(7, 6.5), (11, 10), (15, 6.5)], 1.5), colour)])
        images.append(img)
        return img

    element("chevron", chevron(t["fg_dim"]), [
        ("disabled", chevron(t["fg_muted"])),
        ("active",   chevron(t["fg"])),
    ], border=0)


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def apply_ttk_theme(style: ttk.Style, t: dict[str, str]) -> None:
    style.theme_use("clam")
    key = "so" + t["bg"].lstrip("#")
    _create_elements(style, key, t)

    bg, surface, alt     = t["bg"], t["surface"], t["surface_alt"]
    field, border        = t["field"], t["border"]
    fg, dim, muted       = t["fg"], t["fg_dim"], t["fg_muted"]
    accent, on_accent    = t["accent"], t["accent_fg"]

    style.configure(".", background=bg, foreground=fg, font=FONTS["ui"],
                    bordercolor=border, lightcolor=bg, darkcolor=bg,
                    troughcolor=surface, focuscolor=accent, insertcolor=fg,
                    selectbackground=t["selection"], selectforeground=t["selection_fg"],
                    borderwidth=0, relief="flat")

    style.layout("Card.TFrame", [(f"{key}.card", {"sticky": "nswe"})])
    style.layout("Float.TFrame", [(f"{key}.card", {"sticky": "nswe"})])
    style.configure("TFrame",               background=bg)
    style.configure("Card.TFrame",          background=bg)
    style.configure("Float.TFrame",         background=float_key(t))
    style.configure("Panel.TFrame",         background=surface)
    style.configure("Bar.TFrame",           background=surface)
    style.configure("Rule.TFrame",          background=border)
    style.configure("Tooltip.TFrame",       background=t["border_strong"])
    style.configure("TabLine.TFrame",       background=surface)
    style.configure("TabLineActive.TFrame", background=accent)
    style.configure("TSeparator",           background=border)

    labels = {
        "TLabel":             (bg,      fg,           FONTS["ui"]),
        "Brand.TLabel":       (bg,      accent,       FONTS["brand"]),
        "Version.TLabel":     (bg,      muted,        FONTS["mono_sm"]),
        "DialogTitle.TLabel": (surface, fg,           FONTS["bold"]),
        "ToastTitle.TLabel":  (surface, fg,           FONTS["bold"]),
        "Summary.TLabel":     (surface, muted,        FONTS["mono_sm"]),
        "Card.TLabel":        (surface, fg,           FONTS["ui"]),
        "CardDim.TLabel":     (surface, dim,          FONTS["ui"]),
        "CardTitle.TLabel":   (surface, dim,          FONTS["caption"]),
        "CardHint.TLabel":    (surface, muted,        FONTS["small"]),
        "Empty.TLabel":       (surface, muted,        FONTS["ui"]),
        "Bar.TLabel":         (surface, dim,          FONTS["small"]),
        "BarMuted.TLabel":    (surface, muted,        FONTS["small"]),
        "BarState.TLabel":    (surface, fg,           FONTS["caption"]),
        "Pct.TLabel":         (surface, dim,          FONTS["mono_sm"]),
        "Idle.TLabel":        (surface, t["success"], FONTS["small"]),
        "Busy.TLabel":        (surface, t["warning"], FONTS["small"]),
        "Tab.TLabel":         (surface, muted,        FONTS["tab"]),
        "TabActive.TLabel":   (surface, fg,           FONTS["tab"]),
        "Badge.TLabel":       (surface, muted,        FONTS["mono_sm"]),
        "BadgeActive.TLabel": (surface, accent,       FONTS["mono_sm"]),
        "Tooltip.TLabel":     (alt,     fg,           FONTS["small"]),
    }
    for name, (back, fore, font) in labels.items():
        style.configure(name, background=back, foreground=fore, font=font)
    style.configure("Tooltip.TLabel", padding=(8, 5))

    # "Card." variants only change the colour behind the rounded corners.
    buttons = {
        "TButton":         ("btn",     fg,          fg,        FONTS["ui"]),
        "Primary.TButton": ("primary", on_accent,   on_accent, FONTS["bold"]),
        "Danger.TButton":  ("danger",  t["danger"], on_accent, FONTS["ui"]),
        "Ghost.TButton":   ("ghost",   dim,         fg,        FONTS["ui"]),
        "Step.TButton":    ("btn",     dim,         fg,        FONTS["step"]),
    }
    for name, (element, fore, over_fg, font) in buttons.items():
        style.layout(name, [(f"{key}.{element}", {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [
                ("Button.label", {"sticky": "nswe"})]})]})])
        style.configure(name, background=bg, foreground=fore, font=font,
                        padding=(12, 5), anchor="center")
        style.map(name, background=[], foreground=[("disabled", muted), ("active", over_fg)])
        style.configure(f"Card.{name}", background=surface)
    style.layout("Card.Ghost.TButton", [(f"{key}.flat", {"sticky": "nswe", "children": [
        ("Button.padding", {"sticky": "nswe", "children": [
            ("Button.label", {"sticky": "nswe"})]})]})])
    style.configure("Ghost.TButton", padding=(8, 4))
    style.configure("Card.Ghost.TButton", padding=(6, 4))
    style.configure("Step.TButton",  padding=0, background=surface)

    style.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        (f"{key}.check",      {"side": "left", "sticky": ""}),
        ("Checkbutton.label", {"side": "left", "sticky": "nswe"})]})])
    for name, back in (("TCheckbutton", bg), ("Card.TCheckbutton", surface)):
        style.configure(name, background=back, foreground=fg, font=FONTS["ui"], padding=(0, 3))
        style.map(name, background=[("active", back)], foreground=[("disabled", muted)])

    style.layout("TEntry", [(f"{key}.field", {"sticky": "nswe", "children": [
        ("Entry.padding", {"sticky": "nswe", "children": [
            ("Entry.textarea", {"sticky": "nswe"})]})]})])
    style.layout("TCombobox", [(f"{key}.field", {"sticky": "nswe", "children": [
        (f"{key}.chevron", {"side": "right", "sticky": ""}),
        ("Combobox.padding", {"expand": "1", "sticky": "nswe", "children": [
            ("Combobox.textarea", {"sticky": "nswe"})]})]})])
    for name in ("TEntry", "TCombobox"):
        style.configure(name, background=bg, fieldbackground=field, foreground=fg,
                        insertcolor=fg, padding=(8, 5))
        style.map(name,
                  background=[],
                  fieldbackground=[("disabled", surface), ("readonly", field)],
                  foreground=[("disabled", muted)])
    style.configure("Card.TEntry", background=surface)
    style.configure("Card.TCombobox", background=surface)
    style.configure("Step.TEntry", background=surface, padding=(4, 4))
    style.map("TCombobox",
              selectbackground=[("readonly", field)],
              selectforeground=[("readonly", fg)])

    style.layout("Horizontal.TProgressbar", [(f"{key}.trough", {"sticky": "nswe", "children": [
        (f"{key}.pbar", {"side": "left", "sticky": "ns"})]})])
    style.configure("Horizontal.TProgressbar", background=surface, thickness=6)

    for orient, sticky, thumb in (("Vertical", "ns", "vthumb"), ("Horizontal", "ew", "hthumb")):
        name = f"{orient}.TScrollbar"
        style.layout(name, [(f"{orient}.Scrollbar.trough", {"sticky": sticky, "children": [
            (f"{key}.{thumb}", {"expand": "1", "sticky": "nswe"})]})])
        style.configure(name, troughcolor=surface, background=surface, bordercolor=surface,
                        lightcolor=surface, darkcolor=surface)

    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.layout("Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
        ("Treeitem.indicator", {"side": "left", "sticky": ""}),
        ("Treeitem.image",     {"side": "left", "sticky": ""}),
        ("Treeitem.text",      {"side": "left", "sticky": ""})]})])
    style.configure("Treeview", background=surface, fieldbackground=surface, foreground=fg,
                    font=FONTS["ui"], rowheight=28, indent=16)
    style.map("Treeview",
              background=[("selected", t["selection"])],
              foreground=[("selected", t["selection_fg"])])
    style.configure("Treeview.Heading", background=surface, foreground=muted,
                    font=FONTS["caption"], bordercolor=border, lightcolor=surface,
                    darkcolor=border, relief="flat", padding=(10, 7))
    style.map("Treeview.Heading", background=[("active", alt)], lightcolor=[("active", alt)])

    style.layout("Bare.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
    style.layout("Bare.TNotebook.Tab", [])
    style.configure("Bare.TNotebook", background=surface, bordercolor=surface,
                    lightcolor=surface, darkcolor=surface, borderwidth=0, tabmargins=0)
