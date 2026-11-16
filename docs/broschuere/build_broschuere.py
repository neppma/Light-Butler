#!/usr/bin/env python3
"""
build_broschuere.py - Werbebroschuere "Light-Butler" als PDF (Wunsch von Markus, 14.11.2026).

Fuer Freunde und Interessierte: was der Light-Butler kann, kurz und mit Bildern, Technik am Ende. Die Bildschirmfotos
stammen aus dem Simulator mit einer erfundenen Musik-Bibliothek (demo_daten.py, fotos.py), nie aus der echten Sammlung;
die Showmanager-Bilder aus docs/showmanager_handbuch/bilder (erfundenes Beispiel-Lied). Name immer "Light-Butler".

Nur am Mac:  pip install reportlab pillow
Aufruf:      python3 docs/broschuere/build_broschuere.py      ->  pi/static/Light-Butler-Broschuere.pdf
             (deploy.sh bringt sie auf den Pi, der Helfer kopiert sie in Light-Butler-Programme am Musik-Stick)
"""
import io
import os

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas

HIER = os.path.dirname(os.path.abspath(__file__))
BILDER = os.path.join(HIER, "bilder")
SMB = os.path.join(HIER, "..", "showmanager_handbuch", "bilder")
ZIEL = os.path.normpath(os.path.join(HIER, "..", "..", "pi", "static", "Light-Butler-Broschuere.pdf"))   # am Pi: /download/broschuere.pdf, Stick
COPYRIGHT = "© 2026 Markus Nepp – Idee, Konzept und Gestaltung von Markus Nepp, entwickelt mit Unterstützung von KI"   # Wunsch 14.11.2026

FONTS = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Text", FONTS + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("Fett", FONTS + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("Kursiv", FONTS + "Arial Italic.ttf"))
pdfmetrics.registerFont(TTFont("FettKursiv", FONTS + "Arial Bold Italic.ttf"))
registerFontFamily("Text", normal="Text", bold="Fett", italic="Kursiv", boldItalic="FettKursiv")

W, H = A4
M = 1.6 * cm
DUNKEL = colors.HexColor("#171923")
PANEL = colors.HexColor("#22253a")
ORANGE = colors.HexColor("#e8770f")
BLAU = colors.HexColor("#2f8fd4")
GRAU = colors.HexColor("#5b6070")
TXT = colors.HexColor("#1d2030")

S_TEXT = ParagraphStyle("t", fontName="Text", fontSize=11.2, leading=16, textColor=TXT, spaceAfter=6)
S_PUNKT = ParagraphStyle("p", parent=S_TEXT, leftIndent=12, bulletIndent=0, spaceAfter=3)
S_KLEIN = ParagraphStyle("k", parent=S_TEXT, fontSize=9.2, leading=12.5, textColor=GRAU)
S_LISTE = ParagraphStyle("l", parent=S_TEXT, fontSize=9.6, leading=12.6, leftIndent=10, bulletIndent=0, spaceAfter=2.5)
S_GRUPPE = ParagraphStyle("g", parent=S_TEXT, fontName="Fett", fontSize=11.5, leading=14, textColor=ORANGE, spaceAfter=3)
S_HELL = ParagraphStyle("h", parent=S_TEXT, textColor=colors.HexColor("#d6d9e6"), fontSize=12.5, leading=18)


def bild(name, max_w=1800, crop=None):
    """Bild als ImageReader (verkleinert, JPEG: die PDF bleibt klein). crop = (links, oben, rechts, unten) in 0..1."""
    p = os.path.join(BILDER, name) if os.path.isfile(os.path.join(BILDER, name)) else os.path.join(SMB, name)
    im = PILImage.open(p).convert("RGB")
    if crop:
        w, h = im.size
        im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)), PILImage.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=86)
    buf.seek(0)
    return ImageReader(buf), im.size


class Heft:
    def __init__(self):
        self.c = canvas.Canvas(ZIEL, pagesize=A4)
        self.c.setTitle("Light-Butler – Licht, das die Musik versteht")
        self.c.setAuthor("Markus Nepp")
        self.c.setSubject("Broschüre")
        # Anzeige: eine Seite nach der anderen, untereinander (Wunsch 14.11.2026: keine Doppelseiten im Querformat)
        from reportlab.pdfbase.pdfdoc import PDFName
        self.c._doc.Catalog.PageLayout = PDFName("OneColumn")
        self.seite = 0

    def neu(self, titel=None, unter=None):
        if self.seite:
            self.fuss()
            self.c.showPage()
        self.seite += 1
        self.y = H - M
        if titel:
            self.c.setFillColor(ORANGE)
            self.c.rect(M, self.y - 4, 1.2 * cm, 0.16 * cm, stroke=0, fill=1)
            self.y -= 1.0 * cm
            self.c.setFillColor(TXT)
            self.c.setFont("Fett", 24)
            self.c.drawString(M, self.y, titel)
            self.y -= 0.75 * cm
            if unter:
                self.c.setFont("Text", 13)
                self.c.setFillColor(GRAU)
                self.c.drawString(M, self.y, unter)
                self.y -= 0.8 * cm

    def fuss(self):
        if self.seite <= 1:
            return
        self.c.setFont("Text", 8.5)
        self.c.setFillColor(GRAU)
        self.c.drawString(M, 0.9 * cm, COPYRIGHT)
        self.c.drawRightString(W - M, 0.9 * cm, str(self.seite))

    def text(self, html, style=S_TEXT, w=None, x=None):
        p = Paragraph(html, style)
        ww = w or (W - 2 * M)
        _, hh = p.wrap(ww, H)
        p.drawOn(self.c, x if x is not None else M, self.y - hh)
        self.y -= hh + style.spaceAfter
        return hh

    def punkte(self, items, w=None, x=None):
        for t in items:
            self.text("<font color='#e8770f'>●</font>&nbsp;&nbsp;" + t, S_PUNKT, w, x)
        self.y -= 4

    def foto(self, name, w=None, x=None, crop=None, unter=None, max_h=None):
        img, (iw, ih) = bild(name, crop=crop)
        w = w or (W - 2 * M)
        h = w * ih / iw
        if max_h and h > max_h:
            h = max_h
            w = h * iw / ih
        x = M if x is None else x
        self.c.setFillColor(DUNKEL)
        self.c.roundRect(x - 4, self.y - h - 4, w + 8, h + 8, 8, stroke=0, fill=1)
        self.c.drawImage(img, x, self.y - h, w, h)
        self.y -= h + 10
        if unter:
            self.text(unter, S_KLEIN, w, x)
        return w, h


def verlauf(b):
    """Schaubild: so folgt das Licht dem Lied (Lichtstaerke je Abschnitt)."""
    c = b.c
    teile = [("Intro", 2.0, [0.25, 0.3]), ("Strophe", 2.6, [0.4, 0.45]), ("Aufbau", 2.0, [0.45, 0.8]), ("DROP", 2.6, [1.0, 0.95]),
             ("Break", 1.8, [0.2, 0.15]), ("Aufbau", 1.6, [0.3, 0.85]), ("DROP", 2.4, [1.0, 1.0]), ("Outro", 2.0, [0.5, 0.05])]
    total = sum(t[1] for t in teile)
    breite = W - 2 * M
    hoch = 4.2 * cm
    y0 = b.y - hoch - 0.9 * cm
    c.setFillColor(colors.HexColor("#f2f3f7"))
    c.roundRect(M, y0 - 1.3 * cm, breite, hoch + 2.4 * cm, 10, stroke=0, fill=1)
    c.setFillColor(TXT)
    c.setFont("Fett", 12)
    c.drawString(M + 0.5 * cm, y0 + hoch + 0.5 * cm, "So folgt das Licht dem Lied")
    x = M + 0.5 * cm
    nutz = breite - 1.0 * cm
    stufen = 14
    for name, dauer, (a, z) in teile:
        w = nutz * dauer / total
        for i in range(stufen):
            f = a + (z - a) * (i + 0.5) / stufen
            col = colors.Color(0.18 + 0.73 * f, 0.33 + 0.14 * f, 0.83 - 0.77 * f) if name != "DROP" else colors.HexColor("#e8770f")
            c.setFillColor(col)
            hh = max(0.15 * cm, hoch * f)
            c.rect(x + i * w / stufen, y0, w / stufen - 0.6, hh, stroke=0, fill=1)
        c.setFillColor(TXT if name != "DROP" else ORANGE)
        c.setFont("Fett" if name == "DROP" else "Text", 9.5)
        c.drawCentredString(x + w / 2, y0 - 0.5 * cm, name)
        x += w
    c.setFont("Text", 8.5)
    c.setFillColor(GRAU)
    c.drawString(M + 0.5 * cm, y0 - 1.0 * cm, "Höhe = Helligkeit und Tempo der Effekte. Beim Drop: alles auf dem Schlag, Blitze, volle Farben.")
    b.y = y0 - 1.7 * cm


def titelseite(b):
    c = b.c
    b.seite = 1
    c.setFillColor(DUNKEL)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(M, H - 3.1 * cm, 2 * cm, 0.22 * cm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Fett", 44)
    c.drawString(M, H - 4.6 * cm, "Light-Butler")
    c.setFont("Text", 19)
    c.setFillColor(colors.HexColor("#c9cde0"))
    c.drawString(M, H - 5.7 * cm, "Licht, das die Musik versteht.")
    img, (iw, ih) = bild("panel_handy.jpg", 1200)
    hh = 15.5 * cm
    ww = hh * iw / ih
    x = W - M - ww
    c.setFillColor(colors.HexColor("#2c3046"))
    c.roundRect(x - 0.35 * cm, 2.2 * cm - 0.35 * cm, ww + 0.7 * cm, hh + 0.7 * cm, 22, stroke=0, fill=1)
    c.drawImage(img, x, 2.2 * cm, ww, hh)
    b.y = H - 7.4 * cm
    b.text("Musik an – und das Licht tanzt mit. Der Light-Butler hört zu, erkennt Takt, Stimmung und den großen Moment "
           "im Lied und steuert daraus alle Lichter im Raum: Scheinwerfer, LED-Streifen, Lichtpaneele, Laser und Nebel.",
           S_HELL, w=W - 2 * M - ww - 1.0 * cm)
    b.y -= 0.4 * cm
    for t in ("Für Partys zu Hause, im Keller oder im Vereinslokal", "Bedienung mit Handy, Tablet oder Controller",
              "Läuft von selbst – oder genau nach deiner Show", "Hilft auch beim Ordnen der Musiksammlung"):
        b.text("<font color='#e8770f'>●</font>&nbsp;&nbsp;" + t, S_HELL, w=W - 2 * M - ww - 1.0 * cm)
    c.setFont("Text", 9)
    c.setFillColor(colors.HexColor("#c9cde0"))
    c.drawString(M, 1.35 * cm, COPYRIGHT)
    c.setFillColor(colors.HexColor("#7d8296"))
    c.drawString(M, 0.85 * cm, "Alle Bilder zeigen eine Beispiel-Anlage mit erfundener Musik.")


BLICK = [
    ("Licht live zur Musik", [
        "<b>AUTO:</b> Tempo, Beat, Takt, Tonart, Stimmung, Aufbau, Break und Drop erkennen, vier Stufen von Chillen bis Vollgas",
        "<b>Licht-Stile je Genre:</b> Club, Party, Rock, Ruhig, Weihnachten",
        "Helligkeit folgt der Lautstärke, Hi-Hat-Funkeln, Beat-Puls, Geräte der Reihe nach",
        "40 Szenen mit Szenen-Editor, Strobe, WOW!, Nebel, Freeze, Blinder, Blackout, Laser",
        "Titelerkennung und <b>Liedtexte live</b> zur Musik"]),
    ("Showmanager", [
        "<b>Eigene Licht- und Lasershows</b> zu jedem Lied, auf einer Zeitleiste",
        "<b>Show-Assistent:</b> fertige Show auf Knopfdruck, auf Wunsch mit Claude",
        "Quick-Show mit einem Tipp, Pegelkurven für Schlagzeug, Bass und Gesang",
        "Shows starten von selbst, sobald das Lied läuft"]),
    ("Musik", [
        "<b>Auto-DJ:</b> Playlist nach Energie, Tempo und Tonart, Übergänge im Takt – Musik und Licht laufen ganz von allein",
        "Anbindung an das DJ-Programm Mixxx: Drops im Voraus, Hotcues",
        "Ton von jedem Programm am Musik-Rechner, zum Beispiel Spotify oder YouTube"]),
    ("Musik-Datenbank", [
        "<b>Lieder, Interpreten und Alben</b> mit Cover, Bild, Lebenslauf und Titelliste",
        "<b>Energie, Tonart und BPM</b> misst der Light-Butler selbst, wenn sie in der Datei fehlen",
        "<b>Sterne und Favoriten</b>, Merkliste „Fehlt mir“",
        "Vorhören ab dem Hauptteil, mit Cover und Liedtext"]),
    ("Datenpflege", [
        "<b>CD-Cover besorgen</b> und alle <b>Tags eintragen</b>: Titel, Interpret, Album, Jahr, Genre",
        "Tag-Editor mit Vorschlägen, Auto-Tagger, Cover erzeugen",
        "Genres und Gruppen aufräumen, Doppelte finden",
        "<b>Beschädigte MP3s</b> erkennen und reparieren, in MP3 umwandeln",
        "Import- und CD-Assistent, NAS oder Stick spiegeln"]),
    ("Anlage und Geräte", [
        "<b>DMX</b> über Art-Net oder USB-Adapter, Art-Net auch als Eingang",
        "WLED-LED-Streifen, Nanoleaf-Lichtpaneele, HomeMatic für Raumlicht und Nebel",
        "Controller AKAI APC mini und ROLI LUMI Keys, Ableton Link fürs Tempo",
        "<b>Fixture-Manager</b> für die eigenen Geräte, <b>Raumplaner</b> mit Lichtwellen, DMX-Monitor"]),
    ("Sicherheit und Betrieb", [
        "Sperren für Laser, Strobe und Nebel",
        "Läuft auf Raspberry Pi, Windows-PC oder Mac",
        "Bedienung im Browser, Deutsch oder Englisch",
        "Sicherung jede Nacht, Notfall-Ordner am Musik-Stick"]),
]


def blick(b):
    """Zwei Spalten mit allen Funktionen; die Gruppen fuellen links, dann rechts."""
    b.neu("Alles auf einen Blick", "Was der Light-Butler alles kann")
    b.text("Der Light-Butler macht das Licht und auf Wunsch auch die Musik von allein. Du kümmerst dich um deine Gäste "
           "und die Party, nicht um die Technik.")
    b.y -= 4
    gap = 0.8 * cm
    cw = (W - 2 * M - gap) / 2
    top = b.y
    links = BLICK[:3]
    rechts = BLICK[3:]
    unten = top
    for spalte, x in ((links, M), (rechts, M + cw + gap)):
        b.y = top
        for titel, punkte in spalte:
            b.text(titel, S_GRUPPE, cw, x)
            for t in punkte:
                b.text("<font color='#e8770f'>●</font>&nbsp;" + t, S_LISTE, cw, x)
            b.y -= 8
        unten = min(unten, b.y)
    b.y = unten


def bauen():
    b = Heft()
    titelseite(b)

    b.neu("Was ist der Light-Butler?", "Ein kleiner Computer, der zuhört und Licht macht")
    b.text("Der Light-Butler ist eine Lichtsteuerung für Feste. Ein kleiner Computer (ein Raspberry Pi, ein Windows-PC oder ein Mac) bekommt den Ton vom "
           "Mischpult oder vom DJ-Programm, hört genau hin und steuert alle Lichter so, dass sie zur Musik passen – ohne "
           "dass jemand am Pult stehen muss. Wer will, greift jederzeit ein: über das Handy, das Tablet oder einen Controller.")
    b.y -= 6
    boxen = [("Musik", "Mischpult, DJ-Programm\noder Musik-Rechner", BLAU), ("Light-Butler", "hört zu, versteht\nund entscheidet", ORANGE),
             ("Licht", "Scheinwerfer, LED, Laser,\nLichtpaneele, Nebel", colors.HexColor("#8a4fd1"))]
    bw, bh, gap = 4.9 * cm, 2.6 * cm, 1.0 * cm
    x0 = (W - (3 * bw + 2 * gap)) / 2
    yb = b.y - bh
    for i, (t, u, col) in enumerate(boxen):
        x = x0 + i * (bw + gap)
        b.c.setFillColor(col)
        b.c.roundRect(x, yb, bw, bh, 10, stroke=0, fill=1)
        b.c.setFillColor(colors.white)
        b.c.setFont("Fett", 15)
        b.c.drawCentredString(x + bw / 2, yb + bh - 0.9 * cm, t)
        b.c.setFont("Text", 9.5)
        for k, line in enumerate(u.split("\n")):
            b.c.drawCentredString(x + bw / 2, yb + bh - 1.55 * cm - k * 0.45 * cm, line)
        if i < 2:
            b.c.setStrokeColor(GRAU)
            b.c.setLineWidth(2)
            ax = x + bw + 0.15 * cm
            b.c.line(ax, yb + bh / 2, ax + gap - 0.3 * cm, yb + bh / 2)
            b.c.line(ax + gap - 0.3 * cm, yb + bh / 2, ax + gap - 0.55 * cm, yb + bh / 2 + 0.2 * cm)
            b.c.line(ax + gap - 0.3 * cm, yb + bh / 2, ax + gap - 0.55 * cm, yb + bh / 2 - 0.2 * cm)
    b.y = yb - 0.9 * cm
    b.text("<b>So fühlt sich das an</b>")
    b.punkte(["In ruhigen Passagen ist das Licht weich und gedimmt, vor dem Refrain baut es Spannung auf – und beim "
              "„Drop“ geht es richtig los: alle Lichter auf dem Schlag, Blitze, Bewegung.",
              "Weihnachtslieder bekommen warme Farben ohne Schwarzlicht, Rock wirkt anders als Schlager oder Club-Musik.",
              "Ein Gerät nach dem anderen, Lichtwellen durch den Raum, Farben im Takt – der Abend wird nie eintönig.",
              "Die Bar oder der Couchtisch bleiben dabei ruhig beleuchtet, damit man sich noch zurechtfindet."])
    b.text("<b>Drei Arten, Licht zu machen</b>")
    b.punkte(["<b>AUTO</b> – der Light-Butler macht alles selbst, passend zu jedem Lied.",
              "<b>Szenen und Effekte</b> – auf Knopfdruck: Discokugel, Sternenhimmel, Lauflicht, Stroboskop, Nebel …",
              "<b>Shows</b> – für besondere Lieder eine eigene, genau programmierte Lichtshow, auf die Zehntelsekunde."])

    blick(b)

    b.neu("Die Bedienung", "Alles auf einer Seite, im Browser von Handy, Tablet oder Computer")
    b.foto("panel.jpg", crop=(0, 0, 1, 0.80), max_h=14.5 * cm,
           unter="Oben das laufende Lied mit Cover, Herz für Favoriten und dem Liedverlauf mit seinen Höhepunkten. Darunter die Sofort-Knöpfe, "
                 "Geschwindigkeit, Stil, Farbe, Licht-Mix und Bewegung.")
    b.punkte(["<b>Sofort-Knöpfe:</b> AUTO, Strobe, WOW! (alles voll), Sonnenbrille (alles weiß), Freeze (Bild anhalten), Blackout, Nebel.",
              "<b>Stil:</b> Weihnachten, Club, Party, Rock oder Ruhig – oder automatisch nach dem Genre des Liedes.",
              "<b>Farben und Bewegung:</b> Wunschfarben antippen, die Scheinwerfer folgen einem Muster oder einem Ziel im Raum."])
    b.text("Kein Programm zu installieren: Das Panel ist eine Webseite im eigenen WLAN. Jeder Gast mit dem Link kann mitspielen – oder auch nicht.", S_KLEIN)

    b.neu("Hört die Musik", "Tempo, Takt, Stimmung und die großen Momente")
    b.foto("panel.jpg", crop=(0, 0.05, 1, 0.23), unter="Der Light-Butler kennt das Lied: Tempo, Tonart, Energie, wo es ruhig wird und wo der Drop kommt.")
    verlauf(b)
    b.punkte(["<b>Takt und Tempo:</b> Lichter wechseln genau auf dem Schlag, Blitze sitzen auf dem Beat.",
              "<b>Aufbau, Break und Drop:</b> Der Light-Butler erkennt, wenn ein Lied Spannung aufbaut, kurz ruhig wird und dann "
              "explodiert – und macht das Licht genau dazu.",
              "<b>Mit dem DJ-Programm Mixxx</b> weiß er sogar im Voraus, wann der Drop kommt, weil er das ganze Lied schon kennt.",
              "<b>Stimmung und Tonart:</b> Moll klingt anders als Dur, ruhige Lieder wirken anders als laute – die Farben passen sich an.",
              "<b>Leise und laut:</b> In leisen Stellen wird das Licht sanfter, bei Stille geht es in den Ruhemodus.",
              "<b>Titel erkennen:</b> Auf Wunsch zeigt das Panel Titel, Interpret und sogar die aktuelle Liedtext-Zeile."])

    b.neu("Bedienen, wie es gerade passt", "Handy, Tablet, Controller und Klaviatur")
    y0 = b.y
    w1, h1 = b.foto("panel_handy.jpg", w=6.4 * cm)
    b.y = y0
    xr = M + 6.4 * cm + 0.9 * cm
    wr = W - M - xr
    b.text("<b>Am Handy</b> ist alles in einer Spalte untereinander – mit einer Hand bedienbar, mitten auf der Tanzfläche.", w=wr, x=xr)
    b.text("<b>Am Controller</b> (AKAI APC mini): 64 leuchtende Tasten für Szenen und Effekte, Schieberegler für die Helligkeit "
           "jeder Gerätegruppe. Jede Taste ist frei belegbar.", w=wr, x=xr)
    b.foto("apc.jpg", w=wr, x=xr, unter="Belegung des Controllers, im Panel änderbar.")
    b.text("<b>An der Klaviatur</b> (ROLI LUMI Keys): Szenen und Farben auf den Tasten, die Tasten leuchten in der passenden Farbe.", w=wr, x=xr)
    b.y = min(b.y, y0 - h1 - 20)

    b.neu("Der Showmanager", "Eigene Lichtshows für besondere Lieder")
    b.foto("editor.jpg", max_h=11 * cm, unter="Der Editor: oben das Lied als Wellenform mit seinen Abschnitten, darunter je Gerät die Spuren für Helligkeit, "
                                              "Farbe, Bewegung und Muster.")
    b.punkte(["Lichtbilder einfach auf die Zeitleiste ziehen – wie im Videoschnitt, auf den Takt genau.",
              "Fertige Muster: Blinken, Regenbogen, Kreisbewegung, Lauflicht, Gewitter und viele mehr.",
              "Die Show startet von selbst, sobald das Lied im DJ-Programm läuft – oder per Knopf am Handy.",
              "Laser und Nebel lassen sich einplanen, laufen aber nur mit eigener Freigabe."])
    b.foto("playback.jpg", w=7.6 * cm, x=M, unter="Abspielen am Tablet: Ton und Licht laufen synchron, BLACKOUT immer griffbereit.")

    b.neu("Der Show-Assistent", "Eine fertige Show auf Knopfdruck")
    b.foto("assistent.jpg", max_h=8.8 * cm)
    b.text("Der Assistent baut aus dem Aufbau eines Liedes eine komplette Show: ein Gerät allein für ein paar Sekunden, Wechsel "
           "genau auf dem Schlag, Gewitter an den großen Drops, ein sanftes Ausblenden am Ende. Wer möchte, lässt die künstliche "
           "Intelligenz Claude die Show entwerfen – mit eigenem Wunsch wie „mehr Blau, im zweiten Refrain alles auf einmal“. "
           "Ohne Internet entsteht der Vorschlag nach festen Regeln.")
    b.foto("raum.jpg", crop=(0.11, 0.09, 0.665, 0.67), max_h=8.6 * cm,
           unter="Der Raumplan: wo jedes Licht im Raum steht. Der Assistent nutzt ihn für Lichtwellen von einer Wand zur anderen "
                 "und stellt passende Geräte zusammen. Geräte einfach an ihren Platz ziehen, LED-Streifen als Linie.")

    b.neu("Die Musik-Datenbank", "Die ganze Sammlung im Blick")
    b.foto("musik.jpg", max_h=12.5 * cm)
    b.punkte(["Alle Lieder mit Cover, Tempo, Tonart, Energie (1–9), Genre, Album und wie oft sie gespielt wurden.",
              "Filtern und sortieren nach allem, zum Beispiel: Energie 7 bis 9, 120 bis 128 Schläge pro Minute, nur Favoriten.",
              "Reinhören direkt im Browser, Tags und Cover bearbeiten, mit einem Klick eine Show anlegen.",
              "Fehlende Angaben misst der Light-Butler selbst: Energie, Tonart und Tempo.",
              "Sterne vergeben und Favoriten setzen, Liedtexte live zur Musik."])

    b.neu("Interpreten, Alben und Favoriten", "Stöbern wie in einer Musik-App")
    b.foto("interpreten.jpg", max_h=9.2 * cm, unter="Interpreten mit Bild, Lebenslauf, ihren Alben und allen Liedern.")
    b.foto("favoriten.jpg", max_h=9.2 * cm, unter="Favoriten: ein Herz bei Liedern, Alben, Interpreten und Genres – alles auf einer Seite.")

    b.neu("Der Auto-DJ", "Die Playlist für den ganzen Abend")
    b.foto("autodj.jpg", max_h=12.5 * cm)
    b.punkte(["Wann beginnt das Fest, wie lange dauert es, wie wild soll es werden? Daraus entsteht eine Playlist, "
              "deren Energie über den Abend steigt.",
              "Die Lieder passen zueinander: ähnliches Tempo, harmonische Tonarten, nie zweimal derselbe Interpret hintereinander.",
              "Der Auto-DJ spielt selbst ab und überblendet taktgenau – und das Licht folgt ihm.",
              "Auf Wunsch wählt Claude die Lieder nach Anlass und Publikum aus, Favoriten kommen öfter dran."])

    b.neu("Ordnung in der Sammlung", "Werkzeuge für die Datenpflege")
    b.foto("pflege.jpg", max_h=10.5 * cm, crop=(0.15, 0, 0.85, 0.85))
    b.punkte(["<b>Tags und Cover:</b> CD-Cover besorgen, alle Tags eintragen, Titel per Musikerkennung finden, Cover erzeugen.",
              "<b>Beschädigte MP3s:</b> erkennen und reparieren, andere Formate in MP3 umwandeln.",
              "<b>Doppelte Lieder:</b> finden, vergleichen, die bessere Fassung behalten.",
              "<b>Genres und Gruppen:</b> aufräumen, zusammenlegen, fehlende ergänzen.",
              "<b>Import:</b> neue Musik vorhören, taggen und an den richtigen Platz sortieren.",
              "<b>Sichern:</b> die Sammlung auf eine NAS spiegeln, Notfall-Koffer mit allen Programmen am Musik-Stick."])

    b.neu("Sicherheit geht vor", "Laser, Stroboskop und Nebel – nur mit Freigabe")
    b.punkte(["<b>Laser</b> bleiben aus, außer in der eigenen Laser-Szene oder in einer Show mit ausdrücklicher Freigabe – "
              "und sofort aus bei Pause, Stopp, Blackout oder wenn etwas nicht stimmt.",
              "<b>Stroboskop:</b> Schnelles Blitzen kann Anfälle auslösen. Ohne Erlaubnis höchstens 2 Blitze pro Sekunde.",
              "<b>Nebel</b> läuft nie von allein: nur kurze Stöße auf Knopfdruck, mit Pausen dazwischen.",
              "<b>Blackout</b> geht immer vor: ein Tipp, und alles ist dunkel.",
              "Grenzwerte für jedes Gerät schützen Scheinwerfer vor falschen Einstellungen."])
    b.y -= 6
    b.foto("dmx.jpg", max_h=9 * cm, unter="DMX-Monitor: jeder Kanal jedes Geräts live im Blick.")

    b.neu("Technik", "Für alle, die es genau wissen wollen")
    rows = [("Herzstück", "Raspberry Pi, Windows-PC oder Mac, Programm in Python, Bedienung als Webseite im Heimnetz"),
            ("Ton", "USB-Audio vom Mischpult, Ton vom Musik-Rechner übers Netz, oder direkt aus dem DJ-Programm Mixxx"),
            ("Licht", "DMX über Art-Net oder USB-Adapter: Moving Heads, Wash-Lichter, Derby, Laser, Nebelmaschine"),
            ("Mehr Licht", "LED-Streifen mit WLED, Nanoleaf-Lichtpaneele, Schaltsteckdosen über HomeMatic"),
            ("Bedienung", "Browser auf Handy, Tablet, Computer; AKAI APC mini; ROLI LUMI Keys; Ableton Link fürs Tempo"),
            ("Musik-Rechner", "Mac oder Windows-PC: Helfer für Musiksammlung, Analyse, Tags, Pegelkurven (Grafikkarte)"),
            ("Intelligenz", "Eigene Musikanalyse; auf Wunsch Claude (Anthropic) für Shows, Playlists und Genres"),
            ("Installation", "Fertige Pakete für Pi, Mac und Windows, Sicherung jede Nacht, Notfall-Koffer am USB-Stick")]
    for k, v in rows:
        p1 = Paragraph("<b>%s</b>" % k, S_TEXT)
        p2 = Paragraph(v, S_TEXT)
        _, h1 = p1.wrap(4 * cm, H)
        _, h2 = p2.wrap(W - 2 * M - 4.4 * cm, H)
        hh = max(h1, h2) + 8
        b.c.setStrokeColor(colors.HexColor("#e0e3ea"))
        b.c.line(M, b.y - hh + 2, W - M, b.y - hh + 2)
        p1.drawOn(b.c, M, b.y - h1 - 2)
        p2.drawOn(b.c, M + 4.4 * cm, b.y - h2 - 2)
        b.y -= hh + 4
    b.y -= 10
    b.text("Neue Geräte trägt man im Panel ein, ohne zu programmieren: Adresse, Kanäle und Gruppe, fertig. Ein Simulator zeigt "
           "alles auch ohne Anlage – wie die Bilder in dieser Broschüre.", S_TEXT)
    b.y -= 14
    b.c.setFillColor(DUNKEL)
    b.c.roundRect(M, b.y - 3.2 * cm, W - 2 * M, 3.2 * cm, 12, stroke=0, fill=1)
    b.c.setFillColor(colors.white)
    b.c.setFont("Fett", 20)
    b.c.drawString(M + 0.8 * cm, b.y - 1.35 * cm, "Light-Butler")
    b.c.setFont("Text", 12)
    b.c.setFillColor(colors.HexColor("#c9cde0"))
    b.c.drawString(M + 0.8 * cm, b.y - 2.15 * cm, "Licht, das die Musik versteht. Freie Software (GPLv3) – Kontakt: lightbutler@gmx.at")
    b.c.setFillColor(ORANGE)
    b.c.rect(M + 0.8 * cm, b.y - 0.55 * cm, 1.5 * cm, 0.16 * cm, stroke=0, fill=1)
    b.y -= 3.6 * cm
    b.text("Idee, Konzept und Gestaltung: Markus Nepp. Programm und Broschüre sind mit Unterstützung von KI (Claude von Anthropic) "
           "entstanden. Alle Bilder zeigen eine Beispiel-Anlage mit erfundenen Liedern, Interpreten und Covern.", S_KLEIN)
    b.fuss()
    b.c.save()
    return b.seite


if __name__ == "__main__":
    n = bauen()
    print(ZIEL, n, "Seiten", round(os.path.getsize(ZIEL) / 1e6, 1), "MB")
