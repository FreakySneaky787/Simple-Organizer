# Simple Organizer

Safe, automatic file organisation for Windows and Linux. Simple Organizer sorts the files in a folder — like **Downloads** or the **Desktop** — into category folders such as `Images`, `Documents` and `Videos`.

Nothing is ever deleted or overwritten, and every run can be undone. No internet, no account, no service running behind your back — the optional tray mode is something you switch on yourself.

**[⬇ Download](https://github.com/FreakySneaky787/Simple-Organizer/releases/latest)** · **[📖 Wiki](https://github.com/FreakySneaky787/Simple-Organizer/wiki)** · **[🐞 Report a bug](https://github.com/FreakySneaky787/Simple-Organizer/issues)**

> **Project status:** Simple Organizer is feature-complete with v3.6.0. Further releases fix bugs only, while I focus on [Simple OS](https://github.com/FreakySneaky787/Simple-OS). Bug reports and pull requests are still very welcome; answers may just take a little longer.

---

## Features

- **Sorts by file type** into Images, Documents, Archives, Videos, Music, Code, Programs, Disk Images and Others — optionally into sub-folders like `Images/Photos` or `Documents/PDFs` → [Categories](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Categories-and-File-Types)
- **Preview first** — a scan only plans; nothing moves until you press Organize. Filter and sort the preview, keep single files with **Don't move**, export it as CSV → [Getting Started](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Getting-Started)
- **Multi-level undo** — undo the last run or any of the last 20 manual and 20 automatic runs, in any order; History shows the folder of every run → [Undo and History](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Undo-and-History)
- **Rules** — your own sorting by extension, name pattern, size or age, with several conditions per rule (e.g. *PDF **and** older than a year*) → [Rules](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Rules)
- **Staging mode** — stage moves, then Commit or Revert → [Staging Mode](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Staging-Mode)
- **Auto-organize** on a schedule — also with the window closed: the app can keep running in the system tray and start at login (Windows and Linux) → [Auto-Organize](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Auto-Organize)
- **Duplicate finder** — byte-identical files, also copies of files you already sorted, moved to the Recycle Bin / Trash on request → [Duplicates](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Duplicates)
- **Recursive scans** with limits on depth, folder count and time; folders left empty are cleaned up (and restored by Undo); a running scan or Organize can be cancelled → [Scanning](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Scanning)
- Light and dark theme, keyboard shortcuts, remembers all settings

## Safe by design

- Files are only **moved** — never deleted, never overwritten (`_1`, `_2` … on name conflicts)
- **System files, shortcuts, temporary files and running downloads** are never moved
- **Online-only cloud files** (OneDrive & co.) are never downloaded
- Drive roots, home and system folders and Git repositories need **confirmation**
- The undo history is written **while** files move, so even a crash leaves an undo record
- Only **one instance** runs at a time; one task at a time
- **Cancel** stops after the current file — what already moved stays undoable

All guarantees: [Safety](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Safety)

---

## Download & Install

### Windows 10 / 11

1. Download `simple_organizer_windows_v3.6.1.zip` from the [latest release](https://github.com/FreakySneaky787/Simple-Organizer/releases/latest)
2. Extract it and double-click `simple_organizer.exe` — no installation needed
3. If SmartScreen warns: right-click → **Properties** → **Unblock** (the exe is not code-signed yet)

The `.sha256` file on the release page is the checksum of the exe:

```powershell
Get-FileHash simple_organizer_windows_v3.6.1\simple_organizer.exe -Algorithm SHA256
```

### Linux

**Debian 12+, Ubuntu, Simple OS:** download `simple-organizer_3.6.1_all.deb` from the [latest release](https://github.com/FreakySneaky787/Simple-Organizer/releases/latest) and install it — it appears in the app menu:

```bash
sudo apt install ./simple-organizer_3.6.1_all.deb
```

**Other distributions** — run it from source (Python 3.10+ with Tkinter):

```bash
sudo dnf install python3-tkinter      # Fedora / Bazzite

git clone https://github.com/FreakySneaky787/Simple-Organizer.git
cd Simple-Organizer
python3 main.py
```

For the tray icon (optional) on Linux: `sudo apt install python3-pystray gir1.2-ayatanaappindicator3-0.1`, or `pip install pystray pillow`. On GNOME the tray needs the *AppIndicator and KStatusNotifierItem Support* extension (preinstalled on Ubuntu). Without a tray, closing the window minimises it instead.

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
| `Ctrl+R` / `F5` | Scan |
| `Ctrl+O` | Organize |
| `Ctrl+Z` | Undo last run |
| `Ctrl+F` | Filter the preview |
| `Ctrl+1` … `Ctrl+4` | Preview, Duplicates, Log, Rules |
| `Space` / `Delete` | Don't move the selected files (Preview) |
| `Ctrl+Q` | Quit — also when the app keeps running in the tray (a running task stops after the current file) |

Questions? See the [FAQ and Troubleshooting](https://github.com/FreakySneaky787/Simple-Organizer/wiki/FAQ-and-Troubleshooting).

---

## What's New in v3.6.1

Bug-fix release — fixes from a code review of v3.6.0, mostly for the background mode (#108 – #114):

- **Linux tray:** the tray menu now works with the AppIndicator and GTK tray (GNOME, Simple OS) — its loop runs on its own thread instead of waiting for a GLib main loop that never ran (#108)
- **Background mode:** while the window is hidden in the tray, messages appear as system notifications; an error no longer opens an invisible dialog that held back every later automatic run — it is shown when you open the window (#109)
- **Quit** with a dialog open no longer makes a later click on the close button quit instead of going to the tray (#110)
- **Cancel:** pressing Cancel during the last file no longer reports a finished run as cancelled, and errors of a cancelled run are reported (#111)
- **Duplicates of sorted files:** equal-sized files that are all already sorted are no longer hashed on every scan (#112)
- **Start at login** is no longer moved to every copy of the app you start; it is only repaired when its program is gone (#114)
- Build steps for the exe install `pystray` and `Pillow` (#113)

Full notes: [Release v3.6.1](https://github.com/FreakySneaky787/Simple-Organizer/releases/tag/v3.6.1)

## What's New in v3.6.0

Feature release — the last one; Simple Organizer is now feature-complete (#87 – #89):

- **Cancel** a running scan or Organize — it stops after the current file; the files moved so far stay in the History and can be undone. Closing the window during a run cancels it too (#89)
- **Emptied folders are removed** after organising subdirectories (`Project/deep/` after moving `Project/deep/r.pdf`). Undo brings them back. Option *Remove emptied folders* in the Scan card, on by default (#87)
- **Duplicates of sorted files** — a new `cv (1).pdf` is now found as a copy of `Documents/cv.pdf` instead of being sorted in as a second copy (#88)
- **Keep running when closed** — the window goes to the system tray (Windows and Linux) and Auto-organize carries on. Tray menu: Open, Organize now, Auto-organize on/off, Quit
- **Start at login** — Windows (per user, no admin rights) and Linux (XDG autostart, e.g. Debian, Ubuntu, Simple OS); starts in the background
- Starting the app a second time brings the hidden window back

Full notes: [Release v3.6.0](https://github.com/FreakySneaky787/Simple-Organizer/releases/tag/v3.6.0)

## What's New in v3.5.3

Bug-fix release (#90, #101, #102, #104, #105):

- **Don't move** is kept per folder: picking the same folder again, or another folder and back, no longer clears it. Entries of deleted files are dropped (#101)
- Automatic runs no longer switch to the Preview and Log tabs, and they skip a run while a manual scan that was not organised yet is shown (#105)
- A file named like the first folder of a nested rule target (`Work` → `Work/Archive`) is no longer left as `Work.organizing` when the move fails, and Undo gives it its own name back (#104)
- Windows: Undo gives a file named like a category folder in another case (`others`) its own name back instead of `others_1` (#102)
- The History shows the year for runs from an earlier year (#90)

Full notes: [Release v3.5.3](https://github.com/FreakySneaky787/Simple-Organizer/releases/tag/v3.5.3)

## What's New in v3.5.2

Bug-fix release (#91 – #99):

- Several files named like category folders (`Documents`, `Others`) are now moved in the right order (#91); one set to **Don't move** gives a clear message instead of an error per file (#92)
- Scanning a folder named like a rule's target folder no longer creates `New/New` (#93)
- Windows: recursive scans recognise category folders in any case, e.g. `images` (#94)
- Name conflicts keep compressed tar extensions: `backup_1.tar.gz` instead of `backup.tar_1.gz` (#95)
- Filename patterns: only `*` and `?` are wildcards, so `[Draft]*` matches `[Draft] report.docx` (#96)
- Linux: file names that are not valid UTF-8 no longer break **Export CSV** or the built-in Trash (#97, #98)
- Undo keeps track of a file named like its own folder (`Others/Others`) even if moving it back fails (#99)

Full notes: [Release v3.5.2](https://github.com/FreakySneaky787/Simple-Organizer/releases/tag/v3.5.2)

## What's New in v3.5.1

Bug-fix release (#81 – #86):

- **Don't move** is now kept after a restart, so automatic runs no longer move those files (#82)
- **Duplicates:** a copy is only trashed if the kept copy still has the same content, not just the same size (#86)
- History and settings are flushed to disk before they replace the old file, so a power cut cannot leave them empty (#83)
- A file without extension named like a category folder (`Others`, `Documents`) no longer blocks that whole category (#81)
- Scanning a folder that is itself named like a category (`Downloads/Images`) no longer creates `Images/Images` (#84)
- Recursive scans skip the target folders of your rules, like the category folders (#85)

Full notes: [Release v3.5.1](https://github.com/FreakySneaky787/Simple-Organizer/releases/tag/v3.5.1)

## What's New in v3.5.0

Feature release — fixes all open issues (#65 – #76) and adds what was on the roadmap (#77 – #80):

- **Don't move** — keep single files where they are: select them in the Preview and press `Space`, `Delete` or right-click; also respected by later scans and automatic runs of the folder
- **Filter and sort the Preview** — search field (`Ctrl+F`), click a column heading to sort
- **Rules with several conditions** — a rule matches only if all its conditions match, e.g. *extension `pdf` + older than 365 days → `Archive`*
- **Export to CSV** — the scan result opens directly in Excel or LibreOffice
- **History shows the folder** of every run, and Undo last says exactly which run it undoes; after an undo, Auto-organize can be paused so it does not sort the files again
- **Safer Auto-organize** — an unplugged drive no longer makes it switch to the Downloads folder
- Changing a scan option or a rule clears an outdated preview; files removed after the scan are skipped instead of reported as errors
- Starts about twice as fast; `Ctrl+1`–`Ctrl+4` switch tabs, `F5` scans
- Regression tests are now part of the repository and run on GitHub Actions

Full notes: [Release v3.5.0](https://github.com/FreakySneaky787/Simple-Organizer/releases/tag/v3.5.0) · All versions: [Changelog](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Changelog)

---

## Where Data Is Stored

Settings, rules, undo history, staging area and `error.log` live in `%APPDATA%\simple_organizer\` on Windows and in `~/.config/simple_organizer/` and `~/.local/share/simple_organizer/` on Linux (XDG directories are honoured). Details: [Data and Settings](https://github.com/FreakySneaky787/Simple-Organizer/wiki/Data-and-Settings)

When reporting a bug, please attach `error.log` if there is one.

---

## Roadmap

Simple Organizer is feature-complete. Ideas that may still come as packaging or maintenance work:

- Flatpak / AppImage packaging for Linux
- Code-signed Windows executable
- Run the test suites on Linux in GitHub Actions

---

## License

MIT License — Copyright (c) 2026 SchnekayOpen

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

### Third-party

Icons are from [Phosphor Icons](https://phosphoricons.com) (MIT License, Copyright (c) 2023 Phosphor Icons). Their path data is bundled in `icons.py`.
