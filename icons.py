# icons.py
"""Phosphor icons (regular weight), rendered at runtime in any colour.

Path data comes from @phosphor-icons/core 2.1.1, MIT License,
Copyright (c) 2023 Phosphor Icons. https://phosphoricons.com
Each path uses a 256x256 view box.
"""

import math
import re
import tkinter as tk

from theme import rgba_image

PATHS: dict[str, str] = {
    "arrow-counter-clockwise": (
        "M224,128a96,96,0,0,1-94.71,96H128A95.38,95.38,0,0,1,62.1,197.8a"
        "8,8,0,0,1,11-11.63A80,80,0,1,0,71.43,71.39a3.07,3.07,0,0,1-.26.25L44.59,96H72a"
        "8,8,0,0,1,0,16H24a8,8,0,0,1-8-8V56a8,8,0,0,1,16,0V85.8L60.25,60A"
        "96,96,0,0,1,224,128Z"
    ),
    "arrow-down": (
        "M205.66,149.66l-72,72a8,8,0,0,1-11.32,0l-72-72a8,8,0,0,1,11.32-11.32L120,196.69V"
        "40a8,8,0,0,1,16,0V196.69l58.34-58.35a8,8,0,0,1,11.32,11.32Z"
    ),
    "arrow-u-up-left": (
        "M232,144a64.07,64.07,0,0,1-64,64H80a8,8,0,0,1,0-16h88a48,48,0,0,0,0-96H51.31l"
        "34.35,34.34a8,8,0,0,1-11.32,11.32l-48-48a8,8,0,0,1,0-11.32l48-48A"
        "8,8,0,0,1,85.66,45.66L51.31,80H168A64.07,64.07,0,0,1,232,144Z"
    ),
    "arrow-up": (
        "M205.66,117.66a8,8,0,0,1-11.32,0L136,59.31V216a8,8,0,0,1-16,0V59.31L"
        "61.66,117.66a8,8,0,0,1-11.32-11.32l72-72a8,8,0,0,1,11.32,0l72,72A"
        "8,8,0,0,1,205.66,117.66Z"
    ),
    "check": (
        "M229.66,77.66l-128,128a8,8,0,0,1-11.32,0l-56-56a8,8,0,0,1,11.32-11.32L"
        "96,188.69,218.34,66.34a8,8,0,0,1,11.32,11.32Z"
    ),
    "clock-counter-clockwise": (
        "M136,80v43.47l36.12,21.67a8,8,0,0,1-8.24,13.72l-40-24A8,8,0,0,1,120,128V80a"
        "8,8,0,0,1,16,0Zm-8-48A95.44,95.44,0,0,0,60.08,60.15C"
        "52.81,67.51,46.35,74.59,40,82V64a8,8,0,0,0-16,0v40a8,8,0,0,0,8,8H72a"
        "8,8,0,0,0,0-16H49c7.15-8.42,14.27-16.35,22.39-24.57a"
        "80,80,0,1,1,1.66,114.75,8,8,0,1,0-11,11.64A96,96,0,1,0,128,32Z"
    ),
    "copy": (
        "M216,32H88a8,8,0,0,0-8,8V80H40a8,8,0,0,0-8,8V216a8,8,0,0,0,8,8H168a"
        "8,8,0,0,0,8-8V176h40a8,8,0,0,0,8-8V40A8,8,0,0,0,216,32ZM160,208H48V96H160Zm"
        "48-48H176V88a8,8,0,0,0-8-8H96V48H208Z"
    ),
    "eraser": (
        "M225,80.4,183.6,39a24,24,0,0,0-33.94,0L31,157.66a24,24,0,0,0,0,33.94l"
        "30.06,30.06A8,8,0,0,0,66.74,224H216a8,8,0,0,0,0-16h-84.7L225,114.34A"
        "24,24,0,0,0,225,80.4ZM108.68,208H70.05L42.33,180.28a8,8,0,0,1,0-11.31L"
        "96,115.31,148.69,168Zm105-105L160,156.69,107.31,104,161,50.34a8,8,0,0,1,11.32,0l"
        "41.38,41.38a8,8,0,0,1,0,11.31Z"
    ),
    "eye": (
        "M247.31,124.76c-.35-.79-8.82-19.58-27.65-38.41C194.57,61.26,162.88,48,128,48S"
        "61.43,61.26,36.34,86.35C17.51,105.18,9,124,8.69,124.76a8,8,0,0,0,0,6.5c"
        ".35.79,8.82,19.57,27.65,38.4C61.43,194.74,93.12,208,128,208s"
        "66.57-13.26,91.66-38.34c18.83-18.83,27.3-37.61,27.65-38.4A"
        "8,8,0,0,0,247.31,124.76ZM128,192c-30.78,0-57.67-11.19-79.93-33.25A"
        "133.47,133.47,0,0,1,25,128,133.33,133.33,0,0,1,48.07,97.25C"
        "70.33,75.19,97.22,64,128,64s57.67,11.19,79.93,33.25A"
        "133.46,133.46,0,0,1,231.05,128C223.84,141.46,192.43,192,128,192Zm0-112a"
        "48,48,0,1,0,48,48A48.05,48.05,0,0,0,128,80Zm0,80a32,32,0,1,1,32-32A"
        "32,32,0,0,1,128,160Z"
    ),
    "folder-dashed": (
        "M96,208a8,8,0,0,1-8,8H39.38A15.4,15.4,0,0,1,24,200.62V192a8,8,0,0,1,16,0v8H88A"
        "8,8,0,0,1,96,208Zm64-8H128a8,8,0,0,0,0,16h32a8,8,0,0,0,0-16Zm64-56a"
        "8,8,0,0,0-8,8v48H200a8,8,0,0,0,0,16h16.89A15.13,15.13,0,0,0,232,200.89V152A"
        "8,8,0,0,0,224,144Zm-8-72H168a8,8,0,0,0,0,16h48v24a8,8,0,0,0,16,0V88A"
        "16,16,0,0,0,216,72ZM24,80V56A16,16,0,0,1,40,40H92.69A"
        "15.86,15.86,0,0,1,104,44.69l29.66,29.65A8,8,0,0,1,128,88H32A8,8,0,0,1,24,80Zm"
        "16-8h68.69l-16-16H40Zm-8,88a8,8,0,0,0,8-8V120a8,8,0,0,0-16,0v32A"
        "8,8,0,0,0,32,160Z"
    ),
    "folder-open": (
        "M245,110.64A16,16,0,0,0,232,104H216V88a16,16,0,0,0-16-16H130.67L102.94,51.2a"
        "16.14,16.14,0,0,0-9.6-3.2H40A16,16,0,0,0,24,64V208h0a8,8,0,0,0,8,8H211.1a"
        "8,8,0,0,0,7.59-5.47l28.49-85.47A16.05,16.05,0,0,0,245,110.64ZM"
        "93.34,64,123.2,86.4A8,8,0,0,0,128,88h72v16H69.77a16,16,0,0,0-15.18,10.94L"
        "40,158.7V64Zm112,136H43.1l26.67-80H232Z"
    ),
    "folders": (
        "M224,64H154.67L126.93,43.2a16.12,16.12,0,0,0-9.6-3.2H72A16,16,0,0,0,56,56V72H40A"
        "16,16,0,0,0,24,88V200a16,16,0,0,0,16,16H192.89A15.13,15.13,0,0,0,208,200.89V184h"
        "16.89A15.13,15.13,0,0,0,240,168.89V80A16,16,0,0,0,224,64ZM192,200H40V88H85.33l"
        "29.87,22.4A8,8,0,0,0,120,112h72Zm32-32H208V112a16,16,0,0,0-16-16H122.67L"
        "94.93,75.2a16.12,16.12,0,0,0-9.6-3.2H72V56h45.33L147.2,78.4A8,8,0,0,0,152,80h72Z"
    ),
    "funnel": (
        "M230.6,49.53A15.81,15.81,0,0,0,216,40H40A16,16,0,0,0,28.19,66.76l.08.09L"
        "96,139.17V216a16,16,0,0,0,24.87,13.32l32-21.34A16,16,0,0,0,160,194.66V139.17l"
        "67.74-72.32.08-.09A15.8,15.8,0,0,0,230.6,49.53ZM40,56h0Zm106.18,74.58A"
        "8,8,0,0,0,144,136v58.66L112,216V136a8,8,0,0,0-2.16-5.47L40,56H216Z"
    ),
    "info": (
        "M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a"
        "88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216Zm16-40a"
        "8,8,0,0,1-8,8,16,16,0,0,1-16-16V128a8,8,0,0,1,0-16,16,16,0,0,1,16,16v40A"
        "8,8,0,0,1,144,176ZM112,84a12,12,0,1,1,12,12A12,12,0,0,1,112,84Z"
    ),
    "magnifying-glass": (
        "M229.66,218.34l-50.07-50.06a88.11,88.11,0,1,0-11.31,11.31l50.06,50.07a"
        "8,8,0,0,0,11.32-11.32ZM40,112a72,72,0,1,1,72,72A72.08,72.08,0,0,1,40,112Z"
    ),
    "minus": (
        "M224,128a8,8,0,0,1-8,8H40a8,8,0,0,1,0-16H216A8,8,0,0,1,224,128Z"
    ),
    "moon": (
        "M233.54,142.23a"
        "8,8,0,0,0-8-2,88.08,88.08,0,0,1-109.8-109.8,8,8,0,0,0-10-10,104.84,104.84,0,0,0-52.91,37A"
        "104,104,0,0,0,136,224a"
        "103.09,103.09,0,0,0,62.52-20.88,104.84,104.84,0,0,0,37-52.91A"
        "8,8,0,0,0,233.54,142.23ZM188.9,190.34A88,88,0,0,1,65.66,67.11a"
        "89,89,0,0,1,31.4-26A106,106,0,0,0,96,56,104.11,104.11,0,0,0,200,160a"
        "106,106,0,0,0,14.92-1.06A89,89,0,0,1,188.9,190.34Z"
    ),
    "pencil-simple": (
        "M227.31,73.37,182.63,28.68a16,16,0,0,0-22.63,0L36.69,152A"
        "15.86,15.86,0,0,0,32,163.31V208a16,16,0,0,0,16,16H92.69A"
        "15.86,15.86,0,0,0,104,219.31L227.31,96a16,16,0,0,0,0-22.63ZM92.69,208H48V163.31l"
        "88-88L180.69,120ZM192,108.68,147.31,64l24-24L216,84.68Z"
    ),
    "plus": (
        "M224,128a8,8,0,0,1-8,8H136v80a8,8,0,0,1-16,0V136H40a8,8,0,0,1,0-16h80V40a"
        "8,8,0,0,1,16,0v80h80A8,8,0,0,1,224,128Z"
    ),
    "question": (
        "M140,180a12,12,0,1,1-12-12A12,12,0,0,1,140,180ZM128,72c-22.06,0-40,16.15-40,36v"
        "4a8,8,0,0,0,16,0v-4c0-11,10.77-20,24-20s24,9,24,20-10.77,20-24,20a8,8,0,0,0-8,8v"
        "8a8,8,0,0,0,16,0v-.72c18.24-3.35,32-17.9,32-35.28C168,88.15,150.06,72,128,72Zm"
        "104,56A104,104,0,1,1,128,24,104.11,104.11,0,0,1,232,128Zm-16,0a"
        "88,88,0,1,0-88,88A88.1,88.1,0,0,0,216,128Z"
    ),
    "sun": (
        "M120,40V16a8,8,0,0,1,16,0V40a8,8,0,0,1-16,0Zm72,88a64,64,0,1,1-64-64A"
        "64.07,64.07,0,0,1,192,128Zm-16,0a48,48,0,1,0-48,48A48.05,48.05,0,0,0,176,128ZM"
        "58.34,69.66A8,8,0,0,0,69.66,58.34l-16-16A8,8,0,0,0,42.34,53.66Zm0,116.68-16,16a"
        "8,8,0,0,0,11.32,11.32l16-16a8,8,0,0,0-11.32-11.32ZM192,72a8,8,0,0,0,5.66-2.34l"
        "16-16a8,8,0,0,0-11.32-11.32l-16,16A8,8,0,0,0,192,72Zm5.66,114.34a"
        "8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32-11.32ZM48,128a8,8,0,0,0-8-8H16a"
        "8,8,0,0,0,0,16H40A8,8,0,0,0,48,128Zm80,80a8,8,0,0,0-8,8v24a8,8,0,0,0,16,0V216A"
        "8,8,0,0,0,128,208Zm112-88H216a8,8,0,0,0,0,16h24a8,8,0,0,0,0-16Z"
    ),
    "terminal-window": (
        "M128,128a8,8,0,0,1-3,6.25l-40,32a8,8,0,1,1-10-12.5L107.19,128,75,102.25a"
        "8,8,0,1,1,10-12.5l40,32A8,8,0,0,1,128,128Zm48,24H136a8,8,0,0,0,0,16h40a"
        "8,8,0,0,0,0-16Zm56-96V200a16,16,0,0,1-16,16H40a16,16,0,0,1-16-16V56A"
        "16,16,0,0,1,40,40H216A16,16,0,0,1,232,56ZM216,200V56H40V200H216Z"
    ),
    "toggle-right": (
        "M176,56H80a72,72,0,0,0,0,144h96a72,72,0,0,0,0-144Zm0,128H80A56,56,0,0,1,80,72h"
        "96a56,56,0,0,1,0,112Zm0-96a40,40,0,1,0,40,40A40,40,0,0,0,176,88Zm0,64a"
        "24,24,0,1,1,24-24A24,24,0,0,1,176,152Z"
    ),
    "trash": (
        "M216,48H176V40a24,24,0,0,0-24-24H104A24,24,0,0,0,80,40v8H40a8,8,0,0,0,0,16h8V"
        "208a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V64h8a8,8,0,0,0,0-16ZM96,40a"
        "8,8,0,0,1,8-8h48a8,8,0,0,1,8,8v8H96Zm96,168H64V64H192ZM112,104v64a"
        "8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Zm48,0v64a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Z"
    ),
    "warning": (
        "M236.8,188.09,149.35,36.22h0a24.76,24.76,0,0,0-42.7,0L19.2,188.09a"
        "23.51,23.51,0,0,0,0,23.72A24.35,24.35,0,0,0,40.55,224h174.9a"
        "24.35,24.35,0,0,0,21.33-12.19A23.51,23.51,0,0,0,236.8,188.09ZM222.93,203.8a"
        "8.5,8.5,0,0,1-7.48,4.2H40.55a8.5,8.5,0,0,1-7.48-4.2,7.59,7.59,0,0,1,0-7.72L"
        "120.52,44.21a8.75,8.75,0,0,1,15,0l87.45,151.87A7.59,7.59,0,0,1,222.93,203.8ZM"
        "120,144V104a8,8,0,0,1,16,0v40a8,8,0,0,1-16,0Zm20,36a12,12,0,1,1-12-12A"
        "12,12,0,0,1,140,180Z"
    ),
    "x-circle": (
        "M165.66,101.66,139.31,128l26.35,26.34a8,8,0,0,1-11.32,11.32L128,139.31l"
        "-26.34,26.35a8,8,0,0,1-11.32-11.32L116.69,128,90.34,101.66a"
        "8,8,0,0,1,11.32-11.32L128,116.69l26.34-26.35a8,8,0,0,1,11.32,11.32ZM232,128A"
        "104,104,0,1,1,128,24,104.11,104.11,0,0,1,232,128Zm-16,0a88,88,0,1,0-88,88A"
        "88.1,88.1,0,0,0,216,128Z"
    ),
    "x": (
        "M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a"
        "8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l"
        "66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z"
    ),
}


_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

_coverage_cache: dict[tuple[str, int], list[list[float]]] = {}
_image_cache: dict[tuple[str, int, str, int], tk.PhotoImage] = {}
_badge_cache: dict[tuple[str, int, int, str, str], tk.PhotoImage] = {}


def _arc(x0: float, y0: float, rx: float, ry: float, angle: float, large: bool,
         sweep: bool, x1: float, y1: float) -> list[tuple[float, float]]:
    """Flatten an SVG elliptical arc (endpoint form) into points, excluding the start."""
    if rx == 0 or ry == 0:
        return [(x1, y1)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(angle)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    x1p = cos_p * dx + sin_p * dy
    y1p = -sin_p * dx + cos_p * dy
    scale = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        factor = -factor
    cxp, cyp = factor * rx * y1p / ry, -factor * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x0 + x1) / 2
    cy = sin_p * cxp + cos_p * cyp + (y0 + y1) / 2
    start = math.atan2((y1p - cyp) / ry, (x1p - cxp) / rx)
    delta = math.atan2((-y1p - cyp) / ry, (-x1p - cxp) / rx) - start
    if sweep and delta < 0:
        delta += 2 * math.pi
    elif not sweep and delta > 0:
        delta -= 2 * math.pi
    steps = max(4, int(abs(delta) / (math.pi / 16)))
    points = []
    for i in range(1, steps + 1):
        t = start + delta * i / steps
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        points.append((cos_p * ex - sin_p * ey + cx, sin_p * ex + cos_p * ey + cy))
    return points


def _flatten(path: str) -> list[list[tuple[float, float]]]:
    """Turn SVG path data into closed polygons."""
    tokens = _TOKEN.findall(path)
    polys: list[list[tuple[float, float]]] = []
    poly: list[tuple[float, float]] = []
    x = y = sx = sy = 0.0
    ctrl: tuple[float, float] | None = None
    cmd = ""
    i = 0

    def num() -> float:
        nonlocal i
        i += 1
        return float(tokens[i - 1])

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        rel = cmd.islower()
        op = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        last_ctrl, ctrl = ctrl, None

        if op == "M":
            if len(poly) > 2:
                polys.append(poly)
            x, y = ox + num(), oy + num()
            sx, sy = x, y
            poly = [(x, y)]
            cmd = "l" if rel else "L"
        elif op == "L":
            x, y = ox + num(), oy + num()
            poly.append((x, y))
        elif op == "H":
            x = ox + num()
            poly.append((x, y))
        elif op == "V":
            y = (y if rel else 0.0) + num()
            poly.append((x, y))
        elif op in "CS":
            if op == "C":
                c1 = (ox + num(), oy + num())
            else:
                c1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl else (x, y)
            c2 = (ox + num(), oy + num())
            end = (ox + num(), oy + num())
            for k in range(1, 9):
                t = k / 8
                u = 1 - t
                poly.append((u**3 * x + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * end[0],
                             u**3 * y + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * end[1]))
            ctrl = c2
            x, y = end
        elif op in "QT":
            if op == "Q":
                c = (ox + num(), oy + num())
            else:
                c = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl else (x, y)
            end = (ox + num(), oy + num())
            for k in range(1, 7):
                t = k / 6
                u = 1 - t
                poly.append((u * u * x + 2 * u * t * c[0] + t * t * end[0],
                             u * u * y + 2 * u * t * c[1] + t * t * end[1]))
            ctrl = c
            x, y = end
        elif op == "A":
            rx, ry, angle = num(), num(), num()
            large, sweep = num() != 0, num() != 0
            end = (ox + num(), oy + num())
            poly.extend(_arc(x, y, rx, ry, angle, large, sweep, *end))
            x, y = end
        elif op == "Z":
            if len(poly) > 2:
                polys.append(poly)
            x, y = sx, sy
            poly = [(x, y)]
        else:
            raise ValueError(f"unsupported path command {cmd!r}")
    if len(poly) > 2:
        polys.append(poly)
    return polys


def _coverage(name: str, size: int, samples: int = 4) -> list[list[float]]:
    """Anti-aliased non-zero fill of the icon: vertical supersampling, exact horizontal spans."""
    key = (name, size)
    if key in _coverage_cache:
        return _coverage_cache[key]
    scale = size / 256
    edges = []
    for poly in _flatten(PATHS[name]):
        for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
            if ay != by:
                edges.append((ax * scale, ay * scale, bx * scale, by * scale))
    grid = [[0.0] * size for _ in range(size)]
    for row in range(size * samples):
        y = (row + 0.5) / samples
        crossings = []
        for ax, ay, bx, by in edges:
            if (ay <= y < by) or (by <= y < ay):
                crossings.append((ax + (y - ay) * (bx - ax) / (by - ay), 1 if by > ay else -1))
        crossings.sort()
        pixels = grid[int(y)]
        winding = 0
        start = 0.0
        for cx, direction in crossings:
            before = winding
            winding += direction
            if before == 0 and winding != 0:
                start = cx
            elif before != 0 and winding == 0:
                for px in range(max(0, int(start)), min(size, math.ceil(cx))):
                    overlap = min(cx, px + 1) - max(start, px)
                    if overlap > 0:
                        pixels[px] += overlap / samples
    _coverage_cache[key] = grid
    return grid


def icon(root: tk.Misc, name: str, size: int, colour: str, gap: int = 0) -> tk.PhotoImage:
    """Return a cached PhotoImage of a Phosphor icon in the given colour.

    gap adds transparent pixels on the right, used as spacing before a text label.
    """
    key = (name, size, colour, gap)
    if key not in _image_cache:
        r, g, b = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
        blank = b"\x00\x00\x00\x00" * gap
        rows = [b"".join(bytes((r, g, b, round(min(1.0, c) * 255))) for c in line) + blank
                for line in _coverage(name, size)]
        _image_cache[key] = rgba_image(root, size + gap, size, rows)
    return _image_cache[key]


def badge(root: tk.Misc, name: str, size: int, glyph_size: int,
          fill: str, colour: str) -> tk.PhotoImage:
    """Icon centred on a filled circle, as used by the toast."""
    key = (name, size, glyph_size, fill, colour)
    if key in _badge_cache:
        return _badge_cache[key]
    glyph = _coverage(name, glyph_size)
    offset = (size - glyph_size) // 2
    fr, fg, fb = int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16)
    cr, cg, cb = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
    radius = size / 2
    samples = [(i + 0.5) / 4 for i in range(4)]
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            inside = sum((x + sx - radius) ** 2 + (y + sy - radius) ** 2 <= radius * radius
                         for sx in samples for sy in samples) / 16
            gy, gx = y - offset, x - offset
            g = min(1.0, glyph[gy][gx]) if 0 <= gy < glyph_size and 0 <= gx < glyph_size else 0.0
            row += bytes((round(fr + (cr - fr) * g), round(fg + (cg - fg) * g),
                          round(fb + (cb - fb) * g), round(inside * 255)))
        rows.append(bytes(row))
    _badge_cache[key] = rgba_image(root, size, size, rows)
    return _badge_cache[key]
