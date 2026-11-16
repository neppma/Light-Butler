#!/bin/bash
# Einmalig am Pi ausfuehren:  sudo bash ~/lichtshow/install_poweroff.sh
# Erlaubt dem Benutzer admin (unter dem der Dienst lichtshow laeuft) genau einen Befehl ohne Passwort:
# /usr/sbin/poweroff. Damit funktioniert der Knopf "Pi herunterfahren" im Web-Panel. Sonst aendert sich nichts.
# Rueckgaengig:  sudo rm /etc/sudoers.d/lichtshow-poweroff
set -e
if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo starten:  sudo bash ~/lichtshow/install_poweroff.sh"
  exit 1
fi
USER_NAME="${1:-admin}"
FILE=/etc/sudoers.d/lichtshow-poweroff
TMP=$(mktemp)
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/sbin/poweroff" > "$TMP"
if ! visudo -cf "$TMP" >/dev/null; then                      # Regel pruefen, bevor sie gilt
  echo "Fehler: die Regel ist ungueltig, es wurde nichts geaendert."
  rm -f "$TMP"
  exit 1
fi
install -m 0440 -o root -g root "$TMP" "$FILE"
rm -f "$TMP"
echo "Eingerichtet: $USER_NAME darf /usr/sbin/poweroff ohne Passwort ausfuehren ($FILE)."
echo "Der Knopf zum Herunterfahren im Panel funktioniert jetzt (kein Neustart noetig)."
