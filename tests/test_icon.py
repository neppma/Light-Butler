"""Light-Butler: Name im Browser-Tab, Icon fuer Tab und Home-Bildschirm, der Server liefert die Dateien aus."""
from _common import check, finish

import webpanel

page = webpanel.make_page()
check("<title>Light-Butler</title>" in page, "Tab-Titel Light-Butler")
check('rel="icon" type="image/svg+xml" href="/icon.svg"' in page and 'rel="apple-touch-icon" href="/apple-touch-icon.png"' in page,
      "Panel verlinkt Tab- und Home-Bildschirm-Icon")
check('name="apple-mobile-web-app-title" content="Light-Butler"' in page, "Name auf dem Home-Bildschirm")
svg = webpanel.icon_file("/icon.svg")
png = webpanel.icon_file("/apple-touch-icon.png")
check(svg is not None and svg[1] == "image/svg+xml" and b"<svg" in svg[0], "icon.svg vorhanden")
check(png is not None and png[1] == "image/png" and png[0][:8] == b"\x89PNG\r\n\x1a\n", "apple-touch-icon.png vorhanden")
check(webpanel.icon_file("/favicon.ico") is not None, "favicon.ico liefert das Icon")
check(webpanel.icon_file("/../settings.json") is None and webpanel.icon_file("/nanoleaf.json") is None,
      "nur die Icon-Dateien, keine anderen Dateien")
for lang in ("de", "en"):
    h = webpanel.help_page(lang)
    check("<title>Light-Butler - " in h and 'href="/icon.svg"' in h, f"Handbuch-Seite ({lang}): Titel und Icon")
finish("test_icon")
