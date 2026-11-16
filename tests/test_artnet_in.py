"""Art-Net-Eingang (Ersatz fuer den OLA-Pi fuer ein anderes Lichtprogramm): ArtDmx auf UDP 6454 wird statt der Show auf die
DMX-Kette gegeben, immer abgesichert (Laser und Hazer aus, safe_limits, ohne Strobe-Erlaubnis kein Strobe).
BLACKOUT wirkt weiter, nach 3 s ohne Daten uebernimmt die Show. Echte UDP-Pakete ueber localhost."""
import socket
import struct
import time

from _common import build, check, finish, Clock

import dmx
from artnet_in import ArtNetIn, parse_dmx, poll_reply


def artdmx(data, universe=0):
    return (b"Art-Net\x00" + struct.pack("<H", 0x5000) + struct.pack(">H", 14) + bytes([1, 0])
            + struct.pack("<H", universe) + struct.pack(">H", len(data)) + bytes(data))


# ---- Pakete -------------------------------------------------------------------------------------------------------
check(parse_dmx(artdmx(b"\x01\x02\x03")) == (0, b"\x01\x02\x03"), "ArtDmx erkannt")
check(parse_dmx(artdmx(b"\x01", universe=3))[0] == 3, "Universe gelesen")
check(parse_dmx(b"Art-Net\x00" + b"\x00\x20" + bytes(10)) is None and parse_dmx(b"kaputt") is None, "anderes und Muell verworfen")
r = poll_reply("192.168.1.50", 0)
check(len(r) == 239 and r[:8] == b"Art-Net\x00" and r[8:10] == b"\x00\x21" and r[10:14] == bytes([192, 168, 1, 50])
      and b"Light-Butler" in r, "ArtPollReply: 239 Bytes, eigene Adresse, Name Light-Butler")

# ---- echter Empfang ueber UDP ---------------------------------------------------------------------------------------
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("127.0.0.1", 0))
ain = ArtNetIn(0, sock=s, my_ip="127.0.0.1")
ain.start()
tx = dmx.ArtNetSender("127.0.0.1", 0, port=s.getsockname()[1])
tx.send(bytes([7] * 100))
end = time.time() + 2
while ain.frame() is None and time.time() < end:
    time.sleep(0.01)
f = ain.frame()
check(f is not None and len(f) == 512 and f[:100] == bytes([7] * 100) and f[100:] == bytes(412),
      "ArtDmx kommt an, auf 512 Kanaele aufgefuellt")
check(ain.status()["active"] and ain.status()["src"] == "127.0.0.1", "Status: empfaengt, Absender")
tx.send(bytes([9] * 10))
time.sleep(0.05)
other = dmx.ArtNetSender("127.0.0.1", 5, port=s.getsockname()[1])
other.send(bytes([1] * 10))
time.sleep(0.05)
check(ain.frame()[:10] == bytes([9] * 10), "anderes Universe wird ignoriert")
poller = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
poller.bind(("127.0.0.1", 0))
ain.receive(b"Art-Net\x00" + struct.pack("<H", 0x2000) + bytes(4), ("127.0.0.1", poller.getsockname()[1]))
poller.settimeout(1.0)
try:
    rep, _ = poller.recvfrom(1024)
except OSError:
    rep = b""
check(len(rep) == 239 and b"Light-Butler" in rep, "ArtPoll wird beantwortet (Apps finden den Light-Butler)")
ain.t -= 10
check(ain.frame() is None and not ain.active(), "3 s ohne Daten: nichts mehr aktiv")

# ---- Sicherheitsfilter ----------------------------------------------------------------------------------------------
rig, sh = build(strobe=False)


def val(out, name, p):
    fx = rig[name]
    return out[fx.address - 1 + fx.map[p] - 1]


full = bytes([255] * 512)
out = rig.filter_external(full, strobe_ok=False)
lz = rig["laser"]
check(out[lz.address - 1:lz.address - 1 + lz.n] == bytes(lz.n), "KTV-Laser: Leistung 0, alles 0")
hz = next(f for f in rig.fixtures if f.locked)
check(out[hz.address - 1:hz.address - 1 + hz.n] == bytes(hz.n), "Hazer: 0 (Nebel nur per SMOKE)")
lasers_zero = all(val(out, f.name, p) == 0 for f in rig.fixtures if not f.target
                  for p in f.locked_params if p not in f.rest)
check(lasers_zero, "alle Laser-Kanaele (Eyes, Derby) 0")
bad = [(f.name, p) for f in rig.fixtures if not f.target for p, (lo, hi) in f.limits.items()
       if p in f.map and not lo <= val(out, f.name, p) <= hi]
check(not bad, f"safe_limits eingehalten {bad}")
strobes = [(f.name, p) for f in rig.fixtures if not f.target for p in ("strobe", "strobe_a", "strobe_b") if p in f.map]
check(strobes and all(val(out, n, p) == 0 for n, p in strobes), "ohne Strobe-Erlaubnis: Strobe-Kanaele 0")
vega = rig["vega"]
check(val(rig.filter_external(bytes([128] * 512), False), "vega", "shutter") == 255, "Vega-Shutter: Strobo wird zu offen")
eyes = next(f for f in rig.fixtures if "flash" in f.map)
check(val(out, eyes.name, "flash") <= 4, "Eyes-Blitz hoechstens an (1-4)")
with_perm = rig.filter_external(full, strobe_ok=True)
check(all(val(with_perm, n, p) == 255 for n, p in strobes), "mit Strobe-Erlaubnis: Strobe-Kanaele gehen durch")
d1 = rig["docooler_1"]
check(val(out, "docooler_1", "r1") == 255 and val(out, "vega", "dimmer") == 255, "normale Kanaele gehen durch")
check(val(out, "vega", "pan") == rig["vega"].limits["pan"][1], "Bewegungsgrenzen des Vega gelten auch fuer fremde Daten")
check(out[299] == 0 and out[511] == 0, "Kanaele ohne Fixture bleiben 0")

# ---- in der Ausgabe: statt der Show, BLACKOUT, Rueckfall --------------------------------------------------------------


class Rec:
    def __init__(self):
        self.frames = []

    def send(self, d):
        self.frames.append(bytes(d))

    def close(self):
        pass


rig, sh = build(strobe=False)
recs = {}
out = dmx.Output(rig, lambda ip: recs.setdefault(ip, Rec()))
sh.output = out
fake = ArtNetIn(0, clock=time.monotonic)
fake.data, fake.t, fake.src = bytes([255] * 512), time.monotonic(), "192.168.1.77"
out.ext = fake
c = Clock(sh)
c.run(1)


def main_frame():
    frames = rig.render_all()
    out._apply_ext(frames)
    return frames[rig.target]


check(not out.ext_on and main_frame() == rig.render_all()[rig.target], "Standard aus: die Show steuert")
check(sh.snapshot()["artin"] is None, "Panel: Eingang aus")
sh.cfg.set("artnet_in", 1.0)
fake.t = time.monotonic()
c.run(0.1)
check(out.ext_on and main_frame() == rig.filter_external(fake.data, False), "An und Daten: abgesichertes fremdes Bild")
check(sh.snapshot()["artin"]["active"] and sh.snapshot()["artin"]["src"] == "192.168.1.77", "Panel: empfaengt von")
wled = [t for t in rig.targets() if t != rig.target and not str(t).startswith("nanoleaf:")]
frames = rig.render_all()
out._apply_ext(frames)
check(all(frames[t] == rig.render_all()[t] for t in wled), "WLED steuert weiter die Show")
sh.command({"hold": {"name": "blackout", "on": True}})
c.run(0.1)
mf = main_frame()
check(not out.ext_on and mf == rig.render_all()[rig.target] and val(mf, "docooler_1", "r1") == 0 and val(mf, "vega", "dimmer") == 0,
      "BLACKOUT: die Show (dunkel) statt der fremden Daten")
sh.command({"hold": {"name": "blackout", "on": False}})
c.run(0.1)
fake.t = time.monotonic() - 10
check(main_frame() == rig.render_all()[rig.target], "3 s keine Daten: die Show uebernimmt wieder")
sh.output = None
finish("test_artnet_in")
