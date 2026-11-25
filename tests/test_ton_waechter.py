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

# Waechter: Eingang lief, dann kein Block mehr -> neu oeffnen
logs = []


class Stream:
    active = True

    def __init__(self, **kw):
        self.kw = kw
        Stream.made += 1
        Stream.last = self

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
audio_send.QUIET_S = 0.8
audio_send.QUIET_MAX_S = 1.6
w.quiet = audio_send.QUIET_S
real_sleep = time.sleep
time.sleep = lambda s: real_sleep(0.05)
w.start()
real_sleep(0.3)
check(Stream.made == 1, "Eingang geoeffnet")
w._callback(block, 1024, None, None)             # Ton laeuft ...
real_sleep(0.6)                                  # ... und hoert auf
check(w.restarts == 1 and any("liefert seit 0 s" in m or "liefert seit 1 s" in m for m in logs),
      "Ton lief, dann kein Block mehr: Waechter meldet und schliesst: %s" % logs[-1:])
real_sleep(0.3)
check(Stream.made == 2, "danach neu geoeffnet (%d)" % Stream.made)

# Mac schlaeft (Fehlerbericht 22.11.2026: 5000 Mal neu geoeffnet, dann Absturz): ohne jeden Block nur selten


def wait_made(n, limit=5.0):
    end = time.monotonic() + limit
    while Stream.made < n and time.monotonic() < end:
        real_sleep(0.01)
    return time.monotonic()


wait_made(2)
t2 = w.opened                                    # wann der zweite Eingang geoeffnet wurde
real_sleep(max(0.0, t2 + 0.5 - time.monotonic()))
check(Stream.made == 2, "kein Block seit dem Oeffnen: nicht alle paar Sekunden neu (%d)" % Stream.made)
t3 = wait_made(3)
check(Stream.made == 3 and t3 - t2 >= 0.7 and w.quiet == 1.6,
      "erst nach der Wartezeit neu (%.2f s), Wartezeit verdoppelt (%.1f)" % (t3 - t2, w.quiet))
real_sleep(1.0)
check(Stream.made == 3, "naechster Versuch erst nach der laengeren Wartezeit (%d)" % Stream.made)
w._callback(block, 1024, None, None)             # aufgewacht: Ton kommt wieder
real_sleep(0.2)
check(w.quiet == audio_send.QUIET_S, "Ton wieder da: Wartezeit zurueckgesetzt")
w.stop()
time.sleep = real_sleep
socket.gethostbyname = orig
finish("test_ton_waechter")
