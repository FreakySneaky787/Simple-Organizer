# Tests

Regression tests for every release since v3.4.2 — one core suite (`test_v*.py`, no window)
and one GUI suite (`test_gui_v*.py`, drives the real app) per release.

```bat
py tests\run_all.py
```

- Only temporary folders and a temporary `APPDATA` are used; your files and settings are not touched.
- Written for **Windows** (Recycle Bin, junctions, read-only attributes, known folders).
- The GUI suites open the app window for a few seconds — don't type while they run.
- GitHub Actions runs them on every push (Python 3.11 and the newest Python).
