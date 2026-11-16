"""
cd_assist.py - CD-Assistent (Wunsch von Markus, 09.11.2026): eine Trackliste aus dem Internet einfuegen, der Light-Butler ordnet
sie den Dateien eines Ordners zu, schreibt Tags, benennt nach den Namensregeln um und verschiebt auf Wunsch in einen neuen
Ordner unter Compilations. Das Zerlegen der Liste und die Vorschau macht die Seite /musik/cd (cd.js) im Browser; hier am Mac:
  - folder(): die Lieder eines Ordners (Pfad wie Mixxx, Tracknummer, Laenge, Tags der Datei),
  - apply(): einen fertigen, im Browser geprueften Plan ausfuehren.
Wie bei Dateien pruefen: nie ueberschreiben, kein Dateiname doppelt im Musikordner, Musik und Fingerabdruck bleiben gleich, jede
Umbenennung kommt in die Warteschlange fuer Mixxx (offen.tsv, beim naechsten Start der App "Light-Butler Mixxx", Hotcues bleiben).
"""
import os
import re

import file_check as fc
from pfad import norm as _pn

MAX_ITEMS = 99
SCAN_WAIT_S = 240.0     # so lange wartet "Schreiben" hoechstens auf die Dateipruefung
FIELDS = ("artist", "title", "album", "albumartist", "year", "track", "genre")


def _rel(root, f):
    root, f = _pn(root or "").rstrip("/"), _pn(f)
    return f[len(root) + 1:] if root and f.startswith(root + "/") else f


def _disc(f):
    """CD-Nummer aus dem Tag (TPOS "2/2" -> 2), sonst aus dem Ordnernamen ("Disc 2", "CD2"), sonst 0."""
    try:
        import id3_tags
        v = fc.track_no(id3_tags.read_text(f, b"TPOS") or "") if f.lower().endswith(".mp3") else 0
    except Exception:                                        # noqa: BLE001
        v = 0
    if v:
        return v
    m = re.search(r"(?:^|[\s/_-])(?:disc|disk|cd)\s*(\d{1,2})$", os.path.basename(os.path.dirname(f)), re.I)
    return int(m.group(1)) if m else 0


def _disc_tag(f):
    """CD-Nummer steht im Tag (TPOS)."""
    try:
        import id3_tags
        return bool(f.lower().endswith(".mp3") and (id3_tags.read_text(f, b"TPOS") or "").strip())
    except Exception:                                        # noqa: BLE001
        return False


def _pending():
    """Vorgemerkte Umbenennungen fuer Mixxx (offen.tsv): alter Pfad -> neuester Pfad (Ketten aufgeloest)."""
    m = {}
    try:
        with open(fc.FileCheck.queue_path(), encoding="utf-8") as fh:
            for line in fh:
                a, _, b = line.rstrip("\n").partition("\t")
                if a and b:
                    m[a] = b
    except OSError:
        return {}
    for a in list(m):
        b, seen = m[a], {a}
        while b in m and b not in seen:
            seen.add(b)
            b = m[b]
        m[a] = b
    return m


def _where(check, p, pend):
    """Datei zum Mixxx-Pfad p am Stick. Fehlerbericht 09.11.2026: nach "Ordner umbenennen" zeigte die Seite 0 Lieder, weil Mixxx
    bis zum naechsten Start der App noch den alten Pfad kennt; dann gilt die vorgemerkte Umbenennung."""
    f = check.locate(p) if p else None
    if f and os.path.exists(f):
        return f
    q = pend.get(p)
    if q:
        g = check.locate(q) or q
        if os.path.exists(g):
            return g
    return f


def _item(root, p, f, r, elsewhere=False):
    t = fc.file_tags(f) if f.lower().endswith(".mp3") else {}
    return {"path": p, "rel": _rel(root, f), "name": os.path.basename(f), "dur": round(float(r.get("duration") or 0), 1),
            "track": fc.track_no((t or {}).get("track") or r.get("tracknumber")), "artist": (t or {}).get("artist") or r.get("artist") or "",
            "title": (t or {}).get("title") or r.get("title") or "", "album": (t or {}).get("album") or r.get("album") or "",
            "mp3": f.lower().endswith(".mp3"), "elsewhere": elsewhere, "disc": _disc(f)}


def folder(check, d, album=None):
    """Lieder im Ordner d (relativ zum Musikordner oder ganzer Pfad), sortiert nach Tracknummer, sonst Dateiname. Dazu Lieder in
    anderen Ordnern mit demselben Album im Tag (Wunsch 09.11.2026: drei Tracks der CD lagen bei ihren Interpreten); album = Name,
    sonst das haeufigste Album im Ordner."""
    root = _pn(check.root() or "").rstrip("/")
    want = fc.nfc(os.path.normpath(d if d.startswith("/") or os.path.isabs(d) else os.path.join(root, d)))
    out, rest = [], []
    pend = _pending()
    for r in check.songs() or []:
        p = r.get("path") or ""
        f = _where(check, p, pend) if p else None
        if not f:
            continue
        if fc.nfc(os.path.dirname(f)) == want:
            out.append(_item(root, p, f, r))
        elif r.get("album"):
            rest.append((p, f, r))
    if album is None:
        cnt = {}
        for x in out:
            if x["album"]:
                cnt[fc.loose(x["album"])] = cnt.get(fc.loose(x["album"]), 0) + 1
        ak = max(cnt, key=cnt.get) if cnt else ""
    else:
        ak = fc.loose(album)
    if ak and len(ak) >= 4:
        out += [_item(root, p, f, r, True) for p, f, r in rest if fc.loose(r.get("album")) == ak][:MAX_ITEMS]
    out.sort(key=lambda x: (x["track"] or 999, x["elsewhere"], x["name"].lower()))
    return {"dir": _rel(root, want), "root": root, "files": out}


def dirs(check):
    """Alle Ordner mit Liedern der Bibliothek (relativ, sortiert), mit Zahl der Lieder: Auswahl auf der Seite."""
    root = _pn(check.root() or "").rstrip("/")
    n = {}
    pend = _pending()
    for r in check.songs() or []:
        f = _where(check, r.get("path"), pend) if r.get("path") else None
        if f and _pn(f).startswith(root + "/"):
            d = _rel(root, fc.nfc(os.path.dirname(f)))
            n[d] = n.get(d, 0) + 1
    return {"root": root, "dirs": [[d, k] for d, k in sorted(n.items(), key=lambda x: x[0].lower())]}


def target_dir(root, top, album):
    """Neuer Ordner fuer eine Sammel-CD: <oberster Ordner>/Compilations/<Album> (z. B. U-MUSIK/Compilations/...)."""
    top = str(top or "").strip("/").split("/")[0]
    if top in ("", ".", ".."):
        top = ""
    name = fc.clean_stem("".join(fc.CHAR_MAP.get(c, c) for c in fc.nfc(album)))
    if not top or not name:
        raise ValueError("Für den neuen Ordner fehlt das Album")
    return os.path.join(root, top, "Compilations", name)


def apply(check, plan, write=None, log=None):
    """plan = {"dir", "move": bool, "album", "albumartist", "year", "genre", "items": [{"path", "artist", "title", "track", "total"}]}.
    Schreibt die Tags, benennt um und verschiebt. Rueckgabe {"done": [{"path", "old_path", "new_path", "name"}], "errors": [...],
    "dir": neuer Ordner}."""
    import tag_edit
    write = write or tag_edit.write_tags
    if check.state != "ready":
        # Fehlerbericht 09.11.2026: nach einem Neustart des Helfers war die Pruefung weg, die Seite meldete einen Fehler und man
        # haette die Eingaben verloren. Jetzt pruefen wir hier selbst und schreiben danach (ein bis zwei Minuten).
        check.scan()
        t = check.thread
        if t is not None:
            t.join(SCAN_WAIT_S)
        if check.state != "ready":
            raise ValueError("Die Dateiprüfung dauert noch (" + str(check.done) + " Dateien angesehen). Bitte gleich noch einmal „Angehakte schreiben“ drücken, die Eingaben bleiben.")
    log = log or (lambda t: None)
    root = _pn(check.root() or "").rstrip("/")
    items = [x for x in (plan.get("items") or []) if isinstance(x, dict)][:MAX_ITEMS]
    if not items:
        raise ValueError("Nichts zugeordnet")
    # Lieder aus der ganzen Bibliothek (Wunsch 09.11.2026: die Lieder einer CD liegen oft verstreut), nur bekannte Pfade
    files = {r.get("path"): r for r in check.songs() or [] if r.get("path")}
    top = str(plan.get("top") or plan.get("dir") or "")
    dest = target_dir(root, top, str(plan.get("album") or "")) if plan.get("move") else None
    src_dirs = set()
    taken = {}
    with check.lock:
        for k, v in (check.index or {}).items():
            taken[k] = [fc.nfc(q) for q in v]
    done, errors = [], []
    pend = _pending()
    for it in items:
        p = str(it.get("path") or "")
        if p not in files:
            errors.append({"path": p, "error": "nicht in der Bibliothek"})
            continue
        f = _where(check, p, pend)
        if not f or not os.path.isfile(f):
            errors.append({"path": p, "error": "Datei nicht gefunden (Stick eingesteckt?)"})
            continue
        # Tags behalten "?" und ":" (Fehlerbericht 09.11.2026: "Seid ihr mit mir-"), nur der Dateiname (name_for) ersetzt sie
        artist, title = (re.sub(r"\s+", " ", fc.nfc(str(it.get(k) or ""))).strip()[:200] for k in ("artist", "title"))
        if not artist or not title:
            errors.append({"path": p, "error": "Interpret oder Titel fehlt"})
            continue
        fields = {"artist": artist, "title": title}
        for k in ("album", "albumartist", "year", "genre"):
            v = str(plan.get(k) or "").strip()
            if v:
                fields[k] = v[:200]
        n, tot = fc.track_no(it.get("track")), fc.track_no(it.get("total"))
        if n:
            fields["track"] = f"{n}/{tot}" if tot else str(n)
        dn, dt = fc.track_no(it.get("disc")), fc.track_no(it.get("discs"))
        if dn:                                               # Doppel-CD (09.11.2026): CD-Nummer ins Feld CD (TPOS), "1/2"
            fields["disc"] = f"{dn}/{dt}" if dt else str(dn)
        elif _disc_tag(f):                                   # einzelne CD (09.11.2026: Live-CD lag als "Disc 2" bei der Studio-CD)
            fields["disc"] = "1/1"
        if f.lower().endswith(".mp3"):
            try:
                write(f, fields)
            except Exception as e:                           # noqa: BLE001  eine Datei kaputt: die anderen weiter
                errors.append({"path": p, "error": f"Tags: {str(e)[:80]}"})
                continue
        ext = os.path.splitext(f)[1].lower()
        stem = fc.name_for(artist, title)
        new_dir = dest or os.path.dirname(f)
        new = fc.nfc(os.path.join(new_dir, stem + ext))
        others = [q for q in taken.get(fc.nkey(os.path.basename(new)), []) if q != fc.nfc(f)]
        if others or (os.path.lexists(new) and fc.nkey(new) != fc.nkey(f)):
            al = fc.clean_part(plan.get("album"))
            cands = ([f"{stem} ({al})"] if al else []) + [f"{stem} ({i})" for i in range(2, 50)]
            stem = next(c for c in cands if not [q for q in taken.get(fc.nkey(c + ext), []) if q != fc.nfc(f)]
                        and not os.path.lexists(os.path.join(new_dir, c + ext)))
            new = fc.nfc(os.path.join(new_dir, stem + ext))
        if new == fc.nfc(f):
            done.append({"path": p, "old_path": p, "new_path": p, "name": os.path.basename(f)})
            continue
        src_dirs.add(os.path.dirname(f))
        try:
            os.makedirs(new_dir, exist_ok=True)
            if os.path.lexists(new) and fc.nkey(new) != fc.nkey(f):
                raise OSError("Ziel gibt es schon")
            fc.rename_any(f, new)
        except OSError as e:
            errors.append({"path": p, "error": f"Umbenennen: {e}"})
            continue
        taken.setdefault(fc.nkey(os.path.basename(new)), []).append(new)
        old_k = fc.nkey(os.path.basename(f))
        taken[old_k] = [q for q in taken.get(old_k, []) if q != fc.nfc(f)]
        # Pfad in Mixxx: derselbe Teil unterhalb des Musikordners (Mixxx kennt die Datei vielleicht unter einem anderen Laufwerk)
        rel_old, rel_new = _rel(root, fc.nfc(f)), _rel(root, new)
        newp = p[: len(p) - len(rel_old)] + rel_new if fc.nfc(p).endswith(rel_old) else new
        check._queue(p, newp)
        with check.lock:
            check.index[old_k] = [q for q in check.index.get(old_k, []) if fc.nfc(q) != fc.nfc(f)]
            check.index.setdefault(fc.nkey(os.path.basename(new)), []).append(new)
        if check.renamed is not None:
            try:
                check.renamed(p, newp)
            except Exception:                                # noqa: BLE001  Merkzettel sind Beiwerk
                pass
        done.append({"path": p, "old_path": p, "new_path": newp, "name": os.path.basename(new)})
    for sd in src_dirs if dest else ():                      # alte Ordner leer (nur noch macOS-Hilfsdateien): weg
        try:
            if os.path.normpath(sd) == os.path.normpath(root) or not _pn(sd).startswith(root + "/"):
                continue
            left = [x for x in os.listdir(sd) if not x.startswith("._") and x.lower() not in fc.MAC_AUX]
            if not left:
                for x in os.listdir(sd):
                    os.remove(os.path.join(sd, x))
                os.rmdir(sd)
        except OSError:
            pass
    log(f"CD-Assistent: {len(done)} Lieder geschrieben" + (f", {len(errors)} Fehler" if errors else "") + (f", nach {dest}" if dest else ""))
    return {"done": done, "errors": errors, "dir": _rel(root, dest) if dest else str(plan.get("dir") or "")}


def _real_dir(path):
    """Ordner am Stick in der Schreibweise, die es wirklich gibt (FAT: NFC/NFD), sonst None."""
    import unicodedata
    cands = [path, fc.nfc(path), unicodedata.normalize("NFD", path)]
    try:
        from music_serve import disk_name
        cands.insert(1, disk_name(path))
    except ImportError:
        pass
    return next((c for c in cands if os.path.isdir(c)), None)


def rename_dir(check, d, new):
    """Ordner umbenennen oder verschieben (Wunsch 09.11.2026: aus der Web-Oberflaeche, "1998 - .../Disc 2" -> "1999 - Live").
    d und new relativ zum Musikordner. Nie ueberschreiben, nie aus dem Musikordner hinaus. Jede Datei darin kommt in die
    Warteschlange fuer Mixxx (offen.tsv): wartende Umbenennungen in diesen Ordner zeigen gleich auf den neuen Pfad, alle anderen
    Lieder bekommen eine neue Zeile. Hotcues, Kisten und Playlists bleiben."""
    root = _pn(check.root() or "").rstrip("/")
    if not root or not os.path.isdir(root):
        raise ValueError("Musikordner nicht gefunden (Stick eingesteckt?)")
    d = fc.nfc(str(d or "").strip().strip("/"))
    parts = [x.strip() for x in fc.nfc(str(new or "")).strip().strip("/").split("/")]
    if not d or not parts or any(not x or x in (".", "..") or fc.BAD.search(x) or x != x.strip(" .") for x in parts):
        raise ValueError("Neuer Name ungültig (keine Zeichen \\ : * ? \" < > |, kein Punkt am Ende)")
    if any(len(x) > 120 for x in parts):
        raise ValueError("Ordnername zu lang (höchstens 120 Zeichen)")
    new = "/".join(parts)
    if ".." in d.split("/"):
        raise ValueError("Ordner ungültig")
    src = _real_dir(os.path.join(root, d))
    if not src:
        raise ValueError("Ordner nicht gefunden: " + d)
    dst = os.path.join(root, new)
    if fc.nkey(dst + "/").startswith(fc.nkey(os.path.join(root, d) + "/")) and fc.nkey(dst) != fc.nkey(os.path.join(root, d)):
        raise ValueError("Ein Ordner kann nicht in sich selbst")
    if fc.nfc(dst) == fc.nfc(os.path.join(root, d)):
        raise ValueError("Der Name ist gleich")
    if fc.nkey(dst) != fc.nkey(os.path.join(root, d)) and (os.path.lexists(dst) or _real_dir(dst)):
        raise ValueError("Diesen Ordner gibt es schon: " + new)
    old_n, new_n = fc.nfc(os.path.join(root, d)), fc.nfc(dst)

    def moved(x):                                            # Pfad unter dem alten Ordner -> unter dem neuen (sonst None)
        xn = fc.nfc(x)
        if xn.startswith(old_n + "/"):
            return new_n + xn[len(old_n):]
        i = xn.find("/" + d + "/")                           # Mixxx kennt die Datei vielleicht unter einem anderen Laufwerk
        return xn[:i] + "/" + new + xn[i + 1 + len(d):] if i >= 0 else None

    songs = [r.get("path") for r in check.songs() or [] if r.get("path")]
    mine, pend0 = [], _pending()
    for p in songs:
        f = _where(check, p, pend0)
        if f and fc.nfc(f).startswith(old_n + "/"):
            mine.append(p)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.rename(src, dst)
    q = fc.FileCheck.queue_path()
    lines = []
    try:
        with open(q, encoding="utf-8") as fh:
            lines = [x.rstrip("\n").split("\t") for x in fh if "\t" in x]
    except OSError:
        pass
    pend, out = set(), []
    for a, b in lines:                                       # wartende Umbenennungen in diesen Ordner: gleich auf den neuen
        m = moved(b)
        if m:
            pend.add(fc.nfc(a))
            b = m
        out.append(a + "\t" + b)
    n = 0
    for p in mine:
        if fc.nfc(p) in pend:
            continue
        m = moved(p) or moved(_where(check, p, pend0) or "")
        if m and "\t" not in p + m and "\n" not in p + m:
            out.append(p + "\t" + m)
            n += 1
    os.makedirs(os.path.dirname(q), exist_ok=True)
    tmp = q + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("".join(x + "\n" for x in out))
    os.replace(tmp, q)
    with check.lock:                                         # Dateiliste der Pruefung mitziehen (Namen gleich, Ordner neu)
        for k, v in list((check.index or {}).items()):
            check.index[k] = [moved(x) or x for x in v]
    if check.renamed is not None:
        for p in mine:
            try:
                check.renamed(p, moved(p) or moved(_where(check, p, pend0) or "") or p)
            except Exception:                                # noqa: BLE001  Merkzettel sind Beiwerk
                pass
    parent = os.path.dirname(src)                            # alter Ueberordner leer (nur macOS-Hilfsdateien): weg
    try:
        if _pn(parent).startswith(root + "/") and not [x for x in os.listdir(parent) if not x.startswith("._") and x.lower() not in fc.MAC_AUX]:
            for x in os.listdir(parent):
                os.remove(os.path.join(parent, x))
            os.rmdir(parent)
    except OSError:
        pass
    return {"dir": new, "songs": len(mine), "queued": n + len(pend)}


def clean_line(s):
    """Fuer Tests und den Mac: Fussnoten wie [[1](...)] und Discogs-Sternchen weg."""
    s = re.sub(r"\[\[\d+\]\([^)]*\)\]|\[\d+\]", "", str(s or ""))
    return re.sub(r"\*(?=\s|$|–|-)", "", s).strip()
