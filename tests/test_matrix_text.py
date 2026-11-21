"""Pixel-Matrix: Laufschrift mit Interpret, Titel, Album (Wunsch von Markus 21.11.2026, alle vier Vorschlaege).
A eine grosse Zeile, B drei Zeilen, C Cover mit Laufband, D Wort fuer Wort im Takt. Eigene Pixelschrift mit Umlauten,
Tempo im Takt, Blitzgrenze bei D, Folge zusammen mit den Bildern zum Lied."""
import os
import time
import types

import numpy as np

from _common import DT, check, finish

import pixfont as pf                         # noqa: E402
import settings                              # noqa: E402
import wled_matrix as wm                     # noqa: E402
from showman.api import ShowManager          # noqa: E402

# ---- Schrift ---------------------------------------------------------------------------------------
for ch in "AZaz09ÄÖÜäöüß!?-.,'&()":
    check(ch in pf.GLYPHS and pf.GLYPHS[ch].shape[0] == 7, "Zeichen da: " + ch)
check(pf.width("i") < pf.width("m") and pf.width(" ") == 3, "Schrift proportional, Leerzeichen 3 breit")
check(np.array_equal(pf.glyph("é"), pf.glyph("e")) and np.array_equal(pf.glyph("–"), pf.glyph("-")), "Akzent und Gedankenstrich abgebildet")
check(np.array_equal(pf.glyph("漢"), pf.glyph("?")), "Unbekanntes als ?")
m, c = pf.render([("Ab", (1, 0, 0)), ("c", (0, 0, 1))], scale=2)
check(m.shape[0] == 14 and m.shape[1] == 2 * (pf.width("Ab") + 1 + pf.width("c")) and c.shape == m.shape + (3,), "doppelte Groesse, Farben je Teil")
check(tuple(c[m][0]) == (1, 0, 0) and tuple(c[:, -1][m[:, -1]][0]) == (0, 0, 1), "Farbe je Abschnitt")
f = np.zeros((32, 32, 3))
pf.blit(f, m, c, -5, 30)
pf.blit(f, m, c, 40, 0)
check(f[30:].any() and not f[:30].any(), "Rand: abgeschnitten statt Fehler")

S = {"t": 0, "dt": DT, "bpm": 120, "hue": 0.6, "level": 0.5}
INFO = {"artist": "Falco", "title": "Rock Me Amadeus", "album": "Falco 3"}
check(abs(wm.text_speed({"bpm": 120}, 5) - 10.0) < 1e-9 and wm.text_speed({"bpm": 0}, 5) > 9, "Tempo: Pixel je Beat")


def lit_x(frame):
    xs = np.where(frame.max(axis=2).max(axis=0) > 0.5)[0]
    return xs.mean() if len(xs) else None


# ---- A: eine Zeile ---------------------------------------------------------------------------------
a = wm.LineSlide(INFO, S, 32, 32, 5, 4.0)
check(a.mask.shape[0] == 14 and abs(a.dur - (a.mask.shape[1] + 32) / 10.0) < 1e-6, "A: 14 Pixel hoch, Dauer = einmal durch")
xs = [lit_x(a.render(t, S, np.zeros((32, 32, 3)))) for t in (0.5, 1.0, 1.5)]
check(xs[0] is not None and xs[0] > 20, "A: kommt von rechts")
rows = np.where(a.render(3.0, S, np.zeros((32, 32, 3))).max(axis=2).max(axis=1) > 0.5)[0]
check(rows.min() >= 8 and rows.max() <= 23, "A: in der Mitte")
check(a.render(a.dur, S, np.zeros((32, 32, 3))).max() < 0.5, "A: am Ende durchgelaufen")
base = np.ones((32, 32, 3)) * 0.5
check(abs(a.render(0.0, S, base)[0, 0, 0] - 0.1) < 1e-9, "A: Effekt dahinter gedaempft")

# ---- B: drei Zeilen ---------------------------------------------------------------------------------
b = wm.LinesSlide(INFO, S, 32, 32, 5, 4.0)
check(len(b.rows) == 3, "B: drei Zeilen")
f1, f2 = b.render(0.5, S, None), b.render(1.5, S, None)
top = slice(0, 10)
mid = slice(11, 21)
check(not np.array_equal(f1[top], f2[top]), "B: langer Titel laeuft")
check(np.array_equal(f1[mid], f2[mid]), "B: kurzer Interpret steht in der Mitte")
check(f1[mid].max() > 0.5 and f1[22:].max() > 0.5, "B: Interpret und Album sichtbar")
b2 = wm.LinesSlide({"artist": "X", "title": "Y", "album": ""}, S, 32, 32, 5, 4.0)
check(len(b2.rows) == 2 and b2.dur == 4.0, "B: ohne Album zwei Zeilen, kurz = Dauer je Bild")
check(tuple(b.rows[0][1][b.rows[0][0]][0]) == (1.0, 1.0, 1.0), "B: Titel weiss")

# ---- C: Cover mit Laufband ----------------------------------------------------------------------------
cov = np.ones((32, 32, 3)) * 0.4
cs = wm.BandSlide(INFO, S, 32, 32, 5, 4.0, cov)
fc = cs.render(1.0, S, None)
check(np.allclose(fc[:23], 0.4) and fc[23:].max() > 0.5 and (fc[23:] == 0).any(), "C: Cover oben, Band unten mit Schrift")
check(pf.width("Falco - Rock Me Amadeus · Falco 3") <= cs.mask.shape[1], "C: Interpret, Titel und Album im Band")
fc2 = wm.BandSlide(INFO, S, 32, 32, 5, 4.0, None).render(1.0, S, np.ones((32, 32, 3)))
check(abs(fc2[0, 0, 0] - 0.3) < 1e-9, "C: ohne Cover der Effekt gedaempft")

# ---- D: Wort fuer Wort im Takt -------------------------------------------------------------------------
d = wm.WordsSlide(INFO, S, 32, 32, 5, 4.0)
check(len(d.words) >= 5, "D: Woerter aus Titel und Interpret (%d)" % len(d.words))
check(all(m_.shape[1] <= 32 for m_, _ in d.words), "D: jedes Stueck passt in die Breite")
shown, t = [], 0.0
for i in range(int(4 / DT)):
    d.render(t, dict(S, beat=True), None)               # Beat in jedem Bild
    shown.append(d.i)
    t += DT
changes = [k for k in range(1, len(shown)) if shown[k] != shown[k - 1]]
worst = max(sum(1 for c_ in changes if k <= c_ < k + int(1 / DT)) for k in range(len(shown)))
check(worst <= 2, "D: ohne Strobe-Erlaubnis hoechstens 2 neue Woerter pro Sekunde (%d)" % worst)
d2 = wm.WordsSlide(INFO, S, 32, 32, 5, 4.0)
t, beats = 0.0, 0
for i in range(int(3 / DT)):
    bt = i % 20 == 0
    beats += bt
    d2.render(t, dict(S, beat=bt), None)
    t += DT
check(d2.i == beats - 1 or d2.i == min(beats - 1, len(d2.words)), "D: neues Wort nur auf dem Beat (%d Woerter, %d Beats)" % (d2.i + 1, beats))
d3 = wm.WordsSlide({"title": "Hi", "artist": ""}, S, 32, 32, 5, 4.0)
t = 0.0
while d3.left(t) > 0 and t < 10:
    d3.render(t, dict(S, beat=True), None)
    t += DT
check(t < 3, "D: endet nach dem letzten Wort")
d4 = wm.WordsSlide({"title": "Supercalifragilistic", "artist": ""}, S, 32, 32, 5, 4.0)
check(len(d4.words) >= 3 and all(m_.shape[1] <= 32 for m_, _ in d4.words), "D: langes Wort in Stuecke")

# ---- Folge mit Bildern ---------------------------------------------------------------------------------
RED, GRN = np.ones((32, 32, 3)) * (1, 0, 0), np.ones((32, 32, 3)) * (0, 1, 0)


def loaded(info, pics=(("titel", b"r"), ("interpret", b"g"))):
    pc = wm.Pictures(decode=lambda d_, w, h: {b"r": RED, b"g": GRN}.get(d_))
    pc.song(("", "x", 1, 32, 32), {"title": "x"}, (lambda song: list(pics)) if pics else None, 32, 32, 0,
            text_provider=lambda song: info)
    for _ in range(200):
        if pc.info or pc.pics:
            break
        time.sleep(0.01)
    return pc


pc = loaded(INFO)
check(pc.status.endswith("Text: Falco - Rock Me Amadeus"), "Zustand nennt den Text: " + pc.status)
check([type(x).__name__ for x in pc._build(S, 32, 32, 4.0, 1, 5)] == ["ImgSlide", "ImgSlide", "LineSlide"], "A: erst Bilder, dann Laufschrift")
check([type(x).__name__ for x in pc._build(S, 32, 32, 4.0, 3, 5)] == ["BandSlide", "ImgSlide"], "C: Cover mit Band statt Cover, dann Interpret")
check(pc._build(S, 32, 32, 4.0, 3, 5)[0].cover is RED, "C: das Cover des Liedes")
check([type(x).__name__ for x in pc._build(S, 32, 32, 4.0, 0, 5)] == ["ImgSlide", "ImgSlide"], "aus: nur Bilder")
pt = loaded(INFO, pics=())
check([type(x).__name__ for x in pt._build(S, 32, 32, 4.0, 2, 5)] == ["LinesSlide"], "ohne Bilder: nur die Laufschrift")
t, seen = 100.0, []
for i in range(int(40 / DT)):
    img, a_ = pt.play(t, dict(S, t=t), np.zeros((32, 32, 3)), 4.0, 0.0, True, 2, 5)
    seen.append(img is not None)
    t += DT
check(seen[0] and not seen[-1], "Laufschrift beginnt sofort, endet, kommt mit 0 nicht wieder")
pn = loaded({}, pics=())
check(pn.next_t is None and pn._build(S, 32, 32, 4.0, 1, 5) == [], "ohne Titel keine Laufschrift")

# Auto (21.11.2026): jede Folge eine andere der vier Arten, nie zweimal dieselbe hintereinander
pa = loaded(INFO)
pa.rng.seed(7)
kinds, t = [], 500.0
for i in range(int(400 / DT)):
    img, a_ = pa.play(t, dict(S, t=t), np.zeros((32, 32, 3)), 1.0, 0.5, True, wm.TEXT_AUTO, 8)
    if pa.seq_t == t:
        kinds.append(pa.last_mode)
    t += DT
check(len(kinds) >= 8 and all(a != b for a, b in zip(kinds, kinds[1:])) and set(kinds) == {1, 2, 3, 4},
      "Auto: wechselt, nie zweimal gleich, alle vier kommen: %s" % kinds[:12])
dmax = {x.key: x.hi for x in settings.DEFS}
check(dmax["pm_text"] == 5.0 and "Auto" in next(x.unit for x in settings.DEFS if x.key == "pm_text"), "Einstellung hat Auto")

# Matrix: Text-Lieferant nur, wenn die Laufschrift an ist
calls = []
cfg = settings.Settings(os.devnull)
dflt = {x.key: x.default for x in settings.DEFS}
check(dflt["pm_text"] == 1.0 and dflt["pm_text_px"] == 8.0, "Standard: A, 8 Pixel je Beat")
mt = wm.Matrix(None, dry=True)
mt.preview_until = 1e9
mt.pictures = lambda song: []
mt.song_text = lambda song: (calls.append(song), INFO)[1]
base_s = {"dt": DT, "bpm": 120, "state": "normal", "tier": 1, "hue": 0.5, "song": {"title": "Rock Me Amadeus", "dur": 200}}
mt.tick(dict(base_s, t=1.0), cfg)
for _ in range(100):
    if mt.pics.info:
        break
    time.sleep(0.01)
for i in range(60):
    mt.tick(dict(base_s, t=1.0 + i * DT), cfg)
check(len(calls) == 1 and mt.last.max() > 100, "Matrix zeigt die Laufschrift")
cfg.set("pm_text", 0)
cfg.set("pm_pics", 0)
mt2 = wm.Matrix(None, dry=True)
mt2.preview_until = 1e9
mt2.song_text = lambda song: (calls.append(song), INFO)[1]
mt2.tick(dict(base_s, t=1.0), cfg)
time.sleep(0.05)
check(len(calls) == 1, "Laufschrift und Bilder aus: nichts geholt")

# Showmanager: Interpret, Titel, Album
lib = [{"path": "/m/a.mp3", "title": "Rock Me Amadeus", "artist": "Falco", "album": "Falco 3", "dur": 200}]
fk = types.SimpleNamespace(show=types.SimpleNamespace(mixxx=types.SimpleNamespace(library_full=lambda: lib)),
                           _lib_path=lambda t_, d_: "/m/a.mp3" if t_ == "Rock Me Amadeus" else "",
                           store=types.SimpleNamespace(load=lambda n: {"mixxx": {"title": "Rock Me Amadeus", "dur": 200}}))
check(ShowManager.matrix_song_text(fk, {"title": "Rock Me Amadeus", "dur": 200}) == INFO, "Bibliothek: Interpret, Titel, Album")
check(ShowManager.matrix_song_text(fk, {"radio": {"artist": "A", "title": "B"}}) == {"artist": "A", "title": "B", "album": ""}, "Internetradio")
check(ShowManager.matrix_song_text(fk, {"show": "meine"}) == INFO, "Show: ueber ihr Mixxx-Lied")
check(ShowManager.matrix_song_text(fk, {"title": "Unbekannt"}) == {"artist": "", "title": "Unbekannt", "album": ""}, "unbekannt: nur der Titel")
finish("test_matrix_text")
