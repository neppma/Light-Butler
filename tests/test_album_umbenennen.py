"""Albumname aendern (Seite Alben, Bleistift, Wunsch 14.11.2026) und fehlende Titel auf Spotify anhoeren: der Musik-Rechner
schreibt TALB in alle MP3s des Albums (nur MP3s, nur wo es sich aendert, nie leer), mit Protokoll und Zuruecknehmen."""
import os
import subprocess
import sys
import tempfile
import time

from _common import ROOT, check, finish

tmp = os.path.realpath(tempfile.mkdtemp())
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import genre_edit as ge  # noqa: E402

files = {}
for n in ("a.mp3", "b.mp3", "c.mp3", "d.wav"):
    p = os.path.join(tmp, n)
    open(p, "wb").write(b"x")
    files[n] = p
OLD, NEW = "Ich Wollte Nie Einer Von Denen Sein", "Ich wollte nie einer von denen sein"
LIB = [{"path": files["a.mp3"], "album": OLD}, {"path": files["b.mp3"], "album": OLD},
       {"path": files["c.mp3"], "album": NEW}, {"path": files["d.wav"], "album": OLD}]
written, told = [], []


def write(f, fields):
    written.append((os.path.basename(f), dict(fields)))
    for r in LIB:
        if r["path"] == f:
            r.update(fields)


def wait(e):
    for _ in range(200):
        if (e.job_status() or {}).get("state") == "done":
            return
        time.sleep(0.02)


E = ge.GenreEditor(lambda: LIB, lambda p: p, lambda: tmp, write=write, on_written=lambda p, f: told.append(f))
res = E.set_album([files[n] for n in ("a.mp3", "b.mp3", "c.mp3", "d.wav")], "  " + NEW + " ")
wait(E)
check(res["total"] == 2 and written == [("a.mp3", {"album": NEW}), ("b.mp3", {"album": NEW})], "nur MP3s, die sich aendern: " + str(written))
check(told == [{"album": NEW}] * 2, "Liste am Pi gleich mit dem neuen Namen")
for bad in ("", "   "):
    try:
        E.set_album([files["a.mp3"]], bad)
        check(False, "leer abgelehnt")
    except ValueError:
        check(True, "leer abgelehnt")
h = [x for x in E.history() if x.get("field") == "album"]
check(len(h) == 1 and h[0]["n"] == 2, "Protokoll mit Feld album")
written.clear()
E.undo(h[0]["id"])
wait(E)
check(sorted(written) == [("a.mp3", {"album": OLD}), ("b.mp3", {"album": OLD})], "Zuruecknehmen schreibt den alten Namen")
srv = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('op == "album"' in srv and "ge.set_album(" in srv, "Musik-Rechner nimmt op album an")
js = open(os.path.join(ROOT, "pi", "static", "sm", "albums.js"), encoding="utf-8").read()
check("data-a=\"aedit\"" in js and "op: 'album'" in js and "field=album" in js, "Bleistift, Schreiben, Stand")
core = open(os.path.join(ROOT, "pi", "static", "sm", "core.js"), encoding="utf-8").read()
check("SM.SPOTIFY_SEARCH = 'https://open.spotify.com/search/'" in core and 'target="lb_spotify"' in core and "SM.spotifyLink = " in core,
      "gemeinsamer Spotify-Link, eigenes Fenster")
check("t.have ? '' : spotify(" in js and "SM.spotifyLink(q" in js, "Spotify-Suche nur bei fehlenden Titeln")
mu = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("if (!view.length && sq)" in mu and "SM.spotifyLink(sq" in mu, "Musik-Datenbank: nichts gefunden -> dieselbe Suche auf Spotify")
check(subprocess.run(["node", "--check", os.path.join(ROOT, "pi", "static", "sm", "albums.js")]).returncode == 0, "albums.js ohne Syntaxfehler")
finish("test_album_umbenennen")
