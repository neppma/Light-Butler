"""WLED-Suche fuer die Pixel-Matrix (21.11.2026): mDNS, Nachbarn, Netz-Durchlauf, alles ueber /json/info bestaetigt.
Ohne Netzwerk: Antworten kommen aus einem Ersatz."""
import io
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, check, finish  # noqa: E402

import wled_discover as wd                       # noqa: E402

q = wd.mdns_query()
check(q[:12] == struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) and b"\x05_wled\x04_tcp\x05local\x00" in q and q[-4:] == b"\x00\x0c\x80\x01",
      "mDNS-Frage: PTR _wled._tcp.local mit Unicast-Bit")


class Sock:
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def settimeout(self, t):
        pass

    def sendto(self, d, a):
        self.sent.append(a)

    def recvfrom(self, n):
        if self.replies:
            return self.replies.pop(0)
        raise wd.socket.timeout()


s = Sock([(b"..._wled..._tcp", ("192.168.0.52", 5353)), (b"_airplay", ("192.168.0.9", 5353))])
check(wd.mdns_ips(0.2, s) == {"192.168.0.52"} and s.sent == [wd.MDNS], "mDNS: nur Antworten mit WLED")

check(len(wd.net_hosts("192.168.0.40")) == 253 and "192.168.0.40" not in wd.net_hosts("192.168.0.40"), "Netz /24 ohne eigene Adresse")
check(wd.net_hosts("8.8.8.8") == [] and wd.net_hosts("127.0.0.1") == [] and wd.net_hosts("x") == [], "nur private Netze")

DEV = {
    "192.168.0.52": {"/json/info": {"ver": "0.15.0", "name": "Matrix-Test", "leds": {"count": 1024, "matrix": {"w": 32, "h": 32}}},
                      "/json/nodes": {"nodes": [{"ip": "192.168.0.31", "name": "Bar"}, {"ip": "kaputt"}]}},
    "192.168.0.31": {"/json/info": {"ver": "0.14.4", "name": "Bar <b>", "leds": {"count": 60}}},
    "192.168.0.33": {"/json/info": {"ver": "0.14.4", "name": "Streifen", "leds": {"count": 300}}},
    "192.168.0.50": {"/json/info": {"hallo": "kein WLED"}},
}
asked = []


def opener(req, timeout):
    url = req.full_url
    asked.append(url)
    host, path = url[7:].split("/", 1)
    d = DEV.get(host, {}).get("/" + path)
    if d is None:
        raise OSError("keine Antwort")
    return io.BytesIO(json.dumps(d).encode())


i = wd.info("192.168.0.52", opener=opener)
check(i == {"ip": "192.168.0.52", "name": "Matrix-Test", "ver": "0.15.0", "leds": 1024, "w": 32, "h": 32, "matrix": True},
      "info: Name, Version, Groesse")
check(wd.info("192.168.0.50", opener=opener) is None and wd.info("192.168.0.99", opener=opener) is None, "kein WLED: nichts")
check(wd.nodes("192.168.0.52", opener=opener) == {"192.168.0.31"}, "Nachbarn: nur gueltige Adressen")

asked.clear()
f = wd.discover(known=["192.168.0.33"], scan=False, opener=opener, mdns=lambda: {"192.168.0.52"}, me="192.168.0.40")
check([x["ip"] for x in f] == ["192.168.0.52", "192.168.0.31", "192.168.0.33"], "ohne Durchlauf: mDNS, bekannte, Nachbarn; Matrix zuerst")
check(not any("192.168.0.7" in u for u in asked), "ohne Durchlauf: keine fremden Adressen gefragt")
f2 = wd.discover(scan=True, opener=opener, mdns=lambda: set(), me="192.168.0.40", workers=32)
check({x["ip"] for x in f2} == {"192.168.0.52", "192.168.0.31", "192.168.0.33"}, "mit Durchlauf: alle drei auch ohne mDNS")
check(f2[0]["matrix"] and f2[1]["name"] == "Bar <b>", "Sortierung: Matrix, dann nach Name")
check(all(len(x["name"]) <= 60 for x in f2), "Namen gekuerzt (ungepruefte Daten)")

# Seite und Abfrage
js = open(os.path.join(ROOT, "pi", "static", "sm", "matrix.js"), encoding="utf-8").read()
html = open(os.path.join(ROOT, "pi", "static", "sm", "matrix.html"), encoding="utf-8").read()
check("/api/matrix_scan" in js and 'id="scan"' in html and 'id="found"' in html, "Seite: Knopf und Auswahl")
check("textContent = x.name" in js and "innerHTML = x" not in js, "Namen der Geraete nur als Text")
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check('"/api/matrix_scan"' in wp, "Abfrage im Panel")
finish("test_wled_suche")
