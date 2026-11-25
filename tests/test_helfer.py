"""Light-Butler Helfer: APC und Ton vom Mac ohne Mixxx. Nur einer leitet weiter: laeuft der Helfer (Prozessdatei
~/.light-butler-helfer.pid, Prozess ist wirklich helper.py), haelt sich die Mixxx-Bruecke zurueck."""
import os
import socket
import subprocess
import sys
import tempfile
import time

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "mac", "helper"))
import apc_relay                    # noqa: E402
import helper                       # noqa: E402
from apc_relay import ApcRelay, helper_running   # noqa: E402
from audio_send import AudioSender  # noqa: E402

tmp = tempfile.mkdtemp()
pidf = os.path.join(tmp, "helfer.pid")

# ---- Erkennung ----------------------------------------------------------------------------------------------------
check(not helper_running(pidf), "keine Datei: kein Helfer")
open(pidf, "w").write("999999")
check(not helper_running(pidf), "Prozess gibt es nicht mehr: kein Helfer")
other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
open(pidf, "w").write(str(other.pid))
check(not helper_running(pidf), "fremder Prozess mit derselben Nummer (nach Neustart des Mac): kein Helfer")
fake = os.path.join(tmp, "helper.py")
open(fake, "w").write("import time\ntime.sleep(20)\n")
h = subprocess.Popen([sys.executable, fake])
open(pidf, "w").write(str(h.pid))
check(helper_running(pidf), "laufender helper.py: Helfer erkannt")
other.kill()
h.kill()

# ---- nur ein Helfer -------------------------------------------------------------------------------------------------
os.remove(pidf)
check(helper.claim(pidf) and open(pidf).read() == str(os.getpid()), "erster Helfer traegt sich ein")
helper.release(pidf)
check(not os.path.exists(pidf), "beim Beenden wieder ausgetragen")

# ---- die Mixxx-Bruecke haelt sich zurueck, solange der Helfer laeuft --------------------------------------------------
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", 0))
rx.settimeout(0.3)


class M:
    opened = 0
    get_input_names = staticmethod(lambda: ["APC mini mk2 Control"])
    get_output_names = staticmethod(lambda: ["APC mini mk2 Control"])

    @staticmethod
    def open_input(n):
        M.opened += 1
        return type("P", (), {"iter_pending": lambda s: iter(()), "close": lambda s: None})()

    open_output = open_input


state = {"helper": True}
r = ApcRelay("127.0.0.1", rx.getsockname()[1], mido_mod=M, log=lambda m: None, paused=lambda: state["helper"])
r.start()
time.sleep(1.2)
try:
    rx.recvfrom(2048)
    got = True
except socket.timeout:
    got = False
check(not got and M.opened == 0, "Helfer laeuft: Bruecke oeffnet den APC nicht und sendet nichts")
state["helper"] = False
time.sleep(1.3)
try:
    got = b"hello" in rx.recvfrom(2048)[0]
except socket.timeout:
    got = False
check(got and M.opened >= 1, "Helfer beendet: Bruecke uebernimmt den APC")
state["helper"] = True
time.sleep(1.2)
check(r.inp is None, "Helfer wieder da: Bruecke gibt den APC frei")
r.stop()


class SD:
    asked = 0

    @staticmethod
    def query_devices():
        SD.asked += 1
        return []


snd = AudioSender("127.0.0.1", 9, sd_mod=SD, log=lambda m: None, paused=lambda: True)
snd.start()
time.sleep(1.5)
check(SD.asked == 0 and snd.stream is None, "Helfer laeuft: Bruecke sucht kein BlackHole")
snd.stop()

# ---- Bruecke und Installation ----------------------------------------------------------------------------------------
br = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py")).read()
check(br.count("paused=helper_running") == 3, "Mixxx-Bruecke: APC, Lumi und Ton mit Ruecksicht auf den Helfer")
inst = os.path.join(ROOT, "mac", "helper", "install_helper.sh")
check(subprocess.run(["bash", "-n", inst]).returncode == 0, "install_helper.sh: Syntax in Ordnung")
txt = open(inst).read()
check('cp "$HERE/helper.py" "$SRC/apc_relay.py" "$SRC/audio_send.py" "$SRC/pi_addr.py" "$BASE/"' in txt, "kopiert Helfer, APC- und Ton-Teil (ohne Mixxx-Teile)")
check("<key>LSUIElement</key><true/>" in txt and "NSMicrophoneUsageDescription" in txt, "App ohne Dock-Symbol, mit Mikrofon-Begruendung")
check("MIXXX_BIN" not in txt and "--controller-debug" not in txt, "Installation braucht und startet kein Mixxx (Liedliste aus der Datenbank-Kopie)")
check("--uninstall" in txt and "RunAtLoad" in txt, "Autostart und Entfernen moeglich")
finish("test_helfer")
