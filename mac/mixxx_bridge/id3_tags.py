"""
id3_tags.py - ID3v2-Kopf einer MP3 lesen und neu schreiben, ohne die Musik anzufassen (nur Python, kein mutagen).

Gemeinsam fuer die geschaetzte Energiestufe (energy_level.py, TXXX "EnergyLevel") und die geschaetzte Tonart
(key_estimate.py, TKEY). Nur ID3v2.3 und v2.4 ohne Sonderformen (Unsynchronisation, erweiterter Kopf, Fussteil).
Passt der neue Kopf in den alten (Fuellbytes), wird nur der Kopf ueberschrieben, sonst die Datei neu geschrieben
(Kopie im selben Ordner, dann ersetzt). Die Musik bleibt Byte fuer Byte gleich, darum auch der Fingerabdruck
(audio_fingerprint rechnet ohne Tags).
"""
import os
import re


def _syncsafe(b):
    return (b[0] & 0x7F) << 21 | (b[1] & 0x7F) << 14 | (b[2] & 0x7F) << 7 | (b[3] & 0x7F)


def text_body(value):
    """Textrahmen (TKEY, TIT2 ...) in Latin-1."""
    return b"\x00" + value.encode("latin-1")


def txxx_body(desc, value):
    return b"\x00" + desc.encode("latin-1") + b"\x00" + value.encode("latin-1")


def frame(fid, body, ver):
    n = len(body)
    size = bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F]) if ver == 4 else n.to_bytes(4, "big")
    return fid + size + b"\x00\x00" + body


def _decode(enc, raw):
    try:
        if enc == 1:
            return raw.decode("utf-16", "replace")
        if enc == 2:
            return raw.decode("utf-16-be", "replace")
        return raw.decode("utf-8" if enc == 3 else "latin-1", "replace")
    except (UnicodeDecodeError, LookupError):
        return ""


def _split0(enc, rest):
    """Bis zur ersten Null (bei UTF-16 zwei Nullbytes): (Text-Bytes, Rest)."""
    if enc in (1, 2):
        i = 0
        while i + 1 < len(rest) and rest[i:i + 2] != b"\x00\x00":
            i += 2
        return rest[:i], rest[i + 2:]
    a, _, b = rest.partition(b"\x00")
    return a, b


def txxx_desc(body):
    """Beschreibung eines TXXX-Rahmens, klein geschrieben."""
    if not body:
        return ""
    return _decode(body[0], _split0(body[0], body[1:])[0]).lower()


def text_value(body):
    """Inhalt eines Textrahmens (erster Wert), ohne Nullen am Ende."""
    if not body:
        return ""
    return _decode(body[0], _split0(body[0], body[1:])[0]).strip()


def read(path):
    """(ver, alte Groesse, [(fid, flags, roh, inhalt)]) oder ein Grund (Text), warum es nicht geht. Ohne Kopf: (3, 0, [])."""
    with open(path, "rb") as f:
        head = f.read(10)
        if head[:3] != b"ID3":
            return 3, 0, []
        if len(head) < 10:
            return "Datei zu kurz"
        ver, flags = head[3], head[5]
        if ver not in (3, 4):
            return f"ID3v2.{ver} wird nicht unterstuetzt"
        if flags & 0xD0 or flags & 0x40:
            return "ID3-Kopf mit Sonderformen"
        old_size = _syncsafe(head[6:10])
        tag = f.read(old_size)
    if len(tag) < old_size:
        return "ID3-Kopf abgeschnitten"
    frames, pos = [], 0
    while pos + 10 <= len(tag):
        fid = tag[pos:pos + 4]
        if not fid.strip(b"\x00"):
            break
        if not all(48 <= c <= 57 or 65 <= c <= 90 for c in fid):
            return "ID3-Kopf nicht lesbar"
        raw = tag[pos + 4:pos + 8]
        fsize = _syncsafe(raw) if ver == 4 else int.from_bytes(raw, "big")
        if fsize <= 0 or pos + 10 + fsize > len(tag):
            return "ID3-Kopf nicht lesbar"
        frames.append((fid, tag[pos + 8:pos + 10], tag[pos:pos + 10 + fsize], tag[pos + 10:pos + 10 + fsize]))
        pos += 10 + fsize
    return ver, old_size, frames


def _changed(path):
    """Fuer Mixxx merken: diese Datei hat neue Tags (changed_log, Playlist "Light-Butler geaenderte Tags")."""
    try:
        import changed_log
        changed_log.note(path)
    except ImportError:                                       # alte Installation ohne changed_log.py
        pass


def write(path, ver, old_size, data, pad=2048):
    """Neuen Kopf (alle Rahmen als Bytes) schreiben; die Musik dahinter bleibt unveraendert."""
    def header(size):
        return b"ID3" + bytes([ver, 0, 0, (size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
    if old_size and len(data) <= old_size:                    # passt in den alten Kopf: nur ihn ueberschreiben
        with open(path, "r+b") as f:
            f.write(header(old_size) + data + b"\x00" * (old_size - len(data)))
        _changed(path)
        return
    size = len(data) + pad
    tmp = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".lb-tmp")
    try:
        with open(path, "rb") as src, open(tmp, "wb") as dst:
            src.seek(10 + old_size if old_size else 0)
            dst.write(header(size) + data + b"\x00" * pad)
            while True:
                b = src.read(1 << 20)
                if not b:
                    break
                dst.write(b)
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(tmp, path)
        _changed(path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def read_text(path, fid):
    """Wert eines Textrahmens (z. B. b"TKEY") oder ''. Liest nur den Kopf."""
    try:
        r = read(path)
    except OSError:
        return ""
    if isinstance(r, str):
        return ""
    for f, fl, _raw, body in r[2]:
        if f == fid and fl == b"\x00\x00":
            return text_value(body)
    return ""


# ---- Genre als Nummer (ID3v1-Liste mit den Winamp-Erweiterungen, wie Mixxx/TagLib), Fehlerbericht 09.11.2026: "(148)" -------
GENRES = ('Blues', 'Classic Rock', 'Country', 'Dance', 'Disco', 'Funk', 'Grunge', 'Hip-Hop', 'Jazz', 'Metal', 'New Age',
          'Oldies', 'Other', 'Pop', 'R&B', 'Rap', 'Reggae', 'Rock', 'Techno', 'Industrial', 'Alternative', 'Ska',
          'Death Metal', 'Pranks', 'Soundtrack', 'Euro-Techno', 'Ambient', 'Trip-Hop', 'Vocal', 'Jazz+Funk', 'Fusion',
          'Trance', 'Classical', 'Instrumental', 'Acid', 'House', 'Game', 'Sound Clip', 'Gospel', 'Noise',
          'Alternative Rock', 'Bass', 'Soul', 'Punk', 'Space', 'Meditative', 'Instrumental Pop', 'Instrumental Rock',
          'Ethnic', 'Gothic', 'Darkwave', 'Techno-Industrial', 'Electronic', 'Pop-Folk', 'Eurodance', 'Dream',
          'Southern Rock', 'Comedy', 'Cult', 'Gangsta', 'Top 40', 'Christian Rap', 'Pop/Funk', 'Jungle', 'Native American',
          'Cabaret', 'New Wave', 'Psychedelic', 'Rave', 'Showtunes', 'Trailer', 'Lo-Fi', 'Tribal', 'Acid Punk', 'Acid Jazz',
          'Polka', 'Retro', 'Musical', 'Rock & Roll', 'Hard Rock', 'Folk', 'Folk-Rock', 'National Folk', 'Swing',
          'Fast Fusion', 'Bebop', 'Latin', 'Revival', 'Celtic', 'Bluegrass', 'Avantgarde', 'Gothic Rock',
          'Progressive Rock', 'Psychedelic Rock', 'Symphonic Rock', 'Slow Rock', 'Big Band', 'Chorus', 'Easy Listening',
          'Acoustic', 'Humour', 'Speech', 'Chanson', 'Opera', 'Chamber Music', 'Sonata', 'Symphony', 'Booty Bass', 'Primus',
          'Porn Groove', 'Satire', 'Slow Jam', 'Club', 'Tango', 'Samba', 'Folklore', 'Ballad', 'Power Ballad',
          'Rhythmic Soul', 'Freestyle', 'Duet', 'Punk Rock', 'Drum Solo', 'A Cappella', 'Euro-House', 'Dance Hall', 'Goa',
          'Drum & Bass', 'Club-House', 'Hardcore Techno', 'Terror', 'Indie', 'BritPop', 'Negerpunk', 'Polsk Punk', 'Beat',
          'Christian Gangsta Rap', 'Heavy Metal', 'Black Metal', 'Crossover', 'Contemporary Christian', 'Christian Rock',
          'Merengue', 'Salsa', 'Thrash Metal', 'Anime', 'JPop', 'Synthpop', 'Abstract', 'Art Rock', 'Baroque', 'Bhangra',
          'Big Beat', 'Breakbeat', 'Chillout', 'Downtempo', 'Dub', 'EBM', 'Eclectic', 'Electro', 'Electroclash', 'Emo',
          'Experimental', 'Garage', 'Global', 'IDM', 'Illbient', 'Industro-Goth', 'Jam Band', 'Krautrock', 'Leftfield',
          'Lounge', 'Math Rock', 'New Romantic', 'Nu-Breakz', 'Post-Punk', 'Post-Rock', 'Psytrance', 'Shoegaze',
          'Space Rock', 'Trop Rock', 'World Music', 'Neoclassical', 'Audiobook', 'Audio Theatre', 'Neue Deutsche Welle',
          'Podcast', 'Indie Rock', 'G-Funk', 'Dubstep', 'Garage Rock', 'Psybient')


def genre_name(g):
    """Genre-Feld lesbar: "(148)" -> "Abstract", "(17)Rock" -> "Rock", "17" -> "Rock", "(RX)" -> "Remix", "(CR)" -> "Cover";
    alles andere bleibt. Unbekannte Nummern: ""."""
    g = str(g or "").strip()
    m = re.fullmatch(r"\((\d{1,3})\)(.*)", g) or re.fullmatch(r"(\d{1,3})()", g)
    if m:
        rest = m.group(2).strip()
        if rest:
            return rest
        n = int(m.group(1))
        return GENRES[n] if n < len(GENRES) else ""
    if g in ("(RX)", "RX"):
        return "Remix"
    if g in ("(CR)", "CR"):
        return "Cover"
    return g


def genre_is_number(g):
    """Steht das Genre nur als Nummer in der Datei (alte Schreibweise)?"""
    return bool(re.fullmatch(r"\(\d{1,3}\)|\d{1,3}", str(g or "").strip()))
