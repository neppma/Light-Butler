"""Internetradio (Seite /musik/radio, Wunsch von Markus 21.11.2026). Licht-Rechner: Senderliste (radio-browser), Plaetze,
Favoriten, gewuenschter Sender, Meldung des Helfers, Titelfeld -> Genre und Cover (iTunes), Licht-Stil, Matrix-Bilder,
Logos nur aus dem Internet. Musik-Rechner: Titelfeld (ICY) aus dem Strom, ganzer Durchlauf mit eigenem kleinen Sender."""
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from _common import ROOT, build, check, finish

import settings                                  # noqa: E402
from showman import radio as rm                  # noqa: E402
from showman.api import ShowManager              # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import radio_play as rp                          # noqa: E402

U1 = "11111111-2222-3333-4444-555555555555"
U2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ST1 = {"stationuuid": U1, "name": "Hitradio Ö3", "url_resolved": "https://example.org/oe3", "favicon": "https://example.org/oe3.png",
       "country": "Austria", "countrycode": "AT", "tags": "pop,orf", "codec": "MP3", "bitrate": 192, "hls": 0, "votes": 5}
ST2 = dict(ST1, stationuuid=U2, name="FM4", favicon="http://192.168.1.10/logo.png")
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 50
JPG = b"\xff\xd8\xff" + b"y" * 50

# ---- Sender pruefen --------------------------------------------------------------------------------
s = rm.station(ST1)
check(s["uuid"] == U1 and s["name"] == "Hitradio Ö3" and s["cc"] == "AT" and s["kbps"] == 192 and s["logo"].startswith("https"), "Sender: Kurzform")
for bad in (dict(ST1, url_resolved="javascript:alert(1)", url=""), dict(ST1, stationuuid="x"), "kein dict", dict(ST1, url_resolved="", url="")):
    check(rm.station(bad) is None, "ungueltiger Sender abgelehnt")
check(rm.station(dict(ST1, favicon="data:image/png;base64,xx"))["logo"] == "", "Logo nur http/https")

# ---- Titelfeld ---------------------------------------------------------------------------------------
check(rm.split_title("Falco - Rock Me Amadeus") == ("Falco", "Rock Me Amadeus"), "Interpret - Titel")
check(rm.split_title("Seiler und Speer – Ham kummst") == ("Seiler und Speer", "Ham kummst"), "Gedankenstrich")
for t in ("Dilemma Halbzeit", "", "Werbung - gleich gehts weiter", "Nachrichten - 12 Uhr", " - x"):
    check(rm.split_title(t) == (None, None), "kein Lied: " + repr(t))

# ---- Adressen im Heimnetz nie -------------------------------------------------------------------------
check(not rm.public_host("http://192.168.1.10/x.png") and not rm.public_host("http://127.0.0.1/x") and not rm.public_host("file:///etc/passwd")
      and not rm.public_host("http://localhost/x"), "Logos nie aus dem Heimnetz oder von localhost")

# ---- Radio mit nachgebautem Internet -----------------------------------------------------------------
calls = []


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


fail_first = [True]


def opener(req, timeout):
    url = req.full_url
    calls.append(url)
    if "radio-browser" in url:
        if "de1." in url and fail_first[0]:
            fail_first[0] = False
            raise OSError("de1 weg")
        if "/json/countries" in url:
            return Resp(json.dumps([{"name": "Austria", "iso_3166_1": "AT", "stationcount": 400}, {"name": "X", "iso_3166_1": "XX", "stationcount": 0}]).encode())
        if "/json/tags" in url:
            return Resp(json.dumps([{"name": "pop", "stationcount": 900}, {"name": "rar", "stationcount": 3}]).encode())
        if "/json/stations/search" in url:
            return Resp(json.dumps([ST1, ST2, {"stationuuid": "kaputt"}]).encode())
        if "/json/url/" in url:
            return Resp(b"{}")
    if "itunes.apple.com/search" in url:
        check("term=Falco+Rock+Me+Amadeus" in url, "iTunes bekommt nur Interpret und Titel")
        return Resp(json.dumps({"results": [{"artistName": "Falco", "primaryGenreName": "Pop",
                                             "artworkUrl100": "https://is1-ssl.mzstatic.com/a/100x100bb.jpg"}]}).encode())
    if "mzstatic.com" in url:
        check("300x300bb" in url, "Cover in 300 px")
        return Resp(JPG)
    if url == "https://example.org/oe3.png":
        return Resp(PNG)
    raise OSError("unerwartet: " + url)


base = tempfile.mkdtemp()
now = [1000.0]
r = rm.Radio(base, opener=opener, now=lambda: now[0])
st = r.search("AT", "", "")
check([x["uuid"] for x in st] == [U1, U2], "Suche: Sender, kaputte weggelassen")
check(any("de1." in c for c in calls) and any("de2." in c and "countrycode=AT" in c for c in calls), "zweiter Server, wenn der erste nicht antwortet")
n = len(calls)
r.search("AT", "", "")
check(len(calls) == n, "Antworten 10 min gemerkt")
check(r.countries() == [{"cc": "AT", "name": "Austria", "n": 400}], "Laender mit Sendern")
check(r.tags() == ["pop"], "nur haeufige Genres")
r.cache.clear()
_op = r.opener
r.opener = lambda req, timeout: Resp(json.dumps([{"name": n, "stationcount": 99} for n in ("rock", "Ambient", "pop", "dance", "pop")]).encode())
check(r.tags() == ["Ambient", "dance", "pop", "rock"], "Genres alphabetisch, doppelte einmal")
r.opener = _op
r.cache.clear()
check(r.data["cc"] == "AT", "Land gemerkt")

r.slot_set(1, ST1)
r.slot_set(12, ST2)
for bad in ((0, ST1), (13, ST1), ("x", ST1), (2, {"name": "ohne"})):
    try:
        r.slot_set(*bad)
        check(False, "ungueltiger Platz abgelehnt %r" % (bad[0],))
    except ValueError:
        pass
r.fav(ST2, True)
r2 = rm.Radio(base, opener=opener)
check(set(r2.data["slots"]) == {"1", "12"} and U2 in r2.data["favs"] and r2.data["cc"] == "AT", "Plaetze, Favoriten, Land nach dem Neustart")
r.slot_clear(12)
r.fav(ST2, False)
check("12" not in r.data["slots"] and not r.data["favs"], "Platz leeren, Favorit weg")

check(not r.want_info()["play"], "Start: nichts spielt")
r.play(slot=1)
w = r.want_info()
check(w["play"] and w["url"] == "https://example.org/oe3" and w["seq"] == 1 and w["uuid"] == U1, "Platz 1 spielen")
try:
    r.play(slot=5)
    check(False, "leerer Platz")
except ValueError:
    check(True, "leerer Platz abgelehnt")
r.volume(1.7)
check(r.want_info()["vol"] == 1.0, "Lautstaerke begrenzt")
r.stop()
check(not r.want_info()["play"] and r.want_info()["seq"] == 2, "Stopp")
r.play()
check(r.want_info()["play"] and r.want_info()["uuid"] == U1 and r.want_info()["seq"] == 3, "Abspielen ohne Wahl: zuletzt gehoerter Sender")

# Meldung des Helfers, Titelfeld
check(r.song() is None and not r.alive(), "ohne Helfer kein Lied")
r.report({"state": "spielt", "title": "Dilemma Halbzeit", "seq": 3})
check(r.alive() and r.playing() and r.song() is None, "Sendung ist kein Lied")
check(r.panel()["info"] == "Dilemma Halbzeit" and r.panel()["title"] == "", "Hauptpanel: Sendung als Info")
r.report({"state": "spielt", "title": "Falco - Rock Me Amadeus", "seq": 3, "kbps": "192"})
for _ in range(100):
    if (r.song_info.get(("Falco", "Rock Me Amadeus")) or {}).get("genre"):
        break
    time.sleep(0.01)
sg = r.song()
check(sg == {"artist": "Falco", "title": "Rock Me Amadeus", "genre": "Pop", "station": "Hitradio Ö3", "uuid": U1, "done": True}, "Lied mit Genre: %s" % sg)
check(r.cover("Falco", "Rock Me Amadeus") == JPG, "Cover gemerkt")
pn = r.panel()
check(pn["st"] == "Hitradio Ö3" and pn["artist"] == "Falco" and pn["genre"] == "Pop" and pn["cover"] and pn["logo"], "Hauptpanel: Sender, Titel, Genre, Cover")
check(sg["done"] is True if "done" in sg else r.song()["done"], "Lied: Suche fertig (Matrix holt die Bilder dann neu)")
check(r.state()["song"]["done"] and r.state()["song"]["genre"] == "Pop", "Seite: Suche fertig")
check(rm.FEAT_RE.sub("", "Felix Jaehn feat. Ray Dalton") == "Felix Jaehn" and rm.FEAT_RE.sub("", "Simon & Garfunkel") == "Simon", "feat. und & fuer den Abgleich weg")
r.report({"state": "quatsch", "title": "x" * 999, "seq": "abc"})
check(r.rep["state"] == "" and len(r.rep["title"]) == 200 and r.rep["seq"] == 0, "Meldung als ungepruefte Daten")
r.report({"state": "spielt", "title": "Falco - Rock Me Amadeus", "seq": 3})
now[0] += 10
check(not r.alive() and r.song() is None, "Helfer meldet sich nicht mehr: kein Lied")
now[0] -= 10

# Logos
rm_getaddr = rm.socket.getaddrinfo
rm.socket.getaddrinfo = lambda h, p, **k: [(0, 0, 0, "", ("93.184.216.34" if h == "example.org" else "192.168.1.10", p))]
check(r.logo(U1) == PNG and os.path.isfile(os.path.join(base, "_radio_logos", U1 + ".img")), "Logo geholt und abgelegt")
n = len(calls)
check(r.logo(U1) == PNG and len(calls) == n, "Logo aus der Ablage")
check(r.logo(U2) is None and not any("192.168.1.10" in c for c in calls), "Logo im Heimnetz: nie geholt")
check(r.logo("../../etc") is None, "Kennung geprueft")
rm.socket.getaddrinfo = rm_getaddr

# Showmanager: Befehle und Matrix-Bilder
fk = types.SimpleNamespace(radio=r)
check("slots" in ShowManager.radio_op(fk, "radio_vol", {"v": 0.5}) and r.want["vol"] == 0.5, "Befehl radio_vol")
check(ShowManager.radio_op(fk, "radio_report", {"state": "spielt", "title": "Falco - Rock Me Amadeus"}) == {"ok": True}, "Befehl radio_report")
try:
    ShowManager.radio_op(fk, "radio_boese", {})
    check(False, "unbekannter Befehl")
except ValueError:
    check(True, "unbekannter Radio-Befehl abgelehnt")
tmpd = tempfile.mkdtemp()
with open(os.path.join(tmpd, "falco.jpg"), "wb") as fh:
    fh.write(b"ART")
mk = types.SimpleNamespace(radio=r, artists=types.SimpleNamespace(path=lambda k: os.path.join(tmpd, k + ".jpg")))
got = ShowManager.matrix_pictures(mk, {"radio": {"artist": "Falco", "title": "Rock Me Amadeus", "uuid": U1}})
check(got == [("titel", JPG), ("interpret", b"ART"), ("sender", PNG)], "Matrix: Cover, Interpret, Senderlogo")

# Hauptpanel und Matrix
rig, sh = build()
check(sh.snapshot()["radio"] is None, "ohne Radio: nichts im Hauptpanel")
sh.radio = types.SimpleNamespace(panel=lambda: {"st": "X"}, song=lambda: {"artist": "A", "title": "B", "genre": "", "uuid": U1, "done": False})
check(sh.snapshot()["radio"] == {"st": "X"}, "Hauptpanel bekommt das Radio")
import webpanel                                  # noqa: E402
pg0 = webpanel.make_page()
check("const R=S.radio,L=S.local;" in pg0 and "'<b>Radio</b><i>'" in pg0 and "/api/sm/radio_cover?k=" in pg0 and "/api/sm/radio_logo?u=" in pg0,
      "Hauptpanel: Radio-Zeile und Cover (sonst Senderlogo)")
got_s = []
sh.matrix = types.SimpleNamespace(tick=lambda s_, cfg: got_s.append(s_["song"]))
sh.update(1000.0)
check(got_s and got_s[-1]["title"].endswith("(sucht)"), "Matrix: Lied noch ohne Cover hat eigenen Schluessel")
sh.radio.song = lambda: {"artist": "A", "title": "B", "genre": "", "uuid": U1, "done": True}
sh.update(1000.025)
check(got_s[-1]["title"] == "A - B", "Matrix: nach der Suche neuer Schluessel, Bilder werden neu geholt")

# Licht-Stil nach Genre (nur mit Radio, Mixxx und Stil von Hand gehen vor)
dflt = {d.key: d.default for d in settings.DEFS}
check(dflt["radio_style"] == 1.0, "radio_style Standard an")
rig, sh = build()
check(sh._style_key() is None, "ohne Radio kein Stil")
sh.radio = types.SimpleNamespace(song=lambda: {"artist": "A", "title": "B", "genre": "Rock"})
check(sh._style_key() == sh.gstyles.style("Rock") and sh._style_key() is not None, "Radio: Stil nach Genre")
sh.cfg.set("radio_style", 0)
check(sh._style_key() is None, "Schalter aus: kein Stil")
sh.cfg.set("radio_style", 1)
sh.style_man = "ruhig"
check(sh._style_key() == "ruhig", "Stil von Hand geht vor")
sh.style_man = None
sh.mx = {"plan": True, "deck": 1, "playing": True, "title": "Mixxx-Lied", "genre": "Schlager", "grp": ""}
check(sh._style_key() == sh.gstyles.style("Schlager"), "Mixxx geht vor")

# ---- Musik-Rechner: Titelfeld aus dem Strom ------------------------------------------------------------
check(rp.parse_meta(b"StreamTitle='Falco - Jeanny';StreamUrl='';") == "Falco - Jeanny", "StreamTitle lesen")
check(rp.parse_meta("StreamTitle='Ö3 - Wecker';".encode("latin-1")) == "Ö3 - Wecker", "Latin-1")
check(rp.parse_meta(b"\x00" * 16) is None, "leere Metadaten")
meta = b"StreamTitle='A - B';"
meta += b"\x00" * (-len(meta) % 16)
stream = b"a" * 10 + bytes([len(meta) // 16]) + meta + b"b" * 10 + b"\x00" + b"c" * 10 + b"\x00" + b"dd"
titles = []
for cut in (1, 3, 7, 100):
    titles.clear()
    audio = b"".join(rp.icy_split([stream[i:i + cut] for i in range(0, len(stream), cut)], 10, titles.append))
    check(audio == b"a" * 10 + b"b" * 10 + b"c" * 10 + b"dd" and titles == ["A - B"], "ICY zerlegt (Stuecke zu %d Byte)" % cut)
check(b"".join(rp.icy_split([b"xyz"], 0, titles.append)) == b"xyz", "ohne Titelfeld: alles Ton")

# ---- Ganzer Durchlauf: eigener kleiner Sender, nachgebauter Licht-Rechner, UDP-Empfaenger ---------------
ff = rp.find_ffmpeg()
if ff:
    mp3 = subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=120", "-ac", "2", "-ar", "44100", "-b:a", "128k",
                          "-f", "mp3", "pipe:1"], capture_output=True, timeout=30).stdout
    MI = 4000
    body = b""
    for i in range(0, len(mp3), MI):
        part = mp3[i:i + MI]
        body += part
        if len(part) == MI:
            m = b"StreamTitle='Test - Sinus';" if i == 0 else b""
            m += b"\x00" * (-len(m) % 16)
            body += bytes([len(m) // 16]) + m
    reports, want = [], {"seq": 1, "play": True, "url": "", "uuid": U1, "name": "Testsender", "hls": 0, "vol": 0.5}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/api/sm/radio_want":
                b = json.dumps(want).encode()
                self.send_response(200)
            elif self.path == "/stream":
                b = body
                self.send_response(200)
                self.send_header("icy-metaint", str(MI))
                self.send_header("icy-br", "128")
                self.send_header("Content-Type", "audio/mpeg")
            else:
                b = b""
                self.send_response(404)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            try:
                self.wfile.write(b)
            except OSError:
                pass                              # Sender gewechselt: Verbindung zu

        def do_POST(self):
            reports.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    want["url"] = f"http://127.0.0.1:{port}/stream"
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(0.05)
    written, out_threads = [], set()

    class Out:
        def __init__(self, **k):
            out_threads.add(threading.get_ident())

        def start(self):
            pass

        def write(self, x):
            out_threads.add(threading.get_ident())
            written.append(x.copy())
            time.sleep(len(x) / 44100 / 4)        # vierfach schneller als Echtzeit

        def stop(self):
            pass

        def close(self):
            pass

    pl = rp.RadioPlayer("127.0.0.1", web=port, port=rx.getsockname()[1], log=lambda m: None,
                        sd_mod=types.SimpleNamespace(OutputStream=Out), ffmpeg=ff)
    pl.start()
    got_pk = 0
    t_end = time.time() + 8
    while time.time() < t_end and not any(x.get("state") == "fehler" for x in reports[-1:]):
        try:
            rx.recv(4096)
            got_pk += 1
        except (socket.timeout, BlockingIOError):
            pass
        if got_pk > 300 and pl.title:
            break
    check(pl.title == "Test - Sinus", "Titelfeld aus dem Strom: " + repr(pl.title))
    check(got_pk > 300, "Ton geht per UDP an den Licht-Rechner (%d Pakete)" % got_pk)
    pcm = __import__("numpy").concatenate(written) if written else None
    check(pcm is not None and 0.02 < float(abs(pcm).max()) < 0.5, "Ton ausgepackt, Lautstaerke 50 % angewendet")
    t_end = time.time() + 3
    while time.time() < t_end and not any(x.get("state") == "spielt" for x in reports):
        time.sleep(0.05)
    check(pl.playing() and any(x.get("state") == "spielt" for x in reports), "Helfer meldet: spielt")
    t_end = time.time() + 3
    while time.time() < t_end and not any(x.get("title") == "Test - Sinus" for x in reports):
        time.sleep(0.05)
    check(any(x.get("title") == "Test - Sinus" and x.get("op") == "radio_report" for x in reports), "Titel an den Licht-Rechner gemeldet")
    # Fehlerbericht 21.11.2026: schnell hintereinander Sender gewechselt, danach hing alles bei "verbinde"
    for k in range(12):
        want.update(seq=100 + k)
        time.sleep(0.15 if k % 3 else 1.05)
    t_end = time.time() + 8
    while time.time() < t_end and not (pl.seq == 111 and pl.state == "spielt"):
        time.sleep(0.05)
    n_w = len(written)
    time.sleep(0.6)
    check(pl.seq == 111 and pl.state == "spielt" and len(written) > n_w, "nach 12 schnellen Senderwechseln spielt der letzte Sender")
    check(pl.opened == 1 and len(out_threads) == 1, "Ton-Ausgang nur einmal geoeffnet, nur ein Faden (%d, %d)" % (pl.opened, len(out_threads)))
    check(len([t for t in threading.enumerate() if "_decode" in str(getattr(t, "_target", ""))]) <= 2, "alte Sender-Faeden beendet")
    want.update(play=False, seq=200)
    t_end = time.time() + 4
    while time.time() < t_end and pl.state != "aus":
        time.sleep(0.05)
    check(pl.state == "aus" and not pl.playing(), "Stopp vom Licht-Rechner")
    want.update(play=True, seq=201, url="http://127.0.0.1:1/weg")
    t_end = time.time() + 6
    while time.time() < t_end and pl.state != "fehler":
        time.sleep(0.05)
    check(pl.state == "fehler" and pl.err, "nicht erreichbarer Sender: Fehler gemeldet, Helfer laeuft weiter")
    pl.stop()
    srv.shutdown()
    rx.close()
else:
    print("  (ffmpeg fehlt: Durchlauf nicht geprueft)")

# BlackHole-Weiterleitung: waehrend das Radio spielt nur stumm (Eingang bleibt offen, kein Oeffnen/Schliessen in Core Audio)
import audio_send                                # noqa: E402
sent = []
snd = audio_send.AudioSender("127.0.0.1", sock=types.SimpleNamespace(sendto=lambda p, a: sent.append(p)), mute=lambda: True)
snd.addr, snd.addr_t = ("127.0.0.1", 9), time.monotonic()
snd.feed(__import__("numpy").zeros((512, 2), dtype="float32"), 44100)
check(not sent, "Radio spielt: BlackHole schickt nichts")
snd.mute = lambda: False
snd.feed(__import__("numpy").zeros((512, 2), dtype="float32"), 44100)
check(len(sent) == 2, "Radio aus: BlackHole schickt wieder")
check("mute=(radio.playing" in open(os.path.join(ROOT, "mac", "helper", "helper.py"), encoding="utf-8").read(), "Helfer: BlackHole stumm statt geschlossen")

# Installation: der Helfer bekommt radio_play.py
txt = open(os.path.join(ROOT, "mac", "helper", "install_helper.sh"), encoding="utf-8").read()
check('"$SRC/radio_play.py"' in txt, "Helfer-Installation kopiert radio_play.py")
check("os._exit(code or 0)" in open(os.path.join(ROOT, "mac", "helper", "helper.py"), encoding="utf-8").read(), "Helfer endet immer (auch wenn Core Audio haengt)")
check("radio_play import RadioPlayer" in open(os.path.join(ROOT, "mac", "helper", "helper.py"), encoding="utf-8").read(), "Helfer startet das Radio")
import webpanel                                  # noqa: E402
pg = webpanel.make_page()
check('<a id="rdbtn" href="/musik/radio"' in pg and pg.find('id="djbtn"') < pg.find('id="rdbtn"') < pg.find('id="dbbtn"'), "Hauptseite: runder Radio-Knopf neben dem Auto-DJ")
check("#rdbtn{" in pg and "border-radius:50%" in pg and "#djbtn,#rdbtn{display:none" in pg, "rund wie die anderen, auf dem Handy ausgeblendet wie sie")
shutil.rmtree(base, ignore_errors=True)
finish("test_radio")
