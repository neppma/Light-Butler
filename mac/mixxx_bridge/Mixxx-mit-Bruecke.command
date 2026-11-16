#!/bin/bash
# Startet Mixxx und die Bruecke: zeigt den Deck-Zustand im Terminal, erkennt das Lied, berechnet/holt die Analyse
# und schickt alles an den Raspberry Pi (Lichtsteuerung).
# Einmalig ausfuehrbar machen:  chmod +x Mixxx-mit-Bruecke.command   (danach Doppelklick im Finder)
cd "$(dirname "$0")"
source ~/s2l/bin/activate
PI="lightbutler.local"                      # Adresse des Raspberry Pi (oder dessen IP, z. B. 192.168.1.20)
DB="$HOME/Downloads/mixxxdb.sqlite"         # Kopie der Mixxx-Datenbank (siehe README)
if [ ! -f "$DB" ]; then
  echo "Datenbank-Kopie fehlt: $DB   (siehe README, Abschnitt D)"; exit 1
fi
/Applications/Mixxx.app/Contents/MacOS/mixxx --controller-debug 2>&1 | python3 mixxx_bridge.py --stdin --monitor --db "$DB" --send "$PI"
