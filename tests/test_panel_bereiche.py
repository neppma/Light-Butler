"""Hauptseite in grau hinterlegten Bereichen (.pbox): oberste Zeile frei, dann Status, Sofort-Knoepfe mit Speed und Stil,
Farbe mit Licht-Mix, Bewegung mit Ziel und Beam, Szenen, Effektband. Nur Darstellung, jede Kennung bleibt genau einmal da."""
from _common import check, finish

import webpanel

p = webpanel.make_page()
body = p[p.index("<body>"):p.index('<div id="setsec">')]
boxes = body.split('class="pbox')[1:]
check(len(boxes) == 6, f"sechs Bereiche ({len(boxes)})")
check('<div id="spst" class="lk"><div><h2 data-tx="h_speed">' in body and "#spst{display:grid" in p, "Speed und Stil stehen nebeneinander in einer Zeile")

want = [("Status", ['id="row2"', 'id="mxline"', 'id="mxbar"']),
        ("Sofort-Knoepfe mit Speed und Stil", ['id="b_auto"', 'id="b_fog"', 'id="blitzhz"', 'id="master"', 'id="glpop"', 'id="speed"', 'id="style"']),
        ("Farbe und Licht-Mix", ['id="color"', 'id="mix"', 'id="fine_mx"']),
        ("Bewegung, Ziel, Beam", ['id="move"', 'id="fine_mv"', 'id="aim"', 'id="aimset"', 'id="beam"']),
        ("Szenen", ['id="pages"']),
        ("Effektband", ['id="ebgrid"'])]
for box, (name, ids) in zip(boxes, want):
    check(all(i in box for i in ids), f"Bereich {name}: alles drin")

first = body[:body.index('class="pbox')]
check('id="row1"' in first and 'id="evslot"' in first and 'id="hlbtn"' in first, "oberste Zeile steht frei, ohne Bereich")
for i in ('id="move"', 'id="mix"', 'id="speed"', 'id="beam"', 'id="style"', 'id="color"', 'id="aim"', 'id="pages"', 'id="ebgrid"', 'id="master"'):
    check(p.count(i) == 1, f"{i} gibt es genau einmal")
check(body.count("<div") == body.count("</div>"), "alle Bereiche sauber geschlossen")
check(".pbox{background:#1b1d2a;border-radius:12px" in p, "gleiche Flaeche wie auf den Seiten Statistik und Zustand")
check("@media(max-width:480px){body:not([class]){padding:10px 4px}.pbox{padding:10px 6px}" in p, "am Handy gleicht der kleinere Seitenrand den Innenrand aus")
for page in (webpanel.stats_page(), webpanel.health_page(), webpanel.settings_page(), webpanel.fixtures_page()):
    check('<body class="v' in page, "andere Seiten: Bereiche der Hauptseite bleiben ausgeblendet")
finish("test_panel_bereiche")
