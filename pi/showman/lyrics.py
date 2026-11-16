#!/usr/bin/env python3
"""
lyrics.py - Liedtexte von LRCLIB (lrclib.net): frei, ohne Schluessel. Nur auf Knopfdruck, Titel und Interpret gehen dorthin, keine Musik.

Zeilen mit Zeiten gelten nur, wenn die Laenge zum Lied passt: Ein Remix hat andere Zeiten als das Original, dann lieber nur der Text.
Die Texte gehoeren ihren Rechteinhabern und bleiben in der Showdatei auf dem Pi, nichts davon im Git.
"""
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib

API = "https://lrclib.net/api/search"
AGENT = "Light-Butler Lichtsteuerung"
LINE_MAX_S = 12.0             # laenger steht eine Zeile nie, auch wenn der naechste Eintrag spaeter kommt
DUR_OK_S = 2.5                # so weit darf die Laenge abweichen, damit die Zeiten stimmen
LRC_RE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def parse_lrc(text):
    """LRC-Text in [[Sekunden, Zeile], ...]. Mehrere Zeitstempel und Leerzeilen sind erlaubt, Unsinn faellt weg."""
    out = []
    for raw in str(text or "").splitlines():
        stamps, line = [], raw.strip()
        while True:
            m = LRC_RE.match(line)
            if not m:
                break
            stamps.append(int(m.group(1)) * 60 + float(m.group(2)))
            line = m.group(3).strip()
        for t in stamps:
            out.append([round(t, 2), line])
    return sorted(out, key=lambda x: x[0])


def _words(s):
    return {w.casefold() for w in WORD_RE.findall(str(s or ""))}


def split_title(title):
    """"Interpret - Titel (Remix)" in (Interpret, Titel). Ohne Trennstrich: nur Titel."""
    t = str(title or "").strip()
    a, sep, b = t.partition(" - ")
    return (a.strip(), b.strip()) if sep else ("", t)


def queries(title):
    """Suchbegriffe, vom genauesten zum groebsten."""
    artist, track = split_title(title)
    base = re.sub(r"[\(\[].*?[\)\]]", " ", track)
    first = re.split(r"\s+(?:&|feat\.?|ft\.?|featuring|,|x|vs\.?)\s+", artist, maxsplit=1, flags=re.I)[0]
    out = []
    for q in (f"{artist} {track}", f"{first} {base}", base):
        q = " ".join(q.split())
        if q and q not in out:
            out.append(q)
    return out


def _score(rec, want, base, dur):
    words = _words(rec.get("trackName"))
    if not base <= (words | _words(rec.get("artistName"))) and not base & words:
        return None
    d = abs(float(rec.get("duration") or 0) - dur) if dur else 999.0
    fits = (d <= DUR_OK_S or not dur) and bool(rec.get("syncedLyrics"))
    return (fits, len(want & (words | _words(rec.get("artistName")))), -d, bool(rec.get("plainLyrics")))


def pick(results, title, dur):
    """Bester Treffer: zuerst Zeiten mit passender Laenge, dann die meisten gleichen Woerter."""
    artist, track = split_title(title)
    base = _words(re.sub(r"[\(\[].*?[\)\]]", " ", track))
    want = _words(artist) | _words(track)
    best, top = None, None
    for rec in results if isinstance(results, list) else []:
        if not isinstance(rec, dict) or rec.get("instrumental") or not (rec.get("syncedLyrics") or rec.get("plainLyrics")):
            continue
        s = _score(rec, want, base, dur)
        if s is not None and (top is None or s > top):
            best, top = rec, s
    return best


def to_lyrics(rec, dur):
    """Treffer ins Format der Showdatei. Passt die Laenge nicht, gibt es nur den Text ohne Zeiten."""
    fits = not dur or abs(float(rec.get("duration") or 0) - dur) <= DUR_OK_S    # Laenge unbekannt (Shazam): dem Titel vertrauen
    lines = parse_lrc(rec.get("syncedLyrics")) if fits else []    # Leerzeilen bleiben: sie sagen, wann eine Zeile aufhoert
    while lines and not lines[0][1]:
        lines.pop(0)
    plain = str(rec.get("plainLyrics") or "") or "\n".join(x[1] for x in parse_lrc(rec.get("syncedLyrics")) if x[1])
    return {"lines": lines, "plain": plain, "source": "lrclib", "title": f"{rec.get('artistName', '')} - {rec.get('trackName', '')}",
            "duration": float(rec.get("duration") or 0)}


def fetch(title, dur, opener=urllib.request.urlopen, timeout=8.0):
    """Liedtext suchen. Wirft ValueError mit einer Meldung fuers Panel."""
    results = []
    for q in queries(title):
        url = API + "?" + urllib.parse.urlencode({"q": q})
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        try:
            with opener(req, timeout=timeout) as r:
                found = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raise ValueError(f"Liedtext: Fehler {e.code} bei LRCLIB") from None
        except (urllib.error.URLError, OSError, ValueError):
            raise ValueError("Liedtext: LRCLIB nicht erreichbar") from None
        results += found if isinstance(found, list) else []
        rec = pick(results, title, dur)
        if rec is not None and rec.get("syncedLyrics") and (not dur or abs(float(rec.get("duration") or 0) - dur) <= DUR_OK_S):
            return to_lyrics(rec, dur)
    rec = pick(results, title, dur)
    if rec is None:
        raise ValueError("Liedtext: nichts gefunden")
    return to_lyrics(rec, dur)


def line_end(lines, i):
    """Wann Zeile i aufhoert. LRC kennt nur Anfaenge: spaetestens beim naechsten Eintrag, eine Leerzeile dort ist ein echtes Ende.
    Sonst geschaetzt aus der Zahl der Woerter, damit eine Zeile vor einem langen Instrumental nicht ewig stehen bleibt. Gleiche Rechnung in core.js."""
    t, text = lines[i][0], lines[i][1]
    guess = t + min(LINE_MAX_S, 2.0 + 0.6 * len(str(text).split()))
    return min(guess, lines[i + 1][0]) if i + 1 < len(lines) else guess


def line_at(lines, pos):
    """Die Zeile, die an dieser Stelle gerade dran ist; leer vor der ersten, in Pausen des Textes und nach ihrem Ende."""
    cur = ""
    for i, (t, text) in enumerate(lines or []):
        if t > pos:
            break
        cur = text if pos < line_end(lines, i) else ""
    return cur


class LyricCache:
    """Zeilen je Lied auf dem Pi: einmal geholt, auch wenn nichts gefunden wurde. Kompakt in einer SQLite-Datei (bei 9500 Liedern weder Speicher voll
    noch staendig die SD-Karte neu schreiben). get wartet nie: die Suche laeuft nebenbei."""
    RETRY_S = 600.0               # kein Netz: erst nach dieser Zeit wieder versuchen

    def __init__(self, path, opener=urllib.request.urlopen, sync=False):
        self.path, self.opener, self.sync = path, opener, sync
        self.tried, self.busy, self.memo, self.msg = {}, False, (None, None), ""
        self.lock = threading.Lock()
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS lyrics (k TEXT PRIMARY KEY, n INTEGER, z BLOB)")
            db.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")

    def _db(self):
        db = sqlite3.connect(self.path, timeout=5.0)
        db.execute("PRAGMA synchronous=NORMAL")
        return db

    @staticmethod
    def key(title, dur):
        return f"{unicodedata.normalize('NFC', str(title)).casefold()}|{int(round(float(dur or 0)))}"

    def entry(self, title, dur):
        """{"lines", "plain"} aus der Datei, None = noch nie gesucht. Laenge aus Mixxx und Analyse duerfen um 1 s abweichen; ohne Laenge (Shazam) zaehlt der Titel."""
        d = int(round(float(dur or 0)))
        name = self.key(title, dur).rsplit("|", 1)[0]
        with self._db() as db:
            row = None
            if d:
                for x in (d, d - 1, d + 1):
                    row = db.execute("SELECT z FROM lyrics WHERE k=?", (f"{name}|{x}",)).fetchone()
                    if row:
                        break
            else:
                row = db.execute("SELECT z FROM lyrics WHERE k>=? AND k<? ORDER BY n DESC LIMIT 1", (name + "|", name + "|~")).fetchone()
        if not row:
            return None
        v = json.loads(zlib.decompress(row[0]).decode("utf-8"))
        return v if isinstance(v, dict) else {"lines": v, "plain": ""}

    def lookup(self, title, dur):
        """Zeilen aus der Datei, [] = gesucht und keine Zeiten gefunden, None = noch nie gesucht."""
        e = self.entry(title, dur)
        return None if e is None else e["lines"]

    def store(self, title, dur, lines, plain=""):
        z = zlib.compress(json.dumps({"lines": lines, "plain": "" if lines else str(plain)[:20000]}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))   # mit Zeiten steckt der Text schon in den Zeilen
        with self.lock, self._db() as db:
            db.execute("INSERT OR REPLACE INTO lyrics VALUES (?,?,?)", (self.key(title, dur), len(lines), z))

    def keys(self):
        """Alle gesuchten Lieder: Schluessel -> Anzahl Zeilen mit Zeiten (0 = nichts oder nur Text gefunden). Fuer die Musik-Datenbank."""
        with self._db() as db:
            return {k: int(n or 0) for k, n in db.execute("SELECT k, n FROM lyrics")}

    def counts(self):
        """(alle gesuchten Lieder, davon mit Zeilen)."""
        with self._db() as db:
            return db.execute("SELECT COUNT(*), COALESCE(SUM(n>0),0) FROM lyrics").fetchone()

    def meta(self, k, v=None):
        with self._db() as db:
            if v is not None:
                db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, str(v)))
                return v
            row = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
            return row[0] if row else None

    def get(self, title, dur, now=None):
        """Zeilen mit Zeiten, wenn bekannt. Sonst []: stoesst einmalig die Suche an. Laeuft bei jeder Abfrage des Panels: das aktuelle Lied bleibt im Speicher."""
        return self.get_entry(title, dur, now)["lines"]

    def get_entry(self, title, dur, now=None):
        """Wie get, aber {"lines", "plain"}: auch der Text ohne Zeiten zum Mitlesen."""
        k = self.key(title, dur)
        none = {"lines": [], "plain": ""}
        if self.memo[0] == k:
            return self.memo[1]
        try:
            hit = self.entry(title, dur)
        except (sqlite3.Error, ValueError, OSError):
            return none
        if hit is not None:
            self.memo = (k, hit)
            return hit
        now = time.time() if now is None else now
        with self.lock:
            if self.busy or now - self.tried.get(k, -1e12) < self.RETRY_S:
                return none
            self.busy, self.tried[k] = True, now
        if self.sync:
            self._load(title, dur)
            return self.entry(title, dur) or none
        threading.Thread(target=self._load, args=(title, dur), daemon=True).start()
        return none

    def _load(self, title, dur):
        try:
            self.fetch_store(title, dur)
        except (ValueError, sqlite3.Error, OSError) as e:      # Netz oder LRCLIB weg: nicht merken, spaeter neu versuchen
            print(f"Liedtext: {type(e).__name__}", flush=True)
        finally:
            self.busy = False

    def refetch(self, title, dur, query=None):
        """Von Hand: dieses Lied neu suchen, auf Wunsch mit anderem Suchbegriff. Der alte Eintrag bleibt, bis ein Treffer da ist. Wartet nie."""
        with self.lock:
            if self.busy:
                raise ValueError("Es laeuft gerade schon eine Suche")
            self.busy = True
        self.msg = "Suche ..."
        if self.sync:
            self._refetch(title, dur, query)
        else:
            threading.Thread(target=self._refetch, args=(title, dur, query), daemon=True).start()

    def _refetch(self, title, dur, query):
        try:
            y = fetch(str(query or title), float(dur or 0), opener=self.opener)
            name = self.key(title, dur).rsplit("|", 1)[0]
            with self.lock, self._db() as db:                 # ein Lied, ein Eintrag: auch die mit anderer Laenge ersetzen
                db.execute("DELETE FROM lyrics WHERE k>=? AND k<?", (name + "|", name + "|~"))
            self.store(title, dur, y["lines"], y["plain"])
            self.memo = (None, None)
            self.msg = f"{len([x for x in y['lines'] if x[1]])} Zeilen: {y['title']}"[:120] if y["lines"] else f"Nur Text ohne Zeiten: {y['title']}"[:120]
        except ValueError as e:
            self.msg = str(e)[:120]
        except (sqlite3.Error, OSError) as e:
            self.msg = f"Liedtext nicht gespeichert ({type(e).__name__})"
        finally:
            self.busy = False

    def fetch_store(self, title, dur, opener=None):
        """Suchen und merken. Wirft ValueError, wenn die Suche scheiterte: dann bleibt das Lied offen."""
        try:
            y = fetch(title, float(dur or 0), opener=opener or self.opener)
        except ValueError as e:
            if "nichts gefunden" not in str(e):
                raise
            y = {"lines": [], "plain": ""}
        self.store(title, dur, y["lines"], y["plain"])
        return y["lines"]


class LyricBulk:
    """Alle Lieder der Mixxx-Bibliothek vorab holen, langsam im Hintergrund wie die Analyse. Das Licht wartet nie, unterbrechen und weitermachen gehen jederzeit."""
    GAP_S = 3.0                   # Abstand zwischen zwei Anfragen: LRCLIB ist frei, wir wollen sie nicht belasten
    NET_WAIT_S = 300.0            # kein Netz: so lange warten, dann weiter
    MIN_FREE = 500 * 1024 * 1024  # so viel bleibt auf der SD-Karte frei
    FLAG = "bulk_on"

    def __init__(self, cache, library):
        self.cache, self.library = cache, library
        self.stop_ev = threading.Event()
        self.thread = None
        self.error, self.current = "", ""
        self.total = 0

    def start(self, wait=True):
        if self.thread is not None and self.thread.is_alive():
            return self.status()
        self.cache.meta(self.FLAG, "1")
        self.error = ""
        self.stop_ev.clear()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        return self.status()

    def stop(self):
        self.cache.meta(self.FLAG, "0")
        self.stop_ev.set()
        return self.status()

    def resume(self):
        """Nach einem Neustart des Dienstes weitermachen, wenn es lief."""
        if self.cache.meta(self.FLAG) == "1":
            self.start()

    def _throttled(self, req, timeout=0):
        if self.stop_ev.wait(self.GAP_S):                     # jede einzelne Anfrage mit Abstand, auch die zweite und dritte Suche zu einem Lied
            raise urllib.error.URLError("angehalten")
        return self.cache.opener(req, timeout=timeout)

    def run(self):
        while not self.stop_ev.is_set():
            lib = self._lib()
            self.total = len(lib)
            with self.cache._db() as db:
                known = {r[0] for r in db.execute("SELECT k FROM lyrics")}    # einmal lesen: nicht bei jedem Lied 9500 Abfragen
            open_songs = [(x[0], x[1]) for x in lib if not self._known(known, x[0], x[1])]
            if not open_songs:
                if lib and self.total == len(lib):
                    self.cache.meta(self.FLAG, "0")
                    self.current = ""
                    return
                if self.stop_ev.wait(5.0):                    # die Bibliothek kommt nach einem Neustart erst nach und nach
                    return
                continue
            for title, dur in open_songs:
                if self.stop_ev.is_set():
                    return
                if shutil.disk_usage(os.path.dirname(os.path.abspath(self.cache.path))).free < self.MIN_FREE:
                    self.error = "Zu wenig Platz auf der SD-Karte"
                    self.cache.meta(self.FLAG, "0")
                    return
                self.current = str(title)[:120]
                try:
                    self.cache.fetch_store(title, dur, opener=self._throttled)
                    self.error = ""
                except ValueError as e:
                    if self.stop_ev.is_set():
                        return
                    self.error = str(e)[:120]
                    if self.stop_ev.wait(self.NET_WAIT_S):
                        return

    def _lib(self):
        """Titel der Bibliothek. Der Mac schickt sie nur alle 10 Minuten: der Pi merkt sie sich, damit es auch nach einem Neustart
        und ohne Mac weitergeht. Die aktuelle gilt, auch wenn sie kuerzer ist (geloeschte Lieder); vorher blieb die alte,
        laengere stehen, und die Anzeige erreichte nie 100 % (Fehlerbericht 06.11.2026)."""
        lib = [[x[0], x[1]] for x in self.library() if isinstance(x, (list, tuple)) and len(x) >= 2 and x[0]]
        if lib:
            if self.cache.meta("lib_n") != str(len(lib)) or not self.cache.meta("lib"):
                self.cache.meta("lib", json.dumps(lib, ensure_ascii=False))
                self.cache.meta("lib_n", str(len(lib)))
            return lib
        try:
            return json.loads(self.cache.meta("lib") or "[]")
        except ValueError:
            return []

    def _progress(self, lib):
        """(Lieder, davon gesucht, davon mit Liedtext mit Zeiten) fuer die aktuelle Bibliothek, jedes Lied einmal.
        Zwischengespeichert, solange sich Bibliothek und Liedtexte nicht aendern (die Seite Statistik fragt alle 10 s)."""
        sig = (len(lib), tuple(lib[0]) if lib else None, tuple(lib[-1]) if lib else None, tuple(self.cache.counts()))
        if getattr(self, "_prog", (None,))[0] == sig:
            return self._prog[1]
        res = self._progress_calc(lib)
        self._prog = (sig, res)
        return res

    def _progress_calc(self, lib):
        keys = self.cache.keys()
        songs, seen, found = set(), 0, 0
        for title, dur in lib:
            k = self.cache.key(title, dur)
            if k in songs:
                continue
            songs.add(k)
            name, d = k.rsplit("|", 1)
            ns = [keys[x] for x in (k, f"{name}|{int(d) - 1}", f"{name}|{int(d) + 1}") if x in keys]
            if ns:
                seen += 1
                found += 1 if max(ns) > 0 else 0
        return len(songs), seen, found

    def _known(self, known, title, dur):
        k = self.cache.key(title, dur)
        name, d = k.rsplit("|", 1)
        return k in known or f"{name}|{int(d) - 1}" in known or f"{name}|{int(d) + 1}" in known

    def status(self):
        total, seen, found = self._progress(self._lib())
        running = self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set()
        return {"running": running, "seen": seen, "found": found, "total": total, "done": bool(total) and seen >= total,
                "current": self.current if running else "", "error": self.error}
