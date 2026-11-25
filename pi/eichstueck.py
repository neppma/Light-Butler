"""
eichstueck.py - Eichstueck fuer die Erkennung (Wunsch von Markus 23.11.2026): ein kuenstliches Musikstueck, bei dem auf die
Sekunde feststeht, wo Stille ist, wo Musik ohne Beat und wo welcher Beat. Die Seite /eichen spielt es im Browser ab (der Ton
kommt ueber das Netz oder Line-In zum Light-Butler), liest dabei /api/takt und /api/state mit und legt alles neben die
Sollwerte (SECTIONS).

Nur numpy, fester Zufall: jedes Mal dieselbe Datei. Erzeugen:  python3 eichstueck.py [Ziel.wav|Ziel.mp3]
(MP3 ueber lame oder ffmpeg). Die fertige Datei liegt als static/eichstueck.mp3 im Programm. Nur Ton, aufs Licht wirkt nichts.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

RATE = 44100
VERSION = 3

# Abschnitte: von, bis (s), Schluessel, Name, Sollwerte. spielt = Musik laeuft, aktiv = ein Tempo ist bekannt,
# bpm = so viel (halb oder doppelt zaehlt extra), abschnitt = wie in /api/takt. None = egal.
# einsatz = dieser Abschnitt muss in den ersten EINSATZ_S Sekunden beginnen (ein Drop ist ein Einsatz, kein Dauerzustand;
# Fassung 3: vorher stand "Drop" fuer die ganzen 30 s, das kann und soll das Licht nicht).
SECTIONS = [
    (0, 5, "stille1", "Stille", {"spielt": False, "aktiv": False}),
    (5, 18, "applaus", "Applaus, kein Beat", {"spielt": True, "aktiv": False}),
    (18, 35, "melodie", "Melodie und Fläche, kein Beat", {"spielt": True, "aktiv": False}),
    (35, 65, "beat120", "Beat 120 BPM (Kick, Snare, Hi-Hat, Bass)", {"spielt": True, "aktiv": True, "bpm": 120}),
    (65, 85, "break", "Break: Fläche und Melodie, kein Schlagzeug", {"spielt": True, "abschnitt": "break"}),
    (85, 95, "aufbau", "Aufbau: Snare-Wirbel wird schneller, Rauschen steigt", {"spielt": True, "abschnitt": "aufbau"}),
    (95, 125, "drop", "Drop: voller Beat 120 BPM, laut", {"spielt": True, "aktiv": True, "bpm": 120, "einsatz": "drop"}),
    (125, 135, "stille2", "Stille", {"spielt": False, "aktiv": False}),
    (135, 165, "weich95", "Weicher Beat 95 BPM (nur leiser Kick, Bass, Fläche)", {"spielt": True, "aktiv": True, "bpm": 95}),
    (165, 175, "ausklang", "Ausklang: nur Fläche, kein Beat", {"spielt": True, "aktiv": False}),
    (175, 180, "stille3", "Stille", {"spielt": False, "aktiv": False}),
]
DURATION = SECTIONS[-1][1]
EINSATZ_S = 4.0       # so frueh muss ein Einsatz (einsatz) kommen
GRACE_S = 4.0          # so lange nach einem Wechsel zaehlt noch nicht als falsch (Erkennung braucht Zeit), extra gemessen


def sections():
    """Fuer die Seite: Liste von Dicts."""
    return [{"a": a, "b": b, "key": k, "name": n, "want": dict(w)} for a, b, k, n, w in SECTIONS]


# ---- Klaenge ---------------------------------------------------------------------------------------
def _env(n, att, dec):
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / max(att, 1e-4)) * np.exp(-t / dec)


def kick(amp=1.0, soft=False):
    n = int(0.35 * RATE)
    t = np.arange(n) / RATE
    f = 45 + (110 if not soft else 50) * np.exp(-t / 0.04)
    s = np.sin(2 * np.pi * np.cumsum(f) / RATE) * _env(n, 0.002, 0.12 if not soft else 0.18)
    if not soft:
        s[:200] += np.random.default_rng(1).normal(0, 0.3, 200) * np.linspace(1, 0, 200)   # Klick des Schlegels
    return amp * s


def snare(rng, amp=0.6):
    n = int(0.2 * RATE)
    noise = rng.normal(0, 1, n)
    noise = noise - np.concatenate(([0], noise[:-1])) * 0.6          # etwas heller
    t = np.arange(n) / RATE
    return amp * (0.7 * noise * _env(n, 0.001, 0.05) + 0.4 * np.sin(2 * np.pi * 190 * t) * _env(n, 0.001, 0.04))


def hat(rng, amp=0.25):
    n = int(0.05 * RATE)
    x = rng.normal(0, 1, n)
    x = np.diff(np.concatenate(([0], x)))                             # nur Hoehen
    return amp * x * _env(n, 0.0005, 0.012)


def clap(rng, amp):
    n = int(0.04 * RATE)
    x = rng.normal(0, 1, n)
    return amp * np.diff(np.concatenate(([0], x))) * _env(n, 0.0005, 0.008)


def tone(freq, dur, amp, kind="saw", vib=0.0, att=0.08, rel=0.15, rng=None):
    n = int(dur * RATE)
    t = np.arange(n) / RATE
    f = freq * (1 + vib * np.sin(2 * np.pi * (4.5 + (rng.uniform(-0.5, 0.5) if rng is not None else 0)) * t))
    ph = 2 * np.pi * np.cumsum(f) / RATE
    if kind == "saw":
        s = sum(np.sin(k * ph) / k for k in range(1, 9))
    else:
        s = np.sin(ph) + 0.3 * np.sin(2 * ph)
    e = np.minimum(1.0, t / att) * np.minimum(1.0, np.maximum(0.0, (dur - t) / rel))
    return amp * s * e


def mix(buf, at, sig):
    i = int(round(at * RATE))
    if i >= len(buf):
        return
    m = min(len(sig), len(buf) - i)
    buf[i:i + m] += sig[:m]


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12.0)


CHORDS = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]   # Am F C G


def pad(buf, a, b, amp, rng, bar_s=2.0):
    t = a
    i = 0
    while t < b - 0.01:
        d = min(bar_s, b - t)
        for nn in CHORDS[i % 4]:
            mix(buf, t, tone(midi(nn), d + 0.3, amp / 3, "sine", vib=0.002, att=0.4, rel=0.5, rng=rng))
        t += d
        i += 1


def melody(buf, a, b, amp, rng):
    """Legato wie eine leise Trompete, ohne Schlag: langsamer Einsatz, unregelmaessig lange Noten, die naechste beginnt,
    bevor die vorige ausklingt (Fassung 2: in Fassung 1 kamen die Einsaetze zu regelmaessig, Klarheit bis 0,44)."""
    scale = [69, 71, 72, 74, 76, 74, 72, 71]
    t = a
    j = 0
    while t < b - 0.5:
        d = float(rng.uniform(1.4, 3.8))
        d = min(d, b - t)
        mix(buf, t, tone(midi(scale[j % len(scale)]), d + 0.8, amp, "saw", vib=0.006, att=0.6, rel=0.9, rng=rng))
        t += d * float(rng.uniform(0.6, 0.9))
        j += int(rng.integers(1, 3))


def bass(buf, a, b, bpm, amp):
    beat = 60.0 / bpm
    t, i = a, 0
    while t < b - 0.01:
        root = CHORDS[(i // 8) % 4][0] - 24
        mix(buf, t, tone(midi(root), beat * 0.45, amp, "sine", att=0.005, rel=0.05))
        t += beat / 2
        i += 1


def drums(buf, a, b, bpm, rng, amp=1.0, full=True, soft=False):
    beat = 60.0 / bpm
    n = int(round((b - a) / beat))
    for k in range(n):
        t = a + k * beat
        mix(buf, t, kick(amp * (0.55 if soft else 1.0), soft=soft))
        if full:
            if k % 2 == 1:
                mix(buf, t, snare(rng, 0.5 * amp))
            mix(buf, t, hat(rng, 0.2 * amp))
            mix(buf, t + beat / 2, hat(rng, 0.14 * amp))


def build(seed=7):
    rng = np.random.default_rng(seed)
    buf = np.zeros(int(DURATION * RATE), np.float64)
    # Applaus 5-18 s (laeuft bis 20 s aus), dann Melodie und Flaeche ohne Beat
    for at in np.sort(rng.uniform(5.0, 20.0, 1200)):
        fade = 1.0 if at < 15 else max(0.0, (20 - at) / 5)
        mix(buf, at, clap(rng, 0.12 * fade * float(rng.uniform(0.5, 1.0))))
    pad(buf, 18, 35, 0.10, rng, bar_s=3.1)                 # Akkordwechsel nicht im Takt eines spaeteren Tempos
    melody(buf, 20, 35, 0.05, rng)
    # Beat 120
    drums(buf, 35, 65, 120, rng, 0.8)
    bass(buf, 35, 65, 120, 0.25)
    pad(buf, 35, 65, 0.06, rng)
    # Break
    pad(buf, 65, 85, 0.10, rng, bar_s=4.0)
    melody(buf, 67, 85, 0.05, rng)
    # Aufbau: Snare 1/4 -> 1/8 -> 1/16, Rauschen steigt
    beat = 0.5
    t = 85.0
    while t < 95.0 - 1e-6:
        p = (t - 85.0) / 10.0
        step = beat if p < 0.4 else beat / 2 if p < 0.75 else beat / 4
        mix(buf, t, snare(rng, 0.25 + 0.45 * p))
        t += step
    n = int(10 * RATE)
    riser = rng.normal(0, 1, n) * np.linspace(0.0, 0.18, n)
    riser = np.diff(np.concatenate(([0], riser)))
    mix(buf, 85, riser)
    pad(buf, 85, 95, 0.08, rng)
    # Drop
    drums(buf, 95, 125, 120, rng, 1.0)
    bass(buf, 95, 125, 120, 0.32)
    pad(buf, 95, 125, 0.08, rng)
    # Stille 125-135, weicher Beat 95
    drums(buf, 135, 165, 95, rng, 0.8, full=False, soft=True)
    bass(buf, 135, 165, 95, 0.18)
    pad(buf, 135, 165, 0.07, rng)
    # Ausklang ohne Beat
    pad(buf, 165, 174, 0.09, rng, bar_s=3.0)
    i = int(172 * RATE)
    buf[i:int(175 * RATE)] *= np.linspace(1, 0, int(175 * RATE) - i)
    for a, b, k, _, _ in SECTIONS:                       # Stille wirklich still
        if k.startswith("stille"):
            buf[int(a * RATE):int(b * RATE)] = 0.0
    peak = float(np.max(np.abs(buf))) or 1.0
    return (buf / peak * 0.89).astype(np.float32)


def write_wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def write_mp3(path, x):
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "e.wav")
        write_wav(wav, x)
        if shutil.which("lame"):
            cmd = ["lame", "--quiet", "-b", "160", "--tt", "Light-Butler Eichstueck", "--ta", "Light-Butler", wav, path]
        elif shutil.which("ffmpeg"):
            cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-b:a", "160k", "-metadata", "title=Light-Butler Eichstueck", path]
        else:
            raise RuntimeError("lame oder ffmpeg fehlt")
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "eichstueck.mp3")
    x = build()
    (write_mp3 if out.endswith(".mp3") else write_wav)(out, x)
    print(f"{out}: {DURATION} s, {len(SECTIONS)} Abschnitte")
