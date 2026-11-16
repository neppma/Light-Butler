#!/bin/bash
# install_pi.sh - Light-Butler frisch auf einem Raspberry Pi einrichten (Wunsch von Markus, 12.11.2026).
# Fuer Raspberry Pi OS (64 Bit, Bookworm oder neuer), Pi 3, 4 oder 5. Aus dem Download "Pi: frische Installation" im Panel
# (Einstellungen, ganz unten), entpackt im Home-Ordner des Benutzers:
#     cd ~/Light-Butler-Pi && bash install_pi.sh
# Fragt einmal nach dem Passwort (sudo) fuer Systempakete und Dienst.
#
# Was es tut:
#   1. Systempakete (Python, numpy, PyYAML, MIDI, Audio, ffmpeg ...) mit apt
#   2. Python-Umgebung ~/venv (nutzt die Systempakete mit, dazu sounddevice)
#   3. Programme nach ~/lichtshow kopieren. Vorhandene Einstellungen, Szenen, Shows, Geraete (fixtures.yaml,
#      homematic.yaml) und Startoptionen (show.conf) werden nie ueberschrieben: noch einmal ausfuehren = aktualisieren.
#   4. Beim ersten Mal: alle Ausgaben AUS (DMX, WLED, Nanoleaf). Laufen zwei Light-Butler im selben Netz und senden
#      beide, kaempfen sie ums Licht. Einschalten im Panel unter Einstellungen -> Ausgabe, wenn nur dieser sendet.
#   5. Dienst "lichtshow" (startet mit dem Pi), naechtliche Sicherung (04:30), Knopf "Pi herunterfahren".
# Strobe-Erlaubnis, Laser und Nebel bleiben aus, wie bei jeder neuen Anlage.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/lichtshow"
USER_NAME="$(whoami)"
HOME_DIR="${S2L_HOME:-$HOME}"
DEST="$HOME_DIR/lichtshow"
VENV="$HOME_DIR/venv"
SUDO="${S2L_SUDO-sudo}"                       # Tests: S2L_SUDO= (leer) und S2L_NO_SYSTEM=1
UNIT_DIR="${S2L_UNIT_DIR:-/etc/systemd/system}"

if [ "$(id -u)" -eq 0 ] && [ -z "$S2L_NO_SYSTEM" ]; then
  echo "Bitte ohne sudo starten:  bash install_pi.sh   (das Skript fragt selbst nach dem Passwort)"
  exit 1
fi
if [ ! -f "$SRC/show.py" ]; then
  echo "Der Ordner lichtshow fehlt neben install_pi.sh. Bitte das ZIP vollstaendig entpacken."
  exit 1
fi

echo "== Light-Butler einrichten fuer $USER_NAME in $DEST =="

if [ -z "$S2L_NO_SYSTEM" ]; then
  echo "== 1/5 Systempakete (dauert beim ersten Mal einige Minuten) =="
  $SUDO apt-get update
  $SUDO apt-get install -y python3 python3-venv python3-pip python3-numpy python3-yaml python3-mido python3-rtmidi \
    python3-serial python3-cffi libportaudio2 alsa-utils ffmpeg lame rsync
  $SUDO apt-get install -y python3-aubio || echo "Hinweis: aubio (Beat-Erkennung) nicht verfuegbar, es geht auch ohne."

  echo "== 2/5 Python-Umgebung $VENV =="
  [ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade sounddevice
else
  echo "(Test: Systempakete und Python-Umgebung uebersprungen)"
fi

echo "== 3/5 Programme nach $DEST =="
mkdir -p "$DEST"
# Programme immer neu; was dem Pi gehoert, nie (wie deploy.sh): *.json, show.conf, backup.conf, shows/, aufnahmen/
rsync -a --exclude '*.json' --exclude 'show.conf' --exclude 'backup.conf' --exclude '/shows/' --exclude '/aufnahmen/' \
  --exclude 'fixtures.yaml' --exclude 'homematic.yaml' --exclude '__pycache__' "$SRC/" "$DEST/"
for f in fixtures.yaml homematic.yaml; do                     # Geraete: nur beim ersten Mal
  if [ -f "$SRC/$f" ] && [ ! -f "$DEST/$f" ]; then cp "$SRC/$f" "$DEST/$f"; echo "  $f angelegt"; fi
done
if [ ! -f "$DEST/show.conf" ]; then
  cp "$SRC/show.conf" "$DEST/show.conf"
  echo "  show.conf angelegt (Startoptionen, ohne Strobe-Erlaubnis)"
fi
if [ ! -f "$DEST/settings.json" ]; then                        # erster Start: alle Ausgaben aus
  printf '{\n "ola_out": 0.0,\n "wled_out": 0.0,\n "nano_out": 0.0\n}\n' > "$DEST/settings.json"
  printf '{"ok": false}\n' > "$DEST/sicherheit.json"      # Sicherheitshinweis beim ersten Oeffnen des Panels (safety.py)
  echo "  Ausgaben aus (DMX, WLED, Nanoleaf): im Panel unter Einstellungen -> Ausgabe einschalten"
fi

echo "== 4/5 Dienst lichtshow =="
if [ -z "$S2L_NO_SYSTEM" ] || [ -n "$S2L_UNIT_DIR" ]; then
  sed -e "s#/home/admin/venv#$VENV#g" -e "s#/home/admin/lichtshow#$DEST#g" -e "s#^User=.*#User=$USER_NAME#" \
    "$DEST/lichtshow.service" > "$HOME_DIR/.lichtshow.service.tmp"
  $SUDO install -m 0644 "$HOME_DIR/.lichtshow.service.tmp" "$UNIT_DIR/lichtshow.service"
  rm -f "$HOME_DIR/.lichtshow.service.tmp"
fi
if [ -z "$S2L_NO_SYSTEM" ]; then
  $SUDO usermod -aG audio "$USER_NAME" || true                 # Soundkarte lesen
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable lichtshow
  $SUDO systemctl restart lichtshow

  echo "== 5/5 Sicherung (taeglich 04:30) und Knopf Pi herunterfahren =="
  (cd "$DEST" && $SUDO bash install_backup.sh) || echo "Hinweis: Sicherung nicht eingerichtet"
  $SUDO bash "$DEST/install_poweroff.sh" "$USER_NAME" || echo "Hinweis: Knopf Herunterfahren nicht eingerichtet"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Fertig. Panel im Browser:  http://$(hostname).local:8080/   oder   http://${IP:-<IP-des-Pi>}:8080/"
echo "Erste Schritte: Einstellungen -> Verbindungen (Audio-Eingang), Fixtures (Geraete anlegen), dann Ausgabe einschalten."
echo "Ersatzgeraet: die Sicherung vom Haupt-Pi einspielen (siehe LIESMICH.txt), erst dann die Ausgaben einschalten."
