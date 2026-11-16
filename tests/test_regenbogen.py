"""Licht-Mix Regenbogen: Regenbogenfarben der Reihe nach, aber Helligkeit nach der Musik wie in AUTO
(nicht dauernd 100 %). Nochmal antippen schaltet ihn aus."""
from _common import zurueck, build, Clock, check, finish


def brightness(rig, sh):
    """mittlere Helligkeit der RGB-Lichter (Bars, Washes) 0..1"""
    vals = []
    for fx, zi in sh.bars + sh.wash:
        z = fx.zones()[zi]
        vals.append(max(fx.values.get(z[c], 0) for c in ("r", "g", "b") if c in z) / 255.0)
    return sum(vals) / len(vals)


def hues(sh):
    devs = list(dict.fromkeys(fx for fx, _ in sh.bars + sh.wash))       # je Geraet eine Farbe (mehrere Zonen gleich)
    return [round(sh._rainbow_hue(fx), 3) for fx in devs]


rig, sh = build(seed=5)
clk = Clock(sh)
clk.run(20)

sh.command({"color_toggle": "rot"})
sh.command({"mix": "Regenbogen"})
snap = sh.snapshot()
check(snap["mode"] == "auto", "Regenbogen bleibt im AUTO-Modus (keine feste Szene)")
check(snap["mixbtn"] == "Regenbogen", "Knopf Regenbogen ist markiert")
check(snap["colors"] == [] and snap["color"] == "", "Farbauswahl ist waehrenddessen aus")

h = hues(sh)
check(len(set(h)) == len(h), f"jedes Geraet hat eine eigene Regenbogenfarbe ({h})")
levels = []
clk.run(60, each=lambda t: levels.append(brightness(rig, sh)))
lo, hi = min(levels), max(levels)
check(hi > 0.3, f"Lichter leuchten ({hi:.2f})")
check(sum(1 for v in levels if v > 0.97) < len(levels) * 0.5, "nicht dauernd volle Helligkeit")
check(hi - lo > 0.2, f"Helligkeit folgt der Musik (zwischen {lo:.2f} und {hi:.2f})")
h = hues(sh)
clk.run(2)
check(hues(sh) != h, "Farben laufen langsam weiter")

pres = [f for f in rig.fixtures if f.type == "wled_preset"]
if pres:
    check(pres[0].values.get("preset") == 13, "Effektband zeigt Preset 13 (Regenbogen)")

# nochmal antippen = aus, zurueck zu normalem AUTO
sh.command({"mix": "Regenbogen"})
snap = sh.snapshot()
check(snap["mode"] == "auto" and snap["mixbtn"] == "" and not sh.auto_rainbow, "nochmal antippen schaltet Regenbogen aus")
check(snap["color"] == "auto", "danach wieder Farbe Auto")

# Farbe waehlen beendet den Regenbogen, anderer Mix ebenfalls, AUTO-Knopf ebenfalls
sh.command({"mix": "Regenbogen"})
sh.command({"color_toggle": "blau"})
check(not sh.auto_rainbow and sh.snapshot()["colors"] == ["blau"], "Farbknopf beendet Regenbogen")
sh.command({"mix": "Regenbogen"})
sh.command({"mix": "Scanner"})
check(not sh.auto_rainbow and sh.snapshot()["mixbtn"] == "Scanner", "anderer Mix ersetzt Regenbogen")
sh.command({"mix": "Regenbogen"})
check(sh.auto_rainbow and sh.snapshot()["mode"] == "auto", "Regenbogen aus einer Mix-Szene heraus: AUTO mit Regenbogen")
zurueck(sh)
check(not sh.auto_rainbow, "AUTO-Knopf beendet Regenbogen")

# Szenen mit Mix Regenbogen (Szenen-Editor) bleiben feste Bilder wie bisher
sh.command({"scene": "Chill Colors"})
check(sh.snapshot()["mode"] == "scene" and not sh.auto_rainbow, "Szenen bleiben unveraendert")

finish("test_regenbogen")
