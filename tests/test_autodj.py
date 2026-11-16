"""Auto-DJ (Wunsch von Markus, 07.11.2026): Playlist nach Genre, Zielgruppe, Thema, leicht beginnend und immer staerker
(Energie, BPM), Tonarten passend; optional mit Claude; Auflegen im Browser mit Ueberblendung, taktsynchron. Aufs Licht wirkt nichts."""
import io
import json
import os
import re
import random
import subprocess
import tempfile

from _common import PI, ROOT, build, check, finish

from mixxx_link import MixxxLink
from showman import autodj as aj
from showman import assistant
from showman.api import ShowManager

# ---- Tonart und Tempo -------------------------------------------------------------------------------------------
check(aj.camelot(1) == (8, "B") and aj.camelot(13) == (5, "A") and aj.camelot(22) == (8, "A") and aj.camelot(0) is None, "Camelot wie in der Musik-Datenbank (C = 8B, Cm = 5A, Am = 8A)")
check(aj.key_dist(1, 1) == 0 and aj.key_dist(1, 22) == 1 and aj.key_dist(1, 8) == 1 and aj.key_dist(1, 3) == 2 and aj.key_dist(1, 7) == 3,
      "Tonart: gleich 0, Dur/Moll gleicher Zahl und +-1 sind Nachbarn, +-2 geht, weiter passt nicht")
check(aj.key_dist(0, 5) == 1.5, "ohne Tonart neutral")
check(aj.tempo_rate(128, 125) == (1.024, True) and aj.tempo_rate(128, 64) == (1.0, True) and aj.tempo_rate(128, 100) == (1.0, False),
      "Tempo: bis 6 % angleichen, halbes Tempo passt, weiter weg nur ueberblenden")
check(aj.dance_bpm(64) == 128 and aj.dance_bpm(180) == 90 and aj.dance_bpm(0) == 0, "Tanztempo: halbes und doppeltes Tempo gleich gezaehlt")

# ---- Sammlung zum Probieren ---------------------------------------------------------------------------------------
rng = random.Random(4)
GEN = ["Pop", "Rock", "Schlager", "House", "Latin"]
lib = []
for i in range(400):
    e = rng.randint(1, 9)
    lib.append({"title": f"Band{i % 60} - Lied {i}", "artist": f"Band{i % 60}", "name": f"Lied {i}", "dur": rng.uniform(150, 330),
                "bpm": round(85 + e * 6 + rng.uniform(-8, 8), 1), "kid": rng.randint(1, 24), "genre": GEN[i % 5], "lvl": e, "est": 0, "elv": e,
                "path": f"/m/{i}.mp3", "bad": 0})
lib += [{"title": "Kurz", "artist": "X", "name": "Kurz", "dur": 20, "bpm": 120, "kid": 1, "genre": "Pop", "lvl": 5, "path": "/m/k.mp3"},
        {"title": "Kaputt", "artist": "X", "name": "Kaputt", "dur": 200, "bpm": 120, "kid": 1, "genre": "Pop", "lvl": 5, "path": "/m/b.mp3", "bad": 1},
        {"title": "Ohne Datei", "artist": "X", "name": "Ohne", "dur": 200, "bpm": 120, "kid": 1, "genre": "Pop", "lvl": 5, "path": ""},
        {"title": "Wham! - Last Christmas", "artist": "Wham!", "name": "Last Christmas", "dur": 260, "bpm": 107, "kid": 1, "genre": "Pop", "lvl": 5, "path": "/m/x.mp3"},
        {"title": "Band1 - Lied 1", "artist": "Band1", "name": "Lied 1", "dur": 250, "bpm": 100, "kid": 1, "genre": "Rock", "lvl": 5, "path": "/m/dopp.mp3"}]
c = aj.candidates(lib, "", 1, 9)
paths = {t["path"] for t in c}
check(not paths & {"/m/k.mp3", "/m/b.mp3", "", "/m/x.mp3", "/m/dopp.mp3"}, "Auswahl: keine Samples, nichts Unlesbares, nichts ohne Datei, kein Weihnachtslied, Doppelte nur einmal")
check("/m/x.mp3" in {t["path"] for t in aj.candidates(lib, "", 1, 9, xmas=True)} and aj.wants_xmas({"theme": "Weihnachtsfeier"}), "Weihnachtslieder, wenn das Thema danach ist")
check(all(t["genre"] in ("Pop", "Rock") for t in aj.candidates(lib, "pop, rock", 1, 9)), "Genre-Filter mit Komma, ohne Gross/klein")
check(all(3 <= t["lvl"] <= 6 for t in aj.candidates(lib, "", 4, 6)), "Energie im Bereich (eine Stufe darunter darf zum Einstieg)")
# 08.11.2026: Plattenkisten und Wiedergabelisten aus Mixxx als Quelle (gewaehltes zaehlt zusammen)
kl_lib = [dict(lib[0], crates=["Austropop"], genre="Pop"), dict(lib[1], crates=["Party", "Austropop"], genre="Rock"),
          dict(lib[2], lists=["WEIHNACHTEN"], genre="Schlager"), dict(lib[3], genre="House"),
          {"title": "Wham! - Last Christmas", "artist": "Wham!", "name": "Last Christmas", "dur": 260, "bpm": 107, "kid": 1, "genre": "Pop", "lvl": 5,
           "path": "/m/xk.mp3", "lists": ["WEIHNACHTEN"]}]
kp = lambda **kw: {t["path"] for t in aj.candidates(kl_lib, kw.get("g", ""), 1, 9, crates=kw.get("c", ""))}  # noqa: E731
check(kp(c="K:austropop") == {lib[0]["path"], lib[1]["path"]}, "Kiste: nur deren Lieder, Gross/klein egal")
check(kp(c="L:WEIHNACHTEN") == {lib[2]["path"], "/m/xk.mp3"}, "Liste WEIHNACHTEN: ihre Lieder, Weihnachtslieder dann erlaubt")
check(kp(c="K:Party", g="house") == {lib[1]["path"], lib[3]["path"]}, "Kiste und Genre: eines davon genuegt")
check(kp(c="L:Austropop") == set(), "Kiste und Liste sind getrennt (L: findet keine Kiste)")
check(aj._crates("K:Pop|L:Weihnachten| x |K:") == {("K", "pop"), ("L", "weihnachten")}, "Auswahl lesen")
check(aj.wants_xmas({"crates": "L:WEIHNACHTEN"}), "Liste WEIHNACHTEN gilt als Weihnachtswunsch")
_rq = aj.claude_request(kl_lib[:2], {"crates": "K:Austropop|L:WEIHNACHTEN"}, "m")
# 08.11.2026: Erscheinungsjahr von-bis
y_lib = [dict(lib[0], year=1985), dict(lib[1], year=1999), dict(lib[2], year=0), dict(lib[3], year=2010)]
yp = lambda lo, hi: {t["path"] for t in aj.candidates(y_lib, "", 1, 9, y_lo=lo, y_hi=hi)}  # noqa: E731
check(yp(1980, 1999) == {lib[0]["path"], lib[1]["path"]}, "Jahr von-bis, Lieder ohne Jahr zaehlen dann nicht")
check(yp(2000, 0) == {lib[3]["path"]} and yp(0, 0) == {x["path"] for x in y_lib}, "nur ab, und ohne Bereich alle")
_pl = aj.plan(y_lib * 1, {"y_lo": 1990, "y_hi": 2020, "minutes": 10})
check(all(1990 <= x.get("year", 0) <= 2020 for x in y_lib if x["path"] in {i["path"] for i in _pl["items"]}), "Playlist haelt den Jahresbereich")
_rq2 = aj.claude_request(y_lib[:1], {"y_lo": 1980, "y_hi": 1989}, "m")
check('"jahr_von_bis": [1980' in _rq2["messages"][0]["content"].replace(".0", "") and "|1985" in _rq2["messages"][0]["content"], "Claude bekommt Jahr und Bereich")
_ah = open(os.path.join(PI, "static", "sm", "autodj.html"), encoding="utf-8").read()
_aj = open(os.path.join(PI, "static", "sm", "autodj.js"), encoding="utf-8").read()
check('id="wylo"' in _ah and "y_lo: +$('wylo').value" in _aj, "Seite: Jahr von-bis")
check('id="kchips"' in _ah and 'id="wcrate"' in _ah and "crates: $('wcrate').value" in _aj, "Seite: Kisten und Listen antippen")
check('"crates"' in open(os.path.join(PI, "showman", "autodj.py"), encoding="utf-8").read().split("class Saved")[1], "gemerkte Playlist behaelt die Auswahl")
check('"crates": [[k + ":" + n' in open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read(), "autodj_info liefert Kisten und Listen")
check("Kiste austropop" in _rq["messages"][0]["content"] and "Liste weihnachten" in _rq["messages"][0]["content"], "Claude erfaehrt die gewaehlten Kisten und Listen")

# ---- Playlist nach Regeln ----------------------------------------------------------------------------------------
r = aj.plan(lib, {"minutes": 90, "e_lo": 3, "e_hi": 8}, seed=1)
its = r["items"]
dur = sum(x["dur"] for x in its) - aj.MIX_S * (len(its) - 1)
check(85 * 60 <= dur <= 90 * 60 + 400 and r["dur"] == round(dur), "Laenge wie gewuenscht: %d min" % (dur // 60))
third = len(its) // 3
e1, e3 = sum(x["e"] for x in its[:third]) / third, sum(x["e"] for x in its[-third:]) / third
b1, b3 = sum(aj.dance_bpm(x["bpm"]) for x in its[:third]) / third, sum(aj.dance_bpm(x["bpm"]) for x in its[-third:]) / third
check(e3 - e1 >= 2.5, "leicht beginnend, immer staerker: Energie %.1f -> %.1f" % (e1, e3))
check(b3 > b1 + 5, "BPM steigt mit: %.0f -> %.0f" % (b1, b3))
check(its[0]["e"] <= 4, "Einstieg ruhig (E%d)" % its[0]["e"])
drops = sum(1 for a, b in zip(its, its[1:]) if b["e"] < a["e"] - 1)
check(drops == 0, "nie deutlich schwaecher als das Lied davor")
bad_keys = sum(1 for t in r["trans"] if t["key"] >= 3)
check(bad_keys <= len(r["trans"]) // 5, "Tonarten passen meistens (%d von %d nicht)" % (bad_keys, len(r["trans"])))
sync = sum(1 for t in r["trans"] if t["sync"])
check(sync >= len(r["trans"]) * 0.7, "die meisten Uebergaenge taktgenau moeglich (%d von %d)" % (sync, len(r["trans"])))
arts = [x["artist"] for x in its]
check(all(arts[i] not in arts[i + 1:i + aj.ARTIST_GAP] for i in range(len(arts))), "derselbe Interpret nicht kurz hintereinander")
check(len({x["path"] for x in its}) == len(its), "kein Lied doppelt")
check(aj.plan(lib, {"minutes": 90, "e_lo": 3, "e_hi": 8}, seed=1)["items"] == its, "gleiche Wuensche, gleicher Wurf: gleiche Playlist")
check([x["path"] for x in aj.plan(lib, {"minutes": 90, "e_lo": 3, "e_hi": 8}, seed=2)["items"]] != [x["path"] for x in its], "Neu wuerfeln: andere Playlist")
rb = aj.plan(lib, {"minutes": 60, "e_lo": 3, "e_hi": 8, "bpm_lo": 120, "bpm_hi": 140}, seed=1)
check(rb["bpm"] == [120, 140] and aj.dance_bpm(rb["items"][-1]["bpm"]) > 120, "BPM von bis von Hand")
ex = aj.plan(lib, {"minutes": 30, "exclude": [x["path"] for x in its[:5]]}, seed=1)
check(not {x["path"] for x in ex["items"]} & {x["path"] for x in its[:5]}, "Neuplanung waehrend des Spielens: Gespieltes kommt nicht wieder")
check(set(its[0]) >= {"path", "title", "artist", "dur", "bpm", "cam", "e", "genre"}, "Eintrag hat, was die Seite braucht")

# ---- Claude: ungepruefte Antwort -----------------------------------------------------------------------------------
pool = aj.candidates(lib, "", 3, 8)
body = aj.claude_request(pool, {"theme": "Geburtstag", "audience": "50+", "minutes": 60}, assistant.MODEL)
user = json.loads(body["messages"][0]["content"])
check(body["output_config"]["format"]["type"] == "json_schema" and user["thema"] == "Geburtstag" and "/m/" not in body["messages"][0]["content"],
      "an Claude: Wuensche und Liedliste, keine Pfade vom Mac")
check(len(aj.claude_pool(pool * 10, 3, 8, limit=100)) == 100, "hoechstens so viele Lieder an Claude")
picks, why, note = aj.apply_claude(pool, {"note": "Erst ruhig.", "picks": [{"i": 3, "why": "Klassiker"}, {"i": 3, "why": "doppelt"}, {"i": -1, "why": ""},
                                                                         {"i": 99999, "why": ""}, {"i": True, "why": ""}, {"i": "5", "why": ""}, "Muell", {"i": 7, "why": "x" * 900}]})
check([p["path"] for p in picks] == [pool[3]["path"], pool[7]["path"]] and note == "Erst ruhig." and len(why[pool[7]["path"]]) == 200,
      "Claude-Antwort geprueft: nur gueltige Nummern, jedes Lied einmal, Texte gekuerzt")
try:
    aj.apply_claude(pool, ["kein", "objekt"])
    check(False, "falsche Antwort wird abgelehnt")
except ValueError:
    check(True, "falsche Antwort wird abgelehnt")
cp = pool[:12]
rc = aj.plan(lib, {"minutes": 60, "e_lo": 3, "e_hi": 8}, seed=1, claude_picks=cp, why={cp[0]["path"]: "passt"})
check({x["path"] for x in cp} <= {x["path"] for x in rc["items"]} and any(x["why"] == "passt" for x in rc["items"]), "Claudes Lieder bleiben drin, mit Begruendung")
check(sum(x["dur"] for x in rc["items"]) > 50 * 60, "zu wenige von Claude: mit Regeln aufgefuellt")

# ---- ShowManager: Befehle, Claude mit nachgebautem Server, gemerkte Playlists --------------------------------------
link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
tmp = tempfile.mkdtemp(prefix="s2l_adj_")
mgr = ShowManager(sh, tmp)
mgr.key_path = os.path.join(tmp, "schluessel.json")
mgr.spent_path = os.path.join(tmp, "kosten.json")
link.feed({"type": "lib", "i": 0, "n": 1, "t": [[t["title"], t["dur"], t["artist"], t["name"], t["bpm"], "", t["kid"], t["genre"], t["lvl"], "x.mp3", 0, 1, t["path"]]
                                                 for t in lib[:200]]}, 1.0)
info = mgr.op({"op": "autodj_info"})
check(info["n"] == 200 and not info["has_key"] and any(g[0] == "Pop" for g in info["genres"]), "Info: Lieder, Genres, Schluessel")
r1 = mgr.op({"op": "autodj_plan", "wish": {"minutes": 40, "e_lo": 3, "e_hi": 8}, "claude": True})
check(r1["items"] and not r1["claude"] and "Schluessel" in r1["note"], "ohne Schluessel: nach Regeln, mit Hinweis")


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


sent = []


def fake(req, timeout=0):
    sent.append(json.loads(req.data.decode()))
    lines = json.loads(sent[-1]["messages"][0]["content"])["lieder"].split("\n")
    ans = {"note": "Gartenfest, erst Oldies.", "picks": [{"i": int(x.split("|")[0]), "why": "passt"} for x in lines[:8]]}
    return Resp(json.dumps({"stop_reason": "end_turn", "usage": {"input_tokens": 1000, "output_tokens": 100},
                            "content": [{"type": "text", "text": json.dumps(ans)}]}).encode())


with open(mgr.key_path, "w") as f:
    json.dump({"key": "sk-ant-" + "x" * 30}, f)
mgr.claude_opener = fake
r2 = mgr.op({"op": "autodj_plan", "wish": {"minutes": 40, "e_lo": 3, "e_hi": 8, "theme": "Gartenfest"}, "claude": True})
check(r2["claude"] and r2["note"] == "Gartenfest, erst Oldies." and r2["cost_usd"] > 0 and sum(1 for x in r2["items"] if x["why"] == "passt") == 8,
      "mit Claude: Auswahl uebernommen, Kosten gezaehlt")
check(sent and sent[0]["model"] == assistant.MODEL, "Claude: Modell wie der Show-Assistent")


def refused(req, timeout=0):
    raise OSError("kein Netz")


mgr.claude_opener = refused
r3 = mgr.op({"op": "autodj_plan", "wish": {"minutes": 30}, "claude": True})
check(r3["items"] and not r3["claude"] and "nach Regeln" in r3["note"], "Claude nicht erreichbar: trotzdem eine Playlist nach Regeln")
s1 = mgr.op({"op": "autodj_save", "name": "Gartenfest", "items": r2["items"], "wish": {"theme": "Gartenfest"}, "note": "n"})
check(s1["saved"][0]["name"] == "Gartenfest" and s1["saved"][0]["n"] == len(r2["items"]), "Playlist merken")
ld = mgr.op({"op": "autodj_load", "name": "Gartenfest"})
check([x["path"] for x in ld["items"]] == [x["path"] for x in r2["items"]] and ld["wish"]["theme"] == "Gartenfest", "Playlist laden")
check(os.path.isfile(os.path.join(tmp, "_autodj.json")) and all(x["name"] != "_autodj.json" for x in mgr.store.list()), "gemerkt in shows/_autodj.json, zaehlt nicht als Show")
check(mgr.op({"op": "autodj_delete", "name": "Gartenfest"})["saved"] == [], "Playlist loeschen")
for bad in ({"op": "autodj_save", "name": " ", "items": []}, {"op": "autodj_load", "name": "gibts nicht"}, {"op": "autodj_quatsch"}):
    try:
        mgr.op(bad)
        check(False, "Fehler erkannt: %s" % bad["op"])
    except ValueError:
        check(True, "Fehler erkannt: %s" % bad["op"])

# ---- Seite, Kopfleiste, Knopf in der Musik-Datenbank ---------------------------------------------------------------
SM = os.path.join(PI, "static", "sm")
html = open(os.path.join(SM, "autodj.html"), encoding="utf-8").read()
js = open(os.path.join(SM, "autodj.js"), encoding="utf-8").read()
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
check('if path == "/musik/autodj":' in api and 'class="s2lnav" data-back="/musik" data-cur="autodj" data-title="h_autodj"' in html, "Seite /musik/autodj mit Kopfleiste (eigener Menuepunkt)")
import webpanel  # noqa: E402
page = webpanel.make_page()
check('<a id="djbtn" href="/musik/autodj"' in page and page.find('id="hlbtn"') < page.find('id="djbtn"') < page.find('id="dbbtn"'),
      "runder CD-Knopf im Hauptpanel direkt neben dem Herz (Wunsch von Markus 07.11.2026)")
dj = page[page.find('<a id="djbtn"'):page.find('</a>', page.find('<a id="djbtn"'))]
check("target=" not in dj, "Auto-DJ im selben Tab")
check("#djbtn{" in page.replace("#smbtn,#rmbtn,#dbbtn,#djbtn{", "#djbtn{") and "border-radius:50%" in page, "rund wie die anderen Knoepfe")
check('href="/musik/autodj"' not in open(os.path.join(SM, "music.html"), encoding="utf-8").read(), "kein Auto-DJ-Knopf mehr in der Musik-Datenbank")
check(subprocess.run(["node", "--check", os.path.join(SM, "autodj.js")], capture_output=True).returncode == 0, "autodj.js: node --check")
check(all(x not in js for x in ("confirm(", "prompt(", "alert(")), "eigene Rueckfrage statt Browser-Dialog")
check("crossOrigin = 'anonymous'" in js and "preservesPitch = true" in js and "/audio?p=" in js and "/marks?p=" in js, "Abspielen vom Mac ueber WebAudio, Tempo ohne Tonhoehe")
check("/api/sm/cmd" in js and "ws" not in js.split("/api/sm/cmd")[0][-20:] and "light" not in js.lower().replace("light-butler", ""), "Seite steuert kein Licht direkt")
check(js.count("autodj_feed") == 1, "ans Licht nur ueber autodj_feed (Musikdaten wie Mixxx, 08.11.2026)")

# Rechnungen im Browser (ADJ) mit node
probe = r"""
global.window = {}; global.document = { getElementById: () => null };
require(process.argv[1]);
const A = window.ADJ, out = {};
out.rate = A.rateFor(128, 125, 0.06); out.half = A.rateFor(128, 64, 0.06); out.far = A.rateFor(128, 100, 0.06); out.off = A.rateFor(128, 125, 0);
const m = A.mixPoint({ bpm: 120, fb: 0.25, end: 200 }, 16, 10, true); out.mix = m;
out.late = A.mixPoint({ bpm: 120, fb: 0.25, end: 200 }, 16, 190, true);
out.nosync = A.mixPoint({ bpm: 0, fb: null, end: 200 }, 16, 10, false);
out.err = A.phaseErr(10.0, 0.0, 120, 5.1, 0.0, 120); out.err2 = A.phaseErr(10.0, 0.0, 120, 4.9, 0.0, 120);
out.nudge = [A.nudge(1.02, 0.2, 120), A.nudge(1.02, -0.2, 120), A.nudge(1.02, 0.01, 120), A.nudge(1.0, 5, 120)];
out.mult = [A.beatMult(128, 64), A.beatMult(64, 128), A.beatMult(128, 126)];
out.g = [A.gains(0), A.gains(0.5), A.gains(1)];
const f = new Float32Array(3000); for (let t = 0.37; t < 30; t += 0.5) f[Math.round(t * 100)] = 1; out.fb = A.phaseFromFlux(f, 100, 120);
out.end = A.musicEnd([50, 80, 90, 80, 5, 2], 60); out.start = A.musicStart([1, 2, 60, 80, 90, 80], 60);
out.pick = [A.pickTrans('auto', {genre: 'House'}, {genre: 'EDM'}, true), A.pickTrans('auto', {genre: 'Pop'}, {genre: 'House'}, true),
            A.pickTrans('auto', {genre: 'House'}, {genre: 'EDM'}, false), A.pickTrans('brake', {}, {}, true)];
out.tf = [A.transGains('filter', 0), A.transGains('filter', 0.8), A.transGains('echo', 0.1), A.transGains('echo', 0.5), A.transGains('soft', 0.5)];
out.bk = [A.brake(0), A.brake(0.5), A.brake(0.9), A.brake(1)];
console.log(JSON.stringify(out));
"""
pr = subprocess.run(["node", "-e", probe, os.path.join(SM, "autodj.js")], capture_output=True, text=True)
o = json.loads(pr.stdout or "{}") if pr.returncode == 0 else {}
check(o.get("rate", {}).get("sync") and abs(o["rate"]["rate"] - 1.024) < 1e-6 and o["half"] == {"rate": 1, "sync": True} and not o["far"]["sync"] and not o["off"]["sync"],
      "Browser: Tempo angleichen wie am Pi" + (" " + pr.stderr[:300] if pr.returncode else ""))
mx = o.get("mix", {})
check(mx.get("bars") == 16 and abs(((mx["t"] - 0.25) / 2.0) - round((mx["t"] - 0.25) / 2.0)) < 1e-9 and mx["t"] + mx["len"] <= 200 and mx["len"] == 32,
      "Ueberblendung beginnt auf einem Takt, 16 Takte vor dem Ende der Musik: %s" % mx)
check(o.get("late", {}).get("bars", 0) <= 4 and o["late"]["t"] >= 191, "spaet dran: kuerzer, auf dem naechsten Takt")
check(o.get("nosync", {}).get("bars") == 0 and o["nosync"]["len"] == 12, "ohne Raster: einfache Ueberblendung von 12 s")
check(abs(o.get("err", 0) - 0.2) < 1e-9 and abs(o.get("err2", 0) + 0.2) < 1e-9, "Phasenfehler in Beats, vor und nach")
n = o.get("nudge", [0, 0, 0, 0])
check(n[0] < 1.02 < n[1] and n[2] == 1.02 and abs(n[3] - 0.97) < 1e-9, "Nachregeln: B voraus = langsamer, kleine Fehler ruhen, hoechstens 3 %")
check(o.get("mult") == [2, 0.5, 1], "halbes/doppeltes Tempo: Beats von A zaehlen")
g = o.get("g", [[0, 0], [0, 0], [0, 0]])
check(g[0] == [1, 0] and abs(g[1][0] ** 2 + g[1][1] ** 2 - 1) < 1e-9 and abs(g[2][1] - 1) < 1e-9, "Ueberblenden mit gleicher Leistung")
check(abs(o.get("fb", 0) - 0.37) < 0.02, "erster Beat ohne Analyse aus den Bass-Einsaetzen: %.3f" % o.get("fb", 0))
# Uebergangs-Effekte (Wunsch 07.11.2026)
check(o.get("pick") == ["filter", "soft", "echo", "brake"], f"passend: Filter bei elektronischer Musik, sonst weich, Echo ohne passendes Tempo; eigene Wahl gilt ({o.get('pick')})")
tf = o.get("tf", [{}] * 5)
check(abs(tf[0]["hp"] - 20) < 1e-6 and tf[1]["hp"] >= 1499 and tf[0]["a"] == 1, "Filter: altes Lied verliert die Baesse bis 1,5 kHz")
check(tf[2]["send"] == 1 and tf[2]["a"] > 0.5 and tf[3]["send"] == 0 and tf[3]["a"] == 0 and tf[3]["b"] > 0.7, "Echo: altes Lied ins Echo, trocken schnell weg, neues blendet ein")
check(tf[4]["send"] == 0 and tf[4]["hp"] == 20 and abs(tf[4]["a"] ** 2 + tf[4]["b"] ** 2 - 1) < 1e-9, "weich: wie bisher")
bk = o.get("bk", [{}] * 4)
check(bk[0] == {"rate": 1, "a": 1, "b": 0} and 0.7 < bk[1]["rate"] < 0.8 and bk[2]["b"] == 1 and bk[3]["a"] == 0 and bk[3]["rate"] <= 0.06,
      "Bremse: Tempo faellt, neues Lied setzt am Ende hart ein")
_hh = open(os.path.join(SM, "autodj.html"), encoding="utf-8").read()
_jj = open(os.path.join(SM, "autodj.js"), encoding="utf-8").read()
check('id="otrans"' in _hh and '<option value="auto" selected>passend</option>' in _hh and _hh.count('class="pad"') == 4 and "/\\/(TEST)?SAMPLES\\//i" in _jj,
      "Mischpult: Auswahl Uebergang (Standard passend), vier Sample-Tasten aus dem Ordner SAMPLES")
check(abs(o.get("end", 0) - 40) < 1e-6 and abs(o.get("start", 0) - 18) < 1e-6, "Ende und Anfang der Musik aus der Lautstaerkekurve (Anfang hoechstens 30 %)")

# Mac: /marks liefert das Beat-Raster fuer den Auto-DJ
br = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check('out["bpm"], out["fb"] = round(float(res["bpm"]), 3), round(float(res["first_beat"]), 3)' in br, "Mac: Beat-Raster (bpm, erster Beat) in /marks")
# Neues Aussehen (Wunsch 07.11.2026): Abend einrichten als Assistent (zuklappbar), Mischpult mit quadratischen Decks und Cover, Playlist
_h = open(os.path.join(ROOT, "pi", "static", "sm", "autodj.html"), encoding="utf-8").read()
_j = open(os.path.join(ROOT, "pi", "static", "sm", "autodj.js"), encoding="utf-8").read()
_ids = set(re.findall(r"\$\('([\w-]+)'\)", _j)) | set(re.findall(r"\$\('deck' \+ k\)", _j) and ["deck0", "deck1"])
_missing = sorted(i for i in _ids if 'id="%s"' % i not in _h)
check(not _missing, f"jedes Element, das das Skript anspricht, gibt es auf der Seite ({_missing})")
check(_h.index('id="wiz"') < _h.index('id="playbox"') < _h.index('id="listbox"'), "Reihenfolge: Abend einrichten, Mischpult, Playlist")
check('<details class="box" id="wiz">' in _h and _h.count('class="step') >= 5 and "$('wiz').open = false;" in _j, "Assistent in fuenf Schritten, klappt nach dem Vorschlag zu")
check(".deck { aspect-ratio: 1;" in _h and "el.style.backgroundImage = 'url(\"' + img.src + '\")'" in _j and "deckColor(it && it.e)" in _j,
      "Decks quadratisch, Cover als Hintergrund, ohne Cover Farbe nach Energie")
check("Lied ' + (cur + 1) + ' von ' + items.length" in _j and "als Nächstes" in _j, "Position im Event und naechstes Lied markiert")
# Wunsch 07.11.2026, zweite Runde: zwei Spalten, Genres als Knoepfe, Standards, Event, Beginn mit Uhrzeiten und Zeitachse
check("#cols .box { width: auto; max-height: none; overflow: visible; }" in _h and "max-width: none; margin: 0;" in _h, "ganze Breite: Felder fuellen die Spalten (nicht 560 px wie Fenster)")
check('<div id="cols"><div id="colL">' in _h and "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)" in _h and "@media (max-width: 979px) { #cols { grid-template-columns: 1fr; }" in _h,
      "zwei Spalten (Laptop, Tablet quer), schmaler untereinander")
_css = _h[_h.index("<style>"):_h.index("</style>")]
check(_css.count("/*") == _css.count("*/"), "alle Kommentare in den Stilen geschlossen (sonst verschluckt einer die Regeln fuers Handy)")
check('id="gchips"' in _h and 'type="hidden" id="wgen"' in _h and "$('gchips').onclick" in _j, "Genres einzeln antippen")
check('<option value="4" selected>4 Takte</option>' in _h and 'id="obass" checked' in _h, "Standard: 4 Takte, Baesse tauschen")
check("Event einrichten" in _h and "Abend einrichten" not in _h and 'id="wmin" class="num" min="10" max="360" step="10" value="240"' in _h, "Event statt Abend, Laenge 4 Stunden")
check('type="time" id="wstart"' in _h and "function startTimes()" in _j and "function drawAxis(T)" in _j and 'class="clk"' in _j, "Beginn, Uhrzeit je Lied, Zeitachse")
import showman.autodj as _ad  # noqa: E402
_src = open(_ad.__file__, encoding="utf-8").read()
check('"bpm_lo", "bpm_hi", "y_lo", "y_hi", "start")' in _src, "gemerkte Playlist behaelt den Beginn")
# Playlists umbenennen und loeschen (Wunsch 08.11.2026): die Seite laedt, merkt unter neuem Namen und loescht den alten
import tempfile as _tf2  # noqa: E402
_sv = _ad.Saved(os.path.join(_tf2.mkdtemp(), "_autodj.json"))
_it = [{"path": "/m/a.mp3", "title": "A - Eins", "artist": "A", "dur": 200.0, "bpm": 120.0}]
_sv.save("Party alt", {"items": _it, "wish": {"theme": "Party", "start": "21:00"}, "note": "x"}, 1.0)
_d = _sv.get("Party alt")
_sv.save("Party neu", {"items": _d["items"], "wish": _d["wish"], "note": _d["note"]}, 2.0)
_sv.delete("Party alt")
_names = [x["name"] for x in _sv.list()]
check(_names == ["Party neu"] and _sv.get("Party neu")["wish"]["start"] == "21:00" and len(_sv.get("Party neu")["items"]) == 1,
      "umbenennen: Lieder, Wuensche und Beginn bleiben, der alte Name ist weg")
check('id="bren"' in _h and "cmd('autodj_load', { name: old })" in _j and "cmd('autodj_delete', { name: old })" in _j, "Seite: Knopf Umbenennen")
check("pa.a.currentTime = 0;" in _j and "function drawPadGlow()" in _j and 'id="padstop"' in _h and "if (!pa.a.paused) { pa.a.pause(); return; }" not in _j,
      "Sample-Tasten: jeder Druck von vorne, leuchten nur beim Spielen, Stopp fuer alle")
check("const shift" not in _j and 'id="nowl"' in _j, "Zeitskala fest ab dem Beginn, eigener Strich fuer die echte Uhrzeit")
# 08.11.2026: Musik leiser beim Sample; Playlist und Stelle ueberleben einen Seitenwechsel
_j2 = open(os.path.join(PI, "static", "sm", "autodj.js"), encoding="utf-8").read()
_h2 = open(os.path.join(PI, "static", "sm", "autodj.html"), encoding="utf-8").read()
check('id="pduck"' in _h2 and "d.gain.connect(musicBus)" in _j2 and "duck(true)" in _j2 and "if (!padAudio.some(" in _j2,
      "Sample: Musik ueber eigenen Bus leiser, danach wieder laut")
check("const RUN_KEY = 'autodj_lauf'" in _j2 and "addEventListener('beforeunload'" in _j2 and "playFrom(r.i, r.pos)" in _j2,
      "Seitenwechsel: Playlist und Stelle gemerkt, Rueckfrage beim Verlassen, weiter an der Stelle")
# 08.11.2026: "Als Naechstes spielen" aus der Musik-Datenbank (BroadcastChannel, sonst Warteliste)
_j3 = open(os.path.join(PI, "static", "sm", "autodj.js"), encoding="utf-8").read()
_m3 = open(os.path.join(PI, "static", "sm", "music.js"), encoding="utf-8").read()
check("new BroadcastChannel('lb_autodj')" in _j3 and "type: 'alive'" in _j3 and "d.type === 'next'" in _j3 and "localStorage.getItem('autodj_next')" in _j3,
      "Auto-DJ nimmt Lieder aus der Musik-DB (offen: sofort, zu: beim Start)")
check('data-nx="' in _m3 and "Als Nächstes spielen" in _m3 and "adj.postMessage({ type: 'next', t })" in _m3 and "S2LNav.openAutoDJ()" in _m3,
      "Musik-DB: Knopf als Naechstes spielen, sonst Warteliste und Auto-DJ-Fenster")
check("function nextPos()" in _j3 and "items.splice(nextPos(), 0, trackItem(t" in _j3, "kommt direkt nach dem laufenden Lied")
_h3 = open(os.path.join(ROOT, "pi", "static", "sm", "autodj.html"), encoding="utf-8").read()
check('id="bclear"' in _h3 and "$('bclear').onclick" in _j3 and "items = [now]; cur = 0" in _j3 and "stopAll(); items = []" in _j3,
      "Knopf Leeren: das laufende Lied spielt zu Ende, sonst ganz leer (Wunsch 12.11.2026)")
finish("Auto-DJ")

