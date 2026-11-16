SICHERUNG DER LICHTSTEUERUNG
============================

RASPBERRY PI
------------
Einrichten (einmalig, im Ordner ~/lichtshow, Dateien backup.py und install_backup.sh dorthin kopieren):
    sudo bash install_backup.sh
Das richtet einen taeglichen Zeitplan ein (04:30 Uhr, verpasste Laeufe werden nachgeholt) und macht gleich die erste Sicherung.

Wo liegt was:   ~/backups/lichtshow-backup-DATUM_UHRZEIT.zip   (die letzten 14), Protokoll in ~/backups/backup.log
Im Zip:         alle Programme und Einstellungen aus ~/lichtshow (fixtures.yaml, show.conf, scenes.json, settings.json, aim.json,
                audio.json, midimap.json, nanoleaf.json, Anleitungen), die Dienstdateien von systemd, INFO.txt (Systemstand,
                Pakete), WIEDERHERSTELLEN.txt und manifest.json mit Pruefsummen.
Im Panel:       Bereich "Sicherung": "Jetzt sichern" und die Liste der letzten Sicherungen.

Befehle:
    python3 backup.py --now                       jetzt sichern
    python3 backup.py --list                      Sicherungen zeigen
    python3 backup.py --verify DATEI.zip          Pruefsummen kontrollieren
    python3 backup.py --restore DATEI.zip --dry-run    nur anzeigen, was passieren wuerde
    python3 backup.py --restore DATEI.zip         wiederherstellen (der jetzige Stand wird vorher gesichert)
    python3 backup.py --restore DATEI.zip --only data  nur Einstellungen, Szenen, Ziele (nicht die Programme)
    sudo python3 backup.py --restore DATEI.zip --system  zusaetzlich die Dienstdateien nach /etc/systemd/system
Nach dem Zurueckspielen:   sudo systemctl daemon-reload && sudo systemctl restart lichtshow
Zeitplan pruefen:          systemctl list-timers lichtshow-backup.timer
Zeitplan ausschalten:      sudo systemctl disable --now lichtshow-backup.timer

Einstellungen (optional): Datei ~/lichtshow/backup.conf, zum Beispiel
    {"dir": "~/backups", "keep": 14, "copy_to": "/mnt/nas/backups", "include_secrets": true}
  dir             Zielordner der Sicherungen
  keep            wie viele Sicherungen bleiben
  copy_to         zusaetzliche Kopie in einen anderen Ordner, zum Beispiel ein eingebundenes NAS (ist er nicht da, wird das
                  im Protokoll vermerkt, die Sicherung gelingt trotzdem). SD-Karten fallen aus: eine Kopie ausserhalb des Pi
                  ist die eigentliche Sicherheit.
  include_secrets false = nanoleaf.json (enthaelt den API-Key) wird nicht ins Zip gelegt

Hinweis: Das Zip enthaelt den Nanoleaf-Key und ist deshalb nur fuer dich (Rechte 600). Das Panel bietet es nicht zum Download an.
Nicht gesichert wird die Konfiguration des OLA-Pi (192.168.1.45), das ist ein anderer Rechner.

Einen neuen Pi einrichten: Ordner ~/lichtshow anlegen, backup.py aus dem Zip (Ordner lichtshow/) dorthin kopieren,
Pakete aus INFO.txt installieren, dann python3 backup.py --restore DATEI.zip --system (mit sudo).


MAC (Analysen der Mixxx-Bruecke)
--------------------------------
Mit install_launcher.sh (neue Version) sichert die App beim Start automatisch den Ordner ~/Light-Butler-Daten (Analysen, Programme)
nach ~/Documents/Light-Butler-Backups, hoechstens einmal pro Woche, die letzten 8 bleiben.
Von Hand:    python3 backup_mac.py           oder        python3 backup_mac.py --list
Wiederherstellen: Zip im Finder entpacken, den Ordner Light-Butler-Daten nach ~ kopieren (alten vorher umbenennen).
Die Analysen kosten viel Rechenzeit: ~/Documents/Light-Butler-Backups am besten in Time Machine oder iCloud mitsichern.
