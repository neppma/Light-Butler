"""Licht-Mix STOP: wie Freeze, aber nur das Licht. Farben und Helligkeit bleiben stehen, die Bewegung der Geraete
(Vega Pan/Tilt, Docooler-Neigung) laeuft weiter. Laser, Einzel-Strobe und Effektband bleiben aus."""
from _common import zurueck, build, Clock, ch, check, finish

MOVE = {"pan", "pan_fine", "tilt", "tilt_fine", "tilt1", "tilt2"}


def light(rig):
    """alle Kanaele ausser Bewegung, Laser und Effektband"""
    out = {}
    for fx in rig.fixtures:
        if fx.type == "wled_preset" or fx in rig_lasers:
            continue
        for p in fx.map:
            if p not in MOVE:
                out[(fx.name, p)] = ch(rig, fx.name, p)
    return out


def motion(rig):
    return {(fx.name, p): ch(rig, fx.name, p) for fx in rig.fixtures for p in fx.map if p in MOVE}


rig, sh = build(seed=6)
rig_lasers = set(sh.lasers)
clk = Clock(sh)
clk.run(30)

sh.command({"mix": "STOP"})
snap = sh.snapshot()
check(snap["mode"] == "auto" and snap["mixbtn"] == "STOP" and snap["color_freeze"], "STOP: Farb-Freeze an, Show bleibt in AUTO")
clk.run(0.1)
l0, m0 = light(rig), motion(rig)
changed_light, moved, laser_on, solo = 0, set(), False, False


def each(t):
    global changed_light, laser_on, solo
    if light(rig) != l0:
        changed_light += 1
    m = motion(rig)
    moved.update(k for k in m if m[k] != m0[k])
    if any(ch(rig, fx.name, p) != fx.rest.get(p, 0) for fx in rig_lasers for p in fx.tdef.get("locked_channels", ()) if p in fx.map):
        laser_on = True
    solo = solo or sh.solo is not None


clk.run(40, each=each)
check(changed_light == 0, "Farben und Helligkeit bleiben 40 s lang genau stehen")
check(any(k[1] in ("pan", "tilt") for k in moved), "Vega bewegt sich weiter")
check(any(k[1] in ("tilt1", "tilt2") for k in moved), "Docooler-Neigung bewegt sich weiter")
check(not laser_on, "gesperrte Laser-Kanaele bleiben 0 (Laser aus)")
check(not solo, "kein Einzel-Strobe waehrend STOP")
check(all(fx.values.get("dimmer", 0) == 0 for fx in sh.presets), "Effektband dunkel (wie Freeze)")

# Bewegung per Knopf laeuft auch waehrend STOP
sh.command({"move": "circle"})
check(sh.snapshot()["mixbtn"] == "STOP" and sh.auto_move == "circle", "Bewegung waehlen beendet STOP nicht")
clk.run(2)
check(sh.mo is not None, "gewaehlte Bewegung (Kreis) laeuft")
sh.command({"move": "circle"})

# nochmal antippen = aus, Licht laeuft wieder
sh.command({"mix": "STOP"})
check(not sh.color_freeze and sh.snapshot()["mixbtn"] == "", "nochmal antippen beendet STOP")
l1 = light(rig)
clk.run(5)
check(light(rig) != l1, "Licht laeuft danach wieder nach der Musik")

# anderer Mix, Farbe, AUTO, Szene beenden STOP
for cmd, text in (({"mix": "Scanner"}, "anderer Mix"), ({"color_toggle": "rot"}, "Farbknopf"),
                  ({"auto": True}, "AUTO-Knopf"), ({"scene": "bunt"}, "Szene")):
    sh.command({"mix": "STOP"})
    sh.command(cmd)
    check(not sh.color_freeze, f"{text} beendet STOP")
zurueck(sh)

# STOP in einer Szene: Szene bleibt, ihre Bewegung laeuft weiter
sh.command({"mix": "Scanner"})
sh.command({"move": "sweep"})
clk.run(2)
sh.command({"mix": "STOP"})
snap = sh.snapshot()
check(snap["mode"] == "scene" and snap["mixbtn"] == "STOP", "STOP in einer Mix-Szene: Szene bleibt erhalten")
clk.run(0.1)
l0, m0 = light(rig), motion(rig)
changed_light, moved = 0, set()
clk.run(10, each=each)
check(changed_light == 0, "Szene: Licht bleibt stehen")
check(any(k[1] in ("pan", "tilt") for k in moved), "Szene: Bewegung Besen laeuft weiter")
sh.command({"mix": "STOP"})
check(sh.snapshot()["mixbtn"] == "Scanner", "STOP aus: Scanner ist wieder markiert")

# Sicherheit: STOP in der Laser-Szene schaltet die Laser sofort aus
sh.command({"mix": "STOP"})
sh.command({"scene": "Laser"})
clk.run(3)
locked = lambda: sum(abs(ch(rig, fx.name, p) - fx.rest.get(p, 0)) for fx in rig_lasers for p in fx.tdef.get("locked_channels", ()) if p in fx.map)   # Abweichung vom Ruhezustand
check(locked() > 0, "Laser-Szene: Laser an (Vorbedingung)")
sh.command({"mix": "STOP"})
clk.run(0.025)
check(locked() == 0 and not sh.laser_on, "STOP in der Laser-Szene: Laser im naechsten Bild aus")
clk.run(5)
check(locked() == 0, "Laser bleiben waehrend STOP aus")

finish("test_stop_farbfreeze")
