"""Mixxx-Bruecke, wenn der Pi aus oder nicht erreichbar ist: macOS meldet beim Senden per UDP "Host is down" oder "No route
to host", der Name laesst sich vielleicht gar nicht aufloesen. Fehler 02.11.2026: die Bruecke stuerzte dabei ab, und mit ihr
ging Mixxx zu (seine Ausgabe laeuft in die Bruecke). Jetzt verwirft sie die Daten und sendet weiter, sobald der Pi wieder da ist."""
import io
import os
import socket
import sys
import tempfile
import types
from contextlib import redirect_stdout

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge as mb                    # noqa: E402


class Sock:
    """Wie ein UDP-Socket, der je nach self.err scheitert."""

    def __init__(self):
        self.err, self.sent = None, []

    def sendto(self, data, addr):
        if self.err:
            raise self.err
        self.sent.append(addr)


def retry_now():
    mb._pi_retry = 0.0                        # die Pause nach einem Fehler nicht abwarten


FEHLER = [("Host is down", OSError(64, "Host is down")), ("No route to host", OSError(65, "No route to host")),
          ("Name nicht aufloesbar", socket.gaierror(8, "nodename nor servname provided, or not known"))]

for name, err in FEHLER:
    s = Sock()
    s.err = err
    fw = mb.Forwarder([], s, ("lightbutler.local", 9020), analysis_dir=tempfile.mkdtemp(), analyze=False)
    retry_now()
    try:
        with redirect_stdout(io.StringIO()):
            fw.handle({"d": 1, "tl": "", "du": 0.0})      # Deck leer beim Start: Plan und Zustand werden gesendet
            retry_now()
            fw.handle({"d": 1, "tl": "A - B", "du": 200.0, "fb": 128.0})
        check(True, f"{name}: Bruecke laeuft weiter")
    except OSError as e:
        check(False, f"{name}: Bruecke stuerzt ab ({e})")

# ohne Bibliothek: nur der Zustand
s = Sock()
s.err = FEHLER[0][1]
retry_now()
try:
    with redirect_stdout(io.StringIO()):
        mb.handle_state({"d": 1}, None, s, types.SimpleNamespace(send="lightbutler.local", pi_port=9020))
    check(True, "ohne Bibliothek: Bruecke laeuft weiter")
except OSError as e:
    check(False, f"ohne Bibliothek: Bruecke stuerzt ab ({e})")

# Pi kommt wieder, Meldung nur beim Wechsel, kurze Pause nach einem Fehler
s = Sock()
s.err = FEHLER[0][1]
out = io.StringIO()
mb._pi_down = False                           # die Pruefungen oben haben den Pi schon als weg gemeldet
retry_now()
with redirect_stdout(out):
    for _ in range(5):
        mb.send_udp(s, b"x", ("pi", 9020))
        retry_now()
check(out.getvalue().count("nicht erreichbar") == 1, "die Meldung steht nur einmal im Log, nicht bei jedem Paket")
s.err = None
retry_now()
out2 = io.StringIO()
with redirect_stdout(out2):
    mb.send_udp(s, b"x", ("pi", 9020))
check(len(s.sent) == 1 and "wieder erreichbar" in out2.getvalue(), "Pi wieder da: es wird wieder gesendet und gemeldet")

class Zaehler(Sock):
    def __init__(self):
        super().__init__()
        self.tries = 0

    def sendto(self, data, addr):
        self.tries += 1
        super().sendto(data, addr)


z = Zaehler()
z.err = FEHLER[2][1]
retry_now()
with redirect_stdout(io.StringIO()):
    for _ in range(50):
        mb.send_udp(z, b"x", ("pi", 9020))
check(z.tries == 1, "nach einem Fehler eine Pause: der Name wird nicht bei jedem Paket neu gesucht (das koennte Mixxx bremsen)")
z.err = None
retry_now()
with redirect_stdout(io.StringIO()):
    mb.send_udp(z, b"x", ("pi", 9020))
retry_now()
check(len(z.sent) == 1, "nach der Pause wird es wieder versucht")

finish("test_mixxx_pi_aus")
