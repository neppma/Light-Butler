#!/usr/bin/env python3
"""
midi_ctl.py - AKAI APC mini mk2 als haptische Bedienung der Lichtsteuerung (USB am Raspberry Pi).

  * 8x8 Pads, Hauptseite: Reihe 1 Strobe, AUTO, Smoke, Blackout, Wow, Blinder, Freeze (alle ausser AUTO
    nur solange gedrueckt), BPM (blinkt
    im Takt); Reihe 2 Bewegung; Reihe 3 Licht-Mix; Reihe 4 bis 8 Szenen 1 bis 40
  * SHIFT halten (oder untere Taste "Seite 2"): die Pads zeigen die Farben
  * Tasten rechts (von oben): Low, Med, Hot, Laser, Rest frei
  * Tasten unten (von links): Bank, Tisch, Tuer, Bar, Laser, frei, Hauptseite, Farbseite
  * Fader 1-8: Helligkeit der Lichtgruppen, Fader 9: General Dimmer
  * LEDs zeigen den Zustand (aktive Szene pulsiert, Farben passend), auch wenn etwas im Panel geaendert wird
  * Fader mit Uebernahme: ein Wert wirkt erst, wenn der Fader den aktuellen Stand erreicht (kein Springen)
  * Der APC darf auch am MacBook haengen: die Mixxx-Bruecke leitet Tasten und LEDs per Netzwerk weiter (midi_net.py).
    Haengt er am Pi, gilt der direkte Anschluss.

Aenderungen an der Belegung: Datei midimap.json neben dem Programm (siehe README_midi.txt).
Braucht:  sudo apt install python3-mido python3-rtmidi   (oder pip install mido python-rtmidi)
"""
import json
import os
import threading
import time

PORT_HINT = "apc mini mk2"
# Farbtabelle des APC mini mk2 (Velocity-Werte), passend zu den Farben der Lichtsteuerung
PALETTE = {"auto": 3, "white": 3, "warm": 8, "uv": 50, "multi": 53, "rainbow": 16, "duo": 41, "austria": 5,
           "rot": 5, "orange": 9, "gelb": 13, "gruen": 21, "tuerkis": 33, "cyan": 37, "blau": 45,
           "violett": 49, "magenta": 53, "pink": 56, "off": 0, "grey": 1}
CH_DIM, CH_MID, CH_FULL, CH_PULSE = 1, 3, 6, 9   # MIDI-Kanal 0-basiert: Helligkeit/Animation der Pads
HOLD_CMDS = ("blitz", "fog", "blackout", "allbright", "freeze")   # Taster wie im Panel (zusaetzlich WOW)
SHIFT_NOTE = 122                             # SHIFT-Taste des APC mini mk2: solange gehalten, zeigen die Pads die Farben
TOP_ROW = ["auto", "blitz", "wow", "allbright", "freeze", "blackout", "fog", "beat"]                # Pads Reihe 1 (wie im Panel)
MOVE_ORDER = ["duck", "home", "random", "sweep", "circle", "vertical", "horizontal", "fan"]          # wie im Panel
MIX_ORDER = ["Discokugel", "Karussell", "Sternenhimmel", "STOP", "nach aussen", "nach innen", "Scanner", "Regenbogen"]
SCENE_PADS = 40                                                                                     # Reihe 4 bis 8
COLOR_ORDER = [None, "rot", "orange", "gelb", "gruen", "cyan", "blau", "violett", "magenta", "white", "uv"]
SPEED_ORDER = ["slow", "mid", "fast"]
RIGHT_COLUMN = ["speed:slow", "speed:mid", "speed:fast", "laser",                                    # von oben nach unten
                None, "tap", None, None]                                                             # TAP Tempo; frei: Auto gibt es nur noch oben
BOTTOM_ROW = ["aim:bank", "aim:tisch", "aim:tuer", "aim:bar", "laser", None, "page:1", "page:2"]       # von links nach rechts
FADERS = [("group", "bar"), ("group", "wash"), ("group", "barlight"), ("group", "fx"), ("group", "uv"),
          ("group", "spot"), ("group", "amb"), ("group", "nano"), ("master", "")]


APC_CMDS = ("auto", "blitz", "wow", "allbright", "freeze", "blackout", "fog", "beat", "laser", "page1", "page2", "tap",
            "beam_auto", "eb_auto")
APC_COLORS = [c for c in COLOR_ORDER if c]
APC_SPEEDS = list(SPEED_ORDER)
APC_GROUPS = [g for k, g in FADERS if k == "group"]


def valid_key(sec, key):
    """Gibt es diese Taste oder diesen Fader am APC? SHIFT bleibt fest."""
    if not isinstance(key, int) or isinstance(key, bool):
        return False
    if sec in ("pads1", "pads2"):
        return 0 <= key <= 63
    if sec == "buttons":
        return 100 <= key <= 107 or 112 <= key <= 119
    return sec == "faders" and 48 <= key <= 56


def valid_action(sec, a):
    """Belegung aus dem Panel pruefen. Nur vorhandene Befehle: Sperren und Grenzen liegen weiter in Show.command."""
    if not isinstance(a, dict):
        return False
    if sec == "faders":
        return a == {"fader": "master"} or a == {"fader": "blitz_hz"} or (a.get("fader") == "group" and len(a) == 2 and a.get("group") in APC_GROUPS)
    if len(a) != 1:
        return False
    k, v = next(iter(a.items()))
    return ((k == "cmd" and v in APC_CMDS) or (k == "move" and v in MOVE_ORDER) or (k == "mix" and v in MIX_ORDER)
            or (k == "color" and v in APC_COLORS) or (k == "speed" and v in APC_SPEEDS) or (k == "aim" and isinstance(v, str))
            or (k == "scene_index" and isinstance(v, int) and not isinstance(v, bool) and v >= 0))


def pad_note(row_from_top, col):
    """Pad-Note aus Zeile (0 = oben) und Spalte (0 = links): Note 0 ist unten links, Note 56 oben links."""
    return (7 - row_from_top) * 8 + col


def default_map(scene_top_note=112):
    """Standardbelegung als Dict: pads1 (Hauptseite), pads2 (Farben, mit SHIFT), buttons, faders."""
    pads1 = {}
    for c, name in enumerate(TOP_ROW):
        pads1[str(pad_note(0, c))] = {"cmd": name}
    for c, m in enumerate(MOVE_ORDER):
        pads1[str(pad_note(1, c))] = {"move": m}
    for c, m in enumerate(MIX_ORDER):
        pads1[str(pad_note(2, c))] = {"mix": m}
    for i in range(SCENE_PADS):                        # Szenen nach Index (Reihe 4 links beginnend)
        pads1[str(pad_note(3 + i // 8, i % 8))] = {"scene_index": i}
    pads2 = {}
    for i, col in enumerate(COLOR_ORDER):
        if col:
            pads2[str(pad_note(i // 8, i % 8))] = {"color": col}
    buttons = {}
    for i, name in enumerate(RIGHT_COLUMN):             # rechte Spalte: scene_top_note ist die oberste Taste
        if not name:
            continue
        note = scene_top_note + i if scene_top_note == 112 else scene_top_note - i
        kind, _, val = name.partition(":")
        buttons[str(note)] = {"speed": val} if kind == "speed" else {"cmd": name}
    for i, name in enumerate(BOTTOM_ROW):
        if name:
            kind, _, val = name.partition(":")
            buttons[str(100 + i)] = {"aim": val} if kind == "aim" else ({"cmd": "laser"} if kind == "laser" else {"cmd": "page" + val})
    faders = {str(48 + i): {"fader": k, "group": g} if k == "group" else {"fader": k} for i, (k, g) in enumerate(FADERS)}
    return {"scene_top_note": scene_top_note, "pads1": pads1, "pads2": pads2, "buttons": buttons, "faders": faders}


def load_map(path):
    base = default_map()
    if not path or not os.path.exists(path):
        return base, ""
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
    except (OSError, ValueError) as e:
        return base, f"midimap.json nicht lesbar: {e}"
    if user.get("scene_top_note") in (112, 119):
        base = default_map(user["scene_top_note"])
    for sec in ("pads1", "pads2", "buttons", "faders"):
        for k, v in (user.get(sec) or {}).items():
            if v is None:
                base[sec].pop(str(k), None)
            else:
                from scenes import renamed_action                # alte Namen (KITT -> Scanner)
                base[sec][str(k)] = renamed_action(v)
    if isinstance(user.get("palette"), dict):
        PALETTE.update({k: int(v) for k, v in user["palette"].items()})
    return base, ""


class MidiController:
    leds = True                                       # False: Geraet ohne LED-Anzeige (lumi_ctl.py)

    def __init__(self, show, map_path="midimap.json", port_hint=PORT_HINT):
        self.show, self.map_path, self.hint = show, map_path, port_hint.lower()
        self.map, self.map_error = load_map(map_path)
        self.page = 1
        self.shift = False                            # SHIFT gehalten: Farbseite
        self.connected, self.names = False, []
        self.ins, self.outs = [], []
        self.src_port = None                          # Index des Ports, von dem zuletzt Eingaben kamen
        self.last = []                                # letzte Meldungen fuer das Panel (Monitor)
        self.seq = 0                                  # zaehlt Meldungen (Belegungsseite: gedrueckte Taste kurz aufblitzen)
        self.sent = {}                                # zuletzt gesendete LED-Werte (nur Aenderungen senden)
        self.picked, self.last_cc = {}, {}            # Fader-Uebernahme
        self.held = {}                                # gerade gehaltene Tasten (BLITZ, WOW)
        self.expect = {}                              # zuletzt von einem Fader gesetzte Werte
        self.wow_keep = 0.0
        self.beat_seen, self.beat_off, self.led_test = None, 0.0, 0.0
        self.test_note = None                         # Tasten-Test: Note, die gerade leuchtet
        self.lock = threading.Lock()
        self._run = False
        self.net = None                               # midi_net.NetMidi: APC am Mac (von show.py gesetzt)
        self.via_net, self.net_session, self.net_check = False, None, 0.0

    # ---- Verbindung ----------------------------------------------------------------------------------------------
    def start(self):
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._run = False
        time.sleep(0.1)
        self._leds_off()
        self._close()

    def _close(self):
        for p in self.ins + self.outs:
            try:
                p.close()
            except Exception:                                   # noqa: BLE001
                pass
        self.ins, self.outs, self.connected, self.sent = [], [], False, {}
        self.via_net = False

    def _local_names(self):
        import mido
        ins = sorted(n for n in mido.get_input_names() if self.hint in n.lower())
        outs = sorted(n for n in mido.get_output_names() if self.hint in n.lower())
        return ins, outs

    def _open(self):
        import mido
        ins, outs = self._local_names()
        if ins and outs:                                            # direkt am Pi: hat Vorrang
            # einzeln oeffnen und gleich merken: scheitert einer (Windows: ein Anschluss gehoert immer nur einem
            # Programm, z. B. ROLI Connect), schliesst _close auch die schon offenen, sonst blieben sie gesperrt
            self.ins, self.outs = [], []
            try:
                for n in ins:
                    self.ins.append(mido.open_input(n))
                for n in outs:
                    self.outs.append(mido.open_output(n))
            except Exception:                                       # noqa: BLE001
                self._close()
                raise
            self.names = ins
        elif self.net is not None and self.net.connected():         # am Mac, ueber die Mixxx-Bruecke
            self.ins, self.outs = [self.net.inport], [self.net.outport]
            self.names = [f"{self.net.name or 'APC mini mk2'} (am Musik-Rechner)"]
            self.via_net, self.net_session = True, self.net.session
        else:
            return False
        self.connected, self.src_port, self.sent = True, None, {}
        self._leds_off()
        return True

    def _net_lost(self, now):
        """Verbindung ueber den Mac beenden, wenn er sich nicht mehr meldet, die App am Mac neu gestartet wurde
        (LEDs neu senden) oder der APC jetzt direkt am Pi steckt (alle 2 s geprueft)."""
        if not self.via_net:
            return False
        if not self.net.connected() or self.net.session != self.net_session:
            return True
        if now - self.net_check > 2.0:
            self.net_check = now
            ins, outs = self._local_names()
            return bool(ins and outs)
        return False

    def _loop(self):
        last_state, last_try = 0.0, 0.0
        snap = None
        while self._run:
            now = time.time()
            try:
                if not self.connected:
                    if now - last_try > 2.0:
                        last_try = now
                        self._open()
                    time.sleep(0.2)
                    continue
                if self._net_lost(now):
                    self._close()
                    last_try = 0.0                                  # gleich neu verbinden (direkt oder neue Sitzung)
                    continue
                for idx, port in enumerate(self.ins):
                    for msg in port.iter_pending():
                        self.src_port = idx
                        self.handle(msg)
                if self.leds and (now - last_state >= 0.1 or snap is None):   # Zustand fuer LEDs und Fader-Uebernahme
                    last_state = now
                    snap = self.show.snapshot()
                    if now > self.led_test:
                        self.refresh_leds(snap)
                    self._check_externals(snap)
                if self.leds:
                    self._beat(now)
                if any(self.held.values()) and now - self.wow_keep > 0.4:  # Lebenszeichen, solange Taster gehalten
                    self.wow_keep = now
                    if self.held.get("wow"):
                        self.show.command({"build_keep": True})
                    keep = [n for n in HOLD_CMDS if self.held.get(n)]
                    if keep:
                        self.show.command({"hold_keep": keep})
                time.sleep(0.005)
            except Exception as e:                                  # noqa: BLE001
                self.map_error = f"MIDI getrennt: {str(e)[:80]}"
                self._close()
                time.sleep(1.0)

    # ---- Eingaben --------------------------------------------------------------------------------------------------
    def handle(self, msg):
        t = msg.type
        if t not in ("note_on", "note_off", "control_change"):
            return
        val = getattr(msg, "velocity", getattr(msg, "value", 0)) if t != "note_off" else 0
        what = f"CC {msg.control}" if t == "control_change" else f"Note {msg.note}"
        self.seq += 1
        self.last.append({"t": time.strftime("%H:%M:%S"), "what": what, "value": val, "port": self.src_port, "seq": self.seq})
        self.last = self.last[-12:]
        if t == "control_change":
            self._fader(msg.control, msg.value)
            return
        pressed = t == "note_on" and msg.velocity > 0
        self.press(msg.note, pressed)

    def _pads(self):
        return self.map["pads2" if (self.page == 2 or self.shift) else "pads1"]

    def press(self, note, pressed):
        key = str(note)
        if note == SHIFT_NOTE:
            if pressed != self.shift:
                self.shift = pressed
                self.sent = {k: v for k, v in self.sent.items() if k[0] == "btn"}   # Pads neu zeichnen
            return
        if 0 <= note <= 63:
            act = self._pads().get(key)
        elif 100 <= note <= 119:
            act = self.map["buttons"].get(key)
        else:
            act = None
        if not act:
            return
        self._act(act, pressed, note)

    def _scene_name(self, a):
        if "scene" in a:
            return a["scene"]
        i = a.get("scene_index")
        defs = self.show.scene_defs
        return defs[i].name if i is not None and 0 <= i < len(defs) else None

    def _tap(self, now):
        """TAP Tempo: ab 4 Schlaegen Mittel der letzten 8, nach 2 s Pause beginnt die Zaehlung neu."""
        taps = getattr(self, "taps", [])
        if taps and now - taps[-1] > 2.0:
            taps = []
        taps = (taps + [now])[-8:]
        self.taps = taps
        if len(taps) >= 4:
            bpm = round(60.0 * (len(taps) - 1) / (taps[-1] - taps[0]), 1)
            if 60.0 <= bpm <= 200.0:
                self.show.command({"bpm": bpm})
        return len(taps)

    def _act(self, a, pressed, note):
        cmd, snap = self.show.command, self.show.snapshot()
        if "cmd" in a:
            c = a["cmd"]
            if c in HOLD_CMDS or c == "wow":                           # Taster: wirken nur, solange gedrueckt
                self.held[c] = pressed
                if c == "wow":
                    self.wow_keep = time.time()
                    cmd({"build": pressed})
                else:
                    cmd({"hold": {"name": c, "on": pressed}})
                return
            if not pressed:
                return
            if c == "auto":
                cmd({"auto": "toggle"})
            elif c == "laser":
                sc = next((s.name for s in self.show.scene_defs if s.special == "laser"), None)
                if sc:
                    cmd({"scene": sc})
            elif c == "tap":                                            # TAP Tempo wie im Tempo-Fenster des Panels
                self._tap(time.monotonic())
            elif c == "beam_auto":
                cmd({"beam": "auto"})
            elif c == "eb_auto":
                cmd({"eb_preset": 0})
            elif c in ("page1", "page2"):
                self.page = 1 if c == "page1" else 2
                self.sent = {k: v for k, v in self.sent.items() if k[0] == "btn"}   # Pads neu zeichnen
            return
        if not pressed:
            return
        name = self._scene_name(a)
        if name is not None or "scene" in a or "scene_index" in a:
            if name:
                cmd({"scene": name})
        elif "aim" in a:
            cmd({"aim": "" if snap["aim"] == a["aim"] else a["aim"]})
        elif "speed" in a:                                   # keine Auto-Taste am APC: aktive Taste nochmal = Auto
            cmd({"speed": "auto" if snap["speed"] == a["speed"] else a["speed"]})
        elif "color" in a:                                   # wie im Panel: dazuwaehlen, nochmal druecken = abwaehlen
            cmd({"color_toggle": a["color"]})
        else:
            for k in ("move", "mix"):
                if k in a:
                    cmd({k: a[k]})

    # ---- Fader mit Uebernahme -------------------------------------------------------------------------------------
    def _fader_target(self, cc):
        f = self.map["faders"].get(str(cc))
        if not f:
            return None
        if f["fader"] == "master":
            return "master", None
        if f["fader"] == "group":
            return "group", f["group"]
        if f["fader"] == "blitz_hz":
            return "blitz_hz", None
        return None

    def _current(self, kind, grp):
        s = self.show
        if kind == "master":
            return s.master
        if kind == "group":
            return s.glevel.get(grp, 1.0)
        if kind == "blitz_hz":
            return (s.blitz_hz - 1.0) / 11.0
        return 0.0

    def _fader(self, cc, value):
        tg = self._fader_target(cc)
        if tg is None:
            return
        kind, grp = tg
        cur = self._current(kind, grp) * 127.0
        prev = self.last_cc.get(cc)
        self.last_cc[cc] = value
        if not self.picked.get(cc):
            crossed = prev is not None and (prev - cur) * (value - cur) <= 0
            if abs(value - cur) <= 3 or crossed:                     # Fader hat den aktuellen Stand erreicht: uebernehmen
                self.picked[cc] = True
            else:
                return
        v = value / 127.0
        if kind == "master":
            self.show.command({"master": v})
        elif kind == "group":
            self.show.command({"glevel": {grp: v}})
        elif kind == "blitz_hz":
            self.show.command({"blitz_hz": 1.0 + v * 11.0})
        self.expect[cc] = v

    def _check_externals(self, snap):
        """Hat jemand den Wert im Panel geaendert, muss der Fader ihn wieder neu 'einfangen'."""
        exp = self.expect
        for cc in list(self.picked):
            tg = self._fader_target(cc)
            if tg is None or not self.picked.get(cc):
                continue
            cur = self._current(*tg)
            if abs(cur - exp.get(cc, cur)) > 0.04:
                self.picked[cc] = False

    # ---- LEDs ---------------------------------------------------------------------------------------------------------
    def _send(self, kind, note, vel, ch=0):
        key = (kind, note)
        if self.sent.get(key) == (vel, ch):
            return
        self.sent[key] = (vel, ch)
        self._raw(note, vel, ch)

    def _raw(self, note, vel, ch):
        import mido
        ports = [self.outs[self.src_port]] if self.src_port is not None and self.src_port < len(self.outs) else self.outs
        for p in ports:
            try:
                p.send(mido.Message("note_on", channel=ch, note=note, velocity=vel))
            except Exception:                                       # noqa: BLE001
                pass

    def _leds_off(self):
        if not self.outs:
            return
        try:
            for n in list(range(64)) + list(range(100, 108)) + list(range(112, 120)):
                self._raw(n, 0, 0)
        except Exception:                                           # noqa: BLE001
            pass

    def _scene_color(self, s):
        if s.special == "blackout":
            return PALETTE["rot"]
        if s.special == "auto":
            return PALETTE["gruen"]
        if s.special == "laser":
            return PALETTE["violett"]
        if s.special.startswith("aim:"):
            return PALETTE["warm"]
        return PALETTE.get(s.color, PALETTE["white"])

    def _pad_led(self, act, snap):
        """Farbe und Zustand eines Pads: (Velocity, MIDI-Kanal). Wie in der Vorlage: aus = rot (Reihe 1 gelb,
        AUTO blau), aktiv = gruen. Die Farbseite zeigt die echten Farben."""
        defs = self.show.scene_defs
        red, green = PALETTE["rot"], PALETTE["gruen"]
        if "scene_index" in act or "scene" in act:
            name = self._scene_name(act)
            sc = next((s for s in defs if s.name == name), None)
            if sc is None:
                return 0, 0
            active = (snap["mode"] == "scene" and snap["scene"] == name) or (sc.special == "blackout" and snap["mode"] == "blackout") \
                or (sc.special.startswith("aim:") and snap["aim"] == sc.special[4:])
            return (green, CH_PULSE) if active else (red, CH_MID)
        if "cmd" in act:
            c = act["cmd"]
            if c == "beat":
                return -1, -1                                           # wird von _beat() gesteuert
            on = self._btn_led(act, snap, None)
            if on:
                return green, CH_PULSE if on == 2 else CH_FULL
            return (PALETTE["blau"] if c == "auto" else PALETTE["gelb"]), CH_MID
        if "color" in act:
            return PALETTE.get(act["color"], 3), CH_FULL if (snap["color"] == act["color"] or act["color"] in snap.get("colors", ())) else CH_DIM
        if "move" in act:
            return (green, CH_FULL) if snap["move"] == act["move"] else (red, CH_MID)
        if "mix" in act:
            return (green, CH_FULL) if snap["mixbtn"] == act["mix"] else (red, CH_MID)
        if "speed" in act:
            return (green, CH_FULL) if snap["speed"] == act["speed"] else (red, CH_MID)
        return 0, 0

    def _btn_led(self, act, snap, note):
        """Einfarbige Tasten: 0 aus, 1 an, 2 blinkt."""
        if "aim" in act:
            return 1 if snap["aim"] == act["aim"] else 0
        if "speed" in act:
            return 1 if snap["speed"] == act["speed"] else 0
        c = act.get("cmd")
        if c == "beat":
            return -1                                               # wird von _beat() gesteuert
        if c == "auto":
            return 1 if snap.get("pilot") else 0
        if c == "blackout":
            return 1 if snap["mode"] == "blackout" else 0
        if c == "allbright":
            return 1 if snap["mode"] == "allbright" else 0
        if c == "freeze":
            return 1 if snap["freeze"] else 0
        if c == "blitz":
            return 2 if snap["blitz"] else 0
        if c == "wow":
            return 2 if snap["build"] else 0
        if c == "fog":
            return 2 if snap["fog_on"] else 0
        if c == "laser":
            return 2 if snap["laser"] else (1 if snap["scene"] and any(s.special == "laser" and s.name == snap["scene"] for s in self.show.scene_defs) else 0)
        if c in ("page1", "page2"):
            return 1 if self.page == (1 if c == "page1" else 2) else 0
        if c == "tap":
            return 1 if snap.get("bpm_manual") else 0               # Tempo von Hand gestellt
        if c == "beam_auto":
            return 1 if (snap.get("beam") or {}).get("auto") else 0
        if c == "eb_auto":
            return 1 if not (snap.get("eb") or {}).get("man") else 0
        return 0

    def refresh_leds(self, snap):
        pads = self._pads()
        for note in range(64):
            act = pads.get(str(note))
            vel, ch = self._pad_led(act, snap) if act else (0, 0)
            if vel >= 0:
                self._send("pad", note, vel, ch)
        for note in list(range(100, 108)) + list(range(112, 120)):
            act = self.map["buttons"].get(str(note))
            if not act:
                self._send("btn", note, 0, 0)
                continue
            v = self._btn_led(act, snap, note)
            if v >= 0:
                self._send("btn", note, v, 0)

    def _beat(self, now):
        """BEAT/BPM: blinkt bei jedem Beat kurz (auf der Eins etwas laenger). Als Taste einfarbig, als Pad gruen
        auf rotem Grund."""
        kind, note = "btn", next((int(n) for n, a in self.map["buttons"].items() if a.get("cmd") == "beat"), None)
        if note is None and now > self.led_test:                  # sonst ein Pad der gerade sichtbaren Seite
            kind, note = "pad", next((int(n) for n, a in self._pads().items() if a.get("cmd") == "beat"), None)
        if note is None:
            return
        on, off = ((1, 0), (0, 0)) if kind == "btn" else ((PALETTE["gruen"], CH_FULL), (PALETTE["rot"], CH_MID))
        if (kind, note) not in self.sent:
            self._send(kind, note, *off)
        s = self.show
        if s.beat_t is not None and s.beat_t != self.beat_seen:
            self.beat_seen = s.beat_t
            self._send(kind, note, *on)
            self.beat_off = now + (0.16 if s.step % max(1, s.bar_len) == 0 else 0.07)
        elif self.beat_off and now >= self.beat_off:
            self.beat_off = 0.0
            self._send(kind, note, *off)

    # ---- Befehle aus dem Panel -------------------------------------------------------------------------------------------
    def command(self, d):
        if d.get("test"):                                           # LED-Test: Pad n zeigt Farbe n (zum Abgleichen der Farbtabelle)
            self.led_test = time.time() + 20.0
            for n in range(64):
                self._send("pad", n, n + (64 if d["test"] == 2 else 0), CH_FULL)
        if d.get("test") == 3:                                      # Tasten-Test: runde Tasten nacheinander einzeln leuchten lassen
            threading.Thread(target=self._button_test, daemon=True).start()
        if d.get("redraw"):
            self.led_test = 0.0
            self.sent = {}
        if d.get("reload"):
            self.map, self.map_error = load_map(self.map_path)
            self.sent = {}

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
        except (OSError, ValueError) as e:              # kaputte Datei nicht ueberschreiben
            raise ValueError(f"midimap.json nicht lesbar: {e}") from e
        return user

    def _write_user(self, user):
        tmp = self.map_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(user, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.map_path)
        self.map, self.map_error = load_map(self.map_path)
        self.sent, self.picked = {}, {}                 # LEDs neu, Fader neu einfangen

    def set_key(self, sec, key, act):
        """Panel: Taste oder Fader umbelegen (act None = frei), wirkt sofort."""
        if not valid_key(sec, key):
            raise ValueError("Diese Taste gibt es nicht")
        if act is not None and not valid_action(sec, act):
            raise ValueError("Ungueltige Belegung")
        user = self._read_user()
        part = user.get(sec) if isinstance(user.get(sec), dict) else {}
        part[str(key)] = act
        user[sec] = part
        self._write_user(user)

    def reset_keys(self):
        """Panel: zurueck zur Standardbelegung (Farbtabelle und Lage der rechten Tasten bleiben)."""
        user = self._read_user()
        for sec in ("pads1", "pads2", "buttons", "faders"):
            user.pop(sec, None)
        self._write_user(user)

    def _button_test(self):
        """Erst die rechte Reihe (Noten 112 bis 119), dann die untere (100 bis 107): je 0,8 s. Zeigt die Lage der Noten."""
        self.led_test = time.time() + 20.0
        for n in list(range(112, 120)) + list(range(100, 108)):
            self.test_note = n
            self._send("btn", n, 1, 0)
            time.sleep(0.8)
            self._send("btn", n, 0, 0)
        self.test_note = None
        self.led_test = 0.0
        self.sent = {}

    def status(self):
        return {"connected": self.connected, "via": "mac" if self.via_net else "usb", "ports": self.names, "page": self.page, "shift": self.shift, "last": self.last[-8:],
                "error": self.map_error, "source": self.src_port, "test_note": self.test_note}
