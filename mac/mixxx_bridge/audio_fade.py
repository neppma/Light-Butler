"""Fade-in und Fade-out in MP3s (Wunsch 11.11.2026): am Anfang ueber X Sekunden von 0 auf 100 %, am Ende ueber Y Sekunden
von 100 auf 0 %. Einzeln aus dem Tag-Fenster (Wellenform) oder als Sammelauftrag aus der Musik-Datenbank (Gruppe, gefilterte
Liste). ffmpeg aus Homebrew (wie convert_mp3, vom Nutzer erlaubt 07.11.2026).
Dazu Beschneiden (Wunsch 11.11.2026): vorne und hinten ein paar Sekunden weg, alles in einem Durchgang (atrim, dann afade),
der Ton wird nur einmal neu kodiert. Reihenfolge: vorne weg, Fade-in, Fade-out, hinten weg.

Die Tags bleiben Byte fuer Byte gleich: ffmpeg kodiert nur den Ton neu (320 kbit/s, gleiche Abtastrate, ohne eigene Tags), davor
kommt der ID3v2-Block der Originaldatei, dahinter ihr ID3v1-Teil (Cover, Gruppe, Energie, Importdatum ... unveraendert).
Erst als versteckte Hilfsdatei daneben, dann kommt das Original in den Papierkorb und die neue Datei bekommt seinen Namen
(Mixxx behaelt Hotcues und Playlists). Ein Auftrag nach dem anderen, anhalten jederzeit (nach dem laufenden Lied).
"""
import os
import subprocess
import threading
import time

MAX_FADE_S = 60.0
MAX_CUT_S = 600.0
MIN_LEFT_S = 5.0          # nach dem Schnitt bleiben mindestens 5 s
TIMEOUT_S = 600


def id3_parts(data):
    """(ID3v2-Block, Ende des Tons, ID3v1-Teil) einer MP3 als Bytes."""
    start = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        start = 10 + size + (10 if data[5] & 0x10 else 0)
    v1 = data[-128:] if len(data) >= 128 and data[-128:-125] == b"TAG" else b""
    return data[:start], v1


def strip_tags(data):
    """Nur der Ton (ohne ID3v2 vorne und ID3v1 hinten)."""
    head, v1 = id3_parts(data)
    return data[len(head):len(data) - len(v1)] if v1 else data[len(head):]


def af_filter(fin, fout, dur, ca=0.0, cb=0.0):
    """Filter fuer ffmpeg: zuerst schneiden (Zeiten danach ab 0), dann Fade-in ab dem neuen Anfang, Fade-out bis zum neuen Ende."""
    parts = []
    if ca > 0 or cb > 0:
        trim = f"atrim=start={ca:.3f}" + (f":end={dur - cb:.3f}" if cb > 0 else "")
        parts += [trim, "asetpts=PTS-STARTPTS"]
    left = dur - ca - cb
    if fin > 0:
        parts.append(f"afade=t=in:st=0:d={fin:.3f}")
    if fout > 0:
        parts.append(f"afade=t=out:st={max(0.0, left - fout):.3f}:d={fout:.3f}")
    return ",".join(parts)


def command(ffmpeg, src, out, fin, fout, dur, ca=0.0, cb=0.0):
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-map", "0:a:0", "-af", af_filter(fin, fout, dur, ca, cb),
            "-c:a", "libmp3lame", "-b:a", "320k", "-map_metadata", "-1", "-id3v2_version", "0", "-write_id3v1", "0", "-f", "mp3", out]


def check_values(fin, fout, dur, ca=0, cb=0):
    """(fin, fout, vorne weg, hinten weg) gerundet, sonst ValueError. dur 0 = Laenge noch unbekannt (Sammelauftrag)."""
    try:
        fin, fout, ca, cb = float(fin or 0), float(fout or 0), float(ca or 0), float(cb or 0)
    except (TypeError, ValueError):
        raise ValueError("Sekunden bitte als Zahl") from None
    if fin < 0 or fout < 0 or fin > MAX_FADE_S or fout > MAX_FADE_S:
        raise ValueError(f"Fade hoechstens {int(MAX_FADE_S)} Sekunden")
    if ca < 0 or cb < 0 or ca > MAX_CUT_S or cb > MAX_CUT_S:
        raise ValueError(f"Abschneiden hoechstens {int(MAX_CUT_S)} Sekunden")
    if fin == 0 and fout == 0 and ca == 0 and cb == 0:
        raise ValueError("Weder Fade noch Abschneiden gewaehlt")
    if dur:
        left = dur - ca - cb
        if left < MIN_LEFT_S:
            raise ValueError(f"Nach dem Abschneiden bliebe weniger als {int(MIN_LEFT_S)} s uebrig")
        if fin + fout >= left:
            raise ValueError("Fade-in und Fade-out zusammen laenger als das (beschnittene) Lied")
    return round(fin, 2), round(fout, 2), round(ca, 2), round(cb, 2)


def fade_file(src, fin, fout, dur, ffmpeg, trash, run=subprocess.run, ca=0.0, cb=0.0):
    """Eine MP3 bearbeiten (ca/cb: vorne/hinten abschneiden, Sekunden). Rueckgabe: Pfad der neuen Datei (gleicher Name). ValueError mit Grund."""
    if not src.lower().endswith(".mp3"):
        raise ValueError("nur MP3")
    if not os.path.isfile(src):
        raise ValueError("Datei nicht gefunden")
    try:                                                     # Laenge aus der Datei (genauer als die Liste)
        import folder_lib
        dur = float(folder_lib.read_mp3(src).get("duration") or 0) or dur
    except Exception:                                        # noqa: BLE001
        pass
    if (float(ca or 0) or float(cb or 0)) and not dur:
        raise ValueError("Laenge der Datei unbekannt, Abschneiden geht nicht")
    fin, fout, ca, cb = check_values(fin, fout, dur, ca, cb)
    d, name = os.path.split(src)
    tmp_audio = os.path.join(d, "." + name + ".lb-fade")
    tmp_out = os.path.join(d, "." + name + ".lb-tmp")
    try:
        r = run(command(ffmpeg, src, tmp_audio, fin, fout, dur, ca, cb), capture_output=True, timeout=TIMEOUT_S)
        if r.returncode != 0 or not os.path.isfile(tmp_audio) or os.path.getsize(tmp_audio) < 1024:
            err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or ["unbekannter Fehler"]
            raise ValueError("ffmpeg: " + err[0][:200])
        with open(src, "rb") as f:
            orig = f.read()
        head, v1 = id3_parts(orig)
        with open(tmp_audio, "rb") as f:
            audio = strip_tags(f.read())
        with open(tmp_out, "wb") as f:
            f.write(head + audio + v1)
        if trash([src]):
            raise ValueError("Original liess sich nicht in den Papierkorb legen")
        os.replace(tmp_out, src)
    except subprocess.TimeoutExpired:
        raise ValueError("dauerte zu lange") from None
    finally:
        for p in (tmp_audio, tmp_out):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
    try:
        import changed_log                                   # Mixxx: Lied neu analysieren lassen (Liste "geaenderte Tags")
        changed_log.note(src)
    except Exception:                                        # noqa: BLE001
        pass
    return src


class Jobs:
    """Sammelauftrag: eine Datei nach der anderen. status() fuer das Panel."""

    def __init__(self, ffmpeg_fn=None, trash=None, log=None, done=None, run=subprocess.run):
        if ffmpeg_fn is None:
            from convert_mp3 import find_ffmpeg as ffmpeg_fn
        if trash is None:
            from file_check import to_trash_many as trash
        self.ffmpeg_fn, self.trash, self.log, self.done_cb, self.run = ffmpeg_fn, trash, log or (lambda t: None), done, run
        self.lock = threading.Lock()
        self.st = {"state": "idle"}
        self.stop_ev = threading.Event()
        self.thread = None

    def status(self):
        with self.lock:
            return dict(self.st, errors=list(self.st.get("errors") or [])[:30])

    def stop(self):
        self.stop_ev.set()
        return self.status()

    def start(self, files, fin, fout, ca=0, cb=0):
        """files: [(Pfad in der Bibliothek, Datei am Mac, Laenge in s)]; ca/cb: vorne/hinten abschneiden."""
        ff = self.ffmpeg_fn()
        if not ff:
            raise ValueError("ffmpeg fehlt am Mac (Terminal: brew install ffmpeg)")
        fin, fout, ca, cb = check_values(fin, fout, 0, ca, cb)
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                raise ValueError("Es laeuft schon ein Fade-Auftrag")
            files = [f for f in files if str(f[1]).lower().endswith(".mp3")]
            if not files:
                raise ValueError("Keine MP3s in der Auswahl")
            self.stop_ev.clear()
            self.st = {"state": "run", "total": len(files), "done": 0, "ok": 0, "errors": [], "cur": "", "fin": fin, "fout": fout, "ca": ca, "cb": cb, "t0": time.time()}
            self.thread = threading.Thread(target=self._run, args=(files, fin, fout, ff, ca, cb), name="fade", daemon=True)
            self.thread.start()
            return dict(self.st)

    def _run(self, files, fin, fout, ff, ca=0.0, cb=0.0):
        import stick_hold
        for p, f, dur in files:
            if self.stop_ev.is_set() or stick_hold.held(f):
                with self.lock:
                    self.st.update(state="stopped", cur="")
                return
            with self.lock:
                self.st["cur"] = os.path.basename(f)
            try:
                fade_file(f, fin, fout, float(dur or 0), ff, self.trash, self.run, ca, cb)
                with self.lock:
                    self.st["ok"] += 1
                if self.done_cb is not None:
                    try:
                        self.done_cb(p, f)
                    except Exception:                        # noqa: BLE001
                        pass
            except (ValueError, OSError) as e:
                with self.lock:
                    self.st["errors"].append(f"{os.path.basename(f)}: {e}")
            with self.lock:
                self.st["done"] += 1
        with self.lock:
            self.st.update(state="ok", cur="", t1=time.time())
        self.log(f"Fade: {self.st['ok']} Lieder bearbeitet (in {fin} s, aus {fout} s, vorne weg {ca} s, hinten weg {cb} s)")
