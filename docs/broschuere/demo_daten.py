#!/usr/bin/env python3
"""
demo_daten.py - erfundene Musik-Bibliothek fuer die Broschuere (Wunsch von Markus, 14.11.2026).

Die Bildschirmfotos der Broschuere zeigen nie die echte Sammlung: Interpreten, Alben, Lieder, Cover und Bilder sind hier
erfunden (Fantasie-Namen, erzeugte Grafiken). Ergebnis ist ein Ordner, wie ihn der Pi unter shows/ fuehrt:
    _mixxx_bibliothek.json    Liedliste (wie von der Mixxx-Bruecke)
    _covers/, _covers_index.jsonl
    _interpreten/, _interpreten.json
    _favoriten.json
Aufruf (am Mac, braucht Pillow):  python3 docs/broschuere/demo_daten.py ZIELORDNER
Danach den Simulator mit S2L_SHOWS_DIR=ZIELORDNER starten (siehe build_broschuere.py).
"""
import hashlib
import io
import json
import math
import os
import random
import sys
import time

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, "..", "..", "pi"))
from showman import albums as al    # noqa: E402
from showman import artists as ar   # noqa: E402
from PIL import Image, ImageDraw, ImageFont   # noqa: E402

ROOT = "/Volumes/MUSIK/musik"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

# Interpret, Genre, Gruppe, Jahrzehnt, Energie (um), BPM (um), Farbe
ARTISTS = [
    ("Nordlicht Express", "Pop", "", 2010, 6, 118, (40, 90, 160)), ("Luna Vega", "Pop", "", 2018, 7, 124, (170, 60, 140)),
    ("Die Almrocker", "Schlager", "Après-Ski", 2015, 8, 132, (200, 70, 40)), ("Kaiserblick", "Schlager", "", 2005, 6, 120, (120, 30, 60)),
    ("Neon Pilots", "Dance", "", 2020, 8, 128, (20, 160, 170)), ("Velvet Harbor", "Rock", "", 1995, 6, 112, (80, 80, 80)),
    ("Sunny Delmar", "Pop", "", 2012, 5, 104, (230, 150, 30)), ("Glacier Twins", "Dance", "", 2019, 8, 126, (60, 120, 220)),
    ("Hüttenzauber", "Schlager", "Après-Ski", 2017, 9, 136, (180, 40, 40)), ("Mira Sol", "Chillout", "", 2016, 3, 92, (70, 150, 120)),
    ("The Paper Comets", "Rock", "", 2003, 7, 140, (150, 100, 30)), ("Bergfeuer Band", "Schlager", "", 2011, 7, 124, (140, 50, 20)),
    ("Stella Marlow", "Pop", "", 2021, 6, 110, (200, 90, 160)), ("Pixel Harbour", "Dance", "", 2022, 9, 130, (100, 40, 200)),
    ("Golden Avenue", "Pop", "Oldies", 1984, 6, 116, (200, 160, 40)), ("Frostnacht Chor", "Weihnachten", "Weihnachten", 2008, 3, 84, (40, 110, 70)),
    ("Ocean Drive Club", "Chillout", "", 2014, 4, 98, (30, 120, 150)), ("Disco Galaxis", "Dance", "Oldies", 1979, 7, 122, (210, 80, 200)),
    ("Lena Sommerfeld", "Schlager", "", 2019, 6, 118, (230, 120, 90)), ("Iron Meadow", "Rock", "", 1990, 8, 146, (60, 60, 90)),
    ("Skyline Hearts", "Pop", "", 2016, 7, 122, (90, 70, 180)), ("Tom Berger", "Pop", "", 2009, 5, 100, (120, 120, 60)),
    ("Ella Kingsley", "Pop", "", 2013, 6, 112, (190, 60, 90)), ("Gipfelstürmer", "Schlager", "Après-Ski", 2018, 9, 138, (150, 30, 30)),
]
WORDS_A = ["Sternen", "Sommer", "Mitternachts", "Gold", "Silber", "Nebel", "Feuer", "Wolken", "Nacht", "Himmel", "Sonnen", "Winter",
           "Herz", "Neon", "Gipfel", "Berg", "Hütten", "Schnee", "Morgen", "Abend", "Funkel", "Liebes", "Tanz", "Regenbogen"]
WORDS_B = ["staub", "regen", "tanz", "licht", "fieber", "glanz", "zauber", "traum", "flug", "rausch", "funken", "welle", "sturm",
           "melodie", "nacht", "party", "gold", "himmel", "feuer", "glück"]
EN_A = ["Midnight", "Golden", "Electric", "Silver", "Summer", "Wild", "Neon", "Crystal", "Endless", "Northern", "Paper", "Velvet",
        "Broken", "Secret", "Lucky", "Ocean", "City", "Purple", "Little", "Burning", "Lonely", "Dancing", "Cosmic", "Morning"]
EN_B = ["Lights", "Heart", "Highway", "Dreams", "Rain", "Fire", "Waves", "Skyline", "Echoes", "Horizon", "Stars", "Run", "Love",
        "Thunder", "Garden", "Signals", "Paradise", "Rhythm", "Memories", "Shadows", "Sunrise", "Gravity", "Satellite", "Avenue"]
USED = set()
KEYS = ["C", "Am", "G", "Em", "D", "Bm", "A", "F#m", "E", "C#m", "F", "Dm", "Bb", "Gm", "Eb", "Cm"]


def title(rng, de):
    """Erfundener Titel, jeder nur einmal."""
    for _ in range(200):
        t = rng.choice(WORDS_A) + rng.choice(WORDS_B) if de else rng.choice(EN_A) + " " + rng.choice(EN_B)
        if t not in USED:
            USED.add(t)
            return t
    return t


def cover(seed, color, text):
    """Erzeugtes Cover: Farbverlauf, Kreise, Titel. Keine echten Plattencover."""
    rng = random.Random(seed)
    w = 300
    im = Image.new("RGB", (w, w), color)
    d = ImageDraw.Draw(im)
    r2, g2, b2 = [max(0, min(255, c + rng.randint(-90, 90))) for c in color]
    for y in range(w):
        f = y / w
        d.line([(0, y), (w, y)], fill=(int(color[0] * (1 - f) + r2 * f), int(color[1] * (1 - f) + g2 * f), int(color[2] * (1 - f) + b2 * f)))
    for _ in range(rng.randint(2, 5)):
        x, y, rr = rng.randint(0, w), rng.randint(0, w), rng.randint(30, 140)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=(255, 255, 255), width=rng.randint(1, 4))
    for i in range(0, w, 6):                                  # kleine Wellenform unten
        h = int(20 * abs(math.sin(i * 0.11 + seed % 7)) + rng.randint(0, 12))
        d.line([(i, w - 30 - h), (i, w - 30 + h)], fill=(255, 255, 255), width=3)
    f = ImageFont.truetype(FONT, 26)
    d.text((18, 18), text[:22], fill=(255, 255, 255), font=f)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def portrait(seed, color, name):
    """Erzeugtes Interpretenbild: Silhouette auf Farbe (keine echten Fotos)."""
    w = 400
    im = Image.new("RGB", (w, w), tuple(int(c * 0.6) for c in color))
    d = ImageDraw.Draw(im)
    for rr in range(w, 0, -8):
        k = rr / w
        d.ellipse([w / 2 - rr, w * 0.35 - rr, w / 2 + rr, w * 0.35 + rr], fill=tuple(int(c * (0.6 + 0.6 * (1 - k))) % 256 for c in color))
    sil = (25, 25, 35)
    d.ellipse([w * 0.36, w * 0.22, w * 0.64, w * 0.52], fill=sil)
    d.ellipse([w * 0.18, w * 0.55, w * 0.82, w * 1.15], fill=sil)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def build(dest):
    rng = random.Random(14112026)
    os.makedirs(os.path.join(dest, "_covers"), exist_ok=True)
    os.makedirs(os.path.join(dest, "_interpreten"), exist_ok=True)
    lib, cov_idx, art_idx = [], [], {}
    now = int(time.time())
    for ai, (artist, genre, grp, dec, lvl, bpm, col) in enumerate(ARTISTS):
        de = genre in ("Schlager", "Weihnachten")
        for alb_i in range(rng.randint(1, 3)):
            album = title(rng, de) if alb_i else ("Best of " + artist if rng.random() < 0.3 else title(rng, de))
            year = dec + rng.randint(0, 6)
            cv = cover(ai * 10 + alb_i, col, album)
            fp = "%d:%s" % (len(cv), hashlib.sha1(cv).hexdigest()[:16])
            with open(os.path.join(dest, "_covers", fp.replace(":", "_") + ".jpg"), "wb") as f:
                f.write(cv)
            for tr in range(1, rng.randint(4, 11)):
                name = title(rng, de)
                path = "%s/%s/%s/%s/%02d %s.mp3" % (ROOT, genre.upper(), artist, album, tr, name)
                kid = rng.randint(1, 24)
                feat = rng.random() < 0.08
                lib.append([artist + " - " + name, round(rng.uniform(150, 290), 1), artist + (" feat. Luna Vega" if feat and artist != "Luna Vega" else ""),
                            name, round(bpm + rng.uniform(-6, 6), 1), rng.choice(KEYS), kid, genre, max(1, min(9, lvl + rng.randint(-1, 1))),
                            os.path.basename(path), rng.randint(0, 8), 1, path, 320, 0, 0, 0, 0, 0, 0,
                            [rng.choice(["Party", "Hochzeit", "Warm-up"])] if rng.random() < 0.4 else [], [], year, album, str(tr),
                            grp, now - rng.randint(0, 400) * 86400, round(rng.uniform(-12, -7), 1), round(rng.uniform(-2, 0.5), 1), 0,
                            rng.randint(0, 40), now - rng.randint(0, 200) * 86400])
                cov_idx.append([path, fp])
        k = ar.key(artist)
        if ai % 5 != 4:                                        # ein paar ohne Bild, wie im echten Leben
            with open(os.path.join(dest, "_interpreten", k + ".jpg"), "wb") as f:
                f.write(portrait(ai, col, artist))
            art_idx[k] = {"name": artist, "src": "eigen", "t": now}
    with open(os.path.join(dest, "_mixxx_bibliothek.json"), "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False)
    with open(os.path.join(dest, "_covers_index.jsonl"), "w", encoding="utf-8") as f:
        for p, fp in cov_idx:
            f.write(json.dumps([p, fp], ensure_ascii=False) + "\n")
    with open(os.path.join(dest, "_interpreten.json"), "w", encoding="utf-8") as f:
        json.dump(art_idx, f, ensure_ascii=False)
    # Infos zu Interpreten und Alben vorab (erfunden): die Seiten fragen dann nie im Internet nach (dort gibt es echte
    # Kuenstler mit zufaellig gleichem Namen, deren Alben und Fotos nicht in die Broschuere gehoeren)
    os.makedirs(os.path.join(dest, "_interpreten_info"), exist_ok=True)
    os.makedirs(os.path.join(dest, "_alben_info"), exist_ok=True)
    for ai, (artist, genre, grp, dec, lvl, bpm, col) in enumerate(ARTISTS):
        bio = ("%s ist ein erfundener Interpret aus der Demo-Bibliothek des Light-Butlers. Hier steht sonst der Lebenslauf von "
               "TheAudioDB: Herkunft, Stil, erste Erfolge und Alben, meist auf Deutsch." % artist)
        with open(os.path.join(dest, "_interpreten_info", ar.key(artist) + ".json"), "w", encoding="utf-8") as f:
            json.dump({"t": now, "bio": bio, "lang": "de", "born": 0, "formed": dec - 3, "died": 0, "place": "Fantasien",
                       "genre": genre, "style": "", "web": "", "members": 4 if " " in artist else 1, "albums": [], "n_albums": 0}, f, ensure_ascii=False)
    for x in lib:
        k = al.album_key(x[23], x[12])
        with open(os.path.join(dest, "_alben_info", k + ".json"), "w", encoding="utf-8") as f:
            json.dump({"t": now, "found": False, "date": "", "label": "", "nb": 0, "tracks": [], "cover": "", "title": "", "artist": ""}, f)
    # Raumplan der Demo (8 x 5 m, Geraete sauber verteilt), Datei raum.json im Demo-Ordner (S2L_ROOM_FILE)
    it = lambda x, y, rot=0.0, ln=0.0: {"x": x, "y": y, "rot": rot, "len": ln}
    room = {"v": 1, "w": 8.0, "h": 5.0, "guess": False, "items": {
        "docooler_1": it(0.25, 4.3), "docooler_2": it(0.25, 3.5), "docooler_5": it(0.25, 1.5), "docooler_6": it(0.25, 0.7),
        "vega": it(0.5, 2.9), "laser": it(0.5, 2.1),
        "rgbuv_11": it(2.4, 0.3), "rgbuv_10": it(3.4, 0.3), "rgbuv_8": it(5.4, 0.3), "rgbuv_7": it(6.4, 0.3), "nanoleaf": it(4.4, 0.35),
        "uv_bar": it(4.0, 2.5), "hazer": it(7.6, 2.5), "eyes": it(7.6, 0.4), "derby": it(6.6, 4.6), "par": it(7.6, 4.6),
        "effektband": it(4.0, 4.95, 0.0, 8.0), "effektband#2": it(4.0, 0.05, 0.0, 8.0), "theke": it(6.9, 3.6, 0.0, 1.6),
        "couchtisch": it(2.6, 2.5, 90.0, 1.2)}}
    with open(os.path.join(dest, "raum.json"), "w", encoding="utf-8") as f:
        json.dump(room, f)
    songs = [x[12] for x in lib]
    favs = {"song": {p: {"t": now} for p in rng.sample(songs, 9)}, "artist": {ar.key("Luna Vega"): {"name": "Luna Vega", "t": now},
                                                                             ar.key("Neon Pilots"): {"name": "Neon Pilots", "t": now}},
            "album": {}, "genre": {"Dance": {"t": now}, "Schlager": {"t": now}}}
    x = next(x for x in lib if x[2] == "Die Almrocker")
    favs["album"][al.album_key(x[23], x[12])] = {"name": x[23], "artist": "Die Almrocker", "t": now}
    with open(os.path.join(dest, "_favoriten.json"), "w", encoding="utf-8") as f:
        json.dump(favs, f, ensure_ascii=False)
    return len(lib)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(build(sys.argv[1]), "Lieder")
