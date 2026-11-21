#!/usr/bin/env python3
"""
radio_play.py - Internetradio im Light-Butler Helfer (Wunsch von Markus, 21.11.2026).

Der Licht-Rechner sagt, welcher Sender spielen soll (GET /api/sm/radio_want, jede Sekunde). Dieser Teil
  * liest den Sender (HTTP, mit "Icy-MetaData: 1"), nimmt das Titelfeld (ICY StreamTitle) heraus,
  * packt den Ton mit ffmpeg aus (MP3, AAC, Ogg; HLS-Sender gibt er ffmpeg direkt),
  * spielt ihn auf dem Standard-Ausgang des Musik-Rechners (Lautstaerke aus dem Panel)
  * und schickt dasselbe Signal per UDP 9022 an den Licht-Rechner (wie die Ton-Weiterleitung, audio_send.packets).
Solange das Radio spielt, ruht die BlackHole-Weiterleitung (sonst kaeme der Ton doppelt an).
Zustand und Titelfeld meldet er mit dem Befehl radio_report. Braucht ffmpeg (Homebrew) und sounddevice.
"""
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request

import numpy as np

from audio_send import NET_PORT, RATE, packets

FFMPEG_PATHS = ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")
UA = "Light-Butler/1.0"
BLOCK = 1024                         # Bilder je Block (rund 23 ms)
POLL_S = 1.0
RETRY_S = 10.0
TITLE_RE = re.compile(rb"StreamTitle='(.*?)';", re.S)


def find_ffmpeg():
    for p in (shutil.which("ffmpeg"),) + FFMPEG_PATHS:
        if p and os.path.isfile(p):
            return p
    return None


def parse_meta(raw):
    """ICY-Metadaten -> StreamTitle (Text) oder None."""
    m = TITLE_RE.search(raw or b"")
    if not m:
        return None
    b = m.group(1)
    for enc in ("utf-8", "latin-1"):
        try:
            return b.decode(enc).strip()[:200]
        except UnicodeDecodeError:
            continue
    return None


def icy_split(chunks, metaint, on_title):
    """Generator: aus dem Datenstrom (Stuecke beliebiger Groesse) nur den Ton, Titel an on_title. metaint 0 = ohne Titel."""
    if not metaint:
        yield from chunks
        return
    buf, left, need_meta = b"", metaint, False
    for c in chunks:
        buf += c
        out = b""
        while buf:
            if not need_meta:
                take = min(left, len(buf))
                out += buf[:take]
                buf, left = buf[take:], left - take
                if left == 0:
                    need_meta = True
            else:
                n = buf[0] * 16
                if len(buf) < 1 + n:
                    break
                if n:
                    t = parse_meta(buf[1:1 + n])
                    if t is not None:
                        on_title(t)
                buf, left, need_meta = buf[1 + n:], metaint, False
        if out:
            yield out


class RadioPlayer:
    """Spielt den Sender, den der Licht-Rechner waehlt.

    Fehlerbericht 21.11.2026 (schnell Sender gewechselt, dann haengt alles bei "verbinde"): Ton-Ausgaenge in mehreren Faeden
    oeffnen und schliessen blockiert Core Audio / PortAudio gegenseitig. Darum gehoert der Ausgang genau einem Faden
    (_out_loop): er bleibt beim Senderwechsel offen, nur die Quelle wechselt. Jeder Sender bekommt eine Nummer (gen);
    Bloecke und Meldungen eines alten Senders werden verworfen. Die Lese-Faeden ruehren PortAudio nie an.
    """

    def __init__(self, pi, web=8080, port=NET_PORT, log=print, sd_mod=None, opener=None, ffmpeg=None):
        self.pi, self.base, self.port, self.log = pi, f"http://{pi}:{web}", port, log
        self.sd, self.opener = sd_mod, opener or urllib.request.urlopen
        self.ffmpeg = ffmpeg
        self.seq, self.vol = -1, 0.8
        self.state, self.title, self.err = "aus", "", ""
        self.codec, self.kbps = "", 0
        self.gen = 0                             # Nummer des aktuellen Senders
        self.lock = threading.Lock()
        self.cur_proc, self.stop_ev = None, None
        self.q = queue.Queue(maxsize=24)         # rund 0,5 s Puffer zwischen Sender und Ausgang
        self.sock, self.addr, self.useq = None, None, 0
        self.last_report = 0.0
        self.fail_t = 0.0
        self.opened = 0                          # wie oft der Ausgang geoeffnet wurde (Tests)
        self._run = False

    def playing(self):
        """Fuer die BlackHole-Weiterleitung: True = Radio schickt den Ton selbst."""
        return self.state in ("verbinde", "spielt")

    # ---- Steuerung vom Licht-Rechner ---------------------------------------------------------------
    def start(self):
        if self.ffmpeg is None:
            self.ffmpeg = find_ffmpeg()
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._out_loop, daemon=True).start()
        return True

    def stop(self):
        self._halt()
        self.state = "aus"
        self._report(force=True)
        self._run = False

    def _get_want(self):
        with self.opener(urllib.request.Request(self.base + "/api/sm/radio_want", headers={"User-Agent": UA}), timeout=3) as r:
            return json.loads(r.read(20000).decode("utf-8"))

    def _report(self, force=False):
        if not force and time.monotonic() - self.last_report < 2.0:
            return
        self.last_report = time.monotonic()
        body = json.dumps({"op": "radio_report", "seq": max(self.seq, 0), "state": self.state, "title": self.title, "err": self.err,
                           "codec": self.codec, "kbps": self.kbps}).encode()
        try:
            with self.opener(urllib.request.Request(self.base + "/api/sm/cmd", data=body, headers={"User-Agent": UA}), timeout=3) as r:
                r.read(2000)
        except (OSError, ValueError):
            pass

    def _loop(self):
        while self._run:
            try:
                w = self._get_want()
                self.vol = max(0.0, min(1.0, float(w.get("vol", 0.8))))
                seq = int(w.get("seq", 0))
                if not w.get("play"):
                    if self.state != "aus":
                        self._halt()
                        self.state, self.title, self.err = "aus", "", ""
                        self._report(force=True)
                elif seq != self.seq or (self.state == "fehler" and time.monotonic() - self.fail_t > RETRY_S) or self.state == "aus":
                    self.seq = seq                     # neuer Sender, oder nach einem Fehler alle 10 s neu versuchen
                    self._halt()
                    self._begin(str(w.get("url") or ""), bool(w.get("hls")), str(w.get("name") or ""))
                    self._report(force=True)
                if self.state == "fehler" and not self.fail_t:
                    self.fail_t = time.monotonic()
                elif self.state != "fehler":
                    self.fail_t = 0.0
            except (OSError, ValueError, TypeError):
                pass                                   # Licht-Rechner gerade nicht erreichbar: weiter wie bisher
            self._report()
            time.sleep(POLL_S)

    # ---- Sender lesen (eigener Faden je Sender, ohne PortAudio) ------------------------------------------
    def _begin(self, url, hls, name):
        if not re.match(r"^https?://", url):
            self.state, self.err = "fehler", "Adresse ungueltig"
            return
        if self.ffmpeg is None:
            self.state, self.err = "fehler", "ffmpeg fehlt (brew install ffmpeg)"
            return
        if self.sd is None:
            try:
                import sounddevice
                self.sd = sounddevice
            except Exception:                          # noqa: BLE001
                self.state, self.err = "fehler", "sounddevice fehlt"
                return
        with self.lock:
            self.gen += 1
            g = self.gen
            self.stop_ev = stop = threading.Event()
        self.state, self.title, self.err, self.codec, self.kbps = "verbinde", "", "", "", 0
        threading.Thread(target=self._decode, args=(url, hls, name, g, stop), daemon=True).start()
        self.log(f"Radio: {name} ({url[:80]})")

    def _halt(self):
        """Alten Sender beenden, ohne zu warten: neue Nummer, ffmpeg beenden, der Faden endet von selbst."""
        with self.lock:
            self.gen += 1
            stop, p = self.stop_ev, self.cur_proc
            self.stop_ev, self.cur_proc = None, None
        if stop is not None:
            stop.set()
        if p is not None:
            try:
                p.kill()
            except OSError:
                pass

    def _mine(self, g):
        return g == self.gen

    def _set_title(self, t, g):
        if self._mine(g) and t != self.title:
            self.title = t
            self.log(f"Radio: {t}")
            self.last_report = 0.0

    def _decode(self, url, hls, name, g, stop):
        resp, proc = None, None
        try:
            args = [self.ffmpeg, "-v", "error", "-nostdin"]
            metaint = 0
            if hls:
                args += ["-user_agent", UA, "-i", url]
            else:
                resp = self.opener(urllib.request.Request(url, headers={"Icy-MetaData": "1", "User-Agent": UA}), timeout=10)
                if stop.is_set():
                    return
                if self._mine(g):
                    self.codec = (resp.headers.get("Content-Type") or "")[:20]
                    try:
                        self.kbps = int(resp.headers.get("icy-br") or 0)
                    except ValueError:
                        self.kbps = 0
                metaint = int(resp.headers.get("icy-metaint") or 0)
                args += ["-i", "pipe:0"]
            args += ["-f", "f32le", "-ac", "2", "-ar", str(RATE), "pipe:1"]
            proc = subprocess.Popen(args, stdin=subprocess.PIPE if resp else subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
            with self.lock:
                if self._mine(g) and not stop.is_set():
                    self.cur_proc = proc
                else:
                    return
            if resp is not None:
                threading.Thread(target=self._feed, args=(resp, metaint, proc, stop, g), daemon=True).start()
            while not stop.is_set():
                raw = proc.stdout.read(BLOCK * 8)
                if not raw:
                    break
                x = np.frombuffer(raw[:len(raw) // 8 * 8], dtype="<f4").reshape(-1, 2)
                while not stop.is_set():
                    try:
                        self.q.put((g, x), timeout=0.2)    # Ausgang bremst auf Echtzeit
                        break
                    except queue.Full:
                        continue
            if not stop.is_set() and self._mine(g):
                self.state, self.err = "fehler", "Sender hat aufgehoert"
        except Exception as e:                         # noqa: BLE001  ein Sender darf den Helfer nie anhalten
            if not stop.is_set() and self._mine(g):
                self.state, self.err = "fehler", str(e)[:160]
                self.log(f"Radio: {name}: {str(e)[:120]}")
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:                      # noqa: BLE001
                    pass
            if proc is not None:
                try:
                    proc.kill()
                except OSError:
                    pass

    def _feed(self, resp, metaint, proc, stop, g):
        def chunks():
            while not stop.is_set():
                c = resp.read(8192)
                if not c:
                    return
                yield c
        try:
            for audio in icy_split(chunks(), metaint, lambda t: self._set_title(t, g)):
                proc.stdin.write(audio)
        except Exception:                              # noqa: BLE001  Sender gewechselt: Strom geschlossen
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    # ---- Ausgang (ein Faden, einziger Nutzer von PortAudio) ---------------------------------------------------
    def _out_loop(self):
        stream, last_data = None, 0.0
        silence = np.zeros((BLOCK, 2), dtype=np.float32)
        while self._run or stream is not None:
            try:
                g, x = self.q.get(timeout=0.1)
            except queue.Empty:
                g, x = None, None
            now = time.monotonic()
            if x is not None and g != self.gen:
                continue                               # Rest eines alten Senders: sofort weg, keine Stille dafuer
            if x is not None and self._run:
                if stream is None:
                    try:
                        stream = self.sd.OutputStream(samplerate=RATE, channels=2, dtype="float32", blocksize=BLOCK)
                        stream.start()
                        self.opened += 1
                    except Exception as e:             # noqa: BLE001
                        stream = None
                        if self._mine(g):
                            self.state, self.err = "fehler", ("Ton-Ausgang: " + str(e))[:160]
                        continue
                if self.state == "verbinde" and self._mine(g):
                    self.state = "spielt"
                    self.last_report = 0.0
                last_data = now
                self._send(x)
                try:
                    stream.write((x * self.vol).astype(np.float32))
                except Exception:                      # noqa: BLE001
                    pass
            elif stream is not None:
                if self._run and self.state in ("verbinde", "spielt") and now - last_data < 8.0:
                    try:
                        stream.write(silence)          # Ausgang bleibt offen, solange ein Sender laeuft oder kommt
                    except Exception:                  # noqa: BLE001
                        pass
                elif now - last_data > 3.0 or not self._run:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:                  # noqa: BLE001
                        pass
                    stream = None

    def _send(self, x):
        """Derselbe Ton an den Licht-Rechner (Eingang Musik-Rechner (Netzwerk))."""
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.addr is None:
            try:
                self.addr = (socket.gethostbyname(self.pi), self.port)
            except OSError:
                return
        pk, self.useq = packets(x, self.useq)
        for p in pk:
            try:
                self.sock.sendto(p, self.addr)
            except OSError:
                return
