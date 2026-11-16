"""Mixxx-Daten von fehlenden Tracks auf ihren Zwilling uebertragen (Wunsch von Markus, 09.11.2026): Plattenkisten,
Wiedergabelisten und Hotcues, bevor Markus die fehlenden Tracks in Mixxx bereinigt. Laeuft beim Start der Mixxx-App ueber
mixxx_umbenennen.sh (direkt oder ueber eine Kopie), loescht nichts, zweimal laufen aendert nichts."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from _common import ROOT, check, finish

BR = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BR)
import mixxx_uebertragen as mu  # noqa: E402

SCHEMA = """
CREATE TABLE library (id INTEGER PRIMARY KEY, artist TEXT, title TEXT, duration REAL, location INTEGER, mixxx_deleted INTEGER DEFAULT 0);
CREATE TABLE track_locations (id INTEGER PRIMARY KEY, location TEXT UNIQUE, filename TEXT, directory TEXT, fs_deleted INTEGER DEFAULT 0);
CREATE TABLE crate_tracks (crate_id INTEGER NOT NULL, track_id INTEGER NOT NULL, UNIQUE (crate_id, track_id));
CREATE TABLE PlaylistTracks (id INTEGER PRIMARY KEY, playlist_id INTEGER, track_id INTEGER, position INTEGER, pl_datetime_added);
CREATE TABLE cues (id INTEGER PRIMARY KEY AUTOINCREMENT, track_id INTEGER NOT NULL, type INTEGER DEFAULT 0 NOT NULL,
  position INTEGER DEFAULT -1 NOT NULL, length INTEGER DEFAULT 0 NOT NULL, hotcue INTEGER DEFAULT -1 NOT NULL,
  label TEXT DEFAULT '' NOT NULL, color INTEGER DEFAULT 4294901760 NOT NULL);
"""


def make_db(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    rows = [  # id, artist, title, dur, location, fs_deleted
        (1, "Abba", "Waterloo", 165.0, "/m/U-MUSIK/Abba - Waterloo.mp3", 1),        # verschoben
        (2, "Abba", "Waterloo", 165.1, "/m/OLDIES/Abba - Waterloo.mp3", 0),
        (3, "Daddy Yankee", "Gasolina", 192.0, "/m/U/Daddy Yankee - Gasolina.mp3", 1),   # Doppelte geloescht
        (4, "Daddy Yankee", "Gasolina!", 192.3, "/m/Bravo/04 - Bravo - Daddy Yankee - Gasolina.mp3", 0),
        (5, "Niemand", "Weg", 100.0, "/m/U/Niemand - Weg.mp3", 1),                  # ohne Zwilling
        (6, "Queen", "Intro", 60.0, "/m/U/Queen - Intro.mp3", 1),                   # Zwilling zu lang: nicht
        (7, "Queen", "Intro", 300.0, "/m/Live/Queen - Intro (Live).mp3", 0),
    ]
    for tid, a, t, d, loc, fs in rows:
        con.execute("INSERT INTO track_locations (id, location, filename, directory, fs_deleted) VALUES (?, ?, ?, ?, ?)",
                    (tid, loc, os.path.basename(loc), os.path.dirname(loc), fs))
        con.execute("INSERT INTO library (id, artist, title, duration, location) VALUES (?, ?, ?, ?, ?)", (tid, a, t, d, tid))
    con.executemany("INSERT INTO crate_tracks VALUES (?, ?)", [(10, 1), (11, 1), (11, 2), (12, 3), (13, 5)])
    con.executemany("INSERT INTO PlaylistTracks (playlist_id, track_id, position) VALUES (?, ?, ?)", [(20, 1, 1), (21, 3, 5), (21, 4, 6), (22, 6, 1)])
    con.executemany("INSERT INTO cues (track_id, type, position, hotcue) VALUES (?, ?, ?, ?)",
                    [(1, 1, 44100, 0), (1, 1, 88200, 1), (1, 2, 0, -1), (3, 1, 1000, 0), (4, 1, 2000, 0)])
    con.commit()
    con.close()


tmp = tempfile.mkdtemp(prefix="s2l_ueb_")
db = os.path.join(tmp, "m.sqlite")
make_db(db)
con = sqlite3.connect(db)
twins, none = mu.find_twins(con)
tw = {a: (b, k) for a, b, k, *_ in twins}
check(tw.get(1) == (2, "Name") and tw.get(3) == (4, "Interpret+Titel") and 5 not in tw and 6 not in tw and none == 2,
      "Zwilling: gleicher Name, sonst Interpret+Titel mit hoechstens 3 s Unterschied; sonst keiner")
n, log = mu.transfer(con, dry=True)
check(n["kisten"] == 2 and n["listen"] == 1 and n["hotcues"] == 2, "nur zaehlen: " + json.dumps(n))
check(con.execute("SELECT count(*) FROM crate_tracks WHERE track_id = 2").fetchone()[0] == 1, "nur zaehlen aendert nichts")
n, log = mu.transfer(con)
crates2 = sorted(r[0] for r in con.execute("SELECT crate_id FROM crate_tracks WHERE track_id = 2"))
check(crates2 == [10, 11], "Kisten: Zwilling kommt in dieselben Kisten, nie doppelt")
check(con.execute("SELECT track_id FROM PlaylistTracks WHERE playlist_id = 20").fetchone()[0] == 2, "Wiedergabeliste: Zwilling an derselben Stelle")
check(sorted(r[0] for r in con.execute("SELECT track_id FROM PlaylistTracks WHERE playlist_id = 21")) == [3, 4], "steht der Zwilling schon in der Liste: nicht doppelt")
hc2 = sorted((r[0], r[1]) for r in con.execute("SELECT position, hotcue FROM cues WHERE track_id = 2 AND type = 1"))
check(hc2 == [(44100, 0), (88200, 1)] and not con.execute("SELECT 1 FROM cues WHERE track_id = 2 AND type = 2").fetchone(),
      "Hotcues uebernommen (nur Hotcues), Zwilling hatte keine")
check([r[0] for r in con.execute("SELECT position FROM cues WHERE track_id = 4 AND type = 1")] == [2000], "vorhandene Hotcues nie ueberschrieben")
check(con.execute("SELECT count(*) FROM crate_tracks WHERE track_id IN (1, 3, 5)").fetchone()[0] == 4, "nichts geloescht (alte Eintraege bleiben bis zum Bereinigen)")
n2, _ = mu.transfer(con)
check(n2["kisten"] + n2["listen"] + n2["hotcues"] == 0, "zweiter Lauf aendert nichts")
con.close()

# ---- beim Start der Mixxx-App (mixxx_umbenennen.sh), auch ohne Umbenennungen ----
sh = os.path.join(BR, "mixxx_umbenennen.sh")
for mode in ("direkt", "kopie"):
    d2 = os.path.join(tmp, mode)
    os.makedirs(os.path.join(d2, "q"))
    db2 = os.path.join(d2, "m.sqlite")
    make_db(db2)
    env = dict(os.environ, S2L_TEST="1", **({"S2L_KOPIE": "1"} if mode == "kopie" else {}))
    r = subprocess.run(["bash", sh, db2, os.path.join(d2, "q", "offen.tsv")], capture_output=True, text=True, env=env)
    con = sqlite3.connect(db2)
    ok = sorted(x[0] for x in con.execute("SELECT crate_id FROM crate_tracks WHERE track_id = 2")) == [10, 11]
    con.close()
    prot = [f for f in os.listdir(os.path.join(d2, "q")) if f.startswith("uebertragen-")]
    check(ok and "5 Kisten/Listen/Hotcues/Werte uebertragen" in r.stdout and prot and not os.path.exists(os.path.join(d2, "q", "offen.tsv")),
          f"Start der App ({mode}): uebertragen, Protokoll, keine leere Warteschlange: " + r.stdout.strip()[-160:])
    r = subprocess.run(["bash", sh, db2, os.path.join(d2, "q", "offen.tsv")], capture_output=True, text=True, env=env)
    check(r.stdout.strip() == "", f"({mode}) nichts mehr zu tun: still, keine neue Sicherung")

# feste Paare (zwillinge.tsv, 09.11.2026 THX): behaltene Datei neu getaggt und umbenannt, sonst passt nichts mehr
db3 = os.path.join(tmp, "fest.sqlite")
make_db(db3)
tsv = os.path.join(tmp, "zwillinge.tsv")
with open(tsv, "w", encoding="utf-8") as fh:
    fh.write("/m/U/Niemand - Weg.mp3\t/m/Live/Queen - Intro (Live).mp3\n/m/gibts/nicht.mp3\t/m/auch/nicht.mp3\n")
con = sqlite3.connect(db3)
tw = {a: (b, k) for a, b, k, *_ in mu.find_twins(con, mu.load_pairs(tsv))[0]}
check(tw.get(5) == (7, "fest") and tw.get(1) == (2, "Name"), "feste Paare gehen vor, der Rest wie immer")
con.close()
r = subprocess.run([sys.executable, os.path.join(BR, "mixxx_uebertragen.py"), db3, "--zwillinge", tsv], capture_output=True, text=True)
con = sqlite3.connect(db3)
check(con.execute("SELECT 1 FROM crate_tracks WHERE crate_id = 13 AND track_id = 7").fetchone() is not None, "Aufruf mit --zwillinge: Kiste uebertragen " + r.stdout[-120:])
con.close()
check('--ordner "$DIR"' in open(sh, encoding="utf-8").read() and "mu.load_dir(" in open(os.path.join(BR, "music_serve.py"), encoding="utf-8").read(),
      "App-Start und Datenpflege lesen alle Paare (zwillinge.tsv, Umbenennungen)")
# Fehlerbericht 09.11.2026: Mixxx hatte vor dem App-Start neu eingelesen; die Umbenennungslisten sind feste Paare (auch Ketten),
# Bewertung, Wiedergaben und das fruehere "hinzugefuegt am" gehen mit
db4 = os.path.join(tmp, "werte.sqlite")
make_db(db4)
con = sqlite3.connect(db4)
con.executescript("ALTER TABLE library ADD COLUMN rating INTEGER DEFAULT 0; ALTER TABLE library ADD COLUMN timesplayed INTEGER DEFAULT 0;"
                  "ALTER TABLE library ADD COLUMN datetime_added TEXT; UPDATE library SET datetime_added = '2026-11-09';"
                  "UPDATE library SET rating = 4, timesplayed = 9, datetime_added = '2024-01-11' WHERE id = 5;")
con.commit()
con.close()
qd = os.path.join(tmp, "qd")
os.makedirs(qd)
with open(os.path.join(qd, "erledigt-1.tsv"), "w", encoding="utf-8") as fh:
    fh.write("/m/U/Niemand - Weg.mp3\t/m/U/zwischen.mp3\n")
with open(os.path.join(qd, "erledigt-2.tsv"), "w", encoding="utf-8") as fh:
    fh.write("/m/U/zwischen.mp3\t/m/Live/Queen - Intro (Live).mp3\n")
r = subprocess.run([sys.executable, os.path.join(BR, "mixxx_uebertragen.py"), db4, "--ordner", qd], capture_output=True, text=True)
con = sqlite3.connect(db4)
w7 = con.execute("SELECT rating, timesplayed, datetime_added FROM library WHERE id = 7").fetchone()
check(w7 == (4, 9, "2024-01-11") and con.execute("SELECT 1 FROM crate_tracks WHERE crate_id = 13 AND track_id = 7").fetchone() is not None,
      "Umbenennungslisten als Kette, Bewertung/Wiedergaben/Datum uebertragen: " + str(w7) + r.stdout[-100:])
con.close()
r = subprocess.run([sys.executable, os.path.join(BR, "mixxx_uebertragen.py"), db4, "--ordner", qd, "--nur-zaehlen"], capture_output=True, text=True)
check(json.loads(r.stdout)["geaendert"] == 0, "zweiter Lauf: nichts mehr (auch keine Werte)")
check('need=1' in open(sh, encoding="utf-8").read(), "Lesekopie ging nicht: trotzdem uebertragen")

inst = open(os.path.join(BR, "install_launcher.sh"), encoding="utf-8").read()
check('"$HERE/mixxx_uebertragen.py"' in inst, "Mixxx-App bekommt mixxx_uebertragen.py")
# Datenpflege: was noch offen ist und was zuletzt uebertragen wurde
import music_serve as ms  # noqa: E402
base = os.path.join(tmp, "daten")
os.makedirs(os.path.join(base, "umbenannt"))
make_db(os.path.join(base, "mixxxdb.live.sqlite"))
ti = ms.transfer_info(base)
check(ti["offen"] == 5 and ti["fehlend"] == 4 and ti["ohne"] == 2 and ti["letzt"] is None, "Datenpflege: 5 offen, 4 fehlend: " + json.dumps(ti))
shutil.copy(os.path.join(tmp, "kopie", "m.sqlite"), os.path.join(base, "mixxxdb.live.sqlite"))
pr = [f for f in os.listdir(os.path.join(tmp, "kopie", "q")) if f.startswith("uebertragen-")][0]
shutil.copy(os.path.join(tmp, "kopie", "q", pr), os.path.join(base, "umbenannt", pr))
ti = ms.transfer_info(base)
check(ti["offen"] == 0 and ti["letzt"]["n"] == 5, "Datenpflege: nach dem Start alles uebertragen")
cj = open(os.path.join(ROOT, "pi", "static", "sm", "care.js"), encoding="utf-8").read()
check("note: () => V.ueb" in cj and "jetzt gefahrlos bereinigen" in cj and "mb.ueb" in cj, "Schritt Mixxx aufraeumen zeigt, ob erst uebertragen werden muss")
check('"$SRC/mixxx_uebertragen.py"' in open(os.path.join(ROOT, "mac", "helper", "install_helper.sh"), encoding="utf-8").read(), "Helfer bekommt mixxx_uebertragen.py (fuer die Anzeige)")
check('UT="$DIR/.uebertragen-$STAMP.sqlite"' in open(sh, encoding="utf-8").read(), "direkter Weg: Python rechnet auf einer Kopie (darf den Mixxx-Ordner nicht oeffnen), cp bringt sie zurueck")
finish("test_mixxx_uebertragen")
