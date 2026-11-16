"""Favoriten (Wunsch von Markus, 14.11.2026): Herz bei Liedern, Alben, Interpreten und Genres, halbes Herz fuer Lieder eines
Lieblings-Albums oder -Interpreten, eigene Seite /musik/favoriten, Herz im Hauptpanel und im Tag-Editor, Auto-DJ bevorzugt
Favoriten (mit Auswahl), Herz auf Wunsch als Bewertung 5 Sterne (POPM) in die MP3. Aufs Licht wirkt nichts davon."""
import json
import os
import random
import re
import subprocess
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from showman import albums as al        # noqa: E402
from showman import artists as ar       # noqa: E402
from showman import autodj              # noqa: E402
from showman import favorites as fv     # noqa: E402
import id3_tags as it                   # noqa: E402
import tag_edit as te                   # noqa: E402

M = "/Volumes/USB STICK/musik"
LIB = [{"album": "Falco 3", "artist": "Falco", "name": "Jeanny", "title": "Falco - Jeanny", "dur": 355.2, "track": "4", "path": M + "/U/Falco/Falco 3/04.mp3", "genre": "Pop"},
       {"album": "Falco 3", "artist": "Falco", "name": "Rock Me Amadeus", "title": "Falco - Rock Me Amadeus", "dur": 200, "track": "1", "path": M + "/U/Falco/Falco 3/01.mp3", "genre": "Pop"},
       {"album": "Einzel", "artist": "Falco", "name": "Out of the Dark", "title": "Falco - Out of the Dark", "dur": 220, "path": M + "/U/Falco/Einzel/01.mp3", "genre": "Pop"},
       {"album": "Greatest Hits", "artist": "Queen", "name": "Bohemian Rhapsody", "title": "Queen - Bohemian Rhapsody", "dur": 354, "path": M + "/U/Queen/01.mp3", "genre": "Rock"},
       {"album": "", "artist": "Seiler und Speer", "name": "Ham kummst", "title": "Seiler und Speer - Ham kummst", "dur": 230, "path": M + "/U/SuS/01.mp3", "genre": "Austropop"}]
lib = [dict(x) for x in LIB]
tmp = tempfile.mkdtemp(prefix="s2l_fav_")
A = ar.Artists(tmp, lambda: lib)
B = al.Albums(tmp, lambda: lib, artists=A)
F = fv.Favorites(tmp, lambda: lib, artists=A, albums=B)

# ---- setzen und merken ----
check(F.set("song", LIB[3]["path"], True) and not F.set("song", LIB[3]["path"], True), "Lied-Herz setzen, zweites Mal nichts Neues")
falco3 = al.album_key("Falco 3", LIB[0]["path"])
F.set("album", falco3, True, {"name": "Falco 3", "artist": "Falco"})
F.set("genre", "Austropop", True)
st = F.state()
check(st["song"] == [LIB[3]["path"]] and st["album"] == [falco3] and st["genre"] == ["Austropop"], "Stand: Lied, Album, Genre")
check(set(st["ind"]) == {LIB[0]["path"], LIB[1]["path"]}, "halbes Herz: Lieder des Lieblings-Albums (nicht das Einzellied)")
F.set("artist", "falco", True, {"name": "Falco"})
check(set(F.state()["ind"]) == {LIB[0]["path"], LIB[1]["path"], LIB[2]["path"]}, "halbes Herz: alle Lieder des Lieblings-Interpreten")
F.set("song", LIB[0]["path"], True)
check(LIB[0]["path"] not in F.state()["ind"], "eigenes Herz geht vor dem halben")
d = json.load(open(os.path.join(tmp, "_favoriten.json"), encoding="utf-8"))
check(d["song"][LIB[3]["path"]]["sid"] == "queen|bohemian rhapsody|354" and d["album"][falco3]["name"] == "Falco 3", "Datei shows/_favoriten.json mit Kennung ohne Pfad")
F2 = fv.Favorites(tmp, lambda: lib, artists=A, albums=B)
check(F2.is_fav("artist", "falco") and F2.is_fav("genre", "Austropop"), "nach Neustart wieder da")

# ---- falsche Eingaben ----
for kind, i in (("x", "a"), ("album", "../x"), ("artist", "A B"), ("genre", "a\nb"), ("song", "")):
    try:
        F.set(kind, i, True)
        check(False, "abgelehnt: " + kind + " " + repr(i))
    except ValueError:
        check(True, "abgelehnt: " + kind + " " + repr(i))

# ---- umbenannte Datei: Herz wandert mit ----
lib[3] = dict(lib[3], path=M + "/U/Queen/Greatest Hits/01 Bohemian Rhapsody.mp3")
st = F.state()
check(lib[3]["path"] in st["song"] and LIB[3]["path"] not in st["song"], "verschobene Datei: Herz ueber Interpret/Titel/Laenge wiedergefunden")
lib.pop(4)
check(LIB[0]["path"] in F.state()["song"], "Lieder ausserhalb der Bibliothek bleiben gemerkt")
F.set("song", "/weg/x.mp3", True, {"name": "Weg", "artist": "Niemand"})
P = F.page()
gone = [s for s in P["songs"] if s.get("gone")]
check(len(gone) == 1 and gone[0]["name"] == "Weg", "Seite: gemerktes Lied, das gerade fehlt, steht grau da")
check({s["path"]: s["fav"] for s in P["songs"]}.get(LIB[1]["path"]) == 1 and [a["k"] for a in P["albums"]] == [falco3]
      and [a["k"] for a in P["artists"]] == ["falco"] and P["genres"][0]["name"] == "Austropop", "Seite: Lieder (halbe mit), Alben, Interpreten, Genres")
check(["Pop", 3] in P["all_genres"], "Seite: alle Genres zum Dazunehmen")
check(F.set("genre", "Austropop", False) and not F.is_fav("genre", "Austropop"), "Herz wieder weg")

# ---- Auto-DJ: Gewichte und Bevorzugung ----
w = F.weight()
check(w[LIB[0]["path"]] == 2 and w[LIB[1]["path"]] == 1, "Gewicht: Herz 2, halbes Herz 1")
pool = [{"path": "/p/%d.mp3" % i, "artist": "A%d" % i, "dur": 200, "bpm": 124, "lvl": 6} for i in range(40)]
favw = {"/p/%d.mp3" % i: 2 for i in range(30, 40)}
seqs = [autodj.build(pool, 20, 6, 6, seed=s, favw=favw, fav=f) for s in range(4) for f in (0, 2)]
n0 = sum(sum(1 for t in q if t["path"] in favw) for q in seqs[0::2])
n2 = sum(sum(1 for t in q if t["path"] in favw) for q in seqs[1::2])
check(n2 > n0 + 10, "Auto-DJ: stark bevorzugt deutlich mehr Favoriten (%d statt %d)" % (n2, n0))
check([t["path"] for t in autodj.build(pool, 20, 6, 6, seed=1)] == [t["path"] for t in autodj.build(pool, 20, 6, 6, seed=1, favw=favw, fav=0)], "Auto-DJ: aus = wie bisher")
check(autodj.fav_level({"fav": "2"}) == 2 and autodj.fav_level({"fav": "x"}) == 0 and autodj.fav_level({}) == 0, "Auto-DJ: Stufe aus dem Wunsch")

# ---- MP3: Bewertung 5 Sterne (POPM) ----
AUDIO = bytes(random.Random(5).getrandbits(8) for _ in range(20000))


def mp3(name, frames, ver=3):
    data = b"".join(it.frame(f, b, ver) for f, b in frames) + b"\0" * 64
    n = len(data)
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(b"ID3" + bytes([ver, 0, 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127]) + data + AUDIO)
    return p


def audio_of(p):
    r = it.read(p)
    with open(p, "rb") as f:
        f.seek(10 + r[1])
        return f.read()


p = mp3("a.mp3", [(b"TIT2", it.text_body("Lied")), (b"POPM", b"other@x\x00\x80\x00\x00\x00\x01")])
check(not te.read_tags(p)["fav"], "3 Sterne von anderswo sind kein Favorit")
r = te.write_tags(p, {}, fav=True)
check(r["fav"] and r["fields"]["title"] == "Lied" and audio_of(p) == AUDIO, "Herz in die MP3: 5 Sterne, Titel und Musik bleiben")
frames = [(f, b) for f, _fl, _raw, b in it.read(p)[2] if f == b"POPM"]
check(len(frames) == 2 and any(b.startswith(te.POPM_EMAIL + b"\x00\xff") for _f, b in frames), "eigene Bewertung neben der fremden (3 Sterne bleibt)")
te.write_tags(p, {}, fav=True)
check(sum(1 for f, *_ in it.read(p)[2] if f == b"POPM") == 2, "zweimal setzen: keine doppelte Bewertung")
r = te.write_tags(p, {}, fav=False)
check(not r["fav"] and [b for f, _fl, _raw, b in it.read(p)[2] if f == b"POPM"] == [b"other@x\x00\x80\x00\x00\x00\x01"], "Herz weg: nur die 5 Sterne weg")
r = te.write_tags(p, {"album": "X"})
check(r["fields"]["album"] == "X" and not r["fav"], "ohne fav bleibt die Bewertung, wie sie ist")
ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('fav=None if d.get("fav") is None else bool(d.get("fav"))' in ms, "Musik-Rechner: /tags nimmt fav")

# ---- Pi: API, Einstellungen, Seiten ----
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
for s_ in ('"/musik/favoriten"', '"/api/sm/favs"', '"/api/sm/favs_page"', '"/api/sm/fav_now"', 'op == "fav_set"', "self.favs.weight(lib) if autodj.fav_level(wish)"):
    check(s_ in api, "API: " + s_)
import settings  # noqa: E402
D = {d.key: d for d in settings.DEFS}
check(D["fav_mp3"].default == 0.0 and D["fav_panel"].default == 1.0, "Schalter: MP3 Standard aus, Herz im Hauptpanel Standard an")
SM = os.path.join(ROOT, "pi", "static", "sm")
for f in ("core.js", "favs.js", "music.js", "artists.js", "albums.js", "genres.js", "groups.js", "tagedit.js", "autodj.js", "nav.js"):
    check(subprocess.run(["node", "--check", os.path.join(SM, f)]).returncode == 0, f + " ohne Syntaxfehler")
src = {f: open(os.path.join(SM, f), encoding="utf-8").read() for f in os.listdir(SM) if f.endswith((".js", ".html"))}
check("M7.5 13.5S1 9.6 1 5.2" in src["core.js"] and "SM.favHtml = " in src["core.js"] and "fav_set" in src["core.js"] and "SM.favMp3" in src["core.js"], "Herz aus core.js, dieselbe Form wie der Zustand")
for f, want in (("music.js", "SM.favHtml('song', r.path)"), ("artists.js", "SM.favHtml('artist', a.k"), ("albums.js", "SM.favHtml('album', a.k"),
                ("genres.js", "SM.favHtml('genre', g.g"), ("tagedit.js", "SM.favHtml('song', r.path"), ("groups.js", "SM.favHtml('song', r.path")):
    check(want in src[f], "Herz in " + f)
check('id="ffav"' in src["music.html"] and "k === 'fav'" in src["music.js"] and 'href="/musik/favoriten"' in src["music.html"], "Musik-DB: Filter, Sortieren, Knopf Favoriten")
check('id="favonly"' in src["artists.html"] and 'value="fav"' in src["artists.html"] and 'id="favonly"' in src["albums.html"] and 'value="fav"' in src["albums.html"], "Interpreten und Alben: nur ♥ und Favoriten zuerst")
check('id="wfav"' in src["autodj.html"] and "fav: +$('wfav').value" in src["autodj.js"], "Auto-DJ: Favoriten bevorzugen (aus/etwas/stark)")
page = src["favs.html"]
check('class="s2lnav"' in page and 'data-cur="favs"' in page and all('id="' + i + '"' in page for i in ("songs", "albums", "artists", "genres", "mp3all", "half")), "Seite Favoriten: vier Bereiche, halbe Herzen, MP3-Knopf")
check("'/musik/favoriten', 'h_favs'" in src["nav.js"], "Menue: Favoriten")
import webpanel  # noqa: E402
html = webpanel.make_page()
check('id="pfav"' in html and "async function favNow(m)" in html and "/api/sm/fav_now" in html, "Hauptpanel: Herz neben dem Cover")
js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
check("\\" not in js[js.find("async function favNow"):js.find("async function favNow") + 600], "Hauptpanel-Skript ohne Backslash")
check(".favh.oncover .fi{left:5px;top:5px;height:var(--fs)}" in src["core.js"], "Kachel: volles Herz liegt genau ueber dem umrandeten (Rand des Kreises)")
check(page.index('id="genbar"') < page.index('class="cols"') and page.index('id="secs"') < page.index('id="secr"') < page.index('id="seca"')
      and "grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr)" in page and "max-width: 820px" in page, "Seite Favoriten: Genres oben, drei Spalten Lieder, Interpreten, Alben (Handy untereinander)")
check("function moreSongs()" in src["favs.js"] and "pager()" not in src["favs.js"], "Lieder laden beim Scrollen nach, kein Blaettern")
# Cover beim Darueberfahren (Wunsch 14.11.2026): Kacheln heben sich mit Neon-Rand, grosses Bild kippt mit Glanz; nur mit Maus,
# ohne Bewegung bei "Bewegung reduzieren"
css = open(os.path.join(SM, "sm.css"), encoding="utf-8").read()
check("@media (hover: hover) and (pointer: fine)" in css and ".tile:hover .im" in css and "#det .big:hover" in css and "prefers-reduced-motion: reduce" in css
      and "0 0 0 2px #ff9a3c" in css, "Hover-Effekte fuer Cover: nur mit Maus, Neon-Rand, plastisches grosses Bild, Bewegung reduzierbar")
# "Alle in den Auto-DJ" (Wunsch 14.11.2026): Interpreten, Alben, Favoriten haengen ihre Liste hinten an die Playlist,
# jedes Lied auch "Als Naechstes"; der Auto-DJ nimmt Listen per BroadcastChannel oder Warteliste, ohne Doppelte
aj = src["autodj.js"]
check("SM.autodjAdd = async (rows, next, src)" in src["core.js"] and "'autodj_add'" in src["core.js"] and "type: 'add', ts" in src["core.js"], "gemeinsame Funktion in core.js")
check("function takeAdd(list, src)" in aj and "d.type === 'add'" in aj and "localStorage.getItem('autodj_add')" in aj and "have.has(t.path)" in aj, "Auto-DJ haengt hinten an, ohne Doppelte")
for f, want in (("artists.js", "SM.autodjAdd(curSongs, false, 'Interpret')"), ("albums.js", "SM.autodjAdd(curSongs, false, 'Album')"),
                ("favs.js", "SM.autodjAdd(view.filter(s => !s.gone), false, 'Favoriten')")):
    check(want in src[f] and "data-nx" in src[f], f + ": Alle in den Auto-DJ und Als Naechstes")
check('id="badj" disabled' in src["favs.html"] and 'data-a="adj" id="badj" disabled' in src["artists.js"] and 'data-a="adj" id="badj" disabled' in src["albums.js"],
      "Knopf ausgegraut, bis die Lieder da sind")
check("const cv = x.path ? '<img loading" in src["autodj.js"], "Auto-DJ: Cover der Playlist gleich beim Oeffnen (kommen vom Pi)")
finish("test_favoriten")
