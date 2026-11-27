#!/usr/bin/env python3
"""
bt_audio.py - Audio-Eingang "Bluetooth" (Wunsch von Markus 24.11.2026): der Pi als Bluetooth-Empfaenger. Ein Handy oder
Laptop koppelt sich wie mit einem Lautsprecher, die Musik dient der Analyse wie Line-In oder der Ton vom Musik-Rechner.

Zwei Teile:
  BtManager  verwaltet Bluetooth ueber das Programm bluetoothctl (BlueZ): einschalten, fuer WINDOW_S Sekunden sichtbar
             und koppelbar machen, nach Geraeten suchen, koppeln, verbinden, trennen, entfernen. Ein bluetoothctl laeuft
             dauerhaft als Agent (NoInputNoOutput): Kopplungs-Fragen beantwortet er nur mit "yes", solange das Fenster
             offen ist; bereits gekoppelte (vertraute) Geraete duerfen sich immer verbinden. Sonst lehnt er ab.
  BtAudioIn  liest den Ton, sobald ein Geraet verbunden ist und spielt: bluez-alsa (bluealsad -p a2dp-sink) stellt ihn
             als PCM bereit, "bluealsa-cli open" liefert die rohen Samples (int16). Wie audio_net.NetAudioIn: Bloecke mit
             hop Samples an den Analyzer; andere Abtastrate (48 kHz) wird fortlaufend umgerechnet (ohne Spruenge je Block,
             die waeren falsche Anschlaege, siehe Eichstueck 23.11.2026). Spielt nichts, kommt nichts: die Show sieht Stille.

Einrichtung einmal am Pi mit sudo: bluetooth_setup.sh (Paket bluez-alsa-utils, Bluetooth einschalten). Ohne das zeigt das
Panel nur einen Hinweis. Nur Ton, aufs Licht wirkt Bluetooth nie anders als jeder andere Eingang.
"""
import os
import re
import shutil
import subprocess
import threading
import time

import numpy as np

BT_NAME = "Bluetooth"
ALIAS = "Light-Butler"                 # so heisst der Pi in der Bluetooth-Liste des Handys
WINDOW_S = 180                         # so lange sichtbar und koppelbar
SCAN_S = 30                            # so lange wird nach Geraeten gesucht
REFRESH_S = 3.0                        # Stand der Geraete hoechstens so oft neu lesen
CONNECT_AFTER_S = 4.0                  # Lautsprecher nach dem Koppeln so spaet verbinden, wenn er es nicht selbst tut
MSG_S = 20.0                           # Meldungen im Panel verschwinden nach so vielen Sekunden
MAC_RE = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x01|\x02|\r")
PROMPT_RE = re.compile(r"(Authorize service|Request confirmation|Confirm passkey|Accept pairing|Request authorization)"
                       r".*?\(yes/no\)", re.S)


def available():
    """(bluetoothctl da, bluez-alsa da)"""
    return shutil.which("bluetoothctl") is not None, shutil.which("bluealsa-cli") is not None


def clean_mac(mac):
    m = str(mac or "").strip().upper()
    if not MAC_RE.match(m):
        raise ValueError("Ungueltige Bluetooth-Adresse")
    return m


def run(cmd, timeout=8.0):
    """Einmal-Befehl, Rueckgabe (Code, Ausgabe). Fehler = (-1, Text)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return -1, str(e)


def parse_info(text):
    """Ausgabe von "bluetoothctl info MAC" bzw. "bluealsa-cli info PFAD" als dict (Schluessel: Wert)."""
    out = {}
    for line in str(text).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            if k and k not in out:
                out[k] = v.strip()
    return out


class BtManager:
    def __init__(self, runner=run, spawn=None, clock=time.time, tools=None):
        self.runner, self.clock = runner, clock
        self.spawn = spawn or (lambda: subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                         stderr=subprocess.STDOUT, bufsize=0))
        self.tools = tools if tools is not None else available()
        self.proc = None
        self.lock = threading.RLock()
        self.window_until = 0.0
        self.scan_until = 0.0
        self.found = {}                    # MAC -> Name (beim Suchen gesehen)
        self.devices = {}                  # MAC -> {name, paired, trusted, connected, audio}
        self.ctl = {}                      # Stand des Adapters (bluetoothctl show)
        self.refresh_t = -1e9
        self._msg, self._error, self.msg_t, self.error_t = "", "", -1e9, -1e9
        self.answered = []                 # (Zeit, Frage, Antwort) fuer Tests und Anzeige
        self._buf = ""
        self._reader = None
        self.trusting = set()              # schon vertraut (je Kopplung einmal)
        self.pair_init = set()             # vom Panel aus gekoppelt (Lautsprecher): danach gleich verbinden
        self.connect_at = {}               # MAC -> Zeitpunkt, zu dem nach dem Koppeln verbunden wird

    # Meldungen fuers Panel: verschwinden nach MSG_S (Fehlerbericht 25.11.2026: "Kopple mit ..." blieb stehen)
    @property
    def msg(self):
        return self._msg if self.clock() - self.msg_t < MSG_S else ""

    @msg.setter
    def msg(self, text):
        self._msg, self.msg_t = text, self.clock()

    @property
    def error(self):
        return self._error if self.clock() - self.error_t < MSG_S else ""

    @error.setter
    def error(self, text):
        self._error, self.error_t = text, self.clock()

    # ---- dauerhafter bluetoothctl (Agent und Ereignisse) ----
    def ensure(self):
        """bluetoothctl starten, Agent anmelden, Bluetooth einschalten. Wirft ValueError, wenn Bluetooth nicht eingerichtet ist."""
        if not self.tools[0]:
            raise ValueError("Bluetooth ist am Licht-Rechner nicht eingerichtet (bluetooth_setup.sh)")
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                return
            try:
                self.proc = self.spawn()
            except OSError as e:
                self.proc = None
                raise ValueError(f"bluetoothctl startet nicht: {e}") from None
            self._reader = threading.Thread(target=self._read, args=(self.proc,), daemon=True)
            self._reader.start()
            for c in ("agent NoInputNoOutput", "default-agent", "power on", "system-alias " + ALIAS):
                self.send(c)
        self.refresh(force=True)

    def send(self, line):
        p = self.proc
        if p is None or p.stdin is None:
            return
        try:
            p.stdin.write((line + "\n").encode())
            p.stdin.flush()
        except (OSError, ValueError):
            self.proc = None

    def _read(self, p):
        while True:
            try:
                chunk = os.read(p.stdout.fileno(), 4096) if hasattr(p.stdout, "fileno") else p.stdout.read(4096)
            except (OSError, ValueError):
                break
            if not chunk:
                break
            self.feed(chunk.decode("utf-8", "replace"))

    def feed(self, text):
        """Ausgabe von bluetoothctl auswerten (auch Teilstuecke: Fragen enden ohne Zeilenumbruch)."""
        with self.lock:
            self._buf += ANSI_RE.sub("", text)
            m = PROMPT_RE.search(self._buf)
            while m:
                self._answer(m.group(0))
                self._buf = self._buf[m.end():]
                m = PROMPT_RE.search(self._buf)
            lines = self._buf.split("\n")
            self._buf = lines.pop()
            if len(self._buf) > 2000:
                self._buf = self._buf[-500:]
            for line in lines:
                self._line(line.strip())

    def _answer(self, question):
        mac = re.search(r"([0-9A-F]{2}(:[0-9A-F]{2}){5})", question.upper())
        known = mac is not None and self.devices.get(mac.group(1), {}).get("paired")
        ok = self.window_open() or bool(known)
        self.answered.append((self.clock(), " ".join(question.split())[:80], ok))
        del self.answered[:-20]
        self.send("yes" if ok else "no")
        if not ok:
            self.msg = "Kopplung abgelehnt: zuerst „Sichtbar machen“ druecken"

    def _line(self, line):
        m = re.search(r"\[(NEW|CHG|DEL)\] Device ([0-9A-F:]{17}) (.*)$", line)
        if not m:
            if ("Failed to pair" in line or "Failed to connect" in line) and not any(
                    k in line for k in ("InProgress", "AlreadyConnected", "AlreadyExists")):   # harmlos (25.11.2026:
                self.error = line.split("]")[-1].strip()[:120]                               # JBL verbindet sich selbst)
            return
        kind, mac, rest = m.group(1), m.group(2), m.group(3)
        if kind == "NEW":
            self.found[mac] = rest.strip() or mac
        elif kind == "DEL":
            self.found.pop(mac, None)
            self.devices.pop(mac, None)
        else:
            d = self.devices.setdefault(mac, {"name": self.found.get(mac, mac), "paired": False, "trusted": False,
                                              "connected": False, "audio": False})
            for key, field in (("Paired", "paired"), ("Bonded", "paired"), ("Trusted", "trusted"), ("Connected", "connected")):
                if rest.startswith(key + ":"):
                    d[field] = rest.split(":", 1)[1].strip() == "yes"
                    if field == "paired" and d["paired"] and not d["trusted"] and self.window_open():
                        self._trust(mac, d)
                    if field == "connected":
                        self.msg = ("Verbunden: " if d["connected"] else "Getrennt: ") + d["name"]
            if rest.startswith("Name:") or rest.startswith("Alias:"):
                d["name"] = rest.split(":", 1)[1].strip() or mac
                self.found[mac] = d["name"]
            self.refresh_t = -1e9

    def _trust(self, mac, d):
        """Im Sichtbar-Fenster gekoppelt: vertrauen, sonst lehnt BlueZ die Musik-Verbindung ab (Test 25.11.2026: iPhone
        gekoppelt, aber "a2dp auth_cb Access denied", am Handy "Verbindung fehlgeschlagen")."""
        if mac in self.trusting:
            return
        self.trusting.add(mac)
        self.send("trust " + mac)
        d["trusted"] = True
        if mac in self.pair_init:          # Lautsprecher (25.11.2026): der Pi verbindet sich selbst
            self.pair_init.discard(mac)
            self.connect_at[mac] = self.clock() + CONNECT_AFTER_S   # erst kurz warten: viele Lautsprecher verbinden
            self.msg = "Gekoppelt: " + d.get("name", mac) + " – wird verbunden"   # sich gleich selbst (sonst InProgress)
        else:
            self.msg = "Gekoppelt: " + d.get("name", mac) + " – jetzt am Handy als Ausgabe wählen"

    # ---- Bedienung ----
    def window_open(self):
        return self.clock() < self.window_until

    def visible(self, on=True):
        self.ensure()
        if on:
            self.window_until = self.clock() + WINDOW_S
            for c in ("power on", "discoverable-timeout %d" % WINDOW_S, "pairable on", "discoverable on"):
                self.send(c)
            self.msg = "Sichtbar als „%s“: am Handy unter Bluetooth koppeln" % ALIAS
        else:
            self.window_until = 0.0
            self.send("discoverable off")
            self.send("pairable off")
            self.msg = ""

    def scan(self, on=True):
        self.ensure()
        if on:
            self.scan_until = self.clock() + SCAN_S
            self.send("scan on")
        else:
            self.scan_until = 0.0
            self.send("scan off")

    def pair(self, mac):
        mac = clean_mac(mac)
        self.ensure()
        self.window_until = max(self.window_until, self.clock() + 60)     # Rueckfragen dieser Kopplung beantworten
        self.error = ""
        self.pair_init.add(mac)
        self.send("pair " + mac)
        self.msg = "Kopple mit " + self.found.get(mac, mac) + " … am Handy bestaetigen"

    def connect(self, mac):
        mac = clean_mac(mac)
        self.ensure()
        self.error = ""
        self.send("connect " + mac)

    def disconnect(self, mac):
        self.ensure()
        self.send("disconnect " + clean_mac(mac))

    def remove(self, mac):
        mac = clean_mac(mac)
        self.trusting.discard(mac)
        self.ensure()
        self.send("remove " + mac)
        self.devices.pop(mac, None)
        self.found.pop(mac, None)

    def command(self, d):
        """Befehl aus dem Panel: {"op": visible|hide|scan|scan_off|pair|connect|disconnect|remove, "mac": ...}"""
        op = str(d.get("op") or "")
        if op == "visible":
            self.visible(True)
        elif op == "hide":
            self.visible(False)
        elif op == "scan":
            self.scan(True)
        elif op == "scan_off":
            self.scan(False)
        elif op in ("pair", "connect", "disconnect", "remove"):
            getattr(self, op)(d.get("mac"))
        else:
            raise ValueError("Unbekannter Bluetooth-Befehl")
        self.refresh(force=True)

    # ---- Stand ----
    def tick(self):
        """Fenster und Suche ablaufen lassen (vom Status aufgerufen)."""
        now = self.clock()
        if self.scan_until and now >= self.scan_until:
            self.scan_until = 0.0
            self.send("scan off")
        if self.window_until and now >= self.window_until:
            self.window_until = 0.0
            self.send("pairable off")
        for mac, t in list(self.connect_at.items()):
            if now >= t:
                del self.connect_at[mac]
                if not self.devices.get(mac, {}).get("connected"):
                    self.send("connect " + mac)

    def refresh(self, force=False):
        now = self.clock()
        if not self.tools[0] or (not force and now - self.refresh_t < REFRESH_S):
            return
        self.refresh_t = now
        rc, out = self.runner(["bluetoothctl", "show"], 5.0)
        self.ctl = parse_info(out) if rc == 0 else {}
        rc, out = self.runner(["bluetoothctl", "devices"], 5.0)
        macs = []
        for line in out.splitlines() if rc == 0 else []:
            m = re.match(r"\s*Device ([0-9A-F:]{17}) ?(.*)$", line.strip())
            if m:
                macs.append(m.group(1))
                self.found.setdefault(m.group(1), m.group(2).strip() or m.group(1))
        devs = {}
        for mac in macs[:30]:
            rc, out = self.runner(["bluetoothctl", "info", mac], 5.0)
            i = parse_info(out) if rc == 0 else {}
            devs[mac] = {"name": i.get("Alias") or i.get("Name") or self.found.get(mac, mac), "paired": i.get("Paired") == "yes",
                         "trusted": i.get("Trusted") == "yes", "connected": i.get("Connected") == "yes",
                         "audio": "Audio Source" in out or "0000110a" in out.lower()}
        with self.lock:
            self.devices = devs
            for mac, d in devs.items():                    # gekoppelt, aber nicht vertraut (Ereignis verpasst): nachholen
                if d["paired"] and not d["trusted"] and self.window_open():
                    self._trust(mac, d)
                if not d["paired"]:
                    self.trusting.discard(mac)

    def status(self):
        self.tick()
        self.refresh()
        now = self.clock()
        c = self.ctl
        blocked = "blocked" in c.get("PowerState", "")
        devs = []
        for mac, d in sorted(self.devices.items(), key=lambda x: (not x[1]["connected"], not x[1]["paired"], x[1]["name"].lower())):
            if d["paired"] or d["connected"] or mac in self.found:
                devs.append(dict(d, mac=mac))
        for mac, name in self.found.items():
            if mac not in self.devices and self.scan_until:
                devs.append({"mac": mac, "name": name, "paired": False, "trusted": False, "connected": False, "audio": False})
        return {"tools": self.tools[0], "bluealsa": self.tools[1], "running": self.proc is not None and self.proc.poll() is None,
                "powered": c.get("Powered") == "yes", "blocked": blocked, "name": ALIAS,
                "visible": max(0, int(round(self.window_until - now))) if self.window_until > now else 0,
                "scanning": max(0, int(round(self.scan_until - now))) if self.scan_until > now else 0,
                "devices": devs[:40], "msg": self.msg, "error": self.error,
                "answers": [{"t": round(now - t), "q": q, "ok": ok} for t, q, ok in self.answered[-5:]]}

    def name_of(self, mac):
        d = self.devices.get(mac)
        return d["name"] if d else self.found.get(mac, mac)

    def stop(self):
        p = self.proc
        self.proc = None
        if p is not None:
            try:
                p.terminate()
            except OSError:
                pass


_MGR = None


def manager():
    """Die eine Bluetooth-Verwaltung des Programms (erst bei Bedarf angelegt)."""
    global _MGR
    if _MGR is None:
        _MGR = BtManager()
    return _MGR


class Resampler:
    """Fortlaufende lineare Umrechnung der Abtastrate: die Stelle zwischen zwei Bloecken wird mitgefuehrt."""

    def __init__(self, src, dst):
        self.step = float(src) / float(dst)
        self.pos = 0.0                 # Stelle des naechsten Ausgangs-Samples, relativ zum ersten gepufferten Eingang
        self.prev = None               # letztes Eingangs-Sample des vorigen Stuecks

    def feed(self, x):
        if self.step == 1.0:
            return x
        if self.prev is not None:
            x = np.concatenate([self.prev, x])
        n = len(x)
        if n < 2:
            self.prev = x
            return x[:0]
        idx = np.arange(self.pos, n - 1, self.step)
        i0 = idx.astype(np.int64)
        fr = (idx - i0).astype(np.float32)[:, None]
        y = x[i0] * (1 - fr) + x[i0 + 1] * fr
        nxt = self.pos + len(idx) * self.step
        self.prev = x[n - 1:]
        self.pos = nxt - (n - 1)
        return y.astype(np.float32)


def find_pcm(runner=run):
    """(Pfad, MAC) des ersten A2DP-Eingangs von bluez-alsa (Handy verbunden), sonst (None, None)."""
    rc, out = runner(["bluealsa-cli", "list-pcms"], 4.0)
    if rc != 0:
        return None, None
    for line in out.split():
        if "/a2dpsnk/" in line and line.endswith("/source"):
            m = re.search(r"dev_([0-9A-F_]{17})", line, re.I)
            return line.strip(), (m.group(1).replace("_", ":").upper() if m else "")
    return None, None


def pcm_format(info):
    """(Abtastrate, Kanaele) aus "bluealsa-cli info"; nur int16 (S16_LE, so liefert SBC und AAC)."""
    i = parse_info(info)
    fmt = i.get("Format", "S16_LE").upper()
    if fmt not in ("S16_LE", ""):
        raise ValueError(f"Format {fmt} wird nicht unterstuetzt")
    rate = int(re.sub(r"[^0-9]", "", i.get("Rate") or i.get("Sampling") or "44100") or 44100)
    ch = int(re.sub(r"[^0-9]", "", i.get("Channels") or "2") or 2)
    return rate, max(1, min(2, ch))


class BtAudioIn:
    def __init__(self, deliver, rate=44100, hop=512, runner=run, opener=None, names=None, out=None):
        self.deliver, self.rate, self.hop = deliver, rate, hop
        self.out = out                     # PassThrough: Ton zusaetzlich an eine Ausgabe (25.11.2026), sonst None
                                           # deliver None = nur weiterleiten (Eingang ist nicht Bluetooth)
        self.runner = runner
        self.opener = opener or (lambda path: subprocess.Popen(["bluealsa-cli", "open", path], stdout=subprocess.PIPE,
                                                               stderr=subprocess.DEVNULL, bufsize=0))
        self.names = names                 # MAC -> Name (aus der Verwaltung), fuer die Anzeige
        self.buf = None
        self.proc = None
        self.mac, self.src_rate, self.channels = "", 0, 2
        self.t, self.blocks, self.error = None, 0, ""
        self._run = False
        self._thread = None

    def start(self):
        if not available()[1] and self.runner is run:
            self.error = "Bluetooth-Ton ist am Licht-Rechner nicht eingerichtet (bluetooth_setup.sh)"
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._run = False
        p = self.proc
        if p is not None:
            try:
                p.terminate()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
        self.proc = None
        self.buf = None

    def _loop(self):
        while self._run:
            try:
                self.once()
            except Exception as e:                      # noqa: BLE001  ein Fehler haelt den Eingang nie an
                self.error = str(e)[:120]
            for _ in range(10):                         # 1 s warten, dann wieder nach einem Handy schauen
                if not self._run:
                    return
                time.sleep(0.1)

    def once(self):
        """Ein verbundenes Geraet suchen und lesen, bis es aufhoert (Verbindung weg oder Eingang aus)."""
        path, mac = find_pcm(self.runner)
        if path is None:
            self.mac = ""
            return False
        rc, info = self.runner(["bluealsa-cli", "info", path], 4.0)
        rate, ch = pcm_format(info if rc == 0 else "")
        self.mac, self.src_rate, self.channels, self.error = mac, rate, ch, ""
        rs = Resampler(rate, self.rate)
        self.proc = p = self.opener(path)
        frame = 2 * ch
        rest = b""
        while self._run:
            data = p.stdout.read(4096)
            if not data:
                break
            data = rest + data
            n = len(data) // frame
            rest = data[n * frame:]
            if n and self.out is not None:
                self.out.write(data[:n * frame], rate, ch)
            if n and self.deliver is None:
                self.t = time.time()
            elif n:
                x = np.frombuffer(data[:n * frame], dtype="<i2").astype(np.float32).reshape(n, ch) / 32768.0
                self.push(rs.feed(x))
        try:
            p.terminate()
        except OSError:
            pass
        self.proc = None
        if self.out is not None:
            self.out.end()
        return True

    def push(self, x):
        if not len(x):
            return
        self.t = time.time()
        if self.buf is None or self.buf.shape[1] != x.shape[1]:
            self.buf = x[:0]
        self.buf = np.concatenate([self.buf, x])
        while len(self.buf) >= self.hop:                # in Bloecke wie von der Soundkarte zerlegen
            self.deliver(self.buf[:self.hop].copy())
            self.blocks += 1
            self.buf = self.buf[self.hop:]
        if len(self.buf) > self.hop * 8:
            self.buf = self.buf[-self.hop:]

    def status(self):
        alive = self.t is not None and time.time() - self.t < 2.0
        name = ""
        if self.mac:
            try:
                name = self.names(self.mac) if self.names else self.mac
            except Exception:                           # noqa: BLE001
                name = self.mac
        return {"alive": alive, "connected": bool(self.mac), "src": name, "rate": self.src_rate, "blocks": self.blocks,
                "error": self.error}


# ---- Weiterleitung an eine Ausgabe (Wunsch von Markus 25.11.2026) -------------------------------------------------
# Wer am Handy den Pi als Ausgabe waehlt, hoert dort selbst nichts mehr. Der Pi gibt den Ton darum auf Wunsch an eine
# eigene Ausgabe weiter (Kopfhoereranschluss des Pi, USB-Soundkarte ins Mischpult, HDMI), mit "aplay" (alsa-utils).
# Dieselben Samples wie fuer die Analyse, unveraendert (Abtastrate des Handys). Aufs Licht wirkt das nie.
CARD_RE = re.compile(r"^card (\d+): (\S+) \[(.*?)\], device (\d+): (.*?) \[(.*?)\]")
OUT_QUEUE = 400                        # so viele Stuecke warten hoechstens auf die Ausgabe (LAN: 256 Bilder, Handy: 1024)
# Uhren-Ausgleich (Fehlerbericht 25.11.2026: Aussetzer an der JBL). Die Quelle (Mac, Handy) und die Ausgabe (Lautsprecher,
# Soundkarte) haben je eine eigene Uhr, die minimal anders laeuft. Bisher wuchs die Warteschlange langsam, bis sie voll war,
# dann fiel jedes Mal ein Stueck Ton weg (64 Mal in 8 Minuten). Jetzt wird die Umrechnung um hoechstens DRIFT_MAX schneller
# oder langsamer, sodass rund FILL_TARGET_S Ton in der Warteschlange wartet (unhoerbar, 0,5 % sind weniger als 1/10 Halbton).
FILL_TARGET_S = 0.12
DRIFT_K = 0.05                         # je Sekunde Abweichung so viel schneller/langsamer
DRIFT_MAX = 0.005
DRIFT_SMOOTH = 0.02                    # Glaettung je Stueck
OUT_RETRY_S = 2.0                      # nach einem Fehler der Ausgabe fruehestens so spaet wieder versuchen
BT_CONNECT_S = 10.0                    # nicht verbundenen Lautsprecher hoechstens so oft anrufen
BT_KEEP_S = 1800.0                     # Lautsprecher in Pausen so lange mit Stille verbunden halten (dann darf er schlafen)
KEEP_STEP_S = 0.2                      # so viel Stille je Schritt


def out_label(card_id, long_name, dev_name, n_devs):
    """Lesbarer Name einer Ausgabe aus "aplay -l"."""
    low = (card_id + " " + long_name).lower()
    if "headphones" in low:
        name = "Kopfhörer-Anschluss des Licht-Rechners"
    elif "hdmi" in low:
        name = "HDMI " + (str(int(card_id[-1]) + 1) if card_id[-1:].isdigit() else "")
    else:
        name = long_name or card_id
    if n_devs > 1 and dev_name and dev_name.lower() not in name.lower():
        name += " – " + dev_name
    return name.strip()


def speakers(runner=run):
    """Verbundene Bluetooth-Lautsprecher (bluez-alsa a2dp-source): [(MAC, PCM-Pfad)]."""
    if runner is run and shutil.which("bluealsa-cli") is None:
        return []
    rc, out = runner(["bluealsa-cli", "list-pcms"], 4.0)
    if rc != 0:
        return []
    res = []
    for line in out.split():
        if "/a2dpsrc/" in line and line.endswith("/sink"):
            m = re.search(r"dev_([0-9A-F_]{17})", line, re.I)
            if m:
                res.append((m.group(1).replace("_", ":").upper(), line.strip()))
    return res


def list_outputs(runner=run, names=None):
    """Ausgaenge der Soundkarten: [{"dev": "plughw:CARD=X,DEV=0", "name": ...}], dazu verbundene Bluetooth-Lautsprecher
    als "bt:MAC" (25.11.2026). Ohne aplay keine Soundkarten."""
    bt = []
    for mac, _ in speakers(runner):
        try:
            nm = names(mac) if names else mac
        except Exception:                                   # noqa: BLE001
            nm = mac
        bt.append({"dev": "bt:" + mac, "name": "Bluetooth-Lautsprecher " + str(nm)})
    if runner is run and shutil.which("aplay") is None:
        return bt
    rc, out = runner(["aplay", "-l"], 4.0)
    if rc != 0:
        return bt
    rows = []
    for line in out.splitlines():
        m = CARD_RE.match(line.strip())
        if m:
            rows.append((m.group(2), m.group(3), int(m.group(4)), m.group(6)))
    count = {}
    for cid, _, _, _ in rows:
        count[cid] = count.get(cid, 0) + 1
    return [{"dev": f"plughw:CARD={cid},DEV={d}", "name": out_label(cid, long, dn, count[cid])}
            for cid, long, d, dn in rows] + bt


def convert(data, rate, ch, prate, pch, rs):
    """int16-Bytes (rate, ch) -> int16-Bytes (prate, pch) fuer einen Lautsprecher mit festem Format. rs: Resampler
    (auch bei gleicher Rate, fuer den Uhren-Ausgleich)."""
    if (rate, ch) == (prate, pch) and rs is None:
        return data
    n = len(data) // (2 * ch)
    x = np.frombuffer(data[:n * 2 * ch], dtype="<i2").astype(np.float32).reshape(n, ch) / 32768.0
    if ch != pch:
        x = np.repeat(x[:, :1], pch, axis=1) if ch == 1 else np.repeat(x.mean(axis=1, keepdims=True), pch, axis=1)
    if rs is not None:
        x = rs.feed(x)
    return (np.clip(x, -1.0, 32767 / 32768.0) * 32768.0).astype("<i2").tobytes()


class PassThrough:
    """Schreibt die rohen Samples (int16) in ein aplay auf der gewaehlten Ausgabe. Ein eigener Faden schreibt, damit eine
    haengende Ausgabe nie den Eingang (und damit die Analyse) aufhaelt: ist die Warteschlange voll, wird verworfen."""

    def __init__(self, spawn=None, clock=time.time, runner=run, connector=None):
        import queue
        self._queue_mod = queue
        self.spawn = spawn or (lambda args: subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                                             stderr=subprocess.PIPE, bufsize=0))
        self.clock = clock
        self.runner = runner               # bluealsa-cli (Bluetooth-Lautsprecher)
        self.connector = connector or (lambda mac: manager().connect(mac))
        self.conn_t = None
        self.conv = None                   # (Abtastrate, Kanaele, Resampler) des Lautsprechers
        self.idle_t = None                 # seit wann kein Ton kommt (Lautsprecher bekommt Stille)
        self.qframes = 0                   # Bilder in der Warteschlange (fuer den Uhren-Ausgleich)
        self.drift = 0.0                   # aktuelle Korrektur der Umrechnung (+ = schneller abspielen)
        self.dev = ""
        self.q = queue.Queue(maxsize=OUT_QUEUE)
        self.proc, self.fmt = None, None
        self.error, self.dropped, self.written = "", 0, 0
        self.t = None                      # letzte Weitergabe
        self.fail_t = None
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def set_dev(self, dev):
        dev = str(dev or "")
        if dev != self.dev:
            self.dev, self.error = dev, ""
            self.fail_t = None
            self._put(None)                # laufendes aplay schliessen, beim naechsten Stueck auf der neuen Ausgabe

    def write(self, data, rate, ch):
        if self.dev and data:
            if self._put((bytes(data), int(rate), int(ch))):
                self.qframes += len(data) // (2 * max(1, int(ch)))

    def end(self):
        """Der Ton ist vorbei (Handy getrennt): Ausgabe freigeben. Bluetooth-Lautsprecher: mit Stille verbunden halten
        (25.11.2026: die JBL trennte sich sonst, sobald die Musik aufhoerte, und spielte danach erst nach "Verbinden")."""
        self._put("END")

    def _put(self, item):
        try:
            self.q.put_nowait(item)
            return True
        except self._queue_mod.Full:
            self.dropped += 1
            return False

    def close(self):
        self._run = False
        self._put(None)
        self._thread.join(timeout=1.5)
        self._kill()

    def _kill(self):
        p, self.proc, self.fmt = self.proc, None, None
        if p is None:
            return
        try:
            p.stdin.close()
        except (OSError, ValueError, AttributeError):
            pass
        try:
            p.terminate()
        except OSError:
            pass

    def _start(self, rate, ch, now):
        """aplay auf einer Soundkarte, oder bluealsa-cli open auf einem Bluetooth-Lautsprecher ("bt:MAC")."""
        self.conv = (rate, ch, Resampler(rate, rate))     # Soundkarte: gleiches Format, nur Uhren-Ausgleich
        self.drift = 0.0
        if not self.dev.startswith("bt:"):
            return self.spawn(["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(rate), "-c", str(ch),
                               "-D", self.dev, "--buffer-time=150000"])
        mac = self.dev[3:]
        path = dict(speakers(self.runner)).get(mac)
        if path is None:                   # Lautsprecher nicht verbunden: ab und zu anrufen
            self.error, self.fail_t = "Bluetooth-Lautsprecher nicht verbunden", now
            if self.conn_t is None or now - self.conn_t >= BT_CONNECT_S:
                self.conn_t = now
                try:
                    self.connector(mac)
                except Exception:                           # noqa: BLE001
                    pass
            return None
        rc, info = self.runner(["bluealsa-cli", "info", path], 4.0)
        prate, pch = pcm_format(info if rc == 0 else "")
        self.conv = (prate, pch, Resampler(rate, prate))
        return self.spawn(["bluealsa-cli", "open", path])

    def _dead_reason(self, p):
        try:
            err = p.stderr.read() if p.stderr else b""
        except (OSError, ValueError):
            err = b""
        txt = (err or b"").decode("utf-8", "replace").strip().splitlines()
        return ("Ausgabe: " + txt[-1])[:140] if txt else "Ausgabe beendet"

    def _loop(self):
        while self._run:
            try:
                item = self.q.get(timeout=KEEP_STEP_S)
            except self._queue_mod.Empty:
                self._keep_alive()
                continue
            self._handle(item)

    def _handle(self, item):
        """Ein Stueck aus der Warteschlange bearbeiten (eigener Faden; Tests rufen es direkt auf)."""
        if True:
            if item is None:
                self._kill()
                return
            if item == "END":
                if self.dev.startswith("bt:") and self.proc is not None:
                    self.idle_t = self.idle_t or self.clock()
                else:
                    self._kill()
                return
            data, rate, ch = item
            self.qframes = max(0, self.qframes - len(data) // (2 * max(1, ch)))
            if not self.dev:
                return
            now = self.clock()
            if self.proc is not None and (self.fmt != (self.dev, rate, ch) or self.proc.poll() is not None):
                if self.proc.poll() is not None:
                    self.error, self.fail_t = self._dead_reason(self.proc), now
                self._kill()
            if self.proc is None:
                if self.fail_t is not None and now - self.fail_t < OUT_RETRY_S:
                    return
                try:
                    self.proc = self._start(rate, ch, now)
                    if self.proc is None:
                        return
                    self.fmt = (self.dev, rate, ch)
                except OSError as e:
                    self.error, self.fail_t = ("Ausgabe nicht gestartet: " + str(e))[:140], now
                    return
            if self.conv is not None:
                prate, pch, rs = self.conv
                if rs is not None:                       # Uhren-Ausgleich: Warteschlange um FILL_TARGET_S halten
                    err = self.qframes / float(rate) - FILL_TARGET_S
                    want = max(-DRIFT_MAX, min(DRIFT_MAX, err * DRIFT_K))
                    self.drift += (want - self.drift) * DRIFT_SMOOTH
                    rs.step = float(rate) / float(prate) * (1.0 + self.drift)
                data = convert(data, rate, ch, prate, pch, rs)
            try:
                self.proc.stdin.write(data)
                self.written += len(data)
                self.t = now
                self.idle_t = None
                self.error, self.fail_t = "", None
            except (OSError, ValueError):
                self.error, self.fail_t = self._dead_reason(self.proc), now
                self._kill()

    def _keep_alive(self):
        """Pause beim Bluetooth-Lautsprecher: Stille im Format des Lautsprechers, hoechstens BT_KEEP_S lang."""
        if not self.dev.startswith("bt:") or self.proc is None or self.fmt is None:
            return
        now = self.clock()
        if self.idle_t is None:
            self.idle_t = now
        if now - self.idle_t > BT_KEEP_S:
            self.idle_t = None
            self._kill()                   # lange Pause: Lautsprecher freigeben, er darf schlafen
            return
        rate, ch = (self.conv[0], self.conv[1]) if self.conv is not None else (self.fmt[1], self.fmt[2])
        try:
            self.proc.stdin.write(bytes(int(rate * KEEP_STEP_S) * ch * 2))
            self.kept = getattr(self, "kept", 0) + 1
        except (OSError, ValueError):
            self.error, self.fail_t = self._dead_reason(self.proc), now
            self._kill()

    def status(self):
        return {"dev": self.dev, "active": self.t is not None and self.clock() - self.t < 2.0,
                "drift": round(self.drift * 100, 3), "fill": round(self.qframes / 44100.0, 3),
                "error": self.error, "dropped": self.dropped}
