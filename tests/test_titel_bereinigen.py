"""Titel bereinigen (Wunsch von Markus, 07.11.2026): Nummern am Anfang des Titels erkennen, sichere vorab anhaken, unsichere
hinterfragen; geschrieben werden nur Titel und, wenn frei, der Track (titles.js, mit node gerechnet)."""
import json
import os
import subprocess

from _common import PI, check, finish

import texts
import webpanel

JS = os.path.join(PI, "static", "sm", "titles.js")
CASES = [["01 - Highway to Hell", ""], ["3. Lied", ""], ["(07) Lied", ""], ["7 - Lied", "7"], ["12_Lied", ""], ["05 Lied", ""],
         ["99 Luftballons", ""], ["7 Years", ""], ["5. Sinfonie", ""], ["4 - Lied", "9"], ["1.5 Mix", ""], ["10:30 Uhr", ""],
         ["Lied 01", ""], ["1999", ""], ["(1 Mix) Lied", ""], ["2 - 4", ""], ["0 - Intro", ""], ["8 Lied", "8"], ["68 (Original Mix)", ""]]
code = ("const T=require(process.argv[1]);const C=JSON.parse(process.argv[2]);"
        "console.log(JSON.stringify({a:C.map(c=>T.analyse(c[0],c[1])),f:[T.fields(T.analyse('01 - X',''),'',''),"
        "T.fields(T.analyse('01 - X','3'),'3','Neu')]}))")
out = json.loads(subprocess.run(["node", "-e", code, JS, json.dumps(CASES)], capture_output=True, text=True).stdout)
a = dict(zip([c[0] + "|" + c[1] for c in CASES], out["a"]))
g = lambda t, tr="": a[t + "|" + tr]
for t in ("01 - Highway to Hell", "(07) Lied", "12_Lied", "05 Lied"):
    check(g(t) and g(t)["sure"], f"sicher: {t}")
check(g("01 - Highway to Hell")["clean"] == "Highway to Hell" and g("01 - Highway to Hell")["n"] == 1, "Nummer weg, Titel bleibt")
check(g("7 - Lied", "7")["sure"] and "Track" in g("7 - Lied", "7")["why"], "passt zum Track-Tag")
check(g("8 Lied", "8")["sure"], "nur Leerzeichen, aber Track-Tag gleich: sicher")
for t in ("99 Luftballons", "7 Years", "5. Sinfonie", "3. Lied"):
    check(g(t) and not g(t)["sure"], f"hinterfragen: {t}")
check(not g("4 - Lied", "9")["sure"] and "9" in g("4 - Lied", "9")["why"], "Track-Tag widerspricht: hinterfragen")
check(not g("0 - Intro")["sure"], "Nummer 0: hinterfragen")
for t in ("1.5 Mix", "10:30 Uhr", "Lied 01", "1999", "(1 Mix) Lied", "2 - 4", "68 (Original Mix)"):
    check(g(t) is None, f"keine Tracknummer: {t}")
check(out["f"][0] == {"title": "X", "track": "1"}, "Track frei: Nummer kommt in den Track")
check(out["f"][1] == {"title": "Neu"}, "Track belegt: bleibt, eigener neuer Titel zaehlt")

# Internet: gibt es den Titel mit der Zahl so? (Wunsch 07.11.2026, echte Antwort von MusicBrainz/iTunes zu "10 Nackte Friseusen")
SUG = [{"artist": "Mickie Krause & Knossi", "title": "10 nackte Friseusen (Silberhochzeits-Edition)"}, {"artist": "Mickie Krause", "title": "10 nackte Friseusen"}]
code2 = ("const T=require(process.argv[1]);const S=JSON.parse(process.argv[2]);console.log(JSON.stringify(["
         "T.netMatch('10 Nackte Friseusen','Mickie Krause',S),T.netMatch('10 Nackte Friseusen','Mickie Krause',[S[0]]),"
         "T.netMatch('10 Nackte Friseusen','Andere Band',S),T.netMatch('01 Lied','X',[{artist:'X',title:'Lied'}]),T.netMatch('10 Nackte Friseusen','Mickie Krause',[])]))")
nm = json.loads(subprocess.run(["node", "-e", code2, JS, json.dumps(SUG)], capture_output=True, text=True).stdout)
check(nm == [True, True, False, False, False], f"Internet: gleicher Titel samt Zahl beim Interpreten zaehlt, auch mit Zusatz; anderer Interpret, nur ohne Zahl oder nichts gefunden nicht ({nm})")
tjs = open(JS, encoding="utf-8").read()
check("r.a && !r.a.sure && !r.net" in tjs and "src: ok ? 'netz' : 'nein'" in tjs and "music + '/lookup?p='" in tjs,
      "nur die unsicheren nachsehen, Ergebnis am Pi merken (nicht jedes Mal neu fragen)")

# Seite eingebunden: Route, Kopfleiste, Knopf in der Musik-Datenbank, Texte
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
music = open(os.path.join(PI, "static", "sm", "music.html"), encoding="utf-8").read()
check('"/musik/titel"' in api and ("href: '/musik/titel'" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi", "static", "sm", "care.js"), encoding="utf-8").read()), "Route und Knopf in der Musik-Datenbank")
check("h_titles" in webpanel.NAV_KEYS and texts.DEFAULTS["h_titles"][0] == "Titel bereinigen" if hasattr(texts, "DEFAULTS") else "h_titles" in webpanel.NAV_KEYS,
      "Titel im Menue")
mjs = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check('id="bsame"' in music and "sameOn && !sameTA(r)" in mjs, "Musik-Datenbank: Knopf Titel = Interpret filtert")
check("document.addEventListener('visibilitychange', wake)" in mjs and "e.persisted" in mjs, "Musik-Datenbank: beim Wiederanzeigen (iPad, Zurueckblaettern) neu nachfragen")
check('id="blong"' in music and 'id="bnomp3"' in music and "longOn && !((r.dur || 0) > 600)" in mjs and "nomp3On && twin(r)" in mjs,
      "Musik-Datenbank: Filter ueber 10 min und nicht MP3")
tej = open(os.path.join(PI, "static", "sm", "tagedit.js"), encoding="utf-8").read()
check("SM.peaksFor = async" in tej and "const k = 18" in tej and "peaks = await SM.peaksFor(music, q, 90)" in tej and "decoded.partial = true" in tej,
      "Cover erzeugen bei sehr langen Dateien: Stuecke ueber die Laenge statt der ganzen Datei, Shazam aus der Mitte")
check(subprocess.run(["node", "--check", JS]).returncode == 0, "node --check")
finish("test_titel_bereinigen")
