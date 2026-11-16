"""Farbknoepfe: alle 11 in einer Zeile (schmal, kleine Schrift); am Handy nur Farbflaechen mit Kuerzel A, W, UV."""
from _common import check, finish

import webpanel
from texts import COLORS

p = webpanel.make_page()
check(len(COLORS) == 11 and "#color{grid-template-columns:repeat(11,minmax(0,1fr))" in p, "11 Farben, 11 Spalten in einer Zeile")
check("#color button{min-width:0;padding:10px 2px;font-size:12px" in p, "schmale Knoepfe mit kleiner Schrift")
check("@media(max-width:520px){#color{gap:3px}#color button{font-size:0" in p, "Handy: Namen ausgeblendet, nur Farbflaechen")
check(all(f'#color button[data-v="{v}"]::after{{content:"{t}"}}' in p for v, t in (("auto", "A"), ("white", "W"), ("uv", "UV"))),
      "Kuerzel fuer Auto, Weiss und UV")
finish("test_farben_zeile")
