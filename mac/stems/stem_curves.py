#!/usr/bin/env python3
"""
stem_curves.py - aus den getrennten Spuren eines Liedes werden fuenf Pegelkurven. Nur numpy, damit die Tests ohne Demucs laufen.

Kurven: stimme, bass, kick, hihat, sonstiges. kick und hihat kommen aus dem Schlagzeug: Dort steckt fast alle Energie in der
Bassdrum, in einer einzigen Kurve gingen Snare und Hi-Hat unter.

Je Zeitschritt zaehlt der Spitzenwert in dB, damit kurze Schlaege nicht verloren gehen und leise Stellen sichtbar bleiben.
Gespeichert als ein Byte je Wert: 0 = DB_MIN oder leiser, 255 = 0 dB.
"""
import base64

import numpy as np

RATE = 100                # Werte pro Sekunde
DB_MIN = -60.0
NAMES = ("stimme", "bass", "kick", "hihat", "sonstiges")
KICK_HZ = (120.0, 200.0)  # darunter voll, darueber nichts, dazwischen weich: harte Kanten klingen zeitlich nach
HAT_HZ = (300.0, 600.0)   # darueber voll, darunter nichts
PEAK_RATE = 50            # Raster von peaks.json (Browser)
MAX_LAG_MS = 250          # groesser ist kein Kodierversatz mehr, sondern eine andere Datei
LAG_STEP_MS = 2
MIN_CORR = 0.7            # darunter ist der Vergleich nichts wert


def mono(x):
    x = np.asarray(x, dtype=np.float32)
    return x if x.ndim == 1 else x.mean(axis=1)


def bands(x, sr):
    """Teilt ein Monosignal in tief und hoch, mit weichen Kanten."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / sr)

    def ramp(a, b):
        u = np.clip((f - a) / (b - a), 0.0, 1.0)
        return 0.5 - 0.5 * np.cos(np.pi * u)

    lo = np.fft.irfft(spec * (1.0 - ramp(*KICK_HZ)), len(x))
    hi = np.fft.irfft(spec * ramp(*HAT_HZ), len(x))
    return lo.astype(np.float32), hi.astype(np.float32)


def block_peaks(x, block, start=0):
    """Spitzenwert je Block. x: Betrag, Mono."""
    x = x[start:] if start > 0 else x
    n = len(x) // block
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    return x[:n * block].reshape(n, block).max(axis=1)


def curve(x, sr):
    """Pegelkurve als Bytes. x: Signal, Mono oder mehrkanalig (es zaehlt der lauteste Kanal)."""
    x = np.asarray(x, dtype=np.float32)
    a = np.abs(x) if x.ndim == 1 else np.abs(x).max(axis=1)
    p = block_peaks(a, int(round(sr / RATE)))
    db = 20.0 * np.log10(np.maximum(p, 1e-9))
    v = np.clip((db - DB_MIN) / -DB_MIN, 0.0, 1.0) * 255.0
    return np.rint(v).astype(np.uint8)


def to_db(values):
    """Umkehrung fuer Auswertungen: Bytes in dB."""
    return DB_MIN + np.asarray(values, dtype=np.float32) / 255.0 * -DB_MIN


def measure_lag(summe, sr, peaks):
    """Wie viele ms liegen die getrennten Spuren hinter der Wellenform, die der Browser aus der MP3 gerechnet hat?
    Die Show zaehlt in Browser-Zeit, sie ist also der Massstab. Ergebnis (ms, Korrelation); (0, Wert) wenn nichts passt."""
    if not peaks or int(peaks.get("rate", 0)) != PEAK_RATE or not peaks.get("max"):
        return 0.0, None
    mx = np.abs(np.asarray(peaks["max"], dtype=np.float32))
    mn = np.abs(np.asarray(peaks.get("min") or peaks["max"], dtype=np.float32))
    n = min(len(mx), len(mn))
    ref = np.maximum(mx[:n], mn[:n]) / 127.0
    a = np.abs(mono(summe))
    block = int(round(sr / PEAK_RATE))
    best, best_c = 0, -2.0
    for ms in range(-MAX_LAG_MS, MAX_LAG_MS + 1, LAG_STEP_MS):
        s = int(round(abs(ms) * sr / 1000.0))
        # Positiv: Spuren spaeter, ihr Anfang faellt weg. Negativ: Spuren frueher, sie bekommen vorne Stille.
        p = block_peaks(a, block, s) if ms >= 0 else block_peaks(np.concatenate([np.zeros(s, dtype=a.dtype), a]), block)
        m = min(len(p), len(ref))
        if m < PEAK_RATE * 2:
            continue
        c = float(np.corrcoef(p[:m], ref[:m])[0, 1])
        if np.isfinite(c) and c > best_c:
            best, best_c = ms, c
    if best_c < MIN_CORR:
        return 0.0, best_c
    return float(best), best_c


def shift(x, lag_ms, sr):
    """Verschiebt ein Signal um lag_ms nach vorn (negativ: nach hinten). Die Laenge bleibt gleich."""
    s = int(round(abs(lag_ms) * sr / 1000.0))
    if s == 0:
        return x
    x = np.asarray(x)
    pad = np.zeros((s,) + x.shape[1:], dtype=x.dtype)
    return np.concatenate([x[s:], pad]) if lag_ms > 0 else np.concatenate([pad, x[:-s]])


def analyse(stems, sr, peaks=None):
    """stems: {vocals, bass, drums, other} wie von Demucs. Ergebnis: Daten fuer stems.json, ohne Fingerabdruck."""
    n = min(len(v) for v in stems.values())
    stems = {k: np.asarray(v[:n], dtype=np.float32) for k, v in stems.items()}
    lag, corr = measure_lag(sum(stems.values()), sr, peaks)
    stems = {k: shift(v, lag, sr) for k, v in stems.items()}
    kick, hat = bands(mono(stems["drums"]), sr)
    raw = {"stimme": stems["vocals"], "bass": stems["bass"], "kick": kick, "hihat": hat, "sonstiges": stems["other"]}
    return {"v": 1, "rate": RATE, "db_min": DB_MIN, "duration": round(n / float(sr), 3), "offset_ms": lag,
            "corr": None if corr is None else round(corr, 3),
            "curves": {k: pack(curve(raw[k], sr)) for k in NAMES}}


def pack(values):
    return base64.b64encode(np.asarray(values, dtype=np.uint8).tobytes()).decode("ascii")


def unpack(text):
    return np.frombuffer(base64.b64decode(text), dtype=np.uint8)
