"""KTV-Laser im Ruhezustand. Im 34-Kanal-Modus (Standard seit 03.11.2026) sind gesperrt alle Kanaele 0, das Rad bleibt laut Nutzer ruhig.
Im 6-Kanal-Modus (falls zurueckgestellt wird) sendet die Effektgruppe (Kanal 2) den Ruhewert 255, damit der Motor nicht surrt.
Die Leistung (Kanal 1) bleibt immer 0. Nur in der Szene Laser mit Laser-Betrieb gelten die Werte der Show, beim Verlassen sofort wieder Ruhe."""
import copy

from _common import build, check, finish, Clock, ktv6_config

import dmx


def ktv(rig):
    f = rig["laser"]
    return list(rig.render_all()[rig.target][f.address - 1:f.address - 1 + f.n])


# ---- 34-Kanal-Modus, wie er laeuft ----------------------------------------------------------------
rig, sh = build(seed=3)
check(rig["laser"].type == "laser_ktv34" and rig["laser"].address == 301 and rig["laser"].n == 34, "KTV: 34 Kanaele ab 301")
check(rig["laser"].rest == {}, "34 Kanaele: kein Ruhewert")
check(ktv(rig) == [0] * 34 and rig.check() == [], "Start: alles 0, Dateipruefung ohne Probleme")
c = Clock(sh)
bad = []
c.run(30, each=lambda t: bad.append(t) if ktv(rig) != [0] * 34 else None)
check(not bad, "AUTO: KTV gesperrt, alle 34 Kanaele 0")
sh.cfg.set("laser_mode", 0)
sh.command({"scene": "Laser"})
seen = []
c.run(10, each=lambda t: seen.append(ktv(rig)))
check(any(f[0] > 0 for f in seen), "Szene Laser: Laser darf an")
check(all(f[14] < 245 for f in seen), "Szene Laser, Pi steuert: Kanal 15 nie im Selbstlauf- oder Sound-Bereich")
check(all(f[17:] == [0] * 17 for f in seen), "Muster B und die Zusatzkanaele bleiben 0")
sh.cfg.set("laser_mode", 1)
c.run(0.5)
check(ktv(rig)[14] >= 251, "Szene Laser, Sound-to-Light: Kanal 15 im Ton-Bereich")
sh.command({"auto": True})
c.run(0.025)
check(ktv(rig) == [0] * 34, "Szene verlassen: sofort alles 0")

# ---- 6-Kanal-Modus: alles bleibt moeglich, falls zurueckgestellt wird ------------------------------
CFG = ktv6_config()
REST = [0, 255, 0, 0, 0, 0]
rig, sh = build(seed=3, config=CFG)
check(rig["laser"].address == 181, "6 Kanaele: Adresse 181")
check(rig["laser"].rest == {"group": 255}, "Ruhewert nur fuer die Effektgruppe")
check(ktv(rig) == REST, "Start: Leistung 0, Effektgruppe 255, Rest 0")
check(rig.check() == [], "Dateipruefung ohne Probleme")

# ---- AUTO, Drop, Stille, Blackout, Freeze: immer Ruhe --------------------------------------------
bad = []
c = Clock(sh)
c.run(150, each=lambda t: bad.append(t) if ktv(rig) != REST else None)
check(not bad, "AUTO 150 s mit Aufbau und Drops: KTV immer im Ruhezustand")
for cmd in ({"freeze": True}, {"mix": "STOP"}):
    sh.command(cmd)
    c.run(1)
    check(ktv(rig) == REST, f"{cmd}: KTV im Ruhezustand")
sh.rig.blackout()
check(ktv(rig) == REST, "Blackout: KTV im Ruhezustand")

# ---- Szene Laser: Show-Werte, danach sofort Ruhe -------------------------------------------------
rig, sh = build(seed=3, config=CFG)
c = Clock(sh)
sh.cfg.set("laser_mode", 0)
c.run(5)
sh.command({"scene": "Laser"})
on = []
c.run(10, each=lambda t: on.append(ktv(rig)[0] > 0))
check(any(on), "Szene Laser: Laser darf an (Vorbedingung)")
sh.command({"auto": True})
c.run(0.025)
check(ktv(rig) == REST, "Szene verlassen: im naechsten Bild Leistung 0 und Ruhewert")

# ---- andere Laser und der Hazer bleiben bei 0 ----------------------------------------------------
for name in ("eyes", "derby"):
    fx = next((f for f in rig.fixtures if f.name.startswith(name)), None)
    if fx is not None:
        check(fx.rest == {}, f"{name}: keine Ruhewerte (Laser-Kanaele 0)")
hz = next(f for f in rig.fixtures if f.locked)
check(hz.rest == {} and all(v == 0 for v in rig.render_all()[rig.target][hz.address - 1:hz.address - 1 + hz.n]),
      "Hazer: weiter alles 0")

# ---- Schutz: nie ein Ruhewert fuer die Leistung --------------------------------------------------
td = copy.deepcopy(rig["laser"].tdef)
td["rest_values"] = {"power": 255, "group": 255}
f = dmx.Fixture("x", "laser_ktv", td, 1, "locked")
check(f.rest == {"group": 255}, "Ruhewert fuer 'power' wird ignoriert")
buf = bytearray(512)
f.write(buf)
check(buf[0] == 0, "Leistung bleibt 0")
td2 = copy.deepcopy(rig["laser"].tdef)
td2["locked_channels"] = [p for p in td2["locked_channels"] if p != "power"]
check(dmx.Fixture("y", "laser_ktv", td2, 1, "locked").rest == {}, "ohne gesperrte Leistung keine Ruhewerte")
rig.fixtures[[i for i, x in enumerate(rig.fixtures) if x.name == "laser"][0]].tdef["rest_values"] = {"power": 255}
check(any("rest_values" in p for p in rig.check()), "Dateipruefung meldet einen Ruhewert fuer 'power'")
finish("test_laser_ruhe")
