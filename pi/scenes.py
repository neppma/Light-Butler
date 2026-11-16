#!/usr/bin/env python3
"""
scenes.py - Szenen (Phase 4).

Eine Szene besteht aus:
  mix   = Licht-Mix (Muster ueber alle Lichter: pulse, grow, backforth/Scanner, sweep, in, out,
          switch, random, carousel, onoff, strobe, lightning, static)
  speed = slow | mid | fast (Beats pro Zyklus: 8 / 4 / 2), synchron zum erkannten Tempo (BPM)
  color = auto (Raumfarbe nach Stimmung), white, warm, uv, multi (bunt), rainbow, duo, austria
          oder ein Farbname (rot, orange, gelb, gruen, tuerkis, cyan, blau, violett, magenta, pink)
  move  = Bewegungsart fuer Vega und Docooler-Tilt (home, vertical, horizontal, circle, random,
          calm, sweep (Besen), fan (Schwimmer), duck (Ente)) mit mspeed (slow | mid | fast)
          Die 8 Bewegungsarten im Panel: Rechts-Links, Schwimmer, Ente, Stop, Zufall, Besen, Kreis, Rauf-Runter

Blackout und "Sonnenbrille" (alles hell) sind Overrides in show.py. Laser und Hazer werden
auch hier nie angesteuert (dmx.py sperrt sie).
"""
import json
import math
import os
import random
from dataclasses import dataclass, replace

CYCLE_BEATS = {"slow": 8.0, "mid": 4.0, "fast": 2.0}      # Licht-Mix: Beats pro Zyklus
MOVE_BEATS = {"slow": 16.0, "mid": 8.0, "fast": 4.0}      # Bewegung: Beats pro Zyklus
MOVE_RATE = {"slow": 12.0, "mid": 30.0, "fast": 60.0}     # Vega: DMX-Einheiten/s
BAR_AMP = {"slow": 10.0, "mid": 20.0, "fast": 30.0}       # Docooler-Tilt: Auslenkung
STEP_MIXES = ("scanner", "outwards", "inwards")             # Lauflicht Geraet fuer Geraet (gleiche Ein-/Abdimmzeiten)
SCAN_BEATS = {"slow": 1.0, "mid": 0.5, "fast": 0.25}      # Scanner: Beats pro Schritt von einem Geraet zum naechsten

COLORS = {"rot": 0.0, "orange": 0.07, "gelb": 0.15, "gruen": 0.33, "tuerkis": 0.46,
          "cyan": 0.52, "blau": 0.60, "violett": 0.75, "magenta": 0.88, "pink": 0.93}

MIXES = ["static", "pulse", "grow", "shrink", "backforth", "scanner", "rainbow", "disco", "ring", "stars", "outwards",
         "inwards", "sweep", "in", "out", "switch",
         "random", "carousel", "onoff", "strobe", "lightning"]
MOVES = ["auto", "home", "vertical", "horizontal", "circle", "random", "calm", "sweep", "fan", "duck"]


@dataclass
class Scene:
    name: str = "Eigene"
    mix: str = "static"
    speed: str = "mid"
    color: str = "auto"
    move: str = "home"
    mspeed: str = "mid"
    level: float = 1.0
    hz: float = 8.0               # Blitzrate bei Strobe-Mixen
    narrow: bool = False
    rate: float = 0.8             # random: Blitze pro Sekunde und Zone
    decay: float = 0.35           # random: Abklingzeit in s
    names: tuple = ()             # nur diese Fixtures (leer = alle) ...
    kinds: tuple = ()             # ... oder diese Zonenarten (bar, wash, fx, uv, barlight, amb, spot, preset)
    preset: int = 0               # Effektband-Preset (0 = nach Tempo waehlen)
    vega_pos: tuple = ()          # feste Vega-Position (u, v) im erlaubten Bereich
    special: str = ""             # blackout | auto | laser | aim:<ziel>
    mixbtn: str = ""              # zuletzt gedruckter Licht-Mix-Knopf (bleibt im Panel markiert)

    def copy(self, **kw):
        return replace(self, **kw)


def S(name, **kw):
    return Scene(name=name, **kw)


# Seiten der Szenen
PAGES = {
    1: [S("All off", special="blackout"), S("rot", color="rot"), S("grün", color="gruen"),
        S("blau", color="blau"), S("weiss", color="white"), S("UV", color="uv"),
        S("Austria", color="austria", preset=1),
        S("Super Chill", mix="pulse", speed="slow", level=0.55, move="calm", mspeed="slow"),
        S("Chill Colors", color="rainbow", move="calm", mspeed="slow", level=0.7),
        S("Switch It Up slow", mix="switch", speed="slow", color="duo", move="horizontal", mspeed="slow")],
    2: [S("Random Chill", mix="random", rate=0.25, decay=1.2, color="multi", level=0.8, move="calm", mspeed="slow"),
        S("Chill", mix="pulse", speed="slow", level=0.7, move="calm", mspeed="slow"),
        S("RESET - Auto Mode", special="auto"),
        S("Bank", special="aim:bank"),
        S("Tisch", special="aim:tisch"),
        S("Grow Slow", mix="grow", speed="slow", move="vertical", mspeed="slow"),
        S("Back And Forth Slow", mix="backforth", speed="slow", move="horizontal", mspeed="slow"),
        S("Sweep Slow", mix="sweep", speed="slow", move="sweep", mspeed="slow"),
        S("Laser", special="laser"),
        S("Tür", special="aim:tuer")],
    3: [S("QUIZ", color="warm", level=0.8),
        S("Bar", special="aim:bar"),
        S("Switch It Up Fast", mix="switch", speed="fast", color="duo", move="horizontal", mspeed="fast"),
        S("Random Mid", mix="random", rate=0.8, decay=0.35, color="multi", move="random", mspeed="mid"),
        S("Pulse Slow", mix="pulse", speed="slow", move="fan", mspeed="slow"),
        S("Grow Shrink", mix="shrink", speed="mid", move="vertical", mspeed="mid"),
        S("Grow Fast", mix="grow", speed="fast", move="vertical", mspeed="fast"),
        S("Back And Forth Fast", mix="backforth", speed="fast", move="horizontal", mspeed="fast"),
        S("Sweep Fast", mix="sweep", speed="fast", move="sweep", mspeed="fast"),
        S("On/Off Fast", mix="onoff", speed="fast", move="fan", mspeed="fast")],
    4: [S("Pulse Fast", mix="pulse", speed="fast", move="fan", mspeed="fast"),
        S("Random Crazy", mix="random", rate=3.0, decay=0.12, color="multi", move="random", mspeed="fast"),
        S("UV Strobe", mix="strobe", color="uv", hz=8, move="home"),
        S("statisch", color="auto", move="home"),
        S("bunt", color="multi", move="home"),
        S("Sweep Narrow", mix="sweep", speed="mid", narrow=True, move="sweep", mspeed="mid"),
        S("Strobe Color", mix="strobe", color="multi", hz=8, move="home", preset=32),
        S("Strobe White", mix="strobe", color="white", hz=8, move="home", preset=32),
        S("All on Gewitter", mix="lightning", color="white", move="home", preset=8),
        S("All On", color="auto", move="home")],
}
SCENES = {s.name: s for page in PAGES.values() for s in page}


# ---- Eigene Szenenliste (Reihenfolge, Namen, Eigenschaften) -------------------------------------------
SCENE_FIELDS = ("name", "mix", "speed", "color", "move", "mspeed", "level", "hz", "narrow", "rate", "decay",
                "names", "kinds", "preset", "vega_pos", "special")
SPEEDS = [("slow", "Langsam"), ("mid", "Mittel"), ("fast", "Schnell")]
MIX_LABELS = [("static", "Statisch (dauerhaft an)"), ("pulse", "Pulsieren"), ("grow", "Wachsen (von der Mitte)"),
              ("shrink", "Wachsen und Schrumpfen"), ("backforth", "Hin und Her"), ("scanner", "Scanner (ein Geraet nach dem anderen)"),
              ("rainbow", "Regenbogen (eigene Farben)"), ("disco", "Discokugel"), ("ring", "Karussell"),
              ("stars", "Sternenhimmel"), ("outwards", "Nach aussen"), ("inwards", "Nach innen"),
              ("sweep", "Sweep (Lauflicht im Kreis)"), ("switch", "Switch (Bloecke wechseln)"),
              ("random", "Zufall (Blitze)"), ("onoff", "An/Aus"), ("strobe", "Strobo"), ("lightning", "Gewitter"),
              ("in", "Einwaerts (klassisch)"), ("out", "Auswaerts (klassisch)"), ("carousel", "Karussell (klassisch)")]
COLOR_LABELS = [("auto", "Auto (nach Stimmung)"), ("white", "Weiss"), ("warm", "Warmweiss"), ("uv", "UV"), ("multi", "Bunt"),
                ("rainbow", "Regenbogen"), ("duo", "Duo (zwei Farben)"), ("austria", "Austria (rot-weiss)"), ("rot", "Rot"),
                ("orange", "Orange"), ("gelb", "Gelb"), ("gruen", "Gruen"), ("tuerkis", "Tuerkis"), ("cyan", "Cyan"),
                ("blau", "Blau"), ("violett", "Violett"), ("magenta", "Magenta"), ("pink", "Pink")]
MOVE_LABELS = [("auto", "Musik (wie im Auto-Modus)"), ("home", "Stop (Mitte)"), ("horizontal", "Rechts-Links"),
               ("vertical", "Rauf-Runter"), ("circle", "Kreis"), ("random", "Zufall"), ("sweep", "Besen"),
               ("fan", "Schwimmer (Arme auseinander)"), ("duck", "Ente (Arme parallel)"), ("calm", "Ruhig")]
KIND_LABELS = [("bar", "Docooler"), ("wash", "Washes (4in1)"), ("barlight", "PAR Barlicht"),
               ("fx", "Effektgeraete (Eyes, Derby)"), ("uv", "UV-Leiste"), ("amb", "Ambiente (Theke, Couchtisch)"),
               ("spot", "Vega"), ("preset", "Effektband"), ("nano", "Nanoleaf Panels")]


def default_scenes():
    return [s.copy() for page in PAGES.values() for s in page]


def scene_to_dict(s):
    d = {k: getattr(s, k) for k in SCENE_FIELDS}
    for k in ("names", "kinds", "vega_pos"):
        d[k] = list(d[k])
    return d


OLD_NAMES = {"KITT": "Scanner", "kitt": "scanner"}       # bis 15.11.2026 hiess der Scanner so (gespeicherte Dateien)


def renamed(v):
    """Alten Namen aus gespeicherten Dateien (midimap.json, lumimap.json, scenes.json, fine.json, texts.json) uebersetzen."""
    return OLD_NAMES.get(v, v) if isinstance(v, str) else v


def renamed_action(a):
    """Aktion einer Taste ({"mix": ...}) mit neuem Namen."""
    return {k: (renamed(v) if k in ("mix", "mixbtn") else v) for k, v in a.items()} if isinstance(a, dict) else a


def scene_from_dict(d, base=None):
    """Prueft und uebernimmt Eigenschaften einer Szene (aus dem Panel oder aus scenes.json)."""
    s = (base or Scene()).copy()
    d = renamed_action(d)
    if "name" in d:
        name = str(d["name"]).strip()[:32]
        if not name:
            raise ValueError("Der Name darf nicht leer sein")
        s.name = name
    enums = {"mix": [k for k, _ in MIX_LABELS], "speed": [k for k, _ in SPEEDS], "mspeed": [k for k, _ in SPEEDS],
             "move": [k for k, _ in MOVE_LABELS], "color": [k for k, _ in COLOR_LABELS]}
    for k, allowed in enums.items():
        if k in d:
            if d[k] not in allowed:
                raise ValueError(f"Ungueltiger Wert fuer {k}: {d[k]}")
            setattr(s, k, d[k])
    for k, lo, hi in (("level", 0.05, 1.0), ("hz", 2.0, 12.0), ("rate", 0.05, 10.0), ("decay", 0.03, 3.0)):
        if k in d:
            setattr(s, k, max(lo, min(hi, float(d[k]))))
    if "narrow" in d:
        s.narrow = bool(d["narrow"])
    if "preset" in d:
        s.preset = max(0, min(99, int(d["preset"])))
    if "kinds" in d:
        allowed = [k for k, _ in KIND_LABELS]
        kinds = tuple(k for k in d["kinds"] if k in allowed)
        s.kinds = () if len(kinds) in (0, len(allowed)) else kinds        # alle oder keine = alle Lichter
    if "names" in d:
        s.names = tuple(str(x) for x in d["names"])
    if "vega_pos" in d:
        vp = tuple(float(x) for x in d["vega_pos"])
        s.vega_pos = vp if len(vp) == 2 else ()
    if "special" in d:
        s.special = str(d["special"])
    return s


def load_scenes(path):
    """Gespeicherte Szenenliste laden; ohne Datei (oder bei Fehlern) die Standard-Szenen."""
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            out, seen = [], set()
            for item in data["scenes"]:
                s = scene_from_dict(item)
                if s.name not in seen:
                    seen.add(s.name)
                    out.append(s)
            if out:
                return out
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return default_scenes()


def save_scenes(path, scenes):
    if not path:
        return
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "scenes": [scene_to_dict(s) for s in scenes]}, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass

# "Licht-Mix"-Knoepfe des Panels
# Die 8 Licht-Mix-Knoepfe. Ein Knopf aendert NUR das Muster (Bewegung und Tempo bleiben, wie sie sind);
# Regenbogen ist die einzige Ausnahme: er bringt seine eigenen Farben mit.
MIX_BUTTONS = {
    "Scanner": dict(mix="scanner"), "Regenbogen": dict(mix="rainbow"), "Discokugel": dict(mix="disco"),
    "Karussell": dict(mix="ring"), "Sternenhimmel": dict(mix="stars"), "STOP": dict(mix="static"),
    "nach aussen": dict(mix="outwards"), "nach innen": dict(mix="inwards"),
}
DISCO_RATE = {"slow": 4.0, "mid": 8.0, "fast": 14.0}     # Lichtpunkte pro Sekunde (ueber alle Geraete)
STAR_RATE = {"slow": 2.0, "mid": 3.5, "fast": 6.0}       # neue Sterne pro Sekunde (ueber alle Geraete)


def tri(p):
    p %= 1.0
    return 2 * p if p < 0.5 else 2 * (1 - p)


def saw(p):
    return p % 1.0


def gauss(d, w):
    return math.exp(-(d / w) ** 2)


def fine_speed(pct):
    """Feinregler Speed: 50 % = 1, 0 % = halb so schnell, 100 % = doppelt so schnell."""
    return 2.0 ** ((float(pct) - 50.0) / 50.0)


class Z:
    __slots__ = ("fx", "zi", "kind", "x", "idx", "key")

    def __init__(self, fx, zi, kind, x, idx):
        self.fx, self.zi, self.kind, self.x, self.idx = fx, zi, kind, x, idx
        self.key = f"sc_{fx.name}_{zi}"


class SceneEngine:
    def __init__(self, show):
        self.rng = random.Random(7)
        self.beatpos = 0.0
        self.env = {}
        self.lt_next = 0.0
        self.lt_events = []
        self.zones = []

        def spread(items, kind, lo=0.0, hi=1.0):
            n = len(items)
            for i, (fx, zi) in enumerate(items):
                x = (lo + hi) / 2 if n == 1 else lo + (hi - lo) * i / (n - 1)
                self.zones.append(Z(fx, zi, kind, x, len(self.zones)))
        spread(show.bars, "bar")
        spread(show.wash, "wash")
        spread([(f, i) for f in show.fxs for i in range(len(f.zones()))], "fx", 0.2, 0.8)
        spread([(f, i) for f in show.uv for i in range(len(f.zones()))], "uv")
        spread(show.barlight, "barlight", 0.5, 0.5)
        spread([(f, 0) for f in show.rgb_amb], "amb", 0.3, 0.7)
        for fx, zi in show.nano:                              # Nanoleaf: Position aus der Lage der Panels
            self.zones.append(Z(fx, zi, "nano", fx.extra.get("x", 0.5), len(self.zones)))
        self.spot = show.spot
        self.presets = show.presets
        # Scanner: ein Lauflicht ueber alle Geraete (Docooler, Washes, Vega, FX, PAR, UV) in der Reihenfolge der
        # DMX-Adressen: vom ersten zum letzten und wieder zurueck. Ambiente und Effektband machen nicht mit.
        devs = {}
        for z in self.zones:
            if z.kind not in ("amb", "uv", "nano"):
                devs[z.fx.name] = z.fx
        for fx in show.spot:
            devs[fx.name] = fx
        order = sorted(devs.values(), key=lambda f: f.address)
        self.scan_idx = {f.name: i for i, f in enumerate(order)}
        self.scan_n = max(2, len(order))
        self.scan_pos, self.scan_rel = 0, 0.2
        self.chase_ring = 0                   # Chase-Out/-In: welches Paar gerade leuchtet (0 = Mitte)
        self.zone_n = max(1, len(self.zones))
        self.mxf = None                       # Feinregler des Licht-Mix (speed, shift, size), nur bei gewaehltem Knopf
        self._ph = {}                         # Phasen mit Feinregler-Tempo: Name -> (Faktor, Versatz)

    def _scaled(self, name, f, base):
        """Phase base * f, ohne Sprung beim Verstellen des Reglers (der Versatz gleicht die Aenderung aus)."""
        of, off = self._ph.get(name, (1.0, 0.0))
        if f != of:
            off = base * of + off - base * f
            self._ph[name] = (f, off)
        return base * f + off

    # ---- Muster ----------------------------------------------------------------------
    def _xf(self, z):
        """Position des Geraets im Gesamtaufbau (0..1, nach DMX-Adresse, wie bei Scanner)."""
        i = self.scan_idx.get(z.fx.name)
        return i / (self.scan_n - 1) if i is not None else z.x

    def rainbow_hue(self, name, fallback=0.5):
        i = self.scan_idx.get(name)
        xf = i / (self.scan_n - 1) if i is not None else fallback
        return (xf * 0.9 + self.beatpos / (CYCLE_BEATS["mid"] * 4.0)) % 1.0

    def mix_value(self, sc, z, ph, now, dt, on_strobe, lt):
        m, x = sc.mix, z.x
        w = 0.07 if sc.narrow else 0.16
        sz = 1.0
        if self.mxf is not None:              # Feinregler: Versatz pro Geraet (Welle) und Breite
            ph += self.mxf[1] * self._xf(z)
            sz = self.mxf[2]
            w *= sz
        if m == "static":
            return 1.0
        if m == "pulse":
            return (0.5 - 0.5 * math.cos(2 * math.pi * ph)) ** 1.5
        if m == "grow":
            return 1.0 if abs(x - 0.5) * 2 <= saw(ph) else 0.0
        if m == "shrink":
            return 1.0 if abs(x - 0.5) * 2 <= tri(ph) else 0.0
        if m == "backforth":
            return gauss(x - tri(ph), w)
        if m == "scanner":                       # immer nur ein Geraet an, das vorherige dimmt gerade herunter
            if z.kind == "nano":              # Panels: Lichtpunkt wandert mit, nach der Lage der Panels
                return gauss(z.x - self.scan_pos / max(1, self.scan_n - 1), 0.14 * sz)
            k = self.scan_idx.get(z.fx.name)
            return 1.0 if (k is not None and k == self.scan_pos and z.kind not in ("amb", "uv")) else 0.0
        if m == "rainbow":                    # alle an, jedes Geraet in einer anderen Farbe (siehe color())
            return 1.0
        if m == "ring":                       # Karussell: ein weicher Lichtbereich kreist ueber alle Geraete
            return (0.5 + 0.5 * math.cos(2 * math.pi * (self._xf(z) - saw(ph / 2.0)))) ** (6 / sz ** 2)
        if m in ("outwards", "inwards"):      # Chase-Out/-In: wie Scanner Geraet fuer Geraet, paarweise von der Mitte nach aussen
            rings = (self.scan_n + 1) // 2    # (bzw. von aussen zur Mitte); immer nur ein Paar an
            if z.kind == "nano":              # Panels: Lichtpunkt wandert mit, nach der Lage der Panels
                return gauss(abs(z.x - 0.5) - (self.chase_ring + 0.5) / rings * 0.5, 0.1 * sz)
            k = self.scan_idx.get(z.fx.name)
            return 1.0 if (k is not None and z.kind not in ("amb", "uv")
                           and int(abs(k - (self.scan_n - 1) / 2.0)) == self.chase_ring) else 0.0
        if m in ("disco", "stars"):           # Zufallspunkte: Disco = kurz und schnell, Sterne = selten und weich
            rate, decay = ((DISCO_RATE[sc.speed], 0.1) if m == "disco" else (STAR_RATE[sc.speed], 1.2))
            if self.mxf is not None:
                rate, decay = rate * self.mxf[0], decay * self.mxf[3]
            e = self.env.get(z.key, 0.0) * math.exp(-dt / decay)
            if self.rng.random() < rate / self.zone_n * dt:
                e = 1.0
            self.env[z.key] = e
            return e
        if m == "sweep":
            p = saw(ph)
            d = min(abs(x - p), 1 - abs(x - p))
            return gauss(d, w * (0.7 if sc.narrow else 1.0))
        if m == "in":
            q = saw(ph) * 0.5
            return max(gauss(x - q, w), gauss(x - (1 - q), w))
        if m == "out":
            q = saw(ph) * 0.5
            return max(gauss(x - (0.5 - q), w), gauss(x - (0.5 + q), w))
        if m == "switch":
            return 1.0 if (int(x * 4.999) + int(ph * 2)) % 2 == 0 else 0.0
        if m == "carousel":
            return (0.5 + 0.5 * math.cos(2 * math.pi * (x * 2 - saw(ph)))) ** (2 / sz ** 2)
        if m == "onoff":
            return 1.0 if (ph % 1.0) < 0.5 else 0.0
        if m == "strobe":
            return 1.0 if on_strobe else 0.0
        if m == "lightning":
            return lt
        if m == "random":
            e = self.env.get(z.key, 0.0) * math.exp(-dt / max(0.03, sc.decay))
            if self.rng.random() < sc.rate * dt:
                e = 1.0
            self.env[z.key] = e
            return e
        return 1.0

    def lightning(self, now, strobe_ok):
        if now >= self.lt_next:
            n = self.rng.randint(2, 5) if strobe_ok else 1
            t, self.lt_events = now, []
            for _ in range(n):
                self.lt_events.append((t, t + 0.06))
                t += 0.06 + self.rng.uniform(0.05, 0.15)
            self.lt_next = t + self.rng.uniform(1.5, 6.0)
        return 1.0 if any(a <= now < b for a, b in self.lt_events) else 0.0

    # ---- Farben --------------------------------------------------------------------------
    @staticmethod
    def _has_w(z):
        zs = z.fx.zones()
        return bool(zs) and z.zi < len(zs) and "w" in zs[z.zi]

    def color(self, show, sc, z):
        from show import hsv
        if sc.mix == "rainbow":
            return (*hsv(self.rainbow_hue(z.fx.name, z.x), 1.0, 1.0), 0.0, 0.5)
        c = sc.color
        if c in ("auto", "room"):
            return (*hsv(show.hue, 1.0, 1.0), 0.0, 0.5)
        if c == "white":                    # Geraete mit echten Weiss-LEDs (Docooler): nur Weiss, kein RGB
            return (0.0, 0.0, 0.0, 1.0, 0.0) if self._has_w(z) else (1.0, 1.0, 1.0, 1.0, 0.0)
        if c == "warm":
            return (1.0, 0.55, 0.2, 0.3, 0.0)
        if c == "uv":
            return (0.0, 0.0, 0.0, 0.0, 1.0)
        if c == "multi":
            return (*hsv(z.x * 0.85, 1.0, 1.0), 0.0, 0.6)
        if c == "rainbow":
            return (*hsv(z.x * 0.25 + self.beatpos / 48.0, 1.0, 1.0), 0.0, 0.5)
        if c == "duo":
            return (*hsv(show.hue + (0.5 if z.idx % 2 else 0.0), 1.0, 1.0), 0.0, 0.5)
        if c == "austria":
            red = z.x < 0.33 or z.x > 0.66
            if red:
                return (1.0, 0.0, 0.0, 0.0, 0.0)
            return (0.0, 0.0, 0.0, 1.0, 0.0) if self._has_w(z) else (1.0, 1.0, 1.0, 1.0, 0.0)
        return (*hsv(COLORS.get(c, show.hue), 1.0, 1.0), 0.0, 0.5)

    # ---- Rendern ---------------------------------------------------------------------------
    def allowed(self, sc, z):
        if not sc.names and not sc.kinds:
            return True
        return z.fx.name in sc.names or z.kind in sc.kinds

    def render(self, show, now, dt, sc):
        from show import clamp01
        bpm = show.manual_bpm or (show.bpm if show.bpm > 0 else 120.0)
        self.beatpos += dt * bpm / 60.0
        bscale = getattr(show, "bar_len", 4) / 4.0                     # 3/4: alle Zyklen im Dreier-Raster (3 statt 4 Beats)
        mb, fade = self.beatpos, 1.0
        self.mxf = None
        fv = show.fine.get("mx", sc.mixbtn) if sc.mixbtn and getattr(show, "fine", None) else None
        if fv:                                # Licht-Mix per Knopf gewaehlt: Feinregler Fade, Speed, Shift, Size dieses Knopfes
            sp = fine_speed(fv["speed"])
            fade = 4.0 ** ((fv["fade"] - 50.0) / 50.0)
            self.mxf = (sp, (fv["shift"] - 50.0) / 50.0, 2.0 ** ((fv["size"] - 50.0) / 50.0), fade)
            mb = self._scaled("mix", sp, self.beatpos)
        ph = mb / (CYCLE_BEATS[sc.speed] * bscale)
        hz = max(2.0, min(12.0, sc.hz)) if show.strobe else min(3.0, sc.hz)
        on_strobe = ((now * hz) % 1.0) < 0.5
        lt = self.lightning(now, show.strobe) if sc.mix == "lightning" else 0.0
        hard = sc.mix in ("switch", "onoff", "grow", "shrink", "strobe", "lightning")
        total, count = 0.0, 0
        if sc.mix == "scanner":                  # Position im Hin-und-Zurueck: 0,1,..,n-1,n-2,..,1 (am Ende Richtungswechsel)
            n = self.scan_n
            steps = 2 * (n - 1)
            idx = int(mb / SCAN_BEATS[sc.speed]) % steps
            self.scan_pos = idx if idx < n else steps - idx
            step_t = SCAN_BEATS[sc.speed] * 60.0 / bpm
            if self.mxf is not None:
                step_t /= self.mxf[0]
            self.scan_rel = max(0.06, min(0.45, 0.9 * step_t))     # Abdimmzeit: Vorgaenger leuchtet noch kurz nach
        elif sc.mix in ("outwards", "inwards"):     # Chase: ein Schritt je Paar im Scanner-Tempo, immer in dieselbe Richtung
            rings = (self.scan_n + 1) // 2
            idx = int(mb / SCAN_BEATS[sc.speed]) % rings
            self.chase_ring = idx if sc.mix == "outwards" else rings - 1 - idx
            step_t = SCAN_BEATS[sc.speed] * 60.0 / bpm
            if self.mxf is not None:
                step_t /= self.mxf[0]
            self.scan_rel = max(0.06, min(0.45, 0.9 * step_t))
        for z in self.zones:
            fx = z.fx
            if not self.allowed(sc, z):
                if z.kind == "amb":
                    fx.set_color(0, 0, 0)
                else:
                    self._off(fx, z.zi)
                continue
            raw = self.mix_value(sc, z, ph, now, dt, on_strobe, lt) * sc.level
            fast = hard or sc.mix in ("random", "disco")
            attack = 0.005 if fast else 0.03 if sc.mix in STEP_MIXES else 0.3 if sc.mix == "stars" else 0.02
            release = 0.03 if sc.mix in ("strobe", "lightning") else (0.08 if hard else self.scan_rel if sc.mix in STEP_MIXES else 0.1)
            if self.mxf is not None:
                attack, release = attack * fade, release * fade
            i = show.smooth(z.key, raw, dt, release=release, attack=attack)
            total, count = total + i, count + 1
            r, g, b, w, uvf = self.color(show, sc, z)
            if z.kind == "amb":
                fx.set_color(*[255 * clamp01(c * i) * show.master for c in (r, g, b)])
                fx.set("dimmer", 255)
                continue
            if z.kind == "uv":
                uvv = i * (1.0 if sc.color in ("uv", "multi", "rainbow") else 0.5 if sc.color in ("auto", "room", "duo") or sc.mix == "rainbow" else 0.0)
                show.paint(fx, z.zi, 0, 0, 0, uv=uvv)
            elif z.kind == "nano" and sc.color == "uv":          # UV-Szene: Panels dunkel, sonst stoert ihr Blau das UV-Licht
                show.paint(fx, z.zi, 0, 0, 0)
            else:
                uvq = i * (1.0 if sc.color == "uv" else 0.0)
                show.paint(fx, z.zi, r * i, g * i, b * i, w=w * i, uv=uvq)
            if "strobe" in fx.map:
                fx.set("strobe", 0)
        mean_i = total / count if count else 0.0
        # Vega
        for fx in self.spot:
            on = (not sc.names and not sc.kinds) or fx.name in sc.names or "spot" in sc.kinds or bool(sc.vega_pos)
            if not on or sc.color == "uv":
                fx.set("dimmer", 0)
            else:
                v = show.smooth("sc_vega", (self.mix_value(sc, Z(fx, 0, "spot", 0.5, 99), ph, now, dt, on_strobe, lt)
                                           * sc.level), dt, release=(self.scan_rel if sc.mix in STEP_MIXES else 0.1) * fade, attack=0.01 * fade)
                fx.set("dimmer", 255 * (clamp01(v) ** show.gamma) * show.master)
                fx.set("shutter", 255)
                if sc.mix == "rainbow":
                    wheel = show.wheel_name(self.rainbow_hue(fx.name))
                elif sc.color in ("white", "warm"):
                    wheel = "white"
                else:
                    wheel = show.wheel_name(show.hue if sc.color in ("auto", "room", "duo", "rainbow", "multi")
                                            else COLORS.get(sc.color, show.hue))
                fx.preset("colorwheel", wheel)
                fx.preset("gobo", "open")
                fx.set("gobo_rot", 0)
        # Effektband
        for fx in self.presets:
            on = (not sc.names and not sc.kinds) or fx.name in sc.names or "preset" in sc.kinds
            if not on or sc.color == "uv" or sc.mix in ("outwards", "inwards"):   # Chase-Out/-In: Effektband aus
                fx.set("dimmer", 0)
                continue
            roles = show.eb_roles(fx) if hasattr(show, "eb_roles") else fx.extra.get("preset_roles", {})
            pid = sc.preset or {"rot": 31, "blau": 29, "gruen": 34, "white": 35, "multi": 13, "rainbow": 13}.get(sc.color, 0)
            if sc.mix == "rainbow" and not sc.preset:
                pid = 13                                           # Effektband: Regenbogen
            if sc.mixbtn and not sc.preset and fx.extra.get("preset_mix", {}).get(sc.mixbtn):
                pid = fx.extra["preset_mix"][sc.mixbtn]            # Licht-Mix-Knopf mit eigenem Preset (Sparkle, Karussell, Disco, Scanner)
            man = show._eb_manual() if hasattr(show, "_eb_manual") else None
            if man:
                pid = man                                          # Effektband von Hand gewaehlt (Panel)
            if pid == 32 and not show.strobe:
                pid = 5
            if pid == 8 and not show.strobe:
                pid = 5
            if hasattr(show, "eb_no_sound") and pid != man:
                pid = show.eb_no_sound(fx, pid)                    # Effektband ohne Ton: kein soundgesteuertes Preset
            if not pid:
                own = set(fx.extra.get("preset_scene_skip", []))       # Sparkle/Karussell/Disco gehoeren zu ihren Knoepfen,
                lst = [p for p in roles.get({"slow": "calm", "mid": "warm", "fast": "party"}[sc.speed], [])
                       if p not in own] or [0]                    # feste Szenen waehlen wie bisher
                pid = lst[hash(sc.name) % len(lst)]
            fx.set("preset", pid)
            fx.set("dimmer", 255 * show.master * max(0.35, min(1.0, 0.35 + mean_i)))
        self.motion(show, now, sc)

    def _off(self, fx, zi):
        z = fx.zones()
        if z:
            fx.set_zone(zi, r=0, g=0, b=0, w=0, uv=0)

    # ---- Bewegung ---------------------------------------------------------------------------
    def motion(self, show, now, sc):
        if sc.move == "auto" and not sc.vega_pos:       # keine eigene Bewegung gewaehlt: weiter wie im Auto-Modus
            show.mo = None
            return
        # Bewegung per Knopf gewaehlt: Feinregler Fan, Speed, Shift, Size dieses Knopfes (Center hat keine)
        c = show.fine.get("mv", sc.move) if sc.name == "Eigene" and getattr(show, "fine", None) else None
        fine = c is not None
        mb, tnow, sp = self.beatpos, now, 1.0
        if fine:
            sp = fine_speed(c["speed"])
            mb, tnow = self._scaled("move", sp, self.beatpos), self._scaled("move_t", sp, now)
        mph = mb / (MOVE_BEATS[sc.mspeed] * getattr(show, "bar_len", 4) / 4.0)
        mode = sc.move
        u, v = 0.5, 0.5
        s = math.sin(2 * math.pi * mph)
        if sc.vega_pos:
            u, v = sc.vega_pos
        elif mode == "vertical":
            v = 0.5 + 0.45 * s
        elif mode == "horizontal":
            u = 0.5 + 0.45 * s
        elif mode == "circle":
            u, v = 0.5 + 0.4 * math.cos(2 * math.pi * mph), 0.5 + 0.4 * s
        elif mode == "random":
            r = random.Random(int(mph * 1.0) + 11)
            u, v = 0.1 + 0.8 * r.random(), 0.1 + 0.8 * r.random()
        elif mode == "calm":
            u = 0.5 + 0.38 * math.sin(2 * math.pi * tnow / 24.0)
            v = 0.5 + 0.33 * math.sin(2 * math.pi * tnow / 17.0 + 1.0)
        elif mode == "sweep":
            u, v = 0.05 + 0.9 * tri(mph), 0.3
        elif mode == "duck":                       # Ente (Float): Arme parallel, Vega schwenkt mit und schwebt leicht
            u = 0.5 + 0.4 * s                      # auf und ab (liegende Acht: zweimal auf und ab je Schwenk)
            v = 0.5 + 0.12 * math.sin(4 * math.pi * mph)
        fan = {"home": 0.0, "calm": 5.0, "duck": 0.0}.get(mode, BAR_AMP[sc.mspeed])
        sway = BAR_AMP[sc.mspeed] * 0.6 if mode in ("horizontal", "sweep", "circle") else 0.0
        if mode == "duck":
            sway = BAR_AMP[sc.mspeed] * 1.2
        if mode == "vertical" and sc.name == "Eigene":  # Tilt-Knopf: die Docooler koennen nur seitwaerts, sie bleiben stehen
            fan = sway = 0.0
        rate, bar_rate = MOVE_RATE[sc.mspeed], 255.0 if sc.mspeed == "fast" else 120.0
        if fine:
            size = c["size"] / 50.0
            if not sc.vega_pos:
                u, v = 0.5 + (u - 0.5) * size, 0.5 + (v - 0.5) * size
            fan, sway = fan * c["fan"] / 50.0, sway * size
            rate, bar_rate = rate * sp, min(255.0, bar_rate * sp)
        show.mo = {"u": max(0.0, min(1.0, u)), "v": max(0.0, min(1.0, v)),
                   "rate": rate, "fan_amp": fan, "fan_phase": 2 * math.pi * mph,
                   "sway_amp": sway, "bar_rate": bar_rate,
                   "sway_sin": mode == "duck"}
        if fine:                              # Shift: Versatz der Arme gegeneinander (0 = wie bisher)
            show.mo["shift"] = (c["shift"] - 50.0) / 50.0 * math.pi / 2
