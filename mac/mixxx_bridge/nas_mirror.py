"""Spiegeln zwischen Laufwerken am Mac (Wunsch 10.11.2026 Stick -> NAS, verallgemeinert 12.11.2026: Quelle und Ziel frei waehlbar,
etwa NAS -> Stick oder Stick -> Ersatzstick). Jeder gewaehlte Oberordner der Quelle kommt genau so ans Ziel (rsync --delete); was
dort ersetzt oder geloescht wird, landet im Papierkorb des Ziels: auf der NAS #recycle/Spiegel-<Datum>/..., auf Sticks und Platten
Spiegel-Papierkorb/Spiegel-<Datum>/... ganz oben am Laufwerk. Ordner, die es nur am Ziel gibt, bleiben unberuehrt. An der Quelle
wird nie etwas geaendert. Der Wartebereich musik-import liegt am Stick neben dem Musikordner und kommt mit.

Vorlagen (pairs in ~/Light-Butler-Daten/nas_spiegel.json): Stick -> NAS, NAS -> Stick, Stick -> Ersatzstick und eigene; "@musik" steht
fuer den Musikordner aus dem Panel. Je Vorlage: gewaehlte Ordner, frueher gespiegelte (aufgeloeste bietet der Probelauf an, am Ziel
in den Papierkorb zu legen, nur mit Haken), Dauer des letzten Probelaufs. Geschwindigkeit je Weg (usb>net, net>usb, usb>usb ...)
gemessen, daraus die Dauer.

Erst ein Probelauf (rsync --dry-run, Zahlen je Ordner, Platz am Ziel), dann Spiegeln. Schutz: Quelle und Ziel nie ineinander, ein
schreibgeschuetztes Laufwerk nie als Ziel, zu wenig Platz oder Dateien ab 4 GB auf FAT32 halten an, ab 20 Dateien, die am Ziel
wegkommen, eigene Bestaetigung. Schreibt das Spiegeln auf den Musik-Stick, ruhen Analyse, Ordner-Liste und Vorhoeren
(stick_hold, Sperre "spiegeln"); wird ein beteiligter Stick ausgeworfen, hoert es auf.
"""
import json
import os
import posixpath
import shutil
import subprocess
import threading
import time
import unicodedata
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

CONF = "nas_spiegel.json"
IMPORT_NAME = "musik-import"
BACKUP_NAME = "musik-backup"                            # Sicherung der Kurven, Cue-Punkte, Cover (stems_backup.py), 13.11.2026
PROGRAMS_NAME = "Light-Butler-Programme"                 # Pakete, Handbuecher, Sicherung (programs_copy.py), 14.11.2026
BESIDE = (IMPORT_NAME, BACKUP_NAME, PROGRAMS_NAME)      # liegen am Stick neben dem Musikordner, auf der NAS im Ordner selbst
RECYCLE = "#recycle"
EXCLUDES = ("._*", ".DS_Store", "#recycle", "@eaDir", "Spiegel-Papierkorb")
# vor dem ersten Mal: die Ordner, die am 10.11.2026 von Hand gespiegelt oder geholt wurden
INITIAL = ("CHILLOUT", "FILMMUSIK", "KLASSIK", "MEDITATION", "MUSICAL", "OLDIES", "SAMPLES", "SYNTHESIZER", "TESTSAMPLES",
           "U-MUSIK", "WEIHNACHTEN", "APRES SKI", "FREE")
MAX_LIST = 300
# Abschaltzeit der NAS (Wunsch 10.11.2026: sie faehrt um Mitternacht herunter): Spiegeln startet nur, wenn es vorher fertig wird
OFF_DEFAULT = "00:00"
DEFAULT_SPEED = 25e6                                   # Byte/s ueber das Netz, gemessen 10.11.2026 (72 GB in 49 min); danach je Lauf gemessen
SAFETY = 1.25                                          # Schaetzung mal 1,25 plus 5 Minuten Reserve
PLAN_MIN_S = 180                                       # Probelauf nur, wenn bis zur Abschaltung mehr als 3 Minuten (oder die Dauer des letzten) bleiben
# Name/IP, MAC und Abschaltzeit der NAS stehen in den Einstellungen am Pi (music.json "nas", Wunsch 10.11.2026: nicht im
# Quelltext); die Bruecke holt sie mit dem Musikordner (MusicServer.apply_conf -> from_pi) und merkt sie in nas_spiegel.json.


def from_pi(nas):
    """NAS-Angaben aus den Einstellungen uebernehmen (nur wenn anders)."""
    if not isinstance(nas, dict):
        return False
    c = load_conf()
    new = {"host": str(nas.get("host") or "").strip()[:64], "mac": "", "off_at": str(nas.get("off_at") or "").strip()[:5]}
    try:
        new["mac"] = norm_mac(nas.get("mac")) if nas.get("mac") else ""
    except ValueError:
        new["mac"] = ""
    if all(c.get(k, None) == v for k, v in new.items()):
        return False
    c.update(new)
    save_conf(c)
    return True


def seconds_until(off_at, now):
    """Sekunden bis zur naechsten Abschaltzeit "HH:MM" (leer = keine Abschaltung -> None)."""
    try:
        h, m = [int(x) for x in str(off_at or "").split(":")]
    except ValueError:
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    lt = time.localtime(now)
    today = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, 0, 0, 0, -1))
    return (today if today > now else today + 86400) - now


def estimate_s(st, speed):
    """Geschaetzte Dauer des Spiegelns: so lange wie der Probelauf (vergleichen) plus Menge / Geschwindigkeit."""
    fs = st.get("folders") or []
    b = sum(f.get("bytes") or 0 for f in fs)
    plan_s = max(0.0, float(st.get("t1") or 0) - float(st.get("t0") or 0))
    return plan_s + b / max(1e5, speed or DEFAULT_SPEED)


def wol_packet(mac):
    h = "".join(c for c in str(mac or "").lower() if c in "0123456789abcdef")
    if len(h) != 12:
        raise ValueError("MAC-Adresse ungueltig (zum Beispiel aa:bb:cc:dd:ee:ff)")
    return b"\xff" * 6 + bytes.fromhex(h) * 16


def norm_mac(mac):
    parts = [x for x in str(mac or "").replace("-", ":").lower().split(":") if x]
    if len(parts) != 6 or any(not (1 <= len(x) <= 2) or any(c not in "0123456789abcdef" for c in x) for x in parts):
        raise ValueError("MAC-Adresse ungueltig (zum Beispiel aa:bb:cc:dd:ee:ff)")
    return ":".join(x.zfill(2) for x in parts)


def lookup_mac(host, run=subprocess.run):
    """MAC der NAS aus dem ARP-Speicher des Mac (nach einem Ping), sonst ""."""
    import socket
    try:
        ip = socket.gethostbyname(host)
        run(["/sbin/ping", "-c", "1", "-t", "2", ip], capture_output=True, timeout=5)
        out = run(["/usr/sbin/arp", "-n", ip], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    import re
    m = re.search(r" at ([0-9a-f:]+) ", out or "")
    try:
        return norm_mac(m.group(1)) if m else ""
    except ValueError:
        return ""


def reachable(host, port=445, timeout=2.0):
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def nfc(s):
    return unicodedata.normalize("NFC", str(s or ""))


def conf_path():
    return os.path.join(_pfad.daten(), CONF)


def load_conf():
    try:
        with open(conf_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_conf(d):
    p = conf_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


def find_rsync():
    """rsync 3 (Homebrew): kann --backup-dir mit --delete sicher; das rsync von macOS ist dafuer zu alt."""
    for p in ("/opt/homebrew/bin/rsync", "/usr/local/bin/rsync"):
        if os.path.isfile(p):
            return p
    return ""


MUSIC = "@musik"                                        # Platzhalter in den Vorlagen: der Musikordner (aus dem Panel), wo er gerade liegt
TRASH_LOCAL = "Spiegel-Papierkorb"                      # Sticks und Platten haben kein #recycle: eigener Ordner ganz oben am Laufwerk
SKIP_DIRS = ("$RECYCLE.BIN", "System Volume Information", TRASH_LOCAL, "Light-Butler Papierkorb")
NET_FS = ("smbfs", "afpfs", "nfs", "webdav", "cifs")
FS_NAME = {"msdos": "FAT32", "exfat": "exFAT", "apfs": "APFS", "hfs": "Mac OS", "ntfs": "NTFS", "smbfs": "Netz (SMB)", "afpfs": "Netz (AFP)"}
FAT_MAX = 4 * 1024 ** 3 - 1                             # FAT32: keine Datei ab 4 GB
DEL_CONFIRM = 20                                        # ab so vielen Dateien, die am Ziel wegkommen, eigene Bestaetigung
# Geschwindigkeit je Weg (Byte/s), bis ein Lauf sie misst: Stick -> NAS gemessen 10.11.2026, die anderen vorsichtig angenommen
DEFAULT_SPEEDS = {"usb>net": DEFAULT_SPEED, "net>usb": 20e6, "usb>usb": 15e6, "net>net": 10e6,
                  "usb>int": 30e6, "int>usb": 15e6, "net>int": 25e6, "int>net": 25e6}
# Interne Festplatte des Musik-Rechners (Wunsch 13.11.2026): nur im Benutzerordner, nie in Library oder Papierkorb
MAC = "@mac"                                            # Platzhalter in der Vorlage "Stick -> Mac": ~/Musik-Spiegel/<Ordnername>
MAC_DIR = "Musik-Spiegel"
HOME_SKIP = ("Library", ".Trash", "Applications")


def home():
    return nfc(os.path.realpath(os.path.expanduser("~")))


def allowed(p):
    """Ordner, die Quelle oder Ziel sein duerfen: auf einem Laufwerk unter /Volumes oder im Benutzerordner (nicht er selbst,
    nicht Library, Papierkorb, Programme)."""
    p = str(p or "").rstrip("/")
    if p.startswith("/Volumes/") and p.count("/") >= 2:
        return True
    h = home()
    if not p.startswith(h + "/"):
        return False
    return p[len(h) + 1:].split("/", 1)[0] not in HOME_SKIP
PRESETS = (("stick-nas", "Stick → NAS"), ("nas-stick", "NAS → Stick"), ("stick-ersatz", "Stick → Ersatzstick"), ("stick-mac", "Stick → Mac"))
STICK_MAC = {"id": "stick-mac", "name": "Stick → Mac", "src": "@musik", "dst": "@mac", "preset": True}


def drives(music_root="", run=None, isdir=os.path.isdir, with_mac=True):
    """Laufwerke am Mac fuer die Auswahl: [{path, name, kind ("net"|"usb"), fs, fs_name, ro, total, free, host, music, system}].
    Systemplatte, Recovery und versteckte (nobrowse) fehlen; schreibgeschuetzte (ro) duerfen nur Quelle sein."""
    try:
        out = (run or (lambda: subprocess.run(["/sbin/mount"], capture_output=True, text=True, timeout=5).stdout))()
    except (OSError, subprocess.SubprocessError):
        out = ""
    res = []
    for line in (out or "").splitlines():
        src, sep, rest = line.partition(" on ")
        if not sep or " (" not in rest:
            continue
        path, opts = rest.rsplit(" (", 1)
        o = [x.strip() for x in opts.rstrip(")").split(",")]
        if not path.startswith("/Volumes/") or "nobrowse" in o or path.count("/") != 2 or not isdir(path):
            continue
        fs = o[0]
        net = fs in NET_FS
        host = ""
        if net:
            host = (src.split("@", 1)[1] if "@" in src else src.lstrip("/")).split("/", 1)[0].split(".", 1)[0]
        try:
            du = shutil.disk_usage(path)
            total, free = du.total, du.free
        except OSError:
            total = free = None
        res.append({"path": nfc(path), "name": nfc(os.path.basename(path)), "kind": "net" if net else "usb", "fs": fs,
                    "fs_name": FS_NAME.get(fs, fs), "ro": "read-only" in o, "total": total, "free": free, "host": host,
                    "src": src, "music": bool(music_root) and (music_root == path or music_root.startswith(path + "/"))})
    res = sorted(res, key=lambda d: (not d["music"], d["kind"] != "net", d["name"].casefold()))
    if with_mac:                                          # interne Festplatte (Benutzerordner), immer zuletzt
        h = home()
        try:
            du = shutil.disk_usage(h)
            total, free = du.total, du.free
        except OSError:
            total = free = None
        res.append({"path": h, "name": "Dieser Mac", "kind": "int", "fs": "apfs", "fs_name": "interne Festplatte", "ro": False,
                    "total": total, "free": free, "host": "", "src": "", "music": False})
    return res


def volume_of(path):
    """Laufwerk: /Volumes/NAME, im Benutzerordner der Benutzerordner (Papierkorb ~/Spiegel-Papierkorb), sonst der Ordner selbst."""
    h = home()
    return stick_vol(path) or (h if inside(str(path or ""), h) else str(path or "").rstrip("/"))


def stick_vol(path):
    parts = [x for x in str(path or "").split("/") if x]
    return "/" + "/".join(parts[:2]) if len(parts) >= 2 and parts[0] == "Volumes" else ""


def inside(a, b):
    """Liegt a in b (oder ist a gleich b)?"""
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/")


def check_pair(src, dst, volumes_only=True):
    """Quelle und Ziel pruefen: beide da, unter /Volumes, nicht dasselbe und keines im anderen."""
    s = os.path.realpath(nfc(src or "").rstrip("/")) if src else ""
    d = os.path.realpath(nfc(dst or "").rstrip("/")) if dst else ""
    if not s:
        raise ValueError("Bitte die Quelle wählen")
    if not d:
        raise ValueError("Bitte das Ziel wählen")
    for x, what in ((s, "Quelle"), (d, "Ziel")):
        if volumes_only and not allowed(x):
            raise ValueError(f"{what} bitte auf einem Laufwerk unter /Volumes oder in einem Ordner im Benutzerordner des Musik-Rechners wählen")
    if not os.path.isdir(s):
        raise ValueError("Quelle nicht erreichbar (Laufwerk verbunden?)")
    if not os.path.isdir(d) and not os.path.isdir(os.path.dirname(d)) and not inside(d, home()):
        raise ValueError("Ziel nicht erreichbar (Laufwerk verbunden?)")
    if inside(s, d) or inside(d, s):
        raise ValueError("Quelle und Ziel sind derselbe Ordner oder liegen ineinander")
    return s, d


def check_dest(dest, root, volumes_only=True):
    """Frueheres Ziel (Stick -> NAS): geprueft wie ein Paar mit dem Musikordner als Quelle."""
    d = os.path.realpath(nfc(dest or "").rstrip("/"))
    if volumes_only and (not d.startswith("/Volumes/") or d.count("/") < 2):
        raise ValueError("Ziel bitte auf einem Laufwerk unter /Volumes wählen")
    if not os.path.isdir(d):
        raise ValueError("Ziel nicht erreichbar (Laufwerk verbunden?)")
    vol = (stick_vol(os.path.realpath(root)) or os.path.dirname(os.path.realpath(root).rstrip("/"))) if root else ""
    if vol and inside(d, vol):
        raise ValueError("Das Ziel liegt auf dem Stick selbst")
    return d


def subdirs(path):
    try:
        return sorted((nfc(x) for x in os.listdir(path) if not x.startswith((".", "#", "@")) and x not in SKIP_DIRS
                       and os.path.isdir(os.path.join(path, x))), key=str.casefold)
    except OSError:
        return []


def sources(root):
    """[(Name, Quelle)] : alle Oberordner im Musikordner und die Ordner daneben (musik-import, musik-backup)."""
    out = [(x, os.path.join(root, x)) for x in subdirs(root)]
    for name in BESIDE:
        imp = os.path.join(os.path.dirname(root.rstrip("/")), name)
        if os.path.isdir(imp) and name not in [n for n, _p in out]:
            out.append((name, imp))
    return out


def du(path, limit_s=20.0):
    """Groesse eines Ordners in Byte (fuer den Papierkorb am Ziel; nach limit_s Sekunden abgebrochen)."""
    t0, n = time.time(), 0
    for d, _ds, fs in os.walk(path):
        for f in fs:
            try:
                n += os.path.getsize(os.path.join(d, f))
            except OSError:
                pass
        if time.time() - t0 > limit_s:
            break
    return n


def rsync_cmd(rsync, src, dst, backup, dry):
    cmd = [rsync, "-rt", "--modify-window=2", "--delete", "--backup", "--backup-dir=" + backup]
    for e in EXCLUDES:
        cmd.append("--exclude=" + e)
    if dry:
        cmd.append("--dry-run")
    return cmd + ["--itemize-changes", "--out-format=%i|%l|%n", src.rstrip("/") + "/", dst.rstrip("/") + "/"]


def parse(out):
    """rsync --itemize-changes: {new, replace, delete, bytes, deleted: [Pfade]}."""
    r = {"new": 0, "replace": 0, "delete": 0, "bytes": 0, "deleted": []}
    for ln in (out or "").splitlines():
        i, _, rest = ln.partition("|")
        size, _, name = rest.partition("|")
        if i.startswith("*deleting"):
            if not name.endswith("/"):
                r["delete"] += 1
                if len(r["deleted"]) < MAX_LIST:
                    r["deleted"].append(nfc(name))
        elif len(i) > 2 and i[1] == "f":
            r["new" if "+++" in i else "replace"] += 1
            try:
                r["bytes"] += int(size)
                if int(size) > FAT_MAX:
                    r["big"] = r.get("big", 0) + 1
            except ValueError:
                pass
    return r


class Mirror:
    def __init__(self, root, log=None, run=subprocess.Popen, now=time.time, on_done=None):
        self.root, self.log, self.popen, self.now = root, log or (lambda t: None), run, now
        self.on_done = on_done                                # Musikordner geaendert (Ziel war der Stick): Ordner-Liste neu einlesen
        self.lock = threading.Lock()
        self.st = {"state": "idle"}
        self.thread, self.proc = None, None
        self.wake_st = {"state": "idle"}
        self.volumes_only = True                              # Tests: auch ausserhalb von /Volumes
        self.vol_of = volume_of                               # Tests: eigenes "Laufwerk"
        self.stop_ev = threading.Event()
        self.holding = ""                                     # Laufwerk des Musikordners, solange das Spiegeln darauf schreibt
        self._drv = (0.0, [])
        self._mx = (0.0, False)
        self.sizes = {}                                       # Ordnergroessen vor dem Probelauf: Pfad -> (Byte, Zeit), 13.11.2026
        self.size_todo = []
        self.size_lock = threading.Lock()
        self.size_thread = None
        self.du = du                                          # Tests: eigene Groessen

    SIZE_KEEP_S = 600.0

    def size_of(self, path):
        """Groesse eines Ordners aus dem Zwischenspeicher (None = wird gerade gezaehlt). Zaehlt im Hintergrund, einer nach dem
        anderen; nach SIZE_KEEP_S Sekunden oder nach einem Lauf neu."""
        with self.size_lock:
            v = self.sizes.get(path)
            if v is not None and time.time() - v[1] < self.SIZE_KEEP_S:
                return v[0]
            if path not in self.size_todo:
                self.size_todo.append(path)
            if self.size_thread is None or not self.size_thread.is_alive():
                self.size_thread = threading.Thread(target=self._size_run, name="spiegeln-groesse", daemon=True)
                self.size_thread.start()
            return v[0] if v is not None else None

    def _size_run(self):
        while True:
            with self.size_lock:
                if not self.size_todo:
                    return
                p = self.size_todo.pop(0)
            if self._busy():                                  # waehrend Probelauf und Spiegeln nicht dazwischen lesen
                with self.size_lock:
                    self.size_todo = []
                return
            n = self.du(p, 600.0) if os.path.isdir(p) else 0
            with self.size_lock:
                self.sizes[p] = (n, time.time())

    # ---- Vorlagen (Quelle -> Ziel) ----
    def music(self):
        r = (self.root() or "").rstrip("/")
        return nfc(os.path.realpath(r)) if r else ""

    def resolve(self, p):
        if p == MAC:
            return self.mac_dir()
        return self.music() if p == MUSIC else str(p or "").rstrip("/")

    def mac_dir(self):
        """Ziel der Vorlage "Stick -> Mac": ~/Musik-Spiegel/<Name des Musikordners> (etwa musik)."""
        return os.path.join(home(), MAC_DIR, os.path.basename(self.music()) or "musik")

    @staticmethod
    def pairs_of(c):
        """Vorlagen aus der Datei; beim ersten Mal die drei festen, Stick -> NAS uebernimmt das fruehere Ziel."""
        ps = c.get("pairs")
        if isinstance(ps, list) and ps:
            if not any(isinstance(p, dict) and p.get("id") == "stick-mac" for p in ps):   # neue Vorlage (13.11.2026)
                ps.insert(next((i + 1 for i, p in enumerate(ps) if isinstance(p, dict) and p.get("id") == "stick-ersatz"), len(ps)), dict(STICK_MAC))
            return ps
        old = c.get("dest") or ""
        ps = [{"id": "stick-nas", "name": "Stick → NAS", "src": MUSIC, "dst": old, "mirrored": c.get("mirrored") or list(INITIAL),
               "last": c.get("last") or 0, "plan_s": c.get("plan_s") or 0, "preset": True},
              {"id": "nas-stick", "name": "NAS → Stick", "src": old, "dst": MUSIC, "preset": True},
              {"id": "stick-ersatz", "name": "Stick → Ersatzstick", "src": MUSIC, "dst": "", "preset": True}, dict(STICK_MAC)]
        c["pairs"], c["pair"] = ps, "stick-nas"
        if c.get("speed"):
            c.setdefault("speeds", {})["usb>net"] = c["speed"]
        return ps

    def _cur(self, c):
        ps = self.pairs_of(c)
        return next((p for p in ps if p.get("id") == c.get("pair")), ps[0])

    def drives(self):
        t, v = self._drv
        if time.time() - t > 8.0 or any(not os.path.isdir(d["path"]) for d in v):   # ausgeworfen: gleich neu
            v = drives(self.music())
            self._drv = (time.time(), v)
        return v

    def drive_of(self, path):
        best = None
        for d in self.drives():
            if path and inside(path, d["path"]) and (best is None or len(d["path"]) > len(best["path"])):
                best = d
        return best

    def kind_of(self, path):
        """Art des Laufwerks. Nicht verbunden, aber die gemerkte NAS-Freigabe (smb_path): "net", damit die Seite die NAS-Zeile
        mit "NAS wecken" zeigt (Fehlerbericht 13.11.2026: schlief die NAS, fehlte der Knopf)."""
        d = self.drive_of(path)
        if d:
            return d["kind"]
        sp = str(load_conf().get("smb_path") or "")
        return "net" if sp and path and inside(path, sp) else "usb"

    def items(self, src, dst):
        """[(Name, Quelle, Ziel)] : Oberordner der Quelle. Der Wartebereich musik-import liegt am Stick neben dem Musikordner, auf
        der NAS im Ordner selbst: neben dem Musikordner als Ziel (oder auf einem Ersatzstick neben dem Ordner) kommt er daneben."""
        root = self.music()
        out = [(x, os.path.join(src, x)) for x in subdirs(src)]
        if root and src == root:
            out = sources(root)
        beside = (root and dst == root) or (root and src == root and self.vol_of(dst) != dst)
        pj = posixpath if str(dst).startswith("/") else os.path       # "/Volumes/..." ist auch unter Windows ein Mac-Pfad
        return [(n, p, pj.join(pj.dirname(dst), n) if (n in BESIDE and beside) else pj.join(dst, n)) for n, p in out]

    def selection(self, pair, items):
        """Gewaehlte Ordner: gemerkte Haken; neue Ordner (noch nie gesehen) nach der Grundregel: vom Musikordner alle, sonst die,
        die es am Ziel schon gibt (NAS -> Stick: nicht FLAC, KINDERMUSIK ...), gibt es dort keinen, alle."""
        names = [n for n, _s, _t in items]
        src = self.resolve(pair.get("src"))
        if src and src == self.music():
            base = set(names)
        else:
            have = {n for n, _s, t in items if os.path.isdir(t)}
            base = have or set(names)
        sel, seen = pair.get("sel"), pair.get("seen")
        if isinstance(sel, list) and isinstance(seen, list):
            return [n for n in names if n in sel or (n not in seen and n in base)]
        return [n for n in names if n in base]

    def trash_dir(self, dst):
        vol = self.vol_of(dst)
        if self.kind_of(dst) == "net" or os.path.isdir(os.path.join(vol, RECYCLE)):
            return os.path.join(vol, RECYCLE)
        return os.path.join(vol, TRASH_LOCAL)

    def backup_for(self, dst, target, day):
        vol = self.vol_of(dst)
        rel = os.path.relpath(target, vol)
        if rel.startswith(".."):
            rel = os.path.basename(target)
        return os.path.join(self.trash_dir(dst), "Spiegel-" + day, rel)

    def route(self, src, dst):
        return f"{self.kind_of(src)}>{self.kind_of(dst)}"

    def mixxx_running(self):
        t, v = self._mx
        if time.time() - t > 10.0:
            try:
                v = subprocess.run(["/usr/bin/pgrep", "-xi", "mixxx"], capture_output=True, timeout=3).returncode == 0
            except (OSError, subprocess.SubprocessError):
                v = False
            self._mx = (time.time(), v)
        return v

    # ---- Stand ----
    def status(self):
        with self.lock:
            st = json.loads(json.dumps(self.st))
        c = load_conf()
        ps = self.pairs_of(c)
        pair = self._cur(c)
        src, dst = self.resolve(pair.get("src")), self.resolve(pair.get("dst"))
        st["pairs"] = [{"id": p["id"], "name": p.get("name") or p["id"], "preset": bool(p.get("preset")), "last": p.get("last") or 0} for p in ps]
        st["pair"] = pair["id"]
        st["src"], st["dst"] = src, dst
        st["src_music"], st["dst_music"] = pair.get("src") == MUSIC, pair.get("dst") == MUSIC
        st["music_root"] = self.music()
        try:
            drv = self.drives()
        except Exception:                                     # noqa: BLE001
            drv = []
        st["drives"] = drv
        sd, dd = self.drive_of(src), self.drive_of(dst)
        st["src_drive"], st["dst_drive"] = (sd or {}).get("path", ""), (dd or {}).get("path", "")
        try:
            check_pair(src, dst, self.volumes_only)
            st["pair_err"] = ""
        except ValueError as e:
            st["pair_err"] = str(e)
        items = self.items(src, dst) if src and os.path.isdir(src) else []
        sel = self.selection(pair, items)
        st["avail"] = [{"name": n, "sel": n in sel, "there": os.path.isdir(t)} for n, _s, t in items]
        st["sel"] = sel
        free = (dd or {}).get("free")
        if free is None and dst:
            try:
                free = shutil.disk_usage(dst if os.path.isdir(dst) else os.path.dirname(dst)).free
            except OSError:
                free = None
        st["dst_free"], st["dst_total"] = free, (dd or {}).get("total")
        st["dst_fs"] = (dd or {}).get("fs", "")
        # vor dem Probelauf (Wunsch 13.11.2026): Groesse der gewaehlten Ordner an der Quelle und was davon am Ziel schon liegt.
        # Mindestens dazu kommt Quelle minus Ziel (Ersetztes bleibt im Papierkorb am Ziel, braucht also eher mehr): passt schon
        # das nicht, steht es rot da.
        st["src_size"] = st["dst_have"] = st["pre_need"] = st["pre_fits"] = None
        if items and sel and not st["pair_err"] and not self._busy():
            ss = [self.size_of(sp) for n, sp, _t in items if n in sel]
            ds = [self.size_of(t) if os.path.isdir(t) else 0 for n, _s, t in items if n in sel]
            if None not in ss:
                st["src_size"] = sum(ss)
            if None not in ss and None not in ds:
                st["dst_have"] = sum(ds)
                st["pre_need"] = max(0, st["src_size"] - st["dst_have"])
                st["pre_fits"] = free is None or st["pre_need"] * 1.02 + 200e6 < free
        st["sizing"] = bool(items and sel) and st["pre_need"] is None and not st["pair_err"]
        st["to_music"] = bool(self.music()) and bool(dst) and bool(stick_vol(self.music())) and inside(dst, stick_vol(self.music()))
        st["mixxx"] = st["to_music"] and self.mixxx_running()
        st["trash_name"] = (RECYCLE if dst and (self.kind_of(dst) == "net" or os.path.isdir(os.path.join(self.vol_of(dst), RECYCLE))) else TRASH_LOCAL) if dst else ""
        route = self.route(src, dst) if src and dst else "usb>net"
        speeds = c.get("speeds") or {}
        st["route"] = route
        st["speed"] = speeds.get(route) or DEFAULT_SPEEDS.get(route, DEFAULT_SPEED)
        st["speed_measured"] = bool(speeds.get(route))
        st["mirrored"] = pair.get("mirrored") or []
        st["last"] = pair.get("last") or 0
        st["rsync"] = bool(find_rsync())
        nas = bool(src and dst) and "net" in route
        st["nas"] = nas
        st["off_at"] = c.get("off_at", OFF_DEFAULT)
        st["mac"] = c.get("mac") or ""
        st["host"] = c.get("host") or ""
        sp = str(c.get("smb_path") or "")
        dsp = next((x for x in drv if sp and x["path"] == sp and str(x.get("src") or "").startswith("//")), None)
        if dsp is not None and c.get("smb") != "smb:" + dsp["src"] and not self._busy():
            # Freigabe jetzt unter anderem Benutzer verbunden (13.11.2026: neppma statt "Markus Nepp"): Adresse fuers Wecken mitnehmen
            c2 = load_conf()
            c2["smb"] = "smb:" + dsp["src"]
            save_conf(c2)
        st["online"] = self._online(st["host"], src if self.kind_of(src) == "net" else dst) if nas else True
        st["wake"] = dict(self.wake_st)
        left = seconds_until(st["off_at"], self.now()) if nas else None
        st["left_s"] = None if left is None else round(left)
        need = max(PLAN_MIN_S, float(pair.get("plan_s") or 0))
        st["plan_est_s"] = round(float(pair.get("plan_s") or 0))
        st["plan_need_s"] = round(need)
        st["plan_blocked"] = left is not None and left < need
        same = st.get("pair_id") == pair["id"] and st.get("src_p") == src and st.get("dst_p") == dst
        st["same"] = same
        if st.get("state") in ("planned", "run") and same:
            fs = st.get("folders") or []
            total = sum(f.get("bytes") or 0 for f in fs)
            st["need"] = total
            st["fits"] = free is None or total * 1.02 + 200e6 < free
            st["del_total"] = sum(f.get("delete") or 0 for f in fs)
            st["big"] = sum(f.get("big") or 0 for f in fs) if st["dst_fs"] == "msdos" else 0
            if st["state"] == "planned":
                eta = estimate_s(st, st["speed"])
                st["eta_s"] = round(eta)
                st["too_long"] = left is not None and eta * SAFETY + 300 > left
                st["sel_changed"] = sorted(st.get("plan_sel") or []) != sorted(sel)
            else:                                             # laeuft: Rest aus dem, was schon geschafft ist
                done_b = sum(f.get("bytes") or 0 for f in fs if f.get("name") in (st.get("done") or []))
                el = max(1.0, self.now() - float(st.get("t0") or self.now()))
                rate = done_b / el if done_b > 200e6 and el > 30 else st["speed"]
                st["rest_s"] = round((total - done_b) / max(1e5, rate))
        return st

    def _online(self, host, path=""):
        """Ist die NAS erreichbar? (SMB-Port, hoechstens alle 10 s neu geprueft; ohne Name: aus dem Laufwerk geschlossen)"""
        now = time.time()
        cache = getattr(self, "_on_cache", (None, 0.0, None))
        if cache[0] == (host, path) and now - cache[1] < 10.0:
            return cache[2]
        on = reachable(host) if host else (bool(path) and os.path.isdir(path))
        self._on_cache = ((host, path), now, on)
        return on

    def set_conf(self, off_at=None, mac=None):
        c = load_conf()
        if off_at is not None:
            if off_at and seconds_until(off_at, self.now()) is None:
                raise ValueError("Uhrzeit bitte als HH:MM (leer = NAS schaltet nie ab)")
            c["off_at"] = off_at
        if mac is not None:
            c["mac"] = norm_mac(mac) if mac else ""
        save_conf(c)
        return self.status()

    def wake(self, send=None, run=subprocess.run):
        """NAS per Wake-on-LAN wecken, dann bis 4 Minuten warten, bis sie antwortet, und die Freigabe wieder verbinden."""
        c = load_conf()
        host = c.get("host") or ""
        if not host:
            raise ValueError("Die NAS ist nicht eingetragen: Einstellungen → Verbindungen → NAS (Name oder IP, MAC-Adresse)")
        mac = c.get("mac") or lookup_mac(host, run)
        if not mac:
            raise ValueError("MAC-Adresse der NAS unbekannt: in den Einstellungen eintragen (steht in der FRITZ!Box bei der NAS)")
        if not c.get("mac"):
            c["mac"] = mac
            save_conf(c)
        pkt = wol_packet(mac)
        if send is None:
            import socket

            def send(data):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                try:
                    for addr in ("255.255.255.255", "192.168.1.255"):
                        for port in (9, 7):
                            s.sendto(data, (addr, port))
                finally:
                    s.close()
        send(pkt)
        self.wake_st = {"state": "wait", "t0": self.now(), "mac": mac}
        self._on_cache = (None, 0.0, None)
        self.log(f"NAS wecken: Wake-on-LAN an {mac}")
        smb = c.get("smb") or ""
        share = c.get("smb_path") or c.get("dest") or ""

        def wait():
            t0 = time.time()
            while time.time() - t0 < 240:
                if reachable(host):
                    break
                time.sleep(5)
            else:
                self.wake_st.update(state="err", error="Die NAS antwortet nach 4 Minuten nicht")
                return
            if share and not os.path.isdir(share) and smb:        # Freigabe wieder verbinden (Passwort aus dem Schluesselbund)
                try:
                    run(["/usr/bin/osascript", "-e", f'mount volume "{smb}"'], capture_output=True, timeout=90)
                except (OSError, subprocess.SubprocessError):
                    pass
            self._drv = (0.0, [])
            self.wake_st.update(state="ok" if (not share or os.path.isdir(share)) else "nomount", t1=time.time())
        threading.Thread(target=wait, daemon=True, name="nas-wecken").start()
        return self.status()

    def _remember_smb(self, c, path):
        d = self.drive_of(path)
        if d and d["kind"] == "net" and str(d.get("src") or "").startswith("//"):
            c["smb"], c["smb_path"] = "smb:" + d["src"], d["path"]

    def _edit(self, fn):
        """Vorlage aendern (nicht waehrend eines Laufs); ein alter Probelauf gilt dann nicht mehr."""
        if self._busy():
            raise ValueError("Es läuft gerade etwas: erst anhalten")
        c = load_conf()
        self.pairs_of(c)
        fn(c, self._cur(c))
        save_conf(c)
        with self.lock:
            if self.st.get("state") in ("planned", "ok", "stopped", "err"):
                self.st = {"state": "idle"}
        return self.status()

    def _check_path(self, p, side):
        d = os.path.realpath(nfc(p or "").rstrip("/"))
        if self.volumes_only and not allowed(d):
            raise ValueError("Bitte einen Ordner auf einem Laufwerk unter /Volumes oder im Benutzerordner wählen (nicht den Benutzerordner selbst, nicht Library)")
        if not os.path.isdir(d) and not (side == "dst" and (os.path.isdir(os.path.dirname(d)) or inside(d, home()))):
            raise ValueError("Ordner nicht erreichbar (Laufwerk verbunden?)")
        if side == "dst":
            dr = self.drive_of(d)
            if dr and dr.get("ro"):
                raise ValueError(f"{dr['name']} ist schreibgeschützt und kann kein Ziel sein")
        return MUSIC if d == self.music() else MAC if d == self.mac_dir() else d

    def set_folder(self, side, path):
        if side not in ("src", "dst"):
            raise ValueError("Seite fehlt")
        v = self._check_path(path, side)

        def fn(c, p):
            p[side] = v
            p.pop("sel", None)
            p.pop("seen", None)
            self._remember_smb(c, self.resolve(v))
        return self._edit(fn)

    def set_drive(self, side, drive):
        """Laufwerk aus der Auswahlliste: Ordner darauf nach der Grundregel (der Musikordner, wenn er dort liegt; ein Ersatzstick
        bekommt denselben Ordner wie der Stick; sonst das Laufwerk selbst)."""
        drive = nfc(drive).rstrip("/")
        if not any(d["path"] == drive for d in self.drives()) and self.volumes_only:
            raise ValueError("Laufwerk nicht verbunden")
        root = self.music()
        folder = drive
        if drive == home():                               # interne Festplatte: nie der Benutzerordner selbst
            folder = self.mac_dir()
            if side == "src" and not os.path.isdir(folder):
                folder = next((x for x in (os.path.dirname(folder), os.path.join(drive, "Music")) if os.path.isdir(x)), folder)
            return self.set_folder(side, folder)
        if root and inside(root, drive):
            folder = root
        elif side == "dst" and root and stick_vol(root):
            c = load_conf()
            if self.resolve(self._cur(c).get("src")) == root:
                folder = os.path.join(drive, os.path.relpath(root, stick_vol(root)))
        return self.set_folder(side, folder)

    def set_sel(self, names):
        names = [nfc(n) for n in names if isinstance(n, str)][:500]

        def fn(c, p):
            src, dst = self.resolve(p.get("src")), self.resolve(p.get("dst"))
            all_n = [n for n, _s, _t in self.items(src, dst)] if src and os.path.isdir(src) else []
            p["sel"] = [n for n in all_n if n in names]
            p["seen"] = all_n
        return self._edit(fn)

    def select(self, pid):
        def fn(c, p):
            if not any(x.get("id") == pid for x in c["pairs"]):
                raise ValueError("Vorlage nicht gefunden")
            c["pair"] = pid
        return self._edit(fn)

    def add_pair(self, name):
        name = nfc(name).strip()[:40]
        if not name:
            raise ValueError("Bitte einen Namen eingeben")

        def fn(c, p):
            k = 1
            while any(x.get("id") == f"eigen-{k}" for x in c["pairs"]):
                k += 1
            n = {"id": f"eigen-{k}", "name": name, "src": p.get("src") or "", "dst": p.get("dst") or ""}
            c["pairs"].append(n)
            c["pair"] = n["id"]
        return self._edit(fn)

    def rename_pair(self, pid, name):
        """Eigene Vorlage umbenennen (Wunsch 13.11.2026); die festen behalten ihren Namen."""
        name = nfc(name).strip()[:40]
        if not name:
            raise ValueError("Bitte einen Namen eingeben")

        def fn(c, p):
            x = next((x for x in c["pairs"] if x.get("id") == pid), None)
            if x is None or x.get("preset"):
                raise ValueError("Die festen Vorlagen behalten ihren Namen")
            x["name"] = name
        return self._edit(fn)

    def del_pair(self, pid):
        def fn(c, p):
            x = next((x for x in c["pairs"] if x.get("id") == pid), None)
            if x is None or x.get("preset"):
                raise ValueError("Die festen Vorlagen bleiben")
            c["pairs"].remove(x)
            if c.get("pair") == pid:
                c["pair"] = c["pairs"][0]["id"]
        return self._edit(fn)

    def set_dest(self, dest):
        """Frueher: nur das Ziel fuer Stick -> NAS."""
        d = check_dest(dest, self.root(), self.volumes_only)

        def fn(c, p):
            c["pair"] = "stick-nas"
            pp = next(x for x in c["pairs"] if x["id"] == "stick-nas")
            pp["dst"] = d
            c["dest"] = d
            self._remember_smb(c, d)
        self._edit(fn)
        return d

    def _busy(self):
        return self.thread is not None and self.thread.is_alive()

    # ---- Probelauf und Spiegeln ----
    def start(self, op, gone=(), confirm_del=False):
        rsync = find_rsync()
        if not rsync:
            raise ValueError("rsync 3 fehlt am Mac (Terminal: brew install rsync)")
        c = load_conf()
        pair = self._cur(c)
        src, dst = check_pair(self.resolve(pair.get("src")), self.resolve(pair.get("dst")), self.volumes_only)
        dr = self.drive_of(dst)
        if dr and dr.get("ro"):
            raise ValueError(f"{dr['name']} ist schreibgeschützt")
        items = self.items(src, dst)
        sel = self.selection(pair, items)
        if not (isinstance(pair.get("sel"), list) and isinstance(pair.get("seen"), list)):
            # Auswahl festhalten (Fehlerbericht 13.11.2026): sonst galt nach einem abgebrochenen ersten Lauf wieder die Grundregel
            # "nur was am Ziel schon liegt", und die noch nicht gespiegelten Ordner fielen still heraus
            pair["sel"], pair["seen"] = list(sel), [n for n, _s, _t in items]
            save_conf(c)
        if not sel:
            raise ValueError("Keine Ordner gewählt")
        st = self.status()
        if op == "run":
            if self.st.get("state") != "planned" or not st.get("same") or st.get("sel_changed"):
                raise ValueError("Erst den Probelauf machen")
            if st.get("too_long"):
                raise ValueError(f"Reicht nicht mehr: die NAS schaltet um {st['off_at']} ab (noch {round(st['left_s'] / 60)} min), "
                                 f"das Spiegeln dauert etwa {round(st['eta_s'] / 60)} min")
            if not st.get("fits", True):
                raise ValueError("Zu wenig Platz am Ziel")
            if st.get("big"):
                raise ValueError(f"{st['big']} Dateien sind 4 GB oder größer: das Ziel ist FAT32 und kann sie nicht speichern")
            if (st.get("del_total") or 0) >= DEL_CONFIRM and not confirm_del:
                raise ValueError(f"Am Ziel kommen {st['del_total']} Dateien weg: bitte bestätigen")
        if op == "plan" and st.get("plan_blocked"):
            raise ValueError(f"Die NAS schaltet um {st['off_at']} ab (in {max(1, round(st['left_s'] / 60))} min): heute keinen Probelauf mehr")
        with self.lock:
            if self._busy():
                raise ValueError("Es läuft schon etwas")
            self.stop_ev.clear()
            keep = dict(self.st) if op == "run" else {}
            self.st = {"state": "plan" if op == "plan" else "run", "pair_id": pair["id"], "src_p": src, "dst_p": dst, "t0": self.now(),
                       "folders": keep.get("folders", []), "gone": keep.get("gone", []), "plan_sel": sel, "cur": "", "i": 0, "done": [],
                       "dest": dst}
            todo = [x for x in items if x[0] in sel]
            self.thread = threading.Thread(target=self._work, args=(op, pair["id"], src, dst, todo, [n for n, _s, _t in items], rsync,
                                                                    [nfc(g) for g in gone], st["route"]), daemon=True, name="spiegeln")
            self.thread.start()
            return dict(self.st)

    def stop(self):
        self.stop_ev.set()
        p = self.proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        return self.status()

    def _blocked(self, paths):
        """Stick wird ausgeworfen (fremde Sperre) oder Anhalten gedrueckt."""
        import stick_hold
        if self.stop_ev.is_set():
            return True
        if stick_hold.mine("spiegeln"):
            return False
        return any(stick_hold.held(p) for p in paths if p)

    def _rsync(self, cmd, paths=()):
        # Fehlerbericht 12.11.2026: rsync meldete einen Dateinamen mit abgeschnittenem Umlaut (Byte 0xcc), text=True brach mit
        # UnicodeDecodeError ab, die Spiegelung blieb auf "laeuft" stehen. Unlesbare Bytes werden jetzt ersetzt.
        self.proc = self.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        import stick_hold
        done = threading.Event()

        def watch():                                          # Stick wird ausgeworfen oder Anhalten: rsync beenden
            k = 0
            while not done.wait(1.0):
                k += 1
                if self.holding and k % 60 == 0 and stick_hold.mine("spiegeln"):
                    stick_hold.hold(self.holding, by="spiegeln")  # Sperre frisch halten (sonst faellt sie nach 10 min)
                if self._blocked(paths):
                    try:
                        self.proc.terminate()
                    except OSError:
                        pass
                    return
        threading.Thread(target=watch, daemon=True).start()
        out, err = self.proc.communicate()
        done.set()
        return self.proc.returncode, out or "", err or ""

    def _work(self, op, pid, src, dst, todo, names, rsync, gone_sel, route):
        import stick_hold
        day = time.strftime("%Y-%m-%d", time.localtime(self.now()))
        conf = load_conf()
        pair = next((p for p in self.pairs_of(conf) if p.get("id") == pid), {})
        mirrored = pair.get("mirrored") or []
        paths = (src, dst)
        tmp_empty = ""
        try:
            if op == "plan":
                folders = []
                for k, (name, s, t) in enumerate(todo):
                    with self.lock:
                        self.st.update(cur=name, i=k, n=len(todo))
                    if self._blocked(paths):
                        raise InterruptedError
                    tt = t
                    if not os.path.isdir(os.path.dirname(t)):        # Ziel-Ordner gibt es noch nicht: gegen einen leeren rechnen
                        if not tmp_empty:
                            import tempfile
                            tmp_empty = tempfile.mkdtemp(prefix="s2l-spiegel-")
                        tt = os.path.join(tmp_empty, "x")
                    rc, out, err = self._rsync(rsync_cmd(rsync, s, tt, self.backup_for(dst, t, day), True), paths)
                    r = parse(out)
                    r.update(name=name, exists=os.path.isdir(t), rc=rc, err=(err.strip().splitlines() or [""])[-1][:200] if rc not in (0, 24) else "")
                    folders.append(r)
                gone = [g for g in mirrored if g not in names and os.path.isdir(os.path.join(dst, g))]
                trash = self.trash_dir(dst)
                tinfo = {"path": trash, "bytes": du(trash)} if os.path.isdir(trash) and os.path.basename(trash) == TRASH_LOCAL else None
                with self.lock:
                    self.st.update(state="planned", folders=folders, gone=gone, cur="", t1=self.now(), trash=tinfo)
                c2 = load_conf()                              # Dauer des Probelaufs merken (Schaetzung, Sperre vor der Abschaltung)
                for p in self.pairs_of(c2):
                    if p.get("id") == pid:
                        p["plan_s"] = round(self.now() - float(self.st.get("t0") or self.now()))
                save_conf(c2)
                return
            music_vol = stick_vol(self.music())
            if music_vol and inside(dst, music_vol):        # schreibt auf den Musik-Stick: Analyse, Ordner-Liste, Vorhoeren ruhen
                stick_hold.hold(music_vol, by="spiegeln")
                self.holding = music_vol
            os.makedirs(dst, exist_ok=True)
            done = []
            for k, (name, s, t) in enumerate(todo):
                with self.lock:
                    self.st.update(cur=name, i=k, n=len(todo))
                if self._blocked(paths):
                    raise InterruptedError
                rc, _out, err = self._rsync(rsync_cmd(rsync, s, t, self.backup_for(dst, t, day), False), paths)
                if self._blocked(paths):
                    raise InterruptedError
                if rc not in (0, 24):                        # 24 = Datei verschwunden (Umlaut-Reste auf der NAS): kein Fehler
                    raise RuntimeError(f"{name}: {(err.strip().splitlines() or ['rsync Fehler ' + str(rc)])[-1][:200]}")
                done.append(name)
                with self.lock:
                    self.st["done"] = list(done)
            moved = []
            backup_base = os.path.join(self.trash_dir(dst), "Spiegel-" + day)
            for g in gone_sel:                               # aufgeloeste Ordner: am Ziel in den Papierkorb (nur mit Haken)
                src_g = os.path.join(dst, g)
                if g not in mirrored or g in names or "/" in g or g.startswith(".") or not os.path.isdir(src_g):   # nur frueher gespiegelte
                    continue
                tgt = self.backup_for(dst, src_g, day)
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                k = 2
                base_t = tgt
                while os.path.exists(tgt):
                    tgt = f"{base_t} ({k})"
                    k += 1
                shutil.move(src_g, tgt)
                moved.append(g)
            conf = load_conf()
            sel_names = [n for n, _s, _t in todo]
            run_s = self.now() - float(self.st.get("t0") or self.now())
            moved_b = sum(f.get("bytes") or 0 for f in self.st.get("folders") or [])
            for p in self.pairs_of(conf):
                if p.get("id") == pid:
                    keep = [g for g in (p.get("mirrored") or []) if g not in names and g not in moved and os.path.isdir(os.path.join(dst, g))]
                    p.update(mirrored=sorted(set(sel_names) | set(keep), key=str.casefold), last=self.now())
                    if pid == "stick-nas":
                        conf.update(mirrored=p["mirrored"], last=p["last"])
            if moved_b > 200e6 and run_s > 30:                 # Geschwindigkeit dieses Wegs fuer die naechste Schaetzung merken
                conf.setdefault("speeds", {})[route] = round(min(200e6, max(1e6, moved_b / run_s)))
            save_conf(conf)
            with self.lock:
                self.st.update(state="ok", cur="", done=done, trashed_dirs=moved, t1=self.now(), backup=backup_base)
            self.log(f"Gespiegelt: {len(done)} Ordner von {src} nach {dst}" + (f", in den Papierkorb: {', '.join(moved)}" if moved else ""))
        except InterruptedError:
            with self.lock:
                self.st.update(state="stopped", cur="")
            self.log("Spiegeln angehalten")
        except Exception as e:                               # noqa: BLE001  nie auf "laeuft" haengen bleiben
            with self.lock:
                self.st.update(state="err", error=str(e)[:300], cur="")
            self.log(f"Spiegeln: {e}")
        finally:
            self.proc = None
            if op == "run":                                   # gespiegelt: Groessen am Ziel neu zaehlen
                with self.size_lock:
                    self.sizes = {}
            if tmp_empty:
                shutil.rmtree(tmp_empty, ignore_errors=True)
            if self.holding:
                if stick_hold.mine("spiegeln"):
                    stick_hold.release()
                self.holding = ""
                if self.on_done is not None:
                    try:
                        self.on_done()
                    except Exception:                         # noqa: BLE001
                        pass
