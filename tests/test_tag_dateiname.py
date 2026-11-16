"""Tag-Fenster, Knopf "Aus Dateiname" (Wunsch 12.11.2026): Titel, Interpret und Tracknummer aus dem MP3-Dateinamen, das Album aus
dem Ordner. Kommt nur in die Felder, geschrieben wird erst mit "In die MP3 schreiben"."""
import json
import os
import shutil
import subprocess

from _common import ROOT, check, finish

JS = os.path.join(ROOT, "pi", "static", "sm", "tagedit.js")
src = open(JS, encoding="utf-8").read()
CASES = {
    "/V/musik/U-MUSIK/Artists/Andreas Gabalier/Andreas Gabalier - Hulapalu.mp3": {"artist": "Andreas Gabalier", "title": "Hulapalu"},
    "/V/x/Pink Floyd - The Wall (1979)/03 - Pink Floyd - Another Brick in the Wall, Pt. 2.mp3":
        {"track": "3", "artist": "Pink Floyd", "title": "Another Brick in the Wall, Pt. 2", "album": "The Wall"},
    "/V/x/Bravo Hits 100/CD 1/07 - Rihanna - Diamonds.mp3": {"track": "7", "artist": "Rihanna", "title": "Diamonds", "album": "Bravo Hits 100"},
    "/V/musik-import/neu/19th Floor - Bobby Richards.mp3": {"artist": "19th Floor", "title": "Bobby Richards"},
    "/V/musik/U-MUSIK/99 Luftballons.mp3": {"title": "99 Luftballons"},
    "/V/x/Album/Lied_pn (2).mp3": {"title": "Lied", "album": "Album"},
}
node = shutil.which("node")
if node:
    code = "global.window={};require(" + json.dumps(JS) + ");const f=window.SM.nameTags;console.log(JSON.stringify(" + json.dumps(list(CASES)) + ".map(f)))"
    got = json.loads(subprocess.run([node, "-e", code], capture_output=True, text=True).stdout)
    for (p, want), g in zip(CASES.items(), got):
        check(g == want, os.path.basename(p) + " -> " + json.dumps(g, ensure_ascii=False))
else:
    print("  (node fehlt: Zerlegen nicht geprueft)")
check('id="tgname"' in src and "$('tgname').onclick" in src and "In die MP3 schreiben" in src, "Knopf unten im Tag-Fenster, nur in die Felder")
# Fehlerbericht 12.11.2026: im Import war das Tag-Fenster oben abgeschnitten, kein Scrollen (Seite setzt .box max-height:none)
css = open(os.path.join(ROOT, "pi", "static", "sm", "sm.css"), encoding="utf-8").read()
imp = open(os.path.join(ROOT, "pi", "static", "sm", "import.html"), encoding="utf-8").read()
check(".modal>.box{max-height:calc(100vh - 24px);" in css and "overflow-y:auto" in css and ".modal>.tagbox" in css and "max-height: none" in imp,
      "Fenster scrollen immer selbst, auch wo die Seite .box ohne Hoehengrenze setzt")
finish("test_tag_dateiname")
