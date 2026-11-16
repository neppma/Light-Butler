#!/usr/bin/env python3
"""
clock.py - Synchronisation: die Uhr der Show folgt der tatsaechlichen Audio-Position.

Der Browser spielt die Musik und meldet regelmaessig, wo er ist (Master-Zeitbasis). Die Uhr laeuft zwischen den Meldungen
selbst weiter und wird sanft nachgezogen: kleine Abweichungen ueber die Laufgeschwindigkeit (hoechstens +-4 %, damit
Bewegungen nicht springen), grosse (Sprung, Puffern) mit einem Sprung. Der Regler zieht den Fehler immer gegen 0, deshalb
gibt es keine langfristige Drift. Ausreisser durch das Netz filtert der Median der letzten Meldungen.

Kommt nichts mehr (WLAN weg, Browser zu), laeuft die Uhr mit Tempo 1 frei weiter: Das Licht bleibt beim Lied.
"""
from collections import deque

JUMP_S = 0.30          # ab dieser Abweichung wird gesprungen (nach zwei Meldungen in Folge)
GAIN = 0.8             # Laufgeschwindigkeit je Sekunde Abweichung
MAX_SLEW = 0.04        # hoechstens 4 % schneller oder langsamer
LOST_S = 2.0           # so lange ohne Meldung = frei laufen


class MasterClock:
    def __init__(self, jump=JUMP_S, gain=GAIN, max_slew=MAX_SLEW, lost_after=LOST_S):
        self.jump, self.gain, self.max_slew, self.lost_after = jump, gain, max_slew, lost_after
        self.playing = False
        self.pos0, self.t0, self.rate = 0.0, 0.0, 1.0
        self.last_report = None
        self.errs = deque(maxlen=5)
        self.err = 0.0                 # zuletzt gemessene Abweichung in Sekunden (fuer die Anzeige)
        self.jumps = 0

    def position(self, now):
        if not self.playing:
            return self.pos0
        return self.pos0 + max(0.0, now - self.t0) * self.rate

    def _anchor(self, pos, now):
        self.pos0, self.t0 = max(0.0, pos), now

    def start(self, pos, now):
        self._anchor(self.pos0 if pos is None else pos, now)
        self.playing, self.rate = True, 1.0
        self.errs.clear()
        self.last_report = None

    def pause(self, now, pos=None):
        p = self.position(now) if pos is None else pos
        self._anchor(p, now)
        self.playing, self.rate = False, 1.0

    def seek(self, pos, now):
        self._anchor(pos, now)
        self.rate = 1.0
        self.errs.clear()

    def report(self, pos, now, base=1.0):
        """Der Browser oder Mixxx meldet: Die Musik ist gerade bei pos (schon um die Netzlaufzeit korrigiert).
        base = Grundtempo der Quelle (Pitch und Sync in Mixxx), der Regler arbeitet darum herum."""
        self.last_report = now
        if not self.playing:
            return
        cur = self.position(now)
        err = pos - cur
        self.errs.append(err)
        s = sorted(self.errs)
        med = s[(len(s) - 1) // 2]
        self.err = med
        recent = list(self.errs)[-2:]
        if len(recent) == 2 and min(abs(x) for x in recent) > self.jump and recent[0] * recent[1] > 0:
            # zwei Meldungen in Folge weit daneben: echter Sprung (Puffern, Seek vom Browser), kein einzelner Ausreisser
            self._anchor(pos, now)
            self.rate = base
            self.errs.clear()
            self.jumps += 1
            return
        self._anchor(cur, now)
        self.rate = base + max(-self.max_slew, min(self.max_slew, self.gain * med))

    def source(self, now):
        """browser = folgt der Audio-Position, frei = eigene Uhr."""
        if self.last_report is None or now - self.last_report > self.lost_after:
            return "frei"
        return "browser"

    def tick(self, now):
        """Ohne Meldungen zurueck auf Tempo 1, sonst liefe die Uhr mit dem letzten Korrekturwert davon."""
        if self.playing and self.rate != 1.0 and self.source(now) == "frei":
            self._anchor(self.position(now), now)
            self.rate = 1.0
