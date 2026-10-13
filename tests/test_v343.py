"""Tests for the v3.4.3 fixes (issues #14 - #28). Temp folders and a temp APPDATA only."""
import json, os, shutil, sys, tempfile, time, types
from pathlib import Path

BASE = Path(tempfile.mkdtemp(prefix="so343_"))
os.environ["APPDATA"] = str(BASE / "appdata")
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

import utils, organizer, config, rules
from organizer import FilePlan, scan_folder, organise_files, undo_specific_run, list_undo_history

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

# ---------- #14 exe folder is organised, exe itself is not ----------
dl = BASE / "Downloads"
dl.mkdir()
(dl / "simple_organizer.exe").write_bytes(b"MZ")
(dl / "README.md").write_text("readme")
(dl / "a.pdf").write_text("pdf")
meipass = BASE / "_MEI123"
meipass.mkdir()
sys.frozen, sys._MEIPASS = True, str(meipass)
real_exe, sys.executable = sys.executable, str(dl / "simple_organizer.exe")
try:
    r = scan_folder(dl)
    names = sorted(p.source.name for p in r.plans)
    check("#14 folder containing the exe is scanned", not r.errors and "a.pdf" in names, (r.errors, names))
    check("#14 exe itself is never planned", "simple_organizer.exe" not in names, names)
    check("#14 data dir still refused", scan_folder(organizer.DATA_DIR).errors)
    check("#14 bundle dir (_MEIPASS) refused", scan_folder(meipass).errors)
finally:
    del sys.frozen, sys._MEIPASS
    sys.executable = real_exe
check("#14 source mode: program folder still protected",
      scan_folder(Path(ROOT)).errors)

# ---------- #15 cloud placeholders are never read ----------
hashed = []
real_sha = organizer._sha256
organizer._sha256 = lambda p: hashed.append(p) or real_sha(p)
st_real = os.stat_result
fake_attrs = {}
real_stat = Path.stat
def fake_stat(self, *a, **k):
    st = real_stat(self, *a, **k)
    if self.name in fake_attrs:
        return types.SimpleNamespace(st_size=st.st_size, st_ino=0, st_file_attributes=fake_attrs[self.name],
                                     st_mtime=st.st_mtime, st_dev=st.st_dev)
    return st
cl = BASE / "cloud"; cl.mkdir()
for n in ("x1.bin", "x2.bin", "y1.bin", "y2.bin"):
    (cl / n).write_bytes(b"same content")
fake_attrs.update({"x1.bin": 0x400020, "x2.bin": 0x400020})
Path.stat = fake_stat
skipped: list[Path] = []
groups = organizer.find_duplicates(sorted(cl.iterdir()), skipped_cloud=skipped)
Path.stat = real_stat
organizer._sha256 = real_sha
check("#15 online-only files are not hashed", {p.name for p in hashed} == {"y1.bin", "y2.bin"},
      [p.name for p in hashed])
check("#15 online-only files reported", {p.name for p in skipped} == {"x1.bin", "x2.bin"})
check("#15 local duplicates still found", [sorted(p.name for p in g) for g in groups] == [["y1.bin", "y2.bin"]])
od = Path.home() / "OneDrive - OpenMind"
real_placeholder = next((Path(dp) / f for dp, _, fs in os.walk(od) for f in fs
                         if organizer.is_cloud_placeholder(os.stat(Path(dp) / f))), None)
if real_placeholder:
    skipped = []
    organizer.find_duplicates([real_placeholder, real_placeholder], skipped_cloud=skipped)
    check("#15 real OneDrive placeholder skipped and still online-only",
          len(skipped) == 1 and organizer.is_cloud_placeholder(os.stat(real_placeholder)))

# ---------- #18 cheap history check ----------
reads = []
real_read = Path.read_text
Path.read_text = lambda self, *a, **k: reads.append(self) or real_read(self, *a, **k)
organizer.has_last_run(); organizer.has_last_run(); organizer.has_staging()
Path.read_text = real_read
check("#18 has_undo_history/has_last_run read no history file",
      not any("history" in str(p) for p in reads), reads)

# ---------- #23 C:\Users ----------
check("#23 C:\\Users is unusual", utils.risky_folder_reason(Path.home().parent) is not None)
check("#23 Downloads still fine", utils.risky_folder_reason(Path.home() / "Downloads") is None)

# ---------- #25 undo out of order follows the file ----------
root = BASE / "org"; root.mkdir()
(root / "x.pdf").write_text("x")
r = scan_folder(root)
organise_files(r.plans)                                  # run A: x.pdf -> Documents/x.pdf
time.sleep(0.01)
organise_files([FilePlan(root / "Documents" / "x.pdf", root / "Archive" / "x.pdf", "Archive")])  # run B
runs = sorted(organizer.HISTORY_DIR.glob("run_*.json"))
run_a, run_b = runs[-2], runs[-1]
logs = []
errs = undo_specific_run(run_a, log_callback=logs.append)
check("#25 undo older run restores file to original place",
      not errs and (root / "x.pdf").exists() and not (root / "Archive" / "x.pdf").exists(), (errs, logs))
check("#25 log says it followed the file", any("newer run" in l for l in logs), logs)
errs = undo_specific_run(run_b, log_callback=logs.append)
check("#25 undoing the newer run afterwards is harmless", not errs and (root / "x.pdf").exists())

# ---------- #24 approvals persist (config side) ----------
s = config.load_settings()
check("#24 approved_folders default is empty, not shared", s["approved_folders"] == [] and
      s["approved_folders"] is not config.DEFAULT_SETTINGS["approved_folders"])
s["approved_folders"].append("X")
check("#24 defaults not mutated", config.DEFAULT_SETTINGS["approved_folders"] == [])
config.get_settings_path().write_text(json.dumps({"approved_folders": ["C:\\a", 5], "window_x": "1",
                                                   "window_y": 12.0, "window_maximized": 1}))
s = config.load_settings()
check("#24/#27 settings coercion", s["approved_folders"] == [] and s["window_x"] is None
      and s["window_y"] == 12 and s["window_maximized"] is False, s)

# ---------- #28 Linux: XDG dirs + per-volume trash ----------
real_platform = utils.sys.platform
utils.sys.platform = "linux"
fake_home = BASE / "home"
(fake_home / ".config").mkdir(parents=True)
real_home = Path.home
Path.home = classmethod(lambda cls: fake_home)
try:
    os.environ["XDG_CONFIG_HOME"] = str(BASE / "xdgcfg")
    check("#28 XDG_CONFIG_HOME honoured", utils.get_config_dir() == BASE / "xdgcfg" / "simple_organizer")
    (fake_home / ".config" / "simple_organizer").mkdir()
    check("#28 existing old folder keeps being used", utils.get_config_dir() == fake_home / ".config" / "simple_organizer")
    (BASE / "xdgcfg" / "simple_organizer").mkdir(parents=True)
    check("#28 new folder wins once it exists", utils.get_config_dir() == BASE / "xdgcfg" / "simple_organizer")
    os.environ["XDG_CONFIG_HOME"] = "relative/path"
    check("#28 relative XDG value ignored", utils.get_config_dir() == fake_home / ".config" / "simple_organizer")
    del os.environ["XDG_CONFIG_HOME"]
    os.environ["XDG_DATA_HOME"] = str(BASE / "xdgdata")
    check("#28 XDG_DATA_HOME honoured", utils.get_data_dir() == BASE / "xdgdata" / "simple_organizer")
finally:
    utils.sys.platform = real_platform
    Path.home = real_home

usb = BASE / "usb"
(usb / "photos").mkdir(parents=True)
f = usb / "photos" / "dup copy.jpg"
f.write_bytes(b"jpg")
os.environ["XDG_DATA_HOME"] = str(BASE / "xdgdata")
real_stat = Path.stat
def dev_stat(self, *a, **k):
    st = real_stat(self, *a, **k)
    on_usb = self == usb or usb in self.parents
    return types.SimpleNamespace(st_dev=999 if on_usb else st.st_dev, st_size=st.st_size)
Path.stat = dev_stat
try:
    cands = organizer._trash_candidates(f.resolve())
    check("#28 file on another drive uses that drive's .Trash-uid first",
          cands[0] == (usb.resolve() / ".Trash-0", usb.resolve()) and cands[-1][1] is None, cands)
    organizer._trash_xdg(f.resolve())
finally:
    Path.stat = real_stat
info = list((usb / ".Trash-0" / "info").glob("*.trashinfo"))
check("#28 file moved into the drive's trash", (usb / ".Trash-0" / "files" / "dup copy.jpg").exists() and not f.exists())
check("#28 trashinfo path is relative to the drive", info and "Path=photos/dup%20copy.jpg" in info[0].read_text(), info and info[0].read_text())
g = BASE / "local.txt"; g.write_text("l")
check("#28 same-drive file uses the home trash", organizer._trash_candidates(g.resolve()) ==
      [(BASE / "xdgdata" / "Trash", None)])

shutil.rmtree(BASE, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
