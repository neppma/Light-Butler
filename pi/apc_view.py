#!/usr/bin/env python3
"""
apc_view.py - Daten fuer die Seite "APC mini · Belegung" (/apc): das ganze Board mit aktueller Belegung (inklusive
midimap.json), den LED-Farben wie am Geraet, den Fader-Werten und den zuletzt gedrueckten Tasten.
Nur zum Ansehen; geschaltet wird hier nichts.
"""
from midi_ctl import APC_CMDS, APC_COLORS, APC_GROUPS, APC_SPEEDS, MIX_ORDER, MOVE_ORDER, CH_DIM, CH_FULL, CH_MID, CH_PULSE, PALETTE, SHIFT_NOTE, MidiController, pad_note

# Velocity der APC-Farbtabelle -> Farbe im Browser (ungefaehr wie am Geraet)
CSS = {"rot": "#d62020", "orange": "#f07800", "gelb": "#c9b52a", "gruen": "#2e9e4a", "tuerkis": "#1ab0a0",
       "cyan": "#0fc0d0", "blau": "#2b4fd6", "violett": "#8a2fe0", "magenta": "#e01fae", "pink": "#ff6fb0",
       "white": "#eeeeee", "warm": "#f0a040", "uv": "#5a1fd0", "rainbow": "#e05a20", "duo": "#3a70d0", "grey": "#55576a"}
LEVEL = {CH_DIM: 0.35, CH_MID: 0.6, CH_FULL: 1.0, CH_PULSE: 1.0}


def css_of(vel):
    if vel is None or vel <= 0:
        return None
    for name, v in PALETTE.items():
        if v == vel and name in CSS:
            return CSS[name]
    return CSS["grey"]


def controller(show):
    """Der laufende Controller, sonst ein Ersatz nur fuer die Anzeige (ohne MIDI, ohne Thread)."""
    mc = getattr(show, "midi", None)
    if mc is None:
        mc = getattr(show, "_apc_view", None)
        if mc is None:
            mc = MidiController(show, "midimap.json")
            show._apc_view = mc
    return mc


def state(show):
    mc = controller(show)
    snap = show.snapshot()
    pages = {}
    for key in ("pads1", "pads2"):
        pads = mc.map.get(key, {})
        grid = []
        for r in range(8):
            row = []
            for c in range(8):
                n = pad_note(r, c)
                act = pads.get(str(n))
                cell = {"note": n, "act": act}
                if act:
                    if "scene_index" in act or "scene" in act:
                        cell["scene"] = mc._scene_name(act) or ""
                        if "scene_index" in act:
                            cell["nr"] = act["scene_index"] + 1
                    vel, ch = mc._pad_led(act, snap)
                    cell["color"] = css_of(vel) if vel != -1 else CSS["gelb"]
                    cell["level"] = LEVEL.get(ch, 0.6)
                    cell["pulse"] = ch == CH_PULSE
                row.append(cell)
            grid.append(row)
        pages[key] = grid
    btn = mc.map.get("buttons", {})
    top = mc.map.get("scene_top_note", 112)
    right = []
    for i in range(8):                                    # Scene-Launch-Tasten von oben nach unten
        n = top + i if top == 112 else top - i
        act = btn.get(str(n))
        right.append({"note": n, "act": act, "on": bool(act) and mc._btn_led(act, snap, n) > 0, "scene": mc._scene_name(act) if act else None})
    bottom = []
    for i in range(8):
        n = 100 + i
        act = btn.get(str(n))
        bottom.append({"note": n, "act": act, "on": bool(act) and mc._btn_led(act, snap, n) > 0, "scene": mc._scene_name(act) if act else None})
    faders = []
    for i in range(9):
        cc = 48 + i
        act = mc.map.get("faders", {}).get(str(cc))
        val = None
        if act and act.get("fader") == "master":
            val = snap["master"]
        elif act and act.get("fader") == "group":
            val = (snap.get("glevel") or {}).get(act.get("group"))
        faders.append({"cc": cc, "act": act, "value": None if val is None else round(float(val), 2)})
    st = mc.status()
    return {"connected": st.get("connected", False), "via": st.get("via", ""), "ports": st.get("ports", []),
            "page": mc.page, "shift": mc.shift, "pages": pages, "right": right, "bottom": bottom, "faders": faders,
            "shift_note": SHIFT_NOTE, "last": [x for x in mc.last if "seq" in x][-12:], "error": st.get("error", ""),
            "options": {"cmd": list(APC_CMDS), "color": APC_COLORS, "speed": APC_SPEEDS, "move": MOVE_ORDER, "mix": MIX_ORDER,
                        "scene": [s.name for s in show.scene_defs], "group": APC_GROUPS},
            "midi_running": getattr(show, "midi", None) is not None}
