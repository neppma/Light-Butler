"""Ausgeschlossene Ordner im Musikordner (Wunsch 10.11.2026).

Markus traegt im Panel (Einstellungen -> Verbindungen, unter dem Musikordner) Ordner ein, die der Light-Butler nicht kennen soll:
je Zeile ein Ordner, vom Musikordner aus gesehen ("APRES SKI", "KINDERMUSIK/Duplicates") oder ein voller Pfad. Die Liste steht am
Pi in music.json ("excl"), die Bruecke und der Helfer holen sie mit dem Musikordner alle 30 s (MusicServer.apply_conf) und merken
sie in ~/Light-Butler-Daten/ausschluss.json, damit sie gleich nach dem Start gilt, noch bevor der Pi antwortet.

Lieder darin gibt es fuer den Light-Butler nicht: die Ordner-Liste liest sie nicht ein (folder_lib.walk_mp3), Mixxx-Lieder darin
fallen aus der Liste (Forwarder.folder_tick), die Dateipruefung geht nicht hinein (file_check), Vorhoeren liefert sie nicht
(music_serve.Locator). Alles Weitere (Doppelte, Genres, Tag-Vorschlaege, Energie, Tonart, Analyse, Kurven, Cover) arbeitet nur mit
der Liste und sieht sie damit auch nicht. Es wird nie etwas in diese Dateien geschrieben.
Gross/klein zaehlt nicht (der Stick ist FAT), Umlaute zusammengesetzt oder zerlegt gelten gleich.
"""
import json
import os
import threading
import unicodedata

from pfad import norm as _pn
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

MAX_LINES, MAX_LEN = 100, 200
FILE = "ausschluss.json"

_lock = threading.Lock()
_state = {"list": None, "ver": 0}


def data_path():
    return os.path.join(_pfad.daten(), FILE)


def clean(lines):
    """Text (Zeilen) oder Liste -> saubere Liste: ohne Leerzeilen, ohne "/" am Ende, relative ohne "/" am Anfang, ohne "..",
    ohne Doppelte (Gross/klein egal), hoechstens MAX_LINES Eintraege zu MAX_LEN Zeichen."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    if not isinstance(lines, (list, tuple)):
        return []
    out, seen = [], set()
    for x in lines:
        if not isinstance(x, str):
            continue
        x = unicodedata.normalize("NFC", x).strip()
        if not x or "\0" in x or len(x) > MAX_LEN:
            continue
        absolute = x.startswith("/")
        parts = [p.strip() for p in x.split("/") if p.strip()]
        if not parts or any(p in (".", "..") for p in parts):
            continue
        x = ("/" if absolute else "") + "/".join(parts)
        k = x.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
        if len(out) >= MAX_LINES:
            break
    return out


def get():
    """Aktuelle Liste (beim ersten Aufruf aus ausschluss.json)."""
    with _lock:
        if _state["list"] is None:
            try:
                with open(data_path(), encoding="utf-8") as f:
                    d = json.load(f)
                _state["list"] = clean(d.get("excl") if isinstance(d, dict) else [])
            except (OSError, ValueError):
                _state["list"] = []
        return list(_state["list"])


def version():
    get()
    return _state["ver"]


def set_list(lines):
    """Neue Liste vom Pi: merken, wenn sie anders ist (dann zaehlt version() hoch). Liefert die saubere Liste."""
    new = clean(lines)
    old = get()
    if new == old:
        return new
    with _lock:
        _state["list"] = new
        _state["ver"] += 1
    try:
        p = data_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"excl": new}, f, ensure_ascii=False)
        os.replace(tmp, p)
    except OSError:
        pass
    return new


def reset():
    """Nur fuer Tests: Liste neu aus der Datei lesen."""
    with _lock:
        _state["list"] = None


def _key(p):
    return _pn(unicodedata.normalize("NFC", str(p or ""))).rstrip("/").casefold()


def bases(root, lst=None):
    """Volle Pfade der ausgeschlossenen Ordner (verglichen ohne Gross/klein)."""
    lst = get() if lst is None else lst
    root = (root or "").rstrip("/")
    out = []
    for x in lst:
        if x.startswith("/"):
            out.append(_key(x))
        elif root:
            out.append(_key(root + "/" + x))
    return out


def is_excluded(path, root, lst=None, _b=None):
    """Liegt path (Datei oder Ordner) in einem ausgeschlossenen Ordner?"""
    b = bases(root, lst) if _b is None else _b
    if not b or not path:
        return False
    k = _key(path)
    return any(k == x or k.startswith(x + "/") for x in b)


def matcher(root, lst=None):
    """Schnelle Pruefung fuer viele Pfade: f(path) -> True, wenn ausgeschlossen."""
    b = bases(root, lst)
    if not b:
        return lambda p: False
    return lambda p: is_excluded(p, root, _b=b)


def status(root, lst=None):
    """Fuer die Einstellungen: je Eintrag, ob es den Ordner gibt und wie viele MP3s darin liegen (nur die Namen, nichts wird geoeffnet)."""
    lst = get() if lst is None else lst
    rows = []
    for x, full in zip(lst, [x if x.startswith("/") else (root or "").rstrip("/") + "/" + x for x in lst]):
        found = bool(root or x.startswith("/")) and os.path.isdir(full)
        n = 0
        if found:
            for _d, dirs, files in os.walk(full):
                dirs[:] = [y for y in dirs if not y.startswith(".")]
                n += sum(1 for f in files if f.lower().endswith(".mp3") and not f.startswith("."))
        rows.append({"dir": x, "found": found, "mp3": n})
    return rows
