"""Panel, Zeile Mixxx: Liedverlauf als Balken (Lautstaerkekurve, Aufbau, Break, Drop, Strich an der aktuellen Stelle) und
die Zeiten gespielt / gesamt vor der Restzeit. Die Mac-Bruecke schickt dafuer die verkleinerte Kurve mit dem Plan."""
import os
import sys

from _common import ROOT, build, check, finish, Clock

import webpanel
from mixxx_link import MixxxLink

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from mixxx_bridge import compact_energy    # noqa: E402

# ---- Mac: Kurve verkleinern ---------------------------------------------------------------------------------------
lv = [i % 100 for i in range(600)]
ce = compact_energy(lv)
check(len(ce) == 200 and all(0 <= v <= 100 for v in ce), "600 Sekunden -> 200 Werte")
check(compact_energy([5, 90, 5]) == [5, 90, 5] and compact_energy([]) == [], "kurze Lieder unveraendert, leer bleibt leer")
check(max(compact_energy([0] * 999 + [100])) == 100, "kurze laute Stelle bleibt sichtbar (Maximum)")

# ---- Pi: Plan mit Kurve -> Status -> Panel ---------------------------------------------------------------------------
rig, sh = build()
link = MixxxLink(0)
now = 1000.0
plan = {"type": "plan", "d": 1, "key": "k", "title": "Artist - Song", "du": 240.0,
        "ev": [["build", 60.0, 76.0, 0, ""], ["drop", 76.0, 76.0, 0.9, "b"], ["break", 120.0, 136.0, 0, ""]],
        "en": [10, 40, 80, 120, -5, "x", 55]}
link.feed(plan, now)
link.feed({"d": 1, "pp": 0.25, "du": 240.0, "rr": 1.0, "bp": 128.0, "pl": 1, "tl": 1, "vo": 1.0}, now)
st = link.status(now, sh.cfg)
bar = st.get("bar")
check(st["plan"] and bar is not None, "Status enthaelt den Liedverlauf")
check([e[0] for e in bar["ev"]] == ["build", "drop", "break"] and bar["ev"][0][1:] == [60.0 + sh.cfg["mixxx_shift_s"], 76.0 + sh.cfg["mixxx_shift_s"]],
      "Abschnitte mit Start und Ende")
check(bar["en"] == [10, 40, 80, 100, 0, 55], "Kurve auf 0-100 begrenzt, Unsinn verworfen")
link.feed(dict(plan, en=None), now)
check(link.status(now, sh.cfg)["bar"]["en"] == [], "alte Analyse ohne Kurve: nur Abschnitte")

sh.mx = dict(st)
mp = sh._mx_public()
check(mp["el"] == 60.0 and mp["tot"] == 240.0 and mp["left"] == 180.0, "gespielt 1:00, gesamt 4:00, Rest 3:00")
sh.mx = dict(st, rate=1.2)
mp = sh._mx_public()
check(mp["el"] == 50.0 and mp["tot"] == 200.0, "bei Pitch +20 % in echter Zeit")
check(mp["bar"] is bar, "Panel bekommt den Verlauf")

page = webpanel.make_page()
check('<canvas id="mxbar"></canvas>' in page and "function drawMxBar(m)" in page, "Panel: Balken unter der Mixxx-Zeile")
check("ms(m.el)+' / '+ms(m.tot)" in page and 'class="mxtot"' in page, "Panel: gespielt / gesamt vor der Restzeit")
check("drawMxBar(null)" in page and "if(!m||!m.dur){const g0=cv.getContext('2d')" in page and "g0.setLineDash([4,4])" in page,
      "ohne Lied: gestrichelter Platzhalter in gleicher Hoehe")
finish("test_mixxx_verlauf")
