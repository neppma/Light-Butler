"""Import neuer Musik (Wunsch 10.11.2026): der Wartebereich "musik-import" neben dem Musikordner (dort sieht ihn weder Mixxx noch
der Light-Butler) wird auf einer eigenen Seite (/musik/import) angezeigt: vorhoeren, taggen, Ziel im Musikordner vorschlagen und
auf Knopfdruck hinueber verschieben.

Ziel nach dem Muster am Stick: <Oberordner>/Artists/<Interpret>/<Interpret - Titel>.mp3 (Namensregeln aus file_check.name_for).
Gibt es den Interpreten-Ordner schon (Gross/klein, Umlaute egal), nimmt der Vorschlag genau den; bei mehreren Interpreten
("Almklausi, Specktakel") den ersten, wenn es von ihm schon einen Ordner gibt. Lieder, die es in der Bibliothek schon gibt
(Interpret und Titel gleich), bekommen das vorhandene daneben (Laenge, Bitrate), damit Markus behalten, ersetzen oder wegwerfen
kann.

Nie etwas ueberschreiben: liegt am Ziel schon eine Datei, kommt " (2)" dazu. Ersetzen = erst das alte Lied in den Papierkorb, dann
das neue an seinen Platz. Wegwerfen = Papierkorb. Verschoben wird auf demselben Laufwerk (schnell); leere Ordner im Wartebereich
bleiben (sie sind die Vorlage fuer das naechste Mal).
"""
import os
import re
import unicodedata

import file_check as fc
from pfad import under as _under, relpath as _relpath

IMPORT_NAME = "musik-import"
AUDIO = (".mp3",)
MAX_SONGS = 3000
# Einsortieren (Wunsch 10.11.2026): lose Dateien direkt in musik-import kommen auf Knopfdruck in diese Ordner
CAT_SAME, CAT_LEN, CAT_COVER, CAT_NEW, CAT_OTHER = ("gibt es schon", "gibt es schon, andere Länge", "gleicher Titel, anderer Interpret",
                                                    "neu", "nicht MP3")
CATS = (CAT_NEW, CAT_SAME, CAT_LEN, CAT_COVER)       # nur diese vier sind Reiter der Import-Seite (11.11.2026)
KEEP_DIRS = CATS + (CAT_OTHER,)                    # alle anderen Ordner in musik-import (etwa "Archiv") werden einsortiert
JUNK = (".DS_Store", "Thumbs.db", "desktop.ini")   # zaehlen nicht: ein Ordner nur mit diesen gilt als leer
OTHER_AUDIO = (".m4a", ".mp4", ".aac", ".wav", ".flac", ".aif", ".aiff", ".ogg", ".wma", ".opus")
DUR_SAME_S = 4.0                                   # gleiche Fassung: Laenge hoechstens so weit anders
MAX_RIVALS = 6                                     # so viele Lieder mit gleichem Titel (anderer Interpret) zeigt die Import-Seite
FRESH_S = 15.0                                     # eben erst geschrieben (wird vielleicht noch kopiert): diesmal liegen lassen


def import_dir(root):
    """Wartebereich neben dem Musikordner: /Volumes/STICK/musik -> /Volumes/STICK/musik-import."""
    root = (root or "").rstrip("/")
    return os.path.join(os.path.dirname(root), IMPORT_NAME) if root else ""


def _n(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s)


def _title_key(s, artist=""):
    """Titel fuer den Abgleich: ohne Klammern, feat., Zusatz nach " - " und Schreibweise. Vorher weg (Fehlerbericht 11.11.2026:
    "13 - Tom Lang - Mediator" wurde zu "13" und passte auf das Lied "13" eines anderen Interpreten): eine Tracknummer am
    Anfang ("13 - ", "01. ") und der eigene Interpret am Anfang ("Tom Lang - ")."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c)).strip()
    s = re.sub(r"^\d{1,3}\s*(?:[-._)]|\s-)\s*(?=\S)", "", s)          # Tracknummer
    for a in (artist, first_artist(artist) if artist else ""):
        a = unicodedata.normalize("NFKD", str(a or "").lower())
        a = "".join(c for c in a if not unicodedata.combining(c)).strip()
        if a and s.startswith(a + " - "):
            s = s[len(a) + 3:]
            break
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"\s-\s.*$", "", s)
    s = re.sub(r"\b(feat|ft|featuring)\b.*", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def bad_tag(artist, title):
    """Tag offensichtlich unbrauchbar (Fehlerbericht 11.11.2026, Archiv-Lieder "Maximum P2 Dance - 11 - Maximum P2 Dance -
    Maximum P2 Dance"): Titel beginnt mit einer Tracknummer oder ist nach dem Aufraeumen gleich dem Interpreten. Dann erst
    taggen; ein Abgleich mit der Bibliothek waere Zufall."""
    raw = str(title or "").strip()
    if re.match(r"^\d{1,3}\s*(?:[-._)]|\s-)\s*\S", raw):
        return True
    key = _title_key(raw, artist)
    return bool(key) and key == _n(artist)


def _artists(a):
    a = unicodedata.normalize("NFKD", str(a or "").lower())
    a = "".join(c for c in a if not unicodedata.combining(c))
    return {re.sub(r"[^a-z0-9]+", "", x) for x in re.split(r",|&|\bx\b|\bund\b|\bfeat\.?|\bft\.?|/|\bvs\.?", a)} - {""}


def first_artist(a):
    parts = [p.strip() for p in re.split(r",|&|\bfeat\.?\s|\bft\.?\s|\bx\b|\bund\b", str(a or ""), flags=re.I) if p.strip()]
    return parts[0] if parts else str(a or "").strip()


def tops(root):
    """Oberordner im Musikordner (U-MUSIK, OLDIES ...), die einen Unterordner Artists haben."""
    try:
        return sorted((x for x in os.listdir(root) if not x.startswith(".") and os.path.isdir(os.path.join(root, x, "Artists"))), key=str.casefold)
    except OSError:
        return []


def artist_dirs(root, top):
    """{Schluessel: Ordnername} der Interpreten unter <top>/Artists."""
    try:
        names = [x for x in os.listdir(os.path.join(root, top, "Artists")) if not x.startswith(".")]
    except OSError:
        return {}
    return {_n(x): unicodedata.normalize("NFC", x) for x in names}


def suggest(artist, title, top, adirs):
    """Ziel relativ zum Musikordner."""
    a = (artist or "").strip()
    stem = fc.name_for(a or "Unbekannt", title or "Ohne Titel")
    hit = adirs.get(_n(a)) or adirs.get(_n(first_artist(a)))
    d = hit or fc.clean_stem(fc.short_artist(fc.tidy(a))) or "Unbekannt"
    return f"{top}/Artists/{d}/{stem}.mp3"


def lib_index(songs):
    """Bibliothek nach Titel (ohne Klammern, feat., Schreibweise) fuer den Abgleich."""
    byt = {}
    for r in (songs() if callable(songs) else songs) or []:
        t, a = str(r.get("title") or ""), str(r.get("artist") or "")
        if a and t.startswith(a + " - "):
            t = t[len(a) + 3:]
        byt.setdefault(_title_key(t, a), []).append(r)
    return byt


def classify(byt, artist, title, dur):
    """(Ordner, vorhandene Lieder mit gleichem Interpreten) nach den Regeln der Import-Seite."""
    key = _title_key(title, artist)
    if key and key == _n(artist):                         # Titel = Interpret (Albumname in beiden Feldern): nichts zu vergleichen
        return CAT_NEW, []
    cands = byt.get(key, []) if key else []
    same = [c for c in cands if _artists(c.get("artist")) & _artists(artist)]
    if same:
        close = [c for c in same if not dur or abs(float(c.get("duration") or 0) - dur) <= DUR_SAME_S]
        return (CAT_SAME if close else CAT_LEN), same
    if cands:
        return CAT_COVER, []
    return CAT_NEW, []


def ensure_dirs(root):
    """Wartebereich und die vier Kategorien anlegen, wo sie fehlen (Wunsch 11.11.2026). Nur, wenn der Musikordner da ist
    (sonst entstuende bei abgezogenem Stick ein Ordner unter /Volumes auf der Mac-Platte). Rueckgabe: neu angelegte Ordner."""
    base = import_dir(root)
    if not base or not os.path.isdir((root or "").rstrip("/")):
        return []
    import stick_hold
    if stick_hold.held():
        return []
    made = []
    for d in [base] + [os.path.join(base, c) for c in CATS]:
        if not os.path.isdir(d):
            try:
                os.makedirs(d, exist_ok=True)
                made.append(d)
            except OSError:
                pass
    return made


def foreign_dirs(root):
    """Ordner in musik-import, die keine Kategorie sind (etwa "Archiv"): ihr Inhalt wird einsortiert."""
    base = import_dir(root)
    try:
        names = os.listdir(base)
    except OSError:
        return []
    keep = {unicodedata.normalize("NFC", k).casefold() for k in KEEP_DIRS}
    return sorted((os.path.join(base, d) for d in names if not d.startswith(".") and os.path.isdir(os.path.join(base, d))
                   and unicodedata.normalize("NFC", d).casefold() not in keep), key=str.casefold)


def foreign_files(root):
    """Musikdateien in den fremden Ordnern, auch in Unterordnern."""
    out = []
    for top in foreign_dirs(root):
        for d, ds, fs in os.walk(top):
            ds[:] = sorted(x for x in ds if not x.startswith("."))
            out += [os.path.join(d, f) for f in sorted(fs, key=str.casefold)
                    if not f.startswith(".") and f.lower().endswith(AUDIO + OTHER_AUDIO)]
    return out


def remove_empty(top, left=None):
    """Leere Ordner unter top (und top selbst) loeschen, von unten nach oben. Leer = keine Dateien ausser Finder-Resten
    (.DS_Store, ._Name); Ordner mit Bildern oder anderen Dateien bleiben. Rueckgabe: Zahl geloeschter Ordner. left (Liste):
    bekommt (Ordner, Grund) fuer leere Ordner, die sich nicht loeschen liessen."""
    n = 0
    for d, ds, fs in os.walk(top, topdown=False):
        try:
            names = os.listdir(d)
        except OSError:
            continue
        if any(not (x in JUNK or x.startswith("._")) for x in names):
            continue
        try:
            for x in names:
                os.remove(os.path.join(d, x))
            os.rmdir(d)
            n += 1
        except OSError as e:
            if left is not None:
                left.append((d, e.strerror or str(e)))
    return n


def clean_foreign(root, tries=3, wait_s=1.0, sleep=None):
    """Leere fremde Ordner loeschen, bei Fehlschlag noch einmal (Fehlerbericht 11.11.2026: 8 leere Archiv-Ordner blieben
    stehen; auf dem exFAT-Stick wandern die Begleitdateien ._Name einen Augenblick nach der Datei mit, das Loeschen kam zu
    frueh). Rueckgabe (geloescht, [(Ordner, Grund)] die stehen blieben)."""
    import time
    sleep = sleep or time.sleep
    n, left = 0, []
    for k in range(max(1, tries)):
        left = []
        for top in foreign_dirs(root):
            if any(True for _ in _audio_under(top)):
                continue                                  # da liegt noch Musik: erst einsortieren
            n += remove_empty(top, left)
        if not left:
            break
        if k < tries - 1:
            sleep(wait_s)
    return n, left


def _audio_under(top):
    for d, ds, fs in os.walk(top):
        ds[:] = [x for x in ds if not x.startswith(".")]
        for f in fs:
            if not f.startswith(".") and f.lower().endswith(AUDIO + OTHER_AUDIO):
                yield os.path.join(d, f)


def loose_files(root):
    """Musikdateien direkt im Wartebereich (ohne Unterordner)."""
    base = import_dir(root)
    try:
        names = os.listdir(base)
    except OSError:
        return []
    return sorted((os.path.join(base, f) for f in names if not f.startswith(".") and f.lower().endswith(AUDIO + OTHER_AUDIO)
                   and os.path.isfile(os.path.join(base, f))), key=str.casefold)


def sort_loose(root, songs=None, read=None, now=None, log=None):
    """Lose Dateien im Wartebereich und alle Dateien aus fremden Ordnern (etwa "Archiv", auch Unterordner; 11.11.2026) mit der
    Bibliothek abgleichen und in die Ordner der Kategorien verschieben (nie ueberschreiben: " (2)"). Eben erst geschriebene
    Dateien (FRESH_S) bleiben diesmal liegen. Danach leere fremde Ordner loeschen. Rueckgabe {Ordner: Zahl, "wait": n,
    "removed": Ordner, "errors": [...]}."""
    import time
    log = log or (lambda t: None)
    now = time.time() if now is None else now
    base = import_dir(root)
    import stick_hold
    if stick_hold.held():
        raise ValueError("Der Stick ist ausgeworfen")
    ensure_dirs(root)
    if not base or not os.path.isdir(base):
        raise ValueError("Wartebereich musik-import nicht gefunden")
    if read is None:
        import folder_lib
        read = folder_lib.read_mp3
    byt = lib_index(songs)
    res = {"moved": {}, "wait": 0, "errors": [], "removed": 0}
    foreign = foreign_dirs(root)
    for p in loose_files(root) + foreign_files(root):
        f = os.path.basename(p)
        try:
            if now - os.path.getmtime(p) < FRESH_S:
                res["wait"] += 1
                continue
            if not f.lower().endswith(AUDIO):
                cat = CAT_OTHER
            else:
                try:
                    info = read(p) or {}
                except (OSError, ValueError, IndexError):
                    info = {}
                stem = os.path.splitext(f)[0]
                a, t = info.get("artist") or "", info.get("title") or ""
                if not t:                                         # ohne Tag: "Interpret - Titel.mp3"
                    a, _, t = stem.partition(" - ") if " - " in stem else ("", "", stem)
                cat = classify(byt, a, t, float(info.get("duration") or 0))[0]
            d = os.path.join(base, cat)
            os.makedirs(d, exist_ok=True)
            dst = free_target(os.path.join(d, f))
            fc.rename_any(p, dst)
            res["moved"][cat] = res["moved"].get(cat, 0) + 1
        except OSError as e:
            res["errors"].append(f"{f}: {e.strerror or e}")
    del foreign                                            # leere fremde Ordner weg (Wunsch 11.11.2026), mit Wiederholung
    res["removed"], left = clean_foreign(root)
    res["left"] = [f"{_relpath(d, base)}: {why}" for d, why in left[:5]]
    if res["moved"]:
        log("Import einsortiert: " + ", ".join(f"{n} {k}" for k, n in res["moved"].items()))
    return res


def scan(root, songs=None, top="U-MUSIK", read=None):
    """Alle MP3s im Wartebereich mit Tags, Vorschlag und vorhandenem Gegenstueck.
    songs() -> Bibliothek (Dicts mit path, artist, title, duration, bitrate). read(p) -> Tags (Standard: folder_lib.read_mp3)."""
    base = import_dir(root)
    out = {"dir": base, "root": (root or "").rstrip("/"), "top": top, "tops": tops(root) if root else [], "folders": [], "n": 0}
    import stick_hold
    if stick_hold.held():
        out["held"] = True
        return out
    out["made"] = [os.path.basename(d) for d in ensure_dirs(root)]   # fehlende Ordner anlegen (Wunsch 11.11.2026)
    if base and os.path.isdir(base):                       # leere fremde Ordner (Reste vom letzten Einsortieren) gleich mit weg
        out["cleaned"] = clean_foreign(root, tries=1)[0]
    if not base or not os.path.isdir(base):
        out["missing"] = True
        return out
    if read is None:
        import folder_lib
        read = folder_lib.read_mp3
    import tag_edit
    byt = lib_index(songs)
    out["loose"] = len(loose_files(root))                 # lose Dateien: erst einsortieren (Knopf), sie erscheinen in keinem Reiter
    out["foreign"] = len(foreign_files(root))             # Dateien in fremden Ordnern (Archiv ...): ebenso
    out["foreign_dirs"] = [os.path.basename(d) for d in foreign_dirs(root)]
    try:                                                   # andere Formate: nur zaehlen (erst in MP3 umwandeln)
        out["other_n"] = sum(1 for f in os.listdir(os.path.join(base, CAT_OTHER)) if not f.startswith("."))
    except OSError:
        out["other_n"] = 0
    adirs = artist_dirs(root, top)
    groups = {}
    n = 0
    try:                                                   # Treffer der Klang-Pruefung (klang_fp, 11.11.2026)
        import klang_fp
        kres = klang_fp.load_results()
    except ImportError:
        klang_fp, kres = None, {}
    cats = {unicodedata.normalize("NFC", c).casefold(): c for c in CATS}
    for d, ds, fs in os.walk(base):
        ds[:] = sorted(x for x in ds if not x.startswith("."))
        rel_dir = os.path.relpath(d, base)
        if rel_dir == ".":
            ds[:] = [x for x in ds if unicodedata.normalize("NFC", x).casefold() in cats]   # nur die vier Kategorien sind Reiter
            continue
        cat = cats[unicodedata.normalize("NFC", rel_dir.split(os.sep)[0]).casefold()]
        for f in sorted(fs, key=str.casefold):
            if f.startswith(".") or not f.lower().endswith(AUDIO) or n >= MAX_SONGS:
                continue
            p = os.path.join(d, f)
            try:
                info = read(p) or {}
            except (OSError, ValueError, IndexError):
                info = {}
            try:
                grp = tag_edit.read_tags(p)["fields"].get("grouping", "")
            except Exception:                                  # noqa: BLE001  Tag unlesbar: Gruppe leer
                grp = ""
            a, t = info.get("artist") or "", info.get("title") or ""
            dur = float(info.get("duration") or 0)
            same = classify(byt, a, t, dur)[1]
            dup = None
            if same:
                c = min(same, key=lambda c: abs(float(c.get("duration") or 0) - dur))
                dup = {"path": c.get("path") or "", "dur": round(float(c.get("duration") or 0)), "kbps": int(c.get("bitrate") or 0),
                       "artist": c.get("artist") or "", "title": c.get("title") or ""}
            rec = {"path": unicodedata.normalize("NFC", p), "folder": cat,
                   "file": unicodedata.normalize("NFC", f), "artist": a, "title": t, "album": info.get("album") or "", "genre": info.get("genre") or "",
                   "grp": grp, "dur": round(dur), "kbps": int(info.get("bitrate") or 0), "size": os.path.getsize(p),
                   "target": suggest(a, t, top, adirs), "dup": dup, "badtag": bad_tag(a, t)}
            rec["exists"] = os.path.exists(os.path.join(root, rec["target"]))
            ke = kres.get(p) if kres else None
            if ke and ke.get("dur"):                          # echte Laenge aus der Klang-Pruefung (VBR ohne Kopf: Schaetzung falsch)
                rec["dur"] = round(float(ke["dur"]))
            kh = klang_fp.hit_for(p, kres) if klang_fp is not None and kres else None
            if kh:                                             # gleicher Klang: das vorhandene Lied wie bei "gibt es schon"
                rec["klang"] = kh["score"]
                if rec["dup"] is None:
                    rec["dup"] = {k: kh.get(k) for k in ("path", "dur", "kbps", "artist", "title")}
            if not same and _title_key(t, a):                  # gleicher Titel, anderer Interpret: die vorhandenen zeigen (11.11.2026)
                riv = sorted(byt.get(_title_key(t, a), []), key=lambda c: abs(float(c.get("duration") or 0) - dur))[:MAX_RIVALS]
                rec["rivals"] = [{"path": c.get("path") or "", "dur": round(float(c.get("duration") or 0)), "kbps": int(c.get("bitrate") or 0),
                                  "artist": c.get("artist") or "", "title": c.get("title") or ""} for c in riv]
            groups.setdefault(rec["folder"], []).append(rec)
            n += 1
    out["folders"] = [{"name": c, "songs": groups[c]} for c in CATS if groups.get(c)]   # feste Reihenfolge: neu zuerst
    out["n"] = n
    return out


def count(root):
    """Zahl der Musikdateien im Wartebereich (nur Namen, fuer die Datenpflege). Auch WAV, M4A und andere (Fehlerbericht
    12.11.2026: eine lose WAV lag im Wartebereich, die Datenpflege zeigte 0)."""
    base = import_dir(root)
    n = 0
    if base and os.path.isdir(base):
        for _d, ds, fs in os.walk(base):
            ds[:] = [x for x in ds if not x.startswith(".")]
            n += sum(1 for f in fs if f.lower().endswith(AUDIO + OTHER_AUDIO) and not f.startswith("."))
    return n


def _check_target(root, rel):
    rel = unicodedata.normalize("NFC", str(rel or "")).strip().strip("/")
    parts = [x for x in rel.split("/") if x]
    if len(parts) < 2 or any(x in (".", "..") or x.startswith(".") for x in parts) or not rel.lower().endswith(".mp3"):
        raise ValueError("Ziel ungueltig: " + rel[:80])
    if any(fc.clean_part(x) != x for x in parts):
        raise ValueError("Ziel mit verbotenen Zeichen: " + rel[:80])
    full = os.path.join(root, *parts)
    if not _under(os.path.realpath(full), os.path.realpath(root)):
        raise ValueError("Ziel ausserhalb des Musikordners")
    return full


def free_target(full):
    """Nie ueberschreiben: " (2)", " (3)" ... anhaengen."""
    if not os.path.exists(full):
        return full
    stem, ext = os.path.splitext(full)
    k = 2
    while os.path.exists(f"{stem} ({k}){ext}"):
        k += 1
    return f"{stem} ({k}){ext}"


def stamp_import(path, today=None, write=None, read=None):
    """Importdatum (TXXX Importdatum, "2026-11-11") in die MP3, wenn noch keins drinsteht (Wunsch 11.11.2026: die zuletzt
    importierten Lieder finden). Fehler stoeren den Import nie."""
    import time as _t
    if not str(path).lower().endswith(".mp3"):
        return False
    try:
        if write is None or read is None:
            import tag_edit
            write, read = write or tag_edit.write_tags, read or (lambda p: tag_edit.read_tags(p)["fields"])
        if (read(path) or {}).get("imported"):
            return False
        write(path, {"imported": today or _t.strftime("%Y-%m-%d")})
        return True
    except Exception:                                        # noqa: BLE001
        return False


def apply(root, items, locate=None, trash=fc.to_trash_many, log=None, stamp=stamp_import):
    """items: [{"path": Datei im Wartebereich, "do": "move"|"replace"|"trash", "target": Ziel relativ zum Musikordner}].
    locate(p) -> Datei am Mac fuer das vorhandene Lied (nur fuer "replace"). Rueckgabe {moved, trashed, replaced, errors, done: [...]}."""
    log = log or (lambda t: None)
    root = (root or "").rstrip("/")
    base = import_dir(root)
    import stick_hold
    if stick_hold.held():
        raise ValueError("Der Stick ist ausgeworfen")
    if not root or not os.path.isdir(root):
        raise ValueError("Musikordner nicht gefunden (Stick eingesteckt?)")
    res = {"moved": 0, "trashed": 0, "replaced": 0, "errors": [], "done": []}
    to_trash = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        src = unicodedata.normalize("NFC", str(it.get("path") or ""))
        try:
            if not src or not _under(os.path.realpath(src), os.path.realpath(base)) or not os.path.isfile(fc.nfc(src)) and not os.path.isfile(src):
                raise ValueError("nicht im Wartebereich")
            do = it.get("do")
            if do == "trash":
                to_trash.append(src)
                res["done"].append({"path": src, "do": "trash"})
                continue
            if do not in ("move", "replace"):
                raise ValueError("unbekannte Aktion")
            full = _check_target(root, it.get("target"))
            old = None
            if do == "replace":
                dp = str(it.get("dup") or "")
                old = locate(dp) if (locate and dp) else None
                if not old:
                    raise ValueError("vorhandenes Lied nicht gefunden")
                if trash([old]):
                    raise ValueError("altes Lied liess sich nicht in den Papierkorb legen")
                res["replaced"] += 1
            full = free_target(full)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if stamp is not None:
                stamp(src)                                    # Importdatum, solange die Datei noch im Wartebereich liegt
            fc.rename_any(src, full)
            res["moved"] += 1
            res["done"].append({"path": src, "do": do, "to": _relpath(full, root), "old": old})
            log(f"Import: {os.path.basename(src)} -> {_relpath(full, root)}")
        except (ValueError, OSError) as e:
            res["errors"].append(f"{os.path.basename(src)}: {e}")
    if to_trash:
        if trash(to_trash):
            res["errors"].append("Papierkorb: nicht alle Dateien verschoben")
        res["trashed"] = sum(1 for p in to_trash if not os.path.exists(p))
    return res


# ---- Ordner "nicht MP3": ansehen und in MP3 umwandeln (Wunsch 12.11.2026) ----
# Die MP3 entsteht neben dem Original (convert_mp3, 320 kbit/s, nie ueberschreiben) und kommt danach lose in den Wartebereich,
# dort sortiert "Einsortieren" sie wie jede andere neue Datei. Ist die MP3 da, kommt das Original in den Papierkorb (Wunsch
# 12.11.2026: sonst stand das Lied zweimal im Wartebereich); scheitert die Umwandlung, bleibt es.
_other_jobs = None


def other_dir(root):
    base = import_dir(root)
    return os.path.join(base, CAT_OTHER) if base else ""


def other_path(root, name):
    """Datei im Ordner "nicht MP3" zu einem Namen (nur Namen, kein Pfad von aussen), sonst ValueError."""
    name = str(name or "")
    if not name or name != os.path.basename(name) or name.startswith("."):
        raise ValueError("Dateiname passt nicht")
    p = os.path.join(other_dir(root), name)
    if not os.path.isfile(p):
        raise ValueError("Datei nicht gefunden: " + name)
    return p


def other_jobs(root_fn, log=None, convert_fn=None, trash=None):
    """Umwandlungen fuer den Ordner "nicht MP3", eine nach der anderen; fertige MP3 lose in den Wartebereich."""
    global _other_jobs
    if _other_jobs is None:
        import convert_mp3 as cm

        def done(src, dst):
            base = import_dir(root_fn())
            if base and os.path.isfile(dst) and os.path.getsize(dst) > 0:
                fc.rename_any(dst, free_target(os.path.join(base, os.path.basename(dst))))
                if os.path.isfile(src) and (trash or fc.to_trash_many)([src]):
                    (log or (lambda t: None))(f"Original nicht in den Papierkorb: {src}")
        _other_jobs = cm.Jobs(log=log, done=done, convert_fn=convert_fn or cm.convert)
    return _other_jobs


def other_files(root, jobs=None):
    """[{name, size, ext, can, state, error}] im Ordner "nicht MP3"."""
    import convert_mp3 as cm
    d, out = other_dir(root), []
    try:
        names = sorted(os.listdir(d), key=str.casefold) if d else []
    except OSError:
        names = []
    for f in names:
        p = os.path.join(d, f)
        if f.startswith(".") or not os.path.isfile(p):
            continue
        st = jobs.status(p) if jobs is not None else {}
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        out.append({"name": f, "size": size, "ext": os.path.splitext(f)[1].lower().lstrip("."), "can": cm.can_convert(p),
                    "state": st.get("state", ""), "error": st.get("error", ""), "out": st.get("name", "")})
    return out


def other_convert(root, names, jobs):
    """Umwandlung starten; Rueckgabe {name: Stand}."""
    import convert_mp3 as cm
    import stick_hold
    if stick_hold.held():
        raise ValueError("Der Stick ist ausgeworfen")
    if not cm.find_ffmpeg():
        raise ValueError("ffmpeg fehlt am Mac (Terminal: brew install ffmpeg)")
    res = {}
    for n in list(names)[:200]:
        p = other_path(root, n)
        if not cm.can_convert(p):
            res[n] = {"state": "err", "error": "diese Dateiart wird nicht umgewandelt"}
            continue
        res[n] = jobs.start(p, p)
    return res
