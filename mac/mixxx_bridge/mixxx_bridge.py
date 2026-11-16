#!/usr/bin/env python3
"""
mixxx_bridge.py - laeuft auf dem Mac neben Mixxx.

  python3 mixxx_bridge.py --list                      MIDI-Ports anzeigen
  python3 mixxx_bridge.py --monitor                   Zustand der Decks live anzeigen (Schritt 1: Pruefen)
  python3 mixxx_bridge.py --library                   Mixxx-Bibliothek pruefen (Tempo, Tonart, Eindeutigkeit)
  python3 mixxx_bridge.py --send 192.168.1.20         Zustand zusaetzlich per UDP an den Pi schicken (Schritt 2)

Voraussetzung: Mixxx laeuft mit dem Mapping "Light-Butler Bridge" auf dem Controller "IAC Driver Bus 1"
(siehe README). Benoetigt:  pip install mido python-rtmidi
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
import unicodedata
import zlib

PI_PORT = 9020
DEFAULT_PORT = "Light-Butler" if sys.platform == "win32" else "IAC"     # Windows: virtueller Anschluss von loopMIDI
SYSEX_ID = (0x7D, 0x53)          # nicht-kommerzielle Kennung + 'S', wie im Mixxx-Mapping
# Mixxx laeuft auf dem Mac oft in einem Container (Sandbox): dann liegen Mapping und Datenbank dort.
DB_CANDIDATES = [
    "~/Library/Containers/org.mixxx.mixxx/Data/Library/Application Support/Mixxx/mixxxdb.sqlite",
    "~/Library/Application Support/Mixxx/mixxxdb.sqlite",
] if sys.platform != "win32" else ["%LOCALAPPDATA%/Mixxx/mixxxdb.sqlite"]       # Windows: Mixxx-Einstellungen in AppData/Local
PI_RETRY_S = 2.0                 # nach einem Sendefehler so lange nichts senden (die Namenssuche kann blockieren)
_pi_retry, _pi_down = 0.0, False


def audio_fingerprint(path):
    """Fingerabdruck einer MP3 ohne ihre Tags: dieselbe Musik, auch wenn Mixed In Key die Tags aendert. Muss genau wie
    showman.store.audio_fingerprint am Pi rechnen (test_showmanager_mixxx prueft das)."""
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


PATH_MAX = 1000         # laengerer Pfad: lieber keiner als ein abgeschnittener (der zeigt auf keine Datei, Typ "MP", 06.11.2026)


def full_path(r):
    """Pfad am Mac, nie gekuerzt; zu lang fuer ein Paket (der Pi liest 4096 Byte, Umlaute zaehlen sechsfach): leer."""
    p = str(r.get("path") or "")
    return p if len(json.dumps(p)) <= PATH_MAX else ""


def level_of(rec, est=None):
    """(Stufe, geschaetzt): die Stufe von Mixed In Key (Kommentar, Crate, Farbe), sonst die Schaetzung (energy_level.Estimator)."""
    lv = energy_level(rec)
    if lv:
        return lv, False
    e = est.level(rec.get("path") or "") if est is not None else None
    e = e or rec.get("elvl_est")                                 # Ordner-Lied: frueher geschaetzt und in die MP3 geschrieben
    return (e, True) if e else (None, False)


def key_of(rec, kest=None):
    """(Tonart-Text, Mixxx-Nummer, Kennzeichen): aus Mixxx, sonst aus key_estimate.KeyEstimator (TKEY der Datei = 0,
    geschaetzt = 1, nicht eindeutig bestimmbar = 2 mit Nummer 0)."""
    kid = int(rec.get("kid") or 0)
    if kid or kest is None:
        return str(rec.get("key") or "")[:6], kid, 0
    k, guess = kest.key(rec.get("path") or "")
    if not k:
        return str(rec.get("key") or "")[:6], 0, 2 if guess == 2 else 0
    from key_estimate import camelot
    return camelot(k), k, guess


def bucket_count(n_songs):
    """Feste Zahl Stuecke fuer die Liste an den Pi: Zweierpotenz, rund 2,5 Lieder je Stueck, mindestens 256. Bleibt gleich,
    solange die Bibliothek nicht ueber eine Zweierpotenz waechst."""
    b = 256
    while b * 2.5 < n_songs:
        b *= 2
    return b


def year_of(v):
    """Erscheinungsjahr aus Mixxx ("1997", "1997-05-01", "05.1997"): vierstellig 1900-2099, sonst 0 (08.11.2026)."""
    m = re.search(r"(?<!\d)(19|20)\d\d(?!\d)", str(v or ""))
    return int(m.group(0)) if m else 0


def added_epoch(v):
    """Datum "hinzugefuegt" als Sekunden seit 1970 (0 = unbekannt): Importdatum aus dem Tag ("2026-11-10"), Mixxx-Feld
    datetime_added ("2026-11-10T21:41:19.805Z" oder "2024-01-11 12:00:00") oder schon eine Zahl (11.11.2026)."""
    import calendar
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v) if v > 0 else 0
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?", str(v or ""))
    if not m:
        return 0
    try:
        y, mo, d, h, mi, s = (int(x) if x else 0 for x in m.groups())
        return calendar.timegm((y, mo, d, h, mi, s, 0, 0, 0)) if 1990 <= y <= 2100 else 0
    except (ValueError, OverflowError):
        return 0


def _names(xs):
    """Kisten- oder Listennamen fuer den Pi: sortiert, ohne leere und doppelte, kurz gehalten (das Stueck muss ins Paket passen)."""
    return sorted({str(x).strip()[:40] for x in (xs or []) if str(x or "").strip()})[:12]


def library_chunks(lib, limit=1300, done=None, bad=None, est=None, kest=None, per=0, buckets=0, loud=None):
    """Die Bibliothek fuer den Showmanager und die Musik-Datenbank im Panel, in Stuecken, die in ein WLAN-Paket passen (unter 1500
    Byte, sonst wird es zerteilt und geht im WLAN oft verloren; der Pi liest 4096 Byte). Je Lied: [Interpret - Titel, Laenge, Interpret, Titel, BPM, Tonart, Tonart-Nr, Genre, Energie, Dateiname, Hotcues,
    analysiert, Pfad am Mac, Bitrate in kbit/s, nicht lesbar, Energie geschaetzt (0/1), Schaetzung der Energie (auch neben
    Mixed In Key, zum Vergleichen; 0 = keine), Tonart geschaetzt (0/1), aus dem Musikordner statt aus Mixxx (0/1, folder_lib), BPM geschaetzt (1, 2 = nicht bestimmbar), Plattenkisten, Wiedergabelisten (Namen, Musik-Datenbank: Gruppe Kisten/Listen), Jahr (0 = unbekannt), Album, Track ("4" oder "4/9"), Gruppe (TIT1), hinzugefuegt (Sekunden: Importdatum im Tag, sonst Mixxx, sonst Datei), Lautheit LUFS (0 = nicht gemessen), Spitze dBTP, ReplayGain in der Datei (0 nein, 1 von einem anderen Programm, 2 von uns), wie oft in Mixxx gespielt, zuletzt gespielt (Sekunden, 0 = nie)]. Die ersten zwei Felder bleiben wie frueher (aeltere Pi-Programme lesen nur sie). done = Schluessel fertiger Analysen."""
    chunks, cur, size = [], [], 0
    for r in sorted(lib, key=lambda x: (str(x.get("artist") or "").lower(), str(x.get("title") or "").lower())):
        title = f"{r.get('artist') or ''} - {r.get('title') or ''}".strip(" -")
        if not title or r.get("missing") or file_gone(r.get("path")):   # Datei fehlt laut Mixxx (alter Pfad) oder seither geloescht
            continue
        du = round(float(r.get("duration") or 0), 1)
        ok = int(track_key(r.get("duration") or 0.0, r.get("bpm"), r.get("kid")) in done) if done is not None else 0
        lv, guess = level_of(r, est)
        ktxt, kid, kguess = key_of(r, kest)
        bpm, bguess = float(r.get("bpm") or 0), 0
        if not bpm and kest is not None:                  # Mixxx kennt keine BPM: aus der Datei (TBPM) oder geschaetzt (essentia)
            bpm, bguess = kest.bpm(r.get("path") or "")
        item = [title[:120], du, str(r.get("artist") or "")[:60], str(r.get("title") or "")[:80], round(float(bpm or 0), 1),
                ktxt, kid, str(r.get("genre") or "").strip()[:40], lv or 0,
                os.path.basename(full_path(r))[:200], len(r.get("cues") or []), ok, full_path(r),
                int(r.get("bitrate") or 0), int(track_key(r.get("duration") or 0.0, r.get("bpm"), r.get("kid")) in bad) if bad else 0, int(guess),
                int((est.level(r.get("path") or "") if est is not None else 0) or r.get("elvl_est") or 0), int(kguess),
                int(r.get("src") == "dir"), int(bguess), _names(r.get("crates")), _names(r.get("lists")), year_of(r.get("year")),
                str(r.get("album") or "").strip()[:60], str(r.get("tracknumber") or "").strip()[:7], str(r.get("grouping") or "").strip()[:60],
                added_epoch(r.get("imported")) or added_epoch(r.get("datetime_added")) or added_epoch(r.get("added"))]
        lv_ = loud.get(r.get("path") or "") if loud is not None else None   # Lautheit (loudness.py, 11.11.2026)
        item += [lv_[0], lv_[1], lv_[2]] if lv_ else [0, 0, 0]
        item += [max(0, int(r.get("timesplayed") or 0)), added_epoch(r.get("last_played_at"))]   # wie oft und wann zuletzt in Mixxx gespielt (12.11.2026)
        item += [max(0, min(5, int(r.get("rating") or 0)))]   # Sterne aus Mixxx 0-5 (14.11.2026), Feld 32
        n = len(json.dumps(item, separators=(",", ":"), ensure_ascii=True)) + 1
        if buckets:                                       # Stueck nach dem Pfad, nicht nach der Reihenfolge (unten verteilt)
            chunks.append((full_path(r) or title, item, n))
            continue
        # per > 0: feste Zahl Lieder je Stueck (die Grenzen haengen nur an der Reihenfolge, nicht an der Laenge der Texte):
        # aendert sich ein Titel, aendert sich meist nur sein Stueck, nicht alle dahinter (Wunsch 07.11.2026, nur Geaendertes
        # schicken). Drei Lieder passen fast immer in ein WLAN-Paket, sonst wird es zerteilt (der Pi liest 4096 Byte).
        if cur and ((per and len(cur) >= per) or (not per and size + n > limit)):
            chunks.append(cur)
            cur, size = [], 0
        cur.append(item)
        size += n
    if cur:
        chunks.append(cur)
    if buckets and chunks:
        # Jedes Lied hat einen festen Platz (Pruefsumme des Pfads): Loeschen oder Hinzufuegen aendert nur sein Stueck, nicht alle
        # dahinter (Fehlerbericht 07.11.2026: geloeschte Lieder tauchten waehrend der langen Uebertragung wieder auf). Ist ein
        # Stueck voll (der Pi liest 4096 Byte), kommt das Lied ins naechste. Sortiert wird am Pi.
        out, size_of = [[] for _ in range(buckets)], [0] * buckets
        for key, item, n in sorted(chunks, key=lambda x: x[0]):
            b = zlib.crc32(key.encode("utf-8", "replace")) % buckets
            for _ in range(buckets):
                if size_of[b] + n <= BUCKET_MAX or not out[b]:
                    break
                b = (b + 1) % buckets
            out[b].append(item)
            size_of[b] += n
        return out
    return chunks


BUCKET_MAX = 3600                # Byte je Stueck hoechstens (der Pi liest 4096 Byte je Paket)
LIB_PER = 3                      # Lieder je Stueck der Liste an den Pi (feste Grenzen: Aenderungen betreffen wenige Stuecke)
LIB_CHECK_S = 120.0              # so oft vergleicht die Bruecke ihre Liste mit der Fassung am Pi


def lib_hash(chunks):
    """Pruefsumme der Liste, wie sie an den Pi geht (gleiche Lieder und Felder = gleiche Summe)."""
    return hashlib.sha1(json.dumps(chunks, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()[:20]


def send_udp(sock, data, addr):
    """An den Pi senden. Ist er aus oder nicht erreichbar, gehen die Daten verloren, die Bruecke laeuft weiter: stuerzte sie
    ab, ginge auch Mixxx zu, denn seine Ausgabe laeuft in die Bruecke. Sobald der Pi wieder da ist, kommen die Daten an."""
    global _pi_retry, _pi_down
    if time.monotonic() < _pi_retry:
        return
    try:
        sock.sendto(data, addr)
    except OSError as e:
        _pi_retry = time.monotonic() + PI_RETRY_S
        if not _pi_down:
            _pi_down = True
            print(f"Pi nicht erreichbar ({e}), Mixxx laeuft weiter", flush=True)
        return
    if _pi_down:
        _pi_down = False
        print("Pi wieder erreichbar", flush=True)


# ---- Tonart: verschiedene Schreibweisen auf die Mixxx-Nummer (1..12 Dur ab C, 13..24 Moll ab C) bringen ------------
NOTE_PC = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7,
           "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11, "H": 11}
# Lancelot/Camelot: Nummer -> (Grundton als Halbton ab C, Moll?)
LANCELOT_MINOR = {1: 8, 2: 3, 3: 10, 4: 5, 5: 0, 6: 7, 7: 2, 8: 9, 9: 4, 10: 11, 11: 6, 12: 1}
LANCELOT_MAJOR = {1: 11, 2: 6, 3: 1, 4: 8, 5: 3, 6: 10, 7: 5, 8: 0, 9: 7, 10: 2, 11: 9, 12: 4}


def key_id_from_text(txt):
    """'8A' (Lancelot), '1m'/'1d' (OpenKey), 'Fm', 'F#m', 'Bb' ... -> Mixxx-Nummer 1..24, 0 = unbekannt."""
    t = (txt or "").strip().replace("\u266f", "#").replace("\u266d", "b")
    if not t:
        return 0
    import re
    m = re.fullmatch(r"(\d{1,2})([ABab])", t)
    if m and 1 <= int(m.group(1)) <= 12:
        n = int(m.group(1))
        return 13 + LANCELOT_MINOR[n] if m.group(2).upper() == "A" else 1 + LANCELOT_MAJOR[n]
    m = re.fullmatch(r"(\d{1,2})([md])", t)
    if m and 1 <= int(m.group(1)) <= 12:
        n = (int(m.group(1)) + 6) % 12 + 1                       # OpenKey -> Lancelot
        return 13 + LANCELOT_MINOR[n] if m.group(2) == "m" else 1 + LANCELOT_MAJOR[n]
    m = re.fullmatch(r"([A-Ha-h][#b]?)(m|min|minor)?", t)
    if m:
        pc = NOTE_PC.get(m.group(1).upper())
        if pc is not None:
            return (13 if m.group(2) else 1) + pc
    return 0


# ---- Bibliothek laden und Lieder erkennen ----------------------------------------------------------------------------
def load_library(path, with_path=False):
    tmp = os.path.join(tempfile.mkdtemp(), "mixxxdb.sqlite")
    try:
        shutil.copy2(path, tmp)
    except PermissionError:
        sys.exit("Kein Zugriff auf die Datenbank. Kopiere mixxxdb.sqlite nach Downloads (siehe README) und nutze --db.")
    con = sqlite3.connect(tmp)
    cols = {r[1] for r in con.execute("PRAGMA table_info(library)")}
    sel = ["id", "artist", "title", "duration", "bpm", "key"] + [c for c in ("key_id", "mixxx_deleted", "genre", "color", "comment", "samplerate", "filetype", "bitrate", "year", "tracknumber", "album", "album_artist", "grouping", "datetime_added", "timesplayed", "last_played_at", "rating") if c in cols]
    paths, missing = {}, set()
    if with_path and "location" in cols:                        # Dateipfade aus track_locations; fs_deleted = Datei fehlt (Mixxx blendet sie aus)
        try:
            for lid, p, fsd in con.execute("SELECT l.id, t.location, t.fs_deleted FROM library l JOIN track_locations t ON l.location = t.id"):
                paths[lid] = p
                if fsd:
                    missing.add(lid)
        except sqlite3.Error:
            paths, missing = {}, set()
    crates = {}                                                 # Crates je Lied (fuer die Energiestufe "Energy 8", "Energy 9")
    try:
        for tid, name in con.execute("SELECT ct.track_id, c.name FROM crate_tracks ct JOIN crates c ON c.id = ct.crate_id"):
            crates.setdefault(tid, []).append(name or "")
    except sqlite3.Error:
        crates = {}
    lists = {}                                                  # eigene Wiedergabelisten je Lied (hidden 0; 1 = Auto DJ, 2 = Verlauf)
    try:
        for tid, name in con.execute("SELECT pt.track_id, p.name FROM PlaylistTracks pt JOIN Playlists p ON p.id = pt.playlist_id WHERE p.hidden = 0"):
            if name and name not in lists.setdefault(tid, []):
                lists[tid].append(name)
    except sqlite3.Error:
        lists = {}
    hotcues, lb_cues = {}, set()                                # Hotcues je Lied (Position in Samples, Stereo)
    try:
        for tid, pos, label in con.execute("SELECT track_id, position, label FROM cues WHERE type = 1 AND position >= 0"):
            hotcues.setdefault(tid, []).append(pos)
            if str(label or "").startswith("LB "):            # vom Light-Butler geschaetzt (cue_estimate, 11.11.2026)
                lb_cues.add(tid)
    except sqlite3.Error:
        hotcues = {}
    out = []
    for row in con.execute(f"SELECT {', '.join(sel)} FROM library"):
        r = dict(zip(sel, row))
        if r.get("mixxx_deleted") or not (r["duration"] or 0) > 0:
            continue
        r["kid"] = int(r.get("key_id") or 0) or key_id_from_text(r.get("key"))
        r["crates"] = crates.get(r["id"], [])
        r["lists"] = lists.get(r["id"], [])
        sr = r.get("samplerate") or 0
        r["cues"] = sorted(round(p / 2.0 / sr, 2) for p in hotcues.get(r["id"], [])) if sr > 0 else []
        r["cue_lb"] = r["id"] in lb_cues
        if with_path:
            r["path"] = paths.get(r["id"])
            r["missing"] = r["id"] in missing
        out.append(r)
    con.close()
    return out


def mixxx_live(src, cache=None, log=None):
    """Aktueller Stand der Mixxx-Datenbank fuer den Abgleich mit dem Stick: (alle Pfade, als fehlend markierte Pfade) oder None.
    Die Bruecke laedt ihre Bibliothek nur beim Start aus einer Kopie; nach "Bibliothek neu einlesen" in Mixxx blieb der Hinweis
    darum stehen (Fehlerbericht 07.11.2026). Nur lesen: Kopie samt -wal (Mixxx schreibt dort zuerst) in einen leeren Ordner.
    cache = (Zeitstempel, Ergebnis) vom letzten Mal, gleiche Dateien = gleiches Ergebnis."""
    if not src or not os.path.isfile(src):
        return None, cache
    try:
        stamp = tuple(os.path.getmtime(src + x) if os.path.exists(src + x) else 0 for x in ("", "-wal"))
    except OSError:
        return None, cache
    if cache and cache[0] == stamp:
        return cache[1], cache
    d = tempfile.mkdtemp(prefix="s2l_mixxx_")
    try:
        for x in ("", "-wal", "-shm"):
            if os.path.exists(src + x):
                shutil.copyfile(src + x, os.path.join(d, "m.sqlite" + x))   # nur der Inhalt: copy2 (Rechte, Flags) scheiterte am Mac
        con = sqlite3.connect(os.path.join(d, "m.sqlite"))
        try:
            alle, weg = set(), set()
            for p, fsd, md in con.execute("SELECT t.location, t.fs_deleted, l.mixxx_deleted FROM library l JOIN track_locations t ON l.location = t.id"):
                p = unicodedata.normalize("NFC", str(p or ""))
                if md:
                    continue                                    # in Mixxx entfernt (versteckt oder geloescht)
                alle.add(p)
                if fsd:
                    weg.add(p)
        finally:
            con.close()
        res = (alle, weg)
    except (OSError, sqlite3.Error) as e:
        if log is not None:
            log(f"Abgleich Mixxx: aktuelle Datenbank nicht lesbar ({str(e)[:120]}), es gilt die Kopie vom Start")
        return None, cache
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return res, (stamp, res)


def open_library(args):
    """Mixxx-Bibliothek fuer run/run_stdin. Ohne Datenbank-Datei (oder ohne --db, aber mit --send): leere Liste, die Bruecke
    laeuft dann mit der Ordner-Liste (folder_lib) allein. None = keine Bibliothek (nur Anzeige der Decks)."""
    db = os.path.expanduser(args.db) if args.db else ""
    if db and os.path.isfile(db):
        return load_library(db, with_path=True)
    if (db or args.send) and not getattr(args, "no_folder_lib", False):
        sys.stderr.write(("Mixxx-Datenbank nicht gefunden: " + db if db else "Ohne Mixxx-Datenbank") + ", nur Lieder aus dem Musikordner\n")
        return []
    if db:
        sys.exit(f"Mixxx-Datenbank nicht gefunden: {db}")
    return None


def file_gone(path):
    """Datei weg, obwohl ihr Laufwerk da ist (z. B. im Panel in den Papierkorb gelegt, Mixxx weiss es noch nicht)?
    Ist der Stick abgezogen, gilt nichts als weg: sonst verschwaende die ganze Bibliothek aus der Musik-Datenbank."""
    if not path:
        return False
    if re.match(r"^[A-Za-z]:[\\/]", path):                  # Windows: E:\musik\... -> Laufwerk E:\ angesteckt, Datei weg?
        return os.path.isdir(path[:3]) and not os.path.exists(path)
    parts = path.split("/")
    vol = "/".join(parts[:3] if path.startswith("/Volumes/") else parts[:2])   # /Volumes/STICK oder /Users
    return len(parts) > 2 and os.path.isdir(vol) and not os.path.exists(path)


ENERGY_RE = re.compile(r"energy\s*(\d{1,2})", re.IGNORECASE)
ENERGY_COLORS = {0x993333: 9, 0x997733: 8, 0x339933: 7}       # Trackfarben in Mixxx: Rot = 9, Braun = 8, Gruen = 7


def energy_level(rec):
    """Energiestufe eines Liedes (1 bis 9): aus dem Kommentar von Mixed In Key ("8A - Energy 7"), sonst die hoechste Zahl
    aus Crates wie "Energy 9", sonst aus der Trackfarbe, sonst None. Ordner-Lieder (folder_lib): zuerst TXXX EnergyLevel
    der MP3, wenn sie nicht vom Light-Butler geschaetzt ist (elvl)."""
    if rec.get("elvl"):
        return int(rec["elvl"])
    m = ENERGY_RE.search(str(rec.get("comment") or ""))
    if m and 1 <= int(m.group(1)) <= 10:
        return int(m.group(1))
    levels = [int(m.group(1)) for c in (rec.get("crates") or []) for m in [ENERGY_RE.search(c or "")] if m]
    if levels:
        return max(levels)
    col = rec.get("color")
    try:
        return ENERGY_COLORS.get(int(col) & 0xFFFFFF) if col is not None else None
    except (TypeError, ValueError):
        return None


def identify(lib, deck):
    """Passende Lieder zu einem Deck: Laenge (auf 2 ms), BPM der Datei (auf 0,03) und Tonart der Datei."""
    du, fb = deck.get("du", 0), deck.get("fb", 0)
    if not deck.get("tl") or du <= 0:
        return []
    cand = [r for r in lib if abs(r["duration"] - du) <= 0.002]
    by_bpm = [r for r in cand if abs((r["bpm"] or 0) - fb) <= 0.03]
    cand = by_bpm or cand
    k = deck.get("fk") or 0
    by_key = [r for r in cand if k and r["kid"] == k]
    return by_key or cand


def ident_text(cands):
    if not cands:
        return "unbekannt (nicht in der Bibliothek)"
    names = {((r["artist"] or "").strip().lower(), (r["title"] or "").strip().lower()) for r in cands}
    r = cands[0]
    label = f"{r['artist'] or '-'} - {r['title']}"
    if len(cands) == 1:
        return f"{label}  [eindeutig]"
    if len(names) == 1:
        return f"{label}  [{len(cands)}x dieselbe Datei in der Bibliothek, unkritisch]"
    return f"MEHRDEUTIG: {len(cands)} Kandidaten, z. B. " + " | ".join(f"{c['artist'] or '-'} - {c['title']}" for c in cands[:3])


# ---- Weiterleitung an den Pi: Zustand + Analyse-Plan ------------------------------------------------------------------
ANALYSIS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis")
ANALYSIS_VERSION = 3            # aeltere Analysen (z. B. mit zu frueh gesetzten Drops) werden neu berechnet


def plan_current(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("version", 1) >= ANALYSIS_VERSION
    except (OSError, ValueError):
        return False


def track_key(duration, bpm, kid):
    return f"{duration:.3f}_{(bpm or 0):.2f}_{int(kid or 0)}"


def compact_events(events):
    kinds = {"after_break": "b", "lift": "l", "intro_end": "i"}
    out = []
    for e in events:
        if e["type"] in ("drop", "build", "gap", "break"):
            strength = e.get("strength", e.get("rise", 0)) or 0
            out.append([e["type"], round(e["t"], 2), round(e.get("end", e["t"]), 2), round(strength, 2), kinds.get(e.get("kind"), "")])
    return out


def compact_energy(level, points=200):
    """Lautstaerkekurve (ein Wert 0-100 je Sekunde) fuer den Liedverlauf im Panel auf hoechstens 200 Werte verkleinern
    (Maximum je Abschnitt, damit kurze laute Stellen sichtbar bleiben)."""
    if not level:
        return []
    n = len(level)
    if n <= points:
        return [int(v) for v in level]
    return [int(max(level[i * n // points:max(i * n // points + 1, (i + 1) * n // points)])) for i in range(points)]


class Forwarder:
    """Merkt sich pro Deck das geladene Lied, findet oder berechnet die Analyse und schickt Zustand und Plan an den Pi."""

    def __init__(self, lib, sock, addr, analysis_dir=ANALYSIS_DIR, analyze=True, path_map=(), log=None):
        import queue
        import threading
        self.log = log or (lambda text: None)
        self.lib, self.sock, self.addr, self.dir = lib, sock, addr, analysis_dir
        self.path_map = list(path_map)
        self.decks = {}
        self.lock = threading.Lock()
        self.q = queue.Queue()
        self.analyze = analyze
        self.bg, self.demand_t = None, 0.0                       # Hintergrund-Analyse (eigener Prozess), letzte Analyse beim Laden
        self.music = None                                        # Vorhoer-Server (music_serve.MusicServer), von make_forwarder gesetzt
        self.est = None                                          # Energie-Schaetzung (energy_level.Estimator), von make_forwarder gesetzt
        self.kest = None                                         # Tonart ohne Mixxx (key_estimate.KeyEstimator), von make_forwarder gesetzt
        self.loud = None                                         # Lautheit (loudness.Loudness), von make_forwarder gesetzt
        self.autotag = None                                      # Auto-Tagger (auto_tag.AutoTagger), von make_forwarder gesetzt
        self.lib_off = False                                     # Bibliotheks-Teil macht der Light-Butler Helfer (08.11.2026)
        self.yield_helper, self.lib_setup, self.lib_args = False, None, None
        self.role_t, self.helper_gone = 0.0, 0.0
        self.mixxx_lib = list(lib or [])                         # nur die Lieder aus Mixxx; self.lib = sie plus die Ordner-Lieder
        self.folder, self.folder_ver, self.folder_root, self.folder_t = None, 0, "", 0.0   # Ordner-Liste (folder_lib.FolderLib)
        if analyze:
            threading.Thread(target=self._worker, daemon=True).start()

    def handle(self, d):
        n = d["d"]
        deck = self.decks.setdefault(n, {"sig": None, "plan": None, "info": "leer", "key": "", "sent": 0.0})
        sig = (d.get("tl"), round(d.get("du", 0), 3), round(d.get("fb", 0), 2), d.get("fk", 0))
        if sig != deck["sig"]:
            deck["sig"] = sig
            self._identify(n, d)
        if self.sock and self.addr:
            m = dict(d)
            m["t"] = round(time.time(), 3)
            send_udp(self.sock, json.dumps(m, separators=(",", ":")).encode("ascii"), self.addr)

    def _identify(self, n, d):
        deck = self.decks[n]
        deck["plan"], deck["key"], deck["rec"] = None, "", None
        if not d.get("tl"):
            deck["info"] = "leer"
            self._send(n, {"type": "plan", "d": n, "key": ""})
            self._note(n)
            return
        cands = identify(self.lib, d) if self.lib else []
        names = {((r["artist"] or "").strip().lower(), (r["title"] or "").strip().lower()) for r in cands}
        if not self.lib:
            deck["info"] = "keine Bibliothek (--db fehlt)"
        elif not cands:
            deck["info"] = "Lied nicht in der Bibliothek"
        elif len(names) > 1:
            deck["info"] = f"Lied mehrdeutig ({len(cands)} Kandidaten): keine Vorhersage"
        else:
            rec = self._pick(cands)
            deck["rec"] = rec
            deck["key"] = track_key(rec["duration"], rec["bpm"], rec["kid"])
            path = os.path.join(self.dir, deck["key"] + ".json")
            fpath = self._map(rec.get("path") or "")
            if os.path.exists(path) and (plan_current(path) or not self.analyze):
                self._load_plan(n, path)
            elif not self.analyze:
                deck["info"] = "noch nicht analysiert"
            elif not fpath or not os.path.exists(fpath):
                deck["info"] = f"Datei nicht erreichbar (NAS/USB verbunden?): {fpath or 'kein Pfad'}"[:150]
            else:
                deck["info"] = "Analyse laeuft ..."
                self.q.put((n, deck["key"], rec))
                self.demand_t = time.time()
                if self.bg is not None:
                    self.bg["pause"].set()                     # Lied in Mixxx hat Vorrang vor der Hintergrund-Analyse
        self._note(n)

    def _map(self, path):
        for old, new in self.path_map:
            if path.startswith(old):
                return new + path[len(old):]
        return path

    def _pick(self, cands):
        """Von mehreren gleichen Eintraegen (z. B. USB-Laufwerk und NAS) den waehlen, dessen Datei erreichbar ist."""
        for r in cands:
            p = self._map(r.get("path") or "")
            if p and os.path.exists(p):
                return r
        return cands[0]

    TAG_KEYS = ("title", "artist", "genre", "album", "grouping", "imported")

    def _tags_file(self):
        return os.path.join(os.path.dirname(os.path.abspath(self.dir)), "tags_geaendert.json")

    def _tag_over(self):
        """Selbst geschriebene Tags je Pfad (Mixxx-Pfad): {"title", "artist", "genre"}. Gemerkt in tags_geaendert.json."""
        if getattr(self, "_tags", None) is None:
            try:
                with open(self._tags_file(), encoding="utf-8") as f:
                    d = json.load(f)
                self._tags = {str(k): dict({t: str(v[t]) for t in self.TAG_KEYS if t in v}, t=float(v.get("t") or 0))
                              for k, v in d.items() if isinstance(v, dict)}
            except (OSError, ValueError, TypeError, AttributeError):
                self._tags = {}
        return self._tags

    def tags_written(self, path, fields):
        """music_serve hat Tags in die MP3 geschrieben. Mixxx liest sie erst nach "Metadaten aus Datei importieren" neu ein,
        die Liste am Pi zeigte bis dahin die alten Werte (Fehlerbericht 07.11.2026, Titel = Interpret). Darum: merken, in der
        Liste vor die Werte aus Mixxx stellen und die Bibliothek gleich neu schicken."""
        new = {k: str(fields[k]).strip() for k in self.TAG_KEYS if k in (fields or {})}
        if not path or not new:
            return
        over = self._tag_over()
        over[path] = dict(over.get(path) or {}, **new, t=time.time())
        try:
            tmp = self._tags_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(over, f, ensure_ascii=False)
            os.replace(tmp, self._tags_file())
        except OSError:
            pass
        self.lib_done = -1e9                                    # gleich nach dem laufenden Durchgang neu schicken (sonst erst in 10 Minuten)

    def path_moved(self, old, new):
        """Dateien pruefen hat eine Datei umbenannt (Wunsch 08.11.2026): was nach Pfad gemerkt ist, gilt auch fuer den neuen
        Pfad (geschaetzte Tonart, BPM, Energie, selbst geschriebene Tags). Der alte Pfad bleibt, bis Mixxx den neuen kennt."""
        from file_check import carry_jsonl
        n = 0
        for obj, attr in ((getattr(self, "est", None), "feats_path"), (getattr(self, "kest", None), "path")):
            if obj is not None:
                n += carry_jsonl(getattr(obj, attr), old, new)
                try:
                    obj.refresh()
                except Exception:                                    # noqa: BLE001  Merkzettel sind Beiwerk
                    pass
        over = self._tag_over()
        if old in over and new not in over:
            over[new] = dict(over[old])
            try:
                tmp = self._tags_file() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(over, f, ensure_ascii=False)
                os.replace(tmp, self._tags_file())
            except OSError:
                pass
        if getattr(self, "folder", None) is not None:
            self.folder.t = 0.0                                      # Ordner-Liste gleich neu einlesen
        self.log(f"Umbenannt: {n} Merkzettel (Tonart, BPM, Energie) mitgenommen")

    def file_tags_ready(self):
        """Hat die Ordner-Liste die Tags der Dateien seit dem Start einmal gelesen? Vorher gelten fuer lib_with_tags nur die
        (vielleicht alten) Werte aus Mixxx. Ohne Ordner-Liste: gleich bereit."""
        fl = getattr(self, "folder", None)
        return fl is None or float(getattr(fl, "scan_t", 0) or 0) > 0

    def lib_with_tags(self):
        """Bibliothek mit Titel, Interpret und Genre aus der MP3 statt der (vielleicht alten) Werte aus Mixxx: Mixxx liest
        geaenderte Tags erst nach "Metadaten aus Datei importieren" (Wunsch 07.11.2026). Quelle: die Ordner-Liste (alle 10
        Minuten, Tags aller MP3s), davor selbst geschriebene Tags, bis die Ordner-Liste die Datei danach gelesen hat."""
        from folder_lib import tail
        over = self._tag_over()
        fl = self.folder
        ftags = getattr(fl, "file_tags", None) or {}
        scan_t = float(getattr(fl, "scan_t", 0) or 0)
        if not over and not ftags:
            return self.lib
        out = []
        for r in self.lib:
            p = r.get("path") or ""
            ch = {}
            ft = None
            if r.get("src") != "dir" and ftags:
                ft = ftags.get(tail(self._map(p))) or ftags.get(tail(p))
                if ft:
                    ch.update({k: v for k, v in ft.items() if v})   # leeres Feld in der Datei: Wert aus Mixxx behalten
            o = over.get(p)
            if o and float(o.get("t") or 0) >= scan_t:          # selbst geschrieben, die Ordner-Liste kennt es noch nicht
                ch.update({k: v for k, v in o.items() if k in self.TAG_KEYS})
            elif o:                                             # selbst geleert (Interpret ändern, 13.11.2026): bleibt leer, solange
                ch.update({k: "" for k, v in o.items()           # die Datei es auch ist, sonst kam der alte Name aus Mixxx zurueck
                           if k in self.TAG_KEYS and v == "" and not (ft or {}).get(k)})
            out.append(dict(r, **ch) if ch and any(r.get(k) != v for k, v in ch.items()) else r)
        return out

    def status(self, now=None):
        """Was der Mac gerade fuer die Musik-Datenbank tut (Wunsch 07.11.2026: "alles so intransparent"): Tags der MP3s lesen
        und die Liste an den Pi schicken. Fuer music_serve /status, billig, ohne Dateizugriff."""
        now = time.time() if now is None else now
        fl = self.folder
        tags = None
        if fl is not None:
            busy = bool(getattr(fl, "running", lambda: False)())
            done, total = getattr(fl, "progress", (0, 0))
            tags = {"busy": busy, "done": int(done), "total": int(total), "ago": round(now - fl.done_t) if getattr(fl, "done_t", 0) else -1,
                    "files": int(getattr(fl, "n_files", 0)), "next": max(0, round(getattr(fl, "t", 0) + 600 - now)) if not busy else 0}
        chunks, n = getattr(self, "lib_chunks", None) or [], int(getattr(self, "lib_total", 0) or 0)
        done = getattr(self, "lib_done", -1e9)
        pi_h = getattr(self.music, "pi_libh", None) if self.music is not None else None
        every = LIB_CHECK_S if pi_h is not None else 600.0
        job = int(getattr(self, "lib_job", 0) or n)
        send = {"busy": bool(chunks), "sent": job - len(chunks) if chunks else job, "n": job, "total": n, "kind": getattr(self, "lib_kind", ""),
                "next": 0 if chunks or done < 0 else max(0, round(done + every - now)),
                "same": bool(getattr(self, "lib_h", "")) and pi_h == getattr(self, "lib_h", ""), "pi": pi_h is not None}
        return {"tags": tags, "send": send}

    def _libhash_msg(self):
        """Fassung der Liste fuer den Pi, dazu der Port des Vorhoerens: den erfuhr der Pi sonst nur aus den Listen-Paketen, und
        die kommen nur noch bei Aenderungen (Fehlerbericht 07.11.2026: nach Neustart des Pi "Bruecke laeuft nicht")."""
        msg = {"type": "libhash", "h": self.lib_h}
        if self.music is not None:
            msg["mp"] = self.music.port
        return msg

    def _live_log(self, t):
        self._live_err = True                                   # nur einmal ins Log
        self.log(t)

    def sync_info(self, max_list=500):
        """Passt Mixxx noch zum Stick? (Wunsch von Markus 07.11.2026) gone = Lieder in Mixxx, deren Datei fehlt (geloescht oder
        verschoben, Mixxx weiss es noch nicht); new = MP3s im Musikordner, die Mixxx nicht kennt. Mit beiden Zahlen ungleich 0
        sollte Mixxx die Bibliothek neu einlesen. Fuer die Musik-Datenbank (music_serve /sync), 60 s zwischengespeichert."""
        now = time.time()
        c = getattr(self, "_sync", None)
        if c and now - c[0] < 60.0:
            return c[1]
        live, self._live = mixxx_live(getattr(self, "live_db", ""), getattr(self, "_live", None),
                                      log=None if getattr(self, "_live_err", False) else self._live_log)   # Mixxx jetzt, nicht beim Start
        gone, known = [], 0
        for r in self.mixxx_lib or []:
            p = r.get("path") or ""
            if not p or r.get("missing"):
                continue
            n = unicodedata.normalize("NFC", p)
            if live is not None and (n not in live[0] or n in live[1]):
                known += n in live[1]                          # Mixxx weiss es schon (Fehlende Titel) oder hat es entfernt
                continue
            if file_gone(self._map(p)):
                gone.append(p)
        new = [r.get("path") for r in (self.folder.songs if self.folder is not None else []) if r.get("path")]
        if live is not None:                                   # inzwischen von Mixxx eingelesen: nicht mehr neu
            new = [p for p in new if unicodedata.normalize("NFC", p) not in live[0]]
        res = {"gone": len(gone), "new": len(new), "mixxx": len(self.mixxx_lib or []), "gone_list": sorted(gone)[:max_list],
               "new_list": sorted(new)[:max_list], "folder": bool(self.folder is not None and self.folder.root), "known": known,
               "live": live is not None}
        self._sync = (now, res)
        return res

    def autotag_songs(self):
        """Lieder fuer den Auto-Tagger: MP3s der Bibliothek mit Pfad in Mixxx und Datei am Mac."""
        out = []
        for r in self.lib or []:
            p = r.get("path") or ""
            if p.lower().endswith(".mp3") and not r.get("missing"):
                out.append({"path": p, "file": self._map(p), "title": str(r.get("title") or ""), "artist": str(r.get("artist") or ""),
                            "dur": float(r.get("duration") or 0)})
        return out

    def meta_for_path(self, path):
        """Angaben aus Mixxx zu einem Lied der Bibliothek fuer die MP3 nach dem Umwandeln: Titel, Interpret, Genre, BPM, Tonart
        (Camelot), Kommentar (traegt die Energie von Mixed In Key). {} = unbekannt."""
        rec = next((r for r in (self.lib or []) if r.get("path") == path), None)
        if rec is None:
            return {}
        bpm = float(rec.get("bpm") or 0)
        try:
            from key_estimate import camelot
            key = camelot(rec.get("kid")) or str(rec.get("key") or "")
        except ImportError:
            key = str(rec.get("key") or "")
        return {"title": str(rec.get("title") or ""), "artist": str(rec.get("artist") or ""), "genre": str(rec.get("genre") or ""),
                "bpm": (f"{bpm:.2f}".rstrip("0").rstrip(".") if bpm > 0 else ""), "key": key, "comment": str(rec.get("comment") or "")}

    def cues_for(self, rec, res=None):
        """Hotcues eines Liedes in s und ihre Herkunft: aus Mixxx ("mixxx"); ohne sie und nur mit der Einstellung cue_est am Pi
        (Standard aus, sonst bleibt das Licht gleich) aus dem Tag der MP3 ("datei", Mixed In Key/Serato) oder geschaetzt aus der
        Analyse ("lb"). Wunsch von Markus 11.11.2026."""
        if rec.get("cues"):
            return list(rec["cues"]), "mixxx"
        if self.music is None or not getattr(self.music, "cue_est", False):
            return [], ""
        try:
            import cue_estimate
            f = self._map(rec.get("path") or "")
            cache = self.__dict__.setdefault("_file_cues", {})
            try:
                stamp = os.path.getmtime(f) if f else 0
            except OSError:
                stamp = 0
            if f and stamp and (cache.get(f) or (None,))[0] != stamp:
                cache[f] = (stamp, cue_estimate.file_cues(f))
            fc = cache.get(f, (0, []))[1] if f else []
            if fc:
                return fc, "datei"
            if res is not None:
                est = [t for t, _n in cue_estimate.estimate(res)]
                if est:
                    return est, "lb"
        except Exception as e:                                   # noqa: BLE001  ohne Cues geht es auch
            self.log(f"Cues: {str(e)[:120]}")
        return [], ""

    def marks_for_path(self, path, fp=True):
        """Abschnitte, Hotcues, Ereignisse und Energie eines Liedes der Bibliothek, wie fuer ein Deck, ohne dass es dort liegt
        (Quick in der Musik-Datenbank, Wunsch von Markus 06.11.2026). None = Lied unbekannt oder noch nicht analysiert."""
        rec = next((r for r in (self.lib or []) if r.get("path") == path), None)
        if rec is None:
            return None
        key = track_key(rec.get("duration") or 0.0, rec.get("bpm"), rec.get("kid"))
        jp = os.path.join(self.dir, key + ".json")
        if not os.path.isfile(jp):
            return None
        with open(jp, encoding="utf-8") as f:
            res = json.load(f)
        du = res["duration"]
        if abs((rec.get("duration") or 0) - du) < 1.0:
            du = rec["duration"]
        out = {"title": f"{res.get('artist') or ''} - {res.get('title') or ''}".strip(" -"), "du": du,
               "ev": compact_events(res["events"]), "en": compact_energy(res.get("energy") or []),
               "genre": str(rec.get("genre") or "")[:40], "grp": str(rec.get("grouping") or "")[:120],   # Gruppe: Licht-Stil (13.11.2026)
               "cu": [], "se": [], "fp": ""}
        cu, cs = self.cues_for(rec, res)
        out["cu"] = [c for c in cu if 0 <= c <= du][:16 if fp else 36]   # Vorhoeren (fp aus): alles, auch bei langen Mixen
        if cs and cs != "mixxx":
            out["cs"] = cs                                       # Herkunft der Cues: datei oder lb (geschaetzt)
        if res.get("bpm") and res.get("first_beat") is not None:   # Beat-Raster der Analyse: Auto-DJ mischt damit taktgenau
            out["bpm"], out["fb"] = round(float(res["bpm"]), 3), round(float(res["first_beat"]), 3)
        out["lvl"], guess = level_of(rec, self.est)
        if guess:
            out["le"] = 1                                        # Stufe geschaetzt (nicht von Mixed In Key)
        try:
            import analyze_track as at
            out["se"] = at.find_sections(res, out["cu"])[:32 if fp else 400]
        except Exception as e:                                   # noqa: BLE001  ohne Abschnitte geht es auch
            self.log(f"Abschnitte nicht berechnet: {e}")
        try:
            p_ = self._map(path) if fp else ""                    # Vorhoeren braucht keinen Fingerabdruck (liest sonst die Datei)
            if p_ and p_.lower().endswith(".mp3") and os.path.exists(p_):
                out["fp"] = audio_fingerprint(p_)
        except OSError:
            pass
        return out

    def _load_plan(self, n, path):
        deck = self.decks[n]
        with open(path, encoding="utf-8") as f:
            res = json.load(f)
        title = f"{res.get('artist') or ''} - {res.get('title') or ''}".strip(" -")
        rec = deck.get("rec") or {}
        du = res["duration"]
        if abs((rec.get("duration") or 0) - du) < 1.0:                   # Laenge wie in Mixxx: manche Dekoder lassen kaputte
            du = rec["duration"]                                         # Bilder am Ende weg, sonst "Plan passt nicht"
        deck["plan"] = {"type": "plan", "d": n, "key": deck["key"], "title": title, "du": du,
                        "ev": compact_events(res["events"]), "en": compact_energy(res.get("energy") or [])}
        deck["plan"]["lvl"], guess = level_of(rec, self.est)            # Energiestufe aus Kommentar, Crate oder Farbe, sonst geschaetzt (oder None)
        if guess:
            deck["plan"]["le"] = 1
        _t, ki, kguess = key_of(rec, self.kest)
        if ki and not rec.get("kid"):                            # Mixxx kennt keine Tonart: die aus der Datei oder geschaetzt
            deck["plan"]["ki"] = ki
            if kguess == 1:
                deck["plan"]["ke"] = 1
        deck["plan"]["genre"] = str(rec.get("genre") or "")[:40]
        deck["plan"]["grp"] = str(rec.get("grouping") or "")[:120]          # Gruppe (Weihnachten ...): Licht-Stil, 13.11.2026
        try:
            p_ = self._map(rec.get("path") or "")
            if p_ and p_.lower().endswith(".mp3") and os.path.exists(p_):
                deck["plan"]["fp"] = audio_fingerprint(p_)       # Showmanager: findet die Show zu dieser Datei
        except OSError as e:
            self.log(f"Deck {n}: Fingerabdruck nicht moeglich: {e}")
        cu, cs = self.cues_for(rec, res)                         # Hotcues aus Mixxx, sonst (cue_est) aus der Datei oder geschaetzt
        deck["plan"]["cu"] = [c for c in cu if 0 <= c <= du][:16]
        if cs and cs != "mixxx":
            deck["plan"]["cs"] = cs
        try:
            import analyze_track as at
            deck["plan"]["se"] = at.find_sections(res, deck["plan"]["cu"])[:32]   # Abschnitte: aus der fertigen Analyse, ohne neu zu rechnen
        except Exception as e:
            self.log(f"Deck {n}: Abschnitte nicht berechnet: {e}")
        nd = sum(1 for e in deck["plan"]["ev"] if e[0] == "drop")
        deck["info"] = f"Analyse vorhanden: {len(deck['plan']['ev'])} Ereignisse, davon {nd} Drops"
        self._send(n, deck["plan"])
        deck["sent"] = time.time()
        self.log(f"Deck {n}: {title} - {deck['info']}")

    def _send(self, n, msg):
        if self.sock and self.addr:
            send_udp(self.sock, json.dumps(msg, separators=(",", ":"), ensure_ascii=True).encode("ascii"), self.addr)

    def _worker(self):
        while True:
            n, key, rec = self.q.get()
            try:
                import analyze_track as at
                path = rec["path"] or ""
                for old, new in self.path_map:
                    if path.startswith(old):
                        path = new + path[len(old):]
                at.analyze_record(dict(rec, path=path), self.dir, force=True)
                self.demand_t = time.time()
                deck = self.decks.get(n)
                if deck and deck["key"] == key:
                    self._load_plan(n, os.path.join(self.dir, key + ".json"))
            except ImportError:
                self._set_info(n, key, "Analyse nicht moeglich: pip install numpy scipy soundfile")
            except Exception as e:
                self._set_info(n, key, f"Analyse fehlgeschlagen: {str(e)[:90]}")

    def _set_info(self, n, key, text):
        deck = self.decks.get(n)
        if deck and deck["key"] == key:
            deck["info"] = text
            self._note(n)

    def start_background(self, pause_s=1.0):
        """Hintergrund-Analyse aller Lieder ohne Analyse-Datei starten (eigener Prozess, niedrige Prioritaet)."""
        import multiprocessing as mp
        try:
            done = {f[:-5] for f in os.listdir(self.dir) if f.endswith(".json")}
        except OSError:
            done = set()
        try:
            with open(os.path.join(self.dir, FAILED_FILE), encoding="utf-8") as f:
                failed = set(json.load(f))
        except (OSError, ValueError):
            failed = set()
        todo, seen = [], set()
        for r in self.excl_filter(self.lib):                     # ausgeschlossene Ordner nie analysieren (10.11.2026)
            key = track_key(r["duration"], r["bpm"], r["kid"])
            path = self._map(r.get("path") or "")
            if key in done or key in failed or key in seen or not path:
                continue
            seen.add(key)
            todo.append((key, dict(r, path=path)))
        ctx = mp.get_context("spawn")
        self.bg = {"pause": ctx.Event(), "prog": ctx.Array("i", 2), "todo": len(todo), "failed_before": len(failed)}
        if todo:
            self.bg["proc"] = ctx.Process(target=background_analysis, daemon=True,
                                          args=(todo, self.dir, self.bg["pause"], self.bg["prog"], pause_s))
            self.bg["proc"].start()
        self.log(f"Hintergrund-Analyse: {len(todo)} Lieder offen, {len(failed)} als nicht lesbar gemerkt")
        return len(todo)

    def bg_info(self):
        """Fortschritt fuer die Statistik: offen beim Start, erledigt, nicht lesbar, laeuft, pausiert."""
        b = self.bg
        if b is None:
            return None
        p = b.get("proc")
        return {"todo": b["todo"], "done": b["prog"][0], "fail": b["prog"][1] + b["failed_before"],
                "run": bool(p and p.is_alive()), "pause": b["pause"].is_set(), "gone": self.failed_gone()}

    def failed_gone(self):
        """Wie viele der "nicht lesbaren" Eintraege kein Lied der Liste mehr betreffen: Datei fehlt (Pfad in Mixxx veraltet) oder
        das Lied hat sich seither geaendert (andere Laenge, Tempo, Tonart). Die Liste am Pi zeigt sie nicht, weil die Bruecke
        fehlende Dateien nicht schickt (Fehlerbericht 06.11.2026: 56 gemeldet, 4 angezeigt)."""
        p = os.path.join(self.dir, FAILED_FILE)
        try:
            mt = os.path.getmtime(p)
            if getattr(self, "_gone", None) and self._gone[0] == (mt, len(self.lib)):
                return self._gone[1]
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError, TypeError):
            return 0
        listed = {track_key(r.get("duration") or 0.0, r.get("bpm"), r.get("kid")) for r in self.lib
                  if not r.get("missing") and not file_gone(r.get("path"))}
        n = sum(1 for k in (d if isinstance(d, dict) else {}) if k not in listed)
        self._gone = ((mt, len(self.lib)), n)
        return n

    def energy_songs(self):
        """Lieder ohne Stufe von Mixed In Key fuer die Schaetzung: [{path (wie in Mixxx), file (am Mac), bpm, kid, genre}]."""
        out = []
        for r in self.lib or []:
            p = r.get("path") or ""
            if p and not energy_level(r) and not r.get("missing"):
                out.append({"path": p, "file": self._map(p), "bpm": r.get("bpm") or 0.0, "kid": r.get("kid") or 0,
                            "genre": str(r.get("genre") or "")})
        return out

    ENERGY_MIN_S = 30.0                                          # kurze Stuecke (Samples, Jingles) bekommen keine Energie in den Tag

    def energy_fill_songs(self):
        """Datenpflege "Energie eintragen" (Wunsch 09.11.2026): MP3s ab 30 s ohne Stufe von Mixed In Key oder von Hand.
        [(Pfad in Mixxx, Datei am Mac)], dazu wie viele davon noch keine Schaetzung haben."""
        if self.est is None:
            return [], 0
        dur = {r.get("path"): float(r.get("duration") or 0) for r in self.lib or []}
        out, wait = [], 0
        for s in self.energy_songs():
            if not s["file"].lower().endswith(".mp3") or dur.get(s["path"], 0) < self.ENERGY_MIN_S:
                continue
            w = self.est.written.get(s["path"])
            if w == "mik" or (s["path"] in self.est.est and w == self.est.est[s["path"]]):
                continue                                         # steht schon im Tag (von uns oder Mixed In Key)
            if s["path"] not in self.est.est:
                wait += 1
                continue
            out.append((s["path"], s["file"]))
        return out, wait

    def energy_fill_info(self):
        todo, wait = self.energy_fill_songs()
        w = self.est.writer if self.est is not None else None
        return {"offen": len(todo), "warten": wait, "laeuft": bool(w is not None and w.is_alive()), "an": self.est is not None}

    def energy_fill(self):
        """Knopf: die geschaetzten Stufen in diese MP3s schreiben (nur TXXX EnergyLevel, nie ueber Mixed In Key, nie bei einem
        Lied in einem Deck). Laeuft im Hintergrund."""
        todo, _wait = self.energy_fill_songs()
        if not todo:
            return {"started": False, "n": 0}
        loaded = {(d.get("rec") or {}).get("path") for d in self.decks.values()}
        self.est.write_tick(todo, busy=lambda p: p in loaded)
        return {"started": True, "n": len(todo)}

    def energy_tick(self):
        """Alle 30 s: neue Messwerte einlesen (dann die Bibliothek bald neu schicken), neue Lieder messen lassen und, nur mit
        der Einstellung energy_write am Pi, die geschaetzten Stufen in die MP3s schreiben (nie bei einem Lied in einem Deck)."""
        self.key_tick()
        self.loud_tick()
        self.cue_tick()
        if self.est is None:
            return
        try:
            if self.est.refresh():
                self.lib_done = -1e9
            songs = self.energy_songs()
            if not self.est.running():
                self.est.start(songs, self.bg["pause"] if self.bg is not None else None)
            if self.music is not None and getattr(self.music, "energy_write", False):
                loaded = {(d.get("rec") or {}).get("path") for d in self.decks.values()}
                self.est.write_tick(self.energy_fill_songs()[0], busy=lambda p: p in loaded)   # ab 30 s (09.11.2026)
        except Exception as e:                                   # noqa: BLE001  die Schaetzung darf die Bruecke nie anhalten
            self.log(f"Energie-Schaetzung: {str(e)[:120]}")

    def key_tick(self):
        """Alle 30 s: Lieder ohne Tonart in Mixxx messen lassen (TKEY, essentia, numpy), neue Ergebnisse einlesen und, nur mit
        der Einstellung key_write am Pi, geschaetzte Tonarten ins TKEY schreiben (nie bei einem Lied in einem Deck)."""
        if self.kest is None:
            return
        try:
            if self.kest.refresh():
                self.lib_done = -1e9
            songs = [{"path": r["path"], "file": self._map(r["path"]), "need_key": not r.get("kid"), "need_bpm": not r.get("bpm")}
                     for r in self.lib or [] if r.get("path") and (not r.get("kid") or not r.get("bpm")) and not r.get("missing")]
            if not self.kest.running():
                self.kest.start(songs)
            if self.music is not None and getattr(self.music, "key_write", False):
                loaded = {(d.get("rec") or {}).get("path") for d in self.decks.values()}
                self.kest.write_tick([(s["path"], s["file"]) for s in songs], busy=lambda p: p in loaded)
        except Exception as e:                                   # noqa: BLE001  die Tonart darf die Bruecke nie anhalten
            self.log(f"Tonart-Schaetzung: {str(e)[:120]}")

    CUE_EVERY_S = 600.0

    def cue_tick(self, now=None):
        """Alle 10 Minuten: Liste der Mixxx-Lieder ohne Hotcues mit geschaetzten Cues (oder denen aus der MP3) fuer den Start der
        App (mixxx_uebertragen.py --cues schreibt sie vor Mixxx in die Datenbank). Nur mit der Einstellung cue_write am Pi
        (Standard aus). Lieder, in denen Mixxx schon LB-Cues hat, gelten als geschrieben; loescht Markus sie, kommen sie nie wieder."""
        now = time.time() if now is None else now
        if now - getattr(self, "cue_t", -1e9) < self.CUE_EVERY_S:
            return
        self.cue_t = now
        try:
            import cue_estimate as ce
            written = set(ce.load_json(ce.WRITTEN_FILE, []))
            seen = {r["path"] for r in self.mixxx_lib if r.get("cue_lb") and r.get("path")}
            if seen - written:
                written |= seen
                ce.save_json(ce.WRITTEN_FILE, sorted(written))
            pend = os.path.join(ce.DATA_DIR, ce.PENDING_FILE)
            if self.music is None or not getattr(self.music, "cue_write", False):
                if os.path.exists(pend):
                    os.remove(pend)                              # Schalter aus: nichts mehr in Mixxx schreiben
                return
            items, names = [], None                              # names: Analyse-Dateien, einmal je Durchgang gelesen
            for r in self.mixxx_lib:
                p = r.get("path") or ""
                if p and r.get("cue_lb") and p in written and not r.get("missing") and float(r.get("duration") or 0) >= ce.LONG_S:
                    jp = os.path.join(self.dir, track_key(r.get("duration") or 0.0, r.get("bpm"), r.get("kid")) + ".json")
                    if os.path.isfile(jp):                       # langer Mix mit alten LB-Cues: verteilte statt der fruehen (14.11.2026)
                        with open(jp, encoding="utf-8") as fh:
                            res = json.load(fh)
                        new, olds = ce.estimate(res), [ce.estimate_v1(res)]
                        pre = f"{float(r.get('duration') or 0.0):.3f}_"   # aeltere Analysen desselben Liedes (etwa noch ohne BPM):
                        if names is None:
                            names = sorted(os.listdir(self.dir))
                        for fn in names:                                  # die LB-Cues damals kamen vielleicht aus einer davon
                            if fn.startswith(pre) and fn.endswith(".json") and fn != os.path.basename(jp):
                                try:
                                    with open(os.path.join(self.dir, fn), encoding="utf-8") as fh:
                                        o = ce.estimate_v1(json.load(fh))
                                except (OSError, ValueError, KeyError):
                                    continue
                                if o and o not in olds:
                                    olds.append(o)
                        if new and new not in olds:              # mixxx_uebertragen ersetzt nur, wenn in Mixxx genau eine davon steht
                            items.append({"loc": p, "cues": new, "old": olds[0], "olds": olds})
                    continue
                if not p or r.get("cues") or r.get("missing") or p in written:
                    continue
                jp = os.path.join(self.dir, track_key(r.get("duration") or 0.0, r.get("bpm"), r.get("kid")) + ".json")
                f = self._map(p)
                fc = ce.file_cues(f) if f and os.path.exists(f) else []
                if fc:                                           # echte Cues aus der Datei (Mixed In Key/Serato)
                    cues = [[t, f"LB Cue {i + 1}"] for i, t in enumerate(fc[:ce.MAX_CUES])]
                elif os.path.isfile(jp):
                    with open(jp, encoding="utf-8") as fh:
                        cues = ce.estimate(json.load(fh))
                else:
                    continue
                if cues:
                    items.append({"loc": p, "cues": cues})
            old = ce.load_json(ce.PENDING_FILE, None)
            if old != items:
                ce.save_json(ce.PENDING_FILE, items)
                self.log(f"Cues: {len(items)} Mixxx-Lieder ohne Hotcues bekommen beim naechsten Start der App geschaetzte (LB)")
        except Exception as e:                                   # noqa: BLE001  die Cues duerfen die Bruecke nie anhalten
            self.log(f"Cues: {str(e)[:120]}")

    def loud_tick(self):
        """Alle 30 s: Lautheit neuer Lieder messen lassen (ffmpeg ebur128), neue Werte einlesen und, nur mit der Einstellung
        rg_write am Pi, ReplayGain in MP3s ohne eine Angabe schreiben (nie bei einem Lied in einem Deck)."""
        if self.loud is None:
            return
        try:
            if self.loud.refresh():
                pass                                             # neue Werte gehen mit der naechsten Pruefung (alle 2 Minuten) an den Pi:
                # sofort neu schicken hiess bei laufender Messung alle 30 s eine neue Fassung (Fehlerbericht 11.11.2026)
            songs = [{"path": r["path"], "file": self._map(r["path"])} for r in self.lib or [] if r.get("path") and not r.get("missing")]
            if not self.loud.running():
                self.loud.start(songs)
            if self.music is not None and getattr(self.music, "rg_write", False):
                loaded = {(d.get("rec") or {}).get("path") for d in self.decks.values()}
                self.loud.write_tick([(s["path"], s["file"]) for s in songs], busy=lambda p: p in loaded)
        except Exception as e:                                   # noqa: BLE001  die Lautheit darf die Bruecke nie anhalten
            self.log(f"Lautheit: {str(e)[:120]}")

    def folder_tick(self, now=None):
        """Alle 5 s: Ordner-Liste neu einlesen, wenn der Musikordner neu ist oder 10 Minuten um sind; eine fertige Liste
        uebernehmen (self.lib = Mixxx-Lieder plus Ordner-Lieder, Vorhoeren darf sie liefern, Bibliothek bald neu an den Pi)."""
        if self.folder is None:
            return
        root = (self.music.loc.root if self.music is not None else "") or self.folder_root
        if self.folder.due(root, now):
            # Lieder, die Mixxx als fehlend fuehrt, zaehlen nicht als "in Mixxx": liegt die Datei doch da (etwa nach "→ MP3" oder
            # Umbenennen), kommt sie als Ordner-Lied in die Liste (Fehlerbericht 07.11.2026, "Anachronic Jazz Band - Move.mp3")
            known = [r for r in self.mixxx_lib if not r.get("missing")]
            self.folder.start(root, [self._map(r.get("path") or "") for r in known] + [r.get("path") or "" for r in known])
        import music_excl
        ev = music_excl.version()
        if self.folder.ver != self.folder_ver or ev != getattr(self, "excl_ver", 0):
            self.folder_ver, self.excl_ver = self.folder.ver, ev
            songs = list(self.folder.songs)
            self.lib = self.excl_filter(self.mixxx_lib + songs, root)
            self.lib_done = -1e9
            if self.music is not None:
                self.music.loc.paths = {r.get("path") for r in self.lib if r.get("path")}
            # Neue Ordner-Lieder auch analysieren (Probelauf ohne Mixxx, 14.11.2026: die Hintergrund-Analyse zaehlte ihre Lieder
            # beim Start, bevor die Ordner-Liste da war, und sah ohne Mixxx nie ein Lied). Laeuft sie nicht (mehr), neu starten.
            b = self.bg
            if b is not None and not self.lib_off and not (b.get("proc") is not None and b["proc"].is_alive()):
                self.start_background()

    def stick_pause(self):
        """Stick wird ausgeworfen (stick_hold): Hintergrund-Analyse anhalten, laufende Messungen beenden (sie fangen spaeter
        wieder an, was schon gemessen ist, bleibt)."""
        if self.bg is not None:
            self.bg["pause"].set()
        for e in (self.est, self.kest, self.loud):
            p = getattr(e, "proc", None) if e is not None else None
            try:
                if p is not None and e.running():
                    p.terminate()
            except OSError:
                pass

    def excl_filter(self, songs, root=None):
        """Lieder in den ausgeschlossenen Ordnern aus dem Panel weglassen (Wunsch 10.11.2026). Mixxx-Lieder zaehlen mit dem Pfad
        aus Mixxx und mit dem Pfad am Mac (path_map), Ordner-Lieder kommen gar nicht erst herein (folder_lib.walk_mp3)."""
        import music_excl
        if root is None:
            root = (self.music.loc.root if self.music is not None else "") or self.folder_root
        skip = music_excl.matcher(root)
        out = [r for r in songs if not (skip(r.get("path") or "") or skip(self._map(r.get("path") or "")))]
        self.excl_n = len(songs) - len(out)
        return out

    def genres(self):
        """Alle Genres der Bibliothek mit Anzahl Lieder (fuer die Genre-Stile im Panel), die haeufigsten zuerst."""
        cnt = {}
        for r in self.lib:
            g = str(r.get("genre") or "").strip()[:40]
            if g:
                cnt[g] = cnt.get(g, 0) + 1
        return [[g, n] for g, n in sorted(cnt.items(), key=lambda x: (-x[1], x[0].lower()))[:200]]

    def stats(self):
        """Statistik der Bibliothek fuer die Seite Statistik im Panel: Titel, davon analysiert, Energie, Hotcues, Tempo,
        Dateitypen, Spielzeit und je Genre Anzahl und analysiert."""
        try:
            done = {f[:-5] for f in os.listdir(self.dir) if f.endswith(".json")}
        except OSError:
            done = set()
        n = a = cues = 0
        secs = 0.0
        energy = [0] * 10                                        # E1..E9, dann "ohne"
        bpm = [0] * 14                                           # unter 70, 70-79 ... 180-189, ab 190
        ft, genres = {}, {}
        for r in self.lib:
            n += 1
            ok = track_key(r.get("duration") or 0.0, r.get("bpm"), r.get("kid")) in done
            a += ok
            secs += r.get("duration") or 0.0
            lv = energy_level(r)
            energy[min(9, lv) - 1 if lv else 9] += 1
            cues += bool(r.get("cues"))
            b = r.get("bpm") or 0
            bpm[0 if b < 70 else min(13, int((b - 70) // 10) + 1)] += 1
            t = str(r.get("filetype") or "?").lower()[:6]
            ft[t] = ft.get(t, 0) + 1
            g = str(r.get("genre") or "").strip()[:40]
            if g:
                e = genres.setdefault(g, [0, 0])
                e[0] += 1
                e[1] += ok
        top = sorted(genres.items(), key=lambda x: (-x[1][0], x[0].lower()))[:200]
        return {"type": "stats", "bg": self.bg_info(), "n": n, "a": a, "h": round(secs / 3600.0, 1), "cu": cues, "e": energy, "bpm": bpm,
                "ft": dict(sorted(ft.items(), key=lambda x: -x[1])[:8]), "g": [[k, v[0], v[1]] for k, v in top]}

    def tick(self):
        """Plaene alle 3 Sekunden erneut senden (UDP kann Pakete verlieren, der Pi kann spaeter starten), die Liste der
        Genres und die Statistik alle 30 Sekunden."""
        now = time.time()
        import stick_hold
        if stick_hold.tick(now):
            self.log("Stick wieder da: Hintergrundarbeiten laufen weiter")
        hold = stick_hold.held()
        if hold:
            self.stick_pause()
        self.lib_role_tick(now)
        if self.lib_off:                                       # nur Mixxx mitlesen: Schaetzungen des Helfers fuer den Plan nachlesen
            if now - getattr(self, "genres_sent", 0.0) > 30.0:
                self.genres_sent = now
                for e in (self.est, self.kest, self.loud):
                    try:
                        if e is not None:
                            e.refresh()
                    except Exception:                          # noqa: BLE001
                        pass
            self.resend_plans(now)
            return
        if now - self.folder_t > 5.0 and not hold:
            self.folder_t = now
            self.folder_tick(now)
        if self.bg is not None and self.bg["pause"].is_set() and self.q.empty() and now - self.demand_t > 10.0 and not hold:
            self.bg["pause"].clear()                           # 10 s nach der letzten Analyse beim Laden weiter im Hintergrund
        if now - getattr(self, "genres_sent", 0.0) > 30.0:
            self.genres_sent = now
            if not hold:
                self.energy_tick()
            g = self.genres()
            if g:
                self._send(0, {"type": "genres", "g": g})
            if self.lib:
                self._send(0, self.stats())
            if getattr(self, "lib_h", "") and getattr(self, "lib_total", 0):
                self._send(0, self._libhash_msg())   # welche Fassung der Liste der Mac hat (der Pi vergleicht)
            elif self.music is not None:             # Liste noch nicht fertig (Tags lesen, minutenlang): Port trotzdem melden
                self._send(0, {"type": "libhash", "mp": self.music.port})   # ohne "h" (Fehlerbericht 08.11.2026: Pi kannte das Vorhoeren nicht)
        if self.lib and now - getattr(self, "lib_sent", 0.0) > 0.08:     # Bibliothek fuer Showmanager und Musik-Datenbank, nebenbei (rund 2 Minuten)
            self.lib_sent = now
            w0 = self.__dict__.setdefault("_lib_wait0", now)
            pi_h = getattr(self.music, "pi_libh", None) if self.music is not None else None   # Fassung, die der Pi komplett hat
            tags_first = self.folder is not None and not getattr(self, "folder_ver", 0) and now - w0 < 120.0
            wait_pi = self.music is not None and pi_h is None and now - w0 < 60.0    # nach dem Start: erst den Pi fragen
            if not getattr(self, "lib_chunks", None) and not tags_first and not wait_pi:   # erst die Tags der MP3s lesen (Sekunden),
                # sonst ging die ganze Liste mit den alten Mixxx-Werten raus. Geschickt wird nur, wenn der Pi eine andere Fassung
                # hat (Wunsch 07.11.2026: nicht alle 10 Minuten alles, wenn sich nichts geaendert hat); geprueft alle 2 Minuten.
                # Alter Pi ohne Pruefsumme: wie frueher alle 10 Minuten alles.
                if now - getattr(self, "lib_done", -1e9) > (LIB_CHECK_S if pi_h is not None else 600.0):
                    self.lib_done = now
                    try:
                        done = {f[:-5] for f in os.listdir(self.dir) if f.endswith(".json")}
                    except OSError:
                        done = set()
                    try:                                                  # Lieder, die die Analyse nicht lesen konnte (Musik-Datenbank: Filter)
                        with open(os.path.join(self.dir, FAILED_FILE), encoding="utf-8") as f:
                            bad = set(json.load(f))
                    except (OSError, ValueError, TypeError):
                        bad = set()
                    chunks = library_chunks(self.lib_with_tags(), done=done, bad=bad, est=self.est, kest=self.kest, loud=self.loud,
                                            buckets=bucket_count(len(self.lib)))
                    self.lib_h = lib_hash(chunks)
                    vers = self.__dict__.setdefault("lib_vers", {})       # die letzten Fassungen: Vergleich mit der am Pi
                    vers[self.lib_h] = chunks
                    while len(vers) > 4:
                        vers.pop(next(iter(vers)))
                    self.lib_total, self.lib_same, self.lib_base = len(chunks), pi_h == self.lib_h, ""
                    mh, miss = getattr(self.music, "pi_miss", ("", [])) if self.music is not None else ("", [])
                    # alle fehlenden zaehlen (missn), nicht nur die gemeldeten 600: sonst schien "weniger als die Haelfte" zu fehlen,
                    # die Bruecke schickte nie wieder alles und der Pi kam nie zu einer kompletten Liste (Fehlerbericht 11.11.2026)
                    nmiss = max(len(miss), int(getattr(self.music, "pi_missn", 0) or 0)) if self.music is not None else len(miss)
                    # Grundlage fuer "nur Geaendertes": die Fassung, die der Pi komplett hat, oder die, die er gerade fast ganz
                    # hat (dann die fehlenden Stuecke dazu). Sonst lief beim Helfer alle 3 Minuten alles, weil die Energie-
                    # Schaetzung die Liste laufend aendert und dem Pi von der vorigen Fassung immer ein, zwei Stuecke fehlten
                    # (Fehlerbericht 07.11.2026).
                    base, extra = "", []
                    if getattr(self.music, "pi_libd", False) and pi_h in vers and pi_h != self.lib_h:
                        base = pi_h
                    elif mh and mh != self.lib_h and mh in vers and miss and nmiss < len(chunks) // 2:
                        base, extra = mh, miss
                    old = vers.get(base) if base else None
                    diff = (sorted({i for i, (a, b) in enumerate(zip(old, chunks)) if a != b} | {i for i in extra if 0 <= i < len(chunks)})
                            if old is not None and len(old) == len(chunks) else None)
                    if self.lib_same:
                        pass
                    elif mh == self.lib_h and miss and nmiss < len(chunks) // 2:
                        self.lib_chunks = [(i, chunks[i]) for i in miss if 0 <= i < len(chunks)]   # nur die verlorenen nach
                        self.lib_kind = "fehlende"
                    elif diff and len(diff) < len(chunks) // 2:
                        self.lib_chunks, self.lib_base = [(i, chunks[i]) for i in diff], base   # nur die geaenderten Stuecke
                        self.lib_cnt, self.lib_kind = len(diff), "geaenderte"
                    else:
                        self.lib_chunks, self.lib_kind = list(enumerate(chunks)), "alles"
                        self.lib_rounds = getattr(self, "lib_rounds", 0) + 1
                    if not self.lib_same:
                        self.lib_job = len(self.lib_chunks)            # fuer die Statusanzeige: Teil x von diesem Auftrag
                        self.log(f"Liste an den Pi: {'alles' if self.lib_kind == 'alles' else 'nur ' + self.lib_kind} ({self.lib_job} von {len(chunks)} Stuecken)")
                    if chunks:
                        self._send(0, self._libhash_msg())
            for _k in range(3):                                        # drei Stuecke je Takt (rund 15 pro Sekunde)
                if not getattr(self, "lib_chunks", None):
                    break
                i, part = self.lib_chunks.pop(0)
                msg = {"type": "lib", "i": i, "n": self.lib_total, "t": part, "h": self.lib_h}
                if getattr(self, "lib_base", ""):                      # nur Geaendertes: auf welcher Fassung es aufbaut, wie viele Stuecke
                    msg["b"], msg["c"] = self.lib_base, self.lib_cnt
                if not self.lib_chunks:
                    self.lib_done = now                                # naechste Pruefung 2 Minuten nach dem Ende (der Pi meldet bis dahin)
                if self.music is not None:
                    msg["mp"] = self.music.port                        # Vorhoeren: Port des Webservers am Mac (music_serve.py)
                self._send(0, msg)
        self.resend_plans(now)

    def resend_plans(self, now):
        for n, deck in list(self.decks.items()):
            if now - deck["sent"] > 3.0:
                if deck.get("plan"):
                    self._send(n, deck["plan"])
                elif deck.get("info") and deck["info"] != "leer":
                    self._send(n, {"type": "plan", "d": n, "key": "", "info": deck["info"]})
                deck["sent"] = now

    ROLE_S, TAKE_S = 10.0, 30.0       # so oft schaut die Bruecke nach dem Helfer; so lange muss er weg sein, bis sie uebernimmt

    def lib_role_tick(self, now):
        """Mixxx-Bruecke: laeuft der Light-Butler Helfer, gehoert ihm die Bibliothek (Liste, Vorhoeren, Analyse, Auto-Tagger);
        kommt er dazu, gibt sie ab; ist er TAKE_S lang weg, uebernimmt sie (Wunsch von Markus 08.11.2026)."""
        if not self.yield_helper or now - self.role_t < self.ROLE_S:
            return
        self.role_t = now
        up = _helper_up()
        if up:
            self.helper_gone = 0.0
            if not self.lib_off:
                self.lib_release()
                self.log("Light-Butler Helfer laeuft: Liedliste, Vorhoeren und Analyse macht jetzt er")
            return
        if not self.lib_off:
            return
        if not self.helper_gone:
            self.helper_gone = now
        elif now - self.helper_gone >= self.TAKE_S and self.lib_setup is not None:
            self.helper_gone = 0.0
            self.lib_off = False
            self.lib_setup()
            if self.analyze and getattr(self.lib_args, "background_analysis", False):
                self.start_background()
            self.log("Light-Butler Helfer laeuft nicht: die Bruecke macht Liedliste, Vorhoeren und Analyse selbst")

    def lib_release(self):
        """Bibliotheks-Teil an den Helfer abgeben; die Bruecke liest weiter Mixxx mit (Decks, Plan)."""
        self.stop()
        if self.autotag is not None:
            try:
                self.autotag.pause()
            except Exception:                                  # noqa: BLE001
                pass
            self.autotag = None
        self.dupes, self.folder, self.bg, self.lib_off = None, None, None, True
        if self.lib_args is not None:
            make_estimators(self, self.lib_args)             # neu, nur zum Lesen (die alten haben ihr Messen beendet)

    def stop(self):
        """Bibliotheks-Teil beenden: Vorhoeren, Kurven-Sicherung, Schaetzungen und Hintergrund-Analyse. Nur fuer den Light-Butler
        Helfer, der so an die Mixxx-Bruecke abgibt (beide zugleich wuerden dieselben Dateien messen und schreiben)."""
        self.lib_chunks = []
        if self.music is not None:
            self.music.stop()
            self.music = None
        kp = getattr(self, "stems_backup", None)
        if kp is not None:
            kp.stop()
        for e in (self.est, self.kest, self.loud):
            if e is not None:
                e.stop()
        b = self.bg
        if b is not None and b.get("proc") is not None and b["proc"].is_alive():
            b["proc"].terminate()                              # Analyse-Dateien entstehen ueber .tmp und os.replace: nichts halb
            b["proc"].join(3.0)

    def info(self, n):
        return self.decks.get(n, {}).get("info", "")

    def _note(self, n):
        deck = self.decks[n]
        self.log(f"Deck {n}: {deck['info']}")
        if not deck.get("plan"):                                # dem Pi den Grund mitteilen (statt nur "kein Plan")
            self._send(n, {"type": "plan", "d": n, "key": "", "info": deck["info"]})
            deck["sent"] = time.time()


FAILED_FILE = "_nicht_lesbar.json"                             # Lieder, die die Hintergrund-Analyse nicht lesen konnte


def volume_missing(path):
    """Liegt die Datei auf einem Laufwerk (/Volumes/...), das gerade nicht verbunden ist (NAS, USB)?"""
    parts = path.split("/")                             # /Volumes/X/... immer mit "/" (am Mac ist os.sep "/", unter Windows nicht)
    return path.startswith("/Volumes/") and len(parts) > 2 and not os.path.exists("/".join(parts[:3]))


def background_analysis(todo, outdir, pause_ev, prog, pause_s=1.0):
    """Eigener Prozess mit niedriger Prioritaet: analysiert die Lieder aus todo [(key, rec)] nacheinander. Pausiert,
    solange pause_ev gesetzt ist (ein Lied in Mixxx hat Vorrang), wartet bei getrenntem NAS, merkt sich unlesbare
    Dateien in FAILED_FILE (kein neuer Versuch beim naechsten Start). prog = [erledigt, nicht lesbar]."""
    from prio import lower_priority                    # Mac: os.nice(10); Windows: "Niedriger als normal"
    lower_priority(10)
    import analyze_track as at
    fpath = os.path.join(outdir, FAILED_FILE)
    try:
        with open(fpath, encoding="utf-8") as f:
            failed = dict(json.load(f))
    except (OSError, ValueError):
        failed = {}
    for key, rec in todo:
        while True:
            while pause_ev.is_set():
                time.sleep(0.5)
            if not volume_missing(rec["path"]):
                break
            time.sleep(60)                                     # NAS nicht verbunden: warten, nichts als Fehler merken
        if os.path.exists(os.path.join(outdir, key + ".json")):
            continue                                           # inzwischen von Hand oder beim Laden analysiert
        try:
            at.analyze_record(rec, outdir)
            prog[0] += 1
        except Exception as e:                                 # noqa: BLE001  unlesbar: merken, nicht wieder versuchen
            failed[key] = f"{rec.get('artist') or ''} - {rec.get('title') or ''}: {str(e)[:100]}"
            prog[1] += 1
            tmp = fpath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(failed, f, ensure_ascii=False, indent=0)
            os.replace(tmp, fpath)
        time.sleep(pause_s)
    print(f"[{time.strftime('%H:%M:%S')}] Hintergrund-Analyse fertig: {prog[0]} analysiert, {prog[1]} nicht lesbar", flush=True)


HELPER_DIR_NAME = "Light-Butler-Helfer"                     # Programmordner des Helfers (install_helper.sh)
SHARED_SUBS = ("autotag", "doppelte", "energie", "tonart")   # gemeinsam in ~/Light-Butler-Daten (Mixxx-App und Helfer)


def merge_old_data(here, root, log=None):
    """Einmal beim Start: was der Helfer frueher in seinem eigenen Ordner gesammelt hat (Vorschlaege, Doppelte "alle behalten",
    Energie- und Tonart-Messungen), in die gemeinsame Ablage root uebernehmen, nichts verlieren; danach heisst der alte Ordner
    NAME.uebernommen (Fehlerbericht 07.11.2026). Laeuft nur, wenn here nicht schon root ist (die Mixxx-App liegt in root)."""
    try:
        if os.path.realpath(here) == os.path.realpath(root) or os.path.basename(os.path.realpath(here)) != HELPER_DIR_NAME:
            return 0                                            # nur im Ordner des Helfers (nie im Projektordner bei den Tests)
    except OSError:
        return 0
    moved = 0
    for sub in SHARED_SUBS:
        src, dst = os.path.join(here, sub), os.path.join(root, sub)
        if not os.path.isdir(src):
            continue
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            a, b = os.path.join(src, name), os.path.join(dst, name)
            if not os.path.isfile(a) or name.endswith(".tmp"):
                continue
            try:
                if not os.path.exists(b):
                    shutil.copy2(a, b)
                elif name.endswith(".jsonl"):                     # Messwerte: fehlende Zeilen anhaengen
                    with open(b, encoding="utf-8") as f:
                        have = set(f.read().splitlines())
                    with open(a, encoding="utf-8") as f:
                        add = [x for x in f.read().splitlines() if x.strip() and x not in have]
                    if add:
                        with open(b, "a", encoding="utf-8") as f:
                            f.write("".join(x + "\n" for x in add))
                elif name.endswith(".json"):
                    with open(a, encoding="utf-8") as f:
                        da = json.load(f)
                    with open(b, encoding="utf-8") as f:
                        db = json.load(f)
                    if isinstance(da, list) and isinstance(db, list):  # "alle behalten": beide Listen
                        out = db + [x for x in da if x not in db]
                    elif isinstance(da, dict) and isinstance(db, dict) and isinstance(db.get("items"), dict):   # Vorschlaege
                        items = dict(db["items"])
                        for k, v in (da.get("items") or {}).items():   # erledigt/abgelehnt geht vor offen, sonst der neuere
                            w = items.get(k)
                            if (w is None or (w.get("state", "offen") == "offen" and v.get("state", "offen") != "offen")
                                    or (w.get("state") == v.get("state") and float(v.get("t") or 0) > float(w.get("t") or 0))):
                                items[k] = v
                        out = dict(db, items=items, auto=bool(db.get("auto") or da.get("auto")))
                    elif isinstance(da, dict) and isinstance(db, dict):
                        out = dict(db, **{k: v for k, v in da.items() if k not in db})
                    else:
                        continue
                    with open(b + ".tmp", "w", encoding="utf-8") as f:
                        json.dump(out, f, ensure_ascii=False)
                    os.replace(b + ".tmp", b)
                moved += 1
            except (OSError, ValueError, TypeError, AttributeError) as e:
                if log:
                    log(f"Daten uebernehmen: {name}: {e}")
        try:
            os.replace(src, src + ".uebernommen")
        except OSError:
            pass
    if moved and log:
        log(f"Daten aus {here} in die gemeinsame Ablage {root} uebernommen ({moved} Dateien)")
    return moved


def make_estimators(fw, args):
    """Energie- und Tonart-Schaetzung: in der Bruecke auch ohne Bibliotheks-Teil (nur lesen, fuer den Plan der Decks)."""
    if getattr(args, "energy_est", True) and fw.analyze:          # geschaetzte Energiestufe fuer Lieder ohne Mixed In Key
        try:
            from energy_level import Estimator
            fw.est = Estimator(log=fw.log)
            fw.log(f"Energie-Schaetzung: {len(fw.est.est)} Lieder geschaetzt")
        except Exception as e:                                     # noqa: BLE001  ohne numpy oder Modell: ohne Schaetzung weiter
            fw.log(f"Energie-Schaetzung aus: {e}")
        try:
            from key_estimate import KeyEstimator
            fw.kest = KeyEstimator(log=fw.log)
        except Exception as e:                                     # noqa: BLE001
            fw.log(f"Tonart-Schaetzung aus: {e}")
        try:
            from loudness import Loudness
            fw.loud = Loudness(log=fw.log)
        except Exception as e:                                     # noqa: BLE001
            fw.log(f"Lautheit aus: {e}")


def _helper_up():
    try:
        from apc_relay import helper_running
        return helper_running()
    except ImportError:
        return False


def cover_refresh_bg(pi_url, paths, log=None, gap_s=0.2, post=None):
    """Fehlerbericht 09.11.2026: neue Cover (auch mit anderen Programmen hinterlegt) zeigte die Musik-Datenbank nicht, der Pi
    hatte noch das alte (es haengt am Fingerabdruck der Musik, der bleibt gleich). Die Ordner-Liste meldet geaenderte Dateien,
    der Pi holt ihr Cover neu (cover_refresh). Im Hintergrund, eines nach dem anderen."""
    def send(p):
        req = urllib.request.Request(pi_url.rstrip("/") + "/api/sm/cmd", data=json.dumps({"op": "cover_refresh", "path": p}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    post = post or send

    def run():
        ok = 0
        for p in paths:
            try:
                post(p)
                ok += 1
            except Exception:                                      # noqa: BLE001  Pi weg: beim naechsten Mal
                pass
            time.sleep(gap_s)
        if log is not None and ok:
            log(f"Cover: {ok} geaenderte Dateien an den Pi gemeldet")
    t = threading.Thread(target=run, name="cover-melden", daemon=True)
    t.start()
    return t


def setup_library(fw, args, lib, pm):
    """Bibliotheks-Teil: Ordner-Liste, Vorhoeren mit Auto-Tagger, Doppelten, Kurven-Sicherung. Im Helfer immer, in der Mixxx-Bruecke
    nur, wenn kein Helfer laeuft (Wunsch von Markus 08.11.2026: alles, was Mixxx nicht braucht, macht der Helfer)."""
    if not getattr(args, "no_folder_lib", False):                 # zweite Liedquelle: MP3s im Musikordner ohne Mixxx-Eintrag
        try:
            from folder_lib import FolderLib
            fw.folder = FolderLib(log=fw.log, key_id_from_text=key_id_from_text)
            fw.folder_root = os.path.expanduser(getattr(args, "music_root", "") or "")
            if args.send:                                          # geaenderte Dateien: Cover am Pi neu holen (09.11.2026)
                fw.folder.on_changed = lambda paths: cover_refresh_bg(f"http://{args.send}:{getattr(args, 'pi_web', 8080)}", paths, fw.log)
        except ImportError as e:
            fw.log(f"Ordner-Liste aus: folder_lib.py fehlt ({e}), install_launcher.sh erneut ausfuehren")
    if args.send and not getattr(args, "no_music_serve", False):     # Vorhoeren und "Show anlegen" im Panel: MP3s vom Mac
        try:
            from music_serve import MusicServer
        except ImportError as e:                                   # Datei fehlt (alte Installation): Bruecke laeuft ohne Vorhoeren weiter
            fw.log(f"Vorhoeren aus: music_serve.py fehlt ({e}), install_launcher.sh erneut ausfuehren")
            return
        ms = MusicServer([r.get("path") or "" for r in lib], port=getattr(args, "music_port", 9025),
                         root=os.path.expanduser(getattr(args, "music_root", "") or ""), path_map=pm, log=fw.log, marks=fw.marks_for_path)
        try:                                                       # der Light-Butler Helfer gibt Port 9025 binnen 2 s frei
            from apc_relay import helper_running
            tries = 6 if helper_running() else 1
        except ImportError:
            tries = 1
        if ms.start(tries=tries, retry_bg=True):
            fw.music = ms
            ms.on_converted = lambda src, dst: fw.folder is not None and setattr(fw.folder, "t", 0.0)   # neue MP3: Ordner gleich neu einlesen
            ms.meta = fw.meta_for_path
            ms.on_tags = fw.tags_written                            # Tag geschrieben: Liste am Pi gleich mit den neuen Werten
            ms.status_info = fw.status                              # Statusanzeige: Tags lesen, Liste schicken
            ms.sync_info = fw.sync_info                             # Abgleich Mixxx und Stick fuer die Musik-Datenbank
            ms.energy_info, ms.energy_fill = fw.energy_fill_info, fw.energy_fill   # Datenpflege: Energie eintragen (09.11.2026)
            ms.excl_info = lambda: int(getattr(fw, "excl_n", 0))    # Mixxx-Lieder in ausgeschlossenen Ordnern (Einstellungen)
            ms.lib_songs = fw.lib_with_tags                         # Import-Seite: gibt es das Lied schon? (10.11.2026)
            # aktuelle Mixxx-Datenbank: die Minuten-Kopie aus launch.sh (Python darf den Mixxx-Ordner nicht lesen), sonst direkt
            live_copy = os.path.join(os.path.dirname(os.path.abspath(os.path.expanduser(args.db))), "mixxxdb.live.sqlite") if getattr(args, "db", None) else ""
            fw.live_db = live_copy or next((p for p in (os.path.expandvars(os.path.expanduser(c)) for c in DB_CANDIDATES) if os.path.isfile(p)), "")
            try:                                                   # Doppelte finden und vergleichen (Seite Doppelte), nur lesend
                from dupes import Dupes
                from music_serve import find_cover as _fc
                import tag_edit as _te
                fw.dupes = Dupes(lambda: fw.lib, fw._map, energy=energy_level, has_cover=lambda f: _fc(f) is not None,
                                 read_tags=_te.read_tags, fingerprint=audio_fingerprint, log=fw.log)
                ms.dupes = fw.dupes
            except Exception as e:                                 # noqa: BLE001
                fw.log(f"Doppelte aus: {e}")
            try:                                                   # Beschaedigte Dateien finden (afinfo) und auf Klick reparieren (14.11.2026)
                from damaged import Damaged
                from convert_mp3 import find_ffmpeg as _ff
                from music_serve import to_trash as _tt
                fw.damaged = Damaged(lambda: fw.lib, fw._map, log=fw.log, ffmpeg=_ff, trash=_tt)
                ms.damaged = fw.damaged
                if sys.platform == "darwin":
                    fw.damaged.start()
            except Exception as e:                                 # noqa: BLE001
                fw.log(f"Beschaedigte Dateien aus: {e}")
            try:                                                   # Auto-Tagger: Lieder ohne Cover vorrecherchieren (Seite Vorschlaege)
                from auto_tag import AutoTagger
                from convert_mp3 import find_ffmpeg
                from music_serve import find_cover
                fw.autotag = AutoTagger(fw.autotag_songs, pi_url=f"http://{args.send}:{getattr(args, 'pi_web', 8080)}", log=fw.log,
                                        has_cover=lambda f: find_cover(f) is not None, ffmpeg=find_ffmpeg())
                ms.autotag = fw.autotag
                fw.autotag.on_applied = fw.tags_written              # automatisch uebernommene gleich in die Liste am Pi
                fw.autotag.resume()
            except Exception as e:                                 # noqa: BLE001  ohne Auto-Tagger laeuft alles andere weiter
                fw.log(f"Auto-Tagger aus: {e}")
            try:                                                   # Dateien pruefen (Seite /musik/pruefen): Datenmuell, Dateinamen
                from file_check import FileCheck
                ms.check = FileCheck(lambda: ms.loc.root, fw.lib_with_tags, ms.loc.locate, log=fw.log,
                                     renamed=fw.path_moved, ready=fw.file_tags_ready)
            except ImportError as e:
                fw.log(f"Dateien pruefen aus: file_check.py fehlt ({e})")
            try:                                                   # Genre-Editor (Seite /musik/genres)
                from genre_edit import GenreEditor
                ms.genres = GenreEditor(fw.lib_with_tags, ms.loc.locate, lambda: ms.loc.root, log=fw.log, ready=fw.file_tags_ready,
                                        on_written=lambda p, f: ms.on_tags is not None and ms.on_tags(p, f))
            except ImportError as e:
                fw.log(f"Genre-Editor aus: genre_edit.py fehlt ({e})")
            ms.sync(f"http://{args.send}:{getattr(args, 'pi_web', 8080)}/api/musik/conf")   # Musikordner aus dem Panel
            try:                                                   # Spur-Kurven vom Pi auf den Stick sichern (neben dem Musikordner)
                from stems_backup import Keeper
                fw.stems_backup = Keeper(f"http://{args.send}:{getattr(args, 'pi_web', 8080)}", lambda: ms.loc.root, log=fw.log)
                fw.stems_backup.start()
            except ImportError as e:
                fw.log(f"Kurven-Sicherung aus: stems_backup.py fehlt ({e}), install_launcher.sh erneut ausfuehren")


def make_forwarder(args, lib, sock):
    if lib is None:
        return None
    try:                                                        # Helfer: frueher eigene Ablage, jetzt gemeinsam mit der Mixxx-App
        import auto_tag
        merge_old_data(os.path.dirname(os.path.abspath(__file__)), os.path.dirname(auto_tag.DATA_DIR),
                       log=lambda t: print(f"[{time.strftime('%H:%M:%S')}] {t}", flush=True))
    except Exception as e:                                      # noqa: BLE001  darf den Start nie verhindern
        print(f"Daten uebernehmen: {e}", flush=True)
    pm = []
    for item in (getattr(args, "path_map", None) or []):
        old, _, new = item.partition("=")
        pm.append((old, new))
    def log(text):                                              # ohne Monitor-Anzeige: Meldungen als Textzeilen (fuer die Log-Datei)
        print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)
    fw = Forwarder(lib, sock, (args.send, args.pi_port) if args.send else None,
                   os.path.expanduser(getattr(args, "analysis_dir", None) or ANALYSIS_DIR),
                   analyze=not getattr(args, "no_analyze", False), path_map=pm,
                   log=None if getattr(args, "monitor", False) else log)
    make_estimators(fw, args)
    fw.yield_helper = bool(getattr(args, "yield_to_helper", False))   # nur die Mixxx-Bruecke, nie der Helfer selbst
    fw.lib_setup = lambda: setup_library(fw, args, lib, pm)
    fw.lib_args = args
    if fw.yield_helper and _helper_up():
        fw.lib_off = True                                          # Liste, Vorhoeren, Analyse macht der Light-Butler Helfer
        fw.log("Liedliste, Vorhoeren und Analyse macht der Light-Butler Helfer, die Bruecke liest nur Mixxx mit")
        return fw
    setup_library(fw, args, lib, pm)
    return fw


def handle_state(d, fw, sock, args):
    """Deck-Zustand weitergeben: ueber den Forwarder (mit Plan) oder, ohne Bibliothek, nur als Zustand."""
    if fw:
        fw.handle(d)
    elif sock:
        m = dict(d)
        m["t"] = round(time.time(), 3)
        send_udp(sock, json.dumps(m, separators=(",", ":")).encode("ascii"), (args.send, args.pi_port))


# ---- Nachrichten lesen ---------------------------------------------------------------------------------------
def decode_sysex(data):
    """SysEx-Daten (ohne F0/F7) aus dem Mixxx-Mapping in ein Dict umwandeln; None bei fremden Nachrichten."""
    data = bytes(data)
    if len(data) < 3 or tuple(data[:2]) != SYSEX_ID:
        return None
    try:
        return json.loads(data[2:].decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return None


def audible(deck):
    """Wie laut ein Deck im Mix tatsaechlich ist (0..1): Kanalfader mal Crossfader-Seite, nur wenn es spielt."""
    if not deck.get("pl") or not deck.get("tl"):
        return 0.0
    w = deck.get("vo", 1.0)
    cf, side = deck.get("cf", 0.0), deck.get("or", 1)
    if side == 0:
        w *= 1.0 if cf <= 0 else max(0.0, 1.0 - cf)
    elif side == 2:
        w *= 1.0 if cf >= 0 else max(0.0, 1.0 + cf)
    return round(max(0.0, min(1.0, w)), 2)


def fmt_time(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


def render(decks, lib=None, fw=None):
    """Textzeilen der Live-Tabelle."""
    lines = ["Light-Butler - Mixxx-Zustand (Strg+C beendet)", ""]
    for n in sorted(decks):
        d, age = decks[n]["data"], time.time() - decks[n]["t"]
        if not d.get("tl"):
            lines.append(f"Deck {n}  leer")
            continue
        pitch = (d.get("rr", 1.0) - 1.0) * 100.0
        pos_s = d.get("pp", 0.0) * d.get("du", 0.0)
        lines.append(
            f"Deck {n}  {'spielt ' if d.get('pl') else 'Pause  '} Laenge {fmt_time(d.get('du'))}  "
            f"Position {fmt_time(pos_s)} ({d.get('pp', 0) * 100:4.1f} %)  "
            f"Datei {d.get('fb', 0):6.2f} BPM  jetzt {d.get('bp', 0):6.2f} BPM  Pitch {pitch:+5.1f} %  "
            f"Beat {d.get('bd', 0):.2f}  Sync {'an ' if d.get('sy') else 'aus'}  "
            f"Fader {d.get('vo', 0) * 100:3.0f} %  hoerbar {audible(d) * 100:3.0f} %  Tonart {d.get('k', 0)}"
            + ("   (veraltet)" if age > 2.5 else ""))
        if lib is not None:
            lines.append(f"        erkannt: {ident_text(identify(lib, d))}   "
                         f"(Datei-Tonart Nr. {d.get('fk', 0)}, Laenge {d.get('du', 0):.3f} s)")
        if fw is not None:
            lines.append(f"        Plan:    {fw.info(n)}")
    return lines


# ---- MIDI-Eingang ------------------------------------------------------------------------------------------------
def open_port(name_part):
    try:
        import mido
    except ImportError:
        sys.exit("mido fehlt:  pip install mido python-rtmidi")
    names = mido.get_input_names()
    if not names:
        sys.exit("Keine MIDI-Ports gefunden. " + ("loopMIDI mit dem Anschluss Light-Butler starten (siehe Handbuch)."
                 if sys.platform == "win32" else "IAC-Treiber aktivieren (siehe README)."))
    pick = [n for n in names if name_part.lower() in n.lower()]
    if not pick:
        sys.exit(f"Kein MIDI-Port mit '{name_part}' gefunden. Vorhanden: {names}")
    print("Lese von:", pick[0])
    return mido.open_input(pick[0])


SYSEX_LINE = None


def parse_log_line(line):
    """Zeile aus Mixxx' Terminal-Ausgabe (--controller-debug) -> SysEx-Daten ohne F0/F7, sonst None."""
    global SYSEX_LINE
    import re
    if SYSEX_LINE is None:
        SYSEX_LINE = re.compile(r"outgoing:.*?sysex:\s*\[([0-9A-Fa-f ]+)\]")
    m = SYSEX_LINE.search(line)
    if not m:
        return None
    try:
        raw = bytes(int(h, 16) for h in m.group(1).split())
    except ValueError:
        return None
    if len(raw) < 4 or raw[0] != 0xF0 or raw[-1] != 0xF7:
        return None
    return raw[1:-1]


def run_stdin(args):
    """Nachrichten direkt aus Mixxx' Terminal-Ausgabe lesen (ohne MIDI-Port):
       mixxx --controller-debug 2>&1 | python3 mixxx_bridge.py --stdin --monitor"""
    import queue
    import threading
    q = queue.Queue()

    def reader():
        for line in sys.stdin:
            data = parse_log_line(line)
            if data is not None:
                q.put(data)
        q.put(None)                                             # Mixxx wurde beendet

    threading.Thread(target=reader, daemon=True).start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if args.send else None
    lib = open_library(args)
    if lib:
        sys.stderr.write(f"Bibliothek geladen: {len(lib)} Titel\n")
    fw = make_forwarder(args, lib, sock)
    if fw is not None and fw.analyze and getattr(args, "background_analysis", False) and not fw.lib_off:
        fw.start_background()                                  # noch nicht analysierte Lieder im Hintergrund
    decks, count, last_draw = {}, 0, 0.0
    try:
        while True:
            try:
                data = q.get(timeout=0.2)
            except queue.Empty:
                data = False
            if data is None:
                print("\nMixxx wurde beendet.")
                return
            if data:
                d = decode_sysex(data)
                if d is not None:
                    count += 1
                    decks[d["d"]] = {"data": d, "t": time.time()}
                    handle_state(d, fw, sock, args)
            if fw:
                fw.tick()
            if args.monitor and time.time() - last_draw > 0.4:
                last_draw = time.time()
                lines = render(decks, lib, fw) if decks else ["Warte auf Daten aus Mixxx' Terminal-Ausgabe ... (Mapping aktiviert?)"]
                sys.stdout.write("\033[H\033[J" + "\n".join(lines) + f"\n\nEmpfangen: {count} Nachrichten (aus dem Mixxx-Log)\n")
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nBeendet.")


def start_apc(args):
    """APC mini mk2 am Mac: Tasten an den Pi, LEDs zurueck (apc_relay.py), nur mit --send."""
    if not args.send or getattr(args, "no_apc", False):
        return None
    try:
        from apc_relay import ApcRelay
    except ImportError:
        print("Hinweis: apc_relay.py fehlt, APC am Mac wird nicht weitergeleitet")
        return None
    from apc_relay import helper_running
    r = ApcRelay(args.send, args.apc_port, log=lambda s: print(s, flush=True), paused=helper_running)
    return r if r.start() else None


def start_lumi(args):
    """ROLI LUMI Keys am Mac: Noten an den Pi (apc_relay.lumi_relay), nur mit --send."""
    if not args.send or getattr(args, "no_lumi", False):
        return None
    try:
        from apc_relay import helper_running, lumi_relay
    except ImportError:
        print("Hinweis: apc_relay.py fehlt, Lumi am Mac wird nicht weitergeleitet")
        return None
    r = lumi_relay(args.send, args.lumi_port, log=lambda s: print(s, flush=True), paused=helper_running)
    return r if r.start() else None


def start_audio(args):
    """Ton vom Mac (BlackHole) an den Pi, Eingang "Mac (Netzwerk)" (audio_send.py), nur mit --send."""
    if not args.send or getattr(args, "no_audio", False):
        return None
    try:
        from audio_send import AudioSender
    except ImportError as e:
        print(f"Hinweis: Ton-Weiterleitung nicht moeglich ({e})")
        return None
    from apc_relay import helper_running
    s = AudioSender(args.send, args.audio_port, hint=args.audio_device, log=lambda m: print(m, flush=True), paused=helper_running)
    return s if s.start() else None


def claim_bridge(args):
    """Mit --send: Prozessnummer in ~/.light-butler-bruecke.pid, solange die Bruecke laeuft. Daran erkennt der Light-Butler
    Helfer, dass er Liedliste, Vorhoeren, Schaetzung und Analyse der Bruecke ueberlassen soll."""
    if not args.send:
        return
    try:
        import atexit
        from apc_relay import BRIDGE_PID, remove_pid, write_pid
        write_pid(BRIDGE_PID)
        atexit.register(remove_pid, BRIDGE_PID)
    except (ImportError, OSError) as e:
        print(f"Hinweis: Prozessdatei der Bruecke nicht geschrieben ({e})")


def run(args):
    claim_bridge(args)
    start_apc(args)
    start_lumi(args)
    start_audio(args)
    if args.stdin:
        return run_stdin(args)
    port = open_port(args.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if args.send else None
    decks, last_draw, count = {}, 0.0, 0
    lib = open_library(args)
    if lib:
        print(f"Bibliothek geladen: {len(lib)} Titel")
    fw = make_forwarder(args, lib, sock)
    if fw is not None and fw.analyze and getattr(args, "background_analysis", False) and not fw.lib_off:
        fw.start_background()                                  # noch nicht analysierte Lieder im Hintergrund
    try:
        while True:
            for msg in port.iter_pending():
                if args.raw:                                    # Diagnose: alles zeigen, was am Port ankommt
                    print(f"[{time.strftime('%H:%M:%S')}] {msg.type} {len(getattr(msg, 'data', []))} Byte: {str(msg)[:110]}")
                if msg.type != "sysex":
                    continue
                d = decode_sysex(msg.data)
                if d is None:
                    continue
                count += 1
                decks[d["d"]] = {"data": d, "t": time.time()}
                handle_state(d, fw, sock, args)
            if fw:
                fw.tick()
            if args.raw:
                time.sleep(0.01)
                continue
            if args.monitor and time.time() - last_draw > 0.4:
                last_draw = time.time()
                lines = render(decks, lib, fw) if decks else ["Warte auf Daten von Mixxx ... (Mapping aktiviert? Lied geladen?)"]
                sys.stdout.write("\033[H\033[J" + "\n".join(lines) + f"\n\nEmpfangen: {count} Nachrichten\n")
                sys.stdout.flush()
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nBeendet.")


# ---- Mixxx-Bibliothek pruefen ---------------------------------------------------------------------------------------
def library_check(path=None):
    if path is None:
        found = [p for p in (os.path.expandvars(os.path.expanduser(c)) for c in DB_CANDIDATES) if os.path.exists(p)]
        if not found:
            sys.exit("Mixxx-Datenbank nicht gefunden. Gesucht in:\n  " + "\n  ".join(DB_CANDIDATES) +
                     "\nMit --db den Pfad angeben (Mixxx -> Einstellungen -> Bibliothek).")
        path = found[0]
    elif not os.path.exists(path):
        sys.exit(f"Mixxx-Datenbank nicht gefunden: {path}")
    tmp = os.path.join(tempfile.mkdtemp(), "mixxxdb.sqlite")
    try:
        shutil.copy2(path, tmp)                                 # Kopie, damit Mixxx nicht gestoert wird
    except PermissionError:
        sys.exit(
            "macOS erlaubt dem Terminal keinen Zugriff auf den Mixxx-Ordner (Datenschutz-Schutz).\n"
            "Einfachster Weg: im Finder (Menue Gehe zu -> Ordner ...) diesen Ordner oeffnen:\n"
            f"  {os.path.dirname(path)}\n"
            "die Datei mixxxdb.sqlite in den Ordner Downloads kopieren und dann ausfuehren:\n"
            "  python3 mixxx_bridge.py --library --db ~/Downloads/mixxxdb.sqlite\n"
            "Oder: Systemeinstellungen -> Datenschutz & Sicherheit -> Festplattenvollzugriff -> Terminal einschalten "
            "und das Terminal neu starten.")
    con = sqlite3.connect(tmp)
    cols = {r[1] for r in con.execute("PRAGMA table_info(library)")}
    if not cols:
        sys.exit("Tabelle 'library' nicht gefunden - ist das eine Mixxx-Datenbank?")
    sel = ["id", "artist", "title", "duration", "bpm"] + [c for c in ("key", "key_id", "beats_version", "mixxx_deleted", "bpm_lock") if c in cols]
    rows = [dict(zip(sel, r)) for r in con.execute(f"SELECT {', '.join(sel)} FROM library")]
    rows = [r for r in rows if not r.get("mixxx_deleted")]
    for r in rows:                                              # Tonart einheitlich als Mixxx-Nummer (egal welche Schreibweise)
        r["kid"] = int(r.get("key_id") or 0) or key_id_from_text(r.get("key"))
    n = len(rows)
    if n == 0:
        sys.exit("Die Bibliothek ist leer.")
    with_bpm = [r for r in rows if (r["bpm"] or 0) > 0]
    with_dur = [r for r in rows if (r["duration"] or 0) > 0]
    with_key = [r for r in rows if r.get("key")]
    with_grid = [r for r in rows if r.get("beats_version")] if "beats_version" in cols else []
    # Eindeutigkeit: Laenge (auf 0,1 s) und Tempo (auf 0,1 BPM) zusammen
    groups = {}
    for r in with_dur:
        groups.setdefault((round(r["duration"], 1), round(r["bpm"] or 0, 1)), []).append(r)
    dup = [g for g in groups.values() if len(g) > 1]
    n_dup = sum(len(g) for g in dup)
    print(f"Mixxx-Bibliothek: {path}")
    print(f"  Titel gesamt:              {n}")
    print(f"  mit Laenge:                {len(with_dur)}")
    print(f"  mit BPM (analysiert):      {len(with_bpm)}  ({100 * len(with_bpm) // n} %)")
    print(f"  mit Tonart:                {len(with_key)}  ({100 * len(with_key) // n} %)")
    if "beats_version" in cols:
        print(f"  mit Beat-Raster:           {len(with_grid)}  ({100 * len(with_grid) // n} %)")
    print(f"  Erkennung ueber Laenge+BPM: eindeutig {len(with_dur) - n_dup} von {len(with_dur)}, "
          f"nicht eindeutig {n_dup} (in {len(dup)} Gruppen)")
    # Genauer, nur fuer echte Lieder (ab 60 s) und mit feinerer Aufloesung (0,01 s und 0,01 BPM)
    songs = [r for r in with_dur if r["duration"] >= 60]
    fine = {}
    for r in songs:
        fine.setdefault((round(r["duration"], 2), round(r["bpm"] or 0, 2)), []).append(r)
    fdup = [g for g in fine.values() if len(g) > 1]
    n_fdup = sum(len(g) for g in fdup)
    print(f"  Nur Lieder ab 60 s:        {len(songs)} Titel, davon ueber Laenge+BPM (0,01 s / 0,01 BPM) "
          f"eindeutig {len(songs) - n_fdup}, nicht eindeutig {n_fdup} (in {len(fdup)} Gruppen)")
    short = [r for r in with_dur if r["duration"] < 60]
    print(f"  Kurze Dateien unter 60 s:  {len(short)} (Samples, Jingles; fuer Licht nicht relevant)")
    # dritter Hinweis: die Tonart (Mixxx liefert sie live mit)
    fk = {}
    for r in songs:
        fk.setdefault((round(r["duration"], 2), round(r["bpm"] or 0, 2), r.get("kid") or 0), []).append(r)
    kdup = [g for g in fk.values() if len(g) > 1]
    n_kdup = sum(len(g) for g in kdup)
    print(f"  Mit Tonart als dritter Hinweis: eindeutig {len(songs) - n_kdup} von {len(songs)} Liedern, "
          f"nicht eindeutig {n_kdup}")
    # Wie fein ist die Laenge gespeichert? Anteil der Lieder mit ganzzahliger Laenge
    whole = sum(1 for r in songs if abs(r["duration"] - round(r["duration"])) < 0.005)
    print(f"  Laenge ganzzahlig gespeichert: {whole} von {len(songs)} Liedern ({100 * whole // max(1, len(songs))} %)")
    for g in sorted(fdup, key=len, reverse=True)[:8]:
        print("    gleich lang und gleiches Tempo:",
              " | ".join(f"{r['artist']} - {r['title']} [{r['duration']:.3f} s, {r['bpm']:.2f} BPM, Tonart {r.get('key')} = Nr. {r.get('kid')}]"
                         for r in g[:3]))
    if with_bpm:
        bs = sorted(r["bpm"] for r in with_bpm)
        print(f"  Tempo-Bereich:             {bs[0]:.0f} bis {bs[-1]:.0f} BPM (Mitte {bs[len(bs) // 2]:.0f})")
    con.close()


def main():
    ap = argparse.ArgumentParser(description="Mixxx -> Light-Butler Bruecke")
    ap.add_argument("--list", action="store_true", help="MIDI-Ports anzeigen")
    ap.add_argument("--monitor", action="store_true", help="Zustand der Decks live anzeigen")
    ap.add_argument("--send", metavar="PI_IP", help="Zustand per UDP an den Pi schicken")
    ap.add_argument("--analysis-dir", default=None, help="Ordner mit den Analyse-Dateien (Standard: analysis neben diesem Programm)")
    ap.add_argument("--no-analyze", action="store_true", help="fehlende Analysen nicht automatisch berechnen")
    ap.add_argument("--background-analysis", action="store_true",
                    help="alle noch nicht analysierten Lieder nach und nach im Hintergrund analysieren (niedrige Prioritaet)")
    ap.add_argument("--path-map", action="append", metavar="ALT=NEU", help="Pfad-Anfang ersetzen, falls das NAS anders eingebunden ist")
    ap.add_argument("--music-root", default="", metavar="ORDNER", help="Musikordner am Mac (USB-Stick), falls er anders heisst als in Mixxx (MUSIC_ROOT in config.sh)")
    ap.add_argument("--music-port", type=int, default=9025, help="Port des Vorhoer-Servers fuer das Panel (Standard 9025)")
    ap.add_argument("--no-folder-lib", action="store_true", help="den Musikordner nicht nach Liedern ohne Mixxx-Eintrag durchsuchen")
    ap.add_argument("--no-music-serve", action="store_true", help="kein Vorhoeren: die MP3s nicht fuer das Panel bereitstellen")
    ap.add_argument("--pi-web", type=int, default=8080, help="Port des Web-Panels am Pi (fuer den Musikordner aus den Einstellungen)")
    ap.add_argument("--alles-selbst", dest="yield_to_helper", action="store_false", default=True,
                    help="Liedliste, Vorhoeren und Analyse immer selbst machen, auch wenn der Light-Butler Helfer laeuft")
    ap.add_argument("--stdin", action="store_true", help="statt MIDI-Port die Terminal-Ausgabe von Mixxx (--controller-debug) lesen")
    ap.add_argument("--raw", action="store_true", help="Diagnose: jede ankommende MIDI-Nachricht einzeln ausgeben")
    ap.add_argument("--pi-port", type=int, default=PI_PORT)
    ap.add_argument("--no-apc", action="store_true", help="APC mini mk2 am Mac nicht an den Pi weiterleiten")
    ap.add_argument("--apc-port", type=int, default=9021, help="UDP-Port des Pi fuer den APC mini mk2")
    ap.add_argument("--no-lumi", action="store_true", help="ROLI LUMI Keys am Mac nicht an den Pi weiterleiten")
    ap.add_argument("--lumi-port", type=int, default=9023, help="UDP-Port des Pi fuer den ROLI LUMI Keys")
    ap.add_argument("--no-audio", action="store_true", help="Ton (BlackHole) nicht an den Pi schicken")
    ap.add_argument("--audio-device", default=None, help="Teil des Namens des Ton-Eingangs (Standard: Mac BlackHole, Windows VB-Cable, Stereomix, Line-In)")
    ap.add_argument("--audio-port", type=int, default=9022, help="UDP-Port des Pi fuer den Ton vom Mac")
    ap.add_argument("--port", default=DEFAULT_PORT, help="Teil des MIDI-Port-Namens (Standard: IAC, unter Windows Light-Butler von loopMIDI)")
    ap.add_argument("--library", action="store_true", help="Mixxx-Bibliothek pruefen")
    ap.add_argument("--db", default=None, help="Pfad zu mixxxdb.sqlite (fuer --library; mit --monitor zeigt es das erkannte Lied)")
    a = ap.parse_args()
    if a.list:
        try:
            import mido
        except ImportError:
            sys.exit("mido fehlt:  pip install mido python-rtmidi")
        print("Eingaenge:", mido.get_input_names())
        print("Ausgaenge:", mido.get_output_names())
    elif a.library:
        library_check(os.path.expanduser(a.db) if a.db else None)
    elif a.monitor or a.send or a.raw or a.stdin:
        run(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
