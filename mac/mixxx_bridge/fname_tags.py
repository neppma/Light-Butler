"""Tags aus dem Dateinamen (Wunsch 10.11.2026): Lieder ohne Tags (zum Beispiel lizenzfreie Musik "19th Floor - Bobby Richards.mp3")
bekommen Interpret, Titel und Tracknummer aus dem Dateinamen, nach einem waehlbaren Muster. Werkzeug in der Datenpflege, Seite
/musik/dateinamen. Ordner waehlen, Muster waehlen, Vorschau je Lied (jetzt / neu), dann je Seite eintragen. Standard: nur leere
Felder fuellen; vorhandene Angaben bleiben, ausser man hakt "auch vorhandene ueberschreiben" an. Nur MP3 (ID3), Musik bleibt gleich.
"""
import os
import re
import unicodedata

import cd_assist
from pfad import norm as _pn, relpath as _relpath

PATTERNS = (("a-t", "Interpret - Titel"), ("t-a", "Titel - Interpret"), ("n-a-t", "Nr - Interpret - Titel"), ("n-t", "Nr - Titel"),
            ("t", "nur Titel (ganzer Name)"), ("p", "wörter-mit-bindestrich-123 (Pixabay)"))
MAX_SONGS = 5000


def nfc(s):
    return _pn(unicodedata.normalize("NFC", str(s or "")))          # Windows: "\\" -> "/"


def tidy(s):
    s = nfc(s).replace("_", " ")
    return re.sub(r"\s+", " ", s).strip(" -")


def parse(name, pat):
    """Dateiname (mit oder ohne Endung) -> {artist, title, track}; leere Felder fehlen. Ohne passenden Aufbau: {}."""
    stem = os.path.splitext(os.path.basename(nfc(name)))[0] if nfc(name).lower().endswith((".mp3", ".m4a", ".wav", ".flac")) else os.path.basename(nfc(name))
    stem = re.sub(r"(_pn|\s*\(\d{1,2}\))$", "", stem).strip()
    nr = ""
    if pat.startswith("n-"):
        m = re.match(r"^\(?(\d{1,3})\)?\s*[-._)]?\s+(.*)$", stem) or re.match(r"^(\d{1,3})[-._]\s*(.*)$", stem)
        if not m:
            return {}
        nr, stem = str(int(m.group(1))), m.group(2)
    parts = [tidy(p) for p in re.split(r"\s+-\s+", stem) if tidy(p)]
    out = {}
    if pat in ("a-t", "n-a-t"):
        if len(parts) < 2:
            return {}
        out = {"artist": parts[0], "title": " - ".join(parts[1:])}
    elif pat == "t-a":
        if len(parts) < 2:
            return {}
        out = {"title": " - ".join(parts[:-1]), "artist": parts[-1]}
    elif pat == "p":                                         # "ambient-inspiration-136110" -> "Ambient Inspiration"
        words = [w for w in re.split(r"[-_\s]+", stem) if w]
        while words and words[-1].isdigit():
            words.pop()
        if not words:
            return {}
        out = {"title": " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words)}
    elif pat in ("n-t", "t"):
        if not parts:
            return {}
        out = {"title": " - ".join(parts)}
    if nr:
        out["track"] = nr
    return {k: v[:200] for k, v in out.items() if v}


def dirs(check):
    """Ordner mit MP3s (relativ zum Musikordner) und Zahl der Lieder, fuer die Auswahl."""
    root = nfc((check.root() or "").rstrip("/"))
    cnt = {}
    for r in check.songs() or []:
        p = nfc(r.get("path") or "")
        if not p.lower().endswith(".mp3"):
            continue
        i = p.find(root + "/") if root else -1
        rel = p[i + len(root) + 1:] if i >= 0 else ""
        d = os.path.dirname(rel)
        while d:
            cnt[d] = cnt.get(d, 0) + 1
            d = os.path.dirname(d)
    return sorted(cnt.items(), key=lambda x: x[0].casefold())


def scan(check, d, pat, overwrite=False, read=None):
    """Lieder unter <Musikordner>/<d> (auch Unterordner) mit jetzigen und neuen Angaben."""
    if pat not in dict(PATTERNS):
        raise ValueError("unbekanntes Muster")
    root = nfc((check.root() or "").rstrip("/"))
    d = nfc(d).strip().strip("/")
    if not d or ".." in d.split("/"):
        raise ValueError("Ordner wählen")
    base = _pn(os.path.join(root, d))
    if not os.path.isdir(base):
        raise ValueError("Ordner gibt es nicht: " + d)
    if read is None:
        import tag_edit
        read = lambda f: tag_edit.read_tags(f)["fields"]   # noqa: E731
    pend = cd_assist._pending()
    seg = "/" + d + "/"
    out = []
    for r in check.songs() or []:
        p = r.get("path") or ""
        if not p.lower().endswith(".mp3") or (seg not in nfc(p) and seg not in nfc(pend.get(p, ""))):
            continue
        f = cd_assist._where(check, p, pend)
        if not f or not nfc(f).startswith(base + "/") or not os.path.isfile(f):
            continue
        try:
            cur = read(f)
        except Exception:                                      # noqa: BLE001  Tag unlesbar: wie leer
            cur = {}
        new = parse(f, pat)
        change = {k: v for k, v in new.items() if v != (cur.get(k) or "") and (overwrite or not (cur.get(k) or "").strip())}
        out.append({"path": p, "file": nfc(f), "rel": _relpath(nfc(f), root), "dur": round(float(r.get("duration") or 0)),
                    "cur": {k: cur.get(k) or "" for k in ("artist", "title", "track")}, "new": new, "change": change})
        if len(out) >= MAX_SONGS:
            break
    out.sort(key=lambda x: x["rel"].casefold())
    return {"dir": d, "pat": pat, "songs": out, "n": len(out), "todo": sum(1 for x in out if x["change"])}


def apply(check, items, write=None, on_written=None, log=None):
    """items: [{path, file, fields: {artist, title, track}}] -> nur diese Felder schreiben."""
    import stick_hold
    if stick_hold.held():
        raise ValueError("Der Stick ist ausgeworfen")
    if write is None:
        import tag_edit
        write = tag_edit.write_tags
    log = log or (lambda t: None)
    res = {"written": 0, "errors": []}
    pend = cd_assist._pending()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        p, f = str(it.get("path") or ""), nfc(it.get("file") or "")
        fields = {k: str(v).strip()[:200] for k, v in (it.get("fields") or {}).items() if k in ("artist", "title", "track") and str(v or "").strip()}
        try:
            real = cd_assist._where(check, p, pend)
            if not real or nfc(real) != f or not f.lower().endswith(".mp3"):
                raise ValueError("Datei nicht gefunden")
            if not fields:
                continue
            write(real, fields)
            res["written"] += 1
            if on_written is not None:
                try:
                    on_written(p, fields)
                except Exception:                              # noqa: BLE001
                    pass
        except Exception as e:                                 # noqa: BLE001
            res["errors"].append(f"{os.path.basename(f)}: {str(e)[:120]}")
    if res["written"]:
        log(f"Tags aus Dateinamen: {res['written']} Lieder")
    return res
