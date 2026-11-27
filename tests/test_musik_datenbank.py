"""Musik-Datenbank (Seite /musik): die Bruecke schickt je Lied alle Felder, der Pi merkt sie sich in shows/_mixxx_bibliothek.json,
die API haengt Liedtext (Cache am Pi oder Showdatei) und Show an. Nur Anzeige, aufs Licht wirkt nichts."""
import json
import os
import urllib.parse
import subprocess
import sys
import tempfile

from _common import PI, ROOT, build, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge  # noqa: E402

import mixxx_link  # noqa: E402
import webpanel  # noqa: E402
from mixxx_link import MixxxLink  # noqa: E402
from showman import lyrics as ly  # noqa: E402
from showman.api import ShowManager  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_mdb_")

# ---- Bruecke: Stuecke mit allen Feldern ----------------------------------------------------------------------------
lib = [{"artist": f"A{i}", "title": "Ö" * 30, "duration": 200.0 + i, "bpm": 128.0, "key": "Am", "kid": 22, "genre": "Pop",
        "comment": "8A - Energy 7", "path": "/Volumes/s2l_kein_stick/x/lied%d.mp3" % i, "cues": [1.0, 2.0], "bitrate": 320} for i in range(500)]
done = {mixxx_bridge.track_key(201.0, 128.0, 22)}
check(sum(len(x) for x in mixxx_bridge.library_chunks(lib + [{"artist": "Weg", "title": "Fehlt", "duration": 9.0, "missing": True}])) == 500,
      "Lieder, deren Datei laut Mixxx fehlt, bleiben weg (wie in der Mixxx-Suche)")
ch_ = mixxx_bridge.library_chunks(lib, done=done)
check(len(ch_) > 1 and sum(len(x) for x in ch_) == 500, "Bibliothek in Stuecken")
check(all(len(json.dumps({"type": "lib", "i": 999, "n": 999, "mp": 9025, "t": x}, separators=(",", ":"))) < 1450 for x in ch_), "jedes Stueck passt unzerteilt in ein WLAN-Paket")
it = ch_[0][1]
check(it[:2] == ["A1 - " + "Ö" * 30, 201.0] and it[2] == "A1" and it[3] == "Ö" * 30, "Titel und Laenge wie frueher, dann Interpret und Titel getrennt")
check(it[4:12] == [128.0, "Am", 22, "Pop", 7, "lied1.mp3", 2, 1] and ch_[0][0][11] == 0, "BPM, Tonart, Nr, Genre, Energie, Dateiname, Hotcues, analysiert")
check(it[12] == "/Volumes/s2l_kein_stick/x/lied1.mp3", "Pfad am Mac (fuers Vorhoeren)")
# Fehlerbericht 06.11.2026: 8 Lieder mit Typ "M"/"MP", nicht abspielbar: der Pfad wurde auf 240 Zeichen gekuerzt
LONG = "/Volumes/s2l_kein_stick/musik/U-MUSIK/Artists/Jean-Michel Jarre/2020 - Welcome To The Other Side (Concert From Virtual Notre-Dame)/" \
       "07 - Jean-Michel Jarre - Welcome To The Other Side (Concert From Virtual Notre-Dame) - Equinoxe 4 (Vr Live) – Küss’ Die Hand.mp3"
_li = mixxx_bridge.library_chunks([{"artist": "Jean-Michel Jarre", "title": "Equinoxe 4", "duration": 300.0, "path": LONG}])[0][0]
check(len(LONG) > 240 and _li[12] == LONG and _li[9] == os.path.basename(LONG), "Bruecke schickt langen Pfad und Dateinamen ganz")
check(mixxx_link.lib_item(_li)["path"] == LONG and mixxx_link.lib_item(_li)["file"] == os.path.basename(LONG), "Pi behaelt den ganzen Pfad")
check(len(json.dumps({"type": "lib", "i": 0, "n": 1, "mp": 9025, "t": [_li]}, separators=(",", ":"))) < 4096, "passt in ein Paket (Pi liest 4096 Byte)")
_huge = mixxx_bridge.library_chunks([{"artist": "A", "title": "B", "duration": 9.0, "path": "/Volumes/x/" + "ö" * 1200 + ".mp3"}])[0][0]
check(_huge[12] == "" and mixxx_link.lib_item(["T", 9.0] + [None] * 10 + ["/x/" + "a" * 1200 + ".mp3"])["path"] == "",
      "riesiger Pfad: lieber keiner als ein falscher (abgeschnittener)")
_gd = tempfile.mkdtemp(prefix="s2l_gone_")
open(os.path.join(_gd, "da.mp3"), "wb").close()
_gl = [{"artist": "A", "title": "Da", "duration": 9.0, "path": os.path.join(_gd, "da.mp3")},
       {"artist": "A", "title": "Weg", "duration": 9.0, "path": os.path.join(_gd, "weg.mp3")},
       {"artist": "A", "title": "Stick ab", "duration": 9.0, "path": "/Volumes/s2l_kein_stick/b/c.mp3"}]
check([x[3] for x in mixxx_bridge.library_chunks(_gl)[0]] == ["Da", "Stick ab"],
      "Datei geloescht (Muellkuebel): nicht mehr schicken; Stick abgezogen: alles bleibt")
_bad = [x for ch in mixxx_bridge.library_chunks(lib[:3], done=done, bad={mixxx_bridge.track_key(201.0, 128.0, 22)}) for x in ch]
check([x[14] for x in _bad] == [0, 1, 0] and mixxx_link.lib_item(_bad[1])["bad"] == 1 and mixxx_link.lib_item(_bad[0])["bad"] == 0,
      "nicht lesbare Dateien (_nicht_lesbar.json) als letztes Feld, am Pi 'bad'")
check(it[13] == 320 and mixxx_bridge.library_chunks([{"artist": "A", "title": "B", "duration": 9.0}])[0][0][13] == 0, "Bitrate als letztes Feld, ohne Angabe 0")
import sqlite3  # noqa: E402
_db = os.path.join(tmp, "mixxxdb.sqlite")
_con = sqlite3.connect(_db)
_con.executescript("CREATE TABLE library (id INTEGER, artist TEXT, title TEXT, duration REAL, bpm REAL, key TEXT, bitrate INTEGER);"
                   "INSERT INTO library VALUES (1, 'A', 'Eins', 200, 128, 'Am', 256);")
_con.commit(); _con.close()
check(mixxx_bridge.load_library(_db)[0]["bitrate"] == 256, "Bruecke liest die Bitrate aus der Mixxx-Datenbank")

# ---- Pi: Empfang, Ablage, alte Bruecke ------------------------------------------------------------------------------
link = MixxxLink(0)
path = os.path.join(tmp, "_mixxx_bibliothek.json")
link.persist(path)
check(link.library_full() == [] and not os.path.exists(path), "ohne Datei: leer, nichts geschrieben")
link.feed({"type": "lib", "i": 1, "n": 2, "t": [["Bär - Zwei", 100.0, "Bär", "Zwei", 120.0, "Am", 22, "Rock", 5, "b.mp3", 0, 1]]}, 1.0)
check(link.library() == [("Bär - Zwei", 100.0)] and not os.path.exists(path), "erstes Stueck: schon sichtbar, noch nicht gespeichert")
link.feed({"type": "lib", "i": 0, "n": 2, "t": [["Aha - Eins", 90.0], "kaputt", ["", 5.0], ["X", "y"]]}, 1.0)
full = link.library_full()
check([x["title"] for x in full] == ["Aha - Eins", "Bär - Zwei"] and link.library_complete(), "beide Stuecke, Unsinn weg, Reihenfolge der Bruecke")
check(full[0]["artist"] == "Aha" and full[0]["name"] == "Eins" and full[0]["bpm"] == 0 and full[0]["lvl"] == 0 and full[0]["ana"] == 0 and full[0]["path"] == "",
      "alte Bruecke (nur Titel, Laenge): Interpret und Titel getrennt, Rest leer")
check(mixxx_link.lib_item(["Nur Titel", 5.0])["name"] == "Nur Titel" and mixxx_link.lib_item(["Nur Titel", 5.0])["artist"] == "", "ohne Trennstrich: alles Titel")
check(full[1] == {"title": "Bär - Zwei", "dur": 100.0, "artist": "Bär", "name": "Zwei", "bpm": 120.0, "key": "Am", "kid": 22, "genre": "Rock",
                  "lvl": 5, "file": "b.mp3", "cues": 0, "ana": 1, "path": "", "kbps": 0, "bad": 0, "est": 0, "elv": 0, "kest": 0, "src": 0, "best": 0, "crates": [], "lists": [], "year": 0, "album": "", "track": "", "grp": "", "added": 0, "lufs": 0.0, "tp": 0.0, "rgt": 0, "plays": 0, "lastp": 0, "rating": 0}, "alle Felder")
check(os.path.isfile(path), "komplett: in der Ablage gespeichert")
m1 = os.path.getmtime(path)
link.feed({"type": "lib", "i": 0, "n": 2, "t": [["Aha - Eins", 90.0]]}, 2.0)
check(os.path.getmtime(path) == m1, "gleiche Bibliothek: nicht neu geschrieben")
link.feed({"type": "lib", "i": 0, "n": 3, "t": [["Neu - Null", 50.0], ["Bär - Zwei", 100.0, "Bär", "Zwei", 121.0, "Am", 22, "Rock", 6, "b.mp3", 0, 1, "/x/b.mp3"]]}, 3.0)
fl = link.library_full()
check([x["title"] for x in fl] == ["Aha - Eins", "Bär - Zwei", "Neu - Null"] and not link.library_complete(),
      "neue Bibliothek noch unvollstaendig: die gespeicherte, neue Lieder dahinter")
check(link.library_progress() == [1, 3, 0], "Fortschritt: ein Teil von drei")
link.feed({"type": "lib", "i": 2, "n": 3, "t": [["Zwei - Drei", 50.0]]}, 3.1)
check(link.library_progress() == [2, 3, 1], "letztes Stueck da, eines fehlt: im WLAN verloren")
# Pruefsumme (Wunsch 07.11.2026: nur schicken, wenn sich etwas geaendert hat; verlorene Stuecke einzeln nachschicken)
lk = MixxxLink(0)
_lp = os.path.join(tmp, "_bib_h.json")
lk.persist(_lp)
lk.feed({"type": "lib", "i": 0, "n": 2, "h": "abc", "t": [["A - Eins", 90.0]]}, 1.0)
check(lk.library_missing() == ("abc", [1]) and lk.lib_have_h == "", "Stueck 1 fehlt: wird gemeldet, Fassung noch nicht komplett")
lk.feed({"type": "lib", "i": 1, "n": 2, "h": "abc", "t": [["B - Zwei", 80.0]]}, 1.1)
check(lk.lib_have_h == "abc" and open(_lp + ".hash").read() == "abc" and lk.library_missing() == ("abc", []), "komplett: Fassung neben der Ablage gemerkt")
lk2 = MixxxLink(0)
lk2.persist(_lp)
check(not lk2.library_complete(), "nach Neustart: Ablage da, Mac noch nicht gemeldet")
lk2.feed({"type": "libhash", "h": "abc"}, 2.0)
check(lk2.library_complete() and len(lk2.library_full()) == 2 and lk2.library_progress()[2] == 0, "Mac meldet dieselbe Fassung: komplett, ohne Uebertragung")
lk2.feed({"type": "libhash", "h": "abc", "mp": 9025}, 2.1)
check(lk2.music_port == 9025, "Port des Vorhoerens kommt auch mit der Pruefsumme (sonst nach Neustart des Pi: Bruecke laeuft nicht)")
check(lk2.mac_alive() and not MixxxLink(0).mac_alive(), "Helfer ohne Mixxx meldet sich: Vorhoeren, Doppelte, Tag-Vorschlaege gehen")
lk2.music_port = 0
lk2.feed({"type": "libhash", "mp": 9026}, 2.2)
check(lk2.music_port == 9026 and lk2.library_complete() and lk2.lib_bridge_h == "abc",
      "nur Port ohne Pruefsumme (Liste am Mac noch nicht fertig, 08.11.2026): Port gemerkt, Fassung bleibt")
_mb_src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check('{"type": "libhash", "mp": self.music.port}' in _mb_src, "Bruecke meldet den Port, bevor die Liste fertig ist")
lk2.feed({"type": "libhash", "h": "neu"}, 3.0)
check(not lk2.library_complete(), "Mac hat eine neue Fassung: nicht mehr komplett")
lk2.feed({"type": "lib", "i": 0, "n": 2, "h": "neu", "t": [["C - Drei", 70.0]]}, 3.1)
check(lk2.library_missing() == ("neu", [1]), "neue Fassung: alte Stuecke verworfen, fehlende gemeldet")
# nur Geaendertes (Wunsch 07.11.2026): lk hat die Fassung "abc" komplett im Speicher
check(lk.library_delta_ok() and not lk2.library_delta_ok(), "kann Geaendertes einbauen nur mit allen Stuecken im Speicher (nicht nach Neustart)")
lk.feed({"type": "libhash", "h": "abc"}, 4.0)
lk.feed({"type": "lib", "i": 1, "n": 2, "h": "d1", "b": "abc", "c": 2, "t": [["B - Zwei neu", 80.0]]}, 4.1)
check([x["title"] for x in lk.library_full()] == ["A - Eins", "B - Zwei neu"] and lk.lib_have_h == "abc" and lk.library_delta_ok(),
      "Teil-Uebertragung: Stueck 0 bleibt, Stueck 1 neu, noch nicht fertig (2 erwartet)")
lk.feed({"type": "lib", "i": 1, "n": 2, "h": "d1", "b": "abc", "c": 2, "t": [["B - Zwei neu", 80.0]]}, 4.2)
check(lk.lib_have_h == "abc", "dasselbe Stueck nochmal zaehlt nicht doppelt")
lk.feed({"type": "lib", "i": 0, "n": 2, "h": "d1", "b": "abc", "c": 2, "t": [["A - Eins neu", 90.0]]}, 4.3)
check(lk.lib_have_h == "d1" and open(_lp + ".hash").read() == "d1" and [x["title"] for x in lk.library_full()] == ["A - Eins neu", "B - Zwei neu"],
      "Teil-Uebertragung komplett: neue Fassung gemerkt, Ablage neu")
lk.feed({"type": "lib", "i": 0, "n": 2, "h": "d2", "b": "falsch", "c": 1, "t": [["X", 1.0]]}, 5.0)
check(lk.library_missing() == ("d2", [1]), "Grundlage passt nicht: alles neu sammeln")
# Helfer-Fall (Fehlerbericht 07.11.2026): neue Fassung, bevor die vorige ganz da ist -> Geaenderte plus fehlende darauf
lk3 = MixxxLink(0)
lk3.persist(os.path.join(tmp, "_bib_h3.json"))
for i_, t_ in ((0, "A"), (1, "B")):
    lk3.feed({"type": "lib", "i": i_, "n": 3, "h": "v1", "t": [[t_ + " - x", 10.0]]}, 6.0)
check(lk3.library_missing() == ("v1", [2]), "v1: Stueck 2 im WLAN verloren")
lk3.feed({"type": "lib", "i": 0, "n": 3, "h": "v2", "b": "v1", "c": 2, "t": [["A2 - x", 10.0]]}, 6.1)
lk3.feed({"type": "lib", "i": 2, "n": 3, "h": "v2", "b": "v1", "c": 2, "t": [["C - x", 10.0]]}, 6.2)
check(lk3.lib_have_h == "v2" and [x["title"] for x in lk3.library_full()] == ["A2 - x", "B - x", "C - x"],
      "v2 auf der fast fertigen v1: geaendertes Stueck 0 und fehlendes Stueck 2, komplett")
lk3.feed({"type": "lib", "i": 1, "n": 3, "h": "v3", "b": "v2", "c": 2, "t": [["B3 - x", 10.0]]}, 7.0)
check(lk3.lib_have_h == "v2" and lk3.library_missing() == ("v3", []) and lk3.library_delta_ok(), "v3 halb da (ein Stueck verloren): Pi meldet nichts Fehlendes, kann aber Geaendertes")
lk3.feed({"type": "lib", "i": 1, "n": 3, "h": "v4", "b": "v3", "c": 1, "t": [["B4 - x", 10.0]]}, 7.1)
check(lk3.lib_have_h == "v2" and lk3.library_missing() == ("v4", [0, 2]), "Grundlage v3 (halbe Teil-Uebertragung) gilt nicht: alles neu sammeln")
check(fl[1]["lvl"] == 6 and fl[1]["path"] == "/x/b.mp3" and fl[0]["name"] == "Eins", "schon angekommene Lieder zeigen gleich ihre neuen Felder")
fremd = os.path.join(tmp, "fremd.json")
with open(fremd, "w", encoding="utf-8") as f:
    json.dump({"patterns": [{"name": "meins"}]}, f)
link_f = MixxxLink(0)
link_f.persist(fremd)
link_f.feed({"type": "lib", "i": 0, "n": 1, "t": [["A - B", 10.0]]}, 1.0)
check(link_f.lib_file is None and json.load(open(fremd, encoding="utf-8")) == {"patterns": [{"name": "meins"}]}, "fremde Datei (Muster-Bibliothek) wird nie ueberschrieben")
from showman.store import ShowStore
st_ = ShowStore(tempfile.mkdtemp(dir=tmp))
with open(os.path.join(st_.base, "_bibliothek.json"), "w", encoding="utf-8") as f:
    json.dump([["A - B", 10.0]], f)
check(st_.library() == {"patterns": []}, "Muster-Bibliothek mit Liste statt Mustern: leer statt Absturz")
link2 = MixxxLink(0)
link2.persist(path)
check([x["title"] for x in link2.library_full()] == ["Aha - Eins", "Bär - Zwei"] and link2.library_full()[1]["kid"] == 22, "nach Neustart aus der Datei")
check(mixxx_link.lib_item(["T", 10.0, None, None, "x", None, 99, None, 40]) == {"title": "T", "dur": 10.0, "artist": "", "name": "T", "bpm": 0, "key": "",
                                                                                 "kid": 24, "genre": "", "lvl": 10, "file": "", "cues": 0, "ana": 0, "path": "", "kbps": 0, "bad": 0, "est": 0, "elv": 0, "kest": 0, "src": 0, "best": 0, "crates": [], "lists": [], "year": 0, "album": "", "track": "", "grp": "", "added": 0, "lufs": 0.0, "tp": 0.0, "rgt": 0, "plays": 0, "lastp": 0, "rating": 0}, "Unsinn in Feldern wird begrenzt")
check(mixxx_link.lib_item(["T", 10.0] + [None] * 11 + [320])["kbps"] == 320 and mixxx_link.lib_item(["T", 10.0] + [None] * 11 + [99999])["kbps"] == 9999
      and mixxx_link.lib_item(["T", 10.0] + [None] * 11 + ["x"])["kbps"] == 0, "Bitrate am Pi: Zahl, begrenzt, Unsinn = 0")
link3 = MixxxLink(0)
link3.feed({"type": "lib", "i": 0, "n": 1, "mp": 9025, "t": [["A - B", 10.0, "A", "B", 0, "", 0, "", 0, "b.mp3", 0, 0, "/Volumes/USB/b.mp3"]]}, 1.0, addr="192.168.1.77")
check(link3.mac_ip == "192.168.1.77" and link3.music_port == 9025 and link3.library_full()[0]["path"] == "/Volumes/USB/b.mp3", "Absender, Vorhoer-Port und Pfad gemerkt")
link3.feed({"type": "lib", "i": 0, "n": 1, "mp": "x", "t": [["A - B", 10.0]]}, 2.0)
check(link3.music_port == 0, "ohne gueltigen Port: kein Vorhoeren")

# ---- API: Liedtext und Show dazu ------------------------------------------------------------------------------------
link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
base = tempfile.mkdtemp(dir=tmp)
mgr = ShowManager(sh, base)
check(link.lib_file == os.path.join(base, "_mixxx_bibliothek.json"), "Showmanager legt die Ablage neben die Liedtexte")
link.feed({"type": "lib", "i": 0, "n": 1, "t": [["Aha - Eins", 90.0, "Aha", "Eins", 100.0, "C", 1, "Pop", 3, "a.mp3", 1, 1],
                                                   ["Bär - Zwei", 100.0, "Bär", "Zwei", 120.0, "Am", 22, "Rock", 5, "b.mp3", 0, 1],
                                                   ["Cee - Drei", 200.0, "Cee", "Drei", 0, "", 0, "", 0, "c.mp3", 0, 0],
                                                   ["Dee - Vier", 150.0, "Dee", "Vier", 0, "", 0, "", 0, "d.mp3", 0, 0]]}, 1.0)
sh.lyric_cache.store("Aha - Eins", 91.0, [[0.0, "Hallo"], [2.0, "Welt"]])     # Laenge weicht 1 s ab: zaehlt trotzdem
sh.lyric_cache.store("Bär - Zwei", 100.0, [], plain="nur Text")
mgr.op({"op": "create", "name": "Zwei"})
doc = mgr.store.load("Zwei")
doc["mixxx"] = {"title": "Bär - Zwei", "dur": 100.0}
mgr.store.save("Zwei", doc)
mgr.op({"op": "create", "name": "Vier"})
doc = mgr.store.load("Vier")
doc["mixxx"] = {"title": "Dee - Vier", "dur": 150.0}
doc["lyrics"] = {"lines": [[0.0, "La"]], "plain": ""}
mgr.store.save("Vier", doc)
mgr.index_dirty = True
r = mgr.music_list()
by = {x["name"]: x for x in r["tracks"]}
check("prog" not in r, "komplett: kein Fortschrittsbalken")
check(r["n"] == 4 and r["complete"] and r["connected"] is True, "vier Lieder, komplett; Listen-Nachrichten eben erst: zaehlt als verbunden (wie der Helfer)")
check(by["Eins"]["lyr"] == 2 and by["Zwei"]["lyr"] == 1 and by["Drei"]["lyr"] == 0, "Liedtext: mit Zeiten, nur Text, nie gesucht")
check(by["Zwei"]["show"] == "Zwei" and by["Eins"]["show"] == "" and by["Drei"]["show"] == "", "Show nach Titel und Laenge")
check(by["Vier"]["show"] == "Vier" and by["Vier"]["lyr"] == 2, "Liedtext aus der Showdatei zaehlt")
mgr.op({"op": "create", "name": "Titanium Party"})          # per MP3 angelegt, kein Mixxx-Lied gewaehlt: Laenge der MP3 und Name
doc = mgr.store.load("Titanium Party")
doc["duration"] = 200.4
mgr.store.save("Titanium Party", doc)
mgr.op({"op": "create", "name": "Drei"})
doc = mgr.store.load("Drei")
doc["duration"] = 200.0
mgr.store.save("Drei", doc)
mgr.op({"op": "create", "name": "Cee - Drei Remix"})
doc = mgr.store.load("Cee - Drei Remix")
doc["duration"] = 150.0                                     # Name passt, Laenge nicht
mgr.store.save("Cee - Drei Remix", doc)
mgr.index_dirty = True
by = {x["name"]: x for x in mgr.music_list()["tracks"]}
check(by["Drei"]["shows"] == ["Drei"] and by["Drei"]["show"] == "Drei", "Show ohne Mixxx-Lied: ueber Laenge und Namen gefunden (Titel im Shownamen)")
check(by["Vier"]["shows"] == ["Vier"] and "Titanium Party" not in by["Drei"]["shows"], "fremde Laenge oder fremder Name: keine Zuordnung")
mgr.op({"op": "create", "name": "Vier Live"})
doc = mgr.store.load("Vier Live")
doc["duration"] = 149.5
mgr.store.save("Vier Live", doc)
mgr.index_dirty = True
check({x["name"]: x for x in mgr.music_list()["tracks"]}["Vier"]["shows"] == ["Vier", "Vier Live"], "mehrere Shows zu einem Lied")
_link0 = mgr.show.mixxx
mgr.show.mixxx = type("L", (), {"library_full": lambda self: [dict(mixxx_link.lib_item(["A - Eins", 100.0] + [None] * 10 + ["/m/eins.mp3"])),
                                                               dict(mixxx_link.lib_item(["B - Zwei", 100.0] + [None] * 10 + ["/m/zwei.mp3"])),
                                                               dict(mixxx_link.lib_item(["C - Drei", 100.0] + [None] * 10 + ["/m/drei.mp3"]))],
                                "library_complete": lambda self: True})()
mgr.covers.index = {"/m/eins.mp3": "1234:0123456789abcdef", "/m/zwei.mp3": ""}   # Cover: 1 ja, 0 keins, -1 noch nicht geprueft
_cv = {x["path"]: x["cv"] for x in mgr.music_list()["tracks"]}
check(_cv == {"/m/eins.mp3": 1, "/m/zwei.mp3": 0, "/m/drei.mp3": -1}, "Cover-Stand je Lied: ja, keins, noch nicht geprueft")
mgr.covers.index, mgr.show.mixxx = {}, _link0
_mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("if (fnocv && (r.cv !== 0 || !SM.canCover(r.path))) return false;" in _mj and 'id="fnocv"' in open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read(),
      "Filter ohne Cover: nur Lieder, die sicher keines haben")
link_t = MixxxLink(0)
rig_t, sh_t = build(strobe=False, mixxx=link_t)
mgr_t = ShowManager(sh_t, tempfile.mkdtemp(dir=tmp))
mgr_t.music_path = os.path.join(tmp, "keins.json")
link_t.feed({"type": "lib", "i": 0, "n": 1, "t": [["David Guetta - Titanium (Future Rave Remix)", 211.5, "David Guetta", "Titanium (Future Rave Remix)"],
                                                     ["David Guetta - Titanium", 244.7, "David Guetta", "Titanium"]]}, 1.0)
for nm in ("Titanium", "Titanium (Vorschlag KI)", "Titanium (Vorschlag Show Assistent) (Vorschlag 2)", "Titan"):
    mgr_t.op({"op": "create", "name": nm})
    doc = mgr_t.store.load(nm)
    doc["duration"] = 211.49
    mgr_t.store.save(nm, doc)
mgr_t.index_dirty = True
by_t = {x["name"]: x for x in mgr_t.music_list()["tracks"]}
check(by_t["Titanium (Future Rave Remix)"]["shows"] == ["Titanium", "Titanium (Vorschlag KI)", "Titanium (Vorschlag Show Assistent) (Vorschlag 2)"],
      "Shows mit Klammerzusatz: Kern des Namens gleich dem Kern des Titels, gleiche Laenge")
check(by_t["Titanium"]["shows"] == [], "andere Laenge (Original statt Remix): keine Zuordnung")
# Kurven aus dem Vorab-Lauf der Bibliothek (ohne Show): Fehlerbericht von Markus 06.11.2026, Filter "mit Kurven" zeigte nur die Shows
link_v = MixxxLink(0)
rig_v, sh_v = build(strobe=False, mixxx=link_v)
mgr_v = ShowManager(sh_v, tempfile.mkdtemp(dir=tmp))
mgr_v.music_path = os.path.join(tmp, "keins2.json")
link_v.feed({"type": "lib", "i": 0, "n": 1, "t": [["A - Vorab", 200.0, "A", "Vorab", 0, "", 0, "", 0, "v.mp3", 0, 0, "/m/v.mp3"],
                                                     ["B - Nix", 200.0, "B", "Nix", 0, "", 0, "", 0, "n.mp3", 0, 0, "/m/n.mp3"]]}, 1.0)
FPV = "123:0123456789abcdef"
mgr_v.stem_bulk.fps["/m/v.mp3"] = FPV
os.makedirs(os.path.dirname(mgr_v.store._stems_path(FPV)), exist_ok=True)
with open(mgr_v.store._stems_path(FPV), "w", encoding="utf-8") as f:
    f.write("{}")
by_v = {x["name"]: x for x in mgr_v.music_list()["tracks"]}
check(by_v["Vorab"]["stems"] == 1 and by_v["Nix"]["stems"] == 0, "Spalte Kurven: auch Kurven aus dem Vorab-Lauf (ohne Show)")
from showman.store import audio_fingerprint as _afp
mp3_ = mgr.store.path("Vier Live", "audio.mp3")
with open(mp3_, "wb") as f:
    f.write(b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(range(256)) * 300)
os.makedirs(os.path.dirname(mgr.store._stems_path("x")), exist_ok=True)
with open(mgr.store._stems_path(_afp(mp3_)), "w", encoding="utf-8") as f:
    f.write("{}")                                                # Kurven-Datei zur MP3 dieser Show (Inhalt egal, nur Vorhandensein)
mgr.index_dirty = True
by = {x["name"]: x for x in mgr.music_list()["tracks"]}
check(by["Vier"]["stems"] == 1 and by["Eins"]["stems"] == 0 and by["Drei"]["stems"] == 0, "Pegelkurven: ueber die MP3 der zugeordneten Show")
html_ = open(os.path.join(PI, "static", "sm", "music.html"), encoding="utf-8").read()
check('list="qhist"' in html_ and "const QH = 'musiksuche'" in open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
      and "$('q').addEventListener('change', qhSave);" in open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read(),
      "Suchfeld: fruehere Suchen als Vorschlagsliste (Wunsch 09.11.2026)")
check('id="fnoana"' in html_ and "if (fnoana && r.ana) return false;" in open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read(), "Filter nicht analysiert")
_js = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check("{ k: 'stems'" in _js and 'id="fstems"' in html_ and _js.find("{ k: 'dir'") < _js.find("{ k: 'file'"), "Spalte Kurven, Filter mit Kurven, Ordner vor Datei")
check(by["Eins"]["kid"] == 1 and by["Eins"]["lvl"] == 3 and by["Eins"]["file"] == "a.mp3" and by["Eins"]["ana"] == 1, "Felder kommen durch")
check(r["music"] == "", "Bruecke nicht verbunden: kein Vorhoeren")
link.feed({"type": "lib", "i": 0, "n": 1, "mp": 9025, "t": [[x["title"], x["dur"]] for x in link.library_full()]}, 1.0, addr="192.168.1.77")
sh.mx = {"connected": True}
check(mgr.music_list()["music"] == "http://192.168.1.77:9025", "Bruecke verbunden: Adresse des Vorhoer-Servers am Mac")
sh.mx = {"connected": False}
r = mgr.op({"op": "create", "name": "Aus der Liste", "title": "Aha - Eins", "dur": 90.0})
check(r["doc"]["mixxx"]["title"] == "Aha - Eins" and r["doc"]["mixxx"]["dur"] == 90.0 and mgr.store.load("Aus der Liste")["mixxx"]["on"] is True, "Show anlegen mit Lied aus Mixxx")
mgr.index_dirty = True
check({x["name"]: x["show"] for x in mgr.music_list()["tracks"]}["Eins"] == "Aus der Liste", "neue Show erscheint in der Liste")
doc = mgr.store.load("Zwei")
doc["mixxx"]["dur"] = 130.0
mgr.store.save("Zwei", doc)
mgr.index_dirty = True
check(mgr.music_list()["tracks"][1]["show"] == "", "andere Laenge (Remix): keine Zuordnung")
rig2, sh2 = build()
m2 = ShowManager(sh2, tempfile.mkdtemp(dir=tmp))
m2.music_path = os.path.join(tmp, "keins.json")
# Titel bereinigen: "so lassen" (Wunsch 07.11.2026, "10 Nackte Friseusen")
check(m2.op({"op": "title_kept"}) == {"kept": {}}, "noch nichts so gelassen")
m2.op({"op": "title_keep", "path": "/m/10 Nackte Friseusen.mp3", "title": "10 Nackte Friseusen"})
check(ShowManager(sh2, m2.store.base).titles_kept() == {"/m/10 Nackte Friseusen.mp3": {"t": "10 Nackte Friseusen", "src": "hand"}}, "so lassen: gemerkt in shows/, auch nach Neustart")
m2.op({"op": "title_keep", "path": "/m/7 Years.mp3", "title": "7 Years", "src": "netz"})
check(m2.titles_kept()["/m/7 Years.mp3"]["src"] == "netz", "Ergebnis der Internetsuche gemerkt")
try:
    m2.op({"op": "title_keep", "path": "/m/x.mp3", "title": "x", "src": "quatsch"})
    check(False, "unbekannte Quelle")
except ValueError:
    check(True, "unbekannte Quelle: Fehler")
m2.op({"op": "title_keep", "path": "/m/7 Years.mp3", "keep": False})
check(m2.op({"op": "title_keep", "path": "/m/10 Nackte Friseusen.mp3", "keep": False}) == {"kept": {}}, "nicht mehr behalten: vergessen")
_tj = open(os.path.join(PI, "static", "sm", "titles.js"), encoding="utf-8").read()
check("k.t === r.title && (k.src === 'hand' || k.src === 'netz')" in _tj and 'class="tkeep"' in _tj and "SM.cmd('title_keep'" in _tj, "Seite: Knopf So lassen, behaltene Lieder kommen nicht wieder (nur solange der Titel gleich bleibt)")
check(m2.music_list() == {"connected": False, "complete": False, "n": 0, "tracks": [], "music": "", "v": 0, "root": ""}, "ohne Mixxx-Empfaenger: leer")

# ---- Vorhoer-Server am Mac (music_serve.py) ---------------------------------------------------------------------------
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

import music_serve  # noqa: E402

mdir = os.path.join(tmp, "musik")
os.makedirs(os.path.join(mdir, "a"))
data = bytes(range(256)) * 100
with open(os.path.join(mdir, "a", "lied.mp3"), "wb") as f:
    f.write(data)
with open(os.path.join(mdir, "geheim.txt"), "w") as f:
    f.write("nicht fuer den Browser")
loc = music_serve.Locator(["/Volumes/ALT/musik/a/lied.mp3", "/Volumes/ALT/musik/b/x.mp3"], root=mdir)
check(loc.locate("/Volumes/ALT/musik/a/lied.mp3") == os.path.join(mdir, "a", "lied.mp3"), "Stick heisst anders: Datei unter MUSIC_ROOT gefunden")
check(loc.locate(os.path.join(mdir, "geheim.txt")) is None and loc.locate("/Volumes/ALT/musik/../musik/a/lied.mp3") is None, "nur Dateien aus der Bibliothek, kein ..")
check(music_serve.Locator([os.path.join(mdir, "a", "lied.mp3")]).locate(os.path.join(mdir, "a", "lied.mp3")) == os.path.join(mdir, "a", "lied.mp3"), "Pfad wie in Mixxx")
check(music_serve.Locator(["/Volumes/ALT/a/lied.mp3"], path_map=[("/Volumes/ALT", mdir)]).locate("/Volumes/ALT/a/lied.mp3") == os.path.join(mdir, "a", "lied.mp3"), "path_map wie bei der Analyse")
srv = music_serve.MusicServer(["/Volumes/ALT/musik/a/lied.mp3"], port=0, root=mdir)
check(srv.start() and srv.port > 0, "Server auf freiem Port")
base = f"http://127.0.0.1:{srv.port}"
q = urllib.parse.quote("/Volumes/ALT/musik/a/lied.mp3")
with urllib.request.urlopen(base + "/ping", timeout=5) as r:
    check(json.loads(r.read())["ok"] and r.headers["Access-Control-Allow-Origin"] == "*", "ping, Seite vom Pi darf zugreifen")
with urllib.request.urlopen(base + "/audio?p=" + q, timeout=5) as r:
    check(r.status == 200 and r.read() == data and r.headers["Content-Type"] == "audio/mpeg" and r.headers["Accept-Ranges"] == "bytes", "ganze MP3")
req = urllib.request.Request(base + "/audio?p=" + q, headers={"Range": "bytes=100-199"})
with urllib.request.urlopen(req, timeout=5) as r:
    check(r.status == 206 and r.read() == data[100:200] and r.headers["Content-Range"] == f"bytes 100-199/{len(data)}", "Springen im Lied (Range)")
try:
    urllib.request.urlopen(base + "/audio?p=" + urllib.parse.quote(os.path.join(mdir, "geheim.txt")), timeout=5)
    check(False, "fremde Datei abgelehnt")
except urllib.error.HTTPError as e:
    check(e.code == 404, "fremde Datei abgelehnt")
for cp_, code_ in (("/Volumes/ALT/musik/a/gibtsnicht.mp3", 410), ("/Volumes/ALT/musik/a/lied.mp3", 404)):
    try:
        urllib.request.urlopen(base + "/cover?p=" + urllib.parse.quote(cp_), timeout=5)
        check(False, "Cover: Fehler erwartet")
    except urllib.error.HTTPError as e:
        check(e.code == code_, "Cover: unbekannte Datei 410 (der Pi merkt sich das nicht als 'ohne Cover'), Lied ohne Cover 404: " + str(e.code))
try:
    urllib.request.urlopen(base + "/x", timeout=5)
    check(False, "nur /ping und /audio")
except urllib.error.HTTPError as e:
    check(e.code == 404, "nur /ping und /audio")
# Fehlerbericht 06.11.2026: "2–4 Family - Stay" (Gedankenstrich) kam nicht, ganze MP3 ohne Range: der Server brach ab
os.makedirs(os.path.join(mdir, "2–4 Family"))
with open(os.path.join(mdir, "2–4 Family", "2–4 Family - Stay ä.mp3"), "wb") as f:
    f.write(data)
srv2 = music_serve.MusicServer(["/Volumes/ALT/musik/2–4 Family/2–4 Family - Stay ä.mp3"], port=0, root=mdir)
srv2.start()
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{srv2.port}/audio?p=" + urllib.parse.quote("/Volumes/ALT/musik/2–4 Family/2–4 Family - Stay ä.mp3", safe=""), timeout=5) as r:
        cd = r.headers.get("Content-Disposition", "")
        check(r.status == 200 and r.read() == data and "filename*=UTF-8''2%E2%80%934%20Family" in cd, "ganze MP3 mit Gedankenstrich und Umlaut im Namen")
except OSError as e:
    check(False, "ganze MP3 mit Gedankenstrich und Umlaut im Namen: %s" % e)
srv2.stop()
# Muellkuebel (Wunsch von Markus 06.11.2026): MP3 in den Papierkorb des Mac, nur Bibliothek, nur mit passendem Namen
binned = []
os.makedirs(os.path.join(mdir, "c"))
with open(os.path.join(mdir, "c", "doppelt.mp3"), "wb") as f:
    f.write(data)
srv3 = music_serve.MusicServer(["/Volumes/ALT/musik/c/doppelt.mp3"], port=0, root=mdir, trash=binned.append)
srv3.start()
b3 = f"http://127.0.0.1:{srv3.port}"


def post(body):
    req = urllib.request.Request(b3 + "/trash", json.dumps(body).encode(), {"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


check(post({"p": "/Volumes/ALT/musik/c/doppelt.mp3", "name": "falsch.mp3"})[0] == 400 and not binned, "falscher Dateiname: nichts geloescht")
check(post({"p": os.path.join(mdir, "geheim.txt"), "name": "geheim.txt"})[0] == 404 and not binned, "Datei ausserhalb der Bibliothek: nichts geloescht")
code3, js3 = post({"p": "/Volumes/ALT/musik/c/doppelt.mp3", "name": "doppelt.mp3"})
check(code3 == 200 and js3.get("ok") and binned == [os.path.join(mdir, "c", "doppelt.mp3")], "passende Datei kommt in den Papierkorb")
check(post({"p": "/Volumes/ALT/musik/c/doppelt.mp3", "name": "doppelt.mp3"})[0] == 404 and len(binned) == 1, "danach nicht noch einmal (aus der Liste genommen)")
try:
    urllib.request.urlopen(b3 + "/trash", timeout=5)
    check(False, "GET loescht nie")
except urllib.error.HTTPError as e:
    check(e.code == 404, "GET loescht nie (nur POST)")
opt = urllib.request.Request(b3 + "/trash", method="OPTIONS")
with urllib.request.urlopen(opt, timeout=5) as r:
    check("POST" in r.headers["Access-Control-Allow-Methods"] and "Content-Type" in r.headers["Access-Control-Allow-Headers"], "Seite vom Pi darf POST schicken")
srv3.stop()
ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('"osascript"' in ms and "(item 1 of argv)" in ms and "rm " not in ms and "os.remove" not in ms and "unlink" not in ms,
      "Papierkorb des Finders (wiederherstellbar), Pfad als Argument, nie endgueltig loeschen")
mjs = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check("SM.ask(q, undefined, 'In den Papierkorb')" not in mjs and "music + '/trash'" in mjs and "data-del=" in mjs and "Zurücklegen" in mjs,
      "Musik-Datenbank: Muellkuebel neben dem Abspielknopf, ohne Nachfrage (Wunsch 08.11.2026)")
check(srv.apply_conf({"root": ""}) == mdir and srv.loc.root == mdir, "Panel leer: Reserve aus config.sh")
check(srv.apply_conf({"root": "/Volumes/NEU/musik/"}) == "/Volumes/NEU/musik" and srv.loc.root == "/Volumes/NEU/musik", "Ordner aus dem Panel geht vor")
check(srv.apply_conf("kaputt") == mdir, "Unsinn vom Pi: wieder die Reserve")
srv.stop()

# Einstellung am Pi: music.json, API fuer Panel und Bruecke
mgr.music_path = os.path.join(tmp, "music.json")
check(mgr.music_conf() == {"root": "", "excl": [], "ew": False, "kw": False, "rw": False, "ce": False, "cw": False, "libh": "", "mx": True} and not os.path.exists(mgr.music_path), "ohne Datei: leer")
check(mgr.op({"op": "music_root_save", "root": "  /Volumes/USB STICK/musik "}) == {"root": "/Volumes/USB STICK/musik", "excl": [], "ew": False, "kw": False, "rw": False, "ce": False, "cw": False, "libh": "", "mx": True}, "Ordner aus dem Panel gespeichert")
check(json.load(open(mgr.music_path, encoding="utf-8")) == {"root": "/Volumes/USB STICK/musik"} and mgr.music_conf()["root"] == "/Volumes/USB STICK/musik", "in music.json")
check(mgr.op({"op": "music_root_save", "root": ""}) == {"root": "", "excl": [], "ew": False, "kw": False, "rw": False, "ce": False, "cw": False, "libh": "", "mx": True}, "leer speichern geht")
mgr.op({"op": "music_root_save", "root": "/x"})

# Ausgeschlossene Ordner (Wunsch 10.11.2026): eigene Zeile in music.json, Musikordner und Liste ueberschreiben sich nicht
c = mgr.op({"op": "music_excl_save", "excl": ["APRES SKI", " KINDERMUSIK/Duplicates/ ", "", "apres ski", "/Volumes/X/FUN"]})
check(c["excl"] == ["APRES SKI", "KINDERMUSIK/Duplicates", "/Volumes/X/FUN"] and c["root"] == "/x", "Liste bereinigt gespeichert, Musikordner bleibt")
mgr.op({"op": "music_root_save", "root": "/x"})
check(mgr.music_conf()["excl"] == ["APRES SKI", "KINDERMUSIK/Duplicates", "/Volumes/X/FUN"], "Musikordner speichern loescht die Liste nicht")
try:
    mgr.op({"op": "music_excl_save", "excl": ["U-MUSIK/../.."]})
    check(False, "'..' wird abgelehnt")
except ValueError:
    check(mgr.music_conf()["excl"][0] == "APRES SKI", "'..' wird abgelehnt, alte Liste bleibt")
check(mgr.op({"op": "music_excl_save", "excl": "FUN\nFREE"})["excl"] == ["FUN", "FREE"], "auch als Text mit Zeilen")
mgr.op({"op": "music_excl_save", "excl": []})
check(mgr.music_conf()["excl"] == [] and mgr.music_conf()["root"] == "/x", "leere Liste")

# ---- Seite und Knopf ------------------------------------------------------------------------------------------------
from showman import api as sm_api  # noqa: E402

check(os.path.isfile(os.path.join(sm_api.STATIC, "music.html")) and sm_api.STATIC_RE.match("music.js"), "Seite liegt bei den Showmanager-Dateien")
html = open(os.path.join(sm_api.STATIC, "music.html"), encoding="utf-8").read()
js_find = open(os.path.join(sm_api.STATIC, "music.js"), encoding="utf-8").read().find
check('id="q"' in html and 'id="genre"' in html and 'id="key"' in html and 'id="energy"' in html and 'id="flyr"' in html and 'id="fshow"' in html,
      "Suchfeld, Genre, Tonart, Energie, Liedtext und Show als Filter")
check(js_find("{ k: 'name'") < js_find("{ k: 'artist'") and '<audio id="player"' in html and 'id="bar"' in html and 'id="vol"' in html, "Titel vor Interpret, Abspielleiste mit Lautstaerke")
js = open(os.path.join(sm_api.STATIC, "music.js"), encoding="utf-8").read()
check("'/audio?p=' + encodeURIComponent(r.path)" in js and "'/api/sm/audio?name='" in js and "cmd('create', { name: name.trim(), title: r.title, dur: r.dur })" in js,
      "Vorhoeren vom Mac, Show anlegen: MP3 vom Mac auf den Pi")
check("player.volume = Math.max(0, Math.min(1, $('vol').value / 100 * SM.dbFactor(db)))" in js and "localStorage.setItem('musikvol'" in js, "Lautstaerke wirkt auf den Player und bleibt im Browser gemerkt")
check("if (st !== stamp)" in js and "draw(true, keep === true)" in js and "#hint:empty { display: none; }" in html, "Nachladen zeichnet nur bei Aenderung neu, Hinweis in der oberen Zeile (die Tabelle springt nicht)")
check('id="bdup"' in html and "{ k: 'dir'" in js and "function findDups()" in js and "'gleicher Dateiname'" in js and "gleiches Tempo" not in js,
      "Spalte Ordner und Knopf Doppelte (nur gleicher Dateiname)")
# Spalten: Bitrate, Reihenfolge und Sichtbarkeit je Browser (Wunsch von Markus)
check("{ k: 'kbps', th: 'kb/s'" in js and js.find("{ k: 'dur'") < js.find("{ k: 'kbps'") < js.find("{ k: 'lyr'"), "Spalte kb/s nach der Laenge")
check('id="bcols"' in html and 'id="colbox"' in html and 'id="headrow"' in html and "data-k=" not in html, "Knopf Spalten, Kopf der Tabelle kommt aus music.js")
check("localStorage.setItem(COLS_KEY" in js and "neue Spalten hinter ihrer Vorgaengerin dazu" in js and "if (hidden.size >= order.length)" in js,
      "Spalten je Browser gemerkt, neue Spalten erscheinen, mindestens eine bleibt sichtbar")
check("'kb/s'" in js and "mmss(r.dur), r.ext, r.kbps || ''" in js, "CSV mit Typ und Bitrate")
check("WIDTH_DEF = { dir: 520 }" in js and "setPointerCapture" in js and "ondblclick" in js and "localStorage.setItem(WIDTH_KEY" in js and ".grip" in html,
      "Spaltenbreite ziehen (Maus und Finger), Doppelklick = Standard, Ordner doppelt so breit, je Browser gemerkt")
check('id="fbad"' in html and "if (fbad && !r.bad) return false;" in js and "fq === 'nichtlesbar'" in js and "r.bad ?" in js,
      "Filter 'nicht lesbar', per Adresse /musik?f=nichtlesbar, rotes Kreuz in der Spalte Analyse")
check('href="/musik?f=nichtlesbar"' in webpanel.stats_page(), "Seite Statistik: Link zu den nicht lesbaren Dateien (Wunsch von Markus)")
# Quick (Wunsch von Markus): bei Liedern mit Spur-Kurven Show anlegen und gleich vom Assistenten fuellen lassen
check("r.stems && /\\.mp3$/i.test(r.path) ? '<button class=\"mk quick\" data-quick=" in js and "quickQueue(all[+b.dataset.quick])" in js,
      "Musik-Datenbank: Quick nur mit Kurven und MP3")
_qi = js.index("async function quickOne")
_core = open(os.path.join(ROOT, "pi", "static", "sm", "core.js"), encoding="utf-8").read()
_ci = _core.index("SM.quickShow = ")
_q = js[_qi:_qi + 400] + _core[_ci:_ci + 3500]               # Ablauf liegt in core.js (gemeinsam mit dem Hauptpanel)
check("SM.quickShow(r, music" in _q and "location.href" not in _q and all(op in _q for op in ("'create'", "'/api/sm/audio?name='", "'peaks'", "'analyze'", "'quick_meta'", "'marks_from_mac'", "'lyrics_quick'", "'assist'"))
      and "keep_copy: false" in _q and "claude: false" in _q,
      "Quick bleibt in der Liste (kein Editor): anlegen, MP3, Wellenform, Tempo, Cues, Liedtext, Assistent (Wunsch von Markus)")
check("quickTodo.push(r)" in js and "while (quickTodo.length)" in js and "⚡ nochmal" in js and "if (created) await SM.cmd('delete', { name })" in _core,
      "mehrere Quick nacheinander (Warteschlange), Fehler: halbe Show weg, nochmal moeglich")
_ejs = open(os.path.join(PI, "static", "sm", "editor.js"), encoding="utf-8").read()
check("if (r.ok && await importMp3(await r.blob(), true) && quick) await quickAssist();" in _ejs and "claude: false, design: false, keep_copy: false" in _ejs
      and "wild: SM.wildFor(info.lvl), laser: true, fog: true, strobe: true, move: true" in _ejs and "style: info.style || ''" in _ejs,
      "Editor: nach dem Import der Assistent mit den Standardwerten des Fensters, offline, direkt in die neue Show")
check("{ k: 'ext', th: 'Typ'" in js and "r.ext = extOf(r.path || r.file)" in js and "k === 'ext'" in js, "Spalte Typ aus der Dateiendung, sortierbar (Wunsch von Markus)")
check(subprocess.run(["node", "--check", os.path.join(sm_api.STATIC, "music.js")], capture_output=True).returncode == 0, "music.js ohne Syntaxfehler")


class H:
    def __init__(self, path):
        self.path, self.out = path, None

    def _send(self, code, body, ctype, extra=None):
        self.out = (code, body, ctype)


h = H("/musik")
check(sm_api.handle_get(h, mgr) and h.out[0] == 200 and b"Musik-Datenbank" in h.out[1], "Seite /musik")
h = H("/api/musik")
check(sm_api.handle_get(h, mgr) and h.out[0] == 200 and json.loads(h.out[1])["n"] == 4 and json.loads(h.out[1])["root"] == "/x", "API /api/musik mit Musikordner")
check("function topPrefix(paths, root)" in js and "d.root || ''" in js, "Spalte Ordner kuerzt um den Musikordner aus den Einstellungen")
h = H("/api/musik/conf")
check(sm_api.handle_get(h, mgr) and h.out[0] == 200 and json.loads(h.out[1]) == {"root": "/x", "excl": [], "ew": False, "kw": False, "rw": False, "ce": False, "cw": False, "libh": "", "mx": True}, "API /api/musik/conf fuer die Bruecke")
pg = webpanel.make_page()
check('id="mexcl"' in pg and "op:'music_excl_save'" in pg and pg.find('id="musbox"') < pg.find('id="mrootrow"') < pg.find('id="mexclrow"'),
      "Feld ausgeschlossene Ordner unter dem Musikordner")
check('id="mroot"' in pg and "op:'music_root_save'" in pg and pg.find('data-cat="ton"') < pg.find('id="mrootrow"') < pg.find('data-cat="licht"'), "Feld Musikordner unter Ton und Musik in den Einstellungen")
inst_ = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("/api/musik/conf" in inst_ and "--pi-web" in inst_, "Bruecke fragt den Pi nach dem Musikordner")
p = webpanel.make_page()
check('<a id="dbbtn" href="/musik"' in p and p.find('id="hlbtn"') < p.find('id="dbbtn"') < p.find('id="rmbtn"'), "runder Knopf rechts neben dem Herz")
check("['musik', '/musik', 'h_music']" in open(os.path.join(ROOT, "pi", "static", "sm", "nav.js"), encoding="utf-8").read(), "am Handy im Menue der Kopfleiste")
import texts  # noqa: E402

check(texts.HEADS["h_music"] == ("Musik-Datenbank", "Music library"), "Text in beiden Sprachen")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check('"$HERE/music_serve.py"' in inst and 'MUSIC_ROOT=' in inst and '--music-root "${MUSIC_ROOT:-}"' in inst,
      "Installer kopiert music_serve.py, legt MUSIC_ROOT an und gibt ihn der Bruecke mit")
ed = open(os.path.join(PI, "static", "sm", "editor.html"), encoding="utf-8").read()
css = open(os.path.join(PI, "static", "sm", "sm.css"), encoding="utf-8").read()
check('id="volic"' in ed and "#title,#syncst,.hide-s{display:none}" in css and "#vol{width:64px}" in css, "Lautstaerke im Editor mit Symbol, auch am Tablet hochkant sichtbar")
# Wunsch 07.11.2026: passt Mixxx noch zum Stick? (Lieder in Mixxx ohne Datei, Dateien ohne Mixxx-Eintrag)
import tempfile as _tf  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge as _mb  # noqa: E402
_d = _tf.mkdtemp(prefix="s2l_sync_")
_da = os.path.join(_d, "da.mp3")
open(_da, "wb").write(b"x")
_fw = _mb.Forwarder([{"path": _da, "duration": 1.0}, {"path": os.path.join(_d, "weg.mp3"), "duration": 1.0}], None, None, analysis_dir=_d, analyze=False)
_fw.folder = type("F", (), {"songs": [{"path": os.path.join(_d, "neu.mp3")}], "root": _d})()
_si = _fw.sync_info()
check(_si["gone"] == 1 and _si["gone_list"] == [os.path.join(_d, "weg.mp3")] and _si["new"] == 1 and _si["mixxx"] == 2,
      "Abgleich: 1 Lied in Mixxx ohne Datei, 1 Datei ohne Mixxx-Eintrag")
# nach "Bibliothek neu einlesen" in Mixxx (Fehlerbericht 07.11.2026): der Abgleich liest die echte Datenbank neu, nicht die Kopie vom Start
import sqlite3 as _sq  # noqa: E402
_db = os.path.join(_d, "live.sqlite")
_c = _sq.connect(_db)
_c.executescript("CREATE TABLE library (id INTEGER, location INTEGER, mixxx_deleted INTEGER); CREATE TABLE track_locations (id INTEGER, location TEXT, fs_deleted INTEGER);")
_c.executemany("INSERT INTO track_locations VALUES (?,?,?)", [(1, _da, 0), (2, os.path.join(_d, "weg.mp3"), 1), (3, os.path.join(_d, "neu.mp3"), 0)])
_c.executemany("INSERT INTO library VALUES (?,?,0)", [(1, 1), (2, 2), (3, 3)])
_c.commit(); _c.close()
_fw.live_db, _fw._sync = _db, None
_si2 = _fw.sync_info()
check(_si2["gone"] == 0 and _si2["known"] == 1 and _si2["new"] == 0 and _si2["live"], "nach dem Einlesen: Mixxx kennt das fehlende Lied, die neue Datei ist eingelesen, kein Hinweis mehr")
_fw.live_db, _fw._sync = os.path.join(_d, "gibtsnicht.sqlite"), None
check(_fw.sync_info()["gone"] == 1 and _fw.sync_info()["live"] is False, "ohne Zugriff auf die echte Datenbank: wie bisher")
# geschriebene Tags (Fehlerbericht 07.11.2026): Mixxx zeigt noch die alten, die Liste am Pi soll die neuen zeigen
_ad = os.path.join(_d, "analysis")
os.makedirs(_ad, exist_ok=True)
_fw2 = _mb.Forwarder([{"path": _da, "duration": 1.0, "artist": "Seele", "title": "Seele", "genre": "Ruhig"}], None, None, analysis_dir=_ad, analyze=False)
_fw2.lib_chunks, _fw2.lib_done = [(0, [])], 5.0
_fw2.tags_written(_da, {"artist": "Louise Hay", "track": "2"})
_lw = _fw2.lib_with_tags()[0]
check(_lw["artist"] == "Louise Hay" and _lw["title"] == "Seele" and _lw["genre"] == "Ruhig" and _fw2.lib[0]["artist"] == "Seele",
      "geschriebener Interpret geht vor Mixxx, der Rest bleibt, die Mixxx-Liste selbst unveraendert")
check(_fw2.lib_chunks == [(0, [])] and _fw2.lib_done < 0, "nach dem Schreiben: laufender Durchgang laeuft fertig, gleich danach ein neuer")
check(_mb.library_chunks(_fw2.lib_with_tags())[0][0][2] == "Louise Hay", "auch im Paket an den Pi")
_fw3 = _mb.Forwarder([{"path": _da, "duration": 1.0, "artist": "Seele", "title": "Seele"}], None, None, analysis_dir=_ad, analyze=False)
check(_fw3.lib_with_tags()[0]["artist"] == "Louise Hay", "gemerkt ueber einen Neustart der Bruecke")
_ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('getattr(server, "on_tags", None)' in _ms and "ms.on_tags = fw.tags_written" in open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read(),
      "Vorhoer-Server meldet geschriebene Tags an die Bruecke")
_mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check('if u.path == "/sync":' in _ms and "ms.sync_info = fw.sync_info" in open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read(),
      "Mac liefert den Abgleich unter /sync")
check("await fetch(music + '/sync')" in _mj and "Mixxx ist nicht mehr aktuell." in _mj and 'id="syncbox"' in open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read(),
      "Musik-Datenbank zeigt den Hinweis nur, wenn etwas nicht passt")
mjs = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check("const SHOW_MIN_S = 120;" in mjs and "r.dur < SHOW_MIN_S" in mjs, "+ Show und Quick erst ab 2 Minuten (Wunsch 09.11.2026)")
check("const TINY_S = 30;" in mjs and "td: r => tiny(r) ? '' : r.best === 2" in mjs and "if (tiny(r)) return '';" in mjs,
      "unter 30 s: BPM und Tonart leer, kein ? (Wunsch 09.11.2026)")
_mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("Object.keys(g).sort((a, b) => a.localeCompare(b, 'de', { sensitivity: 'base' }))" in _mj, "Genre-Auswahl alphabetisch (Wunsch 13.11.2026)")
finish("test_musik_datenbank")
