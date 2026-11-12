"""Core tests for v3.6.1: real cancel state (#111), no hashing of sorted-only
duplicates (#112), the login entry is not moved to another copy (#114) and
the tray loop on Linux (#108)."""
import os, shutil, sys, tempfile, threading
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so361_"))
os.environ["APPDATA"] = str(APPDATA)
os.environ["XDG_CONFIG_HOME"] = str(APPDATA / "xdg")
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

import organizer, autostart, tray

def fresh(*parts):
    d = APPDATA.joinpath("w", *parts)
    d.mkdir(parents=True)
    return d.resolve()

# ---------- #111 Cancel during the last file is not a cancelled run ----------
d = fresh("last")
for i in range(3):
    (d / f"f{i}.pdf").write_text(f"file {i}")
r = organizer.scan_folder(d)
cancel = threading.Event()
outcome: dict = {}
def progress(cur, total):
    if cur == total:          # Cancel while the last file is being moved
        cancel.set()
log: list[str] = []
organizer.organise_files(r.plans, progress_callback=progress, log_callback=log.append,
                         cancel=cancel, outcome=outcome)
check("#111 all files moved", len(os.listdir(d / "Documents")) == 3)
check("#111 not reported as cancelled", outcome.get("cancelled") is False, outcome)
check("#111 no [CANCELLED] line", not any("[CANCELLED]" in m for m in log), log)
organizer.undo_last_run()

cancel = threading.Event()
outcome = {}
def progress2(cur, total):
    if cur == 1:
        cancel.set()
organizer.organise_files(organizer.scan_folder(d).plans, progress_callback=progress2,
                         cancel=cancel, outcome=outcome)
check("#111 a real cancel is reported", outcome.get("cancelled") is True, outcome)
organizer.undo_last_run()

# ---------- #112 equal-sized sorted files are not hashed ----------
d = fresh("dups")
(d / "Videos").mkdir()
(d / "Videos" / "a.mp4").write_bytes(b"V" * 4096)
(d / "Videos" / "b.mp4").write_bytes(b"V" * 4096)          # sorted duplicates, same size
(d / "Documents").mkdir()
(d / "Documents" / "cv.pdf").write_bytes(b"CV-1234")
(d / "cv (1).pdf").write_bytes(b"CV-1234")                 # new copy of a sorted file
(d / "other.txt").write_bytes(b"x" * 100)

hashed: list[str] = []
real_hash = organizer._sha256
def counting(path, *a, **k):
    hashed.append(Path(path).name)
    return real_hash(path, *a, **k)
organizer._sha256 = counting
try:
    r = organizer.scan_folder(d)
finally:
    organizer._sha256 = real_hash
names = [sorted(p.name for p in g) for g in r.duplicate_groups]
check("#112 copy of a sorted file still found", ["cv (1).pdf", "cv.pdf"] in names, names)
check("#112 sorted-only group not reported", not any("a.mp4" in g for g in names), names)
check("#112 sorted-only files not hashed", "a.mp4" not in hashed and "b.mp4" not in hashed, hashed)

found = organizer.find_duplicates([d / "Videos" / "a.mp4", d / "Videos" / "b.mp4"])
check("#112 without only_with nothing changes", len(found) == 1, found)
found = organizer.find_duplicates([d / "Videos" / "a.mp4", d / "Videos" / "b.mp4"],
                                  only_with=frozenset())
check("#112 only_with drops buckets without a new file", found == [], found)

# ---------- #114 refresh leaves an entry for another existing copy alone ----------
other = fresh("other") / "simple_organizer.exe"
other.write_text("x")
ours = autostart.command_args()
check("#114 same program is rewritten", autostart._same_or_missing(ours))
check("#114 another existing copy is kept",
      not autostart._same_or_missing([str(other), autostart.MINIMIZED]))
check("#114 a program that is gone is rewritten",
      autostart._same_or_missing([str(other.with_name("gone.exe")), autostart.MINIMIZED]))

if sys.platform == "win32":
    cmd = '"C:\\Program Files\\SO\\simple_organizer.exe" --minimized'
    check("#114 Windows command is split", autostart._split_command(cmd)
          == ["C:\\Program Files\\SO\\simple_organizer.exe", "--minimized"],
          autostart._split_command(cmd))

# refresh() with a stubbed entry: never touches the real login entry.
written: list[str] = []
real = (autostart.is_enabled, autostart.current_args, autostart.enable)
autostart.is_enabled = lambda: True
autostart.enable = lambda: written.append("enable")
try:
    autostart.current_args = lambda: [str(other), autostart.MINIMIZED]
    autostart.refresh()
    check("#114 refresh keeps the other copy", written == [], written)
    autostart.current_args = lambda: [str(other.with_name("gone.exe")), autostart.MINIMIZED]
    autostart.refresh()
    check("#114 refresh repairs a missing program", written == ["enable"], written)
finally:
    autostart.is_enabled, autostart.current_args, autostart.enable = real

# ---------- #108 on Linux the tray loop runs on its own thread ----------
class FakeIcon:
    def __init__(self, *a, **k):
        self.ran = threading.Event(); self.detached = False
    def run(self):
        self.ran.set()
    def run_detached(self):
        self.detached = True
class FakeMenu:
    SEPARATOR = object()
    def __init__(self, *items): pass
class FakeItem:
    def __init__(self, *a, **k): pass
class FakePystray:
    Icon = FakeIcon; Menu = FakeMenu; MenuItem = FakeItem
real_load, real_mod, real_platform = tray._load, tray.pystray, tray.sys.platform
tray._load = lambda: True
tray.pystray = FakePystray
tray._image = lambda: None
try:
    for platform, threaded in (("linux", True), ("win32", False)):
        tray.sys.platform = platform
        t = tray.TrayIcon("T", lambda: None, lambda: None, lambda: None, lambda: False, lambda: None)
        check(f"#108 tray starts ({platform})", t.start())
        icon = t._icon
        if threaded:
            check("#108 Linux runs icon.run() on a thread", icon.ran.wait(2) and not icon.detached)
        else:
            check("#108 Windows uses run_detached()", icon.detached and not icon.ran.is_set())
finally:
    tray._load, tray.pystray = real_load, real_mod
    tray.sys.platform = real_platform

shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
