"""Drei neue Geraetetypen (27.11.2026, Anleitungen vom Nutzer): Six-armed King Kong (26 Kanaele, mit Laser), Eurolite LED Mini
Strobe Cluster SMD 48 (3 Kanaele, nur Weiss) und FM-1500 Nebelmaschine mit RGB-LEDs (7 Kanaele). Alle Sperren wie bei den
bisherigen Typen: Laser 0 ausser in der Szene Laser, Makro/Reset und Programme begrenzt, Strobe nur mit Erlaubnis, die
Nebelmaschine nie von allein, nur der Nebel-Knopf (ihre LEDs leuchten dann in der Farbe der Show)."""
import os
import tempfile
import time

import yaml

from _common import PI, Clock, build, check, finish

import dmx
import fixture_edit as fe
from showman import fixtures as fm

with open(os.path.join(PI, "fixtures.yaml"), encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
T = cfg["types"]
for t, n in (("kingkong_6arm", 26), ("eurolite_smd48", 3), ("fog_fm1500", 7)):
    check(t in T and T[t]["channels"] == n and sorted(T[t]["map"].values()) == list(range(1, n + 1)), f"{t}: {n} Kanaele, jeder genau einmal")
    check(T[t].get("label") and all(p in T[t]["desc"] for p in T[t]["map"]), f"{t}: Name und Beschreibung jedes Kanals")
summ = {x["name"]: x for x in fe.type_summary(cfg)}
check(summ["kingkong_6arm"]["groups"][0] == "bars" and "fx" in summ["kingkong_6arm"]["groups"], "King Kong: bewegt sich wie die Spider oder als Effekt")
check(summ["eurolite_smd48"]["groups"] == ["fx", "wash", "bar"], "Eurolite: Weisslicht in Effekt, Wash oder Barlicht")
check(summ["fog_fm1500"]["groups"] == ["locked"], "FM-1500: ganz gesperrt wie der Hazer")

# Aufbau mit allen drei Geraeten, ohne Nanoleaf
cfg["nanoleaf_file"] = ""
cfg["fixtures"] += [{"name": "kk", "nr": 30, "label": "King Kong", "type": "kingkong_6arm", "address": 451, "group": "bars"},
                    {"name": "smd", "nr": 31, "label": "Strobe Cluster", "type": "eurolite_smd48", "address": 481, "group": "fx"},
                    {"name": "fm", "nr": 32, "label": "FM-1500", "type": "fog_fm1500", "address": 491, "group": "locked"}]
path = os.path.join(tempfile.mkdtemp(prefix="s2l_neu_"), "fixtures.yaml")
with open(path, "w", encoding="utf-8") as f:
    yaml.safe_dump(cfg, f, allow_unicode=True)
rig = dmx.Rig(path)
check(rig.check() == [], "Adressen und Kanaele in Ordnung")
kk, smd, fmx = rig["kk"], rig["smd"], rig["fm"]


def dmxv(fx, p):
    return rig.render_all()[rig.target][fx.address - 1 + fx.map[p] - 1]


# ---- King Kong ----
for p in ("laser_red", "laser_green"):
    kk.set(p, 255)
check(dmxv(kk, "laser_red") == 0 and dmxv(kk, "laser_green") == 0, "King Kong: Laser bleiben 0, auch wenn gesetzt")
kk.set("mode", 255)
kk.set("strip1", 200)
check(dmxv(kk, "mode") == 50 and dmxv(kk, "strip1") == 9, "King Kong: Makro hoechstens 50 (nie Reset), LED-Streifen-Programme aus")
kk.mode_unlock = True
kk.set("mode", 255)
check(dmxv(kk, "mode") == 50, "King Kong: Reset 251-255 auch in der Szene Laser nie")
kk.mode_unlock = False
check(kk.zones() == [{"r": "r", "g": "g", "b": "b", "w": "w"}], "King Kong: eine Farbzone RGBW")

# ---- Eurolite ----
check(smd.zones() == [{"w": "w"}], "Eurolite: eine Zone nur Weiss")
smd.set_color(r=255, g=0, b=0)
check(dmxv(smd, "w") == 0, "Eurolite: bei Rot dunkel")
smd.set_color(w=255)
check(dmxv(smd, "w") == 255, "Eurolite: bei Weiss hell")
smd.set("effect", 254)
check(dmxv(smd, "effect") == 36, "Eurolite: Effekt hoechstens 36 (keine eigenen Programme, keine Musiksteuerung)")

# ---- FM-1500: gesperrt, nur Handbetrieb ----
check(fmx.locked and fmx.manual_ok and fmx.fog, "FM-1500: gesperrt, Nebel-Knopf erlaubt, gilt als Nebelmaschine")
for p in fmx.map:
    fmx.set(p, 255)
check(all(dmxv(fmx, p) == 0 for p in fmx.map), "FM-1500: alle Kanaele 0, auch die LEDs")
check([a["attr"] for a in fm.attrs_for(fmx)] == ["fog"], "Showmanager: nur die Spur Nebel")
src = bytearray([255] * 512)
dst = bytearray(512)
dmx.filter_external(fmx, src, dst, True)
dmx.filter_external(kk, src, dst, False)
check(not any(dst[fmx.address - 1:fmx.address + 6]), "Art-Net-Eingang: FM-1500 bleibt 0")
check(dst[kk.address - 1 + kk.map["laser_red"] - 1] == 0 and dst[kk.address - 1 + kk.map["strobe"] - 1] == 0
      and dst[kk.address - 1 + kk.map["mode"] - 1] == 50, "Art-Net-Eingang: King-Kong-Laser 0, ohne Erlaubnis kein Strobe, Makro begrenzt")

# ---- in der laufenden Show ----
rig2, sh = build(seed=4, strobe=False, config=path, pilot=True)
kk2, smd2, fm2 = rig2["kk"], rig2["smd"], rig2["fm"]
seen = {"fog": 0, "laser": 0, "strobe": 0, "tilt_moves": set()}


def watch(t):
    fr = rig2.render_all()[rig2.target]
    g = lambda fx, p: fr[fx.address - 1 + fx.map[p] - 1]
    seen["fog"] = max(seen["fog"], *(g(fm2, p) for p in fm2.map))
    seen["laser"] = max(seen["laser"], g(kk2, "laser_red"), g(kk2, "laser_green"))
    seen["strobe"] = max(seen["strobe"], g(kk2, "strobe"), g(kk2, "strobe_a"), g(kk2, "strobe_b"), g(smd2, "strobe"))
    seen["tilt_moves"].add((g(kk2, "tilt1"), g(kk2, "tilt3"), g(kk2, "tilt2"), g(kk2, "tilt4")))


clk = Clock(sh)
clk.run(90, watch)
check(seen["fog"] == 0, "Show 90 s: FM-1500 bleibt aus (kein Nebel, keine LEDs)")
check(seen["laser"] == 0, "Show 90 s: King-Kong-Laser bleiben aus")
check(seen["strobe"] == 0, "Show ohne Strobe-Erlaubnis: kein Strobe-Kanal an")
check(len(seen["tilt_moves"]) > 10 and all(t1 == t3 and t2 == t4 for t1, t3, t2, t4 in seen["tilt_moves"]),
      "King Kong: Arme bewegen sich, 1/3/5 wie tilt1, 2/4/6 wie tilt2")

# Nebel-Knopf: alle Nebelmaschinen, LEDs in der Farbe der Show
sh.cfg.set("fog_via", 0)
T0 = [5000.0]
sh._fog_clock = lambda: T0[0]
sh.command({"hold": {"name": "fog", "on": True}})
time.sleep(0.02)
clk.run(0.1)
fr = rig2.render_all()[rig2.target]
rgb = tuple(fr[fm2.address - 1 + fm2.map[p] - 1] for p in ("r", "g", "b"))
hz = rig2["hazer"]
check(fr[fm2.address - 1] == 255 and fr[hz.address - 1] == 150, "Nebel-Knopf: FM-1500 und Hazer nebeln beide")
check(rgb == sh._fog_rgb() and any(rgb), "FM-1500: LEDs leuchten waehrend des Schubs in der Farbe der Show")
check(fr[fm2.address - 1 + fm2.map["strobe"] - 1] == 0 and fr[fm2.address - 1 + fm2.map["led_mode"] - 1] == 0, "FM-1500: kein Strobe, keine LED-Programme")
sh.command({"hold": {"name": "fog", "on": False}})
clk.run(0.1)
fr = rig2.render_all()[rig2.target]
check(not any(fr[fm2.address - 1:fm2.address + 6]), "Loslassen: FM-1500 sofort ganz aus")
check(fm2 in [f for f in rig2.fixtures if f.fog] and hz.fog, "Hazer und FM-1500 gelten als Nebelmaschinen")

finish("test_neue_geraete")
