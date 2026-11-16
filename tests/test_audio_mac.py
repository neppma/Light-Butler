"""Audio-Eingang "Mac (Netzwerk)": die Mac-App (audio_send.py) schickt den Systemton (BlackHole) per UDP 9022 an den Pi
(audio_net.py), der Pi analysiert ihn wie das Line-In. Echte UDP-Pakete ueber localhost, kuenstliche Musik (128 BPM)."""
import os
import socket
import sys
import time

import numpy as np

from _common import ROOT, audio, check, finish

import audio_net
from audio_net import NET_NAME, NetAudioIn, parse

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from audio_send import AudioSender, packets, resample, RATE, FRAMES   # noqa: E402

SR = 48000                                                     # BlackHole laeuft meist mit 48 kHz


def music(n0, n, sr=SR):
    t = (np.arange(n0, n0 + n)) / sr
    beat = 60 / 128.0
    ph = t % beat
    x = 0.8 * np.sin(2 * np.pi * (50 + 90 * np.exp(-ph * 40)) * ph) * np.exp(-ph * 12) + 0.25 * np.sin(2 * np.pi * 55 * t)
    return np.stack([x, x], axis=1).astype(np.float32)


# ---- Pakete und Umrechnung -----------------------------------------------------------------------------------------
y = resample(music(0, 48000), 48000, 44100)
check(len(y) == 44100 and y.shape[1] == 2, "48 kHz -> 44,1 kHz, Stereo bleibt")
pk, seq = packets(y[:FRAMES * 3], 7)
check(len(pk) == 3 and seq == 10 and all(len(p) <= 1100 for p in pk), "256 Bilder je Paket, klein genug fuer UDP")
s0, x0 = parse(pk[0], 44100)
check(s0 == 7 and x0.shape == (FRAMES, 2) and abs(float(x0[10, 0]) - float(y[10, 0])) < 1e-3, "Paket zurueckgelesen = Original")
check(parse(pk[0], 48000) is None and parse(b"S2LX" + pk[0][4:], 44100) is None and parse(b"kurz", 44100) is None,
      "falsche Rate, Kennung oder Laenge verworfen")

blocks = []
n = NetAudioIn(blocks.append, 44100, 512, sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
pk, _ = packets(y[:FRAMES * 10], 100)
for p in pk[:4] + pk[5:]:                                       # Paket 104 fehlt
    n.receive(p, ("192.168.1.50", 5000))
n.receive(pk[2], ("192.168.1.50", 5000))                        # doppelt/zu spaet
check(all(b.shape == (512, 2) for b in blocks) and len(blocks) == (9 * FRAMES) // 512, "Bloecke wie von der Soundkarte (512 Samples)")
check(n.lost == 1 and n.status()["src"] == "192.168.1.50" and n.status()["alive"], "verlorene Pakete gezaehlt, Absender bekannt")

# Senderwechsel (Fehlerbericht 01.11.2026): erst die Mixxx-App mit hohen Laufnummern, dann der frisch gestartete Helfer
# mit Nummer 0 vom selben Mac, aber anderem Port. Vorher wurden alle Pakete des Helfers als "zu spaet" verworfen.
old, _ = packets(y[:FRAMES * 4], 200000)
for p in old:
    n.receive(p, ("192.168.1.66", 50001))
before = n.packets
new, _ = packets(y[:FRAMES * 4], 0)
for p in new:
    n.receive(p, ("192.168.1.66", 50002))
check(n.packets == before + 4, "neuer Sender (anderer Port, Nummer ab 0): Pakete werden angenommen")
n.t -= 1.0                                                      # Pause, dann derselbe Absender mit neuer Zaehlung
again, _ = packets(y[:FRAMES * 2], 0)
before = n.packets
for p in again:
    n.receive(p, ("192.168.1.66", 50002))
check(n.packets == before + 2, "nach einer Pause beginnt die Zaehlung neu")

# ---- Ende zu Ende: Mac-Sender -> UDP -> Analyse am Pi --------------------------------------------------------------
an = audio.Analyzer(NET_NAME, 44100, 512)
an.net_port = 0
an.start()
port = an._net.sock.getsockname()[1]
check(an.dev_name == NET_NAME and an.audio_info()["running"] if hasattr(an, "audio_info") else True, "Eingang Mac (Netzwerk) laeuft")
snd = AudioSender("127.0.0.1", port, sd_mod=object(), log=lambda m: None)
snd.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
pos = 0
for _ in range(80):                                             # 8 s Musik in 0,1-s-Stuecken (wie der Audio-Callback)
    snd.feed(music(pos, 4800), SR)
    pos += 4800
    time.sleep(0.012)
time.sleep(0.5)
f = an.poll()
check(an._net.status()["packets"] > 1000 and an._net.status()["lost"] == 0, f"{an._net.status()['packets']} Pakete ohne Verlust")
check(an.kick_count >= 8, f"Analyse erkennt die Kicks ({an.kick_count})")
check(f.level > 0.05 and not f.silent, "Pegel da, keine Stille")
time.sleep(1.2)
check(an.poll().silent, "kommt nichts mehr: Stille")
an.stop()
check(an._net is None, "Umschalten/Beenden schliesst den UDP-Eingang")
finish("test_audio_mac")
