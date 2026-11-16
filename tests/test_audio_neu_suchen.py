"""Soundkarten neu suchen ohne Neustart (Wunsch von Markus, 07.11.2026: Behringer UCA202 nach dem Start eingesteckt):
PortAudio neu einlesen, denselben Eingang nach Namen wieder oeffnen, Ton vom Mac bleibt unberuehrt."""
import os
import sys
import types

from _common import ROOT, check, finish

import audio  # noqa: E402

DEVS = [{"name": "bcm2835 Headphones: - (hw:0,0)", "max_input_channels": 0, "default_samplerate": 44100},
        {"name": "USB Audio Device: - (hw:1,0)", "max_input_channels": 2, "default_samplerate": 44100}]
NEW = [{"name": "bcm2835 Headphones: - (hw:0,0)", "max_input_channels": 0, "default_samplerate": 44100},
       {"name": "USB Audio CODEC: - (hw:2,0)", "max_input_channels": 2, "default_samplerate": 48000},
       {"name": "USB Audio Device: - (hw:1,0)", "max_input_channels": 2, "default_samplerate": 44100}]


class FakeSD(types.ModuleType):
    def __init__(self):
        super().__init__("sounddevice")
        self.devs, self.calls = list(DEVS), []

    def query_devices(self, idx=None, kind=None):
        return self.devs if idx is None else self.devs[idx]

    def _terminate(self):
        self.calls.append("terminate")

    def _initialize(self):
        self.calls.append("initialize")
        self.devs = list(NEW)


fake = FakeSD()
sys.modules["sounddevice"] = fake
a = audio.Analyzer(audio_file=None)
opened = []
a._close_stream = lambda: opened.append("zu")
a.start = lambda: opened.append(("auf", a.device))
a.device, a.dev_name = 1, "USB Audio Device: - (hw:1,0)"
names = [d["name"] for d in a.list_devices()]
check("USB Audio CODEC: - (hw:2,0)" not in names, "vorher: das neue Geraet fehlt")
devs = a.rescan(sd=fake)
check(fake.calls == ["terminate", "initialize"], "PortAudio neu eingelesen")
check(any(d["name"] == "USB Audio CODEC: - (hw:2,0)" for d in devs), "danach: UCA202 (USB Audio CODEC) in der Liste")
check(opened == ["zu", ("auf", 2)], "derselbe Eingang wieder offen, unter seiner neuen Nummer")
check(a.error == "", "kein Fehler")

from audio_net import NET_NAME  # noqa: E402
fake.calls, opened[:] = [], []
a.device, a.dev_name = NET_NAME, NET_NAME
a.rescan(sd=fake)
check(fake.calls == ["terminate", "initialize"] and opened == [], "Ton vom Mac: laeuft weiter, nichts geschlossen")


def boom():
    raise RuntimeError("Geraet weg")


fake.calls, opened[:] = [], []
a.device, a.dev_name = 1, "Ausgesteckt: - (hw:3,0)"
a.start = boom
a.rescan(sd=fake)
check("nach dem Neusuchen nicht verfuegbar" in a.error, "alter Eingang ausgesteckt: Hinweis im Panel, kein Absturz")

src = open(os.path.join(ROOT, "pi", "show.py"), encoding="utf-8").read()
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check('if a_.get("rescan") and hasattr(self.src, "rescan"):' in src, "Befehl audio.rescan in der Show")
check('id="aud_scan"' in wp and "c({audio:{rescan:true}})" in wp, "Knopf Geraete neu suchen in den Audio-Einstellungen")
del sys.modules["sounddevice"]
finish("Audio neu suchen")
