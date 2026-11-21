"""Geraetetypen aus der Open Fixture Library (Wunsch von Markus, 21.11.2026): Umwandlung, Sicherheitsregeln, Speichern als
eigener Typ, Datei-Import (OFL-JSON, QLC+), Abruf mit unechtem Netz. Ohne Internet, in einem Temp-Ordner."""
import io
import json
import os
import shutil
import tempfile
import urllib.error

from _common import PI, check, finish

import fixture_edit as fe                    # noqa: E402
import ofl_import as o                       # noqa: E402
from dmx import Rig, Fixture                 # noqa: E402


def cap(t, **k):
    return dict({"type": t}, **k)


PAR = {"name": "Test PAR 7", "categories": ["Color Changer"],
       "availableChannels": {
           "Dimmer": {"capability": cap("Intensity")},
           "Red": {"capability": cap("ColorIntensity", color="Red")},
           "Green": {"capability": cap("ColorIntensity", color="Green")},
           "Blue": {"capability": cap("ColorIntensity", color="Blue")},
           "White": {"capability": cap("ColorIntensity", color="White")},
           "Shutter": {"capabilities": [cap("ShutterStrobe", dmxRange=[0, 9], shutterEffect="Closed"),
                                        cap("ShutterStrobe", dmxRange=[10, 239], shutterEffect="Strobe"),
                                        cap("ShutterStrobe", dmxRange=[240, 255], shutterEffect="Open")]},
           "Program": {"capabilities": [cap("NoFunction", dmxRange=[0, 7]), cap("Effect", dmxRange=[8, 200], effectName="Auto"),
                                        cap("SoundSensitivity", dmxRange=[201, 255])]},
           "Speed": {"capability": cap("Speed")}},
       "modes": [{"name": "7-Kanal", "shortName": "7ch", "channels": ["Dimmer", "Red", "Green", "Blue", "White", "Shutter", "Program"]},
                 {"name": "Nur Rot", "channels": ["Red", "Speed"]}]}
t, notes = o.convert(PAR, 0, "testmaker")
fe.check_import(t)
m = t["map"]
check([k for k, _ in sorted(m.items(), key=lambda x: x[1])][:5] == ["dimmer", "r", "g", "b", "w"], "Dimmer und Farben erkannt: %s" % m)
check(t["safe_limits"]["shutter"] == [240, 255] and t["defaults"]["shutter"] == 255, "Shutter fest auf offen (nie Strobo)")
check(t["safe_limits"]["x_program"] == [0, 7], "Programm-/Sound-Kanal fest auf keine Funktion")
check(t["defaults"]["dimmer"] == 255, "Farbgeraet: Dimmer steht auf voll")
check(fe.allowed_groups("", t)[0] == "wash", "Gruppe Wash vorgeschlagen")
t2, n2 = o.convert(PAR, 1, "")
check("r" not in t2["map"] and any("Rot, Gruen, Blau" in x for x in n2), "Nur ein Farbkanal: unbenutzt mit Hinweis")
check("x_speed" in t2["map"] and "x_speed" not in (t2.get("safe_limits") or {}), "reiner Tempo-Kanal bleibt frei")

# Strobe ohne bekannten Ruhewert: fest auf 0 mit Hinweis
ST = {"name": "S", "categories": ["Strobe"], "availableChannels": {"Dimmer": {"capability": cap("Intensity")},
      "Strobe": {"capability": cap("ShutterStrobe", shutterEffect="Strobe")}}, "modes": [{"name": "2", "channels": ["Dimmer", "Strobe"]}]}
ts, ns = o.convert(ST, 0)
check(ts["safe_limits"]["strobe"] == [0, 0] and any("Strobo" in x for x in ns), "Strobe ohne Ruhewert: fest 0, Hinweis")

# Laser, Hazer, Derby mit Laser
LAS = {"name": "Laser X", "categories": ["Laser"], "availableChannels": {"Mode": {"capability": cap("Generic")},
       "Pattern": {"capability": cap("Effect")}}, "modes": [{"name": "2", "channels": ["Mode", "Pattern"]}]}
tl, nl = o.convert(LAS, 0)
check(tl.get("locked") is True and fe.allowed_groups("", tl) == ["locked"] and "laser_channels" not in tl, "Laser: ganzer Typ gesperrt, keine Freigabe")
HZ = {"name": "Hazer", "categories": ["Hazer"], "availableChannels": {"Haze": {"capability": cap("FogOutput")}},
      "modes": [{"name": "1", "channels": ["Haze"]}]}
th, _ = o.convert(HZ, 0)
check(th.get("locked") is True and "manual_allowed" not in th and "burst" not in th, "Hazer gesperrt, kein Handbetrieb")
DER = {"name": "Derby", "categories": ["Color Changer", "Laser"], "availableChannels": {
       "Red": {"capability": cap("ColorIntensity", color="Red")}, "Green": {"capability": cap("ColorIntensity", color="Green")},
       "Blue": {"capability": cap("ColorIntensity", color="Blue")}, "Red Laser": {"capability": cap("Intensity")},
       "Laser Strobe": {"capability": cap("ShutterStrobe", shutterEffect="Strobe")}},
       "modes": [{"name": "5", "channels": ["Red", "Green", "Blue", "Red Laser", "Laser Strobe"]}]}
td, _ = o.convert(DER, 0)
check(not td.get("locked") and sorted(td["locked_channels"]) == ["x_laser_strobe", "x_red_laser"] and "dimmer" not in td["map"],
      "Derby mit Laser: nur die Laser-Kanaele gesperrt")

# Moving Head mit Farb- und Goborad, feine Kanaele
MH = {"name": "Spot", "categories": ["Moving Head"],
      "wheels": {"Color Wheel": {"slots": [{"type": "Open"}, {"type": "Color", "colors": ["#ff0000"]}, {"type": "Color", "colors": ["#0000ff"]}]},
                 "Gobo Wheel": {"slots": [{"type": "Open"}, {"type": "Gobo"}, {"type": "Gobo"}]}},
      "availableChannels": {
          "Pan": {"fineChannelAliases": ["Pan fine"], "capability": cap("Pan")},
          "Tilt": {"fineChannelAliases": ["Tilt fine"], "capability": cap("Tilt")},
          "Dimmer": {"capability": cap("Intensity")},
          "Color Wheel": {"capabilities": [cap("WheelSlot", dmxRange=[0, 9], slotNumber=1), cap("WheelSlot", dmxRange=[10, 19], slotNumber=2),
                                           cap("WheelSlot", dmxRange=[20, 29], slotNumber=3), cap("WheelRotation", dmxRange=[30, 255])]},
          "Gobo Wheel": {"capabilities": [cap("WheelSlot", dmxRange=[0, 9], slotNumber=1), cap("WheelSlot", dmxRange=[10, 19], slotNumber=2),
                                          cap("WheelSlot", dmxRange=[20, 29], slotNumber=3), cap("WheelShake", dmxRange=[30, 255])]},
          "Reset": {"capabilities": [cap("NoFunction", dmxRange=[0, 9]), cap("Maintenance", dmxRange=[10, 255])]}},
      "modes": [{"name": "9", "channels": ["Pan", "Pan fine", "Tilt", "Tilt fine", "Dimmer", "Color Wheel", "Gobo Wheel", "Reset"]}]}
tm, nm = o.convert(MH, 0)
fe.check_import(tm)
check(all(k in tm["map"] for k in ("pan", "pan_fine", "tilt", "tilt_fine", "colorwheel", "gobo")), "Moving Head: Pan/Tilt fein, Raeder")
check(tm["presets"]["colorwheel"]["red"] == 14 and tm["presets"]["colorwheel"]["blue"] == 24 and tm["presets"]["colorwheel"]["green"] == 4,
      "Farbrad: Faecher nach Farbe, fehlende Farbe = offen")
check(tm["presets"]["gobo"]["open"] == 4 and tm["presets"]["gobo"]["star"] == 14, "Goborad: offen und Gobos")
check(tm["safe_limits"]["x_reset"] == [0, 9] and fe.allowed_groups("", tm) == ["spot"], "Reset fest aus, Gruppe Moving Head")

# Matrix: Pixel-Leiste mit Vorlagen
PX = {"name": "Bar", "categories": ["Pixel Bar"], "matrix": {"pixelCount": [3, 1, 1], "pixelGroups": {"Master": "all"}},
      "availableChannels": {"Dimmer": {"capability": cap("Intensity")}},
      "templateChannels": {"Red $pixelKey": {"capability": cap("ColorIntensity", color="Red")},
                           "Green $pixelKey": {"capability": cap("ColorIntensity", color="Green")},
                           "Blue $pixelKey": {"capability": cap("ColorIntensity", color="Blue")}},
      "modes": [{"name": "3", "channels": ["Red Master", "Green Master", "Blue Master"]},
                {"name": "10", "channels": [{"insert": "matrixChannels", "repeatFor": "eachPixelXYZ", "channelOrder": "perPixel",
                                             "templateChannels": ["Red $pixelKey", "Green $pixelKey", "Blue $pixelKey"]}, "Dimmer"]}]}
check([x["channels"] for x in o.modes(PX)] == [3, 10], "Matrix-Modi werden aufgeloest")
tp, _ = o.convert(PX, 1)
check(tp["map"]["r1"] == 1 and tp["map"]["b3"] == 9 and tp["map"]["dimmer"] == 10, "drei Zellen r1 .. b3")
check(o.convert(PX, 0)[0]["map"] == {"r": 1, "g": 2, "b": 3}, "Master-Kanaele aus Vorlagen")
import webpanel                              # noqa: E402
check(webpanel.ofl_preview(PX, "", -1)["mode"] == 1 and webpanel.ofl_preview(PAR, "", -1)["mode"] == 0,
      "ohne Wahl ist der groesste moegliche Modus vorgewaehlt")
check(webpanel.ofl_preview(PX, "", 0)["type"]["channels"] == 3, "gewaehlter Modus gilt")
fx = Fixture("bar", "t", dict(tp, custom=True), 1, "wash")
check(len(fx.zones()) == 3, "Licht kennt alle drei Zellen")
fx.set_color(r=200, g=0, b=0)
buf = bytearray(512)
fx.write(buf)
check(list(buf[:10]) == [200, 0, 0, 200, 0, 0, 200, 0, 0, 255], "alle Zellen leuchten, Dimmer voll")

# Sicherheit beim Schreiben: gesperrter Typ 0, Shutter nie Strobo, Programm nie an
fl = Fixture("l", "t", dict(tl, custom=True), 1, "locked")
fl.values = {p: 200 for p in fl.map}
buf = bytearray(512)
fl.write(buf)
check(max(buf) == 0, "gesperrter Laser-Typ sendet immer 0")
fp = Fixture("p", "t", dict(t, custom=True), 1, "wash")
fp.set("shutter", 100)
fp.set("x_program", 150)
fp.preset("colorwheel", "red")                           # fehlendes Rad: kein Absturz
buf = bytearray(512)
fp.write(buf)
check(buf[5] == 240 and buf[6] == 7, "Shutter und Programm bleiben in ihren Grenzen")

# check_import lehnt gefaehrliche Felder ab
for bad in ({"laser_channels": ["x"]}, {"manual_allowed": True}, {"hw_strobe": {"param": "strobe"}}, {"rest_values": {"x": 1}}, {"locked": False}):
    try:
        fe.check_import(dict(tm, **bad))
        check(False, "abgelehnt: %s" % list(bad))
    except ValueError:
        check(True, "abgelehnt: %s" % list(bad))

# QLC+-Datei
QXF = """<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="http://www.qlcplus.org/FixtureDefinition">
 <Manufacturer>Muster</Manufacturer><Model>Par Q</Model><Type>Color Changer</Type>
 <Channel Name="Dimmer" Preset="IntensityMasterDimmer"/>
 <Channel Name="Red" Preset="IntensityRed"/><Channel Name="Green" Preset="IntensityGreen"/><Channel Name="Blue" Preset="IntensityBlue"/>
 <Channel Name="Strobe"><Group Byte="0">Shutter</Group><Capability Min="0" Max="9" Preset="ShutterOpen">Open</Capability>
  <Capability Min="10" Max="255">Strobe slow to fast</Capability></Channel>
 <Channel Name="Mode"><Group Byte="0">Effect</Group><Capability Min="0" Max="15">No function</Capability>
  <Capability Min="16" Max="255">Auto programs</Capability></Channel>
 <Mode Name="6 Channel"><Channel Number="0">Dimmer</Channel><Channel Number="1">Red</Channel><Channel Number="2">Green</Channel>
  <Channel Number="3">Blue</Channel><Channel Number="4">Strobe</Channel><Channel Number="5">Mode</Channel></Mode>
</FixtureDefinition>"""
qf, qm = o.read_file(QXF)
tq, _ = o.convert(qf, 0, qm)
check(qm == "Muster" and [p for p, _ in sorted(tq["map"].items(), key=lambda x: x[1])][:4] == ["dimmer", "r", "g", "b"], "QLC+: Kanaele erkannt")
check(tq["safe_limits"]["strobe"] == [0, 9] and tq["safe_limits"]["x_mode"] == [0, 15], "QLC+: Strobe offen, Mode ohne Programm")
for bad in ("<!DOCTYPE x [<!ENTITY a 'b'>]><x/>", "kein json", json.dumps({"name": "x"})):
    try:
        o.read_file(bad)
        check(False, "kaputte Datei abgelehnt")
    except ValueError:
        check(True, "kaputte Datei abgelehnt")
fj, _ = o.read_file(json.dumps(PAR))
check(fj["name"] == "Test PAR 7", "OFL-Datei gelesen")

# Speichern als eigener Typ, Bearbeiten im Typ-Editor behaelt die Sperren
tmp = tempfile.mkdtemp()
shutil.copy(os.path.join(PI, "fixtures.yaml"), tmp)
rig = Rig(os.path.join(tmp, "fixtures.yaml"))
name, nn = fe.cmd_type_import(rig, {"fixture": PAR, "mode": 0, "maker": "testmaker", "source": "ofl:testmaker/test-par-7"})
check(name.startswith("ofl_testmaker") and rig.user["types"][name]["ofl"] == "ofl:testmaker/test-par-7", "Typ gespeichert: " + name)
nl_name, _ = fe.cmd_type_import(rig, {"fixture": LAS, "mode": 0})
cat = {x["name"]: x for x in fe.type_summary(fe.apply_user(rig.base_cfg, rig.user))}
check(cat[nl_name]["groups"] == ["locked"], "Laser-Typ nur als gesperrt waehlbar")
edit = {"name": nl_name, "channels": [{"param": "x_mode"}, {"param": "x_pattern"}]}
fe.cmd_type_save(rig, edit)
check(rig.user["types"][nl_name].get("locked") is True, "Bearbeiten im Typ-Editor: Laser bleibt gesperrt")
edit = {"name": name, "channels": [{"param": p, "max": 255} for p, _ in sorted(rig.user["types"][name]["map"].items(), key=lambda x: x[1])]}
fe.cmd_type_save(rig, edit)
check(rig.user["types"][name]["safe_limits"]["shutter"] == [240, 255], "Bearbeiten im Typ-Editor: Shutter bleibt offen")
fe.cmd_fixture_save(rig, {"new": True, "type": name, "label": "PAR aus OFL", "nr": 30, "address": 461, "group": "wash"})
rig2 = Rig(os.path.join(tmp, "fixtures.yaml"))
check("par_aus_ofl" in rig2.by_name and rig2["par_aus_ofl"].n == 7, "nach dem Neustart: Fixture mit importiertem Typ")
mh_name, _ = fe.cmd_type_import(rig, {"fixture": MH, "mode": 0, "maker": "testmaker"})
fe.cmd_fixture_save(rig, {"new": True, "type": mh_name, "label": "Spot OFL", "nr": 31, "address": 470, "group": "spot"})
import show as sw                            # noqa: E402
from _common import Clock                    # noqa: E402
from audio import Simulator                  # noqa: E402
rig3 = Rig(os.path.join(tmp, "fixtures.yaml"))
sh = sw.Show(rig3, Simulator(), aim_file=os.devnull, strobe=False, settings_file=None, scenes_file=None, texts_file=None, genre_file=None)
check(rig3["spot_ofl"] in sh.spot and rig3["vega"] in sh.spot, "importierter Moving Head laeuft in AUTO mit")
seen = set()
Clock(sh).run(20, lambda t: seen.add(rig3.render_all()[rig3.target][469 + rig3["spot_ofl"].map["dimmer"] - 1]))
check(max(seen) > 0, "importierter Moving Head leuchtet in AUTO")
shutil.rmtree(tmp)


# Abruf der Datenbank mit unechtem Netz (nur erlaubte Pfade, Zwischenspeicher)
class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


calls = []


def opener(req, timeout=0):
    calls.append(req.full_url)
    if req.full_url.endswith("/api/v1/manufacturers"):
        return Resp(json.dumps({"testmaker": {"name": "Testmaker", "fixtureCount": 1}, "../x": {"name": "boese"}}).encode())
    if req.full_url.endswith("/api/v1/manufacturers/testmaker"):
        return Resp(json.dumps({"name": "Testmaker", "fixtures": [{"key": "test-par-7", "name": "Test PAR 7", "categories": ["Color Changer"]}]}).encode())
    if req.full_url.endswith("/api/v1/get-search-results"):
        body = json.loads(req.data)
        check(body["searchQuery"] == "par 7" and body["manufacturersQuery"] in ([], ["testmaker"]), "Suche schickt nur den Suchbegriff")
        return Resp(json.dumps([{"key": "testmaker/test-par-7", "name": "Testmaker Test PAR 7"}, {"key": "../boese", "name": "x"}]).encode())
    if req.full_url.endswith("/testmaker/test-par-7.json"):
        return Resp(json.dumps(PAR).encode())
    raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)


cat = o.Catalog(opener=opener)
check([x["key"] for x in cat.manufacturers()] == ["testmaker"], "Herstellerliste ohne ungueltige Namen")
check(cat.fixtures("testmaker")["fixtures"][0]["name"] == "Test PAR 7", "Geraete eines Herstellers")
check(cat.fixture("testmaker", "test-par-7")["name"] == "Test PAR 7", "Geraet geholt")
check(len(calls) == 3 and all(u.startswith("https://open-fixture-library.org/") for u in calls), "nur die Datenbank wird gefragt")
check(cat.search("  par   7 ") == [{"man": "testmaker", "key": "test-par-7", "name": "Testmaker Test PAR 7"}], "Suche in der ganzen Datenbank")
check(cat.search("par 7", "testmaker")[0]["key"] == "test-par-7", "Suche bei einem Hersteller")
for bad in (("x",), ("par", "../x")):
    try:
        cat.search(*bad)
        check(False, "Suche abgelehnt: %s" % (bad,))
    except ValueError:
        check(True, "Suche abgelehnt: %s" % (bad,))
calls.clear()
cat.fixture("testmaker", "test-par-7")
cat.search("par 7")
check(calls == [], "Zwischenspeicher: kein zweiter Abruf")
for bad in (("../etc", "x"), ("testmaker", "a/b")):
    try:
        cat.fixture(*bad)
        check(False, "ungueltiger Name abgelehnt")
    except ValueError:
        check(True, "ungueltiger Name abgelehnt")
try:
    cat.fixture("testmaker", "fehlt")
    check(False, "404")
except ValueError as e:
    check("nicht gefunden" in str(e), "fehlendes Geraet: nicht gefunden")
finish("test_ofl_import")
