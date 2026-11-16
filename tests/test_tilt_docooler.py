"""Bewegung Tilt (Rauf-Runter): die vier Docooler bewegen sich nicht (sie koennen nur seitwaerts), nur der Vega nickt.
Bei Pan (Rechts-Links) schwenken sie wie bisher. Feste Szenen mit Rauf-Runter bleiben unveraendert."""
from _common import build, Clock, check, finish

rig, sh = build(seed=3)
clk = Clock(sh)
clk.run(3)
docs = [f for f in rig.fixtures if f.group == "bars"]
check(len(docs) == 4, "vier Docooler")


def watch(secs):
    tilts, vs = set(), []
    clk.run(secs, lambda t: (tilts.update((f.name, f.values["tilt1"], f.values["tilt2"]) for f in docs),
                             vs.append(rig["vega"].values["tilt"])))
    return tilts, vs


sh.command({"move": "vertical"})
clk.run(2)                                                # Docooler fahren erst in die Ruhelage
tilts, vs = watch(6)
check(len(tilts) == 4, f"Tilt: Docooler stehen still ({len(tilts)} Stellungen)")
check(max(vs) - min(vs) > 20, f"Tilt: der Vega bewegt sich rauf und runter ({min(vs)}..{max(vs)})")

sh.command({"move": "horizontal"})
tilts, _ = watch(6)
check(len(tilts) > 20, f"Pan: Docooler schwenken wie bisher ({len(tilts)} Stellungen)")

sh.command({"scene": "Grow Slow"})
clk.run(2)
tilts, _ = watch(8)
check(len(tilts) > 4, "feste Szene Grow Slow (Rauf-Runter): unveraendert, Docooler faechern")

finish("test_tilt_docooler")
