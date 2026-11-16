#!/usr/bin/env python3
"""
assistant.py - Show-Assistent: macht aus Lied und Geraeten einen Vorschlag, den Markus nur noch verfeinert.

Drei Schritte, jeder fuer sich pruefbar:
  song_info   Aufbau des Liedes: aus der Mixxx-Analyse (marks), sonst aus der Wellenform geschaetzt, sonst gleichmaessig
  direct      Regie: je Abschnitt Stufe, Farben und Muster. Offline nach festen Lichtregeln, Claude darf sie nur umstellen
  render      Spuren daraus, immer mit denselben Grenzen (Regeln 2, 4 und 5 der Projektanleitung)

Der Assistent schaltet nie eine Erlaubnis ein. Laser und Nebel sind nur Clips, die Engine laesst sie erst mit sm_laser und sm_fog
durch, Blitze ohne Strobe-Erlaubnis begrenzt der FlashLimiter. Einzelne Laser-, Strobe-, Mode- und Reset-Kanaele fasst er nie an.
"""
import base64
import colorsys
import json
import random
import re
import time
import urllib.error
import urllib.request

from genre_style import STYLES

from . import patterns as pt

STYLE_NAMES = {"club": "Club", "party": "Party", "rock": "Rock", "ruhig": "Ruhig", "weihnachten": "Weihnachten"}
CLUB_PALETTES = [[0.75, 0.52], [0.60, 0.88], [0.0, 0.60], [0.83, 0.47], [0.13, 0.75]]   # Farbtoene: fuer Club keine feste Palette
KINDS = ("intro", "vers", "main", "break", "outro", "build", "drop", "gap", "hit")
BASE_LEVEL = {"gap": -1, "intro": 0, "outro": 0, "break": 0, "vers": 1, "build": 1, "main": 2, "hit": 2, "drop": 3}
DROP_BARS = 2                 # Gewitter: so kurz arbeiten alle zusammen, dann gleich wieder einer allein
DROP_MIN_GAP_S = 40.0         # grosse Drops liegen weit auseinander, sonst nutzt sich das Gewitter ab
DROP_MAX = 4
PHRASE_BARS = 8               # Bloecke bei geschaetztem Aufbau
# Ein Geraet allein, alles andere dunkel, Wechsel auf dem Beat. So lange ist eines ungefaehr dran (Sekunden, auf ganze Takte gerundet).
TURN_S = {"main": 4.0, "vers": 6.0}
TURN_QUIET_S = 8.0
SEQUENCE = ("spot", "nano", "band", "bars", "laser", "fx", "wash")   # die Reihenfolge von Markus, Eyes/Derby und Washes dazu
# Helligkeit im Raum (docs/RAUM.md): Nanoleaf und Effektband sehr hell, Docooler mittel, Vega, Eyes, Derby und Washes schwach.
# Ein schwaches Geraet ginge im lauten Hauptteil allein unter: dort bekommt es einen Partner, der im Raum wirkt.
WEAK_PARTNER = {"spot": "bars", "fx": "bars", "wash": "nano"}         # Vega steht mitten in den Docoolern, die Washes leuchten aufs Nanoleaf
NOT_AT = {0: ("bars", "laser", "fx"), 1: ("laser",)}                 # ruhige Stellen: nur was ruhig wirkt
# Grundsaetzlich einer allein. Im Hauptteil kommt jeder dritte Einsatz mit einem Partner, der dazu passt, nie mehr: keine helle Einheitssuppe.
PAIRS = {"spot": "laser", "nano": "wash", "bars": "nano", "laser": "spot", "fx": "laser"}   # Nanoleaf und Washes: dieselbe Wand
PAIR_EVERY = 3
SWAP_EVERY = 2                # jeder zweite dieser Einsaetze: die zwei schalten im Takt hin und her statt gemeinsam zu spielen
SWAP_PLAIN = ("spot", "nano", "bars", "fx")   # nur Geraete mit Dimmer, der Laser bleibt bei seinem Clip
HIT_RATIO = 1.3               # starker Peak: so viel lauter als die Beats davor
HIT_MIN = 0.45                # und mindestens so laut, gemessen am lautesten Beat des Liedes
HIT_JUMP = 1.35               # oder so viel lauter als der Beat direkt davor
HIT_BEATS = 4                 # Standard, solange die Wellenform nichts Genaueres sagt
HIT_MAX_BEATS = 8             # so lange darf ein Peak hoechstens ausklingen
HIT_STEP_S = 0.1              # Aufloesung des Abklingens
SERIES_GAP_S = 10.0           # Peaks in diesem Abstand sind eine Reihe und gehoeren demselben Geraet
DENSE_GAP_BARS = 3            # beginnen sie so dicht nacheinander, bleibt es dazwischen finster
ACCENTS = ("band", "laser", "bars", "nano")   # jede Reihe von Peaks bekommt ihr Geraet, nur was im Raum wirkt (der Vega ist zu schwach)
FADE_START = 0.75             # Fade-out: ab hier bleibt der Pegel bis zum Schluss unter diesem Anteil der Musik davor
FADE_END = 0.35               # und am Ende ist er so weit unten, sonst ist es ein hartes Ende
FADE_MIN_BEATS = 4
FADE_MAX_SHARE = 0.3
NANO_FX_EVERY = 3              # jeder so vielte Einsatz des Nanoleaf bekommt einen seiner eigenen Effekte: schoen, aber nicht dauernd
NANO_FX_MIN_S = 3.0           # das Umschalten am Geraet dauert, zu kurz lohnt nicht
HOLD_EVERY = 5                # nach so vielen Wechseln ein laengerer Bereich mit einem Geraet
HOLD_PIECES = 2               # um so viele Stuecke verlaengert
HOLD_ROLES = ("spot", "nano", "bars", "fx")
ROLES = ("bars", "wash", "spot", "fx", "nano", "uv", "laser", "band")
# Pegelkurven der getrennten Spuren (vom Mac, shows/_stems): nur wenn es sie gibt, sonst bleibt alles wie bisher
STEM_KEYS = ("stimme", "bass", "kick", "hihat", "sonstiges")
STEM_NEAR_DB = 15.0           # eine Spur spielt, wenn sie so nah an ihrem lauten Pegel liegt (90 % der Beats sind leiser)
STEM_FLOOR_DB = -45.0         # und mindestens so laut ist
KICKLESS_BEATS = 8            # 2 Takte ohne Kick: ruhige Stelle, auch wenn die Wellenform laut ist
KICK_WINDOW = 8               # Kick zaehlt als da, wenn sie in mindestens der Haelfte der Beats rundum schlaegt:
KICK_DENSE = 0.5              # einzelne Schlaege alle paar Takte (Horn, Akzent im Break) sind noch kein Beat
DROP_AFTER_BEATS = 16         # kommt die Kick nach mindestens 4 Takten zurueck, ist das ein Drop
BUILD_RISE_DB = 6.0           # Snare/Hi-Hat am Ende der Pause so viel lauter als am Anfang: Aufbau
BUILD_MAX_BEATS = 16
SILENT_DB = -40.0             # alle Spuren leiser: Pause in der Musik, finster
VOCAL_SHARE = 0.5             # Gesang in mindestens der Haelfte der Beats
CALM_KICK_SHARE = 0.3         # und Kick in hoechstens so vielen: ruhige Stelle mit Gesang
# Raum (docs/RAUM.md): Washes leuchten auf die Nanoleaf-Wand, der Vega projiziert sein Gobo an die Wand gegenueber.
VOCAL_LEADS = ("spot", "nano")
WALL_PARTNER = "wash"
KTV_FAN_OPEN = 255            # Faecher immer ganz offen: bewegt wird der Zoom (Wunsch von Markus, 05.11.2026)
KTV_ZOOM_SMALL, KTV_ZOOM_BIG = 220, 30                  # Kanal 6: 0 = gross, 255 = klein
FOG_BEAM_S = 20.0             # so lange nach einem Nebelschub ist der Strahl des Vega zu sehen: er ist als Naechster dran
# Raumplan (Seite /raum, raum.json): nur wenn Markus ihn gespeichert hat
WAVE_EVERY = 4                # jeder so vielte Einsatz im Hauptteil ist eine Lichtwelle durch den Raum
WAVE_ROLES = ("bars", "spot", "nano", "uv", "fx")   # Washes nicht (Dimmer zu traege), Ambiente blinkt nie mit, Laser und Nebel sind eigene Clips
WAVE_STEP_M = 0.8             # Geraete naeher beieinander leuchten in derselben Stufe der Welle
WAVE_MIN_STEPS = 3
ORDER_ROLES = ("bars", "wash", "fx")   # Gruppen, deren Reihenfolge (Chase, Lauflicht, Welle) dem Raum folgt
FOG_S = 3.0                   # ein Schub wie vom Nebel-Knopf
FOG_GAP_S = 30.0
MAX_FOG = 10
WASH_PEAK = {0: 0.3, 1: 0.25, 2: 0.3, 3: 0.4}   # hoechste Helligkeit der Washes je Stufe
DIMMERS = ("sine", "pulse", "group_wave", "running", "chase", "beat", "blink")
COLORS = ("solid_color", "rgb_fade", "color_change", "red_blue", "random_color", "rainbow")
MOVES = ("sine_move", "sweep_lr", "sweep_ud", "circle", "eight", "fan", "random_move")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 4.0, 20.0   # Dollar je Million Tokens laut Preisliste, nur fuer die Schaetzung im Fenster


# ---- Aufbau des Liedes ----------------------------------------------------------------------------------------------
def _bar(doc):
    return 60.0 / (doc.get("bpm") or 120.0) * (doc.get("beats_per_bar") or 4)


def energy_from_peaks(peaks):
    """Lautstaerke 0..100 je Sekunde aus der gespeicherten Wellenform."""
    p = peaks or {}
    lo, hi, rate = p.get("min"), p.get("max"), p.get("rate")
    if not lo or not hi or not rate:
        return []
    step = max(1, int(rate))
    return [int(max(0, max(hi[i:i + step]) - min(lo[i:i + step])) * 100 / 254) for i in range(0, min(len(lo), len(hi)), step)]


def beat_levels(peaks, beat, off):
    """Lautstaerke je Beat aus der Wellenform."""
    p = peaks or {}
    lo, hi, rate = p.get("min"), p.get("max"), p.get("rate")
    if not lo or not hi or not rate or beat <= 0:
        return []
    out, n = [], min(len(lo), len(hi))
    t = off
    while int(t * rate) < n:
        i, j = max(0, int(t * rate)), min(n, int((t + beat) * rate))
        if j > i:
            out.append(sum(hi[k] - lo[k] for k in range(i, j)) / (j - i))
        t += beat
    return out


def find_hits(v, beat, off):
    """Starke Peaks, die man auch in der Wellenform sieht (Bass, Schiffshorn): ein Beat viel lauter als die davor. [[Zeit, Dauer, Staerke]]."""
    if not v:
        return []
    top, out, last = max(v) or 1.0, [], -99
    for i, x in enumerate(v):
        prev = sorted(v[max(0, i - 4):i])
        base = prev[len(prev) // 2] if prev else 0.0
        if x < HIT_MIN * top or i - last < 4 or (prev and x < HIT_RATIO * base and x < HIT_JUMP * v[i - 1]):
            continue
        out.append([round(off + i * beat, 3), round(HIT_BEATS * beat, 3), round(x / top, 2)])
        last = i
    return out


def hit_curve(peaks, t, until):
    """Abklingen eines Peaks aus seiner Amplitude: beginnt bei 100 % und faellt, wie das Horn leiser wird, nie wieder nach oben.
    0 % ist der Pegel der Musik unter dem Horn. Gibt (Dauer, [[Sekunden ab Start, Wert 0..255], ...])."""
    lo, hi, rate = peaks["min"], peaks["max"], peaks["rate"]
    size = max(1, int(HIT_STEP_S * rate))
    i0, i1 = int(t * rate), min(len(lo), len(hi), int(until * rate))
    vals = [sum(hi[k] - lo[k] for k in range(i, min(i + size, i1))) / (min(i + size, i1) - i) for i in range(i0, i1, size)]
    if len(vals) < 2:
        return until - t, [[0.0, 255.0], [round(until - t, 3), 0.0]]
    floor, top = sorted(vals)[len(vals) // 4], max(vals)
    for i in range(len(vals) - 2, -1, -1):                       # von hinten: was spaeter noch laut ist, haelt die Kurve oben
        vals[i] = max(vals[i], vals[i + 1])
    lv = [max(0.0, (x - floor) / (top - floor)) if top > floor else 0.0 for x in vals]
    end = next((i for i, x in enumerate(lv) if x < 0.08), len(lv))
    end = max(end, 2)
    step = size / rate
    pts = [[0.0, 255.0]]
    held = 255.0                                                 # bleibt die Kurve flach, muss der Knick erhalten bleiben, sonst wird daraus eine Rampe
    for i in range(1, end):
        v = round(255 * lv[i], 1)
        if abs(v - pts[-1][1]) >= 15:                            # nur wo sich sichtbar etwas tut, sonst wird die Spur unbedienbar
            if round((i - 1) * step, 3) > pts[-1][0]:
                pts.append([round((i - 1) * step, 3), held])
            pts.append([round(i * step, 3), v])
        held = pts[-1][1]
    d = round(end * step, 3)
    if round(d - step, 3) > pts[-1][0]:
        pts.append([round(d - step, 3), held])
    pts.append([d, 0.0])
    return d, pts


def find_fade(v, beat, off, dur):
    """Wird das Lied am Schluss leiser, auch sichtbar in der Wellenform? Dann [Beginn, [[Zeit, Wert 0..255], ...]] fuer den Master, sonst None.
    Ein hartes Ende bleibt ohne Fade."""
    n = len(v)
    if n < 32:
        return None
    body = sorted(v[max(0, n - 64):n - 16]) or [0.0]
    ref = body[len(body) // 2]
    last = sum(v[-2:]) / 2
    if ref <= 0 or last >= FADE_END * ref:
        return None
    i = n
    while i > 0 and (v[i - 1] + v[min(i, n - 1)]) / 2 < FADE_START * ref and n - i < n * FADE_MAX_SHARE:   # ein einzelner Schlag beendet den Ausklang nicht
        i -= 1
    if n - i < FADE_MIN_BEATS:
        return None
    tail = [(v[k] + v[min(k + 1, n - 1)]) / 2 for k in range(i, n)]
    for k in range(len(tail) - 2, -1, -1):                       # faellt nur noch, auch wenn ein Schlag dazwischen lauter ist
        tail[k] = max(tail[k], tail[k + 1])
    start = round(off + i * beat, 3)
    pts = [[start, 255.0]]
    for k, x in enumerate(tail[1:], 1):
        val = round(255 * x / tail[0], 1)
        if abs(val - pts[-1][1]) >= 10:
            pts.append([round(start + k * beat, 3), val])
    pts.append([round(dur, 3), 0.0])
    return [start, pts]


def _level_at(en, a, b, dur):
    """Mittlere Lautstaerke zwischen a und b; die Kurve hat beliebig viele Werte ueber das ganze Lied."""
    if not en or dur <= 0:
        return 0.0
    i, j = int(a / dur * len(en)), max(int(a / dur * len(en)) + 1, int(b / dur * len(en)))
    part = en[i:j]
    return sum(part) / len(part) if part else 0.0


def sections_from_energy(en, dur, bar):
    """Abschnitte nur aus der Lautstaerke, in Bloecken von 8 Takten. Leise am Rand = Intro und Outro, leise in der Mitte = Break."""
    size = PHRASE_BARS * bar
    n = max(1, int(dur / size + 0.5))
    vals = [_level_at(en, i * dur / n, (i + 1) * dur / n, dur) for i in range(n)]
    top = max(vals) or 1.0
    kinds = []
    for i, v in enumerate(vals):
        u = v / top
        if u >= 0.8:
            kinds.append("main")
        elif u >= 0.5:
            kinds.append("vers")
        else:
            kinds.append("intro" if i == 0 else "outro" if i == n - 1 else "break")
    out = []
    for i, k in enumerate(kinds):
        a, b = i * dur / n, (i + 1) * dur / n
        if out and out[-1][0] == k:
            out[-1][2] = b
        else:
            out.append([k, a, b])
    return out


def stem_beats(stems, beat, off, dur):
    """Pegel je Beat (dB, Spitzenwert) aus den Kurven der Spuren. {} ohne Kurven."""
    if not stems or not isinstance(stems.get("curves"), dict) or beat <= 0:
        return {}
    rate, lo = int(stems.get("rate") or 100), float(stems.get("db_min", -60.0))
    n = int(max(0.0, dur - off) / beat)
    out = {}
    for k in STEM_KEYS:
        try:
            v = base64.b64decode(stems["curves"][k])
        except (KeyError, TypeError, ValueError):
            return {}
        row = []
        for i in range(n):
            part = v[max(0, int((off + i * beat) * rate)):max(0, int((off + (i + 1) * beat) * rate))]
            row.append(round(lo - lo * max(part) / 255.0, 1) if part else lo)
        out[k] = row
    return out


def stem_present(row):
    """Spielt die Spur auf diesem Beat? Gemessen an ihrem eigenen lauten Pegel, jede Spur ist anders laut."""
    if not row:
        return []
    top = sorted(row)[int(0.9 * (len(row) - 1))]
    thr = max(STEM_FLOOR_DB, top - STEM_NEAR_DB)
    return [x >= thr for x in row]


def dense(flags, w=KICK_WINDOW, share=KICK_DENSE):
    """Laeuft das durch? Anteil der Beats rundum."""
    n, h = len(flags), w // 2
    out = []
    for i in range(n):
        part = flags[max(0, i - h):min(n, i + h)]
        out.append(bool(part) and sum(part) >= share * len(part))
    return out


def _runs(flags):
    """[(Anfang, Ende)] der zusammenhaengenden True-Strecken."""
    out, i = [], 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j < len(flags) and flags[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def stem_events(sb, beat, off):
    """Aus den Spuren: Pausen (alles leise), ruhige Stellen ohne Kick, Aufbau (Snare/Hi-Hat werden lauter), Drop (die Kick kommt zurueck)."""
    if not sb:
        return []
    n = len(sb["kick"])
    at = lambda i: round(off + i * beat, 3)
    kick, hat = dense(stem_present(sb["kick"])), stem_present(sb["hihat"])
    ev = [["gap", at(i), at(j)] for i, j in _runs([all(sb[k][x] < SILENT_DB for k in STEM_KEYS) for x in range(n)]) if i > 0 and j < n]
    for i, j in _runs([not x for x in kick]):
        if j - i < KICKLESS_BEATS:
            continue
        if j - i >= DROP_AFTER_BEATS and j < n:
            ev.append(["drop", at(j), at(j)])
        if i == 0 or j >= n:
            continue                                             # Anfang und Ende bleiben Intro und Outro
        m = min(BUILD_MAX_BEATS, (j - i) // 2)
        h = sb["hihat"]
        if m >= 4 and sum(hat[j - m:j]) >= 0.5 * m and sum(h[j - m:j]) / m - sum(h[i:i + m]) / m >= BUILD_RISE_DB:
            if j - m > i:
                ev.append(["break", at(i), at(j - m)])
            ev.append(["build", at(j - m), at(j)])
        else:
            ev.append(["break", at(i), at(j)])
    return sorted(ev, key=lambda e: (e[0] != "gap", e[1]))       # Pausen zuerst: sie liegen oft in einer ruhigen Stelle


def stem_share(song, key, a, b):
    """Anteil der Beats zwischen a und b, in denen die Spur spielt."""
    row = (song.get("sp") or {}).get(key)
    if not row:
        return 0.0
    i, j = int((a - song["off"]) / song["beat"]), int((b - song["off"]) / song["beat"])
    part = row[max(0, i):max(max(0, i) + 1, j)]
    return sum(part) / len(part) if part else 0.0


def song_info(doc, peaks=None, stems=None):
    """Alles, was die Regie wissen muss. source sagt, woher der Aufbau stammt: mixxx, wave oder raster."""
    m = doc.get("marks") or {}
    dur, bar = float(doc.get("duration") or 180.0), _bar(doc)
    en = list(m.get("en") or []) or energy_from_peaks(peaks)
    ev = [e for e in m.get("ev") or [] if e[1] < dur]
    if m.get("se"):
        secs, source = [list(s) for s in m["se"]], "mixxx"
    elif en:
        secs, source = sections_from_energy(en, dur, bar), "wave"
    else:
        n = max(1, int(dur / (PHRASE_BARS * bar) + 0.5))        # nichts bekannt: Bloecke im Takt, das Licht baut sich auf und wieder ab
        cycle = ["vers", "main"]
        secs = [[("intro" if i == 0 else "outro" if i == n - 1 and n > 1 else cycle[i % 2]), i * dur / n, (i + 1) * dur / n] for i in range(n)]
        source = "raster"
    if not ev and source != "mixxx":                            # geschaetzt: nach einem leisen Abschnitt kommt der Drop
        ev = [["drop", b[1], b[1]] for a, b in zip(secs, secs[1:]) if a[0] in ("break", "intro") and b[0] == "main"]
    beat, off = bar / (doc.get("beats_per_bar") or 4), float(doc.get("beat_offset") or 0.0)
    sb = stem_beats(stems, beat, off, dur)
    if sb:                                                       # die Spuren wissen es genauer als die Schaetzung aus der Wellenform
        sev = stem_events(sb, beat, off)
        ev = (ev if source == "mixxx" else [e for e in ev if e[0] != "drop"]) + sev
    loud = beat_levels(peaks, beat, off)
    fade = find_fade(loud, beat, off, dur)
    ev = [e for e in ev if not fade or e[1] < fade[0]]           # im Ausklang passiert nichts mehr
    drops = big_drops(ev, dur, loud, beat, off)
    hits = [h for h in find_hits(loud, beat, off) if not any(x - beat <= h[0] < x + DROP_BARS * bar for x in drops) and (not fade or h[0] < fade[0] - beat)]
    for i, h in enumerate(hits):
        # kurz vor dem naechsten Peak Schluss, sein Schlag gehoert nicht mehr zu diesem Abklingen
        stops = [h[0] + HIT_MAX_BEATS * beat, dur] + [x[0] - 2 * HIT_STEP_S for x in hits[i + 1:i + 2]] + [x for x in drops if x > h[0]]
        h[1], curve = hit_curve(peaks, h[0], min(stops))
        h.append(curve)
    return {"dur": dur, "bar": bar, "beat": beat, "off": off, "drops": drops, "hits": hits, "loud": loud, "fade": fade, "secs": secs, "cues": list(m.get("cu") or []), "ev": ev, "en": en, "source": source,
            "genre": m.get("genre") or "", "lvl": m.get("lvl"), "title": m.get("title") or (doc.get("mixxx") or {}).get("title") or doc.get("name", ""),
            "sb": sb, "sp": {k: dense(stem_present(sb[k])) if k == "kick" else stem_present(sb[k]) for k in sb}}


def big_drops(ev, dur, loud=None, beat=0.0, off=0.0):
    """Nur die grossen Drops: nicht ganz am Anfang, weit auseinander, wenige. Mit Wellenform gewinnen die, bei denen es wirklich am meisten
    lauter wird. Die Analyse meldet viel mehr, sonst waere dauernd alles an."""
    def jump(t):
        if not loud or beat <= 0:
            return 0.0
        i = int((t - off) / beat + 0.5)
        a, b = loud[max(0, i - 8):i], loud[i:i + 8]
        return (sum(b) / len(b) - sum(a) / len(a)) if a and b else 0.0
    cand = [e[1] for e in ev if e[0] == "drop" and e[1] >= max(20.0, dur * 0.12)]
    out = []
    for t in sorted(sorted(cand), key=jump, reverse=True):       # ohne Wellenform: der Reihe nach
        if all(abs(t - x) >= DROP_MIN_GAP_S for x in out) and len(out) < DROP_MAX:
            out.append(t)
    return sorted(out)


def _on_beat(song, t):
    """Jeder Wechsel liegt auf einem Beat, nie dazwischen."""
    b = song["beat"]
    return max(0.0, round(song["off"] + round((t - song["off"]) / b) * b, 3))


def _turn_bars(kind, bar):
    """Ganze Takte, gerade Zahl klingt in der Musik richtig."""
    n = max(1, round(TURN_S.get(kind, TURN_QUIET_S) / bar))
    return n + 1 if n > 1 and n % 2 else n


def segments(song):
    """Das Lied in Stuecke teilen: an Abschnitten, Cues und Ereignissen, dazwischen je ein Stueck fuer jedes Geraet. Alle Grenzen auf dem Beat."""
    dur, bar = song["dur"], song["bar"]
    cuts = {0.0, dur}
    for s in song["secs"]:
        cuts.update((s[1], s[2]))
    cuts.update(c for c in song["cues"] if 0 < c < dur)
    if song.get("fade"):
        cuts.add(song["fade"][0])
    for h in song["hits"]:
        cuts.update((h[0], h[0] + h[1]))
    fixed = {_on_beat(song, h[0]) for h in song["hits"]}         # der Beginn eines Peaks wird nie weggeschoben
    for e in song["ev"]:
        if e[0] != "drop":
            cuts.update((e[1], e[2]))
    for t in song["drops"]:
        cuts.update((t, t + DROP_BARS * bar))
    pts = sorted({0.0 if c <= 0 else dur if c >= dur else _on_beat(song, c) for c in cuts})
    keep = [pts[0]]
    for p in pts[1:]:                                            # zu kurze Stuecke mit dem vorigen zusammenlegen
        if p - keep[-1] >= bar * 0.9:
            keep.append(p)
        elif p in fixed and keep[-1] not in fixed:
            if len(keep) > 1:
                keep[-1] = p
            elif p > 0:                                          # Peak gleich am Anfang des Liedes: kurzes erstes Stueck
                keep.append(p)
    if keep[-1] in fixed and keep[-1] < dur:                     # Peak ganz am Ende: er bleibt ein eigenes Stueck
        keep.append(dur)
    keep[-1] = dur
    out = []
    for a, b in zip(keep, keep[1:]):
        kind = "hit" if a in fixed else _kind_at(song, (a + b) / 2)
        n = 1 if kind in ("drop", "build", "gap", "hit") else max(1, round((b - a) / (_turn_bars(kind, bar) * bar)))
        edges = [a] + [_on_beat(song, a + (b - a) * i / n) for i in range(1, n)] + [b]
        for t0, t1 in zip(edges, edges[1:]):
            out.append({"i": len(out), "t": round(t0, 3), "d": round(t1 - t0, 3), "kind": kind})
    return out


def _kind_at(song, t):
    if song.get("fade") and t >= song["fade"][0]:
        return "outro"                                           # Ausklang: ruhig, der Master blendet aus
    for x in song["drops"]:
        if x <= t < x + DROP_BARS * song["bar"]:
            return "drop"
    hits = song["hits"]
    for i, h in enumerate(hits):
        if h[0] <= t < h[0] + h[1]:
            return "hit"
        if i + 1 < len(hits) and h[0] + h[1] <= t < hits[i + 1][0] and hits[i + 1][0] - h[0] <= DENSE_GAP_BARS * song["bar"]:
            return "gap"                                         # zwischen dichten Peaks finster, das macht sie stark
    for e in song["ev"]:
        if e[0] in ("gap", "build", "break") and e[1] <= t < e[2]:
            return e[0]
    for s in song["secs"]:
        if s[1] <= t < s[2]:
            return s[0]
    return "vers"


# ---- Regie -----------------------------------------------------------------------------------------------------------
def _hex(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def palette(style, rng):
    hues = (STYLES.get(style) or {}).get("colors")
    return list(hues) if hues else list(rng.choice(CLUB_PALETTES))


def direct(song, style, wild, seed, waves=False):
    """Offline-Regie: jedes Stueck bekommt Stufe (-1 dunkel bis 3 Hoehepunkt), zwei Farben und je ein Muster."""
    rng = random.Random(seed)
    st = STYLES.get(style) or {}
    wild = max(0.0, min(1.0, wild + st.get("energy", 0.0)))   # Energiestufe stellt schon der Regler im Fenster vor (SM.wildFor)
    hues = palette(style, rng)
    rng.shuffle(hues)
    mean = (sum(song["en"]) / len(song["en"])) if song["en"] else 0.0
    plan, turn, sect, last, prev, solos, swaps = [], 0, -1, None, "", 0, 0
    series, last_hit, was_dense, power, curve = -1, None, False, 1.0, None
    since, hold, vturn, wturn = 0, 0, 0, 0
    hits = [_on_beat(song, c) for c in song["cues"]] + [_on_beat(song, x[1]) for x in song["secs"] if x[1] > 0]
    for sg in segments(song):
        k = sg["kind"]
        lv = BASE_LEVEL[k]
        if k in ("main", "vers") and mean and _level_at(song["en"], sg["t"], sg["t"] + sg["d"], song["dur"]) < mean * 0.7:
            lv -= 1                                              # leise Stelle im Abschnitt: das Licht geht mit
        if lv == 1 and wild > 0.7:
            lv = 2
        if lv == 3 and (wild < 0.25 or style == "ruhig"):
            lv = 2
        if k != last:                                            # neue Farben je Abschnitt, nicht je Stueck: das Licht bleibt ruhig
            sect, last = sect + 1, k
        a, b = hues[sect % len(hues)], hues[(sect + 1) % len(hues)]
        lv = max(-1, min(3, lv))
        lead = ""
        if 0 <= lv <= 2:
            if k == "hit":
                h = min(song["hits"], key=lambda x: abs(x[0] - sg["t"]))   # Stuecke liegen auf dem Beat, der Peak nicht immer genau
                dense = _is_dense(song, h)
                if last_hit is None or h[0] - last_hit > SERIES_GAP_S or dense != was_dense:
                    series += 1                                  # neuer Rhythmus der Peaks: das naechste Geraet
                last_hit, was_dense, power, curve = h[0], dense, h[2], h[3]
                lead = ACCENTS[series % len(ACCENTS)]
            elif k == "build":
                lead = "bars"
            elif prev != "band" and any(abs(h - sg["t"]) < 0.01 for h in hits):
                lead = "band"                                    # etwas passiert in der Musik: das Effektband ist dran
            elif _vocal_calm(song, sg, lv):
                lead = VOCAL_LEADS[vturn % 2] if VOCAL_LEADS[vturn % 2] != prev else VOCAL_LEADS[(vturn + 1) % 2]
                vturn += 1                                       # Gesang an ruhiger Stelle: Gobo an die Wand oder die Wand selbst
            elif hold > 0 and prev in HOLD_ROLES and prev not in NOT_AT.get(lv, ()):
                lead, hold = prev, hold - 1                      # laengerer Bereich: dasselbe Geraet bleibt dran
            else:
                hold = 0
                if waves and k == "main" and lv == 2:
                    wturn += 1
                    if wturn % WAVE_EVERY == 0 and prev != "wave":
                        lead = "wave"                            # das Licht laeuft durch den Raum (Raumplan)
                while not lead:                                  # der Reihe nach, sonst nie zweimal dasselbe Geraet
                    r = SEQUENCE[turn % len(SEQUENCE)]
                    turn += 1
                    if r != prev and r not in NOT_AT.get(lv, ()):
                        lead = r
                since += 1
                if since >= HOLD_EVERY and lead in HOLD_ROLES:   # nach etlichen Wechseln eine ruhigere Strecke, sonst wird es hektisch
                    since, hold = 0, HOLD_PIECES
            prev = lead
        also, swap = "", False
        if lead == "nano" and _vocal_calm(song, sg, lv):
            also = WALL_PARTNER                                  # Washes leuchten auf die Nanoleaf-Wand
        if lead in WEAK_PARTNER and k == "main" and lv == 2:
            also = WEAK_PARTNER[lead]
        elif lead and lead != "wave" and k == "main" and lv == 2:
            solos += 1
            if solos >= PAIR_EVERY and lead in PAIRS:            # hat das Geraet keinen Partner: beim naechsten
                solos, also = 0, PAIRS[lead]
                if lead in SWAP_PLAIN and also in SWAP_PLAIN:
                    swaps += 1
                    swap = swaps % SWAP_EVERY == 1
        sat = 0.75 if lv <= 0 else 1.0
        plan.append(dict(sg, level=lv, lead=lead, also=also, swap=swap, series=series, power=power, curve=curve if k == "hit" else None, colors=[_hex(a, sat), _hex(b, sat)], dimmer=_pick_dimmer(lv, k, rng),
                         color=_pick_color(lv, style, wild, rng), move=_pick_move(lv, rng), laser=lv >= 3, fog=k == "drop"))
    return plan


def _vocal_calm(song, sg, lv):
    """Ruhige Stelle mit Gesang und ohne Kick, nur mit Kurven der Spuren."""
    if not song.get("sp") or lv not in (0, 1) or sg["kind"] in ("hit", "build", "drop", "gap"):
        return False
    a, b = sg["t"], sg["t"] + sg["d"]
    return stem_share(song, "stimme", a, b) >= VOCAL_SHARE and stem_share(song, "kick", a, b) <= CALM_KICK_SHARE


def _is_dense(song, h):
    """Liegt der naechste oder vorige Peak so nah, dass es dazwischen finster bleibt?"""
    return any(x is not h and abs(x[0] - h[0]) <= DENSE_GAP_BARS * song["bar"] for x in song["hits"])


def _pick_dimmer(lv, kind, rng):
    if lv <= 0:
        return "sine"
    if kind == "build":
        return "blink"
    if lv == 1:
        return rng.choice(["pulse", "group_wave"])
    if lv == 2:
        return rng.choice(["running", "chase", "group_wave"])
    return rng.choice(["beat", "chase", "blink"])


def _pick_color(lv, style, wild, rng):
    if lv <= 0:
        return "solid_color"
    if lv == 1:
        return "rgb_fade"
    if lv == 2 or style == "weihnachten":                        # bunt nur, wenn es der Stil zulaesst
        return "color_change"
    return rng.choice(["color_change", "rainbow"] if wild > 0.5 else ["color_change"])


def _pick_move(lv, rng):
    if lv <= 0:
        return "sine_move"
    if lv == 1:
        return rng.choice(["sweep_lr", "sine_move"])
    return rng.choice(["circle", "eight", "fan"])


def apply_claude(plan, answer):
    """Antwort von Claude auf die Regie legen. Sie gilt als ungeprueft: nur bekannte Stuecke, Muster und Farben kommen durch."""
    by_i = {s["i"]: s for s in plan}
    for a in (answer.get("segments") if isinstance(answer, dict) else None) or []:
        s = by_i.get(a.get("i")) if isinstance(a, dict) else None
        if s is None:
            continue
        if isinstance(a.get("level"), int):
            s["level"] = max(-1, min(3 if s["kind"] == "drop" else 2, a["level"]))   # alle zusammen gibt es nur beim Drop
        if a.get("lead") in ROLES:
            s["lead"] = a["lead"]
        if isinstance(a.get("swap"), bool):
            s["swap"] = a["swap"]
        if a.get("also") in ROLES or a.get("also") == "":
            s["also"] = a["also"] if a["also"] != s["lead"] else ""
        cols = a.get("colors")
        if isinstance(cols, list) and len(cols) == 2 and all(isinstance(c, str) and HEX_RE.match(c) for c in cols):
            s["colors"] = cols
        for key, allowed in (("dimmer", DIMMERS), ("color", COLORS), ("move", MOVES)):
            if a.get(key) in allowed:
                s[key] = a[key]
        for key in ("laser", "fog"):
            if isinstance(a.get(key), bool):
                s[key] = a[key]
    return plan


# ---- Spuren ------------------------------------------------------------------------------------------------------------
def rig_parts(meta):
    """Geraete nach ihrer Rolle in der Show: {Rolle: {group, fixtures}}. Die Gruppen kommen aus der Anlage."""
    parts = {"ktv": [], "hazer": [], "ambient": [], "preset": []}
    groups = {}
    for g in meta["groups"]:
        groups[g["id"]] = g
    for f in meta["fixtures"]:
        attrs = {a["attr"] for a in f["attrs"]}
        if "fog" in attrs:
            parts["hazer"].append(f)
        elif "laser" in attrs and f.get("group") == "locked":
            parts["ktv"].append(f)
        elif "preset" in attrs:
            parts["preset"].append(f)
        elif f.get("group") == "ambient":
            parts["ambient"].append(f)
        else:
            parts.setdefault(f.get("group"), []).append(f)
    parts["_groups"] = groups
    return parts


def _attrs(fixtures):
    return {a["attr"] for f in fixtures for a in f["attrs"]}


def _target(parts, role):
    """Ganze Gruppe, wenn es sie gibt (in der Reihenfolge des Raumplans, wenn es ihn gibt), sonst das erste Geraet der Rolle."""
    if "raum_" + role in parts["_groups"]:
        return {"group": "raum_" + role}
    gid = "rig_" + role
    if gid in parts["_groups"]:
        return {"group": gid}
    return {"fixture": parts[role][0]["name"]}


MASTER_TARGET = {"master": True}


class Tracks:
    def __init__(self):
        self.d = {}

    def tr(self, target, attr):
        return self.d.setdefault((json.dumps(target, sort_keys=True), attr), {"target": target, "attr": attr, "keys": [], "clips": []})

    def clip(self, target, attr, t, d, pattern, **p):
        self.tr(target, attr)["clips"].append({"t": t, "d": d, "pattern": pattern, "p": p})

    def key(self, target, attr, t, v, e="constant"):
        self.tr(target, attr)["keys"].append({"t": t, "v": v, "e": e})

    def out(self):
        return [t for t in self.d.values() if t["keys"] or t["clips"]]


def _dimmer(tk, target, s, name, intensity, opts, slow=False):
    """Helligkeit einer Gruppe. slow: Geraete mit traegem Dimmer (Wash) und Ambiente-Nachbarn, nie hart blinken."""
    if s is None:
        return
    t, d, lv = s["t"], s["d"], s["level"]
    base = {"intensity": intensity}
    if slow or name == "sine":
        tk.clip(target, "dimmer", t, d, "sine", start=70 if lv <= 0 else 110, end=170 if lv <= 0 else 255, speed=0.125, beat_sync=1, fade_in=min(0.3, d / 2), **base)
    elif s["kind"] == "build":
        n = 3
        for i, speed in enumerate((0.25, 0.5, 1.0 if not opts["strobe"] else 2.0)):      # immer schneller bis zum Drop
            tk.clip(target, "dimmer", t + d * i / n, d / n, "blink", start=20, end=255, speed=speed, beat_sync=1, intensity=min(1.0, intensity * (0.6 + 0.2 * i)))
    elif name == "blink":
        tk.clip(target, "dimmer", t, d, "blink", start=30, end=255, speed=1.0 if lv >= 3 else 0.5, beat_sync=1, duty=0.5, **base)
    elif name == "beat":
        tk.clip(target, "dimmer", t, d, "beat", start=40, end=255, speed=1.0, **base)
    elif name in ("running", "chase"):
        tk.clip(target, "dimmer", t, d, name, start=20, end=255, speed=0.25, beat_sync=1, **base)
    elif name == "group_wave":
        tk.clip(target, "dimmer", t, d, "group_wave", start=50, end=255, speed=0.25, beat_sync=1, spread=1.0, **base)
    else:
        tk.clip(target, "dimmer", t, d, "pulse", start=60, end=255, speed=0.5, beat_sync=1, **base)


def _color(tk, target, s):
    a, b, t, d, name = s["colors"][0], s["colors"][1], s["t"], s["d"], s["color"]
    if name == "solid_color":
        tk.clip(target, "color", t, d, "solid_color", color_a=a)
    elif name == "rgb_fade":
        tk.clip(target, "color", t, d, "rgb_fade", color_a=a, color_b=b)
    elif name in ("rainbow", "random_color"):
        tk.clip(target, "color", t, d, name, speed=0.125, beat_sync=1, spread=1.0)
    else:
        tk.clip(target, "color", t, d, name, color_a=a, color_b=b, speed=0.125, beat_sync=1, smooth=0.3)


def _laser_ktv(tk, name, s, rng):
    """KTV: der Faecher bleibt ganz offen, das Bild zoomt im Takt auf, am Hoehepunkt mit Effekt (46 und 35 haben Markus gefallen)."""
    hot = s["level"] >= 3
    tk.clip({"fixture": name}, "laser", s["t"], s["d"], "laser", ktv_group="1", ktv_effect=rng.randint(1, 42), ktv_fan=KTV_FAN_OPEN, ktv_fan_to=KTV_FAN_OPEN,
            ktv_sweep="bar" if hot else "bar2", ktv_ease="ease_out", ktv_size=KTV_ZOOM_SMALL, ktv_size_to=KTV_ZOOM_BIG, ktv_fx=rng.choice((46, 35)) if hot else 0, laser_color="bunt")


def _usable(role, parts, opts):
    st = STYLES.get(opts.get("style")) or {}
    if role == "laser":
        return bool(opts["laser"] and parts["ktv"])
    if role == "uv" and not st.get("uv", True):
        return False
    if role == "band":
        return bool(parts["preset"])
    return role in parts


def _lead(s, parts, opts, avoid=""):
    """Wer ist dran? Fehlt das Geraet oder ist es abgehakt: das naechste der Reihe."""
    want = s.get("lead")
    if want in ROLES and _usable(want, parts, opts):
        return want
    if not want:
        return ""
    start = SEQUENCE.index(want) if want in SEQUENCE else 0
    for i in range(len(SEQUENCE)):
        r = SEQUENCE[(start + i) % len(SEQUENCE)]
        if _usable(r, parts, opts) and r != avoid and r not in NOT_AT.get(s["level"], ()):
            return r
    return ""


def _play(tk, role, s, parts, opts, rng, dim_s, goboes):
    """Ein Geraet in diesem Stueck. dim_s: Stueck fuer den Dimmer (beim Drop kommt davor das Gewitter)."""
    t, d, lv = s["t"], s["d"], s["level"]
    inten = {0: 0.7, 1: 0.85, 2: 1.0, 3: 1.0}[lv]
    mv = (STYLES.get(opts.get("style")) or {}).get("mv", 1.0)
    if role == "laser":
        for f in parts["ktv"]:
            _laser_ktv(tk, f["name"], s, rng)
        return
    if role == "band":                                           # spielt nur, wenn es dran ist; Dunkel setzt render
        return
    tg = _target(parts, role)
    if role == "wash":                                           # hellen den ganzen Raum auf: immer nur dezent
        peak = int(WASH_PEAK[lv] * 255)
        tk.clip(tg, "dimmer", t, d, "sine", start=peak // 2, end=peak, speed=0.125, beat_sync=1, fade_in=min(0.3, d / 2))
        _color(tk, tg, s)
    elif role == "uv":
        _dimmer(tk, tg, dim_s, "sine", 0.6 if lv == 0 else 1.0, opts, slow=lv < 3)
    elif role == "nano":                                         # sehr hell: in ruhigen Stellen gedaempft
        _dimmer(tk, tg, dim_s, {0: "sine", 1: "pulse"}.get(lv, "group_wave"), {0: 0.45, 1: 0.65}.get(lv, inten), opts)
        _color(tk, tg, s)
    elif role == "bars":
        _dimmer(tk, tg, dim_s, s["dimmer"], inten, opts)
        _color(tk, tg, s)
        if opts["move"] and "move" in _attrs(parts["bars"]):
            tk.clip(tg, "move", t, d, s["move"] if s["move"] in ("fan", "sweep_lr") else "fan", speed=0.0625, beat_sync=1, size=0.5, spread=1.0)   # faechern nur in die Breite
    elif role == "spot":
        _dimmer(tk, tg, dim_s, "pulse" if lv < 3 else s["dimmer"], inten, opts)
        if opts["move"] and "move" in _attrs(parts["spot"]):
            tk.clip(tg, "move", t, d, s["move"], speed=0.0625 * mv, beat_sync=1, size=0.4 + 0.15 * lv)
        if goboes and "gobo" in _attrs(parts["spot"]):
            tk.key(tg, "gobo", t, goboes[s["i"] % len(goboes)])
    elif role == "fx":
        _dimmer(tk, tg, dim_s, "pulse", inten, opts)
        if "color" in _attrs(parts["fx"]):
            _color(tk, tg, s)


def _storm(tk, role, s, d, parts, flash_ok):
    """Gewitter am Drop: jedes Geraet blitzt in seinem eigenen Takt. Ohne Erlaubnis hoechstens einmal je Beat, dann begrenzt auch die Engine."""
    if role in ("wash", "laser", "band"):
        return
    tg = _target(parts, role)
    if role == "bars" and flash_ok:
        tk.clip(tg, "dimmer", s["t"], d, "strobe", start=0, end=255, speed=10.0, duty=0.25)
        return
    speed = {"spot": 2.0, "fx": 3.0, "nano": 1.5, "uv": 2.0}.get(role, 1.0) if flash_ok else 1.0
    tk.clip(tg, "dimmer", s["t"], d, "blink", start=0, end=255, speed=speed, beat_sync=1, duty=0.3)


def _nano_fx(tk, s, parts, opts, rng, state):
    """Ab und zu spielt das Nanoleaf einen seiner eigenen Effekte statt Einzelpanels. True: dieser Einsatz ist einer."""
    names = opts.get("effects") or []
    if not names or s["d"] < NANO_FX_MIN_S or s.get("swap") or s["level"] < 1:
        return False
    if state["i"] == s["i"] - 1 and state["last"]:                # laengerer Bereich: derselbe Effekt laeuft weiter
        name = state["last"]
    else:
        state["n"] += 1
        if state["n"] % NANO_FX_EVERY:
            return False
        name = rng.choice(names)
    tk.clip(_target(parts, "nano"), "nano_fx", s["t"], s["d"], "nano_effect", nano_effect=name)
    tk.tr(_target(parts, "nano"), "nano_fx")["clips"][-1]["label"] = name[:40]
    state["last"], state["i"] = name, s["i"]
    return True


def _swap(tk, a, b, s, song):
    """Hin und her im Takt: immer genau eines der zwei Geraete an, Wechsel auf jedem Beat. Je Geraet ein Blitz in zwei Beats."""
    beat, t, end, on_a = song["beat"], s["t"], s["t"] + s["d"], True
    while t < end - 0.05:
        d = min(beat, end - t)
        tk.clip(a if on_a else b, "dimmer", round(t, 3), round(d, 3), "fade_in", start=255, end=255)
        t, on_a = t + beat, not on_a


def _ambient(tk, parts, s, state):
    """Ambiente, nur mit Hakerl: steht ruhig, blinkt nie mit. Spur nur, wenn sich etwas aendert."""
    t, d, lv = s["t"], s["d"], s["level"]
    for f in parts["ambient"]:
        tg, name, attrs = {"fixture": f["name"]}, f["name"], _attrs([f])
        v = 60 if lv <= 0 else 90
        if "dimmer" in attrs and state.get(name + "d") != v:
            tk.key(tg, "dimmer", t, v)
            state[name + "d"] = v
        if "color" in attrs:
            last = state.get(name + "c")
            if last and last["p"]["color_a"] == s["colors"][0]:
                last["d"] = round(t + d - last["t"], 3)
            else:
                tk.clip(tg, "color", t, d, "solid_color", color_a=s["colors"][0])
                state[name + "c"] = tk.tr(tg, "color")["clips"][-1]


def _band(tk, parts, s, on, state):
    """Effektband: dunkel, ausser es ist dran oder beim Gewitter. Jeder Einsatz bringt ein neues Preset, eine Reihe von Peaks behaelt ihres."""
    hit = s["kind"] == "hit"
    for f in parts["preset"]:
        tg = {"fixture": f["name"]}
        v = 255 if on else 0
        fresh = on and (state.get("bd") != v or state.get("was") != s["i"] - 1)
        if hit and on and state.get("series") == s.get("series"):
            fresh = False
        if fresh:
            opt = [o["v"] for a in f["attrs"] if a["attr"] == "preset" for o in a.get("options") or [] if "♫" not in o["label"] and "Austria" not in o["label"]]
            if opt:
                state["n"] = state.get("n", -1) + 1
                tk.key(tg, "preset", s["t"], opt[(state["n"] * 7 + state.get("seed", 0)) % len(opt)])
        if hit and on:                                            # Peak: die Helligkeit setzt _accent
            state["bd"], state["series"] = 0, s.get("series")
        elif state.get("bd") != v:
            tk.key(tg, "dimmer", s["t"], v)
            state["bd"] = v
        if on:
            state["was"] = s["i"]


def _curve_keys(tk, tg, s):
    """Dimmer folgt dem Abklingen des Peaks, als Keyframes: du kannst sie von Hand nachziehen. Vorher und nachher dunkel."""
    tr = tk.tr(tg, "dimmer")
    if not tr["keys"] and s["t"] > 0:
        tk.key(tg, "dimmer", 0.0, 0)                              # eine Spur leuchtet sonst bis zum ersten Keyframe
    pts = s.get("curve") or [[0.0, 255.0], [s["d"], 0.0]]
    for i, (dt, v) in enumerate(pts):
        tk.key(tg, "dimmer", round(s["t"] + dt, 3), v, "constant" if i == len(pts) - 1 else "linear")


def _accent(tk, role, s, parts, opts, rng):
    """Peak: ein Geraet startet bei 100 % und klingt mit der Amplitude des Horns ab. Der Laser kennt keine Helligkeit: sein Bild zoomt klein, der Faecher bleibt offen."""
    t, d = s["t"], s["d"]
    if s.get("curve"):
        d = min(d, s["curve"][-1][0])                             # der Laser ist so lang wie das Horn, nicht wie das Stueck
    if role == "laser":
        for f in parts["ktv"]:
            tk.clip({"fixture": f["name"]}, "laser", t, d, "laser", ktv_group="1", ktv_effect=rng.randint(1, 42), ktv_fan=KTV_FAN_OPEN, ktv_fan_to=KTV_FAN_OPEN,
                    ktv_size=KTV_ZOOM_BIG, ktv_size_to=KTV_ZOOM_SMALL, ktv_sweep="once", ktv_ease="ease_in", laser_color="bunt")
    elif role == "band":
        for f in parts["preset"]:
            _curve_keys(tk, {"fixture": f["name"]}, s)
    else:
        tg = _target(parts, role)
        _curve_keys(tk, tg, s)
        if "color" in _attrs(parts[role]):
            _color(tk, tg, dict(s, color="solid_color"))


def room_groups(room, parts):
    """Gruppen in der Reihenfolge, wie die Geraete an der Wand haengen: Chase, Lauflicht und Gruppenwelle laufen dann wirklich
    entlang. Sortiert nach der Richtung, in der sie am weitesten auseinander stehen. Nicht eingezeichnete kommen hinten dran."""
    it = (room or {}).get("items") or {}
    out = []
    for role in ORDER_ROLES:
        fx = [f["name"] for f in parts.get(role, [])]
        placed = [n for n in fx if n in it]
        if len(placed) < 2:
            continue
        xs, ys = [it[n]["x"] for n in placed], [it[n]["y"] for n in placed]
        axis = "x" if max(xs) - min(xs) >= max(ys) - min(ys) else "y"
        order = sorted(placed, key=lambda n: (it[n][axis], it[n]["x" if axis == "y" else "y"])) + [n for n in fx if n not in it]
        base = parts["_groups"].get("rig_" + role, {})
        out.append({"id": "raum_" + role, "name": str(base.get("name") or role) + " (Raum)", "fixtures": order})
    return out


def wave_steps(room, parts):
    """Stufen einer Lichtwelle quer durch den Raum, von links nach rechts. Je Stufe die Ziele, die dort nah beieinander stehen."""
    it = (room or {}).get("items") or {}
    pts = []
    for role in WAVE_ROLES:
        if role == "nano":
            p = it.get("nanoleaf")
            if p and parts.get("nano"):
                pts.append((p["x"], _target(parts, "nano"), "color" in _attrs(parts["nano"])))
            continue
        for f in parts.get(role, []):
            if f["name"] in it and "dimmer" in _attrs([f]):
                pts.append((it[f["name"]]["x"], {"fixture": f["name"]}, "color" in _attrs([f])))
    pts.sort(key=lambda p: p[0])
    steps = []
    for x, tg, col in pts:
        if steps and x - steps[-1][0] <= WAVE_STEP_M:
            steps[-1][1].append((tg, col))
        else:
            steps.append([x, [(tg, col)]])
    return [s[1] for s in steps] if len(steps) >= WAVE_MIN_STEPS else []


def _wave(tk, s, song, steps, back):
    """Lichtwelle: Stufe fuer Stufe an und aus, auf jedem Beat eine weiter, hin und zurueck. Farbe nur, solange die Stufe leuchtet:
    eine Farbe ohne laufenden Dimmer leuchtet sonst voll."""
    seq = steps[::-1] if back else list(steps)
    seq = seq + seq[-2:0:-1]                                     # hin und zurueck, ohne die Enden doppelt
    beat, t, end, i = song["beat"], s["t"], s["t"] + s["d"], 0
    while t < end - 0.05:
        d = round(min(beat, end - t), 3)
        col = s["colors"][(i // len(seq)) % 2]
        for tg, has_color in seq[i % len(seq)]:
            tk.clip(tg, "dimmer", round(t, 3), d, "fade_in", start=255, end=255)
            if has_color:
                tk.clip(tg, "color", round(t, 3), d, "solid_color", color_a=col)
        t, i = t + beat, i + 1


def room_info(room, meta):
    """Raumplan fuer Claude: kurze Namen und Positionen in Metern."""
    it = (room or {}).get("items") or {}
    if not it:
        return None
    label = {f["name"]: f.get("label") or f["name"] for f in meta.get("fixtures", [])}
    label["nanoleaf"] = "Nanoleaf"
    out = []
    for k, v in sorted(it.items()):
        n = k.split("#")[0]
        out.append({"geraet": label.get(n, n) + (" Stueck " + k.split("#")[1] if "#" in k else ""), "x": v["x"], "y": v["y"], "laenge": v["len"]})
    return {"breite_m": room.get("w"), "tiefe_m": room.get("h"), "hinweis": "x von links, y von oben, in Metern", "geraete": out}


def render(plan, song, parts, opts, seed=0, steps=None):
    """Die Regie auf die Anlage legen. Die Schalter opts gelten hier, auch wenn Claude etwas anderes vorschlaegt."""
    rng = random.Random(seed + 1)
    tk = Tracks()
    last_fog, fogs = -1e9, 0
    flash_ok = opts["strobe"] and (STYLES.get(opts.get("style")) or {}).get("flash", True)
    goboes = [o["v"] for f in parts.get("spot", []) for a in f["attrs"] if a["attr"] == "gobo" for o in a.get("options") or []]
    amb, band, last_role, beam_at, nwave = {}, {"seed": seed}, "", None, 0
    fx_state = {"n": 0, "last": None, "i": -9}
    for s in plan:
        t, d, lv = s["t"], s["d"], s["level"]
        if opts.get("ambient"):
            _ambient(tk, parts, s, amb)
        if lv < 0:
            _band(tk, parts, s, False, band)
            continue                                             # Pause in der Musik: finster, das macht den Einsatz stark
        if lv >= 3:                                              # grosser Drop: kurz alle zusammen wie ein Gewitter
            _band(tk, parts, s, _usable("band", parts, opts), band)
            for role in ROLES:
                if _usable(role, parts, opts):
                    _storm(tk, role, s, d, parts, flash_ok)
                    _play(tk, role, s, parts, opts, rng, None, goboes)
            if opts["laser"] and s["laser"]:                     # Eyes und Derby: Laser nur am Drop
                for f in parts.get("fx", []):
                    if "laser" in _attrs([f]):
                        tk.clip({"fixture": f["name"]}, "laser", t, d, "laser", laser_pulse=1.0, duty=0.5, laser_color="bunt", laser_pattern=s["i"] % 16)
        elif s.get("lead") == "wave" and steps:                  # Lichtwelle durch den Raum
            _band(tk, parts, s, False, band)
            _wave(tk, s, song, steps, nwave % 2 == 1)
            nwave, last_role = nwave + 1, "wave"
        else:                                                    # sonst einer allein, alles andere bleibt dunkel
            role = _lead(s, parts, opts, last_role if s["kind"] != "hit" else "")
            if beam_at is not None and t < beam_at + FOG_BEAM_S and s["kind"] not in ("hit", "build") and _usable("spot", parts, opts):
                role, beam_at = "spot", None                     # nach dem Nebel: jetzt sieht man den Strahl des Vega
            last_role = role
            _band(tk, parts, s, role == "band", band)
            if s["kind"] == "hit":
                _accent(tk, role, s, parts, opts, rng)
                continue
            also = s.get("also")
            if role == "band" or role != s.get("lead") or not (also and also != role and also != "band" and _usable(also, parts, opts)):   # das Band spielt allein
                also = ""
            if role and also and s.get("swap") and role in SWAP_PLAIN and also in SWAP_PLAIN:
                _play(tk, role, s, parts, opts, rng, None, goboes)
                _play(tk, also, s, parts, opts, rng, None, goboes)
                _swap(tk, _target(parts, role), _target(parts, also), s, song)
            elif role == "nano" and _nano_fx(tk, s, parts, opts, rng, fx_state):
                if also:
                    _play(tk, also, s, parts, opts, rng, s, goboes)
            else:
                if role:
                    _play(tk, role, s, parts, opts, rng, s, goboes)
                if also:
                    _play(tk, also, s, parts, opts, rng, s, goboes)
        if opts["fog"] and s["fog"] and parts["hazer"] and t >= FOG_S + song["bar"] and t - last_fog >= FOG_GAP_S and fogs < MAX_FOG:
            for f in parts["hazer"]:                              # Schub vor dem Drop, Grenzen wie beim Nebel-Knopf
                tk.clip({"fixture": f["name"]}, "fog", t - FOG_S - song["bar"], FOG_S, "fog_burst")
            last_fog, fogs, beam_at = t, fogs + 1, t
    if song.get("fade"):                                          # Ausklang: der Master folgt dem Pegel der Wellenform
        for ti, v in song["fade"][1]:
            tk.key(MASTER_TARGET, "master", ti, v, "linear")
    calm = {f["name"] for f in parts["ambient"] + parts["preset"]}
    return sorted(tk.out(), key=lambda t: t["target"].get("fixture") in calm)   # Ambiente unten: oben steht, woran du feilst


def suggest(doc, meta, opts, peaks=None, refine=None, stems=None, room=None):
    """Vorschlag: gibt (neues Dokument, Plan, Liedinfo) zurueck. refine(plan, song) kann die Regie umstellen (Claude).
    room: gespeicherter Raumplan, dann laufen Gruppen in der Reihenfolge an der Wand, und es gibt Lichtwellen durch den Raum."""
    seed = int(opts.get("seed") or 0)
    song = song_info(doc, peaks, stems)
    song["room"] = room_info(room, meta)
    parts = rig_parts(meta)
    groups = room_groups(room, parts)
    for g in groups:
        parts["_groups"][g["id"]] = g
    steps = wave_steps(room, parts)
    plan = direct(song, opts.get("style"), float(opts.get("wild", 0.5)), seed, bool(steps))
    if refine:
        plan = refine(plan, song)
    own = [g for g in doc.get("groups") or [] if not str(g.get("id", "")).startswith("raum_")]
    new = dict(doc, tracks=render(plan, song, parts, opts, seed, steps), groups=own + groups, scene_clips=[], scenes=[])
    return new, plan, song


# ---- Claude als Zusatz ---------------------------------------------------------------------------------------------------
SYSTEM = """Du bist ein erfahrener Lichtdesigner fuer Partys. Du bekommst den Aufbau eines Liedes und einen fertigen Vorschlag fuer die Lichtregie, Stueck fuer Stueck.
Verbessere die Regie: Spannungsbogen ueber das ganze Lied, Abwechslung zwischen gleichen Abschnitten, Farben passend zu Genre und Titel, starke Hoehepunkte, ruhige Stellen wirklich ruhig.
Wichtig: lead ist das eine Geraet, das in diesem Stueck allein spielt, alles andere ist dunkel. Der Reihe nach, zum Beispiel spot, nano, band, bars, laser, fx, nie zweimal dasselbe hintereinander. uv allein ist zu dunkel. also ist ein zweites Geraet dazu, nur wenn es zur Musik passt und selten (sonst leer), sonst wird es eine helle Einheitssuppe. swap true: lead und also schalten jeden Beat hin und her (nur spot, nano, bars, fx). starke_peaks sind laute Ereignisse aus der Wellenform: [Zeit, Dauer, Staerke]. Sie sind die Stuecke mit kind hit: dort startet ein Geraet (lead) bei 100 % und klingt mit der Amplitude ab, dazwischen ist es finster. Eine Reihe von Peaks gehoert demselben Geraet. lautstaerke_je_takt zeigt den Verlauf. lead wave ist eine Lichtwelle durch den Raum (Geraete der Reihe nach, nur mit Raumplan); lass sie stehen oder ersetze sie durch ein Geraet. spuren_je_takt (wenn vorhanden): Pegel von Stimme, Bass, Kick, Snare/Hi-Hat und Sonstigem je Takt, 0 bis 100, aus der getrennten Musik; ohne Kick ist es ruhig, kommt sie zurueck, ist das ein Einsatz. ausblenden_ab: dort blendet der Master das Licht automatisch mit dem Pegel aus, plane dort ruhig und ohne Laser. Lange Bereiche mit demselben Geraet sind erwuenscht, wenn die Musik sie traegt, zwischen den schnellen Wechseln. Die Washes (wash) erhellen den ganzen Raum: sparsam einsetzen. Alle zusammen gibt es nur kurz an den grossen Drops.
level: -1 dunkel, 0 ruhig, 1 mittel, 2 Hauptteil, 3 nur beim Drop. Halte dich an die erlaubten Werte. Der Wunsch des Nutzers geht vor, soweit er mit den erlaubten Werten machbar ist.
Gib nur Stuecke zurueck, die du aenderst. Fasse in note in ein bis zwei deutschen Saetzen zusammen, was du geaendert hast und warum."""


def _schema():
    return {"type": "object", "additionalProperties": False, "required": ["note", "segments"], "properties": {
        "note": {"type": "string"},
        "segments": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                "required": ["i", "level", "lead", "also", "swap", "colors", "dimmer", "color", "move", "laser", "fog"], "properties": {
                                                    "i": {"type": "integer"}, "level": {"type": "integer"}, "lead": {"type": "string", "enum": list(ROLES)}, "also": {"type": "string", "enum": list(ROLES) + [""]}, "swap": {"type": "boolean"}, "colors": {"type": "array", "items": {"type": "string"}},
                                                    "dimmer": {"type": "string", "enum": list(DIMMERS)}, "color": {"type": "string", "enum": list(COLORS)},
                                                    "move": {"type": "string", "enum": list(MOVES)}, "laser": {"type": "boolean"}, "fog": {"type": "boolean"}}}}}}


def _per_bar(song):
    """Lautstaerke je Takt, 0..100, damit Claude den Verlauf kennt. Das ist alles von der Musik, was das Haus verlaesst."""
    v, n = song.get("loud") or [], max(1, round(song["bar"] / song["beat"]))
    top = max(v) if v else 1.0
    return [int(sum(v[i:i + n]) / len(v[i:i + n]) * 100 / top) for i in range(0, len(v), n)][:600]


def _stems_per_bar(song):
    """Die fuenf Spuren grob, ein Wert je Takt 0..100 (Spitzenpegel). Leer ohne Kurven."""
    sb = song.get("sb") or {}
    if not sb:
        return {}
    n = max(1, round(song["bar"] / song["beat"]))
    return {k: [int(max(0.0, min(100.0, (max(sb[k][i:i + n]) + 60.0) * 100 / 60.0))) for i in range(0, len(sb[k]), n)][:600] for k in STEM_KEYS}


ROOM = ("Raum: Die 4 Docooler sind sehr wirkungsvoll und faechern nur in die Breite. In ihrer Mitte haengen der Vega (Moving Head) und der KTV-Laser; "
        "den Vega sieht man kaum, nur mit Nebel als Strahl, sonst projiziert er sein Gobo an die Wand gegenueber. Die 4 Washes haengen oben an einer Wand "
        "und leuchten auf das Nanoleaf darunter, das ist eine Wand. Ein Segment des Effektbands haengt darueber, das andere gegenueber. UV in der Mitte, "
        "Eyes, Barlicht und Derby in den Ecken.")


def claude_request(plan, song, opts, wish):
    """Was an Anthropic geht: Titel, Genre, Tempo, Aufbau und Lautstaerke je Takt. Keine Musik, keine Adressen, nichts vom Heimnetz."""
    user = {"titel": song["title"], "genre": song["genre"], "energiestufe": song["lvl"], "stil": opts.get("style") or "", "wunsch": str(wish or "")[:500],
            "erlaubt": {k: bool(opts[k]) for k in ("laser", "fog", "strobe", "move")},
            "ausblenden_ab": (song.get("fade") or [None])[0], "starke_peaks": [h[:3] for h in song.get("hits", [])][:64], "lautstaerke_je_takt": _per_bar(song), "spuren_je_takt": _stems_per_bar(song), "raum": ROOM, "raumplan": song.get("room"), "stuecke": [{k: s[k] for k in ("i", "t", "d", "kind", "level", "lead", "also", "swap", "colors", "dimmer", "color", "move", "laser", "fog")} for s in plan]}
    return {"model": MODEL, "max_tokens": 16000, "system": SYSTEM, "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": _schema()}},
            "fallbacks": "default", "messages": [{"role": "user", "content": json.dumps(user, ensure_ascii=False)}]}


DESIGN_SYSTEM = """Du bist ein professioneller Lichtdesigner fuer Partys und programmierst eine komplette Lichtshow zu einem Lied. Du bekommst die Anlage mit allem, was sie kann, die Analyse des Liedes und vielleicht den Liedtext. Du entwirfst selbst: welches Geraet wann spielt, Farben, Muster, Bewegung.

So will der Besitzer der Anlage seine Shows, das hat er ausdruecklich gesagt:
- Eine Show ist zur Musik gestaltet: ein Geraet nach dem anderen, sinnvoll im Takt abwechselnd. Ein Geraet ein paar Sekunden allein, bis es fad wird, alles andere finster. Wechsel genau auf einem Beat, nie asynchron.
- Nie staendig alle Geraete zugleich, das ist eine helle Einheitssuppe. Wenn es zu einer Stelle passt, duerfen zwei oder mehr zusammen spielen. Auch schnelles Hin und Her zwischen zwei Geraeten im Takt ist gut.
- Alle zusammen wie ein Gewitter nur kurz am grossen Drop (drops), etwa 2 Takte.
- Starke Peaks in der Wellenform (peaks, zum Beispiel Bass oder Schiffshorn) mit einem Effekt betonen: Dimmer-Keyframes aus der mitgegebenen Kurve des Peaks, Start bei 100 %, dann mit der Amplitude abklingen. Eine Reihe von Peaks gehoert einem Geraet, die naechste Reihe einem anderen. Peaks muessen im Raum wirken: nimm helle Geraete wie Effektband, Docooler, Nanoleaf oder den Laser; der Vega allein ist dafuer zu schmal und darf nicht alle Peaks bekommen. Dazwischen ist es bei dichten Peaks finster, nichts anderes laeuft dann. Vorbild aus der Show des Besitzers zu Titanium: Effektband bei den Hoernern am Anfang (bis Sekunde 38), Laser von 38 bis 65 auf jedem Horn, Docooler mit schnellem Blinken und Abklingen auf einzelnen Stoessen.
- WICHTIG: Ein Farb-Clip ohne gleichzeitig laufenden Dimmer leuchtet mit voller Helligkeit. Eine Farbe also nie laenger als den Dimmer legen. Die UV-Leiste nur kurz einsetzen, nie dauernd.
- Die Washes erhellen den ganzen Raum: sparsam, hoechstens 40 % (end hoechstens 100), ihr Dimmer ist traege: nur weiche Muster wie sine, fade_in, fade_out, nie strobe, blink oder beat.
- Das Effektband (einzelgeraete, rolle "Effektband") gehoert fest zur Show und ist kein Ambiente: Es braucht zwei Spuren, dimmer (Keyframes, 0 = aus) und preset (Keyframes mit v aus werte, e constant). Es hat nicht dauernd einen Effekt: dunkel, und im Einsatz, wenn in der Musik etwas passiert. Auch in der Reihe der Geraete darf es dran sein.
- Jedes Geraet der Anlage kommt im Lauf des Liedes vor, keines bleibt die ganze Zeit dunkel: Vega, Docooler, Effektband, Laser, Nanoleaf, Eyes und Derby, Washes, UV. Nur das Ambiente (rolle "Ambiente": Barlicht, Theke, Couchtisch) laeuft nur, wenn erlaubt.ambient wahr ist.
- Es darf auch laengere Bereiche geben, nicht nur Wechsel im Sekundentakt. Abwechslung und eigene Ideen sind erwuenscht, gerade bei den Farben: passend zu Titel, Text, Genre und Stimmung, nicht immer dieselben zwei.
- Nanoleaf-Effekte (Spur nano_fx) sind schoen, aber nur ab und zu und nicht kuerzer als 3 s. Szenen aus dem Panel (panel_scenes) sind erprobt und duerfen fuer laengere Bereiche verwendet werden.
- liedzeilen sind [Sekunden, Zeile], wenn bekannt: Daran siehst du, wann welche Zeile kommt und wo sich der Refrain wiederholt. Lichtwechsel und starke Momente duerfen genau dorthin, und Farben duerfen zum Text passen. Fehlen sie, zaehlen nur Aufbau und liedtext.
- Wird das Lied am Schluss leiser (fade), blendet das Licht dort aus; plane dort ruhig und ohne Laser.
- Ein Laser leuchtet die ganze Clip-Dauer, ohne Helligkeit: kurz und gezielt einsetzen.
- KTV-Laser: den Faecher (ktv_fan und ktv_fan_to) immer ganz offen lassen, 255. Bewegung entsteht ueber den Zoom (ktv_size bis ktv_size_to, 0 = gross, 255 = klein), zum Beispiel bei einem Peak von gross nach klein.
- raumplan (wenn vorhanden) sind die Positionen der Geraete in Metern. Damit kannst du Licht durch den Raum wandern lassen: Geraete der Reihe nach von einer Seite zur anderen an- und ausschalten, eine Lichtwelle, auf dem Beat.
- raum beschreibt, wo die Geraete haengen und wie sie wirken. Nutze das: zum Beispiel die Docooler nur waagrecht bewegen, den Vega nach einem Nebelschub fuer seinen Strahl.
- spuren_je_takt (wenn vorhanden) sind die Pegel von Stimme, Bass, Kick, Snare/Hi-Hat und Sonstigem je Takt, 0 bis 100, aus der getrennten Musik. Ohne Kick ist es eine ruhige Stelle, wird Snare/Hi-Hat lauter, baut es auf, kommt die Kick zurueck, ist das ein Einsatz. Gesang an ruhigen Stellen passt zu ruhigem Licht.

Technik:
Antworte nur mit einem JSON-Objekt, ohne Text davor oder danach: {"note": "ein bis zwei deutsche Saetze, was du dir ueberlegt hast", "tracks": [...]}
Eine Spur: {"target": {"group": "<id>"} oder {"fixture": "<name>"} oder {"panel": true} oder {"master": true}, "attr": "<aus rig>", "keys": [{"t": Sekunden, "v": Wert, "e": "linear" oder "constant"}], "clips": [{"t": Sekunden, "d": Dauer, "pattern": "<aus patterns>", "p": {Parameter}}]}
Je Ziel und attr eine Spur. Ein Clip passt nur auf eine Spur, deren Art seinem out entspricht. Keyframe-Werte: Dimmer 0 bis 255; eine Spur mit Keyframes haelt ihren ersten Wert auch vor dem ersten Keyframe, beginne also mit v 0, wenn es davor dunkel sein soll, und ende mit v 0 und e constant. Ohne Clip und ohne Keyframe ist ein Geraet dunkel. Beats liegen bei beat_offset + n * 60 / bpm. Zeiten mit hoechstens 3 Nachkommastellen. Bleib unter 30000 Zeichen Antwort je Minute Lied: lieber klare Clips als sehr viele kleine.
Nicht erlaubte Effekte (siehe erlaubt) und unbekannte Werte werden vom Pi verworfen."""
DESIGN_ATTRS = ("dimmer", "color", "move", "preset", "gobo", "colorwheel", "laser", "fog", "nano_fx")
MAX_LYRICS = 20000
WASH_MAX = 102.0              # Washes hoechstens 40 %: sie hellen den ganzen Raum auf


def _attr_info(attrs):
    out = []
    for x in attrs:
        if x["attr"] in DESIGN_ATTRS:
            e = {"attr": x["attr"], "art": x.get("kind")}
            if x.get("options"):
                e["werte"] = [{"v": o["v"], "name": o["label"]} for o in x["options"] if "♫" not in o["label"]]
            out.append(e)
    return out


def _role_name(f):
    """Wofuer ein Geraet in der Show da ist. Das Effektband steht in der Gruppe ambient, spielt aber mit."""
    if any(a["attr"] == "preset" for a in f["attrs"]):
        return "Effektband"
    return {"ambient": "Ambiente", "bars": "Docooler", "wash": "Wash", "spot": "Vega", "fx": "Effekt", "uv": "UV", "locked": "Laser" if any(a["attr"] == "laser" for a in f["attrs"]) else "Nebel"}.get(f.get("group"), str(f.get("group") or ""))


def _band_fill(meta, song):
    """Hat Claude das Effektband vergessen: an Drops und Cues kurz einsetzen, ohne Soundeffekte, sonst bleibt es dunkel."""
    out = []
    for f in meta["fixtures"]:
        opt = [o["v"] for a in f["attrs"] if a["attr"] == "preset" for o in a.get("options") or [] if "♫" not in o["label"] and "Austria" not in o["label"]]
        if not opt:
            continue
        hits = sorted({round(x, 3) for x in song["drops"]} | {round(c, 3) for c in song["cues"] if c > 0})
        hits = [h for i, h in enumerate(hits) if h < song["dur"] and not any(0 < h - x < song["bar"] * 2 for x in hits[:i])]
        dim, pre = [{"t": 0.0, "v": 0, "e": "constant"}], []
        for i, h in enumerate(hits):
            pre.append({"t": h, "v": opt[(i * 7) % len(opt)], "e": "constant"})
            dim.append({"t": h, "v": 255, "e": "linear"})
            dim.append({"t": round(min(h + song["bar"] * 2, song["dur"]), 3), "v": 0, "e": "constant"})
        if hits:
            out.append({"target": {"fixture": f["name"]}, "attr": "dimmer", "keys": dim, "clips": []})
            out.append({"target": {"fixture": f["name"]}, "attr": "preset", "keys": pre, "clips": []})
    return out


def design_request(doc, meta, song, opts, wish, lyrics):
    """Alles, was ein Lichtdesigner wissen muss. Keine Musik, keine Adressen, nichts vom Heimnetz."""
    fx_by = {f["name"]: f for f in meta["fixtures"]}
    groups = []
    for g in meta["groups"]:
        attrs = {}
        for n in g["fixtures"]:
            for x in _attr_info(fx_by[n]["attrs"]) if n in fx_by else []:
                attrs.setdefault(x["attr"], x)
        groups.append({"id": g["id"], "name": g["name"], "geraete": [fx_by[n]["label"] for n in g["fixtures"] if n in fx_by], "spuren": list(attrs.values())})
    single = [{"name": f["name"], "label": f["label"], "rolle": _role_name(f), "spuren": _attr_info(f["attrs"])} for f in meta["fixtures"] if f.get("group") != "nano"]
    pats = [{"key": p["key"], "name": p["label"], "out": p["out"], "params": {k: {x: meta["params"][k].get(x) for x in ("label", "lo", "hi") if meta["params"][k].get(x) is not None} for k in p["params"] if k in meta["params"]}}
            for p in meta["patterns"] if p["out"] in ("scalar", "color", "move", "laser", "fog", "nano_fx", "panel")]
    user = {"titel": song["title"], "genre": song["genre"], "energiestufe": song["lvl"], "stil": opts.get("style") or "", "wunsch": str(wish or "")[:1000], "liedtext": str(lyrics or (doc.get("lyrics") or {}).get("plain") or "")[:MAX_LYRICS],
            "liedzeilen": ((doc.get("lyrics") or {}).get("lines") or [])[:600],
            "bpm": doc.get("bpm"), "beat_offset": doc.get("beat_offset"), "takt": doc.get("beats_per_bar"), "dauer": song["dur"],
            "abschnitte": song["secs"], "cues": song["cues"], "drops": song["drops"], "peaks": [{"t": h[0], "d": h[1], "staerke": h[2], "kurve": h[3] if len(h) > 3 else []} for h in song["hits"]],
            "fade": song["fade"], "lautstaerke_je_takt": _per_bar(song), "spuren_je_takt": _stems_per_bar(song), "raum": ROOM, "raumplan": song.get("room"), "erlaubt": {k: bool(opts.get(k)) for k in ("laser", "fog", "strobe", "move", "ambient")},
            "rig": {"gruppen": groups, "einzelgeraete": single, "panel_scenes": opts.get("panel_scenes") or [], "nanoleaf_effekte": opts.get("effects") or []}, "patterns": pats}
    return {"model": MODEL, "max_tokens": 64000, "stream": True, "system": DESIGN_SYSTEM, "output_config": {"effort": "high"}, "fallbacks": "default",
            "messages": [{"role": "user", "content": json.dumps(user, ensure_ascii=False)}]}


def _trim_colors(tracks):
    """Farbe ohne laufenden Dimmer leuchtet in der Engine voll: So war die UV-Leiste die ganze Show an. Bei Claude gilt Farbe nur, wo auch ein
    Dimmer-Clip laeuft. Eine Dimmer-Spur mit Keyframes gilt immer, sie setzt auch 0. Ohne Dimmer-Spur faellt die Farbe weg. Gibt die Zahl der Streichungen."""
    gone = 0
    for tr in tracks:
        if tr["attr"] != "color" or not tr["clips"]:
            continue
        dim = next((x for x in tracks if x["attr"] == "dimmer" and x["target"] == tr["target"]), None)
        if dim is not None and dim["keys"]:
            continue
        spans = []
        for c in sorted(dim["clips"] if dim else [], key=lambda c: c["t"]):
            if spans and c["t"] <= spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], c["t"] + c["d"])
            else:
                spans.append([c["t"], c["t"] + c["d"]])
        keep = []
        for c in tr["clips"]:
            parts = [(max(c["t"], a_), min(c["t"] + c["d"], b)) for a_, b in spans if max(c["t"], a_) < min(c["t"] + c["d"], b)]
            if not parts:
                gone += 1
            keep.extend(dict(c, t=round(x, 3), d=round(y - x, 3)) for x, y in parts if y - x >= 0.05)
        tr["clips"] = keep
    return gone


def apply_design(doc, answer, meta, song, opts):
    """Antwort von Claude pruefen: nur bekannte Ziele, Spuren, Muster und Werte, die Hakerl gelten. Was nicht passt, faellt weg. Gibt (Spuren, verworfen)."""
    if not isinstance(answer, dict) or not isinstance(answer.get("tracks"), list):
        raise ValueError("Claude: keine Spuren in der Antwort")
    fx_by = {f["name"]: f for f in meta["fixtures"]}
    groups = {g["id"]: g for g in meta["groups"]}
    seen, out, dropped = {}, [], 0
    dur = song["dur"]
    fogs = []
    for tr in answer["tracks"]:
        if not isinstance(tr, dict) or not isinstance(tr.get("target"), dict):
            dropped += 1
            continue
        tg, attr = tr["target"], tr.get("attr")
        is_wash = False
        if tg.get("master"):
            target, attr, kinds = {"master": True}, "master", "scalar"
        elif tg.get("panel"):
            target, attr, kinds = {"panel": True}, "panel_scene", "panel"
        else:
            names = groups[tg["group"]]["fixtures"] if tg.get("group") in groups else [tg.get("fixture")] if tg.get("fixture") in fx_by else []
            have = {x["attr"]: x for n in names if n in fx_by for x in fx_by[n]["attrs"]}
            if attr not in DESIGN_ATTRS or attr not in have or (attr == "laser" and not opts.get("laser")) or (attr == "fog" and not opts.get("fog")) or (attr == "move" and not opts.get("move")):
                dropped += 1
                continue
            roles = {_role_name(fx_by[n]) for n in names if n in fx_by}
            if not opts.get("ambient") and roles == {"Ambiente"} or (not opts.get("ambient") and tg.get("group") == "rig_ambient"):
                dropped += 1
                continue
            is_wash = roles == {"Wash"}
            target, kinds = ({"group": tg["group"]} if tg.get("group") in groups else {"fixture": tg["fixture"]}), have[attr].get("kind", "scalar")
        res = seen.get((json.dumps(target, sort_keys=True), attr))
        if res is None:
            res = seen[(json.dumps(target, sort_keys=True), attr)] = {"target": target, "attr": attr, "keys": [], "clips": []}
            out.append(res)
        for k in tr.get("keys") or []:
            try:
                t = float(k["t"])
                if kinds in ("laser", "fog", "nano_fx", "panel") or not 0 <= t <= dur:
                    raise ValueError
                res["keys"].append({"t": round(t, 3), "v": min(float(k["v"]), WASH_MAX) if is_wash and attr == "dimmer" else k["v"], "e": k.get("e", "linear")})
            except (KeyError, TypeError, ValueError):
                dropped += 1
        for c in tr.get("clips") or []:
            try:
                key, t, d = c["pattern"], float(c["t"]), float(c["d"])
                reg = pt.REGISTRY[key]
                p = pt.clean_params(key, c.get("p") or {})
                ok = reg["out"] == kinds and 0 <= t < dur and d > 0
                ok = ok and not (key == "strobe" and not opts.get("strobe"))
                if is_wash and attr == "dimmer":              # Washes bleiben dezent, ihr Dimmer ist zu traege zum Blitzen
                    ok = ok and key not in ("strobe", "blink", "beat", "chase")
                    p["end"] = min(float(p.get("end", 255)), WASH_MAX)
                    p["start"] = min(float(p.get("start", 0)), WASH_MAX)
                ok = ok and not (key == "panel_scene" and p.get("panel_scene") not in (opts.get("panel_scenes") or []))
                ok = ok and not (key == "nano_effect" and p.get("nano_effect") not in (opts.get("effects") or []))
                if ok and kinds == "fog":
                    d = min(d, FOG_S)
                    ok = len(fogs) < MAX_FOG and all(abs(t - x) >= FOG_GAP_S for x in fogs)
                    if ok:
                        fogs.append(t)
                if not ok:
                    raise ValueError
                res["clips"].append({"t": round(t, 3), "d": round(min(d, dur - t), 3), "pattern": key, "p": p, "label": str(c.get("label") or "")[:40]})
            except (KeyError, TypeError, ValueError):
                dropped += 1
    dropped += _trim_colors(out)
    good = [x for x in out if x["keys"] or x["clips"]]
    if not [x for x in good if "master" not in x["target"]]:
        raise ValueError("Claude: keine brauchbaren Spuren in der Antwort")
    bands = {f["name"] for f in meta["fixtures"] if _role_name(f) == "Effektband"}
    if bands and not any(x["target"].get("fixture") in bands and (x["keys"] or x["clips"]) for x in good):
        fill = _band_fill(meta, song)
        good.extend(fill)
        answer["_band_filled"] = bool(fill)
    if song["fade"] and not any("master" in x["target"] for x in good):   # das Ausblenden am Schluss bleibt sicher dabei
        good.append({"target": dict(MASTER_TARGET), "attr": "master", "keys": [{"t": a_, "v": v, "e": "linear"} for a_, v in song["fade"][1]], "clips": []})
    return good, dropped


def add_usage(usage, u):
    """Tokens aus einer Antwort dazuzaehlen. Fehlt die Angabe, bleibt die Schaetzung eben kleiner."""
    if usage is None or not isinstance(u, dict):
        return
    for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        if isinstance(u.get(k), (int, float)):
            usage[k] = u[k]                                       # die API meldet Summen, nicht Stuecke


def cost_usd(usage):
    """Geschaetzte Kosten in Dollar. Die Abrechnung steht auf platform.claude.com."""
    return ((usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0)) * PRICE_IN
            + usage.get("output_tokens", 0) * PRICE_OUT) / 1e6


def stream_claude(key, body, on_chars=None, deadline_s=900.0, timeout=180.0, opener=urllib.request.urlopen, usage=None):
    """Lange Antwort stueckweise lesen. Wirft ValueError mit einer Meldung fuers Panel; der Schluessel steht nie in einer Meldung."""
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": API_VERSION, "anthropic-beta": "server-side-fallback-2026-07-01"})
    start, text, stop = time.time(), [], None
    n = 0
    try:
        with opener(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == "message_start":
                    add_usage(usage, (ev.get("message") or {}).get("usage"))
                elif kind == "message_delta":
                    add_usage(usage, ev.get("usage"))
                if kind == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                    text.append(ev["delta"].get("text", ""))
                    n += len(text[-1])
                    if on_chars:
                        on_chars(n)
                elif kind == "message_delta":
                    stop = (ev.get("delta") or {}).get("stop_reason") or stop
                elif kind == "error":
                    raise ValueError(f"Claude: {str((ev.get('error') or {}).get('type') or 'Fehler')[:60]}")
                if time.time() - start > deadline_s:
                    raise ValueError("Claude: dauert zu lange")
    except urllib.error.HTTPError as e:
        raise ValueError({401: "Claude: Schluessel ungueltig", 402: "Claude: kein Guthaben", 429: "Claude: gerade ueberlastet oder Limit erreicht"}.get(e.code, f"Claude: Fehler {e.code}")) from None
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"Claude nicht erreichbar ({type(e).__name__})") from None
    if stop == "refusal":
        raise ValueError("Claude hat abgelehnt")
    if stop == "max_tokens":
        raise ValueError("Claude: Antwort zu lang")
    s = "".join(text)
    a_, b = s.find("{"), s.rfind("}")
    try:
        return json.loads(s[a_:b + 1])
    except ValueError:
        raise ValueError("Claude: Antwort nicht lesbar") from None


def ask_claude(key, body, timeout=120.0, opener=urllib.request.urlopen, usage=None):
    """Einmal fragen. Wirft ValueError mit einer Meldung fuers Panel; der Schluessel steht nie in einer Meldung."""
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": API_VERSION, "anthropic-beta": "server-side-fallback-2026-07-01"})
    try:
        with opener(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise ValueError({401: "Claude: Schluessel ungueltig", 402: "Claude: kein Guthaben", 429: "Claude: gerade ueberlastet oder Limit erreicht"}.get(e.code, f"Claude: Fehler {e.code}")) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ValueError(f"Claude nicht erreichbar ({type(e).__name__})") from None
    add_usage(usage, data.get("usage"))
    if data.get("stop_reason") == "refusal":
        raise ValueError("Claude hat abgelehnt")
    if data.get("stop_reason") == "max_tokens":
        raise ValueError("Claude: Antwort zu lang")
    text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
    try:
        return json.loads(text)
    except ValueError:
        raise ValueError("Claude: Antwort nicht lesbar") from None
