"""Alle Seiten des Panels gehen im selben Tab auf, nur die Weboberflaechen der Geraete (WLED usw.) im neuen."""
import os, re, sys
from _common import check, finish

HERE = os.path.dirname(os.path.abspath(__file__))
PI = os.path.join(HERE, "..", "pi")
sys.path.insert(0, PI)
import webpanel

texte = {"make_page": webpanel.make_page(), "dmx_page": webpanel.dmx_page(), "help_page": webpanel.help_page()}
SM = os.path.join(PI, "static", "sm")
for n in sorted(os.listdir(SM)):
    if n.endswith((".html", ".js")):
        with open(os.path.join(SM, n), encoding="utf-8") as f:
            texte[n] = f.read()

for name, t in texte.items():
    fremd = [m for m in re.findall(r"<a [^>]*>", t) if ("_blank" in m or "target=" in m) and "S.reach_url" not in m
             and 'target="lb_spotify"' not in m]          # Ausnahme (Wunsch 14.11.2026): Spotify-Suche im eigenen Fenster
    check(not fremd, f"{name}: kein Panel-Link mit neuem Tab {fremd[:2]}")
    rest = t.replace("window.open('', 'lb_autodj')", "").replace("window.open('','lb_autodj')", "")
    check("window.open(" not in rest, f"{name}: kein window.open (Ausnahme: das eigene Auto-DJ-Fenster)")

p = texte["make_page"]
check("S.reach_url[n])+'\" target=\"_blank\"" in p, "Links zu den Geraeten (WLED, OLA) bleiben im neuen Tab")
for href in ("/help", "/dmx", "/dmx-debug"):
    check(f'href="{href}"' in p, f"{href} ist im Panel verlinkt")
check("↗" not in p.split("S.reach_url")[0], "kein Pfeil ↗ mehr, der einen neuen Tab andeutet")

# Ausnahme Auto-DJ (08.11.2026): eigenes Fenster, damit der Ton beim Seitenwechsel weiterlaeuft; laeuft es, nur nach vorne holen
nav = texte["nav.js"]
check("window.open('', 'lb_autodj')" in nav and "a[href=\"/musik/autodj\"]" in nav and "w.focus()" in nav, "Menue: Auto-DJ im eigenen Fenster")
check("w.location.pathname !== '/musik/autodj'" in nav, "laeuft das Fenster schon: nicht neu laden (die Musik spielt weiter)")
check('id="djbtn" href="/musik/autodj" onclick="openAutoDJ(event)"' in p and "window.open('','lb_autodj')" in p, "Panel: CD-Knopf oeffnet das Auto-DJ-Fenster")

finish("test_selber_tab")
