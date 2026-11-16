"""make_ico.py - Windows-Symbol windows/light-butler.ico aus dem Light-Butler-Symbol pi/icon.svg (16.11.2026).

Nur am Mac (qlmanage zeichnet das SVG, sips verkleinert). Die fertige .ico liegt im Projekt, GitHub baut damit
Light-Butler.exe und die Installer. Nach einer Aenderung an pi/icon.svg neu erzeugen:
    python3 windows/make_ico.py
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


def main():
    tmp = tempfile.mkdtemp(prefix="lb-ico-")
    try:
        subprocess.run(["qlmanage", "-t", "-s", "512", "-o", tmp, SVG], check=True, capture_output=True)
        big = os.path.join(tmp, os.path.basename(SVG) + ".png")
        pngs = {}
        for s in SIZES:
            out = os.path.join(tmp, "%d.png" % s)
            subprocess.run(["sips", "-z", str(s), str(s), big, "--out", out], check=True, capture_output=True)
            with open(out, "rb") as f:
                pngs[s] = f.read()
        with open(ICO, "wb") as f:
            f.write(pack_ico(pngs))
        print("geschrieben:", os.path.relpath(ICO, ROOT), "(%d Bytes)" % os.path.getsize(ICO))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
