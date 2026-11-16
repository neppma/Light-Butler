"""
damaged.py - Beschaedigte Musikdateien finden und reparieren (Wunsch von Markus, 14.11.2026, Datenpflege).

Anlass: "07_MESSTON__ROSA_RAUSCHEN__.MP3" liess sich in Mixxx nicht laden. ffmpeg las sie, das Abspielmodul von macOS
(Core Audio, darueber oeffnet Mixxx am Mac die MP3s) nicht: am Anfang der Musikdaten standen Bytes, die nicht dorthin gehoeren.

Finden: im Hintergrund jede Datei der Liedliste mit afinfo (Core Audio) oeffnen, gebremst, eine nach der anderen. Gemerkt in
~/Light-Butler-Daten/defekt/stand.json je Pfad mit Groesse und Zeit: geprueft wird nur, was neu ist oder sich geaendert hat.
Reparieren (nur MP3, nur auf Klick): ffmpeg schreibt die Musik ohne Neukodieren in eine Hilfsdatei daneben (Tags und Cover
bleiben), erst wenn macOS die Hilfsdatei lesen kann und die Laenge passt, kommt das Original in den Papierkorb und die
Hilfsdatei bekommt seinen Namen (Mixxx findet sie am selben Ort, Hotcues und Playlists bleiben). Sonst bleibt alles, wie es war.
Nie bei ausgeworfenem Stick (stick_hold). Aufs Licht wirkt das nie.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

DATA_DIR = os.path.join(_pfad.daten(), "defekt")
STATE_FILE = "stand.json"
AUDIO_EXT = (".mp3", ".m4a", ".mp4", ".aac", ".wav", ".aif", ".aiff", ".flac")
GAP_S = 0.05                       # Pause zwischen zwei Dateien (Stick und Mac nicht auslasten)
RESCAN_S = 600.0                   # danach nach neuen oder geaenderten Dateien sehen
DUR_TOL_S = 1.0                    # so viel darf die reparierte Datei kuerzer oder laenger sein (ein kaputtes Bild am Anfang)
PLATFORM = sys.platform           # welcher Pruefweg (Tests stellen den Mac-Weg nach)
WHY_CA = ("Windows/ffmpeg kann sie nicht lesen" if PLATFORM == "win32"
          else "macOS kann sie nicht öffnen (Mixxx am Mac auch nicht)")
WIN_PROBE_S = 30                   # Windows: so viele Sekunden probehalber dekodieren


def win_check(path, run=subprocess.run, which=None):
    """Windows (15.11.2026, kein afinfo): mit ffmpeg die ersten WIN_PROBE_S Sekunden dekodieren. (ok, Laenge) wie afinfo;
    ok None = ohne ffmpeg nicht pruefbar (dann wird nichts als defekt markiert)."""
    ff = (which or shutil.which)("ffmpeg")
    if not ff:
        return None, None
    try:
        r = run([ff, "-v", "error", "-i", path, "-map", "0:a:0", "-t", str(WIN_PROBE_S), "-f", "null", "-"],
                capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    if r.returncode:
        return False, None
    return True, ffprobe_duration(ff, path, run)


def afinfo(path, run=subprocess.run, platform=None):
    """(ok, Laenge in s oder None) mit dem Abspielmodul von macOS. Windows: win_check (ok None = nicht pruefbar)."""
    if (platform or PLATFORM) == "win32":
        return win_check(path, run)
    try:
        r = run(["/usr/bin/afinfo", path], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode or "Fail" in out:
        return False, None
    m = re.search(r"estimated duration:\s*([0-9.]+)", out)
    return True, (float(m.group(1)) if m else None)


def ffprobe_duration(ffmpeg, path, run=subprocess.run):
    probe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
    try:
        r = run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                capture_output=True, text=True, timeout=60)
        return float((r.stdout or "").strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


class Damaged:
    def __init__(self, lib, mapper, log=None, run=subprocess.run, ffmpeg=None, trash=None, base=DATA_DIR, gap_s=GAP_S):
        """lib() -> Liedliste (path), mapper(p) -> Datei am Mac, ffmpeg() -> Pfad oder '', trash(datei) -> Papierkorb."""
        self.lib, self.mapper, self.run = lib, mapper, run
        self.log = log or (lambda t: None)
        self.ffmpeg = ffmpeg or (lambda: "")
        self.trash = trash
        self.base, self.gap_s = base, gap_s
        self.lock = threading.Lock()
        self.state = {}                # Pfad -> {"s": Groesse, "m": Zeit, "ok": 0/1, "why": "", "fix": 0/1}
        try:
            with open(os.path.join(base, STATE_FILE), encoding="utf-8") as f:
                d = json.load(f)
            self.state = {str(p): v for p, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            pass
        self.progress, self.scan_t, self.thread, self.stop_ev = (0, 0), 0.0, None, threading.Event()
        self.job = None

    def _save(self):
        os.makedirs(self.base, exist_ok=True)
        p = os.path.join(self.base, STATE_FILE)
        with self.lock:
            data = json.dumps(self.state, ensure_ascii=False)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(p + ".tmp", p)

    # ---- Pruefen ----
    def _todo(self):
        out = []
        for r in self.lib() or []:
            p = r.get("path") or ""
            if not p or r.get("missing") or not p.lower().endswith(AUDIO_EXT):
                continue
            f = self.mapper(p)
            if not f:
                continue
            try:
                st = os.stat(f)
            except OSError:
                continue
            e = self.state.get(p)
            if e and e.get("s") == st.st_size and abs(float(e.get("m") or 0) - st.st_mtime) < 1:
                continue
            out.append((p, f, st))
        return out

    def scan_once(self):
        import stick_hold
        todo = self._todo()
        self.progress = (0, len(todo))
        n_bad = 0
        for i, (p, f, st) in enumerate(todo):
            if self.stop_ev.is_set() or stick_hold.held(f):
                break
            ok, _d = afinfo(f, self.run)
            if ok is None:                               # Windows ohne ffmpeg: nicht pruefbar, nichts als defekt merken
                self.log("Beschaedigte Dateien: ohne ffmpeg nicht pruefbar")
                break
            with self.lock:
                self.state[p] = {"s": st.st_size, "m": st.st_mtime, "ok": 1 if ok else 0, "why": "" if ok else WHY_CA}
            n_bad += not ok
            self.progress = (i + 1, len(todo))
            if (i + 1) % 200 == 0:
                self._save()
            if self.gap_s:
                time.sleep(self.gap_s)
        if todo:
            self._save()
            self.log(f"Beschaedigte Dateien: {len(todo)} geprueft, {n_bad} nicht lesbar")
        self.scan_t = time.time()

    def _loop(self):
        while not self.stop_ev.is_set():
            try:
                self.scan_once()
            except Exception as e:                           # noqa: BLE001  die Pruefung darf nie etwas anhalten
                self.log(f"Beschaedigte Dateien: {str(e)[:120]}")
            self.stop_ev.wait(RESCAN_S)

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stop_ev.clear()
            self.thread = threading.Thread(target=self._loop, name="defekt-pruefen", daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_ev.set()

    # ---- Stand fuer die Seite ----
    def get(self):
        known = {r.get("path") for r in self.lib() or [] if r.get("path") and not r.get("missing")}
        with self.lock:
            items = [{"path": p, "why": e.get("why") or WHY_CA, "mp3": p.lower().endswith(".mp3"), "fix": e.get("fix") or ""}
                     for p, e in self.state.items() if not e.get("ok") and p in known]
        items.sort(key=lambda x: x["path"].lower())
        d, n = self.progress
        busy = self.thread is not None and self.thread.is_alive() and d < n
        return {"state": "busy" if busy else ("ok" if self.scan_t else "wait"), "progress": [d, n], "items": items, "n": len(items),
                "job": dict(self.job) if self.job else None, "ffmpeg": bool(self.ffmpeg())}

    # ---- Reparieren ----
    def repair_file(self, path):
        """Eine MP3 reparieren. Rueckgabe "ok" oder ein Grund."""
        import stick_hold
        e = self.state.get(path)
        if not e or e.get("ok"):
            return "nicht als beschaedigt bekannt"
        if not path.lower().endswith(".mp3"):
            return "nur MP3 (sonst → MP3 in der Musik-Datenbank)"
        ff = self.ffmpeg()
        if not ff:
            return "ffmpeg fehlt (winget install Gyan.FFmpeg)" if sys.platform == "win32" else "ffmpeg fehlt (brew install ffmpeg)"
        f = self.mapper(path)
        if not f or not os.path.isfile(f):
            return "Datei nicht da (Stick eingesteckt?)"
        if stick_hold.held(f):
            return "Stick wird ausgeworfen"
        d, b = os.path.split(f)
        tmp = os.path.join(d, "." + b + ".lb-tmp.mp3")
        try:
            r = self.run([ff, "-v", "error", "-y", "-i", f, "-map", "0", "-c", "copy", "-id3v2_version", "3", "-write_xing", "0", tmp],
                         capture_output=True, text=True, timeout=600)
            if r.returncode or not os.path.isfile(tmp) or os.path.getsize(tmp) < 1024:
                return "ffmpeg konnte sie nicht lesen" + (": " + (r.stderr or "").strip()[:100] if r.stderr else "")
            ok, dur = afinfo(tmp, self.run)
            if not ok:
                return "auch die reparierte Fassung ist nicht lesbar" if sys.platform == "win32" else "auch die reparierte Fassung kann macOS nicht öffnen"
            want = ffprobe_duration(ff, f, self.run)
            if want and dur and abs(want - dur) > DUR_TOL_S:
                return f"Länge passt nicht ({dur:.1f} statt {want:.1f} s)"
            if self.trash is None:
                return "Papierkorb nicht verfügbar"
            self.trash(f)
            if os.path.exists(f):
                return "Original ließ sich nicht in den Papierkorb legen"
            os.rename(tmp, f)
            st = os.stat(f)
            with self.lock:
                self.state[path] = {"s": st.st_size, "m": st.st_mtime, "ok": 1, "why": "", "fix": 1}
            self._save()
            self.log(f"Beschaedigte Dateien: repariert {b}")
            return "ok"
        except (OSError, subprocess.TimeoutExpired) as ex:
            return f"Fehler: {str(ex)[:100]}"
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _mark(self, path, why):
        with self.lock:
            if path in self.state:
                self.state[path]["fix"] = why[:120]
        self._save()

    def repair(self, paths):
        """Im Hintergrund nacheinander reparieren (Knopf auf der Seite). Stand in get()["job"]."""
        if self.job and self.job.get("state") == "run":
            raise ValueError("Es wird schon repariert")
        paths = [str(p) for p in (paths or []) if isinstance(p, str)][:2000]
        self.job = {"state": "run", "done": 0, "total": len(paths), "ok": 0, "err": ""}

        def work():
            for p in paths:
                res = self.repair_file(p)
                if res == "ok":
                    self.job["ok"] += 1
                else:
                    self._mark(p, res)
                    self.job["err"] = res
                self.job["done"] += 1
            self.job["state"] = "done"
        threading.Thread(target=work, name="defekt-reparieren", daemon=True).start()
        return {"started": True, "total": len(paths)}

    def trash_file(self, path):
        """Nicht reparierbare Datei in den Papierkorb (nach Rueckfrage auf der Seite)."""
        e = self.state.get(path)
        if not e or e.get("ok"):
            raise ValueError("nicht als beschaedigt bekannt")
        f = self.mapper(path)
        if not f or not os.path.isfile(f):
            raise ValueError("Datei nicht da")
        if self.trash is None:
            raise ValueError("Papierkorb nicht verfügbar")
        self.trash(f)
        with self.lock:
            self.state.pop(path, None)
        self._save()
        return {"ok": True}
