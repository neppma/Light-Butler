"""Show-Assistent mit dem Raumplan: Gruppen laufen entlang der Wand, Lichtwellen durch den Raum, Claude bekommt die Positionen.
Ohne gespeicherten Plan bleibt alles wie bisher."""
import json
import os
import tempfile

from _common import build, check, finish

from showman import assistant as a
from showman import timeline as tl
from showman.api import ShowManager

# Der Plan von Markus am Pi (05.11.2026), gerundet
P = {"hazer": (0.2, 0.3), "docooler_6": (0.2, 0.8), "docooler_5": (0.2, 1.6), "vega": (0.2, 2.5), "docooler_2": (0.2, 3.4), "docooler_1": (0.2, 4.2),
     "laser": (0.3, 2.9), "rgbuv_11": (3.2, 0.2), "rgbuv_10": (3.8, 0.2), "rgbuv_8": (4.4, 0.2), "rgbuv_7": (5.0, 0.2), "nanoleaf": (4.1, 0.3),
     "uv_bar": (6.0, 2.0), "derby": (7.6, 4.7), "eyes": (7.8, 0.3), "par": (7.9, 3.6)}
ROOM = {"v": 1, "w": 8.0, "h": 5.0, "guess": False, "items": {k: {"x": x, "y": y, "rot": 0.0, "len": 0.0} for k, (x, y) in P.items()}}
ROOM["items"]["effektband"] = {"x": 4.0, "y": 5.0, "rot": 0.0, "len": 8.0}
ROOM["items"]["theke"] = {"x": 6.9, "y": 3.6, "rot": 90.0, "len": 1.2}

rig, sh = build()
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_ar_"))
mgr.room_path = os.path.join(tempfile.mkdtemp(prefix="s2l_arr_"), "raum.json")
meta = mgr.meta()
parts = a.rig_parts(meta)

# ---- Reihenfolge an der Wand ----
g = {x["id"]: x["fixtures"] for x in a.room_groups(ROOM, parts)}
check(g["raum_bars"] == ["docooler_6", "docooler_5", "docooler_2", "docooler_1"], f"Docooler von oben nach unten, wie sie an der Wand haengen: {g.get('raum_bars')}")
check(g["raum_wash"] == ["rgbuv_11", "rgbuv_10", "rgbuv_8", "rgbuv_7"], "Washes von links nach rechts")
check(g["raum_fx"] == ["eyes", "derby"], "Eyes und Derby: entlang der rechten Wand")
check(a.room_groups(None, parts) == [] and a.room_groups({"items": {"docooler_1": {"x": 1, "y": 1}}}, parts) == [], "ohne Plan oder mit nur einem Geraet: keine eigene Reihenfolge")

# ---- Stufen der Welle ----
steps = a.wave_steps(ROOM, parts)
names = [sorted(tg.get("fixture") or tg.get("group") for tg, _ in st) for st in steps]
nano = bool(parts.get("nano"))                                  # die Test-Anlage hat kein Nanoleaf, die echte schon
check(len(steps) == 3 + nano and set(names[0]) == {"docooler_1", "docooler_2", "docooler_5", "docooler_6", "vega"}, f"Welle beginnt an der Docooler-Wand: {names}")
check(names[1:] == ([["rig_nano"]] if nano else []) + [["uv_bar"], ["derby", "eyes"]], "dann Nanoleaf (wenn da), UV, rechts Eyes und Derby")
flat = [n for st in names for n in st]
check(not [n for n in flat if n.startswith("rgbuv") or n in ("laser", "hazer", "par", "theke", "effektband")], "keine Washes, kein Laser, kein Nebel, kein Ambiente in der Welle")
check(a.wave_steps({"items": {"docooler_1": {"x": 1, "y": 1, "len": 0}}}, parts) == [], "zu wenige Stufen: keine Welle")

# ---- Vorschlag mit und ohne Plan ----
DOC = {"name": "Lied", "bpm": 120.0, "beats_per_bar": 4, "beat_offset": 0.0, "duration": 160.0, "tracks": [], "groups": [], "scenes": [], "scene_clips": []}
OPTS = {"laser": True, "fog": False, "strobe": False, "move": True, "ambient": False, "style": "club", "wild": 0.6, "seed": 1}
plain, plan0, _ = a.suggest(DOC, meta, OPTS)
same, _, _ = a.suggest(DOC, meta, OPTS, room=None)
check(plain == same and not [s for s in plan0 if s["lead"] == "wave"] and plain["groups"] == [], "ohne Plan: kein Unterschied, keine Welle, keine eigenen Gruppen")
new, plan, song = a.suggest(DOC, meta, OPTS, room=ROOM)
waves = [s for s in plan if s["lead"] == "wave"]
check(waves and all(s["kind"] == "main" and s["level"] == 2 for s in waves), "Lichtwellen im Hauptteil")
mains = [s for s in plan if s["kind"] == "main" and s["level"] == 2 and s["lead"]]
check(len(waves) <= len(mains) / 3, "nur ab und zu eine Welle, sonst einer allein wie gewohnt")
w = waves[0]


def dim_clips(name):
    return [c for t in new["tracks"] if t["target"].get("fixture") == name and t["attr"] == "dimmer" for c in t["clips"] if w["t"] <= c["t"] < w["t"] + w["d"]]


d6, uv, ey = dim_clips("docooler_6"), dim_clips("uv_bar"), dim_clips("eyes")
check(d6 and uv and ey and d6[0]["t"] < uv[0]["t"] < ey[0]["t"], "die Welle laeuft von links nach rechts")
check(abs(uv[0]["t"] - d6[0]["t"] - (1 + nano) * song["beat"]) < 0.01 and all(abs(c["d"] - song["beat"]) < 0.01 or c["t"] + c["d"] >= w["t"] + w["d"] - 0.01 for c in d6), "eine Stufe je Beat")
if len(d6) > 1:
    check(abs(d6[1]["t"] - d6[0]["t"] - 2 * (len(steps) - 1) * song["beat"]) < 0.01, "hin und zurueck, dann wieder an der Docooler-Wand")
col = [c for t in new["tracks"] if t["target"].get("fixture") == "docooler_6" and t["attr"] == "color" for c in t["clips"] if w["t"] <= c["t"] < w["t"] + w["d"]]
check(len(col) == len(d6) and all(x["t"] == y["t"] and x["d"] == y["d"] for x, y in zip(col, d6)), "Farbe nur, solange die Stufe leuchtet")
check({x["id"] for x in new["groups"]} == {"raum_bars", "raum_wash", "raum_fx"}, "Vorschlag bringt die Gruppen in Raum-Reihenfolge mit")
check(any(t["target"].get("group") == "raum_bars" for t in new["tracks"]) and not any(t["target"].get("group") == "rig_bars" for t in new["tracks"]), "Docooler-Spuren nutzen die Reihenfolge an der Wand")
comp = tl.compile_show(dict(new, name="R"), rig)
check(comp is not None and not comp.warnings, f"Vorschlag mit Raumplan laesst sich uebersetzen: {getattr(comp, 'warnings', None)}")
mine = dict(DOC, groups=[{"id": "g1", "name": "Meine", "fixtures": ["eyes"]}, {"id": "raum_bars", "name": "alt", "fixtures": []}])
check([x["id"] for x in a.suggest(mine, meta, OPTS, room=ROOM)[0]["groups"]][:1] == ["g1"] and sum(1 for x in a.suggest(mine, meta, OPTS, room=ROOM)[0]["groups"] if x["id"] == "raum_bars") == 1, "eigene Gruppen bleiben, alte Raum-Gruppen werden ersetzt")

# ---- Claude ----
ri = song["room"]
check(ri and ri["breite_m"] == 8.0 and any(x["geraet"].startswith("Docooler") and x["x"] == 0.2 for x in ri["geraete"]), "Claude: Raumplan mit Positionen")
body = json.loads(a.claude_request(plan, song, OPTS, "")["messages"][0]["content"])
design = json.loads(a.design_request(DOC, meta, song, OPTS, "", "")["messages"][0]["content"])
check(body["raumplan"] == ri and design["raumplan"] == ri and "Lichtwelle" in a.DESIGN_SYSTEM, "Claude bekommt den Plan beim Verfeinern und beim Entwerfen")
check(a.apply_claude([dict(w)], {"segments": [{"i": w["i"], "lead": "wave"}]})[0]["lead"] == "wave", "Claude kann eine Welle stehen lassen")
check(json.loads(a.design_request(DOC, meta, a.song_info(DOC), OPTS, "", "")["messages"][0]["content"])["raumplan"] is None, "ohne Plan: nichts")

# ---- ueber das Panel: nur ein gespeicherter Plan zaehlt ----
check(mgr.saved_room() is None, "ohne Datei kein Plan")
mgr.op({"op": "room_save", "room": ROOM})
check(mgr.saved_room() and mgr.saved_room()["items"]["docooler_6"]["y"] == 0.8, "gespeicherter Plan wird genutzt")
st = mgr.store
st.create("Lied")
st.save("Lied", dict(st.load("Lied"), bpm=120.0, beat_offset=0.0, duration=160.0))
check(mgr.op({"op": "assist_info", "name": "Lied"})["room"] is True, "Fenster: Raumplan ist da")
r = mgr.op({"op": "assist", "name": "Lied", **OPTS})
check(any(x["id"] == "raum_bars" for x in st.load(r["show"])["groups"]), "Vorschlag ueber das Panel nutzt den Raumplan")
finish("test_assistent_raum")
