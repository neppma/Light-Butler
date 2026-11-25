"""Drop hebt nur eine Stufe (drop_step, Wunsch von Markus 23.11.2026): bei einem ruhigen Lied (Marry You, 114 BPM, mittel)
war jeder Refrain ein Drop, danach 20 s Vollgas. Jetzt: Aufbau/Drop eine Stufe ueber der Stufe davor, danach zurueck."""
from _common import build, check, finish


def run(step, pre_tier):
    rig, sh = build()
    sh.cfg.set("drop_step", step)
    sh.cfg.set("energy_bias", 0.3)                 # Musik bleibt energiereich: ohne Sperre ginge es auf Vollgas
    t = 1795430000.0
    for i in range(400):
        sh.update(t + i * 0.025)
    now = t + 400 * 0.025
    sh.tier, sh.tier_t = pre_tier, now - 100
    sh._enter("drop", now)
    during = sh.eff_tier()
    sh._enter("normal", now + 3)
    tiers = []
    f = sh.f
    for i in range(int(25 / 0.025)):
        tt = now + 3 + i * 0.025
        sh.arousal = 0.9                          # Schub nach dem Drop: die Energie bleibt hoch
        sh._update_tier(f, tt, 0.025)
        tiers.append((tt - now, sh.eff_tier()))
    return during, tiers


d, tiers = run(1.0, 2)
check(d == 3, "mittel, Drop: eine Stufe hoeher (schnell)")
check(all(tr <= 2 for t, tr in tiers if t < 19.5), "danach 20 s nicht ueber mittel (Schub hebt nicht)")
check(any(tr == 3 for t, tr in tiers if t > 20.5), "nach 20 s darf die Musik die Stufe wieder heben")
d, tiers = run(1.0, 1)
check(d == 2 and all(tr <= 1 for t, tr in tiers if t < 19.5), "Groove: Drop mittel, danach Groove")
d, tiers = run(1.0, 3)
check(d == 3, "Vollgas bleibt Vollgas")
d, tiers = run(0.0, 2)
check(d == 3 and all(tr == 3 for t, tr in tiers), "aus: Drop und danach Vollgas wie frueher")

rig, sh = build()
sh.tier = 1
sh.state = "build"
check(sh.eff_tier() == 2, "Aufbau: eine Stufe ueber der jetzigen")
sh.cfg.set("drop_step", 0.0)
check(sh.eff_tier() == 3, "aus: Aufbau Vollgas")
finish("test_drop_stufe")
