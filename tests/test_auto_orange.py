"""Gewaehlte Knoepfe (Speed, Beam, Bewegung, Licht-Mix, Farbe, Effektband) sind orange umrandet wie AUTO in der
Knopfreihe oben, nicht mehr weiss."""
from _common import check, finish

import webpanel

p = webpanel.make_page()
O = "inset 0 0 0 3px #e8710a,0 0 12px #e8710a"
check(".big.on.bigfx,.big.on.sun,.big.on.auto{box-shadow:" + O + "}" in p, "AUTO oben: orange Umrandung (Vorbild)")
for rule, what in (("#speed button.on{box-shadow:" + O, "Speed"), ("#beam button.on{box-shadow:" + O, "Beam"),
                   ("#mix button.on,#move button.on{box-shadow:" + O, "Bewegung und Licht-Mix"),
                   (".cb.on{box-shadow:" + O, "Farbe"), ("#ebgrid button.on{box-shadow:" + O, "Effektband")):
    check(rule in p, f"{what}: gewaehlt orange umrandet")
check("inset 0 0 0 4px #fff" not in p and "inset 0 0 0 3px #fff" not in p, "keine weissen Umrandungen mehr")
check('#b_auto,#beam button{background:linear-gradient(90deg,#1c7a3a,#2b8a4a)!important;color:#fff;font-weight:600;' in p,
      "AUTO und Beam: gleicher Verlauf und Schrift")
finish("test_auto_orange")
