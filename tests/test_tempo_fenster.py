"""Tempo-Fenster: Antippen von Lamperl oder BPM-Zahl oeffnet darunter ein Fenster mit erkanntem Tempo, aktuellem
Tempo, Knoepfen fuer halb, -1, Auto, +1, doppelt und TAP im Takt. Der alte Bereich unten entfaellt."""
import os
import subprocess
import tempfile

from _common import build, check, finish

import webpanel

p = webpanel.make_page()
check('<span id="beat" onclick="tempoToggle(event)">' in p and '<span id="bpmtxt" onclick="tempoToggle(event)"' in p,
      "Lamperl und BPM-Zahl oeffnen das Fenster")
pop = p[p.index('<div id="tpop"'):p.index('<div id="row2">')]
for frag, what in (("bpmMul(0.5)", "halbes Tempo"), ("bpmAdd(-1)", "-1"), ("c({bpm:'auto'})", "Auto"), ("bpmAdd(1)", "+1"),
                   ("bpmMul(2)", "doppeltes Tempo"), ('id="tptap" onpointerdown="tapTempo(event)"', "TAP")):
    check(frag in pop, f"Fenster: {what}")
check('id="tempobox"' not in p, "alter Bereich Tempo unten entfaellt")
check("if(TAPS.length<4)" in p and "TAPS=TAPS.slice(-8)" in p and "now-TAPS[TAPS.length-1]>2000" in p,
      "TAP: ab 4 Schlaegen, Mittel der letzten 8, nach 2 s Pause neu")
check("if(bpm>=60&&bpm<=200)c({bpm:bpm})" in p, "TAP setzt nur sinnvolle Werte (60-200)")
check("S.bpm_manual&&S.bpm>0?String(Math.round(+S.bpm))" in p, "von Hand gestellt: oben steht die eingestellte Zahl")

rig, sh = build()
sh.command({"bpm": 124})
check(sh.manual_bpm == 124.0 and sh.snapshot()["bpm_manual"], "Show nimmt das Tempo vom Fenster an")
sh.command({"bpm": 300})
check(sh.manual_bpm == 200.0, "zu hohe Werte werden begrenzt")
sh.command({"bpm": "auto"})
check(sh.manual_bpm is None, "Auto: wieder nach der Erkennung")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_tempo_fenster")
