"""Knopfzeile: AUTO, STROBE, WOW!, BLINDER, FREEZE, BLACKOUT, SMOKE (Reihenfolge laut Nutzer 01.11.2026; alle ausser AUTO sind Taster). Die Strobe-Erlaubnis steht nicht mehr dort,
sondern in den Einstellungen bei "Weisse Blitze und Strobo" und wird nie von selbst eingeschaltet."""
import re

from _common import build, check, finish

import settings
import webpanel

page = webpanel.make_page()
row = page[page.index('<div class="ctlrow">'):page.index('<div class="blitzrow">')]
ids = re.findall(r'<button class="big[^"]*" id="(b_[a-z]+)"', row)
check(ids == ["b_auto", "b_blitz", "b_build", "b_sun", "b_freeze", "b_black", "b_fog"],
      f"Reihenfolge: AUTO, STROBE, WOW!, BLINDER, FREEZE, BLACKOUT, SMOKE ({ids})")
check("b_strobe" not in row and 'id="b_strobe"' not in page.split("<script>")[0], "Strobe-Erlaubnis nicht mehr in der ersten Zeile")
check('id="blitzhz"' in page[page.index('<div class="blitzrow">'):], "Regler Blitze pro Sekunde bleibt darunter")
for bid, name in (("b_blitz", "blitz"), ("b_fog", "fog"), ("b_black", "blackout"), ("b_sun", "allbright"), ("b_freeze", "freeze")):
    tag = row[row.index(f'id="{bid}"'):]
    tag = tag[:tag.index(">")]
    down = "fogDown(event)" if name == "fog" else f"holdStart('{name}',event)"   # SMOKE: erst Rueckfrage, wenn die Maschine aus ist
    check(f"onpointerdown=\"{down}\"" in tag and f"onpointerup=\"holdStop('{name}')\"" in tag
          and "onclick" not in tag, f"{bid} ist ein Taster (nur solange gedrueckt)")
auto = row[row.index('id="b_auto"'):]
check('''onclick="c({auto:'toggle'})"''' in auto[:auto.index(">")], "AUTO schaltet ein und aus")
check("bl.innerHTML=tr('blitz');" in page and "blitz_on" not in page, "STROBE-Knopf behaelt beim Blitzen seinen Text (keine Breitenaenderung)")
check(".big.on.auto{box-shadow" in page or ".big.on.auto," in page or ",.big.on.auto{" in page,
      "AUTO bekommt im aktiven Zustand den orangen Leuchtrahmen wie die anderen Knoepfe")
check("c({hold_keep:[...HELD]})" in page and "if(document.hidden){[...HELD].forEach(holdStop);wowStop()}" in page,
      "Lebenszeichen alle 0,4 s, Loslassen wenn die Seite verdeckt wird")
order = [page.index(f'data-tx="{k}"') for k in ("h_speed", "h_color", "h_mix", "h_move")]
check(order == sorted(order), "Speed bei den Sofort-Knoepfen, darunter Farbe, Licht-Mix und Bewegung")

check(any(p.group == "Weisse Blitze und Strobo" for p in settings.DEFS), "Gruppe Weisse Blitze und Strobo vorhanden")
check("g.group==='Weisse Blitze und Strobo'" in page and 'id="b_strobe" onclick="toggleStrobe()"' in page,
      "Erlaubnis-Knopf in der Gruppe Weisse Blitze und Strobo")
check("function drawStrobe(){const sb=document.getElementById('b_strobe');if(!sb)return;" in page,
      "Anzeige der Erlaubnis funktioniert auch, solange die Einstellungen nicht geladen sind")

# Sicherheit: die Erlaubnis bleibt aus, bis jemand sie einschaltet
rig, sh = build(strobe=False)
check(sh.snapshot()["strobe"] is False, "ohne --strobe: Erlaubnis aus")
sh.command({"blitz": True, "blitz_hz": 10})
check(sh._blitz_rate() <= 3.0, "ohne Erlaubnis hoechstens 3 Blitze pro Sekunde")
sh.command({"strobe": True})
check(sh.snapshot()["strobe"] is True, "Knopf schaltet die Erlaubnis ein")

finish("test_knopfzeile")
