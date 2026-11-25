"""Erreichbare Adresse des Pi (Fehlerbericht 25.11.2026): nach "WLAN ausschalten" lieferte die FritzBox fuer den Namen
des Pi zuerst noch die WLAN-Adresse, Helfer und Mixxx-App schickten ins Leere ("Musik-Rechner nicht erreichbar").
Geprueft: die antwortende Adresse wird genommen, gemerkt, im Hintergrund neu geprueft; eine Adresse/IP ohne Pruefung;
send_udp der Bruecke, APC und Ton nehmen sie."""
import os
import socket
import sys
import time

from _common import check, finish

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mac", "mixxx_bridge"))
import pi_addr  # noqa: E402

WLAN, KABEL = "192.168.1.113", "192.168.1.127"
up = {KABEL}
tried = []


def resolver(host, port, fam, typ):
    if host == "pi.test":
        return [(fam, typ, 0, "", (WLAN, 0)), (fam, typ, 0, "", (KABEL, 0)), (fam, typ, 0, "", (WLAN, 0))]
    if host == "eins.test":
        return [(fam, typ, 0, "", ("10.0.0.9", 0))]
    raise socket.gaierror("unbekannt")


class Conn:
    def close(self):
        pass


def connector(addr, timeout):
    tried.append(addr[0])
    if addr[0] in up:
        return Conn()
    raise OSError("Host is down")


kw = {"resolver": resolver, "connector": connector}
check(pi_addr.probe("pi.test", **kw) == KABEL, "WLAN aus: die Kabel-Adresse")
up.add(WLAN)
check(pi_addr.probe("pi.test", **kw) == WLAN, "beide da: wie bisher die erste")
up.clear()
check(pi_addr.probe("pi.test", **kw) == WLAN, "keine antwortet: wie bisher die erste")
tried.clear()
check(pi_addr.probe("eins.test", **kw) == "10.0.0.9" and not tried, "nur eine Adresse: ohne Pruefung")
check(pi_addr.probe("weg.test", **kw) is None, "unbekannter Name: None")
check(pi_addr.best("192.168.1.5", **kw) == "192.168.1.5", "IP bleibt IP")

pi_addr.forget()
up = {WLAN, KABEL}
clock = [100.0]
check(pi_addr.best("pi.test", clock=lambda: clock[0], **kw) == WLAN, "erster Aufruf: geprueft")
up.discard(WLAN)                                           # WLAN ausgeschaltet
tried.clear()
check(pi_addr.best("pi.test", clock=lambda: clock[0], **kw) == WLAN and not tried, "gemerkt: keine neue Pruefung")
clock[0] += pi_addr.REFRESH_S + 1
pi_addr.best("pi.test", clock=lambda: clock[0], **kw)       # stoesst die Pruefung im Hintergrund an
end = time.time() + 3
while time.time() < end and pi_addr._cache["pi.test"][0] != KABEL:
    time.sleep(0.02)
check(pi_addr.best("pi.test", clock=lambda: clock[0], **kw) == KABEL, "nach %d s: neue Adresse (Kabel)" % pi_addr.REFRESH_S)
check(pi_addr.best("weg.test", clock=lambda: clock[0], **kw) == "weg.test", "nichts bekannt: der Name selbst")

# Bruecke: send_udp nimmt die Adresse
import mixxx_bridge  # noqa: E402


class Sock:
    def __init__(self):
        self.to = []

    def sendto(self, data, addr):
        self.to.append(addr)


orig = pi_addr.best
pi_addr.best = lambda host, *a, **k: KABEL if host == "lightbutler.test" else host
s = Sock()
mixxx_bridge._pi_retry = 0.0
mixxx_bridge.send_udp(s, b"x", ("lightbutler.test", 9020))
check(s.to == [(KABEL, 9020)], "Bruecke schickt an die antwortende Adresse")
import apc_relay  # noqa: E402
import audio_send  # noqa: E402
r = apc_relay.ApcRelay("lightbutler.test", 9021, mido_mod=object(), sock=Sock(), log=lambda m: None)
check(r._target() == (KABEL, 9021), "APC am Mac ebenso")
a = audio_send.AudioSender("lightbutler.test", 9022, sd_mod=object(), sock=Sock(), log=lambda m: None)
a.resolve()
check(a.addr == (KABEL, 9022), "Ton vom Mac ebenso")
pi_addr.best = orig
for f in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    txt = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", f), encoding="utf-8").read()
    check("pi_addr.py" in txt, "%s kopiert pi_addr.py" % f)
finish("test_pi_adresse")
