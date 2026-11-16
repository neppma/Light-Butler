"""
file_check.py - Dateien im Musikordner pruefen (Wunsch von Markus, 08.11.2026; Seite /musik/pruefen).

Drei Listen:
  muell     Datenmuell: Thumbs.db, desktop.ini (Reste von Windows); die Hilfsdateien von macOS ("._", .DS_Store) nicht
  sonstige  keine Musik und kein Bild: Logs, Texte, .bat, Playlists ... (selbst entscheiden)
  namen     Lieder der Bibliothek, deren Dateiname nicht zum Schema passt, mit Vorschlag aus den Tags:
              KATEGORIE/Artists/Interpret/Interpret - Titel.mp3
              KATEGORIE/Artists/Interpret/Jahr - Album/Nr - Interpret - Titel.mp3   (auch Nr - Album - Interpret - Titel)
              KATEGORIE/Compilations/Sampler/Nr - Interpret - Titel.mp3           (auch Nr - Sampler - Interpret - Titel)
Geloescht wird nur auf Klick und nur in den Papierkorb des Mac (Finder, "Zuruecklegen" holt es wieder); umbenannt nur einzeln.
Nur Dateien aus der letzten Pruefung; nie ausserhalb des Musikordners.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata

from pfad import norm as _pn, sibling as _sib
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

AUDIO = {".mp3", ".m4a", ".mp4", ".aac", ".wav", ".flac", ".ogg", ".aif", ".aiff", ".wma", ".opus"}
IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
JUNK_NAMES = {"thumbs.db", "desktop.ini", "ehthumbs.db"}   # Reste von Windows
# Weitere Muell-Namen pflegt Markus selbst (Seite Dateien pruefen, Reiter Datenmuell; Standard: Cover-Kopien vom Media Player).
COVER_FILES = ("folder", "cover", "front")
# Hilfsdateien von macOS ("._Name", .DS_Store, .localized) legt der Mac auf USB-Sticks immer wieder an: nicht vorschlagen, sie
# kaemen gleich wieder (Hinweis von Markus 08.11.2026)
MAC_AUX = {".ds_store", ".localized"}
SKIP_DIRS = {"light-butler papierkorb", ".trashes", ".spotlight-v100", ".fseventsd", ".temporaryitems", ".documentrevisions-v100", "$recycle.bin",
             "system volume information"}
BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
SHORT_S = 30.0             # kurze Stuecke (Samples, Jingles): BPM und Tonart sind nur geraten (Wunsch 09.11.2026)
LIST_MAX = 3000            # so viele Eintraege je Liste gehen an die Seite (die Zahl stimmt immer)


def nfc(s):
    return _pn(unicodedata.normalize("NFC", str(s or "")))          # Windows: auch "\\" -> "/" (Pfade vergleichen)


def clean_part(s):
    """Teil eines Dateinamens: verbotene Zeichen weg, Leerzeichen zusammen (Punkte bleiben: "R.E.M.", "Inc.")."""
    s = BAD.sub("-", nfc(s))
    return re.sub(r"\s+", " ", s).strip()


def clean_stem(s):
    """Ganzer Dateiname ohne Endung: zusaetzlich keine Punkte und Leerzeichen am Ende (Windows, Finder)."""
    return clean_part(s).strip(" .")


# ---- Namensregeln (Wunsch von Markus 08.11.2026, stehen auch als Hinweistafel auf der Seite /musik/pruefen) ----
MAX_STEM = 100                                           # hoechstens 100 Zeichen ohne .mp3, gekuerzt wird der Titel
ARTIST_MAX = 40                                          # laengere Interpreten: die ersten Namen, dann "u. a."
CHAR_MAP = {"“": "'", "”": "'", "„": "'", "‟": "'", '"': "'", "’": "'", "‘": "'", "`": "'", "´": "'", "‚": "'",
            "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", ";": ",", "[": "(", "]": ")", "{": "(", "}": ")",
            "!": "", "?": "", "¡": "", "¿": "", "*": "", "<": "", ">": "", "|": "-", "\\": "-", "…": "", "~": "-"}
FEAT = re.compile(r"\s*[\(\[]\s*(feat\.?|ft\.?|featuring|with)\s[^\)\]]*[\)\]]|\s+(feat\.?|ft\.?|featuring)\s.*$", re.I)


def tidy(s):
    """Interpret oder Titel fuer den Dateinamen aufbereiten: feat. weg, Zeichen vereinheitlichen, Leerzeichen ordnen."""
    s = FEAT.sub("", nfc(s))
    s = re.sub(r"\s*:\s*", " - ", s)                   # "Star Wars: Throne Room" -> "Star Wars - Throne Room"
    s = re.sub(r"\s+/\s+", " & ", s)                   # "A / B" -> "A & B"
    s = s.replace("/", "-")                            # "AC/DC" -> "AC-DC"
    s = "".join(CHAR_MAP.get(c, c) for c in s)
    s = re.sub(r"[\x00-\x1f]", "", s)
    s = re.sub(r"\(\s*\)", "", s)                      # leere Klammern
    s = re.sub(r"\s+([,.)])", r"\1", s)                # kein Leerzeichen vor Satzzeichen
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r"(\S)- ", r"\1 - ", s)                 # "Suite- No. 2" (frueher aus ":") -> "Suite - No. 2"
    return re.sub(r"\s+", " ", s).strip(" ,-")


def short_artist(a):
    """Mehr als ARTIST_MAX Zeichen: die ersten Namen, dann "u. a." (kurze Bandnamen wie "Earth, Wind & Fire" bleiben ganz)."""
    if len(a) <= ARTIST_MAX:
        return a
    parts = [p.strip() for p in re.split(r",|&|\bund\b|\band\b", a) if p.strip()]
    if len(parts) < 2:
        return a[:ARTIST_MAX].rsplit(" ", 1)[0]
    out = parts[0]
    for p in parts[1:]:
        if len(out) + 2 + len(p) > ARTIST_MAX - 6:
            break
        out += ", " + p
    return out + " u. a."


def name_for(artist, title):
    """Dateiname ohne Endung nach den Namensregeln: "Interpret - Titel", hoechstens MAX_STEM Zeichen."""
    a, t = short_artist(tidy(artist)), tidy(title)
    stem = f"{a} - {t}"
    if len(stem) > MAX_STEM:
        room = max(10, MAX_STEM - len(a) - 3)
        cut = t[:room + 1]
        best = max(cut.rfind(x) for x in (" - ", ", ", " ("))
        if best >= room * 0.6:
            cut = cut[:best]                           # lieber an " - " oder "," kuerzen als mitten im Satz
        else:
            cut = cut[:cut.rfind(" ")] if " " in cut and len(t) > room else cut[:room]
        t = re.sub(r"[\s,.\-(]+$", "", cut)
        if t.count("(") > t.count(")"):
            t = t[:t.rfind("(")].rstrip(" ,-")
        stem = f"{a} - {t}"
    return clean_stem(stem)


WAIT_TAGS_S = 900.0                                      # hoechstens 15 min auf die Tags der Dateien warten


TAG_SHOW = ("title", "artist", "album", "albumartist", "track")


def file_tags(f):
    """Titel, Interpret, Album, Album-Interpret, Track aus der MP3 (Wunsch 08.11.2026: sehen, was im Tag steht, bevor etwas
    aus dem Dateinamen verschwindet). Andere Formate oder Fehler: {}."""
    if not str(f).lower().endswith(".mp3"):
        return {}
    try:
        import tag_edit
        fl = tag_edit.read_tags(f).get("fields") or {}
        return {k: str(fl.get(k) or "") for k in TAG_SHOW}
    except Exception:                                    # noqa: BLE001  Anzeige ist Beiwerk
        return {}


def carry_jsonl(file, old, new):
    """Zeilen {"path": old, ...} einer Ablage (JSON je Zeile) fuer den neuen Pfad noch einmal anhaengen. Die alten bleiben,
    weil Mixxx den alten Pfad bis zum naechsten Start der App kennt. Rueckgabe: Zahl der kopierten Zeilen."""
    try:
        with open(file, encoding="utf-8") as fh:
            rows = []
            for line in fh:
                if old not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("path") == old:
                    rows.append(json.dumps(dict(r, path=new), ensure_ascii=False))
    except OSError:
        return 0
    if rows:
        with open(file, "a", encoding="utf-8") as fh:                # ein Schreibvorgang, der Mess-Prozess haengt auch an
            fh.write("".join(x + "\n" for x in rows))
    return len(rows)


SCRIPTS = ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "CYRILLIC", "GREEK", "ARABIC", "HEBREW", "THAI", "DEVANAGARI")


def scripts(s):
    """Fremde Schriften in einem Text (chinesisch, kyrillisch ...), lateinische Buchstaben zaehlen nicht."""
    out = set()
    for c in str(s or ""):
        if ord(c) > 0x24F:
            n = unicodedata.name(c, "")
            out |= {k for k in SCRIPTS if n.startswith(k) or f" {k} " in f" {n} "}
    return out


def has_cover(path):
    """Hat die Musikdatei ein eigenes Bild? (nur MP3 mit ID3; andere: nein)"""
    if not path.lower().endswith(".mp3"):
        return False
    try:
        from music_serve import id3_cover, _syncsafe
        with open(path, "rb") as fh:
            head = fh.read(10)
            if head[:3] != b"ID3" or len(head) < 10:
                return False
            head += fh.read(min(_syncsafe(head[6:10]) + 10, 16 * 1024 * 1024))
        return bool(id3_cover(head))
    except (OSError, ImportError):
        return False


DEFAULT_JUNK_NAMES = ("AlbumArt_{*}_Large.jpg", "AlbumArt_{*}_Small.jpg", "AlbumArtSmall.jpg")   # Cover-Kopien vom Media Player
NAMES_MAX = 100


def junk_names_path():
    return os.path.join(_pfad.daten(), "pruefen", "muell_namen.txt")


def clean_names(lines):
    """Eigene Muell-Namen (Wunsch 09.11.2026): eine Zeile je Name, * = beliebig; leere und doppelte Zeilen weg."""
    out, seen = [], set()
    for x in lines or []:
        x = nfc(str(x)).strip()
        if x and "/" not in x and len(x) <= 120 and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out[:NAMES_MAX]


def load_junk_names():
    """Liste vom Mac (~/Light-Butler-Daten/pruefen/muell_namen.txt); gibt es sie nicht: die Cover-Kopien vom Media Player."""
    try:
        with open(junk_names_path(), encoding="utf-8") as fh:
            return clean_names(fh.read().splitlines())
    except OSError:
        return list(DEFAULT_JUNK_NAMES)


def save_junk_names(lines):
    names = clean_names(lines)
    p = junk_names_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        fh.write("".join(x + "\n" for x in names))
    os.replace(p + ".tmp", p)
    return names


def name_match(name, pat):
    """Dateiname passt zum Muster (ohne Gross/klein, * und ?). Musikdateien passen nie (Sicherung)."""
    import fnmatch
    if os.path.splitext(name)[1].lower() in AUDIO:
        return False
    return fnmatch.fnmatchcase(nfc(name).casefold(), nfc(pat).casefold())


def folder_needs(d, files, gone):
    """Braucht der Ordner d ein Bild aus gone (Namen, die als Muell gelten)? Nein, wenn ein anderes Cover-Bild bleibt (Folder.jpg,
    cover.png, AlbumArt*.jpg ...) oder jedes Lied sein eigenes Cover hat."""
    for f in files:
        stem, ext = os.path.splitext(f.lower())
        if f in gone or ext not in (".jpg", ".jpeg", ".png"):
            continue
        if stem in COVER_FILES or stem.startswith("albumart") or stem == "album":
            try:
                if os.path.getsize(os.path.join(d, f)) > 0:
                    return False
            except OSError:
                pass
    audio = [f for f in files if os.path.splitext(f)[1].lower() in AUDIO]
    return not all(has_cover(os.path.join(d, f)) for f in audio)


def junk_by_names(dfiles, names):
    """Dateien, die nach der Liste Muell sind: {Pfad: Muster}. Bilder nur, wenn der Ordner sie nicht braucht."""
    out = {}
    for d, files in dfiles.items():
        hit = {}
        for f in files:
            for pat in names:
                if name_match(f, pat):
                    hit[f] = pat
                    break
        if not hit:
            continue
        imgs = {f for f in hit if os.path.splitext(f)[1].lower() in IMAGE}
        if imgs and folder_needs(d, files, set(hit)):
            hit = {f: v for f, v in hit.items() if f not in imgs}
        for f, v in hit.items():
            out[_pn(os.path.join(d, f))] = v
    return out


def nkey(name):
    """Dateiname zum Vergleich auf Gleichheit: macOS und der Stick unterscheiden Gross/klein nicht (08.11.2026)."""
    return nfc(name).casefold()


def loose(s):
    """Vergleich ohne Gross/klein, Satzzeichen und Leerzeichen: "Orpheus" == "Orpheus:", "R.E.M" == "R.E.M."."""
    return re.sub(r"[\W_]+", "", nfc(s).casefold())


def track_no(v):
    m = re.match(r"\s*(\d{1,3})", str(v or ""))
    return int(m.group(1)) if m else 0


def layout(rel):
    """Art der Ablage aus dem Pfad im Musikordner: 'single', 'album', 'sampler' oder '' (anders, nicht pruefen)."""
    parts = [p for p in rel.split("/") if p]
    if len(parts) < 4 or parts[1].lower() not in ("artists", "compilations"):
        return ""
    if parts[1].lower() == "compilations":
        return "sampler"
    return "single" if len(parts) == 4 else "album"


MULTI_MIN = 3                                            # so viele gleiche Titel im Ordner, bevor die Nummer in den Namen kommt


def multi_key(f, rec):
    """Ordner + Interpret + Titel: gleich bei Tracks einer CD mit demselben Titel (Hoerbuch, Saetze, Samples)."""
    return (os.path.dirname(f), loose(rec.get("artist") or ""), loose(rec.get("title") or ""))


def multi_groups(items):
    """items: [(Datei, Lied)] -> {multi_key: Art} fuer Ordner, in denen mehrere Dateien denselben Interpreten und Titel haben,
    jede mit eigener Tracknummer (Wunsch 09.11.2026). Art "nr": "Interpret - Titel - 04" statt "(2)" (Hoerbuch, Saetze);
    "tag": der Titel ist der CD-Name oder der Interpret (falsche Tags einer Musik-CD): erst richtige Titel holen."""
    g = {}
    for f, r in items:
        k = multi_key(f, r)
        if k[1] and k[2]:
            g.setdefault(k, []).append((track_no(r.get("tracknumber")), loose(r.get("album") or ""), float(r.get("duration") or 0)))
    out = {}
    for k, v in g.items():
        nrs = [x[0] for x in v]
        # erst ab drei: zwei gleiche sind meist dasselbe Lied zweimal (Doppelte entfernen); verschiedene Alben ebenso
        if len(v) < MULTI_MIN or not all(nrs) or len(set(nrs)) != len(nrs) or len({x[1] for x in v if x[1]}) > 1:
            continue
        # Titel = Interpret oder CD-Name (auch "CD - CD"): falsche Tags einer Musik-CD
        out[k] = "tag" if k[1] in k[2] or all(x[1] and x[1] in k[2] for x in v) else "nr"
    return out


def suggest(rec, rel, multi=False):
    """Vorgeschlagener Dateiname (mit Endung) und ob der jetzige passt. None = nicht pruefbar (keine Tags, andere Ablage).
    multi = im Ordner gibt es denselben Interpreten und Titel mehrmals (multi_groups): Tracknummer hinten an den Namen."""
    kind = layout(rel)
    artist, title = clean_part(rec.get("artist")), clean_part(rec.get("title"))
    if not kind or not artist or not title:
        return None
    name = rel.rsplit("/", 1)[-1]
    stem, ext = os.path.splitext(name)
    stem = nfc(stem)
    # Vorschlag immer "Interpret - Titel" (Wunsch von Markus 08.11.2026: keine Tracknummer vorne, die steht im Tag; so sortiert
    # der Finder nach Interpret). Die heutigen Formen mit Nummer und Album im Namen gelten weiter als passend.
    want = name_for(rec.get("artist"), rec.get("title"))    # Namensregeln (08.11.2026)
    okset = {loose(want), loose(clean_stem(f"{artist} - {title}"))}   # heute schon passende Namen bleiben passend
    if multi == "tag":
        return {"name": name, "want": "", "why": "Alle Lieder dieser CD haben im Tag denselben Titel (den CD-Namen oder den "
                "Interpreten): die Tags sind falsch. Mit dem CD-Assistenten (Trackliste aus dem Internet einfügen) oder mit „Tags“ → Shazam richtigstellen, dann umbenennen."}
    mnr = track_no(rec.get("tracknumber")) if multi else 0
    if mnr:                                                # gleicher Titel mehrmals auf der CD: "Interpret - Titel - 04"
        want = f"{want} - {mnr:02d}"
        okset = {loose(want)}
    if kind != "single":
        nr = track_no(rec.get("tracknumber")) or track_no(stem)
        folder = re.sub(r"^\d{4}\s*-\s*", "", clean_part(rel.split("/")[-2]))      # "1996 - Reverence" -> "Reverence"
        albums = {a for a in (clean_part(rec.get("album")), folder) if a}
        if nr:
            okset |= {loose(f"{nr:02d} - {artist} - {title}"), loose(f"{nr} - {artist} - {title}")}
            for al in albums:                              # heutige Ablage: Album auch im Dateinamen
                for v in (f"{nr:02d} - {artist} - {al} - {title}", f"{nr:02d} - {al} - {artist} - {title}"):
                    okset.add(loose(v))
    ok = loose(stem) in okset
    foreign = scripts(artist + title) - scripts(stem)
    if not ok and foreign:
        # Fehlerbericht 08.11.2026: "09 - Afro Meeting 2000 - Andy Picchu - De Los Andes" hatte chinesische Tags (falscher
        # CD-Datenbank-Treffer). Fremde Schrift in den Tags, die im Namen nicht vorkommt: kein Vorschlag, erst Tags pruefen.
        return {"name": name, "want": "", "why": f"Tags in anderer Schrift ({artist} - {title}), der Dateiname nicht: "
                "wahrscheinlich falsche Tags. Erst anhören und in der Musik-Datenbank mit „Tag bearbeiten“ (Shazam) richtigstellen."}
    album = clean_part(rec.get("album")) or re.sub(r"^\d{4}\s*-\s*", "", clean_part(rel.split("/")[-2]) if "/" in rel else "")
    if ok:
        return {"name": name, "want": name, "ok": True}
    return {"name": name, "want": want + ext.lower(), "why": "", "album": album}


def _size(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def rename_any(src, dst):
    """os.rename, aber jede Schreibweise der Umlaute probieren (Fehlerbericht 09.11.2026: auf dem FAT-Stick laesst sich eine
    alte Datei nur mit dem zusammengesetzten Pfad umbenennen, "No such file or directory" sonst). Begleitdatei "._" geht mit."""
    cands = []
    for v in (src, nfc(src), unicodedata.normalize("NFD", src)):
        if v not in cands:
            cands.append(v)
    try:
        from music_serve import disk_name
        if disk_name(src) not in cands:
            cands.insert(1, disk_name(src))
    except ImportError:
        pass
    err = None
    for v in cands:
        try:
            os.rename(v, dst)
        except FileNotFoundError as e:
            err = e
            continue
        for ad in (os.path.join(os.path.dirname(v), "._" + os.path.basename(v)),
                   os.path.join(os.path.dirname(nfc(v)), "._" + os.path.basename(nfc(v)))):
            try:
                os.rename(ad, os.path.join(os.path.dirname(dst), "._" + os.path.basename(dst)))
                break
            except OSError:
                pass
        return
    raise err or FileNotFoundError(src)


def to_trash_many(paths, run=subprocess.run, batch=150):
    """Viele Dateien auf einmal in den Papierkorb (Finder), in Paketen. Rueckgabe: Zahl der Fehler-Pakete."""
    bad = 0
    if sys.platform == "win32":                          # Windows: einzeln in "Light-Butler Papierkorb" (music_serve.to_trash)
        from music_serve import to_trash
        for p in paths:
            if os.path.lexists(p):
                try:
                    to_trash(p)
                except OSError:
                    bad += 1
        return bad
    script = ["on run argv", "set L to {}", "repeat with p in argv", "copy (POSIX file (contents of p) as alias) to end of L",
              "end repeat", 'tell application "Finder" to delete L', "end run"]
    args = []
    for line in script:
        args += ["-e", line]
    from music_serve import disk_name, trash_move
    for i in range(0, len(paths), batch):
        part = []
        for p in paths[i:i + batch]:
            if not os.path.lexists(p):
                continue
            if not str(p).isascii():                     # Umlaute (FAT-Stick, 09.11.2026): selbst, ohne Finder
                try:
                    trash_move(p)
                    continue
                except OSError:
                    pass
            part.append(disk_name(p))
        if not part:
            continue
        try:
            r = run(["osascript"] + args + part, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
            failed = bool(r.returncode)
        except subprocess.TimeoutExpired:
            failed = True
        if failed:                                       # Finder haengt (09.11.2026): selbst in den Papierkorb des Laufwerks
            for p in part:
                if os.path.lexists(p):
                    try:
                        trash_move(p)
                    except OSError:
                        bad += 1
    return bad


def empty_dirs(root, dfiles, music_dirs):
    """Ordner ohne Musik, auch in keinem Unterordner (Wunsch 09.11.2026). Nur die obersten (ist der Ordner leer, sind es
    seine Unterordner auch). Rueckgabe: [(Ordner, Zahl der Dateien darin, bis zu 3 Beispiele)]."""
    has = set()
    for d in music_dirs:
        while d.startswith(root) and d not in has:
            has.add(d)
            d = os.path.dirname(d)
    cand = sorted(d for d in dfiles if d != root and d not in has)
    out, top = [], None
    for d in cand:
        if top and d.startswith(top + "/"):
            continue
        top = d
        files = [_pn(os.path.join(x, f)) for x in dfiles if x == d or x.startswith(d + "/") for f in dfiles[x]]
        out.append((d, len(files), [os.path.relpath(f, d) for f in sorted(files)[:3]]))
    return out


def has_music(d):
    for _x, _dirs, files in os.walk(d):
        if any(os.path.splitext(f)[1].lower() in AUDIO and not f.startswith("._") for f in files):
            return True
    return False


def bpm_key(f):
    """BPM (TBPM), Tonart (TKEY) und unsere geschaetzte Energie (nie die von Mixed In Key) aus der MP3; Fehler: leer."""
    out = {"bpm": "", "key": "", "energy": ""}
    try:
        import tag_edit
        fl = tag_edit.read_tags(f).get("fields") or {}
        out.update(bpm=str(fl.get("bpm") or ""), key=str(fl.get("key") or ""))
    except Exception:                                    # noqa: BLE001
        pass
    try:
        import energy_level
        out["energy"] = energy_level.own_energy(f)
    except Exception:                                    # noqa: BLE001
        pass
    return out


class FileCheck:
    """root() -> Musikordner am Mac; songs() -> Lieder der Bibliothek (Mixxx-Pfad, Tags); locate(p) -> Datei am Mac."""

    def __init__(self, root, songs, locate, log=None, trash=to_trash_many, renamed=None, ready=None, sleep=time.sleep):
        self.root, self.songs, self.locate = root, songs, locate
        # ready() -> True, sobald die Tags der Dateien gelesen sind (Ordner-Liste). Fehlerbericht 08.11.2026: gleich nach einem
        # Neustart des Helfers galten noch die alten Werte aus Mixxx ("Eric Lévi - Era" sollte "Era - Era" heissen).
        self.ready, self.sleep = ready, sleep
        self.log, self.trash, self.renamed = log or (lambda t: None), trash, renamed
        self.lock = threading.Lock()
        self.state, self.t, self.done, self.err = "idle", 0.0, 0, ""
        self.junk, self.other, self.names, self.sizes = [], [], [], {}
        self.dfiles = {}                                     # Ordner -> Dateinamen (Vorschau der eigenen Muell-Namen)
        self.index, self.same = {}, []                    # Dateiname (ohne Gross/klein) -> Pfade; Gruppen gleicher Namen
        self.held = []                                    # "So lassen" mit Vorschlag (Reiter "So gelassen", Wunsch 08.11.2026)
        self.fmap = {}                                    # Datei -> Pfad in Mixxx (fuer Umbenennen aus "Gleiche Namen")
        self.multi = {}                                   # Ordner+Interpret+Titel mehrmals (Tracknummer in den Namen)
        self.empty = []                                   # Ordner ohne Musik (auch Unterordner): [(Ordner, Zahl Dateien, Beispiele)]
        self.short = []                                   # MP3s unter SHORT_S mit BPM oder Tonart im Tag
        self.job = None                                   # laufendes Loeschen vieler Dateien: [fertig, alle]
        self.thread = None

    # ---- Pruefen ----
    def scan(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return False
            self.thread = threading.Thread(target=self._scan, name="dateien-pruefen", daemon=True)
            self.thread.start()
        return True

    def _scan(self):
        with self.lock:
            self.state, self.done, self.err = "scan", 0, ""
        waited = 0.0
        while self.ready is not None and not self.ready() and waited < WAIT_TAGS_S:
            with self.lock:
                self.state = "wait"                          # Seite: "Warte auf die Tags der Dateien"
            self.sleep(2.0)
            waited += 2.0
        with self.lock:
            self.state = "scan"
        root = _pn(self.root() or "").rstrip("/")
        junk, other, sizes, index = [], [], {}, {}
        if not root or not os.path.isdir(root):
            with self.lock:
                self.state, self.err = "idle", "Musikordner nicht gefunden (Stick eingesteckt? Ordner in den Einstellungen?)"
            return
        n = 0
        dfiles, music_dirs = {}, set()                       # leere Ordner (Wunsch 09.11.2026): Dateien je Ordner, Ordner mit Musik
        import music_excl
        skip = music_excl.matcher(root)                      # ausgeschlossene Ordner aus dem Panel: nicht hineinschauen (10.11.2026)
        import stick_hold
        for d, dirs, files in os.walk(root):
            d = _pn(d)
            if stick_hold.held(root):                        # Stick wird ausgeworfen: Pruefung abbrechen
                with self.lock:
                    self.state, self.err = "idle", "Stick wurde ausgeworfen: bitte neu prüfen, wenn er wieder da ist"
                return
            dirs[:] = [x for x in dirs if x.lower() not in SKIP_DIRS and not x.startswith(".") and not skip(os.path.join(d, x))]
            dfiles[d] = []
            for f in files:
                n += 1
                p = _pn(os.path.join(d, f))
                low, ext = f.lower(), os.path.splitext(f)[1].lower()
                if f.startswith("._") or low in MAC_AUX:      # macOS legt sie wieder an: weder Muell noch "sonstige"
                    continue
                dfiles[d].append(f)
                if ext in AUDIO:                              # jeder Musik-Dateiname im ganzen Ordner (gleiche Namen finden)
                    index.setdefault(nkey(f), []).append(p)
                    music_dirs.add(d)
                if low in JUNK_NAMES:
                    junk.append(p)
                elif ext not in AUDIO and ext not in IMAGE:
                    other.append(p)
                else:
                    continue
                try:
                    sizes[p] = os.lstat(p).st_size              # Groesse fuer die Seite (Wunsch 08.11.2026)
                except OSError:
                    sizes[p] = 0
            with self.lock:
                self.done = n
        jnames = load_junk_names()                           # eigene Muell-Namen (Wunsch 09.11.2026)
        byname = junk_by_names(dfiles, jnames)
        other = [p for p in other if p not in byname]
        for p in byname:
            if p not in junk:
                junk.append(p)
            try:
                sizes[p] = os.lstat(p).st_size
            except OSError:
                sizes[p] = 0
        self.dfiles = dfiles
        empty = empty_dirs(root, dfiles, music_dirs)
        names, held, kept, fmap, short = [], [], self.kept(), {}, []
        songs = self.songs() or []
        multi = multi_groups([(f, r) for r in songs for f in [_pn(self.locate(r.get("path") or "")) if r.get("path") else None] if f])
        for r in songs:
            p = r.get("path") or ""
            f = _pn(self.locate(p)) if p else None
            if not f or not f.startswith(root + "/"):
                continue
            fmap[f] = p
            if 0 < float(r.get("duration") or 0) < SHORT_S and f.lower().endswith(".mp3"):
                bk = bpm_key(f)
                if bk["bpm"] or bk["key"] or bk["energy"]:
                    short.append(dict(bk, path=p, file=f, dur=round(float(r.get("duration") or 0), 1)))
            s = suggest(r, f[len(root) + 1:], multi.get(multi_key(f, r), ""))
            if s and not s.get("ok"):
                item = dict(s, path=p, file=f, mixxx=int(bool(r.get("cues") or r.get("crates") or r.get("lists"))))
                (held if p in kept else names).append(item)    # "So lassen": eigener Reiter, nicht in der Namensliste
        held.sort(key=lambda x: x["file"].lower())
        for x in names + held:                             # Tags der Datei fuer die Seite (nur diese paar hundert Dateien)
            x["tags"] = file_tags(x["file"])
        names.sort(key=lambda x: x["file"].lower())
        # Wunsch 08.11.2026: kein Dateiname darf zweimal vorkommen (fuer einen spaeteren gemeinsamen Ordner). Ist der Vorschlag
        # schon vergeben (anderswo oder von einem anderen Vorschlag), kommt das Album in Klammern dazu, sonst (2), (3) ...
        taken = {k: list(v) for k, v in index.items()}
        drop = set()
        for x in names:
            if not x["want"]:
                continue
            stem, ext = os.path.splitext(x["want"])
            others = [q for q in taken.get(nkey(x["want"]), []) if nfc(q) != nfc(x["file"])]
            cur = nfc(os.path.basename(x["file"]))
            cstem = os.path.splitext(cur)[0]
            # Fehlerbericht 09.11.2026: schon mit Zusatz umbenannt ("Interpret - Titel (Album)" oder "(2)"), weil der einfache Name
            # vergeben ist: das passt, kein neuer Vorschlag (sonst "in sich selbst umbenennen" oder ein anderer Zusatz)
            if others and nkey(cstem).startswith(nkey(stem)) and re.fullmatch(r".* \([^()]+\)", cstem) \
                    and nkey(re.sub(r" \([^()]+\)$", "", cstem)) == nkey(stem) \
                    and not [q for q in taken.get(nkey(cur), []) if nfc(q) != nfc(x["file"])]:
                drop.add(x["file"])
                continue
            if others:
                x["clash"] = others[0]
                cands = ([f"{stem} ({x['album']})"] if x.get("album") else []) + [f"{stem} ({i})" for i in range(2, 50)]
                x["want"] = next(c + ext for c in cands if not [q for q in taken.get(nkey(c + ext), []) if nfc(q) != nfc(x["file"])])
            taken.setdefault(nkey(x["want"]), []).append(x["file"])
            if nkey(x["want"]) == nkey(os.path.basename(x["file"])):
                drop.add(x["file"])                          # Vorschlag = heutiger Name: nichts zu tun
        names = [x for x in names if x["file"] not in drop]
        same = sorted(([os.path.basename(v[0]), sorted(v)] for v in index.values() if len(v) > 1), key=lambda g: g[0].lower())
        with self.lock:
            self.junk, self.other, self.names, self.sizes = sorted(junk), sorted(other), names, sizes
            self.held, self.empty, self.short = held, empty, sorted(short, key=lambda x: x["file"].lower())
            self.multi = multi
            self.index, self.same, self.fmap = index, same, fmap
            self.state, self.t = "ready", time.time()
        self.log(f"Dateien pruefen: {len(junk)} Datenmuell, {len(other)} sonstige, {len(names)} Namen passen nicht zum Schema, "
                 f"{len(same)} Dateinamen mehrfach, {len(empty)} Ordner ohne Musik, {len(short)} kurze Stuecke mit BPM/Tonart")

    def junk_preview(self, lines):
        """Vorschau der eigenen Muell-Namen: je Zeile wie viele Dateien sie erwischt, mit Beispielen (nichts wird geaendert)."""
        names = clean_names(lines)
        root = _pn(self.root() or "").rstrip("/")
        with self.lock:
            dfiles = dict(self.dfiles)
        if not dfiles:
            raise ValueError("Zuerst prüfen (die Dateiliste fehlt noch)")
        hit = junk_by_names(dfiles, names)
        rows = []
        for pat in names:
            ps = sorted(p for p, v in hit.items() if v == pat)
            skipped = 0                                       # Bilder, die ein Ordner noch braucht
            if os.path.splitext(pat)[1].lower() in IMAGE or pat.endswith("*"):
                for d, files in dfiles.items():
                    skipped += sum(1 for f in files if name_match(f, pat) and _pn(os.path.join(d, f)) not in hit
                                   and os.path.splitext(f)[1].lower() in IMAGE)
            rows.append({"name": pat, "n": len(ps), "bytes": sum(_size(p) for p in ps), "ex": [p[len(root) + 1:] for p in ps[:3]],
                         "kept": skipped})
        return {"names": names, "rows": rows, "total": len(hit)}

    def junk_names_set(self, lines):
        """Liste speichern und neu pruefen."""
        names = save_junk_names(lines)
        self.scan()
        return {"names": names, "started": True}

    def status(self):
        root = _pn(self.root() or "").rstrip("/")
        rel = lambda p: p[len(root) + 1:] if root and p.startswith(root + "/") else p   # noqa: E731
        with self.lock:
            return {"state": self.state, "done": self.done, "t": self.t, "err": self.err, "root": root, "pending": self.pending(), "blocked": self.blocked(),
                    "job": list(self.job) if self.job else None,
                    "n": {"muell": len(self.junk), "sonstige": len(self.other), "namen": len(self.names), "gleich": len(self.same), "belassen": len(self.held),
                          "leer": len(self.empty), "kurz": len(self.short)},
                    "leer": [{"rel": rel(d), "files": k, "ex": ex} for d, k, ex in self.empty[:LIST_MAX]],
                    "kurz": [{"path": x["path"], "rel": rel(x["file"]), "dur": x["dur"], "bpm": x["bpm"], "key": x["key"], "energy": x.get("energy", "")} for x in self.short[:LIST_MAX]],
                    "belassen": [{"path": x["path"], "rel": rel(x["file"]), "name": x["name"], "want": x["want"], "why": x.get("why", ""),
                                  "mixxx": x["mixxx"], "size": _size(x["file"]), "clash": "", "tags": x.get("tags") or {}} for x in self.held[:LIST_MAX]],
                    "gleich": [self._same_view(g, rel) for g in self.same[:LIST_MAX]],
                    "bytes": {"muell": sum(self.sizes.get(p, 0) for p in self.junk), "sonstige": sum(self.sizes.get(p, 0) for p in self.other)},
                    "muell": [{"rel": rel(p), "size": self.sizes.get(p, 0)} for p in self.junk[:LIST_MAX]],
                    "jnames": load_junk_names(),
                    "sonstige": [{"rel": rel(p), "size": self.sizes.get(p, 0)} for p in self.other[:LIST_MAX]],
                    "namen": [{"path": x["path"], "rel": rel(x["file"]), "name": x["name"], "want": x["want"], "why": x.get("why", ""),
                               "mixxx": x["mixxx"], "size": _size(x["file"]), "clash": rel(x["clash"]) if x.get("clash") else "",
                               "tags": x.get("tags") or {}}
                              for x in self.names[:LIST_MAX]]}

    # ---- Loeschen (Papierkorb) und Umbenennen ----
    def _abs(self, rel_or_abs):
        root = _pn(self.root() or "").rstrip("/")
        p = rel_or_abs if rel_or_abs.startswith("/") or os.path.isabs(rel_or_abs) else os.path.join(root, rel_or_abs)
        return _pn(os.path.normpath(p))

    def trash_files(self, items):
        """Einzelne Dateien aus muell/sonstige (relativer Pfad wie in der Liste) in den Papierkorb."""
        with self.lock:
            allowed = set(self.junk) | set(self.other)
        paths = []
        for x in items or []:
            p = self._abs(str(x))
            if p not in allowed:
                raise ValueError("Datei nicht in der Pruefliste: " + str(x)[:120])
            paths.append(p)
        bad = self.trash(paths)
        with self.lock:
            gone = {p for p in paths if not os.path.lexists(p)}
            self.junk = [p for p in self.junk if p not in gone]
            self.other = [p for p in self.other if p not in gone]
        return {"ok": not bad, "gone": len(gone)}

    def trash_dirs(self, items):
        """Leere Ordner (relativer Pfad wie in der Liste) in den Papierkorb des Mac, mit allem, was noch drin liegt (Bilder,
        Texte; keine Musik, das hat die Pruefung festgestellt). Vorher noch einmal nachsehen: liegt jetzt Musik drin, bleibt er."""
        with self.lock:
            allowed = {d for d, _k, _e in self.empty}
        paths = []
        for x in items or []:
            p = self._abs(str(x))
            if p not in allowed:
                raise ValueError("Ordner nicht in der Liste: " + str(x)[:120])
            if has_music(p):
                raise ValueError("In diesem Ordner liegt inzwischen Musik: " + str(x)[:120])
            paths.append(p)
        bad = self.trash(paths)
        with self.lock:
            gone = {p for p in paths if not os.path.lexists(p)}
            self.empty = [e for e in self.empty if e[0] not in gone]
        return {"ok": not bad, "gone": len(gone)}

    def clear_short(self, items=None):
        """BPM, Tonart und unsere geschaetzte Energie aus kurzen Stuecken loeschen (nur diese Tags, Musik bleibt; Energie von
        Mixed In Key bleibt). items = relative Pfade, None = alle."""
        import tag_edit
        import energy_level
        with self.lock:
            todo = [x for x in self.short if items is None or self._rel(x["file"]) in set(items)]
        done, bad = set(), 0
        for x in todo:
            try:
                if x.get("bpm") or x.get("key"):
                    tag_edit.write_tags(x["file"], {"bpm": "", "key": ""})
                if x.get("energy"):
                    energy_level.remove_energy_tag(x["file"])
                done.add(x["file"])
            except Exception as e:                       # noqa: BLE001  eine kaputte Datei haelt die anderen nicht auf
                bad += 1
                self.log(f"Kurze Stuecke: {x['file']}: {e}")
        with self.lock:
            self.short = [x for x in self.short if x["file"] not in done]
        self.log(f"Kurze Stuecke: BPM und Tonart aus {len(done)} Dateien entfernt")
        return {"ok": not bad, "done": len(done), "bad": bad}

    def _rel(self, p):
        root = _pn(self.root() or "").rstrip("/")
        return p[len(root) + 1:] if root and p.startswith(root + "/") else p

    def trash_all_junk(self):
        """Alle Eintraege der Liste Datenmuell in den Papierkorb, im Hintergrund mit Fortschritt."""
        with self.lock:
            if self.job:
                return False
            todo = list(self.junk)
            self.job = [0, len(todo)]

        def run():
            step = 150
            for i in range(0, len(todo), step):
                self.trash(todo[i:i + step])
                with self.lock:
                    self.job = [min(len(todo), i + step), len(todo)]
            with self.lock:
                self.junk = [p for p in self.junk if os.path.lexists(p)]
                self.job = None
            self.log(f"Dateien pruefen: Datenmuell in den Papierkorb ({len(todo)} Dateien)")
        threading.Thread(target=run, name="muell-papierkorb", daemon=True).start()
        return True

    @staticmethod
    def queue_path():
        return os.path.join(_pfad.daten(), "umbenannt", "offen.tsv")

    def _same_view(self, g, rel):
        """Gruppe gleicher Dateinamen mit Vorschlag je Datei (Wunsch 08.11.2026: "gleich beheben"). Die Datei mit dem kuerzesten
        Pfad behaelt den Namen, die anderen bekommen den Ordner (Album ohne Jahr) in Klammern, sonst (2), (3) ..."""
        files = sorted(g[1], key=lambda p: (len(p), p.lower()))
        sizes = {p: _size(p) for p in files}
        taken = set(self.index)
        out = []
        for i, p in enumerate(files):
            item = {"rel": rel(p), "file": p, "size": sizes[p], "mixxx": p in self.fmap, "keep": i == 0, "want": "",
                    "twin": sum(1 for q in files if q != p and sizes[q] == sizes[p] and sizes[p] > 0)}
            if i:
                stem, ext = os.path.splitext(os.path.basename(p))
                folder = re.sub(r"^\d{4}\s*-\s*", "", clean_part(os.path.basename(os.path.dirname(p))))
                artist_level = os.path.basename(os.path.dirname(os.path.dirname(p))).lower() in ("artists", "compilations")
                useful = folder and loose(folder) != loose(stem) and not (artist_level and loose(folder) in loose(stem))
                cands = ([f"{stem} ({folder})"] if useful else []) + [f"{stem} ({k})" for k in range(2, 50)]
                want = next((c + ext.lower() for c in cands if nkey(clean_stem(c) + ext.lower()) not in taken), "")
                if want:
                    want = clean_stem(os.path.splitext(want)[0]) + ext.lower()
                    taken.add(nkey(want))
                item["want"] = want
            out.append(item)
        return {"name": g[0], "files": out, "rels": [rel(p) for p in g[1]]}

    def rename_file(self, f, to):
        """Datei aus "Gleiche Namen" umbenennen (im selben Ordner, nie ueberschreiben, kein Name doppelt). Steht sie in Mixxx,
        kommt sie in die Warteschlange fuer den naechsten Start der Mixxx-App (Hotcues bleiben)."""
        with self.lock:
            if not any(f in g[1] for g in self.same):
                raise ValueError("Datei nicht unter Gleiche Namen")
        ext = os.path.splitext(f)[1]
        stem = clean_stem("".join(CHAR_MAP.get(c, c) for c in nfc(os.path.splitext(str(to or ""))[0])))
        if not stem:
            raise ValueError("Neuer Name leer")
        new = _pn(os.path.join(os.path.dirname(f), stem + ext.lower()))
        if os.path.lexists(new):
            raise ValueError("Es gibt schon eine Datei mit diesem Namen")
        with self.lock:
            others = [q for q in self.index.get(nkey(os.path.basename(new)), []) if nfc(q) != nfc(f)]
        if others:
            raise ValueError("Den Dateinamen gibt es schon: " + others[0])
        if not os.path.isfile(f):
            raise ValueError("Datei nicht gefunden (Stick eingesteckt?)")
        rename_any(f, new)
        mp = self.fmap.get(f)
        if mp:
            newmp = _sib(mp, os.path.basename(new))
            self._queue(mp, newmp)
            if self.renamed is not None:
                self.renamed(mp, newmp)
        with self.lock:
            old_k = nkey(os.path.basename(f))
            self.index[old_k] = [q for q in self.index.get(old_k, []) if nfc(q) != nfc(f)]
            self.index.setdefault(nkey(os.path.basename(new)), []).append(new)
            if mp:
                self.fmap[new] = self.fmap.pop(f)
            self.same = [[g[0], [q for q in g[1] if nfc(q) != nfc(f)]] for g in self.same]
            self.same = [g for g in self.same if len(g[1]) > 1]
        self.log(f"Dateien pruefen: umbenannt {os.path.basename(f)} -> {os.path.basename(new)} (gleiche Namen)")
        return {"ok": True, "new": os.path.basename(new), "mixxx": bool(mp)}

    def _queue(self, old, new):
        """Fuer Mixxx merken: beim naechsten Start der Mixxx-App traegt mixxx_umbenennen.sh den neuen Pfad ein (Hotcues bleiben)."""
        if "\t" in old + new or "\n" in old + new:
            return
        try:
            q = self.queue_path()
            os.makedirs(os.path.dirname(q), exist_ok=True)
            with open(q, "a", encoding="utf-8") as fh:
                fh.write(old + "\t" + new + "\n")
        except OSError as e:
            self.log(f"Dateien pruefen: Umbenennung fuer Mixxx nicht gemerkt: {e}")

    def pending(self):
        """Wie viele Umbenennungen warten auf den naechsten Start der Mixxx-App?"""
        try:
            with open(self.queue_path(), encoding="utf-8") as fh:
                return sum(1 for line in fh if line.strip())
        except OSError:
            return 0

    def blocked(self):
        """Hat macOS das Schreiben in die Mixxx-Datenbank verboten (mixxx_umbenennen.sh legt dann gesperrt.txt ab)?"""
        try:
            with open(os.path.join(os.path.dirname(self.queue_path()), "gesperrt.txt"), encoding="utf-8") as fh:
                return fh.read().strip()[:300] or "gesperrt"
        except OSError:
            return ""

    @staticmethod
    def kept_path():
        return os.path.join(_pfad.daten(), "pruefen", "belassen.json")

    def kept(self):
        """Lieder, deren Dateiname bleiben soll ("So lassen"): kommen in der Namensliste nicht wieder."""
        try:
            with open(self.kept_path(), encoding="utf-8") as fh:
                d = json.load(fh)
            return set(x for x in d if isinstance(x, str)) if isinstance(d, list) else set()
        except (OSError, ValueError):
            return set()

    def keep(self, path):
        with self.lock:
            if not any(x["path"] == path for x in self.names):
                raise ValueError("Lied nicht in der Namensliste")
            self.held += [x for x in self.names if x["path"] == path]
            self.names = [x for x in self.names if x["path"] != path]
        k = self.kept()
        k.add(path)
        q = self.kept_path()
        os.makedirs(os.path.dirname(q), exist_ok=True)
        with open(q + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(sorted(k), fh, ensure_ascii=False)
        os.replace(q + ".tmp", q)
        return {"ok": True}

    def unkeep(self, path):
        """Doch nicht so lassen (Reiter "So gelassen"): wieder in die Namensliste, Vorschlag neu (nie doppelt)."""
        k = self.kept()
        if path not in k:
            raise ValueError("Lied ist nicht unter So gelassen")
        k.discard(path)
        q = self.kept_path()
        with open(q + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(sorted(k), fh, ensure_ascii=False)
        os.replace(q + ".tmp", q)
        with self.lock:
            back = [x for x in self.held if x["path"] == path]
            self.held = [x for x in self.held if x["path"] != path]
            self.names = sorted(self.names + back, key=lambda x: x["file"].lower())
        if not back:
            return {"ok": True, "item": None}
        return self.retag(path)

    def retag(self, path):
        """Tags eines Liedes aus der Namensliste wurden geaendert (Tag-Editor auf der Seite, Wunsch 08.11.2026): Vorschlag neu
        rechnen. Rueckgabe: der neue Eintrag fuer die Seite oder {"ok": True} (Name passt jetzt, aus der Liste)."""
        root = _pn(self.root() or "").rstrip("/")
        with self.lock:
            it = next((x for x in self.names if x["path"] == path), None)
        if it is None:
            raise ValueError("Lied nicht in der Namensliste")
        rec = next((r for r in (self.songs() or []) if r.get("path") == path), None)
        s = suggest(rec, it["file"][len(root) + 1:], self.multi.get(multi_key(it["file"], rec), "")) if rec and it["file"].startswith(root + "/") else None
        if s is None or s.get("ok"):
            with self.lock:
                self.names = [x for x in self.names if x["path"] != path]
            return {"ok": True, "gone": True}
        if s["want"]:
            stem, ext = os.path.splitext(s["want"])
            with self.lock:
                taken = lambda c: [q for q in self.index.get(nkey(c), []) if q != it["file"]] + \
                    [x["file"] for x in self.names if x["path"] != path and nkey(x["want"] or "") == nkey(c)]
                cands = [s["want"]] + ([f"{stem} ({s['album']})" + ext] if s.get("album") else []) + [f"{stem} ({i}){ext}" for i in range(2, 50)]
                want = next((c for c in cands if not taken(c)), "")
                clash = taken(s["want"])
        else:
            want, clash = "", []
        with self.lock:
            it.update(want=want, why=s.get("why", ""), name=s["name"], clash=clash[0] if clash else "", tags=file_tags(it["file"]))
        rel = it["file"][len(root) + 1:]
        return {"ok": True, "gone": False, "item": {"path": path, "rel": rel, "name": it["name"], "want": want, "why": it["why"],
                                                     "mixxx": it["mixxx"], "size": _size(it["file"]),
                                                     "clash": clash[0][len(root) + 1:] if clash else "", "tags": it["tags"]}}

    def rename(self, path, to):
        """Lied (Mixxx-Pfad aus der Namensliste) im selben Ordner umbenennen. Nie ueberschreiben, Endung bleibt."""
        with self.lock:
            it = next((x for x in self.names if x["path"] == path), None)
        if it is None:
            raise ValueError("Lied nicht in der Namensliste")
        f = it["file"]
        ext = os.path.splitext(f)[1]
        stem = clean_stem("".join(CHAR_MAP.get(c, c) for c in nfc(os.path.splitext(str(to or ""))[0])))   # auch selbst getippte: Namensregeln
        if not stem:
            raise ValueError("Neuer Name leer")
        new = _pn(os.path.join(os.path.dirname(f), stem + ext.lower()))
        if os.path.lexists(new) and os.path.normcase(new) != os.path.normcase(f):
            raise ValueError("Es gibt schon eine Datei mit diesem Namen")
        with self.lock:                                    # kein Name doppelt im ganzen Musikordner (Wunsch 08.11.2026)
            others = [q for q in self.index.get(nkey(os.path.basename(new)), []) if nfc(q) != nfc(f)]
        if others:
            raise ValueError("Den Dateinamen gibt es schon: " + others[0] + " – bitte unterscheiden (z. B. Album in Klammern)")
        if not os.path.isfile(f):
            raise ValueError("Datei nicht gefunden (Stick eingesteckt?)")
        rename_any(f, new)
        newpath = _sib(path, os.path.basename(new))     # Pfad in der Bibliothek (wie Mixxx ihn kennt)
        self._queue(path, newpath)
        with self.lock:
            old_k = nkey(os.path.basename(f))
            self.index[old_k] = [q for q in self.index.get(old_k, []) if nfc(q) != nfc(f)]
            self.index.setdefault(nkey(os.path.basename(new)), []).append(new)
            self.names = [x for x in self.names if x["path"] != path]
        if self.renamed is not None:                       # Merkzettel nach Pfad mitnehmen (Wunsch 08.11.2026), Ordnerliste neu
            self.renamed(path, newpath)
        self.log(f"Dateien pruefen: umbenannt {os.path.basename(f)} -> {os.path.basename(new)}")
        return {"ok": True, "new": os.path.basename(new), "old_path": path, "path": newpath}
