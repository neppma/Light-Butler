"""Lose Album-Lieder (Wunsch von Markus, 14.11.2026): Lieder eines Albums, die lose im Interpreten-Ordner liegen, waehrend der
Rest des Albums im Unterordner steckt ("Falco/Falco - Zuviel Hitze.mp3" neben "Falco/1982 - Einzelhaft/"). Die Alben-Seite am
Pi zaehlt sie schon zum Album (Regel 1 in pi/showman/albums.py); dieses Werkzeug in der Datenpflege (Seite /musik/lose)
verschiebt die Dateien auf Wunsch in den Album-Ordner.

Gleiche Regel wie am Pi: gleicher Albumname, gleicher Interpret, Ordner direkt darueber; "CD 1"/"Disc 2"/"Disc" zaehlen zum
Ordner darueber. Verschoben wird ueber die Warteschlange fuer Mixxx wie beim Ordner aufloesen (folder_merge._queue_move): Mixxx
behaelt Hotcues, Kisten und Playlists. Nie ueberschreiben: liegt im Ziel schon eine Datei mit dem Namen, bleibt das Lied liegen.
Jeder Schritt steht im Protokoll (~/Light-Butler-Daten/album_lose/protokoll.jsonl) und laesst sich zuruecknehmen. Waehrend der Stick
ausgeworfen wird, passiert nichts. Aufs Licht wirkt das nicht.
"""
import json
import os
import re
import time
import unicodedata

import cd_assist
import file_check as fc
import folder_merge
from pfad import norm as _pn, relpath as _relpath
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

DISC_RE = re.compile(r"^(?:(?:cd|disc|disk|teil|part)\s*[-_ ]?\s*\d+\b|(?:cd|disc|disk)$)", re.I)   # wie pi/showman/albums.py
FEAT_RE = re.compile(r"\s*;.*$|\s+(?:feat\.?|ft\.?|featuring|vs\.?|versus)\s+.*$|\s*\((?:feat\.?|ft\.?|featuring)\s.*\)\s*$", re.I)


def nfc(s):
    return _pn(unicodedata.normalize("NFC", str(s or "")))          # Windows: "\\" -> "/"


def key(s):
    s = nfc(s).lower().replace("ß", "ss")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def album_dir(path):
    d = os.path.dirname(nfc(path))
    return os.path.dirname(d) if DISC_RE.match(os.path.basename(d)) else d


def data_dir():
    return os.path.join(_pfad.daten(), "album_lose")


def scan(check):
    """{"root", "albums": [{artist, album, target, rel_target, n_album, cover, songs: [{path, file, rel, title, exists}]}], "n"}."""
    root = nfc(check.root() or "").rstrip("/")
    pend = cd_assist._pending()
    groups = {}                                            # (Album, Interpret) -> {Ordner: [(Zeile, Datei)]}
    for r in check.songs() or []:
        a, p = nfc(r.get("album")).strip(), r.get("path") or ""
        if not a or not p:
            continue
        f = cd_assist._where(check, p, pend)
        if not f or not os.path.isfile(f):
            continue
        art = key(FEAT_RE.sub("", nfc(r.get("artist")).strip()))
        groups.setdefault((key(a), art), {}).setdefault(album_dir(f), []).append((r, nfc(f)))
    out = []
    for dirs in groups.values():
        if len(dirs) < 2:
            continue
        for parent, items in dirs.items():
            child = next((d for d in sorted(dirs) if d != parent and os.path.dirname(d) == parent), None)
            if child is None:
                continue
            loose = [(r, f) for r, f in items if os.path.dirname(f) == parent]   # nur wirklich lose (nicht schon in einem "Disc"-Ordner)
            if not loose:
                continue
            ex = dirs[child][0][0]
            out.append({"artist": nfc(ex.get("artist")), "album": nfc(ex.get("album")), "target": child,
                        "rel_target": _relpath(child, root) if root else child, "n_album": len(dirs[child]),
                        "cover": dirs[child][0][0].get("path") or "",
                        "songs": [{"path": r.get("path") or "", "file": f, "rel": _relpath(f, root) if root else f,
                                   "title": nfc(r.get("title")), "track": nfc(r.get("tracknumber") or "").strip()[:7], "exists": os.path.exists(os.path.join(child, os.path.basename(f)))}
                                  for r, f in sorted(loose, key=lambda x: x[1].casefold())]})
    out.sort(key=lambda x: (x["artist"].casefold(), x["album"].casefold()))
    return {"root": root, "albums": out, "n": len(out), "songs": sum(len(x["songs"]) for x in out)}


_cache = [0.0, None]


def count(check, max_age=300.0, now=time.time):
    """Fuer die Zahl in der Datenpflege (alle 30 s gefragt): hoechstens alle 5 Minuten neu rechnen."""
    if _cache[1] is None or now() - _cache[0] > max_age:
        _cache[1] = scan(check)
        _cache[0] = now()
    return {"n": _cache[1]["songs"], "albums": _cache[1]["n"]}


def _log(entry):
    os.makedirs(data_dir(), exist_ok=True)
    with open(os.path.join(data_dir(), "protokoll.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def history(n=20):
    try:
        with open(os.path.join(data_dir(), "protokoll.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        return []
    return [{"t": r["t"], "n": len(r.get("moves") or []), "undone": bool(r.get("undone")), "albums": r.get("albums") or []} for r in rows[-n:]][::-1]


def apply(check, items, log=None, now=time.time):
    """items: [{path (Mixxx-Pfad), file (Datei am Stick), target (Album-Ordner)}]. Nie ueberschreiben."""
    import stick_hold
    log = log or (lambda t: None)
    if stick_hold.held():
        raise ValueError("Der Stick ist ausgeworfen")
    root = nfc(check.root() or "").rstrip("/")
    if not root:
        raise ValueError("Musikordner unbekannt")
    pend = cd_assist._pending()
    res = {"moved": 0, "skipped": 0, "errors": []}
    moves, albums = [], set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        mp, f, tgt = str(it.get("path") or ""), nfc(it.get("file") or ""), nfc(it.get("target") or "").rstrip("/")
        name = os.path.basename(f)
        try:
            real = cd_assist._where(check, mp, pend) if mp else None
            if not real or nfc(real) != f or not os.path.isfile(real):
                raise ValueError("Datei nicht (mehr) da")
            if not tgt.startswith(root + "/") or ".." in tgt.split("/") or not os.path.isdir(tgt):
                raise ValueError("Album-Ordner gibt es nicht")
            if os.path.dirname(tgt) != os.path.dirname(f):
                raise ValueError("Album-Ordner liegt nicht direkt unter dem Ordner der Datei")
            full = _pn(os.path.join(tgt, name))
            if os.path.exists(full):
                res["skipped"] += 1
                raise ValueError("im Album-Ordner gibt es schon eine Datei mit diesem Namen, bleibt liegen")
            fc.rename_any(real, full)
            new_mp = folder_merge._new_mixxx_path(mp, real, root, _relpath(full, root))
            folder_merge._queue_move(check, mp, real, new_mp, full)
            moves.append([real, full, mp, new_mp])
            albums.add(os.path.basename(tgt))
            res["moved"] += 1
        except (ValueError, OSError) as e:
            res["errors"].append(f"{name}: {e}")
    _cache[1] = None                                       # Zahl in der Datenpflege neu rechnen
    if moves:
        _log({"t": int(now()), "moves": moves, "albums": sorted(albums)[:50]})
        log(f"Lose Album-Lieder: {len(moves)} in ihren Album-Ordner verschoben")
    return res


def undo(check, t, log=None):
    """Einen Schritt zuruecknehmen: Dateien zurueck an den alten Platz (nur wo dort nichts liegt), Mixxx bekommt den alten Pfad."""
    import stick_hold
    log = log or (lambda x: None)
    if stick_hold.held():
        raise ValueError("Der Stick ist ausgeworfen")
    p = os.path.join(data_dir(), "protokoll.jsonl")
    try:
        with open(p, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        rows = []
    row = next((r for r in rows if r.get("t") == t and not r.get("undone")), None)
    if row is None:
        raise ValueError("Schritt nicht gefunden oder schon zurueckgenommen")
    root = nfc(check.root() or "").rstrip("/")
    res = {"back": 0, "errors": []}
    for old, new, mp, new_mp in row.get("moves") or []:
        try:
            if not os.path.isfile(new):
                raise ValueError("Datei ist nicht mehr im Album-Ordner")
            if os.path.exists(old):
                raise ValueError("am alten Platz liegt schon eine Datei")
            fc.rename_any(new, old)
            folder_merge._queue_move(check, new_mp, new, folder_merge._new_mixxx_path(new_mp, new, root, _relpath(old, root)), old)
            res["back"] += 1
        except (ValueError, OSError) as e:
            res["errors"].append(f"{os.path.basename(old)}: {e}")
    _cache[1] = None
    row["undone"] = True
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    os.replace(p + ".tmp", p)
    log(f"Lose Album-Lieder: {res['back']} zurueckgelegt")
    return res
