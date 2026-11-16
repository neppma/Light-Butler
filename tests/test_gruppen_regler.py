"""Gruppen-Regler: jeder Regler wirkt auf seine Geraete. Fehlerbericht: Das Barlicht reagierte nur noch auf Ambiente, seit es in der
Gruppe ambient ist; sein eigener Regler ging ins Leere. Jetzt wirken beide zusammen."""
from _common import Clock, build, check, ch, finish

import show as sw


def level(rig, sh, name, **glevel):
    sh.glevel.update({k: 1.0 for k in sh.glevel})
    sh.glevel.update(glevel)
    Clock(sh).run(0.05)
    return rig[name].level


rig, sh = build(seed=2)
check(level(rig, sh, "par") == 1.0, "alle Regler voll: Barlicht voll")
check(abs(level(rig, sh, "par", barlight=0.5) - 0.5) < 1e-9, "Regler PAR Barlicht wirkt")
check(abs(level(rig, sh, "par", amb=0.5) - 0.5) < 1e-9, "Regler Ambiente wirkt weiter")
check(abs(level(rig, sh, "par", barlight=0.5, amb=0.5) - 0.25) < 1e-9, "beide zusammen")
check(level(rig, sh, "theke", barlight=0.5) == 1.0 and level(rig, sh, "effektband", barlight=0.5) == 1.0, "Theke und Effektband folgen dem Barlicht-Regler nicht")
check(abs(level(rig, sh, "theke", amb=0.5) - 0.5) < 1e-9, "Theke folgt Ambiente")
# Jeder Regler hat Geraete
used = {sw.GROUP_KEYS.get(f.group) for f in rig.fixtures} | {f.extra.get("fader") for f in rig.fixtures}
for key, label in sw.GROUP_LABELS:
    if key != "nano":
        check(key in used, f"Regler {label} steuert mindestens ein Geraet")
# Ausgabe: Licht-Kanaele am Barlicht
rig, sh = build(seed=2)
sh.command({"allbright": True})
c = Clock(sh)
c.run(0.1)
full = ch(rig, "par", "r")
sh.command({"glevel": {"barlight": 0.5}})
c.run(0.1)
check(full > 0 and ch(rig, "par", "r") == full, "Sonnenbrille: immer voll, wie zuvor")
sh.command({"allbright": False})
sh.command({"color": "rot", "auto": False})
c.run(3)
a = ch(rig, "par", "r")
sh.command({"glevel": {"barlight": 0.0}})
c.run(0.1)
check(ch(rig, "par", "r") == 0 and ch(rig, "par", "g") == 0 and ch(rig, "par", "b") == 0, f"Barlicht-Regler auf 0: dunkel (vorher {a})")
# Regler bleiben auch im Autopilot frei
rig, sh = build(seed=2, pilot=True)
sh.command({"glevel": {"uv": 0.3}})
check(abs(sh.glevel["uv"] - 0.3) < 1e-9 and sh.pilot, "Autopilot: Gruppen-Regler frei")
sh.command({"master": 0.4})
check(abs(sh.master - 0.4) < 1e-9, "Autopilot: Master frei")
# UV-Leiste: Grundhelligkeit
ROWS = ("uv1", "uv2", "uv3", "uv4")


def uv_run(base=0.0, sec=12, level=1.0, master=1.0, style=None):
    rig, sh = build(seed=5)
    sh.cfg.set("uv_base", base)
    sh.glevel["uv"], sh.master = level, master
    if style:
        sh.style_man = style
    c = Clock(sh)
    c.run(3)
    out = []
    c.run(sec, lambda t: out.append(min(ch(rig, "uv_bar", p) for p in ROWS)) if sh.state in ("normal", "break") else None)
    return out, sh


base0, _ = uv_run(0.0)
check(min(base0) == 0, "Standard: zwischen den Schlaegen dunkel wie bisher")
b30, _ = uv_run(30.0)
check(b30 and min(b30) >= 74 and min(b30) <= 80, f"30 %: nie unter 30 % am Kanal (kleinster Wert {min(b30)})")
b30l, _ = uv_run(30.0, level=0.5)
check(36 <= min(b30l) <= 40, f"Regler UV-Leiste wirkt auch auf die Grundhelligkeit ({min(b30l)})")
b30m, _ = uv_run(30.0, master=0.5)
check(36 <= min(b30m) <= 40, f"General Dimmer wirkt auch ({min(b30m)})")
xm, _ = uv_run(30.0, style="weihnachten")
check(not xm or max(xm) == 0, "Stil Weihnachten ohne UV bleibt ohne UV")
rig, sh = build(seed=5)
check(sh.cfg["uv_base"] == 0.0, "Standard ist aus")
finish("test_gruppen_regler")
