#!/usr/bin/env python3
"""
artnet_in.py - Art-Net-Eingang am Light-Butler (Ersatz fuer den OLA-Pi als Ziel fuer ein anderes Lichtprogramm).

Lauscht auf UDP 6454 und nimmt ArtDmx-Pakete fuer das Universe der DMX-Kette an. Ist der Eingang eingeschaltet
(Einstellung artnet_in) und kommen Daten, gehen sie statt der Show auf die DMX-Kette (USB-Adapter oder OLA-Pi),
aber IMMER durch den Sicherheitsfilter (dmx.Rig.filter_external): Laser und Hazer 0, safe_limits, ohne
Strobe-Erlaubnis keine Strobe-Kanaele. Kommt 3 s nichts mehr, uebernimmt wieder die Show.

Auf ArtPoll antwortet er mit ArtPollReply, damit Apps ihn im Netz finden ("Light-Butler").
"""
import socket
import struct
import threading
import time

ARTNET_PORT = 6454
HEADER = b"Art-Net\x00"
OP_POLL, OP_POLL_REPLY, OP_DMX = 0x2000, 0x2100, 0x5000
STALE_S = 3.0


def parse_dmx(pkt):
    """(universe, daten) aus einem ArtDmx-Paket, sonst None."""
    if len(pkt) < 18 or pkt[:8] != HEADER or struct.unpack("<H", pkt[8:10])[0] != OP_DMX:
        return None
    uni = struct.unpack("<H", pkt[14:16])[0] & 0x7FFF
    n = struct.unpack(">H", pkt[16:18])[0]
    if n < 1 or n > 512 or len(pkt) < 18 + n:
        return None
    return uni, bytes(pkt[18:18 + n])


def poll_reply(ip, universe, name="Light-Butler"):
    """ArtPollReply (239 Bytes): ein DMX-Ausgang fuer das Universe der DMX-Kette."""
    try:
        ipb = socket.inet_aton(ip)
    except OSError:
        ipb = bytes(4)
    p = bytearray(239)
    p[0:8] = HEADER
    p[8:10] = struct.pack("<H", OP_POLL_REPLY)
    p[10:14] = ipb
    p[14:16] = struct.pack("<H", ARTNET_PORT)
    p[16:18] = struct.pack(">H", 1)                  # Firmware-Version
    p[18] = (universe >> 8) & 0x7F                   # Net
    p[19] = (universe >> 4) & 0x0F                   # Sub-Net
    p[23] = 0xD0                                     # Status: Ports per Netzwerk eingestellt
    p[26:26 + 18] = name.encode()[:17].ljust(18, b"\x00")
    p[44:44 + 64] = (name + " (DMX ueber USB)").encode()[:63].ljust(64, b"\x00")
    p[108:108 + 64] = b"#0001 [0000] OK".ljust(64, b"\x00")
    p[172:174] = struct.pack(">H", 1)                # ein Port
    p[174] = 0x80                                    # Port 1: DMX-Ausgang
    p[182] = 0x80                                    # Port 1: Daten werden ausgegeben
    p[190] = universe & 0x0F                         # SwOut Port 1
    return bytes(p)


class ArtNetIn:
    def __init__(self, universe=0, port=ARTNET_PORT, sock=None, clock=time.monotonic, my_ip=None):
        self.universe, self.port, self.sock, self.clock = universe, port, sock, clock
        self.my_ip = my_ip
        self.data, self.t, self.src = None, None, ""
        self.frames, self.error = 0, ""
        self.lock = threading.Lock()

    def start(self):
        if self.sock is None:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self.sock.bind(("0.0.0.0", self.port))
            except OSError as e:
                self.error = f"UDP {self.port}: {e}"[:120]
                self.sock = None
                return False
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def _loop(self):
        while True:
            try:
                pkt, addr = self.sock.recvfrom(1024)
            except OSError:
                time.sleep(0.5)
                continue
            self.receive(pkt, addr)

    def _ip(self, peer):
        if self.my_ip:
            return self.my_ip
        try:                                         # eigene Adresse in Richtung des Absenders
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((peer, 9))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "0.0.0.0"

    def receive(self, pkt, addr):
        if len(pkt) >= 10 and pkt[:8] == HEADER and struct.unpack("<H", pkt[8:10])[0] == OP_POLL:
            reply = poll_reply(self._ip(addr[0]), self.universe)
            for dest in {(addr[0], ARTNET_PORT), (addr[0], addr[1])}:   # laut Norm an 6454, manche Apps fragen von einem anderen Port
                try:
                    self.sock.sendto(reply, dest)
                except OSError:
                    pass
            return
        r = parse_dmx(pkt)
        if r is None or r[0] != self.universe:
            return
        with self.lock:
            self.data, self.t, self.src = r[1], self.clock(), addr[0]
            self.frames += 1

    def active(self):
        return self.t is not None and self.clock() - self.t < STALE_S

    def frame(self):
        """Zuletzt empfangenes DMX-Bild (512 Bytes, fehlende Kanaele 0) oder None, wenn nichts Aktuelles kommt."""
        with self.lock:
            if not self.active() or self.data is None:
                return None
            return self.data + bytes(512 - len(self.data))

    def status(self):
        return {"active": self.active(), "src": self.src, "frames": self.frames, "error": self.error}
