"""Genre-Editor: Claude schlaegt fuer Genres ohne Ziel (selten, unbekannt, etwa "80s") ein Genre aus der Hausliste vor
(Wunsch 11.11.2026). Reine Funktionen ohne Netz; gefragt wird ueber assistant.ask_claude (Schluessel in claude.json, Kosten in
claude_kosten.json). An Anthropic gehen nur die Hausliste, die Genres und je Genre Zahl und ein paar Beispiele (Interpret, Titel),
keine Pfade, keine Musik. Die Antwort gilt als ungeprueft: nur Genres aus der Anfrage, nur Ziele aus der Hausliste (oder leer).
Geschrieben wird nichts: der Vorschlag erscheint im Genre-Editor, uebernommen wird erst auf Klick (wie die anderen Vorschlaege).
"""
import json
import re

MAX_GENRES = 80
MAX_EX = 5

SYSTEM = ("Du ordnest Musik-Genres aus MP3-Tags einer Hausliste von Genres zu. Fuer jedes Genre aus 'genres' waehlst du genau ein "
          "Genre aus 'hausliste' (exakt so geschrieben wie dort), das am besten passt, oder einen leeren Text, wenn keins passt oder du "
          "unsicher bist. Nutze die Beispiele (Interpret - Titel), um zu verstehen, was gemeint ist. 'why' ist ein kurzer deutscher "
          "Grund (hoechstens 12 Woerter). Erfinde keine neuen Genres.")


def _clean(s, n):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def request(house, items, model, effort="low"):
    """house: [Genre]; items: [{g, n, ex: [[Interpret, Titel], ...]}]."""
    hs = [_clean(h, 40) for h in house if _clean(h, 40)][:200]
    gs = []
    for it in items[:MAX_GENRES]:
        g = _clean(it.get("g"), 60)
        if not g:
            continue
        ex = [" - ".join(_clean(x, 60) for x in e[:2]) for e in (it.get("ex") or [])[:MAX_EX] if isinstance(e, (list, tuple))]
        gs.append({"genre": g, "lieder": int(it.get("n") or 0), "beispiele": ex})
    schema = {"type": "object", "additionalProperties": False, "required": ["map"],
              "properties": {"map": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["genre", "to", "why"],
                                                                 "properties": {"genre": {"type": "string"}, "to": {"type": "string"}, "why": {"type": "string"}}}}}}
    user = {"hausliste": hs, "genres": gs}
    return {"model": model, "max_tokens": 8000, "system": SYSTEM,
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            "fallbacks": "default", "messages": [{"role": "user", "content": json.dumps(user, ensure_ascii=False)}]}


def apply(house, items, answer):
    """Antwort pruefen: {Genre: {to, why}} nur fuer gefragte Genres, Ziel nur aus der Hausliste (Schreibweise der Hausliste)."""
    if not isinstance(answer, dict):
        raise ValueError("Claude: Antwort nicht lesbar")
    asked = {_clean(it.get("g"), 60).casefold(): _clean(it.get("g"), 60) for it in items[:MAX_GENRES] if _clean(it.get("g"), 60)}
    hk = {_clean(h, 40).casefold(): _clean(h, 40) for h in house if _clean(h, 40)}
    out = {}
    for m in answer.get("map") or []:
        if not isinstance(m, dict):
            continue
        g = asked.get(_clean(m.get("genre"), 60).casefold())
        if not g or g in out:
            continue
        to = hk.get(_clean(m.get("to"), 40).casefold(), "")
        if to and to.casefold() == g.casefold():
            to = ""
        out[g] = {"to": to, "why": _clean(m.get("why"), 160)}
    return out


# ---- einzelne Lieder (Wunsch 11.11.2026: Claude-Knopf je Lied im Genre-Editor) --------------------------------------------
MAX_SONGS = 20

SONG_SYSTEM = ("Du ordnest einzelne Lieder einem Genre aus einer Hausliste zu. Fuer jedes Lied aus 'lieder' (Interpret, Titel, "
               "jetziges Genre aus dem Tag, das falsch oder leer sein kann) waehlst du genau ein Genre aus 'hausliste' (exakt so "
               "geschrieben wie dort), das am besten passt, oder einen leeren Text, wenn du das Lied nicht kennst oder unsicher bist. "
               "'i' ist die Nummer des Liedes aus der Anfrage. 'why' ist ein kurzer deutscher Grund (hoechstens 12 Woerter). "
               "Erfinde keine neuen Genres.")


def song_request(house, songs, model, effort="low"):
    """songs: [{artist, title, genre}] (keine Pfade)."""
    hs = [_clean(h, 40) for h in house if _clean(h, 40)][:200]
    ls = [{"i": i, "interpret": _clean(s.get("artist"), 80), "titel": _clean(s.get("title"), 120), "genre_jetzt": _clean(s.get("genre"), 40)}
          for i, s in enumerate(songs[:MAX_SONGS]) if isinstance(s, dict)]
    schema = {"type": "object", "additionalProperties": False, "required": ["map"],
              "properties": {"map": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["i", "to", "why"],
                                                                 "properties": {"i": {"type": "integer"}, "to": {"type": "string"}, "why": {"type": "string"}}}}}}
    return {"model": model, "max_tokens": 4000, "system": SONG_SYSTEM,
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            "fallbacks": "default", "messages": [{"role": "user", "content": json.dumps({"hausliste": hs, "lieder": ls}, ensure_ascii=False)}]}


def song_apply(house, songs, answer):
    """Antwort pruefen: [{to, why}] in der Reihenfolge der Anfrage, Ziel nur aus der Hausliste (Schreibweise der Hausliste)."""
    if not isinstance(answer, dict):
        raise ValueError("Claude: Antwort nicht lesbar")
    n = min(len(songs), MAX_SONGS)
    hk = {_clean(h, 40).casefold(): _clean(h, 40) for h in house if _clean(h, 40)}
    out = [{"to": "", "why": ""} for _ in range(n)]
    seen = set()
    for m in answer.get("map") or []:
        if not isinstance(m, dict) or not isinstance(m.get("i"), int) or isinstance(m.get("i"), bool):
            continue
        i = m["i"]
        if not 0 <= i < n or i in seen:
            continue
        seen.add(i)
        out[i] = {"to": hk.get(_clean(m.get("to"), 40).casefold(), ""), "why": _clean(m.get("why"), 160)}
    return out
