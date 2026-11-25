"""Internetradio am Geraet (Wunsch von Markus 22.11.2026: Radio-Seite am Fernseher, dessen Analogausgang am Line-In des
Licht-Rechners haengt). Der Browser spielt selbst, der Helfer schweigt, der Licht-Rechner liest das Titelfeld mit und stellt
den Eingang solange auf Line-In, danach zurueck."""
import io
import json
import os
import shutil
import tempfile
import threading
import time
import types

from _common import ROOT, check, finish

from showman import radio as rm                  # noqa: E402
from showman.api import ShowManager              # noqa: E402

U1 = "11111111-2222-3333-4444-555555555555"
ST1 = {"stationuuid": U1, "name": "Hitradio Ö3", "url_resolved": "https://example.org/oe3", "favicon": "",
       "country": "Austria", "countrycode": "AT", "tags": "pop", "codec": "MP3", "bitrate": 192, "hls": 0}

# ---- Titelfeld aus ICY-Bloecken --------------------------------------------------------------------
check(rm.icy_title(b"StreamTitle='Falco - Rock Me Amadeus';StreamUrl='';") == "Falco - Rock Me Amadeus", "ICY: Titel gelesen")
check(rm.icy_title("StreamTitle='Seiler und Speer - Ham kummst';".encode("latin-1")) == "Seiler und Speer - Ham kummst", "ICY: latin-1")
check(rm.icy_title("StreamTitle='Bilderbuch - Schick Schock Ö';".encode("latin-1")).endswith("Ö"), "ICY: Umlaut in latin-1")
check(rm.icy_title(b"nix") is None, "ICY: ohne Titel None")


def icy_stream(titles, metaint=100):
    out = b""
    for t in titles:
        m = ("StreamTitle='%s';" % t).encode("utf-8")
        m += b"\0" * (-len(m) % 16)
        out += b"a" * metaint + bytes([len(m) // 16]) + m
    return out + b"a" * metaint + b"\0"


class Resp(io.BytesIO):
    def __init__(self, data, headers):
        super().__init__(data)
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


seen_req = []


def opener(req, timeout):
    seen_req.append(req)
    return Resp(icy_stream(["Werbung - gleich", "Falco - Rock Me Amadeus"]), {"icy-metaint": "100"})


got = []
r = rm.IcyTitle("https://example.org/oe3", got.append, lambda: True, opener=opener, check=lambda u: True)
r.run()
check(got == ["Werbung - gleich", "Falco - Rock Me Amadeus"], "IcyTitle: alle Titel aus dem Strom: %s" % got)
check(seen_req[0].get_header("Icy-metadata") == "1", "fragt nach dem Titelfeld (Icy-MetaData: 1)")
r = rm.IcyTitle("http://192.168.1.10/x", got.append, lambda: True, opener=opener)
r.run()
check(r.error and len(seen_req) == 1, "IcyTitle: nie zu Adressen im Heimnetz")
r = rm.IcyTitle("https://example.org/x", got.append, lambda: True, opener=lambda q, t: Resp(b"aaa", {}), check=lambda u: True)
r.run()
check("kein Titelfeld" in r.error, "Sender ohne icy-metaint: nur Hinweis")

# ---- Radio: Wiedergabe am Geraet ---------------------------------------------------------------------
tmp = tempfile.mkdtemp()
clock = [1000.0]
R = rm.Radio(tmp, opener=lambda req, t: (_ for _ in ()).throw(OSError("offline")), now=lambda: clock[0])
R.icy_opener, R.icy_check = opener, (lambda u: True)            # Test: example.org ohne Namensabfrage

R.play(rm.station(ST1))
check(R.want_info()["play"], "Musik-Rechner: Helfer spielt wie bisher")
R.play(rm.station(ST1), here=True, dev="tv-1")
w = R.want_info()
check(not w["play"] and w["url"], "Ton am Geraet: der Helfer bekommt play False (Mac still)")
check(R.state()["want"]["here"] and R.state()["want"]["dev"] == "tv-1", "Seite sieht, welcher Browser spielt")
check(R.here_report({"dev": "handy", "state": "spielt"}).get("other"), "anderer Browser: soll aufhoeren")
check(not R.playing(), "ohne Meldung des Browsers: spielt nicht")
R.here_report({"dev": "tv-1", "state": "spielt", "line": True})
check(R.playing() and R.here_line(), "Browser spielt, will Line-In")
for _ in range(100):
    if R.song():
        break
    time.sleep(0.02)
song = R.song()
check(song and song["artist"] == "Falco" and song["title"] == "Rock Me Amadeus", "Titel vom Licht-Rechner mitgelesen: %s" % song)
check(R.panel()["artist"] == "Falco", "Hauptpanel zeigt den Titel")
R.report({"state": "aus", "title": "", "seq": 1})                 # Helfer meldet sich weiter (still)
check(R.playing(), "Meldung des stillen Helfers stoert nicht")
clock[0] += rm.REPORT_S + 1
check(not R.playing() and not R.here_line(), "Seite zu (keine Meldung): vorbei")
R.here_report({"dev": "tv-1", "state": "spielt", "line": False})
check(R.playing() and not R.here_line(), "ohne Haken: kein Line-In")
R.stop()
check(not R.here_line() and not R.playing(), "Stopp: vorbei")
R.play(rm.station(ST1), here=True, dev="")
check(not R.want["here"] and R.want_info()["play"], "ohne Kennung: wie bisher am Musik-Rechner")

# ---- Eingang Line-In umschalten und zurueck -----------------------------------------------------------
NET = "Musik-Rechner (Netzwerk)"


class Src:
    def __init__(self):
        self.dev_name, self.calls = NET, []

    def list_devices(self):
        return [{"index": 0, "name": "default"}, {"index": 2, "name": "USB Audio CODEC: - (hw:2,0)"}, {"index": -1, "name": NET}]

    def configure(self, device=None, **kw):
        self.calls.append(device)
        self.dev_name = device


src = Src()
fk = types.SimpleNamespace(show=types.SimpleNamespace(src=src, note=""), radio=R, line_lock=threading.Lock(), line_sw=None, line_err="")
fk.line_device = lambda: ShowManager.line_device(fk)
fk.line_info = lambda: ShowManager.line_info(fk)
check(fk.line_device() == "USB Audio CODEC: - (hw:2,0)", "Line-In: USB-Soundkarte zuerst, nie der Ton vom Musik-Rechner")
R.play(rm.station(ST1), here=True, dev="tv-1")
R.here_report({"dev": "tv-1", "state": "verbinde", "line": True})
ShowManager.line_tick(fk)
check(src.calls == ["USB Audio CODEC: - (hw:2,0)"], "spielt am Geraet: Eingang auf Line-In")
check(fk.line_info()["auto"] and fk.line_info()["prev"] == NET, "Seite sieht: umgestellt, danach wieder Musik-Rechner")
ShowManager.line_tick(fk)
check(len(src.calls) == 1, "nur einmal umstellen")
R.here_report({"dev": "tv-1", "state": "aus", "line": True})
ShowManager.line_tick(fk)
check(src.calls[-1] == NET and fk.line_sw is None, "Ende: Eingang wieder wie vorher")
# Waehrenddessen von Hand anders gewaehlt: nicht zurueckstellen
R.here_report({"dev": "tv-1", "state": "spielt", "line": True})
ShowManager.line_tick(fk)
src.dev_name = "default"
clock[0] += rm.REPORT_S + 1                      # Fernseher-Seite zu
ShowManager.line_tick(fk)
check(src.dev_name == "default" and src.calls[-1] == "USB Audio CODEC: - (hw:2,0)", "von Hand umgestellt: bleibt so")
# War schon Line-In: danach nichts umstellen
src.dev_name, n = "USB Audio CODEC: - (hw:2,0)", len(src.calls)
R.here_report({"dev": "tv-1", "state": "spielt", "line": True})
ShowManager.line_tick(fk)
R.stop()
ShowManager.line_tick(fk)
check(len(src.calls) == n, "war schon Line-In: nichts umgestellt")
# Simulator: kein Eingang, nichts passiert
fk.show.src = object()
ShowManager.line_tick(fk)
check(True, "Simulator: kein Fehler")

# ---- Seite: Schalter, Meldung, kein Backslash-Problem --------------------------------------------------
js = open(os.path.join(ROOT, "pi", "static", "sm", "radio.js"), encoding="utf-8").read()
html = open(os.path.join(ROOT, "pi", "static", "sm", "radio.html"), encoding="utf-8").read()
check('data-w="here"' in html and 'id="au"' in html and 'id="line"' in html, "Seite: Schalter Ton, Audio-Element, Haken Line-In")
check("radio_here" in js and "sendBeacon" in js and "here: true, dev: DEV" in js, "Seite meldet und schickt die Kennung mit")
core = open(os.path.join(ROOT, "pi", "static", "sm", "core.js"), encoding="utf-8").read()
line = next(l for l in core.splitlines() if "SM.needsSource = " in l).split("=", 1)[1].strip().rstrip(";")
import subprocess                                # noqa: E402
out = subprocess.run(["node", "-e", "const f=%s;console.log([f('/musik'),f('/musik/alben'),f('/musik/radio'),f('/shows')].join())" % line],
                     capture_output=True, text=True).stdout.strip()
check(out == "true,true,false,false", "Hinweis Musik-Daten: auf Musik-Seiten ja, auf dem Internetradio nicht (%s)" % out)
check(".now { display: flex; gap: 14px; align-items: center; height: 96px; }" in html and "cv.style.visibility = 'hidden'" in js
      and "text-overflow: ellipsis; min-height: 1.45em" in html, "Kopfteil mit fester Hoehe: Knoepfe springen nicht, ob mit Cover oder ohne")
check("#hint { min-height: 52px; display: flow-root; }" in html, "Hinweiszeilen (Verbinde, Eingang) mit festem Platz: nichts springt")
# Fernseher-Ansicht (23.11.2026): Kennung des Browsers schlaegt nur bei Fernsehern an
rx = next(l for l in js.splitlines() if "const TV_UA = " in l).split("=", 1)[1].strip().rstrip(";")
uas = {"Mozilla/5.0 (Linux; Android 12; Chromecast HD) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36 CrKey/1.56": True,
       "Mozilla/5.0 (Linux; Android 11; BRAVIA 4K VH2) AppleWebKit/537.36 Chrome/118 Mobile Safari/537.36": True,
       "Mozilla/5.0 (Linux; Android 10; AFTKA) AppleWebKit/537.36 Silk/120": True,
       "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 SamsungBrowser/4.0 TV Safari/537.36": True,
       "Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 Chrome/87 Safari/537.36 WebAppManager": True,
       "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36": False,
       "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1": False,
       "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15": False}
out = subprocess.run(["node", "-e", "const r=%s;console.log(JSON.stringify(%s.map(u=>r.test(u))))" % (rx, json.dumps(list(uas)))],
                     capture_output=True, text=True).stdout.strip()
check(out == json.dumps(list(uas.values())).replace(" ", ""), "Fernseher erkannt, Handy/iPad/Mac nicht: %s" % out)
check("body.tv #where, body.tv #herebox, body.tv #editbtn, body.tv #findcard { display: none !important; }" in html and 'id="tvbtn"' in html,
      "Fernseher-Ansicht blendet Ton-Schalter, Haken, Bearbeiten und Senderliste aus")
check("const where = () => TV ? 'here' : WHERE;" in js and 'tabindex="0" role="button"' in js and "e.key === 'Enter'" in js,
      "Fernseher-Ansicht: Ton immer auf dem Geraet, Plaetze mit der Fernbedienung waehlbar")
shutil.rmtree(tmp, ignore_errors=True)
finish("test_radio_hier")
