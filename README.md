# Simple Organizer

Safe, automatic file organisation for Windows and Linux. Simple Organizer sorts the files in a folder — like **Downloads** or the **Desktop** — into category folders such as `Images`, `Documents` and `Videos`.

Nothing is ever deleted or overwritten, and every run can be undone. No internet, no background service, Python standard library only.

**[⬇ Download](https://github.com/FreakySneaky787/Simple-Organizer/releases/latest)** · **[📖 Wiki](https://github.com/FreakySneaky787/Simple-Organizer/wiki)** · **[🐞 Report a bug](https://github.com/FreakySneaky787/Simple-Organizer/issues)**

---

## Features

- **Sorts by file type** into Images, Documents, Archives, Videos, Music, Code, Programs, Disk Images and Others — optionally into sub-folders like `Images/Photos` or `Documents/PDFs` → [Categories](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Categories-and-File-Types)
- **Preview first** — a scan only plans; nothing moves until you press Organize → [Getting Started](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Getting-Started)
- **Multi-level undo** — undo the last run or any of the last 20 manual and 20 automatic runs, in any order → [Undo and History](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Undo-and-History)
- **Rules** — your own sorting by extension, name pattern, size or age → [Rules](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Rules)
- **Staging mode** — stage moves, then Commit or Revert → [Staging Mode](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Staging-Mode)
- **Auto-organize** on a schedule while the app is open → [Auto-Organize](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Auto-Organize)
- **Duplicate finder** — byte-identical files, moved to the Recycle Bin / Trash on request → [Duplicates](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Duplicates)
- **Recursive scans** with limits on depth, folder count and time → [Scanning](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Scanning)
- Light and dark theme, keyboard shortcuts, remembers all settings

## Safe by design

- Files are only **moved** — never deleted, never overwritten (`_1`, `_2` … on name conflicts)
- **System files, shortcuts, temporary files and running downloads** are never moved
- **Online-only cloud files** (OneDrive & co.) are never downloaded
- Drive roots, home and system folders and Git repositories need **confirmation**
- The undo history is written **while** files move, so even a crash leaves an undo record
- Only **one instance** runs at a time; one task at a time

All guarantees: [Safety](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Safety)

---

## Download & Install

### Windows 10 / 11

1. Download `simple_organizer_windows_v3.4.4.zip` from the [latest release](https://github.com/FreakySneaky787/Simple-Organizer/releases/latest)
2. Extract it and double-click `simple_organizer.exe` — no installation needed
3. If SmartScreen warns: right-click → **Properties** → **Unblock** (the exe is not code-signed yet)

The `.sha256` file on the release page is the checksum of the exe:

```powershell
Get-FileHash simple_organizer_windows_v3.4.4\simple_organizer.exe -Algorithm SHA256
```

### Linux

No prebuilt binary on GitHub at the moment — run it from source (Python 3.11+ with Tkinter):

```bash
sudo dnf install python3-tkinter      # Fedora / Bazzite
sudo apt install python3-tk           # Debian / Ubuntu

git clone https://github.com/FreakySneaky787/Simple-Organizer.git
cd Simple-Organizer
python3 main.py
```

App-menu entry, building a binary and more: [Installation](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Installation) · [Building from Source](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Building-from-Source)

macOS is not supported.

---

## Quick Start

1. **Browse…** to the folder you want to organise
2. **Scan** (`Ctrl+R`) — the Preview tab shows every planned move
3. **Organize** (`Ctrl+O`) — confirm, done
4. Changed your mind? **Undo last** (`Ctrl+Z`)

| Shortcut | Action |
|---|---|
| `Ctrl+R` | Scan |
| `Ctrl+O` | Organize |
| `Ctrl+Z` | Undo last run |
| `Ctrl+Q` | Quit (waits for a running task) |

Questions? See the [FAQ and Troubleshooting](https://github.com/FreakySneaky787/Simple-Organizer/wiki/FAQ-and-Troubleshooting).

---

## What's New in v3.4.4

Bug-fix release — fixes all 23 issues from the third review (#29 – #51):

- Moves across drives never leave stray copies; only one instance runs at a time
- Manual and automatic runs are kept separately in the undo history; runs are numbered, so a wrong clock cannot reorder them
- Undo from History asks first and can still follow files moved by older, trimmed runs
- Shortcuts are never moved; category folders that are links pointing elsewhere are refused
- Staging mode does not download OneDrive online-only files; Commit/Revert never recreate a deleted folder
- New file types and the categories **Programs** and **Disk Images**; `.ts` videos are detected by content
- Unexpected errors are shown and written to `error.log`; dialogs always stay above the main window

Full notes: [Release v3.4.4](https://github.com/FreakySneaky787/Simple-Organizer/releases/tag/v3.4.4) · All versions: [Changelog](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Changelog)

---

## Where Data Is Stored

Settings, rules, undo history, staging area and `error.log` live in `%APPDATA%\simple_organizer\` on Windows and in `~/.config/simple_organizer/` and `~/.local/share/simple_organizer/` on Linux (XDG directories are honoured). Details: [Data and Settings](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Data-and-Settings)

When reporting a bug, please attach `error.log` if there is one.

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
