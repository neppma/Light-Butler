"""Einstellungsseite uebersichtlich (27.11.2026): Startseite mit sieben Bereichen samt Stand, Suche ueber alle
Einstellungen, Filter "Nur Geaendertes". Jede Gruppe aus settings.py hat ihren Bereich, nichts ging beim Umbau verloren."""
import os
import re
import subprocess
import tempfile

from _common import check, finish

import settings
import texts
import webpanel

p = webpanel.make_page()
sec = p[p.index('<div id="setsec">'):p.index('<div id="hlsec"')]
js = p.split("<script>")[-1].split("</script>")[0]
CATS = ("dev", "ton", "licht", "sicher", "haus", "bed", "sys")

check(all('data-cat="%s"' % k in sec for k in CATS) and "const CATS=[['dev'," in js, "sieben Bereiche im HTML und im Skript")
check('id="sethome"' in sec and 'id="setq"' in sec and 'id="setcats"' in sec and 'id="setmodbtn"' in sec, "Startseite: Suche, Bereiche, Nur Geaendertes")
check(sec.count('class="catset"') == len(CATS) - 1, "jeder Bereich ausser System hat Platz fuer seine Gruppen aus settings.py")

# jede Gruppe und jeder abweichende Schluessel passt zu settings.py
gmap = dict(re.findall(r"'([^']+)':'(dev|ton|licht|sicher|haus|bed|sys)'", js[js.index("const SETCAT_G="):js.index("const SETCAT_T=")]))
groups = {d.group for d in settings.DEFS}
check(set(gmap) <= groups, "zugeordnete Gruppen gibt es in settings.py")
LICHT = {settings.G_AUDIO, settings.G_KICK, settings.G_ENERGY, settings.G_COLOR, settings.G_PHASE, settings.G_TIER, settings.G_FLASH,
         settings.G_METER, settings.G_VEGA, settings.G_SCAUTO, settings.G_AMB, settings.G_MIXXX, settings.G_SONG, settings.G_LASER,
         settings.G_FOG, settings.G_HOME, settings.G_PANEL, settings.G_OUT, settings.G_MATRIX}
check(groups <= LICHT, "keine neue Gruppe ohne Entscheidung, wohin sie gehoert (sonst landet sie unter 'Wie das Licht reagiert')")
kmap = dict(re.findall(r"(\w+):'(dev|ton|licht|sicher|haus|bed|sys)'", js[js.index("const SETCAT_K="):js.index("const CATS=")]))
keys = {d.key for d in settings.DEFS}
check(kmap and set(kmap) <= keys, "abweichende Schluessel gibt es in settings.py")
check(kmap.get("sm_laser") == kmap.get("sm_fog") == kmap.get("light_delay_ms") == "sicher" and gmap.get("Laser") == gmap.get("Nebel") == "sicher",
      "Laser, Nebel und Licht-Verzoegerung unter Sicherheit")
check("const ss=document.getElementById('strobeslot')" in js and 'id="strobeslot"' in sec[sec.index('data-cat="sicher"'):], "Strobe-Erlaubnis unter Sicherheit")

# nichts verloren: alle Felder und Links der alten Seite sind noch da
for i in ("sysbox", "syssum", "homebox", "bkbox", "midibox", "audiobox", "mroot", "mexcl", "nashost", "artip", "npip", "dmxmon",
          "fxlink", "mylinks", "ml_host", "setbar", "olarow", "reach", "net"):
    check('id="%s"' % i in sec, "noch da: #" + i)
for h in ("/fixtures", "/raum", "/matrix", "/apc", "/lumi", "/dmx", "/dmx-debug", "/eichen", "/software", "/about", "/health", "/download/backup"):
    check('href="%s"' % h in sec, "Link noch da: " + h)
check(sec.count("<details") == sec.count("</details>") and sec.count("<div") == sec.count("</div>"), "HTML sauber geschlossen")

# Texte deutsch und englisch
for k in ["cat_" + c for c in CATS] + ["cat_" + c + "_d" for c in CATS] + ["set_search", "set_modonly", "set_overview", "set_nohit", "set_nomod",
                                                                          "set_nmod", "set_hits", "m_music", "set_g_show", "set_g_safe"]:
    check(f'"{k}"' in open(texts.__file__, encoding="utf-8").read(), "Text vorhanden: " + k)

# Suche, Spruenge, alte Adressen
check("function setFind()" in js and "function setUnits()" in js and "function nrm(s)" in js, "Suche ueber alle Einstellungen")
check("['ß','ss']" in js, "Suche findet Weisse auch als Weiße")
check("alias={audio:'ton',nas:'ton',musik:'ton'}" in js and "location.href='/settings#audio'" in js, "alte Spruenge #audio, #nas, #musik gehen weiter")
check("genbox" not in p and "autobox" not in p and "GEN_GROUPS" not in p, "alte Zweiteilung entfernt")

with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_einstellungen_bereiche")
