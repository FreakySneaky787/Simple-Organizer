# Simple Organizer

Safe, automatic file organisation for Linux and Windows — with sub-categories, a rules engine, multi-level undo, auto-scheduling, duplicate detection, and a built-in duplicate deleter. No data loss. No internet. No background services.

**GitHub:** https://github.com/FreakySneaky787/Simple-Organizer

---

## Table of Contents

- [What's New in v3.4.2](#whats-new-in-v342)
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

## What's New in v3.4.2

### Safety & Reliability Release

v3.4.2 is the result of a full code review of v3.4.1. The UI looks the same — this release closes every bug found in that review, several of which could move the wrong files or lose undo records. Updating is recommended for everyone.

**Data safety**

- **Closing the app during a task lost the undo record** — the worker thread was killed mid-run and the history was only written at the end. Closing now waits until the running task has finished.
- **Crash or power cut left no undo record** — the history (and the staging manifest) is now written every 2 seconds while files are moving, and every settings, rules, history and manifest file is written atomically (never half-written).
- **Undo threw away files it could not restore** — a run was marked "undone" even when some files failed (e.g. locked). Failed files now stay in the history entry, so you can fix the cause and undo the same run again.
- **A briefly locked `rules.json` deleted your rules** — any read error (sync client, virus scanner) was treated like a corrupt file and the rules were moved away. Read errors now stop the scan with a message instead; only real JSON corruption is backed up, to `rules_corrupt_<time>.json`, without overwriting older backups.
- **The app could organise its own data** — the settings, history and staging folders are now protected like the program folder.

**Never move what shouldn't be moved**

- **System files were moved on Windows** — `desktop.ini`, `Thumbs.db` and files with the Windows *System* attribute are never touched now. "Include hidden files" also respects the Windows *Hidden* attribute, not only dot-files.
- **Running downloads could be moved** — `.crdownload`, `.part`, `.tmp` and similar files, and Office lock files (`~$…`), are left alone.
- **Git repositories inside a recursive scan were taken apart** — sub-folders that are Git repositories are now skipped as a whole.
- **Warning for unusual folders** — scanning a drive root, your home folder, a system/program folder or a Git repository asks for confirmation first. Scheduled runs skip such folders unless you confirmed them in the current session.
- **Windows junctions were followed** — they are now treated like symlinks and never followed, so files are not found twice.

**Concurrency fixes**

- **Two tasks could run at once** — keyboard shortcuts and several buttons (Undo, History, Commit, Revert, Organize, Trash) still worked while another task was moving files. Everything is now blocked while a task runs or a dialog is open.
- **Scheduled run could overrun a confirmation dialog** — a run that comes due while a dialog or another task is open now waits until it is finished. Organize also re-checks after confirming that the scan was not replaced in the meantime.
- **Scheduler could end up with two timers** — and after standby it fired once per missed slot. Now there is always exactly one timer, and missed slots are skipped.

**Scanning fixes**

- **Folders named like categories were skipped everywhere** — a folder such as `Projects/Images`, `Code/Python` or one called `proc`/`sys` was silently ignored in recursive scans. Category folders are now only skipped directly inside the scanned folder.
- **Organise after "Move to Trash" tried to move trashed files** — trashed files are now removed from the preview and the plan; remaining duplicate groups stay visible.
- **Empty files were reported as duplicates** — they are ignored now (trashing empty `__init__.py` files would break projects).
- **Large scans froze the window** — progress updates are throttled and event handling has a time budget.
- **Duplicate check had no time limit** — it now stops after a generous limit and says so in the log; files over 500 MB that were skipped are reported too.

**Rules**

- **Multi-part extensions never matched** — an extension rule like `tar.gz` now works.
- **Invalid target folders failed file by file** — names with `< > : " | ? *`, reserved names like `CON`/`NUL` and trailing dots or spaces are rejected in the dialog and ignored with a warning during scans.
- `inf`/`nan` are no longer accepted as size or age values.

**Usability**

- **Number fields** are clamped to their allowed range; an empty field falls back to the last valid value; −/+ snap to sensible steps (1 → 15 → 30 …); the mouse wheel only changes a focused field; leaving the schedule field no longer restarts the timer.
- **History shows local time** instead of UTC.
- **Undo removes empty category folders** that the undone run had created.
- **Drag-and-drop actually works** when `tkinterdnd2` is installed; without it, the tooltip no longer promises it.
- **Window icon** is drawn automatically when `icon.png` is missing.
- **Damaged settings** (`"max_depth": "x"`, `"dark_mode": "false"`) no longer crash the start — wrong values fall back to defaults.
- Fewer log lines: depth limits and skipped repositories are summarised; `[SCHEDULE ERROR]` lines are coloured.

**Linux**

- Dialogs no longer crash with "grab failed: window not viewable" on slow X11 setups.
- The built-in Trash fallback now follows the freedesktop.org spec (percent-encoded paths, info file created first), so file managers can restore files with spaces or umlauts.

No new dependencies — still Python standard library only.

### Previously in v3.4.1 — Bug-Fix Release

- Scheduled scans could skip the confirmation dialog for the next manual scan
- Rules could move files outside the scanned folder
- "Move to Trash" could permanently delete on drives without a Recycle Bin
- Staging: organising twice before Commit orphaned files; failed Commit/Revert entries were lost
- "Undo Last Run" and History are now always in sync

### Previously in v3.4.0 — UI Refresh

- Folder bar on top, options in a sidebar, tabbed workspace, status bar
- Dark and light themes with rounded controls, drawn at runtime — no image files shipped
- Phosphor icons, in-app dialogs and toast notifications, −/+ number steppers, colour-coded log

> **Note:** On Linux, dialog and toast corners render square instead of rounded — window transparency (used for rounded corners) is Windows-only.

---

## Downloads

### Latest — v3.4.2

| Platform | File |
|---|---|
| Linux x86-64 | `simple_organizer_linux_v3.4.2.tar.gz` |
| Linux x86-64 | `simple_organizer_linux_v3.4.2.sha256` |
| Windows 10/11 | `simple_organizer_windows_v3.4.2.zip` |
| Windows 10/11 | `simple_organizer_windows_v3.4.2.sha256` |

→ [GitHub Releases](https://github.com/FreakySneaky787/Simple-Organizer/releases)

> **Note:** The `.sha256` file is a checksum of the binary or exe directly — not of the tar/zip archive.

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
- Program, settings, history and staging folders are never organised
- Category folders (`Images`, `Documents`, …) are only skipped directly inside the scanned folder
- Git repositories inside a recursive scan are left alone as a whole
- Never moved: system files, Office lock files and downloads that are still running
- Unusual folders (drive root, home, system/program folders, Git repositories) need confirmation
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

### Auto-Organize Scheduler

Fixed-interval automatic organise runs (1–1440 minutes). Stops when the app closes. Never runs as a system service. Runs wait while another task or a dialog is open; slots missed during sleep are skipped.

### Duplicate Detection + Deletion

Two-stage: size buckets then SHA-256. Empty files and files over 500 MB are skipped. Select duplicates in the **Duplicates** tab and move them to Trash with one click. At least one file per group is always kept. Nothing is permanently deleted — files on network drives, which have no Recycle Bin, are left in place. Click anywhere on a group row to expand or collapse it.

### Context Menus

Right-click any row in the Preview or Duplicates tab to open the folder or copy the path to the clipboard.

### Drag and Drop (optional)

Drop a folder (or a file, to use its folder) on the path field. Needs `tkinterdnd2` — see [Known Limitations](#known-limitations).

### Persistent Settings

Remembers last folder, theme, all scan options, staging mode, sub-categories, scheduler state, and window size between sessions. Damaged values fall back to defaults.

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
| Self-protection | Program, settings, history and staging folders are never organised |
| Group integrity | Cannot trash all files in a duplicate group |
| Recoverable staging & undo | Failed entries stay in the manifest / history for another try |

---

## Platform Support

| Platform | Format | Tested on |
|---|---|---|
| Linux x86-64 | tar.gz + binary | Bazzite, Fedora 40, Ubuntu 24.04 |
| Windows 10/11 | .zip + .exe | Windows 10, Windows 11 |
| macOS | Not supported | — |

---

## Installation

### Linux

```bash
tar -xzf simple_organizer_linux_v3.4.2.tar.gz
cd simple_organizer_linux_v3.4.2
chmod +x simple_organizer
./simple_organizer
```

### Windows

1. Download and extract `simple_organizer_windows_v3.4.2.zip`
2. Double-click `simple_organizer.exe`
3. If Windows Defender warns: right-click → **Properties** → **Unblock**

Settings, rules and history from older versions are kept and used automatically.

---

## Verifying Downloads

The `.sha256` file is a checksum of the binary — not the archive.

```bash
# Linux — verify after extracting
tar -xzf simple_organizer_linux_v3.4.2.tar.gz
cd simple_organizer_linux_v3.4.2
sha256sum -c ../simple_organizer_linux_v3.4.2.sha256
```

```powershell
# Windows — compare with the hash in simple_organizer_windows_v3.4.2.sha256
Get-FileHash simple_organizer_windows_v3.4.2\simple_organizer.exe -Algorithm SHA256
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
| Settings | `~/.config/simple_organizer/settings.json` | `%APPDATA%\simple_organizer\settings.json` |
| Rules | `~/.config/simple_organizer/rules.json` | `%APPDATA%\simple_organizer\rules.json` |
| Undo history | `~/.local/share/simple_organizer/history/` | `%APPDATA%\simple_organizer\history\` |
| Staging | `~/.local/share/simple_organizer/staging/` | `%APPDATA%\simple_organizer\staging\` |

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

If `icon.png` is not available, leave out `--add-data` — the app draws its own window icon.

---

## Known Limitations

- Organising, Undo and Revert clear the Preview and Duplicates tabs — re-scan to see updated results
- In recursive mode, files land in the top-level category folder
- Files over 500 MB and empty files are skipped for duplicate detection
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
