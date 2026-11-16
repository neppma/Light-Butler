"""WLED: Effektband bei Stille ganz dunkel (kein Preset-Wechsel zu den Playlists). Couchtisch und Theke ("on_exit: off")
werden beim Start einmal per JSON eingeschaltet, denn ein ausgeschaltetes WLED, das Art-Net empfaengt, blinkt wild.
Im Trockenlauf (Simulator) wird kein WLED angesprochen, auch nicht beim Beenden."""
import time

from _common import build, Clock, check, finish

import dmx

rig, sh = build()
clk = Clock(sh)
clk.run(5)
eb = rig["effektband"]
check(sh.state != "idle" and eb.values["dimmer"] > 0, f"Musik: Effektband leuchtet ({sh.state}, {eb.values['dimmer']})")
pid = eb.values["preset"]
for k in range(400):                                       # 10 s Stille
    sh.state = "idle"
    sh._render_presets(clk.t + k * 0.025, 0.0, False)
check(eb.values["dimmer"] == 0, "Stille: Effektband dunkel (0 %)")
check(eb.values["preset"] == pid and 26 not in (eb.values["preset"],) and 36 not in (eb.values["preset"],),
      "Stille: kein Wechsel zu den Playlists 26/36, Preset bleibt")
sh.state = "normal"
sh._render_presets(clk.t + 11, 0.0, False)
check(eb.values["dimmer"] > 0, "Musik wieder da: Effektband leuchtet")
sh.state = "break"
sh._render_presets(clk.t + 12, 0.0, False)
check(eb.values["dimmer"] > 0, "Break bleibt wie bisher (gedimmt, nicht aus)")


# ---- WLED einschalten beim Start, ausschalten beim Beenden ----
class Snd:
    def __init__(self):
        self.n = 0

    def send(self, data):
        self.n += 1

    def close(self):
        pass


calls = []
out = dmx.Output(rig, lambda ip: Snd())
out.http = lambda ip, on: calls.append((ip, on))
ts = out.wake_wled(["192.168.1.30", "192.168.1.24", "192.168.1.32"])
time.sleep(0.2)
check(sorted(ts) == ["192.168.1.24", "192.168.1.30"] and sorted(calls) == [("192.168.1.24", True), ("192.168.1.30", True)],
      "Start: Couchtisch und Theke eingeschaltet, Effektband (ohne on_exit) nicht")
calls.clear()
out.set_enabled("192.168.1.30", False, blackout=False)
out.start()
out.stop()
check(calls == [("192.168.1.24", False)], "Beenden: Couchtisch aus, Theke mit abgeschalteter Ausgabe nicht angefasst")

calls.clear()
dry = dmx.Output(rig, lambda ip: dmx.make_sender(rig, ip, dry_run=True))
dry.http = lambda ip, on: calls.append((ip, on))
check(dry.wake_wled(["192.168.1.30", "192.168.1.24"]) == [], "Trockenlauf: beim Start kein WLED angesprochen")
dry.start()
dry.stop()
check(calls == [], "Trockenlauf: beim Beenden kein WLED angesprochen")

# Show: einmal beim ersten Bild, nur wenn die WLED-Ausgabe an ist
rig2, sh2 = build()
calls.clear()
o2 = dmx.Output(rig2, lambda ip: Snd())
o2.http = lambda ip, on: calls.append((ip, on))
sh2.output = o2
sh2.cfg.set("wled_out", 0)
Clock(sh2).run(1)
time.sleep(0.1)
check(calls == [], "WLED-Ausgabe aus: nichts eingeschaltet")
sh2.cfg.set("wled_out", 1)
Clock(sh2).run(3)
time.sleep(0.2)
check(sorted(calls) == [("192.168.1.24", True), ("192.168.1.30", True)], "Show schaltet beim Start einmal ein (nicht jedes Bild)")

finish("test_wled_stille")
