"""Sterne aus Mixxx (Wunsch von Markus, 14.11.2026): die Bewertung (library.rating, 0-5) kommt als Feld 32 zum Pi, die
Musik-Datenbank zeigt und filtert sie, 5 Sterne zaehlen als Favorit (Herz hier wegnehmen geht, Mixxx bleibt unveraendert)."""
import os
import sqlite3
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "pi"))
import mixxx_bridge as mb                    # noqa: E402
import mixxx_link                            # noqa: E402
from showman import favorites as fv          # noqa: E402

tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.execute("CREATE TABLE library (id INTEGER, artist TEXT, title TEXT, duration REAL, bpm REAL, key TEXT, mixxx_deleted INTEGER, rating INTEGER)")
con.execute("INSERT INTO library VALUES (1, 'A', 'Super', 200, 128, '', 0, 5)")
con.execute("INSERT INTO library VALUES (2, 'B', 'Mittel', 180, 120, '', 0, 3)")
con.execute("INSERT INTO library VALUES (3, 'C', 'Ohne', 180, 120, '', 0, 0)")
con.commit()
con.close()
lib = {r["title"]: r for r in mb.load_library(db)}
check(lib["Super"]["rating"] == 5 and lib["Ohne"]["rating"] == 0, "Sterne aus Mixxx gelesen")
items = [x for c in mb.library_chunks(list(lib.values())) for x in c]
by = {x[3]: x for x in items}
check(by["Super"][32] == 5 and by["Mittel"][32] == 3 and by["Ohne"][32] == 0, "Feld 32 = Sterne")
check(mixxx_link.lib_item(by["Mittel"])["rating"] == 3 and mixxx_link.lib_item(by["Super"][:32])["rating"] == 0
      and mixxx_link.lib_item(by["Super"][:32] + [9])["rating"] == 0 and mixxx_link.LIB_FIELDS[-1] == "rating", "Pi prueft: 0-5, aeltere Bruecke 0")

# 5 Sterne = Favorit
L = [{"path": "/m/super.mp3", "artist": "A", "name": "Super", "dur": 200, "rating": 5},
     {"path": "/m/mittel.mp3", "artist": "B", "name": "Mittel", "dur": 180, "rating": 3}]
F = fv.Favorites(tmp, lambda: L)
check(F.state()["song"] == ["/m/super.mp3"] and F.weight()["/m/super.mp3"] == 2, "5 Sterne in Mixxx: Herz (auch im Auto-DJ)")
check(any(s["path"] == "/m/super.mp3" and s["fav"] == 2 for s in F.page()["songs"]), "auf der Seite Favoriten")
check(F.set("song", "/m/super.mp3", False) and F.state()["song"] == [], "Herz hier wegnehmen geht")
F2 = fv.Favorites(tmp, lambda: L)
check(F2.state()["song"] == [], "bleibt weg nach Neustart")
check(F2.set("song", "/m/super.mp3", True) and F2.state()["song"] == ["/m/super.mp3"], "wieder an")
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
check("{ k: 'rating', th: '★'" in mj and 'id="frat"' in mh and "(r.rating || 0) < frat" in mj, "Musik-DB: Spalte und Filter")
finish("test_sterne")
