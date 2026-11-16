"""Effektband bei den Licht-Mix-Knoepfen: Sparkle (Sternenhimmel) -> Preset 37 Sparkle, Karussell -> 38, Disco -> 39
(in WLED angelegt), Scanner -> 2 Scanner. Das Effektband leuchtet dabei; Chase bleibt dunkel. Andere Szenen unveraendert."""
from _common import PI, build, Clock, check, finish

import yaml
import os

y = yaml.safe_load(open(os.path.join(PI, "fixtures.yaml")))
eb = next(f for f in y["fixtures"] if f["name"] == "effektband")
check(eb["preset_mix"] == {"Sternenhimmel": 37, "Karussell": 38, "Discokugel": 39, "Scanner": 2}, "Zuordnung in fixtures.yaml")
check(eb["preset_names"][37] == "Sparkle" and eb["preset_names"][38] == "Karussell" and eb["preset_names"][39] == "Disco",
      "Namen der neuen Presets")

for btn, pid in (("Sternenhimmel", 37), ("Karussell", 38), ("Discokugel", 39), ("Scanner", 2)):
    for speed in ("slow", "fast"):
        rig, sh = build(seed=3)
        clk = Clock(sh)
        clk.run(3)
        sh.command({"mix": btn})
        sh.command({"speed": speed})
        clk.run(1)
        v = rig["effektband"].values
        check(v["preset"] == pid and v["dimmer"] > 0, f"{btn} ({speed}): Effektband Preset {pid}, an")

rig, sh = build(seed=3)
clk = Clock(sh)
clk.run(3)
sh.command({"mix": "nach aussen"})
clk.run(1)
check(rig["effektband"].values["dimmer"] == 0, "Chase-Out: Effektband aus")
sh.command({"mix": "Karussell"})
sh.command({"color": "rot"})
clk.run(0.5)
check(rig["effektband"].values["preset"] == 38, "Karussell mit Farbe Rot: weiter das Karussell-Preset")
finish("test_effektband_mix")
