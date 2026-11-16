"""
convert_mp3.py - Lied der Musik-Datenbank, das keine MP3 ist (MP4, M4A, WAV ...), auf Knopfdruck in eine MP3 umwandeln
(Wunsch von Markus, 07.11.2026).

Mit ffmpeg (Homebrew: brew install ffmpeg), 320 kbit/s, Titel, Interpret und weitere Angaben sowie das Cover aus der
Quelle (ID3v2.3). Die MP3 kommt mit demselben Namen in denselben Ordner, das Original bleibt liegen. Es wird nie eine
vorhandene Datei ueberschrieben: Gibt es die MP3 schon, passiert nichts. Geschrieben wird erst in eine versteckte Hilfsdatei
im selben Ordner, die erst am Ende den richtigen Namen bekommt (kein halbes Lied bei einem Abbruch).

Eine MP4 mit echtem Video: Das Video kommt nicht mit, nur ein Cover-Bild (JPEG/PNG, von ffprobe gesucht). Geht das Bild
nicht, kommt nur der Ton (zweiter Versuch ohne Bild).
Aufs Licht wirkt das nicht. Danach findet die Bruecke die neue Datei im Musikordner (Quelle "Ordner"), in Mixxx erscheint
sie erst nach dem Einlesen der Bibliothek dort.
"""
import os
import shutil
import subprocess
import threading
import time

SOURCE_EXT = (".mp4", ".m4a", ".wav", ".aif", ".aiff", ".flac", ".aac", ".ogg")
BITRATE = "320k"
FFMPEG_PATHS = ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")
TIMEOUT_S = 1800


class ConvertError(Exception):
    pass


def find_ffmpeg():
    """Pfad zu ffmpeg oder '' (die App startet ohne die Homebrew-Pfade im PATH)."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    return next((x for x in FFMPEG_PATHS if os.path.isfile(x) and os.access(x, os.X_OK)), "")


def can_convert(path):
    return os.path.splitext(path)[1].lower() in SOURCE_EXT


def target_for(src):
    """Gleicher Ordner, gleicher Name, Endung .mp3."""
    return os.path.splitext(src)[0] + ".mp3"


def cover_stream(ffmpeg, src, run=subprocess.run):
    """Nummer des Bild-Stroms der Quelle (JPEG oder PNG, Cover bevorzugt), None = keins. Ein echtes Video (h264 ...) zaehlt nicht."""
    probe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
    if not os.path.isfile(probe):
        return None
    try:
        r = run([probe, "-v", "error", "-select_streams", "v", "-show_entries", "stream=index,codec_name:stream_disposition=attached_pic",
                 "-of", "csv=p=0", src], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    best = None
    for line in (r.stdout or b"").decode("utf-8", "replace").splitlines():
        f = line.strip().split(",")
        if len(f) >= 2 and f[0].isdigit() and f[1] in ("mjpeg", "png"):
            if len(f) >= 3 and f[2] == "1":
                return int(f[0])
            if best is None:
                best = int(f[0])
    return best


def command(ffmpeg, src, out, cover=None):
    """ffmpeg-Aufruf als Liste (nie ueber eine Shell). cover: Nummer des Bild-Stroms der Quelle (cover_stream) oder None."""
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-map", "0:a:0"]
    if cover is not None:
        cmd += ["-map", f"0:{int(cover)}", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
    cmd += ["-map_metadata", "0", "-c:a", "libmp3lame", "-b:a", BITRATE, "-id3v2_version", "3", "-write_id3v1", "1", "-f", "mp3", out]
    return cmd


def convert(src, ffmpeg=None, run=subprocess.run):
    """Wandelt src in eine MP3 daneben um und gibt ihren Pfad zurueck. ConvertError mit Grund auf Deutsch."""
    ffmpeg = ffmpeg if ffmpeg is not None else find_ffmpeg()
    if not ffmpeg:
        raise ConvertError("ffmpeg fehlt am Mac (Terminal: brew install ffmpeg)")
    if not can_convert(src):
        raise ConvertError("diese Dateiart wird nicht umgewandelt")
    if not os.path.isfile(src):
        raise ConvertError("Datei nicht gefunden (Stick eingesteckt?)")
    dst = target_for(src)
    if os.path.exists(dst):
        raise ConvertError("die MP3 gibt es schon: " + os.path.basename(dst))
    tmp = os.path.join(os.path.dirname(src), "." + os.path.basename(dst) + ".lb-tmp")
    err = ""
    try:
        pic = cover_stream(ffmpeg, src, run)
        for cover in ((pic, None) if pic is not None else (None,)):
            r = run(command(ffmpeg, src, tmp, cover), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=TIMEOUT_S)
            if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 1024:
                break
            err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or ["unbekannter Fehler"]
            err = err[0][:200]
            if os.path.exists(tmp):
                os.remove(tmp)
        else:
            raise ConvertError("ffmpeg: " + err)
        if os.path.exists(dst):                               # inzwischen von woanders angelegt: nicht ueberschreiben
            raise ConvertError("die MP3 gibt es schon: " + os.path.basename(dst))
        os.replace(tmp, dst)
    except subprocess.TimeoutExpired:
        raise ConvertError("Umwandeln dauerte zu lange") from None
    except OSError as e:
        raise ConvertError(f"Datei nicht schreibbar: {e}") from None
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dst


def add_tags(dst, tags):
    """Angaben aus Mixxx zur Quelle in die neue MP3 (Fehlerbericht 07.11.2026: BPM und Tonart fehlten nach dem Umwandeln,
    weil sie bei der MP4 nur in Mixxx standen). Nur in leere Felder, nichts aus der Quelle wird ueberschrieben. Rueckgabe: gesetzte Felder."""
    import tag_edit as te
    have = te.read_tags(dst)["fields"]
    want = {k: str(v).strip() for k, v in tags.items() if k in have and str(v or "").strip()}
    put = {k: v for k, v in want.items() if not have.get(k)}
    if put:
        te.write_tags(dst, put)
    return put


class Jobs:
    """Umwandlungen im Hintergrund, eine nach der anderen. status(p) fuer die Musik-Datenbank (sie fragt nach)."""

    def __init__(self, log=None, done=None, convert_fn=convert):
        self.log, self.done, self.convert_fn = log or (lambda t: None), done or (lambda src, dst: None), convert_fn
        self.lock = threading.Lock()
        self.state = {}                                       # Pfad in Mixxx -> {"state": "wait"|"run"|"ok"|"err", ...}
        self.queue, self.thread = [], None

    def start(self, p, src, tags=None):
        """tags: Angaben aus Mixxx zur Quelle (Titel, Interpret, Genre, BPM, Tonart, Kommentar), kommen in leere Felder der MP3."""
        with self.lock:
            st = self.state.get(p)
            if st and st["state"] in ("wait", "run"):
                return dict(st)
            self.state[p] = {"state": "wait", "t": time.time()}
            self.queue.append((p, src, dict(tags or {})))
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, name="mp3-umwandeln", daemon=True)
                self.thread.start()
            return dict(self.state[p])

    def status(self, p):
        with self.lock:
            return dict(self.state.get(p) or {"state": ""})

    def _run(self):
        while True:
            with self.lock:
                if not self.queue:
                    return
                p, src, tags = self.queue.pop(0)
                self.state[p] = {"state": "run", "t": time.time()}
            try:
                dst = self.convert_fn(src)
                res = {"state": "ok", "out": dst, "name": os.path.basename(dst)}
                self.log(f"MP3 umgewandelt: {dst}")
                if tags:
                    try:
                        res["tags"] = sorted(add_tags(dst, tags))
                    except Exception as e:                     # noqa: BLE001  die MP3 ist da, nur die Angaben fehlen
                        self.log(f"Angaben aus Mixxx nicht geschrieben ({dst}): {e}")
                try:
                    self.done(src, dst)
                except Exception:                              # noqa: BLE001  Nacharbeit (Ordner neu einlesen) darf nicht stoeren
                    pass
            except ConvertError as e:
                res = {"state": "err", "error": str(e)}
                self.log(f"MP3 umwandeln ging nicht ({src}): {e}")
            except Exception as e:                             # noqa: BLE001
                res = {"state": "err", "error": f"unerwartet: {str(e)[:150]}"}
            with self.lock:
                self.state[p] = dict(res, t=time.time())
