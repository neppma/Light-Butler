"""Startseite auf GitHub (README.md, 16.11.2026): Vorstellung wie die Broschuere mit Bildern aus dem Simulator, Download-Links
auf das neueste Release. Alle Bilder und Links im Projekt muessen da sein, die Bilder klein bleiben."""
import os
import re

from _common import ROOT, check, finish

txt = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
local = set()
for m in re.finditer(r'(?:src|href)="([^"]+)"|\]\(([^)]+)\)', txt):
    p = m.group(1) or m.group(2)
    if not p.startswith(("http", "#", "mailto:")):
        local.add(p)
missing = [p for p in sorted(local) if not os.path.exists(os.path.join(ROOT, p))]
check(local and not missing, "alle Bilder und Links des README vorhanden: " + str(missing))
imgs = [p for p in local if p.startswith("docs/bilder/github/")]
check(len(imgs) >= 10 and all(os.path.getsize(os.path.join(ROOT, p)) < 300_000 for p in imgs), "Bilder fuer GitHub klein (< 300 KB)")
dl = re.findall(r"releases/latest/download/([A-Za-z0-9.-]+)", txt)
check("Light-Butler-Setup.exe" in dl and "Light-Butler-Musik-Setup.exe" in dl and "light-butler-pi.zip" in dl
      and not [d for d in dl if "windows-voll" in d or "windows-musik" in d], "Downloads: Installer statt PowerShell-Pakete")
check("Broschuere.pdf" in txt and "Beispiel-Anlage mit erfundener Musik" in txt, "Broschuere verlinkt, Hinweis auf erfundene Musik")
finish("test_readme")
