#!/usr/bin/env python3
"""
patterns.py - Pattern-Generator: fertige Lichtmuster.

Jedes Muster ist eine reine Funktion der Zeit, ohne Zustand: Dasselbe Bild kommt heraus, egal ob die Show hierher gespielt
oder gesprungen ist. Auch die Zufallsmuster wuerfeln deshalb aus Clip-Kennung und Schrittnummer.

Drei Arten von Ergebnis (`out`):
  scalar   Wert 0..255 fuer Dimmer und jeden einfachen Kanal (Formfaktor 0..1 zwischen Anfangs- und Endwert)
  color    Farbe (r, g, b, w, uv), je 0..255
  move     Position (u, v), je 0..1 im erlaubten Bereich des Geraets

Dazu zwei besondere Arten: laser (an/aus, Muster, Farbe, Tempo; wirkt nur ueber engine._laser) und fog (Nebelschub, kein Wert,
ausgeloest ueber Show._fog_cue).

Strobe: nur mit Strobe-Erlaubnis schneller als 2 Blitze pro Sekunde. Die harte Grenze fuer alle Muster und Keyframes steht in
engine.FlashLimiter, hier wird nur schon die Rate begrenzt.
"""
import math

FRAME_HZ = 40.0
STROBE_NO_PERMISSION_HZ = 2.0

# Parameter fuer das Panel: Schluessel -> (Titel, Standard, min, max, Schritt, Einheit)
PARAMS = {
    "panel_scene": ("Szene aus dem Panel", "", None, None, None, "text"),
    "nano_effect": ("Effekt", "", None, None, None, "text"),   # Name auf dem Geraet, die Auswahl fuellt das Panel
    "speed": ("Geschwindigkeit", 1.0, 0.01, 20.0, 0.01, "Hz"),
    "intensity": ("Intensität", 1.0, 0.0, 1.0, 0.01, ""),
    "start": ("Anfangswert", 0, 0, 255, 1, ""),
    "end": ("Endwert", 255, 0, 255, 1, ""),
    "fade_in": ("Fade In: langsam einblenden", 0.0, 0.0, 600.0, 0.05, "s"),
    "fade_out": ("Fade Out: langsam ausblenden", 0.0, 0.0, 600.0, 0.05, "s"),
    "repeat": ("Wiederholungen (0 = nach Geschwindigkeit)", 0, 0, 10000, 1, ""),
    "spread": ("Versatz je Gerät (1 = gleichmäßig verteilt)", 0.0, -4.0, 4.0, 0.01, ""),
    "beat_sync": ("Im Takt (Geschwindigkeit = Zyklen je Beat)", 0, 0, 1, 1, "bool"),
    "duty": ("Einschaltanteil", 0.5, 0.05, 0.95, 0.01, ""),
    "width": ("Breite (Geräte)", 1.0, 0.25, 16.0, 0.25, ""),
    "size": ("Größe", 1.0, 0.0, 1.0, 0.01, ""),
    "center_u": ("Mitte links/rechts", 0.5, 0.0, 1.0, 0.01, ""),
    "center_v": ("Mitte oben/unten", 0.5, 0.0, 1.0, 0.01, ""),
    "color_a": ("Farbe A", "#ff0000", None, None, None, "color"),
    "color_b": ("Farbe B", "#0000ff", None, None, None, "color"),
    "saturation": ("Sättigung", 1.0, 0.0, 1.0, 0.01, ""),
    "smooth": ("Weicher Übergang", 0.0, 0.0, 1.0, 0.01, ""),
    "laser_pulse": ("Pulse je Beat (0 = durchgehend)", 0.0, 0.0, 4.0, 0.25, ""),
    "laser_pattern": ("Muster (Derby)", 0, 0, 15, 1, ""),
    "ktv_group": ("KTV: Gruppe", "1", None, None, None, "select"),
    "ktv_effect": ("KTV: Muster", 3, 0, 42, 1, ""),
    "ktv_size": ("KTV: Zoom (Kanal 6, 0 = groß, 255 = klein)", 128, 0, 255, 1, ""),
    "ktv_size_to": ("KTV: Zoom bis", 128, 0, 255, 1, ""),
    "ktv_zoom": ("KTV: Zoom-Automatik (Kanal 7, 128–159 größer, 160–191 kleiner, ab 192 pendeln)", 0, 0, 255, 1, ""),
    "ktv_rotate": ("KTV: Drehung (0–127 Winkel, 128–191 rückwärts, ab 192 vorwärts)", 0, 0, 255, 1, ""),
    "ktv_rotate_to": ("KTV: Drehung bis", 0, 0, 255, 1, ""),
    "ktv_pos_x": ("KTV: Position links/rechts (1–127, ab 128 bewegen)", 0, 0, 255, 1, ""),
    "ktv_pos_x_to": ("KTV: Position links/rechts bis", 0, 0, 255, 1, ""),
    "ktv_pos_y": ("KTV: Position oben/unten (1–127, ab 128 bewegen)", 0, 0, 255, 1, ""),
    "ktv_pos_y_to": ("KTV: Position oben/unten bis", 0, 0, 255, 1, ""),
    "ktv_wave": ("KTV: Welle", 0, 0, 255, 1, ""),
    "ktv_fan": ("KTV: Fächer (Kanal 14, vom Punkt zur breiten Linie)", 0, 0, 255, 1, ""),
    "ktv_fan_to": ("KTV: Fächer bis", 0, 0, 255, 1, ""),
    "ktv_sweep": ("KTV: Verlauf von → bis", "once", None, None, None, "select"),
    "ktv_sweep_n": ("KTV: Hin und her, wie oft im Clip", 1, 1, 64, 1, ""),
    "ktv_ease": ("KTV: Übergang", "linear", None, None, None, "select"),
    "ktv_fx": ("KTV: Effekt (Kanal 15, 0 = aus, gefallen haben 46 und 35)", 0, 0, 244, 1, ""),
    "laser_color": ("Farbe", "bunt", None, None, None, "select"),
    "laser_tempo": ("Tempo", 120, 0, 255, 1, ""),
}
SWEEP_PARAMS = ("ktv_size", "ktv_rotate", "ktv_pos_x", "ktv_pos_y", "ktv_fan")   # Werte mit Von und Bis
PARAM_OPTIONS = {"ktv_sweep": [["once", "Einmal über den ganzen Clip"], ["pingpong", "Hin und her"], ["beat", "Im Takt: je Beat"],
                               ["beat2", "Im Takt: je 2 Beats"], ["bar", "Im Takt: je Takt"], ["bar2", "Im Takt: je 2 Takte"]],
                 "ktv_ease": [["linear", "Linear"], ["ease_in", "Ease In"], ["ease_out", "Ease Out"], ["ease_in_out", "Ease In/Out"], ["constant", "Konstant"]],
                 "laser_color": [["bunt", "Bunt"], ["rot", "Rot"], ["gruen", "Grün"], ["blau", "Blau"]],
                 "ktv_group": [[str(i), f"Liniengruppe {i}"] for i in range(1, 7)] + [["anim", "Animationsgruppe"]]}
ALWAYS = ["intensity", "fade_in", "fade_out"]
RUN = ["speed", "repeat", "spread", "beat_sync"]


class Ctx:
    """Was ein Muster wissen darf. Wird pro Bild wiederverwendet, damit die Hauptschleife nichts anlegen muss."""
    __slots__ = ("u", "sec", "beat", "i", "n", "frame", "seed", "strobe")

    def __init__(self, u=0.0, sec=0.0, beat=0.0, i=0, n=1, frame=0, seed=0, strobe=False):
        self.u, self.sec, self.beat, self.i, self.n = u, sec, beat, i, n
        self.frame, self.seed, self.strobe = frame, seed, strobe


def rnd(seed, step, salt=0):
    """Fester Zufall 0..1 aus Kennung und Schritt (immer gleich beim Springen in der Show)."""
    x = (seed ^ (step * 0x9E3779B1) ^ (salt * 0x85EBCA6B)) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x2C1B3C6D) & 0xFFFFFFFF
    x ^= x >> 12
    x = (x * 0x297A2D39) & 0xFFFFFFFF
    x ^= x >> 15
    return x / 4294967296.0


def clip_seed(text):
    """Zahl aus der Kennung eines Clips (nicht Pythons hash(): der aendert sich mit jedem Programmstart)."""
    h = 2166136261
    for ch in str(text):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def cycles(p, c):
    """Wie viele Zyklen seit Clip-Beginn: nach Wiederholungen, im Takt oder nach Geschwindigkeit, plus Versatz je Geraet."""
    rep = p["repeat"]
    if rep > 0:
        x = rep * c.u
    elif p["beat_sync"]:
        x = c.beat * p["speed"]                  # auf den Takt der ganzen Show gerastet, nicht auf den Clip-Anfang
    else:
        x = c.sec * p["speed"]
    if p["spread"] and c.n > 1:
        x += p["spread"] * c.i / c.n
    return x


def _frac(x):
    return x - math.floor(x)


def hsv(h, s, v):
    h = _frac(h) * 6.0
    i = int(h)
    f = h - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i % 6]


def parse_color(c):
    """'#rrggbb' oder [r, g, b, w, uv] -> Tupel mit 5 Werten 0..255."""
    if isinstance(c, str):
        s = c.strip().lstrip("#")
        if len(s) != 6:
            raise ValueError(f"Farbe {c!r} ungueltig")
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 0, 0)
    v = [max(0.0, min(255.0, float(x))) for x in c][:5]
    return tuple(v + [0.0] * (5 - len(v)))


# ---- Form 0..1 (scalar) ----------------------------------------------------------------------------
def s_fade_in(p, c):
    return _frac(cycles(p, c)) if p["repeat"] > 0 else c.u


def s_fade_out(p, c):
    return 1.0 - (_frac(cycles(p, c)) if p["repeat"] > 0 else c.u)


def s_blink(p, c):
    return 1.0 if _frac(cycles(p, c)) < p["duty"] else 0.0


def s_pulse(p, c):
    x = _frac(cycles(p, c))
    return math.exp(-5.0 * x)                     # schnell hell, langsam abklingend


def s_sine(p, c):
    return 0.5 - 0.5 * math.cos(2 * math.pi * cycles(p, c))


def s_strobe(p, c):
    """Strobe nach Bildzaehler, damit jeder Zyklus gleich lang ist (wie Blitz im Panel)."""
    hz = p["speed"] if c.strobe else min(p["speed"], STROBE_NO_PERMISSION_HZ)
    period = max(2, 2 * int(round(FRAME_HZ / (2.0 * max(0.1, hz)))))
    return 1.0 if c.frame % period < max(1, int(period * p["duty"])) else 0.0


def s_chase(p, c):
    """Ein Geraet nach dem anderen, hart geschaltet."""
    pos = _frac(cycles(p, c)) * c.n
    d = (c.i - pos) % c.n
    return 1.0 if d < p["width"] else 0.0


def s_running(p, c):
    """Lauflicht mit weichem Schweif."""
    pos = _frac(cycles(p, c)) * c.n
    d = (pos - c.i) % c.n
    return max(0.0, 1.0 - d / max(0.25, p["width"]))


def s_beat(p, c):
    """Puls auf jeden Schlag des Beat-Rasters, unabhaengig vom Clip-Anfang."""
    x = _frac(c.beat * p["speed"])
    return math.exp(-6.0 * x)


# ---- Farben ----------------------------------------------------------------------------------------
def c_solid(p, c):
    """Eine feste Farbe, solange der Clip laeuft."""
    return parse_color(p["color_a"])


def c_change(p, c):
    """Harter oder weicher Wechsel zwischen zwei Farben."""
    x = _frac(cycles(p, c))
    a, b = parse_color(p["color_a"]), parse_color(p["color_b"])
    sm = p["smooth"]
    if sm <= 0:
        return a if x < 0.5 else b
    w = 0.5 - 0.5 * math.cos(2 * math.pi * x)
    w = min(1.0, max(0.0, (w - 0.5) / max(0.01, sm) + 0.5))
    return tuple(a[k] + (b[k] - a[k]) * w for k in range(5))


def c_fade(p, c):
    """RGB-Verlauf von Farbe A nach Farbe B ueber den Clip (oder je Wiederholung)."""
    x = _frac(cycles(p, c)) if p["repeat"] > 0 else c.u
    a, b = parse_color(p["color_a"]), parse_color(p["color_b"])
    return tuple(a[k] + (b[k] - a[k]) * x for k in range(5))


def c_rainbow(p, c):
    r, g, b = hsv(cycles(p, c), p["saturation"], 1.0)
    return (r * 255, g * 255, b * 255, 0.0, 0.0)


def c_random(p, c):
    x = cycles(p, c)
    step = int(math.floor(x))
    salt = c.i if p["spread"] else 0              # mit Versatz: jedes Geraet eigene Farbe
    r, g, b = hsv(rnd(c.seed, step, salt), p["saturation"], 1.0)
    return (r * 255, g * 255, b * 255, 0.0, 0.0)


# ---- Bewegung --------------------------------------------------------------------------------------
def _mv(p, du, dv):
    s = p["size"] * 0.5 * p["intensity"]
    return (max(0.0, min(1.0, p["center_u"] + du * s)), max(0.0, min(1.0, p["center_v"] + dv * s)))


def m_circle(p, c):
    a = 2 * math.pi * cycles(p, c)
    return _mv(p, math.cos(a), math.sin(a))


def m_eight(p, c):
    a = 2 * math.pi * cycles(p, c)
    return _mv(p, math.sin(a), math.sin(2 * a))


def m_sweep_lr(p, c):
    return _mv(p, math.sin(2 * math.pi * cycles(p, c)), 0.0)


def m_sweep_ud(p, c):
    return _mv(p, 0.0, math.sin(2 * math.pi * cycles(p, c)))


def m_sine(p, c):
    """Links-rechts mit langsamer Welle auf und ab."""
    a = 2 * math.pi * cycles(p, c)
    return _mv(p, math.sin(a), 0.5 * math.sin(3 * a))


def m_random(p, c):
    """Von Zufallspunkt zu Zufallspunkt, weich."""
    x = cycles(p, c)
    step = int(math.floor(x))
    w = _frac(x)
    w = w * w * (3 - 2 * w)
    salt = 1000 + c.i * 2 if p["spread"] else 1000
    pts = [(rnd(c.seed, s, salt) * 2 - 1, rnd(c.seed, s, salt + 1) * 2 - 1) for s in (step, step + 1)]
    return _mv(p, pts[0][0] + (pts[1][0] - pts[0][0]) * w, pts[0][1] + (pts[1][1] - pts[0][1]) * w)


def m_fan(p, c):
    """Gruppenbewegung: die Geraete faechern gegeneinander auf und zu."""
    side = (c.i / max(1, c.n - 1)) * 2 - 1 if c.n > 1 else 0.0
    return _mv(p, side * (0.5 - 0.5 * math.cos(2 * math.pi * cycles(p, c))), 0.0)


def _sweep_u(p, c):
    """Lage im Verlauf 0..1, aus der Zeit gerechnet: nach einem Sprung stimmt das Bild sofort."""
    mode = p["ktv_sweep"]
    if mode == "once":
        u = c.u
    elif mode == "pingpong":
        x = _frac(c.u * p["ktv_sweep_n"])
        u = 1.0 - abs(2.0 * x - 1.0)
    else:
        beats = {"beat": 1.0, "beat2": 2.0, "bar": float(p["bar_len"]), "bar2": 2.0 * p["bar_len"]}[mode]
        u = _frac(c.beat / beats)                 # auf dem Beat-Raster, ein Zyklus je Einheit
    e = p["ktv_ease"]
    u = max(0.0, min(1.0, u))
    if e == "constant":
        return 0.0 if u < 0.5 else 1.0
    if e == "ease_in":
        return u * u
    if e == "ease_out":
        return 1.0 - (1.0 - u) * (1.0 - u)
    if e == "ease_in_out":
        return u * u * (3.0 - 2.0 * u)
    return u


def l_laser(p, c):
    """(an?, Muster, Farbe, Tempo, Parameter). Pulse hart auf dem Beat-Raster, ohne Strobe-Erlaubnis begrenzt engine.FlashLimiter."""
    on = 1.0
    if p["laser_pulse"] > 0:
        on = 1.0 if _frac(c.beat * p["laser_pulse"]) < p["duty"] else 0.0
    vals = p
    moving = [k for k in SWEEP_PARAMS if p[k + "_to"] != p[k]]
    if moving:                                    # nur mit Verlauf: eigene Werte fuer dieses Bild, sonst unveraendert
        u = _sweep_u(p, c)
        vals = dict(p)
        for k in moving:
            vals[k] = p[k] + (p[k + "_to"] - p[k]) * u
    return (on, p["laser_pattern"], p["laser_color"], p["laser_tempo"], vals)


def f_fog(p, c):
    return None


def _def(key, label, cat, out, fn, uses=(), **defaults):
    params = (["start", "end"] if out == "scalar" else []) + list(uses) + (ALWAYS if out not in ("laser", "fog", "nano_fx", "panel") else [])
    return {"key": key, "label": label, "cat": cat, "out": out, "fn": fn, "params": params,
            "defaults": {k: defaults.get(k, PARAMS[k][1]) for k in params}}


REGISTRY = {d["key"]: d for d in [
    _def("fade_in", "Fade In", "Dimmer", "scalar", s_fade_in, ["repeat"]),
    _def("fade_out", "Fade Out", "Dimmer", "scalar", s_fade_out, ["repeat"]),
    _def("blink", "Blinken", "Dimmer", "scalar", s_blink, RUN + ["duty"]),
    _def("pulse", "Pulsieren", "Dimmer", "scalar", s_pulse, RUN),
    _def("strobe", "Strobe", "Dimmer", "scalar", s_strobe, ["speed", "duty"], speed=10.0, duty=0.25),
    _def("sine", "Sinus-Helligkeit", "Dimmer", "scalar", s_sine, RUN),
    _def("solid_color", "Einzelfarbe", "Farben", "color", c_solid, ["color_a"]),
    _def("color_change", "Farbwechsel", "Farben", "color", c_change, RUN + ["color_a", "color_b", "smooth"],
         color_a="#ff00c8", color_b="#00d0ff", speed=0.5),
    _def("rgb_fade", "RGB-Verlauf", "Farben", "color", c_fade, ["repeat", "spread", "color_a", "color_b"]),
    _def("rainbow", "Regenbogen", "Farben", "color", c_rainbow, RUN + ["saturation"], speed=0.1),
    _def("red_blue", "Rot-Blau-Wechsel", "Farben", "color", c_change, RUN + ["color_a", "color_b", "smooth"],
         color_a="#ff0000", color_b="#0000ff"),
    _def("random_color", "Zufällige Farben", "Farben", "color", c_random, RUN + ["saturation"], speed=0.5),
    _def("circle", "Kreisbewegung", "Moving Head", "move", m_circle, RUN + ["size", "center_u", "center_v"], speed=0.25),
    _def("eight", "Acht-Bewegung", "Moving Head", "move", m_eight, RUN + ["size", "center_u", "center_v"], speed=0.15),
    _def("sweep_lr", "Links-Rechts-Sweep", "Moving Head", "move", m_sweep_lr, RUN + ["size", "center_u", "center_v"], speed=0.25),
    _def("sweep_ud", "Auf-Ab-Bewegung", "Moving Head", "move", m_sweep_ud, RUN + ["size", "center_u", "center_v"], speed=0.25),
    _def("sine_move", "Sinusbewegung", "Moving Head", "move", m_sine, RUN + ["size", "center_u", "center_v"], speed=0.2),
    _def("random_move", "Zufällige Bewegung", "Moving Head", "move", m_random, RUN + ["size", "center_u", "center_v"], speed=0.25),
    _def("chase", "Chase", "Effekte", "scalar", s_chase, RUN + ["width"], speed=1.0),
    _def("running", "Lauflicht", "Effekte", "scalar", s_running, RUN + ["width"], speed=0.5, width=2.0),
    _def("beat", "Beat-Synchron", "Effekte", "scalar", s_beat, ["speed"]),
    _def("group_wave", "Gruppenwelle", "Effekte", "scalar", s_sine, RUN, spread=1.0, speed=0.5),
    _def("fan", "Gruppenbewegung (Fächer)", "Effekte", "move", m_fan, RUN + ["size", "center_u", "center_v"], speed=0.25),
    _def("laser", "Laser", "Laser", "laser", l_laser, ["ktv_group", "ktv_effect", "ktv_fan", "ktv_fan_to", "ktv_size", "ktv_size_to", "ktv_pos_x", "ktv_pos_x_to", "ktv_pos_y", "ktv_pos_y_to", "ktv_rotate", "ktv_rotate_to", "ktv_sweep", "ktv_sweep_n", "ktv_ease", "ktv_zoom", "ktv_wave", "ktv_fx", "laser_pattern", "laser_color", "laser_tempo", "laser_pulse", "duty"]),
    _def("fog_burst", "Nebelschub", "Nebel", "fog", f_fog),
    _def("nano_effect", "Nanoleaf-Effekt", "Nanoleaf", "nano_fx", f_fog, ["nano_effect"]),
    _def("panel_scene", "Szene aus dem Panel", "Szenen", "panel", f_fog, ["panel_scene"]),
]}


def clean_params(key, p):
    """Parameter eines Clips pruefen, Fehlendes mit dem Standard fuellen, Unbekanntes verwerfen."""
    d = REGISTRY[key]
    out = dict(d["defaults"])
    for k in SWEEP_PARAMS:                        # ohne eigenen Bis-Wert (alte Clips): kein Verlauf, Bis = Von
        if key == "laser" and p and k in p and k + "_to" not in p:
            p = dict(p)
            p[k + "_to"] = p[k]
    for k in d["params"]:
        if k not in (p or {}):
            continue
        title, _, lo, hi, _, unit = PARAMS[k]
        v = p[k]
        if unit == "color":
            parse_color(v)                        # wirft bei falscher Farbe
            out[k] = v
        elif unit == "select":
            if v not in [o[0] for o in PARAM_OPTIONS[k]]:
                raise ValueError(f"{title}: {v!r} gibt es nicht")
            out[k] = v
        elif unit == "text":
            out[k] = str(v)[:80]
        elif unit == "bool":
            out[k] = 1 if v else 0
        else:
            out[k] = max(lo, min(hi, float(v)))
    return out


def full_params(key, p):
    """Werte fuer die Auswertung: alle von den Funktionen gelesenen Schluessel sind da, auch wenn das Muster sie nicht anbietet."""
    full = {"bar_len": 4, "laser_pulse": 0.0, "repeat": 0, "beat_sync": 0, "spread": 0.0, "speed": 1.0, "intensity": 1.0, "start": 0, "end": 255,
            "duty": 0.5, "width": 1.0, "smooth": 0.0, "fade_in": 0.0, "fade_out": 0.0}
    full.update(REGISTRY[key]["defaults"])
    full.update(p)
    return full


def evaluate(key, p, c):
    """Wert eines Musters mit vollstaendigen Parametern (full_params)."""
    d = REGISTRY[key]
    v = d["fn"](p, c)
    if d["out"] == "scalar":
        return p["start"] + (p["end"] - p["start"]) * max(0.0, min(1.0, v)) * p["intensity"]
    if d["out"] == "color":
        k = p["intensity"]
        return tuple(x * k for x in v)
    return v


def catalog():
    """Fuer das Panel: alle Muster mit ihren Parametern."""
    return {"patterns": [{k: d[k] for k in ("key", "label", "cat", "out", "params", "defaults")} for d in REGISTRY.values()],
            "params": {k: {"label": v[0], "default": v[1], "lo": v[2], "hi": v[3], "step": v[4], "unit": v[5], "options": PARAM_OPTIONS.get(k)} for k, v in PARAMS.items()}}
