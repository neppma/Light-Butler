"""Klang-Fingerabdruck fuer die Import-Seite (Wunsch 11.11.2026): gleiche Musik erkennen, auch wenn Titel, Interpret,
Dateiname und Kodierung ganz anders sind (Beispiel: "01 - Future Trance 13 - Techno.mp3", 128 kbit/s, ist am Stick
"Aquagen - Partyalarm (Und ab geht's) (Radio Mix).mp3", 320 kbit/s, beide 219,51 s).

Chromaprint (fpcalc aus Homebrew, "brew install chromaprint", vom Nutzer gewaehlt 11.11.2026; wie AcoustID/MusicBrainz,
rechnet nur am Mac, nichts geht ins Internet). Verglichen wird nur mit Liedern der Bibliothek, die fast gleich lang sind
(DUR_TOL_S), so bleiben es je Lied wenige Vergleiche. Fingerabdruecke der Bibliothek merkt sich der Mac
(~/Light-Butler-Daten/klang/fp.json), Ergebnisse je Import-Datei in ~/Light-Butler-Daten/klang/import.json.

Treffer kommen im Wartebereich nach "gibt es schon" (nie ueberschreiben: " (2)"); die Import-Seite zeigt das vorhandene Lied
mit "gleicher Klang" zum Vorhoeren, Ersetzen oder Wegwerfen.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

DATA_DIR = os.path.join(_pfad.daten(), "klang")
FP_FILE, RES_FILE = "fp.json", "import.json"
FPCALC_PATHS = ("/opt/homebrew/bin/fpcalc", "/usr/local/bin/fpcalc")
LENGTH_S = 90                 # so viele Sekunden ab dem Anfang rechnet fpcalc
DUR_TOL_S = 2.0               # Kandidaten: Laenge hoechstens so weit anders
MAX_CANDS = 25                # hoechstens so viele Kandidaten je Lied (die mit aehnlichster Laenge)
SAME = 0.80                   # ab dieser Aehnlichkeit gilt es als dieselbe Aufnahme (fremde Lieder liegen um 0,5 bis 0,65)
MAX_SHIFT = 24                # Versatz bis rund 3 s (Stille am Anfang anders lang)
MIN_FRAMES = 60               # zu kurz verglichen: kein Urteil
RES_VERSION = 2               # 2: echte Laenge gemessen (VBR ohne Kopf meldete 1308 s statt 220 s, Fehlerbericht 11.11.2026)


def find_fpcalc():
    p = shutil.which("fpcalc")
    if p:
        return p
    return next((x for x in FPCALC_PATHS if os.path.isfile(x) and os.access(x, os.X_OK)), "")


def raw_fp(path, fpcalc, length=LENGTH_S, run=subprocess.run):
    """Rohen Fingerabdruck (Liste 32-Bit-Zahlen, rund 8 je Sekunde) oder None."""
    try:
        r = run([fpcalc, "-raw", "-json", "-length", str(int(length)), path], capture_output=True, timeout=120)
        d = json.loads((r.stdout or b"{}").decode("utf-8", "replace") or "{}")
        fp = d.get("fingerprint")
        return [int(x) & 0xFFFFFFFF for x in fp] if isinstance(fp, list) and fp else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def real_duration(path, ffmpeg, run=subprocess.run):
    """Echte Laenge in s: die Datei einmal ganz dekodieren (ffmpeg, rund 0,2 s je Lied). Die schnelle Schaetzung aus dem
    ersten MPEG-Block liegt bei VBR-Dateien ohne Kopf weit daneben ("Mike & the Mechanics": 1308 s statt 220 s). 0 = unbekannt."""
    if not ffmpeg:
        return 0.0
    try:
        r = run([ffmpeg, "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0", "-f", "null", "-"], capture_output=True, timeout=120)
        t = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", (r.stderr or b"").decode("utf-8", "replace"))
        if not t:
            return 0.0
        h, m, s = t[-1]
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def similarity(a, b, max_shift=MAX_SHIFT):
    """Aehnlichkeit zweier Fingerabdruecke 0..1 (Anteil gleicher Bits, bester Versatz). 1 = gleich, fremde Lieder ~0,5."""
    import numpy as np
    if not a or not b:
        return 0.0
    x, y = np.asarray(a, dtype=np.uint32), np.asarray(b, dtype=np.uint32)
    best = 0.0
    for s in range(-max_shift, max_shift + 1):
        xa, yb = (x[s:], y) if s >= 0 else (x, y[-s:])
        n = min(len(xa), len(yb))
        if n < MIN_FRAMES:
            continue
        diff = np.bitwise_xor(xa[:n], yb[:n])
        bits = int(np.unpackbits(diff.view(np.uint8)).sum())
        best = max(best, 1.0 - bits / (32.0 * n))
    return round(best, 3)


class FpCache:
    """Fingerabdruecke je Datei (Pfad, Aenderungszeit, Groesse), gespeichert in fp.json."""

    def __init__(self, base=DATA_DIR):
        self.path = os.path.join(base, FP_FILE)
        self.lock = threading.Lock()
        try:
            with open(self.path, encoding="utf-8") as f:
                self.d = dict(json.load(f))
        except (OSError, ValueError, TypeError):
            self.d = {}
        self.dirty = False

    @staticmethod
    def _stamp(f):
        st = os.stat(f)
        return [int(st.st_mtime), st.st_size]

    def get(self, f, fpcalc, run=subprocess.run):
        try:
            stamp = self._stamp(f)
        except OSError:
            return None
        with self.lock:
            e = self.d.get(f)
            if e and e[0] == stamp[0] and e[1] == stamp[1]:
                return e[2]
        fp = raw_fp(f, fpcalc, run=run)
        if fp:
            with self.lock:
                self.d[f] = stamp + [fp]
                self.dirty = True
        return fp

    def save(self):
        with self.lock:
            if not self.dirty:
                return
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.d, f, separators=(",", ":"))
            os.replace(tmp, self.path)
            self.dirty = False


def candidates(dur, songs, own=""):
    """Lieder der Bibliothek mit fast gleicher Laenge, die aehnlichste zuerst."""
    out = [s for s in songs if s.get("path") and s.get("path") != own and abs(float(s.get("duration") or 0) - dur) <= DUR_TOL_S]
    out.sort(key=lambda s: abs(float(s.get("duration") or 0) - dur))
    return out[:MAX_CANDS]


def load_results(base=DATA_DIR):
    try:
        with open(os.path.join(base, RES_FILE), encoding="utf-8") as f:
            return dict(json.load(f))
    except (OSError, ValueError, TypeError):
        return {}


def save_results(res, base=DATA_DIR):
    os.makedirs(base, exist_ok=True)
    p = os.path.join(base, RES_FILE)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)


class Checker:
    """Klang pruefen als Auftrag (eine Datei nach der anderen, eigener Faden). status() fuer die Seite."""

    CHECK_DIRS = None              # gesetzt aus import_assist: neu, gleicher Titel, andere Laenge (gibt es schon: schon geprueft)

    def __init__(self, base=DATA_DIR, fpcalc_fn=find_fpcalc, log=None, run=subprocess.run, ffmpeg_fn=None):
        if ffmpeg_fn is None:
            from convert_mp3 import find_ffmpeg as ffmpeg_fn
        self.base, self.fpcalc_fn, self.log, self.run, self.ffmpeg_fn = base, fpcalc_fn, log or (lambda t: None), run, ffmpeg_fn
        self.lock = threading.Lock()
        self.st = {"state": "idle"}
        self.stop_ev = threading.Event()
        self.thread = None

    def status(self):
        with self.lock:
            return dict(self.st)

    def stop(self):
        self.stop_ev.set()
        return self.status()

    def start(self, root, songs, locate):
        """songs: Bibliothek (Dicts mit path, duration, artist, title, bitrate); locate(Pfad) -> Datei am Mac oder None."""
        ff = self.fpcalc_fn()
        if not ff:
            raise ValueError("Chromaprint fehlt am Mac (Terminal: brew install chromaprint)")
        import import_assist as ia
        base = ia.import_dir(root)
        if not base or not os.path.isdir(base):
            raise ValueError("Wartebereich musik-import nicht gefunden")
        files = []
        for cat in (ia.CAT_NEW, ia.CAT_COVER, ia.CAT_LEN):
            for d, ds, fs in os.walk(os.path.join(base, cat)):
                ds[:] = sorted(x for x in ds if not x.startswith("."))
                files += [os.path.join(d, f) for f in sorted(fs, key=str.casefold) if f.lower().endswith(".mp3") and not f.startswith(".")]
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                raise ValueError("Klang-Pruefung laeuft schon")
            self.stop_ev.clear()
            self.st = {"state": "run", "total": len(files), "done": 0, "found": 0, "cur": "", "t0": time.time()}
            self.thread = threading.Thread(target=self._run, args=(root, files, list(songs() if callable(songs) else songs or []), locate, ff),
                                           name="klang", daemon=True)
            self.thread.start()
            return dict(self.st)

    def _run(self, root, files, songs, locate, ff):
        import folder_lib
        import import_assist as ia
        import stick_hold
        cache, res = FpCache(self.base), load_results(self.base)
        same_dir = os.path.join(ia.import_dir(root), ia.CAT_SAME)
        fm = self.ffmpeg_fn()
        try:
            for f in files:
                if self.stop_ev.is_set() or stick_hold.held(f):
                    cache.save()
                    save_results(res, self.base)
                    with self.lock:
                        self.st.update(state="stopped", cur="")
                    return
                with self.lock:
                    self.st["cur"] = os.path.basename(f)
                try:
                    stamp = FpCache._stamp(f)
                    old = res.get(f)
                    if old and old.get("m") == stamp and old.get("v", 1) >= RES_VERSION:   # schon geprueft, Datei unveraendert
                        continue
                    dur = real_duration(f, fm, run=self.run) or float((folder_lib.read_mp3(f) or {}).get("duration") or 0)
                    hit = None
                    cands = candidates(dur, songs) if dur else []
                    mine = cache.get(f, ff, run=self.run) if cands else None
                    for c in cands if mine else []:
                        cf = locate(c["path"]) if locate else c["path"]
                        if not cf or not os.path.isfile(cf):
                            continue
                        sim = similarity(mine, cache.get(cf, ff, run=self.run))
                        if sim >= SAME and (hit is None or sim > hit["score"]):
                            hit = {"path": c["path"], "score": sim, "artist": c.get("artist") or "", "title": c.get("title") or "",
                                   "dur": round(float(c.get("duration") or 0)), "kbps": int(c.get("bitrate") or 0)}
                    if hit:                                # gibt es schon (gleicher Klang): in den Ordner "gibt es schon"
                        os.makedirs(same_dir, exist_ok=True)
                        dst = ia.free_target(os.path.join(same_dir, os.path.basename(f)))
                        import file_check as fc
                        fc.rename_any(f, dst)
                        res.pop(f, None)
                        res[dst] = {"m": FpCache._stamp(dst), "hit": hit, "v": RES_VERSION, "dur": round(dur, 2)}
                        with self.lock:
                            self.st["found"] += 1
                    else:
                        res[f] = {"m": stamp, "hit": None, "v": RES_VERSION, "dur": round(dur, 2)}
                except (OSError, ValueError) as e:
                    self.log(f"Klang: {os.path.basename(f)}: {e}")
                finally:
                    with self.lock:
                        self.st["done"] += 1
                    if self.st["done"] % 20 == 0:
                        cache.save()
                        save_results(res, self.base)
            cache.save()                                   # erst speichern, dann "fertig" melden (sonst las die Seite oder ein Test
            save_results(res, self.base)                   # die Ergebnisse, bevor sie in der Datei standen; Fehlerbericht 11.11.2026)
            with self.lock:
                self.st.update(state="ok", cur="", t1=time.time())
        finally:
            cache.save()
            save_results(res, self.base)
        if self.st.get("found"):
            self.log(f"Klang: {self.st['found']} Lieder gibt es schon (gleicher Klang), nach 'gibt es schon' verschoben")


def hit_for(path, res=None, base=DATA_DIR):
    """Treffer zu einer Datei im Wartebereich (nur, solange sie unveraendert ist)."""
    res = load_results(base) if res is None else res
    e = res.get(path)
    if not e or not e.get("hit"):
        return None
    try:
        if FpCache._stamp(path) != e.get("m"):
            return None
    except OSError:
        return None
    return e["hit"]
