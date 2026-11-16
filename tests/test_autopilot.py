"""Autopilot: nur ein Knopf AUTO. An = Bedienung unter den Schnelleffekten gesperrt, die Knoepfe zeigen, was laeuft;
nochmal = manuell, das Markierte bleibt gewaehlt. Schnelleffekte, Dimmer und Sicherheit bleiben immer bedienbar."""
from _common import Clock, build, check, finish

import webpanel

rig, sh = build()
sh.pilot = True
clk = Clock(sh)
clk.run(5)

# Gesperrt: gilt fuer Panel und APC, beide rufen command()
for d in ({"color_toggle": "rot"}, {"speed": "fast"}, {"move": "fan"}, {"mix": "Scanner"}, {"style": "club"},
          {"aim": "bank"}, {"beam": {"gobo": 2}}, {"eb_preset": 1}, {"scene": sh.scene_defs[3].name}):
    sh.command(d)
    check(sh.auto_colors == [] and sh.auto_speed is None and sh.auto_move is None and sh.sc is None and sh.style_man is None
          and sh.aim is None and not sh.beam_man and sh.eb_man is None, f"gesperrt: {d}")
check("AUTO" in sh.note, "Hinweis bei gesperrter Taste")
laser = next(s.name for s in sh.scene_defs if s.special == "laser")
sh.command({"scene": laser})
check(sh.sc is None, "Laser-Szene im Autopilot gesperrt")

# Frei: Schnelleffekte, Dimmer, Gruppen
sh.command({"hold": {"name": "blackout", "on": True}})
check(sh.override == "blackout", "BLACKOUT bleibt bedienbar")
sh.command({"hold": {"name": "blackout", "on": False}})
sh.command({"hold": {"name": "freeze", "on": True}})
check(sh.freeze, "FREEZE bleibt bedienbar")
sh.command({"hold": {"name": "freeze", "on": False}})
sh.command({"hold": {"name": "allbright", "on": True}})
check(sh.override == "allbright", "BLINDER bleibt bedienbar")
sh.command({"hold": {"name": "allbright", "on": False}})
sh.command({"hold": {"name": "blitz", "on": True}})
check(sh.blitz, "STROBE bleibt bedienbar")
sh.command({"hold": {"name": "blitz", "on": False}})
sh.command({"master": 0.5})
check(sh.master == 0.5, "Dimmer bleibt bedienbar")
sh.command({"glevel": {"bar": 0.4}})
check(sh.glevel["bar"] == 0.4, "Gruppen-Regler bleibt bedienbar")
sh.command({"master": 1.0, "glevel_reset": True})
check(sh.pilot, "Schnelleffekte verlassen den Autopilot nicht")

# Anzeige
s = sh.snapshot()
check(s["pilot"] and s["speed"] in ("slow", "mid", "fast") and s["move"] and s["color"] != "auto", "Knoepfe zeigen den Stand")

# Aus: das Markierte bleibt gewaehlt; manuell keine Szenen-Automatik
sh.sc, sh.sa = None, None
s = sh.snapshot()
sh.command({"auto": "toggle"})
check(not sh.pilot, "AUTO nochmal = manuell")
m = sh.snapshot()
check((m["color"], m["speed"], m["move"]) == (s["color"], s["speed"], s["move"]), "Auswahl bleibt beim Wechsel stehen")
sh.command({"speed": "fast"})
check(sh.snapshot()["speed"] == "fast", "manuell: Knoepfe wieder frei")
sh.command({"speed": "auto", "move": "", "color": "auto"})
clk.run(60)
check(sh.sa is None and sh.sc is None, "manuell waehlt die Show keine Szene von selbst")

# Wieder an: alles von Hand weg, auch die Laser-Szene ist sofort aus
sh.command({"scene": laser})
check(sh.sc is not None, "manuell: Laser-Szene waehlbar")
sh.command({"color_toggle": "rot", "eb_preset": 1, "beam": {"gobo": 1}, "aim": "bank"})
sh.command({"auto": "toggle"})
check(sh.pilot and sh.sc is None and not sh.auto_colors and sh.eb_man is None and not sh.beam_man and sh.aim is None,
      "AUTO an raeumt alle Vorgaben weg")
clk.run(0.05)
check(not sh.laser_on, "Laser aus nach AUTO")

# Strobe-Erlaubnis schaltet der Autopilot nie
rig2, s2 = build(strobe=False)
s2.pilot = True
s2.command({"auto": False})
s2.command({"auto": True})
check(s2.strobe is False, "Autopilot schaltet die Strobe-Erlaubnis nicht ein")

# Panel: nur noch ein Auto-Knopf, Sperrzonen vorhanden, Schnelleffekte ausserhalb
p = webpanel.make_page()
check('id="ebauto"' not in p, "Effektband ohne Auto-Knopf")
check("x[0]!=='auto'" in p, "Speed, Stil und Farbe ohne Auto-Knopf")
check(p.count("pbox lk") == 4 and 'id="spst" class="lk"' in p, "Sperrzonen")
check(p.index('id="b_black"') < p.index('id="spst"') and p.index('id="master"') < p.index('id="spst"'),
      "Schnelleffekte und Dimmer liegen vor der Sperrzone")
finish("test_autopilot")
