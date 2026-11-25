"""WLAN trennen im Panel (Wunsch von Markus 25.11.2026): Bluetooth und WLAN teilen sich am Pi einen Funkchip. Den Funk ganz
abzuschalten liess Bluetooth abstuerzen (hci0: hardware error), darum trennt der Knopf nur die Verbindung. Ohne Hardware:
nmcli nachgespielt. Geprueft: Stand, Trennen nur mit Kabel, Funk bleibt an (und wird wieder eingeschaltet), Waechter haelt
getrennt und verbindet ohne Kabel nach CABLE_LOST_S wieder, fehlende Erlaubnis, Befehl ueber die Show mit Einstellung."""
import os
import tempfile

from _common import build, check, finish

import wlan
from wlan import Wlan, cable_up

st = {"radio": "enabled", "conn": True, "perm": "yes", "cable": True, "want": False, "calls": []}


def runner(cmd, timeout=0):
    st["calls"].append(" ".join(cmd[1:]))
    if cmd[1:] == ["-t", "-f", "WIFI", "radio"]:
        return 0, st["radio"] + "\n"
    if cmd[1:] == ["-t", "-f", "DEVICE,STATE", "device"]:
        return 0, "eth0:connected\nwlan0:%s\nlo:connected (externally)\n" % ("connected" if st["conn"] else "disconnected")
    if cmd[1:] == ["-t", "general", "permissions"]:
        return 0, ("org.freedesktop.NetworkManager.enable-disable-wifi:%s\norg.freedesktop.NetworkManager.network-control:%s\n"
                   % (st["perm"], st["perm"]))
    if st["perm"] != "yes":
        return 1, "Error: Not authorized to control networking."
    if cmd[1:3] == ["radio", "wifi"]:
        st["radio"] = "enabled" if cmd[3] == "on" else "disabled"
        return 0, ""
    if cmd[1:3] == ["device", "disconnect"] and cmd[3] == "wlan0":
        st["conn"] = False
        return 0, ""
    if cmd[1:3] == ["device", "connect"] and cmd[3] == "wlan0":
        st["conn"] = True
        return 0, ""
    return 1, ""


clock = [100.0]
w = Wlan(runner=runner, cable=lambda: st["cable"], clock=lambda: clock[0], tool=True, want_off=lambda: st["want"])
s = w.status()
check(s["tool"] and s["on"] is True and s["cable"] and s["allowed"] and not s["want_off"], "Stand: verbunden, Kabel, erlaubt")
st["want"] = True
w.apply(False)
check(not st["conn"] and st["radio"] == "enabled", "trennen: Verbindung weg, Funk bleibt an")
check(not any(c.startswith("radio wifi off") for c in st["calls"]), "nie den Funk abschalten (Bluetooth stuerzte ab)")
st["want"] = False
w.apply(True)
check(st["conn"], "wieder verbinden")
st["cable"] = False
try:
    w.check(False)
    ok = False
except ValueError as e:
    ok = "Kabel" in str(e)
check(ok, "ohne Kabel: nicht trennen")
st["cable"] = True

# Funk vom frueheren Knopf noch aus: Waechter schaltet ihn ein
st["radio"] = "disabled"
check(w.watch_once() == "radio" and st["radio"] == "enabled", "Funk aus: Waechter schaltet ihn wieder ein")

# Waechter haelt getrennt (z. B. nach Neustart verbindet NetworkManager von selbst)
st["want"], st["conn"] = True, True
check(w.watch_once() == "disconnect" and not st["conn"], "gewuenscht getrennt: Waechter trennt")
check(w.watch_once() is None, "getrennt: nichts zu tun")
st["cable"] = False
w.watch_once()
clock[0] += wlan.CABLE_LOST_S - 1
check(w.watch_once() is None and not st["conn"], "Kabel kurz weg: noch warten")
clock[0] += 2
check(w.watch_once() == "connect" and st["conn"], "Kabel %d s weg: WLAN wieder verbunden" % wlan.CABLE_LOST_S)
check(w.watch_once() is None and st["conn"], "ohne Kabel bleibt es verbunden")
st["cable"] = True
check(w.watch_once() == "disconnect" and not st["conn"], "Kabel wieder da: wieder getrennt")
st["want"] = False
check(w.watch_once() is None and not st["conn"], "nicht gewuenscht: Waechter verbindet nicht von selbst")

st["perm"] = "no"
check(not w.status()["allowed"], "ohne Erlaubnis: Knopf gesperrt")
try:
    w.apply(True)
    ok = False
except ValueError as e:
    ok = "bluetooth_setup.sh" in str(e)
check(ok, "nicht erlaubt: Hinweis auf bluetooth_setup.sh")
st["perm"] = "yes"
check(Wlan(tool=False).status() == {"tool": False}, "ohne NetworkManager (Mac, Windows): kein Knopf")

d = tempfile.mkdtemp()
for name, car in (("lo", "1"), ("wlan0", "1"), ("eth0", "0")):
    os.makedirs(os.path.join(d, name))
    open(os.path.join(d, name, "carrier"), "w").write(car)
check(not cable_up(d), "eth0 ohne Verbindung: kein Kabel (WLAN zaehlt nicht)")
open(os.path.join(d, "eth0", "carrier"), "w").write("1\n")
check(cable_up(d), "eth0 verbunden: Kabel")

# Befehl ueber die Show: Einstellung wlan_trennen merken, sofort umsetzen
rig, sh = build()
st["conn"] = True
wlan._MGR = Wlan(runner=runner, cable=lambda: True, tool=True, want_off=lambda: sh.cfg["wlan_trennen"] > 0.5)
check(sh.cfg["wlan_trennen"] == 0.0, "Standard: WLAN verbunden")
sh.command({"wlan": {"on": False}})
check(sh.cfg["wlan_trennen"] == 1.0 and not st["conn"], "Befehl: trennen, Einstellung gemerkt")
sh.command({"wlan": {"on": True}})
check(sh.cfg["wlan_trennen"] == 0.0 and st["conn"], "Befehl: wieder verbinden")
wlan._MGR = None
txt = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi", "bluetooth_setup.sh"), encoding="utf-8").read()
check("NetworkManager.network-control" in txt, "Einrichtung erlaubt das Trennen")
finish("test_wlan_schalter")
