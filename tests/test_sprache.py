"""Sprache erkennen (Fehlerbericht 25.11.2026: ein Sprecher am Line-In, jede Wortpause wurde zum Drop, das Licht spielte
verrueckt). Sprache = lange kein regelmaessiger Schlag (Schlag-Klarheit), aber viele Anschlaege, die die Stimme in der
Kick-Erkennung ausloest. Dann keine Drops, kein Aufbau, keine Pause, kein Break (speech_guard, Standard an).
Kuenstliche Rede (Stimme mit Obertoenen, Formanten, Silben, Wort- und Satzpausen) durch die ganze Kette; am Mac mit der
Stimme von "say" nachgemessen (keine Drops statt alle 3 s einer). Das Eichstueck bleibt gleich (test_eichlauf)."""
import numpy as np

from _common import build, check, finish
import eichstueck as E  # noqa: E402
from audio import Analyzer  # noqa: E402

RATE = 44100
def synth_speech(sec, rate=44100, seed=3):
    """Kuenstliche Rede: Stimme (Grundton 110-160 Hz mit Obertoenen, zwei Formanten), Silben 3-6/s mit wechselnder
    Laenge, Zischlaute, Wortpausen und Satzpausen. Kein regelmaessiger Schlag."""
    rng = np.random.default_rng(seed)
    n = int(sec * rate); out = np.zeros(n, np.float32); t = 0.0
    while t < sec - 0.5:
        words = rng.integers(3, 9)
        for _ in range(words):
            for _ in range(rng.integers(1, 4)):
                d = rng.uniform(0.12, 0.3); a = int(t * rate); b = min(n, int((t + d) * rate))
                m = b - a
                if m <= 0: break
                tt = np.arange(m) / rate
                f0 = rng.uniform(110, 160) * (1 + 0.1 * np.sin(2 * np.pi * rng.uniform(1, 3) * tt))
                ph = 2 * np.pi * np.cumsum(f0) / rate
                v = sum(np.sin(k * ph) / k for k in range(1, 25))
                f1, f2 = rng.uniform(300, 800), rng.uniform(900, 2500)
                v = v * (1 + 0.8 * np.sin(2 * np.pi * f1 * tt)) * (1 + 0.5 * np.sin(2 * np.pi * f2 * tt))
                if rng.random() < 0.3:
                    v = v + rng.normal(0, 1.5, m) * (tt < 0.06)
                env = np.sin(np.pi * np.clip(tt / d, 0, 1)) ** 0.7
                out[a:b] += (v * env * rng.uniform(0.5, 1.0)).astype(np.float32)
                t += d
            t += rng.uniform(0.05, 0.25)
        t += rng.uniform(0.4, 1.2)
    return out / (np.max(np.abs(out)) + 1e-9) * 0.5


def run(x, **cfg):
    an = Analyzer(rate=RATE)
    rig, sh = build(source=an)
    for k, v in cfg.items():
        sh.cfg.set(k, v)
    t0, pos, states, talk = 1795500000.0, 0, [], []
    for i in range(int(len(x) / RATE / 0.025)):
        end = int((i + 1) * 0.025 * RATE)
        while pos + 512 <= end:
            an.process(x[pos:pos + 512])
            pos += 512
        sh.update(t0 + i * 0.025)
        states.append((i * 0.025, sh.state))
        talk.append((i * 0.025, sh.talk))
    return sh, states, talk


def entered(states, name, a=0.0, b=1e9):
    return [t for (t, s), (_, p) in zip(states[1:], states[:-1]) if s == name and p != name and a <= t < b]


rede = np.concatenate([np.zeros(RATE * 3, np.float32), synth_speech(40)])
sh, st, tk = run(rede, speech_guard=0)
check(len(entered(st, "drop")) >= 3, "ohne Schutz: Wortpausen werden zu Drops (%d), so war es" % len(entered(st, "drop")))
sh, st, tk = run(rede)
check(entered(st, "drop") == [] and entered(st, "build") == [] and entered(st, "break") == [],
      "mit Schutz: keine Drops, kein Aufbau, kein Break waehrend der Rede")
first = next((t for t, v in tk if v), None)
check(first is not None and first < 15, "Rede nach %.1f s erkannt" % (first or -1))
check(sh.snapshot()["talk"] is True, "Status: Sprache (Panel zeigt es an)")
tk_ = sh.takt(1795500000.0 + len(rede) / RATE)
check(tk_["sprache"] is True and tk_["abschnitt"] == "normal", "/api/takt: sprache true, abschnitt bleibt normal")

# Rede, dann setzt die Musik ein: Schutz endet, danach wird wieder erkannt
x = E.build()
musik = x[int(35 * RATE):int(65 * RATE)]
sh, st, tk = run(np.concatenate([rede, musik]))
end = len(rede) / RATE
gone = next((t for t, v in tk if t > end and not v), None)
check(gone is not None and gone - end < 6, "Musik mit Beat: Schutz endet nach %.1f s" % ((gone or 99) - end))
check(not sh.talk and sh.takt(1795500000.0 + len(rede) / RATE + 30)["sprache"] is False, "am Ende: keine Sprache mehr (auch /api/takt)")

# Flaeche und Applaus ohne Beat sind keine Rede (Eichstueck 5-35 s, Break 65-85 s)
sh, st, tk = run(x[:int(90 * RATE)])
check(not any(v for _, v in tk), "Applaus, Melodie, Break: nie als Sprache erkannt")
check(entered(st, "break"), "Break im Eichstueck wird weiter erkannt")

# Simulator ohne Schlag-Klarheit: nie (Licht Bild fuer Bild wie frueher)
rig, sim = build()
check(sim._talk_update(1000.0) is False, "Simulator: kein Schutz, Licht wie frueher")
# Waehrend Sprache: keine Szenen-Automatik, keine Phrasen, kein Shazam, kein Liedtext (Wunsch 25.11.2026)
rig, sp = build()
sp.talk = True
sp._talk_update = lambda now: True
calls, music = [], []
sp._scene_auto = lambda now, phrase, drop_start: calls.append(1)


class Titles:
    song = {"title": "Lied", "artist": "Jemand", "genre": ""}
    status = ""
    active = True
    genre = ""

    def tick(self, now, on, every, m, mx):
        music.append(m)
        return None


sp.titles = Titles()
sp.cfg.set("songrec_on", 1)
sp.cfg.set("lyrics_auto", 1)
sp.lyric_cache = object()
t = 1000.0
for i in range(2400):                                      # 60 s Simulator-Musik, als ob jemand spricht
    t += 0.025
    sp.update(t)
check(not calls, "keine Szenen-Automatik waehrend Sprache")
check(music and not any(music), "keine Titelerkennung (Shazam) waehrend Sprache")
check(sp._lyric_source(t) is None, "kein Liedtext waehrend Sprache")
hue = sp.hue_target
for i in range(800):
    t += 0.025
    sp.update(t)
check(sp.hue_target == hue, "keine Farbwechsel an Phrasen waehrend Sprache")
if sp.presets:
    eb = sp.presets[0]
    calm = sp.eb_roles(eb).get("calm") or []
    seen = set()
    for i in range(4000):                                  # 100 s: frueher spaetestens alle 45 s ein anderes Preset
        t += 0.025
        sp.update(t)
        seen.add(eb.values.get("preset"))
    check(len(seen) == 1 and (not calm or seen == {calm[0]}), "Effektband: ein ruhiges Preset, kein Wechsel (%s)" % sorted(seen))
check(sp.eff_tier() == 0 and sp.burst_until <= t and sp.white_env < 0.1, "ruhig: Stufe Chillen, keine Strobo-Bursts, keine Weiss-Blitze")
sp.auto_speed = "fast"
check(sp.eff_tier() == 3, "Tempo von Hand geht vor")

import webpanel  # noqa: E402
pg = webpanel.make_page()
check("S.talk?['<b class=\"modeb\">'+esc(mt)+'</b>','<span style=\"color:#9fd0ff\" title=\"Jemand spricht: keine Drops\">🎤 '+tr('st_talk')" in pg,
      "Panel: bei Sprache nur Betriebsart und Sprache (wie bei Stille)")
finish("test_sprache")
