"""Merkliste "Fehlt mir" (Wunsch von Markus, 14.11.2026): fehlende Album-Titel und leere Suchen merken; was spaeter in die
Sammlung kommt, zeigt die Liste nicht mehr (kein Haken "besorgt")."""
import os
import subprocess
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
from showman import missing as mm  # noqa: E402

tmp = tempfile.mkdtemp()
LIB = [{"artist": "Falco", "name": "Jeanny", "album": "Falco 3"}]
M = mm.Missing(tmp, lambda: LIB, now=lambda: 100)
k1 = M.add("Rainhard Fendrich", "Mundgeruch", "Ich wollte nie einer von denen sein")
k2 = M.add(q="Halt mi net für'n Narrn  Fendrich")
check(k1 == "t:rainhard fendrich|mundgeruch" and k2 == "q:halt mi net für'n narrn fendrich", "Schluessel wie im Browser: " + k1 + " / " + k2)
check(M.add("Rainhard Fendrich", "Mundgeruch") == k1 and len(M.items) == 2, "doppelt merken: nur einmal")
st = M.state()
check([x["k"] for x in st["items"]] == [k1, k2] or [x["k"] for x in st["items"]] == [k2, k1], "beide gezeigt")
check(st["hidden"] == 0 and set(st["keys"]) == {k1, k2}, "nichts ausgeblendet")
LIB.append({"artist": "Rainhard Fendrich & Vienna Symphony", "name": "Mundgeruch (Live)", "album": "Live"})
st = M.state()
check([x["k"] for x in st["items"]] == [k2] and st["hidden"] == 1 and k1 in st["keys"], "Lied jetzt da (Klammer, Begleitung egal): ausgeblendet, bleibt gemerkt")
LIB.append({"artist": "Rainhard Fendrich", "name": "Halt mi net für'n Narrn", "album": ""})
check(M.state()["items"] == [] and M.state()["hidden"] == 2, "Suchtext: alle Woerter in einem Lied -> ausgeblendet")
LIB.append({"artist": "Andere", "name": "Kinder"})
M.add("Rainhard Fendrich", "Kinder")
check(len(M.state()["items"]) == 1, "gleicher Titel, anderer Interpret: fehlt weiter")
M2 = mm.Missing(tmp, lambda: [])
check(len(M2.items) == 3 and M2.remove(k1) == 1 and len(M2.state()["items"]) == 2, "nach Neustart gemerkt, entfernen")
for bad in ({"a": "X"}, {}):
    try:
        M2.add(**bad)
        check(False, "ohne Titel abgelehnt")
    except ValueError:
        check(True, "ohne Titel abgelehnt")
# Schluessel im Browser gleich wie am Pi
core = open(os.path.join(ROOT, "pi", "static", "sm", "core.js"), encoding="utf-8").read()
a = core.index("  SM.missKey = "); b = core.index("  SM.missLoad = ")
js = "const SM = {};\n" + core[a:b] + "console.log(SM.missKey({a: ' Rainhard  Fendrich', t: 'Mundgeruch'}) + '#' + SM.missKey({q: \"Halt mi net für'n Narrn  Fendrich\"}));"
r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
check(r.stdout.strip() == k1 + "#" + k2, "SM.missKey = entry_key: " + r.stdout + r.stderr)
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('op == "missing_add"' in api and 'op == "missing_del"' in api and '"/api/sm/missing"' in api and '"/musik/fehlt"' in api, "Befehle, Liste, Seite")
SMD = os.path.join(ROOT, "pi", "static", "sm")
rd = lambda f: open(os.path.join(SMD, f), encoding="utf-8").read()
check("SM.missBtn({ a: t.artist" in rd("albums.js") and "SM.missBtn({ q: sq })" in rd("music.js"), "Merken bei Alben und leerer Suche")
check("'/musik/fehlt'" not in rd("nav.js") and "href: '/musik/fehlt'" in rd("care.js") and rd("care.js").index("id: 'import'") < rd("care.js").index("id: 'fehlt'"),
      "nicht im Menue, sondern in der Datenpflege beim Import (Wunsch 14.11.2026)")
check('data-back="/musik/pflege"' in rd("fehlt.html"), "zurueck fuehrt zur Datenpflege")
for f in ("core.js", "albums.js", "music.js", "fehlt.js", "nav.js", "care.js"):
    check(subprocess.run(["node", "--check", os.path.join(SMD, f)]).returncode == 0, f + " ohne Syntaxfehler")
finish("test_fehlt_mir")
