"""Hintergrund-Analyse am Mac (--background-analysis, config.sh BACKGROUND_ANALYSIS=1): Beim Start der App analysiert
ein eigener Prozess mit niedriger Prioritaet alle Lieder ohne Analyse-Datei, eines nach dem anderen. Ein Lied, das in
Mixxx geladen wird, hat Vorrang (Pause, 10 s nach der letzten Analyse beim Laden geht es weiter). Bei getrenntem NAS
wartet sie; unlesbare Dateien kommen in _nicht_lesbar.json und werden beim naechsten Start nicht wieder versucht."""
import json
import os
import sys
import tempfile
import threading
import time

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
try:
    import numpy as np
    from scipy.io import wavfile
    import mixxx_bridge as mb
except ImportError:
    mb = None

if mb is None:
    check(True, "ohne numpy/scipy: Test uebersprungen")
    finish("test_hintergrund_analyse")
    sys.exit(0)

d = tempfile.mkdtemp()
out = os.path.join(d, "analysis")
os.makedirs(out)
sr = 22050
t = np.arange(sr * 40) / sr
kick = np.sin(2 * np.pi * 55 * ((t * 2) % 1) / 2) * np.exp(-((t * 2) % 1) * 18)
song = (0.5 * kick * np.where((t > 15) & (t < 20), 0.1, 1.0)).astype(np.float32)
wav = os.path.join(d, "lied.wav")
wavfile.write(wav, sr, song)

ok = {"id": 1, "artist": "A", "title": "Gut", "duration": 40.0, "bpm": 120.0, "kid": 1, "path": wav}
bad = {"id": 2, "artist": "B", "title": "Kaputt", "duration": 50.0, "bpm": 120.0, "kid": 2, "path": os.path.join(d, "fehlt.mp3")}
dup = dict(ok, id=3)                                          # gleiches Lied ein zweites Mal (z. B. USB und NAS)
old = {"id": 4, "artist": "C", "title": "Schon da", "duration": 60.0, "bpm": 100.0, "kid": 3, "path": wav}
k_ok, k_bad, k_old = (mb.track_key(r["duration"], r["bpm"], r["kid"]) for r in (ok, bad, old))
open(os.path.join(out, k_old + ".json"), "w").write("{}")

check(mb.volume_missing("/Volumes/gibt_es_nicht_xyz/a.mp3") and not mb.volume_missing(wav), "getrenntes Laufwerk erkannt")

# ---- der Ablauf im Hintergrund (hier im selben Prozess, mit Event und Liste statt Prozess-Objekten) ------------------
pause = threading.Event()
pause.set()
prog = [0, 0]
todo = [(k_ok, ok), (k_bad, bad)]
th = threading.Thread(target=mb.background_analysis, args=(todo, out, pause, prog, 0.0), daemon=True)
th.start()
time.sleep(1.0)
check(prog == [0, 0] and not os.path.exists(os.path.join(out, k_ok + ".json")), "pausiert: nichts analysiert (Lied in Mixxx hat Vorrang)")
pause.clear()
th.join(120)
check(not th.is_alive() and prog == [1, 1], f"weiter: 1 analysiert, 1 nicht lesbar ({prog})")
res = json.load(open(os.path.join(out, k_ok + ".json"), encoding="utf-8"))
check(res.get("version") and res.get("duration", 0) > 39, "Analyse-Datei geschrieben")
failed = json.load(open(os.path.join(out, mb.FAILED_FILE), encoding="utf-8"))
check(list(failed) == [k_bad] and "Kaputt" in failed[k_bad], "unlesbare Datei gemerkt")
check(not [f for f in os.listdir(out) if f.endswith(".tmp")], "keine halben Dateien")

# ---- beim naechsten Start: nur, was noch fehlt --------------------------------------------------------------------
os.remove(os.path.join(out, k_ok + ".json"))
fw = mb.Forwarder([ok, bad, dup, old], None, None, analysis_dir=out, analyze=False)
started = []
mb_ctx = __import__("multiprocessing").get_context("spawn")


class FakeProc:
    def __init__(self, target, daemon, args):
        started.append(args[0])

    def start(self):
        pass

    def is_alive(self):
        return True


import multiprocessing    # noqa: E402
real_get = multiprocessing.get_context


class Ctx:
    Event = staticmethod(mb_ctx.Event)
    Array = staticmethod(mb_ctx.Array)
    Process = FakeProc


multiprocessing.get_context = lambda kind=None: Ctx
try:
    n = fw.start_background()
finally:
    multiprocessing.get_context = real_get
check(n == 1 and [k for k, _ in started[0]] == [k_ok], "naechster Start: nur das fehlende Lied, ohne Doppelte, ohne Unlesbare")
info = fw.bg_info()
check(info == {"todo": 1, "done": 0, "fail": 1, "run": True, "pause": False, "gone": 1}, f"Fortschritt fuer die Statistik ({info}; die kaputte Datei gibt es hier gar nicht: alter Eintrag)")
check(fw.stats()["bg"] == info, "steht in der Statistik")

fw.bg["pause"].set()
fw.demand_t = time.time()
fw.tick()
check(fw.bg["pause"].is_set(), "kurz nach einer Analyse beim Laden: noch pausiert")
fw.demand_t = time.time() - 11
fw.tick()
check(not fw.bg["pause"].is_set(), "10 s spaeter: weiter im Hintergrund")

# ---- Pi und Panel -----------------------------------------------------------------------------------------------------
from mixxx_link import clean_stats    # noqa: E402
import webpanel                       # noqa: E402

check(clean_stats({"bg": dict(info, done=-3)})["bg"]["done"] == 0 and clean_stats({})["bg"] is None, "Pi: Fortschritt geprueft")
p = webpanel.make_page()
check("tr('stat_bg_line').replace(/#/g" in p, "Statistik zeigt die Hintergrund-Analyse")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check('BACKGROUND_ANALYSIS="${BG_OLD:-1}"' in inst and '[ "${BACKGROUND_ANALYSIS:-1}" = "1" ] && BG="--background-analysis"' in inst,
      "App: Schalter in config.sh (Standard an, eigene Wahl bleibt)")
finish("test_hintergrund_analyse")
