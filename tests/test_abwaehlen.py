"""Licht-Mix und Bewegung: ein gewaehlter Knopf wird durch nochmaliges Antippen wieder abgewaehlt."""
from _common import build, Clock, check, finish

rig, sh = build(seed=4)
clk = Clock(sh)
clk.run(5)

# Bewegung in AUTO (gab es schon): nochmal tippen = nach der Musik
sh.command({"move": "circle"})
check(sh.snapshot()["move"] == "circle", "AUTO: Bewegung Kreis gewaehlt")
sh.command({"move": "circle"})
snap = sh.snapshot()
check(snap["mode"] == "auto" and snap["move"] == "", "AUTO: Kreis nochmal = abgewaehlt")

# Licht-Mix: nochmal tippen = zurueck zu AUTO
sh.command({"color_toggle": "blau"})
sh.command({"mix": "Scanner"})
snap = sh.snapshot()
check(snap["mode"] == "scene" and snap["mixbtn"] == "Scanner", "Mix Scanner gewaehlt (eigene Szene)")
sh.command({"mix": "Discokugel"})
check(sh.snapshot()["mixbtn"] == "Discokugel", "anderer Mix wechselt direkt")
sh.command({"mix": "Discokugel"})
snap = sh.snapshot()
check(snap["mode"] == "auto" and snap["mixbtn"] == "", "Discokugel nochmal = abgewaehlt, zurueck zu AUTO")
check(snap["colors"] == ["blau"], "Farbauswahl in AUTO bleibt erhalten")
clk.run(2)

# Bewegung in der eigenen Szene: nochmal tippen = Bewegung nach der Musik, Mix bleibt
sh.command({"mix": "Scanner"})
sh.command({"move": "sweep"})
check(sh.snapshot()["move"] == "sweep", "Szene: Bewegung Besen gewaehlt")
sh.command({"move": "sweep"})
snap = sh.snapshot()
check(snap["move"] == "auto" and snap["mixbtn"] == "Scanner" and snap["mode"] == "scene",
      "Szene: Besen nochmal = abgewaehlt, Mix Scanner bleibt")
sh.command({"move": "home"})
check(sh.snapshot()["move"] == "home", "Szene: danach andere Bewegung waehlbar")
clk.run(2)

# feste Szene: Mix-Knopf ohne Auswahl wird nicht versehentlich abgewaehlt
sh.command({"scene": "bunt"})
sh.command({"mix": ""})
check(sh.snapshot()["mode"] == "scene", "leerer Mix-Wert verlaesst die Szene nicht")

finish("test_abwaehlen")
