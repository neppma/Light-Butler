"""Effektband: soundgesteuerte Presets (AudioReactive in WLED) tragen im Panel ein Notensymbol."""
import os
import subprocess
import tempfile

from _common import build, check, finish

import texts
import webpanel

rig, sh = build()
eb = sh.snapshot()["eb"]
ids = {i for i, _ in eb["names"]}
check(eb["sound_ids"] == [6, 10, 17, 18, 19, 20, 22, 23, 24, 25, 26, 30], "soundgesteuerte Presets laut WLED-Effektdaten")
check(set(eb["sound_ids"]) <= ids, "alle markierten Presets gibt es im Panel")
check(not set(eb["sound_ids"]) & {21, 36, 37, 38, 39, 2, 35}, "DEMO, M-Club Effekt, eigene Presets, Scanner und Solid weiss nicht markiert")
page = webpanel.make_page()
check("snd.includes(id)?' <span class=\"ebsnd\"" in page, "Panel: Notensymbol am Preset-Knopf")
check("JSON.stringify([E.names,snd])" in page, "Knoepfe werden neu gebaut, wenn sich die Liste aendert")
hint = str(texts.catalog())
check("♫ = reagiert auf Musik" in hint and "♫ = reacts to the music" in hint, "Hinweis unter den Presets erklaert das Symbol (de/en)")
js = page.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True                                             # ohne node (am Pi) nicht pruefbar
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_effektband_sound")
