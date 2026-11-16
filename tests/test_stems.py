"""Pegelkurven der getrennten Spuren: Rechnung am Mac (ohne Demucs, kuenstliche Spuren), Speichern am Pi. Aufs Licht wirkt das nicht."""
import copy
import glob
import os
import sys
import tempfile

import numpy as np

from _common import ROOT, build, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "stems"))
import stem_curves as sc  # noqa: E402
import stems_show as ss  # noqa: E402

from showman.api import ShowManager  # noqa: E402

SR = 44100
LEN = 12 * SR


def burst(t, hz, amp, dur=0.05, n=LEN):
    """Ton ab Sekunde t."""
    x = np.zeros(n, dtype=np.float32)
    a, m = int(t * SR), int(dur * SR)
    x[a:a + m] = amp * np.sin(2 * np.pi * hz * np.arange(m) / SR)
    return x


def at(v, t):
    return float(sc.to_db(v[int(round(t * sc.RATE))]))


def stereo(x):
    return np.stack([x, x], axis=1)


# ---- eine Kurve ----
x = np.zeros(SR * 2, dtype=np.float32)
x[SR] = 0.5                                      # ein einziger Wert genau bei 1,00 s
c = sc.curve(x, SR)
check(len(c) == 200 and c[99] == 0 and c[101] == 0, "Laenge 100 Werte je Sekunde, nur ein Block betroffen")
check(abs(float(sc.to_db(c[100])) + 6.02) < 0.3, "Spitzenwert in dB, kurzer Schlag bleibt erhalten")
check(c[0] == 0 and float(sc.to_db(0)) == sc.DB_MIN, "Stille ist der kleinste Wert")
check(sc.curve(np.ones(SR, dtype=np.float32) * 3.0, SR).max() == 255, "ueber 0 dB bleibt 255")
check(abs(float(sc.to_db(sc.curve(np.stack([burst(1, 440, 0.5, n=SR * 2), burst(1, 440, 0.1, n=SR * 2)], axis=1), SR)[102])) + 6.02) < 0.5, "Stereo: der lautere Kanal zaehlt")
check((sc.unpack(sc.pack(c)) == c).all(), "packen und auspacken")

# ---- fuenf Kurven, Schlagzeug geteilt ----
drums = burst(2, 60, 0.8) + burst(5, 5000, 0.4)
stems = {"vocals": stereo(burst(3, 500, 0.5)), "bass": stereo(burst(4, 50, 0.5)), "drums": stereo(drums),
         "other": stereo(burst(6, 1000, 0.25))}
d = sc.analyse(stems, SR)
cu = {k: sc.unpack(v) for k, v in d["curves"].items()}
check(tuple(sorted(cu)) == tuple(sorted(sc.NAMES)) and len({len(v) for v in cu.values()}) == 1, "fuenf gleich lange Kurven")
check(at(cu["kick"], 2.02) > -4 and at(cu["kick"], 5.02) < -40, "tiefer Schlag in kick, hoher nicht")
check(at(cu["hihat"], 5.02) > -10 and at(cu["hihat"], 2.02) < -40, "hoher Schlag in hihat, tiefer nicht")
check(at(cu["stimme"], 3.02) > -8 and at(cu["stimme"], 4.02) == sc.DB_MIN, "Stimme nur dort, wo sie klingt")
check(at(cu["bass"], 4.02) > -8 and at(cu["sonstiges"], 6.02) > -14, "Bass und Sonstiges")
check(d["duration"] == 12.0 and d["corr"] is None and d["offset_ms"] == 0.0, "ohne Wellenform kein Versatz")
ungleich = dict(stems, bass=stems["bass"][:-100])
check(len(sc.unpack(sc.analyse(ungleich, SR)["curves"]["bass"])) == len(sc.unpack(sc.analyse(ungleich, SR)["curves"]["kick"])), "ungleich lange Spuren")


# ---- Versatz gegen die Wellenform des Browsers ----
def song(seed=1, late_ms=0.0, n=LEN):
    """Unregelmaessige Schlaege, Lage gegen die Referenz um late_ms spaeter."""
    r = np.random.RandomState(seed)
    x = np.zeros(n, dtype=np.float32)
    t = 0.1
    while t < n / SR - 0.5:
        x += burst(t + late_ms / 1000.0, 200 + r.rand() * 800, 0.2 + 0.6 * r.rand(), 0.03, n)
        t += 0.1 + r.rand() * 0.5
    return x


def wave(x):
    """peaks.json wie vom Browser: 50 Hz, Min und Max in -127..127."""
    b = SR // sc.PEAK_RATE
    n = len(x) // b
    m = x[:n * b].reshape(n, b)
    return {"rate": 50, "min": np.rint(m.min(axis=1) * 127).astype(int).tolist(), "max": np.rint(m.max(axis=1) * 127).astype(int).tolist()}


ref = wave(song())
for late in (50.0, 0.0, -30.0):
    lag, corr = sc.measure_lag(song(late_ms=late), SR, ref)
    check(abs(lag - late) <= 12 and corr > 0.9, "Versatz %+.0f ms gemessen als %+.0f (%.2f)" % (late, lag, corr))
lag, corr = sc.measure_lag(song(seed=9), SR, ref)
check(lag == 0.0 and corr < sc.MIN_CORR, "andere Datei: kein Ausgleich, schlechte Uebereinstimmung gemeldet")
check(sc.measure_lag(song(), SR, {"rate": 20, "max": [1]}) == (0.0, None), "unbekanntes Raster: kein Ausgleich")
s = sc.shift(np.arange(10.0), 1000, 2)
check(s[0] == 2 and s[-1] == 0 and len(s) == 10, "verschieben nach vorn")
s = sc.shift(np.arange(10.0), -1000, 2)
check(s[0] == 0 and s[2] == 0 and s[3] == 1 and len(s) == 10, "verschieben nach hinten")
late = song(late_ms=50.0)
e = {"vocals": stereo(late), "bass": stereo(np.zeros_like(late)), "drums": stereo(np.zeros_like(late)), "other": stereo(np.zeros_like(late))}
d2 = sc.analyse(e, SR, ref)
frueh = sc.curve(song(), SR)
gemessen = sc.unpack(d2["curves"]["stimme"])
m = min(len(frueh), len(gemessen))
check(d2["offset_ms"] > 35 and float(np.mean(np.abs(frueh[:m].astype(float) - gemessen[:m]))) < 25, "Kurve liegt nach dem Ausgleich auf der Show-Zeit")

# ---- temporaerer Ordner verschwindet ----
seen = {}


def fake(audio, tmp):
    seen.update(audio=os.path.isfile(audio), tmp=tmp)
    return stems, SR


data = ss.compute(lambda p: open(p, "wb").write(b"x"), None, fake)
check(seen["audio"] and not os.path.exists(seen["tmp"]), "Musik und Spuren sind nach der Rechnung weg")


def boom(audio, tmp):
    seen.update(tmp=tmp)
    raise RuntimeError("kaputt")


try:
    ss.compute(lambda p: open(p, "wb").write(b"x"), None, boom)
    check(False, "Fehler kommt durch")
except RuntimeError:
    check(not os.path.exists(seen["tmp"]), "auch nach einem Fehler weg")
check(data["model"] == "htdemucs" and data["created"], "Modell und Zeit stehen in den Daten")

# ---- Speichern am Pi ----
_, sh = build()
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_st_"))
st = mgr.store
st.create("Lied")
st.create("Leer")
mp3 = st.path("Lied", "audio.mp3")
with open(mp3, "wb") as f:
    f.write(b"ID3\x04\0\0\0\0\0\0" + b"\xff\xfb" * 5000)
state = st.stems_state("Lied")
check(state["audio"] and not state["current"], "Stand: MP3 da, noch keine Kurven")
check(not st.stems_state("Leer")["audio"] and st.load_stems("Lied") is None, "ohne MP3 und ohne Kurven")
good = dict(copy.deepcopy(data), fp=state["fp"])


def refused(name, changed, text):
    before = sorted(os.listdir(st.dir(name)))
    try:
        mgr.op({"op": "stems", "name": name, "data": changed})
        check(False, text)
    except ValueError:
        check(sorted(os.listdir(st.dir(name))) == before, text)


refused("Lied", dict(good, fp="0:abc"), "andere MP3 abgelehnt")
refused("Leer", good, "Show ohne MP3 abgelehnt")
refused("Lied", dict(good, rate=50), "anderes Raster abgelehnt")
refused("Lied", dict(good, curves={k: v for k, v in good["curves"].items() if k != "kick"}), "fehlende Kurve abgelehnt")
refused("Lied", dict(good, curves=dict(good["curves"], fremd="AAAA")), "fremde Kurve abgelehnt")
refused("Lied", dict(good, curves=dict(good["curves"], kick="kein base64!")), "unlesbare Kurve abgelehnt")
refused("Lied", dict(good, curves=dict(good["curves"], kick="AAAA")), "ungleiche Laenge abgelehnt")
refused("Lied", dict(good, duration=100.0), "Laenge passt nicht zur Dauer")
refused("Lied", "Text", "kein Objekt abgelehnt")
show_vorher = open(st.path("Lied", "show.json"), "rb").read()
check(mgr.op({"op": "stems", "name": "Lied", "data": dict(good, boese="x")}) == {}, "richtige Daten gespeichert")
state = st.stems_state("Lied")
loaded = st.load_stems("Lied")
check(state["current"] and state["created"] == good["created"] and loaded["curves"] == good["curves"], "Kurven kommen zurueck")
check("boese" not in loaded, "unbekannte Felder fallen weg")
check(open(st.path("Lied", "show.json"), "rb").read() == show_vorher, "show.json bleibt unberuehrt")
check(glob.glob(st.path("Lied", "*.wav")) == [] and sorted(f for f in os.listdir(st.dir("Lied")) if f.endswith(".mp3")) == ["audio.mp3"], "nur die eigene MP3 liegt in der Show")
datei = st._stems_path(good["fp"])
check(os.path.isfile(datei) and not os.path.exists(st.path("Lied", "stems.json")), "eine Datei je MP3, nicht im Show-Ordner")
check([x["name"] for x in st.list()] == ["Leer", "Lied"], "der Ordner der Kurven ist keine Show")
st.copy("Lied", "Kopie")
st.create("Andere")
with open(st.path("Andere", "audio.mp3"), "wb") as f, open(mp3, "rb") as g:
    f.write(g.read())
check(st.stems_state("Kopie")["current"] and st.stems_state("Andere")["current"], "Kopie und andere Show mit derselben MP3 nutzen sie mit")
check(st.load_stems("Andere")["curves"] == good["curves"] and len(os.listdir(os.path.dirname(datei))) == 1, "es bleibt eine einzige Datei")
check(mgr.op({"op": "stems_summary"}) == {"mp3": 1, "done": 1}, "Statistik: drei Shows mit derselben MP3 zaehlen einmal")
st.delete("Lied")
check(st.stems_state("Kopie")["current"], "Show geloescht: die anderen behalten die Kurven")
with open(st.path("Kopie", "audio.mp3"), "wb") as f:
    f.write(b"ID3\x04\0\0\0\0\0\0" + b"\xff\xfa" * 6000)
state = st.stems_state("Kopie")
check(not state["current"] and st.load_stems("Kopie") is None and st.stems_state("Andere")["current"], "neue MP3: keine Kurven, die andere Show behaelt ihre")

check(mgr.op({"op": "stems_summary"}) == {"mp3": 2, "done": 1}, "Statistik: zweite MP3 noch ohne Kurven")
with open(st.path("Leer", "show.json"), "w") as x:
    x.write("kaputt")
check(mgr.op({"op": "stems_summary"})["mp3"] == 2, "Statistik: kaputte Show stoert nicht")
page = __import__("webpanel").make_page()
stat = page[page.index("function drawStemStat"):page.index("function loadLyBulk")] if page.index("function drawStemStat") < page.index("function loadLyBulk") else page[page.index("function drawStemStat"):page.index("function drawStemStat") + 900]
check('id="stemstat"' in page and "loadStemStat()" in page and "s.done" in stat, "Statistik: Anzeige auf der Seite")
check("\\" not in stat, "keine Backslashes im Skript")

# ---- je MP3 nur einmal rechnen ----
A, B = {"audio": True, "fp": "1:a"}, {"audio": True, "fp": "2:b"}
check(ss.pick({"x": A, "y": dict(A), "z": B}) == ["x", "z"], "zwei Shows mit derselben MP3: eine Rechnung")
check(ss.pick({"x": dict(A, current=True), "y": dict(A, current=True), "z": B}) == ["z"], "aktuelle MP3 faellt weg")
check(ss.pick({"x": dict(A, current=True), "y": dict(A, current=True)}, again=True) == ["x"], "--neu: auch dann nur einmal")
check(ss.pick({"x": dict(A, current=True)}, named=True) == ["x"], "ausdruecklich genannte Show wird gerechnet")
check(ss.pick({"x": {"audio": False, "fp": ""}}) == [], "ohne MP3 nichts zu tun")

# ---- Ablauf am Mac gegen einen falschen Pi ----


class Fake:
    def __init__(self):
        self.sent = None

    def get(self, path, name=None):
        return {"/api/sm/stems_state": {"audio": True, "fp": "12:ab"}, "/api/sm/peaks": {}}[path]

    def download(self, name, dest):
        open(dest, "wb").write(b"x")

    def op(self, op, **data):
        self.sent = dict(data, op=op)
        return {}


f = Fake()
out = []
check(ss.process(f, "Lied", fake, out.append) and f.sent["op"] == "stems" and f.sent["data"]["fp"] == "12:ab", "der Mac schickt Kurven mit dem Fingerabdruck des Pi")
check("curves" in f.sent["data"] and any("nicht geprueft" in x for x in out), "ohne Wellenform gibt es einen Hinweis")
check(sum(len(v) for v in f.sent["data"]["curves"].values()) < 12 * 100 * 5 * 2, "nur Kurven, keine Musik im Paket")

# ---- Waechter: neue Shows von selbst ----


class FakePi:
    def __init__(self):
        self.shows = {"Neu": {"audio": True, "fp": "1:a", "current": False}, "Alt": {"audio": True, "fp": "2:b", "current": True},
                      "Kopie": {"audio": True, "fp": "1:a", "current": False}, "Leer": {"audio": False, "fp": ""}}
        self.sent, self.fail = [], set()

    def get(self, path, name=None):
        if path == "/api/sm/shows":
            return {"shows": [{"name": n} for n in self.shows]}
        if path == "/api/sm/stems_state":
            return self.shows[name]
        return {}

    def download(self, name, dest):
        if name in self.fail:
            raise RuntimeError("kaputt")
        open(dest, "wb").write(b"x")

    def op(self, op, **data):
        if op != "stems":                        # aelterer Pi ohne Anmeldung (stems_claim): der Helfer rechnet trotzdem
            raise ValueError("Unbekannter Befehl")
        self.sent.append(data["name"])
        for s in self.shows.values():
            if s.get("fp") == data["data"]["fp"]:
                s["current"] = True
        return {}


p = FakePi()
out = []
ss.watch(p, separator=fake, log=out.append, once=True)
check(p.sent == ["Neu"], "Waechter rechnet nur die neue Show, je MP3 einmal, die aktuelle nicht")
ss.watch(p, separator=fake, log=out.append, once=True)
check(p.sent == ["Neu"], "beim naechsten Durchgang nichts mehr zu tun")
p.shows["Spaeter"] = {"audio": True, "fp": "3:c", "current": False}
p.fail.add("Spaeter")
clock = [1000.0]
ss.watch(p, separator=fake, log=out.append, once=True, now=lambda: clock[0])
ss.watch(p, separator=fake, log=out.append, once=True, now=lambda: clock[0])
check(p.sent == ["Neu"] and sum("Fehler bei Spaeter" in x for x in out) == 1, "Fehler: erst nach der Wartezeit wieder versuchen")
clock[0] += ss.RETRY_S + 1
p.fail.clear()
ss.watch(p, separator=fake, log=out.append, once=True, now=lambda: clock[0])
check(p.sent == ["Neu", "Spaeter"], "nach der Wartezeit klappt es")


class Down:
    def get(self, path, name=None):
        raise OSError("aus")


out = []
ss.watch(Down(), log=out.append, once=True)
check(any("antwortet nicht" in x for x in out), "ohne Pi: Hinweis, kein Absturz")
import threading  # noqa: E402

ev = threading.Event()
ev.set()
ss.watch(FakePi(), separator=fake, log=lambda t: None, stop=ev)
check(True, "stop beendet den Waechter")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check('"$BASE/stems/stems_show.py" --watch --reserve --pi "$PI"' in inst and "STEMS_AUTO=" in inst and "stem_curves.py" in inst,
      "App startet den Waechter und kopiert das Kurven-Programm mit")

# ---- aufs Licht wirkt das nicht ----
src = open(os.path.join(ROOT, "pi", "showman", "engine.py"), encoding="utf-8").read() + open(os.path.join(ROOT, "pi", "show.py"), encoding="utf-8").read()
check("stems" not in src, "Engine und Show lesen die Kurven nicht")
finish("test_stems")
