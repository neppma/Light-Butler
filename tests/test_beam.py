"""Bereich Beam (Lichtstrahl) im Panel: Gobo (Open, 1 bis 5), Zoom, Roll und Prisma des Vega von Hand oder Auto.
Roll und Prisma: 50 % steht, darueber im Uhrzeigersinn, darunter gegen den Uhrzeigersinn (Test am Geraet), Prisma 0 % aus.
Gilt in AUTO und allen Szenen; Blinder, WOW!, Blackout und Freeze bleiben wie bisher. Bleibt ueber den Neustart erhalten."""
import json
import os
import tempfile

from _common import zurueck, PI, build, Clock, check, finish

import show as sw
import webpanel
from audio import Simulator
from dmx import Rig

rig, sh = build()
clk = Clock(sh)
clk.run(3)
vega = rig["vega"]
V = vega.values
check(sh.snapshot()["beam"] == {"auto": True, "vals": {"gobo": 0, "zoom": 100.0, "roll": 50.0, "prism": 0.0}}, "Start: Auto")
check(V["zoom"] == 255 and V["prism"] == 0, "Auto: Zoom und Prisma wie bisher")

sh.command({"beam": {"gobo": 2}})
clk.run(0.1)
check(sh.snapshot()["beam"]["auto"] is False, "Gobo gewaehlt: Beam von Hand")
check(V["gobo"] == 46 and V["gobo_rot"] == 0 and V["zoom"] == 255 and V["prism"] == 0, "Gobo 2 (Spirale), sonst Grundwerte")
for g, val in ((0, 0), (1, 21), (3, 71), (4, 96), (5, 121)):
    sh.command({"beam": {"gobo": g}})
    clk.run(0.05)
    check(V["gobo"] == val, f"Gobo {g or 'Open'}: Kanalwert {val}")
sh.command({"beam": {"zoom": 40}})
clk.run(0.05)
check(V["zoom"] == 102, "Zoom 40 %: 102")
for pct, val in ((50, 0), (51, 0), (100, 12), (53, 122), (80, 59), (75, 70), (0, 255), (25, 195)):
    sh.command({"beam": {"roll": pct}})
    clk.run(0.05)
    check(V["gobo_rot"] == val, f"Roll {pct} %: {val} ({V['gobo_rot']})")
for pct, val in ((0, 0), (50, 70), (100, 137), (75, 166), (49, 70), (47, 199), (1, 255)):
    sh.command({"beam": {"prism": pct}})
    clk.run(0.05)
    check(V["prism"] == val, f"Prisma {pct} %: {val} ({V['prism']})")

sh.command({"scene": "Switch It Up slow"})
clk.run(0.5)
check(V["gobo"] == 121 and V["prism"] == 255, "feste Szene: Beam gilt auch dort")  # zuletzt Prisma 1 %
zurueck(sh)
sh.command({"beam": {}})
sh.command({"allbright": True})
clk.run(0.1)
check(V["gobo"] == 0 and V["prism"] == 0, "Blinder: Gobo offen wie bisher")
sh.command({"allbright": False})
clk.run(0.1)
check(V["gobo"] == 121, "nach dem Blinder: wieder Beam")

sh.command({"beam": "auto"})
clk.run(0.1)
snap = sh.snapshot()["beam"]
check(snap["auto"] is True and snap["vals"]["gobo"] == 5 and snap["vals"]["zoom"] == 40.0, "Auto: Werte bleiben fuer das naechste Mal gemerkt")
check(V["zoom"] == 255 and V["prism"] == 0, "Auto: Vega wie ohne Beam")
sh.command({"beam": {"roll": 60}})
check(sh.beam["gobo"] == 5 and sh.beam_man, "von Hand: weiter mit den gemerkten Werten")

sh.command({"beam": {"gobo": 9, "zoom": 150, "prism": -5}})
check(sh.beam["gobo"] == 5 and sh.beam["zoom"] == 100.0 and sh.beam["prism"] == 0.0, "Werte begrenzt")
for bad in ({"farbe": 1}, "irgendwas", 5):
    try:
        sh.command({"beam": bad})
        check(False, f"abgelehnt {bad}")
    except (ValueError, TypeError):
        check(True, f"abgelehnt {bad!r}")

# ---- Neustart ----
tmp = tempfile.mkdtemp()


def mk():
    r = Rig(os.path.join(PI, "fixtures.yaml"))
    return sw.Show(r, Simulator(), aim_file=os.devnull, settings_file=os.path.join(tmp, "settings.json"), scenes_file=None,
                   texts_file=None)


s1 = mk()
s1.pilot = False
s1.command({"beam": {"gobo": 3, "zoom": 20, "roll": 80, "prism": 30}})
s1.close()
s2 = mk()
check(s2.pilot and not s2.beam_man and s2.beam == {"gobo": 3, "zoom": 20.0, "roll": 80.0, "prism": 30.0}, "nach dem Neustart: Autopilot, Beam-Werte gemerkt")
s2.command({"master": 0.9})
s2.close()
d = json.load(open(os.path.join(tmp, "levels.json")))
check(d["beam_man"] is False and d["beam"]["gobo"] == 3, "Auto wird gespeichert, Werte bleiben")
check(mk().beam_man is False, "nach dem Neustart: Auto")

# ---- Panel ----
page = webpanel.make_page()
check(page.index('id="move"') < page.index('id="aim"') < page.index('data-tx="h_beam"') < page.index('id="beam"'),
      "Panel: Bereich Beam bei Bewegung, unter den Zielen")
check("function drawBeam()" in page and "c({beam:S.beam.auto?{}:'auto'})" in page and "c({beam:{gobo:+sel.value}})" in page
      and "c({beam:{[k]:+sl.value}})" in page, "Panel: Auto, Gobo-Auswahl und drei Regler")

finish("test_beam")
