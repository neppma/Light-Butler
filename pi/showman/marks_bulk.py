"""
marks_bulk.py - Cue-Punkte, Abschnitte und Drops aller Lieder vorab vom Mac holen (Wunsch von Markus, 06.11.2026).

Die Mixxx-Bruecke kennt sie fuer jedes Lied (Hotcues aus der Mixxx-Datenbank, Analyse am Mac) und liefert sie ueber den
Vorhoer-Server (music_serve.py, /marks). Dieser Lauf holt sie einmal fuer die ganze Bibliothek und legt sie am Pi ab, je Lied
eine kleine Datei unter shows/_marks/. Shows und Quick finden sie dann sofort, auch wenn der Mac aus ist.
Langsam im Hintergrund wie der Liedtext-Vorab-Lauf: anhalten und weitermachen jederzeit, nach einem Neustart geht es weiter.
Aufs Licht wirkt das nicht.
"""
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse

from . import timeline as tl

DIR = "_marks"
STATE = "_marks_vorab.json"
GAP_S = 0.5                      # Abstand zwischen zwei Liedern: Mac und Pi bleiben ruhig
WAIT_S = 60.0                    # Mac nicht da: so lange warten, dann wieder versuchen


FILE_RE = re.compile(r"^[0-9a-f]{24}\.json$")


def _fname(path):
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:24] + ".json"


class MarksBulk:
    def __init__(self, base, library, music, opener, now=time.time):
        """library() -> Lieder wie MixxxLink.library_full (title, dur, path, ana); music() -> Vorhoer-Server am Mac oder '';
        opener(url, timeout) wie urllib.request.urlopen."""
        self.base, self.library, self.music, self.opener, self.now = base, library, music, opener, now
        self.dir = os.path.join(base, DIR)
        self.state_path = os.path.join(base, STATE)
        self.stop_ev = threading.Event()
        self.thread = None
        self.current, self.error = "", ""
        self.missing = set()             # in diesem Lauf: am Mac (noch) keine Analyse, beim naechsten Starten wieder versuchen
        self.lock = threading.Lock()

    # ---- Ablage ----
    def get(self, path):
        """Abgelegte Marken zu einer Datei (clean_marks-Format) oder None."""
        try:
            with open(os.path.join(self.dir, _fname(path)), encoding="utf-8") as f:
                d = json.load(f)
            return d.get("marks") if d.get("path") == path else None
        except (OSError, ValueError, AttributeError):
            return None

    def moved(self, old, new):
        """Datei am Mac umbenannt (Dateien pruefen, 08.11.2026): abgelegte Marken auch unter dem neuen Pfad. Die alte Datei
        bleibt, bis Mixxx den neuen Pfad kennt. True = mitgenommen."""
        m = self.get(old)
        if m is None or self.get(new) is not None:
            return False
        try:
            with open(os.path.join(self.dir, _fname(old)), encoding="utf-8") as f:
                title = str(json.load(f).get("title") or "")
        except (OSError, ValueError, AttributeError):
            title = ""
        self._save(new, title, m)
        return True

    # ---- Sicherung auf den Stick (stems_backup.py am Mac) ----
    def files(self):
        """[[Dateiname, Groesse]] aller abgelegten Lieder."""
        out = []
        for n in sorted(self._have()):
            if FILE_RE.match(n):
                try:
                    out.append([n, os.path.getsize(os.path.join(self.dir, n))])
                except OSError:
                    pass
        return out

    def raw(self, name):
        """Inhalt einer Datei (Bytes) oder None; nur gueltige Namen, kein Pfad von aussen."""
        if not FILE_RE.match(str(name or "")):
            return None
        try:
            with open(os.path.join(self.dir, name), "rb") as f:
                return f.read()
        except OSError:
            return None

    def restore(self, name, data):
        """Eine Datei aus der Sicherung zurueck: Name muss zum Pfad passen, die Marken werden wie neu geholte geprueft."""
        if not FILE_RE.match(str(name or "")) or not isinstance(data, dict) or not isinstance(data.get("path"), str):
            raise ValueError("Cue-Datei unbrauchbar")
        if _fname(data["path"]) != name:
            raise ValueError("Cue-Datei passt nicht zu ihrem Namen")
        self._save(data["path"], str(data.get("title") or "")[:160], tl.clean_marks(data.get("marks") or {}))

    def _have(self):
        try:
            return set(os.listdir(self.dir))
        except OSError:
            return set()

    def _save(self, path, title, marks):
        os.makedirs(self.dir, exist_ok=True)
        p = os.path.join(self.dir, _fname(path))
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"path": path, "title": title, "t": round(self.now()), "marks": marks}, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, p)

    def _flag(self, on=None):
        if on is None:
            try:
                with open(self.state_path, encoding="utf-8") as f:
                    return bool(json.load(f).get("on"))
            except (OSError, ValueError, AttributeError):
                return False
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"on": bool(on)}, f)
        except OSError:
            pass
        return on

    # ---- Liste ----
    def _songs(self):
        out, seen = [], set()
        for x in self.library() or []:
            p = x.get("path") or ""
            if p and p not in seen:
                seen.add(p)
                out.append(x)
        return out

    def status(self):
        songs = self._songs()
        have = self._have()
        done = sum(1 for x in songs if _fname(x["path"]) in have)
        running = self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set()
        open_ = [x for x in songs if _fname(x["path"]) not in have]
        bad = sum(1 for x in open_ if x.get("bad"))         # Datei fuer die Analyse am Mac nicht lesbar: bekommt nie eine
        missing = sum(1 for x in open_ if not x.get("bad") and x["path"] in self.missing)
        # Erledigt (Knopf weg, Fehlerbericht 07.11.2026): alles da ausser den nicht lesbaren und den noch nicht analysierten
        return {"running": running, "total": len(songs), "done": done, "missing": missing, "bad": bad, "done_all": bool(songs) and done + missing + bad >= len(songs),
                "music": bool(self.music()), "current": self.current if running else "", "error": self.error}

    # ---- Lauf ----
    def step(self, x):
        """Ein Lied holen und ablegen. True = abgelegt, False = keine Analyse am Mac, None = Mac nicht erreichbar."""
        music = self.music()
        if not music:
            return None
        url = music.rstrip("/") + "/marks?p=" + urllib.parse.quote(x["path"], safe="")
        try:
            with self.opener(url, timeout=20) as r:
                m = json.loads(r.read().decode("utf-8"))
        except OSError as e:
            if getattr(e, "code", None) == 404:            # Lied (noch) nicht analysiert: kein Fehler
                self.missing.add(x["path"])
                return False
            return None
        except ValueError:
            self.missing.add(x["path"])
            return False
        marks = tl.clean_marks({"se": m.get("se") or [], "cu": m.get("cu") or [], "ev": m.get("ev") or [], "en": m.get("en") or [],
                                "lvl": m.get("lvl"), "genre": m.get("genre") or "", "title": m.get("title") or "", "fp": m.get("fp") or ""})
        self._save(x["path"], x.get("title") or "", marks)
        return True

    def run(self):
        while not self.stop_ev.is_set():
            have = self._have()
            todo = [x for x in self._songs() if _fname(x["path"]) not in have and x["path"] not in self.missing]
            if not todo:
                if self._songs():                              # fertig: aus, neue Lieder kommen mit dem naechsten Starten
                    self._flag(False)
                    self.current = ""
                    return
                if self.stop_ev.wait(5.0):                     # Bibliothek noch nicht da
                    return
                continue
            for x in todo:
                if self.stop_ev.is_set():
                    return
                self.current = str(x.get("title") or os.path.basename(x["path"]))[:120]
                res = self.step(x)
                if res is None:
                    self.error = "Der Light-Butler erreicht den Musik-Rechner gerade nicht (Mixxx-App oder Helfer laeuft? Stick eingesteckt?)"
                    if self.stop_ev.wait(WAIT_S):
                        return
                    break
                self.error = ""
                if self.stop_ev.wait(GAP_S):
                    return

    def start(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set():
                return self.status()
            self._flag(True)
            self.missing, self.error = set(), ""
            self.stop_ev = threading.Event()
            self.thread = threading.Thread(target=self.run, name="cues-vorab", daemon=True)
            self.thread.start()
        return self.status()

    def stop(self):
        self._flag(False)
        self.stop_ev.set()
        return self.status()

    def resume(self):
        """Nach einem Neustart des Dienstes weitermachen, wenn es lief."""
        if self._flag():
            self.start()
