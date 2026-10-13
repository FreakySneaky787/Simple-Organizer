"""GUI tests for the v3.4.5 fixes. Drives the real app; dialogs are answered by timers."""
import json, os, shutil, sys, tempfile, time
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so345_gui_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)
import main, organizer, rules, utils
from organizer import scan_folder

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

def pump(app, seconds, until=lambda: False):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        if until():
            return True
        time.sleep(0.01)
    return False

# ---------- #52 the app starts with an ANSI rules.json ----------
rules.RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
rules.RULES_FILE.write_bytes(json.dumps([{"name": "für", "enabled": True, "condition_type": "extension",
    "condition_value": "pdf", "target_folder": "X"}], ensure_ascii=False).encode("cp1252"))
try:
    app = main.SimpleOrganizerApp(); exc = None
except Exception as e:  # noqa: BLE001
    app, exc = None, e
check("#52 app starts with an ANSI rules.json", app is not None, repr(exc))
if app is None:
    print("\nFAILED:", fails); sys.exit(1)
app.update()
check("title shows the version", app.title().endswith(f"v{main.APP_VERSION}"))

# ---------- #64 default folder ----------
fresh_settings = not (APPDATA / "simple_organizer" / "settings.json").exists() or True
check("#64 default folder is the Downloads known folder",
      app._folder == utils.get_downloads_dir().resolve(), app._folder)

# ---------- #63 nested dialog keeps the grab ----------
outer = main._Overlay(app, "Outer"); outer.show(); app.update()
app.after(300, lambda: [o for o in app._overlays if o is not outer][0]._accept())
main._showwarning("Inner", "nested", parent=outer)
app.update()
check("#63 dialog underneath gets the grab back", str(app.grab_current()) == str(outer))
outer.destroy(); app.update()
check("#63 no grab left after the last dialog", app.grab_current() is None)

# ---------- #60 extension in the rule dialog ----------
def fill_rule(value):
    dlg = main._RuleDialog(app)
    dlg._name_var.set("PDFs"); dlg._ctype_var.set("extension")
    dlg._val_var.set(value); dlg._folder_var.set("Docs")
    warned = []
    def answer_warning():
        others = [o for o in app._overlays if o is not dlg]
        if others:
            warned.append(True); others[0]._accept()
    app.after(300, answer_warning)
    dlg._ok()
    app.update()
    result = dlg.result
    if dlg.winfo_exists():
        dlg.destroy()
    return result, bool(warned)
res, warned = fill_rule("*.PDF")
check("#60 *.PDF saved as pdf", res is not None and res.condition_value == "pdf" and not warned)
res, warned = fill_rule("pdf, docx")
check("#60 a list of extensions is rejected with a warning", res is None and warned)

# ---------- #58 / #59 trash: kept copies passed on, prune without disk access ----------
folder = APPDATA / "work"; folder.mkdir()
(folder / "a.bin").write_bytes(b"same"); (folder / "b.bin").write_bytes(b"same")
(folder / "c.bin").write_bytes(b"same"); (folder / "doc.txt").write_text("x")
app._set_folder(folder)
app._start_scan(confirmed=True)
pump(app, 30, lambda: app._scan_result is not None and not app._busy_flag)
pump(app, 1)
group = next(iter(app._dup_groups.values()))
by_name = {app._dup_paths[i].name: i for i in group}
app._dup_tree.selection_set([by_name["a.bin"], by_name["b.bin"]])
app.update()

captured = {}
def fake_trash(paths, log_callback=None, progress_callback=None, hwnd=None, keep=None):
    captured["keep"] = keep
    for p in paths:
        p.unlink()
    return [], len(paths)
real_trash, real_ask = main.trash_files, main._askyesno
main.trash_files, main._askyesno = fake_trash, lambda **k: True
try:
    real_exists = Path.exists
    app._confirm_and_trash()
    pump(app, 10, lambda: not app._busy_flag)
    pump(app, 0.5)
finally:
    main.trash_files, main._askyesno = real_trash, real_ask
keep = captured.get("keep") or {}
check("#58 kept copies are passed to trash_files",
      {p.name for p in keep} == {"a.bin", "b.bin"} and all([q.name for q in v] == ["c.bin"] for v in keep.values()), keep)
names = sorted(p.source.name for p in app._scan_result.plans)
check("#59 trashed files pruned from the plan", names == ["c.bin", "doc.txt"], names)
check("#59 duplicate group dissolved", app._scan_result.duplicate_groups == [])

# prune does not touch the disk
calls = []
def counting_exists(self, *a, **k):
    if folder in self.parents: calls.append(self)
    return real_exists(self, *a, **k)
Path.exists = counting_exists
try:
    app._prune_scan_result([folder / "c.bin"])
finally:
    Path.exists = real_exists
check("#59 prune checks no scanned file on the GUI thread", not calls, calls)
check("#59 prune by path works", [p.source.name for p in app._scan_result.plans] == ["doc.txt"])

app.destroy()
shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
