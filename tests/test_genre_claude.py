"""Genre-Editor: Claude schlaegt fuer Genres ohne Ziel eins aus der Hausliste vor (Wunsch 11.11.2026). Ohne Netz: die Anfrage
wird geprueft und die Antwort nachgestellt."""
import io
import json
import os
import sys

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
from showman import genre_ai, assistant  # noqa: E402
from showman.api import ShowManager      # noqa: E402

house = ["Pop", "Schlager", "Rock", "Dance"]
items = [{"g": "80s", "n": 12, "ex": [["Nena", "99 Luftballons"], ["Falco", "Rock Me Amadeus"]], "path": "/geheim/x.mp3"},
         {"g": "Polka", "n": 2, "ex": [["Slavko Avsenik", "Trompetenecho"]]}]
body = genre_ai.request(house, items, assistant.MODEL)
user = json.loads(body["messages"][0]["content"])
check(body["model"] == "claude-opus-5-5" and body["output_config"]["format"]["type"] == "json_schema" and body["fallbacks"] == "default",
      "Anfrage: aktuelles Modell, feste Antwortform, Ausweichmodell")
check(user["hausliste"] == house and user["genres"][0] == {"genre": "80s", "lieder": 12, "beispiele": ["Nena - 99 Luftballons", "Falco - Rock Me Amadeus"]},
      "an Claude: Hausliste, Genres, Zahl und Beispiele")
check("/geheim" not in body["messages"][0]["content"] and "path" not in body["messages"][0]["content"], "keine Pfade an Anthropic")

ans = {"map": [{"genre": "80s", "to": "pop", "why": "Neue Deutsche Welle, Pop der 80er"},
               {"genre": "Polka", "to": "Volksmusik", "why": "erfunden"},
               {"genre": "Techno", "to": "Dance", "why": "nicht gefragt"},
               {"genre": "80s", "to": "Rock", "why": "doppelt"}]}
m = genre_ai.apply(house, items, ans)
check(m == {"80s": {"to": "Pop", "why": "Neue Deutsche Welle, Pop der 80er"}, "Polka": {"to": "", "why": "erfunden"}},
      "Antwort geprueft: nur gefragte Genres, Ziel nur aus der Hausliste (Schreibweise der Hausliste), erstes zaehlt: " + json.dumps(m))
try:
    genre_ai.apply(house, items, "kaputt")
    check(False, "unlesbare Antwort abgelehnt")
except ValueError:
    check(True, "unlesbare Antwort abgelehnt")


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


sent = {}


def opener(req, timeout=0):
    sent["body"] = json.loads(req.data.decode())
    sent["key"] = req.headers.get("X-api-key")
    return Resp(json.dumps({"content": [{"type": "text", "text": json.dumps(ans)}], "stop_reason": "end_turn",
                            "usage": {"input_tokens": 1000, "output_tokens": 200}}).encode())


class Fake:
    claude_opener = staticmethod(opener)
    spent = 0.0

    def _claude_key(self):
        return "sk-test"

    def _add_spent(self, c):
        Fake.spent += c

    def _spent(self):
        return round(Fake.spent, 4)


r = ShowManager.genre_ai(Fake(), house, items)
check(r["map"]["80s"]["to"] == "Pop" and r["cost_usd"] > 0 and sent["key"] == "sk-test", "Pi fragt mit dem Schluessel, Kosten gezaehlt")
for bad in (([], items), (house, [])):
    try:
        ShowManager.genre_ai(Fake(), *bad)
        check(False, "abgelehnt")
    except ValueError:
        check(True, "ohne Hausliste oder Genres abgelehnt")

js = open(os.path.join(ROOT, "pi", "static", "sm", "genres.js"), encoding="utf-8").read()
check("op: 'genre_ai'" in js and "askClaude(" in js and "🤖 Claude fragen" in js and "ai && ai.to ? ai.to : ''" in js,
      "Genre-Editor: Knopf, Vorschlag vorgewaehlt, geschrieben erst mit Uebernehmen")
check("data-sopen=" in js and "function sugSongs(" in js and "data-tagp=" in js and "/cover?p=" in js
      and "tagedit.js" in open(os.path.join(ROOT, "pi", "static", "sm", "genres.html"), encoding="utf-8").read(),
      "Vorschlaege: Liederliste mit Cover, Anhoeren und Tag (Wunsch 11.11.2026)")
te = open(os.path.join(ROOT, "pi", "static", "sm", "tagedit.js"), encoding="utf-8").read()
check("id=\"tg_gsel\"" in te and "/genres?house=1" in te and '"house" in q' in open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read(),
      "Tag-Fenster: Genre-Auswahl aus der Hausliste")
# Claude-Knopf je Lied (Wunsch 11.11.2026), im Genre-Editor und im Tag-Fenster
songs = [{"artist": "Die Kolibris", "title": "Kleiner Kolibri", "genre": "Other", "path": "/geheim/k.mp3"},
         {"artist": "Gala", "title": "Freed From Desire", "genre": ""}]
body2 = genre_ai.song_request(house, songs, assistant.MODEL)
u2 = json.loads(body2["messages"][0]["content"])
check(u2["lieder"][0] == {"i": 0, "interpret": "Die Kolibris", "titel": "Kleiner Kolibri", "genre_jetzt": "Other"} and "/geheim" not in body2["messages"][0]["content"]
      and body2["output_config"]["format"]["type"] == "json_schema", "je Lied: nur Interpret, Titel, jetziges Genre an Claude, keine Pfade")
a2 = {"map": [{"i": 0, "to": "schlager", "why": "Volkstuemlicher Schlager"}, {"i": 1, "to": "Eurodance", "why": "nicht in der Hausliste"},
              {"i": 0, "to": "Rock", "why": "doppelt"}, {"i": 9, "to": "Pop", "why": "gibt es nicht"}, {"i": True, "to": "Pop", "why": "kein int"}]}
check(genre_ai.song_apply(house, songs, a2) == [{"to": "Schlager", "why": "Volkstuemlicher Schlager"}, {"to": "", "why": "nicht in der Hausliste"}],
      "Antwort geprueft: nur Lieder der Anfrage, Ziel nur aus der Hausliste, erstes zaehlt")
ans = a2
r2 = ShowManager.genre_song_ai(Fake(), house, songs)
check(r2["songs"][0]["to"] == "Schlager" and r2["cost_usd"] > 0, "Pi fragt Claude je Lied, Kosten gezaehlt")
for bad in (([], songs), (house, []), (house, "x")):
    try:
        ShowManager.genre_song_ai(Fake(), *bad)
        check(False, "abgelehnt")
    except ValueError:
        check(True, "ohne Hausliste oder Lieder abgelehnt")
api_src = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('op == "genre_song_ai"' in api_src, "Befehl genre_song_ai")
check("data-sai=" in js and "data-sput=" in js and "op: 'genre_song_ai'" in js and "+ aiBtn(x, g) +" in js and "aiBtn(x, g.g)" in js and "aiBtn(x, x.now || '')" in js, "Genre-Editor: Claude-Knopf bei jedem Lied (Vorschlaege, Genre-Liste, Fuellen), Eintragen erst auf Klick")
check('id="tg_gai"' in te and "op: 'genre_song_ai'" in te and "nicht in deiner Hausliste" in te, "Tag-Fenster: Claude-Knopf neben dem Genre, markiert Genres ausserhalb der Hausliste")

check("'zusammenlegen mit …', null, house)" in js and "only && only.length ? only.slice().sort(abc)" in js,
      "Vorschlaege: zusammenlegen mit … bietet nur die Genres der Hausliste an (Wunsch 11.11.2026)")
check("function neverBox()" in js and "data-unnever=" in js and "on: false" in js and "+ neverBox();" in js,
      "Vorschlaege: nicht vorgeschlagene Genres gesammelt, wieder vorschlagen geht (Wunsch 11.11.2026)")
check("genreSel('id=\"edpick\"', '', house.length ? 'oder aus der Hausliste wählen …'" in js and "'oder aus der Liste wählen …', null, house)" in js,
      "Umbenennen/Zusammenlegen: Auswahl aus der Hausliste (Wunsch 11.11.2026)")
css = open(os.path.join(ROOT, "pi", "static", "sm", "sm.css"), encoding="utf-8").read()
gh = open(os.path.join(ROOT, "pi", "static", "sm", "genres.html"), encoding="utf-8").read()
i_g = te.index("k === 'genre' ?")
check('<div class="tggenre">' in te[i_g:i_g + 900] and "tg_gaimsg" in te[i_g:i_g + 900] and ".tggenre { display: flex; flex-direction: column;" in css
      and "b.textContent = '…'" not in te,
      "Tag-Fenster: Genre, Hausliste, Claude und Antwort in einer Zelle untereinander (Raster verrutscht nicht, Fehlerbericht 11.11.2026)")
check("max-width: 1150px" not in gh, "Genre-Editor ueber die ganze Breite (Wunsch 11.11.2026)")
care = open(os.path.join(ROOT, "pi", "static", "sm", "care.js"), encoding="utf-8").read()
ge = open(os.path.join(ROOT, "mac", "mixxx_bridge", "genre_edit.py"), encoding="utf-8").read()
check('"fill_empty": sum(1 for x in fc if not x["now"])' in ge and "gn.suggest.filter(s => s.to).length + fillEmpty" in care and "mit „Other“'" not in care,
      "Datenpflege: 'Other' gilt als vergebenes Genre, offen sind nur Lieder ohne Genre (Wunsch 11.11.2026)")
gh2 = open(os.path.join(ROOT, "pi", "static", "sm", "genres.html"), encoding="utf-8").read()
i_f = js.index("function drawFill()")
fill_js = js[i_f:i_f + 3000]
check('<span class="wsel">\' + genreSel(' in fill_js.replace("'", "\\'") or "'<span class=\"w\"><span class=\"wsel\">' + genreSel(" in fill_js,
      "Genre fuellen: Auswahl und 🤖 in einer Zelle (Raster verrutscht nicht, Fehlerbericht 12.11.2026)")
check('class="fcv cvimg"' in fill_js and "minmax(260px, 1.1fr)" in gh2 and 'id="fsticky"' in gh2 and "#tfill .box { width: auto;" in gh2
      and '<option value="leer" selected>nur ohne Genre</option>' in gh2 and "function fgoUpdate()" in js,
      "Genre fuellen: Cover, breite Vorschlags-Spalte, Leiste ueber die ganze Breite, Schreiben-Knopf unten fest, standardmaessig nur ohne Genre")
finish("test_genre_claude")
