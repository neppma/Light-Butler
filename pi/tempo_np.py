#!/usr/bin/env python3
"""
tempo_np.py - Ersatz fuer aubio.tempo, nur mit numpy (Windows: fuer aubio gibt es dort kein fertiges Paket, 14.11.2026).

Gleiche Schnittstelle wie aubio.tempo: tempo(mono_block) -> [1.0 bei einem Schlag, sonst 0.0], get_bpm(), set_silence(db).
Am Pi bleibt aubio im Einsatz (audio.Analyzer nimmt diesen Ersatz nur, wenn "import aubio" scheitert).

Ablauf je Block (hop Samples):
1. Anschlag-Kurve: Zuwachs im log. Spektrum des Blocks (Spectral Flux bis rund 6 kHz), ohne gleitendes Mittel.
2. Etwa jede Sekunde das Tempo aus der Autokorrelation der letzten 8 s, je Tempo die Summe ueber die Vielfachen des
   Abstands, mit einer Vorliebe um 120 BPM (wie key_estimate.numpy_bpm am Mac). Ein neuer Wert ersetzt den alten nur,
   wenn er deutlich besser ist oder nahe dran liegt (keine Spruenge zwischen Halb und Doppelt).
3. Lage der Schlaege (Phase): die Verschiebung, bei der die Anschlaege der letzten Takte am staerksten auf das Raster
   fallen. Ein Schlag wird gemeldet, wenn die Zeit den naechsten Rasterpunkt erreicht.
Bei Stille (unter set_silence) keine Schlaege.
"""
import math

import numpy as np

BPM_MIN, BPM_MAX = 70.0, 180.0
BPM_PRIOR = 120.0
HIST_S = 8.0                 # Anschlag-Kurve fuer Tempo und Phase
EVERY_S = 1.0                # so oft das Tempo neu schaetzen
MIN_S = 4.0                  # erst ab so viel Musik ein Tempo
MIN_CONF = 0.3               # darunter kein Takt
LOW_HZ = 250.0               # Bassdrum-Bereich: Anschlaege dort zaehlen staerker (sonst rastet es auf die Hi-Hat ein)
LOW_W = 2.0
PHASE_K = 0.5               # je Sekunde die Haelfte der Abweichung des Rasters ausgleichen
KICK_HZ = 150.0             # Lage der Schlaege (Phase) nur aus diesem Bereich: die Bassdrum, nicht Snare oder Off-Beat


class NumpyTempo:
    on_time = True               # meldet den Schlag puenktlich (aubio etwas spaeter): audio.Analyzer misst die Betonung danach

    def __init__(self, win=1024, hop=512, rate=44100):
        self.hop, self.rate = int(hop), int(rate)
        self.fps = self.rate / self.hop
        self.n = int(HIST_S * self.fps)
        self.env = np.zeros(self.n, np.float32)
        self.filled = 0
        self.prev = None
        self.window = np.hanning(self.hop).astype(np.float32)
        top = max(2, int(6000.0 * self.hop / self.rate))
        self.band = slice(0, top)
        self.nlow = max(1, int(math.ceil(LOW_HZ * self.hop / self.rate)) + 1)
        self.nkick = max(1, int(math.ceil(KICK_HZ * self.hop / self.rate)))
        self.env_kick = np.zeros(self.n, np.float32)    # Anschlaege nur der Bassdrum, fuer die Phase
        self.silence_db = -90.0
        self.bpm = 0.0
        self.conf = 0.0
        self.k = 0                       # Bloecke seit Beginn
        self.next_beat = None            # Blocknummer (float) des naechsten Schlags
        self.quiet = 0
        lags = np.arange(int(self.fps * 60.0 / BPM_MAX), int(self.fps * 60.0 / BPM_MIN) + 2)
        self.lags = lags[lags > 0]

    # ---- aubio-Schnittstelle --------------------------------------------------------------------------------
    def set_silence(self, db):
        self.silence_db = float(db)

    def get_bpm(self):
        return float(self.bpm)

    def __call__(self, mono):
        x = np.asarray(mono, dtype=np.float32)
        self.k += 1
        rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
        loud = 20.0 * math.log10(max(rms, 1e-9)) > self.silence_db
        m = np.log1p(30.0 * np.abs(np.fft.rfft(x[:self.hop] * self.window[:len(x[:self.hop])]))[self.band])
        if self.prev is None or len(self.prev) != len(m):
            flux = kick = 0.0
        else:                                            # Mittel je Bereich: der Bass hat nur 2-3 Bins, die Hi-Hat ~70
            d = np.maximum(m - self.prev, 0)
            flux = LOW_W * float(d[:self.nlow].mean()) + float(d.mean())
            kick = float(d[:self.nkick].mean())
        self.prev = m
        self.env = np.roll(self.env, -1)
        self.env[-1] = flux if loud else 0.0
        self.env_kick = np.roll(self.env_kick, -1)
        self.env_kick[-1] = kick if loud else 0.0
        self.filled = min(self.n, self.filled + 1)
        self.quiet = 0 if loud else self.quiet + 1
        if self.quiet > self.fps * 3:                     # 3 s Stille: neues Lied, Tempo neu
            self.bpm, self.conf, self.next_beat, self.filled = 0.0, 0.0, None, 0
            self.env[:] = 0.0
            self.env_kick[:] = 0.0
            return np.array([0.0], np.float32)
        if self.filled >= MIN_S * self.fps and self.k % max(1, int(EVERY_S * self.fps)) == 0:
            self._estimate()
        beat = False
        if self.bpm > 0 and loud:
            if self.next_beat is None:
                self.next_beat = self._phase()
            if self.next_beat is not None and self.k >= self.next_beat:
                beat = True
                period = self.fps * 60.0 / self.bpm
                self.next_beat += period
                while self.next_beat <= self.k:          # nach einer Pause nicht nachholen
                    self.next_beat += period
        return np.array([1.0 if beat else 0.0], np.float32)

    # ---- Tempo und Phase ------------------------------------------------------------------------------------
    def _curve(self, env=None):
        e = (self.env if env is None else env)[-self.filled:].astype(np.float64)
        k = max(3, int(self.fps * 0.5))
        e = np.maximum(e - np.convolve(e, np.ones(k) / k, "same"), 0)
        sd = e.std()
        return None if sd < 1e-9 else (e - e.mean()) / sd

    def score(self, ac, bpm):
        lag = self.fps * 60.0 / bpm
        tot = 0.0
        for mult, w in ((1, 1.0), (2, 0.5), (4, 0.25)):   # kein halber Abstand: der zog das Tempo auf die Haelfte
            L = lag * mult
            i = int(L)
            if 1 <= i < len(ac) - 1:
                tot += w * (ac[i] + (ac[i + 1] - ac[i]) * (L - i))
        return tot * math.exp(-0.5 * (math.log2(bpm / BPM_PRIOR)) ** 2)

    def _estimate(self):
        e = self._curve()
        if e is None:
            return
        nfft = 1 << int(math.ceil(math.log2(2 * len(e))))
        ac = np.fft.irfft(np.abs(np.fft.rfft(e, nfft)) ** 2)[:len(e)]
        ac /= ac[0] + 1e-9
        bpms = np.arange(BPM_MIN, BPM_MAX, 0.5)
        sc = np.array([self.score(ac, b) for b in bpms])
        i = int(np.argmax(sc))
        if sc[i] <= MIN_CONF:                            # kein deutlicher Takt (Rauschen um 0,12, Musik ab etwa 0,5)
            self.conf *= 0.9
            if self.conf < MIN_CONF:
                self.bpm, self.next_beat = 0.0, None
            return
        lo, hi = max(0, i - 1), min(len(bpms) - 1, i + 1)          # fein auf 0,1 BPM
        fine = np.arange(bpms[lo], bpms[hi] + 0.05, 0.1)
        best = float(fine[int(np.argmax([self.score(ac, b) for b in fine]))])
        new, conf = round(best, 1), float(sc[i])
        if self.bpm <= 0 or abs(new - self.bpm) / self.bpm < 0.04 or conf > 1.3 * self.conf:
            changed = self.bpm <= 0 or abs(new - self.bpm) > 1.0
            self.bpm = new
            self.conf = 0.8 * self.conf + 0.2 * conf if not changed else conf
            if changed:
                self.next_beat = None                    # neues Raster: Phase neu bestimmen
        else:
            self.conf *= 0.97                            # alter Wert verliert langsam an Gewicht
        self._follow()

    def _follow(self):
        """Raster jede Sekunde sanft an die Anschlaege angleichen: schon 0,2 BPM Fehler lassen es sonst wegdriften."""
        if self.bpm <= 0 or self.next_beat is None:
            return
        p = self._phase()
        if p is None:
            return
        period = self.fps * 60.0 / self.bpm
        d = (p - self.next_beat + period / 2) % period - period / 2   # kuerzester Weg, -P/2 .. +P/2
        self.next_beat += PHASE_K * d
        while self.next_beat <= self.k:
            self.next_beat += period

    def _phase(self):
        """Naechster Schlag (Blocknummer): Verschiebung, bei der die Bassdrum-Anschlaege der letzten 4 s am besten passen
        (ohne Bassdrum, z. B. Ballade: alle Anschlaege)."""
        e = self._curve(self.env_kick)
        if e is None:
            e = self._curve()
        if e is None or self.bpm <= 0:
            return None
        period = self.fps * 60.0 / self.bpm
        span = min(len(e), int(4.0 * self.fps))
        tail = e[-span:]
        best, best_off = -1e9, 0.0
        for off in np.arange(0.0, period, 0.5):
            pos = np.arange(span - 1 - off, -1, -period).astype(int)
            s = float(tail[pos].sum()) if len(pos) else -1e9
            if s > best:
                best, best_off = s, off
        last = self.k - best_off                         # letzter Schlag auf dem Raster
        nxt = last + period
        while nxt <= self.k:
            nxt += period
        return nxt
