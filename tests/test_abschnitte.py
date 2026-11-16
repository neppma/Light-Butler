"""Abschnitte eines Liedes: Die Bruecke leitet aus der fertigen Analyse (Ereignisse, Lautstaerkekurve) Intro, Strophe,
Hauptteil, Break und Outro ab und schickt sie mit dem Plan. Der Pi kennt damit den aktuellen Abschnitt; das Panel zeigt
ihn als Streifen im Liedverlauf. Das Hi-Hat-Funkeln kann sich auf den Hauptteil beschraenken (hat_main)."""
import os
import sys

from _common import ROOT, build, check, finish

import webpanel
from mixxx_link import MixxxLink, clean_sections

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import analyze_track as at    # noqa: E402


def types(se):
    return [s[0] for s in se]


def res(energy, events=(), **kw):
    return dict({"duration": float(len(energy)), "energy": energy, "events": list(events), "first_beat": None, "bpm": None}, **kw)


# ---- Abschnitte aus Lautstaerke und Ereignissen -----------------------------------------------------------------
curve = [20] * 30 + [50] * 40 + [90] * 40 + [50] * 40 + [90] * 40 + [20] * 30
se = at.find_sections(res(curve))
check(types(se) == ["intro", "vers", "main", "vers", "main", "outro"], f"leises Intro, ruhig, voll, ruhig, voll, Outro ({types(se)})")
check(se[0][1] == 0.0 and se[-1][2] == len(curve) and all(a[2] == b[1] for a, b in zip(se, se[1:])), "lueckenlos von Anfang bis Ende")
check(abs(se[2][1] - 70) <= 3 and abs(se[-1][1] - 190) <= 3, f"Grenzen an den richtigen Stellen ({se[2][1]}, {se[-1][1]})")

se = at.find_sections(res([80] * 200))
check(types(se) == ["main"], "gleichmaessiges Lied: durchgehend Hauptteil")
check(at.find_sections(res([50] * 20)) == [] and at.find_sections({"duration": 200.0, "events": []}) == [], "zu kurz oder ohne Kurve: keine Abschnitte")

se = at.find_sections(res([80] * 200, [{"type": "break", "t": 90.0, "end": 110.0}]))
check(types(se) == ["main", "break", "main"] and se[1][1:] == [90.0, 110.0], "Break aus der Analyse wird uebernommen")
se = at.find_sections(res([80] * 200, [{"type": "intro", "t": 0.0, "end": 16.0}, {"type": "outro", "t": 180.0, "end": 200.0}]))
check(types(se) == ["intro", "main", "outro"] and se[0][2] == 16.0 and se[2][1] == 180.0, "Intro und Outro aus der Analyse")
se = at.find_sections(res([80] * 200, [{"type": "intro", "t": 0.0, "end": 3.0}]))
check(types(se) == ["main"], "ganz kurzes Intro zaehlt nicht")

blip = [20] * 60 + [90] * 5 + [20] * 60 + [90] * 80
se = at.find_sections(res(blip))
check("main" not in types(se)[:1] and not any(s[0] == "main" and s[2] - s[1] < at.SEC_MIN_S for s in se), f"kurze laute Stelle ist kein Hauptteil ({se})")

# Grenzen auf Hotcue, sonst auf den Takt
se = at.find_sections(res(curve), cues=[71.5])
check(se[2][1] == 71.5, "Grenze rastet auf den Hotcue ein")
se = at.find_sections(res(curve, first_beat=0.5, bpm=120.0))
check(all((s[1] - 0.5) / 2.0 == round((s[1] - 0.5) / 2.0) for s in se[1:]), "ohne Hotcue: Grenze auf dem Takt")

# echtes (kuenstliches) Audio durch die ganze Analyse
sig = at.synth_track(128.0)
sig = sig[0] if isinstance(sig, tuple) else sig
full = at.analyze_audio(sig, 128.0)
se = at.find_sections(full)
check(types(se)[0] == "intro" and types(se).count("break") == 2 and types(se).count("main") == 3, f"Audio: Intro, drei Hauptteile, zwei Breaks ({types(se)})")

# ---- Pi: Plan -> Status -> Panel --------------------------------------------------------------------------------------
check(clean_sections({"se": [["main", 0, 10], ["boese", 0, 5], ["main", 5, 5], ["main", "x", 9], "y"]}) == [["main", 0.0, 10.0]], "Unsinn im Plan wird verworfen")
check(clean_sections({}) == [] and clean_sections({"se": 5}) == [], "alte Bruecke ohne Abschnitte")

rig, sh = build()
link = MixxxLink(0)
now = 1000.0
plan = {"type": "plan", "d": 1, "key": "k", "title": "A - B", "du": 240.0, "ev": [], "en": [],
        "se": [["intro", 0.0, 30.0], ["main", 30.0, 200.0], ["outro", 200.0, 240.0]]}
link.feed(plan, now)


def at_pos(pos):
    link.feed({"d": 1, "pp": pos / 240.0, "du": 240.0, "rr": 1.0, "bp": 128.0, "pl": 1, "tl": 1, "vo": 1.0}, now)
    return link.status(now, sh.cfg)


check(at_pos(10.0)["section"] == "intro" and at_pos(100.0)["section"] == "main" and at_pos(220.0)["section"] == "outro", "aktueller Abschnitt je nach Stelle im Lied")
st = at_pos(100.0)
check(len(st["bar"]["se"]) == 3, "Abschnitte stehen im Liedverlauf")
sh.mx = st
check(sh._mx_public()["sec"] == "main" and sh._mx_public()["bar"]["se"][1][0] == "main", "Panel bekommt die Abschnitte")
check("B.se" in webpanel.make_page(), "Panel zeichnet die Abschnitte im Liedverlauf")

# ---- Hi-Hat-Funkeln nur im Hauptteil ------------------------------------------------------------------------------------
check(sh.cfg["hat_main"] == 0.0 and sh.cfg["hat_share"] == 100.0 and sh.cfg["hat_eb_duck"] == 0.0, "Standard: Funkeln wie bisher")
check(sh._hat_gate(), "Standard: Funkeln darf immer")
sh.cfg.set("hat_main", 1)
check(sh._in_main() and sh._hat_gate(), "nur im Hauptteil: im Abschnitt main an")
sh.mx = at_pos(10.0)
check(not sh._in_main() and not sh._hat_gate(), "nur im Hauptteil: im Intro aus")
sh.mx = None
sh.auto_speed = "fast"
check(sh._in_main(), "ohne Analyse: hohe Stufe zaehlt als Hauptteil")
sh.auto_speed = "slow"
check(not sh._in_main() or sh.eff_tier() >= 2, "ohne Analyse: ruhige Stufe nicht")

# Anteil: je Phrase gewuerfelt, innerhalb der Phrase gleich
rig, sh = build()
sh.cfg.set("hat_share", 30)
rolls = []
for block in range(2000):
    sh.step = block * 8 * sh.bar_len
    first = sh._hat_gate()
    sh.step += 5
    check_same = sh._hat_gate() == first
    rolls.append((first, check_same))
share = sum(r[0] for r in rolls) / len(rolls)
check(abs(share - 0.30) < 0.05, f"Anteil 30 %: etwa jede dritte Phrase ({share:.2f})")
check(all(r[1] for r in rolls), "innerhalb einer Phrase bleibt die Entscheidung gleich")
sh.cfg.set("hat_share", 0)
sh.step += 8 * sh.bar_len
check(not sh._hat_gate(), "Anteil 0 %: nie")

finish("test_abschnitte")
