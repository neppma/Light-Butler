#!/bin/bash
# install_online.sh - Light-Butler mit einem einzigen Befehl auf einem Raspberry Pi installieren (Wunsch von Markus, 17.11.2026).
# Statt eines SD-Karten-Images (rund 1 GB): normales Raspberry Pi OS (64 Bit) mit dem Raspberry Pi Imager aufspielen, am Pi:
#     curl -sL https://raw.githubusercontent.com/neppma/Light-Butler/main/pi/install_online.sh | bash
# Holt das Paket light-butler-pi.zip (rund 12 MB) aus dem neuesten Release auf GitHub, packt es nach ~/Light-Butler-Pi aus
# und startet dort install_pi.sh (das fragt einmal nach dem Passwort). Noch einmal ausfuehren = aktualisieren: Einstellungen,
# Szenen, Shows und Geraete bleiben (install_pi.sh ueberschreibt sie nie). Neue Anlagen starten mit allen Ausgaben aus.
# Tests: S2L_ZIP_URL (eigene Adresse oder file://), S2L_HOME (Zielordner), S2L_NO_RUN=1 (install_pi.sh nicht starten),
#        S2L_SKIP_ARCH=1 (Pruefung auf 64 Bit auslassen).
set -e
ZIP_URL="${S2L_ZIP_URL:-https://github.com/neppma/Light-Butler/releases/latest/download/light-butler-pi.zip}"
HOME_DIR="${S2L_HOME:-$HOME}"
DIR="$HOME_DIR/Light-Butler-Pi"

echo "== Light-Butler: Installation auf diesem Raspberry Pi =="
if [ "$(id -u)" -eq 0 ] && [ -z "$S2L_NO_RUN" ]; then
  echo "Bitte ohne sudo starten (das Skript fragt selbst nach dem Passwort)."
  exit 1
fi
if [ -z "$S2L_SKIP_ARCH" ] && [ "$(uname -m)" != "aarch64" ]; then
  echo "Dieser Rechner ist kein Raspberry Pi mit 64-Bit-System ($(uname -m))."
  echo "Bitte mit dem Raspberry Pi Imager \"Raspberry Pi OS (64-bit)\" aufspielen. Windows und Mac: Setup.exe bzw. DMG von GitHub."
  exit 1
fi
for p in curl python3; do
  command -v "$p" >/dev/null 2>&1 || { echo "$p fehlt: sudo apt install $p"; exit 1; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Lade das Paket ..."
curl -fL --retry 3 -o "$TMP/light-butler-pi.zip" "$ZIP_URL" || { echo "Herunterladen ging nicht. Internet am Pi pruefen."; exit 1; }
# Auspacken mit Python (unzip fehlt manchmal); nur Dateien unter Light-Butler-Pi/, nie ausserhalb
python3 - "$TMP/light-butler-pi.zip" "$TMP/aus" <<'PY'
import os, sys, zipfile
z, out = zipfile.ZipFile(sys.argv[1]), os.path.realpath(sys.argv[2])
for n in z.namelist():
    p = os.path.realpath(os.path.join(out, n))
    if not n.startswith("Light-Butler-Pi/") or not p.startswith(out + os.sep):
        sys.exit("Paket unbrauchbar: " + n)
z.extractall(out)
PY
[ -f "$TMP/aus/Light-Butler-Pi/install_pi.sh" ] || { echo "Paket unbrauchbar (install_pi.sh fehlt)."; exit 1; }
if [ -e "$DIR" ]; then                          # Paket von frueher (die laufende Anlage liegt in ~/lichtshow): beiseite, nie loeschen
  rm -rf "$DIR.alt" && mv "$DIR" "$DIR.alt"
fi
mv "$TMP/aus/Light-Butler-Pi" "$DIR"
echo "Ausgepackt nach $DIR"

if [ -n "$S2L_NO_RUN" ]; then
  exit 0
fi
cd "$DIR"
# Ueber "curl | bash" ist die Eingabe das Skript selbst: Rueckfragen und Passwort kommen vom Terminal
if [ -r /dev/tty ]; then
  bash install_pi.sh < /dev/tty
else
  bash install_pi.sh
fi
echo
echo "Fertig. Panel im Browser: http://$(hostname).local:8080/"
