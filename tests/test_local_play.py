"""Musik-DB spielt im Browser (21.11.2026): Hauptpanel zeigt Quelle Lokal, Matrix bekommt Bilder und Text ueber den Pfad, Licht bleibt gleich."""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, build, check, finish  # noqa: F401

from showman import local_play as lp             # noqa: E402
from showman.api import ShowManager              # noqa: E402

clk = [100.0]
L = lp.LocalPlay(now=lambda: clk[0])
check(L.panel() is None and L.song() is None, "anfangs nichts")
r = L.report({"playing": True, "name": "Rock Me Amadeus", "artist": "Falco", "path": "/m/a.mp3", "dur": 200, "pos": 10,
              "genre": "Pop", "album": "Falco 3"})
check(r["title"] == "Rock Me Amadeus" and r["artist"] == "Falco" and r["path"] == "/m/a.mp3", "Meldung kommt an")
clk[0] += 3
check(L.panel()["pos"] == 13.0, "Stelle laeuft seit der Meldung weiter")
check(L.song() == {"title": "Rock Me Amadeus", "dur": 200.0, "path": "/m/a.mp3", "artist": "Falco", "album": "Falco 3"}, "Lied fuer die Matrix")
clk[0] += lp.STALE_S + 1
check(L.panel() is None, "ohne Meldung nach %.0f s beendet" % lp.STALE_S)
L.report({"playing": True, "title": "x", "dur": 50})
L.report({"playing": False})
check(L.panel() is None, "Pause/Stopp: sofort weg")
L.report({"playing": True, "title": "y" * 999, "dur": "abc", "pos": float("nan"), "path": ["boese"]})
c = L.current()
check(len(c["title"]) == 200 and c["dur"] == 0 and c["pos"] == 0, "ungepruefte Daten: gekuerzt, Unsinn wird 0")
check(L.report("kaputt") is None and L.report({"playing": True}) is None, "ohne Titel oder kaputte Meldung: nichts")

# Showmanager: Befehl local_play, Laufschrift und Bilder ueber den Pfad
lib = [{"path": "/m/a.mp3", "title": "Rock Me Amadeus", "artist": "Falco", "album": "Falco 3", "dur": 200}]
fk = types.SimpleNamespace(show=types.SimpleNamespace(mixxx=types.SimpleNamespace(library_full=lambda: lib)))
fk._lib_item = lambda p: ShowManager._lib_item(fk, p)
check(ShowManager.matrix_song_text(fk, {"path": "/m/a.mp3", "title": "egal"}) == {"artist": "Falco", "title": "Rock Me Amadeus", "album": "Falco 3"},
      "Laufschrift aus der Bibliothek ueber den Pfad")
check(ShowManager.matrix_song_text(fk, {"path": "/m/neu.mp3", "title": "T", "artist": "A"}) == {"artist": "A", "title": "T", "album": ""},
      "nicht in der Bibliothek: Angaben des Browsers")

# Show: Hauptpanel und Matrix, Licht gleich
rig, sh = build()
check(sh.snapshot()["local"] is None, "ohne Showmanager: nichts")
sh.local = L
L.report({"playing": True, "title": "Rock Me Amadeus", "artist": "Falco", "path": "/m/a.mp3", "dur": 200})
check(sh.snapshot()["local"]["title"] == "Rock Me Amadeus", "Hauptpanel bekommt das lokale Lied")
got = []
sh.matrix = types.SimpleNamespace(tick=lambda s_, cfg: got.append(s_.get("song")))
sh.update(1000.0)
check(got and got[-1]["path"] == "/m/a.mp3", "Matrix: Lied mit Pfad")
sh.radio = types.SimpleNamespace(panel=lambda: None, song=lambda: {"artist": "R", "title": "S", "done": True, "uuid": "u"})
sh.update(1000.025)
check(got[-1].get("path") == "/m/a.mp3", "lokal geht vor dem Radio")

import webpanel                                  # noqa: E402
pg = webpanel.make_page()
check("const R=S.radio,L=S.local;" in pg and "'Lokal':'Local'" in pg and "'local|'+L.path" in pg and "/api/sm/cover?p='+encodeURIComponent(L.path)" in pg,
      "Hauptpanel: Zeile Lokal mit Cover")
js = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("op: 'local_play'" in js and "'pagehide'" in js, "Musik-DB meldet Abspielen und Schliessen")
finish("test_local_play")
