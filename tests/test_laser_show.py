"""Szene Laser, KTV mit 34 Kanaelen: Choreografie im Takt. Faecher, Wippen, Schwenken, Pumpen, dazu Break, Aufbau und Drop.
Nur Form, Lage und Farbe, nie ausserhalb der Sperren."""
from _common import DT, Clock, build, check, ch, finish

import laser_show as ls


def frames(state="normal", start=0.0, n=800, step=0.05, **kw):
    return [ls.ktv_scene(start + i * step, state, **kw) for i in range(n)]


all_ = frames() + frames(start=200) + frames("drop") + frames("break") + frames("build") + frames(arousal=0.9)
check(all(0 <= v <= 255 for f in all_ for v in f.values()), "alle Werte gueltig")
check(all(1 <= f["pos_x"] <= 127 and 1 <= f["pos_y"] <= 127 for f in all_), "Position im Bereich der Anleitung (1 bis 127, keine Bewegungs-Automatik)")
check(all(f["effect"] in (46, 35) for f in all_), "nur die Lieblingsmuster 46 und 35, nie Selbstlauf- oder Sound-Bereich")
check(ls.ktv_scene(33.3) == ls.ktv_scene(33.3), "gleiche Stelle, gleiches Bild")
fans0 = [ls.ktv_scene(i * 0.1)["draw"] for i in range(40)]
check(fans0[0] == 20 and fans0[-1] > 200 and fans0 == sorted(fans0), "Teil 1: Faecher geht ueber einen Takt vom Punkt zur vollen Breite auf")
wip = [ls.ktv_scene(16 + i * 0.1)["pos_y"] for i in range(40)]
check(max(wip) - min(wip) > 60 and len({ls.ktv_scene(16 + i * 0.1)["pos_x"] for i in range(40)}) == 1, "Teil 2: Wippen auf und ab")
sw_ = [ls.ktv_scene(32 + i * 0.1)["pos_x"] for i in range(80)]
check(max(sw_) - min(sw_) > 60 and len({ls.ktv_scene(32 + i * 0.1)["pos_y"] for i in range(80)}) == 1, "Teil 3: Schwenken links und rechts")
pu = [ls.ktv_scene(48 + i * 0.1)["draw"] for i in range(20)]
check(pu[0] > 200 and pu[9] < 60 and pu[10] > 200, "Teil 4: Pumpen auf jeden Schlag")
check(ls.ktv_scene(0)["effect"] != ls.ktv_scene(8)["effect"], "alle 2 Takte das andere Muster")
fxs = (10, 20, 30, 40, 50)
check(ls.ktv_scene(0, fx_set=fxs)["effect"] == 10 and ls.ktv_scene(8, fx_set=fxs)["effect"] == 20, "eigene Muster A und B")
check([ls.ktv_scene(i, "drop", fx_set=fxs)["effect"] for i in range(2)] == [30, 40], "eigene Muster beim Drop")
check(ls.ktv_scene(0, "break", fx_set=fxs)["effect"] == 50, "eigenes Muster im Break")
zo = [ls.ktv_scene(i * 0.1)["size"] for i in range(40)]
check(zo[0] > zo[-1] and zo == sorted(zo, reverse=True), "Zoom (Kanal 6) laeuft mit dem Faecher von klein nach gross")
check(ls.ktv_scene(0, "drop")["size"] < ls.ktv_scene(0, "break")["size"], "Drop gross, Break klein")
d = [ls.ktv_scene(i, "drop")["effect"] for i in range(4)]
check(d == [46, 35, 46, 35] and all(ls.ktv_scene(i * 0.3, "drop")["color"] == 255 for i in range(20)), "Drop: Musterwechsel auf jeden Schlag, bunt")
check(ls.ktv_scene(0.0, "drop")["draw"] == 230, "Drop: voll offen")
br = [ls.ktv_scene(i * 0.25, "break")["draw"] for i in range(64)]
check(max(br) < 100, "Break: schmale, ruhige Linie")
bu = [ls.ktv_scene(i, "build")["draw"] for i in range(4)]
check(bu == sorted(bu, reverse=True) and bu[3] < bu[0], "Aufbau: wird zum Taktende schmaler")
check(ls.ktv_scene(0, bar=3)["draw"] == 20 and ls.ktv_scene(2.9, bar=3)["draw"] > 200, "auch im 3/4-Takt")

# In der Show
rig, sh = build(seed=3)
c = Clock(sh)
sh.cfg.set("laser_mode", 0)
sh.cfg.set("laser_duty", 100)
c.run(5)
sh.command({"scene": "Laser"})
seen = []


def each(t):
    seen.append({p: ch(rig, "laser", p) for p in ("power", "pos_x", "pos_y", "draw", "effect", "color", "b_group", "draw_a", "grating")})


c.run(70, each)
on = [f for f in seen if f["power"] > 0]
check(on, "Szene Laser: Laser an")
check(len({f["draw"] for f in on}) > 20 and len({f["pos_y"] for f in on}) > 5 and len({f["pos_x"] for f in on}) > 5, "Faecher und Lage bewegen sich in der Show")
check({f["effect"] for f in on} == {46, 35}, "beide Muster kommen vor")
sh.cfg.set("ktv_fx_a", 12)
sh.cfg.set("ktv_fx_b", 14)
sh.cfg.set("ktv_fx_drop_a", 12)
sh.cfg.set("ktv_fx_drop_b", 14)
sh.cfg.set("ktv_fx_break", 12)
later = []
c.run(40, lambda t: later.append(ch(rig, "laser", "effect")))
check(set(later) - {0} == {12, 14}, "Einstellungen wirken sofort, ohne Neustart")
check(sh.cfg["ktv_fx_a"] <= 244, "Einstellungen enden bei 244")
check(all(f["b_group"] == 0 and f["draw_a"] == 0 and f["grating"] == 0 for f in seen), "Muster B und Sonderkanaele bleiben 0")
sh.command({"freeze": True})
c.run(DT)
check(ch(rig, "laser", "power") == 0, "FREEZE: Laser sofort aus")
sh.command({"freeze": False})
sh.command({"blackout": True})
c.run(DT)
check(ch(rig, "laser", "power") == 0 and not any(rig.render()[300:334]), "BLACKOUT: alles 0")
sh.command({"blackout": False})
sh.command({"auto": True})
c.run(DT)
check(not any(rig.render()[300:334]), "Szene verlassen: alles 0")
# Ohne Strobe-Erlaubnis bleibt die Grenze der Pulse
rig, sh = build(seed=3, strobe=False)
c = Clock(sh)
sh.cfg.set("laser_mode", 0)
c.run(5)
sh.command({"scene": "Laser"})
times, prev = [], 0


def each2(t):
    global prev
    v = ch(rig, "laser", "power")
    if v and not prev:
        times.append(t)
    prev = v


c.run(30, each2)
worst = max([sum(1 for x in times if a <= x < a + 1.0) for a in times] or [0])
check(worst <= 2, f"ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde (gemessen {worst})")
finish("test_laser_show")
