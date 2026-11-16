"""
tag_edit.py - MP3-Tags lesen, bearbeiten und Vorschlaege aus dem Internet holen (Wunsch von Markus, 07.11.2026).

Fuer das Fenster "Tag bearbeiten" in der Musik-Datenbank. Lesen und Schreiben ueber id3_tags (nur Python, kein mutagen): die
Musik bleibt Byte fuer Byte gleich, darum auch der Fingerabdruck (Shows, Kurven und Cover passen weiter). Bearbeitbar sind
die ueblichen Felder (FIELDS) und das Cover; alle anderen Rahmen zeigt das Fenster nur an und schreibt sie unveraendert zurueck.
Ein leeres Feld entfernt den Rahmen.

Vorschlaege nur auf Knopfdruck, ins Internet gehen nur Interpret, Titel und Laenge, nie die Musik:
  - MusicBrainz (frei, privat ohne Schluessel, hoechstens eine Anfrage pro Sekunde): Album, Jahr, Track, Album-Interpret
  - iTunes-Suche von Apple (ohne Schluessel): Album, Jahr, Genre, Cover bis 1200 Pixel
  - Deezer (ohne Schluessel): Album, Cover
  - Cover Art Archive (MusicBrainz und Internet Archive): Cover zur MusicBrainz-Veroeffentlichung
Ein Cover holt der Mac nur von diesen Adressen (COVER_HOSTS), geprueft als JPEG oder PNG, hoechstens 5 MB.
Mixxx sieht die Aenderungen erst, wenn es die Tags neu einliest. Aufs Licht wirkt das nicht.
"""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import id3_tags as it

# Feld -> (Rahmen, Bezeichnung). "TXXX:..." = eigenes Textfeld, "COMM" = Kommentar ohne Beschreibung
FIELDS = (("title", "TIT2", "Titel"), ("artist", "TPE1", "Interpret"), ("album", "TALB", "Album"),
          ("albumartist", "TPE2", "Album-Interpret"), ("year", "YEAR", "Jahr"), ("track", "TRCK", "Track"),
          ("disc", "TPOS", "CD"), ("genre", "TCON", "Genre"), ("bpm", "TBPM", "BPM"), ("key", "TKEY", "Tonart"),
          ("comment", "COMM", "Kommentar"), ("composer", "TCOM", "Komponist"), ("publisher", "TPUB", "Verlag"),
          ("isrc", "TSRC", "ISRC"), ("energy", "TXXX:EnergyLevel", "Energie"), ("coversrc", "TXXX:CoverSource", "Cover-Quelle"),
          ("grouping", "TIT1", "Gruppe"), ("imported", "TXXX:Importdatum", "Importdatum"))       # Gruppe/Grouping (Wunsch 10.11.2026: "Après-Ski"; Mixed In Key laesst sie, Mixxx zeigt sie)
COVER_OWN = "Eigenes Bild"              # Vermerk bei einem Bild vom eigenen Rechner (Fenster Tag bearbeiten, "Bild vom Rechner", 09.11.2026)
COVER_MADE = "Light-Butler (erzeugt)"   # Vermerk bei einem selbst erzeugten Cover (Fenster Tag bearbeiten, "Cover erzeugen")
FRAME_NAMES = {"TIT1": "Gruppe", "TIT3": "Untertitel", "TOPE": "Original-Interpret", "TEXT": "Texter", "TLEN": "Laenge (ms)",
               "TENC": "Kodiert von", "TSSE": "Kodier-Programm", "TCOP": "Copyright", "TLAN": "Sprache", "TMED": "Medium",
               "TORY": "Original-Jahr", "TDOR": "Original-Datum", "TPE3": "Dirigent", "TPE4": "Remix", "USLT": "Liedtext",
               "POPM": "Bewertung", "PRIV": "Privat", "UFID": "Kennung", "GEOB": "Objekt", "WXXX": "Link", "PCNT": "Zaehler",
               "TDRL": "Veroeffentlicht", "TDTG": "Getaggt", "TSOA": "Sortierung Album", "TSOP": "Sortierung Interpret",
               "TSOT": "Sortierung Titel", "TSO2": "Sortierung Album-Interpret", "TCMP": "Kompilation", "TDAT": "Datum",
               "TIME": "Uhrzeit", "TRDA": "Aufnahmedatum", "TFLT": "Dateityp", "TOAL": "Original-Album"}
MAX_TEXT = 2000
POPM_EMAIL = b"Windows Media Player 9 Series"   # Bewertung wie Windows/Mp3tag/MusicBee; Favorit (Herz, 14.11.2026) = 5 Sterne (255)
POPM_FAV = 224                                   # ab hier gilt eine Bewertung als 5 Sterne


def popm_rating(body):
    """Bewertung 0..255 aus einem POPM-Rahmen (E-Mail, Null, Bewertung, Zaehler)."""
    i = body.find(b"\x00")
    return body[i + 1] if 0 <= i < len(body) - 1 else 0
COVER_HOSTS = ("mzstatic.com", "dzcdn.net", "coverartarchive.org", "archive.org")
COVER_MAX = 5 * 1024 * 1024
UA = "Light-Butler/1.0 (private Lichtsteuerung, https://musicbrainz.org/doc/MusicBrainz_API)"


class TagError(Exception):
    pass


def _enc_text(value, ver):
    """Text fuer einen Rahmen: v2.4 UTF-8, v2.3 UTF-16 mit BOM (Umlaute, alle Zeichen)."""
    return (b"\x03" + value.encode("utf-8")) if ver == 4 else (b"\x01" + value.encode("utf-16"))


def _pair(desc, value, ver):
    """Kodierung, Beschreibung, Null, Wert (TXXX, und mit Sprache dazwischen COMM): v2.4 UTF-8, v2.3 UTF-16 mit BOM."""
    if ver == 4:
        return b"\x03" + desc.encode("utf-8") + b"\x00" + value.encode("utf-8")
    return b"\x01" + desc.encode("utf-16") + b"\x00\x00" + value.encode("utf-16")


def _comm_parts(body):
    """COMM: (Sprache, Beschreibung, Text)."""
    if len(body) < 4:
        return "", "", ""
    enc, lang, rest = body[0], body[1:4].decode("latin-1", "replace"), body[4:]
    desc, text = it._split0(enc, rest)
    return lang, it._decode(enc, desc), it._decode(enc, text).rstrip("\x00")


def _txxx_value(body):
    enc = body[0] if body else 0
    _desc, rest = it._split0(enc, body[1:])
    return it._decode(enc, rest).rstrip("\x00")


def _apic_info(body):
    """APIC: (MIME, Bildtyp, Bytes)."""
    if not body:
        return "", 0, b""
    enc = body[0]
    mime, rest = body[1:].split(b"\x00", 1) if b"\x00" in body[1:] else (body[1:], b"")
    ptype, rest = (rest[0] if rest else 0), rest[1:]
    _desc, data = it._split0(enc, rest)
    return mime.decode("latin-1", "replace"), ptype, data


def _field_frame(field):
    return next((f for k, f, _l in FIELDS if k == field), None)


def read_tags(path):
    """{"ver", "fields": {Feld: Wert}, "labels", "other": [{id, name, value}], "cover": {mime, size, type} oder None}."""
    r = it.read(path)
    if isinstance(r, str):
        raise TagError(r)
    ver, _size, frames = r
    out, other, cover = {k: "" for k, _f, _l in FIELDS}, [], None
    fav = False
    year_ids = ("TDRC", "TYER") if ver == 4 else ("TYER", "TDRC")
    for fid, fl, _raw, body in frames:
        name = fid.decode("latin-1")
        if fl != b"\x00\x00":                              # komprimiert, verschluesselt ...: nur anzeigen
            other.append({"id": name, "name": FRAME_NAMES.get(name, name), "value": "(besonderes Format)"})
            continue
        if fid == b"APIC":
            mime, ptype, data = _apic_info(body)
            if cover is None or ptype == 3:
                cover = {"mime": mime, "size": len(data), "type": ptype}
            continue
        if fid == b"POPM" and popm_rating(body) >= POPM_FAV:
            fav = True
        if fid == b"COMM":
            lang, desc, text = _comm_parts(body)
            if not desc and not out["comment"]:
                out["comment"] = text[:MAX_TEXT]
            else:
                other.append({"id": "COMM", "name": "Kommentar " + (desc or lang), "value": text[:300]})
            continue
        if fid == b"TXXX":
            desc = it.txxx_desc(body)
            if desc == "energylevel":
                out["energy"] = _txxx_value(body)[:20]
            elif desc == "coversource":
                out["coversrc"] = _txxx_value(body)[:80]
            elif desc == "importdatum":                    # von der Import-Seite (11.11.2026)
                out["imported"] = _txxx_value(body)[:20]
            else:
                other.append({"id": "TXXX", "name": "Eigenes Feld " + desc, "value": _txxx_value(body)[:300]})
            continue
        if name in year_ids:
            if not out["year"]:
                out["year"] = it.text_value(body)[:20]
            continue
        f = next((k for k, fr, _l in FIELDS if fr == name), None)
        if f and name.startswith("T"):
            out[f] = it.text_value(body)[:MAX_TEXT]
            continue
        val = it.text_value(body)[:300] if name.startswith("T") or name == "USLT" else f"{len(body)} Byte"
        if name == "USLT":
            val = _comm_parts(body)[2][:300]
        other.append({"id": name, "name": FRAME_NAMES.get(name, name), "value": val})
    gnum = out["genre"] if it.genre_is_number(out["genre"]) else ""
    if gnum:                                               # "(148)" -> "Abstract" (wie Mixxx); beim Schreiben kommt der Name hinein
        out["genre"] = it.genre_name(gnum)
    return {"ver": ver, "fields": out, "labels": {k: l for k, _f, l in FIELDS}, "other": other, "cover": cover, "genre_num": gnum, "fav": fav}


def is_image(data):
    return isinstance(data, (bytes, bytearray)) and (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n")


def write_tags(path, fields=None, cover=None, remove_cover=False, fav=None):
    """Felder (nur die bekannten, leer = entfernen) und Cover (Bytes, JPEG/PNG) schreiben; alles andere bleibt, wie es war.
    fav True/False: Favorit als Bewertung 5 Sterne (POPM) setzen oder alle 5-Sterne-Bewertungen entfernen, None = unveraendert.
    Rueckgabe: neue read_tags(path)."""
    fields = {k: v for k, v in (fields or {}).items() if _field_frame(k)}
    for k, v in fields.items():
        if not isinstance(v, str) or len(v) > MAX_TEXT or "\x00" in v:
            raise TagError(f"Feld {k} ungueltig")
    if cover is not None and (not is_image(cover) or len(cover) > COVER_MAX):
        raise TagError("Cover ist kein JPEG oder PNG (oder zu gross)")
    if not path.lower().endswith(".mp3"):
        raise TagError("keine MP3")
    r = it.read(path)
    if isinstance(r, str):
        raise TagError(r)
    ver, old_size, frames = r
    year_fid = b"TDRC" if ver == 4 else b"TYER"
    drop, add = set(), []
    for k, v in fields.items():
        v = v.strip()
        fr = _field_frame(k)
        if fr == "YEAR":
            drop.update({b"TYER", b"TDRC", b"TDAT"})
            if v:
                add.append(it.frame(year_fid, _enc_text(v, ver), ver))
        elif fr == "COMM":
            drop.add("COMM")
            if v:
                pair = _pair("", v, ver)
                add.append(it.frame(b"COMM", pair[:1] + b"eng" + pair[1:], ver))
        elif fr.startswith("TXXX:"):
            desc = fr[5:]
            drop.add("TXXX:" + desc.lower())
            if v:
                add.append(it.frame(b"TXXX", _pair(desc, v, ver), ver))
        else:
            drop.add(fr.encode("latin-1"))
            if v:
                add.append(it.frame(fr.encode("latin-1"), _enc_text(v, ver), ver))
    if cover is not None or remove_cover:
        drop.add(b"APIC")
        if cover is not None:
            mime = b"image/png" if cover[:4] == b"\x89PNG" else b"image/jpeg"
            add.append(it.frame(b"APIC", b"\x00" + mime + b"\x00" + b"\x03" + b"\x00" + bytes(cover), ver))

    if fav is not None:
        drop_fav = True
        if fav:
            add.append(it.frame(b"POPM", POPM_EMAIL + b"\x00" + bytes([255]) + b"\x00\x00\x00\x00", ver))
    else:
        drop_fav = False

    def keep(fid, fl, body):
        if fid in drop:
            return False
        if drop_fav and fid == b"POPM" and fl == b"\x00\x00" and (popm_rating(body) >= POPM_FAV or body.startswith(POPM_EMAIL + b"\x00")):
            return False
        if fid == b"COMM" and "COMM" in drop and fl == b"\x00\x00" and not _comm_parts(body)[1]:
            return False
        if fid == b"TXXX" and fl == b"\x00\x00" and ("TXXX:" + it.txxx_desc(body)) in drop:
            return False
        return True
    data = b"".join(raw for fid, fl, raw, body in frames if keep(fid, fl, body)) + b"".join(add)
    it.write(path, ver, old_size, data)
    return read_tags(path)


# ---- Vorschlaege aus dem Internet ----------------------------------------------------------------------------------
_mb_lock = threading.Lock()
_mb_last = [0.0]


def _get_json(url, opener, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with opener(req, timeout=timeout) as r:
        return json.loads(r.read(2_000_000).decode("utf-8", "replace"))


def _clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _q(s):
    """Fuer die Lucene-Suche von MusicBrainz: Sonderzeichen entschaerfen."""
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", _clean(s))


def musicbrainz(artist, title, dur, opener=urllib.request.urlopen, sleep=time.sleep):
    """Bis zu 6 Vorschlaege [{source, title, artist, album, albumartist, year, track, disc, mbid}], beste zuerst."""
    if not _clean(title):
        return []
    q = f'recording:"{_q(title)}"' + (f' AND artist:"{_q(artist)}"' if _clean(artist) else "")
    url = "https://musicbrainz.org/ws/2/recording?fmt=json&limit=50&query=" + urllib.parse.quote(q)
    with _mb_lock:                                        # hoechstens eine Anfrage pro Sekunde (Regel von MusicBrainz)
        wait = 1.1 - (time.time() - _mb_last[0])
        if wait > 0:
            sleep(wait)
        try:
            d = _get_json(url, opener)
        finally:
            _mb_last[0] = time.time()
    out = []
    recs = d.get("recordings") or []
    near = [r for r in recs if not (dur and r.get("length") and abs(r["length"] / 1000.0 - dur) > 6)]
    for rec in near or recs:                              # keine passende Laenge (anderer Mix): dann alle, die Wahl bleibt bei dir
        artist_ = "".join((c.get("name") or "") + (c.get("joinphrase") or "") for c in rec.get("artist-credit") or [])
        for rel in rec.get("releases") or []:
            media = (rel.get("media") or [{}])[0]
            tr = (media.get("track") or [{}])[0]
            rg = rel.get("release-group") or {}
            aa = "".join((c.get("name") or "") + (c.get("joinphrase") or "") for c in rel.get("artist-credit") or []) or artist_
            out.append({"source": "MusicBrainz", "title": _clean(rec.get("title")), "artist": _clean(artist_), "album": _clean(rel.get("title")),
                        "albumartist": _clean(aa), "year": str(rel.get("date") or "")[:4],
                        "track": (f"{tr.get('number')}/{media.get('track-count')}" if tr.get("number") and media.get("track-count") else str(tr.get("number") or "")),
                        "disc": str(media.get("position") or "") if (rel.get("media") and len(rel.get("media")) > 1) else "",
                        "mbid": str(rel.get("id") or ""), "kind": str(rg.get("primary-type") or ""), "score": int(rec.get("score") or 0),
                        "extra": bool(set(rg.get("secondary-types") or []) & {"Compilation", "Live", "DJ-mix", "Remix", "Mixtape/Street"})})
        if len(out) >= 400:
            break
    rank = {"Album": 0, "EP": 1, "Single": 2}
    want = _clean(artist).lower()

    def order(x):                                         # eigenes Album des Interpreten vor Samplern (Various Artists), dann frueheste
        own = bool(want) and want in x["albumartist"].lower()
        return (0 if own else 1, x["extra"], rank.get(x["kind"], 3), -x["score"], x["year"] or "9999")
    out.sort(key=order)
    seen, best = set(), []
    for x in out:
        k = x["album"].lower()                            # dasselbe Album mehrmals (Neuauflagen): nur die erste, beste Ausgabe
        if k not in seen:
            seen.add(k)
            best.append(x)
    for x in best:
        x.pop("extra", None)
    return best[:6]


def itunes(artist, title, opener=urllib.request.urlopen):
    """Vorschlaege von Apple: [{source, title, artist, album, year, genre, track, cover}]."""
    term = _clean(f"{artist} {title}")
    if not term:
        return []
    d = _get_json("https://itunes.apple.com/search?media=music&entity=song&limit=8&term=" + urllib.parse.quote(term), opener)
    out = []
    for x in d.get("results") or []:
        art = str(x.get("artworkUrl100") or "")
        out.append({"source": "iTunes", "title": _clean(x.get("trackName")), "artist": _clean(x.get("artistName")),
                    "album": _clean(x.get("collectionName")), "year": str(x.get("releaseDate") or "")[:4], "genre": _clean(x.get("primaryGenreName")),
                    "track": f"{x.get('trackNumber')}/{x.get('trackCount')}" if x.get("trackNumber") and x.get("trackCount") else "",
                    "cover": art.replace("100x100bb", "600x600bb") if art else ""})
    return out


def deezer(artist, title, opener=urllib.request.urlopen):
    """Vorschlaege von Deezer: [{source, title, artist, album, cover}]."""
    if not _clean(title):
        return []
    q = (f'artist:"{_clean(artist)}" ' if _clean(artist) else "") + f'track:"{_clean(title)}"'
    data = _get_json("https://api.deezer.com/search?limit=8&q=" + urllib.parse.quote(q), opener).get("data") or []
    if not data:                                          # genaue Suche findet nichts: freie Suche, nur passende Interpreten
        a = _clean(artist).lower()
        data = [x for x in _get_json("https://api.deezer.com/search?limit=15&q=" + urllib.parse.quote(_clean(f"{artist} {title}")), opener).get("data") or []
                if not a or a in str((x.get("artist") or {}).get("name") or "").lower()][:8]
    out = []
    for x in data:
        al, ar = x.get("album") or {}, x.get("artist") or {}
        out.append({"source": "Deezer", "title": _clean(x.get("title")), "artist": _clean(ar.get("name")), "album": _clean(al.get("title")),
                    "cover": str(al.get("cover_xl") or al.get("cover_big") or "")})
    return out


def lookup(artist, title, dur=0.0, opener=urllib.request.urlopen, sleep=time.sleep):
    """Alle Quellen nacheinander, Fehler je Quelle still: {"suggest": [...], "covers": [{url, source, album}], "errors": [...]}."""
    sug, covers, errors = [], [], []
    for name, fn in (("MusicBrainz", lambda: musicbrainz(artist, title, dur, opener, sleep)),
                     ("iTunes", lambda: itunes(artist, title, opener)), ("Deezer", lambda: deezer(artist, title, opener))):
        try:
            res = fn()
        except Exception as e:                            # noqa: BLE001  eine Quelle faellt aus: die anderen gelten
            errors.append(f"{name}: {str(e)[:80]}")
            continue
        sug.extend(res)
        if name == "MusicBrainz":
            for x in res[:3]:
                if x.get("mbid"):
                    covers.append({"url": f"https://coverartarchive.org/release/{x['mbid']}/front-500", "source": "Cover Art Archive", "album": x["album"]})
        for x in res:
            if x.get("cover") and all(c["url"] != x["cover"] for c in covers):
                covers.append({"url": x["cover"], "source": name, "album": x.get("album") or ""})
    return {"suggest": sug, "covers": covers[:12], "errors": errors}


def cover_allowed(url):
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    h = (u.hostname or "").lower()
    return u.scheme == "https" and any(h == d or h.endswith("." + d) for d in COVER_HOSTS)


def fetch_cover(url, opener=urllib.request.urlopen, sleep=time.sleep, tries=3):
    """Cover von einer erlaubten Adresse holen (auch nach Weiterleitung nur erlaubte), geprueft. Bytes.
    Serverfehler (5xx, keine Verbindung) noch zweimal versuchen: das Cover Art Archive antwortet manchmal mit 500
    (Fehlerbericht 07.11.2026, "Alicia Keys - Fallin'": beim naechsten Klick ging es)."""
    if not cover_allowed(url):
        raise TagError("Cover nur von iTunes, Deezer oder dem Cover Art Archive")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for k in range(tries):
        try:
            with opener(req, timeout=20) as r:
                final = getattr(r, "geturl", lambda: url)()
                if not cover_allowed(final):
                    raise TagError("Cover-Adresse nicht erlaubt")
                data = r.read(COVER_MAX + 1)
            break
        except urllib.error.HTTPError as e:
            if e.code < 500 or k == tries - 1:
                raise TagError(f"Cover-Server antwortet mit Fehler {e.code}" + (", bitte später nochmal" if e.code >= 500 else "")) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if k == tries - 1:
                raise TagError(f"Cover-Server nicht erreichbar ({str(getattr(e, 'reason', e))[:60]}), bitte später nochmal") from None
        sleep(2.0 * (k + 1))
    if len(data) > COVER_MAX or not is_image(data):
        raise TagError("kein Bild (JPEG oder PNG) bekommen")
    return data
