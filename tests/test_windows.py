"""Windows-Variante: Stellen, die unter Windows anders laufen muessen, am Pi und Mac aber gleich bleiben."""
import os
import sys

from _common import check, finish

import health
import show as sw
import webpanel

# ---- Neustart nach Aenderungen an den Fixtures --------------------------------------------------------------------
argv = ["show.py", "--simulate", "--web", "8080"]
cmd = sw.restart_cmd(argv, exe=r"C:\Program Files\Python\python.exe")
check(cmd[0] == r"C:\Program Files\Python\python.exe" and cmd[1] == os.path.abspath("show.py") and cmd[2:] == argv[1:],
      "Neustart: dasselbe Python, dasselbe Skript, dieselben Optionen")

calls = []
old = sys.argv
sys.argv = argv
try:
    sw.restart_self("linux", execv=lambda p, a: calls.append(("execv", p, a)), popen=lambda *a, **k: calls.append("popen"),
                    exit_=lambda c: calls.append("exit"))
    check(len(calls) == 1 and calls[0][0] == "execv" and calls[0][1] == sys.executable and calls[0][2][0] == sys.executable,
          "Pi und Mac: os.execv wie bisher, kein zweiter Prozess")
    calls.clear()
    sw.restart_self("win32", execv=lambda p, a: calls.append("execv"), popen=lambda c, **k: calls.append(("popen", c, k)),
                    exit_=lambda c: calls.append(("exit", c)), env={})
    check([c[0] for c in calls] == ["popen", "exit"] and calls[0][1][2:] == argv[1:] and calls[1][1] == 0,
          "Windows: neuen Prozess starten, dann diesen beenden (kein execv)")
    calls.clear()
    sw.restart_self("win32", execv=lambda p, a: calls.append("execv"), popen=lambda c, **k: calls.append("popen"),
                    exit_=lambda c: calls.append(("exit", c)), env={"LB_RESTART_EXIT": "1"})
    check(calls == [("exit", sw.RESTART_CODE)], "Windows aus start.ps1: Ende mit Code 3, start.ps1 startet neu (kein zweiter Prozess)")
    calls.clear()
    sw.restart_self("linux", execv=lambda p, a: calls.append("execv"), popen=lambda c, **k: calls.append("popen"),
                    exit_=lambda c: calls.append("exit"), env={"LB_RESTART_EXIT": "1"})
    check(calls == ["execv"], "Pi: LB_RESTART_EXIT wirkt nicht, execv wie bisher")
finally:
    sys.argv = old

# ---- Zustand: Takte pro Sekunde ----------------------------------------------------------------------------------
t = health.clk_tck()
check(isinstance(t, int) and t > 0, "Takte pro Sekunde lesbar (Windows: 100)")
if hasattr(os, "sysconf"):
    check(t == os.sysconf("SC_CLK_TCK"), "Pi/Mac: Wert aus os.sysconf wie bisher")

# ---- Ping ----------------------------------------------------------------------------------------------------------
check(webpanel.ping_cmd("10.0.0.1")[1] == ("-n" if sys.platform == "win32" else "-c"), "Ping passend zum System")

# ---- Pruefen, ob ein Prozess laeuft, darf ihn nie beenden (Windows: os.kill(pid, 0) beendet!) ------------------------
import subprocess  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mac", "mixxx_bridge"))
import apc_relay  # noqa: E402

sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
try:
    pidf = os.path.join(tempfile.mkdtemp(prefix="s2l_win_"), "x.pid")
    with open(pidf, "w") as f:
        f.write(str(sleeper.pid))
    r = apc_relay.bridge_running(pidf)
    check(sleeper.poll() is None, "Abfrage laesst den fremden Prozess am Leben")
    check(r is False, "fremder Prozess gilt nicht als Bruecke")
    check(apc_relay.bridge_running(pidf, cmdline="python mixxx_bridge.py --send x") is True, "laufender Prozess mit passendem Namen erkannt")
finally:
    sleeper.kill()
    sleeper.wait()
with open(pidf, "w") as f:
    f.write(str(sleeper.pid))
check(apc_relay.bridge_running(pidf, cmdline="mixxx_bridge.py") is False, "beendeter Prozess: nicht erkannt")

# ---- MIDI: scheitert ein Anschluss, bleiben die anderen nicht offen (Windows: sonst gesperrt) ----------------------
import types  # noqa: E402

import midi_ctl  # noqa: E402


class Port:
    def __init__(self, name):
        self.name, self.closed = name, False

    def close(self):
        self.closed = True


opened = []


def open_input(n):
    p = Port(n)
    opened.append(p)
    return p


def open_output(n):
    raise OSError("MMSYSERR_ALLOCATED: belegt von einem anderen Programm")


fake = types.SimpleNamespace(get_input_names=lambda: ["APC mini mk2 0", "MIDIIN2 (APC mini mk2) 1", "PC 0"],
                             get_output_names=lambda: ["APC mini mk2 2", "MIDIOUT2 (APC mini mk2) 3"],
                             open_input=open_input, open_output=open_output)
old_mido = sys.modules.get("mido")
sys.modules["mido"] = fake
try:
    mc = midi_ctl.MidiController(types.SimpleNamespace(), map_path=None)
    check(mc._local_names()[0] == ["APC mini mk2 0", "MIDIIN2 (APC mini mk2) 1"], "Windows-Namen des APC erkannt (beide Anschluesse)")
    try:
        mc._open()
        check(False, "belegter Ausgang meldet einen Fehler")
    except OSError:
        check(True, "belegter Ausgang meldet einen Fehler")
    check(len(opened) == 2 and all(p.closed for p in opened) and mc.ins == [] and not mc.connected,
          "schon geoeffnete Eingaenge wieder geschlossen, naechster Versuch moeglich")
finally:
    if old_mido is None:
        sys.modules.pop("mido", None)
    else:
        sys.modules["mido"] = old_mido

# ---- Audio: Windows fuehrt ein Geraet mehrfach (MME, DirectSound, WASAPI, WDM-KS) ----------------------------------
import audio  # noqa: E402


class FakeSd:
    def __init__(self, devs, ok):
        self.devs, self.ok = devs, ok

    def query_devices(self, i=None, kind=None):
        return self.devs if i is None else self.devs[i]

    def check_input_settings(self, device, channels, samplerate, dtype):
        if (device, samplerate) not in self.ok:
            raise ValueError("Invalid sample rate")


win = [{"name": "Lautsprecher", "max_input_channels": 0},
       {"name": "Mikrofon (Sennheiser USB headse", "max_input_channels": 1},      # MME
       {"name": "Mikrofon (Sennheiser USB headset)", "max_input_channels": 1},    # DirectSound
       {"name": "Mikrofon (Sennheiser USB headset)", "max_input_channels": 2}]    # WASAPI, nur 48000
fs = FakeSd(win, {(2, 44100), (3, 48000)})
check(audio.Analyzer.find_device("Sennheiser", 44100, sd=fs) == 2, "mehrere Treffer: erster, der 44100 Hz kann")
check(audio.Analyzer.find_device("Sennheiser", 48000, sd=fs) == 3, "mehrere Treffer: passende Abtastrate entscheidet")
check(audio.Analyzer.find_device("Sennheiser", sd=fs) == 1, "ohne Abtastrate: erster Treffer wie bisher")
pi = FakeSd([{"name": "USB Audio CODEC: Audio (hw:2,0)", "max_input_channels": 2}], set())
check(audio.Analyzer.find_device("USB", 44100, sd=pi) == 0, "Pi: ein Treffer, keine Pruefung, wie bisher")
check(audio.Analyzer.find_device("Fehlt", 44100, sd=fs) is None, "kein Treffer: None")

# ---- Musik-Teil des Helfers unter Windows (15.11.2026) --------------------------------------------------------------
import prio  # noqa: E402
import music_serve  # noqa: E402
import stick_hold  # noqa: E402
import mixxx_bridge as mb  # noqa: E402

check(prio.lower_priority(10, platform="darwin" if sys.platform == "win32" else sys.platform) in (True, False),
      "niedrige Prioritaet: Mac-Weg ohne Absturz")
if sys.platform == "win32":
    import ctypes  # noqa: E402
    check(prio.lower_priority(10) is True, "Windows: Prozessklasse 'Niedriger als normal' gesetzt")
    from ctypes import wintypes  # noqa: E402
    k32 = ctypes.windll.kernel32
    k32.GetPriorityClass.argtypes = (wintypes.HANDLE,)
    check(k32.GetPriorityClass(k32.GetCurrentProcess()) == prio.BELOW_NORMAL, "Windows: Klasse wirklich BELOW_NORMAL")

check(music_serve.win_trash_dir(r"E:\musik\Pop\a.mp3") == "E:\\Light-Butler Papierkorb" if sys.platform == "win32" else True,
      "Windows-Papierkorb: Ordner oben auf demselben Laufwerk")
wt = tempfile.mkdtemp(prefix="s2l_trash_")
song = os.path.join(wt, "Pop", "Lied.mp3")
os.makedirs(os.path.dirname(song))
open(song, "wb").write(b"musik")
old_dir = music_serve.win_trash_dir
music_serve.win_trash_dir = lambda p: os.path.join(wt, music_serve.OWN_TRASH)
try:
    dest = music_serve.to_trash(song, run=lambda *a, **k: 1 / 0, platform="win32")
    check(not os.path.exists(song) and os.path.isfile(dest) and open(dest, "rb").read() == b"musik"
          and os.path.dirname(dest).endswith(music_serve.OWN_TRASH), "Windows: in den eigenen Papierkorb verschoben, nie geloescht, kein Finder")
    open(song, "wb").write(b"zwei")
    dest2 = music_serve.to_trash(song, platform="win32")
    check(dest2 != dest and os.path.isfile(dest) and os.path.isfile(dest2), "gleicher Name im Papierkorb: nichts ueberschrieben")
finally:
    music_serve.win_trash_dir = old_dir

check(stick_hold.volume_of(r"E:\musik", platform="win32", removable=lambda r: True) == "E:\\" and
      stick_hold.volume_of(r"C:\Users\x\Musik", platform="win32", removable=lambda r: False) == "" and
      stick_hold.volume_of("/Volumes/USB STICK/musik", platform="win32") == "/Volumes/USB STICK",
      "Windows: Stick = Wechsellaufwerk E:\\, Festplatte nicht; Mac-Pfade wie bisher")
check(stick_hold._under(r"E:\musik\a.mp3", "E:\\") and stick_hold._under(r"e:\musik\a.mp3", "E:\\") and
      not stick_hold._under(r"F:\a.mp3", "E:\\") and stick_hold._under("/Volumes/X/a.mp3", "/Volumes/X")
      and not stick_hold._under("/Volumes/X2/a.mp3", "/Volumes/X"), "Sperre gilt nur fuer dieses Laufwerk (Windows und Mac)")
cmd = stick_hold.eject_cmd("E:\\", platform="win32")
check(cmd[0] == "powershell" and "'E:'" in cmd[-1] and "Eject" in cmd[-1], "Windows: Auswerfen ueber den Explorer")
check(stick_hold.eject_cmd("/Volumes/X", platform="darwin") == ["/usr/sbin/diskutil", "eject", "/Volumes/X"], "Mac: diskutil wie bisher")
check(stick_hold.eject_cmd("E:\\'; Remove-Item x; '", platform="win32")[0] != "powershell",
      "ungueltiger Laufwerksname: nie ueber PowerShell (kein fremder Befehl)")

check(mb.file_gone(os.path.join(wt, "gibt_es_nicht.mp3")) and not mb.file_gone(dest), "Datei weg: auch mit Windows-Pfad erkannt")
check(mb.volume_missing("/Volumes/gibt_es_nicht_xyz/a.mp3"), "getrenntes Mac-Laufwerk erkannt (auch unter Windows)")
shutil.rmtree(wt, ignore_errors=True)

finish("test_windows")
