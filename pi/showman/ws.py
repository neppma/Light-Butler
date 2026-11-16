#!/usr/bin/env python3
"""
ws.py - kleiner WebSocket-Server (RFC 6455) fuer den vorhandenen http.server, ohne neue Abhaengigkeit.
Nur Textnachrichten, wie sie der Showmanager braucht. Jede Verbindung laeuft in ihrem eigenen Thread des Panels und
kann die Show nie aufhalten.
"""
import base64
import hashlib
import select
import struct

MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_FRAME = 1 << 20


def accept_key(key):
    return base64.b64encode(hashlib.sha1((key.strip() + MAGIC).encode()).digest()).decode()


def encode(text, opcode=1):
    """Rahmen vom Server: unmaskiert."""
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    n = len(data)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + data


def unmask(data, mask):
    return bytes(b ^ mask[i % 4] for i, b in enumerate(data))


class Conn:
    """Eine offene Verbindung. Nach dem Handschlag wird direkt auf dem Socket gearbeitet."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = bytearray()
        self.closed = False
        sock.settimeout(5.0)                     # ein haengender Browser blockiert hoechstens seinen eigenen Thread

    def send(self, text, opcode=1):
        self.sock.sendall(encode(text, opcode))

    def wait(self, timeout):
        """True, wenn etwas zu lesen ist."""
        if self.buf:
            return True
        r, _, _ = select.select([self.sock], [], [], timeout)
        return bool(r)

    def _read_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("Verbindung zu")
            self.buf += chunk
        data = bytes(self.buf[:n])
        del self.buf[:n]
        return data

    def recv(self):
        """Naechste Textnachricht oder None (bei Ping/Pong). Wirft ConnectionError, wenn die Verbindung endet."""
        b1, b2 = self._read_exact(2)
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._read_exact(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._read_exact(8))[0]
        if n > MAX_FRAME:
            raise ConnectionError("Nachricht zu gross")
        mask = self._read_exact(4) if masked else None
        data = self._read_exact(n) if n else b""
        if mask:
            data = unmask(data, mask)
        if opcode == 8:
            self.closed = True
            raise ConnectionError("Close")
        if opcode == 9:
            self.send(data, 10)
            return None
        if opcode in (0, 1):
            return data.decode("utf-8", "replace")
        return None
