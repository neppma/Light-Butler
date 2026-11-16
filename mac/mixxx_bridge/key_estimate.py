#!/usr/bin/env python3
"""
key_estimate.py - Tonart fuer Lieder, die in Mixxx keine haben (Wunsch von Markus, 07.11.2026).

Damit die Tonart auch ohne Mixxx bestimmt werden kann (neue MP3s, spaeter vielleicht ganz ohne Mixxx), in dieser Reihenfolge:
  1. Tonart aus Mixxx (macht die Bruecke selbst, dieses Programm sieht nur Lieder ohne)
  2. das ID3-Feld TKEY der Datei (Mixed In Key schreibt Camelot, "8A")
  3. Schaetzung aus dem Klang mit essentia (KeyExtractor, Profil "bgate"), eigene Umgebung ~/s2l-key am Mac
  4. ohne essentia: Chroma mit numpy und Profilen, die an 400 Liedern der Bibliothek gelernt sind
Stichprobe 400 Lieder gegen Mixxx (07.11.2026): essentia bgate 73 % genau, 84 % gleich oder eng verwandt (Paralleltonart,
Quinte); numpy mit gelernten Profilen 64 % / 78 %.

Nicht eindeutig (Wunsch von Markus, 07.11.2026): Sicherheit von essentia unter KEY_MIN_STRENGTH (darunter stimmte in der
Stichprobe nur jede fuenfte, rund 5 % der Lieder) oder Laenge ausserhalb KEY_DUR_S (Geraeusche, ganze DJ-Sets): keine
Tonart, src "unsicher", im Panel "?", nie in die Datei (auch kein "keine Angabe": andere Programme laesen das als Tonart).

Ergebnis je Pfad in ~/Light-Butler-Daten/tonart/tonarten.jsonl ({path, kid, src, v}, src = tag, essentia, numpy, unsicher oder err).
Geschaetzte Tonarten zeigt das Panel mit "~". Ins TKEY der MP3 schreibt die Bruecke nur mit der Einstellung key_write am
Pi (Standard aus), nur die Camelot-Angabe ohne "~", nie ueber eine vorhandene Tonart.

    python3 key_estimate.py messen --liste liste.json --aus tonarten.jsonl     (die Bruecke ruft das selbst auf)
Aufs Licht wirkt die Tonart nur wie die aus Mixxx (Einstellung mixxx_key), und nur bei Liedern, die dort keine haben.
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

DATA_DIR = os.path.join(_pfad.daten(), "tonart")   # gemeinsame Ablage von Mixxx-App und Helfer (Fehlerbericht 07.11.2026: der Helfer hatte eine eigene)
KEYS_FILE = "tonarten.jsonl"
WRITTEN_FILE = "geschrieben.json"
ESS_PY = os.path.expanduser("~/s2l-key/bin/python")
SRC_DESC = "KeySource"
SRC_VALUE = "Light-Butler (geschaetzt)"
GUESS = ("essentia", "numpy")                    # geschaetzt; "tag" = aus der Datei gelesen, keine Schaetzung
UNSURE = "unsicher"
KEY_MIN_STRENGTH = 0.65                          # Sicherheit von essentia (KeyExtractor strength)
KEY_DUR_S = (30.0, 1200.0)                       # kuerzer: Geraeusch oder Schnipsel, laenger: ganzes DJ-Set
KEY_VERSION = 2                                  # aeltere Schaetzungen (ohne diese Grenzen) werden neu gemessen

NOTE_PC = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7,
           "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11, "H": 11}           # wie mixxx_bridge.NOTE_PC
LANCELOT_MINOR = {1: 8, 2: 3, 3: 10, 4: 5, 5: 0, 6: 7, 7: 2, 8: 9, 9: 4, 10: 11, 11: 6, 12: 1}
LANCELOT_MAJOR = {1: 11, 2: 6, 3: 1, 4: 8, 5: 3, 6: 10, 7: 5, 8: 0, 9: 7, 10: 2, 11: 9, 12: 4}
# An 400 Liedern gelernt (Mittel der Chroma, auf den Grundton gedreht), Dur und Moll
PROF_MAJOR = (1.0, 0.4627, 0.745, 0.4507, 0.7678, 0.6259, 0.4722, 0.9573, 0.4668, 0.6664, 0.4697, 0.6716)
PROF_MINOR = (1.0, 0.5663, 0.7312, 0.7582, 0.5877, 0.7451, 0.5481, 0.9486, 0.6142, 0.5696, 0.7412, 0.5991)


def kid_from_text(txt):
    """'8A' (Camelot), '1m'/'1d' (OpenKey), 'Fm', 'F#m', 'A minor', 'Bb' ... -> Mixxx-Nummer 1..24, 0 = unbekannt
    (wie mixxx_bridge.key_id_from_text, dazu "A minor"/"C major")."""
    t = (txt or "").strip().replace("♯", "#").replace("♭", "b")
    if not t:
        return 0
    m = re.fullmatch(r"(\d{1,2})([ABab])", t)
    if m and 1 <= int(m.group(1)) <= 12:
        n = int(m.group(1))
        return 13 + LANCELOT_MINOR[n] if m.group(2).upper() == "A" else 1 + LANCELOT_MAJOR[n]
    m = re.fullmatch(r"(\d{1,2})([md])", t)
    if m and 1 <= int(m.group(1)) <= 12:
        n = (int(m.group(1)) + 6) % 12 + 1
        return 13 + LANCELOT_MINOR[n] if m.group(2) == "m" else 1 + LANCELOT_MAJOR[n]
    m = re.fullmatch(r"([A-Ha-h][#b]?)\s*(m|min|minor|moll|maj|major|dur)?", t, re.IGNORECASE)
    if m:
        pc = NOTE_PC.get(m.group(1).upper())
        if pc is not None:
            return (13 if (m.group(2) or "").lower() in ("m", "min", "minor", "moll") else 1) + pc
    return 0


def camelot(kid):
    """Mixxx-Nummer -> Camelot ('8A'), '' = unbekannt."""
    kid = int(kid or 0)
    if 1 <= kid <= 12:
        return next(f"{n}B" for n, pc in LANCELOT_MAJOR.items() if pc == kid - 1)
    if 13 <= kid <= 24:
        return next(f"{n}A" for n, pc in LANCELOT_MINOR.items() if pc == kid - 13)
    return ""


# ---- Schaetzen ---------------------------------------------------------------------------------------------------
def chroma(x, sr=22050):
    """Mittlere Chroma (12 Werte, Summe 1) eines Mono-Signals, Bereich 55 Hz bis 2 kHz."""
    import numpy as np
    n_fft, hop = 8192, 4096
    f = np.fft.rfftfreq(n_fft, 1.0 / sr)
    ok = (f >= 55) & (f <= 2000)
    pc = np.full(len(f), -1)
    pc[ok] = np.round(12 * np.log2(f[ok] / 440.0) + 9).astype(int) % 12
    W = np.stack([(pc == i).astype(float) for i in range(12)])
    n = 1 + (len(x) - n_fft) // hop
    if n < 4:
        raise ValueError("Lied zu kurz")
    win = np.hanning(n_fft)
    acc = np.zeros(12)
    for s in range(0, n, 256):
        fr = np.stack([x[i * hop:i * hop + n_fft] for i in range(s, min(n, s + 256))]) * win
        c = np.abs(np.fft.rfft(fr, axis=1)) @ W.T
        acc += (c / (c.sum(1, keepdims=True) + 1e-9)).sum(0)
    return acc / (acc.sum() + 1e-12)


def key_from_chroma(c):
    """Mixxx-Nummer aus einer Chroma mit den gelernten Profilen (Korrelation, alle 24 Tonarten)."""
    import numpy as np
    c = np.asarray(c, float)
    if c.std() < 1e-12:
        return 0
    best = max((np.corrcoef(c, np.roll(np.array(p), t))[0, 1], (13 if minor else 1) + t)
               for minor, p in ((False, PROF_MAJOR), (True, PROF_MINOR)) for t in range(12))
    return int(best[1])


def essentia_key(path):
    """(Tonart, Sicherheit 0..1, Laenge s) mit essentia (Profil bgate) oder None, wenn essentia hier fehlt."""
    try:
        import essentia
        essentia.log.warningActive = False
        import essentia.standard as es
    except ImportError:
        return None
    a = es.MonoLoader(filename=path, sampleRate=44100)()
    if len(a) < 44100 * 5:
        raise ValueError("Lied zu kurz")
    k, scale, strength = es.KeyExtractor(profileType="bgate")(a)
    return kid_from_text(k + (" minor" if scale == "minor" else " major")), float(strength), len(a) / 44100.0


def judge(kid, strength, dur):
    """Schaetzung nur, wenn sie eindeutig genug ist: (kid, src-Zusatz) mit kid 0 bei unsicher."""
    if not KEY_DUR_S[0] <= dur <= KEY_DUR_S[1]:
        return 0, UNSURE
    if strength is not None and strength < KEY_MIN_STRENGTH:
        return 0, UNSURE
    return kid, ""


BPM_METHOD = "degara"                            # essentia RhythmExtractor2013: Stichprobe 300 Lieder, 79 % auf 2 % wie Mixxx, 3,6 s je Lied
BPM_RANGE = (40.0, 250.0)


def judge_bpm(bpm, dur):
    """BPM nur, wenn sie glaubhaft ist (Laenge wie bei der Tonart, Tempo im ueblichen Bereich): Wert oder 0."""
    if not KEY_DUR_S[0] <= dur <= KEY_DUR_S[1] or not BPM_RANGE[0] <= bpm <= BPM_RANGE[1]:
        return 0.0
    return round(float(bpm), 1)


BPM_PRIOR = 120.0                                # Tempo ohne essentia: Vorliebe um 120 BPM (eine Oktave Breite), wie DJ-Programme
BPM_SEARCH = (60.0, 200.0)


def numpy_bpm(x, sr=22050):
    """Tempo ohne Mixxx und essentia (Probelauf ohne Mixxx, 14.11.2026): Anschlag-Kurve (Zuwachs im Spektrum, log), deren
    Autokorrelation, je Tempo die Summe ueber 4 Vielfache des Abstands, gewichtet mit einer Vorliebe um 120 BPM; feiner auf
    0,1 BPM. Ein Ausschnitt von hoechstens 3 Minuten aus der Mitte. Rueckgabe BPM oder 0 (kein deutlicher Takt)."""
    import numpy as np
    n_fft, hop = 1024, 256
    fps = sr / hop
    if len(x) > sr * 200:                                  # lange Stuecke: 3 Minuten ab einem Fuenftel
        a = len(x) // 5
        x = x[a:a + sr * 180]
    n = 1 + (len(x) - n_fft) // hop
    if n < fps * 20:
        return 0.0
    win = np.hanning(n_fft).astype(np.float32)
    prev, env = None, np.zeros(n, np.float32)
    for s in range(0, n, 2048):
        idx = np.arange(s, min(n, s + 2048))
        fr = np.stack([x[i * hop:i * hop + n_fft] for i in idx]).astype(np.float32) * win
        m = np.log1p(30.0 * np.abs(np.fft.rfft(fr, axis=1))[:, 1:300])     # bis rund 6 kHz
        d = np.diff(np.vstack([m[:1] if prev is None else prev[None, :], m]), axis=0)
        env[idx] = np.maximum(d, 0).sum(1)
        prev = m[-1]
    k = int(fps)                                           # gleitender Mittelwert weg (1 s), nur Anstiege
    env = np.maximum(env - np.convolve(env, np.ones(k) / k, "same"), 0)
    if env.std() < 1e-6:
        return 0.0
    env = (env - env.mean()) / env.std()
    nfft = 1 << int(np.ceil(np.log2(2 * len(env))))
    ac = np.fft.irfft(np.abs(np.fft.rfft(env, nfft)) ** 2)[:len(env)]
    ac /= ac[0] + 1e-9
    bpms = np.arange(BPM_SEARCH[0], BPM_SEARCH[1], 0.1)

    def score(b):
        lag = 60.0 * fps / b
        tot = 0.0
        for m_, w in ((1, 1.0), (2, 0.5), (4, 0.25), (0.5, 0.25)):
            L = lag * m_
            i = int(L)
            if 1 <= i < len(ac) - 1:
                tot += w * (ac[i] + (ac[i + 1] - ac[i]) * (L - i))
        return tot * np.exp(-0.5 * (np.log2(b / BPM_PRIOR) / 1.0) ** 2)
    sc = np.array([score(b) for b in bpms])
    best = float(bpms[int(np.argmax(sc))])
    if sc.max() <= 0.02:
        return 0.0
    return round(best, 1)


def measure_one(r):
    """{path, file, need_key (Standard ja), need_bpm} -> {path, v, kid, src, bpm, bsrc}: zuerst die Felder TKEY und TBPM der
    Datei, dann essentia (Tonart und BPM in einem Durchgang), ohne essentia die Tonart mit numpy (BPM dann keine)."""
    import id3_tags as it
    f = r.get("file") or r["path"]
    want_key, want_bpm = r.get("need_key", True), bool(r.get("need_bpm"))
    out = {"path": r["path"], "v": KEY_VERSION}
    try:
        if f.lower().endswith(".mp3"):
            kid = kid_from_text(it.read_text(f, b"TKEY")) if want_key else 0
            if kid:
                out.update(kid=kid, src="tag")
                want_key = False
            if want_bpm:
                try:
                    tb = float(it.read_text(f, b"TBPM").replace(",", ".") or 0)
                except ValueError:
                    tb = 0.0
                if tb > 0:
                    out.update(bpm=round(tb, 2), bsrc="tag")
                    want_bpm = False
        if not (want_key or want_bpm):
            return out
        try:
            import essentia
            essentia.log.warningActive = False
            import essentia.standard as es
        except ImportError:
            es = None
        if es is not None:
            a = es.MonoLoader(filename=f, sampleRate=44100)()
            if len(a) < 44100 * 5:
                raise ValueError("Lied zu kurz")
            dur = len(a) / 44100.0
            if want_key:
                k, scale, strength = es.KeyExtractor(profileType="bgate")(a)
                kid, why = judge(kid_from_text(k + (" minor" if scale == "minor" else " major")), float(strength), dur)
                out.update(kid=kid, src=why or "essentia", st=round(float(strength), 3))
            if want_bpm:
                b = judge_bpm(es.RhythmExtractor2013(method=BPM_METHOD)(a)[0], dur)
                out.update(bpm=b, bsrc="essentia" if b else UNSURE)
            return out
        x = None
        if want_key:
            import analyze_track as at
            x = at.decode_audio(f)
            kid, why = judge(key_from_chroma(chroma(x)), None, len(x) / 22050.0)
            out.update(kid=kid, src=why or "numpy")
        if want_bpm:                                        # ohne essentia: eigene Tempo-Messung (14.11.2026)
            import analyze_track as at
            x = x if want_key else at.decode_audio(f)
            b = judge_bpm(numpy_bpm(x), len(x) / 22050.0)
            out.update(bpm=b, bsrc="numpy" if b else UNSURE)
        return out
    except Exception as e:                                  # noqa: BLE001  unlesbar: merken, nicht wieder versuchen
        if want_key:
            out.update(kid=0, src="err")
        if want_bpm:
            out.update(bpm=0.0, bsrc="err")
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
            out.write(json.dumps(measure_one(r), ensure_ascii=False) + "\n")
            out.flush()
            time.sleep(0.3)


# ---- In der Mixxx-Bruecke ----------------------------------------------------------------------------------------
def write_key_tag(path, kid):
    """Camelot-Tonart ins TKEY der MP3 (wie Mixed In Key, ohne "~"), dazu TXXX "KeySource". Nie ueber ein vorhandenes TKEY,
    ausser es ist unser eigenes. Rueckgabe: "ok", "gleich", "vorhanden" oder ein Grund, warum es nicht geht."""
    import id3_tags as it
    cam = camelot(kid)
    if not cam:
        return "Tonart ungueltig"
    if not path.lower().endswith(".mp3"):
        return "keine MP3"
    r = it.read(path)
    if isinstance(r, str):
        return r
    ver, old_size, frames = r
    tkey = [body for fid, fl, _raw, body in frames if fid == b"TKEY"]
    ours = any(fid == b"TXXX" and it.txxx_desc(body) == SRC_DESC.lower() for fid, fl, _raw, body in frames)
    if tkey and not ours:
        return "vorhanden"
    if ours and tkey and it.text_value(tkey[0]) == cam:
        return "gleich"
    keep = [raw for fid, fl, raw, body in frames
            if fid != b"TKEY" and not (fid == b"TXXX" and it.txxx_desc(body) == SRC_DESC.lower())]
    it.write(path, ver, old_size, b"".join(keep) + it.frame(b"TKEY", it.text_body(cam), ver)
             + it.frame(b"TXXX", it.txxx_body(SRC_DESC, SRC_VALUE), ver))
    return "ok"


BPM_SRC_DESC = "BpmSource"


def write_bpm_tag(path, bpm):
    """Geschaetzte BPM ins TBPM der MP3, dazu TXXX "BpmSource". Nie ueber ein vorhandenes TBPM, ausser unser eigenes.
    Rueckgabe wie write_key_tag."""
    import id3_tags as it
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        return "BPM ungueltig"
    if not BPM_RANGE[0] <= bpm <= BPM_RANGE[1]:
        return "BPM ungueltig"
    if not path.lower().endswith(".mp3"):
        return "keine MP3"
    r = it.read(path)
    if isinstance(r, str):
        return r
    ver, old_size, frames = r
    txt = f"{bpm:.1f}".rstrip("0").rstrip(".")
    tb = [body for fid, fl, _raw, body in frames if fid == b"TBPM"]
    ours = any(fid == b"TXXX" and it.txxx_desc(body) == BPM_SRC_DESC.lower() for fid, fl, _raw, body in frames)
    if tb and not ours:
        return "vorhanden"
    if ours and tb and it.text_value(tb[0]) == txt:
        return "gleich"
    keep = [raw for fid, fl, raw, body in frames
            if fid != b"TBPM" and not (fid == b"TXXX" and it.txxx_desc(body) == BPM_SRC_DESC.lower())]
    it.write(path, ver, old_size, b"".join(keep) + it.frame(b"TBPM", it.text_body(txt), ver)
             + it.frame(b"TXXX", it.txxx_body(BPM_SRC_DESC, SRC_VALUE), ver))
    return "ok"


class KeyEstimator:
    """Tonart je Pfad fuer Lieder ohne Tonart in Mixxx. key(path) -> (Mixxx-Nummer, Kennzeichen): 0 = keine oder aus der
    Datei, 1 = geschaetzt, 2 = nicht eindeutig bestimmbar (Nummer 0).
    start() misst neue Lieder in einem eigenen Prozess (mit essentia, wenn ~/s2l-key da ist), refresh() liest nach,
    write_tick() schreibt mit der Einstellung ins TKEY."""

    def __init__(self, base=DATA_DIR, log=None, ess_py=ESS_PY):
        self.base, self.log, self.ess_py = base, log or (lambda t: None), ess_py
        self.path = os.path.join(base, KEYS_FILE)
        self.written_path = os.path.join(base, WRITTEN_FILE)
        self.keys, self.bpms, self.pos, self.proc, self.writer = {}, {}, 0, None, None
        self.stop_ev = threading.Event()                      # stop(): Schreiben und Messen beenden (Helfer gibt an die Bruecke ab)
        try:
            with open(self.written_path, encoding="utf-8") as f:
                self.written = {str(k): v for k, v in dict(json.load(f)).items()}
        except (OSError, ValueError, TypeError):
            self.written = {}
        self.refresh()

    def refresh(self):
        """Neue Zeilen lesen. True = neue Tonarten."""
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
                p, kid, src = str(r["path"]), int(r.get("kid") or 0), str(r.get("src") or "")
                bpm, bsrc = float(r.get("bpm") or 0), str(r.get("bsrc") or "")
            except (ValueError, KeyError, TypeError):
                continue
            if "bsrc" in r and bsrc != "none":               # BPM (seit 07.11.2026): eigener Eintrag; "none" = frueher ohne essentia, neu messen
                self.bpms[p] = (bpm if BPM_RANGE[0] <= bpm <= BPM_RANGE[1] or bsrc == "tag" else 0.0, bsrc)
                new = new or bpm > 0 or bsrc == UNSURE
            if "src" not in r:
                continue
            if src in GUESS + (UNSURE,) and int(r.get("v") or 1) < KEY_VERSION:
                continue                                     # Schaetzung von frueher, ohne die Grenzen: neu messen
            self.keys[p] = (kid if 1 <= kid <= 24 else 0, src)
            new = new or bool(kid) or src == UNSURE
        return new

    def key(self, path):
        kid, src = self.keys.get(path, (0, ""))
        if src == UNSURE:
            return 0, 2
        return (kid, int(src in GUESS)) if kid else (0, 0)

    def bpm(self, path):
        """(BPM, Kennzeichen): 0 = keine oder aus der Datei, 1 = geschaetzt, 2 = nicht bestimmbar (BPM 0)."""
        b, src = self.bpms.get(path, (0.0, ""))
        if src == UNSURE:
            return 0.0, 2
        return (b, int(src in ("essentia", "numpy"))) if b else (0.0, 0)   # numpy: eigene Messung (14.11.2026), auch geschaetzt

    def stop(self, wait_s=5.0):
        """Messen abbrechen und das Schreiben nach der laufenden Datei beenden (der Light-Butler Helfer gibt an die Mixxx-Bruecke ab)."""
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

    def python(self):
        return self.ess_py if self.ess_py and os.path.isfile(self.ess_py) else sys.executable

    def start(self, songs):
        """songs: [{path, file, need_key, need_bpm}] ohne Tonart oder BPM in Mixxx. Misst die noch nicht gemessenen in einem eigenen Prozess."""
        if self.running():
            return 0
        todo = []
        for s in songs:                                      # need_key/need_bpm: was Mixxx nicht kennt (ohne Angabe: nur die Tonart)
            if not s.get("path"):
                continue
            nk = s.get("need_key", True) and s["path"] not in self.keys
            nb = bool(s.get("need_bpm")) and s["path"] not in self.bpms
            if nk or nb:
                todo.append({"path": s["path"], "file": s.get("file") or s["path"], "need_key": nk, "need_bpm": nb})
        if not todo:
            return 0
        os.makedirs(self.base, exist_ok=True)
        fd, lst = tempfile.mkstemp(prefix="tonart_", suffix=".json", dir=self.base)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(todo, f, ensure_ascii=False)
        py = self.python()
        self.proc = subprocess.Popen([py, os.path.join(HERE, "key_estimate.py"), "messen", "--liste", lst, "--aus", self.path],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log(f"Tonart-Schaetzung: {len(todo)} Lieder ohne Tonart oder BPM werden gemessen ({'essentia' if py == self.ess_py else 'numpy'})")
        return len(todo)

    def _save_written(self):
        tmp = self.written_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.written, f, ensure_ascii=False)
        os.replace(tmp, self.written_path)

    def write_tick(self, songs, busy=lambda p: False, gap_s=0.3):
        """Geschaetzte Tonarten ins TKEY schreiben (eigener Thread, je Lied einmal). songs: [(Pfad in Mixxx, Datei am Mac)]."""
        if self.writer is not None and self.writer.is_alive():
            return
        todo = []
        for p, f in songs:
            if not f.lower().endswith(".mp3"):
                continue
            kid, guess = self.key(p)
            if guess == 1 and p not in self.written:
                todo.append(("key", p, f, kid))
            b, bguess = self.bpm(p)
            if bguess == 1 and "bpm:" + p not in self.written:
                todo.append(("bpm", p, f, b))
        if not todo:
            return

        def run():
            n = 0
            for what, p, f, v in todo:
                if self.stop_ev.is_set():
                    break
                import stick_hold
                if stick_hold.held():                     # Stick wird ausgeworfen: aufhoeren
                    break
                if busy(p) or not os.path.exists(f):
                    continue
                try:
                    res = write_key_tag(f, v) if what == "key" else write_bpm_tag(f, v)
                except OSError as e:
                    res = f"Fehler: {e}"
                self.written[p if what == "key" else "bpm:" + p] = v if res in ("ok", "gleich") else res[:60]
                n += res == "ok"
                time.sleep(gap_s)
            self._save_written()
            if n:
                self.log(f"Tonart-Schaetzung: Tonart oder BPM in {n} MP3s geschrieben")
        self.writer = threading.Thread(target=run, name="tonart-schreiben", daemon=True)
        self.writer.start()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tonart fuer Lieder ohne Tonart in Mixxx (TKEY, essentia, numpy)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("messen")
    m.add_argument("--liste", required=True)
    m.add_argument("--aus", required=True)
    a = ap.parse_args(argv)
    try:
        cmd_measure(a)
    finally:
        if os.path.basename(a.liste).startswith("tonart_"):
            try:
                os.remove(a.liste)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
