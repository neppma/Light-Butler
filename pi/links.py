"""
links.py - eigene Links zu Geraeten im Heimnetz (Wunsch von Markus 24.11.2026): in den Einstellungen Name, Adresse und Port
eintragen, zum Beispiel "TV-Dashboard" auf 192.168.1.31:8080, dann oeffnet ein Knopf deren Seite in einem neuen Tab.

Gespeichert in links.json neben settings.json (deploy.sh fasst *.json am Pi nie an). Nur Adressen im eigenen Netz:
private IPv4-Adressen oder ein Name ohne Punkt bzw. mit .local/.lan/.home/.box (Router) (keine Internetadressen, das Panel
hat keine Anmeldung). Der Light-Butler ruft die Seiten selbst nie auf, er merkt sich nur den Link.
"""
import ipaddress
import json
import os
import re
from urllib.parse import urlsplit

MAX_LINKS = 20
NAME_MAX = 30
LOCAL_SUFFIX = (".local", ".lan", ".home", ".internal", ".box")   # .box: Namen, die ein Heimrouter vergibt
PATH_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/?#-]{0,300}$")
HOST_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,62})(\.[a-zA-Z0-9-]{1,63})*$")


def clean_host(host):
    """Adresse im eigenen Netz pruefen: private IPv4 oder lokaler Name. Gibt sie zurueck oder wirft ValueError."""
    h = str(host or "").strip().lower()
    h = re.sub(r"^https?://", "", h).split("/")[0].split(":")[0]
    if not h:
        raise ValueError("Adresse fehlt")
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        if not HOST_RE.match(h) or len(h) > 120:
            raise ValueError("Adresse ungueltig") from None
        if "." in h and not h.endswith(LOCAL_SUFFIX):
            raise ValueError("Nur Geraete im eigenen Netz (zum Beispiel 192.168.1.31 oder name.local)") from None
        return h
    if ip.version != 4 or not (ip.is_private or ip.is_loopback) or ip.is_unspecified:
        raise ValueError("Nur Adressen im eigenen Netz (zum Beispiel 192.168.1.31)")
    return h


def clean_port(port):
    if port in (None, ""):
        return 80
    p = int(port)
    if not 1 <= p <= 65535:
        raise ValueError("Port 1 bis 65535")
    return p


class Links:
    def __init__(self, path=None):
        self.path = path
        self.items = []
        self.load()

    def load(self):
        if not self.path or not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            items = []
            for x in data.get("links", []) if isinstance(data, dict) else []:
                try:
                    items.append(self._clean(x))
                except (ValueError, TypeError, AttributeError):
                    continue
            self.items = items[:MAX_LINKS]
        except (OSError, ValueError):
            self.items = []

    def save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"links": self.items}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    @staticmethod
    def _clean(x):
        """Name, Adresse, Port, Pfad. Im Adressfeld darf auch eine ganze Adresse stehen (http://localhost:8123/party.html):
        Port und Pfad kommen dann daraus, ein eigener Port im Portfeld geht vor."""
        name = str(x.get("name") or "").strip()[:NAME_MAX]
        raw = str(x.get("host") or "").strip()
        sp = urlsplit(raw if "://" in raw else "http://" + raw)
        if sp.scheme not in ("http", "https"):
            raise ValueError("Nur http oder https")
        host = clean_host(sp.hostname or "")
        port = clean_port(x.get("port") if str(x.get("port") or "").strip() else (sp.port or (443 if sp.scheme == "https" else 80)))
        path = str(x.get("path") or (sp.path + ("?" + sp.query if sp.query else "")) or "/").strip() or "/"
        if not PATH_RE.match(path):
            raise ValueError("Pfad ungueltig")
        if not name:
            name = host if port == 80 else f"{host}:{port}"
        return {"name": name, "host": host, "port": port, "path": path, "https": sp.scheme == "https"}

    @staticmethod
    def url(item):
        tls = bool(item.get("https"))
        default = 443 if tls else 80
        return (("https" if tls else "http") + f"://{item['host']}" + ("" if item["port"] == default else f":{item['port']}")
                + (item.get("path") or "/"))

    def public(self):
        return [dict(x, url=self.url(x)) for x in self.items]

    def add(self, x):
        if len(self.items) >= MAX_LINKS:
            raise ValueError(f"Hoechstens {MAX_LINKS} Links")
        item = self._clean(x if isinstance(x, dict) else {})
        self.items.append(item)
        self.save()
        return item

    def remove(self, i):
        i = int(i)
        if 0 <= i < len(self.items):
            del self.items[i]
            self.save()
