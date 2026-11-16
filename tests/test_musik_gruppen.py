"""Musik-Datenbank gruppiert (Wunsch von Markus, 08.11.2026): Ansicht Liste, Interpreten, Genres, Energie, aufklappbar wie ein
Baum. Die Gruppier-Logik (pi/static/sm/music_groups.js) laeuft hier mit node; die Seite selbst nur auf Bausteine geprueft."""
import json
import os
import subprocess

from _common import PI, check, finish

SM = os.path.join(PI, "static", "sm")
GJS = os.path.join(SM, "music_groups.js")

SONGS = [
    {"artist": "Avicii", "name": "Levels", "genre": "House", "lvl": 8, "dur": 338},
    {"artist": "avicii feat. Aloe Blacc", "name": "Wake Me Up", "genre": "House", "lvl": 7, "dur": 247},
    {"artist": "Avicii ft. Rita Ora", "name": "Lonely Together", "genre": "house", "lvl": 7, "dur": 180},
    {"artist": "Simon & Garfunkel", "name": "Mrs Robinson", "genre": "Rock", "lvl": 4, "dur": 240},
    {"artist": "Ötzi", "name": "Ein Stern", "genre": "Schlager", "lvl": 6, "dur": 231},
    {"artist": "The Beatles", "name": "Help", "genre": "Rock", "lvl": 5, "dur": 140},
    {"artist": "", "name": "Track 01", "genre": "", "lvl": 0, "dur": 100},
    {"artist": "2Pac", "name": "Changes", "genre": "Hip-Hop", "lvl": 12, "dur": 269},
]

PROG = """
require(%s);
const songs = %s;
const out = {};
for (const m of ['art', 'gen', 'lvl']) out[m] = MG.group(songs, m).map(g => ({key: g.key, name: g.name, letter: g.letter, n: g.n, dur: g.dur, top: g.top, songs: g.songs.map(s => s.name)}));
out.main = ['Avicii feat. Aloe Blacc', 'A (feat. B)', 'Simon & Garfunkel', 'David Guetta vs. Sia', 'Calvin Harris x Dua Lipa', 'Xavier Naidoo'].map(MG.mainArtist);
out.hm = [MG.hm(59), MG.hm(3120), MG.hm(15120)];
console.log(JSON.stringify(out));
""" % (json.dumps(GJS), json.dumps(SONGS))

r = subprocess.run(["node", "-e", PROG], capture_output=True, text=True)
check(r.returncode == 0, "music_groups.js laeuft mit node: " + r.stderr[:300])
d = json.loads(r.stdout or "{}")
art, gen, lvl = d.get("art", []), d.get("gen", []), d.get("lvl", [])

# Interpreten
av = [g for g in art if g["name"] == "Avicii"]
check(len(av) == 1 and av[0]["n"] == 3 and av[0]["songs"] == ["Levels", "Wake Me Up", "Lonely Together"],
      "Avicii mit feat./ft. und Kleinschreibung in einer Gruppe, Reihenfolge der Tabelle bleibt")
check(av and av[0]["top"] == "House" and av[0]["dur"] == 765, "Interpret: haeufigstes Genre und Gesamtdauer")
check(any(g["name"] == "Simon & Garfunkel" for g in art), "& trennt keinen Interpreten")
names = [g["name"] for g in art]
check(names[-1] == "(ohne Interpret)", "ohne Interpret immer unten")
check(names.index("Avicii") < names.index("The Beatles") < names.index("Ötzi"), "A-Z: 'The' zaehlt nicht, Ö unter O")
check({g["name"]: g["letter"] for g in art}.get("Ötzi") == "O" and {g["name"]: g["letter"] for g in art}.get("2Pac") == "#"
      and {g["name"]: g["letter"] for g in art}.get("The Beatles") == "B", "Buchstaben fuer die A-Z-Leiste")
check(d.get("main") == ["Avicii feat. Aloe Blacc".split(" feat")[0], "A", "Simon & Garfunkel", "David Guetta", "Calvin Harris", "Xavier Naidoo"],
      "Hauptinterpret: feat., (feat.), vs., x; Xavier bleibt ganz")

# Genres
check([g["name"] for g in gen][:4] == ["Hip-Hop", "House", "Rock", "Schlager"] and gen[1]["n"] == 3 and gen[1]["top"] == 1 and gen[2]["top"] == 2,
      "Genres alphabetisch (Wunsch 08.11.2026), Gross/klein egal, Zahl der Interpreten")
check(gen[-1]["name"] == "(ohne Genre)", "ohne Genre unten")

# Energie
check([g["key"] for g in lvl] == ["9", "8", "7", "6", "5", "4", "0"], "Energie 9 bis 1, ueber 9 zaehlt als 9, ohne Energie unten")
check(lvl[-1]["name"] == "ohne Energie" and lvl[2]["n"] == 2, "Energie: Namen und Anzahl")
check(d.get("hm") == ["1 min", "52 min", "4 h 12 min"], "Dauer kurz")

# Seite
html = open(os.path.join(SM, "music.html"), encoding="utf-8").read()
js = open(os.path.join(SM, "music.js"), encoding="utf-8").read()
check(all('data-gv="%s"' % m in html for m in ("list", "art", "gen", "lvl")), "Umschalter Liste/Interpreten/Genres/Energie")
check(html.index("music_groups.js") < html.index("/music.js"), "music_groups.js vor music.js geladen")
check('id="az"' in html and 'id="gall"' in html, "A-Z-Leiste und Alle aufklappen")
check("MG.group(view, gmode)" in js, "Gruppen aus der gefilterten Liste: Filter und Suche wirken auch hier")
check("localStorage.setItem('musikgruppe'" in js, "Browser merkt sich die Ansicht")
check("GLIM = 50" in js and "data-gmore" in js, "grosse Gruppen: erst 50, dann weitere")
for f in ("music.js", "music_groups.js"):
    check(subprocess.run(["node", "--check", os.path.join(SM, f)], capture_output=True).returncode == 0, f + " ohne Syntaxfehler")
import re  # noqa: E402
check(re.match(r"^[a-z_]+\.(js|css|html|svg)$", "music_groups.js") is not None, "Dateiname passt zu den ausgelieferten Dateien")

# ---- Kisten und Wiedergabelisten aus Mixxx (08.11.2026) ----------------------------------------------------------------
import sqlite3  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402

from _common import ROOT  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge as mb  # noqa: E402
import mixxx_link  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_kisten_")
db = os.path.join(tmp, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE library (id INTEGER, artist TEXT, title TEXT, duration REAL, bpm REAL, key TEXT, key_id INTEGER, mixxx_deleted INTEGER, genre TEXT);
CREATE TABLE crates (id INTEGER, name TEXT);
CREATE TABLE crate_tracks (crate_id INTEGER, track_id INTEGER);
CREATE TABLE Playlists (id INTEGER, name TEXT, hidden INTEGER);
CREATE TABLE PlaylistTracks (id INTEGER, playlist_id INTEGER, track_id INTEGER, position INTEGER);
INSERT INTO library VALUES (1, 'Wham!', 'Last Christmas', 260, 107, 'D', 0, 0, 'Pop');
INSERT INTO library VALUES (2, 'Seiler und Speer', 'Ham kummst', 220, 98, 'G', 0, 0, 'Austropop');
INSERT INTO crates VALUES (1, 'Pop'), (2, 'Austropop'), (3, 'Partymusik');
INSERT INTO crate_tracks VALUES (1, 1), (2, 2), (3, 2);
INSERT INTO Playlists VALUES (1, 'WEIHNACHTEN', 0), (2, 'Auto DJ', 1), (3, '2026-11-01', 2);
INSERT INTO PlaylistTracks VALUES (1, 1, 1, 1), (2, 1, 1, 2), (3, 2, 1, 1), (4, 3, 2, 1);
""")
con.commit()
con.close()
lib = {r["id"]: r for r in mb.load_library(db)}
check(lib[1]["lists"] == ["WEIHNACHTEN"] and lib[2]["lists"] == [], "nur eigene Wiedergabelisten (nicht Auto DJ, nicht Verlauf), doppelt nur einmal")
check(lib[2]["crates"] == ["Austropop", "Partymusik"], "Plattenkisten je Lied")
recs = [dict(lib[1], path="/m/wham.mp3"), dict(lib[2], path="/m/seiler.mp3")]
items = [x for c in mb.library_chunks(recs) for x in c]
check(all(len(x) == 33 for x in items) and items[0][20] == ["Austropop", "Partymusik"] and items[1][21] == ["WEIHNACHTEN"],
      "Bruecke: Kisten und Listen als Feld 21 und 22, die ersten Felder unveraendert")
check(mb.year_of("1997") == 1997 and mb.year_of("1997-05-01") == 1997 and mb.year_of("05.2003") == 2003 and mb.year_of("") == 0
      and mb.year_of("12345") == 0 and mb.year_of(None) == 0, "Jahr aus Mixxx lesen")
check(mixxx_link.lib_item(items[1][:22] + [1994])["year"] == 1994 and mixxx_link.lib_item(items[1][:22] + [94])["year"] == 0
      and mixxx_link.lib_item(items[1][:22] + ["1994"])["year"] == 0, "Pi: Jahr nur als Zahl 1900-2099")
it = mixxx_link.lib_item(items[1])
check(it["crates"] == ["Pop"] and it["lists"] == ["WEIHNACHTEN"], "Pi liest sie")
check(mixxx_link.lib_item(items[1][:20])["crates"] == [] and mixxx_link.lib_item(items[1][:20] + ["Pop", 5])["lists"] == [],
      "aeltere Bruecke oder fremde Werte: leere Listen")
check(mixxx_link.lib_item(list(it.values())) == it, "Ablage am Pi: Lied -> Liste -> Lied ohne Verlust")
check(list(it)[-13:] == ["crates", "lists", "year", "album", "track", "grp", "added", "lufs", "tp", "rgt", "plays", "lastp", "rating"] and mixxx_link.LIB_FIELDS[-13:] == ("crates", "lists", "year", "album", "track", "grp", "added", "lufs", "tp", "rgt", "plays", "lastp", "rating"), "Feldreihenfolge wie LIB_FIELDS")

KL = [{"artist": "Wham!", "name": "Last Christmas", "crates": ["Pop"], "lists": ["WEIHNACHTEN"], "dur": 260},
      {"artist": "Seiler und Speer", "name": "Ham kummst", "crates": ["Austropop", "Partymusik"], "lists": [], "dur": 220},
      {"artist": "X", "name": "Ohne", "dur": 100}]
r = subprocess.run(["node", "-e", "require(%s); console.log(JSON.stringify([MG.group(%s, 'kl').map(g => [g.key, g.name, g.kind, g.n]), MG.lists(%s).length]))"
                    % (json.dumps(GJS), json.dumps(KL), json.dumps(KL))], capture_output=True, text=True)
kl = json.loads(r.stdout or "[[], 0]")
check(kl[0] == [["L:weihnachten", "WEIHNACHTEN", "Liste", 1], ["K:austropop", "Austropop", "Kiste", 1], ["K:partymusik", "Partymusik", "Kiste", 1],
                ["K:pop", "Pop", "Kiste", 1], ["", "(in keiner Kiste oder Liste)", "", 1]], "Gruppen: erst Listen, dann Kisten A-Z, ein Lied in mehreren, ohne unten")
check(kl[1] == 4, "Auswahl im Filter: alle Kisten und Listen")
check("k: 'year'" in open(os.path.join(SM, "music.js"), encoding="utf-8").read(), "Musik-DB: Spalte Jahr")
check('data-gv="kl"' in html and 'id="crate"' in html and "MG.keysOf(r, 'kl')" in open(os.path.join(SM, "music.js"), encoding="utf-8").read(),
      "Seite: Ansicht Kisten/Listen und Filter Kiste")

# Album (Wunsch 09.11.2026): Feld 24 von der Bruecke, Pi prueft, Musik-DB sucht und zeigt es
recA = [dict(lib[1], path="/m/a.mp3", album="Nachtschicht Club Explosion Vol. 1", tracknumber="4/17")]
itA = [x for c in mb.library_chunks(recA) for x in c][0]
check(itA[23] == "Nachtschicht Club Explosion Vol. 1" and mixxx_link.lib_item(itA)["album"] == "Nachtschicht Club Explosion Vol. 1"
      and mixxx_link.lib_item(itA[:23])["album"] == "" and mixxx_link.lib_item(itA[:23] + [5])["album"] == "", "Album: Bruecke -> Pi, alte Bruecke ohne Feld")
check(itA[24] == "4/17" and mixxx_link.lib_item(itA)["track"] == "4/17" and mixxx_link.lib_item(itA[:24])["track"] == "", "Track: Bruecke -> Pi")
check("k: 'track', th: 'Track'" in open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read() and "parseInt(x, 10)" in open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read(), "Musik-DB: Spalte Track, sortiert nach Nummer")
mjs = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check("(r.album || '') + ' ' + (r.grp || '') + ' ' + r.file" in mjs and "k: 'album', th: 'Album'" in mjs, "Musik-DB: Suche und Spalte Album")
import folder_lib  # noqa: E402
check('out["album"] = texts.get(b"TALB", "")' in open(folder_lib.__file__, encoding="utf-8").read() and "album" in mb.Forwarder.TAG_KEYS,
      "Album aus der Datei (Ordner-Liste, selbst geschriebene Tags)")
mjs2 = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check("r.bpm ? Math.round(r.bpm)" in mjs2 and "k: 'kid', th: 'Tonart', cls: 'c'" in mjs2, "Musik-DB: BPM ganz, Tonart mittig (Wunsch 09.11.2026)")
# Alben (Wunsch 09.11.2026): Gruppe je Album, Lieder nach Track, Interpret oder Zahl der Interpreten
alb = subprocess.run(["node", "-e", "global.window=global;require(process.argv[1]);const g=MG.group(["
                      "{artist:'A',name:'Zwei',album:'CD',track:'2/9',dur:60},{artist:'A',name:'Eins',album:'CD',track:'1/9',dur:60},"
                      "{artist:'B',name:'X',album:'Sampler',track:'1'},{artist:'C',name:'Y',album:'sampler',track:'2'},{artist:'D',name:'Z',album:''}],'alb');"
                      "console.log(JSON.stringify(g.map(x=>[x.name,x.top,x.songs.map(s=>s.name)])))", os.path.join(PI, "static", "sm", "music_groups.js")],
                     capture_output=True, text=True).stdout.strip()
check(alb == '[["CD","A",["Eins","Zwei"]],["Sampler",2,["X","Y"]],["(ohne Album)","D",["Z"]]]', "Gruppen nach Album, Track-Reihenfolge, Sampler mit Zahl der Interpreten: " + alb)
mj3 = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check("'list', 'art', 'alb'" in mj3 and 'data-gv="alb"' in open(os.path.join(PI, "static", "sm", "music.html"), encoding="utf-8").read(), "Musik-DB: Knopf Alben")
# Gruppen aus dem Tag (Wunsch 10.11.2026): mehrere mit ";" getrennt, A-Z, ohne Gruppe unten
GR = [{"artist": "Tobee", "name": "Saufi", "grp": "Après-Ski", "dur": 200},
      {"artist": "ES", "name": "Pinata", "grp": "Happy, Sunny Holiday; Lizenzfrei (Epidemic Sound Abo)", "dur": 100},
      {"artist": "Pixa", "name": "Lied", "grp": "Lizenzfrei", "dur": 100},
      {"artist": "Mickie Krause", "name": "Solo", "grp": "après-ski", "dur": 200},
      {"artist": "X", "name": "Ohne", "dur": 50}]
gr = subprocess.run(["node", "-e", "require(%s); console.log(JSON.stringify(MG.group(%s, 'grp').map(g => [g.name, g.n, g.top])))" % (json.dumps(GJS), json.dumps(GR))],
                    capture_output=True, text=True).stdout.strip()
check(gr == '[["Après-Ski",2,2],["Happy, Sunny Holiday",1,1],["Lizenzfrei",1,1],["Lizenzfrei (Epidemic Sound Abo)",1,1],["(ohne Gruppe)",1,1]]',
      "Gruppen: A-Z, Gross/klein zusammen, mit ; in mehreren, ohne unten: " + gr)
check("'gen', 'grp', 'lvl'" in mj3 and 'data-gv="grp"' in open(os.path.join(PI, "static", "sm", "music.html"), encoding="utf-8").read(), "Musik-DB: Knopf Gruppen")
finish("test_musik_gruppen")
