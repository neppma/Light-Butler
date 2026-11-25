"""Tempo erst wenn sicher (Wunsch von Markus 23.11.2026): in einer Einleitung ohne Beat (Klatschen, leise Trompete) meldet
aubio schon ein Tempo (120-130), das Licht wurde unruhig. Show._bpm_gate laesst das Tempo erst durch, wenn die
Schlag-Klarheit (beat_clarity.py) bpm_sure_s lang ueber bpm_clear lag und das Tempo gleich blieb. Ohne Messung
(Simulator): gleiches Tempo plus Kicks, ohne Kicks das Dreifache. Bis dahin BPM 0 (der Kick fuehrt, Anzeige --)."""
import numpy as np
from _common import build, check, finish  # noqa: I001  (_common setzt den Pfad zu pi/)
from audio import Features  # noqa: E402

rig, sh = build()
check(sh.cfg["bpm_sure_s"] == 2.0 and sh.cfg["bpm_clear"] == 0.25, "Standard 2 s, Klarheit 0,25")
sh.cfg.set("bpm_clear", 0.35)                    # die Faelle unten rechnen mit 0,35
sh.cfg.set("bpm_sure_s", 4.0)                    # 1) bis 7): Simulator ohne Klarheits-Messung, mit 4 s


def feat(bpm, kicks=0, silent=False):
    return Features(0.6, 0.6, 0.4, 0.3, bpm, 0.5, -12.0, -12.0, silent, 0, kicks, 0.0, 0.0)


def run(sh, t0, secs, bpm_of, kick_every=None, silent=False):
    """Bilder zu 25 ms durch _bpm_gate; gibt (Zeit, durchgelassenes BPM) zurueck."""
    out, kicks = [], getattr(sh, "_tk", 0)
    for i in range(int(secs * 40)):
        t = t0 + i * 0.025
        if kick_every and i % kick_every == 0:
            kicks += 1
        out.append((t - t0, sh._bpm_gate(feat(bpm_of(i), kicks, silent), t).bpm, sh.bpm_unsure))
    sh._tk = kicks
    return out


# 1) Intro ohne Kick, aubio springt zwischen 130 und 115: nie sicher
o = run(sh, 1000.0, 20, lambda i: 115.0 if (i // 40) % 2 else 130.0)
check(all(b == 0.0 and u for _, b, u in o), "springendes Tempo ohne Kick: 20 s lang kein Tempo")

# 2) Beat setzt ein: gleiches Tempo mit Kicks, nach 4 s gilt es
o = run(sh, 1020.0, 8, lambda i: 128.0, kick_every=19)
first = next(t for t, b, _ in o if b > 0)
check(3.9 <= first <= 4.1 and o[-1][1] == 128.0, "mit Kicks nach 4 s sicher (%.2f s)" % first)

# 3) kleine Schwankung und halb/doppelt erkannt bleiben sicher
o = run(sh, 1028.0, 6, lambda i: [128.0, 129.5, 64.0, 127.0][(i // 30) % 4], kick_every=19)
check(all(b > 0 and not u for _, b, u in o), "Schwankung unter 3 % und Oktavsprung: bleibt sicher")

# 4) neues Tempo (Liedwechsel): wieder warten
o = run(sh, 1034.0, 6, lambda i: 100.0, kick_every=24)
first = next(t for t, b, _ in o if b > 0)
check(3.9 <= first <= 4.1, "anderes Tempo: wieder 4 s warten (%.2f s)" % first)

# 5) Stille: danach neu pruefen
run(sh, 1040.0, 2, lambda i: 100.0, silent=True)
o = run(sh, 1042.0, 1, lambda i: 100.0, kick_every=24)
check(all(b == 0.0 for _, b, _ in o), "nach Stille: wieder unsicher")

# 6) gleichmaessiges Tempo ohne Kick (Lied ohne Bass-Kick): erst nach 12 s
rig, sh = build()
sh.cfg.set("bpm_sure_s", 4.0)
o = run(sh, 2000.0, 14, lambda i: 90.0)
first = next(t for t, b, _ in o if b > 0)
check(11.9 <= first <= 12.1, "ohne Kicks erst nach 3 x 4 s (%.2f s)" % first)

# 7) aus (0), Tempo von Hand: unveraendert
rig, sh = build()
sh.cfg.set("bpm_sure_s", 0.0)
o = run(sh, 3000.0, 2, lambda i: 130.0 if i % 2 else 125.0)
check(all(b > 0 and not u for _, b, u in o), "Einstellung 0: Tempo wie frueher")
rig, sh = build()
sh.manual_bpm = 120.0
o = run(sh, 3000.0, 2, lambda i: 130.0 if i % 2 else 125.0)
check(all(b > 0 for _, b, _ in o), "Tempo von Hand: keine Pruefung")

# 8) in der Show: am Anfang BPM-Anzeige 0, Schlaege zaehlen nicht, danach normal
rig, sh = build()
sh.cfg.set("bpm_sure_s", 2.0)
t, steps = 5000.0, []
for i in range(40 * 10):
    sh.update(t + i * 0.025)
    if i == 40 * 1:
        check(sh.bpm == 0.0 and sh.bpm_unsure, "Show nach 1 s: noch kein Tempo")
check(sh.bpm > 0 and not sh.bpm_unsure, "Show nach 10 s: Tempo da (%.1f)" % sh.bpm)

# 9) mit Klarheits-Messung: eine Minute Einleitung mit gleichbleibendem Tempo und Kicks (Klatschen), aber ohne klaren Schlag
rig, sh = build()
sh.cfg.set("bpm_sure_s", 2.0)
sh.src.beat_clarity = 0.1
o = run(sh, 6000.0, 60, lambda i: 126.0, kick_every=17)
check(all(b == 0.0 for _, b, _ in o), "Einleitung ohne klaren Schlag: 60 s kein Tempo, auch mit Kicks und gleichem Tempo")
sh.src.beat_clarity = 0.6                         # der Beat setzt ein
o = run(sh, 6060.0, 4, lambda i: 128.0, kick_every=19)
first = next(t for t, b, _ in o if b > 0)
check(0.4 <= first <= 1.0, "Beat setzt ein, Tempo war schon gleich: sobald die Klarheit im Mittel der 2 s reicht (%.2f s)" % first)
sh.src.beat_clarity = 0.05                        # Break im Lied: Tempo bleibt
o = run(sh, 6064.0, 20, lambda i: 128.0)
check(all(b > 0 for _, b, _ in o), "Break ohne Schlag, gleiches Tempo: Tempo bleibt")
sh.src.beat_clarity = 0.6                         # kurz klar, dann nicht: Zaehlung beginnt neu
run(sh, 6084.0, 1, lambda i: 100.0, silent=True)
seq = [0.6] * 40 + [0.2] * 10 + [0.6] * 200
out = []
for i, cl in enumerate(seq):
    sh.src.beat_clarity = cl
    out.append(sh._bpm_gate(feat(100.0, 0), 6085.0 + i * 0.025).bpm)
first = next(i for i, b in enumerate(out) if b > 0) * 0.025
check(1.9 <= first <= 2.1, "Klarheit kurz weg (0,25 s): zaehlt im Mittel, kein Neustart (%.2f s)" % first)


# 10) die Messung selbst (Analyzer) mit kuenstlichem Ton
from audio import Analyzer  # noqa: E402

R = 44100
rng = np.random.default_rng(1)


def tone(kind, secs=14.0):
    t = np.arange(int(secs * R)) / R
    x = np.zeros_like(t)

    def hit(at, dur, f=None, amp=1.0):
        i, m = int(at * R), int(dur * R)
        seg = np.arange(m) / R
        sig = (np.sin(2 * np.pi * f * seg) if f else rng.normal(0, 1, m)) * np.exp(-seg / (dur / 4)) * amp
        x[i:i + m] += sig[:len(x) - i]
    if "kick" in kind:
        for b in np.arange(0, secs - 1, 60 / 128):
            hit(b, 0.2, 55)
    if "hihat" in kind:
        for b in np.arange(0, secs - 1, 60 / 256):
            hit(b, 0.05, None, 0.3)
    if "applaus" in kind:
        for a in np.sort(rng.uniform(0, secs - 1, int(secs * 40))):
            hit(a, 0.03, None, 0.2)
    if "trompete" in kind:
        f0 = 466 * (1 + 0.005 * np.sin(2 * np.pi * 5 * t))
        x += 0.3 * np.sin(2 * np.pi * np.cumsum(f0) / R) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.25 * t))
    return x.astype(np.float32)


def clarity_of(x):
    an = Analyzer(rate=R)
    vals = []
    for i in range(0, len(x) - 512, 512):
        an.process(x[i:i + 512])
        vals.append(an.beat_clarity)
    return np.array(vals[int(5.0 * R / 512):])     # nach dem ersten vollen Messfenster


for kind, lo, hi in (("kick", 0.45, 1.0), ("hihat", 0.45, 1.0), ("applaus", 0.0, 0.2), ("applaus+trompete", 0.0, 0.2)):
    v = clarity_of(tone(kind))
    check(lo <= np.median(v) <= hi, "Klarheit %s: Mitte %.2f (erwartet %.2f bis %.2f)" % (kind, np.median(v), lo, hi))
v = clarity_of(np.zeros(int(8 * R), np.float32))
check(float(v.max()) == 0.0, "Stille: Klarheit 0")
finish("test_tempo_sicher")
