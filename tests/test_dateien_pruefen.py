"""Dateien pruefen (Wunsch von Markus, 08.11.2026, Seite /musik/pruefen): Datenmuell, sonstige Dateien, Dateinamen nach Schema.
In den Papierkorb und Umbenennen nur auf Klick, nur Dateien aus der Pruefung, nie ausserhalb des Musikordners."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

from _common import PI, ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import file_check as fc  # noqa: E402
import music_serve as ms  # noqa: E402

os.environ["S2L_DATA"] = tempfile.mkdtemp(prefix="s2l_pruefen_daten_")   # nie die echten Merkzettel am Mac (Muell-Namen, Warteschlange)

# ---- Schema ----
check(fc.layout("U-MUSIK/Artists/Dr. Alban/Dr. Alban - No Coke.mp3") == "single"
      and fc.layout("U-MUSIK/Artists/Faithless/1996 - Reverence/08 - x.mp3") == "album"
      and fc.layout("U-MUSIK/Compilations/Pacha/14 - x.mp3") == "sampler" and fc.layout("SAMPLES/x.mp3") == "", "Ablage aus dem Pfad")
s = fc.suggest({"artist": "Dr. Alban", "title": "No Coke"}, "U/Artists/Dr. Alban/Dr. Alban - No Coke.mp3")
check(s["ok"], "passender Einzeltitel: ok")
s = fc.suggest({"artist": "Dr. Alban", "title": "No Coke"}, "U/Artists/Dr. Alban/dr alban no coke (1).MP3")
check(not s.get("ok") and s["want"] == "Dr. Alban - No Coke.mp3", "Vorschlag aus den Tags, Endung klein")
check(fc.suggest({"artist": "Faithless", "title": "Flowerstand Man", "tracknumber": "8/12", "album": "Reverence"},
                 "U/Artists/Faithless/1996 - Reverence/08 - Faithless - Reverence - Flowerstand Man.mp3")["ok"],
      "Album: auch mit Albumname im Dateinamen ok (heutige Ablage)")
s = fc.suggest({"artist": "Die Form", "title": "The Saw", "tracknumber": "14"}, "U/Compilations/Pacha Ibiza 2007/Track 14.mp3")
check(s["want"] == "Die Form - The Saw.mp3", "Vorschlag ohne Tracknummer (Wunsch 08.11.2026: die steht im Tag)")
check(fc.suggest({"artist": "Die Form", "title": "The Saw", "tracknumber": "14"}, "U/Compilations/Pacha Ibiza 2007/14 - Pacha Ibiza 2007 - Die Form - The Saw.mp3")["ok"]
      and fc.suggest({"artist": "Die Form", "title": "The Saw"}, "U/Compilations/Pacha Ibiza 2007/Die Form - The Saw.mp3")["ok"],
      "heutige Form mit Nummer gilt weiter, die neue ohne Nummer auch")
check(fc.suggest({"artist": "A", "title": "B"}, "U/Compilations/X/irgendwas.mp3")["want"] == "A - B.mp3", "ohne Nummer im Tag: einfach Interpret - Titel")
check(fc.suggest({"artist": "AC/DC", "title": "T.N.T."}, "U/Artists/ACDC/x.mp3")["want"] == "AC-DC - T.N.T.mp3", "verbotene Zeichen und Punkt am Ende")
check(fc.suggest({"artist": "R.E.M.", "title": "Strange Currencies", "tracknumber": "6", "album": "Monster"},
                 "U/Artists/R.E.M/1994 - Monster/06 - R.E.M. - Monster - Strange Currencies.mp3")["ok"], "Punkte im Namen bleiben (R.E.M.)")
check(fc.suggest({"artist": "Franz Liszt", "title": "Symphonische Dichtung Nr. 4: Orpheus"}, "K/Artists/Franz Liszt/Franz Liszt - Symphonische Dichtung Nr. 4 Orpheus.mp3")["ok"]
      and fc.suggest({"artist": "Xavier Naidoo", "title": "20.000 Meilen", "tracknumber": "2", "album": "Nicht von dieser Welt"},
                     "U/Artists/Xavier Naidoo/1998 - Nicht Von Dieser Welt/02 - Xavier Naidoo - Nicht Von Dieser Welt - 20.000 Meilen.mp3")["ok"],
      "nur Satzzeichen oder Gross/klein anders: passt")
check(fc.suggest({"artist": "", "title": "B"}, "U/Artists/X/y.mp3") is None, "ohne Interpret: nicht pruefbar")
# Namensregeln (Wunsch 08.11.2026, Beispiele von Markus abgenommen)
N = fc.name_for
check(N("Sash!", "Mysterious Times (feat. Tina Cousins) [Original Maxi]") == "Sash - Mysterious Times (Original Maxi)", "feat. weg, ! weg, [ ] -> ( )")
check(N("Bobby McFerrin", "Don’t Worry, Be Happy") == "Bobby McFerrin - Don't Worry, Be Happy", "schraeger Apostroph -> '")
check(N("John Williams; Skywalker Symphony Orchestra", "Star Wars: Throne Room and Finale") == "John Williams u. a. - Star Wars - Throne Room and Finale",
      "; und langer Interpret, Doppelpunkt -> ' - '")
check(N("Earth, Wind & Fire", "September") == "Earth, Wind & Fire - September", "kurze Bandnamen bleiben ganz")
check(N("AC/DC", "Back in Black") == "AC-DC - Back in Black" and N("A / B", "X") == "A & B - X", "/ im Namen und zwischen Namen")
h = N("Hamburg Rundfunk-Sinfonieorchester, Petrus Schneider & Alexander Pervomaisky", "Violin Concerto No. 3 in G Major, K. 216: III. Rondeau: Allegro")
check(h == "Hamburg Rundfunk-Sinfonieorchester u. a. - Violin Concerto No. 3 in G Major, K. 216 - III. Rondeau" and len(h) <= 100, "hoechstens 100 Zeichen, an ' - ' gekuerzt")
check(N("Munich Symphony Orchestra", "Symphony No. 5 in D Major, Op. 107 (Reformation)- Andante - Allegro Con Fuoco")
      == "Munich Symphony Orchestra - Symphony No. 5 in D Major, Op. 107 (Reformation) - Andante", "Kuerzen nicht mitten im Satz")
check(N("Ashed Last", "You (feat. Noemi)") == "Ashed Last - You" and N("X", "Y ft. Z") == "X - Y", "feat./ft. in jeder Form")
check(all(len(N("A" * 30, "Wort " * 40)) <= 100 for _ in [0]) and N("Kein Problem", "Lied (Radio Edit)") == "Kein Problem - Lied (Radio Edit)", "Laenge und Versionen")
check(fc.suggest({"artist": "Sash!", "title": "Mysterious Times (feat. Tina Cousins)"}, "U/Artists/Sash/Sash! - Mysterious Times (feat. Tina Cousins).mp3")["ok"],
      "heute schon passende Namen bleiben passend")
html_c = open(os.path.join(PI, "static", "sm", "check.html"), encoding="utf-8").read()
check('<details id="rules">' in html_c and "Namensregeln" in html_c and "höchstens 100 Zeichen" in html_c, "Hinweistafel Namensregeln auf der Seite")
s = fc.suggest({"artist": "王小娟", "title": "想你的时光"}, "CHILLOUT/Compilations/Afro Meeting 2000/09 - Afro Meeting 2000 - Andy Picchu - De Los Andes.mp3")
check(s["want"] == "" and "anderer Schrift" in s["why"], "chinesische Tags, lateinischer Name: kein Vorschlag, erst Tags pruefen (08.11.2026)")
check(fc.suggest({"artist": "Кино", "title": "Группа крови"}, "U/Artists/Кино/Кино - Группа крови.mp3")["ok"]
      and fc.suggest({"artist": "Beyoncé", "title": "Halo"}, "U/Artists/B/x.mp3")["want"] == "Beyoncé - Halo.mp3", "Schrift auch im Namen oder nur Akzente: normal")

# ---- Pruefung im Ordner ----
tmp = tempfile.mkdtemp(prefix="s2l_pruefen_")
root = os.path.join(tmp, "musik")
files = {"U/Artists/Dr. Alban/Dr. Alban - No Coke.mp3": b"\xff\xfb", "U/Artists/Dr. Alban/._Dr. Alban - No Coke.mp3": b"x",
         "U/Artists/Brings/brings 01.mp3": b"\xff\xfb", "U/Thumbs.db": b"x", "U/desktop.ini": b"x", "U/.DS_Store": b"x", "U/Bad MP3 Copy.bat": b"x",
         "U/Artists/Dr. Alban/cover.jpg": b"\xff\xd8\xff", ".Trashes/501/alt.mp3": b"x"}
for rel, data in files.items():
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data)
songs = [{"path": os.path.join(root, "U/Artists/Dr. Alban/Dr. Alban - No Coke.mp3"), "artist": "Dr. Alban", "title": "No Coke"},
         {"path": os.path.join(root, "U/Artists/Brings/brings 01.mp3"), "artist": "Brings", "title": "Nur nicht aus Liebe weinen", "cues": 3}]
trashed = []


def fake_trash(paths):
    for p in paths:
        trashed.append(p)
        os.remove(p)
    return 0


renamed = []
chk = fc.FileCheck(lambda: root, lambda: songs, lambda p: p, trash=fake_trash, renamed=lambda a, b: renamed.append((a, b)))
chk.scan()
chk.thread.join(10)
st = chk.status()
check(st["state"] == "ready" and sorted(x["rel"] for x in st["muell"]) == ["U/Thumbs.db", "U/desktop.ini"],
      "Datenmuell: Thumbs.db, desktop.ini (nicht der Papierkorb des Sticks)")
check(not any("._" in x["rel"] or "DS_Store" in x["rel"] for x in st["muell"] + st["sonstige"]),
      "Hilfsdateien von macOS (._, .DS_Store) nie vorschlagen: der Mac legt sie wieder an (08.11.2026)")
check([x["rel"] for x in st["sonstige"]] == ["U/Bad MP3 Copy.bat"], "Sonstige: keine Musik, kein Bild (cover.jpg bleibt)")
check(all(x["size"] == 1 for x in st["muell"]) and st["bytes"]["muell"] == 2 and st["bytes"]["sonstige"] == 1 and st["namen"][0]["size"] == 2,
      "Dateigroesse je Zeile und Summe (Wunsch 08.11.2026)")
check(len(st["namen"]) == 1 and st["namen"][0]["want"] == "Brings - Nur nicht aus Liebe weinen.mp3" and st["namen"][0]["mixxx"] == 1,
      "Dateinamen: nur der unpassende, mit Vorschlag und Mixxx-Warnung (Hotcues)")
try:
    chk.trash_files(["../ausserhalb.mp3"])
    check(False, "nur Dateien aus der Pruefliste")
except ValueError:
    check(True, "nur Dateien aus der Pruefliste")
try:
    chk.trash_files(["U/Artists/Dr. Alban/Dr. Alban - No Coke.mp3"])
    check(False, "Musik nicht ueber die Muell-Liste")
except ValueError:
    check(True, "Musik nicht ueber die Muell-Liste")
r = chk.trash_files(["U/Thumbs.db"])
check(r["gone"] == 1 and not os.path.exists(os.path.join(root, "U/Thumbs.db")) and "U/Thumbs.db" not in [x["rel"] for x in chk.status()["muell"]], "einzeln in den Papierkorb")
chk.trash_all_junk()
for _ in range(50):
    if not chk.status()["job"]:
        break
    time.sleep(0.05)
check(chk.status()["n"]["muell"] == 0 and os.path.exists(os.path.join(root, "U/Artists/Dr. Alban/cover.jpg")), "alle Datenmuell-Dateien weg, Bilder und Musik bleiben")
r = chk.rename(songs[1]["path"], "Brings - Nur nicht aus Liebe weinen")
newp = os.path.join(root, "U/Artists/Brings/Brings - Nur nicht aus Liebe weinen.mp3")
check(r["ok"] and os.path.isfile(newp) and renamed and chk.status()["n"]["namen"] == 0, "umbenannt im selben Ordner, Ordner-Liste neu einlesen")
try:
    chk.rename(songs[0]["path"], "x")
    check(False, "nur Lieder aus der Namensliste")
except ValueError:
    check(True, "nur Lieder aus der Namensliste")
open(os.path.join(root, "U/Artists/Brings/b.mp3"), "wb").write(b"\xff\xfb")
songs.append({"path": os.path.join(root, "U/Artists/Brings/b.mp3"), "artist": "Brings", "title": "Nur nicht aus Liebe weinen"})
chk.scan()
chk.thread.join(10)
try:
    chk.rename(songs[2]["path"], "Brings - Nur nicht aus Liebe weinen")
    check(False, "nie ueberschreiben")
except ValueError:
    check(True, "nie ueberschreiben")

# ---- HTTP und Seite ----
srv = ms.MusicServer([], port=0)
check(srv.check is None, "ohne Bruecke: keine Pruefung")
srv.check = chk
srv.start()
base = "http://127.0.0.1:%d" % srv.port
d = json.loads(urllib.request.urlopen(base + "/check", timeout=5).read())
check(d["state"] == "ready" and "namen" in d, "GET /check")
req = urllib.request.Request(base + "/check", data=json.dumps({"op": "rename", "p": "/x", "to": "y"}).encode(), method="POST")
try:
    urllib.request.urlopen(req, timeout=5)
    check(False, "Fehler als 400")
except urllib.error.HTTPError as e:
    check(e.code == 400, "Fehler als 400")
srv.stop()
for inst in ("mac/mixxx_bridge/install_launcher.sh", "mac/helper/install_helper.sh"):
    check("file_check.py" in open(os.path.join(ROOT, inst), encoding="utf-8").read(), inst + " kopiert file_check.py")
html = open(os.path.join(PI, "static", "sm", "check.html"), encoding="utf-8").read()
js = open(os.path.join(PI, "static", "sm", "check.js"), encoding="utf-8").read()
check("fmt(x.size)" in js and "🗑" in html + js and "mac('trash', { items: [rel] })" in js and "music + '/trash'" not in js and "data-mdel" not in js,
      "Mistkuebel nur bei Datenmuell und Sonstigen, nicht bei Dateinamen")
check("mac('keep', { p })" in js and ">So lassen<" in js, "Dateinamen: So lassen")
check('data-play="' in js and "music + '/audio?p='" in js and 'id="ppos"' in html and "audio.currentTime = d * $('ppos').value / 1000" in js,
      "Dateinamen: anhoeren mit Leiste zum Spulen (Wunsch 08.11.2026)")
check("hat in Mixxx Hotcues oder Kisten" in js, "Warnung vor dem Umbenennen von Liedern mit Mixxx-Daten")
check(subprocess.run(["node", "--check", os.path.join(PI, "static", "sm", "check.js")], capture_output=True).returncode == 0, "check.js ohne Fehler")
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
check('path == "/musik/pruefen"' in api and '/musik/pruefen?t=namen' in open(os.path.join(PI, "static", "sm", "care.js"), encoding="utf-8").read(), "Seite und Knopf in der Musik-DB")
# ---- Umbenennen in Mixxx nachziehen (08.11.2026): Warteschlange + mixxx_umbenennen.sh vor dem Start von Mixxx ----
import shutil  # noqa: E402
import sqlite3  # noqa: E402
qf = fc.FileCheck.queue_path()
check(os.path.isfile(qf) and open(qf, encoding="utf-8").read().strip().split("\t")
      == [songs[1]["path"], os.path.join(root, "U/Artists/Brings/Brings - Nur nicht aus Liebe weinen.mp3")],
      "Umbenennung gemerkt (alter Mixxx-Pfad, neuer Pfad)")
check(chk.status()["pending"] == 1, "Seite zeigt: wartet auf den naechsten Start der Mixxx-App")
db = os.path.join(tmp, "mixxxdb.sqlite")
con = sqlite3.connect(db)
con.executescript("""CREATE TABLE track_locations (id INTEGER PRIMARY KEY AUTOINCREMENT, location varchar(512) UNIQUE, filename varchar(512),
                     directory varchar(512), filesize INTEGER, fs_deleted INTEGER, needs_verification INTEGER);
                     CREATE TABLE cues (id INTEGER PRIMARY KEY, track_id INTEGER, position INTEGER);""")
old = songs[1]["path"]
con.execute("INSERT INTO track_locations (id, location, filename, directory, fs_deleted) VALUES (7, ?, ?, ?, 0)", (old, os.path.basename(old), os.path.dirname(old)))
con.execute("INSERT INTO track_locations (id, location, filename, directory, fs_deleted) VALUES (8, '/x/Dont''s.mp3', 'Dont''s.mp3', '/x', 0)")
con.execute("INSERT INTO cues (track_id, position) VALUES (7, 4410)")
con.commit()
con.close()
with open(qf, "a", encoding="utf-8") as fh:
    fh.write("/x/Dont's.mp3\t/x/Don't Stop.mp3\n/gibt/es/nicht.mp3\t/gibt/es/neu.mp3\n")
sh = os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_umbenennen.sh")
r = subprocess.run(["bash", sh, db], capture_output=True, text=True, env=dict(os.environ, S2L_TEST="1"))
con = sqlite3.connect(db)
rows = dict(con.execute("SELECT id, location FROM track_locations").fetchall())
check(rows[7].endswith("/Brings - Nur nicht aus Liebe weinen.mp3") and con.execute("SELECT filename FROM track_locations WHERE id=7").fetchone()[0]
      == "Brings - Nur nicht aus Liebe weinen.mp3", "Mixxx: neuer Pfad und Dateiname im selben Eintrag")
check(con.execute("SELECT count(*) FROM cues WHERE track_id=7").fetchone()[0] == 1, "Hotcues haengen weiter am Lied (gleiche Nummer)")
check(rows[8] == "/x/Don't Stop.mp3", "Hochkomma im Namen sicher")
con.close()
qd = os.path.dirname(qf)
check(not os.path.exists(qf) and any(n.startswith("erledigt-") for n in os.listdir(qd)) and any(n.startswith("mixxxdb-vor-umbenennen-") for n in os.listdir(qd)),
      "Warteschlange erledigt, Sicherungskopie angelegt")
check("2 Pfade in Mixxx nachgezogen, 1 uebersprungen" in r.stdout, "Meldung im Log: " + r.stdout.strip()[-120:])
with open(qf, "w", encoding="utf-8") as fh:
    fh.write("/x/Don't Stop.mp3\t" + old + "\n")
con = sqlite3.connect(db)
con.execute("INSERT INTO track_locations (location) VALUES (?)", (old,))
con.commit()
con.close()
subprocess.run(["bash", sh, db], capture_output=True, text=True, env=dict(os.environ, S2L_TEST="1"))
con = sqlite3.connect(db)
check(con.execute("SELECT location FROM track_locations WHERE id=8").fetchone()[0] == "/x/Don't Stop.mp3", "neuer Pfad schon in Mixxx (neu eingelesen): nichts kaputt machen")
con.close()
# Fehlerbericht 08.11.2026: macOS verbot das Schreiben, das Skript legte alles als erledigt ab. Jetzt bleibt die Warteschlange.
ro = tempfile.mkdtemp(prefix="s2l_ro_")
rdb = os.path.join(ro, "m.sqlite")
con = sqlite3.connect(rdb)
con.execute("CREATE TABLE track_locations (id INTEGER PRIMARY KEY, location TEXT UNIQUE, filename TEXT, directory TEXT, fs_deleted INTEGER)")
con.execute("INSERT INTO track_locations VALUES (1, '/a/x.mp3', 'x.mp3', '/a', 0)")
con.commit()
con.close()
rq = os.path.join(ro, "q", "offen.tsv")
os.makedirs(os.path.dirname(rq))
open(rq, "w", encoding="utf-8").write("/a/x.mp3\t/a/y.mp3\n")
os.chmod(rdb, 0o444)
os.chmod(ro, 0o555)
r = subprocess.run(["bash", sh, rdb, rq], capture_output=True, text=True, env=dict(os.environ, S2L_TEST="1"))
os.chmod(ro, 0o755)
os.chmod(rdb, 0o644)
check(os.path.exists(rq) and "Zurueckkopieren" in r.stdout and os.path.exists(os.path.join(ro, "q", "gesperrt.txt")),
      "Datenbank gesperrt: Warteschlange bleibt, Vermerk fuer die Seite")
fcq = fc.FileCheck(lambda: ro, lambda: [], lambda p: p)
fcq.queue_path = lambda: rq
check(fcq.status()["pending"] == 1 and fcq.status()["blocked"], "Seite sieht: wartet und gesperrt")
r = subprocess.run(["bash", sh, rdb, rq], capture_output=True, text=True, env=dict(os.environ, S2L_TEST="1"))
con = sqlite3.connect(rdb)
check(con.execute("SELECT location FROM track_locations").fetchone()[0] == "/a/y.mp3" and not os.path.exists(rq)
      and not os.path.exists(os.path.join(ro, "q", "gesperrt.txt")), "wieder erlaubt: eingetragen, Vermerk weg")
con.close()
# Weg ueber eine Kopie (sqlite3 darf im Ordner von Mixxx nichts oeffnen, cp schon): aendern, pruefen, zurueckkopieren
con = sqlite3.connect(rdb)
con.execute("INSERT INTO track_locations VALUES (2, '/a/D''s.mp3', 'D''s.mp3', '/a', 0)")
con.commit()
con.close()
open(rq, "w", encoding="utf-8").write("/a/D's.mp3\t/a/Don't.mp3\n")
r = subprocess.run(["bash", sh, rdb, rq], capture_output=True, text=True, env=dict(os.environ, S2L_TEST="1", S2L_KOPIE="1"))
con = sqlite3.connect(rdb)
check(con.execute("SELECT location FROM track_locations WHERE id=2").fetchone()[0] == "/a/Don't.mp3" and "(kopie): 1 Pfade" in r.stdout
      and not os.path.exists(rq) and not [n for n in os.listdir(os.path.join(ro, "q")) if n.startswith(".arbeit")], "ueber die Kopie eingetragen, Arbeitskopie weg")
con.close()
open(rq, "w", encoding="utf-8").write("/a/y.mp3\t/a/z.mp3\n")
before = open(rdb, "rb").read()
os.chmod(rdb, 0o444)                                    # Zurueckkopieren verboten
r = subprocess.run(["bash", sh, rdb, rq], capture_output=True, text=True, env=dict(os.environ, S2L_TEST="1", S2L_KOPIE="1"))
os.chmod(rdb, 0o644)
check(open(rdb, "rb").read() == before and os.path.exists(rq) and "Zurueckkopieren" in r.stdout and "1 bleiben" in r.stdout,
      "Zurueckkopieren verboten: Datenbank unveraendert, Umbenennung wartet")
open(rq, "w", encoding="utf-8").write("/a/y.mp3\t/a/z.mp3\n")
open(rdb + "-journal", "wb").write(b"x")                # Mixxx nicht sauber beendet
r = subprocess.run(["bash", sh, rdb, rq], capture_output=True, text=True, env=dict(os.environ, S2L_TEST="1", S2L_KOPIE="1"))
os.remove(rdb + "-journal")
check(open(rdb, "rb").read() == before and os.path.exists(rq) and "nicht sauber beendet" in r.stdout, "Journal daneben: nichts anfassen")
mj = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check("NICHT „Bibliothek neu einlesen“" in mj and "Festplattenvollzugriff" not in mj, "Musik-DB warnt vor dem Neu-Einlesen, solange Umbenennungen warten")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check('bash "$BASE/mixxx_umbenennen.sh" "$SRC"' in inst and inst.index("mixxx_umbenennen.sh\" \"$SRC\"") < inst.index('cp "$SRC" "$BASE/mixxxdb.sqlite.neu"')
      and '"$HERE/mixxx_umbenennen.sh"' in inst, "Startskript zieht nach, bevor Mixxx startet und bevor die Kopie entsteht")
# So lassen: kommt nicht wieder
chk2 = fc.FileCheck(lambda: root, lambda: [{"path": os.path.join(root, "U/Artists/Brings/b.mp3"), "artist": "Brings", "title": "Anders"}], lambda p: p)
chk2.scan()
chk2.thread.join(10)
pth = os.path.join(root, "U/Artists/Brings/b.mp3")
check(chk2.status()["n"]["namen"] == 1 and chk2.keep(pth)["ok"] and chk2.status()["n"]["namen"] == 0, "So lassen: aus der Liste")
chk2.scan()
chk2.thread.join(10)
check(chk2.status()["n"]["namen"] == 0 and pth in chk2.kept(), "So lassen: auch nach erneutem Pruefen nicht wieder")
# Reiter "So gelassen" (Wunsch 08.11.2026): ansehen und doch noch umbenennen
st2 = chk2.status()
check(st2["n"]["belassen"] == 1 and st2["belassen"][0]["path"] == pth and st2["belassen"][0]["want"] == "Brings - Anders.mp3", "So gelassen: mit Vorschlag sichtbar")
r = chk2.unkeep(pth)
check(r["ok"] and r["item"]["want"] == "Brings - Anders.mp3" and pth not in chk2.kept() and chk2.status()["n"]["namen"] == 1
      and chk2.status()["n"]["belassen"] == 0, "Doch umbenennen: zurueck in die Namensliste")
chk2.keep(pth)
check(chk2.status()["n"]["belassen"] == 1, "So lassen: sofort im Reiter So gelassen")
cj = open(os.path.join(PI, "static", "sm", "check.js"), encoding="utf-8").read()
check("mac('unkeep', { p })" in cj and "heldRow" in cj and 'data-t="belassen"' in open(os.path.join(PI, "static", "sm", "check.html"), encoding="utf-8").read(),
      "Seite: Reiter So gelassen mit Doch umbenennen")
# Gleiche Dateinamen (Wunsch 08.11.2026: kein Name doppelt, fuer einen spaeteren gemeinsamen Ordner)
r3 = os.path.join(tmp, "musik3")
for rel in ["U/Artists/Queen/Queen - Intro.mp3", "U/Artists/Abba/queen - intro.MP3", "U/Artists/Queen/1990 - Live/03 x.mp3",
            "U/Artists/Queen/1991 - Best/04 y.mp3", "U/Artists/Queen/Abba - Dancing.mp3", "U/Artists/Queen/1991 - Best/07 dancing.mp3"]:
    p = os.path.join(r3, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"\xff\xfb")
P3 = lambda rel: os.path.join(r3, rel)
songs3 = [{"path": P3("U/Artists/Queen/1990 - Live/03 x.mp3"), "artist": "Queen", "title": "Intro", "album": "Live"},
          {"path": P3("U/Artists/Queen/1991 - Best/04 y.mp3"), "artist": "Queen", "title": "Intro"},
          {"path": P3("U/Artists/Queen/1991 - Best/07 dancing.mp3"), "artist": "Abba", "title": "Dancing"}]
chk3 = fc.FileCheck(lambda: r3, lambda: songs3, lambda p: p)
chk3.scan()
chk3.thread.join(10)
st3 = chk3.status()
check(st3["n"]["gleich"] == 1 and len(st3["gleich"][0]["rels"]) == 2 and st3["gleich"][0]["name"].lower() == "queen - intro.mp3",
      "gleiche Namen: Gross/klein zaehlt nicht, eine Gruppe mit beiden Pfaden")
g0 = st3["gleich"][0]
check(g0["files"][0]["keep"] and not g0["files"][1]["keep"] and g0["files"][1]["want"].lower() != "queen - intro.mp3",
      "Gleiche Namen: kuerzester Pfad behaelt den Namen, die anderen bekommen einen Vorschlag")
w = {x["rel"]: x for x in st3["namen"]}
check(w["U/Artists/Queen/1990 - Live/03 x.mp3"]["want"] == "Queen - Intro (Live).mp3" and w["U/Artists/Queen/1990 - Live/03 x.mp3"]["clash"],
      "Vorschlag schon vergeben: Album in Klammern")
check(w["U/Artists/Queen/1991 - Best/04 y.mp3"]["want"] == "Queen - Intro (Best).mp3", "Album aus dem Ordner ohne Jahr")
check(w["U/Artists/Queen/1991 - Best/07 dancing.mp3"]["want"] == "Abba - Dancing (Best).mp3", "auch wenn der Name nur anders geschrieben schon da ist")
wants = [x["want"].lower() for x in st3["namen"]]
check(len(wants) == len(set(wants)), "keine zwei Vorschlaege gleich")
try:
    chk3.rename(P3("U/Artists/Queen/1991 - Best/04 y.mp3"), "Abba - Dancing")
    check(False, "Umbenennen auf einen vergebenen Namen muss scheitern")
except ValueError as e:
    check("gibt es schon" in str(e) and os.path.exists(P3("U/Artists/Queen/1991 - Best/04 y.mp3")), "Umbenennen auf vergebenen Namen gesperrt")
check(chk3.rename(P3("U/Artists/Queen/1991 - Best/04 y.mp3"), "Queen - Intro (Best)")["ok"], "Vorschlag mit Album geht")
try:
    chk3.rename(P3("U/Artists/Queen/1990 - Live/03 x.mp3"), "Queen - Intro (Best)")
    check(False, "gerade vergebener Name muss gesperrt sein")
except ValueError:
    check(True, "gerade umbenannter Name zaehlt sofort als vergeben")
# Fehlerbericht 08.11.2026 ("Eric Lévi - Era" -> "Era - Era"): erst pruefen, wenn die Tags der Dateien gelesen sind
state = {"ready": False, "polls": 0}


def fake_sleep(sec):
    state["polls"] += 1
    if state["polls"] >= 3:
        state["ready"] = True


chk4 = fc.FileCheck(lambda: r3, lambda: songs3, lambda p: p, ready=lambda: state["ready"], sleep=fake_sleep)
chk4.scan()
chk4.thread.join(10)
check(state["polls"] == 3 and chk4.status()["state"] == "ready", "Pruefung wartet auf die Tags der Dateien")
src_b = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("ready=fw.file_tags_ready" in src_b and src_b.count("ready=fw.file_tags_ready") == 2, "Bruecke/Helfer: Pruefung und Genre-Editor warten auf die Ordner-Liste")
check("st.state === 'wait'" in open(os.path.join(PI, "static", "sm", "check.js"), encoding="utf-8").read(), "Seite zeigt das Warten")
# Tag-Editor auf der Seite: nach dem Speichern neuer Vorschlag (Wunsch 08.11.2026)
songs3[2]["artist"], songs3[2]["title"] = "王小娟", "想你的时光"
chk3.scan()
chk3.thread.join(10)
pa = P3("U/Artists/Queen/1991 - Best/07 dancing.mp3")
check(next(x for x in chk3.status()["namen"] if x["path"] == pa)["want"] == "", "falsche Tags: erst kein Vorschlag")
songs3[2]["artist"], songs3[2]["title"] = "Abba", "Dancing Queen"
r = chk3.retag(pa)
check(not r["gone"] and r["item"]["want"] == "Abba - Dancing Queen.mp3" and not r["item"]["why"], "nach Tag-Editor: neuer Vorschlag")
songs3[2]["artist"], songs3[2]["title"] = "Abba", "Dancing"
r = chk3.retag(pa)
check(r["item"]["want"] == "Abba - Dancing (Best).mp3" and r["item"]["clash"], "neuer Vorschlag auch nie doppelt")
songs3[2]["artist"], songs3[2]["title"] = "07", "dancing"
check(chk3.retag(pa)["gone"] and pa not in [x["path"] for x in chk3.status()["namen"]], "Name passt jetzt: aus der Liste")
js = open(os.path.join(PI, "static", "sm", "check.js"), encoding="utf-8").read()
check("SM.tagEdit({ path: p, dur: 0 }, music" in js and "mac('retag', { p })" in js and "🏷 Tags" in js
      and "tagedit.js" in open(os.path.join(PI, "static", "sm", "check.html"), encoding="utf-8").read(), "Knopf Tags in den Dateinamen-Zeilen")
# Gleiche Namen sofort beheben (Wunsch 08.11.2026)
r5 = os.path.join(tmp, "musik5")
for rel in ["U/Artists/Abba/Abba - Waterloo.mp3", "U/Artists/Abba/1974 - Waterloo/Abba - Waterloo.mp3"]:
    p = os.path.join(r5, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"\xff\xfb" * (3 if "1974" in rel else 1))
songs5 = [{"path": os.path.join(r5, "U/Artists/Abba/1974 - Waterloo/Abba - Waterloo.mp3"), "artist": "Abba", "title": "Waterloo", "cues": 2}]
moved5 = []
chk5 = fc.FileCheck(lambda: r5, lambda: songs5, lambda p: p, renamed=lambda a, b: moved5.append((a, b)))
chk5.scan()
chk5.thread.join(10)
g5 = chk5.status()["gleich"][0]
f2 = g5["files"][1]
check(f2["want"] == "Abba - Waterloo (Waterloo).mp3" and f2["mixxx"] and not f2["twin"], "Vorschlag mit Albumordner (ohne Jahr), Mixxx-Lied erkannt: " + f2["want"])
r = chk5.rename_file(f2["file"], f2["want"])
newp = os.path.join(r5, "U/Artists/Abba/1974 - Waterloo/Abba - Waterloo (Waterloo).mp3")
check(r["ok"] and os.path.isfile(newp) and chk5.status()["n"]["gleich"] == 0 and moved5 and moved5[0][1] == newp, "umbenannt, Gruppe weg, Merkzettel mitgenommen")
try:
    chk5.rename_file(newp, "x")
    check(False, "nur Dateien aus Gleiche Namen")
except ValueError:
    check(True, "nur Dateien aus Gleiche Namen")
# Tags unter dem Vorschlag (Wunsch 08.11.2026)
import tag_edit  # noqa: E402
r6 = os.path.join(tmp, "musik6")
f6 = os.path.join(r6, "U/Artists/X/1999 - Best/03 x.mp3")
os.makedirs(os.path.dirname(f6))
open(f6, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
tag_edit.write_tags(f6, {"title": "Lied", "artist": "X", "album": "Best", "track": "3"})
chk6 = fc.FileCheck(lambda: r6, lambda: [{"path": f6, "artist": "X", "title": "Lied", "album": "Best"}], lambda p: p)
chk6.scan()
chk6.thread.join(10)
t6 = chk6.status()["namen"][0]["tags"]
check(t6.get("title") == "Lied" and t6.get("album") == "Best" and t6.get("albumartist") == "" and t6.get("track") == "3", "Tags der Datei in der Namensliste: " + str(t6))
check("tagLine(x)" in js and "'Album-Interpret'" in js, "Seite zeigt Titel, Interpret, Album, Album-Interpret, Track")
check("mac('rename_file'" in js and "data-sren" in js and "SM.ask('„' + it.name" not in js, "Seite: Gleiche Namen mit Umbenennen; Umbenennen ohne Nachfrage")
check("sameRow" in js and 'data-t="gleich"' in open(os.path.join(PI, "static", "sm", "check.html"), encoding="utf-8").read()
      and "/musik/pruefen?t=gleich" in open(os.path.join(PI, "static", "sm", "care.js"), encoding="utf-8").read(), "Reiter Gleiche Namen und Schritt in der Datenpflege")
cj2 = open(os.path.join(PI, "static", "sm", "check.js"), encoding="utf-8").read()
ch2 = open(os.path.join(PI, "static", "sm", "check.html"), encoding="utf-8").read()
check("<s>" not in cj2 and 'class="oldn"' in cj2 and ".oldn {" in ch2 and "background: #1f4d31" in ch2,
      "Dateinamen: alter Name rot hinterlegt (nicht durchgestrichen), neuer gruen (Variante A, 08.11.2026)")
# ---- leere Ordner und kurze Stuecke (Wunsch 09.11.2026) ----
r7 = os.path.join(tmp, "m7")
for rel, data in {"A/Leer/Unter/._x.mp3": b"x", "A/Bild/Folder.jpg": b"x", "A/Bild/Tief/info.txt": b"x", "A/Voll/Unter/lied.wav": b"x",
                  "A/Voll/cover.jpg": b"x", "S/kurz.mp3": None, "S/lang.mp3": None, "S/ohne.mp3": None, "S/nurE.mp3": None, "S/mik.mp3": None}.items():
    p = os.path.join(r7, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data or (b"\xff\xfb\x90\x00" + b"\x00" * 400))
os.makedirs(os.path.join(r7, "A/GanzLeer"))
tag_edit.write_tags(os.path.join(r7, "S/kurz.mp3"), {"title": "Jingle", "bpm": "140", "key": "Em"})
tag_edit.write_tags(os.path.join(r7, "S/lang.mp3"), {"title": "Lied", "bpm": "120", "key": "Am"})
tag_edit.write_tags(os.path.join(r7, "S/ohne.mp3"), {"title": "Sample"})
import energy_level  # noqa: E402
energy_level.write_energy_tag(os.path.join(r7, "S/kurz.mp3"), 4)
energy_level.write_energy_tag(os.path.join(r7, "S/nurE.mp3"), 3)
tag_edit.write_tags(os.path.join(r7, "S/mik.mp3"), {"energy": "7"})        # wie Mixed In Key (ohne unser Kennzeichen)
songs7 = [{"path": os.path.join(r7, "S/kurz.mp3"), "artist": "", "title": "Jingle", "duration": 13.8},
          {"path": os.path.join(r7, "S/lang.mp3"), "artist": "", "title": "Lied", "duration": 200.0},
          {"path": os.path.join(r7, "S/ohne.mp3"), "artist": "", "title": "Sample", "duration": 5.0},
          {"path": os.path.join(r7, "S/nurE.mp3"), "artist": "", "title": "E", "duration": 9.0},
          {"path": os.path.join(r7, "S/mik.mp3"), "artist": "", "title": "M", "duration": 9.0}]
gone7 = []


def trash7(paths):
    for p in paths:
        gone7.append(p)
        shutil.rmtree(p)
    return 0


chk7 = fc.FileCheck(lambda: r7, lambda: songs7, lambda p: p, trash=trash7)
chk7.scan()
chk7.thread.join(10)
st7 = chk7.status()
leer = {x["rel"]: x for x in st7["leer"]}
check(sorted(leer) == ["A/Bild", "A/GanzLeer", "A/Leer"] and leer["A/Bild"]["files"] == 2 and leer["A/GanzLeer"]["files"] == 0,
      "leere Ordner: ohne Musik auch in Unterordnern, nur der oberste, Bilder/Texte zaehlen nicht als Musik: " + str(sorted(leer)))
check([x["rel"] for x in st7["kurz"]] == ["S/kurz.mp3", "S/nurE.mp3"] and st7["kurz"][0]["bpm"] == "140" and st7["kurz"][1]["energy"] == "3",
      "kurze Stuecke: nur unter 30 s mit BPM, Tonart oder unserer Energie (Mixed In Key zaehlt nicht): " + str([x["rel"] for x in st7["kurz"]]))
try:
    chk7.trash_dirs(["A/Voll"])
    check(False, "Ordner mit Musik laesst sich nicht loeschen")
except ValueError:
    check(True, "Ordner mit Musik laesst sich nicht loeschen")
open(os.path.join(r7, "A/Leer/neu.mp3"), "wb").write(b"x")
try:
    chk7.trash_dirs(["A/Leer"])
    check(False, "inzwischen Musik drin: bleibt")
except ValueError:
    check(os.path.isdir(os.path.join(r7, "A/Leer")), "inzwischen Musik drin: bleibt")
res = chk7.trash_dirs(["A/Bild", "A/GanzLeer"])
check(res["gone"] == 2 and not os.path.exists(os.path.join(r7, "A/Bild")) and chk7.status()["n"]["leer"] == 1, "leere Ordner in den Papierkorb")
res = chk7.clear_short()
kt = tag_edit.read_tags(os.path.join(r7, "S/kurz.mp3"))["fields"]
lt = tag_edit.read_tags(os.path.join(r7, "S/lang.mp3"))["fields"]
check(res["done"] == 2 and energy_level.own_energy(os.path.join(r7, "S/kurz.mp3")) == "" and energy_level.own_energy(os.path.join(r7, "S/nurE.mp3")) == ""
      and tag_edit.read_tags(os.path.join(r7, "S/mik.mp3"))["fields"]["energy"] == "7", "Leeren nimmt unsere Energie mit, Mixed In Key bleibt")
check(kt["bpm"] == "" and kt["key"] == "" and kt["title"] == "Jingle" and lt["bpm"] == "120" and chk7.status()["n"]["kurz"] == 0,
      "Leeren: nur BPM und Tonart der kurzen Stuecke, Titel und lange Lieder bleiben")
ms_src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
cj3 = open(os.path.join(PI, "static", "sm", "check.js"), encoding="utf-8").read()
check('op == "trash_dirs"' in ms_src and 'op == "clear_short"' in ms_src and "data-ddel" in cj3 and "data-sclr" in cj3 and "mac('clear_short')" in cj3,
      "Mac und Seite: Reiter Leere Ordner und Kurze Stuecke")
# Fehlerbericht 09.11.2026: nach dem Umbenennen mit Zusatz (Album) oder (2) kam beim naechsten Pruefen derselbe Name als Vorschlag
r8 = os.path.join(tmp, "m8")
f8 = {"X/A - Lied.mp3": ("A", "Lied", "Best"), "Y/A - Lied (Best Of).mp3": ("A", "Lied", "Anderes Album"), "Z/A - Lied (2).mp3": ("A", "Lied", ""),
      "W/A - Lied (Live).mp3": ("A", "Lied", "")}
songs8 = []
for rel, (a, t, al) in f8.items():
    p = os.path.join(r8, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
    songs8.append({"path": p, "artist": a, "title": t, "album": al})
chk8 = fc.FileCheck(lambda: r8, lambda: songs8, lambda p: p)
chk8.scan()
chk8.thread.join(10)
n8 = chk8.status()["namen"]
check(n8 == [], "schon mit Zusatz umbenannt: kein Vorschlag mehr (" + str([(x["rel"], x["want"]) for x in n8]) + ")")
# Wunsch 09.11.2026: gleicher Titel mehrmals auf einer CD -> Tracknummer hinten ("Interpret - Titel - 04"), statt "(2)"
mk = lambda d, a, t, al, nr: {"path": f"/m/MEDITATION/Artists/{d}/x{nr.split('/')[0]}.mp3", "artist": a, "title": t, "album": al, "tracknumber": nr}
hay = [mk("Balance", "Louise Hay", "Balance Für Körper Und Seele", al, nr) for nr, al in (("4/9", ""), ("5", ""), ("2", "Balance Für Körper Und Seele"))]
gp = [mk("GP", "Grand Prix", "Grand Prix - Grand Prix", "Grand Prix", str(n)) for n in (1, 2, 3)]
two = [mk("Two", "A", "Lied", "Best", str(n)) for n in (1, 5)]
mg = fc.multi_groups([(r["path"], r) for r in hay + gp + two])
check(mg.get(fc.multi_key(hay[0]["path"], hay[0])) == "nr" and mg.get(fc.multi_key(gp[0]["path"], gp[0])) == "tag" and fc.multi_key(two[0]["path"], two[0]) not in mg,
      "CD mit gleichem Titel: Nummer; Titel = CD-Name/Interpret: erst Tags; nur zwei: eher Doppelte " + str(mg))
sh = fc.suggest(dict(hay[0], path=""), "MEDITATION/Artists/Balance/Louise Hay - Balance Für Körper Und Seele (2).mp3", "nr")
check(sh["want"] == "Louise Hay - Balance Für Körper Und Seele - 04.mp3", "Vorschlag mit Track hinten: " + sh["want"])
check(fc.suggest(dict(hay[0], path=""), "MEDITATION/Artists/Balance/Louise Hay - Balance Für Körper Und Seele - 04.mp3", "nr").get("ok"), "so benannt: passt")
st = fc.suggest(dict(gp[0], path=""), "MEDITATION/Artists/GP/Grand Prix - Grand Prix - Grand Prix (2).mp3", "tag")
check(st["want"] == "" and "Shazam" in st["why"], "falsche CD-Tags: kein Vorschlag, Hinweis auf Shazam")
# Fehlerbericht 09.11.2026: Akzente im Namen ("Préludes"): der Stick liefert die Pfade zerlegt (NFD), Mixxx zusammengesetzt (NFC);
# die Datei galt als "fremde" mit gleichem Namen, Vorschlag "(2)" statt dem schon passenden "(Klavier)"
import unicodedata  # noqa: E402
r9 = os.path.join(tmp, "m9")
nfd = lambda x: unicodedata.normalize("NFD", x)  # noqa: E731
songs9 = []
for rel in ("K/Compilations/Klavier/A - Préludes.mp3", "K/Compilations/Klavier/A - Préludes (Klavier).mp3"):
    p = os.path.join(r9, nfd(rel))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
    songs9.append({"path": unicodedata.normalize("NFC", os.path.join(r9, rel)), "artist": "A", "title": "Préludes", "album": "Klavier", "tracknumber": "1"})
chk9 = fc.FileCheck(lambda: r9, lambda: songs9, lambda p: p)
chk9.scan()
chk9.thread.join(10)
n9 = chk9.status()["namen"]
check(n9 == [], "Akzente (NFD am Stick, NFC in Mixxx): schon passender Name mit Zusatz bleibt " + str([(x["name"], x["want"]) for x in n9]))
# Fehlerbericht 09.11.2026 (Gleiche Namen, "Original-Künstlern"): Umbenennen probiert jede Schreibweise, "._" geht mit
r10 = tempfile.mkdtemp(prefix="s2l_ren_")
a10 = os.path.join(r10, unicodedata.normalize("NFD", "Kröger.mp3"))
open(a10, "wb").write(b"x")
open(os.path.join(r10, "._" + unicodedata.normalize("NFD", "Kröger.mp3")), "wb").write(b"y")
fc.rename_any(os.path.join(r10, "Kröger.mp3"), os.path.join(r10, "Kröger (Disc 2).mp3"))
check(sorted(os.listdir(r10)) == ["._Kröger (Disc 2).mp3", "Kröger (Disc 2).mp3"], "umbenannt samt Begleitdatei " + str(os.listdir(r10)))
src10 = open(os.path.join(ROOT, "mac", "mixxx_bridge", "file_check.py"), encoding="utf-8").read()
check(src10.count("rename_any(f, new)") == 2 and "fc.rename_any(f, new)" in open(os.path.join(ROOT, "mac", "mixxx_bridge", "cd_assist.py"), encoding="utf-8").read(),
      "Dateinamen, Gleiche Namen und CD-Assistent nutzen es")
# Bilder vom Windows Media Player (Wunsch 09.11.2026): Muell nur, wenn der Ordner sie nicht braucht
import tag_edit  # noqa: E402
wt = tempfile.mkdtemp(prefix="s2l_wmp_")
os.environ["S2L_DATA"] = os.path.join(wt + "_daten")
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
G = "AlbumArt_{FDCE2392-4BCD-4CC5-B06C-321D46BAAF2D}_Large.jpg"
for d_, extra in (("mitFolder", {"Folder.jpg": JPG}), ("allein", {}), ("eigenesCover", {})):
    os.makedirs(os.path.join(wt, d_))
    open(os.path.join(wt, d_, "lied.mp3"), "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
    for n_, b_ in dict(extra, **{G: JPG, "AlbumArtSmall.jpg": JPG}).items():
        open(os.path.join(wt, d_, n_), "wb").write(b_)
tag_edit.write_tags(os.path.join(wt, "eigenesCover", "lied.mp3"), {"title": "x"}, cover=JPG)
wc = fc.FileCheck(lambda: wt, lambda: [], lambda p: p)
wc.scan()
wc.thread.join(10)
wm = sorted(x["rel"] for x in wc.status()["muell"])
check(wm == sorted(["eigenesCover/" + G, "eigenesCover/AlbumArtSmall.jpg", "mitFolder/" + G, "mitFolder/AlbumArtSmall.jpg"]),
      "Media-Player-Bilder: Muell neben Folder.jpg oder wenn jedes Lied ein eigenes Cover hat, nie als einziges Cover " + str(wm))
check(not any(fc.name_match("AlbumArt.jpg", x) or fc.name_match("Folder.jpg", x) for x in fc.DEFAULT_JUNK_NAMES)
      and fc.name_match("albumart_{ab12-cd}_small.JPG", fc.DEFAULT_JUNK_NAMES[1]), "Standard: nur die Namen des Media Players, nie AlbumArt.jpg oder Folder.jpg")
# eigene Muell-Namen (Wunsch 09.11.2026)
open(os.path.join(wt, "allein", "info.nfo"), "wb").write(b"x")
open(os.path.join(wt, "allein", "Liste.M3U"), "wb").write(b"x")
check(not fc.name_match("lied.mp3", "*") and not fc.name_match("x.flac", "*.flac") and fc.name_match("Liste.M3U", "*.m3u"),
      "Musikdateien sind nie Muell, egal was in der Liste steht")
wc.scan(); wc.thread.join(10)
pv = wc.junk_preview(["*.nfo", "*", " ", "*.NFO", "*.jpg"])
rows = {r["name"]: r for r in pv["rows"]}
check(pv["names"] == ["*.nfo", "*", "*.jpg"] and rows["*.nfo"]["n"] == 1 and rows["*.nfo"]["ex"] == ["allein/info.nfo"]
      and not any(e.endswith(".mp3") for r in pv["rows"] for e in r["ex"]),
      "Vorschau: leere und doppelte Zeilen weg, zaehlt je Zeile, nie MP3 " + json.dumps(pv["rows"]))
check(rows["*"]["n"] >= 1 and pv["total"] == len({p for r in pv["rows"] for p in r["ex"]}) or pv["total"] >= 5,
      "Stern erwischt alles ausser Musik und gebrauchten Bildern")
res = wc.junk_names_set(["*.nfo", "*.m3u"])
wc.thread.join(10)
wm2 = sorted(x["rel"] for x in wc.status()["muell"])
check(res["names"] == ["*.nfo", "*.m3u"] and open(fc.junk_names_path(), encoding="utf-8").read() == "*.nfo\n*.m3u\n"
      and wm2 == ["allein/Liste.M3U", "allein/info.nfo"] and wc.status()["jnames"] == ["*.nfo", "*.m3u"],
      "Liste gespeichert, ohne die Media-Player-Zeilen gelten die Bilder nicht mehr als Muell " + str(wm2))
finish("test_dateien_pruefen")
