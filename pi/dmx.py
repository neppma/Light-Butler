#!/usr/bin/env python3
"""
dmx.py - Rig-Verwaltung, Sicherheitslogik und Art-Net-Ausgabe (Phase 2).

Die Szenen-Engine (Phase 3) benutzt nur diese Schnittstelle:

    rig = Rig("fixtures.yaml")
    out = Output(rig, lambda ip: ArtNetSender(ip, rig.universe))
    out.start()
    rig["docooler_1"].set_zone(0, r=255)        # Zelle 1 rot
    rig.group("bars")                          # Liste der Fixtures einer Gruppe
    out.stop()                                 # Blackout + Ende

SICHERHEIT (wird bei JEDEM Frame in Fixture.write erzwungen):
  * Typen mit "locked: true" (Hazer) senden immer 0 auf allen Kanaelen.
  * "rest_values" (nur KTV-Laser, Kanal Effektgruppe): Ruhewert statt 0, solange der Laser gesperrt ist, damit sein
    Motor nicht dauernd surrt. Nur fuer Typen mit gesperrtem Kanal "power" und nie fuer "power" selbst (siehe Rig.check).
  * "locked_channels" (Laser-Kanaele von 21 Eyes und Derby) senden immer 0.
  * "safe_limits" (Modus-/Reset-Kanaele) werden auf den erlaubten Bereich begrenzt.
"""
import os
import socket
import struct
import threading
import time

import yaml

ARTNET_PORT = 6454


class ArtNetSender:
    """Sendet ArtDmx-Pakete per UDP (Unicast) an den OLA-Pi."""

    def __init__(self, target, universe=0, port=ARTNET_PORT):
        self.addr = (target, port)
        self.universe = universe
        self.seq = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, data):
        self.seq = self.seq % 255 + 1  # 1..255 (0 = Sequenz aus)
        pkt = (b"Art-Net\x00" + struct.pack("<H", 0x5000)   # OpOutput/ArtDmx
               + struct.pack(">H", 14)                      # Protokollversion
               + bytes([self.seq, 0])                       # Sequenz, Physical
               + struct.pack("<H", self.universe & 0x7FFF)  # SubUni + Net
               + struct.pack(">H", len(data)) + bytes(data))
        self.sock.sendto(pkt, self.addr)

    def close(self):
        self.sock.close()


class PrintSender:
    """Trockenlauf: gibt nur die geaenderten, von 0 verschiedenen Kanaele aus."""

    def __init__(self, label=""):
        self.label = label
        self.last = None

    def send(self, data):
        if data != self.last:
            self.last = bytes(data)
            nz = {i + 1: v for i, v in enumerate(data) if v}
            print(f"[{self.label}] DMX:", ", ".join(f"{k}={v}" for k, v in nz.items()) or "(alles 0)")

    def close(self):
        pass


def wled_set(ip, on):
    """Schaltet ein WLED-Geraet ueber die JSON-API ein/aus (best effort, 1 s Timeout)."""
    import json
    import urllib.request
    req = urllib.request.Request(
        f"http://{ip}/json/state", data=json.dumps({"on": bool(on)}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=1.0).read()
        return True
    except Exception:
        return False


def slew(cur, target, rate, dt):
    """Bewegt cur hoechstens um rate*dt auf target zu (weiche, begrenzte Bewegung)."""
    step = rate * dt
    if abs(target - cur) <= step:
        return target
    return cur + step if target > cur else cur - step


def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(round(v))))


class Fixture:
    def __init__(self, name, ftype, tdef, address, group, dead=(), target=None, extra=None):
        self.name, self.type, self.address, self.group = name, ftype, address, group
        self.dead = set(dead)  # defekte LED-Kanaele (nur Hinweis fuer die Szenen-Engine)
        self.target = target   # eigene Art-Net-Ziel-IP (z. B. WLED), None = Standardziel
        self.extra = extra or {}
        self.tdef = tdef
        self.map = tdef["map"]
        self.n = tdef["channels"]
        self.defaults = tdef.get("defaults", {})
        self.locked = bool(tdef.get("locked", False))
        self.locked_params = set(tdef.get("locked_channels", []))
        # Ruhewerte gesperrter Kanaele (KTV: Effektgruppe 255, Motor still). Nie fuer den Leistungskanal "power",
        # nur wenn "power" selbst gesperrt ist: der Laser bleibt damit sicher aus.
        rest = tdef.get("rest_values", {}) if "power" in self.locked_params else {}
        self.rest = {k: clamp(int(v)) for k, v in rest.items() if k in self.locked_params and k != "power"}
        self.blitz_ok = bool(self.extra.get("blitz", tdef.get("blitz", True)))   # False: nicht im allgemeinen Strobe
        self.hw_unlock = set()                                                    # Einzel-Strobe: Grenzen dieser Kanaele in diesem Bild aufgehoben
        self.limits = {k: tuple(v) for k, v in tdef.get("safe_limits", {}).items()}
        self.presets = tdef.get("presets", {})
        self.white_mix = bool(tdef.get("white_mix", False))
        self.manual_ok = bool(tdef.get("manual_allowed", False))   # nur der Hazer, nie die Laser
        self.manual_vals, self.manual_until = None, 0.0
        # Laser-Kanaele (nur 21 Eyes, Derby): gesperrt, ausser die Show gibt sie in diesem Frame frei
        self.laser_params = set(tdef.get("laser_channels", []))
        self.laser_unlock = False
        self.sound_mode = tdef.get("sound_mode")           # Wert des Mode-Kanals fuer den internen Sound-Modus (falls bekannt)
        self.auto_mode = tdef.get("auto_mode")             # Wert des Mode-Kanals fuer das eigene AUTO-Programm (falls bekannt)
        self.allowed_modes = {int(m) for m in (self.sound_mode, self.auto_mode) if m is not None}
        self.mode_unlock = False                           # nur in der Laser-Szene mit Sound-Betrieb gesetzt
        # Gruppen-Helligkeit: skaliert nur die Licht-Kanaele (Farben, UV, Dimmer bei Geraeten ohne Farbzonen) beim Schreiben
        self.level = 1.0
        zs = self.zones()
        self.light_params = {p for z in zs for p in z.values()}
        if not zs and "dimmer" in self.map:
            self.light_params.add("dimmer")
        # Installationsspezifische Grenzen (z. B. Richtungsbegrenzung des Moving Heads)
        for k, v in self.extra.get("limits", {}).items():
            self.limits[k] = tuple(v)
        self.mirror = {ax: bool(self.extra.get(f"{ax}_mirror")) for ax in ("pan", "tilt")}
        self.move16 = {}
        ln = self.extra.get("limits_norm")
        if ln:
            for ax in ("pan", "tilt"):
                lo, hi = ln[ax]
                if self.extra.get(f"{ax}_invert"):
                    lo, hi = 1.0 - hi, 1.0 - lo
                self.limits[ax] = (int(round(255 * lo)), int(round(255 * hi)))
                self.move16[ax] = (self.limits[ax][0] * 256, self.limits[ax][1] * 256)
        self.values = {}
        self.reset()

    # ---- Werte -------------------------------------------------------
    def reset(self):
        self.values = {p: 0 for p in self.map}
        self.values.update({k: v for k, v in self.defaults.items() if k in self.map})
        self.values.update({k: v for k, v in self.extra.get("defaults", {}).items() if k in self.map})
        for ax in ("pan", "tilt"):          # Parkposition = Mitte des erlaubten Bereichs
            if ax in self.limits and ax in self.map:
                lo, hi = self.limits[ax]
                self.values[ax] = (lo + hi) // 2
                if ax + "_fine" in self.map:
                    self.values[ax + "_fine"] = 0

    def set(self, param, value):
        if param not in self.map:
            if self.tdef.get("custom") or self.extra.get("user_added"):     # eigene Typen: fehlende Kanaele (z. B. strobe) ignorieren
                return
            raise KeyError(f"{self.name}: unbekannter Parameter '{param}'")
        self.values[param] = clamp(value)

    def get(self, param):
        return self.values[param]

    def usable(self, param):
        return param in self.map and param not in self.dead

    def preset(self, param, name):
        pr = self.presets.get(param)
        if (pr is None or name not in pr) and (self.tdef.get("custom") or self.extra.get("user_added")):
            return                                   # eigene/importierte Typen ohne dieses Rad oder Fach: nichts tun
        self.set(param, self.presets[param][name])

    # ---- Farbzonen (Zellen, Reihen, ...) -----------------------------------
    def zones(self):
        m = self.map
        if "r1" in m:  # Docooler: zwei Zellen; importierte Geraete (Open Fixture Library) auch mehr (r3, g3, ...)
            zs = []
            i = 1
            while f"r{i}" in m:
                zs.append({k: f"{k}{i}" for k in ("r", "g", "b", "w", "uv") if f"{k}{i}" in m or k in ("r", "g", "b", "w")})
                i += 1
        elif "led_r" in m:  # 21 Eyes (nur LEDs + UV)
            zs = [{"r": "led_r", "g": "led_g", "b": "led_b", "uv": "uv"}]
        elif "r" in m:  # 4in1, PAR, Derby, Ambiente
            zs = [{k: k for k in ("r", "g", "b", "w", "uv") if k in m}]
        elif "uv1" in m:  # BUV463: vier UV-Reihen
            zs = []
            i = 1
            while f"uv{i}" in m:             # BUV463 hat vier, importierte Geraete auch mehr
                zs.append({"uv": f"uv{i}"})
                i += 1
        else:
            zs = []
        return zs

    def set_zone(self, i, r=None, g=None, b=None, w=None, uv=None):
        z = self.zones()[i]
        if self.white_mix and w:
            # Kein echtes Weiss-LED: Weiss wird ueber R, G, B zugemischt
            r, g, b = (min(255, (c or 0) + w) for c in (r, g, b))
            w = None
        for key, val in (("r", r), ("g", g), ("b", b), ("w", w), ("uv", uv)):
            if val is not None and key in z:
                self.set(z[key], val)

    def set_color(self, r=0, g=0, b=0, w=0, uv=0):
        for i in range(len(self.zones())):
            self.set_zone(i, r=r, g=g, b=b, w=w, uv=uv)

    def blackout(self):
        self.manual_vals, self.manual_until = None, 0.0   # Handbetrieb (Nebel) immer beenden
        self.laser_unlock = False                          # Laser-Freigabe immer beenden
        self.mode_unlock = False
        zs = self.zones()
        if zs:
            self.set_color(0, 0, 0, 0, 0)
        elif "dimmer" in self.map:
            self.set("dimmer", 0)

    # ---- Ausgabe mit Sicherheitslogik ----------------------------------------
    def manual(self, vals, seconds):
        """Zeitlich begrenzter Handbetrieb (z. B. Nebelschub). Nur fuer Geraete mit manual_allowed."""
        if not self.manual_ok:
            return False
        self.manual_vals = {k: clamp(v) for k, v in vals.items() if k in self.map}
        self.manual_until = time.time() + max(0.0, min(10.0, float(seconds)))
        return True

    def write(self, buf):
        active = (self.locked and self.manual_ok and self.manual_vals is not None
                  and time.time() < self.manual_until)
        for param, ch in self.map.items():
            v = self.values[param]
            if active:
                v = self.manual_vals.get(param, 0)
            elif self.locked:
                v = 0
            elif param in self.locked_params and not (self.laser_unlock and param in self.laser_params):
                v = self.rest.get(param, 0)                  # gesperrt: 0, beim KTV-Laser Ruhewert (Leistung bleibt 0)
            elif param == "mode" and self.mode_unlock and int(v) in self.allowed_modes:
                v = clamp(int(v), 0, 255)                    # nur die eingetragenen Werte (Sound, Auto), nur in der Laser-Szene
            elif param in self.hw_unlock:
                v = clamp(v)                                     # nur beim Einzel-Strobe (zum Beispiel Mode 230 der 4in1-Washes)
            elif param in self.limits:
                lo, hi = self.limits[param]
                v = clamp(v, lo, hi)
            if self.level != 1.0 and v and param in self.light_params and not active:
                v = clamp(int(round(v * self.level)), 0, 255)
            idx = self.address - 1 + ch - 1
            if 0 <= idx < 512:
                buf[idx] = v


# Fremde DMX-Daten (Art-Net-Eingang) ohne Strobe-Erlaubnis: Strobe-Kanaele aus, Shutter offen statt
# Strobo, Eyes-Blitz hoechstens "an" (1-4). Mit Erlaubnis gehen diese Werte unveraendert durch.
EXT_NO_STROBE = {"strobe": lambda v: 0, "strobe_a": lambda v: 0, "strobe_b": lambda v: 0,
                 "shutter": lambda v: 255 if 5 <= v <= 250 else v, "flash": lambda v: min(v, 4)}


def filter_external(fx, src, dst, strobe_ok):
    """Ein Fixture aus einem fremden DMX-Bild uebernehmen, mit derselben Sicherheitslogik wie Fixture.write:
    gesperrte Typen (Hazer) 0, Laser-Kanaele 0 bzw. Ruhewert (nie freigegeben), safe_limits, Strobe nur mit Erlaubnis."""
    for param, ch in fx.map.items():
        idx = fx.address - 1 + ch - 1
        if not 0 <= idx < 512:
            continue
        v = src[idx]
        if fx.locked:
            v = 0
        elif param in fx.locked_params:
            v = fx.rest.get(param, 0)
        elif param in fx.limits:
            lo, hi = fx.limits[param]
            v = clamp(v, lo, hi)
        if not strobe_ok and param in EXT_NO_STROBE:
            v = EXT_NO_STROBE[param](v)
        dst[idx] = v


class Rig:
    def __init__(self, path="fixtures.yaml"):
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        # Aenderungen aus dem Web-Panel (fixtures_user.json) einarbeiten; ein Fehler dort darf den Start nie verhindern
        import copy as _copy
        self.base_cfg = _copy.deepcopy(cfg)
        self.user, self.user_warning = None, ""
        try:
            import fixture_edit as _fe
            self.user_path = _fe.user_path_for(path, cfg)
            self.user, self.user_warning = _fe.load_user(self.user_path)
            merged = _fe.apply_user(cfg, self.user)
            Rig._check_merged(merged)
            cfg = merged
        except Exception as e:                       # noqa: BLE001
            print(f"Hinweis: Aenderungen aus dem Panel nicht benutzt ({e})")
            self.user_warning = f"Aenderungen aus dem Panel nicht benutzt: {e}"
            self.user_path = os.path.join(os.path.dirname(os.path.abspath(path)), "fixtures_user.json")
            try:
                import fixture_edit as _fe
                self.user = _fe.empty_user()
            except Exception:                        # noqa: BLE001
                self.user = None
        self.cfg = cfg
        self.universe = int(cfg.get("universe", 0))
        self.target = cfg.get("artnet_target", "127.0.0.1")
        self.dmx_port = None                         # Geraetedatei des USB-DMX-Adapters (None = automatisch suchen)
        self.fixtures = []
        self.by_name = {}
        for e in cfg["fixtures"]:
            tdef = cfg["types"][e["type"]]
            fx = Fixture(e["name"], e["type"], tdef, e["address"], e.get("group", ""),
                         dead=e.get("dead", ()), target=e.get("target"), extra=e)
            self.fixtures.append(fx)
            self.by_name[fx.name] = fx
        # Nanoleaf Light Panels: jedes leuchtende Panel wird ein Fixture (3 Kanaele R, G, B) in einem eigenen
        # "Universum" mit dem Ziel "nanoleaf:<ip>". Ohne nanoleaf.json bleibt alles wie bisher.
        self.nano = None
        self.nano_file_host = None                      # IP aus nanoleaf.json (im Panel aenderbar, siehe nano_host)
        self.nano_path = None                           # Pfad der nanoleaf.json (Token im Panel aenderbar, nie lesbar)
        self.nano_token_changed = False                 # neuer Token gespeichert, gilt nach dem Neustart
        nf = cfg.get("nanoleaf_file", "nanoleaf.json")
        if nf:
            npath = nf if os.path.isabs(nf) else os.path.join(os.path.dirname(os.path.abspath(path)), nf)
            try:
                from nanoleaf import load_config
                ncfg = load_config(npath)
            except Exception as e:                      # defekte Datei darf die Show nicht verhindern
                print(f"Hinweis: nanoleaf.json nicht benutzt ({e})")
                ncfg = None
            if ncfg:
                self.nano_file_host, self.nano_path = ncfg["host"], npath
                if cfg.get("nano_host"):                # eigene IP aus dem Panel (fixtures_user.json)
                    ncfg = dict(ncfg, host=cfg["nano_host"])
            if ncfg and ncfg.get("panels"):
                self.nano = ncfg
                tdef = cfg["types"].get("nanoleaf_panel", {"channels": 3, "map": {"r": 1, "g": 2, "b": 3}})
                tgt = f"nanoleaf:{ncfg['host']}"
                for i, p in enumerate(ncfg["panels"]):
                    ex = {"nr": 100 + i, "label": f"Nanoleaf Panel {p['id']}", "x": p.get("x", 0.5), "y": p.get("y", 0.5),
                          "nano_id": p["id"]}
                    fx = Fixture(f"nano_{p['id']}", "nanoleaf_panel", tdef, 1 + 3 * i, "nano", target=tgt, extra=ex)
                    self.fixtures.append(fx)
                    self.by_name[fx.name] = fx
        self.lock = threading.Lock()
        self.blackout()  # Start immer dunkel (auch der Vega mit Dimmer 0)

    @staticmethod
    def _check_merged(cfg):
        """Zusammengefuehrte Daten grob pruefen, damit ein kaputter Eintrag den Start nicht verhindert."""
        for e in cfg["fixtures"]:
            t = cfg["types"][e["type"]]
            a = int(e["address"])
            if not 1 <= a <= 512 - t["channels"] + 1:
                raise ValueError(f"{e['name']}: DMX-Adresse {a} ungueltig")

    def __getitem__(self, name):
        return self.by_name[name]

    def group(self, name):
        return [f for f in self.fixtures if f.group == name]

    def groups(self):
        seen = []
        for f in self.fixtures:
            if f.group not in seen:
                seen.append(f.group)
        return seen

    def blackout(self):
        for f in self.fixtures:
            f.blackout()

    def dmx_channels(self):
        """Hoechster belegter Kanal der DMX-Kette (Fixtures ohne eigenes Ziel). Ueber USB wird nur bis dahin gesendet:
        ein kuerzeres Bild ist schneller draussen, so passt jedes der 40 Show-Bilder pro Sekunde sicher auf die Leitung."""
        return max([f.address + f.n - 1 for f in self.fixtures if not f.target] or [512])

    def targets(self):
        """Alle Art-Net-Ziele (Standardziel zuerst)."""
        out = [self.target]
        for f in self.fixtures:
            if f.target and f.target not in out:
                out.append(f.target)
        return out

    def render_all(self):
        """Ein 512-Kanal-Frame pro Ziel-IP: {ip: bytes}."""
        bufs = {t: bytearray(512) for t in self.targets()}
        for f in self.fixtures:
            f.write(bufs[f.target or self.target])
        return {t: bytes(b) for t, b in bufs.items()}

    def filter_external(self, data, strobe_ok=False):
        """Fremdes DMX-Bild fuer die DMX-Kette absichern. Kanaele ohne eingetragenes Fixture bleiben 0."""
        out = bytearray(512)
        for f in self.fixtures:
            if not f.target:
                filter_external(f, data, out, strobe_ok)
        return bytes(out)

    def render(self):
        """Frame fuer das Standardziel (OLA)."""
        return self.render_all()[self.target]

    def check(self):
        """Prueft Adressen auf Ueberlappung und Kanalnummern gegen die Kanalzahl."""
        problems, used = [], {}
        for f in self.fixtures:
            if f.address + f.n - 1 > 512:
                problems.append(f"{f.name}: Adressbereich ueber 512")
            for param, ch in f.map.items():
                if ch < 1 or ch > f.n:
                    problems.append(f"{f.name}: Kanal {ch} ({param}) ausserhalb 1..{f.n}")
            tgt = f.target or self.target
            for a in range(f.address, f.address + f.n):
                if (tgt, a) in used:
                    problems.append(f"Ueberlappung bei Adresse {a} ({tgt}): "
                                    f"{used[(tgt, a)]} / {f.name}")
                used[(tgt, a)] = f.name
            want = f.tdef.get("rest_values", {})
            if want and ("power" not in f.locked_params or "power" in want or set(want) - f.locked_params):
                problems.append(f"{f.name}: rest_values nur fuer gesperrte Kanaele ausser 'power', und 'power' muss gesperrt sein")
        return problems


def make_sender(rig, ip, dry_run=False):
    """Passenden Sender fuer ein Ziel: Art-Net (OLA, WLED) oder Nanoleaf-Streaming."""
    if dry_run:
        return PrintSender(ip)
    if str(ip).startswith("nanoleaf:"):
        from nanoleaf import NanoleafSender
        return NanoleafSender(rig.nano)
    if ip == rig.target:                     # DMX-Kette: Art-Net zum OLA-Pi oder direkt ueber den USB-Adapter (dmx_usb.py)
        from dmx_usb import DmxRouter, OpenDmxSender
        return DmxRouter(ArtNetSender(ip, rig.universe),
                         lambda: OpenDmxSender(rig.dmx_port, rig.dmx_channels()))
    return ArtNetSender(ip, rig.universe)


class Output:
    """Sendet den Rig mit 40 Hz; ein Art-Net-Sender pro Ziel-IP (OLA und WLEDs).

    make_sender(ip) liefert ein Objekt mit send(data) und close().
    """

    def __init__(self, rig, make_sender, rate=40):
        self.rig, self.dt = rig, 1.0 / rate
        self.senders = {t: make_sender(t) for t in rig.targets()}
        self.mode = {t: "on" for t in self.senders}      # on | closing (Blackout-Bilder) | off (es wird nichts gesendet)
        self._tick = threading.Event()                   # von der Show nach jedem Bild gesetzt
        self.synced = False                              # True, sobald eine Show das Senden taktet
        self.close_left = {}
        self._run = False
        self._thread = None
        self.http = wled_set                              # WLED-JSON-API (in Tests austauschbar)
        self.ext = None                                   # artnet_in.ArtNetIn: fremde DMX-Daten fuer die DMX-Kette
        self.ext_on, self.ext_strobe = False, False       # von der Show gesetzt (Einstellung artnet_in, Strobe-Erlaubnis)
        self.send_errors = 0                              # fehlgeschlagene Sendungen (Seite Zustand)
        self.last_sent = {}                               # zuletzt gesendetes Bild je Ziel (DMX-Monitor)
        self.debug = None                                 # dmx_debug.DmxDebug: Seite /dmx-debug, ersetzt eingeschaltet das Bild der DMX-Kette

    def _wled_exit_off(self, targets=None):
        """WLED-Ziele mit "on_exit: off", nur im echten Betrieb (nie im Trockenlauf/Simulator: kein Zugriff auf Geraete)."""
        out = []
        for fx in self.rig.fixtures:
            t = fx.target
            if (fx.extra.get("on_exit") in ("off", False) and t and t not in out and (targets is None or t in targets)
                    and t in self.senders and not isinstance(self.senders[t], PrintSender)):
                out.append(t)
        return out

    def wake_wled(self, targets):
        """WLED mit "on_exit: off" beim Start wieder einschalten, bevor Art-Net uebernimmt (im Hintergrund, best effort).
        Ein per JSON ausgeschaltetes WLED, das Art-Net empfaengt, blinkt wild (Couchtisch nach dem Neustart der Show)."""
        ts = self._wled_exit_off(targets)
        if ts:
            threading.Thread(target=lambda: [self.http(t, True) for t in ts], daemon=True).start()
        return ts

    def set_enabled(self, target, on, blackout=True):
        """Ausgabe an ein Ziel ein- oder ausschalten. Beim Ausschalten gehen erst einige Blackout-Bilder raus, damit
        keine alten Werte beim Empfaenger (OLA) haengen bleiben und andere Art-Net-Sender frei sind.
        blackout=False (WLED): einfach aufhoeren, das Geraet kehrt nach seinem Timeout zu seinem eigenen Zustand zurueck."""
        cur = self.mode.get(target)
        if cur is None:
            return
        snd = self.senders.get(target)
        if on:
            self.mode[target] = "on"
            if cur != "on" and hasattr(snd, "resume"):           # z. B. Nanoleaf: Streaming wieder aufnehmen
                snd.resume()
        elif cur == "on":
            if blackout:
                self.mode[target] = "closing"
                self.close_left[target] = 6
            else:
                self.mode[target] = "off"
                if hasattr(snd, "pause"):                        # z. B. Nanoleaf: Panels freigeben
                    snd.pause()

    def is_sending(self, target):
        return self.mode.get(target, "on") != "off"

    def _send_all(self, frames):
        for t, data in frames.items():
            m = self.mode.get(t, "on")
            if m == "off":
                continue
            if m == "closing":
                data = bytes(len(data))
                self.close_left[t] -= 1
                if self.close_left[t] <= 0:
                    self.mode[t] = "off"
            self.last_sent[t] = data                     # fuer den DMX-Monitor im Panel (genau das, was rausgeht)
            try:
                self.senders[t].send(data)
            except OSError:
                self.send_errors += 1  # ein nicht erreichbares Geraet darf die Show nicht stoppen

    def start(self):
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def notify(self):
        """Die Show meldet: ein neues Bild ist fertig. Die Ausgabe sendet es sofort (genau einmal)."""
        self.synced = True
        self._tick.set()

    def _loop(self):
        nxt = time.perf_counter()
        while self._run:
            if self.synced:
                self._tick.wait(0.1)                    # normalerweise vom Takt der Show geweckt, sonst nach 0,1 s trotzdem senden
                self._tick.clear()
            with self.rig.lock:
                frames = self.rig.render_all()
            self._apply_ext(frames)
            if self.debug is not None:
                raw = self.debug.frame()
                if raw is not None:
                    frames[self.rig.target] = raw      # roh, ohne Sperren: siehe dmx_debug.py
            self._send_all(frames)
            if not self.synced:
                nxt += self.dt
                time.sleep(max(0, nxt - time.perf_counter()))

    def ext_active(self):
        return bool(self.ext_on and self.ext is not None and self.ext.active())

    def _apply_ext(self, frames):
        """Art-Net-Eingang: kommen fremde Daten, ersetzen sie (abgesichert) das Bild der DMX-Kette."""
        if not self.ext_on or self.ext is None:
            return
        data = self.ext.frame()
        if data is not None:
            frames[self.rig.target] = self.rig.filter_external(data, self.ext_strobe)

    def stop(self):
        """Blackout, einige Frames senden (falls Pakete verloren gehen), dann Ende."""
        if self.debug is not None:
            self.debug.arm(False)
        with self.rig.lock:
            self.rig.blackout()
        time.sleep(0.3)
        self._run = False
        if self._thread:
            self._thread.join(timeout=1)
        with self.rig.lock:
            frames = self.rig.render_all()
        for _ in range(5):
            self._send_all(frames)
            time.sleep(0.03)
        for snd in self.senders.values():
            snd.close()
        # WLED kehrt nach dem Ende der Art-Net-Daten zu seinem eigenen Zustand zurueck.
        # Mit "on_exit: off" in der YAML wird das Geraet dann ausgeschaltet.
        for t in self._wled_exit_off():
            if self.mode.get(t) != "off":                      # ist die Ausgabe zu diesem Geraet aus, wird es nicht angefasst
                self.http(t, False)
