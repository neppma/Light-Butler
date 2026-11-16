#!/bin/bash
# Sterne aus dem Light-Butler in Mixxx eintragen (Wunsch 14.11.2026), aufgerufen von launch.sh, solange Mixxx noch zu ist.
# Fehlerbericht 14.11.2026: Python darf die Datenbank im Ordner von Mixxx nicht oeffnen ("Operation not permitted"), cp und
# cmp aus diesem Skript schon (wie bei mixxx_umbenennen.sh). Darum: cp holt Sicherung und Arbeitskopie, mixxx_sterne.py
# traegt in der Arbeitskopie ein und prueft sie, cp bringt sie zurueck, cmp vergleicht; geht etwas schief, kommt die
# Sicherung zurueck und die Warteschlange bleibt fuer den naechsten Start.
DB="$1"
BASE="$(cd "$(dirname "$0")" && pwd)"
PY="$BASE/mixxx_sterne.py"
DIR="${S2L_DATA:-$HOME/Light-Butler-Daten}/sterne"
[ -s "$DIR/offen.json" ] || exit 0
[ "$(tr -d ' {}\n' < "$DIR/offen.json")" = "" ] && exit 0
if [ ! -f "$DB" ]; then echo "Sterne: Mixxx-Datenbank nicht gefunden, bleibt fuer spaeter"; exit 0; fi
if [ -e "$DB-journal" ] || [ -e "$DB-wal" ]; then echo "Sterne: Mixxx wurde nicht sauber beendet (Journal liegt daneben), nichts eingetragen"; exit 0; fi
BAK="$DIR/mixxxdb-vor-sterne.sqlite"
WORK="$DIR/.arbeit.sqlite"
if ! { cp "$DB" "$BAK" && chmod u+w "$BAK" && cp "$BAK" "$WORK" && chmod u+w "$WORK"; }; then
  echo "Sterne: keine Kopie der Mixxx-Datenbank moeglich, nichts eingetragen"; rm -f "$WORK"; exit 0
fi
n="$(python3 "$PY" --kopie "$WORK")"
case "$n" in
  ''|*[!0-9]*) echo "Sterne: ${n:-Arbeitskopie ging nicht}, nichts eingetragen"; rm -f "$WORK"; exit 0 ;;
esac
if [ "$n" -gt 0 ]; then
  if ! { cp "$WORK" "$DB" && cmp -s "$WORK" "$DB"; }; then
    cp "$BAK" "$DB"
    echo "Sterne: Zurueckkopieren ging nicht, Sicherung zurueckgespielt (liegt in $DIR)"; rm -f "$WORK" "$DIR/.erledigt.json"; exit 0
  fi
fi
python3 "$PY" --fertig
rm -f "$WORK"
