"""Titelerkennung mit SongRec: Ton aus dem Ringpuffer, Anfragen nur bei Musik und ohne Mixxx, Fehler ohne Absturz.
Das Genre gibt den Stil vor, sonst bleibt das Licht gleich. SongRec ist hier nachgebaut, es geht nichts ins Internet. Ausgeschaltet wird nichts gesammelt und nichts aufgerufen."""
import json
import os
import subprocess
import tempfile
import threading
import time
import types
import wave

import numpy as np

from _common import Clock, build, check, finish
from audio import Analyzer
from songrec_id import ERROR_PAUSE_S, MISS_CLEAR, NOMATCH_WAV, QUIET_CLEAR_S, SECONDS, TitleFinder, error_line, parse_result
from webpanel import make_page

RATE = 8000
SONG = {"track": {"title": "Schifoan", "subtitle": "Wolfgang Ambros", "genres": {"primary": "Austropop"}}}


class Fake:
    """Nachgebautes SongRec: merkt sich die Aufrufe und liest die Datei wie das echte Programm."""

    def __init__(self):
        self.calls, self.seen = [], []
        self.answer = lambda: types.SimpleNamespace(returncode=0, stdout=json.dumps(SONG), stderr="")

    def __call__(self, args, **kw):
        self.calls.append(args)
        with wave.open(args[-1], "rb") as w:
            self.seen.append((w.getframerate(), w.getnframes(), w.getnchannels()))
        return self.answer()


def finder(fake, rate=RATE):
    return TitleFinder(rate, cmd="/snap/bin/songrec", wav_file=os.path.join(tempfile.mkdtemp(), "x", "probe.wav"), runner=fake)


def filled(tf):
    tf.feed(np.full(tf.size, 0.5, np.float32))


def settle(tf, now):
    """Wartet auf den Arbeits-Thread und holt das Ergebnis ab."""
    for _ in range(300):
        if tf.done is not None or not tf.busy:
            break
        time.sleep(0.01)
    return tf.tick(now, True, 40.0, True, False)


print("Antwort von SongRec lesen")
check(parse_result(json.dumps(SONG)) == {"title": "Schifoan", "artist": "Wolfgang Ambros", "genre": "Austropop"}, "Titel, Interpret und Genre")
check(parse_result("Hinweis davor\n" + json.dumps(SONG, indent=2))["title"] == "Schifoan", "mehrzeilig und mit Text davor")
check(parse_result("") is None and parse_result("{kaputt}") is None and parse_result('{"matches":[]}') is None, "leer, kaputt oder ohne Lied = None")
check(parse_result('{"track":{"title":"Nur Titel"}}')["artist"] == "", "ohne Interpret und Genre geht es auch")

print("Ausgeschaltet")
f = Fake()
tf = finder(f)
tf.feed(np.ones(100, np.float32))
check(tf.filled == 0, "kein Ton gesammelt, solange aus")
check(tf.tick(100.0, False, 40.0, True, False) is None and not f.calls and tf.public() is None, "kein Aufruf, keine Anzeige")

print("Ablauf einer Anfrage")
f = Fake()
tf = finder(f)
tf.tick(100.0, True, 40.0, True, False)
filled(tf)
tf.tick(100.0 + SECONDS - 1, True, 40.0, True, False)
check(not tf.busy, "noch keine Anfrage, bevor 12 s Musik liefen")
tf.tick(100.0 + SECONDS, True, 40.0, True, False)
check(tf.public()["st"] in ("search", "ok"), "dann wird gesucht")
new = settle(tf, 113.0)
check(new and new["title"] == "Schifoan", "neu erkanntes Lied wird gemeldet")
check(tf.public()["artist"] == "Wolfgang Ambros" and tf.public()["st"] == "ok", "Anzeige mit Interpret")
check(f.calls[0][:3] == ["nice", "-n", "15"] and f.calls[0][3:6] == ["/snap/bin/songrec", "recognize", "--json"], "niedrige Prioritaet, richtiger Aufruf")
check(f.seen[0] == (RATE // 2, SECONDS * RATE // 2, 1), "WAV: mono, halbe Rate, 12 s")
check(not os.path.exists(tf.wav_file), "Datei danach wieder weg")
tf.tick(150.0, True, 40.0, True, False)
check(len(f.calls) == 1, "vor Ablauf des Abstands keine neue Anfrage")
tf.tick(153.0, True, 40.0, True, False)
new = settle(tf, 153.0)
check(len(f.calls) == 2 and new is None, "danach wieder, dasselbe Lied gilt nicht als neu")

print("Ringpuffer haelt die letzten 12 s in der richtigen Reihenfolge")
tf = finder(Fake())
tf.active = True
for i in range(SECONDS + 3):
    tf.feed(np.full(RATE, (i + 1) / 100.0, np.float32))
snap = tf._snapshot()
check(abs(snap[0] / 32767.0 - 0.04) < 0.001 and abs(snap[-1] / 32767.0 - 0.15) < 0.001, "aeltester vorne, neuester hinten")
tf.feed(np.full(500, 9.0, np.float32))
check(tf._snapshot().max() == 32767, "zu laut wird begrenzt, nicht umgeklappt")

print("Keine Anfragen bei Stille oder wenn Mixxx spielt")
f = Fake()
tf = finder(f)
tf.tick(100.0, True, 40.0, False, False)
filled(tf)
tf.tick(200.0, True, 40.0, False, False)
check(not f.calls, "Stille: keine Anfrage")
tf.tick(300.0, True, 40.0, True, True)
tf.tick(400.0, True, 40.0, True, True)
check(not f.calls and tf.public() is None, "Mixxx spielt: keine Anfrage, keine eigene Zeile")

print("Alter Titel verschwindet")
f = Fake()
tf = finder(f)
tf.tick(100.0, True, 40.0, True, False)
filled(tf)
tf.tick(120.0, True, 40.0, True, False)
settle(tf, 120.0)
tf.tick(130.0, True, 40.0, False, False)
tf.tick(130.0 + QUIET_CLEAR_S - 1, True, 40.0, False, False)
check(tf.public()["title"] == "Schifoan", "kurzer Break: Titel bleibt")
tf.tick(130.0 + QUIET_CLEAR_S, True, 40.0, False, False)
check(tf.public()["title"] == "", "lange Stille: Titel weg")

f = Fake()
tf = finder(f)
tf.tick(100.0, True, 40.0, True, False)
filled(tf)
tf.tick(120.0, True, 40.0, True, False)
settle(tf, 120.0)
f.answer = lambda: types.SimpleNamespace(returncode=0, stdout="", stderr="Error: No match for this song")
t = 200.0
for i in range(MISS_CLEAR):
    check(tf.public()["title"] == "Schifoan", f"vor Fehlversuch {i + 1} noch sichtbar")
    tf.tick(t, True, 40.0, True, False)
    settle(tf, t)
    t += 100.0
check(tf.public()["title"] == "" and tf.public()["st"] == "nomatch", f"nach {MISS_CLEAR} Fehlversuchen weg")

print("Echte Ausgabe von SongRec am Pi (03.11.2026), Meldungen auf stdout oder stderr")
PULSE = ("[2026-11-03T09:37:01Z ERROR songrec::core::audio_controllers::pulseaudio src/core/audio_controllers/pulseaudio.rs:28] Could not initialize PulseAudio backend: PulseCtl(...)\n"
         "[2026-11-03T09:37:01Z WARN pxbackend bridged_logging.rs:265] Could not query proxy: GDBus.Error\n")
NOMATCH = PULSE + "[2026-11-03T09:37:02Z ERROR songrec::cli_main src/cli_main.rs:180] Error: No match for this song\n"
check(error_line(PULSE) == "", "PulseAudio-Meldung gilt nicht als Fehler")
check(error_line(NOMATCH) == "Error: No match for this song", "echte Fehlerzeile ohne Vorspann")
SNAP = 'internal error, please report: running "songrec" failed: cannot track application process'
check(error_line(SNAP + "\n") == SNAP[:160], "Meldung von snap selbst bleibt sichtbar (Dienst am Pi, 03.11.2026)")
check(parse_result(PULSE + json.dumps(SONG) + "\n")["title"] == "Schifoan", "Lied zwischen Meldungen auf stdout")
for name, ans in (("stderr", types.SimpleNamespace(returncode=0, stdout="", stderr=NOMATCH)),
                  ("stdout", types.SimpleNamespace(returncode=0, stdout=NOMATCH, stderr=""))):
    f = Fake()
    f.answer = lambda a=ans: a
    tf = finder(f)
    tf.tick(100.0, True, 40.0, True, False)
    filled(tf)
    tf.tick(120.0, True, 40.0, True, False)
    settle(tf, 120.0)
    check(tf.public()["st"] == "nomatch" and tf.next_t == 160.0, f"Kein Treffer auf {name}: nicht erkannt, normaler Abstand")
    keep = os.path.join(os.path.dirname(tf.wav_file), NOMATCH_WAV)
    check(os.path.exists(keep) and not os.path.exists(tf.wav_file), "nicht erkannte Probe bleibt zum Nachhoeren liegen")

print("Leiser Eingang wird fuer die Probe angehoben")
for name, level, want in (("-40 dB", 0.01, 0.9), ("voll", 1.0, 0.9), ("Rauschen -80 dB", 0.0001, 0.01)):
    tf = finder(Fake())
    tf.active = True
    tf.feed(np.sin(np.arange(tf.size) * 0.2).astype(np.float32) * level)
    tf._write_wav(tf._snapshot())
    with wave.open(tf.wav_file, "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    check(abs(np.abs(x).max() / 32767.0 - want) < 0.03, f"{name}: Spitze {np.abs(x).max() / 32767.0:.3f}")
tf = finder(Fake())
tf._write_wav(np.zeros(tf.size, np.int16))
check(os.path.exists(tf.wav_file), "Stille: kein Absturz")

print("Fehler enden nie im Absturz, danach seltener fragen")
ANTWORT = [("offline", types.SimpleNamespace(returncode=0, stdout="", stderr="Error: Network unreachable")),
           ("missing", types.SimpleNamespace(returncode=127, stdout="", stderr="nice: songrec: No such file or directory")),
           ("error", types.SimpleNamespace(returncode=1, stdout="", stderr="Error: HTTP 429")),
           ("error", types.SimpleNamespace(returncode=0, stdout="", stderr="")),
           ("error", types.SimpleNamespace(returncode=0, stdout="", stderr=PULSE)),
           ("error", types.SimpleNamespace(returncode=1, stdout="", stderr=SNAP))]
for want, ans in ANTWORT:
    f = Fake()
    f.answer = lambda a=ans: a
    tf = finder(f)
    tf.tick(100.0, True, 40.0, True, False)
    filled(tf)
    tf.tick(120.0, True, 40.0, True, False)
    settle(tf, 120.0)
    check(tf.public()["st"] == want, f"{ans.stderr[:32]} = {want}")
    check(tf.next_t == 120.0 + ERROR_PAUSE_S, "Pause nach dem Fehler")


def boom(exc):
    def run(args, **kw):
        raise exc
    return run


for want, exc in (("error", subprocess.TimeoutExpired("songrec", 1)), ("missing", FileNotFoundError("nice")), ("error", RuntimeError("kaputt"))):
    tf = finder(boom(exc))
    tf.tick(100.0, True, 40.0, True, False)
    filled(tf)
    tf.tick(120.0, True, 40.0, True, False)
    settle(tf, 120.0)
    check(tf.public()["st"] == want and not tf.busy, f"{type(exc).__name__} = {want}")
    check(not os.path.exists(tf.wav_file), "Datei auch dann weg")

print("In der Show")
rig, sh = build()
check(sh.cfg["songrec_on"] == 0.0, "Standard: aus")
check(sh.titles is None and sh.snapshot()["sr"] is None, "Simulator: ohne Erkennung, keine Anzeige")
f = Fake()
sh.titles = finder(f, 44100)
clk = Clock(sh)
clk.run(1.0)
filled(sh.titles)
check(not sh.titles.active and not f.calls, "aus: nicht aktiv, kein Aufruf")
sh.cfg.set("songrec_on", 1.0)
clk.run(1.0)
filled(sh.titles)
sh.titles.music_since = clk.t - SECONDS
sh.titles.next_t = 0.0
clk.run(0.1)
for _ in range(200):
    if sh.titles.done is not None or f.calls and not sh.titles.busy:
        break
    time.sleep(0.01)
clk.run(0.1)
check(f.calls, "an: SongRec wird aufgerufen")
check(sh.snapshot()["sr"]["title"] == "Schifoan", "Titel im Status fuers Panel")
check(any(p["title"] == "Wolfgang Ambros - Schifoan" and p["genre"] == "Austropop" for p in sh.played), "Lied in der Liste auf /stats")
n = len(sh.played)
sh.titles.next_t = 0.0
clk.run(0.1)
for _ in range(200):
    if not sh.titles.busy:
        break
    time.sleep(0.01)
clk.run(0.1)
check(len(sh.played) == n, "dasselbe Lied nur einmal in der Liste")
sh.cfg.set("songrec_on", 0.0)
clk.run(0.1)
check(sh.snapshot()["sr"] is None, "wieder aus: Anzeige weg")

print("Erkanntes Genre gibt den Stil vor")
rig, sh = build()
check(sh.cfg["songrec_style"] == 1.0, "Standard: an (wirkt nur mit Titelerkennung)")
tf = finder(Fake(), 44100)
sh.titles = tf
tf.song = {"title": "T", "artist": "A", "genre": "Rock"}
check(sh._style_key() is None, "Titelerkennung aus: kein Stil, auch mit altem Lied")
tf.active = True
check(sh._style_key() == "rock", "Rock: Stil Rock")
check(sh._style("mv", 1.0) == 1.15, "Stil wirkt auf die Bewegung")
hues = {sh._pick_hue() for _ in range(12)}
check(hues <= {0.0, 0.07, 0.10}, "Farben aus dem Stil")
tf.song = dict(tf.song, genre="Holiday")
check(sh._style_key() == "weihnachten", "Holiday = Weihnachten")
tf.song = dict(tf.song, genre="R&B/Soul")
check(sh._style_key() is None, "Genre ohne Zuordnung: kein Stil")
sh.gstyles.set("R&B/Soul", "party")
check(sh._style_key() == "party", "eigene Zuordnung gilt")
sh.gstyles.set("R&B/Soul", "")
tf.song = dict(tf.song, genre="Rock")
sh.cfg.set("songrec_style", 0.0)
check(sh._style_key() is None, "Schalter aus: kein Stil")
sh.cfg.set("songrec_style", 1.0)
sh.style_man = "ruhig"
check(sh._style_key() == "ruhig", "Stil von Hand geht vor")
sh.style_man = None
sh.mx = {"plan": True, "deck": 1, "genre": "Techno", "playing": True, "title": "X"}
check(sh._style_key() == "club", "Mixxx geht vor")
sh.mx = None
tf.song = None
check(sh._style_key() is None, "kein Lied mehr: wieder ohne Stil")
tf.done = ("ok", {"title": "Neu", "artist": "B", "genre": "Pop"}, "")
sh.cfg.set("songrec_on", 1.0)
sh._titles_tick(5000.0, types.SimpleNamespace(silent=False))
check(sh.played[-1]["style"] == "party" and sh.live_genres == {"Pop": 1}, "Liste auf /stats mit Stil, Genre fuer die Tabelle gemerkt")

print("Show nimmt Mixxx als Quelle, wenn ein Deck hoerbar mit Titel spielt")
sh.mx = {"plan": True, "deck": 1, "playing": True, "title": "Aus Mixxx"}
check(sh._mixxx_has_title(), "Mixxx spielt mit Titel")
sh.mx = {"plan": True, "deck": None, "playing": False, "title": ""}
check(not sh._mixxx_has_title(), "kein Deck hoerbar")
sh.mx = None
check(not sh._mixxx_has_title(), "ohne Mixxx")

print("Audio-Eingang gibt den Ton weiter")
check(Analyzer.tap is None, "Analyzer ohne Abnehmer: tap ist None")
an = Analyzer(rate=44100)
got = []
an.tap = got.append
an.gain_db = 6.0
an._run = True
an._callback(np.full((512, 2), 0.25, np.float32), 512, None, None)
th = threading.Thread(target=an._loop, daemon=True)
th.start()
for _ in range(200):
    if got:
        break
    time.sleep(0.01)
an._run = False
th.join(2.0)
check(len(got) == 1 and got[0].shape == (512,) and abs(got[0][0] - 0.25 * 10 ** (6 / 20)) < 0.001, "Mono-Ton mit Verstaerkung kommt beim Abnehmer an")

print("Panel")
page = make_page()
check("srline" not in page and "tr('sr_label')" in page, "keine eigene Zeile: Live nimmt die Mixxx-Zeile, das Panel springt nicht")
check("tr('sr_label')+'</b><i>'+(S.lvsrc==='lan'?'LAN':S.lvsrc==='bt'?'Bluetooth':'Line-In')+'</i>'" in page, "neben Live steht, woher der Ton kommt (Line-In, LAN vom Mac oder Bluetooth)")
check("s&&(!m||!m.connected||m.deck===null||(!m.plan&&s.title))" in page, "Live nur, wenn aus Mixxx kein Lied kommt")
check("Titelerkennung" in page, "Gruppe unter Einstellungen allgemein")

finish("test_titelerkennung")
