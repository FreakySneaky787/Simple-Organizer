#!/bin/sh
# Test the package in a clean Debian 12 (run as root in debian:bookworm, e.g. by GitHub Actions):
# structure (dpkg-deb, lintian), installation with its dependencies, start on a virtual screen,
# removal. Usage: packaging/test_deb.sh dist/simple-organizer_<version>_all.deb [screenshot.png]
set -eu
DEB=$(readlink -f "$1")
SHOT=${2:-}
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends lintian xvfb x11-apps x11-utils imagemagick xauth >/dev/null

echo "== dpkg-deb"
dpkg-deb --info "$DEB"
dpkg-deb --contents "$DEB"

echo "== lintian"
# Checks that do not fit a package built outside a Debian source tree.
lintian --tag-display-limit 0 --suppress-tags \
    no-manual-page,initial-upload-closes-no-bugs,changelog-file-missing-in-native-package,debian-changelog-file-missing-or-wrong-name \
    "$DEB" || { echo "lintian found errors"; exit 1; }

echo "== install"
apt-get install -y -qq "$DEB" >/dev/null
test -x /usr/bin/simple-organizer
test -d /usr/lib/simple-organizer/__pycache__        # postinst precompiled it
desktop-file-validate /usr/share/applications/simple-organizer.desktop 2>/dev/null || true

echo "== start"
useradd -m tester
su tester -c "xvfb-run -a -s '-screen 0 1280x860x24' sh -ec '
    simple-organizer & pid=\$!
    for i in \$(seq 1 60); do
        xwininfo -root -tree 2>/dev/null | grep -q \"Simple Organizer  v\" && break
        sleep 0.5
    done
    xwininfo -root -tree | grep \"Simple Organizer  v\" || { echo no window; exit 1; }
    sleep 2
    ${SHOT:+xwd -root -silent | convert xwd:- /tmp/shot.png}
    kill -0 \$pid
    kill \$pid
'"
LOG=/home/tester/.local/share/simple_organizer/error.log
if [ -f "$LOG" ]; then cat "$LOG"; echo "error.log written"; exit 1; fi
[ -z "$SHOT" ] || cp /tmp/shot.png "$SHOT"

echo "== scan, organize, undo, trash"
su tester -c "python3 - <<'PY'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, '/usr/lib/simple-organizer')
import organizer
work = Path(tempfile.mkdtemp())
for name in ('a.pdf', 'b.jpg', 'c.zip'):
    (work / name).write_text(name)
(work / 'dup.txt').write_text('same'); (work / 'dup2.txt').write_text('same')
result = organizer.scan_folder(work)
assert len(result.plans) == 5 and len(result.duplicate_groups) == 1, result
assert not organizer.organise_files(result.plans)
assert (work / 'Documents' / 'a.pdf').exists() and (work / 'Images' / 'b.jpg').exists()
assert not organizer.undo_last_run()
assert (work / 'a.pdf').exists() and not (work / 'Documents').exists()
errors, count = organizer.trash_files([work / 'dup2.txt'])
assert count == 1 and not errors and not (work / 'dup2.txt').exists(), errors
print('functions OK')
PY"

echo "== remove"
apt-get purge -y -qq simple-organizer >/dev/null
test ! -e /usr/lib/simple-organizer
echo "ALL OK"
