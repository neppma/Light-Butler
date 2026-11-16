#!/usr/bin/env python3
"""
lumi_view.py - Daten fuer die Seite "ROLI Lumi · Belegung" (/lumi): alle Tasten mit aktueller Belegung (inklusive
lumimap.json) und die zuletzt gedrueckten Tasten. Nur zum Ansehen; geschaltet wird hier nichts.
"""
from apc_view import CSS
from lumi_ctl import BLACK, COLORS, LUMI_CMDS, LumiController, lumi_scenes
from midi_ctl import MIX_ORDER, MOVE_ORDER

KEYS_ON_DEVICE = 24
KIND_CSS = {"speed": "#2e9e4a", "move": "#2b7fd6", "mix": "#8a2fe0", "fx": "#f07800", "blackout": "#8a1414", "scene": "#12a59a",
            "aim": "#c9b52a"}


def controller(show):
    """Der laufende Controller, sonst ein Ersatz nur fuer die Anzeige (ohne MIDI, ohne Thread)."""
    lc = getattr(show, "lumi", None)
    if lc is None:
        lc = getattr(show, "_lumi_view", None)
        if lc is None:
            lc = LumiController(show, "lumimap.json")
            show._lumi_view = lc
    return lc


def kind_of(act):
    if not act:
        return ""
    if act.get("cmd") == "blackout":
        return "blackout"
    if "cmd" in act:
        return "fx"
    if "scene" in act or "scene_index" in act:
        return "scene"
    return next((k for k in ("color", "speed", "move", "mix", "aim") if k in act), "")


def color_of(act):
    """Farbe einer Belegung als #rrggbb (Grafik und Lumi-Programm), None = frei."""
    kind = kind_of(act)
    return CSS.get(act["color"], CSS["grey"]) if kind == "color" else KIND_CSS.get(kind)


def state(show):
    lc = controller(show)
    base = lc.map["base_note"]
    notes = [int(n) for n in lc.map["keys"]]
    top = max([n for n in notes if n >= base], default=base)
    windows = (max(top, base) - base) // KEYS_ON_DEVICE + 1            # Seiten (Pfeil = 2 Oktaven), bis alles Belegte zu sehen ist
    keys = []
    for n in range(base, base + KEYS_ON_DEVICE * windows):
        act = lc.map["keys"].get(str(n))
        kind = kind_of(act)
        key = {"note": n, "black": (n - base) % 12 in BLACK, "act": act, "kind": kind}
        key["color"] = color_of(act)
        if kind == "scene":
            key["scene"] = lc._scene_name(act) or ""
        keys.append(key)
    st = lc.status()
    return {"connected": st.get("connected", False), "via": st.get("via", ""), "ports": st.get("ports", []), "base": base,
            "windows": windows, "options": {"color": COLORS, "cmd": list(LUMI_CMDS), "speed": ["slow", "mid", "fast"], "move": MOVE_ORDER,
                                         "mix": MIX_ORDER, "scene": [s.name for s in lumi_scenes(show.scene_defs)]}, "keys": keys, "last": [x for x in lc.last if "seq" in x][-12:], "error": st.get("error", "")}
