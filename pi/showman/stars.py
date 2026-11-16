"""
stars.py - Sterne im Light-Butler setzen (Wunsch von Markus, 14.11.2026).

Mixxx bewertet Lieder mit 0 bis 5 Sternen (nur in seiner Datenbank). Die Bruecke schickt sie mit (Feld 32). Hier lassen sie sich
auch setzen: Musik-Datenbank, Alben, Interpreten, Tag-Editor. Gemerkt in shows/_sterne.json:
    {Pfad: {"r": 0-5, "t": Zeit, "q": 0/1}}     q = der Musik-Rechner hat es in seine Warteschlange fuer Mixxx uebernommen
Der Musik-Rechner holt offene Eintraege mit /api/musik/conf (alle 30 s, Feld "stars") und bestaetigt mit dem Befehl
stars_ack. Beim naechsten Start der Mixxx-App traegt mixxx_sterne.py sie in die Mixxx-Datenbank ein (Mixxx laeuft dann nicht).
Bis Mixxx denselben Wert meldet, gilt der Wert von hier; danach faellt der Eintrag weg. Aufs Licht wirkt das nie.
"""
import json
import os
import threading
import time

FILE = "_sterne.json"
MAX_SET = 3000
MAX_PENDING = 3000


class Stars:
    def __init__(self, base, now=time.time):
        self.base, self.now = base, now
        self.path = os.path.join(base, FILE)
        self.lock = threading.Lock()
        self.d = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.d = {str(p): e for p, e in d.items() if isinstance(e, dict) and isinstance(e.get("r"), int) and 0 <= e["r"] <= 5}
        except (OSError, ValueError):
            pass

    def _save(self):
        os.makedirs(self.base, exist_ok=True)
        with open(self.path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False)
        os.replace(self.path + ".tmp", self.path)

    def set(self, paths, r):
        """Sterne fuer Lieder setzen (0 = keine). Rueckgabe: Zahl der Lieder."""
        if isinstance(r, bool) or not isinstance(r, int) or not 0 <= r <= 5:
            raise ValueError("Sterne 0 bis 5")
        ps = [str(p) for p in (paths or []) if isinstance(p, str) and p and len(p) <= 2000 and "\x00" not in p][:MAX_SET]
        if not ps:
            raise ValueError("kein Lied")
        t = int(self.now())
        with self.lock:
            for p in ps:
                self.d[p] = {"r": r, "t": t, "q": 0}
            self._save()
        return len(ps)

    def eff(self, path, lib_r):
        """Wirksamer Wert: von hier, solange Mixxx ihn noch nicht hat, sonst der aus Mixxx."""
        e = self.d.get(path)
        return e["r"] if e else int(lib_r or 0)

    def apply(self, rows):
        """Liedliste mit den Sternen von hier (Kopie nur der geaenderten Eintraege)."""
        if not self.d:
            return rows
        out = []
        for x in rows:
            e = self.d.get(x.get("path") or "")
            out.append(dict(x, rating=e["r"]) if e and e["r"] != int(x.get("rating") or 0) else x)
        return out

    def settle(self, lib):
        """Meldet Mixxx denselben Wert (nach dem Eintragen beim App-Start), braucht es den Eintrag hier nicht mehr."""
        if not self.d or not lib:
            return 0
        have = {x.get("path"): int(x.get("rating") or 0) for x in lib if x.get("path")}
        with self.lock:
            done = [p for p, e in self.d.items() if e.get("q") and have.get(p) == e["r"]]
            for p in done:
                del self.d[p]
            if done:
                self._save()
        return len(done)

    def pending(self):
        """Fuer den Musik-Rechner: [[Pfad, Sterne, Zeit]] noch nicht uebernommen."""
        with self.lock:
            return [[p, e["r"], e["t"]] for p, e in self.d.items() if not e.get("q")][:MAX_PENDING]

    def ack(self, items):
        """Der Musik-Rechner hat diese in seine Warteschlange uebernommen (nur, wenn seither nicht neu gesetzt)."""
        n = 0
        with self.lock:
            for it in items or []:
                if not isinstance(it, list) or len(it) < 3:
                    continue
                e = self.d.get(str(it[0]))
                if e and e["r"] == it[1] and e["t"] == it[2] and not e.get("q"):
                    e["q"] = 1
                    n += 1
            if n:
                self._save()
        return n
