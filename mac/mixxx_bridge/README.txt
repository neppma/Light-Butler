LIGHT-BUTLER - MIXXX-BRUECKE, SCHRITT 1: PRUEFEN
================================================
Ziel: Wir schauen, welche Werte Mixxx 2.5.6 wirklich hergibt (Position, Tempo, Beat, Sync, Fader).
Noch kein Eingriff in die Lichtsteuerung auf dem Pi.

Dateien in diesem Ordner:
  Light-Butler-Bridge.midi.xml          Mixxx-Mapping (Beschreibung)
  Light-Butler-Bridge-scripts.js        Mixxx-Mapping (liest die Decks, sendet sie als MIDI-SysEx)
  mixxx_bridge.py                      Programm fuer den Mac (anzeigen, weiterleiten, Bibliothek pruefen)


A) EINMALIG VORBEREITEN
-----------------------
1. IAC-Treiber (virtueller MIDI-Port) einschalten:
   Programm "Audio-MIDI-Setup" oeffnen -> Menue "Fenster" -> "MIDI-Studio einblenden" ->
   Doppelklick auf "IAC-Treiber" -> Haken bei "Gerat ist online" -> "Anwenden".
   (Es muss ein Bus "Bus 1" in der Liste stehen.)

2. Mapping in Mixxx-Ordner kopieren (Finder: Gehe zu -> Ordner ... -> Eingabe unten). Je nach Installation
   (Mixxx laeuft oft in einem Container) heisst der Ordner:
   ~/Library/Containers/org.mixxx.mixxx/Data/Library/Application Support/Mixxx/controllers/
   oder  ~/Library/Application Support/Mixxx/controllers/   (Mixxx zeigt beim Start im Terminal, welchen es nutzt)
   Dorthin die beiden Dateien  Light-Butler-Bridge.midi.xml  und  Light-Butler-Bridge-scripts.js  kopieren.

3. Python-Pakete (im Terminal). Wenn "externally-managed-environment" kommt, den Weg mit venv nehmen:
   python3 -m venv ~/s2l
   source ~/s2l/bin/activate
   pip install mido python-rtmidi
   (Spaeter jedes Mal im Terminal vorher:  source ~/s2l/bin/activate )

B) IN MIXXX AKTIVIEREN
----------------------
1. Mixxx starten (am besten aus dem Terminal, dann siehst du Meldungen des Mappings):
   /Applications/Mixxx.app/Contents/MacOS/mixxx --controller-debug
2. Einstellungen -> Controller -> in der Liste "IAC Driver Bus 1" auswaehlen.
3. Haken bei "Aktiviert". Bei "Geladene Zuordnung" "Light-Butler Bridge" waehlen. Uebernehmen.
   Dein Hercules-Pult bleibt unberuehrt (hat eine eigene Zeile). Im Terminal sollte erscheinen:
   [Light-Butler] Bridge gestartet

C) ANZEIGEN
-----------
Im Terminal (in dem Ordner mit mixxx_bridge.py, in einem zweiten Terminal-Fenster):
   python3 mixxx_bridge.py --monitor

Dann in Mixxx: ein Lied laden, abspielen, Sync einschalten, Pitch-Fader bewegen, Crossfader
und Kanalfader bewegen, ein zweites Lied auf Deck 2. Du siehst pro Deck eine Zeile mit:
   spielt/Pause, Laenge, Position, BPM der Datei, BPM jetzt, Pitch in %, Beat-Lage, Sync, Fader, hoerbar, Tonart.

Wenn nichts erscheint:
   python3 mixxx_bridge.py --list       zeigt alle MIDI-Ports (dort muss "IAC Driver Bus 1" stehen)
   Mixxx -> Einstellungen -> Controller: ist die Zeile "IAC Driver Bus 1" aktiviert, Mapping geladen?

D) BIBLIOTHEK PRUEFEN (Mixxx darf dabei laufen)
-----------------------------------------------
   python3 mixxx_bridge.py --library
Zeigt: wie viele Titel, wie viele mit BPM, Tonart und Beat-Raster, und ob sich Titel ueber Laenge+BPM
eindeutig erkennen lassen. Liegt die Datenbank woanders:  --db /Pfad/zu/mixxxdb.sqlite
Sagt macOS "Operation not permitted" (Datenschutz): die Datei mixxxdb.sqlite im Finder aus dem Mixxx-Ordner
(siehe oben, Container) nach Downloads kopieren und dann:
   python3 mixxx_bridge.py --library --db ~/Downloads/mixxxdb.sqlite

Bitte schick mir:
  1. Die Ausgabe von  --library
  2. Ein Foto oder Text der Live-Tabelle (--monitor) waehrend ein Lied mit Sync und bewegtem Pitch laeuft
  3. Falls etwas nicht klappt: die Terminal-Meldungen von Mixxx


E) ERSATZWEG OHNE MIDI-PORT (wenn --monitor nichts empfaengt)
-------------------------------------------------------------
Mixxx schreibt jede gesendete Nachricht mit --controller-debug ins Terminal. Das Programm kann diese Ausgabe
direkt mitlesen, ganz ohne IAC-Port:

   source ~/s2l/bin/activate
   cd ~/Downloads/mixxx_bridge
   /Applications/Mixxx.app/Contents/MacOS/mixxx --controller-debug 2>&1 | python3 mixxx_bridge.py --stdin --monitor --db ~/Downloads/mixxxdb.sqlite

Mixxx laeuft dabei ganz normal, im Terminal erscheint die Live-Tabelle. Das Mapping muss in Mixxx wie bisher
aktiviert sein (Controller "IAC-Treiber Bus 1"). Mit Mixxx-mit-Bruecke.command geht das per Doppelklick.


F) ANALYSE EINZELNER LIEDER (Breaks, Aufbauten, Drops)
-------------------------------------------------------
Einmalig, in der Umgebung s2l:
   source ~/s2l/bin/activate
   pip install numpy scipy soundfile
   (MP3-Dateien liest soundfile selbst. Scheitert es (AAC/m4a, manche MP3), hilft afconvert aus macOS aus.
    Alternativ ffmpeg:  brew install ffmpeg)

Eigentest mit einem kuenstlichen Lied (muss "OK" zeigen):
   python3 analyze_track.py --selftest

Lied in Mixxx suchen (liefert Nummer und Dateipfad):
   python3 analyze_track.py --db ~/Downloads/mixxxdb.sqlite --find "Distorted Truth"

Lied analysieren (zeigt eine Zeitleiste und alle Ereignisse, speichert eine kleine JSON-Datei in analysis/):
   python3 analyze_track.py --db ~/Downloads/mixxxdb.sqlite --id 1234

Eine Datei direkt (BPM optional):
   python3 analyze_track.py --file ~/Music/lied.mp3 --bpm 128

Ganze Bibliothek (dauert, am besten ueber Nacht; schon fertige Lieder werden uebersprungen):
   python3 analyze_track.py --db ~/Downloads/mixxxdb.sqlite --all --jobs 4

Hinweis macOS: Beim ersten Zugriff auf Ordner wie Musik oder Dokumente fragt macOS, ob das Terminal darauf zugreifen darf.
Dann "Erlauben" waehlen.

Musik auf dem NAS: Das NAS muss auf dem Mac eingebunden sein (Finder -> Gehe zu -> Mit Server verbinden), bevor du
analysierst. Die Pfade stehen in der Mixxx-Bibliothek, meist als /Volumes/<NAS-Name>/... Heisst das Laufwerk heute
anders oder ist es unter einem anderen Namen eingebunden, hilft die Pfad-Umsetzung:
   python3 analyze_track.py --db ~/Downloads/mixxxdb.sqlite --all --path-map /Volumes/alt=/Volumes/neu
Jede Datei wird einmal komplett gelesen (Netzwerk). Fuer die ganze Bibliothek am besten per LAN-Kabel, nicht per WLAN.


G) VORHERSAGE: MIXXX -> RASPBERRY PI (Schritt 2)
------------------------------------------------
Auf dem Raspberry Pi (Ordner ~/lichtshow): die Dateien  mixxx_link.py, show.py, settings.py, webpanel.py
aus der Lieferung kopieren und den Dienst neu starten:   sudo systemctl restart lichtshow
Der Pi lauscht dann auf UDP-Port 9020 (andere Nummer mit --mixxx-port in show.conf, ausschalten mit --no-mixxx).

Auf dem Mac: Mixxx mit der Bruecke starten, mit Pi-Adresse:
   source ~/s2l/bin/activate
   cd ~/Downloads/mixxx_bridge
   /Applications/Mixxx.app/Contents/MacOS/mixxx --controller-debug 2>&1 | python3 mixxx_bridge.py --stdin --monitor --db ~/Downloads/mixxxdb.sqlite --send lightbutler.local
(oder per Doppelklick auf Mixxx-mit-Bruecke.command)

Was passiert: Du laedst ein Lied in ein Deck. Die Bruecke erkennt es (Laenge, BPM, Tonart), holt die Analyse aus dem
Ordner analysis/ oder berechnet sie im Hintergrund (das NAS muss verbunden sein), und schickt dem Pi den Plan mit
Aufbau, Stille und Drop. Im Monitor steht pro Deck eine Zeile "Plan: ...".

Auf dem Pi steht im Panel unter "AUTO" eine Zeile "Mixxx": Deck, Titel, "Drop in 12 s" und ob das Licht der
Vorhersage folgt. Zuerst nur Anzeige. Zum Einschalten: Panel -> Einstellungen -> Gruppe "Mixxx-Vorhersage" ->
"Vorhersage fuers Licht nutzen" auf 1. Fallen Verbindung oder Plan weg, nutzt das Licht wieder die Audio-Erkennung.

Hinweise:
  - Die Datenbank-Kopie (mixxxdb.sqlite in Downloads) ist ein Stand von jetzt. Neue Lieder in Mixxx erscheinen dort
    erst, wenn du die Datei im Finder erneut aus dem Mixxx-Ordner kopierst.
  - Der Mac und der Pi muessen im selben Netz sein. Klappt "lightbutler.local" nicht, nimm die IP-Adresse des Pi.


H) START MIT EINEM KLICK: DIE APP "LIGHT-BUTLER MIXXX"
-----------------------------------------------------
Einmal installieren (im Terminal, im Ordner mixxx_bridge):
   bash install_launcher.sh
Das Skript fragt nach der Adresse des Raspberry Pi (Standard lightbutler.local), legt den Ordner ~/Light-Butler-Daten an
und erzeugt die App  ~/Applications/Light-Butler Mixxx.app.

Danach zeigt der Finder die App an (Fenster mit markiertem Symbol). Doppelklick startet sie, oder das Symbol auf das
Dock ziehen. Sie startet Mixxx und die Bruecke. Beendest du Mixxx, beendet sich die Bruecke von selbst.
Wieder finden:   open -R ~/Applications/Light-Butler\ Mixxx.app      (zeigt sie im Finder)
Direkt starten:  open ~/Applications/Light-Butler\ Mixxx.app
Ins Programme-Verzeichnis: mv ~/Applications/Light-Butler\ Mixxx.app /Applications/   (oder im Finder hineinziehen)
Oder Spotlight: Cmd+Leertaste, "Light-Butler" tippen.

  - Bei jedem Start wird die Mixxx-Datenbank neu kopiert, neue Lieder sind sofort bekannt.
  - Beim ersten Start fragt macOS evtl. nach Erlaubnis (Daten anderer Apps, Netzwerklaufwerke / NAS). Jeweils "Erlauben".
    Ohne die erste Erlaubnis nutzt die App die alte Datenbank-Kopie, ohne die zweite kann sie das NAS nicht lesen.
  - Die Analyse neuer Lieder laeuft im Hintergrund, sobald du sie in ein Deck laedst (NAS muss verbunden sein).
  - Meldungen stehen in ~/Library/Logs/Light-Butler/bridge.log (Ueberblick in launcher.log).
  - Pi-Adresse, Mixxx-Pfad oder Musikordner (MUSIC_ROOT, fuer Vorhoeren und "Show anlegen" im Panel) aendern:
    ~/Light-Butler-Daten/config.sh   (oeffnen mit:  open -e ~/Light-Butler-Daten/config.sh)
  - Vorhoeren: die Bruecke liefert die MP3s der Bibliothek auf Port 9025 an die Seite "Musik-Datenbank" des Panels
    (nur lesend, nur Dateien aus der Mixxx-Bibliothek, nur im Heimnetz). Abschalten mit --no-music-serve.
  - Ist Mixxx schon gestartet, bittet die App, Mixxx erst zu beenden (die Bruecke braucht einen frischen Start).
  - Du siehst den Zustand weiter im Panel des Pi (Zeile "Mixxx"). Die Terminal-Anzeige gibt es nur ueber
    Mixxx-mit-Bruecke.command.


I) APP BLEIBT UNVERAENDERT, ERLAUBNISSE BLEIBEN ERHALTEN
---------------------------------------------------------
Seit dieser Version legt install_launcher.sh die App "Light-Butler Mixxx" nur noch EINMAL an. Bei jedem weiteren Lauf
wird nur ~/Light-Butler-Daten/launch.sh (die eigentliche Startlogik) und das Programm der Bruecke aktualisiert. macOS merkt sich
Erlaubnisse (Festplattenvollzugriff, Netzlaufwerk) pro App und verlangt sie bei einer neu erzeugten App wieder.
Der erste Lauf mit dieser Version ersetzt die alte App noch einmal (Festplattenvollzugriff danach einmal wieder einschalten).

Zwei Symbole im Dock: Das ist normal. Eines gehoert zur App "Light-Butler Mixxx" (sie wartet, bis du Mixxx beendest), das
andere zu Mixxx selbst (huepft, bis es geladen ist). Nur das Starter-Symbol ausblenden (App neu erzeugen):
   S2L_HIDE_DOCK=1 S2L_RECREATE_APP=1 bash install_launcher.sh

Fehlersuche: Warnungen und Fehler von Mixxx stehen in ~/Library/Logs/Light-Butler/mixxx_errors.log.
