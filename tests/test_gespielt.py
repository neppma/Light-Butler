"""Musik-Datenbank: wie oft und wann zuletzt ein Lied in Mixxx gespielt wurde (Wunsch 12.11.2026). Mixxx zaehlt selbst
(library.timesplayed, last_played_at); die Bruecke schickt es als Feld 30 und 31, der Pi prueft es, die Tabelle zeigt es."""
import os
import sqlite3
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "pi"))
import mixxx_bridge as mb                    # noqa: E402
import mixxx_link                            # noqa: E402

# Mixxx-Datenbank im Kleinen
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.execute("CREATE TABLE library (id INTEGER, artist TEXT, title TEXT, duration REAL, bpm REAL, key TEXT, mixxx_deleted INTEGER, timesplayed INTEGER, last_played_at TEXT)")
con.execute("INSERT INTO library VALUES (1, 'A', 'Oft', 200, 128, '', 0, 5, '2026-11-06 22:31:10')")
con.execute("INSERT INTO library VALUES (2, 'B', 'Nie', 180, 120, '', 0, 0, NULL)")
con.commit()
con.close()
lib = {r["title"]: r for r in mb.load_library(db)}
check(lib["Oft"]["timesplayed"] == 5 and lib["Oft"]["last_played_at"].startswith("2026-11-06"), "aus Mixxx gelesen")

items = [x for c in mb.library_chunks(list(lib.values())) for x in c]
by = {x[3]: x for x in items}
check(len(by["Oft"]) >= 32 and by["Oft"][30] == 5 and by["Oft"][31] == 1794004270 and by["Nie"][30] == 0 and by["Nie"][31] == 0,
      "Feld 30 = wie oft, 31 = zuletzt (Sekunden): " + str(by["Oft"][30:]))
d = mixxx_link.lib_item(by["Oft"])
check(d["plays"] == 5 and d["lastp"] == 1794004270, "Pi liest beide Felder")
old = mixxx_link.lib_item(by["Oft"][:30])
check(old["plays"] == 0 and old["lastp"] == 0, "aeltere Bruecke ohne die Felder: 0")
bad = mixxx_link.lib_item(by["Oft"][:30] + [True, "gestern"])
check(bad["plays"] == 0 and bad["lastp"] == 0, "ungueltige Werte: 0")
check(mixxx_link.LIB_FIELDS[30:32] == ("plays", "lastp"), "Felder 30 und 31")

mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("{ k: 'plays', mx: 1, th: 'Gespielt'" in mj and "{ k: 'lastp', mx: 1, th: 'Zuletzt gespielt'" in mj and "'Gespielt', 'Zuletzt gespielt'];" in mj
      and "sortK === 'plays' || sortK === 'lastp'" in mj, "Spalten, Sortierung (meiste zuerst) und Export")
# Genre-Editor, Reiter Genres: Tag-Knopf je Lied in der aufgeklappten Liste (Wunsch 12.11.2026)
gj = open(os.path.join(ROOT, "pi", "static", "sm", "genres.js"), encoding="utf-8").read()
row = gj[gj.index("s.songs.map(x => '<div>'"):][:400]
check("data-tagp=" in row and "async function reloadOpen()" in gj and "setTimeout(reloadOpen, 500)" in gj,
      "Genre-Liste: Tag je Lied, danach offene Listen neu")
finish("test_gespielt")
