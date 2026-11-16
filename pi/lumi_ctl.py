#!/usr/bin/env python3
"""
lumi_ctl.py - ROLI LUMI Keys als zweite haptische Bedienung neben dem APC mini mk2.

Der Lumi haengt am MacBook: die Mixxx-Bruecke oder der Helfer (apc_relay.lumi_relay) schickt seine Noten per UDP 9023
an den Pi (midi_net.NetMidi, eigener Port, damit sich APC und Lumi nicht verdraengen). Steckt er am Pi, gilt wie beim
APC der direkte Anschluss. Die Klaviatur hat keine Pads und keine Fader, die Tastenfarben kommen vom Programm auf dem Lumi
(lumi_program.py, Download auf /lumi), der Pi steuert sie nicht an.

Belegung nach MIDI-Note, darum wirkt die Oktav-Taste am Lumi wie ein Seitenwechsel. Standard ab base_note (Note 36, tiefste Taste in
Grundstellung, 24 Tasten bis Note 59; am Geraet gemessen):
  Oktave 0  weiss: Rot, Orange, Gelb, Gruen, Cyan, Blau, Violett     schwarz: Wow, Blinder, Freeze, AUTO, TAP
  Oktave 1  weiss: Magenta, Weiss, UV, Low, Med, Hot, Blackout       schwarz: Szenen 1-5
  Oktave 2  weiss: Bewegung 1-7                                      schwarz: Szenen 6-10
  Oktave 3  weiss: Bewegung 8, Licht-Mix 1-6                         schwarz: Szenen 11-15
  Oktave 4  weiss: Licht-Mix 7-8                                     schwarz: Szenen 16-20

Laser, Strobe und Nebel gibt es hier bewusst nicht, auch nicht ueber die eigene Belegung lumimap.json: eine Klaviatur
trifft man zu leicht daneben. Szenen sind nur normale Szenen, ohne Laser, Strobo, Gewitter, All off, Reset und Ziele.
Eigene Belegung (Datei lumimap.json neben dem Programm): {"base_note": 36, "keys": {"60": {"color": "rot"}, "61": null}}
"""
import json
import os

from midi_ctl import MIX_ORDER, MOVE_ORDER, MidiController

PORT_HINT = "lumi keys"
BASE_NOTE = 36
WHITE = (0, 2, 4, 5, 7, 9, 11)                  # Halbtoene der weissen und schwarzen Tasten innerhalb einer Oktave
BLACK = (1, 3, 6, 8, 10)
COLORS = ["rot", "orange", "gelb", "gruen", "cyan", "blau", "violett", "magenta", "white", "uv"]
BLACK_CMDS = ["wow", "allbright", "freeze", "auto", "tap"]
LUMI_CMDS = ("wow", "allbright", "freeze", "blackout", "auto", "tap", "beam_auto", "eb_auto")
NO_SCENE_MIX = ("strobe", "lightning")


def default_map(base=BASE_NOTE):
    whites = [{"color": c} for c in COLORS] + [{"speed": s} for s in ("slow", "mid", "fast")] + [{"cmd": "blackout"}]
    whites += [{"move": m} for m in MOVE_ORDER] + [{"mix": m} for m in MIX_ORDER]
    blacks = [{"cmd": c} for c in BLACK_CMDS] + [{"scene_index": i} for i in range(20)]
    keys = {}
    for i, act in enumerate(whites):
        keys[str(base + i // 7 * 12 + WHITE[i % 7])] = act
    for i, act in enumerate(blacks):
        keys[str(base + i // 5 * 12 + BLACK[i % 5])] = act
    return {"base_note": base, "keys": keys}


def lumi_scenes(defs):
    """Szenen, die der Lumi ausloesen darf: nur normale, ohne Sonderfunktion und ohne Strobo oder Gewitter."""
    return [s for s in defs if not s.special and s.mix not in NO_SCENE_MIX]


def allowed(a):
    """Eine Aktion aus lumimap.json pruefen. Alles, was nicht ausdruecklich vorgesehen ist, gilt nicht."""
    if not isinstance(a, dict) or len(a) != 1:
        return False
    k, v = next(iter(a.items()))
    return ((k == "cmd" and v in LUMI_CMDS) or (k == "mix" and v in MIX_ORDER) or (k == "move" and v in MOVE_ORDER)
            or (k == "speed" and v in ("slow", "mid", "fast")) or (k == "color" and isinstance(v, str))
            or (k == "aim" and isinstance(v, str)) or (k == "scene" and isinstance(v, str))
            or (k == "scene_index" and isinstance(v, int) and not isinstance(v, bool)))


def load_map(path):
    base = default_map()
    if not path or not os.path.exists(path):
        return base, ""
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        if not isinstance(user, dict):
            raise ValueError("kein Objekt")
    except (OSError, ValueError) as e:
        return base, f"lumimap.json nicht lesbar: {e}"
    bn = user.get("base_note")
    if isinstance(bn, int) and not isinstance(bn, bool) and 0 <= bn <= 67:
        base = default_map(bn)
    bad = []
    from scenes import renamed_action                            # alte Namen (KITT -> Scanner)
    for k, v in (user.get("keys") or {}).items():
        v = renamed_action(v)
        if v is None:
            base["keys"].pop(str(k), None)
        elif allowed(v):
            base["keys"][str(k)] = v
        else:
            bad.append(str(k))
    return base, f"lumimap.json: nicht erlaubt, ignoriert: Note {', '.join(bad)}" if bad else ""


class LumiController(MidiController):
    """Dieselbe Verbindung und dieselben Befehle wie beim APC, aber eigene Belegung, keine LEDs und keine Fader."""
    leds = False

    def __init__(self, show, map_path="lumimap.json", port_hint=PORT_HINT):
        super().__init__(show, None, port_hint)
        self.map_path = map_path
        self.map, self.map_error = load_map(map_path)

    def _read_user(self):
        if not self.map_path:
            raise ValueError("Keine Belegungsdatei")
        if not os.path.exists(self.map_path):
            return {}
        try:
            with open(self.map_path, encoding="utf-8") as f:
                user = json.load(f)
            if not isinstance(user, dict):
                raise ValueError("kein Objekt")
        except (OSError, ValueError) as e:             # kaputte Datei nicht ueberschreiben
            raise ValueError(f"lumimap.json nicht lesbar: {e}") from e
        return user

    def _write_user(self, user):
        tmp = self.map_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(user, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.map_path)
        self.map, self.map_error = load_map(self.map_path)

    def set_key(self, note, act):
        """Panel: eine Taste umbelegen (act None = frei), wirkt sofort. Es gilt dieselbe Pruefung wie fuer die Datei."""
        if not isinstance(note, int) or isinstance(note, bool) or not 0 <= note <= 127:
            raise ValueError("Ungueltige Note")
        if act is not None and not allowed(act):
            raise ValueError("Diese Belegung ist auf dem Lumi nicht erlaubt")
        user = self._read_user()
        keys = user.get("keys") if isinstance(user.get("keys"), dict) else {}
        keys[str(note)] = act
        user["keys"] = keys
        self._write_user(user)

    def reset_keys(self):
        """Panel: zurueck zur Standardbelegung (base_note bleibt)."""
        user = self._read_user()
        user["keys"] = {}
        self._write_user(user)

    def press(self, note, pressed):
        act = self.map["keys"].get(str(note))
        if act:
            self._act(act, pressed, note)

    def _scene_name(self, a):
        ok = lumi_scenes(self.show.scene_defs)
        if "scene" in a:                              # eigene Belegung: Name gilt nur, wenn die Szene erlaubt ist
            return a["scene"] if any(s.name == a["scene"] for s in ok) else None
        i = a.get("scene_index")
        return ok[i].name if i is not None and 0 <= i < len(ok) else None

    def _fader(self, cc, value):
        pass

    def _leds_off(self):
        pass

    def command(self, d):
        if d.get("reload"):
            self.map, self.map_error = load_map(self.map_path)
