"""Abwechslung Docooler/Vega (AUTO, Einstellung dc_mix): die vier Docooler leuchten in wechselnden Gruppierungen
(aussen, innen, einzeln wandernd, links/rechts, einer allein), der Vega in der Mitte vor allem, wenn die inneren
dunkel sind. Stufe 3 und Drop wie bisher, ausgeschaltet alles wie vorher."""
from _common import build, check, finish, Clock


def lit(fx):
    return sum(fx.values.get(p, 0) for p in fx.light_params)


rig, sh = build(seed=3)
check([f.name for f in sh.dc_order] == ["docooler_1", "docooler_2", "docooler_5", "docooler_6"],
      "Reihenfolge an der Decke nach DMX-Adresse: 1, 2, (Vega), 5, 6")
check(sh.cfg["dc_mix"] == 1.0 and sh.cfg["dc_mix_bars"] == 8.0, "Standard: an, neue Gruppierung alle 8 Takte")

# ---- Gruppierungen einzeln -----------------------------------------------------------------------
sh.dc_pat = "aussen"
check(sh._dc_targets(1) == [1, 0, 0, 1], "aussen: Docooler 1 und 6")
sh.dc_pat = "innen"
check(sh._dc_targets(1) == [0, 1, 1, 0], "innen: Docooler 2 und 5")
sh.dc_pat = "wandern"
seq = []
for st in range(0, 8, 2):
    sh.step = st
    seq.append(sh._dc_targets(1).index(1.0))
check(seq == [0, 3, 1, 2], "wandern: einzeln von aussen nach innen (1, 6, 2, 5), alle 2 Beats weiter")
sh.dc_pat = "seiten"
sh.step = 0
a = sh._dc_targets(1)
sh.step = sh.bar_len
b = sh._dc_targets(1)
check(a == [1, 1, 0, 0] and b == [0, 0, 1, 1], "seiten: links und rechts im Wechsel, jeden Takt")
sh.dc_pat = "wechsel"
sh.step = 0
a = sh._dc_targets(2)
sh.step = sh.bar_len
b = sh._dc_targets(2)
check(a == [1, 0, 0, 1] and b == [0, 1, 1, 0], "wechsel: aussen und innen im Wechsel, jeden Takt")
sh.dc_pat, sh.dc_solo = "solo", 2
check(sh._dc_targets(0) == [0, 0, 1, 0], "solo: einer allein")
check(set(sh.DC_POOLS[0]) == {"solo", "aussen", "innen"}, "ruhig: nur 1 oder 2 Docooler")

# ---- im Lauf: Stufe 1 (Low) ----------------------------------------------------------------------
rig, sh = build(seed=3)
sh.command({"speed": "slow"})
vega, docs = rig["vega"], sh.dc_order
st = {"dark_some": 0, "all_dark": 0, "frames": 0, "pats": set(), "vega_inner": [], "vega_outer": []}


def each(t):
    if sh.state != "normal" or sh.eff_tier() != 1 or sh.dc_mask is None:
        return
    st["frames"] += 1
    st["pats"].add(sh.dc_pat)
    d = [lit(f) for f in docs]
    if min(d) == 0 and max(d) > 0:
        st["dark_some"] += 1
    m = [sh.dc_mask[f] for f in docs]
    if sh.dc_pat == "innen" and min(m[1], m[2]) > 0.99:
        st["vega_inner"].append(vega.values["dimmer"])
    if sh.dc_pat == "aussen" and max(m[1], m[2]) < 0.01:
        st["vega_outer"].append(vega.values["dimmer"])


c = Clock(sh)
c.run(240, each=each)
check(st["frames"] > 500, f"Stufe 1 laeuft lange genug ({st['frames']} Bilder)")
check(st["dark_some"] > 0.5 * st["frames"], f"meist sind einzelne Docooler ganz dunkel ({st['dark_some']} von {st['frames']})")
check(len(st["pats"]) >= 2, f"Gruppierung wechselt ({sorted(st['pats'])})")
check(st["pats"] <= set(sh.DC_POOLS[1]), "nur Gruppierungen der Stufe 1")
check(not st["vega_inner"] or max(st["vega_inner"]) == 0, "innere Docooler an: Vega dunkel")
check(not st["vega_outer"] or max(st["vega_outer"]) > 0, "nur aeussere an: Vega leuchtet in der Mitte")

# ---- Stufe 3 (Hot) und Drop wie bisher: Docooler gleich mit und ohne Abwechslung --------------------
runs = []
for on in (1, 0):
    rig, sh = build(seed=3)
    sh.command({"set": {"dc_mix": on}})
    sh.command({"speed": "fast"})
    vals, masks = [], []
    Clock(sh).run(60, each=lambda t: (vals.append((sh.eff_tier(), [lit(f) for f in sh.dc_order], rig["vega"].values["dimmer"])),
                                       masks.append(sh.dc_mask)))
    runs.append((vals, masks))
same = all(a == b for a, b in zip(runs[0][0], runs[1][0]) if a[0] == 3)
check(same, "Stufe 3 und Drop: Docooler und Vega wie ohne Abwechslung")
check(all(m is None for m in runs[1][1]), "ausgeschaltet: keine Gruppierung")

# ---- Drop: danach gleich eine neue Gruppierung ---------------------------------------------------
rig, sh = build(seed=3)
sh.command({"speed": "slow"})
Clock(sh).run(5)
sh.state = "normal"
sh._dc_update(0.025)
before = sh.dc_pat
sh.last_drop += 1.0
sh._dc_update(0.025)
check(sh.dc_pat != before, "nach einem Drop gleich eine neue Gruppierung")
finish("test_docooler_abwechslung")
