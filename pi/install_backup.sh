#!/bin/bash
# Richtet die automatische nachtliche Sicherung ein (systemd-Zeitplan, taeglich 04:30).
#
# Aufruf auf dem Raspberry Pi, im Ordner der Lichtsteuerung (~/lichtshow):
#     sudo bash install_backup.sh
#
# Danach: Sicherungen liegen in ~/backups (die letzten 14), der erste Lauf passiert sofort.
# Pruefen:      systemctl list-timers lichtshow-backup.timer      und      python3 backup.py --list
# Ausschalten:  sudo systemctl disable --now lichtshow-backup.timer

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-$(whoami)}"
PYTHON="$(command -v python3)"
UNIT_DIR="${S2L_UNIT_DIR:-/etc/systemd/system}"

if [ -z "$S2L_NO_SYSTEMD" ] && [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo ausfuehren:  sudo bash install_backup.sh"
  exit 1
fi

cat > "$UNIT_DIR/lichtshow-backup.service" <<UNIT
[Unit]
Description=Sicherung der Lichtsteuerung (Einstellungen, Szenen, Programme)

[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=$HERE
ExecStart=$PYTHON $HERE/backup.py --auto
UNIT

cat > "$UNIT_DIR/lichtshow-backup.timer" <<UNIT
[Unit]
Description=Taegliche Sicherung der Lichtsteuerung

[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
UNIT

if [ -z "$S2L_NO_SYSTEMD" ]; then
  systemctl daemon-reload
  systemctl enable --now lichtshow-backup.timer
fi

echo "Zeitplan eingerichtet: taeglich 04:30 Uhr (verpasste Laeufe werden nachgeholt)."
echo "Erste Sicherung jetzt ..."
if [ "$(id -u)" -eq 0 ] && [ -n "$SUDO_USER" ]; then
  sudo -u "$SUDO_USER" "$PYTHON" "$HERE/backup.py" --now
else
  "$PYTHON" "$HERE/backup.py" --now
fi
