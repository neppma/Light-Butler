#!/usr/bin/env python3
"""
pi_addr.py - erreichbare Adresse des Licht-Rechners (Fehlerbericht 25.11.2026).

Hat der Pi zwei Adressen (Kabel und WLAN), liefert der Router fuer den Namen des Pi beide, die WLAN-Adresse oft
zuerst. Schaltet man das WLAN des Pi aus (Knopf im Panel, wegen Bluetooth), schickten Helfer und Mixxx-App ihre
UDP-Pakete weiter an die tote WLAN-Adresse: im Panel "Musik-Rechner nicht erreichbar", Liedliste, APC und Ton weg.

best(host) liefert die erste Adresse, unter der das Panel (TCP 8080) antwortet. Gemerkt und alle REFRESH_S Sekunden im
Hintergrund neu geprueft; nur der allererste Aufruf wartet (kurz). Eine einzige Adresse oder eine IP: ohne Pruefung.
"""
import socket
import threading
import time

REFRESH_S = 30.0
PROBE_S = 0.6
WEB_PORT = 8080

_cache = {}                  # host -> (ip, Zeitpunkt)
_busy = set()
_lock = threading.Lock()


def _ips(host, resolver):
    try:
        infos = resolver(host, None, socket.AF_INET, socket.SOCK_DGRAM)
    except (OSError, UnicodeError):
        return []
    out = []
    for i in infos:
        ip = i[4][0]
        if ip not in out:
            out.append(ip)
    return out


def _reachable(ip, port, connector):
    try:
        connector((ip, port), PROBE_S).close()
        return True
    except OSError:
        return False


def probe(host, port=WEB_PORT, resolver=socket.getaddrinfo, connector=socket.create_connection):
    """Erste Adresse, die antwortet; antwortet keine, die erste (wie bisher); unbekannt: None."""
    ips = _ips(host, resolver)
    if len(ips) <= 1:
        return ips[0] if ips else None
    for ip in ips:
        if _reachable(ip, port, connector):
            return ip
    return ips[0]


def _is_ip(host):
    try:
        socket.inet_aton(host)
        return host.count(".") == 3
    except OSError:
        return False


def best(host, port=WEB_PORT, clock=time.monotonic, **kw):
    """Adresse fuer UDP an den Pi: IP oder (wenn nichts bekannt) der Name selbst."""
    if not host or _is_ip(host):
        return host
    now = clock()
    with _lock:
        e = _cache.get(host)
    if e is None:
        ip = probe(host, port, **kw)
        with _lock:
            _cache[host] = (ip, now)
        return ip or host
    if now - e[1] > REFRESH_S:
        with _lock:
            start = host not in _busy
            _busy.add(host)
            _cache[host] = (e[0], now)              # nicht gleich wieder anstossen

        def work():
            try:
                ip = probe(host, port, **kw)
                if ip:
                    with _lock:
                        _cache[host] = (ip, clock())
            finally:
                with _lock:
                    _busy.discard(host)
        if start:
            threading.Thread(target=work, daemon=True).start()
    return e[0] or host


def forget():
    with _lock:
        _cache.clear()
