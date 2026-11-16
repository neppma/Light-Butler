"""BPM fuer Lieder ohne BPM in Mixxx und Angaben aus Mixxx beim Umwandeln (Fehlerbericht und Wunsch von Markus, 07.11.2026):
nach dem Umwandeln einer MP4 fehlten BPM und Tonart, ausserdem soll es neben Energie und Tonart auch eine BPM-Messung geben."""
import json
import os
import random
import sys
import tempfile

from _common import ROOT, check, finish

BRIDGE = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BRIDGE)
import convert_mp3 as cm    # noqa: E402
import id3_tags as it       # noqa: E402
import key_estimate as ke   # noqa: E402
import mixxx_bridge as mb   # noqa: E402
import mixxx_link           # noqa: E402
import tag_edit as te       # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_bpm_")
AUDIO = bytes(random.Random(4).getrandbits(8) for _ in range(20000))


def mp3(name, frames, ver=3):
    data = b"".join(it.frame(f, b, ver) for f, b in frames) + b"\0" * 64
    n = len(data)
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(b"ID3" + bytes([ver, 0, 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127]) + data + AUDIO)
    return p


# ---- Umwandeln: Angaben aus Mixxx in leere Felder der neuen MP3 ----
dst = mp3("neu.mp3", [(b"TIT2", it.text_body("Aus der Quelle")), (b"TALB", it.text_body("Album"))])
put = cm.add_tags(dst, {"title": "Aus Mixxx", "artist": "Dj Fresh", "bpm": "174", "key": "8A", "comment": "8A - Energy 8", "genre": "", "unbekannt": "x"})
f = te.read_tags(dst)["fields"]
check(put == {"artist": "Dj Fresh", "bpm": "174", "key": "8A", "comment": "8A - Energy 8"}, "nur leere Felder gesetzt, leere Werte und Unbekanntes uebergangen")
check(f["title"] == "Aus der Quelle" and f["album"] == "Album" and f["bpm"] == "174" and f["key"] == "8A", "Angaben der Quelle bleiben, BPM und Tonart aus Mixxx dazu")
fw = mb.Forwarder([{"path": "/m/a.mp4", "artist": "Dj Fresh", "title": "Hypercaine", "bpm": 174.0, "kid": 22, "key": "8A",
                    "genre": "Drum & Bass", "comment": "8A - Energy 8", "duration": 300.0},
                   {"path": "/m/b.mp4", "artist": "X", "title": "Y", "bpm": 127.99, "kid": 0, "key": "", "comment": None}], None, None,
                  analysis_dir=tmp, analyze=False)
check(fw.meta_for_path("/m/a.mp4") == {"title": "Hypercaine", "artist": "Dj Fresh", "genre": "Drum & Bass", "bpm": "174", "key": "8A",
                                       "comment": "8A - Energy 8"}, "Angaben aus Mixxx zum Lied (Tonart als Camelot)")
check(fw.meta_for_path("/m/b.mp4")["bpm"] == "127.99" and fw.meta_for_path("/m/b.mp4")["key"] == "" and fw.meta_for_path("/fremd") == {},
      "BPM mit zwei Stellen, ohne Tonart leer, unbekanntes Lied leer")
seen = []
jobs = cm.Jobs(convert_fn=lambda s: dst)
cm_add = cm.add_tags
cm.add_tags = lambda d, t: seen.append((d, t)) or {"bpm": t["bpm"]}
jobs.start("/m/a.mp4", "/x/a.mp4", {"bpm": "174"})
import time  # noqa: E402
for _ in range(100):
    if jobs.status("/m/a.mp4").get("state") == "ok":
        break
    time.sleep(0.02)
cm.add_tags = cm_add
check(seen == [(dst, {"bpm": "174"})] and jobs.status("/m/a.mp4")["tags"] == ["bpm"], "nach dem Umwandeln kommen die Angaben in die MP3")
ms_src = open(os.path.join(BRIDGE, "music_serve.py"), encoding="utf-8").read()
mb_src = open(os.path.join(BRIDGE, "mixxx_bridge.py"), encoding="utf-8").read()
check("tags = getm(p) if getm is not None else None" in ms_src and "jobs.start(p, f, tags)" in ms_src and "ms.meta = fw.meta_for_path" in mb_src,
      "Vorhoer-Server holt die Angaben bei der Bruecke")

# ---- BPM-Messung: TBPM der Datei, sonst essentia, Grenzen ----
check(ke.judge_bpm(174.04, 200) == 174.0 and ke.judge_bpm(300, 200) == 0 and ke.judge_bpm(120, 10) == 0 and ke.judge_bpm(120, 5000) == 0,
      "BPM nur im ueblichen Bereich und bei normaler Liedlaenge")
tb = mp3("tbpm.mp3", [(b"TBPM", it.text_body("128")), (b"TKEY", it.text_body("8A"))])
r = ke.measure_one({"path": "/m/t", "file": tb, "need_key": False, "need_bpm": True})
check(r == {"path": "/m/t", "v": ke.KEY_VERSION, "bpm": 128.0, "bsrc": "tag"}, "TBPM der Datei geht vor, Tonart nicht gefragt")
r = ke.measure_one({"path": "/m/t", "file": tb, "need_key": True, "need_bpm": True})
check(r["kid"] == ke.kid_from_text("8A") and r["src"] == "tag" and r["bsrc"] == "tag", "beides aus der Datei in einem Durchgang")

base = os.path.join(tmp, "tonart")
os.makedirs(base)
with open(os.path.join(base, ke.KEYS_FILE), "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"path": "/m/nur_bpm", "v": 2, "bpm": 140.0, "bsrc": "essentia"}) + "\n")
    fh.write(json.dumps({"path": "/m/beides", "v": 2, "kid": 22, "src": "essentia", "bpm": 0.0, "bsrc": "unsicher"}) + "\n")
    fh.write(json.dumps({"path": "/m/tag", "v": 2, "bpm": 99.5, "bsrc": "tag"}) + "\n")
kest = ke.KeyEstimator(base=base, ess_py="")
check(kest.bpm("/m/nur_bpm") == (140.0, 1) and kest.bpm("/m/beides") == (0.0, 2) and kest.bpm("/m/tag") == (99.5, 0) and kest.bpm("/m/neu") == (0.0, 0),
      "BPM: geschaetzt, nicht bestimmbar, aus der Datei, unbekannt")
check("/m/nur_bpm" not in kest.keys and kest.key("/m/beides") == (22, 1), "Zeile nur mit BPM setzt keine Tonart")
started = []
kest.running = lambda: False


class _P:
    def poll(self):
        return None


def fake_popen(args, **kw):
    started.append(json.load(open(args[args.index("--liste") + 1], encoding="utf-8")))
    return _P()


ke_popen = ke.subprocess.Popen
ke.subprocess.Popen = fake_popen
kest.start([{"path": "/m/nur_bpm", "file": "/f/a.mp3", "need_key": True, "need_bpm": True},
            {"path": "/m/beides", "file": "/f/b.mp3", "need_key": True, "need_bpm": True},
            {"path": "/m/x", "file": "/f/x.mp3", "need_key": False, "need_bpm": True},
            {"path": "/m/y", "file": "/f/y.mp3"}])
ke.subprocess.Popen = ke_popen
todo = {t["path"]: (t["need_key"], t["need_bpm"]) for t in started[0]}
check(todo == {"/m/nur_bpm": (True, False), "/m/x": (False, True), "/m/y": (True, False)}, "nur messen, was fehlt (Tonart, BPM oder beides)")

# ---- Bruecke und Pi ----
lib = [{"path": "/m/nur_bpm", "artist": "A", "title": "Geschaetzt", "duration": 100.0, "kid": 5, "key": "3B", "bpm": 0},
       {"path": "/m/beides", "artist": "A", "title": "Unsicher", "duration": 100.0, "kid": 5, "key": "3B", "bpm": 0},
       {"path": "/m/mixxx", "artist": "A", "title": "Mixxx", "duration": 100.0, "kid": 5, "key": "3B", "bpm": 126.0}]
items = {x[3]: x for ch in mb.library_chunks(lib, kest=kest) for x in ch}
check(items["Geschaetzt"][4] == 140.0 and items["Geschaetzt"][19] == 1 and items["Unsicher"][4] == 0 and items["Unsicher"][19] == 2
      and items["Mixxx"][4] == 126.0 and items["Mixxx"][19] == 0, "Bibliothek: BPM aus Mixxx, sonst geschaetzt mit Kennzeichen")
check(mixxx_link.lib_item(items["Geschaetzt"])["best"] == 1 and mixxx_link.lib_item(items["Unsicher"])["best"] == 2
      and mixxx_link.lib_item(["T", 1.0])["best"] == 0, "Pi liest das Kennzeichen, alte Bruecke: keins")
check('"need_bpm": not r.get("bpm")' in mb_src, "Bruecke misst Lieder ohne BPM in Mixxx")

# ---- Schreiben ins TBPM: nur mit Schalter, nie ueber ein vorhandenes ----
w = mp3("w.mp3", [(b"TIT2", it.text_body("x"))])
check(ke.write_bpm_tag(w, 139.96) == "ok" and it.read_text(w, b"TBPM") == "140", "BPM ins TBPM, gerundet")
check(ke.write_bpm_tag(w, 140.0) == "gleich" and ke.write_bpm_tag(w, 141) == "ok" and it.read_text(w, b"TBPM") == "141", "eigene Schaetzung darf ersetzt werden")
check(ke.write_bpm_tag(tb, 100) == "vorhanden" and it.read_text(tb, b"TBPM") == "128", "vorhandenes TBPM nie ueberschrieben")
check(ke.write_bpm_tag(w, 999) == "BPM ungueltig", "unsinnige BPM nicht geschrieben")
kest.keys, kest.bpms, kest.written = {}, {"/m/w": (150.0, "essentia"), "/m/u": (0.0, "unsicher")}, {}
kest.write_tick([("/m/w", w), ("/m/u", tb)], gap_s=0)
kest.writer.join(5)
check(kest.written == {"bpm:/m/w": 150.0} and it.read_text(w, b"TBPM") == "150", "Schreib-Takt: nur geschaetzte BPM, je Lied einmal")
st = open(os.path.join(ROOT, "pi", "settings.py"), encoding="utf-8").read()
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("Geschaetzte Tonart und BPM in die MP3 schreiben" in st, "Schalter key_write gilt fuer Tonart und BPM")
check("r.best === 1 ? '<span title=\"geschätzt (nicht aus Mixxx)\">~</span>'" in mj and "r.best === 2" in mj, "Musik-Datenbank: BPM mit ~ oder ?")
# Fehlerbericht 07.11.2026: BPM und Tonart kamen trotzdem nicht mit, weil die Bruecke meta erst nach dem Start setzt.
# Echter Ablauf: Server starten, DANACH meta setzen, dann umwandeln.
import music_serve as ms  # noqa: E402
import urllib.request  # noqa: E402
src4 = os.path.join(tmp, "Lied.mp4")
open(src4, "wb").write(b"x")
srv = ms.MusicServer([src4], port=0)
got = []
srv.jobs = cm.Jobs(convert_fn=lambda s: dst)
_add = cm.add_tags
cm.add_tags = lambda d, t: got.append(t) or {}
_ff = cm.find_ffmpeg
cm.find_ffmpeg = lambda: "/x/ffmpeg"
_tf = cm.target_for
cm.target_for = lambda s: os.path.join(tmp, "gibt-es-nicht.mp3")
check(srv.start(), "Server startet")
srv.meta = lambda p: {"bpm": "127.93", "key": "11A"} if p == src4 else {}
req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/convert", data=json.dumps({"p": src4, "name": "Lied.mp4"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=5) as resp:
    pass
for _ in range(100):
    if got:
        break
    time.sleep(0.02)
srv.stop()
cm.add_tags, cm.find_ffmpeg, cm.target_for = _add, _ff, _tf
check(got == [{"bpm": "127.93", "key": "11A"}], "meta erst nach dem Start gesetzt: BPM und Tonart kommen trotzdem in die MP3")
finish("BPM-Schaetzung")
