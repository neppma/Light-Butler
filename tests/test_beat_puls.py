"""Beat-Puls: Licht und Effektband pulsieren in AUTO auf denselben Beats wie das Lamperl im Panel (beat_pulse,
beat_pulse_eb; Standard aus). Ambiente pulsiert nie. Ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde.
Dazu: Effektband wird beim Hi-Hat-Funkeln dunkler (hat_eb_duck), damit es das Funkeln nicht ueberstrahlt."""
from _common import build, check, finish, Clock, ch

import audio
import scenes  # noqa: F401


def pulses(strobe, bpm=None, sec=8.0, start=22.0, **cfg):
    rig, sh = build(strobe=strobe)
    for k, v in cfg.items():
        sh.cfg.set(k, v)
    clk = Clock(sh)
    clk.run(start)
    times, lamp = [], []
    last, last_b = sh.pulse_t, sh.beat_t

    def look(t):
        nonlocal last, last_b
        if sh.pulse_t != last:
            times.append(t)
            last = sh.pulse_t
        if sh.beat_t != last_b:
            lamp.append(t)
            last_b = sh.beat_t
    clk.run(sec, look)
    return times, lamp, rig, sh, clk


rig, sh = build()
check(sh.cfg["beat_pulse"] == 0.0 and sh.cfg["beat_pulse_eb"] == 0.0, "Standard: aus")
t0, _, _, sh0, _ = pulses(True)
check(not t0 and sh0.pulse_k == 1.0, "aus: kein Puls, Faktor 1")

# ---- Takt: auf dem Beat des Lamperls ----------------------------------------------------------------------------------
ts, lamp, _, sh, _ = pulses(True, beat_pulse=50)
check(len(ts) > 8 and set(ts) <= set(lamp), f"jeder Puls liegt auf einem Beat des Lamperls ({len(ts)} Pulse, {len(lamp)} Beats)")
check(len(ts) >= len(lamp) - 1, "mit Strobe-Erlaubnis: jeder Beat pulsiert")
tn, lampn, _, _, _ = pulses(False, beat_pulse=50)
check(tn and set(tn) <= set(lampn), "ohne Strobe-Erlaubnis: Puls bleibt auf dem Beat")
check(min(b - a for a, b in zip(tn, tn[1:])) >= 0.5 - 1e-6, f"ohne Strobe-Erlaubnis: hoechstens 2 Pulse pro Sekunde ({len(tn)} in 8 s, {len(lampn)} Beats)")

# ---- Tiefe: nie ganz dunkel, voll auf dem Beat -------------------------------------------------------------------------
rig, sh = build(strobe=True)
sh.cfg.set("beat_pulse", 70)
clk = Clock(sh)
clk.run(22)
ks = []
clk.run(6, lambda t: ks.append(sh.pulse_k) if sh.state == "normal" else None)
check(ks and max(ks) > 0.95, f"auf dem Beat volle Helligkeit ({max(ks):.2f})")
check(min(ks) >= 0.30 - 1e-9 and min(ks) < 0.7, f"dazwischen dunkler, hoechstens 70 % ({min(ks):.2f})")

# ---- Ambiente und Barlicht bleiben, Docooler und Effektband pulsieren --------------------------------------------------
def run(strobe=True, sec=4.0, **cfg):
    rig, sh = build(strobe=strobe)
    for k, v in cfg.items():
        sh.cfg.set(k, v)
    clk = Clock(sh)
    clk.run(22)
    sh.auto_speed = "slow"
    clk.run(1.5)
    d = {"par": [], "theke": [], "eb": [], "lvl": []}
    theke = next(f for f in rig.fixtures if f.type == "wled_drgb")
    band = rig.presets_fx if hasattr(rig, "presets_fx") else sh.presets[0]

    def look(t):
        d["par"].append(list(rig.render()[220:228]))
        d["theke"].append(dict(theke.values))
        d["eb"].append(band.values["dimmer"])
    clk.run(sec, look)
    return d, sh


base, _ = run()
puls, _ = run(beat_pulse=70)
check(puls["par"] == base["par"], "Barlicht pulsiert nie")
check(puls["theke"] == base["theke"], "Theke pulsiert nie")
check(puls["eb"] == base["eb"], "nur beat_pulse: Effektband unveraendert")
ebp, _ = run(beat_pulse_eb=70)
ratio = [a / b for a, b in zip(ebp["eb"], base["eb"]) if b > 10]
check(ratio and min(ratio) < 0.7 and max(ratio) > 0.95, f"Effektband pulsiert ({min(ratio):.2f}..{max(ratio):.2f})")
check(min(ratio) >= 0.30 - 0.02, "Effektband: nie unter 30 %")

# ---- Nur in AUTO: keine Szene, kein Blackout, ohne Beat kein Dunkelstehen --------------------------------------------------
rig, sh = build(strobe=True)
sh.cfg.set("beat_pulse", 70)
clk = Clock(sh)
clk.run(22)
sh.command({"blackout": True})
clk.run(1)
check(sh.pulse_k == 1.0 and not sh.pulse_on, "Blackout: kein Puls")
sh.command({"blackout": False})
clk.run(0.2)


class Stumm:
    """Musik laeuft, aber ohne Beat und Kick."""

    def __init__(self):
        self.sim = audio.Simulator()
        self.b = self.k = None

    def poll(self, now=None):
        f = self.sim.poll(now)
        self.b = f.beat_count if self.b is None else self.b
        self.k = f.kick_count if self.k is None else self.k
        return f._replace(beat_count=self.b, kick_count=self.k)


rig, sh = build(strobe=True, source=Stumm())
sh.cfg.set("beat_pulse", 70)
clk = Clock(sh)
clk.run(24)
check(sh.pulse_k == 1.0, "ohne Beat bleibt das Licht nicht dunkel stehen")

# ---- Effektband zuruecknehmen beim Funkeln -----------------------------------------------------------------------------
class Hats:
    def __init__(self, hz):
        self.sim, self.hz, self.t0 = audio.Simulator(), hz, None

    def poll(self, now=None):
        f = self.sim.poll(now)
        self.t0 = now if self.t0 is None else self.t0
        return f._replace(hat_count=int((now - self.t0) * self.hz))


def duck(amount, hz=16.0, share=100.0):
    rig, sh = build(strobe=True, source=Hats(hz))
    sh.cfg.set("hat_eb_duck", amount)
    sh.cfg.set("hat_share", share)
    clk = Clock(sh)
    clk.run(22)
    sh.auto_speed = "slow"
    clk.run(3)
    return sh.presets[0].values["dimmer"], sh.state, sh.hat_duck


a, st_a, _ = duck(0)
b, st_b, hd = duck(50)
check(st_a == "normal" and st_b == "normal", "Vergleich im normalen Licht")
check(hd > 0.9 and abs(b / a - 0.5) < 0.08, f"Effektband halb so hell beim Funkeln ({a} -> {b})")
c0, _, hd0 = duck(50, share=0)
check(hd0 < 0.1 and abs(c0 - a) <= 2, f"kein Funkeln (Anteil 0 %): Effektband wie sonst ({a} -> {c0})")

# ---- Im Autopilot (Knopf AUTO an) wirken Puls und Funkeln genauso ------------------------------------------------------
rig, sh = build(strobe=True, source=Hats(16.0))
sh.pilot = True
sh.cfg.set("beat_pulse", 70)
sh.cfg.set("hat_eb_duck", 50)
clk = Clock(sh)
clk.run(22)
seen = []
clk.run(6, lambda t: seen.append((sh.pulse_k, sh.hat_env)) if sh.sc is None and sh.state == "normal" else None)
check(sh.pilot and seen and min(k for k, _ in seen) < 0.7, "Autopilot: Beat-Puls laeuft")
check(max(h for _, h in seen) > 0.9, "Autopilot: Funkeln laeuft")

finish("test_beat_puls")
