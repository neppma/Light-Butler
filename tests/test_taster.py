"""Taster: Strobe, Smoke, Blackout, Blinder und Freeze (Panel und APC mini) wirken nur, solange gedrueckt. Kommt
1,5 s kein Lebenszeichen, laesst die Show den Taster selbst los. Smoke: hoechstens 10 s am Stueck, danach 20 s Pause
ab dem Ende des Nebels."""
import time

from _common import build, Clock, check, finish

from midi_ctl import MidiController, pad_note

rig, sh = build(seed=11)
clk = Clock(sh)
clk.run(5)
snap = sh.snapshot

# jeder Taster: an solange gedrueckt, aus beim Loslassen
for name, is_on in (("blitz", lambda s: s["blitz"]), ("blackout", lambda s: s["mode"] == "blackout"),
                    ("allbright", lambda s: s["mode"] == "allbright"), ("freeze", lambda s: s["freeze"])):
    sh.command({"hold": {"name": name, "on": True}})
    clk.run(0.5)
    on = is_on(snap())
    sh.command({"hold": {"name": name, "on": False}})
    clk.run(0.1)
    check(on and not is_on(snap()) and snap()["mode"] != "scene", f"{name}: an solange gedrueckt, aus beim Loslassen")

# Sicherung: ohne Lebenszeichen wird losgelassen
sh.command({"hold": {"name": "blitz", "on": True}})
sh._hold_check(time.time() + 1.0)
check(snap()["blitz"], "Strobe: 1 s nach dem letzten Lebenszeichen noch an")
sh.command({"hold_keep": ["blitz"]})
sh._hold_check(time.time() + 1.4)
check(snap()["blitz"], "Strobe: Lebenszeichen verlaengert")
sh._hold_check(time.time() + 1.6)
check(not snap()["blitz"] and snap()["held"] == [], "Strobe: 1,6 s ohne Lebenszeichen = losgelassen")
sh.command({"hold": {"name": "allbright", "on": True}})
sh.held["allbright"] -= 2.0
clk.run(0.1)
check(snap()["mode"] != "allbright", "Blinder: Show laesst ohne Lebenszeichen im laufenden Betrieb los")
try:
    sh.command({"hold": {"name": "laser", "on": True}})
    check(False, "unbekannter Taster abgelehnt")
except ValueError:
    check(True, "unbekannter Taster abgelehnt (z. B. kein Laser als Taster)")

# Smoke: nur solange gedrueckt, hoechstens 10 s, dann Pause ab dem Ende
hz = next(f for f in rig.fixtures if f.type == "hazer")
sh.command({"hold": {"name": "fog", "on": True}})
check(snap()["fog_on"] and hz.manual_vals is not None, "Smoke gedrueckt: Nebel laeuft")
check(abs(sh.fog_end - time.time() - 10.0) < 0.5 and hz.manual_until - time.time() <= 10.01, "Nebel hoechstens 10 s am Stueck")
sh.command({"hold": {"name": "fog", "on": False}})
check(not snap()["fog_on"] and hz.manual_vals is None, "Smoke losgelassen: Nebel sofort aus")
check(19 <= snap()["fog_wait"] <= 20, f"danach 20 s Pause ab dem Ende ({snap()['fog_wait']} s)")
sh.command({"hold": {"name": "fog", "on": True}})
check(not snap()["fog_on"] and "warten" in sh.note, "waehrend der Pause kein Nebel")
sh.command({"hold": {"name": "fog", "on": False}})
sh.fog_end = time.time() - 25
sh.command({"fog": True})
check(snap()["fog_on"] and 2.5 < sh.fog_end - time.time() <= 3.01, "fester Nebelschub (3 s) geht weiterhin")
sh.command({"hold": {"name": "fog", "on": False}})

# APC mini: dieselben Taster mit Lebenszeichen
m = MidiController(sh, map_path=None)
m._raw = lambda *a: None
sh.fog_end = time.time() - 25
from midi_ctl import TOP_ROW
check(TOP_ROW == ["auto", "blitz", "wow", "allbright", "freeze", "blackout", "fog", "beat"],
      "APC Reihe 1 wie im Panel: AUTO, STROBE, WOW!, BLINDER, FREEZE, BLACKOUT, SMOKE, BPM")
for col, name, is_on in ((TOP_ROW.index("blitz"), "blitz", lambda s: s["blitz"]), (TOP_ROW.index("blackout"), "blackout", lambda s: s["mode"] == "blackout"),
                         (TOP_ROW.index("allbright"), "allbright", lambda s: s["mode"] == "allbright"), (TOP_ROW.index("freeze"), "freeze", lambda s: s["freeze"]),
                         (TOP_ROW.index("fog"), "fog", lambda s: s["fog_on"])):
    m.press(pad_note(0, col), True)
    on = is_on(snap()) and name in snap()["held"]
    m.press(pad_note(0, col), False)
    check(on and not is_on(snap()), f"APC {name}: an solange gedrueckt, aus beim Loslassen")
m.press(pad_note(0, TOP_ROW.index("auto")), True)
check(snap()["mode"] == "auto", "APC AUTO: normaler Knopf")

finish("test_taster")
