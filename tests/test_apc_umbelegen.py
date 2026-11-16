"""APC mini: Tasten und Fader im Panel umbelegen. Gespeichert in midimap.json, jede erlaubte Belegung laesst LEDs und Seite heil."""
import json
import os
import sys
import tempfile
import types

from _common import build, check, finish

fake = types.ModuleType("mido")                                # LEDs ohne Geraet: nichts wird gesendet
fake.Message = lambda *a, **k: None
sys.modules.setdefault("mido", fake)

import apc_view
from midi_ctl import MidiController, load_map, valid_action, valid_key

rig, sh = build(seed=3)
mp = os.path.join(tempfile.mkdtemp(prefix="s2l_apc_"), "midimap.json")
with open(mp, "w", encoding="utf-8") as f:
    json.dump({"palette": {"rot": 6}}, f)
mc = MidiController(sh, mp)
sh._apc_view = mc

sh.command({"apc_key": {"sec": "pads1", "key": 56, "act": {"color": "blau"}}})
check(mc.map["pads1"]["56"] == {"color": "blau"} and load_map(mp)[0]["pads1"]["56"] == {"color": "blau"}, "Pad wirkt sofort und bleibt gespeichert")
sh.command({"apc_key": {"sec": "buttons", "key": 112, "act": None}})
check("112" not in mc.map["buttons"], "Taste freigeben")
sh.command({"apc_key": {"sec": "faders", "key": 48, "act": {"fader": "master"}}})
check(mc.map["faders"]["48"] == {"fader": "master"}, "Fader umbelegen")
check(json.load(open(mp, encoding="utf-8"))["palette"] == {"rot": 6}, "Farbtabelle bleibt in der Datei")

check(not valid_key("buttons", 122) and not valid_key("pads1", 64) and not valid_key("faders", 57) and not valid_key("x", 1), "SHIFT und erfundene Tasten nicht")
for sec, bad in (("pads1", {"cmd": "rm"}), ("pads1", {"mix": "Strobo"}), ("pads1", {"fader": "master"}), ("faders", {"color": "rot"}),
                 ("faders", {"fader": "group", "group": "laser"}), ("pads1", {"color": "rot", "cmd": "fog"}), ("pads1", {"hw_unlock": True})):
    check(not valid_action(sec, bad), f"abgelehnt: {sec} {bad}")
    try:
        mc.set_key(sec, 48, bad)
        check(False, "Fehler erwartet")
    except ValueError:
        pass

# jede angebotene Belegung auf Pad und Taste: Seite und LEDs duerfen nicht scheitern
o = apc_view.state(sh)["options"]
acts = [{k: v} for k in ("cmd", "color", "speed", "move", "mix") for v in o[k]] + [{"scene_index": i} for i in range(len(o["scene"]))] + [{"aim": "bank"}]
ok = True
for a in acts:
    check_ok = valid_action("pads1", a)
    ok = ok and check_ok
    mc.map["pads1"]["0"] = a
    mc.map["buttons"]["113"] = a
    apc_view.state(sh)
    mc.refresh_leds(sh.snapshot())
check(ok, "alles Angebotene ist erlaubt, Seite und LEDs bleiben heil")

sh.command({"apc_reset": True})
check(mc.map["pads1"]["56"] == load_map(None)[0]["pads1"]["56"] and "112" in mc.map["buttons"], "Standard wiederhergestellt")
check(json.load(open(mp, encoding="utf-8")) == {"palette": {"rot": 6}}, "nur die Belegung geht weg")

with open(mp, "w", encoding="utf-8") as f:
    f.write("kaputt")
try:
    mc.set_key("pads1", 1, None)
    check(False, "kaputte Datei bleibt")
except ValueError:
    check(open(mp, encoding="utf-8").read() == "kaputt", "kaputte Datei wird nicht ueberschrieben")

finish("test_apc_umbelegen")
