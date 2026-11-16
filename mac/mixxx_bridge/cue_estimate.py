"""Cue-Punkte ohne Mixxx (Wunsch von Markus, 11.11.2026: Mixed In Key wird nicht mehr verwendet, viele Lieder haben keine Hotcues).

Zwei Quellen fuer Lieder, die in Mixxx keine Hotcues haben:
  1. aus der MP3: Mixed In Key und Serato haben ihre Cues in den Tag geschrieben (GEOB "CuePoints" als JSON, sonst
     "Serato Markers2"). Mixxx liest das nur beim Aufnehmen einer Datei; der Light-Butler liest es selbst.
  2. geschaetzt aus der eigenen Analyse: erster Beat (bzw. Ende des Intros), Drops, Abschnittsanfaenge (vers, main, break,
     outro), auf das Beat-Raster gerastet, hoechstens MAX_CUES, nie zwei naeher als MIN_GAP_S. Ab LONG_S (Mixe) gleichmaessig
     ueber das ganze Lied verteilt; alte LB-Cues solcher Lieder ersetzt die Bruecke, solange sie unveraendert sind (14.11.2026).

Fuers Licht nur mit der Einstellung cue_est am Pi (Standard aus: ohne sie bleibt das Licht Bild fuer Bild gleich).
In die Mixxx-Datenbank kommen die geschaetzten nur mit der Einstellung cue_write (Standard aus), beim Start der App vor Mixxx
(mixxx_uebertragen.py --cues), nur in Lieder ganz ohne Hotcues, Name "LB ..." und eigene Farbe. Loescht Markus sie in Mixxx,
kommen sie nie wieder (geschrieben.json).
"""
import base64
import json
import os
import re
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

MAX_CUES = 8                   # so viele Hotcue-Knoepfe zeigt Mixxx ohne Umschalten
MIN_GAP_S = 8.0
DROP_MIN = 0.5                 # nur deutliche Drops (Staerke der Analyse)
LB_COLOR = 0x9B30FF            # Farbe der geschaetzten Cues in Mixxx (lila), damit Markus sie erkennt
LABELS = {"start": "LB Start", "drop": "LB Drop", "vers": "LB Vers", "main": "LB Hauptteil", "break": "LB Break", "outro": "LB Outro",
          "part": "LB Teil"}
LONG_S = 15 * 60.0             # ab dieser Laenge (DJ-Mixe, Live-Sets) gleichmaessig verteilen (Wunsch 14.11.2026)
PRIO = {"start": 4, "drop": 3, "main": 2, "break": 2, "outro": 1, "vers": 1}
DATA_DIR = os.path.join(_pfad.daten(), "cues")
PENDING_FILE, WRITTEN_FILE = "mixxx_neu.json", "geschrieben.json"


def _b64(data):
    d = re.sub(rb"[^A-Za-z0-9+/]", b"", data)
    if len(d) % 4 == 1:
        d = d[:-1]
    return base64.b64decode(d + b"=" * (-len(d) % 4))


def _geob(body):
    """(Beschreibung, Daten) eines GEOB-Rahmens (Text Latin-1/UTF-8, wie Mixed In Key und Serato schreiben)."""
    rest = body[1:]
    _mime, _, rest = rest.partition(b"\x00")
    _fn, _, rest = rest.partition(b"\x00")
    desc, _, data = rest.partition(b"\x00")
    return desc.decode("latin-1", "replace"), data


def serato_markers2(raw):
    """Positionen in s aus dem Inhalt von "Serato Markers2" (base64, darin CUE-Eintraege mit Position in ms)."""
    b = _b64(raw[2:] if raw[:2] == b"\x01\x01" else raw)
    out, i = [], 2 if b[:2] == b"\x01\x01" else 0
    while i < len(b):
        j = b.find(b"\x00", i)
        if j < 0 or j - i > 20:
            break
        name, i = b[i:j], j + 1
        if i + 4 > len(b):
            break
        n = int.from_bytes(b[i:i + 4], "big")
        data, i = b[i + 4:i + 4 + n], i + 4 + n
        if name == b"CUE" and len(data) >= 6:
            out.append(round(int.from_bytes(data[2:6], "big") / 1000.0, 2))
        if not name:
            break
    return sorted(out)


def file_cues(path):
    """Cues aus dem Tag der MP3 in s (Mixed In Key "CuePoints", sonst Serato), [] = keine."""
    if not str(path).lower().endswith(".mp3"):
        return []
    import id3_tags as it
    try:
        r = it.read(path)
    except OSError:
        return []
    if isinstance(r, str):
        return []
    mik, ser = [], []
    for fid, _fl, _raw, body in r[2]:
        if fid != b"GEOB" or not body:
            continue
        try:
            desc, data = _geob(body)
            if desc == "CuePoints":
                d = json.loads(_b64(data).decode("utf-8", "replace"))
                mik = sorted(round(float(c["time"]) / 1000.0, 2) for c in d.get("cues") or [] if isinstance(c, dict) and c.get("time") is not None)
            elif desc == "Serato Markers2":
                ser = serato_markers2(data)
        except (ValueError, KeyError, TypeError):
            continue
    return [c for c in (mik or ser) if c >= 0]


def _snap(t, bpm, fb):
    if bpm and bpm > 0 and fb is not None:
        beat = 60.0 / bpm
        return round(fb + round((t - fb) / beat) * beat, 2)
    return round(t, 2)


def _cands(res, sections):
    """Kandidaten [(s, Art)] und die Abschnitte (find_sections, wenn nicht mitgegeben)."""
    if sections is None:
        try:
            import analyze_track as at
            sections = at.find_sections(res, [])
        except Exception:                                    # noqa: BLE001
            sections = []
    cands = []
    start = float(res.get("first_beat") or 0)
    if sections and sections[0][0] == "intro" and len(sections) > 1:
        start = float(sections[1][1])                         # wo die Musik nach dem Intro richtig losgeht
    cands.append((start, "start"))
    for e in res.get("events") or []:
        if e.get("type") == "drop" and float(e.get("strength") or 0) >= DROP_MIN:
            cands.append((float(e.get("t") or 0), "drop"))
    prev = sections[0][0] if sections else ""
    for kind, a, _b in (sections or [])[1:]:
        if kind != prev and kind in PRIO:
            cands.append((float(a), kind))
        prev = kind
    return cands


def _short(res, du):
    if du < 30.0:                                            # Samples, Jingles, Testtoene: nur wo der Ton beginnt (Wunsch 11.11.2026)
        t = float(res.get("first_beat") or 0)
        return [[round(t if 0 <= t < du - 0.5 else 0.0, 2), LABELS["start"]]]
    return None


def estimate_v1(res, sections=None):
    """Die Schaetzung bis 14.11.2026 (Drops vor Abschnitten, die fruehesten zuerst). Bleibt, damit die Bruecke erkennt, ob in
    Mixxx noch genau diese LB-Cues stehen (dann darf sie sie bei langen Liedern durch die verteilten ersetzen)."""
    du = float(res.get("duration") or 0)
    if du <= 0:
        return []
    sh = _short(res, du)
    if sh is not None:
        return sh
    bpm, fb = float(res.get("bpm") or 0), res.get("first_beat")
    picked = []
    for t, k in sorted(_cands(res, sections), key=lambda c: (-PRIO[c[1]], c[0])):
        t = _snap(t, bpm, fb)
        if not 0 <= t < du - 2.0 or any(abs(t - p[0]) < MIN_GAP_S for p in picked):
            continue
        picked.append((t, k))
        if len(picked) >= MAX_CUES:
            break
    return [[t, LABELS[k]] for t, k in sorted(picked)]


def estimate(res, sections=None):
    """Geschaetzte Cues [[s, Name]] aus einer Analyse (analyze_track) und ihren Abschnitten (find_sections).
    Bis LONG_S wie bisher (estimate_v1). Laengere (Fehlerbericht 14.11.2026: Mix von 134 Minuten hatte alle 8 Cues in der
    ersten halben Stunde): das Lied in MAX_CUES gleich lange Stuecke teilen, im ersten der Start, in jedem anderen der beste
    Kandidat (Drop, dann Hauptteil/Break, dann Vers/Outro, frueher vor spaeter), ohne Kandidaten der Anfang des Stuecks
    ("LB Teil"), alles auf den Takt gerastet."""
    du = float(res.get("duration") or 0)
    if du < LONG_S:
        return estimate_v1(res, sections)
    bpm, fb = float(res.get("bpm") or 0), res.get("first_beat")
    cands = _cands(res, sections)
    w = du / MAX_CUES
    picked = []
    for i in range(MAX_CUES):
        a, b = i * w, (i + 1) * w
        if i == 0:
            mine = [c for c in cands if c[1] == "start"] or [(0.0, "start")]
        else:
            mine = sorted((c for c in cands if a <= c[0] < b and c[1] != "start"), key=lambda c: (-PRIO[c[1]], c[0])) or [(a, "part")]
        for t, k in mine:
            t = _snap(t, bpm, fb)
            if 0 <= t < du - 2.0 and not any(abs(t - p[0]) < MIN_GAP_S for p in picked):
                picked.append((t, k))
                break
    return [[t, LABELS[k]] for t, k in sorted(picked)]


def load_json(name, default, base=DATA_DIR):
    try:
        with open(os.path.join(base, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(name, data, base=DATA_DIR):
    os.makedirs(base, exist_ok=True)
    p = os.path.join(base, name)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)
