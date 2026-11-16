"""APC mini mk2, Farbseite: Farben lassen sich wie im Panel dazuwaehlen (Mehrfachauswahl) und durch nochmaliges
Druecken wieder abwaehlen. Keine Farbe mehr = Auto nach Stimmung."""
from _common import build, check, finish, Clock

from midi_ctl import MidiController

rig, sh = build(seed=3)
Clock(sh).run(1)
m = MidiController(sh, map_path=None)
colors = [(n, a) for n, a in m.map.get("pads2", {}).items() if "color" in a]
check(len(colors) >= 8, "Farbseite hat Farb-Pads")


def press(color):
    note = next(int(n) for n, a in colors if a["color"] == color)
    m._act({"color": color}, True, note)


press("rot")
check(sh.auto_colors == ["rot"], "Rot gewaehlt")
press("blau")
check(sh.auto_colors == ["rot", "blau"], "Blau dazugewaehlt (Mehrfachauswahl wie im Panel)")
press("rot")
check(sh.auto_colors == ["blau"], "Rot nochmal gedrueckt: abgewaehlt")
press("blau")
check(sh.auto_colors == [] and sh.snapshot()["color"] == "auto", "letzte Farbe abgewaehlt: Auto nach Stimmung")
snap = sh.snapshot()
press("rot")
press("gruen")
snap = sh.snapshot()
check(set(snap["colors"]) == {"rot", "gruen"}, "Panel und APC zeigen beide gewaehlten Farben (LEDs voll)")
finish("test_apc_farben")
