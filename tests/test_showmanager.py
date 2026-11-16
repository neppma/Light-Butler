"""Showmanager, Backend: Patterns, Timeline, Uhr, Engine mit allen Sicherheitsgrenzen, Dateiverwaltung, HTTP und WebSocket."""
import base64
import http.client
import io
import json
import math
import os
import shutil
import socket
import struct
import tempfile
import threading
import time

from _common import DT, Clock, build, check, finish, zurueck, ch, sw

import dmx
import webpanel
from showman import analysis, fixtures as fm, patterns as pt, timeline as tl, ws
from showman.api import ShowManager, parse_range
from showman.clock import MasterClock
from showman.engine import EB_STROBE, FlashLimiter, PlaybackEngine
from showman.store import ShowStore, check_name

check(EB_STROBE == sw.EB_STROBE, "Blitz-Presets wie in show.py")


def show_doc(**kw):
    d = tl.new_show("Test")
    d.update(duration=60.0, bpm=120.0, **kw)
    return d


def track(fx, attr, keys=(), clips=(), group=None):
    return {"target": {"group": group} if group else {"fixture": fx}, "attr": attr, "keys": list(keys), "clips": list(clips)}


def key(t, v, e="linear"):
    return {"t": t, "v": v, "e": e}


def clip(t, d, pattern, **p):
    return {"id": f"c{t}{pattern}", "t": t, "d": d, "pattern": pattern, "p": p}


# ---- Patterns ---------------------------------------------------------------------------------------
print("Patterns")
check(len(pt.REGISTRY) >= 24, "alle Muster aus dem Pflichtenheft vorhanden")
for k in ("fade_in", "fade_out", "blink", "pulse", "strobe", "sine", "color_change", "rgb_fade", "rainbow", "red_blue", "random_color",
          "circle", "eight", "sweep_lr", "sweep_ud", "sine_move", "random_move", "chase", "running", "beat", "group_wave", "fan"):
    check(k in pt.REGISTRY, f"Muster {k}")
for k, d in pt.REGISTRY.items():                                # jedes Muster liefert in jeder Lage gueltige Werte
    p = pt.full_params(k, pt.clean_params(k, {}))
    for t in (0.0, 0.3, 1.7, 9.99):
        for i, n in ((0, 1), (2, 5)):
            v = pt.evaluate(k, p, pt.Ctx(u=t / 10, sec=t, beat=t * 2, i=i, n=n, frame=int(t * 40), seed=7, strobe=True))
            if d["out"] == "scalar":
                good = 0 <= v <= 255
            elif d["out"] == "color":
                good = len(v) == 5 and all(0 <= x <= 255 for x in v)
            elif d["out"] in ("laser", "fog", "nano_fx", "panel"):
                good = True
            else:
                good = len(v) == 2 and all(0 <= x <= 1 for x in v)
            if not good:
                check(False, f"{k} liefert ungueltigen Wert {v}")
p = pt.full_params("random_color", pt.clean_params("random_color", {"speed": 2}))
a = pt.evaluate("random_color", p, pt.Ctx(sec=3.2, seed=5))
b = pt.evaluate("random_color", p, pt.Ctx(sec=3.2, seed=5))
check(a == b, "Zufallsmuster: dasselbe Bild beim Springen")
p = pt.full_params("solid_color", pt.clean_params("solid_color", {"color_a": "#102030", "fade_in": 2, "intensity": 0.5}))
check(pt.evaluate("solid_color", p, pt.Ctx(u=0.1)) == (8.0, 16.0, 24.0, 0.0, 0.0) and pt.evaluate("solid_color", p, pt.Ctx(u=0.9)) == (8.0, 16.0, 24.0, 0.0, 0.0), "Einzelfarbe: bleibt gleich, Intensitaet wirkt")
check("fade_in" in pt.REGISTRY["solid_color"]["params"] and "speed" not in pt.REGISTRY["solid_color"]["params"], "Einzelfarbe: mit Fades, ohne Geschwindigkeit")
check(pt.clip_seed("abc") == 440920331, "Zufall haengt nicht vom Programmstart ab")
p = pt.full_params("fade_in", pt.clean_params("fade_in", {"start": 10, "end": 110}))
check(abs(pt.evaluate("fade_in", p, pt.Ctx(u=0.5)) - 60) < 0.01, "Anfangs- und Endwert wirken")
p = pt.full_params("blink", pt.clean_params("blink", {"repeat": 4}))
check(pt.evaluate("blink", p, pt.Ctx(u=0.01)) == 255 and pt.evaluate("blink", p, pt.Ctx(u=0.2)) == 0, "Wiederholungen ueber den Clip verteilt")
p = pt.full_params("chase", pt.clean_params("chase", {"speed": 1}))
on = [pt.evaluate("chase", p, pt.Ctx(sec=0.45, i=i, n=4)) for i in range(4)]
check(sum(1 for x in on if x) == 1, "Chase: genau ein Geraet an")
check(pt.clean_params("sine", {"speed": 9999})["speed"] == 20.0, "Parameter werden begrenzt")
try:
    pt.clean_params("color_change", {"color_a": "nix"})
    check(False, "falsche Farbe abgelehnt")
except ValueError:
    check(True, "falsche Farbe abgelehnt")

# ---- Timeline ----------------------------------------------------------------------------------------
print("Timeline")
rig, sh = build(strobe=False)
d = show_doc(tracks=[track("vega", "dimmer", keys=[key(10, 0), key(20, 200), key(30, 100, "constant"), key(40, 0)])])
c = tl.compile_show(d, rig)
ev = lambda t: c.evaluate(t).get("vega", {}).get("dimmer")
check(ev(5) == 0 and ev(15) == 100 and ev(60) == 0, "Keyframes: halten und linear interpolieren")
check(ev(35) == 100, "Interpolation konstant")
check(tl.ease("ease_in", 0.5) == 0.25 and tl.ease("ease_out", 0.5) == 0.75 and tl.ease("ease_in_out", 0.5) == 0.5 and tl.ease("constant", 0.9) == 0, "alle Interpolationen")
d = show_doc(tracks=[track("par", "dimmer", keys=[key(0, 50)], clips=[clip(10, 10, "fade_in", start=0, end=250, fade_out=2)])])
c = tl.compile_show(d, rig)
ev = lambda t: c.evaluate(t)["par"]["dimmer"]
check(ev(5) == 50 and abs(ev(15) - 125) < 0.01, "Clip liegt ueber den Keyframes")
check(abs(ev(19) - (50 + (225 - 50) * 0.5)) < 0.01, "Fade Out blendet zum Keyframe zurueck")
check(ev(25) == 50, "nach dem Clip wieder Keyframe")
# Fehlerbericht: Blinken langsam auf- und abdimmen. Der Standardwert des Dimmer-Kanals (255) darf nicht durchscheinen
d = show_doc(tracks=[track("", "dimmer", clips=[clip(0, 10, "blink", speed=2, fade_in=4, fade_out=4)], group="rig_bars")])
c = tl.compile_show(d, rig)
ev = lambda t: c.evaluate(t)["docooler_1"]["dimmer"]
check(ev(0.05) < 10 and ev(0.3) == 0, "Fade In: beginnt dunkel, auch in den Hellphasen")
check(ev(1.05) < ev(2.05) < ev(3.05) < 255 and ev(5.05) == 255, "Fade In: die Blitze werden gleichmaessig heller")
check(ev(5.3) == 0 and ev(1.3) == 0, "Dunkelphasen bleiben dunkel")
check(ev(9.55) < ev(8.05) < 255 and ev(9.8) == 0, "Fade Out: die Blitze werden dunkler")
d = show_doc(tracks=[track("par", "dimmer", clips=[clip(0, 10, "sine", speed=1, fade_in=5)])])
c = tl.compile_show(d, rig)
check(c.evaluate(0.5)["par"]["dimmer"] < 255 * 0.1 + 1, "auch beim Sinus: Fade In von dunkel")
d = show_doc(tracks=[track("vega", "zoom", clips=[clip(0, 10, "sine", speed=1, fade_in=5)])])
check(tl.compile_show(d, rig).evaluate(0.0)["vega"]["zoom"] == 255, "andere Kanaele blenden weiter von ihrem Standardwert")
d = show_doc(groups=[{"id": "g1", "name": "Alle", "fixtures": ["docooler_1", "docooler_2", "nanogibtsnicht"]}],
             tracks=[track("", "dimmer", clips=[clip(0, 10, "chase", speed=0.1)], group="g1")])
c = tl.compile_show(d, rig)
st = c.evaluate(1.0)
check(st["docooler_1"]["dimmer"] != st["docooler_2"]["dimmer"], "Gruppe: Chase verteilt sich ueber die Geraete")
check(any("nanogibtsnicht" in w for w in c.warnings), "fehlendes Geraet gibt einen Hinweis, keinen Absturz")
d = show_doc(tracks=[track("par", "dimmer", keys=[key(0, 50)]), track("", "dimmer", keys=[key(0, 200)], group="rig_ambient")])
c = tl.compile_show(d, rig)
check(c.evaluate(1.0)["par"]["dimmer"] == 200, "Dimmer: hellster Wert gewinnt (auch vorgegebene Gruppen)")
d = show_doc(scenes=[{"id": "s1", "name": "Rot", "values": {"par": {"dimmer": 255, "color": [255, 0, 0, 0, 0]}}}],
             scene_clips=[{"t": 10, "d": 10, "scene": "s1", "fade_in": 2}])
c = tl.compile_show(d, rig)
check("par" not in c.evaluate(5) and abs(c.evaluate(11)["par"]["dimmer"] - 127.5) < 0.01 and c.evaluate(15)["par"]["color"][0] == 255, "Szene mit Fade In")
d = show_doc(tracks=[track("vega", "dimmer", clips=[clip(0, 10, "circle")])])
check(tl.compile_show(d, rig).evaluate(1.0) == {}, "Muster passt nicht zur Spur: wirkt nicht")
big = show_doc(tracks=[track("vega", "dimmer", keys=[key(i * 0.1, i % 255) for i in range(20000)],
                             clips=[clip(i * 0.5, 0.4, "sine") for i in range(5000)])])
c = tl.compile_show(big, rig)
t0 = time.perf_counter()
for i in range(400):
    c.evaluate(i * 2.5)
check((time.perf_counter() - t0) / 400 < 0.002, "20000 Keyframes und 5000 Clips auf einer Spur: unter 2 ms je Bild")
for bad, what in (([1, 2], "kein Objekt"), ({"tracks": [{"clips": [{"pattern": "gibtsnicht"}]}]}, "unbekanntes Muster")):
    try:
        tl.normalize(bad)
        check(False, f"{what} abgelehnt")
    except ValueError:
        check(True, f"{what} abgelehnt")

# ---- Uhr ----------------------------------------------------------------------------------------------
print("Uhr")
ck = MasterClock()
ck.start(0.0, 1000.0)
check(ck.position(1010.0) == 10.0, "laeuft zwischen den Meldungen selbst")
# Der Browser laeuft 0,1 % schneller, Netz streut +-30 ms, eine ganze Stunde lang
import random
rnd = random.Random(3)
now, worst = 1000.0, 0.0
for i in range(3600 * 4):
    now += 0.25
    audio = (now - 1000.0) * 1.001
    ck.report(audio + rnd.uniform(-0.03, 0.03), now)
    if i > 40:
        worst = max(worst, abs(ck.position(now) - audio))
check(worst < 0.05, f"keine Drift ueber eine Stunde bei 0,1 % Abweichung (hoechstens {worst * 1000:.0f} ms)")
ck = MasterClock()
ck.start(0.0, 0.0)
ck.report(1.0, 1.0)
ck.report(5.0, 1.25)
check(abs(ck.position(1.25) - 5.0) > 1, "ein einzelner Ausreisser springt nicht")
ck.report(1.5, 1.5)
check(abs(ck.position(1.5) - 1.5) < 0.05, "nach dem Ausreisser weiter auf Kurs")
ck = MasterClock()
ck.start(0.0, 0.0)
for t in (0.25, 0.5, 0.75):
    ck.report(t + 20.0, t)
check(abs(ck.position(0.75) - 20.75) < 0.01 and ck.jumps == 1, "echter Sprung (Puffern) wird uebernommen")
ck = MasterClock()
ck.start(0.0, 0.0)
ck.report(0.45, 0.25)
check(ck.rate > 1.0 and ck.rate <= 1.04, "kleine Abweichung: sanft nachziehen, hoechstens 4 %")
check(ck.source(0.5) == "browser", "Quelle Browser")
ck.tick(5.0)
check(ck.rate == 1.0 and ck.source(5.0) == "frei", "Browser weg: laeuft mit Tempo 1 frei weiter")

# ---- Tempo --------------------------------------------------------------------------------------------
print("Tempo")
for bpm, off in ((128.0, 0.2), (100.0, 0.35), (174.0, 0.1)):
    rate = 100
    x = [0.0] * (rate * 40)
    per = 60.0 / bpm
    b = off
    while b < 40:
        for k in range(12):
            j = int(b * rate) + k
            if j < len(x):
                x[j] = max(x[j], math.exp(-k / 4.0))
        b += per
    res = analysis.estimate_tempo(x, rate)
    ok = min(abs(res["bpm"] - bpm), abs(res["bpm"] - bpm * 2), abs(res["bpm"] - bpm / 2)) < 1.0
    check(ok, f"{bpm} BPM erkannt ({res['bpm']})")
    grid = 60.0 / res["bpm"]
    diff = (res["offset"] - off) % grid
    check(min(diff, grid - diff) < 0.03, f"Beat-Raster trifft ({res['offset']} s)")
check(analysis.estimate_tempo([0.0] * 100)["bpm"] == 0.0, "zu wenig Daten: kein Tempo")

# ---- Sicherheit der Spuren ----------------------------------------------------------------------------
print("Spuren und Sperren")
names = {a["attr"] for f in rig.fixtures for a in fm.attrs_for(f)}
check(not any(p in names for p in ("power", "laser_red", "laser_red1", "motor_speed", "laser_effect", "pump", "reset", "mode", "speed_mode", "function")),
      "einzelne Laser- und Hazer-Kanaele, Mode und Reset werden nie als Spur angeboten")
check([a["attr"] for a in fm.attrs_for(rig["hazer"])] == ["fog"] and [a["attr"] for a in fm.attrs_for(rig["laser"])] == ["laser"], "Hazer und KTV-Laser: nur die eigene Spur")
vega = {a["attr"] for a in fm.attrs_for(rig["vega"])}
check({"dimmer", "move", "pan", "tilt", "gobo", "colorwheel"} <= vega and "color" not in vega, "Vega: Dimmer, Bewegung, Pan, Tilt, Gobo, Farbrad")
doco = {a["attr"] for a in fm.attrs_for(rig["docooler_1"])}
check({"dimmer", "color", "move", "tilt1"} <= doco, "Docooler: Dimmer, Farbe, Bewegung")
check(rig["vega"].extra.get("limits_verified") and "move" in vega, "Vega bewegt sich nur mit bestaetigten Grenzen")
rig["vega"].extra["limits_verified"] = False
check("move" not in {a["attr"] for a in fm.attrs_for(rig["vega"])} and "pan" not in {a["attr"] for a in fm.attrs_for(rig["vega"])}, "ohne Bestaetigung keine Pan/Tilt-Spur")
rig["vega"].extra["limits_verified"] = True


# Feste Stufen: Auswahl mit Namen, springen immer
eb = next(a for a in fm.attrs_for(rig["effektband"]) if a["attr"] == "preset")
check(eb["stepped"] and {"v": 1, "label": "1 Austria"} in eb["options"], "Effektband: Presets mit Namen")
check(any("♫" in o["label"] for o in eb["options"]) and any(o["v"] == 32 and "⚡" in o["label"] for o in eb["options"]), "Presets: Ton und Blitz erkennbar")
go = next(a for a in fm.attrs_for(rig["vega"]) if a["attr"] == "gobo")
check(go["stepped"] and {"v": 21, "label": "Stern"} in go["options"], "Gobo mit Namen")
check(next(a for a in fm.attrs_for(rig["vega"]) if a["attr"] == "colorwheel")["options"][1]["label"] == "Rot", "Farbrad mit Namen")
check(not next(a for a in fm.attrs_for(rig["vega"]) if a["attr"] == "pan").get("stepped"), "Pan bleibt stufenlos")
c = tl.compile_show(show_doc(tracks=[track("effektband", "preset", keys=[key(0, 5), key(10, 20)]), track("vega", "pan", keys=[key(0, 100), key(10, 150)])]), rig)
check(c.evaluate(5)["effektband"]["preset"] == 5, "Preset springt, auch wenn in der Datei Linear steht")
check(c.evaluate(5)["vega"]["pan"] == 125, "stufenlose Spur blendet weiter")

# ---- Engine in der Show -------------------------------------------------------------------------------
print("Engine")
def rig_engine(strobe=False):
    r, s = build(strobe=strobe)
    e = PlaybackEngine(r)
    s.showman = e
    return r, s, e


# Regression: Engine vorhanden, aber nichts abgespielt: Bild fuer Bild wie ohne
r1, s1 = build(seed=5)
r2, s2, e2 = rig_engine(strobe=True)
s2._rng.seed(5)
c1, c2 = Clock(s1), Clock(s2)
same = True
for i in range(400):
    c1.run(DT)
    c2.run(DT)
    if r1.render_all() != r2.render_all():
        same = False
        break
check(same, "ohne laufende Show bleibt das Licht Bild fuer Bild gleich")

r, s, e = rig_engine()
c_ = Clock(s)
e.load(show_doc(tracks=[track("par", "dimmer", keys=[key(0, 255)]), track("par", "color", keys=[key(0, [255, 0, 128, 0, 0])]),
                        track("vega", "dimmer", keys=[key(0, 128)]), track("vega", "move", clips=[clip(0, 60, "circle", speed=0.1)]),
                        track("uv_bar", "dimmer", keys=[key(0, 255)]), track("docooler_2", "dimmer", keys=[key(0, 255)]),
                        track("effektband", "preset", keys=[key(0, 14, "constant")]),
                        track("theke", "color", keys=[key(0, [0, 255, 0, 0, 0])])]))
s.command({"auto": True})
e.play(c_.t, 0.0, True, "c1")
c_.run(1.0)
check(s.showman.active() and s.status.startswith("SHOW"), "Show steuert das Licht, Anzeige SHOW")
check(s.snapshot()["sm_show"] == "Test", "Panel sieht die laufende Show")
check(ch(r, "par", "r") == 255 and ch(r, "par", "b") == 128 and ch(r, "par", "g") == 0, "Farbe und Dimmer am PAR")
check(ch(r, "vega", "dimmer") == 128, "Dimmer ohne Farbzonen am Dimmer-Kanal")
check(ch(r, "uv_bar", "uv1") == 255 and ch(r, "uv_bar", "uv4") == 255, "UV-Leiste: nur Dimmer genuegt")
check(ch(r, "docooler_2", "w1") == 255 and ch(r, "docooler_2", "w2") == 255, "Docooler: nur Dimmer = weiss")
check(ch(r, "effektband", "preset") == 14 and ch(r, "effektband", "dimmer") == 255, "Effektband-Preset")
check(ch(r, "theke", "g") == 255, "WLED Theke")
check(ch(r, "docooler_1", "w1") == 0 and ch(r, "docooler_1", "r1") == 0, "Geraete ohne Spur bleiben dunkel")
lo, hi = r["vega"].limits["pan"]
pans = set()
c_.run(5.0, lambda t: pans.add(ch(r, "vega", "pan")))
check(len(pans) > 5 and min(pans) >= lo and max(pans) <= hi, "Bewegung bleibt im erlaubten Bereich")

s.master = 0.5
c_.run(0.1)
check(ch(r, "par", "r") == 128, "General Dimmer wirkt")
s.master = 1.0
s.command({"blackout": True})
c_.run(0.1)
check(ch(r, "par", "r") == 0 and ch(r, "vega", "dimmer") == 0, "BLACKOUT: alles dunkel")
s.command({"blackout": False})
c_.run(0.1)
check(ch(r, "par", "r") == 255, "nach BLACKOUT weiter in der Show")
s.command({"allbright": True})
c_.run(0.1)
check(ch(r, "docooler_1", "w1") > 0 or ch(r, "docooler_1", "r1") > 0, "ALLES HELL geht vor")
s.command({"allbright": False})
s.command({"freeze": True})
c_.run(0.1)
v0 = r.render()
c_.run(0.5)
check(r.render() == v0, "FREEZE haelt das Bild")
s.command({"freeze": False})
p0 = e.position(c_.t)
e.pause(c_.t)
c_.run(0.5)
check(abs(e.position(c_.t) - p0) < 0.001 and s.showman.active() and ch(r, "par", "r") == 255, "Pause: Position steht, Licht bleibt")
e.seek(30.0, c_.t)
check(abs(e.position(c_.t) - 30.0) < 0.001, "Sprung")
e.stop(c_.t)
c_.run(0.5)
check(not e.active() and not e.dirty and s.snapshot()["sm_show"] == "", "Stop: zurueck zur Musiksteuerung")
check(not s.status.startswith("SHOW"), "Anzeige wieder normal")

# Laser, Hazer, Grenzen: auch wenn eine Showdatei von Hand alles eintraegt
r, s, e = rig_engine(strobe=True)
c_ = Clock(s)
danger = [track("laser", p, keys=[key(0, [255] * 5 if p == "color" else 255)]) for p in r["laser"].map]
danger += [track("hazer", "pump", keys=[key(0, 255)]), track("hazer", "fan", keys=[key(0, 255)])]
danger += [track("eyes", p, keys=[key(0, 255)]) for p in r["eyes"].locked_params] + [track("derby", p, keys=[key(0, 255)]) for p in r["derby"].locked_params]
danger += [track("rgbuv_7", "mode", keys=[key(0, 255)]), track("docooler_1", "reset", keys=[key(0, 255)]),
           track("vega", "speed_mode", keys=[key(0, 255)]), track("vega", "auto_play", keys=[key(0, 255)]),
           track("eyes", "mode", keys=[key(0, 255)]), track("docooler_2", "tilt1", keys=[key(0, 255)])]
s.command({"auto": False})
s.command({"scene": "Laser"})                                    # auch aus der Szene Laser heraus: Show geht vor, Laser aus
w = e.load(show_doc(tracks=danger))
check(any("laser" in x for x in w) and any("hazer" in x for x in w), "gesperrte Spuren werden gemeldet")
e.play(c_.t, 0.0, True, "c1")
bad = []


def chk(_t):
    f = r.render()
    for fx in r.fixtures:
        vals = {p: f[fx.address - 1 + ch_ - 1] for p, ch_ in fx.map.items()} if not fx.target else None
        if vals is None:
            continue
        if fx.locked and any(vals.values()):
            bad.append(f"{fx.name} gesperrt")
        for p in fx.locked_params:
            if vals[p] != fx.rest.get(p, 0):
                bad.append(f"{fx.name}.{p}={vals[p]}")
        for p, (lo_, hi_) in fx.limits.items():
            if not lo_ <= vals[p] <= hi_:
                bad.append(f"{fx.name}.{p}={vals[p]} ausserhalb Grenze")


c_.run(3.0, chk)
check(not bad, f"Laser, Hazer und safe_limits halten in jedem Bild {bad[:3]}")
f = r.render()
check(f[301 - 1] == 0 and not any(f[300:334]), "KTV: Leistung 0, alle 34 Kanaele 0")
check(not any(fx.laser_unlock or fx.mode_unlock or fx.hw_unlock for fx in r.fixtures), "keine Freigabe gesetzt")
check(not s.laser_on, "Laser aus, auch wenn die Szene Laser gewaehlt war")
e.stop(c_.t)

# Nebel: Handbetrieb bleibt, die Show fasst den Hazer nicht an
r, s, e = rig_engine()
c_ = Clock(s)
e.load(show_doc(tracks=[track("par", "dimmer", keys=[key(0, 255)])]))
e.play(c_.t, 0.0, True, "c1")
c_.run(0.1)
check(ch(r, "hazer", "pump") == 0 and ch(r, "hazer", "fan") == 0, "Hazer laeuft nie von allein")
r["hazer"].manual({"pump": 150, "fan": 100}, 3.0)
c_.run(0.1)
check(ch(r, "hazer", "pump") == 150, "Nebel-Knopf wirkt weiter und wird nicht abgebrochen")
r["hazer"].manual_vals = None

# Strobe ohne Erlaubnis: egal wie schnell programmiert, hoechstens 2 Blitze pro Sekunde


def flashes(r, s, e, c_, fx, p, sec=5.0):
    """Zaehlt unabhaengig: Anstiege um mindestens 48 seit dem letzten Tiefpunkt. Liefert die groesste Zahl in einer Sekunde."""
    times, low, high = [], None, False
    peak = 0

    def each(t):
        nonlocal low, high, peak
        v = ch(r, fx, p)
        if low is None:
            low = v
            return
        if high:
            peak = max(peak, v)
            if v <= peak - 48:
                low, high = v, False
        else:
            low = min(low, v)
            if v - low >= 48:
                times.append(t)
                high, peak = True, v
    c_.run(sec, each)
    return max([sum(1 for x in times if a <= x < a + 1.0) for a in times] or [0])


cases = [("par", "dimmer", "blink", {"speed": 10}, "r"), ("par", "dimmer", "strobe", {"speed": 10}, "r"), ("par", "dimmer", "sine", {"speed": 8}, "r"),
         ("vega", "dimmer", "blink", {"speed": 12}, "dimmer"), ("effektband", "dimmer", "strobe", {"speed": 20}, "dimmer"),
         ("par", "color", "red_blue", {"speed": 10}, "r"), ("theke", "color", "color_change", {"speed": 15}, "g")]
for fx, attr, pat, kw, watch in cases:
    r, s, e = rig_engine(strobe=False)
    c_ = Clock(s)
    tr = [track(fx, attr, clips=[clip(0, 60, pat, **kw)])]
    if attr == "dimmer" and fx == "par":
        tr.append(track(fx, "color", keys=[key(0, [255, 255, 255, 0, 0])]))
    e.load(show_doc(tracks=tr))
    e.play(c_.t, 0.0, True, "c1")
    n = flashes(r, s, e, c_, fx, watch)
    check(n <= 2, f"ohne Erlaubnis {fx}/{pat} {kw['speed']} Hz: hoechstens 2 Blitze/s (gemessen {n})")
# Keyframes im schnellen Wechsel
r, s, e = rig_engine(strobe=False)
c_ = Clock(s)
e.load(show_doc(tracks=[track("vega", "dimmer", keys=[key(i * 0.05, 255 * (i % 2), "constant") for i in range(400)])]))
e.play(c_.t, 0.0, True, "c1")
n = flashes(r, s, e, c_, "vega", "dimmer")
check(n <= 2, f"schnelle Keyframes ohne Erlaubnis: hoechstens 2 Blitze/s (gemessen {n})")
# Shutter und Strobe-Kanaele
r, s, e = rig_engine(strobe=False)
c_ = Clock(s)
e.load(show_doc(tracks=[track("vega", "dimmer", keys=[key(0, 255)]), track("vega", "shutter", keys=[key(0, 100)]),
                        track("docooler_1", "strobe", keys=[key(0, 200)]), track("eyes", "flash", keys=[key(0, 200)]),
                        track("effektband", "preset", keys=[key(0, 32, "constant")])]))
e.play(c_.t, 0.0, True, "c1")
c_.run(0.5)
check(ch(r, "vega", "shutter") == 255, "Shutter ohne Erlaubnis: offen statt Strobe")
check(ch(r, "docooler_1", "strobe") == 0, "Strobe-Kanal ohne Erlaubnis: aus")
check(ch(r, "eyes", "flash") <= 4, "Eyes-Blitz ohne Erlaubnis: aus")
check(ch(r, "effektband", "preset") == 0, "blitzendes Effektband-Preset ohne Erlaubnis: aus")
check(s.strobe is False and s.snapshot()["strobe"] is False, "Show schaltet die Erlaubnis nie selbst ein")
# Mit Erlaubnis
r, s, e = rig_engine(strobe=True)
c_ = Clock(s)
e.load(show_doc(tracks=[track("par", "dimmer", clips=[clip(0, 60, "strobe", speed=10)]), track("par", "color", keys=[key(0, [255, 255, 255, 0, 0])]),
                        track("docooler_1", "strobe", keys=[key(0, 200)])]))
e.play(c_.t, 0.0, True, "c1")
n = flashes(r, s, e, c_, "par", "r", 2.0)
check(n >= 9, f"mit Erlaubnis: 10 Hz (gemessen {n})")
check(ch(r, "docooler_1", "strobe") == 200, "mit Erlaubnis: Strobe-Kanal wirkt")
# Blitz-Grenze unberuehrt von langsamen Fades
lim = FlashLimiter()
out = [lim.filter("x", int(255 * i / 400), i * DT) for i in range(401)]
check(out[-1] == 255 and out == sorted(out), "langsamer Fade laeuft ungestoert durch die Blitz-Grenze")

# Synchronisation ueber die Engine
r, s, e = rig_engine()
c_ = Clock(s)
e.load(show_doc(tracks=[track("par", "dimmer", keys=[key(0, 0), key(60, 255)])]))
e.play(c_.t, 0.0, True, "browser1")
check(not e.report("fremd", 30.0, True, 0.0, c_.t + 0.1) and abs(e.position(c_.t + 0.1) - 0.1) < 0.01, "nur der Besitzer der Zeitbasis zaehlt")
base = c_.t
for i in range(40):
    c_.t += 0.25
    e.report("browser1", 10.0 + i * 0.25, True, 0.02, c_.t)
    s.update(c_.t)
check(abs(e.position(c_.t) - (10.0 + 39 * 0.25 + 0.02)) < 0.02, "folgt der Audio-Position inklusive Netzlaufzeit")
check(e.status(c_.t)["src"] == "browser", "Quelle Browser")
p0 = e.position(c_.t)
c_.run(5.0)
check(abs(e.position(c_.t) - (p0 + 5.0)) < 0.05 and e.status(c_.t)["src"] == "frei" and e.active(), "Browser weg: Show laeuft weiter")
check(e.report("browser1", 25.0, False, 0.0, c_.t) and not e.clock.playing, "Browser meldet Pause")
e.report("browser1", 25.0, True, 0.0, c_.t)
check(e.clock.playing, "Browser spielt wieder: Show auch")
e.seek(59.9, c_.t)
c_.run(0.3)
check(not e.loaded and e.ended and not e.active(), "Ende der Show: zurueck zu AUTO")
# Versatz
s.cfg.set("sm_light_ms", 500.0)
e.load(show_doc(tracks=[track("vega", "dimmer", keys=[key(0, 0), key(10, 255)])]))
e.play(c_.t, 5.0, True, "b")
c_.run(DT)
check(abs(ch(r, "vega", "dimmer") - 255 * 0.5525) < 2, "Licht-Versatz wird eingerechnet")
s.cfg.set("sm_light_ms", 0.0)
e.stop(c_.t)
# Nur im Browser (Licht aus): das Licht bleibt bei AUTO
r1, s1 = build(seed=8)
r2, s2, e2 = rig_engine(strobe=True)
s2._rng.seed(8)
c1, c2 = Clock(s1), Clock(s2)
e2.load(show_doc(tracks=[track("par", "dimmer", keys=[key(0, 255)])]))
e2.play(c2.t, 0.0, False, "b")
same = True
for i in range(200):
    c1.run(DT)
    c2.run(DT)
    same = same and r1.render_all() == r2.render_all()
check(same and e2.loaded and not e2.active(), "Wiedergabe ohne Licht: AUTO bleibt Bild fuer Bild gleich")
check(e2.values_for("par", 1.0) == {"dimmer": 255}, "Anzeige der Werte auch ohne Licht")
t0 = time.perf_counter()
r, s, e = rig_engine()
many = []
for fx in r.fixtures:
    for a in fm.attrs_for(fx)[:3]:
        k = tl.kind_of(a["attr"])
        many.append(track(fx.name, a["attr"], clips=[clip(0, 60, {"scalar": "sine", "color": "rainbow", "move": "circle", "laser": "laser", "fog": "fog_burst"}[k])]))
e.load(show_doc(tracks=many))
e.play(100.0, 0.0, True, "b")
t0 = time.perf_counter()
for i in range(400):
    with r.lock:
        e.render(100.0 + i * DT, 1.0, False)
per = (time.perf_counter() - t0) / 400
check(per < 0.008, f"{len(many)} Spuren: {per * 1000:.1f} ms je Bild (Takt 25 ms)")

# ---- Dateiverwaltung ----------------------------------------------------------------------------------
print("Dateiverwaltung")
tmp = tempfile.mkdtemp(prefix="s2l_sm_")
st = ShowStore(tmp)
for b in ("../boese", "a/b", "", ".x", "_intern", "x" * 61, "a\nb"):
    try:
        check_name(b)
        check(False, f"Name {b!r} abgelehnt")
    except ValueError:
        check(True, f"Name {b!r} abgelehnt")
doc = st.create("Konzert_01")
check(os.path.isfile(os.path.join(tmp, "Konzert_01", "show.json")), "Ordner je Show mit show.json")
check([x["name"] for x in st.list()] == ["Konzert_01"], "Liste")
doc["bpm"] = 140
doc["tracks"].append(track("par", "dimmer", keys=[key(1, 2)]))
st.save("Konzert_01", doc, fixtures=[{"a": 1}], patterns=[])
check(st.load("Konzert_01")["bpm"] == 140 and st.load("Konzert_01")["tracks"][0]["keys"][0]["t"] == 1, "Speichern und Laden")
check(os.path.isfile(os.path.join(tmp, "Konzert_01", "fixtures.json")) and os.path.isfile(os.path.join(tmp, "Konzert_01", "patterns.json")), "fixtures.json und patterns.json")
check(os.path.isfile(os.path.join(tmp, "Konzert_01", "show.json.alt")), "vorige Fassung bleibt liegen")
st.save_audio("Konzert_01", io.BytesIO(b"ID3" + b"\0" * 1000), 1003)
check(st.list()[0]["has_audio"], "MP3 gespeichert")
try:
    st.save_audio("Konzert_01", io.BytesIO(b"<html>" + b"\0" * 100), 106)
    check(False, "keine MP3 abgelehnt")
except ValueError:
    check(True, "keine MP3 abgelehnt")
check(not os.path.exists(os.path.join(tmp, "Konzert_01", "audio.mp3.neu")), "keine halbe Datei bleibt liegen")
check(os.path.getsize(os.path.join(tmp, "Konzert_01", "audio.mp3")) == 1003, "alte MP3 bleibt bei Fehler erhalten")
st.copy("Konzert_01", "Kopie")
check(st.load("Kopie")["name"] == "Kopie" and st.load("Kopie")["bpm"] == 140 and os.path.isfile(os.path.join(tmp, "Kopie", "audio.mp3")), "Kopieren mit Musik")
st.rename("Kopie", "Neu")
check(st.exists("Neu") and not st.exists("Kopie"), "Umbenennen")
st.delete("Neu")
check(not st.exists("Neu") and os.listdir(os.path.join(tmp, "_papierkorb")), "Loeschen: in den Papierkorb")
check([x["name"] for x in st.list()] == ["Konzert_01"], "Papierkorb nicht in der Liste")
st.autosave("Konzert_01", dict(doc, bpm=99))
os.utime(os.path.join(tmp, "Konzert_01", "autosave.json"), (time.time() + 10, time.time() + 10))
check(st.load_autosave("Konzert_01")["doc"]["bpm"] == 99, "automatischer Stand")
st.library_save([{"name": "Mein Puls", "pattern": "pulse", "p": {}}])
check(st.library()["patterns"][0]["name"] == "Mein Puls", "eigene Muster bleiben erhalten")
check(parse_range("bytes=0-9", 100) == (0, 9) and parse_range("bytes=90-", 100) == (90, 99) and parse_range("bytes=-10", 100) == (90, 99) and parse_range("bytes=200-", 100) is None and parse_range("x", 100) is None, "Range-Anfragen")

import backup
_base = backup.BASE
bk = tempfile.mkdtemp(prefix="s2l_bk_")
os.makedirs(os.path.join(bk, "shows", "A"))
os.makedirs(os.path.join(bk, "shows", "_papierkorb", "B"))
for p_ in ("shows/A/show.json", "shows/A/audio.mp3", "shows/_papierkorb/B/show.json", "shows/_bibliothek.json"):
    open(os.path.join(bk, p_), "w").close()
backup.BASE = bk
names_ = [n for _, n in backup.collect({})]
backup.BASE = _base
shutil.rmtree(bk, ignore_errors=True)
check("lichtshow/shows/A/show.json" in names_ and "lichtshow/shows/_bibliothek.json" in names_, "Sicherung enthaelt Shows und eigene Muster")
check(not any(n.endswith(".mp3") or "_papierkorb" in n for n in names_), "Sicherung ohne MP3 und ohne Papierkorb")
# ---- Profile ------------------------------------------------------------------------------------------
prof = fm.export_profile(rig, "par_rgbw_8ch")
check(prof["format"] == "lightbutler-profile-1" and prof["channels"][0]["param"] == "dimmer", "Profil exportieren")
try:
    fm.import_profile(rig, {"format": "falsch"})
    check(False, "falsches Profil abgelehnt")
except ValueError:
    check(True, "falsches Profil abgelehnt")

# ---- HTTP und WebSocket (echter Server) ---------------------------------------------------------------
print("Server")
os.environ["S2L_SHOWS_DIR"] = tmp
r, s = build(strobe=False)
webpanel._watch_hosts = lambda *a, **k: None
webpanel._watch_net = lambda *a, **k: None
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
import health
health.watch = lambda *a, **k: None
webpanel.start(s, port)
time.sleep(0.2)
check(isinstance(s.showman, PlaybackEngine), "Panel richtet den Showmanager ein")


def req(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body, headers or {})
    res = c.getresponse()
    return res.status, res.read(), res


def cmd(**d):
    code, b, _ = req("POST", "/api/sm/cmd", json.dumps(d))
    return code, json.loads(b)


code, body, _ = req("GET", "/shows")
check(code == 200 and b"Showmanager" in body, "Seite /shows")
code, body, _ = req("GET", "/shows/edit?show=Konzert_01")
check(code == 200 and b"editor.js" in body, "Seite /shows/edit")
code, body, _ = req("GET", "/static/sm/core.js")
check(code == 200, "Dateien der Oberflaeche")
check(req("GET", "/static/sm/../show.py")[0] == 404 and req("GET", "/static/sm/nanoleaf.json")[0] == 404, "nur freigegebene Dateien")
check(req("GET", "/")[0] == 200, "restliches Panel unveraendert erreichbar")
code, m = 0, json.loads(req("GET", "/api/sm/meta")[1])
check(any(f["name"] == "vega" for f in m["fixtures"]) and len(m["patterns"]) >= 22 and m["strobe"] is False, "Daten fuer den Editor")
check([a["attr"] for a in next(f for f in m["fixtures"] if f["name"] == "hazer")["attrs"]] == ["fog"], "Hazer im Editor: nur die Nebel-Spur")
code, d = cmd(op="create", name="Demo")
check(code == 200 and d["doc"]["name"] == "Demo", "Show anlegen")
code, d = cmd(op="create", name="../x")
check(code == 400 and "error" in d, "falscher Name: Fehlermeldung")
mp3 = b"ID3" + bytes(range(256)) * 400
code, b, _ = req("POST", "/api/sm/audio?name=Demo", mp3, {"Content-Length": str(len(mp3))})
check(code == 200, "MP3 hochladen")
code, b, res = req("GET", "/api/sm/audio?name=Demo", headers={"Range": "bytes=100-199"})
check(code == 206 and b == mp3[100:200] and res.getheader("Content-Range") == f"bytes 100-199/{len(mp3)}", "Audio: Range-Anfrage")
code, b, res = req("GET", "/api/sm/audio?name=Demo")
check(code == 200 and b == mp3 and res.getheader("Accept-Ranges") == "bytes", "Audio: ganze Datei")
check(req("GET", "/api/sm/audio?name=../../x")[0] in (400, 404), "Pfad ausserhalb abgelehnt")
doc = json.loads(req("GET", "/api/sm/show?name=Demo")[1])["doc"]
doc["tracks"] = [track("par", "dimmer", keys=[key(0, 255)])]
code, d = cmd(op="save", name="Demo", doc=doc)
check(code == 200 and d["doc"]["tracks"][0]["keys"][0]["v"] == 255, "Speichern ueber das Panel")
code, st_ = cmd(op="play", name="Demo", pos=1.0, light=True, client="tab1")
check(code == 200 and st_["playing"] and st_["on"], "Play: Show laeuft mit Licht")
# WebSocket von Hand, damit der Test ohne Browser auskommt
sock = socket.create_connection(("127.0.0.1", port), timeout=3)
key_ = base64.b64encode(os.urandom(16)).decode()
sock.sendall((f"GET /api/sm/ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key_}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
head = b""
while b"\r\n\r\n" not in head:
    head += sock.recv(1)
check(b" 101 " in head.split(b"\r\n")[0] and ws.accept_key(key_).encode() in head, "WebSocket: Handschlag")


def ws_send(text):
    data = text.encode()
    mask = os.urandom(4)
    sock.sendall(bytes([0x81, 0x80 | len(data)] if len(data) < 126 else [0x81, 0x80 | 126]) + (struct.pack(">H", len(data)) if len(data) >= 126 else b"") + mask + ws.unmask(data, mask))


def ws_recv():
    b1, b2 = sock.recv(1)[0], sock.recv(1)[0]
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", sock.recv(2))[0]
    data = b""
    while len(data) < n:
        data += sock.recv(n - len(data))
    return json.loads(data)


ws_send(json.dumps({"t": "watch", "fixture": "par"}))
ws_send(json.dumps({"t": "sync", "client": "tab1", "pos": 42.0, "playing": True, "rtt": 10, "ol": 0, "ts": 7}))
got = [ws_recv() for _ in range(4)]
check(any(g.get("t") == "pong" and g.get("ts") == 7 for g in got), "WebSocket: Antwort auf die Meldung")
stm = [g for g in got if g.get("t") == "st"]
check(stm and stm[-1]["name"] == "Demo" and "vals" in stm[-1], "WebSocket: Stand mit Werten des beobachteten Geraets")
ws_send(json.dumps({"t": "sync", "client": "tab1", "pos": 42.2, "playing": True, "rtt": 10, "ol": 0, "ts": 8}))
time.sleep(0.05)
check(abs(s.showman.position(time.time()) - 42.2) < 0.5, "WebSocket: Show folgt der gemeldeten Position")
sock.close()
code, st_ = cmd(op="light_ms", ms=-280)
check(code == 200 and st_["light_ms"] == -280 and s.cfg["sm_light_ms"] == -280, "Licht-Versatz aus dem Editor")
code, st_ = cmd(op="light_ms", ms=99999)
check(st_["light_ms"] == 1000, "Licht-Versatz begrenzt")
cmd(op="light_ms", ms=0)
code, st_ = cmd(op="pause", pos=50.0)
check(not st_["playing"] and st_["pos"] == 50.0, "Pause")
code, st_ = cmd(op="stop")
check(not st_["loaded"], "Stop")
code, d = cmd(op="analyze", env=[1.0 if i % 50 == 0 else 0.0 for i in range(3000)], rate=100)
check(abs(d["tempo"]["bpm"] - 120.0) < 1 or abs(d["tempo"]["bpm"] - 60) < 1, "Tempo-Analyse ueber das Panel")
code, d = cmd(op="peaks", name="Demo", data={"rate": 50, "min": [0, 1], "max": [1, 2]})
check(json.loads(req("GET", "/api/sm/peaks?name=Demo")[1])["rate"] == 50, "Wellenform gespeichert")
check("nanoleaf" not in " ".join(os.listdir(tmp)), "keine fremden Dateien im Showordner")
shutil.rmtree(tmp, ignore_errors=True)

finish("test_showmanager")
