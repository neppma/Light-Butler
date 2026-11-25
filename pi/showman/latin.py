"""
latin.py - Liedtexte nur in lateinischer Schrift (Wunsch von Markus 24.11.2026): Zeilen in arabischer, chinesischer,
kyrillischer oder anderer Schrift waren im Panel, auf der Matrix und ueber die Schnittstelle nicht lesbar.

Erlaubt: lateinische Buchstaben samt Umlauten und Akzenten (ae oe ue ss e-Akut ...), Ziffern, Satzzeichen, Leerzeichen und
die ueblichen Zeichen wie & + - ' " ( ). Eine Zeile, deren Buchstaben ueberwiegend nicht lateinisch sind, wird leer (die
Zeit bleibt, damit die Zeile davor richtig endet); einzelne fremde Zeichen in einer sonst lateinischen Zeile fallen weg,
ebenso Emojis und Bildzeichen. Nur Anzeige, aufs Licht wirkt Liedtext nie. Gefiltert wird beim Anzeigen, gespeichert bleibt
der ganze Text: mit der Einstellung lyrics_latin aus (Haken) erscheint wieder alles.
"""
import unicodedata

MAX_FOREIGN = 0.3        # mehr als dieser Anteil der Buchstaben nicht lateinisch: Zeile faellt weg
ENABLED = True           # Einstellung lyrics_latin (Show setzt das je Bild); aus = alles unveraendert


def _latin(ch):
    try:
        return "LATIN" in unicodedata.name(ch)
    except ValueError:
        return False


def line(text):
    """Eine Zeile nur mit lateinischer Schrift, "" wenn sie ueberwiegend in einer anderen Schrift steht."""
    s = str(text or "")
    if not ENABLED:
        return s
    letters = [ch for ch in s if unicodedata.category(ch).startswith("L")]
    if letters:
        foreign = sum(1 for ch in letters if not _latin(ch))
        if foreign / len(letters) > MAX_FOREIGN:
            return ""
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith("L"):
            if _latin(ch):
                out.append(ch)
        elif cat.startswith(("N", "P", "Z")) or cat == "Sc" or (cat.startswith("S") and ord(ch) < 0x2000):
            if cat.startswith("N") and ord(ch) > 0x2000 and not ch.isascii():
                continue                                  # Ziffern fremder Schriften
            out.append(" " if cat.startswith("Z") else ch)
    return " ".join("".join(out).split())


def lines(items):
    """[[Zeit, Text], ...] mit gefilterten Texten (Zeiten bleiben). Bleibt keine Zeile mit Text, dann [] (wie kein Liedtext)."""
    if not ENABLED:
        return [list(x) for x in items]
    out = [[t, line(x)] for t, x in items]
    return out if any(x for _, x in out) else []


def plain(text):
    """Reiner Text: jede Zeile gefiltert, Zeilen die ganz wegfallen verschwinden (Leerzeilen zwischen Strophen bleiben)."""
    if not ENABLED:
        return str(text or "")
    out = []
    for raw in str(text or "").splitlines():
        if not raw.strip():
            out.append("")
            continue
        x = line(raw)
        if x:
            out.append(x)
    return "\n".join(out).strip("\n")
