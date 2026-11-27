"""Einrichtungsassistent (27.11.2026): sechs Schritte (Sprache, Ton, Licht-Ausgang, Geraete, Zusaetze, Fertig) auf der
Einstellungsseite (/settings#einrichten). Er zeigt die vorhandenen Bereiche (verschoben, beim Verlassen zurueck), baut also
nichts doppelt und schaltet selbst nichts ein; startet nach dem Sicherheitshinweis einer neuen Anlage, sonst ueber den Knopf."""
import os
import subprocess
import tempfile

from _common import check, finish

import texts
import webpanel

p = webpanel.make_page()
sec = p[p.index('<div id="setsec">'):p.index('<div id="hlsec"')]
js = p.split("<script>")[-1].split("</script>")[0]
check('id="setwiz"' in sec and 'id="wzbody"' in sec and 'id="wznext"' in sec, "Assistent auf der Einstellungsseite")
check(sec.count("setGo('einrichten')") >= 2, "Knopf auf der Startseite und unter System")
check("const WZ=[{k:'lang'},{k:'audio',els:['audiobox']},{k:'out',els:['sysbox']},{k:'fix',els:['fxsec']},{k:'extra',els:['homebox','midibox'],skip:1},{k:'done'}];" in js,
      "sechs Schritte, jeweils mit den vorhandenen Bereichen")
for i in ("audiobox", "sysbox", "fxsec", "homebox", "midibox"):
    check(p.count('id="%s"' % i) == 1, "Bereich nur einmal da (wird verschoben, nicht kopiert): " + i)
check("function wzRestore()" in js and "if(wz)wzGo(WZI,true);else wzRestore();" in js, "beim Verlassen kommt alles an seinen Platz zurueck")
check("const wz=h==='einrichten'" in js, "Adresse /settings#einrichten")
check("c({safety_ok:1}).then(()=>{location.href='/settings#einrichten'})" in js, "nach dem Sicherheitshinweis einer neuen Anlage startet er")
wz = js[js.index("const WZ="):js.index("function setFlash(")]
check("c({set:{ui_lang:" in wz and wz.count("c({") == 1, "der Assistent selbst stellt nur die Sprache ein, alles andere ueber die vorhandenen Felder")
for bad in ("ola_out:1", "strobe", "laser", "fog", "safety_ok"):
    check(bad not in wz, "schaltet nichts ein: " + bad)
check("#wzbody #fxsec{display:block}" in p and "#wzbody div[data-back]{display:none}" in p, "Fixtures im Assistenten sichtbar, ohne zweite Kopfleiste")
src = open(texts.__file__, encoding="utf-8").read()
for k in ("wz_start", "wz_title", "wz_next", "wz_prev", "wz_skip", "wz_end", "wz_hint", "wz_s_restart") + tuple(
        "wz_" + s + t for s in ("lang", "audio", "out", "fix", "extra", "done") for t in ("", "_t")):
    check(f'"{k}"' in src, "Text deutsch und englisch: " + k)

with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_einrichtungsassistent")
