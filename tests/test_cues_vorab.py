"""Cue-Punkte vorab (Wunsch von Markus 06.11.2026): der Pi holt Cue-Punkte, Abschnitte und Drops aller Lieder einmal vom Mac
und legt sie ab; Shows und Quick nehmen sie dann ohne Mac."""
import io
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse

from _common import build, check, finish

from mixxx_link import MixxxLink
from showman import marks_bulk as mbk
from showman.api import ShowManager

tmp = tempfile.mkdtemp(prefix="s2l_cues_")
LIB = [{"title": "A - Eins", "dur": 200.0, "path": "/m/eins.mp3"}, {"title": "B - Zwei", "dur": 210.0, "path": "/m/zwei.mp3"},
       {"title": "C - Neu", "dur": 220.0, "path": "/m/neu.mp3"}, {"title": "A - Eins", "dur": 200.0, "path": "/m/eins.mp3"}]
music = ["http://mac:9025"]
asked = []


class R(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def mac(url, timeout=0):
    p = urllib.parse.unquote(url.split("p=")[1])
    asked.append(p)
    if p == "/m/neu.mp3":
        raise urllib.error.HTTPError(url, 404, "keine Analyse", {}, None)
    return R(json.dumps({"title": p, "se": [["intro", 0, 20]], "cu": [5.0, 40.0], "ev": [["drop", 40.0, 40.0, 0.9, ""]], "en": [10] * 50,
                         "lvl": 6, "genre": "Pop", "fp": ""}).encode())


mb = mbk.MarksBulk(tmp, lambda: LIB, lambda: music[0], mac)
check(mb.status()["total"] == 3 and mb.status()["done"] == 0, "je Pfad einmal")
check(mb.step(LIB[0]) is True and mb.get("/m/eins.mp3")["cu"] == [5.0, 40.0] and mb.get("/m/eins.mp3")["se"][0][0] == "intro", "ein Lied holen und ablegen")
check(mb.step(LIB[2]) is False and "/m/neu.mp3" in mb.missing, "am Mac nicht analysiert: kein Fehler, gemerkt")
music[0] = ""
check(mb.step(LIB[1]) is None, "Mac nicht da: spaeter wieder")
music[0] = "http://mac:9025"
mbk.GAP_S = 0.0
mb.start()
mb.thread.join(5)
st = mb.status()
check(st["done"] == 2 and st["missing"] == 1 and st["done_all"] and not st["running"], "Lauf: alle geholt, das nicht analysierte gezaehlt, dann fertig")
check(mb._flag() is False, "fertig: laeuft nach einem Neustart nicht wieder an")
LIB[2]["bad"] = 1
st = mb.status()
check(st["missing"] == 0 and st["bad"] == 1 and st["done"] == 2, "nicht lesbare Datei (Analyse am Mac scheitert): eigens gezaehlt, nicht als offen")
check(st["done_all"], "nur noch nicht lesbare offen: erledigt, Startknopf weg (Fehlerbericht 07.11.2026)")
LIB[2]["bad"] = 0
pg0 = __import__("webpanel").stats_page()
check("want=Math.max(0,s.total-(s.bad||0))" in pg0 and "nicht lesbare Dateien, die nie eine Analyse bekommen" in pg0, "Karte: 100 % ohne die nicht lesbaren, die stehen eigens da")
n_before = len(asked)
mb.start()
mb.thread.join(5)
check(asked[n_before:] == ["/m/neu.mp3"], "naechstes Starten: nur das bisher fehlende nochmal fragen")
mb2 = mbk.MarksBulk(tmp, lambda: LIB, lambda: music[0], mac)
mb2._flag(True)
mb2.resume()
mb2.thread.join(5)
check(mb2.status()["done"] == 2, "lief es, geht es nach einem Neustart weiter")
check(mb.get("/m/zwei.mp3") is not None and mb.get("/m/fremd.mp3") is None, "nur abgelegte Lieder")

# ---- Shows nehmen die Ablage, auch ohne Mac ----
link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
mgr = ShowManager(sh, tmp)
link.feed({"type": "lib", "i": 0, "n": 1, "t": [["A - Eins", 200.0, "A", "Eins", 128.0, "Am", 22, "Pop", 6, "eins.mp3", 2, 1, "/m/eins.mp3"]]}, 1.0)
mgr.op({"op": "create", "name": "Eins", "title": "A - Eins", "dur": 200.0})
mgr.music_url = lambda: ""                             # Mac aus
mgr.mac_opener = lambda *a, **k: (_ for _ in ()).throw(OSError("aus"))
r = mgr.op({"op": "marks_from_mac", "name": "Eins"})
check(r["found"] and r.get("from") == "ablage" and mgr.store.load("Eins")["marks"]["cu"] == [5.0, 40.0], "Show bekommt Cue-Punkte aus der Ablage, ohne Mac")
st2 = mgr.op({"op": "marks_bulk_status"})
check(st2["total"] == 1 and st2["done"] == 1, "Seite Statistik: Stand ueber den Showmanager")

import webpanel  # noqa: E402
pg = webpanel.stats_page()
check('id="mkbulk"' in pg and "mkBulkCmd({op:'marks_bulk',on:!s.running})" in pg and "loadMkBulk()" in pg, "Karte Cue-Punkte vorab holen mit Starten/Anhalten")
eng = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi", "showman", "engine.py"), encoding="utf-8").read()
check("marks_bulk" not in eng, "aufs Licht wirkt das nicht")
time.sleep(0.05)
finish("test_cues_vorab")
