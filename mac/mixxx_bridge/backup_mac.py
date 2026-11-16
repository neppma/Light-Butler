#!/usr/bin/env python3
"""
backup_mac.py - Sicherung der Mac-Seite der Mixxx-Bruecke in ein Zip.

Gesichert wird der Ordner ~/Light-Butler-Daten: die Analysen der Lieder (viel Rechenzeit!), die Programme der Bruecke und
config.sh. Die Kopie der Mixxx-Datenbank wird nicht gesichert (sie entsteht bei jedem Start neu).

  python3 backup_mac.py                   jetzt sichern
  python3 backup_mac.py --if-older 7      nur sichern, wenn die letzte Sicherung aelter als 7 Tage ist
  python3 backup_mac.py --list            vorhandene Sicherungen zeigen

Ziel:  ~/Documents/Light-Butler-Backups   (die letzten 8 bleiben)
Wiederherstellen: Zip im Finder entpacken, den Ordner Light-Butler-Daten nach ~ kopieren (alten vorher umbenennen).
"""
import argparse
import fnmatch
import glob
import os
import sys
import time
import zipfile
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

BASE = _pfad.daten()
PREFIX = "light-butler-mac-"
DEFAULT_DIR = "~/Documents/Light-Butler-Backups"


def _items(dest):
    """Alle Sicherungen im Ordner, aelteste zuerst (nach Zeitstempel im Namen)."""
    return sorted(glob.glob(os.path.join(dest, PREFIX + "*.zip")), key=lambda p: os.path.basename(p).split("-mac-", 1)[-1])


def dest_dir(path):
    """Zielordner."""
    return os.path.expanduser(path)
EXCLUDE = ["mixxxdb.sqlite*", "*.tmp", "*.pyc", "__pycache__"]


def newest(dest):
    items = _items(dest)
    return items[-1] if items else None


def create(base, dest, keep):
    os.makedirs(dest, exist_ok=True)
    final = os.path.join(dest, f"{PREFIX}{time.strftime('%Y-%m-%d_%H%M%S')}.zip")
    tmp = final + ".tmp"
    n = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d, p) for p in EXCLUDE)]
            for f in files:
                if any(fnmatch.fnmatch(f, p) for p in EXCLUDE):
                    continue
                full = os.path.join(root, f)
                z.write(full, os.path.join("Light-Butler-Daten", os.path.relpath(full, base)))
                n += 1
    os.replace(tmp, final)
    items = _items(dest)
    for p in items[:-keep] if len(items) > keep else []:
        os.remove(p)
    return final, n


def main():
    ap = argparse.ArgumentParser(description="Sicherung der Mac-Seite (Analysen und Programme der Bruecke)")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--keep", type=int, default=8)
    ap.add_argument("--if-older", type=float, metavar="TAGE")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    dest, base = dest_dir(a.dir), os.path.expanduser(a.base)
    if a.list:
        for p in reversed(_items(dest)):
            print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(p)))}  {os.path.getsize(p) // 1024:7d} KB  {os.path.basename(p)}")
        return
    if not os.path.isdir(base):
        sys.exit(f"Ordner {base} nicht gefunden.")
    last = newest(dest)
    if a.if_older is not None and last and time.time() - os.path.getmtime(last) < a.if_older * 86400:
        print("Letzte Sicherung ist noch aktuell, nichts zu tun.")
        return
    path, n = create(base, dest, max(1, a.keep))
    print(f"{time.strftime('%H:%M:%S')} Sicherung {os.path.basename(path)}: {n} Dateien, {os.path.getsize(path) // 1024} KB")


if __name__ == "__main__":
    main()
