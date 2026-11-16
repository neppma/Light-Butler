"""Seite /software (Wunsch 15.11.2026): Systemschema mit Download-Symbolen, Link in den Einstellungen, Texte DE/EN."""
import os
import re
import subprocess
import sys

from _common import PI, check, finish

import texts
import webpanel

SM = os.path.join(PI, "static", "sm")
html = open(os.path.join(SM, "software.html"), encoding="utf-8").read()
js = open(os.path.join(SM, "software.js"), encoding="utf-8").read()
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()

check('class="s2lnav" data-back="/settings" data-cur="settings" data-title="h_software"' in html, "Kopfleiste, zurueck zu den Einstellungen")
check('<script src="/static/sm/nav.js"></script>' in html, "laedt nav.js")
check('path == "/software"' in api and '_static(h, "software.html")' in api, "Route /software")
check('path == "/api/sm/pakete"' in api and "exe_zip_path() is not None" in api, "Route /api/sm/pakete meldet die vorhandenen Pakete")

# Symbole: Light-Butler Pi/Windows/Mac (Mac noch blass), Helfer und Bruecke je Mac/Windows
keys = re.findall(r'class="ico( off)?" data-k="([\w-]+)"', html)
check([k for _, k in keys] == ["helfer-mac", "helfer-win", "bruecke-mac", "bruecke-win", "lb-pi", "lb-win", "lb-mac", "stems-mac", "stems-win"], "neun Download-Symbole")
check(not [k for o, k in keys if o.strip()], "kein Symbol fest blass (blass nur, wenn das Paket am Pi fehlt)")
check("['lb-mac', 'macvoll']" in js, "Mac als Light-Butler: blass, solange das Paket am Pi fehlt")
for k in [k for _, k in keys] + ["lb", "helfer", "bruecke", "ton", "mixxx", "artnet", "usb", "wled", "nano", "hm", "pult", "browser", "midi", "musik", "stems"]:
    check("'%s': [" % k in js, f"Eintrag fuer {k}")
for p in ("light-butler-pi.zip", "light-butler-pi-ersatz.zip", "light-butler-windows-exe.zip", "light-butler-windows-voll.zip",
          "light-butler-mac.zip", "light-butler-windows.zip", "light-butler-mac-voll.zip"):
    check(p in js and ('"/download/%s"' % p in api or p in api), f"Download {p} gibt es am Pi")
check('data-k="stems"' in html and "'stems-win'" in js and "light-butler-windows.zip" in js.split("'stems-win'")[1].split("]]]")[0], "Pegelkurven-Rechner mit Mac- und Windows-Download")
check('data-k="musik"' in html and "USB-Stick, NAS" in html, "Musiksammlung (Stick, NAS) im Schema")
check("'winmusik'" in js and "'exe'" in js and "AV[d[3]]" in js, "Pakete, die es noch nicht gibt, ohne Knopf (blass)")
check("['helfer-win', 'winmusik'], ['bruecke-win', 'winmusik']" in js and "!AV[a]" in js, "Windows-Symbole bei Helfer und Bruecke blass ohne eigenes Paket")

# Einstellungen: Link oben in Software fuer andere Rechner, Texte zweisprachig, Kopfleiste kennt den Titel
page = webpanel.make_page()
check('<a class="seclink" href="/software"><span data-tx="h_software">' in page, "Link in den Einstellungen")
check(page.index('href="/software"') < page.index('href="/download/light-butler-mac.zip"'), "Link steht vor den einzelnen Paketen")
src = open(os.path.join(PI, "texts.py"), encoding="utf-8").read()
check('"h_software": ("Systemschema und Downloads", "System diagram and downloads")' in src and '"sw_hint": (' in src, "Texte DE/EN")
check("h_software" in webpanel.NAV_KEYS, "Kopfleiste bekommt den Titel")
check(all(t.count("data-en=") > 0 for t in (html,)) and "d.lang === 'en'" in js, "Seite folgt der Sprache des Panels")

r = subprocess.run(["node", "--check", os.path.join(SM, "software.js")], capture_output=True, text=True)
check(r.returncode == 0, "software.js: node --check " + r.stderr[:200])
# Bild im Handbuch (15.11.2026): systemschema.svg/_en.svg aus dem Schema der Seite, docs/bilder/systemschema_svg.py
sys.path.insert(0, os.path.join(os.path.dirname(PI), "docs", "bilder"))
import systemschema_svg as _ss
for _l, _n in (("de", "systemschema.svg"), ("en", "systemschema_en.svg")):
    _f = os.path.join(SM, _n)
    check(os.path.exists(_f) and open(_f, encoding="utf-8").read() == _ss.build(_l), f"{_n} passt zum Schema (sonst: python3 docs/bilder/systemschema_svg.py)")
_en = _ss.build("en")
check("Music computer" in _en and "Musik-Rechner" not in _en and "data-" not in _en and "var(--" not in _en, "englisches Bild ohne deutsche Texte, ohne Klick-Kennungen und Panel-Farben")
check("(/static/sm/systemschema.svg)" in open(os.path.join(os.path.dirname(PI), "docs", "HANDBUCH.md"), encoding="utf-8").read()
      and "(/static/sm/systemschema_en.svg)" in open(os.path.join(os.path.dirname(PI), "docs", "MANUAL_EN.md"), encoding="utf-8").read(), "Schema in beiden Handbuechern")

finish("test_systemschema")
