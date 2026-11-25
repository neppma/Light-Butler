"""Eichlauf ohne Hardware (23.11.2026): das Eichstueck (eichstueck.py) durch die ganze Kette, Analyse, Show und /api/takt,
wie die Seite /eichen es am echten Licht-Rechner misst. Haelt fest, was die Erkennung schon kann; wird sie besser, die
Grenzen hier anheben. Am Mac/Windows ohne aubio mit dem Ersatz tempo_np (am Pi aubio: Werte koennen etwas abweichen)."""

from _common import build, check, finish
import eichstueck as E  # noqa: E402
from audio import Analyzer  # noqa: E402


def run(**cfg):
    x = E.build()
    an = Analyzer(rate=E.RATE)
    rig, sh = build(source=an)
    for k, v in cfg.items():
        sh.cfg.set(k, v)
    t0, pos, out = 1795500000.0, 0, []
    for i in range(int(E.DURATION / 0.025)):
        end = int((i + 1) * 0.025 * E.RATE)
        while pos + 512 <= end:
            an.process(x[pos:pos + 512])
            pos += 512
        sh.update(t0 + i * 0.025)
        if i % 10 == 0:
            out.append((i * 0.025, sh.takt(t0 + i * 0.025)))
    return out


def score(samples):
    res = {}
    for a, b, key, _, want in E.SECTIONS:
        r = [d for t, d in samples if a + E.GRACE_S <= t < b]
        for k, w in want.items():
            if k == "einsatz":                    # muss in den ersten EINSATZ_S Sekunden beginnen
                res[(key, k)] = 100.0 if any(d["abschnitt"] == w for t, d in samples if a <= t <= a + E.EINSATZ_S) else 0.0
                continue
            ok = [(d["aktiv"] and abs(d["bpm"] - w) / w <= 0.03) if k == "bpm" else d[k] == w for d in r]
            res[(key, k)] = 100.0 * sum(ok) / max(1, len(ok))
    return res


S = run()
R = score(S)
MIN = {("stille1", "spielt"): 100, ("applaus", "spielt"): 95, ("applaus", "aktiv"): 95, ("melodie", "spielt"): 95,
       ("melodie", "aktiv"): 90, ("beat120", "bpm"): 75, ("drop", "bpm"): 90, ("stille2", "spielt"): 90,
       ("weich95", "bpm"): 60, ("stille3", "spielt"): 90}
for (key, k), lo in MIN.items():
    check(R[(key, k)] >= lo, "%s %s: %.0f %% richtig (mindestens %d)" % (key, k, R[(key, k)], lo))
check(R[("aufbau", "abschnitt")] >= 50, "Aufbau erkannt: %.0f %%" % R[("aufbau", "abschnitt")])
check(R[("break", "abschnitt")] >= 70, "Break erkannt: %.0f %% (phase_v2)" % R[("break", "abschnitt")])
check(R[("drop", "einsatz")] == 100, "Drop setzt nach dem Aufbau ein (phase_v2)")
# pegel/baender in /api/takt (Wunsch Bravia-Dashboard 23.11.2026): bezogen auf die lauten Teile, ohne Musik weggelassen
def med_of(a, b, key, band=None):
    v = [(d["baender"][band] if band else d[key]) for t, d in S if a <= t < b and key in d]
    return sorted(v)[len(v) // 2] if v else None


check(all("pegel" not in d for t, d in S if 1 <= t < 4.5 or 129 <= t < 134), "Stille: kein pegel")
check(med_of(100, 124, "pegel") > 0.75, "Drop: pegel nahe 1 (%.2f)" % med_of(100, 124, "pegel"))
check(med_of(72, 84, "pegel") < med_of(100, 124, "pegel") - 0.15, "Break leiser als Drop (%.2f)" % med_of(72, 84, "pegel"))
check(med_of(172.5, 174.8, "pegel") is not None and med_of(172.5, 174.8, "pegel") < 0.5, "Ausklingen am Ende gegen 0 (%.2f)" % (med_of(172.5, 174.8, "pegel") or -1))
check(all(0.0 <= d["baender"][k] <= 1.0 for t, d in S if "baender" in d for k in ("bass", "mitten", "hoehen")), "Baender 0..1")
check(med_of(100, 124, "baender", "bass") > med_of(72, 84, "baender", "bass") + 0.2, "Bass im Drop deutlich staerker als im Break")
drops_in_melody = [t for t, d in S if 18 <= t < 35 and d["abschnitt"] == "drop"]
check(not drops_in_melody, "kein Drop in der Melodie ohne Beat (phase_v2)")

# mit phase_v2 aus: wie frueher (Break nie erkannt), damit die Wirkung des Schalters belegt ist
R0 = score(run(phase_v2=0.0))
check(R0[("break", "abschnitt")] < 20, "phase_v2 aus: Break wie frueher nicht erkannt (%.0f %%)" % R0[("break", "abschnitt")])

# Simulator (kuenstliche Merkmale): Aufbau und Drop wie frueher, dazu der Break davor
import random  # noqa: E402

from _common import Clock  # noqa: E402

for pv in (0.0, 1.0):
    random.seed(3)
    rig, sh = build(strobe=True, seed=1, pilot=True)
    sh.cfg.set("phase_v2", pv)
    seq = []
    Clock(sh).run(80, lambda t: seq.append((round(t - 1000.0, 1), sh.state)) if not seq or seq[-1][1] != sh.state else None)
    first = {st: t for t, st in reversed(seq)}
    check(abs(first.get("build", -9) - 65.5) < 1.0 and abs(first.get("drop", -9) - 16.0) < 1.0
          and any(st == "drop" and 68 < t < 71 for t, st in seq), "Simulator phase_v2=%d: Aufbau und Drop wie frueher" % pv)
    if pv:
        check(any(st == "break" and 55 < t < 60 for t, st in seq), "Simulator phase_v2: Break vor dem Aufbau erkannt")
finish("test_eichlauf")
