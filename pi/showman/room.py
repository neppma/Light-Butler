#!/usr/bin/env python3
"""
room.py - Raumplan: wo die Geraete im Partyraum stehen (Seite /raum, Beschreibung in docs/RAUM.md).

Nur Anzeige und Grundlage fuer spaetere Regeln, aufs Licht wirkt der Plan nicht.
Gespeichert in raum.json im Programmordner (Zustandsdatei: deploy.sh schliesst *.json aus, die Sicherung nimmt sie mit).

Ein Eintrag je Geraet, Schluessel = Name aus der Anlage. Weitere Stuecke desselben Geraets (zum Beispiel das zweite Segment des
Effektbands) heissen NAME#2, NAME#3. x und y in Metern ab der linken oberen Ecke, rot in Grad (0 = nach rechts), len in Metern
(0 = Punkt, sonst eine Linie wie ein LED-Band).
"""
import json
import os
import re

from .store import write_json

KEY_RE = re.compile(r"^([A-Za-z0-9_.\-]{1,40})(#[2-9])?$")
SIZE_MIN, SIZE_MAX = 1.0, 40.0
EXTRA = [{"name": "nanoleaf", "label": "Nanoleaf", "short": "Nanoleaf", "group": "nano", "line": False}]
SHORT_GROUP = {"bars": "Spider", "wash": "Wash", "spot": "Moving Head", "uv": "UV"}
SHORT_NAME = {"eyes": "Eyes", "derby": "Derby", "par": "Barlicht", "laser": "KTV-Laser", "hazer": "Hazer", "effektband": "Effektband",
              "theke": "Theke", "couchtisch": "Couchtisch"}    # kein DMX-Geraet, haengt aber im Raum

# Erster Vorschlag aus der Beschreibung von Markus (05.11.2026), 8 x 5 m, von ihm in der Vorschau korrigiert (gespiegelt): Docooler an
# der schmalen Wand links, Vega und KTV in ihrer Mitte, Washes und Nanoleaf an der langen Wand oben, Effektband an beiden langen
# Waenden ueber die ganzen 8 m (Band 1 unten, Band 2 oben), UV in der Mitte, Eyes, Barlicht und Derby rechts. Er zieht die Geraete
# danach an ihren Platz.
DEFAULT = {
    "docooler_1": (0.2, 4.2), "docooler_2": (0.2, 3.4), "docooler_5": (0.2, 1.6), "docooler_6": (0.2, 0.8),
    "vega": (0.4, 2.7), "laser": (0.4, 2.2),
    "rgbuv_7": (5.0, 0.25), "rgbuv_8": (4.4, 0.25), "rgbuv_10": (3.8, 0.25), "rgbuv_11": (3.2, 0.25), "nanoleaf": (4.1, 0.7),
    "uv_bar": (4.0, 2.5), "eyes": (7.7, 0.3), "par": (7.7, 4.7), "derby": (6.7, 4.7),
}
DEFAULT_LINES = {"effektband": (4.0, 4.95, 0.0, 8.0), "effektband#2": (4.0, 0.05, 0.0, 8.0)}   # Band 1 unten, Band 2 oben


def devices(rig):
    """Alles, was im Raum stehen kann. line: LED-Band, wird als Linie gezeichnet."""
    out = []
    for fx in rig.fixtures:
        if fx.group == "nano":
            continue                                             # Einzelpanels nicht: das Nanoleaf steht als Ganzes im Plan
        line = fx.type.startswith("wled")                      # LED-Streifen: Effektband, Theke, Couchtisch
        label = fx.extra.get("label", fx.name)
        short = SHORT_NAME.get(fx.name) or SHORT_GROUP.get(fx.group) or label.split(" (")[0][:16]
        if fx.group in ("bars", "wash") and fx.extra.get("nr"):
            short += " " + str(fx.extra["nr"])                   # mehrere gleiche: mit Nummer
        out.append({"name": fx.name, "label": label, "short": short, "nr": fx.extra.get("nr"), "group": fx.group, "line": line})
    return out + [dict(e) for e in EXTRA if e["name"] not in {f.name for f in rig.fixtures}]


def default(names):
    items = {}
    for k, (x, y) in DEFAULT.items():
        if k in names:
            items[k] = {"x": x, "y": y, "rot": 0.0, "len": 0.0}
    for k, (x, y, r, n) in DEFAULT_LINES.items():
        if k.split("#")[0] in names:
            items[k] = {"x": x, "y": y, "rot": r, "len": n}
    return {"v": 1, "w": 8.0, "h": 5.0, "items": items, "guess": True}


def _num(v, lo, hi, dflt):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return dflt
    if f != f:                                                   # NaN
        return dflt
    return round(max(lo, min(hi, f)), 3)


def clean(data, names):
    """Kommt aus dem Browser: nur bekannte Geraete, Zahlen in Grenzen, alles andere faellt weg."""
    if not isinstance(data, dict):
        raise ValueError("Raumplan: falsches Format")
    w, h = _num(data.get("w"), SIZE_MIN, SIZE_MAX, 8.0), _num(data.get("h"), SIZE_MIN, SIZE_MAX, 5.0)
    items = {}
    for k, it in (data.get("items") or {}).items() if isinstance(data.get("items"), dict) else []:
        m = KEY_RE.match(str(k))
        if not m or m.group(1) not in names or not isinstance(it, dict):
            continue
        items[k] = {"x": _num(it.get("x"), 0.0, w, w / 2), "y": _num(it.get("y"), 0.0, h, h / 2),
                    "rot": round(_num(it.get("rot"), -720.0, 720.0, 0.0) % 360.0, 1), "len": _num(it.get("len"), 0.0, max(w, h), 0.0)}
    return {"v": 1, "w": w, "h": h, "items": items, "guess": bool(data.get("guess", False))}


def load(path, names):
    try:
        with open(path, encoding="utf-8") as f:
            return clean(json.load(f), names)
    except (OSError, ValueError):
        return default(names)


def save(path, data, names):
    room = clean(dict(data, guess=False) if isinstance(data, dict) else data, names)
    write_json(path, room)
    return room


def room_path():
    return os.environ.get("S2L_ROOM_FILE") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raum.json")
