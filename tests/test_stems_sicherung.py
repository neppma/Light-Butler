"""Spur-Kurven auf den USB-Stick sichern (Wunsch von Markus, 06.11.2026): Ordner Backup/Light-Butler-Kurven neben dem
Musikordner, nur neue Dateien, nie loeschen, Zurueckspielen an den Pi mit Pruefung."""
import base64
import io
import json
import os
import sys
import tempfile
import urllib.parse

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import stems_backup as sb  # noqa: E402
from showman import store as st  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_sich_")


def data(fp, dur=5.0):
    c = base64.b64encode(bytes(int(dur * st.STEM_RATE))).decode()
    return {"v": 1, "rate": st.STEM_RATE, "db_min": -60, "duration": dur, "offset_ms": 0.0, "corr": None, "fp": fp, "model": "htdemucs",
            "created": "x", "curves": {k: c for k in st.STEM_CURVES}}


pi = st.ShowStore(os.path.join(tmp, "pi"))
FPS = ["11:0123456789abcdef", "22:fedcba9876543210"]
for fp in FPS:
    pi.save_stems_fp(fp, data(fp))
check([f[0] for f in pi.stems_files()] == sorted(FPS) and all(f[1] > 0 for f in pi.stems_files()), "Pi: Liste mit Groesse")
check(pi.stems_raw(FPS[0]) is not None and pi.stems_raw("../../show") is None and pi.stems_raw("1:2") is None, "Pi: nur gueltige Fingerabdruecke")


class R(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(store):
    def op(req, timeout=0):
        if not isinstance(req, str):                              # POST /api/sm/cmd (Zurueckspielen)
            d = json.loads(req.data.decode())
            try:
                store.save_stems_fp(d["fp"], d["data"])
                return R(b"{}")
            except ValueError as e:
                return R(json.dumps({"error": str(e)}).encode())
        u = urllib.parse.urlparse(req)
        if u.path == "/api/sm/stems_list":
            return R(json.dumps({"files": store.stems_files()}).encode())
        if u.path == "/api/sm/stems_file":
            raw = store.stems_raw(urllib.parse.parse_qs(u.query)["fp"][0])
            if raw is None:
                raise OSError("404")
            return R(raw)
        raise OSError("unbekannt " + req)
    return op


stick = os.path.join(tmp, "USB STICK")
music = os.path.join(stick, "musik")
os.makedirs(music)
dest = sb.dest_for(music + "/")
check(dest == os.path.join(stick, "musik-backup", "Light-Butler-Kurven"), "Ordner neben dem Musikordner: musik-backup/Light-Butler-Kurven")
check(sb.dest_for(os.path.join(tmp, "abgezogen", "musik")) == "" and sb.dest_for("") == "", "Stick nicht da oder kein Musikordner: nichts")
check(sb.sync("http://pi:8080", dest, opener_for(pi)) == (2, 2) and sorted(os.listdir(dest)) == sorted(sb.fname(f) for f in FPS), "erste Sicherung: alle Dateien")
check(sb.sync("http://pi:8080", dest, opener_for(pi)) == (0, 2), "zweite Sicherung: nichts Neues, nichts kopiert")
pi.save_stems_fp(FPS[0], data(FPS[0], dur=7.0))
pi.save_stems_fp("33:00000000000000aa", data("33:00000000000000aa"))
check(sb.sync("http://pi:8080", dest, opener_for(pi)) == (2, 3), "geaenderte und neue Dateien kommen nach")
open(os.path.join(dest, "zz_eigene_notiz.txt"), "w").write("bleibt")
os.remove(pi._stems_path("33:00000000000000aa"))
sb.sync("http://pi:8080", dest, opener_for(pi))
check(os.path.isfile(os.path.join(dest, sb.fname("33:00000000000000aa"))) and os.path.isfile(os.path.join(dest, "zz_eigene_notiz.txt")),
      "auf dem Stick wird nie etwas geloescht")

# ---- Zurueckspielen ----
neu = st.ShowStore(os.path.join(tmp, "neuer_pi"))
with open(os.path.join(dest, "44_" + "b" * 16 + ".json"), "w") as f:
    json.dump(data("55:" + "c" * 16), f)                            # Inhalt passt nicht zum Namen
out = []
ok, bad = sb.restore("http://pi:8080", dest, opener_for(neu), out.append)
check(ok == 3 and bad == 1 and sorted(neu.stems_fps()) == sorted(FPS + ["33:00000000000000aa"]), "Zurueckspielen: gute kommen an, falsche lehnt der Pi ab")
check(neu.load_stems is not None and json.loads(neu.stems_raw(FPS[0]))["duration"] == 7.0, "Inhalt unveraendert")

# ---- Waechter in der Bruecke ----
logs = []
k = sb.Keeper("http://pi:8080", lambda: music, log=logs.append, opener=opener_for(pi))
check(k.once() == (0, 2), "Waechter gleicht ab")
k2 = sb.Keeper("http://pi:8080", lambda: os.path.join(tmp, "weg", "musik"), log=logs.append, opener=opener_for(pi))
check(k2.once() is None, "ohne Stick: still nichts")


def down(req, timeout=0):
    raise OSError("Pi aus")


k3 = sb.Keeper("http://pi:8080", lambda: music, log=logs.append, opener=down)
k3.once(); k3.once()
check(sum("nicht erreichbar" in x for x in logs) == 1, "Pi aus: nur einmal gemeldet")

src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "stems_backup.py"), encoding="utf-8").read()
check("os.remove" not in src and "rmtree" not in src and "unlink" not in src, "das Programm loescht nie")
br = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("Keeper(" in br and "lambda: ms.loc.root" in br, "Bruecke startet die Sicherung mit dem Musikordner")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check('"$HERE/stems_backup.py"' in inst, "Installer kopiert stems_backup.py")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('"/api/sm/stems_list"' in api and '"/api/sm/stems_file"' in api and 'op == "stems_restore"' in api, "Pi: Liste, Datei, Zurueckspielen")
# ---- Cue-Punkte (Wunsch von Markus: sicher am Stick, auch wenn er Mixxx einmal nicht mehr verwendet) ----
from showman import marks_bulk as mbk  # noqa: E402
cue_pi = mbk.MarksBulk(os.path.join(tmp, "pi"), lambda: [], lambda: "", None)
cue_pi._save("/m/eins.mp3", "A - Eins", {"se": [["intro", 0, 20]], "cu": [5.0], "ev": [], "en": [], "lvl": 6, "genre": "Pop", "title": "A - Eins", "fp": ""})
cue_pi._save("/m/zwei.mp3", "B - Zwei", {"se": [], "cu": [7.0], "ev": [], "en": [], "lvl": None, "genre": "", "title": "B - Zwei", "fp": ""})
check(len(cue_pi.files()) == 2 and cue_pi.raw("../x") is None and cue_pi.raw(cue_pi.files()[0][0]) is not None, "Pi: Liste und Dateien, keine Pfade von aussen")


def cue_opener(mb):
    def op(req, timeout=0):
        if not isinstance(req, str):
            d = json.loads(req.data.decode())
            try:
                mb.restore(d["f"], d["data"])
                return R(b"{}")
            except ValueError as e:
                return R(json.dumps({"error": str(e)}).encode())
        u = urllib.parse.urlparse(req)
        if u.path == "/api/sm/marks_list":
            return R(json.dumps({"files": mb.files()}).encode())
        if u.path == "/api/sm/marks_file":
            raw = mb.raw(urllib.parse.parse_qs(u.query)["f"][0])
            if raw is None:
                raise OSError("404")
            return R(raw)
        raise OSError("unbekannt " + req)
    return op


cdest = sb.dest_for(music, sb.CUES_FOLDER)
check(cdest == os.path.join(stick, "musik-backup", "Light-Butler-Cues"), "Ordner musik-backup/Light-Butler-Cues neben dem Musikordner")
check(sb.sync_cues("http://pi:8080", cdest, cue_opener(cue_pi)) == (2, 2) and sb.sync_cues("http://pi:8080", cdest, cue_opener(cue_pi)) == (0, 2),
      "Cues auf den Stick, beim zweiten Mal nichts Neues")
one = json.load(open(os.path.join(cdest, sorted(os.listdir(cdest))[0]), encoding="utf-8"))
check(one["path"].startswith("/m/") and "cu" in one["marks"] and one["title"], "lesbar: Pfad, Titel und Cue-Punkte stehen in der Datei")
neu_pi = mbk.MarksBulk(os.path.join(tmp, "neuer_pi2"), lambda: [], lambda: "", None)
with open(os.path.join(cdest, "0" * 24 + ".json"), "w") as f:
    json.dump({"path": "/m/falsch.mp3", "marks": {}}, f)          # Name passt nicht zum Pfad
okc, badc = sb.restore_cues("http://pi:8080", cdest, cue_opener(neu_pi), out.append)
check(okc == 2 and badc == 1 and neu_pi.get("/m/eins.mp3")["cu"] == [5.0], "Zurueckspielen: gute kommen an, falsche lehnt der Pi ab")
k4 = sb.Keeper("http://pi:8080", lambda: music, log=logs.append, opener=lambda req, timeout=0: (opener_for(pi) if "stems" in str(req) else cue_opener(cue_pi))(req, timeout))
cue_pi._save("/m/drei.mp3", "C - Drei", {"se": [], "cu": [9.0], "ev": [], "en": [], "lvl": None, "genre": "", "title": "C - Drei", "fp": ""})
k4.once()
check(os.path.isfile(os.path.join(cdest, mbk._fname("/m/drei.mp3"))), "Bruecke sichert Kurven und Cues im selben Durchgang (neue Cue-Datei angekommen)")
api2 = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('"/api/sm/marks_list"' in api2 and '"/api/sm/marks_file"' in api2 and 'op == "marks_restore"' in api2, "Pi: Liste, Datei, Zurueckspielen der Cues")
# Ordner heisst musik-backup wie musik-import (Wunsch 13.11.2026): die alte Sicherung "Backup" zieht von selbst um
mv = os.path.realpath(tempfile.mkdtemp())
os.makedirs(os.path.join(mv, "musik"))
for sub, f in (("Light-Butler-Kurven", "a.json"), ("Light-Butler-Cues", "b.json"), ("Light-Butler-Covers", "c.jpg")):
    os.makedirs(os.path.join(mv, "Backup", sub))
    open(os.path.join(mv, "Backup", sub, f), "w").write("x")
n = sb.move_old(os.path.join(mv, "musik"), log=lambda t: None)
check(n == 3 and not os.path.exists(os.path.join(mv, "Backup")) and os.path.isfile(os.path.join(mv, "musik-backup", "Light-Butler-Cues", "b.json"))
      and os.path.isfile(os.path.join(mv, "musik-backup", "Light-Butler-Covers", "c.jpg")), "Backup -> musik-backup umbenannt, leerer alter Ordner weg")
check(sb.move_old(os.path.join(mv, "musik"), log=lambda t: None) == 0, "zweites Mal: nichts zu tun")
os.makedirs(os.path.join(mv, "Backup", "Light-Butler-Kurven"))
open(os.path.join(mv, "Backup", "Light-Butler-Kurven", "a.json"), "w").write("alt")
open(os.path.join(mv, "Backup", "Light-Butler-Kurven", "neu.json"), "w").write("y")
open(os.path.join(mv, "Backup", "Steuer.pdf"), "w").write("eigen")
n = sb.move_old(os.path.join(mv, "musik"), log=lambda t: None)
check(n == 1 and open(os.path.join(mv, "musik-backup", "Light-Butler-Kurven", "a.json")).read() == "x"
      and os.path.isfile(os.path.join(mv, "musik-backup", "Light-Butler-Kurven", "neu.json")) and os.path.isfile(os.path.join(mv, "Backup", "Steuer.pdf"))
      and os.path.isfile(os.path.join(mv, "Backup", "Light-Butler-Kurven", "a.json")),
      "zusammenfuehren: Neues bleibt, Fehlendes kommt dazu, nichts wird geloescht, eigene Dateien bleiben")
check(sb.move_old(os.path.join(mv, "fehlt"), log=lambda t: None) == 0, "ohne Musikordner: nichts")

# Spiegeln nimmt musik-backup mit: am Ersatzstick neben dem Musikordner, auf der NAS im Ordner
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import nas_mirror as nm  # noqa: E402
names = [x for x, _p in nm.sources(os.path.join(mv, "musik"))]
check("musik-backup" in names and nm.BESIDE == ("musik-import", "musik-backup", "Light-Butler-Programme"), "Spiegeln: musik-backup in der Ordnerliste")
mmr = nm.Mirror(lambda: os.path.join(mv, "musik"))
mmr.vol_of = lambda p: mv if p.startswith(mv) else ("/Volumes/X" if p.startswith("/Volumes/X") else p)
it = {n_: t for n_, _s, t in mmr.items(os.path.join(mv, "musik"), "/Volumes/X/musik")}
it2 = {n_: t for n_, _s, t in mmr.items(os.path.join(mv, "musik"), "/Volumes/music")}
check(it["musik-backup"] == "/Volumes/X/musik-backup" and it2["musik-backup"] == "/Volumes/music/musik-backup",
      "Ersatzstick: neben dem Musikordner; NAS (Freigabe = Musik): im Ordner")
finish("test_stems_sicherung")
