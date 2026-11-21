"""Export je Fixture (Wunsch von Markus, 21.11.2026): Light-Butler-Datei, OFL, QLC+ und YAML. Jeder Export laesst sich
wieder einlesen; beim Einlesen bleiben Laser und Nebel gesperrt, keine Laser-Freigabe, kein Einzel-Strobe, keine Ruhewerte.
Echte QLC+-Dateien beginnen mit <!DOCTYPE FixtureDefinition>, das muss der Import annehmen."""
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET

import yaml

from _common import PI, check, finish

import fixture_edit as fe                    # noqa: E402
import fixture_export as fx                  # noqa: E402
import ofl_import as o                       # noqa: E402
from dmx import Rig                          # noqa: E402

c = yaml.safe_load(open(os.path.join(PI, "fixtures.yaml"), encoding="utf-8"))
names = [e["name"] for e in c["fixtures"]]
bad = []
for n in names:
    for fmt in fx.FORMATS:
        try:
            fn, body, ct = fx.export(c, n, fmt)
            if fmt in ("lb", "ofl"):
                json.loads(body)
            elif fmt == "qxf":
                ET.fromstring(body.decode().replace("<!DOCTYPE FixtureDefinition>", ""))
            else:
                yaml.safe_load(body)
        except Exception as e:                # noqa: BLE001
            bad.append((n, fmt, str(e)))
check(not bad, "alle Fixtures in allen Formaten exportierbar: %s" % bad[:3])

fn, body, ct = fx.export(c, "vega", "lb")
check(fn.endswith(".lightbutler.json") and ct.startswith("application/json"), "Dateiname und Inhaltstyp: " + fn)
for fmt in fx.FORMATS:
    try:
        fx.export(c, "gibtsnicht", fmt)
        check(False, "unbekanntes Fixture abgelehnt")
    except ValueError:
        pass
try:
    fx.export(c, "vega", "exe")
    check(False, "unbekanntes Format abgelehnt")
except ValueError:
    check(True, "unbekanntes Format abgelehnt")

# Rueckweg: jede Datei geht wieder durch den Import, gleiche Kanalzahl
for n in names:
    for fmt in ("lb", "ofl", "qxf"):
        d, mk = o.read_file(fx.export(c, n, fmt)[1].decode())
        t, _ = o.convert(d, 0, mk)
        fe.check_import(t)
        if t["channels"] != c["types"][next(e["type"] for e in c["fixtures"] if e["name"] == n)]["channels"]:
            bad.append((n, fmt))
check(not bad, "Export -> Import ergibt dieselbe Kanalzahl: %s" % bad[:3])

# Light-Butler-Datei: Inhalt bleibt, Sicherheit bleibt
d, _ = o.read_file(fx.export(c, "vega", "lb")[1].decode())
tv, nv = o.convert(d, 0, "")
vt = c["types"]["vega_spot_60"]
check(tv["map"] == vt["map"] and tv["safe_limits"] == vt["safe_limits"] and tv["presets"] == vt["presets"]
      and tv["desc"] == vt["desc"], "Vega: Kanaele, Grenzen, Presets und Beschreibungen gleich")
check("hw_strobe" not in tv and any("hw_strobe" in x for x in nv), "Einzel-Strobe wird nicht uebernommen (mit Hinweis)")
d, _ = o.read_file(fx.export(c, "laser", "lb")[1].decode())
tl, nl = o.convert(d, 0, "")
lt = c["types"]["laser_ktv34"]
check("laser_channels" not in tl and set(lt["laser_channels"]) <= set(tl["locked_channels"]), "Laser: Laser-Kanaele gesperrt, keine Freigabe")
d, _ = o.read_file(fx.export(c, "eyes", "lb")[1].decode())
te, _ = o.convert(d, 0, "")
check("laser_channels" not in te and "auto_mode" not in te and set(c["types"]["eyes_21"]["laser_channels"]) <= set(te["locked_channels"]),
      "Eyes: Laser gesperrt, kein Auto-Modus")
d, _ = o.read_file(fx.export(c, "hazer", "lb")[1].decode())
th, _ = o.convert(d, 0, "")
check(th.get("locked") is True and "manual_allowed" not in th and "burst" not in th, "Hazer: ganz gesperrt, kein Handbetrieb")
d, _ = o.read_file(fx.export(c, "laser", "lb")[1].decode())
d["type"].pop("locked_channels")
d["type"]["rest_values"] = {"x": 255}
t2, _ = o.convert(d, 0, "")
check(set(lt["laser_channels"]) <= set(t2["locked_channels"]) and "rest_values" not in t2, "veraenderte Datei: Laser trotzdem gesperrt")
d["type"]["laser_channels"] = []
d["type"]["map"]["laser_x"] = 35
d["type"]["channels"] = 35
t3, _ = o.convert(d, 0, "")
check("laser_channels" not in t3, "nie eine Laser-Freigabe aus einer Datei")
try:
    o.convert(d, 1, "")
    check(False, "Light-Butler-Datei hat nur einen Modus")
except ValueError:
    check(True, "Light-Butler-Datei hat nur einen Modus")

# OFL und QLC+: Laser gesperrt, Kategorien, Rollen
of = fx.to_ofl(c, "laser")
check("Laser" in of["categories"] and of["modes"][0]["channels"][0] in of["availableChannels"], "OFL: Laser als Kategorie")
d, _ = o.read_file(json.dumps(of))
check(o.convert(d, 0, "")[0].get("locked") is True, "OFL-Export eines Lasers: wieder ganz gesperrt")
ov = fx.to_ofl(c, "vega")
check("Moving Head" in ov["categories"] and ov["availableChannels"]["Pan"]["fineChannelAliases"] == ["Pan fine"], "OFL: Moving Head mit Pan fein")
tq, _ = o.convert(o.read_file(fx.export(c, "vega", "qxf")[1].decode())[0], 0, "")
check(all(k in tq["map"] for k in ("pan", "pan_fine", "tilt", "dimmer")), "QLC+-Export des Vega: Pan, Tilt, Dimmer erkannt")
tp, _ = o.convert(o.read_file(fx.export(c, "docooler_1", "qxf")[1].decode())[0], 0, "")
check(all(k in tp["map"] for k in ("r1", "g1", "b1", "dimmer")), "QLC+-Export der Docooler: Zellen erkannt")
xml = fx.export(c, "laser", "qxf")[1].decode()
check("<Type>Laser</Type>" in xml and "Maintenance" in xml, "QLC+: Laser-Kanaele als Wartung markiert")

# DOCTYPE: QLC+-Kopf ja, eigene Regeln nie
try:
    o.read_file('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><FixtureDefinition/>')
    check(False, "DOCTYPE mit ENTITY abgelehnt")
except ValueError:
    check(True, "DOCTYPE mit ENTITY abgelehnt")
try:
    o.read_file('<?xml version="1.0"?><!DOCTYPE x SYSTEM "file:///etc/passwd"><FixtureDefinition/>')
    check(False, "fremdes DOCTYPE abgelehnt")
except ValueError:
    check(True, "fremdes DOCTYPE abgelehnt")

# YAML: Typ und Fixture
y = yaml.safe_load(fx.export(c, "par", "yaml")[1])
check(y["fixtures"][0]["name"] == "par" and y["types"]["par_rgbw_8ch"]["map"] == c["types"]["par_rgbw_8ch"]["map"], "YAML: Typ und Fixture")

# Ganzer Weg: exportieren, auf einem anderen Licht-Rechner einlesen, Name bleibt
tmp = tempfile.mkdtemp()
shutil.copy(os.path.join(PI, "fixtures.yaml"), tmp)
rig = Rig(os.path.join(tmp, "fixtures.yaml"))
d, mk = o.read_file(fx.export(c, "par", "lb")[1].decode())
name, _ = fe.cmd_type_import(rig, {"fixture": d, "maker": mk, "mode": 0, "source": "datei:par.lightbutler.json"})
check(name == "par_rgbw_8ch_2", "Typname bleibt (mit Nummer, wenn es ihn schon gibt): " + name)
d["name"] = "mein_par"
name2, _ = fe.cmd_type_import(rig, {"fixture": d, "maker": mk, "mode": 0})
check(name2 == "mein_par" and rig.user["types"]["mein_par"]["map"] == c["types"]["par_rgbw_8ch"]["map"], "freier Name bleibt gleich")
d["name"] = "../böse"
name3, _ = fe.cmd_type_import(rig, {"fixture": d, "maker": mk, "mode": 0})
check(fe.NAME_RE.match(name3) is not None, "ungueltiger Name ersetzt: " + name3)
c2 = fe.apply_user(rig.base_cfg, rig.user)
fe.cmd_fixture_save(rig, {"new": True, "type": "mein_par", "label": "Zweiter PAR", "nr": 40, "address": 470, "group": "bar"})
c2 = fe.apply_user(rig.base_cfg, rig.user)
check(json.loads(fx.export(c2, "zweiter_par", "lb")[1])["type"]["map"] == c["types"]["par_rgbw_8ch"]["map"], "neues Fixture exportierbar")
shutil.rmtree(tmp)

finish("test_fixture_export")
