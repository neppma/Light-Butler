"""Interpret aendern oder leeren (Seite Interpreten, Wunsch 13.11.2026, etwa "Konrad" bei den Samples): schreibt der Musik-Rechner
ueber den Genre-Editor (TPE1 statt TCON), nur MP3s, "feat. ..." bleibt, mit Protokoll und Zuruecknehmen."""
import os
import sys
import tempfile
import time

from _common import ROOT, check, finish

tmp = os.path.realpath(tempfile.mkdtemp())
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import genre_edit as ge  # noqa: E402

files = {}
for n in ("a.mp3", "b.mp3", "c.mp3", "d.wav"):
    p = os.path.join(tmp, n)
    open(p, "wb").write(b"x")
    files[n] = p
LIB = [{"path": files["a.mp3"], "artist": "Konrad", "title": "Ansage 1", "genre": "Sample"},
       {"path": files["b.mp3"], "artist": "Konrad feat. Mediamarkt", "title": "Ansage 2", "genre": "Sample"},
       {"path": files["c.mp3"], "artist": "Falco", "title": "Jeanny", "genre": "Pop"},
       {"path": files["d.wav"], "artist": "Konrad", "title": "Ansage 3", "genre": "Sample"}]
written, told = [], []


def write(f, fields):
    written.append((os.path.basename(f), dict(fields)))
    for r in LIB:
        if r["path"] == f:
            r.update(fields)


def wait(e):
    for _ in range(200):
        if (e.job_status() or {}).get("state") == "done":
            return
        time.sleep(0.02)


E = ge.GenreEditor(lambda: LIB, lambda p: p, lambda: tmp, write=write, on_written=lambda p, f: told.append(f))
res = E.set_artist([files["a.mp3"], files["b.mp3"], files["d.wav"]], "Konrad", "Sprecher")
wait(E)
check(res["total"] == 2 and written == [("a.mp3", {"artist": "Sprecher"}), ("b.mp3", {"artist": "Sprecher feat. Mediamarkt"})],
      "nur MP3s, \"feat. ...\" bleibt: " + str(written))
check(told == [{"artist": "Sprecher"}, {"artist": "Sprecher feat. Mediamarkt"}] and LIB[2]["artist"] == "Falco", "andere Lieder unberuehrt, Liste wird gemerkt")
h = E.history()[0]
check(h["field"] == "artist" and h["items"][0][1] == "Konrad" and h["items"][1][1] == "Konrad feat. Mediamarkt", "Protokoll mit Feld und alten Namen")
written.clear()
E.undo(h["id"])
wait(E)
check(written == [("a.mp3", {"artist": "Konrad"}), ("b.mp3", {"artist": "Konrad feat. Mediamarkt"})] and E.history()[1]["undone"],
      "Zuruecknehmen schreibt die alten Namen ins Feld Interpret (nicht ins Genre)")
written.clear()
E.set_artist([files["a.mp3"]], "Konrad", "")
wait(E)
check(written == [("a.mp3", {"artist": ""})], "leer = Interpret entfernen")
try:
    E.set_artist([files["d.wav"]], "Konrad", "X")
    check(False, "nur WAV: abgelehnt")
except ValueError:
    check(True, "ohne MP3: abgelehnt mit Meldung")
# Lied steht bei mehreren (Bach & Glenn Gould): bei Glenn Gould nur dessen Teil, leeren nie den ganzen Eintrag
LIB.append({"path": files["c.mp3"].replace("c.mp3", "e.mp3"), "artist": "Johann Sebastian Bach & Glenn Gould", "title": "Aria", "genre": "Klassik"})
open(LIB[-1]["path"], "wb").write(b"x")
written.clear()
E.set_artist([LIB[-1]["path"]], "Glenn Gould", "Glenn Herbert Gould")
wait(E)
check(written == [("e.mp3", {"artist": "Johann Sebastian Bach & Glenn Herbert Gould"})], "nur der eigene Teil des gemeinsamen Eintrags: " + str(written))
try:
    E.set_artist([LIB[-1]["path"]], "Glenn Herbert Gould", "")
    check(False, "leeren bei gemeinsamem Eintrag abgelehnt")
except ValueError:
    check(True, "leeren nimmt nie den ganzen gemeinsamen Eintrag weg")
written.clear()
E.rename(["Sample"], "Samples")
wait(E)
check(written and all(f == {"genre": "Samples"} for _n, f in written), "Genre umbenennen schreibt weiter nur das Genre")
# Fehlerbericht 13.11.2026: Interpret geleert (Media Markt), nach dem naechsten Einlesen der Ordner-Liste kam er aus Mixxx zurueck
import mixxx_bridge as mb  # noqa: E402
from folder_lib import tail  # noqa: E402
P = "/Volumes/USB STICK/musik/TESTSAMPLES/UHR.MP3"
fw = mb.Forwarder([{"path": P, "duration": 3.0, "artist": "Media Markt", "title": "Uhr", "genre": "Sample"}], None, None,
                  analysis_dir=os.path.join(tmp, "an"), analyze=False)
fw.tags_written(P, {"artist": ""})
fw.folder = type("F", (), {"file_tags": {}, "scan_t": 0.0})()
check(fw.lib_with_tags()[0]["artist"] == "", "gleich nach dem Schreiben: leer")
fw.folder = type("F", (), {"file_tags": {tail(P): {"title": "Uhr", "artist": "", "genre": "Sample"}}, "scan_t": time.time() + 60})()
check(fw.lib_with_tags()[0]["artist"] == "", "nach dem Einlesen der Ordner-Liste: bleibt leer, auch wenn Mixxx noch den alten Namen hat")
fw.folder = type("F", (), {"file_tags": {tail(P): {"title": "Uhr", "artist": "Sprecher", "genre": "Sample"}}, "scan_t": time.time() + 60})()
check(fw.lib_with_tags()[0]["artist"] == "Sprecher", "spaeter woanders neu getaggt: der Wert aus der Datei gilt")
fw.folder = type("F", (), {"file_tags": {tail(P): {"title": "Uhr", "artist": "", "genre": ""}}, "scan_t": time.time() + 60})()
check(fw.lib_with_tags()[0]["genre"] == "Sample", "leeres Genre in der Datei, nicht selbst geleert: Wert aus Mixxx wie bisher")

ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
aj = open(os.path.join(ROOT, "pi", "static", "sm", "artists.js"), encoding="utf-8").read()
check('op == "artist" and isinstance(d.get("paths"), list)' in ms and '"job" in q' in ms, "Musik-Rechner: Befehl und Stand")
check("data-a=\"rename\"" in aj and "op: 'artist'" in aj and "op: 'undo'" in aj, "Seite: Knopf, Schreiben, Zuruecknehmen")
check("for (const ms of [5000, 20000, 60000]) setTimeout(load, ms);" in aj, "Seite schaut nach 5, 20 und 60 Sekunden wieder nach")
finish("test_interpret_aendern")
