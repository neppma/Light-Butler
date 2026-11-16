#!/usr/bin/env python3
"""
engine.py - DMX-Playback-Engine: rechnet die Show und schreibt sie in den Rig.

Sie hat keinen eigenen Sendetakt: Show.update ruft render() einmal je Bild (40 pro Sekunde) in der Hauptschleife auf, danach
sendet dmx.Output genau dieses Bild. So bleibt die Regel "jedes Bild genau einmal" erhalten, und die Ausgabe haengt weder am
Browser noch am Web-Thread.

SICHERHEIT (zusaetzlich zu Fixture.write, das Laser, Hazer und safe_limits in jedem Bild erzwingt):
  * mode_unlock und hw_unlock werden hier nie gesetzt, Fixture.manual nie aufgerufen.
  * Hazer und einzelne Laser-Kanaele sind keine Spuren (fixtures.attrs_for), die Show kann sie nicht ansprechen.
  * Laser nur ueber Laser-Clips (vom Nutzer am 03.11.2026 freigegeben). laser_unlock gilt fuer genau ein Bild und nur mit
    Einstellung sm_laser, waehrend die Musik wirklich laeuft und die Zeitquelle sich meldet. Sofort aus bei Pause, Springen,
    Stop, BLACKOUT, FREEZE, WOW!, Dienstende (siehe _laser_ok). Leistung nie ueber safe_limits, Mode bleibt im sicheren Bereich.
  * Ohne Strobe-Erlaubnis: Strobe-Kanaele aus (dmx.EXT_NO_STROBE), blitzende Effektband-Presets aus und FlashLimiter
    (hoechstens 2 Blitze pro Sekunde je Kanal, egal ob aus Muster oder Keyframes).
  * BLACKOUT, ALLES HELL und FREEZE liegen in Show.update vor der Show.
"""
import threading

from dmx import EXT_NO_STROBE

from . import fixtures as fm
from . import timeline as tl
from .clock import MasterClock

EB_STROBE = (8, 32)          # wie show.EB_STROBE (test_showmanager prueft die Gleichheit); show.py wird hier nicht importiert
MIXXX = "mixxx"              # Besitzer der Zeitbasis: das hoerbare Deck in Mixxx statt eines Browsers
MAX_FLASH_HZ = 2.0
LIVE_S = 0.6                 # so lange darf die Meldung von Browser oder Mixxx fehlen, bevor die Laser aus sind
# KTV im 6-Kanal-Modus (Typ laser_ktv, nur noch fuer den Fall, dass zurueckgestellt wird): Gruppe und Effekt wirken dort erst nach
# einer Aenderung im eingeschalteten Zustand, deshalb beim Start kurz andere Werte. Im 34-Kanal-Modus ist das nicht noetig.
KTV_PRESET_S = 0.15
KTV_KICK_S = 0.20
SEEK_HOLD_S = 0.5            # so lange bleiben die Laser nach einem Sprung aus
FLASH_STEP = 48              # ein Anstieg um mindestens so viel gilt als Blitz (etwa 19 % der Helligkeit)


class FlashLimiter:
    """Ohne Strobe-Erlaubnis: hoechstens 2 Blitze pro Sekunde je Kanal.

    Ein Blitz ist ein Anstieg um FLASH_STEP oder mehr seit dem letzten Tiefpunkt. Kommt er zu frueh nach dem vorigen, bleibt der
    Kanal beim Tiefpunkt, bis wieder einer erlaubt ist. Das erfasst jede Wellenform, auch schnelle Sinus-Kurven und Farbwechsel.
    Langsame Fades sind davon nicht betroffen."""

    def __init__(self, hz=MAX_FLASH_HZ, step=FLASH_STEP):
        self.gap, self.step = 1.0 / hz + 0.001, step      # knapp darueber: auch auf die Rundung hin nie 3 Blitze in einer Sekunde
        self.st = {}                 # Kanal -> [Tiefpunkt, in Hochphase?, Spitze, Zeit des letzten Blitzes]

    def reset(self):
        self.st = {}

    def filter(self, key, v, now):
        s = self.st.get(key)
        if s is None:                            # schon hell beim ersten Bild: das zaehlt als Blitz
            s = self.st[key] = [v, v >= self.step, v, now if v >= self.step else -1e9]
            return v
        if s[1]:                                 # Hochphase: erst nach einem Abfall ist der naechste Anstieg ein neuer Blitz
            if v > s[2]:
                s[2] = v
            elif v <= s[2] - self.step:
                s[0], s[1] = v, False
            return v
        if v < s[0]:
            s[0] = v
        if v - s[0] >= self.step:
            if now - s[3] < self.gap:
                return s[0]                      # zu frueh: bleibt dunkel
            s[1], s[2], s[3] = True, v, now
        return v


class PlaybackEngine:
    def __init__(self, rig):
        self.rig = rig
        self.lock = threading.Lock()
        self.clock = MasterClock()
        self.compiled = None
        self.doc_name = ""
        self.light = False           # True: die Show steuert das Licht. False: Wiedergabe nur im Browser, das Licht bleibt bei AUTO
        self.loaded = False          # True zwischen Play und Stop
        self.owner = None            # Browser, dessen Audio die Zeitbasis ist
        self.offset = 0.0            # Licht-Versatz in Sekunden (Einstellung sm_light_ms)
        self.limiter = FlashLimiter()
        self.frame = 0
        self.dirty = False           # die Show hat zuletzt Werte in den Rig geschrieben
        self.last_now = 0.0
        self.ended = False
        self.live_t = 0.0            # letzte Meldung der Zeitquelle (oder Play)
        self.hold_until = 0.0        # Laser aus bis (nach einem Sprung)
        self.jumps_seen = 0
        self.ktv_t = {}              # seit wann ein KTV-Clip ohne Unterbrechung laeuft
        self.laser_live = False      # in diesem Bild ist ein Laser freigegeben (Anzeige LASER AKTIV)
        self.parts = {f.name: self._parts(f) for f in rig.fixtures if not f.locked}

    @staticmethod
    def _parts(fx):
        """Was je Geraet gebraucht wird, einmal vorab: Blitz-Grenze gilt fuer Licht-Kanaele und den Shutter."""
        watch = [p for p in fx.map if p in fx.light_params or p in ("dimmer", "shutter")]
        pu, pv = fm.move_params(fx)
        lim = {}
        for p in pu + pv:
            lim[p] = fx.limits.get(p, (0, 255))
        return {"watch": watch, "pu": pu, "pv": pv, "lim": lim}

    # ---- Bedienung (aus den Web-Threads) --------------------------------------------------------------
    def load(self, doc):
        """Show uebersetzen und tauschen. Laufende Wiedergabe laeuft mit den neuen Werten weiter (Bearbeiten im Editor)."""
        c = tl.compile_show(doc, self.rig)
        with self.lock:
            self.compiled, self.doc_name = c, c.name
        return c.warnings

    def play(self, now, pos=None, light=None, owner=None):
        with self.lock:
            if self.compiled is None:
                raise ValueError("Keine Show geladen")
            if light is not None:
                self.light = bool(light)
            self.owner = owner
            self.clock.start(pos, now)
            self.loaded, self.ended = True, False
            self.live_t = now

    def pause(self, now, pos=None):
        with self.lock:
            self.clock.pause(now, pos)

    def seek(self, pos, now):
        with self.lock:
            self.clock.seek(max(0.0, float(pos)), now)
            self.hold_until = now + SEEK_HOLD_S

    def stop(self, now):
        with self.lock:
            self.clock.pause(now, 0.0)
            self.loaded, self.owner = False, None
            self.light = False       # das naechste Play entscheidet neu, ob es ans echte Licht geht

    def set_light(self, on):
        with self.lock:
            self.light = bool(on)

    def report(self, client, pos, playing, lat, now, base=1.0):
        """Meldung eines Browsers oder von Mixxx: nur der Besitzer der Zeitbasis zaehlt. lat = Korrektur in Sekunden (Netz, Tonausgabe)."""
        with self.lock:
            if not self.loaded or client != self.owner:
                return False
            if playing:
                if not self.clock.playing:
                    self.clock.start(pos, now)
                self.clock.report(pos + lat, now, base)
                self.live_t = now
            elif self.clock.playing:
                self.clock.pause(now, pos)
            return True

    # ---- Bild fuer Bild (Hauptschleife) -----------------------------------------------------------------
    def active(self):
        """True: Dieses Bild kommt aus der Show."""
        return self.loaded and self.light and self.compiled is not None

    def position(self, now):
        return self.clock.position(now)

    def tick(self, now):
        """Einmal je Bild: Zeit weiterschalten, am Ende der Show aufhoeren. Danach gilt wieder AUTO."""
        self.last_now = now
        self.frame += 1
        with self.lock:
            self.clock.tick(now)
            c = self.compiled
            if self.loaded and c is not None and self.clock.position(now) >= c.duration:
                self.clock.pause(now, 0.0)
                self.loaded, self.owner, self.ended, self.light = False, None, True, False

    def _laser_ok(self, now, allowed):
        """Darf in diesem Bild ein Laser an sein? Der Strahl soll nie stehen oder nachlaufen, wenn die Musik nicht wirklich spielt."""
        ck = self.clock
        if ck.jumps != self.jumps_seen:          # die Zeitquelle ist gesprungen (Sprung in Mixxx, Puffern im Browser)
            self.jumps_seen = ck.jumps
            self.hold_until = now + SEEK_HOLD_S
        if not (allowed and self.active() and ck.playing) or now < self.hold_until:
            return False
        return self.owner is None or now - self.live_t <= LIVE_S    # ohne Besitzer: bewusst nach der eigenen Uhr ("Ton woanders")

    def lyric_pos(self, now):
        """(Zeilen, Stelle) der laufenden Show fuer die Anzeige im Panel."""
        c = self.compiled
        return (c.lyric_lines if c is not None else []), self.clock.position(now) + self.offset

    def panel_scene(self, now):
        """Szene aus dem Hauptpanel an dieser Stelle der Show, sonst None."""
        c = self.compiled
        if c is None or not c.panel_cues:
            return None
        return c.panel_scene_at(max(0.0, self.clock.position(now) + self.offset))

    def master_now(self, now):
        c = self.compiled
        return c.master_at(max(0.0, self.clock.position(now) + self.offset)) if c is not None else 1.0

    def nano_effect(self, now):
        """Effekt des Nanoleaf gerade jetzt; bei Pause und Stop keiner, dann wieder Einzelpanels."""
        c = self.compiled
        if c is None or not c.nano_cues or not self.clock.playing:
            return None
        return c.nano_effect_at(self.clock.position(now) + self.offset)

    def render(self, now, master=1.0, strobe=False, laser=False):
        """Schreibt das Bild in die Fixtures. Aufruf unter rig.lock. laser = Einstellung sm_laser."""
        c = self.compiled
        self.laser_live = False
        if c is None:
            return
        t = self.clock.position(now) + self.offset
        state = c.evaluate(max(0.0, t), self.frame, strobe)
        master *= c.master_at(max(0.0, t))                # Master-Zeile der Show, zusaetzlich zum Dimmer im Panel
        if strobe:
            self.limiter.reset()
        laser_ok = self._laser_ok(now, laser)
        for fx in self.rig.fixtures:
            if fx.locked:
                continue                                  # Hazer: nie anfassen, ein laufender Nebelschub bleibt unberuehrt
            self._apply(fx, state.get(fx.name), master, strobe, now, laser_ok)
        self.dirty = True

    def release(self):
        """Nach dem Ende: Geraete zurueck auf ihre Standardwerte, AUTO rechnet ab dem naechsten Bild neu. Aufruf unter rig.lock."""
        for fx in self.rig.fixtures:
            if not fx.locked:
                fx.reset()
                fx.blackout()                             # nimmt auch die Laser-Freigabe zurueck
        self.limiter.reset()
        self.laser_live = False
        self.ktv_t = {}
        self.dirty = False

    def _apply(self, fx, st, master, strobe, now, laser_ok=False):
        fx.reset()
        fx.laser_unlock = False
        zones = fx.zones()
        # Grundbild: dunkel, Standardwerte der Betriebsarten-Kanaele bleiben (Mode 5, Shutter offen ...)
        for z in zones:
            for p in z.values():
                fx.values[p] = 0
        if not zones and "dimmer" in fx.map:
            fx.values["dimmer"] = 0
        if st:
            self._apply_state(fx, st, zones, master, strobe)
        if not strobe:
            for p, f in EXT_NO_STROBE.items():
                if p in fx.values:
                    fx.values[p] = f(fx.values[p])
            for p in self.parts[fx.name]["watch"]:
                fx.values[p] = self.limiter.filter((fx.name, p), fx.values[p], now)
        if laser_ok and st and fm.A_LASER in st and fx.laser_params:
            self._laser(fx, st[fm.A_LASER], strobe, now)
        else:
            self.ktv_t.pop(fx.name, None)

    def _laser(self, fx, v, strobe, now):
        """Laser-Clip: Werte wie in der Szene Laser (Pi steuert). Freigabe nur fuer dieses Bild, Show.update nimmt sie vor jedem Bild zurueck."""
        on, muster, color, tempo, p = v
        ktv_group, ktv_effect = p["ktv_group"], p["ktv_effect"]
        on = on >= 0.5
        muster, tempo = int(muster), int(tempo)
        fx.laser_unlock = True
        self.laser_live = True
        beams = []
        if fx.type == "eyes_21":
            beams = {"bunt": ["laser_red1", "laser_red2", "laser_green", "laser_blue"], "rot": ["laser_red1", "laser_red2"],
                     "gruen": ["laser_green"], "blau": ["laser_blue"]}[color]
            for p in ("laser_red1", "laser_red2", "laser_green", "laser_blue"):
                fx.values[p] = 255 if on and p in beams else 0
            fx.values["motor_speed"] = tempo
            beams = ["laser_red1", "laser_red2", "laser_green", "laser_blue"]
        elif fx.type == "laser_ktv":
            # Anleitung 6CH: Kanal 2 je 32 Werte eine Liniengruppe, ab 192 Animationen; Kanal 3 bis 5 alle Effekte, dann je 6 Werte einer;
            # Kanal 6 bis 127 Laufgeschwindigkeit, nie der Sound-Bereich. Jeweils die Mitte des Bereichs.
            group = 224 if ktv_group == "anim" else (int(ktv_group) - 1) * 32 + 16
            n = int(ktv_effect)
            effect = 2 if n <= 0 else 6 * n + 3
            age = now - self.ktv_t.setdefault(fx.name, now)
            if age < KTV_PRESET_S:                    # noch ohne Strahl: nur die Werte
                on = False
            elif age < KTV_PRESET_S + KTV_KICK_S:     # andere Werte, damit das Geraet eine Aenderung sieht
                group = group + 32 if group < 160 else 16
                effect = effect + 6 if effect <= 243 else effect - 6
            fx.values["power"] = 255 if on else 0
            fx.values["group"] = group
            fx.values["effect"] = effect
            fx.values["color"] = {"rot": 10, "gruen": 17, "blau": 27}.get(color, 255)
            fx.values["color_speed"] = tempo
            fx.values["auto"] = 40
            beams = ["power"]
        elif fx.type == "laser_ktv34":                    # Profi-Modus: Kanal 15 (effect) bleibt 0, kein Selbstlauf. Muster B bleibt aus.
            fx.values["power"] = 255 if on else 0
            fx.values["color"] = {"rot": 10, "gruen": 17, "blau": 27}.get(color, 255)
            fx.values["color_speed"] = tempo
            fx.values["group"] = 224 if ktv_group == "anim" else (int(ktv_group) - 1) * 32 + 16
            fx.values["pattern"] = min(255, 6 * int(ktv_effect) + 3)
            fx.values["size"] = int(p["ktv_size"])
            fx.values["zoom"] = int(p["ktv_zoom"])
            fx.values["rotate"] = int(p["ktv_rotate"])
            fx.values["pos_x"] = int(p["ktv_pos_x"])
            fx.values["pos_y"] = int(p["ktv_pos_y"])
            fx.values["wave_x"] = int(p["ktv_wave"])
            fx.values["draw"] = int(p["ktv_fan"])
            fx.values["effect"] = int(p["ktv_fx"])                # Regler endet bei 244: nie Selbstlauf- oder Sound-Bereich
            beams = ["power"]
        elif fx.type == "derby_4in1_15ch":                # kein blauer Laser: wie bunt
            red, green = color != "gruen", color != "rot"
            fx.values["laser_effect"] = 16 + (muster % 16) * 15 + 7
            fx.values["laser_red"] = 255 if on and red else 0
            fx.values["laser_green"] = 255 if on and green else 0
            fx.values["laser_red8"] = 255 if on and red else 0
            fx.values["laser_motor"] = 192 + tempo * 63 // 255
            fx.values["speed"] = tempo
            beams = ["laser_red", "laser_green", "laser_red8"]
        else:                                             # eigener Typ mit Laser-Kanaelen: Belegung unbekannt, bleibt gesperrt
            fx.laser_unlock = False
            self.laser_live = False
            return
        if not strobe:
            for p in beams:
                fx.values[p] = self.limiter.filter((fx.name, p), fx.values[p], now)

    def _apply_state(self, fx, st, zones, master, strobe):
        dim = st.get(fm.A_DIMMER)
        col = st.get(fm.A_COLOR)
        if dim is not None or col is not None:
            k = (1.0 if dim is None else dim / 255.0) * master
            if zones:
                c = col
                for z in zones:
                    if c is None:                         # nur Dimmer programmiert: weiss
                        if "w" in z and not fx.white_mix:
                            vals = {"w": 255}
                        elif "r" in z:
                            vals = {"r": 255, "g": 255, "b": 255}
                        else:
                            vals = {"uv": 255}
                    elif "r" in z:
                        vals = {"r": c[0], "g": c[1], "b": c[2], "w": c[3], "uv": c[4]}
                    else:                                 # nur UV-Reihen: die staerkste Farbe gibt die Helligkeit vor
                        vals = {"uv": max(c)}
                    if fx.white_mix and vals.get("w"):
                        w = vals.pop("w")
                        for q in "rgb":
                            vals[q] = min(255, vals.get(q, 0) + w)
                    for q, v in vals.items():
                        if q in z and z[q] in fx.values and z[q] not in fx.locked_params:
                            fx.values[z[q]] = max(0, min(255, int(v * k + 0.5)))
            elif "dimmer" in fx.map:
                fx.values["dimmer"] = max(0, min(255, int((255 if dim is None else dim) * master + 0.5)))
        mv = st.get(fm.A_MOVE)
        if mv is not None:
            self._move(fx, mv)
        for a, v in st.items():
            if a in (fm.A_DIMMER, fm.A_COLOR, fm.A_MOVE, fm.A_LASER):
                continue
            if a == "preset":
                pid = int(v + 0.5)
                if pid in EB_STROBE and not strobe:
                    pid = 0
                fx.values["preset"] = pid
                if "dimmer" in fx.map and dim is None:    # nur ein Preset programmiert: das Band leuchtet
                    fx.values["dimmer"] = max(0, min(255, int(255 * master)))
            elif a in ("pan", "tilt") and a + "_fine" in fx.map:
                self._set16(fx, a, v)
            elif a in fx.values:
                x = v * master if a in fx.light_params else v
                fx.values[a] = max(0, min(255, int(x + 0.5)))

    def _set16(self, fx, a, v):
        """Pan und Tilt mit Feinkanal; v als Gleitkommazahl 0..255, im erlaubten Bereich."""
        lo, hi = fx.limits.get(a, (0, 255))
        v = max(float(lo), min(float(hi), v))
        coarse = int(v)
        fx.values[a] = coarse
        fx.values[a + "_fine"] = 0 if coarse >= hi else int((v - coarse) * 255)

    def _move(self, fx, mv):
        parts = self.parts[fx.name]
        u, v = mv
        for params, x in ((parts["pu"], u), (parts["pv"], v)):
            for p in params:
                lo, hi = parts["lim"][p]
                val = lo + (hi - lo) * x
                if p + "_fine" in fx.map:
                    self._set16(fx, p, val)
                else:
                    fx.values[p] = int(val + 0.5)

    # ---- Anzeige --------------------------------------------------------------------------------------
    def status(self, now, strobe=False):
        c = self.compiled
        ck = self.clock
        return {"name": self.doc_name, "loaded": self.loaded, "on": self.active(), "light": self.light, "playing": ck.playing,
                "pos": round(ck.position(now), 3), "duration": c.duration if c else 0, "src": ("mixxx" if self.owner == MIXXX else ck.source(now)) if ck.playing else "",
                "err_ms": round(ck.err * 1000, 1), "rate": round(ck.rate, 4), "owner": self.owner or "", "ended": self.ended,
                "strobe": bool(strobe), "uses_strobe": bool(c and c.uses_strobe),
                "uses_laser": bool(c and c.uses_laser), "uses_fog": bool(c and c.fog_cues), "laser_live": self.laser_live}

    def values_for(self, name, t):
        """Anzeige im Editor: die Werte eines Geraets zum Zeitpunkt t, unabhaengig vom laufenden Bild."""
        c, fx = self.compiled, self.rig.by_name.get(name)
        if c is None or fx is None:
            return {}
        out = {}
        for a, v in c.evaluate(t, self.frame, False, only=name).get(name, {}).items():
            if a == fm.A_LASER:
                out[a] = "an" if v[0] >= 0.5 else "aus"
            else:
                out[a] = [round(x, 3) for x in v] if isinstance(v, tuple) else round(v, 1)
        return out

    def dmx_for(self, name):
        """Was gerade fuer dieses Geraet rausgeht (mit allen Grenzen)."""
        fx = self.rig.by_name.get(name)
        if fx is None:
            return {}
        buf = bytearray(512)
        fx.write(buf)
        return {p: buf[fx.address - 1 + ch - 1] for p, ch in fx.map.items() if 0 <= fx.address - 1 + ch - 1 < 512}
