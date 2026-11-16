"""Systemschema fuer das Handbuch (15.11.2026): nimmt das Bild der Seite /software (pi/static/sm/software.html) und
schreibt es als eigenstaendige Bilder pi/static/sm/systemschema.svg (deutsch) und systemschema_en.svg (englisch).
Farben fest fuer die dunkle Hilfe-Seite, ohne Klicks. Aufruf nach jeder Aenderung am Schema:
    python3 docs/bilder/systemschema_svg.py
tests/test_systemschema.py prueft, dass die Bilder zum Schema passen."""
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "pi", "static", "sm", "software.html")
OUT = {"de": os.path.join(ROOT, "pi", "static", "sm", "systemschema.svg"),
       "en": os.path.join(ROOT, "pi", "static", "sm", "systemschema_en.svg")}
TITLE = {"de": "Systemschema Light-Butler", "en": "Light-Butler system diagram"}
STYLE = """<style>
text { fill: #e8eaf2; font: 600 14px Inter, -apple-system, "Segoe UI", Roboto, sans-serif; }
text.s { fill: #8a90a8; font-weight: 400; font-size: 12px; }
.bx { fill: #1f2230; stroke: #2c2f42; }
.lb { fill: #26214a; stroke: #7f77dd; }
.sw { fill: #0f2e28; stroke: #1d9e75; }
.mu { fill: #33260c; stroke: #ba7517; }
.grp { fill: none; stroke: #4a4f70; stroke-dasharray: 4 4; }
.ar { stroke: #8a90a8; stroke-width: 1.3; fill: none; }
.fig { stroke: #8a90a8; stroke-width: 1.6; fill: none; stroke-linecap: round; }
.ico { fill: #e8eaf2; }
</style>"""


def build(lang, src=None):
    page = src if src is not None else open(SRC, encoding="utf-8").read()
    svg = re.search(r"<svg id=\"schema\".*?</svg>", page, re.S).group(0)
    if lang == "en":                                   # Texte mit data-en tauschen
        svg = re.sub(r'(<text[^>]*?) data-en="([^"]*)"([^>]*)>[^<]*</text>',
                     lambda m: m.group(1) + m.group(3) + ">" + m.group(2) + "</text>", svg)
    svg = re.sub(r' data-en="[^"]*"', "", svg)
    svg = re.sub(r' (?:data-k|tabindex|role|aria-label|aria-labelledby)="[^"]*"', "", svg)
    svg = re.sub(r'<rect class="hit"[^>]*/>', "", svg)
    svg = re.sub(r'<title id="sct">[^<]*</title>', "<title>" + html.escape(TITLE[lang]) + "</title>", svg)
    svg = svg.replace('<svg id="schema" ', '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="680" height="690" ', 1)
    svg = svg.replace("<defs>", STYLE + '<rect x="0" y="0" width="680" height="690" fill="#0f1017"/><defs>', 1)
    svg = re.sub(r'<use href="#', '<use xlink:href="#', svg)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n"


def main():
    for lang, path in OUT.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(build(lang))
        print("geschrieben:", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
