"""Blitz: gleichmaessiger Takt, Washes dunkel, Effektband synchron, Strobe-Erlaubnis."""
import collections
from _common import build, ch, Clock, check, finish

WASH = ["rgbuv_7", "rgbuv_8", "rgbuv_10", "rgbuv_11"]


def runlen(seq):
    out, cur, n = [], seq[0], 1
    for v in seq[1:]:
        if v == cur:
            n += 1
        else:
            out.append((cur, n))
            cur, n = v, 1
    return out


rig, sh = build()
clk = Clock(sh)
clk.run(10)
sh.command({"blitz": True})
print("Blitz-Takt (Bilder an / aus je Zyklus):")
for hz, period in ((1, 40), (2, 20), (4, 10), (5, 8), (6.7, 6), (10, 4)):
    sh.command({"blitz_hz": hz})
    clk.run(1)
    seq = []
    clk.run(6, lambda t: seq.append(1 if ch(rig, "docooler_2", "w1") > 0 else 0))
    r = runlen(seq)[1:-1]
    on = collections.Counter(n for v, n in r if v == 1)
    off = collections.Counter(n for v, n in r if v == 0)
    check(on == {2: sum(on.values())} and off == {period - 2: sum(off.values())},
          f"{hz} Hz: an {dict(on)}, aus {dict(off)} (Periode {period} Bilder)")

sh.command({"blitz_hz": 10})
clk.run(1)
wash_max, band = [], []
clk.run(2, lambda t: (wash_max.append(max(ch(rig, n, k) for n in WASH for k in ("r", "g", "b", "uv"))),
                      band.append((ch(rig, "effektband", "dimmer"), ch(rig, "effektband", "preset"),
                                   ch(rig, "docooler_2", "w1") > 0))))
check(max(wash_max) == 0, "die vier 4in1-Washes bleiben beim Blitz dunkel")
check({p for _, p, _ in band} == {35}, "Effektband steht beim Blitz auf Preset 35 (Solid weiss)")
check(all((d > 0) == w for d, p, w in band[8:]), "Effektband blitzt im Takt der Docooler")
sh.command({"blitz": False})

# ohne Strobe-Erlaubnis nie schneller als 2 pro Sekunde
rig2, sh2 = build(strobe=False)
sh2.command({"blitz_hz": 10})
check(sh2.snapshot()["blitz_eff"] <= 2.0, "ohne Strobe-Erlaubnis hoechstens 2 Blitze pro Sekunde")
finish("test_blitz")
