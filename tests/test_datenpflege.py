"""Datenpflege (Wunsch von Markus, 08.11.2026, Seite /musik/pflege): alle Werkzeuge zum Bereinigen als Rezept in sinnvoller
Reihenfolge, mit Zahl offener Faelle je Schritt; die Seite zaehlt nur und fuehrt zu den Werkzeugen."""
import os
import re
import subprocess

from _common import PI, check, finish

SM = os.path.join(PI, "static", "sm")
js = open(os.path.join(SM, "care.js"), encoding="utf-8").read()
html = open(os.path.join(SM, "care.html"), encoding="utf-8").read()
music = open(os.path.join(SM, "music.html"), encoding="utf-8").read()
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()

ids = re.findall(r"\bid: '(\w+)', (?:mx: 1, )?t: '", js)
check("V.dupes = keepLast('dupes'," in js and "V.folder = keepLast('folder'," in js and "const LAST_KEY = 'pflege_letzte';" in js,
      "Doppelte und Ordnerbilder behalten die letzte Zahl, solange der Mac neu rechnet (Fehlerbericht 09.11.2026: gruen, dann blau)")
_wp = open(os.path.join(PI, "webpanel.py"), encoding="utf-8").read()
check("if(s.on&&left<=0&&!(s.work||[]).length)k.hidden=true;" in _wp, "Spur-Kurven fertig: kein Knopf Anhalten mehr")
check("unit: 'CDs', wait: 'noch nicht geprüft', tool: true" in js and "href: '/musik/ordner', tool: true" in js and "if (!stt.tool) k++;" in js,
      "CD-Assistent und Ordner umbenennen sind Werkzeuge mit Raedchen, ohne Nummer (Wunsch 09.11.2026)")
check(ids == ["backup", "import", "fehlt", "junk", "empty", "defekt", "folders", "merge", "lose", "mp3", "dupes", "mixxx", "titles", "fnametags", "cd", "same", "folder", "tags", "genres", "energy", "short", "changed", "names", "samename", "mirror"],
      f"Reihenfolge: Sicherung, Import, Fehlt mir (14.11.2026), Muell, Leere, Beschaedigte (14.11.2026), Ordner, lose Album-Lieder (14.11.2026), MP3, Doppelte, Mixxx aufraeumen, Titel, Titel=Interpret, Ordnerbilder, Tags, Geaenderte, Dateinamen ({ids})")
for href in ("/musik/pruefen?t=muell", "/musik?f=nichtmp3", "/musik/doppelte", "/musik/titel", "/musik?f=same", "/musik/vorschlaege?f=ordner",
             "/musik/vorschlaege", "/musik/pruefen?t=namen", "/musik/vorab"):
    check(href in js, "fuehrt zu " + href)
check("mac('/check')" in js and "mac('/folderart')" in js and "mac('/changed')" in js and "mac('/dupes')" in js and "mac('/sync')" in js,
      "Zahlen vom Mac (Pruefung, Ordnerbilder, Geaenderte, Doppelte, Abgleich Mixxx)")
check("t.cv === 0" in js and "!tw(t)" in js, "Zahlen vom Pi (ohne Cover, nicht MP3 ohne MP3-Schwester)")
check("localStorage.setItem(DONE_KEY" in js and "manual: true" in js, "Sicherung und Mixxx aufraeumen von Hand abhaken")
check("method: 'POST'" in js and "op: 'm3u'" in js and "op: 'clear'" in js, "Geaenderte → Mixxx direkt aus der Datenpflege")
check('id="bcare" href="/musik/pflege"' in music and not re.search(r'<a class="btn" href="/musik/(doppelte|pruefen|titel|vorschlaege)"', music),
      "Musik-DB: ein Knopf Datenpflege statt vieler einzelner")
check('path == "/musik/pflege"' in api and 'data-title="h_care"' in html, "Seite am Pi, Kopfleiste")
mj = open(os.path.join(SM, "music.js"), encoding="utf-8").read()
check("fq === 'nichtmp3'" in mj and "fq === 'same'" in mj, "Musik-DB versteht die Spruenge (f=nichtmp3, f=same)")
check("tq = new URLSearchParams" in open(os.path.join(SM, "check.js"), encoding="utf-8").read()
      and "get('f') === 'ordner'" in open(os.path.join(SM, "autotag.js"), encoding="utf-8").read(), "Dateien pruefen und Tag-Vorschlaege oeffnen den richtigen Teil")
check(subprocess.run(["node", "--check", os.path.join(SM, "care.js")], capture_output=True).returncode == 0, "care.js ohne Fehler")
# Fehlerbericht 08.11.2026: Datenpflege zeigte "Titel bereinigen 48", die Seite 0 (So lassen und Ausnahmen zaehlten mit)
cj = open(os.path.join(PI, "static", "sm", "care.js"), encoding="utf-8").read()
check("op: 'title_kept'" in cj and "hasNr(t.name)" in cj, "Titel: So lassen und dieselben Ausnahmen wie die Seite")
nd = subprocess.run(["node", "-e", "const s=require('fs').readFileSync(process.argv[1],'utf8');const a=s.indexOf('  const RX_NR');const b=s.indexOf('\\n  }',s.indexOf('function hasNr'))+4;eval(s.slice(a,b));"
                     "console.log(['01 - Lied','68 (Original Mix)','8.00 Am','20.000 Meilen','99 Luftballons'].map(hasNr).join(','))",
                     os.path.join(PI, "static", "sm", "care.js")], capture_output=True, text=True)
check(nd.stdout.strip() == "true,false,false,false,true", "Ausnahmen wie Titel bereinigen: " + (nd.stdout.strip() or nd.stderr[-200:]))
# Wunsch 08.11.2026: WAV/MP4 mit MP3-Schwester nicht bemaengeln; Datenmuell nicht gruen, solange Dateinamen offen sind
core = open(os.path.join(PI, "static", "sm", "core.js"), encoding="utf-8").read()
nd = subprocess.run(["node", "-e", "const s=require('fs').readFileSync(process.argv[1],'utf8');const SM={};const a=s.indexOf('  SM.mp3Twin');const b=s.indexOf('  };',a)+4;eval(s.slice(a,b));"
                     "const tr=[{path:'/m/A/x - THX Intro.mp3',artist:'X',name:'THX Intro'},{path:'/m/A/x - Thx.wav',artist:'',name:'THX Intro'},"
                     "{path:'/m/B/Lied.mp4',artist:'Y',name:'Lied'},{path:'/m/C/Lied.wav',artist:'Z',name:'Anders'},{path:'/m/C/lied.MP3',artist:'',name:''},{path:'/m/D/Song.wav',artist:'Y',name:'Lied'}];"
                     "const tw=SM.mp3Twin(tr);console.log(tr.map(tw).join(','))", os.path.join(PI, "static", "sm", "core.js")], capture_output=True, text=True)
check(nd.stdout.strip() == "true,true,false,true,true,false", "MP3-Schwester: gleicher Ordner+Name, gleicher Ordner+Titel; sonst bemaengeln: " + (nd.stdout.strip() or nd.stderr[-200:]))
check("SM.mp3Twin(tr)" in js and "twin(r)" in open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read(), "Datenpflege und Musik-DB-Filter nutzen dieselbe Regel")
cj = open(os.path.join(PI, "static", "sm", "care.js"), encoding="utf-8").read()
check("extra: () =>" in cj and "cnt bad" in cj and "!stt.ex ? ' ok'" in cj, "Datenmuell rot, solange Dateinamen offen sind")
care_html = open(os.path.join(SM, "care.html"), encoding="utf-8").read()
check("libprog" not in open(os.path.join(SM, "music.html"), encoding="utf-8").read(), "Musik-Datenbank ohne die alten Statuszeilen (Fehlerbericht 11.11.2026: blieb sichtbar)")
check("nhref: '/musik?f=nocover'" in js and "if (fq === 'nocover') $('fnocv').checked = true" in open(os.path.join(SM, "music.js"), encoding="utf-8").read()
      and "/musik?f=nocover" in open(os.path.join(SM, "autotag.html"), encoding="utf-8").read(),
      "Zahl ohne Cover fuehrt zu genau diesen Liedern (Fehlerbericht 11.11.2026)")
check('id="libstat"' in care_html and "SM.libStatusHtml(lastLib" in js, "Stand der Liedliste in der Datenpflege (11.11.2026)")
finish("test_datenpflege")
