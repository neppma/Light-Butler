"""
albums.py - Alben (Wunsch von Markus, 13.11.2026). Seite /musik/alben, gebaut wie die Interpreten (artists.py).

Ein Album = Albumname plus Ordner: eine CD liegt fast immer in einem eigenen Ordner, Unterordner wie "CD 1" / "Disc 2" zaehlen
zum Ordner darueber. So fallen gleich benannte Alben ("Greatest Hits") verschiedener Interpreten nicht zusammen. Sampler
(viele Interpreten, keiner mit der Mehrheit) heissen "Verschiedene". Das Cover ist das des ersten Liedes (covers.py, schon am Pi).
Auf Wunsch je Album von Deezer: Erscheinungsdatum, Label und die Titelliste, verglichen mit den eigenen Liedern ("es fehlen ...").
Nur beim Ansehen, 90 Tage gemerkt in shows/_alben_info/<schluessel>.json; ins Internet gehen nur Album- und Interpretenname.
Aufs Licht wirkt das nicht.
"""
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

from . import artists as ar

INFO_DIR = "_alben_info"
INFO_KEEP_S = 90 * 86400.0
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,90}--[0-9a-f]{8}$")
DISC_RE = re.compile(r"^(?:(?:cd|disc|disk|teil|part)\s*[-_ ]?\s*\d+\b|(?:cd|disc|disk)$)", re.I)   # auch "Disc" ohne Nummer (14.11.2026)


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def album_dir(path):
    """Ordner des Albums: der Ordner der Datei, bei "CD 1", "Disc 2" ... der darueber."""
    d = os.path.dirname(nfc(path))
    return os.path.dirname(d) if DISC_RE.match(os.path.basename(d)) else d


def disc_of(path):
    m = re.search(r"\d+", os.path.basename(os.path.dirname(nfc(path))))
    return int(m.group()) if m and DISC_RE.match(os.path.basename(os.path.dirname(nfc(path)))) else 0


def track_no(t):
    m = re.match(r"\s*(\d+)", str(t or ""))
    return int(m.group(1)) if m else 0


def album_key(album, path):
    k = ar.key(album)[:80].strip("-") or "x"
    return k + "--" + hashlib.sha1(album_dir(path).encode("utf-8")).hexdigest()[:8]


class Albums:
    def __init__(self, base, library, opener=None, now=time.time, root=None, artists=None):
        """library() wie artists.Artists; artists: dieselbe Artists-Instanz (Interpreten-Schluessel fuer die Verknuepfung)."""
        self.base, self.library, self.now = base, library, now
        self.root = root or (lambda: "")
        self.artists = artists
        self.opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
        self.lock = threading.Lock()
        self.alias = {}                                  # Schluessel loser Lieder -> Album darunter (Regel 1, 14.11.2026)

    def canon(self, k):
        """Schluessel eines Albums nach dem Zusammenlegen (lose Lieder im Ordner darueber gehoeren zum Album darunter)."""
        return self.alias.get(k, k)

    def groups(self):
        """{Schluessel: {name, artist, artist_k, sampler, songs, plays, last, year, dirs, grps, folder}}."""
        try:
            root = nfc(self.root() or "").rstrip("/")
        except Exception:                                   # noqa: BLE001  Musikordner unbekannt: ohne Bereich weiter
            root = ""
        out = {}
        for x in self.library() or []:
            name = nfc(x.get("album")).strip()
            p = x.get("path") or ""
            if not name or not p:
                continue
            k = album_key(name, p)
            g = out.setdefault(k, {"names": {}, "songs": [], "plays": 0, "last": 0, "years": {}, "arts": {}, "dirs": {}, "grps": {}, "gens": {}, "folder": album_dir(p)})
            ge = nfc(x.get("genre")).strip()[:40]
            if ge:
                g["gens"][ge] = g["gens"].get(ge, 0) + 1
            g["names"][name] = g["names"].get(name, 0) + 1
            g["songs"].append(x)
            g["plays"] += int(x.get("plays") or 0)
            g["last"] = max(g["last"], int(x.get("lastp") or 0))
            if x.get("year"):
                g["years"][x["year"]] = g["years"].get(x["year"], 0) + 1
            a = ar.main_name(x.get("artist") or "")
            if a:
                g["arts"][a] = g["arts"].get(a, 0) + 1
            d = ar.top_dir(p, root)
            if d:
                g["dirs"][d] = g["dirs"].get(d, 0) + 1
            for gr in {t.strip() for t in str(x.get("grp") or "").split(";") if t.strip()}:
                g["grps"][gr[:40]] = g["grps"].get(gr[:40], 0) + 1
        # Regel 1 (Wunsch 14.11.2026, Fehlerbericht Falco "Einzelhaft" doppelt): gleicher Albumname, gleicher Interpret, und die
        # Lieder liegen lose im Ordner direkt ueber dem Album-Ordner ("Falco/" und "Falco/1982 - Einzelhaft/") -> ein Album.
        # Verschiedene Ausgaben in Geschwister-Ordnern (1998 / 1999) und Sampler unter "Compilations" bleiben getrennt.
        def ident(g):
            nm = max(g["names"].items(), key=lambda kv: (kv[1], kv[0]))[0]
            top = max(g["arts"].items(), key=lambda kv: kv[1])[0] if g["arts"] else ""
            return ar.key(nm), ar.key(top)
        by_id = {}
        for k, g in out.items():
            by_id.setdefault(ident(g), []).append(k)
        alias = {}
        for keys in by_id.values():
            if len(keys) < 2:
                continue
            for kp in sorted(keys, key=lambda k: len(out[k]["folder"]), reverse=True):   # tiefste zuerst: Ketten laufen nach unten
                if kp not in out:
                    continue
                child = next((kc for kc in keys if kc != kp and kc in out and os.path.dirname(out[kc]["folder"]) == out[kp]["folder"]), None)
                if child is None:
                    continue
                gp, gc = out.pop(kp), out[child]
                for f in ("names", "years", "arts", "dirs", "grps", "gens"):
                    for n, c in gp[f].items():
                        gc[f][n] = gc[f].get(n, 0) + c
                gc["songs"] += gp["songs"]
                gc["plays"] += gp["plays"]
                gc["last"] = max(gc["last"], gp["last"])
                alias[kp] = child
                for a_, b_ in list(alias.items()):
                    if b_ == kp:
                        alias[a_] = child
        self.alias = alias
        alone = {}                                           # wie artists.groups: Namen mit Zahl ihrer Lieder
        for x in self.library() or []:
            ka = ar.key(ar.main_name(x.get("artist") or ""))
            alone[ka] = alone.get(ka, 0) + 1
        for g in out.values():
            g["name"] = max(g["names"].items(), key=lambda kv: (kv[1], kv[0]))[0]
            g["year"] = max(g["years"].items(), key=lambda kv: kv[1])[0] if g["years"] else 0
            n = len(g["songs"])
            top = max(g["arts"].items(), key=lambda kv: kv[1]) if g["arts"] else ("", 0)
            g["sampler"] = len(g["arts"]) >= 3 and top[1] * 2 <= n      # viele Interpreten, keiner mit der Mehrheit
            g["artist"] = "" if g["sampler"] else top[0]
            # Interpreten-Seite (Fehlerbericht 17.11.2026, "David Guetta, Marten Hoerger, Men Machine & Snap!"): derselbe Schluessel
            # wie dort, also beim gemeinsamen Eintrag der erste Name, unter dem das Lied auch steht
            parts = [q for q in ar.lead_parts(top[0], alone) if ar.key(q)] if top[0] else []
            g["artist_k"] = (ar.key(parts[0]) if parts else ar.key(top[0])) if top[0] and not g["sampler"] else ""
            ds = {disc_of(s.get("path")) for s in g["songs"]}
            last = 999 if ds - {0} else 0                            # lose Lieder neben "Disc 1/2" ans Ende
            g["songs"].sort(key=lambda s: (disc_of(s.get("path")) or last, track_no(s.get("track")) or 999, nfc(s.get("path"))))
        return out

    def listing(self):
        out = []
        for k, g in self.groups().items():
            out.append({"k": k, "name": g["name"], "artist": g["artist"], "artist_k": g["artist_k"], "sampler": 1 if g["sampler"] else 0,
                        "n": len(g["songs"]), "plays": g["plays"], "last": g["last"], "year": g["year"], "dirs": g["dirs"], "grps": g["grps"], "gens": g["gens"],
                        "cover": g["songs"][0].get("path") or ""})
        return out

    def key_of_path(self, path):
        """Album zu einem Lied (Link aus der Musik-Datenbank)."""
        for x in self.library() or []:
            if (x.get("path") or "") == path and nfc(x.get("album")).strip():
                if not self.alias:
                    self.groups()
                return self.canon(album_key(nfc(x.get("album")).strip(), path))
        return ""

    def songs(self, k):
        gs = self.groups()
        k = self.canon(k)                                # alter Link auf die losen Lieder fuehrt zum ganzen Album
        g = gs.get(k)
        if not g:
            return {"k": k, "name": "", "songs": []}
        keys = ("title", "name", "artist", "dur", "bpm", "key", "kid", "genre", "lvl", "path", "plays", "lastp", "album", "year", "track", "rating")
        return {"k": k, "name": g["name"], "artist": g["artist"], "artist_k": g["artist_k"], "sampler": g["sampler"], "year": g["year"],
                "folder": g["folder"], "songs": [dict({f: s.get(f) for f in keys}, disc=disc_of(s.get("path"))) for s in g["songs"]]}

    # ---- Deezer: Datum, Label, Titelliste ----
    def _get_json(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": ar.UA, "Accept": "application/json"})
        with self.opener(req, 12) as r:
            return json.loads(r.read(2 * 1024 * 1024).decode("utf-8") or "{}")

    def _find(self, g):
        """Deezer-Album: gleicher Name (ohne Klammern wie "Remastered"), bei Nicht-Samplern gleicher Interpret; sonst None."""
        want = ar._slug_title(g["name"])
        q = g["name"] if g["sampler"] else g["artist"] + " " + g["name"]
        d = self._get_json(ar.DEEZER + "/search/album?limit=25&q=" + urllib.parse.quote(q))
        best = None
        for a in d.get("data") or []:
            if not isinstance(a, dict) or ar._slug_title(a.get("title")) != want:
                continue
            if not g["sampler"] and ar.key((a.get("artist") or {}).get("name") or "") != ar.key(g["artist"]):
                continue
            nb = int(a.get("nb_tracks") or 0)
            score = -abs(nb - len(g["songs"]))                   # Ausgabe mit passender Zahl der Lieder bevorzugt
            if best is None or score > best[0]:
                best = (score, a)
        return best[1] if best else None

    def info(self, k, refresh=False):
        if not KEY_RE.match(str(k or "")):
            raise ValueError("Album fehlt")
        gs = self.groups()
        k = self.canon(k)
        g = gs.get(k)
        if not g:
            raise ValueError("Album nicht in der Bibliothek")
        p = os.path.join(self.base, INFO_DIR, k + ".json")
        if not refresh:
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                if self.now() - float(d.get("t") or 0) < INFO_KEEP_S:
                    return self._mark(d, g)
            except (OSError, ValueError):
                pass
        out = {"t": int(self.now()), "found": False, "date": "", "label": "", "nb": 0, "tracks": [], "cover": "", "title": "", "artist": ""}
        a = self._find(g)
        if a:
            al = self._get_json(ar.DEEZER + "/album/%d" % int(a.get("id") or 0))
            tr = [{"title": str(t.get("title") or "")[:160], "artist": str((t.get("artist") or {}).get("name") or "")[:80],
                   "disc": int(t.get("disk_number") or 1), "no": int(t.get("track_position") or 0)}
                  for t in ((al.get("tracks") or {}).get("data") or []) if isinstance(t, dict)]
            cover = str(al.get("cover_big") or "")
            out.update(found=True, title=str(al.get("title") or "")[:200], artist=str((al.get("artist") or {}).get("name") or "")[:120],
                       date=str(al.get("release_date") or "")[:10], label=str(al.get("label") or "")[:120], nb=int(al.get("nb_tracks") or len(tr)),
                       tracks=tr[:200], cover=cover if ar.host_ok(cover) else "")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)
        return self._mark(out, g)

    @staticmethod
    def _mark(d, g):
        """Je Titel der Titelliste: hast du ihn (Vergleich ohne Klammern, Gross/klein, Zeichen)?"""
        have = {ar._slug_title(s.get("name") or s.get("title")) for s in g["songs"]}
        d = dict(d)
        d["tracks"] = [dict(t, have=ar._slug_title(t.get("title")) in have) for t in d.get("tracks") or []]
        d["missing"] = sum(1 for t in d["tracks"] if not t["have"])
        return d
