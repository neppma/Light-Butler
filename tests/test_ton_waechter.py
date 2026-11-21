"""Ton vom Musik-Rechner (21.11.2026, Fehlerbericht: Ton zum Pi riss mitten im Auto-DJ ab): Namensabfrage nie im
Ton-Faden, Waechter oeffnet den Eingang neu, wenn Core Audio nichts mehr liefert."""
import os
import socket
import sys
import time
import types

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, check, finish  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import audio_send                                # noqa: E402

lookups = []
orig = socket.gethostbyname


def slow_lookup(name):
    lookups.append(name)
    return "127.0.0.1"


socket.gethostbyname = slow_lookup
sent = []
snd = audio_send.AudioSender("pi.test", sd_mod=object(), sock=types.SimpleNamespace(sendto=lambda p, a: sent.append(a)),
                             log=lambda m: None)
snd._run = True                                  # wie im Betrieb: der Faden laeuft
block = np.zeros((1024, 2), dtype=np.float32)
snd._callback(block, 1024, None, None)
check(not lookups and not sent, "Ton-Faden fragt nie selbst nach dem Namen (ohne Adresse: verwerfen)")
snd.resolve()
n0 = len(lookups)
snd.addr_t -= 100                                # Adresse ist alt
for _ in range(5):
    snd._callback(block, 1024, None, None)
check(len(lookups) == n0 and sent and sent[-1] == ("127.0.0.1", 9022), "Ton nimmt die bekannte Adresse, auch wenn sie alt ist")
check(snd.last_cb is not None and time.monotonic() - snd.last_cb < 1, "Zeit des letzten Blocks gemerkt")
snd._run = False
fresh = audio_send.AudioSender("pi.test", sd_mod=object(), sock=types.SimpleNamespace(sendto=lambda p, a: None), log=lambda m: None)
fresh.feed(block, 44100)
check(fresh.addr == ("127.0.0.1", 9022), "ohne Faden (Tests, Radio): einmal selbst nachschlagen")

# Waechter: Eingang offen, aber kein Block mehr -> neu oeffnen
logs = []


class Stream:
    active = True

    def __init__(self, **kw):
        self.kw = kw
        Stream.made += 1

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


Stream.made = 0
SD = types.SimpleNamespace(query_devices=lambda: [{"name": "BlackHole 2ch", "max_input_channels": 2, "default_samplerate": 48000}],
                           InputStream=lambda **kw: Stream(**kw))
w = audio_send.AudioSender("pi.test", sd_mod=SD, sock=types.SimpleNamespace(sendto=lambda p, a: None), log=logs.append)
audio_send.STALL_S = 0.3
real_sleep = time.sleep
time.sleep = lambda s: real_sleep(0.05)
w.start()
real_sleep(0.4)
check(Stream.made >= 1, "Eingang geoeffnet")
real_sleep(0.6)
check(w.restarts >= 1 and any("liefert seit" in m for m in logs), "kein Block mehr: Waechter meldet und schliesst: %s" % logs[-1:])
real_sleep(0.3)
w.stop()
time.sleep = real_sleep
socket.gethostbyname = orig
check(Stream.made >= 2, "danach neu geoeffnet (%d)" % Stream.made)
finish("test_ton_waechter")
