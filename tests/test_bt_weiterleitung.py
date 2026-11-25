"""Bluetooth-Ton weiterleiten (Wunsch von Markus 25.11.2026): wer am Handy den Pi als Ausgabe waehlt, hoert am Handy nichts
mehr. Der Pi gibt den Ton darum an eine gewaehlte Ausgabe weiter (Kopfhoerer-Anschluss, USB-Soundkarte, HDMI) ueber aplay.
Ohne Hardware: aplay und bluez-alsa werden nachgespielt. Geprueft: Ausgaben aus "aplay -l", Weitergabe derselben Bytes
mit passendem Format, Ende der Verbindung gibt die Ausgabe frei, Fehler der Ausgabe mit Meldung und neuem Versuch, eine
haengende Ausgabe haelt den Eingang nie auf, Weiterleitung auch ohne Eingang Bluetooth, Wahl in audio.json gemerkt.
Dasselbe fuer den Ton vom Musik-Rechner (LAN, UDP 9022)."""
import io
import json
import os
import tempfile
import threading
import time

from _common import audio, check, finish

import bt_audio
from bt_audio import BT_NAME, BtAudioIn, PassThrough, list_outputs

APLAY_L = """**** List of PLAYBACK Hardware Devices ****
card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
  Subdevices: 8/8
  Subdevice #0: subdevice #0
card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
card 2: CODEC [USB Audio CODEC], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
card 3: vc4hdmi0 [vc4-hdmi-0], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
  Subdevices: 1/1
"""


def out_runner(cmd, timeout=0):
    return (0, APLAY_L) if cmd[:2] == ["aplay", "-l"] else (1, "")


outs = list_outputs(out_runner)
check([o["dev"] for o in outs] == ["plughw:CARD=Headphones,DEV=0", "plughw:CARD=Device,DEV=0", "plughw:CARD=CODEC,DEV=0",
                                    "plughw:CARD=vc4hdmi0,DEV=0"], "Ausgaben aus aplay -l: %s" % [o["dev"] for o in outs])
check([o["name"] for o in outs] == ["Kopfhörer-Anschluss des Licht-Rechners", "USB Audio Device", "USB Audio CODEC", "HDMI 1"],
      "lesbare Namen: %s" % [o["name"] for o in outs])
check(list_outputs(lambda c, t=0: (1, "")) == [], "ohne aplay: keine Ausgaben")


class Aplay:
    """nachgespieltes aplay: sammelt die Bytes, kann sterben oder haengen."""
    def __init__(self, args, die=False, hang=None):
        self.args, self.data, self.closed, self.die, self.hang = args, bytearray(), False, die, hang
        self.stdin = self
        self.stderr = io.BytesIO(b"aplay: main:850: audio open error: Device or resource busy\n")

    def write(self, b):
        if self.hang is not None:
            self.hang.wait()
        if self.die:
            raise BrokenPipeError("weg")
        self.data += b

    def close(self):
        self.closed = True

    def poll(self):
        return 1 if self.die or self.closed else None

    def terminate(self):
        self.closed = True


def wait(cond, s=3.0):
    end = time.time() + s
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


procs = []
pt = PassThrough(spawn=lambda a: procs.append(Aplay(a)) or procs[-1])
pt.write(b"\x01\x00" * 100, 48000, 2)
time.sleep(0.1)
check(not procs, "ohne gewaehlte Ausgabe: kein aplay")
pt.set_dev("plughw:CARD=CODEC,DEV=0")
pt.write(b"\x01\x00\x02\x00" * 100, 48000, 2)
pt.write(b"\x03\x00\x04\x00" * 100, 48000, 2)
check(wait(lambda: procs and len(procs[0].data) == 800), "Bytes gehen unveraendert an aplay")
a = procs[0].args
check(a[0] == "aplay" and a[a.index("-D") + 1] == "plughw:CARD=CODEC,DEV=0" and a[a.index("-r") + 1] == "48000"
      and a[a.index("-c") + 1] == "2" and a[a.index("-f") + 1] == "S16_LE", "aplay mit Ausgabe und Format des Handys")
check(pt.status()["active"] and pt.status()["dev"] == "plughw:CARD=CODEC,DEV=0", "Stand: spielt")
pt.write(b"\x00\x00" * 100, 44100, 2)
check(wait(lambda: len(procs) == 2) and procs[0].closed and procs[1].args[procs[1].args.index("-r") + 1] == "44100",
      "anderes Format: aplay neu mit 44100 Hz")
pt.end()
check(wait(lambda: procs[1].closed), "Ende der Verbindung gibt die Ausgabe frei")
pt.set_dev("plughw:CARD=Headphones,DEV=0")
pt.write(b"\x00\x00" * 10, 44100, 2)
check(wait(lambda: len(procs) == 3) and "Headphones" in procs[2].args[procs[2].args.index("-D") + 1], "Wechsel der Ausgabe")
pt.set_dev("")
pt.write(b"\x00\x00" * 10, 44100, 2)
check(wait(lambda: procs[2].closed) and len(procs) == 3, "Nicht weiterleiten: aplay zu, kein neues")
pt.close()

# Ausgabe besetzt: Meldung, neuer Versuch erst nach OUT_RETRY_S
clock = [1000.0]
dead = []
pt2 = PassThrough(spawn=lambda a: dead.append(Aplay(a, die=True)) or dead[-1], clock=lambda: clock[0])
pt2.set_dev("plughw:CARD=Device,DEV=0")
pt2.write(b"\x00\x00" * 10, 48000, 2)
check(wait(lambda: "busy" in pt2.status()["error"]), "Fehler der Ausgabe im Stand: %r" % pt2.status()["error"])
pt2.write(b"\x00\x00" * 10, 48000, 2)
time.sleep(0.15)
check(len(dead) == 1, "kein neuer Versuch sofort")
clock[0] += bt_audio.OUT_RETRY_S + 0.1
pt2.write(b"\x00\x00" * 10, 48000, 2)
check(wait(lambda: len(dead) == 2), "neuer Versuch nach %.0f s" % bt_audio.OUT_RETRY_S)
pt2.close()

# haengende Ausgabe: write kehrt sofort zurueck, zu viel wird verworfen
hang = threading.Event()
pt3 = PassThrough(spawn=lambda a: Aplay(a, hang=hang))
pt3.set_dev("plughw:CARD=Device,DEV=0")
t0 = time.time()
for _ in range(bt_audio.OUT_QUEUE * 3):
    pt3.write(b"\x00\x00" * 512, 48000, 2)
check(time.time() - t0 < 0.5 and pt3.status()["dropped"] > 0, "haengende Ausgabe haelt den Eingang nicht auf")
hang.set()
pt3.close()


# Eingang mit Weiterleitung: dieselben Bytes wie vom Handy
PCMS = "/org/bluealsa/hci0/dev_AA_BB_CC_11_22_33/a2dpsnk/source\n"
raw = bytes(range(256)) * 400


class Pcm:
    def __init__(self, data):
        self.stdout = io.BytesIO(data)

    def terminate(self):
        pass


def pcm_runner(cmd, timeout=0):
    if cmd[:2] == ["bluealsa-cli", "list-pcms"]:
        return 0, PCMS
    if cmd[:2] == ["bluealsa-cli", "info"]:
        return 0, "Format: S16_LE\nChannels: 2\nRate: 48000\n"
    return 1, ""


class Rec:
    def __init__(self):
        self.data, self.ends, self.fmt = bytearray(), 0, None

    def write(self, d, rate, ch):
        self.data += d
        self.fmt = (rate, ch)

    def end(self):
        self.ends += 1


rec, blocks = Rec(), []
bi = BtAudioIn(blocks.append, 44100, 512, runner=pcm_runner, opener=lambda p: Pcm(raw), out=rec)
bi._run = True
bi.once()
check(bytes(rec.data) == raw and rec.fmt == (48000, 2) and rec.ends == 1, "Eingang gibt dieselben Bytes weiter, dann Ende")
check(len(blocks) > 0, "und liefert weiter Bloecke an die Analyse")
rec2 = Rec()
bi2 = BtAudioIn(None, 44100, 512, runner=pcm_runner, opener=lambda p: Pcm(raw), out=rec2)
bi2._run = True
bi2.once()
check(bytes(rec2.data) == raw and bi2.blocks == 0 and bi2.status()["alive"], "nur weiterleiten: keine Bloecke, aber Stand lebt")

# Analyzer: Weiterleitung auch, wenn der Eingang nicht Bluetooth ist; Wahl in audio.json
tmp = tempfile.mkdtemp()
af = os.path.join(tmp, "audio.json")
spawned = []
audio.Analyzer.bt_opts = {"runner": pcm_runner, "opener": lambda p: Pcm(raw * 4)}
audio.Analyzer.bt_out_opts = {"runner": out_runner, "spawn": lambda a: spawned.append(Aplay(a)) or spawned[-1]}
an = audio.Analyzer("default", 44100, 512, audio_file=af)
try:
    an.set_bt_out("plughw:CARD=Gibtsnicht,DEV=0")
    bad = False
except ValueError:
    bad = True
check(bad and an.bt_out == "", "unbekannte Ausgabe abgelehnt")
an.set_bt_out("plughw:CARD=CODEC,DEV=0")
check(an._bt is None and an._bt_fwd is not None, "Eingang nicht Bluetooth: eigener Leser nur fuer die Weiterleitung")
check(wait(lambda: spawned and len(spawned[0].data) >= len(raw)), "Ton vom Handy geht an USB Audio CODEC")
check(json.load(open(af))["bt_out"] == "plughw:CARD=CODEC,DEV=0", "Wahl in audio.json gemerkt")
info = an.bt_out_info()
check(info["dev"] == "plughw:CARD=CODEC,DEV=0" and len(info["outs"]) == 4, "Stand fuer das Panel mit Ausgaben")
an.set_bt_out("")
check(an._bt_fwd is None and wait(lambda: spawned[-1].closed), "Nicht weiterleiten: Leser und aplay zu")
an2 = audio.Analyzer("default", 44100, 512, audio_file=af)
an2._load_audio_cfg()
check(an2.bt_out == "", "aus gemerkt")
an.stop()

# Eingang Bluetooth mit Weiterleitung: ein Leser fuer beides
spawned.clear()
an3 = audio.Analyzer(BT_NAME, 44100, 512, audio_file=af)
an3.bt_out = "plughw:CARD=Headphones,DEV=0"
an3.start()
check(an3._bt is not None and an3._bt_fwd is None and an3._bt.out is an3._pt, "Eingang Bluetooth: derselbe Leser leitet weiter")
check(an3.fwd_state()["kind"] == "line" and an3.fwd_state()["name"] == "Kopfhörer-Anschluss des Licht-Rechners",
      "Anzeige oben: Weiterleitung an den Kopfhoerer-Anschluss")
check(wait(lambda: spawned and len(spawned[0].data) >= len(raw)) and an3._bt.blocks > 0, "Analyse und Kopfhoerer bekommen den Ton")
check(an3.fwd_state()["active"], "Anzeige: spielt")
an3.bt_out = ""
check(an3.fwd_state() is None, "ohne Weiterleitung: kein Pfeil")
an3.bt_out = "plughw:CARD=Headphones,DEV=0"
an3.stop()
check(an3._pt is None and an3._bt is None, "Beenden schliesst Eingang und Ausgabe")
audio.Analyzer.bt_opts = {}

# Ton vom Musik-Rechner (LAN) weiterleiten (25.11.2026): dieselben Samples als int16, mit Ersatz fuer Luecken
import socket
import numpy as np
import audio_net
from audio_net import NET_NAME, NetAudioIn


def pkt(seq, val, ch=2, n=256):
    x = np.full(n * ch, val, dtype="<i2")
    return audio_net.HEAD.pack(audio_net.MAGIC, seq, 44100, ch, 1) + x.tobytes()


rec3, nb = Rec(), []
ni = NetAudioIn(nb.append, 44100, 512, out=rec3)
ni.receive(pkt(1, 1000), ("10.0.0.5", 1))
ni.receive(pkt(2, -2000), ("10.0.0.5", 1))
got = np.frombuffer(bytes(rec3.data), dtype="<i2")
check(len(got) == 1024 and got[0] == 1000 and got[-1] == -2000 and rec3.fmt == (44100, 2), "LAN: dieselben Samples an die Ausgabe")
check(len(nb) == 1, "und weiter an die Analyse")
ni.receive(pkt(4, 500), ("10.0.0.5", 1))                       # Paket 3 verloren: Ersatz geht mit
check(len(np.frombuffer(bytes(rec3.data), dtype="<i2")) == 2048, "verlorenes Paket: Ersatz auch an die Ausgabe")
rec4, nb4 = Rec(), []
ni4 = NetAudioIn(None, 44100, 512, out=rec4)
ni4.receive(pkt(1, 7), ("10.0.0.5", 1))
check(len(rec4.data) == 1024 and ni4.status()["alive"], "nur weiterleiten: Stand lebt, keine Bloecke")

spawned.clear()
an4 = audio.Analyzer("default", 44100, 512, audio_file=af)
an4.net_port = 0
an4.set_net_out("plughw:CARD=Device,DEV=0")
check(an4.fwd_state() is None, "Eingang nicht LAN: oben kein Pfeil fuer LAN")
check(an4._net is None and an4._net_fwd is not None and an4._net_fwd.sock is not None,
      "Eingang nicht LAN: eigener Empfaenger nur fuer die Weiterleitung")
port = an4._net_fwd.sock.getsockname()[1]
snd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for i in range(1, 6):
    snd.sendto(pkt(i, 300), ("127.0.0.1", port))
check(wait(lambda: spawned and len(spawned[0].data) >= 5 * 1024), "Ton vom Musik-Rechner geht an USB Audio Device")
check("Device" in spawned[0].args[spawned[0].args.index("-D") + 1], "auf der gewaehlten Ausgabe")
check(json.load(open(af))["net_out"] == "plughw:CARD=Device,DEV=0", "Wahl in audio.json gemerkt (net_out)")
check(an4.net_out_info()["dev"] == "plughw:CARD=Device,DEV=0", "Stand fuer das Panel")
try:
    an4.set_net_out("plughw:CARD=Nix,DEV=0")
    bad = False
except ValueError:
    bad = True
check(bad, "unbekannte Ausgabe abgelehnt")
an4.set_net_out("")
check(an4._net_fwd is None, "Nicht weiterleiten: Empfaenger zu")
an4.stop()

# Eingang LAN mit Weiterleitung: ein Empfaenger fuer beides
spawned.clear()
an5 = audio.Analyzer(NET_NAME, 44100, 512, audio_file=af)
an5.net_port = 0
an5.net_out = "plughw:CARD=CODEC,DEV=0"
an5.start()
check(an5._net is not None and an5._net_fwd is None and an5._net.out is an5._pt_net, "Eingang LAN: derselbe Empfaenger leitet weiter")
port = an5._net.sock.getsockname()[1]
for i in range(1, 6):
    snd.sendto(pkt(i, 300), ("127.0.0.1", port))
check(wait(lambda: spawned and len(spawned[0].data) >= 5 * 1024), "Analyse und Ausgabe bekommen den Ton")
an5.stop()
check(an5._pt_net is None and an5._net is None, "Beenden schliesst Empfaenger und Ausgabe")
snd.close()
audio.Analyzer.bt_out_opts = {}
finish("test_bt_weiterleitung")
