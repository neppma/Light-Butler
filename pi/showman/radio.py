"""
radio.py - Internetradio (Seite /musik/radio, Wunsch von Markus, 21.11.2026).

Am Licht-Rechner: Senderliste aus radio-browser.info (freie Datenbank, ohne Schluessel), Programmplaetze 1-12, Favoriten,
Logos, der gewuenschte Sender. Abspielen tut der Light-Butler Helfer am Musik-Rechner (mac/mixxx_bridge/radio_play.py):
er fragt jede Sekunde /api/sm/radio_want, spielt den Sender ueber ffmpeg auf seinen Lautsprechern und schickt denselben Ton
per UDP 9022 an den Licht-Rechner (Eingang "Musik-Rechner (Netzwerk)"). Er meldet Zustand und Titelfeld (ICY StreamTitle)
mit dem Befehl radio_report zurueck.

Abspielen am Geraet (Wunsch 22.11.2026, Fernseher mit Line-In am Licht-Rechner): radio_play mit here und dev (Kennung des
Browsers). Dann spielt der Browser selbst (<audio>), der Helfer bekommt play False und bleibt still. Der Browser meldet alle
2 s radio_here (Zustand); das Titelfeld liest der Licht-Rechner selbst mit (IcyTitle: nur die Titel-Bloecke, der Ton wird
verworfen). Mit Haken "line" schaltet der ShowManager den Eingang solange auf Line-In und danach zurueck.

Titelfeld "Interpret - Titel": einmal je Lied fragt der Licht-Rechner iTunes (nur Interpret und Titel) nach Genre und Cover.
Genre -> Licht-Stil (Einstellung radio_style), Cover und Senderlogo -> Pixel-Matrix. Anderer Text (Sendung, Nachrichten,
Werbung) ist nur Info. Verkehrsfunk und Radiotext (RDS, DAB+) kommen ueber das Internet nicht mit.

Ablage:  shows/_radio.json               Plaetze, Favoriten, zuletzt gehoerter Sender, Lautstaerke, Land
         shows/_radio_logos/<uuid>.img   Senderlogos (nur Bilder, nur aus dem Internet, keine Adressen im Heimnetz)
         shows/_radio_covers/<sha1>.jpg  Cover zu Interpret und Titel (iTunes)
Ins Internet gehen nur Land, Genre, Suchtext, Senderkennung und bei Titeln Interpret und Titel.
"""
import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.parse
import urllib.request

SERVERS = ("de1.api.radio-browser.info", "de2.api.radio-browser.info")
UA = "Light-Butler/1.0"
SLOTS = 12
FILE = "_radio.json"
LOGOS = "_radio_logos"
COVERS = "_radio_covers"
MAX_IMG = 600_000
CACHE_S = 600
REPORT_S = 6.0                       # so lange gilt eine Meldung des Helfers
TITLE_GAP_S = 3.0                    # iTunes hoechstens alle 3 s
UUID_RE = re.compile(r"^[0-9a-f-]{36}$")
CC_RE = re.compile(r"^[A-Z]{2}$")
ITUNES_IMG = ("is1-ssl.mzstatic.com", "is2-ssl.mzstatic.com", "is3-ssl.mzstatic.com", "is4-ssl.mzstatic.com", "is5-ssl.mzstatic.com")
SPLIT_RE = re.compile(r"\s+[-–—]\s+")
FEAT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring|vs\.?|x|&|und|and|,)\s+.*$", re.I)
NOISE_RE = re.compile(r"^(?:werbung|news|nachrichten|verkehr|wetter|jingle|ad|advert|commercial)\b", re.I)


def clean(s, n=160):
    return re.sub(r"[\x00-\x1f]", " ", str(s or "")).strip()[:n]


def is_image(b):
    return (b[:3] == b"\xff\xd8\xff" or b[:8] == b"\x89PNG\r\n\x1a\n" or b[:6] in (b"GIF87a", b"GIF89a")
            or (b[:4] == b"RIFF" and b[8:12] == b"WEBP") or b[:4] == b"\x00\x00\x01\x00")


def public_host(url):
    """Nur http/https zu Adressen im Internet (keine Geraete im Heimnetz, kein localhost)."""
    try:
        u = urllib.parse.urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        for info in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP):
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False
        return True
    except (OSError, ValueError):
        return False


def station(x):
    """Sender aus radio-browser (oder aus der eigenen Datei) auf die gepruefte Kurzform bringen, sonst None."""
    if not isinstance(x, dict):
        return None
    uuid = str(x.get("uuid") or x.get("stationuuid") or "").lower()
    url = str(x.get("url_resolved") or x.get("url") or "").strip()
    if not UUID_RE.match(uuid) or not re.match(r"^https?://", url, re.I) or len(url) > 600:
        return None
    logo = str(x.get("favicon") or x.get("logo") or "").strip()
    try:
        br = int(x.get("bitrate") or 0)
    except (TypeError, ValueError):
        br = 0
    return {"uuid": uuid, "name": clean(x.get("name"), 120) or "?", "url": url,
            "logo": logo if re.match(r"^https?://", logo, re.I) and len(logo) <= 600 else "",
            "country": clean(x.get("country"), 60), "cc": clean(x.get("countrycode") or x.get("cc"), 2).upper(),
            "tags": clean(x.get("tags"), 120), "codec": clean(x.get("codec"), 12), "kbps": max(0, min(br, 9999)),
            "hls": 1 if str(x.get("hls") or "0") in ("1", "True", "true") else 0,
            "votes": int(x.get("votes") or 0) if str(x.get("votes") or "0").isdigit() else 0}


def icy_title(meta):
    """StreamTitle aus einem ICY-Metadatenblock (Bytes) oder None."""
    m = re.search(rb"StreamTitle='(.*?)';", meta, re.S)
    if not m:
        return None
    b = m.group(1)
    try:
        return clean(b.decode("utf-8"), 200)
    except UnicodeDecodeError:
        return clean(b.decode("latin-1"), 200)


class IcyTitle:
    """Liest beim Abspielen am Geraet das Titelfeld des Senders mit (eigener Faden, Ton wird verworfen)."""

    def __init__(self, url, on_title, keep, opener=None, check=public_host):
        self.url, self.on_title, self.keep = url, on_title, keep
        self.opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
        self.check = check
        self.error = ""

    def run(self):
        if not self.check(self.url):
            self.error = "Adresse nicht im Internet"
            return
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": UA, "Icy-MetaData": "1"})
            with self.opener(req, 15) as r:
                try:
                    n = int(r.headers.get("icy-metaint") or 0)
                except (TypeError, ValueError, AttributeError):
                    n = 0
                if not 0 < n <= 1_000_000:
                    self.error = "Sender schickt kein Titelfeld"
                    return
                while self.keep():
                    left = n
                    while left > 0:
                        b = r.read(min(left, 65536))
                        if not b:
                            return
                        left -= len(b)
                    ln = r.read(1)
                    if not ln:
                        return
                    if ln[0]:
                        t = icy_title(r.read(ln[0] * 16))
                        if t is not None:
                            self.on_title(t)
        except (OSError, ValueError) as e:
            self.error = str(e)[:120]


def split_title(t):
    """"Interpret - Titel" -> (Interpret, Titel); sonst (None, None): Sendung, Nachrichten, Werbung, Sendername."""
    t = clean(t, 200)
    if not t or NOISE_RE.match(t):
        return None, None
    p = SPLIT_RE.split(t, maxsplit=1)
    if len(p) != 2 or not p[0].strip() or not p[1].strip():
        return None, None
    return p[0].strip()[:120], p[1].strip()[:160]


class Radio:
    def __init__(self, base, opener=None, now=time.time):
        self.base, self.now = base, now
        self.opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
        self.path = os.path.join(base, FILE)
        self.lock = threading.Lock()
        self.cache = {}
        self.data = self._load()
        self.want = {"seq": 0, "play": False, "st": self.data.get("last"), "vol": self.data.get("vol", 0.8), "here": False, "dev": ""}
        self.rep, self.rep_t = {}, 0.0
        self.here_rep, self.here_t = {}, 0.0          # Meldung des Browsers, der selbst spielt
        self.icy, self.icy_title, self.icy_url = None, "", ""
        self.icy_opener, self.icy_check = None, public_host     # Tests setzen beides
        self.song_info = {}                       # Titelfeld -> {genre, cover}
        self.title_t = 0.0
        self.server = 0

    # ---- Ablage --------------------------------------------------------------------------------
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        slots = {}
        for k, v in (d.get("slots") or {}).items():
            s = station(v)
            if s and str(k).isdigit() and 1 <= int(k) <= SLOTS:
                slots[str(int(k))] = s
        favs = {}
        for v in (d.get("favs") or {}).values():
            s = station(v)
            if s:
                favs[s["uuid"]] = s
        vol = d.get("vol", 0.8)
        cc = str(d.get("cc") or "")
        return {"slots": slots, "favs": favs, "last": station(d.get("last")),
                "vol": max(0.0, min(1.0, float(vol))) if isinstance(vol, (int, float)) else 0.8, "cc": cc if CC_RE.match(cc) else ""}

    def _save(self):
        os.makedirs(self.base, exist_ok=True)
        with open(self.path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
        os.replace(self.path + ".tmp", self.path)

    # ---- radio-browser ---------------------------------------------------------------------------
    def _get(self, path, params=None):
        q = path + ("?" + urllib.parse.urlencode(params) if params else "")
        hit = self.cache.get(q)
        if hit and self.now() - hit[0] < CACHE_S:
            return hit[1]
        err = None
        for i in range(len(SERVERS)):
            host = SERVERS[(self.server + i) % len(SERVERS)]
            try:
                with self.opener(urllib.request.Request("https://" + host + q, headers={"User-Agent": UA}), 10) as r:
                    data = json.loads(r.read(4_000_000).decode("utf-8"))
                self.server = (self.server + i) % len(SERVERS)
                self.cache[q] = (self.now(), data)
                if len(self.cache) > 200:
                    self.cache.pop(next(iter(self.cache)))
                return data
            except (OSError, ValueError) as e:
                err = e
        raise ValueError("Senderliste nicht erreichbar (%s)" % str(err)[:80])

    def countries(self):
        d = self._get("/json/countries")
        out = [{"cc": str(x.get("iso_3166_1") or "").upper(), "name": clean(x.get("name"), 60), "n": int(x.get("stationcount") or 0)}
               for x in d if isinstance(x, dict)]
        return sorted([x for x in out if CC_RE.match(x["cc"]) and x["n"] > 0], key=lambda x: x["name"])

    def tags(self, cc=""):
        p = {"order": "stationcount", "reverse": "true", "limit": "80", "hidebroken": "true"}
        d = self._get("/json/tags", p)
        top = [clean(x.get("name"), 40) for x in d if isinstance(x, dict) and int(x.get("stationcount") or 0) >= 50][:80]
        return sorted(set(t for t in top if t), key=str.casefold)          # alphabetisch (Wunsch 21.11.2026)

    def search(self, cc="", tag="", name="", limit=120):
        p = {"order": "clickcount", "reverse": "true", "hidebroken": "true", "limit": str(max(1, min(int(limit), 300)))}
        cc = str(cc or "").upper()
        if CC_RE.match(cc):
            p["countrycode"] = cc
        if tag:
            p["tag"] = clean(tag, 40)
        if name:
            p["name"] = clean(name, 60)
        out = [station(x) for x in self._get("/json/stations/search", p)]
        if CC_RE.match(cc) and cc != self.data.get("cc"):
            with self.lock:
                self.data["cc"] = cc
                self._save()
        return [s for s in out if s]

    def click(self, uuid):
        """radio-browser zaehlt, welche Sender gehoert werden (wie es die Datenbank wuenscht); Fehler sind egal."""
        try:
            self._get("/json/url/" + uuid)
        except ValueError:
            pass

    # ---- Plaetze, Favoriten, Abspielen ----------------------------------------------------------------
    def slot_set(self, n, st):
        s = station(st)
        if s is None or not str(n).isdigit() or not 1 <= int(n) <= SLOTS:
            raise ValueError("Platz oder Sender ungueltig")
        with self.lock:
            self.data["slots"][str(int(n))] = s
            self._save()

    def slot_clear(self, n):
        with self.lock:
            self.data["slots"].pop(str(n), None)
            self._save()

    def fav(self, st, on):
        s = station(st)
        if s is None:
            raise ValueError("Sender ungueltig")
        with self.lock:
            if on:
                self.data["favs"][s["uuid"]] = s
            else:
                self.data["favs"].pop(s["uuid"], None)
            self._save()

    def play(self, st=None, slot=None, here=False, dev=""):
        if slot is not None:
            s = self.data["slots"].get(str(slot))
            if s is None:
                raise ValueError("Platz %s ist leer" % slot)
        else:
            s = station(st) if st is not None else self.data.get("last")
        if s is None:
            raise ValueError("Kein Sender gewaehlt")
        with self.lock:
            dev = re.sub(r"[^A-Za-z0-9_-]", "", str(dev or ""))[:40] if here else ""
            self.want = dict(self.want, seq=self.want["seq"] + 1, play=True, st=s, here=bool(here and dev), dev=dev)
            self.here_rep, self.here_t, self.icy_title = {}, 0.0, ""
            self.data["last"] = s
            self._save()
        threading.Thread(target=self.click, args=(s["uuid"],), daemon=True).start()

    def stop(self):
        with self.lock:
            self.want = dict(self.want, seq=self.want["seq"] + 1, play=False)

    def volume(self, v):
        v = max(0.0, min(1.0, float(v)))
        with self.lock:
            self.want = dict(self.want, vol=v)
            self.data["vol"] = v
            self._save()

    def want_info(self):
        """Fuer den Helfer: was spielen (nur Adresse, Name, Kennung, Lautstaerke). Spielt ein Browser selbst: nichts."""
        w, s = self.want, self.want.get("st") or {}
        return {"seq": w["seq"], "play": bool(w["play"] and s and not w.get("here")), "url": s.get("url", ""), "uuid": s.get("uuid", ""),
                "name": s.get("name", ""), "hls": s.get("hls", 0), "vol": w["vol"]}

    # ---- Meldung vom Helfer, Titelfeld ------------------------------------------------------------
    def report(self, d):
        """Helfer meldet: state (verbinde, spielt, fehler, aus), title (Titelfeld), err, seq. Ungepruefte Daten."""
        st = str(d.get("state") or "")
        self.rep = {"state": st if st in ("verbinde", "spielt", "fehler", "aus") else "",
                    "title": clean(d.get("title"), 200), "err": clean(d.get("err"), 200),
                    "seq": int(d.get("seq") or 0) if str(d.get("seq") or "0").isdigit() else 0,
                    "codec": clean(d.get("codec"), 20), "kbps": int(d.get("kbps") or 0) if str(d.get("kbps") or "0").isdigit() else 0}
        self.rep_t = self.now()
        self._title_seen(self.rep["title"])
        return {"ok": True}

    def _title_seen(self, title):
        a, t = split_title(title)
        if a and (a, t) not in self.song_info and self.now() - self.title_t >= TITLE_GAP_S:
            self.title_t = self.now()
            self.song_info[(a, t)] = {}
            threading.Thread(target=self._lookup, args=(a, t), daemon=True).start()

    # ---- Abspielen am Geraet (Browser) -------------------------------------------------------------
    def here_report(self, d):
        """Browser, der selbst spielt, meldet: state (verbinde, spielt, fehler, aus), dev, err. Ungepruefte Daten."""
        dev = re.sub(r"[^A-Za-z0-9_-]", "", str(d.get("dev") or ""))[:40]
        if not self.want.get("here") or dev != self.want.get("dev"):
            return {"ok": False, "other": True}           # anderer Browser oder nicht mehr gewuenscht: aufhoeren
        st = str(d.get("state") or "")
        self.here_rep = {"state": st if st in ("verbinde", "spielt", "fehler", "aus") else "", "err": clean(d.get("err"), 200),
                         "line": bool(d.get("line"))}
        self.here_t = self.now()
        if self.here_rep["state"] == "spielt":
            self._icy_start()
        return {"ok": True}

    def here_alive(self):
        return bool(self.want.get("here")) and self.now() - self.here_t < REPORT_S

    def here_line(self):
        """True, solange ein Browser hier spielt und den Eingang Line-In will."""
        return self.here_alive() and self.want["play"] and self.here_rep.get("state") in ("verbinde", "spielt") and self.here_rep.get("line")

    def _icy_keep(self, url):
        return self.here_alive() and self.want["play"] and (self.want.get("st") or {}).get("url") == url

    def _icy_on(self, title):
        self.icy_title = title
        self._title_seen(title)

    def _icy_start(self):
        url = (self.want.get("st") or {}).get("url", "")
        if not url or (self.icy is not None and self.icy.is_alive() and self.icy_url == url):
            return
        self.icy_url, self.icy_title = url, ""
        r = IcyTitle(url, self._icy_on, lambda: self._icy_keep(url), opener=self.icy_opener, check=self.icy_check)
        self.icy = threading.Thread(target=r.run, daemon=True)
        self.icy.start()

    def _rep(self):
        """Zustand und Titelfeld: vom Browser plus mitgelesenem Titel, sonst vom Helfer."""
        if self.want.get("here"):
            return dict(self.here_rep, title=self.icy_title) if self.here_alive() else {}
        return self.rep if self.now() - self.rep_t < REPORT_S else {}

    def alive(self):
        return self.here_alive() if self.want.get("here") else self.now() - self.rep_t < REPORT_S

    def playing(self):
        return self.alive() and self._rep().get("state") == "spielt" and self.want["play"]

    def song(self):
        """Laufendes Lied aus dem Titelfeld: {artist, title, genre, station} oder None (Sendung, Werbung, nichts)."""
        if not self.playing():
            return None
        a, t = split_title(self._rep().get("title"))
        if not a:
            return None
        info = self.song_info.get((a, t)) or {}
        return {"artist": a, "title": t, "genre": info.get("genre", ""), "station": (self.want.get("st") or {}).get("name", ""),
                "uuid": (self.want.get("st") or {}).get("uuid", ""), "done": bool(info.get("done"))}

    def panel(self):
        """Hauptpanel: was das Internetradio gerade spielt (nur solange es spielt), sonst None."""
        if not self.playing():
            return None
        st = self.want.get("st") or {}
        rp = self._rep()
        a, t = split_title(rp.get("title"))
        info = self.song_info.get((a, t)) or {} if a else {}
        return {"st": st.get("name", ""), "uuid": st.get("uuid", ""), "logo": bool(st.get("logo")), "artist": a or "", "title": t or "",
                "info": "" if a else rp.get("title", ""), "genre": info.get("genre", ""), "cover": bool(info.get("cover"))}

    def _lookup(self, artist, title):
        """iTunes: Genre und Cover zu Interpret und Titel (nur diese beiden gehen ins Internet)."""
        info = {"genre": "", "cover": "", "done": True}
        try:
            q = urllib.parse.urlencode({"term": f"{artist} {title}", "media": "music", "entity": "song", "limit": "3"})
            with self.opener(urllib.request.Request("https://itunes.apple.com/search?" + q, headers={"User-Agent": UA}), 10) as r:
                res = json.loads(r.read(1_000_000).decode("utf-8")).get("results") or []
            al = FEAT_RE.sub("", artist).strip().lower()           # "Felix Jaehn feat. Ray Dalton" -> "felix jaehn"
            best = next((x for x in res if al and al in str(x.get("artistName") or "").lower()), None)
            if best:
                info["genre"] = clean(best.get("primaryGenreName"), 40)
                art = str(best.get("artworkUrl100") or "").replace("100x100bb", "300x300bb")
                u = urllib.parse.urlsplit(art)
                if u.scheme == "https" and u.hostname in ITUNES_IMG:
                    with self.opener(urllib.request.Request(art, headers={"User-Agent": UA}), 10) as r:
                        img = r.read(MAX_IMG + 1)
                    if len(img) <= MAX_IMG and is_image(img):
                        os.makedirs(os.path.join(self.base, COVERS), exist_ok=True)
                        p = os.path.join(self.base, COVERS, hashlib.sha1(f"{artist}|{title}".encode()).hexdigest() + ".jpg")
                        with open(p, "wb") as f:
                            f.write(img)
                        info["cover"] = p
        except (OSError, ValueError, AttributeError):
            pass
        self.song_info[(artist, title)] = info
        if len(self.song_info) > 500:
            self.song_info.pop(next(iter(self.song_info)))

    def cover(self, artist, title):
        p = (self.song_info.get((artist, title)) or {}).get("cover")
        if p and os.path.isfile(p):
            with open(p, "rb") as f:
                return f.read()
        return None

    # ---- Logos ---------------------------------------------------------------------------------------
    def _known(self, uuid):
        for s in list(self.data["slots"].values()) + list(self.data["favs"].values()) + [self.data.get("last") or {}, self.want.get("st") or {}]:
            if s.get("uuid") == uuid:
                return s
        for _, (_, d) in list(self.cache.items()):
            if isinstance(d, list):
                for x in d:
                    if isinstance(x, dict) and str(x.get("stationuuid") or "") == uuid:
                        return station(x)
        return None

    def logo(self, uuid):
        """Senderlogo als Bild-Bytes oder None. Einmal geholt, dann aus der Ablage."""
        uuid = str(uuid or "").lower()
        if not UUID_RE.match(uuid):
            return None
        p = os.path.join(self.base, LOGOS, uuid + ".img")
        if os.path.isfile(p):
            with open(p, "rb") as f:
                b = f.read()
            return b or None
        s = self._known(uuid)
        if not s or not s.get("logo") or not public_host(s["logo"]):
            return None
        b = b""
        try:
            with self.opener(urllib.request.Request(s["logo"], headers={"User-Agent": UA}), 8) as r:
                b = r.read(MAX_IMG + 1)
            if len(b) > MAX_IMG or not is_image(b):
                b = b""
        except (OSError, ValueError):
            b = b""
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b)                                # leer = kein Logo (nicht jedes Mal neu fragen)
        return b or None

    # ---- Seite ---------------------------------------------------------------------------------------
    def state(self):
        st = self.want.get("st") or {}
        rp = self._rep()
        a, t = split_title(rp.get("title"))
        info = self.song_info.get((a, t)) or {}
        return {"slots": self.data["slots"], "favs": list(self.data["favs"].values()), "cc": self.data.get("cc", ""),
                "want": {"play": bool(self.want["play"]), "st": st or None, "vol": self.want["vol"],
                         "here": bool(self.want.get("here")), "dev": self.want.get("dev", "")},
                "helper": self.now() - self.rep_t < REPORT_S, "here_alive": self.here_alive(), "rep": rp,
                "song": {"artist": a, "title": t, "genre": info.get("genre", ""), "cover": bool(info.get("cover")),
                         "done": bool(info.get("done"))} if a else None}
