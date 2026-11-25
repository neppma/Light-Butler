"""Raumplan: Pixel-Matrix und API-Anzeige (Fernseher am /api/takt) lassen sich setzen, drehen, entfernen und werden gespeichert.
Sie sind nur Anzeige: keine Raum-Gruppen, keine Lichtwelle, nichts fuer den Show-Assistenten."""
import json
import os
import subprocess
import tempfile

from _common import PI, build, check, finish

from showman import assistant
from showman import room as rm
from showman.api import ShowManager

rig, sh = build()
devs = rm.devices(rig)
by = {d["name"]: d for d in devs}
check("matrix" in by and "api_anzeige" in by, "Pixel-Matrix und API-Anzeige stehen zur Wahl")
check(by["matrix"]["display"] and by["api_anzeige"]["display"] and by["matrix"]["group"] == "display", "als Anzeige gekennzeichnet")
check(not by["matrix"]["line"] and by["api_anzeige"]["size"] > by["matrix"]["size"] > 0, "kein Streifen, Fernseher breiter als die Matrix")
check(not [d for d in devs if d.get("display") and d["name"] not in rm.DISPLAY_NAMES], "nur die zwei Anzeigen")
names = {d["name"] for d in devs}
check(not set(rm.default(names)["items"]) & rm.DISPLAY_NAMES, "der erste Vorschlag setzt keine Anzeige")

mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_ra_"))
mgr.room_path = os.path.join(tempfile.mkdtemp(prefix="s2l_raum_"), "raum.json")
r = mgr.op({"op": "room"})["room"]
check(not set(r["items"]) & rm.DISPLAY_NAMES, "ohne Datei: keine Anzeige im Plan")
plan = dict(r, items=dict(r["items"], matrix={"x": 7.5, "y": 2.5, "rot": 180, "len": 0.3},
                          api_anzeige={"x": 4, "y": 0.1, "rot": 450, "len": 1.4}, **{"matrix#2": {"x": 1, "y": 1}}))
s = mgr.op({"op": "room_save", "room": plan})["room"]
f = json.load(open(mgr.room_path))
check(f["items"]["matrix"] == {"x": 7.5, "y": 2.5, "rot": 180.0, "len": 0.3}, "Matrix in raum.json gespeichert")
check(f["items"]["api_anzeige"]["rot"] == 90.0 and f["items"]["api_anzeige"]["len"] == 1.4, "API-Anzeige gedreht (Grad 0 bis 360), Breite gespeichert")
got = mgr.op({"op": "room"})["room"]["items"]
check(got["api_anzeige"]["x"] == 4.0 and got["matrix"]["x"] == 7.5, "gespeicherte Anzeigen kommen zurueck")
moved = dict(s, items={k: v for k, v in s["items"].items() if k != "matrix"})
mgr.op({"op": "room_save", "room": moved})
check("matrix" not in json.load(open(mgr.room_path))["items"], "Aus dem Plan: Matrix entfernt")

# Nichts davon fuer das Licht oder den Assistenten
mgr.op({"op": "room_save", "room": s})
saved = mgr.saved_room()
check(saved and not set(saved["items"]) & rm.DISPLAY_NAMES and "vega" in saved["items"], "Show-Assistent bekommt den Plan ohne Anzeigen")
check(rm.lights_only(None) is None and rm.lights_only({"items": {"matrix": {}, "vega": {}}})["items"] == {"vega": {}}, "lights_only")
meta = mgr.meta()
info = assistant.room_info(saved, meta)
check(not [g for g in info["geraete"] if "Matrix" in g["geraet"] or "API" in g["geraet"]], "Claude bekommt keine Anzeigen als Geraete")
alone = {"w": 8, "h": 5, "items": {"matrix": {"x": 1, "y": 1, "rot": 0, "len": 0.3}, "api_anzeige": {"x": 7, "y": 1, "rot": 0, "len": 1.2}}}
check(assistant.room_info(rm.lights_only(alone), meta) is None, "nur Anzeigen im Plan: fuer Claude kein Raum")

sm = os.path.join(PI, "static", "sm")
js = open(os.path.join(sm, "room.js"), encoding="utf-8").read()
if subprocess.run(["node", "--version"], capture_output=True).returncode == 0:
    check(subprocess.run(["node", "--check", os.path.join(sm, "room.js")], capture_output=True).returncode == 0, "room.js fehlerfrei")
check("isDisp(" in js and "d.size" in js and "Breite des Bildschirms" in js, "Editor zeichnet Anzeigen als Bildschirm mit Breite")
eng = open(os.path.join(PI, "showman", "engine.py"), encoding="utf-8").read() + open(os.path.join(PI, "show.py"), encoding="utf-8").read()
check("api_anzeige" not in eng and "DISPLAY_NAMES" not in eng, "aufs Licht wirken die Anzeigen nicht")
finish("test_raum_anzeigen")
