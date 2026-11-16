"""
dupes.py - Doppelte Lieder finden und vergleichen (Wunsch von Markus, 07.11.2026, Datenbankpflege).

Gruppen: gleicher Dateiname (ohne Endung und Kopie-Zusaetze wie "(1)", "_pn", "Kopie") oder gleicher Interpret und Titel.
Je Datei wird gesammelt, was fuer die Wahl zaehlt: Dateiart, Bitrate, Abtastrate, Laenge, Hotcues, Energie (Mixed In Key),
Cover, wie vollstaendig die Tags sind, Fingerabdruck der Musik (nur MP3, ohne Tags) und ob das Lied in Mixxx steht.
Die Empfehlung rechnet die Seite /musik/doppelte (dupes.js) daraus, zusammen mit Shows und Kurven vom Pi; geloescht wird
nur dort, nur auf Klick und nur in den Papierkorb des Mac (music_serve /trash). Dieses Modul liest nur.
"""
import json
import os
import re
import threading
import time
import unicodedata
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

STALE_S = 600.0                    # so lange gilt eine Auswertung, dann wird neu gerechnet
KEPT_FILE = os.path.join(_pfad.daten(), "doppelte", "behalten.json")   # Gruppen "alle behalten", gemeinsam mit dem Helfer
TAG_KEYS = ("title", "artist", "album", "albumartist", "year", "track", "disc", "genre", "bpm", "key", "composer", "publisher", "isrc")
TRACK_TOL_S = 0.3                  # gleiches Album, gleiche Tracknummer: nur bei fast genau gleicher Laenge (14.11.2026)
DUR_TOL_S = 3.0                    # so viel duerfen Doppelte in der Laenge abweichen (Stille am Anfang, andere Kodierung)


def fold(s):
    """Apostrophe (’ ' ` ´) fallen weg, lange und kurze Striche werden zu "-" (Wunsch 09.11.2026: "It’s Raining Men" und
    "It's Raining Men", "Played‐a‐Live" und "Played-A-Live" sind dasselbe Lied)."""
    return re.sub(r"[‐‑‒–—]", "-", re.sub(r"['’‘`´ʼ]", "", str(s or "")))


def stem_key(path):
    """Dateiname fuer den Vergleich: ohne Ordner, Endung, Kopie-Zusaetze, Gross-/Kleinschreibung, Sonderzeichen."""
    s = fold(os.path.splitext(os.path.basename(path or ""))[0])
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"(_pn|\s*\(\d{1,2}\)|\s*[-_ ]?(kopie|copy)(\s*\d+)?)$", "", s)   # Tracknummern am Ende bleiben (Teil 01, 02 ...)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def title_key(artist, title):
    """Interpret und Titel fuer den Vergleich ('' wenn eines fehlt)."""
    def n(x):
        x = unicodedata.normalize("NFKD", fold(x)).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", " ", x).strip()
    a, t = n(artist), n(title)
    return f"{a}|{t}" if a and t else ""


def track_key(r):
    """Interpret, Album und Tracknummer (Wunsch 14.11.2026: "Der Wind" und eine Datei mit dem Albumnamen als Titel, Austria 3
    Austro Pop Parade Track 8, klingen gleich): '' wenn etwas davon fehlt."""
    m = re.match(r"\s*(\d+)", str(r.get("tracknumber") or ""))
    al = re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", str(r.get("album") or "")).lower())
    ar = title_key(r.get("artist"), "x")[:-2]             # nur der Interpret (title_key braucht einen Titel)
    return "%s|%s|%d" % (ar, al, int(m.group(1))) if m and int(m.group(1)) and al and ar else ""


def same_folder_other_name(a, b):
    """Selber Ordner, verschiedener Dateiname (etwa nur die Tracknummer): verschiedene Lieder eines Albums, auch wenn die Tags
    gleich sind (Fehlerbericht 07.11.2026: "01/07/08 - Klangraeume Catalogue" als Doppelte vorgeschlagen)."""
    return os.path.dirname(a) == os.path.dirname(b) and stem_key(a) != stem_key(b)


def groups(lib):
    """Gruppen doppelter Lieder: Liste von Listen von Bibliothekseintraegen (je mindestens zwei verschiedene Pfade)."""
    # dieselbe Datei zweimal in Mixxx (Umlaute verschieden gespeichert, Fehlerbericht 11.11.2026): nur einmal zaehlen, sonst
    # schlug die Seite vor, eine davon zu loeschen, und damit waere die einzige Datei weg gewesen
    import unicodedata
    recs, seen_p = [], set()
    for r in lib:
        if not r.get("path") or r.get("missing"):
            continue
        k = unicodedata.normalize("NFC", r["path"])
        if k in seen_p:
            continue
        seen_p.add(k)
        recs.append(r)
    parent = list(range(len(recs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen = {}                                          # Schluessel -> Liedern mit diesem Schluessel
    for i, r in enumerate(recs):
        d = float(r.get("duration") or 0)
        tk = track_key(r)
        for k in (("s:" + stem_key(r["path"])) if len(stem_key(r["path"])) >= 4 else "",
                  ("t:" + title_key(r.get("artist"), r.get("title"))), ("a:" + tk) if tk else ""):
            if len(k) <= 2:
                continue
            for j in seen.setdefault(k, []):               # nur fast gleich lange: andere Fassungen und Alben mit lauter
                dj = float(recs[j].get("duration") or 0)   # gleichen (falschen) Titeln sind keine Doppelten
                if k.startswith("t:") and same_folder_other_name(r["path"], recs[j]["path"]):
                    continue                               # Album mit gleichen Tags je Lied: 01, 07, 08 sind verschiedene Lieder
                if k.startswith("a:"):                     # Album + Track: Titel darf falsch sein, Laenge muss fast genau passen
                    if d and dj and abs(d - dj) <= TRACK_TOL_S:
                        parent[find(i)] = find(j)
                    continue
                if not d or not dj or abs(d - dj) <= DUR_TOL_S:
                    parent[find(i)] = find(j)
            seen[k].append(i)
    out = {}
    for i, r in enumerate(recs):
        out.setdefault(find(i), []).append(r)
    res = []
    for g in out.values():
        paths = {r["path"] for r in g}
        if len(paths) >= 2:
            res.append(sorted({r["path"]: r for r in g}.values(), key=lambda r: r["path"]))
    return sorted(res, key=lambda g: stem_key(g[0]["path"]))


def describe(r, file, energy=None, has_cover=None, read_tags=None, fingerprint=None):
    """Angaben zu einer Datei der Gruppe (liest den Kopf der Datei, nie die ganze Musik ausser fuer den Fingerabdruck)."""
    ext = os.path.splitext(r["path"])[1].lstrip(".").lower()
    out = {"path": r["path"], "ext": ext, "dur": round(float(r.get("duration") or 0), 1), "kbps": int(r.get("bitrate") or 0),
           "rate": int(r.get("samplerate") or 0), "cues": len(r.get("cues") or []), "lvl": int(energy(r) or 0) if energy else 0,
           "mixxx": r.get("src") != "dir", "artist": str(r.get("artist") or ""), "title": str(r.get("title") or ""),
           "exists": bool(file and os.path.isfile(file)), "cover": False, "tags": 0, "fp": "", "size": 0,
           "sk": stem_key(r["path"]), "tk": title_key(r.get("artist"), r.get("title"))}   # die Seite prueft: passt direkt zur behaltenen?
    if not out["exists"]:
        return out
    try:
        out["size"] = os.path.getsize(file)
    except OSError:
        pass
    if has_cover is not None:
        try:
            out["cover"] = bool(has_cover(file))
        except OSError:
            pass
    if ext == "mp3":
        if read_tags is not None:
            try:
                f = read_tags(file)["fields"]
                out["tags"] = sum(1 for k in ("title", "artist", "album", "year", "genre", "bpm", "key", "track") if f.get(k))
                out["tv"] = {k: str(f.get(k) or "")[:120] for k in TAG_KEYS if f.get(k)}   # Inhalt: die Seite vergleicht und uebertraegt
            except Exception:                                   # noqa: BLE001  Kopf nicht lesbar: zaehlt als ohne Tags
                pass
        if fingerprint is not None:
            try:
                out["fp"] = fingerprint(file)
            except OSError:
                pass
    return out


class Dupes:
    """Auswertung im Hintergrund (eigener Thread), fuer die Seite Doppelte. lib() -> Bibliothek, mapper(p) -> Datei am Mac."""

    def __init__(self, lib, mapper, energy=None, has_cover=None, read_tags=None, fingerprint=None, log=None, kept_file=KEPT_FILE):
        self.lib, self.mapper = lib, mapper
        self.kept_file = kept_file
        try:
            with open(kept_file, encoding="utf-8") as f:
                self.kept = {str(x) for x in json.load(f)}
        except (OSError, ValueError, TypeError):
            self.kept = set()
        self.kw = {"energy": energy, "has_cover": has_cover, "read_tags": read_tags, "fingerprint": fingerprint}
        self.log = log or (lambda t: None)
        self.lock = threading.Lock()
        self.result, self.t, self.thread, self.progress = None, 0.0, None, (0, 0)

    def _work(self):
        try:
            gs = [g for g in groups(self.lib() or []) if self.gkey(r["path"] for r in g) not in self.kept]   # "alle behalten" kommt nicht wieder
            out, n = [], sum(len(g) for g in gs)
            done = 0
            for g in gs:
                items = []
                for r in g:
                    import stick_hold
                    if stick_hold.held():                    # Stick wird ausgeworfen: aufhoeren, altes Ergebnis bleibt
                        self.log("Doppelte: angehalten (Stick wird ausgeworfen)")
                        return
                    d = describe(r, self.mapper(r["path"]), **self.kw)
                    if d["exists"]:                          # Datei fehlt im Ordner (nur noch ein Eintrag in Mixxx): nicht zeigen,
                        items.append(d)                      # loeschen geht ohnehin nicht (Fehlerbericht 07.11.2026)
                    done += 1
                    self.progress = (done, n)
                if len(items) >= 2:
                    out.append(items)
            with self.lock:
                self.result, self.t = out, time.time()
            self.log(f"Doppelte: {len(out)} Gruppen mit {n} Dateien")
        except Exception as e:                                  # noqa: BLE001
            self.log(f"Doppelte: {e}")
            with self.lock:
                self.result, self.t = [], time.time()

    def get(self, fresh=False):
        """{"state": "ok"|"busy", "groups": [...], "progress": [fertig, alle], "age": s}. Rechnet bei Bedarf im Hintergrund neu."""
        with self.lock:
            busy = self.thread is not None and self.thread.is_alive()
            stale = self.result is None or fresh or time.time() - self.t > STALE_S
            if stale and not busy:
                self.progress = (0, 0)
                self.thread = threading.Thread(target=self._work, name="doppelte", daemon=True)
                self.thread.start()
                busy = True
            res = self.result
        if res is None or (busy and fresh):
            return {"state": "busy", "groups": [], "progress": list(self.progress)}
        return {"state": "busy" if busy else "ok", "groups": res, "progress": list(self.progress), "age": round(time.time() - self.t)}

    @staticmethod
    def gkey(paths):
        return "|".join(sorted(paths))

    def keep_all(self, paths):
        """Gruppe "alle behalten" (keine echten Doppelten oder bewusst beide): merken, kommt nicht wieder (Wunsch 07.11.2026)."""
        paths = [str(p) for p in paths if p]
        if len(paths) < 2:
            raise ValueError("Gruppe unvollstaendig")
        with self.lock:
            self.kept.add(self.gkey(paths))
            if self.result:
                self.result = [g for g in self.result if self.gkey(x["path"] for x in g) not in self.kept]
            data = sorted(self.kept)
        os.makedirs(os.path.dirname(self.kept_file), exist_ok=True)
        tmp = self.kept_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.kept_file)

    def forget(self, path):
        """Nach dem Loeschen: Datei aus der Auswertung nehmen (die Seite zeigt sofort den neuen Stand)."""
        with self.lock:
            if self.result:
                self.result = [g for g in ([x for x in g if x["path"] != path] for g in self.result) if len(g) >= 2]
