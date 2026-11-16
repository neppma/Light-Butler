"""Bei Stille (keine Musik, Ruhemodus) sind die Nanoleaf-Panels ganz dunkel; die anderen Lichter atmen weiter."""
from _common import build, Clock, check, finish

from dmx import Fixture

rig, sh = build(seed=13)
nano = Fixture("nano_1", "nanoleaf_panel", {"channels": 3, "map": {"r": 1, "g": 2, "b": 3}}, 1, "nano",
               target="nanoleaf:10.0.0.1", extra={"nr": 100, "label": "Panel 1", "x": 0.3})
rig.fixtures.append(nano)
rig.by_name[nano.name] = nano
sh.nano = [(nano, 0)]
clk = Clock(sh)
clk.run(10)
lit = lambda f: max(f.values.get(p, 0) for p in ("r", "g", "b"))
check(lit(nano) > 0, "mit Musik: Nanoleaf leuchtet")

# Stille: Ruhemodus erzwingen (wie nach einigen Sekunden ohne Musik)
seen_nano, seen_bars = [], []
def each(_):
    sh.state = "idle"
    sh._render_idle(sh.last_t, 0.025)
    seen_nano.append(lit(nano))
    seen_bars.append(max(sh.bars[0][0].values.get(p, 0) for p in sh.bars[0][0].map))
clk.run(5, each=each)
check(max(seen_nano) == 0, "Stille: Nanoleaf ganz dunkel")
check(max(seen_bars) > 0, "Stille: die anderen Lichter atmen weiter")

finish("test_nanoleaf_stille")
