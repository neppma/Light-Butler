"""Knoepfe bleiben an ihrem Platz (Wunsch von Markus, 14.11.2026): In der Musik-Datenbank kam "Geaenderte → Mixxx" erst nach dem
Laden dazu und schob die anderen Knoepfe weiter; der rote Hinweis "Musik-Rechner nicht erreichbar" schob alles nach unten. Man
tippte daneben. Jetzt: spaete Knoepfe hinten und von Anfang an da (ausgegraut), Hinweise unter den Knoepfen bzw. fest am Rand."""
import os
import re

from _common import ROOT, check, finish

SM = os.path.join(ROOT, "pi", "static", "sm")
html = open(os.path.join(SM, "music.html"), encoding="utf-8").read()
js = open(os.path.join(SM, "music.js"), encoding="utf-8").read()
core = open(os.path.join(SM, "core.js"), encoding="utf-8").read()
head = html[html.index('<div id="mhead">'):html.index("</div>", html.index('<div id="mhead">'))]
ids = re.findall(r'id="(b[a-z0-9]+)"', head)
check(ids[-2:] == ["bchg", "bchg0"], "Geaenderte → Mixxx ganz hinten in der Knopfzeile: " + ", ".join(ids))
check(not re.search(r"<(button|a)[^>]*\shidden[\s>]", head), "kein Knopf der Zeile startet versteckt")
check('<button id="bchg" disabled' in html and "$('bchg').disabled = !d" in js and "$('bchg').hidden" not in js and "$('bchg0').hidden" not in js, "ausgrauen statt verstecken")
check(html.index('<div id="mhead">') < html.index('id="syncbox"') and html.index('<div id="mhead">') < html.index('id="hint"'), "Hinweise unter der Knopfzeile")
check("#srcwarn{position:fixed" in core and "insertBefore(el, nav.nextSibling)" not in core, "Hinweis Musik-Rechner fest am unteren Rand, schiebt nichts")
# Seiten-Knoepfe rechtsbuendig neben den Ansichten, Geaenderte → Mixxx und ↺ zusammen (Wunsch 14.11.2026)
gbar = html[html.index('<div id="gbar">'):html.index("</div>", html.index('<div id="gbar">'))]
check(all('id="' + i + '"' in gbar for i in ("bfavs", "bartists", "balbums")) and "bfavs" not in head and "Interpreten-Seite" in gbar and "Alben-Seite" in gbar,
      "Favoriten, Interpreten-Seite, Alben-Seite neben den Ansichten")
check("#pglinks { margin-left: auto; order: 5;" in html and '<span class="keep mx"><button id="bchg"' in html and "#az { order: 10; flex-basis: 100%; }" in html, "rechtsbuendig, ↺ nie allein in einer Zeile, A-Z darunter")
finish("test_knoepfe_fest")
