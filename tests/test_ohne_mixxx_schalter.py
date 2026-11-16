"""Betrieb ohne Mixxx (Wunsch von Markus, 14.11.2026): Einstellung "Mixxx verwenden" (Standard an). Aus: jede Seite bekommt die
Klasse nomixxx und nomixxx.js, das Wort Mixxx verschwindet aus Texten; der Musik-Rechner nimmt keine Mixxx-Datenbank-Kopie.
An: alles Bild fuer Bild wie bisher (keine Einfuegung in die Seiten)."""
import json
import os
import subprocess
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
import settings  # noqa: E402

p = {x.key: x for x in settings.PARAMS}["mixxx_on"] if hasattr(settings, "PARAMS") else None
src_set = open(os.path.join(ROOT, "pi", "settings.py"), encoding="utf-8").read()
check('P(G_SONG, "mixxx_on", "Mixxx verwenden"' in src_set and '1.0, 0.0, 1.0, 1.0, "switch:Aus|An"),\n    P(G_SONG, "lyrics_auto"' in src_set, "Schalter, Standard an")
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check('show.cfg["mixxx_on"] < 0.5' in wp and 'not self.path.startswith("/help")' in wp and "body.replace(b\"<head>\", MX_OFF_HEAD, 1)" in wp,
      "nur wenn aus, nicht im Handbuch")
check("classList.contains('nomixxx')" in wp and "el.style.display='none'" in wp, "Hauptpanel: Mixxx-Zeile nur fuer den Auto-DJ")

# nomixxx.js: die Textregeln in node pruefen
js = open(os.path.join(ROOT, "pi", "static", "sm", "nomixxx.js"), encoding="utf-8").read()
a, b = js.index("  const PHRASES = ["), js.index("  const HIDE = ")
code = "const fixmod = (() => {\n" + js[a:b] + "\nreturn fix; })();\n" + """
const cases = [
 'Die Liste kommt von der Mixxx-Brücke am Mac (alle 10 Minuten) und bleibt am Pi gespeichert. Liedtext und Show stammen vom Pi.',
 'Der Mac ist nicht erreichbar (läuft der Helfer oder die Mixxx-App?).',
 'Tempo und Beat von Mixxx',
 'Mixxx-Vorhersage',
 'Lieder ohne Tags. In Mixxx die Bibliothek neu einlesen. Fertig.',
 'Mixxx',
 'Musik-Rechner nicht erreichbar: Der Pi erreicht den Musik-Rechner (Light-Butler Helfer bzw. Mixxx-App) nicht.',
 'Ganz ohne das Wort.',
 'Ordner umbenennen oder verschieben (etwa eine CD), Mixxx übernimmt die neuen Pfade',
 'Dateien, die macOS und damit Mixxx am Mac nicht öffnen kann: reparieren'];
console.log(JSON.stringify(cases.map(fixmod)));
"""
r = subprocess.run(["node", "-e", code], capture_output=True, text=True)
out = json.loads(r.stdout or "null") or []
check(len(out) == 10 and not any("Mixxx" in x for x in out), "nirgends mehr Mixxx: " + str(out) + r.stderr[:200])
check(out[0].startswith("Die Liste kommt vom Helfer am Mac") and out[1] == "Der Mac ist nicht erreichbar (läuft der Helfer?)." and out[2] == "Tempo und Beat aus der Liedanalyse",
      "Saetze weg, Wendungen ersetzt")
check(out[3] == "Lied-Vorhersage" and out[4] == "Lieder ohne Tags. Fertig." and out[5] == "" and out[7] == "Ganz ohne das Wort.", "Rest bleibt, nur Mixxx faellt")
check(out[8] == "Ordner umbenennen oder verschieben (etwa eine CD)" and out[9] == "Dateien, die macOS nicht öffnen kann: reparieren", "Nebensatz weg, Rest bleibt: " + str(out[8:]))
check("Light-Butler Helfer" in out[6] and "nicht erreichbar" in out[6], "Hinweis Musik-Rechner bleibt verstaendlich: " + out[6])

SMD = os.path.join(ROOT, "pi", "static", "sm")
mu = open(os.path.join(SMD, "music.js"), encoding="utf-8").read()
check("mxOff(k)" in mu and "if (SM.MXOFF) { $('syncbox').hidden = true; return; }" in mu and mu.count(", mx: 1, ") == 4, "Musik-DB: Spalten, Abgleich")
check(open(os.path.join(SMD, "music.html"), encoding="utf-8").read().count('class="mx') >= 4 and 'class="keep mx"' in open(os.path.join(SMD, "music.html"), encoding="utf-8").read(), "Musik-DB: Knoepfe und Filter nur mit Mixxx")
check("if (SM.MXOFF) for (let i = STEPS.length" in open(os.path.join(SMD, "care.js"), encoding="utf-8").read(), "Datenpflege ohne Mixxx-Schritte")

# Musik-Rechner: Flag aus /api/musik/conf, Helfer laedt dann keine Mixxx-Datenbank
tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = tmp
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import music_serve as ms  # noqa: E402
check(not ms.mixxx_off() and ms.set_mixxx_off(True) and ms.mixxx_off() and not ms.set_mixxx_off(True), "aus: gemerkt")
check(ms.set_mixxx_off(False) and not ms.mixxx_off(), "wieder an")
hp = open(os.path.join(ROOT, "mac", "helper", "helper.py"), encoding="utf-8").read()
check("and not self.mx_off else []" in hp and "Einstellung Mixxx verwenden geaendert" in hp, "Helfer: keine alte Kopie, Wechsel laedt neu")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('out["mx"] = self.show.cfg["mixxx_on"] > 0.5' in api, "Pi sagt es dem Musik-Rechner")
for f in ("nomixxx.js", "core.js", "music.js", "care.js"):
    check(subprocess.run(["node", "--check", os.path.join(SMD, f)]).returncode == 0, f + " ohne Syntaxfehler")
finish("test_ohne_mixxx_schalter")
