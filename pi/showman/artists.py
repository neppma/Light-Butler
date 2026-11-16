"""
artists.py - Interpreten mit Bild (Wunsch von Markus, 13.11.2026). Seite /musik/interpreten.

Die Interpreten kommen aus der Bibliothek (Mixxx und Musikordner, wie die Musik-Datenbank). "Falco feat. X" zaehlt bei Falco;
"Simon & Garfunkel" oder "Seiler und Speer" bleiben, wie sie sind (Bands). Je Interpret ein Bild am Pi:
    shows/_interpreten/<schluessel>.jpg       Schluessel = vereinfachter Name (key), z. B. "falco", "seiler-und-speer"
    shows/_interpreten.json                   Schluessel -> {name, src (deezer|audiodb|eigen), t} oder {none: Zeit}
Geholt wird auf Knopfdruck je Interpret oder vorab fuer alle (Karte auf der Seite Statistik), eine Anfrage nach der anderen.
Quellen ohne Anmeldung: Deezer (Bild 500 Pixel; bei gleichem Namen gewinnt, wer eines der eigenen Lieder im Programm hat,
sonst der mit deutlich den meisten Fans), sonst TheAudioDB. Ins Internet gehen nur Namen von Interpreten, keine Musik, keine
Pfade. Eigenes Bild: der Browser schneidet es quadratisch zu und schickt ein JPEG. Die Mixxx-Bruecke sichert die Bilder auf
den Stick (musik-backup/Light-Butler-Interpreten). Aufs Licht wirkt das nicht.
"""
import json
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

DIR = "_interpreten"
INDEX = "_interpreten.json"
STATE = "_interpreten_vorab.json"
INFO_DIR = "_interpreten_info"                       # Lebenslauf und Alben je Interpret (13.11.2026), <schluessel>.json
INFO_KEEP_S = 90 * 86400.0                           # nach 90 Tagen neu holen
FILE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}\.jpg$")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
MAX_BYTES = 3 * 1024 * 1024
IMG_HOSTS = ("dzcdn.net", "theaudiodb.com")         # Bilder nur von dort (https)
DEEZER = "https://api.deezer.com"
AUDIODB = "https://www.theaudiodb.com/api/v1/json/123"
UA = "Light-Butler/1.0"
GAP_S = 3.0                                          # Vorab-Lauf: ein Interpret alle 3 Sekunden
WAIT_S = 60.0                                        # kein Internet: in einer Minute wieder
NONE_RETRY_S = 30 * 86400.0                          # nichts gefunden: erst nach 30 Tagen wieder fragen
FEAT_RE = re.compile(r"\s*;.*$|\s+(?:feat\.?|ft\.?|featuring|vs\.?|versus)\s+.*$|\s*\((?:feat\.?|ft\.?|featuring)\s.*\)\s*$", re.I)


def main_name(artist):
    """Hauptname: "Falco feat. X" -> "Falco", "John Williams; Skywalker Symphony Orchestra" -> "John Williams" (; trennt mehrere
    Interpreten im Tag). Bands mit & oder "und" bleiben ganz."""
    a = unicodedata.normalize("NFC", str(artist or "")).strip()
    a = FEAT_RE.sub("", a).strip(" -,")
    return a


# "Rainhard Fendrich & Vienna Symphony Orchestra" (13.11.2026): & und, and, with, Beistrich trennen nur, wenn der erste Name in der
# Sammlung auch allein vorkommt oder danach ein Orchester, Chor, Ensemble kommt; "Simon & Garfunkel", "Earth, Wind & Fire" bleiben.
JOIN_RE = re.compile(r"\s+(?:&|\+|und|and|with|mit|x)\s+|\s*,\s+", re.I)
ART_RE = re.compile(r"(?:the|die|der|das|den|dem|los|las|les|la|le|il|i|a|an|ein|eine|his|her|their|seine|seinen|seinem|ihre|ihren|ihrem)\s", re.I)   # Begleitband: "& The Wailers", "and His Comets"
GROUP_RE = re.compile(r"(?:friends|freunde|family|familie|kinder|co\.?|sons|söhne|singers|sänger)", re.I)   # "& Friends": nur der Erste
MESSY_RE = re.compile(r"\s-\s|/|[()\[\]]|\b(?:meets?|pres\.?|presents|by|vs\.?)\s", re.I)
DUET_RE = re.compile(r"\s+(?:duet|duett)$", re.I)
ORCH_RE = re.compile(r"camerata|choral|orchest|philharmoni|symphon|sinfoni|ensemble|choir|\bchor|chor\b|quartet|kammer|chamber|band\b|big ?band", re.I)


def split_first(artist):
    """(erster Name, Rest) bei "A & B", "A und B", "A, B" ...; ohne Trenner (Name, '')."""
    m = JOIN_RE.search(artist or "")
    if not m or m.start() == 0:
        return artist, ""
    return artist[:m.start()].strip(), artist[m.end():].strip()


def lead_parts(artist, alone):
    """Interpreten, bei denen ein gemeinsamer Eintrag steht, oder [] (bleibt ganz). alone: {Schluessel: Zahl der Lieder}.
    Der vordere Name zaehlt, wenn es ihn auch allein gibt: mindestens so oft wie den ganzen Eintrag ("Rainhard Fendrich & ...")
    oder mindestens 3-mal und ein Fuenftel so oft ("Johann Sebastian Bach & Glenn Gould": 13 zu 62, Wunsch 13.11.2026); der
    laengste solche vordere Teil gewinnt ("Seiler und Speer, Sebastian Schneider" -> Seiler und Speer, nicht Seiler). Die Namen
    dahinter bekommen das Lied auch (Glenn Gould), ausser Orchester, Chor, Ensemble. Ohne bekannten vorderen Namen: nur bei
    einem Orchester danach der erste Name, sonst bleibt der Eintrag ganz ("Simon & Garfunkel")."""
    k = key(artist)
    whole = alone.get(k, 0)
    cuts = [m for m in JOIN_RE.finditer(artist or "") if m.start() > 0]
    for m in reversed(cuts):
        part = artist[:m.start()].strip()
        kp = key(part)
        n = alone.get(kp, 0)
        if kp != k and (n >= max(1, whole) or (n >= 3 and n * 5 >= whole)):
            rest = [x.strip() for x in re.split(r"\s*[,;]\s+", artist[m.end():]) if x and x.strip()]   # dahinter nur bei Beistrich: "Niki & The Dove" bleibt
            if len(rest) > 1 or "," in artist[:m.end() + 1]:   # Liste: auch "&" dahinter aufloesen ("..., Mistajam & John Newman"), 14.11.2026
                rest = [y for x in rest for y in _split_pair(x, alone)]
            return [part] + [x for x in rest if key(x) and key(x) != kp and not ORCH_RE.search(x)]
    first, rest = split_first(artist)
    if rest and ORCH_RE.search(rest) and not ORCH_RE.search(first) and key(first) != k:
        return [first]
    # Zwei Personen ohne Einzel-Lieder (Wunsch 14.11.2026: "John Travolta & Olivia Newton-John", "Albina & Stefy De Cicco"): genau
    # ein Trenner, kein Beistrich. Hinten eine Begleitband mit Artikel ("& The Wailers"): nur der vordere Name, wenn er aus zwei
    # Woertern besteht ("Kool & The Gang" bleibt). Sonst getrennt, wenn der hintere Teil mindestens zwei Woerter hat ("Simon &
    # Garfunkel", "Seiler und Speer" bleiben ganz).
    # Verunglueckte Tags ("... - Groove Me", "A / B", Klammern, "Meets", "Pres.") und Orchester/Ensembles bleiben ganz, ebenso
    # Bands mit Artikel vorne ("The Mamas & the Papas", "Die Doraus & Die Marinas", "Dance With a Stranger").
    first = DUET_RE.sub("", first).strip()
    if (len(cuts) == 1 and rest and not MESSY_RE.search(artist) and key(first) and key(rest) and key(first) != k
            and not ORCH_RE.search(first) and not ORCH_RE.search(rest) and not ART_RE.match(first)):
        nf, nr = len(first.split()), len(rest.split())
        if nf == 1 and (len(key(first)) < 3 or first.endswith(".")):
            return []                                    # "Mr. & Msr. Smith"
        if ART_RE.match(rest) or GROUP_RE.fullmatch(rest):
            return [first] if nf >= 2 else []           # Begleitung: "& the Wailers", "& Friends"
        if nr >= 2 or nf >= 2:                           # eine Seite mit zwei Woertern: zwei Interpreten ("Clean Bandit & Topic")
            return [first, rest]
    if len(cuts) >= 2 and key(first) != k:
        return list_parts(artist, alone)
    return []


LIST_AND_RE = re.compile(r"\s+(?:&|and|und|\+)\s+", re.I)


def _split_pair(sg, alone):
    """Ein Stueck einer Liste: "A & B" getrennt, ausser zwei einzelne Woerter (Duo) oder ein bekannter Name ("Klaus & Klaus")."""
    sub = [x.strip() for x in LIST_AND_RE.split(sg) if x.strip()]
    if len(sub) < 2 or (len(sub) == 2 and (all(len(x.split()) == 1 for x in sub) or ART_RE.match(sub[1]))):
        return [sg]                                      # Duo ("Harris & Ford") oder Band ("Niki & The Dove")
    if alone.get(key(sg), 0):                            # bekannt: so, wie der Eintrag allein zerlegt wird
        return lead_parts(sg, alone) or [sg]
    return sub


def list_parts(artist, alone=None):
    """Liste mehrerer Interpreten (Wunsch 14.11.2026: "Alok, Sofi Tukker & Inna"): an Beistrichen getrennt ("Jr." bleibt beim
    Namen davor), "&"/"und"/"+" trennen auch, ausser zwischen zwei einzelnen Woertern ("Harris & Ford" ist ein Duo). Nur einzelne
    Woerter: eine Band, bleibt ganz ("Earth, Wind & Fire", "Crosby, Stills & Nash"). "mit"/"with" trennen hier nicht ("Kloss mit
    Soss"), Orchester fallen weg. Verunglueckte Tags bleiben ganz."""
    alone = dict(alone or {})
    alone.pop(key(artist), None)                         # der ganze Eintrag selbst schuetzt nichts
    if MESSY_RE.search(artist or ""):
        return []
    segs = []
    for sg in re.split(r"\s*,\s+", artist.strip()):
        sg = sg.strip()
        m = re.match(r"(?:jr|sr)\.?(?=\s|$)", sg, re.I)
        if segs and m:                                   # "Tito Puente, Jr. & The Latin Rhythm"
            segs[-1] += ", " + m.group()
            sg = LIST_AND_RE.sub("", sg[m.end():], count=1).strip() if LIST_AND_RE.match(sg[m.end():]) else sg[m.end():].strip()
        if sg:
            segs.append(sg)
    if all(len(x.split()) == 1 for sg in segs for x in LIST_AND_RE.split(sg)) and not any(LIST_AND_RE.search(sg) for sg in segs[:-1]):
        return []                                        # Band: "Earth, Wind & Fire" ("Heinrich & Heine, Touchtalk" ist ein Duo plus einer)
    parts = [y for sg in segs for y in _split_pair(sg, alone)]
    out, seen = [], set()
    for x in parts:
        kx = key(x)
        if len(kx) >= 2 and kx not in seen and not ORCH_RE.search(x):
            seen.add(kx)
            out.append(x)
    return out if len(out) >= 2 else []


def key(artist):
    """Vereinfachter Name als Dateiname: klein, ohne Akzente, ss fuer ss, sonst nur a-z, 0-9 und -."""
    a = main_name(artist).lower().replace("ß", "ss")
    a = "".join(c for c in unicodedata.normalize("NFKD", a) if not unicodedata.combining(c))
    k = re.sub(r"[^a-z0-9]+", "-", a).strip("-")[:80].strip("-")
    if not k and a.strip():                           # nur andere Schriften: Zeichen-Nummern
        k = "u-" + "-".join("%x" % ord(c) for c in a.strip() if not c.isspace())[:70].strip("-")
    return k


def is_jpeg(data):
    return isinstance(data, (bytes, bytearray)) and data[:3] == b"\xff\xd8\xff"


def host_ok(url):
    try:
        u = urllib.parse.urlparse(str(url or ""))
    except ValueError:
        return False
    h = (u.hostname or "").lower()
    return u.scheme == "https" and any(h == x or h.endswith("." + x) for x in IMG_HOSTS)


def _slug_title(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def top_dir(path, root):
    """Oberster Ordner im Musikordner ("KLASSIK"), daneben liegende Ordner wie musik-import mit ihrem Namen, sonst ''."""
    p = unicodedata.normalize("NFC", str(path or ""))
    if not root or not p:
        return ""
    if p.startswith(root + "/"):
        rest = p[len(root) + 1:].split("/")
        return rest[0][:60] if len(rest) > 1 else ""
    base = os.path.dirname(root)
    if p.startswith(base + "/"):
        rest = p[len(base) + 1:].split("/")
        return rest[0][:60] if len(rest) > 1 and rest[0].startswith("musik-") else ""
    return ""


class Artists:
    def __init__(self, base, library, opener=None, now=time.time, root=None):
        """library() -> Lieder wie MixxxLink.library_full (artist, name, plays ...); opener(Request, timeout) fuers Internet."""
        self.base, self.library, self.now = base, library, now
        self.root = root or (lambda: "")                     # Musikordner am Mac (Filter nach oberstem Ordner, 13.11.2026)
        self.opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
        self.dir = os.path.join(base, DIR)
        self.index_path = os.path.join(base, INDEX)
        self.state_path = os.path.join(base, STATE)
        self.lock = threading.Lock()
        self.index = {}
        self.stop_ev = threading.Event()
        self.thread = None
        self.current, self.error = "", ""
        self.alias = {}
        self._load()

    # ---- Ablage ----
    def _load(self):
        try:
            with open(self.index_path, encoding="utf-8") as f:
                d = json.load(f)
            self.index = {k: v for k, v in d.items() if KEY_RE.match(k) and isinstance(v, dict)} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            self.index = {}

    def _save_index(self):
        os.makedirs(self.base, exist_ok=True)
        with open(self.index_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False)
        os.replace(self.index_path + ".tmp", self.index_path)

    def path(self, k):
        return os.path.join(self.dir, k + ".jpg")

    def mtime(self, k):
        try:
            return int(os.path.getmtime(self.path(k))) if KEY_RE.match(str(k or "")) else 0
        except OSError:
            return 0

    def save(self, k, name, data, src):
        if not KEY_RE.match(str(k or "")):
            raise ValueError("Schluessel unbrauchbar")
        if not is_jpeg(data) or len(data) > MAX_BYTES:
            raise ValueError("kein JPEG-Bild")
        os.makedirs(self.dir, exist_ok=True)
        p = self.path(k)
        with open(p + ".tmp", "wb") as f:
            f.write(data)
        os.replace(p + ".tmp", p)
        with self.lock:
            self.index[k] = {"name": str(name or "")[:120], "src": src, "t": int(self.now())}
            self._save_index()

    def mark_none(self, k, name):
        with self.lock:
            self.index[k] = {"name": str(name or "")[:120], "none": int(self.now())}
            self._save_index()

    def remove(self, k):
        """Bild weg (der Vorab-Lauf holt es nicht von selbst wieder: gilt als "keins gewollt")."""
        if not KEY_RE.match(str(k or "")):
            raise ValueError("Schluessel unbrauchbar")
        try:
            os.remove(self.path(k))
        except OSError:
            pass
        with self.lock:
            name = (self.index.get(k) or {}).get("name", "")
            self.index[k] = {"name": name, "none": int(self.now()), "user": 1}
            self._save_index()

    def raw(self, name):
        if not FILE_RE.match(str(name or "")):
            return None
        try:
            with open(os.path.join(self.dir, name), "rb") as f:
                return f.read()
        except OSError:
            return None

    def files(self):
        """[[Dateiname, Groesse, Aenderungszeit]] fuer die Sicherung auf den Stick."""
        try:
            names = os.listdir(self.dir)
        except OSError:
            return []
        out = []
        for n in sorted(names):
            if FILE_RE.match(n):
                try:
                    st = os.stat(os.path.join(self.dir, n))
                    out.append([n, st.st_size, int(st.st_mtime)])
                except OSError:
                    pass
        return out

    def restore(self, name, data):
        if not FILE_RE.match(str(name or "")):
            raise ValueError("Dateiname unbrauchbar")
        k = name[:-4]
        self.save(k, (self.index.get(k) or {}).get("name") or k, data, (self.index.get(k) or {}).get("src") or "sicherung")

    # ---- Liste aus der Bibliothek ----
    def groups(self):
        """{Schluessel: {name, songs: [Lied], plays, last, genres: {Genre: n}}} aus der Bibliothek."""
        out = {}
        try:
            root = unicodedata.normalize("NFC", str(self.root() or "")).rstrip("/")
        except Exception:                                   # noqa: BLE001  Musikordner unbekannt: ohne Bereich weiter, nie abstuerzen
            root = ""
        lib = self.library() or []
        alone = {}                                           # Namen mit Zahl ihrer Lieder (auch allein?)
        for x in lib:
            ka = key(main_name(x.get("artist") or ""))
            alone[ka] = alone.get(ka, 0) + 1
        alias = {}
        for x in lib:
            a = main_name(x.get("artist") or "")
            k = key(a)
            if not k:
                continue
            parts = [p for p in lead_parts(a, alone) if key(p)]
            if parts:
                alias[k] = key(parts[0])
            for a, k in ([(p, key(p)) for p in parts] or [(a, k)]):   # ein Lied kann bei mehreren stehen (Bach und Glenn Gould)
                self._add(out, a, k, x, root)
        for g in out.values():
            g["name"] = max(g["names"].items(), key=lambda kv: (kv[1], kv[0]))[0]
        self.alias = alias                                   # voller Schluessel -> Interpret (Seite: Link aus der Musik-DB)
        return out

    @staticmethod
    def _add(out, a, k, x, root):
        """Ein Lied beim Interpreten k (Anzeigename a) eintragen."""
        g = out.setdefault(k, {"names": {}, "songs": [], "plays": 0, "last": 0, "genres": {}, "dirs": {}, "grps": {}})
        d = top_dir(x.get("path") or "", root)
        if d:
            g["dirs"][d] = g["dirs"].get(d, 0) + 1
        for gr in {t.strip() for t in str(x.get("grp") or "").split(";") if t.strip()}:
            g["grps"][gr[:40]] = g["grps"].get(gr[:40], 0) + 1
        g["names"][a] = g["names"].get(a, 0) + 1
        g["songs"].append(x)
        g["plays"] += int(x.get("plays") or 0)
        g["last"] = max(g["last"], int(x.get("lastp") or 0))
        ge = str(x.get("genre") or "").strip()
        if ge:
            g["genres"][ge] = g["genres"].get(ge, 0) + 1

    def listing(self):
        """Fuer die Seite: [{k, name, n, plays, last, genre, img (Zeitstempel oder 0), none}]."""
        gs = self.groups()
        idx = dict(self.index)
        out = []
        for k, g in gs.items():
            e = idx.get(k) or {}
            gen = max(g["genres"].items(), key=lambda kv: kv[1])[0] if g["genres"] else ""
            out.append({"k": k, "name": g["name"], "n": len(g["songs"]), "plays": g["plays"], "last": g["last"], "genre": gen,
                        "dirs": g["dirs"], "grps": g["grps"], "gens": g["genres"],   # Genres mit Zahl der Lieder (Genre-Filter, 13.11.2026)
                        "img": self.mtime(k) if "none" not in e else 0, "none": 1 if "none" in e else 0, "src": e.get("src", "")})
        return out

    def songs(self, k):
        g = self.groups().get(k)
        if not g:
            return {"k": k, "name": "", "songs": []}
        keys = ("title", "name", "artist", "dur", "bpm", "key", "kid", "genre", "lvl", "path", "plays", "lastp", "album", "year", "rating")
        return {"k": k, "name": g["name"], "songs": [{f: s.get(f) for f in keys} for s in g["songs"]]}

    # ---- Internet ----
    def _get_json(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with self.opener(req, 12) as r:
            return json.loads(r.read(2 * 1024 * 1024).decode("utf-8") or "{}")

    def _get_img(self, url):
        if not host_ok(url):
            raise ValueError("Bildquelle nicht erlaubt")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with self.opener(req, 20) as r:
            data = r.read(MAX_BYTES + 1)
        if not is_jpeg(data) or len(data) > MAX_BYTES:
            raise ValueError("kein JPEG-Bild")
        return data

    def candidates(self, name):
        """Deezer-Treffer mit gleichem Namen, die meisten Fans zuerst: [{id, name, fans, url}]."""
        k = key(name)
        d = self._get_json(DEEZER + "/search/artist?limit=15&q=" + urllib.parse.quote(main_name(name)))
        out = []
        for a in d.get("data") or []:
            if not isinstance(a, dict) or key(a.get("name") or "") != k:
                continue
            url = str(a.get("picture_big") or "")
            if not host_ok(url) or "/artist//" in url:        # Deezer ohne Bild: leerer Pfad
                continue
            out.append({"id": int(a.get("id") or 0), "name": str(a.get("name") or ""), "fans": int(a.get("nb_fan") or 0), "url": url})
        return sorted(out, key=lambda a: -a["fans"])

    def _overlap(self, artist_id, titles):
        if not titles or not artist_id:
            return 0
        d = self._get_json(DEEZER + "/artist/%d/top?limit=50" % artist_id)
        theirs = {_slug_title(t.get("title")) for t in d.get("data") or [] if isinstance(t, dict)}
        return len(theirs & titles)

    def audiodb(self, name):
        d = self._get_json(AUDIODB + "/search.php?s=" + urllib.parse.quote(main_name(name)))
        out = []
        for a in d.get("artists") or []:
            if isinstance(a, dict) and key(a.get("strArtist") or "") == key(name):
                u = str(a.get("strArtistThumb") or "")
                if host_ok(u):
                    out.append({"name": str(a.get("strArtist") or ""), "url": u + "/medium", "src": "audiodb"})
        return out

    def deezer_pick(self, name, titles):
        """Der richtige Deezer-Eintrag bei gleichem Namen: der mit einem eigenen Lied im Programm, sonst einer mit deutlich den
        meisten Fans; sonst None."""
        ts = {_slug_title(t) for t in titles if _slug_title(t)}
        cands = self.candidates(name)
        for a in cands[:3]:
            if self._overlap(a["id"], ts):
                return a
        if cands and cands[0]["fans"] >= 1000 and (len(cands) == 1 or cands[0]["fans"] >= 10 * max(1, cands[1]["fans"])):
            return cands[0]
        if len(cands) == 1:                                # nur einer mit diesem Namen und Bild: auch mit wenigen Fans (Wunsch 14.11.2026)
            return cands[0]
        return None

    def pick(self, name, titles):
        """Bestes Bild (url, Quelle, Deezer-Nummer) oder (None, None, 0)."""
        a = self.deezer_pick(name, titles)
        if a:
            return a["url"], "deezer", a["id"]
        ad = self.audiodb(name)
        if ad:
            return ad[0]["url"], "audiodb", 0
        return None, None, 0

    def fetch(self, k, force=False):
        """Bild fuer einen Interpreten suchen und ablegen. True = abgelegt, False = nichts gefunden."""
        g = self.groups().get(k)
        if not g:
            raise ValueError("Interpret nicht in der Bibliothek")
        e = self.index.get(k) or {}
        if not force and e.get("user"):
            return False
        url, src, did = self.pick(g["name"], [s.get("name") or "" for s in g["songs"]])
        if not url:
            self.mark_none(k, g["name"])
            return False
        self.save(k, g["name"], self._get_img(url), src)
        if did:
            with self.lock:
                self.index[k]["did"] = did                     # fuer die Alben (info)
                self._save_index()
        return True

    # ---- Infos: Lebenslauf (TheAudioDB) und Alben (Deezer), nur beim Ansehen, 90 Tage gemerkt ----
    def info(self, k, refresh=False):
        g = self.groups().get(k)
        if not g:
            raise ValueError("Interpret nicht in der Bibliothek")
        p = os.path.join(self.base, INFO_DIR, k + ".json")
        if not refresh:
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                if self.now() - float(d.get("t") or 0) < INFO_KEEP_S:
                    return d
            except (OSError, ValueError):
                pass
        out = {"t": int(self.now()), "bio": "", "lang": "", "born": 0, "formed": 0, "died": 0, "place": "", "genre": "", "style": "",
               "web": "", "members": 0, "albums": [], "n_albums": 0}
        try:
            d = self._get_json(AUDIODB + "/search.php?s=" + urllib.parse.quote(g["name"]))
            a = next((x for x in d.get("artists") or [] if isinstance(x, dict) and key(x.get("strArtist") or "") == k), None)
        except (OSError, ValueError):
            a = None
        if a:
            num = lambda v: int(v) if str(v or "").isdigit() and 1000 <= int(v) <= 2100 else 0   # noqa: E731
            bio_de, bio_en = str(a.get("strBiographyDE") or "").strip(), str(a.get("strBiographyEN") or "").strip()
            out.update(bio=(bio_de or bio_en)[:6000], lang="de" if bio_de else ("en" if bio_en else ""),
                       born=num(a.get("intBornYear")), formed=num(a.get("intFormedYear")), died=num(a.get("intDiedYear")),
                       place=str(a.get("strCountry") or "")[:80], genre=str(a.get("strGenre") or "")[:40], style=str(a.get("strStyle") or "")[:40],
                       members=int(a["intMembers"]) if str(a.get("intMembers") or "").isdigit() else 0)
            w = str(a.get("strWebsite") or "").strip()
            if w and re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/\S*)?$", w, re.I):   # TheAudioDB schreibt ohne https://
                out["web"] = "https://" + w
        did = int((self.index.get(k) or {}).get("did") or 0)
        try:
            if not did:
                c = self.deezer_pick(g["name"], [s.get("name") or "" for s in g["songs"]])
                did = c["id"] if c else 0
            if did:
                al = self._get_json(DEEZER + "/artist/%d/albums?limit=100" % did)
                items = [x for x in al.get("data") or [] if isinstance(x, dict) and x.get("record_type") in ("album", "ep")]
                out["n_albums"] = len(items)
                out["albums"] = sorted(({"title": str(x.get("title") or "")[:120], "year": str(x.get("release_date") or "")[:4],
                                         "cover": str(x.get("cover_medium") or "") if host_ok(x.get("cover_medium")) else ""}
                                        for x in items), key=lambda x: (x["year"] or "9999", x["title"]))[:60]
        except (OSError, ValueError):
            pass
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)
        return out

    def suggestions(self, k):
        """Bilder zur Auswahl (Fenster "Bild aendern"): [{url, label, src}], hoechstens 8."""
        g = self.groups().get(k)
        name = g["name"] if g else k
        out = [{"url": a["url"], "label": "%s · %d Fans" % (a["name"], a["fans"]), "src": "deezer"} for a in self.candidates(name)[:6]]
        try:
            out += [{"url": a["url"], "label": a["name"] + " · TheAudioDB", "src": "audiodb"} for a in self.audiodb(name)[:2]]
        except (OSError, ValueError):
            pass
        return out[:8]

    def choose(self, k, url):
        g = self.groups().get(k)
        if not g:
            raise ValueError("Interpret nicht in der Bibliothek")
        self.save(k, g["name"], self._get_img(url), "audiodb" if "theaudiodb.com" in url else "deezer")
        return True

    def upload(self, k, data):
        g = self.groups().get(k)
        if not g:
            raise ValueError("Interpret nicht in der Bibliothek")
        self.save(k, g["name"], data, "eigen")
        return True

    # ---- Vorab-Lauf (Seite Statistik) ----
    def _flag(self, on=None):
        if on is None:
            try:
                with open(self.state_path, encoding="utf-8") as f:
                    return bool(json.load(f).get("on"))
            except (OSError, ValueError, AttributeError):
                return False
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"on": bool(on)}, f)
        except OSError:
            pass
        return on

    def _todo(self, tried):
        idx, now = dict(self.index), self.now()
        out = []
        for k, g in self.groups().items():
            e = idx.get(k) or {}
            if k in tried or e.get("user") or (("none" not in e) and self.mtime(k)):
                continue
            if "none" in e and now - float(e.get("none") or 0) < NONE_RETRY_S:
                continue
            out.append((len(g["songs"]), k))
        return [k for _n, k in sorted(out, key=lambda x: (-x[0], x[1]))]   # Interpreten mit vielen Liedern zuerst

    def status(self):
        gs = self.groups()
        idx = dict(self.index)
        done = sum(1 for k in gs if "none" not in (idx.get(k) or {}) and self.mtime(k))
        none = sum(1 for k in gs if "none" in (idx.get(k) or {}))
        running = self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set()
        return {"running": running, "total": len(gs), "done": done, "none": none, "done_all": bool(gs) and done + none >= len(gs),
                "current": self.current if running else "", "error": self.error, "files": len(self.files())}

    def run(self):
        tried = set()
        while not self.stop_ev.is_set():
            todo = self._todo(tried)
            if not todo:
                if self.groups():
                    self._flag(False)
                    self.current = ""
                    return
                if self.stop_ev.wait(5.0):
                    return
                continue
            for k in todo:
                if self.stop_ev.is_set():
                    return
                self.current = k
                try:
                    self.fetch(k)
                    self.error = ""
                except (OSError, ValueError) as e:
                    if isinstance(e, ValueError) and "Bibliothek" in str(e):
                        tried.add(k)
                        continue
                    self.error = "Internet gerade nicht erreichbar (%s)" % str(e)[:80]
                    if self.stop_ev.wait(WAIT_S):
                        return
                    break
                tried.add(k)
                if self.stop_ev.wait(GAP_S):
                    return

    def start(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set():
                return self.status()
            self._flag(True)
            self.error = ""
            self.stop_ev = threading.Event()
            self.thread = threading.Thread(target=self.run, name="interpreten-vorab", daemon=True)
            self.thread.start()
        return self.status()

    def retry_none(self):
        """"Leere noch einmal versuchen" (Wunsch 14.11.2026): erfolglose Suchen vergessen und den Vorab-Lauf starten.
        Von Hand entfernte Bilder ("keins gewollt") bleiben leer."""
        with self.lock:
            n = 0
            for k in [k for k, e in self.index.items() if "none" in e and not e.get("user")]:
                del self.index[k]
                n += 1
            if n:
                self._save_index()
        return dict(self.start(), retried=n)

    def stop(self):
        self._flag(False)
        self.stop_ev.set()
        return self.status()

    def resume(self):
        if self._flag():
            self.start()
