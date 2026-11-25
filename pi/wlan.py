#!/usr/bin/env python3
"""
wlan.py - WLAN-Verbindung des Licht-Rechners im Panel trennen (Wunsch von Markus 25.11.2026).

Warum: Bluetooth und WLAN teilen sich am Pi einen Funkchip (BCM43455). Haengt der Pi am Kabel, stoert der WLAN-Verkehr den
Bluetooth-Ton (Handy -> Pi -> Lautsprecher kam abgehackt).

Wichtig (Test 25.11.2026): den WLAN-Funk NICHT ganz abschalten ("nmcli radio wifi off" / rfkill). Danach stuerzte der
Bluetooth-Teil des Chips nach ein bis zwei Minuten Ton an die JBL ab ("hci0: hardware error 0x00", erst ein Neustart des Pi
half), zweimal hintereinander. Deshalb trennt der Knopf nur die Verbindung (nmcli device disconnect), der Funk bleibt an;
ist er (vom frueheren Knopf) noch aus, schaltet ihn der Waechter wieder ein.

Gewuenscht wird ueber die Einstellung wlan_trennen (settings.json, bleibt ueber einen Neustart). Der Waechter (eigener
Faden, alle WATCH_S Sekunden) setzt sie um:
  - gewuenscht getrennt und Kabel da: WLAN-Verbindung trennen;
  - Kabel laenger als CABLE_LOST_S weg: WLAN wieder verbinden (sonst waere der Licht-Rechner nicht erreichbar).
Ausschalten nur mit Kabel. Erlaubt durch die polkit-Regel aus bluetooth_setup.sh. Aufs Licht wirkt das nie.
"""
import os
import shutil
import subprocess
import threading
import time

WATCH_S = 5.0
CABLE_LOST_S = 20.0
NET_DIR = "/sys/class/net"
IFACE = "wlan0"


def run(cmd, timeout=8.0):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def cable_up(net_dir=NET_DIR):
    """Ist ein Kabel-Anschluss (eth*/en*) verbunden?"""
    try:
        names = os.listdir(net_dir)
    except OSError:
        return False
    for n in names:
        if n.startswith(("eth", "en")):
            try:
                with open(os.path.join(net_dir, n, "carrier")) as f:
                    if f.read().strip() == "1":
                        return True
            except OSError:
                pass
    return False


class Wlan:
    def __init__(self, runner=run, cable=cable_up, clock=time.time, tool=None, want_off=None):
        self.runner, self.cable, self.clock = runner, cable, clock
        self.tool = shutil.which("nmcli") is not None if tool is None else tool
        self.want_off = want_off or (lambda: False)      # Einstellung wlan_trennen (von der Show gesetzt)
        self.msg, self.error = "", ""
        self.lost_t = None
        self.rescue = False                               # Kabel weg: WLAN vom Waechter verbunden
        self._thread = None

    # ---- Stand ----
    def radio_on(self):
        rc, out = self.runner(["nmcli", "-t", "-f", "WIFI", "radio"])
        if rc != 0:
            return None
        v = out.strip().splitlines()[-1].strip().lower() if out.strip() else ""
        return True if v == "enabled" else False if v == "disabled" else None

    def connected(self):
        """WLAN-Verbindung aktiv? None = kein WLAN-Geraet."""
        rc, out = self.runner(["nmcli", "-t", "-f", "DEVICE,STATE", "device"])
        if rc != 0:
            return None
        for line in out.splitlines():
            dev, _, state = line.partition(":")
            if dev == IFACE:
                return state.strip().startswith("connected")
        return None

    def allowed(self):
        rc, out = self.runner(["nmcli", "-t", "general", "permissions"])
        need = {"org.freedesktop.NetworkManager.network-control", "org.freedesktop.NetworkManager.enable-disable-wifi"}
        ok = set()
        for line in out.splitlines():
            k, _, v = line.partition(":")
            if k in need and v.strip() == "yes":
                ok.add(k)
        return ok == need

    def status(self):
        if not self.tool:
            return {"tool": False}
        return {"tool": True, "on": self.connected(), "radio": self.radio_on(), "want_off": bool(self.want_off()),
                "cable": bool(self.cable()), "allowed": self.allowed(), "msg": self.msg, "error": self.error}

    # ---- Bedienung ----
    def check(self, on):
        if not self.tool:
            raise ValueError("WLAN laesst sich hier nicht schalten (kein NetworkManager)")
        if not on and not self.cable():
            raise ValueError("Kein Kabel verbunden: WLAN bleibt verbunden, sonst ist der Licht-Rechner nicht mehr erreichbar")

    def _nm(self, *args):
        rc, out = self.runner(["nmcli"] + list(args))
        if rc != 0:
            self.error = ("WLAN schalten nicht erlaubt: bluetooth_setup.sh noch einmal ausfuehren"
                          if "authoriz" in out.lower() or "not allowed" in out.lower() else out.strip()[:140])
            return False
        self.error = ""
        return True

    def apply(self, on):
        """Nach dem Umstellen der Einstellung sofort umsetzen (der Waechter haelt es danach)."""
        self.rescue, self.lost_t = False, None
        if self.radio_on() is False:
            self._nm("radio", "wifi", "on")
        if on:
            ok = self._nm("device", "connect", IFACE)
            self.msg = "WLAN wird verbunden" if ok else ""
        else:
            ok = self.connected() is False or self._nm("device", "disconnect", IFACE)
            self.msg = "WLAN getrennt (Licht-Rechner nur noch ueber Kabel erreichbar)" if ok else ""
        if not ok:
            raise ValueError(self.error)
        return True

    def watch_once(self):
        """Funk immer an; gewuenscht getrennt: getrennt halten, aber ohne Kabel nach CABLE_LOST_S wieder verbinden."""
        if not self.tool:
            return None
        if self.radio_on() is False:                     # frueherer Knopf (Funk aus): Bluetooth stuerzte ab
            self._nm("radio", "wifi", "on")
            self.msg = "WLAN-Funk wieder eingeschaltet (Funk aus stoert Bluetooth)"
            return "radio"
        if not self.want_off():
            self.lost_t, self.rescue = None, False
            return None
        if self.cable():
            self.lost_t = None
            if self.connected():
                self.rescue = False
                self._nm("device", "disconnect", IFACE)
                return "disconnect"
            return None
        if self.rescue:
            return None
        now = self.clock()
        if self.lost_t is None:
            self.lost_t = now
            return None
        if now - self.lost_t < CABLE_LOST_S:
            return None
        self.rescue = True
        self._nm("device", "connect", IFACE)
        self.msg = "Kabel weg: WLAN wieder verbunden"
        print("WLAN: " + self.msg)
        return "connect"

    def start_watch(self):
        if not self.tool or self._thread is not None:
            return

        def loop():
            while True:
                try:
                    self.watch_once()
                except Exception:                           # noqa: BLE001  der Waechter haelt nie an
                    pass
                time.sleep(WATCH_S)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()


_MGR = None


def manager():
    global _MGR
    if _MGR is None:
        _MGR = Wlan()
    return _MGR
