"""Bereich Verbindungen: die IP-Adresse ist ein Link zur Konfigurationsseite (OLA :9090, WLED, HomeMatic-CCU), in einem
neuen Tab, aber nur wenn das Geraet erreichbar ist. Nanoleaf hat keine Weboberflaeche und bleibt ohne Link."""
from _common import build, check, finish

import webpanel

u = webpanel.config_url
check(u("Art-Net-Gateway", "192.168.1.45") == "http://192.168.1.45:9090/", "OLA: Weboberflaeche auf Port 9090")
check(all(u(n, "192.168.1.32") == "http://192.168.1.32/" for n in ("Effektband", "Theke", "Couchtisch")), "WLED: Startseite")
check(u("CCU", "192.168.1.20") == "http://192.168.1.20/", "CCU: WebUI")
check(u("Nanoleaf", "192.168.1.33") is None, "Nanoleaf: kein Link")
rig, sh = build()
check(sh.snapshot()["reach_url"] == {}, "Status liefert die Links (leer bis zur ersten Pruefung)")
page = webpanel.make_page()
check("""'<a class="cfgl" href="'+esc(S.reach_url[n])+'" target="_blank" rel="noopener">'""" in page, "Panel: IP als Link, neuer Tab")
check("(S.reach_url||{})[n]&&ok===true?" in page, "Link nur, wenn das Geraet erreichbar ist")
finish("test_verbindungen_links")
