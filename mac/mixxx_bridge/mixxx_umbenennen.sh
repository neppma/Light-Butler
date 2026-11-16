#!/bin/bash
# Umbenannte Dateien in der Mixxx-Datenbank nachziehen (Wunsch von Markus, 08.11.2026).
# Die Seite "Dateien pruefen" merkt sich jede Umbenennung (alter Pfad <TAB> neuer Pfad) in ~/Light-Butler-Daten/umbenannt/offen.tsv.
# Das Startskript der App "Light-Butler Mixxx" ruft dieses Skript auf, BEVOR Mixxx startet (Mixxx darf nicht laufen): es aendert
# nur den Pfad in track_locations, darum bleiben Hotcues, Beatgrid, Kisten und Playlists. Vorher eine Sicherungskopie.
#
# Fehlerbericht 08.11.2026: sqlite3 durfte die Datenbank im Ordner von Mixxx nicht oeffnen ("unable to open database file"),
# obwohl cp sie lesen kann und die App Festplattenvollzugriff hat. Das Skript hielt das fuer "steht schon in Mixxx" und legte
# alles als erledigt ab. Jetzt:
#   1. Geht sqlite3 direkt, wird direkt geaendert.
#   2. Sonst ueber eine Kopie: Datenbank herauskopieren, die Kopie aendern und pruefen (integrity_check), zurueckkopieren und
#      vergleichen. Mixxx fuehrt die Datenbank im Journal-Modus "delete": nach dem Beenden steht alles in der einen Datei.
#      Liegt noch ein Journal daneben (Mixxx nicht sauber beendet), wird nichts angefasst.
#   3. Was nicht geklappt hat, bleibt in der Warteschlange; nur eindeutige Faelle (neuer Pfad wirklich schon da) fallen heraus.
#
# Aufruf:  bash mixxx_umbenennen.sh MIXXXDB [WARTESCHLANGE]      (S2L_KOPIE=1 erzwingt den Weg ueber die Kopie, fuer Tests)
DB="$1"
DATA="${S2L_DATA:-$HOME/Light-Butler-Daten}"
Q="${2:-$DATA/umbenannt/offen.tsv}"
UEB="$(cd "$(dirname "$0")" && pwd)/mixxx_uebertragen.py"   # Kisten/Listen/Hotcues fehlender Tracks auf den Zwilling (09.11.2026)
CUES="$DATA/cues/mixxx_neu.json"                             # geschaetzte Cues fuer Lieder ohne Hotcues (cue_estimate, 11.11.2026)
if [ ! -f "$DB" ]; then [ -s "$Q" ] && echo "Umbenennen: Mixxx-Datenbank nicht gefunden ($DB), bleibt fuer spaeter"; exit 0; fi
mkdir -p "$(dirname "$Q")"
need=0
if [ -f "$UEB" ]; then                                        # gibt es etwas zu uebertragen? (auf einer Lesekopie gezaehlt)
  RC="$(dirname "$Q")/.zaehlen.sqlite"
  if cp "$DB" "$RC" 2>/dev/null; then
    need="$(python3 "$UEB" "$RC" --ordner "$(dirname "$Q")" --cues "$CUES" --liste-nicht-analysiert --nur-zaehlen 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("geaendert", 0))' 2>/dev/null)"
    rm -f "$RC"
  else
    need=1                                                     # Lesekopie ging nicht (macOS sperrt manchmal kurz): trotzdem versuchen
  fi
fi
case "$need" in ''|*[!0-9]*) need=0 ;; esac
[ -s "$Q" ] || [ "$need" -gt 0 ] || exit 0
touch "$Q"
# Mixxx muss ganz beendet sein (Mixxx schliesst sich manchmal noch, waehrend die App schon neu startet)
[ -z "$S2L_TEST" ] && for _ in $(seq 1 30); do pgrep -x mixxx >/dev/null 2>&1 || pgrep -f "MacOS/mixxx" >/dev/null 2>&1 || break; sleep 1; done
if { pgrep -x mixxx >/dev/null 2>&1 || pgrep -f "MacOS/mixxx" >/dev/null 2>&1; } && [ -z "$S2L_TEST" ]; then echo "Umbenennen: Mixxx laeuft, bleibt fuer spaeter"; exit 0; fi
[ -z "$S2L_TEST" ] && sleep 2
DIR="$(dirname "$Q")"
STAMP="$(date +%Y%m%d-%H%M%S)"
n_open=$(grep -c . "$Q")
BAK="$DIR/mixxxdb-vor-umbenennen-$STAMP.sqlite"
[ -e "$BAK" ] && STAMP="$STAMP-$$" && BAK="$DIR/mixxxdb-vor-umbenennen-$STAMP.sqlite"   # zwei Laeufe in derselben Sekunde

blocked() {                                                    # nichts geaendert, alles bleibt in der Warteschlange
  echo "Umbenennen: $1. $n_open Umbenennungen bleiben in der Warteschlange."
  echo "$STAMP $1" > "$DIR/gesperrt.txt"
  if [ -z "$S2L_TEST" ]; then
    osascript -e "display dialog \"$n_open umbenannte Dateien konnten noch nicht in Mixxx eingetragen werden ($1).\n\nSie warten und kommen beim nächsten Start der App dran, Hotcues gehen nicht verloren. In Mixxx bis dahin nicht „Bibliothek neu einlesen“.\" with title \"Light-Butler Mixxx\" buttons {\"OK\"} default button \"OK\" with icon caution" >/dev/null 2>&1 &
  fi
  rm -f "$WORK" "$WORK-journal"
  exit 0
}

# Weg 1: direkt? (gleicher user_version-Wert zurueckgeschrieben: aendert nichts, zeigt nur, ob Schreiben geht)
MODE="direkt"; TARGET="$DB"; WORK=""; wr=""
if [ -z "$S2L_KOPIE" ]; then
  uv="$(sqlite3 -cmd ".timeout 5000" "$DB" "PRAGMA user_version;" 2>&1)"
  case "$uv" in ''|*[!0-9]*) wr="${uv:-leer}" ;; *) wr="$(sqlite3 -cmd ".timeout 5000" "$DB" "PRAGMA user_version=$uv;" 2>&1)" ;; esac
fi
{ cp "$DB" "$BAK" && chmod u+w "$BAK"; } || blocked "keine Sicherungskopie moeglich, nichts geaendert"
ls -1t "$DIR"/mixxxdb-vor-umbenennen-*.sqlite 2>/dev/null | tail -n +6 | while read -r old; do rm -f "$old"; done   # 5 Sicherungen
if [ -n "$wr" ] || [ -n "$S2L_KOPIE" ]; then
  # Weg 2: ueber eine Kopie
  [ -n "$wr" ] && echo "Umbenennen: direkt geht nicht ($wr), nehme den Weg ueber eine Kopie"
  if [ -e "$DB-journal" ] || [ -e "$DB-wal" ]; then blocked "Mixxx wurde nicht sauber beendet (Journal liegt neben der Datenbank)"; fi
  MODE="kopie"; WORK="$DIR/.arbeit-$STAMP.sqlite"; TARGET="$WORK"
  cp "$BAK" "$WORK" && chmod u+w "$WORK" || blocked "Arbeitskopie ging nicht"
  w2="$(sqlite3 "$WORK" "PRAGMA user_version=$(sqlite3 "$WORK" "PRAGMA user_version;");" 2>&1)"
  [ -z "$w2" ] || blocked "Arbeitskopie nicht beschreibbar ($w2)"
fi
rm -f "$DIR/gesperrt.txt"

ok=0; skip=0; keep=0
LEFT="$DIR/.offen-$STAMP.tsv"; DONE="$DIR/.ok-$STAMP.tsv"
: > "$LEFT"; : > "$DONE"
while IFS=$'\t' read -r OLD NEW; do
  [ -n "$OLD" ] && [ -n "$NEW" ] || continue
  q="'"                                                        # Hochkomma fuer SQL verdoppeln
  o="${OLD//$q/$q$q}"; n="${NEW//$q/$q$q}"
  f="$(basename "$NEW")"; d="$(dirname "$NEW")"
  f="${f//$q/$q$q}"; d="${d//$q/$q$q}"
  have="$(sqlite3 -cmd ".timeout 5000" "$TARGET" "SELECT count(*) FROM track_locations WHERE location='$n';" 2>/dev/null)"
  case "$have" in
    ''|*[!0-9]*) echo "Umbenennen: $OLD: Datenbank nicht lesbar, bleibt fuer spaeter"; printf '%s\t%s\n' "$OLD" "$NEW" >> "$LEFT"; keep=$((keep + 1)); continue ;;
  esac
  if [ "$have" != "0" ]; then
    echo "Umbenennen: $NEW steht schon in Mixxx (neu eingelesen?), alter Eintrag bleibt"; skip=$((skip + 1)); continue
  fi
  ch="$(sqlite3 -cmd ".timeout 5000" "$TARGET" "UPDATE track_locations SET location='$n', filename='$f', directory='$d', fs_deleted=0 WHERE location='$o'; SELECT changes();" 2>/dev/null)"
  case "$ch" in
    1) ok=$((ok + 1)); printf '%s\t%s\n' "$OLD" "$NEW" >> "$DONE" ;;
    0) echo "Umbenennen: $OLD nicht in Mixxx"; skip=$((skip + 1)) ;;
    *) echo "Umbenennen: $OLD: Schreiben ging nicht, bleibt fuer spaeter"; printf '%s\t%s\n' "$OLD" "$NEW" >> "$LEFT"; keep=$((keep + 1)) ;;
  esac
done < "$Q"

tr=0                                                           # Mixxx-Daten von fehlenden Tracks auf ihren Zwilling
if [ -f "$UEB" ]; then                                         # immer (aendert nur, was noch fehlt; 09.11.2026)
  # Fehlerbericht 09.11.2026: Python darf den Mixxx-Ordner nicht oeffnen ("unable to open database file"), sqlite3 und cp schon.
  # Direkt: Python rechnet auf einer Kopie, die geaenderte Kopie geht mit cp zurueck (wie beim Weg ueber eine Kopie).
  UT="$TARGET"
  if [ "$MODE" = "direkt" ]; then UT="$DIR/.uebertragen-$STAMP.sqlite"; { cp "$DB" "$UT" && chmod u+w "$UT"; } || UT=""; fi
  if [ -n "$UT" ] && out="$(python3 "$UEB" "$UT" --ordner "$DIR" --cues "$CUES" --liste-nicht-analysiert --protokoll "$DIR/uebertragen-$STAMP.json" 2>&1)"; then
    tr="$(printf '%s' "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("geaendert", 0))' 2>/dev/null)"
    case "$tr" in ''|*[!0-9]*) tr=0 ;; esac
    echo "Uebertragen: $out"
    if [ "$MODE" = "direkt" ] && [ "$tr" -gt 0 ]; then
      SNAP="$DIR/.vorher-$STAMP.sqlite"; cp "$DB" "$SNAP" 2>/dev/null
      chk="$(sqlite3 "$UT" "PRAGMA integrity_check;" 2>&1)"
      if [ "$chk" != "ok" ]; then echo "Uebertragen: Pruefung der Kopie: $chk, nichts uebernommen"; tr=0; rm -f "$DIR/uebertragen-$STAMP.json"
      elif ! cp "$UT" "$DB" 2>/dev/null || ! cmp -s "$UT" "$DB"; then
        echo "Uebertragen: Zurueckkopieren ging nicht, nichts uebernommen"; tr=0; rm -f "$DIR/uebertragen-$STAMP.json"
        cmp -s "$DB" "$SNAP" || cp "$SNAP" "$DB" 2>/dev/null       # halb geschrieben: Stand davor zurueck
      fi
      rm -f "$SNAP"
    fi
  elif [ -n "$UT" ]; then
    echo "Uebertragen ging nicht: $(printf '%s' "$out" | tail -1)"
  else
    echo "Uebertragen: Kopie der Mixxx-Datenbank ging nicht"
  fi
  [ "$MODE" = "direkt" ] && rm -f "$UT" "$UT-journal"
fi

if [ "$MODE" = "kopie" ] && { [ "$ok" -gt 0 ] || [ "$tr" -gt 0 ]; }; then
  chk="$(sqlite3 "$WORK" "PRAGMA integrity_check;" 2>&1)"
  back=""
  if [ "$chk" != "ok" ]; then back="Pruefung der geaenderten Kopie: $chk"
  elif ! cmp -s "$DB" "$BAK"; then back="Mixxx-Datenbank hat sich inzwischen geaendert"
  elif ! cp "$WORK" "$DB" 2>/dev/null || ! cmp -s "$WORK" "$DB"; then
    back="Zurueckkopieren in den Ordner von Mixxx ging nicht"
    cmp -s "$DB" "$BAK" || cp "$BAK" "$DB" 2>/dev/null       # halb geschrieben: Sicherung zurueck
  fi
  if [ -n "$back" ]; then                                      # nichts uebernommen: alle wieder in die Warteschlange
    cat "$DONE" >> "$LEFT"; keep=$((keep + ok)); ok=0; tr=0
    rm -f "$DIR/uebertragen-$STAMP.json"
    echo "Umbenennen: $back"
    echo "$STAMP $back" > "$DIR/gesperrt.txt"
  fi
fi
rm -f "$DONE" "$WORK" "$WORK-journal"
if [ -s "$Q" ]; then mv "$Q" "$DIR/erledigt-$STAMP.tsv"; else rm -f "$Q"; fi
if [ -s "$LEFT" ]; then mv "$LEFT" "$Q"; else rm -f "$LEFT"; fi
echo "Umbenennen ($MODE): $ok Pfade in Mixxx nachgezogen, $skip uebersprungen, $keep bleiben fuer spaeter, $tr Kisten/Listen/Hotcues/Werte uebertragen (Sicherung: $(basename "$BAK"))"
