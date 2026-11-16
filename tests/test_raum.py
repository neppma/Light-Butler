"""Raumplan (Seite /raum): wo die Geraete stehen. Nur Anzeige, gespeichert in raum.json, aufs Licht wirkt er nie."""
import json
import os
import subprocess
import tempfile

from _common import PI, ROOT, build, check, finish

from showman import room as rm
from showman.api import ShowManager

rig, sh = build()
devs = rm.devices(rig)
names = {d["name"] for d in devs}
check({"docooler_1", "vega", "effektband", "theke", "couchtisch", "nanoleaf"} <= names, "alle Geraete und das Nanoleaf stehen zur Wahl")
check(not [x for x in devs if x["group"] == "nano" and x["name"] != "nanoleaf"], "keine einzelnen Nanoleaf-Panels")
check(all(d["line"] for d in devs if d["name"] in ("effektband", "theke", "couchtisch")) and not [d for d in devs if d["name"] == "vega" and d["line"]], "LED-Streifen sind Linien")
check([d["short"] for d in devs if d["name"] in ("docooler_1", "rgbuv_7", "par")] == ["Spider 1", "Wash 7", "Barlicht"], "kurze Namen im Plan")

d = rm.default(names)
check(d["w"] == 8.0 and d["h"] == 5.0 and d["guess"] and set(d["items"]) <= names | {"effektband#2"}, "Vorschlag: 8 x 5 m, nur bekannte Geraete")
check(d["items"]["effektband"]["y"] > 4 and d["items"]["effektband#2"]["y"] < 1 and d["items"]["effektband"]["len"] == 8.0, "Effektband 1 unten, 2 oben, ueber 8 m")
check(d["items"]["docooler_1"]["x"] < 1 and d["items"]["rgbuv_7"]["y"] < 1 and "theke" not in d["items"], "Docooler links, Washes oben, Theke noch offen")

bad = {"w": 100, "h": "x", "items": {"vega": {"x": -3, "y": 99, "rot": 370, "len": -1}, "fremd": {"x": 1, "y": 1}, "effektband#2": {"x": 2, "y": 2, "len": 50},
                                     "../etc": {"x": 1}, "vega#1": {"x": 1}, "vega#2": "kaputt", "theke": {"x": "nan", "y": 1}}}
c = rm.clean(bad, names)
check(c["w"] == rm.SIZE_MAX and c["h"] == 5.0, "Raumgroesse begrenzt, Unsinn wird Standard")
check(c["items"]["vega"] == {"x": 0.0, "y": 5.0, "rot": 10.0, "len": 0.0}, "Position im Raum, Drehung 0 bis 360")
check(set(c["items"]) == {"vega", "effektband#2", "theke"}, "fremde und unsinnige Eintraege fallen weg")
check(c["items"]["effektband#2"]["len"] == 40.0 and c["items"]["theke"]["x"] == 20.0, "Laenge begrenzt, keine Zahl: Mitte")
try:
    rm.clean("Text", names)
    check(False, "kein Objekt abgelehnt")
except ValueError:
    check(True, "kein Objekt abgelehnt")

mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_ra_"))
mgr.room_path = os.path.join(tempfile.mkdtemp(prefix="s2l_raum_"), "raum.json")
r = mgr.op({"op": "room"})
check(r["room"]["guess"] and not os.path.exists(mgr.room_path) and r["devices"], "ohne Datei: Vorschlag, nichts geschrieben")
plan = dict(r["room"], items=dict(r["room"]["items"], couchtisch={"x": 6, "y": 3, "rot": 90, "len": 1.2}))
s = mgr.op({"op": "room_save", "room": plan})["room"]
check(not s["guess"] and os.path.isfile(mgr.room_path) and json.load(open(mgr.room_path))["items"]["couchtisch"]["rot"] == 90.0, "speichern: Datei, kein Vorschlag mehr")
check(mgr.op({"op": "room"})["room"]["items"]["couchtisch"]["len"] == 1.2, "gespeicherter Plan kommt zurueck")
open(mgr.room_path, "w").write("kaputt")
check(mgr.op({"op": "room"})["room"]["guess"], "kaputte Datei: Vorschlag statt Absturz")

api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
check('if path == "/raum":' in api and 'room.html' in api, "Seite /raum")
sm = os.path.join(PI, "static", "sm")
check(os.path.isfile(os.path.join(sm, "room.html")) and "room.js" in open(os.path.join(sm, "room.html"), encoding="utf-8").read(), "Seite und Skript da")
js = os.path.join(sm, "room.js")
if subprocess.run(["node", "--version"], capture_output=True).returncode == 0:
    check(subprocess.run(["node", "--check", js], capture_output=True).returncode == 0, "room.js fehlerfrei")
src = open(js, encoding="utf-8").read()
check("room_save" in src and "pointerdown" in src and "flip(" in src and "+ Stück" in src, "ziehen, spiegeln, weiteres Stueck, speichern")
import webpanel  # noqa: E402
page = webpanel.make_page()
check(page.count('href="/raum"') == 2 and '<a id="rmbtn" href="/raum"' in page and page.index('id="hlbtn"') < page.index('id="rmbtn"'), "Link in den Einstellungen und runder Knopf neben dem Herz")
_cm = os.path.join(ROOT, "CLAUDE" ".md")
if os.path.isfile(_cm):
    check("raum.json" in open(_cm, encoding="utf-8").read(), "raum.json steht bei den Zustandsdateien")
check("pi/*.json" in open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read(), "raum.json kommt nicht ins Git")
check("'*.json'" in open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read(), "deploy.sh ueberschreibt raum.json nicht")
eng = open(os.path.join(PI, "showman", "engine.py"), encoding="utf-8").read() + open(os.path.join(PI, "show.py"), encoding="utf-8").read()
check("raum.json" not in eng and "import room" not in eng and "room_path" not in eng, "aufs Licht wirkt der Plan nicht")
_rj = open(js, encoding="utf-8").read()
_rh = open(os.path.join(sm, "room.html"), encoding="utf-8").read()
check("svg.style.aspectRatio = (W + 2 * m) + ' / ' + (H + 2 * m);" in _rj and "#plan { display: block; flex: 1 1 560px; min-width: 300px; width: 100%; height: auto;" in _rh,
      "Plan mit Seitenverhaeltnis des Raums (Safari am iPad machte sonst einen 150 px hohen Streifen)")
finish("test_raum")
