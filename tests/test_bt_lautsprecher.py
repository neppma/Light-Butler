"""Bluetooth-Lautsprecher als Ausgabe (Wunsch von Markus 25.11.2026): der Pi sendet den Ton (LAN oder vom Handy) an einen
gekoppelten Lautsprecher (bluez-alsa a2dp-source). Ohne Hardware nachgespielt. Geprueft: verbundene Lautsprecher in der
Liste der Ausgaben, Ton ueber "bluealsa-cli open" mit dem Format des Lautsprechers (umgerechnet), nicht verbunden:
Meldung und hoechstens alle BT_CONNECT_S ein Verbindungsversuch, vom Panel gekoppelt: vertraut und gleich verbunden."""
import io
import time

import numpy as np

from _common import check, finish

import bt_audio
from bt_audio import BtManager, PassThrough, convert, list_outputs, speakers

SPK = "11:22:33:44:55:66"
PCMS = ("/org/bluealsa/hci0/dev_AA_BB_CC_11_22_33/a2dpsnk/source\n"
        "/org/bluealsa/hci0/dev_11_22_33_44_55_66/a2dpsrc/sink\n")
state = {"pcms": PCMS}


def runner(cmd, timeout=0):
    if cmd[:2] == ["bluealsa-cli", "list-pcms"]:
        return 0, state["pcms"]
    if cmd[:2] == ["bluealsa-cli", "info"]:
        return 0, "Format: S16_LE\nChannels: 2\nRate: 48000\n"
    if cmd[:2] == ["aplay", "-l"]:
        return 0, "card 0: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]\n"
    return 1, ""


check(speakers(runner) == [(SPK, "/org/bluealsa/hci0/dev_11_22_33_44_55_66/a2dpsrc/sink")], "verbundener Lautsprecher gefunden")
outs = list_outputs(runner, names=lambda mac: "JBL Flip")
check([o["dev"] for o in outs] == ["plughw:CARD=Headphones,DEV=0", "bt:" + SPK]
      and outs[1]["name"] == "Bluetooth-Lautsprecher JBL Flip", "Lautsprecher in den Ausgaben: %s" % outs)
check(all("a2dpsnk" not in p for _, p in speakers(runner)), "das Handy (Eingang) ist kein Lautsprecher")


class Proc:
    def __init__(self, args):
        self.args, self.data, self.closed = args, bytearray(), False
        self.stdin = self
        self.stderr = io.BytesIO(b"")

    def write(self, b):
        self.data += b

    def close(self):
        self.closed = True

    def poll(self):
        return 1 if self.closed else None

    def terminate(self):
        self.closed = True


def wait(cond, s=3.0):
    end = time.time() + s
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


procs, calls = [], []
clock = [1000.0]
pt = PassThrough(spawn=lambda a: procs.append(Proc(a)) or procs[-1], clock=lambda: clock[0], runner=runner,
                 connector=calls.append)
pt._keep_alive = lambda: None                              # hier nur die Umrechnung zaehlen, ohne Stille
pt.set_dev("bt:" + SPK)
x = (np.sin(np.arange(44100) / 20.0) * 10000).astype("<i2")
data = np.stack([x, x], axis=1).tobytes()
for i in range(10):
    pt.write(data[i * 17640:(i + 1) * 17640], 44100, 2)
check(wait(lambda: procs and len(procs[0].data) > 0), "Ton geht an den Lautsprecher")
check(procs[0].args == ["bluealsa-cli", "open", "/org/bluealsa/hci0/dev_11_22_33_44_55_66/a2dpsrc/sink"],
      "ueber bluealsa-cli open auf dem Lautsprecher")
check(wait(lambda: abs(len(procs[0].data) / 4 - 48000) < 200), "auf 48 kHz umgerechnet (%d Bilder)" % (len(procs[0].data) // 4))
pt.close()

# nicht verbunden: Meldung, Verbindungsversuch hoechstens alle BT_CONNECT_S
state["pcms"] = ""
procs.clear()
pt2 = PassThrough(spawn=lambda a: procs.append(Proc(a)) or procs[-1], clock=lambda: clock[0], runner=runner,
                  connector=calls.append)
pt2.set_dev("bt:" + SPK)
pt2.write(b"\x00\x00" * 100, 44100, 2)
check(wait(lambda: "nicht verbunden" in pt2.status()["error"]) and calls == [SPK], "nicht verbunden: Meldung und Anruf")
for step in (bt_audio.OUT_RETRY_S + 0.1, bt_audio.OUT_RETRY_S + 0.1):
    clock[0] += step
    pt2.write(b"\x00\x00" * 100, 44100, 2)
    time.sleep(0.15)
check(calls == [SPK] and not procs, "nicht gleich wieder anrufen")
clock[0] += bt_audio.BT_CONNECT_S
pt2.write(b"\x00\x00" * 100, 44100, 2)
check(wait(lambda: len(calls) == 2), "nach %.0f s wieder anrufen" % bt_audio.BT_CONNECT_S)
state["pcms"] = PCMS
clock[0] += bt_audio.OUT_RETRY_S + 0.1
pt2.write(b"\x00\x00" * 100, 44100, 2)
check(wait(lambda: len(procs) == 1), "verbunden: spielt")
pt2.close()

# Pause: Stille haelt den Lautsprecher verbunden, nach BT_KEEP_S frei (25.11.2026: JBL trennte sich in Pausen)
procs.clear()
pt3 = PassThrough(spawn=lambda a: procs.append(Proc(a)) or procs[-1], clock=lambda: clock[0], runner=runner,
                  connector=calls.append)
pt3.set_dev("bt:" + SPK)
pt3.write(data[:17640], 44100, 2)
check(wait(lambda: procs and len(procs[0].data) > 0), "spielt")
n0 = len(procs[0].data)
pt3.end()                                                  # Musik aus
check(wait(lambda: len(procs[0].data) > n0 + 48000 * 4 * 0.3) and not procs[0].closed, "Pause: Stille, Verbindung bleibt")
tail = bytes(procs[0].data[-4000:])
check(tail == bytes(len(tail)), "es ist wirklich Stille")
clock[0] += bt_audio.BT_KEEP_S + 1
check(wait(lambda: procs[0].closed), "nach %d min ohne Musik: Lautsprecher frei" % (bt_audio.BT_KEEP_S // 60))
pt3.write(data[:17640], 44100, 2)
check(wait(lambda: len(procs) == 2), "Musik kommt wieder: spielt neu")
pt3.close()
procs.clear()
pt4 = PassThrough(spawn=lambda a: procs.append(Proc(a)) or procs[-1], clock=lambda: clock[0], runner=runner)
pt4.set_dev("plughw:CARD=Headphones,DEV=0")
pt4.write(data[:400], 44100, 2)
check(wait(lambda: procs and len(procs[0].data) == 400), "Soundkarte spielt")
time.sleep(0.6)
check(len(procs[0].data) == 400, "Soundkarte: keine Stille in Pausen (nur Bluetooth)")
pt4.end()
check(wait(lambda: procs[0].closed), "Soundkarte: Ende gibt sie frei")
pt4.close()

# Umrechnung: mono -> stereo, gleiche Rate unveraendert
m = np.array([100, -100], dtype="<i2").tobytes()
check(np.frombuffer(convert(m, 44100, 1, 44100, 2, None), dtype="<i2").tolist() == [100, 100, -100, -100], "mono -> stereo")
check(convert(data[:400], 44100, 2, 44100, 2, None) == data[:400], "gleiches Format: unveraendert")


# vom Panel gekoppelt: vertraut, dann gleich verbunden
class FP:
    def __init__(self):
        self.sent, self.stdin, self.stdout = [], self, io.BytesIO(b"")

    def write(self, b):
        self.sent.append(b.decode().strip())

    def flush(self):
        pass

    def poll(self):
        return None


fp = FP()
mclock = [5000.0]
mgr = BtManager(runner=lambda c, t=0: (0, ""), spawn=lambda: fp, clock=lambda: mclock[0], tools=(True, True))
mgr.ensure()
mgr.found[SPK] = "JBL Flip"
mgr.pair(SPK)
mgr.feed("[CHG] Device " + SPK + " Paired: yes\n")
check("trust " + SPK in fp.sent and "connect " + SPK not in fp.sent, "Lautsprecher gekoppelt: vertraut, noch nicht anrufen")
check("verbunden" in mgr.msg, "Meldung: wird verbunden")
mclock[0] += bt_audio.CONNECT_AFTER_S + 0.1
mgr.tick()
check(fp.sent.count("connect " + SPK) == 1, "nach %.0f s verbunden" % bt_audio.CONNECT_AFTER_S)
mgr.feed("Failed to connect: org.bluez.Error.InProgress br-connection-busy\n")
check(mgr.error == "", "InProgress ist kein Fehler")
mgr.feed("Failed to connect: org.bluez.Error.Failed\n")
check("Failed" in mgr.error, "echter Fehler wird gezeigt")
fp2 = FP()
m2 = BtManager(runner=lambda c, t=0: (0, ""), spawn=lambda: fp2, clock=lambda: mclock[0], tools=(True, True))
m2.ensure()
m2.pair(SPK)
m2.feed("[CHG] Device " + SPK + " Paired: yes\n")
m2.feed("[CHG] Device " + SPK + " Connected: yes\n")
mclock[0] += bt_audio.CONNECT_AFTER_S + 0.1
m2.tick()
check("connect " + SPK not in fp2.sent, "hat sich selbst verbunden: kein zweiter Anruf")
finish("test_bt_lautsprecher")
