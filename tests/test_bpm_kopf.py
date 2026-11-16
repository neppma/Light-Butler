"""Kopfzeile 1: Quelle des Tempos (MIXXX blau, MANUELL orange) klein ueber "BPM" rechts neben der Zahl, nicht mehr
darunter. Lamperl, Zahl, Beschriftung und Statusfeld auf einer Mittellinie."""
import os
import subprocess
import tempfile

from _common import check, finish

import webpanel

p = webpanel.make_page()
check('<b id="bpmnum">--</b><span id="bpmlab"><span id="bpmsrc"></span><small>BPM</small></span>' in p,
      "Quelle oben, BPM darunter, rechts neben der Zahl")
check("#bpmtxt{flex:none;min-width:84px;display:flex;align-items:center" in p and "#row1{display:flex;align-items:center" in p,
      "alles auf einer Mittellinie")
check("#bpmlab{display:flex;flex-direction:column;justify-content:flex-end;height:26px" in p,
      "BPM bleibt unten, auch ohne Quelle (nichts springt)")
check("#beat{display:inline-block;width:32px;height:32px;" in p and "#bpmtxt{box-sizing:border-box;height:32px;border:1px solid #2a2e3c" in p,
      "Lamperl und BPM-Block so hoch wie Statusfeld und Knoepfe (32 px mit Rand)")
check("bs.classList.toggle('man',!!S.bpm_manual)" in p and "#bpmsrc.man{color:#ffb86b}" in p, "MANUELL orange, MIXXX blau")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_bpm_kopf")
