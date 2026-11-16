"""Pegelkurven auch am Windows-PC (Wunsch von Markus, 06.11.2026): Grafikkarte, MP3 ohne ffmpeg, Mac und PC teilen sich die
Arbeit ueber eine Anmeldung am Pi, Lieder ueber 6 Minuten bleiben weg, die Dateien kommen vom Pi (/helfer/)."""
import os
import sys
import time
import types

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "stems"))
import stems_show as ss  # noqa: E402
from showman import api  # noqa: E402

# ---- Geraet und Aufruf ----
check(ss.pick_device("auto", "darwin", cuda=True) == "cpu", "Mac: immer die CPU (der Grafikchip des M1 bricht ab)")
check(ss.pick_device("auto", "win32", cuda=True) == "cuda" and ss.pick_device("auto", "win32", cuda=False) == "cpu", "Windows: CUDA, wenn vorhanden")
check(ss.pick_device("cpu", "win32", cuda=True) == "cpu", "--device cpu erzwingt die CPU")
mac = ss.demucs_cmd("a.mp3", "/t", "cpu", "darwin")
win = ss.demucs_cmd("a.wav", "C:/t", "cuda", "win32")
check(mac[:3] == ["nice", "-n", "10"] and mac[mac.index("-d") + 1] == "cpu", "Mac: wie bisher mit nice auf der CPU")
check("nice" not in win and win[win.index("-d") + 1] == "cuda" and win[-1] == "a.wav", "Windows: ohne nice, auf der Grafikkarte, mit WAV")
src = open(os.path.join(ROOT, "mac", "stems", "stems_show.py"), encoding="utf-8").read()
check("if WIN:\n        audio = to_wav(audio, tmp)" in src and '"creationflags": 0x00004000' in src, "Windows: MP3 vorher zu WAV, niedrige Prioritaet")
check('"tasklist"' in src and '"pgrep"' in src, "Mixxx-Pruefung auf beiden Systemen")

# ---- MP3 zu WAV: mit soundfile, wenn vorhanden (am Mac in den Tests nicht zwingend) ----
try:
    import numpy as np
    import soundfile as sf
    import tempfile
    d = tempfile.mkdtemp()
    src_wav = os.path.join(d, "in.wav")
    sf.write(src_wav, np.zeros((4410, 2), dtype="float32"), 44100)
    out = ss.to_wav(src_wav, d)
    x, sr = sf.read(out, always_2d=True)
    check(out.endswith("audio.wav") and sr == 44100 and x.shape == (4410, 2), "to_wav schreibt eine WAV mit gleicher Rate und Kanaelen")
    # Fehlerbericht 09.11.2026: beschaedigte MP3 ("Unspecified internal error." von libsndfile): ffmpeg als Ausweg, wenn da
    _orig = sf.read
    sf.read = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Unspecified internal error."))
    try:
        if ss.ffmpeg_path():
            d2 = tempfile.mkdtemp()
            out2 = ss.to_wav(src_wav, d2)
            sf.read = _orig
            x2, sr2 = sf.read(out2, always_2d=True)
            check(sr2 == 44100 and x2.shape[0] >= 4000, "soundfile scheitert: ffmpeg liest die Datei (beschaedigte MP3)")
        else:
            check(True, "kein ffmpeg hier: Ausweg nicht geprueft")
        _p = ss.ffmpeg_path
        ss.ffmpeg_path = lambda: None
        sf.read = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Unspecified internal error."))
        try:
            ss.to_wav(src_wav, tempfile.mkdtemp())
            check(False, "ohne ffmpeg bleibt der Fehler")
        except RuntimeError:
            check(True, "ohne ffmpeg bleibt der Fehler (der Mac rechnet das Lied als Reserve)")
        ss.ffmpeg_path = _p
    finally:
        sf.read = _orig
except ImportError:
    check(True, "soundfile fehlt hier: to_wav nicht geprueft")

# ---- MP3 ohne Tags (libsndfile scheiterte an grossen ID3v2.4-Koepfen, Fehlerbericht 06.11.2026) ----
import tempfile as _tf  # noqa: E402
_d = _tf.mkdtemp()
_src = os.path.join(_d, "t.mp3")
_audio = b"\xff\xfb\x90\x00" + bytes(range(256)) * 50
with open(_src, "wb") as f:
    f.write(b"ID3\x04\x00\x00\x00\x00\x03\x00" + b"B" * 384 + _audio + b"TAG" + b"x" * 125)   # 384 Byte Tag (Bild), ID3v1 hinten
_dst = ss.strip_tags(_src, os.path.join(_d, "o.mp3"))
check(open(_dst, "rb").read() == _audio, "Tags vorn und hinten weg, Audiodaten unveraendert")
check(ss.tag_range(_src) == (394, 394 + len(_audio)), "Bereich der Audiodaten wie beim Fingerabdruck")
with open(_src, "wb") as f:
    f.write(_audio)
check(open(ss.strip_tags(_src, os.path.join(_d, "o2.mp3")), "rb").read() == _audio, "ohne Tags: Datei bleibt gleich")
check("strip_tags(audio, os.path.join(tmp, \"notag.mp3\"))" in src, "to_wav liest die MP3 ohne Tags")

# ---- Laenge der MP3 (nicht der Show): nur bis 6 Minuten (Wunsch von Markus) ----
A = {"audio": True, "fp": "1:a", "current": False}
B = {"audio": True, "fp": "2:b", "current": False}
check(ss.MAX_MIN is None and ss.too_long(361) and not ss.too_long(360) and not ss.too_long(3600, 0), "aelterer Pi: Grenze 6 min, 0 = keine Grenze")
# Einstellung am Pi (09.11.2026): stems_state max_min gilt, --max-min geht vor
check(not ss.too_long(500, None, {"max_min": 10}) and ss.too_long(601, None, {"max_min": 10}) and not ss.too_long(9999, None, {"max_min": 0})
      and ss.too_long(500, 6, {"max_min": 10}), "Grenze aus der Einstellung am Pi, --max-min geht vor")
check(ss.pick({"x": dict(A, audio_s=500, max_min=10)}) == ["x"], "Lied mit 8:20 bei Grenze 10 min: wird gerechnet")
check(ss.pick({"kurz": dict(A, audio_s=200), "lang": dict(B, audio_s=3600)}) == ["kurz"], "Stundenlange MP3 wird nicht gerechnet")
check(ss.pick({"x": dict(A, audio_s=3600)}, durs={"x": 180}) == [], "es zaehlt die MP3, nicht die Laenge der Show")
check(ss.pick({"x": dict(A, audio_s=200)}, durs={"x": 3600}) == ["x"], "kurze MP3 in langer Show: wird gerechnet")
check(ss.pick({"x": dict(A)}, durs={"x": 3600}) == [], "aelterer Pi ohne audio_s: Laenge der Show als Ersatz")
check(ss.pick({"lang": dict(B, audio_s=3600)}, named=True) == ["lang"], "beim Namen genannt: trotzdem")
check(ss.pick({"lang": dict(B, audio_s=3600)}, max_min=0) == ["lang"], "--max-min 0: alle")


class Pi:
    """Falscher Pi mit Anmeldung wie ShowManager.stems_claim."""
    def __init__(self, shows, claims=None):
        self.shows, self.claims, self.sent, self.ops = shows, dict(claims or {}), [], []

    def get(self, path, name=None):
        if path == "/api/sm/shows":
            return {"shows": [{"name": n, "duration": s.pop("dur", 200)} for n, s in self.shows.items()]}
        if path == "/api/sm/stems_state":
            return self.shows[name]
        return {}

    def download(self, name, dest):
        open(dest, "wb").write(b"x")

    def op(self, op, **data):
        self.ops.append((op, data.get("name")))
        fp = self.shows[data["name"]]["fp"]
        if op == "stems_claim":
            if self.claims.get(fp, data["who"]) != data["who"]:
                return {"ok": False, "by": self.claims[fp]}
            self.claims[fp] = data["who"]
            return {"ok": True}
        if op == "stems_release":
            if self.claims.get(fp) == data["who"]:
                del self.claims[fp]
            return {"ok": True}
        self.sent.append(data["name"])
        self.shows[data["name"]]["current"] = True
        return {}


def fake(audio, tmp):
    import numpy as np
    x = np.zeros((44100 * 2, 2), dtype="float32")
    return {s: x for s in ss.STEMS}, 44100


p = Pi({"Neu": dict(A, audio_s=200), "Mix": dict(B, audio_s=3600)})
out = []
ss.watch(p, separator=fake, log=out.append, once=True)
check(p.sent == ["Neu"] and ("stems_claim", "Neu") in p.ops and ("stems_release", "Neu") in p.ops and not p.claims,
      "Waechter meldet an, rechnet, gibt frei; die Stunde-MP3 nicht")
check(not any(n == "Mix" for _o, n in p.ops), "zu lange MP3 wird am Pi gar nicht erst angemeldet")
p2 = Pi({"Neu": dict(A)}, claims={"1:a": "WINDOWS-PC"})
ss.watch(p2, separator=fake, log=out.append, once=True)
check(p2.sent == [] and any("rechnet gerade WINDOWS-PC" in x for x in out), "rechnet ein anderer Rechner, wird uebersprungen")

# ---- Pi: Laenge der MP3 aus dem Dateikopf ----
from showman import store  # noqa: E402
import tempfile  # noqa: E402
td = tempfile.mkdtemp()


def mp3(name, header, body, id3=b""):
    p_ = os.path.join(td, name)
    with open(p_, "wb") as f:
        f.write(id3 + header + body)
    return p_


cbr = mp3("cbr.mp3", bytes([0xFF, 0xFB, 0x90, 0x00]), b"\0" * (16000 * 60 - 4))      # MPEG-1 L3, 128 kbit/s, 44,1 kHz, Stereo
check(abs(store.mp3_duration(cbr) - 60.0) < 0.01, "CBR: Groesse durch Bitrate (128 kbit/s, 60 s)")
id3 = b"ID3\x03\x00\x00\x00\x00\x02\x00" + b"\0" * 256                              # ID3-Kopf mit 256 Byte Tags
cbr2 = mp3("tag.mp3", bytes([0xFF, 0xFB, 0x90, 0x00]), b"\0" * (16000 * 60 - 4), id3)
check(abs(store.mp3_duration(cbr2) - 60.0) < 0.01, "ID3-Tags zaehlen nicht mit")
xing = bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\0" * 32 + b"Xing" + (1).to_bytes(4, "big") + (11484).to_bytes(4, "big")
vbr = mp3("vbr.mp3", xing, b"\0" * 5000)
check(abs(store.mp3_duration(vbr) - 11484 * 1152 / 44100) < 0.01, "VBR: Rahmenzahl aus dem Xing-Kopf (5 min)")
check(store.mp3_duration(os.path.join(td, "fehlt.mp3")) == 0.0 and store.mp3_duration(mp3("leer.mp3", b"", b"abc")) == 0.0, "unlesbar: 0")
check('"audio_s": mp3_duration(self.path(name, "audio.mp3"))' in open(os.path.join(ROOT, "pi", "showman", "store.py"), encoding="utf-8").read(),
      "stems_state meldet die Laenge der MP3")

# ---- Pi: Anmeldung ----
mgr = types.SimpleNamespace(store=types.SimpleNamespace(_audio_fp=lambda n: {"A": "1:a", "B": "2:b"}.get(n, "")),
                            stem_claims={}, CLAIM_S=api.ShowManager.CLAIM_S)
claim = lambda n, w, t=True: api.ShowManager.stems_claim(mgr, n, w, t)   # noqa: E731
check(claim("A", "mac")["ok"] and not claim("A", "pc")["ok"] and claim("A", "pc")["by"] == "mac", "zweiter Rechner bekommt dieselbe MP3 nicht")
check(claim("B", "pc")["ok"], "andere MP3: frei")
claim("A", "pc", False)
check(not claim("A", "pc")["ok"], "fremde Anmeldung kann man nicht freigeben")
claim("A", "mac", False)
check(claim("A", "pc")["ok"], "nach der Freigabe darf der andere")
mgr.stem_claims["2:b"] = ("pc", time.time() - api.ShowManager.CLAIM_S - 1)
check(claim("B", "mac")["ok"], "nach 20 Minuten verfaellt eine Anmeldung (abgestuerzter Rechner)")
try:
    claim("X", "mac")
    check(False, "Show ohne MP3: Fehler")
except ValueError:
    check(True, "Show ohne MP3: Fehler")
asrc = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('self.stem_claims.pop(st._audio_fp(d.get("name")), None)' in asrc, "Kurven gespeichert: Anmeldung erledigt")

# ---- Dateien vom Pi: /helfer/ ----
check(api.HELFER == ("stems_show.py", "stem_curves.py", "install_stems.ps1"), "nur die drei Helfer-Dateien")
check(all(os.path.isfile(os.path.join(api.HELFER_DIRS[1], n)) for n in api.HELFER), "im Projekt liegen alle drei in mac/stems")


class H:
    def _send(self, code, body, ctype, headers=None):
        self.code, self.body, self.headers = code, body, headers or {}


h = H()
api._helfer(h, "")
check(h.code == 200 and h.body.decode().split() == list(api.HELFER), "/helfer/ zeigt die Dateien")
h = H()
api._helfer(h, "stems_show.py")
check(h.code == 200 and b"def pick_device" in h.body and "attachment" in h.headers.get("Content-Disposition", ""), "/helfer/stems_show.py zum Herunterladen")
for bad in ("../show.py", "nanoleaf.json", "claude.json"):
    h = H()
    api._helfer(h, bad)
    check(h.code == 404, "keine anderen Dateien: " + bad)
dep = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
check('mac/stems/install_stems.ps1 "$PI:$DEST/helfer/"' in dep, "deploy.sh push kopiert die Helfer auf den Pi")

# ---- Installation am PC ----
ps = open(os.path.join(ROOT, "mac", "stems", "install_stems.ps1"), "rb").read()
check(all(b < 128 for b in ps), "install_stems.ps1 nur ASCII (Windows-PowerShell liest sonst Umlaute falsch)")
ps = ps.decode()
check('$Torch = "2.5.1"' in ps and "whl/cu124" in ps and '"3.12", "3.11", "3.10", "3.9"' in ps, "Torch 2.5.1 mit CUDA, Python 3.9 bis 3.12")
check("Register-ScheduledTask" in ps and "-AtLogOn" in ps and "--watch$Vorab --log" in ps and "-OhneVorab" in ps and "pythonw.exe" in ps, "Waechter startet beim Anmelden ohne Fenster, mit Log")
check("-Entfernen" in ps and "Unregister-ScheduledTask" in ps, "laesst sich wieder entfernen")
check("--log" in src and "buffering=1" in src, "Helfer schreibt mit --log in eine Datei (pythonw hat keine Konsole)")
finish("test_stems_windows")
