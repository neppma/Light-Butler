"""
covers.py - Cover der Lieder (Wunsch von Markus, 06.11.2026).

Das Bild steckt in der MP3 (ID3, APIC), in der MP4 (covr) oder liegt als cover.jpg/folder.jpg im Ordner. Der Vorhoer-Server
am Mac (music_serve.py, /cover?p=) sucht es, verkleinert es auf hoechstens 300 Pixel und schickt den Fingerabdruck der Datei
mit (Kopfzeile X-FP). Der Pi legt es einmal ab, je Fingerabdruck eine Datei:
    shows/_covers/<Groesse>_<sha1>.jpg
    shows/_covers_index.jsonl      Pfad am Mac -> Fingerabdruck ('' = Lied ohne Cover), Zeile fuer Zeile angehaengt
Angezeigt werden die Cover in der Musik-Datenbank, im Showmanager und im Hauptpanel. Geholt wird beim ersten Anzeigen oder
vorab fuer die ganze Bibliothek (Seite Statistik). Die Mixxx-Bruecke sichert die Bilder auf den Stick (Backup/Light-Butler-Covers).
Aufs Licht wirkt das nicht.
"""
import json
import os
import re
import threading
import time
import urllib.parse

DIR = "_covers"
INDEX = "_covers_index.jsonl"
STATE = "_covers_vorab.json"
FILE_RE = re.compile(r"^\d{1,12}_[0-9a-f]{16}\.jpg$")
FP_RE = re.compile(r"^\d{1,12}:[0-9a-f]{16}$")
MAX_BYTES = 2 * 1024 * 1024        # ein Vorschaubild ist ~20-80 KB; groesser = kaputt oder fremd
GAP_S = 0.3
WAIT_S = 60.0
NONE_RETRY_S = 6 * 3600.0          # Lied ohne Cover: beim Anzeigen erst nach dieser Zeit wieder am Mac fragen
# Nachschauen (08.11.2026): Lieder "ohne Cover" bekommen oft spaeter eins (Auto-Tagger am Mac, Tag-Editor, Cover erzeugen),
# ohne dass der Pi davon hoert. Ein leiser Lauf fragt sie darum regelmaessig wieder am Mac, eines pro Sekunde.
RECHECK_FIRST_S = 120.0            # erster Lauf nach dem Start
RECHECK_S = 3 * 3600.0             # dann alle 3 Stunden
RECHECK_GAP_S = 1.0
RECHECK_AWAY_S = 600.0             # Mac nicht erreichbar: in 10 Minuten wieder


def fname(fp):
    return fp.replace(":", "_") + ".jpg"


def is_image(data):
    return isinstance(data, (bytes, bytearray)) and (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n")


def _syncsafe(b):
    return (b[0] & 0x7F) << 21 | (b[1] & 0x7F) << 14 | (b[2] & 0x7F) << 7 | (b[3] & 0x7F)


def id3_image(head):
    """Bild aus dem ID3v2-Kopf einer MP3 (wie music_serve.id3_cover am Mac), Vorderseite (Typ 3) bevorzugt; Bytes oder None."""
    if head[:3] != b"ID3" or len(head) < 10:
        return None
    ver, size = head[3], _syncsafe(head[6:10])
    end, pos, best = min(len(head), 10 + size), 10, None
    if head[5] & 0x40 and ver >= 3:
        pos += _syncsafe(head[10:14]) if ver == 4 else 4 + int.from_bytes(head[10:14], "big")
    while pos + (6 if ver == 2 else 10) <= end:
        if ver == 2:
            fid, fsize, hdr = head[pos:pos + 3], int.from_bytes(head[pos + 3:pos + 6], "big"), 6
        else:
            fid, hdr = head[pos:pos + 4], 10
            fsize = _syncsafe(head[pos + 4:pos + 8]) if ver == 4 else int.from_bytes(head[pos + 4:pos + 8], "big")
        if not fid.strip(b"\0") or fsize <= 0:
            break
        body = head[pos + hdr:pos + hdr + fsize]
        if fid in (b"APIC", b"PIC") and body:
            enc = body[0]
            rest = body[4:] if fid == b"PIC" else body[body.find(b"\0", 1) + 1:]
            ptype, rest = (rest[0] if rest else 0), rest[1:]
            if enc in (1, 2):
                i = 0
                while i + 1 < len(rest) and rest[i:i + 2] != b"\0\0":
                    i += 2
                data = rest[i + 2:]
            else:
                data = rest[rest.find(b"\0") + 1:]
            if is_image(data) and (best is None or ptype == 3):
                best = data
                if ptype == 3:
                    break
        pos += hdr + fsize
    return best


def mp3_image(path):
    """Eingebettetes Cover einer MP3-Datei am Pi (MP3 einer Show) oder None."""
    try:
        with open(path, "rb") as f:
            head = f.read(10)
            if head[:3] != b"ID3" or len(head) < 10:
                return None
            head += f.read(min(_syncsafe(head[6:10]), 16 * 1024 * 1024))
    except OSError:
        return None
    return id3_image(head)


class Covers:
    def __init__(self, base, library, music, opener, now=time.time):
        self.mt = {}                      # Fingerabdruck -> Zeitstempel der Bilddatei (Musik-Datenbank: neues Cover sofort)
        """library() -> Lieder wie MixxxLink.library_full; music() -> Vorhoer-Server am Mac oder ''; opener(url, timeout)."""
        self.base, self.library, self.music, self.opener, self.now = base, library, music, opener, now
        self.dir = os.path.join(base, DIR)
        self.index_path = os.path.join(base, INDEX)
        self.state_path = os.path.join(base, STATE)
        self.lock = threading.Lock()
        self.index = {}                    # Pfad -> Fingerabdruck oder '' (kein Cover)
        self.none_t = {}                   # Pfad -> wann zuletzt ohne Cover (in diesem Lauf)
        self.no_mp3 = set()                # Fingerabdruecke von Show-MP3s ohne eingebettetes Bild
        self.stop_ev = threading.Event()
        self.thread = None
        self.recheck_ev = threading.Event()
        self.recheck_thread = None
        self.current, self.error = "", ""
        self._load()

    # ---- Ablage ----
    def _load(self):
        try:
            with open(self.index_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        p, fp = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(p, str) and isinstance(fp, str) and (fp == "" or FP_RE.match(fp)):
                        self.index[p] = fp
        except OSError:
            pass

    def _remember(self, path, fp):
        with self.lock:
            if self.index.get(path) == fp:
                return
            self.index[path] = fp
            try:
                with open(self.index_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps([path, fp], ensure_ascii=False) + "\n")
            except OSError:
                pass

    def moved(self, old, new):
        """Datei am Mac umbenannt: dasselbe Cover (Fingerabdruck) gilt auch fuer den neuen Pfad. True = mitgenommen."""
        fp = self.index.get(old)
        if not fp or new in self.index:
            return False
        self._remember(new, fp)
        return True

    def mtime(self, fp):
        """Zeitstempel des abgelegten Bildes (Musik-Datenbank: neues Cover sofort zeigen, ohne die Seite neu zu laden; 09.11.2026)."""
        if not fp:
            return 0
        t = self.mt.get(fp)
        if t is None:
            try:
                t = int(os.path.getmtime(os.path.join(self.dir, fname(fp))))
            except OSError:
                t = 0
            self.mt[fp] = t
        return t

    def save(self, fp, data):
        if not FP_RE.match(str(fp or "")) or not is_image(data) or len(data) > MAX_BYTES:
            raise ValueError("Cover unbrauchbar")
        os.makedirs(self.dir, exist_ok=True)
        p = os.path.join(self.dir, fname(fp))
        with open(p + ".tmp", "wb") as f:
            f.write(data)
        os.replace(p + ".tmp", p)
        self.mt[fp] = int(time.time())

    def from_mp3(self, path, fp):
        """Cover aus einer MP3 am Pi (Show), unter ihrem Fingerabdruck abgelegt; einmal je Fingerabdruck versucht."""
        if not fp or fp in self.no_mp3:
            return None
        img = mp3_image(path)
        if img is None or len(img) > MAX_BYTES:
            self.no_mp3.add(fp)
            return None
        try:
            self.save(fp, img)
        except (ValueError, OSError):
            self.no_mp3.add(fp)
            return None
        return img

    def by_fp(self, fp):
        if not FP_RE.match(str(fp or "")):
            return None
        return self.raw(fname(fp))

    def raw(self, name):
        """Bild (Bytes) zu einem Dateinamen oder None; nur gueltige Namen, kein Pfad von aussen."""
        if not FILE_RE.match(str(name or "")):
            return None
        try:
            with open(os.path.join(self.dir, name), "rb") as f:
                return f.read()
        except OSError:
            return None

    def files(self):
        """[[Dateiname, Groesse, Aenderungszeit]] fuer die Sicherung auf den Stick (die Zeit erkennt ein geaendertes Cover gleicher
        Groesse: der Name haengt am Fingerabdruck der Musik und bleibt gleich, Frage von Markus 07.11.2026)."""
        try:
            names = os.listdir(self.dir)
        except OSError:
            return []
        out = []
        for n in sorted(names):
            if FILE_RE.match(n):
                try:
                    st = os.stat(os.path.join(self.dir, n))
                    out.append([n, st.st_size, int(st.st_mtime)])
                except OSError:
                    pass
        return out

    def restore(self, name, data):
        """Ein Bild aus der Sicherung zurueck (Name = Fingerabdruck), geprueft wie ein neu geholtes."""
        if not FILE_RE.match(str(name or "")):
            raise ValueError("Dateiname unbrauchbar")
        self.save(name[:-4].replace("_", ":", 1), data)

    # ---- Holen ----
    def fetch(self, path):
        """Cover vom Mac holen und ablegen. True = abgelegt, False = Lied ohne Cover, None = Mac nicht erreichbar."""
        music = self.music()
        if not music:
            return None
        url = music.rstrip("/") + "/cover?p=" + urllib.parse.quote(path, safe="")
        try:
            with self.opener(url, timeout=20) as r:
                fp = str(r.headers.get("X-FP") or "")
                data = r.read(MAX_BYTES + 1)
        except OSError as e:
            if getattr(e, "code", None) == 410:            # Mac kennt die Datei (noch) nicht: nichts merken, spaeter wieder fragen
                return False
            if getattr(e, "code", None) == 404:
                self._remember(path, "")
                self.none_t[path] = self.now()
                return False
            return None
        try:
            self.save(fp, data)
        except (ValueError, OSError):
            self._remember(path, "")
            self.none_t[path] = self.now()
            return False
        self._remember(path, fp)
        return True

    def for_path(self, path, fetch=True):
        """Bild zum Pfad am Mac: aus der Ablage, sonst (fetch) einmal vom Mac. None = keins."""
        fp = self.index.get(path)
        if fp:
            img = self.by_fp(fp)
            if img is not None:
                return img
        if not fetch or not path:
            return None
        if fp == "" and self.now() - self.none_t.get(path, 0) < NONE_RETRY_S:
            return None
        if fp == "" and path not in self.none_t:          # aus frueheren Laeufen: kein Cover, nicht bei jedem Anzeigen fragen
            self.none_t[path] = self.now()
            return None
        return self.by_fp(self.index.get(path, "")) if self.fetch(path) else None

    def has(self, path):
        fp = self.index.get(path)
        return bool(fp) and os.path.isfile(os.path.join(self.dir, fname(fp)))

    # ---- Nachschauen: Lieder ohne Cover wieder am Mac fragen ----
    def recheck_once(self):
        """Alle Lieder mit '' (kein Cover), die laenger als NONE_RETRY_S nicht gefragt wurden, noch einmal holen.
        Rueckgabe: Zahl der neu gefundenen Cover, None = Mac nicht erreichbar."""
        found = 0
        for x in self._songs():
            p = x["path"]
            if self.index.get(p) != "" or self.now() - self.none_t.get(p, 0) < NONE_RETRY_S:
                continue
            if self.recheck_ev.is_set():
                break
            res = self.fetch(p)
            if res is None:
                return None
            if res:
                found += 1
            self.none_t[p] = self.now()
            if self.recheck_ev.wait(RECHECK_GAP_S):
                break
        return found

    def _recheck_loop(self):
        wait = RECHECK_FIRST_S
        while not self.recheck_ev.wait(wait):
            try:
                res = self.recheck_once()
            except Exception:                  # noqa: BLE001  (nie den Pi stoeren, naechstes Mal wieder)
                res = 0
            wait = RECHECK_AWAY_S if res is None else RECHECK_S

    def start_recheck(self):
        if self.recheck_thread is None or not self.recheck_thread.is_alive():
            self.recheck_ev.clear()
            self.recheck_thread = threading.Thread(target=self._recheck_loop, name="cover-nachschauen", daemon=True)
            self.recheck_thread.start()

    # ---- Vorab-Lauf (Seite Statistik) ----
    def _songs(self):
        out, seen = [], set()
        for x in self.library() or []:
            p = x.get("path") or ""
            if p and p not in seen:
                seen.add(p)
                out.append(x)
        return out

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

    def status(self):
        songs = self._songs()
        idx = dict(self.index)
        done = sum(1 for x in songs if idx.get(x["path"]))
        none = sum(1 for x in songs if idx.get(x["path"]) == "")
        running = self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set()
        return {"running": running, "total": len(songs), "done": done, "none": none, "done_all": bool(songs) and done + none >= len(songs),
                "music": bool(self.music()), "current": self.current if running else "", "error": self.error, "files": len(self.files())}

    def run(self):
        tried = set()
        while not self.stop_ev.is_set():
            todo = [x for x in self._songs() if not self.has(x["path"]) and x["path"] not in tried]
            if not todo:
                if self._songs():
                    self._flag(False)
                    self.current = ""
                    return
                if self.stop_ev.wait(5.0):
                    return
                continue
            for x in todo:
                if self.stop_ev.is_set():
                    return
                self.current = str(x.get("title") or os.path.basename(x["path"]))[:120]
                res = self.fetch(x["path"])
                if res is None:
                    self.error = "Der Light-Butler erreicht den Musik-Rechner gerade nicht (Mixxx-App oder Helfer laeuft? Stick eingesteckt?)"
                    if self.stop_ev.wait(WAIT_S):
                        return
                    break
                tried.add(x["path"])
                self.error = ""
                if self.stop_ev.wait(GAP_S):
                    return

    def start(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive() and not self.stop_ev.is_set():
                return self.status()
            self._flag(True)
            self.error = ""
            self.stop_ev = threading.Event()
            self.thread = threading.Thread(target=self.run, name="cover-vorab", daemon=True)
            self.thread.start()
        return self.status()

    def stop(self):
        self._flag(False)
        self.stop_ev.set()
        return self.status()

    def resume(self):
        if self._flag():
            self.start()
