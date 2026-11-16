#!/usr/bin/env python3
"""
mixxx_link.py - Empfaenger auf dem Raspberry Pi fuer die Mixxx-Bruecke (laeuft im Lichtsteuerungs-Dienst).

Der Mac schickt per UDP (Port 9020) zwei Arten von Nachrichten:
  * Deck-Zustand (ca. 10 pro Sekunde und Deck): Position, Tempo, Pitch, Fader ...
  * Plan (beim Laden eines Liedes und alle paar Sekunden): Breaks, Aufbauten, Drops mit Zeitpunkt im Lied

Daraus berechnet status() fuer das Deck, das gerade hoerbar laeuft:
  * die aktuelle Stelle im Lied (mit Pitch und Sync),
  * wie viele Sekunden es bis zum naechsten Aufbau, zur Stille und zum Drop sind,
  * in welcher Phase das Lied laut Plan gerade ist ("want": normal, build, gap, break, drop).
Die Show nutzt "want" nur, wenn die Einstellung "Vorhersage fuers Licht nutzen" eingeschaltet ist.
"""
import hashlib
import json
import os
import socket
import threading
import time

TYPES = {"b": "after_break", "l": "lift", "i": "intro_end"}
SECTIONS = ("intro", "vers", "main", "break", "outro")   # Abschnitte eines Liedes aus der Analyse am Mac


LIB_FIELDS = ("title", "dur", "artist", "name", "bpm", "key", "kid", "genre", "lvl", "file", "cues", "ana", "path", "kbps", "bad", "est", "elv", "kest", "src", "best", "crates", "lists", "year", "album", "track", "grp", "added", "lufs", "tp", "rgt", "plays", "lastp", "rating")


def _merge_library(parts_by_i, n, saved):
    """Bibliothek aus den Stuecken der Bruecke und der Ablage am Pi (ohne Sperre aufrufen)."""
    parts = [x for i in sorted(parts_by_i) for x in parts_by_i[i]]
    if n and len(parts_by_i) >= n:
        return parts
    if not saved:
        return parts
    if not parts:
        return list(saved)
    # Zuordnen ueber den Pfad der Datei: dasselbe Lied kann zweimal mit fast gleicher Laenge in verschiedenen
    # Ordnern liegen (Abba - Dancing Queen, 230,5 s und 230,4 s). Nur Eintraege ohne Pfad (aeltere Bruecke)
    # nach Titel und Laenge auf 0,1 s, jedes neue Lied hoechstens einmal.
    tl = lambda x: (x["title"], round(x["dur"], 1))      # noqa: E731
    new = {}
    by_tl = {}
    for x in parts:
        k = x.get("path") or tl(x)
        new[k] = x
        by_tl.setdefault(tl(x), []).append(k)
    out = []
    for x in saved:
        if x.get("path"):
            out.append(new.pop(x["path"], x))
            continue
        k = next((k for k in by_tl.get(tl(x), ()) if k in new), None)
        out.append(new.pop(k) if k is not None else x)
    return out + list(new.values())


def lib_digest(lib):
    """Pruefsumme der Bibliothek, Lied fuer Lied: json.dumps ueber alle 9000 Lieder auf einmal haelt in Python alle anderen
    Faeden an (am Pi rund 200 ms), die Show-Schleife verpasste Bilder und der Ton setzte aus (Fehlerbericht 06.11.2026)."""
    h = hashlib.sha1()
    for x in lib:
        h.update(json.dumps(list(x.values()), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def full_path(p):
    """Pfad am Mac ganz oder gar nicht: ein abgeschnittener zeigt auf keine Datei (Typ "MP", nicht abspielbar, 06.11.2026)."""
    p = str(p or "")
    return p if len(p) <= 1000 else ""


# Auto-DJ im Browser als zweite Quelle neben Mixxx (Wunsch von Markus, 08.11.2026): er meldet seine zwei Decks wie die Bruecke,
# nur mit eigenen Nummern. Gilt dann das lauteste Deck, steht im Panel "Auto-DJ" statt "Mixxx". Plan = Analyse vom Mac (/marks).
AUTODJ_DECKS = (11, 12)
DECK_NUM = ("pp", "du", "pl", "tl", "vo", "rr", "bp", "bd", "fb", "fk", "k")
LIB_TYPES = ("lib", "genres", "stats", "libhash")                    # Nachrichten zur Bibliothek, auch vom Light-Butler Helfer ohne Mixxx


def lib_item(x):
    """Ein Lied aus einem Bibliotheks-Stueck der Bruecke (Liste, siehe mixxx_bridge.library_chunks) als Dict; None = unbrauchbar.
    Aeltere Bruecken schicken nur [Titel, Laenge]: dann bleiben die anderen Felder leer."""
    if not isinstance(x, list) or len(x) < 2 or not isinstance(x[1], (int, float)) or not str(x[0]):
        return None
    x = list(x) + [None] * (len(LIB_FIELDS) - len(x))

    def num(v, k=1):
        try:
            return round(float(v), k) if k else int(v)
        except (TypeError, ValueError):
            return 0
    artist, name = str(x[2] or "")[:60], str(x[3] or "")[:80]
    if not artist and not name:                                   # alte Bruecke: "Interpret - Titel" selbst trennen
        artist, _, name = str(x[0])[:120].partition(" - ")
        if not name:
            artist, name = "", artist
    return {"title": str(x[0])[:120], "dur": float(x[1]), "artist": artist[:60], "name": name[:80],
            "bpm": num(x[4]), "key": str(x[5] or "")[:6], "kid": max(0, min(24, num(x[6], 0))), "genre": str(x[7] or "")[:40],
            "lvl": max(0, min(10, num(x[8], 0))), "file": str(x[9] or "")[:200], "cues": max(0, num(x[10], 0)), "ana": 1 if x[11] else 0,
            "path": full_path(x[12]), "kbps": max(0, min(9999, num(x[13], 0))),
            "bad": 1 if x[14] else 0,              # die Analyse am Mac konnte die Datei nicht lesen (Statistik: "nicht lesbar")
            "est": 1 if x[15] and x[8] else 0,   # Energiestufe geschaetzt (energy_level.py am Mac), nicht aus dem Tag
            "elv": max(0, min(9, num(x[16], 0))),   # Schaetzung der Energie, auch neben einer Stufe im Tag (Musik-Datenbank: vergleichen)
            "kest": 2 if x[17] == 2 and not x[6] else (1 if x[17] and x[6] else 0),   # Tonart: 1 geschaetzt (key_estimate.py am Mac), 2 nicht eindeutig bestimmbar
            "src": 1 if x[18] else 0,               # 1 = aus dem Musikordner (folder_lib.py am Mac), nicht in der Mixxx-Bibliothek
            "best": x[19] if x[19] in (1, 2) else 0,   # BPM: 1 geschaetzt (essentia am Mac), 2 nicht bestimmbar
            "crates": _names(x[20]), "lists": _names(x[21]),
            "year": x[22] if isinstance(x[22], int) and 1900 <= x[22] <= 2099 else 0,
            "album": str(x[23])[:60] if isinstance(x[23], str) else "",
            "track": str(x[24])[:7] if isinstance(x[24], str) else "",
            "grp": str(x[25])[:60] if isinstance(x[25], str) else "",
            "added": int(x[26]) if isinstance(x[26], (int, float)) and not isinstance(x[26], bool) and 0 < x[26] < 4e9 else 0,
            # Lautheit (loudness.py am Mac, 11.11.2026): LUFS (0 = nicht gemessen), Spitze dBTP, ReplayGain in der Datei (1 fremd, 2 von uns)
            "lufs": _fnum(x[27], -70.0, 5.0), "tp": _fnum(x[28], -70.0, 20.0) if _fnum(x[27], -70.0, 5.0) else 0.0,
            "rgt": x[29] if x[29] in (1, 2) else 0,
            # wie oft und wann zuletzt in Mixxx gespielt (Mixxx zaehlt selbst, 12.11.2026)
            "plays": x[30] if isinstance(x[30], int) and not isinstance(x[30], bool) and 0 <= x[30] < 100000 else 0,
            "lastp": int(x[31]) if isinstance(x[31], (int, float)) and not isinstance(x[31], bool) and 0 < x[31] < 4e9 else 0,
            "rating": x[32] if isinstance(x[32], int) and not isinstance(x[32], bool) and 0 <= x[32] <= 5 else 0}   # Sterne aus Mixxx (14.11.2026)


def _fnum(v, lo, hi):
    """Zahl mit einer Nachkommastelle zwischen lo und hi (ausserhalb, kein Wert: 0)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo <= v <= hi:
        return 0.0
    return round(float(v), 1)   # hinzugefuegt (11.11.2026)   # Gruppe, TIT1 ("Après-Ski", 10.11.2026)   # Track "4" oder "4/9" (09.11.2026)   # Album (09.11.2026: Spalte und Suche in der Musik-Datenbank)   # Erscheinungsjahr (Mixxx), 0 = unbekannt   # Plattenkisten und Wiedergabelisten aus Mixxx (08.11.2026)


def _names(v):
    """Namensliste von der Bruecke pruefen: nur Texte, hoechstens 12, je 40 Zeichen."""
    return [str(n)[:40] for n in v if isinstance(n, str) and n.strip()][:12] if isinstance(v, list) else []


def _f(v):
    """Zahl aus ungeprueften Daten (Auto-DJ im Browser), sonst 0."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v and abs(v) < 1e7 else 0.0


def audible(d):
    """Wie laut ein Deck im Mix ist (0..1): Kanalfader mal Crossfader-Seite, nur wenn es spielt."""
    if not d.get("pl") or not d.get("tl"):
        return 0.0
    w = d.get("vo", 1.0)
    cf, side = d.get("cf", 0.0), d.get("or", 1)
    if side == 0:
        w *= 1.0 if cf <= 0 else max(0.0, 1.0 - cf)
    elif side == 2:
        w *= 1.0 if cf >= 0 else max(0.0, 1.0 + cf)
    return max(0.0, min(1.0, w))


def clean_stats(m):
    """Statistik von der Bruecke pruefen: nur Zahlen und kurze Texte, begrenzte Laengen."""
    def num(x):
        return int(x) if isinstance(x, (int, float)) and x >= 0 else 0

    def nums(x, k):
        return [num(v) for v in x[:k]] if isinstance(x, list) else []
    ft = m.get("ft") if isinstance(m.get("ft"), dict) else {}
    g = m.get("g") if isinstance(m.get("g"), list) else []
    bg = m.get("bg") if isinstance(m.get("bg"), dict) else None
    return {"bg": {"todo": num(bg.get("todo")), "done": num(bg.get("done")), "fail": num(bg.get("fail")),
                   "run": bool(bg.get("run")), "pause": bool(bg.get("pause"))} if bg else None,
            "n": num(m.get("n")), "a": num(m.get("a")), "cu": num(m.get("cu")),
            "h": round(float(m["h"]), 1) if isinstance(m.get("h"), (int, float)) else 0.0,
            "e": nums(m.get("e"), 10), "bpm": nums(m.get("bpm"), 14),
            "ft": {str(k)[:6]: num(v) for k, v in list(ft.items())[:8]},
            "g": [[str(x[0])[:40], num(x[1]), num(x[2])] for x in g[:200]
                  if isinstance(x, list) and len(x) == 3 and all(isinstance(v, (int, float)) for v in x[1:])]}


def clean_sections(plan, shift=0.0):
    """Abschnitte aus dem Plan pruefen: [[Art, Start, Ende], ...], unbekannte Arten und Unsinn verwerfen."""
    se = plan.get("se")
    out = []
    for s in se[:32] if isinstance(se, list) else []:
        if (isinstance(s, list) and len(s) == 3 and s[0] in SECTIONS
                and all(isinstance(v, (int, float)) for v in s[1:]) and s[2] > s[1]):
            out.append([s[0], round(float(s[1]) + shift, 1), round(float(s[2]) + shift, 1)])
    return out


def snap_drops(plan, window):
    """Drops der Analyse auf den naechsten Hotcue (taktgenau) ruecken, wenn er hoechstens window Sekunden
    entfernt ist. Liefert {alte Zeit: neue Zeit}; ohne Hotcues oder mit window 0 leer."""
    cues = [float(c) for c in plan.get("cu") or [] if isinstance(c, (int, float))]
    if window <= 0 or not cues:
        return {}
    out = {}
    for e in plan.get("ev", []):
        if e[0] == "drop":
            t = float(e[1])
            c = min(cues, key=lambda x: abs(x - t))
            if abs(c - t) <= window:
                out[t] = c
    return out


def _moved(moved, t):
    """Ende eines Aufbaus oder einer Stille mit dem Drop mitruecken (Ende liegt hoechstens 0,3 s neben dem Drop)."""
    for old, new in moved.items():
        if abs(old - t) <= 0.3:
            return new
    return t


class MixxxLink:
    def __init__(self, port=9020, bind="0.0.0.0"):
        self.port, self.bind = port, bind
        self.decks = {}                 # Deck-Nr -> {"d": Zustand, "t": Empfangszeit}
        self.plans = {}                 # Deck-Nr -> {"p": Plan, "t": Empfangszeit}
        self.lib_parts, self.lib_n = {}, 0   # Bibliothek fuer Showmanager und Musik-Datenbank (Stueck-Nr -> Liste von Dicts)
        self.lib_round, self.lib_round_done = set(), False   # Stuecke des laufenden Durchgangs der Bruecke
        self.lib_ver, self._full_cache = 0, (None, None)     # Stand der Bibliothek: library_full rechnet nur bei Aenderung neu
        self.lib_file, self.lib_hash = None, ""   # Ablage der kompletten Bibliothek am Pi (persist), damit sie ohne Mac da ist
        self.lib_saved = []             # Bibliothek aus der Datei, solange die vom Mac noch nicht ganz da ist
        # Stuecke, die beim Neu-Sammeln verworfen wurden (Fehlerbericht 11.11.2026: heute importierte Lieder verschwanden immer
        # wieder aus der Musik-Datenbank): library_full mischt sie in die Ablage, bis die neue Fassung komplett ist
        self.lib_carry = []
        # Pruefsumme der Bruecke (Wunsch 07.11.2026: nicht alle 10 Minuten alles schicken, wenn sich nichts geaendert hat):
        # lib_have_h = Fassung, die der Pi komplett hat (gemerkt neben der Ablage), lib_bridge_h = aktuelle Fassung am Mac
        self.lib_round_h, self.lib_have_h, self.lib_bridge_h = "", "", ""
        self.lib_delta = None           # [Anzahl, {erhaltene Stuecke}]: nur Geaendertes zur Fassung lib_have_h kommt
        self.lib_last_t = 0.0           # wann das letzte Stueck kam (stockt die Uebertragung, sind Teile verloren)
        self.mac_ip, self.music_port = "", 0   # Absender der Bruecke und Port ihres Vorhoer-Servers (Seite /musik)
        self.infos = {}                 # Deck-Nr -> Text, warum es (noch) keinen Plan gibt (von der Bruecke)
        self.genres = []                # [Genre, Anzahl Lieder] aus der Mixxx-Bibliothek (fuer die Genre-Stile im Panel)
        self.stats, self.stats_t = None, 0.0   # Statistik der Bibliothek von der Bruecke (Seite Statistik), Empfangszeit
        self.last_rx = 0.0
        self.lib_rx = 0.0               # letzte Nachricht zur Bibliothek (auch vom Helfer ohne Mixxx: Vorhoeren, Doppelte ...)
        self.count = 0
        self.lock = threading.Lock()
        self.sock = None
        self.error = ""
        self._run = False

    # ---- Netzwerk ------------------------------------------------------------------------------------------------
    def start(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.bind, self.port))
            self.sock.settimeout(0.5)
        except OSError as e:
            self.error = f"Port {self.port} nicht verfuegbar: {e}"
            self.sock = None
            return False
        self._run = True
        threading.Thread(target=self._rx, daemon=True).start()
        return True

    def stop(self):
        self._run = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def _rx(self):
        while self._run:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                self.feed(json.loads(data.decode("ascii", "replace")), addr=addr[0])
            except ValueError:
                pass

    def library(self):
        """Titel aus Mixxx fuer den Showmanager: [(Titel, Laenge)], sortiert wie von der Bruecke geschickt."""
        return [(x["title"], x["dur"]) for x in self.library_full()]

    def library_full(self):
        """Alle Lieder der Mixxx-Bibliothek mit allen Feldern (Musik-Datenbank im Panel), sortiert nach Interpret und Titel.
        Solange der Mac sie noch nicht ganz geschickt hat (sie kommt in Stuecken, alle 10 Minuten): die Ablage am Pi, darin die
        schon angekommenen Lieder mit ihren neuen Feldern, fehlende Lieder dahinter.
        Die Sperre gilt nur fuer eine Momentaufnahme: die Show-Schleife fragt bei jedem Bild status() und wartete sonst, bis
        9000 Lieder gemischt sind (bis 140 ms je Bild, Fehlersuche 06.11.2026). Ergebnis zwischengespeichert bis zum naechsten
        Stueck von der Bruecke; nur lesen, nicht veraendern."""
        with self.lock:
            ver = self.lib_ver
            if self._full_cache[0] == ver:
                return self._full_cache[1]
            parts_by_i = dict(self.lib_parts)
            n, saved, carry = self.lib_n, self.lib_saved, list(self.lib_carry)
        if carry and n and len(parts_by_i) >= n:
            with self.lock:                                    # neue Fassung komplett: die verworfenen Stuecke braucht es nicht mehr
                if self.lib_carry[:len(carry)] == carry:
                    self.lib_carry = self.lib_carry[len(carry):]
        elif carry:
            base = saved
            for c_parts, c_n in carry:                         # verworfene Stuecke der vorigen Fassungen, aelteste zuerst
                base = _merge_library(c_parts, c_n, base)
            with self.lock:
                if self.lib_saved is saved and self.lib_carry[:len(carry)] == carry:
                    self.lib_saved, self.lib_carry = base, self.lib_carry[len(carry):]   # nur im Speicher, die Datei bleibt
            saved = base
        out = _merge_library(parts_by_i, n, saved)
        # die Bruecke verteilt die Lieder nach dem Pfad auf feste Stuecke (nur Geaendertes schicken): hier nach Interpret und Titel
        out.sort(key=lambda x: (str(x.get("artist") or "").lower(), str(x.get("name") or "").lower(), str(x.get("path") or "")))
        with self.lock:
            if self.lib_ver == ver:
                self._full_cache = (ver, out)
        return out

    def library_complete(self):
        """True, sobald alle Stuecke der Bibliothek vom Mac da sind."""
        with self.lock:
            return (bool(self.lib_n) and len(self.lib_parts) >= self.lib_n) or self._synced()

    def library_missing(self, limit=600):
        """(Fassung, [fehlende Stuecke]) des laufenden Durchgangs: die Bruecke schickt dann nur diese nach (WLAN verliert
        von 2500 Paketen oft ein paar, Fehlerbericht 07.11.2026: "haengt bei 98 %")."""
        with self.lock:
            if not self.lib_round_h or not self.lib_n or len(self.lib_parts) >= self.lib_n:
                return self.lib_round_h, []
            return self.lib_round_h, [i for i in range(self.lib_n) if i not in self.lib_parts][:limit]

    def library_missing_count(self):
        """Zahl aller fehlenden Stuecke des laufenden Durchgangs (library_missing meldet hoechstens 600)."""
        with self.lock:
            if not self.lib_round_h or not self.lib_n:
                return 0
            return max(0, self.lib_n - len(self.lib_parts))

    def library_delta_ok(self):
        """Hat der Pi alle Stuecke seiner Fassung im Speicher? Dann reicht es, wenn die Bruecke nur Geaendertes schickt
        (nach einem Neustart nicht: die Ablage kennt die Stuecke nicht)."""
        with self.lock:
            return (bool(self.lib_n) and bool(self.lib_have_h) and len(self.lib_parts) >= self.lib_n
                    and (self.lib_round_h == self.lib_have_h or self.lib_delta is not None))   # auch mitten in einer Teil-Uebertragung

    def _synced(self):
        """Die Ablage am Pi ist genau die Fassung, die der Mac gerade hat (nichts zu uebertragen). Mit der Sperre aufrufen."""
        return bool(self.lib_have_h) and self.lib_have_h == self.lib_bridge_h and bool(self.lib_saved)

    def mac_alive(self, max_age=90.0):
        """Meldet sich am Mac die Mixxx-Bruecke oder der Helfer? Fuer die Adresse des Vorhoerens (Musik-Datenbank, Doppelte,
        Tag-Vorschlaege). Der Helfer schickt nur Nachrichten zur Bibliothek (Pruefsumme alle 30 s), Fehlerbericht 07.11.2026."""
        return time.time() - self.lib_rx < max_age

    def library_progress(self):
        """[angekommene Stuecke, alle Stuecke, verloren] der Bibliothek vom Mac (Fortschrittsbalken der Musik-Datenbank, Wunsch
        07.11.2026). verloren = 1: das letzte Stueck dieses Durchgangs ist da, andere fehlen (im WLAN verloren, kommen mit dem
        naechsten Durchgang)."""
        with self.lock:
            if self._synced():
                return [self.lib_n or 1, self.lib_n or 1, 0]
            have, n = min(len(self.lib_parts), self.lib_n), self.lib_n
            stuck = time.time() - self.lib_last_t > 15.0 if self.lib_last_t else False
            return [have, n, int(bool(n) and have < n and ((n - 1) in self.lib_round or stuck))]

    def persist(self, path):
        """Bibliothek in dieser Datei merken (JSON) und beim Start daraus laden. Geschrieben wird nur, wenn sie sich geaendert hat."""
        self.lib_file = path
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):           # fremde Datei (kein Bibliotheks-Abbild): nie ueberschreiben
                self.lib_file = None
                return
            saved = [x for x in (lib_item(x) for x in data) if x]
            h = lib_digest(saved)                            # ohne Sperre: die Show-Schleife wartet nie darauf
            try:
                with open(path + ".hash", encoding="utf-8") as f:
                    self.lib_have_h = f.read().strip()[:64]     # Fassung der Bruecke, zu der diese Ablage gehoert
            except OSError:
                pass
            with self.lock:
                self.lib_saved, self.lib_hash = saved, h
                self.lib_ver += 1
        except (OSError, ValueError, TypeError):
            pass

    def _save_lib(self):
        """Vollstaendige Bibliothek in die Ablage schreiben (nur bei Aenderung). OHNE die Sperre aufrufen: nur die
        Momentaufnahme braucht sie, Pruefsumme und Schreiben laufen ohne (die Show-Schleife wartet sonst).
        Danach die Fassung der Bruecke daneben merken (.hash): sie schickt die Liste nur, wenn ihre anders ist."""
        if not self.lib_file:
            return
        with self.lock:
            parts_by_i = dict(self.lib_parts)
            rh = self.lib_round_h
        lib = [x for i in sorted(parts_by_i) for x in parts_by_i[i]]
        h = lib_digest(lib)
        if h != self.lib_hash:
            try:
                tmp = self.lib_file + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:            # Lied fuer Lied: dazwischen kommt die Show-Schleife dran
                    f.write("[")
                    for k, x in enumerate(lib):
                        f.write(("," if k else "") + json.dumps(list(x.values()), ensure_ascii=False, separators=(",", ":")))
                    f.write("]")
                os.replace(tmp, self.lib_file)
                with self.lock:
                    self.lib_hash, self.lib_saved = h, lib
                    self.lib_ver += 1
            except OSError:
                return                                             # Ablage nicht geschrieben: Fassung nicht als vorhanden merken
        if rh and rh != self.lib_have_h:                           # erst nach der Ablage: beide passen immer zusammen
            try:
                with open(self.lib_file + ".hash.tmp", "w", encoding="utf-8") as f:
                    f.write(rh)
                os.replace(self.lib_file + ".hash.tmp", self.lib_file + ".hash")
            except OSError:
                pass
            with self.lock:
                self.lib_have_h = rh
                self.lib_ver += 1

    def loaded(self):
        """Lieder, die gerade in einem Deck liegen: [(Titel, Laenge)]."""
        with self.lock:
            return [(pl["p"].get("title", ""), float(pl["p"].get("du", 0.0))) for _, pl in sorted(self.plans.items()) if pl["p"].get("title")]

    def deck_marks(self):
        """Abschnitte und Hotcues der Lieder in den Decks, ohne Versatz: so liegen sie in der Datei. Fuer die Timeline des Showmanagers."""
        with self.lock:
            return [{"title": pl["p"].get("title", ""), "du": float(pl["p"].get("du", 0.0)), "fp": str(pl["p"].get("fp") or ""),
                     "se": clean_sections(pl["p"]), "cu": [float(c) for c in pl["p"].get("cu") or [] if isinstance(c, (int, float))],
                     "ev": pl["p"].get("ev") or [], "en": pl["p"].get("en") or [], "lvl": pl["p"].get("lvl"), "genre": str(pl["p"].get("genre") or "")}
                    for _, pl in sorted(self.plans.items())]

    # ---- Nachrichten verarbeiten ----------------------------------------------------------------------------------
    def feed(self, msg, now=None, addr=""):
        now = time.time() if now is None else now
        if not isinstance(msg, dict):
            return
        save_now = False
        with self.lock:
            if msg.get("type") not in LIB_TYPES:              # Liedliste allein (Light-Butler Helfer ohne Mixxx) heisst nicht "Mixxx verbunden"
                self.last_rx = now
            else:
                self.lib_rx = time.time()
            self.count += 1
            if addr:
                self.mac_ip = str(addr)
            if msg.get("type") == "plan":
                d = int(msg.get("d", 0))
                if not msg.get("key"):
                    self.plans.pop(d, None)                       # Lied ausgeworfen oder (noch) kein Plan
                    if msg.get("info"):
                        self.infos[d] = str(msg["info"])[:160]
                    else:
                        self.infos.pop(d, None)
                else:
                    self.plans[d] = {"p": msg, "t": now}
                    self.infos.pop(d, None)
            elif msg.get("type") == "genres":                     # alle Genres der Mixxx-Bibliothek mit Anzahl Lieder
                g = msg.get("g")
                if isinstance(g, list):
                    self.genres = [[str(x[0])[:40], int(x[1])] for x in g[:200]
                                   if isinstance(x, list) and len(x) == 2 and isinstance(x[1], (int, float))]
            elif msg.get("type") == "lib":                        # Titel der Bibliothek fuer den Showmanager, in Stuecken
                if isinstance(msg.get("t"), list) and isinstance(msg.get("n"), int) and msg["n"] > 0:
                    h, b = str(msg.get("h") or "")[:64], str(msg.get("b") or "")[:64]
                    if msg["n"] != self.lib_n or (h and h != self.lib_round_h):   # andere Fassung
                        # Grundlage A: die komplette Fassung lib_have_h (auch mitten in einer Teil-Uebertragung: die neue enthaelt
                        # alles, was seit ihr anders ist). Grundlage B: die Fassung, die der Pi gerade ganz sammelt (nicht mitten in
                        # einer Teil-Uebertragung, dann wuesste die Bruecke nicht, welche Stuecke veraltet sind).
                        base_a = (b == self.lib_have_h != "" and len(self.lib_parts) >= self.lib_n
                                  and (self.lib_round_h == self.lib_have_h or self.lib_delta is not None))
                        base_b = b == self.lib_round_h != "" and self.lib_delta is None
                        if b and msg["n"] == self.lib_n and (base_a or base_b):
                            # nur Geaendertes: die anderen Stuecke bleiben. Grundlage ist die Fassung, die der Pi komplett hat,
                            # oder die, die er gerade sammelt (dann kommen die fehlenden Stuecke mit)
                            self.lib_round, self.lib_round_done = set(), False
                            self.lib_delta = [int(msg.get("c") or 0) if isinstance(msg.get("c"), int) else 0, set()]
                        else:                                                     # alles neu sammeln
                            if self.lib_parts and not (self.lib_n and len(self.lib_parts) >= self.lib_n):
                                self.lib_carry = (self.lib_carry + [(self.lib_parts, self.lib_n)])[-8:]   # bis dahin Angekommenes weiter zeigen
                            elif self.lib_parts:
                                self.lib_carry = [(self.lib_parts, self.lib_n)]       # komplette Fassung: sie ersetzt alles davor
                            self.lib_parts, self.lib_n, self.lib_round, self.lib_round_done = {}, msg["n"], set(), False
                            self.lib_delta = None
                        self.lib_round_h = h
                    self.music_port = int(msg["mp"]) if isinstance(msg.get("mp"), int) and 0 < msg["mp"] < 65536 else 0
                    items = [lib_item(x) for x in msg["t"]]
                    i = int(msg.get("i", 0))
                    self.lib_parts[i] = [x for x in items if x]
                    self.lib_last_t = time.time()
                    self.lib_ver += 1
                    if i == 0 and self.lib_round_done:            # neuer Durchgang der Bruecke (alle 10 Minuten)
                        self.lib_round, self.lib_round_done = set(), False
                    self.lib_round.add(i)
                    if self.lib_delta is not None and b:
                        self.lib_delta[1].add(i)
                    delta_done = (self.lib_delta is not None and self.lib_delta[0] > 0 and len(self.lib_delta[1]) >= self.lib_delta[0]
                                  and len(self.lib_parts) >= self.lib_n)
                    if not self.lib_round_done and (delta_done or (len(self.lib_round) >= self.lib_n and len(self.lib_parts) >= self.lib_n)):
                        self.lib_round_done = True                 # je Durchgang einmal speichern, nicht bei jedem Stueck
                        save_now = True
            elif msg.get("type") == "libhash":                    # aktuelle Fassung der Bibliothek am Mac (alle 30 s)
                if isinstance(msg.get("mp"), int) and 0 < msg["mp"] < 65536:
                    self.music_port = int(msg["mp"])                 # Port des Vorhoerens auch ohne Listen-Pakete
                h = str(msg.get("h") or "")[:64]
                if "h" in msg and h != self.lib_bridge_h:     # ohne "h": nur der Port (Liste am Mac noch nicht fertig)
                    self.lib_bridge_h = h
                    self.lib_ver += 1
            elif msg.get("type") == "stats":                      # Statistik der Bibliothek (Seite Statistik)
                self.stats, self.stats_t = clean_stats(msg), now
            elif "pp" in msg and "d" in msg:
                self.decks[int(msg["d"])] = {"d": msg, "t": now}

        if save_now:
            self._save_lib()                                  # nach der Sperre: Show-Schleife und Panel warten nicht

    # ---- Vorhersage ----------------------------------------------------------------------------------------------
    def _events(self, plan, cfg):
        """Ereignisse des Plans: Liste von (Art, Start, Ende) nach den Schwellen aus den Einstellungen."""
        out = []
        shift = cfg["mixxx_shift_s"]
        moved = snap_drops(plan, cfg["mixxx_cue_snap_s"])
        for e in plan.get("ev", []):
            t0, end0 = float(e[1]), float(e[2] or e[1])
            if e[0] == "drop":
                t0 = end0 = moved.get(t0, t0)
            else:
                end0 = _moved(moved, end0)                                    # Aufbau/Stille enden mit dem Drop
            typ, t, end, strength, kind = e[0], t0 + shift, end0 + shift, float(e[3] or 0), e[4] if len(e) > 4 else ""
            if typ == "drop":
                lim = cfg["mixxx_drop_min"] if kind == "b" else cfg["mixxx_lift_min"] if kind == "l" else 9.0
                if strength >= lim:
                    out.append(("drop", t, t))
            elif typ in ("build", "gap", "break"):
                out.append((typ, t, end))
        return out

    def feed_autodj(self, msgs, now=None):
        """Meldungen der Auto-DJ-Seite (ungepruefte Daten aus dem Browser): nur Decks 11/12, nur bekannte Felder mit Zahlen,
        Plaene gekuerzt. Rueckgabe: Zahl der angenommenen Meldungen."""
        n = 0
        for m in msgs if isinstance(msgs, list) else []:
            if not isinstance(m, dict) or m.get("d") not in AUTODJ_DECKS:
                continue
            if m.get("type") == "plan":
                p = {"type": "plan", "d": m["d"], "key": str(m.get("key") or "")[:64]}
                if not p["key"]:
                    p["info"] = str(m.get("info") or "Keine Analyse am Musik-Rechner")[:160]
                else:
                    p["title"] = str(m.get("title") or "")[:120]
                    p["du"] = _f(m.get("du"))
                    p["ev"] = [[e[0], _f(e[1]), _f(e[2]), _f(e[3] if len(e) > 3 else 0), str(e[4] if len(e) > 4 else "")[:2]]
                               for e in (m.get("ev") or [])[:400]
                               if isinstance(e, list) and len(e) >= 3 and e[0] in ("drop", "build", "break", "gap")]   # wie compact_events
                    p["en"] = [_f(v) for v in (m.get("en") or [])[:400]]
                    p["cu"] = [_f(v) for v in (m.get("cu") or [])[:16]]
                    p["se"] = [x for x in (m.get("se") or [])[:32] if isinstance(x, list)]
                    p["genre"] = str(m.get("genre") or "")[:40]
                    p["grp"] = str(m.get("grp") or "")[:120]
                    p["fp"] = str(m.get("fp") or "")[:40]
                    for k in ("lvl", "le", "ki", "ke"):
                        if isinstance(m.get(k), int) and not isinstance(m.get(k), bool):
                            p[k] = m[k]
            else:
                p = {"d": m["d"]}
                for k in DECK_NUM:
                    p[k] = _f(m.get(k))
                p["pp"] = max(0.0, min(1.0, p["pp"]))
                p["vo"] = max(0.0, min(1.0, p["vo"]))
                p["rr"] = p["rr"] if 0.05 <= p["rr"] <= 4.0 else 1.0
                p["cf"], p["or"] = 0.0, 1                       # kein Crossfader: die Lautstaerke steckt schon in vo
            self.feed(p, now)
            n += 1
        return n

    def status(self, now, cfg):
        """Zustand fuer die Show und das Panel. Immer ein Dict; "plan" ist True, wenn die Vorhersage nutzbar ist."""
        with self.lock:
            connected = (now - self.last_rx) < 3.0
            stale = cfg["mixxx_stale_s"]
            best, best_w = None, 0.0
            for n, rec in self.decks.items():
                d = rec["d"]
                if now - rec["t"] > stale:
                    continue
                w = audible(d)
                if w > best_w + 0.02:
                    best, best_w = n, w
            st = {"connected": connected, "deck": best, "plan": False, "want": "normal", "next": [], "title": "",
                  "pos": 0.0, "dur": 0.0, "rate": 1.0, "bpm": 0.0, "audible": round(best_w, 2), "status": "",
                  "playing": False, "phase": None, "fk": 0, "key": 0, "fbpm": 0.0, "fp": "", "t": now, "pos_f": 0.0}
            if best is None:
                st["status"] = "kein Deck hoerbar" if connected else "nicht verbunden"
                st["status_key"] = "mx_nodeck" if connected else "mx_noconn"     # fuer die Uebersetzung im Panel
                return st
            st["src"] = "autodj" if best in AUTODJ_DECKS else "mixxx"            # Quelle des hoerbaren Liedes (Panel)
            rec = self.decks[best]
            d = rec["d"]
            rr = d.get("rr", 1.0) or 1.0
            du = d.get("du", 0.0)
            tp = d.get("pp", 0.0) * du + (now - rec["t"]) * rr                # Stelle im Lied jetzt (zwischen den Meldungen weiterlaufen)
            bp = d.get("bp", 0.0) or 0.0
            age = now - rec["t"]
            # Lage im Beat jetzt: letzte Meldung plus die Zeit seither im aktuellen Tempo (Pitch und Sync schon enthalten)
            phase = ((d.get("bd", 0.0) + (age + cfg["mixxx_lead_s"]) * bp / 60.0) % 1.0) if bp > 0 else None
            st.update({"pos_f": tp, "pos": round(tp, 2), "dur": du, "rate": rr, "bpm": bp, "playing": bool(d.get("pl")),
                       "phase": phase, "fk": int(d.get("fk", 0) or 0), "key": int(d.get("k", 0) or 0),
                       "fbpm": d.get("fb", 0.0)})
            pl = self.plans.get(best)
            if pl is None:
                st["status"] = self.infos.get(best) or "Lied nicht erkannt oder noch nicht analysiert"
                st["status_key"] = "" if self.infos.get(best) else "mx_unknown"   # Hinweis der Bruecke bleibt wie er ist
                return st
            p = pl["p"]
            st["title"] = p.get("title", "")
            st["fp"] = str(p.get("fp") or "")[:40]
            lvl = p.get("lvl")
            st["lvl"] = int(lvl) if isinstance(lvl, (int, float)) and 0 < lvl < 100 else None   # Energiestufe aus Mixxx (Crate/Farbe)
            st["lvl_est"] = bool(st["lvl"] and p.get("le"))                   # geschaetzt (Mac), nicht aus dem Tag
            ki = p.get("ki")
            st["key_est"] = False
            if not st["fk"] and isinstance(ki, int) and 1 <= ki <= 24:        # Mixxx kennt keine Tonart: aus der Datei oder geschaetzt (Mac)
                st["fk"], st["key_est"] = ki, bool(p.get("ke"))
            st["genre"] = str(p.get("genre") or "")[:40]
            st["grp"] = str(p.get("grp") or "")[:120]                       # Gruppe(n) im Tag, "A; B" (Licht-Stil, 13.11.2026)
            if abs(p.get("du", 0.0) - du) > 0.05:                             # Plan gehoert zu einem anderen Lied
                st["status"] = "Plan passt nicht zum geladenen Lied"
                st["status_key"] = "mx_mismatch"
                return st
            events = self._events(p, cfg)
            lead = cfg["mixxx_lead_s"] * rr
            tl = tp + lead
            drop_len = cfg["drop_len_s"]
            want = "normal"
            for typ, a, b in events:
                if typ == "break" and a <= tl < b:
                    want = "break"
            for typ, a, b in events:
                if typ == "build" and a <= tl < b:
                    want = "build"
            for typ, a, b in events:
                if typ == "gap" and a <= tl < b:
                    want = "gap"
            for typ, a, b in events:
                if typ == "drop" and a <= tl < a + drop_len * rr:
                    want = "drop"
            upcoming = []
            for typ, a, b in events:
                if typ in ("build", "gap", "drop") and a > tp:
                    upcoming.append({"type": typ, "in": round((a - tp) / rr, 1)})
            upcoming.sort(key=lambda u: u["in"])
            en = p.get("en") if isinstance(p.get("en"), list) else []
            st["bar"] = {"ev": [[typ, round(a, 1), round(b, 1)] for typ, a, b in events],      # Liedverlauf im Panel
                         "en": [max(0, min(100, int(v))) for v in en[:400] if isinstance(v, (int, float))],
                         "cu": [round(float(c), 1) for c in (p.get("cu") or [])[:16] if isinstance(c, (int, float))],   # Hotcues
                         "se": clean_sections(p, cfg["mixxx_shift_s"])}                       # Intro, Strophe, Hauptteil, Break, Outro
            st["section"] = next((s[0] for s in st["bar"]["se"] if s[1] <= tl < s[2]), "")
            cues = [float(c) for c in (p.get("cu") or []) if isinstance(c, (int, float))]
            st["cue_n"] = sum(1 for c in cues if c <= tl)                     # so viele Hotcues sind schon vorbei
            st["cue_id"] = (best, p.get("key", ""))
            st.update({"plan": True, "want": want, "next": upcoming[:3], "status": "Plan aktiv", "status_key": "mx_plan"})
            return st
