"""Export aus der Musik-Datenbank (Wunsch 10.11.2026): gefilterte Lieder flach in einen Ordner kopieren, Laufwerke am Mac zum
Auswaehlen. Nur kopieren, nie ueberschreiben, nie in den Musikordner."""
import json
import os
import sys
import tempfile
import time
import urllib.request

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp(dir=os.path.expanduser("~"), prefix=".s2l_export_test_")   # Ziel muss im Benutzerordner liegen
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import export_files as ef                    # noqa: E402
import music_serve                           # noqa: E402

MOUNT = """/dev/disk3s3 on /Volumes/Recovery (apfs, local, journaled, nobrowse)
/dev/disk4s1 on /Volumes/USB STICK (msdos, local, nodev, nosuid, noowners, noatime, fskit)
//Markus%20Nepp@nas._smb._tcp.local/music on /Volumes/music (smbfs, nodev, nosuid, mounted by markus)
/dev/disk3s1 on / (apfs, sealed, local, journaled)"""
m = ef.mounts(run=lambda: MOUNT)
check(m == {"/Volumes/USB STICK": ("msdos", "/dev/disk4s1"), "/Volumes/music": ("smbfs", "//Markus%20Nepp@nas._smb._tcp.local/music")},
      "Laufwerke aus mount, ohne versteckte (Recovery) und ohne die Systemplatte")
dl = ef.dirs("", "", run=lambda: MOUNT)
check(dl["path"] == "" and dl["drives"][-1]["kind"] == "home", "ohne Ordner: Laufwerksliste, Benutzerordner zuletzt")

music = os.path.join(tmp, "stick", "musik")
os.makedirs(os.path.join(music, "U-MUSIK", "A"))
os.makedirs(os.path.join(music, "U-MUSIK", "B"))
songs = {"U-MUSIK/A/Lied.mp3": b"a" * 3000, "U-MUSIK/B/Lied.mp3": b"b" * 4000, "U-MUSIK/A/Anders.mp3": b"c" * 100}
for rel, data in songs.items():
    with open(os.path.join(music, rel), "wb") as f:
        f.write(data)
dest = os.path.join(tmp, "party")
os.makedirs(os.path.join(dest, "Alt"))

d = ef.dirs(dest, music)
check(d["path"] == os.path.realpath(dest) and d["dirs"] == ["Alt"] and d["free"] and not d["music"], "Ordner mit Unterordnern und freiem Platz")
check(ef.dirs(os.path.join(music, "U-MUSIK"), music)["music"], "Musikordner wird erkannt")
for bad, why in ((music, "Musikordner"), (os.path.join(music, "U-MUSIK"), "darin"), (os.path.dirname(music), "darueber"), ("/etc", "ausserhalb"),
                 ("", "leer"), (os.path.join(tmp, "gibtsnicht"), "fehlt")):
    try:
        ef.check_dest(bad, music)
        check(False, "Ziel abgelehnt: " + why)
    except ValueError:
        check(True, "Ziel abgelehnt: " + why)
check(ef.check_dest(dest, music) == os.path.realpath(dest), "Ziel ausserhalb des Musikordners geht")
check(ef.mkdir(dest, "Après-Ski") == os.path.join(os.path.realpath(dest), "Après-Ski"), "neuer Ordner")
for bad in ("a/b", "..", ".x", ""):
    try:
        ef.mkdir(dest, bad)
        check(False, "Ordnername abgelehnt: " + bad)
    except ValueError:
        check(True, "Ordnername abgelehnt: " + repr(bad))

# ---- ueber den Musik-Server wie aus dem Panel ----
lib = [os.path.join(music, r) for r in songs]
srv = music_serve.MusicServer(lib, port=0, root=music)
srv.start()
base = f"http://127.0.0.1:{srv.srv.server_address[1]}"


def post(d):
    req = urllib.request.Request(base + "/export", data=json.dumps(d).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def wait():
    for _ in range(100):
        with urllib.request.urlopen(base + "/export", timeout=5) as r:
            s = json.loads(r.read())
        if s["state"] != "run":
            return s
        time.sleep(0.05)
    return s


tgt = os.path.join(dest, "Après-Ski")
check("error" in post({"op": "start", "dest": music, "paths": lib}), "Server: nicht in den Musikordner")
check("error" in post({"op": "start", "dest": tgt, "paths": ["/etc/passwd"]}), "Server: nur Dateien der Bibliothek")
r = post({"op": "start", "dest": tgt, "paths": lib + ["/fehlt.mp3"]})
check(r.get("state") == "run" and r["total"] == 3 and r["missing"] == 1, "Export startet: 3 Lieder, 1 nicht erreichbar")
s = wait()
names = sorted(x for x in os.listdir(tgt) if not x.startswith("."))
check(s["state"] == "ok" and s["copied"] == 3 and s["renamed"] == 1 and names == ["Anders.mp3", "Lied (2).mp3", "Lied.mp3"],
      "flach in einem Ordner, gleicher Name bekommt (2): " + str(names))
check(sorted(os.path.getsize(os.path.join(tgt, n)) for n in names) == [100, 3000, 4000], "Inhalt kopiert")
check(all(os.path.exists(p) for p in lib), "Originale bleiben")
r = post({"op": "start", "dest": tgt, "paths": lib})
s = wait()
check(s["copied"] == 0 and s["skipped"] == 3 and sorted(x for x in os.listdir(tgt) if not x.startswith(".")) == names,
      "zweiter Durchgang: alle schon da, auch die mit (2), nichts doppelt: " + str(s))
with urllib.request.urlopen(base + "/dirs?p=" + urllib.request.quote(dest), timeout=5) as rr:
    check(json.loads(rr.read())["dirs"] == ["Alt", "Après-Ski"], "Server: /dirs listet die Ordner")
srv.stop()

# ---- Platz und Seite ----
ex = ef.Exporter()
try:
    import shutil as _sh
    real = _sh.disk_usage
    _sh.disk_usage = lambda p: type("U", (), {"free": 10})()
    ex.start(tgt, [(lib[0], lib[0])])
    check(False, "zu wenig Platz: abgelehnt")
except ValueError as e:
    check("Platz" in str(e), "zu wenig Platz: abgelehnt, bevor kopiert wird")
finally:
    _sh.disk_usage = real
js = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
html = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
check("data-gexp=" in js and "exportDlg(g.songs, g.name)" in js and "(Array.isArray(only) ? only : view)" in js, "Export-Knopf je Gruppe: nur deren Lieder")
check('id="bexp"' in html and "$('bexp').onclick = () => exportDlg()" in js and "'/dirs?p='" in js and "exportziel" in js,
      "Musik-DB: Knopf Export, Ordnerauswahl, letzter Ordner gemerkt")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("export_files.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert export_files.py")

import shutil  # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)
finish("test_export")
