"""Ordner aufloesen (Wunsch 10.11.2026): einen Oberordner im Musikordner (zum Beispiel OLDIES, damals nur fuer eine Feier
angelegt) in einen anderen (U-MUSIK) einsortieren, Lied fuer Lied nach dem Muster <Ziel>/Artists/<Interpret>/<Interpret - Titel>.mp3
(gleiche Vorschlaege wie die Import-Seite, import_assist.suggest). Werkzeug in der Datenpflege, Seite /musik/aufloesen.

Die Lieder kennt Mixxx schon (Hotcues, Kisten, Playlists): verschoben wird ueber die Warteschlange fuer Mixxx wie beim Ordner
umbenennen (offen.tsv, beim naechsten Start der App "Light-Butler Mixxx" traegt mixxx_umbenennen.sh die neuen Pfade ein). Zeigt
schon eine vorgemerkte Umbenennung auf die Datei, wird diese Zeile auf das neue Ziel gestellt (sonst liefe die Kette ins Leere).
Nie ueberschreiben (" (2)"), Papierkorb statt loeschen, ein leer gewordener Ordner (nur macOS-Hilfsdateien) kommt weg.
Auf Wunsch kommt der Name des alten Ordners in die Gruppe (TIT1), nur wo sie noch fehlt: so findet man die Lieder wieder.
"""
import os
import unicodedata

import cd_assist
import file_check as fc
import import_assist as ia
from pfad import norm as _pn, relpath as _relpath

MAC_AUX = (".DS_Store",)


def nfc(s):
    return _pn(unicodedata.normalize("NFC", str(s or "")))          # Windows: "\\" -> "/"


def tops(root):
    try:
        return sorted((x for x in os.listdir(root) if not x.startswith(".") and os.path.isdir(os.path.join(root, x))), key=str.casefold)
    except OSError:
        return []


def _top_dir(root, name):
    name = nfc(name).strip().strip("/")
    if not name or "/" in name or name in (".", "..") or name.startswith("."):
        raise ValueError("Ordner ungueltig")
    d = os.path.join(root, name)
    if not os.path.isdir(d):
        raise ValueError("Ordner gibt es nicht: " + name)
    return d


def scan(check, src, dst):
    """Lieder unter <Musikordner>/<src> mit Vorschlag unter <dst> und vorhandenem Gegenstueck (ausserhalb von src)."""
    root = _pn(check.root() or "").rstrip("/")
    out = {"root": root, "src": src, "dst": dst, "tops": tops(root), "songs": [], "n": 0}
    if not src or not dst:
        return out
    sd, _dd = _top_dir(root, src), _top_dir(root, dst)
    if nfc(src) == nfc(dst):
        raise ValueError("Quelle und Ziel sind gleich")
    base = nfc(sd) + "/"
    pend = cd_assist._pending()
    mine, others = [], []
    for r in check.songs() or []:
        p = r.get("path")
        if not p:
            continue
        seg = "/" + nfc(src) + "/"                         # schnell: nur Lieder, deren Pfad den Ordner enthaelt, am Stick suchen
        if seg not in nfc(p) and seg not in nfc(pend.get(p, "")):
            others.append((r, None))
            continue
        f = cd_assist._where(check, p, pend)
        (mine if f and nfc(f).startswith(base) and os.path.isfile(f) else others).append((r, f))
    byt = ia.lib_index([r for r, _f in others])
    adirs = ia.artist_dirs(root, dst)
    for r, f in sorted(mine, key=lambda x: nfc(x[1]).casefold()):
        a, t = str(r.get("artist") or ""), str(r.get("title") or "")
        if a and t.startswith(a + " - "):
            t = t[len(a) + 3:]
        dur = float(r.get("duration") or 0)
        same = ia.classify(byt, a, t, dur)[1]
        dup = None
        if same:
            c = min(same, key=lambda c: abs(float(c.get("duration") or 0) - dur))
            dup = {"path": c.get("path") or "", "dur": round(float(c.get("duration") or 0)), "kbps": int(c.get("bitrate") or 0),
                   "artist": c.get("artist") or "", "title": c.get("title") or ""}
        tgt = ia.suggest(a, t, dst, adirs)
        out["songs"].append({"path": r["path"], "file": nfc(f), "rel": _relpath(nfc(f), nfc(root)), "artist": a, "title": t,
                             "album": r.get("album") or "", "genre": r.get("genre") or "", "grp": r.get("grouping") or "",
                             "dur": round(dur), "kbps": int(r.get("bitrate") or 0), "target": tgt,
                             "exists": os.path.exists(os.path.join(root, tgt)), "dup": dup})
    out["n"] = len(out["songs"])
    return out


def _new_mixxx_path(mp, f, root, new_rel):
    """Mixxx-Pfad nach dem Verschieben: gleicher Anfang wie der alte (Mixxx kennt den Stick vielleicht unter anderem Namen)."""
    old_rel = _relpath(nfc(f), nfc(root))
    m = nfc(mp)
    if m.endswith("/" + old_rel):
        return m[:-len(old_rel)] + new_rel
    return _pn(os.path.join(nfc(root), new_rel))


def _queue_move(check, mp, f, new_mp, new_file):
    """Warteschlange fuer Mixxx: Zeilen, deren Ziel diese Datei ist, auf das neue Ziel; sonst eine neue Zeile mp -> new_mp."""
    if "\t" in mp + new_mp or "\n" in mp + new_mp:
        return
    q = fc.FileCheck.queue_path()
    lines = []
    try:
        with open(q, encoding="utf-8") as fh:
            lines = [x.rstrip("\n").split("\t", 1) for x in fh if "\t" in x]
    except OSError:
        pass
    hit = False
    out = []
    for a, b in lines:
        loc = check.locate(b) if check.locate else None
        if nfc(b) == nfc(f) or (loc and nfc(loc) == nfc(f)) or nfc(b) == nfc(mp):
            b, hit = new_mp, True
        out.append(a + "\t" + b)
    if not hit:
        out.append(mp + "\t" + new_mp)
    os.makedirs(os.path.dirname(q), exist_ok=True)
    with open(q + ".tmp", "w", encoding="utf-8") as fh:
        fh.write("".join(x + "\n" for x in out))
    os.replace(q + ".tmp", q)
    with check.lock:
        k = fc.nkey(os.path.basename(f))
        check.index[k] = [x for x in check.index.get(k, []) if nfc(x) != nfc(f)]
        check.index.setdefault(fc.nkey(os.path.basename(new_file)), []).append(new_file)
    if check.renamed is not None:
        try:
            check.renamed(mp, new_mp)
        except Exception:                                    # noqa: BLE001  Merkzettel sind Beiwerk
            pass


def remove_empty(d):
    """Leere Ordner unter d (und d selbst) entfernen; Hilfsdateien von macOS zaehlen als leer."""
    n = 0
    for cur, dirs, files in os.walk(d, topdown=False):
        rest = [x for x in files if not (x.startswith("._") or x in MAC_AUX)]
        if rest or any(os.path.isdir(os.path.join(cur, x)) for x in dirs):
            continue
        for x in files:
            try:
                os.remove(os.path.join(cur, x))
            except OSError:
                pass
        try:
            os.rmdir(cur)
            n += 1
        except OSError:
            pass
    return n


def apply(check, src, items, group="", trash=fc.to_trash_many, write_group=None, log=None):
    """items: [{path (Mixxx-Pfad), file (Datei am Stick), do: move|replace|trash, target, dup}]."""
    import stick_hold
    log = log or (lambda t: None)
    if stick_hold.held():
        raise ValueError("Der Stick ist ausgeworfen")
    root = _pn(check.root() or "").rstrip("/")
    sd = _top_dir(root, src)
    base = nfc(sd) + "/"
    res = {"moved": 0, "trashed": 0, "replaced": 0, "grouped": 0, "removed_dirs": 0, "errors": []}
    to_trash = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        mp, f = str(it.get("path") or ""), nfc(it.get("file") or "")
        name = os.path.basename(f)
        try:
            real = cd_assist._where(check, mp, cd_assist._pending()) if mp else None
            if not real or nfc(real) != f or not f.startswith(base) or not os.path.isfile(real):
                raise ValueError("Datei nicht (mehr) im aufzuloesenden Ordner")
            do = it.get("do")
            if do == "trash":
                to_trash.append(real)
                continue
            if do not in ("move", "replace"):
                raise ValueError("unbekannte Aktion")
            full = ia._check_target(root, it.get("target"))
            if nfc(full).startswith(base):
                raise ValueError("Ziel liegt im aufzuloesenden Ordner")
            if do == "replace":
                old = check.locate(str(it.get("dup") or "")) if it.get("dup") else None
                if not old or trash([old]):
                    raise ValueError("vorhandenes Lied liess sich nicht in den Papierkorb legen")
                res["replaced"] += 1
            if group and write_group is not None and f.lower().endswith(".mp3"):
                try:
                    if write_group(real, group):
                        res["grouped"] += 1
                except Exception as e:                       # noqa: BLE001  die Gruppe ist Beiwerk, verschoben wird trotzdem
                    log(f"Ordner aufloesen: Gruppe nicht geschrieben ({name}): {e}")
            full = ia.free_target(full)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            fc.rename_any(real, full)
            new_rel = _relpath(nfc(full), nfc(root))
            _queue_move(check, mp, real, _new_mixxx_path(mp, real, root, new_rel), full)
            res["moved"] += 1
        except (ValueError, OSError) as e:
            res["errors"].append(f"{name}: {e}")
    if to_trash:
        if trash(to_trash):
            res["errors"].append("Papierkorb: nicht alle Dateien verschoben")
        res["trashed"] = sum(1 for p in to_trash if not os.path.exists(p))
    res["removed_dirs"] = remove_empty(sd)
    if res["moved"] or res["trashed"]:
        log(f"Ordner aufloesen {src}: {res['moved']} verschoben, {res['trashed']} Papierkorb, {res['removed_dirs']} leere Ordner weg")
    return res


def group_writer(tag_edit):
    """Gruppe nur eintragen, wo sie fehlt (vorhandene bleibt, der Name kommt hinten dazu, wenn er noch nicht drinsteht)."""
    def write(path, group):
        cur = tag_edit.read_tags(path)["fields"].get("grouping") or ""
        parts = [x.strip() for x in cur.split(";") if x.strip()]
        if any(x.casefold() == group.casefold() for x in parts):
            return False
        tag_edit.write_tags(path, {"grouping": "; ".join(parts + [group])})
        return True
    return write
