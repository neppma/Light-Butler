"""Audio-Einstellungen am Mac pruefen (Wunsch von Markus 25.11.2026): BlackHole soll auf 44,1 kHz stehen (Mixxx stellte es
mit Abtastrate 48000 um), im Multiausgangsgeraet Driftkorrektur bei jedem Geraet ausser dem Primaergeraet. Der Helfer
prueft das nur (nie aendern), schickt es an den Pi, das Panel warnt. Geprueft ohne CoreAudio: Bewertung, Nachricht des
Helfers, Pi merkt sie hoechstens 3 min, zaehlt nicht als Mixxx verbunden, Panel-Hinweis."""
import json
import os
import sys

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "mac", "helper"))
import mac_audio_check  # noqa: E402
from mac_audio_check import warnings  # noqa: E402

BH = {"id": 60, "name": "BlackHole 2ch", "uid": "BlackHole2ch_UID", "rate": 44100.0, "aggregate": False}
SPK = {"id": 116, "name": "MacBook Air-Lautsprecher", "uid": "BuiltInSpeakerDevice", "rate": 44100.0, "aggregate": False}
MULTI = {"id": 56, "name": "Multiausgangsgerät", "uid": "~:AMS2", "rate": 44100.0, "aggregate": True}


def subs(drift_bh=True, drift_spk=False, main="BuiltInSpeakerDevice"):
    return lambda i: ([("BlackHole 2ch", "BlackHole2ch_UID", drift_bh), ("MacBook Air-Lautsprecher", "BuiltInSpeakerDevice", drift_spk)], main)


check(warnings([BH, SPK, MULTI], 56, subs()) == [], "wie empfohlen: keine Warnung")
w = warnings([dict(BH, rate=48000.0), SPK, dict(MULTI, rate=48000.0)], 56, subs())
check(len(w) == 2 and "48,0 kHz" in w[0] and "Mixxx" in w[0] and "Multiausgangsgerät" in w[1], "48 kHz: Warnung mit Hinweis auf Mixxx")
w = warnings([BH, SPK, MULTI], 56, subs(drift_bh=False))
check(len(w) == 1 and "Driftkorrektur bei BlackHole 2ch" in w[0], "Driftkorrektur bei BlackHole aus: Warnung")
check(warnings([BH, SPK, MULTI], 56, subs(drift_bh=True, drift_spk=False, main="BuiltInSpeakerDevice")) == [],
      "Primaergeraet ohne Driftkorrektur: richtig, keine Warnung")
w = warnings([BH, SPK, MULTI], 56, subs(drift_bh=False, drift_spk=True, main="BlackHole2ch_UID"))
check(w == [], "BlackHole als Primaergeraet, Lautsprecher mit Driftkorrektur: auch richtig")
agg2 = dict(MULTI, id=70)
check(warnings([BH, agg2], 0, lambda i: ([("Andere", "X", False), ("Noch eins", "Y", False)], "X")) == [],
      "Aggregat ohne BlackHole: geht den Light-Butler nichts an")
if sys.platform != "darwin":
    check(mac_audio_check.check() == [], "nicht am Mac: keine Pruefung")

# Helfer: schickt die Warnungen an den Pi (UDP 9020), hoechstens alle CHECK_S
import helper  # noqa: E402
import mixxx_bridge  # noqa: E402


class Sock:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((json.loads(data.decode()), addr))


clock = [0.0]
s = Sock()
logs = []
mixxx_bridge._pi_retry = 0.0
p = helper.AudioCheckPart("10.0.0.5", checker=lambda: ["BlackHole 2ch steht auf 48,0 kHz"], sock=s, log=logs.append,
                          clock=lambda: clock[0])
p.update()
check(s.sent and s.sent[0][0] == {"type": "macaudio", "w": ["BlackHole 2ch steht auf 48,0 kHz"]} and s.sent[0][1] == ("10.0.0.5", 9020),
      "Helfer schickt die Warnung an den Pi")
check(logs and "48,0" in logs[-1], "und schreibt sie ins Protokoll")
p.update()
check(len(s.sent) == 1, "nicht oefter als alle %d s" % p.CHECK_S)
clock[0] += p.CHECK_S + 1
p.checker = lambda: []
p.update()
check(s.sent[-1][0]["w"] == [] and "in Ordnung" in logs[-1], "behoben: leere Liste, Warnung verschwindet")
p.checker = lambda: 1 / 0
clock[0] += p.CHECK_S + 1
check(p.update() is None, "Fehler in der Pruefung: Helfer laeuft weiter")

# Pi: merkt die Warnung, nur solange der Helfer sie schickt; zaehlt nicht als "Mixxx verbunden"
sys.path.insert(0, os.path.join(ROOT, "pi"))
import mixxx_link  # noqa: E402
link = mixxx_link.MixxxLink(0)
t0 = 1000.0
link.feed({"type": "macaudio", "w": ["BlackHole 2ch steht auf 48,0 kHz"]}, now=t0, addr="10.0.0.5")
check(link.mac_audio_warn(t0 + 10) == ["BlackHole 2ch steht auf 48,0 kHz"], "Pi merkt die Warnung")
check(link.mac_audio_warn(t0 + 200) == [], "nach 3 min ohne Helfer: weg")
check("macaudio" in mixxx_link.LIB_TYPES, "zaehlt nicht als Mixxx verbunden")
link.feed({"type": "macaudio", "w": "kaputt"}, now=t0 + 300)
check(link.mac_audio_warn(t0 + 301) == [], "falsche Daten: keine Warnung")

import webpanel  # noqa: E402
pg = webpanel.make_page()
check("Ton am Musik-Rechner" in pg and "S.mac_audio" in pg, "Panel: Hinweis in der Hinweiszeile, Antippen zeigt die Einzelheiten")
from _common import build  # noqa: E402
rig, sh = build()
check(sh.snapshot()["mac_audio"] == [], "Status: ohne Warnung leer")
txt = open(os.path.join(ROOT, "mac", "helper", "install_helper.sh"), encoding="utf-8").read()
check("mac_audio_check.py" in txt, "Helfer-Installation kopiert mac_audio_check.py")
finish("test_mac_ton_pruefung")
