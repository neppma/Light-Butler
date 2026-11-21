"""Pixel-Matrix, neue Effekte (21.11.2026): Schlange, Raster, Scanner, Explosion, Kaleidoskop, Glitch; Blitzgrenze; Gamma."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import DT, check, finish  # noqa: E402

import settings                                  # noqa: E402
import wled_matrix as wm                         # noqa: E402

NEW = ["schlange", "raster", "scanner", "explosion", "kaleido", "glitch"]
check(all(p in wm.PATTERNS for p in NEW) and wm.PATTERNS.index("test") == 6, "neue Muster hinten, Testbild bleibt Nummer 6")
check(len(wm.PATTERN_LABELS.split("|")) == len(wm.PATTERNS), "jedes Muster hat einen Namen")
d = {x.key: x for x in settings.DEFS}
check(d["pm_pattern"].hi == len(wm.PATTERNS) - 1 and d["pm_pattern"].unit.count("|") == len(wm.PATTERNS) - 1, "Einstellung kennt alle Muster")


def run(pat, secs, strobe=False, state="normal", bpm=128.0, every_frame=False):
    fx = wm.MatrixFx(32, 32, seed=3)
    spb = 60.0 / bpm
    frames, t, nb = [], 0.0, 0.0
    for i in range(int(secs / DT)):
        beat = t >= nb
        if beat:
            nb += spb
        trig = beat or every_frame
        s = {"t": t, "dt": DT, "bpm": bpm, "beat": trig, "kick": trig, "hat": True, "level": 0.6, "bass": 0.7, "mid": 0.5,
             "high": 0.4, "hue": 0.3, "cmode": "hue", "state": state, "tier": 3, "build_p": 0.5, "phrase": 0,
             "strobe": strobe, "pattern": pat}
        frames.append(fx.render(s).copy())
        t += DT
    return frames


def rises(frames, thr=0.2):
    """Wie oft das Bild als Ganzes heller springt (Blitz), je Sekunde."""
    m = np.array([f.max(axis=2).mean() for f in frames])
    up = np.diff(m) > thr * max(0.05, m.max())
    onsets = up[1:] & ~up[:-1]                                  # zusammenhaengende Anstiege zaehlen als ein Blitz
    return onsets.sum() / (len(frames) * DT)          # das erste Aufleuchten aus Schwarz zaehlt nicht


for pat in NEW:
    fr = run(pat, 20)
    check(all(f.shape == (32, 32, 3) and np.isfinite(f).all() and f.min() >= 0 and f.max() <= 1 for f in fr), pat + ": Bilder gueltig")
    check(max(f.max() for f in fr) > 0.5, pat + ": leuchtet")
    diff = np.mean([np.abs(a - b).mean() for a, b in zip(fr[::5], fr[5::5])])
    check(diff > 0.005, pat + ": bewegt sich (%.3f)" % diff)
    fast = run(pat, 15, every_frame=True)                     # Ausloeser in jedem Bild: Blitzgrenze muss halten
    check(rises(fast) <= 2.05, pat + ": ohne Strobe-Erlaubnis hoechstens 2 Blitze/s (%.2f)" % rises(fast))
    fs = run(pat, 15, strobe=True, every_frame=True)
    check(rises(fs) <= 8.05, pat + ": mit Strobe-Erlaubnis hoechstens 8/s (%.2f)" % rises(fs))

# dunkle Grundflaeche: Raster, Scanner, Explosion lassen den Grossteil fast schwarz
for pat in ("raster", "scanner", "explosion"):
    fr = run(pat, 10)
    dark = np.mean([(f.max(axis=2) < 0.1).mean() for f in fr[40:]])
    check(dark > 0.5, pat + ": meist dunkel, damit die Blitze wirken (%.0f %%)" % (dark * 100))

# Schlange: die Mitte des Tunnels wandert
fx = wm.MatrixFx(32, 32)
cent = []
for i in range(int(60 / DT)):
    f = fx.render({"t": i * DT, "dt": DT, "bpm": 120, "beat": i % 20 == 0, "pattern": "schlange", "hue": 0.2})
    v = f.max(axis=2)
    y, x = np.unravel_index(np.argmin(v + fx.R * 0.01), v.shape)   # dunkelster Punkt = fernes Ende
    cent.append((x, y))
xs = [c[0] for c in cent]
check(max(xs) - min(xs) >= 4, "Schlange: das ferne Ende wandert (%d Pixel)" % (max(xs) - min(xs)))

# Raster beim Drop (Auto): alle Kacheln
fx = wm.MatrixFx(32, 32)
f = fx.raster({"t": 1.0, "dt": DT, "beat": True, "hue": 0.1}, all_on=True)
check((f.max(axis=2) > 0.5).mean() > 0.5, "Raster: alle Kacheln auf einmal")

# Auto: Aufbau = Scanner, Drop = Explosion und Raster
fx = wm.MatrixFx(32, 32)
fx.render({"t": 0.0, "dt": DT, "bpm": 128, "pattern": "auto", "state": "build", "beat": True, "build_p": 0.5, "hue": 0.1})
check(len(fx.scans) == 1, "Auto im Aufbau: Scanner")
fx.render({"t": 1.0, "dt": DT, "bpm": 128, "pattern": "auto", "state": "drop", "beat": True, "hue": 0.1})
check(len(fx.parts) >= 80, "Auto beim Drop: grosse Explosion (%d Funken)" % len(fx.parts))

# Auto ohne Aufbau: im Wechsel der Phrasen kommt auch der Scanner
fx = wm.MatrixFx(32, 32)
seen = set()
for ph in range(7):
    fx.scans = []
    fx.last_trig = -1e9
    fx.render({"t": 100.0 + ph, "dt": DT, "bpm": 128, "pattern": "auto", "state": "normal", "tier": 3, "phrase": ph, "beat": True, "hue": 0.1})
    if fx.scans:
        seen.add(ph)
check(len(seen) == 1, "Auto, Stufe 3: Scanner in einer von sieben Phrasen")

# Gamma: dunkle Stellen an den LEDs dunkel wie in der Vorschau
g = np.zeros((1, 3, 3))
g[0, 0] = (0.1, 0.1, 0.1)
g[0, 1] = (0.5, 0.5, 0.5)
g[0, 2] = (1, 1, 1)
b = wm.to_bytes(g, 1.0, gamma=2.2)
check(b[0] <= 2 and 45 <= b[3] <= 60 and b[6] == 255, "Gamma 2,2: 10 %% -> %d, 50 %% -> %d, voll bleibt voll" % (b[0], b[3]))
check(wm.to_bytes(g, 1.0) == wm.to_bytes(g, 1.0, gamma=1.0) and wm.to_bytes(g, 1.0)[0] == 26, "Gamma 1,0: wie bisher")
check(d["pm_gamma"].default == 2.2 and d["pm_gamma"].lo == 1.0, "Standard Gamma 2,2")

# Huellkurve (21.11.2026): leise Stellen dunkler, laute ganz hell, schnell
cfg = settings.Settings(os.devnull)
check(d["pm_loud"].default == 0.7 and d["pm_loud_db"].default == 18.0, "Standard: Huellkurve 70 %, 18 dB")


def bright_after(loud, k=None, secs=1.0):
    c = settings.Settings(os.devnull)
    c.set("pm_pattern", 1)
    if k is not None:
        c.set("pm_loud", k)
    mt = wm.Matrix(None, dry=True)
    mt.preview_until = 1e9
    t = 0.0
    for i in range(int(secs / DT)):
        mt.tick({"t": t, "dt": DT, "bpm": 120, "state": "normal", "tier": 1, "hue": 0.3, "master": 0.8, "master_raw": 1.0,
                 "loud": loud}, c)
        t += DT
    return mt.last.mean(), mt
hi, _ = bright_after(1.0)
lo, _ = bright_after(0.0, secs=3.0)
check(lo < hi * 0.4, "leise Stelle viel dunkler (%.1f gegen %.1f)" % (lo, hi))
off, _ = bright_after(0.0, k=0.0)
check(abs(off - hi * 0.8) < hi * 0.05, "aus: wie bisher (Master mit loud_k)")
_, mt = bright_after(0.0)
c = settings.Settings(os.devnull)
c.set("pm_pattern", 1)
for i in range(4):                                # 0,1 s laut: fast ganz oben
    mt.tick({"t": 10 + i * DT, "dt": DT, "bpm": 120, "state": "normal", "tier": 1, "hue": 0.3, "master": 1, "master_raw": 1, "loud": 1.0}, c)
check(mt.env > 0.8, "laut: in 0,1 s oben (%.2f)" % mt.env)

# Show liefert die Lautstaerke
from _common import build                         # noqa: E402
rig, sh = build(seed=3)
got = []
sh.matrix = type("M", (), {"tick": lambda self_, s_, cfg_: got.append(s_)})()
for i in range(int(60 / DT)):
    sh.update(100 + i * DT)
check(got and all(0 <= x["loud"] <= 1 for x in got) and "master_raw" in got[-1], "Show: loud 0..1 und master_raw")
check(min(x["loud"] for x in got) < max(x["loud"] for x in got), "loud bewegt sich mit der Musik")
finish("test_matrix_effekte")
