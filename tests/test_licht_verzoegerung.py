"""Licht-Verzoegerung (Wunsch von Markus 25.11.2026): kommt die Musik spaeter (Bluetooth-Lautsprecher), geht das ganze
Licht um light_delay_ms spaeter hinaus. Geprueft: 0 = Bild fuer Bild wie frueher, Verzoegerung in ganzen Bildern, Aendern
haelt oder laesst Bilder aus, BLACKOUT sofort, Laser- und Nebel-Kanaele gehen sofort aus (Einschalten verzoegert),
die Show setzt die Werte aus der Einstellung."""
import os

from _common import PI, Clock, build, check, finish

from dmx import Output, Rig

rig = Rig(os.path.join(PI, "fixtures.yaml"))
out = Output(rig, lambda t: None)
T = rig.target


def fr(v, laser=None):
    b = bytearray([v]) * 512
    if laser is not None:
        for i in out.instant_channels()[T]:
            b[i] = laser
    return {T: bytes(b)}


laser = rig["laser"]
inst = out.instant_channels()
check(T in inst and laser.address - 1 in inst[T], "Laser-Kanaele gehen sofort aus")
hz = next(f for f in rig.fixtures if f.manual_ok)
check(hz.address - 1 in inst.get(hz.target or T, []), "Nebel-Kanaele auch")
wash = rig.fixtures[0]
check(wash.address - 1 not in inst[T], "normale Lichter nicht")

seq = [fr(i) for i in range(1, 11)]
check(all(out._delay(f) is f for f in seq), "ohne Verzoegerung: genau das aktuelle Bild")

out.delay_frames = 3
got = [out._delay(fr(i))[T][wash.address - 1] for i in range(1, 11)]
check(got == [1, 1, 1, 1, 2, 3, 4, 5, 6, 7], "3 Bilder (75 ms) spaeter: %s" % got)
out.delay_frames = 1
got2 = [out._delay(fr(i))[T][wash.address - 1] for i in range(11, 14)]
check(got2 == [10, 11, 12], "kleiner: alte Bilder ausgelassen %s" % got2)
out.delay_frames = 4
got3 = [out._delay(fr(i))[T][wash.address - 1] for i in range(14, 20)]
check(got3 == [13, 13, 13, 13, 14, 15], "groesser: altes Bild gehalten %s" % got3)

out.delay_now = True
check(out._delay(fr(99))[T][wash.address - 1] == 99 and not out._delayq, "BLACKOUT: sofort, Warteschlange leer")
out.delay_now = False

out.delay_frames = 4
for i in range(6):
    out._delay(fr(50, laser=200))
o = out._delay(fr(50, laser=0))
check(o[T][laser.address - 1] == 0 and o[T][wash.address - 1] == 50, "Laser aus: sofort, auch wenn das alte Bild an war")
out._delayq.clear()
for i in range(5):
    o = out._delay(fr(50, laser=0 if i < 4 else 200))
check(o[T][laser.address - 1] == 0, "Laser an: erst verzoegert")

# Show setzt die Ausgabe aus der Einstellung
rig2, sh = build()


class Null:
    def send(self, data):
        pass

    def close(self):
        pass


sh.output = Output(rig2, lambda t: Null())
cl = Clock(sh)
cl.run(0.5)
check(sh.output.delay_frames == 0 and not sh.output.delay_now, "Standard 0: Licht wie frueher")
sh.command({"set": {"light_delay_ms": 200}})
cl.run(0.1)
check(sh.output.delay_frames == 8, "200 ms = 8 Bilder")
sh.command({"blackout": True})
cl.run(0.1)
check(sh.output.delay_now, "BLACKOUT: Ausgabe sofort")
finish("test_licht_verzoegerung")
