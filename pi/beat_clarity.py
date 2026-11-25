"""
beat_clarity.py - wie deutlich ein regelmaessiger Schlag im Ton steckt (Wunsch von Markus 23.11.2026).

aubio meldet immer ein Tempo, auch in einer Einleitung ohne Beat (Publikum klatscht, eine Trompete spielt leise): dann
eines um 120-130, das es bevorzugt. Diese Messung sagt, ob es ueberhaupt einen Schlag gibt:

1. Anschlaege je Block: Anteil der Frequenzen, die gegenueber dem Block davor deutlich lauter werden (RISE im Logarithmus).
   Ein Schlag (Kick, Snare, Hi-Hat) hebt viele Frequenzen auf einmal, ein gehaltener Ton oder Gesang kaum welche.
2. Alle EVERY_S ueber die letzten SPAN_S: Autokorrelation dieser Anschlaege, hoechster Wert bei 60 bis 200 BPM, der auch
   beim doppelten Abstand gilt. Regelmaessiger Schlag: um 0,6. Applaus, Orchester, Gesang, Gitarre: fast immer unter 0,15.

Gemessen am Mac (23.11.2026) an Partymusik, Also sprach Zarathustra, Gesangsspuren, Gitarre, kuenstlichem Applaus:
mit der Regel "0,35 zwei Sekunden lang" nie ein Beat ohne Beat, mit Beat nach 5 bis 6 s. Nur numpy.

Feines Tempo (bpm, Eichstueck 23.11.2026): aubio rastet auf seine Blockgroesse ein und meldet am Pi 121,7 statt 120 und
96 statt 95. Hier ueber TEMPO_S: die Spitze der Autokorrelation beim Vielfachen des Schlagabstands (2, 3, 4, 6 oder 8
Schlaege), zwischen den Bloecken genau gerechnet (Parabel), geteilt durch das Vielfache. Eichstueck: 119,99 und 95,03.
Ob die Zahl gilt, entscheidet die Show (nahe an aubio, sonst nicht).
"""
import numpy as np

SPAN_S = 4.0       # Messfenster
TEMPO_S = 8.0      # Fenster fuer das feine Tempo
TEMPO_KEEP = 5     # Median der letzten so vielen feinen Werte
EVERY_S = 0.5      # so oft wird gerechnet
RISE = 0.5         # so viel lauter (log) zaehlt eine Frequenz als Anschlag
BINS = 300         # bis etwa 13 kHz (Fenster 1024 bei 44,1 kHz)
SCALE = 1000.0     # vor dem Logarithmus


class BeatClarity:
    def __init__(self, dt):
        self.dt = dt
        self.n = max(16, int(round(SPAN_S / dt)))
        self.nt = max(self.n, int(round(TEMPO_S / dt)))
        self.buf = np.zeros(self.nt, np.float32)
        self.i = 0                                   # Bloecke seit Beginn
        self.every = max(1, int(round(EVERY_S / dt)))
        self.lo, self.hi = max(1, int(0.3 / dt)), max(2, int(1.0 / dt))   # 200 bis 60 BPM
        self.prev = None
        self.value = 0.0
        self.bpm = 0.0                               # feines Tempo, 0 = noch keins
        self.bpms = []

    def feed(self, mag, audible=True):
        """mag: Betrag des Spektrums (rfft) eines Blocks."""
        s = np.log1p(SCALE * np.asarray(mag[:BINS], np.float32))
        x = float(((s - self.prev) > RISE).mean()) if (self.prev is not None and audible) else 0.0
        self.prev = s
        self.buf[self.i % self.nt] = x
        self.i += 1
        if self.i % self.every == 0:
            self.value = self._measure() if self.i >= self.n else 0.0
            if self.i >= self.nt:
                b = self._tempo()
                self.bpms = (self.bpms + [b])[-TEMPO_KEEP:] if b > 0 else []
                self.bpm = float(np.median(self.bpms)) if len(self.bpms) >= 3 else 0.0
        return self.value

    def _series(self, n):
        """Die letzten n Anschlagswerte, aufbereitet: nur Spitzen ueber der Umgebung, ohne Mittelwert."""
        k = self.i % self.nt
        o = np.concatenate((self.buf[k:], self.buf[:k]))[-n:].astype(np.float64)
        o = np.maximum(o - np.convolve(o, np.ones(15) / 15.0, "same"), 0.0)
        return o - o.mean()

    @staticmethod
    def _ac(o):
        n = len(o)
        f = np.fft.rfft(o, 2 * n)
        ac = np.fft.irfft(f * np.conj(f))[:n]
        if ac[0] <= 1e-9:
            return None
        return ac / ac[0] * n / (n - np.arange(n))     # weniger Ueberlappung bei grossem Abstand ausgleichen

    @staticmethod
    def _peak(ac, c, w):
        """Spitze nahe c (+-w), zwischen den Bloecken genau (Parabel durch drei Punkte)."""
        a, b = max(1, c - w), min(len(ac) - 2, c + w)
        if a > b:
            return float(c)
        k = a + int(np.argmax(ac[a:b + 1]))
        y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]
        den = y0 - 2.0 * y1 + y2
        return k + (0.5 * (y0 - y2) / den if den < 0 else 0.0)

    def _tempo(self):
        ac = self._ac(self._series(self.nt))
        if ac is None:
            return 0.0
        lag = self.lo + int(np.argmax(ac[self.lo:self.hi]))
        if min(ac[lag], ac[2 * lag]) < 0.25:           # kein deutlicher Schlag (auch beim doppelten Abstand): keins
            return 0.0
        per = self._peak(ac, lag, 2)
        for m in (2, 3, 4, 6, 8):
            if m * lag < self.nt * 0.55:
                per = self._peak(ac, int(round(m * lag)), 3) / m
        return 60.0 / (per * self.dt) if per > 0 else 0.0

    def _measure(self):
        ac = self._ac(self._series(self.n))
        if ac is None:
            return 0.0
        n = self.n
        lag = self.lo + int(np.argmax(ac[self.lo:self.hi]))
        c = float(ac[lag])
        if 2 * lag < n - 10:
            c = min(c, float(ac[2 * lag]))
        return max(0.0, min(1.0, c))
