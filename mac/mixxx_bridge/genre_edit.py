"""
genre_edit.py - Genre-Editor (Wunsch von Markus, 08.11.2026, Seite /musik/genres am Pi).

- Liste aller Genres aus den Tags (wie die Musik-Datenbank sie sieht: Mixxx plus geaenderte Tags der MP3s), mit Anzahl.
- Vorschlaege zum Zusammenlegen: nur Gross/klein, angehaengtes "; Other" (mehrere Genres in einem Feld), gleiche Bedeutung
  (feste Liste SYNONYMS), seltene Genres (unter RARE_N Liedern, Ziel waehlt Markus). "Nicht vorschlagen" merkt sich ein Genre.
- Umbenennen/Zusammenlegen: schreibt nur das Genre-Feld (TCON) der betroffenen MP3s, im Hintergrund, mit Fortschritt.
  Jede Sammelaenderung kommt ins Protokoll (alter Wert je Datei) und laesst sich in einem Schritt zuruecknehmen.
- Hausliste: welche Genres es geben soll; alles andere zeigt die Seite gelb.
- Genre fuellen fuer Lieder ohne Genre oder mit "Other": Vorschlag vom Interpreten (seine anderen Lieder), vom Ordner
  (die anderen Lieder im selben obersten Ordner) oder auf Knopfdruck aus dem Internet (iTunes, hoechstens alle 3 s).
  Samples (Ordner SAMPLES, TESTSAMPLES) bleiben aussen vor. Geschrieben wird nur auf Klick.

Die Musik in der Datei bleibt Byte fuer Byte gleich (Fingerabdruck, Shows, Pegelkurven bleiben). id3_tags merkt jede
Datei fuer die Mixxx-Playlist "geaenderte Tags". Ablage: ~/Light-Butler-Daten/genres/ (hausliste.json, protokoll.jsonl, internet.json).
"""
import collections
import json
import os
import re
import threading
import time
import unicodedata

from pfad import norm as _pn
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

OTHER = {"other", "miscellaneous", "misc", "unknown", "sonstiges", "sonstige", "diverse", "genre", "none"}
SAMPLE_DIRS = {"samples", "testsamples"}
RARE_N = 5
NET_EVERY_S = 3.0
MAX_TEXT = 40
# gleiche Bedeutung: Schreibweise (klein) -> Ziel (wird an eine vorhandene Schreibweise angeglichen)
SYNONYMS = {
    "classical": "Klassik", "classical other": "Klassik", "classical other other": "Klassik", "klassisch": "Klassik",
    "classic": "Klassik", "orchestral": "Klassik", "opera": "Klassik", "oper": "Klassik",
    "miscellaneous": "Other", "misc": "Other", "unknown": "Other", "sonstiges": "Other", "sonstige": "Other",
    "hip-hop": "Hip Hop", "hiphop": "Hip Hop", "hip hop/rap": "Hip Hop", "rap": "Hip Hop",
    "rnb": "R&B", "r and b": "R&B", "rhythm & blues": "R&B", "r&b/soul": "R&B",
    "soundtracks": "Soundtrack", "filmmusik": "Soundtrack", "film": "Soundtrack", "score": "Soundtrack", "original score": "Soundtrack",
    "christmas": "Weihnachten", "xmas": "Weihnachten", "holiday": "Weihnachten", "weihnachtslieder": "Weihnachten",
    "ndw": "Neue Deutsche Welle", "volkstuemlich": "Volksmusik", "volkstümlich": "Volksmusik", "volksmusik": "Volksmusik",
    "trip-hop": "Trip Hop", "triphop": "Trip Hop", "dance-pop": "Dance", "eurodance": "Dance", "electronica": "Electronic",
    "electronic dance music": "EDM", "tv themes": "Soundtrack", "musicals": "Musical", "new age": "Meditation",
}


def nfc(s):
    return unicodedata.normalize("NFC", str(s or "")).strip()


def gkey(g):
    """Vergleichsschluessel: Gross/klein und Leerzeichen egal."""
    return re.sub(r"\s+", " ", nfc(g).casefold())


def first_part(g):
    """"Eurodance; Other" -> "Eurodance" (mehrere Genres in einem Feld, das erste zaehlt)."""
    parts = [p.strip() for p in re.split(r"[;/]|\s,\s", nfc(g)) if p.strip()]
    keep = [p for p in parts if gkey(p) not in OTHER] or parts
    return keep[0] if keep else ""


def is_other(g):
    return not nfc(g) or gkey(g) in OTHER


def clean_genre(g):
    g = re.sub(r"\s+", " ", nfc(g))
    if not g or len(g) > MAX_TEXT or any(c in g for c in "\x00\n\r\t;"):
        raise ValueError("Genre leer, zu lang (40 Zeichen) oder mit ; (nur ein Genre je Datei)")
    return g


def data_dir():
    return os.path.join(_pfad.daten(), "genres")


def top_dir(rel):
    parts = [p for p in str(rel or "").split("/") if p]
    return parts[0] if len(parts) > 1 else ""


class GenreEditor:
    def __init__(self, songs, locate, root, write=None, on_written=None, lookup=None, log=None, now=time.time, sleep=time.sleep, ready=None):
        """songs() -> Lieder wie Forwarder.lib_with_tags (path, artist, title, genre); locate(path) -> Datei oder None;
        root() -> Musikordner; write(file, fields) schreibt Tags (Standard tag_edit.write_tags); on_written(path, fields)
        wie music_serve.on_tags; lookup(artist, title) -> Genre aus dem Internet oder ''."""
        self.songs, self.locate, self.root = songs, locate, root
        self.write, self.on_written, self.lookup = write, on_written, lookup
        self.log, self.now, self.sleep = log or (lambda t: None), now, sleep
        self.ready = ready                  # ready() -> Tags der Dateien gelesen (sonst noch alte Werte aus Mixxx)
        self.lock = threading.Lock()
        self.written_now = set()            # in diesem Lauf geschrieben (Genre-Nummer-Hinweis gleich aktuell)
        self.job = None                     # {"kind", "done", "total", "ok", "skip", "err", "to"}
        self.net = {"busy": False, "done": 0, "total": 0}
        self.dir = data_dir()
        self.conf = self._load_json("hausliste.json", {"house": [], "never": []})
        self.inet = self._load_json("internet.json", {})

    # ---- Ablage ----
    def _load_json(self, name, default):
        try:
            with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, type(default)) else default
        except (OSError, ValueError):
            return default

    def _save_json(self, name, data):
        os.makedirs(self.dir, exist_ok=True)
        p = os.path.join(self.dir, name)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(p + ".tmp", p)

    def _writer(self):
        if self.write is None:
            import tag_edit
            self.write = tag_edit.write_tags
        return self.write

    # ---- Ueberblick ----
    def _lib(self):
        """Nur MP3s (Wunsch 09.11.2026): nur dort schreibt der Editor das Genre, WAV & Co. zaehlen nicht mit ("THX Intro.wav")."""
        return [r for r in (self.songs() or []) if str(r.get("path") or "").lower().endswith(".mp3")]

    def counts(self):
        """{Genre (genaue Schreibweise): Anzahl}, leeres Genre als ""."""
        return collections.Counter(nfc(r.get("genre")) for r in self._lib())

    def overview(self):
        c = self.counts()
        house = {gkey(g) for g in self.conf.get("house") or []}
        rows = [{"g": g, "n": n, "house": (gkey(g) in house) if house else None, "other": is_other(g)}
                for g, n in sorted(c.items(), key=lambda x: (-x[1], x[0].casefold())) if g]
        root = _pn(self.root() or "").rstrip("/")
        empty_sam = sum(1 for r in self._lib() if not nfc(r.get("genre")) and root and _pn(str(r.get("path") or "")).startswith(root + "/")
                        and top_dir(_pn(str(r["path"]))[len(root) + 1:]).casefold() in SAMPLE_DIRS)
        fc = self.fill_candidates()
        return {"ready": self.ready is None or bool(self.ready()), "genres": rows, "empty": c.get("", 0), "empty_sam": empty_sam, "total": sum(c.values()), "house": list(self.conf.get("house") or []),
                "never": list(self.conf.get("never") or []), "suggest": self.suggestions(c), "job": self.job_status(),
                "net": dict(self.net), "fill_n": len(fc), "num": self.numeric(),
                "fill_empty": sum(1 for x in fc if not x["now"]),   # nur ganz ohne Genre: "Other" gilt als vergeben (Wunsch 11.11.2026)
                "undo": [{k: v for k, v in h.items() if k != "items"} for h in self.history()[:30]]}

    def songs_of(self, genre, limit=500):
        """Lieder eines Genres fuer die Seite (Anhoeren, ansehen)."""
        g = nfc(genre)
        out = [{"path": r["path"], "artist": nfc(r.get("artist")), "title": nfc(r.get("title"))} for r in self._lib() if nfc(r.get("genre")) == g]
        return {"g": g, "n": len(out), "songs": out[:limit]}

    def numeric(self):
        """Lieder, deren Genre in der Datei nur als Nummer steht ("(148)", alte ID3v1-Schreibweise; Mixxx zeigt den Namen):
        [{path, now, want}] - "Namen eintragen" schreibt den Namen hinein (Fehlerbericht 09.11.2026)."""
        import id3_tags
        out = []
        for r in self._lib():
            raw = r.get("gnum")
            if raw and r["path"] not in self.written_now:
                want = id3_tags.genre_name(raw)
                if want:
                    out.append({"path": r["path"], "now": raw, "want": want})
        return out

    def suggestions(self, c=None):
        """[{from: [Genres], to, why, kind, n}] - kind: case, multi, same, rare (rare ohne Ziel)."""
        c = c if c is not None else self.counts()
        never = {gkey(g) for g in self.conf.get("never") or []}
        names = [g for g in c if g]
        by_key = collections.defaultdict(list)
        for g in names:
            by_key[gkey(g)].append(g)
        spelled = {k: max(v, key=lambda g: c[g]) for k, v in by_key.items()}    # haeufigste Schreibweise

        def target(label):
            return spelled.get(gkey(label), label)

        out, used = [], set()
        groups = collections.defaultdict(set)              # Ziel -> Genres, die dorthin sollen
        why = {}
        for k, v in by_key.items():                        # nur Gross/klein
            if len(v) > 1:
                t = spelled[k]
                for g in v:
                    if g != t:
                        groups[t].add(g)
                        why.setdefault(g, ("case", "nur Groß/klein"))
        for g in names:                                    # mehrere Genres in einem Feld
            if ";" in g or "/" in g:
                fp = first_part(g)
                if fp and gkey(fp) != gkey(g):
                    groups[target(SYNONYMS.get(gkey(fp), fp))].add(g)
                    why.setdefault(g, ("multi", "mehrere Genres in einem Feld, das erste zählt"))
        for g in names:                                    # gleiche Bedeutung
            syn = SYNONYMS.get(gkey(g))
            if syn and gkey(syn) != gkey(g):
                t = target(syn)
                if gkey(t) != gkey(g):
                    groups[t].add(g)
                    why.setdefault(g, ("same", "gleiche Bedeutung"))
        for t, gs in groups.items():
            gs = sorted(g for g in gs if gkey(g) not in never and g != t)
            if not gs:
                continue
            kinds = {why[g][0] for g in gs}
            kind = "case" if kinds == {"case"} else "multi" if "multi" in kinds and "same" not in kinds else "same"
            out.append({"from": gs, "to": t, "kind": kind, "why": "; ".join(sorted({why[g][1] for g in gs})),
                        "n": sum(c[g] for g in gs)})
            used.update(gs)
        for g in names:                                    # selten, Ziel waehlt Markus
            if c[g] < RARE_N and g not in used and gkey(g) not in never and not is_other(g) and g not in groups:
                out.append({"from": [g], "to": "", "kind": "rare", "why": f"nur {c[g]} Lied" + ("" if c[g] == 1 else "er"), "n": c[g]})
        order = {"case": 0, "multi": 1, "same": 2, "rare": 3}
        return sorted(out, key=lambda s: (order[s["kind"]], -s["n"]))

    # ---- Einstellungen ----
    def set_house(self, genres):
        seen, out = set(), []
        for g in genres or []:
            g = clean_genre(g)
            if gkey(g) not in seen:
                seen.add(gkey(g))
                out.append(g)
        self.conf["house"] = out[:200]
        self._save_json("hausliste.json", self.conf)
        return {"house": self.conf["house"]}

    def house_from_counts(self, min_n=20):
        """Vorschlag fuer die Hausliste: Genres mit mindestens min_n Liedern, ohne Other und ohne Doppelte."""
        c = self.counts()
        sug = {g for s in self.suggestions(c) for g in s["from"] if s["to"]}
        return [g for g, n in sorted(c.items(), key=lambda x: -x[1]) if g and n >= min_n and not is_other(g) and g not in sug]

    def set_never(self, genre, on=True):
        k = gkey(genre)
        nv = [g for g in self.conf.get("never") or [] if gkey(g) != k]
        if on:
            nv.append(nfc(genre))
        self.conf["never"] = nv[:500]
        self._save_json("hausliste.json", self.conf)
        return {"never": nv}

    # ---- Schreiben ----
    def job_status(self):
        with self.lock:
            return dict(self.job) if self.job else None

    def _check_ready(self):
        if self.ready is not None and not self.ready():
            raise ValueError("Der Mac liest gerade noch die Tags der Dateien (nach einem Neustart), bitte in ein paar Minuten nochmal")

    def rename(self, genres, to):
        """Alle Lieder mit einem der Genres (genaue Schreibweise) bekommen das Genre to."""
        self._check_ready()
        to = clean_genre(to)
        gs = {nfc(g) for g in genres or [] if nfc(g)}
        if not gs:
            raise ValueError("Kein Genre gewaehlt")
        items = [(r["path"], to) for r in self._lib() if nfc(r.get("genre")) in gs and nfc(r.get("genre")) != to]
        return self._start("rename", items, label=f"{', '.join(sorted(gs))} → {to}")

    def assign(self, pairs):
        """Einzelne Lieder: [[Pfad, Genre]] (Genre fuellen)."""
        self._check_ready()
        lib = {r["path"]: r for r in self._lib()}
        items = []
        for p, g in pairs or []:
            if p in lib:
                items.append((p, clean_genre(g)))
        if not items:
            raise ValueError("Keine Lieder gewaehlt")
        return self._start("fill", items, label=f"Genre gefüllt ({len(items)} Lieder)")

    def set_artist(self, paths, old, to):
        """Interpret aendern oder leeren (Seite Interpreten, Wunsch 13.11.2026), nur in den genannten Liedern (MP3). old = der
        Hauptname, wie ihn die Seite zeigt: "Falco feat. X" wird "<to> feat. X"; leer = das Feld Interpret entfernen."""
        self._check_ready()
        to, old = nfc(to).strip()[:200], nfc(old).strip()
        lib = {r["path"]: r for r in self._lib()}
        items = []
        for p in paths or []:
            r = lib.get(p)
            if r is None:
                continue
            cur = nfc(r.get("artist"))
            if not old or cur == old or (cur.startswith(old) and not to):
                new = to                                      # ganz ersetzen oder leeren
            elif cur.startswith(old):
                new = to + cur[len(old):]                     # "Falco feat. X" -> "<to> feat. X"
            elif to and old in cur:
                new = cur.replace(old, to)                    # "Bach & Glenn Gould" bei Glenn Gould: nur dieser Teil (13.11.2026)
            else:
                continue                                      # nur mitgezaehlt (gemeinsamer Eintrag): nie ganz ueberschreiben
            if new != cur:
                items.append((p, new))
        if not items:
            raise ValueError("Keine MP3 zu aendern (nur MP3s lassen sich schreiben)")
        return self._start("artist", items, label=f"Interpret {old or '?'} → {to or '(leer)'}", field="artist")

    def set_album(self, paths, to):
        """Albumname in allen MP3s eines Albums schreiben (Seite Alben, Bleistift, Wunsch 14.11.2026), etwa nur Gross/klein.
        Nur die genannten Lieder, nur wenn der Name sich aendert; leer geht nicht (das Album wuerde verschwinden)."""
        self._check_ready()
        to = " ".join(nfc(to).split())[:200]
        if not to:
            raise ValueError("Der Albumname darf nicht leer sein")
        lib = {r["path"]: r for r in self._lib()}
        items = [(p, to) for p in paths or [] if p in lib and nfc(lib[p].get("album")) != to]
        if not items:
            raise ValueError("Nichts zu aendern (nur MP3s lassen sich schreiben)")
        olds = sorted({nfc(lib[p].get("album")) for p, _ in items})
        return self._start("album", items, label=f"Album {olds[0] if len(olds) == 1 else '…'} → {to}", field="album")

    def set_grouping(self, pairs, label=""):
        """Gruppen-Manager (Wunsch 13.11.2026): [[Pfad, neue Gruppe(n) "A; B"]] schreiben (TIT1), nur MP3s, mit Protokoll."""
        self._check_ready()
        lib = {r["path"]: r for r in self._lib()}
        items = []
        for p, g in pairs or []:
            r = lib.get(p)
            if r is None:
                continue
            g = "; ".join(t for t in (x.strip()[:60] for x in nfc(g).split(";")) if t)[:200]
            if g != nfc(r.get("grouping")):
                items.append((p, g))
        if not items:
            raise ValueError("Nichts zu aendern (nur MP3s lassen sich schreiben)")
        return self._start("group", items, label=(nfc(label).strip()[:120] or f"Gruppe geaendert ({len(items)} Lieder)"), field="grouping")

    def undo(self, op_id):
        h = next((x for x in self.history() if x["id"] == op_id), None)
        if h is None or h.get("undone"):
            raise ValueError("Nicht im Protokoll oder schon zurueckgenommen")
        items = [(p, old) for p, old, _new in h["items"]]
        return self._start("undo", items, label="Zurück: " + h["label"], undo_of=op_id, field=h.get("field") or "genre")

    def _start(self, kind, items, label, undo_of=None, field="genre"):
        with self.lock:
            if self.job and self.job.get("state") == "run":
                raise ValueError("Es laeuft schon ein Schreibvorgang")
            self.job = {"kind": kind, "label": label, "state": "run", "done": 0, "total": len(items), "ok": 0, "skip": 0, "err": "",
                        "gone": 0, "notmp3": 0}     # uebersprungen: Datei fehlt am Stick / keine MP3 (Fehlerbericht 08.11.2026)
        t = threading.Thread(target=self._run, args=(kind, items, label, undo_of, field), daemon=True, name="genre-schreiben")
        t.start()
        self.thread = t
        return {"started": True, "total": len(items)}

    def _run(self, kind, items, label, undo_of, field="genre"):
        """field: "genre" (TCON) oder "artist" (TPE1, 13.11.2026); Protokoll und Zuruecknehmen fuer beide."""
        write = self._writer()
        lib = {r["path"]: nfc(r.get(field)) for r in self._lib()}
        done = []
        for i, (path, g) in enumerate(items):
            import stick_hold
            if stick_hold.held():                         # Stick wird ausgeworfen: Rest nicht schreiben
                break
            f = self.locate(path)
            if not f or not f.lower().endswith(".mp3") or not os.path.isfile(f):
                with self.lock:
                    self.job["skip"] += 1
                    self.job["notmp3" if f and os.path.isfile(f) else "gone"] += 1
                    self.job["done"] = i + 1
                continue
            try:
                write(f, {field: g})
                self.written_now.add(path)                     # Nummer-Hinweis: gleich weg, nicht erst nach dem Einlesen
                done.append([path, lib.get(path, ""), g])
                if self.on_written is not None:
                    try:
                        self.on_written(path, {field: g})
                    except Exception as e:                    # noqa: BLE001  Merken darf das Schreiben nie stoeren
                        self.log(f"Genre merken: {e}")
                with self.lock:
                    self.job["ok"] += 1
            except Exception as e:                            # noqa: BLE001  eine Datei kaputt: die anderen weiter
                with self.lock:
                    self.job["skip"] += 1
                    self.job["err"] = f"{os.path.basename(f)}: {str(e)[:80]}"
            with self.lock:
                self.job["done"] = i + 1
        if done:
            self._log_op(kind, label, done, undo_of, field)
        with self.lock:
            self.job["state"] = "done"
        self.log(f"{ {'artist': 'Interpret', 'album': 'Album'}.get(field, 'Genre-Editor')}: {label}: {len(done)} Dateien geschrieben, {len(items) - len(done)} uebersprungen")

    def _log_op(self, kind, label, items, undo_of, field="genre"):
        os.makedirs(self.dir, exist_ok=True)
        rec = {"id": f"{int(self.now() * 1000)}", "t": round(self.now()), "kind": kind, "label": label, "items": items}
        if field != "genre":
            rec["field"] = field
        with open(os.path.join(self.dir, "protokoll.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if undo_of:
                f.write(json.dumps({"undone": undo_of}) + "\n")

    def history(self):
        """Sammelaenderungen, neueste zuerst: [{id, t, kind, label, n, items, undone}]."""
        ops, undone = [], set()
        try:
            with open(os.path.join(self.dir, "protokoll.jsonl"), encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if "undone" in r:
                        undone.add(str(r["undone"]))
                    elif isinstance(r.get("items"), list):
                        ops.append(r)
        except OSError:
            return []
        out = []
        for r in reversed(ops):
            out.append({"id": str(r["id"]), "t": r.get("t", 0), "kind": r.get("kind", ""), "label": r.get("label", ""),
                        "n": len(r["items"]), "items": r["items"], "undone": str(r["id"]) in undone, "field": r.get("field") or "genre"})
        return out

    # ---- Genre fuellen ----
    def fill_candidates(self, with_samples=False):
        """Lieder ohne Genre oder mit Other, je mit Vorschlag: [{path, artist, title, now, want, src, why}]."""
        root = _pn(self.root() or "").rstrip("/")
        lib = self._lib()
        house = {gkey(g): g for g in self.conf.get("house") or []}
        c = self.counts()
        spelled = {}
        for g, n in c.items():
            if g and n > c.get(spelled.get(gkey(g), ""), 0):
                spelled[gkey(g)] = g

        known = house or {k: v for k, v in spelled.items() if c.get(v, 0) >= RARE_N and not is_other(v)}

        def norm_label(g):
            g = first_part(g)
            g = SYNONYMS.get(gkey(g), g)
            hit = house.get(gkey(g)) or spelled.get(gkey(g))
            if hit and (not house or gkey(hit) in house):
                return hit
            words = gkey(g).replace("-", " ").split()       # "Hard Rock" -> Rock, "German Pop" -> Pop (vorhandenes Genre)
            for k, v in sorted(known.items(), key=lambda kv: -len(kv[0])):
                if k in words or (" " in k and k in gkey(g)):
                    return v
            return hit or g

        def rel_of(p):
            if root and _pn(p).startswith(root + "/"):     # schon im Musikordner: ohne Dateizugriff (9000 Lieder, USB-Stick)
                return _pn(p)[len(root) + 1:]
            f = _pn(self.locate(p) or p)
            return f[len(root) + 1:] if root and f.startswith(root + "/") else ""

        by_artist = collections.defaultdict(collections.Counter)
        by_dir = collections.defaultdict(collections.Counter)
        rels = {}
        for r in lib:
            rels[r["path"]] = rel_of(r["path"])
            g = nfc(r.get("genre"))
            if is_other(g):
                continue
            g = norm_label(g)
            if nfc(r.get("artist")):
                by_artist[gkey(r.get("artist"))][g] += 1
            d = top_dir(rels[r["path"]])
            if d:
                by_dir[d.casefold()][g] += 1

        def majority(cnt, min_n, share):
            if not cnt:
                return "", 0
            g, n = cnt.most_common(1)[0]
            tot = sum(cnt.values())
            return (g, n) if n >= min_n and n / tot >= share else ("", 0)

        out = []
        for r in lib:
            now = nfc(r.get("genre"))
            if not is_other(now):
                continue
            rel = rels.get(r["path"], "")
            if not with_samples and top_dir(rel).casefold() in SAMPLE_DIRS:
                continue
            item = {"path": r["path"], "artist": nfc(r.get("artist")), "title": nfc(r.get("title")), "now": now, "want": "", "src": "", "why": ""}
            g, n = majority(by_artist.get(gkey(r.get("artist")), None), 2, 0.6) if nfc(r.get("artist")) else ("", 0)
            if g:
                item.update(want=g, src="interpret", why=f"{n} andere Lieder von {item['artist']} sind {g}")
            else:
                d = top_dir(rel)
                g, n = majority(by_dir.get(d.casefold()), 10, 0.7) if d else ("", 0)
                if g:
                    item.update(want=g, src="ordner", why=f"{n} andere Lieder im Ordner {d} sind {g}")
            net = self.inet.get(r["path"])
            if not item["want"] and isinstance(net, list) and net and net[0]:
                item.update(want=norm_label(net[0]), src="internet", why=f"iTunes sagt „{net[0]}“")
            elif not item["want"] and isinstance(net, list):
                item["why"] = "im Internet nichts gefunden"
            item["house"] = (gkey(item["want"]) in house) if house and item["want"] else None
            out.append(item)
        return out

    def fill_status(self, with_samples=False):
        cands = self.fill_candidates(with_samples)
        n = collections.Counter(x["src"] or "keiner" for x in cands)
        return {"items": cands[:3000], "n": len(cands), "by_src": dict(n), "net": dict(self.net), "job": self.job_status(),
                "net_todo": len(self._net_todo(cands))}

    def _net_todo(self, cands):
        """Was die Internet-Suche noch fragen wuerde (Fehlerbericht 12.11.2026: Knopf nannte 251, gesucht war alles):
        ohne Vorschlag, noch nie gesucht, mit Interpret und Titel; "Other" gilt als vergeben."""
        return [x for x in cands if not x["want"] and not x["now"] and x["path"] not in self.inet and x["artist"] and x["title"]]

    def net_start(self, with_samples=False):
        """Fuer Lieder ohne Vorschlag im Internet nachsehen (iTunes), im Hintergrund, hoechstens alle NET_EVERY_S Sekunden."""
        if self.net.get("busy"):
            return {"started": False}
        todo = self._net_todo(self.fill_candidates(with_samples))
        self.net = {"busy": True, "done": 0, "total": len(todo), "stop": False}
        threading.Thread(target=self._net_run, args=(todo,), daemon=True, name="genre-internet").start()
        return {"started": True, "total": len(todo)}

    def net_stop(self):
        self.net["stop"] = True
        return {"ok": True}

    def _net_run(self, todo):
        look = self.lookup or itunes_genre
        for i, x in enumerate(todo):
            if self.net.get("stop"):
                break
            try:
                g = look(x["artist"], x["title"]) or ""
            except Exception:                                 # noqa: BLE001  Netz weg: spaeter wieder
                g = None
            if g is not None:
                self.inet[x["path"]] = [nfc(g)[:MAX_TEXT], round(self.now())]
                if i % 20 == 0:
                    self._save_json("internet.json", self.inet)
            self.net["done"] = i + 1
            self.sleep(NET_EVERY_S)
        self._save_json("internet.json", self.inet)
        self.net["busy"] = False


def itunes_genre(artist, title):
    """Genre des besten Treffers bei iTunes oder '' (Interpret muss passen)."""
    import tag_edit
    res = tag_edit.itunes(artist, title)
    a = gkey(artist)
    for x in res:
        if x.get("genre") and (gkey(x.get("artist")) == a or a in gkey(x.get("artist")) or gkey(x.get("artist")) in a):
            return x["genre"]
    return ""
