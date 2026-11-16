#!/usr/bin/env python3
"""
store.py - Show-Dateiverwaltung: jede Show ist ein Ordner.

    shows/
        Konzert_01/
            show.json       Timeline, Gruppen, Szenen (alles, was zum Abspielen noetig ist)
            audio.mp3       die Musik
            fixtures.json   Stand der Geraete beim Speichern (zum Nachsehen, wenn sich der Aufbau aendert)
            patterns.json   die in dieser Show benutzten eigenen Muster
            peaks.json      Wellenform und Huellkurve (vom Browser beim Import berechnet)
            autosave.json   letzter automatischer Stand des Editors
        _papierkorb/        geloeschte Shows
        _stems/             Pegelkurven von Stimme, Bass, Kick, Snare/Hi-Hat, Sonstigem, je MP3 eine Datei (vom Mac, mac/stems/stems_show.py)
        _bibliothek.json    eigene Muster, in allen Shows verfuegbar

Geschrieben wird immer erst in eine neue Datei, dann getauscht: Ein Stromausfall zerstoert nie die letzte Fassung.
"""
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import time

from . import timeline as tl

NAME_RE = re.compile(r"^[^\W_][\w .()\-]{0,59}$", re.UNICODE)
TRASH = "_papierkorb"
STEMS_DIR = "_stems"
FP_RE = re.compile(r"^\d{1,12}:[0-9a-f]{16}$")     # Fingerabdruck einer MP3: Groesse:SHA1-Anfang (audio_fingerprint)
LIBRARY = "_bibliothek.json"
MAX_AUDIO = 400 * 1024 * 1024
STEM_CURVES = ("stimme", "bass", "kick", "hihat", "sonstiges")
STEM_RATE = 100
MIN_FREE = 200 * 1024 * 1024    # so viel bleibt auf der SD-Karte frei
CHUNK = 256 * 1024


def check_name(name):
    name = str(name or "").strip()
    if not NAME_RE.match(name) or name.endswith((".", " ")):
        raise ValueError("Name: Buchstaben, Ziffern, Leerzeichen, Punkt, Klammern, _ und - (mit Buchstabe oder Ziffer am Anfang, hoechstens 60 Zeichen)")
    return name


def write_json(path, data):
    tmp = path + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def is_mp3(head):
    """ID3-Kopf oder MPEG-Audio-Rahmen am Anfang der Datei."""
    return head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)


_BR1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)      # kbit/s, MPEG-1 Layer III
_BR2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)          # MPEG-2 und 2.5 Layer III
_SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def mp3_duration(path):
    """Laenge einer MP3 in Sekunden, ohne sie zu dekodieren: Rahmenzahl aus dem Xing/Info- oder VBRI-Kopf (VBR),
    sonst Groesse der Musikdaten durch die Bitrate (CBR). 0.0, wenn die Datei nicht zu lesen ist."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(10)
            start = 0
            if head[:3] == b"ID3" and len(head) == 10:
                start = 10 + ((head[6] & 0x7F) << 21 | (head[7] & 0x7F) << 14 | (head[8] & 0x7F) << 7 | (head[9] & 0x7F))
                if head[5] & 0x10:
                    start += 10
            f.seek(start)
            buf = f.read(64 * 1024)
            end = size
            if size >= 128:
                f.seek(size - 128)
                if f.read(3) == b"TAG":
                    end -= 128
    except OSError:
        return 0.0
    for i in range(len(buf) - 4):
        b1, b2, b3 = buf[i + 1], buf[i + 2], buf[i + 3]
        if buf[i] != 0xFF or b1 & 0xE0 != 0xE0:
            continue
        ver, layer, bri, sri = (b1 >> 3) & 3, (b1 >> 1) & 3, b2 >> 4, (b2 >> 2) & 3
        if ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
            continue                                   # kein Layer-III-Rahmen
        sr = _SR[ver][sri]
        kbps = (_BR1 if ver == 3 else _BR2)[bri]
        spf = 1152 if ver == 3 else 576
        mono = (b3 >> 6) == 3
        side = (17 if mono else 32) if ver == 3 else (9 if mono else 17)
        x = i + 4 + side
        if buf[x:x + 4] in (b"Xing", b"Info") and buf[x + 7] & 1:
            frames = int.from_bytes(buf[x + 8:x + 12], "big")
            if frames:
                return round(frames * spf / sr, 2)
        v = i + 4 + 32
        if buf[v:v + 4] == b"VBRI":
            frames = int.from_bytes(buf[v + 14:v + 18], "big")
            if frames:
                return round(frames * spf / sr, 2)
        return round(max(0, end - start - i) * 8 / (kbps * 1000.0), 2)
    return 0.0


def audio_fingerprint(path):
    """Fingerabdruck einer MP3 ohne ihre Tags: dieselbe Musik, auch wenn ein Programm die Tags aendert. Muss genau wie
    audio_fingerprint in mac/mixxx_bridge/mixxx_bridge.py rechnen."""
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


class ShowStore:
    def __init__(self, base):
        self.base = base
        os.makedirs(base, exist_ok=True)

    def dir(self, name):
        return os.path.join(self.base, check_name(name))

    def path(self, name, file):
        return os.path.join(self.dir(name), file)

    def exists(self, name):
        return os.path.isfile(self.path(name, "show.json"))

    def list(self):
        out = []
        for n in sorted(os.listdir(self.base), key=str.lower):
            p = os.path.join(self.base, n, "show.json")
            if n.startswith("_") or not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                out.append({"name": n, "error": "Datei nicht lesbar"})
                continue
            a = os.path.join(self.base, n, "audio.mp3")
            has = os.path.isfile(a)
            try:
                stems = has and self.has_stems(self._audio_fp(n))   # Seite Shows: Kurven vorhanden?
            except (OSError, ValueError):
                stems = False
            out.append({"name": n, "duration": d.get("duration", 0), "bpm": d.get("bpm", 0), "has_audio": has,
                        "tracks": len(d.get("tracks", [])), "mtime": int(os.path.getmtime(p)), "stems": bool(stems)})
        return out

    def mixxx_index(self, cache=None):
        """Was der Showmanager zum Finden einer Show braucht: [{name, fp, title, dur, duration, on, mtime}]. cache spart das Neuberechnen."""
        cache = {} if cache is None else cache
        out = []
        for n in os.listdir(self.base):
            p = os.path.join(self.base, n, "show.json")
            if n.startswith("_") or not os.path.isfile(p):
                continue
            a = os.path.join(self.base, n, "audio.mp3")
            try:
                stamp = (os.path.getmtime(p), os.path.getmtime(a) if os.path.isfile(a) else 0)
                e = cache.get(n)
                if e is None or e["stamp"] != stamp:
                    with open(p, encoding="utf-8") as f:
                        d = json.load(f)
                    m = d.get("mixxx") if isinstance(d.get("mixxx"), dict) else {}
                    e = {"name": n, "stamp": stamp, "mtime": stamp[0], "fp": audio_fingerprint(a) if stamp[1] else "",
                         "title": str(m.get("title") or ""), "dur": float(m.get("dur") or 0), "on": m.get("on", True) is not False,
                         "duration": float(d.get("duration") or 0),
                         "lyr": bool(isinstance(d.get("lyrics"), dict) and (d["lyrics"].get("lines") or d["lyrics"].get("plain")))}
                out.append(e)
            except (OSError, ValueError, TypeError):
                continue
        return out

    def create(self, name):
        name = check_name(name)
        if os.path.exists(self.dir(name)):
            raise ValueError("Diese Show gibt es schon")
        os.makedirs(self.dir(name))
        doc = tl.new_show(name)
        write_json(self.path(name, "show.json"), doc)
        return doc

    def load(self, name):
        if not self.exists(name):
            raise ValueError("Diese Show gibt es nicht")
        with open(self.path(name, "show.json"), encoding="utf-8") as f:
            doc = json.load(f)
        doc = tl.normalize(doc)
        doc["name"] = check_name(name)
        return doc

    def save(self, name, doc, fixtures=None, patterns=None):
        """Show speichern. Die vorige Fassung bleibt als show.json.alt liegen."""
        if not self.exists(name):
            raise ValueError("Diese Show gibt es nicht")
        d = tl.normalize(doc)
        d["name"] = check_name(name)
        p = self.path(name, "show.json")
        shutil.copy2(p, p + ".alt")
        write_json(p, d)
        if fixtures is not None:
            write_json(self.path(name, "fixtures.json"), fixtures)
        if patterns is not None:
            write_json(self.path(name, "patterns.json"), patterns)
        try:
            os.unlink(self.path(name, "autosave.json"))
        except OSError:
            pass
        return d

    def save_marks(self, name, marks):
        """Nur die Abschnitte und Cues in die Datei schreiben, ungespeicherte Aenderungen im Editor bleiben davon unberuehrt."""
        d = self.load(name)
        d["marks"] = tl.clean_marks(marks)
        write_json(self.path(name, "show.json"), d)
        return d["marks"]

    def save_lyrics(self, name, lyrics):
        """Nur den Liedtext schreiben, ungespeicherte Aenderungen im Editor bleiben unberuehrt. None loescht ihn."""
        d = self.load(name)
        if lyrics is None:
            d.pop("lyrics", None)
        else:
            d["lyrics"] = tl.clean_lyrics(lyrics)
        write_json(self.path(name, "show.json"), d)
        return d.get("lyrics")

    def autosave(self, name, doc):
        if not self.exists(name):
            raise ValueError("Diese Show gibt es nicht")
        write_json(self.path(name, "autosave.json"), {"t": time.time(), "doc": tl.normalize(doc)})

    def load_autosave(self, name):
        """Neuerer automatischer Stand, falls vorhanden, sonst None."""
        p = self.path(name, "autosave.json")
        if not os.path.isfile(p):
            return None
        try:
            if os.path.getmtime(p) <= os.path.getmtime(self.path(name, "show.json")):
                return None
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def copy(self, name, new):
        if not self.exists(name):
            raise ValueError("Diese Show gibt es nicht")
        new = check_name(new)
        if os.path.exists(self.dir(new)):
            raise ValueError("Diese Show gibt es schon")
        shutil.copytree(self.dir(name), self.dir(new))
        doc = self.load(new)
        write_json(self.path(new, "show.json"), doc)
        return doc

    def rename(self, name, new):
        if not self.exists(name):
            raise ValueError("Diese Show gibt es nicht")
        new = check_name(new)
        if os.path.exists(self.dir(new)):
            raise ValueError("Diese Show gibt es schon")
        os.rename(self.dir(name), self.dir(new))
        doc = self.load(new)
        write_json(self.path(new, "show.json"), doc)
        return doc

    def delete(self, name):
        """In den Papierkorb, nicht endgueltig."""
        if not self.exists(name):
            raise ValueError("Diese Show gibt es nicht")
        trash = os.path.join(self.base, TRASH)
        os.makedirs(trash, exist_ok=True)
        os.rename(self.dir(name), os.path.join(trash, f"{check_name(name)}_{time.strftime('%Y%m%d-%H%M%S')}"))

    # ---- Papierkorb (Seite Shows, Wunsch von Markus 06.11.2026) -------------------------------------------
    TRASH_RE = re.compile(r"^(.+)_(\d{8})-(\d{6})$")

    def _trash_dir(self, entry):
        """Ordner eines Eintrags im Papierkorb; nur direkte Eintraege, kein Pfad von aussen."""
        entry = str(entry or "")
        if not self.TRASH_RE.match(entry) or "/" in entry or "\\" in entry or entry.startswith("."):
            raise ValueError("Diesen Eintrag gibt es im Papierkorb nicht")
        p = os.path.join(self.base, TRASH, entry)
        if not os.path.isfile(os.path.join(p, "show.json")):
            raise ValueError("Diesen Eintrag gibt es im Papierkorb nicht")
        return p

    def trash_list(self):
        """Geloeschte Shows, neueste zuerst: [{entry, name, deleted (JJJJ-MM-TT HH:MM), tracks, has_audio}]."""
        base = os.path.join(self.base, TRASH)
        out = []
        try:
            names = os.listdir(base)
        except OSError:
            return out
        for n in names:
            m = self.TRASH_RE.match(n)
            p = os.path.join(base, n, "show.json")
            if not m or not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                d = {}
            dt, tm = m.group(2), m.group(3)
            out.append({"entry": n, "name": m.group(1), "deleted": f"{dt[:4]}-{dt[4:6]}-{dt[6:]} {tm[:2]}:{tm[2:4]}",
                        "tracks": len(d.get("tracks") or []), "has_audio": os.path.isfile(os.path.join(base, n, "audio.mp3"))})
        out.sort(key=lambda x: x["entry"][-15:], reverse=True)
        return out

    def trash_restore(self, entry):
        """Zuruecklegen. Gibt es den Namen schon, heisst sie "Name (zurueck)". Rueckgabe: neuer Name."""
        src = self._trash_dir(entry)
        name = self.TRASH_RE.match(entry).group(1)
        new = name
        for i in range(1, 100):
            if not os.path.exists(self.dir(new)):
                break
            new = (name[:45] + (" (zurueck)" if i == 1 else f" (zurueck {i})")).strip()
        else:
            raise ValueError("Kein freier Name zum Zuruecklegen")
        os.rename(src, self.dir(new))
        if new != name:
            p = self.path(new, "show.json")
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            d["name"] = new
            write_json(p, d)
        return new

    def trash_delete(self, entry=None):
        """Endgueltig loeschen: ein Eintrag oder (entry=None) der ganze Papierkorb. Rueckgabe: Anzahl."""
        if entry is not None:
            shutil.rmtree(self._trash_dir(entry))
            return 1
        n = 0
        for x in self.trash_list():
            shutil.rmtree(os.path.join(self.base, TRASH, x["entry"]))
            n += 1
        return n

    # ---- Audio ---------------------------------------------------------------------------------------
    def save_audio(self, name, stream, length):
        """MP3 aus dem Datenstrom speichern (mit Pruefung von Groesse, Art und freiem Platz)."""
        if not self.exists(name):
            raise ValueError("Diese Show gibt es nicht")
        if not 0 < length <= MAX_AUDIO:
            raise ValueError(f"Datei zu gross oder leer (hoechstens {MAX_AUDIO // (1024 * 1024)} MB)")
        if shutil.disk_usage(self.base).free - length < MIN_FREE:
            raise ValueError("Zu wenig Platz auf der SD-Karte")
        dst = self.path(name, "audio.mp3")
        tmp = dst + ".neu"
        left = length
        first = True
        try:
            with open(tmp, "wb") as f:
                while left > 0:
                    b = stream.read(min(CHUNK, left))
                    if not b:
                        raise ValueError("Verbindung beim Hochladen abgebrochen")
                    if first and not is_mp3(b[:4]):
                        raise ValueError("Das ist keine MP3-Datei")
                    first = False
                    f.write(b)
                    left -= len(b)
            os.replace(tmp, dst)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return length

    def save_peaks(self, name, data):
        write_json(self.path(name, "peaks.json"), data)

    def load_peaks(self, name):
        p = self.path(name, "peaks.json")
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    # ---- Pegelkurven der getrennten Spuren --------------------------------------------------------------
    def _stems_path(self, fp):
        return os.path.join(self.base, STEMS_DIR, fp.replace(":", "_") + ".json")

    _fp_cache = {}                                     # Pfad -> (Groesse, Zeit, Fingerabdruck): Seite Statistik fragt alle 10 s

    def _audio_fp(self, name):
        audio = self.path(name, "audio.mp3")
        try:
            stt = os.stat(audio)
        except OSError:
            return ""
        c = self._fp_cache.get(audio)
        if c and c[0] == stt.st_size and c[1] == stt.st_mtime:
            return c[2]
        fp = audio_fingerprint(audio)
        self._fp_cache[audio] = (stt.st_size, stt.st_mtime, fp)
        return fp

    def _read_stems(self, fp):
        try:
            with open(self._stems_path(fp), encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else None
        except (OSError, ValueError):
            return None

    def stems_state(self, name):
        """Stand der Kurven einer Show. Sie haengen an der MP3, nicht an der Show: Shows mit derselben MP3 teilen sich eine Datei."""
        fp = self._audio_fp(name)
        d = self._read_stems(fp) if fp else None
        out = {"audio": bool(fp), "fp": fp, "current": d is not None,
               "audio_s": mp3_duration(self.path(name, "audio.mp3")) if fp else 0.0}   # Laenge der MP3 (Helfer: nur bis 6 min)
        if d:
            out.update({k: d.get(k) for k in ("created", "model", "offset_ms", "corr", "duration")})
        return out

    def load_stems(self, name):
        """Die Kurven zur MP3 dieser Show, oder None."""
        fp = self._audio_fp(name)
        return self._read_stems(fp) if fp else None

    def stems_summary(self):
        """Fuer die Seite Statistik: verschiedene MP3s in den Shows und wie viele davon Kurven haben. Kopien zaehlen einmal."""
        fps = set()
        for s in self.list():
            if s.get("has_audio") and not s.get("error"):
                try:
                    fps.add(self._audio_fp(s["name"]))
                except (OSError, ValueError):
                    pass
        fps.discard("")
        return {"mp3": len(fps), "done": sum(1 for fp in fps if os.path.isfile(self._stems_path(fp)))}

    def save_stems(self, name, data):
        """Kommt ueber das Netz: nur bekannte Felder, und nur zur MP3, die gerade in der Show liegt."""
        fp = self._audio_fp(name)
        if not fp or not isinstance(data, dict) or data.get("fp") != fp:
            raise ValueError("Kurven gehoeren nicht zur MP3 dieser Show")
        self.save_stems_fp(fp, data)

    def has_stems(self, fp):
        return bool(FP_RE.match(fp or "")) and os.path.isfile(self._stems_path(fp))

    def stems_fps(self):
        """Fingerabdruecke aller MP3s mit Kurven (Vorab-Lauf, Seite Statistik)."""
        try:
            names = os.listdir(os.path.join(self.base, STEMS_DIR))
        except OSError:
            return set()
        return {n[:-5].replace("_", ":", 1) for n in names if n.endswith(".json")}

    def stems_files(self):
        """Fuer die Sicherung auf den Stick am Mac: [[Fingerabdruck, Groesse in Byte]] aller Kurven-Dateien."""
        out = []
        for fp in sorted(self.stems_fps()):
            if FP_RE.match(fp):
                try:
                    out.append([fp, os.path.getsize(self._stems_path(fp))])
                except OSError:
                    pass
        return out

    def stems_raw(self, fp):
        """Inhalt einer Kurven-Datei (Bytes) oder None. Nur gueltige Fingerabdruecke, kein Pfad von aussen."""
        if not FP_RE.match(fp or ""):
            return None
        try:
            with open(self._stems_path(fp), "rb") as f:
                return f.read()
        except OSError:
            return None

    def save_stems_fp(self, fp, data):
        """Kurven zu einer MP3 ablegen, auch ohne Show (Vorab-Lauf ueber die Bibliothek). Kommt ueber das Netz: nur bekannte
        Felder, der Fingerabdruck muss passen und darf keinen Pfad bilden."""
        if not FP_RE.match(fp or ""):
            raise ValueError("Kurven: Fingerabdruck unbrauchbar")
        if not isinstance(data, dict) or data.get("v") != 1 or data.get("rate") != STEM_RATE:
            raise ValueError("Kurven: falsches Format")
        if data.get("fp") != fp:
            raise ValueError("Kurven gehoeren zu einer anderen MP3")
        curves = data.get("curves")
        if not isinstance(curves, dict) or set(curves) != set(STEM_CURVES):
            raise ValueError("Kurven: falsche Namen")
        sizes = set()
        for text in curves.values():
            try:
                sizes.add(len(base64.b64decode(text, validate=True)))
            except (TypeError, ValueError, binascii.Error):
                raise ValueError("Kurven: unlesbar")
        duration = float(data.get("duration", 0))
        if len(sizes) != 1 or sizes == {0} or abs(sizes.pop() - duration * STEM_RATE) > STEM_RATE:
            raise ValueError("Kurven: Laenge passt nicht")
        clean = {k: data.get(k) for k in ("v", "rate", "db_min", "duration", "offset_ms", "corr", "fp", "model", "created")}
        clean["curves"] = {k: curves[k] for k in STEM_CURVES}
        os.makedirs(os.path.join(self.base, STEMS_DIR), exist_ok=True)
        write_json(self._stems_path(fp), clean)

    # ---- Bibliothek: eigene Muster --------------------------------------------------------------------
    def library(self):
        p = os.path.join(self.base, LIBRARY)
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):             # fremder Inhalt (z. B. eine Liste): keine Muster, aber kein Absturz des Editors
                return {"patterns": []}
            return {"patterns": [x for x in d.get("patterns", []) if isinstance(x, dict)]}
        except (OSError, ValueError, AttributeError):
            return {"patterns": []}

    def library_save(self, patterns):
        write_json(os.path.join(self.base, LIBRARY), {"patterns": patterns})
