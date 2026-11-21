"""
local_play.py - was gerade in der Musik-Datenbank im Browser laeuft (Knopf Play, 21.11.2026).

Die Seite /musik meldet beim Abspielen, Anhalten und alle paar Sekunden Titel, Interpret, Pfad, Stelle und Laenge
(Befehl local_play). Das Hauptpanel zeigt es als Quelle "Lokal" (Titel, Cover), die Pixel-Matrix nimmt Bilder und
Laufschrift dazu. Aufs Licht wirkt es nie. Ohne Meldung seit STALE_S gilt es als beendet (Seite zu, Browser weg).
"""
import time

STALE_S = 8.0


def _txt(v, n=200):
    return str(v or "").strip()[:n]


def _num(v, lo=0.0, hi=24 * 3600.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return min(hi, max(lo, x)) if x == x else 0.0


class LocalPlay:
    def __init__(self, now=time.monotonic):
        self.now = now
        self.cur = None

    def report(self, d):
        """Meldung der Seite (ungepruefte Daten aus dem Browser): nur kurze Texte und Zahlen."""
        if not isinstance(d, dict) or not d.get("playing") or not _txt(d.get("title") or d.get("name")):
            self.cur = None
            return None
        self.cur = {"title": _txt(d.get("title") or d.get("name")), "artist": _txt(d.get("artist")), "album": _txt(d.get("album")),
                    "genre": _txt(d.get("genre"), 60), "path": _txt(d.get("path"), 1000),
                    "dur": round(_num(d.get("dur")), 1), "pos": round(_num(d.get("pos")), 1), "t": self.now()}
        return self.panel()

    def current(self):
        c = self.cur
        if c is None or self.now() - c["t"] > STALE_S:
            return None
        return c

    def panel(self):
        """Fuer das Hauptpanel: Titel, Interpret, Genre, Pfad (Cover), Stelle jetzt (laeuft weiter seit der Meldung)."""
        c = self.current()
        if c is None:
            return None
        pos = c["pos"] + (self.now() - c["t"])
        if c["dur"]:
            pos = min(pos, c["dur"])
        return {"title": c["title"], "artist": c["artist"], "genre": c["genre"], "path": c["path"],
                "dur": c["dur"], "pos": round(pos, 1)}

    def song(self):
        """Fuer die Pixel-Matrix: Lied mit Pfad (Cover, Interpret, Album aus der Bibliothek)."""
        c = self.current()
        if c is None:
            return None
        return {"title": c["title"], "dur": c["dur"], "path": c["path"], "artist": c["artist"], "album": c["album"]}
