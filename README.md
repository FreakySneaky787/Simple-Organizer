# Simple Organizer

> Safe, automatic file organisation for Linux and Windows — with sub-categories,
> a rules engine, multi-level undo, auto-scheduling, duplicate detection,
> and now a built-in duplicate deleter.
> No data loss. No internet. No background services.

**GitHub:** https://github.com/SchnekayOpen/Simple-Organizer
**Codeberg:** https://codeberg.org/Simple-Project/Simple-Organizer

---

## Table of Contents

- [What's New in v3.3.1](#whats-new-in-v331)
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

## What's New in v3.3.1

### Duplicate Deleter

The biggest new feature since the rules engine. The Duplicates tab now lets
you act on duplicates — not just view them.

After a scan, select any duplicate file rows using click, Ctrl+click, or
Shift+click. Then click **Move Selected to Trash** to send them to the
system Trash or Recycle Bin.

**How it works:**
- Multi-select is fully supported — click, Ctrl+click, Shift+click
- A live label shows how many files are selected
- The **Move to Trash** button is disabled until you make a valid selection
- A confirmation dialog shows exactly which files will be moved before
  anything happens
- Every trashed file is logged in the Log tab

**Safety rules — always enforced:**
- At least one file per duplicate group must remain — you can never
  trash an entire group accidentally. The button stays disabled and shows
  `"keep at least 1 per group"` if the selection is invalid.
- Files go to the **system Trash / Recycle Bin** only — nothing is ever
  permanently deleted
- App files are excluded from duplicate results entirely

**Cross-platform implementation — no external packages:**

| Platform | Method |
|----------|--------|
| Windows | `ctypes` → `SHFileOperation` with `FOF_ALLOWUNDO` (native Recycle Bin) |
| Linux | `gio trash` → `trash-put` → manual XDG Trash fallback |

No `send2trash` or any other pip dependency required.

### Bug Fixes

**`save_rules()` silently swallowed write errors** — `rules.py` · Low
`save_rules()` caught all exceptions with `pass`, making a failed rules
write invisible. Fixed: now returns `bool` and the caller logs a warning
in the Log tab if saving fails.

**`_adjust_colour()` only lightened colours** — `main.py` · Low
The hover colour helper always added to RGB channels, making colours
lighter regardless of the theme. In light mode the hover was barely
visible. Fixed: the function now supports negative amounts to darken,
and the light theme hover correctly darkens the accent.

---

## Downloads

### Latest — v3.3.1

| Platform | File |
|----------|------|
| Linux x86-64 | `simple_organizer_linux_v3.3.1.tar.gz` |
| Linux x86-64 | `simple_organizer_linux_v3.3.1.sha256` |
| Windows 10/11 | `simple_organizer_windows_v3.3.1.zip` |
| Windows 10/11 | `simple_organizer_windows_v3.3.1.sha256` |

→ [GitHub Releases](../../releases/tag/v3.3.1)
→ [Codeberg Releases](https://codeberg.org/SchnekayOpen/Simple-Organizer/releases/tag/v3.3.1)

> **Note:** The `.sha256` file is a checksum of the **binary or exe**
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
- App directory excluded from all scans and duplicate detection
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
Off by default.

```
Images/Photos/        Images/Raw/         Images/Editing/
Documents/PDFs/       Documents/Word/     Documents/Spreadsheets/
Documents/Presentations/                  Documents/Text/
Music/Lossless/       Music/MP3/          Music/AAC/
Videos/MP4/           Videos/MKV/
Archives/ZIP/         Archives/RAR/       Archives/TAR/
Code/Python/          Code/JavaScript/    Code/Web/
```

### Rules Engine

| Condition | Example | Matches |
|-----------|---------|---------|
| Extension | `pdf` | Files with that extension |
| Filename pattern | `*.log` | Wildcard match on filename |
| Min size (MB) | `100` | Files larger than 100 MB |
| Max size (MB) | `10` | Files smaller than 10 MB |
| Older than (days) | `365` | Not modified in over a year |
| Newer than (days) | `7` | Modified in the last week |

### Staging Mode

Files move to a temporary area first. Inspect, then **Commit** or **Revert**.

- Linux: `~/.local/share/simple_organizer/staging/`
- Windows: `%APPDATA%\simple_organizer\staging\`

### Multi-Level Undo

**Undo Last Run** reverses the most recent operation. **History** lists the
last 20 runs — undo any specific one.

### Auto-Organize Scheduler

Fixed-interval automatic organise runs (1–1440 minutes). Stops when the
app closes. Never runs as a system service.

### Duplicate Detection + Deletion

Two-stage: size buckets then SHA-256. Files over 500 MB skipped. Select
duplicates in the Duplicates tab and move them to Trash with one click.
At least one file per group is always kept. Nothing is permanently deleted.

### Context Menus

Right-click any row in Preview or Duplicates tab to open the folder or
copy the path to the clipboard.

### Persistent Settings

Remembers last folder, theme, all scan options, staging mode, sub-categories,
scheduler state, and window size between sessions.

### Self-Protection

The app detects its own location at startup and excludes its own files from
all scans, planning, and duplicate detection at three independent layers.

---

## Safety Guarantees

| Guarantee | How enforced |
|-----------|-------------|
| No permanent deletion | Duplicates go to system Trash only — never `os.remove()` |
| No overwrites | `resolve_conflict()` runs before every move |
| No symlink traversal | `is_symlink()` checked before processing |
| No system dirs | `/proc` and `/sys` hard-excluded on Linux |
| Bounded scans | Hard limits on depth, dir count, and time |
| Thread safety | All file ops in daemon threads via `queue.Queue` |
| Self-protection | App directory excluded at three independent layers |
| Group integrity | Cannot trash all files in a duplicate group |

---

## Platform Support

| Platform | Format | Tested on |
|----------|--------|-----------|
| Linux x86-64 | `tar.gz` + binary | Bazzite, Fedora 40, Ubuntu 24.04 |
| Windows 10/11 | `.zip` + `.exe` | Windows 10, Windows 11 |
| macOS | Not supported | — |

---

## Installation

### Linux

```bash
tar -xzf simple_organizer_linux_v3.3.1.tar.gz
cd simple_organizer_linux_v3.3.1
chmod +x simple_organizer
./simple_organizer
```

### Windows

1. Download and extract `simple_organizer_windows_v3.3.1.zip`
2. Double-click `simple_organizer.exe`
3. If Windows Defender warns: right-click → **Properties** → **Unblock**

---

## Verifying Downloads

The `.sha256` file is a checksum of the **binary** — not the archive.

```bash
# Linux — verify after extracting
tar -xzf simple_organizer_linux_v3.3.1.tar.gz
cd simple_organizer_linux_v3.3.1
sha256sum -c ../simple_organizer_linux_v3.3.1.sha256
```

```powershell
# Windows
Get-FileHash simple_organizer_windows_v3.3.1\simple_organizer.exe -Algorithm SHA256
```

---

## Usage

### Basic Workflow

1. Launch — last folder pre-selected automatically
2. **Browse** to choose a folder
3. Set scan options
4. **Scan** (`Ctrl+R`) — Preview tab shows planned moves with file count
5. Review Preview; right-click rows for folder/path actions
6. **Organize** (`Ctrl+O`) — confirms total count and size
7. **Undo Last Run** (`Ctrl+Z`) or **History** to reverse if needed

### Using the Duplicate Deleter

1. Run a **Scan**
2. Open the **Duplicates** tab
3. Click file rows to select — Ctrl+click for multiple, Shift+click for range
4. Click **Move Selected to Trash**
5. Review the confirmation dialog
6. Click **Yes** — files go to Trash/Recycle Bin

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
> does not appear.
>
> **GNOME:** wrap the `Exec=` path in quotes if it contains spaces.

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
py -m PyInstaller --onefile --windowed --name simple_organizer ^
    --add-data "icon.png;." --icon icon.ico main.py
```

---

## Known Limitations

- Trashing duplicates clears the Duplicates tab — re-scan to see updated results
- Only direct organise runs appear in the History dialog
- In recursive mode, files land in the top-level category folder
- Files over 500 MB skipped for duplicate detection
- Drag-and-drop requires the `tkdnd` Tcl extension (silently disabled if absent)
- Network drives untested
- macOS not supported

---

## Roadmap

- Filter / search bar in the Preview tab
- CSV / HTML export of scan results
- Watch mode — live folder monitoring
- Flatpak / AppImage packaging for Linux
- Code-signed Windows executable
- Automated test suite with pytest

---

## License

MIT License — Copyright (c) 2026 SchnekayOpen

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
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
