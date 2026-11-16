"""Effektband ohne Ton (eb_no_sound): Liegt am Mikrofon des Effektbands kein Ton an, waehlt die Automatik keine
soundgesteuerten Presets (preset_sound) - weder nach Stufe noch als Drop-Akzent, in der Szenen-Automatik oder in festen
Szenen. Von Hand gewaehlte Presets bleiben. Aus = wie bisher."""
import os
import subprocess
import tempfile

from _common import build, check, finish, Clock

import webpanel

rig, sh = build(seed=4)
eb = sh.presets[0]
snd = set(eb.extra["preset_sound"])
roles0 = eb.extra["preset_roles"]
check(sh.cfg["eb_no_sound"] == 0.0 and sh.eb_roles(eb) is roles0, "Standard aus: Rollen wie bisher")
check(any(p in snd for p in roles0["party"]), "ohne die Einstellung enthaelt Party soundgesteuerte Presets")

sh.cfg.set("eb_no_sound", 1)
r = sh.eb_roles(eb)
check(all(p not in snd for lst in r.values() for p in lst), "an: keine soundgesteuerten Presets in den Rollen")
check(r["party"] == [p for p in roles0["party"] if p not in snd] and r["party"], "Party behaelt die anderen (z. B. Rot BPM, Juggle)")
check(r["idle"] == [36], "Playlist ohne Ton bleibt (36), die soundgesteuerte (26) faellt weg")
check(sh.eb_no_sound(eb, 25) == 0 and sh.eb_no_sound(eb, 31) == 31, "festes Preset: soundgesteuert -> automatisch, sonst bleibt es")
check(all(sh._sa_pick_preset(k) not in snd for k in (0, 1, 3) for _ in range(20)), "Szenen-Automatik: nie soundgesteuert")

used = set()
clk = Clock(sh)
clk.run(240, lambda t: used.add(int(eb.values.get("preset", 0))))
check(used and not (used & snd), f"240 s AUTO: nur Presets ohne Ton ({sorted(used)})")

sc = next(s for s in sh.scene_defs if s.name == "Austria")
old_preset = sc.preset
sc.preset = 25                                         # Szene mit soundgesteuertem Preset
sh.command({"scene": sc.name})
clk.run(1)
check(int(eb.values["preset"]) not in snd, "feste Szene mit Ripple Peak: anderes Preset")
sh.command({"eb_preset": 25})
clk.run(1)
check(int(eb.values["preset"]) == 25, "von Hand gewaehlt: bleibt (Ripple Peak)")
sc.preset = old_preset

s = sh.snapshot()["eb"]
check(s["no_sound"] is True, "Panel erfaehrt die Einstellung")
p = webpanel.make_page()
check("b.classList.toggle('nosnd',!!E.no_sound&&snd.includes(id))" in p and "#ebgrid button.nosnd{opacity:.45}" in p,
      "Panel: soundgesteuerte Presets blass")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_effektband_ohne_ton")
