#!/usr/bin/env python3
"""
nanoleaf.py - Nanoleaf Light Panels (Aurora) als weitere Lichtquelle der Show.

Die Show berechnet pro Panel eine Farbe. Hier werden sie per UDP "External Control" (extControl)
direkt an die Panels gestreamt, nicht ueber openHAB (zu traege fuer Takt und Beat).

Einrichtung (einmalig, auf dem Pi in ~/lichtshow):

  1. nanoleaf.json anlegen:   {"host": "192.168.1.33", "token": "<API-Key>"}
     Der Token ist derselbe wie im openHAB-Binding (Thing "Nanoleaf Controller" -> authToken).
     Er kann parallel von mehreren Programmen benutzt werden.
  2. python3 nanoleaf.py --setup     liest Modell, Firmware und die Panel-Anordnung und speichert sie
  3. python3 nanoleaf.py --test      laesst die Panels der Reihe nach leuchten (Zuordnung pruefen)
  4. Dienst neu starten:  sudo systemctl restart lichtshow

Weitere Optionen in nanoleaf.json (alle optional):
  "fps": 10          Pakete pro Sekunde (die Panels vertragen etwa 10 bis 20)
  "trans": 1         Ueberblendzeit je Paket in Zehntelsekunden (1 = 0,1 s, weicher Verlauf)
  "protocol": "v1"   "v1" fuer Light Panels/Aurora (Standard), "v2" fuer Canvas/Shapes
  "on_exit": "restore"   beim Beenden: "restore" = vorherigen Effekt, "off" = ausschalten, "keep" = lassen
  "port": 16021      Port der Nanoleaf-API
"""
import argparse
import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_FILE = "nanoleaf.json"
NOT_LIGHTS = (1, 12, 999)          # shapeType: Rhythm-Modul, Controller, Netzteil haben keine LEDs


class NanoleafError(Exception):
    pass


# ---- Konfiguration -------------------------------------------------------------------------------------
def load_config(path=DEFAULT_FILE):
    """nanoleaf.json laden; None, wenn es die Datei nicht gibt (dann ist Nanoleaf einfach aus)."""
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("host") or not cfg.get("token"):
        raise NanoleafError("nanoleaf.json braucht 'host' und 'token'")
    return cfg


def save_config(cfg, path=DEFAULT_FILE):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)                 # enthaelt den API-Key
    except OSError:
        pass


def panels_from_layout(layout):
    """Aus panelLayout/layout die leuchtenden Panels mit normierter Lage (x, y 0..1) bestimmen."""
    pd = [p for p in layout.get("positionData", []) if p.get("shapeType") not in NOT_LIGHTS]
    if not pd:
        return []
    xs, ys = [p["x"] for p in pd], [p["y"] for p in pd]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    out = []
    for p in sorted(pd, key=lambda p: (p["x"], p["y"], p["panelId"])):
        out.append({"id": int(p["panelId"]),
                    "x": round((p["x"] - x0) / (x1 - x0), 4) if x1 > x0 else 0.5,
                    "y": round((p["y"] - y0) / (y1 - y0), 4) if y1 > y0 else 0.5})
    return out


# ---- HTTP-Client (Nanoleaf OpenAPI) ----------------------------------------------------------------------
class Client:
    def __init__(self, host, token, port=16021, timeout=3.0):
        self.host, self.token, self.port, self.timeout = host, token, int(port), timeout

    def _req(self, method, path, body=None):
        url = f"http://{self.host}:{self.port}/api/v1/{self.token}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raise NanoleafError(f"HTTP {e.code} bei {method} {path.split('?')[0] or '/'}") from None
        except (urllib.error.URLError, OSError) as e:
            raise NanoleafError(f"{self.host} nicht erreichbar ({e})") from None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return raw.decode(errors="replace").strip().strip('"')

    def info(self):
        return self._req("GET", "")

    def layout(self):
        return self._req("GET", "/panelLayout/layout")

    def current_effect(self):
        r = self._req("GET", "/effects/select")
        return r if isinstance(r, str) else None

    def select_effect(self, name):
        self._req("PUT", "/effects", {"select": name})

    def effects(self):
        """Effekte auf dem Geraet: [{"name", "rhythm"}]. rhythm: reagiert auf das Akustikmodul."""
        names = self._req("GET", "/effects/effectsList")
        rhythm = set()
        try:
            r = self._req("PUT", "/effects", {"write": {"command": "requestAll"}})
            for a in (r.get("animations") or []) if isinstance(r, dict) else []:
                if a.get("pluginType") == "rhythm":
                    rhythm.add(a.get("animName"))
        except NanoleafError:
            pass                                                # ohne Angabe bleibt die Liste brauchbar
        return [{"name": n, "rhythm": n in rhythm} for n in (names if isinstance(names, list) else []) if isinstance(n, str) and not n.startswith("*")]

    def set_power(self, on):
        self._req("PUT", "/state", {"on": {"value": bool(on)}})

    def start_ext(self, version="v1"):
        """Streaming einschalten. v1 meldet IP und Port des UDP-Ziels zurueck, v2 nutzt Port 60222."""
        r = self._req("PUT", "/effects", {"write": {"command": "display", "animType": "extControl",
                                                    "extControlVersion": version}})
        if isinstance(r, dict) and r.get("streamControlPort"):
            return r.get("streamControlIpAddr") or self.host, int(r["streamControlPort"])
        return self.host, 60222


# ---- Paketaufbau -------------------------------------------------------------------------------------------
def pack_v1(panels, colors, trans):
    """v1 (Light Panels): 1 Byte Anzahl, je Panel 7 Byte: id, 1 Frame, R, G, B, W, Ueberblendzeit."""
    out = bytearray([len(panels) & 0xFF])
    for pid, (r, g, b) in zip(panels, colors):
        out += bytes([pid & 0xFF, 1, r, g, b, 0, min(255, trans)])
    return bytes(out)


def pack_v2(panels, colors, trans):
    """v2 (Canvas/Shapes): 2 Byte Anzahl, je Panel 8 Byte: id (2), R, G, B, W, Ueberblendzeit (2)."""
    out = bytearray(struct.pack(">H", len(panels)))
    for pid, (r, g, b) in zip(panels, colors):
        out += struct.pack(">HBBBBH", pid, r, g, b, 0, min(65535, trans))
    return bytes(out)


# ---- Sender fuer die Show (wird von der Ausgabe-Schleife aufgerufen) --------------------------------------
class NanoleafSender:
    """Passt zur Output-Schnittstelle der Show: send(data) mit dem 512-Byte-Frame, close().

    Panel i liest seine Farbe aus den Kanaelen 3*i+1..3*i+3. Verbindung, Streaming-Modus und erneutes
    Aufbauen nach Stromausfall laufen in einem eigenen Thread, damit die Show nie darauf wartet."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = Client(cfg["host"], cfg["token"], cfg.get("port", 16021))
        self.ids = [int(p["id"]) for p in cfg.get("panels", [])]
        self.fps = max(1.0, min(30.0, float(cfg.get("fps", 10))))
        self.trans = max(0, int(cfg.get("trans", 1)))
        self.version = cfg.get("protocol", "v1")
        self.on_exit = cfg.get("on_exit", "restore")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.dest = None                    # (ip, port) des UDP-Ziels, gesetzt sobald das Streaming laeuft
        self.prev_effect = None
        self.last_sent, self.last_t = None, 0.0
        self.online = False
        self.error = ""
        self.paused = False                 # Ausgabe aus (Schalter im Panel): Panels werden freigegeben, es wird nichts gesendet
        self.want_effect = None             # eigener Effekt des Geraets statt Einzelpanels (Showmanager); None = Streaming
        self.effect_on = None               # dieser Effekt laeuft gerade
        self._release = False               # der Keeper-Thread soll das Streaming beenden und den vorherigen Effekt zurueckholen
        self._run = True
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._keeper, daemon=True)
        self._thread.start()

    # -- Verbindung halten ----------------------------------------------------------------------------------
    def pause(self):
        """Ausgabe ausschalten: dunkel, vorherigen Effekt wiederherstellen, danach nichts mehr senden."""
        self.paused = True
        self._release = True

    def resume(self):
        """Ausgabe wieder einschalten: Streaming startet neu (der Keeper-Thread merkt sich den Effekt der Panels erneut)."""
        self.paused = False

    def set_effect(self, name):
        """Show-Bild kommt vom Effekt des Geraets, oder (None) wieder von den Einzelpanels. Wartet nie: Umschalten macht der Keeper-Thread."""
        self.want_effect = name

    def _release_device(self):
        self.effect_on = None
        if self.dest is not None:
            try:                                                # dunkle Frames, damit keine Farbe haengen bleibt
                pack = pack_v2 if self.version == "v2" else pack_v1
                for _ in range(3):
                    self.sock.sendto(pack(self.ids, [(0, 0, 0)] * len(self.ids), 0), self.dest)
                    time.sleep(0.05)
            except OSError:
                pass
        try:
            if self.prev_effect:
                self.client.select_effect(self.prev_effect)     # Panels wieder frei fuer die Nanoleaf-App
        except NanoleafError:
            pass
        self.dest, self.prev_effect, self.last_sent = None, None, None

    def _keeper(self):
        while self._run:
            if self.paused:
                if self._release:
                    self._release = False
                    self._release_device()
                time.sleep(0.1)
                continue
            want = self.want_effect
            if want:
                try:
                    if want != self.effect_on:
                        if self.prev_effect is None and self.effect_on is None:
                            cur = self.client.current_effect()
                            if cur and cur != "*ExtControl*":
                                self.prev_effect = cur
                        self.dest = None                        # ab jetzt keine Einzelpanels mehr
                        self.client.select_effect(want)
                        self.effect_on = want
                    self.online, self.error = True, ""
                except NanoleafError as e:
                    self.online, self.error = False, str(e)
                time.sleep(0.1)
                continue
            was_effect, self.effect_on = self.effect_on, None
            try:
                eff = self.client.current_effect()
                if self.dest is None or eff != "*ExtControl*":
                    if self.prev_effect is None and eff and eff != "*ExtControl*" and eff != was_effect:
                        self.prev_effect = eff                 # fuer "restore" beim Beenden merken
                    self.dest = self.client.start_ext(self.version)
                    self.last_sent = None                       # nach (Wieder-)Start sofort neu senden
                self.online, self.error = True, ""
            except NanoleafError as e:
                self.online, self.error = False, str(e)
                self.dest = None
            for _ in range(20 if self.online else 50):          # 2 s Pruefintervall, bei Fehlern 5 s
                if not self._run:
                    return
                if self._release or self.want_effect:           # Ausgabe aus oder Effekt gewuenscht: sofort
                    break
                time.sleep(0.1)

    # -- Frames senden --------------------------------------------------------------------------------------
    def _colors(self, data):
        n = len(self.ids)
        return [tuple(data[3 * i:3 * i + 3]) for i in range(n)]

    def send(self, data):
        if self.paused or self.want_effect or self.dest is None or not self.ids:
            return
        now = time.time()
        colors = self._colors(data)
        # hoechstens fps Pakete pro Sekunde, bei unveraenderten Farben nur ein Lebenszeichen pro Sekunde
        due = now - self.last_t >= 1.0 / self.fps
        if not due or (colors == self.last_sent and now - self.last_t < 1.0):
            return
        pack = pack_v2 if self.version == "v2" else pack_v1
        try:
            self.sock.sendto(pack(self.ids, colors, self.trans), self.dest)
            self.last_sent, self.last_t = colors, now
        except OSError:
            pass

    def close(self):
        self._run = False
        if self.paused:                                         # Ausgabe war aus: die Panels nicht anfassen
            self.sock.close()
            return
        if self.dest is not None:
            try:                                                # letzter Frame: dunkel
                pack = pack_v2 if self.version == "v2" else pack_v1
                for _ in range(3):
                    self.sock.sendto(pack(self.ids, [(0, 0, 0)] * len(self.ids), 0), self.dest)
                    time.sleep(0.05)
            except OSError:
                pass
        try:
            if self.on_exit == "restore" and self.prev_effect:
                self.client.select_effect(self.prev_effect)
            elif self.on_exit in ("off", "restore"):
                self.client.set_power(False)
        except NanoleafError:
            pass
        self.sock.close()


# ---- Werkzeug: Einrichtung und Test -------------------------------------------------------------------------
def cmd_setup(path):
    cfg = load_config(path)
    if cfg is None:
        sys.exit(f"{path} fehlt. Lege sie an mit: {{\"host\": \"192.168.1.33\", \"token\": \"<API-Key aus openHAB>\"}}")
    cl = Client(cfg["host"], cfg["token"], cfg.get("port", 16021))
    try:
        info = cl.info()
        layout = cl.layout()
    except NanoleafError as e:
        sys.exit(f"Fehler: {e}\nIst das Geraet an und die IP richtig? Stimmt der Token?")
    panels = panels_from_layout(layout)
    model = info.get("model", "")
    cfg.update({"panels": panels, "model": model, "name": info.get("name", ""), "firmware": info.get("firmwareVersion", "")})
    if "protocol" not in cfg:
        cfg["protocol"] = "v2" if model in ("NL29", "NL42", "NL47", "NL52", "NL59") else "v1"
    save_config(cfg, path)
    print(f"Gefunden: {info.get('name', '?')} | Modell {model or '?'} | Firmware {info.get('firmwareVersion', '?')}")
    print(f"{len(panels)} leuchtende Panels (Rhythm-Modul und Controller zaehlen nicht), Protokoll {cfg['protocol']}")
    for p in panels:
        print(f"   Panel {p['id']:>5}  x={p['x']:.2f}  y={p['y']:.2f}")
    print(f"Gespeichert in {path}. Jetzt: python3 nanoleaf.py --test")


def cmd_test(path, seconds):
    cfg = load_config(path)
    if cfg is None or not cfg.get("panels"):
        sys.exit("Erst --setup ausfuehren.")
    snd = NanoleafSender(cfg)
    print("Verbinde ...")
    for _ in range(60):
        if snd.dest:
            break
        time.sleep(0.1)
    if not snd.dest:
        snd.close()
        sys.exit(f"Keine Verbindung: {snd.error or 'Zeit abgelaufen'}")
    n = len(snd.ids)
    print(f"Streaming laeuft ({snd.dest[0]}:{snd.dest[1]}). Panels leuchten der Reihe nach von links nach rechts. Strg+C beendet.")
    t0 = time.time()
    try:
        while time.time() - t0 < seconds:
            k = int((time.time() - t0) / 1.0) % n
            data = bytearray(512)
            data[3 * k:3 * k + 3] = bytes([255, 40, 0])
            for j in range(n):
                if j != k:
                    data[3 * j:3 * j + 3] = bytes([0, 0, 25])
            snd.send(bytes(data))
            time.sleep(0.05)
            if int((time.time() - t0) * 1.0) % n == k and (time.time() - t0) % 1.0 < 0.06:
                print(f"   Panel {snd.ids[k]} (Nummer {k + 1} von links)")
    except KeyboardInterrupt:
        pass
    snd.close()
    print("Fertig, Panels zurueckgesetzt.")


def cmd_status(path):
    cfg = load_config(path)
    if cfg is None:
        sys.exit(f"{path} fehlt.")
    cl = Client(cfg["host"], cfg["token"], cfg.get("port", 16021))
    try:
        info = cl.info()
        print("Erreichbar:", info.get("name"), "| Modell", info.get("model"), "| Effekt", info.get("effects", {}).get("select"))
    except NanoleafError as e:
        print("Nicht erreichbar:", e)


def main():
    ap = argparse.ArgumentParser(description="Nanoleaf Light Panels einrichten und testen")
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--setup", action="store_true", help="Modell und Panel-Anordnung auslesen und speichern")
    ap.add_argument("--test", action="store_true", help="Panels der Reihe nach leuchten lassen")
    ap.add_argument("--status", action="store_true", help="nur pruefen, ob das Geraet antwortet")
    ap.add_argument("--seconds", type=float, default=30.0)
    a = ap.parse_args()
    if a.setup:
        cmd_setup(a.file)
    elif a.test:
        cmd_test(a.file, a.seconds)
    elif a.status:
        cmd_status(a.file)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
