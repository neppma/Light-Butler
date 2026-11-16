"""Hauptdimmer, Gruppen-Dimmer und Blitze pro Sekunde bleiben ueber einen Neustart erhalten (levels.json neben
settings.json). Gespeichert wird gesammelt hoechstens alle 2 s und beim Beenden. Die Strobe-Erlaubnis wird nie gespeichert:
ohne sie bleibt es bei hoechstens 3 Blitzen pro Sekunde."""
import json
import os
import tempfile
import time

from _common import PI, Clock, check, finish

import show as sw
from dmx import Rig
from audio import Simulator

tmp = tempfile.mkdtemp()
lpath = os.path.join(tmp, "levels.json")


def mk(strobe=True):
    rig = Rig(os.path.join(PI, "fixtures.yaml"))
    sh = sw.Show(rig, Simulator(), aim_file=os.devnull, strobe=strobe, settings_file=os.path.join(tmp, "settings.json"),
                 scenes_file=None, texts_file=None)
    return sh


sh = mk()
check(sh.master == 1.0 and all(v == 1.0 for v in sh.glevel.values()) and sh.blitz_hz == 5.0, "ohne levels.json: Startwerte")
clk = Clock(sh)
sh.command({"master": 0.4})
sh.command({"glevel": {"bar": 0.25, "nano": 0.0}})
sh.command({"blitz_hz": 10})
clk.run(0.5)
check(not os.path.exists(lpath), "nicht sofort gespeichert (Fader senden viel)")
sh.levels_dirty_t = time.monotonic() - 2.5                 # 2 s sind vergangen
clk.run(0.1)
d = json.load(open(lpath))
check(d["master"] == 0.4 and d["glevel"]["bar"] == 0.25 and d["glevel"]["nano"] == 0.0 and d["blitz_hz"] == 10.0,
      "nach 2 s gespeichert: Master, Gruppen, Blitze pro Sekunde")
check(sh.levels_dirty_t is None, "danach nichts mehr offen")
n = os.path.getmtime(lpath)
clk.run(3)
check(os.path.getmtime(lpath) == n, "ohne Aenderung wird nicht geschrieben")

sh.command({"master": 0.7})
sh.close()
check(json.load(open(lpath))["master"] == 0.7, "beim Beenden gespeichert")

sh2 = mk(strobe=False)
check(sh2.master == 0.7 and sh2.glevel["bar"] == 0.25 and sh2.glevel["nano"] == 0.0 and sh2.blitz_hz == 10.0,
      "nach dem Neustart: Werte wieder da")
check(sh2.strobe is False and sh2._blitz_rate() <= 3.0, "ohne Strobe-Erlaubnis trotzdem hoechstens 3 Blitze pro Sekunde")
check("strobe" not in json.load(open(lpath)), "Strobe-Erlaubnis wird nie gespeichert")
sh2.command({"glevel_reset": True})
sh2.close()
check(all(v == 1.0 for v in json.load(open(lpath))["glevel"].values()), "Gruppen zuruecksetzen wird gespeichert")

json.dump({"master": 7, "glevel": {"bar": -1, "gibtsnicht": 0.5}, "blitz_hz": 99}, open(lpath, "w"))
sh3 = mk()
check(sh3.master == 1.0 and sh3.glevel["bar"] == 0.0 and "gibtsnicht" not in sh3.glevel and sh3.blitz_hz <= 10.0,
      "Werte begrenzt, Unbekanntes ignoriert")
open(lpath, "w").write("{kaputt")
sh4 = mk()
check(sh4.master == 1.0 and sh4.blitz_hz == 5.0, "defekte levels.json: Startwerte")

finish("test_dimmer_speichern")
