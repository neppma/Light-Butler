"""Musik-Datenbank: Solange die Bibliothek vom Mac nicht ganz da ist, mischt der Pi neue Stuecke mit der Ablage.
Fehlerbericht von Markus (06.11.2026): "Abba - Dancing Queen" liegt zweimal am Stick (U-MUSIK und OLDIES, 230,5 s und
230,4 s); beide Zeilen zeigten den Ordner OLDIES, weil der Pi nach Titel und Laenge auf ganze Sekunden mischte."""
import json
import os
import tempfile

from _common import check, finish

from mixxx_link import MixxxLink

U = "/Volumes/USB STICK/musik/U-MUSIK/Artists/Abba/Abba - Dancing Queen.mp3"
O = "/Volumes/USB STICK/musik/OLDIES/Artists/Abba/Abba - Dancing Queen.mp3"


def item(dur, path, kbps=0):  # noqa: E302
    return ["Abba - Dancing Queen", dur, "Abba", "Dancing Queen", 101.0, "Am", 0, "", 0, os.path.basename(path), 0, 1, path, kbps]


tmp = tempfile.mkdtemp(prefix="s2l_mix_")
p = os.path.join(tmp, "_mixxx_bibliothek.json")
with open(p, "w", encoding="utf-8") as f:
    json.dump([item(230.5, U), item(230.4, O), ["Zz - Rest", 100.0, "Zz", "Rest", 0, "", 0, "", 0, "r.mp3", 0, 0, "/x/r.mp3"]], f)
link = MixxxLink(0)
link.persist(p)
check(sorted(x["path"] for x in link.library_full())[:2] == sorted([O, U]), "Ablage: beide Fassungen mit eigenem Pfad")

# erstes von zwei Stuecken kommt an (mit Bitrate), das zweite fehlt noch
link.feed({"type": "lib", "i": 0, "n": 2, "t": [item(230.5, U, 320), item(230.4, O, 320)]}, 1.0)
full = link.library_full()
paths = [x["path"] for x in full]
check(not link.library_complete(), "Bibliothek noch nicht vollstaendig")
check(sorted(paths) == sorted([O, U, "/x/r.mp3"]), "beide Fassungen bleiben getrennt, nichts doppelt, Rest aus der Ablage: %s" % paths)
check(all(x["kbps"] == 320 for x in full if x["path"] in (O, U)), "beide mit den neuen Feldern (Bitrate)")

# alte Ablage ohne Pfad (aeltere Bruecke): dann wie bisher nach Titel und Laenge zuordnen, ohne Doppelte
p2 = os.path.join(tmp, "alt.json")
with open(p2, "w", encoding="utf-8") as f:
    json.dump([["Abba - Dancing Queen", 230.5], ["Abba - Dancing Queen", 230.4]], f)
l2 = MixxxLink(0)
l2.persist(p2)
l2.feed({"type": "lib", "i": 0, "n": 2, "t": [item(230.5, U, 320), item(230.4, O, 320)]}, 1.0)
f2 = l2.library_full()
check(len(f2) == 2 and sorted(x["path"] for x in f2) == sorted([O, U]), "Ablage ohne Pfad: neue Stuecke ersetzen sie, keine Doppelten")

# Fehlerbericht 06.11.2026 (Zustand: 28 Bilder/s, Aussetzer): nach dem ersten vollstaendigen Durchgang schrieb der Pi bei
# JEDEM weiteren Stueck die ganze Bibliothek (json.dumps und Pruefsumme ueber 9000 Lieder, am Pi rund 200 ms ohne Pause).
l3 = MixxxLink(0)
l3.persist(os.path.join(tmp, "runden.json"))
calls = []
orig = l3._save_lib
l3._save_lib = lambda: (calls.append(1), orig())[1]
for rnd in range(3):
    for i in range(4):
        l3.feed({"type": "lib", "i": i, "n": 4, "t": [item(200.0 + i, "/m/%d.mp3" % i, rnd)]}, 1.0)
check(len(calls) == 3, "je Durchgang der Bruecke einmal speichern, nicht bei jedem Stueck: %d" % len(calls))
l4 = MixxxLink(0)
l4.persist(os.path.join(tmp, "mitten.json"))
c4 = []
o4 = l4._save_lib
l4._save_lib = lambda: (c4.append(1), o4())[1]
for i in (2, 3, 0, 1):                                            # Pi startet mitten in einem Durchgang
    l4.feed({"type": "lib", "i": i, "n": 4, "t": [item(200.0 + i, "/m/%d.mp3" % i)]}, 1.0)
check(len(c4) == 1 and l4.library_complete(), "Start mitten im Durchgang: gespeichert, sobald alle Stuecke da sind")
with open(os.path.join(tmp, "runden.json"), encoding="utf-8") as f:
    saved = json.load(f)
check(len(saved) == 4 and saved[0][13] == 2, "Ablage hat den Stand des letzten Durchgangs")
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi", "mixxx_link.py"), encoding="utf-8").read()
check("json.dumps([list(x.values()) for x in" not in src, "nie die ganze Bibliothek in einem Stueck umwandeln (haelt die Show-Schleife an)")
import sys  # noqa: E402
from showman import api as _api  # noqa: E402


class _H:
    def _send(self, code, body, ct):
        self.body = body


for _d in ({"connected": True, "tracks": [{"t": "Küss’ die Hand"}, {"n": 2}], "n": 2}, {"tracks": []}):
    _h = _H()
    _api._json_list(_h, _d, "tracks")
    check(json.loads(_h.body) == _d, "Musik-Datenbank: Antwort Lied fuer Lied, gleicher Inhalt")
_asrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi", "showman", "api.py"), encoding="utf-8").read()
check('_json_list(h, mgr.music_list(), "tracks")' in _asrc, "/api/musik wird stueckweise umgewandelt")
# Fehlersuche 06.11.2026 (Spuerhund): bis 140 ms je Bild, die Show-Schleife wartete in status() auf die Sperre, waehrend das
# Panel die Bibliothek (9000 Lieder) zusammenstellte. Jetzt nur eine Momentaufnahme unter der Sperre, Ergebnis zwischengespeichert.
import threading  # noqa: E402
import time  # noqa: E402
import mixxx_link as _ml  # noqa: E402
l5 = MixxxLink(0)
l5.feed({"type": "lib", "i": 0, "n": 2, "t": [item(200.0, "/m/a.mp3")]}, 1.0)
a1 = l5.library_full()
check(l5.library_full() is a1, "ohne neues Stueck: zwischengespeichert, nicht neu gemischt")
l5.feed({"type": "lib", "i": 1, "n": 2, "t": [item(201.0, "/m/b.mp3")]}, 1.0)
check(len(l5.library_full()) == 2 and l5.library_full() is not a1, "neues Stueck: neu gemischt")
_orig = _ml._merge_library
_ml._merge_library = lambda *a: (time.sleep(0.3), _orig(*a))[1]
l5.feed({"type": "lib", "i": 0, "n": 3, "t": [item(202.0, "/m/c.mp3")]}, 1.0)
th = threading.Thread(target=l5.library_full)
th.start()
time.sleep(0.05)
t0 = time.perf_counter()
l5.status(time.time(), {"mixxx_stale_s": 5.0, "mixxx_shift_s": 0.0, "mixxx_cue_snap_s": 0.0, "mixxx_drop_min": 0.5, "mixxx_lift_min": 0.5,
                        "mixxx_pause_idle": 1.0})
dt = time.perf_counter() - t0
th.join()
_ml._merge_library = _orig
check(dt < 0.05, "Show-Schleife wartet nicht, waehrend die Bibliothek gemischt wird (%.0f ms)" % (dt * 1000))
finish("test_bibliothek_mischen")
