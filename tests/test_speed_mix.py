"""Speed: Auto (nach der Musik), Low, Med, Hot; beim Start Auto, immer genau eins gewaehlt. Die Wahl gilt gemeinsam
fuer AUTO und jeden Licht-Mix (ein Mix setzt sie nicht zurueck, eine Wahl im Mix bleibt danach in AUTO)."""
from _common import zurueck, build, Clock, check, finish

from midi_ctl import MidiController

rig, sh = build(seed=12)
clk = Clock(sh)
clk.run(3)
snap = sh.snapshot

check(snap()["speed"] == "auto" and sh.auto_speed is None, "Start: Speed Auto (nach der Musik)")
sh.command({"speed": "fast"})
check(snap()["speed"] == "fast", "AUTO: Hot gewaehlt")
sh.command({"speed": "fast"})
check(snap()["speed"] == "fast", "Hot nochmal antippen: bleibt Hot (zurueck nur ueber Auto)")
sh.command({"mix": "Scanner"})
check(snap()["mixbtn"] == "Scanner" and snap()["speed"] == "fast" and sh.sc.mspeed == "fast", "Scanner: bleibt Hot")
sh.command({"mix": "Karussell"})
check(snap()["speed"] == "fast", "Carousel: bleibt Hot")
sh.command({"speed": "slow"})
check(snap()["speed"] == "slow" and sh.sc.speed == "slow", "im Mix Low gewaehlt")
sh.command({"mix": "Karussell"})
check(snap()["mode"] == "auto" and snap()["speed"] == "slow", "Mix abgewaehlt: AUTO behaelt Low")
sh.command({"mix": "Discokugel"})
sh.command({"speed": "auto"})
check(snap()["speed"] == "auto" and sh.sc.speed == "mid" and sh.auto_speed is None, "Auto im Mix: Muster laufen mit Med, Anzeige Auto")
sh.command({"mix": "Discokugel"})
check(snap()["mode"] == "auto" and snap()["speed"] == "auto", "zurueck in AUTO: Speed Auto")

# feste Szenen behalten ihre eigene Geschwindigkeit
sh.command({"scene": "Switch It Up slow"})
check(snap()["speed"] == sh.sc.speed, f"feste Szene zeigt ihre eigene Geschwindigkeit ({snap()['speed']})")
eigen = (sh.sc.speed, sh.sc.mspeed)
for wahl in ("fast", "slow", "auto"):                          # Fehler 02.11.2026: der Knopf aenderte die laufende Szene
    sh.command({"speed": wahl})
    check((sh.sc.speed, sh.sc.mspeed) == eigen and snap()["speed"] == eigen[0], f"Speed {wahl} aendert die feste Szene nicht")
    check(sh.auto_speed is None, f"Speed {wahl} in fester Szene merkt sich nichts fuer AUTO")
zurueck(sh)
check(snap()["speed"] == "auto", "zurueck in AUTO: Speed wie vorher")
sh.command({"scene": "Laser"})
check(sh.sc.special == "laser", "Szene Laser aktiv")
sh.command({"speed": "fast"})
check(sh.sc.speed == "fast", "Ausnahme: Speed wirkt weiter in der Szene Laser")
zurueck(sh)
sh.command({"speed": "auto"})

# APC mini: keine Auto-Taste, aktive Taste nochmal = Auto
m = MidiController(sh, map_path=None)
m._raw = lambda *a: None
m.press(113, True)
check(snap()["speed"] == "mid", "APC: Med")
m.press(113, True)
check(snap()["speed"] == "auto", "APC: Med nochmal = Auto")

finish("test_speed_mix")
