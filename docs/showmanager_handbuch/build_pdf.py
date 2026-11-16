#!/usr/bin/env python3
"""
build_pdf.py - baut die Bedienungsanleitung des Showmanagers als PDF.

Ergebnis: pi/static/Showmanager-Handbuch.pdf (der runde Knopf im Showmanager laedt sie, Route /shows/handbuch.pdf).
Der Text steht in inhalt.py, die Bilder in bilder/ (Bildschirmfotos aus dem Simulator mit einem Beispiel-Lied).

Nur am Mac noetig, nicht auf dem Pi:  pip install reportlab pillow
Aufruf:  python3 docs/showmanager_handbuch/build_pdf.py

Die Schriften kommen von macOS (Arial). Zeichen, die sie nicht kennen, brechen den Bau ab, statt im PDF als
schwarzes Kaestchen zu landen.
"""
import io
import os
import re
import sys

from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
                                PageBreakIfNotEmpty,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

HIER = os.path.dirname(os.path.abspath(__file__))
BILDER = os.path.join(HIER, "bilder")
AUTOR = "Markus Nepp"
KI_HINWEIS = "Diese Anleitung wurde mit Unterstützung von KI (Claude von Anthropic) erstellt."
ZIEL = os.path.normpath(os.path.join(HIER, "..", "..", "pi", "static", "Showmanager-Handbuch.pdf"))

FONTS = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Text", FONTS + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("Text-B", FONTS + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("Text-I", FONTS + "Arial Italic.ttf"))
pdfmetrics.registerFontFamily("Text", normal="Text", bold="Text-B", italic="Text-I", boldItalic="Text-B")

ORANGE = colors.HexColor("#df7a2c")
DUNKEL = colors.HexColor("#14161f")
TINTE = colors.HexColor("#22242e")
GRAU = colors.HexColor("#5d6170")
LINIE = colors.HexColor("#d9dbe3")
HELL = colors.HexColor("#f4f5f8")
ROT = colors.HexColor("#b3261e")
ROT_H = colors.HexColor("#fbeceb")
BLAU = colors.HexColor("#2c6cc4")
BLAU_H = colors.HexColor("#ebf2fb")
OR_H = colors.HexColor("#fdf1e6")

S = {
    "p": ParagraphStyle("p", fontName="Text", fontSize=10.2, leading=14.4, textColor=TINTE, spaceAfter=6),
    "li": ParagraphStyle("li", fontName="Text", fontSize=10.2, leading=14.2, textColor=TINTE),
    "h1": ParagraphStyle("h1", fontName="Text-B", fontSize=21, leading=26, textColor=DUNKEL, spaceAfter=12),
    "h2": ParagraphStyle("h2", fontName="Text-B", fontSize=13.5, leading=17, textColor=DUNKEL, spaceBefore=12, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName="Text-B", fontSize=10.8, leading=14, textColor=ORANGE, spaceBefore=7, spaceAfter=3),
    "cap": ParagraphStyle("cap", fontName="Text-I", fontSize=8.6, leading=11, textColor=GRAU, spaceBefore=3, spaceAfter=9),
    "td": ParagraphStyle("td", fontName="Text", fontSize=9.1, leading=12, textColor=TINTE),
    "th": ParagraphStyle("th", fontName="Text-B", fontSize=9.1, leading=12, textColor=colors.white),
    "box": ParagraphStyle("box", fontName="Text", fontSize=9.6, leading=13.2, textColor=TINTE),
    "toc1": ParagraphStyle("toc1", fontName="Text-B", fontSize=10, leading=13, spaceBefore=4.5, textColor=DUNKEL),
    "toc2": ParagraphStyle("toc2", fontName="Text", fontSize=9, leading=11.6, leftIndent=16, textColor=TINTE),
    "badge": ParagraphStyle("badge", fontName="Text-B", fontSize=8.4, leading=10, textColor=colors.white, alignment=TA_CENTER),
}
BREITE = A4[0] - 4.4 * cm


def _pruefe(text):
    """Kein Zeichen ohne Glyphe ins PDF lassen (alle drei Schnitte)."""
    rein = re.sub(r"<[^>]+>", "", text).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    for name in ("Text", "Text-B", "Text-I"):
        face = pdfmetrics.getFont(name).face
        for ch in rein:
            if ord(ch) > 32 and ord(ch) not in face.charToGlyph:
                sys.exit("Zeichen %r (U+%04X) fehlt in %s: %s" % (ch, ord(ch), name, rein[:70]))
    return text


def _code(text):
    """`so` wird zu Schreibmaschinenschrift."""
    return re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', text)


class Buch:
    """Sammelt den Inhalt. inhalt.py ruft nur diese Methoden auf."""

    def __init__(self):
        self.story = []
        self.kap = 0
        self.ab = 0
        self.bild_nr = 0

    def kapitel(self, titel):
        self.kap += 1
        self.ab = 0
        while self.story and isinstance(self.story[-1], Spacer):
            self.story.pop()                                     # ein Abstand am Seitenende wuerde sonst eine leere Seite fuellen
        self.story.append(PageBreakIfNotEmpty())               # endet das Kapitel davor genau am Seitenende: keine leere Seite
        h = Paragraph(_pruefe("%d&nbsp;&nbsp;%s" % (self.kap, titel)), S["h1"])
        h._toc = (0, "%d  %s" % (self.kap, titel))
        self.story.append(h)

    def abschnitt(self, titel):
        self.ab += 1
        nr = "%d.%d" % (self.kap, self.ab)
        h = Paragraph(_pruefe("%s&nbsp;&nbsp;%s" % (nr, titel)), S["h2"])
        h._toc = (1, "%s  %s" % (nr, titel))
        self.story.append(CondPageBreak(3.2 * cm))
        self.story.append(h)

    def thema(self, titel):
        self.story.append(CondPageBreak(2.2 * cm))
        self.story.append(Paragraph(_pruefe(titel), S["h3"]))

    def text(self, t):
        self.story.append(Paragraph(_pruefe(_code(t)), S["p"]))

    def _liste(self, marken, punkte, breite_marke):
        zeilen = [[m, Paragraph(_pruefe(_code(p)), S["li"])] for m, p in zip(marken, punkte)]
        t = Table(zeilen, colWidths=[breite_marke, BREITE - breite_marke])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        self.story.append(t)
        self.story.append(Spacer(1, 5))

    def punkte(self, punkte):
        m = ParagraphStyle("m", parent=S["li"], textColor=ORANGE, fontName="Text-B")
        self._liste([Paragraph("•", m) for _ in punkte], punkte, 0.45 * cm)

    def schritte(self, punkte):
        marken = []
        for i in range(len(punkte)):
            z = Table([[Paragraph(str(i + 1), S["badge"])]], colWidths=[0.48 * cm], rowHeights=[0.48 * cm])
            z.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ORANGE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                                   ("ROUNDEDCORNERS", [3, 3, 3, 3])]))
            marken.append(z)
        self._liste(marken, punkte, 0.72 * cm)

    def tabelle(self, kopf, zeilen, breiten):
        """breiten: Anteile, die Summe wird auf die Satzbreite gebracht."""
        s = sum(breiten)
        cw = [BREITE * b / s for b in breiten]
        daten = [[Paragraph(_pruefe(k), S["th"]) for k in kopf]]
        daten += [[Paragraph(_pruefe(_code(z)), S["td"]) for z in zeile] for zeile in zeilen]
        t = Table(daten, colWidths=cw, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), DUNKEL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HELL]),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINIE), ("LEFTPADDING", (0, 0), (-1, -1), 5),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        self.story.append(t)
        self.story.append(Spacer(1, 9))

    def _kasten(self, titel, t, farbe, grund):
        p = Paragraph('<font name="Text-B" color="%s">%s</font>&nbsp;&nbsp;%s' % (farbe.hexval().replace("0x", "#"), _pruefe(titel), _pruefe(_code(t))), S["box"])
        k = Table([[p]], colWidths=[BREITE])
        k.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), grund), ("LINEBEFORE", (0, 0), (0, -1), 3, farbe),
                               ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        self.story.append(Spacer(1, 2))
        self.story.append(k)
        self.story.append(Spacer(1, 9))

    def tipp(self, t):
        self._kasten("Tipp", t, BLAU, BLAU_H)

    def hinweis(self, t):
        self._kasten("Hinweis", t, ORANGE, OR_H)

    def warnung(self, t):
        self._kasten("Achtung", t, ROT, ROT_H)

    def _kopf_mitnehmen(self):
        """Steht direkt davor eine Ueberschrift, wandert sie mit dem Bild auf die naechste Seite."""
        if self.story and hasattr(self.story[-1], "_toc"):
            kopf = self.story.pop()
            if self.story and isinstance(self.story[-1], CondPageBreak):
                self.story.pop()
            return [kopf]
        return []

    def bild(self, name, titel, crop=None, breite=1.0, marken=None, streifen=None):
        """Bild mit Unterschrift. crop in Pixeln des Originals, breite als Anteil der Satzbreite, marken: Nummern.
        streifen: Zeilen des Bildes (y0, y1); jede bekommt ein Band fuer die Nummern, y der Marke ist dann die Zeile."""
        self.bild_nr += 1
        im = _bild(name, crop, marken, streifen)
        w = BREITE * breite
        h = w * im.size[1] / im.size[0]
        puffer = io.BytesIO()
        im.convert("RGB").save(puffer, "JPEG", quality=88, optimize=True)
        puffer.seek(0)
        fl = Image(puffer, width=w, height=h)
        fl.hAlign = "CENTER"
        rahmen = Table([[fl]], colWidths=[w + 2])
        rahmen.hAlign = "CENTER"
        rahmen.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINIE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        cap = Paragraph(_pruefe("Bild %d: %s" % (self.bild_nr, titel)), S["cap"])
        self.story.append(KeepTogether(self._kopf_mitnehmen() + [Spacer(1, 3), rahmen, cap]))

    def bilder_reihe(self, teile, titel):
        """Mehrere schmale Bilder nebeneinander. teile: [(name, crop, Beschriftung), ...]"""
        self.bild_nr += 1
        n = len(teile)
        w = (BREITE - (n - 1) * 0.25 * cm) / n
        zeile, kopf = [], []
        for name, crop, text in teile:
            im = _bild(name, crop, None)
            puffer = io.BytesIO()
            im.convert("RGB").save(puffer, "JPEG", quality=88, optimize=True)
            puffer.seek(0)
            zeile.append(Image(puffer, width=w, height=w * im.size[1] / im.size[0]))
            kopf.append(Paragraph(_pruefe(text), S["td"]))
        t = Table([kopf, zeile], colWidths=[w + 0.25 * cm] * n)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        cap = Paragraph(_pruefe("Bild %d: %s" % (self.bild_nr, titel)), S["cap"])
        self.story.append(KeepTogether(self._kopf_mitnehmen() + [t, cap]))


def _bild(name, crop, marken, streifen=None):
    pfad = os.path.join(BILDER, name)
    im = PILImage.open(pfad).convert("RGB")
    if crop:
        im = im.crop(crop)
    if streifen:
        return _leiste(im, marken, streifen)
    # Fotos sind 800 px breit: fuer den Druck weich verdoppeln, damit die Nummern scharf bleiben
    im = im.resize((im.width * 2, im.height * 2), PILImage.LANCZOS)
    if marken:
        d = ImageDraw.Draw(im)
        schrift = ImageFont.truetype(FONTS + "Arial Bold.ttf", 21)
        ox, oy = (crop[0], crop[1]) if crop else (0, 0)
        for text, x, y in marken:
            cx, cy = (x - ox) * 2, (y - oy) * 2
            r = 16 if len(str(text)) < 2 else 18
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(223, 40, 60), outline=(255, 255, 255), width=2)
            d.text((cx, cy), str(text), font=schrift, fill="white", anchor="mm")
    return im


def _leiste(im, marken, streifen):
    """Zerlegt eine Leiste in Zeilen und setzt die Nummern in ein Band ueber jede Zeile, damit sie nichts verdecken."""
    band, faktor = 24, 3
    h = sum(y1 - y0 + band for y0, y1 in streifen)
    neu = PILImage.new("RGB", (im.width, h), (20, 22, 31))
    y, lage = 0, []
    for y0, y1 in streifen:
        neu.paste(im.crop((0, y0, im.width, y1)), (0, y + band))
        lage.append(y + band // 2)
        y += y1 - y0 + band
    neu = neu.resize((neu.width * faktor, neu.height * faktor), PILImage.LANCZOS)
    d = ImageDraw.Draw(neu)
    schrift = ImageFont.truetype(FONTS + "Arial Bold.ttf", 25)
    for text, x, zeile in marken:
        cx, cy = x * faktor, lage[zeile] * faktor
        d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(223, 40, 60), outline=(255, 255, 255), width=2)
        d.text((cx, cy), str(text), font=schrift, fill="white", anchor="mm")
    return neu


class Handbuch(BaseDocTemplate):
    def __init__(self, ziel):
        super().__init__(ziel, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2.3 * cm,
                         bottomMargin=2.1 * cm, title="Showmanager – Bedienungsanleitung", author=AUTOR,
                         subject="Light-Butler: Lichtshows zu einer MP3 programmieren und abspielen")
        rahmen = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f", leftPadding=0, rightPadding=0,
                       topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="titel", frames=[rahmen], onPage=_titelseite),
                               PageTemplate(id="seite", frames=[rahmen], onPage=_kopf_fuss)])

    def beforeDocument(self):
        self._lz = 0     # je Durchlauf von multiBuild neu, sonst aendern sich die Marken und das Inhaltsverzeichnis wird nie fertig

    def afterFlowable(self, fl):
        toc = getattr(fl, "_toc", None)
        if not toc:
            return
        stufe, text = toc
        self._lz += 1
        key = "h%d" % self._lz
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=stufe, closed=stufe == 0)
        self.notify("TOCEntry", (stufe, text, self.page, key))


def _titelseite(c, doc):
    W, H = A4
    c.saveState()
    c.setFillColor(DUNKEL)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(2.2 * cm, H - 7.05 * cm, 1.6 * cm, 0.14 * cm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Text-B", 38)
    c.drawString(2.2 * cm, H - 6.4 * cm, "Showmanager")
    c.setFont("Text", 17)
    c.drawString(2.2 * cm, H - 8.1 * cm, "Bedienungsanleitung")
    c.setFillColor(colors.HexColor("#a8acba"))
    c.setFont("Text", 11)
    c.drawString(2.2 * cm, H - 8.9 * cm, "Lichtshows zu einer MP3 programmieren und abspielen")
    bild = ImageReader(os.path.join(BILDER, "editor.jpg"))
    iw, ih = bild.getSize()
    w = W - 4.4 * cm
    h = w * ih / iw
    y = H - 10.2 * cm - h
    c.drawImage(bild, 2.2 * cm, y, w, h)
    c.setStrokeColor(colors.HexColor("#3a3d4c"))
    c.setLineWidth(0.8)
    c.rect(2.2 * cm, y, w, h, stroke=1, fill=0)
    c.setFillColor(colors.white)
    c.setFont("Text-B", 13)
    c.drawString(2.2 * cm, 4.1 * cm, AUTOR)
    c.setFillColor(colors.HexColor("#a8acba"))
    c.setFont("Text", 10)
    c.drawString(2.2 * cm, 3.4 * cm, "Light-Butler")
    c.drawRightString(W - 2.2 * cm, 3.4 * cm, "Stand: November 2026")
    c.setStrokeColor(colors.HexColor("#3a3d4c"))
    c.line(2.2 * cm, 2.75 * cm, W - 2.2 * cm, 2.75 * cm)
    c.setFont("Text-I", 8.8)
    c.drawString(2.2 * cm, 2.2 * cm, _pruefe(KI_HINWEIS))
    c.restoreState()


def _kopf_fuss(c, doc):
    W, H = A4
    c.saveState()
    c.setFont("Text", 8.4)
    c.setFillColor(GRAU)
    c.drawString(2.2 * cm, H - 1.45 * cm, "Showmanager – Bedienungsanleitung")
    c.setStrokeColor(LINIE)
    c.setLineWidth(0.5)
    c.line(2.2 * cm, H - 1.6 * cm, W - 2.2 * cm, H - 1.6 * cm)
    c.line(2.2 * cm, 1.55 * cm, W - 2.2 * cm, 1.55 * cm)
    c.drawString(2.2 * cm, 1.15 * cm, AUTOR + " · Light-Butler")
    c.setFont("Text-B", 9)
    c.setFillColor(TINTE)
    c.drawRightString(W - 2.2 * cm, 1.15 * cm, str(doc.page))
    c.restoreState()


def baue():
    sys.path.insert(0, HIER)
    import inhalt
    b = Buch()
    inhalt.schreibe(b)

    toc = TableOfContents()
    toc.levelStyles = [S["toc1"], S["toc2"]]
    toc.dotsMinLevel = 0
    toc.tableStyle = TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")])
    vorn = [NextPageTemplate("seite"), PageBreak(), Paragraph("Inhalt", S["h1"]), toc]

    os.makedirs(os.path.dirname(ZIEL), exist_ok=True)
    doc = Handbuch(ZIEL)
    doc.multiBuild(vorn + b.story)
    print("%s: %d Seiten, %.1f MB" % (ZIEL, doc.page, os.path.getsize(ZIEL) / 1e6))


if __name__ == "__main__":
    baue()
