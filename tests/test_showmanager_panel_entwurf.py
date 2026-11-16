"""Showmanager: Szenen aus dem Hauptpanel in eigener Zeile, Claude entwirft die ganze Show. Claude ist nachgestellt, kein Netz."""
import io
import json
import os
import tempfile
import urllib.error

from _common import Clock, build, check, ch, finish

from showman import assistant as a
from showman import timeline as tl
from showman.api import ShowManager

rig, sh = build(strobe=True)
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_pe_"))
names = mgr.panel_scenes()
all_names = {s.name: s.special for s in sh.scene_defs}
check(names and "Laser" not in names and "All off" not in names and not any(all_names[n] for n in names), "Panel-Szenen: keine Sondertasten, nicht die Szene Laser")
SC = next(n for n in names if n == "rot") if "rot" in names else names[0]


def show(tracks, duration=60.0):
    d = tl.new_show("P")
    d.update(duration=duration, bpm=120.0, tracks=tracks)
    return d


def panel(*clips):
    return {"target": {"panel": True}, "attr": "panel_scene", "keys": [{"t": 0, "v": 1}], "clips": [{"t": t, "d": dd, "pattern": "panel_scene", "p": {"panel_scene": n}} for t, dd, n in clips]}


n = tl.normalize(show([panel((2, 4, SC)), panel((9, 1, SC))]))
check(len(n["tracks"]) == 1 and n["tracks"][0]["keys"] == [] and n["tracks"][0]["attr"] == "panel_scene", "nur eine Panel-Zeile, nur Clips")
check(tl.normalize(show([panel()]))["tracks"] == [], "ohne Clips keine Spur in der Datei")
check(tl.normalize(n) == n, "bleibt beim Speichern gleich")
c = tl.compile_show(n, rig)
check(not c.warnings and c.panel_scene_at(3.0) == SC and c.panel_scene_at(7.0) is None, "Show kennt die Szene zur Zeit")

DIM = {"target": {"fixture": "rgbuv_7"}, "attr": "dimmer", "keys": [{"t": 0, "v": 0, "e": "constant"}], "clips": []}


def start(tracks, pos, **kw):
    r, s = build(strobe=True)
    m = ShowManager(s, tempfile.mkdtemp(prefix="s2l_pe_"))
    ck = Clock(s)
    m.engine.load(show(tracks))
    m.engine.play(ck.t, pos, True, None)
    return r, s, m, ck


def wash(r):
    return max(ch(r, "rgbuv_7", p) for p in "rgb")


r0, s0, m0, ck = start([DIM, panel((2, 4, SC))], 0.5)
ck.run(0.3)
check(wash(r0) == 0, "vor dem Clip: das, was die Show programmiert hat")
ck.run(2.2)
check(wash(r0) > 0, "im Clip: die Szene aus dem Panel leuchtet")
sc_before = s0.sc
check(sc_before is None, "die Auswahl im Panel bleibt unberuehrt")
ck.run(3.5)
check(wash(r0) == 0, "danach wieder die Show")
r1, s1, m1, ck = start([panel((0, 30, SC))], 1.0)
ck.run(0.2)
full = wash(r1)
s1.override = "blackout"
ck.run(0.1)
check(wash(r1) == 0, "BLACKOUT geht vor")
s1.override = None
r2, s2, m2, ck = start([panel((0, 30, SC)), {"target": {"master": True}, "attr": "master", "keys": [{"t": 0, "v": 128, "e": "constant"}], "clips": []}], 1.0)
ck.run(0.2)
check(0 < wash(r2) < full, "Master-Zeile regelt auch die Panel-Szene")
check(s2.master == 1.0 or s2.master == s1.master, "der Dimmer im Panel bleibt, wie er war")
r3, s3, m3, ck = start([panel((0, 30, "Laser")), {"target": {"fixture": "laser"}, "attr": "dimmer", "keys": [], "clips": []}], 1.0)
s3.cfg.set("sm_laser", 1.0)
ck.run(0.3)
f3 = r3.render()
check(all(f3[x.address - 1 + x.map[p] - 1] == x.rest.get(p, 0) for x in r3.fixtures if x.laser_params for p in x.laser_params), "Szene Laser aus einer Showdatei: bleibt aus, Laser gehen nur ueber Laser-Clips")
r4, s4, m4, ck = start([panel((0, 30, "gibtsnicht"))], 1.0)
ck.run(0.1)
check(m4.engine.active(), "unbekannte Szene: kein Absturz")
laser_clip = {"target": {"fixture": "laser"}, "attr": "laser", "keys": [], "clips": [{"t": 0, "d": 30, "pattern": "laser", "p": {}}]}
r5, s5, m5, ck = start([panel((0, 5, SC)), laser_clip], 1.0)
s5.cfg.set("sm_laser", 1.0)
ck.run(0.3)
check(not s5.snapshot()["laser"] and ch(r5, "laser", "power") == 0, "waehrend der Panel-Szene ruht der Laser-Clip")

# ---- Claude entwirft -------------------------------------------------------------------------------------------------------
mgr.key_path = os.path.join(mgr.store.base, "s2l_test_key.json")
mgr.spent_path = os.path.join(mgr.store.base, "s2l_test_kosten.json")
mgr.op({"op": "claude_key", "key": "sk-ant-test-" + "y" * 30})
MARKS = {"se": [["main", 0.0, 60.0]], "cu": [8.0], "ev": [["drop", 30.0, 30.0]], "en": [], "lvl": 7, "genre": "House", "title": "Test - Lied", "fp": ""}
d = mgr.store.create("Lied")
d.update(bpm=120.0, duration=60.0, marks=MARKS)
d["tracks"] = [{"target": {"fixture": "vega"}, "attr": "dimmer", "keys": [{"t": 0, "v": 9, "e": "linear"}], "clips": []}]
mgr.store.save("Lied", d)
mgr.job_sync = True
ANSWER = {"note": "Blau zu Beginn, dann Rot.", "tracks": [
    {"target": {"group": "rig_spot"}, "attr": "dimmer", "keys": [{"t": 0, "v": 0, "e": "constant"}, {"t": 4, "v": 255, "e": "linear"}, {"t": 6, "v": 0, "e": "constant"}, {"t": 99999, "v": 3}], "clips": [{"t": 8, "d": 4, "pattern": "pulse", "p": {"speed": 0.5, "beat_sync": 1, "boese": 1}}]},
    {"target": {"group": "rig_wash"}, "attr": "dimmer", "clips": [{"t": 0, "d": 8, "pattern": "sine", "p": {"start": 10, "end": 90}}]},
    {"target": {"group": "rig_wash"}, "attr": "color", "clips": [{"t": 0, "d": 8, "pattern": "solid_color", "p": {"color_a": "#0000ff"}}, {"t": 8, "d": 2, "pattern": "pulse", "p": {}}]},
    {"target": {"group": "rig_bars"}, "attr": "dimmer", "clips": [{"t": 30, "d": 2, "pattern": "strobe", "p": {}}, {"t": 40, "d": 2, "pattern": "gibtsnicht", "p": {}}]},
    {"target": {"fixture": "laser"}, "attr": "laser", "clips": [{"t": 30, "d": 2, "pattern": "laser", "p": {"ktv_effect": 5}}]},
    {"target": {"fixture": "hazer"}, "attr": "fog", "clips": [{"t": 25, "d": 60, "pattern": "fog_burst"}, {"t": 28, "d": 3, "pattern": "fog_burst"}]},
    {"target": {"fixture": "vega"}, "attr": "shutter", "keys": [{"t": 0, "v": 255}]},
    {"target": {"fixture": "docooler_1"}, "attr": "strobe", "keys": [{"t": 0, "v": 255}]},
    {"target": {"fixture": "eyes"}, "attr": "mode", "keys": [{"t": 0, "v": 255}]},
    {"target": {"group": "gibtsnicht"}, "attr": "dimmer", "keys": [{"t": 0, "v": 255}]},
    {"target": {"panel": True}, "clips": [{"t": 12, "d": 8, "pattern": "panel_scene", "p": {"panel_scene": SC}}, {"t": 22, "d": 1, "pattern": "panel_scene", "p": {"panel_scene": "Laser"}}]},
    "kaputt"]}


class Stream:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *x):
        return False

    def __iter__(self):
        return iter(self.lines)


def sse(*events):
    return [("data: " + json.dumps(e) + "\n").encode() for e in events]


def good(text, stop="end_turn"):
    half = len(text) // 2
    return sse({"type": "message_start", "message": {"usage": {"input_tokens": 1000, "output_tokens": 1}}}, {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "x"}}, {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hier:\n" + text[:half]}},
               {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text[half:]}}, {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 5000}})


sent = []


def opener(req, timeout=0):
    sent.append(req)
    return Stream(good(json.dumps(ANSWER)))


mgr.claude_opener = opener
ALL = {"laser": True, "fog": True, "strobe": True, "move": True, "seed": 1}
r = mgr.op({"op": "assist", "name": "Lied", **ALL, "design": True, "wish": "mehr Blau", "lyrics": "Ein Liedtext zum Testen"})
check(r == {"job": True}, "Claude entwirft: laeuft im Hintergrund")
j = mgr.op({"op": "assist_job"})
check(j["state"] == "done" and j["result"]["claude"] and j["chars"] > 100, f"fertig, Fortschritt bekannt: {j['state']} {j.get('error')}")
check("Blau zu Beginn" in j["result"]["note"] and "verworfen" in j["result"]["note"], "Hinweis von Claude und Zahl der verworfenen Eintraege")
check(j["result"]["design"] is True, "Fenster weiss: Claude hat die Show entworfen")
check(abs(j["result"]["cost_usd"] - (1000 * 4 + 5000 * 20) / 1e6) < 0.001, f"Kosten aus den Tokens: {j['result']['cost_usd']}")
check(j["result"]["spent"]["calls"] == 1 and abs(j["result"]["spent"]["usd"] - 0.104) < 0.001, "Summe seit Beginn gezaehlt")
check(mgr.op({"op": "assist_info", "name": "Lied"})["spent"]["calls"] == 1, "Summe steht auch im Fenster")
body = json.loads(sent[0].data.decode())
check(body["stream"] and body["model"] == a.MODEL and body["max_tokens"] >= 32000 and "temperature" not in body and "thinking" not in body, "lange Antwort: gestreamt")
user = json.loads(body["messages"][0]["content"])
check(user["liedtext"] == "Ein Liedtext zum Testen" and user["wunsch"] == "mehr Blau" and user["titel"] == "Test - Lied" and user["genre"] == "House", "Titel, Text, Genre und Wunsch gehen mit")
rg = user["rig"]
check({g["id"] for g in rg["gruppen"]} >= {"rig_bars", "rig_wash", "rig_spot"} and SC in rg["panel_scenes"] and rg["einzelgeraete"], "Claude kennt Gruppen, Einzelgeraete und Panel-Szenen")
vega = next(x for x in rg["einzelgeraete"] if x["name"] == "vega")
check(any(s["attr"] == "gobo" and s.get("werte") for s in vega["spuren"]), "auch die Gobos mit Namen")
check(all(s["attr"] in a.DESIGN_ATTRS for x in rg["einzelgeraete"] for s in x["spuren"]), "keine rohen Strobe-, Mode- oder Laser-Kanaele im Angebot")
pk = {p["key"] for p in user["patterns"]}
check({"pulse", "laser", "fog_burst", "panel_scene"} <= pk, "alle Muster mit Parametern")
blob = json.dumps(body)
check(not any(w in blob for w in ("192.168", "fritz" ".box", "sk-ant-test", "audio.mp3")), "keine Adressen, kein Schluessel im Text")
check(sent[0].get_header("X-api-key").startswith("sk-ant-test"), "Schluessel nur im Kopf")
new = mgr.store.load(j["result"]["show"])
check(mgr.store.load("Lied")["tracks"][0]["keys"][0]["v"] == 9, "die Show selbst bleibt unberuehrt")
by = {(json.dumps(t["target"], sort_keys=True), t["attr"]): t for t in new["tracks"]}
spot = by[('{"group": "rig_spot"}', "dimmer")]
check(len(spot["keys"]) == 3 and spot["clips"][0]["pattern"] == "pulse" and "boese" not in spot["clips"][0]["p"], "gueltige Keyframes und Clips bleiben, Unsinn faellt weg")
check([c["pattern"] for c in by[('{"group": "rig_wash"}', "color")]["clips"]] == ["solid_color"], "Muster auf falscher Spur faellt weg")
check([c["pattern"] for c in by[('{"group": "rig_bars"}', "dimmer")]["clips"]] == ["strobe"], "unbekanntes Muster faellt weg")
fog = by[('{"fixture": "hazer"}', "fog")]["clips"]
check(len(fog) == 1 and fog[0]["d"] <= a.FOG_S, "Nebel: Laenge begrenzt, Abstand eingehalten")
check(not [t for t in new["tracks"] if t["attr"] in ("shutter", "strobe", "mode")], "rohe Strobe- und Mode-Kanaele kommen nie durch")
pc = by[('{"panel": true}', "panel_scene")]["clips"]
check(len(pc) == 1 and pc[0]["p"]["panel_scene"] == SC, "Panel-Szene gilt, die Szene Laser nicht")
check(sh.cfg["sm_laser"] < 0.5 and sh.cfg["sm_fog"] < 0.5, "keine Erlaubnis wird eingeschaltet")
r_off = mgr.op({"op": "assist", "name": "Lied", "laser": False, "fog": False, "strobe": False, "move": True, "seed": 1, "design": True})
n_off = mgr.store.load(mgr.op({"op": "assist_job"})["result"]["show"])
check(not [t for t in n_off["tracks"] if t["attr"] in ("laser", "fog")] and not [c for t in n_off["tracks"] for c in t["clips"] if c["pattern"] == "strobe"], "Hakerl aus: Claude kommt nicht durch")
cc = tl.compile_show(new, rig)
check(not cc.warnings, f"Entwurf laesst sich abspielen: {cc.warnings}")

# ---- Effektband, Washes -----------------------------------------------------------------------------------------------------
vu = next(x for x in rg["einzelgeraete"] if x["name"] == "effektband")
check(vu["rolle"] == "Effektband" and {"dimmer", "preset"} <= {s["attr"] for s in vu["spuren"]}, "Claude sieht das Effektband als eigene Rolle, nicht als Ambiente")
check(not [o for s in vu["spuren"] if s["attr"] == "preset" for o in s.get("werte", []) if "♫" in o["name"]], "keine Soundeffekte im Angebot")
check("Effektband" in a.DESIGN_SYSTEM and "keines bleibt die ganze Zeit dunkel" in a.DESIGN_SYSTEM, "Anleitung: jedes Geraet kommt vor")
mt = mgr.meta()
s_b = {"dur": 60.0, "bar": 2.0, "beat": 0.5, "drops": [30.0], "cues": [8.0, 31.0], "fade": None}
tr_b, _ = a.apply_design({}, {"tracks": [{"target": {"group": "rig_spot"}, "attr": "dimmer", "keys": [{"t": 0, "v": 9}]}]}, mt, s_b, ALL)
bd = [t for t in tr_b if t["target"].get("fixture") == "effektband"]
dk = next(t for t in bd if t["attr"] == "dimmer")["keys"]
check(len(bd) == 2 and any(k["t"] == 30.0 and k["v"] == 255 for k in dk) and any(k["t"] == 8.0 and k["v"] == 255 for k in dk) and dk[0]["v"] == 0, "Effektband vergessen: es spielt an Drops und Cues")
ans_b = {"tracks": [{"target": {"fixture": "effektband"}, "attr": "dimmer", "keys": [{"t": 5, "v": 200}]}, {"target": {"fixture": "effektband"}, "attr": "preset", "keys": [{"t": 5, "v": 3, "e": "constant"}]}]}
tr_c, _ = a.apply_design({}, ans_b, mt, s_b, ALL)
check(len([t for t in tr_c if t["target"].get("fixture") == "effektband"]) == 2 and not ans_b.get("_band_filled"), "Claude bespielt es selbst: nichts dazu")
tr_w, dw = a.apply_design({}, {"tracks": [{"target": {"group": "rig_wash"}, "attr": "dimmer", "keys": [{"t": 1, "v": 255}], "clips": [{"t": 2, "d": 2, "pattern": "strobe", "p": {}}, {"t": 4, "d": 2, "pattern": "sine", "p": {"start": 200, "end": 255}}]}]}, mt, s_b, ALL)
wt = next(t for t in tr_w if t["target"].get("group") == "rig_wash")
check(wt["keys"][0]["v"] <= 102 and [c["pattern"] for c in wt["clips"]] == ["sine"] and wt["clips"][0]["p"]["end"] <= 102 and dw == 1, "Washes bleiben dezent und blitzen nicht, auch bei Claude")
tr_a, da = a.apply_design({}, {"tracks": [{"target": {"group": "rig_ambient"}, "attr": "dimmer", "keys": [{"t": 1, "v": 255}]}, {"target": {"fixture": "par"}, "attr": "dimmer", "keys": [{"t": 1, "v": 255}]}, {"target": {"group": "rig_spot"}, "attr": "dimmer", "keys": [{"t": 1, "v": 9}]}]}, mt, s_b, ALL)
check(da == 2 and not [t for t in tr_a if t["target"].get("group") == "rig_ambient" or t["target"].get("fixture") == "par"], "Ambiente nur mit Hakerl, auch als Gruppe")

# Farbe ohne Dimmer: so war die UV-Leiste in einer echten Show die ganze Zeit an
tr_u, _ = a.apply_design({}, {"tracks": [
    {"target": {"group": "rig_uv"}, "attr": "dimmer", "clips": [{"t": 10, "d": 4, "pattern": "pulse", "p": {}}, {"t": 12, "d": 4, "pattern": "pulse", "p": {}}, {"t": 30, "d": 2, "pattern": "pulse", "p": {}}]},
    {"target": {"group": "rig_uv"}, "attr": "color", "clips": [{"t": 0, "d": 60, "pattern": "solid_color", "p": {"color_a": "#ff0000"}}]},
    {"target": {"group": "rig_spot"}, "attr": "dimmer", "keys": [{"t": 0, "v": 0}, {"t": 5, "v": 255}]},
    {"target": {"group": "rig_bars"}, "attr": "color", "clips": [{"t": 0, "d": 60, "pattern": "solid_color", "p": {"color_a": "#00ff00"}}]},
    {"target": {"group": "rig_fx"}, "attr": "dimmer", "keys": [{"t": 0, "v": 0}]},
    {"target": {"group": "rig_fx"}, "attr": "color", "clips": [{"t": 0, "d": 60, "pattern": "solid_color", "p": {"color_a": "#0000ff"}}]}]}, mt, s_b, ALL)
col = {t["target"].get("group"): t for t in tr_u if t["attr"] == "color"}
check([(c["t"], c["d"]) for c in col["rig_uv"]["clips"]] == [(10.0, 6.0), (30.0, 2.0)], "Farbe gilt nur, wo der Dimmer laeuft: UV nicht mehr dauernd an")
check("rig_bars" not in col, "Farbe ganz ohne Dimmer faellt weg")
check(len(col["rig_fx"]["clips"]) == 1 and col["rig_fx"]["clips"][0]["d"] == 60.0, "Dimmer mit Keyframes: Farbe bleibt, die Keyframes setzen die Helligkeit")
check("ohne gleichzeitig laufenden Dimmer" in a.DESIGN_SYSTEM, "Anleitung nennt die Falle")
check("Vega" in a.DESIGN_SYSTEM and "Laser von 38" in a.DESIGN_SYSTEM, "Anleitung: Peaks auf helle Geraete, Beispiel aus Titanium")

# ---- Fade bleibt, Fehler fuehren zu offline --------------------------------------------------------------------------------
song_f = {"dur": 60.0, "bar": 2.0, "beat": 0.5, "drops": [], "cues": [], "fade": [50.0, [[50.0, 255.0], [60.0, 0.0]]]}
tr_f, _ = a.apply_design({}, {"tracks": [{"target": {"group": "rig_spot"}, "attr": "dimmer", "keys": [{"t": 0, "v": 9}]}]}, mgr.meta(), song_f, ALL)
check(any("master" in t["target"] for t in tr_f), "Ausblenden am Schluss bleibt dabei, wenn Claude es vergisst")
for bad in ({}, {"tracks": "x"}, {"tracks": []}, {"tracks": [{"target": {"master": True}, "keys": [{"t": 0, "v": 9}]}]}):
    try:
        a.apply_design({}, bad, mgr.meta(), song_f, ALL)
        check(False, f"unbrauchbare Antwort erkannt: {bad}")
    except ValueError:
        check(True, f"unbrauchbare Antwort erkannt: {str(bad)[:30]}")


def http(code):
    def f(req, timeout=0):
        raise urllib.error.HTTPError(a.API_URL, code, "x", {}, None)
    return f


CASES = ((http(401), "Schluessel"), (http(402), "Guthaben"), (http(500), "Fehler 500"), (lambda q, timeout=0: Stream(good(json.dumps(ANSWER), "refusal")), "abgelehnt"),
         (lambda q, timeout=0: Stream(good(json.dumps(ANSWER), "max_tokens")), "zu lang"), (lambda q, timeout=0: Stream(good("Das ist kein JSON")), "nicht lesbar"),
         (lambda q, timeout=0: Stream(good('{"tracks": []}')), "keine brauchbaren"), (lambda q, timeout=0: Stream(sse({"type": "error", "error": {"type": "overloaded_error"}})), "overloaded"))
for op, text in CASES:
    mgr.claude_opener = op
    mgr.op({"op": "assist", "name": "Lied", **ALL, "design": True})
    j = mgr.op({"op": "assist_job"})
    check(j["state"] == "done" and not j["result"]["claude"] and text in j["result"]["note"] and "offline" in j["result"]["note"] and "sk-ant" not in j["result"]["note"], f"Fehler {text}: offline erstellt, Grund im Fenster")
    n_o = mgr.store.load(j["result"]["show"])
    if not n_o["tracks"]:
        check(False, "offline: trotzdem eine Show")
mgr.claude_opener = lambda q, timeout=0: (_ for _ in ()).throw(RuntimeError("x"))
mgr.op({"op": "assist", "name": "Lied", **ALL, "design": True})
j = mgr.op({"op": "assist_job"})
check(j["state"] == "error" and "Vorschlag ging nicht" in j["error"], "unerwarteter Fehler: Meldung im Fenster, kein Absturz")
mgr.job = {"state": "running", "chars": 0, "result": None, "error": ""}
try:
    mgr.op({"op": "assist", "name": "Lied", **ALL, "design": True})
    check(False, "nur ein Entwurf zugleich")
except ValueError:
    check(True, "nur ein Entwurf zugleich")
mgr.job = None
check(mgr.op({"op": "assist_job"})["state"] == "none", "Stand ohne Auftrag")
ej = open(os.path.join(os.path.dirname(os.path.abspath(a.__file__)), "..", "static", "sm", "editor.js"), encoding="utf-8").read()
check(ej.index('id="aspent"') < ej.index('id="amode"') and "noch kein Aufruf" in ej, "Kosten stehen oben im Fenster, schon bevor Claude gewaehlt ist")
check("confirmBox('API-Schlüssel wirklich löschen?" in ej and ej.index('id="akeydel"') < ej.index('id="awish"') < ej.index('id="ago"'), "Schluessel loeschen: oben im Bereich, weit weg vom Knopf, mit Rueckfrage")
mgr.op({"op": "claude_key", "key": ""})
io.StringIO()
finish("test_showmanager_panel_entwurf")
