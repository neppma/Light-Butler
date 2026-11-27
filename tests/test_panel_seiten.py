"""Panel-Aufbau: Einstellungsseite in sieben Bereichen (seit 27.11.2026, vorher allgemein und Auto-Erkennung), die
Fixtures auf eigener Seite /fixtures (wie DMX-Monitor und Hilfe)."""
import os
import subprocess
import tempfile

from _common import check, finish

import webpanel

p = webpanel.make_page()
sec = p[p.index('<div id="setsec">'):p.index('<div id="fxsec">')]
cats = {k: sec.index('data-cat="%s"' % k) for k in ("dev", "ton", "licht", "sicher", "haus", "bed", "sys")}
check(list(cats) == sorted(cats, key=cats.get), "Einstellungen in sieben Bereichen (27.11.2026)")
check(all(i in sec for i in ('id="sysbox"', 'id="homebox"', 'id="bkbox"', 'id="midibox"', 'id="audiobox"', 'id="musbox"', 'class="catset"')),
      "Verbindungen, Haus, Sicherung, MIDI, Audio, Musikordner und Platz fuer die Gruppen aus settings.py")
check("const SETCAT_G={'Ausgabe':'dev','Pixel-Matrix':'dev'" in p and "'Haus':'haus','Panel':'bed'" in p, "Gruppen aus settings.py stehen in ihrem Bereich")
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
