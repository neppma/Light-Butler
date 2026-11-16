"""ROLI LUMI Keys als zweite Bedienung: eigene Belegung, keine LEDs und Fader, kein Laser, Strobe oder Nebel, eigener
UDP-Port neben dem APC. Echte UDP-Pakete ueber localhost, Lumi und mido nachgebaut."""
import json
import os
import socket
import sys
import tempfile
import time
import types

from _common import ROOT, build, check, finish

fake = types.ModuleType("mido")


class Message:
    def __init__(self, type, channel=0, note=0, velocity=0, control=0, value=0, raw=None):
        self.type, self.channel, self.note, self.velocity, self.control, self.value = type, channel, note, velocity, control, value
        self.raw = raw

    @classmethod
    def from_bytes(cls, b):
        st, d1, d2 = b[0], b[1], b[2]
        if st & 0xF0 == 0xB0:
            return cls("control_change", st & 15, control=d1, value=d2)
        return cls("note_on" if st & 0xF0 == 0x90 else "note_off", st & 15, note=d1, velocity=d2)

    def bytes(self):
        if self.raw:
            return list(self.raw)
        if self.type == "control_change":
            return [0xB0 | self.channel, self.control, self.value]
        return [(0x90 if self.type == "note_on" else 0x80) | self.channel, self.note, self.velocity]


class Port:
    def __init__(self):
        self.queue, self.sent = [], []

    def iter_pending(self):
        q, self.queue = self.queue, []
        return iter(q)

    def send(self, m):
        self.sent.append(m.bytes())

    def close(self):
        pass


NAME = "LUMI Keys BLOCK"
LUMI = {"in": Port(), "out": Port()}
fake.Message = Message
fake.get_input_names = lambda: []
fake.get_output_names = lambda: []
sys.modules.setdefault("mido", fake)
mac_mido = types.SimpleNamespace(Message=Message, get_input_names=lambda: [NAME, "IAC-Treiber Bus 1"],
                                 get_output_names=lambda: [NAME, "IAC-Treiber Bus 1"],
                                 open_input=lambda n: LUMI["in"], open_output=lambda n: LUMI["out"])

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from apc_relay import ApcRelay, lumi_relay                                     # noqa: E402
from lumi_ctl import BLACK, BASE_NOTE, COLORS, WHITE, LumiController, allowed, default_map, load_map, lumi_scenes  # noqa: E402
from midi_ctl import MIX_ORDER, MOVE_ORDER, MidiController                     # noqa: E402
from midi_net import NetMidi                                                   # noqa: E402


def wait(cond, sec=2.0):
    end = time.time() + sec
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


# ---- Standardbelegung ----------------------------------------------------------------------------------------------
m = default_map()["keys"]
acts = list(m.values())
check(all(allowed(a) for a in acts), "Standardbelegung erfuellt die eigene Pruefung")
check(all(any(a.get("color") == c for a in acts) for c in COLORS), "alle Farben belegt")
check(all(any(a.get("move") == x for a in acts) for x in MOVE_ORDER), "alle Bewegungen belegt")
check(all(any(a.get("mix") == x for a in acts) for x in MIX_ORDER), "alle Licht-Mixe belegt")
check(BASE_NOTE == 36 and m["36"] == {"color": "rot"} and m["59"] == {"cmd": "blackout"},
      "gemessene Grundstellung 36 bis 59: tiefste Taste Rot, hoechste Blackout")
check(all((int(n) - BASE_NOTE) % 12 in WHITE for n, a in m.items() if "color" in a or "move" in a or "mix" in a),
      "Farben, Bewegung und Licht-Mix liegen auf weissen Tasten")
check(all((int(n) - BASE_NOTE) % 12 in BLACK for n, a in m.items() if "scene_index" in a), "Szenen liegen auf schwarzen Tasten")
check(len([a for a in acts if "scene_index" in a]) == 20, "20 Szenen belegt")

# ---- Sicherheit: kein Laser, Strobe, Nebel ---------------------------------------------------------------------------
for bad in ({"cmd": "laser"}, {"cmd": "blitz"}, {"cmd": "fog"}, {"cmd": "page1"}, {"mix": "Strobo"}, {"fader": "master"},
            {"color": "rot", "cmd": "fog"}, "fog", None):
    check(not allowed(bad), f"nicht erlaubt: {bad}")
check(not any(a.get("cmd") in ("laser", "blitz", "fog") for a in acts), "Standard ohne Laser, Strobe und Nebel")

rig, sh = build(seed=3)
ok = lumi_scenes(sh.scene_defs)
check(ok and not any(s.special or s.mix in ("strobe", "lightning") for s in ok),
      "Szenen ohne Laser, Strobo, Gewitter, All off, Reset und Ziele")

path = os.path.join(tempfile.mkdtemp(prefix="s2l_lumi_"), "lumimap.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump({"base_note": 48, "keys": {"40": {"cmd": "fog"}, "41": {"cmd": "laser"}, "42": {"color": "uv"}, "48": None, "50": None}}, f)
um, err = load_map(path)
check("40" not in um["keys"] or um["keys"]["40"].get("cmd") != "fog", "Nebel aus lumimap.json wird nicht uebernommen")
check(um["keys"].get("41", {}).get("cmd") != "laser", "Laser aus lumimap.json wird nicht uebernommen")
check(um["keys"]["42"] == {"color": "uv"} and "48" not in um["keys"] and "50" not in um["keys"] and "Note 40, 41" in err,
      "Rest gilt, Fehler wird gemeldet")
check(um["keys"]["52"] == {"color": "gelb"}, "base_note verschiebt die Standardbelegung")
with open(path, "w", encoding="utf-8") as f:
    f.write("kaputt")
check(load_map(path)[1].startswith("lumimap.json nicht lesbar") and load_map(path)[0]["keys"]["36"] == {"color": "rot"},
      "kaputte Datei: Standard und Meldung")

# ---- Tasten wirken wie gedacht ---------------------------------------------------------------------------------------
lc = LumiController(sh, map_path=None)
calls = []
orig = sh.command
sh.command = lambda d: (calls.append(d), orig(d))[1]


def press(note, on=True):
    calls.clear()
    lc.handle(Message("note_on" if on else "note_off", channel=3, note=note, velocity=90 if on else 0))
    return list(calls)


check(press(36) == [{"color_toggle": "rot"}], "Taste 36 waehlt Rot, auch auf einem anderen MIDI-Kanal (MPE)")
check(press(59) == [{"hold": {"name": "blackout", "on": True}}], "Blackout: Taster an")
check(press(59, False) == [{"hold": {"name": "blackout", "on": False}}], "Blackout: Taster los")
sh.command({"hold": {"name": "blackout", "on": False}})
check(press(0) == [] and press(20) == [], "Noten ausserhalb der Belegung wirken nicht, keine APC-Pads")
check(press(49) == [{"scene": ok[0].name}], "schwarze Taste: erste erlaubte Szene")
lc.map["keys"]["108"] = {"scene": "Laser"}
check(press(108) == [], "Szene Laser ist auch mit Namen nicht ausloesbar")
calls.clear()
lc.handle(Message("control_change", control=48, value=64))
check(calls == [], "Regler vom Lumi wirkt nicht (kein Fader)")

# ---- Autopilot gilt auch hier ----------------------------------------------------------------------------------------
sh.sc, sh.auto_colors, sh.auto_color = None, [], None                 # die Szene von oben wieder weg: Farbe wirkt auf AUTO
press(36)
check(sh.auto_color == "rot" or "rot" in sh.auto_colors, "ohne Autopilot waehlt die Taste die Farbe wirklich")
press(36)
sh.auto_colors, sh.auto_color = [], None
sh.pilot = True
press(36)
check(sh.auto_color is None and not sh.auto_colors, "Autopilot sperrt auch den Lumi")
sh.pilot = False

# ---- Weiterleitung und Verbindung, APC und Lumi gleichzeitig -----------------------------------------------------------
pisock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
pisock.bind(("127.0.0.1", 0))
net = NetMidi(sock=pisock)
net.start()
relay = lumi_relay("127.0.0.1", pisock.getsockname()[1], mido_mod=mac_mido, log=lambda s: None)
relay.start()
check(wait(net.connected) and net.name == NAME, "Pi sieht den Lumi am Mac")
lc.net = net
check(lc._open() and lc.via_net and lc.names == [NAME + " (am Musik-Rechner)"], "Lumi verbindet sich ueber den Mac")
time.sleep(0.2)
check(LUMI["out"].sent == [], "der Pi schickt dem Lumi nichts (keine LEDs)")
apc_only = ApcRelay("127.0.0.1", 9, hint="apc mini mk2", mido_mod=mac_mido, log=lambda s: None, sock=pisock)
check(not apc_only.connect(time.monotonic() + 9) and apc_only.inp is None, "die APC-Weiterleitung greift den Lumi nicht")

LUMI["in"].queue += [Message("control_change", control=74, value=3), Message("poly", raw=[0xA3, 60, 40]),
                     Message("note_on", channel=3, note=36, velocity=90), Message("note_off", channel=3, note=36)]
got = []
wait(lambda: (got.extend(lc.ins[0].iter_pending()) or len(got) >= 2))
check([(x.type, x.note) for x in got] == [("note_on", 36), ("note_off", 36)], "nur Noten gehen zum Pi, kein Regler, kein Druck")
calls.clear()
for x in got:
    lc.handle(x)
check(calls == [{"color_toggle": "rot"}], "Taste vom Mac wirkt am Pi")
relay._run = False

# APC bleibt, wie er war: dieselbe Klasse, gleiche Werte
r = ApcRelay("127.0.0.1", 9021, mido_mod=mac_mido, log=lambda s: None)
check(r.hint == "apc mini mk2" and r.label == "APC" and not r.notes_only, "APC-Weiterleitung unveraendert")
check(MidiController.leds and not LumiController.leds, "nur der APC zeigt LEDs")

# ---- Seite /lumi: Grafik mit allen Tasten -----------------------------------------------------------------------------
import re                                                                      # noqa: E402
import subprocess                                                              # noqa: E402

import lumi_view                                                               # noqa: E402
import webpanel                                                                # noqa: E402

v = lumi_view.state(sh)
byn = {k["note"]: k for k in v["keys"]}
check(v["base"] == 36 and v["windows"] == 3 and v["keys"][-1]["note"] == 107, "drei Seiten, bis alles Belegte zu sehen ist")
check(all(str(k["note"]) in default_map()["keys"] for k in v["keys"] if k["act"]) and
      all(int(n) in byn for n in default_map()["keys"]), "jede belegte Taste steht in der Grafik")
check(not byn[36]["black"] and byn[37]["black"] and byn[36]["color"] == lumi_view.CSS["rot"], "Rot weiss und in echter Farbe, 37 schwarz")
check(byn[59]["kind"] == "blackout" and byn[49]["scene"] == ok[0].name, "Blackout und Szenenname stehen dabei")
check(sum(1 for k in v["keys"] if 36 <= k["note"] < 60) == 24 and sum(1 for k in v["keys"] if 36 <= k["note"] < 60 and not k["black"]) == 14,
      "ein Bild zeigt 24 Tasten, davon 14 weisse")
sh.lumi = None
check(lumi_view.state(sh)["connected"] is False and sh._lumi_view is not None, "Seite geht auch ohne laufenden Lumi")
p = webpanel.make_page()
check('<a class="seclink" href="/lumi">' in p and "body.vlumi>*:not(#lumisec)" in p and '<body class="vlumi">' in webpanel.lumi_page(),
      "eigene Seite /lumi mit Link in den Einstellungen")
check(not re.search(r"\\.(lumt|lumw|lumb|lumn)\\b", p.split("#lumisec{display:none}")[0]) and ".lk{position:absolute" not in p,
      "Klassen der Lumi-Seite aendern keine Bereiche der Hauptseite")
js = p.split("<script>")[-1].split("</script>")[0]
jsf = os.path.join(tempfile.mkdtemp(prefix="s2l_lumi_"), "p.js")
with open(jsf, "w", encoding="utf-8") as f:
    f.write(js)
check(subprocess.run(["node", "--check", jsf], capture_output=True).returncode == 0, "Skript des Panels ist gueltig")

# ---- Umbelegen im Panel ----------------------------------------------------------------------------------------------
mp = os.path.join(tempfile.mkdtemp(prefix="s2l_lumi_"), "lumimap.json")
sh._lumi_view = LumiController(sh, map_path=mp)
sh.lumi = None
orig({"lumi_key": {"note": 36, "act": {"color": "blau"}}})
check(sh._lumi_view.map["keys"]["36"] == {"color": "blau"} and load_map(mp)[0]["keys"]["36"] == {"color": "blau"}, "Umbelegen wirkt sofort und bleibt gespeichert")
orig({"lumi_key": {"note": 38, "act": None}})
check("38" not in sh._lumi_view.map["keys"], "Taste freigeben")
for bad_act in ({"cmd": "fog"}, {"cmd": "laser"}, {"cmd": "blitz"}):
    try:
        sh._lumi_view.set_key(40, bad_act)
        check(False, f"abgelehnt: {bad_act}")
    except ValueError:
        check(sh._lumi_view.map["keys"]["40"] == {"color": "gelb"}, f"abgelehnt: {bad_act}")
orig({"lumi_reset": True})
check(sh._lumi_view.map["keys"]["36"] == {"color": "rot"} and sh._lumi_view.map["keys"]["38"] == {"color": "orange"}, "Standard wiederhergestellt")
with open(mp, "w", encoding="utf-8") as f:
    f.write("kaputt")
try:
    sh._lumi_view.set_key(36, None)
    check(False, "kaputte Datei wird nicht ueberschrieben")
except ValueError:
    check(open(mp, encoding="utf-8").read() == "kaputt", "kaputte Datei wird nicht ueberschrieben")
check("fog" not in lumi_view.state(sh)["options"]["cmd"], "Liste ohne Nebel")

# ---- Lumi-Programm: passt zur Belegung -----------------------------------------------------------------------------------
import lumi_program                                                            # noqa: E402

src = lumi_program.program(default_map()["keys"])
check('href="/lumi/LightButler.littlefoot" download=' in p, "Download-Knopf auf der Seite /lumi")
check("colours[12] = 0xffd62020;" in src, "Note 36 in Rot wie in der Grafik")
check(src.count("colours[") - 3 == len(default_map()["keys"]), "jede belegte Taste hat eine Farbe")
check("currentOctave + 2);" in src and "currentOctave - 2);" in src, "Pfeile springen zwei Oktaven")
check(src.count("{") == src.count("}") and all(w in src for w in ("sendNoteOn", "sendNoteOff", "deassignChannel")),
      "Programm sendet weiter Noten")

finish("ROLI LUMI Keys")
