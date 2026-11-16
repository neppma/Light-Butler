"""Musik stoppt abrupt (verschiedene Rauschpegel): kein Drop, Ruhemodus, Wiederbeginn ohne falschen Drop.
Benutzt die echte Audio-Analyse mit einem kuenstlichen 4/4-Signal bei 128 BPM."""
import numpy as np
from _common import audio, Rig, sw, check, finish, PI
import os

SR, HOP = 44100, 512


def music(n0, n):
    t = (np.arange(n0, n0 + n)) / SR
    beat = 60 / 128.0
    ph = t % beat
    x = 0.8 * np.sin(2 * np.pi * (50 + 90 * np.exp(-ph * 40)) * ph) * np.exp(-ph * 12) + 0.25 * np.sin(2 * np.pi * 55 * t)
    hp = (t + beat / 2) % beat
    x += 0.08 * np.random.default_rng(n0).normal(size=n) * np.exp(-hp * 60)
    return x.astype(np.float32)


def scenario(noise_db, before=40.0, after=25.0, resume_at=None, quiet=None):
    an = audio.Analyzer(None, SR, HOP)
    rig = Rig(os.path.join(PI, "fixtures.yaml"))
    rig["vega"].extra["limits_verified"] = True
    sh = sw.Show(rig, an, aim_file=os.devnull, settings_file=None, scenes_file=None, texts_file=None)
    nb, sb = int((before + after) * SR / HOP), int(before * SR / HOP)
    rb = None if resume_at is None else int(resume_at * SR / HOP)
    n, t0, seq, last, nu = 0, 1000.0, [], None, 1000.0
    for b in range(nb):
        now = t0 + b * HOP / SR
        if b < sb or (rb is not None and b >= rb):
            blk = music(n, HOP)
        elif quiet is not None:
            blk = music(n, HOP) * quiet                             # leiser Teil: Musik geht weiter, nur leiser
        elif noise_db > -120:
            blk = (np.random.default_rng(b).normal(size=HOP) * 10 ** (noise_db / 20)).astype(np.float32)
        else:
            blk = np.zeros(HOP, np.float32)
        n += HOP
        an.process(blk)
        while nu <= now:
            sh.update(nu)
            if sh.state != last:
                seq.append((round(nu - t0, 1), sh.state))
                last = sh.state
            nu += 0.025
    return [x for x in seq if x[0] >= before - 2], sh.snapshot()


for nd in (-200, -72, -58, -52, -48, -44, -40):
    seq, snap = scenario(nd)
    drops = [x for x in seq if x[1] == "drop"]
    check(not drops and snap["state"] == "idle", f"Stopp, Rauschen {nd} dB: kein Drop, am Ende Ruhemodus  {seq}")
for nd, ra in ((-48, 70.0), (-72, 70.0)):
    seq, snap = scenario(nd, resume_at=ra, after=40.0)
    check(not [x for x in seq if x[1] in ("drop", "build") and x[0] > ra - 1] and snap["state"] == "normal",
          f"Pause, Rauschen {nd} dB, Musik wieder ab {ra:.0f} s: kein Drop oder Aufbau beim Wiedereinsetzen")
# Fehlerbericht 15.11.2026: mit aubio (Pi, Windows) kamen im Rauschen weiter Beats, der Ruhemodus kam nie (oben -48..-40 dB).
# Beats bei relativer Stille zaehlen darum nicht mehr; ein leiser Teil (20 dB leiser, unter rel_silence_db) bleibt Musik.
seq, snap = scenario(-200, quiet=0.1)
check(snap["state"] != "idle" and not [x for x in seq if x[1] == "idle"], f"leiser Teil 20 dB unter der Musik: kein Ruhemodus  {seq}")
finish("test_stop_silence")
