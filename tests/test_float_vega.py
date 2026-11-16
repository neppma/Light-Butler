"""Bewegung Float (Ente): der Vega schwenkt rechts-links und schwebt dabei leicht auf und ab (liegende Acht).
Die Docooler bleiben parallel wie bisher."""
from _common import build, Clock, check, finish

rig, sh = build(seed=3)
clk = Clock(sh)
clk.run(3)
sh.command({"move": "duck"})
us, vs = [], []
clk.run(8, lambda t: (us.append(sh.mo["u"]), vs.append(sh.mo["v"])))
check(max(us) - min(us) > 0.7, f"Float: Vega schwenkt weit rechts-links ({min(us):.2f}..{max(us):.2f})")
check(0.15 < max(vs) - min(vs) < 0.3, f"Float: leichtes Auf und Ab ({min(vs):.2f}..{max(vs):.2f})")
check(abs(sum(vs) / len(vs) - 0.5) < 0.05, "Float: um die Mitte")
sh.command({"fine": {"grp": "mv", "btn": "duck", "key": "size", "v": 0}})
clk.run(0.1)
check(abs(sh.mo["v"] - 0.5) < 1e-9 and abs(sh.mo["u"] - 0.5) < 1e-9, "Size 0 %: steht in der Mitte")
finish("test_float_vega")
