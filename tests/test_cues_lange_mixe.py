"""Lange Mixe (Fehlerbericht von Markus, 14.11.2026: "The Concourse Project", 134 Minuten, alle 8 Cues in der ersten halben
Stunde): ab 15 Minuten verteilt cue_estimate die Cues ueber das ganze Lied; alte LB-Cues ersetzt mixxx_uebertragen nur,
solange in Mixxx genau die alten stehen (lila, Name, Lage). Normale Lieder bleiben wie bisher."""
import os
import sqlite3
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import cue_estimate as ce          # noqa: E402
import mixxx_uebertragen as mu     # noqa: E402

D = 134 * 60.0
res = {"duration": D, "bpm": 0, "first_beat": 1.0,
       "events": [{"type": "drop", "t": 60.0 * k, "strength": 1} for k in range(2, 31)]       # Drops nur in der ersten halben Stunde
       + [{"type": "drop", "t": 5000.0, "strength": 1}]}
secs = [["intro", 0, 30], ["main", 30, 3000], ["break", 3000, 3100], ["main", 3100, 7000], ["outro", 7000, D]]
old, new = ce.estimate_v1(res, secs), ce.estimate(res, secs)
check(len(old) == 8 and max(t for t, _ in old) <= 1800, "alt: alle 8 in der ersten halben Stunde (der Fehler)")
w = D / 8
check(len(new) == 8 and all(i * w <= t < (i + 1) * w for i, (t, _n) in enumerate(new)), "neu: je ein Cue in jedem Achtel: " + str(new))
names = dict((round(t), n) for t, n in new)
check(new[0] == [30.0, "LB Start"] and names.get(5000) == "LB Drop" and names.get(3000) == "LB Break" and "LB Teil" in names.values(),
      "Start nach dem Intro, Drop und Break im eigenen Achtel, sonst Teil-Anfang")
short = {"duration": 600.0, "bpm": 0, "first_beat": 0, "events": [{"type": "drop", "t": 20.0 * k, "strength": 1} for k in range(1, 29)]}
check(ce.estimate(short, []) == ce.estimate_v1(short, []), "Lieder unter 15 Minuten: genau wie bisher")

# ---- Mixxx: nur unveraenderte alte LB-Cues ersetzen ----
db = os.path.join(tempfile.mkdtemp(), "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.executescript("""CREATE TABLE track_locations (id INTEGER PRIMARY KEY, location TEXT);
CREATE TABLE library (id INTEGER PRIMARY KEY, location INTEGER, samplerate INTEGER, mixxx_deleted INTEGER DEFAULT 0);
CREATE TABLE cues (id INTEGER PRIMARY KEY, track_id INTEGER, type INTEGER, position INTEGER, length INTEGER, hotcue INTEGER, label TEXT, color INTEGER);""")
for i in (1, 2, 3):
    con.execute("INSERT INTO track_locations VALUES (?, ?)", (i, "/m/mix%d.mp3" % i))
    con.execute("INSERT INTO library VALUES (?, ?, 44100, 0)", (i, i))
mu.write_cues(con, [{"loc": "/m/mix%d.mp3" % i, "cues": old} for i in (1, 2, 3)])        # so stehen sie heute in Mixxx
con.execute("UPDATE cues SET position = position + 44100 * 2 * 4 WHERE track_id = 2 AND hotcue = 3")   # Markus hat einen verschoben
con.execute("UPDATE cues SET label = 'Mein Drop' WHERE track_id = 3 AND hotcue = 0")
con.commit()
pos = lambda tid: [round(p / 88200.0, 2) for (p,) in con.execute("SELECT position FROM cues WHERE track_id = ? ORDER BY position", (tid,))]
before2, before3 = pos(2), pos(3)
n = mu.write_cues(con, [{"loc": "/m/mix%d.mp3" % i, "cues": new, "old": old} for i in (1, 2, 3)])
check(n == 1 and pos(1) == [t for t, _ in new], "unveraenderte alte LB-Cues ersetzt")
check(pos(2) == before2 and pos(3) == before3, "verschoben oder umbenannt (von Markus): nie angefasst")
check(mu.write_cues(con, [{"loc": "/m/mix1.mp3", "cues": new, "old": old}]) == 0 and pos(1) == [t for t, _ in new], "zweiter Start: nichts mehr zu tun")
check(mu.write_cues(con, [{"loc": "/m/mix2.mp3", "cues": new}]) == 0, "ohne old: Lieder mit Hotcues bleiben unberuehrt (wie bisher)")
# Fehlerbericht 14.11.2026: die alten LB-Cues kamen aus einer aelteren Analyse (ohne BPM), heute liegen sie ein paar
# Hundertstel anders -> olds: Schaetzungen aller Analysen desselben Liedes
con.execute("INSERT INTO track_locations VALUES (4, '/m/mix4.mp3')")
con.execute("INSERT INTO library VALUES (4, 4, 44100, 0)")
older = [[t + 0.2, n] for t, n in old]
mu.write_cues(con, [{"loc": "/m/mix4.mp3", "cues": older}])
check(mu.write_cues(con, [{"loc": "/m/mix4.mp3", "cues": new, "old": old}]) == 0, "nur mit der heutigen Schaetzung: nicht erkannt")
check(mu.write_cues(con, [{"loc": "/m/mix4.mp3", "cues": new, "old": old, "olds": [old, older]}]) == 1 and pos(4) == [t for t, _ in new],
      "mit der Schaetzung aus der aelteren Analyse: ersetzt")
br = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check('items.append({"loc": p, "cues": new, "old": olds[0], "olds": olds})' in br and "ce.LONG_S" in br, "Bruecke: lange Mixe mit alten LB-Cues kommen in die Liste")
finish("test_cues_lange_mixe")
