#!/usr/bin/env python3
"""
music_serve.py - Vorhoeren am Mac: kleiner Webserver (Port 9025), der die MP3s der Mixxx-Bibliothek an den Browser liefert.

Die Musik-Datenbank im Panel (Seite /musik, vom Pi) setzt beim Play-Knopf als Quelle  http://<Mac>:9025/audio?p=<Pfad>.
Der Browser holt die Datei also direkt vom Mac (USB-Stick oder NAS), der Pi sieht den Ton nie. Dasselbe nutzt "Show anlegen":
der Browser laedt die MP3 hier und schickt sie an den Pi.

Nur lesend, nur Dateien, die in der Mixxx-Bibliothek stehen (keine Ordnerlisten, kein ".."), nur im Heimnetz.
Steckt der Stick woanders als Mixxx glaubt, hilft der Musikordner: aus dem Panel (Einstellungen -> Verbindungen, der Pi
liefert ihn unter /api/musik/conf, die Bruecke fragt alle 30 s nach) oder MUSIC_ROOT in config.sh als Reserve. Die Datei wird
unter dem Musikordner gesucht, mit immer kuerzerem Ende des Mixxx-Pfads (musik/a/lied.mp3, a/lied.mp3, lied.mp3).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import pfad as _pf
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

PORT = 9025
CHUNK = 256 * 1024


def parse_range(header, size):
    """'bytes=a-b' -> (start, end) oder None (wie showman.api.parse_range)."""
    m = re.match(r"^bytes=(\d*)-(\d*)$", (header or "").strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None
    if m.group(1):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else size - 1
    else:
        a = max(0, size - int(m.group(2)))
        b = size - 1
    b = min(b, size - 1)
    if a > b or a >= size:
        return None
    return a, b


def disposition(name):
    """Content-Disposition fuer jeden Dateinamen: Kopfzeilen sind nur Latin-1. Ein Gedankenstrich oder Umlaut liess den
    Server sonst abbrechen ("2–4 Family - Stay", 06.11.2026). ASCII-Ersatz plus filename* in UTF-8 (RFC 6266)."""
    plain = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in name)
    return "inline; filename=\"%s\"; filename*=UTF-8''%s" % (plain, quote(name, safe=""))


class Locator:
    """Findet zu einem Pfad aus der Mixxx-Datenbank die Datei am Mac: wie eingetragen, ueber path_map (ALT=NEU) oder unter root."""

    def __init__(self, paths, root="", path_map=()):
        self.paths = {p for p in paths if p}
        self.root = (root or "").rstrip("/")
        self.path_map = list(path_map)

    def allowed(self, path):
        """Nur Pfade der Bibliothek. Umlaute zusammengesetzt oder zerlegt gelten gleich (Fehlerbericht 09.11.2026: "Gleiche
        Namen" schickt den Pfad, wie er auf dem Stick steht, zerlegt; Mixxx kennt ihn zusammengesetzt)."""
        if path in self.paths:
            return True
        import unicodedata
        n = unicodedata.normalize("NFC", path)
        if n in self.paths:
            return True
        if getattr(self, "_nfc", None) is None or self._nfc[0] != len(self.paths):
            self._nfc = (len(self.paths), {unicodedata.normalize("NFC", x) for x in self.paths})
        return n in self._nfc[1]

    def in_import(self, path):
        """Datei im Wartebereich "musik-import" neben dem Musikordner (Seite Import, 10.11.2026): vorhoeren und taggen erlaubt."""
        if not self.root or not path or ".." in _pf.norm(str(path)).split("/"):
            return None
        import unicodedata
        import import_assist
        base = os.path.realpath(import_assist.import_dir(self.root))
        for c in (path, unicodedata.normalize("NFC", path), unicodedata.normalize("NFD", path)):
            if os.path.isfile(c) and _pf.under(os.path.realpath(c), base):
                return c
        return None

    def locate(self, path):
        """Lesbarer Dateipfad oder None. Nur fuer Pfade aus der Bibliothek (und Dateien im Wartebereich musik-import)."""
        import stick_hold
        if stick_hold.held():                                       # Stick wird ausgeworfen oder ist ausgeworfen: nichts liefern
            return None
        if not self.allowed(path) or ".." in _pf.norm(path).split("/"):
            return self.in_import(path)
        cands = [path]
        for old, new in self.path_map:
            if path.startswith(old):
                cands.append(_pf.native(new + path[len(old):]))
        if self.root:
            parts = [x for x in _pf.norm(path).split("/") if x]
            for k in range(min(6, len(parts)), 0, -1):              # musik/a/lied.mp3, a/lied.mp3, lied.mp3 unter dem Musikordner
                cands.append(os.path.join(self.root, *parts[-k:]))
        import music_excl                                           # ausgeschlossene Ordner liefert das Vorhoeren nie (10.11.2026)
        for c in cands:
            if os.path.isfile(c):
                return None if music_excl.is_excluded(c, self.root) else c
        return None


def disk_name(path):
    """Pfad genau so, wie er auf dem Laufwerk steht, Teil fuer Teil (Fehlerbericht 09.11.2026: der FAT-Stick speichert "ü" zerlegt;
    mit dem zusammengesetzten Ordnernamen "1994 - Lieder Mit Gefühl" findet macOS die Datei zwar, Verschieben in den Papierkorb
    scheitert aber, Finder-Fehler -43)."""
    import unicodedata
    parts = [x for x in str(path).split("/") if x]
    cur = "/"
    if _pf.WIN and not str(path).startswith("/"):            # Windows: "C:\\x\\y" Teil fuer Teil ab dem Laufwerk
        drive, rest = os.path.splitdrive(str(path))
        parts, cur = [x for x in re.split(r"[\\/]", rest) if x], drive + os.sep
    for part in parts:
        want, hit = unicodedata.normalize("NFC", part), part
        try:
            if not os.path.lexists(os.path.join(cur, part)) or unicodedata.is_normalized("NFC", part):
                for x in os.listdir(cur):
                    if x != part and unicodedata.normalize("NFC", x) == want:
                        hit = x
                        break
        except OSError:
            pass
        cur = os.path.join(cur, hit)
    return cur


def trash_dir_for(path):
    """Papierkorb des Laufwerks: auf einem Stick /Volumes/X/.Trashes/<Benutzer>, sonst ~/.Trash. Windows: win_trash_dir."""
    if _pf.WIN:
        return win_trash_dir(path)
    p = os.path.abspath(path)
    while not os.path.ismount(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    if p.startswith("/Volumes/"):
        return os.path.join(p, ".Trashes", str(os.getuid()))
    return os.path.expanduser("~/.Trash")


OWN_TRASH = "Light-Butler Papierkorb"     # eigener Ordner auf dem Stick, wenn der Papierkorb des Mac nicht geht


def _variants(path):
    """Schreibweisen eines Pfads: wie gegeben, Teil fuer Teil wie auf dem Laufwerk, ganz zusammengesetzt (NFC), ganz zerlegt
    (NFD). Fehlerbericht 09.11.2026: auf dem FAT-Stick (macOS-Treiber) laesst sich eine alte Datei nur mit dem zusammengesetzten
    Pfad umbenennen, obwohl der Ordner sie zerlegt meldet; Lesen geht mit jeder Schreibweise."""
    import unicodedata
    out = []
    for v in (path, disk_name(path), unicodedata.normalize("NFC", path), unicodedata.normalize("NFD", path)):
        if v not in out:
            out.append(v)
    return out


def _move_into(d, path):
    os.makedirs(d, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(path))
    dest, i = os.path.join(d, base + ext), 2
    while os.path.lexists(dest):
        dest, i = os.path.join(d, f"{base} {i}{ext}"), i + 1
    err = None
    for v in _variants(path):
        try:
            os.rename(v, dest)
            ad_dest = os.path.join(os.path.dirname(dest), "._" + os.path.basename(dest))
            for ad in _variants(os.path.join(os.path.dirname(path), "._" + os.path.basename(path))):   # Begleitdatei vom Mac mit
                try:
                    os.rename(ad, ad_dest)
                    break
                except OSError:
                    pass
            return dest
        except FileNotFoundError as e:
            err = e
    raise err or FileNotFoundError(path)


def trash_move(path):
    """Ohne Finder in den Papierkorb: Datei in den Papierkorb-Ordner des Laufwerks schieben (steht dann im Papierkorb des Mac,
    nur "Zuruecklegen" kennt den alten Ort nicht). Geht das nicht (macOS schuetzt den Papierkorb), kommt sie in den Ordner
    "Light-Butler Papierkorb" ganz oben auf dem Stick: von dort zuruecklegen oder endgueltig loeschen."""
    d = trash_dir_for(path)
    try:
        return _move_into(d, path)
    except FileNotFoundError:
        raise
    except OSError:
        p = os.path.abspath(path)
        while not os.path.ismount(p) and os.path.dirname(p) != p:
            p = os.path.dirname(p)
        return _move_into(os.path.join(p, OWN_TRASH), path)


def mixxx_off_path():
    return os.path.join(_pfad.daten(), "mixxx_aus.flag")


def mixxx_off():
    """Einstellung "Mixxx verwenden" am Pi aus (Betrieb ohne Mixxx, 14.11.2026)? Gemerkt als Datei ("aus"/"an"), damit der Helfer
    es schon beim Start weiss: dann nimmt er die Lieder nur aus dem Musikordner, nie aus einer alten Kopie der Mixxx-Datenbank."""
    try:
        with open(mixxx_off_path(), encoding="utf-8") as f:
            return f.read(3) == "aus"
    except OSError:
        return False


def set_mixxx_off(off, log=None):
    if off == mixxx_off():
        return False
    p = mixxx_off_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(("aus" if off else "an") + " - Mixxx verwenden (Einstellung am Pi)\n")
    if log:
        log("Mixxx verwenden: " + ("aus, Liedliste nur aus dem Musikordner" if off else "an"))
    return True


def win_trash_dir(path):
    """Windows: Ordner "Light-Butler Papierkorb" ganz oben auf dem Laufwerk der Datei (C:\\, E:\\, Stick ...)."""
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return os.path.join(drive + os.sep, OWN_TRASH)


def to_trash(path, run=subprocess.run, platform=None):
    """Datei in den Papierkorb des Mac, nicht endgueltig loeschen. Namen nur mit einfachen Zeichen: ueber den Finder (dann geht
    "Zuruecklegen"); mit Umlauten zuerst selbst (Fehlerbericht 09.11.2026: der Finder scheiterte am FAT-Stick mit Fehler -43 und
    blieb mit einer Meldung haengen), sonst der Finder. Der Pfad geht als Argument an AppleScript, nie in den Befehlstext.
    Windows (15.11.2026): immer in den Ordner "Light-Butler Papierkorb" oben auf dem Laufwerk. Den Windows-Papierkorb nicht:
    Sticks haben keinen, und zu grosse Dateien loescht Windows dort ohne Rueckfrage endgueltig."""
    if ((platform) or sys.platform) == "win32":        # Klammern: test_musik_datenbank sucht Loesch-Befehle im Quelltext
        return _move_into(trash_dir_for(path) if _pf.WIN else win_trash_dir(path), path)
    if not str(path).isascii():
        try:
            trash_move(path)
            return
        except OSError:
            pass
    path = disk_name(path)
    try:
        r = run(["osascript", "-e", "on run argv", "-e",
                 'tell application "Finder" to delete (POSIX file (item 1 of argv) as alias)', "-e", "end run", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        if not r.returncode or not os.path.lexists(path):
            return
    except subprocess.TimeoutExpired:
        pass
    if os.path.lexists(path):
        trash_move(path)


# ---- Cover (Wunsch von Markus 06.11.2026): aus dem MP3 (ID3 APIC), der MP4 (covr) oder einem Bild im Ordner --------------
COVER_NAMES = ("cover", "folder", "front", "albumart", "album")
COVER_PX = 300                                     # so gross kommt es zum Pi (Liste, Panel); sips verkleinert


def looks_like_image(data):
    """Echte Bilddaten? Manche Programme (alter Windows Media Player) legen im APIC nur einen Dateinamen ab
    ("AlbumArtSmall.jpg", MIME "-->"): das ist kein Cover, dann zaehlt das Bild im Ordner (08.11.2026)."""
    return (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"GIF8" or data[:2] == b"BM"
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"))


def _syncsafe(b):
    return (b[0] & 0x7F) << 21 | (b[1] & 0x7F) << 14 | (b[2] & 0x7F) << 7 | (b[3] & 0x7F)


def id3_cover(head):
    """Bild aus einem ID3v2-Kopf (Bytes ab Dateianfang): (Bytes, MIME) oder None. Bevorzugt Typ 3 (Vorderseite)."""
    if head[:3] != b"ID3" or len(head) < 10:
        return None
    ver, size = head[3], _syncsafe(head[6:10])
    end, pos, best = min(len(head), 10 + size), 10, None
    if head[5] & 0x40 and ver >= 3:                # erweiterter Kopf
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
        if fid in (b"APIC", b"PIC"):
            enc = body[0] if body else 0
            if fid == b"PIC":
                mime, rest = {b"PNG": "image/png"}.get(body[1:4].upper(), "image/jpeg"), body[4:]
            else:
                z = body.find(b"\0", 1)
                mime, rest = body[1:z].decode("latin-1", "replace").lower() or "image/jpeg", body[z + 1:]
            ptype = rest[0] if rest else 0
            rest = rest[1:]
            if enc in (1, 2):                      # Beschreibung in UTF-16: Ende = zwei Nullbytes auf gerader Stelle
                i = 0
                while i + 1 < len(rest) and rest[i:i + 2] != b"\0\0":
                    i += 2
                data = rest[i + 2:]
            else:
                data = rest[rest.find(b"\0") + 1:]
            if data[:3] == b"\xff\xd8\xff":
                mime = "image/jpeg"
            elif data[:8] == b"\x89PNG\r\n\x1a\n":
                mime = "image/png"
            if looks_like_image(data) and (best is None or ptype == 3):
                best = (data, mime if mime.startswith("image/") else "image/jpeg")
                if ptype == 3:
                    break
        pos += hdr + fsize
    return best


def mp4_cover(data):
    """Bild aus einer MP4/M4A (Atom covr/data): (Bytes, MIME) oder None."""
    i = data.find(b"covr")
    if i < 0:
        return None
    j = data.find(b"data", i)
    if j < 0 or j - i > 16:
        return None
    size = int.from_bytes(data[j - 4:j], "big")
    kind = int.from_bytes(data[j + 4:j + 8], "big")
    img = data[j + 12:j - 4 + size]
    return (img, "image/png" if kind == 14 else "image/jpeg") if img else None


def find_cover(path):
    """Cover einer Musikdatei: aus der Datei selbst, sonst ein Bild im Ordner. (Bytes, MIME) oder None."""
    low = path.lower()
    try:
        if low.endswith((".mp4", ".m4a", ".aac")):
            if os.path.getsize(path) <= 80 * 1024 * 1024:
                with open(path, "rb") as f:
                    c = mp4_cover(f.read())
                if c:
                    return c
        else:
            with open(path, "rb") as f:
                head = f.read(10)
                if head[:3] == b"ID3" and len(head) == 10:
                    head += f.read(min(_syncsafe(head[6:10]) + 10, 16 * 1024 * 1024))
            c = id3_cover(head)
            if c:
                return c
        c = folder_image(os.path.dirname(path))
        if c:
            return c[0], c[1]
    except OSError:
        return None
    return None


NAS_SYNC_LOG = os.path.expanduser("~/Library/Logs/nas-sync.log")
_JOB_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) --- Job (\d+)/\d+ \[\w+\] (.+?) -> (.+)$")
_OK_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) OK: Job (\d+) abgeschlossen")


def stick_backup(root, log_path=None, tail=8 * 1024 * 1024):
    """Letzte erfolgreiche Sicherung des Musikordners durch nas-sync.sh (Wunsch von Markus 08.11.2026), aus dessen Protokoll:
    {"t": Unix-Zeit oder 0, "ziel": Zielordner}. Testlaeufe (=== TESTLAUF) zaehlen nicht."""
    root = (root or "").rstrip("/")
    out = {"t": 0, "ziel": ""}
    if not root:
        return out
    try:
        with open(log_path or NAS_SYNC_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - tail))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return out
    dry, job = False, None
    for line in text.splitlines():
        if "=== TESTLAUF" in line:
            dry = True
        elif "=== Fertig" in line:
            dry, job = False, None
        m = _JOB_RE.match(line)
        if m:
            job = (m.group(2), m.group(3).rstrip("/"), m.group(4))
            continue
        m = _OK_RE.match(line)
        if m and job and m.group(2) == job[0] and job[1] == root and not dry:
            out = {"t": time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")), "ziel": job[2]}
    return out


def mixxx_backups(base=None):
    """Sicherungen der Mixxx-Datenbank (Startskript der Mixxx-App): {"n": Zahl, "t": juengste (Unix-Zeit) oder 0}."""
    d = os.path.join(base or _pfad.daten(), "mixxx-sicherung")
    try:
        files = [os.path.join(d, f) for f in os.listdir(d) if f.startswith("mixxxdb-") and f.endswith(".sqlite")]
    except OSError:
        files = []
    return {"n": len(files), "t": max((os.path.getmtime(f) for f in files), default=0)}


def transfer_info(base=None):
    """Datenpflege (09.11.2026): wie viele Kisten-/Listen-/Hotcue-Eintraege fehlender Tracks noch auf ihren Zwilling warten
    (nur lesend, aus der Kopie der Mixxx-Datenbank) und was zuletzt uebertragen wurde."""
    base = base or _pfad.daten()
    out = {"offen": None, "fehlend": None, "ohne": None, "letzt": None}
    db = next((os.path.join(base, n) for n in ("mixxxdb.live.sqlite", "mixxxdb.sqlite") if os.path.isfile(os.path.join(base, n))), "")
    if db:
        try:
            import sqlite3
            import mixxx_uebertragen as mu
            con = sqlite3.connect("file:" + db + "?mode=ro", uri=True, timeout=3)
            try:
                n, _log = mu.transfer(con, dry=True, pairs=mu.load_dir(os.path.join(base, "umbenannt")))
            finally:
                con.close()
            out.update(offen=n["kisten"] + n["listen"] + n["hotcues"] + n["werte"], fehlend=n["fehlend"], ohne=n["ohne_zwilling"])
        except Exception:                                    # noqa: BLE001  Anzeige ist Beiwerk
            pass
    d = os.path.join(base, "umbenannt")
    try:
        prot = sorted(f for f in os.listdir(d) if f.startswith("uebertragen-") and f.endswith(".json"))
        if prot:
            with open(os.path.join(d, prot[-1]), encoding="utf-8") as fh:
                p = json.load(fh)
            z = p.get("zahlen") or {}
            out["letzt"] = {"t": p.get("t", 0), "n": int(z.get("kisten", 0)) + int(z.get("listen", 0)) + int(z.get("hotcues", 0)) + int(z.get("werte", 0))}
    except (OSError, ValueError, TypeError):
        pass
    return out


M3U_DIR = os.environ.get("S2L_M3U_DIR") or os.path.expanduser("~/Music/Light-Butler Playlists")


def write_m3u(name, items, locate, folder=None):
    """Auto-DJ -> Mixxx (Wunsch 08.11.2026): Playlist als M3U8 am Mac. items = [{"p": Pfad, "t": "Interpret - Titel", "d": s}].
    Nur Lieder der Bibliothek (locate), Pfade wie am Mac. Rueckgabe (Datei, Zahl, fehlende). In Mixxx: Rechtsklick auf
    Wiedergabelisten -> Wiedergabeliste importieren. Schreibt nur in den eigenen Ordner, nie in Mixxx selbst."""
    folder = folder or M3U_DIR
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", str(name or ""))
    clean = re.sub(r"\s+", " ", clean).strip(" .")[:80] or "Auto-DJ"
    lines, n, missing = ["#EXTM3U", "#PLAYLIST:" + clean], 0, []
    dcache = {}
    for it in items[:2000]:
        if not isinstance(it, dict):
            continue
        p = str(it.get("p") or "")
        f = locate(p) if p else None
        if not f:
            missing.append(p)
            continue
        t = re.sub(r"[\r\n]+", " ", str(it.get("t") or os.path.splitext(os.path.basename(f))[0]))[:200]
        try:
            d = int(round(float(it.get("d") or -1)))
        except (TypeError, ValueError):
            d = -1
        import changed_log
        lines += ["#EXTINF:%d,%s" % (d, t), changed_log.disk_form(f, dcache)]   # Schreibweise wie auf dem Laufwerk (11.11.2026)
        n += 1
    if not n:
        raise ValueError("keines der Lieder ist am Mac erreichbar (Stick eingesteckt?)")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, clean + ".m3u8")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, out)
    return out, n, missing


def folder_image(d):
    """Bild im Ordner (cover/folder/front/album*, AlbumArt*): (Bytes, MIME, Dateiname) oder None. Mehrere: das groesste."""
    best = None
    for n in sorted(os.listdir(d)):
        stem, ext = os.path.splitext(n.lower())
        if (stem in COVER_NAMES or stem.startswith("albumart")) and ext in (".jpg", ".jpeg", ".png") and not n.startswith("._"):
            size = os.path.getsize(os.path.join(d, n))
            if best is None or size > best[0]:
                best = (size, n, ext)
    if best is None:
        return None
    with open(os.path.join(d, best[1]), "rb") as f:
        data = f.read()
    return (data, "image/png" if best[2] == ".png" else "image/jpeg", best[1]) if looks_like_image(data) else None


def thumb(img, px=COVER_PX):
    """Verkleinern mit sips (macOS) auf hoechstens px, als JPEG. Ohne sips oder bei Fehler: das Bild wie es ist."""
    import subprocess
    import tempfile
    try:
        with tempfile.TemporaryDirectory(prefix="s2l_cover_") as d:
            src, dst = os.path.join(d, "in"), os.path.join(d, "out.jpg")
            with open(src, "wb") as f:
                f.write(img)
            r = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80", "-Z", str(px), src, "--out", dst],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            if r.returncode == 0 and os.path.getsize(dst) > 0:
                with open(dst, "rb") as f:
                    return f.read(), "image/jpeg"
    except (OSError, subprocess.SubprocessError):
        pass
    return img, None


def audio_fp(path):
    """Fingerabdruck der Musik ohne Tags, wie audio_fingerprint am Pi und in der Bruecke (Name der Cover-Sicherung)."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(10)
        start = 0
        if head[:3] == b"ID3" and len(head) == 10:
            start = 10 + _syncsafe(head[6:10])
            if head[5] & 0x10:
                start += 10
        end = size
        if size >= 128:
            f.seek(size - 128)
            if f.read(3) == b"TAG":
                end -= 128
        f.seek(start)
        data = f.read(max(0, min(256 * 1024, end - start)))
    return f"{max(0, end - start)}:{hashlib.sha1(data).hexdigest()[:16]}"


def make_handler(loc, log, trash=to_trash, marks=None, jobs=None, meta=None, server=None):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):      # keine Zeile je Anfrage ins Log
            pass

        def _head(self, code, ctype, length, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Access-Control-Allow-Origin", "*")        # die Seite kommt vom Pi, die Musik vom Mac
            self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()

        def _text(self, code, text):
            body = text.encode("utf-8")
            self._head(code, "text/plain; charset=utf-8", len(body))
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_HEAD(self):
            self._serve(head=True)

        def do_POST(self):
            """Musik-Datenbank, Muellkuebel: {"p": Pfad aus Mixxx, "name": Dateiname zur Bestaetigung} -> Papierkorb des Mac.
            Nur Dateien der Mixxx-Bibliothek, nur mit passendem Dateinamen (kein Loeschen aus Versehen ueber einen Link)."""
            if urlparse(self.path).path == "/convert":
                return self._convert()
            if urlparse(self.path).path == "/export":         # Export der gefilterten Liste in einen Ordner (10.11.2026)
                return self._export_post()
            if urlparse(self.path).path == "/import":         # Import aus dem Wartebereich in den Musikordner (10.11.2026)
                return self._import_post()
            if urlparse(self.path).path == "/lose":           # Lose Album-Lieder (14.11.2026): in den Album-Ordner verschieben, zuruecknehmen
                import album_loose
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)).decode("utf-8")) if n else {}
                    fc_ = getattr(server, "check", None)
                    if fc_ is None:
                        raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    if d.get("op") == "apply" and isinstance(d.get("items"), list):
                        res = album_loose.apply(fc_, d["items"][:3000], log=log)
                        changed = res["moved"]
                    elif d.get("op") == "undo":
                        res = album_loose.undo(fc_, int(d.get("t") or 0), log=log)
                        changed = res["back"]
                    else:
                        raise ValueError("unbekannter Befehl")
                    cb = getattr(server, "on_converted", None)
                    if cb is not None and changed:
                        try:
                            cb(None, None)
                        except Exception:                      # noqa: BLE001
                            pass
                    self._json(200, res)
                except (ValueError, OSError, TypeError) as e:
                    self._json(400, {"error": str(e)})
                return
            if urlparse(self.path).path == "/merge":          # Ordner aufloesen (10.11.2026): verschieben ueber die Mixxx-Warteschlange
                import folder_merge
                import tag_edit
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)).decode("utf-8")) if n else {}
                    fc_ = getattr(server, "check", None)
                    if fc_ is None:
                        raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    if d.get("op") != "apply" or not isinstance(d.get("items"), list):
                        raise ValueError("unbekannter Befehl")
                    grp = str(d.get("group") or "").strip()[:60]
                    res = folder_merge.apply(fc_, str(d.get("src") or ""), d["items"][:3000], group=grp,
                                             write_group=folder_merge.group_writer(tag_edit), log=log)
                    cb = getattr(server, "on_converted", None)
                    if cb is not None and res["moved"]:
                        try:
                            cb(None, None)
                        except Exception:                      # noqa: BLE001
                            pass
                    self._json(200, res)
                except (ValueError, OSError) as e:
                    self._json(400, {"error": str(e)})
                return
            if urlparse(self.path).path == "/fade":           # Fade-in/-out in MP3s (11.11.2026): einzeln oder Sammelauftrag
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)).decode("utf-8")) if n else {}
                    fj = self._fader()
                    if d.get("op") == "stop":
                        self._json(200, fj.stop())
                        return
                    if d.get("op") != "start" or not isinstance(d.get("paths"), list):
                        raise ValueError("unbekannter Befehl")
                    files = []
                    for p in d["paths"][:5000]:
                        f = loc.locate(str(p)) if isinstance(p, str) else None
                        if f and f.lower().endswith(".mp3"):
                            files.append((p, f, 0.0))
                    if not files:
                        raise ValueError("Keine der MP3s ist am Mac erreichbar")
                    res = fj.start(files, d.get("fin"), d.get("fout"), d.get("ca"), d.get("cb"))
                    log(f"Fade: {len(files)} Lieder (in {d.get('fin')} s, aus {d.get('fout')} s, vorne weg {d.get('ca') or 0} s, hinten weg {d.get('cb') or 0} s)")
                    self._json(200, res)
                except (ValueError, OSError) as e:
                    self._json(400, {"error": str(e)})
                return
            if urlparse(self.path).path == "/fnametags":      # Tags aus dem Dateinamen eintragen (10.11.2026)
                import fname_tags
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)).decode("utf-8")) if n else {}
                    fc_ = getattr(server, "check", None)
                    if fc_ is None:
                        raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    if d.get("op") != "apply" or not isinstance(d.get("items"), list):
                        raise ValueError("unbekannter Befehl")
                    cb = getattr(server, "on_tags", None)
                    self._json(200, fname_tags.apply(fc_, d["items"][:2000], on_written=cb, log=log))
                except (ValueError, OSError) as e:
                    self._json(400, {"error": str(e)})
                return
            if urlparse(self.path).path == "/mirror":         # Spiegeln (10.11.2026, Quelle/Ziel frei 12.11.2026): Vorlage, Laufwerke, Ordner, Probelauf, Spiegeln, Anhalten
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 256 * 1024)).decode("utf-8")) if n else {}
                    m, op = self._mirror(), d.get("op")
                    if op == "dest":
                        m.set_dest(str(d.get("dest") or ""))
                        self._json(200, m.status())
                    elif op == "drive":                         # Quelle/Ziel: Laufwerk aus der Auswahlliste
                        self._json(200, m.set_drive(str(d.get("side") or ""), str(d.get("path") or "")))
                    elif op == "folder":                        # Quelle/Ziel: anderer Ordner auf dem Laufwerk
                        self._json(200, m.set_folder(str(d.get("side") or ""), str(d.get("path") or "")))
                    elif op == "sel":                           # welche Ordner gespiegelt werden
                        self._json(200, m.set_sel(list(d.get("names") or [])))
                    elif op == "pair":                          # Vorlage waehlen, anlegen, loeschen
                        self._json(200, m.select(str(d.get("id") or "")))
                    elif op == "pair_add":
                        self._json(200, m.add_pair(str(d.get("name") or "")))
                    elif op == "pair_del":
                        self._json(200, m.del_pair(str(d.get("id") or "")))
                    elif op == "pair_rename":                   # eigene Vorlage umbenennen (13.11.2026)
                        self._json(200, m.rename_pair(str(d.get("id") or ""), str(d.get("name") or "")))
                    elif op in ("plan", "run"):
                        gone = [str(g) for g in d.get("gone") or [] if isinstance(g, str)][:50]
                        m.start(op, gone, confirm_del=bool(d.get("confirm_del")))
                        self._json(200, m.status())
                    elif op == "stop":
                        self._json(200, m.stop())
                    elif op == "conf":                          # Abschaltzeit der NAS, MAC-Adresse fuer Wake-on-LAN
                        self._json(200, m.set_conf(off_at=d.get("off_at") if "off_at" in d else None, mac=d.get("mac") if "mac" in d else None))
                    elif op == "wake":                          # NAS per Wake-on-LAN wecken
                        self._json(200, m.wake())
                    else:
                        raise ValueError("unbekannter Befehl")
                except (ValueError, OSError) as e:
                    self._json(400, {"error": str(e)})
                return
            if urlparse(self.path).path == "/eject":          # Stick auswerfen (10.11.2026); {"vol"}: anderes Laufwerk (12.11.2026)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 4096)).decode("utf-8")) if n else {}
                    vol = str((d if isinstance(d, dict) else {}).get("vol") or "")
                    if vol:
                        import nas_mirror
                        dv = next((x for x in nas_mirror.drives() if x["path"] == nas_mirror.nfc(vol)), None)
                        if dv is None:
                            raise ValueError("Dieses Laufwerk ist nicht (mehr) verbunden")
                        if dv["kind"] == "net":
                            raise ValueError("Netzlaufwerke trennt der Finder (Auswerfen-Symbol neben der Freigabe)")
                        if dv["kind"] != "usb":
                            raise ValueError("Die interne Festplatte lässt sich nicht auswerfen")
                        mst = server.mirror.status() if getattr(server, "mirror", None) is not None else {}
                        if mst.get("state") in ("plan", "run") and any(nas_mirror.inside(p_, vol) for p_ in (mst.get("src") or "", mst.get("dst") or "") if p_):
                            raise ValueError("Das Spiegeln arbeitet gerade mit diesem Laufwerk: zuerst fertig werden lassen oder anhalten")
                    self._json(200, self._ejector().start(loc.root, vol=vol or None))
                except ValueError as e:
                    self._json(400, {"error": str(e)})
                return
            if urlparse(self.path).path == "/tags":
                return self._tags_write()
            if urlparse(self.path).path == "/autotag":
                return self._autotag_post()
            if urlparse(self.path).path == "/genres":         # Genre-Editor: umbenennen, fuellen, zurueck, Hausliste
                return self._genres_post()
            if urlparse(self.path).path == "/cd":             # CD-Assistent: fertigen Plan ausfuehren (Tags, Namen, Ordner)
                import cd_assist
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 512 * 1024)).decode("utf-8")) if n else {}
                    fc_ = getattr(server, "check", None)
                    if fc_ is None:
                        raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    if d.get("op") == "rename_dir":           # Ordner umbenennen/verschieben (09.11.2026), Mixxx-Warteschlange
                        res = cd_assist.rename_dir(fc_, d.get("dir"), d.get("new"))
                        log(f"Ordner umbenannt: {d.get('dir')} -> {res['dir']} ({res['songs']} Lieder)")
                        self._json(200, res)
                        return
                    res = cd_assist.apply(fc_, d.get("plan") or {}, log=log)
                    cb = getattr(server, "on_tags", None)
                    if cb is not None:
                        for x in res["done"]:
                            try:
                                cb(x["new_path"], {})
                            except Exception:                    # noqa: BLE001
                                pass
                except (ValueError, OSError, StopIteration) as e:
                    self._json(400, {"error": str(e)})
                    return
                self._json(200, res)
                return
            if urlparse(self.path).path == "/check":          # Dateien pruefen: scan, trash (Liste), trash_all (Datenmuell), rename
                fc = getattr(server, "check", None)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 2 * 1024 * 1024)).decode("utf-8")) if n else {}
                    if fc is None:
                        raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    op = d.get("op")
                    if op == "scan":
                        res = {"started": fc.scan()}
                    elif op == "trash" and isinstance(d.get("items"), list):
                        res = fc.trash_files([str(x) for x in d["items"][:500]])
                    elif op == "trash_dirs" and isinstance(d.get("items"), list):   # leere Ordner (09.11.2026)
                        res = fc.trash_dirs([str(x) for x in d["items"][:500]])
                    elif op == "clear_short":                # kurze Stuecke: BPM und Tonart weg (09.11.2026)
                        res = fc.clear_short([str(x) for x in d["items"][:3000]] if isinstance(d.get("items"), list) else None)
                    elif op == "trash_all":
                        res = {"started": fc.trash_all_junk()}
                    elif op == "rename":
                        res = fc.rename(str(d.get("p") or ""), str(d.get("to") or ""))
                    elif op == "retag":                      # Tags im Tag-Editor geaendert: Vorschlag neu rechnen
                        res = fc.retag(str(d.get("p") or ""))
                    elif op == "keep":                       # Dateiname so lassen (kommt nicht wieder)
                        res = fc.keep(str(d.get("p") or ""))
                    elif op == "rename_file":                # Gleiche Namen: eine Datei umbenennen
                        res = fc.rename_file(str(d.get("f") or ""), str(d.get("to") or ""))
                    elif op == "jnames_preview":             # eigene Muell-Namen: Vorschau (09.11.2026)
                        res = fc.junk_preview([str(x) for x in (d.get("names") or [])][:200])
                    elif op == "jnames_set":                 # eigene Muell-Namen speichern, neu pruefen
                        res = fc.junk_names_set([str(x) for x in (d.get("names") or [])][:200])
                    elif op == "unkeep":                     # doch nicht so lassen (Reiter So gelassen)
                        res = fc.unkeep(str(d.get("p") or ""))
                    else:
                        raise ValueError("unbekannter Befehl")
                except (ValueError, AttributeError, OSError) as e:
                    self._json(400, {"error": str(e)})
                    return
                self._json(200, res)
                return
            if urlparse(self.path).path == "/energie":        # Datenpflege: geschaetzte Energie in leere Tags (09.11.2026)
                fn = getattr(server, "energy_fill", None)
                self._json(200, fn() if fn is not None else {"started": False, "error": "Am Mac noch nicht eingerichtet"})
                return
            if urlparse(self.path).path == "/changed":        # geaenderte Tags -> Playlist fuer Mixxx: {"op": "m3u"} / {"op": "clear", "before": t}
                import changed_log
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 8192)).decode("utf-8")) if n else {}
                    if d.get("op") == "m3u":
                        f, cnt, t = changed_log.write_m3u(M3U_DIR)
                        self._json(200, {"ok": True, "file": f, "n": cnt, "t": t})
                    elif d.get("op") == "reset":
                        changed_log.reset()
                        self._json(200, {"ok": True, "n": 0})
                    elif d.get("op") == "clear":
                        b = d.get("before")
                        self._json(200, {"ok": True, "left": changed_log.clear(float(b) if isinstance(b, (int, float)) else None)})
                    else:
                        raise ValueError("unbekannter Befehl")
                except (ValueError, AttributeError, OSError) as e:
                    self._json(400, {"error": str(e)})
                return
            if urlparse(self.path).path == "/m3u":            # Auto-DJ: Playlist fuer Mixxx als M3U8-Datei am Mac
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 2 * 1024 * 1024)).decode("utf-8")) if n else {}
                    if not isinstance(d.get("items"), list):
                        raise ValueError("keine Lieder")
                    f, cnt, missing = write_m3u(d.get("name"), d["items"], loc.locate)
                except (ValueError, AttributeError, OSError) as e:
                    self._json(400, {"error": str(e)})
                    return
                log(f"Auto-DJ: Playlist fuer Mixxx geschrieben: {f} ({cnt} Lieder)")
                self._json(200, {"ok": True, "file": f, "n": cnt, "missing": len(missing)})
                return
            if urlparse(self.path).path == "/folderart":     # Ordnerbilder: {"op": "scan"} oder {"op": "write", "paths": [...]}
                fa = getattr(server, "folderart", None)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)).decode("utf-8")) if n else {}
                    if fa is None or d.get("op") not in ("scan", "write"):
                        raise ValueError("unbekannter Befehl")
                    paths = d.get("paths") if isinstance(d.get("paths"), list) else None
                    ok = fa.scan() if d["op"] == "scan" else fa.write([str(x) for x in paths] if paths else None)
                except (ValueError, AttributeError) as e:
                    self._json(400, {"error": str(e)})
                    return
                self._json(200, dict(fa.status(), started=bool(ok)))
                return
            if urlparse(self.path).path == "/defekt":        # Beschaedigte Dateien: {"op": "repair", "paths": [...]} | {"op": "trash", "path"}
                dm = getattr(server, "damaged", None)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)).decode("utf-8")) if n else {}
                    if dm is None:
                        raise ValueError("Am Musik-Rechner noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    if d.get("op") == "repair" and isinstance(d.get("paths"), list):
                        res = dm.repair([str(x) for x in d["paths"]])
                    elif d.get("op") == "trash" and isinstance(d.get("path"), str):
                        res = dm.trash_file(d["path"])
                        loc.paths.discard(d["path"])
                    else:
                        raise ValueError("unbekannter Befehl")
                except (ValueError, OSError) as e:
                    self._json(400, {"error": str(e)})
                    return
                self._json(200, res)
                return
            if urlparse(self.path).path == "/dupes":         # Seite Doppelte: Gruppe "alle behalten"
                du = getattr(server, "dupes", None)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    d = json.loads(self.rfile.read(min(n, 65536)).decode("utf-8")) if n else {}
                    if du is None or d.get("op") != "keep" or not isinstance(d.get("paths"), list):
                        raise ValueError("unbekannter Befehl")
                    du.keep_all(d["paths"])
                except (ValueError, AttributeError, OSError) as e:
                    self._json(400, {"error": str(e)})
                    return
                self._json(200, {"ok": True})
                return
            if urlparse(self.path).path != "/trash":
                self._text(404, "nicht gefunden")
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(min(n, 8192)).decode("utf-8")) if n else {}
                p, name = str(d.get("p") or ""), str(d.get("name") or "")
            except (ValueError, AttributeError):
                self._json(400, {"error": "Anfrage unlesbar"})
                return
            f = loc.locate(p)
            if f is None:
                self._json(404, {"error": "Datei nicht in der Mixxx-Bibliothek oder nicht erreichbar (Stick eingesteckt?)"})
                return
            if not name or name != os.path.basename(p) or name != os.path.basename(f):
                self._json(400, {"error": "Dateiname passt nicht"})
                return
            try:
                trash(f)
            except (OSError, subprocess.SubprocessError) as e:
                self._json(500, {"error": "Papierkorb: %s" % e})
                return
            loc.paths.discard(p)
            du = getattr(server, "dupes", None)
            if du is not None:
                du.forget(p)                                     # Seite Doppelte: gleich ohne diese Datei
            log(f"Vorhoeren: in den Papierkorb gelegt: {f}")
            self._json(200, {"ok": True, "file": f})

        def _fader(self):
            if getattr(server, "fader", None) is None:
                import audio_fade
                cb = getattr(server, "on_converted", None)       # neue Datei: Ordner-Liste bald neu einlesen
                server.fader = audio_fade.Jobs(log=log, done=(lambda p, f: cb(None, None)) if cb else None)
            return server.fader

        def _mirror(self):
            if getattr(server, "mirror", None) is None:
                import nas_mirror
                def done():                                     # auf den Stick gespiegelt: Ordner-Liste neu einlesen
                    cb = getattr(server, "on_converted", None)
                    if cb is not None:
                        cb("", "")
                server.mirror = nas_mirror.Mirror(lambda: loc.root, log=log, on_done=done)
            return server.mirror

        def _ejector(self):
            if getattr(server, "ejector", None) is None:
                import stick_hold
                server.ejector = stick_hold.Eject(log=log)
            return server.ejector

        def _import_post(self):
            """{"op": "apply", "items": [{path, do: move|replace|trash, target, dup}]} -> verschieben, ersetzen, wegwerfen."""
            import import_assist
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)).decode("utf-8")) if n else {}
                if d.get("op") in ("klang", "klang_stop"):    # Klang pruefen (Chromaprint, 11.11.2026): gleiche Musik unter anderem Namen
                    import klang_fp
                    if getattr(server, "klang", None) is None:
                        server.klang = klang_fp.Checker(log=log)
                    if d["op"] == "klang_stop":
                        self._json(200, server.klang.stop())
                    else:
                        self._json(200, server.klang.start(loc.root, getattr(server, "lib_songs", None), loc.locate))
                    return
                if d.get("op") in ("other_convert", "other_trash"):   # Ordner "nicht MP3": umwandeln / Original weg (12.11.2026)
                    jb = import_assist.other_jobs(lambda: loc.root, log)
                    names = [str(x) for x in (d.get("names") or [])][:200]
                    if d["op"] == "other_convert":
                        self._json(200, {"started": import_assist.other_convert(loc.root, names, jb)})
                    else:
                        paths = [import_assist.other_path(loc.root, n) for n in names]
                        bad = import_assist.fc.to_trash_many(paths) if paths else 0
                        self._json(200, {"trashed": 0 if bad else len(paths), "error": "Papierkorb ging nicht" if bad else ""})
                    return
                if d.get("op") == "sort":                     # lose Dateien in die Kategorien einsortieren (Knopf, 10.11.2026)
                    self._json(200, import_assist.sort_loose(loc.root, getattr(server, "lib_songs", None), log=log))
                    return
                if d.get("op") != "apply" or not isinstance(d.get("items"), list):
                    raise ValueError("unbekannter Befehl")
                res = import_assist.apply(loc.root, d["items"][:import_assist.MAX_SONGS], locate=loc.locate, log=log)
                try:                                           # geschriebene Tags im Wartebereich: Mixxx liest die Dateien ohnehin neu
                    import changed_log
                    changed_log.forget_under(import_assist.import_dir(loc.root))
                except (ImportError, AttributeError, OSError):
                    pass
                cb = getattr(server, "on_converted", None)     # neue Dateien im Musikordner: Ordner-Liste gleich neu einlesen
                if cb is not None and res["moved"]:
                    try:
                        cb(None, None)
                    except Exception:                          # noqa: BLE001
                        pass
                self._json(200, res)
            except ValueError as e:
                self._json(400, {"error": str(e)})

        def _exporter(self):
            if getattr(server, "exporter", None) is None:
                import export_files
                server.exporter = export_files.Exporter(log=log)
            return server.exporter

        def _export_post(self):
            """{"op": "start", "dest": Ordner, "paths": [Pfade der Bibliothek]} | {"op": "stop"} | {"op": "mkdir", "parent", "name"}.
            Nur Dateien der Bibliothek (loc.locate), kopiert wird nur, nie verschoben (export_files)."""
            import export_files
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(min(n, 8 * 1024 * 1024)).decode("utf-8")) if n else {}
                op = d.get("op")
                if server is None:
                    raise ValueError("Export hier nicht moeglich")
                if op == "mkdir":
                    self._json(200, {"path": export_files.mkdir(d.get("parent"), d.get("name"))})
                    return
                if op == "stop":
                    self._json(200, self._exporter().stop())
                    return
                if op != "start":
                    raise ValueError("unbekannter Befehl")
                dest = export_files.check_dest(d.get("dest"), loc.root)
                paths = d.get("paths")
                if not isinstance(paths, list) or not paths:
                    raise ValueError("Keine Lieder ausgewaehlt")
                files, miss, seen = [], 0, set()
                for p in paths[:export_files.MAX_FILES]:
                    f = loc.locate(str(p)) if isinstance(p, str) else None
                    if f is None:
                        miss += 1
                    elif f not in seen:
                        seen.add(f)
                        files.append((p, f))
                if not files:
                    raise ValueError("Keine der Dateien ist am Mac erreichbar (Stick eingesteckt?)")
                res = self._exporter().start(dest, files, missing=miss)
                log(f"Export: {len(files)} Lieder nach {dest}")
                self._json(200, res)
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except OSError as e:
                self._json(400, {"error": f"Ordner: {e.strerror or e}"})

        def _convert(self):
            """Musik-Datenbank, Knopf "→ MP3": {"p": Pfad, "name": Dateiname zur Bestaetigung} -> Umwandlung im Hintergrund
            (convert_mp3.Jobs). Nur Dateien der Bibliothek, nur Arten, die umgewandelt werden, nie ueber eine vorhandene MP3."""
            import convert_mp3 as cm
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(min(n, 8192)).decode("utf-8")) if n else {}
                p, name = str(d.get("p") or ""), str(d.get("name") or "")
            except (ValueError, AttributeError):
                self._json(400, {"error": "Anfrage unlesbar"})
                return
            if jobs is None:
                self._json(503, {"error": "Umwandeln hier nicht moeglich"})
                return
            f = loc.locate(p)
            if f is None:
                self._json(404, {"error": "Datei nicht in der Bibliothek oder nicht erreichbar (Stick eingesteckt?)"})
                return
            if not name or name != os.path.basename(p) or name != os.path.basename(f):
                self._json(400, {"error": "Dateiname passt nicht"})
                return
            if not cm.can_convert(f):
                self._json(400, {"error": "diese Dateiart wird nicht umgewandelt"})
                return
            if not cm.find_ffmpeg():
                self._json(503, {"error": "ffmpeg fehlt am Mac (Terminal: brew install ffmpeg)"})
                return
            if os.path.exists(cm.target_for(f)) and jobs.status(p).get("state") != "ok":
                self._json(409, {"error": "die MP3 gibt es schon: " + os.path.basename(cm.target_for(f))})
                return
            try:
                getm = getattr(server, "meta", None) or meta   # erst beim Klick nachsehen: die Bruecke setzt meta nach dem Start (Fehler 07.11.2026)
                tags = getm(p) if getm is not None else None   # BPM, Tonart, Kommentar ... aus Mixxx in die neue MP3
            except Exception:                                    # noqa: BLE001
                tags = None
            self._json(202, jobs.start(p, f, tags))

        def _mp3_of(self, p):
            """Datei am Mac zu einem Pfad der Bibliothek, nur MP3; sonst (None, Fehlertext, Code)."""
            f = loc.locate(p)
            if f is None:
                return None, "Datei nicht in der Bibliothek oder nicht erreichbar (Stick eingesteckt?)", 404
            if not f.lower().endswith(".mp3"):
                return None, "Tags bearbeiten geht nur bei MP3", 400
            return f, "", 200

        def _tags_write(self):
            """Fenster Tag bearbeiten: {"p", "name", "fields": {...}, "cover_url" | "remove_cover"} -> in die MP3 schreiben."""
            import tag_edit as te
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(min(n, 8 * 1024 * 1024)).decode("utf-8")) if n else {}
                p, name = str(d.get("p") or ""), str(d.get("name") or "")
                fields = d.get("fields") or {}
                if not isinstance(fields, dict):
                    raise ValueError
            except (ValueError, AttributeError):
                self._json(400, {"error": "Anfrage unlesbar"})
                return
            f, err, code = self._mp3_of(p)
            if f is None:
                self._json(code, {"error": err})
                return
            if not name or name != os.path.basename(p) or name != os.path.basename(f):
                self._json(400, {"error": "Dateiname passt nicht"})
                return
            try:
                cover = te.fetch_cover(str(d["cover_url"])) if d.get("cover_url") else None
                if d.get("cover_data"):                              # im Browser erzeugtes Cover (JPEG, base64)
                    import base64
                    raw = str(d["cover_data"])
                    if len(raw) > te.COVER_MAX * 4 // 3 + 8:
                        raise te.TagError("Cover zu gross")
                    try:
                        cover = base64.b64decode(raw, validate=True)
                    except ValueError:
                        raise te.TagError("Cover unlesbar") from None
                    fields = dict(fields, coversrc=te.COVER_OWN if d.get("cover_src") == "datei" else te.COVER_MADE)   # vermerkt: erzeugt oder eigenes Bild
                res = te.write_tags(f, fields, cover=cover, remove_cover=bool(d.get("remove_cover")),
                                    fav=None if d.get("fav") is None else bool(d.get("fav")))   # Herz als Bewertung (Einstellung fav_mp3)
            except te.TagError as e:
                self._json(400, {"error": str(e)})
                return
            except OSError as e:
                self._json(500, {"error": f"Schreiben ging nicht: {e}"})
                return
            log(f"Tags geschrieben: {f}")
            cb = getattr(server, "on_tags", None)
            if cb is not None:
                try:
                    cb(p, fields)
                except Exception as e:                              # noqa: BLE001  Merken darf das Schreiben nie stoeren
                    log(f"Tags merken: {e}")
            self._json(200, dict(res, ok=True))

        def _genres_post(self):
            """Genre-Editor (Wunsch 08.11.2026): {"op": rename|assign|undo|house|house_suggest|never|net_start|net_stop, ...}."""
            ge = getattr(server, "genres", None)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(min(n, 4 * 1024 * 1024)).decode("utf-8")) if n else {}
                if ge is None:
                    raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                op, samples = d.get("op"), bool(d.get("samples"))
                if op == "rename" and isinstance(d.get("from"), list):
                    res = ge.rename([str(x) for x in d["from"][:200]], str(d.get("to") or ""))
                elif op == "assign" and isinstance(d.get("pairs"), list):
                    res = ge.assign([(str(p), str(g)) for p, g in d["pairs"][:5000] if isinstance(p, str)])
                elif op == "artist" and isinstance(d.get("paths"), list):   # Seite Interpreten: Interpret aendern oder leeren
                    res = ge.set_artist([str(x) for x in d["paths"][:5000]], str(d.get("old") or ""), str(d.get("to") or ""))
                elif op == "album" and isinstance(d.get("paths"), list):    # Seite Alben: Albumname in allen MP3s (Bleistift, 14.11.2026)
                    res = ge.set_album([str(x) for x in d["paths"][:5000]], str(d.get("to") or ""))
                elif op == "group" and isinstance(d.get("pairs"), list):    # Gruppen-Manager: neue Gruppe(n) je Lied
                    res = ge.set_grouping([(str(p), str(g)) for p, g in d["pairs"][:5000] if isinstance(p, str)], str(d.get("label") or ""))
                elif op == "undo":
                    res = ge.undo(str(d.get("id") or ""))
                elif op == "house" and isinstance(d.get("genres"), list):
                    res = ge.set_house([str(x) for x in d["genres"]])
                elif op == "house_suggest":
                    res = {"house": ge.house_from_counts()}
                elif op == "never":
                    res = ge.set_never(str(d.get("g") or ""), bool(d.get("on", True)))
                elif op == "net_start":
                    res = ge.net_start(samples)
                elif op == "net_stop":
                    res = ge.net_stop()
                else:
                    raise ValueError("unbekannter Befehl")
            except (ValueError, TypeError, AttributeError, OSError) as e:
                self._json(400, {"error": str(e)})
                return
            self._json(200, res)

        def _autotag_post(self):
            """Seite Vorschlaege: {"op": start|stop|reject|done|apply, "path", "fields": [...] oder null, "cover": true}."""
            at = getattr(server, "autotag", None)
            if at is None:
                self._json(503, {"error": "Auto-Tagger hier nicht verfuegbar"})
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(min(n, 512 * 1024)).decode("utf-8")) if n else {}
                op, p = str(d.get("op") or ""), str(d.get("path") or "")
            except (ValueError, AttributeError):
                self._json(400, {"error": "Anfrage unlesbar"})
                return
            try:
                if op == "start":
                    at.start()
                elif op == "stop":
                    at.stop()
                elif op == "auto":                            # Schalter "Gute automatisch uebernehmen"
                    at.set_auto(d.get("on") is True)
                elif op == "research":                        # Musik-DB "Titel = Interpret": diese Lieder gezielt recherchieren
                    paths = d.get("paths") if isinstance(d.get("paths"), list) else []
                    self._json(200, {"queued": at.research_paths([str(x) for x in paths[:500]])})
                    return
                elif op == "reject":
                    at.reject(p)
                elif op == "unreject":                        # Reiter "Abgelehnt": wieder anbieten
                    at.unreject(p)
                elif op == "done":
                    at.mark_done(p)
                elif op == "apply":
                    f, err, code = self._mp3_of(p)
                    if f is None:
                        self._json(code, {"error": err})
                        return
                    fields = d.get("fields")
                    sel = [str(x) for x in fields] if isinstance(fields, list) else None
                    at.apply(p, f, fields=sel, cover=d.get("cover", True) is not False)
                    log(f"Auto-Tagger: Vorschlag uebernommen: {f}")
                    cb = getattr(server, "on_tags", None)             # Liste am Pi gleich mit den neuen Angaben (wie Tag-Editor)
                    if cb is not None:
                        try:
                            new = dict((at.items.get(p) or {}).get("new") or {})
                            cb(p, {k: v for k, v in new.items() if sel is None or k in sel})
                        except Exception as e:                      # noqa: BLE001  Merken darf das Schreiben nie stoeren
                            log(f"Tags merken: {e}")
                else:
                    self._json(400, {"error": "unbekannter Befehl"})
                    return
            except (KeyError, ValueError) as e:
                self._json(400, {"error": str(e).strip("'")})
                return
            except Exception as e:                               # noqa: BLE001  Cover nicht mehr da, Datei gesperrt ...
                self._json(500, {"error": str(e)[:200]})
                return
            self._json(200, {"ok": True, "status": at.status()})

        def _json(self, code, d):
            body = json.dumps(d, ensure_ascii=False).encode("utf-8")
            self._head(code, "application/json; charset=utf-8", len(body))
            self.wfile.write(body)

        def do_GET(self):
            self._serve(head=False)

        def _serve(self, head):
            u = urlparse(self.path)
            if u.path == "/ping":
                body = json.dumps({"ok": True, "n": len(loc.paths)}).encode()
                self._head(200, "application/json", len(body))
                if not head:
                    self.wfile.write(body)
                return
            if u.path == "/cover":                     # Cover eines Liedes der Bibliothek, verkleinert (Panel, Musik-Datenbank)
                f = loc.locate((parse_qs(u.query).get("p") or [""])[0])
                if not f:                              # Datei (noch) nicht bekannt, etwa gleich nach dem Umbenennen: nicht "kein Cover"
                    self._json(410, {"error": "Datei nicht gefunden"})   # (Fehlerbericht 09.11.2026: sonst merkt der Pi das 6 h)
                    return
                c = find_cover(f)
                if c is None:
                    self._json(404, {"error": "kein Cover"})
                    return
                img, mime = thumb(c[0])
                try:
                    fp = audio_fp(f)
                except OSError:
                    fp = ""
                self._head(200, mime or c[1], len(img), {"X-FP": fp, "Access-Control-Expose-Headers": "X-FP"})
                if not head:
                    self.wfile.write(img)
                return
            if u.path == "/status":                     # Musik-Datenbank: was der Mac gerade tut (Tags lesen, Liste schicken)
                fn = getattr(server, "status_info", None)
                try:
                    st = dict(fn()) if fn is not None else {"off": True}
                    root = loc.root or ""                      # Musikordner erreichbar? (Stick abgezogen, Wunsch 12.11.2026)
                    st["root"], st["root_ok"] = root, bool(root) and os.path.isdir(root)
                    self._json(200, st)
                except Exception as e:                      # noqa: BLE001
                    self._json(500, {"error": str(e)})
                return
            if u.path == "/sync":                       # Musik-Datenbank: passt Mixxx noch zum Stick?
                fn = getattr(server, "sync_info", None)
                try:
                    self._json(200, fn() if fn is not None else {"gone": 0, "new": 0, "off": True})
                except Exception as e:                      # noqa: BLE001
                    self._json(500, {"error": str(e)[:200]})
                return
            if u.path == "/mixxxsicherung":             # Datenpflege: wann die Mixxx-App die Mixxx-Datenbank zuletzt gesichert hat
                self._json(200, dict(mixxx_backups(), stick=stick_backup(loc.root), ueb=transfer_info()))   # dazu die Sicherung des Sticks (nas-sync)
                return
            if u.path == "/genres":                     # Genre-Editor: Ueberblick, Lieder eines Genres oder Genre fuellen
                ge = getattr(server, "genres", None)
                q = parse_qs(u.query)
                if ge is None:
                    self._json(200, {"state": "off"})
                elif "house" in q:                       # nur die Hausliste (Tag-Fenster: Auswahl beim Genre, 11.11.2026)
                    self._json(200, {"house": list(ge.conf.get("house") or [])})
                elif "g" in q:
                    self._json(200, ge.songs_of(q["g"][0]))
                elif "fill" in q:
                    self._json(200, ge.fill_status(q.get("samples", ["0"])[0] == "1"))
                elif "job" in q:                         # nur der Stand des Schreibens (Seite Interpreten)
                    fld = (q.get("field") or ["artist"])[0]
                    hs = [h for h in ge.history() if h.get("field") == fld][:10]
                    ops = [{k: h[k] for k in ("id", "t", "label", "n", "undone")} for h in hs]
                    self._json(200, {"job": ge.job_status(), "artist_ops": ops, "ops": ops})
                else:
                    self._json(200, ge.overview())
                return
            if u.path == "/cd":                         # CD-Assistent: Ordner zur Auswahl oder Lieder eines Ordners (09.11.2026)
                import cd_assist
                fc_ = getattr(server, "check", None)
                q = parse_qs(u.query)
                if fc_ is None:
                    self._json(200, {"state": "off"})
                elif "d" in q:
                    self._json(200, cd_assist.folder(fc_, q["d"][0], (q.get("album") or [None])[0]))
                else:
                    self._json(200, cd_assist.dirs(fc_))
                return
            if u.path == "/lose":                       # Lose Album-Lieder: Liste und Protokoll
                import album_loose
                fc_ = getattr(server, "check", None)
                try:
                    if fc_ is None:
                        raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    if parse_qs(u.query).get("count"):
                        self._json(200, album_loose.count(fc_))
                    else:
                        self._json(200, dict(album_loose.scan(fc_), history=album_loose.history()))
                except (ValueError, OSError) as e:
                    self._json(400, {"error": str(e)})
                return
            if u.path == "/merge":                      # Ordner aufloesen: Lieder der Quelle mit Vorschlag im Ziel
                import folder_merge
                q = parse_qs(u.query)
                fc_ = getattr(server, "check", None)
                try:
                    if fc_ is None:
                        raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    self._json(200, folder_merge.scan(fc_, (q.get("src") or [""])[0][:120], (q.get("dst") or [""])[0][:120]))
                except ValueError as e:
                    self._json(400, {"error": str(e)})
                return
            if u.path == "/fade":                       # Stand des Fade-Auftrags
                self._json(200, self._fader().status() if server is not None else {"state": "off"})
                return
            if u.path == "/fnametags":                  # Tags aus dem Dateinamen: Ordner, Muster, Vorschau
                import fname_tags
                q = parse_qs(u.query)
                fc_ = getattr(server, "check", None)
                try:
                    if fc_ is None:
                        raise ValueError("Am Mac noch nicht eingerichtet (Helfer oder Mixxx-App neu installieren)")
                    dd = (q.get("dir") or [""])[0][:300]
                    if not dd:
                        self._json(200, {"dirs": fname_tags.dirs(fc_), "patterns": fname_tags.PATTERNS})
                    else:
                        self._json(200, fname_tags.scan(fc_, dd, (q.get("pat") or ["a-t"])[0], overwrite=(q.get("ow") or [""])[0] == "1"))
                except (ValueError, OSError) as e:
                    self._json(400, {"error": str(e)})
                return
            if u.path == "/mirror":                     # Stand des Spiegelns auf die NAS
                self._json(200, self._mirror().status() if server is not None else {"state": "off"})
                return
            if u.path == "/eject":                      # Stand des Auswerfens (Panel fragt nach)
                import stick_hold
                st = self._ejector().status() if server is not None else {"state": "idle", "held": stick_hold.held()}
                st["vol"] = st.get("vol") or stick_hold.volume_of(loc.root)
                st["mounted"] = bool(st["vol"]) and os.path.isdir(st["vol"])
                self._json(200, st)
                return
            if u.path == "/import":                     # Import-Seite: Wartebereich mit Tags, Vorschlag und vorhandenem Gegenstueck
                import import_assist
                try:
                    if (parse_qs(u.query).get("klang") or [""])[0]:   # Stand der Klang-Pruefung
                        import klang_fp
                        kc = getattr(server, "klang", None)
                        self._json(200, dict(kc.status() if kc is not None else {"state": "idle"}, fpcalc=bool(klang_fp.find_fpcalc())))
                        return
                    if (parse_qs(u.query).get("other") or [""])[0]:   # Ordner "nicht MP3" mit Stand der Umwandlung
                        self._json(200, {"files": import_assist.other_files(loc.root, import_assist.other_jobs(lambda: loc.root, log))})
                        return
                    if (parse_qs(u.query).get("count") or [""])[0]:   # Datenpflege: nur zaehlen (billig)
                        self._json(200, {"n": import_assist.count(loc.root)})
                        return
                    top = (parse_qs(u.query).get("top") or ["U-MUSIK"])[0][:60]
                    songs = getattr(server, "lib_songs", None)
                    self._json(200, import_assist.scan(loc.root, songs, top))
                except (OSError, ValueError) as e:
                    self._json(400, {"error": str(e)})
                return
            if u.path == "/dirs":                       # Export: verbundene Laufwerke und Ordner zum Auswaehlen
                import export_files
                try:
                    self._json(200, export_files.dirs((parse_qs(u.query).get("p") or [""])[0], loc.root))
                except ValueError as e:
                    self._json(400, {"error": str(e)})
                return
            if u.path == "/export":                     # Stand des Exports
                ex = getattr(server, "exporter", None)
                self._json(200, ex.status() if ex is not None else {"state": "idle"})
                return
            if u.path == "/excl":                       # ausgeschlossene Ordner (Einstellungen): je Ordner gefunden und Zahl MP3s
                import music_excl
                root = loc.root
                info = getattr(server, "excl_info", None)
                self._json(200, {"root": root, "excl": music_excl.get(), "rows": music_excl.status(root),
                                 "lib_out": info() if info is not None else None})
                return
            if u.path == "/check":                      # Dateien pruefen: Stand und Listen
                fc = getattr(server, "check", None)
                self._json(200, fc.status() if fc is not None else {"state": "off"})
                return
            if u.path == "/energie":                    # Datenpflege: wie viele MP3s ab 30 s noch keine Energie im Tag haben
                fn = getattr(server, "energy_info", None)
                self._json(200, fn() if fn is not None else {"an": False})
                return
            if u.path == "/changed":                    # wie viele MP3s der Light-Butler seit dem letzten Leeren geaendert hat
                import changed_log
                self._json(200, changed_log.status())
                return
            if u.path == "/folderart":                  # Ordnerbilder: Stand der Suche bzw. des Schreibens
                fa = getattr(server, "folderart", None)
                self._json(200, fa.status() if fa is not None else {"state": "off"})
                return
            if u.path == "/defekt":                     # Beschaedigte Dateien (Datenpflege, 14.11.2026): Stand und Liste
                dm = getattr(server, "damaged", None)
                g = dm.get() if dm is not None else {"state": "off", "items": [], "n": 0, "progress": [0, 0]}
                self._json(200, {"n": g["n"], "state": g["state"]} if (parse_qs(u.query).get("count") or [""])[0] == "1" else g)
                return
            if u.path == "/dupes":                      # Seite Doppelte: Gruppen mit Angaben je Datei (rechnet im Hintergrund)
                du = getattr(server, "dupes", None)
                fresh = (parse_qs(u.query).get("neu") or [""])[0] == "1"
                self._json(200, du.get(fresh) if du is not None else {"state": "off", "groups": []})
                return
            if u.path == "/autotag":                    # Seite Vorschlaege: Stand und offene Vorschlaege des Auto-Taggers
                at = getattr(server, "autotag", None)
                if at is not None:
                    at.prune_soon()                          # inzwischen anderswo mit Cover versehen: faellt heraus
                self._json(200, {"status": at.status(), "items": at.list(rej=True)} if at is not None else {"status": None, "items": []})
                return
            if u.path in ("/tags", "/lookup"):            # Tag bearbeiten: lesen, Vorschlaege aus dem Internet (nur auf Knopfdruck)
                import tag_edit as te
                qs = parse_qs(u.query)
                p = (qs.get("p") or [""])[0]
                f, err, code = self._mp3_of(p)
                if f is None:
                    self._json(code, {"error": err})
                    return
                try:
                    if u.path == "/tags":
                        self._json(200, dict(te.read_tags(f), file=os.path.basename(f)))
                    else:
                        a, t = (qs.get("artist") or [""])[0][:200], (qs.get("title") or [""])[0][:200]
                        try:
                            dur = float((qs.get("dur") or ["0"])[0])
                        except ValueError:
                            dur = 0.0
                        self._json(200, te.lookup(a, t, dur))
                except te.TagError as e:
                    self._json(400, {"error": str(e)})
                except OSError as e:
                    self._json(500, {"error": f"Lesen ging nicht: {e}"})
                return
            if u.path == "/convert":                   # Stand einer Umwandlung (Musik-Datenbank fragt nach)
                p = (parse_qs(u.query).get("p") or [""])[0]
                self._json(200, jobs.status(p) if (jobs is not None and loc.allowed(p)) else {"state": ""})
                return
            if u.path == "/marks":                     # Abschnitte, Hotcues, Drops eines Liedes der Bibliothek (Quick im Panel)
                qq = parse_qs(u.query)
                p = (qq.get("p") or [""])[0]
                try:
                    if marks is None or not loc.allowed(p):
                        m = None
                    elif "nofp" in qq:                     # Vorhoeren am Pi: ohne Fingerabdruck, schnell (14.11.2026)
                        m = marks(p, False)
                    else:
                        m = marks(p)
                except (OSError, ValueError, KeyError) as e:
                    log(f"Vorhoeren: Analyse zu {p} nicht lesbar: {e}")
                    m = None
                if m is None:
                    self._json(404, {"error": "keine Analyse zu diesem Lied"})
                else:
                    self._json(200, m)
                return
            if u.path != "/audio":
                self._text(404, "nicht gefunden")
                return
            p = (parse_qs(u.query).get("p") or [""])[0]
            f = loc.locate(p)
            if f is None:
                self._text(404, "Datei nicht in der Mixxx-Bibliothek oder nicht erreichbar (Stick eingesteckt?)")
                return
            size = os.path.getsize(f)
            rng = self.headers.get("Range")
            r = parse_range(rng, size) if rng else (0, size - 1)
            if r is None:
                self._head(416, "text/plain", 0, {"Content-Range": f"bytes */{size}"})
                return
            a, b = r
            ctype = "audio/mpeg" if f.lower().endswith(".mp3") else "application/octet-stream"
            extra = {"Content-Range": f"bytes {a}-{b}/{size}"} if rng else {"Content-Disposition": disposition(os.path.basename(f))}
            self._head(206 if rng else 200, ctype, b - a + 1, extra)
            if head:
                return
            try:
                with open(f, "rb") as fh:
                    fh.seek(a)
                    left = b - a + 1
                    while left > 0:
                        chunk = fh.read(min(CHUNK, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (OSError, BrokenPipeError, ConnectionResetError):
                self.close_connection = True
    return H


class MusicServer:
    """Startet den Webserver in einem eigenen Thread. port=0 waehlt einen freien Port (Tests)."""

    SYNC_S = 30.0

    def __init__(self, paths, port=PORT, root="", path_map=(), log=None, trash=to_trash, marks=None):
        self.loc, self.trash, self.marks = Locator(paths, root, path_map), trash, marks
        self.on_converted = None                                # Bruecke: Musikordner neu einlesen, wenn eine MP3 dazukam
        self.meta = None                                        # Bruecke: Angaben aus Mixxx zu einem Pfad (Umwandeln nach MP3)
        self.autotag = None                                     # Auto-Tagger (auto_tag.AutoTagger), von der Bruecke gesetzt
        self.dupes = None                                       # Doppelte (dupes.Dupes), von der Bruecke gesetzt
        self.damaged = None                                     # Beschaedigte Dateien (damaged.Damaged), von der Bruecke gesetzt
        self.check = None                                       # Dateien pruefen (file_check.FileCheck), von der Bruecke gesetzt
        self.genres = None                                      # Genre-Editor (genre_edit.GenreEditor), von der Bruecke gesetzt
        try:                                                    # Ordnerbilder in MP3s ohne eigenes Bild schreiben (08.11.2026)
            import folder_art
            import tag_edit
            self.folderart = folder_art.FolderArt(lambda: list(self.loc.paths), self.loc.locate, folder_image, looks_like_image,
                                                  thumb, lambda f, data: tag_edit.write_tags(f, cover=data), log=log)
        except ImportError:
            self.folderart = None
        self.on_tags = None                                     # Bruecke: geschriebene Tags merken (Forwarder.tags_written)
        self.status_info = None                                 # Statusanzeige (Forwarder.status), von der Bruecke gesetzt
        self.sync_info = None                                   # Abgleich Mixxx und Stick (Forwarder.sync_info), von der Bruecke gesetzt
        try:
            from convert_mp3 import Jobs
            self.jobs = Jobs(log=log, done=lambda src, dst: self.on_converted and self.on_converted(src, dst))
        except ImportError:                                      # alte Installation ohne convert_mp3.py
            self.jobs = None
        self.port, self.log = port, log or (lambda t: None)
        self.srv, self.thread = None, None
        self.key_write = False                                  # geschaetzte Tonart ins TKEY schreiben (vom Pi, Standard aus)
        self.energy_write = False                               # geschaetzte Energiestufe in die MP3s schreiben (vom Pi, Standard aus)
        self.rg_write = False                                   # ReplayGain in MP3s ohne Angabe schreiben (vom Pi, Standard aus, 11.11.2026)
        self.cue_est = False                                    # Cues aus der Datei oder geschaetzt fuers Licht (vom Pi, Standard aus)
        self.cue_write = False                                  # geschaetzte Cues beim App-Start in Mixxx schreiben (vom Pi, Standard aus)
        self.pi_libh = None                                     # Fassung der Liste am Pi (/api/musik/conf), None = unbekannt
        self.pi_libd = False                                    # Pi hat die Stuecke seiner Fassung im Speicher (dann reicht Geaendertes)
        self.pi_miss = ("", [])                                 # (Fassung, fehlende Stuecke) des laufenden Durchgangs am Pi
        self.pi_missn = 0                                       # Zahl aller fehlenden Stuecke am Pi (pi_miss hat hoechstens 600)
        self.conf_root, self.pi_root = self.loc.root, None    # Reserve aus config.sh, Ordner aus dem Panel (None = noch nicht geholt)
        self.stop_ev = threading.Event()

    def apply_conf(self, d):
        """Antwort des Pi (/api/musik/conf) uebernehmen: der Ordner aus dem Panel geht vor, leer = Reserve aus config.sh."""
        root = str(d.get("root") or "").strip() if isinstance(d, dict) else ""
        self.energy_write = bool(isinstance(d, dict) and d.get("ew") is True)   # Einstellung energy_write am Pi (Standard aus)
        self.key_write = bool(isinstance(d, dict) and d.get("kw") is True)      # Einstellung key_write am Pi (Standard aus)
        self.rg_write = bool(isinstance(d, dict) and d.get("rw") is True)       # Einstellung rg_write am Pi (Standard aus)
        self.cue_est = bool(isinstance(d, dict) and d.get("ce") is True)        # Einstellung cue_est am Pi (Standard aus)
        self.cue_write = bool(isinstance(d, dict) and d.get("cw") is True)      # Einstellung cue_write am Pi (Standard aus)
        if isinstance(d, dict) and isinstance(d.get("mx"), bool):  # Mixxx verwenden (14.11.2026); alter Pi ohne Angabe: wie gemerkt
            set_mixxx_off(not d["mx"], self.log)
        self.pi_libh = str(d["libh"]) if isinstance(d, dict) and "libh" in d else None   # Fassung der Liste am Pi (None: alter Pi)
        self.pi_libd = bool(isinstance(d, dict) and d.get("libd") is True)   # Pi kann Geaendertes einbauen (Stuecke im Speicher)
        miss = d.get("miss") if isinstance(d, dict) else None
        self.pi_miss = (str(d.get("libr") or ""), [int(i) for i in miss if isinstance(i, int)][:600]) if isinstance(miss, list) else ("", [])
        mn = d.get("missn") if isinstance(d, dict) else None
        self.pi_missn = int(mn) if isinstance(mn, int) and not isinstance(mn, bool) and mn >= 0 else len(self.pi_miss[1])
        if isinstance(d, dict) and isinstance(d.get("excl"), list):   # ausgeschlossene Ordner (Wunsch 10.11.2026; alter Pi: bleibt wie gemerkt)
            import music_excl
            old_ex = music_excl.get()
            ex = music_excl.set_list(d["excl"])
            if ex != old_ex:
                self.log("Ausgeschlossene Ordner: " + (", ".join(ex) if ex else "keine"))
        if isinstance(d, dict) and isinstance(d.get("nas"), dict):   # NAS fuer das Spiegeln aus den Einstellungen (10.11.2026)
            try:
                import nas_mirror
                if nas_mirror.from_pi(d["nas"]):
                    self.log("NAS-Angaben aus den Einstellungen uebernommen")
            except Exception:                                    # noqa: BLE001
                pass
        new = root.rstrip("/") or self.conf_root
        if root != self.pi_root:
            self.pi_root = root
            if new != self.loc.root:
                self.log(f"Vorhoeren: Musikordner {new or '(keiner)'}" + (" aus dem Panel" if root else " aus config.sh"))
        self.loc.root = new
        try:
            import stick_hold
            if stick_hold.moved(new):
                self.log(f"Musikordner auf anderem Laufwerk ({new}): Sperre des ausgeworfenen Sticks aufgehoben")
        except Exception:                                        # noqa: BLE001
            pass
        return new

    def sync(self, url, opener=urllib.request.urlopen):
        """Alle 30 s den Musikordner vom Pi holen (eigener Thread, Fehler still: ohne Pi gilt config.sh)."""
        def loop():
            while not self.stop_ev.is_set():
                try:
                    with opener(url, timeout=3.0) as r:
                        conf = json.loads(r.read().decode("utf-8"))
                    self.apply_conf(conf)
                    if isinstance(conf, dict) and conf.get("stars"):
                        self.take_stars(conf["stars"], url.split("/api/")[0], opener)
                except Exception:                                  # noqa: BLE001  (Pi aus, alter Pi ohne diese Seite, kein Netz)
                    pass
                if self.stop_ev.wait(self.SYNC_S):
                    return
        threading.Thread(target=loop, daemon=True).start()

    def take_stars(self, items, pi_base, opener=urllib.request.urlopen):
        """Im Light-Butler gesetzte Sterne (14.11.2026): in die Warteschlange fuer Mixxx, dann dem Pi bestaetigen.
        Eingetragen werden sie beim naechsten Start der Mixxx-App (mixxx_sterne.py, Mixxx laeuft dann nicht)."""
        import mixxx_sterne
        ok = mixxx_sterne.add(items)
        if ok:
            req = urllib.request.Request(pi_base + "/api/sm/cmd", data=json.dumps({"op": "stars_ack", "items": ok}).encode("utf-8"), method="POST")
            with opener(req, timeout=5.0) as r:
                r.read()
            self.log(f"Sterne fuer Mixxx vorgemerkt: {len(ok)} (kommen beim naechsten Start der Mixxx-App hinein)")
        return ok

    RETRY_S, RETRY_FOR_S = 3.0, 600.0

    def start(self, tries=1, wait_s=1.0, retry_bg=False):
        """Webserver starten. tries > 1: so oft im Abstand wait_s versuchen (der Light-Butler Helfer gibt den Port gerade frei).
        retry_bg: klappt es nicht, im Hintergrund alle RETRY_S Sekunden weiter versuchen (bis RETRY_FOR_S) und True liefern
        (Fehlerbericht 08.11.2026: der Helfer gab Port 9025 erst nach 6 s frei, die Bruecke lief dann ohne Vorhoeren)."""
        for i in range(max(1, tries)):
            try:
                self.srv = ThreadingHTTPServer(("0.0.0.0", self.port), make_handler(self.loc, self.log, self.trash, self.marks, self.jobs, self.meta, self))
                break
            except OSError as e:
                self.srv = None
                if i + 1 >= max(1, tries):
                    if retry_bg:
                        self.log(f"Vorhoeren: Port {self.port} noch belegt ({e}), versuche es im Hintergrund weiter")
                        threading.Thread(target=self._retry, name="vorhoeren-start", daemon=True).start()
                        return True
                    self.log(f"Vorhoeren: Port {self.port} nicht verfuegbar ({e}), kein Vorhoeren")
                    return False
                time.sleep(wait_s)
        self._serve()
        return True

    def _retry(self):
        t0 = time.time()
        while not self.stop_ev.wait(self.RETRY_S):
            try:
                self.srv = ThreadingHTTPServer(("0.0.0.0", self.port), make_handler(self.loc, self.log, self.trash, self.marks, self.jobs, self.meta, self))
            except OSError as e:
                self.srv = None
                if time.time() - t0 > self.RETRY_FOR_S:
                    self.log(f"Vorhoeren: Port {self.port} nicht verfuegbar ({e}), kein Vorhoeren")
                    return
                continue
            self._serve()
            return

    def _serve(self):
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self.log(f"Vorhoeren: Musik der Bibliothek auf Port {self.port} fuer das Panel ({len(self.loc.paths)} Dateien)")
        return True

    def stop(self):
        self.stop_ev.set()
        if self.srv is not None:
            self.srv.shutdown()
            self.srv.server_close()
            self.srv = None
