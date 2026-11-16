"""Vorhoeren ab der wichtigen Stelle (Wunsch von Markus, 14.11.2026): ▶ beginnt beim Hauptteil, sonst beim 2. Hotcue, sonst beim
ersten Drop, sonst bei einem Drittel. Der Pi liefert die Marken (Ablage oder Musik-Rechner ohne Fingerabdruck)."""
import io
import json
import os
import subprocess
import sys
import types

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
from showman import api  # noqa: E402

# ---- Pi: Marken holen ----
asked = []


def opener(url, timeout):
    asked.append(url)
    if "fehlt" in url:
        raise OSError("404")
    return io.BytesIO(json.dumps({"se": [["intro", 0, 20], ["main", 20, 60], ["break", 60, 70]], "cu": [5, 30],
                                  "ev": [["drop", 40, 41, 0.5, ""], ["build", 30, 40, 0.2, ""]], "fp": "x"}).encode())


kept = {"/m/abgelegt.mp3": {"se": [["main", 12.0, 50.0]], "cu": [], "ev": []}}
fake = types.SimpleNamespace(marks_bulk=types.SimpleNamespace(get=lambda p: kept.get(p)), music_url=lambda: "http://mac:9025",
                             mac_opener=opener, PV_CACHE=600, _pv_clean=api.ShowManager._pv_clean)
pm = lambda p: api.ShowManager.preview_marks(fake, p)
check(pm("/m/abgelegt.mp3") == {"se": [["main", 12.0, 50.0]], "cu": [], "ev": []} and not asked, "Ablage zuerst, ohne Mac")
m = pm("/m/neu.mp3")
check(m["se"] == [["main", 20.0, 60.0]] and m["cu"] == [5.0, 30.0] and m["ev"] == [["drop", 40.0, 41.0]], "vom Musik-Rechner, nur Hauptteile und Drops: " + str(m))
check(len(asked) == 1 and "nofp=1" in asked[0] and "p=%2Fm%2Fneu.mp3" in asked[0], "ohne Fingerabdruck, Pfad maskiert")
pm("/m/neu.mp3")
check(len(asked) == 1, "gemerkt: kein zweites Mal zum Musik-Rechner")
check(pm("/m/fehlt.mp3") == {} and pm("") == {}, "nichts da: leer, kein Fehler")
fake2 = types.SimpleNamespace(marks_bulk=types.SimpleNamespace(get=lambda p: None), music_url=lambda: "", mac_opener=opener, PV_CACHE=600,
                              _pv_clean=api.ShowManager._pv_clean)
check(api.ShowManager.preview_marks(fake2, "/m/x.mp3") == {}, "ohne Musik-Rechner: leer")
# Lange Mixe (Fehlerbericht 14.11.2026: Striche nur bis Minute 30): Ablage gekuerzt -> vom Mac, ohne die Grenzen von clean_marks
from showman import timeline as tl  # noqa: E402
asked.clear()
longev = [["drop", 50.0 * i, 50.0 * i + 1, 1, ""] for i in range(1, 160)] + [["break", 60.0 * i, 60.0 * i + 5, 1, ""] for i in range(1, 70)]
kept["/m/mix.mp3"] = tl.clean_marks({"ev": longev, "se": [], "cu": []})
fake.mac_opener = lambda url, timeout: (asked.append(url), io.BytesIO(json.dumps({"se": [["main", 10, 20]], "cu": [], "ev": longev}).encode()))[1]
m = pm("/m/mix.mp3")
check(len(asked) == 1 and len(m["ev"]) == 159 and max(e[1] for e in m["ev"]) > 7000, "langer Mix: alle Drops bis zum Ende (vom Mac): " + str(len(m["ev"])))
src = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('"/api/sm/preview_marks"' in src, "Route am Pi")

# ---- Musik-Rechner ----
srv = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
br = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check('"nofp" in qq' in srv and "marks(p, False)" in srv and "def marks_for_path(self, path, fp=True)" in br, "Musik-Rechner: /marks ohne Fingerabdruck")

# ---- Browser: Einstiegspunkt (die Rechnung aus core.js in node) ----
core = os.path.join(ROOT, "pi", "static", "sm", "core.js")
txt = open(core, encoding="utf-8").read()
a, b = txt.index("  SM.pvEntry = "), txt.index("  SM.preview = ")
js = "const SM = {};\n" + txt[a:b] + """
const D = 240, out = [];
out.push(SM.pvEntry({se: [['intro', 0, 20], ['main', 20, 60]], cu: [5, 30], ev: [['drop', 40, 41]]}, D).t);   // Hauptteil
out.push(SM.pvEntry({se: [['main', 0, 240]], cu: [5, 30], ev: []}, D).t);                                   // main ab 0 zaehlt nicht: 2. Hotcue
out.push(SM.pvEntry({se: [], cu: [5], ev: [['drop', 70, 71]]}, D).t);                                        // nur ein Hotcue: Drop
out.push(SM.pvEntry({}, D).t);                                                                               // nichts: ein Drittel
out.push(SM.pvEntry(null, 50).t);                                                                            // kurz: vom Anfang
out.push(SM.pvPoints({se: [['main', 20, 60]], cu: [5, 21, 30], ev: [['drop', 40, 41]]}, D).map(x => x.k + x.t).join(','));
console.log(JSON.stringify(out));
"""
r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
res = json.loads(r.stdout or "null")
check(res == [20, 30, 70, 80, 0, "cue5,main20,cue30,drop40"], "Einstieg: Hauptteil, 2. Hotcue, Drop, Drittel, kurz vorne; Stellen fuer ⏭: " + str(res))
check("const v = fadeTo !== null ? fadeTo : audio.volume;" in txt and "Math.abs(audio.volume - lastV) > 0.001" in txt,
      "Einblenden: Ziel bleibt die Lautstaerke davor, auch wenn das naechste Lied kommt (Fehlerbericht 14.11.2026: beim dritten Lied kein Ton)")
check("bar.pv = SM.preview(audio" in txt and "opt.start !== false" in txt, "jede Vorhoer-Leiste (SM.playBar)")
sm = os.path.join(ROOT, "pi", "static", "sm")
check("SM.preview(player, { pos: $('pos')" in open(os.path.join(sm, "music.js"), encoding="utf-8").read(), "Musik-Datenbank (eigene Leiste)")
check("SM.playBar(audio, { start: false" in open(os.path.join(sm, "tagedit.js"), encoding="utf-8").read(), "Tag-Editor (Cover-Wellenform) bleibt beim Anfang")
for f in ("core.js", "music.js", "tagedit.js"):
    check(subprocess.run(["node", "--check", os.path.join(sm, f)]).returncode == 0, f + " ohne Syntaxfehler")
finish("test_vorhoeren_ab")
