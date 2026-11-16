"""DMX direkt ueber den USB-Adapter (FTDI, Open DMX): DMX-Bild mit Break und Startcode, nur bis zum letzten belegten
Kanal, dieselben Bytes wie per Art-Net (Laser-Sperre bleibt), Umschalten OLA/USB mit Blackout auf dem alten Weg,
Neuverbindung, wenn der Adapter fehlt, Anzeige im Panel. Alles mit einem nachgebauten Adapter, ohne Hardware."""
import os
import subprocess
import tempfile

from _common import PI, build, check, finish, Clock

import dmx
import dmx_usb
import webpanel
from dmx_usb import DmxRouter, OpenDmxSender


class FakeSerial:
    """Nachgebauter Adapter: merkt sich Break-Wechsel und geschriebene Bytes in der Reihenfolge."""
    fail_open = False
    opened = []

    def __init__(self, port, baud, **kw):
        if FakeSerial.fail_open:
            raise OSError("nicht da")
        self.port, self.baud, self.kw = port, baud, kw
        self.log, self.closed = [], False
        FakeSerial.opened.append(self)

    @property
    def break_condition(self):
        return False

    @break_condition.setter
    def break_condition(self, v):
        self.log.append(("break", v))

    def write(self, b):
        if self.closed:
            raise OSError("abgezogen")
        self.log.append(("data", bytes(b)))

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeMod:
    Serial = FakeSerial


class Recorder:
    def __init__(self):
        self.frames, self.closed = [], False

    def send(self, data):
        self.frames.append(bytes(data))

    def close(self):
        self.closed = True


# ---- ein DMX-Bild --------------------------------------------------------------------------------
s = OpenDmxSender("/dev/ttyUSB0", 282, serial_mod=FakeMod, threaded=False)
s.send(bytes(range(256)) * 2)
ser = FakeSerial.opened[-1]
check(ser.baud == 250000 and ser.kw.get("stopbits") == 2 and ser.kw.get("bytesize") == 8 and ser.kw.get("parity") == "N",
      "Adapter mit 250 kBaud, 8 Datenbits, keine Paritaet, 2 Stopbits")
check([e[0] for e in ser.log] == ["break", "break", "data"] and ser.log[0][1] is True and ser.log[1][1] is False,
      "Break an, Break aus, dann die Daten")
pkt = ser.log[2][1]
check(len(pkt) == 283 and pkt[0] == 0, "Startcode 0 und genau 282 Kanaele")
check(pkt[1:] == (bytes(range(256)) * 2)[:282], "Kanalwerte unveraendert")
s.send(bytes(10))
check(len(ser.log[-1][1]) == 283, "zu kurzes Bild wird mit Nullen aufgefuellt")
check(OpenDmxSender(None, 5, serial_mod=FakeMod).n == 24, "mindestens 24 Kanaele (DMX-Norm)")
st = s.status()
check(st["ok"] and st["port"] == "/dev/ttyUSB0" and st["frames"] == 2, "Status: verbunden, Port, gesendete Bilder")

# ---- Adapter fehlt, wird abgezogen, kommt wieder --------------------------------------------------
FakeSerial.fail_open = True
s2 = OpenDmxSender("/dev/ttyUSB0", 100, serial_mod=FakeMod, threaded=False)
s2.send(bytes(100))
check(not s2.status()["ok"] and s2.status()["err"] == "open", "Adapter nicht zu oeffnen: Fehler 'open', kein Absturz")
FakeSerial.fail_open = False
s2.send(bytes(100))
check(not s2.status()["ok"], "neuer Versuch erst nach 2 s (kein Dauerversuch in jedem Bild)")
s2.next_try = 0
s2.send(bytes(100))
check(s2.status()["ok"], "danach verbunden")
FakeSerial.opened[-1].closed = True                       # abgezogen
s2.send(bytes(100))
check(not s2.status()["ok"] and s2.status()["err"] == "write", "abgezogen: Fehler 'write', Verbindung zu")
s2.next_try = 0
s2.send(bytes(100))
check(s2.status()["ok"], "wieder eingesteckt: verbindet neu")
s3 = OpenDmxSender(None, 100, serial_mod=type("M", (), {"Serial": FakeSerial, "fake_ports": []}), threaded=False)
s3.send(bytes(100))
check(s3.status()["err"] == "notfound", "kein FTDI-Adapter gefunden: Fehler 'notfound'")

# ---- Thread: jedes Bild genau einmal, Ende mit dem letzten Bild ----------------------------------
t = OpenDmxSender("/dev/ttyUSB0", 50, serial_mod=FakeMod)
import time
for i in range(5):
    t.send(bytes([i + 1]) * 50)
    time.sleep(0.03)
t.send(bytes(50))                                         # Blackout beim Beenden
t.close()
datas = [e[1] for e in FakeSerial.opened[-1].log if e[0] == "data"]
check([d[1] for d in datas[:5]] == [1, 2, 3, 4, 5], "Thread sendet jedes Bild der Reihe nach")
check(datas[-1] == bytes(51), "beim Schliessen geht das letzte Bild (Blackout) noch raus")
check(FakeSerial.opened[-1].closed, "Adapter danach freigegeben")

# ---- Weiche OLA/USB ------------------------------------------------------------------------------
ola, usbs = Recorder(), []


def mk():
    usbs.append(Recorder())
    return usbs[-1]


r = DmxRouter(ola, mk)
r.send(b"\x05" * 8)
check(ola.frames == [b"\x05" * 8] and not usbs, "Standard: Art-Net zum OLA-Pi, USB wird nicht angefasst")
r.set_via("usb")
for _ in range(8):
    r.send(b"\x07" * 8)
check(ola.frames[1:7] == [bytes(8)] * 6 and len(ola.frames) == 7, "Umschalten auf USB: OLA bekommt 6 Blackout-Bilder, dann nichts mehr")
check(usbs and usbs[0].frames == [b"\x07" * 8] * 8, "USB bekommt ab sofort jedes Bild")
r.set_via("ola")
for _ in range(7):
    r.send(b"\x09" * 8)
check(usbs[0].frames[8:14] == [bytes(8)] * 6 and usbs[0].closed and r.usb is None,
      "zurueck auf OLA: USB bekommt 6 Blackout-Bilder und wird freigegeben")
check(ola.frames[-7:] == [b"\x09" * 8] * 7, "OLA bekommt wieder jedes Bild")
check(r.status()["via"] == "ola" and r.status()["usb"] is None, "Status der Weiche")

# ---- echter Aufbau: Kanalzahl, make_sender, gleiche Bytes wie per Art-Net ------------------------
rig, sh = build(strobe=False)
check(rig.dmx_channels() == 334, "USB sendet bis Kanal 334 (KTV), WLED und Nanoleaf haben eigene Ziele")
check((334 + 1) * 44e-6 + 0.0002 < 0.025, "ein Bild mit 334 Kanaelen passt auf der Leitung in den 40-Hz-Takt")
snd = dmx.make_sender(rig, rig.target)
check(isinstance(snd, DmxRouter) and snd.via == "ola", "Hauptziel ist die Weiche, Standard OLA-Pi")
check(isinstance(dmx.make_sender(rig, rig.target, dry_run=True), dmx.PrintSender), "Trockenlauf: kein Adapter")
snd.close()
check(sh.cfg["dmx_via"] == 0.0, "Einstellung DMX-Weg steht anfangs auf OLA-Pi")


class FakeOutput:
    def __init__(self, router):
        self.senders = {rig.target: router}
        self.mode = {}

    def set_enabled(self, *a, **k):
        pass

    def wake_wled(self, t):
        return []

    def is_sending(self, t):
        return True

    def notify(self):
        pass


usb_frames = Recorder()
router = DmxRouter(Recorder(), lambda: usb_frames)
sh.output = FakeOutput(router)
c = Clock(sh)
c.run(1.0)
check(router.via == "ola" and sh.snapshot()["dmx_via"] == "ola" and sh.snapshot()["dmx_usb"] is None, "OLA-Weg: kein USB-Status")
sh.cfg.set("dmx_via", 1.0)
c.run(0.1)
check(router.via == "usb", "Einstellung DMX-Weg USB schaltet die Weiche um")
check(sh.snapshot()["dmx_via"] == "usb" and sh.snapshot()["dmx_usb"]["err"] == "wait", "Status: Adapter wird gesucht")
for _ in range(40):
    c.run(0.025)
    data = rig.render_all()[rig.target]
    router.send(data)
lz = rig["laser"]
rest = bytes(lz.rest.get(p, 0) for p in sorted(lz.map, key=lambda p: lz.map[p]))
check(all(f[lz.address - 1:lz.address - 1 + lz.n] == rest and f[lz.address - 1] == 0 for f in usb_frames.frames[6:]),
      "AUTO: KTV-Laser auch ueber USB im Ruhezustand, Leistung 0 (gleiche Sicherheitslogik)")
check(usb_frames.frames[-1] == bytes(rig.render_all()[rig.target]), "USB bekommt genau die Bytes, die sonst per Art-Net gingen")
sh.output = None

# ---- Panel ---------------------------------------------------------------------------------------
page = webpanel.make_page()
check('id="via_ola"' in page and 'id="via_usb"' in page and "c({set:{dmx_via:1}})" in page, "Panel: Schalter DMX-Weg")
check("tr('usb_e_'+(u.err||'wait'))" in page, "Panel: Fehler des Adapters uebersetzt")
import texts
cat = texts.catalog() if callable(getattr(texts, "catalog", None)) else {}
keys = str(cat)
check(all(k in keys for k in ("usb_e_wait", "usb_e_dry", "usb_e_nomod", "usb_e_notfound", "usb_e_open", "usb_e_write")),
      "alle Fehlertexte vorhanden")
js = page.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True                                             # ohne node (am Pi) nicht pruefbar
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")


class FakeShow:
    def __init__(self, usb):
        self.rig, self.home, self.usb = rig, None, usb

    def dmx_usb_status(self):
        return self.usb


fs = FakeShow({"ok": True, "port": "/dev/ttyUSB0"})
calls = []
orig = webpanel._reachable
webpanel._reachable = lambda ip, port: calls.append(ip) or True
orig_sleep = webpanel.time.sleep


def stop(_):
    raise StopIteration


webpanel.time.sleep = stop
try:
    webpanel._watch_hosts(fs)
except StopIteration:
    pass
webpanel._reachable, webpanel.time.sleep = orig, orig_sleep
check("Art-Net-Gateway" not in fs.reach and fs.reach.get("DMX-USB") is True and fs.reach_ip["DMX-USB"] == "/dev/ttyUSB0",
      "Verbindungen: bei USB der Adapter statt des OLA-Pi")
check(rig.target not in calls, "OLA-Pi wird bei USB nicht abgefragt")
check("DMX-USB" in sh.PARTY_LIGHTS, "Adapter zaehlt fuer das Wohnzimmerlicht als Partylicht")
check(webpanel.ping_cmd("1.2.3.4", "linux") == ["ping", "-c", "1", "-W", "1", "1.2.3.4"]
      and webpanel.ping_cmd("1.2.3.4", "darwin")[1:3] == ["-c", "1"], "Ping am Pi und Mac wie bisher")
check(webpanel.ping_cmd("1.2.3.4", "win32") == ["ping", "-n", "1", "-w", "1000", "1.2.3.4"], "Ping unter Windows: -n 1 -w 1000")
finish("test_dmx_usb")
