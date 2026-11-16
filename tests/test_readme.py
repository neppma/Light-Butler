"""Startseite auf GitHub (16.11.2026): README.md englisch, README.de.md deutsch, gegenseitig verlinkt; Vorstellung wie die
Broschuere mit Bildern aus dem Simulator, Download-Links auf das neueste Release. Alle Bilder und Links im Projekt muessen
da sein, die Bilder klein bleiben."""
import os
import re

from _common import ROOT, check, finish

for name, other, note in (("README.md", "README.de.md", "sample system with made-up music"),
                          ("README.de.md", "README.md", "Beispiel-Anlage mit erfundener Musik")):
    txt = open(os.path.join(ROOT, name), encoding="utf-8").read()
    local = set()
    for m in re.finditer(r'(?:src|href)="([^"]+)"|\]\(([^)]+)\)', txt):
        p = m.group(1) or m.group(2)
        if not p.startswith(("http", "#", "mailto:")):
            local.add(p)
    missing = [p for p in sorted(local) if not os.path.exists(os.path.join(ROOT, p))]
    check(local and not missing, f"{name}: alle Bilder und Links vorhanden: " + str(missing))
    check(other in local, f"{name}: Link zur anderen Sprache")
    imgs = [p for p in local if p.startswith("docs/bilder/github/")]
    check(len(imgs) >= 10 and all(os.path.getsize(os.path.join(ROOT, p)) < 300_000 for p in imgs), f"{name}: Bilder klein (< 300 KB)")
    dl = re.findall(r"releases/latest/download/([A-Za-z0-9.-]+)", txt)
    check({"Light-Butler-Setup.exe", "Light-Butler-Musik-Setup.exe", "light-butler-pi.zip", "Light-Butler.dmg"} <= set(dl)
          and not [d for d in dl if "windows-voll" in d or "windows-musik" in d], f"{name}: Downloads mit Installern")
    check(note in txt and "lightbutler@gmx.at" in txt, f"{name}: Hinweis auf erfundene Musik, Kontakt")
check("Broschuere.pdf" in open(os.path.join(ROOT, "README.de.md"), encoding="utf-8").read(), "deutsche Seite verlinkt die Broschuere")
prev = os.path.join(ROOT, "docs", "bilder", "github", "social-preview.png")
check(os.path.isfile(prev) and os.path.getsize(prev) < 1_000_000, "Vorschaubild fuer GitHub (< 1 MB)")
finish("test_readme")
