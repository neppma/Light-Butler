"""Auto-Tagger (Wunsch von Markus, 07.11.2026): Lieder ohne Cover im Hintergrund vorrecherchieren (Internetsuche, sonst
Shazam), Vorschlaege zum Abhaken; geschrieben wird nur auf Klick, vorhandene Angaben bleiben, nur ergaenzt."""
import json
import os
import random
import sys
import tempfile
import time
import urllib.error
import urllib.request

from _common import ROOT, check, finish

BRIDGE = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BRIDGE)
import auto_tag as at       # noqa: E402
import id3_tags as it       # noqa: E402
import music_serve as ms    # noqa: E402
import tag_edit as te       # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_autotag_")
AUDIO = bytes(random.Random(6).getrandbits(8) for _ in range(20000))
JPG = b"\xff\xd8\xff\xe0" + b"bild" * 30


def mp3(name, frames):
    data = b"".join(it.frame(f, b, 3) for f, b in frames) + b"\0" * 64
    n = len(data)
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(b"ID3" + bytes([3, 0, 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127]) + data + AUDIO)
    return p


# ---- Vergleiche ----
check(at.norm("Waiting For Love (Radio Edit) feat. X") == "waiting for love" and at.norm("Café-Lied!") == "cafe lied", "Vergleich ohne Zusaetze, Akzente, Zeichen")
check(at.sim("Candy Everybody Wants", "candy everybody wants") == 1.0 and at.sim("Prisma", "Track 07") < 0.5 and at.sim("", "x") == 0.0, "Aehnlichkeit")
SUG = [{"source": "MusicBrainz", "title": "Track 07", "artist": "Hoerbuch", "album": "Kapitel"},
       {"source": "MusicBrainz", "title": "Lied", "artist": "Band", "album": "Album", "year": "1999", "mbid": "m1"},
       {"source": "iTunes", "title": "Lied", "artist": "Band", "album": "Album", "genre": "Rock"}]
check(at.best_match(SUG, "Track 07", "") is None, "ohne Interpret nie ein Treffer aus der Suche (Hoerbuch 'Track 07')")
check(at.best_match(SUG, "Lied", "Band")["album"] == "Album" and at.best_match(SUG, "Lied", "Andere") is None, "Titel und Interpret muessen passen")


# ---- Recherche ----
def lookup_for(table):
    calls = []

    def lookup(artist, title, dur):
        calls.append((artist, title))
        return table.get((artist, title), {"suggest": [], "covers": []})
    return lookup, calls


COV = {"suggest": SUG, "covers": [{"url": "https://coverartarchive.org/release/m1/front-500", "album": "Album"},
                                  {"url": "https://is1-ssl.mzstatic.com/x.jpg", "album": "Album"}]}
look, calls = lookup_for({("Band", "Lied"): COV})
fetched = []
r = at.research({"path": "/m/a", "file": "/m/a.mp3", "dur": 200, "now": {"title": "Lied", "artist": "Band", "genre": "House"}},
                lookup=look, recognize=lambda s: (_ for _ in ()).throw(AssertionError("kein Shazam noetig")), fetch=lambda u: fetched.append(u) or JPG)
check(r["source"] == "tags" and r["level"] == "gut" and r["new"] == {"album": "Album", "year": "1999"}, "Tags passen: nur fehlende Felder ergaenzt, Genre House bleibt")
check(r["cover"] == "https://coverartarchive.org/release/m1/front-500" and fetched == [r["cover"]], "Cover zum gefundenen Album, vorher probehalber geholt")


def flaky(u):
    if "coverartarchive" in u:
        raise te.TagError("kein Bild")
    return JPG


check(at.pick_cover(COV, SUG[1], flaky) == "https://is1-ssl.mzstatic.com/x.jpg", "Cover Art Archive hat keins: das naechste")
look2, calls2 = lookup_for({("", "track 07"): {"suggest": SUG, "covers": []}, ("Band", "Lied"): COV})
sz = {"kind": "ok", "song": {"title": "Lied", "artist": "Band", "genre": "Rock"}}
r = at.research({"path": "/m/b", "file": "/m/Track 07.mp3", "dur": 200, "now": {"title": "track 07"}}, lookup=look2, recognize=lambda s: sz, fetch=lambda u: JPG)
check(r["source"] == "shazam" and r["level"] == "unsicher" and r["new"]["title"] == "Lied" and r["new"]["artist"] == "Band" and r["shazam"] == sz["song"],
      "Shazam erkennt ein anderes Lied als der alte Titel sagt: unsicher, Titel und Interpret korrigiert")
r = at.research({"path": "/m/c", "file": "/m/Band - Lied.mp3", "dur": 200, "now": {"title": "", "artist": ""}}, lookup=look2,
                recognize=lambda s: sz, fetch=lambda u: JPG)
check(r["level"] == "gut" and r["source"] == "tags", "ohne Tags: Interpret und Titel aus dem Dateinamen")
r = at.research({"path": "/m/d", "file": "/m/x.mp3", "dur": 200, "now": {"title": "Unbekannt", "artist": "Niemand"}},
                lookup=lambda a, t, d: {"suggest": [], "covers": []}, recognize=lambda s: {"kind": "nomatch"}, fetch=lambda u: JPG)
check(r["level"] == "nichts" and r["new"] == {} and r["cover"] == "", "nichts gefunden: Stufe nichts")
# Tags passen nicht (falscher Titel), der Dateiname schon: zweiter Versuch mit dem Dateinamen vor Shazam (Wunsch 07.11.2026)
look3, calls3 = lookup_for({("Band", "Lied"): COV})
r = at.research({"path": "/m/e", "file": "/m/07 - Album - Band - Lied.mp3", "dur": 200, "now": {"title": "Track 07", "artist": "Unbekannt"}},
                lookup=look3, recognize=lambda s: (_ for _ in ()).throw(AssertionError("Shazam nicht noetig")), fetch=lambda u: JPG)
check(r["source"] == "datei" and r["level"] == "gut" and "title" not in r["new"], "Dateiname findet das Lied: gut, ohne Shazam, Titel bleibt (nur ergaenzen)")
check(at.from_filename("/x/13 - Sunshine Feeling - 2 Eivissa - 2 Eivissa (Mega Mix).mp3") == ("2 Eivissa", "2 Eivissa (Mega Mix)")
      and at.from_filename("/x/03. Band - Song_pn.mp3") == ("Band", "Song") and at.from_filename("/x/Lied.mp3") == ("", "Lied"),
      "Dateiname: Tracknummer und Album weg, Interpret und Titel aus den letzten zwei Teilen")
r = at.research({"path": "/m/e", "file": "/m/x.mp3", "dur": 200, "now": {"title": "Unbekannt", "artist": "Niemand"}},
                lookup=lambda a, t, d: {"suggest": [], "covers": []}, recognize=None, fetch=lambda u: JPG)
check(r["level"] == "nichts" and r["shazam"] is None, "ohne Shazam (ffmpeg fehlt): nur die Suche")

# ---- Auto-Tagger: Liste, Entscheidungen, Ablage ----
a = mp3("a.mp3", [(b"TIT2", it.text_body("Lied")), (b"TPE1", it.text_body("Band")), (b"TCON", it.text_body("House"))])
b = mp3("b.mp3", [(b"TIT2", it.text_body("Mit Cover")), (b"APIC", b"\x00image/jpeg\x00\x03\x00" + JPG)])
songs = [{"path": "/m/a", "file": a, "title": "Lied", "artist": "Band", "dur": 200.0},
         {"path": "/m/b", "file": b, "title": "Mit Cover", "artist": "", "dur": 200.0},
         {"path": "/m/w", "file": os.path.join(tmp, "x.wav"), "title": "W", "artist": "", "dur": 200.0}]
base = os.path.join(tmp, "autotag")
tg = at.AutoTagger(lambda: songs, base=base, has_cover=lambda f: ms.find_cover(f) is not None)
check([s["path"] for s in tg.todo()] == ["/m/a"], "nur MP3s ohne Cover")
tg.items["/m/a"] = dict(at.research(dict(songs[0], now=te.read_tags(a)["fields"]), lookup=look, recognize=None, fetch=lambda u: JPG), state="offen")
tg.items["/m/a"].pop("path")
tg._save()
check(tg.todo() == [] and tg.status()["open"] == 1 and tg.status()["good"] == 1, "mit Vorschlag nicht nochmal")
check(at.AutoTagger(lambda: songs, base=base).items.keys() == {"/m/a"}, "Vorschlaege bleiben nach einem Neustart")
lst = tg.list()
check(lst[0]["path"] == "/m/a" and lst[0]["new"] == {"album": "Album", "year": "1999"}, "Liste fuer die Seite")
before = open(a, "rb").read()
res = tg.apply("/m/a", a, fetch=lambda u: JPG)
f = te.read_tags(a)
check(f["fields"]["album"] == "Album" and f["fields"]["genre"] == "House" and f["cover"]["size"] == len(JPG) and tg.items["/m/a"]["state"] == "erledigt",
      "Uebernehmen: Tags und Cover in die MP3, erledigt")
check(open(a, "rb").read().endswith(AUDIO) and tg.list() == [] and tg.status()["done"] == 1, "Musik gleich, Vorschlag weg")
tg.items["/m/x"] = {"state": "offen", "level": "gut", "new": {"album": "A"}, "cover": "", "now": {}}
tg.reject("/m/x")
tg.items["/m/y"] = {"state": "offen", "level": "gut", "new": {}, "cover": "", "now": {}}
tg.mark_done("/m/y")
check(tg.items["/m/x"]["state"] == "abgelehnt" and tg.items["/m/y"]["state"] == "erledigt" and tg.status()["rejected"] == 1, "Ablehnen und selbst erledigt")
tg.unreject("/m/x")
check(tg.items["/m/x"]["state"] == "offen" and tg.status()["rejected"] == 0, "Abgelehnten wieder anbieten (Reiter Abgelehnt, 11.11.2026)")
tg.reject("/m/x")
_aj = open(os.path.join(ROOT, "pi", "static", "sm", "autotag.js"), encoding="utf-8").read()
check("lv === 'rej' ? it.rej" in _aj and "op: 'unreject'" in _aj and 'data-lv="rej"' in open(os.path.join(ROOT, "pi", "static", "sm", "autotag.html"), encoding="utf-8").read()
      and "at.list(rej=True)" in open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read(), "Seite: Reiter Abgelehnt mit Wieder anbieten")
try:
    tg.apply("/m/y", a, fetch=lambda u: JPG)
    check(False, "nichts zu schreiben")
except ValueError:
    check(True, "leerer Vorschlag: nichts geschrieben")
try:
    tg.reject("/m/fremd")
    check(False, "unbekannt")
except KeyError:
    check(True, "unbekanntes Lied: Fehler")
tg.start()
check(tg.status()["on"] and tg.status()["running"], "Starten: laeuft und ist gemerkt")
tg.stop()
tg.thread.join(3)
check(not tg.status()["on"] and not at.AutoTagger(lambda: songs, base=base).on, "Anhalten bleibt nach Neustart")
check(at.AutoTagger(lambda: [], base=base).status()["shazam"] is False, "ohne Pi-Adresse und ffmpeg: kein Shazam")

# ---- Vorhoer-Server ----
c = mp3("c.mp3", [(b"TIT2", it.text_body("Lied")), (b"TPE1", it.text_body("Band"))])
srv = ms.MusicServer([c], port=0)
srv.autotag = at.AutoTagger(lambda: [], base=os.path.join(tmp, "at2"))
srv.autotag.items = {c: {"state": "offen", "level": "gut", "new": {"album": "Neu", "artist": "Neue Band"}, "cover": "", "now": {}}}
_told = []
srv.on_tags = lambda p, f: _told.append((p, f))
check(srv.start(), "Server startet")
base_url = f"http://127.0.0.1:{srv.port}"


def post(body):
    req = urllib.request.Request(base_url + "/autotag", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


with urllib.request.urlopen(base_url + "/autotag", timeout=5) as resp:
    d = json.loads(resp.read())
check(d["status"]["open"] == 1 and d["items"][0]["path"] == c, "Stand und Liste ueber den Server")
check(post({"op": "apply", "path": "/fremd.mp3"})[0] == 404, "Uebernehmen nur fuer Dateien der Bibliothek")
code, d = post({"op": "apply", "path": c})
check(code == 200 and te.read_tags(c)["fields"]["album"] == "Neu" and d["status"]["done"] == 1, "Uebernehmen ueber den Server")
check(_told == [(c, {"album": "Neu", "artist": "Neue Band"})], "Uebernehmen meldet die neuen Angaben an die Bruecke (Liste am Pi gleich aktuell)")
check(post({"op": "quatsch"})[0] == 400 and post({"op": "reject", "path": "/x"})[0] == 400, "unbekannter Befehl oder Lied: Fehler")
srv.stop()

# ---- "gut" automatisch uebernehmen (Wunsch 07.11.2026: die guten gehen von selbst, die unsicheren entscheide ich) ----
g1 = mp3("g1.mp3", [(b"TIT2", it.text_body("Gut1"))])
g2 = mp3("g2.mp3", [(b"TIT2", it.text_body("Gut2"))])
u1 = mp3("u1.mp3", [(b"TIT2", it.text_body("Unsicher"))])
songs_g = [{"path": "/g/1", "file": g1, "title": "Gut1", "artist": "", "dur": 1.0}, {"path": "/g/2", "file": g2, "title": "Gut2", "artist": "", "dur": 1.0},
           {"path": "/g/u", "file": u1, "title": "Unsicher", "artist": "", "dur": 1.0}]
tga = at.AutoTagger(lambda: songs_g, base=os.path.join(tmp, "auto_gut"))
tga.items = {"/g/1": {"state": "offen", "level": "gut", "new": {"album": "A1"}, "cover": "", "now": {}},
             "/g/u": {"state": "offen", "level": "unsicher", "new": {"album": "U"}, "cover": "", "now": {}},
             "/g/2": {"state": "offen", "level": "gut", "new": {}, "cover": "", "now": {}}}     # nichts zu schreiben
told = []
tga.on_applied = lambda p, f: told.append((p, f))
check(not tga.status()["auto"], "Standard: aus")
tga.set_auto(True)
tga.auto_thread.join(5)
check(te.read_tags(g1)["fields"]["album"] == "A1" and tga.items["/g/1"]["state"] == "erledigt" and told == [("/g/1", {"album": "A1"})],
      "eingeschaltet: offener guter Vorschlag geschrieben, der Bruecke gemeldet")
check(tga.items["/g/u"]["state"] == "offen" and te.read_tags(u1)["fields"]["album"] == "", "unsichere bleiben offen und unberuehrt")
check(tga.items["/g/2"]["state"] == "offen", "guter ohne etwas zum Schreiben: bleibt (wie auf der Seite nicht angehakt)")
check(tga.status()["auto"] and tga.status()["auto_n"] == 1 and at.AutoTagger(lambda: songs_g, base=os.path.join(tmp, "auto_gut")).auto,
      "Schalter gemerkt (auch nach Neustart), Zaehler")
check(not tga.apply_auto("/g/1", g1), "schon erledigt: nicht nochmal schreiben")
tga.items["/g/2"]["new"] = {"album": "A2"}
tga.items["/g/2"]["cover"] = "https://coverartarchive.org/x/front-500"
_orig = te.fetch_cover
try:
    at.te.fetch_cover = lambda url, **kw: (_ for _ in ()).throw(te.TagError("Cover-Server antwortet mit Fehler 500, bitte später nochmal"))
    tga.apply = (lambda real: (lambda p, f, **kw: real(p, f, fetch=at.te.fetch_cover, **kw)))(tga.apply)
    check(not tga.apply_auto("/g/2", g2) and tga.items["/g/2"]["state"] == "offen" and "500" in tga.status()["auto_err"],
          "Cover-Server weg: bleibt offen, Fehler gemeldet, naechster Lauf versucht es wieder")
finally:
    at.te.fetch_cover = _orig
tga.set_auto(False)
check(not tga.status()["auto"], "ausschalten")
src_at = open(os.path.join(BRIDGE, "auto_tag.py"), encoding="utf-8").read()
check("if self.auto and self._worth(self.items[s[\"path\"]]):" in src_at, "frisch gefundene gute werden sofort geschrieben, wenn an")

# ---- Bruecke, Pi, Seite ----
mb_src = open(os.path.join(BRIDGE, "mixxx_bridge.py"), encoding="utf-8").read()
check("fw.autotag = AutoTagger(fw.autotag_songs" in mb_src and "fw.autotag.resume()" in mb_src and "has_cover=lambda f: find_cover(f) is not None" in mb_src,
      "Bruecke startet den Auto-Tagger (laeuft nach Neustart weiter, wenn er an war)")
for f_ in ("install_launcher.sh", os.path.join("..", "helper", "install_helper.sh")):
    check("auto_tag.py" in open(os.path.join(BRIDGE, f_), encoding="utf-8").read(), f"{os.path.basename(f_)} kopiert auto_tag.py")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('if path == "/musik/vorschlaege":' in api and 'if path == "/api/musik/mac":' in api, "Pi: Seite und Adresse des Mac")
sm = os.path.join(ROOT, "pi", "static", "sm")
html, js = open(os.path.join(sm, "autotag.html"), encoding="utf-8").read(), open(os.path.join(sm, "autotag.js"), encoding="utf-8").read()
mh, mj, tj = (open(os.path.join(sm, n), encoding="utf-8").read() for n in ("music.html", "music.js", "tagedit.js"))
check('class="s2lnav" data-back="/musik" data-cur="musik" data-title="h_autotag"' in html and '<script src="/static/sm/nav.js"></script>' in html,
      "Seite mit Kopfleiste, zurueck zur Musik-Datenbank")
check('id="bauto2"' in html and "post({ op: 'auto', on })" in js and "' (' + (cnt[b.dataset.lv] || 0) + ')'" in js
      and "fw.autotag.on_applied = fw.tags_written" in mb_src and 'elif op == "auto":' in open(os.path.join(BRIDGE, "music_serve.py"), encoding="utf-8").read(),
      "Seite: Schalter Gute automatisch, Anzahl in den Reiter-Knoepfen; Bruecke meldet die Angaben an den Pi")
check("if (playing && !cur.some(it => it.path === playing)) { audio.pause(); playing = ''; }" in js
      and "audio.pause();   // Zeile weg: Ton aus" in open(os.path.join(sm, "dupes.js"), encoding="utf-8").read(),
      "Vorschlaege und Doppelte: verschwindet die Zeile, hoert der Ton auf (sonst kein Knopf mehr dafuer)")
check("const autoLevel = () => (lv === 'nichts' ? 'nichts' : lv === 'rej' ? 'rej' : 'cover');" in js and "!it.rej && it.level === level" in js,
      "Cover fuer alle auch im Reiter nichts gefunden (Wunsch 07.11.2026)")
check('class="adel"' in js and "fetch(music + '/trash'" in js and "SM.goneMark(it.path)" in js and "In den Papierkorb" in js,
      "Vorschlaege: Datei loeschen (Papierkorb des Mac, mit Rueckfrage), Musik-Datenbank blendet sie aus")
check("const PAGE = 20;" in js and "pageItems().cur.filter(it => canApply(it) && isOn(it))" in js and 'class="aone"' in js and "Markierte dieser Seite übernehmen" in html,
      "Seiten zu 20, Uebernehmen je Seite und je Lied (Wunsch 07.11.2026)")
check("href: '/musik/vorschlaege'" in open(os.path.join(ROOT, "pi", "static", "sm", "care.js"), encoding="utf-8").read(), "Tag-Vorschlaege ueber die Datenpflege")
check("await post({ op: 'apply', path: it.path })" in js and "SM.ask(todo.length + ' Vorschläge dieser Seite in die MP3s schreiben" in js, "Uebernehmen der Seite nur nach Rueckfrage")
check("{ fields: it.new || {}, cover: it.cover || '' }" in js and "SM.tagEdit = async function (r, music, onSaved, preset)" in tj, "Ansehen: Tag-Fenster mit Vorschlag")
check("function hasMp3(r)" in mj and "(r._cv || !hasMp3(r))" in mj, "→ MP3 nur, wenn es die MP3 daneben noch nicht gibt (Wunsch 07.11.2026)")
check("'<button class=\"pb aplay'" in js and "audio.src = music + '/audio?p=' + encodeURIComponent(it.path);" in js,
      "Vorschlagszeile: Hineinhoeren mit ▶ (Wunsch 07.11.2026)")
check(js.index("'<div class=\"anow\">") < js.index("'<div class=\"anew\">") < js.index("<img class=\"cvimg\" src=\"' + esc(it.cover)")
      and '<div class="acv none" title="kein Cover">' in js, "neues Cover rechts beim Vorschlag, links nur der leere Rahmen")
check(not at.skipped("/Volumes/USB/musik/SAMPLES/thx.mp3") and not at.skipped("/m/TESTSAMPLES/x/y.mp3"),
      "SAMPLES und TESTSAMPLES wieder dabei (Wunsch 07.11.2026, seit es Cover erzeugen gibt)")
_old_skip = at.SKIP_DIRS
at.SKIP_DIRS = ("samples",)                              # der Mechanismus bleibt, falls wieder Ordner ausgelassen werden sollen
_s = mp3("s.mp3", [(b"TIT2", it.text_body("Sample"))])
_tg = at.AutoTagger(lambda: [{"path": "/x/SAMPLES/s.mp3", "file": _s, "title": "S", "artist": "", "dur": 10.0}], base=os.path.join(tmp, "at3"))
_tg.items["/x/SAMPLES/alt.mp3"] = {"state": "offen", "level": "gut", "new": {"album": "A"}, "cover": "", "now": {}}
check(_tg.todo() == [] and _tg.list() == [], "Samples: nicht recherchiert, alte Vorschlaege dazu nicht gezeigt")
at.SKIP_DIRS = _old_skip
check("'<div class=\"afile\" title=\"' + esc(it.path) + '\">' + esc(short(it.path))" in js, "Zeile zeigt Dateiname und Ordner (Wunsch 07.11.2026)")
# Fehlerbericht 07.11.2026: oben 71 offen, in der Liste viel weniger (Samples mitgezaehlt)
_tg2 = at.AutoTagger(lambda: [{"path": "/m/a", "file": a, "title": "L", "artist": "B", "dur": 213.4}], base=os.path.join(tmp, "at4"), has_cover=lambda f: False)
_tg2.items = {"/m/a": {"state": "offen", "level": "gut", "new": {}, "cover": "", "now": {}},
              "/x/SAMPLES/s1.mp3": {"state": "offen", "level": "unsicher", "new": {}, "cover": "", "now": {}}}
at.SKIP_DIRS = ("samples",)
check(_tg2.status()["open"] == len(_tg2.list()) == 1 and _tg2.status()["unsure"] == 0, "Zahlen oben wie die Liste: ausgelassene Ordner zaehlen nicht")
at.SKIP_DIRS = _old_skip
check(_tg2.list()[0]["dur"] == 213.4, "Spieldauer je Vorschlag (auch fuer aeltere ohne)")
_tg2.has_cover = lambda f: f == a
check(_tg2.prune() == 1 and _tg2.items["/m/a"]["state"] == "erledigt", "Lied hat inzwischen ein Cover: Vorschlag erledigt")
check("<span class=\"adur\">' + mmss(it.dur)" in js, "Seite zeigt die Dauer")
check("gen.set(it.path, await SM.coverFor(music, it.path))" in js and "fields: {}, cover_data: gen.get(it.path)" in js,
      "Cover erzeugen links: nur aus den Tags der Datei, beim Speichern keine Tags (Wunsch 07.11.2026)")
_tj2 = open(os.path.join(ROOT, "pi", "static", "sm", "tagedit.js"), encoding="utf-8").read()
check("SM.coverFor = async (music, path)" in _tj2 and "const t = await fetch(music + '/tags?' + q)" in _tj2, "coverFor liest die Tags der Datei selbst")
check("at.prune_soon()" in open(os.path.join(BRIDGE, "music_serve.py"), encoding="utf-8").read(), "beim Oeffnen der Seite wird aufgeraeumt")
check("function dirOf(p) { const a = String(p || '').split('/'); a.pop(); return a.join('/'); }" in js, "voller Ordnerpfad (Wunsch 07.11.2026)")
check("b.textContent = 'Speichere …';" in js and "b.textContent = '✓ Gespeichert';" in js, "Speichern zeigt, dass es laeuft und fertig ist (Fehlerbericht 07.11.2026)")
check(js.count('<img class="cvimg"') == 2, "Cover in der Liste vergroessern sich beim Darueberfahren")
check('<button class="agedit"' in js and "SM.tagEdit({ path: it.path, dur: it.dur || 0 }, music, async d =>" in js,
      "links bei jetzt: Tag-Editor fuer die Datei ohne Vorschlaege (Wunsch 07.11.2026)")
# Wunsch 07.11.2026: Samples und Testsamples nur zum Cover erzeugen, ohne Internet und Shazam
check(at.cover_only("/m/SAMPLES/x.mp3") and at.cover_only("/m/TESTSAMPLES/a/b.mp3") and not at.cover_only("/m/Artists/x.mp3"), "Samples-Ordner erkannt")
_cs = mp3("cs.mp3", [(b"TIT2", it.text_body("Donner"))])
_looked = []
_tg5 = at.AutoTagger(lambda: [{"path": "/m/SAMPLES/cs.mp3", "file": _cs, "title": "Donner", "artist": "", "dur": 13.0}], base=os.path.join(tmp, "at5"),
                     has_cover=lambda f: False)
_orig_research = at.research
at.research = lambda *a_, **k_: _looked.append(1) or {}
_tg5.start()
for _ in range(100):
    if _tg5.items:
        break
    time.sleep(0.02)
_tg5.stop()
at.research = _orig_research
check(not _looked and _tg5.items["/m/SAMPLES/cs.mp3"]["level"] == "cover" and _tg5.items["/m/SAMPLES/cs.mp3"]["new"] == {},
      "Samples: keine Suche, Stufe nur Cover")
check(_tg5.status()["cover"] == 1 and _tg5.list()[0]["level"] == "cover", "nur Cover in Zahlen und Liste")
json.dump({"on": False, "items": {"/m/SAMPLES/alt.mp3": {"state": "abgelehnt", "level": "unsicher", "new": {"title": "Falsch"}, "cover": "x", "now": {}}}},
          open(os.path.join(tmp, "at6.json"), "w"))
os.makedirs(os.path.join(tmp, "at6"), exist_ok=True)
os.replace(os.path.join(tmp, "at6.json"), os.path.join(tmp, "at6", at.FILE))
_tg6 = at.AutoTagger(lambda: [], base=os.path.join(tmp, "at6"))
check(_tg6.items["/m/SAMPLES/alt.mp3"]["level"] == "cover" and _tg6.items["/m/SAMPLES/alt.mp3"]["state"] == "offen"
      and _tg6.items["/m/SAMPLES/alt.mp3"]["new"] == {}, "fruehere Samples-Vorschlaege (auch abgelehnte): jetzt nur Cover")
check("it.level === 'cover' ? '<span class=\"alab\">Samples: keine Suche im Internet." in js and 'data-lv="cover"' in html, "Seite: Reiter und Hinweis nur Cover")
# Fehler beim Push 07.11.2026: Start und Hintergrund-Lauf speicherten gleichzeitig (FileNotFoundError bei der Hilfsdatei)
import threading  # noqa: E402
_tg7 = at.AutoTagger(lambda: [], base=os.path.join(tmp, "at7"))
_errs = []


def _hammer(n):
    for i in range(30):
        try:
            with _tg7.lock:
                _tg7.items[f"/m/{n}/{i}.mp3"] = {"state": "offen", "level": "gut", "new": {}, "cover": "", "now": {}}
            _tg7._save()
        except Exception as e:  # noqa: BLE001
            _errs.append(e)


_ts = [threading.Thread(target=_hammer, args=(n,)) for n in range(8)]
for _t in _ts:
    _t.start()
for _t in _ts:
    _t.join()
check(not _errs and len(json.load(open(os.path.join(tmp, "at7", at.FILE), encoding="utf-8"))["items"]) == 240,
      f"viele gleichzeitige Speichervorgaenge: kein Fehler, nichts verloren ({_errs[:1]})")
# Wunsch 07.11.2026: unter "nur Cover" alle der Reihe nach automatisch erzeugen und speichern
check('id="bauto"' in html and "async function autoCovers()" in js and "const todo = items.filter(it => level === 'rej' ? it.rej : !it.rej && it.level === level);" in js,
      "Knopf Alle Cover automatisch, fuer die Lieder unter nur Cover (oder nichts gefunden)")
check("gen.set(it.path, await SM.coverFor(music, it.path));" in js and "await saveCover(it);" in js and "if (!autoRun) break;" in js,
      "je Lied: Cover aus den eigenen Tags erzeugen, speichern; Anhalten jederzeit")
check("fields: {}, cover_data: gen.get(it.path)" in js, "Automatik schreibt nur das Bild, keine Tags")
# Fehlerbericht 07.11.2026 ("Nun Lasst Uns Gehn"): Vorschlag zu einer geloeschten Datei (nur noch in Mixxx) liess sich nicht speichern
_tg8 = at.AutoTagger(lambda: [{"path": "/m/da.mp3", "file": a, "title": "x", "artist": "", "dur": 1.0},
                              {"path": "/m/weg.mp3", "file": os.path.join(tmp, "geloescht.mp3"), "title": "y", "artist": "", "dur": 1.0}],
                     base=os.path.join(tmp, "at8"), has_cover=lambda f: False)
_tg8.items = {"/m/da.mp3": {"state": "offen", "level": "cover", "new": {}, "cover": "", "now": {}},
              "/m/weg.mp3": {"state": "offen", "level": "cover", "new": {}, "cover": "", "now": {}}}
check([x["path"] for x in _tg8.list()] == ["/m/da.mp3"] and _tg8.status()["open"] == 1 and _tg8.status()["cover"] == 1,
      "Datei fehlt: nicht in der Liste und nicht gezaehlt")
check("/m/weg.mp3" not in [x["path"] for x in _tg8.todo()], "fuer fehlende Dateien kein neuer Vorschlag")
# 08.11.2026: Lautstaerke oben (gemeinsam mit der Musik-Datenbank) und Leiste zum Spulen im Lied
_ah = open(os.path.join(ROOT, "pi", "static", "sm", "autotag.html"), encoding="utf-8").read()
_aj = open(os.path.join(ROOT, "pi", "static", "sm", "autotag.js"), encoding="utf-8").read()
check('id="vol"' in _ah and _ah.index('id="vol"') < _ah.index('id="list"') and "localStorage.setItem('musikvol'" in _aj, "Tag-Vorschlaege: Lautstaerke oben, gemerkt wie in der Musik-DB")
check('id="ppos"' in _ah and "audio.currentTime = d * $('ppos').value / 1000" in _aj, "Tag-Vorschlaege: im Lied spulen")
# 08.11.2026: uebernommen, aber ohne Cover (Titel erst per Shazam richtig) -> genau einmal neu suchen
c_again = mp3("again.mp3", [(b"TIT2", it.text_body("Richtig"))])
songs_a = [{"path": "/m/a", "file": c_again, "title": "Richtig", "artist": "", "dur": 200.0}]
tga = at.AutoTagger(lambda: songs_a, base=os.path.join(tmp, "at_again"), has_cover=lambda f: ms.find_cover(f) is not None)
tga.items["/m/a"] = {"state": "erledigt", "new": {"title": "Richtig"}, "cover": "", "level": "unsicher"}
check([x["path"] for x in tga.todo()] == ["/m/a"], "uebernommen ohne Cover: noch einmal suchen")
tga.items["/m/a"] = {"state": "erledigt", "new": {"title": "Richtig"}, "cover": "", "again": 1}
check(tga.todo() == [], "nach dem zweiten Mal nicht wieder")
tga.items["/m/a"] = {"state": "erledigt", "new": {}, "cover": ""}
check(tga.todo() == [], "erledigt ohne Aenderung (z.B. Cover selbst erzeugt oder so gelassen): nicht wieder")
tga.items["/m/a"] = {"state": "abgelehnt", "new": {"title": "X"}, "cover": ""}
check(tga.todo() == [], "abgelehnt bleibt abgelehnt")
# 08.11.2026: Titel = Interpret - Assistent aus der Musik-DB: zuerst Shazam, dann Dateiname; Titel und Interpret duerfen ersetzt werden
SZ = {"kind": "ok", "song": {"title": "Lied", "artist": "Band", "genre": "Rock"}}
lk, lcalls = lookup_for({("Band", "Lied"): COV})
r = at.research({"path": "/m/t", "file": "/m/Band - Lied.mp3", "dur": 200, "now": {"title": "Balance", "artist": "Balance"}},
                lookup=lk, recognize=lambda s_: SZ, fetch=lambda u: JPG, suspect=True)
check(r["source"] == "shazam" and r["new"].get("title") == "Lied" and r["new"].get("artist") == "Band" and r["why"] == "ti",
      "verdaechtig: Shazam zuerst, Titel und Interpret ersetzt, Reiter Titel = Interpret")
check(lcalls and lcalls[0] == ("Band", "Lied"), "keine Suche mit den falschen Tags")
r = at.research({"path": "/m/t", "file": "/m/x/07 - Album - Band - Lied.mp3", "dur": 200, "now": {"title": "Balance", "artist": "Balance"}},
                lookup=lambda a, t, d: {"suggest": [], "covers": []}, recognize=lambda s_: {"kind": "nomatch"}, fetch=lambda u: JPG, suspect=True)
check(r["source"] == "datei" and r["new"] == {"title": "Lied", "artist": "Band"} and r["level"] == "unsicher",
      "Shazam kennt es nicht: Vorschlag aus dem Dateinamen, als unsicher (selbst ansehen)")
check(not at.AutoTagger._worth({"state": "offen", "level": "gut", "new": {"title": "x"}, "why": "ti"}), "Titel = Interpret nie automatisch uebernehmen")
ti_song = mp3("ti.mp3", [(b"TIT2", it.text_body("Balance")), (b"TPE1", it.text_body("Balance")), (b"APIC", b"\x00image/jpeg\x00\x03\x00" + JPG)])
tgt = at.AutoTagger(lambda: [{"path": "/m/ti", "file": ti_song, "title": "Balance", "artist": "Balance", "dur": 200.0}],
                    base=os.path.join(tmp, "at_ti"), has_cover=lambda f: True)
tgt.recognize = lambda s_: SZ
check(tgt.research_paths(["/m/ti", "/m/fremd"], start=False) == 1 and tgt.ti_queue == ["/m/ti"], "nur Lieder der Bibliothek in die Warteschlange")
tgt.lookup = lambda a, t, d=0.0, **k: {"suggest": [{"source": "x", "title": "Lied", "artist": "Band"}], "covers": []}   # kein Internet im Test
check(tgt._ti_step() and not tgt.ti_queue and tgt.items["/m/ti"]["why"] == "ti" and tgt.items["/m/ti"]["new"].get("title") == "Lied",
      "ein Lied recherchiert, obwohl es ein Cover hat")
check(tgt.prune() == 0 and tgt.items["/m/ti"]["state"] == "offen", "Aufraeumen nach Cover laesst Titel = Interpret stehen")
# Fehlerbericht 08.11.2026: der Faden schlief 5 Minuten (keine Lieder ohne Cover), der Knopf muss ihn sofort wecken
import time as _time  # noqa: E402
tgw = at.AutoTagger(lambda: [{"path": "/m/ti", "file": ti_song, "title": "Balance", "artist": "Balance", "dur": 200.0}],
                    base=os.path.join(tmp, "at_wake"), has_cover=lambda f: True)
tgw.recognize = lambda s_: SZ
tgw.lookup = lambda a, t, d=0.0, **k: {"suggest": [], "covers": []}
tgw.start()
_time.sleep(0.5)                                     # jetzt in der langen Pause
tgw.research_paths(["/m/ti"])
for _ in range(40):
    if "/m/ti" in tgw.items:
        break
    _time.sleep(0.1)
check("/m/ti" in tgw.items and tgw.items["/m/ti"]["why"] == "ti", "Knopf weckt den Auto-Tagger sofort aus der Pause")
tgw.stop()
tgw.thread.join(3)
check(tgt.status()["ti"] == 1, "Zahl fuer den Reiter")
_mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
_mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
_ah = open(os.path.join(ROOT, "pi", "static", "sm", "autotag.html"), encoding="utf-8").read()
_aj = open(os.path.join(ROOT, "pi", "static", "sm", "autotag.js"), encoding="utf-8").read()
check('id="bsameai"' in _mh and "op: 'research', paths" in _mj and "'/musik/vorschlaege?f=ti'" in _mj, "Musik-DB: Knopf Assistent bei Titel = Interpret")
check('data-lv="ti"' in _ah and "it.why === 'ti'" in _aj and "get('f') === 'ti'" in _aj, "Tag-Vorschlaege: Reiter Titel = Interpret")
finish("Auto-Tagger")
