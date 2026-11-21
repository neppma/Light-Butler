#!/bin/bash
# Einspielen auf den Raspberry Pi. Aufruf im Projektordner:  ./deploy.sh <befehl>
#   check        alle Tests lokal ausfuehren
#   push -n      zeigt nur, was kopiert wuerde (Trockenlauf)
#   push         kopiert pi/ (und docs/HANDBUCH.md, docs/MANUAL_EN.md, TECHNIK.md, TECHNICAL_EN.md) nach ~/lichtshow auf dem Pi und prueft dort die Dateien (startet NICHT neu)
#   restart      startet den Dienst "lichtshow" am Pi neu (das Licht ist ca. 5 s aus)
#   alles        alles in einem: push (mit Tests), restart nur wenn sich Programmdateien am Pi geaendert haben, Mixxx-App und
#                Light-Butler Helfer am Mac neu installieren; laeuft "Light-Butler Mixxx", wartet er, bis du sie beendest,
#                und startet sie danach selbst wieder
#   status       Dienststatus
#   logs [N]     die letzten N Zeilen des Dienst-Logs (Standard 60)
#   pull-state   holt die Zustandsdateien (settings.json, scenes.json ...) nach ./pi_state (nur Kopie, nicht im Git)
#   where        zeigt, welcher Pi angesprochen wird
#   rename NAME  Rechnernamen des Pi aendern (zum Beispiel lightbutler), Pi startet neu; traegt den neuen Namen am Mac ein
# Der Pi steht in ~/.light-butler-pi (eine Zeile, zum Beispiel lightbutler.local), gemeinsam fuer deploy.sh,
# die Mixxx-App und den Light-Butler Helfer. Ohne Datei: lightbutler.local.
# Einstellungen per Umgebung:  S2L_PI=admin@lightbutler.local   S2L_DEST=~/lichtshow   S2L_PI_FILE=...   S2L_OHNE_MAIN=1 (push trotz fehlender Commits aus main)
set -e
cd "$(dirname "$0")"
PI_FILE="${S2L_PI_FILE:-$HOME/.light-butler-pi}"
PI_HOST="lightbutler.local"
[ -s "$PI_FILE" ] && PI_HOST="$(head -n 1 "$PI_FILE" | tr -d '[:space:]')"
PI="${S2L_PI:-admin@$PI_HOST}"
RUN="${S2L_DRY:+echo}"                # S2L_DRY=1: ssh/scp nur anzeigen (Tests)
DEST="${S2L_DEST:-lichtshow}"      # relativ zum Home des Benutzers auf dem Pi
# Diese Dateien gehoeren dem Pi und werden NIE ueberschrieben (Einstellungen, Szenen, Token, Startoptionen):
EXCL=(--exclude '__pycache__' --exclude '*.pyc' --exclude '*.json' --exclude '*.json.alt' --exclude 'show.conf' --exclude '/shows/'
      --exclude 'backup.conf' --exclude '*.bak' --exclude '.DS_Store' --exclude '/aufnahmen/')

# Light-Butler.exe fuer Windows (15.11.2026): wird am Windows-PC gebaut (windows/build_exe.py), das ZIP kommt hierher und
# push kopiert es auf den Pi (pakete/windows), von dort ist es ein Download in den Einstellungen und auf dem Stick
EXE_ZIP="${S2L_EXE_ZIP:-windows/build/light-butler-windows-exe.zip}"
# Mac-Paket zum Herunterladen (pakete/mac): ohne Zwischendateien und eigene Daten
PAKET_EXCL=(--exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' --exclude 'analysis' --exclude 'autotag' --exclude 'doppelte'
            --exclude 'energie' --exclude 'tonart' --exclude 'ordner' --exclude '*.sqlite' --exclude '*.log')

need_rsync() { command -v rsync >/dev/null || { echo "rsync fehlt (am Mac vorhanden, am Pi: sudo apt install rsync)"; exit 1; }; }

# Jeder Chat arbeitet in einem eigenen Ordner mit eigenem Zweig. Fehlt hier etwas, das schon in main ist, wuerde es auf dem Pi ueberschrieben.
missing_main() { git log --oneline HEAD..main 2>/dev/null || true; }
warn_main() {
  echo "ACHTUNG: In diesem Ordner fehlt, was schon in main ist:"
  echo "$1" | sed 's/^/  /'
  echo "Auf dem Pi wuerde das ueberschrieben."
}

case "$1" in
  check)
    bash tests/run_all.sh ;;
  push)
    need_rsync
    MISSING="$(missing_main)"
    if [ -n "$MISSING" ]; then
      warn_main "$MISSING"
      if [ "$2" != "-n" ] && [ -z "$S2L_OHNE_MAIN" ]; then
        echo "Es wird nichts kopiert. Zuerst main hierher holen (git merge main, oder im Chat: \"hol main\")."
        echo "Mit Absicht trotzdem: S2L_OHNE_MAIN=1 ./deploy.sh push"
        exit 1
      fi
      echo
    fi
    if [ "$2" = "-n" ]; then
      rsync -avn --itemize-changes "${EXCL[@]}" pi/ "$PI:$DEST/"
      rsync -avn --itemize-changes docs/HANDBUCH.md "$PI:$DEST/HANDBUCH.md"     # Handbuch fuer den Hilfe-Knopf
      rsync -avn --itemize-changes docs/MANUAL_EN.md "$PI:$DEST/MANUAL_EN.md"   # englisches Handbuch
      rsync -avn --itemize-changes docs/TECHNIK.md docs/TECHNICAL_EN.md "$PI:$DEST/"   # Technische Beschreibung
      [ -f docs/MEINE_ANLAGE.md ] && rsync -avn --itemize-changes docs/MEINE_ANLAGE.md "$PI:$DEST/MEINE_ANLAGE.md"   # Seite Meine Anlage
      rsync -avn --itemize-changes mac/stems/stems_show.py mac/stems/stem_curves.py mac/stems/install_stems.ps1 "$PI:$DEST/helfer/"
      rsync -an --itemize-changes "${PAKET_EXCL[@]}" mac/install_mac.sh mac/mixxx_bridge mac/helper mac/stems "$PI:$DEST/pakete/mac/"
      [ -s "$EXE_ZIP" ] && rsync -an --itemize-changes "$EXE_ZIP" "$PI:$DEST/pakete/windows/"
      echo; echo "Trockenlauf: nichts wurde kopiert."
    else
      # Ausgabe der Tests aufheben: schlaegt einer fehl, steht hier, welcher (Fehlerbericht 11.11.2026: nur "fehlgeschlagen", ohne Namen)
      TESTLOG="${TMPDIR:-/tmp}/lightbutler-tests.log"
      echo "Tests laufen ..."
      if bash tests/run_all.sh >"$TESTLOG" 2>&1; then
        echo "Tests ok."
      else
        echo "Tests fehlgeschlagen, es wird nichts kopiert. Diese Pruefungen gingen nicht:"
        awk '/^== tests\//{f=$2} /FEHLER|Traceback/ && !/siehe oben/{print "  " f ": " $0}' "$TESTLOG" | tail -20
        echo "Ganze Ausgabe: $TESTLOG"
        exit 1
      fi
      rsync -av "${EXCL[@]}" pi/ "$PI:$DEST/"
      rsync -av docs/HANDBUCH.md "$PI:$DEST/HANDBUCH.md"                        # Handbuch fuer den Hilfe-Knopf
      rsync -av docs/MANUAL_EN.md "$PI:$DEST/MANUAL_EN.md"                      # englisches Handbuch
      rsync -av docs/TECHNIK.md docs/TECHNICAL_EN.md "$PI:$DEST/"               # Technische Beschreibung (/help/technik)
      [ -f docs/MEINE_ANLAGE.md ] && rsync -av docs/MEINE_ANLAGE.md "$PI:$DEST/MEINE_ANLAGE.md"   # Seite Meine Anlage (nur hier, nie in Paketen)
      rsync -av mac/stems/stems_show.py mac/stems/stem_curves.py mac/stems/install_stems.ps1 "$PI:$DEST/helfer/"   # Pegelkurven-Helfer zum Herunterladen (/helfer/, Windows-PC)
      ssh "$PI" "mkdir -p $DEST/pakete/mac"
      rsync -a --delete "${PAKET_EXCL[@]}" mac/install_mac.sh mac/mixxx_bridge mac/helper mac/stems "$PI:$DEST/pakete/mac/"   # Mac-Paket (Einstellungen: Download)
      if [ -s "$EXE_ZIP" ]; then                 # Light-Butler.exe (am Windows-PC gebaut, hier abgelegt): Download in den Einstellungen
        ssh "$PI" "mkdir -p $DEST/pakete/windows"
        rsync -a "$EXE_ZIP" "$PI:$DEST/pakete/windows/"
      else
        echo "Hinweis: keine Light-Butler.exe in $EXE_ZIP (der Download zeigt am Pi weiter die vorige oder einen Hinweis)."
      fi
      echo; echo "Dateien pruefen am Pi ..."
      ssh "$PI" "cd $DEST && python3 phase2_test.py --check | tail -2"
      echo; echo "Kopiert. Zum Uebernehmen: ./deploy.sh restart"
    fi ;;
  restart)
    ssh -t "$PI" "sudo systemctl restart lichtshow && sleep 3 && systemctl status lichtshow --no-pager | head -12" ;;
  alles)
    # Einspielen in einem Befehl (Wunsch 07.11.2026): nur das sudo-Passwort und das Beenden der Mixxx-App bleiben bei dir
    need_rsync
    echo "== 1/4 Was sich am Pi aendert =="
    # Vergleich mit dem Pi; schlaegt er fehl (Verbindung hakt), sicherheitshalber neu starten (Fehlerbericht 21.11.2026:
    # Fehler wurde verschluckt, "keine Programmdateien", der Pi lief mit dem alten Programm weiter)
    if RAW="$(rsync -ain "${EXCL[@]}" pi/ "$PI:$DEST/" 2>/dev/null)"; then
      CHANGED="$(echo "$RAW" | awk '$1 ~ /^[<>c]f/ {print $2}')"
      PROG="$(echo "$CHANGED" | grep -E '\.(py|yaml|service|sh)$' | grep -v '^static/' || true)"
    else
      PROG="(Vergleich mit dem Pi nicht moeglich, sicherheitshalber Neustart)"
    fi
    if [ -n "$PROG" ]; then echo "Programmdateien:"; echo "$PROG" | sed 's/^/  /'; else echo "keine Programmdateien (nur Seiten oder nichts): kein Neustart noetig"; fi
    echo; echo "== 2/4 Kopieren auf den Pi (mit Tests) =="
    bash "$0" push
    if [ -z "$PROG" ]; then
      # Laeuft am Pi noch ein aelteres Programm als die Dateien dort (zum Beispiel von einem anderen Chat nur kopiert)?
      STALE="$(ssh "$PI" 'p=$(systemctl show -p MainPID --value lichtshow 2>/dev/null); [ -n "$p" ] && [ "$p" != 0 ] && find '"$DEST"' -maxdepth 2 -name "*.py" -newermt "$(ps -o lstart= -p $p)" -print 2>/dev/null | head -5' 2>/dev/null || true)"
      if [ -n "$STALE" ]; then PROG="$STALE"; echo; echo "Am Pi laeuft noch ein aelteres Programm als diese Dateien:"; echo "$STALE" | sed 's/^/  /'; fi
    fi
    if [ -n "$PROG" ]; then
      echo; echo "== 3/4 Pi neu starten (das Licht ist ca. 5 s aus; sudo-Passwort am Pi eintippen) =="
      bash "$0" restart
    else
      echo; echo "== 3/4 Pi: kein Neustart noetig =="
    fi
    echo; echo "== 4/4 Mac: Mixxx-App und Helfer =="
    # nur die laufende Bruecke der App ("python3 mixxx_bridge.py --stdin"), nicht jeder Befehl, in dem der Dateiname vorkommt
    # (Fehlerbericht 14.11.2026: ein Testlauf mit "git add mac/mixxx_bridge/mixxx_bridge.py" hielt das Warten 5 Minuten fest)
    BRIDGE_ON=""; pgrep -f "mixxx_bridge\.py --stdin" >/dev/null 2>&1 && BRIDGE_ON=1
    S2L_PI="$PI_HOST" S2L_NO_OPEN=1 bash mac/mixxx_bridge/install_launcher.sh | tail -3
    if [ -d "$HOME/Light-Butler-Helfer" ]; then
      AUTO=n; [ -f "$HOME/Library/LaunchAgents/local.lightbutler.helfer.plist" ] && AUTO=j   # Autostart bleibt, wie er war
      S2L_PI="$PI_HOST" S2L_AUTOSTART="$AUTO" S2L_NO_OPEN=1 bash mac/helper/install_helper.sh | tail -2
      pkill -f "helper.py" 2>/dev/null || true
      for _ in $(seq 1 20); do pgrep -f "helper.py" >/dev/null 2>&1 || break; sleep 0.5; done   # erst ganz beendet, dann neu
      # Fehlerbericht 11.11.2026: nach pkill blieb der Helfer manchmal aus (open traf noch die alte App). Pruefen, sonst nochmal.
      HOK=""
      for _try in 1 2 3; do
        open -g -a "Light-Butler Helfer" 2>/dev/null
        for _ in $(seq 1 20); do pgrep -f "helper.py" >/dev/null 2>&1 && { HOK=1; break; }; sleep 0.5; done
        [ -n "$HOK" ] && break
        sleep 2
      done
      [ -n "$HOK" ] && echo "Helfer neu gestartet." || echo "Helfer startet nicht: bitte von Hand starten (open -g -a \"Light-Butler Helfer\")"
    fi
    if [ -n "$BRIDGE_ON" ]; then
      echo
      echo ">>> Bitte jetzt \"Light-Butler Mixxx\" ueber das Symbol im Dock beenden (Rechtsklick -> Beenden)."
      echo "    Ich warte darauf und starte die App danach wieder (hoechstens 5 Minuten, Abbruch mit Ctrl+C)."
      for _ in $(seq 1 300); do pgrep -f "mixxx_bridge\.py --stdin" >/dev/null 2>&1 || break; sleep 1; done
      if pgrep -f "mixxx_bridge\.py --stdin" >/dev/null 2>&1; then
        echo "Die App laeuft noch. Spaeter beenden und mit  open ~/Applications/Light-Butler\ Mixxx.app  starten."
      else
        sleep 2; open "$HOME/Applications/Light-Butler Mixxx.app" && echo "Light-Butler Mixxx neu gestartet."
      fi
    else
      echo "Light-Butler Mixxx laeuft nicht: beim naechsten Start ist die neue Fassung dabei."
    fi
    echo; echo "Fertig." ;;
  status)
    ssh "$PI" "systemctl status lichtshow --no-pager | head -14" ;;
  logs)
    ssh "$PI" "journalctl -u lichtshow -n ${2:-60} --no-pager" ;;
  where)
    echo "$PI" ;;
  rename)
    NEW="$2"
    if ! [[ "$NEW" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
      echo "Aufruf: ./deploy.sh rename NAME  (nur Kleinbuchstaben, Ziffern, Bindestrich; zum Beispiel lightbutler)"; exit 2
    fi
    HOSTPART="${PI#*@}"
    case "$HOSTPART" in *.*) DOMAIN=".${HOSTPART#*.}" ;; *) DOMAIN="" ;; esac
    NEWHOST="$NEW$DOMAIN"
    if [ -z "$S2L_YES" ]; then
      read -r -p "Pi $HOSTPART in $NEWHOST umbenennen? Er startet danach neu (Licht etwa 1 Minute aus). [j/N] " ANS
      case "$ANS" in j|J|ja|Ja) ;; *) echo "Abgebrochen."; exit 1 ;; esac
    fi
    $RUN scp pi/rename_host.sh "$PI:$DEST/rename_host.sh"
    $RUN ssh -t "$PI" "sudo bash $DEST/rename_host.sh $NEW"
    # Neuen Namen am Mac eintragen: deploy.sh, Mixxx-App, Light-Butler Helfer
    echo "$NEWHOST" > "$PI_FILE"
    for d in "$HOME/Light-Butler-Daten"; do      # Datenordner
      [ -f "$d/pi_host" ] && echo "$NEWHOST" > "$d/pi_host"
      if [ -f "$d/config.sh" ]; then
        sed -i.bak "s/^PI=.*/PI=\"$NEWHOST\"/" "$d/config.sh" && rm -f "$d/config.sh.bak"
      fi
    done
    [ -f "$HOME/Light-Butler-Helfer/pi_host" ] && echo "$NEWHOST" > "$HOME/Light-Butler-Helfer/pi_host"
    echo
    echo "Neuer Name am Mac eingetragen: $NEWHOST (deploy.sh, Mixxx-App, Helfer)."
    echo "Bitte: die App Light-Butler Mixxx und den Light-Butler Helfer einmal beenden und neu starten."
    echo "Das Panel heisst jetzt http://$NEWHOST:8080/ (Lesezeichen anpassen)."
    echo "Kennt die FRITZ!Box den neuen Namen nach 2 Minuten nicht: Heimnetz -> Netzwerk -> Pi -> Name aendern." ;;
  pull-state)
    need_rsync
    mkdir -p pi_state
    rsync -av --include='*.json' --include='show.conf' --exclude='*' "$PI:$DEST/" pi_state/
    echo "Kopie liegt in ./pi_state (nicht im Git, enthaelt den Nanoleaf-Token)." ;;
  *)
    sed -n '2,15p' "$0"; exit 1 ;;
esac
