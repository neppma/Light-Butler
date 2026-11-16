"""Export aus der Musik-Datenbank (Wunsch 10.11.2026): die gefilterte Liste als Dateien in einen Zielordner kopieren, alle in
einer Ebene (ohne Unterordner), zum Beispiel auf einen zweiten Stick fuer eine Party.

Nur kopieren, nie verschieben oder loeschen: die Quelle bleibt, wie sie ist. Gibt es im Ziel schon eine Datei mit dem Namen,
wird sie uebersprungen, wenn sie gleich gross ist (zweiter Durchgang nach einem Abbruch), sonst bekommt die neue " (2)", " (3)"
... angehaengt. Nie etwas ueberschreiben. Ziel nur ausserhalb des Musikordners (sonst entstuenden Doppelte in der Bibliothek),
nur unter /Volumes oder im Benutzerordner. Kopiert wird im eigenen Thread, eine Datei nach der anderen (erst als versteckte
Hilfsdatei, dann umbenannt: ein abgezogener Stick hinterlaesst keine halben Lieder).

Ordner waehlen: dirs(p) listet die Unterordner am Mac (Seite Musik-Datenbank, Fenster Export), mkdir legt einen neuen an.
"""
import os
import shutil
import threading
import time
import unicodedata

from pfad import norm as _pn

MAX_FILES = 20000
BAD = set('/\\:*?"<>|')


def allowed_roots():
    return ["/Volumes", os.path.expanduser("~")]


def _real(p):
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(p or ""))))


def _under(p, base):
    p, base = _pn(_real(p)), _pn(_real(base))
    return p == base or p.startswith(base.rstrip("/") + "/")


def check_dest(dest, music_root=""):
    """Zielordner pruefen; Rueckgabe der echte Pfad oder ValueError mit Grund auf Deutsch."""
    if not isinstance(dest, str) or not dest.strip() or "\0" in dest:
        raise ValueError("Kein Zielordner gewaehlt")
    d = _real(dest)
    if not any(_under(d, r) for r in allowed_roots()):
        raise ValueError("Ziel nur auf einem Laufwerk unter /Volumes oder im Benutzerordner")
    if d in ("/Volumes", _real("~")):
        raise ValueError("Bitte einen Ordner waehlen, nicht die oberste Ebene")
    if not os.path.isdir(d):
        raise ValueError("Zielordner gibt es nicht")
    if music_root and (_under(d, music_root) or _under(music_root, d)):
        raise ValueError("Nicht in den Musikordner exportieren (sonst entstehen Doppelte in der Bibliothek)")
    if not os.access(d, os.W_OK):
        raise ValueError("In den Zielordner darf nicht geschrieben werden")
    return d


def mounts(run=None):
    """Laufwerke am Mac aus "mount": {Pfad: (Art, Quelle)}; ohne die versteckten (nobrowse, etwa Recovery)."""
    import subprocess
    try:
        out = (run or (lambda: subprocess.run(["/sbin/mount"], capture_output=True, text=True, timeout=5).stdout))()
    except (OSError, subprocess.SubprocessError):
        return {}
    res = {}
    for line in out.splitlines():
        src, sep, rest = line.partition(" on ")
        if not sep or " (" not in rest:
            continue
        path, opts = rest.rsplit(" (", 1)
        kinds = [x.strip() for x in opts.rstrip(")").split(",")]
        if path.startswith("/Volumes/") and "nobrowse" not in kinds:
            res[path] = (kinds[0], src)
    return res


def drives(music_root="", run=None):
    """Verbundene Laufwerke fuer die Auswahl: [{path, name, kind ("usb"|"net"|"home"), host, free, music}]."""
    out = []
    for path, (fs, src) in sorted(mounts(run).items(), key=lambda x: x[0].casefold()):
        if not os.path.isdir(path):
            continue
        net = fs in ("smbfs", "afpfs", "nfs", "webdav", "cifs")
        host = ""
        if net and "@" in src:
            host = src.split("@", 1)[1].split("/", 1)[0].split(".", 1)[0]
        elif net:
            host = src.lstrip("/").split("/", 1)[0].split(".", 1)[0]
        try:
            free = shutil.disk_usage(path).free
        except OSError:
            free = None
        out.append({"path": path, "name": unicodedata.normalize("NFC", os.path.basename(path)), "kind": "net" if net else "usb",
                    "host": host, "free": free, "music": bool(music_root) and _under(music_root, path)})
    home = os.path.expanduser("~")
    try:
        hfree = shutil.disk_usage(home).free
    except OSError:
        hfree = None
    out.append({"path": home, "name": "Benutzerordner", "kind": "home", "host": "", "free": hfree, "music": False})
    return out


def dirs(p="", music_root="", run=None):
    """Unterordner zum Auswaehlen: {path, parent, dirs: [Name], free, drives}. Ohne p: nur die verbundenen Laufwerke."""
    if not p:
        return {"path": "", "parent": None, "dirs": [], "free": None, "drives": drives(music_root, run)}
    d = _real(p)
    if not any(_under(d, r) for r in allowed_roots()) or not os.path.isdir(d):
        raise ValueError("Ordner nicht erlaubt oder nicht vorhanden")
    names = []
    try:
        for x in os.listdir(d):
            if not x.startswith(".") and os.path.isdir(os.path.join(d, x)) and x not in ("$RECYCLE.BIN", "System Volume Information"):
                names.append(unicodedata.normalize("NFC", x))
    except OSError as e:
        raise ValueError(f"Ordner nicht lesbar: {e}") from None
    try:
        free = shutil.disk_usage(d).free
    except OSError:
        free = None
    parent = os.path.dirname(d)
    top = d.count("/") <= 2 or d == _real("~")              # /Volumes/STICK oder Benutzerordner: hoeher geht es zur Laufwerksliste
    inside = bool(music_root) and _under(d, music_root)
    return {"path": d, "parent": "" if top else parent, "dirs": sorted(names, key=str.casefold), "free": free,
            "music": inside}


def mkdir(parent, name):
    """Neuen Ordner im Ziel anlegen (nur ein Name, keine Pfade)."""
    name = unicodedata.normalize("NFC", str(name or "")).strip()
    if not name or any(c in BAD for c in name) or name.startswith(".") or len(name) > 120:
        raise ValueError("Ungueltiger Ordnername")
    d = dirs(parent)["path"]
    if not d:
        raise ValueError("Erst ein Laufwerk waehlen")
    p = os.path.join(d, name)
    if os.path.exists(p):
        raise ValueError("Den Ordner gibt es schon")
    os.mkdir(p)
    return p


def free_name(dest, name, size, taken):
    """Zielname: gleicher Name, sonst " (2)", " (3)" ... Liegt unter einem dieser Namen schon eine gleich grosse Datei (frueherer
    Export), None = ueberspringen. taken = in diesem Durchgang schon vergebene Namen (die zaehlen nie als "schon da")."""
    stem, ext = os.path.splitext(name)
    k = 1
    while True:
        cand = name if k == 1 else f"{stem} ({k}){ext}"
        p = os.path.join(dest, cand)
        if cand.casefold() not in taken:
            if not os.path.exists(p):
                return cand
            try:
                if os.path.getsize(p) == size:
                    return None
            except OSError:
                pass
        k += 1


class Exporter:
    """Ein Export zur Zeit. start(dest, files) mit files = [(Pfad in der Bibliothek, Datei am Mac)]."""

    def __init__(self, log=None, copy=shutil.copyfile):
        self.log, self.copy = log or (lambda t: None), copy
        self.lock = threading.Lock()
        self.st = {"state": "idle"}
        self.stop_ev = threading.Event()
        self.thread = None

    def status(self):
        with self.lock:
            return dict(self.st, errors=list(self.st.get("errors") or [])[:50])

    def stop(self):
        self.stop_ev.set()
        return self.status()

    def start(self, dest, files, missing=0):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                raise ValueError("Es laeuft schon ein Export")
            files = list(files)[:MAX_FILES]
            total = 0
            for _p, f in files:
                try:
                    total += os.path.getsize(f)
                except OSError:
                    pass
            try:
                free = shutil.disk_usage(dest).free
            except OSError:
                free = None
            if free is not None and total > free:
                raise ValueError(f"Zu wenig Platz im Ziel: {total / 1e9:.1f} GB noetig, {free / 1e9:.1f} GB frei")
            self.stop_ev.clear()
            self.st = {"state": "run", "dest": dest, "total": len(files), "bytes": total, "done": 0, "copied": 0, "skipped": 0,
                       "renamed": 0, "missing": int(missing), "errors": [], "t0": time.time(), "cur": ""}
            self.thread = threading.Thread(target=self._run, args=(dest, files), name="export", daemon=True)
            self.thread.start()
            return dict(self.st)

    def _run(self, dest, files):
        taken = set()
        import stick_hold
        for _p, src in files:
            if stick_hold.held(src) or stick_hold.held(dest):   # ein beteiligtes Laufwerk wird ausgeworfen
                self.stop_ev.set()
            if self.stop_ev.is_set():
                with self.lock:
                    self.st["state"] = "stopped"
                self.log(f"Export angehalten: {self.st['copied']} kopiert")
                return
            name = os.path.basename(src)
            with self.lock:
                self.st["cur"] = name
            try:
                size = os.path.getsize(src)
                tgt = free_name(dest, unicodedata.normalize("NFC", name), size, taken)
                if tgt is None:
                    with self.lock:
                        self.st["skipped"] += 1
                else:
                    taken.add(tgt.casefold())
                    tmp = os.path.join(dest, "." + tgt + ".lb-tmp")
                    try:
                        self.copy(src, tmp)
                        os.replace(tmp, os.path.join(dest, tgt))
                    finally:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    with self.lock:
                        self.st["copied"] += 1
                        if tgt != unicodedata.normalize("NFC", name):
                            self.st["renamed"] += 1
            except OSError as e:
                with self.lock:
                    self.st["errors"].append(f"{name}: {e.strerror or e}")
                if not os.path.isdir(dest):                  # Ziel weg (Stick abgezogen): aufhoeren
                    with self.lock:
                        self.st["state"] = "err"
                        self.st["error"] = "Zielordner nicht mehr erreichbar"
                    return
            with self.lock:
                self.st["done"] += 1
        with self.lock:
            self.st["state"], self.st["cur"], self.st["t1"] = "ok", "", time.time()
        self.log(f"Export fertig: {self.st['copied']} kopiert, {self.st['skipped']} schon da, nach {dest}")
