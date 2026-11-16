"""Szene Laser (Pi steuert): die Laser pulsieren im Takt (an kurz nach dem Beat, dann aus) und Speed Low/Med/Hot
wirkt: Low pulst alle 2 Beats, Med jeden Beat, Hot jeden halben Beat (nur mit Strobe-Erlaubnis).
Ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde. Puls-Anteil 100 % = immer an."""
from _common import build, Clock, check, finish


def measure(spd, strobe=True, duty=None, secs=20.0):
    rig, sh = build(strobe=strobe, seed=3)
    clk = Clock(sh)
    sh.cfg.set("laser_mode", 0)
    if duty is not None:
        sh.cfg.set("laser_duty", duty)
    clk.run(5)
    sh.command({"scene": "Laser"})
    if spd:
        sh.command({"speed": spd})
    clk.run(1)
    ktv = next(f for f in sh.lasers if f.type in ("laser_ktv", "laser_ktv34"))
    eyes = next(f for f in sh.lasers if f.type == "eyes_21")
    on, edges, prev, eyes_on, motor = 0, 0, False, 0, []
    n = int(secs / 0.025)
    for _ in range(n):
        clk.run(0.025)
        p = ktv.values["power"] > 0 and sh.state != "idle"
        on += p
        edges += p and not prev
        prev = p
        eyes_on += any(eyes.values[k] for k in ("laser_red1", "laser_red2", "laser_green", "laser_blue"))
        motor.append(eyes.values["motor_speed"])
    return {"on": on / n, "rate": edges / secs, "eyes_on": eyes_on / n, "motor": sum(motor) / len(motor), "bpm": sh.bpm,
            "speed": sh.snapshot()["speed"]}


mid = measure("mid")
check(mid["speed"] == "mid", "Speed-Knopf wirkt in der Szene Laser")
check(0.25 < mid["on"] < 0.55, f"Med: Laser nur gut ein Drittel der Zeit an ({mid['on']:.2f})")
check(0.2 < mid["eyes_on"] < 0.55, f"Med: Eyes-Laser pulsieren mit ({mid['eyes_on']:.2f})")
check(abs(mid["rate"] - min(mid["bpm"] / 60.0, 2.5)) < 0.6, f"Med: ein Puls je Beat ({mid['rate']:.2f}/s bei {mid['bpm']:.0f} BPM)")
slow = measure("slow")
check(abs(slow["rate"] - mid["rate"] / 2) < 0.4, f"Low: halb so viele Pulse ({slow['rate']:.2f}/s)")
check(slow["motor"] < mid["motor"], f"Low: Motoren langsamer ({slow['motor']:.0f} < {mid['motor']:.0f})")
fast = measure("fast")
check(fast["rate"] > 1.6 * mid["rate"], f"Hot mit Strobe-Erlaubnis: doppelt so viele Pulse ({fast['rate']:.2f}/s)")
check(fast["motor"] > mid["motor"], f"Hot: Motoren schneller ({fast['motor']:.0f} > {mid['motor']:.0f})")
nostrobe = measure("fast", strobe=False)
check(nostrobe["rate"] <= 2.05, f"ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde ({nostrobe['rate']:.2f}/s)")
check(nostrobe["on"] > 0.1, "ohne Strobe-Erlaubnis: Laser laufen trotzdem")
full = measure("mid", duty=100)
check(full["on"] > 0.95, f"Puls-Anteil 100 %: immer an ({full['on']:.2f})")
short = measure("mid", duty=20)
check(short["on"] < mid["on"] - 0.1, f"Puls-Anteil 20 %: kuerzer an ({short['on']:.2f})")
auto = measure(None)
check(abs(auto["rate"] - mid["rate"]) < 0.3, "Speed Auto: wie Med")

# Sicherheit bleibt: Laser-Szene verlassen -> sofort aus
rig, sh = build(seed=3)
clk = Clock(sh)
sh.cfg.set("laser_mode", 0)
clk.run(5)
sh.command({"scene": "Laser"})
clk.run(2)
sh.command({"auto": True})
clk.run(0.025)
check(all(fx.values[p] == 0 for fx in sh.lasers for p in fx.tdef.get("locked_channels", ()) if p in fx.values) or not sh.laser_on,
      "Szene verlassen: Laser sofort aus")
finish("test_laser_puls")
