"""Tag bearbeiten in der Musik-Datenbank (Wunsch von Markus, 07.11.2026): alle ID3-Felder lesen, die ueblichen aendern, Cover
setzen, Vorschlaege von MusicBrainz, iTunes und Deezer (nur auf Knopfdruck, nachgestellt), Musik und Fingerabdruck bleiben."""
import io
import json
import os
import random
import sys
import tempfile
import urllib.error
import urllib.request

from _common import ROOT, check, finish

BRIDGE = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BRIDGE)
import id3_tags as it      # noqa: E402
import mixxx_bridge as mb  # noqa: E402
import music_serve as ms   # noqa: E402
import tag_edit as te      # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_tag_")
AUDIO = bytes(random.Random(3).getrandbits(8) for _ in range(30000))
JPG = b"\xff\xd8\xff\xe0" + b"bild" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 60


def id3(frames, ver=3, pad=64):
    data = b"".join(it.frame(f, b, ver) for f, b in frames) + b"\0" * pad
    n = len(data)
    return b"ID3" + bytes([ver, 0, 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127]) + data


def mp3(name, frames, ver=3, pad=64):
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(id3(frames, ver, pad) + AUDIO)
    return p


def audio_of(p):
    r = it.read(p)
    with open(p, "rb") as f:
        f.seek(10 + r[1])
        return f.read()


# ---- Lesen ----
a = mp3("a.mp3", [(b"TIT2", it.text_body("Lied")), (b"TPE1", it.text_body("Band")), (b"TYER", it.text_body("1999")),
                  (b"COMM", b"\x00eng\x008A - Energy 7"), (b"COMM", b"\x00engiTunNORM\x00 000"), (b"TXXX", it.txxx_body("EnergyLevel", "7")),
                  (b"TXXX", it.txxx_body("Quelle", "CD")), (b"TLEN", it.text_body("1000")), (b"APIC", b"\x00image/jpeg\x00\x03\x00" + JPG),
                  (b"PRIV", b"geheim\x00123")])
t = te.read_tags(a)
check(t["ver"] == 3 and t["fields"]["title"] == "Lied" and t["fields"]["artist"] == "Band" and t["fields"]["year"] == "1999"
      and t["fields"]["comment"] == "8A - Energy 7" and t["fields"]["energy"] == "7", "uebliche Felder gelesen")
names = [o["name"] for o in t["other"]]
check("Laenge (ms)" in names and "Eigenes Feld quelle" in names and "Kommentar iTunNORM" in names and "Privat" in names,
      "alle anderen Rahmen werden angezeigt")
check(t["cover"] == {"mime": "image/jpeg", "size": len(JPG), "type": 3}, "Cover erkannt")
check(set(t["labels"]) == {k for k, _f, _l in te.FIELDS} and t["labels"]["albumartist"] == "Album-Interpret", "Bezeichnungen auf Deutsch")

# ---- Schreiben: nur die geaenderten Felder, alles andere bleibt ----
fpa = mb.audio_fingerprint(a)
before = {(f[0], f[3]) for f in it.read(a)[2] if f[0] not in (b"TIT2", b"TALB", b"COMM", b"TYER")}
r = te.write_tags(a, {"title": "Größer – Ä", "album": "Österreich", "year": "2016", "comment": "neu"})
check(r["fields"]["title"] == "Größer – Ä" and r["fields"]["album"] == "Österreich" and r["fields"]["year"] == "2016" and r["fields"]["comment"] == "neu",
      "Umlaute und Sonderzeichen (UTF-16) zurueckgelesen")
after = {(f[0], f[3]) for f in it.read(a)[2]}
check(before <= after, "alle anderen Rahmen unveraendert (Cover, eigene Felder, Privat, Laenge)")
check(any(x["name"] == "Kommentar iTunNORM" for x in r["other"]), "Kommentar mit Beschreibung bleibt beim Aendern des Hauptkommentars")
check(audio_of(a) == AUDIO and mb.audio_fingerprint(a) == fpa, "Musik und Fingerabdruck gleich: Shows passen weiter")
r = te.write_tags(a, {"energy": "", "artist": ""})
check(r["fields"]["energy"] == "" and r["fields"]["artist"] == "" and not any(f[0] == b"TPE1" for f in it.read(a)[2])
      and any(x["name"] == "Eigenes Feld quelle" for x in r["other"]), "leeres Feld entfernt den Rahmen, nur diesen")
r = te.write_tags(a, cover=PNG)
apics = [f for f in it.read(a)[2] if f[0] == b"APIC"]
check(len(apics) == 1 and r["cover"]["mime"] == "image/png" and r["cover"]["size"] == len(PNG), "neues Cover ersetzt das alte")
check(te.write_tags(a, remove_cover=True)["cover"] is None, "Cover entfernen")
for bad, why in (({"title": "a\x00b"}, "Nullzeichen"), ({"title": "x" * 3000}, "zu lang")):
    try:
        te.write_tags(a, bad)
        check(False, why)
    except te.TagError:
        check(True, f"abgelehnt: {why}")
try:
    te.write_tags(a, cover=b"kein bild")
    check(False, "kein Bild")
except te.TagError:
    check(True, "Cover nur JPEG oder PNG")
check(te.write_tags(a, {"unbekannt": "x", "title": "T"})["fields"]["title"] == "T", "unbekannte Felder werden ignoriert")
b4 = mp3("b4.mp3", [(b"TIT2", it.text_body("v4")), (b"TDRC", it.text_body("2001"))], ver=4)
r = te.write_tags(b4, {"year": "2002", "title": "Café"})
check(r["ver"] == 4 and r["fields"]["year"] == "2002" and r["fields"]["title"] == "Café" and any(f[0] == b"TDRC" for f in it.read(b4)[2])
      and audio_of(b4) == AUDIO, "ID3v2.4: Jahr als TDRC, UTF-8")
v2 = os.path.join(tmp, "alt.mp3")
with open(v2, "wb") as f:
    f.write(b"ID3\x02\0\0\0\0\0\x10" + b"\0" * 16 + AUDIO)
try:
    te.read_tags(v2)
    check(False, "v2.2")
except te.TagError as e:
    check("ID3v2.2" in str(e), "alte ID3-Form: verstaendlicher Fehler statt Schaden")


# ---- Vorschlaege (Internet nachgestellt) ----
class Resp(io.BytesIO):
    def __init__(self, data, url=""):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


MB = {"recordings": [
    {"title": "Lied", "length": 200000, "score": 100, "artist-credit": [{"name": "Band"}],
     "releases": [{"id": "rel-sampler", "title": "Hits 2015", "date": "2015-05-01", "artist-credit": [{"name": "Various Artists"}],
                   "release-group": {"primary-type": "Album"}, "media": [{"position": 1, "track-count": 20, "track": [{"number": "7"}]}]},
                  {"id": "rel-album", "title": "Das Album", "date": "2014-03-01", "artist-credit": [{"name": "Band"}],
                   "release-group": {"primary-type": "Album"}, "media": [{"position": 1, "track-count": 12, "track": [{"number": "3"}]}]}]},
    {"title": "Lied (Live)", "length": 400000, "score": 100, "artist-credit": [{"name": "Band"}],
     "releases": [{"id": "rel-live", "title": "Live", "date": "2018", "release-group": {"primary-type": "Album"}, "media": [{"track": [{"number": "1"}]}]}]}]}
IT = {"results": [{"trackName": "Lied", "artistName": "Band", "collectionName": "Das Album", "releaseDate": "2014-03-01T00:00:00Z",
                   "primaryGenreName": "Dance", "trackNumber": 3, "trackCount": 12, "artworkUrl100": "https://is1-ssl.mzstatic.com/x/100x100bb.jpg"}]}
DZ = {"data": [{"title": "Lied", "artist": {"name": "Band"}, "album": {"title": "Das Album", "cover_xl": "https://e-cdns-images.dzcdn.net/x/1000.jpg"}}]}
asked = []


def opener(req, timeout=0):
    url = req.full_url if hasattr(req, "full_url") else req
    asked.append((url, dict(req.header_items()) if hasattr(req, "header_items") else {}))
    if "musicbrainz.org" in url:
        return Resp(json.dumps(MB).encode())
    if "itunes.apple.com" in url:
        return Resp(json.dumps(IT).encode())
    if "api.deezer.com" in url:
        return Resp(json.dumps(DZ).encode())
    if "mzstatic.com" in url or "coverartarchive.org" in url:
        return Resp(JPG, url)
    raise urllib.error.URLError("unbekannt")


res = te.lookup("Band", "Lied", 201.0, opener=opener, sleep=lambda s: None)
mbs = [x for x in res["suggest"] if x["source"] == "MusicBrainz"]
check(mbs and mbs[0]["album"] == "Das Album" and mbs[0]["year"] == "2014" and mbs[0]["track"] == "3/12" and mbs[0]["albumartist"] == "Band",
      "MusicBrainz: eigenes Album vor dem Sampler")
check(not any(x["album"] == "Live" for x in mbs), "andere Laenge (Live-Fassung) aussortiert")
MB2 = {"recordings": [{"title": "Lied", "length": 200000, "score": 100, "artist-credit": [{"name": "Band"}], "releases": [
    {"id": "best-of", "title": "Band Forever", "date": "2025", "artist-credit": [{"name": "Band"}],
     "release-group": {"primary-type": "Album", "secondary-types": ["Compilation"]}, "media": [{"track": [{"number": "1"}]}]},
    {"id": "orig", "title": "Erstes Album", "date": "1992", "artist-credit": [{"name": "Band"}],
     "release-group": {"primary-type": "Album"}, "media": [{"track": [{"number": "2"}]}]},
    {"id": "orig2", "title": "Erstes Album", "date": "2009", "artist-credit": [{"name": "Band"}],
     "release-group": {"primary-type": "Album"}, "media": [{"track": [{"number": "2"}]}]}]}]}
m2 = te.musicbrainz("Band", "Lied", 0, opener=lambda req, timeout=0: Resp(json.dumps(MB2).encode()), sleep=lambda s: None)
check([x["album"] for x in m2] == ["Erstes Album", "Band Forever"] and m2[0]["year"] == "1992" and "extra" not in m2[0],
      "Originalalbum vor eigener Best-of (Fehlerbericht 07.11.2026), Neuauflagen zusammengefasst")
itn = [x for x in res["suggest"] if x["source"] == "iTunes"]
check(itn and itn[0]["genre"] == "Dance" and itn[0]["year"] == "2014" and itn[0]["cover"].endswith("600x600bb.jpg"), "iTunes: Genre, Jahr, Cover in 600 Pixeln")
urls = [c["url"] for c in res["covers"]]
check(urls[0] == "https://coverartarchive.org/release/rel-album/front-500" and any("dzcdn.net" in u for u in urls) and any("mzstatic" in u for u in urls),
      "Cover von Cover Art Archive, iTunes und Deezer")
check(all("Light-Butler" in h.get("User-agent", "") for u, h in asked if "musicbrainz" in u), "MusicBrainz bekommt eine eigene Kennung (Regel)")
sent = " ".join(u for u, h in asked)
check("markus" not in sent.lower() and "@" not in sent, "keine persoenlichen Daten in den Anfragen")


def broken(req, timeout=0):
    if "deezer" in (req.full_url if hasattr(req, "full_url") else req):
        raise urllib.error.URLError("weg")
    return opener(req, timeout)


res2 = te.lookup("Band", "Lied", 0, opener=broken, sleep=lambda s: None)
check(res2["errors"] and res2["errors"][0].startswith("Deezer") and any(x["source"] == "MusicBrainz" for x in res2["suggest"]),
      "eine Quelle faellt aus: die anderen gelten")
slept = []
te._mb_last[0] = __import__("time").time()
te.musicbrainz("Band", "Lied", 0, opener=opener, sleep=slept.append)
check(slept and 0 < slept[0] <= 1.1, "MusicBrainz hoechstens eine Anfrage pro Sekunde")
check(te.cover_allowed("https://is1-ssl.mzstatic.com/a.jpg") and te.cover_allowed("https://coverartarchive.org/release/x/front")
      and not te.cover_allowed("http://is1-ssl.mzstatic.com/a.jpg") and not te.cover_allowed("https://mzstatic.com.boese.de/a.jpg")
      and not te.cover_allowed("https://192.168.1.45/a.jpg"), "Cover nur per https von den vier Quellen")
check(te.fetch_cover("https://is1-ssl.mzstatic.com/a.jpg", opener=opener) == JPG, "Cover geholt und geprueft")
try:
    te.fetch_cover("https://coverartarchive.org/x", opener=lambda req, timeout=0: Resp(JPG, "https://boese.example/x.jpg"))
    check(False, "Weiterleitung woandershin")
except te.TagError:
    check(True, "Weiterleitung auf fremde Adresse abgelehnt")
# Cover Art Archive antwortet manchmal mit 500 (Fehlerbericht 07.11.2026): noch zweimal versuchen
import urllib.error as _ue  # noqa: E402
_calls, _waits = [], []


def _flaky(req, timeout=0):
    _calls.append(1)
    if len(_calls) < 3:
        raise _ue.HTTPError(req.full_url, 500, "Internal Server Error", {}, None)
    return Resp(JPG, req.full_url)


check(te.fetch_cover("https://coverartarchive.org/r/front-500", opener=_flaky, sleep=_waits.append) == JPG and len(_calls) == 3 and _waits == [2.0, 4.0],
      "Serverfehler 500: noch zweimal versucht, beim dritten Mal da")
try:
    te.fetch_cover("https://coverartarchive.org/r/front-500", opener=lambda req, timeout=0: (_ for _ in ()).throw(_ue.HTTPError(req.full_url, 500, "x", {}, None)), sleep=lambda s: None)
    check(False, "immer 500")
except te.TagError as e:
    check("Fehler 500" in str(e) and "später" in str(e), f"immer 500: verstaendliche Meldung ({e})")
try:
    te.fetch_cover("https://coverartarchive.org/r/front-500", opener=lambda req, timeout=0: (_ for _ in ()).throw(_ue.HTTPError(req.full_url, 404, "x", {}, None)), sleep=lambda s: None)
    check(False, "404")
except te.TagError as e:
    check("404" in str(e), "404 (kein Cover dort): kein zweiter Versuch, Meldung")

# ---- Vorhoer-Server: lesen, schreiben, nur MP3 der Bibliothek ----
c = mp3("c.mp3", [(b"TIT2", it.text_body("Server"))])
wav = os.path.join(tmp, "d.wav")
open(wav, "wb").write(b"RIFF")
srv = ms.MusicServer([c, wav], port=0)
check(srv.start(), "Server startet")
base = f"http://127.0.0.1:{srv.port}"


def get(path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def post(body):
    req = urllib.request.Request(base + "/tags", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


q = urllib.request.quote
code, d = get("/tags?p=" + q(c, safe=""))
check(code == 200 and d["fields"]["title"] == "Server" and d["file"] == "c.mp3", "Tags lesen ueber den Server")
check(get("/tags?p=" + q("/fremd/x.mp3", safe=""))[0] == 404 and get("/tags?p=" + q(wav, safe=""))[0] == 400, "nur MP3 der Bibliothek")
check(post({"p": c, "name": "falsch.mp3", "fields": {"title": "x"}})[0] == 400, "falscher Dateiname: abgelehnt")
check(post({"p": c, "name": "c.mp3", "fields": "kaputt"})[0] == 400, "unbrauchbare Felder: abgelehnt")
code, d = post({"p": c, "name": "c.mp3", "fields": {"title": "Neu", "genre": "House"}})
check(code == 200 and d["ok"] and te.read_tags(c)["fields"]["genre"] == "House" and audio_of(c) == AUDIO, "Tags schreiben ueber den Server")
check(post({"p": c, "name": "c.mp3", "fields": {}, "cover_url": "https://boese.example/x.jpg"})[0] == 400, "Cover von fremder Adresse abgelehnt")
code, d = get("/lookup?p=" + q("/fremd/x.mp3", safe="") + "&artist=a&title=b")
check(code == 404, "Suche nur fuer Lieder der Bibliothek (kein offener Vermittler)")
srv.stop()

# ---- Shazam fuer eine Datei: Ausschnitt vom Browser, SongRec am Pi ----
sys.path.insert(0, os.path.join(ROOT, "pi"))
import songrec_id  # noqa: E402
import subprocess  # noqa: E402
import wave  # noqa: E402
buf = io.BytesIO()
with wave.open(buf, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(22050)
    w.writeframes(b"\0\0" * 22050)
probe = buf.getvalue()
seen = []


def runner(args, **kw):
    seen.append((args, os.path.isfile(args[-1]) and open(args[-1], "rb").read(4)))
    return subprocess.CompletedProcess(args, 0, '{"track": {"title": "Candy Everybody Wants", "subtitle": "10,000 Maniacs", "genres": {"primary": "Rock"}}}', "")


wavp = os.path.join(tmp, "probe.wav")
res = songrec_id.recognize_upload("/snap/bin/songrec", probe, wav_file=wavp, runner=runner)
check(res == {"kind": "ok", "song": {"title": "Candy Everybody Wants", "artist": "10,000 Maniacs", "genre": "Rock"}, "msg": ""},
      "Shazam erkennt den Ausschnitt")
check(seen[0][0][-3:] == ["recognize", "--json", wavp] and seen[0][1] == b"RIFF" and not os.path.exists(wavp), "SongRec bekommt die WAV, danach geloescht")
for bad in (b"kein wav", b"RIFF" + b"x" * 8, b"RIFF\0\0\0\0WAVE" + b"\0" * (songrec_id.TAG_MAX_BYTES)):
    try:
        songrec_id.recognize_upload("/x", bad, wav_file=wavp, runner=runner)
        check(False, "kaputter Ausschnitt")
    except ValueError:
        pass
check(len(seen) == 1, "nur echte, kleine WAV-Ausschnitte gehen an SongRec")
nm = songrec_id.recognize_upload("/x", probe, wav_file=wavp, runner=lambda a, **k: subprocess.CompletedProcess(a, 0, "", "No match for this song"))
check(nm["kind"] == "nomatch", "nicht erkannt: Hinweis statt Fehler")

# ---- Selbst erzeugtes Cover (Wunsch 07.11.2026, Entwurf C Wellenform) ----
g = mp3("gen.mp3", [(b"TIT2", it.text_body("Eigenmix"))])
srv2 = ms.MusicServer([g], port=0)
check(srv2.start(), "Server startet")
import base64  # noqa: E402
req = urllib.request.Request(f"http://127.0.0.1:{srv2.port}/tags", data=json.dumps({"p": g, "name": "gen.mp3", "fields": {}, "cover_data": base64.b64encode(JPG).decode()}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=5) as resp:
    gd = json.loads(resp.read())
check(gd["ok"] and gd["cover"]["size"] == len(JPG) and gd["fields"]["coversrc"] == te.COVER_MADE and audio_of(g) == AUDIO,
      "erzeugtes Cover in der MP3, mit Vermerk 'erzeugt', Musik gleich")
# Bild vom eigenen Rechner (Wunsch 09.11.2026): gleicher Weg, Vermerk "Eigenes Bild"
req = urllib.request.Request(f"http://127.0.0.1:{srv2.port}/tags", data=json.dumps({"p": g, "name": "gen.mp3", "fields": {}, "cover_data": base64.b64encode(JPG).decode(),
                                                                                     "cover_src": "datei"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=5) as resp:
    gd = json.loads(resp.read())
check(gd["ok"] and gd["fields"]["coversrc"] == te.COVER_OWN and audio_of(g) == AUDIO, "eigenes Bild in der MP3, Vermerk 'Eigenes Bild', Musik gleich")
bad = urllib.request.Request(f"http://127.0.0.1:{srv2.port}/tags", data=json.dumps({"p": g, "name": "gen.mp3", "fields": {}, "cover_data": "kein bild!"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(bad, timeout=5)
    check(False, "kaputtes Cover")
except urllib.error.HTTPError as e:
    check(e.code == 400, "kaputte Bilddaten abgelehnt")
srv2.stop()
_tj = open(os.path.join(ROOT, "pi", "static", "sm", "tagedit.js"), encoding="utf-8").read()
check("SM.makeCover = o =>" in _tj and "SM.peaksFor(music, q, 90, decode)" in _tj and "cover_data: coverData ? coverData.split(',')[1] : undefined" in _tj,
      "Fenster: Cover erzeugen aus Titel, Interpret, BPM, Tonart, Energie und Wellenform")
check("SM.squareCover = (file, max)" in _tj and 'id="tgfilein" accept="image/*"' in _tj and "cover_src: coverData && coverOwn ? 'datei'" in _tj
      and "(w - side) / 2, (h - side) / 2, side, side" in _tj, "Fenster: Bild vom Rechner, Mitte quadratisch, hoechstens 1000 px")
_cc = subprocess.run(["node", "-e", "global.window={};require(process.argv[1]);const S=window.SM;console.log(JSON.stringify([1,5,6,7,9,0].map(e=>S.coverColors(e)[0])))",
                      os.path.join(ROOT, "pi", "static", "sm", "tagedit.js")], capture_output=True, text=True).stdout.strip()
check(_cc == '["#042C53","#04342C","#412402","#4A1B0C","#501313","#04342C"]', f"Farbe nach Energie: ruhig blau bis wild rot ({_cc})")

# ---- Pi und Panel ----
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('if op == "cover_refresh":' in api and "self.covers.fetch(path)" in api, "Pi holt das neue Cover gleich")
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
tj = open(os.path.join(ROOT, "pi", "static", "sm", "tagedit.js"), encoding="utf-8").read()
check("String(r.ext || '').toLowerCase() === 'mp3' ? '<button class=\"pb tag\"" in mj and "SM.tagEdit(r, music," in mj, "Knopf Tag bei jeder MP3")
_css = open(os.path.join(ROOT, "pi", "static", "sm", "sm.css"), encoding="utf-8").read()
_ah = open(os.path.join(ROOT, "pi", "static", "sm", "autotag.html"), encoding="utf-8").read()
check('<script src="/static/sm/tagedit.js"></script>' in mh and ".tagbox" in _css and ".tagbox" not in mh and "sm.css" in _ah,
      "Fenster eingebunden, Gestaltung in sm.css: auf den Tag-Vorschlaegen genauso (Wunsch 07.11.2026)")
check("<audio id=\"tgplay\" controls" in tj and "music + '/audio?' + q" in tj, "Play im Tag-Fenster (MP3 vom Mac)")
check("fetch('/api/sm/recognize', { method: 'POST', body: wavOf(buf, from, secs) })" in tj and "$('tgshuse').onclick" in tj,
      "Shazam-Knopf: Ausschnitt an den Pi, Vorschlag uebernehmen und neu suchen")
check('elif path == "/api/sm/recognize":' in api and "songrec_id.recognize_upload(tf.cmd, h.rfile.read(n))" in api, "Pi: Erkennung eines Ausschnitts")
check("if (document.querySelector('.modal.tagmodal')) return;" in tj and "document.querySelectorAll('.modal.tagmodal').forEach(x => x.remove());" in tj,
      "nur ein Tag-Fenster, Schliessen raeumt alle weg (Fehlerbericht 07.11.2026: Liste blieb gesperrt)")
check("fetch(music + '/lookup?'" in tj and "$('tgsearch').onclick" in tj and "SM.cmd('cover_refresh'" in tj, "Suche nur auf Knopfdruck, Cover am Pi aufgefrischt")
for f in ("install_launcher.sh", os.path.join("..", "helper", "install_helper.sh")):
    check("tag_edit.py" in open(os.path.join(BRIDGE, f), encoding="utf-8").read(), f"{os.path.basename(f)} kopiert tag_edit.py")
# Cover lokal speichern (Wunsch 14.11.2026): Knopf neben "Bild vom Rechner", ausgegraut ohne Cover, Datei "Interpret - Titel.jpg"
check('id="tgsavecv"' in tj and "a.download = base + '.' + ext" in tj and "$('tgsavecv').disabled = !coverData && !coverUrl" in tj,
      "Tag-Editor: Cover speichern (gezeigtes Bild als Datei, ausgegraut ohne Cover)")
finish("Tag-Editor")
