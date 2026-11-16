"""Probelauf ohne Mixxx (14.11.2026): die Hintergrund-Analyse zaehlte ihre Lieder beim Start, bevor die Ordner-Liste da war,
und analysierte ohne Mixxx-Datenbank nie ein Lied. Jetzt startet sie neu, sobald neue Ordner-Lieder kommen und sie nicht laeuft."""
import os
import socket
import sys
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge as mb  # noqa: E402

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
fw = mb.Forwarder([], s, ("127.0.0.1", 9), analysis_dir=os.path.join(tmp, "an"), analyze=False)
starts = []


class Proc:
    def __init__(self, alive):
        self.alive = alive

    def is_alive(self):
        return self.alive


def fake_start(pause_s=1.0):
    starts.append(len(fw.lib))
    fw.bg = {"proc": Proc(True)} if fw.lib else {}
    return len(fw.lib)


fw.start_background = fake_start
fw.start_background()                                     # Start wie im Helfer: noch keine Lieder (keine Mixxx-Datenbank)


class FL:
    def __init__(self):
        self.ver, self.songs = 1, [{"path": "/m/a.mp3", "duration": 100.0, "bpm": 0, "kid": 0}]

    def due(self, root, now=None):
        return False


fw.folder, fw.folder_root = FL(), tmp
fw.folder_tick()
check(starts == [0, 1], "Ordner-Liste da: Analyse startet neu und sieht das Lied: " + str(starts))
fw.folder.ver, fw.folder.songs = 2, fw.folder.songs + [{"path": "/m/b.mp3", "duration": 90.0, "bpm": 0, "kid": 0}]
fw.folder_tick()
check(starts == [0, 1], "laeuft noch: kein zweiter Start")
fw.bg["proc"].alive = False
fw.folder.ver = 3
fw.folder_tick()
check(starts == [0, 1, 2], "fertig und neue Lieder: wieder an")
fw2 = mb.Forwarder([], s, ("127.0.0.1", 9), analysis_dir=os.path.join(tmp, "an"), analyze=False)
fw2.start_background = lambda pause_s=1.0: starts.append("nein")
fw2.folder, fw2.folder_root = FL(), tmp
fw2.folder_tick()
check("nein" not in starts, "ohne Hintergrund-Analyse (bg nie gestartet): bleibt aus")
finish("test_ohne_mixxx_analyse")
