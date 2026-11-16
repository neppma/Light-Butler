"""Windows-Starter der Mixxx-Bruecke (mixxx_start.py, 15.11.2026): vor dem Start von Mixxx Sicherung, Umbenennungen und Sterne
ueber eine gepruefte Arbeitskopie (wie launch.sh/mixxx_umbenennen.sh/mixxx_sterne.sh am Mac), Journal = nichts anfassen.
Laeuft auf jedem System (reines Python), braucht kein Mixxx."""
import json
import os
import sqlite3
import sys
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
data = os.path.join(tmp, "daten")
os.environ["S2L_DATA"] = data
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_start as st                    # noqa: E402
import mixxx_sterne as ms                   # noqa: E402
import audio_send as asnd                   # noqa: E402

db = os.path.join(tmp, "Mixxx", "mixxxdb.sqlite")
os.makedirs(os.path.dirname(db))
con = sqlite3.connect(db)
con.execute("CREATE TABLE track_locations (id INTEGER PRIMARY KEY, location TEXT, filename TEXT, directory TEXT, fs_deleted INTEGER)")
con.execute("CREATE TABLE library (id INTEGER PRIMARY KEY, location INTEGER, rating INTEGER)")
for i, p in enumerate(["C:/m/Alt.mp3", "C:/m/B.mp3", "C:/m/Neu2.mp3", "C:/m/Doppelt.mp3"], 1):
    con.execute("INSERT INTO track_locations VALUES (?, ?, ?, ?, 0)", (i, p, p.rsplit("/", 1)[1], "C:/m"))
    con.execute("INSERT INTO library VALUES (?, ?, 0)", (i, i))
con.commit()
con.close()
logs = []
log = logs.append

st.backup(db, data, "20261115-100000", log)
for k in range(6):
    st.backup(db, data, "20261115-10000%d" % (k + 1), log)
check(len(os.listdir(os.path.join(data, "mixxx-sicherung"))) == st.KEEP_BACKUPS, "Sicherung, die letzten 5 bleiben")

r = st.prepare(db, data, log, "s1", test=True)
check(r == {"ok": 0, "tr": 0, "stars": 0}, "nichts offen: Datenbank unberuehrt")

q = os.path.join(data, "umbenannt", "offen.tsv")
with open(q, "w", encoding="utf-8") as f:
    f.write("C:/m/Alt.mp3\tC:/m/Neu/Alt neu.mp3\nC:/m/Fehlt.mp3\tC:/m/x.mp3\nC:/m/Doppelt.mp3\tC:/m/Neu2.mp3\n")
ms.add([["C:/m/B.mp3", 4, 10]])
open(db + "-journal", "w").close()
before = open(db, "rb").read()
r = st.prepare(db, data, log, "s2", test=True)
check(r.get("blocked") == "Journal" and open(db, "rb").read() == before and os.path.isfile(q) and ms.load(),
      "Journal daneben (Mixxx nicht sauber zu): nichts angefasst, alles bleibt")
os.remove(db + "-journal")

r = st.prepare(db, data, log, "s3", test=True)
c = sqlite3.connect(db)
loc = dict(c.execute("SELECT id, location FROM track_locations").fetchall())
row = c.execute("SELECT filename, directory FROM track_locations WHERE id=1").fetchone()
rat = dict(c.execute("SELECT location, rating FROM library").fetchall())
c.close()
check(r["ok"] == 1 and loc[1] == "C:/m/Neu/Alt neu.mp3" and row == ("Alt neu.mp3", "C:/m/Neu") and loc[4] == "C:/m/Doppelt.mp3",
      "Umbenennen: Pfad, Name, Ordner; vorhandenes Ziel und Unbekanntes uebersprungen: " + str(r))
check(rat[2] == 4 and r["stars"] == 1 and ms.load() == {}, "Sterne eingetragen, Warteschlange leer")
check(not os.path.exists(q) and os.path.isfile(os.path.join(data, "umbenannt", "erledigt-s3.tsv")), "Warteschlange erledigt")
check(os.path.isfile(os.path.join(data, "umbenannt", "mixxxdb-vor-umbenennen-s3.sqlite")), "Sicherung vor dem Aendern")
check(not [f for f in os.listdir(os.path.join(data, "umbenannt")) if f.startswith(".")], "Arbeitskopien aufgeraeumt")
check(sqlite3.connect(db).execute("PRAGMA integrity_check").fetchone()[0] == "ok", "Datenbank in Ordnung")

# Konfiguration: Standard und eigene Werte
cfg = st.load_config(data)
check(cfg["mixxx_bin"] == st.MIXXX_BIN_DEFAULT and cfg["port"] == "Light-Butler", "Standard: Mixxx in Programme, loopMIDI-Anschluss")
with open(os.path.join(data, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"pi": "licht.local", "mixxx_bin": "D:/Mixxx/mixxx.exe"}, f)
cfg = st.load_config(data)
check(cfg["pi"] == "licht.local" and cfg["mixxx_bin"] == "D:/Mixxx/mixxx.exe", "eigene Werte aus config.json")

# Ton-Abgriff: Mac BlackHole, Windows VB-Cable vor Stereomix vor Line-In, eigener Name geht vor
devs = [{"name": "Mikrofon (Realtek)", "max_input_channels": 2}, {"name": "Stereomix (Realtek HD Audio Stereo input)", "max_input_channels": 2},
        {"name": "Line In (Realtek)", "max_input_channels": 2}, {"name": "CABLE Output (VB-Audio Virtual ", "max_input_channels": 2},
        {"name": "Lautsprecher", "max_input_channels": 0}]
check(asnd.default_hints("darwin") == ("blackhole",), "Mac: BlackHole wie bisher")
check(asnd.pick_device(devs, asnd.default_hints("win32")) == 3, "Windows: VB-Cable zuerst")
check(asnd.pick_device(devs[:3], asnd.default_hints("win32")) == 1, "ohne VB-Cable: Stereomix")
check(asnd.pick_device([devs[0], devs[2]], asnd.default_hints("win32")) == 1, "sonst Line-In")
check(asnd.pick_device([devs[0], devs[4]], asnd.default_hints("win32")) is None, "nichts Passendes: keiner (kein Mikrofon)")
check(asnd.pick_device(devs, ("mikrofon",)) == 0, "eigener Name (--audio-device)")
cd = os.path.join(tmp, "Mixxx", "controllers")
check(st.install_mapping(log, cd) == 2 and st.install_mapping(log, cd) == 0 and sorted(os.listdir(cd)) == sorted(st.MAPPING),
      "Mapping in den Controller-Ordner, beim zweiten Mal nichts")
finish("mixxx_start_windows")
