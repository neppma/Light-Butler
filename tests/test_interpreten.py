"""Interpreten mit Bild (Wunsch von Markus, 13.11.2026): Seite /musik/interpreten, Bilder von Deezer oder TheAudioDB (ohne
Anmeldung), eigenes Bild, Vorab-Lauf, Sicherung auf den Stick (musik-backup/Light-Butler-Interpreten)."""
import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from showman import artists as ar  # noqa: E402
import stems_backup as sb  # noqa: E402

# ---- Name und Schluessel ----
CASES = ["Falco", "Falco feat. Brigitte Nielsen", "John Williams; Skywalker Symphony Orchestra", "Falco (feat. X)", "DJ Ötzi", "Seiler und Speer", "Simon & Garfunkel",
         "Earth, Wind & Fire", "Die Ärzte", "Straßenjungs", "AC/DC", "Beyoncé ft. Jay-Z", "Avicii vs. Nicky Romero", "  Queen  ",
         "坂本龍一", "P!nk", "Mötley Crüe", "Ludwig van Beethoven", ""]
py = {c: ar.key(c) for c in CASES}
check(py["Falco"] == "falco" and py["Falco feat. Brigitte Nielsen"] == "falco" and py["Falco (feat. X)"] == "falco", "feat. zaehlt beim Hauptinterpreten")
check(py["John Williams; Skywalker Symphony Orchestra"] == "john-williams", "; trennt mehrere Interpreten im Tag")
check(py["Seiler und Speer"] == "seiler-und-speer" and py["Simon & Garfunkel"] == "simon-garfunkel" and py["Earth, Wind & Fire"] == "earth-wind-fire",
      "Bands mit und, & oder Beistrich bleiben ganz")
check(py["DJ Ötzi"] == "dj-otzi" and py["Straßenjungs"] == "strassenjungs" and py["Die Ärzte"] == "die-arzte" and py["AC/DC"] == "ac-dc",
      "Umlaute, ss und Zeichen: " + str((py["DJ Ötzi"], py["Straßenjungs"])))
check(py["坂本龍一"].startswith("u-") and ar.KEY_RE.match(py["坂本龍一"]) and py[""] == "", "andere Schriften: Zeichen-Nummern, leer bleibt leer")
core = open(os.path.join(ROOT, "pi", "static", "sm", "core.js"), encoding="utf-8").read()
js = core[core.index("  SM.artistMain = "):core.index("  SM.ejectStick = ")]
r = subprocess.run(["node", "-e", "const SM={};" + js + ";console.log(JSON.stringify(" + json.dumps(CASES) + ".map(SM.artistKey)))"],
                   capture_output=True, text=True)
jsk = json.loads(r.stdout or "[]")
diff = [(c, py[c], j) for c, j in zip(CASES, jsk) if py[c] != j]
check(len(jsk) == len(CASES) and not diff, "Browser rechnet denselben Schluessel wie der Pi: " + str(diff))

check(ar.host_ok("https://cdn-images.dzcdn.net/images/artist/x/500x500.jpg") and ar.host_ok("https://r2.theaudiodb.com/images/a.jpg/medium")
      and not ar.host_ok("http://cdn-images.dzcdn.net/a.jpg") and not ar.host_ok("https://evil.example/dzcdn.net.jpg")
      and not ar.host_ok("https://dzcdn.net.evil.com/a.jpg"), "Bilder nur per https von Deezer und TheAudioDB")

# ---- Internet zum Schein ----
JPEG = b"\xff\xd8\xff\xe0" + b"x" * 2000
REAL = "https://cdn-images.dzcdn.net/images/artist/echt/500x500.jpg"
FAKE = "https://cdn-images.dzcdn.net/images/artist/falsch/500x500.jpg"
calls = []


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(req, timeout):
    url = req.full_url if hasattr(req, "full_url") else req
    calls.append(url)
    u = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(u.query)
    if u.path == "/search/artist":
        name = q["q"][0]
        if name == "Falco":
            data = [{"id": 1, "name": "Falco", "nb_fan": 7, "picture_big": FAKE}, {"id": 2, "name": "Falco", "nb_fan": 105493, "picture_big": REAL},
                    {"id": 3, "name": "Talco", "nb_fan": 16704, "picture_big": FAKE}]
        elif name == "Seiler und Speer":
            data = [{"id": 9, "name": "Seiler und Speer", "nb_fan": 50000, "picture_big": REAL}]
        else:
            data = []
        return Resp(json.dumps({"data": data}).encode())
    if u.path == "/artist/1/top":
        return Resp(json.dumps({"data": [{"title": "Irgendwas"}]}).encode())
    if u.path == "/artist/2/top":
        return Resp(json.dumps({"data": [{"title": "Rock Me Amadeus (Salieri Mix)"}, {"title": "Jeanny"}]}).encode())
    if u.path == "/artist/9/top":
        return Resp(json.dumps({"data": []}).encode())
    if "search.php" in u.path:
        if q["s"][0] == "Falco":
            return Resp(json.dumps({"artists": [{"strArtist": "Falco", "intBornYear": "1957", "intFormedYear": "1974", "intDiedYear": "1998",
                                                 "strCountry": "Vienna, Austria", "strGenre": "Synthpop", "strBiographyDE": "Falco <b>war</b> ein Musiker.",
                                                 "strWebsite": "falco.at", "intMembers": "1"}]}).encode())
        return Resp(json.dumps({"artists": None}).encode())
    if u.path == "/artist/2/albums":
        return Resp(json.dumps({"data": [{"title": "Falco 3", "release_date": "1985-10-01", "record_type": "album", "cover_medium": REAL},
                                         {"title": "Jeanny", "release_date": "1985-11-01", "record_type": "single", "cover_medium": REAL},
                                         {"title": "Einzelhaft", "release_date": "1982-01-01", "record_type": "album", "cover_medium": "https://evil.example/c.jpg"}]}).encode())
    if url in (REAL, FAKE):
        return Resp(JPEG if url == REAL else b"\xff\xd8\xff" + b"f" * 100)
    raise OSError("unbekannt: " + url)


LIB = [{"artist": "Falco", "name": "Rock Me Amadeus", "path": "/m/a.mp3", "plays": 7, "lastp": 1794000000, "genre": "Austropop"},
       {"artist": "Falco feat. Brigitte Nielsen", "name": "Body Next to Body", "path": "/m/b.mp3", "plays": 1},
       {"artist": "Seiler und Speer", "name": "Ham kummst", "path": "/m/c.mp3"},
       {"artist": "Seiler und Speer", "name": "Soll so sein", "path": "/m/d.mp3"},
       {"artist": "Niemand Bekannt", "name": "Lied", "path": "/m/e.mp3"}]
tmp = tempfile.mkdtemp()
A = ar.Artists(tmp, lambda: LIB, opener=opener)
g = A.groups()
check(g["falco"]["name"] == "Falco" and len(g["falco"]["songs"]) == 2 and g["falco"]["plays"] == 8, "Falco mit seinem feat.-Lied, 8-mal gespielt")
check(A.fetch("falco") is True and open(A.path("falco"), "rb").read() == JPEG and A.index["falco"]["src"] == "deezer",
      "gleicher Name mehrfach: der mit einem eigenen Lied im Programm (nicht der erste Treffer)")
check(A.fetch("seiler-und-speer") is True, "einziger Treffer mit vielen Fans: genommen")
check(A.fetch("niemand-bekannt") is False and A.index["niemand-bekannt"].get("none"), "nichts gefunden: gemerkt")
check(not any("/m/" in c for c in calls) and all(c.startswith("https://") for c in calls), "ins Internet gehen nur Namen, keine Pfade")
L = {x["k"]: x for x in A.listing()}
check(L["falco"]["img"] > 0 and L["falco"]["n"] == 2 and L["falco"]["genre"] == "Austropop" and L["niemand-bekannt"]["none"] == 1, "Liste fuer die Seite")
check([s["name"] for s in A.songs("falco")["songs"]] == ["Rock Me Amadeus", "Body Next to Body"], "Lieder eines Interpreten")
inf = A.info("falco")
check(inf["born"] == 1957 and inf["died"] == 1998 and inf["place"] == "Vienna, Austria" and inf["bio"].startswith("Falco") and inf["lang"] == "de"
      and inf["web"] == "https://falco.at", "Infos von TheAudioDB: Jahre, Herkunft, Lebenslauf, Webseite")
check([x["title"] for x in inf["albums"]] == ["Einzelhaft", "Falco 3"] and inf["albums"][0]["cover"] == "" and inf["n_albums"] == 2,
      "Alben von Deezer: ohne Singles, nach Jahr, fremde Bildquellen weg")
n0 = len(calls)
check(A.info("falco")["born"] == 1957 and len(calls) == n0, "zweites Mal aus der Ablage, ohne Internet")
check(A.info("niemand-bekannt")["bio"] == "", "ohne Treffer: leere Infos")
sg = A.suggestions("falco")
check([x["url"] for x in sg][:2] == [REAL, FAKE] and "105493 Fans" in sg[0]["label"], "Vorschlaege: meiste Fans zuerst")
try:
    A.choose("falco", "https://evil.example/x.jpg")
    check(False, "fremde Bildquelle abgelehnt")
except ValueError:
    check(True, "fremde Bildquelle abgelehnt")
A.upload("niemand-bekannt", JPEG)
check(A.index["niemand-bekannt"]["src"] == "eigen" and "none" not in A.index["niemand-bekannt"], "eigenes Bild")
try:
    A.upload("falco", b"<svg>")
    check(False, "nur JPEG")
except ValueError:
    check(True, "nur JPEG als eigenes Bild")
A.remove("seiler-und-speer")
check(not os.path.exists(A.path("seiler-und-speer")) and A.index["seiler-und-speer"].get("user"), "Bild entfernt, gemerkt")
check("seiler-und-speer" not in A._todo(set()) and "falco" not in A._todo(set()), "Vorab-Lauf: holt nichts wieder, was entfernt wurde oder schon da ist")
st = A.status()
check(st["total"] == 3 and st["done"] == 2 and st["none"] == 1, "Stand fuer die Karte auf der Statistikseite: " + str(st))
files = A.files()
check(sorted(f[0] for f in files) == ["falco.jpg", "niemand-bekannt.jpg"] and A.raw("../x.jpg") is None and A.raw("falco.jpg") == JPEG,
      "Dateiliste fuer die Sicherung, nur gueltige Namen")

# ---- Sicherung auf den Stick und zurueck ----
stick = os.path.join(tmp, "stick", "musik-backup", "Light-Butler-Interpreten")


def pi(url, timeout=0):
    url = url.full_url if hasattr(url, "full_url") else url
    u = urllib.parse.urlparse(url)
    if u.path == "/api/sm/artists_list":
        return Resp(json.dumps({"files": A.files()}).encode())
    if u.path == "/api/sm/artists_file":
        return Resp(A.raw(urllib.parse.parse_qs(u.query)["f"][0]))
    raise OSError(url)


c, n = sb.sync_artists("http://pi", stick, pi)
check(c == 2 and n == 2 and os.path.isfile(os.path.join(stick, "falco.jpg")), "Sicherung: Bilder auf den Stick")
check(sb.sync_artists("http://pi", stick, pi)[0] == 0, "zweites Mal: nichts Neues")
check(sb.ARTISTS_FOLDER == os.path.join("musik-backup", "Light-Butler-Interpreten"), "Ordner neben Kurven, Cues und Covern")
B = ar.Artists(os.path.join(tmp, "neu"), lambda: LIB, opener=opener)
B.restore("falco.jpg", open(os.path.join(stick, "falco.jpg"), "rb").read())
check(B.raw("falco.jpg") == JPEG, "Zurueckspielen auf einen neuen Pi")

# ---- Seite, Routen, Verknuepfungen ----
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
for s_ in ('"/musik/interpreten"', '"/api/sm/artists"', '"/api/sm/artist"', '"/api/sm/artist_img"', '"/api/sm/artists_list"', '"/api/sm/artists_file"',
           'op == "artists_bulk"', '"artist_upload"', 'op == "artists_restore"'):
    check(s_ in api, "API: " + s_)
page = open(os.path.join(ROOT, "pi", "static", "sm", "artists.html"), encoding="utf-8").read()
aj = open(os.path.join(ROOT, "pi", "static", "sm", "artists.js"), encoding="utf-8").read()
check('class="s2lnav"' in page and "artists.js" in page and "tagedit.js" in page, "Seite mit Kopfleiste")
check(subprocess.run(["node", "--check", os.path.join(ROOT, "pi", "static", "sm", "artists.js")]).returncode == 0, "artists.js ohne Syntaxfehler")
check("'artist_info'" in aj and "class=\"cvimg\" data-tag=" in aj and "SM.tagEdit({ path: s.path" in aj,
      "Infos und Alben, Cover gross beim Darueberfahren, Antippen oeffnet Tag bearbeiten")
check("SM.squareCover(f, 800)" in aj and "artist_suggest" in aj and "'/api/sm/artist?k='" in aj, "Bild aendern, eigenes Bild, Lieder")
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
nav = open(os.path.join(ROOT, "pi", "static", "sm", "nav.js"), encoding="utf-8").read()
check('href="/musik/interpreten"' in mh and "/musik/interpreten?n=" in mj and "get('q')" in mj and "'/musik/interpreten', 'h_artists'" in nav,
      "Musik-Datenbank: Knopf, Interpret anklickbar, Suche aus der Adresse; Menue")
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check('id="arbulk"' in wp and "op:'artists_bulk'" in wp, "Karte auf der Statistikseite")
# Bereich: oberster Ordner im Musikordner oder Gruppe im Tag (Wunsch 13.11.2026)
R = "/Volumes/USB STICK/musik"
check(ar.top_dir(R + "/KLASSIK/Mozart/a.mp3", R) == "KLASSIK" and ar.top_dir(R + "/a.mp3", R) == "" and ar.top_dir("/Volumes/USB STICK/musik-import/x/a.mp3", R) == "musik-import"
      and ar.top_dir("/anders/a.mp3", R) == "" and ar.top_dir(R + "/KLASSIK/a.mp3", "") == "", "oberster Ordner")
LIB2 = [{"artist": "Mozart", "name": "A", "path": R + "/KLASSIK/a.mp3"}, {"artist": "Mozart", "name": "B", "path": R + "/U-MUSIK/b.mp3", "grp": "Après-Ski; Party"}]
C = ar.Artists(os.path.join(tmp, "c"), lambda: LIB2, opener=opener, root=lambda: R)
mz = [x for x in C.listing() if x["k"] == "mozart"][0]
check(mz["dirs"] == {"KLASSIK": 1, "U-MUSIK": 1} and mz["grps"] == {"Après-Ski": 1, "Party": 1}, "je Interpret: Ordner und Gruppen mit Zahl")
check("$('areal').addEventListener('change'" in aj and "localStorage.setItem('art_areas'" in aj and 'id="areab"' in page and "const inArea = a =>" in aj and "data-zoom=\"500\"" in aj and "e.target.dataset.zoom" in core,
      "Seite: Bereichsauswahl; grosses Bild zoomt auf 500 Pixel")
check("filter(true);" in aj and "function pager()" in aj and "'more'" not in aj and 'id="pgbot"' in page,
      "Seiten zum Blaettern; Auffrischen bleibt auf der Seite (Fehlerbericht 13.11.2026)")
js_pg = aj[aj.index("  function pager() {"):aj.index("  function draw() {")]
r = subprocess.run(["node", "-e", "let view=[], page=0; const PER=60; const esc=x=>x;" + js_pg +
                    ";const out=[];for(const p of [0,3,4,7,11,12,15]){page=p;view=new Array(16*60);const h=pager();out.push((h.match(/<button|<span class=\"gap\"/g)||[]).length)};console.log(JSON.stringify(out))"],
                   capture_output=True, text=True)
check(r.stdout.strip() and len(set(json.loads(r.stdout))) == 1, "Seitenleiste hat auf jeder Seite gleich viele Felder: " + r.stdout.strip() + r.stderr[-200:])
check("const PER = 60;" in aj, "60 Interpreten je Seite")
js_ia = aj[aj.index("  const inArea = a =>"):aj.index("  const area = () =>")]
r = subprocess.run(["node", "-e", "const $=()=>null;const SM={checkPicker:()=>({sel:[]})};let areaSel=['d:KLASSIK','g:Après-Ski'];" + js_ia +
                    ";const a={n:10,dirs:{KLASSIK:4,'U-MUSIK':6},grps:{'Après-Ski':3}};const b={n:5,dirs:{'U-MUSIK':5},grps:{}};const c={n:4,dirs:{},grps:{'Après-Ski':2}};"
                    "console.log(JSON.stringify([inArea(a),inArea(b),inArea(c)]));areaSel=[];console.log(JSON.stringify([inArea(a)]))"], capture_output=True, text=True)
check(r.stdout.split() == ["[7,0,2]", "[10]"], "mehrere Bereiche: Lieder zusammengezaehlt, keiner gewaehlt = alle: " + r.stdout + r.stderr[-200:])
# & und Co. (13.11.2026): trennen nur, wenn der erste Name auch allein vorkommt oder ein Orchester folgt
LIB3 = [{"artist": "Rainhard Fendrich", "name": "Macho Macho", "path": "/m/1.mp3"},
        {"artist": "Rainhard Fendrich & Vienna Symphony Orchestra", "name": "I am from Austria", "path": "/m/2.mp3"},
        {"artist": "John Williams & London Symphony Orchestra", "name": "Star Wars", "path": "/m/3.mp3"},
        {"artist": "Simon & Garfunkel", "name": "The Boxer", "path": "/m/4.mp3"},
        {"artist": "Earth, Wind & Fire", "name": "September", "path": "/m/5.mp3"},
        {"artist": "Seiler und Speer", "name": "Ham kummst", "path": "/m/6.mp3"},
        {"artist": "Bob Marley", "name": "Sun Is Shining", "path": "/m/7.mp3"},
        {"artist": "Bob Marley & The Wailers", "name": "One Love", "path": "/m/8.mp3"},
        {"artist": "Seiler", "name": "Irgendwas", "path": "/m/9.mp3"}, {"artist": "Seiler und Speer", "name": "Soll so sein", "path": "/m/12.mp3"},
        {"artist": "Seiler und Speer, Sebastian Schneider", "name": "Zusammen", "path": "/m/10.mp3"},
        {"artist": "Orchester, Chor, Eric Frantzen", "name": "Messe", "path": "/m/11.mp3"}]
LIB3 += [{"artist": "Johann Sebastian Bach", "name": "Solo %d" % i, "path": "/m/b%d.mp3" % i} for i in range(3)]
LIB3 += [{"artist": "Johann Sebastian Bach & Glenn Gould", "name": "Goldberg %d" % i, "path": "/m/g%d.mp3" % i} for i in range(12)]
D = ar.Artists(os.path.join(tmp, "d"), lambda: LIB3, opener=opener)
g3 = D.groups()
check(len(g3["rainhard-fendrich"]["songs"]) == 2 and g3["rainhard-fendrich"]["name"] == "Rainhard Fendrich", "Fendrich & Orchester: bei Rainhard Fendrich")
check("john-williams" in g3 and "london-symphony-orchestra" not in g3, "Orchester danach: beim Ersten, auch ohne eigenes Lied")
check({"simon-garfunkel", "earth-wind-fire", "seiler-und-speer"} <= set(g3) and len(g3["bob-marley"]["songs"]) == 2, "Bands bleiben ganz; Bob Marley & The Wailers bei Bob Marley")
check(D.alias.get("rainhard-fendrich-vienna-symphony-orchestra") == "rainhard-fendrich", "Link aus der Musik-DB findet den Interpreten (alias)")
check(len(g3["seiler-und-speer"]["songs"]) == 3 and len(g3["seiler"]["songs"]) == 1,
      "laengster bekannter Name gewinnt; Seiler und Speer bleibt, obwohl es Seiler allein einmal gibt: " + str({k: len(v["songs"]) for k, v in g3.items() if "seiler" in k}))
check("orchester-chor-eric-frantzen" in g3 and "orchester" not in g3, "ein Orchester vorne wird nicht abgetrennt")
check(len(g3["johann-sebastian-bach"]["songs"]) == 15 and len(g3["glenn-gould"]["songs"]) == 12 and "johann-sebastian-bach-glenn-gould" not in g3,
      "Bach & Glenn Gould: bei beiden (Bach 3 allein, 12 gemeinsam)")
check(ar.lead_parts("Swedish House Mafia, Niki & The Dove, Argy", {"swedish-house-mafia": 5}) == ["Swedish House Mafia", "Niki & The Dove", "Argy"],
      "dahinter nur bei Beistrich trennen: Niki & The Dove bleibt")
check("vienna-symphony-orchestra" not in g3 and "london-symphony-orchestra" not in g3 and "sebastian-schneider" in g3,
      "Orchester bekommen keine Kachel, Gaeste schon")
check("alias[want] || want" in aj and '"alias": dict(mgr.artists.alias)' in api, "Seite nimmt den alias")

# Fehlerbericht 13.11.2026: Vorab-Lauf vor dem Einspielen gestartet -> der Neustart stuerzte ab (Musikordner noch nicht geladen)
from _common import build  # noqa: E402
from showman.api import ShowManager  # noqa: E402
base = tempfile.mkdtemp(prefix="s2l_art_")
open(os.path.join(base, ar.STATE), "w").write('{"on": true}')
_rig, _sh = build()
try:
    _m = ShowManager(_sh, base)
    _m.artist_opener = lambda req, timeout: (_ for _ in ()).throw(OSError("kein Internet im Test"))
    check(_m.artists.status()["total"] >= 0, "Start mit laufendem Vorab-Lauf stuerzt nicht ab")
    _m.artists.stop()
except Exception as e:  # noqa: BLE001
    check(False, "Start mit laufendem Vorab-Lauf stuerzt nicht ab: " + repr(e))
# Genre-Filter (13.11.2026): Genres je Interpret mit Zahl; Bereich und Genre zusammen
check(L["falco"]["gens"] == {"Austropop": 1}, "Genres je Interpret in der Liste: " + str(L["falco"].get("gens")))
core2 = open(os.path.join(ROOT, "pi", "static", "sm", "core.js"), encoding="utf-8").read()
artj = open(os.path.join(ROOT, "pi", "static", "sm", "artists.js"), encoding="utf-8").read()
js_g = artj[artj.index("  const inArea = a =>"):artj.index("  const area = () =>")].replace("const genP = SM.checkPicker", "const genP0 = SM.checkPicker")
r = subprocess.run(["node", "-e", "const $=()=>null;const SM={checkPicker:()=>null};let areaSel=['d:U-MUSIK'];var genP={sel:['Pop']};" + js_g +
                    ";const a={n:10,dirs:{'U-MUSIK':8,KLASSIK:2},grps:{},gens:{Pop:3,Rock:7}};const b={n:4,dirs:{'U-MUSIK':4},grps:{},gens:{Rock:4}};"
                    "console.log(JSON.stringify([cnt(a),cnt(b)]));genP.sel=[];areaSel=[];console.log(JSON.stringify([cnt(a)]))"], capture_output=True, text=True)
check(r.stdout.split() == ["[3,0]", "[10]"], "Bereich und Genre zusammen: das Kleinere, ohne Auswahl alle: " + r.stdout + r.stderr[-300:])
check("SM.checkPicker = (btn, opt) =>" in core2 and "SM.checkPicker($('genb'), { name: 'Genre', key: 'art_genres'" in artj, "Genre-Auswahl mit Haekchen, gemerkt")
# Zwei Personen ohne Einzel-Lieder (Wunsch 14.11.2026): getrennt, Bands bleiben ganz, Begleitbands zaehlen beim Ersten
for a_, want in (("John Travolta & Olivia Newton‐John", ["John Travolta", "Olivia Newton‐John"]), ("Albina & Stefy De Cicco", ["Albina", "Stefy De Cicco"]),
                 ("Bob Marley & the Wailers", ["Bob Marley"]), ("Bill Haley and His Comets", ["Bill Haley"]), ("Frank Sinatra Duet With Tony Bennett", ["Frank Sinatra", "Tony Bennett"]),
                 ("Marco Wagner, Dominik Ofner", ["Marco Wagner", "Dominik Ofner"]), ("Clean Bandit & Topic", ["Clean Bandit", "Topic"]),
                 ("Kool Savas & Azad", ["Kool Savas", "Azad"]), ("Oliver Shanti & Friends", ["Oliver Shanti"]), ("Starlite Orchestra and Choir", []),
                 ("Simon & Garfunkel", []), ("Seiler und Speer", []), ("Kool & The Gang", []), ("The Mamas & the Papas", []), ("Niki & The Dove", []),
                 ("Earth, Wind & Fire", []), ("Dance With a Stranger", []), ("Mr. & Msr. Smith", []), ("Camerata Academica & Alfred Scholz", []),
                 ("Claudia Jung (Duett Mit Cliff Richard)", []), ("Booker T. & Bb Stone Pres. Belinda James - Groove Me", [])):
    check(ar.lead_parts(a_, {}) == want, "zerlegen: " + a_ + " -> " + str(ar.lead_parts(a_, {})))
# Listen (Wunsch 14.11.2026): "Alok, Sofi Tukker & Inna", Duos bleiben ("Calmani & Grey"), Bands mit "&" am Ende bleiben ganz
for a_, want in (("Alok, Sofi Tukker & Inna", ["Alok", "Sofi Tukker", "Inna"]), ("Calmani & Grey, Golden Chocolate", ["Calmani & Grey", "Golden Chocolate"]),
                 ("Heinrich & Heine, Touchtalk", ["Heinrich & Heine", "Touchtalk"]), ("Swedish House Mafia, Niki & The Dove, Argy", ["Swedish House Mafia", "Niki & The Dove", "Argy"]),
                 ("Tito Puente, Jr. & The Latin Rhythm", ["Tito Puente, Jr.", "The Latin Rhythm"]), ("Hannes, Peter Wackel, Kloß mit Soß", ["Hannes", "Peter Wackel", "Kloß mit Soß"]),
                 ("Earth, Wind & Fire", []), ("Crosby, Stills & Nash", []), ("Bell, Book & Candle", [])):
    check(ar.lead_parts(a_, {}) == want, "Liste: " + a_ + " -> " + str(ar.lead_parts(a_, {})))
al_ = {ar.key("David Guetta"): 5, ar.key("Klaus & Klaus"): 3, ar.key("Dimitri Vegas & Like Mike"): 4}
check(ar.lead_parts("David Guetta, Mistajam & John Newman", al_) == ["David Guetta", "Mistajam", "John Newman"], "bekannter erster Name: auch das & dahinter aufgeloest")
check(ar.lead_parts("Mickie Krause, Klaus & Klaus", al_) == ["Mickie Krause", "Klaus & Klaus"]
      and ar.lead_parts("Dimitri Vegas & Like Mike, Ummet Ozcan & Brennan Heart", al_) == ["Dimitri Vegas & Like Mike", "Ummet Ozcan", "Brennan Heart"], "bekannte Namen bleiben ganz")
# Eindeutiger Name (Wunsch 14.11.2026): nur ein Deezer-Treffer mit Bild -> auch mit wenigen Fans; mehrere kleine -> nichts
def op2(req, timeout):
    u = urllib.parse.urlparse(req.full_url if hasattr(req, "full_url") else req)
    q = urllib.parse.parse_qs(u.query)
    if u.path == "/search/artist":
        n = q["q"][0]
        data = {"Klein": [{"id": 31, "name": "Klein", "nb_fan": 12, "picture_big": REAL}],
                "Doppelt": [{"id": 41, "name": "Doppelt", "nb_fan": 30, "picture_big": REAL}, {"id": 42, "name": "Doppelt", "nb_fan": 20, "picture_big": FAKE}]}.get(n, [])
        return Resp(json.dumps({"data": data}).encode())
    if u.path.endswith("/top"):
        return Resp(json.dumps({"data": []}).encode())
    if "search.php" in u.path:
        return Resp(json.dumps({"artists": None}).encode())
    return opener(req, timeout)


E = ar.Artists(os.path.join(tmp, "e"), lambda: [{"artist": "Klein", "name": "x", "path": "/m/k.mp3"}, {"artist": "Doppelt", "name": "y", "path": "/m/d2.mp3"}], opener=op2)
check(E.deezer_pick("Klein", ["x"])["id"] == 31 and E.deezer_pick("Doppelt", ["y"]) is None, "eindeutiger Name: Bild auch mit wenigen Fans, bei Gleichnamigen nicht")
check(E.fetch("klein") and not E.fetch("doppelt") and "none" in E.index["doppelt"], "Vorab-Lauf: Klein bekommt ein Bild, Doppelt bleibt leer")
E.mark_none("klein", "Klein")
E.index["klein"]["user"] = 1                          # von Hand entfernt
E.stop_ev.set()
E.start = lambda: {"running": False}                  # Test: kein echter Lauf
r = E.retry_none()
check(r["retried"] == 1 and "doppelt" not in E.index and E.index["klein"].get("user"), "Leere noch einmal versuchen: erfolglose vergessen, von Hand entfernte bleiben")
aj_ = open(os.path.join(ROOT, "pi", "static", "sm", "artists.js"), encoding="utf-8").read()
check('id="bretry"' in open(os.path.join(ROOT, "pi", "static", "sm", "artists.html"), encoding="utf-8").read() and "SM.cmd('artists_retry'" in aj_
      and 'op == "artists_retry"' in open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read(), "Knopf Leere noch einmal versuchen")
finish("test_interpreten")
