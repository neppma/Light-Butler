"""Ambiente-Lichter (Gruppe ambient: Barlicht/PAR, Theke, Couchtisch) blinken nie mit: kein Drop-Effekt, kein Weiss-Blitz,
kein Einzel-Strobe. Beim Strobe (Blitz-Knopf, Strobo-Burst) gehen sie fuer den Kontrast ruhig aus. Sie leuchten nie
dunkler als die Grundhelligkeit amb_idle (auch in Stille und Pausen), ausser bei Blackout, Laser und Wohnzimmerlicht."""
from _common import build, check, finish, Clock

AMB = ("par", "theke", "couchtisch")


def lum(fx):
    return sum(fx.values.get(k, 0) for k in ("r", "g", "b", "w")) * fx.values.get("dimmer", 255) / 255


rig, sh = build(strobe=True)
check([f.name for f in sh.rgb_amb] == list(AMB), "Barlicht gehoert zum Ambiente (wie Theke und Couchtisch)")
check(not set(AMB) & {f.name for f in sh._solo_candidates()}, "kein Einzel-Strobe auf Ambiente-Lichtern")

jumps = {n: 0 for n in AMB}
prev = {}


def look(t):
    for n in AMB:
        v = lum(rig[n])
        if n in prev and abs(v - prev[n]) > 60:
            jumps[n] += 1
        prev[n] = v


Clock(sh).run(150, look)
check(all(j <= 8 for j in jumps.values()), f"150 s mit Drops und Strobe: kaum Spruenge ({jumps}, vorher 80-119)")

rig, sh = build(strobe=False)
jumps = {n: 0 for n in AMB}
prev.clear()
Clock(sh).run(150, look)
check(all(j == 0 for j in jumps.values()), f"ohne Strobe-Erlaubnis: kein einziger Sprung, auch beim Drop ({jumps})")

rig, sh = build(strobe=True)
clk = Clock(sh)
clk.run(30)
sh.command({"blitz": True})
vals = []
clk.run(2, lambda t: vals.append(max(lum(rig[n]) for n in AMB)))
check(max(vals[10:]) == 0, "Blitz-Knopf (Strobe): Ambiente ruhig aus fuer den Kontrast")
sh.command({"blitz": False})

rig, sh = build()
sh.state = "idle"
sh._render_idle(1000.0, 0.025)
lv = [max(rig[n].values.get(k, 0) for k in ("r", "g", "b")) for n in AMB]
check(min(lv) >= int(0.85 * 0.9 * sh.cfg["amb_idle"] * 255) - 1, f"Stille: Ambiente leuchtet in der Grundhelligkeit ({lv})")
check(sh.cfg["amb_idle"] == 0.25, "Grundhelligkeit Standard 25 %")
finish("test_ambiente_ruhig")
