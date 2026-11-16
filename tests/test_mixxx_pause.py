"""Pausiert Mixxx ('kein Deck hoerbar'), geht das Licht sofort in den Ruhemodus. Kommt aber weiter Musik am
Audio-Eingang an (andere Quelle am Pult), uebernimmt die Audio-Erkennung mit Beat und BPM."""
import numpy as np
from _common import audio, Rig, sw, check, finish, PI
from mixxx_link import MixxxLink
import os

SR, HOP = 44100, 512


def music(n0, n):
    t = (np.arange(n0, n0 + n)) / SR
    beat = 60 / 128.0
    ph = t % beat
    return (0.8 * np.sin(2 * np.pi * (50 + 90 * np.exp(-ph * 40)) * ph) * np.exp(-ph * 12)
            + 0.25 * np.sin(2 * np.pi * 55 * t)).astype(np.float32)


def deck(now, play):
    return {"d": 1, "q": 1, "pl": 1 if play else 0, "tl": 1, "du": 240.0, "fb": 128, "bp": 128, "rr": 1.0,
            "pp": (now - 1000.0) / 240.0, "bd": (now * 128 / 60) % 1, "sy": 0, "vo": 1.0, "or": 1, "vu": 0.5,
            "k": 4, "fk": 4, "cf": 0.0}


def scenario(setting, pause_at=40.0, noise_db=-48, other_music=False, probe=None):
    an = audio.Analyzer(None, SR, HOP)
    rig = Rig(os.path.join(PI, "fixtures.yaml"))
    rig["vega"].extra["limits_verified"] = True
    ln = MixxxLink(port=19998)
    sh = sw.Show(rig, an, aim_file=os.devnull, settings_file=None, scenes_file=None, mixxx=ln, texts_file=None)
    sh.cfg.v["mixxx_pause_idle"] = setting
    n, t0, seq, last, nu, ml = 0, 1000.0, [], None, 1000.0, 1000.0
    for b in range(int(60 * SR / HOP)):
        now = t0 + b * HOP / SR
        playing = (now - t0) < pause_at
        blk = music(n, HOP) if (playing or other_music) else (np.random.default_rng(b).normal(size=HOP) * 10 ** (noise_db / 20)).astype(np.float32)
        n += HOP
        an.process(blk)
        while ml <= now:
            ln.feed(deck(ml, playing), ml)
            ml += 0.1
        while nu <= now:
            sh.update(nu)
            if probe is not None:
                probe.append((round(nu - t0, 2), sh.state, sh._bpm_live(), sh.beat_t))
            if sh.state != last:
                seq.append((round(nu - t0, 2), sh.state))
                last = sh.state
            nu += 0.025
    return [x for x in seq if x[0] >= pause_at - 2]


seq = scenario(1.0)
check(seq and seq[0][1] == "idle" and abs(seq[0][0] - 40.0) < 0.2 and not [x for x in seq if x[1] == "drop"],
      f"Mixxx pausiert: sofort Ruhemodus, kein Drop  {seq}")
seq = scenario(0.0)
check(not [x for x in seq if x[1] == "drop"], f"Schalter aus: nur Audio entscheidet, trotzdem kein Drop  {seq}")

# Mixxx pausiert, aber am Pult laeuft andere Musik weiter: Audio-Erkennung uebernimmt
probe = []
seq = scenario(1.0, other_music=True, probe=probe)
after = [p for p in probe if p[0] >= 45.0]
check(after and all(p[1] != "idle" for p in after), f"andere Musik nach der Pause: kein Ruhemodus mehr ab 5 s danach  {seq}")
try:
    import aubio  # noqa: F401
    check(after and all(p[2] > 0 for p in after), f"BPM-Anzeige laeuft ({after[0][2] if after else '-'} BPM)")
except ImportError:
    print("  (BPM-Pruefung uebersprungen: aubio fehlt hier, am Pi ist es installiert)")
beats = {p[3] for p in after if p[3] is not None}
check(len(beats) > 10, f"Beat-Lamperl blinkt weiter ({len(beats)} Beats in 15 s)")
check(not [x for x in seq if x[1] == "drop"], "kein Drop durch die Umschaltung")
finish("test_mixxx_pause")
