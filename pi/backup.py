#!/usr/bin/env python3
"""
backup.py - Sicherung der Lichtsteuerung (Raspberry Pi) in ein Zip.

  python3 backup.py --now                    jetzt sichern
  python3 backup.py --auto                   leise sichern (fuer den Zeitplan)
  python3 backup.py --list                   vorhandene Sicherungen zeigen
  python3 backup.py --verify DATEI.zip       Pruefsummen kontrollieren
  python3 backup.py --restore DATEI.zip      wiederherstellen (vorher wird der jetzige Stand gesichert)
        --ausgaben-aus  danach DMX, WLED und Nanoleaf aus (Ersatzgeraet, solange der Haupt-Pi laeuft)
        --dry-run     nur anzeigen, was passieren wuerde
        --only data   nur Einstellungen, Szenen, Ziele ... (nicht die Programme)
        --system      auch die Dienstdateien nach /etc/systemd/system (nur als root)

Was gesichert wird (Ordner der Lichtsteuerung):
  Programme (*.py), fixtures.yaml, show.conf, scenes.json, settings.json, aim.json, audio.json, midimap.json,
  nanoleaf.json, Anleitungen und alles Weitere, was als einfache Datei in diesem Ordner liegt;
  dazu die Dienstdateien des Systems (lichtshow.service und Zeitplan) und eine Liste der installierten Pakete.
Optionen in backup.conf (JSON, neben diesem Programm):
  {"dir": "~/backups", "keep": 14, "copy_to": "/mnt/nas/backups", "include_secrets": true}
"""
import argparse
import fnmatch
import glob
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
PREFIX = "lichtshow-backup-"
INCLUDE = ["*.py", "*.yaml", "*.yml", "*.json", "*.conf", "*.txt", "*.md", "*.service", "*.timer", "*.sh"]
EXCLUDE = ["*.tmp", "*.pyc", "*.zip"]
SYSTEM_FILES = ["/etc/systemd/system/lichtshow.service", "/etc/systemd/system/lichtshow-backup.service",
                "/etc/systemd/system/lichtshow-backup.timer"]
SECRET_FILES = ["nanoleaf.json", "claude.json"]
DEFAULTS = {"dir": "~/backups", "keep": 14, "copy_to": "", "include_secrets": True}


def load_conf(path=None):
    cfg = dict(DEFAULTS)
    p = path or os.path.join(BASE, "backup.conf")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, ValueError) as e:
            print(f"Hinweis: backup.conf nicht lesbar ({e}), Standardwerte werden benutzt.", file=sys.stderr)
    cfg["dir"] = os.path.expanduser(cfg["dir"])
    return cfg


def log(cfg, text):
    os.makedirs(cfg["dir"], exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}"
    try:
        with open(os.path.join(cfg["dir"], "backup.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    return line


def sha256(path=None, data=None):
    h = hashlib.sha256()
    if data is not None:
        h.update(data)
    else:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def collect(cfg):
    """Dateien im Programmordner, die gesichert werden: [(Pfad, Name im Zip)]."""
    out = []
    for name in sorted(os.listdir(BASE)):
        full = os.path.join(BASE, name)
        if not os.path.isfile(full) or os.path.islink(full):
            continue
        if not any(fnmatch.fnmatch(name, p) for p in INCLUDE) or any(fnmatch.fnmatch(name, p) for p in EXCLUDE):
            continue
        if not cfg.get("include_secrets", True) and name in SECRET_FILES:
            continue
        out.append((full, "lichtshow/" + name))
    for full in sorted(glob.glob(os.path.join(BASE, "shows", "*", "*.json"))):     # Showmanager: Shows ohne die MP3s (zu gross)
        show = os.path.basename(os.path.dirname(full))
        if not show.startswith("_"):
            out.append((full, f"lichtshow/shows/{show}/{os.path.basename(full)}"))
    if os.path.isfile(os.path.join(BASE, "shows", "_bibliothek.json")):
        out.append((os.path.join(BASE, "shows", "_bibliothek.json"), "lichtshow/shows/_bibliothek.json"))
    for sf in SYSTEM_FILES + glob.glob("/etc/systemd/system/lichtshow*.d/*.conf"):
        if os.path.isfile(sf):
            out.append((sf, "system" + sf))
    return out


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def info_text():
    pk = _run(["pip3", "list", "--format=freeze"]) or _run([sys.executable, "-m", "pip", "list", "--format=freeze"])
    keep = [ln for ln in pk.splitlines() if ln.split("==")[0].lower() in
            ("numpy", "scipy", "sounddevice", "soundfile", "aubio", "pyyaml", "mido", "python-rtmidi")]
    deb = _run(["dpkg-query", "-W", "-f=${Package} ${Version}\\n", "python3-mido", "python3-rtmidi", "python3-numpy",
                "python3-scipy", "python3-aubio", "python3-yaml", "libportaudio2", "alsa-utils"])
    return "\n".join([
        f"Gesichert am:   {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Rechner:        {socket.gethostname()}",
        f"System:         {platform.platform()}",
        f"Python:         {platform.python_version()}",
        f"Ordner:         {BASE}", "", "Python-Pakete (pip):", *(keep or ["(keine gefunden)"]), "",
        "Systempakete (apt):", deb or "(nicht abfragbar)", ""])


RESTORE_TEXT = """WIEDERHERSTELLEN
================
Auf dem Raspberry Pi (Ordner ~/lichtshow, mit backup.py aus dieser Sicherung):

  python3 backup.py --verify DATEI.zip                  Pruefsummen kontrollieren
  python3 backup.py --restore DATEI.zip --dry-run       nur anzeigen, was passieren wuerde
  python3 backup.py --restore DATEI.zip                 wiederherstellen (jetziger Stand wird vorher gesichert)
  python3 backup.py --restore DATEI.zip --only data     nur Einstellungen, Szenen und Ziele (nicht die Programme)
  sudo python3 backup.py --restore DATEI.zip --system   zusaetzlich die Dienstdateien nach /etc/systemd/system

Danach:  sudo systemctl daemon-reload && sudo systemctl restart lichtshow

Auf einem frischen Pi: Ordner ~/lichtshow anlegen, backup.py aus dem Zip dorthin kopieren (Ordner lichtshow/ im Zip),
dann die Schritte oben. Benoetigte Pakete stehen in INFO.txt.
Hinweis: nanoleaf.json enthaelt den API-Key des Nanoleaf. Das Zip darum nicht weitergeben.
"""


def create(cfg, reason="manuell"):
    """Zip erstellen; gibt den Pfad zurueck."""
    os.makedirs(cfg["dir"], exist_ok=True)
    files = collect(cfg)
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    final = os.path.join(cfg["dir"], f"{PREFIX}{stamp}.zip")
    tmp = final + ".tmp"
    manifest = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "reason": reason, "host": socket.gethostname(),
                "base": BASE, "files": []}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for full, arc in files:
            data = open(full, "rb").read()
            z.writestr(arc, data)
            manifest["files"].append({"name": arc, "size": len(data), "sha256": sha256(data=data)})
        z.writestr("INFO.txt", info_text())
        z.writestr("WIEDERHERSTELLEN.txt", RESTORE_TEXT)
        z.writestr("manifest.json", json.dumps(manifest, indent=1, ensure_ascii=False))
    os.replace(tmp, final)
    try:
        os.chmod(final, 0o600)                         # enthaelt ggf. den Nanoleaf-Key
    except OSError:
        pass
    return final, len(files)


def prune(cfg):
    keep = max(1, int(cfg.get("keep", 14)))
    items = sorted(glob.glob(os.path.join(cfg["dir"], PREFIX + "*.zip")))
    removed = []
    for p in items[:-keep] if len(items) > keep else []:
        try:
            os.remove(p)
            removed.append(os.path.basename(p))
        except OSError:
            pass
    return removed


def copy_out(cfg, path):
    dest = os.path.expanduser(cfg.get("copy_to") or "")
    if not dest:
        return ""
    if not os.path.isdir(dest):
        return f"Zielordner {dest} nicht erreichbar (NAS eingebunden?), keine Kopie"
    try:
        shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
        # alte Kopien im Ziel ebenfalls aufraeumen
        items = sorted(glob.glob(os.path.join(dest, PREFIX + "*.zip")))
        for p in items[:-max(1, int(cfg.get("keep", 14)))]:
            os.remove(p)
        return f"Kopie in {dest}"
    except OSError as e:
        return f"Kopie nach {dest} fehlgeschlagen: {e}"


def list_backups(cfg):
    out = []
    for p in sorted(glob.glob(os.path.join(cfg["dir"], PREFIX + "*.zip")), reverse=True):
        st = os.stat(p)
        out.append({"name": os.path.basename(p), "size": st.st_size, "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
    return out


def download_copy(cfg=None):
    """Juengste Sicherung zum Herunterladen im Panel (Wunsch 12.11.2026, Einstellungen -> Software fuer andere Rechner):
    (Dateiname, Zip als Bytes) oder None. Das Panel hat keine Anmeldung, darum ohne die geheimen Dateien (SECRET_FILES:
    Nanoleaf-Token, Schluessel des Show-Assistenten); das Manifest passt dazu, --verify und --restore gehen weiter. Die
    Sicherung am Pi bleibt unveraendert."""
    import io
    cfg = cfg or load_conf()
    lst = list_backups(cfg)
    if not lst:
        return None
    src = os.path.join(cfg["dir"], lst[0]["name"])
    secret = {"lichtshow/" + n for n in SECRET_FILES}
    buf = io.BytesIO()
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in zi.infolist():
            if info.filename in secret:
                continue
            data = zi.read(info.filename)
            if info.filename == "manifest.json":
                man = json.loads(data)
                man["files"] = [f for f in man.get("files", []) if f.get("name") not in secret]
                man["ohne"] = sorted(secret)
                data = json.dumps(man, indent=1, ensure_ascii=False).encode("utf-8")
            zo.writestr(info.filename, data)
        zo.writestr("OHNE_SCHLUESSEL.txt", "Diese Kopie kommt aus dem Panel und enthaelt keine geheimen Dateien ("
                    + ", ".join(SECRET_FILES) + "). Nach einem Wiederherstellen den Nanoleaf neu koppeln und den Schluessel "
                    "des Show-Assistenten neu eintragen.\n")
    return lst[0]["name"], buf.getvalue()


def verify(path):
    """Pruefsummen im Zip kontrollieren. Rueckgabe: (ok, Meldung)."""
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                return False, f"Zip beschaedigt bei {bad}"
            man = json.loads(z.read("manifest.json"))
            for f in man["files"]:
                if sha256(data=z.read(f["name"])) != f["sha256"]:
                    return False, f"Pruefsumme stimmt nicht: {f['name']}"
        return True, f"in Ordnung: {len(man['files'])} Dateien, gesichert am {man['created']}"
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
        return False, f"nicht lesbar: {e}"


DATA_PATTERNS = ["*.json", "*.yaml", "*.yml", "*.conf"]


OUTPUT_KEYS = ("ola_out", "wled_out", "nano_out")


def outputs_off(base=None):
    """Alle Ausgaben aus (DMX, WLED, Nanoleaf) in settings.json. Fuer ein Ersatzgeraet (12.11.2026): senden zwei Light-Butler
    zugleich, kaempfen sie ums Licht."""
    p = os.path.join(base or BASE, "settings.json")
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.update({k: 0.0 for k in OUTPUT_KEYS})
    with open(p + ".neu", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(p + ".neu", p)


def restore(cfg, path, dry=False, only="all", system=False, off=False):
    ok, msg = verify(path)
    if not ok:
        raise SystemExit(f"Abbruch, die Sicherung ist nicht in Ordnung: {msg}")
    plan = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.startswith("lichtshow/") and not n.endswith("/"):
                name = n[len("lichtshow/"):]
                in_shows = name.startswith("shows/") and name.endswith(".json") and ".." not in name   # Showmanager
                if ("/" in name and not in_shows) or name.startswith(".."):
                    continue
                if only == "data" and not any(fnmatch.fnmatch(name, p) for p in DATA_PATTERNS):
                    continue
                plan.append((n, os.path.join(BASE, name)))
            elif n.startswith("system/") and system:
                plan.append((n, n[len("system"):]))
        if dry:
            for src, dst in plan:
                print(("ueberschreibt " if os.path.exists(dst) else "legt an      ") + dst)
            print(f"{len(plan)} Dateien (Trockenlauf, nichts geaendert)")
            return
        safety, _ = create(cfg, reason="vor Wiederherstellung")
        print("Jetziger Stand gesichert in", safety)
        for src, dst in plan:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst + ".neu", "wb") as f:
                f.write(z.read(src))
            os.replace(dst + ".neu", dst)
    if off:
        outputs_off()
        print("Ausgaben aus (DMX, WLED, Nanoleaf): im Panel einschalten, wenn nur dieser Light-Butler sendet.")
    print(f"{len(plan)} Dateien wiederhergestellt. Danach: sudo systemctl daemon-reload && sudo systemctl restart lichtshow")


def main():
    ap = argparse.ArgumentParser(description="Sicherung der Lichtsteuerung")
    ap.add_argument("--now", action="store_true")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--verify", metavar="ZIP")
    ap.add_argument("--restore", metavar="ZIP")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["all", "data"], default="all")
    ap.add_argument("--system", action="store_true")
    ap.add_argument("--conf")
    ap.add_argument("--ausgaben-aus", action="store_true", help="nach --restore: DMX, WLED und Nanoleaf aus (Ersatzgeraet)")
    a = ap.parse_args()
    cfg = load_conf(a.conf)
    if a.list:
        for b in list_backups(cfg):
            print(f"{b['time']}  {b['size'] // 1024:6d} KB  {b['name']}")
        return
    if a.verify:
        ok, msg = verify(a.verify)
        print(("OK: " if ok else "FEHLER: ") + msg)
        sys.exit(0 if ok else 1)
    if a.restore:
        restore(cfg, a.restore, dry=a.dry_run, only=a.only, system=a.system, off=a.ausgaben_aus)
        return
    if a.now or a.auto:
        try:
            path, n = create(cfg, reason="automatisch" if a.auto else "manuell")
            ok, msg = verify(path)
            extra = copy_out(cfg, path)
            removed = prune(cfg)
            line = log(cfg, f"Sicherung {os.path.basename(path)}: {n} Dateien, {os.path.getsize(path) // 1024} KB, Pruefung {'ok' if ok else 'FEHLER'}"
                            + (f"; {extra}" if extra else "") + (f"; entfernt: {', '.join(removed)}" if removed else ""))
            if not a.auto:
                print(line)
            if not ok:
                sys.exit(1)
        except Exception as e:                                 # noqa: BLE001
            log(cfg, f"FEHLER: {e}")
            if not a.auto:
                raise
            sys.exit(1)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
