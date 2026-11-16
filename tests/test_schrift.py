"""Eine Schrift im ganzen Panel: Inter (SIL OFL), liegt auf dem Pi (pi/static/inter.woff2) und wird von dort geladen,
ohne Internet. Knoepfe uebernehmen sie (sonst nimmt der Browser Arial); ueberall Stärke 600. Fehlt die Datei: Systemschrift."""
import os

from _common import PI, check, finish

import webpanel

f = os.path.join(PI, "static", "inter.woff2")
data = open(f, "rb").read() if os.path.exists(f) else b""
check(data[:4] == b"wOF2" and 30000 < len(data) < 200000, f"Schriftdatei vorhanden ({len(data)} Bytes, WOFF2)")
check(webpanel.FONT_FILE == f, "Panel liest genau diese Datei")
check(os.path.exists(os.path.join(PI, "static", "INTER_LIZENZ.txt")), "Lizenzhinweis liegt dabei")
p = webpanel.make_page()
check('@font-face{font-family:Inter;src:url(/static/inter.woff2) format("woff2")' in p, "Schrift vom Pi eingebunden (kein Internet)")
check("font-family:Inter,-apple-system" in p, "ganzes Panel in Inter, sonst Systemschrift")
check("button,input,select,textarea{font-family:inherit}" in p, "Knoepfe und Felder uebernehmen die Schrift")
check("font-size:14px;font-weight:600;min-height:50px}" in p and "font-size:13px;line-height:1.2;font-weight:600;" in p,
      "Knoepfe 14 px halbfett, obere Reihe 13 px halbfett")
check("http://" not in p.split("<style>")[1].split("</style>")[0] and "https://" not in p.split("<style>")[1].split("</style>")[0],
      "keine Schrift aus dem Internet")
src = open(os.path.join(PI, "webpanel.py"), encoding="utf-8").read()
check('elif self.path == "/static/inter.woff2":' in src and '"font/woff2"' in src, "Pi liefert die Schrift unter /static/inter.woff2")
finish("test_schrift")
