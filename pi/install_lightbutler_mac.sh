#!/bin/bash
# install_lightbutler_mac.sh - den Light-Butler selbst (Licht, Panel, Shows) auf einem Mac einrichten (Wunsch von Markus,
# 15.11.2026). Aus dem Download "Mac: ganzer Light-Butler" im Panel. ZIP entpacken, im Terminal im Ordner:
#     bash install_lightbutler_mac.sh
# Kein Administrator-Passwort noetig.
#
# Was es tut:
#   1. python3 (3.9 oder neuer) suchen, Umgebung <Ziel>/venv mit numpy, PyYAML, sounddevice, mido, python-rtmidi, pyserial.
#      aubio (Beat-Erkennung) nur, wenn es sich installieren laesst; sonst nimmt die Tempo-Erkennung den Ersatz tempo_np.py.
#   2. Programme nach <Ziel>/lichtshow kopieren. Vorhandene Einstellungen, Szenen, Shows, Geraete (fixtures.yaml,
#      homematic.yaml) und Startoptionen (show.conf) werden nie ueberschrieben: noch einmal ausfuehren = aktualisieren.
#   3. Beim ersten Mal: alle Ausgaben AUS (DMX, WLED, Nanoleaf). Laufen zwei Light-Butler im selben Netz und senden
#      beide, kaempfen sie ums Licht. Einschalten im Panel unter Einstellungen -> Ausgabe, wenn nur dieser sendet.
#   4. Autostart beim Anmelden ueber launchd (~/Library/LaunchAgents/light-butler.show.plist, startet nach einem Absturz
#      neu) und die taegliche Sicherung um 04:30 (light-butler.backup.plist, nach <Ziel>/backups).
#      Meldungen: ~/Library/Logs/Light-Butler/show.log
# Strobe-Erlaubnis, Laser und Nebel bleiben aus, wie bei jeder neuen Anlage.
# Helfer und Mixxx-Bruecke kommen aus dem eigenen Paket "Mac: Mixxx-Bruecke und Helfer" (install_mac.sh, als Adresse des
# Light-Butler dann localhost angeben).
#
# Optionen:  --ziel ORDNER      anderer Ort (Standard ~/Light-Butler)
#            --ohne-autostart   keinen Autostart einrichten (Start von Hand: bash <Ziel>/start.sh)
#            --entfernen        Autostart, Sicherung und Python-Umgebung entfernen; Programme und Daten bleiben
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ZIEL="$HOME/Light-Butler"
AUTOSTART=1
REMOVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --ziel) ZIEL="$2"; shift 2 ;;
    --ohne-autostart) AUTOSTART=0; shift ;;
    --entfernen) REMOVE=1; shift ;;
    *) echo "Unbekannte Option: $1"; exit 2 ;;
  esac
done
case "$ZIEL" in /*) ;; *) ZIEL="$(pwd)/$ZIEL" ;; esac
SRC="$HERE/lichtshow"
DEST="$ZIEL/lichtshow"
VENV="$ZIEL/venv"
START="$ZIEL/start.sh"
LOGDIR="$HOME/Library/Logs/Light-Butler"
AGENTS="${S2L_AGENT_DIR:-$HOME/Library/LaunchAgents}"
L_SHOW="light-butler.show"
L_BACKUP="light-butler.backup"
GUI="gui/$(id -u)"

agent_off() {                       # Dienst anhalten und abmelden (still, wenn er nicht laeuft)
  [ -n "$S2L_NO_LAUNCHD" ] && return 0
  launchctl bootout "$GUI/$1" >/dev/null 2>&1 || true
}

if [ "$REMOVE" = 1 ]; then
  agent_off "$L_SHOW"; agent_off "$L_BACKUP"
  rm -f "$AGENTS/$L_SHOW.plist" "$AGENTS/$L_BACKUP.plist" "$START"
  rm -rf "$VENV"
  echo "Entfernt: Autostart, Sicherung und $VENV. Programme und Daten bleiben in $DEST (von Hand loeschen, wenn gewuenscht)."
  exit 0
fi

[ -f "$SRC/show.py" ] || { echo "lichtshow/show.py fehlt neben diesem Skript (ZIP vollstaendig entpackt?)"; exit 1; }

echo "== 1/4 Python =="
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import venv, sys; assert sys.version_info >= (3, 9)" 2>/dev/null; then
  echo "python3 (3.9 oder neuer) fehlt. Entweder im Terminal  xcode-select --install  oder Python 3.12 von python.org."
  exit 1
fi
echo "python3 $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])') gefunden."
agent_off "$L_SHOW"                 # laufenden Light-Butler anhalten, bevor die Programme erneuert werden
[ -x "$VENV/bin/python3" ] || python3 -m venv "$VENV"
if [ -n "$S2L_NO_PIP" ]; then                # nur Tests: ohne Pakete aus dem Internet
  echo "  (Tests: Python-Pakete nicht installiert)"
else
"$VENV/bin/python3" -m pip install -q --upgrade pip
"$VENV/bin/python3" -m pip install -q numpy pyyaml sounddevice mido python-rtmidi pyserial
"$VENV/bin/python3" -m pip install -q aubio >/dev/null 2>&1 \
  || echo "Hinweis: aubio liess sich nicht installieren, die Beat-Erkennung nimmt den Ersatz tempo_np (geht auch)."
fi

echo "== 2/4 Programme nach $DEST =="
mkdir -p "$DEST" "$LOGDIR"
# Programme immer neu; was dieser Anlage gehoert, nie (wie deploy.sh am Pi): *.json, show.conf, backup.conf, Geraete, shows/
rsync -a --exclude '*.json' --exclude show.conf --exclude backup.conf --exclude fixtures.yaml --exclude homematic.yaml \
  --exclude shows/ --exclude aufnahmen/ --exclude __pycache__/ "$SRC/" "$DEST/"
for f in fixtures.yaml homematic.yaml show.conf; do          # nur beim ersten Mal
  if [ -f "$SRC/$f" ] && [ ! -f "$DEST/$f" ]; then cp "$SRC/$f" "$DEST/$f"; echo "  $f angelegt"; fi
done

echo "== 3/4 Einstellungen =="
if [ ! -f "$DEST/settings.json" ]; then
  printf '{\n "ola_out": 0.0,\n "wled_out": 0.0,\n "nano_out": 0.0\n}\n' > "$DEST/settings.json"
  printf '{"ok": false}\n' > "$DEST/sicherheit.json"      # Sicherheitshinweis beim ersten Oeffnen des Panels (safety.py)
  echo "  Neue Anlage: alle Ausgaben AUS (DMX, WLED, Nanoleaf). Einschalten im Panel: Einstellungen -> Ausgabe."
else
  echo "  Vorhandene Einstellungen bleiben."
fi
if [ ! -f "$DEST/backup.conf" ]; then
  printf '{"dir": "%s/backups", "keep": 14, "copy_to": "", "include_secrets": true}\n' "$ZIEL" > "$DEST/backup.conf"
fi

# Startskript: liest show.conf (SHOW_ARGS=...) und startet den Light-Butler; ein Neustart aus dem Panel ersetzt den Prozess
cat > "$START" <<'EOS'
#!/bin/bash
# start.sh - startet den Light-Butler (von install_lightbutler_mac.sh angelegt). Optionen in lichtshow/show.conf.
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/lichtshow" || exit 1
ARGS="$(grep -E '^[[:space:]]*SHOW_ARGS=' show.conf 2>/dev/null | tail -1 | sed -E 's/^[[:space:]]*SHOW_ARGS=//')"
export PYTHONUNBUFFERED=1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Start: show.py $ARGS"
# shellcheck disable=SC2086
exec "$HERE/venv/bin/python3" -u show.py $ARGS
EOS
chmod +x "$START"

echo "== 4/4 Autostart =="
if [ "$AUTOSTART" = 1 ]; then
  mkdir -p "$AGENTS"
  cat > "$AGENTS/$L_SHOW.plist" <<EOP
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
 <key>Label</key><string>$L_SHOW</string>
 <key>ProgramArguments</key><array><string>/bin/bash</string><string>$START</string></array>
 <key>RunAtLoad</key><true/>
 <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
 <key>ThrottleInterval</key><integer>10</integer>
 <key>StandardOutPath</key><string>$LOGDIR/show.log</string>
 <key>StandardErrorPath</key><string>$LOGDIR/show.log</string>
</dict></plist>
EOP
  cat > "$AGENTS/$L_BACKUP.plist" <<EOP
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
 <key>Label</key><string>$L_BACKUP</string>
 <key>ProgramArguments</key><array><string>$VENV/bin/python3</string><string>$DEST/backup.py</string><string>--auto</string></array>
 <key>WorkingDirectory</key><string>$DEST</string>
 <key>StartCalendarInterval</key><dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>30</integer></dict>
 <key>StandardOutPath</key><string>$LOGDIR/backup.log</string>
 <key>StandardErrorPath</key><string>$LOGDIR/backup.log</string>
</dict></plist>
EOP
  if [ -z "$S2L_NO_LAUNCHD" ]; then
    agent_off "$L_BACKUP"
    launchctl bootstrap "$GUI" "$AGENTS/$L_BACKUP.plist"
    launchctl bootstrap "$GUI" "$AGENTS/$L_SHOW.plist"
    echo "  Light-Butler laeuft und startet beim Anmelden von selbst."
  fi
else
  echo "  Ohne Autostart. Starten:  bash $START"
fi

echo
if [ "$AUTOSTART" = 1 ]; then
  echo "Fertig. Panel: http://localhost:8080/  (Handy/iPad im Heimnetz: http://$(scutil --get LocalHostName 2>/dev/null || hostname).local:8080/)"
else
  echo "Fertig. Nach dem Start (bash $START) steht das Panel unter http://localhost:8080/"
fi
echo "Ton: Beim ersten Start fragt macOS vielleicht, ob Python das Mikrofon (den Ton-Eingang) benutzen darf: erlauben."
echo "     Kommt keine Frage und es bleibt still: Systemeinstellungen -> Datenschutz & Sicherheit -> Mikrofon."
echo "Helfer und Mixxx-Bruecke: Paket 'Mac: Mixxx-Bruecke und Helfer' (install_mac.sh), als Light-Butler localhost angeben."
