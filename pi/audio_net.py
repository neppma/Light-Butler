#!/usr/bin/env python3
"""
audio_net.py - Audio-Eingang "Mac (Netzwerk)": Ton vom MacBook per UDP (Port 9022) statt vom Line-In.

Die Mac-App (mac/mixxx_bridge/audio_send.py) liest eine Kopie des Systemtons (BlackHole) und schickt sie als
Pakete hierher. Fuer audio.Analyzer sieht das aus wie eine Soundkarte: Bloecke mit hop Samples, float32, 1 oder 2 Kanaele.

Paket:  b"S2LA" | Folge-Nr. uint32 | Abtastrate uint32 | Kanaele uint8 | Format uint8 (1 = int16) | 2 Byte frei | Samples
        (int16, little endian, Kanaele verschraenkt). Alles klein (256 Bilder je Paket), damit nichts fragmentiert.
Kommt nichts mehr, liefert der Eingang keine Bloecke: die Show sieht das wie Stille.
"""
import socket
import struct
import threading
import time

import numpy as np

NET_NAME = "Musik-Rechner (Netzwerk)"
OLD_NET_NAMES = ("Mac (Netzwerk)",)               # alter Name (bis 15.11.2026) in audio.json oder show.conf


def net_alias(name):
    """Alten Namen des Netzwerk-Eingangs auf den neuen abbilden."""
    return NET_NAME if name in OLD_NET_NAMES else name
NET_PORT = 9022
MAGIC = b"S2LA"
HEAD = struct.Struct("<4sIIBB2x")


def parse(pkt, rate):
    """(Folge-Nr., Samples als float32-Array [n, Kanaele]) oder None, wenn das Paket nicht passt."""
    if len(pkt) < HEAD.size:
        return None
    magic, seq, r, ch, fmt = HEAD.unpack_from(pkt)
    if magic != MAGIC or fmt != 1 or ch not in (1, 2) or r != rate:
        return None
    body = pkt[HEAD.size:]
    n = len(body) // (2 * ch)
    if n == 0:
        return None
    x = np.frombuffer(body[:n * 2 * ch], dtype="<i2").astype(np.float32) / 32768.0
    return seq, x.reshape(n, ch)


class NetAudioIn:
    def __init__(self, deliver, rate=44100, hop=512, port=NET_PORT, sock=None):
        self.deliver, self.rate, self.hop, self.port = deliver, rate, hop, port
        self.sock = sock
        self.buf = None
        self.last_seq, self.last_addr = None, None
        self.src, self.t, self.packets, self.lost, self.error = "", None, 0, 0, ""
        self.channels = 2
        self._run = False
        self._thread = None

    def start(self):
        if self.sock is None:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
                self.sock.bind(("0.0.0.0", self.port))
            except OSError as e:
                self.error = f"UDP {self.port}: {e}"[:120]
                self.sock = None
                raise ValueError(self.error) from None
        self.sock.settimeout(0.5)
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._run = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self.buf = None

    def _loop(self):
        while self._run:
            try:
                pkt, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                time.sleep(0.2)
                continue
            self.receive(pkt, addr)

    def receive(self, pkt, addr):
        r = parse(pkt, self.rate)
        if r is None:
            return
        seq, x = r
        now = time.time()
        # Neuer Sender (anderer Absender, zum Beispiel Helfer statt Mixxx-App) oder eine Pause: Laufnummer neu
        # beginnen. Sonst wuerden die kleinen Nummern eines frisch gestarteten Senders alle als "zu spaet" verworfen.
        fresh = (self.last_seq is None or addr != self.last_addr or self.t is None or now - self.t > 0.5)
        if not fresh:
            gap = (seq - self.last_seq) & 0xFFFFFFFF
            if gap == 0 or gap > 0x7FFFFFFF:                  # doppelt oder zu spaet: verwerfen
                return
            self.lost += gap - 1
        self.last_seq, self.last_addr = seq, addr
        self.src, self.t, self.packets = addr[0], now, self.packets + 1
        if self.buf is None or self.buf.shape[1] != x.shape[1]:
            self.buf = x[:0]
            self.channels = x.shape[1]
        self.buf = np.concatenate([self.buf, x])
        while len(self.buf) >= self.hop:                       # in Bloecke wie von der Soundkarte zerlegen
            self.deliver(self.buf[:self.hop].copy())
            self.buf = self.buf[self.hop:]
        if len(self.buf) > self.hop * 8:                       # Rueckstau (sollte nie passieren)
            self.buf = self.buf[-self.hop:]

    def status(self):
        alive = self.t is not None and time.time() - self.t < 2.0
        return {"alive": alive, "src": self.src, "packets": self.packets, "lost": self.lost, "error": self.error}
