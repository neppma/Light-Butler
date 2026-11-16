#!/usr/bin/env python3
"""
stems_backup.py - Sicherung der Spur-Kurven vom Pi auf den USB-Stick mit der Musik (Wunsch von Markus, 06.11.2026).

Die Kurven stecken in vielen Stunden Rechenzeit am Windows-PC. Sie liegen am Pi in shows/_stems (je MP3 eine kleine Datei)
und kommen hier auf den Stick, in einen eigenen Ordner neben dem Musikordner:
    /Volumes/STICK/musik            <- Musikordner (Einstellungen -> Verbindungen)
    /Volumes/STICK/musik-backup/Light-Butler-Kurven/<Fingerabdruck>.json
Kopiert wird nur, was neu oder geaendert ist; am Mac selbst bleibt nichts liegen. Die Mixxx-Bruecke ruft das alle 30 Minuten
auf, solange der Stick steckt. Geloescht wird auf dem Stick nie etwas.

Von Hand:
    python3 stems_backup.py --pi lightbutler.local --ziel "/Volumes/USB STICK/musik-backup/Light-Butler-Kurven"
Zurueckspielen (z. B. nach einem neuen Pi), der Pi prueft jede Datei wie neu gerechnete Kurven:
    python3 stems_backup.py --pi lightbutler.local --ziel "/Volumes/USB STICK/musik-backup/Light-Butler-Kurven" --zurueck
Genauso die Cue-Punkte (--cues, musik-backup/Light-Butler-Cues), die Cover (--covers, musik-backup/Light-Butler-Covers/<Fingerabdruck>.jpg)
und die Interpreten-Bilder (--interpreten, musik-backup/Light-Butler-Interpreten/<Name>.jpg).
"""
import argparse
import base64
import json
import os
import re
import sys
import threading
import urllib.parse
import urllib.request

# Ordner neben dem Musikordner, wie der Wartebereich musik-import (Wunsch 13.11.2026; frueher "Backup", zieht von selbst um)
BACKUP_NAME = "musik-backup"
OLD_BACKUP = "Backup"
FOLDER = os.path.join(BACKUP_NAME, "Light-Butler-Kurven")
CUES_FOLDER = os.path.join(BACKUP_NAME, "Light-Butler-Cues")     # Cue-Punkte, Abschnitte, Drops je Lied (lesbar, auch ohne Mixxx)
CUE_RE = re.compile(r"^[0-9a-f]{24}\.json$")                 # wie pi/showman/marks_bulk.py
COVERS_FOLDER = os.path.join(BACKUP_NAME, "Light-Butler-Covers")  # Cover je Lied, Dateiname = Fingerabdruck der Musikdatei
COVER_RE = re.compile(r"^\d{1,12}_[0-9a-f]{16}\.jpg$")        # wie pi/showman/covers.py
ARTISTS_FOLDER = os.path.join(BACKUP_NAME, "Light-Butler-Interpreten")   # Interpreten-Bilder (13.11.2026), Name = Schluessel
ARTIST_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}\.jpg$")      # wie pi/showman/artists.py
FP_RE = re.compile(r"^\d{1,12}:[0-9a-f]{16}$")          # wie pi/showman/store.py
EVERY_S = 30 * 60.0


def dest_for(music_root, folder=FOLDER):
    """Ordner der Sicherung neben dem Musikordner, oder '' (kein Musikordner, Stick nicht da)."""
    root = (music_root or "").rstrip("/")
    if not root or not os.path.isdir(root):
        return ""
    return os.path.join(os.path.dirname(root), folder)



def move_old(music_root, log=print):
    """Alte Sicherungen umziehen: Backup/... nach musik-backup/ (am selben Laufwerk nur umbenennen). Gibt es den neuen Ordner schon, kommen nur fehlende Dateien
    hinueber. Ein alter Ordner verschwindet nur, wenn er danach ganz leer ist (geloescht wird nie etwas). Rueckgabe: Zahl."""
    root = (music_root or "").rstrip("/")
    if not root or not os.path.isdir(root):
        return 0
    base = os.path.dirname(root)
    new_b = os.path.join(base, BACKUP_NAME)
    moved = 0
    for f in (FOLDER, CUES_FOLDER, COVERS_FOLDER, ARTISTS_FOLDER):
        sub = os.path.basename(f)
        new = os.path.join(new_b, sub)
        for old in (os.path.join(base, OLD_BACKUP, sub),):
            if not os.path.isdir(old):
                continue
            try:
                if not os.path.exists(new):
                    os.makedirs(new_b, exist_ok=True)
                    os.rename(old, new)
                    moved += 1
                    continue
                for n in os.listdir(old):
                    if not os.path.exists(os.path.join(new, n)):
                        os.rename(os.path.join(old, n), os.path.join(new, n))
                        moved += 1
                if not os.listdir(old):                    # nur ganz leere Ordner verschwinden (geloescht wird nie etwas)
                    os.rmdir(old)
            except OSError as e:
                log(f"Sicherung: Umzug nach {new} ging nicht ({e})")
                return moved
    old_b = os.path.join(base, OLD_BACKUP)
    try:
        if os.path.isdir(old_b) and not os.listdir(old_b):
            os.rmdir(old_b)
    except OSError:
        pass
    if moved:
        log(f"Sicherung: alte Ordner umgezogen nach {BACKUP_NAME}/Light-Butler-... (neben dem Musikordner)")
    return moved


def sync_cues(base, dest, opener=urllib.request.urlopen):
    """Neue oder geaenderte Cue-Dateien vom Pi nach dest (Wunsch von Markus: sicher am Stick, auch ohne Mixxx). (kopiert, vorhanden)"""
    with opener(base + "/api/sm/marks_list", timeout=20) as r:
        files = json.loads(r.read().decode("utf-8")).get("files") or []
    os.makedirs(dest, exist_ok=True)
    copied = 0
    for name, size in files:
        if not CUE_RE.match(str(name)):
            continue
        p = os.path.join(dest, name)
        try:
            if os.path.getsize(p) == size:
                continue
        except OSError:
            pass
        with opener(base + "/api/sm/marks_file?f=" + urllib.parse.quote(name), timeout=30) as r:
            data = r.read()
        with open(p + ".tmp", "wb") as f:
            f.write(data)
        os.replace(p + ".tmp", p)
        copied += 1
    return copied, len(files)


def restore_cues(base, src, opener=urllib.request.urlopen, log=print):
    """Cue-Dateien aus der Sicherung an den Pi (der Pi prueft jede). (ok, Fehler)"""
    ok = bad = 0
    for n in sorted(os.listdir(src)):
        if not CUE_RE.match(n):
            continue
        try:
            with open(os.path.join(src, n), encoding="utf-8") as f:
                data = json.load(f)
            body = json.dumps({"op": "marks_restore", "f": n, "data": data}).encode("utf-8")
            req = urllib.request.Request(base + "/api/sm/cmd", body, {"Content-Type": "application/json"})
            with opener(req, timeout=30) as r:
                res = json.loads(r.read().decode("utf-8") or "{}")
            if res.get("error"):
                raise ValueError(res["error"])
            ok += 1
        except (OSError, ValueError) as e:
            bad += 1
            log("  %s: %s" % (n, e))
    return ok, bad


def sync_covers(base, dest, opener=urllib.request.urlopen):
    """Neue Cover vom Pi nach dest (Wunsch von Markus: mit dem Fingerabdruck als Dateiname). (kopiert, vorhanden)"""
    with opener(base + "/api/sm/covers_list", timeout=20) as r:
        files = json.loads(r.read().decode("utf-8")).get("files") or []
    os.makedirs(dest, exist_ok=True)
    copied = 0
    for entry in files:
        name, size = entry[0], entry[1]
        mtime = entry[2] if len(entry) > 2 else None       # aeltere Pi-Programme schicken nur Name und Groesse
        if not COVER_RE.match(str(name)):
            continue
        p = os.path.join(dest, name)
        try:                                               # gleich, wenn Groesse und (falls bekannt) Aenderungszeit passen:
            if os.path.getsize(p) == size and (mtime is None or abs(os.path.getmtime(p) - mtime) < 2):
                continue                                   # ein neues Cover hat denselben Namen (Fingerabdruck der Musik)
        except OSError:
            pass
        with opener(base + "/api/sm/covers_file?f=" + urllib.parse.quote(name), timeout=30) as r:
            data = r.read()
        with open(p + ".tmp", "wb") as f:
            f.write(data)
        os.replace(p + ".tmp", p)
        if mtime is not None:
            try:
                os.utime(p, (mtime, mtime))                # Zeit vom Pi: beim naechsten Mal als gleich erkannt
            except OSError:
                pass
        copied += 1
    return copied, len(files)


def sync_artists(base, dest, opener=urllib.request.urlopen):
    """Interpreten-Bilder vom Pi nach dest (neu oder geaendert: Groesse oder Zeit). (kopiert, vorhanden)"""
    with opener(base + "/api/sm/artists_list", timeout=20) as r:
        files = json.loads(r.read().decode("utf-8")).get("files") or []
    os.makedirs(dest, exist_ok=True)
    copied = 0
    for entry in files:
        name, size, mtime = entry[0], entry[1], entry[2]
        if not ARTIST_RE.match(str(name)):
            continue
        p = os.path.join(dest, name)
        try:
            if os.path.getsize(p) == size and abs(os.path.getmtime(p) - mtime) < 2:
                continue
        except OSError:
            pass
        with opener(base + "/api/sm/artists_file?f=" + urllib.parse.quote(name), timeout=30) as r:
            data = r.read()
        with open(p + ".tmp", "wb") as f:
            f.write(data)
        os.replace(p + ".tmp", p)
        try:
            os.utime(p, (mtime, mtime))
        except OSError:
            pass
        copied += 1
    return copied, len(files)


def restore_artists(base, src, opener=urllib.request.urlopen, log=print):
    """Interpreten-Bilder aus der Sicherung an den Pi (der Pi prueft jedes Bild). (ok, Fehler)"""
    ok = bad = 0
    for n in sorted(os.listdir(src)):
        if not ARTIST_RE.match(n):
            continue
        try:
            with open(os.path.join(src, n), "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            body = json.dumps({"op": "artists_restore", "f": n, "data": data}).encode("utf-8")
            req = urllib.request.Request(base + "/api/sm/cmd", body, {"Content-Type": "application/json"})
            with opener(req, timeout=30) as r:
                res = json.loads(r.read().decode("utf-8") or "{}")
            if res.get("error"):
                raise ValueError(res["error"])
            ok += 1
        except (OSError, ValueError) as e:
            bad += 1
            log("  %s: %s" % (n, e))
    return ok, bad


def restore_covers(base, src, opener=urllib.request.urlopen, log=print):
    """Cover aus der Sicherung an den Pi (der Pi prueft jedes Bild). (ok, Fehler)"""
    ok = bad = 0
    for n in sorted(os.listdir(src)):
        if not COVER_RE.match(n):
            continue
        try:
            with open(os.path.join(src, n), "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            body = json.dumps({"op": "covers_restore", "f": n, "data": data}).encode("utf-8")
            req = urllib.request.Request(base + "/api/sm/cmd", body, {"Content-Type": "application/json"})
            with opener(req, timeout=30) as r:
                res = json.loads(r.read().decode("utf-8") or "{}")
            if res.get("error"):
                raise ValueError(res["error"])
            ok += 1
        except (OSError, ValueError) as e:
            bad += 1
            log("  %s: %s" % (n, e))
    return ok, bad


def fname(fp):
    return fp.replace(":", "_") + ".json"


def sync(base, dest, opener=urllib.request.urlopen):
    """Neue oder geaenderte Kurven vom Pi (base = http://pi:8080) nach dest. Rueckgabe: (kopiert, vorhanden)."""
    with opener(base + "/api/sm/stems_list", timeout=20) as r:
        files = json.loads(r.read().decode("utf-8")).get("files") or []
    os.makedirs(dest, exist_ok=True)
    copied = 0
    for fp, size in files:
        if not FP_RE.match(str(fp)):
            continue
        p = os.path.join(dest, fname(fp))
        try:
            if os.path.getsize(p) == size:
                continue
        except OSError:
            pass
        with opener(base + "/api/sm/stems_file?fp=" + urllib.parse.quote(fp), timeout=60) as r:
            data = r.read()
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
        copied += 1
    return copied, len(files)


def restore(base, src, opener=urllib.request.urlopen, log=print):
    """Alle Kurven aus der Sicherung an den Pi schicken (der Pi prueft jede). Rueckgabe: (ok, Fehler)."""
    ok = bad = 0
    for n in sorted(os.listdir(src)):
        m = re.match(r"^(\d{1,12})_([0-9a-f]{16})\.json$", n)
        if not m:
            continue
        fp = m.group(1) + ":" + m.group(2)
        try:
            with open(os.path.join(src, n), encoding="utf-8") as f:
                data = json.load(f)
            body = json.dumps({"op": "stems_restore", "fp": fp, "data": data}).encode("utf-8")
            req = urllib.request.Request(base + "/api/sm/cmd", body, {"Content-Type": "application/json"})
            with opener(req, timeout=60) as r:
                res = json.loads(r.read().decode("utf-8") or "{}")
            if res.get("error"):
                raise ValueError(res["error"])
            ok += 1
        except (OSError, ValueError) as e:
            bad += 1
            log("  %s: %s" % (n, e))
    return ok, bad


class Keeper:
    """Laeuft in der Mixxx-Bruecke: alle 30 Minuten abgleichen, still, wenn Stick oder Pi fehlen."""

    def __init__(self, base, music_root, log=print, every=EVERY_S, opener=urllib.request.urlopen):
        self.base, self.music_root, self.log, self.every, self.opener = base, music_root, log, every, opener
        self.stop_ev = threading.Event()
        self.last, self.err = None, False

    def once(self):
        dest = dest_for(self.music_root())
        if not dest:
            return None
        move_old(self.music_root(), self.log)
        try:
            copied, n = sync(self.base, dest, self.opener)
            try:                                               # dazu die Cue-Punkte (aelterer Pi: gibt es noch nicht)
                cc, cn = sync_cues(self.base, dest_for(self.music_root(), CUES_FOLDER), self.opener)
                if cc:
                    self.log(f"Cue-Sicherung: {cc} neu auf dem Stick ({cn} gesamt)")
            except (OSError, ValueError):
                pass
            try:                                               # und die Cover (aelterer Pi: gibt es noch nicht)
                vc, vn = sync_covers(self.base, dest_for(self.music_root(), COVERS_FOLDER), self.opener)
                if vc:
                    self.log(f"Cover-Sicherung: {vc} neu auf dem Stick ({vn} gesamt)")
            except (OSError, ValueError):
                pass
            try:                                               # und die Interpreten-Bilder (aelterer Pi: gibt es noch nicht)
                ac, an = sync_artists(self.base, dest_for(self.music_root(), ARTISTS_FOLDER), self.opener)
                if ac:
                    self.log(f"Interpreten-Sicherung: {ac} neu auf dem Stick ({an} gesamt)")
            except (OSError, ValueError):
                pass
            try:
                self.programs()
            except Exception as e:                             # noqa: BLE001  die Programme duerfen die Sicherung nie stoeren
                self.log(f"Programme am Stick: {e}")
        except (OSError, ValueError) as e:
            if not self.err:                                   # nur einmal melden, nicht jede Minute
                self.log(f"Kurven-Sicherung: Pi nicht erreichbar ({e})")
            self.err = True
            return None
        self.err = False
        if copied:
            self.log(f"Kurven-Sicherung: {copied} neu auf dem Stick ({n} gesamt) in {dest}")
        self.last = (copied, n)
        return self.last

    def programs(self):
        """Pakete, Handbuecher und Sicherung nach Light-Butler-Programme neben dem Musikordner (14.11.2026)."""
        try:
            import programs_copy
        except ImportError:
            return None
        try:
            res = programs_copy.sync(self.base, self.music_root(), self.opener, log=self.log)
        except (OSError, ValueError) as e:
            self.log(f"Programme am Stick: {e}")
            programs_copy.report(self.base, {}, self.opener, err=str(e)[:200])
            return None
        if res is not None:
            if res.get("new"):
                self.log(f"Programme am Stick aktualisiert: {res['dir']} ({res['mb']} MB)")
            programs_copy.report(self.base, res, self.opener)
        return res

    def start(self):
        def loop():
            while not self.stop_ev.wait(60.0 if self.last is None else self.every):
                import stick_hold
                if stick_hold.held():                     # Stick wird ausgeworfen oder ist ausgeworfen: nicht schreiben
                    continue
                self.once()
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self.stop_ev.set()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Spur-Kurven vom Pi auf den Stick sichern oder zurueckspielen")
    ap.add_argument("--pi", required=True, help="HOST[:PORT] des Pi (Port 8080, wenn nicht angegeben)")
    ap.add_argument("--ziel", required=True, help="Ordner der Sicherung, z. B. /Volumes/STICK/musik-backup/Light-Butler-Kurven")
    ap.add_argument("--zurueck", action="store_true", help="aus dem Ordner an den Pi zurueckspielen")
    ap.add_argument("--cues", action="store_true", help="Cue-Punkte statt Kurven (Ordner musik-backup/Light-Butler-Cues)")
    ap.add_argument("--covers", action="store_true", help="Cover statt Kurven (Ordner musik-backup/Light-Butler-Covers)")
    ap.add_argument("--interpreten", action="store_true", help="Interpreten-Bilder statt Kurven (Ordner musik-backup/Light-Butler-Interpreten)")
    a = ap.parse_args(argv)
    base = "http://" + (a.pi if ":" in a.pi else a.pi + ":8080")
    if a.interpreten:
        if a.zurueck:
            ok, bad = restore_artists(base, a.ziel)
            print(f"Zurueckgespielt: {ok}, Fehler: {bad}")
            return 1 if bad else 0
        copied, n = sync_artists(base, a.ziel)
        print(f"Gesichert: {copied} neu, {n} am Pi")
        return 0
    if a.covers:
        if a.zurueck:
            ok, bad = restore_covers(base, a.ziel)
            print(f"Zurueckgespielt: {ok}, Fehler: {bad}")
            return 1 if bad else 0
        copied, n = sync_covers(base, a.ziel)
        print(f"Gesichert: {copied} neu, {n} am Pi")
        return 0
    if a.cues:
        ok, bad = restore_cues(base, a.ziel) if a.zurueck else (0, 0)
        if not a.zurueck:
            copied, n = sync_cues(base, a.ziel)
            print(f"Gesichert: {copied} neu, {n} am Pi")
            return 0
        print(f"Zurueckgespielt: {ok}, Fehler: {bad}")
        return 1 if bad else 0
    if a.zurueck:
        ok, bad = restore(base, a.ziel)
        print(f"Zurueckgespielt: {ok}, Fehler: {bad}")
        return 1 if bad else 0
    copied, n = sync(base, a.ziel)
    print(f"Gesichert: {copied} neu, {n} am Pi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
