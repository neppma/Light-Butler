#!/usr/bin/env python3
"""
folder_lib.py - zweite Liedquelle der Bruecke: die MP3s im Musikordner (Wunsch von Markus, 07.11.2026, unabhaengig von Mixxx).

Der Musikordner kommt aus dem Panel (Einstellungen -> Verbindungen, music.json am Pi, /api/musik/conf, music_serve.MusicServer),
sonst MUSIC_ROOT aus config.sh. Die Bruecke liest alle MP3s darunter ein (nur den ID3-Kopf und das erste MPEG-Bild, nie die
ganze Musik): Titel, Interpret, Genre, BPM (TBPM), Tonart (TKEY), Energie (TXXX EnergyLevel oder der Kommentar von Mixed In Key),
Laenge und Bitrate. Lieder, die schon in der Mixxx-Bibliothek stehen, bleiben weg (Vergleich ueber Ordner/Datei am Ende des
Pfads). Die uebrigen gehen wie Mixxx-Lieder an die Energie- und Tonart-Schaetzung und in die Musik-Datenbank am Pi, gekennzeichnet
mit src = "dir" (Spalte Quelle).

Gemerkt je Datei (Groesse, Aenderungszeit) in ~/Light-Butler-Daten/ordner/lieder.json, damit ein neuer Durchgang (alle 10 Minuten)
nur neue oder geaenderte Dateien oeffnet. Nur Python, keine neuen Pakete.
"""
import json
import os
import re
import sys
import threading
import time
import unicodedata

import id3_tags as it
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

DATA_DIR = os.path.join(_pfad.daten(), "ordner")
CACHE_FILE = "lieder.json"
SEP_RE = r"[\\/]" if sys.platform == "win32" else "/"   # Windows: E:\musik\... und Mac-Pfade aus Mixxx (/Volumes/...) gleich
RESCAN_S = 600.0                        # alle 10 Minuten neu durch den Ordner (neue Dateien)
CHANGED_MAX = 2000                                         # so viele geaenderte Dateien je Durchgang an den Pi melden
MAX_FILES = 30000                       # Sicherung gegen einen falsch gesetzten Ordner (z. B. "/")
# Kennzeichen aus energy_level.py und key_estimate.py (dort SRC_DESC): vom Light-Butler geschaetzt, nicht von Hand
ENERGY_DESC, ENERGY_SRC, KEY_SRC = "energylevel", "energylevelsource", "keysource"

# ---- MPEG-Kopf: Laenge und Bitrate ohne Dekoder ----------------------------------------------------------------------
BR_V1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
BR_V2_L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
SR_V1 = (44100, 48000, 32000)


def _frame(h):
    """4 Byte MPEG-Kopf (nur Layer III) -> (Bildlaenge, Abtastrate, Bitrate kbit/s, MPEG1?, Mono?) oder None."""
    if len(h) < 4 or h[0] != 0xFF or (h[1] & 0xE0) != 0xE0:
        return None
    ver, layer = (h[1] >> 3) & 3, (h[1] >> 1) & 3
    bri, sri, pad = h[2] >> 4, (h[2] >> 2) & 3, (h[2] >> 1) & 1
    if ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
        return None
    v1 = ver == 3
    sr = SR_V1[sri] // (1 if v1 else 2 if ver == 2 else 4)
    br = (BR_V1_L3 if v1 else BR_V2_L3)[bri]
    size = (144 if v1 else 72) * br * 1000 // sr + pad
    return size, sr, br, v1, (h[3] >> 6) == 3


def mp3_length(f, start, end):
    """(Laenge in s, Bitrate kbit/s) einer MP3 ab dem Ende des ID3-Kopfs. Mit Xing/Info- oder VBRI-Kopf genau, sonst aus
    Dateigroesse und Bitrate (konstante Bitrate). (0.0, 0) = kein MPEG-Bild gefunden."""
    f.seek(start)
    buf = f.read(64 * 1024)
    i = 0
    while True:
        i = buf.find(b"\xff", i)
        if i < 0 or i + 4 > len(buf):
            return 0.0, 0
        fr = _frame(buf[i:i + 4])
        if fr:
            nxt = buf[i + fr[0]:i + fr[0] + 4]                     # das naechste Bild muss passen (kein Zufallstreffer in Daten)
            if len(nxt) < 4 or _frame(nxt):
                break
        i += 1
    size, sr, br, v1, mono = fr
    spf = 1152 if v1 else 576
    side = (17 if mono else 32) if v1 else (9 if mono else 17)
    x = i + 4 + side
    frames = 0
    if buf[x:x + 4] in (b"Xing", b"Info") and int.from_bytes(buf[x + 4:x + 8], "big") & 1:
        frames = int.from_bytes(buf[x + 8:x + 12], "big")
    elif buf[i + 36:i + 40] == b"VBRI":
        frames = int.from_bytes(buf[i + 50:i + 54], "big")
    audio = max(0, end - (start + i))
    if frames > 0:
        dur = frames * spf / float(sr)
        return round(dur, 3), int(round(audio * 8 / dur / 1000.0)) if dur > 0 else br
    return (round(audio * 8 / (br * 1000.0), 3), br) if br else (0.0, 0)


def _comment(body):
    """Text eines COMM-Rahmens (Kommentar, z. B. "8A - Energy 7" von Mixed In Key)."""
    if len(body) < 5:
        return ""
    enc, rest = body[0], body[4:]
    _desc, rest = it._split0(enc, rest)
    return it._decode(enc, rest).strip("\x00 ").strip()


def _genre(g):
    """ID3-Genre: "(17)Rock" -> "Rock", "(148)" -> "Abstract" (Nummer wie Mixxx uebersetzt, 09.11.2026)."""
    g = it.genre_name(g)
    while g.startswith("(") and ")" in g:
        g = g[g.index(")") + 1:].strip()
    return "" if g.isdigit() else g


def read_mp3(path):
    """Angaben einer MP3 fuer die Liedliste: {title, artist, genre, bpm, tkey, key_est, comment, elvl, elvl_est, duration,
    bitrate}. Liest nur den Kopf. Titel und Interpret ohne Tags aus dem Dateinamen ("Interpret - Titel.mp3")."""
    out = {"title": "", "artist": "", "genre": "", "bpm": 0.0, "tkey": "", "key_est": False, "comment": "",
           "elvl": 0, "elvl_est": False, "duration": 0.0, "bitrate": 0, "album": "", "track": "", "grouping": "", "imported": ""}
    r = it.read(path)
    texts, txxx = {}, {}
    if not isinstance(r, str):
        for fid, fl, _raw, body in r[2]:
            if fl != b"\x00\x00":
                continue
            if fid == b"TXXX" and body:
                desc, rest = it._split0(body[0], body[1:])
                txxx[it._decode(body[0], desc).lower()] = it._decode(body[0], it._split0(body[0], rest)[0]).strip()
            elif fid == b"COMM" and not out["comment"]:
                out["comment"] = _comment(body)
            elif fid[:1] == b"T" and fid not in texts:
                texts[fid] = it.text_value(body)
    out["title"], out["artist"] = texts.get(b"TIT2", ""), texts.get(b"TPE1", "")
    out["tt"] = bool(out["title"])                         # Titel steht wirklich im Tag (nicht aus dem Dateinamen)
    out["genre"] = _genre(texts.get(b"TCON", ""))
    out["gnum"] = texts.get(b"TCON", "").strip() if it.genre_is_number(texts.get(b"TCON", "")) else ""   # nur als Nummer in der Datei
    out["album"] = texts.get(b"TALB", "")
    out["track"] = texts.get(b"TRCK", "")                  # Musik-Datenbank: Spalte und Suche Album (09.11.2026)
    out["grouping"] = texts.get(b"TIT1", "")               # Gruppe ("Après-Ski", 10.11.2026)
    out["imported"] = txxx.get("importdatum", "")[:10]     # Importdatum von der Import-Seite (11.11.2026)
    try:
        out["bpm"] = round(float(texts.get(b"TBPM", "").replace(",", ".") or 0), 2)
    except ValueError:
        pass
    out["tkey"] = texts.get(b"TKEY", "")
    out["key_est"] = KEY_SRC in txxx
    lv = txxx.get(ENERGY_DESC, "")
    if lv.isdigit() and 1 <= int(lv) <= 10:
        out["elvl"], out["elvl_est"] = int(lv), ENERGY_SRC in txxx
    if not out["title"]:
        stem = os.path.splitext(os.path.basename(path))[0]
        a, sep, t = stem.partition(" - ")
        out["artist"], out["title"] = (a.strip(), t.strip()) if sep and not out["artist"] else (out["artist"], stem.strip())
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(10)
        start = 0
        if head[:3] == b"ID3" and len(head) == 10:
            start = 10 + it._syncsafe(head[6:10]) + (10 if head[5] & 0x10 else 0)
        end = size
        if size >= 128:
            f.seek(size - 128)
            if f.read(3) == b"TAG":
                end -= 128
        out["duration"], out["bitrate"] = mp3_length(f, start, end)
    return out


def tail(path, n=2):
    """Ende eines Pfads (Ordner/Datei), klein und in NFC: gleich fuer dieselbe Datei auf Stick, NAS oder umbenanntem Laufwerk."""
    parts = [x for x in re.split(SEP_RE, str(path or "")) if x]
    return unicodedata.normalize("NFC", "/".join(parts[-n:])).lower()


def song_record(path, info, key_id_from_text):
    """Lied wie aus der Mixxx-Bibliothek (mixxx_bridge.load_library), mit src = "dir"."""
    kid = 0 if info.get("key_est") else key_id_from_text(info.get("tkey"))   # selbst geschaetzt: die Schaetzung neu fragen
    return {"id": None, "artist": info.get("artist") or "", "title": info.get("title") or "", "duration": float(info.get("duration") or 0),
            "bpm": float(info.get("bpm") or 0), "key": (info.get("tkey") or "")[:6] if kid else "", "kid": kid,
            "genre": info.get("genre") or "", "album": info.get("album") or "", "tracknumber": info.get("track") or "", "grouping": info.get("grouping") or "", "imported": info.get("imported") or "", "comment": info.get("comment") or "", "color": None, "crates": [], "cues": [],
            "filetype": "mp3", "bitrate": int(info.get("bitrate") or 0), "path": path, "missing": False, "src": "dir",
            "elvl": 0 if info.get("elvl_est") else int(info.get("elvl") or 0),
            "elvl_est": int(info.get("elvl") or 0) if info.get("elvl_est") else 0}


def walk_mp3(root, limit=MAX_FILES):
    """Alle MP3s unter root (ohne versteckte Ordner und Dateien, ohne "._"-Dateien vom Mac, ohne die ausgeschlossenen Ordner aus
    dem Panel, music_excl), sortiert."""
    import music_excl
    skip = music_excl.matcher(root)
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not x.startswith(".") and x != "Light-Butler Papierkorb" and not skip(os.path.join(d, x)))
        for n in sorted(files):
            if n.lower().endswith(".mp3") and not n.startswith("."):
                out.append(os.path.join(d, n))
                if len(out) >= limit:
                    return out
    return out


class FolderLib:
    """Liest den Musikordner im eigenen Thread ein. start(root, known) beginnt einen Durchgang, songs ist danach die neue Liste
    (Lieder ohne Mixxx-Eintrag), ver zaehlt die fertigen Durchgaenge."""

    def __init__(self, base=DATA_DIR, log=None, key_id_from_text=None):
        self.base, self.log = base, log or (lambda t: None)
        self.kid_of = key_id_from_text or (lambda t: 0)
        self.cache_path = os.path.join(base, CACHE_FILE)
        self.songs, self.ver, self.root, self.t, self.thread = [], 0, None, 0.0, None
        self.progress, self.done_t, self.n_files = (0, 0), 0.0, 0   # fuer die Statusanzeige der Musik-Datenbank
        self.file_tags, self.scan_t = {}, 0.0                  # Tags der Mixxx-Lieder aus der Datei: tail(Pfad) -> {title, artist, genre}
        self.on_changed = None                                 # on_changed([Pfade]): Dateien seit dem letzten Durchgang geaendert (Cover am Pi)
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                d = json.load(f)
            self.cache = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            self.cache = {}

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def due(self, root, now=None):
        now = time.time() if now is None else now
        import music_excl                                       # andere ausgeschlossene Ordner: gleich neu einlesen
        import stick_hold
        if stick_hold.held(root):                               # Stick wird ausgeworfen: nicht einlesen
            return False
        return bool(root) and not self.running() and (root != self.root or now - self.t > RESCAN_S or music_excl.version() != getattr(self, "excl_ver", 0))

    def start(self, root, known=(), wait=False):
        """Durchgang durch root; known = Pfade der Mixxx-Bibliothek (diese Lieder bleiben weg)."""
        import music_excl
        self.root, self.t, self.excl_ver = root, time.time(), music_excl.version()
        self.thread = threading.Thread(target=self._run, args=(root, {tail(p) for p in known if p}), daemon=True)
        self.thread.start()
        if wait:
            self.thread.join()

    def _run(self, root, known):
        try:
            if not os.path.isdir(root):
                self.log(f"Ordner-Liste: Musikordner nicht erreichbar: {root}")
                return
            t0 = time.time()
            files = walk_mp3(root)
            songs, cache, opened, bad, ftags, changed = [], {}, 0, 0, {}, []
            self.progress = (0, len(files))
            import stick_hold
            for k, p in enumerate(files):
                if k % 50 == 0:
                    self.progress = (k, len(files))
                    if stick_hold.held(p):                     # Stick wird ausgeworfen: Durchgang abbrechen, alte Liste bleibt
                        self.log("Ordner-Liste: angehalten (Stick wird ausgeworfen)")
                        self.progress = (0, 0)
                        return
                in_mixxx = tail(p) in known                       # Mixxx-Lied: nur seine Tags merken (Mixxx liest sie nicht von selbst neu,
                try:                                              # Wunsch 07.11.2026: die Liste soll zeigen, was in der Datei steht)
                    st = os.stat(p)
                except OSError:
                    continue
                c = self.cache.get(p)
                if isinstance(c, list) and len(c) == 3 and (c[0] != int(st.st_mtime) or c[1] != st.st_size):
                    changed.append(unicodedata.normalize("NFC", p))  # anderswo geaendert (Tags, Cover): der Pi soll das Cover neu holen
                if isinstance(c, list) and len(c) == 3 and c[0] == int(st.st_mtime) and c[1] == st.st_size and (not in_mixxx or "tt" in (c[2] or {"tt": 0})) \
                        and "imported" in (c[2] or {"imported": ""}):      # aeltere Ablage ohne Importdatum (11.11.2026): einmal neu lesen
                    info = c[2]
                else:
                    try:
                        info = read_mp3(p)
                    except (OSError, ValueError, IndexError):
                        info = None
                    opened += 1
                cache[p] = [int(st.st_mtime), st.st_size, info]
                if in_mixxx:
                    if info and not info.get("tt"):
                        # ohne Titel-Tag (Samples): Titel und Interpret kaemen nur aus dem Dateinamen, die bleiben aus Mixxx; Genre,
                        # Album, Track und Genre-Nummer stehen aber wirklich in der Datei (Fehlerbericht 09.11.2026: Abstract -> neues
                        # Genre geschrieben, die Liste zeigte nach dem naechsten Durchgang wieder Abstract aus Mixxx)
                        ft = {k: v for k, v in (("genre", info.get("genre")), ("album", info.get("album")), ("tracknumber", info.get("track")),
                                                ("gnum", info.get("gnum")), ("grouping", info.get("grouping")), ("imported", info.get("imported"))) if v}
                        if ft:
                            ftags[tail(p)] = ft
                    if info and info.get("tt"):
                        ftags[tail(p)] = {"title": info.get("title") or "", "artist": info.get("artist") or "", "genre": info.get("genre") or "",
                                          "album": info.get("album") or "", "tracknumber": info.get("track") or "",
                                          "gnum": info.get("gnum") or "", "grouping": info.get("grouping") or "", "imported": info.get("imported") or ""}
                    continue
                if not info or not info.get("duration"):
                    bad += 1
                    continue
                rec = song_record(p, info, self.kid_of)
                rec["added"] = int(getattr(st, "st_birthtime", 0) or st.st_mtime)   # nur im Ordner: wann die Datei auf den Stick kam
                songs.append(rec)
            self.cache = cache
            self._save()
            self.songs, self.file_tags, self.scan_t = songs, ftags, t0
            self.progress, self.done_t, self.n_files = (len(files), len(files)), time.time(), len(files)
            self.ver += 1
            if changed and self.on_changed is not None:
                try:
                    self.on_changed(changed[:CHANGED_MAX])
                except Exception as e:                             # noqa: BLE001  Melden ist Beiwerk
                    self.log(f"Ordner-Liste: Aenderungen melden: {str(e)[:80]}")
            self.log(f"Ordner-Liste: {len(songs)} Lieder ohne Mixxx-Eintrag in {root} ({len(files)} MP3s, {opened} neu gelesen"
                     + (f", {bad} ohne lesbares MPEG-Bild" if bad else "") + ")")
        except Exception as e:                                     # noqa: BLE001  die Ordner-Liste darf die Bruecke nie anhalten
            self.log(f"Ordner-Liste: {str(e)[:120]}")

    def _save(self):
        try:
            os.makedirs(self.base, exist_ok=True)
            tmp = self.cache_path + ".%d.tmp" % os.getpid()   # eigener Name je Prozess: Helfer und Bruecke kurz gleichzeitig (08.11.2026)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
            os.replace(tmp, self.cache_path)
        except OSError as e:
            self.log(f"Ordner-Liste: Zwischenspeicher nicht geschrieben ({e})")
