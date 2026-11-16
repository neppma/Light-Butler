"""
folder_art.py - Ordnerbilder in die MP3s schreiben (Wunsch von Markus, 08.11.2026).

Bei aelteren Alben liegt das Cover nur als Folder.jpg / AlbumArt*.jpg / cover.jpg im Ordner, nicht in der MP3 (oder die MP3
hat im APIC nur einen Dateinamen, alter Windows Media Player). Der Light-Butler zeigt das Ordnerbild schon an; Mixxx, Handy
und Auto haben es aber erst, wenn es in der MP3 steckt.

Ablauf: suchen (nur Ordner mit einem Bild, je MP3 nur die Kopfzeilen der ID3-Rahmen lesen), Liste zeigen, auf Klick
schreiben (tag_edit.write_tags, nur das Bild; die Musik bleibt Bit fuer Bit gleich). Grosse Bilder werden vorher mit sips auf
hoechstens EMBED_PX verkleinert. Alles laeuft in einem eigenen Faden, eine Datei nach der anderen.
"""
import os
import threading
import time

EMBED_PX = 800                     # so gross kommt das Bild in die MP3 (Handy, Auto, Mixxx reicht das)
EMBED_MAX = 400 * 1024             # kleinere Bilder bleiben, wie sie sind


def _syncsafe(b):
    return (b[0] & 0x7F) << 21 | (b[1] & 0x7F) << 14 | (b[2] & 0x7F) << 7 | (b[3] & 0x7F)


def has_image(path, looks_like_image):
    """Steckt in der MP3 ein echtes Bild (APIC/PIC)? Liest nur Rahmenkoepfe und den Anfang der Bilddaten."""
    with open(path, "rb") as f:
        head = f.read(10)
        if head[:3] != b"ID3" or len(head) < 10:
            return False
        ver, end, pos = head[3], 10 + _syncsafe(head[6:10]), 10
        if head[5] & 0x40 and ver >= 3:
            f.seek(10)
            x = f.read(4)
            pos += _syncsafe(x) if ver == 4 else 4 + int.from_bytes(x, "big")
        hdr = 6 if ver == 2 else 10
        while pos + hdr <= end:
            f.seek(pos)
            h = f.read(hdr)
            if len(h) < hdr:
                return False
            if ver == 2:
                fid, size = h[:3], int.from_bytes(h[3:6], "big")
            else:
                fid = h[:4]
                size = _syncsafe(h[4:8]) if ver == 4 else int.from_bytes(h[4:8], "big")
            if not fid.strip(b"\0") or size <= 0:
                return False
            if fid in (b"APIC", b"PIC"):
                body = f.read(min(size, 1024))
                if fid == b"PIC":
                    rest = body[5:]
                else:
                    z = body.find(b"\0", 1)
                    rest = body[z + 2:] if z > 0 else b""
                enc = body[0] if body else 0
                if enc in (1, 2):
                    i = 0
                    while i + 1 < len(rest) and rest[i:i + 2] != b"\0\0":
                        i += 2
                    data = rest[i + 2:]
                else:
                    data = rest[rest.find(b"\0") + 1:]
                if looks_like_image(data):
                    return True
            pos += hdr + size
    return False


class FolderArt:
    """paths() -> Pfade der Bibliothek; locate(p) -> Datei am Mac oder None; folder_image(ordner) -> (Bytes, MIME, Name) oder None."""

    def __init__(self, paths, locate, folder_image, looks_like_image, thumb, write_cover, log=None):
        self.paths, self.locate, self.folder_image = paths, locate, folder_image
        self.looks_like_image, self.thumb, self.write_cover = looks_like_image, thumb, write_cover
        self.log = log or (lambda t: None)
        self.lock = threading.Lock()
        self.state, self.done, self.total, self.t = "idle", 0, 0, 0.0   # idle, scan, ready, write
        self.items, self.errors, self.written = [], [], 0
        self.thread = None

    def status(self, limit=300):
        with self.lock:
            return {"state": self.state, "done": self.done, "total": self.total, "n": len(self.items), "written": self.written,
                    "errors": self.errors[-20:], "t": self.t,
                    "items": [{"path": p, "image": img} for p, f, img in self.items[:limit]]}

    def _run(self, fn):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return False
            self.thread = threading.Thread(target=fn, name="ordnerbilder", daemon=True)
            self.thread.start()
        return True

    def scan(self):
        """Im Hintergrund suchen. False = laeuft schon."""
        return self._run(self._scan)

    def _scan(self):
        with self.lock:
            self.state, self.done, self.items, self.errors, self.written = "scan", 0, [], [], 0
        by_dir = {}
        for p in sorted(self.paths()):
            if p.lower().endswith(".mp3"):
                f = self.locate(p)
                if f:
                    by_dir.setdefault(os.path.dirname(f), []).append((p, f))
        with self.lock:
            self.total = sum(len(v) for v in by_dir.values())
        found = []
        for d, songs in by_dir.items():
            img = None
            try:
                img = self.folder_image(d)
            except OSError:
                img = None
            for p, f in songs:
                if img is not None:
                    try:
                        if not has_image(f, self.looks_like_image):
                            found.append((p, f, img[2]))
                    except OSError:
                        pass
                with self.lock:
                    self.done += 1
        with self.lock:
            self.items, self.state, self.t = found, "ready", time.time()
        self.log(f"Ordnerbilder: {len(found)} MP3s ohne eigenes Bild, im Ordner liegt eins")

    def write(self, paths=None):
        """Die gefundenen (oder nur paths) schreiben. False = laeuft schon oder nichts gesucht."""
        with self.lock:
            if self.state not in ("ready",):
                return False
            want = set(paths) if paths else None
            todo = [x for x in self.items if want is None or x[0] in want]
        return self._run(lambda: self._write(todo))

    def _write(self, todo):
        with self.lock:
            self.state, self.done, self.total = "write", 0, len(todo)
        cache, left = {}, []
        for p, f, name in todo:
            d = os.path.dirname(f)
            try:
                if d not in cache:
                    img = self.folder_image(d)
                    data = img[0] if img else None
                    if data is not None and len(data) > EMBED_MAX:
                        small, _mime = self.thumb(data, EMBED_PX)
                        data = small if self.looks_like_image(small) and len(small) < len(data) else data
                    cache[d] = data
                if cache[d] is None:
                    raise OSError("Bild im Ordner nicht mehr da")
                if has_image(f, self.looks_like_image):    # inzwischen anderswo eingetragen: nichts tun
                    continue
                self.write_cover(f, cache[d])
                with self.lock:
                    self.written += 1
            except Exception as e:                          # noqa: BLE001  (eine Datei darf die anderen nicht aufhalten)
                with self.lock:
                    self.errors.append(f"{os.path.basename(f)}: {e}"[:200])
                left.append((p, f, name))
            with self.lock:
                self.done += 1
        with self.lock:
            done_paths = {x[0] for x in todo} - {x[0] for x in left}
            self.items = [x for x in self.items if x[0] not in done_paths]
            self.state = "ready"
        self.log(f"Ordnerbilder: {self.written} MP3s mit Bild versehen, {len(left)} Fehler")
