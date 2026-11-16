"""Quick im Hauptpanel (Wunsch von Markus, 06.11.2026): zum Lied aus Mixxx ohne Show eine Show anlegen und sie gleich mit dem
laufenden Lied starten, einmal, auch wenn die Mixxx-Automatik (sm_mixxx_auto) aus ist. Dazu Cover gross beim Darueberfahren."""
import os
import tempfile

from _common import DT, ROOT, Clock, build, check, finish

import webpanel
from mixxx_link import MixxxLink
from showman.api import ShowManager
from showman.engine import MIXXX

tmp = tempfile.mkdtemp(prefix="s2l_qh_")
link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
mgr = ShowManager(sh, tmp)
sh.cfg.set("sm_mixxx_auto", 0.0)
sh.cfg.set("mixxx_lead_s", 0.0)
c = Clock(sh)
link.feed({"type": "lib", "i": 0, "n": 1, "t": [["Abba - Dancing Queen", 240.0, "Abba", "Dancing Queen", 100.0, "A", 1, "Pop", 6,
                                                  "dq.mp3", 0, 1, "/m/dq.mp3"]]}, c.t)
mgr.music_url = lambda: "http://mac:9025"


def deck(title, pos, playing=1):
    link.feed({"type": "plan", "d": 1, "key": title, "title": title, "du": 240.0, "ev": [], "en": [], "fp": ""}, c.t)
    link.feed({"d": 1, "pp": pos / 240.0, "du": 240.0, "rr": 1.0, "bp": 128.0, "pl": playing, "tl": 1, "vo": 1.0}, c.t)


n = [0]


def run(sec, title, start):
    t0 = c.t
    for _ in range(int(round(sec / DT))):
        deck(title, start + c.t - t0)
        c.run(DT)
        n[0] += 1
        if n[0] % 8 == 0:
            mgr.mixxx_tick(c.t)


q = mgr.quick_check("Abba - Dancing Queen", 240.0)
check(q["show"] is None and q["song"]["path"] == "/m/dq.mp3" and q["song"]["mp3"] and q["music"] == "http://mac:9025"
      and q["song"]["artist"] == "Abba" and q["song"]["name"] == "Dancing Queen", "noch keine Show: Angaben fuer Quick")
check(mgr.quick_check("Unbekannt", 100)["song"] is None, "Lied nicht in der Bibliothek: kein Quick")
check(q["stems"] is False, "ohne Spur-Kurven: kein Quick-Knopf (Wunsch von Markus)")
FP = "300:0123456789abcdef"
mgr.stem_bulk.fps["/m/dq.mp3"] = FP
os.makedirs(os.path.dirname(mgr.store._stems_path(FP)), exist_ok=True)
open(mgr.store._stems_path(FP), "w").write("{}")
check(mgr.quick_check("Abba - Dancing Queen", 240.0)["stems"] is True, "mit Spur-Kurven: Quick-Knopf")

# Quick hat die Show angelegt (im Browser: SM.quickShow); hier nur das Ergebnis
mgr.op({"op": "create", "name": "Abba - Dancing Queen", "title": "Abba - Dancing Queen", "dur": 240.0})
doc = mgr.store.load("Abba - Dancing Queen")
doc["duration"] = 240.0
mgr.store.save("Abba - Dancing Queen", doc)
mgr.index_dirty = True
check(mgr.quick_check("Abba - Dancing Queen", 240.0)["show"] == "Abba - Dancing Queen", "danach: Show gefunden, kein Knopf mehr")

run(5.0, "Abba - Dancing Queen", 30.0)
check(not mgr.engine.loaded, "ohne Quick und ohne Mixxx-Automatik: die Show startet nicht von allein")
mgr.op({"op": "mixxx_once"})
run(5.0, "Abba - Dancing Queen", 35.0)
e = mgr.engine
check(e.loaded and e.owner == MIXXX and e.light, "nach Quick: die Show startet mit dem laufenden Lied")
check(abs(e.position(c.t) - 40.0) < 1.0, "an der Stelle des Liedes")
sh.command({"auto": "toggle"})                       # Knopf SHOW beendet sie
run(5.0, "Abba - Dancing Queen", 40.0)
check(not e.loaded and mgr.mx_once is None, "Knopf SHOW: beendet und nicht wieder gestartet (nur einmal)")
mgr.op({"op": "mixxx_once"})
run(1.0, "Was Anderes", 0.0)
check(mgr.mx_once is None and not e.loaded, "anderes Lied: Quick gilt nicht mehr")
link.feed({"d": 1, "pp": 0, "du": 240.0, "rr": 1.0, "bp": 128.0, "pl": 0, "tl": 1, "vo": 0.0}, c.t)

page = webpanel.make_page()
check("q.stems&&q.song" in page and 'id="pquick"' in page and "/api/sm/quick_check?t=" in page and "SM.quickShow(" in page and "mixxx_once" in page, "Hauptpanel: Knopf Quick-Show in der Liedtext-Zeile")
check('<script src="/static/sm/core.js"></script>' in page, "Hauptpanel laedt den gemeinsamen Quick-Ablauf")
core = open(os.path.join(ROOT, "pi", "static", "sm", "core.js"), encoding="utf-8").read()
music = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("SM.quickShow = " in core and "SM.quickShow(r, music" in music, "Musik-Datenbank und Hauptpanel nutzen denselben Ablauf")
check("SM.coverZoom" in core and "pointerType !== 'mouse'" in core, "Cover gross beim Darueberfahren mit der Maus")
finish("Quick im Hauptpanel")
