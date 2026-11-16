#!/usr/bin/env python3
"""
analyze_track.py - Voranalyse einer Musikdatei fuer die Lichtsteuerung (laeuft auf dem Mac).

Bestimmt aus dem Audio: Energieverlauf, Breaks, Aufbauten (Build-ups), kurze Stille vor dem Drop und die
Drops selbst, jeweils mit Zeitpunkt in Sekunden. Das Ergebnis wird als kleine JSON-Datei gespeichert.

  python3 analyze_track.py --selftest                              Eigentest mit einem kuenstlichen Lied
  python3 analyze_track.py --file ~/Music/lied.mp3 --bpm 128       eine Datei analysieren (BPM optional)
  python3 analyze_track.py --db ~/Downloads/mixxxdb.sqlite --find "Distorted Truth"      Lied in Mixxx suchen
  python3 analyze_track.py --db ~/Downloads/mixxxdb.sqlite --id 1234                     Lied aus Mixxx analysieren
  python3 analyze_track.py --db ~/Downloads/mixxxdb.sqlite --all --jobs 4                ganze Bibliothek (dauert!)

Benoetigt:  pip install numpy scipy soundfile      (auf dem Mac hilft afconvert aus, sonst ffmpeg:  brew install ffmpeg)
"""
import argparse
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings

import numpy as np

SR = 22050            # Analyse-Abtastrate
NFFT = 2048
HOP = 1024            # 46 ms je Bild (ca. 21,5 Bilder pro Sekunde)
FPS = SR / HOP
VERSION = 3
LIFT_MIN = 0.15       # Mindest-Anstieg des Pegels (0..1) fuer einen Einsatz ohne Break (per --lift aenderbar)


# ---- Audio laden ----------------------------------------------------------------------------------------------
def explain_missing(path):
    """Verstaendliche Meldung, warum eine Datei fehlt (typisch: NAS nicht verbunden)."""
    parts = path.split(os.sep)
    if path.startswith("/Volumes/") and len(parts) > 2:
        vol = os.sep.join(parts[:3])
        if not os.path.exists(vol):
            return (f"Laufwerk {vol} ist nicht verbunden (NAS?). Im Finder: Gehe zu -> Mit Server verbinden, "
                    f"dann nochmal starten. Datei: {path}")
    return f"Datei nicht gefunden: {path}"


def read_bytes(path, retries=3):
    """Datei in einem Stueck lesen (viel schneller als kleine Zugriffe ueber das Netzwerk), mit Wiederholung."""
    last = None
    for i in range(retries):
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(explain_missing(path)) from None
        except OSError as e:                                      # kurze Netzwerkstoerung
            last = e
            time.sleep(0.5 * (i + 1))
    raise OSError(f"Lesefehler bei {path}: {last}")


def decode_afconvert(raw, ext):
    """Mit afconvert (in macOS eingebaut) dekodieren: liest auch MP3, an denen libsndfile mitten im Lied scheitert,
    und AAC. Liefert Mono mit SR Hz oder None, wenn es afconvert nicht gibt oder die Datei nicht lesbar ist."""
    tool = shutil.which("afconvert")
    if not tool:
        return None
    from scipy.io import wavfile
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in" + ext), os.path.join(d, "out.wav")
        with open(src, "wb") as f:
            f.write(raw)
        r = subprocess.run([tool, "-f", "WAVE", "-d", f"LEF32@{SR}", src, dst], capture_output=True, timeout=600)
        if r.returncode != 0 or not os.path.exists(dst):
            return None
        with warnings.catch_warnings():                          # afconvert schreibt einen Fuell-Block (FLLR), harmlos
            warnings.simplefilter("ignore")
            _, data = wavfile.read(dst)
    data = np.asarray(data, dtype=np.float32)
    return (data.mean(axis=1) if data.ndim > 1 else data) if data.size else None   # Kanaele selbst mitteln wie bei soundfile


def decode_audio(path):
    """Datei als Mono-Signal mit SR Hz laden. WAV direkt, sonst soundfile (MP3 ab libsndfile 1.1), afconvert (Mac)
    oder ffmpeg."""
    path = os.path.expanduser(path)
    raw = read_bytes(path)
    x, sr = None, None
    if path.lower().endswith(".wav"):
        try:
            from scipy.io import wavfile
            sr, data = wavfile.read(io.BytesIO(raw))
            data = data.astype(np.float32)
            if np.abs(data).max() > 2.0:
                data /= max(1.0, np.abs(data).max())
            x = data.mean(axis=1) if data.ndim > 1 else data
        except Exception:
            x = None
    if x is None:
        try:
            import soundfile as sf
            data, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
            x = data.mean(axis=1)
        except Exception:
            x = None
    if x is None:
        y = decode_afconvert(raw, os.path.splitext(path)[1] or ".mp3")
        if y is not None:
            return y
    if x is None:
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                               input=raw, capture_output=True, timeout=600)
            if r.returncode != 0 or not r.stdout:
                raise RuntimeError(r.stderr.decode(errors="replace")[:200])
            return np.frombuffer(r.stdout, dtype=np.float32).copy()
        except FileNotFoundError:
            raise RuntimeError("Datei nicht lesbar (soundfile und afconvert gescheitert, ffmpeg nicht installiert): "
                               + os.path.basename(path)) from None
    if sr != SR:
        from scipy.signal import resample_poly
        g = math.gcd(int(sr), SR)
        x = resample_poly(x, SR // g, int(sr) // g).astype(np.float32)
    return x.astype(np.float32)


# ---- Merkmale ---------------------------------------------------------------------------------------------------
def smooth(v, n):
    n = max(1, int(n))
    if n == 1:
        return v
    k = np.ones(n) / n
    pad = np.pad(v, (n // 2, n - 1 - n // 2), mode="edge")
    return np.convolve(pad, k, mode="valid")


def norm(v, lo_pct=10, hi_pct=95):
    lo, hi = np.percentile(v, lo_pct), np.percentile(v, hi_pct)
    return np.clip((v - lo) / max(1e-6, hi - lo), 0.0, 1.2)


def features(x):
    """Pegel in drei Baendern pro Bild (dB): Bass 30-150 Hz, Mitten 150-2000 Hz, Hoehen 2-10 kHz."""
    n = 1 + max(0, (len(x) - NFFT) // HOP)
    win = np.hanning(NFFT).astype(np.float32)
    freqs = np.fft.rfftfreq(NFFT, 1.0 / SR)
    bands = {"bass": (30, 150), "mid": (150, 2000), "high": (2000, 10000)}
    idx = {k: np.where((freqs >= lo) & (freqs < hi))[0] for k, (lo, hi) in bands.items()}
    out = {k: np.zeros(n, dtype=np.float32) for k in bands}
    chunk = 512
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        fr = np.stack([x[i * HOP:i * HOP + NFFT] for i in range(s, e)]) * win
        p = np.abs(np.fft.rfft(fr, axis=1)) ** 2
        for k, ix in idx.items():
            out[k][s:e] = p[:, ix].sum(axis=1)
    db = {k: 10.0 * np.log10(v + 1e-9) for k, v in out.items()}
    return db


def beat_phase(bass_db, bpm):
    """Zeit des ersten Beats (Sekunden) aus den Bass-Einsaetzen; None bei unbekanntem Tempo."""
    if not bpm or bpm <= 0:
        return None
    on = np.maximum(0.0, np.diff(np.sqrt(10 ** (bass_db / 10.0)), prepend=0.0))
    T = FPS * 60.0 / bpm                                          # Beat-Laenge in Bildern
    steps = np.linspace(0, T, max(8, int(T)), endpoint=False)
    best, best_s = -1.0, 0.0
    for ph in steps:
        pos = np.arange(ph, len(on) - 1, T)
        i = pos.astype(int)
        val = on[i] * (1 - (pos - i)) + on[np.minimum(i + 1, len(on) - 1)] * (pos - i)
        if val.sum() > best:
            best, best_s = val.sum(), ph
    return best_s / FPS


# ---- Ereignisse finden ---------------------------------------------------------------------------------------------
def find_events(db, bpm=None):
    n = len(db["bass"])
    dur = n / FPS
    B = norm(smooth(norm(db["bass"]), FPS * 1.0))                # Bass (geglaettet, 0..1)
    L = norm(smooth(norm(0.5 * db["bass"] + 0.3 * db["mid"] + 0.2 * db["high"]), FPS * 0.5))   # Gesamtpegel
    H = norm(smooth(norm(db["high"]), FPS * 1.0))                # Hoehen
    beat = 60.0 / bpm if bpm and bpm > 0 else 0.47
    min_break = max(6.0, 8 * beat)
    low = B < 0.33                                               # kein Bass-Teppich: Break
    events, runs, i = [], [], 0
    while i < n:
        if low[i]:
            j = i
            while j < n and low[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    breaks = [(a / FPS, b / FPS) for a, b in runs if (b - a) / FPS >= min_break]
    for (t0, t1) in breaks:
        a, b = int(t0 * FPS), min(n - 1, int(t1 * FPS))
        if t0 < 3.0:                                             # Intro: der Einsatz der Bassdrum ist ein schwacher Drop
            events.append({"type": "intro", "t": 0.0, "end": round(t1, 2)})
            kick_in = {"type": "drop", "t": round(t1, 2), "strength": round(float(B[min(n - 1, b + int(2 * FPS))] - B[max(0, b - int(2 * FPS))]), 2), "kind": "intro_end"}
            events.append(kick_in)
            continue
        if t1 >= dur - 1.0:                                      # Outro: Bass kommt nicht mehr zurueck
            events.append({"type": "outro", "t": round(t0, 2), "end": round(dur, 2)})
            continue
        events.append({"type": "break", "t": round(t0, 2), "end": round(t1, 2)})
        # Drop: wie stark kommt der Bass zurueck?
        before = B[max(0, b - int(2 * FPS)):b].mean()
        after = B[min(n - 1, b + int(1 * FPS)):min(n, b + int(4 * FPS) + 1)].mean() if b + 1 < n else 0.0
        strength = float(after - before)
        # genauer Zeitpunkt: groesster Bass-Anstieg im Fenster um das Ende des Breaks
        raw = norm(db["bass"])
        lo_i, hi_i = max(1, b - int(1.5 * FPS)), min(n - 1, b + int(2.0 * FPS))
        jump = np.diff(smooth(raw, 3))[lo_i:hi_i]
        t_drop = (lo_i + int(np.argmax(jump)) + 1) / FPS if len(jump) else t1
        if abs(t_drop - t1) > 2.0:
            t_drop = t1
        # Genauer Einsatz: die Bassdrum kehrt zurueck (kurze, harte Bass-Schlaege), nicht ein anschwellender Bass-Riser
        amp = np.sqrt(10 ** (db["bass"] / 10.0))
        flux = np.maximum(0.0, np.diff(amp, prepend=amp[0]))
        post = flux[min(n - 1, b + int(1 * FPS)):min(n, b + int(8 * FPS))]
        if len(post) > 10:
            thr = 0.5 * float(np.percentile(post, 90))
            beat_f = max(1, int(round(beat * FPS)))
            lo_f, hi_f = max(1, b - int(3.5 * FPS)), min(n - beat_f - 2, b + int(5 * FPS))
            for i in range(lo_f, max(lo_f, hi_f)):
                if flux[i] >= thr > 0 and flux[i + beat_f - 1:i + beat_f + 2].max() >= thr:   # Schlag und der naechste Beat-Schlag
                    t_drop = i / FPS + 0.03
                    break
        if strength >= 0.35:
            events.append({"type": "drop", "t": round(t_drop, 2), "strength": round(strength, 2), "kind": "after_break"})
        # Aufbau: Hoehen/Gesamtpegel steigen im Break bis zum Hoehepunkt vor dem Drop
        R = smooth(0.5 * H + 0.5 * L, FPS * 2.0)
        seg = R[a:b]
        if len(seg) > 4 * FPS:
            tail = max(1, int(1.0 * FPS))
            peak_i = int(np.argmax(seg[:len(seg) - tail])) if len(seg) > tail + 2 else len(seg) - 1
            pre = seg[:peak_i + 1]
            rng = float(pre.max() - pre.min())
            if rng > 0.05:
                near_min = np.where(pre <= pre.min() + 0.15 * rng)[0]     # letzter Tiefpunkt vor dem Anstieg
                s_i = int(near_min[-1])
                rise = float(pre[-1] - pre[s_i])
                s = a + s_i
                if (t_drop - s / FPS) >= 4.0 and rise >= 0.2:
                    events.append({"type": "build", "t": round(s / FPS, 2), "end": round(t_drop, 2), "rise": round(rise, 2)})
        # kurze Stille unmittelbar vor dem Drop
        bd = min(n - 1, int(t_drop * FPS))
        w0, w1 = max(a, bd - int(2.5 * FPS)), bd
        if w1 - w0 > 3:
            pre = float(np.median(L[max(a, bd - int(6 * FPS)):max(a + 1, bd - int(3 * FPS))]))
            dip = np.where(L[w0:w1] < 0.4 * max(pre, 0.1))[0]
            if len(dip) >= 2 and pre > 0.15:
                events.append({"type": "gap", "t": round((w0 + int(dip[0])) / FPS, 2), "end": round(t_drop, 2)})
    # Anstiege ohne Break: ruhige Strophe -> lauter Refrain (der Bass faellt vorher nicht weg)
    E = smooth(0.5 * B + 0.5 * L, FPS * 1.5)
    wb, wa = int(6 * FPS), int(4 * FPS)
    if n > wb + wa + 2:
        cs = np.concatenate([[0.0], np.cumsum(E)])
        idx = np.arange(wb, n - wa)
        mean_before = (cs[idx] - cs[idx - wb]) / wb
        mean_after = (cs[idx + wa] - cs[idx]) / wa
        d = mean_after - mean_before
        cand = idx[(d >= LIFT_MIN) & (mean_after >= 0.55)]
        raw_lvl = smooth(0.5 * norm(db["bass"]) + 0.5 * norm(db["bass"] * 0.5 + db["mid"] * 0.3 + db["high"] * 0.2), 3)
        taken = [e["t"] for e in events if e["type"] == "drop"]
        spans = [(e["t"], e.get("end", e["t"])) for e in events if e["type"] in ("break", "intro", "outro")]
        last_t = -999.0
        j = 0
        while j < len(cand):
            k = j
            while k + 1 < len(cand) and cand[k + 1] - cand[k] <= int(2 * FPS):
                k += 1
            grp = cand[j:k + 1]
            best = grp[int(np.argmax(d[grp - wb]))]
            lo_i, hi_i = max(1, best - int(3 * FPS)), min(n - 1, best + int(3 * FPS))
            step = np.diff(raw_lvl)[lo_i:hi_i]
            t_lift = (lo_i + int(np.argmax(step)) + 1) / FPS if len(step) else best / FPS
            near_drop = any(abs(t_lift - td) < 6.0 for td in taken)
            in_span = any(a_ <= t_lift <= b_ + 6.0 for a_, b_ in spans if b_ > a_)
            if not near_drop and not in_span and t_lift - last_t >= 10.0:
                events.append({"type": "drop", "t": round(float(t_lift), 2), "strength": round(float(d[best - wb]), 2), "kind": "lift"})
                last_t = t_lift
            j = k + 1
    events.sort(key=lambda e: e["t"])
    energy = smooth(0.5 * B + 0.5 * L, FPS * 1.0)
    level = [int(round(100 * float(np.clip(energy[int(s * FPS)], 0, 1)))) for s in range(int(dur))]
    return events, level


def snap_to_beats(events, first_beat, bpm):
    """Drop- und Aufbau-Zeiten auf das naechste Beat-Raster legen (Fehler unter einem halben Beat)."""
    if first_beat is None or not bpm:
        return events
    beat = 60.0 / bpm
    for e in events:
        if e["type"] in ("drop", "build", "gap"):
            e["t"] = round(first_beat + round((e["t"] - first_beat) / beat) * beat, 2)
        if e.get("end") and e["type"] in ("build", "gap"):
            e["end"] = round(first_beat + round((e["end"] - first_beat) / beat) * beat, 2)
    return events


SEC_MIN_S = 12.0           # kuerzere Strophen und Hauptteile gehoeren zum Nachbarn
SEC_EDGE_S = 6.0           # kuerzeres Intro oder Outro zaehlt nicht
SEC_FULL = 0.6             # "voll": so weit zwischen dem leisen (10 %) und dem lauten (85 %) Teil des Liedes
SEC_EDGE = 0.3             # Intro und Outro: leiser als so weit dazwischen (sonst waere die erste Strophe schon Intro)
SEC_FLAT = 15.0            # Lied mit weniger Unterschied (Energie 0-100): durchgehend Hauptteil


def _snap_section(t, cues, drops, first_beat, bpm):
    """Grenze eines Abschnitts: naechster Hotcue, sonst naechster Drop (je bis 2,5 s), sonst der naechste Takt (4/4)."""
    for cand in (cues, drops):
        near = [c for c in cand if abs(c - t) <= 2.5]
        if near:
            return min(near, key=lambda c: abs(c - t))
    if first_beat is not None and bpm:
        bar = 240.0 / bpm
        return first_beat + round((t - first_beat) / bar) * bar
    return t


def find_sections(res, cues=()):
    """Abschnitte des Liedes aus einer fertigen Analyse (Ereignisse und Lautstaerkekurve), ohne die Datei neu zu lesen:
    [[Art, Start, Ende], ...] lueckenlos, Art = intro, vers (ruhigerer Teil, z. B. Strophe), main (voller Teil, z. B.
    Refrain), break, outro. Unterschieden wird nach der Energie, nicht danach, ob sich ein Teil wiederholt.
    Zu kurze oder gleichmaessige Lieder: leer bzw. durchgehend main."""
    dur, en, events = float(res.get("duration") or 0), res.get("energy") or [], res.get("events") or []
    if dur < 30.0 or len(en) < 30:
        return []
    s = smooth(np.asarray(en, dtype=float), 8)
    low, top = float(np.percentile(s, 10)), float(np.percentile(s, 85))
    full = s >= low + SEC_FULL * (top - low)
    flat = top - low < SEC_FLAT
    a, b = 0.0, dur
    if not flat:
        idx = np.where(s >= low + SEC_EDGE * (top - low))[0]
        a, b = min(float(idx[0]), 0.35 * dur), max(float(idx[-1] + 1), 0.7 * dur)
    for e in events:
        if e["type"] == "intro":
            a = max(a, float(e["end"]))
        elif e["type"] == "outro":
            b = min(b, float(e["t"]))
    a = a if a >= SEC_EDGE_S else 0.0
    b = b if dur - b >= SEC_EDGE_S else dur
    # Mitte: Breaks aus der Analyse, dazwischen voll oder ruhiger
    parts, pos = [], a
    for e in sorted((e for e in events if e["type"] == "break"), key=lambda e: e["t"]):
        t0, t1 = max(float(e["t"]), a), min(float(e.get("end", e["t"])), b)
        if t1 > t0:
            parts += [("", pos, t0), ("break", t0, t1)]
            pos = t1
    parts.append(("", pos, b))
    out = [["intro", 0.0, a]] if a > 0 else []
    for typ, t0, t1 in parts:
        if t1 - t0 < 0.5:
            continue
        if typ:
            out.append([typ, t0, t1])
            continue
        runs = []                                                # Laeufe voll/ruhiger, je Sekunde
        for sec in range(int(t0), max(int(t0) + 1, int(t1))):
            typ_s = "main" if flat or full[min(sec, len(full) - 1)] else "vers"
            if runs and runs[-1][0] == typ_s:
                runs[-1][2] = sec + 1.0
            else:
                runs.append([typ_s, float(sec), sec + 1.0])
        runs[0][1], runs[-1][2] = t0, t1
        while len(runs) > 1:                                     # zu kurze Laeufe (der kuerzeste zuerst) zum Nachbarn
            i = min(range(len(runs)), key=lambda k: runs[k][2] - runs[k][1])
            if runs[i][2] - runs[i][1] >= SEC_MIN_S:
                break
            if i == 0:
                runs[1][1] = runs[0][1]
            else:
                runs[i - 1][2] = runs[i][2]
            del runs[i]
            k = 0
            while k + 1 < len(runs):                             # gleiche Nachbarn zusammenlegen
                if runs[k][0] == runs[k + 1][0]:
                    runs[k][2] = runs[k + 1][2]
                    del runs[k + 1]
                else:
                    k += 1
        out += runs
    if b < dur:
        out.append(["outro", b, dur])
    # Grenzen auf Hotcue, Drop oder Takt legen
    drops = [float(e["t"]) for e in events if e["type"] == "drop"]
    cues = [float(c) for c in cues]
    first_beat, bpm = res.get("first_beat"), res.get("bpm")
    edges = [0.0] + [_snap_section(x[1], cues, drops, first_beat, bpm) for x in out[1:]] + [dur]
    return [[x[0], round(max(0.0, edges[i]), 2), round(min(dur, edges[i + 1]), 2)]
            for i, x in enumerate(out) if edges[i + 1] > edges[i]]


def analyze_audio(x, bpm=None):
    dur = len(x) / SR
    db = features(x)
    fb = beat_phase(db["bass"], bpm)
    events, level = find_events(db, bpm)
    events = snap_to_beats(events, fb, bpm)
    events = [{k: (float(v) if isinstance(v, np.floating) else v) for k, v in e.items()} for e in events]
    drops = [e for e in events if e["type"] == "drop" and e.get("kind") == "after_break"]
    return {"version": VERSION, "duration": round(dur, 3), "bpm": None if bpm is None else round(float(bpm), 3), "first_beat": None if fb is None else round(fb, 3),
            "events": events, "energy": level, "drops": len(drops)}


def analyze_file(path, bpm=None):
    return analyze_audio(decode_audio(path), bpm)


# ---- Anzeige --------------------------------------------------------------------------------------------------------
def fmt(t):
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def ascii_timeline(res, width=96):
    dur = res["duration"]
    bars = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    lv = res["energy"]
    line1, line2 = [], []
    for c in range(width):
        t0, t1 = dur * c / width, dur * (c + 1) / width
        seg = lv[int(t0):max(int(t0) + 1, int(t1))] or [0]
        line1.append(bars[min(8, int(np.mean(seg) / 100 * 8.99))])
        mark = " "
        for e in res["events"]:
            a, b = e["t"], e.get("end", e["t"])
            if e["type"] in ("break", "intro", "outro") and a <= (t0 + t1) / 2 <= b:
                mark = "\u2591"
            if e["type"] == "build" and a <= (t0 + t1) / 2 <= b:
                mark = "\u25B2"
            if e["type"] == "gap" and a <= (t0 + t1) / 2 <= b:
                mark = "\u00B7"
        for e in res["events"]:
            if e["type"] == "drop" and t0 <= e["t"] < t1:
                mark = "\u25BC"
        line2.append(mark)
    return ["".join(line1), "".join(line2),
            f"0:00{' ' * (width - 9)}{fmt(dur)}", "\u2591 Break/Intro/Outro   \u25B2 Aufbau   \u00B7 kurze Stille   \u25BC Drop"]


def print_result(res, name=""):
    bpm = None if res["bpm"] is None else round(res["bpm"], 2)
    print(f"\n{name}  Laenge {fmt(res['duration'])}  BPM {bpm}  erster Beat {res['first_beat']} s")
    for ln in ascii_timeline(res):
        print(ln)
    if not res["events"]:
        print("(keine Breaks oder Drops gefunden - durchgehend gleichmaessiges Lied)")
    for e in res["events"]:
        extra = ""
        if e["type"] == "drop":
            kind = {"after_break": "nach Break", "lift": "Anstieg ohne Break (z. B. Refrain)"}.get(e.get("kind"), "Einsatz nach dem Intro")
            extra = f"  Staerke {e['strength']}  ({kind})"
        if e.get("end"):
            print(f"  {e['type']:6s} {fmt(e['t'])} ({e['t']:7.2f} s) bis {fmt(e['end'])} ({e['end']:7.2f} s){extra}")
        else:
            print(f"  {e['type']:6s} {fmt(e['t'])} ({e['t']:7.2f} s){extra}")
    print("Abschnitte: " + "  ".join(f"{typ} {fmt(a)}" for typ, a, b in find_sections(res)))


# ---- Eigentest mit einem kuenstlichen Lied ------------------------------------------------------------------------
def synth_track(bpm=128.0, seed=3):
    """Kuenstliches Lied: Intro, Groove, Break mit Aufbau und kurzer Stille, Drop, Groove, Outro."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    bar = 4 * beat
    plan = [("intro", 8), ("groove", 8), ("break", 8), ("drop", 16), ("break", 8), ("drop", 16), ("outro", 8)]
    total = int(sum(n for _, n in plan) * bar * SR)
    x = np.zeros(total, dtype=np.float32)
    t = np.arange(total) / SR
    truth, pos = [], 0.0
    for name, bars in plan:
        t0, t1 = pos, pos + bars * bar
        a, b = int(t0 * SR), int(t1 * SR)
        n = b - a
        tt = np.arange(n) / SR
        if name in ("groove", "drop", "intro", "outro"):
            for k in range(int(bars * 4)):
                s = a + int(k * beat * SR)
                m = int(0.25 * SR)
                if name in ("groove", "drop") or (name == "intro" and k >= 8 * 4 - 0 and False):
                    kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-np.arange(m) / SR * 40)) * np.arange(m) / SR) * np.exp(-np.arange(m) / SR * 12)
                    x[s:s + m] += (0.9 if name == "drop" else 0.7) * kick[: len(x[s:s + m])]
                hat_pos = s + int(beat * SR / 2)
                m2 = int(0.05 * SR)
                x[hat_pos:hat_pos + m2] += 0.12 * rng.normal(size=len(x[hat_pos:hat_pos + m2])) * np.exp(-np.arange(len(x[hat_pos:hat_pos + m2])) / SR * 60)
            if name in ("drop", "groove"):
                x[a:b] += 0.35 * np.sin(2 * np.pi * 55 * tt) * (1.0 if name == "drop" else 0.6)
            if name == "drop":
                x[a:b] += 0.12 * np.sin(2 * np.pi * 440 * tt) * (np.sin(2 * np.pi * 2 * bpm / 60 * tt) > 0)
            if name == "outro":
                x[a:b] += 0.05 * rng.normal(size=n)
        if name == "break":
            pad = 0.15 * np.sin(2 * np.pi * 220 * tt) + 0.1 * np.sin(2 * np.pi * 330 * tt)
            ramp = np.linspace(0.2, 1.0, n) ** 2
            noise = rng.normal(size=n) * 0.35 * ramp
            noise = np.convolve(noise, [1, -1], mode="same")      # Hoehenanteil: wie ein Riser
            x[a:b] += pad.astype(np.float32) * (0.5 + 0.5 * ramp) + noise.astype(np.float32)
            if bars >= 8:                                          # kurze Stille in den letzten 2 Schlaegen
                g0 = b - int(2 * beat * SR)
                x[g0:b] *= 0.02
        truth.append((name, round(t0, 2), round(t1, 2)))
        pos = t1
    x /= max(1e-6, np.abs(x).max()) * 1.1
    return x, truth, bpm


def selftest():
    x, truth, bpm = synth_track()
    res = analyze_audio(x, bpm)
    print_result(res, "KUENSTLICHES LIED (Eigentest)")
    print("\nWahrheit (so wurde das Lied gebaut):")
    for name, a, b in truth:
        print(f"  {name:7s} {a:6.2f} s bis {b:6.2f} s")
    true_drops = [b for (nme, a, b) in truth if nme == "break"]
    found = [e["t"] for e in res["events"] if e["type"] == "drop" and e.get("kind") == "after_break"]
    beat = 60.0 / bpm
    ok = len(found) == len(true_drops) and all(abs(f - t) <= beat for f, t in zip(found, true_drops))
    print(f"\nDrops: gefunden {found}, erwartet {true_drops} -> {'OK (Abweichung hoechstens ein Beat)' if ok else 'ABWEICHUNG'}")
    return ok


# ---- Bibliothek ------------------------------------------------------------------------------------------------------
def track_key(duration, bpm, kid):
    return f"{duration:.3f}_{(bpm or 0):.2f}_{int(kid or 0)}"


def out_path(outdir, r):
    return os.path.join(os.path.expanduser(outdir), track_key(r["duration"], r["bpm"], r.get("kid")) + ".json")


PATH_MAP = []          # Liste von (alt, neu): Pfad-Anfang ersetzen, wenn das NAS woanders eingebunden ist


def map_path(p):
    for old, new in PATH_MAP:
        if p.startswith(old):
            return new + p[len(old):]
    return p


def is_current(path):
    """Ist die gespeicherte Analyse mit der aktuellen Programmversion berechnet?"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("version", 1) >= VERSION
    except (OSError, ValueError):
        return False


def analyze_record(r, outdir, force=False):
    r = dict(r, path=map_path(r["path"]))
    p = out_path(outdir, r)
    if os.path.exists(p) and not force and is_current(p):
        return p, None
    res = analyze_file(r["path"], r["bpm"] if (r["bpm"] or 0) > 0 else None)
    res["artist"], res["title"], res["key"] = r.get("artist"), r.get("title"), track_key(r["duration"], r["bpm"], r.get("kid"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"                                             # erst fertig schreiben, dann umbenennen (Abbruch = keine halbe Datei)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)
    return p, res


def _job(args):
    r, outdir = args
    try:
        analyze_record(r, outdir)
        return r["id"], None
    except Exception as e:
        return r["id"], str(e)[:120]


def main():
    ap = argparse.ArgumentParser(description="Voranalyse von Musikdateien (Breaks, Aufbauten, Drops)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--bpm", type=float)
    ap.add_argument("--db")
    ap.add_argument("--find")
    ap.add_argument("--id", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="analysis")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--lift", type=float, help="Empfindlichkeit fuer Einsaetze ohne Break (Standard 0.15, hoeher = weniger Treffer)")
    ap.add_argument("--path-map", action="append", metavar="ALT=NEU",
                    help="Pfad-Anfang ersetzen, z. B. /Volumes/music=/Volumes/NAS/music (mehrfach moeglich)")
    a = ap.parse_args()
    global LIFT_MIN
    if a.lift:
        LIFT_MIN = a.lift
    for pm in (a.path_map or []):
        old, _, new = pm.partition("=")
        PATH_MAP.append((old, new))
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if a.file:
        res = analyze_file(a.file, a.bpm)
        print_result(res, os.path.basename(a.file))
        return
    if a.db:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import mixxx_bridge as mb
        lib = mb.load_library(os.path.expanduser(a.db), with_path=True)
        songs = [r for r in lib if r["duration"] >= 60 and r.get("path")]
        if a.find:
            q = a.find.lower()
            hits = [r for r in songs if q in f"{r['artist']} {r['title']}".lower()]
            for r in hits[:30]:
                print(f"{r['id']:6d}  {r['artist'] or '-'} - {r['title']}  [{r['duration']:.1f} s, {r['bpm']:.1f} BPM]  {r['path']}")
            print(f"{len(hits)} Treffer" + (" (erste 30 gezeigt)" if len(hits) > 30 else ""))
            return
        if a.id:
            r = next((r for r in songs if r["id"] == a.id), None)
            if r is None:
                sys.exit("Titel-Nummer nicht gefunden (oder zu kurz / ohne Pfad).")
            if not os.path.exists(map_path(r["path"])):
                sys.exit(explain_missing(map_path(r["path"])))
            p, res = analyze_record(r, a.out, force=True)
            print_result(res, f"{r['artist']} - {r['title']}")
            print(f"\nGespeichert: {p}")
            return
        if a.all:
            from multiprocessing import Pool
            todo = [r for r in songs if a.force or not is_current(out_path(a.out, r))]
            # NAS-Vorpruefung: welche Laufwerke sind erreichbar?
            def vol_of(path):
                pp = path.split(os.sep)
                return os.sep.join(pp[:3]) if path.startswith("/Volumes/") and len(pp) > 2 else os.sep.join(pp[:2])
            vols = {}
            for r in todo:
                v = vol_of(map_path(r["path"]))
                vols.setdefault(v, [0, os.path.exists(v)])[0] += 1
            for vol, (cnt, ok) in sorted(vols.items(), key=lambda kv: -kv[1][0])[:6]:
                print(f"  {'erreichbar       ' if ok else 'NICHT ERREICHBAR'} {vol}  ({cnt} Titel)")
            if todo and sum(c for c, ok in vols.values() if ok) == 0:
                sys.exit("Kein einziges Laufwerk erreichbar. NAS verbinden (Finder: Gehe zu -> Mit Server verbinden) "
                         "oder mit --path-map den neuen Pfad angeben.")
            todo = [r for r in todo if vols[vol_of(map_path(r["path"]))][1]]
            seen, uniq = set(), []
            for r in todo:                                        # gleiche Lieder (Doppelte) nur einmal
                k = track_key(r["duration"], r["bpm"], r.get("kid"))
                if k not in seen:
                    seen.add(k)
                    uniq.append(r)
            if a.limit:
                uniq = uniq[:a.limit]
            print(f"{len(uniq)} Lieder zu analysieren ({len(songs) - len(todo)} schon fertig), {a.jobs} parallel ...")
            done = errs = 0
            with Pool(a.jobs) as pool:
                for rid, err in pool.imap_unordered(_job, [(r, a.out) for r in uniq]):
                    done += 1
                    if err:
                        errs += 1
                        print(f"  Fehler bei Titel {rid}: {err}")
                    if done % 25 == 0 or done == len(uniq):
                        print(f"  {done}/{len(uniq)} fertig, {errs} Fehler")
            return
    ap.print_help()


if __name__ == "__main__":
    main()
