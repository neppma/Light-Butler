"""Helligkeit folgt Lautstaerke: Wird eine Passage leiser als die lauten Teile des Liedes, wird das normale Licht
dunkler (loud_dim, Untergrenze loud_dim_min, volle Wirkung ab loud_dim_db). Mit Mixxx und analysiertem Lied zaehlt die
Lautstaerkekurve der Analyse, ohne Analyse das Audiosignal. Dazu: ein Drop nach einem Break erst, wenn der Pegel bis
auf return_db (jetzt 6 dB) an den Pegel davor herankommt, nicht schon in einer leiseren Passage mit weiterlaufendem Beat."""
from _common import build, check, finish

import settings

rig, sh = build()
c = sh.cfg
check(c["loud_dim"] == 0.5 and c["loud_dim_min"] == 0.40 and c["loud_dim_db"] == 14.0, "Standard: halbe Wirkung, Untergrenze 40 %, ab 14 dB")
check(c["return_db"] == 6.0 and next(p for p in settings.DEFS if p.key == "return_db").default == 6.0, "Rueckkehr-Abstand 6 dB")

f0 = sh.src.poll(1000.0)


def run(f, sec):
    for _ in range(int(sec / 0.025)):
        sh._update_loud(f, 0.025)


# ---- ohne Mixxx: Audiosignal gegen die lauten Teile -----------------------------------------------------------------
sh.state, sh.mx = "normal", None
run(f0._replace(db_short=-10.0, silent=False), 5)
check(abs(sh.loud_ref + 10.0) < 0.01 and abs(sh.loud_k - 1.0) < 1e-6, "laut: volle Helligkeit")
run(f0._replace(db_short=-11.5, silent=False), 5)
check(sh.loud_k > 0.999, "bis 2 dB leiser: nichts")
run(f0._replace(db_short=-22.0, silent=False), 8)
exp = 1.0 - 0.5 * 0.6 * ((sh.loud_ref + 22.0 - 2.0) / 12.0)
check(0.70 <= sh.loud_k <= 0.80 and abs(sh.loud_k - exp) < 0.02, f"12 dB leiser: dunkler ({sh.loud_k:.2f})")
sh.state = "drop"
run(f0._replace(db_short=-22.0, silent=False), 6)
check(sh.loud_k > 0.99, "im Drop voll hell")
sh.state = "normal"
c.set("loud_dim", 1.0)
run(f0._replace(db_short=-40.0, silent=False), 8)
check(abs(sh.loud_k - 0.40) < 0.02, "volle Wirkung: nie dunkler als die Untergrenze")
c.set("loud_dim", 0.5)
sh.state = "idle"
run(f0._replace(db_short=-40.0, silent=True), 1)
check(sh.loud_ref is None, "Stille: Bezug neu (naechstes Lied)")

# ---- mit Mixxx: Kurve der Analyse, ohne Analyse Rueckfall aufs Audiosignal ----------------------------------------
sh.state = "normal"
en = [100] * 50 + [25] * 50
mx = {"plan": True, "deck": 1, "pos": 150.0, "dur": 200.0, "bar": {"ev": [], "en": en, "cu": []}}
sh.mx = dict(mx)
sh.loud_k, sh.loud_ref = 1.0, None
run(f0._replace(db_short=-10.0, silent=False), 8)
check(abs(sh.loud_k - 0.70) < 0.02, f"Mixxx: leise Stelle laut Analyse (Kurve 25) -> 70 % ({sh.loud_k:.2f})")
sh.mx = dict(mx, pos=40.0)
run(f0._replace(db_short=-30.0, silent=False), 8)
check(sh.loud_k > 0.99, "Mixxx: laute Stelle laut Analyse -> voll, auch wenn das Mikrofon leise ist")
sh.mx = dict(mx, plan=False, bar=None)
sh.loud_ref = -10.0
run(f0._replace(db_short=-10.0, silent=False), 8)
check(sh.loud_k > 0.99, "Lied ohne Analyse: Audiosignal (laut = voll)")
run(f0._replace(db_short=-22.0, silent=False), 8)
check(sh.loud_k < 0.85, "Lied ohne Analyse: Audiosignal (leiser = dunkler)")
sh.mx = dict(mx, bar={"ev": [], "en": [], "cu": []})
sh.loud_k = 1.0
run(f0._replace(db_short=-22.0, silent=False), 8)
check(sh.loud_k < 0.85, "alte Analyse ohne Kurve: Audiosignal")

c.set("loud_dim", 0.0)
run(f0._replace(db_short=-40.0, silent=False), 1)
check(sh.loud_k == 1.0, "aus (0): genau 1, Licht wie bisher")
finish("test_lautstaerke_hell")
