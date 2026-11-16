"""Energiestufe und Genre aus Mixxx: Die Mac-Bruecke liest die Energie aus dem Kommentar von Mixed In Key ("8A - Energy 7"),
sonst aus den Crates "Energy 8"/"Energy 9", sonst aus der Trackfarbe (#993333 = 9, #997733 = 8, #339933 = 7), dazu das
Genre, und schickt beides mit dem Plan. Auf dem Pi verschiebt jede Stufe ueber/unter der Mitte die Energie um
mixxx_energy_w, das Panel zeigt E1-E9 in Farbe und das Genre in der Mixxx-Zeile."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

from _common import ROOT, build, check, finish

import webpanel
from mixxx_link import MixxxLink

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from mixxx_bridge import Forwarder, energy_level, load_library    # noqa: E402

# ---- Mac: Energiestufe aus Kommentar, Crate oder Farbe -------------------------------------------------------------
check(energy_level({"comment": "8A - Energy 7"}) == 7 and energy_level({"comment": "10B - energy 3"}) == 3, "Kommentar von Mixed In Key")
check(energy_level({"comment": "8A - Energy 5", "crates": ["Energy 8"], "color": 0x997733}) == 5, "Kommentar vor Crate und Farbe")
check(energy_level({"comment": "Radio", "color": 0x339933}) == 7, "ohne Energie im Kommentar: Farbe gruen = 7")
check(energy_level({"crates": ["Energy 9"]}) == 9 and energy_level({"crates": ["House", "energy 8"]}) == 8,
      "Crate 'Energy 9' / 'energy 8'")
check(energy_level({"crates": ["Energy 8", "Energy 9"], "color": 0x997733}) == 9, "mehrere Crates: die hoechste, Crate vor Farbe")
check(energy_level({"crates": [], "color": 0x993333}) == 9 and energy_level({"color": 0xFF997733}) == 8,
      "Trackfarbe rot = 9, braun = 8 (auch mit Alpha)")
check(energy_level({"crates": ["Party"], "color": 0x00FF00}) is None and energy_level({}) is None, "sonst keine Stufe")

d = tempfile.mkdtemp()
db = os.path.join(d, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE library (id INTEGER, artist TEXT, title TEXT, duration REAL, bpm REAL, key TEXT, key_id INTEGER,
                      mixxx_deleted INTEGER, genre TEXT, color INTEGER, comment TEXT);
CREATE TABLE crates (id INTEGER, name TEXT);
CREATE TABLE crate_tracks (crate_id INTEGER, track_id INTEGER);
INSERT INTO library VALUES (1, 'A', 'Eins', 200, 128, 'Am', 0, 0, 'Techno', NULL, NULL);
INSERT INTO library VALUES (2, 'B', 'Zwei', 210, 124, 'C', 0, 0, 'House', 10057523, NULL);
INSERT INTO library VALUES (3, 'C', 'Drei', 220, 120, 'G', 0, 0, 'Pop', 3381555, '9A - Energy 4');
INSERT INTO crates VALUES (5, 'Energy 9');
INSERT INTO crate_tracks VALUES (5, 1);
""")
con.commit()
con.close()
lib = {r["id"]: r for r in load_library(db)}
check(lib[1]["crates"] == ["Energy 9"] and energy_level(lib[1]) == 9 and lib[1]["genre"] == "Techno", "Datenbank: Crate und Genre")
check(lib[2]["crates"] == [] and energy_level(lib[2]) == 8 and lib[2]["genre"] == "House", "Datenbank: Farbe #997733 = 8")
check(energy_level(lib[3]) == 4, "Datenbank: Kommentar 'Energy 4' vor der gruenen Farbe")

# ---- Mac: Plan mit der Laenge aus Mixxx ------------------------------------------------------------------------------
# afconvert laesst kaputte Bilder am Ende weg (Froehliche Weihnacht Ueberall: 149,052 statt 149,28 s). Der Pi wuerde den
# Plan sonst als "passt nicht zum geladenen Lied" verwerfen.
fw = Forwarder([], None, None, analysis_dir=d, analyze=False)
jp = os.path.join(d, "plan.json")
with open(jp, "w", encoding="utf-8") as fh:
    json.dump({"duration": 149.052, "artist": "Helene Fischer", "title": "Weihnacht", "events": [], "energy": []}, fh)
fw.decks[1] = {"key": "k", "rec": {"duration": 149.28, "comment": "8A - Energy 3", "genre": "Weihnachten"}}
fw._load_plan(1, jp)
pl = fw.decks[1]["plan"]
check(pl["du"] == 149.28 and pl["lvl"] == 3 and pl["genre"] == "Weihnachten", "Plan: Laenge wie in Mixxx, Stufe und Genre")
fw.decks[1]["rec"]["duration"] = 160.0
fw._load_plan(1, jp)
check(fw.decks[1]["plan"]["du"] == 149.052, "weicht die Laenge weit ab: Laenge der Analyse (Pi prueft weiter)")

# ---- Pi: Plan -> Status -> Zuschlag ----------------------------------------------------------------------------------
rig, sh = build()
link = MixxxLink(0)
now = 1000.0
plan = {"type": "plan", "d": 1, "key": "k", "title": "A - Eins", "du": 240.0, "ev": [], "en": [], "lvl": 9, "genre": "Techno"}
link.feed(plan, now)
link.feed({"d": 1, "pp": 0.25, "du": 240.0, "rr": 1.0, "bp": 128.0, "pl": 1, "tl": 1, "vo": 1.0}, now)
st = link.status(now, sh.cfg)
check(st["lvl"] == 9 and st["genre"] == "Techno", "Status mit Stufe und Genre")
sh.mx = dict(st)
check(sh.cfg["mixxx_energy_w"] == 0.03 and sh.cfg["mixxx_energy_mid"] == 6, "Standard: 0,03 je Stufe, Mitte 6")
check(abs(sh._track_boost() - 0.09) < 1e-9, "Energy 9: +0,09")
mp = sh._mx_public()
check(mp["lvl"] == 9 and mp["genre"] == "Techno", "ans Panel")
link.feed(dict(plan, lvl=8), now)
sh.mx = link.status(now, sh.cfg)
check(abs(sh._track_boost() - 0.06) < 1e-9, "Energy 8: +0,06")
link.feed(dict(plan, lvl=6), now)
sh.mx = link.status(now, sh.cfg)
check(sh._track_boost() == 0.0, "Energy 6 (Mitte): unveraendert")
link.feed(dict(plan, lvl=3), now)
sh.mx = link.status(now, sh.cfg)
check(abs(sh._track_boost() + 0.09) < 1e-9, "Energy 3: -0,09 (ruhiger)")
link.feed(dict(plan, lvl=None, genre=None), now)
sh.mx = link.status(now, sh.cfg)
check(sh._track_boost() == 0.0 and sh.mx["lvl"] is None and sh.mx["genre"] == "", "ohne Stufe kein Zuschlag")
link.feed(dict(plan, lvl="x"), now)
check(link.status(now, sh.cfg)["lvl"] is None, "Unsinn verworfen")
sh.cfg.set("mixxx_energy_w", 0.0)
link.feed(plan, now)
sh.mx = link.status(now, sh.cfg)
check(sh._track_boost() == 0.0, "Zuschlag 0 = aus")
sh.mx = dict(sh.mx, deck=None, plan=False)
check(sh._track_boost() == 0.0, "kein Deck hoerbar: kein Zuschlag")
sh.mx = None
check(sh._track_boost() == 0.0, "ohne Mixxx: kein Zuschlag")

# ---- Panel ---------------------------------------------------------------------------------------------------------------
p = webpanel.make_page()
check("'<span class=\"mxe\" style=\"background:'+(ECOL[Math.min(m.lvl,10)-1]" in p and "'<span class=\"mxg\">'+esc(m.genre)" in p,
      "Panel: Abzeichen E1-E9 und Genre neben dem Titel")
check("'#339933','#997733','#993333'" in p, "Abzeichen 7-9 in den Mixxx-Farben")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_mixxx_energie")
