"""Farbauswahl im Panel: Bunt und Regenbogen sind weg, Farbtoene lassen sich in AUTO an- und abwaehlen,
und ab zwei Farben wechselt die Show nur zwischen den gewaehlten Farben."""
from _common import build, Clock, check, finish

import webpanel
from scenes import COLORS as HUES

names = [k for k, *_ in webpanel.COLORS]
check("multi" not in names and "rainbow" not in names, "Panel hat keine Knoepfe Bunt und Regenbogen mehr")
check(names == ["auto", "rot", "orange", "gelb", "gruen", "cyan", "blau", "violett", "magenta", "white", "uv"],
      "uebrige Farbknoepfe unveraendert")
page = webpanel.make_page()
check("{color_toggle:v}" in page, "Farbknoepfe schicken color_toggle")

rig, sh = build(seed=2)
clk = Clock(sh)
clk.run(5)

# einzeln an- und abwaehlen
sh.command({"color_toggle": "rot"})
snap = sh.snapshot()
check(snap["color"] == "rot" and snap["colors"] == ["rot"], "eine Farbe: wirkt wie bisher fest (rot)")
sh.command({"color_toggle": "orange"})
sh.command({"color_toggle": "gelb"})
snap = sh.snapshot()
check(snap["colors"] == ["rot", "orange", "gelb"], f"drei Farben gewaehlt ({snap['colors']})")
check(snap["color"] == "", "bei mehreren Farben ist Auto nicht markiert")
check(abs(sh.hue_target - HUES["gelb"]) < 1e-9, "zuletzt gewaehlte Farbe wird sofort gezeigt")
sh.command({"color_toggle": "orange"})
check(sh.snapshot()["colors"] == ["rot", "gelb"], "nochmal antippen nimmt die Farbe weg")

# die Show nutzt nur die gewaehlten Farben
allowed = {HUES["rot"], HUES["gelb"]}
targets = set()
clk.run(120, each=lambda t: targets.add(round(sh.hue_target, 6)))
check(targets <= {round(h, 6) for h in allowed}, f"nur gewaehlte Farbtoene als Ziel ({sorted(targets)})")
check(len(targets) == 2, "die gewaehlten Farben wechseln sich ab")
check(min(abs(((sh.hue - h + 0.5) % 1.0) - 0.5) for h in allowed) < 0.02, "Licht steht auf einer gewaehlten Farbe")

# letzte Farbe weg = Auto
sh.command({"color_toggle": "rot"})
check(sh.snapshot()["colors"] == ["gelb"] and sh.auto_color == "gelb", "eine Farbe uebrig: fest gelb")
sh.command({"color_toggle": "gelb"})
snap = sh.snapshot()
check(snap["colors"] == [] and snap["color"] == "auto" and sh.auto_color is None, "keine Farbe: zurueck zu Auto")

# Weiss, UV und Auto bleiben Einzelauswahl
sh.command({"color_toggle": "rot"})
sh.command({"color_toggle": "blau"})
sh.command({"color_toggle": "white"})
snap = sh.snapshot()
check(snap["color"] == "white" and snap["colors"] == [], "Weiss ersetzt die Farbauswahl")
sh.command({"color_toggle": "rot"})
check(sh.snapshot()["color"] == "rot" and sh.auto_color == "rot", "Farbe nach Weiss: Weiss ist aus")
sh.command({"color_toggle": "auto"})
check(sh.snapshot()["colors"] == [] and sh.auto_color is None, "Auto loescht die Auswahl")

# Controller (MIDI) setzt weiter genau eine Farbe
sh.command({"color_toggle": "rot"})
sh.command({"color_toggle": "blau"})
sh.command({"color": "gruen"})
check(sh.snapshot()["colors"] == ["gruen"] and sh.auto_color == "gruen", "color (Controller) setzt genau eine Farbe")

# in einer Szene: Farbe der Szene wie bisher
sh.command({"scene": "bunt"})
sh.command({"color_toggle": "blau"})
snap = sh.snapshot()
check(snap["color"] == "blau" and snap["colors"] == [], "in einer Szene setzt der Knopf die Szenenfarbe")

finish("test_farbauswahl")
