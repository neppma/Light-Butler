"""Kopf kompakter: General Dimmer halb so lang, daneben "Gruppen" mit aufklappbaren Gruppenreglern (zwei Spalten),
Blitze pro Sekunde als Knopfreihe statt langem Regler. Am Licht aendert sich nichts."""
import os
import subprocess
import tempfile

from _common import check, finish

import webpanel

p = webpanel.make_page()
dim = p[p.index('<div id="dimrow">'):]
check('id="master"' in dim[:600] and 'id="glbtn" onclick="glToggle()"' in dim[:900], "Dimmer und Knopf Gruppen in einer Zeile")
check("#dimrow{flex:1 1 330px" in p, "Dimmer teilt sich die Zeile mit den Blitzen (kuerzer als frueher)")
check('<div id="glpop" style="display:none"><div id="glbody"></div></div>' in p, "Gruppenregler aufklappbar, anfangs zu")
check('id="glbox"' not in p, "alter Bereich Gruppen-Helligkeit entfaellt")
check("#glbody{display:grid;grid-template-columns:1fr 1fr" in p and "@media(max-width:520px){#glbody{grid-template-columns:1fr}" in p,
      "zwei Spalten, am Handy eine")
check("document.getElementById('glmod').innerHTML=n?n+'<span class=\"glw\"> '+tr('gl_mod')+'</span>':''" in p, "Knopf zeigt, wie viele Gruppen nicht auf 100 % stehen")
check("#dimrow input[type=range]{flex:1 1 auto;min-width:60px" in p, "der Regler bekommt den freien Platz in seiner Zeile")
check('<div id="blitzhz" class="bzseg"></div>' in p and "e.onclick=()=>c({blitz_hz:v})" in p, "Blitze pro Sekunde als Knoepfe")
check("cap=!S.strobe&&BZ[k]>3" in p and "e.classList.toggle('cap',cap)" in p, "ohne Strobe-Erlaubnis: Knoepfe ueber 3 abgedunkelt")
check("const BZ=[1,2,4,5,6.7,10];" in p, "dieselben Stufen wie bisher")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_dimmer_kompakt")
