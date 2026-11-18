"""Alben (Wunsch von Markus, 13.11.2026): Seite /musik/alben wie die Interpreten. Album = Name plus Ordner (CD 1/CD 2 zaehlen
zusammen), Sampler = viele Interpreten, Lieder in CD-Reihenfolge, Titelliste von Deezer mit "dir fehlen ...", Verknuepfungen."""
import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
from showman import albums as al  # noqa: E402

M = "/Volumes/USB STICK/musik"
check(al.album_dir(M + "/U-MUSIK/Falco/Falco 3/01.mp3") == M + "/U-MUSIK/Falco/Falco 3"
      and al.album_dir(M + "/KLASSIK/Bach/Goldberg/CD 2/03.mp3") == M + "/KLASSIK/Bach/Goldberg"
      and al.album_dir(M + "/x/Disc 1/a.mp3") == M + "/x", "Ordner des Albums, CD 1 / Disc 2 zaehlen zum Ordner darueber")
check(al.disc_of(M + "/KLASSIK/Bach/Goldberg/CD 2/03.mp3") == 2 and al.disc_of(M + "/U/a.mp3") == 0 and al.track_no("4/9") == 4, "CD und Track")

LIB = [{"album": "Falco 3", "artist": "Falco", "name": "Jeanny", "track": "4", "path": M + "/U-MUSIK/Falco/Falco 3/04.mp3", "year": 1985, "plays": 2},
       {"album": "Falco 3", "artist": "Falco", "name": "Rock Me Amadeus", "track": "1/9", "path": M + "/U-MUSIK/Falco/Falco 3/01.mp3", "year": 1985},
       {"album": "Greatest Hits", "artist": "Queen", "name": "Bohemian Rhapsody", "track": "1", "path": M + "/U-MUSIK/Queen/Greatest Hits/01.mp3"},
       {"album": "Greatest Hits", "artist": "ABBA", "name": "Waterloo", "track": "1", "path": M + "/U-MUSIK/ABBA/Greatest Hits/01.mp3"},
       {"album": "Goldberg", "artist": "Johann Sebastian Bach & Glenn Gould", "name": "Var. 2", "track": "1", "path": M + "/KLASSIK/Goldberg/CD 2/01.mp3"},
       {"album": "Goldberg", "artist": "Johann Sebastian Bach & Glenn Gould", "name": "Aria", "track": "1", "path": M + "/KLASSIK/Goldberg/CD 1/01.mp3"},
       {"album": "Chartmix 3", "artist": "A", "name": "a", "track": "1", "path": M + "/U-MUSIK/Chartmix 3/01.mp3", "grp": "Party"},
       {"album": "Chartmix 3", "artist": "B", "name": "b", "track": "2", "path": M + "/U-MUSIK/Chartmix 3/02.mp3"},
       {"album": "Chartmix 3", "artist": "C", "name": "c", "track": "3", "path": M + "/U-MUSIK/Chartmix 3/03.mp3"},
       {"album": "", "artist": "Ohne", "name": "x", "path": M + "/U-MUSIK/x.mp3"}]
JPEG = b"\xff\xd8\xff" + b"x" * 100
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
    if u.path == "/search/album":
        return Resp(json.dumps({"data": [{"id": 7, "title": "Falco 3 (Remastered)", "artist": {"name": "Falco"}, "nb_tracks": 9},
                                         {"id": 8, "title": "Falco 3", "artist": {"name": "Talco"}, "nb_tracks": 2}]}).encode())
    if u.path == "/album/7":
        return Resp(json.dumps({"title": "Falco 3", "artist": {"name": "Falco"}, "release_date": "1985-10-01", "label": "GIG", "nb_tracks": 3,
                                "cover_big": "https://cdn-images.dzcdn.net/images/cover/x/500x500.jpg",
                                "tracks": {"data": [{"title": "Rock Me Amadeus (Salieri Version)", "artist": {"name": "Falco"}, "disk_number": 1, "track_position": 1},
                                                    {"title": "America", "artist": {"name": "Falco"}, "disk_number": 1, "track_position": 2},
                                                    {"title": "Jeanny", "artist": {"name": "Falco"}, "disk_number": 1, "track_position": 3}]}}).encode())
    raise OSError(url)


tmp = tempfile.mkdtemp()
A = al.Albums(tmp, lambda: LIB, opener=opener, root=lambda: M)
G = A.groups()
names = sorted((g["name"], g["artist"]) for g in G.values())
check(len(G) == 5 and ("Greatest Hits", "Queen") in names and ("Greatest Hits", "ABBA") in names, "gleich benannte Alben verschiedener Ordner bleiben getrennt: " + str(names))
fk = [k for k, g in G.items() if g["name"] == "Falco 3"][0]
check([s["name"] for s in G[fk]["songs"]] == ["Rock Me Amadeus", "Jeanny"] and G[fk]["year"] == 1985 and G[fk]["plays"] == 2, "Lieder nach Track, Jahr, Spielzahl")
gk = [k for k, g in G.items() if g["name"] == "Goldberg"][0]
check([s["name"] for s in G[gk]["songs"]] == ["Aria", "Var. 2"] and len(G[gk]["songs"]) == 2, "CD 1 und CD 2 sind ein Album, CD 1 zuerst")
LIBX = [{"album": "Mix", "artist": "A", "name": "lose", "track": "24", "path": M + "/U/Mix/lose.mp3"},
        {"album": "Mix", "artist": "A", "name": "d2", "track": "1", "path": M + "/U/Mix/Disc 2/01.mp3"},
        {"album": "Mix", "artist": "A", "name": "d1", "track": "1", "path": M + "/U/Mix/Disc 1/01.mp3"}]
GX = al.Albums(tmp, lambda: LIBX).groups()
check([s["name"] for s in list(GX.values())[0]["songs"]] == ["d1", "d2", "lose"], "lose Lieder neben Disc 1/2 ans Ende")
ck = [k for k, g in G.items() if g["name"] == "Chartmix 3"][0]
check(G[ck]["sampler"] and G[ck]["artist"] == "" and not G[fk]["sampler"] and G[fk]["artist_k"] == "falco", "Sampler erkannt, sonst Interpret mit Schluessel")
L = {x["k"]: x for x in A.listing()}
check(L[fk]["cover"].endswith("/01.mp3") and L[ck]["dirs"] == {"U-MUSIK": 3} and L[ck]["grps"] == {"Party": 1} and al.KEY_RE.match(fk), "Liste: Cover-Lied, Bereich")
check(A.key_of_path(M + "/U-MUSIK/Falco/Falco 3/04.mp3") == fk and A.key_of_path(M + "/U-MUSIK/x.mp3") == "", "Album zu einem Lied (Link aus der Musik-DB)")
d = A.songs(fk)
check(d["artist"] == "Falco" and [s["track"] for s in d["songs"]] == ["1/9", "4"], "Lieder eines Albums")
inf = A.info(fk)
check(inf["found"] and inf["date"] == "1985-10-01" and inf["label"] == "GIG" and inf["missing"] == 1
      and [t["have"] for t in inf["tracks"]] == [True, False, True], "Titelliste von Deezer: was du hast, was fehlt (Remastered/Version egal)")
n0 = len(calls)
check(A.info(fk)["missing"] == 1 and len(calls) == n0, "zweites Mal aus der Ablage")
check(not any("/Volumes/" in c for c in calls), "ins Internet nur Namen, keine Pfade")
try:
    A.info("../x")
    check(False, "falscher Schluessel abgelehnt")
except ValueError:
    check(True, "falscher Schluessel abgelehnt")

api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
for s_ in ('"/musik/alben"', '"/api/sm/albums"', '"/api/sm/album"', 'op == "album_info"'):
    check(s_ in api, "API: " + s_)
check(subprocess.run(["node", "--check", os.path.join(ROOT, "pi", "static", "sm", "albums.js")]).returncode == 0, "albums.js ohne Syntaxfehler")
page = open(os.path.join(ROOT, "pi", "static", "sm", "albums.html"), encoding="utf-8").read()
aj = open(os.path.join(ROOT, "pi", "static", "sm", "albums.js"), encoding="utf-8").read()
check('class="s2lnav"' in page and 'data-cur="albums"' in page and "albums.js" in page and 'id="smp"' in page and 'id="areab"' in page, "Seite mit Kopfleiste, Sampler-Auswahl, Bereich")
check("'album_info'" in aj and "SM.tagEdit({ path: s.path" in aj and "const PER = 60;" in aj and "'alb_areas'" in aj, "Titelliste, Tag bearbeiten, 60 je Seite, Bereich gemerkt")
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
nav = open(os.path.join(ROOT, "pi", "static", "sm", "nav.js"), encoding="utf-8").read()
arj = open(os.path.join(ROOT, "pi", "static", "sm", "artists.js"), encoding="utf-8").read()
check('href="/musik/alben"' in mh and "/musik/alben?p=" in mj and "'/musik/alben', 'h_albums'" in nav and "async function myAlbums(k)" in arj,
      "Musik-DB: Knopf und Album als Link; Menue; Interpreten zeigen ihre Alben")
check(L[fk]["gens"] == {} and L[ck]["gens"] == {} and "SM.checkPicker($('genb'), { name: 'Genre', key: 'alb_genres'" in aj and "gens" in open(os.path.join(ROOT, "pi", "showman", "albums.py"), encoding="utf-8").read(),
      "Alben: Genres je Album und Genre-Auswahl")
G2 = al.Albums(tmp, lambda: [dict(LIB[0], genre="Pop"), dict(LIB[1], genre="Pop")]).listing()
check(G2[0]["gens"] == {"Pop": 2}, "Genres je Album gezaehlt")
# Regel 1 (Wunsch 14.11.2026, Falco "Einzelhaft" doppelt): lose Lieder im Ordner direkt ueber dem Album-Ordner gehoeren dazu
F = M + "/U-MUSIK/Artists/Falco"
LIB4 = [{"album": "Einzelhaft", "artist": "Falco", "name": "Zuviel Hitze", "path": F + "/Falco - Zuviel Hitze.mp3"},
        {"album": "Einzelhaft", "artist": "Falco", "name": "Der Kommissar", "track": "2", "path": F + "/1982 - Einzelhaft/02 - Der Kommissar.mp3"},
        {"album": "Einzelhaft", "artist": "Falco", "name": "Helden", "track": "9", "path": F + "/1982 - Einzelhaft/09 - Helden.mp3"},
        {"album": "My Love", "artist": "Whitney", "name": "a", "path": M + "/W/1998 - My Love/01.mp3"},
        {"album": "My Love", "artist": "Whitney", "name": "b", "path": M + "/W/1999 - My Love/01.mp3"},
        {"album": "Einzelhaft", "artist": "Falco", "name": "x", "path": M + "/Compilations/Einzelhaft/01.mp3"},
        {"album": "Parade", "artist": "Austria 3", "name": "lose", "path": M + "/A3/x.mp3"},
        {"album": "Parade", "artist": "Austria 3", "name": "d", "track": "1", "path": M + "/A3/2012 - Parade/Disc/01.mp3"}]
A4 = al.Albums(tmp, lambda: LIB4)
G4 = A4.groups()
ein = [g for g in G4.values() if g["name"] == "Einzelhaft"]
check(sorted(len(g["songs"]) for g in ein) == [1, 3] and any(g["folder"].endswith("1982 - Einzelhaft") and len(g["songs"]) == 3 for g in ein),
      "Regel 1: lose Lieder im Interpreten-Ordner kommen zum Album darunter, der Sampler-Ordner bleibt getrennt")
check(sum(1 for g in G4.values() if g["name"] == "My Love") == 2, "Geschwister-Ordner (1998/1999) bleiben getrennt")
check(al.album_dir(M + "/A3/2012 - Parade/Disc/01.mp3") == M + "/A3/2012 - Parade" and sum(1 for g in G4.values() if g["name"] == "Parade") == 1,
      "Ordner 'Disc' ohne Nummer zaehlt zum Album darueber, dann greift Regel 1")
kk = A4.key_of_path(F + "/Falco - Zuviel Hitze.mp3")
check(kk in G4 and len(G4[kk]["songs"]) == 3 and A4.songs(al.album_key("Einzelhaft", F + "/Falco - Zuviel Hitze.mp3"))["k"] == kk,
      "Link vom losen Lied und alter Schluessel fuehren zum ganzen Album")
# Fehlerbericht 17.11.2026: Album eines gemeinsamen Eintrags steht beim ersten Interpreten (gleicher Schluessel wie dort)
from showman import artists as arm  # noqa: E402
LIB2 = [{"album": "Men Machine EP", "artist": "David Guetta, Marten H\u00f8rger, Men Machine & Snap!", "name": "PWR", "path": M + "/U/Guetta/PWR.mp3"},
        {"album": "Listen", "artist": "David Guetta", "name": "Lovers", "path": M + "/U/Guetta/Listen/01.mp3"},
        {"album": "Simon", "artist": "Simon & Garfunkel", "name": "Boxer", "path": M + "/U/SG/01.mp3"}]
with tempfile.TemporaryDirectory() as d2:
    art2 = arm.Artists(d2, lambda: LIB2)
    G2 = al.Albums(d2, lambda: LIB2, artists=art2).groups()
    ak = {g["name"]: g["artist_k"] for g in G2.values()}
    ag = art2.groups()
    check(ak["Men Machine EP"] == "david-guetta" and "david-guetta" in ag and any(s["name"] == "PWR" for s in ag["david-guetta"]["songs"]),
          "Album mit mehreren Interpreten beim ersten Namen (Interpreten-Seite)")
    check(ak["Simon"] == "simon-garfunkel" and ak["Listen"] == "david-guetta", "Duo bleibt ganz, Einzelname unveraendert")

finish("test_alben")
