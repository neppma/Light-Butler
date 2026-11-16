"""Strobe-Grenze je Geraetegruppe: bis zu einer einstellbaren Stufe blitzt die Gruppe beim allgemeinen Strobe mit,
darueber bleibt sie dunkel (z. B. Nanoleaf kommt ab 6,7 Blitzen pro Sekunde nicht mehr mit). Standard: blitzt immer."""
from _common import build, Clock, check, finish

import settings
from dmx import Fixture

d = {p.key: p for p in settings.DEFS}
keys = ["strobe_max_" + k for k in ("bar", "wash", "barlight", "fx", "uv", "spot", "amb", "nano")]
check(all(k in d and d[k].default == 6.0 for k in keys), "Einstellung je Gruppe vorhanden, Standard 10 (immer)")

rig, sh = build(seed=8)
# ein Nanoleaf-Panel zum Pruefen (im Testaufbau gibt es keine nanoleaf.json)
nano = Fixture("nano_1", "nanoleaf_panel", {"channels": 3, "map": {"r": 1, "g": 2, "b": 3}}, 1, "nano",
               target="nanoleaf:10.0.0.1", extra={"nr": 100, "label": "Panel 1"})
rig.fixtures.append(nano)
rig.by_name[nano.name] = nano
clk = Clock(sh)
clk.run(10)
doc = rig["docooler_1"]


def lit(fx):
    return max(fx.values.get(p, 0) for p in fx.map if p not in ("pan", "tilt", "pan_fine", "tilt_fine", "tilt1", "tilt2"))


def blitz_run(hz, secs=2.0):
    """Strobe-Knopf mit hz Blitzen pro Sekunde; zaehlt, in wie vielen Bildern Nanoleaf und Docooler leuchten."""
    sh.command({"blitz": True, "blitz_hz": hz})
    seen = {"nano": 0, "doc": 0}

    def each(_):
        seen["nano"] += lit(nano) > 0
        seen["doc"] += lit(doc) > 0
    clk.run(secs, each=each)
    sh.command({"blitz": False})
    clk.run(0.5)
    return seen


s = blitz_run(10)
check(s["nano"] > 0 and s["doc"] > 0, "Standard: Nanoleaf und Docooler blitzen bei 10 Hz mit")

sh.cfg.set("strobe_max_nano", 4)                            # Nanoleaf bis Stufe 4 = 5 Blitze pro Sekunde
for hz, expect in ((1, True), (5, True), (6.7, False), (10, False)):
    s = blitz_run(hz)
    check((s["nano"] > 0) == expect and s["doc"] > 0,
          f"Grenze 5 Hz, Strobe {hz} Hz: Nanoleaf {'blitzt' if expect else 'bleibt dunkel'}, Docooler blitzt")

sh.cfg.set("strobe_max_nano", 0)
check(blitz_run(1)["nano"] == 0, "nie: Nanoleaf blitzt auch bei 1 Hz nicht")
sh.cfg.set("strobe_max_nano", 6)

# Effektband (Ambiente) bleibt ueber der Grenze dunkel, auch sein Dimmer
band = [f for f in rig.fixtures if f.type == "wled_preset"]
if band:
    sh.cfg.set("strobe_max_amb", 2)                         # bis 2 Blitze pro Sekunde
    sh.command({"blitz": True, "blitz_hz": 10})
    mx = [0]
    clk.run(1, each=lambda _: mx.__setitem__(0, max(mx[0], band[0].values.get("dimmer", 0))))
    sh.command({"blitz": False})
    check(mx[0] == 0, "Effektband: ueber der Grenze bleibt der Dimmer auf 0")
    sh.cfg.set("strobe_max_amb", 6)

# WOW!: schneller werdend; mit Grenze 1 Hz bleibt der Nanoleaf im Blitzteil dunkel, im Dauerlicht am Ende leuchtet er
sh.cfg.set("strobe_max_nano", 1)
sh.command({"build": True})
frames = []
clk.run(8, each=lambda _: (setattr(sh, "build_seen", sh.last_t),          # Taster bleibt gedrueckt
                           frames.append((sh.build_p, lit(nano) > 0))))
fast = [on for p, on in frames if 0.3 < p < 0.7]          # Blitzteil (das Dauerlicht beginnt kurz vor dem Ende)
check(fast and not any(fast), "WOW!: im schnellen Teil bleibt der Nanoleaf dunkel")
check(any(on for p, on in frames if p >= 0.9), "WOW!: im Dauerlicht am Ende leuchtet er wieder")

finish("test_strobe_grenze")
