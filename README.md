# Simple Organizer

Safe, automatic file organisation for Linux and Windows — with sub-categories, a rules engine, multi-level undo, auto-scheduling, duplicate detection, and a built-in duplicate deleter. No data loss. No internet. No background services.

**GitHub:** https://github.com/FreakySneaky787/Simple-Organizer

---

## Table of Contents

- [What's New in v3.4.4](#whats-new-in-v344)
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

## What's New in v3.4.4

### Bug-Fix Release

v3.4.4 fixes all 23 issues from the third review (#29 – #51). The most important ones could leave stray copies of files behind, mix up the undo history, or move files that should stay where they are. Updating is recommended for everyone.

**Never lose track of a file**

- **Moves across drives left orphaned copies** (#29) — when a file was copied to another drive (e.g. into the staging area) but the original could not be deleted because it was open, the copy stayed behind, unknown to Commit, Revert and Undo. Now the copy is removed again and the error is reported; a copy also never overwrites an existing file.
- **Two running instances overwrote each other's staging and history** (#30) — Simple Organizer now runs only once. Starting it again brings the open window to the front.
- **Commit / Revert recreated a renamed or deleted folder** (#35) — if the scanned folder no longer exists, the files stay staged with a clear error instead of a resurrected folder tree.
- **A category folder that is a link moved files out of the folder** (#43) — if e.g. `Images` is a junction or symlink to another place, those files are not planned and the scan says why.
- **Shortcuts were moved and disappeared from the Desktop** (#41) — `.lnk`, `.url`, `.desktop` and `.webloc` files are never moved.

**Undo history**

- **Scheduled runs pushed manual runs out of the history** (#31) — manual and automatic runs are now limited separately (20 each), and History marks automatic runs.
- **"Undo last" depended on the system clock** (#45) — runs are numbered, so a wrong or jumping clock (e.g. dual boot) can no longer reorder them.
- **Undo could not follow a file after the newer run was trimmed** (#38) — runs dropped from the undo list are kept for a while (`history/trimmed/`), so undo still finds the file.
- **Undo from History started without asking** (#32) — it now asks for confirmation, like Undo last.

**OneDrive & cloud files**

- **Staging mode downloaded online-only files** (#33) — moving them out of the OneDrive folder into the staging area would download them; they now stay where they are, with a note in the log.

**Errors are visible**

- **Errors in the exe vanished silently** (#42) — unexpected errors are now shown as a notification, written to the log and to `error.log` in the data folder.
- **The trash confirmation could hide behind the window** (#46) — Windows' Recycle Bin dialogs now open above Simple Organizer.
- **Dialogs could end up behind the main window** (#34) — dialogs and notifications are now owned by the main window and always stay above it.

**Sorting**

- **New categories and file types** (#47) — iPhone photos (`.heic`, `.heif`), `.avif`, `.jxl`; e-books and e-mails (`.epub`, `.mobi`, `.eml`, `.msg`); Office macro files (`.docm`, `.xlsm`, `.pptm`); a new **Programs** category (`.exe`, `.msi`, `.dmg`, `.pkg`, `.apk`, `.appimage`, `.deb`, `.rpm`, `.flatpakref`) and **Disk Images** (`.iso`, `.img`).
- **`.ts` videos were sorted as TypeScript** (#44) — MPEG transport stream videos are detected by their content and go to `Videos/TS` (also `.m2ts`, `.mts`).
- **A file named like a category folder** (#37) — e.g. a file called `Documents` no longer causes one error per PDF; the scan reports the conflict once.
- **Hard links were reported as duplicates** (#40) — several links to the same file are counted once.

**Smaller fixes**

- **Auto-organize ran silently into a missing folder** (#48) — the card shows "Paused: the folder was not found" and a notification appears once.
- **Ctrl+Z in a number field opened Undo** (#36) — it no longer does.
- **Settings write failures flooded the log** (#49) — reported once.
- **A damaged `rules.json` could be overwritten** (#50) — if it cannot be backed up, the Rules tab refuses to save instead.
- **Window position on Linux/X11** (#39) — only Windows restores the window position; on Linux the window manager places the window, so it no longer creeps down on every start.
- **Dead code removed** (#51).

No new dependencies — still Python standard library only.

### Previously in v3.4.3 — Bug-Fix Release

- The folder that contains the exe is organised again (only the exe is skipped)
- Online-only OneDrive files are not downloaded by the duplicate check
- Large scans fill Preview and Duplicates in slices; the log keeps 5 000 lines
- Undo follows files that a newer run moved again; confirmed unusual folders are remembered
- Window size, position and maximised state are remembered; Linux per-volume trash and XDG directories

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

### Latest — v3.4.4

| Platform | File |
|---|---|
| Windows 10/11 | `simple_organizer_windows_v3.4.4.zip` |
| Windows 10/11 | `simple_organizer_windows_v3.4.4.sha256` |
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
- Never moved: system files, shortcuts (`.lnk`, `.url`, `.desktop`, `.webloc`), Office lock files and downloads that are still running
- Category folders that are links pointing outside the scanned folder, or blocked by a file with the same name, are reported instead of used
- Unusual folders (drive root, home, the folder holding all home folders, system/program folders, Git repositories) need confirmation once
- All scan options remembered between sessions

### Default File Categories

| Category | Extensions |
|---|---|
| Images | jpg, jpeg, png, gif, webp, bmp, tiff, heic, heif, avif, jxl, svg, ico, psd, xcf, kra, raw, cr2, nef, arw, dng |
| Documents | pdf, docx, docm, doc, txt, odt, rtf, xlsx, xlsm, xls, ods, pptx, pptm, ppt, odp, pps, ppsx, csv, md, epub, mobi, eml, msg |
| Archives | zip, tar, gz, rar, 7z, bz2, xz, tgz |
| Videos | mp4, mkv, mov, avi, wmv, flv, webm, m4v, mpeg, mpg, m2ts, mts, and `.ts` files that are MPEG transport streams |
| Music | mp3, wav, flac, aac, ogg, wma, m4a, opus, aiff |
| Code | py, ipynb, js, ts (TypeScript), jsx, tsx, html, css, cpp, c, h, java, rb, go, rs, php, sh, bash, json, yaml, toml, xml, sql, swift, kt, dart |
| Programs | exe, msi, dmg, pkg, apk, appimage, deb, rpm, flatpakref |
| Disk Images | iso, img |
| Others | Everything else |

### Sub-Categories (Toggle)

Enable **Use sub-categories** to sort into sub-folders inside each category. Off by default.

```
Images/Photos/        Images/Raw/         Images/Editing/
Documents/PDFs/       Documents/Word/     Documents/Spreadsheets/
Documents/Presentations/                  Documents/Text/
Documents/Ebooks/     Documents/Email/
Music/Lossless/       Music/MP3/          Music/AAC/
Videos/MP4/           Videos/MKV/         Videos/TS/
Archives/ZIP/         Archives/RAR/       Archives/TAR/
Code/Python/          Code/JavaScript/    Code/Web/
Programs/Windows/     Programs/macOS/     Programs/Linux/     Programs/Android/
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

- If the scanned folder was renamed, moved or deleted in the meantime, Commit and Revert leave those files staged with an error instead of recreating the old folder.
- Online-only cloud files (OneDrive …) are not staged, because moving them out of the cloud folder would download them. Organise without staging to sort them.

### Multi-Level Undo

**Undo Last Run** reverses the newest run in History. **History** lists the last 20 manual and the last 20 automatic runs (local time, automatic runs are marked) — undo any specific one after a confirmation.

- Files that cannot be restored stay in the history entry for another try
- Empty category folders created by the run are removed again
- The history is written during the run, so it survives crashes
- Runs can be undone in any order: a file that a newer run moved again is followed and restored to its original place — even when that newer run has already dropped out of the list
- Runs are numbered, so the order never depends on the system clock

### Auto-Organize Scheduler

Fixed-interval automatic organise runs (1–1440 minutes). Stops when the app closes. Never runs as a system service. Runs wait while another task or a dialog is open; slots missed during sleep are skipped.

Unusual folders (drive root, home, `C:\Users` / `/home`, system folders, Git repositories) are only organised automatically after you scanned them once by hand and confirmed. That answer is remembered. Until then — and while the folder cannot be found, e.g. an unplugged drive — the Auto-organize card shows "Paused" and a notification explains why.

### Duplicate Detection + Deletion

Two-stage: size buckets then SHA-256. Empty files, files over 500 MB and online-only cloud files are skipped; several hard links to one file count as one file. Select duplicates in the **Duplicates** tab and move them to Trash with one click. At least one file per group is always kept. Nothing is permanently deleted — files on network drives, which have no Recycle Bin, are left in place. Click anywhere on a group row to expand or collapse it.

### Context Menus

Right-click any row in the Preview or Duplicates tab to open the folder or copy the path to the clipboard.

### Drag and Drop (optional)

Drop a folder (or a file, to use its folder) on the path field. Needs `tkinterdnd2` — see [Known Limitations](#known-limitations).

### Error Reports

Unexpected errors are shown as a notification and written to the log and to `error.log` in the data folder (see [Where Data Is Stored](#where-data-is-stored)). Please attach that file when you report a bug.

### Persistent Settings

Remembers last folder, theme, all scan options, staging mode, sub-categories, scheduler state, confirmed unusual folders, and window size, maximised state and (on Windows) position between sessions. If the monitor changed, the window is moved and shrunk to fit. Damaged values fall back to defaults.

---

## Safety Guarantees

| Guarantee | How enforced |
|---|---|
| No permanent deletion | Duplicates go to system Trash only — never `os.remove()`; drives without a Recycle Bin are refused or warned about |
| No overwrites | `resolve_conflict()` runs before every move; copies across drives never overwrite |
| No stray copies | A move across drives that cannot delete the original removes its copy again |
| One instance | A second start only brings the running window to the front |
| Files stay inside the folder | Rule and category targets checked during every scan, links pointing outside are refused |
| Every move confirmed | Only scheduled runs skip the dialog; auto-mode can't leak into manual scans |
| One task at a time | Buttons and shortcuts blocked while a task runs or a dialog is open |
| Undo record survives crashes | History and staging manifest written during the run, atomically |
| Closing is safe | The window waits for a running task before it closes |
| No link traversal | Symlinks and junctions are never followed |
| No system files | System files, shortcuts, lock files and running downloads are never moved |
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

1. Download and extract `simple_organizer_windows_v3.4.4.zip`
2. Double-click `simple_organizer.exe`
3. If Windows Defender warns: right-click → **Properties** → **Unblock**

Settings, rules and history from older versions are kept and used automatically. Simple Organizer runs only once at a time — starting it again brings the open window to the front.

---

## Verifying Downloads

The `.sha256` file is a checksum of the exe — not the zip archive.

```powershell
# Windows — compare with the hash in simple_organizer_windows_v3.4.4.sha256
Get-FileHash simple_organizer_windows_v3.4.4\simple_organizer.exe -Algorithm SHA256
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
| `Ctrl+Z` | Undo last run (not while typing in a number field) |
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
| Error report | `$XDG_DATA_HOME/simple_organizer/error.log` | `%APPDATA%\simple_organizer\error.log` |

> On Linux `$XDG_CONFIG_HOME` defaults to `~/.config` and `$XDG_DATA_HOME` to `~/.local/share`. If you set them after using v3.4.2 or older, the existing folders in the default locations keep being used so nothing gets lost — move them yourself if you want.
>
> The highest-numbered file in `history/` is the last run; `history/trimmed/` keeps runs that dropped out of the undo list, so undo can still follow files they moved. A `last_run.json` from v3.4.0 or older is migrated automatically.

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
