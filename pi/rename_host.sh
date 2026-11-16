#!/bin/bash
# rename_host.sh NEUERNAME  -  Rechnernamen des Pi aendern (als root, wird von "./deploy.sh rename" aufgerufen).
# Aendert /etc/hostname (hostnamectl) und die Zeile 127.0.1.1 in /etc/hosts und startet den Pi nach 5 s neu.
# Dienst "lichtshow", Ordner ~/lichtshow und Benutzer bleiben unveraendert.
set -e
NEW="$1"
if ! [[ "$NEW" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
  echo "Ungueltiger Name '$NEW': nur Kleinbuchstaben, Ziffern und Bindestrich, nicht am Anfang oder Ende."
  exit 2
fi
if [ "$(id -u)" != "0" ]; then
  echo "Bitte mit sudo aufrufen."
  exit 3
fi
OLD="$(hostname)"
hostnamectl set-hostname "$NEW"
if grep -q '^127\.0\.1\.1' /etc/hosts; then
  sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$NEW/" /etc/hosts
else
  printf '127.0.1.1\t%s\n' "$NEW" >> /etc/hosts
fi
echo "Rechnername geaendert: $OLD -> $NEW. Der Pi startet in 5 Sekunden neu."
# Neustart als eigener systemd-Auftrag: er laeuft weiter, auch wenn die ssh-Verbindung gleich endet
systemd-run --on-active=5 /bin/systemctl reboot >/dev/null 2>&1 || nohup sh -c 'sleep 5; systemctl reboot' >/dev/null 2>&1 &
