"""Tempo fein nachmessen (Eichstueck 23.11.2026): aubio meldete am Pi 121,7 statt 120 und 96 statt 95 (rastet auf die
Blockgroesse ein). beat_clarity rechnet das Tempo aus den Abstaenden der Anschlaege genauer, Show._bpm_refine nimmt es,
wenn es hoechstens 4 % neben aubio liegt (auch halb/doppelt)."""
import numpy as np

from _common import build, check, finish
import eichstueck as E  # noqa: E402
from audio import Analyzer, Features  # noqa: E402

# 1) feines Tempo im Eichstueck
x = E.build()
an = Analyzer(rate=E.RATE)
got = {}
for i in range(0, len(x) - 512, 512):
    an.process(x[i:i + 512])
    t = i / E.RATE
    for a, b, k in ((45, 65, "beat120"), (105, 125, "drop"), (145, 165, "weich95"), (20, 35, "melodie")):
        if a <= t < b:
            got.setdefault(k, []).append(an.bpm_fine)
med = {k: float(np.median(v)) for k, v in got.items()}
check(abs(med["beat120"] - 120) < 0.3 and abs(med["drop"] - 120) < 0.3, "Beat 120: fein %.2f / %.2f" % (med["beat120"], med["drop"]))
check(abs(med["weich95"] - 95) < 0.3, "weicher Beat 95: fein %.2f" % med["weich95"])
share = float(np.mean(np.array(got["melodie"]) > 0))
check(share < 0.5, "ohne Beat: meist kein feines Tempo (%.0f %% der Zeit eines)" % (share * 100))


# 2) Show: aubio 121,7 -> fein 120; zu weit weg oder aus: aubio bleibt
def feat(bpm):
    return Features(0.6, 0.6, 0.4, 0.3, bpm, 0.5, -12.0, -12.0, False, 0, 0, 0.0, 0.0)


rig, sh = build()
check(sh.cfg["bpm_fine"] == 1.0, "Standard an")
sh.src.bpm_fine = 120.0
check(abs(sh._bpm_refine(feat(121.7)).bpm - 120.0) < 1e-9, "aubio 121,7, fein 120: 120")
check(abs(sh._bpm_refine(feat(60.9)).bpm - 60.0) < 1e-9, "aubio halb (60,9): 60, aubios Oktave bleibt")
check(abs(sh._bpm_refine(feat(243.0)).bpm - 240.0) < 1e-9, "aubio doppelt: 240")
check(sh._bpm_refine(feat(130.0)).bpm == 130.0, "zu weit weg (8 %): aubio bleibt")
sh.src.bpm_fine = 0.0
check(sh._bpm_refine(feat(121.7)).bpm == 121.7, "kein feines Tempo: aubio bleibt")
sh.src.bpm_fine = 120.0
sh.cfg.set("bpm_fine", 0.0)
check(sh._bpm_refine(feat(121.7)).bpm == 121.7, "Einstellung aus: aubio bleibt")
sh.cfg.set("bpm_fine", 1.0)
sh.manual_bpm = 125.0
check(sh._bpm_refine(feat(121.7)).bpm == 121.7, "Tempo von Hand: nicht anfassen")
finish("test_tempo_fein")
