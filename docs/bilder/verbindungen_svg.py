"""Erzeugt das Schema "Geraete, Programme und Verbindungen" fuer das Handbuch (pi/static/sm/verbindungen.svg und _en.svg).
Farben fest fuer die dunkle Hilfe-Seite. Aufruf: python3 docs/bilder/verbindungen_svg.py"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
T = {
    "de": dict(mac="Musik-Rechner", bridge="Mixxx + Brücke", bridge2="App Light-Butler Mixxx", helper="Light-Butler Helfer",
               helper2="MIDI, Ton, ohne Mixxx", serve="Vorhör-Server", serve2="Port 9025, MP3s, Tags", pi="Licht-Rechner",
               show2="Musik hören, Licht", panel="Web-Panel", panel2="Port 8080, alle Seiten", store="Ablage",
               store2="Liedliste, Shows, Kurven", light="Licht", ola="Art-Net-Gerät", ola2="DMX-Geräte", wled2="LED-Streifen", nano2="Panels",
               browser="Browser", browser2="Handy, Tablet, PC", pc="Windows-PC", pc2="Pegelkurven, Grafikkarte",
               legend="Lila = Programme, grün = Lichtgeräte, gestrichelt = MP3s vom Musik-Rechner holen",
               title="Geräte, Programme und Verbindungen"),
    "en": dict(mac="Music computer", bridge="Mixxx + bridge", bridge2="App Light-Butler Mixxx", helper="Light-Butler helper",
               helper2="MIDI, audio, without Mixxx", serve="Preview server", serve2="Port 9025, MP3s, tags", pi="Lighting computer",
               show2="Listens, drives lights", panel="Web panel", panel2="Port 8080, all pages", store="Storage",
               store2="Track list, shows, curves", light="Lights", ola="Art-Net device", ola2="DMX fixtures", wled2="LED strips", nano2="Panels",
               browser="Browser", browser2="Phone, tablet, PC", pc="Windows PC", pc2="Level curves, GPU",
               legend="Purple = programs, green = light devices, dashed = fetch MP3s from the music computer",
               title="Devices, programs and connections"),
}
C = {"cont": ("#1a1d29", "#3a3f58", "#cfd3e6"), "prog": ("#2a2650", "#7f77dd", "#e4e1ff", "#b9b4f0"),
     "dev": ("#123a30", "#1d9e75", "#c9f2e3", "#8fd9bf"), "gray": ("#222536", "#4a4f68", "#e6e8f2", "#a8acba")}


def box(x, y, w, h, kind, a, b=None, rx=8):
    f = C[kind]
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{f[0]}" stroke="{f[1]}" stroke-width="1"/>'
    if b is None:
        return s + f'<text x="{x + w / 2}" y="{y + 24}" text-anchor="middle" font-weight="600" fill="{f[2]}">{a}</text>'
    return (s + f'<text x="{x + w / 2}" y="{y + 23}" text-anchor="middle" font-weight="600" fill="{f[2]}">{a}</text>'
            f'<text x="{x + w / 2}" y="{y + 42}" text-anchor="middle" font-size="12" fill="{f[3]}">{b}</text>')


def svg(t):
    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 450" width="680" font-family="-apple-system,Segoe UI,sans-serif" font-size="14">',
         f'<title>{t["title"]}</title>',
         '<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
         '<path d="M2 1L8 5L2 9" fill="none" stroke="#9fa4bd" stroke-width="1.5"/></marker></defs>',
         '<rect width="680" height="450" rx="12" fill="#14161f"/>']
    o += [box(20, 20, 210, 280, "cont", t["mac"], rx=16), box(35, 64, 180, 56, "prog", t["bridge"], t["bridge2"]),
          box(35, 132, 180, 56, "prog", t["helper"], t["helper2"]), box(35, 200, 180, 56, "prog", t["serve"], t["serve2"]),
          box(250, 20, 200, 280, "cont", t["pi"], rx=16), box(265, 64, 170, 56, "prog", "show.py", t["show2"]),
          box(265, 132, 170, 56, "prog", t["panel"], t["panel2"]), box(265, 200, 170, 56, "prog", t["store"], t["store2"]),
          box(470, 20, 190, 280, "cont", t["light"], rx=16), box(480, 64, 170, 56, "dev", t["ola"], t["ola2"]),
          box(480, 132, 170, 56, "dev", "WLED", t["wled2"]), box(480, 200, 170, 56, "dev", "Nanoleaf", t["nano2"]),
          box(250, 340, 200, 56, "gray", t["browser"], t["browser2"]), box(470, 340, 190, 56, "prog", t["pc"], t["pc2"])]
    ln = 'stroke="#9fa4bd" stroke-width="1.3" fill="none"'
    for x1, y, x2 in ((216, 92, 263), (216, 160, 263), (436, 92, 478), (436, 160, 478), (436, 228, 478)):
        o.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" {ln} marker-end="url(#a)"/>')
    o += [f'<line x1="350" y1="340" x2="350" y2="303" {ln} marker-end="url(#a)"/>',
          f'<path d="M250 368 L125 368 L125 303" {ln} marker-end="url(#a)"/>',
          f'<path d="M565 340 L565 320 L420 320 L420 303" {ln} marker-end="url(#a)" marker-start="url(#a)"/>',
          f'<path d="M500 396 L500 416 L60 416 L60 303" {ln} stroke-dasharray="4 3" marker-end="url(#a)"/>',
          f'<text x="340" y="440" text-anchor="middle" font-size="12" fill="#a8acba">{t["legend"]}</text>', "</svg>"]
    return "\n".join(o) + "\n"


for lang, name in (("de", "verbindungen.svg"), ("en", "verbindungen_en.svg")):
    with open(os.path.join(ROOT, "pi", "static", "sm", name), "w", encoding="utf-8") as f:
        f.write(svg(T[lang]))
    print("geschrieben:", name)
