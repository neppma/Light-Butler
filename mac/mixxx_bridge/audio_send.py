#!/usr/bin/env python3
"""
audio_send.py - Ton vom MacBook an den Light-Butler (Pi): Eingang "Mac (Netzwerk)", UDP-Port 9022.

macOS laesst den Ton anderer Programme (Spotify, YouTube) nicht direkt mitlesen. Dafuer gibt es den virtuellen
Audio-Treiber BlackHole (kostenlos):  brew install blackhole-2ch
Im Programm "Audio-MIDI-Setup" ein "Geraet mit mehreren Ausgaengen" aus Lautsprecher und BlackHole 2ch anlegen und als
Ausgabe waehlen: man hoert alles wie gewohnt, und BlackHole bekommt eine Kopie. Dieses Programm liest BlackHole,
rechnet auf 44100 Hz um und schickt den Ton in kleinen Paketen an den Pi. Am Pi im Panel unter Audio-Eingang
"Musik-Rechner (Netzwerk)" waehlen.

Laeuft in der Mixxx-Bruecke mit (mixxx_bridge.py --send PI), oder allein:
    python3 audio_send.py lightbutler.local
Braucht sounddevice und numpy. Fehlt BlackHole, wird alle 5 s neu gesucht.

Windows: kein Zusatz noetig, wenn die Soundkarte "Stereomix" hat (in den Sound-Einstellungen unter Aufnahme
aktivieren) oder der Ton per Kabel am Line-In-Eingang ankommt. Sonst VB-Cable (kostenlos, vb-audio.com) als
Ausgabe waehlen. Gesucht wird der Reihe nach VB-Cable, Stereomix, Line-In (WIN_HINTS), ein eigener Name geht vor
(--audio-device, Teil des Geraetenamens).
"""
import socket
import struct
import sys
import threading
import time

import numpy as np

NET_PORT = 9022
RATE = 44100                  # wie die Analyse am Pi
FRAMES = 256                  # Bilder je Paket: 1024 Byte bei Stereo, passt ohne Fragmentierung in ein UDP-Paket
HEAD = struct.Struct("<4sIIBB2x")
HINT = "blackhole"
WIN_HINTS = ("cable output", "stereomix", "stereo mix", "line in", "line-in", "line-eingang", "leitungseingang")


def default_hints(platform=None):
    """Gesuchte Geraetenamen (Teile, klein) in dieser Reihenfolge: Mac BlackHole, Windows VB-Cable/Stereomix/Line-In."""
    return WIN_HINTS if (platform or sys.platform) == "win32" else (HINT,)


def pick_device(devs, hints):
    """Erstes Eingabegeraet zum ersten passenden Namen (Reihenfolge der hints geht vor der Liste). Index oder None."""
    for h in hints:
        for i, d in enumerate(devs):
            if h in d["name"].lower() and d["max_input_channels"] > 0:
                return i
    return None


def resample(x, src, dst):
    """Einfache lineare Umrechnung der Abtastrate (fuer die Analyse genau genug)."""
    if src == dst or len(x) == 0:
        return x
    n = int(round(len(x) * dst / src))
    if n <= 0:
        return x[:0]
    pos = np.arange(n) * (src / dst)
    i = np.minimum(pos.astype(int), len(x) - 1)
    j = np.minimum(i + 1, len(x) - 1)
    f = (pos - i)[:, None]
    return (x[i] * (1 - f) + x[j] * f).astype(np.float32)


def packets(x, seq):
    """float32-Samples [n, Kanaele] in Pakete zerlegen. Gibt (Liste der Pakete, naechste Folge-Nr.) zurueck."""
    ch = x.shape[1]
    out = []
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    for k in range(0, len(pcm), FRAMES):
        part = pcm[k:k + FRAMES]
        out.append(HEAD.pack(b"S2LA", seq & 0xFFFFFFFF, RATE, ch, 1) + part.tobytes())
        seq += 1
    return out, seq


class AudioSender:
    def __init__(self, pi_host, port=NET_PORT, hint=None, sd_mod=None, sock=None, log=print, paused=None):
        self.pi, self.sd, self.sock, self.log = (pi_host, port), sd_mod, sock, log
        self.hints = (hint.lower(),) if hint else default_hints()
        self.addr, self.addr_t = None, -99.0
        self.stream, self.name, self.dev_rate = None, "", RATE
        self.seq, self.rest = 0, None
        self.sent = 0
        self.paused = paused                          # Funktion: True = ein anderes Programm (Helfer) schickt den Ton
        self.lock = threading.Lock()
        self._run = False

    def _target(self):
        now = time.monotonic()
        if self.addr is None or now - self.addr_t > 30.0:
            self.addr_t = now
            try:
                self.addr = (socket.gethostbyname(self.pi[0]), self.pi[1])
            except OSError:
                pass
        return self.addr

    def feed(self, block, rate):
        """Ein Block vom Audiogeraet (float32 [n, Kanaele]) -> umrechnen -> Pakete an den Pi."""
        x = np.asarray(block, dtype=np.float32)
        if x.ndim == 1:
            x = x[:, None]
        x = x[:, :2]
        y = resample(x, rate, RATE)
        pk, self.seq = packets(y, self.seq)
        addr = self._target()
        if addr is None:
            return
        for p in pk:
            try:
                self.sock.sendto(p, addr)
                self.sent += 1
            except OSError:
                return

    def _callback(self, indata, frames, t, status):
        self.feed(indata, self.dev_rate)

    def connect(self):
        try:
            devs = self.sd.query_devices()
        except Exception:                             # noqa: BLE001
            return False
        i = pick_device(devs, self.hints)
        if i is not None:
            d = devs[i]
            if d:
                try:
                    rate = int(d["default_samplerate"]) or RATE
                    ch = min(2, d["max_input_channels"])
                    self.stream = self.sd.InputStream(device=i, channels=ch, samplerate=rate, blocksize=1024,
                                                      dtype="float32", callback=self._callback)
                    self.stream.start()
                    self.name, self.dev_rate = d["name"], rate
                    self.log(f"Ton: {self.name} ({rate} Hz) geht an {self.pi[0]}:{self.pi[1]}")
                    return True
                except Exception as e:                # noqa: BLE001
                    self.log(f"Ton: {d['name']} nicht zu oeffnen ({e})")
                    self.stream = None
                    return False
        return False

    def start(self):
        if self.sd is None:
            try:
                import sounddevice
                self.sd = sounddevice
            except Exception:                         # noqa: BLE001
                self.log("Ton: sounddevice fehlt (pip install sounddevice), Ton-Weiterleitung aus")
                return False
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def _loop(self):
        told, last_try = False, -99.0
        while self._run:
            if self.paused is not None and self.paused():          # Helfer laeuft: Ton schickt er
                if self.stream is not None:
                    self.stop_stream()
                    self.log("Ton: Weiterleitung uebernimmt der Light-Butler Helfer")
            elif self.stream is None:
                if time.monotonic() - last_try >= 5.0:
                    last_try = time.monotonic()
                    if self.connect():
                        told = False
                    elif not told:
                        self.log("Ton: %s nicht gefunden, Ton-Weiterleitung wartet (alle 5 s neuer Versuch)"
                                 % ("VB-Cable, Stereomix oder Line-In" if self.hints == WIN_HINTS else self.hints[0]))
                        told = True
            elif not self.stream.active:              # Geraet weg (zum Beispiel BlackHole entfernt)
                self.log("Ton: Eingang beendet, suche neu")
                self.stop_stream()
            time.sleep(1.0)

    def stop_stream(self):
        s, self.stream = self.stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:                         # noqa: BLE001
                pass

    def stop(self):
        self._run = False
        self.stop_stream()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Aufruf: python3 audio_send.py <Adresse des Pi>  (zum Beispiel lightbutler.local)")
    s = AudioSender(sys.argv[1])
    if not s.start():
        sys.exit(1)
    print("Ton-Weiterleitung laeuft, Strg+C beendet.")
    try:
        while True:
            time.sleep(5)
            print(f"  {s.sent} Pakete gesendet", flush=True)
    except KeyboardInterrupt:
        s.stop()
