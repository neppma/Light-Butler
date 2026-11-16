"""
stems_bulk.py - Pegelkurven vorab fuer die ganze Mixxx-Bibliothek (Wunsch von Markus, 06.11.2026).

Der Pi ist nur Auftraggeber: Er fuehrt die Liste, welche Lieder dran sind, und nimmt die fertigen Kurven an. Rechnen tut ein
anderer Rechner (der Windows-PC mit Grafikkarte, stems_show.py --watch --vorab): Er fragt nach dem naechsten Lied, holt die
MP3 beim Vorhoer-Server am Mac (music_serve.py), rechnet und schickt nur die Kurven zurueck. Die Musik liegt nie am Pi.
Die Kurven haengen am Fingerabdruck der MP3 wie bei den Shows: legt man spaeter eine Show zum Lied an, hat sie sie sofort.

Stand in shows/_stems_vorab.json: ob es laeuft, Pfad -> Fingerabdruck (das kennt der Pi erst, wenn ein Rechner die Datei
gesehen hat), Fehler je Pfad. Aufs Licht wirkt das nicht.
"""
import json
import os
import threading
import time

from .store import FP_RE

MIN_S, MAX_S = 30.0, 600.0      # nur Lieder von 30 s bis 10 min (keine Jingles, keine Mitschnitte und Mixe); Einstellung sm_stems_max_min
CLAIM_S = 20 * 60.0             # so lange gehoert ein Lied dem Rechner, der es geholt hat (dann darf ein anderer)
RETRY_S = 24 * 3600.0           # ein Lied mit Fehler erst nach einem Tag wieder versuchen
SEEN_S = 180.0                  # ein Rechner gilt als aktiv, wenn er sich in dieser Zeit gemeldet hat
SAVE_S = 120.0                  # Stand hoechstens so oft auf die SD-Karte schreiben
FILE = "_stems_vorab.json"


class StemBulk:
    def __init__(self, store, library, music, now=time.time, max_s=None):
        """library() -> Lieder wie MixxxLink.library_full (title, dur, path); music() -> Adresse des Vorhoer-Servers am Mac
        oder ''; store = ShowStore (Kurven-Ablage); max_s() -> Laengengrenze in Sekunden (0 = keine), sonst MAX_S."""
        self.store, self.library, self.music, self.now = store, library, music, now
        self.max_s = max_s or (lambda: MAX_S)
        self.path = os.path.join(store.base, FILE)
        self.lock = threading.Lock()
        self.on, self.fps, self.fail = False, {}, {}
        self.claims = {}                # Pfad -> (Rechner, Zeit, Titel)
        self.seen = {}                  # Rechner -> letzte Meldung
        self.times = []                 # Rechenzeit der letzten Lieder (s), fuer die Schaetzung
        self.saved_t, self.dirty = 0.0, False
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.on = bool(d.get("on"))
                self.fps = {str(k): str(v) for k, v in (d.get("fps") or {}).items()}
                self.fail = {str(k): v for k, v in (d.get("fail") or {}).items() if isinstance(v, list) and len(v) == 2}
        except (OSError, ValueError):
            pass

    # ---- Ablage ----
    def _save(self, force=False):
        t = self.now()
        if not force and t - self.saved_t < SAVE_S:
            self.dirty = True
            return
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:            # Eintrag fuer Eintrag: die Show-Schleife kommt dazwischen dran
                f.write('{"on":%s,"fail":%s,"fps":{' % (json.dumps(self.on), json.dumps(self.fail, ensure_ascii=False)))
                for k, (p, fp) in enumerate(self.fps.items()):
                    f.write(("," if k else "") + json.dumps(p, ensure_ascii=False) + ":" + json.dumps(fp))
                f.write("}}")
            os.replace(tmp, self.path)
            self.saved_t, self.dirty = t, False
        except OSError:
            pass

    # ---- Liste ----
    def _short(self, d):
        """Kurz genug fuer Kurven (Einstellung sm_stems_max_min, 0 = keine Grenze)?"""
        try:
            m = float(self.max_s())
        except (TypeError, ValueError):
            m = MAX_S
        return m <= 0 or d <= m

    def _songs(self):
        """Lieder der Bibliothek, die in Frage kommen: MP3 mit Pfad, 30 s bis 6 min, je Pfad einmal, in der Reihenfolge der
        Bibliothek. Nur MP3: eine Show gibt es nur mit MP3, und MP4/AAC kann der Helfer ohne ffmpeg nicht lesen (06.11.2026)."""
        lib = self.library() or []
        c = getattr(self, "_songs_cache", (None, 0, None))
        if c[0] is lib and c[1] == len(lib):                                  # library_full liefert dieselbe Liste, solange sich nichts aendert
            return c[2]
        out, seen = [], set()
        for x in lib:
            p, d = x.get("path") or "", float(x.get("dur") or 0)
            if p and p not in seen and MIN_S <= d and self._short(d) and p.lower().endswith(".mp3"):
                seen.add(p)
                out.append(x)
        self._songs_cache = (lib, len(lib), out)
        return out

    def _claimed(self, path, who, t):
        c = self.claims.get(path)
        return bool(c) and c[0] != who and t - c[1] < CLAIM_S

    def status(self):
        with self.lock:
            t = self.now()
            lib = self.library() or []
            songs = self._songs()
            have = self.store.stems_fps()
            done = sum(1 for x in songs if self.fps.get(x["path"]) in have)
            fail = sum(1 for x in songs if x["path"] in self.fail and self.fps.get(x["path"]) not in have)
            long_ = sum(1 for x in lib if x.get("path") and not self._short(float(x.get("dur") or 0)))
            other = sum(1 for x in lib if x.get("path") and MIN_S <= float(x.get("dur") or 0) and self._short(float(x.get("dur") or 0))
                        and not x["path"].lower().endswith(".mp3"))
            work = [{"who": w, "title": ti, "since_s": round(t - t0)} for p, (w, t0, ti) in self.claims.items() if t - t0 < CLAIM_S]
            workers = sorted(w for w, ts in self.seen.items() if t - ts < SEEN_S)
            avg = sum(self.times) / len(self.times) if self.times else 0.0
            left = max(0, len(songs) - done - fail)
            titles = {x["path"]: x.get("title") or os.path.basename(x["path"]) for x in songs}
            failed = sorted(([titles[p], p, str(f[1]), round(float(f[0]))] for p, f in self.fail.items() if p in titles and self.fps.get(p) not in have),
                            key=lambda r: -r[3])[:30]      # welche Lieder scheiterten und woran (Seite Statistik)
            return {"on": self.on, "max_min": round(float(self.max_s() or 0) / 60.0, 1), "total": len(songs), "done": done, "fail": fail, "failed": [{"title": a, "path": b, "error": c, "t": d} for a, b, c, d in failed],
                    "long": long_, "other": other, "work": work, "workers": workers,
                    "music": bool(self.music()), "avg_s": round(avg, 1), "eta_h": round(left * avg / 3600.0, 1) if avg else None}

    def busy(self, fp):
        """Rechnet gerade ein Rechner die MP3 mit diesem Fingerabdruck (bekannt, sobald er sie geholt hat)?"""
        with self.lock:
            t = self.now()
            for p, (w, t0, _ti) in self.claims.items():
                if t - t0 < CLAIM_S and self.fps.get(p) == fp:
                    return w
            return ""

    def retry(self):
        """Lieder mit Fehler sofort wieder versuchen (Knopf auf der Seite Statistik, z. B. nach einer Korrektur am Helfer)."""
        with self.lock:
            self.fail.clear()
            self._save(force=True)
        return self.status()

    def set(self, on):
        with self.lock:
            self.on = bool(on)
            if not self.on:
                self.claims.clear()
            self._save(force=True)
        return self.status()

    def next(self, who):
        """Naechstes Lied fuer diesen Rechner und gleich fuer ihn reserviert. {} = nichts zu tun, mit Grund."""
        with self.lock:
            t = self.now()
            self.seen[who] = t
            if not self.on:
                return {"off": True}
            music = self.music()
            if not music:
                return {"wait": "Der Light-Butler erreicht den Musik-Rechner gerade nicht (die MP3s kommen von dort)"}
            have = self.store.stems_fps()
            for x in self._songs():
                p = x["path"]
                if self.fps.get(p) in have or self._claimed(p, who, t):
                    continue
                f = self.fail.get(p)
                if f and t - float(f[0]) < RETRY_S:
                    continue
                self.claims[p] = (who, t, x.get("title") or os.path.basename(p))
                return {"path": p, "title": x.get("title") or "", "dur": x.get("dur"), "music": music}
            return {"done": True}

    def _mine(self, who, path):
        if path not in {x["path"] for x in self._songs()}:
            raise ValueError("Lied nicht in der Bibliothek")
        c = self.claims.get(path)
        if c and c[0] != who and self.now() - c[1] < CLAIM_S:
            raise ValueError("Dieses Lied rechnet gerade " + c[0])

    def note_fp(self, who, path, fp):
        """Der Rechner hat die MP3 geholt und meldet ihren Fingerabdruck. have=True: Kurven gibt es schon (z. B. aus einer Show)."""
        with self.lock:
            self.seen[who] = self.now()
            self._mine(who, path)
            if not FP_RE.match(fp or ""):
                raise ValueError("Fingerabdruck unbrauchbar")
            self.fps[path] = fp
            have = self.store.has_stems(fp)
            if have:
                self.claims.pop(path, None)
            self._save()
            return {"have": have}

    def done(self, who, path, fp, data, secs=None):
        with self.lock:
            self.seen[who] = self.now()
            self._mine(who, path)
            self.store.save_stems_fp(fp, data)
            self.fps[path] = fp
            self.fail.pop(path, None)
            self.claims.pop(path, None)
            if secs:
                self.times = (self.times + [float(secs)])[-30:]
            self._save()
            return {}

    def failed(self, who, path, error):
        with self.lock:
            self.seen[who] = self.now()
            self._mine(who, path)
            self.fail[path] = [self.now(), str(error or "")[:200]]
            self.claims.pop(path, None)
            self._save()
            return {}

    def flush(self):
        with self.lock:
            if self.dirty:
                self._save(force=True)
