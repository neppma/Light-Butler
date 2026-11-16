"""Light-Butler Helfer ohne Mixxx: Liedliste (Mixxx-Datenbank-Kopie plus Musikordner), Vorhoeren, Schaetzung und Analyse
ueber denselben Teil wie die Mixxx-Bruecke (mixxx_bridge.make_forwarder, ohne Decks). Laeuft die Bruecke
(~/.light-butler-bruecke.pid), gibt der Helfer ab und nimmt den Teil wieder auf, wenn sie endet (Wunsch von Markus, 07.11.2026).
Der Pi wertet Listen-Nachrichten nicht als "Mixxx verbunden" (sonst ginge die Show in den Ruhemodus mixxx_pause_idle)."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

TMP = tempfile.mkdtemp(prefix="s2l_helfer_lib_")
os.environ["HOME"] = TMP                       # alle ~/Light-Butler-Daten-Ordner (Ordner-Liste, Energie, Tonart) im Testordner
os.environ["S2L_DATA"] = os.path.join(TMP, "Light-Butler")   # gemeinsame Ablage von Mixxx-App und Helfer, auch im Testordner

from _common import ROOT, check, finish        # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "mac", "helper"))
import apc_relay                               # noqa: E402
import energy_level                            # noqa: E402
import helper                                  # noqa: E402
import id3_tags as it                          # noqa: E402
import key_estimate                            # noqa: E402
import mixxx_bridge as mb                      # noqa: E402
import mixxx_link                              # noqa: E402
from music_serve import MusicServer            # noqa: E402

check(apc_relay.BRIDGE_PID.startswith(TMP), "Test arbeitet nicht im echten Home-Ordner")

# ---- Erkennung der Mixxx-Bruecke ----------------------------------------------------------------------------------
pidf = os.path.join(TMP, "bruecke.pid")
check(not apc_relay.bridge_running(pidf), "keine Datei: keine Bruecke")
fake = os.path.join(TMP, "mixxx_bridge.py")
open(fake, "w").write("import time\ntime.sleep(20)\n")
other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
open(pidf, "w").write(str(other.pid))
check(not apc_relay.bridge_running(pidf), "fremder Prozess mit derselben Nummer: keine Bruecke")
b = subprocess.Popen([sys.executable, fake])
open(pidf, "w").write(str(b.pid))
check(apc_relay.bridge_running(pidf), "laufende mixxx_bridge.py erkannt")
check(not apc_relay.helper_running(pidf), "die Bruecke gilt nicht als Helfer")
other.kill()
b.kill()
b.wait()
check(not apc_relay.bridge_running(pidf), "Bruecke beendet: nicht mehr erkannt")
apc_relay.write_pid(pidf)
check(open(pidf).read() == str(os.getpid()), "write_pid schreibt die eigene Nummer")
apc_relay.remove_pid(pidf)
check(not os.path.exists(pidf), "remove_pid loescht die eigene Datei")
open(pidf, "w").write("1")
apc_relay.remove_pid(pidf)
check(os.path.exists(pidf), "fremde Prozessdatei bleibt stehen")

src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("def run(args):\n    claim_bridge(args)" in src, "Bruecke traegt sich beim Start ein (auch mit --stdin, laeuft ueber run)")
mb.claim_bridge(type("A", (), {"send": None})())
check(not os.path.exists(apc_relay.BRIDGE_PID), "ohne --send: keine Prozessdatei (Monitor allein)")
mb.claim_bridge(type("A", (), {"send": "127.0.0.1"})())
check(open(apc_relay.BRIDGE_PID).read() == str(os.getpid()), "mit --send: Prozessdatei der Bruecke")
apc_relay.remove_pid(apc_relay.BRIDGE_PID)

# ---- Vorhoeren: Port frei werden lassen ------------------------------------------------------------------------------
busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
busy.bind(("0.0.0.0", 0))
busy.listen(1)
port = busy.getsockname()[1]
ms = MusicServer([], port=port, log=lambda t: None)
check(not ms.start(), "Port belegt, ein Versuch: kein Vorhoeren")
threading.Timer(0.4, busy.close).start()
ms = MusicServer([], port=port, log=lambda t: None)
check(ms.start(tries=6, wait_s=0.2), "Port wird frei (Helfer gibt ab): Bruecke startet das Vorhoeren beim naechsten Versuch")
ms.stop()


# ---- Liedliste im Helfer --------------------------------------------------------------------------------------------
HDR = b"\xff\xfb\x90\x00"                      # MPEG1 Layer III, 128 kbit/s, 44,1 kHz: 417 Byte je Bild
root = os.path.join(TMP, "Musik")
os.makedirs(os.path.join(root, "Neu"))
song = os.path.join(root, "Neu", "Erika - Ohne Mixxx.mp3")
with open(song, "wb") as f:
    f.write((HDR + bytes(413)) * 400)
it.write(song, 3, 0, it.frame(b"TIT2", it.text_body("Ohne Mixxx"), 3) + it.frame(b"TPE1", it.text_body("Erika"), 3))

rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", 0))
rx.settimeout(0.05)
state, logs = {"br": False}, []
part = helper.LibraryPart("127.0.0.1", db=os.path.join(TMP, "fehlt.sqlite"), analysis_dir=os.path.join(TMP, "analysis"),
                          music_root=root, background=False, pi_port=rx.getsockname()[1], music_port=0, pi_web=1,
                          log=logs.append, bridge=lambda: state["br"])
part.update(now=0.0)
fw = part.fw
check(part.active() and fw is not None and not fw.decks, "Helfer startet den Bibliotheks-Teil der Bruecke, ohne Decks")
check(fw.music is not None and fw.music.port > 0, "Vorhoeren laeuft")
check(fw.folder is not None and fw.folder.base.startswith(TMP), "Ordner-Liste (folder_lib) laeuft mit")
check(fw.est is not None and fw.kest is not None, "Energie- und Tonart-Schaetzung angelegt")
check(fw.dir == os.path.join(TMP, "analysis") and fw.analyze, "Analysen im Ordner der Mixxx-App, Analyse an")
fw.est = fw.kest = None                        # im Test nichts messen (eigene Prozesse)
fw.music.pi_libh = ""                          # im Test gibt es keinen Pi, der seine Fassung meldet: "hat noch nichts"
mport = fw.music.port

items, kinds, mp_seen, t_end = {}, set(), None, time.time() + 30.0   # feste Stuecke: bis zum richtigen kann es dauern
while time.time() < t_end and "Erika - Ohne Mixxx" not in items:
    part.update(now=0.5)
    try:
        data = rx.recvfrom(65536)[0]
    except socket.timeout:
        continue
    m = json.loads(data.decode("utf-8"))
    kinds.add(m.get("type"))
    if m.get("type") == "lib":
        mp_seen = m.get("mp")
        for x in m["t"]:
            d = mixxx_link.lib_item(x)
            if d:
                items[d["title"]] = d
d = items.get("Erika - Ohne Mixxx")
check(d is not None and d["src"] == 1 and d["artist"] == "Erika" and abs(d["dur"] - 400 * 1152 / 44100.0) < 0.2,
      f"MP3 aus dem Musikordner kommt als Ordner-Lied an den Pi ({sorted(items)})")
check(mp_seen == mport, "lib-Nachricht nennt den Port des Vorhoerens")
check(song in fw.music.loc.paths, "Vorhoeren darf die Ordner-Datei liefern")

# neue Kopie der Mixxx-Datenbank (Mixxx-App gestartet): neu laden
part.db_mtime = 1.0
calls_re = []
_orig_start = part.start
part._db_mtime = lambda: 2.0
part.start = lambda: calls_re.append(1) or _orig_start()
part.db_checked = 0.0
part.update(now=200.0)
check(calls_re and part.active() and any("neu laden" in x for x in logs), "neue Datenbank-Kopie: Liedliste neu geladen")
part.fw.est = part.fw.kest = None
part.start = _orig_start

# Mixxx-Bruecke startet (08.11.2026): der Helfer behaelt alles, die Bruecke gibt ihm ab
state["br"] = True
part.update(now=3.0)
check(part.active() and part.fw.music is not None, "Bruecke laeuft: der Helfer behaelt Liedliste und Vorhoeren")
part.fw.est = part.fw.kest = None
part.stop()
check(not part.active(), "Helfer beendet: Teil gestoppt")

# Start schlaegt fehl: nicht alle 2 s erneut
calls = []
p3 = helper.LibraryPart("127.0.0.1", db="", music_root=root, background=False, music_port=0, log=logs.append, bridge=lambda: False)
p3.start = lambda: calls.append(1) or (_ for _ in ()).throw(RuntimeError("kaputt"))
p3.update(now=0.0)
p3.update(now=10.0)
p3.update(now=61.0)
check(len(calls) == 2 and not p3.active(), f"defekte Datenbank: neuer Versuch erst nach einer Minute ({len(calls)})")

# ---- Forwarder.stop beendet Schaetzung, Kurven-Sicherung, Hintergrund-Analyse ----------------------------------------
class Stoppable:
    def __init__(self):
        self.stopped = False

    def stop(self, *a):
        self.stopped = True


class Proc:
    def __init__(self):
        self.term = False

    def is_alive(self):
        return not self.term

    def terminate(self):
        self.term = True

    def join(self, t=None):
        pass


f2 = mb.Forwarder([], None, None, analysis_dir=TMP, analyze=False)
f2.est, f2.kest, f2.stems_backup, f2.music = Stoppable(), Stoppable(), Stoppable(), Stoppable()
music = f2.music
f2.bg = {"proc": Proc()}
f2.stop()
check(f2.est.stopped and f2.kest.stopped and f2.stems_backup.stopped and music.stopped and f2.music is None,
      "stop(): Schaetzungen, Kurven-Sicherung und Vorhoeren beendet")
check(f2.bg["proc"].term, "stop(): Hintergrund-Analyse beendet")

# ---- Estimator.stop: Schreiben in die MP3s endet nach der laufenden Datei --------------------------------------------
os.makedirs(os.path.join(TMP, "e"))
est = energy_level.Estimator(base=os.path.join(TMP, "e"), model_path=os.path.join(TMP, "kein_modell.json"))
written = []
orig = energy_level.write_energy_tag
energy_level.write_energy_tag = lambda f, lv: (written.append(f), time.sleep(0.02), "ok")[2]
songs = []
for i in range(60):
    p = os.path.join(TMP, f"s{i}.mp3")
    open(p, "w").close()
    est.est[p] = 5
    songs.append((p, p))
est.write_tick(songs, gap_s=0.01)
time.sleep(0.15)
est.stop()
n = len(written)
time.sleep(0.2)
energy_level.write_energy_tag = orig
check(0 < n < 60 and len(written) == n and not est.writer.is_alive(), f"Energie: Schreiben nach stop() beendet ({n} von 60)")
kest = key_estimate.KeyEstimator(base=os.path.join(TMP, "k"))
kest.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
kest.stop()
kest.proc.wait(5)
check(not kest.running(), "Tonart: Messung nach stop() beendet")

# ---- Pi: Liedliste allein heisst nicht "Mixxx verbunden" ---------------------------------------------------------------
link = mixxx_link.MixxxLink(0)
link.feed({"type": "lib", "i": 0, "n": 1, "t": [["A - B", 100.0]]}, now=100.0)
link.feed({"type": "genres", "g": [["House", 3]]}, now=100.0)
link.feed({"type": "stats", "n": 3}, now=100.0)
check(link.last_rx == 0.0, "lib, genres, stats: nicht verbunden")
check(link.library_complete() and link.genres == [["House", 3]], "Liste und Genres trotzdem uebernommen")
link.feed({"type": "lib", "i": 0, "n": 1, "t": [], "mp": 9025}, now=101.0, addr="192.168.1.50")
check(link.mac_ip == "192.168.1.50" and link.music_port == 9025, "Adresse des Vorhoerens auch vom Helfer")
link.feed({"d": 1, "pl": 0}, now=102.0)
check(link.last_rx == 102.0, "Deck-Zustand aus Mixxx: verbunden")

# ---- Installation -----------------------------------------------------------------------------------------------------
inst = open(os.path.join(ROOT, "mac", "helper", "install_helper.sh"), encoding="utf-8").read()
for fn in ("mixxx_bridge.py", "analyze_track.py", "music_serve.py", "stems_backup.py", "energy_level.py", "energie_modell.json",
           "key_estimate.py", "id3_tags.py", "folder_lib.py"):
    check(f'"$SRC/{fn}"' in inst, f"install_helper.sh kopiert {fn}")
check("scipy:scipy" in inst and "soundfile:soundfile" in inst, "install_helper.sh: Pakete fuer die Analyse")
check(helper.config_value("MUSIC_ROOT", os.path.join(TMP, "fehlt.sh")) == "", "ohne config.sh: kein Reserve-Ordner")
cfg = os.path.join(TMP, "config.sh")
open(cfg, "w").write('PI="x"\nMUSIC_ROOT="/Volumes/USB STICK/musik"\nBACKGROUND_ANALYSIS="0"\n')
check(helper.config_value("MUSIC_ROOT", cfg) == "/Volumes/USB STICK/musik" and helper.config_value("BACKGROUND_ANALYSIS", cfg) == "0",
      "Musikordner und Hintergrund-Analyse aus der config.sh der Mixxx-App")
# ---- Pegelkurven-Waechter gehoert zum Helfer (08.11.2026) ---------------------------------------------------------------
class Proc:
    def __init__(self):
        self.alive, self.killed = True, False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.alive = False

    def wait(self, t=None):
        return 0

    def kill(self):
        self.killed = True


other = {"run": True}
started = []
sp = helper.StemsPart("lightbutler.local", log=logs.append, cmd=lambda: ["py", "stems_show.py", "--watch", "--reserve"],
                      running=lambda: other["run"], popen=lambda c: started.append(c) or Proc())
sp.update(now=0.0)
check(not started, "Mixxx-App hat schon einen Waechter: der Helfer startet keinen zweiten")
other["run"] = False
sp.update(now=30.0)
check(not started, "erst nach einer Minute wieder schauen")
sp.update(now=61.0)
check(len(started) == 1 and "--reserve" in started[0], "anderer beendet (App zu): der Helfer uebernimmt")
other["run"] = True                       # sein eigener zaehlt jetzt mit
sp.update(now=130.0)
check(len(started) == 1, "laeuft der eigene: nichts Neues")
pr = sp.proc
sp.stop()
check(not pr.alive and sp.proc is None, "Helfer beendet: Waechter beendet")
check(helper.StemsPart("x", cmd=lambda: None, running=lambda: False, popen=lambda c: started.append(c) or Proc()).update(now=0.0) is None
      and len(started) == 1, "ohne ~/s2l-stems: nichts starten")
check(os.environ.get("S2L_NO_STEMS") == "1" and helper.StemsPart("x")._cmd() is None, "in den Tests nie der echte Waechter")
inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check('! pgrep -f "stems_show.py --watch"' in inst, "Mixxx-App startet nur, wenn noch keiner laeuft")
ih = open(os.path.join(ROOT, "mac", "helper", "install_helper.sh"), encoding="utf-8").read()
check('"$BASE/stems/"' in ih and "stems_show.py" in ih, "Helfer bekommt das Kurven-Programm mit")
finish("test_helfer_liedliste")
