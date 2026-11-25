"""Einzel-Strobe im AUTO-Modus."""
import collections
from _common import build, ch, Clock, check, finish

WASH = ["rgbuv_7", "rgbuv_8", "rgbuv_10", "rgbuv_11"]
rig, sh = build(seed=3)
sh.cfg.set("drop_step", 0.0)                     # prueft den Einzel-Strobe (ab Vollgas), nicht die Stufe nach dem Drop
clk = Clock(sh)
events, other, wash_vals = [], set(), set()
cur = [None]


def watch(t):
    s = sh.solo
    if s and cur[0] is None:
        cur[0] = s["fx"].name
        events.append(cur[0])
    elif not s:
        cur[0] = None
    if s:
        n = s["fx"].name
        if n in WASH:
            wash_vals.add((ch(rig, n, "mode"), ch(rig, n, "dimmer")))
        for f in rig.fixtures:
            if f.name != n and f.map.get("strobe") and f.tdef.get("hw_strobe"):
                other.add(ch(rig, f.name, "strobe"))


clk.run(240, watch)
check(len(events) >= 5, f"Einzel-Strobes in 240 s AUTO: {len(events)}")
check(not ({"eyes", "derby", "laser"} & set(events)), "Eyes, Derby und Laser sind nie dabei")
check(other <= {0}, "Strobe-Kanaele der anderen Fixtures bleiben waehrend eines Solos auf 0")
check(all(m == 230 for m, d in wash_vals) or not wash_vals, "Wash im Solo: Mode 230 (Strobe-Programm)")
modes = []
clk.run(3, lambda t: modes.append(max(ch(rig, n, "mode") for n in WASH)))
check(max(modes) <= 10, "Wash-Mode ausserhalb des Solos wieder im sicheren Bereich (hoechstens 10)")

for label, kw, setup in (("ohne Strobe-Erlaubnis", dict(strobe=False), None),
                         ("bei einer Szene", {}, lambda s: s.command({"scene": "rot"})),
                         ("bei Blackout", {}, lambda s: s.command({"blackout": True}))):
    r2, s2 = build(seed=3, **kw)
    c2 = Clock(s2)
    if setup:
        setup(s2)
    n = []
    c2.run(240, lambda t: n.append(1 if s2.solo else 0))
    check(sum(n) == 0, f"kein Einzel-Strobe {label}")

# Test-Befehl
rig3, s3 = build()
c3 = Clock(s3)
c3.run(5)
s3.command({"solo_test": "rgbuv_8"})
frames = []
c3.run(4, lambda t: frames.append(1 if s3.solo else 0))
check(abs(sum(frames) * 0.025 - 3.0) < 0.1, "Test-Befehl: 3 Sekunden Einzel-Strobe")
try:
    s3.command({"solo_test": "eyes"})
    check(False, "Laser-Geraet muss abgelehnt werden")
except ValueError:
    check(True, "Laser-Geraet (Eyes) wird abgelehnt")
finish("test_solo")
