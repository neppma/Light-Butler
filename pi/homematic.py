#!/usr/bin/env python3
"""
homematic.py - Steckdosen und Dimmer der HomeMatic-CCU aus dem Web-Panel schalten (Bereich "Haus").

Schalten per XML-RPC ohne Anmeldung (HmIP-RF Port 2010, BidCos-RF Port 2001). Die Geraete stehen in homematic.yaml.
Schalten laeuft im Hintergrund (das Panel wartet nicht auf die CCU), der Zustand wird alle paar Sekunden gelesen.
Lesen NUR ueber ReGa (Port 8181, ein Skript fuer alle Geraete): die Werte kommen aus dem Speicher der CCU, ohne Funk.
getValue per XML-RPC fragt HmIP-Geraete per Funk ab und fuellt den Duty Cycle der CCU (bis 99 %, Geraete unerreichbar).
Schutz des Duty Cycle: hoechstens MAX_SENDS Schaltbefehle pro Minute, jeder Befehl steht im Log.
Im Trockenlauf (Simulator) wird diese Anbindung nicht gestartet.

Aenderungen aus dem Panel (Adresse der CCU, Namen, neue und entfernte Kanaele) stehen in homematic_user.json,
homematic.yaml bleibt unveraendert. Neue Kanaele kommen nur aus der Kanalliste der CCU (Knopf "Kanaele holen"),
der Nebelschub (FORBIDDEN) wird dort nie angeboten und laesst sich auf keinem Weg als Kanal eintragen.
Ohne homematic.yaml (neue Installation, Windows, Mac, 27.11.2026) startet die Anbindung leer (DEFAULT_CCU, ohne Adresse):
Adresse der CCU, Kanaele und die Rollen (ROLES: Steckdose der Nebelmaschine, Wohnzimmerlicht der Automatik) kommen dann
ganz aus dem Panel. Ohne Adresse wird nie etwas gesendet oder gelesen.

Nebelschub (ccu.fog_trigger): schaltet NUR der SMOKE-Knopf ueber fog_fire(), nie das Panel oder die Automatik. Jeder
Schub sendet zuerst ON_TIME (Sekunden), damit der Schalter auch dann von selbst ausgeht, wenn der Aus-Befehl verloren geht.
"""
import json
import os
import re
import threading
import time
import urllib.request
import xmlrpc.client

import yaml

ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
KINDS = ("switch", "dimmer")
FOG_ID = "fogtrig"                 # Zeile des Nebelschubs im ReGa-Skript
MAX_SENDS = 12                     # Schaltbefehle pro Minute, mehr lehnt Home.set ab (Schutz des Duty Cycle)
USER_FILE = "homematic_user.json"
DEFAULT_CCU = {"host": "", "ports": {"HmIP-RF": 2010, "BidCos-RF": 2001}, "poll_s": 5}   # ohne homematic.yaml
ROLES = {"fog_power": ("switch",), "room_light": ("switch", "dimmer")}   # Rolle -> erlaubte Arten; "" = keiner
FORBIDDEN = set()                  # Nebelschub-Geraet: Nebel nur ueber den SMOKE-Knopf (Sicherheitsregel), nie schaltbar;
                                   # load_config traegt das Geraet aus ccu.fog_trigger ein (nur dazu, nie heraus)
ADDR_RE = re.compile(r"^[A-Za-z0-9]{6,20}:[0-9]{1,2}$")
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,62})$")
LABEL_MAX = 40
# Kanaltypen der CCU, die das Panel anbietet: Typ -> (kind, Abstand des Schaltkanals zum Statuskanal)
# HmIP: Status im *_TRANSMITTER, geschaltet wird der erste virtuelle Kanal danach; BidCos: ein Kanal fuer beides.
SCAN_TYPES = {"SWITCH_TRANSMITTER": ("switch", 1), "DIMMER_TRANSMITTER": ("dimmer", 1), "SWITCH": ("switch", 0), "DIMMER": ("dimmer", 0)}
SCAN_SCRIPT = (
    'string id;object ch;object fc;string t;string a;string n;string f;boolean k;\n'
    'foreach(id, dom.GetObject(ID_CHANNELS).EnumUsedIDs()){ch=dom.GetObject(id);t=ch.HssType();k=false;\n'
    + "".join(f'if(t=="{t}"){{k=true;}}' for t in SCAN_TYPES) + '\n'
    'if(k){fc=dom.GetObject(ch.Interface());f=fc.Name();a=ch.Address();n=ch.Name();WriteLine(f#";"#a#";"#t#";"#n);}}')


def forbidden(address):
    return str(address).split(":")[0].upper() in FORBIDDEN


def empty_user():
    return {"version": 1, "host": "", "labels": {}, "added": [], "removed": [], "roles": {}}


def load_user(path):
    """homematic_user.json lesen. Fehlt sie oder ist sie defekt: keine Aenderungen."""
    u = empty_user()
    if not path or not os.path.exists(path):
        return u
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for k in u:
            if k in d and isinstance(d[k], type(u[k])):
                u[k] = d[k]
        u["roles"] = {k: v for k, v in u["roles"].items() if k in ROLES and isinstance(v, str) and (v == "" or ID_RE.match(v))}
    except (OSError, ValueError) as e:
        print(f"Hinweis: {os.path.basename(path)} nicht lesbar ({e}), Aenderungen aus dem Panel werden ignoriert")
    return u


def merge(ccu, devs, user):
    """Geraete aus homematic.yaml mit den Aenderungen aus dem Panel zusammenfuehren. Rueckgabe: (ccu, [Geraete])."""
    ccu = dict(ccu)
    if user.get("host") and HOST_RE.match(user["host"]):
        ccu["host"] = user["host"]
    out = [dict(d) for d in devs if d["id"] not in user.get("removed", [])]
    ids = {d["id"] for d in devs}
    for a in user.get("added", []):
        try:
            if (a.get("id") in ids or not ID_RE.match(str(a.get("id", ""))) or a.get("kind") not in KINDS
                    or a.get("interface") not in (ccu.get("ports") or {}) or not ADDR_RE.match(str(a.get("address", "")))
                    or not ADDR_RE.match(str(a.get("status", ""))) or forbidden(a["address"]) or forbidden(a["status"])):
                continue
        except AttributeError:
            continue
        ids.add(a["id"])
        out.append({"id": a["id"], "label": str(a.get("label") or a["id"])[:LABEL_MAX], "kind": a["kind"],
                    "interface": a["interface"], "address": a["address"], "status": a["status"], "user": True})
    for role, dev_id in (user.get("roles") or {}).items():   # Rolle aus dem Panel geht vor homematic.yaml ("" = keiner)
        if role in ROLES and isinstance(dev_id, str):
            ccu[role] = dev_id
    for d in out:
        lab = user.get("labels", {}).get(d["id"])
        if isinstance(lab, str) and lab.strip():
            d["label"] = lab.strip()[:LABEL_MAX]
    return ccu, out


def slug(text):
    s = str(text).lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:24] or "kanal"
    return s if s[0].isalpha() else "k_" + s


def default_label(name):
    """Aus dem Kanalnamen der CCU einen Namen fuers Panel: ohne ':3' am Ende und ohne das Wort 'Status'."""
    n = re.sub(r":[0-9]+$", "", str(name)).replace("Status", " ")
    return re.sub(r"\s+", " ", n).strip()[:LABEL_MAX] or str(name)[:LABEL_MAX]


class _Timeout(xmlrpc.client.Transport):
    def __init__(self, timeout):
        super().__init__()
        self.timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self.timeout
        return conn


def load_config(path):
    """homematic.yaml lesen und pruefen. Rueckgabe: (ccu, [Geraete])."""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    ccu = cfg.get("ccu") or {}
    if not ccu.get("host"):
        raise ValueError("homematic.yaml: ccu.host fehlt")
    ft = ccu.get("fog_trigger")
    if isinstance(ft, dict) and ft.get("address"):               # Nebelschub sperren, bevor Geraete geprueft werden
        FORBIDDEN.add(str(ft["address"]).split(":")[0].upper())
    devs, seen = [], set()
    for d in cfg.get("devices") or []:
        if not ID_RE.match(str(d.get("id", ""))) or d["id"] in seen:
            raise ValueError(f"homematic.yaml: ungueltige oder doppelte id {d.get('id')!r}")
        if forbidden(d.get("address", "")) or forbidden(d.get("status", "")):
            raise ValueError(f"homematic.yaml: Geraet {d['id']} ist gesperrt (Nebelschub)")
        if d.get("kind") not in KINDS or d.get("interface") not in (ccu.get("ports") or {}) or not d.get("address"):
            raise ValueError(f"homematic.yaml: Geraet {d['id']} unvollstaendig (kind, interface, address)")
        seen.add(d["id"])
        devs.append({"id": d["id"], "label": str(d.get("label") or d["id"]), "kind": d["kind"],
                     "interface": d["interface"], "address": str(d["address"]), "status": str(d.get("status") or d["address"])})
    return ccu, devs


class Home:
    def __init__(self, path="homematic.yaml", proxy=None, rega=None, timeout=3.0, log=print, user_path=None):
        """proxy: Funktion (interface) -> Objekt mit setValue; rega: Funktion (Skript) -> Text (beide nur fuer Tests austauschbar).
        user_path: Datei mit den Aenderungen aus dem Panel (Standard: homematic_user.json neben homematic.yaml)."""
        self.has_file = bool(path) and os.path.exists(path)
        if self.has_file:
            self.base_ccu, self.base_devs = load_config(path)
        else:                                                  # ohne homematic.yaml: alles kommt aus dem Panel
            self.base_ccu, self.base_devs = json.loads(json.dumps(DEFAULT_CCU)), []
        self.user_path = user_path or os.path.join(os.path.dirname(os.path.abspath(path)), USER_FILE)
        self.user = load_user(self.user_path)
        self.found, self.scanning = None, False                # Kanalliste der CCU (Knopf "Kanaele holen")
        ft = self.base_ccu.get("fog_trigger") or None          # Nebelschub-Schalter (nur fuer den SMOKE-Knopf)
        if ft is not None and (ft.get("interface") not in (self.base_ccu.get("ports") or {})
                               or not ADDR_RE.match(str(ft.get("address", "")))):
            raise ValueError("homematic.yaml: ccu.fog_trigger braucht interface und address")
        self.fog_trigger = ft
        self.fog_state = {"on": None, "ok": None}             # Nebelschub: an? erreichbar?
        self.timeout = timeout
        self._proxy = proxy or self._xmlrpc
        self._rega = rega or self._rega_http
        self.log = log
        self.sends = []                                        # Zeitpunkte der letzten Schaltbefehle
        self.state, self.last_level = {}, {}
        self.error = ""
        self.lock = threading.Lock()
        self._run = False
        self._apply()

    def _apply(self):
        """Geraeteliste neu zusammenstellen (nach dem Start und nach jeder Aenderung im Panel, ohne Neustart)."""
        ccu, devs = merge(self.base_ccu, self.base_devs, self.user)
        with self.lock:
            self.ccu, self.devices = ccu, devs
            self.by_id = {d["id"]: d for d in devs}
            for d in devs:
                self.state.setdefault(d["id"], {"on": None, "level": None, "ok": None})
                if d["kind"] == "dimmer":
                    self.last_level.setdefault(d["id"], 1.0)

    def _save(self):
        tmp = self.user_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.user, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.user_path)

    # ---- im Panel bearbeiten ---------------------------------------------------------------------------------------
    def edit(self, d):
        """Aenderung aus dem Panel: {"host": "192.168.1.20"} | {"label": {"id", "text"}} | {"add": {"interface", "status"}}
        (nur ein Kanal aus der Kanalliste der CCU) | {"remove": id} | {"role": {"role": "fog_power", "id": id oder ""}}.
        Wird sofort gespeichert und gilt sofort."""
        u = json.loads(json.dumps(self.user))
        if "host" in d:
            h = str(d["host"]).strip()
            if h and not HOST_RE.match(h):
                raise ValueError("Ungueltige Adresse der CCU (zum Beispiel 192.168.1.20)")
            u["host"] = "" if h == self.base_ccu["host"] else h
        if "label" in d:
            dev_id, text = str(d["label"].get("id")), str(d["label"].get("text", "")).strip()
            if dev_id not in self.by_id:
                raise ValueError("Unbekannter Kanal")
            if not text:
                raise ValueError("Der Name darf nicht leer sein")
            u["labels"][dev_id] = text[:LABEL_MAX]
        if "remove" in d:
            dev_id = str(d["remove"])
            if dev_id not in self.by_id:
                raise ValueError("Unbekannter Kanal")
            if any(a["id"] == dev_id for a in u["added"]):
                u["added"] = [a for a in u["added"] if a["id"] != dev_id]
            elif dev_id not in u["removed"]:
                u["removed"].append(dev_id)
            u["labels"].pop(dev_id, None)
        if "add" in d:
            self._add(u, d["add"])
        if "role" in d:
            role, dev_id = str(d["role"].get("role")), str(d["role"].get("id") or "")
            if role not in ROLES:
                raise ValueError("Unbekannte Rolle")
            if dev_id and (dev_id not in self.by_id or self.by_id[dev_id]["kind"] not in ROLES[role]):
                raise ValueError("Dieser Kanal passt hier nicht" + (" (nur Steckdosen)" if ROLES[role] == ("switch",) else ""))
            u["roles"][role] = dev_id
        self.user = u
        self._save()
        self._apply()

    def _add(self, u, a):
        key = (str(a.get("interface")), str(a.get("status")))
        f = next((x for x in (self.found or []) if (x["interface"], x["status"]) == key), None)
        if f is None or forbidden(key[1]):
            raise ValueError("Diesen Kanal bietet die CCU nicht an (erst 'Kanaele holen')")
        if any((d["interface"], d["address"]) == (f["interface"], f["address"]) for d in self.devices):
            raise ValueError("Dieser Kanal ist schon im Panel")
        old = next((d for d in self.base_devs if (d["interface"], d["address"]) == (f["interface"], f["address"])), None)
        if old is not None:                                    # Kanal aus homematic.yaml, der entfernt war: wieder einblenden
            u["removed"] = [x for x in u["removed"] if x != old["id"]]
            return
        ids = {d["id"] for d in self.base_devs} | {x["id"] for x in u["added"]}
        base = slug(f["label"])
        new_id, n = base, 2
        while new_id in ids:
            new_id, n = f"{base[:20]}_{n}", n + 1
        u["added"].append({"id": new_id, "label": f["label"], "kind": f["kind"], "interface": f["interface"],
                           "address": f["address"], "status": f["status"]})

    def scan(self, wait=False):
        """Kanalliste der CCU holen (ein ReGa-Aufruf, kein Funk). Ergebnis in self.found."""
        if self.scanning:
            return
        if not self.ccu.get("host"):
            raise ValueError("Zuerst die Adresse der CCU eintragen und speichern")
        self.scanning = True

        def run():
            try:
                text = self._rega(SCAN_SCRIPT)
                found = []
                for line in text.split("<xml>")[0].splitlines():
                    parts = line.strip().split(";", 3)
                    if len(parts) != 4 or parts[2] not in SCAN_TYPES or parts[0] not in (self.ccu.get("ports") or {}):
                        continue
                    iface, status, typ, name = parts
                    if not ADDR_RE.match(status) or forbidden(status):
                        continue
                    kind, step = SCAN_TYPES[typ]
                    dev, ch = status.split(":")
                    found.append({"interface": iface, "status": status, "address": f"{dev}:{int(ch) + step}", "kind": kind,
                                  "name": name[:60], "label": default_label(name)})
                self.found = sorted(found, key=lambda x: x["name"].lower())
            except Exception as e:                                  # noqa: BLE001
                self.error = f"Kanalliste der CCU nicht lesbar: {str(e)[:80]}"
            finally:
                self.scanning = False
        if wait:
            run()
        else:
            threading.Thread(target=run, daemon=True).start()

    def _xmlrpc(self, interface):
        port = int(self.ccu["ports"][interface])
        return xmlrpc.client.ServerProxy(f"http://{self.ccu['host']}:{port}/", transport=_Timeout(self.timeout))

    def _rega_http(self, script):
        url = f"http://{self.ccu['host']}:{int(self.ccu.get('rega_port', 8181))}/tester.exe"
        with urllib.request.urlopen(urllib.request.Request(url, data=script.encode("latin-1")), timeout=self.timeout) as r:
            return r.read().decode("latin-1")

    def read_script(self, devs=None):
        """ReGa-Skript: je Geraet eine Zeile  id;Wert;UNREACH  (Werte aus dem Speicher der CCU, kein Funk)."""
        lines = ["object o;object u;"]
        devs = list(self.devices if devs is None else devs)
        if self.fog_trigger:                                   # Nebelschub mitlesen (Zustand, erreichbar)
            devs.append({"id": FOG_ID, "kind": "switch", "interface": self.fog_trigger["interface"],
                         "status": self.fog_trigger["address"]})
        for d in devs:
            dp = f'{d["interface"]}.{d["status"]}.{"LEVEL" if d["kind"] == "dimmer" else "STATE"}'
            un = f'{d["interface"]}.{d["status"].split(":")[0]}:0.UNREACH'
            lines.append(f'o=dom.GetObject("{dp}");u=dom.GetObject("{un}");Write("{d["id"]};");'
                         f'if(o){{Write(o.Value());}}Write(";");if(u){{Write(u.Value());}}WriteLine("");')
        return "\n".join(lines)

    # ---- lesen -----------------------------------------------------------------------------------------------------
    def poll(self):
        """Zustand aller Geraete einmal lesen (blockiert, ruft der Hintergrund-Thread auf). Ein Aufruf, kein Funk."""
        devs = list(self.devices)
        if not self.ccu.get("host"):                           # keine CCU eingetragen: nichts lesen, kein Fehler
            self.error = ""
            return
        try:
            text = self._rega(self.read_script(devs))
        except Exception as e:                                      # noqa: BLE001
            with self.lock:
                for d in devs:
                    self.state[d["id"]] = {"on": None, "level": None, "ok": False}
                self.fog_state = {"on": None, "ok": False}
            self.error = f"CCU nicht erreichbar (ReGa): {str(e)[:80]}"
            return
        rows = {}
        for line in text.split("<xml>")[0].splitlines():
            parts = line.strip().split(";")
            if len(parts) == 3:
                rows[parts[0]] = parts[1:]
        errs = []
        for d in devs:
            val, unreach = rows.get(d["id"], ("", ""))
            try:
                if val == "":
                    raise ValueError("kein Wert")
                if d["kind"] == "dimmer":
                    lvl = float(val)
                    new = {"on": lvl > 0.005, "level": round(lvl, 3), "ok": unreach != "true"}
                    if lvl > 0.005:
                        self.last_level[d["id"]] = lvl
                else:
                    new = {"on": val == "true", "level": None, "ok": unreach != "true"}
            except ValueError as e:
                new = {"on": None, "level": None, "ok": False}
                errs.append(f"{d['label']}: {e}")
            if new["ok"] is False and not any(x.startswith(d["label"] + ":") for x in errs):
                errs.append(f"{d['label']}: nicht erreichbar")
            with self.lock:
                self.state[d["id"]] = new
        self.error = "; ".join(errs)[:200]
        if self.fog_trigger:                                   # aus = nicht erreichbar ist normal (Maschine stromlos)
            val, unreach = rows.get(FOG_ID, ("", ""))
            with self.lock:
                self.fog_state = {"on": val == "true", "ok": val != "" and unreach != "true"}

    def start(self):
        self._run = True

        def loop():
            while self._run:
                self.poll()
                for _ in range(int(max(1, float(self.ccu.get("poll_s", 5))) * 10)):
                    if not self._run:
                        return
                    time.sleep(0.1)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._run = False

    # ---- schalten --------------------------------------------------------------------------------------------------
    def set(self, dev_id, on=None, level=None, wait=False, ramp_s=None):
        """Schalten oder dimmen. Laeuft im Hintergrund, der Zustand im Panel wird sofort angepasst. ramp_s: bei Dimmern langsam
        dorthin dimmen (RAMP_TIME vor LEVEL, wie ON_TIME vor STATE beim Nebelschub; HmIP-BDT kennt es, Wunsch 12.11.2026)."""
        d = self.by_id.get(dev_id)
        if d is None:
            raise ValueError("Unbekanntes Geraet")
        if not self.ccu.get("host"):
            raise ValueError("Keine CCU eingetragen")
        now = time.monotonic()
        with self.lock:
            self.sends = [t for t in self.sends if now - t < 60.0]
            if len(self.sends) >= MAX_SENDS:
                self.error = f"Zu viele Schaltbefehle (hoechstens {MAX_SENDS} pro Minute, Schutz des Duty Cycle der CCU)"
                raise ValueError(self.error)
            self.sends.append(now)
        if d["kind"] == "switch":
            if on is None:
                raise ValueError("Steckdose: an oder aus fehlt")
            key, val, new = "STATE", bool(on), {"on": bool(on), "level": None}
        else:
            if level is None:
                level = (self.last_level.get(dev_id, 1.0) or 1.0) if on else 0.0
            val = max(0.0, min(1.0, float(level)))
            if val > 0.005:
                self.last_level[dev_id] = val
            key, new = "LEVEL", {"on": val > 0.005, "level": round(val, 3)}
        ramp = max(0.0, min(600.0, float(ramp_s or 0))) if d["kind"] != "switch" else 0.0
        with self.lock:
            self.state[dev_id].update(new)

        def send():
            self.log(f"HomeMatic: {d['label']} {key}={val}" + (f" ueber {ramp:g} s" if ramp else ""))
            try:
                if ramp:
                    self._proxy(d["interface"]).setValue(d["address"], "RAMP_TIME", ramp)
                self._proxy(d["interface"]).setValue(d["address"], key, val)
            except Exception as e:                                  # noqa: BLE001
                with self.lock:
                    self.state[dev_id]["ok"] = False
                self.error = f"{d['label']}: Schalten fehlgeschlagen ({str(e)[:60]})"
        if wait:
            send()
        else:
            threading.Thread(target=send, daemon=True).start()

    def fog_fire(self, on, on_time=10.0, wait=False):
        """Nebelschub ein (mit ON_TIME, der Schalter geht danach von selbst aus) oder sofort aus. Nur fuer den SMOKE-Knopf.
        Aus wird nie durch die Befehlsgrenze blockiert."""
        ft = self.fog_trigger
        if not ft:
            raise ValueError("Kein Nebelschub-Schalter eingetragen (ccu.fog_trigger)")
        if on:
            now = time.monotonic()
            with self.lock:
                self.sends = [t for t in self.sends if now - t < 60.0]
                if len(self.sends) >= MAX_SENDS:
                    self.error = f"Zu viele Schaltbefehle (hoechstens {MAX_SENDS} pro Minute, Schutz des Duty Cycle der CCU)"
                    raise ValueError(self.error)
                self.sends.append(now)
        secs = max(1.0, min(10.0, float(on_time)))

        def send():
            self.log(f"HomeMatic: Nebelschub {'AN fuer ' + str(int(secs)) + ' s' if on else 'AUS'}")
            try:
                p = self._proxy(ft["interface"])
                if on:
                    p.setValue(ft["address"], "ON_TIME", secs)       # Sicherung: geht nach secs von selbst aus
                    p.setValue(ft["address"], "STATE", True)
                else:
                    p.setValue(ft["address"], "STATE", False)
                with self.lock:
                    self.fog_state["on"] = bool(on)
            except Exception as e:                                  # noqa: BLE001
                with self.lock:
                    self.fog_state["ok"] = False
                self.error = f"Nebelschub: Schalten fehlgeschlagen ({str(e)[:60]})"
        if wait:
            send()
        else:
            threading.Thread(target=send, daemon=True).start()

    def status(self):
        with self.lock:
            empty = {"on": None, "level": None, "ok": None}
            return {"devices": [dict(id=d["id"], label=d["label"], kind=d["kind"], iface=d["interface"], addr=d["address"],
                                     **self.state.get(d["id"], empty)) for d in self.devices],
                    "error": self.error, "host": self.ccu["host"], "found": self.found, "scanning": self.scanning,
                    "roles": {r: (self.ccu.get(r) if self.ccu.get(r) in self.by_id else "") for r in ROLES}, "file": self.has_file}


def default_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "homematic.yaml")
