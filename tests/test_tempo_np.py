"""tempo_np: Tempo und Schlaege ohne aubio (Windows-Ersatz). Kuenstliche Musik: Kick, Hi-Hat, etwas Rauschen."""
import math

import numpy as np

from _common import check, finish

from tempo_np import NumpyTempo

RATE, HOP = 44100, 512


def track(bpm, secs, seed=1, start=0.0):
    rng = np.random.default_rng(seed)
    n = int(secs * RATE)
    x = 0.02 * rng.standard_normal(n).astype(np.float32)
    period = 60.0 / bpm
    t = start
    k = 0
    while t < secs:
        i = int(t * RATE)
        L = min(n - i, int(0.12 * RATE))
        tt = np.arange(L) / RATE
        x[i:i + L] += 0.8 * np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 30)          # Kick
        h = int(t * RATE + period / 2 * RATE)                                       # Hi-Hat dazwischen
        if h < n:
            Lh = min(n - h, int(0.03 * RATE))
            x[h:h + Lh] += 0.2 * rng.standard_normal(Lh) * np.exp(-np.arange(Lh) / RATE * 150)
        t += period
        k += 1
    return x


def run(x, tp=None):
    tp = tp or NumpyTempo(1024, HOP, RATE)
    tp.set_silence(-50)
    beats = []
    for b in range(len(x) // HOP):
        if tp(x[b * HOP:(b + 1) * HOP])[0]:
            beats.append(b * HOP / RATE)
    return tp, beats


for bpm in (100.0, 124.0, 128.0, 140.0, 174.0 / 2 * 2 if False else 150.0):
    tp, beats = run(track(bpm, 20))
    ok = abs(tp.get_bpm() - bpm) <= 1.5
    late = [b for b in beats if b > 10]
    gaps = np.diff(late) if len(late) > 2 else np.array([0])
    check(ok, "Tempo %.0f BPM erkannt: %.1f" % (bpm, tp.get_bpm()))
    check(len(late) > 2 and abs(float(np.median(gaps)) - 60.0 / bpm) < 0.02, "Schlaege im Abstand des Tempos (%.0f BPM)" % bpm)

# Schlaege liegen auf den Kicks (Phase), hoechstens ~1 Block daneben
bpm = 128.0
tp, beats = run(track(bpm, 20, start=0.3))
period = 60.0 / bpm
err = [min(abs((b - 0.3) % period), period - abs((b - 0.3) % period)) for b in beats if b > 10]
check(err and float(np.median(err)) < 0.04, "Schlaege auf den Kicks (Abweichung %.0f ms)" % (1000 * float(np.median(err)) if err else -1))

# Stille: keine Schlaege, danach Tempo neu
x = np.concatenate([track(120, 12), np.zeros(5 * RATE, np.float32)])
tp, beats = run(x)
check(not [b for b in beats if b > 12.5], "Stille: keine Schlaege")
check(tp.get_bpm() == 0.0, "nach 3 s Stille wird das Tempo neu gesucht")

# Nur Rauschen: kein festes Tempo, kaum Schlaege
rng = np.random.default_rng(3)
tp, beats = run((0.1 * rng.standard_normal(15 * RATE)).astype(np.float32))
check(len(beats) < 15, "Rauschen ohne Takt: kaum Schlaege (%d)" % len(beats))

# Schnittstelle wie aubio
check(isinstance(NumpyTempo().get_bpm(), float) and len(NumpyTempo()(np.zeros(HOP, np.float32))) == 1, "Schnittstelle wie aubio.tempo")
check(not math.isnan(tp.get_bpm()), "kein NaN")
finish("test_tempo_np")
