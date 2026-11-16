"""Bereich Effektband im Panel: Preset von Hand waehlen (auch in der Stille gedimmt sichtbar), nochmal tippen oder Auto =
automatisch. Blitz-Presets nur mit Strobe-Erlaubnis. Die Szenen-Automatik waehlt ab und zu statt einer Szene ein passendes
Effektband-Preset (Rollen calm/warm/party, dazu Sparkle, Karussell, Disco)."""
from _common import zurueck, build, Clock, check, finish

import webpanel

rig, sh = build(seed=3)
clk = Clock(sh)
clk.run(3)
eb = rig["effektband"]
roles = eb.extra["preset_roles"]
check(37 in roles["calm"] and 38 in roles["warm"] and 39 in roles["party"], "Sparkle ruhig, Karussell mittel, Disco Party")
E = sh.snapshot()["eb"]
check(E["man"] == 0 and [37, "Sparkle"] in E["names"] and len(E["names"]) == 39, "Status: 39 Presets mit Namen, automatisch")

sh.command({"eb_preset": 17})
clk.run(0.2)
check(eb.values["preset"] == 17 and sh.snapshot()["eb"]["man"] == 17, "Preset 17 von Hand: Effektband zeigt es")
sh.state = "idle"
sh._render_presets(clk.t, 0.0, False)
check(abs(eb.values["dimmer"] - 127.5 * sh.master) <= 1 and eb.values["preset"] == 17, f"Stille: von Hand gewaehlt bleibt gedimmt sichtbar ({eb.values['dimmer']})")
sh.state = "normal"
sh.command({"mix": "Karussell"})
clk.run(0.2)
check(eb.values["preset"] == 17, "Licht-Mix Karussell: das gewaehlte Preset bleibt")
sh.command({"mix": "nach aussen"})
clk.run(0.2)
check(eb.values["dimmer"] == 0, "Chase-Out: Effektband trotzdem aus")
zurueck(sh)
sh.command({"eb_preset": 17})
sh.command({"eb_preset": 17})
clk.run(0.2)
check(sh.eb_man is None and sh.snapshot()["eb"]["man"] == 0, "nochmal tippen: wieder automatisch")
sh.command({"eb_preset": 5})
sh.command({"eb_preset": 0})
check(sh.eb_man is None, "Auto-Knopf: wieder automatisch")
for bad in (99, "x"):
    try:
        sh.command({"eb_preset": bad})
        check(False, f"abgelehnt {bad}")
    except (ValueError, TypeError):
        check(True, f"abgelehnt {bad!r}")

rig2, sh2 = build(strobe=False, seed=3)
try:
    sh2.command({"eb_preset": 32})
    check(False, "strobo ohne Erlaubnis")
except ValueError:
    check(sh2.eb_man is None, "strobo (32) ohne Strobe-Erlaubnis abgelehnt")

# Fehler bis 31.10.2026: Beam von Hand und zurueck auf Auto setzte das gewaehlte Preset und die Szenen-Automatik zurueck
rig5, sh5 = build(seed=3)
c5 = Clock(sh5)
c5.run(2)
sh5.command({"eb_preset": 22})
sh5.command({"beam": {"gobo": 1}})
c5.run(0.5)
sh5.command({"beam": "auto"})
c5.run(0.5)
check(sh5.eb_man == 22 and rig5["effektband"].values["preset"] == 22, "Beam zurueck auf Auto: gewaehltes Effektband-Preset bleibt")
sh5.cfg.set("vega_live", 1)
c5.run(3)
check(sh5.eb_man == 22, "lebendiger Vega-Strahl setzt nichts zurueck")

# Szenen-Automatik mit Effektband-Presets
def run(share, strobe=True, secs=150):
    rig, sh = build(strobe=strobe, seed=3, pilot=True)
    for k, v in (("sa_on", 1), ("sa_prob", 100), ("sa_eb_share", share)):
        sh.cfg.set(k, v)
    picks, scenes = [], 0
    prev = None

    def each(t):
        nonlocal prev, scenes
        if sh.sa_eb is not None and sh.sa_eb is not prev:
            picks.append((sh.sa_eb["pid"], sh._base_tier(), rig["effektband"].values["preset"]))
        if sh.sa is not None and not sh.sa["drop"]:
            scenes += 1
        prev = sh.sa_eb
    Clock(sh).run(secs, each)
    return picks, scenes, sh


picks, scenes, s3 = run(100)
allr = {p for lst in roles.values() for p in lst}
check(len(picks) >= 4, f"Anteil 100 %: Effektband-Presets gewaehlt ({[p for p, _, _ in picks]})")
check(scenes == 0, "Anteil 100 %: keine Szenen ausser beim Drop")
check(all(p in roles[{0: "calm", 1: "warm"}.get(int(t), "party")] for p, t, _ in picks), "Preset passt zur Stufe")
check(s3.snapshot()["eb"]["auto"] in (0,) + tuple(p for p, _, _ in picks), "Panel sieht das automatisch gewaehlte Preset")
picks0, scenes0, _ = run(0)
check(not picks0 and scenes0 > 0, "Anteil 0 %: nur Szenen")
picksn, _, _ = run(100, strobe=False)
check(picksn and not any(p in (8, 32) for p, _, _ in picksn), "ohne Strobe-Erlaubnis keine Blitz-Presets")

page = webpanel.make_page()
check(page.index('id="pages"') < page.index('id="ebgrid"') and "function drawEB()" in page and "c({eb_preset:id})" in page, "Panel: Bereich Effektband unter den Szenen")
finish("test_effektband_panel")
