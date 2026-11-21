"""Pixel-Matrix, Liedtext (21.11.2026): gesungene Zeile als Laufschrift oder Wort fuer Wort, nur im Refrain oder immer."""
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import DT, build, check, finish  # noqa: E402

import settings                                  # noqa: E402
import wled_matrix as wm                         # noqa: E402
from showman import lyrics                       # noqa: E402

L = [(10.0, "I'm a little teapot short and stout"), (14.0, "Here is my handle"), (18.0, "Oh!"),
     (20.0, "We will, we will rock you"), (24.0, "Oh!"), (26.0, "Und dann der Vers"), (30.0, "we will we will ROCK you"),
     (34.0, "oh"), (36.0, "")]
rep = lyrics.repeats(L)
check(rep == {2, 3, 4, 6, 7} and 5 not in rep, "Refrain: mehrmals vorkommende Zeilen, kurze Rufe nur neben dem Refrain: %s" % sorted(rep))
check(lyrics.repeats([]) == set(), "leer: kein Refrain")

d = {x.key: x for x in settings.DEFS}
check(d["pm_lyrics"].default == 0.0 and d["pm_lyrics"].hi == 4.0, "Standard aus, fuenf Stufen")

S = {"t": 0.0, "dt": DT, "hue": 0.3, "cmode": "hue", "strobe": False}
base = np.ones((32, 32, 3)) * 0.5


def run_line(mode, lyr, secs, strobe=False, allowed=True):
    ov = wm.LyricOverlay()
    out = []
    for i in range(int(secs / DT)):
        x = dict(lyr, pos=lyr["t0"] + i * DT) if lyr else None
        out.append(ov.render(base.copy(), x, dict(S, strobe=strobe), mode, allowed))
    return out, ov


ch = {"text": "We will, we will rock you", "t0": 20.0, "t1": 24.0, "pos": 20.0, "chorus": True}
vs = dict(ch, text="Und dann der Vers", chorus=False)
fr, ov = run_line(1, ch, 4.0)
check(fr[-1].max() > 0.9 and fr[-1].mean() < 0.3, "Refrain, Laufschrift: Schrift hell, Effekt gedaempft")
cols = [np.where(f.max(axis=2) > 0.9)[1] for f in fr[10::30]]
lefts = [c.min() if len(c) else 99 for c in cols]
check(lefts[0] > lefts[2] or lefts[-1] < 30, "Laufschrift laeuft nach links: %s" % lefts)
fr, _ = run_line(1, vs, 2.0)
check(fr[-1].max() <= 0.51, "Refrain-Modus: Vers bleibt ohne Text")
fr, _ = run_line(3, vs, 2.0)
check(fr[-1].max() > 0.9, "immer: auch der Vers")
fr, _ = run_line(0, ch, 2.0)
check(np.array_equal(fr[-1], base), "aus: Bild unveraendert")
fr, _ = run_line(1, ch, 2.0, allowed=False)
check(np.array_equal(fr[-1], base), "nicht erlaubt (Stille, BLACKOUT, Testbild): kein Text")

# Wort fuer Wort: ohne Strobe-Erlaubnis hoechstens 2 neue Gruppen pro Sekunde
fast = {"text": "eins zwei drei vier fuenf sechs sieben acht neun zehn", "t0": 0.0, "t1": 2.5, "pos": 0.0, "chorus": True}
_, ov = run_line(2, fast, 0.2)
starts = [c[0] for c in ov.chunks]
check(all(b - a >= 0.5 - 1e-6 for a, b in zip(starts, starts[1:])), "Wort fuer Wort ohne Strobe: Gruppen >= 0,5 s: %s" % starts)
check(all(m.shape[1] <= 32 and m.shape[0] <= 32 for _, m, _ in ov.chunks), "Gruppen passen auf die Matrix")
_, ov = run_line(2, fast, 0.2, strobe=True)
check(len(ov.chunks) >= len(starts), "mit Strobe-Erlaubnis feiner")
slow = {"text": "Ich bin dein", "t0": 0.0, "t1": 3.0, "pos": 0.0, "chorus": True}
fr, ov = run_line(2, slow, 3.0)
check(len(ov.chunks) == 3, "langsam: jedes Wort einzeln")
sig = [f.max(axis=2).sum() for f in fr[5::20]]
check(len(set(np.round(sig, 1))) >= 3, "die Woerter wechseln")
fr, ov = run_line(1, ch, 2.0)
after = ov.render(base.copy(), None, S, 1, True)
check(after.max() > 0.6, "Ende der Zeile: Text blendet weich aus")
for _ in range(40):
    after = ov.render(base.copy(), None, S, 1, True)
check(np.allclose(after, base, atol=0.02), "danach wieder nur der Effekt")

# Show: gesungene Zeile mit Refrain-Kennzeichen
rig, sh = build(seed=3)
sh.cfg.set("pm_lyrics", 1)
calls = []


def src(now):
    calls.append(now)
    return {"src": "mixxx", "name": "X", "lines": L, "plain": "", "pos": now - 1000.0 + 21.0}
sh._lyric_source = src
x = sh._matrix_lyric(1000.0)
check(x["text"] == "We will, we will rock you" and x["chorus"] and x["t1"] == 24.0, "Show: Zeile, Ende, Refrain")
for i in range(1, 9):
    y = sh._matrix_lyric(1000.0 + i * DT)
check(len(calls) == 1 and abs(y["pos"] - (21.0 + 8 * DT)) < 1e-6, "Quelle hoechstens alle 0,25 s, Stelle laeuft weiter")
x = sh._matrix_lyric(1000.0 + 6.0)
check(x["text"] == "Und dann der Vers" and not x["chorus"], "Vers: kein Refrain")
sh._lyric_source = lambda now: None
check(sh._matrix_lyric(1100.0) is None, "ohne Liedtext: nichts")
got = []
sh.matrix = types.SimpleNamespace(tick=lambda s_, cfg: got.append(s_))
sh._lyric_source = src
sh.update(2000.0)
check(got and "lyric" in got[-1], "Matrix bekommt den Liedtext")
sh.cfg.set("pm_lyrics", 0)
sh.update(2000.025)
check("lyric" not in got[-1], "aus: kein Liedtext abgefragt")

# Matrix: ganzer Weg
cfg = settings.Settings(os.devnull)
cfg.set("pm_lyrics", 1)
cfg.set("pm_pics", 0)
cfg.set("pm_text", 0)
mt = wm.Matrix(None, dry=True)
mt.preview_until = 1e9
for i in range(60):
    mt.tick({"t": i * DT, "dt": DT, "bpm": 120, "state": "normal", "tier": 1, "hue": 0.3, "master": 1, "master_raw": 1, "loud": 1,
             "lyric": dict(ch, pos=21.0 + i * DT)}, cfg)
check((mt.last.max(axis=2) > 100).sum() > 20, "Matrix zeigt die Zeile")
finish("test_matrix_liedtext")
