"""Uhren-Ausgleich der Weiterleitung (Fehlerbericht 25.11.2026: Aussetzer an der JBL-Box). Quelle (Mac ueber LAN) und
Lautsprecher haben eigene Uhren; lief der Lautsprecher etwas langsamer, wuchs die Warteschlange bis voll, dann fiel jedes
Mal ein Stueck Ton weg (64 Mal in 8 Minuten). Jetzt passt die Umrechnung das Tempo um hoechstens 0,5 % an.
Ohne echte Zeit nachgestellt (unabhaengig von der Last am Rechner): Lautsprecher 0,4 % langsamer, gleich, 0,3 % schneller."""
import io

import numpy as np

from _common import check, finish

import bt_audio
from bt_audio import PassThrough, Resampler, convert

RATE = 44100
STEP = 256 / RATE                  # ein LAN-Paket


class Device:
    """Lautsprecher, der langsamer abspielt (blockiert wie bluealsa, wenn sein Puffer von 0,1 s voll ist)."""
    def __init__(self):
        self.frames = 0
        self.stdin, self.stderr = self, io.BytesIO(b"")

    def write(self, b):
        self.frames += len(b) // 4

    def close(self):
        pass

    def poll(self):
        return None

    def terminate(self):
        pass


def runner(cmd, timeout=0):
    if cmd[:2] == ["bluealsa-cli", "list-pcms"]:
        return 0, "/org/bluealsa/hci0/dev_11_22_33_44_55_66/a2dpsrc/sink\n"
    if cmd[:2] == ["bluealsa-cli", "info"]:
        return 0, "Format: S16_LE\nChannels: 2\nRate: 44100\n"
    return 1, ""


def simulate(factor, secs, control=True):
    """Ohne echte Zeit: je Paketzeit kommt ein Paket (Quelle), der Lautsprecher nimmt nur so viel, wie er bis dahin mit
    seiner Uhr (factor) abgespielt hat plus 0,1 s Puffer; den Rest haelt die Warteschlange. Liefert (verworfen, Korrektur %,
    groesste Fuellung der zweiten Haelfte in s)."""
    clock = [0.0]
    dev = Device()
    pt = PassThrough(spawn=lambda a: dev, runner=runner, connector=lambda m: None, clock=lambda: clock[0])
    pt._run = False                                  # den Faden anhalten: hier wird von Hand bearbeitet
    pt._thread.join(timeout=2)
    if not control:
        old = bt_audio.DRIFT_MAX
        bt_audio.DRIFT_MAX = 0.0
    pt.set_dev("bt:11:22:33:44:55:66")
    pt._handle(pt.q.get_nowait())                    # set_dev legt ein None in die Warteschlange
    pkt = np.zeros((256, 2), dtype="<i2").tobytes()
    fills = []
    n = int(secs / STEP)
    for i in range(n):
        clock[0] = i * STEP
        pt.write(pkt, RATE, 2)
        room = clock[0] * RATE * factor + 0.1 * RATE
        while not pt.q.empty() and dev.frames < room:
            pt._handle(pt.q.get_nowait())
        if i > n // 2:
            fills.append(pt.qframes / RATE)
    if not control:
        bt_audio.DRIFT_MAX = old
    return pt.dropped, pt.status()["drift"], max(fills)


dropped, drift, fill = simulate(0.996, 60)
check(dropped == 0, "60 s mit 0,4 %% langsamerem Lautsprecher: nichts verworfen (%d)" % dropped)
check(0.2 < drift <= 0.5, "Ausgleich: %.3f %% schneller" % drift)
check(fill < 0.4, "Warteschlange bleibt klein (hoechstens %.2f s)" % fill)
d0, _, f0 = simulate(0.996, 300, control=False)
check(f0 > 0.8, "ohne Ausgleich waechst sie in 5 min auf %.2f s, so war es (dann lief sie voll)" % f0)
dropped, drift, fill = simulate(1.0, 120)
check(dropped == 0 and abs(drift) < 0.1 and fill < 0.3, "gleiche Uhren: nichts verworfen, nach dem Einpendeln kaum Korrektur (%.3f %%)" % drift)
dropped, drift, fill = simulate(1.003, 60)
check(dropped == 0 and -0.5 <= drift < -0.1, "Lautsprecher schneller: langsamer abspielen (%.3f %%)" % drift)

# Umrechnung bleibt fortlaufend: Sinus ohne Spruenge bei leicht veraenderter Rate
rs = Resampler(RATE, RATE)
x = (np.sin(np.arange(RATE) * 2 * np.pi * 440 / RATE) * 10000).astype("<i2")
st2 = np.stack([x, x], axis=1)
out = []
for i in range(0, RATE, 256):
    rs.step = 1.003 if (i // 256) % 2 else 0.997
    out.append(np.frombuffer(convert(st2[i:i + 256].tobytes(), RATE, 2, RATE, 2, rs), dtype="<i2").reshape(-1, 2)[:, 0])
y = np.concatenate(out).astype(float)
check(np.max(np.abs(np.diff(y))) < 700, "Tempo-Anpassung ohne Knackser (groesster Sprung %d)" % np.max(np.abs(np.diff(y))))
finish("test_bt_uhren")
