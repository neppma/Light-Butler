"""
wled_discover.py - WLED-Geraete im Heimnetz finden (Seite Pixel-Matrix, Knopf Suchen, 21.11.2026). Ohne Zusatzpakete.

Drei Wege, zusammengefuehrt und jedes Geraet ueber /json/info bestaetigt:
1. mDNS: eine Frage nach "_wled._tcp.local" (WLED meldet sich so), Antwort direkt an uns (Unicast-Bit).
2. /json/nodes bekannter WLEDs (WLED kennt seine Nachbarn ueber die eigene Sync-Suche).
3. Durchlauf durch das eigene /24-Netz: GET /json/info mit kurzer Wartezeit, viele gleichzeitig.
Nur auf Knopfdruck, nur im eigenen Netz, nur lesend (HTTP GET). Antworten der Geraete gelten als ungepruefte Daten.
"""
import ipaddress
import json
import socket
import struct
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

MDNS = ("224.0.0.251", 5353)
SERVICE = "_wled._tcp.local"


def mdns_query(service=SERVICE):
    """DNS-Frage (PTR) mit Unicast-Bit: Antwort kommt direkt an unseren Port."""
    q = b"".join(bytes([len(p)]) + p.encode() for p in service.split(".")) + b"\0"
    return struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + q + struct.pack(">HH", 12, 0x8001)


def mdns_ips(timeout=1.5, sock=None):
    """Adressen, die auf die Frage nach WLED antworten."""
    own = sock is None
    if own:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    out = set()
    try:
        sock.settimeout(0.3)
        sock.sendto(mdns_query(), MDNS)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, addr = sock.recvfrom(9000)
            except socket.timeout:
                continue
            if b"_wled" in data.lower() or b"wled" in data.lower():
                out.add(addr[0])
    except OSError:
        pass
    finally:
        if own:
            sock.close()
    return out


def own_ip():
    """Eigene Adresse im Heimnetz (ohne Paket: UDP-connect waehlt nur die Route)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.254.254.254", 1))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def net_hosts(ip):
    """Alle Adressen des eigenen /24-Netzes (nur private Netze)."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return []
    if a.version != 4 or not a.is_private or a.is_loopback:
        return []
    net = ipaddress.ip_network(ip + "/24", strict=False)
    return [str(h) for h in net.hosts() if str(h) != ip]


def _get(url, timeout, opener):
    with opener(urllib.request.Request(url, headers={"User-Agent": "Light-Butler"}), timeout=timeout) as r:
        return json.loads(r.read(200_000).decode("utf-8", "replace"))


def _txt(v, n=60):
    return str(v or "").strip()[:n]


def _int(v):
    try:
        return max(0, min(100_000, int(v)))
    except (TypeError, ValueError):
        return 0


def info(ip, timeout=0.8, opener=urllib.request.urlopen):
    """{ip, name, ver, leds, w, h, matrix} wenn dort ein WLED antwortet, sonst None."""
    try:
        d = _get(f"http://{ip}/json/info", timeout, opener)
    except Exception:                                     # noqa: BLE001  keine Antwort, kein WLED
        return None
    if not isinstance(d, dict) or "ver" not in d or not isinstance(d.get("leds"), dict):
        return None
    leds = d["leds"]
    mx = leds.get("matrix") if isinstance(leds.get("matrix"), dict) else {}
    w, h = _int(mx.get("w")), _int(mx.get("h"))
    return {"ip": ip, "name": _txt(d.get("name")) or ip, "ver": _txt(d.get("ver"), 20), "leds": _int(leds.get("count")),
            "w": w, "h": h, "matrix": bool(w > 1 and h > 1)}


def nodes(ip, timeout=0.8, opener=urllib.request.urlopen):
    """Nachbarn, die dieses WLED kennt."""
    try:
        d = _get(f"http://{ip}/json/nodes", timeout, opener)
    except Exception:                                     # noqa: BLE001
        return set()
    out = set()
    for n in (d.get("nodes") or []) if isinstance(d, dict) else []:
        try:
            out.add(str(ipaddress.ip_address(str(n.get("ip")))))
        except (ValueError, AttributeError):
            pass
    return out


def discover(known=(), scan=True, opener=urllib.request.urlopen, mdns=mdns_ips, me=None, workers=64, timeout=0.8):
    """Alle WLEDs im Netz: Matrizen zuerst, dann nach Name."""
    cand = set(mdns()) | {k for k in known if k}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for s in ex.map(lambda ip: nodes(ip, timeout, opener), list(cand)):
            cand |= s
    me = own_ip() if me is None else me
    if scan:
        cand |= set(net_hosts(me))
    cand.discard(me)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        found = [x for x in ex.map(lambda ip: info(ip, timeout, opener), sorted(cand)) if x]
    return sorted(found, key=lambda x: (not x["matrix"], x["name"].casefold(), x["ip"]))
