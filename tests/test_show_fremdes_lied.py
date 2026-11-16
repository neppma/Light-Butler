"""Show aus dem Showmanager (Browser) haelt das Licht, Mixxx spielt schon ein anderes Lied (Fehlerbericht 06.11.2026: Hauptpanel
blieb auf Cover und Liedtext der alten Show stehen). Nach 3 s anderem Lied endet sie, AUTO uebernimmt, die Show des neuen
Liedes darf starten. Dasselbe Lied oder ein kurzes Anspielen beenden nichts."""
import tempfile

from _common import DT, Clock, build, check, finish

from mixxx_link import MixxxLink
from showman.api import ShowManager
from showman.engine import MIXXX

tmp = tempfile.mkdtemp(prefix="s2l_fremd_")
link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
mgr = ShowManager(sh, tmp)
sh.cfg.set("sm_mixxx_auto", 1.0)
sh.cfg.set("mixxx_lead_s", 0.0)
c = Clock(sh)


def make(name, title):
    mgr.op({"op": "create", "name": name, "title": title, "dur": 240.0})
    doc = mgr.store.load(name)
    doc.update(duration=240.0, tracks=[{"target": {"fixture": "par"}, "attr": "dimmer", "keys": [{"t": 0, "v": 200, "e": "linear"}], "clips": []}])
    mgr.store.save(name, doc)
    mgr.index_dirty = True


make("Alt", "A - Alt")
make("Neu", "B - Neu")
n = [0]


def run(sec, title=None, start=0.0):
    t0 = c.t
    for _ in range(int(round(sec / DT))):
        if title:
            link.feed({"type": "plan", "d": 1, "key": title, "title": title, "du": 240.0, "ev": [], "en": [], "fp": ""}, c.t)
            link.feed({"d": 1, "pp": (start + c.t - t0) / 240.0, "du": 240.0, "rr": 1.0, "bp": 128.0, "pl": 1, "tl": 1, "vo": 1.0}, c.t)
        c.run(DT)
        n[0] += 1
        if n[0] % 8 == 0:
            mgr.mixxx_tick(c.t)


e = mgr.engine
e.load(mgr.store.load("Alt"))
e.play(c.t, 0.0, False, "b1")                 # im Showmanager mit Licht an, dann angehalten
e.set_light(True)
run(0.5)
check(sh.snapshot()["sm_show"] == "Alt", "Show aus dem Browser haelt das Licht (angehalten)")
run(2.0, "B - Neu", 10.0)
check(e.loaded and e.doc_name == "Alt", "kurz ein anderes Lied: die Show bleibt")
run(2.0, "B - Neu", 12.0)
check(e.loaded and e.owner == MIXXX and e.doc_name == "Neu", "Mixxx spielt laenger ein anderes Lied: alte Show weg, die des neuen Liedes laeuft")
run(1.0, "B - Neu", 14.0)
check(sh.snapshot()["sm_show"] == "Neu", "Hauptpanel zeigt die neue Show")

# dieselbe Lied: die Show aus dem Browser bleibt
sh.command({"auto": "toggle"})
run(1.0)
e.load(mgr.store.load("Alt"))
e.play(c.t, 30.0, True, "b1")
e.set_light(True)
run(5.0, "A - Alt", 30.0)
check(e.loaded and e.owner == "b1" and e.doc_name == "Alt", "Mixxx spielt dasselbe Lied: die Show aus dem Browser bleibt")

# ohne Show zum neuen Lied: zurueck zu AUTO
mgr.store.delete("Neu") if hasattr(mgr.store, "delete") else None
mgr.index_dirty = True
run(5.0, "C - Ohne Show", 0.0)
run(0.5)
check(not e.loaded and sh.snapshot()["sm_show"] == "", "anderes Lied ohne Show: alte Show endet, AUTO uebernimmt")
finish("Show und fremdes Lied in Mixxx")
