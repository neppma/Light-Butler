"""Cue-Punkte ohne Mixxx (Wunsch 11.11.2026, Mixed In Key wird nicht mehr verwendet): aus der MP3 (Mixed In Key/Serato) oder
geschaetzt aus der Analyse; fuers Licht nur mit cue_est, in Mixxx nur mit cue_write beim App-Start, nur in Lieder ohne Hotcues."""
import base64
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "pi"))
import cue_estimate as ce                    # noqa: E402
import id3_tags as it                        # noqa: E402
import mixxx_bridge as mb                    # noqa: E402
import mixxx_uebertragen as mu               # noqa: E402

# ---- aus der MP3 ----
def geob(desc, data):
    return it.frame(b"GEOB", b"\x00application/octet-stream\x00\x00" + desc.encode() + b"\x00" + data, 3)


def cue(i, ms):
    d = b"\x00" + bytes([i]) + ms.to_bytes(4, "big") + b"\x00\xcc\x00\x00\x00\x00" + f"Cue {i + 1}".encode() + b"\x00"
    return b"CUE\x00" + len(d).to_bytes(4, "big") + d


ser = b"\x01\x01" + base64.b64encode(b"\x01\x01" + b"COLOR\x00" + (4).to_bytes(4, "big") + b"\x00\x99\xff\x99" + cue(0, 2297) + cue(1, 16840))
check(ce.serato_markers2(ser) == [2.3, 16.84], "Serato Markers2 gelesen")
mik = base64.b64encode(json.dumps({"algorithm": 14, "cues": [{"name": "Cue 1", "time": 2176.99}, {"name": "Cue 2", "time": 16717.2}]}).encode())


def mp3(name, frames=b""):
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" * 100)
    if frames:
        it.write(p, 3, 0, frames)
    return p


both = mp3("beide.mp3", geob("Serato Markers2", ser) + geob("CuePoints", mik))
only_ser = mp3("serato.mp3", geob("Serato Markers2", ser))
none = mp3("ohne.mp3")
check(ce.file_cues(both) == [2.18, 16.72] and ce.file_cues(only_ser) == [2.3, 16.84] and ce.file_cues(none) == [],
      "aus der MP3: zuerst Mixed In Key (CuePoints), sonst Serato, sonst keine")

# ---- geschaetzt ----
res = {"duration": 200.0, "bpm": 120.0, "first_beat": 0.5,
       "events": [{"type": "drop", "t": 60.2, "strength": 0.8}, {"type": "drop", "t": 62.0, "strength": 0.9}, {"type": "drop", "t": 100.0, "strength": 0.2}]}
secs = [["intro", 0.0, 15.1], ["vers", 15.1, 45.0], ["main", 45.0, 90.0], ["break", 90.0, 120.0], ["main", 120.0, 170.0], ["outro", 170.0, 200.0]]
est = ce.estimate(res, secs)
check(est == [[15.0, "LB Start"], [45.0, "LB Hauptteil"], [60.0, "LB Drop"], [90.0, "LB Break"], [120.0, "LB Hauptteil"], [170.0, "LB Outro"]],
      "geschaetzt: Start nach dem Intro, deutliche Drops, Abschnitte, auf den Takt gerastet, nichts doppelt: " + json.dumps(est))
check(ce.estimate({"duration": 20.0, "first_beat": 0.4}) == [[0.4, "LB Start"]] and ce.estimate({"duration": 0}) == [],
      "kurze Stuecke (Samples): nur ein Start-Cue (Wunsch 11.11.2026), ohne Laenge keiner")
many = ce.estimate({"duration": 600.0, "bpm": 0, "first_beat": 0, "events": [{"type": "drop", "t": 20.0 * k, "strength": 1} for k in range(1, 29)]}, [])
check(len(many) == ce.MAX_CUES, "hoechstens 8")

# ---- Bruecke: nur mit Schalter ----
an = os.path.join(tmp, "analyse")
os.makedirs(an)
rec = {"path": none, "duration": 200.0, "bpm": 120.0, "kid": 1, "cues": []}
with open(os.path.join(an, mb.track_key(200.0, 120.0, 1) + ".json"), "w") as f:
    json.dump(dict(res, events=res["events"], energy=[0.5] * 200), f)
fw = mb.Forwarder([rec], None, None, analysis_dir=an, analyze=False)
fw.music = type("M", (), {"cue_est": False, "cue_write": False})()
check(fw.cues_for(rec, res) == ([], ""), "Schalter aus: wie bisher keine Cues (Licht bleibt gleich)")
fw.music.cue_est = True
cu, cs = fw.cues_for(rec, res)
check(cs == "lb" and cu and cu[0] >= 0, "Schalter an: geschaetzt")
check(fw.cues_for(dict(rec, path=both), res) == ([2.18, 16.72], "datei"), "Schalter an: aus der MP3 vor der Schaetzung")
check(fw.cues_for(dict(rec, cues=[5.0]), res) == ([5.0], "mixxx"), "Hotcues aus Mixxx gehen immer vor")

# ---- Liste fuer Mixxx (cue_tick) ----
rec2 = dict(rec, path=os.path.join(tmp, "zwei.mp3"))
rec3 = dict(rec, path=os.path.join(tmp, "geloescht.mp3"))
for r_ in (rec2, rec3):
    open(r_["path"], "wb").write(b"\xff\xfb\x90\x00" * 10)
fw.mixxx_lib = [rec, rec2, dict(rec3), dict(rec, path=os.path.join(tmp, "mit.mp3"), cues=[1.0]), dict(rec, path=both)]
fw.music.cue_write = False
fw.cue_tick(now=1e9)
check(not os.path.exists(os.path.join(ce.DATA_DIR, ce.PENDING_FILE)), "cue_write aus: keine Liste")
fw.music.cue_write = True
ce.save_json(ce.WRITTEN_FILE, [rec3["path"]])               # dort hat Markus die LB-Cues geloescht
fw.cue_tick(now=2e9)
pend = ce.load_json(ce.PENDING_FILE, [])
by = {x["loc"]: x["cues"] for x in pend}
check(set(by) == {none, rec2["path"], both} and by[both][0] == [2.18, "LB Cue 1"] and by[none][0][1] == "LB Start",
      "Liste: nur Lieder ohne Hotcues, nicht die geloeschten; echte Cues aus der Datei als LB Cue: " + json.dumps(sorted(by)))
fw.mixxx_lib[1] = dict(rec2, cues=[15.0], cue_lb=True)    # nach dem Schreiben liest die Bruecke sie aus Mixxx
fw.cue_tick(now=3e9)
check(rec2["path"] in ce.load_json(ce.WRITTEN_FILE, []), "LB-Cues in Mixxx gesehen: als geschrieben gemerkt (geloescht kommen sie nie wieder)")

# ---- Schreiben in eine nachgebaute Mixxx-Datenbank ----
db = os.path.join(tmp, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.executescript("""CREATE TABLE track_locations (id INTEGER PRIMARY KEY, location TEXT, filename TEXT, directory TEXT, fs_deleted INTEGER DEFAULT 0);
CREATE TABLE library (id INTEGER PRIMARY KEY, artist TEXT, title TEXT, duration REAL, location INTEGER, samplerate INTEGER, mixxx_deleted INTEGER DEFAULT 0);
CREATE TABLE cues (id INTEGER PRIMARY KEY, track_id INTEGER, type INTEGER, position INTEGER, length INTEGER, hotcue INTEGER, label TEXT, color INTEGER);
CREATE TABLE crate_tracks (crate_id INTEGER, track_id INTEGER);
CREATE TABLE PlaylistTracks (id INTEGER PRIMARY KEY, playlist_id INTEGER, track_id INTEGER, position INTEGER, pl_datetime_added TEXT);""")
con.executemany("INSERT INTO track_locations (id, location) VALUES (?, ?)", [(1, "/m/a.mp3"), (2, "/m/b.mp3")])
con.executemany("INSERT INTO library (id, location, samplerate) VALUES (?, ?, ?)", [(10, 1, 44100), (20, 2, 48000)])
con.execute("INSERT INTO cues (track_id, type, position, length, hotcue, label, color) VALUES (20, 1, 1000, 0, 0, 'Mein Cue', 0)")
con.commit()
con.close()
items = [{"loc": "/m/a.mp3", "cues": [[15.0, "LB Start"], [60.0, "LB Drop"]]}, {"loc": "/m/b.mp3", "cues": [[5.0, "LB Start"]]}, {"loc": "/m/x.mp3", "cues": [[1.0, "LB"]]}]
cf = os.path.join(tmp, "neu.json")
json.dump(items, open(cf, "w"))
out = subprocess.run([sys.executable, os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_uebertragen.py"), db, "--cues", cf, "--nur-zaehlen"], capture_output=True, text=True)
n = json.loads(out.stdout or "{}")
check(n.get("cues") == 1 and n.get("geaendert") == 1, "zaehlen: ein Lied bekommt Cues (das mit eigenem Cue nicht, das unbekannte nicht): " + out.stdout + out.stderr[-200:])
subprocess.run([sys.executable, os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_uebertragen.py"), db, "--cues", cf], capture_output=True, text=True, check=True)
con = sqlite3.connect(db)
rows = con.execute("SELECT track_id, type, position, hotcue, label, color FROM cues ORDER BY track_id, hotcue").fetchall()
con.close()
check(rows == [(10, 1, 1323000, 0, "LB Start", ce.LB_COLOR), (10, 1, 5292000, 1, "LB Drop", ce.LB_COLOR), (20, 1, 1000, 0, "Mein Cue", 0)],
      "geschrieben: Position in Samples (Stereo), Name LB, lila; eigener Cue unberuehrt: " + str(rows))
out = subprocess.run([sys.executable, os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_uebertragen.py"), db, "--cues", cf, "--nur-zaehlen"], capture_output=True, text=True)
check(json.loads(out.stdout)["cues"] == 0, "zweites Mal: nichts mehr (hat jetzt Hotcues)")
check(mu.LB_COLOR == ce.LB_COLOR, "gleiche Farbe in beiden Programmen")
sh = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_umbenennen.sh"), encoding="utf-8").read()
check(sh.count('--cues "$CUES"') == 2 and 'CUES="$DATA/cues/mixxx_neu.json"' in sh, "App-Start: zaehlen und schreiben mit den geschaetzten Cues (vor Mixxx, mit Sicherung)")

# ---- Wiedergabeliste "LB zu analysieren" (Wunsch 11.11.2026) ----
con = sqlite3.connect(db)
con.executescript("""CREATE TABLE Playlists (id INTEGER PRIMARY KEY, name TEXT, position INTEGER, hidden INTEGER DEFAULT 0, date_created TEXT, date_modified TEXT, locked INTEGER DEFAULT 0);
CREATE TABLE track_analysis (id INTEGER PRIMARY KEY, track_id INTEGER, type TEXT);""")
con.executemany("INSERT INTO track_locations (id, location) VALUES (?, ?)", [(3, "/m/c.mp3")])
con.executemany("INSERT INTO library (id, location, samplerate, artist, title) VALUES (?, ?, ?, ?, ?)", [(30, 3, 44100, "Zz", "Letzt")])
con.execute("UPDATE library SET artist = 'Aa', title = 'Erst' WHERE id = 20")
con.execute("INSERT INTO track_analysis (track_id, type) VALUES (10, '1')")
con.execute("INSERT INTO Playlists (id, name, position, hidden) VALUES (1, 'Auto DJ', 1, 1)")
con.commit()
con.close()
ub = os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_uebertragen.py")
def run(*x):
    r_ = subprocess.run([sys.executable, ub, db, "--liste-nicht-analysiert", *x], capture_output=True, text=True)
    if not r_.stdout:
        print(r_.stderr[-600:])
    return json.loads(r_.stdout)
check(run("--nur-zaehlen")["liste"] == 1, "zaehlen: Liste fehlt noch")
run()
con = sqlite3.connect(db)
pl = con.execute("SELECT id, hidden, position FROM Playlists WHERE name = 'LB zu analysieren'").fetchone()
tr = [r[0] for r in con.execute("SELECT track_id FROM PlaylistTracks WHERE playlist_id = ? ORDER BY position", (pl[0],))]
con.close()
check(pl[1] == 0 and pl[2] == 2 and tr == [20, 30], "Liste angelegt (sichtbar, hinten), nur nicht analysierte, nach Interpret: " + str((pl, tr)))
check(run("--nur-zaehlen")["liste"] == 0, "nichts geaendert: kein neues Schreiben")
con = sqlite3.connect(db)
con.executemany("INSERT INTO track_analysis (track_id, type) VALUES (?, '1')", [(20,), (30,)])
con.commit()
con.close()
run()
con = sqlite3.connect(db)
check(not con.execute("SELECT 1 FROM Playlists WHERE name = 'LB zu analysieren'").fetchone() and con.execute("SELECT count(*) FROM PlaylistTracks").fetchone()[0] == 0,
      "alles analysiert: Liste wieder weg")
con.close()
check(sh.count("--liste-nicht-analysiert") == 2, "App-Start: Liste zaehlen und nachfuehren (vor Mixxx, mit Sicherung)")

# ---- Pi und Seite ----
import settings                              # noqa: E402
d = {p.key: p for p in settings.DEFS}
check(d["cue_est"].default == 0.0 and d["cue_write"].default == 0.0, "beide Schalter Standard aus")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('"ce": ce, "cw": cw' in api, "Pi schickt die Schalter an den Mac")
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check('id="fnocue"' in open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read() and "if (fnocue && r.cues) return false;" in mj,
      "Musik-DB: Filter ohne Hotcues")
for s_ in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("cue_estimate.py" in open(os.path.join(ROOT, s_), encoding="utf-8").read(), s_ + " installiert cue_estimate.py")
finish("test_cues_ohne_mixxx")
