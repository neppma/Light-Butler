"""Vega-Strahl in AUTO (Einstellung vega_live, Standard an): ruhig offen ohne Drehung; hohe Energie alle fuenf Gobos,
Drehung in beide Richtungen nach Stufe und Tempo; Aufbau enger mit stehendem Prisma; Drop: naechstes Gobo, Prisma dreht.
Nach dem Drop in eine Szene: Prisma aus, Zoom normal. Aus: wie frueher."""
from _common import zurueck, build, Clock, check, finish

import settings

check({p.key: p for p in settings.DEFS}["vega_live"].default == 1.0, "Standard: an")
rig, sh = build(seed=3)
vega = rig["vega"]
V = vega.values
log = []
Clock(sh).run(150, lambda t: log.append((sh.state, sh.eff_tier(), sh.build_prog, V["gobo"], V["gobo_rot"], V["prism"], V["zoom"],
                                         sh.state == "drop" and t - 0 >= 0)))
calm = [e for e in log if e[0] == "normal" and e[1] <= 1]
high = [e for e in log if e[0] == "normal" and e[1] >= 2]
builds = [e for e in log if e[0] == "build"]
drops = [e for e in log if e[0] == "drop"]
check(calm and all(e[3] == 0 and e[4] == 0 and e[5] == 0 and e[6] == 255 for e in calm), f"ruhig: offen, keine Drehung, kein Prisma ({len(calm)} Bilder)")
check(high and all(e[3] != 0 and e[4] != 0 and e[5] == 0 for e in high), f"hohe Energie: Gobo und Drehung ({len(high)} Bilder)")
gobos = {e[3] for e in log if e[3]}
check(len(gobos) >= 4, f"mehrere Gobos im Wechsel ({sorted(gobos)})")
check(any(11 <= e[4] <= 129 for e in high + builds + drops) and any(135 <= e[4] <= 255 for e in high + builds + drops),
      "Drehung in beide Richtungen")
late = [e for e in builds if e[2] > 0.21]
check(late and all(e[6] < 255 and e[5] == 70 for e in late), f"Aufbau: Strahl enger, Prisma steht ({len(late)} Bilder)")
sh.state, sh.build_prog = "build", 1.0                    # langer Aufbau (10 s): deutlich enger
sh._vega_beam_auto(sh._t_now)
check(V["zoom"] == 153 and V["prism"] == 70, f"langer Aufbau: Zoom 60 %, Prisma steht ({V['zoom']})")
check(drops and any(135 <= e[5] <= 194 for e in drops), "Drop: Prisma dreht")

# Drop: sofort das naechste Gobo
rig2, sh2 = build(seed=3)
seq = []
Clock(sh2).run(150, lambda t: seq.append((sh2.state, rig2["vega"].values["gobo"])))
changed = [i for i in range(1, len(seq)) if seq[i][0] == "drop" and seq[i - 1][0] != "drop"]
check(changed and all(seq[i][1] != seq[i - 2][1] for i in changed), "Drop: Gobo wechselt sofort")

# nach dem Drop in eine Szene: Prisma aus, Zoom normal
rig3, sh3 = build(seed=3)
c3 = Clock(sh3)
for _ in range(6000):
    c3.run(0.025)
    if sh3.state == "drop" and rig3["vega"].values["prism"] > 0:
        break
check(rig3["vega"].values["prism"] > 0, "Vorbedingung: Prisma im Drop an")
sh3.command({"scene": "Switch It Up slow"})
c3.run(0.1)
check(rig3["vega"].values["prism"] == 0 and rig3["vega"].values["zoom"] == 255, "Szene danach: Prisma aus, Zoom normal")

# Beam von Hand geht vor
zurueck(sh3)
sh3.command({"beam": {"gobo": 2, "prism": 0}})
c3.run(2)
check(rig3["vega"].values["gobo"] == 46 and rig3["vega"].values["prism"] == 0, "Beam von Hand geht vor")

# aus: wie frueher (kein Prisma, Zoom fest)
rig4, sh4 = build(seed=3)
sh4.cfg.set("vega_live", 0)
pz = set()
Clock(sh4).run(150, lambda t: pz.add((rig4["vega"].values["prism"], rig4["vega"].values["zoom"])))
check(pz == {(0, 255)}, "aus: kein Prisma, Zoom unveraendert")
finish("test_vega_strahl")
