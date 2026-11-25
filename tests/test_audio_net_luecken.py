"""Netzwerk-Ton (audio_net.NetAudioIn): verlorene Pakete werden aufgefuellt (Eichstueck 23.11.2026: rund 1 % ging verloren,
ohne Ersatz lief die Musik am Licht-Rechner zu schnell, das Tempo war 1,5 % zu hoch)."""

import numpy as np

from _common import check, finish
import audio_net  # noqa: E402

RATE, N = 44100, 256


def pkt(seq, val, ch=2):
    x = np.full((N, ch), val, np.int16)
    return audio_net.HEAD.pack(audio_net.MAGIC, seq, RATE, ch, 1) + x.tobytes()


got = []
na = audio_net.NetAudioIn(lambda b: got.append(b), rate=RATE, hop=512, sock=object())
A = ("10.0.0.2", 5000)
for s in range(0, 10):
    na.receive(pkt(s, 1000), A)
before = sum(len(b) for b in got) + len(na.buf)
check(before == 10 * N and na.lost == 0, "ohne Verlust: genau so viele Proben wie gesendet")

for s in (10, 11, 14, 15):                       # 12 und 13 fehlen
    na.receive(pkt(s, 1000), A)
total = sum(len(b) for b in got) + len(na.buf)
check(na.lost == 2 and total == 16 * N and na.filled == 2 * N, "2 Pakete verloren: aufgefuellt, Zeit stimmt (%d Proben)" % total)
allx = np.concatenate(got + [na.buf])
check(float(allx[12 * N:14 * N].min()) > 0.9 * 1000 / 32768, "kurze Luecke: fast voller Pegel, kein Sprung")

na.receive(pkt(15 + 200, 1000), A)               # sehr grosse Luecke: nicht auffuellen
total2 = sum(len(b) for b in got) + len(na.buf)
check(total2 == total + N and na.filled == 2 * N, "grosse Luecke (199 Pakete): nicht aufgefuellt")

na.receive(pkt(300, 1000, ch=1), A)              # anderer Kanalzahl: nichts aus dem alten Paket einsetzen
check(na.filled == 2 * N, "andere Kanalzahl: kein Ersatz")
check("filled" in na.status(), "Stand meldet aufgefuellte Proben")

# lange Luecke wird leiser, aber nie ganz still
c = na.concealment(40, N)
check(abs(float(c[0, 0]) - float(na.last_x[0, 0])) < 1e-6 and float(np.abs(c[-1]).max()) >= 0.29 * float(np.abs(na.last_x).max()),
      "Ersatz: beginnt voll, endet bei 30 %")
finish("test_audio_net_luecken")
