#!/usr/bin/env python3
"""
mixxx_sterne.py - Sterne aus dem Light-Butler in Mixxx eintragen (Wunsch von Markus, 14.11.2026).

Im Light-Butler gesetzte Sterne holt der Musik-Rechner vom Pi (/api/musik/conf, Feld "stars") in die Warteschlange
~/Light-Butler-Daten/sterne/offen.json ({Pfad: [Sterne, Zeit]}, das Neueste gilt). Das Startskript der App "Light-Butler Mixxx" ruft
mixxx_sterne.sh auf, BEVOR Mixxx startet (Mixxx darf nicht laufen), wie mixxx_umbenennen.sh:
  - Liegt ein Journal neben der Datenbank (Mixxx nicht sauber beendet), wird nichts angefasst.
  - Vorher eine Sicherungskopie (~/Light-Butler-Daten/sterne/mixxxdb-vor-sterne.sqlite).
  - Immer ueber eine Kopie (Python darf den Ordner von Mixxx nicht oeffnen, cp im Skript schon, Fehlerbericht 14.11.2026):
    das Skript holt Sicherung und Arbeitskopie mit cp, hier wird eingetragen und geprueft (--kopie, integrity_check), das
    Skript kopiert mit cp zurueck und vergleicht mit cmp, dann kuerzt --fertig die Warteschlange.
  - Geaendert wird nur library.rating der passenden Lieder (Pfad aus track_locations, Umlaute egal). Was eingetragen ist
    oder kein Lied in Mixxx hat, faellt aus der Warteschlange; der Rest bleibt fuer den naechsten Start.
Aufruf:  python3 mixxx_sterne.py --kopie ARBEITSKOPIE | --fertig | MIXXXDB [WARTESCHLANGE] (alles in einem, ohne cp)
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)


def data_dir():
    return os.path.join(_pfad.daten(), "sterne")


def queue_path():
    return os.path.join(data_dir(), "offen.json")


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def load(q=None):
    try:
        with open(q or queue_path(), encoding="utf-8") as f:
            d = json.load(f)
        return {str(p): v for p, v in d.items() if isinstance(v, list) and len(v) == 2} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d, q=None):
    q = q or queue_path()
    os.makedirs(os.path.dirname(q), exist_ok=True)
    with open(q + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(q + ".tmp", q)


def add(items, q=None):
    """Vom Pi: [[Pfad, Sterne, Zeit]]. Neueres ersetzt Aelteres. Rueckgabe: die uebernommenen Eintraege (zum Bestaetigen)."""
    d, ok = load(q), []
    for it in items or []:
        if not (isinstance(it, list) and len(it) >= 3 and isinstance(it[0], str) and isinstance(it[1], int) and not isinstance(it[1], bool)
                and 0 <= it[1] <= 5 and isinstance(it[2], int)):
            continue
        old = d.get(it[0])
        if old is None or it[2] >= old[1]:
            d[it[0]] = [it[1], it[2]]
        ok.append([it[0], it[1], it[2]])
    if ok:
        _write(d, q)
    return ok


def _apply_db(path, d):
    """In der Datenbank path eintragen. Rueckgabe (eingetragen, unbekannt)."""
    con = sqlite3.connect(path, timeout=5)
    try:
        locs = {}
        for lid, loc in con.execute("SELECT id, location FROM track_locations"):
            locs[nfc(loc)] = lid
        done, unknown = [], []
        for p, (r, _t) in d.items():
            lid = locs.get(nfc(p))
            if lid is None:
                unknown.append(p)
                continue
            con.execute("UPDATE library SET rating = ? WHERE location = ?", (int(r), lid))
            done.append(p)
        con.commit()
        return done, unknown
    finally:
        con.close()


def _ok(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def _done_path():
    return os.path.join(data_dir(), ".erledigt.json")


def prepare(work, q=None):
    """In der Arbeitskopie eintragen und pruefen (die Kopie holt mixxx_sterne.sh mit cp: Python darf den Ordner von Mixxx
    nicht oeffnen, Fehlerbericht 14.11.2026). Merkt, was erledigt ist (.erledigt.json), Rueckgabe: Zahl der eingetragenen."""
    d = load(q)
    if not d:
        return 0
    done, unknown = _apply_db(work, d)
    if not _ok(work):
        raise sqlite3.DatabaseError("Arbeitskopie nach dem Eintragen fehlerhaft")
    os.makedirs(data_dir(), exist_ok=True)
    with open(_done_path(), "w", encoding="utf-8") as f:
        json.dump({"done": {p: d[p] for p in done}, "unknown": {p: d[p] for p in unknown}}, f, ensure_ascii=False)
    return len(done)


def finish(q=None, log=print):
    """Nach dem Zurueckkopieren: Erledigtes und Unbekanntes aus der Warteschlange (was inzwischen neu gesetzt wurde, bleibt)."""
    try:
        with open(_done_path(), encoding="utf-8") as f:
            r = json.load(f)
        os.remove(_done_path())
    except (OSError, ValueError):
        return {"done": 0, "unknown": 0, "left": len(load(q))}
    gone = dict(r.get("done") or {}, **(r.get("unknown") or {}))
    cur = load(q)
    rest = {p: v for p, v in cur.items() if not (p in gone and gone[p] == v)}
    _write(rest, q)
    nd, nu = len(r.get("done") or {}), len(r.get("unknown") or {})
    log(f"Sterne in Mixxx eingetragen: {nd}" + (f", {nu} ohne Lied in Mixxx" if nu else ""))
    return {"done": nd, "unknown": nu, "left": len(rest)}


def apply(db, q=None, log=print, force_copy=False):
    """Derselbe Ablauf wie mixxx_sterne.sh, ganz in Python (Tests, Rechner ohne Schutz des Mixxx-Ordners): Journal = nichts,
    Sicherung, Arbeitskopie, eintragen, zurueckkopieren, vergleichen, dann Warteschlange kuerzen."""
    if not load(q):
        return {"done": 0, "unknown": 0, "left": 0}
    if not os.path.isfile(db) or os.path.exists(db + "-journal") or os.path.exists(db + "-wal"):
        log("Sterne: Mixxx-Datenbank fehlt oder Mixxx wurde nicht sauber beendet, nichts eingetragen")
        return {"done": 0, "unknown": 0, "left": len(load(q))}
    os.makedirs(data_dir(), exist_ok=True)
    bak = os.path.join(data_dir(), "mixxxdb-vor-sterne.sqlite")
    tmpd = tempfile.mkdtemp(prefix="lb_sterne_")
    work = os.path.join(tmpd, "mixxxdb.sqlite")
    try:
        shutil.copyfile(db, bak)
        shutil.copyfile(bak, work)
        if prepare(work, q):
            shutil.copyfile(work, db)
            with open(work, "rb") as a, open(db, "rb") as b:
                if a.read() != b.read():
                    shutil.copyfile(bak, db)
                    raise OSError("Zurueckkopieren hat nicht geklappt, Sicherung zurueckgespielt")
    except (OSError, sqlite3.Error) as e:
        log(f"Sterne: nichts eingetragen ({e}), bleibt fuer den naechsten Start")
        return {"done": 0, "unknown": 0, "left": len(load(q))}
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    return finish(q, log)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--kopie"] and len(a) == 2:                 # aus mixxx_sterne.sh: nur die Zahl auf stdout
        try:
            print(prepare(a[1]))
        except (OSError, sqlite3.Error) as e:
            print(f"Arbeitskopie: {e}")
            sys.exit(1)
    elif a[:1] == ["--fertig"]:
        finish()
    elif a:
        apply(a[0], a[1] if len(a) > 1 else None)
    else:
        sys.exit(__doc__)
