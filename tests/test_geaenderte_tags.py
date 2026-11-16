"""Geaenderte Tags -> Mixxx (Wunsch von Markus, 08.11.2026): jede vom Light-Butler geschriebene MP3 wird gemerkt, daraus eine
Playlist fuer Mixxx; danach leeren. Mixxx selbst bleibt unberuehrt."""
import json
import os
import sys
import tempfile
import urllib.request

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import changed_log as cl  # noqa: E402
import music_serve as ms  # noqa: E402
import tag_edit as te  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_geaendert_")
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
ms.M3U_DIR = os.path.join(tmp, "pl")
a, b = os.path.join(tmp, "a.mp3"), os.path.join(tmp, "b.mp3")
for p in (a, b):
    open(p, "wb").write(b"\xff\xfb" + b"\0" * 300)

check(cl.status()["n"] == 0, "am Anfang leer")
te.write_tags(a, {"title": "Neu"})
te.write_tags(a, {"artist": "Wer"})                     # zweimal dieselbe: einmal in der Liste
te.write_tags(b, cover=b"\xff\xd8\xff\xe0" + b"x" * 50)
check(cl.status()["n"] == 2 and set(cl.files()) == {a, b}, "jede geschriebene MP3 gemerkt (Tags und Cover), doppelt nur einmal")
f, n, t = cl.write_m3u(ms.M3U_DIR)
lines = open(f, encoding="utf-8").read().splitlines()
check(os.path.basename(f) == "Light-Butler geaenderte Tags.m3u8" and n == 2 and lines[0] == "#EXTM3U" and a in lines and b in lines,
      "Playlist mit den geaenderten Dateien")
os.remove(b)
check(set(cl.files()) == {a}, "geloeschte Datei faellt heraus")
cl.note(b + "-neu")  # Datei gibt es nicht
te.write_tags(a, {"genre": "Pop"})
check(cl.clear(before=t) == 1 and cl.status()["n"] == 1, "leeren bis zum Stand der Playlist, Spaeteres bleibt")
check(cl.clear() == 0 and cl.status()["n"] == 0, "ganz leeren")
try:
    cl.write_m3u(ms.M3U_DIR)
    check(False, "leer: Hinweis statt leerer Playlist")
except ValueError:
    check(True, "leer: Hinweis statt leerer Playlist")

srv = ms.MusicServer([a], port=0)
srv.start()
base = "http://127.0.0.1:%d" % srv.port
te.write_tags(a, {"title": "Noch neuer"})
check(json.loads(urllib.request.urlopen(base + "/changed", timeout=5).read())["n"] == 1, "GET /changed: Zahl")
post = lambda d: json.loads(urllib.request.urlopen(urllib.request.Request(base + "/changed", data=json.dumps(d).encode(), method="POST"), timeout=5).read())  # noqa: E731
d = post({"op": "m3u"})
check(d["n"] == 1 and os.path.isfile(d["file"]), "POST m3u")
check(post({"op": "clear", "before": d["t"]})["left"] == 0, "POST clear")
check(post({"op": "reset"})["n"] == 0, "POST reset")
srv.stop()

# rueckwirkend: Datei neuer als der letzte Abgleich in Mixxx (source_synchronized_ms)
import sqlite3  # noqa: E402
import time  # noqa: E402
db = os.path.join(tmp, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.executescript("CREATE TABLE library (id INTEGER, location INTEGER, mixxx_deleted INTEGER, source_synchronized_ms INTEGER);"
                  "CREATE TABLE track_locations (id INTEGER, location TEXT, fs_deleted INTEGER);")
c_old, c_new, c_none = (os.path.join(tmp, n + ".mp3") for n in ("alt", "neu", "nie"))
for p in (c_old, c_new, c_none):
    open(p, "wb").write(b"\xff\xfb")
now_ms = int(time.time() * 1000)
os.utime(c_new, (time.time(), time.time()))
con.executemany("INSERT INTO track_locations VALUES (?, ?, 0)", [(1, c_old), (2, c_new), (3, c_none)])
con.executemany("INSERT INTO library VALUES (?, ?, 0, ?)", [(1, 1, now_ms + 60000), (2, 2, now_ms - 3600 * 1000), (3, 3, None)])
con.commit()
con.close()
check(set(cl.mixxx_newer(db)) == {c_new}, "rueckwirkend: nur Dateien, die neuer sind als der Abgleich in Mixxx (nie abgeglichene nicht)")
os.rename(db, os.path.join(os.environ["S2L_DATA"], "mixxxdb.sqlite"))
f, n, t = cl.write_m3u(ms.M3U_DIR)
check(c_new in open(f, encoding="utf-8").read().splitlines(), "Playlist enthaelt auch diese")
te.write_tags(a, {"title": "Vor dem Reset"})
check(cl.status()["n"] >= 2, "vor dem Zuruecksetzen: eigene und ueber Mixxx")
cl.reset()
check(cl.status()["n"] == 0 and cl.all_files(wait=True) == {}, "Zuruecksetzen: alles auf 0, auch was Mixxx noch nicht kennt")
time.sleep(0.01)
te.write_tags(a, {"title": "Nach dem Reset"})
check(set(cl.all_files(wait=True)) == {a}, "danach zaehlen neue Aenderungen wieder")
# Fehlerbericht 09.11.2026: nach "Fertig, Liste leeren" blieb die Zahl (336), weil auch alles zaehlte, was neuer ist als der
# Abgleich in Mixxx. Jetzt gilt "Fertig" nach dem Export wie Zuruecksetzen bis zum Stand der Playlist.
time.sleep(0.01)
os.utime(c_new, None)
check(c_new in cl.all_files(wait=True), "vor dem Export: Datei neuer als Mixxx zaehlt")
f, n, t = cl.write_m3u(ms.M3U_DIR)
cl.clear(before=t)
check(cl.all_files(wait=True) == {} and cl.status()["n"] == 0, "Fertig nach dem Export: auf 0, auch was nur ueber Mixxx zaehlte")

for inst in ("mac/mixxx_bridge/install_launcher.sh", "mac/helper/install_helper.sh"):
    check("changed_log.py" in open(os.path.join(ROOT, inst), encoding="utf-8").read(), inst + " kopiert changed_log.py")
html = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check('id="bchg0"' in html and "op: 'reset'" in js, "Musik-DB: Knopf zum Zuruecksetzen")
check('id="bchg"' in html and "music + '/changed'" in js and "Aus Datei importieren" in js, "Musik-DB: Knopf Geaenderte → Mixxx mit Anleitung")
finish("test_geaenderte_tags")
