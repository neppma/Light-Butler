"""
eichen.py - letzter Durchlauf des Eichstuecks (Seite /eichen, Wunsch von Markus 23.11.2026).

Die Seite spielt das Eichstueck (eichstueck.py) im Browser, liest dabei /api/takt und /api/state mit und schickt das
Ergebnis hierher (Befehl eich_result), damit es sich ohne den Browser abholen laesst (GET /api/sm/eichen). Nur im
Speicher, keine Datei; die Daten kommen aus dem Browser und gelten als ungeprueft: nur bekannte Felder, Zahlen,
Wahrheitswerte und kurze Texte. Aufs Licht wirkt das nie.
"""
import time

MAX_SAMPLES = 4000
FIELDS = {"t": "num", "spielt": "bool", "aktiv": "bool", "bpm": "num", "abschnitt": "str", "dynamik": "str",
          "energie": "num", "beat_bpm": "num", "bpm_unsure": "bool", "beat_clear": "num", "state": "str", "db": "num",
          "src": "str"}
META = {"device": "str", "ua": "str", "start": "num", "version": "num", "note": "str"}


def _val(kind, v):
    if v is None:
        return None
    if kind == "num":
        return round(float(v), 3) if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 1e7 else None
    if kind == "bool":
        return bool(v) if isinstance(v, bool) else None
    return str(v)[:40] if isinstance(v, str) else None


def clean(d):
    d = d if isinstance(d, dict) else {}
    rows = d.get("samples") if isinstance(d.get("samples"), list) else []
    out = []
    for r in rows[:MAX_SAMPLES]:
        if isinstance(r, dict):
            out.append({k: _val(kind, r.get(k)) for k, kind in FIELDS.items()})
    meta = {k: _val(kind, d.get(k)) for k, kind in META.items()}
    return dict(meta, samples=out)


class EichRuns:
    def __init__(self):
        self.last = None

    def put(self, d):
        r = clean(d)
        r["got"] = time.time()
        self.last = r
        return {"ok": True, "n": len(r["samples"])}
