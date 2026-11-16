"""Kopf aufgeraeumt: Zahnrad links neben dem Hilfe-Knopf oeffnet die Einstellungen auf eigener Seite im selben Tab
(/settings, oben "Panel" zurueck), Statusfeld so hoch wie die runden Knoepfe, rote Warnungen in Zeile 2 mittig."""
import os
import subprocess
import tempfile

from _common import ROOT, check, finish

import webpanel

p = webpanel.make_page()
row1 = p[p.index('<div id="row1">'):p.index('<div id="row2">')]
check(row1.index('id="setbtn"') < row1.index('id="helpbtn"') < row1.index('id="powerbtn"'), "Zahnrad links neben ? und Ausschalten")
check('<a id="setbtn" href="/settings" title="Einstellungen / Settings"><svg' in p, "Zahnrad oeffnet /settings im selben Tab")
_nav = open(os.path.join(ROOT, "pi", "static", "sm", "nav.js"), encoding="utf-8").read()
check(">⚙</a>" not in p and "settings: '<svg" in _nav, "Zahnrad als Grafik (Zeichen war im Browser am Mac zu klein, 12.11.2026)")
check("#evslot{flex:1;min-width:0;height:30px;" in p and "#helpbtn{flex:none;width:30px;height:30px" in p, "Statusfeld so hoch wie die Knoepfe (30 px)")
check("#row2{display:grid;grid-template-columns:minmax(0,1fr) auto" in p and "#lvm{grid-column:2;justify-self:end}" in p and "r2w" not in p,
      "Zeile 2: Betriebsart links, Pegel rechts, keine Warnungen mehr")
st = p[p.index('<div class="pbox" id="stbox">'):p.index('<div id="fognote"')]
check(st.index('id="mxbar"') < st.index('id="warnrow"'), "Hinweiszeile unten im Statusbereich")
check("#warnrow{display:flex;align-items:center;gap:6px;height:24px;" in p and "overflow-x:auto" in p, "feste Hoehe, bei vielen Warnungen wischen, nichts springt")
check("wh||(S.mode?" in p and "tr('w_allok')" in p, "ohne Warnung: Alle Geraete erreichbar, aber erst mit echten Daten")
check("catch(e){const wr=document.getElementById('warnrow');if(wr){wr.dataset.h='';wr.innerHTML=''}" in p, "Verbindung weg: keine alte Entwarnung stehen lassen")
check(p.index("wh=warnl.map") < p.index("wbtn('i','Antippen = Art-Net"), "fehlende Geraete zuerst, sie sind am wichtigsten")
s = p.index('<div id="setsec">')
sec = p[s:p.index('<div id="fxsec">')]
check('<div class="s2lnav" data-back="/" data-cur="settings" data-title="h_setpage">' in sec and all(k in sec for k in ('id="genbox"', 'id="autobox"', 'id="fxlink"', 'href="/dmx"')),
      "Einstellungsseite: zurueck, allgemein, Auto-Erkennung, Fixtures, DMX-Monitor")
check("#setsec{display:none}body.vset #setsec{display:block}" in p, "Hauptseite zeigt die Einstellungen nicht mehr")
sp = webpanel.settings_page()
check('<body class="vset">' in sp and "<title>Light-Butler - Einstellungen</title>" in sp, "Seite /settings: eigener Titel, nur Einstellungen")
check("location.href='/settings#audio'" in p and "location.hash==='#audio'" in p, "Pegelmeter springt zur Einstellungsseite beim Audio-Eingang")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_einstellungsseite")
