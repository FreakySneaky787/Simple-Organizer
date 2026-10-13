"""Build the Debian package simple-organizer_<version>_all.deb.

    python packaging/build_deb.py            -> dist/simple-organizer_<version>_all.deb

Pure Python (no dpkg-deb needed), so it runs on Windows and Linux alike, and the
result is reproducible: every file gets the time of SOURCE_DATE_EPOCH (default:
the last commit, else a fixed date) and root ownership.

Layout:
  /usr/lib/simple-organizer/       the program (.py files, icon.png)
  /usr/bin/simple-organizer        start script
  /usr/share/applications/         menu entry
  /usr/share/icons/hicolor/256x256/apps/simple-organizer.png
  /usr/share/doc/simple-organizer/ copyright, changelog
The package needs only python3 (>= 3.10) and python3-tk -- Debian 12 has 3.11.
"""
import gzip
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = "simple-organizer"
PROGRAM_FILES = ("main.py", "organizer.py", "rules.py", "utils.py", "config.py",
                 "scheduler.py", "theme.py", "icons.py", "icon.png")
HOMEPAGE = "https://github.com/FreakySneaky787/Simple-Organizer"


def app_version() -> str:
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', (REPO / "main.py").read_text(encoding="utf-8"), re.M)
    if not match:
        sys.exit("APP_VERSION not found in main.py")
    return match.group(1)


def build_time() -> int:
    if os.environ.get("SOURCE_DATE_EPOCH", "").isdigit():
        return int(os.environ["SOURCE_DATE_EPOCH"])
    try:
        out = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%ct"],
                             capture_output=True, text=True, check=True).stdout.strip()
        return int(out)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 1767225600   # 2026-01-01


LAUNCHER = f"""#!/bin/sh
# Simple Organizer -- {HOMEPAGE}
exec python3 /usr/lib/{PACKAGE}/main.py "$@"
"""

DESKTOP = f"""[Desktop Entry]
Type=Application
Name=Simple Organizer
GenericName=File Organizer
Comment=Sort the files of a folder into category folders, with preview and undo
Exec={PACKAGE}
Icon={PACKAGE}
Terminal=false
Categories=Utility;FileTools;
Keywords=organize;organise;sort;files;folder;downloads;duplicates;
"""

# The program is precompiled after installation; the bytecode is not part of
# the package (it depends on the Python version) and is removed with it.
POSTINST = f"""#!/bin/sh
set -e
if [ "$1" = "configure" ] && command -v python3 >/dev/null 2>&1; then
    python3 -m compileall -q /usr/lib/{PACKAGE} >/dev/null 2>&1 || true
fi
"""

PRERM = f"""#!/bin/sh
set -e
rm -rf /usr/lib/{PACKAGE}/__pycache__
"""


def copyright_text() -> str:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    license_part = readme.split("## License", 1)[1].strip() if "## License" in readme else "MIT License"
    return ("Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n"
            f"Upstream-Name: Simple Organizer\nSource: {HOMEPAGE}\n\n"
            "Files: *\nLicense: MIT\n\n"
            + "\n".join(" " + (line if line.strip() else ".") for line in license_part.splitlines()) + "\n")


def changelog(version: str, when: int) -> bytes:
    from email.utils import formatdate
    text = (f"{PACKAGE} ({version}) stable; urgency=medium\n\n"
            f"  * Simple Organizer {version}. Release notes:\n"
            f"    {HOMEPAGE}/releases/tag/v{version}\n\n"
            f" -- Simple Organizer <simple-organizer@users.noreply.github.com>  "
            f"{formatdate(when)}\n")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=when, compresslevel=9, filename="") as gz:
        gz.write(text.encode("utf-8"))
    return buf.getvalue()


def tar_bytes(entries: list[tuple[str, bytes | None, int]], when: int) -> bytes:
    """A gzip'd tar of (path, data or None for a folder, mode), owned by root."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for path, data, mode in entries:
            info = tarfile.TarInfo("./" + path if path else ".")
            info.mtime, info.mode = when, mode
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            if data is None:
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=when, compresslevel=9, filename="") as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def ar_archive(members: list[tuple[str, bytes]], when: int) -> bytes:
    out = bytearray(b"!<arch>\n")
    for name, data in members:
        out += (f"{name + '/':<16}{when:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n").encode("ascii")
        out += data
        if len(data) % 2:
            out += b"\n"
    return bytes(out)


def build() -> Path:
    version, when = app_version(), build_time()
    files: dict[str, tuple[bytes, int]] = {}
    for name in PROGRAM_FILES:
        files[f"usr/lib/{PACKAGE}/{name}"] = ((REPO / name).read_bytes(), 0o644)
    files[f"usr/bin/{PACKAGE}"] = (LAUNCHER.encode(), 0o755)
    files[f"usr/share/applications/{PACKAGE}.desktop"] = (DESKTOP.encode(), 0o644)
    files[f"usr/share/icons/hicolor/256x256/apps/{PACKAGE}.png"] = ((REPO / "icon.png").read_bytes(), 0o644)
    files[f"usr/share/doc/{PACKAGE}/copyright"] = (copyright_text().encode(), 0o644)
    files[f"usr/share/doc/{PACKAGE}/changelog.gz"] = (changelog(version, when), 0o644)

    dirs = sorted({str(Path(p).parent.as_posix()) for p in files}
                  | {"/".join(Path(p).parts[:i]) for p in files for i in range(1, len(Path(p).parts))})
    data_entries = [("", None, 0o755)] + [(d, None, 0o755) for d in dirs if d and d != "."]
    data_entries += [(p, data, mode) for p, (data, mode) in sorted(files.items())]

    installed_kb = (sum(len(d) for d, _ in files.values()) + 1023) // 1024
    control = (f"Package: {PACKAGE}\nVersion: {version}\nArchitecture: all\n"
               "Maintainer: Simple Organizer <simple-organizer@users.noreply.github.com>\n"
               f"Installed-Size: {installed_kb}\n"
               "Depends: python3 (>= 3.10), python3-tk\n"
               "Recommends: libglib2.0-bin\n"
               "Section: utils\nPriority: optional\n"
               f"Homepage: {HOMEPAGE}\n"
               "Description: sort the files of a folder into category folders\n"
               " Simple Organizer sorts files into folders such as Images, Documents or\n"
               " Archives. A scan shows what would move before anything happens; every run\n"
               " can be undone. It finds duplicates, has your own rules, a staging mode and\n"
               " an automatic schedule. Files are never deleted or overwritten.\n")
    md5sums = "".join(f"{hashlib.md5(data).hexdigest()}  {p}\n" for p, (data, _) in sorted(files.items()))
    control_entries = [("", None, 0o755), ("control", control.encode(), 0o644),
                       ("md5sums", md5sums.encode(), 0o644),
                       ("postinst", POSTINST.encode(), 0o755), ("prerm", PRERM.encode(), 0o755)]

    deb = ar_archive([("debian-binary", b"2.0\n"),
                      ("control.tar.gz", tar_bytes(control_entries, when)),
                      ("data.tar.gz", tar_bytes(data_entries, when))], when)
    out = REPO / "dist" / f"{PACKAGE}_{version}_all.deb"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(deb)
    return out


if __name__ == "__main__":
    path = build()
    print(f"{path}  {path.stat().st_size / 1024:.0f} KB  sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}")
