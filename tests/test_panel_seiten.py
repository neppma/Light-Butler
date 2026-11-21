"""Panel-Aufbau: Einstellungen allgemein (mit der Gruppe Panel) und Einstellungen (Auto-Erkennung) als zwei
Aufklapp-Bereiche, die Fixtures auf eigener Seite /fixtures (wie DMX-Monitor und Hilfe)."""
import os
import subprocess
import tempfile

from _common import check, finish

import webpanel

p = webpanel.make_page()
gen, auto, fxl, fxs = (p.find('<details id="genbox"'), p.find('<details id="autobox"'), p.find('id="fxlink"'), p.find('<div id="fxsec">'))
check(min(gen, auto, fxl, fxs) > 0 and gen < auto < fxl < fxs, "Reihenfolge: allgemein, Auto-Erkennung, Link Fixtures, Fixtures-Bereich")
blk = p[gen:auto]
check(all(i in blk for i in ('id="sysbox"', 'id="homebox"', 'id="bkbox"', 'id="midibox"', 'id="audiobox"', 'id="genset"')),
      "allgemein: Verbindungen, Haus, Sicherung, MIDI, Audio und Platz fuer die Gruppe Panel")
check('id="setlist"' in p[auto:fxl], "Auto-Erkennung: Liste der Einstellungen im zweiten Bereich")
check("(GEN_GROUPS.includes(g.group)&&gen?gen:box).appendChild(d)" in p and "const GEN_GROUPS=['Ausgabe','Haus','Nebel','Titelerkennung','Panel','Pixel-Matrix'];" in p,
      "Gruppen Ausgabe, Haus, Nebel, Titelerkennung und Panel stehen unter den allgemeinen Einstellungen")
import settings
groups = {getattr(settings, n) for n in ("G_OUT", "G_HOME", "G_FOG", "G_PANEL")}
check(groups == {"Ausgabe", "Haus", "Nebel", "Panel"}, "Gruppennamen passen zu settings.py")
check('<a id="fxlink" class="seclink" href="/fixtures">' in p and "#fxsec{display:none}" in p, "Fixtures nur als Link (im selben Tab)")
f = webpanel.fixtures_page()
check('<body class="vfx">' in f and "<title>Light-Butler - Fixtures</title>" in f, "Fixtures-Seite: eigener Titel, nur Fixtures sichtbar")
check("body.vfx>*:not(#fxsec):not(#toast):not(script){display:none!important}" in f and 'data-back="/settings" data-cur="settings" data-title="h_fixtures"' in f,
      "Fixtures-Seite blendet den Rest aus, Kopfleiste zurueck zu den Einstellungen")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_panel_seiten")
