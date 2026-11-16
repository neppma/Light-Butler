#!/usr/bin/env python3
"""
loudness.py - Lautheit jedes Liedes messen (Wunsch von Markus, 11.11.2026: Pegel angleichen).

Gemessen wird wie im Rundfunk und bei Spotify nach EBU R128 (ffmpeg, Filter ebur128): die integrierte Lautheit in LUFS
(wie laut das Lied fuers Ohr wirkt) und der echte Spitzenpegel in dBTP. Die Musik selbst bleibt immer unveraendert.

Verwendet wird das so:
  - Musik-Datenbank: Spalten Lautheit und Spitze, Filter von-bis (Ausreisser finden)
  - Vorhoeren im Panel und Auto-DJ: gleich laut abspielen (core.js SM.loudGain)
  - mit der Einstellung rg_write am Pi (Standard aus): ReplayGain-Angabe in die MP3 (TXXX REPLAYGAIN_TRACK_GAIN/_PEAK,
    Bezug -18 LUFS wie ReplayGain 2.0), dazu TXXX "ReplayGainSource". Nur, wenn in der Datei noch keine ReplayGain-Angabe
    steht (auch kein RVA2): eine vorhandene von einem anderen Programm bleibt, wie sie ist (Wunsch 11.11.2026).

Ergebnis je Pfad in ~/Light-Butler-Daten/lautheit/lautheit.jsonl ({path, v, lufs, tp, rg}; rg = 1: die Datei hatte schon eine
ReplayGain-Angabe beim Messen). Gemessen wird in einem eigenen Prozess mit nice 10, eine Datei nach der anderen.

    python3 loudness.py messen --liste liste.json --aus lautheit.jsonl     (die Bruecke ruft das selbst auf)
Aufs Licht wirkt das nie.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA_DIR = os.path.join(_pfad.daten(), "lautheit")
LOUD_FILE = "lautheit.jsonl"
WRITTEN_FILE = "geschrieben.json"
VERSION = 1
RG_REF_LUFS = -18.0                       # ReplayGain 2.0: Verstaerkung = -18 - Lautheit
RG_DESC = ("replaygain_track_gain", "replaygain_track_peak", "replaygain_album_gain", "replaygain_album_peak")
SRC_DESC = "ReplayGainSource"
SRC_VALUE = "Light-Butler (gemessen)"
TIMEOUT_S = 900
LUFS_RANGE = (-70.0, 5.0)


def parse_ebur128(text):
    """(LUFS, Spitze dBTP) aus der Zusammenfassung von ffmpeg ebur128, None wenn nicht lesbar."""
    i = re.findall(r"^\s*I:\s*(-?[\d.]+|-inf)\s*LUFS", text, re.M)
    p = re.findall(r"^\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS", text, re.M)
    if not i:
        return None
    lufs = float(i[-1].replace("-inf", "-70"))
    tp = float(p[-1].replace("-inf", "-70")) if p else 0.0
    if not LUFS_RANGE[0] < lufs <= LUFS_RANGE[1]:
        return None                                     # Stille (oder Geraeusch unter der Messschwelle)
    return round(lufs, 1), round(tp, 1)


def rg_present(path):
    """Steht schon eine ReplayGain-Angabe in der MP3? (True/False, unsere eigene?)"""
    import id3_tags as it
    if not path.lower().endswith(".mp3"):
        return False, False
    r = it.read(path)
    if isinstance(r, str):
        return False, False
    frames = r[2]
    has = any((fid == b"TXXX" and it.txxx_desc(body) in RG_DESC) or fid == b"RVA2" for fid, fl, _raw, body in frames)
    ours = any(fid == b"TXXX" and it.txxx_desc(body) == SRC_DESC.lower() for fid, fl, _raw, body in frames)
    return has, ours


def measure_one(r, ffmpeg, run=subprocess.run):
    """{path, file} -> {path, v, lufs, tp, rg} oder {path, v, err}."""
    f = r.get("file") or r["path"]
    out = {"path": r["path"], "v": VERSION}
    try:
        has, ours = rg_present(f)
        out["rg"] = 1 if has and not ours else 0
        p = run([ffmpeg, "-hide_banner", "-nostats", "-i", f, "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                capture_output=True, timeout=TIMEOUT_S)
        res = parse_ebur128((p.stderr or b"").decode("utf-8", "replace"))
        if res is None:
            out["err"] = "nicht messbar"
        else:
            out["lufs"], out["tp"] = res
    except subprocess.TimeoutExpired:
        out["err"] = "dauerte zu lange"
    except Exception as e:                                   # noqa: BLE001  unlesbar: merken, nicht wieder versuchen
        out["err"] = str(e)[:120]
    return out


def cmd_measure(a):
    from prio import lower_priority                    # Mac: os.nice(10); Windows: "Niedriger als normal"
    lower_priority(10)
    with open(a.liste, encoding="utf-8") as f:
        songs = json.load(f)
    with open(a.aus, "a", encoding="utf-8") as out:
        for r in songs:
            p = r.get("file") or r["path"]
            parts = p.split(os.sep)
            while p.startswith("/Volumes/") and len(parts) > 2 and not os.path.exists(os.sep.join(parts[:3])):
                time.sleep(60)                               # NAS oder Stick nicht verbunden: warten
            out.write(json.dumps(measure_one(r, a.ffmpeg), ensure_ascii=False) + "\n")
            out.flush()
            time.sleep(0.2)


def write_rg_tag(path, lufs, tp):
    """ReplayGain-Angabe in die MP3 (TXXX REPLAYGAIN_TRACK_GAIN "-3.20 dB", REPLAYGAIN_TRACK_PEAK linear, dazu ReplayGainSource).
    Nie ueber eine vorhandene Angabe, ausser es ist unsere eigene. Rueckgabe: "ok", "gleich", "vorhanden" oder ein Grund."""
    import id3_tags as it
    if not path.lower().endswith(".mp3"):
        return "keine MP3"
    try:
        lufs, tp = float(lufs), float(tp)
    except (TypeError, ValueError):
        return "Wert ungueltig"
    if not LUFS_RANGE[0] < lufs <= LUFS_RANGE[1]:
        return "Wert ungueltig"
    r = it.read(path)
    if isinstance(r, str):
        return r
    ver, old_size, frames = r
    ours = any(fid == b"TXXX" and it.txxx_desc(body) == SRC_DESC.lower() for fid, fl, _raw, body in frames)
    rg = [(fid, body) for fid, fl, _raw, body in frames if (fid == b"TXXX" and it.txxx_desc(body) in RG_DESC) or fid == b"RVA2"]
    if rg and not ours:
        return "vorhanden"
    gain = f"{RG_REF_LUFS - lufs:+.2f} dB"
    peak = f"{10 ** (tp / 20.0):.6f}"
    if ours and any(fid == b"TXXX" and it.txxx_desc(b) == "replaygain_track_gain" and _txxx_value(b) == gain for fid, b in rg):
        return "gleich"
    keep = [raw for fid, fl, raw, body in frames
            if not (fid == b"TXXX" and (it.txxx_desc(body) in RG_DESC or it.txxx_desc(body) == SRC_DESC.lower()))]
    it.write(path, ver, old_size, b"".join(keep)
             + it.frame(b"TXXX", it.txxx_body("REPLAYGAIN_TRACK_GAIN", gain), ver)
             + it.frame(b"TXXX", it.txxx_body("REPLAYGAIN_TRACK_PEAK", peak), ver)
             + it.frame(b"TXXX", it.txxx_body(SRC_DESC, SRC_VALUE), ver))
    return "ok"


def _txxx_value(body):
    import id3_tags as it
    enc = body[0] if body else 0
    rest = it._split0(enc, body[1:])[1]
    return it._decode(enc, it._split0(enc, rest)[0]).strip()


class Loudness:
    """Lautheit je Pfad. get(path) -> (LUFS, Spitze dBTP, rg) oder None; rg 1 = ReplayGain von einem anderen Programm in der
    Datei, 2 = von uns geschrieben. start() misst neue Lieder in einem eigenen Prozess, refresh() liest nach, write_tick()
    schreibt mit der Einstellung rg_write die ReplayGain-Angabe (nur in Dateien ohne)."""

    def __init__(self, base=DATA_DIR, log=None, ffmpeg_fn=None):
        if ffmpeg_fn is None:
            from convert_mp3 import find_ffmpeg as ffmpeg_fn
        self.base, self.log, self.ffmpeg_fn = base, log or (lambda t: None), ffmpeg_fn
        self.path = os.path.join(base, LOUD_FILE)
        self.written_path = os.path.join(base, WRITTEN_FILE)
        self.vals, self.pos, self.proc, self.writer = {}, 0, None, None
        self.stop_ev = threading.Event()
        try:
            with open(self.written_path, encoding="utf-8") as f:
                self.written = {str(k): v for k, v in dict(json.load(f)).items()}
        except (OSError, ValueError, TypeError):
            self.written = {}
        self.refresh()

    def refresh(self):
        """Neue Zeilen lesen. True = neue Werte."""
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                raw = f.read()
        except OSError:
            return False
        end = raw.rfind(b"\n") + 1
        self.pos += end
        new = False
        for line in raw[:end].decode("utf-8", "replace").splitlines():
            try:
                r = json.loads(line)
                p = str(r["path"])
                v = (float(r["lufs"]), float(r.get("tp") or 0), int(r.get("rg") or 0)) if "lufs" in r else None
            except (ValueError, KeyError, TypeError):
                continue
            self.vals[p] = v
            new = new or v is not None
        return new

    def get(self, path):
        v = self.vals.get(path)
        if v is None:
            return None
        rg = v[2] or (2 if self.written.get(path) == "ok" else 0)
        return v[0], v[1], rg

    def stop(self, wait_s=5.0):
        self.stop_ev.set()
        if self.running():
            try:
                self.proc.terminate()
            except OSError:
                pass
        if self.writer is not None and self.writer.is_alive():
            self.writer.join(wait_s)

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, songs):
        """songs: [{path, file}]. Misst die noch nicht gemessenen in einem eigenen Prozess (ohne ffmpeg: nichts)."""
        if self.running():
            return 0
        todo = [{"path": s["path"], "file": s.get("file") or s["path"]} for s in songs if s.get("path") and s["path"] not in self.vals]
        if not todo:
            return 0
        ff = self.ffmpeg_fn()
        if not ff:
            return 0
        os.makedirs(self.base, exist_ok=True)
        fd, lst = tempfile.mkstemp(prefix="lautheit_", suffix=".json", dir=self.base)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(todo, f, ensure_ascii=False)
        self.proc = subprocess.Popen([sys.executable, os.path.join(HERE, "loudness.py"), "messen", "--liste", lst, "--aus", self.path,
                                      "--ffmpeg", ff], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log(f"Lautheit: {len(todo)} Lieder werden gemessen")
        return len(todo)

    def _save_written(self):
        tmp = self.written_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.written, f, ensure_ascii=False)
        os.replace(tmp, self.written_path)

    def write_tick(self, songs, busy=lambda p: False, gap_s=0.3):
        """ReplayGain-Angabe in MP3s ohne eine (eigener Thread, je Lied einmal). songs: [(Pfad in Mixxx, Datei am Mac)]."""
        if self.writer is not None and self.writer.is_alive():
            return
        todo = []
        for p, f in songs:
            v = self.vals.get(p)
            if v is None or v[2] or p in self.written or not f.lower().endswith(".mp3"):
                continue
            todo.append((p, f, v[0], v[1]))
        if not todo:
            return

        def run():
            n = 0
            for p, f, lufs, tp in todo:
                if self.stop_ev.is_set():
                    break
                import stick_hold
                if stick_hold.held():                     # Stick wird ausgeworfen: aufhoeren
                    break
                if busy(p) or not os.path.exists(f):
                    continue
                try:
                    res = write_rg_tag(f, lufs, tp)
                except OSError as e:
                    res = f"Fehler: {e}"
                self.written[p] = "ok" if res in ("ok", "gleich") else res[:60]
                n += res == "ok"
                time.sleep(gap_s)
            self._save_written()
            if n:
                self.log(f"Lautheit: ReplayGain in {n} MP3s geschrieben")
        self.writer = threading.Thread(target=run, name="lautheit-schreiben", daemon=True)
        self.writer.start()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lautheit (EBU R128) der Lieder messen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("messen")
    m.add_argument("--liste", required=True)
    m.add_argument("--aus", required=True)
    m.add_argument("--ffmpeg", required=True)
    a = ap.parse_args(argv)
    try:
        cmd_measure(a)
    finally:
        if os.path.basename(a.liste).startswith("lautheit_"):
            try:
                os.remove(a.liste)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
