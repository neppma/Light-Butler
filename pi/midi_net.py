#!/usr/bin/env python3
"""
midi_net.py - APC mini mk2 am MacBook statt am Pi: MIDI ueber das Netzwerk (UDP, Port 9021).

Die Mixxx-Bruecke am Mac (apc_relay.py) liest den APC und schickt jede Taste und jeden Fader hierher; die
LED-Farben gehen auf demselben Weg zurueck an den Mac. Fuer midi_ctl.MidiController sieht das aus wie ein
gewoehnlicher MIDI-Ein- und Ausgang (iter_pending, send, close).

Pakete (JSON):
  Mac -> Pi  {"t": "hello", "sid": "<Sitzung>", "dev": true|false, "name": "<Port>"}   jede Sekunde
             {"t": "midi", "sid": "<Sitzung>", "d": [status, daten1, daten2]}         Taste, Fader
  Pi -> Mac  {"t": "midi", "d": [status, daten1, daten2]}                             LED
Nur Noten und Regler (3 Bytes) werden angenommen, keine SysEx. Wie das Panel nur fuer das Heimnetz gedacht.
"""
import json
import socket
import threading
import time

NET_PORT = 9021
STALE_S = 3.0                      # so lange ohne Lebenszeichen: Verbindung gilt als weg


def valid(d):
    """Nur Note an/aus und Regler mit drei Bytes im MIDI-Bereich."""
    return (isinstance(d, list) and len(d) == 3 and all(isinstance(x, int) for x in d)
            and 0x80 <= d[0] <= 0xBF and 0 <= d[1] <= 127 and 0 <= d[2] <= 127)


class NetMidi:
    """Empfaenger am Pi. start() bindet den UDP-Port und liest im Hintergrund."""

    def __init__(self, port=NET_PORT, sock=None, clock=time.monotonic):
        self.port, self.sock, self.clock = port, sock, clock
        self.addr = None                             # Absender der letzten Sitzung (Mac)
        self.sid, self.session = None, 0             # session zaehlt neue Sitzungen (App am Mac neu gestartet)
        self.dev, self.name, self.gen = False, "", None
        self.last = None
        self.pending = []
        self.error = ""
        self.lock = threading.Lock()
        self.inport, self.outport = NetIn(self), NetOut(self)

    def start(self):
        if self.sock is None:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.bind(("0.0.0.0", self.port))
            except OSError as e:
                self.error = f"UDP-Port {self.port}: {e}"[:120]
                self.sock = None
                return False
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def _loop(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(2048)
            except OSError:
                time.sleep(0.5)
                continue
            self.receive(data, addr)

    def receive(self, data, addr):
        try:
            m = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(m, dict):
            return
        sid = str(m.get("sid", ""))[:40]
        with self.lock:
            if sid and sid != self.sid:              # neue Sitzung: LEDs muessen komplett neu gesendet werden
                self.sid, self.session, self.pending, self.gen = sid, self.session + 1, [], None
            if sid != self.sid:
                return
            self.addr, self.last = addr, self.clock()
            if m.get("t") == "hello":
                gen = m.get("gen")
                if gen != self.gen and self.gen is not None:   # APC am Mac neu angesteckt: er ist dunkel, alle LEDs neu senden
                    self.session += 1
                self.gen = gen
                self.dev = bool(m.get("dev"))
                self.name = str(m.get("name", ""))[:60]
            elif m.get("t") == "midi" and valid(m.get("d")):
                self.pending.append(bytes(m["d"]))
                del self.pending[:-256]

    def connected(self):
        """True, solange der Mac sich meldet und der APC dort angeschlossen ist."""
        return self.last is not None and self.clock() - self.last < STALE_S and self.dev

    def take(self):
        with self.lock:
            out, self.pending = self.pending, []
        return out

    def send(self, data):
        if self.sock is None or self.addr is None or not valid(list(data)):
            return
        try:
            self.sock.sendto(json.dumps({"t": "midi", "d": list(data)}).encode(), self.addr)
        except OSError:
            pass


class NetIn:
    """Eingang wie bei mido: iter_pending() liefert die Meldungen vom Mac."""

    def __init__(self, net):
        self.net = net

    def iter_pending(self):
        import mido
        for raw in self.net.take():
            yield mido.Message.from_bytes(raw)

    def close(self):
        pass


class NetOut:
    """Ausgang wie bei mido: send(msg) schickt die LED-Meldung an den Mac."""

    def __init__(self, net):
        self.net = net

    def send(self, msg):
        self.net.send(msg.bytes())

    def close(self):
        pass
