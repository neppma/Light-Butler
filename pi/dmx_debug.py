#!/usr/bin/env python3
"""
dmx_debug.py - DMX-Debugger (Seite /dmx-debug): jeden Kanal der DMX-Kette direkt setzen, um Geraete zu erforschen.

AUSNAHME von den Sicherheitsregeln 2, 3 und 5, vom Nutzer am 03.11.2026 ausdruecklich so verlangt: Hier greifen weder Laser- noch
Hazer-Sperre noch safe_limits, das Bild geht roh auf den Bus. Sicherungen, die bleiben:
  * Nach jedem Start aus, jedes Einschalten beginnt mit allen Kanaelen auf 0.
  * Totmann: meldet sich die Seite 2 s nicht (Tab zu, WLAN weg), ist er aus und die Show uebernimmt wieder.
  * BLACKOUT und das Dienstende schalten ihn sofort aus (Show.update, Output.stop).
  * WLED und Nanoleaf bleiben davon unberuehrt: nur die DMX-Kette.
"""
import threading
import time

TIMEOUT_S = 2.0


class DmxDebug:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.data = bytearray(512)
        self.armed = False
        self.hold = False                    # Taster "Kurz dunkel": alles 0, die Werte bleiben gemerkt
        self.last_beat = 0.0

    def arm(self, on):
        with self.lock:
            self.data = bytearray(512)       # immer von 0: nichts bleibt von frueher an
            self.armed = bool(on)
            self.hold = False
            self.last_beat = self.clock()

    def beat(self):
        with self.lock:
            if self.armed:
                self.last_beat = self.clock()

    def set_hold(self, on):
        with self.lock:
            self.hold = bool(on) and self.armed
            if self.armed:
                self.last_beat = self.clock()

    def set_values(self, values):
        """values: {Kanal 1..512: Wert 0..255}. Wirkt nur eingeschaltet."""
        with self.lock:
            if not self.armed:
                return False
            for ch, v in values.items():
                ch, v = int(ch), int(v)
                if not 1 <= ch <= 512:
                    raise ValueError(f"Kanal {ch} gibt es nicht")
                self.data[ch - 1] = max(0, min(255, v))
            self.last_beat = self.clock()
            return True

    def frame(self):
        """Das Bild fuer die DMX-Kette oder None (dann gilt die Show). Prueft den Totmann."""
        with self.lock:
            if not self.armed:
                return None
            if self.clock() - self.last_beat > TIMEOUT_S:
                self.armed = False
                self.data = bytearray(512)
                self.hold = False
                return None
            return bytes(512) if self.hold else bytes(self.data)

    def is_armed(self):
        return self.frame() is not None

    def values(self):
        with self.lock:
            return list(self.data)
