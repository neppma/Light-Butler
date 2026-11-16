"""Feinregler unter Bewegung (Fan, Speed, Shift, Size) und Licht-Mix (Fade, Speed, Shift, Size): jeder Knopf hat eigene
Werte (fine.json), 50 % = wie ohne Regler. Center und Static haben keine Regler. Sie wirken nur, wenn ihr Knopf gewaehlt ist
(nicht in festen Szenen, nicht in AUTO ohne Auswahl). Speed ist ein Feinregler zu Low/Med/Hot und springt beim Verstellen nicht."""
import json
import math
import os
import tempfile

from _common import zurueck, build, Clock, check, finish

import fine
import settings
import webpanel
from scenes import BAR_AMP, MOVE_RATE

check(not any(p.key.startswith(("mv_", "mx_")) for p in settings.DEFS), "keine gemeinsamen Feinregler mehr in den Einstellungen")
check(fine.BUTTONS["mv"] == ["duck", "random", "sweep", "circle", "vertical", "horizontal", "fan"], "Bewegung: alle Knoepfe ausser Center")
check("STOP" not in fine.BUTTONS["mx"] and len(fine.BUTTONS["mx"]) == 7, "Licht-Mix: alle Knoepfe ausser Static")

rig, sh = build(seed=3)
clk = Clock(sh)
clk.run(3)
snap = sh.snapshot
check(snap()["fine"] == {"mv": None, "mx": None}, "AUTO ohne Auswahl: keine Regler")


def setf(g, vals):
    btn = snap()["fine"][g]["btn"]
    for k, v in vals.items():
        sh.command({"fine": {"grp": g, "btn": btn, "key": k, "v": v}})


# ---- Bewegung --------------------------------------------------------------------------------
sh.command({"move": "horizontal"})
clk.run(0.5)
check(snap()["fine"]["mv"] == {"btn": "horizontal", "vals": {"fan": 50.0, "speed": 50.0, "shift": 50.0, "size": 50.0}},
      "Bewegungs-Knopf gewaehlt: Regler mit seinen Werten")
mo = dict(sh.mo)
check(abs(mo["fan_amp"] - BAR_AMP["mid"]) < 1e-9 and mo["shift"] == 0.0 and mo["rate"] == MOVE_RATE["mid"], "50 %: wie ohne Regler")
setf("mv", {"fan": 100})
clk.run(0.1)
check(abs(sh.mo["fan_amp"] - 2 * BAR_AMP["mid"]) < 1e-9, "Fan 100 %: doppelter Faecher")
setf("mv", {"fan": 0})
clk.run(0.1)
check(sh.mo["fan_amp"] == 0.0, "Fan 0 %: kein Faecher")
setf("mv", {"size": 0})
clk.run(0.1)
check(sh.mo["u"] == 0.5 and sh.mo["v"] == 0.5 and sh.mo["sway_amp"] == 0.0, "Size 0 %: steht in der Mitte")
setf("mv", {"size": 100})
us = []
clk.run(4, lambda t: us.append(sh.mo["u"]))
check(max(us) > 0.97 and min(us) < 0.03, f"Size 100 %: grosse Bewegung bis zum Rand ({min(us):.2f}..{max(us):.2f})")
setf("mv", {"shift": 0})
clk.run(0.1)
check(abs(sh.mo["shift"] + math.pi / 2) < 1e-9, "Shift 0 %: alle Arme gleich (kein Versatz)")
setf("mv", {"shift": 100})
clk.run(0.1)
check(abs(sh.mo["shift"] - math.pi / 2) < 1e-9, "Shift 100 %: Arme gegenlaeufig")

eng = sh.scenes
ph0 = sh.mo["fan_phase"]
setf("mv", {"speed": 100})
sh.update(clk.t)                                         # gleicher Zeitpunkt: kein Sprung
check(abs(sh.mo["fan_phase"] - ph0) < 1e-6, "Speed verstellen: die Bewegung springt nicht")
check(abs(sh.mo["rate"] - 2 * MOVE_RATE["mid"]) < 1e-9, "Speed 100 %: Vega doppelt so schnell")
a = sh.mo["fan_phase"]
clk.run(1.0)
b1 = sh.mo["fan_phase"] - a
setf("mv", {"speed": 50})
clk.run(0.025)
a = sh.mo["fan_phase"]
clk.run(1.0)
b2 = sh.mo["fan_phase"] - a
check(abs(b1 / b2 - 2.0) < 0.05, f"Speed 100 %: doppelt so schnell wie 50 % ({b1 / b2:.2f})")
setf("mv", {"speed": 0})
clk.run(0.025)
a = sh.mo["fan_phase"]
clk.run(1.0)
check(abs((sh.mo["fan_phase"] - a) / b2 - 0.5) < 0.05, "Speed 0 %: halb so schnell")

# ---- jeder Knopf eigene Werte ----
setf("mv", {"fan": 100, "size": 30, "speed": 50, "shift": 80})
hz = dict(snap()["fine"]["mv"]["vals"])
sh.command({"move": "circle"})
clk.run(0.2)
check(snap()["fine"]["mv"] == {"btn": "circle", "vals": {"fan": 50.0, "speed": 50.0, "shift": 50.0, "size": 50.0}},
      "Kreis hat eigene Werte (noch 50 %)")
check(abs(sh.mo["fan_amp"] - BAR_AMP["mid"]) < 1e-9, "Kreis: Faecher wie ohne Regler")
setf("mv", {"fan": 20})
sh.command({"move": "horizontal"})
clk.run(0.2)
check(snap()["fine"]["mv"]["vals"] == hz and abs(sh.mo["fan_amp"] - 2 * BAR_AMP["mid"]) < 1e-9,
      "zurueck zu Rechts-Links: seine Werte sind wieder da")
check(sh.fine.get("mv", "circle")["fan"] == 20.0, "Kreis behaelt seine 20 %")
try:
    sh.command({"fine": {"grp": "mv", "btn": "circle", "key": "fan", "v": 90}})
    check(False, "nicht gewaehlter Knopf")
except ValueError:
    check(sh.fine.get("mv", "circle")["fan"] == 20.0, "Wert fuer einen nicht gewaehlten Knopf wird abgelehnt")

# Center: keine Regler, Bewegung wie ohne Regler
setf("mv", {"speed": 100})
sh.command({"move": "home"})
clk.run(0.3)
check(snap()["fine"]["mv"] is None, "Center: keine Regler")
check(sh.mo["fan_amp"] == 0.0 and "shift" not in sh.mo and sh.mo["rate"] == MOVE_RATE["mid"], "Center: Bewegung wie ohne Regler")
try:
    sh.command({"fine": {"grp": "mv", "btn": "home", "key": "fan", "v": 90}})
    check(False, "Center")
except ValueError:
    check(True, "Center: Werte werden abgelehnt")
sh.command({"move": "home"})                           # abwaehlen
clk.run(0.2)
check(snap()["fine"]["mv"] is None, "keine Bewegung gewaehlt: keine Regler")

# feste Szene: Regler wirken nicht
sh.command({"scene": "Switch It Up slow"})
clk.run(0.5)
check(snap()["fine"] == {"mv": None, "mx": None}, "feste Szene: keine Regler")
if sh.mo is not None and "fan_amp" in sh.mo:
    check(sh.mo["fan_amp"] in (0.0, 5.0, BAR_AMP[sh.sc.mspeed]) and "shift" not in sh.mo, "feste Szene: Faecher wie ohne Regler")
zurueck(sh)

# ---- Licht-Mix ----------------------------------------------------------------------------------
clk.run(0.5)
check(eng.mxf is None or sh.sc is None, "AUTO: kein Licht-Mix gewaehlt")
sh.command({"mix": "Karussell"})
clk.run(0.5)
check(snap()["fine"]["mv"] is None and snap()["fine"]["mx"]["btn"] == "Karussell", "Licht-Mix-Knopf gewaehlt: nur die Mix-Regler")
check(eng.mxf == (1.0, 0.0, 1.0, 1.0), "50 %: wie ohne Regler")
setf("mx", {"fade": 100, "speed": 100, "shift": 0, "size": 100})
clk.run(0.1)
check(eng.mxf == (2.0, -1.0, 2.0, 4.0), f"100/100/0/100 %: Speed x2, Shift eine Welle, Size x2, Fade x4 ({eng.mxf})")
sh.command({"mix": "Discokugel"})
clk.run(0.1)
check(eng.mxf == (1.0, 0.0, 1.0, 1.0), "Discokugel: eigene Werte (50 %)")
setf("mx", {"speed": 0})
sh.command({"mix": "Karussell"})
clk.run(0.1)
check(eng.mxf == (2.0, -1.0, 2.0, 4.0) and sh.fine.get("mx", "Discokugel")["speed"] == 0.0, "Karussell und Discokugel getrennt")
setf("mx", {"fade": 0, "speed": 0, "size": 0})
clk.run(0.1)
check(eng.mxf[0] == 0.5 and eng.mxf[2] == 0.5 and eng.mxf[3] == 0.25, "0 %: halb so schnell, halb so breit, viermal haerter")
sh.command({"mix": "STOP"})
clk.run(0.1)
check(snap()["fine"]["mx"] is None and snap()["mixbtn"] == "STOP", "Static: keine Regler (Licht eingefroren)")
sh.command({"mix": "STOP"})                            # nochmal: Einfrieren aus, Karussell laeuft weiter
clk.run(0.1)
def mean_val(size):
    eng.mxf = (1.0, 0.0, size, 1.0)
    z = eng.zones[0]
    return sum(eng.mix_value(sh.sc, z, i / 50.0, 0.0, 0.025, False, 0.0) for i in range(100)) / 100.0


check(mean_val(2.0) > 1.5 * mean_val(1.0) > 1.5 * mean_val(0.5) > 0, "Size: breiterer Lichtbereich beim Karussell")
eng.mxf = (1.0, 0.25, 1.0, 1.0)
z1, z2 = eng.zones[0], eng.zones[-1]
v1 = [eng.mix_value(sh.sc, z, 0.3, 0.0, 0.025, False, 0.0) for z in (z1, z2)]
eng.mxf = (1.0, 0.0, 1.0, 1.0)
v0 = [eng.mix_value(sh.sc, z, 0.3, 0.0, 0.025, False, 0.0) for z in (z1, z2)]
check(v1 != v0, "Shift: Versatz zwischen den Geraeten aendert das Muster")
b = eng.beatpos
x1 = eng._scaled("mix", 1.0, b)
x2 = eng._scaled("mix", 2.0, b)
check(abs(x1 - x2) < 1e-9 and abs(eng._scaled("mix", 2.0, b + 1.0) - x2 - 2.0) < 1e-9, "Mix-Speed: kein Sprung, danach doppelt so schnell")

# feste Szene: Mix-Regler wirken nicht
sh.command({"scene": "Switch It Up slow"})
clk.run(0.2)
check(eng.mxf is None and snap()["fine"]["mx"] is None, "feste Szene: Mix-Regler wirken nicht")
zurueck(sh)

# Regenbogen-Knopf (bleibt in AUTO): Size verteilt die Farben, Shift dreht sie, Speed laesst sie schneller laufen
sh.command({"mix": "Regenbogen"})
clk.run(0.2)
check(sh.sc is None and snap()["fine"]["mx"]["btn"] == "Regenbogen", "Regenbogen: Mix-Regler wirken")
fx = rig["vega"]
h0 = sh._rainbow_hue(fx)
setf("mx", {"shift": 100})
check(abs((sh._rainbow_hue(fx) - h0) % 1.0 - 0.5) < 1e-9, "Regenbogen Shift 100 %: Farben um eine halbe Runde gedreht")
r0 = sh.rb_beats
clk.run(1.0)
d50 = sh.rb_beats - r0
setf("mx", {"speed": 100})
r0 = sh.rb_beats
clk.run(1.0)
check(abs((sh.rb_beats - r0) / d50 - 2.0) < 0.05, "Regenbogen Speed 100 %: doppelt so schnell")

# ---- Speichern in fine.json ----
tmp = os.path.join(tempfile.mkdtemp(), "fine.json")
st = fine.FineStore(tmp)
st.set("mv", "duck", "fan", 77)
st.set("mx", "Scanner", "size", 10)
st.set("mx", "Scanner", "fade", 50)
st2 = fine.FineStore(tmp)
check(st2.get("mv", "duck")["fan"] == 77.0 and st2.get("mx", "Scanner") == {"fade": 50.0, "speed": 50.0, "shift": 50.0, "size": 10.0},
      "Werte je Knopf bleiben nach dem Neustart")
check(st2.get("mv", "home") is None and st2.get("mx", "STOP") is None, "Center und Static: keine Werte")
st2.set("mv", "duck", "fan", 50)
check(json.load(open(tmp))["mv"] == {}, "50 % wird nicht gespeichert")
for bad in (("mv", "home", "fan"), ("mx", "STOP", "fade"), ("mv", "duck", "fade"), ("xx", "duck", "fan")):
    try:
        st2.set(*bad, 10)
        check(False, f"abgelehnt {bad}")
    except ValueError:
        check(True, f"abgelehnt {bad}")
st2.set("mv", "duck", "size", 500)
check(st2.get("mv", "duck")["size"] == 100.0, "Werte auf 0 bis 100 % begrenzt")
open(tmp, "w").write('{"mv": {"duck": {"fan": "x"}, "home": {"fan": 10}}, "mx": 3}')
check(fine.FineStore(tmp).get("mv", "duck")["fan"] == 50.0, "defekte fine.json: alles 50 %")
check(build()[1].fine.path is None, "Tests schreiben keine fine.json")
# ---- Panel ---------------------------------------------------------------------------------------
page = webpanel.make_page()
check(page.index('id="mix"') < page.index('id="fine_mx"') < page.index('data-tx="h_move"') < page.index('id="move"') < page.index('id="fine_mv"')
      < page.index('data-tx="h_aim"'), "Panel: Regler direkt unter Licht-Mix und unter Bewegung")
check("const FINE={mv:['fan','speed','shift','size'],mx:['fade','speed','shift','size']}" in page,
      "Panel: Reihenfolge Fan, Speed, Shift, Size und Fade, Speed, Shift, Size")
check("c({fine:{grp:g,btn:a.btn,key:k,v:x}})" in page and "box.classList.toggle('off',!a)" in page and "sl.disabled=!a" in page,
      "Panel: Regler speichern fuer den gewaehlten Knopf, ausgegraut und gesperrt ohne Knopf")

finish("test_feinregler")
