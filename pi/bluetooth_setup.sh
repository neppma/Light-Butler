#!/bin/bash
# bluetooth_setup.sh - den Licht-Rechner (Raspberry Pi) als Bluetooth-Empfaenger einrichten (Wunsch von Markus 24.11.2026).
# Einmal ausfuehren, mit sudo:
#     sudo bash ~/lichtshow/bluetooth_setup.sh
# Was es tut:
#   1. Pakete bluez-alsa-utils (Bluetooth-Ton, A2DP) und rfkill installieren
#   2. Bluetooth einschalten (die Funk-Sperre aufheben)
#   3. bluez-alsa als Empfaenger (a2dp-sink: Handy -> Pi) und als Sender (a2dp-source: Pi -> Bluetooth-Lautsprecher,
#      25.11.2026). Der Pi spielt den Ton nur ab, wenn im Panel "Ton weiterleiten an" gewaehlt ist (bluealsa-aplay
#      bleibt aus, der Light-Butler leitet selbst weiter).
#   4. In der Bluetooth-Liste erscheint der Pi als Lautsprecher; den Benutzer in die Gruppe bluetooth aufnehmen
#   5. Dem Light-Butler erlauben, das WLAN zu trennen und zu verbinden (polkit-Regel, Knopf im Panel, 25.11.2026):
#      Bluetooth und WLAN teilen sich einen Funkchip, am Kabel stoert das WLAN den Bluetooth-Ton
#   6. Dienste neu starten (das Licht ist dabei ein paar Sekunden aus)
# Sichtbar und koppelbar ist der Pi danach nur, wenn im Panel "Sichtbar machen" gedrueckt wird (3 Minuten).
set -e
if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo starten:  sudo bash $0"
  exit 1
fi
USER_NAME="${SUDO_USER:-admin}"
CONF=/etc/bluetooth/main.conf

echo "== 1/6 Pakete =="
apt-get update
apt-get install -y bluez-alsa-utils rfkill

echo "== 2/6 Bluetooth einschalten =="
rfkill unblock bluetooth || true

echo "== 3/6 bluez-alsa als Empfaenger und Sender =="
BIN="$(command -v bluealsad || command -v bluealsa || true)"
if [ -z "$BIN" ]; then
  echo "bluealsad nicht gefunden: ist bluez-alsa-utils richtig installiert?"
  exit 1
fi
mkdir -p /etc/systemd/system/bluealsa.service.d
printf '[Service]\nExecStart=\nExecStart=%s -S -p a2dp-sink -p a2dp-source\n' "$BIN" > /etc/systemd/system/bluealsa.service.d/light-butler.conf
systemctl disable --now bluealsa-aplay 2>/dev/null || true

echo "== 4/6 Als Lautsprecher anmelden =="
if [ -f "$CONF" ]; then
  [ -f "$CONF.vor-light-butler" ] || cp "$CONF" "$CONF.vor-light-butler"
  # Class: als Lautsprecher anzeigen. ControllerMode bredr: nur klassisches Bluetooth (Test 25.11.2026: ein iPhone hatte
  # sich sonst ueber Bluetooth Low Energy gekoppelt, das kann keine Musik, der Pi erschien nicht als Ausgabe).
  for KV in "Class = 0x240414" "ControllerMode = bredr"; do
    KEY="${KV%% *}"
    if grep -qE "^[#[:space:]]*$KEY[[:space:]]*=" "$CONF"; then
      sed -i -E "s/^[#[:space:]]*$KEY[[:space:]]*=.*/$KV/" "$CONF"
    else
      sed -i -E "s/^\[General\]/[General]\n$KV/" "$CONF"
    fi
  done
fi
usermod -aG bluetooth "$USER_NAME" || true

echo "== 5/6 WLAN-Schalter im Panel erlauben =="
if [ -d /etc/polkit-1/rules.d ]; then
  cat > /etc/polkit-1/rules.d/50-light-butler-wlan.rules <<EOR
// Light-Butler: der Dienst darf das WLAN trennen und verbinden (nmcli device) und den Funk einschalten
polkit.addRule(function(action, subject) {
  if ((action.id == "org.freedesktop.NetworkManager.enable-disable-wifi" ||
       action.id == "org.freedesktop.NetworkManager.network-control") && subject.user == "$USER_NAME") {
    return polkit.Result.YES;
  }
});
EOR
  chmod 644 /etc/polkit-1/rules.d/50-light-butler-wlan.rules
else
  echo "polkit nicht gefunden: der WLAN-Knopf im Panel bleibt gesperrt"
fi

echo "== 6/6 Dienste neu starten =="
systemctl daemon-reload
systemctl restart bluetooth
systemctl enable bluealsa
systemctl restart bluealsa
sleep 2
systemctl is-active bluealsa >/dev/null && echo "bluez-alsa laeuft." || { echo "bluez-alsa laeuft NICHT:"; systemctl status bluealsa --no-pager | head -15; }
if systemctl list-unit-files lichtshow.service >/dev/null 2>&1; then
  systemctl restart lichtshow
fi
echo
echo "Fertig. Im Panel: Einstellungen -> Audio-Eingang -> Bluetooth-Empfaenger -> Sichtbar machen, am Handy koppeln,"
echo "dann oben den Eingang Bluetooth waehlen."
