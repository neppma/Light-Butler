"""Genre-Stile: Das Genre aus Mixxx gibt in AUTO einen Stil vor (Farbpalette, Tempo der Bewegung, Energie, weisse
Akzent-Blitze). Die feste Zuordnung steht hier, eigene Zuordnungen aus dem Panel in genre_styles.json."""
import json
import os
import threading

# Farbpalette in AUTO (None = nach Stimmung wie bisher), Tempo der Bewegung, Zuschlag zur Energie und ob weisse
# Akzent-Blitze erlaubt sind (Ein Stil macht Blitze nur seltener, nie haeufiger), uv False = UV-Licht bleibt aus.
STYLES = {
    "weihnachten": {"colors": [0.0, 0.33, 0.11], "mv": 0.6, "energy": -0.05, "flash": False, "uv": False},   # rot, gruen, gold
    "club":        {"colors": None, "mv": 1.0, "energy": 0.0, "flash": True},
    "party":       {"colors": [0.88, 0.52, 0.15, 0.07], "mv": 1.25, "energy": 0.0, "flash": True},   # magenta, cyan, gelb, orange
    "rock":        {"colors": [0.0, 0.07, 0.10], "mv": 1.15, "energy": 0.03, "flash": True},      # rot, orange, bernstein
    "ruhig":       {"colors": [0.60, 0.75, 0.46], "mv": 0.5, "energy": -0.10, "flash": False},    # blau, violett, tuerkis
}
OFF = "aus"                                                   # eigene Zuordnung "kein Stil" (wie bisher)
GENRE_STYLE = {g: s for s, gs in {
    "weihnachten": ("weihnachten", "christmas", "xmas", "holiday"),   # Holiday: so nennt Shazam Weihnachtslieder
    "club": ("edm", "house", "techno", "trance", "dance", "electronic", "electro"),
    "party": ("pop", "austropop", "schlager", "neue deutsche welle", "latin", "reggae", "oldies", "volksmusik"),
    "rock": ("rock", "metal", "punk", "blues", "funk"),
    "ruhig": ("klassik", "classical", "classical other", "ambient", "meditation", "soundtrack", "jazz", "musical",
              "soul", "folk", "synthesizer"),
}.items() for g in gs}
MAX_GENRES = 200


def norm(genre):
    """Schluessel eines Genres: "House; Other" zaehlt als House, Gross-/Kleinschreibung egal."""
    return str(genre or "").split(";")[0].strip().lower()[:40]


def genre_style(genre):
    """Fester Stil zum Genre, sonst None."""
    return GENRE_STYLE.get(norm(genre))


class GenreStyles:
    """Eigene Zuordnung Genre -> Stil (genre_styles.json). path=None: nur im Speicher (Tests)."""

    def __init__(self, path="genre_styles.json"):
        self.path, self.lock, self.own = path, threading.Lock(), {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                for g, s in (d.items() if isinstance(d, dict) else ()):
                    if norm(g) and (s in STYLES or s == OFF):
                        self.own[norm(g)] = s
            except (OSError, ValueError) as e:
                print(f"Hinweis: {os.path.basename(path)} nicht lesbar ({e}), es gilt die feste Zuordnung")

    def style(self, genre):
        """Stil fuer ein Genre: eigene Zuordnung vor der festen, "aus" = kein Stil."""
        k = norm(genre)
        if not k:
            return None
        with self.lock:
            s = self.own.get(k)
        if s == OFF:
            return None
        return s or GENRE_STYLE.get(k)

    def style_of_groups(self, grp):
        """Stil aus der Gruppe im Tag (13.11.2026: "Weihnachten" ist ein Anlass, kein Genre): eine Gruppe mit eigener Zuordnung
        (Genre-Stile im Panel) oder eine Weihnachtsgruppe; sonst None. Andere Gruppen aendern nichts am Licht."""
        for t in str(grp or "").split(";"):
            k = norm(t)
            if not k:
                continue
            with self.lock:
                own = self.own.get(k)
            if own == OFF:
                continue
            if own:
                return own
            if GENRE_STYLE.get(k) == "weihnachten":
                return "weihnachten"
        return None

    def set(self, genre, style):
        """Eigene Zuordnung setzen; style "" (oder gleich der festen) = zurueck auf die feste Zuordnung."""
        k = norm(genre)
        if not k:
            raise ValueError("Kein Genre angegeben")
        if style not in STYLES and style not in (OFF, ""):
            raise ValueError("Unbekannter Stil")
        with self.lock:
            if not style or style == GENRE_STYLE.get(k) or (style == OFF and k not in GENRE_STYLE):
                self.own.pop(k, None)
            elif len(self.own) < MAX_GENRES or k in self.own:
                self.own[k] = style
            else:
                raise ValueError("Zu viele eigene Zuordnungen")
        self._save()

    def table(self, seen=()):
        """Zeilen fuer das Panel: alle Genres aus Mixxx (mit Anzahl Lieder), dazu die festen und die eigenen."""
        rows, have = [], set()
        for name, n in seen:
            k = norm(name)
            if k and k not in have:
                have.add(k)
                rows.append({"genre": str(name)[:40], "n": int(n)})
        for k in list(GENRE_STYLE) + sorted(self.own):
            if k not in have:
                have.add(k)
                rows.append({"genre": k, "n": 0})
        with self.lock:
            own = dict(self.own)
        rows.sort(key=lambda r: (r["n"] == 0, r["genre"].casefold()))   # alphabetisch (Wunsch 08.11.2026), deine Genres zuerst
        for r in rows:
            k = norm(r["genre"])
            r["default"] = GENRE_STYLE.get(k) or ""
            r["own"] = own.get(k, "")
            r["style"] = self.style(r["genre"]) or ""
        return rows

    def _save(self):
        if not self.path:
            return
        with self.lock:
            data = dict(self.own)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.path)
