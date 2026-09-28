# Simple Organizer

Safe, automatic file organisation for Linux and Windows — with sub-categories, a rules engine, multi-level undo, auto-scheduling, duplicate detection, and a built-in duplicate deleter. No data loss. No internet. No background services.

**GitHub:** https://github.com/FreakySneaky787/Simple-Organizer

---

## Table of Contents

- [What's New in v3.4.1](#whats-new-in-v341)
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

## What's New in v3.4.1

### Bug-Fix Release

v3.4.1 fixes every open bug report from v3.4.0. The UI and features are the same as v3.4.0 — this release is about safety and reliability. Updating is recommended for everyone.

**Safety fixes**

- **Scheduled scan could skip confirmation** (#8) — if a scheduled scan failed, the next *manual* scan organised files immediately without the "Confirm Organize" dialog. Auto-mode is now always reset, even when a scan fails.
- **Rules could move files outside the scanned folder** (#9) — a rule target like `C:\Backup`, `/tmp/x` or `..\Other` was accepted. The rule dialog now only accepts sub-folder names, and the scanner double-checks every rule target and ignores unsafe ones with a warning in the log.
- **"Move to Trash" could permanently delete on Windows** (#7) — on drives without a Recycle Bin, Windows deleted files for good. Network drives and UNC paths are now refused (the file is left in place and logged), other drives without a Recycle Bin show a Windows warning first, and a cancelled operation is reported as an error instead of a success.

**Staging fixes**

- **Organising twice before Commit orphaned files** (#5) — the second run overwrote the staging manifest. New staged files are now added to the existing manifest, so Commit and Revert always cover everything in staging. This also fixes staging mode combined with the scheduler.
- **Commit/Revert lost track of failed files** (#6) — the manifest was deleted even when some moves failed. Failed files now stay in the manifest so you can fix the problem and simply press Commit or Revert again.
- **Empty nested staging folders were left behind** (#12) — e.g. `staging/Images/Photos/` with sub-categories on. They are now removed at every level.

**Undo fixes**

- **"Undo Last Run" and History got out of sync** (#11) — each run used to be recorded twice. The newest entry in History is now the one and only "last run", so both always agree. An existing `last_run.json` from older versions is merged into History automatically on first start, and old `undone_*.json` files are cleaned up.

**Other fixes**

- **Empty number field blocked closing and scanning** (#10) — clearing *Max depth*, *Max folders*, *Timeout* or the schedule interval made the ✕ button and Scan do nothing. Empty or invalid fields now fall back to the last saved value.
- **One broken rule wiped all rules** (#12) — invalid entries in `rules.json` are now skipped one by one. An unreadable `rules.json` is backed up to `rules.json.bak` instead of being overwritten.
- **Rule save errors were silent** (#12) — if rules cannot be written, the app now shows a warning.
- **Trash count included skipped files** (#12) — the "moved to Trash" message now only counts files that were actually trashed.
- **Duplicates tab kept stale paths after organising** (#12) — it is now cleared once files have moved. Re-scan to see updated results.
- **Version label showed v3.3.1** (#13) — title bar and header now show the correct version.

No new dependencies — still Python standard library only.

### Previously in v3.4.0 — UI Refresh

- Folder bar on top, options in a sidebar, tabbed workspace, status bar
- Dark and light themes with rounded controls, drawn at runtime — no image files shipped
- Native-looking title bar theming on Windows 10/11
- Phosphor icons throughout (MIT-licensed, bundled as path data)
- In-app dialogs and toast notifications
- −/+ number steppers, timestamped colour-coded log
- Click a rule's status dot to toggle it; click anywhere on a duplicate group row to expand/collapse it

> **Note:** On Linux, dialog and toast corners render square instead of rounded — window transparency (used for rounded corners) is Windows-only.

---

## Downloads

### Latest — v3.4.1

| Platform | File |
|---|---|
| Linux x86-64 | `simple_organizer_linux_v3.4.1.tar.gz` |
| Linux x86-64 | `simple_organizer_linux_v3.4.1.sha256` |
| Windows 10/11 | `simple_organizer_windows_v3.4.1.zip` |
| Windows 10/11 | `simple_organizer_windows_v3.4.1.sha256` |

→ [GitHub Releases](https://github.com/FreakySneaky787/Simple-Organizer/releases)
→ [Codeberg Releases](https://codeberg.org/Simple-Project/Simple-Organizer/releases)

> **Note:** The `.sha256` file is a checksum of the binary or exe directly — not of the tar/zip archive.

---

## Features

### Scanning

| Parameter | Default | Description |
|---|---|---|
| Max depth | 5 | Directory levels to descend |
| Max dirs | 10,000 | Max folders before scan aborts |
| Timeout | 30 s | Wall-clock time limit |

- Symbolic links are never followed
- `/proc` and `/sys` unconditionally excluded on Linux
- App directory excluded from all scans and duplicate detection
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

| Condition | Example | Matches |
|---|---|---|
| Extension | `pdf` | Files with that extension |
| Filename pattern | `*.log` | Wildcard match on filename |
| Min size (MB) | `100` | Files larger than 100 MB |
| Max size (MB) | `10` | Files smaller than 10 MB |
| Older than (days) | `365` | Not modified in over a year |
| Newer than (days) | `7` | Modified in the last week |

- Click a rule's status dot in the list to toggle it on or off.
- The target folder is always a sub-folder of the scanned folder (e.g. `Invoices` or `Work/Reports`). Absolute paths, drive letters and `..` are rejected.

### Staging Mode

Files move to a temporary area first. Inspect, then **Commit** or **Revert**.

- Linux: `~/.local/share/simple_organizer/staging/`
- Windows: `%APPDATA%\simple_organizer\staging\`

Organising several times before committing is fine — every batch is added to the staging area. If some files fail to commit or revert, they stay staged so you can retry.

### Multi-Level Undo

**Undo Last Run** reverses the newest run in History. **History** lists the last 20 runs — undo any specific one. Both always show the same state.

### Auto-Organize Scheduler

Fixed-interval automatic organise runs (1–1440 minutes). Stops when the app closes. Never runs as a system service.

### Duplicate Detection + Deletion

Two-stage: size buckets then SHA-256. Files over 500 MB skipped. Select duplicates in the **Duplicates** tab and move them to Trash with one click. At least one file per group is always kept. Nothing is permanently deleted — files on network drives, which have no Recycle Bin, are left in place. Click anywhere on a group row to expand or collapse it.

### Context Menus

Right-click any row in the Preview or Duplicates tab to open the folder or copy the path to the clipboard.

### Persistent Settings

Remembers last folder, theme, all scan options, staging mode, sub-categories, scheduler state, and window size between sessions.

### Self-Protection

The app detects its own location at startup and excludes its own files from all scans, planning, and duplicate detection at three independent layers.

---

## Safety Guarantees

| Guarantee | How enforced |
|---|---|
| No permanent deletion | Duplicates go to system Trash only — never `os.remove()`; drives without a Recycle Bin are refused or warned about |
| No overwrites | `resolve_conflict()` runs before every move |
| Files stay inside the folder | Rule targets validated in the dialog and again during every scan |
| Every move confirmed | Only scheduled runs skip the dialog; auto-mode can't leak into manual scans |
| No symlink traversal | `is_symlink()` checked before processing |
| No system dirs | `/proc` and `/sys` hard-excluded on Linux |
| Bounded scans | Hard limits on depth, dir count, and time |
| Thread safety | All file ops in daemon threads via `queue.Queue` |
| Self-protection | App directory excluded at three independent layers |
| Group integrity | Cannot trash all files in a duplicate group |
| Recoverable staging | Failed commit/revert entries stay in the manifest |

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
tar -xzf simple_organizer_linux_v3.4.1.tar.gz
cd simple_organizer_linux_v3.4.1
chmod +x simple_organizer
./simple_organizer
```

### Windows

1. Download and extract `simple_organizer_windows_v3.4.1.zip`
2. Double-click `simple_organizer.exe`
3. If Windows Defender warns: right-click → **Properties** → **Unblock**

---

## Verifying Downloads

The `.sha256` file is a checksum of the binary — not the archive.

```bash
# Linux — verify after extracting
tar -xzf simple_organizer_linux_v3.4.1.tar.gz
cd simple_organizer_linux_v3.4.1
sha256sum -c ../simple_organizer_linux_v3.4.1.sha256
```

```powershell
# Windows — compare with the hash in simple_organizer_windows_v3.4.1.sha256
Get-FileHash simple_organizer_windows_v3.4.1\simple_organizer.exe -Algorithm SHA256
```

---

## Usage

### Basic Workflow

1. **Launch** — last folder pre-selected automatically
2. **Browse** to choose a folder
3. Set scan options
4. **Scan** (`Ctrl+R`) — Preview tab shows planned moves with file count
5. Review Preview; right-click rows for folder/path actions
6. **Organize** (`Ctrl+O`) — confirms total count and size
7. **Undo Last Run** (`Ctrl+Z`) or **History** to reverse if needed

### Using the Duplicate Deleter

1. Run a **Scan**
2. Open the **Duplicates** tab
3. Click file rows to select — `Ctrl+click` for multiple, `Shift+click` for range
4. Click **Move Selected to Trash**
5. Review the confirmation dialog
6. Click **Continue** — files go to Trash/Recycle Bin

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+R` | Scan |
| `Ctrl+O` | Organize |
| `Ctrl+Z` | Undo last run |
| `Ctrl+Q` | Quit |

---

## Where Data Is Stored

| Data | Linux | Windows |
|---|---|---|
| Settings | `~/.config/simple_organizer/settings.json` | `%APPDATA%\simple_organizer\settings.json` |
| Rules | `~/.config/simple_organizer/rules.json` | `%APPDATA%\simple_organizer\rules.json` |
| Undo history (incl. last run) | `~/.local/share/simple_organizer/history/` | `%APPDATA%\simple_organizer\history\` |
| Staging | `~/.local/share/simple_organizer/staging/` | `%APPDATA%\simple_organizer\staging\` |

> Since v3.4.1 there is no separate `last_run.json` — the newest file in `history/` is the last run. An existing `last_run.json` is migrated automatically.

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

Requires Python 3.11+ and Tkinter. No third-party packages.

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

---

## Known Limitations

- Trashing duplicates clears the Duplicates tab — re-scan to see updated results
- Organising also clears the Duplicates tab — re-scan to see updated results
- In recursive mode, files land in the top-level category folder
- Files over 500 MB skipped for duplicate detection
- Duplicates on network drives can't be moved to Trash (no Recycle Bin) — they are left in place
- Drag-and-drop requires the tkdnd Tcl extension (silently disabled if absent)
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
