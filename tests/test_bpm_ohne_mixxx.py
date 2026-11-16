"""Tempo ohne Mixxx und essentia (Probelauf ohne Mixxx, 14.11.2026): key_estimate.numpy_bpm misst das Tempo selbst.
An 60 zufaelligen Liedern der Sammlung: 75 % auf 2 % wie Mixxx, 83 % mit halbem/doppeltem Tempo."""
import json
import os
import sys
import tempfile

import numpy as np

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import key_estimate as ke  # noqa: E402

SR = 22050


def beat(bpm, secs=60, swing=False):
    t = np.arange(int(SR * secs)) / SR
    period = 60.0 / bpm
    ph = np.mod(t, period)
    kick = np.sin(2 * np.pi * 55 * t) * np.exp(-ph * 25)
    hat = 0.2 * np.random.RandomState(1).randn(len(t)) * np.exp(-np.mod(t + period / 2, period) * 60)
    return (0.8 * kick + hat + 0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


for b in (90.0, 124.0, 128.0, 140.0, 174.0):
    m = ke.numpy_bpm(beat(b))
    ok = abs(m - b) / b <= 0.02 or abs(m * 2 - b) / b <= 0.02 or abs(m / 2 - b) / b <= 0.02
    check(ok, f"{b} BPM gemessen als {m}")
check(ke.numpy_bpm(beat(124.0)) == ke.numpy_bpm(beat(124.0)), "gleiche Musik, gleiches Ergebnis")
check(ke.numpy_bpm(np.zeros(SR * 60, np.float32)) == 0.0, "Stille: kein Tempo")
check(ke.numpy_bpm(beat(124.0, secs=10)) == 0.0, "zu kurz: kein Tempo")

# frueher ohne essentia gemerkte "none" werden neu gemessen
E = ke.KeyEstimator(base=os.path.join(tmp, "daten", "tonart"))
os.makedirs(os.path.dirname(E.path), exist_ok=True)
with open(E.path, "w", encoding="utf-8") as f:
    f.write(json.dumps({"path": "/m/a.mp3", "v": 2, "kid": 3, "src": "numpy", "bpm": 0.0, "bsrc": "none"}) + "\n")
    f.write(json.dumps({"path": "/m/b.mp3", "v": 2, "kid": 3, "src": "numpy", "bpm": 126.0, "bsrc": "numpy"}) + "\n")
E.refresh()
check("/m/a.mp3" not in E.bpms and E.bpm("/m/b.mp3") == (126.0, 1), "alte Eintraege ohne Messung zaehlen nicht, neue gelten")
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "key_estimate.py"), encoding="utf-8").read()
check('bsrc="numpy" if b else UNSURE' in src, "ohne essentia: eigene Messung statt keiner")
finish("test_bpm_ohne_mixxx")
