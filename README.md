# Simple Organizer

> Safe, automatic file organisation for Linux and Windows — with sub-categories,
> a rules engine, multi-level undo, auto-scheduling, and duplicate detection.
> No data loss. No internet. No background services.

**GitHub:** https://github.com/FreakySneaky787/Simple-Organizer
**Codeberg:** https://codeberg.org/Simple-Project/Simple-Organizer

---

## Welcome Back

After a period of false suspension, i found a way to get the Project back to Github.
Releases are now published on **both GitHub and Codeberg** simultaneously.

Thank you to everyone who followed the project on Codeberg during this time.

---

## Table of Contents

- [What's New in v3.2.2](#whats-new-in-v322)
- [Downloads](#downloads)
- [Features](#features)
- [Safety Guarantees](#safety-guarantees)
- [Platform Support](#platform-support)
- [Installation](#installation)
- [Verifying Downloads](#verifying-downloads)
- [Usage](#usage)
- [Where Data Is Stored](#where-data-is-stored)
- [Adding to Your App Menu — Linux](#adding-to-your-app-menu--linux)
- [Developer Mode](#developer-mode-run-from-source)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [License](#license)

---

## What's New in v3.2.2

### Bug Fixes

**Window icon disappearing during runtime** — `main.py` · Medium
The window icon was stored as a local variable inside `__init__`. Python's
garbage collector could destroy the `PhotoImage` object after startup,
removing the icon from the title bar mid-session. Fixed: stored as
`self._icon` to keep it alive for the lifetime of the window.

**History write errors invisible to user** — `organizer.py` · Medium
`_write_history_run()` caught all exceptions silently. A full disk or
permission error during history writing gave no feedback. Fixed: errors
now surface via `log_callback` and appear in the Log tab.

**Settings save failures invisible** — `config.py` · Low–Medium
`save_settings()` always returned `None` regardless of success or failure.
A failed write went completely unnoticed. Fixed: now returns `bool`. If
saving fails, a warning appears in the Log tab immediately.

**Rule numeric values not validated** — `main.py` · Low–Medium
Entering `abc` for a numeric condition like `min_size_mb` saved without
error and silently never matched any file. Fixed: the Add Rule dialog now
validates numeric fields and shows a clear error message for invalid input.

**Undo rename timestamp collision** — `organizer.py` · Low
The `undone_*` history rename used a seconds-only timestamp. Two undo
operations within the same second could target the same filename. Fixed:
microseconds added (`%Y%m%dT%H%M%S_%f`) matching the rest of the history system.

**`import time` inside function body** — `organizer.py` · Low
`import time` was placed inside `_iter_files_recursive()` and executed on
every scan. Moved to the top-level imports where it belongs.

**Dead `entry_fg` key in theme dicts** — `utils.py` · Low
Both `LIGHT_THEME` and `DARK_THEME` defined `entry_fg` which was never
read anywhere in `_apply_ttk_theme`. Removed.

### Dark Mode Overhaul

The dark theme has been completely redesigned based on the **Tokyo Night**
colour palette for a more modern, polished look.

| Element | Before | After |
|---------|--------|-------|
| Background | `#1e1e2e` flat grey-blue | `#1a1b26` deep navy |
| Text | `#cdd6f4` | `#c0caf5` warm lavender |
| Accent | `#89b4fa` | `#7aa2f7` vivid blue |
| Input fields | `#313244` | `#1f2335` distinct dark |
| Log area | `#11111b` | `#0d0e17` near-black |
| Row selection | `#89b4fa` blue on dark | `#2e4479` deep navy |

Additional visual improvements across both themes:
- Section headers and treeview column headings now use the accent colour
- Button hover state uses a computed lighter shade of the accent
- Treeview row height increased from 22 to 24 px for better readability
- Light theme accent updated to a richer blue (`#2563ab`)

---

## Downloads

### Latest — v3.2.2

| Platform | File |
|----------|------|
| Linux x86-64 | `simple_organizer_linux_v3.2.2.tar.gz` |
| Linux x86-64 | `simple_organizer_linux_v3.2.2.sha256` |
| Windows 10/11 | `simple_organizer_windows_v3.2.2.zip` |
| Windows 10/11 | `simple_organizer_windows_v3.2.2.sha256` |

→ [GitHub Releases](Soon)
→ [Codeberg Releases](https://codeberg.org/Simple-Project/Simple-Organizer)

> **Note:** The `.sha256` file contains a checksum of the **binary or exe**
> directly — not of the tar/zip archive.

---

## Features

### Scanning

| Parameter | Default | Description |
|-----------|---------|-------------|
| Max depth | 5 | Directory levels to descend |
| Max dirs | 10,000 | Max folders before scan aborts |
| Timeout | 30 s | Wall-clock time limit |

- Symbolic links are **never** followed
- `/proc` and `/sys` unconditionally excluded on Linux
- App's own directory excluded from all scans and duplicate detection
- All scan options remembered between sessions

### Default File Categories

| Category  | Extensions |
|-----------|------------|
| Images    | jpg, jpeg, png, gif, webp, bmp, tiff, svg, ico, psd, xcf, kra, raw, cr2, nef, arw, dng |
| Documents | pdf, docx, doc, txt, odt, rtf, xlsx, xls, ods, pptx, ppt, odp, pps, ppsx, csv, md |
| Archives  | zip, tar, gz, rar, 7z, bz2, xz, tgz |
| Videos    | mp4, mkv, mov, avi, wmv, flv, webm, m4v, mpeg, mpg |
| Music     | mp3, wav, flac, aac, ogg, wma, m4a, opus, aiff |
| Code      | py, ipynb, js, ts, jsx, tsx, html, css, cpp, c, h, java, rb, go, rs, php, sh, bash, json, yaml, toml, xml, sql, swift, kt, dart |
| Others    | Everything else |

### Sub-Categories (Toggle)

Enable **Use sub-categories** to sort into sub-folders inside each category.
Off by default — existing workflows are completely unaffected.

```
Images/Photos/        Images/Raw/         Images/Editing/
Documents/PDFs/       Documents/Word/     Documents/Spreadsheets/
Documents/Presentations/                  Documents/Text/
Music/Lossless/       Music/MP3/          Music/AAC/
Videos/MP4/           Videos/MKV/
Archives/ZIP/         Archives/RAR/       Archives/TAR/
Code/Python/          Code/JavaScript/    Code/Web/
Code/Shell/           Code/Config/
```

Custom Rules are never affected by this toggle.

### Rules Engine

| Condition | Example | Matches |
|-----------|---------|---------|
| Extension | `pdf` | Files with that extension |
| Filename pattern | `*.log` | Wildcard match on filename |
| Min size (MB) | `100` | Files larger than 100 MB |
| Max size (MB) | `10` | Files smaller than 10 MB |
| Older than (days) | `365` | Not modified in over a year |
| Newer than (days) | `7` | Modified in the last week |

Numeric rule values are now validated on entry — invalid values show an
error dialog instead of silently never matching.

### Staging Mode

Files move to a temporary area first. Inspect, then **Commit** to finalise
or **Revert** to cancel.

- Linux: `~/.local/share/simple_organizer/staging/`
- Windows: `%APPDATA%\simple_organizer\staging\`

### Multi-Level Undo

Every organise operation is logged. **Undo Last Run** reverses the most
recent operation. **History** lists the last 20 runs — undo any specific one.

### Auto-Organize Scheduler

Fixed-interval automatic organise runs from 1 to 1440 minutes. Runs
silently. Stops when the app closes. Never runs as a system service.

### Duplicate Detection

Two-stage: size buckets then SHA-256. Files over 500 MB skipped. Nothing
deleted. App files never included in results.

### Context Menus

Right-click any row in the Preview or Duplicates tab to open the containing
folder or copy the path to the clipboard.

### Persistent Settings

Remembers last folder, theme, all scan options, staging mode, sub-categories,
scheduler state, and window size between sessions. Failed saves now shown in
the Log tab instead of being invisible.

### Self-Protection

The app detects its own location at startup and excludes its own files from
all scans, planning, and duplicate detection at three independent layers.

---

## Safety Guarantees

| Guarantee | How enforced |
|-----------|-------------|
| No deletion | `os.remove()` and `shutil.rmtree()` never called |
| No overwrites | `resolve_conflict()` runs before every single move |
| No symlink traversal | `is_symlink()` checked before processing |
| No system dirs | `/proc` and `/sys` hard-excluded on Linux |
| Bounded scans | Hard limits on depth, dir count, and time |
| Thread safety | All file ops in daemon threads via `queue.Queue` |
| Self-protection | App directory excluded at three independent layers |

---

## Platform Support

| Platform | Format | Tested on |
|----------|--------|-----------|
| Linux x86-64 | `tar.gz` + binary | Bazzite, Fedora 40, Ubuntu 24.04 |
| Windows 10/11 | `.zip` + `.exe` | Windows 10, Windows 11 |
| macOS | Not supported | — |

One codebase. No feature differences between platforms.

---

## Installation

### Linux

```bash
tar -xzf simple_organizer_linux_v3.2.2.tar.gz
cd simple_organizer_linux_v3.2.2
chmod +x simple_organizer
./simple_organizer
```

**Add to application menu (optional):**

```bash
mkdir -p ~/.local/share/applications

cat > ~/.local/share/applications/simple-organizer.desktop << 'DESK'
[Desktop Entry]
Name=Simple Organizer
Comment=Safe file organiser with undo support
Exec="/full/path/to/simple_organizer"
Icon=/full/path/to/icon.png
Terminal=false
Type=Application
Categories=Utility;
DESK

chmod +x ~/.local/share/applications/simple-organizer.desktop
update-desktop-database ~/.local/share/applications
```

> **Bazzite / KDE Plasma:** run `kbuildsycoca6 --noincremental` if the icon
> does not appear after the above.
>
> **GNOME:** wrap the `Exec=` path in quotes if it contains spaces.

### Windows

1. Download and extract `simple_organizer_windows_v3.2.2.zip`
2. Double-click `simple_organizer.exe`
3. If Windows Defender warns: right-click → **Properties** → **Unblock**

---

## Verifying Downloads

The `.sha256` file contains a checksum of the **binary** directly, not the
archive.

**Linux — verify after extracting:**
```bash
tar -xzf simple_organizer_linux_v3.2.2.tar.gz
cd simple_organizer_linux_v3.2.2
sha256sum -c ../simple_organizer_linux_v3.2.2.sha256
# Expected: simple_organizer: OK
```

**Windows — verify the exe:**
```powershell
Get-FileHash simple_organizer_windows_v3.2.2\simple_organizer.exe -Algorithm SHA256
# Compare against simple_organizer_windows_v3.2.2.sha256
```

---

## Usage

### Basic Workflow

1. Launch — last folder pre-selected automatically
2. **Browse** to choose a folder
3. Set scan options (recursive, sub-categories, staging mode)
4. **Scan** (`Ctrl+R`) — Preview tab shows planned moves with file count
5. Review Preview; right-click rows for folder/path actions
6. **Organize** (`Ctrl+O`) — confirms total count and size
7. **Undo Last Run** (`Ctrl+Z`) or **History** to reverse if needed

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+R` | Scan |
| `Ctrl+O` | Organize |
| `Ctrl+Z` | Undo last run |
| `Ctrl+Q` | Quit |

---

## Where Data Is Stored

| Data | Linux | Windows |
|------|-------|---------|
| Settings | `~/.config/simple_organizer/settings.json` | `%APPDATA%\simple_organizer\settings.json` |
| Rules | `~/.config/simple_organizer/rules.json` | `%APPDATA%\simple_organizer\rules.json` |
| Last run | `~/.local/share/simple_organizer/last_run.json` | `%APPDATA%\simple_organizer\last_run.json` |
| Undo history | `~/.local/share/simple_organizer/history/` | `%APPDATA%\simple_organizer\history\` |
| Staging | `~/.local/share/simple_organizer/staging/` | `%APPDATA%\simple_organizer\staging\` |

---

## Adding to Your App Menu — Linux

```bash
# Find your binary path
find ~/ -name "simple_organizer" -type f 2>/dev/null
```

Then create the desktop entry with the full path. See the Installation
section above for the full command.

---

## Developer Mode (Run from Source)

Requires Python 3.11+ and Tkinter. No third-party packages.

```bash
# Fedora / Bazzite
sudo dnf install python3-tkinter

# Debian / Ubuntu
sudo apt install python3-tk

git clone https://github.com/SchnekayOpen/Simple-Organizer.git
cd Simple-Organizer
python3 main.py
```

**Build a standalone binary:**

```bash
python3 -m venv .venv
source .venv/bin/activate         # Linux
# .venv\Scripts\activate          # Windows

pip install pyinstaller

# Linux
pyinstaller --onefile --windowed --name simple_organizer \
    --add-data "icon.png:." main.py

# Windows
pyinstaller --onefile --windowed --name simple_organizer ^
    --add-data "icon.png;." --icon icon.ico main.py
```

---

## Known Limitations

- Only direct organise runs appear in the History dialog — staging commits
  recorded as a single last_run entry
- In recursive mode, files land in the top-level category folder — original
  subfolder structure not preserved
- Files over 500 MB skipped for duplicate detection
- Drag-and-drop requires the `tkdnd` Tcl extension (silently disabled if absent)
- Network drives untested
- macOS not supported

---

## Roadmap

- Exclusion list editor in the UI
- Filter / search bar in the Preview tab
- CSV / HTML export of scan results
- Watch mode — live folder monitoring
- Flatpak / AppImage packaging for Linux
- Code-signed Windows executable
- Automated test suite with pytest
- GitHub Actions CI with per-platform builds

---

## License

MIT License

Copyright (c) 2026 Aaron Veider

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
