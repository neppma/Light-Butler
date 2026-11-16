"""Licht-Mix Chase-Out und Chase-In: wie Scanner ein Lauflicht von Geraet zu Geraet (Reihenfolge wie Scanner, nach DMX-Adresse),
aber symmetrisch: Chase-Out von der Mitte paarweise nach aussen, Chase-In von aussen zur Mitte. Immer nur ein Paar an.
Das Effektband ist dabei aus."""
from _common import build, Clock, check, finish
from scenes import Z


def ring_log(btn, secs=8.0, speed=None):
    rig, sh = build(seed=3)
    clk = Clock(sh)
    clk.run(3)
    sh.command({"mix": btn})
    if speed:
        sh.command({"speed": speed})
    clk.run(1)
    eng = sh.scenes
    n = eng.scan_n
    rings, seq = [], []
    for _ in range(int(secs / 0.025)):
        clk.run(0.025)
        raw = {}
        for z in eng.zones:
            k = eng.scan_idx.get(z.fx.name)
            if k is None or z.kind in ("amb", "uv", "nano"):
                continue
            raw[k] = max(raw.get(k, 0.0), eng.mix_value(sh.sc, z, 0.0, clk.t, 0.025, False, 0.0))
        for fx in eng.spot:                                 # Vega laeuft mit (eigene Ausgabe, gleiche Reihenfolge)
            raw[eng.scan_idx[fx.name]] = eng.mix_value(sh.sc, Z(fx, 0, "spot", 0.5, 99), 0.0, clk.t, 0.025, False, 0.0)
        full = sorted(k for k, v in raw.items() if v > 0.99)
        on = sorted(k for k, v in raw.items() if v > 0.01)
        rings.append((full, on))
        d = {abs(k - (n - 1) / 2.0) for k in full}
        if d and (not seq or seq[-1] != min(d)):
            seq.append(min(d))
    return rings, seq, n, sh


for btn, out in (("nach aussen", True), ("nach innen", False)):
    rings, seq, n, sh = ring_log(btn)
    name = "Chase-Out" if out else "Chase-In"
    check(all(len(full) <= 2 and full == on for full, on in rings), f"{name}: immer nur ein Paar an, sonst aus (wie Scanner)")
    check(all(len(full) == 0 or (len(full) == 2 and full[0] + full[1] == n - 1) or (len(full) == 1 and 2 * full[0] == n - 1)
              for full, _ in rings), f"{name}: symmetrisch zur Mitte (Paare)")
    steps = [b - a for a, b in zip(seq, seq[1:])]
    want = 1.0 if out else -1.0
    good = sum(1 for s in steps if abs(s - want) < 1e-9)
    lo_d, hi_d = (0.0 if n % 2 else 0.5), (n - 1) / 2.0            # ungerade Zahl Geraete: in der Mitte eines allein
    wrap = sum(1 for s in steps if abs(s + want * (hi_d - lo_d)) < 1e-9)
    check(len(steps) >= 8 and good + wrap == len(steps) and good > wrap,
          f"{name}: Schritt fuer Schritt {'nach aussen' if out else 'zur Mitte'} ({[round(x, 1) for x in seq[:8]]})")
    check(seq and (min(seq) == lo_d and max(seq) == hi_d), f"{name}: alle Paare kommen dran")

for btn in ("nach aussen", "nach innen"):
    rig, sh = build(seed=3)
    clk = Clock(sh)
    clk.run(3)
    sh.command({"mix": btn})
    dims = []
    clk.run(4, lambda t: dims.append(rig["effektband"].values["dimmer"]))
    check(max(dims) == 0, f"{btn}: Effektband aus")

_, s_mid, _, _ = ring_log("nach aussen", speed="mid")
_, s_fast, _, _ = ring_log("nach aussen", speed="fast")
check(len(s_fast) > 1.6 * len(s_mid), f"Speed Hot: schneller ({len(s_fast)} statt {len(s_mid)} Schritte)")
finish("test_chase_inout")
