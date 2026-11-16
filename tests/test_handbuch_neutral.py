"""Allgemeines Handbuch ohne Angaben der eigenen Anlage; eigene Seite "Meine Anlage" nur am eigenen Licht-Rechner (15.11.2026)."""
import io
import os
import re
import zipfile

from _common import PI, check, finish

import pakete
import webpanel

ROOT = os.path.dirname(PI)
for name in ("HANDBUCH.md", "MANUAL_EN.md", "TECHNIK.md", "TECHNICAL_EN.md"):
    t = open(os.path.join(ROOT, "docs", name), encoding="utf-8").read()
    bad = [w for w in ("fritz" ".box", "192.168.", "OLA-Pi 192", "MN" "EPP", "/Users/" "markus", "Couchtisch", "Hercules", "MacBook", "QEQ", "RAUM.md")
           if w in t]
    check(not bad, f"{name}: nichts Anlagenspezifisches ({bad})")
    check(t.count("Markus Nepp") <= 3, f"{name}: Name nur als Autor und Copyright")
if os.path.isfile(os.path.join(ROOT, "docs", "MEINE_ANLAGE.md")):     # eigene Fassung (in der Veroeffentlichung fehlt sie)
    check(webpanel.anlage_file() is not None and 'href="/help/anlage"' in webpanel.help_page("de")
          and "Meine Anlage" in webpanel.help_page("de", anlage=True), "Hilfe: Link und Seite Meine Anlage")
else:
    check(webpanel.anlage_file() is None and 'href="/help/anlage"' not in webpanel.help_page("de"), "ohne Meine Anlage: kein Link")
check("MEINE_ANLAGE.md" in pakete.PI_SKIP_FILES, "Meine Anlage nie in Paketen")
for f in ("pi_zip", "windows_zip", "mac_full_zip"):
    names = zipfile.ZipFile(io.BytesIO(getattr(pakete, f)())).namelist()
    check(not [n for n in names if "MEINE_ANLAGE" in n], f"{f}: ohne Meine Anlage")
if os.path.isfile(os.path.join(ROOT, "NICHT_VEROEFFENTLICHEN.txt")):
    nv = open(os.path.join(ROOT, "NICHT_VEROEFFENTLICHEN.txt"), encoding="utf-8").read()
    check(all(x in nv for x in ("docs/archiv/", "docs/MEINE_ANLAGE.md", "docs/RAUM.md")), "Liste: nicht veroeffentlichen")
dep = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
check('rsync -av docs/MEINE_ANLAGE.md "$PI:$DEST/MEINE_ANLAGE.md"' in dep, "deploy.sh kopiert Meine Anlage an den eigenen Pi")
finish("test_handbuch_neutral")
