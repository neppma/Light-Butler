"""
inhalt.py - Text der Showmanager-Bedienungsanleitung (build_pdf.py macht daraus das PDF).

Bei Aenderungen am Showmanager auch hier nachziehen und neu bauen. Quelle der Fakten: Kapitel "Showmanager" in
docs/HANDBUCH.md und die Oberflaeche in pi/static/sm/.
"""

# Nummern im Bild der Werkzeugleiste (bilder/werkzeugleiste.png, 800 x 110 Pixel; Kopfleiste darueber nicht im Bild)
LEISTE = [(1, 24, 0), (2, 62, 0), (3, 101, 0), (4, 173, 0), (5, 249, 0), (6, 301, 0), (7, 336, 0), (8, 371, 0), (9, 443, 0),
          (10, 514, 0), (11, 22, 1), (12, 58, 1), (13, 93, 1), (14, 128, 1), (15, 163, 1), (16, 198, 1), (17, 234, 1),
          (18, 269, 1), (19, 304, 1), (20, 368, 1), (21, 430, 1), (22, 490, 1), (23, 546, 1), (24, 634, 1),
          (25, 753, 1), (26, 112, 2), (27, 183, 2), (28, 238, 2), (29, 270, 2)]
LEISTE_ZEILEN = [(2, 38), (38, 75), (75, 110)]

# Bereiche im Editor (bilder/editor_show_eigenschaften.jpg, oben Kopfleiste und Werkzeugleiste)
BEREICHE = [("A", 480, 124), ("B", 168, 191), ("C", 262, 215), ("D", 255, 296), ("E", 470, 152), ("F", 400, 182),
            ("G", 530, 319), ("H", 400, 491)]

# Schaltflaechen der Playback-Seite (bilder/shows_seite.jpg)
PLAY = [(1, 143, 55), (2, 664, 9), (3, 201, 55), (4, 118, 163), (5, 118, 270), (6, 260, 270), (7, 403, 270), (8, 547, 270),
        (9, 175, 345), (10, 565, 332), (11, 628, 332), (12, 118, 370), (13, 603, 411), (14, 525, 503), (15, 582, 501),
        (16, 620, 501), (17, 658, 501)]


def schreibe(b):
    einleitung(b)
    schnellstart(b)
    playback(b)
    editor(b)
    timeline(b)
    spuren(b)
    muster(b)
    gruppen(b)
    zeilen(b)
    sondergeraete(b)
    lied(b)
    eigenschaften(b)
    assistent(b)
    licht(b)
    mixxx(b)
    synchron(b)
    einstellungen(b)
    sicherheit(b)
    dateien(b)
    fehler(b)
    kurz(b)


def einleitung(b):
    b.kapitel("Einleitung")
    b.text("Mit dem <b>Showmanager</b> programmierst du eine komplette Lichtshow zu einer MP3 und spielst sie synchron ab, "
           "ähnlich wie in einem Musikprogramm. Du legst auf einer Zeitachse fest, wann welches Gerät was tut. "
           "Danach läuft die Show immer gleich ab, Bild für Bild, und nicht mehr nach dem, was der Light-Butler gerade in der Musik hört.")
    b.bild("playback.jpg", "Der Showmanager spielt eine Show ab.", crop=(100, 0, 700, 390), breite=0.72)
    b.abschnitt("Showmanager oder AUTO?")
    b.tabelle(["", "AUTO (Hauptpanel)", "Showmanager"], [
        ["<b>Woher das Licht kommt</b>", "Live aus der Musik: Tempo, Beat, Stimmung und Phasen", "Aus deiner Programmierung, genau auf die Zeit im Lied"],
        ["<b>Vorbereitung</b>", "Keine", "Show programmieren, oder den Show-Assistenten einen Vorschlag machen lassen"],
        ["<b>Passt für</b>", "Jede Musik, einen ganzen Abend", "Einzelne Lieder, die genau sitzen sollen"],
        ["<b>Was danach kommt</b>", "–", "Eine Show endet mit dem Lied, danach gilt wieder AUTO"],
    ], [2.3, 3.5, 3.8])
    b.abschnitt("So erreichst du ihn")
    b.punkte([
        "Im Hauptpanel oben über den Knopf mit den drei Balken und dem Strich.",
        "Am Handy in den Einstellungen unter <b>Showmanager</b>.",
        "Direkt im Browser: `http://lightbutler.local:8080/shows`",
    ])
    b.text("Der Showmanager hat zwei Seiten: die Seite <b>Shows</b> zum Abspielen und Verwalten (Kapitel 3) und den <b>Editor</b> zum Programmieren (ab Kapitel 4). "
           "Am besten arbeitest du am Editor mit einem großen Bildschirm, zum Abspielen reicht auch ein Handy.")
    b.abschnitt("Diese Anleitung herunterladen")
    b.text("Oben rechts gibt es auf beiden Seiten einen <b>runden Knopf mit einem Buch</b>. Er lädt diese Anleitung als PDF auf das Gerät, an dem du gerade arbeitest. "
           "Sie liegt auf dem Pi, du brauchst dafür kein Internet.")
    b.abschnitt("Die wichtigsten Begriffe")
    b.tabelle(["Begriff", "Bedeutung"], [
        ["<b>Show</b>", "Eine MP3 mit allem, was du dazu programmiert hast."],
        ["<b>Timeline</b>", "Die Zeitachse des Editors: links der Anfang des Liedes, rechts das Ende."],
        ["<b>Spur</b>", "Eine Zeile in der Timeline für eine Eigenschaft eines Geräts oder einer Gruppe, zum Beispiel Dimmer oder Farbe."],
        ["<b>Muster</b>", "Eine fertige Bewegung von Werten, zum Beispiel Blinken, Regenbogen oder Kreisbewegung."],
        ["<b>Clip</b>", "Ein Muster, das auf einer Spur liegt, mit Startzeit, Dauer und eigenen Einstellungen."],
        ["<b>Keyframe</b>", "Ein fester Wert zu einem festen Zeitpunkt. Zwischen zwei Keyframes wird übergeblendet."],
        ["<b>Gruppe</b>", "Mehrere Geräte, die eine Spur gemeinsam steuert."],
        ["<b>Szene</b>", "Ein gespeichertes festes Bild innerhalb der Show."],
        ["<b>Panel-Szene</b>", "Eine Szene aus dem Hauptpanel, die die Show für eine gewisse Zeit aufruft."],
        ["<b>Raster</b>", "Hilfslinien nach Takt oder Zeit, an denen Clips und Keyframes einrasten."],
        ["<b>Abschnitt, Cue</b>", "Aufbau des Liedes (Intro, Strophe, Main, Break, Outro) und Hotcues aus Mixxx, als Orientierung."],
    ], [1.5, 6])
    b.hinweis("Diese Anleitung hat Markus Nepp mit Unterstützung von KI (Claude von Anthropic) erstellt. Inhalte und Bilder stammen aus dem laufenden Programm, trotzdem können Fehler darin stecken.")
    b.hinweis("Die Bilder in dieser Anleitung stammen aus einem Probelauf ohne echte Anlage, mit einem erfundenen Beispiel-Lied. "
              "Deshalb stehen dort manche Geräte als „nicht erreichbar“, und deine Liste der Geräte und Shows sieht etwas anders aus.")


def schnellstart(b):
    b.kapitel("Schnellstart: deine erste Show")
    b.text("In diesen Schritten entsteht eine kleine Show, die du gleich am Licht sehen kannst. Was die einzelnen Knöpfe genau tun, steht in den späteren Kapiteln.")
    b.abschnitt("Von Hand programmieren")
    b.schritte([
        "Seite <b>Shows</b> öffnen, <b>+ Neue Show</b> antippen und einen Namen eingeben. Es öffnet sich der Editor.",
        "<b>MP3</b> antippen und das Lied wählen. Der Browser berechnet die Wellenform und schätzt das Tempo.",
        "Links im Reiter <b>Geräte</b> oder <b>Gruppen</b> ein Gerät in die Timeline ziehen. Es entstehen die Spuren Dimmer, Farbe und Bewegung, soweit es sie gibt.",
        "Links zum Reiter <b>Muster</b> wechseln und zum Beispiel <b>Blinken</b> auf die Spur <b>Dimmer</b> ziehen. Zur Spur <b>Farbe</b> passt zum Beispiel <b>Regenbogen</b>.",
        "Den Clip antippen. Unten erscheinen seine Einstellungen. Stelle Dauer und Geschwindigkeit ein oder ziehe den Rand des Clips mit dem Finger oder der Maus.",
        "<b>Speichern</b> antippen.",
        "Prüfen, ob <b>Licht an</b> leuchtet, und <b>Play</b> drücken. Die Musik läuft im Browser, das Licht folgt ihr.",
        "<b>Stop</b> beendet die Show und gibt das Licht zurück an AUTO.",
    ])
    b.abschnitt("Vom Assistenten vorschlagen lassen")
    b.text("Noch schneller geht es, wenn eine Show mit MP3 schon da ist:")
    b.schritte([
        "Im Editor <b>Assistent</b> antippen.",
        "Stil und den Regler „Ruhig bis wild“ einstellen, die Hakerl für Laser, Nebel, schnelle Blitze und Bewegung setzen.",
        "Vorschlag erstellen lassen. Er entsteht als <b>neue Kopie</b>, zum Beispiel „Mein Lied (Vorschlag)“, deine Show bleibt unverändert. Ist sie noch leer, kommt er direkt in sie.",
        "Vorschlag anhören, ansehen und im Editor nachbessern.",
    ])
    b.warnung("Prüfe jede Show einmal, bevor Gäste im Raum sind, besonders Laser und schnelle Blitze. Mehr dazu in Kapitel 18.")


def playback(b):
    b.kapitel("Die Seite Shows: abspielen und verwalten")
    b.text("Die Seite <b>Shows</b> (`/shows`) ist die Fernbedienung für fertige Shows. Oben liegt der Player, darunter die Liste aller Shows.")
    b.bild("shows_seite.jpg", "Die Seite Shows. Die Nummern gehören zur Tabelle darunter.", crop=(100, 0, 700, 565), breite=0.86, marken=PLAY)
    b.tabelle(["Nr.", "Knopf", "Was er tut"], [
        ["1", "<b>BLACKOUT</b>", "Alles dunkel, wie im Panel. Geht immer vor."],
        ["2", "<b>Kopfleiste</b>", "Wie auf jeder Seite: links ← zurück zur vorigen Seite, rechts das Haus (Panel) und die drei Striche, das Menü mit allen Seiten."],
        ["3", "<b>Runder Knopf mit Buch</b>", "Lädt diese Anleitung als PDF herunter."],
        ["4", "<b>Wellenform</b>", "Zeigt das Lied, gespielte Teile sind orange. Antippen springt an diese Stelle."],
        ["5", "<b>Zum Anfang</b>", "Springt an den Anfang des Liedes."],
        ["6", "<b>Play</b>", "Startet die Musik und damit die Show."],
        ["7", "<b>Pause</b>", "Hält an der aktuellen Stelle an."],
        ["8", "<b>Stop</b>", "Beendet die Show und gibt das Licht zurück an AUTO."],
        ["9", "<b>Lautstärke</b>", "Lautstärke der Musik in diesem Browser. Aufs Licht wirkt sie nicht."],
        ["10", "<b>Ton hier / woanders</b>", "Hier: Dieser Browser spielt die Musik und gibt den Takt vor. Woanders: Der Browser spielt nichts ab, die Show läuft nach der Uhr des Pi."],
        ["11", "<b>Licht an / aus</b>", "Aus: Du hörst nur die Musik, das Licht bleibt bei AUTO."],
        ["12", "<b>Hinweiszeile</b>", "Nennt, was gerade eingeschränkt ist, zum Beispiel die fehlende Strobe-Erlaubnis."],
        ["13", "<b>+ Neue Show</b>", "Fragt nach dem Namen, legt eine leere Show an und öffnet den Editor."],
        ["14", "<b>Bearbeiten</b>", "Öffnet diese Show im Editor."],
        ["15", "<b>Kopieren</b>", "Macht eine Kopie der Show."],
        ["16", "<b>Umbenennen</b>", "Gibt der Show einen neuen Namen."],
        ["17", "<b>Löschen</b>", "Legt die Show nach einer Rückfrage in den Papierkorb."],
    ], [0.5, 2.2, 6.4])
    b.abschnitt("Eine Show abspielen")
    b.schritte([
        "Show in der Liste antippen. Sie bekommt einen orangen Rahmen und erscheint oben im Player.",
        "<b>Play</b> drücken. Die Musik startet im Browser, das Licht folgt ihr.",
        "<b>Pause</b> hält an, <b>Stop</b> beendet die Show und gibt das Licht an AUTO zurück, <b>Zum Anfang</b> springt nach vorn. In der Wellenform springst du an jede Stelle.",
    ])
    b.bild("playback.jpg", "Während der Wiedergabe: Zeit, gespielter Teil in Orange, Anzeige „Synchron“ und die aktuelle Liedzeile.", crop=(100, 88, 700, 390), breite=0.72)
    b.abschnitt("Was die Anzeigen bedeuten")
    b.punkte([
        "<b>Synchron</b> mit einer Zahl: So viele Millisekunden weicht das Licht von der Musik ab. Kleine Werte sind normal.",
        "<b>Eigene Uhr</b>: Der Browser meldet sich nicht (WLAN weg, Seite zu). Die Show läuft nach der Uhr des Pi weiter und findet zurück, sobald er wieder da ist. Mehr in Kapitel 16.",
        "<b>Liedzeile</b> unter der Wellenform: die aktuelle Zeile, wenn die Show einen Liedtext hat (Kapitel 11).",
        "In jedem Eintrag der Liste stehen Länge, Tempo und die Zahl der Spuren. <b>ohne Musik</b> heißt, dass noch keine MP3 in der Show liegt.",
    ])
    b.abschnitt("Während eine Show läuft")
    b.text("Im Hauptpanel steht in der Hinweiszeile <b>SHOW LÄUFT</b>. Antippen führt zur Seite Shows. BLACKOUT, BLINDER, FREEZE, WOW!, Blitz, Nebel und General Dimmer wirken auch während einer Show. Mehr dazu in Kapitel 14.")


def editor(b):
    b.kapitel("Der Editor im Überblick")
    b.text("Im Editor programmierst du die Show. Du erreichst ihn über <b>Bearbeiten</b> in der Liste der Shows. Beim Öffnen bleibt das Licht bei AUTO, erst <b>Play</b> geht ans echte Licht.")
    b.bild("editor_show_eigenschaften.jpg", "Die Bereiche des Editors.", marken=BEREICHE)
    b.tabelle(["", "Bereich", "Wofür"], [
        ["A", "<b>Werkzeugleiste</b>", "Abspielen, Zoom, Raster, Bearbeiten, Speichern, Assistent. Im Abschnitt 4.1 Knopf für Knopf. Darüber die Kopfleiste wie auf jeder Seite: ← zurück zur vorigen Seite (meist die Liste der Shows), das Haus zum Panel, die drei Striche öffnen das Menü mit allen Seiten."],
        ["B", "<b>Linke Leiste</b>", "Die vier Reiter Geräte, Gruppen, Muster und Szenen. Von hier ziehst du alles in die Timeline."],
        ["C", "<b>Feste Zeilen</b>", "Musik, Szenen, Panel-Szenen und Master. Sie gehören zu keinem Gerät und bleiben immer stehen."],
        ["D", "<b>Spurnamen</b>", "Geräte und Gruppen mit ihren Spuren. Oben klappt <b>Alle zu</b> alle Geräte ein."],
        ["E", "<b>Lineal</b>", "Zeitleiste mit Abschnitten und Cue-Punkten. Antippen springt, oben ziehen setzt einen Loop."],
        ["F", "<b>Wellenform</b>", "Das Lied als Bild, gefärbt nach Abschnitten, unten die Balken der Liedzeilen."],
        ["G", "<b>Spuren</b>", "Hier liegen Clips und Keyframes. Die rote Linie ist die Abspielposition."],
        ["H", "<b>Eigenschaften</b>", "Einstellungen von dem, was gerade gewählt ist: Clip, Keyframe, Gerät oder die Show selbst."],
    ], [0.35, 1.9, 7])
    b.abschnitt("Die Werkzeugleiste Knopf für Knopf")
    b.text("Bei schmalem Fenster, etwa am Handy, ist die linke Leiste ausgeblendet. Dann steht ganz links in der Werkzeugleiste ein Knopf mit einem Fenster-Symbol, der sie ein- und ausblendet.")
    b.bild("werkzeugleiste.png", "Die Werkzeugleiste. Bei schmalem Fenster rücken die Knöpfe anders zusammen, die Bilder darauf bleiben gleich.", marken=LEISTE, streifen=LEISTE_ZEILEN)
    b.tabelle(["Nr.", "Knopf", "Was er tut", "Taste"], [
        ["1", "Zum Anfang", "Springt an den Anfang des Liedes.", "Pos1"],
        ["2", "Play / Pause", "Startet oder hält an. Mit <b>Licht an</b> läuft das echte Licht mit.", "Leertaste"],
        ["3", "Stop", "Beendet die Wiedergabe, das Licht geht zurück an AUTO.", ""],
        ["4", "Zeitanzeige", "Aktuelle Position. Antippen: Zeit genau eingeben.", ""],
        ["5", "Tempo", "Tempo der Show. Ändern unten bei den Eigenschaften der Show.", ""],
        ["6, 7", "Zoom", "Heraus- und hineinzoomen.", "− und +"],
        ["8", "Ganze Show zeigen", "Das ganze Lied passt in die Ansicht.", ""],
        ["9", "Raster", "Aus, Takt, Beat, 1/2, 1/4, 1 s oder 0,1 s. Clips und Keyframes rasten daran ein.", ""],
        ["10", "Fahne", "Blendet Abschnitte und Cue-Punkte ein oder aus und schaltet damit auch das Einrasten daran ein oder ab.", ""],
        ["11, 12", "Rückgängig, Wiederholen", "Nimmt den letzten Schritt zurück oder holt ihn wieder.", "Strg+Z, Strg+Y"],
        ["13", "Mehrfachauswahl", "Antippen wählt dazu, Ziehen zieht einen Rahmen. Vor allem für Touch.", "Strg+A = alles"],
        ["14", "Loop", "Schaltet den Loop ein oder aus. Ist er gesetzt, steht daneben ein Knopf zum Entfernen.", "L, Umschalt+L"],
        ["15", "Keyframe", "Setzt einen Keyframe an der Abspielposition auf der gewählten Spur.", "K"],
        ["16", "Ausschneiden", "Schneidet das Gewählte aus.", "Strg+X"],
        ["17", "Kopieren", "Kopiert das Gewählte.", "Strg+C"],
        ["18", "Einfügen", "Fügt an der Abspielposition ein.", "Strg+V"],
        ["19", "Löschen", "Löscht das Gewählte.", "Entf"],
        ["20", "Speichern", "Speichert die Show. Ein Punkt am Knopf zeigt ungespeicherte Änderungen.", "Strg+S"],
        ["21", "Laden", "Öffnet eine andere Show.", ""],
        ["22", "Assistent", "Erstellt einen Vorschlag, als neue Kopie oder in eine noch leere Show (Kapitel 13).", ""],
        ["23", "MP3", "Wählt die Musik dieser Show.", ""],
        ["24", "Name", "Der Name der offenen Show.", ""],
        ["25", "Lautstärke", "Lautstärke in diesem Browser.", ""],
        ["26", "Licht an / aus", "An: Play steuert das echte Licht, im Panel steht SHOW. Aus: nur im Browser anhören, das Licht bleibt bei AUTO.", ""],
        ["27", "BLACKOUT", "Alles dunkel, geht immer vor.", ""],
        ["28", "Eigenschaften", "Blendet den Bereich H ein oder aus.", ""],
        ["29", "Runder Knopf mit Buch", "Lädt diese Anleitung herunter.", ""],
    ], [0.65, 2.1, 6, 1.55])
    b.tipp("Am Mac wirkt die Befehlstaste wie Strg, also zum Beispiel Befehl+S zum Speichern. Halte den Mauszeiger über einen Knopf, dann erscheint ein kurzer Hinweis.")
    b.abschnitt("Die linke Leiste")
    b.bilder_reihe([
        ("editor_show_eigenschaften.jpg", (0, 141, 180, 474), "<b>Geräte</b>"),
        ("reiter_gruppen.jpg", (0, 85, 180, 418), "<b>Gruppen</b>"),
        ("reiter_muster.jpg", (0, 85, 180, 418), "<b>Muster</b>"),
        ("reiter_szenen.jpg", (0, 85, 180, 418), "<b>Szenen</b>"),
    ], "Die vier Reiter der linken Leiste.")
    b.punkte([
        "<b>Geräte:</b> Alle Geräte deiner Anlage mit DMX-Adresse und Kanalzahl. Ziehe ein Gerät in die Timeline, um seine Spuren anzulegen. Unten führt <b>Geräte bearbeiten</b> zur Seite Fixtures, <b>Profil laden</b> liest ein gesichertes Geräteprofil ein.",
        "<b>Gruppen:</b> Die Gruppen deines Aufbaus sind schon da, mit <b>+ Gruppe</b> legst du eigene an.",
        "<b>Muster:</b> Alle Muster, geordnet nach Dimmer, Farben, Moving Head, Effekte und den Sonderspuren. Ziehe sie auf eine Spur.",
        "<b>Szenen:</b> <b>+ Szene</b> legt eine leere Szene an, <b>+ Aus Position</b> übernimmt das Bild an der Abspielposition.",
    ])
    b.text("Bei schmalem Fenster ist die linke Leiste eingeklappt. Der Knopf mit den drei Strichen ganz links öffnet sie.")


def timeline(b):
    b.kapitel("Die Timeline bedienen")
    b.bild("gezoomt_abschnitte.jpg", "Hineingezoomt: Liedzeilen als Balken in der Wellenform, Abschnitte als Bänder über allen Spuren, Clips und Keyframes.")
    b.abschnitt("Alle Handgriffe auf einen Blick")
    b.tabelle(["Aktion", "Maus", "Touch", "Taste"], [
        ["Zoomen", "Strg + Rad", "Zwei Finger", "+ und −"],
        ["Waagrecht scrollen", "Umschalt + Rad", "Ziehen auf leerer Fläche", ""],
        ["Springen", "Lineal antippen, in der Wellenform auch ziehen", "Ebenso", "Pos1 = Anfang"],
        ["Loop setzen", "Im Lineal oben ziehen, Ränder und Band verschieben", "Ebenso", ""],
        ["Loop ein, aus, entfernen", "Loop-Knopf, Knopf daneben", "Ebenso", "L, Umschalt+L"],
        ["Verschieben", "Clip oder Keyframe ziehen", "Ebenso", ""],
        ["Länge ändern", "Linken oder rechten Rand ziehen (Zeiger wird zum Verschiebepfeil), oder Pfeile am Feld", "Ebenso", "Pfeil rauf und runter im Feld"],
        ["Mehrfachauswahl", "Rahmen ziehen, Umschalt + Klick", "Knopf mit gestricheltem Rahmen", "Strg+A = alles"],
        ["Kopieren, Ausschneiden, Einfügen", "Knöpfe", "Knöpfe", "Strg+C, X, V"],
        ["Löschen", "Knopf", "Knopf", "Entf"],
        ["Rückgängig, Wiederholen", "Knöpfe", "Knöpfe", "Strg+Z, Strg+Y"],
        ["Keyframe setzen", "Doppelklick auf die Spur, oder Knopf an der Abspielposition", "Doppelt tippen, oder Knopf", "K"],
        ["Play, Pause", "Knopf", "Knopf", "Leertaste"],
        ["Speichern", "Knopf", "Knopf", "Strg+S"],
    ], [2.4, 3.6, 2, 1.7])
    b.abschnitt("Raster und Einrasten")
    b.text("Das <b>Raster</b> (Takt, Beat, 1/2, 1/4, Sekunde, 0,1 s oder aus) zeigt seine Linien in der Timeline, und alles rastet beim Ziehen daran ein. "
           "Die Linien richten sich nach Tempo, erstem Schlag und Schlägen je Takt aus den Eigenschaften der Show. Sitzen sie nicht auf der Musik, korrigiere dort zuerst diese Werte (Kapitel 12).")
    b.text("Clips rasten außerdem an Cue-Punkten und Abschnittsgrenzen ein, mit dem Anfang und mit dem Ende, außer das Raster steht auf „aus“. Der Knopf mit der Fahne schaltet das zusammen mit der Anzeige ab.")
    b.tipp("Weit herausgezoomt ist ein Pixel bis zu einem halben Beat breit. Zum genauen Setzen also hineinzoomen. Exakte Zeiten gibst du unten bei den Eigenschaften ein.")
    b.abschnitt("Loop: eine Stelle immer wieder hören")
    b.bild("loop.jpg", "Ein Loop: der Bereich ist oben im Lineal orange markiert und über den Spuren hell, der Loop-Knopf leuchtet orange.")
    b.schritte([
        "Im Lineal oben einen Bereich ziehen. Es erscheint ein oranges Band, der Editor spielt ihn immer wieder.",
        "Band und Ränder lassen sich verschieben. Einen neuen Bereich ziehst du auch über einen alten hinweg.",
        "Der Loop-Knopf schaltet ein und aus, der Bereich bleibt in diesem Browser gemerkt.",
        "Der Knopf daneben (mit dem Kreuz) entfernt den Loop ganz.",
    ])
    b.punkte([
        "Gibt es noch keinen Loop, oder liegt er außerhalb der Ansicht, setzt der Knopf ihn neu: auf die gewählten Clips, sonst vier Takte ab der Abspielposition oder dem Anfang der Ansicht.",
        "Beim Abspielen springt die Linie gleich in den Bereich hinein.",
        "Der Loop gilt nur im Editor, nicht auf der Seite Shows und nicht aus Mixxx, und er wird nicht in der Show gespeichert.",
        "Bei jedem Rücksprung bleibt der Laser 0,5 s aus, und ein Nebelschub kommt nur, wenn die Mindestpause um ist.",
    ])
    b.abschnitt("Überblick behalten")
    b.bild("alle_auf.jpg", "Mit „Alle zu“ eingeklappt: Je Gerät bleibt eine schmale Zeile mit den Clips und Keyframes.", crop=(175, 85, 800, 470), breite=0.86)
    b.punkte([
        "<b>Alle zu</b> ganz oben in der Spalte mit den Spurnamen klappt alle Geräte auf ihre Kopfzeile ein, <b>Alle auf</b> wieder auseinander. Der Browser merkt sich die Einstellung. Master, Szenen und Panel-Szenen bleiben stehen.",
        "Der <b>Kopf eines Geräts</b> (die Zeile mit dem Namen) antippen klappt nur dieses Gerät ein oder aus. Eingeklappt zeigt er je Spur eine schmale Zeile, du siehst also, wann das Gerät etwas tut. Doppelt darauf tippen klappt es wieder aus.",
        "Beim Abspielen läuft die Ansicht mit. Scrollst oder zoomst du dabei selbst, bleibt sie stehen, bis du springst oder neu startest.",
    ])
    b.abschnitt("Geräte ordnen")
    b.text("Ziehe den Kopf eines Geräts nach oben oder unten, eine orange Linie zeigt das Ziel. Das ändert auch den Vorrang: Steuern ein Gerät und seine Gruppe denselben Wert, gewinnt die untere Spur, beim Dimmer weiter der hellste Wert.")
    b.abschnitt("Wie Clips aussehen")
    b.tabelle(["Aussehen", "Bedeutung"], [
        ["Schwarz-weiß, nach der Form des Musters", "Dimmer"],
        ["Bunt", "Farbe"],
        ["Blaugrün", "Bewegung"],
        ["Strich oben in der Farbe des Geräts", "Zu welchem Gerät der Clip gehört"],
        ["Pfeil nach schräg oben im Laser-Clip", "Ein Wert des KTV-Lasers läuft während des Clips (Kapitel 10)"],
        ["Weiße Rauten auf einer Linie", "Keyframes"],
        ["Breites Band mit Namen", "Spuren mit festen Stufen, zum Beispiel Gobo oder WLED-Preset"],
    ], [4, 5])


def spuren(b):
    b.kapitel("Spuren, Clips und Keyframes")
    b.abschnitt("Spuren anlegen")
    b.text("Ziehst du ein Gerät oder eine Gruppe in die Timeline, entstehen die Spuren <b>Dimmer</b>, <b>Farbe</b> und <b>Bewegung</b>, soweit es sie gibt. Weitere Spuren legst du unten an, wenn das Gerät gewählt ist: Tippe es in der linken Leiste an, dann steht unter „Spur anlegen“, was es noch kann.")
    b.bild("geraet_eigenschaften.jpg", "Das gewählte Gerät: unten seine möglichen Spuren und die aktuellen Werte der Kanäle.", crop=(0, 400, 800, 566))
    b.punkte([
        "Je nach Gerät gibt es zum Beispiel Farbrad, Gobo, Gobo-Rotation, Zoom, Prisma, Shutter, Strobe, Pan, Tilt, die Farben einzeln oder das WLED-Preset.",
        "Der Buchstabe <b>M</b> in der Spurzeile schaltet die Spur stumm (Mute, dann orange), das Kreuz entfernt sie.",
        "<b>Profil sichern</b> speichert die Beschreibung des Geräts als Datei. Neue Geräte legst du wie bisher auf der Seite Fixtures an.",
    ])
    b.hinweis("Einzelne Laser- und Hazer-Kanäle sowie Mode- und Reset-Kanäle gibt es absichtlich nicht als Spur. Das ist eine Sicherheitsregel (Kapitel 18).")
    b.abschnitt("Clips: Muster auf eine Spur legen")
    b.schritte([
        "Reiter <b>Muster</b> öffnen.",
        "Ein Muster auf eine passende Spur ziehen: Dimmer-Muster auf Dimmer, Farb-Muster auf Farbe, Bewegungen auf Bewegung.",
        "Den Clip antippen und unten einstellen. Verschieben und die Länge ändern geht auch direkt in der Timeline.",
    ])
    b.bild("clip_blinken.jpg", "Die Einstellungen eines Clips, hier Blinken auf der Dimmer-Spur der Docooler-Gruppe.", crop=(175, 345, 800, 567))
    b.abschnitt("Die Einstellungen eines Clips")
    b.text("Welche Felder erscheinen, hängt vom Muster ab. Hier stehen alle bis auf den Laser (Kapitel 10).")
    b.tabelle(["Einstellung", "Bereich", "Bedeutung"], [
        ["<b>Startzeit, Dauer</b>", "", "Wann der Clip beginnt und wie lang er ist. Die Pfeile am Feld ändern um einen Rasterschritt."],
        ["<b>Muster</b>", "", "Tauscht das Muster des Clips, die Zeit bleibt."],
        ["<b>Anfangswert, Endwert</b>", "0 bis 255", "Unterer und oberer Wert des Musters. 255 ist voll."],
        ["<b>Geschwindigkeit</b>", "0,01 bis 20 Hz", "Wiederholungen je Sekunde, oder je Beat, wenn <b>Im Takt</b> an ist."],
        ["<b>Im Takt</b>", "an, aus", "An: Die Geschwindigkeit zählt Zyklen je Beat und folgt dem Tempo der Show."],
        ["<b>Wiederholungen</b>", "0 bis 10000", "So oft läuft das Muster im Clip. 0 heißt: nach Geschwindigkeit."],
        ["<b>Versatz je Gerät</b>", "−4 bis 4", "Bei Gruppen: Die Geräte laufen zeitversetzt, 1 ist gleichmäßig verteilt."],
        ["<b>Einschaltanteil</b>", "0,05 bis 0,95", "Wie lang das Licht je Zyklus an ist, 0,5 ist halb an, halb aus."],
        ["<b>Intensität</b>", "0 bis 1", "Feste Stärke über den ganzen Clip."],
        ["<b>Fade In, Fade Out</b>", "0 bis 600 s", "Blendet das ganze Muster ein und aus."],
        ["<b>Breite</b>", "0,25 bis 16 Geräte", "Chase und Lauflicht: So viele Geräte leuchten gleichzeitig."],
        ["<b>Größe</b>", "0 bis 1", "Bewegungen: Wie weit das Gerät ausschwenkt."],
        ["<b>Mitte links/rechts, oben/unten</b>", "0 bis 1", "Bewegungen: Um welchen Punkt sie läuft, 0,5 ist die Mitte."],
        ["<b>Farbe A, Farbe B</b>", "", "Die Farben des Musters."],
        ["<b>Sättigung</b>", "0 bis 1", "Regenbogen und Zufällige Farben: 1 ist kräftig, kleinere Werte sind blasser."],
        ["<b>Weicher Übergang</b>", "0 bis 1", "Farbwechsel: 0 springt, höhere Werte blenden über."],
    ], [2.7, 1.5, 5.5])
    b.tipp("<b>Fade In</b> und <b>Intensität</b> sind verschieden: Beim Blinken mit einem Fade In von 4 s werden die Blitze 4 s lang heller, die Dunkelphasen bleiben dunkel. Die Intensität ist dagegen die feste Stärke über den ganzen Clip.")
    b.abschnitt("Keyframes")
    b.text("Doppelt auf eine Spur tippen setzt einen <b>Keyframe</b>, also einen festen Wert zu einem festen Zeitpunkt. Dazu gibt es den Knopf mit der Raute oder die Taste K, die ihn an der Abspielposition auf der gewählten Spur setzen.")
    b.text("Zwischen zwei Keyframes wird übergeblendet. Unten wählst du beim Feld <b>Bis zum nächsten</b>, wie:")
    b.tabelle(["Übergang", "Wirkung"], [
        ["<b>Linear</b>", "Gleichmäßig."],
        ["<b>Ease In</b>", "Beginnt langsam und wird schneller."],
        ["<b>Ease Out</b>", "Beginnt schnell und wird langsamer."],
        ["<b>Ease In/Out</b>", "Langsam am Anfang und am Ende."],
        ["<b>Konstant</b>", "Der Wert bleibt stehen und springt beim nächsten Keyframe."],
    ], [2, 7])
    b.thema("Spuren mit festen Stufen")
    b.text("WLED-Preset, Gobo und Farbrad springen immer, weil es dazwischen nichts gibt. Die Stufe wählst du unten in der Liste mit Namen, die Timeline zeigt ihn. Ein Notenzeichen in der Liste heißt, dass die Stufe Ton braucht, ein Blitz-Zeichen, dass sie blitzt und deshalb nur mit Strobe-Erlaubnis wirkt.")
    b.bild("keyframe_gobo.jpg", "Ein Keyframe auf der Gobo-Spur: Unten stehen Zeit und Gobo, in der Timeline das Band mit den Namen.", crop=(175, 240, 800, 567), breite=0.86)
    b.thema("Eine Farbe halten")
    b.text("Das Muster <b>Einzelfarbe</b> hält eine feste Farbe, solange der Clip läuft, mit Fade In und Fade Out. Soll eine Farbe bis zur nächsten Änderung stehen bleiben, setze auf der Spur <b>Farbe</b> einen Keyframe und stelle <b>Konstant</b> ein.")
    b.hinweis("Ein Farb-Clip ohne laufenden Dimmer leuchtet in voller Helligkeit. Soll das Gerät nur kurz da sein, lege einen Dimmer-Clip dazu und halte die Farbe so kurz wie ihn. Ein Dimmer-Keyframe auf 0 macht das Gerät dunkel, auch wenn eine Farbe läuft.")
    b.abschnitt("Eigene Muster")
    b.text("Hast du einen Clip fertig eingestellt, speichere ihn mit <b>Als eigenes Muster</b> oben bei seinen Eigenschaften. Er steht dann in allen Shows im Reiter Muster zur Verfügung.")
    b.abschnitt("Was gewinnt, wenn mehrere Spuren dasselbe steuern?")
    b.punkte([
        "<b>Dimmer:</b> Der hellste Wert gewinnt.",
        "<b>Alles andere:</b> Die unterste Spur gewinnt. Die Reihenfolge änderst du, indem du den Kopf eines Geräts ziehst.",
        "<b>Clip und Keyframes:</b> Ein laufendes Muster liegt über den Keyframes seiner Spur.",
        "<b>Spuren und Szenen:</b> Spuren liegen über Szenen. Eine Panel-Szene ersetzt dagegen alle Spuren, solange sie läuft (Kapitel 9).",
    ])
    b.abschnitt("Speichern und automatischer Stand")
    b.text("<b>Speichern</b> oder Strg+S sichert die Show. Ungespeicherte Änderungen zeigt ein Punkt am Knopf. Jede Minute entsteht zusätzlich ein automatischer Stand. Öffnest du die Show später und es gibt einen neueren automatischen Stand, fragt der Editor, ob er ihn wiederherstellen soll.")


def muster(b):
    b.kapitel("Alle Muster")
    b.text("Die Muster liegen im Reiter <b>Muster</b>, nach Art geordnet. Dieselben Muster an derselben Stelle ergeben immer dasselbe Bild, auch nach dem Springen.")
    b.bild("reiter_muster.jpg", "Der Reiter Muster: Ziehe ein Muster aus der Liste auf eine passende Spur.", crop=(0, 85, 400, 450), breite=0.62)
    b.abschnitt("Dimmer")
    b.tabelle(["Muster", "Was es tut"], [
        ["<b>Fade In</b>", "Blendet vom Anfangswert zum Endwert auf."],
        ["<b>Fade Out</b>", "Blendet vom Endwert zum Anfangswert ab."],
        ["<b>Blinken</b>", "Hartes An und Aus mit einstellbarem Einschaltanteil."],
        ["<b>Pulsieren</b>", "Wird schnell hell und klingt langsam ab."],
        ["<b>Strobe</b>", "Sehr schnelles Blitzen. Ohne Strobe-Erlaubnis höchstens 2 Blitze pro Sekunde."],
        ["<b>Sinus-Helligkeit</b>", "Gleichmäßiges Atmen auf und ab."],
    ], [2.2, 7])
    b.abschnitt("Farben")
    b.tabelle(["Muster", "Was es tut"], [
        ["<b>Einzelfarbe</b>", "Eine feste Farbe, solange der Clip läuft."],
        ["<b>Farbwechsel</b>", "Wechselt zwischen Farbe A und Farbe B, hart oder weich."],
        ["<b>RGB-Verlauf</b>", "Läuft von Farbe A nach Farbe B, über den ganzen Clip oder je Wiederholung."],
        ["<b>Regenbogen</b>", "Läuft durch alle Farben."],
        ["<b>Rot-Blau-Wechsel</b>", "Wechselt zwischen Rot und Blau (Farben änderbar)."],
        ["<b>Zufällige Farben</b>", "Immer neue Farben, an derselben Stelle aber immer dieselben."],
    ], [2.2, 7])
    b.abschnitt("Moving Head")
    b.text("Diese Muster gehören auf die Spur <b>Bewegung</b>. Alle haben Größe und Mitte.")
    b.tabelle(["Muster", "Was es tut"], [
        ["<b>Kreisbewegung</b>", "Fährt einen Kreis."],
        ["<b>Acht-Bewegung</b>", "Fährt eine liegende Acht."],
        ["<b>Links-Rechts-Sweep</b>", "Schwenkt waagrecht hin und her."],
        ["<b>Auf-Ab-Bewegung</b>", "Schwenkt senkrecht auf und ab."],
        ["<b>Sinusbewegung</b>", "Links und rechts, dazu eine langsame Welle auf und ab."],
        ["<b>Zufällige Bewegung</b>", "Fährt weich von Zufallspunkt zu Zufallspunkt, an derselben Stelle aber immer gleich."],
    ], [2.2, 7])
    b.abschnitt("Effekte für Gruppen")
    b.text("Chase, Lauflicht, Gruppenwelle und Fächer verteilen sich über die Geräte einer Gruppe und zeigen sich erst dort richtig.")
    b.tabelle(["Muster", "Was es tut"], [
        ["<b>Chase</b>", "Ein Gerät nach dem anderen, hart geschaltet. <b>Breite</b> sagt, wie viele zugleich leuchten."],
        ["<b>Lauflicht</b>", "Wie Chase, mit einem weichen Schweif."],
        ["<b>Beat-Synchron</b>", "Ein Puls auf jeden Schlag des Rasters, unabhängig vom Anfang des Clips. <b>Geschwindigkeit</b> sind die Pulse je Beat."],
        ["<b>Gruppenwelle</b>", "Eine Welle läuft durch die Geräte."],
        ["<b>Gruppenbewegung (Fächer)</b>", "Die Moving Heads fächern gegeneinander auf und zu."],
    ], [2.6, 7])
    b.abschnitt("Sonderspuren")
    b.tabelle(["Muster", "Spur", "Was es tut", "Kapitel"], [
        ["<b>Laser</b>", "Laser", "Steuert Eyes, Derby oder KTV.", "10"],
        ["<b>Nebelschub</b>", "Nebel", "Löst einen Schub am Hazer aus.", "10"],
        ["<b>Nanoleaf-Effekt</b>", "Effekt", "Lässt das Nanoleaf einen eigenen Effekt spielen.", "10"],
        ["<b>Szene aus dem Panel</b>", "Panel-Szenen", "Ruft eine Szene aus dem Hauptpanel auf.", "9"],
    ], [2.6, 1.4, 4.4, 0.8])


def gruppen(b):
    b.kapitel("Gruppen und Szenen")
    b.abschnitt("Gruppen")
    b.text("Eine Spur auf einer Gruppe steuert alle ihre Geräte gemeinsam. Die Gruppen deines Aufbaus sind schon da, sie tragen den Vermerk „aus dem Aufbau“. Eigene legst du unter <b>Gruppen</b> mit <b>+ Gruppe</b> an.")
    b.bild("reiter_gruppen.jpg", "Der Reiter Gruppen und daneben die Spuren der Gruppen in der Timeline.", crop=(0, 85, 620, 390), breite=0.86)
    b.punkte([
        "Chase, Lauflicht und Gruppenwelle verteilen sich von selbst über die Geräte.",
        "Bei anderen Mustern wirkt der <b>Versatz je Gerät</b>: Bei 1 sind die Geräte gleichmäßig über einen Zyklus verteilt, bei 0 laufen alle gleich.",
    ])
    b.abschnitt("Szenen")
    b.text("Eine Szene ist ein gespeichertes festes Bild innerhalb der Show.")
    b.schritte([
        "Reiter <b>Szenen</b> öffnen.",
        "<b>+ Szene</b> legt eine leere Szene an. <b>+ Aus Position</b> übernimmt, was an der Abspielposition programmiert ist.",
        "Die Szene in die Zeile <b>Szenen</b> der Timeline ziehen.",
        "Fade In und Fade Out unten einstellen.",
    ])
    b.text("Spuren liegen über Szenen. Eine Szene eignet sich also gut als Grundbild, über dem einzelne Clips spielen.")


def zeilen(b):
    b.kapitel("Panel-Szenen und Master")
    b.text("Über den Geräten liegen zwei Zeilen, die für die ganze Anlage wirken.")
    b.abschnitt("Panel-Szenen")
    b.text("Die Zeile <b>Panel-Szenen</b> ruft Szenen aus dem Hauptpanel für eine gewisse Zeit auf.")
    b.schritte([
        "In der Zeile doppelt antippen. Es entsteht ein Bereich.",
        "Unten die <b>Szene aus dem Panel</b> wählen.",
        "An den Rändern die Länge ziehen.",
    ])
    b.bild("panel_szene.jpg", "Die Panel-Szene „rot“ in ihrer Zeile, unten die Auswahl der Szene.", crop=(175, 85, 800, 567), breite=0.86)
    b.text("Die Szene läuft genau wie im Panel und ersetzt in dieser Zeit alle Spuren. Der Master wirkt mit. Sondertasten und die Szene Laser gibt es hier nicht, Laser laufen nur über Laser-Clips.")
    b.abschnitt("Master")
    b.text("Die Zeile <b>Master</b> regelt die Helligkeit aller Geräte, zum Beispiel für ein Ausblenden am Liedende oder „im Break alles auf 50 %“.")
    b.punkte([
        "Doppelt antippen setzt einen Keyframe. Oben ist 100 %, unten 0 %.",
        "Die Muster bleiben dabei erhalten, sie werden nur dunkler.",
        "Ohne Keyframe gilt 100 %. Der General Dimmer im Panel wirkt zusätzlich.",
        "Laser und Nebel regelt der Master nicht, sie laufen weiter nach ihren Clips.",
        "Einen Nanoleaf-Effekt regelt der Master ebenfalls nicht.",
    ])


def sondergeraete(b):
    b.kapitel("Laser, Nebel, Effektband und Nanoleaf")
    b.bild("laser_nebel_zeilen.jpg", "Spuren für Laser, Nebel und Effektband in der Timeline.", crop=(175, 85, 800, 330), breite=0.86)
    b.abschnitt("Erlaubnis einschalten")
    b.text("Laser und Nebel in Shows sind nur mit einem Hakerl möglich: Einstellungen allgemein → Ausgabe → <b>Laser in Shows erlauben</b> und <b>Nebel in Shows erlauben</b>. Standard ist aus. Die Hakerl gelten auch, wenn die Show aus Mixxx startet. Ohne Hakerl läuft die Show ohne Laser und Nebel, der Clip zeigt dann einen Hinweis.")
    b.abschnitt("Laser")
    b.warnung("Laser nie auf Personen oder in Augenhöhe richten. Die Software weiß nicht, wohin der Strahl zeigt und wer im Raum steht. Das bleibt deine Verantwortung, besonders wenn die Show aus Mixxx von selbst startet.")
    b.schritte([
        "Bei Eyes, Derby oder KTV die Spur <b>Laser</b> anlegen (Gerät wählen, unten „Spur anlegen“).",
        "Unter <b>Muster</b> den Clip <b>Laser</b> auf diese Spur ziehen.",
        "Unten einstellen und mit <b>Play</b> prüfen. Oben steht dann <b>LASER AKTIV</b>.",
    ])
    b.bild("laser_clip.jpg", "Die Einstellungen eines Laser-Clips am KTV-Laser.", crop=(175, 350, 800, 567))
    b.tabelle(["Einstellung", "Gerät", "Bedeutung"], [
        ["<b>Farbe</b>", "alle", "Bunt, Rot, Grün oder Blau."],
        ["<b>Tempo</b>", "alle", "Geschwindigkeit des Geräts, 0 bis 255."],
        ["<b>Pulse je Beat</b>", "alle", "0 = durchgehend, sonst bis zu 4 Pulse je Beat, mit <b>Einschaltanteil</b>."],
        ["<b>Muster (Derby)</b>", "Derby", "Muster 0 bis 15."],
        ["<b>KTV: Gruppe</b>", "KTV", "Liniengruppe 1 bis 6 oder Animationsgruppe."],
        ["<b>KTV: Muster</b>", "KTV", "Muster 0 bis 42 in der gewählten Gruppe."],
        ["<b>KTV: Fächer</b>", "KTV", "Kanal 14, vom Punkt zur breiten Linie."],
        ["<b>KTV: Zoom</b>", "KTV", "Kanal 6, 0 ist groß, 255 ist klein."],
        ["<b>KTV: Zoom-Automatik</b>", "KTV", "Kanal 7: 128 bis 159 größer, 160 bis 191 kleiner, ab 192 pendeln."],
        ["<b>KTV: Drehung</b>", "KTV", "0 bis 127 Winkel, 128 bis 191 rückwärts, ab 192 vorwärts."],
        ["<b>KTV: Position</b>", "KTV", "Links/rechts und oben/unten: 1 bis 127 feste Stelle, ab 128 bewegen."],
        ["<b>KTV: Welle</b>", "KTV", "Wellen-Effekt des Lasers, 0 bis 255."],
        ["<b>KTV: Effekt</b>", "KTV", "Kanal 15, 0 ist aus. Gefallen haben die Werte 46 und 35."],
    ], [2.5, 1.2, 5.6])
    b.thema("Werte während des Clips ändern (KTV)")
    b.text("<b>Fächer</b>, <b>Zoom</b>, <b>Drehung</b> und die beiden <b>Positionen</b> haben zusätzlich einen Wert <b>bis</b>. Weicht er ab, läuft der Wert während des Clips dorthin. Clips mit Verlauf zeigen in der Timeline einen kleinen Pfeil.")
    b.punkte([
        "<b>KTV: Verlauf</b>: einmal über den ganzen Clip, hin und her, oder im Takt je Beat, 2 Beats, Takt oder 2 Takte.",
        "<b>KTV: Hin und her, wie oft im Clip</b>: 1 bis 64.",
        "<b>KTV: Übergang</b>: Linear, Ease In, Ease Out, Ease In/Out oder Konstant.",
    ])
    b.thema("Wann der Laser sofort aus geht")
    b.text("Bei Pause, Springen, Stop, <b>Licht aus</b>, BLACKOUT, FREEZE, BLINDER und wenn sich Browser oder Mixxx mehr als 0,6 s nicht melden. Beim Programmieren im Stillstand siehst du den Laser also nicht, nur beim Abspielen. Ohne Strobe-Erlaubnis gibt es höchstens 2 Pulse pro Sekunde.")
    b.abschnitt("Nebel")
    b.warnung("Vorsicht Rauchmelder.")
    b.text("Den Clip <b>Nebelschub</b> auf den Hazer ziehen. Seine Dauer ist die Länge des Schubs, höchstens 10 s. Er nimmt denselben Weg wie der SMOKE-Knopf (DMX oder HomeMatic) mit derselben Mindestpause.")
    b.punkte([
        "<b>Der Schub entfällt,</b> wenn die Maschine aus oder kalt ist oder die Pause nicht um ist. Das Panel zeigt dann einen Hinweis. Die Show schaltet die Maschine nie selbst ein.",
        "Beim Springen über einen Schub kommt keiner. Pause, Stop und Springen beenden einen laufenden.",
    ])
    b.abschnitt("Effektband (WLED-Preset)")
    b.text("Das Effektband hat eine Spur <b>Dimmer</b> und eine Spur <b>WLED-Preset</b>. Auf der Preset-Spur setzt du Keyframes und wählst unten das Preset aus der Liste mit Namen. Ein Preset mit Notenzeichen braucht Ton, eines mit Blitz-Zeichen wirkt nur mit Strobe-Erlaubnis.")
    b.abschnitt("Nanoleaf")
    b.text("Das Nanoleaf läuft in der Show normal über seine Einzelpanels. Es kann aber auch seine eigenen Effekte spielen:")
    b.schritte([
        "Muster <b>Nanoleaf-Effekt</b> auf die Spur <b>Effekt</b> ziehen.",
        "Unten den Effekt wählen. Die Liste kommt vom Gerät, ein Notenzeichen heißt, dass der Effekt aufs Akustikmodul reagiert.",
    ])
    b.punkte([
        "Der Wechsel läuft übers Netz und ist nicht auf das Bild genau. Nimm dafür Bereiche von ein paar Sekunden.",
        "Bei Pause, Stop, BLACKOUT, ALLES HELL und FREEZE geht das Nanoleaf zurück auf Einzelpanels.",
        "Der Master regelt die Helligkeit eines Effekts nicht.",
    ])


def lied(b):
    b.kapitel("Abschnitte, Cues und Liedtext")
    b.abschnitt("Abschnitte und Cue-Punkte")
    b.text("Sie helfen beim Positionieren, aufs Licht wirken sie nicht.")
    b.bild("editor.jpg", "Oben im Lineal die Abschnitte (Intro, Strophe, Main, Break) und die gelben Cue-Punkte mit Nummer.", crop=(335, 112, 800, 240), breite=0.86)
    b.punkte([
        "Die <b>Abschnitte</b> (Intro, Strophe, Main, Break, Outro) färben die Wellenform und liegen als zarte Bänder über allen Spuren.",
        "Die <b>Cue-Punkte</b> sind gelbe Linien mit einer Nummer im Lineal.",
        "Dazu muss das Lied nur einmal in einem Mixxx-Deck liegen. Danach stehen sie in der Show und sind auch ohne Mixxx da.",
        "Gefunden wird das Lied über die MP3 der Show oder den Titel unter <b>Lied wählen</b> (Kapitel 12). Ohne fertige Analyse gibt es nur die Cues.",
        "Stammen sie aus einer anderen Datei als die MP3 der Show, warnt der Editor, weil sie dann versetzt liegen können.",
        "Der Knopf mit der Fahne neben dem Raster blendet alles aus und schaltet auch das Einrasten daran ab.",
    ])
    b.abschnitt("Pegelkurven der Spuren")
    b.bild("kurven.jpg", "Unter der Wellenform die fünf Kurven: Stimme, Bass, Kick, Snare/Hi-Hat und Sonstiges.", crop=(195, 108, 800, 300))
    b.text("Hat der Mac oder der Windows-PC die MP3 der Show zerlegt, stehen unter der Wellenform fünf schmale Zeilen, jede in ihrer Farbe. Je höher der Ausschlag, desto lauter spielt dort Stimme, Bass, Kick, Snare/Hi-Hat oder der Rest. So siehst du zum Beispiel, wo der Gesang einsetzt oder wo die Kick aussetzt. Aufs Licht wirken die Kurven nicht.")
    b.punkte([
        "Der Knopf <b>Kurven</b> links unter „Musik“ klappt die Zeilen ein und aus. Der Browser merkt sich das.",
        "Ohne Kurven gibt es weder Zeilen noch Knopf. Gerechnet werden sie am Mac oder am Windows-PC, mehr dazu im Handbuch des Panels unter „Pegelkurven der Spuren“.",
        "Oben in der Werkzeugleiste steht, wie es um die Kurven steht: „Kurven: PC rechnet …“, „Kurven: noch keine“ oder „Kurven: MP3 zu lang“ (nur bis 6 Minuten). Sobald sie fertig sind, erscheinen sie von selbst, ohne die Seite neu zu laden.",
        "Auf der Seite Shows zeigt eine Zeile unter der Überschrift, welcher Rechner gerade welches Lied rechnet und wie weit der Vorab-Lauf der Bibliothek ist. In der Liste steht bei jeder Show ein Häkchen bei „Kurven“ oder „Kurven werden gerechnet“.",
        "Wählst du eine andere MP3, verschwinden sie, bis die neue MP3 gerechnet ist.",
    ])
    b.abschnitt("Liedtext zu einer Show")
    b.schritte([
        "Unten bei den Eigenschaften der Show <b>Liedtext holen</b> antippen. Der Pi sucht bei LRCLIB, frei und ohne Anmeldung.",
        "Passt die Länge des Eintrags zur MP3, stehen die Zeilen als Balken an ihrer Stelle unten in der Wellenform.",
        "Mit <b>Liedtext neu holen</b> versuchst du es noch einmal, <b>Liedtext weg</b> entfernt ihn.",
    ])
    b.punkte([
        "An LRCLIB gehen Titel und Interpret, keine Musik, und nur auf Knopfdruck.",
        "Passt die Länge nicht, zum Beispiel bei einem anderen Remix, gibt es nur den Text ohne Zeiten.",
        "Das Ende einer Zeile ist oft geschätzt, weil Liedtext-Dateien meist nur den Anfang einer Zeile kennen. Die Zeiten stammen von anderen Nutzern und können ungenau sein.",
        "Auf der Seite Shows läuft die aktuelle Zeile mit, und Claude bekommt den Text für den Entwurf (Kapitel 13). Aufs Licht wirkt er nie.",
    ])
    b.hinweis("Die Texte gehören ihren Rechteinhabern. Das Ganze ist für zu Hause gedacht, eine öffentliche Anzeige ist etwas anderes.")
    b.abschnitt("Liedzeile im Hauptpanel")
    b.bild("hauptpanel_show.jpg", "Im Hauptpanel steht die aktuelle Zeile unter dem Liedtitel, daneben der Knopf Text.", crop=(0, 0, 800, 290), breite=0.86)
    b.text("Die Zeile hat im Statusbereich einen festen Platz, die Knöpfe darunter bleiben also stehen, auch ohne Text. Der Knopf <b>Text</b> daneben öffnet ein Fenster mit dem ganzen Text.")
    b.bild("text_fenster.jpg", "Das Fenster Text: Die aktuelle Zeile ist markiert.", crop=(185, 40, 620, 567), breite=0.5)
    b.abschnitt("Liedtext in AUTO")
    b.text("In den Einstellungen unter <b>Titelerkennung</b> gibt es den Schalter <b>Liedtext zum laufenden Lied holen</b> (Standard aus). Der Pi sucht dann je Lied einmal bei LRCLIB und merkt es sich. Ohne Treffer mit passender Länge bleibt die Zeile leer.")
    b.punkte([
        "Das gilt für Lieder aus Mixxx und, wenn die Titelerkennung an ist, auch für Musik ohne Mixxx. Dort kommt die Stelle im Lied aus der Antwort von Shazam, wenn sie mitkommt, und jede neue Erkennung rückt sie zurecht.",
        "<b>Text neu suchen</b> im Fenster sucht noch einmal, auf Wunsch mit anderem Interpret oder Titel. Der alte Text bleibt, bis es einen Treffer gibt.",
        "Ohne Mixxx kannst du im Fenster die Zeile antippen, die gerade gesungen wird. Der Pi rechnet ab dort weiter.",
        "Eine echte Live-Band erkennt Shazam oft nicht, und ihr Tempo weicht ab. Dann bleibt nur das Antippen, falls überhaupt ein Text da ist.",
    ])
    b.abschnitt("Liedtexte vorab holen")
    b.bild("statistik_vorabladen.jpg", "Auf der Seite Statistik: Liedtexte vorab holen.", crop=(0, 0, 800, 158))
    b.text("Auf der Seite <b>Statistik</b> holt <b>Liedtexte vorab holen</b> die Texte aller Lieder der Mixxx-Bibliothek langsam im Hintergrund, eine Anfrage alle 3 Sekunden, also bei 9500 Liedern mindestens rund 8 Stunden.")
    b.punkte([
        "Anhalten und später weitermachen geht jederzeit. Nach einem Neustart macht es von selbst weiter, auch ohne Mac, sobald der Pi die Bibliothek einmal bekommen hat (der Mac schickt sie alle 10 Minuten).",
        "Dafür gehen alle Titel und Interpreten an LRCLIB, keine Musik.",
        "Danach läuft die Anzeige auch ohne Internet, wenn der Schalter an ist.",
    ])


def eigenschaften(b):
    b.kapitel("Eigenschaften der Show")
    b.text("Ist nichts gewählt, zeigt der untere Bereich die Eigenschaften der Show. Hast du links ein Gerät, eine Gruppe oder eine Szene gewählt, zeigt er deren Einstellungen: Tippe dann einen Clip an und danach auf eine leere Stelle der Timeline. Ist der Bereich nicht zu sehen, blendet ihn der Knopf neben BLACKOUT ein.")
    b.bild("editor_show_eigenschaften.jpg", "Die Eigenschaften der Show.", crop=(180, 474, 800, 646))
    b.tabelle(["Feld", "Bedeutung"], [
        ["<b>Tempo (BPM)</b>", "Schläge pro Minute. Der Browser schätzt es beim Laden der MP3. Bestimmt das Raster und alles, was <b>Im Takt</b> läuft."],
        ["<b>Erster Schlag bei (s)</b>", "Wo der erste Schlag im Lied liegt. Die Rasterlinien beginnen hier."],
        ["<b>Schläge je Takt</b>", "Meist 4."],
        ["<b>Länge</b>", "Länge der Show."],
        ["<b>Linie vorziehen (ms)</b>", "Läuft die rote Linie hörbar hinter dem Ton her, stelle hier zum Beispiel 50 ms ein. Wirkt nur auf die Anzeige in diesem Browser, nie auf das Licht oder gesetzte Zeiten."],
        ["<b>Licht-Versatz (ms)</b>", "Läuft das Licht vor oder nach dem Ton, stelle es hier ein, plus = früher. Wirkt sofort, auch während die Musik läuft. Gilt für alle Shows und steht auch unter Einstellungen allgemein → Ausgabe."],
        ["<b>Lied wählen</b>", "Ordnet der Show ein Lied aus den Mixxx-Decks oder der Bibliothek zu. Bringt Abschnitte und Cues und ist die Grundlage für den Start aus Mixxx."],
        ["<b>Trennen</b>", "Löst diese Zuordnung."],
        ["<b>startet aus Mixxx</b>", "Nimmst du das Hakerl weg, startet diese Show nicht von selbst aus Mixxx (Kapitel 15)."],
        ["<b>Liedtext holen</b>, <b>Liedtext weg</b>", "Siehe Kapitel 11."],
    ], [2.6, 7])
    b.abschnitt("Den Licht-Versatz einstellen")
    b.text("Am besten hörst du den Versatz mit einem Loop um einen Clip, der hart auf einem Schlag beginnt, nicht mit einem durchgehenden Muster: Ein Blinken im Takt sieht nach einer Verschiebung um einen ganzen Zyklus wieder gleich aus. "
           "Läuft das Licht gegen den Anfang eines Clips um den Versatz zu spät, bleibt es in dieser Zeit dunkel.")
    b.tipp("Bluetooth-Lautsprecher brauchen etwa +150 bis +250 ms.")


def assistent(b):
    b.kapitel("Der Show-Assistent")
    b.text("Der Knopf <b>Assistent</b> erstellt aus Lied und Geräten einen fertigen Vorschlag als <b>neue Kopie</b> der Show, zum Beispiel „Mein Lied (Vorschlag)“. Deine Show bleibt unverändert, jeder weitere Klick macht einen neuen Vorschlag mit anderen Farben und Mustern. Ist die Show noch <b>leer</b> (keine Clips oder Keyframes) und im Editor nichts ungespeichert, kommt der Vorschlag direkt in diese Show, so sammeln sich keine leeren Shows an. Das Fenster sagt vorher, wohin er kommt. Danach brauchst du nur noch das Feintuning.")
    b.bild("assistent.jpg", "Das Fenster des Show-Assistenten. Die Summe bei „Claude bisher“ ist ein Beispiel.", crop=(190, 30, 610, 545), breite=0.66)
    b.abschnitt("Woher er das Lied kennt")
    b.text("Liegt das Lied einmal in einem Mixxx-Deck, nutzt er Abschnitte, Cues, Aufbauten, Pausen, Drops, Energie und Genre. Ohne Mixxx schätzt er den Aufbau aus der Wellenform der MP3, das ist ungenauer. Oben im Fenster steht, was vorliegt.")
    b.abschnitt("Die Einstellungen im Fenster")
    b.tabelle(["Einstellung", "Wirkung"], [
        ["<b>Stil</b>", "Kommt aus dem Genre und lässt sich hier ändern."],
        ["<b>Ruhig bis wild</b>", "Regelt, wie viel passiert. Steht am Anfang nach der Energiestufe des Liedes (1 ruhig, 6 Mitte, 9 fast wild)."],
        ["<b>Laser</b>", "Setzt Laser-Clips. Wirkt nur mit dem Hakerl <b>Laser in Shows erlauben</b>."],
        ["<b>Nebel</b>", "Setzt Nebelschübe. Wirkt nur mit dem Hakerl <b>Nebel in Shows erlauben</b>."],
        ["<b>Schnelle Blitze</b>", "Ohne Strobe-Erlaubnis gilt trotzdem höchstens 2 Blitze pro Sekunde."],
        ["<b>Bewegung</b>", "Setzt Bewegungen auf Moving Heads."],
        ["<b>Ambiente an</b>", "Lässt Barlicht, Theke und Couchtisch ruhig mitleuchten. Sonst bleiben sie aus."],
        ["<b>Wer entwirft?</b>", "Offline, „Claude verfeinert“ oder „Claude entwirft die ganze Show“, siehe unten."],
        ["<b>Wunsch, Liedtext</b>", "Nur für Claude: dein Wunsch in eigenen Worten, und ein eigener Liedtext, sonst der aus der Show."],
    ], [2.3, 7])
    b.warnung("Der Assistent setzt nur Clips und schaltet keine Erlaubnis ein. Prüfe den Vorschlag vor dem ersten Einsatz, besonders den Laser.")
    b.abschnitt("Wie er arbeitet")
    b.punkte([
        "<b>Ein Gerät nach dem anderen:</b> Ein Gerät spielt ein paar Sekunden allein, alles andere ist finster, dann kommt genau auf dem Beat das nächste: Vega, Nanoleaf, Effektband, Docooler, Laser, Eyes und Derby, Washes, dann wieder von vorn.",
        "<b>Partner:</b> Im Hauptteil kommt jeder dritte Einsatz mit einem passenden zweiten Gerät, nie mehr. Mal spielen beide gemeinsam, mal schalten sie jeden Beat hin und her.",
        "<b>Cues und Abschnitte:</b> Liegt ein Cue oder ein neuer Abschnitt an der Stelle, ist das Effektband dran.",
        "<b>Große Drops:</b> Nur dort, weit auseinander, arbeiten für 2 Takte alle zusammen wie ein Gewitter.",
        "<b>Starke Peaks</b> (Bass, Schiffshorn), die man auch in der Wellenform sieht: Ein Gerät startet bei 100 % und klingt mit der Amplitude des Peaks ab, als Keyframes, die du nachziehen kannst. Beim Laser bleibt der Fächer ganz offen, und das Bild zoomt klein. Dazwischen bleibt es bei dichten Peaks finster. Eine Reihe von Peaks gehört einem Gerät, die nächste Reihe dem nächsten: Effektband, Laser, Docooler, Vega, Nanoleaf.",
        "<b>Nanoleaf:</b> Jeder dritte Einsatz ist einer seiner eigenen Effekte, wenn er lang genug ist.",
        "<b>Ruhepunkte:</b> Nach einigen Wechseln bleibt ein Gerät länger dran, damit es nicht hektisch wird.",
        "<b>Liedende:</b> Wird das Lied am Schluss leiser, blendet die Zeile Master das Licht mit dem Pegel der Wellenform aus.",
        "<b>Aufbau und Pause:</b> Im Aufbau wird das Blinken schneller, in einer Pause der Musik wird es finster.",
        "<b>Washes und Farben:</b> Die Washes bleiben dezent (höchstens 40 %), neue Farben gibt es je Abschnitt.",
        "<b>Raum und Helligkeit:</b> Die Docooler bewegen sich nur waagrecht. Schwache Geräte (Vega, Eyes, Derby, Washes) spielen im lauten Hauptteil nie allein: Vega, Eyes und Derby bekommen die Docooler dazu, die Washes das Nanoleaf, auf das sie leuchten. Nach einem Nebelschub ist der Vega dran, dann sieht man seinen Strahl.",
    ])
    b.abschnitt("Mit den Pegelkurven der Spuren")
    b.text("Hat der Mac die MP3 zerlegt (Kapitel 11), weiß der Assistent genauer, was in der Musik passiert. Oben im Fenster steht dann „Dazu die Pegelkurven …“.")
    b.punkte([
        "<b>Ruhige Stelle:</b> Fehlt die Kick mindestens 2 Takte, ist es ruhig, auch wenn die Musik laut ist. Einzelne Schläge alle paar Takte zählen nicht als Beat.",
        "<b>Aufbau:</b> Wird dort Snare/Hi-Hat lauter, blinken die Docooler immer schneller.",
        "<b>Drop:</b> Kommt die Kick nach mindestens 4 Takten zurück, ist das ein Drop.",
        "<b>Pause:</b> Sind alle Spuren leise, wird es finster.",
        "<b>Gesang an ruhiger Stelle:</b> Der Vega projiziert sein Gobo an die Wand gegenüber, oder das Nanoleaf leuchtet mit den Washes.",
        "<b>Claude:</b> bekommt die Kurven grob, einen Wert je Takt, und die Beschreibung des Raums.",
    ])
    b.abschnitt("Mit dem Raumplan")
    b.text("Hast du im Panel auf der Seite <b>Raumplan</b> eingezeichnet und gespeichert, wo die Geräte stehen, nutzt der Assistent das. Oben im Fenster steht dann „Mit Raumplan“.")
    b.punkte([
        "<b>Reihenfolge an der Wand:</b> Chase, Lauflicht und Gruppenwelle laufen über Docooler, Washes, Eyes und Derby so, wie sie im Raum hängen. Dafür legt der Vorschlag eigene Gruppen mit dem Zusatz „(Raum)“ an.",
        "<b>Lichtwelle:</b> Jeder vierte Einsatz im Hauptteil lässt das Licht durch den Raum laufen. Die Geräte leuchten von links nach rechts nacheinander auf, auf jedem Beat eine Stufe weiter, und wieder zurück. Geräte, die nah beieinander stehen, leuchten gemeinsam.",
        "<b>Wer mitmacht:</b> Docooler, Vega, Nanoleaf, UV, Eyes und Derby. Washes (zu träger Dimmer), Ambiente, Laser und Nebel nicht.",
        "<b>Claude</b> bekommt die Positionen in Metern und kann selbst Lichtwellen planen.",
    ])
    b.abschnitt("Wer entwirft: offline oder Claude")
    b.tabelle(["Wahl", "Was passiert", "Kosten"], [
        ["<b>Offline</b>", "Der Assistent arbeitet nach festen Regeln. Kein Internet nötig.", "Keine"],
        ["<b>Claude verfeinert</b>", "Claude stellt die Regie nur um, gesetzt wird weiter nach den festen Regeln.", "Geschätzt einige Cent"],
        ["<b>Claude entwirft die ganze Show</b>", "Claude bekommt Anlage, Liedanalyse, Wunsch und Liedtext und setzt selbst Clips und Keyframes, auch Panel-Szenen und Nanoleaf-Effekte. Dauert einige Minuten.", "Geschätzt 50 Cent bis 1,50 Euro"],
    ], [2.5, 5.4, 1.8])
    b.thema("API-Schlüssel")
    b.text("Für beide Claude-Arten braucht es Internet und einen API-Schlüssel von platform.claude.com. Ein Abo reicht dafür nicht. Du hinterlegst ihn im Fenster, er bleibt nur auf dem Pi und wird nicht mehr angezeigt. Löschen geht oben im Claude-Bereich des Fensters, mit Rückfrage.")
    b.thema("Kosten")
    b.text("Oben im Fenster steht immer die geschätzte Summe bisher, nach jedem Aufruf zusätzlich dessen Kosten, aus den Angaben von Claude und der Preisliste. Das ist keine Abrechnung und kein Guthaben: Beides steht auf platform.claude.com, über die API lässt sich das Guthaben nicht abfragen.")
    b.thema("Was an Anthropic geht")
    b.text("Titel, Genre, Tempo, Aufbau, Lautstärke je Takt, deine Anlage ohne Adressen, dein Wunsch und der Liedtext. Keine Musik.")
    b.thema("Wenn etwas nicht passt")
    b.text("Klappt es nicht, entsteht der Vorschlag offline, und das Fenster nennt den Grund. Auch Claude kann nur bekannte Muster und Werte wählen und nichts einschalten, was du abgehakt hast. Was nicht passt, verwirft der Pi und nennt die Zahl.")


def licht(b):
    b.kapitel("Licht beim Programmieren und SHOW im Panel")
    b.abschnitt("Was das Licht im Editor tut")
    b.tabelle(["Du tust", "Das Licht"], [
        ["Editor öffnen", "Bleibt bei AUTO."],
        ["<b>Play</b> mit <b>Licht an</b>", "Geht ans echte Licht, das Panel zeigt SHOW."],
        ["<b>Pause</b>", "Bleibt an der Show und folgt der Abspielposition und jeder Änderung."],
        ["<b>Stop</b>", "Zurück an AUTO."],
        ["<b>Licht aus</b>", "Du hörst nur im Browser, die Anlage bleibt bei AUTO."],
        ["<b>Licht an</b> im Stillstand", "Du siehst das Bild an der Abspielposition, ohne zu starten."],
    ], [3, 6.5])
    b.tipp("So programmierst du bequem: Licht an, Pause, und dann siehst du jede Änderung sofort an der Anlage. Nur Laser und Nebel laufen nur beim Abspielen.")
    b.abschnitt("SHOW im Panel")
    b.bild("hauptpanel_show.jpg", "Das Hauptpanel während einer Show: oben SHOW, der AUTO-Knopf heißt SHOW, gesperrte Bereiche sind abgedunkelt.", crop=(0, 0, 800, 470), breite=0.86)
    b.text("Solange eine Show das Licht steuert, zeigt das Panel in der Betriebsart <b>SHOW</b> den Namen der Show, im Statusfeld steht <b>SHOW</b>, und der Knopf AUTO heißt <b>SHOW</b>.")
    b.punkte([
        "Die Musiksteuerung ruht dann ganz.",
        "<b>Gesperrt:</b> Szenen, Farben, Bewegung und Speed.",
        "<b>Frei:</b> die Schnelleffekte, der General Dimmer und die Gruppen-Regler.",
        "Ein Tipp auf <b>SHOW</b> beendet die Show und schaltet auf AUTO, auch am APC mini.",
    ])


def mixxx(b):
    b.kapitel("Shows aus Mixxx")
    b.text("Spielst du in Mixxx ein Lied, zu dem es eine Show gibt, übernimmt sie von selbst das Licht. Der Ton kommt aus Mixxx, der Browser muss nicht offen sein.")
    b.abschnitt("Einschalten")
    b.text("Einstellungen allgemein → Ausgabe → <b>Shows aus Mixxx automatisch starten</b> (Standard: aus). Einmalig am Mac den Starter neu anlegen und die App <b>Light-Butler Mixxx</b> neu starten:")
    b.text("`bash mac/mixxx_bridge/install_launcher.sh`")
    b.abschnitt("So wird das Lied erkannt")
    b.punkte([
        "Ist in Mixxx dieselbe MP3 geladen wie in der Show, erkennt der Pi sie von selbst, auch wenn sich die Tags geändert haben.",
        "Sonst wählst du im Editor bei den Eigenschaften der Show mit <b>Lied wählen</b> das Lied aus den Decks oder der Bibliothek. Dann müssen Titel und Länge (±1 s) passen.",
        "Das Lied braucht eine Analyse in Mixxx, sonst kennt der Pi seinen Titel nicht.",
    ])
    b.abschnitt("Was dann passiert")
    b.tabelle(["Situation", "Verhalten"], [
        ["<b>Im Lied</b>", "Die Show folgt dem Deck, auch bei Pitch, Sync und Sprüngen. Der Vorlauf aus Mixxx und der Licht-Versatz gelten auch hier."],
        ["<b>Mischen</b>", "Es läuft immer nur eine Show. Sie wechselt etwa 2 s, nachdem das andere Deck lauter geworden ist. Hat das andere Lied keine Show, übernimmt AUTO."],
        ["<b>Ende</b>", "Pause, leises Deck oder das Ende der Show schalten nach etwa 1,5 s auf AUTO."],
        ["<b>Knopf SHOW</b>", "Danach bleibt die Show für dieses Lied aus, bis ein anderes Lied gespielt wurde."],
        ["<b>Vorrang</b>", "Spielt gerade eine Show aus dem Browser mit <b>Licht an</b>, bleibt sie. Ein angehaltener Editor oder einer mit <b>Licht aus</b> hält nichts auf."],
        ["<b>Hakerl „startet aus Mixxx“</b>", "Damit schließt du eine einzelne Show aus."],
        ["<b>Kopien mit derselben MP3</b>", "Die zuletzt gespeicherte gewinnt. Nimm also bei Vorschlägen, die du nicht willst, das Hakerl weg."],
    ], [2.7, 7])
    b.warnung("Die Hakerl für Laser und Nebel gelten auch hier: Eine Show mit Laser-Clips startet dann von selbst, sobald das Lied hörbar spielt.")


def synchron(b):
    b.kapitel("Synchron bleiben")
    b.text("Der Browser spielt die Musik und gibt die Zeit vor. Der Pi rechnet daraus 40-mal pro Sekunde das Bild. Die Anzeige <b>Synchron</b> nennt die Abweichung in Millisekunden.")
    b.tabelle(["Anzeige oder Problem", "Bedeutung und Abhilfe"], [
        ["<b>Synchron</b> mit kleiner Zahl", "Alles in Ordnung."],
        ["<b>Eigene Uhr</b>", "Der Browser meldet sich nicht (WLAN weg, Seite zu). Die Show läuft nach der Uhr des Pi weiter und findet zurück, sobald er wieder da ist. Laser bleiben in dieser Zeit aus."],
        ["Licht läuft hörbar vor oder nach", "<b>Licht-Versatz</b> einstellen (Kapitel 12). Bluetooth-Lautsprecher brauchen etwa +150 bis +250 ms."],
        ["Rote Linie läuft hinter dem Ton her", "<b>Linie vorziehen</b> einstellen. Das ändert nur die Anzeige, nicht das Licht."],
    ], [3, 6.5])
    b.text("<b>Ton woanders:</b> Mit dem Schalter <b>Ton hier / woanders</b> auf der Seite Shows spielt der Browser nichts ab, und die Show läuft nach der Uhr des Pi. Dann musst du die Musik selbst zur selben Zeit starten.")


def einstellungen(b):
    b.kapitel("Einstellungen für den Showmanager")
    b.text("Die Einstellungen erreichst du über das Zahnrad im Hauptpanel. Die Schalter für den Showmanager stehen unter <b>Einstellungen allgemein → Ausgabe</b>.")
    b.bild("einstellungen_ausgabe.jpg", "Die Einstellungen für den Showmanager im Bereich Ausgabe.", crop=(0, 180, 800, 567))
    b.tabelle(["Einstellung", "Standard", "Bedeutung"], [
        ["<b>Showmanager: Licht-Versatz</b>", "0 ms", "Das Licht läuft der Musik so viele Millisekunden voraus, negativ hinterher."],
        ["<b>Shows aus Mixxx automatisch starten</b>", "aus", "Eine Show übernimmt das Licht, wenn ihr Lied in Mixxx hörbar spielt."],
        ["<b>Laser in Shows erlauben</b>", "aus", "Ohne das bleiben die Laser in Shows aus, der Rest läuft."],
        ["<b>Nebel in Shows erlauben</b>", "aus", "Ohne das kommen keine Nebelschübe."],
    ], [3.6, 1.3, 4.7])
    b.text("Unter <b>Einstellungen allgemein → Titelerkennung</b> steht außerdem <b>Liedtext zum laufenden Lied holen</b> (Kapitel 11).")
    b.text("Die <b>Strobe-Erlaubnis</b> gibst du im Hauptpanel. Die Show schaltet sie nie ein.")


def sicherheit(b):
    b.kapitel("Sicherheit")
    b.warnung("Diese Anlage hat Laser, Strobe, Nebel und starke Lichter, die Menschen gefährden können. Schnelles Blitzen kann Anfälle auslösen. Die Sperren helfen, sie ersetzen aber nicht deinen Blick in den Raum.")
    b.abschnitt("Was immer gilt")
    b.punkte([
        "<b>BLACKOUT</b> geht immer vor, auf beiden Seiten des Showmanagers und im Panel.",
        "Einzelne Laser- und Hazer-Kanäle sowie die Mode- und Reset-Kanäle lassen sich nicht programmieren. Laser und Nebel gibt es nur als eigene Clips. Die Szene Laser ruht während einer Show.",
        "Ohne Strobe-Erlaubnis sind höchstens <b>2 Blitze pro Sekunde</b> möglich, egal was programmiert ist, und die Strobe-Kanäle bleiben aus.",
        "Eine laufende Show endet mit dem Lied. Danach gilt wieder AUTO.",
    ])
    b.abschnitt("Laser")
    b.punkte([
        "Laser nur mit dem Hakerl <b>Laser in Shows erlauben</b>, Standard aus.",
        "Nur während die Musik wirklich läuft und sich die Zeitquelle meldet. Sofort aus bei Pause, Springen, Stop, Licht aus, BLACKOUT, FREEZE, BLINDER und wenn 0,6 s lang keine Meldung kommt.",
        "Die Software weiß nicht, wohin der Strahl zeigt und wer im Raum steht. Nie auf Personen oder in Augenhöhe richten.",
    ])
    b.abschnitt("Nebel")
    b.punkte([
        "Nebel nur mit dem Hakerl <b>Nebel in Shows erlauben</b>, Standard aus.",
        "Derselbe Weg und dieselben Grenzen wie der SMOKE-Knopf, höchstens 10 s am Stück, mit Mindestpause.",
        "Die Show schaltet die Maschine nie ein. Vorsicht Rauchmelder.",
    ])
    b.abschnitt("Vor dem ersten Einsatz einer Show")
    b.schritte([
        "Show einmal vollständig ohne Gäste abspielen.",
        "Prüfen, ob Laser-Clips dorthin zeigen, wo niemand steht oder sitzt.",
        "Strobe-Erlaubnis nur geben, wenn alle im Raum damit einverstanden sind.",
        "Bei Shows aus Mixxx daran denken, dass sie von selbst starten.",
    ])


def dateien(b):
    b.kapitel("Dateien und Sicherung")
    b.text("Jede Show ist ein Ordner auf dem Pi unter `~/lichtshow/shows/NAME`:")
    b.tabelle(["Datei", "Inhalt"], [
        ["`show.json`", "Spuren, Clips, Keyframes, Eigenschaften und Liedtext"],
        ["`audio.mp3`", "Die Musik"],
        ["`fixtures.json`", "Stand der Geräte beim Speichern, zum Nachsehen, wenn sich der Aufbau ändert"],
        ["`patterns.json`", "Die in dieser Show benutzten eigenen Muster"],
        ["`peaks.json`", "Die Wellenform"],
    ], [2.5, 7])
    b.punkte([
        "Gelöschte Shows liegen im Papierkorb: unten auf der Seite Shows aufklappen, dort Zurücklegen oder endgültig löschen.",
        "Pegelkurven von Stimme, Bass, Kick, Snare/Hi-Hat und Sonstigem liegen in `shows/_stems`, je MP3 eine Datei, wenn sie am Mac berechnet wurden. Sie wirken noch nicht aufs Licht.",
        "Das Cover des Liedes (aus der MP3 oder einem Bild im Ordner am Mac) steht in der Showliste und oben im Editor. Es liegt in `shows/_covers` und wird auf den Stick gesichert (`musik-backup/Light-Butler-Covers`).",
        "Die nächtliche Sicherung enthält die Shows, aber <b>nicht die MP3s</b>. Bewahre die MP3s also auch woanders auf.",
        "Geräteprofile sicherst du mit <b>Profil sichern</b> beim Gerät und liest sie unter <b>Geräte</b> mit <b>Profil laden</b> wieder ein.",
    ])


def fehler(b):
    b.kapitel("Wenn etwas nicht klappt")
    b.tabelle(["Was du siehst", "Woran es liegen kann", "Was du tun kannst"], [
        ["Musik läuft, das Licht bleibt bei AUTO", "<b>Licht aus</b> ist gewählt", "<b>Licht an</b> antippen"],
        ["Alles dunkel", "BLACKOUT ist aktiv oder der Master steht auf 0 %", "BLACKOUT lösen, Master-Zeile prüfen"],
        ["Ein Gerät leuchtet voll, obwohl es dunkel sein soll", "Ein Farb-Clip läuft ohne Dimmer", "Farb-Clip kürzen, oder auf der Spur Dimmer einen Clip oder Keyframe setzen"],
        ["Laser-Clip wirkt nicht", "Hakerl aus, oder die Show steht still", "<b>Laser in Shows erlauben</b> einschalten, mit Play prüfen"],
        ["Nebelschub kommt nicht", "Hakerl aus, Maschine aus oder kalt, Mindestpause nicht um", "Hakerl setzen, Maschine einschalten, Abstand vergrößern"],
        ["Blitze sind langsamer als programmiert", "Keine Strobe-Erlaubnis, dann gelten höchstens 2 pro Sekunde", "Erlaubnis im Panel geben, wenn es im Raum vertretbar ist"],
        ["Licht läuft vor oder nach", "Verzögerung im Ton, zum Beispiel Bluetooth", "Licht-Versatz einstellen (Kapitel 12)"],
        ["Anzeige „Eigene Uhr“", "Browser meldet sich nicht", "WLAN prüfen, Seite offen lassen"],
        ["Rasterlinien liegen neben dem Beat", "Tempo oder erster Schlag falsch geschätzt", "Beide Werte bei den Eigenschaften der Show korrigieren"],
        ["Keine Abschnitte, keine Cues", "Lied lag noch nie in einem Mixxx-Deck", "Lied einmal in ein Deck legen, oder <b>Lied wählen</b>"],
        ["Show startet nicht aus Mixxx", "Schalter aus, keine Analyse, Hakerl <b>startet aus Mixxx</b> weg, Titel oder Länge passen nicht", "Der Reihe nach prüfen (Kapitel 15)"],
        ["Falsche Show startet aus Mixxx", "Mehrere Kopien mit derselben MP3, die zuletzt gespeicherte gewinnt", "Bei den anderen das Hakerl wegnehmen"],
        ["Liedtext ohne Zeiten", "Länge des Eintrags passt nicht zur MP3", "Mit anderem Titel oder Interpret neu suchen"],
        ["Assistent meldet einen Fehler bei Claude", "Kein Internet, Schlüssel oder Guthaben fehlt", "Der Vorschlag entsteht offline, das Fenster nennt den Grund. Guthaben auf platform.claude.com prüfen"],
        ["Show versehentlich gelöscht", "Sie liegt im Papierkorb", "Seite Shows, unten Papierkorb aufklappen, Zurücklegen"],
        ["Der Editor fragt nach einem neueren Stand", "Es gibt einen automatisch gesicherten Stand", "Wiederherstellen, wenn du ungespeicherte Arbeit verloren hast"],
    ], [3, 3.3, 3.3])


def kurz(b):
    b.kapitel("Kurzübersicht: Tasten im Editor")
    b.tabelle(["Taste", "Wirkung"], [
        ["Leertaste", "Play, Pause"],
        ["Pos1", "Zum Anfang"],
        ["+ und −", "Hinein- und herauszoomen"],
        ["K", "Keyframe an der Abspielposition auf der gewählten Spur"],
        ["L", "Loop ein, aus"],
        ["Umschalt+L", "Loop entfernen"],
        ["Strg+S", "Speichern"],
        ["Strg+Z, Strg+Y", "Rückgängig, Wiederholen"],
        ["Strg+A", "Alles wählen"],
        ["Strg+C, Strg+X, Strg+V", "Kopieren, Ausschneiden, Einfügen an der Abspielposition"],
        ["Entf", "Löschen"],
        ["Pfeil rauf und runter im Feld", "Wert des Felds ändern"],
        ["Strg + Rad", "Zoomen"],
        ["Umschalt + Rad", "Waagrecht scrollen"],
        ["Umschalt + Klick", "Zur Auswahl dazu"],
    ], [3, 6.5])
    b.text("Am Mac wirkt die Befehlstaste wie Strg.")
