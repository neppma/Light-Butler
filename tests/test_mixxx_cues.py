"""Hotcues aus Mixxx (Mixed In Key setzt sie taktgenau an Abschnittswechsel): Die Bruecke liest sie aus der Datenbank
(Position in Samples, Stereo) und schickt sie mit dem Plan ("cu"). Der Pi rueckt Drops der Analyse, die hoechstens
mixxx_cue_snap_s daneben liegen, genau auf den Hotcue (Aufbau und Stille enden mit), das Panel zeichnet sie im Liedverlauf."""
import json
import os
import sqlite3
import sys
import tempfile

from _common import ROOT, build, check, finish

import webpanel
from mixxx_link import MixxxLink, snap_drops

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from mixxx_bridge import Forwarder, load_library    # noqa: E402

# ---- Mac: Hotcues aus der Datenbank ---------------------------------------------------------------------------------
d = tempfile.mkdtemp()
db = os.path.join(d, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE library (id INTEGER, artist TEXT, title TEXT, duration REAL, bpm REAL, key TEXT, key_id INTEGER,
                      mixxx_deleted INTEGER, samplerate INTEGER);
CREATE TABLE cues (id INTEGER, track_id INTEGER, type INTEGER, position REAL, length REAL, hotcue INTEGER, label TEXT);
INSERT INTO library VALUES (1, 'A', 'Eins', 200, 128, 'Am', 0, 0, 44100);
INSERT INTO cues VALUES (1, 1, 1, 2646000, 0, 1, 'Cue 2');
INSERT INTO cues VALUES (2, 1, 1, 88200, 0, 0, 'Cue 1');
INSERT INTO cues VALUES (3, 1, 6, 0, 0, -1, '');
INSERT INTO cues VALUES (4, 1, 1, -1, 0, 2, 'leer');
""")
con.commit()
con.close()
lib = load_library(db)
check(lib[0]["cues"] == [1.0, 30.0], "nur Hotcues, in Sekunden (Samples / 2 / Abtastrate), sortiert")

fw = Forwarder([], None, None, analysis_dir=d, analyze=False)
jp = os.path.join(d, "plan.json")
with open(jp, "w", encoding="utf-8") as fh:
    json.dump({"duration": 200.0, "artist": "A", "title": "Eins", "events": [], "energy": []}, fh)
fw.decks[1] = {"key": "k", "rec": {"duration": 200.0, "cues": [1.0, 30.0, 250.0]}}
fw._load_plan(1, jp)
check(fw.decks[1]["plan"]["cu"] == [1.0, 30.0], "Plan mit Hotcues (nur innerhalb des Liedes)")

# ---- Pi: Drops einrasten -------------------------------------------------------------------------------------------
plan = {"type": "plan", "d": 1, "key": "k", "title": "A - Eins", "du": 200.0, "cu": [30.0, 90.0, 150.0],
        "ev": [["build", 20.0, 28.9, 0, ""], ["gap", 28.9, 28.9, 0, ""], ["drop", 28.9, 28.9, 0.9, "b"],
               ["drop", 92.0, 92.0, 0.9, "b"], ["drop", 120.0, 120.0, 0.9, "b"]],
        "en": []}
check(snap_drops(plan, 1.5) == {28.9: 30.0}, "Drop 1,1 s vor dem Hotcue rastet ein, 2 s daneben nicht")
check(snap_drops(plan, 0.0) == {} and snap_drops(dict(plan, cu=[]), 1.5) == {}, "aus (0) oder ohne Hotcues: nichts")

rig, sh = build()
link = MixxxLink(0)
now = 1000.0
link.feed(plan, now)
link.feed({"d": 1, "pp": 0.05, "du": 200.0, "rr": 1.0, "bp": 128.0, "pl": 1, "tl": 1, "vo": 1.0}, now)
shift = sh.cfg["mixxx_shift_s"]
ev = link._events(plan, sh.cfg)
check(("drop", 30.0 + shift, 30.0 + shift) in ev, "Drop auf den Hotcue geruckt")
check(("build", 20.0 + shift, 30.0 + shift) in ev and ("gap", 28.9 + shift, 30.0 + shift) in ev,
      "Aufbau und Stille enden mit dem Drop")
check(("drop", 92.0 + shift, 92.0 + shift) in ev and ("drop", 120.0 + shift, 120.0 + shift) in ev, "weiter entfernte Drops bleiben")
st = link.status(now, sh.cfg)
check(st["bar"]["cu"] == [30.0, 90.0, 150.0], "Hotcues im Liedverlauf")

sh.cfg.set("mixxx_cue_snap_s", 0.0)
ev0 = link._events(plan, sh.cfg)
check(("drop", 28.9 + shift, 28.9 + shift) in ev0 and ("build", 20.0 + shift, 28.9 + shift) in ev0, "Einrasten aus: wie bisher")
sh.cfg.set("mixxx_cue_snap_s", 1.5)
old = dict(plan)
old.pop("cu")
check(link._events(old, sh.cfg) == ev0, "alte Bruecke ohne Hotcues: wie bisher")

# ---- Pi: Wechsel an Hotcues (wie eine neue Phrase) ------------------------------------------------------------------
base = {"plan": True, "playing": True, "cue_id": (1, "k"), "cue_n": 0}
rig, sh = build()
sh.mx = dict(base)
check(not sh._cue_hit(), "erstes Bild: nur merken")
sh.mx = dict(base, cue_n=1)
check(sh._cue_hit(), "ueber einen Hotcue gelaufen: Wechsel")
check(not sh._cue_hit(), "nur in einem Bild")
sh.mx = dict(base, cue_n=4)
check(not sh._cue_hit(), "gesprungen (mehrere auf einmal): kein Wechsel")
sh.mx = dict(base, cue_n=5, cue_id=(2, "x"))
check(not sh._cue_hit(), "anderes Lied/Deck: kein Wechsel")
sh.mx = dict(base, cue_n=6, cue_id=(2, "x"))
sh.cfg.set("mixxx_cue_change", 0)
check(not sh._cue_hit(), "Einstellung aus: kein Wechsel")
sh.cfg.set("mixxx_cue_change", 1)
sh.mx = None
check(not sh._cue_hit(), "ohne Mixxx: kein Wechsel")


class Feed:
    """Mixxx-Anbindung fuer die Show: ein Lied ab 25 s, Hotcue bei 30 s (die Zeit laeuft mit der Uhr der Show)."""

    def __init__(self, link):
        self.link = link

    def status(self, now, cfg):
        return self.link.status(now, cfg)


cplan = dict(plan, ev=[], cu=[30.0])
lk = MixxxLink(0)
from _common import Clock    # noqa: E402
rig, sh = build(mixxx=Feed(lk))
clk = Clock(sh)
lk.feed(cplan, clk.t)
t0 = clk.t
seen = []


def step(t):
    lk.feed({"d": 1, "pp": (25.0 + t - t0) / 200.0, "du": 200.0, "rr": 1.0, "bp": 128.0, "bd": 0.0, "pl": 1, "tl": 1, "vo": 1.0}, t)
    seen.append((t, sh.cue_seq, sh.last_color_change))


step(t0)
clk.run(6.0, step)
hit = [x for x in seen if x[1] == 1]
lead = sh.cfg["mixxx_lead_s"]
check(len(hit) > 0 and abs(hit[0][0] - (clk.t - 6.0) - (5.0 - lead)) < 0.06, "Wechsel genau am Hotcue (mit Vorlauf)")
check(any(abs(x[2] - hit[0][0]) < 0.001 for x in seen), "dabei neue Farbe")
check(max(x[1] for x in seen) == 1, "nur ein Wechsel")

# ---- Panel ---------------------------------------------------------------------------------------------------------------
p = webpanel.make_page()
check("(B.cu||[]).forEach(c=>" in p and "#ffd24d" in p, "Panel: Hotcues als gelbe Striche im Liedverlauf")
finish("test_mixxx_cues")
