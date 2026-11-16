#!/usr/bin/env python3
"""mixxx_start.py - Windows-Gegenstueck zur Mac-App "Light-Butler Mixxx" (launch.sh aus install_launcher.sh).

Startet Mixxx und die Mixxx-Bruecke. Beendest du Mixxx, beendet sich die Bruecke.
Vorher, solange Mixxx zu ist (wie am Mac):
  * Sicherung der Mixxx-Datenbank (die letzten 5 in Light-Butler/mixxx-sicherung)
  * Umbenennungen aus "Dateien pruefen" (umbenannt/offen.tsv), Uebertragen auf Zwillinge (mixxx_uebertragen.py) und Sterne
    (sterne/offen.json) eintragen: immer ueber eine Arbeitskopie, die geprueft (integrity_check) und erst dann zurueckkopiert
    wird; geht etwas schief, kommt die Sicherung zurueck und alles bleibt in der Warteschlange.
  * Kopie der Datenbank nach Light-Butler/mixxxdb.sqlite fuer die Bruecke, waehrend Mixxx laeuft jede Minute eine Lesekopie
    (mixxxdb.live.sqlite) fuer den Abgleich in der Musik-Datenbank.

Die Daten von Mixxx kommen ueber den virtuellen MIDI-Anschluss "Light-Butler" von loopMIDI (am Mac IAC-Treiber).
Einstellungen: Light-Butler/config.json (pi, mixxx_bin, background_analysis, music_root, port), Log in
%LOCALAPPDATA%\\Light-Butler (launcher.log, bridge.log).

Aufruf:  python mixxx_start.py            (oder Light-Butler.exe mixxx_start.py)
"""
import datetime
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

HERE = os.path.dirname(os.path.abspath(__file__))
MIXXX_BIN_DEFAULT = r"C:\Program Files\Mixxx\mixxx.exe"
KEEP_BACKUPS = 5
LIVE_EVERY_S = 60


def data_dir():
    return _pfad.daten()


def log_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Light-Butler")


def mixxx_db():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Mixxx", "mixxxdb.sqlite")


def load_config(data):
    cfg = {"pi": "", "mixxx_bin": MIXXX_BIN_DEFAULT, "background_analysis": 1, "music_root": "", "port": "Light-Butler"}
    try:
        with open(os.path.join(data, "config.json"), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if not cfg["pi"]:
        try:
            with open(os.path.expanduser("~/.light-butler-pi"), encoding="utf-8") as f:
                cfg["pi"] = f.readline().strip()
        except OSError:
            cfg["pi"] = "127.0.0.1"                     # kein Pi eingetragen: Light-Butler auf diesem PC
    return cfg


def mixxx_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq mixxx.exe", "/NH"], capture_output=True, text=True, errors="replace",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except OSError:
        return False
    return "mixxx.exe" in (out or "").lower()


def dialog(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Light-Butler Mixxx", 0x30)
    except Exception:                                           # noqa: BLE001
        print(text)


def same(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                x, y = fa.read(1 << 20), fb.read(1 << 20)
                if x != y:
                    return False
                if not x:
                    return True
    except OSError:
        return False


def backup(src, data, stamp, log):
    """Sicherung bei jedem Start, die letzten KEEP_BACKUPS bleiben (wie launch.sh)."""
    d = os.path.join(data, "mixxx-sicherung")
    os.makedirs(d, exist_ok=True)
    try:
        shutil.copy2(src, os.path.join(d, f"mixxxdb-{stamp}.sqlite"))
    except OSError:
        log("Mixxx-Datenbank nicht gesichert (kein Zugriff)")
        return
    for old in sorted(glob.glob(os.path.join(d, "mixxxdb-*.sqlite")), reverse=True)[KEEP_BACKUPS:]:
        try:
            os.remove(old)
        except OSError:
            pass
    log("Mixxx-Datenbank gesichert")


def read_queue(path):
    pairs = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) == 2 and parts[0] and parts[1]:
                    pairs.append((parts[0], parts[1]))
    except OSError:
        pass
    return pairs


def apply_renames(con, pairs, log):
    """Pfad in track_locations aendern (Hotcues, Kisten bleiben). Gibt (erledigt, uebersprungen, bleibt) zurueck."""
    done, skip, keep = [], 0, []
    for old, new in pairs:
        try:
            if con.execute("SELECT count(*) FROM track_locations WHERE location=?", (new,)).fetchone()[0]:
                log(f"Umbenennen: {new} steht schon in Mixxx (neu eingelesen?), alter Eintrag bleibt")
                skip += 1
                continue
            d, f = new.rsplit("/", 1) if "/" in new else ("", new)
            ch = con.execute("UPDATE track_locations SET location=?, filename=?, directory=?, fs_deleted=0 WHERE location=?",
                             (new, f, d, old)).rowcount
        except sqlite3.Error as e:
            log(f"Umbenennen: {old}: {e}, bleibt fuer spaeter")
            keep.append((old, new))
            continue
        if ch == 1:
            done.append((old, new))
        else:
            log(f"Umbenennen: {old} nicht in Mixxx")
            skip += 1
    return done, skip, keep


def run_py(args, log):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=HERE,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        text = (r.stderr or r.stdout).strip().splitlines()
        log("Fehler: " + (text[-1] if text else os.path.basename(args[0])))
    return r.returncode, r.stdout.strip()


def prepare(src, data, log, stamp=None, test=False):
    """Alles, was Mixxx zu braucht: Umbenennungen, Uebertragen, Sterne, ueber eine gepruefte Arbeitskopie."""
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ren_dir = os.path.join(data, "umbenannt")
    star_dir = os.path.join(data, "sterne")
    q = os.path.join(ren_dir, "offen.tsv")
    pairs = read_queue(q)
    stars = False
    try:
        with open(os.path.join(star_dir, "offen.json"), encoding="utf-8") as f:
            stars = bool(json.load(f))
    except (OSError, ValueError):
        pass
    ueb = os.path.join(HERE, "mixxx_uebertragen.py")
    cues = os.path.join(data, "cues", "mixxx_neu.json")
    os.makedirs(ren_dir, exist_ok=True)
    rc = os.path.join(ren_dir, ".zaehlen.sqlite")
    need = 0
    if os.path.isfile(ueb):
        try:
            shutil.copy2(src, rc)
            code, out = run_py([ueb, rc, "--ordner", ren_dir, "--cues", cues, "--liste-nicht-analysiert", "--nur-zaehlen"], log)
            need = int(json.loads(out).get("geaendert", 0)) if not code and out else 0
        except (OSError, ValueError):
            need = 0
        finally:
            for x in (rc, rc + "-journal"):
                if os.path.exists(x):
                    os.remove(x)
    if not pairs and not stars and not need:
        return {"ok": 0, "tr": 0, "stars": 0}
    if not test:
        for _ in range(30):                                  # Mixxx schliesst sich manchmal noch
            if not mixxx_running():
                break
            time.sleep(1)
        if mixxx_running():
            log("Mixxx laeuft, Umbenennen und Sterne bleiben fuer spaeter")
            return {"ok": 0, "tr": 0, "stars": 0, "blocked": "Mixxx laeuft"}
    if os.path.exists(src + "-journal") or os.path.exists(src + "-wal"):
        log("Mixxx wurde nicht sauber beendet (Journal liegt neben der Datenbank), nichts geaendert")
        return {"ok": 0, "tr": 0, "stars": 0, "blocked": "Journal"}
    bak = os.path.join(ren_dir, f"mixxxdb-vor-umbenennen-{stamp}.sqlite")
    work = os.path.join(ren_dir, f".arbeit-{stamp}.sqlite")
    try:
        shutil.copy2(src, bak)
        shutil.copy2(bak, work)
    except OSError as e:
        log(f"Umbenennen: keine Sicherungskopie moeglich ({e}), nichts geaendert")
        return {"ok": 0, "tr": 0, "stars": 0, "blocked": "Kopie"}
    for old in sorted(glob.glob(os.path.join(ren_dir, "mixxxdb-vor-umbenennen-*.sqlite")), reverse=True)[KEEP_BACKUPS:]:
        os.remove(old)
    con = sqlite3.connect(work)
    done, skip, keep = apply_renames(con, pairs, log)
    con.commit()
    con.close()
    tr = 0
    if os.path.isfile(ueb):
        code, out = run_py([ueb, work, "--ordner", ren_dir, "--cues", cues, "--liste-nicht-analysiert",
                            "--protokoll", os.path.join(ren_dir, f"uebertragen-{stamp}.json")], log)
        try:
            tr = int(json.loads(out).get("geaendert", 0)) if not code else 0
        except ValueError:
            tr = 0
        log(f"Uebertragen: {out}")
    n_stars = 0
    if stars:
        code, out = run_py([os.path.join(HERE, "mixxx_sterne.py"), "--kopie", work], log)
        n_stars = int(out) if not code and out.isdigit() else 0
        if code or not out.isdigit():
            log(f"Sterne: {out or 'Arbeitskopie ging nicht'}, nichts eingetragen")
            stars = False
    back = ""
    if done or tr or n_stars:
        con = sqlite3.connect(work)
        chk = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        if chk != "ok":
            back = f"Pruefung der geaenderten Kopie: {chk}"
        elif not same(src, bak):
            back = "Mixxx-Datenbank hat sich inzwischen geaendert"
        else:
            try:
                shutil.copyfile(work, src)
                if not same(work, src):
                    raise OSError("Vergleich nach dem Kopieren")
            except OSError:
                back = "Zurueckkopieren in den Ordner von Mixxx ging nicht"
                if not same(src, bak):
                    shutil.copyfile(bak, src)
    if back:
        log(f"Umbenennen: {back}")
        keep += done
        done, tr, n_stars, stars = [], 0, 0, False
        prot = os.path.join(ren_dir, f"uebertragen-{stamp}.json")
        if os.path.exists(prot):
            os.remove(prot)
    for x in (work, work + "-journal"):
        if os.path.exists(x):
            os.remove(x)
    if pairs:
        os.replace(q, os.path.join(ren_dir, f"erledigt-{stamp}.tsv"))
    if keep:
        with open(q, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(f"{a}\t{b}\n" for a, b in keep)
    if stars and not back:
        run_py([os.path.join(HERE, "mixxx_sterne.py"), "--fertig"], log)
    log(f"Umbenennen (kopie): {len(done)} Pfade in Mixxx nachgezogen, {skip} uebersprungen, {len(keep)} bleiben fuer "
        f"spaeter, {tr} Kisten/Listen/Hotcues/Werte uebertragen, {n_stars} Sterne")
    return {"ok": len(done), "tr": tr, "stars": n_stars, "keep": len(keep), "blocked": back}


MAPPING = ("Light-Butler-Bridge.midi.xml", "Light-Butler-Bridge-scripts.js")


def install_mapping(log, ctrl_dir=None):
    """Mapping "Light-Butler Bridge" in den Controller-Ordner von Mixxx legen (nur diese zwei Dateien, nur wenn anders).
    In Mixxx danach einmal: Einstellungen -> Controller -> Light-Butler (loopMIDI) aktivieren, Mapping waehlen."""
    ctrl_dir = ctrl_dir or os.path.join(os.path.dirname(mixxx_db()), "controllers")
    n = 0
    for name in MAPPING:
        a, b = os.path.join(HERE, name), os.path.join(ctrl_dir, name)
        if os.path.isfile(a) and not same(a, b):
            try:
                os.makedirs(ctrl_dir, exist_ok=True)
                shutil.copyfile(a, b)
                n += 1
            except OSError as e:
                log(f"Mapping nicht kopiert ({e})")
    if n:
        log(f"Mapping Light-Butler Bridge in {ctrl_dir} gelegt")
    return n


def live_copy(src, data, stop):
    """Lesekopie fuer den Abgleich Mixxx/Stick, jede Minute (wie die Schleife in launch.sh)."""
    while not stop.wait(0 if not os.path.exists(os.path.join(data, "mixxxdb.live.sqlite")) else LIVE_EVERY_S):
        for x in ("", "-wal"):
            dst = os.path.join(data, "mixxxdb.live.sqlite" + x)
            if os.path.isfile(src + x):
                try:
                    shutil.copyfile(src + x, dst + ".neu")
                    os.replace(dst + ".neu", dst)
                except OSError:
                    pass
            elif os.path.exists(dst):
                os.remove(dst)


def main():
    data, logs = data_dir(), log_dir()
    os.makedirs(data, exist_ok=True)
    os.makedirs(logs, exist_ok=True)
    lf = open(os.path.join(logs, "launcher.log"), "a", encoding="utf-8")

    def log(m):
        lf.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
        lf.flush()

    log("=== Start")
    cfg = load_config(data)
    if mixxx_running():
        dialog("Mixxx laeuft schon. Bitte Mixxx beenden und Light-Butler Mixxx danach starten "
               "(die Bruecke braucht einen frischen Start von Mixxx).")
        return 0
    if not os.path.isfile(cfg["mixxx_bin"]):
        dialog(f"Mixxx wurde nicht gefunden: {cfg['mixxx_bin']}. Pfad in {os.path.join(data, 'config.json')} (mixxx_bin) anpassen.")
        return 1
    src = mixxx_db()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dbarg = []
    install_mapping(log)
    if os.path.isfile(src):
        backup(src, data, stamp, log)
        prepare(src, data, log, stamp)
        try:
            shutil.copyfile(src, os.path.join(data, "mixxxdb.sqlite.neu"))
            os.replace(os.path.join(data, "mixxxdb.sqlite.neu"), os.path.join(data, "mixxxdb.sqlite"))
            log("Datenbank aktualisiert")
        except OSError:
            log("Datenbank nicht kopierbar, alte Kopie wird genutzt")
    if os.path.isfile(os.path.join(data, "mixxxdb.sqlite")):
        dbarg = ["--db", os.path.join(data, "mixxxdb.sqlite")]
    else:
        log("Mixxx-Datenbank fehlt: nur Lieder aus dem Musikordner")
    stop = threading.Event()
    threading.Thread(target=live_copy, args=(src, data, stop), daemon=True).start()
    nw = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    bridge = [sys.executable, os.path.join(HERE, "mixxx_bridge.py"), "--port", cfg["port"]] + dbarg + \
             ["--analysis-dir", os.path.join(data, "analysis"), "--music-root", cfg.get("music_root") or ""]
    if cfg["pi"]:
        bridge += ["--send", cfg["pi"]]
    if str(cfg.get("background_analysis", 1)) == "1":
        bridge.append("--background-analysis")
    mixxx = subprocess.Popen([cfg["mixxx_bin"]])
    log(f"Mixxx gestartet (PID {mixxx.pid})")
    time.sleep(3)                                               # loopMIDI-Anschluss erst nach dem Start von Mixxx oeffnen
    bl = open(os.path.join(logs, "bridge.log"), "a", encoding="utf-8")
    br = subprocess.Popen(bridge, stdout=bl, stderr=subprocess.STDOUT, cwd=HERE, creationflags=nw,
                          env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1"))
    log(f"Bruecke gestartet (PID {br.pid})")
    mixxx.wait()
    stop.set()
    br.terminate()
    try:
        br.wait(10)
    except subprocess.TimeoutExpired:
        br.kill()
    log("=== Ende")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                           # noqa: BLE001
        import traceback
        os.makedirs(log_dir(), exist_ok=True)
        with open(os.path.join(log_dir(), "launcher.log"), "a", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        dialog("Light-Butler Mixxx: Fehler beim Start, siehe launcher.log in " + log_dir())
        sys.exit(1)
