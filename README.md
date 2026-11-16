# Light-Butler

**Lichtsteuerung, die Musik hört.** Light-Butler steuert deine Lichtanlage automatisch zur Musik. Ein Licht-Rechner (Raspberry Pi, Windows-PC oder Mac) hört die Musik, erkennt Tempo, Beat, Takt, Tonart, Stimmung und Phasen (Aufbau, Break, Drop) und schickt daraus die Lichtdaten an alle Geräte. Bedient wird alles im Web-Panel am Handy, Tablet oder PC.

*English: Light-Butler is a party lighting controller that listens to the music. It runs on a Raspberry Pi, a Windows PC or a Mac and drives DMX (Art-Net or USB), WLED and Nanoleaf from tempo, beat, key and song structure. The web panel and the manual are available in German and English (`docs/MANUAL_EN.md`).*

![Systemschema](pi/static/sm/systemschema.svg)

## Was es kann

- **Licht live zur Musik:** AUTO folgt der Musik ohne Eingriff, mit vier Stufen von Chillen bis Vollgas, Licht-Stilen je Genre, 40 Szenen und Sofort-Knöpfen (Strobe, Nebel, Blackout, Laser).
- **Showmanager:** eigene Licht- und Lasershows zu einer MP3 in einer Zeitleiste, ein Show-Assistent erstellt sie auf Wunsch automatisch.
- **Musik:** Auto-DJ mit Übergängen im Takt, Anbindung an die DJ-Software Mixxx, Titelerkennung und Liedtexte im Panel.
- **Musik-Datenbank:** Lieder, Interpreten und Alben mit Cover, Energie, Tonart und BPM, dazu Werkzeuge zum Aufräumen (Tags, Cover, Doppelte, beschädigte Dateien).
- **Geräte:** DMX über Art-Net oder einen DMX-USB-Adapter, WLED, Nanoleaf, HomeMatic, AKAI APC mini und ROLI LUMI Keys, Fixture-Editor und Raumplan.
- **Sicherheit:** Sperren für Laser, Strobe und Nebel, nächtliche Sicherung.

Die ganze Liste steht im Handbuch: [`docs/HANDBUCH.md`](docs/HANDBUCH.md) (Deutsch), [`docs/MANUAL_EN.md`](docs/MANUAL_EN.md) (English). Technische Einzelheiten: [`docs/TECHNIK.md`](docs/TECHNIK.md), [`docs/TECHNICAL_EN.md`](docs/TECHNICAL_EN.md).

## Ausprobieren ohne Lichtanlage

Mit Python 3.10 oder neuer läuft der Light-Butler im Simulator: künstliche Musik, nichts wird gesendet.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd pi && python3 show.py --simulate --dry-run --web 8080 --no-midi --no-mixxx
```

Dann im Browser `http://localhost:8080/` öffnen.

## Installieren

Die Installationspakete entstehen aus diesem Quelltext:

```bash
python3 pi/pakete.py pi            # Raspberry Pi    -> light-butler-pi.zip
python3 pi/pakete.py windows       # Windows-PC      -> light-butler-windows-voll.zip
python3 pi/pakete.py mac           # Mac             -> light-butler-mac-voll.zip
python3 pi/pakete.py musik-mac     # Musik-Rechner Mac (Mixxx-Anbindung, Helfer)
```

Jedes Paket enthält eine `LIESMICH.txt` und ein Installationsskript. Die Schritte stehen im Handbuch im Kapitel **Installation**. Eine neue Anlage startet mit allen Ausgaben aus. Die Geräte legst du danach im Panel unter Einstellungen → Fixtures an.

## Sicherheit

Light-Butler kann Laser, Strobe und Nebelmaschinen steuern. Laser und schnelles Blitzen können Augen schädigen und Anfälle auslösen. Laser senden nur in der Szene „Laser“ mit Freigabe, Strobe braucht eine eigene Erlaubnis, Nebel läuft nur auf Knopfdruck. Richte Laser nie auf Personen oder in Augenhöhe. Das Web-Panel hat keine Anmeldung: Betreibe es nur im eigenen Heimnetz, nie offen im Internet.

## Tests

```bash
bash tests/run_all.sh        # endet mit "ALLES IN ORDNUNG"
```

Die Tests brauchen keine Hardware.

## Lizenz

Copyright © 2026 Markus Nepp. Freie Software unter der GNU General Public License Version 3 (GPLv3), siehe [`LICENSE`](LICENSE). Ohne jede Gewährleistung.

Kontakt: lightbutler@gmx.at
