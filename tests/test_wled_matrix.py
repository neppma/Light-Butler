"""Pixel-Matrix per DDP (wled_matrix.py, Wunsch von Markus 21.11.2026, Testgeraet WLED 32 x 32).
Standard aus; aufs uebrige Licht wirkt sie nie; ohne Strobe-Erlaubnis hoechstens 2 Ausloeser pro Sekunde;
BLACKOUT schwarz, FREEZE steht, Szene Laser schwarz; beim Ausschalten und Dienstende schwarze Bilder; Trockenlauf sendet nie."""
import json
import os
import socket
import tempfile

import numpy as np

from _common import DT, build, check, finish

import settings                              # noqa: E402
import wled_matrix as wm                     # noqa: E402

# ---- DDP-Pakete ------------------------------------------------------------------------------
data = bytes(range(256)) * 12                 # 3072 Byte = 32 x 32 RGB
pk = wm.ddp_packets(data, 5)
check(len(pk) == 3 and [len(p) - 10 for p in pk] == [1440, 1440, 192], "32 x 32 = drei Pakete")
check([p[0] for p in pk] == [0x40, 0x40, 0x41] and all(p[1] == 5 and p[3] == 1 for p in pk), "Version 1, PUSH nur im letzten, Sequenz")
check([int.from_bytes(p[4:8], "big") for p in pk] == [0, 1440, 2880], "Versatz je Paket")
check(b"".join(p[10:] for p in pk) == data, "Daten vollstaendig")

# ---- Adresse ---------------------------------------------------------------------------------
check(wm.check_host(" 192.168.0.52 ") == "192.168.0.52" and wm.check_host("") == "" and wm.check_host("wled-matrix.local") == "wled-matrix.local",
      "Adresse: IP, Name, leer")
for bad in ("224.0.0.1", "0.0.0.0", "../x", "a b", "::1", "x" * 80):
    try:
        wm.check_host(bad)
        check(False, "ungueltige Adresse abgelehnt: " + bad)
    except ValueError:
        pass

# ---- Reihenfolge: Drehung, Schlangenlinie ----------------------------------------------------
f = np.zeros((2, 3, 3))
f[0, 0] = (1, 0, 0)                            # oben links rot
b = wm.to_bytes(f, 1.0)
check(b[:3] == bytes([255, 0, 0]) and len(b) == 18, "ohne Drehung: erstes Pixel oben links")
b = wm.to_bytes(f, 1.0, serp=True)
f2 = np.zeros((2, 3, 3)); f2[1, 0] = (0, 0, 1)
check(wm.to_bytes(f2, 1.0, serp=True)[15:18] == bytes([0, 0, 255]), "Schlangenlinie: zweite Zeile andersherum")
check(wm.to_bytes(f, 0.5)[:3] == bytes([128, 0, 0]), "Helligkeit")
check(len(wm.to_bytes(f, 1.0, rot=1)) == 18, "Drehung behaelt die Pixelzahl")

# ---- Standard aus ----------------------------------------------------------------------------
dflt = {d.key: d.default for d in settings.DEFS}
check(dflt["pm_on"] == 0.0 and dflt["pm_pattern"] == 0.0, "Pixel-Matrix: Standard aus, Muster Auto")

# ---- Empfaenger auf dem eigenen Rechner ------------------------------------------------------
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", 0))
rx.settimeout(0.05)
port = rx.getsockname()[1]


def drain():
    n = []
    while True:
        try:
            n.append(rx.recv(2000))
        except (socket.timeout, BlockingIOError):
            return n


tmp = tempfile.mkdtemp()
mpath = os.path.join(tmp, "matrix.json")


def run(sh, secs, cb=None):
    t = 1000.0
    for i in range(int(secs / DT)):
        sh.update(t)
        if cb:
            cb(sh, t)
        t += DT
    return t


# Aufs uebrige Licht wirkt die Matrix nie: dieselben DMX-Bilder mit und ohne
def frames(with_matrix):
    rig, sh = build(seed=3)
    if with_matrix:
        sh.matrix = wm.Matrix(mpath, port=port)
        sh.matrix.set_host("127.0.0.1")
        sh.cfg.set("pm_on", 1)
    out = []
    run(sh, 40, lambda s, t: out.append(bytes(rig.render_all()[rig.target])))
    return out, sh


a, _ = frames(False)
bm, shm = frames(True)
check(a == bm, "DMX Bild fuer Bild gleich mit und ohne Pixel-Matrix")
check(shm.matrix is not None and shm.matrix.sender.sent > 1500 and shm.matrix.sender.errors == 0, "40 s: jedes Bild gesendet")
got = drain()
check(len(got) >= 3 and len(got[-1]) - 10 == 192 and got[-1][0] & 1, "Empfaenger bekommt DDP mit PUSH")
check(json.load(open(mpath)) == {"ip": "127.0.0.1"}, "Adresse in matrix.json")
check(wm.Matrix(mpath).host == "127.0.0.1", "Adresse nach dem Neustart wieder da")

# Ausschalten: schwarze Bilder, danach nichts mehr
shm.cfg.set("pm_on", 0)
run(shm, 0.2)
got = drain()
check(got and all(not any(p[10:]) for p in got), "Ausschalten: nur schwarze Bilder")
run(shm, 1.0)
check(not drain(), "aus: nichts mehr gesendet")

# Trockenlauf: nie senden, aber Vorschau
rig, sh = build(seed=3)
sh.matrix = wm.Matrix(None, dry=True, port=port)
sh.matrix.host = "127.0.0.1"
sh.cfg.set("pm_on", 1)
sh.matrix.info(sh.cfg, 1000.0)
run(sh, 2.0)
check(not drain() and sh.matrix.sender is None, "Trockenlauf sendet nie")
inf = sh.matrix.info(sh.cfg, 1002.0)
check(inf["dry"] and inf["w"] == 32 and len(inf["px"]) > 100, "Vorschau im Trockenlauf")

# Ohne Adresse: nichts senden, ohne offene Seite auch nicht rechnen
rig, sh = build(seed=3)
sh.matrix = wm.Matrix(None, port=port)
sh.cfg.set("pm_on", 1)
run(sh, 1.0)
check(sh.matrix.sender is None and not sh.matrix.last.any(), "ohne Adresse: kein Versand, keine Rechnung")


# ---- Blitzgrenze -----------------------------------------------------------------------------
def rises(strobe, pattern, secs=60):
    rig, sh = build(seed=5, strobe=strobe)
    sh.matrix = wm.Matrix(None, dry=True)
    sh.cfg.set("pm_on", 1)
    sh.cfg.set("pm_pattern", pattern)
    mean = []

    def cb(s, t):
        s.matrix.preview_until = t + 10
        mean.append(float(s.matrix.last.mean()) / 255.0)
    run(sh, secs, cb)
    ev, low, last = [], mean[0], -1e9
    for i, m in enumerate(mean):           # Anstieg = mindestens 0,15 heller als der Tiefpunkt davor
        low = min(low, m)
        if m - low >= 0.15:
            ev.append(i * DT)
            low = m
    worst = max((sum(1 for e in ev if t0 <= e < t0 + 1.0) for t0 in ev), default=0)
    return worst


for p in range(6):
    w = rises(False, p)
    check(w <= 2, "ohne Strobe-Erlaubnis hoechstens 2 Anstiege pro Sekunde, Muster %d: %d" % (p, w))
fx = wm.MatrixFx()
n = 0
for i in range(80):                          # Beat in jedem Bild: Ausloeser hoechstens alle 0,5 s
    s = {"t": i * DT, "dt": DT, "bpm": 128, "beat": True, "kick": True, "hat": True, "strobe": False}
    fx.ringe(s)
n_rings = len(fx.rings)
check(n_rings <= 4, "2 s Dauer-Beat ohne Erlaubnis: hoechstens 4 Ringe (%d)" % n_rings)
for strobe, want in ((False, 4), (True, 16)):
    fx = wm.MatrixFx()
    n = sum(fx._trigger_ok({"t": i * DT, "strobe": strobe}) for i in range(80))
    check(n == want, "2 s Ausloeser %s Strobe-Erlaubnis: %d" % ("mit" if strobe else "ohne", n))

# ---- Bewegung auf dem Beat (Rueckmeldung 21.11.2026: Tunnel lief gleichmaessig, nicht zur Musik) ---------
for pat in ("tunnel", "plasma"):
    fx = wm.MatrixFx()
    early, late, prev = [], [], None
    for i in range(int(8 / DT)):
        t = i * DT
        beat = i % 20 == 0                         # 120 BPM
        f_ = fx.render({"t": t, "dt": DT, "bpm": 120, "beat": beat, "pattern": pat, "level": 0.5, "hue": 0.2})
        if prev is not None and i > 40:
            ch_ = float(np.abs(f_ - prev).mean())
            (early if i % 20 < 5 else late).append(ch_)
        prev = f_.copy()
    e, l_ = sum(early) / len(early), sum(late) / len(late)
    check(e > 2.5 * l_, "%s: Bewegung direkt nach dem Beat viel staerker als dazwischen (%.4f / %.4f)" % (pat, e, l_))
fx = wm.MatrixFx()
for i in range(40):
    fx.render({"t": i * DT, "dt": DT, "bpm": 120, "beat": i % 20 == 0, "pattern": "tunnel"})
check(abs(fx.step_target - 2.0) < 1e-9 and abs(fx.tun - fx.step_cur) < 1e-6, "Tunnel: je Beat ein Ring")
fx = wm.MatrixFx()
for i in range(200):
    fx.render({"t": i * DT, "dt": DT, "bpm": 0, "pattern": "tunnel"})
check(fx.step_cur > 0.5, "ohne Beat laeuft der Tunnel langsam weiter")

# ---- Blackout, Freeze, Laser, Alles hell -------------------------------------------------------
fx = wm.MatrixFx()
s = {"t": 1.0, "dt": DT, "bpm": 120, "level": 0.8, "hue": 0.3, "state": "normal", "tier": 2}
on = fx.render(dict(s, beat=True))
check(on.max() > 0.2, "Muster leuchtet")
check(not fx.render(dict(s, override="blackout")).any(), "BLACKOUT schwarz")
fr = fx.render(dict(s, t=2.0)).copy()
check(np.array_equal(fx.render(dict(s, t=5.0, frozen=True)), fr), "FREEZE: Bild steht")
check(not fx.render(dict(s, dark=True)).any(), "Szene Laser: Matrix schwarz")
check(fx.render(dict(s, override="allbright")).min() > 0.5, "ALLES HELL: weiss")
check(not np.any(fx.render(dict(s, cmode="uv"))[..., 1] > 0.01), "UV: kein Gruen")
for pat in wm.PATTERNS:
    for st in ("idle", "gap", "break", "build", "drop", "normal"):
        r = fx.render(dict(s, pattern=pat, state=st))
        check(r.shape == (32, 32, 3) and np.isfinite(r).all() and r.min() >= 0 and r.max() <= 1, "Muster %s / %s gueltig" % (pat, st))
fx.resize(16, 8)
check(fx.render(dict(s)).shape == (8, 16, 3), "andere Groesse")
t = fx.test({})
check(tuple(t[0, 0]) == (1, 0, 0) and tuple(t[0, -1]) == (0, 1, 0) and tuple(t[-1, 0]) == (0, 0, 1), "Testbild: Ecken rot, gruen, blau")

# In der Show: Blackout und Laser-Szene machen die Matrix dunkel
rig, sh = build(seed=3)
sh.matrix = wm.Matrix(None, dry=True)
sh.cfg.set("pm_on", 1)
run(sh, 20, lambda s, t: setattr(s.matrix, "preview_until", t + 10))
check(sh.matrix.last.any(), "Show: Matrix leuchtet zur Musik")
sh.command({"blackout": True})
run(sh, 0.2, lambda s, t: setattr(s.matrix, "preview_until", t + 10))
check(not sh.matrix.last.any(), "Show: BLACKOUT macht die Matrix schwarz")

# Fehler in der Matrix halten die Show nie an
rig, sh = build(seed=3)


class Kaputt:
    def tick(self, s, cfg):
        raise RuntimeError("kaputt")


sh.matrix = Kaputt()
run(sh, 0.5)
check(sh.matrix is None and "Pixel-Matrix" in sh.note, "Fehler: Matrix aus, Show laeuft weiter")

# Befehl matrix_ip
rig, sh = build(seed=3)
sh.matrix = wm.Matrix(os.path.join(tmp, "m2.json"))
sh.command({"matrix_ip": "192.168.0.52"})
check(sh.matrix.host == "192.168.0.52", "Befehl matrix_ip")
try:
    sh.command({"matrix_ip": "nicht gültig!"})
    check(False, "falsche Adresse abgelehnt")
except ValueError:
    check(sh.matrix.host == "192.168.0.52", "falsche Adresse abgelehnt, alte bleibt")

# ---- Bilder zum Lied: Cover, Interpret, Album im Wechsel mit dem Effekt -------------------------
import shutil                                   # noqa: E402
import subprocess                               # noqa: E402
import time as _time                            # noqa: E402
import types                                    # noqa: E402

from showman.api import ShowManager             # noqa: E402

check(dflt["pm_pics"] == 1.0 and dflt["pm_pic_s"] == 4.0 and dflt["pm_pic_every"] == 60.0, "Bilder: Standard an, 4 s, alle 60 s")
RED, GRN, BLU = (np.ones((32, 32, 3)) * c for c in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
fake = {b"r": RED, b"g": GRN, b"b": BLU}
calls = []


def provider(song):
    calls.append(dict(song))
    return [("titel", b"r"), ("interpret", b"g"), ("album", b"b")]


def wait_pics(pc):
    for _ in range(200):
        if pc.pics:
            return
        _time.sleep(0.01)


pc = wm.Pictures(decode=lambda d, w, h: fake.get(d))
pc.song(("", "Lied", 200, 32, 32), {"title": "Lied", "dur": 200}, provider, 32, 32, 0.0)
wait_pics(pc)
check(len(pc.pics) == 3 and calls == [{"title": "Lied", "dur": 200}], "Bilder im Hintergrund geladen")
seq = []
for i in range(int(80 / DT)):
    t = 10.0 + i * DT
    img, a_ = pc.alpha(t, 4.0, 60.0, True)
    seq.append((t, None if img is None else int(np.argmax(img[0, 0])), a_))
shown = [x for x in seq if x[1] is not None and x[0] < 30]
check(abs(shown[0][0] - 10.0) < 1e-6 and abs(shown[-1][0] - (10.0 + 12.0 - DT)) < 1e-6, "Folge beginnt sofort, 3 x 4 s")
order = [k for i, (_, k, _) in enumerate(shown) if i == 0 or shown[i - 1][1] != k]
check(order[:3] == [0, 1, 2], "Reihenfolge Titel, Interpret, Album")
check(shown[0][2] == 0.0 and max(x[2] for x in shown[:30]) == 1.0, "weich eingeblendet")
again = [x[0] for x in seq if x[1] is not None and x[0] > 30]
check(again and abs(again[0] - (10.0 + 12.0 + 60.0)) < 0.1 if again else False, "wieder nach 60 s Effekt: " + str(again[:1]))
check(all(abs(a_ - b_) < 0.1 for (_, _, a_), (_, _, b_) in zip(shown, shown[1:])), "kein Sprung in der Deckkraft (kein Blitz)")

pc = wm.Pictures(decode=lambda d, w, h: fake.get(d))
pc.song(("", "Lied", 200, 32, 32), {"title": "Lied"}, provider, 32, 32, 0.0)
wait_pics(pc)
check(pc.alpha(1.0, 4.0, 0.0, False)[0] is None, "im Aufbau und beim Drop keine Bilder")
check(pc.alpha(2.0, 4.0, 0.0, True)[0] is not None, "danach kommen sie")
check(pc.alpha(3.0, 4.0, 0.0, False)[0] is None and pc.alpha(4.0, 4.0, 0.0, True)[0] is None, "Drop bricht ab; 0 = nur am Anfang")
pc.song(("", "Neu", 180, 32, 32), {"title": "Neu"}, provider, 32, 32, 5.0)
wait_pics(pc)
check(pc.alpha(5.1, 4.0, 0.0, True)[0] is not None, "neues Lied: Bilder wieder von vorn")
pc.song(None, None, provider, 32, 32, 6.0)
check(not pc.pics and pc.alpha(6.1, 4.0, 0.0, True)[0] is None, "kein Lied: keine Bilder")
pc = wm.Pictures(decode=lambda d, w, h: None)
pc.song(("", "x", 1, 32, 32), {"title": "x"}, provider, 32, 32, 0.0)
_time.sleep(0.1)
check(pc.alpha(1.0, 4.0, 60.0, True)[0] is None, "nicht lesbare Bilder: nur Effekt")
pc = wm.Pictures(decode=lambda d, w, h: fake.get(d))
pc.song(("", "x", 1, 32, 32), {"title": "x"}, lambda song: 1 / 0, 32, 32, 0.0)
_time.sleep(0.1)
check(not pc.pics, "Fehler beim Holen: nur Effekt")

# In der Matrix: Bild deckt den Effekt, nicht beim Testbild, nicht bei BLACKOUT, Schalter aus
mt = wm.Matrix(None, dry=True)
mt.pictures = provider
mt.pics.decode = lambda d, w, h: fake.get(d)
mt.preview_until = 1e9
cfg = settings.Settings(os.devnull)
base = {"dt": DT, "bpm": 120, "state": "normal", "tier": 1, "hue": 0.5, "song": {"title": "Lied", "dur": 200}}
mt.tick(dict(base, t=100.0), cfg)
wait_pics(mt.pics)
mt.tick(dict(base, t=100.5), cfg)
mt.tick(dict(base, t=102.0), cfg)
check(mt.last[16, 16, 0] > 100 and mt.last[16, 16, 1] < 5 and mt.last[16, 16, 2] < 5, "Matrix zeigt das Cover (rot)")
mt.tick(dict(base, t=102.025, override="blackout"), cfg)
check(not mt.last.any(), "BLACKOUT vor dem Bild")
cfg.set("pm_pics", 0)
mt2 = wm.Matrix(None, dry=True)
mt2.pictures = provider
mt2.pics.decode = lambda d, w, h: fake.get(d)
n0 = len(calls)
mt2.preview_until = 1e9
mt2.tick(dict(base, t=1.0), cfg)
check(len(calls) == n0, "Schalter aus: keine Bilder geholt")
cfg.set("pm_pics", 1)
cfg.set("pm_pattern", 6)
mt2.tick(dict(base, t=2.0), cfg)
check(len(calls) == n0, "Testbild: keine Bilder")

# Stille: Matrix blendet dunkel (Rueckmeldung 21.11.2026), Testbild bleibt, Musik zurueck = schnell wieder hell
cfg3 = settings.Settings(os.devnull)
cfg3.set("pm_pics", 0)
mq = wm.Matrix(None, dry=True)
mq.preview_until = 1e9
q = {"dt": DT, "bpm": 120, "tier": 1, "hue": 0.3, "level": 0.5}
for i in range(40):
    mq.tick(dict(q, t=i * DT, state="normal", beat=i % 20 == 0), cfg3)
lit = int(mq.last.max())
for i in range(40, 200):
    mq.tick(dict(q, t=i * DT, state="idle"), cfg3)
check(lit > 30 and int(mq.last.max()) <= 2, "Stille: Matrix dunkel (%d -> %d)" % (lit, int(mq.last.max())))
for i in range(200, 240):
    mq.tick(dict(q, t=i * DT, state="normal", beat=i % 20 == 0), cfg3)
check(int(mq.last.max()) > 30, "Musik zurueck: wieder hell")
for i in range(240, 400):
    mq.tick(dict(q, t=i * DT, state="gap"), cfg3)
check(int(mq.last.max()) <= 2, "Pause im Lied: auch dunkel")
cfg3.set("pm_pattern", 6)
for i in range(400, 460):
    mq.tick(dict(q, t=i * DT, state="idle"), cfg3)
check(int(mq.last.max()) > 30, "Testbild bleibt auch in Stille sichtbar")

# Zustand der Bilder fuer die Seite
pc = wm.Pictures()
pc.song(("", "a", 1, 32, 32), {"title": "a"}, None, 32, 32, 0)
check(pc.status == "nicht verfuegbar", "Zustand: ohne Lieferant")
pc.song(None, None, provider, 32, 32, 0)
check(pc.status.startswith("kein Lied"), "Zustand: kein Lied")
pc = wm.Pictures(decode=lambda d, w, h: fake.get(d))
pc.song(("", "s", 1, 32, 32), {"title": "s"}, provider, 32, 32, 0)
wait_pics(pc)
check(pc.status == "3 Bild(er): titel, interpret, album", "Zustand: Bilder da: " + pc.status)
_ff = wm.find_ffmpeg
wm.find_ffmpeg = lambda: None
pc = wm.Pictures()
pc.song(("", "t", 1, 32, 32), {"title": "t"}, provider, 32, 32, 0)
_time.sleep(0.2)
check("ffmpeg fehlt" in pc.status, "Zustand: ffmpeg fehlt am Licht-Rechner")
wm.find_ffmpeg = _ff
pc = wm.Pictures(decode=lambda d, w, h: fake.get(d))
pc.song(("", "u", 1, 32, 32), {"title": "u"}, lambda song: [], 32, 32, 0)
_time.sleep(0.1)
check(pc.status == "zu diesem Lied gibt es kein Bild", "Zustand: Lied ohne Bild")

# Lieferant im Showmanager: Cover, Interpret, Album; gleiches Bild nur einmal
tmpd = tempfile.mkdtemp()
with open(os.path.join(tmpd, "falco.jpg"), "wb") as fh:
    fh.write(b"ART")
lib = [{"path": "/m/Falco/Best/01.mp3", "title": "Jeanny", "artist": "Falco feat. X", "album": "Best"},
       {"path": "/m/Falco/Best/00.mp3", "title": "Intro", "artist": "Falco", "album": "Best"}]
covers = {"/m/Falco/Best/01.mp3": b"COV1", "/m/Falco/Best/00.mp3": b"COV0"}
fk = types.SimpleNamespace(
    show=types.SimpleNamespace(mixxx=types.SimpleNamespace(library_full=lambda: lib)),
    _lib_path=lambda t, d: "/m/Falco/Best/01.mp3" if t == "Jeanny" else "",
    cover=lambda **k: b"SHOWCOV",
    covers=types.SimpleNamespace(for_path=lambda p: covers.get(p)),
    artists=types.SimpleNamespace(path=lambda k: os.path.join(tmpd, k + ".jpg")),
    albums=types.SimpleNamespace(key_of_path=lambda p: "best", songs=lambda k: {"songs": [{"path": "/m/Falco/Best/00.mp3"}]}))
got = ShowManager.matrix_pictures(fk, {"title": "Jeanny", "dur": 180})
check(got == [("titel", b"COV1"), ("interpret", b"ART"), ("album", b"COV0")], "Lieferant: Cover, Interpret, Album")
covers["/m/Falco/Best/00.mp3"] = b"COV1"
got = ShowManager.matrix_pictures(fk, {"title": "Jeanny", "dur": 180})
check([k for k, _ in got] == ["titel", "interpret"], "gleiches Album-Cover nur einmal")
check(ShowManager.matrix_pictures(fk, {"title": "Unbekannt"}) == [], "unbekanntes Lied: keine Bilder")
check(ShowManager.matrix_pictures(fk, {"show": "x"})[0] == ("titel", b"SHOWCOV"), "Show mit eigener MP3: ihr Cover")

# Echtes Umrechnen mit ffmpeg (falls vorhanden): rotes Bild 64 x 48 -> 32 x 32
ff = shutil.which("ffmpeg")
if ff:
    jpg = subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "color=red:s=64x48", "-frames:v", "1", "-f", "mjpeg", "pipe:1"],
                         capture_output=True, timeout=20).stdout
    im = wm.decode_image(jpg, 32, 32)
    check(im is not None and im.shape == (32, 32, 3) and im[..., 0].mean() > 0.8 and im[..., 1].mean() < 0.2, "ffmpeg: JPEG auf 32 x 32")
    check(wm.decode_image(b"kein bild", 32, 32) is None, "kaputtes Bild: None")
else:
    print("  (ffmpeg fehlt: Umrechnen nicht geprueft)")

rx.close()
finish("test_wled_matrix")
