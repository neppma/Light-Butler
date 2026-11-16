"""Quick in der Musik-Datenbank (Wunsch von Markus 06.11.2026): Show anlegen, Cue-Punkte und Abschnitte vom Mac, Liedtext aus dem
Speicher, dann der Assistent mit Standardwerten. Hier: Mac-Seite (/marks) und Pi-Seite (marks_from_mac, lyrics_quick)."""
import io
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request

from _common import ROOT, build, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge as mb  # noqa: E402
import music_serve  # noqa: E402
from mixxx_link import MixxxLink  # noqa: E402
from showman import lyrics as ly  # noqa: E402
from showman.api import ShowManager  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_quick_")

# ---- Mac: Analyse eines Liedes der Bibliothek, ohne Deck ----
P = "/Volumes/s2l_kein_stick/musik/a/Lied.mp3"
rec = {"artist": "A", "title": "Lied", "duration": 200.0, "bpm": 128.0, "kid": 22, "genre": "House", "comment": "8A - Energy 7",
       "path": P, "cues": [10.0, 60.0, 250.0]}
fw = mb.Forwarder([rec], None, None, analysis_dir=tmp, analyze=False)
key = mb.track_key(200.0, 128.0, 22)
with open(os.path.join(tmp, key + ".json"), "w", encoding="utf-8") as f:
    json.dump({"artist": "A", "title": "Lied", "duration": 200.0, "events": [{"type": "drop", "t": 60.0, "strength": 0.9}],
               "energy": [50] * 200}, f)
m = fw.marks_for_path(P)
check(m is not None and m["title"] == "A - Lied" and m["cu"] == [10.0, 60.0] and m["ev"][0][:2] == ["drop", 60.0] and m["genre"] == "House" and m["lvl"] == 7,
      "Bruecke: Hotcues (nur im Lied), Drops, Genre und Energie wie fuer ein Deck")
check(fw.marks_for_path("/x/fremd.mp3") is None, "unbekanntes Lied: nichts")
os.remove(os.path.join(tmp, key + ".json"))
check(fw.marks_for_path(P) is None, "noch nicht analysiert: nichts")

srv = music_serve.MusicServer([P], port=0, marks=lambda p: {"title": "A - Lied", "cu": [10.0]} if p == P else None)
srv.start()
base = f"http://127.0.0.1:{srv.port}"
with urllib.request.urlopen(base + "/marks?p=" + urllib.parse.quote(P, safe=""), timeout=5) as r:
    check(json.loads(r.read())["cu"] == [10.0], "Vorhoer-Server: /marks liefert die Analyse")
try:
    urllib.request.urlopen(base + "/marks?p=" + urllib.parse.quote("/etc/passwd", safe=""), timeout=5)
    check(False, "nur Lieder der Bibliothek")
except urllib.error.HTTPError as e:
    check(e.code == 404, "nur Lieder der Bibliothek")
srv.stop()

# ---- Pi: in die Show uebernehmen ----
link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_quick_pi_"))
link.feed({"type": "lib", "i": 0, "n": 1, "t": [["A - Lied", 200.0, "A", "Lied", 128.0, "Am", 22, "House", 7, "Lied.mp3", 2, 1, P]]}, 1.0)
mgr.op({"op": "create", "name": "A - Lied", "title": "A - Lied", "dur": 200.0})
check(mgr.op({"op": "marks_from_mac", "name": "A - Lied"}) == {"found": False, "why": "Musik-Rechner nicht verbunden"}, "Musik-Rechner nicht da: kein Fehler, nur ohne Cues")
mgr.music_url = lambda: "http://mac:9025"
seen = []


class R(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def mac(url, timeout=0):
    seen.append(url)
    return R(json.dumps({"title": "A - Lied", "du": 200.0, "se": [["intro", 0, 30], ["main", 30, 200]], "cu": [10.0, 60.0],
                         "ev": [["drop", 60.0, 60.0, 0.9, ""]], "en": [50] * 200, "lvl": 7, "genre": "House", "fp": ""}).encode())


mgr.mac_opener = mac
r = mgr.op({"op": "marks_from_mac", "name": "A - Lied"})
doc = mgr.store.load("A - Lied")
check(r["found"] and doc["marks"]["cu"] == [10.0, 60.0] and doc["marks"]["se"][0][0] == "intro" and doc["marks"]["genre"] == "House",
      "Pi: Cue-Punkte, Abschnitte und Genre in der Show, wie aus einem Deck")
check(seen and urllib.parse.unquote(seen[0].split("p=")[1]) == P, "fragt den Mac nach genau dieser Datei")
check(mgr.assist_info("A - Lied")["source"] == "mixxx", "der Assistent nutzt sie (Aufbau aus Mixxx statt Wellenform)")

# ---- Pi: Liedtext ----
cache = ly.LyricCache(os.path.join(tmp, "ly.db"))
sh.lyric_cache = cache
calls = []
mgr.lyrics_opener = lambda req, timeout=0: (calls.append(req), (_ for _ in ()).throw(OSError("kein Netz")))[1]
cache.store("A - Lied", 200.0, [[1.0, "Hallo"], [3.0, "Welt"]])
r = mgr.op({"op": "lyrics_quick", "name": "A - Lied"})
check(r["from"] == "cache" and mgr.store.load("A - Lied")["lyrics"]["lines"][0] == [1.0, "Hallo"] and not calls, "Liedtext aus dem Speicher, ohne Internet")
mgr.op({"op": "create", "name": "B - Nichts", "title": "B - Nichts", "dur": 180.0})
cache.store("B - Nichts", 180.0, [])
check(mgr.op({"op": "lyrics_quick", "name": "B - Nichts"})["from"] == "none" and not calls, "schon gesucht, nichts gefunden: nicht wieder fragen")
mgr.op({"op": "create", "name": "C - Neu", "title": "C - Neu", "dur": 180.0})
check(mgr.op({"op": "lyrics_quick", "name": "C - Neu"})["from"] == "none" and calls, "nie gesucht: einmal LRCLIB, kein Netz ist kein Fehler")

# ---- quick_meta: Laenge, Tempo und MP3 in die Show, ohne sie zu laden ----
mgr.op({"op": "create", "name": "D - Meta", "title": "D - Meta", "dur": 180.0})
loaded_before = mgr.engine.loaded
r = mgr.op({"op": "quick_meta", "name": "D - Meta", "duration": 181.5, "bpm": 124.0, "offset": 0.31})
dm = mgr.store.load("D - Meta")
check(dm["duration"] == 181.5 and dm["bpm"] == 124.0 and dm["beat_offset"] == 0.31 and dm["audio"] == "audio.mp3", "quick_meta: Laenge, Tempo, Taktbeginn, MP3")
check(mgr.engine.loaded == loaded_before, "quick_meta laedt die Show nicht in die Abspiel-Maschine")
ejs = open(os.path.join(ROOT, "pi", "static", "sm", "editor.js"), encoding="utf-8").read()
i = ejs.index("async function quickAssist")
q = ejs[i:i + 1500]
check(q.index("marks_from_mac") < q.index("lyrics_quick") < q.index("SM.cmd('assist'"), "Quick: erst Cues vom Mac, dann Liedtext, dann der Assistent")
check("if (!macTried && (doc.mixxx || {}).title && !(m0.se || []).length && !(m0.cu || []).length)" in ejs and "SM.cmd('marks_from_mac', { name: NAME }); if (x.found)" in ejs,
      "Editor: fehlen Cues und Abschnitte, einmal vom Mac holen (jede Show, nicht nur Quick)")
finish("test_quick")
