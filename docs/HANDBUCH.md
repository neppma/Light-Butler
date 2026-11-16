# Light-Butler – Benutzerhandbuch

Lichtsteuerung zur Musik für Partys

**Markus Nepp** · Stand: November 2026

Dieses Handbuch wurde mit Unterstützung von KI (Claude von Anthropic) erstellt.

## Überblick

**Light-Butler** steuert deine Lichtanlage automatisch zur Musik. Ein **Licht-Rechner** (Raspberry Pi, Windows-PC oder Mac) hört die Musik und schickt die Lichtdaten an alle Geräte. Du bedienst alles im **Web-Panel** am Handy, Tablet oder PC. Technische Einzelheiten stehen in der **Technischen Beschreibung** (Link oben).

![Systemschema: was läuft wo](/static/sm/systemschema.svg)

Das Systemschema zeigt, was auf welchem Rechner läuft. Zum Antippen findest du es unter **⚙** → **Software für andere Rechner** → **Systemschema und Downloads**.

**Die Teile der Anlage**

- **Mischpult:** liefert die Musik über ein USB-Audio-Interface an den Licht-Rechner.
- **Licht-Rechner mit Light-Butler:** hört die Musik, rechnet das Licht und zeigt das Web-Panel.
- **DMX-Geräte** (Moving Heads, Spider, Washes, Laser, Effektlichter, Nebelmaschine): über ein Art-Net-Gateway im Netzwerk oder einen DMX-USB-Adapter am Licht-Rechner.
- **WLED-LED-Streifen** und **Nanoleaf Light Panels** (beide optional): direkt über das Netzwerk.
- **Musik-Rechner** (optional, Mac oder Windows): mit der DJ-Software Mixxx, dem Light-Butler Helfer und deiner Musiksammlung.
- **MIDI-Eingabetasten** (optional): AKAI APC mini mk2 und ROLI LUMI Keys.
- **HomeMatic** (optional): für Raumlicht, Steckdosen und Nebel.

**Was die Software kann**

Light-Butler macht das Licht und auf Wunsch auch die Musik von allein. Du kümmerst dich um deine Gäste und die Party, nicht um die Technik.

**Licht live zur Musik**

- **AUTO:** Das Licht folgt der Musik ohne Eingriff. Es erkennt Tempo, Beat, Takt, Tonart, Stimmung und Phasen (Aufbau, Break, Drop), mit vier Stufen von Chillen bis Vollgas.
- **Licht-Stile je Genre** (Club, Party, Rock, Ruhig, Weihnachten), auch über die Gruppe im Tag.
- **Feine Wirkungen:** Helligkeit folgt der Lautstärke, Hi-Hat-Funkeln, Beat-Puls, Geräte der Reihe nach.
- **40 Szenen** mit Szenen-Editor und Sofort-Knöpfe: STROBE, WOW! (aufbauender Strobo), SMOKE (Nebel), FREEZE, BLINDER, BLACKOUT und Laser. Alle außer AUTO wirken nur, solange du sie drückst.
- **Titelerkennung** über Shazam: Titel und Interpret auch ohne DJ-Software, das Genre wählt den Licht-Stil.
- **Liedtexte** laufen live zur Musik im Panel mit.

**Showmanager**

- **Eigene Lichtshows und Lasershows** zu einer MP3, Spur für Spur in einer Zeitleiste.
- **Show-Assistent:** erstellt automatisch eine Show aus der Liedanalyse und dem Raumplan, auf Wunsch zusammen mit Claude.
- **Quick-Show** mit einem Knopfdruck aus der Musik-Datenbank oder dem Hauptpanel.
- **Pegelkurven** (Schlagzeug, Bass, Gesang getrennt) für genauere Shows.
- Shows **starten von selbst**, sobald das passende Lied in der DJ-Software läuft.

**Musik**

- **Auto-DJ:** Playlist nach Energie, Tempo und Tonart, Übergänge im Takt, das Licht folgt. Musik und Licht laufen dann ganz von allein.
- **Anbindung an DJ-Software (Mixxx):** Tempo, Beat, Tonart und Hotcues kommen genau aus der DJ-Software, Drops werden vorausgesagt.
- **Ton von jedem Programm** am Musik-Rechner (zum Beispiel Spotify, YouTube) über das Netzwerk.

**Musik-Datenbank und Datenpflege**

- **Datenbanken** für Lieder, Interpreten (mit Bildern und Lebenslauf) und Alben (mit Titelliste und Merkliste „Fehlt mir“).
- **Für jedes Lied** misst der Light-Butler Energie, Tonart und BPM. Du vergibst Sterne und setzt Favoriten.
- **Vorhören** ab dem Hauptteil, mit Cover und Liedtext.
- **Tags und Cover:** Der Light-Butler besorgt die CD-Cover und trägt die Tags ein (Titel, Interpret, Album, Jahr, Genre), mit Tag-Editor, Vorschlägen und Auto-Tagger. Fehlt ein Cover, erzeugt er eines.
- **Aufräumen:**
  - Genre-Editor und Gruppen-Manager,
  - Doppelte finden, beschädigte MP3s erkennen und reparieren, in MP3 umwandeln,
  - Import-Assistent, CD-Assistent, Ordner auflösen,
  - NAS oder Stick spiegeln, Stick sicher auswerfen.

**Anlage und Geräte**

- **DMX** über ein Art-Net-Gateway oder einen DMX-USB-Adapter, Art-Net auch als Eingang für andere Lichtprogramme.
- **WLED-LED-Streifen**, **Nanoleaf Light Panels** (auch ihre eigenen Effekte) und **HomeMatic** für Raumlicht und Nebel.
- **MIDI-Eingabetasten:** AKAI APC mini und ROLI LUMI Keys, frei belegbar.
- **Ableton Link:** Der Light-Butler gibt das Tempo an Link-Geräte im Netz weiter.
- **Fixture-Manager** für deine Geräte, **Raumplaner** (daraus auch Lichtwellen durch den Raum), DMX-Monitor und DMX-Debugger.

**Sicherheit und Betrieb**

- **Sperren** für Laser, Strobe und Nebel, ein Sicherheitshinweis bei jeder neuen Anlage.
- Läuft auf **Raspberry Pi, Windows-PC oder Mac**, auch gemischt.
- **Bedienung** am Handy, Tablet oder PC, auf Deutsch oder Englisch, mit eigener Übersetzungstabelle.
- **Sicherung** jede Nacht, dazu ein Notfall-Ordner mit allen Programmen auf dem Musik-Stick.
- **Zustand und Statistik** der Anlage auf eigenen Seiten.

## Erste Schritte

Der Light-Butler startet beim Einschalten des Licht-Rechners von selbst. Du brauchst nur einen Browser.

### Panel öffnen

1. Handy, Tablet oder PC ins Heimnetz bringen.
2. Im Browser die Adresse `http://<name-des-light-butler>:8080/` öffnen (oder die IP-Adresse des Licht-Rechners mit `:8080`).
3. Es gibt keine Anmeldung. Benutze das Panel nur im Heimnetz.

### Das Panel als App aufs Handy

1. Panel im Browser des Handys öffnen.
2. Im Menü des Browsers **Zum Home-Bildschirm** wählen.
3. Das Panel liegt jetzt als App mit dem Butler-Symbol auf dem Handy.

### In fünf Minuten startklar

1. Licht-Rechner, Art-Net-Gateway (falls vorhanden), Mischpult und Lichter einschalten. Nach etwa einer Minute ist der Licht-Rechner bereit.
2. Panel öffnen. Oben links blinkt das **Beat-Lamperl** im Takt, sobald Musik läuft.
3. **AUTO** ist der Normalfall: Das Licht folgt der Musik von allein.
4. Mit dem **General Dimmer** die Gesamthelligkeit einstellen.
5. **BLACKOUT** gedrückt halten schaltet alles aus, solange du drückst.
6. Die **Hinweiszeile** unten im Statusbereich warnt, wenn ein Gerät fehlt.
7. Der kleine **?** oben rechts öffnet dieses Handbuch. Am Handy findest du es im Menü **☰**.

### Sicherheitshinweis beim ersten Start

Bei einer neuen Anlage erscheint beim ersten Öffnen ein Fenster zu Strobe, Laser, Nebel, Ausgaben und Aufbau. Lies es und tippe auf **Verstanden**. Das gilt für die ganze Anlage und erscheint danach nicht wieder.

Eine neue Anlage startet mit **allen Ausgaben aus** und ohne Strobe-Erlaubnis. Schalte die Ausgaben unter **Verbindungen** erst ein, wenn nur dieser Light-Butler sendet, sonst kämpfen zwei ums Licht.

### Herunterfahren

Am Raspberry Pi fährt der rote Knopf **⏻** oben rechts den Licht-Rechner sauber herunter.

1. **⏻** antippen. Im Fenster stehen Knöpfe zum Ausschalten der HomeMatic-Steckdosen, die noch an sind.
2. Mit **Herunterfahren** bestätigen. Das Licht und die Laser gehen sofort aus.
3. Etwa 30 Sekunden warten, bis die grüne LED am Pi nicht mehr blinkt, dann den Strom trennen.

## Die Hauptseite

Die Hauptseite ist nur zum Bedienen da. Sie ist in grau hinterlegte Bereiche gegliedert. Von oben nach unten:

### Der Kopf

| Zeile | Was du siehst |
| --- | --- |
| 1 | **Beat-Lamperl**, **BPM**, das **Statusfeld** und runde Knöpfe: Herz (**Zustand**), CD (**Auto-DJ**), Datenbank (**Musik-Datenbank**), Balken (**Statistik**), **⚙** (**Einstellungen**), **?** (Hilfe) und **⏻** |
| 2 | Betriebsart, Stufe in Worten (**Chillen**, **Groove**, **Party**, **Vollgas**), Stimmung, Tonart, Takt und ein kleines Pegelmeter des Audio-Eingangs |
| 3 | Lied aus Mixxx oder dem Auto-DJ: Titel, Energiestufe, Genre, Restzeit und die nächsten Ereignisse, zum Beispiel „Drop 5,1 s“ |
| 4 | **Liedverlauf**: die Lautstärke des Liedes als Kurve mit Aufbau, Break, Drops und Hotcues, nur zum Ansehen |

- Das **Statusfeld** zeigt, was gerade passiert: zum Beispiel **DROP !**, **AUFBAU**, **BREAK**, **STILLE**, **STROBE** oder **LASER AKTIV**.
- Ein Tipp auf Lamperl oder BPM öffnet das **Tempo-Fenster**: **÷ 2**, **× 2**, **−1**, **+1**, **TAP im Takt** und **Auto**. Ein Tempo von Hand wirkt nur auf Szenen und WOW!.

### AUTO und manuell

- **AUTO an** (orange, nach dem Start): Das Licht läuft auf Autopilot. Farbe, Licht-Mix, Bewegung, Ziele, Beam, Szenen und Effektband sind gesperrt. Orange Rahmen zeigen, was gerade läuft.
- **AUTO aus** (manuell): Alle Knöpfe sind frei. Was markiert war, bleibt deine Auswahl. Farbe, Bewegung und Speed sind dann **Vorgaben**: Das Licht läuft weiter mit der Musik, nur eben in deiner Farbe oder Bewegung.
- **AUTO wieder an** löscht alle Vorgaben von Hand.
- Immer frei bleiben die Sofort-Knöpfe, **Blitze/s**, der **General Dimmer** und die Gruppen-Regler.

### Sofort-Knöpfe

Alle außer AUTO sind **Taster**: Sie wirken nur, solange du drückst.

| Knopf | Wirkung |
| --- | --- |
| AUTO | Autopilot ein und aus (der einzige Schalter) |
| STROBE | alle Lichter blitzen |
| WOW! | aufbauender Strobo, Loslassen löst einen Drop aus |
| BLINDER | alles mit voller Helligkeit |
| FREEZE | Licht und Bewegung bleiben stehen, Laser sofort aus |
| BLACK OUT | alles aus, auch Laser und Nebel |
| SMOKE | Nebel, höchstens 10 Sekunden am Stück |

- Bricht die Verbindung ab (Handy gesperrt, WLAN weg), lässt der Light-Butler einen gedrückten Knopf nach 1,5 Sekunden selbst los.
- Darunter wählst du die **Blitze/s** (1 bis 10). Ohne Strobe-Erlaubnis sind die schnellen Stufen abgedunkelt.
- **General Dimmer** stellt die Gesamthelligkeit ein. **Gruppen ▾** klappt je Lichtgruppe einen eigenen Regler auf (zum Beispiel Spider, Washes, Moving Head, Ambiente, Nanoleaf).

### Speed und Stil

- **Speed:** **Low**, **Med** oder **Hot** legt die Intensität fest und bestimmt das Tempo von Licht-Mix und Bewegung. Nochmal antippen = wieder nach der Musik.
- **Stil:** **Weihnachten**, **Club**, **Party**, **Rock** oder **Ruhig** färbt das Licht in AUTO. Bei **Auto** kommt der Stil aus dem Genre des Liedes, ein Stil von Hand geht vor.

### Farbe und Licht-Mix

- **Farbe:** eine Farbe antippen = nur diese Farbe. Mehrere Farben antippen = sie wechseln sich bei jeder Phrase und jedem Drop ab. Nochmal antippen nimmt eine Farbe weg. Weiß und UV gehen nur einzeln.
- **Licht-Mix:** ein Muster für alle Lichter, zum Beispiel **Disco**, **Carousel**, **Sparkle**, **Static** (Farben bleiben stehen), **Chase-Out**, **Chase-In**, **Scanner** oder **Rainbow**. Nochmal antippen wählt ab.

### Bewegung, Ziele und Beam

- **Bewegung** für Moving Head und Spider: **Float**, **Center**, **Random**, **Sweep**, **Circle**, **Tilt**, **Pan**, **Swim**. Nochmal antippen gibt frei. Feinregler unter Bewegung und Licht-Mix stellen Fächer, Tempo, Versatz und Größe ein.
- **Ziele** richten Moving Head und Spider auf einen festen Platz, zum Beispiel **Couch**, **Table**, **Door**, **Bar**. Nur diese Geräte leuchten dann weiß. Nochmal antippen (oder **Free**) beendet das.
  - Eigenes Ziel: **✎ Bearbeiten**, dann **+ Target**, Name eingeben, mit den Reglern ausrichten, **Speichern**.
- **Beam** steuert den Strahl eines Moving Heads (Gobo, Zoom, Roll, Prisma). **Auto** = die Show macht das selbst, sonst gilt deine Einstellung, bis du **Von Hand** ausschaltest.

### Szenen und Effektband

- Am Ende stehen die **Szenen** und das **Effektband**: ein Knopf je Preset des Effekt-Streifens, nochmal antippen = wieder automatisch. **♫** = das Preset reagiert selbst auf die Musik.

### Die Hinweiszeile

Unten im Statusbereich steht immer die Hinweiszeile. Ist alles in Ordnung, steht dort „✓ Alle Geräte erreichbar“.

- **rot:** ein Gerät ist nicht erreichbar.
- **orange:** eine Ausgabe ist abgeschaltet. Antippen schaltet sie ein.
- **blau:** Art-Net von außen, ein offener Neustart oder **SHOW LÄUFT**. Antippen führt hin.
- **⏻ davor:** das Gerät hängt an einer HomeMatic-Steckdose, die aus ist. Antippen schaltet sie nach einer Rückfrage ein.

## Szenen und Effekte

### Szenen wählen

1. Eine Szene antippen: Sie hält ein festes Lichtbild.
2. Dieselbe Szene nochmal antippen: wieder abgewählt, das Licht läuft wieder nach der Musik.
3. Für **dauerhaft dunkel** (Pause, Aufräumen) die Szene **All off** nehmen.

Es gibt 40 Standardszenen, dazu Spezialszenen wie **All off**, **RESET**, **Laser** und die Ziel-Szenen. Ist eine Szene aktiv, ändern Farbe, Bewegung und Licht-Mix diese Szene.

### Szenen bearbeiten

1. Über den Szenen **✎ Bearbeiten** antippen.
2. Eine Szene antippen. Einstellbar sind Name, Licht-Mix, Tempo, Farbe, Bewegung, Helligkeit, welche Lichter mitmachen und ein Preset.
3. Mit **+** legst du eine neue Szene an. Kopieren, verschieben und löschen gehen ebenso.
4. **Szenen auf Standard zurücksetzen** holt die ursprünglichen Szenen zurück.

### Szenen-Automatik

Auf Wunsch wählt die Show in AUTO ab und zu selbst kurz eine Szene (**Einstellungen (Auto-Erkennung)** → **Szenen-Automatik**, Standard aus). Vorne in deiner Liste stehen ruhige, hinten wilde Szenen. Laser- und Ziel-Szenen wählt sie nie.

### Strobe-Erlaubnis

Schnelles Blitzen kann bei empfindlichen Menschen **epileptische Anfälle** auslösen. Darum blitzt es ohne Erlaubnis höchstens 3-mal pro Sekunde, und es gibt keinen Strobo-Burst beim Drop und keinen Einzel-Strobe.

- Einschalten: **⚙** → **Einstellungen (Auto-Erkennung)** → **Weiße Blitze und Strobo** → ganz oben **Strobe-Erlaubnis**.
- Schalte sie nur ein, wenn du weißt, dass es für alle Gäste in Ordnung ist, und nimm sie danach wieder zurück.

### Laser in Kürze

- Laser laufen nur in der Szene **Laser** und, wenn du es erlaubst, in Laser-Clips einer Show.
- Beim Start der Szene gehen alle anderen Lichter aus. Bei Freeze, Blackout, Stille und Szenenwechsel sind die Laser sofort aus.
- Die **Laser-Betrieb**-Einstellung (Gruppe **Laser**) wählt, ob der Light-Butler die Laser steuert oder sie zur Musik ihr eigenes Programm spielen.
- **Richte Laser nie auf Personen oder in Augenhöhe.**

### Nebel in Kürze

1. **SMOKE** gedrückt halten: Nebel, solange du drückst, höchstens 10 Sekunden.
2. Danach gilt eine Pause von 20 Sekunden. Der Knopf zeigt die Restzeit.
3. Hängt die Nebelmaschine an einer HomeMatic-Steckdose, schaltet der erste Druck sie ein. Das Panel fragt vorher nach den **Rauchmeldern**. Nebel gibt es erst nach der Aufheizzeit.

Die kleine Zeile auf dem Knopf zeigt den Zustand: **aus · tippen**, **heizt**, **bereit**, Restzeit oder **Pause**. Die Nebelmaschine läuft nie von allein.

## Showmanager

Mit dem Showmanager programmierst du eine eigene Lichtshow zu einer MP3 und spielst sie im Takt ab. Du erreichst ihn über das Menü **☰** → **Showmanager** (Seite `/shows`). Eine ausführliche Anleitung mit Bildern lädt der runde Knopf oben rechts als PDF herunter (nur auf Deutsch).

### Show abspielen

1. Show in der Liste antippen.
2. **▶** drücken: Die Musik startet im Browser, das Licht folgt ihr.
3. **⏸** hält an, **⏹** beendet die Show und gibt das Licht an AUTO zurück, **⏮** springt zum Anfang.

| Schalter | Bedeutung |
| --- | --- |
| **Licht an / aus** | aus: nur Musik, das Licht bleibt bei AUTO |
| **Ton hier / woanders** | woanders: der Browser spielt nichts ab, die Show läuft nach der Uhr des Licht-Rechners |
| **BLACKOUT** | alles dunkel, geht immer vor |

Solange eine Show läuft, heißt der Knopf AUTO **SHOW**, ein Tipp darauf beendet sie. BLACKOUT, BLINDER, FREEZE und der General Dimmer wirken weiter. Läuft das Licht vor oder nach dem Ton, stell bei den Eigenschaften der Show den **Licht-Versatz** ein.

### Neue Show anlegen

1. In der Übersicht **+ Neue Show** antippen.
2. Eine **MP3** wählen. Der Browser rechnet die Wellenform und schätzt das Tempo.
3. Ein Gerät oder eine Gruppe aus der linken Leiste in die Zeitleiste ziehen. Es entstehen Spuren wie Dimmer, Farbe und Bewegung.
4. Unter **Muster** ein Muster auf eine Spur ziehen und unten einstellen (Startzeit, Dauer, Geschwindigkeit, Fade In, Fade Out und mehr).
5. Doppelt auf eine Spur tippen setzt einen **Keyframe**. Zwischen Keyframes wird übergeblendet.
6. **Speichern** (Strg+S). Ein Punkt am Knopf zeigt ungespeicherte Änderungen.

### Der Editor in Grundzügen

- **Zoomen** mit Strg + Mausrad, zwei Fingern oder den Tasten + und −. **Springen** durch Antippen des Lineals.
- **Loop:** im Lineal einen Bereich ziehen, **⟳** schaltet ihn ein und aus, **⟳✕** entfernt ihn.
- **Rückgängig** und **Wiederholen** mit ↶ ↷ (Strg+Z, Strg+Y). **Leertaste** = Play und Pause.
- Die Zeile **Master** regelt die Helligkeit aller Geräte, zum Beispiel zum Ausblenden am Liedende.
- **Licht beim Programmieren:** **▶** geht ans echte Licht. Mit **Licht aus** hörst du nur im Browser.

### Show-Assistent

Der Knopf **Assistent** baut aus Lied und Geräten einen fertigen Vorschlag. Deine Show bleibt unverändert, der Vorschlag kommt als Kopie (ist die Show noch leer, direkt hinein). Jeder weitere Klick macht einen neuen Vorschlag.

1. Im Editor **Assistent** antippen.
2. Stil und Stärke (ruhig bis wild) prüfen, Hakerl für Laser, Nebel, Blitze und Bewegung setzen.
3. Wählen, wer entwirft: der Assistent nach festen Regeln (kostenlos, offline) oder auf Wunsch **Claude** (braucht Internet und einen eigenen API-Schlüssel, kostet ein paar Cent bis gut einen Euro).
4. Vorschlag erstellen lassen und danach fein abstimmen.

Der Assistent schaltet nie eine Erlaubnis ein. Prüfe den Vorschlag vor dem ersten Einsatz, besonders den Laser. Mit gespeichertem **Raumplan** werden die Vorschläge besser (zum Beispiel Lichtwellen durch den Raum).

### Quick-Show

- In der **Musik-Datenbank** legt **⚡ Quick** bei einem Lied mit Pegelkurven in einem Schritt eine fertige Show an: MP3 holen, Wellenform, Cue-Punkte, Liedtext und Assistent.
- Im **Hauptpanel** erscheint **⚡ Quick-Show**, wenn in Mixxx ein solches Lied ohne Show spielt. Die fertige Show startet einmal mit dem laufenden Lied.

### Shows automatisch starten

1. **⚙** → **Einstellungen allgemein** → **Ausgabe** → **Shows aus Mixxx automatisch starten** einschalten.
2. Spielst du in Mixxx ein Lied mit Show, übernimmt sie das Licht. Der Browser muss dafür nicht offen sein.
3. Wird ein Lied nicht erkannt, wählst du im Editor bei den Eigenschaften mit **Lied wählen** das passende Lied.

### Laser und Nebel in Shows

Beides geht nur mit Hakerl unter **Einstellungen allgemein** → **Ausgabe** (**Laser in Shows erlauben**, **Nebel in Shows erlauben**, Standard aus). Laser gehen bei Pause, Stop und Springen sofort aus, die Show schaltet die Nebelmaschine nie ein.

## Musik-Datenbank

Der runde Knopf mit dem Datenbank-Symbol (am Handy im Menü **☰**) öffnet die Seite `/musik`: alle Lieder deiner Sammlung. Die Liste kommt vom Musik-Rechner, aus Mixxx und aus deinem Musikordner. Aufs Licht wirkt die Seite nicht.

### Liste, Suchen und Filtern

- **Suchen:** ins Suchfeld tippen, mehrere Wörter gehen (Titel, Interpret, Album, Genre, Ordner …).
- **Filter** zum Beispiel nach Energie, Sternen, „ohne Cover“, „hinzugefügt“ (heute, gestern, seit …), „über 10 min“ oder „nicht MP3“.
- **Sortieren:** Spaltenkopf antippen, nochmal für die andere Richtung.
- **Ansicht:** **Liste** oder gruppiert nach Interpreten, Alben, Genres, Gruppen, Energie oder Kisten/Listen.
- **CSV** lädt die gefilterte Liste für eine Tabellenkalkulation herunter, **Export** kopiert die gefilterten Lieder in einen Ordner (zum Beispiel auf einen Party-Stick), ohne etwas zu überschreiben.

Steht oben ein roter Hinweis, ist der Musik-Rechner nicht erreichbar oder der Musikordner fehlt (Stick nicht angesteckt). Dann gehen Vorhören, Tags und Cover nicht.

### Vorhören

1. **▶** bei einem Lied antippen. Die Musik kommt direkt vom Musik-Rechner.
2. Unten erscheint eine Leiste mit Pause, Position zum Springen, Zeit und Lautstärke. **✕** schließt sie.
3. Mit dem Haken **Ab Hauptteil** beginnt das Lied dort, wo man es gut beurteilen kann, zum Beispiel beim Refrain.

### Energie, Tonart und BPM

Zu jedem Lied zeigt die Liste **Energie** (1 bis 9), **Tonart** und **BPM**, aus der DJ-Software, aus der Datei oder vom Light-Butler selbst gemessen. Geschätzte Werte tragen eine Wellenlinie (**E6~**), „?“ heißt nicht bestimmbar. Details: Technische Beschreibung.

### Sterne und Favoriten

- **Sterne:** in der Spalte **★** auf den 1. bis 5. Stern tippen. Derselbe Stern noch einmal = keine Sterne. Sterne aus Mixxx kommen mit.
- **Favoriten:** das **Herz** bei Liedern, Alben, Interpreten und Genres antippen. Ein halbes Herz heißt: Lied eines Lieblings-Albums oder -Interpreten. Lieder mit 5 Sternen zählen als Favorit.
- Die Seite **♥ Favoriten** zeigt alles, was du gemerkt hast. Im Hauptpanel steht das Herz neben dem Cover des laufenden Liedes.

### Interpreten und Alben

- **👤 Interpreten-Seite:** alle Interpreten als Kacheln mit Bild. Antippen zeigt ihre Lieder, Alben und auf Wunsch einen Lebenslauf. Bilder holt der Light-Butler auf Knopfdruck aus dem Internet (nur der Name geht hinaus).
- **💿 Alben-Seite:** alle Alben als Kacheln mit Cover. Antippen zeigt die Lieder nach Track. Auf Wunsch holt der Light-Butler die Titelliste des Albums und zeigt, welche Titel dir fehlen.

### Fehlt mir

Fehlt ein Titel eines Albums oder findet die Suche nichts, merkst du das Lied mit **+ merken**. Die Seite **Fehlt mir** zeigt die Merkliste, Lieder aus deiner Sammlung verschwinden daraus von selbst.

### Tag bearbeiten und Cover

1. **Tag** bei einem Lied antippen. Das Fenster **Tag bearbeiten** zeigt alle Felder der MP3.
2. Felder ändern (Titel, Interpret, Album, Jahr, Genre, Gruppe …). **Vorschläge** sucht passende Angaben im Internet, Shazam erkennt das Lied am Ton.
3. Cover einfügen, entfernen oder mit **Cover erzeugen** selbst eines machen.
4. Speichern. Geschrieben wird nur, was du geändert hast, die Musik bleibt gleich.

### Weitere Knöpfe je Lied

- **+ Show** legt zu einem Lied eine neue Show an und öffnet den Editor.
- **Als Nächstes spielen** (CD mit ▶) setzt das Lied im Auto-DJ direkt hinter das laufende.
- **🗑** legt die Datei am Musik-Rechner in den Papierkorb (mit Rückfrage).
- **→ MP3** wandelt eine Datei, die keine MP3 ist, in eine MP3 um. Das Original bleibt.

## Datenpflege

Der Knopf **🧹 Datenpflege** in der Musik-Datenbank zeigt ein Rezept zum Aufräumen, von oben nach unten: **grün** = nichts zu tun, **blau** = nächster sinnvoller Schritt, **Öffnen** führt zum Werkzeug. Geschrieben wird erst nach deinem Klick, nie wird eine Datei überschrieben.

### Die Schritte

- **Sicherung:** vor dem Aufräumen die Sammlung sichern, dann selbst abhaken.
- **Dateien prüfen:** findet Datenmüll (Reste wie Thumbs.db), leere Ordner und kurze Stücke mit geratenen Werten. Alles geht in den Papierkorb, nichts wird gleich gelöscht.
- **Alles in MP3:** zeigt Dateien, die keine MP3 sind, zum Umwandeln mit **→ MP3**.
- **Doppelte:** sucht doppelte Lieder und schlägt vor, welche Datei bleibt. Du löschst je Gruppe oder tippst **Alle behalten**.
- **Mixxx aufräumen:** fehlende Titel in Mixxx entfernen und die Bibliothek neu einlesen. Das machst du in Mixxx und hakst es selbst ab.
- **Titel bereinigen:** findet Titel mit Tracknummer vorne („01 - Lied“). Grün = sicher, orange = bitte prüfen. **So lassen** merkt sich Ausnahmen.
- **Titel = Interpret:** findet Lieder, bei denen Titel und Interpret gleich sind. Der Assistent macht Vorschläge, du entscheidest.
- **Tag-Vorschläge und Cover:** der **Auto-Tagger** sucht im Hintergrund Angaben und Cover, auf der Seite **Tag-Vorschläge** übernimmst oder verwirfst du sie.
- **Geänderte → Mixxx:** zeigt Lieder, deren Tags du geändert hast. In Mixxx dann „Metadaten aus Datei importieren“ wählen.
- **Dateinamen:** Lieder, deren Dateiname nicht zu den Tags passt, mit Vorschlag „Interpret - Titel“ zum Umbenennen.
- **Energie eintragen:** schreibt die geschätzte Energiestufe in MP3s ohne Stufe.
- **Genres:** zählt alle Genres, schlägt Zusammenlegungen vor und schreibt nur das Genre-Feld. Der Licht-Stil geht mit.
- **Beschädigte Dateien:** Dateien, die sich nicht abspielen lassen. MP3s lassen sich oft **reparieren**, das Original kommt in den Papierkorb.
- **Lose Album-Lieder:** Lieder eines Albums, die neben dem Album-Ordner liegen, verschiebt das Werkzeug auf Wunsch in den Ordner. Jeder Schritt lässt sich zurücknehmen.

### Werkzeuge mit Zahnrad ⚙

- **Neue Musik importieren:** neue Lieder in den Wartebereich `musik-import` neben dem Musikordner legen, dann **Einsortieren**: das Werkzeug vergleicht mit der Sammlung.
- **CD-Assistent:** für ganze CDs mit falschen oder fehlenden Tags. Trackliste einfügen, der Assistent ordnet die Lieder zu und trägt die Tags ein.
- **Ordner umbenennen:** einen Ordner umbenennen oder verschieben, Unterordner gehen mit. Mixxx übernimmt die neuen Pfade.
- **Ordner auflösen:** einen Oberordner, den du früher nur zum Auswählen angelegt hast, in einen anderen einsortieren, auf Wunsch mit Gruppe im Tag.
- **Tags aus Dateinamen:** für Lieder ohne Tags. Ordner und Muster wählen (zum Beispiel „Interpret - Titel“), Vorschau prüfen, **Eintragen**.
- **Gruppen:** der Gruppen-Manager für das Feld Gruppe im Tag (zum Beispiel eine Partyrichtung). Lieder anhaken, verschieben, zusätzlich zuordnen oder herausnehmen.
- **Spiegeln:** bringt ein Laufwerk auf den Stand eines anderen (zum Beispiel „Stick → NAS“), immer zuerst mit Probelauf.
- **Vorab-Läufe:** holt im Hintergrund für die ganze Sammlung Liedtexte, Cue-Punkte, Cover und Pegelkurven. Anhalten und weitermachen geht jederzeit.

### Rund um den Stick

- **⏏ Stick auswerfen** (Musik-Datenbank und **Verbindungen**): hält alle Arbeiten am Stick an und wirft ihn sicher aus.
- **Ausgeschlossene Ordner** (unter **Verbindungen**, beim Musikordner): je Zeile ein Ordner, den der Light-Butler nie liest und nie verändert.

## Auto-DJ

Der **Auto-DJ** stellt eine Playlist aus deiner Sammlung zusammen und legt sie mit Übergängen im Takt auf. Der runde Knopf mit der **CD** öffnet ihn in einem eigenen Fenster, damit die Musik beim Blättern im Panel weiterläuft.

### Playlist erstellen

1. **Event einrichten** öffnen. In fünf Schritten wählst du Anlass, Publikum, Musik (Genres, Gruppen, Kisten), Beginn, Länge und Energie.
2. **Playlist nach Regeln** baut die Playlist kostenlos ohne Internet: Energie und Tempo steigen, Tonarten passen zusammen, derselbe Interpret kommt nicht kurz hintereinander.
3. Oder **Mit Claude vorschlagen**: Claude wählt passende Lieder nach Thema und Publikum (braucht Internet und den API-Schlüssel, ein paar Cent).
4. **Neu würfeln** macht eine andere Playlist mit denselben Wünschen.
5. **Merken** hebt eine Playlist auf, **Laden** holt sie wieder.

### Abspielen

1. Im **Mischpult** auf Play tippen. Deck A und Deck B zeigen Cover, Titel, BPM und Restzeit.
2. Der Auto-DJ blendet vor dem Ende über und gleicht das Tempo an. **Jetzt mixen** wechselt früher.
3. **Übergang** wählt die Art: passend, weich, Filter, Echo oder Bremse.
4. In der Playlist spielt **▶** sofort ab einem Lied, **⤴** setzt es als Nächstes, **↑ ↓** stellt um, **✕** nimmt es heraus.

Die Musik kommt vom Musik-Rechner. Am besten spielst du den Auto-DJ im Browser am Musik-Rechner und gibst den Ton von dort ins Mischpult. Lass das Fenster offen.

### Das Licht folgt

Mit dem Häkchen **Licht folgt dem Auto-DJ** (Standard an) arbeitet das Licht wie mit Mixxx, oben steht **Auto-DJ Deck A** oder **B**. Laser, Strobe und Nebel bleiben hinter ihren Freigaben.

## DJ-Software und Musik-Rechner

### Mixxx

Mit der DJ-Software **Mixxx** am Musik-Rechner kennt der Light-Butler Tempo, Beat und Tonart genau und weiß schon vor dem Drop, dass er kommt.

1. Mixxx **immer über die App „Light-Butler Mixxx“** starten (unter Windows die gleichnamige Verknüpfung). Sie startet Mixxx und die Brücke zum Light-Butler.
2. Lied laden und spielen. Die Mixxx-Zeile im Panel zeigt Titel, Restzeit und die nächsten Ereignisse.
3. Fehlt die Analyse eines Liedes, rechnet die Brücke sie in wenigen Sekunden. Nach und nach analysiert sie im Hintergrund die ganze Bibliothek.
4. Damit die Vorhersage auch das Licht steuert: **⚙** → **Einstellungen (Auto-Erkennung)** → **Mixxx-Vorhersage** → **Vorhersage fürs Licht nutzen** auf „Licht folgt“ stellen.

- In der Gruppe **Mixxx-Vorhersage** steht auch die Tabelle **Genre-Stile**: Dort gibst du jedem Genre einen Licht-Stil.
- Ohne Mixxx: Schalter **Mixxx verwenden** (**Einstellungen allgemein** → **Titelerkennung**) ausschalten. Das Panel blendet dann alles aus, was nur mit Mixxx geht.

### Light-Butler Helfer

Der **Helfer** ist ein kleines Hintergrundprogramm am Musik-Rechner, auch ohne Mixxx: Er leitet APC und LUMI weiter, schickt den Ton und hält die Musik-Datenbank aktuell.

### Ton vom Musik-Rechner

Läuft die Musik am Musik-Rechner (zum Beispiel Spotify, YouTube), schickt der Helfer eine Kopie des Tons über das Netzwerk.

1. Am Mac einmal den Audio-Treiber BlackHole installieren (dein Mac-Passwort tippst du selbst):

```
brew install blackhole-2ch
```

2. Im Programm **Audio-MIDI-Setup** ein **Gerät mit mehreren Ausgängen** anlegen: deine Lautsprecher und „BlackHole 2ch“ anhaken, überall dieselbe Rate (44100 Hz).
3. In den Systemeinstellungen unter **Ton → Ausgabe** dieses Gerät wählen.
4. Fragt macOS nach dem **Mikrofon-Zugriff** für den Helfer: erlauben.
5. Im Panel unter **Audio-Eingang** den Eingang **Musik-Rechner (Netzwerk)** wählen.

An einem Windows-Musik-Rechner nimmt der Helfer VB-Cable, Stereomix oder Line-In.

### Titelerkennung

Ohne Mixxx erkennt der Light-Butler Titel und Interpret über Shazam (nur am Raspberry Pi, braucht Internet): **Einstellungen allgemein** → **Titelerkennung** → **Titel und Interpret erkennen**. Das Genre wählt dann den Licht-Stil.

### Installation am Musik-Rechner

- **Mac:** **⚙** → **Software für andere Rechner** → **Mac: Mixxx-Brücke und Helfer (ZIP)** laden, entpacken und im Ordner im Terminal ausführen:

```
bash install_mac.sh
```

- Das Skript fragt nach der Adresse des Light-Butler, richtet die App „Light-Butler Mixxx“ und den Helfer ein und sagt am Ende, was noch von Hand zu tun ist.
- **Windows:** Paket **Windows: Musik-Rechner (ZIP)** laden, entpacken und in der PowerShell ausführen:

```
powershell -ExecutionPolicy Bypass -File install_windows_musik.ps1
```

- Für Mixxx unter Windows brauchst du einmal das kostenlose Programm loopMIDI mit dem Anschluss „Light-Butler“. Details: Technische Beschreibung.

## MIDI-Controller

### AKAI APC mini mk2

Der APC mini bedient die Show mit Pads, Tasten und Fadern. Die LEDs zeigen den Zustand, auch wenn du im Panel etwas änderst.

1. Den APC per USB am Licht-Rechner anstecken, oder am Musik-Rechner (dann leitet der Helfer oder die Mixxx-App ihn weiter).
2. Unter **⚙** → **Einstellungen allgemein** → **MIDI-Controller** muss „verbunden“ stehen.
3. In Mixxx den APC **nicht** als Controller aktivieren, sonst reagiert auch Mixxx auf die Tasten.

| Bereich | Belegung |
| --- | --- |
| Pads Reihe 1 | AUTO, Strobe, Wow, Blinder, Freeze, Blackout, Smoke, BPM |
| Pads Reihe 2 | Bewegung |
| Pads Reihe 3 | Licht-Mix |
| Pads Reihe 4 bis 8 | Szenen 1 bis 40 |
| Tasten rechts | Low, Med, Hot, Laser-Szene, TAP |
| Tasten unten | vier Ziele, Laser, Hauptseite, Farbseite |
| Fader 1 bis 8 | Gruppen-Helligkeit, Fader 9 = General Dimmer |

- **SHIFT** gedrückt halten: Die Pads zeigen die Farben.
- Ein Fader wirkt erst, wenn du ihn an den aktuellen Wert herangefahren hast. So springt nichts.

### ROLI LUMI Keys

Der LUMI ist eine zweite Bedienung neben dem APC: Auf der Klaviatur wählst du Farben, Bewegung, Licht-Mix und Szenen. Laser, Strobe und Nebel gibt es dort bewusst nicht.

1. Den LUMI per USB an den Musik-Rechner stecken.
2. Helfer oder App „Light-Butler Mixxx“ starten. Unter **MIDI-Controller** steht dann „ROLI Lumi: verbunden“.
3. Die Oktav-Tasten am LUMI wirken wie ein Seitenwechsel.

### Belegung ändern

1. **⚙** → **APC mini · Belegung** oder **ROLI Lumi · Belegung** öffnen. Du siehst das Gerät gezeichnet, gedrückte Tasten blitzen auf.
2. **Umbelegen** antippen, dann eine Taste antippen oder am Gerät drücken.
3. Die neue Belegung aus der Liste wählen. Sie wirkt sofort.
4. **Standard wiederherstellen** löscht alle eigenen Änderungen.

Für die Tastenfarben am LUMI lädst du auf der Seite **ROLI Lumi · Belegung** das **Lumi-Programm** herunter und ziehst es im ROLI Dashboard auf den LUMI.

## Geräte und Anlage

### Fixtures

Die Seite **Fixtures** (**⚙** → **Fixtures**) zeigt jedes Gerät mit Name, Nummer und DMX-Adresse. Aufklappen zeigt alle Kanäle mit Beschreibung und Live-Wert.

1. **Bearbeiten** einschalten.
2. Name, Nummer, DMX-Adresse, Gruppe oder Ziel-IP (bei WLED) ändern.
3. **+ Fixture** legt ein neues Gerät aus einem vorhandenen Typ an. Überschneiden sich Adressen, warnt das Panel.
4. Für ein ganz neues Gerät legst du unter **Gerätetypen** einen eigenen Typ an, am besten mit **Kopie von** einem ähnlichen.
5. Name und Beschreibungen gelten sofort. Adresse, Gruppe, neue und entfernte Geräte nach einem Neustart: Tippe auf **Jetzt neu starten** (das Licht ist etwa 5 Sekunden aus).

- Die Gruppe **Ambiente** macht ein Farbgerät ruhig: weiche Übergänge, ohne Beat und ohne Blitze, zum Beispiel für ein Arbeitslicht an der Bar.
- **Entfernen** nimmt ein Gerät heraus, **Entfernte Fixtures** holt es zurück, **Änderungen verwerfen** setzt alles zurück.

### Raumplan

Auf der Seite **Raumplan** (Menü **☰**) zeichnest du ein, wo deine Geräte im Raum stehen. Aufs Licht wirkt der Plan nicht direkt, aber der Show-Assistent nutzt ihn.

1. Raumgröße in Metern eintragen.
2. Geräte aus **Noch nicht im Plan** antippen und an ihren Platz ziehen.
3. Ein Gerät antippen, um Lage, Blickrichtung und Länge (bei LED-Streifen) genau einzustellen. **+ Stück** fügt einem Streifen ein weiteres Stück hinzu.
4. **Speichern**.

### Verbindungen und Ausgänge

Unter **⚙** → **Einstellungen allgemein** → **Verbindungen** siehst du alle Netzwerk-Geräte und ob sie erreichbar sind. Ein Tipp auf die Adresse öffnet ihre Weboberfläche.

- Je Ausgabe (DMX, WLED, Nanoleaf) gibt es **Aus**, **An** und **Nicht vorhanden**. **Aus** ist für eine Weile gedacht (orange Erinnerung), **Nicht vorhanden** für eine Anlage ohne dieses Gerät (keine Warnung).
- **DMX-Weg:** **Art-Net-Gateway** über das Netzwerk oder **USB-Adapter** direkt am Licht-Rechner.
- **Art-Net-Eingang** (Standard aus): nimmt Licht von einem anderen Lichtprogramm an. Die Sperren für Laser, Nebel und Strobe gelten weiter.
- **Ableton Link** gibt das Tempo an Link-Geräte im Netz weiter.

### WLED und Nanoleaf

- **WLED:** In WLED muss die **Übergangszeit auf 0** stehen, und Presets dürfen keinen eigenen Übergang enthalten, sonst blitzt der Streifen nicht im Takt.
- **Nanoleaf:** Adresse und Schlüssel änderst du unter **Fixtures** → **Bearbeiten**. Kommen die Panels beim Strobe nicht mit, die **Strobe-Grenze: Nanoleaf** senken.

### HomeMatic (Haus)

Im Bereich **Haus** (unter **Verbindungen**) schaltest du Raumlicht und Steckdosen deiner HomeMatic-Zentrale.

- **Raumlicht** (im Panel „Wohnzimmerlicht“): Regler für die Helligkeit, **Aus** und **An**.
- **Steckdosen:** ein Tipp schaltet um, eingeschaltete sind orange.
- **Automatik:** Läuft länger keine Musik, dimmt der Light-Butler das Raumlicht hoch, kommt die Musik zurück, schaltet er es aus.
- **Einstellungen: CCU und Kanäle** (unten im Bereich): Adresse eintragen, **Kanäle von der CCU holen**, mit **+ Hinzufügen** übernehmen.
- Den Nebelschub gibt es dort nie, Nebel nur über den SMOKE-Knopf.

### DMX-Monitor

Der **DMX-Monitor** (**⚙** → **Technik**) zeigt alle 512 Kanäle so, wie sie gerade hinausgehen, nur zum Ansehen.

### DMX-Debugger

Mit dem **DMX-Debugger** (**⚙** → **Technik**) setzt du jeden DMX-Kanal einzeln, um ein Gerät zu erforschen.

**Achtung:** Der DMX-Debugger arbeitet **ohne alle Sperren**, auch für Laser, Nebelmaschine und die Mode- und Reset-Kanäle der Geräte.

- Richte Laser nie auf Personen.
- Schalte die Nebelmaschine beim Testen am besten stromlos.
- Teste keine Strobe-Kanäle, wenn empfindliche Menschen im Raum sind.
- Der Taster **Kurz dunkel** (oder die Leertaste) setzt alle Kanäle auf 0, solange du hältst.
- BLACKOUT geht immer vor. Der Debugger geht beim Schließen der Seite und nach 2 Sekunden ohne Verbindung aus.

## Einstellungen

Das Zahnrad **⚙** oben öffnet die Seite **Einstellungen**. Sie hat zwei große aufklappbare Bereiche und darunter Links zu weiteren Seiten.

### Aufbau der Seite

| Bereich | Inhalt |
| --- | --- |
| **Einstellungen allgemein** | Verbindungen, Haus, Sicherung, MIDI-Controller, Audio-Eingang sowie Ausgabe, Nebel, Titelerkennung und Panel |
| **Einstellungen (Auto-Erkennung)** | wie AUTO die Musik deutet: Stille, Kick und Beat, Energie, Phasen, Stufen, Strobe, Laser, Szenen-Automatik, Ambiente, Mixxx-Vorhersage |
| **Geräte** | Fixtures, Raumplan, APC mini · Belegung, ROLI Lumi · Belegung |
| **Technik** | DMX-Monitor, DMX-Debugger |
| **Software für andere Rechner** | Systemschema und Downloads der Installationspakete |

- Jede Änderung wirkt sofort und bleibt gespeichert.
- **↺** neben einem Wert stellt den Standard wieder her, **Alle auf Standard** setzt alles zurück. Die Standardwerte sind für gemischte Partymusik abgestimmt.

### Sprache und Texte

- **Einstellungen allgemein** → **Panel** → **Sprache der Knöpfe**: **Deutsch** oder **English**. Das gilt sofort auf allen Geräten, auch für dieses Handbuch.
- **Hinweistexte im Panel anzeigen** blendet die grauen Erklärzeilen aus oder ein.
- In der **Übersetzungstabelle** darunter gibst du jedem Knopf einen eigenen Text. **↺** setzt eine Zeile zurück, ein senkrechter Strich **|** macht einen Zeilenumbruch auf dem Knopf.

### Audio-Eingang

Die ganze Automatik hängt am Musiksignal.

1. Unter **Audio-Eingang** den **Eingang** wählen: die Soundkarte am Mischpult oder **Musik-Rechner (Netzwerk)**.
2. Eine eben angesteckte Soundkarte findet **Geräte neu suchen**.
3. Pegel ansehen: Spitzen zwischen etwa −12 und −3 dB, nie rot.
4. Zu leise: **Verstärkung (Software)** erhöhen. Zu laut (rotes **ÜBERSTEUERT**): am Mischpult leiser stellen.

Verwende einen Line-Eingang, keinen Mikrofon-Eingang.

### Die wichtigsten Schalter

- **Laser-Betrieb** (Gruppe **Laser**) und **Nebel über** DMX oder HomeMatic (Gruppe **Nebel**).
- **Ausgabe:** Shows aus Mixxx automatisch starten, Laser und Nebel in Shows erlauben, Licht-Versatz.
- **Titelerkennung:** Titel erkennen, Liedtexte holen, Mixxx verwenden, Schätzungen in die MP3 schreiben.

### Typische Anpassungen

| Problem | Was tun |
| --- | --- |
| Licht zu unruhig oder zu ruhig | **Gesamt ruhiger / lebhafter** verschieben |
| zu viele oder zu wenige Drops | Schwellen der Gruppe **Phasen** anpassen |
| Licht geht bei leisen Stellen in den Ruhemodus | **Stille-Schwelle** senken oder Stille-Dauer erhöhen |
| leise Passagen zu hell oder zu dunkel | **Helligkeit folgt Lautstärke** erhöhen oder senken |

## Sicherung

### Was wann gesichert wird

- **Jede Nacht um 04:30** sichert der Light-Butler (am Raspberry Pi und am Mac) Einstellungen, Szenen, Geräte, Raumplan, Shows (ohne MP3s) und Programme. Die letzten 14 Sicherungen bleiben.
- Der Helfer legt auf dem Musik-Stick einen **Notfall-Ordner** „Light-Butler-Programme“ an: alle Installationspakete, die jüngste Sicherung und dieses Handbuch.

### Im Panel

1. **⚙** → **Einstellungen allgemein** → **Sicherung** aufklappen.
2. **Jetzt sichern** macht sofort eine Sicherung.
3. **Download** bei einer Sicherung lädt sie herunter. Heb sie zusätzlich auf einem anderen Gerät auf, zum Beispiel einem NAS, denn die nächtliche Sicherung liegt auf derselben SD-Karte.

Der Nanoleaf-Schlüssel und der Claude-Schlüssel fehlen in heruntergeladenen Sicherungen absichtlich. Gib Sicherungen nicht weiter.

### Wiederherstellen

1. Neuen Licht-Rechner installieren (siehe Installation), am besten mit dem Paket **Pi: Ersatzgerät mit meinen Geräten**.
2. Die jüngste Sicherung zurückspielen. Den genauen Befehl findest du in der Technischen Beschreibung.
3. Danach den Nanoleaf neu koppeln und den Claude-Schlüssel neu eintragen.

## Installation

Alle Pakete findest du unter **⚙** → **Software für andere Rechner**, im **Systemschema** auch per Symbol (Himbeere = Raspberry Pi, Fenster = Windows, Apfel = Mac). Sie enthalten keine persönlichen Daten und starten mit allen Ausgaben aus.

### Raspberry Pi

1. Mit dem Raspberry Pi Imager ein Raspberry Pi OS (64 Bit) auf die SD-Karte spielen. Dort Hostname, Benutzer `admin`, WLAN und SSH eintragen.
2. Das Paket **Pi: frische Installation (ZIP)** laden (für ein Ersatzgerät **Pi: Ersatzgerät mit meinen Geräten (ZIP)**).
3. Das ZIP auf den Pi kopieren und dort installieren:

```
scp light-butler-pi.zip admin@<name-des-light-butler>:
unzip light-butler-pi.zip && cd Light-Butler-Pi && bash install_pi.sh
```

4. Einmal das Passwort eingeben und 5 bis 15 Minuten warten. Das Skript richtet den Dienst, die nächtliche Sicherung und den Knopf zum Herunterfahren ein.
5. Panel öffnen, Geräte unter **Fixtures** anlegen, dann die Ausgaben einschalten.

Noch einmal ausführen aktualisiert die Programme. Einstellungen, Szenen, Shows und Geräte bleiben.

### Windows-PC

1. Python 3.12 von python.org installieren und dabei „Add python.exe to PATH“ anhaken.
2. Das Paket **Windows: ganzer Light-Butler (ZIP)** laden und entpacken.
3. Im entpackten Ordner ein Terminal öffnen und eintippen:

```
powershell -ExecutionPolicy Bypass -File install_windows.ps1
```

4. Das Panel steht dann unter `http://localhost:8080/`. Fragt die Firewall, nur **Private Netzwerke** zulassen.

Ohne Python geht es mit **Windows: Light-Butler.exe ohne Python (ZIP)**: entpacken und `Light-Butler.exe` doppelklicken. Unter Windows fehlen Titelerkennung und die nächtliche Sicherung.

### Mac

1. Das Paket **Mac: ganzer Light-Butler (ZIP)** laden und entpacken.
2. Im Terminal in den Ordner wechseln und eintippen:

```
bash install_lightbutler_mac.sh
```

3. Fragt macOS, ob Python das Mikrofon benutzen darf: erlauben.

Diese Fassung ist neu und noch nicht am echten Licht geprüft. Für Mixxx und den Helfer auf einem Musik-Rechner siehe Kapitel DJ-Software und Musik-Rechner.

### Pegelkurven-Rechner (Windows mit Grafikkarte)

1. Das Paket **Windows: Pegelkurven (ZIP)** laden und entpacken.
2. In der PowerShell eintippen:

```
powershell -ExecutionPolicy Bypass -File install_stems.ps1
```

3. Der Rechner holt sich danach beim Anmelden von selbst Aufträge vom Light-Butler. Am Mac bietet `install_mac.sh` die Pegelkurven gleich mit an.

## Sicherheit

Die Anlage hat Laser, Strobe, Nebel und starke Lichter. Die Sperren der Software ersetzen nicht deine Aufmerksamkeit vor Ort.

### Im Notfall

- **BLACKOUT** gedrückt halten (Panel oder APC-Pad): sofort alles aus, auch Laser und Nebel.
- Für **dauerhaft dunkel** die Szene **All off** antippen.
- **FREEZE** schaltet die Laser sofort aus.
- Wird der Light-Butler beendet, gehen die Laser sofort aus.

### Laser

- Laser laufen nur in der Szene **Laser** und, mit Hakerl, in Laser-Clips einer Show.
- Bei Freeze, Blackout, Stille, Szenenwechsel und Beenden sind sie sofort aus.
- **Richte Laser nie auf Personen oder in Augenhöhe.** Plane die Ausrichtung beim Aufbau, nicht während der Party. Die Software weiß nicht, wohin der Strahl zeigt.

### Strobe

- Ohne **Strobe-Erlaubnis** blitzt es höchstens 3-mal pro Sekunde.
- Schnelles Blitzen kann bei Menschen mit Epilepsie Anfälle auslösen. Schalte die Erlaubnis nur ein, wenn es für alle Gäste in Ordnung ist, und nimm sie danach zurück.
- STROBE blitzt nur, solange du drückst.

### Nebel

- Die Nebelmaschine läuft nie von allein: nur mit SMOKE oder, mit Hakerl, in einem Nebel-Clip einer Show.
- Höchstens 10 Sekunden am Stück, danach 20 Sekunden Pause.
- Achte auf **Rauchmelder** in der Nähe und deaktiviere sie vorher, wenn nötig. Danach wieder aktivieren.

### Netzwerk

- Das Panel hat **keine Anmeldung**. Benutze es nur im Heimnetz und stelle es nie ins Internet.
- Wer in deinem Heimnetz ist, kann das Licht bedienen. Gib Gästen das Heim-WLAN nur, wenn du das willst.

## Fehlersuche

Die meisten Probleme erkennst du an der Hinweiszeile und am Statusfeld. Mehr Hilfe und Befehle stehen in der Technischen Beschreibung.

| Problem | Was tun |
| --- | --- |
| Panel öffnet nicht | IP-Adresse des Licht-Rechners statt des Namens versuchen, Licht-Rechner und Netz prüfen |
| Panel zeigt Altes | Seite neu laden, auf jedem Gerät (am Handy nach unten ziehen) |
| Licht reagiert nicht auf Musik | **Audio-Eingang**: richtigen Eingang wählen, Pegel ansehen, Verstärkung erhöhen |
| rotes ÜBERSTEUERT | am Mischpult oder Interface leiser stellen |
| kein DMX | Hinweiszeile lesen: ist die DMX-Ausgabe an, ist das Art-Net-Gateway erreichbar, steckt der USB-Adapter? |
| WLED-Streifen oder Nanoleaf dunkel | Strom und WLAN des Geräts prüfen, Ausgabe unter **Verbindungen** einschalten |
| ein Knopf oben wirkt nur kurz | STROBE, SMOKE, BLACKOUT, WOW!, BLINDER und FREEZE sind Taster: gedrückt halten |
| Bedienung gesperrt | AUTO ist an (oder eine Show läuft): AUTO oder SHOW antippen |
| SMOKE reagiert nicht | die Zeile auf dem Knopf zeigt den Grund: Pause, aus, heizt |
| Laser bleiben aus | Szene **Laser** wählen, **Laser-Betrieb** prüfen |
| Mixxx-Zeile meldet nicht verbunden | Mixxx über die App „Light-Butler Mixxx“ starten, Controller in Mixxx aktivieren |
| APC-Fader tut nichts | Fader erst bis an den aktuellen Wert heranfahren |
| Vorhören geht nicht, roter Hinweis | Musik-Rechner und Helfer einschalten, Stick anstecken, Musikordner unter **Verbindungen** prüfen |
| Herz oben gelb oder rot | Seite **Zustand** öffnen, dort steht, was nicht passt |

## Über Light-Butler und Lizenz

- **Light-Butler** ist freie Software unter der **GNU General Public License Version 3 (GPLv3)**, ohne jede Gewährleistung.
- Die Seite **Über Light-Butler** (Menü **☰** ganz unten) zeigt Stand, Copyright, Quelltext, Lizenz und die genutzten Dienste im Internet. Die Dienste laufen nur auf Knopfdruck, das Licht braucht kein Internet.
- Kontakt: lightbutler@gmx.at
