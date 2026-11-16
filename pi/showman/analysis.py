#!/usr/bin/env python3
"""
analysis.py - Tempo und Beat-Raster einer MP3.

Der Browser dekodiert die Datei (der Pi braucht dafuer kein ffmpeg) und schickt die Huellkurve mit 100 Werten pro Sekunde.
Hier: Einsaetze (Anstiege der Huellkurve), Autokorrelation ueber 60..200 BPM, dann die Phase des Beat-Rasters.
"""
import numpy as np


def estimate_tempo(env, rate=100.0, lo=60.0, hi=200.0):
    """Liefert {bpm, offset, conf}: Tempo, Zeit des ersten Schlags in Sekunden, Sicherheit 0..1. Zu wenig Daten: bpm 0."""
    x = np.asarray(env, dtype=float)
    if x.size < rate * 4 or np.max(x) <= 0:
        return {"bpm": 0.0, "offset": 0.0, "conf": 0.0}
    onset = np.maximum(0.0, np.diff(x, prepend=x[0]))
    onset -= np.mean(onset)
    n = int(2 ** np.ceil(np.log2(onset.size * 2)))
    spec = np.fft.rfft(onset, n)
    ac = np.fft.irfft(spec * np.conj(spec))[:onset.size]
    if ac[0] <= 0:
        return {"bpm": 0.0, "offset": 0.0, "conf": 0.0}
    ac = ac / ac[0]
    lag_lo, lag_hi = int(rate * 60.0 / hi), int(rate * 60.0 / lo)
    lags = np.arange(lag_lo, min(lag_hi + 1, ac.size))
    # sanfte Vorliebe fuer die uebliche Tanzmusik um 125 BPM, sonst gewinnt oft das halbe oder doppelte Tempo
    bpms = 60.0 * rate / lags
    weight = np.exp(-0.5 * (np.log2(bpms / 125.0) / 0.9) ** 2)
    k = int(np.argmax(ac[lags] * weight))
    lag = float(lags[k])
    if 0 < k < lags.size - 1:                      # zwischen den Abtastwerten genauer treffen
        a, b, c = ac[lags[k - 1]], ac[lags[k]], ac[lags[k + 1]]
        d = a - 2 * b + c
        if d < 0:
            lag += 0.5 * (a - c) / d
    # Feinsuche: Auf die ganze Lied-Laenge faellt schon ein kleiner Tempofehler auf, das Raster wird dann unscharf.
    pos = np.maximum(0.0, onset)
    idx = np.arange(onset.size)
    best = (-1.0, lag, 0)
    for cand in np.linspace(lag - 0.5, lag + 0.5, 41):
        size = int(np.ceil(cand)) + 1
        hist = np.bincount((idx % cand).astype(int), weights=pos, minlength=size)
        j = int(np.argmax(hist))
        if hist[j] > best[0]:
            best = (float(hist[j]), float(cand), j)
    _, lag, first = best
    conf = float(ac[lags[k]])
    return {"bpm": round(60.0 * rate / lag, 2), "offset": round(first / rate, 3), "conf": round(max(0.0, min(1.0, conf)), 3)}
