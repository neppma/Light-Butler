#!/usr/bin/env python3
"""
songrec_id.py - Titel und Interpret der laufenden Musik ueber SongRec (Shazam-Erkennung, braucht Internet).

Fuer die Anzeige im Panel und die Liste auf /stats; aufs Licht wirkt nur das Genre ueber Show._style_key. SongRec kann die Soundkarte nicht selbst
oeffnen (die Show belegt sie, und "Mac (Netzwerk)" ist gar kein Geraet). Deshalb merkt sich die Show die letzten 12 s
Ton (feed), schreibt sie alle paar Sekunden in eine kurze WAV-Datei und ruft `songrec recognize --json DATEI` auf,
in einem eigenen Thread und mit niedriger Prioritaet. Die Datei liegt im Home-Ordner, weil das Snap-Paket von SongRec
sonst nichts lesen darf (nicht /tmp und keine versteckten Ordner direkt im Home).
"""
import json
import os
import shlex
import subprocess
import threading
import wave

import numpy as np

DEFAULT_CMD = "/snap/bin/songrec"
DEFAULT_WAV = "~/songrec_tmp/probe.wav"
NOMATCH_WAV = "last_nomatch.wav"
SECONDS = 12                     # so viel Ton pro Anfrage, mehr wertet Shazam nicht aus
RUN_TIMEOUT_S = 45.0
ERROR_PAUSE_S = 120.0            # nach einem Fehler (kein Internet, gesperrt) seltener fragen
MISS_CLEAR = 3                   # so viele Fehlversuche in Folge, dann verschwindet der alte Titel
QUIET_CLEAR_S = 20.0             # so lange Stille, dann verschwindet der alte Titel (kurze Breaks nicht)
PROBE_PEAK = 0.9                 # auf diese Spitze anheben: SongRec hat feste Schwellen, zu leiser Ton ergibt zu wenig Merkmale
PROBE_MAX_GAIN = 100.0           # hoechstens 40 dB, damit aus Rauschen keine laute Probe wird


def error_line(text):
    """Die letzte echte Fehlermeldung von SongRec, ohne die harmlosen Meldungen zu PulseAudio."""
    lines = [ln for ln in text.splitlines() if ln.strip() and "pulseaudio" not in ln.lower()]
    errs = [ln for ln in lines if "ERROR" in ln] or [ln for ln in lines if not ln.startswith(("[", "{"))]   # sonst Text von snap selbst
    return errs[-1].split("] ", 1)[-1][:160] if errs else ""


def parse_result(stdout):
    """Aus der Ausgabe von `songrec --json`: {"title", "artist", "genre"} oder None, wenn kein Lied darin steht."""
    a, b = stdout.find("{"), stdout.rfind("}")
    tr, whole = None, None
    for text in [stdout[a:b + 1] if 0 <= a < b else ""] + [ln for ln in stdout.splitlines() if ln.startswith("{")]:
        try:                                     # Meldungen von SongRec koennen um das JSON herum stehen
            whole = json.loads(text)
            tr = whole.get("track")
        except (ValueError, AttributeError):
            continue
        if tr:
            break
    if not isinstance(tr, dict) or not tr.get("title"):
        return None
    genres = tr.get("genres") if isinstance(tr.get("genres"), dict) else {}
    out = {"title": str(tr["title"])[:120], "artist": str(tr.get("subtitle") or "")[:120],
           "genre": str(genres.get("primary") or "")[:40]}
    matches = whole.get("matches") if isinstance(whole, dict) else None    # wo im Lied der Ausschnitt liegt, fuer die Liedzeile im Panel
    first = matches[0] if isinstance(matches, list) and matches and isinstance(matches[0], dict) else {}
    if isinstance(first.get("offset"), (int, float)) and first["offset"] >= 0:
        out["offset"] = float(first["offset"])
    return out


TAG_WAV = "~/songrec_tmp/tag_probe.wav"   # Tag bearbeiten in der Musik-Datenbank: eigene Datei, stoert die Live-Erkennung nicht
TAG_MAX_BYTES = 3 * 1024 * 1024
_tag_lock = threading.Lock()


def recognize_wav(cmd, wav_file, runner=subprocess.run):
    """SongRec auf eine WAV-Datei: (Art, Lied, Meldung). Art: ok, nomatch, offline, missing, error."""
    env = dict(os.environ, LC_ALL="C.UTF-8", LANGUAGE="en")    # Meldungen auf Englisch, sonst passt der Vergleich unten nicht
    args = ["nice", "-n", "15"] + shlex.split(cmd) + ["recognize", "--json", wav_file]
    try:
        r = runner(args, capture_output=True, text=True, timeout=RUN_TIMEOUT_S, env=env)
    except subprocess.TimeoutExpired:
        return ("error", None, "Zeitueberschreitung")
    except OSError as e:
        return ("missing", None, str(e)[:120])
    out = f"{r.stdout or ''}\n{r.stderr or ''}"      # SongRec schreibt auch Harmloses dazu (PulseAudio, Proxy)
    last = error_line(out)
    if r.returncode in (126, 127):              # nice findet das Programm nicht
        return ("missing", None, last)
    song = parse_result(r.stdout or "")
    if song:
        return ("ok", song, "")
    if "etwork unreachable" in out:
        return ("offline", None, last)
    if r.returncode == 0 and "No match" in out:
        return ("nomatch", None, "")
    return ("error", None, last or "Keine Antwort von SongRec")


def recognize_upload(cmd, data, wav_file=TAG_WAV, runner=subprocess.run):
    """Tag bearbeiten (Wunsch von Markus, 07.11.2026): ein Ausschnitt des Liedes als WAV vom Browser (12 s, Mono), am Pi
    mit SongRec erkannt, nur auf Knopfdruck. Einer nach dem anderen. {"kind", "song", "msg"}."""
    if not isinstance(data, (bytes, bytearray)) or data[:4] != b"RIFF" or data[8:12] != b"WAVE" or len(data) > TAG_MAX_BYTES:
        raise ValueError("kein WAV-Ausschnitt")
    path = os.path.expanduser(wav_file)
    if not _tag_lock.acquire(timeout=1.0):
        raise ValueError("Es laeuft schon eine Erkennung")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        kind, song, msg = recognize_wav(cmd, path, runner)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
        _tag_lock.release()
    return {"kind": kind, "song": song, "msg": msg}


class TitleFinder:
    def __init__(self, rate=44100, cmd=DEFAULT_CMD, wav_file=DEFAULT_WAV, runner=subprocess.run):
        self.rate, self.cmd, self.runner = rate, cmd, runner
        self.wav_file = os.path.expanduser(wav_file)
        self.size = SECONDS * rate
        self.buf = np.zeros(self.size, np.int16)
        self.pos, self.filled = 0, 0
        self.lock = threading.Lock()
        self.active = False              # nur wenn eingeschaltet, sonst kostet feed nichts
        self.busy = False
        self.done = None                 # Ergebnis aus dem Arbeits-Thread, abgeholt in tick
        self.song = None                 # aktuell angezeigtes Lied
        self.status = "wait"             # wait | search | ok | nomatch | offline | missing | error | mixxx
        self.msg = ""
        self.misses = 0
        self.next_t = 0.0
        self.music_since = self.quiet_since = None

    # ---- Ton aus dem Audio-Thread ------------------------------------------------------------------
    def feed(self, mono):
        if not self.active:
            return
        try:
            s = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)[-self.size:]
            with self.lock:
                end = self.pos + len(s)
                if end <= self.size:
                    self.buf[self.pos:end] = s
                else:
                    n = self.size - self.pos
                    self.buf[self.pos:] = s[:n]
                    self.buf[:end - self.size] = s[n:]
                self.pos = end % self.size
                self.filled = min(self.size, self.filled + len(s))
        except (TypeError, ValueError):       # der Audio-Thread darf hieran nie sterben
            pass

    def _snapshot(self):
        with self.lock:
            return np.concatenate((self.buf[self.pos:], self.buf[:self.pos]))

    # ---- Takt aus der Show (40-mal pro Sekunde) ----------------------------------------------------
    def tick(self, now, on, every_s, music, mixxx_plays):
        """Holt Ergebnisse ab und startet bei Bedarf die naechste Anfrage. Gibt ein neu erkanntes Lied zurueck, sonst None."""
        if not on:
            if self.done is not None:           # Antwort einer Anfrage von vor dem Ausschalten verwerfen
                self.done, self.busy = None, False
            if self.active:
                self._reset()
            return None
        self.active = True
        new = self._collect(now, every_s)
        if mixxx_plays:                         # Mixxx kennt den Titel genauer, Shazam nicht fragen
            self.song, self.status, self.misses, self.music_since, self.quiet_since = None, "mixxx", 0, None, None
            return None
        if not music:
            self.music_since = None
            if self.quiet_since is None:
                self.quiet_since = now
            if now - self.quiet_since >= QUIET_CLEAR_S:
                self.song, self.misses, self.msg = None, 0, ""
                if not self.busy and self.status != "missing":
                    self.status = "wait"
            return new
        self.quiet_since = None
        if self.music_since is None:
            self.music_since = now
        if self.status == "mixxx":
            self.status = "wait"
        if (not self.busy and now >= self.next_t and self.filled >= self.size
                and now - self.music_since >= SECONDS):
            self.busy, self.status = True, "search"
            self.snap_t = now                   # hier endet der Ausschnitt: gehoert zur Stelle im Lied
            threading.Thread(target=self._work, args=(self._snapshot(),), daemon=True).start()
        return new

    def _reset(self):
        self.active = False
        with self.lock:
            self.pos, self.filled = 0, 0
        self.song, self.status, self.msg, self.misses = None, "wait", "", 0
        self.next_t, self.music_since, self.quiet_since = 0.0, None, None

    def _collect(self, now, every_s):
        res, self.done = self.done, None
        if res is None:
            return None
        self.busy = False
        kind, song, self.msg = res
        self.next_t = now + (every_s if kind in ("ok", "nomatch") else max(every_s, ERROR_PAUSE_S))
        self.status = kind
        if kind == "ok":
            self.misses = 0
            if "offset" in song:                # Stelle im Lied, am Anfang des Ausschnitts, zur Zeit des Aufnehmens
                song["pos_t"] = getattr(self, "snap_t", now) - SECONDS
            new = song if self.song is None or (song["title"], song["artist"]) != (self.song["title"], self.song["artist"]) else None
            self.song = song
            return new
        if kind == "nomatch":
            self.misses += 1
            if self.misses >= MISS_CLEAR:
                self.song = None
        return None

    # ---- Arbeits-Thread ----------------------------------------------------------------------------
    def _work(self, samples):
        try:
            self.done = self._recognize(samples)
        except Exception as e:                 # noqa: BLE001  (die Show darf daran nie haengen bleiben)
            self.done = ("error", None, str(e)[:120])

    def _write_wav(self, samples):
        """Halbe Abtastrate, Mittelwert aus je zwei Werten: Shazam wertet nur bis 8 kHz aus, die Datei wird halb so gross."""
        os.makedirs(os.path.dirname(self.wav_file), exist_ok=True)
        half = samples[:len(samples) // 2 * 2].astype(np.int32).reshape(-1, 2).mean(axis=1)
        peak = float(np.max(np.abs(half))) if half.size else 0.0
        if peak > 0.0:
            half = half * min(PROBE_PEAK * 32767.0 / peak, PROBE_MAX_GAIN)
        half = half.astype(np.int16)
        with wave.open(self.wav_file, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.rate // 2)
            w.writeframes(half.tobytes())

    def _recognize(self, samples):
        self._write_wav(samples)
        try:
            kind, song, last = recognize_wav(self.cmd, self.wav_file, self.runner)
        except Exception:
            self._drop_wav()
            raise
        if kind == "nomatch":                   # letzte nicht erkannte Probe bleibt zum Nachhoeren liegen
            os.replace(self.wav_file, os.path.join(os.path.dirname(self.wav_file), NOMATCH_WAV))
        else:
            self._drop_wav()
        print(f"Titelerkennung: {kind}" + (f" {song['artist']} - {song['title']}" if song else f" {last}" if kind != "nomatch" else ""), flush=True)
        return (kind, song, "" if kind in ("ok", "nomatch") else last)

    def _drop_wav(self):
        try:
            os.remove(self.wav_file)
        except OSError:
            pass

    # ---- Anzeige -----------------------------------------------------------------------------------
    def public(self):
        """Stand fuers Panel. None, wenn nichts zu zeigen ist (aus, oder Mixxx zeigt den Titel)."""
        if not self.active or self.status == "mixxx":
            return None
        s = self.song or {}
        return {"st": self.status, "title": s.get("title", ""), "artist": s.get("artist", ""),
                "genre": s.get("genre", ""), "msg": self.msg}
