#!/usr/bin/env python3
"""
wled_matrix.py - Muster fuer eine WLED-Pixel-Matrix (Wunsch von Markus, 21.11.2026, Testgeraet 32 x 32 LEDs).

Der Light-Butler rechnet jedes Bild selbst (Plasma, Ringe, Pegel, Funken, Tunnel, Testbild) nach Beat, Kick,
Hi-Hat, Pegel, Phase und Farbe der Show und schickt es per DDP (UDP 4048, das schlanke Echtzeit-Protokoll von WLED)
an die Matrix. Ein Bild mit 32 x 32 LEDs = 3072 Byte = drei UDP-Pakete.

Regeln:
- Standard aus (Einstellung pm_on). Ohne Adresse (matrix.json) und im Trockenlauf wird nichts gesendet.
- Die Matrix ist ein eigenes Ziel: aufs uebrige Licht wirkt sie nie (sie liest nur den Zustand der Show).
- Blitzgrenze wie beim Hi-Hat-Funkeln: ohne Strobe-Erlaubnis loesen Beat, Kick und Hi-Hat hoechstens 2-mal pro
  Sekunde etwas Neues aus, mit ihr hoechstens 8-mal. Kein ganzflaechiger Weiss-Blitz, kein Strobe.
- BLACKOUT = schwarz, FREEZE = Bild steht, ALLES HELL = weiss, Szene Laser = schwarz. Beim Ausschalten und am
  Dienstende gehen schwarze Bilder raus; danach zeigt WLED nach seiner Echtzeit-Pause wieder sein eigenes Programm.
"""
import base64
import colorsys
import ipaddress
import json
import math
import os
import random
import re
import shutil
import socket
import subprocess
import threading

import numpy as np

import pixfont

DDP_PORT = 4048
DDP_MAX = 1440                      # Nutzdaten je Paket (wie WLED selbst)
PATTERNS = ["auto", "plasma", "ringe", "pegel", "funken", "tunnel", "test",
            "schlange", "raster", "scanner", "explosion", "kaleido", "glitch"]   # neue hinten: gespeicherte Nummern bleiben gleich
PATTERN_LABELS = "Auto|Plasma|Ringe|Pegel|Funken|Tunnel|Testbild|Schlange|Raster|Scanner|Explosion|Kaleidoskop|Glitch"
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,62}[A-Za-z0-9])?$")


def gap_s(strobe):
    """Kleinster Abstand zwischen zwei Ausloesern: ohne Strobe-Erlaubnis 0,5 s (2/s), mit 0,125 s (8/s)."""
    return 0.125 if strobe else 0.5


def check_host(s):
    """IP-Adresse oder Hostname der Matrix pruefen. Leer = keine Matrix."""
    s = str(s or "").strip()
    if not s:
        return ""
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        if not HOST_RE.match(s) or ".." in s:
            raise ValueError("Keine gueltige Adresse: " + s[:60])
        return s
    if ip.version != 4 or ip.is_multicast or ip.is_unspecified:
        raise ValueError("Bitte eine IPv4-Adresse eines Geraets angeben")
    return s


def hsv_arr(h, s, v):
    """HSV -> RGB fuer numpy-Felder (h beliebig, s und v 0..1). Rueckgabe (..., 3)."""
    h = np.mod(h, 1.0) * 6.0
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def ddp_packets(data, seq):
    """DDP-Pakete fuer ein ganzes Bild: Kopf 10 Byte, das letzte mit PUSH (WLED zeigt das Bild dann)."""
    out = []
    n = len(data)
    for off in range(0, max(n, 1), DDP_MAX):
        chunk = data[off:off + DDP_MAX]
        last = off + DDP_MAX >= n
        flags = 0x40 | (0x01 if last else 0x00)          # Version 1, PUSH am Ende
        hdr = bytes([flags, seq & 0x0F, 0x0B, 0x01]) + off.to_bytes(4, "big") + len(chunk).to_bytes(2, "big")
        out.append(hdr + bytes(chunk))
    return out


class DdpSender:
    """Schickt Bilder per DDP. Wartet nie (UDP), Fehler werden nur gezaehlt."""

    def __init__(self, host, port=DDP_PORT):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.seq, self.sent, self.errors = 0, 0, 0

    def send(self, data):
        self.seq = self.seq % 15 + 1
        try:
            for p in ddp_packets(data, self.seq):
                self.sock.sendto(p, self.addr)
            self.sent += 1
        except OSError:
            self.errors += 1

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class MatrixFx:
    """Rechnet Bilder (h, w, 3) mit Werten 0..1. Reine Rechnung, eigener Zufall, kein Zugriff auf die Show."""

    def __init__(self, w=32, h=32, seed=7):
        self.rng = random.Random(seed)
        self.resize(w, h)
        self.rings = []                        # (Startzeit, Farbton-Versatz, Staerke)
        self.sparks = np.zeros((h, w))
        self.spark_hue = np.zeros((h, w))
        self.last_trig = -1e9
        self.bars = np.zeros(w)
        self.step_target = 0.0             # Beat-Uhr: springt je Beat um 1, step_cur folgt weich (Bewegung auf dem Beat)
        self.step_cur = 0.0
        self.last_beat = -1e9
        self.surge = 0.0                   # Schub direkt nach dem Beat (Bewegung), klingt in 0,15 s ab
        self.pulse = 0.0                   # Helligkeits-Puls auf den Beat (Blitzgrenze wie alle Ausloeser)
        self.last_pulse = -1e9
        self.ptime = 0.0                   # Zeit des Plasmas: laeuft auf dem Beat schneller
        self.tun = 0.0                     # Lage des Tunnels (Ringe), je Beat ein Ring
        self.tun_last = 0.0
        self.frame = np.zeros((h, w, 3))
        self.snake = 0.0                   # Schlangen-Tunnel: Phase der Kurve
        self.cells = None                  # Strobo-Raster: Helligkeit und Farbton je Kachel
        self.cell_hue = None
        self.checker = 0
        self.scans = []                    # Scanner: (Start, Dauer, Richtung, Farbton)
        self.parts = np.zeros((0, 6))      # Explosion: x, y, vx, vy, Helligkeit, Farbton
        self.last_state = ""
        self.glitch_until = -1.0           # Glitch: bis wann gestoert, mit welchen Versaetzen
        self.glitch_rows = None
        self.glitch_split = 0

    def resize(self, w, h):
        self.w, self.h = int(w), int(h)
        ys, xs = np.mgrid[0:self.h, 0:self.w]
        self.X = (xs + 0.5) / self.w * 2 - 1          # -1..1
        self.Y = (ys + 0.5) / self.h * 2 - 1
        self.R = np.sqrt(self.X ** 2 + self.Y ** 2) / math.sqrt(2)   # 0 Mitte .. 1 Ecke
        self.A = np.arctan2(self.Y, self.X) / (2 * math.pi)
        self.sparks = np.zeros((self.h, self.w))
        self.spark_hue = np.zeros((self.h, self.w))
        self.bars = np.zeros(self.w)
        self.frame = np.zeros((self.h, self.w, 3))

    # ---- Farbe -----------------------------------------------------------------------------
    def color(self, s, hue_field, v):
        """Farbe nach der Show: Farbton der Stimmung, Bunt, Regenbogen, Weiss oder UV (violett, dunkel)."""
        mode = s.get("cmode", "hue")
        if mode == "white":
            return np.repeat(v[..., None], 3, axis=-1)
        if mode == "uv":
            return hsv_arr(np.full_like(v, 0.78), 1.0, v * 0.5)
        base = s.get("hue", 0.0)
        if mode == "multi":
            base = base + 0.5 * self.X
        elif mode == "rainbow":
            base = s["t"] * 0.05 + 0.3 * self.X
        return hsv_arr(base + hue_field, np.ones_like(v), v)

    # ---- Ausloeser (Blitzgrenze) ---------------------------------------------------------------
    def _trigger_ok(self, s):
        if s["t"] - self.last_trig < gap_s(s.get("strobe", False)) - 1e-6:    # 1e-6: Rundung, 120 BPM = genau 0,5 s
            return False
        self.last_trig = s["t"]
        return True

    # ---- Muster ------------------------------------------------------------------------------
    # ---- Beat-Uhr: einmal je Bild, vor allen Mustern -------------------------------------------------
    def clock(self, s):
        """Bewegung im Takt: je Beat springt die Uhr um 1 (weich in rund 0,1 s), dazwischen steht sie fast.
        Ohne Beat (keine Tempo-Erkennung, Stille) laeuft sie langsam weiter. Der Helligkeits-Puls haelt die Blitzgrenze ein."""
        t, dt = s["t"], s.get("dt", 0.025)
        beat = s.get("beat") or (s.get("kick") and not s.get("bpm"))
        if beat:
            self.step_target += 1.0
            self.surge, self.last_beat = 1.0, t
            if t - self.last_pulse >= gap_s(s.get("strobe", False)) - 1e-6:
                self.pulse, self.last_pulse = 1.0, t
        elif t - self.last_beat > 2.0:
            self.step_target += dt * 0.4
        self.step_cur += (self.step_target - self.step_cur) * (1 - math.exp(-dt / 0.07))
        self.surge *= math.exp(-dt / 0.15)
        self.pulse *= math.exp(-dt / 0.14)
        self.ptime += dt * (0.25 + 0.35 * s.get("level", 0.0)) * (0.5 + 3.0 * self.surge)

    def plasma(self, s, k=1.0):
        t = self.ptime * k
        v = (np.sin(self.X * 3.1 + t * 1.3) + np.sin(self.Y * 3.7 - t * 0.9)
             + np.sin(self.R * 7.0 - t * 1.7) + np.sin((self.X + self.Y) * 2.3 + t * 0.6)) / 4.0
        bright = 0.35 + 0.35 * (0.5 + 0.5 * v) + 0.15 * self.pulse
        return self.color(s, 0.12 * v, bright)

    def ringe(self, s, base=0.12):
        t = s["t"]
        if (s.get("beat") or s.get("kick")) and self._trigger_ok(s):
            self.rings.append((t, self.rng.uniform(-0.08, 0.08), 1.0))
        spb = 60.0 / s["bpm"] if s.get("bpm", 0) > 0 else 0.5
        life = max(0.6, 2.0 * spb)
        self.rings = [r for r in self.rings if t - r[0] < life][-8:]
        v = np.zeros((self.h, self.w))
        hue = np.zeros((self.h, self.w))
        for t0, ho, st in self.rings:
            age = (t - t0) / life
            rad = age * 1.15
            g = st * (1 - age) * np.exp(-((self.R - rad) / 0.07) ** 2)
            hue = np.where(g > v, ho + 0.1 * age, hue)
            v = np.maximum(v, g)
        bg = self.plasma(s, 0.6) * base
        return np.maximum(bg, self.color(s, hue, np.clip(v, 0, 1)))

    def pegel(self, s):
        """Balken von unten: links Bass, Mitte Mitten, rechts Hoehen (die Audio-Analyse liefert drei Baender)."""
        xs = np.linspace(0, 1, self.w)
        bass, mid, high = s.get("bass", 0.0), s.get("mid", 0.0), s.get("high", 0.0)
        tgt = np.interp(xs, [0, 0.5, 1], [bass, mid, high])
        tgt = tgt * (0.85 + 0.3 * np.array([self.rng.random() for _ in range(self.w)]))
        if s.get("kick"):
            tgt[: max(1, self.w // 3)] += 0.25
        up = tgt > self.bars
        self.bars = np.where(up, self.bars + 0.6 * (tgt - self.bars), self.bars * 0.88)
        self.bars = np.clip(self.bars, 0, 1)
        height = (1 - (self.Y + 1) / 2)                     # 0 unten .. 1 oben
        on = height <= self.bars[None, :]
        v = np.where(on, 0.55 + 0.45 * height, 0.0)
        return self.color(s, -0.25 * height, v)

    def funken(self, s, base=0.25):
        if (s.get("hat") or s.get("kick") or s.get("beat")) and self._trigger_ok(s):
            n = max(3, self.w * self.h // 40)
            for _ in range(n):
                y, x = self.rng.randrange(self.h), self.rng.randrange(self.w)
                self.sparks[y, x] = 1.0
                self.spark_hue[y, x] = self.rng.uniform(-0.12, 0.12)
        self.sparks *= math.exp(-s.get("dt", 0.025) / 0.18)
        bg = self.plasma(s, 0.5) * base
        return np.maximum(bg, self.color(s, self.spark_hue, self.sparks))

    def tunnel(self, s, speed=1.0):
        d = self.step_cur - self.tun_last         # je Beat ein Ring weiter (im Aufbau schneller: speed)
        self.tun_last = self.step_cur
        self.tun += (d if d < 2.0 else 0.0) * speed
        r = np.maximum(self.R, 0.04)
        stripes = 0.5 + 0.5 * np.sin(2 * math.pi * (0.35 / r + self.tun))
        twist = 0.5 + 0.5 * np.sin(2 * math.pi * (self.A * 4 + self.tun * 0.25))
        v = (0.55 * stripes + 0.45 * twist * stripes) * np.clip(r * 1.6, 0.15, 1.0) * (0.75 + 0.4 * self.pulse)
        return self.color(s, 0.15 * r, v)

    # ---- neue Muster (21.11.2026): mehr Bewegung, Blitze nur ueber die Blitzgrenze -----------------
    def schlange(self, s, speed=1.0):
        """Tunnel mit Kurven: das ferne Ende wandert, man fliegt durch eine Roehre, die sich windet. Je Beat ein Ring."""
        d = self.step_cur - self.tun_last
        self.tun_last = self.step_cur
        self.tun += (d if d < 2.0 else 0.0) * speed
        self.snake += s.get("dt", 0.025) * (0.6 + 1.4 * self.surge) * speed
        r0 = np.maximum(self.R, 0.03)
        far = np.clip(1.0 - r0 * 1.5, 0.0, 1.0) ** 1.5           # Mitte = weit weg: dort biegt die Roehre am meisten
        ph = self.snake + 0.12 / r0
        ox = 0.6 * far * np.sin(ph * 1.3)
        oy = 0.5 * far * np.cos(ph * 0.9)
        r = np.maximum(np.sqrt((self.X - ox) ** 2 + (self.Y - oy) ** 2) / math.sqrt(2), 0.03)
        a = np.arctan2(self.Y - oy, self.X - ox) / (2 * math.pi)
        z = 0.8 / r + self.tun
        stripes = (0.5 + 0.5 * np.sin(2 * math.pi * z)) ** 1.5
        seg = 0.55 + 0.45 * np.sin(2 * math.pi * (a * 5 + z * 0.35))
        v = stripes * seg * np.clip((r - 0.05) * 3.5, 0.0, 1.0)   # fernes Ende dunkel, ohne Flimmern feiner Ringe
        v = np.clip(v * (0.3 / max(0.05, float(v.mean()))), 0, 1)   # gleiche Gesamthelligkeit: die Bewegung flackert nie
        v = v * (0.8 + 0.35 * self.pulse)                           # Puls nur ueber die Blitzgrenze
        return self.color(s, 0.08 * np.sin(z * 0.7), v)

    def _cells(self, n):
        if self.cells is None or self.cells.shape != (n, n):
            self.cells = np.zeros((n, n))
            self.cell_hue = np.zeros((n, n))

    def raster(self, s, all_on=False):
        """Strobo-Raster: auf den Beat blitzen Kacheln auf, mal zufaellig, mal schachbrettartig, beim Drop alle.
        Mit Strobe-Erlaubnis auch auf die Hi-Hats (Blitzgrenze gap_s)."""
        k = max(2, min(self.w, self.h) // 8)                 # 32 Pixel: 8 x 8 Kacheln zu 4 Pixel
        n = max(1, min(self.w, self.h) // k)
        self._cells(n)
        hit = s.get("beat") or s.get("kick") or (s.get("strobe") and s.get("hat"))
        if hit and self._trigger_ok(s):
            if all_on:
                on = np.ones((n, n), dtype=bool)
            elif self.rng.random() < 0.4:
                self.checker ^= 1
                on = (np.add.outer(np.arange(n), np.arange(n)) % 2) == self.checker
            else:
                on = np.array([[self.rng.random() < 0.3 for _ in range(n)] for _ in range(n)])
            hue = self.rng.uniform(-0.15, 0.15)
            self.cells[on] = 1.0
            self.cell_hue[on] = hue + np.array([self.rng.uniform(-0.05, 0.05) for _ in range(int(on.sum()))])
        self.cells *= math.exp(-s.get("dt", 0.025) / 0.14)
        yi = np.minimum((np.arange(self.h) * n) // self.h, n - 1)
        xi = np.minimum((np.arange(self.w) * n) // self.w, n - 1)
        v = self.cells[np.ix_(yi, xi)]
        hue = self.cell_hue[np.ix_(yi, xi)]
        gap = ((np.arange(self.h) % k) == k - 1)[:, None] | ((np.arange(self.w) % k) == k - 1)[None, :]
        v = np.where(gap & (k >= 4), v * 0.25, v)
        return self.color(s, hue, v)

    def scanner(self, s, speed=1.0):
        """Helle Balken schiessen quer, senkrecht oder schraeg durchs Bild, je Beat einer; im Aufbau schneller."""
        t = s["t"]
        if (s.get("beat") or s.get("kick")) and self._trigger_ok(s):
            spb = 60.0 / s["bpm"] if s.get("bpm", 0) > 0 else 0.5
            self.scans.append((t, max(0.15, 0.9 * spb / max(0.5, speed)), self.rng.randrange(6), self.rng.uniform(-0.12, 0.12)))
        self.scans = [x for x in self.scans if t - x[0] < x[1]][-6:]
        v = np.zeros((self.h, self.w))
        hue = np.zeros((self.h, self.w))
        for t0, dur, dr, ho in self.scans:
            p = (t - t0) / dur * 2.6 - 1.3                    # -1.3 .. 1.3 quer durchs Bild
            coord = [self.X, -self.X, self.Y, -self.Y, (self.X + self.Y) / 1.4, (self.X - self.Y) / 1.4][dr]
            g = np.maximum(np.exp(-((coord - p) / 0.1) ** 2),                       # Balken mit kurzem Schweif
                           np.where(coord < p, np.exp(-(p - coord) / 0.25) * 0.35, 0.0))
            hue = np.where(g > v, ho, hue)
            v = np.maximum(v, g)
        bg = self.plasma(s, 0.4) * 0.08
        return np.maximum(bg, self.color(s, hue, v))

    def explosion(self, s, big=False):
        """Bei jedem Kick platzt ein Funkenring aus der Mitte; big (Drop) = viele, schnelle Funken ueber das ganze Bild."""
        dt = s.get("dt", 0.025)
        if (big or s.get("kick") or s.get("beat")) and self._trigger_ok(s):
            n = 90 if big else 28
            cx, cy = (0.0, 0.0) if big else (self.rng.uniform(-0.4, 0.4), self.rng.uniform(-0.4, 0.4))
            hue = self.rng.uniform(-0.15, 0.15)
            new = []
            for _ in range(n):
                ang = self.rng.uniform(0, 2 * math.pi)
                sp = self.rng.uniform(1.2, 2.6 if big else 1.8)
                new.append((cx, cy, sp * math.cos(ang), sp * math.sin(ang), 1.0, hue + self.rng.uniform(-0.06, 0.06)))
            self.parts = np.vstack([self.parts, np.array(new)])[-260:]
        P = self.parts
        if len(P):
            P[:, 0] += P[:, 2] * dt
            P[:, 1] += P[:, 3] * dt
            P[:, 2:4] *= math.exp(-dt / 0.35)
            P[:, 4] *= math.exp(-dt / 0.4)
            self.parts = P = P[(P[:, 4] > 0.03) & (np.abs(P[:, 0]) < 1.3) & (np.abs(P[:, 1]) < 1.3)]
        v = np.zeros((self.h, self.w))
        hue = np.zeros((self.h, self.w))
        if len(P):
            xs = np.clip(((P[:, 0] + 1) / 2 * self.w).astype(int), 0, self.w - 1)
            ys = np.clip(((P[:, 1] + 1) / 2 * self.h).astype(int), 0, self.h - 1)
            ok = (np.abs(P[:, 0]) <= 1) & (np.abs(P[:, 1]) <= 1)
            for x, y, b, h in zip(xs[ok], ys[ok], P[ok, 4], P[ok, 5]):
                if b > v[y, x]:
                    v[y, x], hue[y, x] = b, h
            glow = v.copy()                                  # leichter Schein um jeden Funken
            glow[1:, :] = np.maximum(glow[1:, :], v[:-1, :] * 0.35)
            glow[:-1, :] = np.maximum(glow[:-1, :], v[1:, :] * 0.35)
            glow[:, 1:] = np.maximum(glow[:, 1:], v[:, :-1] * 0.35)
            glow[:, :-1] = np.maximum(glow[:, :-1], v[:, 1:] * 0.35)
            v = glow
        bg = self.plasma(s, 0.5) * 0.06
        return np.maximum(bg, self.color(s, hue, v))

    def kaleido(self, s):
        """Kaleidoskop: achtfach gespiegeltes Muster wie eine Pop-Art-Blume, dreht sich und springt auf dem Beat weiter."""
        ang = self.step_cur * math.pi / 8 + self.ptime * 0.15
        c, sn = math.cos(ang), math.sin(ang)
        x, y = self.X * c - self.Y * sn, self.X * sn + self.Y * c
        u, v = np.abs(x), np.abs(y)
        u, v = np.maximum(u, v), np.minimum(u, v)
        t = self.ptime
        f = (np.sin(u * 7.0 - t * 2.0) + np.sin(v * 9.0 + t * 1.3) + np.sin((u + v) * 5.0 - self.step_cur * 0.8)) / 3.0
        petals = 0.5 + 0.5 * np.sin(2 * math.pi * (self.R * 2.2 - self.step_cur * 0.25))
        bright = np.clip(0.05 + 0.95 * (0.5 + 0.5 * f) ** 3 * (0.35 + 0.65 * petals) * 1.6, 0, 1) * (0.8 + 0.3 * self.pulse)
        return self.color(s, 0.25 * f + 0.1 * self.R, bright)

    def glitch(self, s, force=False):
        """Glitch: ab und zu (auf dem Beat) werden Zeilen kurz verschoben und die Farben verrutschen, wie ein gestoerter Bildschirm."""
        t = s["t"]
        base = (self.schlange(s) if int(self.step_cur // 16) % 2 else self.kaleido(s))
        if (s.get("beat") or s.get("kick")) and (force or self.rng.random() < 0.5) and self._trigger_ok(s):
            self.glitch_until = t + 0.18
            self.glitch_rows = []
            for _ in range(self.rng.randint(2, 5)):
                y0 = self.rng.randrange(self.h)
                self.glitch_rows.append((y0, min(self.h, y0 + self.rng.randint(1, max(2, self.h // 5))),
                                         self.rng.randint(-self.w // 3, self.w // 3)))
            self.glitch_split = self.rng.choice([-2, -1, 1, 2])
        if t >= self.glitch_until or not self.glitch_rows:
            return base
        f = base.copy()
        for y0, y1, dx in self.glitch_rows:
            f[y0:y1] = np.roll(f[y0:y1], dx, axis=1)
        f[..., 0] = np.roll(f[..., 0], self.glitch_split, axis=1)
        f[..., 2] = np.roll(f[..., 2], -self.glitch_split, axis=1)
        return np.clip(f * 1.15, 0, 1)

    def test(self, s):
        """Testbild: oben links rot, oben rechts gruen, unten links blau, Pfeil nach oben in der Mitte."""
        f = np.zeros((self.h, self.w, 3))
        c = max(1, self.w // 8)
        f[:c, :c] = (1, 0, 0)
        f[:c, -c:] = (0, 1, 0)
        f[-c:, :c] = (0, 0, 1)
        mx = self.w // 2
        for y in range(self.h // 4, self.h - self.h // 6):
            f[y, max(0, mx - 1):mx + 1] = (0.6, 0.6, 0.6)
        for i in range(self.w // 5):
            y = self.h // 4 + i
            if y < self.h:
                f[y, max(0, mx - 1 - i)] = (0.6, 0.6, 0.6)
                f[y, min(self.w - 1, mx + i)] = (0.6, 0.6, 0.6)
        return f

    # ---- Auswahl nach Musik ---------------------------------------------------------------------
    def auto(self, s):
        """Auswahl nach der Musik. Ruhe: Plasma; Aufbau: Scanner ueber dem Tunnel, immer schneller; Drop: Explosion und
        Strobo-Raster; sonst je Phrase ein anderes Muster (ab Stufe 2 alle sieben im Wechsel, Stufe 1 die ruhigeren)."""
        st, tier = s.get("state", "normal"), s.get("tier", 1)
        entered = st != self.last_state
        self.last_state = st
        if st == "idle":
            return self.plasma(s, 0.4) * 0.25
        if st == "gap":
            return self.plasma(s, 0.3) * 0.12
        if st == "break":
            return self.kaleido(s) * 0.6 if s.get("phrase", 0) % 2 else self.plasma(s, 0.7) * 0.7
        if st == "build":
            p = s.get("build_p", 0.0)
            return np.maximum(self.tunnel(s, 1.0 + 3.0 * p) * (0.25 + 0.35 * p), self.scanner(s, 1.0 + 2.0 * p) * (0.5 + 0.5 * p))
        if st == "drop":
            return np.maximum(self.explosion(s, big=entered), self.raster(s) * 0.55)
        if tier <= 0:
            return self.plasma(s)
        k = s.get("phrase", 0)
        if tier == 1:
            return [self.ringe, self.schlange, self.kaleido][k % 3](s)
        k %= 7
        if k == 0:
            return np.maximum(self.ringe(s), self.funken(s, 0.0))
        if k == 1:
            return self.schlange(s, 1.3)
        if k == 2:
            return self.pegel(s)
        if k == 3:
            return self.kaleido(s)
        if k == 4:
            return self.glitch(s)
        if k == 5:                         # Scanner auch ohne erkannten Aufbau (Rueckmeldung Markus: kam in Auto nie)
            return np.maximum(self.scanner(s), self.plasma(s, 0.6) * 0.15)
        return np.maximum(self.tunnel(s), self.explosion(s) * 0.7)

    def render(self, s):
        """Ein Bild nach dem Zustand s (dict). Gibt (h, w, 3) mit 0..1 zurueck."""
        ov = s.get("override")
        if ov == "blackout" or s.get("dark"):
            self.frame = np.zeros((self.h, self.w, 3))
            return self.frame
        if s.get("frozen"):
            return self.frame
        if ov == "allbright":
            self.frame = np.ones((self.h, self.w, 3)) * 0.6
            return self.frame
        self.clock(s)
        pat = s.get("pattern", "auto")
        fn = getattr(self, pat if pat in PATTERNS else "auto")
        f = np.clip(fn(s), 0.0, 1.0)
        self.frame = f
        return f


LOUD_FLOOR = 0.12                   # Huellkurve: leiseste Stelle bei voller Staerke noch 12 % hell
PIC_FADE_S = 0.6                    # Bilder blenden weich ein und aus (kein Blitz)
PIC_MAX_BYTES = 5_000_000


def find_ffmpeg():
    for p in (shutil.which("ffmpeg"), "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"):
        if p and os.path.isfile(p):
            return p
    return None


def decode_image(data, w, h):
    """JPEG/PNG -> (h, w, 3) mit 0..1, auf das Quadrat zugeschnitten. Ueber ffmpeg (am Pi installiert); ohne ffmpeg None."""
    exe = find_ffmpeg()
    if not exe or not data or len(data) > PIC_MAX_BYTES:
        return None
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=area,crop={w}:{h}"
    try:
        r = subprocess.run([exe, "-v", "error", "-i", "pipe:0", "-vf", vf, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "pipe:1"], input=data, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode or len(r.stdout) != w * h * 3:
        return None
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(h, w, 3) / 255.0


def _rgb(h, sat=1.0, val=1.0):
    return colorsys.hsv_to_rgb(h % 1.0, sat, val)


def text_colors(s):
    """Farben der Laufschrift: Titel weiss, Interpret in der Farbe der Stimmung, Album gedaempft (UV: alles violett)."""
    hue = s.get("hue", 0.0) or 0.0
    if s.get("cmode") == "uv":
        v = _rgb(0.78, 1.0, 0.7)
        return v, v, v
    return (1.0, 1.0, 1.0), _rgb(hue, 0.75, 1.0), _rgb(hue + 0.5, 0.45, 0.8)


def text_speed(s, px_per_beat):
    """Laufschrift im Takt: so viele Pixel je Beat (ohne Tempo 110 BPM)."""
    bpm = s.get("bpm") or 0
    return max(4.0, px_per_beat * (bpm if bpm > 0 else 110.0) / 60.0)


class ImgSlide:
    def __init__(self, img, dur):
        self.img, self.dur = img, dur

    def left(self, t):
        return self.dur - t

    def render(self, t, s, base):
        return self.img


class LineSlide:
    """A: eine grosse Zeile (Schrift doppelt, 14 Pixel hoch) "Interpret - Titel" laeuft von rechts nach links."""

    def __init__(self, info, s, w, h, px_per_beat, min_s):
        tc, ac, _ = text_colors(s)
        seg = [(info["artist"], ac), (" - ", ac), (info["title"], tc)] if info.get("artist") else [(info["title"], tc)]
        self.mask, self.col = pixfont.render(seg, scale=2)
        self.w, self.h, self.speed = w, h, text_speed(s, px_per_beat)
        self.dur = min(30.0, max(min_s, (self.mask.shape[1] + w) / self.speed))

    def left(self, t):
        return self.dur - t

    def render(self, t, s, base):
        f = (base * 0.2) if base is not None else np.zeros((self.h, self.w, 3))
        return pixfont.blit(f, self.mask, self.col, self.w - t * self.speed, (self.h - self.mask.shape[0]) // 2)


class LinesSlide:
    """B: drei Zeilen (Titel, Interpret, Album); was hineinpasst, steht, laengere Zeilen laufen, jede in eigenem Tempo."""

    def __init__(self, info, s, w, h, px_per_beat, min_s):
        tc, ac, lc = text_colors(s)
        rows = [(info.get("title"), tc, 1.0), (info.get("artist"), ac, 0.75), (info.get("album"), lc, 0.6)]
        rows = [r for r in rows if r[0]]
        sp = h // max(1, len(rows))
        base_speed = text_speed(s, px_per_beat)
        self.rows = []
        dur = min_s
        for i, (txt, col, k) in enumerate(rows):
            m, c = pixfont.render([(txt, col)])
            v = base_speed * k
            self.rows.append((m, c, i * sp + (sp - m.shape[0]) // 2, v))
            if m.shape[1] > w:
                dur = max(dur, (m.shape[1] + w) / v)
        self.w, self.h, self.dur = w, h, min(30.0, dur)

    def left(self, t):
        return self.dur - t

    def render(self, t, s, base):
        f = (base * 0.15) if base is not None else np.zeros((self.h, self.w, 3))
        for m, c, y, v in self.rows:
            mw = m.shape[1]
            if mw <= self.w:
                x = (self.w - mw) // 2
            else:
                x = self.w - (t * v) % (mw + self.w)
            pixfont.blit(f, m, c, x, y)
        return f


class BandSlide:
    """C: Cover oben, unten ein Laufband "Interpret - Titel · Album" (wie ein Nachrichtenband)."""

    def __init__(self, info, s, w, h, px_per_beat, min_s, cover=None):
        tc, ac, lc = text_colors(s)
        seg = []
        if info.get("artist"):
            seg += [(info["artist"], ac), (" - ", ac)]
        seg.append((info["title"], tc))
        if info.get("album"):
            seg += [(" · ", lc), (info["album"], lc)]
        self.mask, self.col = pixfont.render(seg)
        self.cover, self.w, self.h, self.speed = cover, w, h, text_speed(s, px_per_beat) * 0.8
        self.dur = min(30.0, max(min_s, (self.mask.shape[1] + w) / self.speed))

    def left(self, t):
        return self.dur - t

    def render(self, t, s, base):
        if self.cover is not None:
            f = self.cover.copy()
        else:
            f = (base * 0.3) if base is not None else np.zeros((self.h, self.w, 3))
        band = pixfont.H + 2
        f[self.h - band:] = 0.0
        return pixfont.blit(f, self.mask, self.col, self.w - t * self.speed, self.h - band + 1)


class WordsSlide:
    """D: Wort fuer Wort im Takt (Titel, dann Interpret). Jeder Beat bringt das naechste Wort, es leuchtet auf und klingt ab.
    Blitzgrenze wie alle Ausloeser (ohne Strobe-Erlaubnis hoechstens 2 neue Woerter pro Sekunde)."""

    def __init__(self, info, s, w, h, px_per_beat, min_s):
        tc, ac, _ = text_colors(s)
        words = [(x, tc) for x in str(info.get("title") or "").upper().split()]
        words += [(x, ac) for x in str(info.get("artist") or "").upper().split()]
        self.words = []
        for x, col in words:
            if pixfont.width(x, 2) <= w:
                self.words.append(pixfont.render([(x, col)], 2))
            else:
                part = ""
                for ch in x:                              # zu lang: in Stuecke, die in eine Zeile passen
                    if part and pixfont.width(part + ch) > w:
                        self.words.append(pixfont.render([(part, col)]))
                        part = ""
                    part += ch
                if part:
                    self.words.append(pixfont.render([(part, col)], 2 if pixfont.width(part, 2) <= w else 1))
        self.w, self.h = w, h
        self.i, self.t_word, self.env, self.last_t = -1, -1e9, 0.0, None
        self.end = None

    def left(self, t):
        return (self.end - t) if self.end is not None else 99.0

    def render(self, t, s, base):
        dt = 0.0 if self.last_t is None else max(0.0, t - self.last_t)
        self.last_t = t
        beat = s.get("beat") or (s.get("kick") and not s.get("bpm"))
        due = t - self.t_word >= gap_s(s.get("strobe", False)) - 1e-6 and (beat or t - self.t_word > 1.2)
        if self.end is None and due:
            self.i += 1
            self.t_word, self.env = t, 1.0
            if self.i >= len(self.words):
                self.end = t + 0.6
        self.env = max(0.3, self.env * math.exp(-dt / 0.35))
        f = (base * 0.15) if base is not None else np.zeros((self.h, self.w, 3))
        if 0 <= self.i < len(self.words):
            m, c = self.words[self.i]
            pixfont.blit(f, m, c * self.env, (self.w - m.shape[1]) // 2, (self.h - m.shape[0]) // 2)
        return f


TEXT_SLIDES = {1: LineSlide, 2: LinesSlide, 3: BandSlide, 4: WordsSlide}
TEXT_AUTO = 5                              # pm_text 5: jede Folge zufaellig eine der vier Arten
TEXT_LABELS = "aus|A: eine Zeile|B: drei Zeilen|C: Cover mit Laufband|D: Wort fuer Wort im Takt"


class LyricOverlay:
    """Liedtext auf der Matrix (21.11.2026): die gesungene Zeile als Laufschrift (laeuft genau in der Zeit der Zeile durch)
    oder Wort fuer Wort (in der Zeit der Zeile gleich verteilt). Neue Woerter kommen ohne Strobe-Erlaubnis hoechstens
    zweimal pro Sekunde: schnelle Woerter werden zu Gruppen in bis zu drei Zeilen zusammengefasst. Der Effekt laeuft
    gedaempft dahinter weiter."""
    MODES = {1: ("scroll", True), 2: ("words", True), 3: ("scroll", False), 4: ("words", False)}

    def __init__(self):
        self.key = None
        self.alpha = 0.0
        self.mask = self.col = None
        self.chunks = []                  # Wort-Modus: [(Beginn, Maske, Farbe)]
        self.last = None                  # zuletzt gezeigte Zeile (fuer das Ausblenden)

    def _prepare(self, lyr, s, w, h, kind, strobe):
        tc, ac, _ = text_colors(s)
        col = tc if lyr.get("chorus") else ac
        text = " ".join(str(lyr["text"]).split())
        dur = max(0.3, float(lyr["t1"]) - float(lyr["t0"]))
        if kind == "scroll":
            sc = 2 if (pixfont.width(text, 2) + w) / dur <= 90.0 else 1
            self.mask, self.col = pixfont.render([(text, col)], sc)
            self.chunks = []
            return
        words = text.split() or [text]
        slot = dur / len(words)
        gap = gap_s(strobe)
        chunks, cur, start = [], [], 0.0
        for i, x in enumerate(words):
            if cur and (i * slot - start >= gap or len(cur) >= 4):
                chunks.append((start, cur))
                cur, start = [], i * slot
            cur.append(x)
        if cur:
            chunks.append((start, cur))
        self.chunks = []
        for st, ws in chunks:
            one = " ".join(ws)
            if pixfont.width(one, 2) <= w:
                m, c = pixfont.render([(one, col)], 2)
            else:
                pieces = []
                for x in ws:                     # zu lange Woerter: eng geschrieben, sonst in Stuecke, die in eine Zeile passen
                    if pixfont.width(x) <= w or pixfont.width(x, 1, 0) <= w:
                        pieces.append(x)
                        continue
                    part = ""
                    for chx in x:
                        if part and pixfont.width(part + chx) > w:
                            pieces.append(part)
                            part = ""
                        part += chx
                    pieces.append(part)
                lines, ln = [], ""
                for x in pieces:                 # Zeilen zu hoechstens w Pixeln
                    cand = (ln + " " + x).strip()
                    if ln and pixfont.width(cand) > w:
                        lines.append(ln)
                        ln = x
                    else:
                        ln = cand
                lines.append(ln)
                lines = lines[: max(1, h // 8)]
                rows = [pixfont.render([(x, col)], 1, 1 if pixfont.width(x) <= w else 0) for x in lines]
                mw = max(r[0].shape[1] for r in rows)
                m = np.zeros((8 * len(rows) - 1, mw), dtype=bool)
                c = np.zeros((8 * len(rows) - 1, mw, 3))
                for k, (rm, rc) in enumerate(rows):
                    x0 = (mw - rm.shape[1]) // 2
                    m[8 * k:8 * k + 7, x0:x0 + rm.shape[1]] = rm
                    c[8 * k:8 * k + 7, x0:x0 + rm.shape[1]] = rc
            self.chunks.append((st, m, c))

    def render(self, frame, lyr, s, mode, allowed):
        """Bild mit Liedtext (oder das unveraenderte Bild). lyr = {text, t0, t1, pos, chorus} von der Show."""
        h, w = frame.shape[:2]
        kind, only_chorus = self.MODES.get(int(mode), (None, True))
        show = bool(kind and allowed and lyr and str(lyr.get("text") or "").strip() and (lyr.get("chorus") or not only_chorus))
        dt = s.get("dt", 0.025)
        if show:
            key = (lyr["text"], round(float(lyr["t0"]), 2), kind, w, h, bool(s.get("strobe")))
            if key != self.key:
                self.key = key
                self._prepare(lyr, s, w, h, kind, bool(s.get("strobe")))
            self.last = dict(lyr)
        elif self.last is not None:
            self.last["pos"] = float(self.last["pos"]) + dt      # beim Ausblenden laeuft die Zeile weiter
        self.alpha += (1 - math.exp(-dt / 0.12)) * ((1.0 if show else 0.0) - self.alpha)
        if self.alpha < 0.02 or self.last is None or self.key is None:
            if not show:
                self.last = None
            return frame
        lyr = self.last
        rel = max(0.0, float(lyr["pos"]) - float(lyr["t0"]))
        dur = max(0.3, float(lyr["t1"]) - float(lyr["t0"]))
        out = frame * (1 - 0.75 * self.alpha)
        if self.key[2] == "scroll":
            mw = self.mask.shape[1]
            x = w - min(1.0, rel / dur) * (mw + w)
            return pixfont.blit(out, self.mask, self.col, x, (h - self.mask.shape[0]) // 2, self.alpha)
        cur = None
        for st, m, c in self.chunks:
            if st <= rel + 1e-6:
                cur = (m, c)
        if cur is None:
            return out
        m, c = cur
        return pixfont.blit(out, m, c, (w - m.shape[1]) // 2, (h - m.shape[0]) // 2, self.alpha)


class Pictures:
    """Bilder und Laufschrift zum laufenden Lied (Cover, Interpret, Album) im Wechsel mit dem Effekt.
    Laden und Umrechnen im eigenen Faden; die Show liest nur fertige Bilder und wartet nie."""

    def __init__(self, decode=decode_image):
        self.decode = decode
        self.key = None
        self.pics = []                     # [(Art, Feld (h, w, 3))]
        self.info = {}                     # Interpret, Titel, Album fuer die Laufschrift
        self.seq_t = None                  # Beginn der laufenden Folge
        self.next_t = None                 # wann die naechste beginnt (None = nie)
        self.slides, self.si, self.slide_t0 = [], 0, 0.0
        self.lock = threading.Lock()
        self.loading = False
        self.status = "kein Lied"          # fuer die Seite /matrix: was mit den Bildern ist
        self.rng = random.Random()         # Laufschrift Auto: eigener Zufall
        self.last_mode = 0

    def song(self, key, song, provider, w, h, now, text_provider=None):
        """Neues Lied (oder andere Groesse): alte Bilder weg, neue im Hintergrund holen."""
        if key == self.key:
            return
        with self.lock:
            self.key, self.pics, self.info, self.seq_t, self.next_t = key, [], {}, None, None
        if key is None or (provider is None and text_provider is None):
            self.status = ("kein Lied (Titel kommen von Mixxx, Auto-DJ, Show oder Internetradio)" if provider or text_provider
                           else "nicht verfuegbar")
            return
        self.status = "Bilder werden geholt"

        def work():
            try:
                raw = provider(song) or [] if provider else []
            except Exception:              # noqa: BLE001  ein fehlendes Bild haelt nichts auf
                raw = []
            try:
                info = text_provider(song) or {} if text_provider else {}
            except Exception:              # noqa: BLE001
                info = {}
            info = {k: str(info.get(k) or "").strip()[:120] for k in ("artist", "title", "album")}
            if not info["title"]:
                info = {}
            out = []
            for kind, data in raw[:6]:
                a = self.decode(data, w, h)
                if a is not None:
                    out.append((kind, a))
            with self.lock:
                if self.key == key:
                    self.pics, self.info = out, info
                    self.next_t = 0.0 if out or info else None
                    st = []
                    if out:
                        st.append("%d Bild(er): %s" % (len(out), ", ".join(k for k, _ in out)))
                    elif raw and self.decode is decode_image and not find_ffmpeg():
                        st.append("ffmpeg fehlt am Licht-Rechner (sudo apt install ffmpeg)")
                    elif raw:
                        st.append("Bilder nicht lesbar")
                    elif provider is not None:
                        st.append("zu diesem Lied gibt es kein Bild")
                    if info:
                        st.append("Text: " + (info["artist"] + " - " if info["artist"] else "") + info["title"])
                    self.status = " · ".join(st)
        threading.Thread(target=work, daemon=True).start()

    def _build(self, s, w, h, pic_s, mode, px_per_beat):
        pics, info = list(self.pics), self.info
        slides = []
        cover = None
        if mode == 3 and info and pics and pics[0][0] == "titel":
            cover = pics.pop(0)[1]
        if mode == 3 and info:
            slides.append(BandSlide(info, s, w, h, px_per_beat, pic_s, cover))
        slides += [ImgSlide(a, pic_s) for _, a in pics]
        if mode in (1, 2, 4) and info:
            slides.append(TEXT_SLIDES[mode](info, s, w, h, px_per_beat, pic_s))
        return slides

    def play(self, now, s, base, pic_s, every, allowed, mode=0, px_per_beat=5.0, size=None):
        """(Bild, Deckkraft 0..1) fuer dieses Bild der Show, sonst (None, 0)."""
        with self.lock:
            if self.seq_t is None:
                if not allowed or self.next_t is None or now < self.next_t:
                    return None, 0.0
                h, w = size if size is not None else ((base.shape[0], base.shape[1]) if base is not None else (32, 32))
                if mode == TEXT_AUTO:      # Auto (21.11.2026): jede Folge eine andere Art, nie zweimal dieselbe hintereinander
                    self.last_mode = self.rng.choice([m for m in TEXT_SLIDES if m != self.last_mode])
                    mode = self.last_mode
                self.slides = self._build(s, w, h, pic_s, mode, px_per_beat)
                if not self.slides:
                    return None, 0.0
                self.seq_t, self.si, self.slide_t0 = now, 0, now
            while self.si < len(self.slides) and self.slides[self.si].left(now - self.slide_t0) <= 0:
                self.si += 1
                self.slide_t0 = now
            if self.si >= len(self.slides) or not allowed:
                self.seq_t = None
                self.next_t = now + every if every > 0 else None
                return None, 0.0
            sl = self.slides[self.si]
            tt = now - self.slide_t0
            a = min(1.0, (now - self.seq_t) / PIC_FADE_S)
            if self.si == len(self.slides) - 1:
                a = min(a, sl.left(tt) / PIC_FADE_S)
        return sl.render(tt, s, base), max(0.0, a)

    def alpha(self, now, pic_s, every, allowed):
        """Nur Bilder (ohne Laufschrift): (Bild, Deckkraft)."""
        return self.play(now, {"t": now}, None, pic_s, every, allowed, 0)


def to_bytes(frame, bright, rot=0, serp=False, gamma=1.0):
    """Bild (h, w, 3, 0..1) -> Bytes in LED-Reihenfolge: Gamma, Helligkeit, Drehung (0..3 x 90 Grad), Schlangenlinie.
    Gamma (21.11.2026): LEDs leuchten linear, ein Bildschirm nicht. Ohne Korrektur sind 10 % am Bildschirm fast schwarz,
    an der Matrix aber gut sichtbar (Fehlerbericht Markus: dunkle Flaechen hell, Funken klingen traege aus)."""
    f = np.rot90(frame, k=-int(rot) % 4)
    if gamma and abs(gamma - 1.0) > 1e-6:
        f = np.clip(f, 0, 1) ** float(gamma)
    if serp:
        f = f.copy()
        f[1::2] = f[1::2, ::-1]
    return (np.clip(f * bright, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes()


class Matrix:
    """Verbindet MatrixFx mit der Show: Einstellungen, Adresse (matrix.json), Versand, Vorschau fuers Panel."""

    def __init__(self, path=None, dry=False, port=DDP_PORT):
        self.path, self.port = path, port
        self.dry = dry
        self.fx = MatrixFx()
        self.sender = None
        self.host = self._load()
        self.preview_until = 0.0
        self.reachable = None              # None = nicht geprueft, False = antwortet nicht (dann kein Senden), _watch_hosts alle 5 s
        self.env = 1.0                     # Lautstaerke-Huellkurve 0..1
        self.lyr = LyricOverlay()          # Liedtext im Refrain
        self.lock = threading.Lock()
        self.last = np.zeros((32, 32, 3), dtype=np.uint8)
        self.was_on = False
        self.pictures = None               # Lieferant der Bilder zum Lied (ShowManager.matrix_pictures, setzt das Panel)
        self.song_text = None              # Lieferant von Interpret, Titel, Album (ShowManager.matrix_song_text)
        self.pics = Pictures()
        self.quiet_k = 1.0                 # Stille (keine Musik, Pause im Lied): Matrix blendet dunkel (Wunsch 21.11.2026)

    def _load(self):
        if not self.path or not os.path.isfile(self.path):
            return ""
        try:
            with open(self.path, encoding="utf-8") as f:
                return check_host(json.load(f).get("ip", ""))
        except (OSError, ValueError, AttributeError):
            return ""

    def set_host(self, host):
        host = check_host(host)
        self.host = host
        self.reachable = None              # neue Adresse: gleich versuchen, die Pruefung folgt
        if self.sender is not None:
            self._blank()
            self.sender.close()
            self.sender = None
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"ip": host}, f)
            os.replace(tmp, self.path)
        return host

    def _blank(self, n=3):
        if self.sender is not None:
            data = bytes(self.fx.w * self.fx.h * 3)
            for _ in range(n):
                self.sender.send(data)

    def tick(self, s, cfg):
        """Ein Bild der Show: rechnen (nur wenn an oder die Vorschau offen ist) und senden (nur wenn an)."""
        on = cfg["pm_on"] > 0.5 and bool(self.host) and not self.dry and self.reachable is not False   # antwortet nicht: nichts senden
        want = on or s["t"] < self.preview_until
        if self.was_on and not on and self.reachable is not False:
            self._blank()
        self.was_on = on
        if not want:
            return
        w, h = int(cfg["pm_w"]), int(cfg["pm_h"])
        if (w, h) != (self.fx.w, self.fx.h):
            self.fx.resize(w, h)
        s["pattern"] = PATTERNS[int(cfg["pm_pattern"]) % len(PATTERNS)]
        frame = self.fx.render(s)
        frame = self._pictures(s, cfg, frame, w, h)
        if cfg["pm_lyrics"] > 0.5 or self.lyr.alpha > 0.02:     # Liedtext (Refrain) ueber Effekt und Bilder
            ok = (s.get("state") not in ("idle", "gap") and not s.get("override") and not s.get("frozen") and not s.get("dark")
                  and s["pattern"] != "test")
            frame = self.lyr.render(frame, s.get("lyric"), s, cfg["pm_lyrics"], ok)
        quiet = (s.get("state") in ("idle", "gap") and s["pattern"] != "test" and s.get("override") != "allbright"
                 and not s.get("frozen"))
        dt = s.get("dt", 0.025)
        self.quiet_k += (1 - math.exp(-dt / (0.8 if quiet else 0.15))) * ((0.0 if quiet else 1.0) - self.quiet_k)
        k = cfg["pm_loud"]                 # Huellkurve (21.11.2026): leise Stellen dunkler, laute ganz hell, schnell wie die Musik
        lv = s.get("loud", 1.0) if k > 0 else 1.0
        self.env += (1 - math.exp(-dt / (0.06 if lv > self.env else 0.35))) * (lv - self.env)
        if s.get("override") == "allbright":
            m = 1.0
        elif k > 0:
            m = s.get("master_raw", s.get("master", 1.0)) * (1.0 - k * (1.0 - LOUD_FLOOR) * (1.0 - self.env))
        else:
            m = s.get("master", 1.0)
        bright = cfg["pm_bright"] * m * self.quiet_k
        with self.lock:
            self.last = (np.clip(frame * bright, 0, 1) * 255 + 0.5).astype(np.uint8)
        if on:
            if self.sender is None:
                self.sender = DdpSender(self.host, self.port)
            self.sender.send(to_bytes(frame, bright, cfg["pm_rot"], cfg["pm_serp"] > 0.5, cfg["pm_gamma"]))

    def _pictures(self, s, cfg, frame, w, h):
        """Bilder und Laufschrift zum Lied ueber den Effekt blenden (nicht beim Testbild, nicht bei BLACKOUT, FREEZE,
        ALLES HELL, Laser-Szene, Stille, Aufbau und Drop)."""
        pics_on = cfg["pm_pics"] > 0.5
        mode = int(cfg["pm_text"])
        song = s.get("song") if (pics_on or mode) and s["pattern"] != "test" else None
        key = None
        if song:
            key = (song.get("show") or "", song.get("title") or "", round(float(song.get("dur") or 0)), w, h, pics_on, bool(mode))
        self.pics.song(key, song, self.pictures if pics_on else None, w, h, s["t"], text_provider=self.song_text if mode else None)
        calm = (s.get("state") not in ("build", "drop", "idle", "gap") and not s.get("override") and not s.get("frozen") and not s.get("dark"))
        img, a = self.pics.play(s["t"], s, frame, cfg["pm_pic_s"], cfg["pm_pic_every"], calm, mode, cfg["pm_text_px"], (h, w))
        if img is None or a <= 0 or img.shape != frame.shape:
            return frame
        return frame * (1 - a) + img * a

    def set_reachable(self, ok):
        if ok is False and self.reachable is not False and self.sender is not None:
            self.sender.close()            # Geraet weg: Socket zu, beim naechsten Senden neu
            self.sender = None
        self.reachable = ok

    def info(self, cfg, now):
        """Fuer die Seite /matrix: Zustand und das letzte Bild (Base64, Zeile fuer Zeile RGB)."""
        self.preview_until = now + 3.0
        with self.lock:
            img = self.last
        return {"on": cfg["pm_on"] > 0.5, "ip": self.host, "dry": self.dry, "w": int(img.shape[1]), "h": int(img.shape[0]),
                "pattern": int(cfg["pm_pattern"]), "patterns": PATTERN_LABELS.split("|"),
                "pics": self.pics.status if cfg["pm_pics"] > 0.5 else "aus",
                "reach": self.reachable,
                "sent": self.sender.sent if self.sender else 0, "errors": self.sender.errors if self.sender else 0,
                "px": base64.b64encode(img.tobytes()).decode()}

    def close(self):
        if self.sender is not None:
            self._blank()
            self.sender.close()
            self.sender = None
