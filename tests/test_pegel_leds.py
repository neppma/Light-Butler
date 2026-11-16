"""Pegelmeter in den Einstellungen (Audio-Eingang) als LED-Kette (Wunsch 12.11.2026): feste Farbbereiche statt eines Verlaufs,
der mit dem Pegel mitwandert; gruen bis -12,5 dB, gelb bis -2,5 dB, rot bis 0 dB, Spitze im gelben und roten Bereich blinkt."""
import os
import re
import subprocess
import sys

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
import webpanel                              # noqa: E402

pg = webpanel.make_page()
js = pg[pg.index("const LEDS="):]
js = js[:js.index("function ledIdx")] + js[js.index("function ledIdx"):].split("\n", 1)[0]
r = subprocess.run(["node", "-e", js + "\nconst z=[...Array(LEDS).keys()].map(ledZone);"
                    "console.log(JSON.stringify({z, a: ledIdx(-100), b: ledIdx(-60), c: ledIdx(-13), d: ledIdx(-12), e: ledIdx(-3), f: ledIdx(-1), g: ledIdx(3)}))"],
                   capture_output=True, text=True)
import json                                  # noqa: E402
d = json.loads(r.stdout)
z = d["z"]
check(len(z) == 24 and z.count("") == 19 and z.count("y") == 4 and z.count("r") == 1 and z.index("y") == 19 and z[-1] == "r",
      "24 LEDs: 19 gruen, 4 gelb, 1 rot: " + str(z))
check(d["a"] == -1 and d["b"] == -1 and d["c"] == 18 and d["d"] == 19 and d["e"] == 22 and d["f"] == 23 and d["g"] == 23,
      "Pegel -> letzte leuchtende LED: " + str(d))
check('id="aud_bar">' in pg and "linear-gradient(90deg,#2ecc40" not in pg and ".meter i.pk.y,.meter i.pk.r{animation:bl" in pg,
      "kein mitwandernder Verlauf mehr, Spitze blinkt im gelben und roten Bereich")
check(not re.search(r"aud_hold", pg), "kein weisser Strich mehr")
finish("test_pegel_leds")
