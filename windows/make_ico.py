"""make_ico.py - Symbole aus dem Light-Butler-Symbol pi/icon.svg (16.11.2026): windows/light-butler.ico (Windows) und
mac/app/light-butler.icns (Mac-App).

Nur am Mac (qlmanage zeichnet das SVG, pillow macht die Ecken durchsichtig, sips verkleinert). Die fertige .ico liegt im Projekt, GitHub baut damit
Light-Butler.exe und die Installer. Nach einer Aenderung an pi/icon.svg neu erzeugen:
    python3 windows/make_ico.py      (ein Python mit pillow)
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, "pi", "icon.svg")
ICO = os.path.join(ROOT, "windows", "light-butler.ico")
ICNS = os.path.join(ROOT, "mac", "app", "light-butler.icns")
SIZES = (16, 24, 32, 48, 64, 128, 256)


def pack_ico(pngs):
    """ICO aus PNG-Bildern {Groesse: Bytes} (PNG im ICO geht ab Windows Vista)."""
    sizes = sorted(pngs)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    dirs, data = b"", b""
    for s in sizes:
        b = pngs[s]
        dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(b), off + len(data))
        data += b
    return head + dirs + data


def clear_corners(png, radius=14 / 64):
    """qlmanage zeichnet auf weissem Grund: alles ausserhalb des abgerundeten Quadrats (wie in icon.svg) durchsichtig."""
    from PIL import Image, ImageDraw
    im = Image.open(png).convert("RGBA")
    w, h = im.size
    mask = Image.new("L", (w * 4, h * 4), 0)                 # vierfach zeichnen, dann verkleinern: glatte Kante
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * 4 - 1, h * 4 - 1), radius=int(radius * w * 4), fill=255)
    im.putalpha(mask.resize((w, h), Image.LANCZOS))
    im.save(png)


def main():
    tmp = tempfile.mkdtemp(prefix="lb-ico-")
    try:
        subprocess.run(["qlmanage", "-t", "-s", "512", "-o", tmp, SVG], check=True, capture_output=True)
        big = os.path.join(tmp, os.path.basename(SVG) + ".png")
        clear_corners(big)
        pngs = {}
        for s in SIZES:
            out = os.path.join(tmp, "%d.png" % s)
            subprocess.run(["sips", "-z", str(s), str(s), big, "--out", out], check=True, capture_output=True)
            with open(out, "rb") as f:
                pngs[s] = f.read()
        with open(ICO, "wb") as f:
            f.write(pack_ico(pngs))
        print("geschrieben:", os.path.relpath(ICO, ROOT), "(%d Bytes)" % os.path.getsize(ICO))
        iconset = os.path.join(tmp, "light-butler.iconset")              # Mac: iconutil aus 16 bis 1024 Pixel
        os.makedirs(iconset)
        big1k = os.path.join(tmp, "big1k")
        os.makedirs(big1k)
        subprocess.run(["qlmanage", "-t", "-s", "1024", "-o", big1k, SVG], check=True, capture_output=True)
        src1k = os.path.join(big1k, os.path.basename(SVG) + ".png")
        clear_corners(src1k)
        for s in (16, 32, 128, 256, 512):
            for f, px in (("icon_%dx%d.png" % (s, s), s), ("icon_%dx%d@2x.png" % (s, s), 2 * s)):
                subprocess.run(["sips", "-z", str(px), str(px), src1k, "--out", os.path.join(iconset, f)],
                               check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", ICNS], check=True, capture_output=True)
        print("geschrieben:", os.path.relpath(ICNS, ROOT), "(%d Bytes)" % os.path.getsize(ICNS))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
