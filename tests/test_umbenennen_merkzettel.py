"""Umbenennen in "Dateien pruefen" nimmt mit, was nach Pfad gemerkt ist (Wunsch von Markus, 08.11.2026): am Mac geschaetzte
Tonart, BPM und Energie, am Pi abgelegte Cue-Punkte und die Cover-Zuordnung. Der alte Pfad bleibt gueltig, bis Mixxx den
neuen kennt. Fingerabdruck, Shows, Pegelkurven und Liedtexte haengen nicht am Dateinamen."""
import json
import os
import sys
import tempfile

from _common import PI, ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, PI)
import file_check as fc  # noqa: E402
import key_estimate as ke  # noqa: E402
from showman import covers, marks_bulk, store  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_merk_")
OLD, NEW = "/Volumes/M/U/Artists/X/03 x.mp3", "/Volumes/M/U/Artists/X/X - Lied.mp3"

# ---- Mac: Ablage je Zeile ----
kf = os.path.join(tmp, ke.KEYS_FILE)
with open(kf, "w", encoding="utf-8") as f:
    f.write(json.dumps({"path": OLD, "kid": 5, "src": "essentia", "v": ke.KEY_VERSION}) + "\n")
    f.write(json.dumps({"path": OLD, "bpm": 128.0, "bsrc": "essentia"}) + "\n")
    f.write(json.dumps({"path": "/anders.mp3", "kid": 7, "src": "essentia", "v": ke.KEY_VERSION}) + "\n")
kest = ke.KeyEstimator(base=tmp)
check(kest.key(NEW) == (0, 0), "vorher: neuer Pfad unbekannt")
check(fc.carry_jsonl(kf, OLD, NEW) == 2, "beide Zeilen (Tonart, BPM) kopiert, andere Lieder nicht")
kest.refresh()
check(kest.key(NEW) == (5, 1) and kest.bpm(NEW) == (128.0, 1), "Tonart und BPM gelten fuer den neuen Pfad")
check(kest.key(OLD) == (5, 1), "alter Pfad gilt weiter (Mixxx kennt den neuen erst nach dem Neustart der App)")
check(fc.carry_jsonl(os.path.join(tmp, "fehlt.jsonl"), OLD, NEW) == 0, "fehlende Ablage: nichts")

# ---- Bruecke ruft path_moved ----
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("renamed=fw.path_moved" in src and '"feats_path"' in src and "carry_jsonl" in src, "Bruecke: Energie, Tonart, BPM und Tags mitnehmen")

# ---- FileCheck meldet Bibliothekspfade ----
root = os.path.join(tmp, "musik")
f_old = os.path.join(root, "U/Artists/X/03 x.mp3")
os.makedirs(os.path.dirname(f_old))
open(f_old, "wb").write(b"\xff\xfb")
got = []
chk = fc.FileCheck(lambda: root, lambda: [{"path": f_old, "artist": "X", "title": "Lied"}], lambda p: p,
                   renamed=lambda a, b: got.append((a, b)))
chk.scan()
chk.thread.join(10)
r = chk.rename(f_old, "X - Lied")
check(got == [(f_old, os.path.join(root, "U/Artists/X/X - Lied.mp3"))] and r["path"] == got[0][1] and r["old_path"] == f_old,
      "Umbenennen meldet alten und neuen Pfad (an die Bruecke und an die Seite)")
fp_before = store.audio_fingerprint(got[0][1])
check(fp_before == store.audio_fingerprint(got[0][1]) and os.path.basename(got[0][1]) == "X - Lied.mp3",
      "Fingerabdruck haengt nicht am Namen")

# ---- Pi: Cue-Punkte und Cover ----
base = os.path.join(tmp, "shows")
os.makedirs(base)
mb = marks_bulk.MarksBulk(base, lambda: [], lambda: "", None)
mb._save(OLD, "X - Lied", {"drops": [10.0]})
check(mb.get(NEW) is None and mb.moved(OLD, NEW) and mb.get(NEW) == mb.get(OLD), "Cue-Punkte auch unter dem neuen Pfad")
check(not mb.moved(OLD, NEW) and not mb.moved("/gibt/es/nicht.mp3", NEW), "doppelt oder unbekannt: nichts")
cv = covers.Covers(base, lambda: [], lambda: "", None)
cv._remember(OLD, "123:0123456789abcdef")
check(cv.moved(OLD, NEW) and cv.index[NEW] == "123:0123456789abcdef", "Cover-Zuordnung mitgenommen")
cv2 = covers.Covers(base, lambda: [], lambda: "", None)
check(cv2.index.get(NEW) == "123:0123456789abcdef" and cv2.index.get(OLD) == "123:0123456789abcdef", "nach einem Neustart noch da, alter Pfad bleibt")
check(not cv.moved("/ohne.mp3", "/neu.mp3"), "ohne Cover: nichts")
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
js = open(os.path.join(PI, "static", "sm", "check.js"), encoding="utf-8").read()
check('op == "path_moved"' in api and "SM.cmd('path_moved'" in js, "Seite meldet die Umbenennung an den Pi")
finish("test_umbenennen_merkzettel")
