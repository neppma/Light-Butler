"""Show-Assistent mit den Pegelkurven der Spuren und dem Raum (docs/RAUM.md). Ohne Kurven bleibt der Aufbau wie bisher."""
import base64
import json
import os
import tempfile

from _common import build, check, finish

from showman import assistant as a
from showman.api import ShowManager

BPM, DUR, RATE = 120.0, 96.0, 100
N = int(DUR * RATE)


def curves(kick=(), voc=(), hat=None, silent=(), sparse=()):
    """Bytes je 10 ms. kick: Bereiche mit Kick auf jedem Beat, sparse: Bereiche mit einer Kick alle 8 Beats, hat: (a, b) lauter werdend."""
    c = {k: bytearray(N) for k in a.STEM_KEYS}
    for k in ("bass", "sonstiges"):
        c[k][:] = bytes([200]) * N
    for x0, x1 in kick:
        t = x0
        while t < x1:
            for i in range(int(t * RATE), int(t * RATE) + 8):
                c["kick"][i] = 250
            t += 0.5
    for x0, x1 in sparse:
        t = x0
        while t < x1:
            for i in range(int(t * RATE), int(t * RATE) + 8):
                c["kick"][i] = 250
            t += 4.0
    for x0, x1 in voc:
        c["stimme"][int(x0 * RATE):int(x1 * RATE)] = bytes([220]) * (int(x1 * RATE) - int(x0 * RATE))
    for i in range(N):
        c["hihat"][i] = 60
    if hat:
        h0, h1 = hat
        for i in range(int(h0 * RATE), int(h1 * RATE)):
            c["hihat"][i] = int(120 + 130 * (i / RATE - h0) / (h1 - h0)) if i % 25 < 6 else 60
    for x0, x1 in silent:
        for k in a.STEM_KEYS:
            c[k][int(x0 * RATE):int(x1 * RATE)] = bytes(int(x1 * RATE) - int(x0 * RATE))
    return {"v": 1, "rate": RATE, "db_min": -60.0, "duration": DUR, "curves": {k: base64.b64encode(bytes(v)).decode() for k, v in c.items()}}


DOC = {"name": "Lied", "bpm": BPM, "beats_per_bar": 4, "beat_offset": 0.0, "duration": DUR, "tracks": [], "groups": [], "scenes": [], "scene_clips": []}
ST = curves(kick=[(16, 32), (48, 70), (71, 96)], voc=[(0, 48)], hat=(40, 48), silent=[(70, 71)], sparse=[(32, 48)])

# ---- Pegel je Beat und was die Spuren spielen ----
sb = a.stem_beats(ST, 0.5, 0.0, DUR)
check(set(sb) == set(a.STEM_KEYS) and len(sb["kick"]) == 192, "Pegel je Beat fuer alle fuenf Spuren")
check(sb["kick"][40] > -5 and sb["kick"][70] < -40, "Kick: laut auf dem Beat, leise in der Pause")
kick = a.dense(a.stem_present(sb["kick"]))
check(kick[50] and not kick[80], "einzelne Kicks alle zwei Takte sind kein Beat")
check(a.stem_beats(None, 0.5, 0.0, DUR) == {} and a.stem_beats({"curves": {"kick": "x"}}, 0.5, 0.0, DUR) == {}, "ohne oder mit kaputten Kurven: nichts")

# ---- Aufbau aus den Spuren ----
song = a.song_info(DOC, None, ST)
ev = {(e[0], e[1], e[2]) for e in song["ev"]}
check(("drop", 16.0, 16.0) in ev and ("drop", 48.0, 48.0) in ev, f"Drop, wo die Kick nach langer Pause zurueckkommt: {sorted(ev)}")
brk = [e for e in song["ev"] if e[0] == "break" and 32.0 <= e[1] <= 33.5]
bld = [e for e in song["ev"] if e[0] == "build" and e[2] == 48.0 and 39.0 <= e[1] <= 41.0]
check(brk and bld and brk[0][2] == bld[0][1], f"ruhige Stelle ohne Kick, am Ende baut Snare/Hi-Hat auf: {sorted(ev)}")
check(any(e[0] == "gap" and e[1] == 70.0 for e in song["ev"]), "alles leise: Pause in der Musik")
check(song["drops"] == [48.0], "grosser Drop nur weit genug im Lied")
check(a._kind_at(song, 36.0) == "break" and a._kind_at(song, 44.0) == "build" and a._kind_at(song, 70.2) == "gap", "die Stellen bekommen ihre Art")
plain = a.song_info(DOC, None)
check(plain["sb"] == {} and plain["sp"] == {} and plain == a.song_info(DOC) and not [e for e in plain["ev"] if e[0] in ("break", "build", "gap")], "ohne Kurven: Aufbau wie bisher")

# ---- Regie ----
plan = a.direct(song, "club", 0.5, 0)
calm = [s for s in plan if 32.0 <= s["t"] < 40.0]
check(calm and all(s["lead"] in a.VOCAL_LEADS for s in calm), f"Gesang ohne Kick: Gobo an der Wand oder die Wand selbst: {[s['lead'] for s in calm]}")
check(all(s["also"] == "wash" for s in calm if s["lead"] == "nano"), "Nanoleaf mit den Washes, die auf es leuchten")
check(all(s["lead"] == "bars" for s in plan if s["kind"] == "build"), "Aufbau: die Docooler blinken immer schneller")
check(all(s["level"] < 0 for s in plan if s["kind"] == "gap"), "Pause: finster")
for seed in range(6):
    p = a.direct(a.song_info(DOC, None), "club", 0.6, seed)
    weak = [s for s in p if s["kind"] == "main" and s["level"] == 2 and s["lead"] in a.WEAK_PARTNER]
    check(all(s["also"] == a.WEAK_PARTNER[s["lead"]] for s in weak), f"schwache Geraete im Hauptteil nie allein (Lied {seed})")
check("spot" not in a.ACCENTS and "nano" in a.ACCENTS and "band" in a.ACCENTS, "Peaks nur fuer Geraete, die im Raum wirken")

# ---- Spuren auf der Anlage ----
rig, sh = build()
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_ak_"))
meta = mgr.meta()
parts = a.rig_parts(meta)
OPTS = {"laser": True, "fog": True, "strobe": False, "move": True, "ambient": False, "style": "club"}
moves = set()
for seed in range(8):
    pl = a.direct(song, "club", 0.9, seed)
    for t in a.render([dict(s, lead="bars") for s in pl], song, parts, OPTS, seed):
        if t["target"].get("group") == "rig_bars" and t["attr"] == "move":
            moves |= {c["pattern"] for c in t["clips"]}
check(moves and moves <= {"fan", "sweep_lr"}, f"Docooler faechern nur in die Breite: {moves}")
tracks = a.render(plan, song, parts, OPTS, 0)
fog = [c for t in tracks if t["attr"] == "fog" for c in t["clips"]]
after = [s for s in plan if s["t"] >= 48.0 + 2 * song["bar"] and s["kind"] not in ("hit", "build")]
spot_clips = [c for t in tracks if t["target"].get("group") == "rig_spot" and t["attr"] == "dimmer" for c in t["clips"]]
check(fog and after and any(abs(c["t"] - after[0]["t"]) < 0.01 for c in spot_clips), "nach dem Nebel ist der Vega dran: jetzt sieht man seinen Strahl")
no_fog = a.render(plan, song, parts, dict(OPTS, fog=False), 0)
check(not [c for t in no_fog if t["attr"] == "fog" for c in t["clips"]], "ohne Nebel kein Schub")

# ---- Claude bekommt die Kurven grob ----
body = json.loads(a.claude_request(plan, song, OPTS, "")["messages"][0]["content"])
sp = body["spuren_je_takt"]
check(set(sp) == set(a.STEM_KEYS) and len(sp["kick"]) == 48 and all(0 <= x <= 100 for v in sp.values() for x in v), "Claude: fuenf Spuren, ein Wert je Takt")
check(sp["kick"][2] < 40 and sp["kick"][15] > 90 and "Docooler" in body["raum"], "Claude: ruhige Stelle und Raum stehen drin")
check(json.loads(a.claude_request(plan, plain, OPTS, "")["messages"][0]["content"])["spuren_je_takt"] == {}, "ohne Kurven: leer")
design = json.loads(a.design_request(DOC, meta, song, OPTS, "", "")["messages"][0]["content"])
check(design["spuren_je_takt"] == sp and design["raum"] == a.ROOM and "curves" not in json.dumps(design), "Entwurf: grob, keine Rohkurven")

# ---- ueber die Show mit gespeicherten Kurven ----
st = mgr.store
st.create("Lied")
st.save("Lied", dict(st.load("Lied"), bpm=BPM, beat_offset=0.0, duration=DUR))
with open(st.path("Lied", "audio.mp3"), "wb") as f:
    f.write(b"ID3\x04\0\0\0\0\0\0" + b"\xff\xfb" * 4000)
check(mgr.op({"op": "assist_info", "name": "Lied"})["stems"] is False, "Fenster: noch keine Kurven")
st.save_stems("Lied", dict(ST, fp=st.stems_state("Lied")["fp"]))
check(mgr.op({"op": "assist_info", "name": "Lied"})["stems"] is True, "Fenster: Kurven sind da")
r = mgr.op({"op": "assist", "name": "Lied", "laser": False, "fog": False, "strobe": False, "move": True, "ambient": False, "seed": 3})
new = st.load(r["show"])
wall = {t["target"].get("group") for t in new["tracks"] for c in t["clips"] if t["attr"] == "dimmer" and c["t"] < 40.0 <= c["t"] + c["d"] + 4}
check(new["tracks"] and wall & {"rig_spot", "rig_nano", "rig_wash"}, f"Vorschlag nutzt die gespeicherten Kurven: {wall}")
finish("test_assistent_kurven")
