# Light-Butler

**Lichtsteuerung, die Musik hört.** Light-Butler steuert deine Lichtanlage automatisch zur Musik. Ein Licht-Rechner (Raspberry Pi, Windows-PC oder Mac) hört die Musik, erkennt Tempo, Beat, Takt, Tonart, Stimmung und Phasen (Aufbau, Break, Drop) und schickt daraus die Lichtdaten an alle Geräte. Bedient wird alles im Web-Panel am Handy, Tablet oder PC.

*English: Light-Butler is a party lighting controller that listens to the music. It runs on a Raspberry Pi, a Windows PC or a Mac and drives DMX (Art-Net or USB), WLED and Nanoleaf from tempo, beat, key and song structure. Panel and manual in German and English.*

![Systemschema](pi/static/sm/systemschema.svg)

## Download

**Windows:** [Light-Butler-Setup.exe](https://github.com/neppma/Light-Butler/releases/latest/download/Light-Butler-Setup.exe) laden, doppelklicken, installieren. Danach startest du den Light-Butler über das Symbol auf dem Desktop, das Panel öffnet sich im Browser. Für einen Windows-PC als Musik-Rechner gibt es genauso [Light-Butler-Musik-Setup.exe](https://github.com/neppma/Light-Butler/releases/latest/download/Light-Butler-Musik-Setup.exe): Er fragt nach der Adresse des Light-Butler und legt das Symbol „Mixxx mit Light-Butler“ an. Python ist eingebaut, Administrator-Rechte braucht es nicht. Zeigt Windows „Der Computer wurde durch Windows geschützt“, auf **Weitere Informationen** und **Trotzdem ausführen** klicken (der Installer ist nicht kostenpflichtig signiert).

Für die anderen Rechner: ZIP laden, entpacken, das Installationsskript starten. Jedes Paket hat eine `LIESMICH.txt` mit den Schritten.

| Wofür | Paket |
| --- | --- |
| **Raspberry Pi** als Licht-Rechner | [light-butler-pi.zip](https://github.com/neppma/Light-Butler/releases/latest/download/light-butler-pi.zip) |
| **Windows-PC** als Licht-Rechner | [Light-Butler-Setup.exe](https://github.com/neppma/Light-Butler/releases/latest/download/Light-Butler-Setup.exe) |
| **Mac** als Licht-Rechner | [light-butler-mac-voll.zip](https://github.com/neppma/Light-Butler/releases/latest/download/light-butler-mac-voll.zip) |
| **Musik-Rechner Mac** (DJ-Software Mixxx, Ton übers Netz, Musik-Datenbank) | [light-butler-mac.zip](https://github.com/neppma/Light-Butler/releases/latest/download/light-butler-mac.zip) |
| **Musik-Rechner Windows** | [Light-Butler-Musik-Setup.exe](https://github.com/neppma/Light-Butler/releases/latest/download/Light-Butler-Musik-Setup.exe) |
| **Pegelkurven-Rechner** (Windows mit NVIDIA-Grafikkarte, optional) | [light-butler-windows.zip](https://github.com/neppma/Light-Butler/releases/latest/download/light-butler-windows.zip) |

Alle Fassungen stehen unter [Releases](https://github.com/neppma/Light-Butler/releases). Du brauchst nur **einen** Licht-Rechner. Ein Musik-Rechner ist optional. Eine neue Anlage startet mit allen Ausgaben aus: Geräte im Panel unter Einstellungen → Fixtures anlegen, dann die Ausgaben einschalten. Die Schritte im Einzelnen stehen im Handbuch im Kapitel **Installation**.

## Was es kann

- **Licht live zur Musik:** AUTO folgt der Musik ohne Eingriff, mit vier Stufen von Chillen bis Vollgas, Licht-Stilen je Genre, 40 Szenen und Sofort-Knöpfen (Strobe, Nebel, Blackout, Laser).
- **Showmanager:** eigene Licht- und Lasershows zu einer MP3 in einer Zeitleiste, ein Show-Assistent erstellt sie auf Wunsch automatisch.
- **Musik:** Auto-DJ mit Übergängen im Takt, Anbindung an die DJ-Software Mixxx, Titelerkennung und Liedtexte im Panel.
- **Musik-Datenbank:** Lieder, Interpreten und Alben mit Cover, Energie, Tonart und BPM, dazu Werkzeuge zum Aufräumen (Tags, Cover, Doppelte, beschädigte Dateien).
- **Geräte:** DMX über Art-Net oder einen DMX-USB-Adapter, WLED, Nanoleaf, HomeMatic, AKAI APC mini und ROLI LUMI Keys, Fixture-Editor und Raumplan.
- **Sicherheit:** Sperren für Laser, Strobe und Nebel, nächtliche Sicherung.

Handbuch: [Deutsch](docs/HANDBUCH.md) · [English](docs/MANUAL_EN.md). Technische Beschreibung: [Deutsch](docs/TECHNIK.md) · [English](docs/TECHNICAL_EN.md).

## Sicherheit

Light-Butler kann Laser, Strobe und Nebelmaschinen steuern. Laser und schnelles Blitzen können Augen schädigen und Anfälle auslösen. Laser senden nur in der Szene „Laser“ mit Freigabe, Strobe braucht eine eigene Erlaubnis, Nebel läuft nur auf Knopfdruck. Richte Laser nie auf Personen oder in Augenhöhe. Das Web-Panel hat keine Anmeldung: Betreibe es nur im eigenen Heimnetz, nie offen im Internet.

## Lizenz

Copyright © 2026 Markus Nepp. Freie Software unter der GNU General Public License Version 3 (GPLv3), siehe [`LICENSE`](LICENSE). Ohne jede Gewährleistung. Kontakt: lightbutler@gmx.at
