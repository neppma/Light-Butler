"""Stick auswerfen aus dem Panel (Wunsch 10.11.2026): der Musik-Stick liess sich am Mac oft nicht auswerfen, solange der Helfer
oder die Mixxx-Bruecke im Hintergrund darauf las (Tags, Pruefung, Doppelte, Schaetzungen, Kurven-Sicherung ...).

Ablauf (Eject.run, eigener Thread): Sperre setzen (Datei ~/Light-Butler-Daten/stick_sperre.json, damit sich Helfer UND Bruecke daran
halten), alle Hintergrundarbeiten hoeren nach der laufenden Datei auf (held()), warten, bis keiner der eigenen Prozesse mehr eine
Datei auf dem Laufwerk offen hat (lsof, hoechstens WAIT_S), dann "diskutil eject". Klappt es nicht, sagt macOS, welcher Prozess
blockiert (zum Beispiel Mixxx); die Sperre geht dann wieder weg. Klappt es, bleibt sie, bis der Stick wieder angesteckt ist
(watch: alle paar Sekunden, ob das Laufwerk wieder da ist).
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

FILE = "stick_sperre.json"
WAIT_S = 60.0
_cache = {"t": 0.0, "v": None}


def data_path():
    return os.path.join(_pfad.daten(), FILE)


def win_removable(root):
    """Windows: ist root (z. B. "E:\\") ein Wechsellaufwerk (USB-Stick, Speicherkarte)?"""
    try:
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(str(root)) == 2       # DRIVE_REMOVABLE
    except (AttributeError, OSError):
        return False


def volume_of(path, platform=None, removable=win_removable):
    """/Volumes/USB STICK/musik -> /Volumes/USB STICK (sonst ""). Windows (15.11.2026): E:\\musik -> E:\\, nur bei einem
    Wechsellaufwerk (Festplatten wirft der Light-Butler nicht aus)."""
    m = re.match(r"^([A-Za-z]):[\\/]", str(path or ""))
    if (platform or sys.platform) == "win32" and m:     # Mac-Pfade (/Volumes/...) gelten auch unter Windows (Tests)
        root = m.group(1).upper() + ":\\"
        return root if removable(root) else ""
    parts = [x for x in str(path or "").split("/") if x]
    return "/" + "/".join(parts[:2]) if len(parts) >= 2 and parts[0] == "Volumes" else ""


def _under(p, vol):
    """Liegt p auf vol? Mac: /Volumes/X/..., Windows: E:\\... (vol endet dort schon mit dem Trenner)."""
    if p == vol or p.rstrip("\\/") == vol.rstrip("\\/"):
        return True
    pre = vol if vol.endswith(("/", "\\")) else vol + "/"
    return p.startswith(pre) or (pre.endswith("\\") and p.upper().startswith(pre.upper()))


def eject_cmd(vol, platform=None):
    """Befehl zum Auswerfen. Windows: ueber den Explorer ("Auswerfen" im Rechtsklick-Menue), nur fuer "X:\\"."""
    if (platform or sys.platform) == "win32" and re.match(r"^[A-Z]:\\$", vol):   # nur echte Laufwerke (volume_of: "E:\")
        ps ="(New-Object -ComObject Shell.Application).Namespace(17).ParseName('%s').InvokeVerb('Eject'); Start-Sleep 3" % vol[:2]
        return ["powershell", "-NoProfile", "-Command", ps]
    return ["/usr/sbin/diskutil", "eject", vol]


def state():
    """Inhalt der Sperrdatei ({vol, t, ejected}) oder None; fuer held() eine Sekunde zwischengespeichert."""
    now = time.time()
    if now - _cache["t"] < 1.0:
        return _cache["v"]
    try:
        with open(data_path(), encoding="utf-8") as f:
            v = json.load(f)
        v = v if isinstance(v, dict) and v.get("vol") else None
    except (OSError, ValueError):
        v = None
    _cache.update(t=now, v=v)
    return v


def held(path=None):
    """Ist der Stick gesperrt (wird ausgeworfen oder ist ausgeworfen)? Mit path: nur, wenn path auf diesem Laufwerk liegt."""
    v = state()
    if not v:
        return False
    if path is None:
        return True
    return _under(str(path), v["vol"])


def _write(v):
    p = data_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if v is None:
        try:
            os.remove(p)
        except OSError:
            pass
    else:
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(v, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)
    _cache.update(t=0.0, v=None)


def tick(now=None):
    """Alle paar Sekunden (Bruecke und Helfer): Stick wieder angesteckt -> Sperre weg; haengengebliebene Sperre (Auswerfen
    abgebrochen, Programm beendet) nach 10 Minuten weg."""
    v = state()
    if not v:
        return False
    now = time.time() if now is None else now
    if (v.get("ejected") and os.path.isdir(v["vol"])) or (not v.get("ejected") and now - float(v.get("t") or 0) > 600.0):
        release()
        return True
    return False


def moved(root):
    """Musikordner liegt jetzt auf einem anderen, angesteckten Laufwerk (Wunsch 12.11.2026: alter Stick ausgeworfen, Ersatzstick
    als Musikordner eingetragen): die Sperre des ausgeworfenen Sticks gilt nicht mehr. True, wenn sie weg ist."""
    v = state()
    nv = volume_of(root)
    if v and v.get("ejected") and nv and nv != v["vol"] and os.path.isdir(nv):
        release()
        return True
    return False


def hold(vol, ejected=False, by=""):
    """Sperren. by: wer sperrt (Spiegeln auf den Stick schreibt "spiegeln" und frischt die Zeit auf, solange es laeuft)."""
    v = {"vol": vol, "t": time.time(), "ejected": bool(ejected)}
    if by:
        v["by"] = by
    _write(v)


def mine(by):
    """Haelt by die Sperre (und niemand anderer, etwa das Auswerfen)?"""
    v = state()
    return bool(v) and v.get("by") == by


def release():
    _write(None)


def tree_pids(root_pid=None):
    """Eigener Prozess und alle Kinder (Messungen, Analyse)."""
    pids, todo = [], [root_pid or os.getpid()]
    while todo:
        p = todo.pop()
        pids.append(p)
        try:
            out = subprocess.run(["/usr/bin/pgrep", "-P", str(p)], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        todo += [int(x) for x in out.split() if x.isdigit()]
    return pids


def open_files(vol, pids, run=subprocess.run):
    """Dateien auf vol, die einer dieser Prozesse offen hat (lsof)."""
    try:
        out = run(["/usr/sbin/lsof", "-Fn", "-p", ",".join(str(p) for p in pids)], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pre = vol.rstrip("/") + "/"
    return [ln[1:] for ln in out.splitlines() if ln.startswith("n") and (ln[1:] == vol or ln[1:].startswith(pre))]


def blocker(text, run=subprocess.run):
    """Aus der Meldung von diskutil den blockierenden Prozess lesen: "Mixxx (PID 123)" oder ""."""
    m = re.search(r"dissented by PID (\d+)", text or "")
    if not m:
        return ""
    pid = m.group(1)
    try:
        name = run(["/bin/ps", "-p", pid, "-o", "comm="], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    return (os.path.basename(name) or "unbekannt") + f" (PID {pid})"


class Eject:
    """Ein Auswerfen zur Zeit; status() fuer das Panel."""

    def __init__(self, log=None, run=subprocess.run, wait_s=WAIT_S, sleep=time.sleep, pids=tree_pids):
        self.log, self.run_cmd, self.wait_s, self.sleep, self.pids = log or (lambda t: None), run, wait_s, sleep, pids
        self.lock = threading.Lock()
        self.st = {"state": "idle"}
        self.thread = None
        self.watcher = None

    def status(self):
        with self.lock:
            st = dict(self.st)
        v = state()
        st["held"] = bool(v)
        if v and v.get("ejected") and os.path.isdir(v["vol"]):
            release()                                          # wieder angesteckt: weiterarbeiten
            st["held"] = False
        return st

    def start(self, root, vol=None):
        """root: Musikordner. vol (Wunsch 12.11.2026, Seite Spiegeln): ein anderes Laufwerk unter /Volumes auswerfen, etwa den
        Ersatzstick; dann ohne Sperre (die gilt nur fuer den Musik-Stick, an dem Helfer und Bruecke arbeiten)."""
        mvol = volume_of(root)
        win = sys.platform == "win32" and bool(re.match(r"^[A-Za-z]:[\\/]", str(vol or root or "")))
        if vol:
            want = volume_of(vol) if win else str(vol).rstrip("/")
            if not want or volume_of(vol) != want:
                raise ValueError("Nur Wechsellaufwerke (USB-Stick) lassen sich auswerfen" if win
                                 else "Nur Laufwerke unter /Volumes lassen sich auswerfen")
            vol = want
        else:
            vol = mvol
        if not vol:
            raise ValueError("Der Musikordner liegt auf keinem Wechsellaufwerk (USB-Stick)" if win
                             else "Der Musikordner liegt auf keinem auswerfbaren Laufwerk (/Volumes/…)")
        if not os.path.isdir(vol):
            raise ValueError("Der Stick ist nicht angesteckt")
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return dict(self.st)
            music = vol == mvol
            self.st = {"state": "wait", "vol": vol, "music": music, "t": time.time(), "open": 0}
            self.thread = threading.Thread(target=self._run, args=(vol, music), name="stick-auswerfen", daemon=True)
            self.thread.start()
            return dict(self.st)

    def _set(self, **kw):
        with self.lock:
            self.st.update(kw)

    def _run(self, vol, music=True):
        if music:
            hold(vol)
        self.log(f"Stick auswerfen: {vol}" + (", Hintergrundarbeiten halten an" if music else ""))
        t0 = time.time()
        files = []
        while True:
            files = open_files(vol, self.pids(), self.run_cmd)
            self._set(open=len(files), files=[os.path.basename(f) for f in files[:5]])
            if not files or time.time() - t0 > self.wait_s:
                break
            self.sleep(1.0)
        self._set(state="eject")
        try:
            r = self.run_cmd(eject_cmd(vol), capture_output=True, text=True, timeout=60)
            ok, text = r.returncode == 0, (r.stdout or "") + (r.stderr or "")
            if ok and sys.platform == "win32" and re.match(r"^[A-Z]:\\$", vol) and os.path.isdir(vol):   # Explorer meldet nichts: weg?
                ok, text = False, "Windows hat den Stick nicht ausgeworfen (eine Datei darauf ist noch offen?)"
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            ok, text = False, str(e)
        if ok:
            if music:
                hold(vol, ejected=True)
            self._set(state="ok", t1=time.time())
            self.log(f"Stick ausgeworfen: {vol}")
            return
        who = blocker(text, self.run_cmd)
        if music:
            release()
        msg = f"{who} hält den Stick" if who else (text.strip().splitlines() or ["Auswerfen ging nicht"])[-1][:200]
        if "mixxx" in who.lower():
            msg += ": Mixxx beenden und noch einmal tippen"
        elif files:
            msg += f" (noch offen: {', '.join(os.path.basename(f) for f in files[:3])})"
        self._set(state="err", error=msg)
        self.log(f"Stick auswerfen ging nicht: {msg}")
