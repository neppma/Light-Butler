"""
auto_tag.py - Auto-Tagger: Lieder ohne Cover im Hintergrund vorrecherchieren (Wunsch von Markus, 07.11.2026).

Macht, was Markus sonst im Fenster "Tag bearbeiten" von Hand tut, nur ohne Klicks, und schreibt nichts von selbst:
  1. Internetsuche mit den vorhandenen Tags (tag_edit.lookup: MusicBrainz, iTunes, Deezer). Passt ein Treffer zu Titel
     und Interpret, genuegt das ("Tags passen").
  2. Sonst Shazam: ffmpeg schneidet 12 s aus der Mitte (Mono, 22050 Hz), der Light-Butler erkennt sie mit SongRec
     (POST /api/sm/recognize, wie der Knopf im Fenster), danach Suche mit dem erkannten Titel.
  3. Cover: zuerst das zum gefundenen Album (Cover Art Archive), sonst iTunes, sonst Deezer; jedes vorher probehalber geholt.
Ergebnis je Lied in ~/Light-Butler-Daten/autotag/vorschlaege.json: jetzt, neu (nur geaenderte Felder), Cover-Adresse, Quelle,
Stufe (gut, unsicher, nichts). Die Seite /musik/vorschlaege zeigt die Liste; erst "Uebernehmen" schreibt in die MP3
(tag_edit.write_tags, Musik und Fingerabdruck bleiben), "Ablehnen" merkt sich das Lied, es kommt nicht wieder.
Gemaechlich: hoechstens eine Shazam-Anfrage alle SHAZAM_GAP_S, Pause zwischen den Liedern, nach einem Fehler laenger.
Aufs Licht wirkt das nicht.
"""
import difflib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.request

import tag_edit as te
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

DATA_DIR = os.path.join(_pfad.daten(), "autotag")   # gemeinsame Ablage von Mixxx-App und Helfer (Fehlerbericht 07.11.2026: der Helfer hatte eine eigene)
FILE = "vorschlaege.json"
GAP_S = 4.0                       # zwischen zwei Liedern
SHAZAM_GAP_S = 20.0               # zwischen zwei Shazam-Anfragen
ERROR_PAUSE_S = 600.0             # Pi oder Internet weg: so lange warten
EXCERPT_S = 12


def norm(s):
    """Fuer Vergleiche: klein, ohne Akzente, ohne Klammerzusaetze, nur Buchstaben und Ziffern."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s)
    s = re.sub(r"\b(feat|ft|featuring)\b.*", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b or (len(a) >= 5 and a in b) or (len(b) >= 5 and b in a):
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_match(suggest, title, artist):
    """Bester Vorschlag zu Titel und Interpret (MusicBrainz vor iTunes vor Deezer, sie sind schon so sortiert) oder None.
    Ohne Interpret nie: "Track 07" fand sonst ein Hoerbuch (Fehler beim Ausprobieren, 07.11.2026), dann fragt der Assistent Shazam."""
    if not norm(artist) or not norm(title):
        return None
    for x in suggest:
        if sim(x.get("title"), title) >= 0.8 and sim(x.get("artist"), artist) >= 0.7:
            return x
    return None


def excerpt_wav(ffmpeg, src, dur, run=subprocess.run):
    """12 s aus der Mitte als WAV (Mono, 22050 Hz, 16 Bit), Bytes."""
    start = max(0.0, min(dur * 0.4, dur - EXCERPT_S)) if dur else 30.0
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
        out = t.name
    try:
        r = run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.1f}", "-t", str(EXCERPT_S), "-i", src,
                 "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", "-af", "dynaudnorm", out],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg: " + (r.stderr or b"").decode("utf-8", "replace").strip()[-150:])
        with open(out, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def shazam(pi_url, wav, opener=urllib.request.urlopen):
    """Ausschnitt an den Light-Butler (SongRec). {"kind", "song", "msg"}."""
    req = urllib.request.Request(pi_url.rstrip("/") + "/api/sm/recognize", data=wav, method="POST",
                                 headers={"Content-Type": "audio/wav"})
    with opener(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def pick_cover(res, best, fetch=te.fetch_cover):
    """Cover-Adresse, die sich wirklich holen laesst: zuerst zum gefundenen Album, dann die anderen. '' = keins."""
    covers = list(res.get("covers") or [])
    album = norm((best or {}).get("album"))
    first = [c for c in covers if best and best.get("mbid") and best["mbid"] in c["url"]]
    same = [c for c in covers if album and norm(c.get("album")) == album and c not in first]
    for c in (first + same + [c for c in covers if c not in first and c not in same])[:4]:
        try:
            fetch(c["url"])
            return c["url"]
        except Exception:                                 # noqa: BLE001  nicht da (Cover Art Archive hat nicht zu jedem Album eines)
            continue
    return ""


FIELDS = ("title", "artist", "album", "albumartist", "year", "track", "genre")
SKIP_DIRS = ()   # Ordner, die gar nicht erscheinen (zurzeit keine)
COVER_ONLY_DIRS = ("samples", "testsamples")   # erscheinen nur zum "Cover erzeugen", ohne Internet und Shazam (Wunsch 07.11.2026)


def cover_only(path):
    """Liegt die Datei in einem Ordner wie SAMPLES, fuer den es keine Suche gibt, nur das Angebot Cover erzeugen?"""
    return any(part.lower() in COVER_ONLY_DIRS for part in str(path or "").split("/")[:-1])


def skipped(path):
    """Liegt die Datei in einem Ordner, den der Assistent auslaesst (zum Beispiel .../SAMPLES/...)?"""
    return any(part.lower() in SKIP_DIRS for part in str(path or "").split("/")[:-1])


def from_filename(path):
    """(Interpret, Titel) aus dem Dateinamen: "Interpret - Titel.mp3", auch mit Tracknummer und Album davor
    ("13 - Sunshine Feeling - 2 Eivissa - 2 Eivissa (Mega Mix).mp3" -> "2 Eivissa", "2 Eivissa (Mega Mix)")."""
    stem = os.path.splitext(os.path.basename(path or ""))[0]
    stem = re.sub(r"(_pn|\s*\(\d{1,2}\))$", "", stem).strip()
    stem = re.sub(r"^\(?\d{1,3}\)?\s*[-._)]\s*", "", stem)          # Tracknummer vorne
    parts = [p.strip() for p in stem.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "", stem


def research(song, lookup=te.lookup, recognize=None, fetch=te.fetch_cover, suspect=False):
    """Ein Lied vorrecherchieren. song: {path, file, title, artist, dur, now: {Feld: Wert}}. recognize(song) -> Shazam-Ergebnis
    oder None (dann ohne Shazam). suspect=True (Titel = Interpret, Wunsch 08.11.2026): Titel und Interpret gelten als falsch,
    zuerst Shazam, dann der Dateiname; beide duerfen Titel und Interpret ersetzen. Rueckgabe: Vorschlag {path, now, new, cover,
    source, level, shazam, t}."""
    now = dict(song.get("now") or {})
    title, artist, dur = now.get("title") or song.get("title") or "", now.get("artist") or song.get("artist") or "", song.get("dur") or 0
    if not title:                                        # ohne Titel: aus dem Dateinamen ("Interpret - Titel.mp3")
        stem = os.path.splitext(os.path.basename(song.get("file") or song["path"]))[0]
        artist, _, title = stem.partition(" - ") if " - " in stem else ("", "", stem)
    if suspect:
        res, best, source, sz = {}, None, "tags", None
        if recognize is not None:                        # zuerst Shazam: die Tags sind ja verdaechtig
            sz = recognize(song)
            if sz and sz.get("kind") == "ok" and sz.get("song"):
                s_ = sz["song"]
                res = lookup(s_.get("artist") or "", s_.get("title") or "", dur)
                best = best_match(res.get("suggest") or [], s_.get("title"), s_.get("artist")) or {"title": s_.get("title"), "artist": s_.get("artist")}
                best = dict(best, genre=best.get("genre") or s_.get("genre") or "")
                source = "shazam"
        if best is None:                                 # dann der Dateiname ("Interpret - Titel.mp3")
            fa, ft = from_filename(song.get("file") or song["path"])
            if fa and ft and norm(fa) != norm(ft):
                res = lookup(fa, ft, dur)
                best = best_match(res.get("suggest") or [], ft, fa) or {"title": ft, "artist": fa}
                source = "datei"
        return _proposal(song, now, res, best, source, sz, title, fetch, suspect=True)
    res = lookup(artist, title, dur)
    best, source, sz = best_match(res.get("suggest") or [], title, artist), "tags", None
    if best is None:                                     # zweiter Versuch mit dem Dateinamen, bevor Shazam gefragt wird
        fa, ft = from_filename(song.get("file") or song["path"])   # (Wunsch 07.11.2026: Dateiname zum Erkennen heranziehen)
        if ft and (norm(ft) != norm(title) or norm(fa) != norm(artist)):
            res2 = lookup(fa, ft, dur)
            b2 = best_match(res2.get("suggest") or [], ft, fa)
            if b2 is not None:
                res, best, source = res2, b2, "datei"
    if best is None and recognize is not None:
        sz = recognize(song)
        if sz and sz.get("kind") == "ok" and sz.get("song"):
            s = sz["song"]
            res = lookup(s.get("artist") or "", s.get("title") or "", dur)
            best = best_match(res.get("suggest") or [], s.get("title"), s.get("artist")) or {"title": s.get("title"), "artist": s.get("artist")}
            best = dict(best, genre=best.get("genre") or s.get("genre") or "")
            source = "shazam"
    return _proposal(song, now, res, best, source, sz, title, fetch)


def _proposal(song, now, res, best, source, sz, title, fetch, suspect=False):
    new, level, cover = {}, "nichts", ""
    if best:
        for k in FIELDS:                                 # nur ergaenzen: vorhandene Angaben bleiben (Wunsch: vervollstaendigen)
            v, old_v = str(best.get(k) or "").strip(), str(now.get(k) or "").strip()
            if not v or norm(v) == norm(old_v):
                continue
            if not old_v or (k in ("title", "artist") and (source == "shazam" or suspect)):   # Titel/Interpret nur nach Shazam (oder verdaechtig)
                new[k] = v
        if not now.get("genre") and not new.get("genre"):   # Genre: iTunes kennt es oft, MusicBrainz nicht
            g = next((x.get("genre") for x in res.get("suggest") or [] if x.get("genre") and sim(x.get("title"), best.get("title")) >= 0.8), "")
            if g:
                new["genre"] = g
        cover = pick_cover(res, best, fetch)
        level = "gut"
        if source == "shazam":                           # Shazam-Titel passt nicht zum alten Titel oder Dateinamen: unsicher
            old = f"{now.get('artist') or ''} {now.get('title') or ''} {os.path.basename(song.get('file') or song['path'])}"
            if sim(best.get("title"), title) < 0.6 and norm(best.get("title")) not in norm(old):
                level = "unsicher"
        if suspect and source != "shazam":               # nur aus dem Dateinamen: selbst ansehen
            level = "unsicher"
        if not new and not cover:
            level = "nichts"
    out = {"path": song["path"], "now": {k: now.get(k, "") for k in FIELDS}, "new": new, "cover": cover, "source": source,
           "level": level, "shazam": (sz or {}).get("song") if sz else None, "t": round(time.time())}
    if suspect:
        out["why"] = "ti"                                # Seite: Reiter "Titel = Interpret"
    return out


class AutoTagger:
    """Laeuft in der Mixxx-Bruecke (eigener Thread). songs() -> [{path, file, title, artist, dur}] der Bibliothek (nur MP3)."""

    def __init__(self, songs, pi_url="", base=DATA_DIR, log=None, has_cover=None, ffmpeg=None):
        self.songs, self.pi_url, self.base, self.log = songs, pi_url, base, log or (lambda t: None)
        self.path = os.path.join(base, FILE)
        self.has_cover = has_cover or (lambda f: False)
        self.ffmpeg = ffmpeg
        self.lock = threading.Lock()
        self.save_lock = threading.Lock()
        self.stop_ev = threading.Event()
        self.thread, self.current, self.error, self.shazam_t, self.prune_t = None, "", "", 0.0, 0.0
        self.ti_queue = []                                 # Titel = Interpret: gezielt recherchieren (Musik-DB, Assistent)
        self.wake_ev = threading.Event()                   # weckt den Faden aus der Pause (Knopf Assistent, Fehlerbericht 08.11.2026)
        self.lookup = te.lookup                            # Suche im Internet (Tests setzen eine eigene)
        self.items, self.on = self._load()
        self.auto = self._load_auto()                    # "gut" automatisch uebernehmen (Wunsch 07.11.2026, Standard aus)
        self.on_applied = None                           # Bruecke: Liste am Pi gleich mit den neuen Angaben (Forwarder.tags_written)
        self.auto_thread, self.auto_n, self.auto_err = None, 0, ""
        self.auto_lock = threading.Lock()                # nie zweimal dasselbe Lied gleichzeitig schreiben (Lauf und Suche)
        for k, v in self.items.items():                  # fruehere Internet-Vorschlaege fuer Samples: jetzt nur Cover erzeugen
            if cover_only(k) and v.get("level") != "cover" and v.get("state", "offen") in ("offen", "abgelehnt"):
                v.update(level="cover", new={}, cover="", source="ordner", state="offen")

    # ---- Ablage ----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            return dict(d.get("items") or {}), bool(d.get("on"))
        except (OSError, ValueError, AttributeError):
            return {}, False

    def _load_auto(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return bool(json.load(f).get("auto"))
        except (OSError, ValueError, AttributeError):
            return False

    def _save(self):
        """Ablage schreiben. Mehrere Ablaeufe speichern gleichzeitig (Start und Hintergrund-Lauf): Text unter der Sperre bilden
        (die Liste aendert sich sonst waehrend des Schreibens), schreiben nacheinander (Fehler beim Push 07.11.2026)."""
        os.makedirs(self.base, exist_ok=True)
        with self.lock:
            text = json.dumps({"on": self.on, "auto": getattr(self, "auto", False), "items": self.items}, ensure_ascii=False)
        with self.save_lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self.path)

    # ---- Liste fuer die Seite ----
    def todo(self):
        """Lieder ohne Cover, die noch keinen Vorschlag haben (und nicht abgelehnt oder erledigt sind)."""
        out = []
        for s in self.songs():
            old = self.items.get(s["path"])
            if old is not None and not self._again(old):
                continue
            if not s["file"].lower().endswith(".mp3") or skipped(s["path"]) or not os.path.exists(s["file"]):
                continue
            try:
                if self.has_cover(s["file"]):
                    continue
            except OSError:
                continue
            out.append(s)
        return out

    @staticmethod
    def _again(item):
        """Ein zweites Mal suchen (Fehlerbericht 08.11.2026): Vorschlag uebernommen, aber ohne Cover (z.B. Titel erst per Shazam
        richtig). Mit dem richtigen Titel findet die Suche das Cover oft. Nur einmal (again), danach bleibt es erledigt."""
        return (item.get("state") == "erledigt" and not item.get("again") and not item.get("cover")
                and any(v for v in (item.get("new") or {}).values()))

    def status(self):
        with self.lock:                                   # dieselbe Auswahl wie list() (Fehlerbericht 07.11.2026)
            vis = {k: v for k, v in self.items.items() if not skipped(k)}
            st = [x.get("state", "offen") for x in vis.values()]
        lv = [x.get("level") for x in self.list()]        # offene: genau die, die die Liste zeigt (fehlende Dateien nicht)
        st = [x for x in st if x != "offen"] + ["offen"] * len(lv)
        running = self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set()
        return {"on": self.on, "running": running, "current": self.current if running else "", "error": self.error,
                "open": st.count("offen"), "done": st.count("erledigt"), "rejected": st.count("abgelehnt"),
                "ti_queue": len(self.ti_queue), "ti": sum(1 for x in self.list() if x.get("why") == "ti"),
                "good": lv.count("gut"), "unsure": lv.count("unsicher"), "none": lv.count("nichts"), "cover": lv.count("cover"),
                "shazam": bool(self.pi_url and self.ffmpeg), "auto": self.auto, "auto_n": self.auto_n, "auto_err": self.auto_err,
                "auto_busy": bool(self.auto_thread is not None and self.auto_thread.is_alive())}

    def list(self, rej=False):
        """Offene Vorschlaege; mit rej auch die abgelehnten (Reiter "Abgelehnt", Wunsch 11.11.2026), gekennzeichnet mit rej=True."""
        with self.lock:
            out = [dict(v, path=k, rej=v.get("state") == "abgelehnt") for k, v in self.items.items()
                   if (v.get("state", "offen") == "offen" or (rej and v.get("state") == "abgelehnt")) and not skipped(k)]
        songs = {s_["path"]: s_ for s_ in self.songs()}
        if songs:                                         # Datei weg (geloescht, nur noch Eintrag in Mixxx): nicht zeigen, schreiben
            out = [x for x in out if x["path"] in songs and os.path.exists(songs[x["path"]]["file"])]   # ginge nicht (Fehlerbericht 07.11.2026)
        for x in out:                                     # Spieldauer fuer die Seite (aeltere Vorschlaege hatten sie nicht)
            x["dur"] = x.get("dur") or (songs.get(x["path"]) or {}).get("dur") or 0
        return out

    def prune_soon(self, every_s=60.0):
        """Beim Oeffnen der Seite: hoechstens jede Minute im Hintergrund ausraeumen (auch wenn der Tagger angehalten ist)."""
        if time.time() - self.prune_t < every_s:
            return
        self.prune_t = time.time()
        threading.Thread(target=self.prune, name="auto-tagger-aufraeumen", daemon=True).start()

    def research_paths(self, paths, start=True):
        """Musik-DB, Knopf Assistent bei "Titel = Interpret": diese Lieder zuerst recherchieren (Shazam, dann Dateiname), auch mit
        Cover und auch, wenn es schon einen Vorschlag gab. Rueckgabe: wie viele neu in der Warteschlange."""
        known = {s_["path"] for s_ in self.songs()}
        n = 0
        with self.lock:
            for p in paths:
                if p in known and p not in self.ti_queue:
                    self.ti_queue.append(p)
                    n += 1
        if n and start and (self.thread is None or not self.thread.is_alive()):
            self.start()
        if n:
            self.wake_ev.set()                             # schlaeft er gerade (keine Lieder ohne Cover): gleich los
        return n

    def _ti_step(self):
        """Ein Lied aus der Warteschlange Titel = Interpret. False = nichts zu tun."""
        with self.lock:
            p = self.ti_queue[0] if self.ti_queue else None
        if p is None:
            return False
        s = next((x for x in self.songs() if x["path"] == p), None)
        try:
            if s is not None and os.path.exists(s["file"]):
                self.current = f"{s.get('artist') or ''} - {s.get('title') or ''}".strip(" -")[:120]
                now = te.read_tags(s["file"])["fields"]
                prop = research(dict(s, now=now), lookup=self.lookup, recognize=self.recognize, suspect=True)
                prop.pop("path", None)
                prop["dur"] = round(float(s.get("dur") or 0), 1)
                with self.lock:
                    self.items[p] = dict(prop, state="offen")
                self._save()
        except te.TagError as e:
            with self.lock:
                self.items[p] = {"state": "offen", "level": "nichts", "now": {}, "new": {}, "cover": "", "source": "", "why": "ti",
                                 "error": str(e)[:120], "t": round(time.time())}
            self._save()
        finally:
            with self.lock:
                if self.ti_queue and self.ti_queue[0] == p:
                    self.ti_queue.pop(0)
        return True

    def prune(self):
        """Vorschlaege zu Liedern, die inzwischen ein Cover haben (anderswo bearbeitet): erledigt. Rueckgabe: wie viele.
        Vorschlaege "Titel = Interpret" bleiben (es geht dort nicht ums Cover)."""
        with self.lock:
            open_ = [k for k, v in self.items.items() if v.get("state", "offen") == "offen" and v.get("why") != "ti"]
        files = {s_["path"]: s_["file"] for s_ in self.songs()}
        n = 0
        for k in open_:
            f = files.get(k)
            try:
                if f and self.has_cover(f):
                    with self.lock:
                        self.items[k]["state"] = "erledigt"
                    n += 1
            except OSError:
                continue
        if n:
            self._save()
        return n

    # ---- Entscheidungen ----
    def reject(self, path):
        with self.lock:
            if path not in self.items:
                raise KeyError("kein Vorschlag zu diesem Lied")
            self.items[path]["state"] = "abgelehnt"
        self._save()

    def unreject(self, path):
        """Abgelehnten Vorschlag wieder anbieten."""
        with self.lock:
            if path not in self.items:
                raise KeyError("kein Vorschlag zu diesem Lied")
            self.items[path]["state"] = "offen"
        self._save()

    def mark_done(self, path):
        """Im Fenster Tag bearbeiten selbst geschrieben: Vorschlag erledigt."""
        with self.lock:
            if path not in self.items:
                raise KeyError("kein Vorschlag zu diesem Lied")
            self.items[path]["state"] = "erledigt"
        self._save()

    def apply(self, path, file, fields=None, cover=True, write=te.write_tags, fetch=te.fetch_cover):
        """Vorschlag in die MP3 schreiben (fields: nur diese Felder, None = alle vorgeschlagenen; cover: Cover mit)."""
        with self.lock:
            it = dict(self.items.get(path) or {})
        if not it:
            raise KeyError("kein Vorschlag zu diesem Lied")
        new = it.get("new") or {}
        put = {k: v for k, v in new.items() if fields is None or k in fields}
        img = fetch(it["cover"]) if (cover and it.get("cover")) else None
        if not put and img is None:
            raise ValueError("nichts zu schreiben")
        res = write(file, put, cover=img)
        with self.lock:
            self.items[path]["state"] = "erledigt"
        self._save()
        return res

    # ---- Lauf ----
    # ---- "gut" automatisch uebernehmen ----
    @staticmethod
    def _worth(v):
        """Vorschlag "gut" mit etwas zum Schreiben (neue Angaben oder Cover), wie die Seite ihn vorab anhakt."""
        return (v.get("state", "offen") == "offen" and v.get("level") == "gut" and bool(v.get("new") or v.get("cover"))
                and v.get("why") != "ti")                # Titel = Interpret: immer selbst entscheiden

    def apply_auto(self, path, file):
        """Einen guten Vorschlag schreiben und der Bruecke melden. Fehler (Cover-Server weg): bleibt offen, kommt wieder."""
        with self.auto_lock:
            if not self._worth(self.items.get(path) or {}):  # inzwischen erledigt (Seite oder anderer Lauf)
                return False
            return self._apply_auto(path, file)

    def _apply_auto(self, path, file):
        try:
            new = dict((self.items.get(path) or {}).get("new") or {})
            self.apply(path, file)
            self.auto_n += 1
            self.log(f"Auto-Tagger: automatisch uebernommen (gut): {file}")
            if self.on_applied is not None and new:
                try:
                    self.on_applied(path, new)
                except Exception as e:                    # noqa: BLE001  Merken darf das Schreiben nie stoeren
                    self.log(f"Tags merken: {e}")
            return True
        except Exception as e:                            # noqa: BLE001  einzelner Fehler haelt den Lauf nicht an
            self.auto_err = f"{os.path.basename(file)}: {str(e)[:100]}"
            self.log(f"Auto-Tagger: automatisch uebernehmen ging nicht: {self.auto_err}")
            return False

    def auto_batch(self, sleep=time.sleep):
        """Alle offenen guten Vorschlaege schreiben, einen nach dem anderen (eigener Thread)."""
        songs = {s["path"]: s for s in self.songs()}
        with self.lock:
            todo = [k for k, v in self.items.items() if self._worth(v) and not skipped(k)]
        for p in todo:
            if not self.auto or getattr(self, "paused", False):
                return
            s = songs.get(p)
            if s and os.path.exists(s["file"]):
                self.apply_auto(p, s["file"])
                sleep(0.5)

    def set_auto(self, on):
        """Schalter "Gute automatisch uebernehmen": an = gleich alle offenen guten schreiben, neue gute sofort."""
        self.auto = bool(on)
        self._save()
        if self.auto and not (self.auto_thread is not None and self.auto_thread.is_alive()):
            self.auto_err = ""
            self.auto_thread = threading.Thread(target=self.auto_batch, name="auto-tagger-gut", daemon=True)
            self.auto_thread.start()

    def recognize(self, song):
        if not (self.pi_url and self.ffmpeg):
            return None
        wait = SHAZAM_GAP_S - (time.time() - self.shazam_t)
        if wait > 0 and self.stop_ev.wait(wait):
            return None
        self.shazam_t = time.time()
        res = shazam(self.pi_url, excerpt_wav(self.ffmpeg, song["file"], song.get("dur") or 0))
        if res.get("error") or res.get("kind") in ("offline", "missing", "error"):
            raise RuntimeError("Shazam: " + str(res.get("error") or res.get("msg") or res.get("kind")))
        return res

    def run(self):
        while not self.stop_ev.is_set():
            if self._ti_step():                          # Titel = Interpret geht vor (auf Knopfdruck in der Musik-DB)
                continue
            self.prune()
            todo = self.todo()
            if not todo:
                self.current = ""
                if self.auto:                             # liegengebliebene gute (Cover-Server war weg) nochmal versuchen
                    self.auto_batch()
                self.wake_ev.wait(300.0)                  # spaeter wieder schauen (neue Lieder, neue Cover-Pruefung); Knopf weckt sofort
                self.wake_ev.clear()
                if self.stop_ev.is_set():
                    return
                continue
            for s in todo:
                if self.stop_ev.is_set():
                    return
                import stick_hold
                if stick_hold.held():                     # Stick wird ausgeworfen: warten, bis er wieder da ist
                    self.current = ""
                    self.wake_ev.wait(30.0)
                    self.wake_ev.clear()
                    break
                while self._ti_step():                   # Knopf in der Musik-DB: auch mitten im grossen Durchgang zuerst
                    if self.stop_ev.is_set():
                        return
                self.current = f"{s.get('artist') or ''} - {s.get('title') or ''}".strip(" -")[:120]
                try:
                    now = te.read_tags(s["file"])["fields"]
                    if cover_only(s["path"]):                 # Samples: nichts suchen, nur Cover erzeugen anbieten
                        prop = {"now": {k: now.get(k, "") for k in FIELDS}, "new": {}, "cover": "", "source": "ordner", "level": "cover",
                                "shazam": None, "t": round(time.time())}
                    else:
                        prop = research(dict(s, now=now), recognize=self.recognize)
                    prop.pop("path", None)
                    prop["dur"] = round(float(s.get("dur") or 0), 1)
                    if s["path"] in self.items:            # zweiter Durchgang: nie ein drittes Mal
                        prop["again"] = 1
                    with self.lock:
                        self.items[s["path"]] = dict(prop, state="offen")
                    self._save()
                    self.error = ""
                    if self.auto and self._worth(self.items[s["path"]]):   # frisch gefunden und gut: gleich schreiben
                        self.apply_auto(s["path"], s["file"])
                except te.TagError as e:                   # Datei nicht lesbar (alte ID3-Form): merken, nicht wieder
                    with self.lock:
                        self.items[s["path"]] = {"state": "offen", "level": "nichts", "now": {}, "new": {}, "cover": "", "source": "",
                                                 "error": str(e)[:120], "t": round(time.time()), "again": 1}
                    self._save()
                except Exception as e:                     # noqa: BLE001  Pi oder Internet weg: spaeter weiter, nichts merken
                    self.error = str(e)[:150]
                    self.log(f"Auto-Tagger: {self.error}")
                    if self.stop_ev.wait(ERROR_PAUSE_S):
                        return
                    break
                if not cover_only(s["path"]) and self.stop_ev.wait(GAP_S):   # Samples ohne Suche: gleich das naechste
                    return

    def start(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set():
                return
            self.on = True
            self.stop_ev = threading.Event()
            self.thread = threading.Thread(target=self.run, name="auto-tagger", daemon=True)
            self.thread.start()
        self._save()

    def stop(self):
        with self.lock:
            self.on = False
        self.stop_ev.set()
        self.wake_ev.set()
        self._save()

    def pause(self):
        """Anhalten, ohne es sich zu merken (die Mixxx-Bruecke gibt an den Helfer ab, dort laeuft er weiter)."""
        self.stop_ev.set()
        self.wake_ev.set()
        self.paused = True

    def resume(self):
        if self.on:
            self.start()
        if self.auto:                                     # nach Neustart: liegengebliebene gute (Cover-Server war weg) schreiben
            self.set_auto(True)
