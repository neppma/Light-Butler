"""Szenen-Automatik: in AUTO waehlt die Show ab und zu kurz selbst eine Szene, nach ihrer Stelle in der Szenenliste
(ruhig vorne, wild hinten, Drop ganz hinten). Nie Laser, Ziele, All off, RESET, QUIZ; Strobe-Szenen nur mit Erlaubnis.
Eigene Bedienung beendet die Szene und pausiert die Automatik. Aus (Standard): das Licht bleibt Bild fuer Bild gleich."""
from _common import build, Clock, check, finish

import settings
from show import SA_RANGE


def run(strobe=True, secs=150, prob=100, bars=4, setup=None, each=None):
    rig, sh = build(strobe=strobe, seed=3, pilot=True)
    clk = Clock(sh)
    sh.cfg.set("sa_on", 1)
    sh.cfg.set("sa_prob", prob)
    sh.cfg.set("sa_bars", bars)
    if setup:
        setup(sh)
    log, prev = [], None

    def step(t):
        nonlocal prev
        cur = sh.sa["name"] if sh.sa else None
        if cur and cur != prev:
            pos = [s.name for s in sh.scene_defs].index(cur) / (len(sh.scene_defs) - 1)
            log.append({"name": cur, "pos": pos, "start": sh.step, "until": sh.sa["until_step"], "drop": sh.sa["drop"],
                        "state": sh.state, "tier": sh._base_tier() if sh.sc is None else sh.tier, "laser": sh.laser_on})
        if cur and log:
            log[-1]["laser"] = log[-1]["laser"] or sh.laser_on
            log[-1]["end"] = sh.step
        if each:
            each(sh, t)
        prev = cur
    clk.run(secs, step)
    return sh, log


defs = {p.key: p for p in settings.DEFS if p.group == settings.G_SCAUTO}
check(defs["sa_on"].default == 0.0, "Standard: Szenen-Automatik aus")

rig, sh = build(seed=3, pilot=True)
seen = []
Clock(sh).run(60, lambda t: seen.append(sh.sa))
check(all(x is None for x in seen) and sh.snapshot()["autoscene"] == "", "aus: keine automatischen Szenen")

sh, log = run()
names = {e["name"] for e in log}
check(len(log) >= 5, f"an: Szenen werden gewaehlt ({len(log)}: {sorted(names)[:6]} ...)")
specials = {s.name for s in sh.scene_defs if s.special} | {"QUIZ"}
check(not (names & specials), "nie Laser, Ziele, All off, RESET oder QUIZ")
check(not any(e["laser"] for e in log), "Laser bleiben aus")
check(all(e["end"] - e["start"] <= 4 * 4 + 1 for e in log if not e["drop"]), "hoechstens 4 Takte je Szene")
drops = [e for e in log if e["drop"]]
check(drops and all(e["pos"] >= 0.75 for e in drops), f"Drop: wilde Szenen vom Ende der Liste ({[e['name'] for e in drops]})")
normal = [e for e in log if not e["drop"] and e["state"] == "normal"]
ok = [SA_RANGE[max(0, min(3, int(e["tier"])))][0] - 0.05 <= e["pos"] <= SA_RANGE[max(0, min(3, int(e["tier"])))][1] + 0.05 for e in normal]
check(normal and sum(ok) >= 0.8 * len(ok), f"Stelle in der Liste passt zur Stufe ({sum(ok)}/{len(ok)})")
check(all(a["name"] != b["name"] for a, b in zip(log, log[1:])), "nie dieselbe Szene zweimal hintereinander")

sh2, log2 = run(strobe=False)
strobe_sc = {s.name for s in sh2.scene_defs if s.mix in ("strobe", "lightning") or s.preset in (8, 32)}
check(log2 and not ({e["name"] for e in log2} & strobe_sc), f"ohne Strobe-Erlaubnis keine Strobe-Szenen ({sorted(strobe_sc)})")
check(sh2.strobe is False, "Strobe-Erlaubnis wird nie eingeschaltet")

# eigene Bedienung: Szene endet sofort, Pause
state = {"done": False, "after": []}


def poke(sh, t):
    if not state["done"] and sh.sa is not None and t > 20:
        sh.command({"hold": {"name": "freeze", "on": True}})
        state["done"] = True
        state["t"] = t
        state["sc_after"] = sh.sc
    elif state["done"]:
        state["after"].append(sh.sa)


sh3, _ = run(setup=lambda s: s.cfg.set("sa_pause_s", 600), each=poke, secs=90)
check(state["done"] and state["sc_after"] is None or (state["sc_after"] is not None and state["sc_after"].name == "Eigene"),
      "Schnelleffekt beendet die automatische Szene")
check(all(x is None for x in state["after"]), "danach Pause: keine automatischen Szenen")

# AUTO-Vorgaben (Bewegung gewaehlt): keine automatischen Szenen
sh4, log4 = run(setup=lambda s: (setattr(s, "pilot", False), s.command({"move": "circle"}), s.cfg.set("sa_pause_s", 10)), secs=60)
check(not log4, "manuell: keine automatischen Szenen")

# Panel
import webpanel
page = webpanel.make_page()
check("S.autoscene===b.dataset.scene" in page and "classList.toggle('on',!!S.pilot||!!S.sm_show)" in page, "Panel: Szene mit AUTO markiert, AUTO bleibt an")
finish("test_szenen_automatik")
