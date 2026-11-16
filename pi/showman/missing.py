"""
missing.py - Merkliste "Fehlt mir" (Wunsch von Markus, 14.11.2026).

Lieder, die in der Sammlung fehlen, lassen sich merken: bei den Alben (Titelliste laut Deezer, fehlende Titel) und in der
Musik-Datenbank, wenn die Suche nichts findet (dann der Suchtext). Gemerkt in shows/_fehlt_mir.json:
    [{"k": Schluessel, "a": Interpret, "t": Titel, "al": Album, "q": Suchtext, "at": Zeit}]
Kommt ein Lied spaeter in die Sammlung, zeigt die Liste es nicht mehr (kein Haken "besorgt", Wunsch): Titel gleich (ohne
Klammern, Gross/klein, Akzente) und der Interpret passt; bei einem Suchtext kommen alle seine Woerter in einem Lied vor.
Nur am Pi, nichts geht ins Internet, aufs Licht wirkt es nie.
"""
import json
import os
import threading
import time

from .artists import _slug_title, key as artist_key

FILE = "_fehlt_mir.json"
MAX = 2000


def norm(s):
    return " ".join(str(s or "").lower().split())[:200]


def entry_key(e):
    """Gleich wie SM.missKey im Browser: 'q:' + Suchtext oder 't:' + Interpret + '|' + Titel (klein, Leerzeichen einfach)."""
    return ("q:" + norm(e.get("q"))) if e.get("q") else ("t:" + norm(e.get("a")) + "|" + norm(e.get("t")))


def _words(s):
    return [w for w in _slug_title(s).split() if len(w) >= 2]


class Missing:
    def __init__(self, base, library, now=time.time):
        self.base, self.library, self.now = base, library, now
        self.path = os.path.join(base, FILE)
        self.lock = threading.Lock()
        self.items = []
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.items = [x for x in d if isinstance(x, dict) and isinstance(x.get("k"), str)] if isinstance(d, list) else []
        except (OSError, ValueError):
            pass

    def _save(self):
        os.makedirs(self.base, exist_ok=True)
        with open(self.path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False)
        os.replace(self.path + ".tmp", self.path)

    def add(self, a="", t="", al="", q=""):
        e = {"a": str(a or "").strip()[:160], "t": str(t or "").strip()[:200], "al": str(al or "").strip()[:200], "q": str(q or "").strip()[:200]}
        if e["q"]:
            e["a"] = e["t"] = e["al"] = ""
        elif not e["t"]:
            raise ValueError("Titel oder Suchtext fehlt")
        e["k"] = entry_key(e)
        e["at"] = int(self.now())
        with self.lock:
            if any(x["k"] == e["k"] for x in self.items):
                return e["k"]
            if len(self.items) >= MAX:
                raise ValueError("Die Liste ist voll (%d)" % MAX)
            self.items.append({k: v for k, v in e.items() if v or k in ("k", "at")})
            self._save()
        return e["k"]

    def remove(self, k):
        with self.lock:
            n = len(self.items)
            self.items = [x for x in self.items if x["k"] != k]
            if len(self.items) != n:
                self._save()
            return n - len(self.items)

    @staticmethod
    def _index(lib):
        idx = []
        for x in lib or []:
            idx.append((_slug_title(x.get("name") or x.get("title")), artist_key(x.get("artist")),
                        " " + _slug_title(" ".join(str(x.get(f) or "") for f in ("artist", "name", "title", "album"))) + " "))
        return idx

    @staticmethod
    def have(e, idx):
        """Gibt es das Lied jetzt in der Sammlung?"""
        if e.get("q"):
            ws = _words(e["q"])
            return bool(ws) and any(all(" " + w + " " in blob for w in ws) for _t, _a, blob in idx)
        t, a = _slug_title(e.get("t")), artist_key(e.get("a"))
        if not t:
            return False
        for st, sa, _b in idx:
            if st == t and (not a or not sa or a == sa or a in sa or sa in a):
                return True
        return False

    def state(self):
        """Fuer die Seite und die Knoepfe: gezeigte Eintraege (neueste zuerst), alle Schluessel, Zahl der ausgeblendeten."""
        idx = self._index(self.library())
        with self.lock:
            items = list(self.items)
        show = [dict(x, have=0) for x in items if not self.have(x, idx)]
        show.sort(key=lambda x: -int(x.get("at") or 0))
        return {"items": show, "keys": [x["k"] for x in items], "hidden": len(items) - len(show)}
