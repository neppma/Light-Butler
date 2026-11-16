"""Liedtext von LRCLIB: Zeiten nur bei passender Laenge, nur auf Knopfdruck, wirkt nie aufs Licht. LRCLIB ist nachgestellt, kein Netz."""
import io
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse

from _common import PI, build, check, finish

from showman import assistant as a
from showman import lyrics as ly
from showman import timeline as tl
from showman.api import ShowManager

check(ly.parse_lrc("[00:15.42] Hallo\n[01:02.5]Welt\nkaputt\n[00:20.00][00:40.00] Refrain\n[00:30.00]") == [[15.42, "Hallo"], [20.0, "Refrain"], [30.0, ""], [40.0, "Refrain"], [62.5, "Welt"]], "LRC lesen: Zeiten, Wiederholungen, Unsinn")
check(ly.parse_lrc(None) == [], "kein Text")
TITLE = "David Guetta & Morten Feat. Sia - Titanium (David Guetta & Morten Future Rave Remix)"
check(ly.split_title(TITLE)[0].startswith("David") and ly.split_title("Nur Titel") == ("", "Nur Titel"), "Interpret und Titel trennen")
q = ly.queries(TITLE)
check(q[0] == "David Guetta & Morten Feat. Sia Titanium (David Guetta & Morten Future Rave Remix)" and q[1] == "David Guetta Titanium" and q[2] == "Titanium", f"Suchbegriffe: {q}")


def rec(track, dur, synced=True, artist="David Guetta", **k):
    return {"trackName": track, "artistName": artist, "duration": dur, "plainLyrics": "Zeile eins\nZeile zwei", "syncedLyrics": "[00:15.42] Zeile eins\n[00:24.80] Zeile zwei" if synced else None, "instrumental": False, **k}


SEARCH = [rec("Titanium", 246.0), rec("Titanium (Future Rave Remix)", 346.0), rec("Titanium (David Guetta & MORTEN Future Rave Remix)", 211.0), rec("Ganz anders", 211.0, artist="Jemand"), rec("Titanium Instrumental", 211.0, instrumental=True)]
best = ly.pick(SEARCH, TITLE, 211.49)
check(best["duration"] == 211.0 and "Future Rave" in best["trackName"], "der Eintrag mit passender Laenge gewinnt, ein Remix bekommt seine Zeiten")
y = ly.to_lyrics(best, 211.49)
check(y["lines"] == [[15.42, "Zeile eins"], [24.8, "Zeile zwei"]] and y["plain"], "Zeilen mit Zeiten")
y2 = ly.to_lyrics(rec("Titanium", 246.0), 211.49)
check(y2["lines"] == [] and "Zeile eins" in y2["plain"], "Laenge passt nicht: nur Text, keine falschen Zeiten")
check(ly.pick([rec("Ganz anders", 211.0, artist="Jemand")], TITLE, 211.0) is None, "fremdes Lied wird nicht genommen")
y3 = ly.to_lyrics(dict(rec("X", 100.0), plainLyrics=None), 100.0)
check("Zeile eins" in y3["plain"], "Text notfalls aus den Zeilen")

asked = []


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *x):
        return False


def opener(req, timeout=0):
    asked.append(req)
    return Resp(json.dumps(SEARCH).encode())


got = ly.fetch(TITLE, 211.49, opener=opener)
check(got["lines"] and len(asked) == 1, "eine Anfrage reicht, wenn sie passt")
check(asked[0].full_url.startswith(ly.API) and "Titanium" in urllib.parse.unquote_plus(asked[0].full_url) and asked[0].get_header("User-agent") == ly.AGENT, "Anfrage an LRCLIB mit Titel")
check(not any(w in asked[0].full_url for w in ("192.168", "fritz" ".box", "markus")), "nichts vom Heimnetz in der Anfrage")
asked.clear()


def no_fit(req, timeout=0):
    asked.append(req)
    return Resp(json.dumps([rec("Titanium", 246.0)]).encode())


got = ly.fetch(TITLE, 211.49, opener=no_fit)
check(got["lines"] == [] and got["plain"] and len(asked) == 3, "alle Suchbegriffe probiert, dann Text ohne Zeiten")
for op, text in ((lambda q, timeout=0: Resp(b"[]"), "nichts gefunden"), (lambda q, timeout=0: Resp(b"kein json"), "nicht erreichbar")):
    try:
        ly.fetch(TITLE, 211.49, opener=op)
        check(False, text)
    except ValueError as e:
        check(text in str(e), f"Meldung: {text}")


def down(req, timeout=0):
    raise urllib.error.URLError("weg")


try:
    ly.fetch(TITLE, 211.49, opener=down)
    check(False, "ohne Netz")
except ValueError as e:
    check("nicht erreichbar" in str(e), "ohne Netz: Meldung, kein Absturz")

# ---- In der Show -----------------------------------------------------------------------------------------------------
rig, sh = build()
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_ly_"))
d = mgr.store.create("Lied")
d.update(bpm=120.0, duration=211.49, marks={"se": [], "cu": [], "ev": [], "en": [], "lvl": None, "genre": "", "title": TITLE, "fp": ""})
d["tracks"] = [{"target": {"fixture": "vega"}, "attr": "dimmer", "keys": [{"t": 0, "v": 9, "e": "linear"}], "clips": []}]
mgr.store.save("Lied", d)
before = mgr.store.load("Lied")["tracks"]
check("lyrics" not in mgr.store.load("Lied"), "ohne Knopfdruck kein Liedtext")
mgr.lyrics_opener = opener
r = mgr.op({"op": "lyrics_fetch", "name": "Lied"})
check(r["lyrics"]["lines"] and "Future Rave" in r["lyrics"]["title"], "Knopf holt den Text")
n = mgr.store.load("Lied")
check(n["lyrics"]["lines"] == r["lyrics"]["lines"] and n["tracks"] == before, "bleibt in der Show, sonst aendert sich nichts")
info = mgr.op({"op": "assist_info", "name": "Lied"})
check(info["lyrics_lines"] == 2 and info["lyrics_text"], "Fenster des Assistenten weiss davon")
check(tl.normalize(n) == n, "bleibt beim Speichern gleich")
c = tl.compile_show(n, rig)
e0 = tl.compile_show(dict(n, lyrics={"lines": []}), rig)
check(c.evaluate(5.0) == e0.evaluate(5.0), "wirkt nicht aufs Licht")
bad = tl.normalize(dict(n, lyrics={"lines": ["x", [1, "gut"], [-1, "nein"], [2, 3]], "plain": 5}))
check(bad["lyrics"]["lines"] == [[1.0, "gut"], [2.0, "3"]], "kaputte Datei wird bereinigt")
s = a.song_info(n)
b = a.design_request(n, mgr.meta(), s, {"laser": True}, "", "")
u = json.loads(b["messages"][0]["content"])
check(u["liedzeilen"] == n["lyrics"]["lines"] and "Zeile eins" in u["liedtext"], "Claude bekommt die Zeilen mit Zeiten")
b2 = a.design_request(n, mgr.meta(), s, {}, "", "Eigener Text")
check(json.loads(b2["messages"][0]["content"])["liedtext"] == "Eigener Text", "eigener Text geht vor")
check("liedzeilen" in a.DESIGN_SYSTEM, "Anleitung erklaert die Zeilen")
check(mgr.op({"op": "lyrics_clear", "name": "Lied"}) == {"lyrics": None} and "lyrics" not in mgr.store.load("Lied"), "Liedtext wieder weg")
mgr.lyrics_opener = down
try:
    mgr.op({"op": "lyrics_fetch", "name": "Lied"})
    check(False, "Fehler kommt als Meldung")
except ValueError:
    check("lyrics" not in mgr.store.load("Lied"), "Fehler kommt als Meldung, die Show bleibt")
ed = open(os.path.join(PI, "static", "sm", "editor.js"), encoding="utf-8").read()
tj = open(os.path.join(PI, "static", "sm", "timeline.js"), encoding="utf-8").read()
pj = open(os.path.join(PI, "static", "sm", "play.js"), encoding="utf-8").read()
cj = open(os.path.join(PI, "static", "sm", "core.js"), encoding="utf-8").read()
check("SM.lyricEnd" in cj and "SM.lyricEnd(L, i)" in tj and "SM.lyricEnd(lyricLines, i)" in pj, "Balken und Playback nutzen dieselbe Rechnung")
check("SM.cmd('lyrics_fetch'" in ed and "drawLyrics(" in tj and "plyric" in pj, "Knopf, Anzeige in der Wellenform und auf der Playback-Seite")

# ---- Hauptpanel ------------------------------------------------------------------------------------------------------
L_E = [[10.0, "drei kleine Woerter"], [13.0, ""], [20.0, "kurz"], [21.0, "lange Pause danach"], [90.0, "Ende"]]
check(ly.line_end(L_E, 0) == 13.0, "Leerzeile: echtes Ende der Zeile")
check(ly.line_end(L_E, 2) == 21.0, "naechste Zeile kommt: spaetestens dort Schluss")
check(abs(ly.line_end(L_E, 3) - 24.8) < 0.01 and ly.line_at(L_E, 30.0) == "" and ly.line_at(L_E, 22.0) == "lange Pause danach", "vor einem langen Instrumental: Ende geschaetzt, die Zeile bleibt nicht stehen")
check(ly.line_end([[0.0, "wort " * 50]], 0) == ly.LINE_MAX_S, "hoechstens 12 Sekunden")
blank = ly.to_lyrics(rec("X", 100.0, syncedLyrics="[00:01.00]\n[00:02.00] Eins\n[00:04.00]\n[00:09.00] Zwei"), 100.0)
check(blank["lines"] == [[2.0, "Eins"], [4.0, ""], [9.0, "Zwei"]], "Leerzeilen bleiben als Ende, davor keine")
check(ly.line_at([[1.0, "a"], [5.0, "b"]], 0.5) == "" and ly.line_at([[1.0, "a"], [5.0, "b"]], 3.0) == "a" and ly.line_at([[1.0, "a"], [5.0, "b"]], 6.0) == "b", "aktuelle Zeile zur Stelle")
tmp_c = tempfile.mkdtemp(prefix="s2l_lyc_")
path = os.path.join(tmp_c, "c.db")
calls = []


def op_c(req, timeout=0):
    calls.append(req)
    return Resp(json.dumps(SEARCH).encode())


lc = ly.LyricCache(path, opener=op_c, sync=True)
got = lc.get(TITLE, 211.49, 100.0)
check(got == [[15.42, "Zeile eins"], [24.8, "Zeile zwei"]], "Lied aus Mixxx: Zeilen werden geholt")
n1 = len(calls)
check(lc.get(TITLE, 211.49, 101.0) == got and len(calls) == n1, "jedes Lied nur einmal gefragt")
check(ly.LyricCache(path, opener=down, sync=True).get(TITLE, 211.49, 200.0) == got, "nach Neustart bekannt, auch ohne Netz")
check(ly.LyricCache(path).lookup(TITLE, 212.2) == got, "Laenge aus Analyse und Mixxx darf um 1 s abweichen")
lc2 = ly.LyricCache(os.path.join(tmp_c, "d.db"), opener=lambda q, timeout=0: Resp(b"[]"), sync=True)
check(lc2.get("Niemand - Kennt", 100.0, 1.0) == [] and lc2.lookup("Niemand - Kennt", 100.0) == [], "nichts gefunden: wird gemerkt, nicht immer wieder gefragt")
lc3 = ly.LyricCache(os.path.join(tmp_c, "e.db"), opener=down, sync=True)
check(lc3.get(TITLE, 211.49, 1.0) == [] and lc3.lookup(TITLE, 211.49) is None, "kein Netz: nicht gemerkt")
lc3.opener = op_c
check(lc3.get(TITLE, 211.49, 2.0) == [], "kurz danach: keine neue Anfrage")
check(lc3.get(TITLE, 211.49, 2.0 + lc3.RETRY_S) != [], "spaeter wieder versucht")
lc4 = ly.LyricCache(os.path.join(tmp_c, "f.db"), opener=op_c)
t_a = time.time()
check(lc4.get(TITLE, 211.49) == [] and time.time() - t_a < 0.05, "die Suche haelt das Licht nie auf")
time.sleep(0.3)

# ---- Ganze Bibliothek vorab --------------------------------------------------------------------------------------------
LIB = [["Interpret %d - Lied" % i, 200.0 + i] for i in range(6)]
reqs = []


def op_lib(req, timeout=0):
    reqs.append(req)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(req.full_url).query)["q"][0]
    if "Interpret 1 " in q or q == "Lied" and False:
        return Resp(b"[]")
    n = q.split()[1] if q.split()[0] == "Interpret" and len(q.split()) > 1 else "0"
    return Resp(json.dumps([rec("Lied", 200.0 + int(n), artist="Interpret " + n)]).encode())


lb_cache = ly.LyricCache(os.path.join(tmp_c, "b.db"), opener=op_lib)
lb = ly.LyricBulk(lb_cache, lambda: LIB)
lb.GAP_S = 0.0
lb.start()
lb.thread.join(10)
st = lb.status()
check(not st["running"] and st["seen"] == 6 and st["total"] == 6 and st["found"] >= 4, f"ganze Bibliothek abgearbeitet: {st}")
n_lib = len(reqs)
check(lb_cache.meta(lb.FLAG) == "0", "fertig: laeuft nach einem Neustart nicht wieder an")
lb.start()
lb.thread.join(5)
check(len(reqs) == n_lib, "zweiter Lauf: bekannte Lieder werden nicht noch einmal gefragt")
LIB.append(["Interpret 9 - Neu", 300.0])
lb.start()
lb.thread.join(5)
check(lb_cache.lookup("Interpret 9 - Neu", 300.0) is not None and len(reqs) > n_lib, "neue Lieder kommen beim naechsten Lauf dazu")
gaps = ly.LyricBulk(ly.LyricCache(os.path.join(tmp_c, "g2.db"), opener=op_lib), lambda: [["Interpret 2 - Lied", 202.0]])
check(gaps.GAP_S >= 3.0, "Standard: hoechstens eine Anfrage alle 3 Sekunden")
gaps.start()
time.sleep(0.2)
check(gaps.status()["running"] and gaps.cache.meta(gaps.FLAG) == "1", "laeuft und merkt sich das")
t_b = time.time()
gaps.stop()
gaps.thread.join(2)
check(not gaps.thread.is_alive() and time.time() - t_b < 1.0 and gaps.cache.meta(gaps.FLAG) == "0", "Anhalten wirkt sofort, auch mitten im Warten")
rs_c = ly.LyricCache(os.path.join(tmp_c, "r.db"), opener=op_lib)
rs_c.meta("bulk_on", "1")
rs = ly.LyricBulk(rs_c, lambda: [["Interpret 3 - Lied", 203.0]])
rs.GAP_S = 0.0
rs.resume()
rs.thread.join(5)
check(rs_c.lookup("Interpret 3 - Lied", 203.0) is not None, "nach einem Neustart des Dienstes geht es weiter")
wn = ly.LyricBulk(ly.LyricCache(os.path.join(tmp_c, "w.db"), opener=down), lambda: [["Interpret 4 - Lied", 204.0]])
wn.GAP_S = 0.0
wn.start()
time.sleep(0.3)
check("LRCLIB" in wn.status()["error"] and wn.cache.lookup("Interpret 4 - Lied", 204.0) is None, "kein Netz: Meldung, das Lied bleibt offen und wartet")
wn.stop()
wn.thread.join(2)
fs = ly.LyricBulk(ly.LyricCache(os.path.join(tmp_c, "fs.db"), opener=op_lib), lambda: [["Interpret 5 - Lied", 205.0]])
fs.MIN_FREE = 1 << 62
fs.GAP_S = 0.0
fs.start()
fs.thread.join(3)
check("Platz" in fs.status()["error"] and fs.cache.meta(fs.FLAG) == "0", "zu wenig Platz auf der SD-Karte: es haelt an")
mem = ly.LyricCache(os.path.join(tmp_c, "mem.db"), opener=op_lib)
one = ly.LyricBulk(mem, lambda: [["Interpret 2 - Lied", 202.0], ["Interpret 3 - Lied", 203.0]])
check(len(one._lib()) == 2, "Bibliothek wird gemerkt")
two = ly.LyricBulk(ly.LyricCache(os.path.join(tmp_c, "mem.db"), opener=op_lib), lambda: [])
check(len(two._lib()) == 2 and two.status()["total"] == 2, "nach einem Neustart auch ohne Mac bekannt")
empty = ly.LyricBulk(ly.LyricCache(os.path.join(tmp_c, "em.db")), lambda: [])
empty.GAP_S = 0.0
empty.start()
time.sleep(0.1)
check(empty.status()["running"], "Bibliothek noch nicht da: wartet darauf")
empty.stop()
empty.thread.join(6)
# Fehlerbericht von Markus 06.11.2026: "8.799 von 9.565 gesucht", Starten bricht sofort ab, Balken nie voll.
# Die gemerkte Liste war die alte, laengere (Lieder inzwischen geloescht), gezaehlt wurden Eintraege statt Lieder.
fb = ly.LyricCache(os.path.join(tmp_c, "fb.db"), opener=op_lib)
fb.meta("lib", json.dumps([["Alt - Geloescht", 100.0], ["A - Eins", 200.0], ["A - Zwei", 210.0], ["A - Drei", 220.0]]))
fb.store("A - Eins", 200.0, [[1.0, "x"]])
fb.store("A - Zwei", 211.0, [])                                   # Laenge um 1 s anders, nur Text oder nichts gefunden
fb.store("A - Drei", 220.0, [[1.0, "y"]])
fb.store("Ganz - Woanders", 99.0, [])                              # Eintrag ohne Lied in der Bibliothek
NOW = [["A - Eins", 200.0], ["A - Zwei", 210.0], ["A - Drei", 220.0], ["A - Drei", 220.0]]   # zweimal dasselbe Lied
fbl = ly.LyricBulk(fb, lambda: NOW)
st_fb = fbl.status()
check(st_fb["total"] == 3 and st_fb["seen"] == 3 and st_fb["found"] == 2 and st_fb["done"], "Zaehlung nach Liedern der aktuellen Bibliothek: alle gesucht, 2 mit Liedtext: %s" % st_fb)
check(len(fbl._lib()) == 4 and json.loads(fb.meta("lib"))[0][0] == "A - Eins", "aktuelle Bibliothek gilt und wird gemerkt, auch wenn sie kuerzer ist")
fbl.GAP_S = 0.0
fbl.start()
fbl.thread.join(5)
check(not fbl.status()["running"] and fbl.status()["done"] and fb.meta(fbl.FLAG) == "0", "Starten: nichts offen, gleich fertig")
pg = open(os.path.join(PI, "webpanel.py"), encoding="utf-8").read()
check("mit Liedtext" in pg and "Math.floor(s.seen*1000/s.total)/10" in pg and "Erledigt." in pg and "if(s.done&&!s.running){k.remove();return}" in pg,
      "Seite Statistik: 'mit Liedtext', fertig = 100 % erledigt ohne Knopf (neue Lieder: Knopf kommt wieder)")
lb_cache2 = ly.LyricCache(os.path.join(tmp_c, "s.db"))
big = [[float(i), "Eine Zeile Text die sich wiederholt"] for i in range(80)]
lb_cache2.store("A - B", 200.0, big)
check(lb_cache2.lookup("A - B", 200.0) == big and os.path.getsize(os.path.join(tmp_c, "s.db")) < 30000, "kompakt gespeichert")

rig_p, sh_p = build()
m_p = ShowManager(sh_p, tempfile.mkdtemp(prefix="s2l_lyp_"))
check(sh_p.cfg["lyrics_auto"] == 0.0, "AUTO: Schalter steht auf aus")
sh_p.lyric_cache = ly.LyricCache(os.path.join(tmp_c, "g.db"), opener=op_c, sync=True)
calls.clear()
sh_p.mx = {"playing": True, "deck": 1, "title": TITLE, "dur": 211.49, "pos_f": 16.0, "t": 500.0, "rate": 1.0}
check(sh_p.lyric_line(500.0) == "" and not calls, "aus: nichts geht ins Internet, keine Zeile")
sh_p.cfg.set("lyrics_auto", 1.0)
check(sh_p.lyric_line(500.0) == "Zeile eins" and calls, "an: Zeile zum Lied aus Mixxx")
check(sh_p.lyric_line(509.0) == "Zeile zwei", "laeuft mit der Zeit des Decks mit")
sh_p.mx = dict(sh_p.mx, playing=False)
check(sh_p.lyric_line(505.0) == "", "Deck angehalten: keine Zeile")
sh_p.mx = None
check(sh_p.lyric_line(505.0) == "", "ohne Mixxx: keine Zeile")
d_p = tl.new_show("L")
d_p.update(bpm=120.0, duration=60.0, lyrics={"lines": [[1.0, "Aus der Show"]], "plain": "x"}, tracks=[])
e_p = m_p.engine
from _common import Clock  # noqa: E402
ck = Clock(sh_p)
e_p.load(d_p)
sh_p.cfg.set("lyrics_auto", 0.0)
e_p.play(ck.t, 2.0, True, None)
ck.run(0.1)
check(sh_p.lyric_line(ck.t) == "Aus der Show" and "lyric" in sh_p.snapshot(), "laufende Show: ihr Text, auch ohne Schalter, kommt im Status an")
e_p.stop(ck.t)
ck.run(0.1)
check(sh_p.snapshot()["lyric"] == "", "Show zu Ende: keine Zeile")
check(m_p.op({"op": "lyrics_bulk_status"})["running"] is False, "Stand fuer die Seite Statistik")
page = __import__("webpanel").make_page()
check("lyBulkCmd" in page and 'id="lybulk"' in page, "Statistik: Knopf und Fortschritt")
check("lyricToggle" in page and 'id="lyricbox"' in page and "innerHTML" not in page[page.index("function drawLyric"):page.index("async function loadStats")], "Text anzeigen: nur als Text, nie als HTML")

# ---- Musik ohne Mixxx: Stelle aus der Titelerkennung --------------------------------------------------------------------
from songrec_id import SECONDS, parse_result  # noqa: E402
sr = parse_result(json.dumps({"matches": [{"offset": 42.5, "timeskew": 0.0}], "track": {"title": "Titanium", "subtitle": "David Guetta"}}))
check(sr["offset"] == 42.5, "Antwort: Stelle im Lied wird gelesen")
check("offset" not in parse_result(json.dumps({"matches": [], "track": {"title": "T", "subtitle": "A"}})), "ohne Angabe: keine erfundene Stelle")
check("offset" not in parse_result(json.dumps({"matches": [{"offset": "x"}], "track": {"title": "T"}})), "Unsinn: keine Stelle")
rl, sl = build()
ml = ShowManager(sl, tempfile.mkdtemp(prefix="s2l_lyl_"))
sl.cfg.set("lyrics_auto", 1.0)


def op_live(req, timeout=0):
    calls.append(req)
    return Resp(json.dumps([rec("Titanium", 246.0)]).encode())


sl.lyric_cache = ly.LyricCache(os.path.join(tmp_c, "l.db"), opener=op_live, sync=True)
sl.state = "normal"
sl.titles = type("T", (), {"song": None})()
check(sl.lyric_status(100.0)["lyric_avail"] is False and sl.lyric_line(100.0) == "", "nichts erkannt: keine Zeile")
sl.titles.song = {"title": "Titanium", "artist": "David Guetta", "genre": "", "offset": 10.0, "pos_t": 100.0}
st_l = sl.lyric_status(106.0)
check(st_l["lyric"] == "Zeile eins" and st_l["lyric_i"] == 0 and st_l["lyric_tap"], f"Laenge unbekannt: Stelle aus Shazam plus vergangene Zeit, Zeile laeuft mit: {st_l}")
check(sl.lyric_line(115.0) == "Zeile zwei", "laeuft weiter")
sl.titles.song = {"title": "Titanium", "artist": "David Guetta", "genre": ""}
st_n = sl.lyric_status(106.0)
check(st_n["lyric"] == "" and st_n["lyric_avail"] and st_n["lyric_tap"], "ohne Stelle: keine laufende Zeile, aber Text zum Mitlesen")
check(sl.lyric_full(106.0)["lines"] == [[15.42, "Zeile eins"], [24.8, "Zeile zwei"]], "ganzer Text fuers Aufklappen")
check(ml.op({"op": "lyric_sync", "i": 1})["ok"] and sl.lyric_tap[1] == 24.8, "Antippen setzt die Stelle")
now_t = sl.lyric_tap[2]
check(sl.lyric_line(now_t + 1.0) == "Zeile zwei", "ab der angetippten Zeile rechnet der Pi weiter")
sl.titles.song = {"title": "Titanium", "artist": "David Guetta", "genre": "", "offset": 10.0, "pos_t": 100.0}
check(sl.lyric_line(now_t + 1.0) == "Zeile zwei", "Angetippt geht vor: eine neue Erkennung springt nicht zurueck")
sl.titles.song = {"title": "Anders", "artist": "Jemand", "genre": "", "offset": 16.0, "pos_t": 100.0}
sl.lyric_cache.store("Jemand - Anders", 0.0, [[16.0, "Neues Lied"]])
check(sl.lyric_line(100.5) == "Neues Lied", "neues Lied: die alte Korrektur gilt nicht mehr")
try:
    sl.titles.song = None
    sl.lyric_sync(1.0, 0)
    check(False, "ohne Lied kein Antippen")
except ValueError:
    check(True, "ohne Lied kein Antippen")
sl.titles.song = {"title": "Titanium", "artist": "David Guetta", "genre": "", "offset": 10.0, "pos_t": 100.0}
sl.state = "idle"
check(sl.lyric_line(106.0) == "", "Stille: keine Zeile")
sl.state = "normal"
sl.mx = {"playing": True, "deck": 1, "title": TITLE, "dur": 211.49, "pos_f": 16.0, "t": 500.0, "rate": 1.0}
check(sl.lyric_status(500.0)["lyric_tap"] is False, "Mixxx geht vor und kennt die Stelle selbst: kein Antippen")
sl.mx = None
sl.cfg.set("lyrics_auto", 0.0)
check(sl.lyric_status(106.0)["lyric_avail"] is False, "Schalter aus: nichts")
# ---- Text neu suchen -----------------------------------------------------------------------------------------------------
sl.cfg.set("lyrics_auto", 1.0)
sl.state = "normal"
sl.lyric_cache = rc = ly.LyricCache(os.path.join(tmp_c, "rf.db"), opener=lambda q, timeout=0: Resp(b"[]"), sync=True)
sl.titles.song = {"title": "Falsch", "artist": "Jemand", "genre": ""}
st_r = sl.lyric_status(100.0)
check(st_r["lyric_again"] and not st_r["lyric_avail"], "nichts gefunden: Knopf neu suchen ist trotzdem da")
wanted = []


def op_again(req, timeout=0):
    wanted.append(urllib.parse.unquote_plus(req.full_url))
    return Resp(json.dumps([rec("Richtig", 300.0, artist="Band")]).encode())


rc.opener = op_again
check(ml.op({"op": "lyric_refetch", "query": "Band - Richtig"})["ok"], "Knopf sucht neu")
check("Band Richtig" in wanted[0] and sl.lyric_status(100.0)["lyric_avail"], "mit dem eingegebenen Suchbegriff, gespeichert fuer das laufende Lied")
check(sl.lyric_status(100.0)["lyric_msg"].startswith("2 Zeilen"), "Meldung im Panel")
keep = sl.lyric_full(100.0)["lines"]
rc.opener = lambda q, timeout=0: Resp(b"[]")
ml.op({"op": "lyric_refetch", "query": "Gibt - Es nicht"})
check(sl.lyric_full(100.0)["lines"] == keep and "nichts gefunden" in sl.lyric_status(100.0)["lyric_msg"], "kein Treffer: der alte Text bleibt, mit Meldung")
rc.opener = down
ml.op({"op": "lyric_refetch"})
check(sl.lyric_full(100.0)["lines"] == keep and "nicht erreichbar" in sl.lyric_status(100.0)["lyric_msg"], "kein Netz: der alte Text bleibt")
rc.busy = True
try:
    ml.op({"op": "lyric_refetch"})
    check(False, "nur eine Suche zugleich")
except ValueError:
    check(True, "nur eine Suche zugleich")
rc.busy = False
rc.opener = op_again
sl.lyric_tap = ("Jemand - Falsch", 5.0, 1.0)
ml.op({"op": "lyric_refetch"})
check(sl.lyric_tap is None, "neu gesucht: die alte Korrektur per Antippen gilt nicht mehr")
sl.titles.song = None
try:
    ml.op({"op": "lyric_refetch"})
    check(False, "ohne Lied keine Suche")
except ValueError:
    check(True, "ohne Lied keine Suche")
check("lyricAgain" in page and 'id="lyricre"' in page, "Knopf im Fenster")
check("#lyricbox{flex:1 1 auto;min-height:120px" in page and "keinen Text" in page, "Fenster: Textbereich faellt nie zusammen, ohne Text ein Hinweis")
check('id="lyricpop"' in page and "#lyricrow{display:flex;align-items:center;gap:8px;height:24px" in page and "row.style.display" not in page, "Liedzeile: fester Platz, nichts rutscht, der ganze Text im Fenster")
sl.cfg.set("lyrics_auto", 0.0)
lc_p = ly.LyricCache(os.path.join(tmp_c, "p.db"), opener=lambda q, timeout=0: Resp(json.dumps([rec("Titanium", 246.0, synced=False)]).encode()), sync=True)
e_p2 = lc_p.get_entry("David Guetta - Titanium", 0.0, 1.0)
check(e_p2["lines"] == [] and "Zeile eins" in e_p2["plain"], "nur Text bekannt: bleibt zum Mitlesen gemerkt")
check(SECONDS >= 1, "Ausschnitt hat eine Laenge")
check('id="lyricline"' in page and "S.lyric" in page and ".textContent=t?" in page, "Hauptpanel: eigene Zeile, nur als Text, nie als HTML")
finish("test_liedtext")
