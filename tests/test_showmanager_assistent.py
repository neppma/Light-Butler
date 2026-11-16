"""Show-Assistent: Vorschlag aus Lied und Geraeten, als neue Kopie, nur ueber die normalen Wege der Engine. Claude ist Zusatz und ohne Netz nachgestellt."""
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error

from _common import DT, Clock, build, check, finish, ch

from dmx import Fixture
from mixxx_link import MixxxLink
from showman import assistant as a
from showman import timeline as tl
from showman.api import ShowManager

tmp = tempfile.mkdtemp(prefix="s2l_assist_")
link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
mgr = ShowManager(sh, tmp)
mgr.key_path = os.path.join(tmp, "schluessel.json")

BPM, DUR = 120.0, 192.0
SE = [["intro", 0.0, 16.0], ["vers", 16.0, 48.0], ["main", 48.0, 96.0], ["break", 96.0, 112.0], ["main", 112.0, 176.0], ["outro", 176.0, 192.0]]
EV = [["build", 40.0, 48.0, 0.5, "l"], ["drop", 48.0, 48.0, 1.0, ""], ["gap", 110.0, 112.0, 0.5, ""], ["drop", 112.0, 112.0, 1.0, ""]]
MARKS = {"se": SE, "cu": [16.0, 48.0, 96.0, 112.0], "ev": EV, "en": [60] * 8 + [70] * 16 + [95] * 24 + [30] * 8 + [95] * 32 + [50] * 8, "lvl": 8, "genre": "House", "title": "Test - Lied", "fp": ""}


def make(name, marks=MARKS, peaks=None):
    d = mgr.store.create(name)
    d.update(bpm=BPM, duration=DUR)
    if marks:
        d["marks"] = marks
    mgr.store.save(name, d)
    if peaks:
        mgr.store.save_peaks(name, peaks)


# ---- Aufbau des Liedes --------------------------------------------------------------------------------------------
make("Lied")
doc = mgr.store.load("Lied")
check(doc["marks"]["genre"] == "House" and doc["marks"]["lvl"] == 8 and doc["marks"]["ev"][0][:3] == ["build", 40.0, 48.0], "Genre, Energie und Ereignisse bleiben in der Show")
song = a.song_info(doc)
check(song["source"] == "mixxx", "mit Analyse: Aufbau aus Mixxx")
segs = a.segments(song)
check(abs(segs[0]["t"]) < 1e-6 and abs(segs[-1]["t"] + segs[-1]["d"] - DUR) < 1e-6 and all(abs(x["t"] + x["d"] - y["t"]) < 0.01 for x, y in zip(segs, segs[1:])), "Stuecke decken das Lied ohne Luecke")
check(all(c in [round(s["t"], 3) for s in segs] for c in MARKS["cu"]), "jeder Cue beginnt ein neues Stueck")
kinds = {round(s["t"], 1): s["kind"] for s in segs}
check(kinds[0.0] == "intro" and kinds[48.0] == "drop" and kinds[110.0] == "gap", "Intro, Drop und Pause erkannt")

peaks = {"rate": 10, "min": [-10] * 480 + [-100] * 960 + [-10] * 480, "max": [10] * 480 + [100] * 960 + [10] * 480}
make("NurWelle", marks=None, peaks=peaks)
song2 = a.song_info(mgr.store.load("NurWelle"), peaks)
check(song2["source"] == "wave" and song2["secs"][0][0] == "intro" and any(s[0] == "main" for s in song2["secs"]), "ohne Mixxx: aus der Wellenform geschaetzt")
check(any(e[0] == "drop" for e in song2["ev"]), "geschaetzter Drop nach der leisen Stelle")
make("Nichts", marks=None)
check(a.song_info(mgr.store.load("Nichts"))["source"] == "raster", "ganz ohne Daten: im Takt")

# ---- Vorschlag ----------------------------------------------------------------------------------------------------
sh.cfg.set("sm_laser", 1.0)
ALL = {"laser": True, "fog": True, "strobe": True, "move": True, "seed": 3, "keep_copy": True}   # hier immer als Kopie (leere Show direkt: test_assistent_genre)
r = mgr.op({"op": "assist", "name": "Lied", **ALL})
check(r["show"] == "Lied (Vorschlag)" and r["source"] == "mixxx" and not r["claude"], "neue Kopie der Show")
check(mgr.store.load("Lied")["tracks"] == [], "die Show selbst bleibt unberuehrt")
new = mgr.store.load(r["show"])
check(new["bpm"] == BPM and new["marks"]["genre"] == "House", "Tempo und Analyse gehen mit")
check(tl.normalize(new)["tracks"] == new["tracks"], "Vorschlag ist eine gueltige Show")
check(mgr.op({"op": "assist", "name": r["show"], **ALL})["show"] == "Lied (Vorschlag 2)", "weiterer Vorschlag aus dem Vorschlag: neuer Name, keine Doppelung")


def tracks(doc, attr=None):
    return [t for t in doc["tracks"] if attr is None or t["attr"] == attr]


def clips(doc, attr):
    return [c for t in tracks(doc, attr) for c in t["clips"]]


check(len(tracks(new, "dimmer")) >= 5 and tracks(new, "color") and tracks(new, "move") and clips(new, "laser") and clips(new, "fog"), "Dimmer, Farbe, Bewegung, Laser und Nebel sind belegt")
ALLOWED = {"dimmer", "color", "move", "preset", "gobo", "laser", "fog"}
check({t["attr"] for t in new["tracks"]} <= ALLOWED, "nur erlaubte Spuren: keine Strobe-, Mode- oder Reset-Kanaele")
AMB = ("par", "theke", "couchtisch")
check(not [t for t in new["tracks"] if t["target"].get("fixture") in AMB], "Standard: Ambiente aus, alles andere ist finster")
with_amb = mgr.store.load(mgr.op({"op": "assist", "name": "Lied", **ALL, "ambient": True})["show"])
ambient = [t for t in with_amb["tracks"] if t["target"].get("fixture") in AMB]
check(ambient and all(c["pattern"] == "solid_color" for t in ambient for c in t["clips"]), "mit Hakerl: Ambiente steht ruhig und blinkt nie mit")
check(len(ambient[0]["clips"]) < 12, "Ambiente wechselt nur selten die Farbe")
wash = [c for t in new["tracks"] if t["attr"] == "dimmer" and t["target"].get("group") == "rig_wash" for c in t["clips"]]
check(wash and all(c["p"]["end"] <= 0.4 * 255 for c in wash), "Washes bleiben dezent, auch am Hoehepunkt hoechstens 40 %")
check(not any(t["attr"] == "dimmer" and t["target"].get("group") == "rig_wash" and c["pattern"] in ("blink", "strobe", "beat") for t in new["tracks"] for c in t["clips"]), "Wash: kein hartes Blinken (Dimmer zu traege)")
for fog in clips(new, "fog"):
    check(fog["d"] <= 10.0, "Nebel: Schub unter 10 s")
check(all(f["t"] >= 0 for f in clips(new, "fog")) and clips(new, "fog")[0]["t"] < 48.0, "Nebel kommt vor dem Drop")
ts = sorted(f["t"] for f in clips(new, "fog"))
check(all(b - x >= a.FOG_GAP_S - a.FOG_S for x, b in zip(ts, ts[1:])), "Nebel: Abstand zwischen den Schueben")
check(not [c for t in new["tracks"] for c in t["clips"] if c["t"] < 110.5 and c["t"] + c["d"] > 111.5 and t["attr"] == "dimmer"], "Pause in der Musik: Dimmer-Clips machen dunkel")

off = {"laser": False, "fog": False, "strobe": False, "move": False, "seed": 3}
small = mgr.store.load(mgr.op({"op": "assist", "name": "Lied", **off})["show"])
check(not clips(small, "laser") and not clips(small, "fog") and not tracks(small, "move"), "Schalter aus: kein Laser, kein Nebel, keine Bewegung")
check(not [c for c in clips(small, "dimmer") if c["pattern"] == "strobe"], "ohne Blitze: kein Strobe-Muster")
fast = [c["p"]["speed"] for c in clips(small, "dimmer") if c["pattern"] == "blink"]
check(all(v <= 1.0 for v in fast), "ohne Blitze: hoechstens ein Blinken je Beat")
check(sh.cfg["sm_fog"] < 0.5 and not sh.strobe, "der Assistent schaltet keine Erlaubnis ein")



def playing_at(d, sec):
    """Welche Geraete haben zu dieser Zeit einen Clip (ohne Ambiente und Effektband)?"""
    out = set()
    for t in d["tracks"]:
        who = t["target"].get("group") or t["target"].get("fixture")
        if who in ("par", "theke", "couchtisch", "effektband", "hazer") or t["attr"] not in ("dimmer", "laser"):
            continue
        if any(c["t"] <= sec < c["t"] + c["d"] for c in t["clips"]):
            out.add(who)
    return out


rng_t = [s * 0.5 for s in range(int(DUR * 2))]
drop_zone = [(48.0, 52.0), (112.0, 116.0)]
outside = [t for t in rng_t if not any(x <= t < y for x, y in drop_zone)]
check(all(len(playing_at(new, t)) <= 2 for t in outside), "ausserhalb der Drops hoechstens zwei Geraete, nie alle")
pairs = sum(1 for t in outside if len(playing_at(new, t)) == 2)
check(0 < pairs < len(outside) * 0.35, "meist einer allein, ab und zu ein passender Partner")
check(len(playing_at(new, 49.0)) >= 5 and len(playing_at(new, 113.0)) >= 5, "beim grossen Drop spielen alle zusammen")
check(not playing_at(new, 53.0) >= {"rig_bars", "rig_spot"}, "nach 2 Takten ist das Gewitter vorbei")
storm = [c for t in new["tracks"] if t["attr"] == "dimmer" for c in t["clips"] if abs(c["t"] - 48.0) < 0.01 and c["pattern"] in ("strobe", "blink")]
check(len(storm) >= 3 and len({(c["pattern"], c["p"].get("speed")) for c in storm}) >= 2, "Gewitter: mehrere Geraete, jedes im eigenen Takt")
plan_new = a.direct(song, "", 0.5, 3)
check(all(abs((s["t"] / 0.5) - round(s["t"] / 0.5)) < 0.01 for s in plan_new), "jeder Wechsel liegt auf einem Beat")
leads = [s["lead"] for s in plan_new if s["lead"]]
runs, cur = [], 1
for x, y in zip(leads, leads[1:]):
    if x == y:
        cur += 1
    else:
        runs.append((x, cur))
        cur = 1
check(all(n == 1 or (w in a.HOLD_ROLES and n <= a.HOLD_PIECES + 1) for w, n in runs), f"sonst nie zweimal dasselbe Geraet: {runs}")
check(any(n > 1 for _, n in runs), "ab und zu ein laengerer Bereich mit einem Geraet")
check({"spot", "nano", "band", "bars", "laser"} <= set(leads), "Vega, Nanoleaf, Effektband, Docooler und Laser kommen an die Reihe")
check("uv" not in leads, "UV allein waere zu dunkel: nicht in der Reihe")
main = [s for s in plan_new if s["kind"] == "main"]
check(main and all(3.0 <= s["d"] <= 8.5 for s in main[:-1]), "im Hauptteil ist ein Geraet ein paar Sekunden dran")
check(not [s for s in plan_new if s["level"] <= 0 and s["lead"] in ("bars", "laser", "fx")], "ruhige Stellen: nichts Hartes")
sw = [s for s in plan_new if s.get("swap")]
check(sw, "im Hauptteil schalten zwei Geraete auch hin und her")
parts_all = a.rig_parts(mgr.meta())
one = dict(sw[0], lead="spot", also="fx", level=2, kind="main")
trk = a.render([one], song, parts_all, ALL, 1)
xa = [c for t in trk if t["attr"] == "dimmer" and t["target"] == a._target(parts_all, one["lead"]) for c in t["clips"]]
xb = [c for t in trk if t["attr"] == "dimmer" and t["target"] == a._target(parts_all, one["also"]) for c in t["clips"]]
times = sorted([c["t"] for c in xa] + [c["t"] for c in xb])
check(xa and xb and all(abs(c["d"] - 0.5) < 0.01 or c["t"] + c["d"] >= one["t"] + one["d"] - 0.01 for c in xa + xb) and all(abs(y - x - 0.5) < 0.01 for x, y in zip(times, times[1:])), "Hin und her: je Beat genau ein Geraet, nahtlos")
# Peaks wie beim Schiffshorn: leise, dann ein lauter Stoss, immer wieder
LOUD = [40] * 8 + ([120] * 4 + [50] * 4) * 6 + [50] * 8 + [160] * 40 + [60] * 16 + [165] * 40
hits = a.find_hits(LOUD, 0.5, 0.0)
check([h[0] for h in hits[:3]] == [4.0, 8.0, 12.0], f"Schiffshorn: jeder Stoss wird erkannt: {hits[:3]}")
check(hits[0][1] == 2.0, "die Dauer des Peaks ist bekannt, hoechstens 4 Beats")
check(not a.find_hits([100] * 64, 0.5, 0.0)[1:], "gleichmaessig laut: kein Peak mitten im Lied")
check(a.find_hits([], 0.5, 0.0) == [], "ohne Wellenform: keine Peaks")
peaks_h = {"rate": 20, "min": [-v // 2 for v in LOUD for _ in range(10)], "max": [v // 2 for v in LOUD for _ in range(10)]}
check(a.beat_levels(peaks_h, 0.5, 0.0)[:9] == [40.0] * 8 + [120.0], "Lautstaerke je Beat aus der Wellenform")
loud_ev = [["drop", x, x] for x in (30.0, 32.0, 66.0)]
check(a.big_drops(loud_ev, 192.0, LOUD, 0.5, 0.0) == [32.0], "mit Wellenform gewinnt der Drop, bei dem es am meisten lauter wird")
doc_h = dict(doc, marks=dict(MARKS, ev=[], cu=[], se=[["vers", 0.0, DUR]]), bpm=120.0)
song_h = a.song_info(doc_h, peaks_h)
new_h = a.suggest(doc_h, mgr.meta(), ALL, peaks_h)[0]
plan_h = a.direct(song_h, "", 0.5, 0)
h_lead = [s["lead"] for s in plan_h if s["kind"] == "hit"]
check(h_lead and len(set(h_lead[:6])) == 1, f"eine Reihe von Peaks gehoert einem Geraet: {h_lead[:6]}")
check(all(len(playing_at(new_h, h[0] + 0.1)) <= 1 for h in song_h["hits"]), "am Peak leuchtet ein Geraet, nicht alle")
check(not playing_at(new_h, song_h["hits"][1][0] + song_h["hits"][1][1] + 0.5), "zwischen dichten Peaks ist es finster")
bh = next(t for t in new_h["tracks"] if t["target"].get("fixture") == "effektband" and t["attr"] == "dimmer")
pk = song_h["hits"][0]
fade = [k for k in bh["keys"] if k["t"] == pk[0]]
check(fade and fade[0]["v"] == 255 and fade[0]["e"] == "linear" and any(k["v"] == 0 and abs(k["t"] - pk[0] - pk[1]) < 0.01 for k in bh["keys"]), "Effektband am Peak: voll an, klingt mit der Amplitude ab")
presets = next(t for t in new_h["tracks"] if t["target"].get("fixture") == "effektband" and t["attr"] == "preset")["keys"]
check(len([k for k in presets if k["t"] < song_h["hits"][4][0]]) == 1, "eine Reihe von Peaks behaelt ihr Preset")
one_h = [dict(s, lead="bars") for s in plan_h if s["kind"] == "hit"][1]
trk_h = a.render([one_h], song_h, a.rig_parts(mgr.meta()), ALL, 0)
bars_h = next(t for t in trk_h if t["attr"] == "dimmer" and t["target"].get("group") == "rig_bars")
check(bars_h["keys"][0]["t"] == 0.0 and bars_h["keys"][0]["v"] == 0, "vor dem Peak dunkel, die Spur leuchtet nicht bis zum ersten Keyframe")
vals = [k["v"] for k in bars_h["keys"][1:]]
check(vals[0] == 255 and vals[-1] == 0 and all(x >= y for x, y in zip(vals, vals[1:])), f"Peak: startet bei 100 %, faellt nur noch, endet bei 0: {vals}")
check(bars_h["keys"][-1]["e"] == "constant" and bars_h["keys"][1]["e"] == "linear", "laeuft weich ab und bleibt danach dunkel, bis zum naechsten Peak")
# Amplitude: lauter Schlag, Horn klingt ab, darunter die Musik
rate_c = 50
env = [150] * 5 + [120] * 50 + [100] * 25 + [60] * 120
pk_c = {"rate": rate_c, "min": [-v // 2 for v in env], "max": [v // 2 for v in env]}
d_c, pts_c = a.hit_curve(pk_c, 0.0, 4.0)
at = lambda x: next(v for dt, v in reversed(pts_c) if dt <= x)
check(pts_c[0] == [0.0, 255.0] and at(0.5) < 255 and at(1.2) > 0 and at(1.7) == 0 and 1.5 <= d_c <= 1.7, f"die Kurve folgt der Amplitude: {pts_c}, Dauer {d_c}")
wob = [100, 140, 90, 130, 80, 120, 70, 110, 60, 50, 50, 50] * 30
_, pts_w = a.hit_curve({"rate": 50, "min": [-v // 2 for v in wob], "max": [v // 2 for v in wob]}, 0.0, 4.0)
vals_w = [v for _, v in pts_w]
check(all(x >= y for x, y in zip(vals_w, vals_w[1:])), "Schwankungen der Musik: die Kurve steigt nie wieder")
flat = song_h["hits"][1]
half = next(v for dt, v in reversed(flat[3]) if dt <= flat[1] / 2)
check(half >= 200, f"flach gehaltenes Horn bleibt hell, keine gleichmaessige Rampe: {flat[3]}")
check(flat[0] + flat[1] < song_h["hits"][2][0], "der Schlag des naechsten Peaks zaehlt nicht mehr dazu")
import random as _r                                               # noqa: E402
for seed_r in range(30):                                          # unregelmaessige Lieder: kurze Stoesse, die nicht auf dem Raster liegen
    rr = _r.Random(seed_r)
    env_r = []
    while len(env_r) < 9000:
        env_r += [rr.randint(20, 90)] * rr.randint(40, 400) + [rr.randint(120, 240)] * rr.randint(3, 120)
    pk_r = {"rate": 50, "min": [-v // 2 for v in env_r], "max": [v // 2 for v in env_r]}
    d_r = dict(doc_h, bpm=rr.uniform(70, 175), beat_offset=rr.uniform(0, 0.4), marks=dict(MARKS, ev=[], cu=[rr.uniform(1, 180) for _ in range(5)]))
    n_r = a.suggest(d_r, mgr.meta(), {**ALL, "seed": seed_r}, pk_r)[0]
    tl.normalize(n_r)
    s_r = a.song_info(d_r, pk_r)
    starts = [s["t"] for s in a.segments(s_r) if s["kind"] == "hit"]
    if not all(any(abs(h[0] - x) <= s_r["beat"] for x in starts) for h in s_r["hits"]):
        check(False, f"jeder Peak beginnt ein Stueck auf dem Beat (Lied {seed_r})")
check(True, "unregelmaessige Lieder: Vorschlag entsteht immer, jeder Peak beginnt auf dem Beat")
sh_bad = a.suggest
a.suggest = lambda *x, **y: next(iter(()))
try:
    mgr.op({"op": "assist", "name": "Lied", **ALL})
    check(False, "Fehler im Assistenten kommt als Meldung")
except ValueError as e:
    check("Vorschlag ging nicht" in str(e), "Fehler im Assistenten kommt als Meldung, nicht als abgerissene Verbindung")
a.suggest = sh_bad
# Fade-out: das Lied wird am Schluss leiser
FADE_V = [160] * 200 + [100, 110, 105, 90, 95, 80, 70, 72, 60, 50, 30, 10]
fd = a.find_fade(FADE_V, 0.5, 0.0, 106.0)
check(fd and fd[0] == 100.0 and fd[1][0] == [100.0, 255.0] and fd[1][-1] == [106.0, 0.0], f"Fade-out erkannt, von 100 % bis zum Schluss: {fd}")
fv = [v for _, v in fd[1]]
check(all(x >= y for x, y in zip(fv, fv[1:])) and len(fv) > 3, "der Fade folgt dem Pegel und steigt nie wieder")
check(a.find_fade([160] * 200, 0.5, 0.0, 100.0) is None, "hartes Ende: kein Fade")
check(a.find_fade([160] * 200 + [20] * 2, 0.5, 0.0, 101.0) is None, "kurz abgerissen: kein Fade")
pk_f = {"rate": 20, "min": [-v // 2 for v in FADE_V for _ in range(10)], "max": [v // 2 for v in FADE_V for _ in range(10)]}
d_f = dict(doc_h, duration=106.0, marks=dict(MARKS, ev=[], cu=[], se=[["main", 0.0, 106.0]]))
n_f, pl_f, s_f = a.suggest(d_f, mgr.meta(), ALL, pk_f)
mt = [t for t in n_f["tracks"] if t["target"].get("master")]
check(mt and mt[0]["keys"][0]["t"] == 100.0, "der Fade liegt auf der Master-Zeile")
check(tl.normalize(n_f)["tracks"][0] is not None and any("master" in t["target"] for t in tl.normalize(n_f)["tracks"]), "Master-Keyframes bleiben beim Speichern")
c_f = tl.compile_show(dict(n_f, name="F"), rig)
check(c_f.master_at(50.0) == 1.0 and 0 < c_f.master_at(103.0) < 1.0 and c_f.master_at(106.0) == 0.0, "Master: bis zum Fade 100 %, dann abblenden")
check(not [s for s in pl_f if s["t"] >= 100.0 and s["lead"] in ("laser", "bars", "fx")], "im Ausklang nichts Hartes, kein Laser")
cmp_h = tl.compile_show(dict(a.suggest(doc_h, mgr.meta(), ALL, peaks_h)[0], name="H"), rig)
check(cmp_h is not None and not cmp_h.warnings, "Show mit Kurven laesst sich uebersetzen")
laser_h = a.render([dict(s, lead="laser") for s in plan_h if s["kind"] == "hit"][:1], song_h, a.rig_parts(mgr.meta()), ALL, 0)
lc = [c for t in laser_h if t["attr"] == "laser" for c in t["clips"]]
check(lc and lc[0]["p"]["ktv_fan"] == lc[0]["p"]["ktv_fan_to"] == 255 and lc[0]["p"]["ktv_size"] < lc[0]["p"]["ktv_size_to"] and abs(lc[0]["d"] - song_h["hits"][0][1]) < 0.01, "Laser am Peak: Faecher bleibt offen, das Bild zoomt klein, so lang wie das Horn")
body_h = a.claude_request(a.direct(song_h, "", 0.5, 1), song_h, ALL, "")
user_h = json.loads(body_h["messages"][0]["content"])
check(user_h["starke_peaks"] and user_h["lautstaerke_je_takt"] and "min" not in user_h, "Claude bekommt Peaks und Lautstaerke, keine Wellenform und keine Musik")
big = a.big_drops([["drop", x, x] for x in (7.6, 22.9, 64.8, 83.8, 158.1, 177.1, 192.4)], 211.0)
check(big == [64.8, 158.1], "viele gemeldete Drops: nur die grossen zaehlen, weit auseinander")
wash_on = sum(1 for t in rng_t if "rig_wash" in playing_at(new, t))
check(wash_on < len(rng_t) * 0.3, "Washes leuchten nicht durchgehend")
band = next(t for t in new["tracks"] if t["target"].get("fixture") == "effektband" and t["attr"] == "dimmer")


def band_at(sec):
    v = 0
    for k in band["keys"]:
        if k["t"] <= sec:
            v = k["v"]
    return v


check(band_at(49.0) > 0 and band_at(113.0) > 0, "Effektband spielt beim Drop")
band_share = sum(1 for t in rng_t if band_at(t) > 0) / len(rng_t)
check(0.0 < band_share < 0.4, "Effektband ist nicht dauernd an")
dark_band = [t for t in outside if band_at(t) > 0 and playing_at(new, t)]
check(not dark_band, "wenn das Effektband dran ist, spielt es allein")
check(band_at(16.5) > 0, "Effektband kommt am Cue zum Einsatz")

x1 = a.suggest(doc, mgr.meta(), {**ALL, "seed": 1})[0]["tracks"]
check(x1 == a.suggest(doc, mgr.meta(), {**ALL, "seed": 1})[0]["tracks"], "gleicher Zufallswert: gleicher Vorschlag")
check(x1 != a.suggest(doc, mgr.meta(), {**ALL, "seed": 2})[0]["tracks"], "anderer Zufallswert: anderer Vorschlag")
calm = a.direct(song, "ruhig", 0.5, 1)
check(max(s["level"] for s in calm) <= 2, "Stil Ruhig: kein Hoehepunkt")
xmas = a.suggest(doc, mgr.meta(), {**ALL, "style": "weihnachten", "seed": 1})[0]
check(not [t for t in xmas["tracks"] if t["target"].get("group") == "rig_uv"], "Weihnachten: kein UV")
check(not [c for c in clips(xmas, "color") if c["pattern"] == "rainbow"], "Weihnachten: kein Regenbogen")

# ---- Am Licht: laeuft durch die normale Engine ------------------------------------------------------------------------
def run_to(sec, laser=1.0):
    """Vorschlag mit echter Engine bis zur Stelle spielen; gibt das Rig zurueck."""
    rig2, sh2 = build(strobe=True)
    sh2.cfg.set("sm_laser", laser)
    m2 = ShowManager(sh2, tempfile.mkdtemp(dir=tmp))
    warn = m2.engine.load(new)
    c = Clock(sh2)
    m2.engine.play(c.t, sec - 0.5, True, None)
    c.run(0.5)
    return rig2, warn


rig2, warn = run_to(49.0)
check(not warn, f"Engine kennt alle Spuren des Vorschlags: {warn}")


def light(r, name, params=("r", "g", "b")):
    """Helligkeit eines Farbgeraets: beim Show-Bild stecken Farbe und Dimmer zusammen in den Farbkanaelen."""
    return max(ch(r, name, p) for p in params)


BARS = ("r1", "g1", "b1", "w1", "r2", "b2", "w2")
check(light(rig2, "rgbuv_7") > 0, "im Hauptteil leuchtet es")
rig3, _ = run_to(111.0)
check(light(rig3, "docooler_1", BARS) == 0 and light(rig3, "rgbuv_7") == 0 and light(rig3, "par") == 0, "in der Pause finster")
check(light(rig2, "rgbuv_7") <= 0.4 * 255, "Washes am echten Bild dezent")
rig5, _ = run_to(49.0)
check(ch(rig5, "laser", "power") == 255, "mit Erlaubnis laeuft der Laser im Hauptteil am Hoehepunkt")
rig4, _ = run_to(49.0, laser=0.0)
f = rig4.render()
check(all(f[x.address - 1 + x.map[p] - 1] == x.rest.get(p, 0) for x in rig4.fixtures if x.laser_params for p in x.laser_params), "ohne Laser-Erlaubnis bleibt jeder Laser aus, obwohl Clips da sind")

# ---- Nanoleaf: spielt mit, wenn es ihn gibt ---------------------------------------------------------------------------
rig6, sh6 = build(strobe=True)
for i in range(3):
    nano = Fixture(f"nano_{i}", "nanoleaf_panel", {"channels": 3, "map": {"r": 1, "g": 2, "b": 3}}, 1 + 3 * i, "nano", target="nanoleaf:10.0.0.1", extra={"nr": 100 + i, "label": f"Panel {i}", "x": i / 3})
    rig6.fixtures.append(nano)
    rig6.by_name[nano.name] = nano
m6 = ShowManager(sh6, tempfile.mkdtemp(dir=tmp))
d6 = m6.store.create("Nano")
d6.update(bpm=BPM, duration=DUR, marks=MARKS)
m6.store.save("Nano", d6)
n6 = m6.store.load(m6.op({"op": "assist", "name": "Nano", **ALL})["show"])
check({"rig_nano"} <= {t["target"].get("group") for t in n6["tracks"]}, "Vorschlag steuert die Nanoleaf-Panels")
warn6 = m6.engine.load(n6)
c6 = Clock(sh6)
m6.engine.play(c6.t, 48.5, True, None)
seen6 = []
c6.run(1.0, lambda t: seen6.append(max(ch(rig6, "nano_0", p) for p in "rgb")))
check(not warn6 and max(seen6) > 0, "am Bild leuchten die Panels")
check(not {"rig_nano"} & {t["target"].get("group") for t in new["tracks"]}, "ohne Nanoleaf: keine leere Spur")

# ---- Claude: Zusatz, ungepruefte Antwort, Rueckfall offline -----------------------------------------------------------
check(mgr.op({"op": "assist_info", "name": "Lied"})["has_key"] is False, "ohne Schluessel")
r = mgr.op({"op": "assist", "name": "Lied", **ALL, "claude": True})
check(not r["claude"] and "offline" in r["note"], "ohne Schluessel: offline, mit Hinweis")
for bad in ("zu kurz", "mit leerzeichen und so weiter und so fort"):
    try:
        mgr.op({"op": "claude_key", "key": bad})
        check(False, "unsinniger Schluessel abgelehnt")
    except ValueError:
        check(True, "unsinniger Schluessel abgelehnt")
KEY = "sk-ant-test-" + "x" * 30
check(mgr.op({"op": "claude_key", "key": KEY}) == {"has_key": True}, "Schluessel wird gespeichert und nicht zurueckgegeben")
check(sys.platform == "win32" or oct(os.stat(mgr.key_path).st_mode)[-3:] == "600",
      "Schluesseldatei nur fuer den Besitzer")   # Windows: keine Unix-Rechte, das Benutzerprofil ist ohnehin privat
check(KEY not in json.dumps(mgr.op({"op": "assist_info", "name": "Lied"})), "Schluessel steht nicht in der Anzeige")

sent = []
ANSWER = {"note": "Mehr Blau.", "segments": [{"i": 0, "level": 3, "colors": ["#0000ff", "#00ffff"], "dimmer": "chase", "color": "rainbow", "move": "circle", "laser": True, "fog": True},
                                             {"i": 1, "level": 99, "colors": ["rot", "<script>"], "lead": "alles", "also": "alles", "dimmer": "strobe", "color": "boese", "move": "x", "laser": "ja", "fog": 1},
                                             {"i": 9999, "level": 1}]}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake(req, timeout=0):
    sent.append(req)
    return Resp(json.dumps({"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": json.dumps(ANSWER)}]}).encode())


mgr.claude_opener = fake
r = mgr.op({"op": "assist", "name": "Lied", **ALL, "seed": 3, "claude": True, "wish": "mehr Blau"})
check(r["claude"] and r["note"] == "Mehr Blau.", "Claude: Antwort kommt an, Hinweis fuers Panel")
req = sent[0]
body = json.loads(req.data.decode())
check(req.full_url == a.API_URL and req.get_header("X-api-key") == KEY and req.get_header("Anthropic-version") == a.API_VERSION, "Claude: Aufruf mit Schluessel im Kopf")
check(body["model"] == a.MODEL and body["output_config"]["format"]["type"] == "json_schema" and "thinking" not in body and "temperature" not in body, "Claude: Modell und festes Antwortformat")
user = json.loads(body["messages"][0]["content"])
check(user["wunsch"] == "mehr Blau" and user["genre"] == "House" and KEY not in body["messages"][0]["content"], "Claude: Wunsch und Genre gehen mit, der Schluessel nicht im Text")
check(not any(w in json.dumps(user) for w in ("192.168", "fritz" ".box", "audio.mp3")), "Claude: keine Adressen aus dem Heimnetz")

plan = a.direct(song, "club", 0.5, 1)
keep = dict(plan[1])
a.apply_claude(plan, ANSWER)
check(plan[0]["level"] == 2 and plan[0]["colors"] == ["#0000ff", "#00ffff"] and plan[0]["dimmer"] == "chase", "gueltige Aenderung gilt")
check(plan[1]["level"] == 2 and plan[1]["lead"] == keep["lead"] and plan[1]["also"] == keep["also"] and plan[1]["colors"] == keep["colors"] and plan[1]["dimmer"] == keep["dimmer"] and plan[1]["color"] == keep["color"] and plan[1]["laser"] == keep["laser"], "Unsinn aus der Antwort wird verworfen, Stufe begrenzt")
for odd in (None, [], "text", {"segments": "x"}, {"segments": [1, None]}):
    a.apply_claude(a.direct(song, "club", 0.5, 1), odd)
check(True, "kaputte Antwort: kein Absturz")

plan_off = a.direct(song, "club", 0.5, 1)
for s in plan_off:
    s.update(laser=True, fog=True, level=3)
out = a.render(plan_off, song, a.rig_parts(mgr.meta()), off, 1)
check(not [t for t in out if t["attr"] in ("laser", "fog", "move")] and not [c for t in out for c in t["clips"] if c["pattern"] == "strobe"], "Claude kann ausgeschaltete Effekte nicht einschalten")


def boom(code):
    def f(req, timeout=0):
        raise urllib.error.HTTPError(a.API_URL, code, "x", {}, None)
    return f


for opener, text in ((boom(401), "Schluessel"), (boom(429), "ueberlastet"), (boom(500), "Fehler 500")):
    mgr.claude_opener = opener
    r = mgr.op({"op": "assist", "name": "Lied", **ALL, "claude": True})
    check(not r["claude"] and text in r["note"] and "offline" in r["note"] and KEY not in r["note"], f"Claude-Fehler {text}: offline, Schluessel nicht in der Meldung")


def refused(req, timeout=0):
    return Resp(json.dumps({"stop_reason": "refusal", "content": []}).encode())


mgr.claude_opener = refused
check("abgelehnt" in mgr.op({"op": "assist", "name": "Lied", **ALL, "claude": True})["note"], "Claude lehnt ab: offline")
check(mgr.op({"op": "claude_key", "key": ""}) == {"has_key": False} and not os.path.exists(mgr.key_path), "Schluessel loeschen")
shutil.rmtree(tmp, ignore_errors=True)
finish("test_showmanager_assistent")
