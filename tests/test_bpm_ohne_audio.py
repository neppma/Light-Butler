"""BPM-Anzeige und Lamperl ohne Ton am Eingang (Wunsch von Markus, 08.11.2026, Variante A): spielt ein Deck von Mixxx oder vom
Auto-DJ hoerbar, zeigt das Panel dessen Tempo, auch wenn am Line-In/LAN nichts ankommt. Das Licht bleibt im Ruhemodus, die
Weitergabe an Ableton Link bleibt wie bisher."""
import os

import numpy as np
from _common import PI, Rig, audio, check, finish, sw
from mixxx_link import MixxxLink

SR, HOP = 44100, 512


def deck(now, play):
    return {"d": 1, "q": 1, "pl": 1 if play else 0, "tl": 1, "du": 240.0, "fb": 128, "bp": 128, "rr": 1.0,
            "pp": (now - 1000.0) / 240.0, "bd": (now * 128 / 60) % 1, "sy": 0, "vo": 1.0, "or": 1, "vu": 0.5, "k": 4, "fk": 4, "cf": 0.0}


def run(play, secs=20.0, autodj=False):
    an = audio.Analyzer(None, SR, HOP)
    rig = Rig(os.path.join(PI, "fixtures.yaml"))
    rig["vega"].extra["limits_verified"] = True
    ln = MixxxLink(port=19997)
    sh = sw.Show(rig, an, aim_file=os.devnull, settings_file=None, scenes_file=None, mixxx=ln, texts_file=None)
    t0, ml, nu, n = 1000.0, 1000.0, 1000.0, 0
    out = []
    for b in range(int(secs * SR / HOP)):
        now = t0 + b * HOP / SR
        an.process((np.random.default_rng(b).normal(size=HOP) * 10 ** (-70 / 20)).astype(np.float32))   # Eingang still
        n += HOP
        while ml <= now:
            if autodj:
                ln.feed_autodj([dict(deck(ml, play), d=11)], ml)
            else:
                ln.feed(deck(ml, play), ml)
            ml += 0.1
        while nu <= now:
            sh.update(nu)
            out.append((nu - t0, sh.state, sh._bpm_show(), sh._bpm_live(), sh.beat_t))
            nu += 0.025
    return sh, out


sh, out = run(True)
late = [x for x in out if x[0] > 10.0]
check(all(x[1] == "idle" for x in late), "Eingang still: das Licht bleibt im Ruhemodus")
check(all(abs(x[2] - 128.0) < 0.5 for x in late), "Anzeige: BPM aus Mixxx, obwohl am Eingang nichts ankommt")
check(all(x[3] == 0.0 for x in late), "Ableton Link und Licht: unveraendert (dort weiter 0 bei Stille)")
beats = {round(x[4], 2) for x in late if x[4] is not None}
check(len(beats) >= 15, f"Lamperl: Beats aus Mixxx kommen weiter ({len(beats)} in 10 s)")
snap = sh.snapshot()
check(round(snap["beat_bpm"]) == 128 and snap["beat_ago"] is not None, "ans Panel: beat_bpm und beat_ago")

sh2, out2 = run(False)
check(all(x[2] == 0.0 for x in out2 if x[0] > 10.0), "Mixxx pausiert und Eingang still: Anzeige -- wie bisher")

sh3, out3 = run(True, autodj=True)
check(all(abs(x[2] - 128.0) < 0.5 for x in out3 if x[0] > 10.0), "Auto-DJ genauso")
finish("test_bpm_ohne_audio")
