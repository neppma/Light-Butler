#!/usr/bin/env python3
"""
audio.py - Live-Audioanalyse fuer die Szenen-Engine (Phase 3).

Analyzer  : liest die USB-Audiokarte, liefert Pegel, Baender, Beat (aubio),
            Kick-Erkennung (Bass-Onset, kaum Verzoegerung), Spektralschwerpunkt
            und kurz-/langfristigen Pegel in dB (fuer Break/Drop).
Simulator : erzeugt dieselben Daten kuenstlich (128 BPM mit Intro, Groove, Break,
            Drop), damit die Lichtshow ohne Musik getestet werden kann.

Beide haben poll(now=None) -> Features. beat_count und kick_count zaehlen nur hoch;
die Engine erkennt neue Ereignisse an der Differenz.
"""
import math
import os
import queue
import sys
import threading
import time
from collections import deque, namedtuple

import numpy as np

Features = namedtuple(
    "Features",
    "level bass mid high bpm centroid db_short db_long silent beat_count kick_count mode key_conf key meter meter_conf hat_count",
    defaults=(-1, 0, 0.0, 0))
# mode: -1 (Moll) .. +1 (Dur) aus dem Tonartprofil; key_conf: wie deutlich die Tonart erkennbar ist (0..1)
# key: Grundton 0..11 (0 = C, 1 = Cis ... 11 = H), -1 = unbekannt
# meter: Schlaege pro Takt (3 = 3/4, 4 = 4/4), 0 = noch unbekannt; meter_conf: Sicherheit 0..1
# hat_count: Zaehler kurzer Spitzen in den Hoehen (Hi-Hat, Shaker, Clap, Snare)

MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def estimate_mode(chroma):
    """Dur/Moll aus einem Chromavektor (Krumhansl-Profile). Rueckgabe (mode -1..1, confidence 0..1)."""
    if chroma.std() < 1e-9:
        return 0.0, 0.0
    maj = max(np.corrcoef(np.roll(MAJOR, t), chroma)[0, 1] for t in range(12))
    mnr = max(np.corrcoef(np.roll(MINOR, t), chroma)[0, 1] for t in range(12))
    return float(math.tanh(5.0 * (maj - mnr))), float(max(0.0, max(maj, mnr)))

class MeterEstimator:
    """Taktart (3/4 oder 4/4) aus den Betonungen der Schlaege.

    Pro erkanntem Beat wird eine Betonung (Bass + Lautstaerke rund um den Schlag) gemerkt. Eine Taktart
    zeigt sich als Wiederholung der Betonung im Abstand von 3 bzw. 4 Schlaegen (Autokorrelation).
    Andere Taktarten (5/4, 6/8, 7/8 ...) werden nicht unterschieden."""

    def __init__(self, n=48, min_beats=16):
        self.acc = deque(maxlen=n)
        self.min_beats = min_beats
        self.meter, self.conf = 0, 0.0

    def add(self, accent):
        self.acc.append(float(accent))
        if len(self.acc) >= self.min_beats:
            self._evaluate()

    def _r(self, x, lag, denom):
        if lag >= len(x) - 3:
            return 0.0
        return float(np.dot(x[lag:], x[:-lag]) / (len(x) - lag)) / denom

    def _evaluate(self):
        x = np.array(self.acc, dtype=float)
        x -= x.mean()
        denom = float(np.dot(x, x) / len(x))
        if denom < 1e-6:                                   # alle Schlaege gleich stark: keine Aussage moeglich
            self.meter, self.conf = 4, 0.0
            return
        s3 = 0.5 * (self._r(x, 3, denom) + self._r(x, 6, denom))
        s4 = 0.5 * (self._r(x, 4, denom) + self._r(x, 8, denom))
        new = 3 if s3 > s4 else 4
        strength, margin = max(s3, s4), abs(s3 - s4)
        # nur wechseln, wenn die neue Taktart klar vorne liegt (verhindert Hin- und Herspringen)
        if self.meter in (3, 4) and new != self.meter and margin < 0.08:
            new = self.meter
        self.meter = new
        self.conf = max(0.0, min(1.0, strength / 0.6)) * max(0.0, min(1.0, 0.4 + margin / 0.3))

    def reset(self):
        self.acc.clear()
        self.meter, self.conf = 0, 0.0


def meter_label(meter):
    return {3: "3/4", 4: "4/4"}.get(meter, "")


KEY_NAMES = ["C", "Cis", "D", "Es", "E", "F", "Fis", "G", "As", "A", "B", "H"]


def estimate_key(chroma):
    """Tonart aus einem Chromavektor: (mode -1..1, confidence 0..1, Grundton 0..11 oder -1)."""
    if chroma.std() < 1e-9:
        return 0.0, 0.0, -1
    cm = [np.corrcoef(np.roll(MAJOR, t), chroma)[0, 1] for t in range(12)]
    cn = [np.corrcoef(np.roll(MINOR, t), chroma)[0, 1] for t in range(12)]
    maj, mnr = max(cm), max(cn)
    tonic = int(np.argmax(cm)) if maj >= mnr else int(np.argmax(cn))
    return float(math.tanh(5.0 * (maj - mnr))), float(max(0.0, maj, mnr)), tonic


def key_label(key, mode):
    """z. B. 'A-Moll' oder 'Es-Dur'; leer, wenn noch keine Tonart erkannt wurde."""
    if key is None or key < 0:
        return ""
    return f"{KEY_NAMES[key % 12]}-{'Dur' if mode >= 0 else 'Moll'}"


BANDS = {"bass": (20, 150), "mid": (150, 2000), "high": (2000, 12000)}
WEAK_BEAT_CONF = 0.2       # aubio: Sicherheit darunter = Beat im Rauschen (gemessen 15.11.2026: Rauschen 0,1, Musik auch leise 4,7)
METER_AFTER_S = 0.12      # tempo_np (puenktlicher Schlag): Betonung so lange nach dem Schlag messen
METER_WIN_S = 0.18        # ueber dieses Fenster bis jetzt (also ab 0,06 s vor dem Schlag)


class AutoGain:
    """Normiert auf 0..1 relativ zu einem langsam abfallenden Spitzenwert."""

    def __init__(self, decay_s, rate_hz, floor=1e-4):
        self.peak, self.floor = floor, floor
        self.k = 0.5 ** (1.0 / (decay_s * rate_hz))

    def __call__(self, x):
        self.peak = max(x, self.peak * self.k, self.floor)
        return min(x / self.peak, 1.0)


def stable_name(name):
    """Geraetename ohne die wechselnde ALSA-Nummer, z. B. 'USB Audio Device: - (hw:3,0)' -> 'USB Audio Device: -'."""
    import re
    return re.sub(r"\s*\(hw:\d+,\d+\)\s*$", "", name).strip()


def alsa_card(name):
    import re
    m = re.search(r"hw:(\d+),", name or "")
    return int(m.group(1)) if m else None


def _amixer(args, timeout=2.0):
    import subprocess
    try:
        r = subprocess.run(["amixer"] + args, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def hw_controls(card):
    """Aufnahme-Regler der Soundkarte (ALSA), nur solche, die es wirklich gibt: [{name, percent}]."""
    import re
    if card is None:
        return []
    out, cur = [], None
    for line in _amixer(["-c", str(card), "scontents"]).splitlines():
        m = re.match(r"Simple mixer control '(.+)',(\d+)", line)
        if m:
            cur = {"name": m.group(1), "cap": False, "percent": None}
            out.append(cur)
        elif cur is not None:
            if "Capabilities:" in line and "cvolume" in line:
                cur["cap"] = True
            m = re.search(r"Capture (\d+) \[(\d+)%\]", line)
            if m and cur["percent"] is None:
                cur["percent"] = int(m.group(2))
    return [{"name": c["name"], "percent": c["percent"]} for c in out if c["cap"] and c["percent"] is not None]


def hw_set(card, control, percent):
    pct = max(0, min(100, int(percent)))
    if card is None or not _amixer(["-c", str(card), "sset", control, f"{pct}%"]):
        raise ValueError("Der Hardware-Regler laesst sich nicht setzen")


class Analyzer:
    tap = None                                           # Abnehmer des Tons (songrec_id.TitleFinder.feed), sonst None
    raw_tap = None                                       # Abnehmer der rohen Bloecke [n, Kanaele] direkt vom Eingang (recorder.Recorder.feed)

    def __init__(self, device=None, rate=44100, hop=512, win=1024, silence_db=-60.0, audio_file=None):
        self.device, self.rate, self.hop, self.win = device, rate, hop, win
        self.audio_file = audio_file                     # gespeicherte Eingangswahl (Geraet, Gain, Kanal)
        self.gain_db, self.channel = 0.0, "mix"          # Software-Verstaerkung und Kanalwahl (mix | left | right)
        self.dev_name, self.dev_channels, self.error = "", 0, ""
        self.meter = {"rms_db": -120.0, "peak_db": -120.0}
        self.peaks = deque()                             # (Zeit, Spitze in dB) fuer die Spitzenanzeige
        self.clip_t = 0.0                                # letzter Moment mit Vollaussteuerung am Eingang
        self.cfg_lock = threading.Lock()
        self._load_audio_cfg()
        self.silence_db = silence_db
        self.cfg = None                      # live einstellbare Parameter (settings.py), setzt die Show
        self.dt = hop / rate
        self.window = np.hanning(win).astype(np.float32)
        self.freqs = np.fft.rfftfreq(win, 1.0 / rate)
        self.masks = {k: (self.freqs >= lo) & (self.freqs < hi)
                      for k, (lo, hi) in BANDS.items()}
        hz = 1.0 / self.dt
        self.gains = {k: AutoGain(8.0, hz) for k in BANDS}
        self.gain_rms = AutoGain(8.0, hz)
        self.ring = np.zeros(win, np.float32)
        self.bass_hist = deque(maxlen=max(4, int(0.5 / self.dt)))
        self.high_hist = deque(maxlen=max(4, int(0.25 / self.dt)))   # Hoehen der letzten 0,25 s (Hi-Hat-Erkennung)
        self.hat_count, self.last_hat = 0, -1.0
        self.t = 0.0
        self.last_kick = -1.0
        self.beat_count = self.kick_count = 0
        self.weak_beats = 0                              # Beats mit geringer Sicherheit (aubio im Rauschen), zaehlen nicht als Musik
        self.bpm = 0.0
        self.db_short = self.db_long = -60.0
        self._first = True
        self.centroid = 0.5
        self.silent_for = 0.0
        # Chroma (Tonhoehenklassen) aus einem laengeren 4096er-Fenster, alle ca. 0,25 s
        self.cwin = 4096
        self.cring = np.zeros(self.cwin, np.float32)
        self.cwindow = np.hanning(self.cwin).astype(np.float32)
        cf = np.fft.rfftfreq(self.cwin, 1.0 / rate)
        self.csel = (cf >= 150.0) & (cf <= 2000.0)
        self.cpcs = (np.round(12 * np.log2(cf[self.csel] / 440.0) + 69).astype(int)) % 12
        self.chroma = np.zeros(12)
        self.chroma_every = max(1, int(0.25 / self.dt))
        self.nblk = 0
        self.mode, self.key_conf, self.key = 0.0, 0.0, -1
        self.meter_est = MeterEstimator()
        self.acc_hist = deque(maxlen=64)                    # Betonung je Block (Bass + Lautstaerke) fuer die Takterkennung
        self._meter_due, self._meter_audible = None, False  # nur tempo_np: Block, an dem die Betonung des Schlags gemessen wird
        self.state = dict(level=0.0, bass=0.0, mid=0.0, high=0.0)
        self.last_block_time = 0.0
        self.lock = threading.Lock()
        self.tempo = None
        try:
            import aubio
            self.tempo = aubio.tempo("default", win, hop, rate)
            self.tempo.set_silence(-50)
        except ImportError:
            if sys.platform in ("win32", "darwin") or os.environ.get("S2L_TEMPO_NP"):
                from tempo_np import NumpyTempo             # Windows/Mac: aubio oft nicht installierbar, Ersatz nur mit numpy
                self.tempo = NumpyTempo(win, hop, rate)
                self.tempo.set_silence(-50)
                print("Hinweis: aubio fehlt, Beat-Tracking mit dem numpy-Ersatz (tempo_np.py).")
            else:                                           # Pi wie bisher (dort ist aubio installiert)
                print("Hinweis: aubio fehlt, kein Beat-Tracking (nur Kick-Erkennung).")
        self._q = queue.Queue(maxsize=200)
        self.xruns, self.q_drops = 0, 0
        self._run = False
        self._stream = None
        self._thread = None
        self._net = None                                 # Eingang "Mac (Netzwerk)" (audio_net.py), sonst None

    def _c(self, key, default):
        return self.cfg[key] if self.cfg is not None else default

    # ---- Verarbeitung eines Blocks (hop Samples, mono) -----------------------
    def process(self, mono):
        mono = np.ascontiguousarray(mono, dtype=np.float32)
        self.t += self.dt
        rms = float(np.sqrt(np.mean(mono ** 2)))
        db = 20.0 * math.log10(max(rms, 1e-6))
        if self._first:
            self.db_short = self.db_long = db
            self._first = False
        self.db_short += (1 - math.exp(-self.dt / 1.0)) * (db - self.db_short)
        self.db_long += (1 - math.exp(-self.dt / 20.0)) * (db - self.db_long)

        self.ring = np.roll(self.ring, -self.hop)
        self.ring[-self.hop:] = mono
        spec = np.abs(np.fft.rfft(self.ring * self.window)) / self.win
        n = {k: self.gains[k](float(spec[m].mean())) for k, m in self.masks.items()}
        level = self.gain_rms(rms)

        self.acc_hist.append(0.6 * n["bass"] + 0.4 * level)
        audible = db > self._c("silence_db", self.silence_db)
        self.silent_for = 0.0 if audible else self.silent_for + self.dt
        if self.silent_for > 10.0 and self.meter_est.acc:    # lange Stille: neuer Song, Takt neu erkennen
            self.meter_est.reset()

        # Kick: Bass deutlich ueber dem Mittel der letzten 0,5 s
        avg = sum(self.bass_hist) / len(self.bass_hist) if self.bass_hist else 0.0
        kick = (audible and n["bass"] > self._c("kick_bass_min", 0.45) and n["bass"] > self._c("kick_ratio", 1.5) * avg
                and self.t - self.last_kick > self._c("kick_gap_s", 0.28))
        self.bass_hist.append(n["bass"])

        # Hi-Hat/Clap: Hoehen deutlich ueber dem Mittel der letzten 0,25 s (kurze Spitze), hoechstens alle 60 ms
        havg = sum(self.high_hist) / len(self.high_hist) if self.high_hist else 0.0
        hat = (audible and n["high"] > self._c("hat_min", 0.25) and n["high"] > self._c("hat_ratio", 1.6) * havg
               and self.t - self.last_hat > 0.06)
        self.high_hist.append(n["high"])

        beat = False
        if self.tempo is not None:
            beat = bool(self.tempo(mono)[0])

        tot = float(spec.sum())
        if tot > 1e-9:
            c = float((self.freqs * spec).sum() / tot)
            x = min(1.0, max(0.0, math.log2(max(c, 200.0) / 200.0) / math.log2(30.0)))
            self.centroid += (1 - math.exp(-self.dt / 3.0)) * (x - self.centroid)

        # Chroma/Tonart (nur bei hoerbarem Signal)
        self.cring = np.roll(self.cring, -self.hop)
        self.cring[-self.hop:] = mono
        self.nblk += 1
        if audible and self.nblk % self.chroma_every == 0:
            mags = np.sqrt(np.abs(np.fft.rfft(self.cring * self.cwindow))[self.csel])
            ch = np.bincount(self.cpcs, weights=mags, minlength=12)
            ch = ch / (ch.sum() + 1e-12)
            alpha = 1 - math.exp(-(self.chroma_every * self.dt) / 10.0)    # ca. 10 s Gedaechtnis
            self.chroma = (1 - alpha) * self.chroma + alpha * ch
            self.mode, self.key_conf, self.key = estimate_key(self.chroma)

        with self.lock:
            if kick:
                self.kick_count += 1
                self.last_kick = self.t
            if hat:
                self.hat_count += 1
                self.last_hat = self.t
            if beat:
                self.beat_count += 1
                if hasattr(self.tempo, "get_confidence") and float(self.tempo.get_confidence()) < WEAK_BEAT_CONF:
                    self.weak_beats += 1
                self.bpm = float(self.tempo.get_bpm())
                if getattr(self.tempo, "on_time", False):       # Ersatz tempo_np: Schlag puenktlich, Betonung erst danach messen
                    self._meter_due = self.nblk + max(1, int(round(METER_AFTER_S / self.dt)))
                    self._meter_audible = audible
                else:
                    lo, hi = int(0.35 / self.dt), max(1, int(0.03 / self.dt))   # aubio meldet den Schlag etwas spaeter
                    win = list(self.acc_hist)[-lo:-hi] if len(self.acc_hist) > lo else list(self.acc_hist)
                    if win and audible:
                        self.meter_est.add(max(win))
            if self._meter_due is not None and self.nblk >= self._meter_due:
                n_win = max(2, int(round(METER_WIN_S / self.dt)))      # vom Schlag (etwas davor) bis jetzt
                win = list(self.acc_hist)[-n_win:]
                if win and self._meter_audible:
                    self.meter_est.add(max(win))
                self._meter_due = None
            self.state = dict(level=level, **n)
            self.last_block_time = time.time()

    # ---- Audio-Eingang --------------------------------------------------------
    def _callback(self, indata, frames, t, status):
        if status:
            self.xruns += 1                               # Aussetzer der Soundkarte (Seite Zustand)
        if self.raw_tap is not None:                      # Debug-Aufnahme: wie es ankommt, vor Kanalwahl und Gain (reiht nur ein)
            try:
                self.raw_tap(indata)
            except Exception:                             # noqa: BLE001
                pass
        try:
            self._q.put_nowait(indata.copy())
        except queue.Full:
            self.q_drops += 1

    def _select(self, block):
        """Kanalwahl: Summe (Standard), nur links oder nur rechts."""
        if block.shape[1] == 1:
            return block[:, 0]
        if self.channel == "left":
            return block[:, 0]
        if self.channel == "right":
            return block[:, 1]
        return block.mean(axis=1)

    def _loop(self):
        while self._run:
            try:
                block = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            raw_peak = float(np.max(np.abs(block))) if block.size else 0.0
            now = time.time()
            if raw_peak >= 0.985:                          # Vollaussteuerung am Eingang = uebersteuert
                self.clip_t = now
            mono = self._select(block) * (10.0 ** (self.gain_db / 20.0))
            peak_db = 20.0 * math.log10(max(float(np.max(np.abs(mono))), 1e-6))
            rms_db = 20.0 * math.log10(max(float(np.sqrt(np.mean(mono ** 2))), 1e-6))
            self.meter = {"rms_db": rms_db, "peak_db": peak_db}
            self.peaks.append((now, peak_db))
            while self.peaks and now - self.peaks[0][0] > 1.5:
                self.peaks.popleft()
            if self.tap is not None:
                self.tap(mono)
            self.process(mono)

    # ---- Eingang auswaehlen und einstellen (Web-Panel) -------------------------------------------------------------
    def _load_audio_cfg(self):
        import json
        import os
        if not self.audio_file or not os.path.exists(self.audio_file):
            return
        try:
            with open(self.audio_file, encoding="utf-8") as f:
                d = json.load(f)
            self.gain_db = max(-24.0, min(36.0, float(d.get("gain_db", 0.0))))
            self.channel = d.get("channel", "mix") if d.get("channel") in ("mix", "left", "right") else "mix"
            from audio_net import net_alias
            self.saved_device = net_alias(d.get("device") or "")
        except (OSError, ValueError, TypeError):
            pass

    def _save_audio_cfg(self):
        import json
        import os
        if not self.audio_file:
            return
        try:
            tmp = self.audio_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"device": stable_name(self.dev_name), "gain_db": self.gain_db, "channel": self.channel}, f, indent=1)
            os.replace(tmp, self.audio_file)
        except OSError:
            pass

    saved_device = ""

    @staticmethod
    def find_device(name_part, rate=None, sd=None):
        """Eingang nach (stabilem) Namensteil suchen; gibt die Geraetenummer oder None zurueck.
        Windows fuehrt jedes Geraet mehrfach (MME, DirectSound, WASAPI, WDM-KS). Mit rate wird dann der erste Eintrag
        genommen, der diese Abtastrate kann; am Pi gibt es nur einen Treffer, dort bleibt alles wie bisher."""
        if sd is None:
            import sounddevice as sd
        hits = [i for i, d in enumerate(sd.query_devices())
                if d["max_input_channels"] > 0 and name_part and name_part in d["name"]]
        if len(hits) > 1 and rate:
            for i in hits:
                try:
                    ch = min(2, sd.query_devices(i)["max_input_channels"])
                    sd.check_input_settings(device=i, channels=ch, samplerate=rate, dtype="float32")
                    return i
                except Exception:                           # noqa: BLE001
                    continue
        return hits[0] if hits else None

    def list_devices(self):
        from audio_net import NET_NAME
        out = []
        try:
            import sounddevice as sd
            devs = sd.query_devices()
        except Exception:                                   # noqa: BLE001  (ohne Soundkarten-Paket: nur der Mac-Eingang)
            devs = []
        for i, d in enumerate(devs):
            if d["max_input_channels"] > 0:
                out.append({"index": i, "name": d["name"], "stable": stable_name(d["name"]),
                            "channels": d["max_input_channels"], "rate": int(d["default_samplerate"]),
                            "current": d["name"] == self.dev_name})
        out.append({"index": -1, "name": NET_NAME, "stable": NET_NAME, "channels": 2, "rate": self.rate,
                    "current": self.dev_name == NET_NAME})              # Ton vom MacBook ueber das Netzwerk
        return out

    def audio_info(self):
        card = alsa_card(self.dev_name)
        now = time.time()
        return {"devices": self.list_devices(), "current": self.dev_name,
                "channels": self.dev_channels, "rate": self.rate, "gain_db": self.gain_db, "channel": self.channel,
                "hw": hw_controls(card), "error": self.error, "running": self._stream is not None or self._net is not None,
                "net": self._net.status() if self._net is not None else None,
                "clip": now - self.clip_t < 3.0}

    def level(self):
        now = time.time()
        hold = max((p for t, p in self.peaks), default=-120.0)
        return {"rms_db": round(self.meter["rms_db"], 1), "peak_db": round(self.meter["peak_db"], 1),
                "hold_db": round(hold, 1), "clip": now - self.clip_t < 3.0,
                "alive": now - self.last_block_time < 1.0}

    def rescan(self, sd=None):
        """Soundkarten neu suchen (Wunsch von Markus, 07.11.2026: Behringer UCA202 nach dem Start am Pi eingesteckt).
        PortAudio liest die Geraete nur beim Start ein; neu einlesen geht nur mit geschlossenem Eingang. Darum: Eingang zu,
        PortAudio neu starten, denselben Eingang (nach Namen, die Nummern koennen sich verschieben) wieder auf. Ton vom Mac
        laeuft ohne PortAudio weiter. Rueckgabe: die neue Liste der Eingaenge."""
        from audio_net import NET_NAME
        if sd is None:
            import sounddevice as sd
        with self.cfg_lock:
            net = self.device == NET_NAME
            name = self.dev_name
            if not net:
                self._close_stream()
            try:
                sd._terminate()
                sd._initialize()
            except Exception as e:                          # noqa: BLE001
                self.error = f"Geraete neu suchen ging nicht: {str(e)[:100]}"
            if not net:
                idx = self.find_device(stable_name(name)) if name else None
                if idx is not None:
                    self.device = idx
                try:
                    self.start()
                    self.error = ""
                except Exception as e:                      # noqa: BLE001  der alte Eingang ist weg: im Panel einen anderen waehlen
                    self.error = f"Eingang {name or ''} nach dem Neusuchen nicht verfuegbar: {str(e)[:80]}"
        return self.list_devices()

    def configure(self, device=None, gain_db=None, channel=None, hw=None):
        """Eingang waehlen, Software-Gain und Kanal setzen, Hardware-Regler stellen. Fehler als ValueError."""
        with self.cfg_lock:
            if gain_db is not None:
                self.gain_db = max(-24.0, min(36.0, float(gain_db)))
            if channel is not None:
                if channel not in ("mix", "left", "right"):
                    raise ValueError("Ungueltige Kanalwahl")
                self.channel = channel
            if hw:
                hw_set(alsa_card(self.dev_name), hw["control"], hw["percent"])
            if device is not None:
                self._switch(device)
            self._save_audio_cfg()

    def _switch(self, name):
        from audio_net import NET_NAME, net_alias
        name = net_alias(name)
        if name == NET_NAME:                                # Ton vom Mac: kein Geraet zu pruefen
            idx = NET_NAME
            prev_dev, prev_name, prev_ch = self.device, self.dev_name, self.dev_channels
            self._close_stream()
            try:
                self.device = idx
                self.start()
                self.error = ""
            except Exception as e:                          # noqa: BLE001
                self.device, self.dev_name, self.dev_channels = prev_dev, prev_name, prev_ch
                try:
                    self.start()
                except Exception:                           # noqa: BLE001
                    pass
                self.error = f"Wechsel fehlgeschlagen: {str(e)[:100]}"
                raise ValueError(self.error) from None
            return
        import sounddevice as sd
        idx = self.find_device(name, self.rate) if isinstance(name, str) else int(name)
        if idx is None:
            raise ValueError(f"Eingang nicht gefunden: {name}")
        prev_dev, prev_name, prev_ch = self.device, self.dev_name, self.dev_channels
        try:
            info = sd.query_devices(idx, "input")
            n_ch = min(2, info["max_input_channels"])
            sd.check_input_settings(device=idx, channels=n_ch, samplerate=self.rate, dtype="float32")
        except Exception as e:                              # noqa: BLE001
            raise ValueError(f"Eingang nicht nutzbar: {str(e)[:120]}") from None
        self._close_stream()
        try:
            self.device = idx
            self.start()
            self.error = ""
        except Exception as e:                              # noqa: BLE001
            self.device, self.dev_name, self.dev_channels = prev_dev, prev_name, prev_ch
            try:
                self.start()
            except Exception:                               # noqa: BLE001
                pass
            self.error = f"Wechsel fehlgeschlagen: {str(e)[:100]}"
            raise ValueError(self.error) from None

    def _close_stream(self):
        self._run = False
        if self._net is not None:
            self._net.stop()
            self._net = None
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:                               # noqa: BLE001
                pass
            self._stream = None
        if self._thread:
            self._thread.join(timeout=1.0)
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    net_port = 9022                                      # UDP-Port fuer "Mac (Netzwerk)" (Tests: 0 = beliebig)

    def start(self):
        from audio_net import NET_NAME, NetAudioIn
        from audio_net import net_alias
        self.device = net_alias(self.device) if isinstance(self.device, str) else self.device   # alter Name (--device "Mac (Netzwerk)")
        if not self.dev_name and self.saved_device:         # gespeicherte Wahl hat Vorrang vor --device
            idx = NET_NAME if self.saved_device == NET_NAME else self.find_device(self.saved_device, self.rate)
            if idx is not None:
                self.device = idx
        if self.device == NET_NAME:                         # Ton vom MacBook (UDP 9022) statt Soundkarte
            self._net = NetAudioIn(lambda b: self._callback(b, len(b), None, None), self.rate, self.hop, port=self.net_port)
            self._net.start()
            self.dev_name, self.dev_channels = NET_NAME, 2
            print(f"Audio: {NET_NAME} | UDP {self._net.port} | {self.rate} Hz | Block {self.hop}")
            self._run = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return
        import sounddevice as sd
        if isinstance(self.device, str) and not self.device.isdigit():   # --device NAME: selbst aufloesen (Windows: mehrere Treffer)
            idx = self.find_device(self.device, self.rate)
            if idx is not None:
                self.device = idx
        info = sd.query_devices(self.device, "input")
        n_ch = min(2, info["max_input_channels"])
        self.dev_name, self.dev_channels = info["name"], n_ch
        print(f"Audio: {info['name']} | {self.rate} Hz | Block {self.hop} | Kanaele {n_ch}")
        self._run = True
        self._stream = sd.InputStream(device=self.device, channels=n_ch,
                                      samplerate=self.rate, blocksize=self.hop,
                                      dtype="float32", callback=self._callback)
        self._stream.start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._close_stream()

    def poll(self, now=None):
        with self.lock:
            stale = time.time() - self.last_block_time > 1.0
            s = self.state
            return Features(s["level"], s["bass"], s["mid"], s["high"], self.bpm,
                            self.centroid, self.db_short, self.db_long,
                            stale or self.silent_for > self._c("silence_hold_s", 3.0),
                            self.beat_count, self.kick_count, self.mode, self.key_conf, self.key,
                            self.meter_est.meter, self.meter_est.conf, self.hat_count)


class Simulator:
    """Kuenstliche Musik: 128 BPM, 100-s-Zyklus mit Intro, Groove, Build-up, Pause, Drop."""

    def __init__(self, bpm=128.0):
        self.bpm = bpm
        self.t0 = None
        self.last = 0.0
        self.beats = self.kicks = self.hats = 0
        self.db_long = -26.0

    @staticmethod
    def section(t):
        c = t % 100.0
        if c < 16: return "intro"
        if c < 56: return "groove"
        if c < 68: return "build"
        if c < 69: return "gap"
        return "drop"

    def poll(self, now=None):
        now = time.time() if now is None else now
        if self.t0 is None:
            self.t0 = self.last = now
        t = now - self.t0
        sec = self.section(t)
        period = 60.0 / self.bpm
        new = int(t / period) - int((self.last - self.t0) / period)
        dt = max(0.0, now - self.last)
        self.last = now
        if sec != "gap":
            self.beats += max(0, new)
        if sec in ("intro", "groove", "drop"):
            self.kicks += max(0, new)
        if sec in ("groove", "drop"):                          # Hi-Hat auf den Achteln zwischen den Schlaegen
            half = period / 2.0
            self.hats += max(0, int((t - half) / period) - int((t - dt - half) / period)) if t > half else 0
        c = t % 100.0
        prog = (c - 56.0) / 12.0 if sec == "build" else 0.0
        db = {"intro": -26.0, "groove": -14.0, "build": -24.0 + 10.0 * prog,
              "gap": -45.0, "drop": -9.0}[sec]
        self.db_long += (1 - math.exp(-dt / 20.0)) * (-16.0 - self.db_long)
        phase = (t % period) / period
        bass = math.exp(-phase * 6.0) if sec in ("intro", "groove", "drop") else 0.0
        cen = {"intro": 0.35, "groove": 0.6, "build": 0.4 + 0.45 * prog, "gap": 0.3, "drop": 0.75}[sec]
        hi = {"intro": 0.2, "groove": 0.4, "build": 0.2 + 0.75 * prog, "gap": 0.0, "drop": 0.6}[sec]
        lvl = {"intro": 0.35, "groove": 0.7, "build": 0.4 + 0.4 * prog, "gap": 0.05, "drop": 0.95}[sec]
        return Features(lvl, bass, 0.4, hi, self.bpm, cen, db, self.db_long,
                        False, self.beats, self.kicks, 0.6, 0.8, 9, 4, 0.8, self.hats)      # Simulator: A-Dur, 4/4

    def start(self): pass
    def stop(self): pass
