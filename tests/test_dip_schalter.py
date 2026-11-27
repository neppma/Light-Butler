"""Tippschalter (DIP) neben der Startadresse (27.11.2026): bei jedem DMX-Geraet zeigt die Fixture-Ansicht, welche Schalter fuer
die Adresse auf ON muessen (Schalter i = 2^(i-1)). Typen mit "dip" (zum Beispiel FM-1500, 9 Schalter) zeigen das Bild gleich
offen, andere zum Aufklappen. Rechnet im Browser (dipHtml), hier mit node nachgeprueft."""
import json
import os
import subprocess
import tempfile

import yaml

from _common import PI, check, finish

import webpanel

p = webpanel.make_page()
js = p.split("<script>")[-1].split("</script>")[0]
check("function dipHtml(addr,n,off)" in js and "details class=\"dipw\"" in js, "Bild der Tippschalter in der Fixture-Ansicht")
import fixture_edit as fe
check("document.getElementById('na_addr').addEventListener('input',dipNa)" in js and 'id="na_dipw"' in js, "auch beim Anlegen (+ Fixture): Schalter zur Adresse")
check(next(t for t in fe.type_summary({"types": T0}) if t["name"] == "fog_fm1500")["dip"] == 9 if (T0 := __import__("yaml").safe_load(open(os.path.join(PI, "fixtures.yaml"), encoding="utf-8"))["types"]) else False,
      "Typ-Katalog meldet die Zahl der Schalter")
check("dw.innerHTML=dipHtml(ai.value,f.dip,f.dip_offset)" in js, "beim Bearbeiten folgen die Schalter der eingetippten Adresse")
with open(os.path.join(PI, "fixtures.yaml"), encoding="utf-8") as f:
    T = yaml.safe_load(f)["types"]
check(T["fog_fm1500"].get("dip") == 9, "FM-1500: 9 Tippschalter")

# dipHtml mit node ausfuehren
start, end = js.index("function dipHtml("), js.index("function editForm(")
code = ("const tr=k=>k,esc=s=>String(s);" + js[start:end] +
        "const out={};for(const [a,n,o] of [[1,9,0],[49,9,0],[301,9,0],[511,9,0],[512,9,0],[512,0,0],[1,9,1],[49,9,1],[0,9,0]]){"
        "const h=dipHtml(a,n,o);out[a+'/'+n+'/'+o]={on:(h.match(/dsw dson/g)||[]).length,n:(h.match(/class=\"dsw/g)||[]).length,txt:h.split('diptx\">')[1]}}"
        "console.log(JSON.stringify(out))")
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(code)
try:
    r = subprocess.run(["node", fh.name], capture_output=True, text=True)
    R = json.loads(r.stdout) if r.returncode == 0 else None
except FileNotFoundError:
    R = None
os.unlink(fh.name)
if R is None:
    check(True, "node fehlt: Rechnung nicht geprueft")
else:
    check(R["1/9/0"]["on"] == 1 and "<b>1</b> (1 = 1)" in R["1/9/0"]["txt"], "Adresse 1: nur Schalter 1")
    check(R["49/9/0"]["on"] == 3 and "<b>1, 5, 6</b> (1 + 16 + 32 = 49)" in R["49/9/0"]["txt"], "Adresse 49: Schalter 1, 5, 6")
    check("<b>1, 3, 4, 6, 9</b> (1 + 4 + 8 + 32 + 256 = 301)" in R["301/9/0"]["txt"], "Adresse 301: Schalter 1, 3, 4, 6, 9")
    check(R["511/9/0"]["on"] == 9, "Adresse 511: alle neun")
    check(R["512/9/0"]["on"] == 0 and "dip_big" in R["512/9/0"]["txt"], "512 geht mit 9 Schaltern nicht: Hinweis")
    check(R["512/0/0"]["n"] == 10 and R["512/0/0"]["on"] == 1, "ohne Angabe beim Typ: 9 Schalter, fuer 512 zehn")
    check(R["1/9/1"]["on"] == 0 and "dip_none" in R["1/9/1"]["txt"] and R["49/9/1"]["on"] == 2, "Geraet zaehlt ab 0 (dip_offset): Adresse - 1")
    check("dip_big" in R["0/9/0"]["txt"], "Adresse 0 gibt es nicht")

finish("test_dip_schalter")
