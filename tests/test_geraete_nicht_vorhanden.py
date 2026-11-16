"""Geraete nicht vorhanden (Wunsch von Markus, 14.11.2026): je Ausgabe (DMX, WLED, Nanoleaf) eine dritte Stellung. Nicht
vorhanden: nichts senden, keine orange Warnung, keine Erreichbarkeits-Pruefung (kein rotes "fehlt"). Standard: vorhanden."""
import os
import re
import time

from _common import ROOT, build, Clock, check, finish

import dmx


class Snd:
    def __init__(self):
        self.n = 0

    def send(self, data):
        self.n += 1

    def close(self):
        pass


rig, sh = build()
check(all(sh.cfg[k + "_have"] > 0.5 for k in ("ola", "wled", "nano")), "Standard: alles vorhanden (Licht wie bisher)")
check(all(sh.out_on(k) for k in ("ola", "wled")), "an und vorhanden: Ausgabe an")
snds = {}
o = dmx.Output(rig, lambda ip: snds.setdefault(ip, Snd()))
o.http = lambda ip, on: None
sh.output = o
sh.cfg.set("wled_have", 0)
Clock(sh).run(1)
wl = sh._wled_targets()
check(wl and all(not o.is_sending(t) for t in wl) and o.is_sending(rig.target), "WLED nicht vorhanden: WLED aus, DMX weiter an")
st = sh.snapshot() if hasattr(sh, "snapshot") else {}
check(st.get("wled_have") is False and st.get("wled_out") is True and st.get("ola_have") is True, "Status meldet es dem Panel")
sh.cfg.set("wled_have", 1)
sh.cfg.set("ola_have", 0)
Clock(sh).run(1)
check(o.mode[rig.target] in ("closing", "off") and all(o.is_sending(t) for t in wl), "DMX nicht vorhanden: DMX schaltet ab (erst Blackout-Bilder), WLED wieder an")

wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
for k in ("ola", "wled", "nano"):
    check('id="%s_none"' % k in wp and "c({set:{%s_out:0,%s_have:0}})" % (k, k) in wp and "c({set:{%s_out:1,%s_have:1}})" % (k, k) in wp,
          k + ": Knoepfe Aus, An, Nicht vorhanden")
check("S.wled_out===false&&S.wled_have!==false?wbtn(" in wp and "S.nano_out===false&&S.nano_have!==false?wbtn(" in wp and "S.ola_out===false&&S.ola_have!==false?wbtn(" in wp,
      "keine orange Warnung, wenn nicht vorhanden")
check('if (n in names.values() and not have("wled")) or (n == "Nanoleaf" and not have("nano")):' in wp and 'not have("ola")' in wp, "keine Erreichbarkeits-Pruefung")
finish("test_geraete_nicht_vorhanden")
