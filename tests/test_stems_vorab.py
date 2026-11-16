"""Pegelkurven vorab fuer die ganze Bibliothek (Wunsch von Markus, 06.11.2026): Der Pi fuehrt die Liste, der Windows-PC holt
die MP3s beim Vorhoer-Server am Mac, rechnet und schickt nur die Kurven. Shows finden sie spaeter ueber den Fingerabdruck."""
import base64
import os
import sys
import tempfile
import urllib.error

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "stems"))
import stems_show as ss  # noqa: E402
from showman import stems_bulk as sb  # noqa: E402
from showman import store as st  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_vorab_")

# ---- Fingerabdruck: PC und Pi rechnen gleich ----
for i, (pre, post) in enumerate([(b"", b""), (b"ID3\x03\x00\x00\x00\x00\x01\x00" + b"x" * 128, b""), (b"", b"TAG" + b"y" * 125),
                                 (b"ID3\x04\x00\x10\x00\x00\x00\x20" + b"z" * 42, b"TAG" + b"q" * 125)]):
    p = os.path.join(tmp, "f%d.mp3" % i)
    with open(p, "wb") as f:
        f.write(pre + bytes(range(256)) * 1500 + post)
    check(ss.audio_fingerprint(p) == st.audio_fingerprint(p), "Fingerabdruck wie am Pi (Fall %d: Tags vorn/hinten)" % i)

# ---- Pi: Liste ----
store = st.ShowStore(os.path.join(tmp, "shows"))
LIB = [{"title": "A - Kurz", "dur": 12.0, "path": "/m/kurz.mp3"}, {"title": "B - Eins", "dur": 200.0, "path": "/m/eins.mp3"},
       {"title": "C - Mix", "dur": 3600.0, "path": "/m/mix.mp3"}, {"title": "D - Zwei", "dur": 300.0, "path": "/m/zwei.mp3"},
       {"title": "E - ohne Pfad", "dur": 200.0, "path": ""}, {"title": "B - Eins", "dur": 200.0, "path": "/m/eins.mp3"},
       {"title": "G - Move", "dur": 200.0, "path": "/m/move.mp4"}]
music = [""]
clock = [1000.0]
bulk = sb.StemBulk(store, lambda: LIB, lambda: music[0], now=lambda: clock[0])
s0 = bulk.status()
check(s0["on"] is False and s0["total"] == 2 and s0["long"] == 1 and s0["done"] == 0, "nur Lieder 30 s bis 10 min (Standard) mit Pfad, je Pfad einmal")
lim = [480.0]
blim = sb.StemBulk(st.ShowStore(os.path.join(tmp, "shows_lim")), lambda: LIB + [{"title": "H - Lang", "dur": 540.0, "path": "/m/lang.mp3"}], lambda: "", max_s=lambda: lim[0])
s_l = blim.status()
lim[0] = 0.0
s_0 = blim.status()
check(s_l["total"] == 2 and s_l["long"] == 2 and s_l["max_min"] == 8.0 and s_0["total"] == 4 and s_0["long"] == 0,
      "Grenze aus der Einstellung (8 min), 0 = keine Grenze (09.11.2026)")
check(s0["other"] == 1, "MP4 (Anachronic Jazz Band - Move) nicht im Vorab-Lauf, als 'keine MP3' gezaehlt statt als Fehler")
check(bulk.next("PC") == {"off": True}, "aus: nichts zu tun")
bulk.set(True)
check("wait" in bulk.next("PC"), "Mac-Bruecke nicht verbunden: warten")
music[0] = "http://mac:9025"
j1 = bulk.next("PC")
j2 = bulk.next("MAC")
check(j1["path"] == "/m/eins.mp3" and j1["music"] == "http://mac:9025" and j2["path"] == "/m/zwei.mp3", "jeder Rechner bekommt ein anderes Lied")
check(bulk.next("PC")["path"] == "/m/eins.mp3", "eigenes Lied bekommt man wieder (Abbruch, Neustart)")
check(bulk.next("NOCH1") == {"done": True}, "alle vergeben: nichts mehr")
check([w["who"] for w in bulk.status()["work"]] == ["PC", "MAC"] or sorted(w["who"] for w in bulk.status()["work"]) == ["MAC", "PC"], "Anzeige: wer woran rechnet")


def data(fp, dur=10.0):
    c = base64.b64encode(bytes(int(dur * st.STEM_RATE))).decode()
    return {"v": 1, "rate": st.STEM_RATE, "db_min": -60, "duration": dur, "offset_ms": 0.0, "corr": None, "fp": fp, "model": "htdemucs",
            "created": "x", "curves": {k: c for k in st.STEM_CURVES}}


FP1, FP2 = "123:0123456789abcdef", "456:fedcba9876543210"
for bad in ("../x", "1:2", "abc"):
    try:
        bulk.note_fp("PC", "/m/eins.mp3", bad)
        check(False, "unbrauchbarer Fingerabdruck abgelehnt: " + bad)
    except ValueError:
        check(True, "unbrauchbarer Fingerabdruck abgelehnt: " + bad)
try:
    bulk.note_fp("PC", "/etc/passwd", FP1)
    check(False, "Pfad ausserhalb der Bibliothek abgelehnt")
except ValueError:
    check(True, "Pfad ausserhalb der Bibliothek abgelehnt")
try:
    bulk.done("PC", "/m/zwei.mp3", FP2, data(FP2))
    check(False, "fremdes Lied (rechnet MAC) abgelehnt")
except ValueError:
    check(True, "fremdes Lied (rechnet MAC) abgelehnt")
check(bulk.note_fp("PC", "/m/eins.mp3", FP1) == {"have": False}, "Fingerabdruck gemeldet, noch keine Kurven")
try:
    bulk.done("PC", "/m/eins.mp3", FP1, data(FP2))
    check(False, "Kurven zu anderer MP3 abgelehnt")
except ValueError:
    check(True, "Kurven zu anderer MP3 abgelehnt")
bulk.done("PC", "/m/eins.mp3", FP1, data(FP1), secs=18)
check(store.has_stems(FP1) and bulk.status()["done"] == 1 and bulk.status()["avg_s"] == 18.0, "Kurven abgelegt, gezaehlt, Rechenzeit gemerkt")
check(os.path.isfile(store._stems_path(FP1)) and store._stems_path(FP1).endswith("123_0123456789abcdef.json"), "dieselbe Ablage wie bei den Shows")
bulk.failed("MAC", "/m/zwei.mp3", "kaputt")
check(bulk.status()["failed"][0]["title"] == "D - Zwei" and bulk.status()["failed"][0]["error"] == "kaputt" and bulk.status()["failed"][0]["path"] == "/m/zwei.mp3",
      "Seite Statistik: welches Lied mit welchem Fehler (Wunsch von Markus)")
check(bulk.status()["fail"] == 1 and bulk.next("PC") == {"done": True}, "Fehler: erst einmal nicht wieder")
clock[0] += sb.RETRY_S + 1
check(bulk.retry()["fail"] == 0 and bulk.next("PC")["path"] == "/m/zwei.mp3", "Knopf Fehler neu versuchen: sofort wieder dran")
store.save_stems_fp(FP2, data(FP2))
check(bulk.note_fp("PC", "/m/zwei.mp3", FP2) == {"have": True} and not bulk.status()["work"], "gleiche MP3 wie eine Show: hat schon Kurven, nichts zu rechnen")
check(bulk.status()["done"] == 2 and bulk.next("PC") == {"done": True}, "alles fertig")
bulk.set(False)
b2 = sb.StemBulk(store, lambda: LIB, lambda: music[0], now=lambda: clock[0])
check(b2.on is False and b2.fps.get("/m/eins.mp3") == FP1 and b2.status()["done"] == 2, "Stand bleibt nach einem Neustart")
b2.set(True)
b3 = sb.StemBulk(store, lambda: LIB, lambda: music[0], now=lambda: clock[0])
check(b3.on is True, "laeuft nach einem Neustart weiter, wenn es lief")
LIB.append({"title": "F - Neu", "dur": 180.0, "path": "/m/neu.mp3"})
check(b3.next("PC")["path"] == "/m/neu.mp3", "neue Lieder der Bibliothek kommen spaeter dran")
clock[0] += sb.CLAIM_S + 1
check(b3.next("MAC")["path"] == "/m/neu.mp3", "nach 20 Minuten darf ein anderer Rechner (abgestuerzter PC)")

# ---- Helfer: ein Schritt ----


class Pi:
    def __init__(self, job, have=False):
        self.job, self.have, self.ops = job, have, []

    def op(self, op, **d):
        self.ops.append((op, d))
        if op == "stems_bulk_next":
            return self.job
        if op == "stems_bulk_fp":
            return {"have": self.have}
        return {}


def fake(audio, tmp_):
    import numpy as np
    x = np.zeros((44100 * 2, 2), dtype="float32")
    return {s: x for s in ss.STEMS}, 44100


def fetch_ok(music_, path, dest):
    with open(dest, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" + bytes(5000))


JOB = {"path": "/m/eins.mp3", "title": "B - Eins", "dur": 200.0, "music": "http://mac:9025"}
p = Pi(JOB)
out = []
check(ss.bulk_step(p, fake, out.append, fetch_ok) is True, "ein Lied gerechnet")
done = [d for o, d in p.ops if o == "stems_bulk_done"]
check(len(done) == 1 and done[0]["path"] == "/m/eins.mp3" and done[0]["data"]["fp"] == done[0]["fp"] and done[0]["data"]["corr"] is None,
      "Kurven mit Fingerabdruck an den Pi, ohne Wellenform")
p = Pi(JOB, have=True)
ss.bulk_step(p, fake, out.append, fetch_ok)
check(not any(o == "stems_bulk_done" for o, _ in p.ops), "schon vorhanden: nicht rechnen")
for job in ({"off": True}, {"done": True}, {"wait": "Mac"}):
    check(ss.bulk_step(Pi(job), fake, out.append, fetch_ok) is False, "nichts zu tun: %s" % list(job)[0])


def fetch_down(music_, path, dest):
    raise urllib.error.URLError("Verbindung abgelehnt")


def fetch_404(music_, path, dest):
    raise urllib.error.HTTPError("http://mac:9025/audio", 404, "nicht gefunden", {}, None)


p = Pi(JOB)
check(ss.bulk_step(p, fake, out.append, fetch_down, alive=lambda m: False) is False and not any(o == "stems_bulk_fail" for o, _ in p.ops),
      "Mac aus: Runde endet, kein Lied als Fehler (sonst waere die ganze Bibliothek markiert)")
p = Pi(JOB)
check(ss.bulk_step(p, fake, out.append, fetch_down, alive=lambda m: True) is True and any(o == "stems_bulk_fail" for o, _ in p.ops),
      "Mac antwortet, nur die Datei nicht (2–4 Family - Stay): Lied als Fehler, weiter mit dem naechsten statt endlos dasselbe")
p = Pi(JOB)
check(ss.bulk_step(p, fake, out.append, fetch_404) is True and any(o == "stems_bulk_fail" for o, _ in p.ops), "Datei fehlt am Mac: nur dieses Lied als Fehler")


class Old:
    def op(self, op, **d):
        raise ValueError("Unbekannter Befehl")


check(ss.bulk_step(Old(), fake, out.append, fetch_ok) is False, "aelterer Pi ohne Vorab-Lauf: nichts tun")
src = open(os.path.join(ROOT, "mac", "stems", "stems_show.py"), encoding="utf-8").read()
check("watch(c, log=tlog, vorab=a.vorab, reserve=a.reserve)" in src and "BULK_ROUND_S" in src, "Waechter mit --vorab; Shows gehen alle 5 min wieder vor")


# 08.11.2026: Mac als Reserve fuer die letzten Lieder (Windows-PC aus)
class St:
    def __init__(self, st):
        self.st = st

    def op(self, op, **d):
        return self.st if op == "stems_bulk_status" else {}


base_st = {"on": True, "total": 7432, "done": 7430, "fail": 0, "workers": []}
check(ss.reserve_ok(St(base_st)), "PC aus, nur 2 fehlen: der Mac rechnet")
check(ss.reserve_ok(St(dict(base_st, workers=[ss.WHO]))), "der Mac selbst zaehlt nicht als anderer Rechner")
check(not ss.reserve_ok(St(dict(base_st, workers=["WINDOWS-PC"]))), "PC holt Arbeit: der Mac nicht")
check(not ss.reserve_ok(St(dict(base_st, done=7000))), "viele fehlen (432): nicht auf der langsamen Mac-CPU")
check(not ss.reserve_ok(St(dict(base_st, on=False))) and not ss.reserve_ok(St(dict(base_st, done=7432))), "Vorab aus oder fertig: nichts")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check("--watch --reserve" in inst, "Mac-Waechter startet als Reserve")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check("--vorab" not in inst, "Mac-Waechter rechnet die Bibliothek nicht vorab (zu langsam)")

# ---- Seite Statistik ----
sys.path.insert(0, os.path.join(ROOT, "pi"))
import webpanel  # noqa: E402
pg = webpanel.stats_page()
check("Lieder mit Fehler anzeigen" in pg and "li.textContent=f.title+': '+f.error" in pg, "Karte listet die Lieder mit Fehler (nur als Text)")
check("op:'stems_bulk_retry'" in pg and 'op == "stems_bulk_retry"' in open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read(), "Knopf Fehler neu versuchen")
check('id="stbulk"' in pg and "stBulkCmd({op:'stems_bulk',on:!s.on})" in pg and "loadStemBulk()" in pg, "Karte mit Starten/Anhalten auf der Seite Statistik")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check(all('op == "%s"' % o in api for o in ("stems_bulk", "stems_bulk_status", "stems_bulk_next", "stems_bulk_fp", "stems_bulk_done", "stems_bulk_fail")),
      "Befehle am Pi")
eng = open(os.path.join(ROOT, "pi", "showman", "engine.py"), encoding="utf-8").read()
check("stem" not in eng, "aufs Licht wirkt das nicht")
finish("test_stems_vorab")
