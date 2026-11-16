#!/usr/bin/env python3
"""
stems_show.py - rechnet am Mac die Pegelkurven von Stimme, Bass, Kick, Snare/Hi-Hat und Sonstigem fuer Shows des Showmanagers.

Holt die MP3 der Show vom Pi, trennt sie mit Demucs in einem temporaeren Ordner, schickt nur die Kurven zurueck
(shows/_stems/, je MP3 eine Datei: Shows mit derselben MP3 teilen sie sich, sie wird nur einmal gerechnet).
Der temporaere Ordner mit Musik und Spuren ist danach weg. Aufs Licht wirkt das nicht.

Installation einmalig:  bash mac/stems/install_stems.sh
Aufruf:
    ~/s2l-stems/bin/python mac/stems/stems_show.py --liste           Shows und ihr Stand
    ~/s2l-stems/bin/python mac/stems/stems_show.py "Mein Lied"       eine Show
    ~/s2l-stems/bin/python mac/stems/stems_show.py --alle            alle ohne aktuelle Kurven
    ~/s2l-stems/bin/python mac/stems/stems_show.py --watch           Waechter: fragt den Pi jede Minute und rechnet neue Shows
Weitere Schalter: --neu rechnet auch aktuelle Kurven neu, --pi HOST[:PORT] anderes Ziel, --auch-mit-mixxx siehe unten.

Laeuft auch am Windows-PC (Installation: install_stems.ps1, Dateien vom Pi unter /helfer/): dort rechnet Demucs auf der
NVIDIA-Grafikkarte (CUDA), die MP3 wird vorher mit soundfile zu WAV (kein ffmpeg noetig). Mac und PC teilen sich die
Arbeit: vor dem Rechnen meldet der Helfer die MP3 am Pi an (stems_claim), ein anderer Rechner nimmt sie dann nicht.
Am Mac rechnet es rund 1,5-mal so lang wie das Lied und belastet alle Kerne. Solange Mixxx laeuft, startet es deshalb nur mit --auch-mit-mixxx.
Der Waechter (--watch) rechnet auch neben Mixxx (Wunsch von Markus, 06.11.2026); die App "Light-Butler Mixxx" startet ihn mit
(STEMS_AUTO in config.sh), so bekommt jede neu angelegte Show ihre Kurven von selbst.
"""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stem_curves as sc  # noqa: E402

MODEL = "htdemucs"
WIN = sys.platform == "win32"
DEVICE = "auto"         # --device: auto = am Mac die CPU (der Grafikchip des M1 bricht ab), sonst CUDA, wenn vorhanden
MAX_MIN = None         # Kurven nur fuer MP3s bis zu dieser Laenge (Minuten); None = Einstellung am Pi (sm_stems_max_min, 09.11.2026)
OLD_PI_MAX_MIN = 6.0   # aelterer Pi ohne diese Einstellung
WHO = socket.gethostname() or "?"   # so meldet sich dieser Rechner am Pi an (stems_claim)
PI_FILE = os.path.expanduser("~/.light-butler-pi")
STEMS = ("vocals", "bass", "drums", "other")


class Client:
    def __init__(self, host):
        self.base = "http://" + (host if ":" in host else host + ":8080")

    def _url(self, path, name=None):
        return self.base + path + ("?name=" + urllib.parse.quote(name) if name else "")

    def get(self, path, name=None):
        with urllib.request.urlopen(self._url(path, name), timeout=30) as r:
            return json.load(r)

    def download(self, name, dest):
        with urllib.request.urlopen(self._url("/api/sm/audio", name), timeout=60) as r, open(dest, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    return
                f.write(b)

    def op(self, op, **data):
        body = json.dumps(dict(data, op=op)).encode("utf-8")
        req = urllib.request.Request(self._url("/api/sm/cmd"), body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise ValueError(json.load(e).get("error") or str(e))


def pick_device(want=None, platform=sys.platform, cuda=None):
    """cpu oder cuda. Am Mac immer die CPU (auf dem Grafikchip des M1 bricht Demucs ab), sonst CUDA, wenn Torch eine
    NVIDIA-Karte sieht. want = --device (auto, cpu, cuda)."""
    want = want or DEVICE
    if want in ("cpu", "cuda"):
        return want
    if platform == "darwin":
        return "cpu"
    if cuda is None:
        try:
            import torch
            cuda = bool(torch.cuda.is_available())
        except ImportError:
            cuda = False
    return "cuda" if cuda else "cpu"


def tag_range(path):
    """(Anfang, Ende) der reinen Audiodaten einer MP3: ohne ID3v2-Kopf vorn und ID3v1-Anhang hinten (wie audio_fingerprint)."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(10)
        start = 0
        if head[:3] == b"ID3" and len(head) == 10:
            start = 10 + ((head[6] & 0x7F) << 21 | (head[7] & 0x7F) << 14 | (head[8] & 0x7F) << 7 | (head[9] & 0x7F))
            if head[5] & 0x10:
                start += 10
        end = size
        if size >= 128:
            f.seek(size - 128)
            if f.read(3) == b"TAG":
                end -= 128
    return min(start, size), end


def strip_tags(src, dst):
    """Kopie der MP3 ohne Tags. libsndfile scheitert an manchen grossen ID3v2.4-Koepfen (Albumbild) mit
    "Unspecified internal error" (06.11.2026, rund 40 % der Lieder); ohne die Tags liest es sie einwandfrei."""
    a, b = tag_range(src)
    with open(src, "rb") as f, open(dst, "wb") as o:
        f.seek(a)
        left = max(0, b - a)
        while left > 0:
            chunk = f.read(min(1 << 20, left))
            if not chunk:
                break
            o.write(chunk)
            left -= len(chunk)
    return dst


def to_wav(audio, tmp):
    """MP3 -> WAV mit soundfile (libsndfile kann MP3), vorher ohne Tags. Unter Windows fehlt meist ffmpeg, das Demucs sonst
    fuer MP3 braucht."""
    import soundfile as sf
    wav = os.path.join(tmp, "audio.wav")
    try:
        data, sr = sf.read(strip_tags(audio, os.path.join(tmp, "notag.mp3")), dtype="float32", always_2d=True)
    except Exception:                                        # noqa: BLE001  Fehlerbericht 09.11.2026: "Unspecified internal error."
        # MP3 mit beschaedigter Stelle ("Header missing"): libsndfile bricht ab, ffmpeg ueberspringt die Stelle. Nur wenn es
        # ffmpeg gibt, sonst bleibt der Fehler (der Mac rechnet das Lied dann als Reserve, dort liest Demucs mit ffmpeg).
        ff = ffmpeg_path()
        if not ff:
            raise
        r = subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-i", audio, "-vn", "-acodec", "pcm_f32le", wav],
                           capture_output=True, timeout=600)
        if r.returncode != 0 or not os.path.isfile(wav) or os.path.getsize(wav) < 1000:
            raise
        return wav
    sf.write(wav, data, sr, subtype="FLOAT")
    return wav


def ffmpeg_path():
    """ffmpeg, wenn es da ist (Mac: Homebrew; Windows: nur wenn installiert), sonst None."""
    import shutil
    for c in (shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if c and os.path.isfile(c):
            return c
    return None


def demucs_cmd(audio, tmp, device, platform=sys.platform):
    """Aufruf von Demucs. Am Mac mit nice (niedrige Prioritaet); unter Windows regelt das creationflags in demucs()."""
    cmd = [sys.executable, "-m", "demucs", "-n", MODEL, "-d", device, "--float32", "--clip-mode", "none",
           "-o", tmp, "--filename", "{stem}.{ext}", audio]
    return cmd if platform == "win32" else ["nice", "-n", "10"] + cmd


def demucs(audio, tmp):
    """Trennt mit Demucs: am Mac auf dem Hauptprozessor, am Windows-PC auf der Grafikkarte, wenn vorhanden."""
    import soundfile as sf
    device = pick_device()
    if WIN:
        audio = to_wav(audio, tmp)
    kw = {"creationflags": 0x00004000} if WIN else {}              # BELOW_NORMAL_PRIORITY_CLASS: der PC bleibt bedienbar
    r = subprocess.run(demucs_cmd(audio, tmp, device), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kw)
    if r.returncode:
        raise RuntimeError("Demucs: " + r.stderr.decode("utf-8", "replace")[-400:])
    out, sr = {}, None
    for s in STEMS:
        out[s], sr = sf.read(os.path.join(tmp, MODEL, s + ".wav"), dtype="float32", always_2d=True)
    return out, sr


def compute(audio_download, peaks, separator=demucs):
    """Temporaerer Ordner: Musik und Spuren sind danach weg, auch bei einem Fehler. audio_download(pfad) legt die MP3 ab."""
    with tempfile.TemporaryDirectory(prefix="s2l_stems_") as tmp:
        audio = os.path.join(tmp, "audio.mp3")
        audio_download(audio)
        stems, sr = separator(audio, tmp)
        data = sc.analyse(stems, sr, peaks)
    data["model"] = MODEL
    data["created"] = time.strftime("%Y-%m-%d %H:%M")
    return data


def process(client, name, separator=demucs, log=print):
    state = client.get("/api/sm/stems_state", name)
    if not state.get("audio"):
        log("  keine MP3 in dieser Show")
        return False
    t0 = time.time()
    data = compute(lambda p: client.download(name, p), client.get("/api/sm/peaks", name) or None, separator)
    data["fp"] = state["fp"]
    client.op("stems", name=name, data=data)
    if data["corr"] is None:
        log("  Hinweis: keine Wellenform der Show zum Vergleich, Versatz nicht geprueft")
    elif data["corr"] < sc.MIN_CORR:
        log("  Warnung: passt schlecht zur Wellenform der Show (%.2f), Versatz nicht korrigiert. Stimmt die MP3?" % data["corr"])
    else:
        log("  Versatz %+.0f ms ausgeglichen (Uebereinstimmung %.2f)" % (data["offset_ms"], data["corr"]))
    log("  fertig in %.0f s, %d Werte je Kurve" % (time.time() - t0, data["duration"] * sc.RATE))
    return True


def too_long(dur, max_min=None, state=None):
    """Laenger als die Grenze (Minuten, 0 = keine Grenze)? Ohne Angabe: --max-min, sonst die Einstellung am Pi (state)."""
    m = max_min if max_min is not None else MAX_MIN
    if m is None:
        m = float((state or {}).get("max_min", OLD_PI_MAX_MIN) or 0)
    return bool(m) and float(dur or 0) > m * 60.0


def mp3_len(state, show_dur=None):
    """Laenge der MP3 (vom Pi, stems_state audio_s); ein aelterer Pi kennt sie nicht, dann die Laenge der Show."""
    return float(state.get("audio_s") or show_dur or 0)


def audio_fingerprint(path):
    """Fingerabdruck einer MP3 ohne ihre Tags. Muss genau wie audio_fingerprint in pi/showman/store.py rechnen
    (tests/test_stems_vorab.py vergleicht beide): daran haengen die Kurven am Pi, auch fuer spaetere Shows."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(10)
        start = 0
        if head[:3] == b"ID3" and len(head) == 10:
            start = 10 + ((head[6] & 0x7F) << 21 | (head[7] & 0x7F) << 14 | (head[8] & 0x7F) << 7 | (head[9] & 0x7F))
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


def fetch_mac(music, path, dest, timeout=120):
    """MP3 beim Vorhoer-Server am Mac holen (music_serve.py, liefert nur Dateien aus der Mixxx-Bibliothek)."""
    url = music.rstrip("/") + "/audio?p=" + urllib.parse.quote(path, safe="")
    with urllib.request.urlopen(url, timeout=timeout) as r, open(dest, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)


def mac_alive(music, timeout=5):
    """Antwortet der Vorhoer-Server am Mac (/ping)?"""
    try:
        with urllib.request.urlopen(music.rstrip("/") + "/ping", timeout=timeout) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def bulk_step(client, separator=demucs, log=print, fetch=fetch_mac, alive=mac_alive):
    """Vorab-Lauf: ein Lied der Bibliothek vom Pi holen und rechnen. True = es gab etwas (gleich weiter), False = nichts zu tun
    (aus, fertig, Mac nicht da, aelterer Pi)."""
    try:
        job = client.op("stems_bulk_next", who=WHO)
    except ValueError as e:
        if "Unbekannter Befehl" in str(e):
            return False
        raise
    if not job.get("path"):
        if job.get("wait"):
            log("Vorab: " + job["wait"])
        return False
    path, t0 = job["path"], time.time()
    log("vorab %s" % (job.get("title") or os.path.basename(path)))
    try:
        with tempfile.TemporaryDirectory(prefix="s2l_vorab_") as tmp:
            audio = os.path.join(tmp, "audio.mp3")
            try:
                fetch(job["music"], path, audio)
            except urllib.error.HTTPError:
                raise                                      # diese Datei fehlt am Mac: nur dieses Lied als Fehler merken
            except OSError as e:
                if alive(job["music"]):                    # Mac antwortet, nur diese Datei nicht: als Fehler merken, weiter
                    raise RuntimeError("Der Mac liefert diese Datei nicht: %s" % e)
                log("  Mac nicht erreichbar (%s), versuche es spaeter wieder" % e)   # Mac aus, Stick weg: nichts als Fehler merken
                return False
            fp = audio_fingerprint(audio)
            if client.op("stems_bulk_fp", who=WHO, path=path, fp=fp).get("have"):
                log("  hat schon Kurven (gleiche MP3 wie eine Show)")
                return True
            stems, sr = separator(audio, tmp)
            data = sc.analyse(stems, sr, None)
        data.update(model=MODEL, created=time.strftime("%Y-%m-%d %H:%M"), fp=fp)
        secs = time.time() - t0
        client.op("stems_bulk_done", who=WHO, path=path, fp=fp, data=data, secs=round(secs, 1))
        log("  fertig in %.0f s" % secs)
    except (OSError, ValueError, RuntimeError, KeyError) as e:
        log("  Fehler: %s" % e)
        try:
            client.op("stems_bulk_fail", who=WHO, path=path, error=str(e))
        except (OSError, ValueError):
            pass
    return True


BULK_ROUND_S = 300.0    # Vorab-Lauf: nach so langer Zeit wieder nach neuen Shows sehen (die gehen vor)
RESERVE_MAX = 50        # Mac als Reserve (Wunsch 08.11.2026): nur wenn kein anderer Rechner holt und hoechstens so viele fehlen


def reserve_ok(client, log=print):
    """Darf der Mac als Reserve Lieder der Bibliothek rechnen? Nur wenn sich kein anderer Rechner (Windows-PC) meldet und
    hoechstens RESERVE_MAX Lieder fehlen: der Rest nach dem PC, nicht die ganze Bibliothek auf der langsamen CPU."""
    try:
        st = client.op("stems_bulk_status")
    except (OSError, ValueError):
        return False
    if not st.get("on"):
        return False
    others = [w for w in st.get("workers") or [] if w != WHO]
    left = int(st.get("total") or 0) - int(st.get("done") or 0) - int(st.get("fail") or 0)
    return not others and 0 < left <= RESERVE_MAX


def pick(states, again=False, named=False, durs=None, max_min=None):
    """Welche Shows sind zu rechnen? Je MP3 nur eine, die Kurven gehoeren allen Shows mit derselben MP3. MP3s laenger als
    max_min Minuten bleiben weg, ausser die Show ist beim Namen genannt. durs = Name -> Laenge der Show (nur Ersatz)."""
    seen, todo = set(), []
    for n, s in states.items():
        if not named and too_long(mp3_len(s, (durs or {}).get(n)), max_min, s):
            continue
        if s.get("audio") and s.get("fp") not in seen and (again or named or not s.get("current")):
            seen.add(s["fp"])
            todo.append(n)
    return todo


def mixxx_running():
    if WIN:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq mixxx.exe", "/NH"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return b"mixxx.exe" in r.stdout.lower()
    return subprocess.run(["pgrep", "-ix", "mixxx"], stdout=subprocess.DEVNULL).returncode == 0


def claim(client, name, take=True):
    """Am Pi anmelden, dass dieser Rechner die MP3 rechnet (oder wieder freigeben). Ein aelterer Pi kennt das nicht:
    dann gilt es als erlaubt. Rueckgabe: None = frei, sonst der Name des Rechners, der sie gerade rechnet."""
    try:
        r = client.op("stems_claim" if take else "stems_release", name=name, who=WHO)
    except ValueError as e:
        if "Unbekannter Befehl" in str(e):
            return None
        raise
    return None if r.get("ok", True) else str(r.get("by") or "?")


def process_claimed(client, name, separator=demucs, log=print):
    """process() mit Anmeldung am Pi. False, wenn ein anderer Rechner die MP3 schon rechnet."""
    by = claim(client, name)
    if by:
        log("  rechnet gerade %s, uebersprungen" % by)
        return False
    try:
        return process(client, name, separator, log)
    finally:
        try:
            claim(client, name, take=False)
        except (OSError, ValueError):
            pass


WATCH_S = 60.0          # Waechter: so oft den Pi fragen
RETRY_S = 1800.0        # nach einem Fehler dieselbe MP3 erst nach dieser Zeit wieder versuchen


FAILED = {}             # Fingerabdruck der MP3 -> Zeit des letzten Fehlers (bleibt ueber Durchgaenge erhalten)


def watch(client, every=WATCH_S, separator=demucs, log=print, stop=None, once=False, now=time.time, failed=FAILED, vorab=False, reserve=False):
    """Waechter: fragt den Pi, welche Shows noch keine aktuellen Kurven haben, und rechnet sie der Reihe nach. Laeuft, bis stop
    gesetzt ist (threading.Event) oder once=True. Ohne Pi wartet er still und versucht es wieder. vorab=True: danach Lieder
    der Bibliothek vorab (wenn auf der Seite Statistik gestartet), bis BULK_ROUND_S um ist, dann wieder zuerst die Shows."""
    while True:
        try:
            lst = client.get("/api/sm/shows")["shows"]
            durs = {s["name"]: s.get("duration") for s in lst}
            states = {n: client.get("/api/sm/stems_state", n) for n in durs}
            todo = [n for n in pick(states, durs=durs) if now() - failed.get(states[n].get("fp"), -1e9) > RETRY_S]
        except (OSError, ValueError, KeyError, TypeError) as e:
            log("Der Pi antwortet nicht: %s" % e)
            todo, states = [], {}
        for n in todo:
            log("rechne %s" % n)
            try:
                process_claimed(client, n, separator, lambda t: log(t.strip()))
            except (OSError, ValueError, RuntimeError, KeyError) as e:
                failed[states[n].get("fp")] = now()
                log("Fehler bei %s: %s (naechster Versuch in %d min)" % (n, e, RETRY_S // 60))
            if stop is not None and stop.is_set():
                return
        busy = False
        if vorab or (reserve and reserve_ok(client, log)):    # Mac: nur als Reserve fuer die letzten Lieder
            t_end = now() + BULK_ROUND_S
            try:
                while now() < t_end and not (stop is not None and stop.is_set()):
                    if not bulk_step(client, separator, lambda t: log(t.strip())):
                        break
                    busy = True
                    if once:
                        break
            except (OSError, ValueError, KeyError, TypeError) as e:
                log("Vorab: der Pi antwortet nicht: %s" % e)
        if once:
            return
        if busy:
            continue                                       # gleich weiter, nicht eine Minute warten
        if stop is not None:
            if stop.wait(every):
                return
        else:
            time.sleep(every)


def main(argv=None):
    global DEVICE, MAX_MIN
    ap = argparse.ArgumentParser(description="Pegelkurven der getrennten Spuren fuer Shows des Showmanagers")
    ap.add_argument("name", nargs="?", help="Name der Show")
    ap.add_argument("--alle", action="store_true", help="alle Shows ohne aktuelle Kurven")
    ap.add_argument("--liste", action="store_true", help="nur den Stand zeigen")
    ap.add_argument("--neu", action="store_true", help="auch aktuelle Kurven neu rechnen")
    ap.add_argument("--pi", help="Ziel, sonst aus ~/.light-butler-pi")
    ap.add_argument("--auch-mit-mixxx", action="store_true", help="auch rechnen, wenn Mixxx laeuft (kann Aussetzer geben)")
    ap.add_argument("--watch", action="store_true", help="Waechter: jede Minute den Pi fragen und neue Shows rechnen, auch neben Mixxx")
    ap.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto", help="auto: Mac CPU, sonst Grafikkarte, wenn vorhanden")
    ap.add_argument("--vorab", action="store_true", help="mit --watch: auch Lieder der Bibliothek vorab rechnen, wenn auf der "
                    "Seite Statistik gestartet (MP3s vom Vorhoer-Server am Mac); nur am schnellen Rechner")
    ap.add_argument("--reserve", action="store_true", help="mit --watch: Lieder der Bibliothek nur rechnen, wenn kein anderer "
                    "Rechner holt und hoechstens %d fehlen (Mac neben dem Windows-PC)" % RESERVE_MAX)
    ap.add_argument("--max-min", type=float, default=None, help="nur Lieder bis zu so vielen Minuten (Standard: Einstellung am Pi, 0 = alle); "
                    "eine beim Namen genannte Show wird immer gerechnet")
    ap.add_argument("--log", help="Ausgaben an diese Datei anhaengen (Windows: der Waechter laeuft mit pythonw ohne Fenster)")
    a = ap.parse_args(argv)
    if a.log:
        os.makedirs(os.path.dirname(os.path.abspath(a.log)), exist_ok=True)
        sys.stdout = sys.stderr = open(a.log, "a", encoding="utf-8", buffering=1)
    DEVICE, MAX_MIN = a.device, (None if a.max_min is None else max(0.0, a.max_min))
    if not (a.name or a.alle or a.liste or a.watch):
        ap.error("Name der Show, --alle, --liste oder --watch angeben")
    host = a.pi
    if not host:
        try:
            with open(PI_FILE, encoding="utf-8") as f:
                host = f.readline().strip()
        except OSError:
            host = ""
    if not host:
        ap.error("Kein Ziel: --pi HOST angeben")
    c = Client(host)
    if a.watch:
        def tlog(text):
            print(time.strftime("[%H:%M:%S] ") + text, flush=True)
        tlog("Waechter laeuft auf %s (%s): fragt %s jede Minute nach Shows ohne Kurven, bis %s" % (WHO, pick_device(), host,
             "Grenze aus den Einstellungen am Pi" if MAX_MIN is None else "%.0f min" % MAX_MIN if MAX_MIN else "beliebig lang") + (", dazu Bibliothek vorab" if a.vorab else ", Bibliothek als Reserve" if a.reserve else ""))
        try:
            watch(c, log=tlog, vorab=a.vorab, reserve=a.reserve)
        except KeyboardInterrupt:
            pass
        return 0
    try:
        lst = c.get("/api/sm/shows")["shows"]
        shows = [s["name"] for s in lst]
        durs = {s["name"]: s.get("duration") for s in lst}
    except (OSError, ValueError, KeyError) as e:
        print("Der Pi antwortet nicht (%s): %s" % (host, e))
        return 1
    if a.name and not a.liste and a.name not in shows:
        print("Diese Show gibt es nicht: " + a.name)
        return 1
    states = {n: c.get("/api/sm/stems_state", n) for n in ([a.name] if a.name and not a.liste else shows)}
    if a.liste:
        first = {}
        for n in shows:
            s = states[n]
            same = first.setdefault(s.get("fp"), n) if s.get("audio") else n
            print("%-40s %s%s" % (n, "keine MP3" if not s.get("audio") else "aktuell (%s)" % s.get("created") if s.get("current")
                                  else "MP3 zu lang (%.0f min), wird nicht gerechnet" % (mp3_len(s, durs.get(n)) / 60.0)
                                  if too_long(mp3_len(s, durs.get(n)), None, s)
                                  else "noch keine Kurven", "" if same == n else ", gleiche MP3 wie " + same))
        return 0
    todo = pick(states, a.neu, bool(a.name), durs)
    if not todo:
        print("Nichts zu tun, alle Kurven sind aktuell.")
        return 0
    if mixxx_running() and not a.auch_mit_mixxx:
        print("Mixxx laeuft. Das Rechnen belastet alle Kerne und kann dort Aussetzer geben. Mixxx beenden oder --auch-mit-mixxx.")
        return 1
    fail = 0
    for i, n in enumerate(todo):
        print("[%d/%d] %s" % (i + 1, len(todo), n), flush=True)
        try:
            process_claimed(c, n)
        except (OSError, ValueError, RuntimeError, KeyError) as e:
            print("  Fehler: %s" % e)
            fail += 1
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
