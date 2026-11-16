"""Fehlerbericht 11.11.2026: 83 Lieder mit Umlauten standen zweimal in Mixxx, mit gleichem Pfad. Die Datei auf dem Stick heisst
"Kings of Gu + Punkte nter" (zerlegt), die Playlist "geaenderte Tags" schrieb "Kings of Günter" (zusammengesetzt); Mixxx
vergleicht Byte fuer Byte und nahm sie beim Neu-Einlesen ein zweites Mal auf. Die Doppelte-Seite schlug dann vor, eine zu
loeschen, und damit waere die einzige Datei weg gewesen."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import changed_log                           # noqa: E402
import dupes                                 # noqa: E402

d = os.path.join(tmp, "U-MUSIK", "Almklausi")
os.makedirs(d)
name = "Kings of Günter - Martha.mp3"
nfd, nfc = unicodedata.normalize("NFD", name), unicodedata.normalize("NFC", name)
with open(os.path.join(d, nfd), "wb") as f:
    f.write(b"x")
on_disk = [x for x in os.listdir(d) if unicodedata.normalize("NFC", x) == nfc][0]
P_NFC, P_DISK = os.path.join(d, nfc), os.path.join(d, on_disk)

check(changed_log.disk_form(P_DISK) == P_NFC and changed_log.disk_form(P_NFC) == P_NFC,
      "Fehlerbericht 12.11.2026: Playlists an Mixxx in der Schreibweise von Mixxx (Umlaut als ein Zeichen), nicht wie am Stick")
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
cl = open(os.path.join(ROOT, "mac", "mixxx_bridge", "changed_log.py"), encoding="utf-8").read()
check("changed_log.disk_form(f, dcache)" in src and "disk_form(p, cache)" in cl, "Liste 'geaenderte Tags' und Export schreiben die Schreibweise vom Laufwerk")

# Doppelte-Seite: dieselbe Datei nur einmal
lib = [{"path": P_NFC, "artist": "A", "title": "Martha", "duration": 193}, {"path": P_DISK, "artist": "A", "title": "Martha", "duration": 193}]
check(dupes.groups(lib) == [] if P_NFC != P_DISK else True, "zwei Schreibweisen derselben Datei sind keine Doppelten")
lib.append({"path": os.path.join(tmp, "anders", nfc), "artist": "A", "title": "Martha", "duration": 193})
check([len(g) for g in dupes.groups(lib)] == [2], "eine echte Kopie anderswo bleibt ein Doppeltes")

# Mixxx-Datenbank aufraeumen (beim Start der App, vor Mixxx)
db = os.path.join(tmp, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.executescript("""CREATE TABLE track_locations (id INTEGER PRIMARY KEY, location TEXT, filename TEXT, directory TEXT, fs_deleted INTEGER DEFAULT 0);
CREATE TABLE library (id INTEGER PRIMARY KEY, artist TEXT, title TEXT, duration REAL, location INTEGER, samplerate INTEGER, rating INTEGER, timesplayed INTEGER, mixxx_deleted INTEGER DEFAULT 0, datetime_added TEXT);
CREATE TABLE cues (id INTEGER PRIMARY KEY, track_id INTEGER, type INTEGER, position INTEGER, length INTEGER, hotcue INTEGER, label TEXT, color INTEGER);
CREATE TABLE crate_tracks (crate_id INTEGER, track_id INTEGER);
CREATE TABLE PlaylistTracks (id INTEGER PRIMARY KEY, playlist_id INTEGER, track_id INTEGER, position INTEGER, pl_datetime_added TEXT);""")
con.executemany("INSERT INTO track_locations (id, location) VALUES (?, ?)", [(1, P_NFC), (2, P_DISK)])
con.executemany("INSERT INTO library (id, artist, title, duration, location, rating, timesplayed, datetime_added) VALUES (?, 'A', 'Martha', 193, ?, ?, ?, ?)",
                [(10, 1, 4, 7, "2026-11-10"), (20, 2, 0, 0, "2026-11-11")])
con.execute("INSERT INTO cues (track_id, type, position, hotcue, label) VALUES (10, 1, 500, 0, 'Mein Cue')")
con.executemany("INSERT INTO crate_tracks VALUES (?, ?)", [(5, 10)])
con.executemany("INSERT INTO PlaylistTracks (playlist_id, track_id, position) VALUES (?, ?, ?)", [(1, 10, 1), (2, 10, 1), (2, 20, 2)])
con.commit()
con.close()
ub = os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_uebertragen.py")
run = lambda *x: json.loads(subprocess.run([sys.executable, ub, db, *x], capture_output=True, text=True).stdout)   # noqa: E731
if P_NFC != P_DISK:
    check(run("--nur-zaehlen")["umlaut_doppelt"] == 1, "zaehlen: ein Paar")
    run()
    con = sqlite3.connect(db)
    lib_ = dict(con.execute("SELECT id, mixxx_deleted FROM library").fetchall())
    check(lib_ == {10: 0, 20: 1}, "behalten: Eintrag in der Schreibweise von Mixxx (NFC), der andere ausgeblendet: " + str(lib_))
    check(con.execute("SELECT crate_id FROM crate_tracks WHERE track_id = 10").fetchall() == [(5,)]
          and sorted(con.execute("SELECT playlist_id FROM PlaylistTracks WHERE track_id = 10").fetchall()) == [(1,), (2,)]
          and not con.execute("SELECT 1 FROM PlaylistTracks WHERE track_id = 20").fetchone(),
          "Kisten und Listen bleiben beim behaltenen, ohne doppelte Eintraege in derselben Liste")
    check(con.execute("SELECT label FROM cues WHERE track_id = 10").fetchall() == [("Mein Cue",)], "Hotcues bleiben")
    check(con.execute("SELECT rating, timesplayed, datetime_added FROM library WHERE id = 10").fetchone() == (4, 7, "2026-11-10"),
          "Bewertung, Wiedergaben und das fruehere Datum bleiben")
    # Fehlerbericht 12.11.2026: Stand nach der ersten Fassung (NFC ausgeblendet, NFD sichtbar) und "Bibliothek neu einlesen":
    # Mixxx meldet den NFD-Eintrag als fehlend. Der App-Start dreht es um.
    con.execute("UPDATE library SET mixxx_deleted = 1 WHERE id = 10")
    con.execute("UPDATE library SET mixxx_deleted = 0 WHERE id = 20")
    con.execute("UPDATE track_locations SET fs_deleted = 1 WHERE id = 2")
    con.execute("UPDATE crate_tracks SET track_id = 20")
    con.execute("UPDATE cues SET track_id = 20")
    con.commit()
    con.close()
    check(run("--nur-zaehlen")["umlaut_doppelt"] == 1, "falsch zusammengelegt: erkannt")
    run()
    con = sqlite3.connect(db)
    check(dict(con.execute("SELECT id, mixxx_deleted FROM library WHERE id IN (10, 20)").fetchall()) == {10: 0, 20: 1}
          and con.execute("SELECT fs_deleted FROM track_locations WHERE id = 1").fetchone() == (0,),
          "umgedreht: NFC-Eintrag wieder sichtbar und nicht fehlend, der andere ausgeblendet (nicht mehr bei den fehlenden)")
    check(con.execute("SELECT crate_id FROM crate_tracks WHERE track_id = 10").fetchall() == [(5,)]
          and con.execute("SELECT label FROM cues WHERE track_id = 10").fetchall() == [("Mein Cue",)], "Kisten und Hotcues zurueck auf den behaltenen")
    con.close()
    check(run("--nur-zaehlen")["umlaut_doppelt"] == 0, "zweiter Lauf: nichts mehr")
    check(os.path.isfile(P_DISK), "die Datei bleibt, wie sie ist")
else:
    print("  (Dateisystem speichert beide Schreibweisen gleich: Mixxx-Teil uebersprungen)")
# Fehlerbericht 11.11.2026: Probedatei aus einem Testlauf ("probe", Zwischenordner) landete ueber "geaenderte Tags" in Mixxx
check(changed_log.is_temp("/private/tmp/x/probe.mp3") and changed_log.is_temp("/var/folders/ab/T/p.mp3")
      and not changed_log.is_temp("/Volumes/USB STICK/musik/a.mp3"), "Zwischenordner erkannt")
_s2l = os.environ.pop("S2L_DATA")
_before = os.path.exists(changed_log.log_path())
changed_log.note("/private/tmp/x/probe.mp3")
check(not os.path.exists(changed_log.log_path()) or _before, "echte Liste 'geaenderte Tags' nimmt keine Datei aus einem Zwischenordner auf")
os.environ["S2L_DATA"] = _s2l
con = sqlite3.connect(db)
con.execute("INSERT INTO track_locations (id, location) VALUES (9, '/private/tmp/claude/scratchpad/probe.mp3')")
con.execute("INSERT INTO library (id, title, location) VALUES (90, 'probe', 9)")
con.execute("INSERT INTO PlaylistTracks (playlist_id, track_id, position) VALUES (7, 90, 1)")
con.commit()
con.close()
check(run("--nur-zaehlen")["probe"] == 1, "App-Start: Probedatei in Mixxx gefunden")
run()
con = sqlite3.connect(db)
check(con.execute("SELECT mixxx_deleted FROM library WHERE id = 90").fetchone() == (1,) and not con.execute("SELECT 1 FROM PlaylistTracks WHERE track_id = 90").fetchone(),
      "ausgeblendet und aus den Listen genommen")
con.close()

finish("test_umlaut_doppelt")
