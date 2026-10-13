"""Tests for the v3.4.5 fixes (issues #52 - #64), core logic. Temp folders and a temp APPDATA only."""
import errno, json, os, shutil, stat, subprocess, sys, tempfile
from pathlib import Path

BASE = Path(tempfile.mkdtemp(prefix="so345_"))
os.environ["APPDATA"] = str(BASE / "appdata")
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

import utils, organizer, rules, config
from organizer import scan_folder, organise_files

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

def fresh(name: str) -> Path:
    d = BASE / name
    d.mkdir()
    return d

RULE = {"name": "Rechnungen für 2024", "enabled": True, "condition_type": "extension",
        "condition_value": "pdf", "target_folder": "Invoices"}
rules.RULES_FILE.parent.mkdir(parents=True, exist_ok=True)

# ---------- #52 rules.json that is not UTF-8 ----------
for label, data in (("ANSI", json.dumps([RULE], ensure_ascii=False).encode("cp1252")),
                    ("UTF-16", json.dumps([RULE]).encode("utf-16"))):
    for old in rules.RULES_FILE.parent.glob("rules_corrupt_*.json"):
        old.unlink()
    rules.RULES_FILE.write_bytes(data)
    try:
        loaded, exc = rules.load_rules(), None
    except Exception as e:  # noqa: BLE001
        loaded, exc = None, e
    check(f"#52 {label} rules.json does not raise", exc is None, repr(exc))
    check(f"#52 {label} rules.json backed up, not lost",
          not rules.RULES_FILE.exists() and len(list(rules.RULES_FILE.parent.glob("rules_corrupt_*.json"))) == 1)
d = fresh("x52")
(d / "a.pdf").write_text("x")
rules.RULES_FILE.write_bytes(json.dumps([RULE], ensure_ascii=False).encode("cp1252"))
res = scan_folder(d)
check("#52 scan still works with an ANSI rules.json", [p.source.name for p in res.plans] == ["a.pdf"], res.errors)
real_load = organizer.load_rules
organizer.load_rules = lambda: (_ for _ in ()).throw(UnicodeDecodeError("utf-8", b"\xfc", 0, 1, "x"))
try:
    res = scan_folder(d)
finally:
    organizer.load_rules = real_load
check("#52 unexpected rules error stops the scan cleanly", not res.plans and any("Rules could not be loaded" in e for e in res.errors))
for old in rules.RULES_FILE.parent.glob("rules_corrupt_*.json"):
    old.unlink()

# ---------- #53 BOM ----------
rules.RULES_FILE.write_bytes(b"\xef\xbb\xbf" + json.dumps([RULE]).encode())
loaded = rules.load_rules()
check("#53 rules.json with BOM is read", len(loaded) == 1 and loaded[0].target_folder == "Invoices")
check("#53 rules.json with BOM is not moved aside", rules.RULES_FILE.exists()
      and not list(rules.RULES_FILE.parent.glob("rules_corrupt_*.json")))
rules.RULES_FILE.unlink()
sp = config.get_settings_path()
sp.write_bytes(b"\xef\xbb\xbf" + json.dumps({"dark_mode": True, "max_depth": 9}).encode())
s = config.load_settings()
check("#53 settings.json with BOM is read", s["dark_mode"] is True and s["max_depth"] == 9)
sp.unlink()

# ---------- #54 cross-drive move of read-only files ----------
real_rename, real_unlink, real_copystat = os.rename, os.unlink, shutil.copystat
def cross_device(a, b):
    raise OSError(errno.EXDEV, "Invalid cross-device link")
d = fresh("x54")
src, dst = d / "ro.txt", d / "out" / "ro.txt"
dst.parent.mkdir()
src.write_text("data"); os.chmod(src, stat.S_IREAD)
os.rename = cross_device
try:
    utils.safe_move(src, dst); exc = None
except Exception as e:  # noqa: BLE001
    exc = e
finally:
    os.rename = real_rename
check("#54 read-only file moved across drives", exc is None and not src.exists() and dst.read_text() == "data", repr(exc))
check("#54 read-only attribute kept on the moved file", dst.exists() and not os.stat(dst).st_mode & stat.S_IWRITE)
os.chmod(dst, stat.S_IWRITE)

src2, dst2 = d / "locked_ro.txt", d / "out" / "locked_ro.txt"
src2.write_text("data"); os.chmod(src2, stat.S_IREAD)
def unlink_src_locked(p, *a, **k):
    if os.path.normcase(str(p)) == os.path.normcase(str(src2)):
        raise PermissionError(errno.EACCES, "in use")
    return real_unlink(p, *a, **k)
os.rename, os.unlink = cross_device, unlink_src_locked
try:
    utils.safe_move(src2, dst2); exc = None
except Exception as e:  # noqa: BLE001
    exc = e
finally:
    os.rename, os.unlink = real_rename, real_unlink
check("#54 locked read-only file: move fails", isinstance(exc, PermissionError), repr(exc))
check("#54 locked read-only file: no stray copy left", not dst2.exists())
check("#54 locked read-only file: original intact and still read-only",
      src2.read_text() == "data" and not os.stat(src2).st_mode & stat.S_IWRITE)
os.chmod(src2, stat.S_IWRITE)

src3, dst3 = d / "fat.txt", d / "out" / "fat.txt"
src3.write_text("data")
def copystat_fails(*a, **k):
    raise PermissionError(errno.EPERM, "Operation not permitted")
os.rename, shutil.copystat = cross_device, copystat_fails
try:
    utils.safe_move(src3, dst3); exc = None
except Exception as e:  # noqa: BLE001
    exc = e
finally:
    os.rename, shutil.copystat = real_rename, real_copystat
check("#54 metadata that cannot be copied does not fail the move",
      exc is None and not src3.exists() and dst3.read_text() == "data", repr(exc))

# ---------- #55 damaged newest history run ----------
d = fresh("x55")
(d / "a.txt").write_text("a")
organise_files(scan_folder(d).plans)
seq = organizer._next_seq()
bad = organizer.HISTORY_DIR / f"run_{seq:08d}_20991231T000000_000000.json"
bad.write_text("{ not json")
logs: list[str] = []
errs = organizer.undo_last_run(log_callback=logs.append)
check("#55 undo last skips the damaged run", errs == [] and (d / "a.txt").exists(), errs)
check("#55 damaged run moved to history/damaged", not bad.exists()
      and (organizer.DAMAGED_DIR / bad.name).exists())
check("#55 damaged run is reported in the log", any("is damaged" in l for l in logs))
check("#55 nothing left to undo afterwards", not organizer.has_last_run())

# ---------- #56 instance lock ----------
first = utils.acquire_instance_lock()
second = utils.acquire_instance_lock()
check("#56 second instance is still refused", first is not None and second is None)
first.close()
import msvcrt
real_locking = msvcrt.locking
def no_lock_support(*a, **k):
    raise OSError(errno.ENOLCK, "No locks available")
msvcrt.locking = no_lock_support
try:
    h = utils.acquire_instance_lock()
finally:
    msvcrt.locking = real_locking
check("#56 a file system without locks does not block the start", h is not None)
if hasattr(h, "close"):
    h.close()

# ---------- #57 junctions without DirEntry.is_junction ----------
d = fresh("x57")
(d / "real").mkdir()
target = fresh("x57_outside")
subprocess.run(["cmd", "/c", "mklink", "/J", str(d / "jn"), str(target)], check=True, capture_output=True)
class OldEntry:   # DirEntry of Python 3.11: no is_junction
    def __init__(self, e): self._e = e
    def is_symlink(self): return self._e.is_symlink()
    def stat(self, **k): return self._e.stat(**k)
entries = {e.name: OldEntry(e) for e in os.scandir(d)}
check("#57 junction detected without is_junction", organizer._is_link(entries["jn"]))
check("#57 normal folder is not a link", not organizer._is_link(entries["real"]))
os.rmdir(d / "jn")

# ---------- #58 trash re-checks the kept copy ----------
d = fresh("x58")
a, b = d / "a.bin", d / "b.bin"
a.write_bytes(b"same"); b.write_bytes(b"same")
real_trash = organizer._trash_file_platform
trashed: list[Path] = []
organizer._trash_file_platform = lambda p, hwnd=None: (trashed.append(p), p.unlink())
try:
    b.unlink()   # the kept copy disappears after the scan
    errs, n = organizer.trash_files([a], keep={a: [b]})
    check("#58 last copy is not trashed", n == 0 and a.exists() and not trashed and errs)
    b.write_bytes(b"other content")   # kept copy changed (different size)
    errs, n = organizer.trash_files([a], keep={a: [b]})
    check("#58 changed kept copy: not trashed", n == 0 and a.exists())
    b.write_bytes(b"same")
    errs, n = organizer.trash_files([a], keep={a: [b]})
    check("#58 kept copy present: trashed", n == 1 and not a.exists() and errs == [])
finally:
    organizer._trash_file_platform = real_trash

# ---------- #60 extension values ----------
check("#60 *.pdf normalised", rules.normalize_extension(" *.PDF ") == "pdf")
check("#60 valid single extensions", rules.is_valid_extension("tar.gz") and rules.is_valid_extension(".pdf"))
check("#60 lists rejected", not rules.is_valid_extension("pdf, docx") and not rules.is_valid_extension("pdf docx")
      and not rules.is_valid_extension("*") and not rules.is_valid_extension(""))
r = rules.Rule("x", True, "extension", "*.pdf", "Docs")
check("#60 *.pdf rule from a hand-edited file matches", rules.match_rule(Path("report.PDF"), r))

# ---------- #61 LibreOffice lock files ----------
d = fresh("x61")
(d / "report.odt").write_text("doc")
(d / ".~lock.report.odt#").write_text("lock")
names = sorted(p.source.name for p in scan_folder(d, include_hidden=True).plans)
check("#61 LibreOffice lock file is left alone", names == ["report.odt"], names)

# ---------- #62 running downloads ----------
d = fresh("x62")
(d / "setup.zip").write_bytes(b"")
(d / "setup.zip.part").write_bytes(b"x" * 10)
(d / "movie.mkv.crdownload").write_bytes(b"x")
(d / "movie.mkv").write_bytes(b"")
(d / "done.pdf").write_text("x")
res = scan_folder(d)
names = sorted(p.source.name for p in res.plans)
check("#62 placeholder of a running download is left alone", names == ["done.pdf"], names)
check("#62 counted as left alone", any("4 files left alone" in n for n in res.notes), res.notes)
sub = d / "sub"; sub.mkdir()
(sub / "x.iso").write_bytes(b""); (sub / "x.iso.part").write_bytes(b"x")
names = sorted(p.source.name for p in scan_folder(d, recursive=True).plans)
check("#62 also in recursive scans", "x.iso" not in names, names)
(d / "setup.zip.part").unlink()
names = sorted(p.source.name for p in scan_folder(d).plans)
check("#62 organised once the download has finished", "setup.zip" in names, names)

# ---------- #64 Downloads folder ----------
check("#64 Windows known folder", utils.get_downloads_dir() == Path(subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path"],
    capture_output=True, text=True).stdout.strip()))
cfg = BASE / "xdgcfg"; cfg.mkdir()
(cfg / "user-dirs.dirs").write_text('# comment\nXDG_DOWNLOAD_DIR="$HOME/Téléchargements"\n', encoding="utf-8")
real_platform = utils.sys.platform
os.environ["XDG_CONFIG_HOME"] = str(cfg)
utils.sys.platform = "linux"
try:
    got = utils.get_downloads_dir()
    (cfg / "user-dirs.dirs").write_text('XDG_DOWNLOAD_DIR="$HOME/"\n', encoding="utf-8")
    got_home = utils.get_downloads_dir()
finally:
    utils.sys.platform = real_platform
    del os.environ["XDG_CONFIG_HOME"]
check("#64 Linux XDG_DOWNLOAD_DIR", got == Path.home() / "Téléchargements", got)
check("#64 Linux: download dir = home falls back to ~/Downloads", got_home == Path.home() / "Downloads", got_home)

shutil.rmtree(BASE, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
