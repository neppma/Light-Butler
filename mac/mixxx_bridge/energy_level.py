#!/usr/bin/env python3
"""
energy_level.py - Energiestufe 1 bis 9 eines Liedes schaetzen, geeicht an den Werten von Mixed In Key (Wunsch von Markus, 06.11.2026).

Mixed In Key ist nicht mehr da, rund 8800 Lieder haben aber schon seine Stufe ("Energy 7" im Kommentar). Daraus lernt dieses
Programm: Es misst je Lied einige Merkmale (Lautheit und ihre Schwankung, Bass- und Hoehenanteil, Helligkeit, Anschlaege pro
Sekunde, Pulsstaerke, Tempo) und rechnet ein kleines Modell, das daraus die Stufe schaetzt. Nur numpy, keine neuen Pakete.

    python3 energy_level.py messen --liste musik.json --aus merkmale.jsonl [--anzahl 1500] [--jobs 3]
    python3 energy_level.py eichen --merkmale merkmale.jsonl [--modell modell.json]

Messen haengt an (bereits gemessene Pfade werden uebersprungen), laeuft gebremst (nice 10).

Geeicht am 07.11.2026 an 8836 Liedern (Kreuzprobe): 58,7 % genau wie Mixed In Key, 96,4 % hoechstens eine Stufe daneben;
E8 und E9 schaetzt das Modell nie (dort sagt es E7). Das Modell liegt in energie_modell.json neben diesem Programm.

In der Mixxx-Bruecke (Estimator): Lieder ohne Stufe von Mixed In Key bekommen die geschaetzte Stufe, gekennzeichnet als
geschaetzt (im Panel "E6~"). Messwerte in ~/Light-Butler-Daten/energie/merkmale.jsonl, neue Lieder misst ein eigener Prozess mit
nice 10 nach. In die MP3 (ID3, TXXX "EnergyLevel" wie Mixed In Key) schreibt die Bruecke nur mit der Einstellung
energy_write am Pi (Standard aus), nie ueber eine Stufe von Mixed In Key.
"""
import argparse
import json
import math
import os
import random
import sys
import threading
import time

import numpy as np
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SR = 22050
DUR_CAP_S = 15 * 60.0         # Laenge fuer die Schaetzung hoechstens 15 Minuten (DJ-Mixe, Konzerte; 14.11.2026)
NFFT = 2048
HOP = 1024
# Grundmerkmale (gehen auch quadratisch ins Modell): Lautheit, Dynamik, Klangbalance, Helligkeit, Rhythmus, Tempo, Tonart
FEATS = ("loud_mean", "loud_p90", "loud_p10", "loud_std", "loud_frac", "bass_rel", "high_rel", "mid_rel", "cent_mean",
         "cent_std", "flux_mean", "onset_rate", "pulse", "bpm", "dur", "dyn_range", "loud_peak", "sub_rel", "hf_flux",
         "flat_mean", "rolloff", "zcr", "beat_reg", "low_pulse", "minor")
N_MFCC = 13                      # Klangfarbe: Mittel und Streuung je Koeffizient, gehen linear ins Modell
N_MEL = 40
MODEL_FILE = os.path.join(HERE, "energie_modell.json")
DATA_DIR = os.path.join(_pfad.daten(), "energie")   # gemeinsame Ablage von Mixxx-App und Helfer (Fehlerbericht 07.11.2026: der Helfer hatte eine eigene)
FEATS_FILE = "merkmale.jsonl"
WRITTEN_FILE = "geschrieben.json"
TAG_DESC = "EnergyLevel"                 # wie Mixed In Key
SRC_DESC = "EnergyLevelSource"           # unser Kennzeichen: geschaetzt vom Light-Butler
SRC_VALUE = "Light-Butler (geschaetzt)"


# ---- Messen ------------------------------------------------------------------------------------------------------
def _mel_matrix():
    f = np.fft.rfftfreq(NFFT, 1.0 / SR)
    mel = lambda h: 2595.0 * np.log10(1.0 + h / 700.0)          # noqa: E731
    pts = 700.0 * (10 ** (np.linspace(mel(30.0), mel(11000.0), N_MEL + 2) / 2595.0) - 1.0)
    M = np.zeros((N_MEL, len(f)), np.float32)
    for i in range(N_MEL):
        a, b, c = pts[i], pts[i + 1], pts[i + 2]
        M[i] = np.clip(np.minimum((f - a) / (b - a), (c - f) / (c - b)), 0.0, None)
    k = np.arange(N_MEL)
    D = np.cos(np.pi / N_MEL * (k[None, :] + 0.5) * np.arange(N_MFCC)[:, None]).astype(np.float32)   # DCT-II
    return M, D


def measure(x, bpm=0.0, kid=0):
    """Merkmale eines Mono-Signals (SR Hz). Rueckgabe: dict mit den Namen aus FEATS und mfcc_m*/mfcc_s*."""
    n = 1 + max(0, (len(x) - NFFT) // HOP)
    if n < 50:
        raise ValueError("Lied zu kurz")
    win = np.hanning(NFFT).astype(np.float32)
    freqs = np.fft.rfftfreq(NFFT, 1.0 / SR).astype(np.float32)
    band = {"sub": (20, 60), "bass": (60, 250), "mid": (250, 4000), "high": (4000, 11000)}
    idx = {k: (freqs >= lo) & (freqs < hi) for k, (lo, hi) in band.items()}
    hf = freqs >= 2000
    tot = np.zeros(n, np.float32)
    bp = {k: np.zeros(n, np.float32) for k in band}
    cent = np.zeros(n, np.float32)
    flux = np.zeros(n, np.float32)
    hflux = np.zeros(n, np.float32)
    flat = np.zeros(n, np.float32)
    roll = np.zeros(n, np.float32)
    lowe = np.zeros(n, np.float32)
    mf = np.zeros((n, N_MFCC), np.float32)
    M, D = _mel_matrix()
    prev = None
    chunk = 512
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        fr = np.stack([x[i * HOP:i * HOP + NFFT] for i in range(s, e)]) * win
        mag = np.abs(np.fft.rfft(fr, axis=1)).astype(np.float32)
        p = mag ** 2
        tot[s:e] = p.sum(axis=1)
        for k, ix in idx.items():
            bp[k][s:e] = p[:, ix].sum(axis=1)
        cent[s:e] = (p * freqs).sum(axis=1) / (p.sum(axis=1) + 1e-12)
        lm = np.log1p(mag * 100.0)
        d = np.diff(np.vstack([lm[:1] if prev is None else prev[None, :], lm]), axis=0)
        d = np.maximum(d, 0.0)
        flux[s:e] = d.sum(axis=1)
        hflux[s:e] = d[:, hf].sum(axis=1)
        prev = lm[-1]
        flat[s:e] = np.exp(np.log(p[:, 1:] + 1e-12).mean(axis=1)) / (p[:, 1:].mean(axis=1) + 1e-12)
        cs = np.cumsum(p, axis=1)
        roll[s:e] = freqs[np.minimum(np.argmax(cs >= 0.85 * cs[:, -1:], axis=1), len(freqs) - 1)]
        lowe[s:e] = p[:, (freqs >= 30) & (freqs < 150)].sum(axis=1)
        mf[s:e] = np.log(p @ M.T + 1e-8) @ D.T
    db = 10.0 * np.log10(tot + 1e-10)
    peak = np.percentile(db, 99)
    act = db > peak - 40.0                                   # Stille am Anfang und Ende nicht mitzaehlen
    if act.sum() < 50:
        act = np.ones(n, bool)
    dba = db[act]
    p90, p10 = np.percentile(dba, 90), np.percentile(dba, 10)
    rel = {k: float(10.0 * np.log10((v[act].mean() + 1e-12) / (tot[act].mean() + 1e-12))) for k, v in bp.items()}
    fa = flux[act]
    fn = (fa - np.median(fa)) / (np.std(fa) + 1e-9)
    thr = 1.5
    peaks = (fn[1:-1] > thr) & (fn[1:-1] >= fn[:-2]) & (fn[1:-1] >= fn[2:])
    dur_act = act.sum() * HOP / SR
    # Pulsstaerke: Autokorrelation des Anschlag-Verlaufs im Bereich 60-180 BPM
    env = fa - fa.mean()
    ac = np.correlate(env[:4096], env[:4096], mode="full")[min(len(env), 4096) - 1:]
    fps = SR / HOP
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 60)
    pulse = float(ac[lo:hi].max() / (ac[0] + 1e-9)) if len(ac) > hi else 0.0
    # Bass-Puls (Kick) und Gleichmaessigkeit des Beats: Autokorrelation des Bass-Verlaufs, Abstand Spitze zu Mittel
    le = np.log1p(lowe[act])
    le = np.maximum(np.diff(le, prepend=le[:1]), 0.0)
    le = le - le.mean()
    acl = np.correlate(le[:4096], le[:4096], mode="full")[min(len(le), 4096) - 1:]
    low_pulse = float(acl[lo:hi].max() / (acl[0] + 1e-9)) if len(acl) > hi else 0.0
    beat_reg = float((acl[lo:hi].max() - acl[lo:hi].mean()) / (acl[0] + 1e-9)) if len(acl) > hi else 0.0
    zc = np.abs(np.diff(np.signbit(x[:: 2]).astype(np.int8))).mean() if len(x) > 4 else 0.0
    mfa = mf[act]
    out_m = {f"mfcc_m{i}": float(v) for i, v in enumerate(mfa.mean(axis=0))}
    out_s = {f"mfcc_s{i}": float(v) for i, v in enumerate(mfa.std(axis=0))}
    return {**out_m, **out_s, "flat_mean": float(flat[act].mean()), "rolloff": float(roll[act].mean()), "zcr": float(zc),
            "beat_reg": beat_reg, "low_pulse": low_pulse, "minor": 1.0 if int(kid or 0) > 12 else 0.0,
"loud_mean": float(dba.mean()), "loud_p90": float(p90), "loud_p10": float(p10), "loud_std": float(dba.std()),
            "loud_frac": float((dba > p90 - 6.0).mean()), "bass_rel": rel["bass"], "high_rel": rel["high"], "mid_rel": rel["mid"],
            "sub_rel": rel["sub"], "cent_mean": float(cent[act].mean()), "cent_std": float(cent[act].std()),
            "flux_mean": float(fa.mean()), "onset_rate": float(peaks.sum() / max(1.0, dur_act)), "pulse": pulse,
            "bpm": float(bpm or 0.0), "dur": float(len(x) / SR), "dyn_range": float(p90 - p10), "loud_peak": float(peak),
            "hf_flux": float(hflux[act].mean())}


def measure_file(path, bpm=0.0, kid=0):
    import analyze_track as at
    return measure(at.decode_audio(path), bpm, kid)


def _init(nice):
    from prio import lower_priority                    # Mac: os.nice; Windows: "Niedriger als normal"
    lower_priority(nice)


def _job(a):
    r = a
    try:
        f = measure_file(r.get("file") or r["path"], r.get("bpm") or 0.0, r.get("kid") or 0)
        return {"path": r["path"], "lvl": r.get("lvl") or 0, "genre": r.get("genre") or "", "f": f}
    except Exception as e:                                  # noqa: BLE001  (unlesbare Datei: weiter mit der naechsten)
        return {"path": r["path"], "err": str(e)[:200]}


def cmd_measure(a):
    with open(a.liste, encoding="utf-8") as f:
        songs = json.load(f)
    songs = songs.get("tracks", songs) if isinstance(songs, dict) else songs
    songs = [s for s in songs if s.get("path") and not s.get("bad")]
    done = set()
    if os.path.exists(a.aus):
        with open(a.aus, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["path"])
                except (ValueError, KeyError):
                    pass
    todo = [s for s in songs if s["path"] not in done and os.path.exists(s["path"])]
    if a.anzahl:                                             # Stichprobe: gleich viele je Stufe, damit seltene Stufen vorkommen
        rng = random.Random(7)
        by = {}
        for s in todo:
            by.setdefault(int(s.get("lvl") or 0), []).append(s)
        for v in by.values():
            rng.shuffle(v)
        pick, i = [], 0
        while len(pick) < a.anzahl and any(i < len(v) for v in by.values()):
            for k in sorted(by):
                if i < len(by[k]) and len(pick) < a.anzahl:
                    pick.append(by[k][i])
            i += 1
        todo = pick
    print(f"Messe {len(todo)} Lieder ({len(done)} schon gemessen) ...", flush=True)
    from multiprocessing import Pool
    n = 0
    with Pool(a.jobs, initializer=_init, initargs=(a.nice,)) as pool, open(a.aus, "a", encoding="utf-8") as out:
        for res in pool.imap_unordered(_job, todo, chunksize=2):
            out.write(json.dumps(res, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            if n % 50 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
    print("fertig", flush=True)


# ---- Eichen ------------------------------------------------------------------------------------------------------
def load_feats(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if "f" in r:
                rows.append(r)
    return rows


def design(rows, genres=None):
    """Merkmalsmatrix: Merkmale, ihre Quadrate und ein paar Produkte, dazu die haeufigsten Genres als 0/1."""
    X = np.array([[r["f"][k] for k in FEATS] for r in rows], float)
    X[:, FEATS.index("bpm")] = np.where(X[:, FEATS.index("bpm")] > 0, X[:, FEATS.index("bpm")], 120.0)
    # Laenge hoechstens DUR_CAP_S (Fehlerbericht 14.11.2026: Mix von 134 Minuten bekam E1, das Modell kennt Lieder von wenigen
    # Minuten und rechnete die Laenge weit darueber hinaus). Lieder bis 15 Minuten (ueber 99 %) bleiben genau gleich.
    X[:, FEATS.index("dur")] = np.minimum(X[:, FEATS.index("dur")], DUR_CAP_S)
    MF = np.array([[r["f"].get(f"mfcc_m{i}", 0.0) for i in range(N_MFCC)] + [r["f"].get(f"mfcc_s{i}", 0.0) for i in range(N_MFCC)] for r in rows], float)
    cols = [X, X ** 2, MF]
    pairs = [("loud_mean", "onset_rate"), ("loud_mean", "bpm"), ("bass_rel", "pulse"), ("onset_rate", "bpm"), ("loud_frac", "loud_mean")]
    cols.append(np.stack([X[:, FEATS.index(a)] * X[:, FEATS.index(b)] for a, b in pairs], axis=1))
    if genres:
        g = [str(r.get("genre") or "").strip().lower() for r in rows]
        cols.append(np.array([[1.0 if x == k else 0.0 for k in genres] for x in g]))
    return np.hstack(cols)


class Model:
    """Ridge-Regression auf standardisierten Merkmalen, danach Schwellen je Stufe so gelegt, dass moeglichst viele Stufen
    genau stimmen (die Verteilung von Mixed In Key bleibt erhalten)."""

    def fit(self, rows, lam=3.0, genres=None):
        self.genres = genres or []
        X = design(rows, self.genres)
        y = np.array([r["lvl"] for r in rows], float)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        Z1 = np.hstack([Z, np.ones((len(Z), 1))])
        reg = lam * np.eye(Z1.shape[1])
        reg[-1, -1] = 0.0
        self.w = np.linalg.solve(Z1.T @ Z1 + reg, Z1.T @ y)
        s = Z1 @ self.w
        self.cuts = self._cuts(s, y)
        return self

    @staticmethod
    def _cuts(s, y):
        """Schwellen zwischen den Stufen: je Grenze die, bei der am meisten Lieder richtig liegen (von unten nach oben)."""
        cuts = []
        levels = sorted(set(int(v) for v in y))
        for a, b in zip(levels, levels[1:]):
            cand = np.unique(np.percentile(s, np.linspace(0, 100, 401)))
            m = (y == a) | (y == b)
            if not m.any():
                cuts.append(cuts[-1] if cuts else float(s.min()))
                continue
            ss, yy = s[m], y[m]
            best = max(cand, key=lambda c: ((ss < c) & (yy == a)).sum() + ((ss >= c) & (yy == b)).sum())
            cuts.append(float(max(best, cuts[-1] if cuts else -1e9)))
        return {"levels": levels, "cuts": cuts}

    def score(self, rows):
        Z = (design(rows, self.genres) - self.mu) / self.sd
        return np.hstack([Z, np.ones((len(Z), 1))]) @ self.w

    def predict(self, rows):
        s = self.score(rows)
        lv, cu = self.cuts["levels"], self.cuts["cuts"]
        return np.array([lv[int(np.searchsorted(cu, v, side="right"))] for v in s])

    def to_json(self):
        return {"feats": FEATS, "genres": self.genres, "mu": self.mu.tolist(), "sd": self.sd.tolist(), "w": self.w.tolist(), "cuts": self.cuts}

    @classmethod
    def from_json(cls, d):
        if list(d.get("feats") or []) != list(FEATS):
            raise ValueError("Modell passt nicht zu diesen Merkmalen")
        m = cls()
        m.genres = [str(g) for g in d.get("genres") or []]
        m.mu, m.sd, m.w = np.array(d["mu"], float), np.array(d["sd"], float), np.array(d["w"], float)
        m.cuts = {"levels": [int(v) for v in d["cuts"]["levels"]], "cuts": [float(v) for v in d["cuts"]["cuts"]]}
        if not (len(m.mu) == len(m.sd) == len(m.w) - 1) or len(m.cuts["cuts"]) != len(m.cuts["levels"]) - 1:
            raise ValueError("Modell unvollstaendig")
        return m


def evaluate(rows, folds=5, **kw):
    """Kreuzprobe: das Modell sieht die geprueften Lieder beim Lernen nie. (genau, hoechstens 1 daneben, Verwechslungstabelle)."""
    rng = random.Random(1)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    pred = np.zeros(len(rows))
    for k in range(folds):
        test = set(idx[k::folds])
        tr = [rows[i] for i in idx if i not in test]
        te = sorted(test)
        m = Model().fit(tr, **kw)
        pred[te] = m.predict([rows[i] for i in te])
    y = np.array([r["lvl"] for r in rows])
    return float((pred == y).mean()), float((np.abs(pred - y) <= 1).mean()), pred, y


def cmd_calibrate(a):
    rows = [r for r in load_feats(a.merkmale) if 1 <= int(r.get("lvl") or 0) <= 9]
    print(f"{len(rows)} Lieder mit Stufe von Mixed In Key")
    cnt = {}
    for r in rows:
        g = str(r.get("genre") or "").strip().lower()
        if g:
            cnt[g] = cnt.get(g, 0) + 1
    genres = [g for g, n in sorted(cnt.items(), key=lambda x: -x[1]) if n >= 15][:25]
    best = None
    for lam in (0.3, 1.0, 3.0, 10.0, 30.0):
        for gs in ([], genres):
            ex, near, pred, y = evaluate(rows, lam=lam, genres=gs)
            print(f"  lam {lam:5.1f}  Genres {'ja ' if gs else 'nein'}: genau {ex * 100:5.1f} %, hoechstens 1 daneben {near * 100:5.1f} %")
            if best is None or ex > best[0]:
                best = (ex, near, lam, gs, pred, y)
    ex, near, lam, gs, pred, y = best
    print(f"Bestes: lam {lam}, Genres {'ja' if gs else 'nein'}: genau {ex * 100:.1f} %, hoechstens 1 daneben {near * 100:.1f} %")
    print("Zeile = Mixed In Key, Spalte = Schaetzung")
    lv = list(range(1, 10))
    print("      " + "".join(f"{v:>6}" for v in lv))
    for a_ in lv:
        print(f"  E{a_}  " + "".join(f"{int(((y == a_) & (pred == b)).sum()):>6}" for b in lv))
    if a.modell:
        m = Model().fit(rows, lam=lam, genres=gs)
        with open(a.modell, "w", encoding="utf-8") as f:
            json.dump(dict(m.to_json(), exact=ex, near=near, n=len(rows)), f)
        print("Modell gespeichert:", a.modell)


# ---- In der Mixxx-Bruecke ----------------------------------------------------------------------------------------
def measure_list(todo, out_path, pause_ev=None, nice=10):
    """Eigener Prozess: misst die Lieder aus todo [{path, file, bpm, kid}] nacheinander und haengt sie an out_path an.
    Wartet, solange pause_ev gesetzt ist (Analyse beim Laden hat Vorrang) und solange das Laufwerk fehlt."""
    _init(nice)
    with open(out_path, "a", encoding="utf-8") as out:
        for r in todo:
            while pause_ev is not None and pause_ev.is_set():
                time.sleep(0.5)
            f = r.get("file") or r["path"]
            parts = f.split(os.sep)
            while f.startswith("/Volumes/") and len(parts) > 2 and not os.path.exists(os.sep.join(parts[:3])):
                time.sleep(60)                               # NAS oder Stick nicht verbunden: warten, nichts als Fehler merken
            out.write(json.dumps(_job(r), ensure_ascii=False) + "\n")
            out.flush()
            time.sleep(0.5)


def write_energy_tag(path, level):
    """Stufe als ID3-Rahmen TXXX "EnergyLevel" in die MP3 schreiben (wie Mixed In Key, nur die Zahl), dazu TXXX
    "EnergyLevelSource". Lesen und Schreiben ueber id3_tags (Musik und Fingerabdruck bleiben gleich). Rueckgabe: "ok",
    "gleich", "mik" (Stufe von Mixed In Key vorhanden, nie ueberschreiben) oder ein Grund, warum es nicht geht."""
    import id3_tags as it
    level = int(level)
    if not 1 <= level <= 9:
        return "Stufe ungueltig"
    if not path.lower().endswith(".mp3"):
        return "keine MP3"
    r = it.read(path)
    if isinstance(r, str):
        return r
    ver, old_size, frames = r
    descs = {}
    for fid, fl, _raw, body in frames:
        if fid == b"TXXX" and fl == b"\x00\x00":
            descs.setdefault(it.txxx_desc(body), []).append(body)
    ours = SRC_VALUE.lower().encode("latin-1")
    if TAG_DESC.lower() in descs and not any(ours in b.lower() for b in descs.get(SRC_DESC.lower(), [])):
        return "mik"
    new_body = it.txxx_body(TAG_DESC, str(level))
    if any(b == new_body for b in descs.get(TAG_DESC.lower(), [])) and SRC_DESC.lower() in descs:
        return "gleich"
    keep = [raw for fid, fl, raw, body in frames
            if not (fid == b"TXXX" and fl == b"\x00\x00" and it.txxx_desc(body) in (TAG_DESC.lower(), SRC_DESC.lower()))]
    it.write(path, ver, old_size, b"".join(keep) + it.frame(b"TXXX", new_body, ver) + it.frame(b"TXXX", it.txxx_body(SRC_DESC, SRC_VALUE), ver))
    return "ok"


def own_energy(path):
    """Unsere geschaetzte Stufe aus der MP3 (TXXX EnergyLevel mit unserem Kennzeichen), sonst "" (keine oder von Mixed In Key)."""
    import id3_tags as it
    r = it.read(path) if path.lower().endswith(".mp3") else "keine MP3"
    if isinstance(r, str):
        return ""
    descs = {}
    for fid, fl, _raw, body in r[2]:
        if fid == b"TXXX" and fl == b"\x00\x00":
            descs.setdefault(it.txxx_desc(body), []).append(body)
    ours = SRC_VALUE.lower().encode("latin-1")
    if not any(ours in b.lower() for b in descs.get(SRC_DESC.lower(), [])):
        return ""
    for b in descs.get(TAG_DESC.lower(), []):
        _d, rest = it._split0(b[0], b[1:])
        return it._decode(b[0], rest).strip("\x00 ")
    return ""


def remove_energy_tag(path):
    """Unsere geschaetzte Stufe wieder aus der MP3 nehmen (kurze Stuecke, Wunsch 09.11.2026). Nie eine von Mixed In Key.
    Rueckgabe: "ok", "keine" (nichts von uns drin) oder ein Grund."""
    import id3_tags as it
    if not own_energy(path):
        return "keine"
    r = it.read(path)
    if isinstance(r, str):
        return r
    ver, old_size, frames = r
    keep = [raw for fid, fl, raw, body in frames
            if not (fid == b"TXXX" and fl == b"\x00\x00" and it.txxx_desc(body) in (TAG_DESC.lower(), SRC_DESC.lower()))]
    it.write(path, ver, old_size, b"".join(keep))
    return "ok"


class Estimator:
    """Geschaetzte Energiestufe je Pfad (Mixxx-Bruecke). level(path) -> 1..9 oder None. Neue Lieder misst start() in einem
    eigenen Prozess, refresh() liest die neuen Messwerte nach, write_tick() schreibt mit der Einstellung in die MP3s."""

    def __init__(self, base=DATA_DIR, model_path=MODEL_FILE, log=None):
        self.base, self.log = base, log or (lambda t: None)
        self.feats_path = os.path.join(base, FEATS_FILE)
        self.written_path = os.path.join(base, WRITTEN_FILE)
        self.est, self.measured, self.pos, self.proc, self.writer = {}, set(), 0, None, None
        self.stop_ev = threading.Event()                      # stop(): Schreiben und Messen beenden (Helfer gibt an die Bruecke ab)
        self.model = None
        try:
            with open(model_path, encoding="utf-8") as f:
                self.model = Model.from_json(json.load(f))
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.log(f"Energie-Schaetzung aus: Modell nicht lesbar ({e})")
        try:
            with open(self.written_path, encoding="utf-8") as f:
                self.written = {str(k): v for k, v in dict(json.load(f)).items()}
        except (OSError, ValueError, TypeError):
            self.written = {}
        self.refresh()

    def refresh(self):
        """Neue Zeilen der Messwerte lesen und schaetzen. True = neue Schaetzungen."""
        if self.model is None:
            return False
        try:
            with open(self.feats_path, "rb") as f:
                f.seek(self.pos)
                raw = f.read()
        except OSError:
            return False
        end = raw.rfind(b"\n") + 1                            # halbe letzte Zeile (wird gerade geschrieben) erst beim naechsten Mal
        self.pos += end
        rows = []
        for line in raw[:end].decode("utf-8", "replace").splitlines():
            try:
                r = json.loads(line)
                p = str(r["path"])
            except (ValueError, KeyError, TypeError):
                continue
            self.measured.add(p)
            if isinstance(r.get("f"), dict) and all(k in r["f"] for k in FEATS):
                rows.append(r)
        if not rows:
            return False
        for r, v in zip(rows, self.model.predict(rows)):
            self.est[r["path"]] = int(v)
        return True

    def level(self, path):
        return self.est.get(path)

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
        return self.proc is not None and self.proc.is_alive()

    def start(self, songs, pause_ev=None):
        """songs: [{path, file, bpm, kid, genre}] ohne Stufe von Mixed In Key. Misst die noch nicht gemessenen (eigener Prozess)."""
        if self.model is None or self.running():
            return 0
        todo = [s for s in songs if s.get("path") and s["path"] not in self.measured]
        if not todo:
            return 0
        import multiprocessing as mp
        os.makedirs(self.base, exist_ok=True)
        self.proc = mp.get_context("spawn").Process(target=measure_list, args=(todo, self.feats_path, pause_ev), daemon=True)
        self.proc.start()
        self.log(f"Energie-Schaetzung: {len(todo)} neue Lieder werden gemessen")
        return len(todo)

    def _save_written(self):
        tmp = self.written_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.written, f, ensure_ascii=False)
        os.replace(tmp, self.written_path)

    def write_tick(self, songs, busy=lambda p: False, gap_s=0.3):
        """Geschaetzte Stufen in die MP3s schreiben (eigener Thread, je Lied einmal, erneut nur bei anderer Stufe).
        songs: [(Pfad in Mixxx, Datei am Mac)] ohne Stufe von Mixed In Key. busy(p) = gerade in einem Deck geladen: auslassen."""
        if self.writer is not None and self.writer.is_alive():
            return
        todo = [(p, f, self.est[p]) for p, f in songs if p in self.est and not isinstance(self.written.get(p), str) and self.written.get(p) != self.est[p] and f.lower().endswith(".mp3")]
        if not todo:
            return

        def run():
            n = 0
            for p, f, lv in todo:
                if self.stop_ev.is_set():
                    break
                import stick_hold
                if stick_hold.held():                     # Stick wird ausgeworfen: aufhoeren
                    break
                if busy(p) or not os.path.exists(f):
                    continue
                try:
                    res = write_energy_tag(f, lv)
                except OSError as e:
                    res = f"Fehler: {e}"
                if res in ("ok", "gleich"):
                    n += res == "ok"
                    self.written[p] = lv
                elif res == "mik":
                    self.written[p] = "mik"
                else:
                    self.written[p] = res[:60]
                time.sleep(gap_s)
                if n and n % 50 == 0:
                    self._save_written()
            self._save_written()
            if n:
                self.log(f"Energie-Schaetzung: Stufe in {n} MP3s geschrieben")
        self.writer = threading.Thread(target=run, name="energie-schreiben", daemon=True)
        self.writer.start()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Energiestufe 1-9 schaetzen, geeicht an Mixed In Key")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("messen")
    m.add_argument("--liste", required=True, help="Liedliste (JSON von /api/musik des Pi)")
    m.add_argument("--aus", required=True)
    m.add_argument("--anzahl", type=int, default=0)
    m.add_argument("--jobs", type=int, default=3)
    m.add_argument("--nice", type=int, default=10, help="Bremse (0 = volle Kraft, 10 = nachrangig)")
    e = sub.add_parser("eichen")
    e.add_argument("--merkmale", required=True)
    e.add_argument("--modell", default="")
    a = ap.parse_args(argv)
    if a.cmd == "messen":
        cmd_measure(a)
    else:
        cmd_calibrate(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
