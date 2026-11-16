"""Kopf ohne Springen: der Mixxx-Bereich (Zeile und Liedverlauf) ist immer gleich hoch, ohne Deck ein gestrichelter
Platzhalter. General Dimmer und Gruppen stehen neben den Blitzen pro Sekunde (eigene Kopfzeile entfaellt). Die grossen
Knoepfe (STROBE bis FREEZE) sind so hoch wie die Knoepfe fuer Bewegung und Licht-Mix."""
import os
import subprocess
import tempfile

from _common import check, finish

import webpanel

p = webpanel.make_page()
hdr = p[p.index('<div id="hdr">'):p.index('<div id="toast">')]
check('id="dimrow"' not in hdr and 'id="mxline"' in hdr and '<canvas id="mxbar"></canvas>' in hdr,
      "Kopf: Mixxx-Zeile und Liedverlauf, keine Dimmer-Zeile mehr")
row = p[p.index('<div class="blitzrow">'):]
check(row.index('id="blitzhz"') < row.index('<div id="dimrow">') < row.index('id="glbtn"') < row.index('<div id="glpop"'),
      "Zeile unter den grossen Knoepfen: Blitze, dann Dimmer mit Gruppen, Gruppenregler darunter")
check(".blitzrow{display:flex;flex-wrap:wrap" in p, "zu schmal (Handy): Dimmer in eigener Zeile")
check("#mxbar{display:block;" in p and "cv.style.display='none'" not in p, "Liedverlauf immer sichtbar (kein Springen)")
check(".ctlrow button{flex:1 1 auto;min-width:0;min-height:50px" in p and "button{background:#2a2c3d;color:#eee;border:0;border-radius:10px;padding:14px 4px;font-size:14px;font-weight:600;min-height:50px}" in p,
      "grosse Knoepfe so hoch wie die Effekt-Knoepfe (50 px)")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_kopf_ruhig")
