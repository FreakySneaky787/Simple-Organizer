# Simple Organizer

Safe, automatic file organisation for Linux and Windows — with sub-categories, a rules engine, multi-level undo, auto-scheduling, duplicate detection, and a built-in duplicate deleter. No data loss. No internet. No background services.

**GitHub:** https://github.com/FreakySneaky787/Simple-Organizer

---

## Table of Contents

- [What's New in v3.4.3](#whats-new-in-v343)
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

## What's New in v3.4.3

### Bug-Fix Release

v3.4.3 fixes all 15 issues found in a review of v3.4.2 (#14 – #28), including one regression. Updating is recommended — especially if you keep `simple_organizer.exe` inside the folder you organise.

**Safety & data**

- **The folder that contains the exe could not be organised** (#14, regression in v3.4.2) — the whole folder was refused as "belongs to Simple Organizer itself". Now only the exe itself is left alone and the folder is organised normally. The settings, history and staging folders stay fully protected.
- **The duplicate check downloaded OneDrive files** (#15) — "online-only" cloud files (OneDrive, Dropbox, iCloud) were read for hashing, which downloads them. They are now skipped and counted in the log.
- **Undoing runs out of order left files in the wrong place** (#25) — when a newer run had moved a file again, undoing the older run skipped it. Undo now follows the file to where it is and restores it to its original location.
- **Organize stayed enabled with an outdated plan after a crash** (#21) — after a task that moves files fails unexpectedly, the preview is cleared so you scan again first.
- **No warning for `C:\Users` or `/home`** (#23) — the folder that holds all users' home folders now asks for confirmation like other unusual folders.

**Scheduler**

- **Scheduled runs silently stopped after a restart** (#24) — your "scan anyway" answer for an unusual folder is now remembered, also for automatic runs. If a run is paused because a folder still needs that confirmation, the Auto-organize card and a notification say so.
- **The schedule timer restarted after an automatic correction** (#26) — e.g. after an out-of-range interval was corrected.

**Performance**

- **The window froze while showing very large scans** (#16) — Preview and Duplicates are now filled in small slices, so the window stays responsive.
- **The log grew without limit** (#17) — it now keeps the newest 5 000 lines.
- **The UI stuttered after every task** (#18) — button states no longer read every history file.

**Usability**

- **Shortcuts did not work with Caps Lock on** (#22).
- **Window size and position** (#27) — a maximised window no longer overwrites the normal size with the screen size. Position and maximised state are remembered, and the window is moved and shrunk to fit if the monitor changed.

**Linux**

- **Trash on USB sticks and other partitions** (#28) — the built-in Trash fallback now uses the drive's own trash (`.Trash-<uid>`) instead of copying the file into the home folder.
- **`XDG_CONFIG_HOME` and `XDG_DATA_HOME` are honoured** (#28) — an existing folder in the old location keeps being used, so nothing gets lost.

**Project**

- **The README promised a Linux build that does not exist** (#19) — Downloads and Installation now explain how to run Simple Organizer on Linux (from source or self-built).
- **Building from source failed** (#20) — `icon.png` and `icon.ico` are now in the repository.

No new dependencies — still Python standard library only.

### Previously in v3.4.2 — Safety & Reliability Release

- Closing during a task waits for it; history and staging manifest are written during the run and atomically
- Undo keeps files it could not restore; a locked `rules.json` no longer wipes the rules
- System files, Office lock files and running downloads are never moved; Git repositories and junctions are skipped
- Confirmation before organising drive roots, home, system folders or Git repositories
- One task at a time; scheduled runs wait for open dialogs; exactly one scheduler timer
- Multi-part extension rules (`tar.gz`), invalid rule targets rejected, clamped number fields, history in local time

### Previously in v3.4.1 — Bug-Fix Release

- Scheduled scans could skip the confirmation dialog for the next manual scan
- Rules could move files outside the scanned folder
- "Move to Trash" could permanently delete on drives without a Recycle Bin
- Staging: organising twice before Commit orphaned files; failed Commit/Revert entries were lost

### Previously in v3.4.0 — UI Refresh

- Folder bar on top, options in a sidebar, tabbed workspace, status bar
- Dark and light themes with rounded controls, drawn at runtime — no image files shipped
- Phosphor icons, in-app dialogs and toast notifications, −/+ number steppers, colour-coded log

> **Note:** On Linux, dialog and toast corners render square instead of rounded — window transparency (used for rounded corners) is Windows-only.

---

## Downloads

### Latest — v3.4.3

| Platform | File |
|---|---|
| Windows 10/11 | `simple_organizer_windows_v3.4.3.zip` |
| Windows 10/11 | `simple_organizer_windows_v3.4.3.sha256` |
| Linux x86-64 | No prebuilt binary on GitHub — [run it from source](#linux) or [build your own](#developer-mode-run-from-source) |

→ [GitHub Releases](https://github.com/FreakySneaky787/Simple-Organizer/releases)

> **Note:** The `.sha256` file is a checksum of the exe directly — not of the zip archive.

---

## Features

### Scanning

| Parameter | Default | Range | Description |
|---|---|---|---|
| Max depth | 5 | 1–50 | Directory levels to descend |
| Max folders | 10,000 | 100–500,000 | Max folders before the scan stops |
| Timeout | 30 s | 5–300 s | Wall-clock time limit for collecting files |

- Top-level only by default; **Scan subdirectories** for recursive mode
- Symbolic links and Windows junctions are never followed
- `/proc` and `/sys` unconditionally excluded on Linux
- Settings, history and staging folders are never organised; the exe itself is never moved, but the folder it sits in is organised normally
- Online-only cloud files (OneDrive, Dropbox, iCloud) are never downloaded — they are left out of the duplicate check
- Category folders (`Images`, `Documents`, …) are only skipped directly inside the scanned folder
- Git repositories inside a recursive scan are left alone as a whole
- Never moved: system files, Office lock files and downloads that are still running
- Unusual folders (drive root, home, the folder holding all home folders, system/program folders, Git repositories) need confirmation once
- All scan options remembered between sessions

### Default File Categories

| Category | Extensions |
|---|---|
| Images | jpg, jpeg, png, gif, webp, bmp, tiff, svg, ico, psd, xcf, kra, raw, cr2, nef, arw, dng |
| Documents | pdf, docx, doc, txt, odt, rtf, xlsx, xls, ods, pptx, ppt, odp, pps, ppsx, csv, md |
| Archives | zip, tar, gz, rar, 7z, bz2, xz, tgz |
| Videos | mp4, mkv, mov, avi, wmv, flv, webm, m4v, mpeg, mpg |
| Music | mp3, wav, flac, aac, ogg, wma, m4a, opus, aiff |
| Code | py, ipynb, js, ts, jsx, tsx, html, css, cpp, c, h, java, rb, go, rs, php, sh, bash, json, yaml, toml, xml, sql, swift, kt, dart |
| Others | Everything else |

### Sub-Categories (Toggle)

Enable **Use sub-categories** to sort into sub-folders inside each category. Off by default.

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

Rules run before extension-based sorting. The first matching enabled rule wins.

| Condition | Example | Matches |
|---|---|---|
| Extension | `pdf`, `tar.gz` | Files with that extension |
| Filename pattern | `*.log` | Wildcard match on filename |
| Min size (MB) | `100` | Files of at least 100 MB |
| Max size (MB) | `10` | Files of at most 10 MB |
| Older than (days) | `365` | Not modified in over a year |
| Newer than (days) | `7` | Modified in the last week |

- Click a rule's status dot to toggle it; use the arrows to change the order.
- The target folder is always a sub-folder of the scanned folder (e.g. `Invoices` or `Work/Reports`). Absolute paths, drive letters, `..`, the characters `< > : " | ? *`, reserved names like `CON`/`NUL` and trailing dots or spaces are rejected.
- If `rules.json` can't be read right now, scans stop instead of sorting without your rules.

### Staging Mode

Files move to a temporary area first. Inspect, then **Commit** or **Revert**.

- Linux: `~/.local/share/simple_organizer/staging/`
- Windows: `%APPDATA%\simple_organizer\staging\`

Organising several times before committing is fine — every batch is added to the staging area. If some files fail to commit or revert, they stay staged so you can retry.

### Multi-Level Undo

**Undo Last Run** reverses the newest run in History. **History** lists the last 20 runs (local time) — undo any specific one.

- Files that cannot be restored stay in the history entry for another try
- Empty category folders created by the run are removed again
- The history is written during the run, so it survives crashes
- Runs can be undone in any order: a file that a newer run moved again is followed and restored to its original place

### Auto-Organize Scheduler

Fixed-interval automatic organise runs (1–1440 minutes). Stops when the app closes. Never runs as a system service. Runs wait while another task or a dialog is open; slots missed during sleep are skipped.

Unusual folders (drive root, home, `C:\Users` / `/home`, system folders, Git repositories) are only organised automatically after you scanned them once by hand and confirmed. That answer is remembered. Until then the Auto-organize card shows "Paused" and a notification explains why.

### Duplicate Detection + Deletion

Two-stage: size buckets then SHA-256. Empty files, files over 500 MB and online-only cloud files are skipped. Select duplicates in the **Duplicates** tab and move them to Trash with one click. At least one file per group is always kept. Nothing is permanently deleted — files on network drives, which have no Recycle Bin, are left in place. Click anywhere on a group row to expand or collapse it.

### Context Menus

Right-click any row in the Preview or Duplicates tab to open the folder or copy the path to the clipboard.

### Drag and Drop (optional)

Drop a folder (or a file, to use its folder) on the path field. Needs `tkinterdnd2` — see [Known Limitations](#known-limitations).

### Persistent Settings

Remembers last folder, theme, all scan options, staging mode, sub-categories, scheduler state, confirmed unusual folders, and window size, position and maximised state between sessions. If the monitor changed, the window is moved and shrunk to fit. Damaged values fall back to defaults.

---

## Safety Guarantees

| Guarantee | How enforced |
|---|---|
| No permanent deletion | Duplicates go to system Trash only — never `os.remove()`; drives without a Recycle Bin are refused or warned about |
| No overwrites | `resolve_conflict()` runs before every move |
| Files stay inside the folder | Rule targets validated in the dialog and again during every scan |
| Every move confirmed | Only scheduled runs skip the dialog; auto-mode can't leak into manual scans |
| One task at a time | Buttons and shortcuts blocked while a task runs or a dialog is open |
| Undo record survives crashes | History and staging manifest written during the run, atomically |
| Closing is safe | The window waits for a running task before it closes |
| No link traversal | Symlinks and junctions are never followed |
| No system files | System files, lock files and running downloads are never moved |
| No system dirs | `/proc` and `/sys` hard-excluded; system/program folders need confirmation |
| Bounded scans | Hard limits on depth, folder count, and time |
| Self-protection | Settings, history and staging folders are never organised; the exe is never moved |
| No surprise downloads | Online-only cloud files are never read |
| Group integrity | Cannot trash all files in a duplicate group |
| Recoverable staging & undo | Failed entries stay in the manifest / history for another try |

---

## Platform Support

| Platform | Format | Tested on |
|---|---|---|
| Linux x86-64 | From source (Python 3.11+, Tkinter) | Bazzite, Fedora 40, Ubuntu 24.04 |
| Windows 10/11 | .zip + .exe | Windows 10, Windows 11 |
| macOS | Not supported | — |

---

## Installation

### Linux

There is no prebuilt Linux binary on GitHub at the moment. Simple Organizer runs directly from source — it only needs Python 3.11+ with Tkinter:

```bash
# Fedora / Bazzite
sudo dnf install python3-tkinter

# Debian / Ubuntu
sudo apt install python3-tk

git clone https://github.com/FreakySneaky787/Simple-Organizer.git
cd Simple-Organizer
python3 main.py
```

To get a single executable file, build it yourself — see [Developer Mode](#developer-mode-run-from-source).

### Windows

1. Download and extract `simple_organizer_windows_v3.4.3.zip`
2. Double-click `simple_organizer.exe`
3. If Windows Defender warns: right-click → **Properties** → **Unblock**

Settings, rules and history from older versions are kept and used automatically.

---

## Verifying Downloads

The `.sha256` file is a checksum of the exe — not the zip archive.

```powershell
# Windows — compare with the hash in simple_organizer_windows_v3.4.3.sha256
Get-FileHash simple_organizer_windows_v3.4.3\simple_organizer.exe -Algorithm SHA256
```

---

## Usage

### Basic Workflow

1. **Launch** — last folder pre-selected automatically
2. **Browse** (or drop a folder) to choose a folder
3. Set scan options
4. **Scan** (`Ctrl+R`) — Preview tab shows planned moves with file count
5. Review Preview; right-click rows for folder/path actions
6. **Organize** (`Ctrl+O`) — confirms total count and size
7. **Undo Last Run** (`Ctrl+Z`) or **History** to reverse if needed

### Using the Duplicate Deleter

1. Run a **Scan**
2. Open the **Duplicates** tab
3. Click file rows to select — `Ctrl+click` for multiple, `Shift+click` for range
4. Click **Move selected to Trash**
5. Review the confirmation dialog
6. Click **Continue** — files go to Trash/Recycle Bin

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+R` | Scan |
| `Ctrl+O` | Organize |
| `Ctrl+Z` | Undo last run |
| `Ctrl+Q` | Quit (waits for a running task) |

Shortcuts do nothing while a task is running or a dialog is open.

---

## Where Data Is Stored

| Data | Linux | Windows |
|---|---|---|
| Settings | `$XDG_CONFIG_HOME/simple_organizer/settings.json` | `%APPDATA%\simple_organizer\settings.json` |
| Rules | `$XDG_CONFIG_HOME/simple_organizer/rules.json` | `%APPDATA%\simple_organizer\rules.json` |
| Undo history | `$XDG_DATA_HOME/simple_organizer/history/` | `%APPDATA%\simple_organizer\history\` |
| Staging | `$XDG_DATA_HOME/simple_organizer/staging/` | `%APPDATA%\simple_organizer\staging\` |

> On Linux `$XDG_CONFIG_HOME` defaults to `~/.config` and `$XDG_DATA_HOME` to `~/.local/share`. If you set them after using v3.4.2 or older, the existing folders in the default locations keep being used so nothing gets lost — move them yourself if you want.
>
> The newest file in `history/` is the last run. A `last_run.json` from v3.4.0 or older is migrated automatically.

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

**Bazzite / KDE Plasma:** run `kbuildsycoca6 --noincremental` if the icon does not appear.

**GNOME:** wrap the `Exec=` path in quotes if it contains spaces.

---

## Developer Mode (Run from Source)

Requires Python 3.11+ and Tkinter. No third-party packages (`tkinterdnd2` is optional for drag-and-drop).

```bash
# Fedora / Bazzite
sudo dnf install python3-tkinter

# Debian / Ubuntu
sudo apt install python3-tk

git clone https://github.com/FreakySneaky787/Simple-Organizer.git
cd Simple-Organizer
python3 main.py
```

Build a standalone binary:

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

`icon.png` and `icon.ico` are part of the repository. Without them the app still works — it draws its own window icon.

---

## Known Limitations

- Organising, Undo and Revert clear the Preview and Duplicates tabs — re-scan to see updated results
- In recursive mode, files land in the top-level category folder
- Files over 500 MB, empty files and online-only cloud files are skipped for duplicate detection
- No prebuilt Linux binary on GitHub — run from source or build it yourself
- Duplicates on network drives can't be moved to Trash (no Recycle Bin) — they are left in place
- Drag-and-drop needs tkdnd: `pip install tkinterdnd2` (bundles it) or a system Tcl package; without it the feature is off
- macOS not supported
- On Linux, dialog and toast windows have square corners (rounded corners rely on Windows-only transparency)

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

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

### Third-party

Icons are from [Phosphor Icons](https://phosphoricons.com) (MIT License, Copyright (c) 2023 Phosphor Icons). Their path data is bundled in `icons.py`.
