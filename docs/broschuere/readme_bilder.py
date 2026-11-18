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


FONTS = ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf")


def font(size, bold=False):
    from PIL import ImageFont
    for f in FONTS:
        try:
            return ImageFont.truetype(f, size, index=1 if (bold and f.endswith(".ttc")) else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def vorschau():
    """Vorschaubild fuer GitHub (Settings -> Social preview, 1280 x 640): Symbol, Name, Satz, Handy-Bild. Nur am Mac (Schrift)."""
    from PIL import ImageDraw
    W, H = 1280, 640
    im = Image.new("RGB", (W, H), "#16171f")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 8), fill="#e8770f")
    ico = Image.open(os.path.join(ROOT, "windows", "light-butler.ico"))
    ico = ico.ico.getimage(max(ico.ico.sizes())).convert("RGBA").resize((150, 150), Image.LANCZOS)
    d.rounded_rectangle((72, 82, 238, 248), radius=38, fill="#2c3046")   # Rahmen, sonst verschwindet das dunkle Symbol
    im.paste(ico, (80, 90), ico)
    d.text((80, 270), "Light-Butler", font=font(96, True), fill="#ffffff")
    d.text((84, 385), "Lighting that understands the music.", font=font(40), fill="#c9cde0")
    d.text((84, 450), "Licht, das die Musik versteht.", font=font(30), fill="#8a90a8")
    d.text((84, 545), "DMX · Art-Net · WLED · Nanoleaf · Mixxx", font=font(26), fill="#e8770f")
    d.text((84, 582), "Raspberry Pi · Windows · Mac · free (GPLv3)", font=font(26), fill="#e8770f")
    tel = Image.open(quelle("panel_handy.jpg")).convert("RGB")
    h = 560
    tel = tel.resize((int(tel.width * h / tel.height), h), Image.LANCZOS)
    x, y = W - tel.width - 90, (H - h) // 2 + 4
    d.rounded_rectangle((x - 12, y - 12, x + tel.width + 12, y + h + 12), radius=34, fill="#2c3046")
    mask = Image.new("L", tel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tel.width, h), radius=26, fill=255)
    im.paste(tel, (x, y), mask)
    p = os.path.join(ZIEL, "social-preview.png")
    im.save(p, optimize=True)
    print("social-preview.png  %d x %d  %d KB" % (W, H, os.path.getsize(p) // 1024))


def vorschau_symbol():
    """Vorschaubild nur mit dem Light-Butler-Symbol (1280 x 640): Symbol gross in der Mitte, Name darunter."""
    from PIL import ImageDraw
    W, H = 1280, 640
    im = Image.new("RGB", (W, H), "#0f1017")
    d = ImageDraw.Draw(im)
    ico = Image.open(os.path.join(ROOT, "windows", "light-butler.ico"))
    big = ico.ico.getimage(max(ico.ico.sizes())).convert("RGBA").resize((380, 380), Image.LANCZOS)
    x, y = (W - 380) // 2, 70
    d.rounded_rectangle((x - 10, y - 10, x + 390, y + 390), radius=92, fill="#2c3046")
    im.paste(big, (x, y), big)
    f = font(64, True)
    t = "Light-Butler"
    tw = d.textlength(t, font=f)
    d.text(((W - tw) / 2, 495), t, font=f, fill="#ffffff")
    p = os.path.join(ZIEL, "social-preview-symbol.png")
    im.save(p, optimize=True)
    print("social-preview-symbol.png  %d x %d  %d KB" % (W, H, os.path.getsize(p) // 1024))


def main():
    os.makedirs(ZIEL, exist_ok=True)
    vorschau()
    vorschau_symbol()
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
