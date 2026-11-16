"""Debug-Aufnahme des Toneingangs (Wunsch von Markus, 12.11.2026): ist der Schalter im Bereich Audio-Eingang an, beginnt bei
Signal (Pegel ueber der Stille-Schwelle) eine neue WAV-Datei, mit PRE_S Vorlauf; ist das Signal HOLD_S weg, endet sie; kommt
es wieder, beginnt die naechste.

Mitgeschnitten wird direkt an der Schnittstelle (Fehlerbericht 12.11.2026: "direkt an der Schnittstelle, linker und rechter
Kanal, nicht die Summe"): die Bloecke, wie sie von der Soundkarte bzw. vom Netzwerk-Eingang kommen, vor Kanalwahl und
Verstaerkung, mit allen Kanaelen (Stereo bleibt Stereo), 16 Bit, Abtastrate des Eingangs. feed() legt den Block nur in eine
Warteschlange (der Ton-Faden wartet nie); geschrieben wird in einem eigenen Faden. Laeuft die Warteschlange ueber (Speicher-
karte zu langsam), zaehlt "verworfen" mit.

Sicherungen: hoechstens MAX_FILE_S je Datei (dann gleich die naechste), hoechstens MAX_TOTAL_MB im Ordner (die aeltesten
fallen weg), der Schalter ist nach einem Neustart wieder aus. Nur Ton, aufs Licht wirkt das nie. Die Dateien liegen in
~/lichtshow/aufnahmen (deploy.sh fasst den Ordner nicht an).

MP3 statt WAV (Wunsch 12.11.2026: die WAV-Dateien sind zu gross): ist eine Datei fertig, wandelt ein eigener Faden sie mit ffmpeg
in eine MP3 (Stereo 192 kbit/s, Mono 128 kbit/s) und loescht die WAV erst, wenn die MP3 vollstaendig da ist. Immer nur eine
Umwandlung zur Zeit, mit niedrigster Prioritaet (nice 19, ionice idle, ein Faden): die Show und eine gleich folgende Aufnahme
gehen immer vor. Gemessen 12.11.2026: 10 min Stereo am M1 in 3,6 s (168-fach), am Pi 4 etwa 25-fach erwartet, also rund 25 s
eines von vier Kernen je 10 min Aufnahme. Das Panel zeigt die gemessene Geschwindigkeit. Statt ffmpeg geht auch lame (am Pi
viel kleiner); ohne beide bleiben es WAV-Dateien.
"""
import collections
import json
import math
import os
import shutil
import subprocess
import threading
import time
import wave

import numpy as np

PRE_S = 1.0
HOLD_S = 3.0
MAX_FILE_S = 600.0
MAX_TOTAL_MB = 1000.0
MAX_QUEUE_S = 10.0
NAME_PREFIX = "aufnahme-"
EXTS = (".wav", ".mp3")
INFO = "_info.json"                                       # Laenge und Kanaele der MP3s (aus der WAV gemerkt)
KBPS = {1: 128, 2: 192}


class Recorder:
    def __init__(self, base, rate, threshold_db=lambda: -60.0, log=None, clock=time.time, thread=True, ffmpeg=None):
        self.base, self.rate, self.thr, self.log, self.clock = base, int(rate), threshold_db, log or (lambda t: None), clock
        self.on = False
        self.lock = threading.Lock()
        self.q = collections.deque()                      # (Zeit, Block) vom Ton-Faden
        self.q_n, self.dropped = 0, 0
        self.ev = threading.Event()
        self.pre = collections.deque()                    # Vorlauf: die letzten PRE_S Sekunden (Bloecke als Bytes)
        self.pre_n = 0
        self.wav = None
        self.ch = 0
        self.cur, self.cur_n, self.last_sig = "", 0, 0.0
        self._thread = None
        # Werkzeug: ffmpeg, sonst lame (am Pi das kleinere Paket: sudo apt-get install lame); "" = nicht umwandeln
        self.ffmpeg = (shutil.which("ffmpeg") or shutil.which("lame") or "") if ffmpeg is None else ffmpeg
        self.enc_q = collections.deque()                  # fertige WAVs, die zur MP3 werden
        self.enc_ev = threading.Event()
        self.enc_cur, self.enc_last, self.enc_err = "", None, ""
        self._enc_cleanup()
        if thread:
            self._thread = threading.Thread(target=self._run, name="aufnahme", daemon=True)
            self._thread.start()
            if self.ffmpeg:
                threading.Thread(target=self._enc_run, name="aufnahme-mp3", daemon=True).start()

    # ---- Schalter ----
    def set_on(self, on):
        with self.lock:
            self.on = bool(on)
            if not self.on:
                self.q.clear()
                self.q_n = 0
                self._close()
                self.pre.clear()
                self.pre_n = 0
        self.log("Debug-Aufnahme " + ("an" if on else "aus"))

    # ---- aus dem Ton-Faden, je Block: nur einreihen ----
    def feed(self, block):
        if not self.on:
            return
        b = np.array(block, dtype=np.float32, copy=True)
        if b.ndim == 1:
            b = b[:, None]
        with self.lock:
            if self.q_n + len(b) > MAX_QUEUE_S * self.rate:
                self.dropped += 1
                return
            self.q.append((self.clock(), b))
            self.q_n += len(b)
        self.ev.set()

    def _run(self):
        while True:
            self.ev.wait(0.5)
            self.ev.clear()
            self.process()

    def process(self):
        """Eingereihte Bloecke schreiben (eigener Faden; Tests rufen es direkt auf)."""
        while True:
            with self.lock:
                if not self.q:
                    return
                t, b = self.q.popleft()
                self.q_n -= len(b)
                if not self.on:
                    continue
                try:
                    self._handle(t, b)
                except Exception as e:                   # noqa: BLE001  die Aufnahme darf nie haengen bleiben
                    self.log(f"Debug-Aufnahme: {e}")
                    self._close()

    def _handle(self, now, b):
        db = 20.0 * math.log10(max(float(np.sqrt(np.mean(b * b))), 1e-6))
        s = (np.clip(b, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()   # Kanaele verschraenkt, wie in WAV
        loud = db > float(self.thr())
        if self.wav is not None and b.shape[1] != self.ch:          # Eingang mit anderer Kanalzahl: neue Datei
            self._close()
        if self.wav is None:
            if self.pre and self.ch != b.shape[1]:
                self.pre.clear()
                self.pre_n = 0
            self.ch = b.shape[1]
            self.pre.append(s)
            self.pre_n += len(b)
            while self.pre and self.pre_n - len(self.pre[0]) // (2 * self.ch) >= PRE_S * self.rate:
                self.pre_n -= len(self.pre.popleft()) // (2 * self.ch)
            if loud:
                self._open(now)
                for x in self.pre:
                    self._write(x)
                self.pre.clear()
                self.pre_n = 0
            return
        self._write(s)
        if loud:
            self.last_sig = now
        if now - self.last_sig > HOLD_S:                  # Signal weg: Datei zu, beim naechsten Signal eine neue
            self._close()
        elif self.cur_n >= MAX_FILE_S * self.rate:         # zu lang: gleich die naechste Datei
            self._close()
            self._open(now)

    def _open(self, now):
        os.makedirs(self.base, exist_ok=True)
        stem = NAME_PREFIX + time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
        name, k = stem + ".wav", 2
        while os.path.exists(os.path.join(self.base, name)):
            name, k = f"{stem}-{k}.wav", k + 1
        self.wav = wave.open(os.path.join(self.base, name), "wb")
        self.wav.setnchannels(self.ch)
        self.wav.setsampwidth(2)
        self.wav.setframerate(self.rate)
        self.cur, self.cur_n, self.last_sig = name, 0, now
        self._limit()

    def _write(self, by):
        self.wav.writeframesraw(by)
        self.cur_n += len(by) // (2 * self.ch)

    def _close(self):
        if self.wav is not None:
            try:
                self.wav.close()                         # schreibt die Laenge in den Kopf
            except Exception:                            # noqa: BLE001
                pass
            self.log(f"Debug-Aufnahme: {self.cur} ({self.cur_n / self.rate:.0f} s, {self.ch} Kanaele)")
            if self.ffmpeg and self.cur:
                self.enc_q.append(self.cur)
                self.enc_ev.set()
        self.wav, self.cur, self.cur_n = None, "", 0

    # ---- WAV -> MP3 (eigener Faden, eine nach der anderen, niedrigste Prioritaet) ----
    def _enc_cleanup(self):
        """Nach einem Neustart: halbe MP3s weg, liegengebliebene WAVs (aelteste zuerst) wieder einreihen."""
        try:
            names = os.listdir(self.base)
        except OSError:
            return
        for n in names:
            if n.startswith(NAME_PREFIX) and n.endswith(".mp3.tmp"):
                try:
                    os.remove(os.path.join(self.base, n))
                except OSError:
                    pass
        if self.ffmpeg:
            wavs = [n for n in names if n.startswith(NAME_PREFIX) and n.endswith(".wav")]
            self.enc_q.extend(sorted(wavs, key=lambda n: os.path.getmtime(os.path.join(self.base, n))))

    def _enc_run(self):
        while True:
            self.enc_ev.wait(5.0)
            self.enc_ev.clear()
            self.convert_pending()

    def convert_pending(self):
        while self.enc_q:
            name = self.enc_q.popleft()
            if name != self.cur:
                self.convert(name)

    def _cmd(self, src, dst, ch):
        pre = []
        if shutil.which("nice"):
            pre += ["nice", "-n", "19"]
        if shutil.which("ionice"):                        # Linux: liest und schreibt nur, wenn die Karte frei ist
            pre += ["ionice", "-c", "3"]
        if os.path.basename(self.ffmpeg) == "lame":       # lame liest WAV direkt, gleiche Abtastrate, Stereo bleibt Stereo
            return pre + [self.ffmpeg, "--quiet", "-b", str(KBPS.get(ch, 192)), "--cbr", src, dst]
        return pre + [self.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "1", "-y", "-i", src,
                      "-codec:a", "libmp3lame", "-b:a", f"{KBPS.get(ch, 192)}k", "-f", "mp3", dst]

    def convert(self, name):
        src = os.path.join(self.base, name)
        if not (name.startswith(NAME_PREFIX) and name.endswith(".wav")) or not os.path.isfile(src):
            return False
        try:
            with wave.open(src) as w:
                ch, dur = w.getnchannels(), w.getnframes() / float(w.getframerate() or self.rate)
        except (OSError, EOFError, wave.Error):
            ch, dur = 1, 0.0
        mp3 = src[:-4] + ".mp3"
        tmp = mp3 + ".tmp"
        self.enc_cur = name
        t0 = time.time()
        try:
            r = subprocess.run(self._cmd(src, tmp, ch), capture_output=True, text=True, timeout=max(300.0, dur * 2))
            if r.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) < 1000:
                raise RuntimeError((r.stderr or "").strip().splitlines()[-1][:200] if (r.stderr or "").strip() else f"ffmpeg {r.returncode}")
            os.replace(tmp, mp3)
            self._info_set(os.path.basename(mp3), {"dur": round(dur, 1), "ch": ch})
            os.remove(src)                                # WAV erst weg, wenn die MP3 ganz da ist
            el = time.time() - t0
            self.enc_last = {"name": os.path.basename(mp3), "s": round(el, 1), "x": round(dur / el, 1) if el > 0 else None}
            self.enc_err = ""
            self.log(f"Debug-Aufnahme: {os.path.basename(mp3)} ({dur:.0f} s in {el:.1f} s umgewandelt)")
            return True
        except (OSError, subprocess.SubprocessError, RuntimeError) as e:
            self.enc_err = f"{name}: {e}"
            self.log(f"Debug-Aufnahme: MP3 ging nicht, WAV bleibt: {e}")
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False
        finally:
            self.enc_cur = ""

    def _info(self):
        try:
            with open(os.path.join(self.base, INFO), encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _info_set(self, name, v):
        d = {k: x for k, x in self._info().items() if os.path.exists(os.path.join(self.base, k))}
        d[name] = v
        p = os.path.join(self.base, INFO)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(p + ".tmp", p)

    def _limit(self):
        fs = self._files()
        total = sum(f["size"] for f in fs)
        for f in sorted(fs, key=lambda f: f["t"]):      # aelteste zuerst weg, die laufende nie
            if total <= MAX_TOTAL_MB * 1e6:
                break
            if f["name"] in (self.cur, self.enc_cur):
                continue
            try:
                os.remove(os.path.join(self.base, f["name"]))
                total -= f["size"]
            except OSError:
                pass

    # ---- Panel ----
    def _files(self):
        out = []
        try:
            names = os.listdir(self.base)
        except OSError:
            return out
        info = None
        for n in names:
            if not (n.startswith(NAME_PREFIX) and n.endswith(EXTS)):
                continue
            p = os.path.join(self.base, n)
            if n.endswith(".mp3"):
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                info = self._info() if info is None else info
                i = info.get(n) or {}
                ch = int(i.get("ch") or 2)
                dur = float(i.get("dur") or st.st_size * 8 / (KBPS.get(ch, 192) * 1000))
                out.append({"name": n, "size": st.st_size, "t": round(st.st_mtime), "ch": ch, "dur": round(dur, 1), "mp3": True})
                continue
            try:
                st = os.stat(p)
                with wave.open(p) as w:
                    ch, fr = w.getnchannels(), w.getnframes()
            except (OSError, EOFError, wave.Error):
                ch, fr = 1, max(0, os.path.getsize(p) - 44) // 2 if os.path.exists(p) else 0
                st = os.stat(p) if os.path.exists(p) else None
                if st is None:
                    continue
            out.append({"name": n, "size": st.st_size, "t": round(st.st_mtime), "ch": ch, "dur": round(fr / self.rate, 1),
                        "conv": bool(self.ffmpeg) and n != self.cur})
        # neueste zuerst; gleiche Sekunde: nach Name (Zeitstempel im Namen), sonst haengt die Reihenfolge vom Dateisystem ab
        return sorted(out, key=lambda f: (f["t"], f["name"]), reverse=True)

    def status(self):
        with self.lock:
            fs = self._files()
            return {"on": self.on, "rec": self.wav is not None, "cur": self.cur, "cur_s": round(self.cur_n / self.rate, 1),
                    "ch": self.ch, "dropped": self.dropped,
                    "files": fs[:50], "n": len(fs), "mb": round(sum(f["size"] for f in fs) / 1e6, 1), "max_mb": MAX_TOTAL_MB,
                    "mp3": bool(self.ffmpeg), "enc": {"cur": self.enc_cur, "wait": len(self.enc_q), "last": self.enc_last, "err": self.enc_err}}

    def path_of(self, name):
        """Datei fuers Herunterladen: nur Namen aus dem Ordner (kein Pfad von aussen)."""
        name = os.path.basename(str(name or ""))
        if not (name.startswith(NAME_PREFIX) and name.endswith(EXTS)):
            return None
        p = os.path.join(self.base, name)
        return p if os.path.isfile(p) else None

    def delete_all(self):
        with self.lock:
            n = 0
            self.enc_q.clear()
            for f in self._files():
                if f["name"] in (self.cur, self.enc_cur):
                    continue
                try:
                    os.remove(os.path.join(self.base, f["name"]))
                    n += 1
                except OSError:
                    pass
            return n
