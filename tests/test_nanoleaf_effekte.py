"""Nanoleaf-Effekte im Showmanager und AUTO "Geraete der Reihe nach". Das Geraet ist nachgestellt: kein Netz, keine echte Hardware."""
import json
import os
import tempfile
import time

from _common import Clock, build, check, finish

from dmx import Fixture
from nanoleaf import Client, NanoleafError, NanoleafSender
from showman import assistant as a
from showman import fixtures as fm
from showman import patterns as pt
from showman import timeline as tl
from showman.api import ShowManager


class FakeClient:
    def __init__(self):
        self.effect, self.calls, self.fail = "Forest", [], False

    def current_effect(self):
        if self.fail:
            raise NanoleafError("weg")
        return self.effect

    def select_effect(self, name):
        if self.fail:
            raise NanoleafError("weg")
        self.calls.append(name)
        self.effect = name

    def start_ext(self, version="v1"):
        self.calls.append("EXT")
        self.effect = "*ExtControl*"
        return ("127.0.0.1", 9)

    def effects(self):
        return [{"name": "Aurora", "rhythm": False}, {"name": "Beat", "rhythm": True}]


def wait_for(cond, s=3.0):
    end = time.time() + s
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ---- Effektliste ------------------------------------------------------------------------------------------------
cl = Client("127.0.0.1", "t")
cl._req = lambda m, p, b=None: ["Aurora", "*Solid*", "Beat", 5] if m == "GET" else {"animations": [{"animName": "Beat", "pluginType": "rhythm"}, {"animName": "Aurora", "pluginType": "color"}]}
check(cl.effects() == [{"name": "Aurora", "rhythm": False}, {"name": "Beat", "rhythm": True}], "Effektliste: ohne interne Namen, Akustik-Effekte markiert")


def no_details(m, p, b=None):
    if m == "GET":
        return ["Aurora"]
    raise NanoleafError("x")


cl._req = no_details
check(cl.effects() == [{"name": "Aurora", "rhythm": False}], "ohne Zusatzangaben bleibt die Liste brauchbar")

# ---- Sender: Umschalten -------------------------------------------------------------------------------------------
snd = NanoleafSender({"host": "127.0.0.1", "token": "t", "port": 1, "panels": [{"id": 1}]})
snd.client = fake = FakeClient()
check(wait_for(lambda: snd.dest is not None, 10.0), "Sender: Streaming laeuft")   # Windows: abgelehnte Verbindung dauert ~2 s
t0 = time.time()
snd.set_effect("Aurora")
check(time.time() - t0 < 0.05, "set_effect wartet nie, die Show laeuft weiter")
check(wait_for(lambda: fake.effect == "Aurora"), "Effekt wird am Geraet gewaehlt")
check(snd.dest is None, "waehrend des Effekts keine Einzelpanels")
sent = []
snd.sock = type("S", (), {"sendto": lambda self, *x: sent.append(x), "close": lambda self: None})()
snd.send(bytes(512))
check(not sent, "send schweigt, solange der Effekt laeuft")
n = len(fake.calls)
time.sleep(0.4)
check(len(fake.calls) == n, "der Effekt wird nicht staendig neu gesendet")
snd.set_effect(None)
check(wait_for(lambda: fake.effect == "*ExtControl*" and snd.dest is not None), "zurueck zu den Einzelpanels")
check(snd.prev_effect == "Forest", "der Effekt vor der Show bleibt zum Wiederherstellen gemerkt")
snd.set_effect("Beat")
wait_for(lambda: fake.effect == "Beat")
snd.pause()
check(wait_for(lambda: snd.effect_on is None and fake.effect == "Forest"), "Ausgabe aus: Panels frei, voriger Effekt zurueck")
calls = list(fake.calls)
time.sleep(0.3)
check(fake.calls == calls, "Ausgabe aus: kein Effekt mehr gesendet")
snd.resume()
snd.set_effect(None)
snd.client = FakeClient()
snd._run = False

# ---- Show-Format ---------------------------------------------------------------------------------------------------
rig, sh = build(strobe=True)
for i in range(3):
    nano = Fixture(f"nano_{i}", "nanoleaf_panel", {"channels": 3, "map": {"r": 1, "g": 2, "b": 3}}, 1 + 3 * i, "nano", target="nanoleaf:10.0.0.1", extra={"nr": 100 + i, "label": f"Panel {i}", "x": i / 3})
    rig.fixtures.append(nano)
    rig.by_name[nano.name] = nano
sh.nano = [(f, 0) for f in rig.fixtures if f.type == "nanoleaf_panel"]
check("nano_fx" in [x["attr"] for x in fm.attrs_for(rig.by_name["nano_0"])], "Nanoleaf hat die Spur Effekt")
check("nano_fx" not in [x["attr"] for x in fm.attrs_for(rig.by_name["vega"])], "andere Geraete nicht")
check(pt.clean_params("nano_effect", {"nano_effect": "Aurora", "x": 1}) == {"nano_effect": "Aurora"}, "Name des Effekts bleibt, Fremdes faellt weg")
d = tl.new_show("N")
d.update(duration=60.0, bpm=120.0, tracks=[{"target": {"group": "rig_nano"}, "attr": "nano_fx", "keys": [{"t": 0, "v": 9}], "clips": [{"t": 2, "d": 4, "pattern": "nano_effect", "p": {"nano_effect": "Aurora"}}, {"t": 10, "d": 4, "pattern": "nano_effect", "p": {}}]},
                                           {"target": {"group": "rig_nano"}, "attr": "dimmer", "keys": [{"t": 0, "v": 200, "e": "constant"}], "clips": []}])
n = tl.normalize(d)
check(n["tracks"][0]["keys"] == [], "Effekt-Spur nur mit Clips")
c = tl.compile_show(n, rig)
check(not c.warnings and c.nano_effect_at(3.0) == "Aurora" and c.nano_effect_at(1.0) is None and c.nano_effect_at(6.5) is None, "Show kennt den Effekt zur Zeit")
check(c.nano_effect_at(11.0) is None, "Clip ohne gewaehlten Effekt: Einzelpanels")
state = c.evaluate(3.0)
check("nano_fx" not in state.get("nano_0", {}), "der Effekt ist kein Wert im Bild")
try:
    tl.compile_show(dict(n, tracks=[{"target": {"fixture": "vega"}, "attr": "nano_fx", "keys": [], "clips": [{"t": 0, "d": 2, "pattern": "nano_effect", "p": {"nano_effect": "X"}}]}]), rig)
    w = tl.compile_show(dict(n, tracks=[{"target": {"fixture": "vega"}, "attr": "nano_fx", "keys": [], "clips": [{"t": 0, "d": 2, "pattern": "nano_effect", "p": {"nano_effect": "X"}}]}]), rig)
    check(w.warnings and w.nano_cues == [], "auf anderem Geraet: verworfen, mit Warnung")
except ValueError:
    check(False, "auf anderem Geraet: verworfen, mit Warnung")

# ---- Show: Wahl des Effekts, BLACKOUT geht vor --------------------------------------------------------------------------
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_nfx_"))
sets = []


class Snd:
    client = FakeClient()

    def set_effect(self, name):
        sets.append(name)


sh.output = type("O", (), {"senders": {"nanoleaf:10.0.0.1": Snd()}, "set_enabled": lambda self, *a, **k: None, "notify": lambda self: None})()
ck = Clock(sh)
e = mgr.engine
e.load(n)
e.play(ck.t, 2.5, True, None)
ck.run(0.1)
check(sets == ["Aurora"], f"Show waehlt den Effekt einmal: {sets}")
ck.run(0.5)
check(sets == ["Aurora"], "nicht in jedem Bild neu")
sh.override = "blackout"
ck.run(0.1)
check(sets[-1] is None, "BLACKOUT: sofort zurueck zu den Einzelpanels (dunkel)")
sh.override = None
ck.run(0.1)
check(sets[-1] == "Aurora", "nach BLACKOUT wieder der Effekt")
sh.freeze = True
ck.run(0.1)
check(sets[-1] is None, "FREEZE: kein Effekt")
sh.freeze = False
ck.run(0.1)
e.pause(ck.t)
ck.run(0.1)
check(sets[-1] is None, "Pause: kein Effekt")
e.play(ck.t, 2.5, True, None)
ck.run(0.1)
check(sets[-1] == "Aurora", "weiter")
e.stop(ck.t)
ck.run(0.1)
check(sets[-1] is None, "Stop: wieder Einzelpanels")

# ---- Assistent: ab und zu ------------------------------------------------------------------------------------------------
check([x["name"] for x in mgr.nano_effects()] == ["Aurora", "Beat"], "Liste kommt vom Geraet")
meta = mgr.meta()
check(meta["params"]["nano_effect"]["options"] == [["Aurora", "Aurora"], ["Beat", "Beat ♫"]] and meta["params"]["nano_effect"]["unit"] == "select", "Auswahl im Editor, Akustik-Effekte markiert")
Snd.client = type("X", (), {"effects": lambda self: 1 / 0})()
mgr.nano_fx_t = -1e9
check(mgr.nano_effects() == [], "Geraet antwortet nicht: keine Effekte, kein Absturz")
Snd.client = FakeClient()
mgr.nano_fx_t = -1e9
doc = tl.new_show("A")
doc.update(bpm=120.0, duration=300.0, marks={"se": [["main", 0.0, 300.0]], "cu": [], "ev": [], "en": [], "lvl": None, "genre": "", "title": "", "fp": ""})
OPT = {"laser": False, "fog": False, "strobe": False, "move": False, "ambient": False, "seed": 2}
new = a.suggest(doc, meta, {**OPT, "effects": ["Aurora", "Beat"]}, None)[0]
fx = [x for t in new["tracks"] if t["attr"] == "nano_fx" for x in t["clips"]]
dimmer = [x for t in new["tracks"] if t["attr"] == "dimmer" and t["target"].get("group") == "rig_nano" for x in t["clips"]]
check(fx and all(x["p"]["nano_effect"] in ("Aurora", "Beat") for x in fx) and fx[0]["label"], "Vorschlag nutzt die Effekte des Geraets")
check(len(fx) < len(dimmer), f"nur ab und zu: {len(fx)} Effekte, {len(dimmer)} Einsaetze ohne")
check(not [x for x in dimmer for y in fx if x["t"] < y["t"] + y["d"] and y["t"] < x["t"] + x["d"]], "beim Effekt keine Einzelpanels daneben")
tl.normalize(new)
none = a.suggest(doc, meta, {**OPT, "effects": []}, None)[0]
check(not [t for t in none["tracks"] if t["attr"] == "nano_fx"], "ohne Hakerl oder ohne Liste: keine Effekte")
body = a.claude_request(a.direct(a.song_info(doc), "", 0.5, 1), a.song_info(doc), {**OPT, "effects": ["Aurora"]}, "")
check("Aurora" not in json.dumps(body), "die Effektnamen gehen nicht an Claude")

# ---- AUTO: Geraete der Reihe nach --------------------------------------------------------------------------------------
rig2, sh2 = build(strobe=False)
check(sh2.cfg["auto_solo"] == 0.0, "Standard: aus, AUTO wie immer")
ck2 = Clock(sh2)
ck2.run(8.0)
check(all(f.level == 1.0 for f in rig2.fixtures), "aus: alle Gruppen wie immer")
sh2.cfg.set("auto_solo", 1.0)
sh2.state = "normal"
seen = set()
ck2.run(40.0, lambda t: seen.add(sh2._auto_solo_key(False)) if sh2.state == "normal" else None)
check(len(seen - {None}) >= 3, f"die Gruppen wechseln sich ab: {seen}")
sh2.state = "normal"
key = sh2._auto_solo_key(False)
check(key in ("spot", "bar", "fx", "wash"), "ohne Nanoleaf bleibt es aus der Reihe")
i0 = sh2.solo_i
sh2.solo_i = i0
sh2.update(ck2.t + 0.025)
ck2.t += 0.025
if sh2.state == "normal":
    key = sh2._auto_solo_key(False)
    lv = {f.name: f.level for f in rig2.fixtures}
    check(lv["vega"] == (1.0 if key == "spot" else 0.0) and lv["rgbuv_7"] == (1.0 if key == "wash" else 0.0) and lv["uv_bar"] == 0.0 and lv["par"] == 1.0, f"nur die Gruppe {key} leuchtet, das Ambiente bleibt")
for st in ("drop", "idle", "gap"):
    sh2.state = st
    check(sh2._auto_solo_key(False) is None, f"bei {st}: alle wie immer")
sh2.state = "normal"
check(sh2._auto_solo_key(True) is None, "waehrend einer Show ohne Wirkung")
sh2.override = "blackout"
check(sh2._auto_solo_key(False) is None, "BLACKOUT geht vor")
sh2.override = None
sh2.sc = object()
check(sh2._auto_solo_key(False) is None, "Szene: ohne Wirkung")
sh2.sc = None
sh2.cfg.set("auto_solo", 0.0)
os.environ.pop("X", None)
finish("test_nanoleaf_effekte")
