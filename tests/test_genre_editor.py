"""Genre-Editor (Wunsch von Markus, 08.11.2026, Seite /musik/genres): Genres zaehlen, Vorschlaege zum Zusammenlegen,
Umbenennen in allen betroffenen MP3s (nur das Genre-Feld), Protokoll mit Zuruecknehmen, Hausliste, Genre fuellen vom
Interpreten, vom Ordner und aus dem Internet (Samples aussen vor), Licht-Stil geht mit."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from _common import PI, ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, PI)
import genre_edit as ge  # noqa: E402
import music_serve as ms  # noqa: E402
from genre_style import GenreStyles  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_genre_")
os.environ["S2L_DATA"] = tmp
root = os.path.join(tmp, "musik")
files = {}


def song(rel, artist, title, genre):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"\xff\xfb")
    files[p] = genre
    return {"path": p, "artist": artist, "title": title, "genre": genre}


lib = [song("U/Artists/A/a1.mp3", "Alpha", "Eins", "EDM"), song("U/Artists/A/a2.mp3", "Alpha", "Zwei", "EDM"),
       song("U/Artists/A/a3.mp3", "Alpha", "Drei", "Edm"), song("U/Artists/A/a4.mp3", "Alpha", "Vier", "Other"),
       song("U/Artists/B/b1.mp3", "Beta", "Eins", "Eurodance; Other"), song("U/Artists/B/b2.mp3", "Beta", "Zwei", "Dance"),
       song("U/Artists/B/b3.mp3", "Beta", "Drei", "Dance"), song("U/Artists/B/b4.mp3", "Beta", "Vier", "Dance"),
       song("U/Artists/B/b5.mp3", "Beta", "Fuenf", "Dance"), song("U/Artists/B/b6.mp3", "Beta", "Sechs", "Dance"),
       song("U/Artists/C/c1.mp3", "Gamma", "Eins", "Classical Other"), song("U/Artists/C/c2.mp3", "Gamma", "Zwei", "Miscellaneous"),
       song("U/Artists/D/d1.mp3", "Delta", "Eins", ""), song("U/Artists/D/d2.flac", "Delta", "Zwei", "Swing"),
       song("SAMPLES/Kick/k1.mp3", "", "Kick", ""), song("U/Artists/E/e1.mp3", "Epsilon", "Eins", ""),
       song("U/Artists/D/d3.mp3", "Delta", "Drei", "Swing")]   # seit 09.11.2026 zaehlen nur MP3s: Swing auch als MP3
lib += [song(f"KLASSIK/Artists/K{i}/k.mp3", f"Komponist {i}", "Sinfonie", "Klassik") for i in range(12)]
lib.append(song("KLASSIK/Artists/X/x.mp3", "Unbekannt", "Etwas", ""))
written, noted = [], []


def fake_write(f, fields):
    written.append((f, dict(fields)))
    files[f] = fields["genre"]
    for r in lib:
        if r["path"] == f:
            r["genre"] = fields["genre"]          # wie lib_with_tags: geschriebene Tags gelten sofort


ed = ge.GenreEditor(lambda: lib, lambda p: p if os.path.exists(p) else None, lambda: root, write=fake_write,
                    on_written=lambda p, f: noted.append((p, f)), lookup=lambda a, t: {"Epsilon": "Hard Rock"}.get(a, ""), sleep=lambda s: None)
c = ed.counts()
check(c["EDM"] == 2 and c["Edm"] == 1 and c[""] == 4, "Genres genau gezaehlt, leere eigens")
sug = {tuple(s["from"]): s for s in ed.suggestions()}
check(sug[("Edm",)]["to"] == "EDM" and sug[("Edm",)]["kind"] == "case", "nur Gross/klein -> haeufigste Schreibweise")
check(sug[("Eurodance; Other",)]["to"] == "Dance", "mehrere Genres in einem Feld -> erstes (Eurodance gleich Dance)")
check(sug[("Classical Other",)]["to"] == "Klassik" and sug[("Miscellaneous",)]["to"] == "Other", "gleiche Bedeutung, an vorhandene Schreibweise")
check(sug[("Swing",)]["kind"] == "rare" and sug[("Swing",)]["to"] == "", "selten: Ziel waehlt Markus")
ed.set_never("Swing")
check(("Swing",) not in {tuple(s["from"]) for s in ed.suggestions()}, "Nicht vorschlagen wirkt (und bleibt gespeichert)")
check("Swing" in ge.GenreEditor(lambda: lib, lambda p: p, lambda: root).conf["never"], "Nicht vorschlagen nach Neustart")

# ---- Umbenennen ----
r = ed.rename(["Edm", "EDM"], "EDM")
ed.thread.join(10)
check(r["total"] == 1 and written == [(lib[2]["path"], {"genre": "EDM"})], "nur Dateien mit anderem Genre, nur das Genre-Feld")
check(noted == [(lib[2]["path"], {"genre": "EDM"})], "geschriebene Tags gemeldet (Liste am Pi, Mixxx-Playlist)")
check(ed.job_status()["state"] == "done" and ed.job_status()["ok"] == 1, "Fortschritt fertig")
lib.append({"path": os.path.join(root, "U/Artists/Z/weg.mp3"), "artist": "Z", "title": "Weg", "genre": "Polka"})
ed.rename(["Polka"], "Volksmusik")
ed.thread.join(10)
check(ed.job_status()["gone"] == 1 and ed.job_status()["ok"] == 0, "Grund fuers Ueberspringen: Datei fehlt am Stick (Mixxx kennt sie noch)")
lib.pop()
try:
    ed.rename(["Dance"], "A; B")
    check(False, "ein Genre je Datei")
except ValueError:
    check(True, "Genre mit ; abgelehnt (nur ein Genre je Datei)")
h = ed.history()
check(len(h) == 1 and h[0]["n"] == 1 and h[0]["items"][0][1] == "Edm", "Protokoll mit altem Wert je Datei")
ed.undo(h[0]["id"])
ed.thread.join(10)
check(files[lib[2]["path"]] == "Edm" and ed.history()[1]["undone"], "Zuruecknehmen: altes Genre wieder, als zurueckgenommen markiert")
try:
    ed.undo(h[0]["id"])
    check(False, "nicht zweimal")
except ValueError:
    check(True, "nicht zweimal zuruecknehmen")
r = ed.rename(["Swing"], "Jazz")
ed.thread.join(10)
check(files[lib[13]["path"]] == "Swing" and files[lib[16]["path"]] == "Jazz", "keine MP3: nicht angefasst (zaehlt gar nicht mit), MP3 umbenannt")
ed.rename(["Jazz"], "Swing")
ed.thread.join(10)

# ---- Hausliste ----
check(ed.set_house(["Klassik", "Dance", "dance", "EDM", "Rock"])["house"] == ["Klassik", "Dance", "EDM", "Rock"], "Hausliste ohne Doppelte")
ov = ed.overview()
row = {x["g"]: x for x in ov["genres"]}
check(row["Klassik"]["house"] is True and row["Swing"]["house"] is False, "Genres ausserhalb der Hausliste markiert")
_wl = [song("SAMPLES/THX - THX Intro.wav", "", "THX Intro", ""), song("SAMPLES/x/k2.mp3", "", "Kick", "")]   # WAV: kein Genre moeglich
_we = ge.GenreEditor(lambda: _wl, lambda p: p, lambda: root)
_wo = _we.overview()
check(_wo["empty"] == 1 and _wo["total"] == 1 and [x["path"] for x in _we.fill_candidates(with_samples=True)] == [_wl[1]["path"]],
      "nur MP3s: WAV ohne Genre zaehlt nicht und steht nicht in der Liste (Wunsch 09.11.2026)")
check(ov["empty_sam"] == sum(1 for r in lib if not r.get("genre") and "/SAMPLES/" in r["path"].replace(os.sep, "/")) and ov["empty_sam"] >= 1 and ov["empty"] >= ov["empty_sam"],
      "Ueberblick: wie viele ohne Genre in SAMPLES/TESTSAMPLES liegen (Fehlerbericht 09.11.2026: 213 ohne Genre, Liste zeigte sie nicht) " + str(ov["empty_sam"]))
_gjs = open(os.path.join(ROOT, "pi", "static", "sm", "genres.js"), encoding="utf-8").read()
check('id="gother"' in _gjs and "$('fnow').value = ge ? 'leer' : 'other'" in _gjs
      and "V.genresNote = " in open(os.path.join(ROOT, "pi", "static", "sm", "care.js"), encoding="utf-8").read(),
      "Zahl der Datenpflege aufgeschluesselt, auf der Seite 'mit Other' anklickbar (Fehlerbericht 09.11.2026: 135 gelb, Seite 0)")
check(_gjs.count("fileLine(x.path)") == 3, "Genre-Editor zeigt unter jedem Titel die Datei (Wunsch 09.11.2026), auch unter den Vorschlaegen")
check('id="gempty"' in _gjs and "$('fsam').checked = true" in _gjs and "nw === 'leer'" in _gjs and "$('fset').onclick" in _gjs,
      "Seite: Zahl ohne Genre fuehrt zu den Liedern (auch Samples), Filter leer/Other, ein Genre fuer alle gezeigten")
check("items" not in ov["undo"][0] and ov["fill_n"] > 0, "Ueberblick schlank (Protokoll ohne Dateilisten), Zahl zum Fuellen")
check("Other" not in ed.house_from_counts(min_n=1) and "Edm" not in ed.house_from_counts(min_n=1), "Vorschlag Hausliste ohne Other und ohne Doppelte")

# ---- Genre fuellen ----
fc = {x["path"]: x for x in ed.fill_candidates()}
check(fc[lib[3]["path"]]["want"] == "EDM" and fc[lib[3]["path"]]["src"] == "interpret", "vom Interpreten (seine anderen Lieder)")
check(fc[lib[-1]["path"]]["want"] == "Klassik" and fc[lib[-1]["path"]]["src"] == "ordner", "vom obersten Ordner")
check(lib[14]["path"] not in fc and lib[14]["path"] in {x["path"] for x in ed.fill_candidates(with_samples=True)}, "Samples nur auf Wunsch")
check(lib[11]["path"] in fc, "Miscellaneous zaehlt wie Other")
st0 = ed.fill_status()
check(st0["net_todo"] == len([x for x in st0["items"] if not x["want"] and not x["now"] and x["artist"] and x["title"]]),
      "Knopf nennt nur, was die Suche noch fragt (ohne Other, ohne Interpret/Titel)")
ed.net_start()
for _ in range(100):
    if not ed.net["busy"]:
        break
    time.sleep(0.02)
e1 = {x["path"]: x for x in ed.fill_candidates()}[lib[15]["path"]]
check(e1["want"] == "Rock" and e1["src"] == "internet" and "Hard Rock" in e1["why"], "Internet: Hard Rock -> vorhandenes Rock (Hausliste)")
check(json.load(open(os.path.join(tmp, "genres", "internet.json"))).get(lib[15]["path"])[0] == "Hard Rock", "Internet-Antworten gemerkt")
check(ed.fill_status()["net_todo"] == 0 and ed.net_start()["total"] == 0, "Fehlerbericht 12.11.2026: schon gesuchte nie ein zweites Mal, Knopf zeigt 0")
for _ in range(100):
    if not ed.net["busy"]:
        break
    time.sleep(0.02)
gj = open(os.path.join(ROOT, "pi", "static", "sm", "genres.js"), encoding="utf-8").read()
check("fill.net_todo" in gj and "(alle schon gesucht)" in gj and "$('fnet').disabled = netOff()" in gj, "Seite: Zahl beim Knopf, ausgegraut wenn nichts mehr zu suchen")
ed.assign([(lib[3]["path"], "EDM"), ("/nicht/in/der/liste.mp3", "Rock")])
ed.thread.join(10)
check(files[lib[3]["path"]] == "EDM" and ed.history()[0]["kind"] == "fill", "Fuellen schreibt nur Lieder aus der Bibliothek, mit Protokoll")

busy = ge.GenreEditor(lambda: lib, lambda p: p, lambda: root, write=fake_write, ready=lambda: False)
check(busy.overview()["ready"] is False, "Ueberblick meldet: Tags noch nicht gelesen")
try:
    busy.rename(["Dance"], "Disco")
    check(False, "nicht schreiben, solange die Tags nicht gelesen sind")
except ValueError:
    check(True, "nicht schreiben, solange die Tags nicht gelesen sind")
# ---- HTTP ----
srv = ms.MusicServer([], port=0)
srv.genres = ed
srv.start()
base = "http://127.0.0.1:%d" % srv.port
d = json.loads(urllib.request.urlopen(base + "/genres", timeout=5).read())
check(d["total"] == sum(1 for r in lib if r["path"].endswith(".mp3")) and d["genres"] and "suggest" in d, "GET /genres")
d = json.loads(urllib.request.urlopen(base + "/genres?g=Dance", timeout=5).read())
check(d["n"] == 5 and d["songs"][0]["artist"] == "Beta", "GET /genres?g= Lieder eines Genres")
d = json.loads(urllib.request.urlopen(base + "/genres?fill=1", timeout=5).read())
check(d["n"] >= 3 and "by_src" in d, "GET /genres?fill=1")
req = urllib.request.Request(base + "/genres", data=json.dumps({"op": "rename", "from": ["Dance"], "to": ""}).encode(), method="POST")
try:
    urllib.request.urlopen(req, timeout=5)
    check(False, "leeres Genre: 400")
except urllib.error.HTTPError as e:
    check(e.code == 400, "leeres Genre: 400")
req = urllib.request.Request(base + "/genres", data=json.dumps({"op": "house_suggest"}).encode(), method="POST")
check("house" in json.loads(urllib.request.urlopen(req, timeout=5).read()), "POST house_suggest")
srv.stop() if hasattr(srv, "stop") else None

# ---- Licht-Stil geht mit (Pi) ----
gs = GenreStyles(None)
check(gs.style("Classical Other") == "ruhig" and gs.style("Klassik") == "ruhig", "feste Zuordnung: Klassik und Classical Other ruhig")
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
check('op == "genre_style_carry"' in api and 'op == "genre_styles"' in api and 'path == "/musik/genres"' in api, "Pi: Route und Stil mitnehmen")
check("gstyles.set(to, want" in api, "Stil des alten Genres auf das neue")

# ---- Seite ----
js = open(os.path.join(PI, "static", "sm", "genres.js"), encoding="utf-8").read()
html = open(os.path.join(PI, "static", "sm", "genres.html"), encoding="utf-8").read()
check(subprocess.run(["node", "--check", os.path.join(PI, "static", "sm", "genres.js")], capture_output=True).returncode == 0, "genres.js ohne Fehler")
check('class="s2lnav"' in html and 'data-title="h_genres"' in html, "Kopfleiste")
check("SM.cmd('genre_style_carry'" in js and "SM.ask(" in js and "'undo'" in js and "'net_start'" in js, "Seite: Stil mitnehmen, nachfragen, zuruecknehmen, Internet")
check("/musik/genres" in open(os.path.join(PI, "static", "sm", "care.js"), encoding="utf-8").read()
      and 'href="/musik/genres"' in open(os.path.join(PI, "static", "sm", "music.html"), encoding="utf-8").read(), "Schritt in der Datenpflege, Knopf in der Musik-DB")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read() + \
    open(os.path.join(ROOT, "mac", "helper", "install_helper.sh"), encoding="utf-8").read()
check(inst.count("genre_edit.py") == 2, "Mixxx-App und Helfer bekommen genre_edit.py")
# Fehlerbericht 08.11.2026: Auswahl liess sich nicht oeffnen (datalist, Neuaufbau alle 1,5 s), Seite wurde beim Vorhoeren blau
check("datalist" not in html and "glistdl" not in js and "genreSel(" in js and "<select " in js, "echte Auswahllisten statt datalist")
check("lastSig" in js and "if (sig !== lastSig)" in js, "Liste nur bei Aenderung neu aufbauen")
check("classList.add('bar')" not in js and "classList.add('pbon')" in js, "Seite beim Vorhoeren nicht wie ein Balken eingefaerbt")
# Wunsch 08.11.2026: Genres in jeder Liste alphabetisch
check("out.sort(abc)" in js and "ov.genres.slice().sort((a, b) => abc(a.g, b.g))" in js and "house.sort(abc)" in js, "Genre-Seite: Auswahl, Liste und Hausliste alphabetisch")
check("mode === 'gen' || mode === 'alb' || mode === 'grp') return byName" in open(os.path.join(PI, "static", "sm", "music_groups.js"), encoding="utf-8").read()
      and "localeCompare(String(b[0]), 'de'" in open(os.path.join(PI, "static", "sm", "autodj.js"), encoding="utf-8").read(), "Musik-DB-Gruppen und Auto-DJ alphabetisch")
t = GenreStyles(None).table([["Zydeco", 1], ["ambient", 9], ["Pop", 5]])
mine = [r["genre"].casefold() for r in t if r["n"]]
check(mine == sorted(mine) and all(r["n"] for r in t[:len(mine)]), "Panel: Genre-Stile alphabetisch, deine Genres zuerst")
# Fehlerbericht 09.11.2026: Genre "(148)" (alte ID3v1-Nummer) - Mixxx zeigt "Abstract", unsere Werkzeuge kannten die Nummer nicht
import id3_tags  # noqa: E402
import folder_lib  # noqa: E402
import tag_edit  # noqa: E402
check([id3_tags.genre_name(x) for x in ("(148)", "(17)Rock", "17", "(RX)", "Techno", "(999)")] == ["Abstract", "Rock", "Rock", "Remix", "Techno", ""]
      and len(id3_tags.GENRES) == 192 and id3_tags.genre_is_number("(148)") and not id3_tags.genre_is_number("(17)Rock"),
      "Genre-Nummern wie Mixxx (ID3v1 mit Winamp-Erweiterung bis 191)")
nt = tempfile.mkdtemp(prefix="s2l_gnum_")
nf = os.path.join(nt, "BAHN.MP3")
open(nf, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
tag_edit.write_tags(nf, {"title": "Bahn", "genre": "(148)"})
ri = folder_lib.read_mp3(nf)
rt = tag_edit.read_tags(nf)
check(ri["genre"] == "Abstract" and ri["gnum"] == "(148)" and rt["fields"]["genre"] == "Abstract" and rt["genre_num"] == "(148)",
      "Ordner-Liste und Tag-Editor zeigen den Namen und merken, dass nur die Nummer drinsteht")
ned = ge.GenreEditor(lambda: [{"path": nf, "genre": "Abstract", "gnum": "(148)"}, {"path": "/x.mp3", "genre": "Rock"}], lambda p: p if os.path.exists(p) else None,
                     lambda: nt)
num = ned.numeric()
check(num == [{"path": nf, "now": "(148)", "want": "Abstract"}] and ned.overview()["num"] == num, "Genre-Editor: Vorschlag Namen eintragen")
ned.assign([[x["path"], x["want"]] for x in num])
ned.thread.join(10) if getattr(ned, "thread", None) else time.sleep(1)
for _ in range(50):
    if tag_edit.read_tags(nf)["genre_num"] == "":
        break
    time.sleep(0.1)
check(tag_edit.read_tags(nf)["genre_num"] == "" and tag_edit.read_tags(nf)["fields"]["genre"] == "Abstract" and ned.numeric() == [],
      "Namen eingetragen: in der Datei steht jetzt Abstract, Hinweis weg")
gj = open(os.path.join(PI, "static", "sm", "genres.js"), encoding="utf-8").read()
tj = open(os.path.join(PI, "static", "sm", "tagedit.js"), encoding="utf-8").read()
check('id="numgo"' in gj and "mac('', 'assign', { pairs: num.map" in gj and "tags.genre_num" in tj, "Seiten: Knopf Namen eintragen; Tag-Editor schreibt den Namen beim Speichern")
# Fehlerbericht 09.11.2026: die 60 Samples haben keinen Titel-Tag, darum merkte die Ordner-Liste die Genre-Nummer nicht (kein Knopf)
fd2 = tempfile.mkdtemp(prefix="s2l_gnum2_")
nf2 = os.path.join(fd2, "AUTO.MP3")
open(nf2, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
tag_edit.write_tags(nf2, {"genre": "(148)"})
fl2 = folder_lib.FolderLib(base=os.path.join(fd2, "d"))
fl2.start(fd2, known=[nf2], wait=True)
check(fl2.file_tags.get(folder_lib.tail(nf2)) == {"genre": "Abstract", "gnum": "(148)"}, "ohne Titel-Tag: Genre und Genre-Nummer gemerkt " + str(fl2.file_tags))
tag_edit.write_tags(nf2, {"genre": "Geraeusche"})
os.utime(nf2, (time.time() + 5, time.time() + 5))       # im Test in derselben Sekunde geschrieben: Zeit weiterstellen
fl2.start(fd2, known=[nf2], wait=True)
check(fl2.file_tags.get(folder_lib.tail(nf2)) == {"genre": "Geraeusche"}, "neues Genre bleibt auch nach dem naechsten Durchgang (nicht wieder Abstract aus Mixxx)")
gj2 = open(os.path.join(PI, "static", "sm", "genres.js"), encoding="utf-8").read()
check("genreSel('id=\"hpick\"', '', 'Genre hinzufügen …', house)" in gj2 and "!no.has(g.toLowerCase())" in gj2, "Hausliste: Auswahl zeigt nur Genres, die noch fehlen")
gj3 = open(os.path.join(PI, "static", "sm", "genres.js"), encoding="utf-8").read()
check("neuen Namen eintippen" in gj3 and "'Name ist noch gleich'" in gj3 and "$('edto').select()" in gj3,
      "Angehakt mit gleichem Namen: Hinweis statt '0 Lieder', Name zum Ueberschreiben markiert (09.11.2026)")
gj4 = open(os.path.join(ROOT, "pi", "static", "sm", "genres.js"), encoding="utf-8").read()
check("const PER = 20;" in gj4 and "for (const x of pageItems()) if (x.want) fsel.add(x.path);" in gj4 and "for (const x of pageItems()) { x.want = g; fsel.add(x.path); }" in gj4
      and "genreSel('data-fw=\"' + esc(x.path) + '\"', x.want, null, null, house)" in gj4 and "genreSel('id=\"fsetg\"', '', null, null, house)" in gj4
      and "$('fnone').onclick = () => { fsel.clear(); drawFill(); };" in gj4,
      "Genre fuellen: 20 je Seite, Keine anhaken, Anhaken und Eintragen nur fuer die gezeigte Seite (Wunsch 12.11.2026)")
finish("test_genre_editor")
