"""APC mini mk2 am MacBook: die Mixxx-Bruecke (apc_relay.py) schickt Tasten und Fader per UDP an den Pi (midi_net.py),
die LEDs kommen zurueck. Echte UDP-Pakete ueber localhost, APC und mido nachgebaut (am Mac zum Testen nicht noetig)."""
import os
import socket
import sys
import time
import types

from _common import ROOT, build, check, finish

# ---- mido nachbauen (nur das, was midi_ctl, midi_net und apc_relay benutzen) ----------------------------------
fake = types.ModuleType("mido")


class Message:
    def __init__(self, type, channel=0, note=0, velocity=0, control=0, value=0):
        self.type, self.channel, self.note, self.velocity, self.control, self.value = type, channel, note, velocity, control, value

    @classmethod
    def from_bytes(cls, b):
        st, d1, d2 = b[0], b[1], b[2]
        kind = {0x80: "note_off", 0x90: "note_on", 0xB0: "control_change"}[st & 0xF0]
        if kind == "control_change":
            return cls(kind, st & 15, control=d1, value=d2)
        return cls(kind, st & 15, note=d1, velocity=d2)

    def bytes(self):
        if self.type == "control_change":
            return [0xB0 | self.channel, self.control, self.value]
        return [(0x90 if self.type == "note_on" else 0x80) | self.channel, self.note, self.velocity]


class Port:
    def __init__(self):
        self.queue, self.sent, self.closed = [], [], False

    def iter_pending(self):
        q, self.queue = self.queue, []
        return iter(q)

    def send(self, m):
        self.sent.append(m.bytes())

    def close(self):
        self.closed = True


MAC = {"names": ["APC mini mk2 Control"], "in": Port(), "out": Port()}
PI_LOCAL = {"names": []}
fake.Message = Message
fake.get_input_names = lambda: list(PI_LOCAL["names"])
fake.get_output_names = lambda: list(PI_LOCAL["names"])
sys.modules.setdefault("mido", fake)
mac_mido = types.SimpleNamespace(Message=Message, get_input_names=lambda: list(MAC["names"]),
                                 get_output_names=lambda: list(MAC["names"]),
                                 open_input=lambda n: MAC["in"], open_output=lambda n: MAC["out"])

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from apc_relay import ApcRelay          # noqa: E402
from midi_ctl import MidiController     # noqa: E402
from midi_net import NetMidi, valid     # noqa: E402

# ---- Pi-Empfaenger und Mac-Weiterleitung ueber echtes UDP auf localhost --------------------------------------------
pisock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
pisock.bind(("127.0.0.1", 0))
net = NetMidi(sock=pisock)
net.start()
relay = ApcRelay("127.0.0.1", pisock.getsockname()[1], mido_mod=mac_mido, log=lambda s: None)
relay.start()


def wait(cond, sec=2.0):
    end = time.time() + sec
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


check(wait(lambda: net.connected()), "Pi sieht den APC am Mac (Lebenszeichen mit Geraet)")
check(net.name == "APC mini mk2 Control", "Name des Ports kommt mit")

rig, sh = build(seed=3)
mc = MidiController(sh, map_path=None)
mc.net = net
check(mc._open() and mc.via_net and mc.status()["via"] == "mac", "Controller verbindet sich ueber den Mac")
check(mc.names == ["APC mini mk2 Control (am Musik-Rechner)"], "Panel zeigt: am Musik-Rechner")
check(wait(lambda: len(MAC["out"].sent) >= 80), "LEDs beim Verbinden ausgeschaltet (an den APC am Mac)")

# Taste und Fader vom Mac
MAC["in"].queue += [Message("note_on", note=56, velocity=127), Message("control_change", control=56, value=64)]
got = []
wait(lambda: (got.extend(mc.ins[0].iter_pending()) or len(got) >= 2))
check([(m.type, getattr(m, "note", None) or m.control) for m in got] == [("note_on", 56), ("control_change", 56)],
      "Taste und Fader kommen am Pi an")
for m in got:
    mc.handle(m)
check(mc.last[-2]["what"] == "Note 56" and mc.last[-1]["what"] == "CC 56", "Controller wertet sie aus wie am USB")

# LED vom Pi zum APC
MAC["out"].sent.clear()
mc._raw(5, 21, 6)
check(wait(lambda: [0x96, 5, 21] in MAC["out"].sent), "LED-Farbe (mit Kanal = Verhalten) kommt am APC an")

# ---- Pruefungen und Wechsel ---------------------------------------------------------------------------------------
check(not valid([0xF0, 1, 2]) and not valid([0x90, 200, 1]) and not valid("x") and valid([0x90, 1, 2]),
      "nur Noten und Regler, keine SysEx")
before = len(net.pending)
net.receive(b'{"t":"midi","sid":"' + relay.sid.encode() + b'","d":[240,1,2]}', ("127.0.0.1", 1))
net.receive(b"kaputt", ("127.0.0.1", 1))
check(len(net.pending) == before, "ungueltige Pakete werden verworfen")

relay._run = False                                        # ab hier schicken nur die Pruefungen selbst Pakete,
time.sleep(0.3)                                           # sonst mischen sich Lebenszeichen der laufenden Weiterleitung ein
PI_LOCAL["names"] = ["APC mini mk2 Control"]
mc.net_check = 0.0
check(mc._net_lost(time.time()), "APC jetzt direkt am Pi: Wechsel auf den direkten Anschluss")
PI_LOCAL["names"] = []
old = mc.net_session
net.receive(b'{"t":"hello","sid":"neu123","dev":true,"name":"APC mini mk2 Control"}', relay.addr)
check(net.session == old + 1 and mc._net_lost(time.time()), "App am Mac neu gestartet: neu verbinden, LEDs neu senden")
net.last -= 10
check(not net.connected(), "3 s ohne Lebenszeichen: Verbindung weg")
net.receive(b'{"t":"hello","sid":"neu123","dev":false,"name":""}', relay.addr)
check(not net.connected(), "Mac meldet sich, aber ohne APC: nicht verbunden")
# ---- APC am Mac ab- und wieder angesteckt: der Pi sendet alle LEDs neu ------------------------------------------
gen0 = relay.gen
MAC["names"] = []
relay.check_gone(time.monotonic() + 5)
check(relay.inp is None, "abgezogen: Port verschwindet aus der Liste, Weiterleitung schliesst ihn")
MAC["names"] = ["APC mini mk2 Control"]
relay.last_try = 0.0
relay.connect(time.monotonic() + 10)
check(relay.inp is not None and relay.gen == gen0 + 1, "wieder angesteckt: neu geoeffnet, Zaehler erhoeht")
time.sleep(0.3)                                           # Lebenszeichen von connect() erst ankommen lassen
net.receive(('{"t":"hello","sid":"neu123","dev":true,"name":"APC","gen":%d}' % (gen0 + 5)).encode(), relay.addr)
s0 = net.session                                          # Sitzung neu123 mit Zaehler gen0+5 steht
net.receive(('{"t":"hello","sid":"neu123","dev":true,"name":"APC","gen":%d}' % (gen0 + 6)).encode(), relay.addr)
check(net.session == s0 + 1, "Pi: neuer Zaehler = neue Sitzung (alle LEDs neu senden)")
net.receive(('{"t":"hello","sid":"neu123","dev":true,"name":"APC","gen":%d}' % (gen0 + 6)).encode(), relay.addr)
check(net.session == s0 + 1, "gleicher Zaehler: nichts neu")
relay.stop()
finish("test_apc_mac")
