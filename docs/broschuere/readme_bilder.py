"""readme_bilder.py - Bilder fuer die Startseite auf GitHub (README.md), aus den Bildern der Broschuere (16.11.2026).

Gleiche Ausschnitte wie in der Broschuere, auf hoechstens 1400 Pixel Breite verkleinert, nach docs/bilder/github/.
Alle Bilder zeigen die Beispiel-Anlage aus dem Simulator mit erfundener Musik (demo_daten.py), nie die echte Sammlung.
Aufruf (braucht pillow, wie build_broschuere.py):
    python3 docs/broschuere/readme_bilder.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
QUELLEN = (os.path.join(HERE, "bilder"), os.path.join(ROOT, "docs", "showmanager_handbuch", "bilder"))
ZIEL = os.path.join(ROOT, "docs", "bilder", "github")
# Name im README: (Quelle, Ausschnitt links/oben/rechts/unten in 0..1 oder None, Breite)
BILDER = {
    "handy.jpg": ("panel_handy.jpg", None, 520),
    "panel.jpg": ("panel.jpg", (0, 0, 1, 0.80), 1400),
    "lied.jpg": ("panel.jpg", (0, 0.05, 1, 0.23), 1400),
    "apc.jpg": ("apc.jpg", None, 1000),
    "editor.jpg": ("editor.jpg", None, 800),
    "assistent.jpg": ("assistent.jpg", None, 800),
    "raum.jpg": ("raum.jpg", (0.11, 0.09, 0.665, 0.67), 1000),
    "musik.jpg": ("musik.jpg", None, 1400),
    "interpreten.jpg": ("interpreten.jpg", None, 1400),
    "favoriten.jpg": ("favoriten.jpg", None, 1400),
    "autodj.jpg": ("autodj.jpg", None, 1400),
    "pflege.jpg": ("pflege.jpg", (0.15, 0, 0.85, 0.85), 1200),
    "dmx.jpg": ("dmx.jpg", None, 1200),
}


def quelle(name):
    for d in QUELLEN:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(name)


def main():
    os.makedirs(ZIEL, exist_ok=True)
    for ziel, (name, crop, breite) in BILDER.items():
        im = Image.open(quelle(name)).convert("RGB")
        if crop:
            w, h = im.size
            im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
        if im.width > breite:
            im = im.resize((breite, int(im.height * breite / im.width)), Image.LANCZOS)
        p = os.path.join(ZIEL, ziel)
        im.save(p, "JPEG", quality=84, optimize=True, progressive=True)
        print("%-16s %4d x %4d  %4d KB" % (ziel, im.width, im.height, os.path.getsize(p) // 1024))


if __name__ == "__main__":
    main()
