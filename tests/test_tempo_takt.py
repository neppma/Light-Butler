"""tempo_np mit audio.Analyzer: Taktart (4/4, 3/4) aus betonten Schlaegen. Der Ersatz meldet den Schlag puenktlich,
die Betonung wird deshalb danach gemessen (METER_AFTER_S), nicht im Fenster davor wie bei aubio."""
import numpy as np

from _common import check, finish

import audio
from tempo_np import NumpyTempo

RATE, HOP = 44100, 512


def track(bpm, secs, beats_per_bar, seed=2):
    rng = np.random.default_rng(seed)
    n = int(secs * RATE)
    x = 0.01 * rng.standard_normal(n).astype(np.float32)
    period, t, k = 60.0 / bpm, 0.2, 0
    while t < secs:
        i = int(t * RATE)
        L = min(n - i, int(0.15 * RATE))
        tt = np.arange(L) / RATE
        amp = 0.9 if k % beats_per_bar == 0 else 0.45                       # erster Schlag des Takts betont
        x[i:i + L] += amp * np.sin(2 * np.pi * 60 * tt) * np.exp(-tt * 25)
        j = int((t + 0.6 * period) * RATE)                                  # Off-Beat (Snare/Hi-Hat) zwischen den Schlaegen,
        if j < n:                                                           # immer gleich laut: wie in echter Musik
            Lj = min(n - j, int(0.08 * RATE))
            tj = np.arange(Lj) / RATE
            noise = np.diff(rng.standard_normal(Lj + 1)).astype(np.float32)   # ohne Bass, wie Snare/Hi-Hat
            x[j:j + Lj] += (0.35 * noise + 0.6 * np.sin(2 * np.pi * 200 * tj)) * np.exp(-tj * 40)
        t += period
        k += 1
    return x


def analyse(x, bpm):
    a = audio.Analyzer(rate=RATE, hop=HOP)
    a.tempo = NumpyTempo(a.win, HOP, RATE)                                  # wie unter Windows ohne aubio
    a.tempo.set_silence(-50)
    beats = []
    for b in range(len(x) // HOP):
        n0 = a.beat_count
        a.process(x[b * HOP:(b + 1) * HOP])
        if a.beat_count > n0:
            beats.append((b + 1) * HOP / RATE)
    period = 60.0 / bpm
    off = [(t - 0.2) % period for t in beats if t > 15]
    a.lage_ms = 1000 * float(np.median([min(o, period - o) for o in off])) if off else 1e9
    return a


a4 = analyse(track(124, 40, 4), 124)
check(abs(a4.bpm - 124) < 1.5, "Tempo im Analyzer: %.1f" % a4.bpm)
check(a4.lage_ms < 60, "4/4: Schlaege auf der Bassdrum, nicht auf dem Off-Beat (%.0f ms)" % a4.lage_ms)
check(a4.meter_est.meter == 4, "betonter 4/4-Takt erkannt (%s, Sicherheit %.2f)" % (a4.meter_est.meter, a4.meter_est.conf))
a3 = analyse(track(120, 40, 3), 120)
check(a3.lage_ms < 60, "3/4: Schlaege auf der Bassdrum, nicht auf dem Off-Beat (%.0f ms)" % a3.lage_ms)
check(a3.meter_est.meter == 3, "betonter 3/4-Takt erkannt (%s, Sicherheit %.2f)" % (a3.meter_est.meter, a3.meter_est.conf))

finish("test_tempo_takt")
