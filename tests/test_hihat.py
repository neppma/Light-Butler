"""Hi-Hat-Funkeln: Die Audio-Analyse zaehlt kurze Spitzen in den Hoehen (Hi-Hat, Shaker, Clap, Snare, hat_count).
In AUTO pulsieren Derby, 21 Eyes und Vega weich darauf mit (hoechstens 60 % heller, hat_amount, je ein Schalter), wahlweise
ein zufaelliges Nanoleaf-Panel. Das Barlicht (Arbeitslicht an der Bar) pulsiert nie.
Blitzgrenze: ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde, mit ihr hoechstens 8. Aus = Licht wie bisher."""
import numpy as np

from _common import build, check, finish, Clock

import audio

RATE, HOP, BPM = 44100, 512, 124.0


def detect(hats=False, clap=False, sec=20):
    an = audio.Analyzer(rate=RATE, hop=HOP, win=1024)
    rng = np.random.default_rng(1)
    for s0 in range(0, RATE * sec, HOP):
        n = np.arange(s0, s0 + HOP) / RATE
        beat = n * BPM / 60.0
        bt = (beat % 1.0) * 60.0 / BPM
        x = 0.6 * np.sin(2 * np.pi * 55 * bt) * np.exp(-bt * 18) + 0.2 * np.sin(2 * np.pi * 220 * n) + 0.1 * np.sin(2 * np.pi * 330 * n)
        if hats:
            x += 0.25 * rng.standard_normal(HOP) * np.exp(-((beat + 0.5) % 1.0) * 60.0 / BPM * 60)
        if clap:
            x += 0.4 * rng.standard_normal(HOP) * np.exp(-((beat - 1) % 2.0) * 60.0 / BPM * 25)
        an.process(x.astype(np.float32))
    return an.hat_count, an.poll().hat_count


played = int(20 * BPM / 60)
h0, p0 = detect()
check(h0 <= 2, f"nur Bassdrum und Flaeche: (fast) keine Hi-Hats ({h0})")
h1, p1 = detect(hats=True)
check(abs(h1 - played) <= 3 and p1 == h1, f"Hi-Hats auf den Achteln erkannt ({h1} von {played})")
h2, _ = detect(clap=True)
check(abs(h2 - played // 2) <= 3, f"Clap auf 2 und 4 erkannt ({h2} von {played // 2})")
check(audio.Features(*range(16)).hat_count == 0, "alte Aufrufe ohne Hi-Hat-Zaehler: 0")

# ---- Licht: weicher Puls mit Blitzgrenze ---------------------------------------------------------------------------


class Src:
    """Simulator-Musik, Hi-Hats nach Wunsch (hz pro Sekunde)."""

    def __init__(self, hz):
        self.sim, self.hz, self.t0 = audio.Simulator(), hz, None

    def poll(self, now=None):
        f = self.sim.poll(now)
        self.t0 = now if self.t0 is None else self.t0
        return f._replace(hat_count=int((now - self.t0) * self.hz))


def pulses(strobe, hz=16.0, amount=0.5, sec=4.0, start=22.0, **cmd):
    rig, sh = build(strobe=strobe, source=Src(hz))
    sh.cfg.set("hat_amount", amount)
    clk = Clock(sh)
    clk.run(start)                                         # Simulator: ab 16 s Groove
    for k, v in cmd.items():
        sh.command({k: v})
    times = []
    last = sh.hat_t

    def look(t):
        nonlocal last
        if sh.hat_t != last:
            times.append(t)
            last = sh.hat_t
    clk.run(sec, look)
    return times, rig, sh


t_no, _, _ = pulses(False)
check(t_no and len(t_no) <= 4 * 2 + 1 and min(b - a for a, b in zip(t_no, t_no[1:])) >= 0.5 - 1e-6,
      f"ohne Strobe-Erlaubnis: hoechstens 2 Pulse pro Sekunde ({len(t_no)} in 4 s)")
t_st, _, _ = pulses(True)
check(len(t_st) <= 4 * 8 + 1 and min(b - a for a, b in zip(t_st, t_st[1:])) >= 0.125 - 1e-6 and len(t_st) > len(t_no),
      f"mit Strobe-Erlaubnis: hoechstens 8 pro Sekunde ({len(t_st)} in 4 s)")
t_off, _, _ = pulses(True, amount=0.0)
check(not t_off, "Hi-Hat-Funkeln 0: kein Puls")
t_bo, _, _ = pulses(True, blackout=True)
check(not t_bo, "Blackout: kein Puls")

rig, sh = build()
c = sh.cfg
check(c["hat_amount"] == 0.5 and c["hat_derby"] == c["hat_eyes"] == c["hat_vega"] == 1.0 and c["hat_nano"] == 0.0,
      "Standard: halbe Staerke, Derby, Eyes und Vega an, Nanoleaf aus")
sh.hat_env = 1.0
derby, eyes, vega, par = rig["derby"], rig["eyes"], rig["vega"], rig["par"]
check(abs(sh._hat_puls(derby) - 0.30 * sh.dim) < 1e-9 and sh._hat_puls(eyes) == sh._hat_puls(vega) == sh._hat_puls(derby),
      "Derby, Eyes, Vega: Puls 30 % bei 0,5")
check(sh._hat_puls(par) == 0.0 and all(sh._hat_puls(f) == 0.0 for f in rig.fixtures if f.group in ("bar", "bars", "wash", "uv")),
      "Barlicht (Arbeitslicht) und alle anderen: nie")
c.set("hat_amount", 1.0)
check(abs(sh._hat_puls(vega) - 0.60 * sh.dim) < 1e-9, "volle Staerke: 60 %, weicher Puls")
c.set("hat_eyes", 0)
check(sh._hat_puls(eyes) == 0.0 and sh._hat_puls(derby) > 0, "Schalter je Geraet")

# im laufenden Licht: Barlicht bleibt gleich, Eyes und Derby leuchten auf den Hi-Hats (Stufe ruhig: sonst dunkel)
def run(amount):
    rig, sh = build(strobe=True, source=Src(16.0))
    sh.cfg.set("hat_amount", amount)
    clk = Clock(sh)
    clk.run(22)
    sh.auto_speed = "slow"                                   # ruhige Stufe: Eyes/Derby sonst dunkel
    clk.run(1.5)                                             # vorherige Stufe ausklingen lassen
    bar, fx = [], []
    ey = rig["eyes"]
    clk.run(4, lambda t: (bar.append(rig.render()[220:228]), fx.append(max(ey.values[k] for k in ("led_r", "led_g", "led_b")))))
    return bar, fx
bar1, fx1 = run(1.0)
bar0, fx0 = run(0.0)
check(bar1 == bar0, "Barlicht: Bild fuer Bild gleich, ob mit oder ohne Funkeln")
check(max(fx1) > 0 and max(fx0) == 0, f"21 Eyes: dunkel ohne, leuchtet mit Funkeln ({max(fx1)})")
finish("test_hihat")
