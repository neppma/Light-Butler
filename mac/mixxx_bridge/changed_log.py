"""
changed_log.py - welche MP3s der Light-Butler geaendert hat (Wunsch von Markus, 08.11.2026).

Mixxx liest geaenderte Tags erst nach "Metadaten aus Datei importieren" neu ein; alle 9000 Lieder zu markieren dauerte zwei
Stunden. Darum merkt sich id3_tags.write jede Datei, die es schreibt (Tag-Editor, Auto-Tagger, Titel bereinigen, Ordnerbilder,
erzeugte Cover, geschaetzte Tonart/Energie). Daraus entsteht auf Knopfdruck die Playlist "Light-Butler geaenderte Tags" fuer
Mixxx: importieren, dort alle markieren, Metadaten importieren, fertig. Danach wird die Liste geleert.

Dazu rueckwirkend (auch vor diesem Merken und von anderen Programmen): Mixxx (ab 2.4) traegt je Lied ein, wann es die Tags
zuletzt gelesen hat (library.source_synchronized_ms). Ist die Datei neuer, fehlt Mixxx die Aenderung (mixxx_newer). Lieder, die
Mixxx nie abgeglichen hat, lassen sich so nicht erkennen.

Ablage: ~/Light-Butler-Daten/geaendert/dateien.jsonl (eine Zeile je Schreibvorgang: [Pfad, Zeit]), gemeinsam fuer Mixxx-App und Helfer.
"""
import json
import os
import sqlite3
import threading
import time
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

_lock = threading.Lock()
NAME = "Light-Butler geaenderte Tags"


def log_path():
    return os.path.join(_pfad.daten(), "geaendert", "dateien.jsonl")


TEMP_DIRS = ("/private/tmp/", "/tmp/", "/private/var/folders/", "/var/folders/")


def is_temp(path):
    """Datei in einem Zwischenordner (Tests, Probedateien): gehoert nie in die Liste fuer Mixxx (Fehlerbericht 11.11.2026:
    eine Probedatei aus einem Testlauf landete ueber "geaenderte Tags" in Mixxx und in "LB zu analysieren")."""
    import tempfile
    p = os.path.realpath(str(path or ""))
    roots = TEMP_DIRS + (os.path.realpath(tempfile.gettempdir()).rstrip("/") + "/",)
    return any(p.startswith(r) for r in roots) or any(str(path or "").startswith(r) for r in roots)


def note(path):
    """Datei als geaendert merken. Nie einen Fehler werfen: das Schreiben der Tags ist wichtiger."""
    if is_temp(path) and not os.environ.get("S2L_DATA"):   # Tests mit eigener Ablage (S2L_DATA) duerfen, die echte Liste nie
        return
    try:
        p = log_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with _lock, open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps([os.path.abspath(path), time.time()], ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        pass


def forget_under(folder):
    """Eintraege unter folder vergessen (Import-Seite: Dateien aus dem Wartebereich sind jetzt woanders, Mixxx liest sie neu ein)."""
    base = os.path.abspath(folder).rstrip("/") + "/"
    p = log_path()
    with _lock:
        try:
            with open(p, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            return 0
        keep = []
        for ln in lines:
            try:
                if str(json.loads(ln)[0]).startswith(base):
                    continue
            except (ValueError, IndexError, TypeError):
                pass
            keep.append(ln)
        if len(keep) != len(lines):
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                f.write("".join(x + "\n" for x in keep))
            os.replace(p + ".tmp", p)
        return len(lines) - len(keep)


def files():
    """{Pfad: letzte Zeit} der gemerkten Dateien, die es noch gibt (geloeschte oder umbenannte fallen heraus)."""
    out = {}
    try:
        with open(log_path(), encoding="utf-8") as f:
            for line in f:
                try:
                    p, t = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(p, str):
                    out[p] = max(float(t or 0), out.get(p, 0.0))
    except OSError:
        return {}
    return {p: t for p, t in out.items() if os.path.isfile(p)}


def db_path():
    """Kopie der Mixxx-Datenbank, die launch.sh jede Minute macht (lesbar ohne Zugriff auf den Container)."""
    base = _pfad.daten()
    for n in ("mixxxdb.live.sqlite", "mixxxdb.sqlite"):
        if os.path.isfile(os.path.join(base, n)):
            return os.path.join(base, n)
    return ""


def reset_path():
    return os.path.join(os.path.dirname(log_path()), "zurueckgesetzt.json")


def reset_time():
    """Zeitpunkt von "Zuruecksetzen": Dateien, die davor geaendert wurden, zaehlen nicht mehr (auch nicht ueber Mixxx)."""
    try:
        with open(reset_path(), encoding="utf-8") as f:
            return float(json.load(f).get("t") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0.0


def reset():
    """Alles auf 0 (Wunsch 08.11.2026): eigene Liste leeren und fruehere Aenderungen, die Mixxx nicht kennt, nicht mehr zaehlen."""
    t = time.time()
    try:
        os.makedirs(os.path.dirname(reset_path()), exist_ok=True)
        with open(reset_path(), "w", encoding="utf-8") as f:
            json.dump({"t": t}, f)
    except OSError:
        pass
    clear()
    _cache.update(t=0.0, files={})
    return t


def mixxx_newer(db=None, slack_ms=2000):
    """{Pfad: Aenderungszeit} der Dateien, die neuer sind als der letzte Abgleich in Mixxx. Nur lesen."""
    db = db if db is not None else db_path()
    out = {}
    if not db:
        return out
    try:
        con = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT t.location, l.source_synchronized_ms FROM library l JOIN track_locations t ON l.location = t.id "
                               "WHERE l.mixxx_deleted = 0 AND t.fs_deleted = 0 AND l.source_synchronized_ms > 0").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return out
    since = reset_time()
    for p, ms in rows:
        try:
            m = os.path.getmtime(p)
        except (OSError, TypeError):
            continue
        if m * 1000 > ms + slack_ms and m > since:
            out[p] = m
    return out


_cache = {"t": 0.0, "files": {}, "busy": False}
CACHE_S = 600.0


def _refresh():
    try:
        fs = mixxx_newer()
    except Exception:                       # noqa: BLE001
        fs = {}
    _cache.update(t=time.time(), files=fs, busy=False)


def newer_cached(wait=False):
    """mixxx_newer, hoechstens alle 10 Minuten neu (9000 Dateien am Stick); sonst im Hintergrund nachrechnen."""
    if wait:
        _refresh()
    elif time.time() - _cache["t"] > CACHE_S and not _cache["busy"]:
        _cache["busy"] = True
        threading.Thread(target=_refresh, name="geaendert-mixxx", daemon=True).start()
    return dict(_cache["files"])


def all_files(wait=False):
    """Eigene Aenderungen und alles, was neuer ist als der Abgleich in Mixxx."""
    fs = newer_cached(wait)
    for p, t in files().items():
        fs[p] = max(t, fs.get(p, 0.0))
    return fs


def status():
    fs = all_files()
    return {"n": len(fs), "since": min(fs.values()) if fs else 0}


def clear(before=None):
    """Liste leeren; before = nur Eintraege bis zu dieser Zeit (was waehrenddessen dazukam, bleibt). Mit before ("Fertig, Liste
    leeren" nach dem Export, Fehlerbericht 09.11.2026: die Zahl blieb bei 336, weil auch alles zaehlt, was neuer ist als der
    Abgleich in Mixxx): was bis dahin geaendert war, zaehlt auch ueber Mixxx nicht mehr, wie bei "Zuruecksetzen"."""
    if before is not None and before > reset_time():
        try:
            os.makedirs(os.path.dirname(reset_path()), exist_ok=True)
            with open(reset_path(), "w", encoding="utf-8") as f:
                json.dump({"t": float(before)}, f)
        except OSError:
            pass
        _cache["files"] = {p: t for p, t in _cache["files"].items() if t > before}
    fs = files()
    keep = {p: t for p, t in fs.items() if before is not None and t > before}
    p = log_path()
    try:
        with _lock:
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for k, t in sorted(keep.items(), key=lambda x: x[1]):
                    f.write(json.dumps([k, t], ensure_ascii=False) + "\n")
            os.replace(tmp, p)
    except OSError:
        pass
    _cache["t"] = 0.0                          # Mixxx hat inzwischen eingelesen: beim naechsten Mal neu vergleichen
    return len(keep)


def disk_form(path, cache=None):
    """Pfad in der Schreibweise, die Mixxx selbst verwendet: Umlaute als ein Zeichen (NFC). Mixxx vergleicht Byte fuer Byte; eine
    Playlist mit anderer Schreibweise legte jedes Lied mit Umlaut ein zweites Mal an (Fehlerbericht 11.11.2026, 83 Lieder).
    Fehlerbericht 12.11.2026: die erste Fassung nahm die Schreibweise vom Stick (u + Punkte) und erzeugte genau diese Zwillinge;
    Mixxx liest auch solche Dateien als NFC ein. (Name bleibt fuer die Aufrufer; cache wird nicht mehr gebraucht.)"""
    import unicodedata
    return unicodedata.normalize("NFC", str(path))


def write_m3u(folder):
    """Playlist mit allen gemerkten Dateien (aelteste zuerst). Rueckgabe (Datei, Zahl, Zeit des Standes)."""
    now = time.time()
    fs = all_files(wait=True)
    if not fs:
        raise ValueError("Keine geaenderte MP3: Mixxx kennt alle Tags.")
    lines = ["#EXTM3U", "#PLAYLIST:" + NAME]
    cache = {}
    for p, _t in sorted(fs.items(), key=lambda x: x[1]):
        lines += ["#EXTINF:-1," + os.path.splitext(os.path.basename(p))[0].replace("\n", " "), disk_form(p, cache)]
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, NAME + ".m3u8")
    with open(out + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(out + ".tmp", out)
    return out, len(fs), now
