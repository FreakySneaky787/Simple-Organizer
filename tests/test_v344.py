"""Tests for the v3.4.4 fixes (issues #29 - #51), core logic. Temp folders and a temp APPDATA only."""
import errno, json, os, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(tempfile.mkdtemp(prefix="so344_"))
os.environ["APPDATA"] = str(BASE / "appdata")
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

import utils, organizer, rules
from organizer import FilePlan, scan_folder, organise_files, commit_staging, revert_staging

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

def fresh(name: str) -> Path:
    d = BASE / name
    d.mkdir()
    return d

# ---------- #29 cross-drive moves never leave a second copy ----------
real_rename, real_unlink = os.rename, os.unlink
def cross_device(a, b):
    raise OSError(errno.EXDEV, "Invalid cross-device link")
d = fresh("x29")
(d / "report.pdf").write_text("locked")
src_locked = str(d / "report.pdf")
def unlink_locked(p, *a, **k):
    if str(p) == src_locked:
        raise PermissionError("file is open in another program")
    return real_unlink(p, *a, **k)
os.rename, os.unlink = cross_device, unlink_locked
try:
    errs = organise_files(scan_folder(d).plans, staging=True)
finally:
    os.rename, os.unlink = real_rename, real_unlink
staged = list(organizer.STAGING_DIR.rglob("report*.pdf")) if organizer.STAGING_DIR.exists() else []
check("#29 failed cross-drive move reports an error", len(errs) == 1, errs)
check("#29 no orphaned copy in staging", staged == [], staged)
check("#29 original untouched", (d / "report.pdf").read_text() == "locked")

(d / "ok.pdf").write_text("fine")
os.rename = cross_device
try:
    utils.safe_move(d / "ok.pdf", d / "moved.pdf")
finally:
    os.rename = real_rename
check("#29 cross-drive move works: copy made, original removed",
      (d / "moved.pdf").read_text() == "fine" and not (d / "ok.pdf").exists())
(d / "a.txt").write_text("new"); (d / "b.txt").write_text("existing")
os.rename = cross_device
try:
    utils.safe_move(d / "a.txt", d / "b.txt"); overwrote = True
except FileExistsError:
    overwrote = False
finally:
    os.rename = real_rename
check("#29 cross-drive copy never overwrites an existing file",
      not overwrote and (d / "b.txt").read_text() == "existing" and (d / "a.txt").exists())

# ---------- #30 single instance ----------
lock = utils.acquire_instance_lock()
probe = subprocess.run([sys.executable, "-c",
    "import sys; sys.path.insert(0, ' + repr(ROOT) + '); import utils; "
    "print(utils.acquire_instance_lock() is None)"], capture_output=True, text=True,
    env={**os.environ})
check("#30 second process cannot take the lock", probe.stdout.strip() == "True", probe.stdout + probe.stderr)
lock.close()
probe = subprocess.run([sys.executable, "-c",
    "import sys; sys.path.insert(0, ' + repr(ROOT) + '); import utils; "
    "print(utils.acquire_instance_lock() is None)"], capture_output=True, text=True, env={**os.environ})
check("#30 lock is free again once released", probe.stdout.strip() == "False", probe.stdout + probe.stderr)

# ---------- #31 / #45 numbered history, manual runs survive the scheduler ----------
def one_run(folder: Path, name: str, scheduled: bool) -> None:
    (folder / name).write_text(name)
    organise_files([FilePlan(folder / name, folder / "Documents" / name, "Documents", root=folder)],
                   scheduled=scheduled)
h = fresh("x31")
for i in range(3):
    one_run(h, f"manual{i}.txt", False)
for i in range(25):
    one_run(h, f"auto{i}.txt", True)
runs = organizer._sorted_runs()
manual = [r for r in runs if not organizer._is_scheduled_run(r)]
auto = [r for r in runs if organizer._is_scheduled_run(r)]
check("#31 all 3 manual runs still undoable after 25 automatic runs", len(manual) == 3, len(manual))
check("#31 automatic runs limited to MAX_HISTORY", len(auto) == organizer.MAX_HISTORY, len(auto))
check("#31 trimmed runs kept for following", len(list(organizer.TRIMMED_DIR.glob("run_*.json"))) == 5)
check("#31 History marks automatic runs",
      any(e["scheduled"] and e["label"].endswith("automatic") for e in organizer.list_undo_history()))
check("#45 run files are numbered", all(organizer._run_seq(r) for r in runs))

class EarlyClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2001, 1, 1, tzinfo=timezone.utc)
real_dt = organizer.datetime
organizer.datetime = EarlyClock
try:
    one_run(h, "after_clock_jump.txt", False)
finally:
    organizer.datetime = real_dt
newest = organizer._newest_run_file()
check("#45 run written with a clock in the past is still the newest",
      "after_clock_jump" in newest.read_text(), newest.name)
check("#45 and it was not trimmed away", newest.exists())

# ---------- #33 staging leaves online-only files where they are ----------
c = fresh("x33")
(c / "cloud.pdf").write_text("c"); (c / "local.pdf").write_text("l")
real_cp = organizer.is_cloud_placeholder
organizer.is_cloud_placeholder = lambda st: getattr(st, "st_size", 0) == 1 and False
cloud_ino = (c / "cloud.pdf").stat().st_ino
organizer.is_cloud_placeholder = lambda st: st.st_ino == cloud_ino
logs = []
try:
    errs = organise_files(scan_folder(c).plans, staging=True, log_callback=logs.append)
finally:
    organizer.is_cloud_placeholder = real_cp
check("#33 online-only file not staged", (c / "cloud.pdf").exists() and not errs, errs)
check("#33 local file staged", not (c / "local.pdf").exists())
check("#33 log explains it", any("online-only" in l for l in logs), logs)
revert_staging()

# ---------- #35 commit/revert never recreate a vanished scanned folder ----------
s = fresh("x35")
(s / "a.pdf").write_text("a")
organise_files(scan_folder(s).plans, staging=True)
s.rename(BASE / "x35_renamed")
errs = commit_staging()
check("#35 commit refuses: folder gone", errs and "no longer exists" in errs[0], errs)
check("#35 old folder not recreated", not s.exists())
check("#35 file stays staged", organizer.has_staging())
errs = revert_staging()
check("#35 revert refuses too and keeps it staged",
      errs and not s.exists() and organizer.has_staging(), errs)
(BASE / "x35_renamed").rename(s)
check("#35 works again once the folder is back", not commit_staging() and (s / "Documents" / "a.pdf").exists())

# ---------- #37 / #43 problem target folders ----------
f37 = fresh("x37")
(f37 / "Documents").write_text("I am a file")
(f37 / "a.pdf").write_text("a"); (f37 / "b.pdf").write_text("b"); (f37 / "c.jpg").write_bytes(b"c")
r = scan_folder(f37)
planned = sorted(p.source.name for p in r.plans)
check("#37 PDFs not planned while a file blocks 'Documents'", "a.pdf" not in planned and "c.jpg" in planned, planned)
check("#37 reported once with the cause", sum("blocks the folder 'Documents'" in e for e in r.errors) == 1, r.errors)

f43 = fresh("x43"); outside = fresh("x43_outside")
(f43 / "a.jpg").write_bytes(b"x")
subprocess.run(["cmd", "/c", "mklink", "/J", str(f43 / "Images"), str(outside)], capture_output=True, check=True)
r = scan_folder(f43)
organise_files(r.plans)
check("#43 nothing moved through the junction", not any(outside.iterdir()) and (f43 / "a.jpg").exists())
check("#43 reported", any("points outside" in e for e in r.errors), r.errors)
subprocess.run(["cmd", "/c", "rmdir", str(f43 / "Images")])

# ---------- #38 undo follows a file through a trimmed run ----------
f38 = fresh("x38")
(f38 / "x.pdf").write_text("x")
organise_files(scan_folder(f38).plans)                         # manual run A: x -> Documents
run_a = organizer._newest_run_file()
organise_files([FilePlan(f38 / "Documents" / "x.pdf", f38 / "Archive" / "x.pdf", "Archive", root=f38)],
               scheduled=True)                                 # automatic run B moves it on
for i in range(organizer.MAX_HISTORY + 1):                    # B gets trimmed
    one_run(f38, f"filler{i}.txt", True)
check("#38 run B is no longer undoable",
      not any("Archive" in r.read_text() for r in organizer._sorted_runs() if organizer._is_scheduled_run(r)))
logs = []
errs = organizer.undo_specific_run(run_a, log_callback=logs.append)
check("#38 undo of A still finds x via the trimmed run", not errs and (f38 / "x.pdf").exists(), logs)

# ---------- #40 hard links ----------
f40 = fresh("x40")
(f40 / "a.bin").write_bytes(b"same")
os.link(f40 / "a.bin", f40 / "a_link.bin")
links: list[Path] = []
check("#40 hard links alone are no duplicate group", organizer.find_duplicates(sorted(f40.iterdir()), hard_links=links) == [])
check("#40 hard link reported", [p.name for p in links] == ["a_link.bin"], links)
(f40 / "copy.bin").write_bytes(b"same")
groups = organizer.find_duplicates(sorted(f40.iterdir()))
check("#40 real copy still found, link counted once", len(groups) == 1 and len(groups[0]) == 2, groups)

# ---------- #41 shortcuts ----------
f41 = fresh("x41")
for n in ("Chrome.lnk", "Site.url", "app.desktop", "doc.pdf"):
    (f41 / n).write_text("x")
r = scan_folder(f41)
check("#41 shortcuts are never planned", [p.source.name for p in r.plans] == ["doc.pdf"], [p.source.name for p in r.plans])
check("#41 note mentions shortcuts", any("shortcuts" in n for n in r.notes), r.notes)

# ---------- #44 .ts ----------
f44 = fresh("x44")
packet = bytes([0x47]) + bytes(187)
(f44 / "recording.ts").write_bytes(packet * 5)
(f44 / "app.ts").write_text("export const x = 1;\n" * 30)
(f44 / "G.ts").write_text("G" + "x" * 500)
cat = {n: utils.get_category(f44 / n) for n in ("recording.ts", "app.ts", "G.ts")}
check("#44 MPEG-TS video -> Videos", cat["recording.ts"] == "Videos", cat)
check("#44 TypeScript stays Code", cat["app.ts"] == "Code" and cat["G.ts"] == "Code", cat)
check("#44 video sub-category TS", utils.get_subcategory(f44 / "recording.ts", "Videos") == "TS")

# ---------- #47 new file types ----------
expect = {"IMG.HEIC": ("Images", "Photos"), "p.avif": ("Images", "Photos"), "setup.exe": ("Programs", "Windows"),
          "x.msi": ("Programs", "Windows"), "a.dmg": ("Programs", "macOS"), "a.apk": ("Programs", "Android"),
          "a.AppImage": ("Programs", "Linux"), "a.deb": ("Programs", "Linux"), "disk.iso": ("Disk Images", ""),
          "b.epub": ("Documents", "Ebooks"), "m.eml": ("Documents", "Email"), "s.xlsm": ("Documents", "Spreadsheets"),
          "c.mts": ("Videos", "TS")}
got = {n: (utils.get_category(Path(n)), utils.get_subcategory(Path(n), utils.get_category(Path(n)))) for n in expect}
check("#47 new categories", got == expect, {n: g for n, g in got.items() if g != expect[n]})

# ---------- #46 trash owner window plumbing ----------
seen = []
real_tp = organizer._trash_file_platform
organizer._trash_file_platform = lambda p, hwnd=None: seen.append(hwnd)
(BASE / "t.txt").write_text("t")
organizer.trash_files([BASE / "t.txt"], hwnd=4242)
organizer._trash_file_platform = real_tp
check("#46 hwnd reaches the trash call", seen == [4242], seen)

# ---------- #50 corrupt rules that cannot be backed up ----------
rules.RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
rules.RULES_FILE.write_text("{ broken")
real_replace = Path.replace
Path.replace = lambda self, target: (_ for _ in ()).throw(PermissionError("locked"))
try:
    rules.load_rules(); raised = False
except rules.RulesReadError:
    raised = True
finally:
    Path.replace = real_replace
check("#50 RulesReadError instead of 'no rules'", raised)
check("#50 corrupt file left untouched", rules.RULES_FILE.read_text() == "{ broken")
rules.RULES_FILE.unlink()

# ---------- #51 dead code ----------
check("#51 has_undo_history removed", not hasattr(organizer, "has_undo_history"))
check("#51 ALL_SUBCATEGORY_NAMES removed", not hasattr(utils, "ALL_SUBCATEGORY_NAMES"))

shutil.rmtree(BASE, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
