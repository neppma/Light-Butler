"""Der Name ist Light-Butler (15.11.2026). Seit 16.11.2026 steht der fruehere Name nirgends mehr, auch nicht im Programmcode:
Datenordner ~/Light-Butler-Daten, App Light-Butler Mixxx, Sicherungen light-butler-mac-*, Windows-Aufgabe Light-Butler."""
import os
import re
import subprocess
import sys
import tempfile

from _common import check, finish

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import backup_mac   # noqa: E402
import pfad   # noqa: E402

env = os.environ.pop("S2L_DATA", None)
try:
    with tempfile.TemporaryDirectory() as h:
        check(pfad.daten(h) == os.path.join(h, "Light-Butler-Daten"), "Datenordner ~/Light-Butler-Daten")
finally:
    if env is not None:
        os.environ["S2L_DATA"] = env
os.environ["S2L_DATA"] = "/x/y"
check(pfad.daten() == "/x/y", "S2L_DATA geht vor")
if env is not None:
    os.environ["S2L_DATA"] = env
else:
    os.environ.pop("S2L_DATA", None)

with tempfile.TemporaryDirectory() as d:
    for n in ("light-butler-mac-2026-11-15_100000.zip", "light-butler-mac-2026-11-01_100000.zip", "anderes.zip"):
        open(os.path.join(d, n), "w").write("x")
    check([os.path.basename(p) for p in backup_mac._items(d)] == ["light-butler-mac-2026-11-01_100000.zip", "light-butler-mac-2026-11-15_100000.zip"],
          "Mac-Sicherung: Zips nach Datum")

il = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check('APP="$HOME/Applications/Light-Butler Mixxx.app"' in il and 'BASE="${S2L_DATA:-$HOME/Light-Butler-Daten}"' in il, "App Light-Butler Mixxx")
mb = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check('DEFAULT_PORT = "Light-Butler" if sys.platform == "win32"' in mb, "loopMIDI-Anschluss Light-Butler")
st = open(os.path.join(ROOT, "mac", "stems", "install_stems.ps1"), encoding="utf-8").read()
check('$Task = "Light-Butler Pegelkurven"' in st, "Windows-Aufgabe Light-Butler Pegelkurven")
sys.path.insert(0, os.path.join(ROOT, "pi"))
import audio_net   # noqa: E402
check(audio_net.NET_NAME == "Musik-Rechner (Netzwerk)" and audio_net.net_alias("Mac (Netzwerk)") == audio_net.NET_NAME
      and audio_net.net_alias("USB") == "USB", "Audio-Eingang: neuer Name, gespeicherter alter Name wirkt weiter")

# frueherer Name nirgends in Git (ausser den eigenen, nie veroeffentlichten Dateien)
OLD = re.compile("sound ?2 ?light|sound to " "light", re.I)
private = ("CLAUDE" ".md", "docs/archiv/", "docs/MEINE_ANLAGE.md", "docs/WINDOWS_PORT.md", "docs/ENTWICKLUNGSNOTIZEN.md")
r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
hits = []
for f in (r.stdout.splitlines() if r.returncode == 0 else []):
    if f.startswith(private) or not os.path.isfile(os.path.join(ROOT, f)):
        continue
    try:
        if OLD.search(open(os.path.join(ROOT, f), encoding="utf-8").read()):
            hits.append(f)
    except (UnicodeDecodeError, OSError):
        pass
check(not hits, "frueherer Name kommt nicht mehr vor: " + str(hits[:5]))
finish("test_neuer_name")
