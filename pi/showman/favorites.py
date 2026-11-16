"""
favorites.py - Favoriten (Wunsch von Markus, 14.11.2026): Herz bei Liedern, Alben, Interpreten und Genres.

Gemerkt am Pi in shows/_favoriten.json (Ordner shows/ wird beim Einspielen nie ueberschrieben, die Sicherung nimmt ihn mit):
  {"song": {Pfad: {"sid", "name", "artist", "t"}}, "album": {Schluessel: {"name", "artist", "t"}},
   "artist": {Schluessel: {"name", "t"}}, "genre": {Name: {"t"}}}
Ein Lied haengt am Pfad, zusaetzlich an "sid" (Interpret, Titel, Laenge gerundet): wird eine Datei umbenannt oder verschoben,
findet es das Herz ueber sid wieder (heal). Lieder, die gerade nicht in der Bibliothek stehen, bleiben gemerkt.
Halbes Herz ("ind"): Lieder eines Lieblings-Albums oder -Interpreten. Genres machen kein halbes Herz (zu viele Lieder).
Aufs Licht wirkt das nicht. In die MP3 (Bewertung POPM) schreibt nur der Musik-Rechner, und nur mit Einstellung fav_mp3.
"""
import json
import os
import re
import threading
import time
import unicodedata

from . import albums as al
from . import artists as ar

FILE = "_favoriten.json"
KINDS = ("song", "album", "artist", "genre")
MAX_ITEMS = 20000
CACHE_S = 20.0


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def sid_of(x):
    """Kennung eines Liedes ohne Pfad: Interpret|Titel|Laenge (gerundet). Leer, wenn Titel fehlt."""
    t = ar._slug_title(x.get("name") or x.get("title") or "")
    if not t:
        return ""
    return ar.key(ar.main_name(x.get("artist") or "")) + "|" + t + "|" + str(int(round(float(x.get("dur") or 0))))


def check_id(kind, i):
    i = nfc(i).strip()
    if kind not in KINDS:
        raise ValueError("Art unbekannt")
    if kind == "song":
        if not i or len(i) > 2000 or "\x00" in i:
            raise ValueError("Lied fehlt")
    elif kind == "album":
        if not al.KEY_RE.match(i):
            raise ValueError("Album fehlt")
    elif kind == "artist":
        if not ar.KEY_RE.match(i):
            raise ValueError("Interpret fehlt")
    elif not i or len(i) > 60 or re.search(r"[\x00-\x1f]", i):
        raise ValueError("Genre fehlt")
    return i


class Favorites:
    def __init__(self, base, library, artists=None, albums=None, now=time.time):
        """library() wie artists.Artists; artists/albums: dieselben Instanzen (fuer das halbe Herz)."""
        self.base, self.library, self.now = base, library, now
        self.artists, self.albums = artists, albums
        self.lock = threading.Lock()
        self.path = os.path.join(base, FILE)
        self.d = {k: {} for k in KINDS}
        self.no = set()                                  # Lieder mit 5 Sternen in Mixxx, deren Herz hier weggenommen wurde
        self.ver = 0
        self._ind = (None, 0.0, set())
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            for k in KINDS:
                if isinstance(d.get(k), dict):
                    self.d[k] = {str(i): (v if isinstance(v, dict) else {}) for i, v in d[k].items()}
            if isinstance(d.get("no_mixxx"), list):
                self.no = {str(x) for x in d["no_mixxx"]}
        except (OSError, ValueError):
            pass

    def _save(self):
        os.makedirs(self.base, exist_ok=True)
        with open(self.path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(dict(self.d, no_mixxx=sorted(self.no)), f, ensure_ascii=False)
        os.replace(self.path + ".tmp", self.path)
        self.ver += 1

    # ---- 5 Sterne in Mixxx = Favorit (Wunsch 14.11.2026) ----
    stars = None                                         # showman/stars.py: hier gesetzte Sterne zaehlen auch

    def five(self, lib):
        st = self.stars
        return {x["path"] for x in lib or [] if x.get("path") and (st.eff(x["path"], x.get("rating")) if st is not None else int(x.get("rating") or 0)) >= 5}

    def songs(self, lib=None):
        """Lieder mit eigenem Herz: hier gesetzt oder 5 Sterne in Mixxx (ausser hier weggenommen). {Pfad: Eintrag}."""
        lib = self.library() if lib is None else lib
        with self.lock:
            out = dict(self.d["song"])
            no = set(self.no)
        for p in self.five(lib) - no:
            out.setdefault(p, {"t": 0, "mixxx": 1})
        return out

    # ---- setzen ----
    def set(self, kind, i, on, meta=None):
        i = check_id(kind, i)
        meta = meta if isinstance(meta, dict) else {}
        with self.lock:
            box = self.d[kind]
            if kind == "song" and i in self.five(self.library()):   # 5 Sterne in Mixxx: Herz weg merken, wieder an vergessen
                if not on and i not in self.no:
                    self.no.add(i)
                    box.pop(i, None)
                    self._save()
                    return True
                if on and i in self.no:
                    self.no.discard(i)
                    self._save()
                    return True
            if not on:
                gone = box.pop(i, None) is not None
                if kind == "album" and self.albums is not None:   # Herz auf einem zusammengelegten Album: auch den alten Schluessel
                    for k in [k for k in box if self.albums.canon(k) == i]:
                        box.pop(k)
                        gone = True
                if not gone:
                    return False
                self._save()
                return True
            if i in box:
                return False
            if sum(len(v) for v in self.d.values()) >= MAX_ITEMS:
                raise ValueError("Zu viele Favoriten")
            e = {"t": int(self.now())}
            if kind == "song":
                x = next((x for x in self.library() or [] if (x.get("path") or "") == i), None) or {}
                e.update(sid=sid_of(x) if x else "", name=nfc(x.get("name") or x.get("title") or meta.get("name"))[:160],
                         artist=nfc(x.get("artist") or meta.get("artist"))[:120])
            elif kind in ("album", "artist"):
                e["name"] = nfc(meta.get("name"))[:160]
                if kind == "album":
                    e["artist"] = nfc(meta.get("artist"))[:120]
            box[i] = e
            self._save()
            return True

    def is_fav(self, kind, i):
        return nfc(i) in self.d.get(kind, {})

    # ---- umbenannte/verschobene Lieder wiederfinden ----
    def heal(self, lib=None):
        lib = self.library() if lib is None else lib
        if not lib:
            return 0
        paths = {x.get("path") for x in lib if x.get("path")}
        with self.lock:
            lost = {p: e for p, e in self.d["song"].items() if p not in paths and e.get("sid")}
            if not lost:
                return 0
            by_sid = {}
            for x in lib:
                if x.get("path") and x["path"] not in self.d["song"]:
                    by_sid.setdefault(sid_of(x), x["path"])
            n = 0
            for p, e in lost.items():
                np_ = by_sid.get(e["sid"])
                if np_ and np_ not in self.d["song"]:
                    self.d["song"][np_] = e
                    del self.d["song"][p]
                    n += 1
            if n:
                self._save()
            return n

    # ---- halbes Herz: Lieder von Lieblings-Alben und -Interpreten ----
    def indirect(self, lib=None):
        if not self.d["album"] and not self.d["artist"]:
            return set()
        lib = self.library() if lib is None else lib
        key = (self.ver, len(lib or []), id(lib))
        k0, t0, s0 = self._ind
        if k0 == key and self.now() - t0 < CACHE_S:
            return s0
        out = set()
        if self.d["artist"] and self.artists is not None:
            G = self.artists.groups()
            for k in self.d["artist"]:
                out.update(s.get("path") for s in (G.get(k) or {}).get("songs", []) if s.get("path"))
        if self.d["album"]:
            canon = self.albums.canon if self.albums is not None else (lambda k: k)
            if self.albums is not None:
                self.albums.groups()                         # Zusammenlegen (Regel 1) kennen
            fav = {canon(k) for k in self.d["album"]}
            for x in lib or []:
                a = nfc(x.get("album")).strip()
                if a and x.get("path") and canon(al.album_key(a, x["path"])) in fav:
                    out.add(x["path"])
        out -= set(self.songs(lib))
        self._ind = (key, self.now(), out)
        return out

    def state(self):
        """Fuer alle Seiten: was ein Herz hat. ind = halbes Herz (Lied eines Lieblings-Albums oder -Interpreten)."""
        lib = self.library() or []
        self.heal(lib)
        ind = self.indirect(lib)
        with self.lock:
            d = {k: sorted(self.d[k]) for k in KINDS}
        d["song"] = sorted(self.songs(lib))
        if self.albums is not None:                          # zusammengelegte Alben: Herz auch unter dem neuen Schluessel
            d["album"] = sorted(set(d["album"]) | {self.albums.canon(k) for k in d["album"]})
        d["ind"] = sorted(ind)
        d["v"] = self.ver
        return d

    def weight(self, lib=None):
        """Auto-DJ: Pfad -> 2 (eigenes Herz), 1 (halbes Herz oder Lieblings-Genre)."""
        lib = self.library() if lib is None else lib
        w = {p: 1 for p in self.indirect(lib)}
        gen = {g.lower() for g in self.d["genre"]}
        if gen:
            for x in lib or []:
                if x.get("path") and str(x.get("genre") or "").strip().lower() in gen:
                    w.setdefault(x["path"], 1)
        for p in self.songs(lib):
            w[p] = 2
        return w

    def page(self):
        """Seite /musik/favoriten: Lieder (mit halben Herzen), Alben, Interpreten, Genres."""
        lib = self.library() or []
        self.heal(lib)
        ind = self.indirect(lib)
        fs = self.songs(lib)
        with self.lock:
            fa, fr, fg = dict(self.d["album"]), dict(self.d["artist"]), dict(self.d["genre"])
        keys = ("title", "name", "artist", "dur", "bpm", "key", "kid", "genre", "lvl", "est", "elv", "path", "plays", "lastp", "album", "year", "grp")
        songs, seen = [], set()
        for x in lib:
            p = x.get("path") or ""
            if p in fs or p in ind:
                songs.append(dict({f: x.get(f) for f in keys}, fav=2 if p in fs else 1, ft=int((fs.get(p) or {}).get("t") or 0)))
                seen.add(p)
        for p, e in fs.items():                                  # gemerkt, aber gerade nicht in der Bibliothek
            if p not in seen:
                songs.append({"path": p, "name": e.get("name") or os.path.basename(p), "artist": e.get("artist") or "", "fav": 2, "ft": int(e.get("t") or 0), "gone": 1})
        albums = []
        if fa and self.albums is not None:
            for x in self.albums.listing():
                if x["k"] in fa or any(self.albums.canon(k) == x["k"] for k in fa):
                    e = fa.get(x["k"]) or next(v for k, v in fa.items() if self.albums.canon(k) == x["k"])
                    albums.append(dict(x, ft=int(e.get("t") or 0)))
            have = {x["k"] for x in albums}
            albums += [{"k": k, "name": e.get("name") or k, "artist": e.get("artist") or "", "n": 0, "gone": 1, "ft": int(e.get("t") or 0)} for k, e in fa.items() if k not in have and self.albums.canon(k) not in have]
        artists = []
        if fr and self.artists is not None:
            for x in self.artists.listing():
                if x["k"] in fr:
                    artists.append(dict(x, ft=int(fr[x["k"]].get("t") or 0)))
            have = {x["k"] for x in artists}
            artists += [{"k": k, "name": e.get("name") or k, "n": 0, "img": 0, "gone": 1, "ft": int(e.get("t") or 0)} for k, e in fr.items() if k not in have]
        cnt, shown = {}, {}
        for x in lib:
            g = nfc(x.get("genre")).strip()[:60]
            if g:
                cnt[g.lower()] = cnt.get(g.lower(), 0) + 1
                shown.setdefault(g.lower(), g)
        genres = [{"name": g, "n": cnt.get(g.lower(), 0), "ft": int(e.get("t") or 0)} for g, e in fg.items()]
        all_g = sorted(([shown[k], n] for k, n in cnt.items()), key=lambda gn: gn[0].lower())   # zum Dazunehmen auf der Seite
        return {"songs": songs, "albums": albums, "artists": artists, "genres": genres, "all_genres": all_g}
