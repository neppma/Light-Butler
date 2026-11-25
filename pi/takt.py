"""
takt.py - gleichmaessige Takt-Uhr fuer /api/takt (Rueckmeldung Bravia-Dashboard 23.11.2026).

Die erkannten Schlaege (Zaehlzeit der Show) schwanken um einige zehn Millisekunden. Die Uhr legt eine Gerade
beat = b0 + (t - t0) * bpm / 60 durch sie und zieht sie bei jedem Schlag nur ein Stueck (GAIN) nach: so laeuft sie ruhig
weiter und bleibt doch auf der Musik. Nicht die Zeitachse von Ableton Link: deren Schlaege liegen nicht auf der Musik.

Tempo stabil (aktiv) erst, wenn es SETTLE_S lang innerhalb TOL blieb: ein kurz doppelt oder halb erkanntes Tempo am
Liedanfang wird nicht gemeldet. Nur Anzeige, das Licht rechnet nie damit.
"""
GAIN = 0.15           # Anteil des Phasenfehlers, der je Schlag ausgeglichen wird
BPM_GAIN = 0.1        # so schnell folgt das Tempo der Uhr kleinen Aenderungen
TOL = 0.03            # mehr Abweichung im Tempo (3 %) = neues Tempo: Uhr neu, Wartezeit neu
JUMP = 0.5            # Schlag weiter als einen halben Schlag daneben: Uhr neu ansetzen (Tempo bleibt)
SETTLE_S = 3.0        # so lange muss das Tempo stabil sein
STALE_S = 4.0         # ohne Schlag so lange: nicht mehr aktiv


class TaktClock:
    def __init__(self):
        self.b0 = self.t0 = None
        self.bpm = 0.0
        self.since = None             # seit wann das Tempo stabil ist
        self.last = None              # letzter Schlag (Zeit)

    def beat(self, n, t, bpm):
        """Schlag Nummer n zur Zeit t, erkanntes Tempo bpm."""
        if not bpm or bpm <= 0:
            return
        self.last = t
        if self.b0 is None or abs(bpm - self.bpm) > TOL * self.bpm:
            self.b0, self.t0, self.bpm, self.since = float(n), t, float(bpm), t
            return
        pred = self.at(t)
        err = n - pred
        if abs(err) > JUMP:
            self.b0, self.t0 = float(n), t
            return
        self.bpm += BPM_GAIN * (bpm - self.bpm)
        self.b0, self.t0 = pred + GAIN * err, t

    def at(self, t):
        """Schlag (mit Nachkommastellen) zur Zeit t, None ohne Uhr."""
        if self.b0 is None:
            return None
        return self.b0 + (t - self.t0) * self.bpm / 60.0

    def stable(self, t):
        return (self.since is not None and self.last is not None and t - self.since >= SETTLE_S
                and t - self.last < STALE_S)


def to_bar(b, q):
    """Auf den naechsten Taktanfang (Vielfaches von q) runden."""
    q = max(1, int(q))
    return float(q * int(b / q + 0.5)) if b >= 0 else float(-q * int(-b / q + 0.5))
