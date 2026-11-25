#!/usr/bin/env python3
"""
apc_relay.py - APC mini mk2 am MacBook, Bedienung des Light-Butler (Pi) ueber das Netzwerk.

Liest den APC per USB und schickt jede Taste und jeden Fader per UDP (Port 9021) an den Pi; die LED-Farben, die der
Pi zurueckschickt, gehen an den APC. Jede Sekunde ein Lebenszeichen, auch ohne APC (dann mit dev=false). Steckt der
APC ab oder wieder an, verbindet sich das Programm von selbst neu (Suche alle 2 s).

Laeuft in der Mixxx-Bruecke mit (mixxx_bridge.py --send PI), oder allein zum Testen:
    python3 apc_relay.py lightbutler.local
Braucht mido und python-rtmidi (in ~/s2l schon installiert).

Wichtig: In Mixxx unter Einstellungen > Controller den APC mini NICHT aktivieren, sonst reagiert auch Mixxx auf die Tasten.

Dieselbe Weiterleitung bedient auch den ROLI LUMI Keys (lumi_relay, UDP 9023, nur Noten).
"""
import json
import os
import socket
import sys
import threading
import time
import uuid

NET_PORT = 9021
HINT = "apc mini mk2"
LUMI_PORT = 9023
LUMI_HINT = "lumi keys"
HELPER_PID = os.path.expanduser("~/.light-butler-helfer.pid")   # schreibt der Light-Butler Helfer, solange er laeuft
BRIDGE_PID = os.path.expanduser("~/.light-butler-bruecke.pid")  # schreibt die Mixxx-Bruecke (mit --send), solange sie laeuft


def proc_running(path, name, cmdline=None):
    """True, wenn die Prozessnummer in path zu einem laufenden Programm name (z. B. "helper.py") gehoert.
    Die Nummer in der Datei kann nach einem Neustart des Mac zu einem fremden Prozess gehoeren: darum wird auch
    geprueft, ob dieser Prozess wirklich name ist."""
    try:
        with open(path) as f:
            pid = int(f.read().strip() or 0)
        if pid <= 0 or pid == os.getpid():
            return False
        if sys.platform == "win32":
            if not _win_alive(pid):                   # NIE os.kill(pid, 0) unter Windows: das BEENDET den Prozess
                return False
        else:
            os.kill(pid, 0)                           # Prozess noch da? (Mac/Linux: Signal 0 prueft nur)
    except (OSError, ValueError):
        return False
    if cmdline is None:
        import subprocess
        cmd = (["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Process -Filter 'ProcessId=%d').CommandLine" % pid]
               if sys.platform == "win32" else ["ps", "-p", str(pid), "-o", "command="])
        try:
            cmdline = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return True                               # im Zweifel: laeuft
    return name in cmdline


def _win_alive(pid):
    """Windows: laeuft der Prozess? Nur lesend (OpenProcess mit Abfragerecht, Exit-Code 259 = laeuft noch)."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE          # 64 Bit: ohne Typen wird das Handle verfaelscht
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    h = k32.OpenProcess(0x1000, False, int(pid))     # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259
    finally:
        k32.CloseHandle(h)


def helper_running(path=HELPER_PID, cmdline=None):
    """True, wenn der Light-Butler Helfer laeuft. Dann ueberlaesst die Mixxx-Bruecke ihm APC und Ton."""
    return proc_running(path, "helper.py", cmdline)


def bridge_running(path=BRIDGE_PID, cmdline=None):
    """True, wenn die Mixxx-Bruecke laeuft. Dann ueberlaesst ihr der Helfer die Bibliothek (Liste, Vorhoeren, Schaetzung, Analyse)."""
    return proc_running(path, "mixxx_bridge.py", cmdline)


def write_pid(path):
    with open(path, "w") as f:
        f.write(str(os.getpid()))


def remove_pid(path):
    """Prozessdatei loeschen, aber nur die eigene."""
    try:
        with open(path) as f:
            mine = int(f.read().strip() or 0) == os.getpid()
        if mine:                                      # erst nach dem Schliessen loeschen (Windows: offene Datei geht nicht)
            os.remove(path)
    except (OSError, ValueError):
        pass


def valid(d):
    """Nur Note an/aus und Regler mit drei Bytes (gleiche Pruefung wie am Pi)."""
    return (isinstance(d, list) and len(d) == 3 and all(isinstance(x, int) for x in d)
            and 0x80 <= d[0] <= 0xBF and 0 <= d[1] <= 127 and 0 <= d[2] <= 127)


class ApcRelay:
    def __init__(self, pi_host, port=NET_PORT, hint=HINT, mido_mod=None, sock=None, log=print, paused=None, label="APC", notes_only=False):
        self.pi = (pi_host, port)
        self.addr, self.addr_t = None, -99.0          # aufgeloeste Adresse des Pi (lightbutler.local), alle 30 s neu
        self.hint = hint.lower()
        self.label = label                            # Name des Geraets in den Meldungen
        self.notes_only = notes_only                  # True: nur Note an/aus weiterleiten (Lumi: kein Regler, kein Druck)
        self.mido = mido_mod
        self.sock = sock
        self.log = log
        self.sid = uuid.uuid4().hex[:12]              # neue Sitzung bei jedem Start: der Pi sendet dann alle LEDs neu
        self.inp = self.out = None
        self.name = ""
        self.last_try = 0.0
        self.gen = 0                                  # zaehlt jedes Oeffnen des APC: der Pi sendet dann alle LEDs neu
        self.paused = paused                          # Funktion: True = ein anderes Programm (Helfer) leitet weiter
        self.last_check = 0.0
        self._run = False

    # ---- Netz ---------------------------------------------------------------------------------------------------------
    def _target(self):
        """Adresse des Pi einmal aufloesen statt bei jedem Paket (mDNS kann dauern)."""
        now = time.monotonic()
        if self.addr is None or now - self.addr_t > 30.0:
            self.addr_t = now
            try:
                try:
                    import pi_addr                    # Kabel und WLAN: die Adresse, die antwortet (25.11.2026)
                    ip = pi_addr.best(self.pi[0])
                except ImportError:
                    ip = self.pi[0]
                self.addr = (socket.gethostbyname(ip), self.pi[1])
            except OSError:
                pass                                  # alte Adresse behalten, spaeter neu versuchen
        return self.addr

    def _send(self, obj):
        obj["sid"] = self.sid
        addr = self._target()
        if addr is None:
            return
        try:
            self.sock.sendto(json.dumps(obj).encode(), addr)
        except OSError:
            pass                                      # Pi gerade nicht erreichbar: naechstes Lebenszeichen versucht es wieder

    def hello(self):
        self._send({"t": "hello", "dev": self.inp is not None, "name": self.name, "gen": self.gen})

    def from_pi(self, data):
        """LED-Meldung vom Pi an den APC weitergeben."""
        try:
            m = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not (isinstance(m, dict) and m.get("t") == "midi" and valid(m.get("d")) and self.out is not None):
            return
        try:
            self.out.send(self.mido.Message.from_bytes(m["d"]))
        except Exception:                             # noqa: BLE001
            self._drop()

    # ---- APC --------------------------------------------------------------------------------------------------------
    def connect(self, now):
        if self.inp is not None or now - self.last_try < 2.0:
            return self.inp is not None
        self.last_try = now
        try:
            ins = sorted(n for n in self.mido.get_input_names() if self.hint in n.lower())
            outs = sorted(n for n in self.mido.get_output_names() if self.hint in n.lower())
            if not ins or not outs:
                return False
            self.inp, self.out = self.mido.open_input(ins[0]), self.mido.open_output(outs[0])
            self.name = ins[0]
            self.gen += 1
            self.log(f"{self.label}: verbunden ({self.name}), Tasten gehen an {self.pi[0]}:{self.pi[1]}")
            self.hello()
            return True
        except Exception as e:                        # noqa: BLE001
            self.log(f"{self.label}: nicht zu oeffnen ({e})")
            self._drop()
            return False

    def _drop(self):
        for p in (self.inp, self.out):
            try:
                if p is not None:
                    p.close()
            except Exception:                         # noqa: BLE001
                pass
        if self.inp is not None:
            self.log(f"{self.label}: getrennt")
        self.inp = self.out = None

    def check_gone(self, now):
        """APC abgezogen? macOS meldet keinen Fehler, der Port verschwindet nur aus der Liste (alle 1 s geprueft).
        Nach dem Wiederanstecken ist der APC dunkel: neu oeffnen, der Pi schickt dann alle LEDs neu."""
        if self.inp is None or now - self.last_check < 1.0:
            return
        self.last_check = now
        try:
            if self.name not in self.mido.get_input_names():
                self._drop()
                self.hello()
        except Exception:                             # noqa: BLE001
            pass

    def pump(self):
        """Tasten und Fader vom APC an den Pi."""
        if self.inp is None:
            return
        try:
            for msg in self.inp.iter_pending():
                d = list(msg.bytes())
                if valid(d) and (not self.notes_only or d[0] < 0xA0):
                    self._send({"t": "midi", "d": d})
        except Exception:                             # noqa: BLE001
            self._drop()

    # ---- Ablauf -----------------------------------------------------------------------------------------------------
    def start(self):
        if self.mido is None:
            try:
                import mido
                self.mido = mido
            except ImportError:
                self.log(f"{self.label}: mido fehlt (pip install mido python-rtmidi), Weiterleitung aus")
                return False
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("0.0.0.0", 0))
        self._run = True
        threading.Thread(target=self._rx, daemon=True).start()
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def _rx(self):
        while self._run:
            try:
                data, _ = self.sock.recvfrom(2048)
            except OSError:
                time.sleep(0.5)
                continue
            self.from_pi(data)

    def _loop(self):
        last_hello = 0.0
        while self._run:
            now = time.monotonic()
            if self.paused is not None and self.paused():          # Helfer laeuft: nichts tun (kein Lebenszeichen)
                if self.inp is not None:
                    self._drop()
                    self.log(f"{self.label}: Weiterleitung uebernimmt der Light-Butler Helfer")
                time.sleep(1.0)
                continue
            self.check_gone(now)
            self.connect(now)
            self.pump()
            if now - last_hello >= 1.0:
                last_hello = now
                self.hello()
            time.sleep(0.003)

    def stop(self):
        self._run = False
        self._drop()
        self.hello()


def lumi_relay(pi_host, port=LUMI_PORT, **kw):
    """Weiterleitung fuer den ROLI LUMI Keys: eigener Port, nur Noten."""
    return ApcRelay(pi_host, port, hint=LUMI_HINT, label="Lumi", notes_only=True, **kw)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Aufruf: python3 apc_relay.py <Adresse des Pi>  (zum Beispiel lightbutler.local)")
    r = ApcRelay(sys.argv[1])
    if not r.start():
        sys.exit(1)
    print("Weiterleitung laeuft, Strg+C beendet.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        r.stop()
