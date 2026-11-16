"""Gruppe ambient fuer jedes Farbgeraet (z. B. das PAR an der Bar): dann laeuft es so ruhig wie Theke und Couchtisch
(1 s Ueberblendung, kleine Aenderungen werden nicht gesendet, kein Beat). Ohne Umstellung bleibt alles wie bisher."""
from _common import Clock, check, finish, build, PI

import os
import fixture_edit
import show as sw
from audio import Simulator
from dmx import Rig

rig, sh = build(seed=3)
check([f.name for f in sh.rgb_amb] == ["par", "theke", "couchtisch"], "Standard: Ambiente = Barlicht, Theke und Couchtisch")
par = rig["par"]
check("ambient" in fixture_edit.allowed_groups(par.type, par.tdef), "PAR darf in die Gruppe ambient")
check("ambient" in fixture_edit.allowed_groups("docooler_90w", rig["docooler_1"].tdef), "Docooler auch")
uvf = next(f for f in rig.fixtures if "uv1" in f.map)
check("ambient" not in fixture_edit.allowed_groups(uvf.type, uvf.tdef), "UV-Leiste nicht (keine Farbe)")


def run(group):
    r = Rig(os.path.join(PI, "fixtures.yaml"))
    r["vega"].extra["limits_verified"] = True
    r["par"].group = group
    s = sw.Show(r, Simulator(), aim_file=os.devnull, strobe=False, settings_file=None, scenes_file=None,
                mixxx=None, texts_file=None)
    s._rng.seed(3)
    vals, steps = [], []
    c = Clock(s)

    def each(t):
        if s.state not in ("normal",):
            vals.clear()                                     # nur direkt aufeinanderfolgende Bilder vergleichen
            return
        v = tuple(r["par"].values.get(k, 0) for k in ("r", "g", "b"))
        if vals:
            steps.append(max(abs(a - b) for a, b in zip(v, vals[-1])))
        vals.append(v)
    c.run(120, each=each)
    return s, vals, steps


s_amb, v_amb, st_amb = run("ambient")
check(s_amb.rgb_amb[-1].name == "par" or "par" in [f.name for f in s_amb.rgb_amb], "PAR in ambient: von der Ambiente-Funktion gesteuert")
check("par" not in [f.name for f, _ in s_amb.barlight], "und nicht mehr vom Barlicht")
s_bar, v_bar, st_bar = run("bar")
jumps = lambda st: sum(1 for x in st if x > 20)
check(v_amb and v_bar, "beide Laeufe haben normale Musik")
check(jumps(st_bar) > 0 and jumps(st_amb) == 0, f"kein Flackern mehr: Spruenge ueber 20 ({jumps(st_amb)} statt {jumps(st_bar)})")
check(max(st_amb) <= max(st_bar), f"und in kleineren Schritten (max {max(st_amb)} statt {max(st_bar)})")
check(s_amb.rig["par"].values.get("strobe", 0) == 0, "Strobe-Kanal bleibt 0")
finish("test_ambiente_gruppe")
