"""CD-Assistent (Wunsch von Markus, 09.11.2026): Trackliste aus dem Internet einfuegen, den Dateien eines Ordners zuordnen,
Tags schreiben, nach den Namensregeln umbenennen und auf Wunsch in einen eigenen Ordner unter Compilations verschieben."""
import json
import os
import subprocess
import sys
import tempfile

from _common import PI, ROOT, check, finish

BR = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BR)
import cd_assist  # noqa: E402
import file_check as fc  # noqa: E402
import tag_edit  # noqa: E402

JS = os.path.join(PI, "static", "sm", "cd.js")
check(subprocess.run(["node", "--check", JS], capture_output=True).returncode == 0, "cd.js ohne Fehler")


def node(expr):
    r = subprocess.run(["node", "-e", "global.window={};require(process.argv[1]);const C=window.CD;console.log(JSON.stringify(" + expr + "))", JS],
                       capture_output=True, text=True)
    return json.loads(r.stdout or "null") if r.returncode == 0 else r.stderr[-300:]


HIGH = ("Die Kompilation „Techno Dance Highflyer“ von DJ 7 And The Sound Generators (erschienen 1994 bei LaserLight Digital) enthält "
        "folgende Trackliste: [[1](https://www.discogs.com/x)]\n\n1. Maximum Overdrive – 2 Unlimited\n2. Slave To The Vibe – Aftershock\n"
        "3. Faces – 2 Unlimited\n16. Activ 8 (Come With Me) – Altern-8\n")
p = node("C.parseList(" + json.dumps(HIGH) + ")")
check(isinstance(p, dict) and [r["n"] for r in p["rows"]] == [1, 2, 3, 16] and p["rows"][3] == {"n": 16, "disc": 0, "a": "Activ 8 (Come With Me)", "b": "Altern-8", "dur": 0}
      and p["album"] == "Techno Dance Highflyer" and p["year"] == "1994" and p["performer"] == "DJ 7 And The Sound Generators",
      "Liste wie aus dem Internet: Nummern, Titel – Interpret, Album, Jahr, nachspielender Interpret: " + json.dumps(p, ensure_ascii=False)[:300])
d = node("C.parseList('1\\tThe Bronx–\\tWe Like The Rain\\t5:42\\n3\\tPfaffendorf*–\\tSmile\\t5:01\\n4. Lied - Remix – Wer\\nBest Disco 1998').rows")
check(d == [{"n": 1, "disc": 0, "a": "The Bronx", "b": "We Like The Rain", "dur": 342}, {"n": 3, "disc": 0, "a": "Pfaffendorf", "b": "Smile", "dur": 301},
            {"n": 4, "disc": 0, "a": "Lied - Remix", "b": "Wer", "dur": 0}], "Discogs mit Tabulatoren, Laenge, Sternchen weg; langer Strich vor ' - ': " + json.dumps(d))
check(node("C.titleFirst([{a:'Faces',b:'2 Unlimited'},{a:'Free',b:'Bacon Popper'}], new Set(['2unlimited']))") is True
      and node("C.titleFirst([{a:'2 Unlimited',b:'Faces'}], new Set(['2unlimited']))") is False, "Reihenfolge nach bekannten Interpreten erraten")
m = node("C.assign([{path:'a',track:3,dur:215},{path:'b',track:4,dur:210}], [{n:3,a:'x',b:'y',dur:216},{n:4,a:'x',b:'y',dur:300},{n:5,a:'x',b:'y',dur:0}])"
         ".map(x=>[x.file&&x.file.path,x.ok])")
m2 = node("C.assign([{path:'a',track:1},{path:'x',track:1,elsewhere:true}], [{n:1,a:'x',b:'y',dur:0}]).map(x=>x.file.path)")
check(m2 == ["a"], "gleiche Nummer im Ordner und anderswo: die im Ordner")
check(m == [["a", True], ["b", False], [None, False]], "Zuordnen ueber die Tracknummer; Laenge weit daneben: nur Vorschlag, nicht angehakt " + json.dumps(m))
pl = node("C.plan([{row:{n:3,a:'Faces',b:'2 Unlimited'},file:{path:'a'},ok:true}], {swap:true, cover:true, perf:'DJ 7 And The Sound Generators'}).map(x=>[x.artist,x.title])")
check(pl == [["DJ 7 And The Sound Generators", "Faces (2 Unlimited)"]], "Nachgespielt: Interpret der CD, Original in Klammern hinter dem Titel")

# Doppel-CD (09.11.2026, Future Trance 13 von Discogs): "1-01", "CD 1:", Mitwirkende und Laenge in eigenen Zeilen, "(2)" hinter Namen
DOP = ("„Future Trance Vol. 13“\nJahr: 2000\n\nCD 1:\n1-01\tDarude–\tSandstorm (Radio Edit)\t3:45\n1-04\tSash!–\tWith My Own Eyes (Single Edit)\n"
       "Vocals – Inka\n3:40\n\nCD2:\n2-02\tLange–\tFollow Me (Remix)\nFeaturing – The Morrighan\nRemix – DuMonde\n8:04\n2-06\tSunchild (2)–\tNino Del Sol\t3:54\n")
dp = node("C.parseList(" + json.dumps(DOP) + ")")
check(isinstance(dp, dict) and [(r["disc"], r["n"], r["dur"]) for r in dp["rows"]] == [(1, 1, 225), (1, 4, 220), (2, 2, 484), (2, 6, 234)] and dp["discs"] == 2
      and dp["album"] == "Future Trance Vol. 13" and dp["year"] == "2000" and dp["rows"][1]["b"] == "With My Own Eyes (Single Edit)",
      "Doppel-CD: CD-Nummer, Laenge aus eigener Zeile, Mitwirkende uebergangen, Album und Jahr: " + json.dumps(dp, ensure_ascii=False)[:300])
check(node("C.plan([{row:{a:'Sunchild (2)',b:'Nino'}}], {}).map(x=>x.artist)") == ["Sunchild"], "Discogs-Nummer hinter dem Interpreten weg")
fl = ("[{path:'a',name:'02 - FT - Lange - Follow Me (Remix).mp3',track:2,dur:487},{path:'b',name:'02 - FT - Blank - Culture.mp3',track:2,dur:193},"
      "{path:'c',name:'01 - Darude - Sandstorm.mp3',track:1,dur:227},{path:'x',name:'Techno (3).mp3',track:3,dur:222.5}]")
rw = "[{disc:1,n:2,a:'Blank',b:'Culture',dur:191},{disc:2,n:2,a:'Lange',b:'Follow Me (Remix)',dur:484},{disc:1,n:1,a:'Darude',b:'Sandstorm',dur:225},{disc:1,n:4,a:'Sash',b:'Eyes',dur:220},{disc:2,n:9,a:'Heaven',b:'Cry',dur:215}]"
mm = node("C.assign(" + fl + "," + rw + ").map(x=>[x.file&&x.file.path,x.ok])")
check(mm == [["b", True], ["a", True], ["c", True], ["x", False], [None, False]],
      "gleiche Nummer auf beiden CDs: ueber den Titel; falscher Titel: nur ueber die Laenge mit dem typischen Versatz, nicht angehakt " + json.dumps(mm))

# ganze Bibliothek ohne Ordner (09.11.2026): gleiches Album ("Vol." egal) oder Titel und Interpret
LIB = ("[{path:'/m/U/A/Mauro Picotto - Komodo.mp3',file:'Mauro Picotto - Komodo.mp3',name:'Komodo (Remix)',artist:'Mauro Picotto',dur:200,album:'Best',track:'7'},"
       "{path:'/m/U/C/Techno (2).mp3',file:'Techno (2).mp3',name:'Techno',artist:'Techno',dur:180,album:'Future Trance 13',track:'2'},"
       "{path:'/m/U/X/Andere - Lied.mp3',file:'Andere - Lied.mp3',name:'Lied',artist:'Andere',dur:180,album:'',track:''}]")
lc = node("C.libCandidates(" + LIB + ", [{a:'Mauro Picotto',b:'Komodo (Save A Soul)'}], 'Future Trance Vol. 13', '/m').map(x=>[x.rel,x.local])")
check(lc == [["U/A/Mauro Picotto - Komodo.mp3", False], ["U/C/Techno (2).mp3", True]], "Bibliothek: Titel+Interpret anderswo, gleiches Album ohne 'Vol.', Rest nicht " + json.dumps(lc))
far = node("C.assign([{path:'z',name:'Fremd.mp3',title:'Fremd',dur:200,local:false}], [{n:1,a:'X',b:'Y',dur:200}]).map(x=>x.file)")
check(far == [None], "Lied aus der Bibliothek nie nur ueber die Laenge")

# ---- Mac: Ordner lesen, Plan ausfuehren ----
tmp = tempfile.mkdtemp(prefix="s2l_cd_")
root = os.path.join(tmp, "musik")
src = os.path.join(root, "U-MUSIK", "Artists", "Highflyer", "Highflyer")
os.makedirs(src)
os.makedirs(os.path.join(root, "U-MUSIK", "Artists", "Andere"))
songs = []
for n, name in ((3, "BP Studio Musicians - Faces.mp3"), (4, "Highflyer - Highflyer (2).mp3")):
    f = os.path.join(src, name)
    open(f, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
    tag_edit.write_tags(f, {"title": "Highflyer", "artist": "Highflyer", "track": str(n)})
    songs.append({"path": f, "artist": "Highflyer", "title": "Highflyer", "duration": 200.0 + n, "tracknumber": str(n)})
open(os.path.join(root, "U-MUSIK", "Artists", "Andere", "DJ 7 And The Sound Generators - Faces (2 Unlimited).mp3"), "wb").write(b"\xff\xfb")
for s_ in songs:
    s_["album"] = "Techno Dance Highflyer"
fx = os.path.join(root, "U-MUSIK", "Artists", "Countdown", "Countdown - Maximum Overdrive.mp3")   # gleiche CD, anderer Ordner (09.11.2026)
os.makedirs(os.path.dirname(fx))
open(fx, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
tag_edit.write_tags(fx, {"title": "Maximum Overdrive", "artist": "Countdown", "track": "1", "album": "Techno Dance Highflyer"})
songs.append({"path": fx, "artist": "Countdown", "title": "Maximum Overdrive", "duration": 205.0, "tracknumber": "1", "album": "Techno Dance Highflyer"})
chk = fc.FileCheck(lambda: root, lambda: songs, lambda p: p)
chk.scan()
chk.thread.join(10)
fo = cd_assist.folder(chk, "U-MUSIK/Artists/Highflyer/Highflyer")
check([(x["track"], x["elsewhere"]) for x in fo["files"]] == [(1, True), (3, False), (4, False)] and fo["dir"] == "U-MUSIK/Artists/Highflyer/Highflyer",
      "Ordner: Lieder nach Tracknummer, dazu dasselbe Album aus anderen Ordnern")
check([d for d, _n in cd_assist.dirs(chk)["dirs"]] == ["U-MUSIK/Artists/Countdown", "U-MUSIK/Artists/Highflyer/Highflyer"], "Auswahl der Ordner mit Liedern")
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
res = cd_assist.apply(chk, {"dir": fo["dir"], "move": True, "album": "Techno Dance Highflyer", "albumartist": "DJ 7 And The Sound Generators", "year": "1994",
                            "items": [{"path": songs[0]["path"], "artist": "DJ 7 And The Sound Generators", "title": "Faces (2 Unlimited)", "track": 3, "total": 16},
                                      {"path": songs[1]["path"], "artist": "DJ 7 And The Sound Generators", "title": "U Got To Let The Music? (Cappella)", "track": 4, "total": 16},
                                      {"path": fx, "artist": "DJ 7 And The Sound Generators", "title": "Maximum Overdrive (2 Unlimited)", "track": 1, "total": 16,
                                       "disc": 1, "discs": 2}]})
dest = os.path.join(root, "U-MUSIK", "Compilations", "Techno Dance Highflyer")
got = sorted(os.listdir(dest)) if os.path.isdir(dest) else []
check(got == ["DJ 7 And The Sound Generators - Faces (2 Unlimited) (Techno Dance Highflyer).mp3", "DJ 7 And The Sound Generators - Maximum Overdrive (2 Unlimited).mp3",
              "DJ 7 And The Sound Generators - U Got To Let The Music (Cappella).mp3"]
      and not res["errors"] and res["dir"] == "U-MUSIK/Compilations/Techno Dance Highflyer",
      "eigener Ordner unter Compilations, Namen nach den Regeln, schon vergebener Name mit Album: " + str(got) + str(res["errors"]))
t = tag_edit.read_tags(os.path.join(dest, "DJ 7 And The Sound Generators - U Got To Let The Music (Cappella).mp3"))["fields"]
check(t.get("disc") in ("", None), "ohne CD-Nummer in Datei und Liste: keine CD-Nummer geschrieben " + str(t.get("disc")))
check(t["title"] == "U Got To Let The Music? (Cappella)", "Fragezeichen bleibt im Tag, nur der Dateiname ohne: " + t["title"])
check(t["artist"] == "DJ 7 And The Sound Generators" and t["album"] == "Techno Dance Highflyer" and t["track"] == "4/16" and t["year"] == "1994"
      and t["albumartist"] == "DJ 7 And The Sound Generators", "Tags geschrieben: " + str({k: t[k] for k in ("artist", "title", "album", "track", "year")}))
q = open(fc.FileCheck.queue_path(), encoding="utf-8").read().splitlines()
tm = tag_edit.read_tags(os.path.join(dest, "DJ 7 And The Sound Generators - Maximum Overdrive (2 Unlimited).mp3"))["fields"]
check(tm["disc"] == "1/2" and tm["track"] == "1/16", "Doppel-CD: CD-Nummer 1/2 im Tag")
check(len(q) == 3 and q[0].split("\t")[0] == songs[0]["path"] and "/Compilations/Techno Dance Highflyer/" in q[0], "Umbenennungen fuer Mixxx gemerkt")
check(not os.path.exists(src) and not os.path.exists(fx), "alter Ordner leer: weg; Lied aus dem anderen Ordner mitgenommen")
fresh = fc.FileCheck(lambda: root, lambda: songs, lambda p: p)
try:
    cd_assist.apply(fresh, {"dir": "x", "items": [{"path": "/nicht/da.mp3", "artist": "A", "title": "B"}]})
except ValueError:
    pass
check(fresh.state == "ready", "ohne vorherige Pruefung: der Mac prueft selbst und schreibt dann (Fehlerbericht 09.11.2026)")
# Live-CD als "Disc 2" bei der Studio-CD (09.11.2026): einzelne CD in der Liste, Datei hat CD 2/2 -> 1/1
lv = os.path.join(root, "U-MUSIK", "Artists", "Andere", "Live 20000.mp3")
open(lv, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
tag_edit.write_tags(lv, {"title": "20.000 Meilen", "artist": "X", "disc": "2/2"})
songs.append({"path": lv, "artist": "X", "title": "20.000 Meilen", "duration": 271.0, "tracknumber": "2", "album": "Nicht"})
lr = cd_assist.apply(fresh, {"dir": "U-MUSIK/Artists/Andere", "album": "Live", "items": [{"path": lv, "artist": "X", "title": "20.000 Meilen", "track": 2, "total": 15}]})
lt = tag_edit.read_tags(os.path.join(root, "U-MUSIK", "Artists", "Andere", "X - 20.000 Meilen.mp3"))["fields"]
check(not lr["errors"] and lt["disc"] == "1/1" and lt["album"] == "Live", "einzelne CD: alte CD-Nummer 2/2 wird 1/1 " + str(lr["errors"]) + str(lt.get("disc")))
# Ordner umbenennen (Wunsch 09.11.2026: "1998 - Studio/Disc 2" ist die Live-CD, "1999 - Live" daneben)
xd = os.path.join(root, "U-MUSIK", "Artists", "XN", "1998 - Studio", "Disc 2")
os.makedirs(xd)
open(os.path.join(root, "U-MUSIK", "Artists", "XN", "1998 - Studio", "studio.mp3"), "wb").write(b"\xff\xfb")
xa, xb = os.path.join(xd, "a (Live).mp3"), os.path.join(xd, "b.mp3")
for f in (xa, xb):
    open(f, "wb").write(b"\xff\xfb")
xa_old = os.path.join(xd, "01 - a.mp3")                        # Mixxx kennt a noch unter dem alten Namen (wartet in offen.tsv)
xsongs = [{"path": xa_old}, {"path": xb}]
loc = {xa_old: xa, xb: xb}
xc = fc.FileCheck(lambda: root, lambda: xsongs, lambda p: loc.get(p))
qp = fc.FileCheck.queue_path()
open(qp, "w", encoding="utf-8").write("/x/alt.mp3\t/x/neu.mp3\n" + xa_old + "\t" + xa + "\n")
rr = cd_assist.rename_dir(xc, "U-MUSIK/Artists/XN/1998 - Studio/Disc 2", "U-MUSIK/Artists/XN/1999 - Live")
nd = os.path.join(root, "U-MUSIK", "Artists", "XN", "1999 - Live")
ql = open(qp, encoding="utf-8").read().splitlines()
check(rr["dir"] == "U-MUSIK/Artists/XN/1999 - Live" and rr["songs"] == 2 and sorted(os.listdir(nd)) == ["a (Live).mp3", "b.mp3"] and not os.path.exists(xd)
      and os.path.exists(os.path.join(root, "U-MUSIK", "Artists", "XN", "1998 - Studio", "studio.mp3")), "Ordner verschoben, Studio bleibt " + str(rr))
check([x.replace(os.sep, "/") for x in ql] == [x.replace(os.sep, "/") for x in ["/x/alt.mp3\t/x/neu.mp3", xa_old + "\t" + os.path.join(nd, "a (Live).mp3"), xb + "\t" + os.path.join(nd, "b.mp3")]],
      "Mixxx: wartende Umbenennung zeigt gleich auf den neuen Ordner, das andere Lied neu vorgemerkt " + str(ql))
nf = cd_assist.folder(xc, "U-MUSIK/Artists/XN/1999 - Live")
check(sorted(x["name"] for x in nf["files"] if not x["elsewhere"]) == ["a (Live).mp3", "b.mp3"]
      and "U-MUSIK/Artists/XN/1999 - Live" in [d_ for d_, _n in cd_assist.dirs(xc)["dirs"]],
      "nach dem Umbenennen findet die Seite die Lieder im neuen Ordner, obwohl Mixxx noch den alten Pfad kennt (Fehlerbericht: 0 Lieder) " + str(nf["files"]))
for bad, why in (("U-MUSIK/Artists/XN/1998 - Studio", "gibt es schon"), ("U-MUSIK/Artists/XN/A?B", "ungültig"), ("../raus", "ungültig"),
                 ("U-MUSIK/Artists/XN/1999 - Live/innen", "in sich selbst")):
    try:
        cd_assist.rename_dir(xc, "U-MUSIK/Artists/XN/1999 - Live", bad)
        check(False, "Ordner umbenennen sollte scheitern: " + bad)
    except ValueError as e:
        check(why in str(e), "Ordner umbenennen abgelehnt (" + why + "): " + str(e))
try:
    cd_assist.rename_dir(xc, "U-MUSIK/gibtsnicht", "U-MUSIK/x")
    check(False, "fehlender Ordner")
except ValueError as e:
    check("nicht gefunden" in str(e), "fehlender Ordner: " + str(e))
ojs = open(os.path.join(PI, "static", "sm", "ordner.js"), encoding="utf-8").read()
ohtml = open(os.path.join(PI, "static", "sm", "ordner.html"), encoding="utf-8").read()
check('op") == "rename_dir"' in open(os.path.join(BR, "music_serve.py"), encoding="utf-8").read() and "op: 'rename_dir'" in ojs
      and 'data-title="h_folders"' in ohtml and 'path == "/musik/ordner"' in open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
      and "href: '/musik/ordner', tool: true" in open(os.path.join(PI, "static", "sm", "care.js"), encoding="utf-8").read()
      and "rename_dir" not in open(JS, encoding="utf-8").read(),
      "Ordner umbenennen: eigene Seite in der Datenpflege (nicht im CD-Assistenten, Wunsch 09.11.2026), Route am Mac")
# Abspiel-Leiste: jede Seite mit Vorhoeren hat unten Play/Pause, Position und Lautstaerke (Wunsch 09.11.2026)
SMD = os.path.join(PI, "static", "sm")
for fn in sorted(os.listdir(SMD)):
    if fn.endswith(".js") and fn not in ("core.js", "autodj.js"):
        t = open(os.path.join(SMD, fn), encoding="utf-8").read()
        if "new Audio()" in t:
            check("SM.playBar(" in t or "ppos" in t, fn + ": Vorhoeren mit Leiste unten (springen, Lautstaerke)")
core = open(os.path.join(SMD, "core.js"), encoding="utf-8").read()
check("SM.playBar = " in core and "class=\"ppos\"" in core and "musikvol" in core, "gemeinsame Abspiel-Leiste in core.js")
ms = open(os.path.join(BR, "music_serve.py"), encoding="utf-8").read()
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
html = open(os.path.join(PI, "static", "sm", "cd.html"), encoding="utf-8").read()
check('u.path == "/cd"' in ms and 'urlparse(self.path).path == "/cd"' in ms and 'path == "/musik/cd"' in api and 'data-title="h_cd"' in html
      and '"/musik/cd"' in open(os.path.join(PI, "static", "sm", "check.html"), encoding="utf-8").read(), "Routen, Seite mit Kopfleiste, Einstieg aus Dateien pruefen")
for inst in ("mac/mixxx_bridge/install_launcher.sh", "mac/helper/install_helper.sh"):
    check("cd_assist.py" in open(os.path.join(ROOT, inst), encoding="utf-8").read(), inst + " kopiert cd_assist.py")
check("width: auto; max-width: none;" in html and "table-layout: fixed" in html and "data-play" in open(JS, encoding="utf-8").read(),
      "Seite ueber die ganze Breite (nicht 560 px wie ein Dialog), feste Spalten, Vorhoeren (09.11.2026)")
js2 = open(JS, encoding="utf-8").read()
check("async function ensureCheck()" in js2 and "mac('/check', { op: 'scan' })" in js2 and "Prüfe und schreibe" in js2
      and "href: '/musik/cd'" in open(os.path.join(PI, "static", "sm", "care.js"), encoding="utf-8").read(),
      "startet die Dateipruefung selbst, Schreiben erst danach; eigener Schritt in der Datenpflege (09.11.2026)")
check("$('list').value = ''; parsed = null;" in open(JS, encoding="utf-8").read(), "nach dem Schreiben ohne Fehler: Eingaben leer fuer die naechste CD")
# Fehlerbericht 09.11.2026 (Grand Prix 1994): Dateien bis 7 s laenger, "Woaßt" statt "Woasst", eine Datei mit falscher Nummer (1 statt 11)
gp = node("C.assign(["
          "{path:'g1',name:'GP - GP (1).mp3',title:'GP',track:1,dur:178.8,local:true},"
          "{path:'h',name:'Hahnenkamm Trio - Ja Du Woaßt, Daß I Di Mag.mp3',title:'Ja Du Woaßt, Daß I Di Mag',track:1,dur:171.4,local:true},"
          "{path:'g4',name:'GP - GP (4).mp3',title:'GP',track:4,dur:165,local:true},"
          "{path:'g12',name:'GP - GP (12).mp3',title:'GP',track:12,dur:180.9,local:true}],"
          "[{n:1,a:'Die Kolibris',b:'Kleiner Kolibri',dur:173},{n:4,a:'Ernie & Maria',b:'Musik',dur:158},"
          "{n:11,a:'Hahnenkamm Trio',b:'Ja, Du Woasst, Dass I Di Mag',dur:168},{n:12,a:'Horst',b:'Drum',dur:176}]).map(x=>[x.file&&x.file.path,x.ok])")
check(gp == [["g1", True], ["g4", True], ["h", True], ["g12", True]], "Nummer gilt bis 10 s Laenge, ß = ss, falsche Nummer ueber den Titel richtig " + json.dumps(gp))
al = node("[C.parseList('GRAND PRIX Der Volkstümlichen Musik 1994\\nGenre: Pop, Folk\\nYear: 1994\\n1 Die Kolibris - Kleiner Kolibri\\t2:53'),"
           "C.parseList('Album: Best Of X\\nGenre: Pop\\n1. A – B'), C.parseList('Tracklist:\\n1. A – B')].map(p=>[p.album,p.year])")
check(al == [["GRAND PRIX Der Volkstümlichen Musik 1994", "1994"], ["Best Of X", ""], ["", ""]],
      "Album aus der ersten Zeile ohne Anfuehrungszeichen, aus 'Album:'; 'Genre:'/'Tracklist:' nicht (Fehlerbericht 09.11.2026) " + json.dumps(al, ensure_ascii=False))
# Musical Stars (09.11.2026): "TRACKLISTING CD 1", Haendler-Zusaetze, Klammern in Grossbuchstaben, fremdes Album nur Vorschlag
MS = ("MUSICAL STARS Volume 1\\nJahre 2005\\nTRACKLISTING CD 1\\n01 Felix Martin - Totale Finsternis (TANZ DER VAMPIRE)\\n"
      "10 Pia Douwes – New Hampshire Nights (AN UNFINISHED SONG) RARITÄT!\\nTRACKLISTING CD 2\\n"
      "03 Annika Bruhns – Waterloo (MUSICALSTARS SINGEN ABBA-HITS)\\n11 Maik Lohse – THE SHADES OF NIGHT (ELISABETH) RAR: DIE SCHATTEN\\n"
      "Hidden Track: Martin Schäffner - Mondballade (LETTERLAND)")
ms = node("C.parseList('" + MS + "').rows.map(r=>[r.disc,r.n,r.b])")
check(ms == [[1, 1, "Totale Finsternis (Tanz Der Vampire)"], [1, 10, "New Hampshire Nights (An Unfinished Song)"],
             [2, 3, "Waterloo (Musicalstars Singen ABBA-Hits)"], [2, 11, "The Shades Of Night (Elisabeth)"]],
      "TRACKLISTING CD n, Zusaetze weg, Grossbuchstaben normal " + json.dumps(ms, ensure_ascii=False))
aw = node("C.assign([{path:'own',name:'03 - MS - Kröger - Winner.mp3',title:'Winner',track:3,dur:160,local:true},"
          "{path:'other',name:'05 - Hits - Bruhns - Waterloo.mp3',title:'Waterloo',track:5,dur:170,local:false}],"
          "[{disc:2,n:3,a:'Annika Bruhns',b:'Waterloo',dur:0}]).map(x=>[x.file&&x.file.path,x.ok])")
check(aw == [["own", True]], "gleiches Album mit passender Nummer vor Titel aus fremdem Album " + json.dumps(aw))
ag = node("C.albumGuess([{file:{album:'Musical Stars Mit X'},why:'Titel'},{file:{album:'Musical Stars Mit X'},why:'Titel (anderes Album)'},"
          "{file:{album:'Musical Stars Mit X'},why:'Titel und Länge'},{file:{album:'Hits'},why:'Titel'},{file:null,why:''}], 6)")
check(ag == "Musical Stars Mit X", "Album aus den Titeltreffern erraten (Musical Stars, 09.11.2026): " + json.dumps(ag))
check("CD.albumGuess(m, parsed.rows.length)" in open(JS, encoding="utf-8").read(), "Seite nimmt das erratene Album und ordnet neu zu")
# Xavier Naidoo (09.11.2026): CD eines Interpreten, "1 Titel – 4:08", Interpret aus der ersten Zeile
XN = "Xavier Naidoo Nicht Von Dieser Welt\\nJahr 1998\\n\\n1 Seid ihr mit mir? – 4:08\\n7 Freisein (Nachtschicht am Meer) – 5:20"
xn = node("(()=>{const p=C.parseList('" + XN + "');const sp=C.splitArtist(p.album,new Set(['xaviernaidoo']));"
          "return [p.rows.map(r=>[r.n,r.b,r.dur,!!r.solo]),sp,p.year,C.plan([{row:p.rows[0]}],{artist:sp[0]}).map(x=>[x.artist,x.title])]})()")
check(xn == [[[1, "Seid ihr mit mir?", 248, True], [7, "Freisein (Nachtschicht am Meer)", 320, True]], ["Xavier Naidoo", "Nicht Von Dieser Welt"], "1998",
             [["Xavier Naidoo", "Seid ihr mit mir?"]]], "nur Titel mit Laenge, Interpret aus der ersten Zeile abgetrennt " + json.dumps(xn, ensure_ascii=False))
# Xavier Naidoo Live (09.11.2026): Ordnerzeile, "Interpret:/Album:/Jahr:", "2. 20.000 Meilen" ist keine CD 2, Interpret in jeder Zeile
XL = ("U-MUSIK/Artists/Xavier Naidoo/1998 - Nicht Von Dieser Welt/Disc 2\\nInterpret: „Xavier Naidoo“\\nAlbum: „Live“\\nJahr: 1999\\n\\nCD1\\n"
      "1. Seid Ihr mit mir? (5:23)\\n2. 20.000 Meilen (4:31)")
xl = node("(()=>{const p=C.parseList('" + XL + "');return [p.dir,p.artist,p.album,p.year,p.rows.map(r=>[r.disc,r.n,r.b,r.dur])]})()")
check(xl == ["U-MUSIK/Artists/Xavier Naidoo/1998 - Nicht Von Dieser Welt/Disc 2", "Xavier Naidoo", "Live", "1999",
             [[0, 1, "Seid Ihr mit mir?", 323], [0, 2, "20.000 Meilen", 271]]], "Angaben mit Namen und Ordner aus der Liste " + json.dumps(xl, ensure_ascii=False))
rep = node("C.assign([{path:'x',name:'Xavier Naidoo - Führ Mich Ans Licht (Disc 2).mp3',title:'Führ Mich Ans Licht',track:4,dur:313,local:true}],"
           "C.withArtist([{n:4,a:'',b:'Gute Aussichten',dur:312,solo:true},{n:5,a:'',b:'Mich belogen',dur:338,solo:true}],'Xavier Naidoo')).map(x=>x.why)")
check(rep == ["Nummer und Länge", ""], "Interpret in jeder Zeile zaehlt nicht als Titeltreffer " + json.dumps(rep, ensure_ascii=False))
sure = node("[C.parseList('" + XL + "').albumSure, C.parseList('MUSICAL STARS Volume 1\\n1 A - B').albumSure, C.parseList('„Future Trance Vol. 13“\\n1-01 A – B').albumSure]")
check(sure == [True, False, True], "ausdruecklich genanntes Album wird nicht durch das erratene ersetzt " + json.dumps(sure))
check("if (parsed) parsed.albumSure = true;" in open(JS, encoding="utf-8").read(), "selbst getipptes Album wird nicht mehr erraten")
check("parsed.albumSure ? '' : CD.albumGuess" in open(JS, encoding="utf-8").read(), "Seite haelt sich daran")
finish("test_cd_assistent")
