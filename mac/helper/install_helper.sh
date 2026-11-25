#!/bin/bash
# Installiert den "Light-Butler Helfer": APC mini mk2, Ton und Liedliste vom MacBook an den Light-Butler (Pi), ganz ohne Mixxx.
#
# Aufruf (im Projektordner, in Terminal):
#     bash mac/helper/install_helper.sh              installieren oder aktualisieren
#     bash mac/helper/install_helper.sh --uninstall  wieder entfernen
#
# Was passiert:
#   1. Python-Umgebung ~/s2l (falls noch nicht da) mit mido, python-rtmidi, numpy, scipy, soundfile und sounddevice.
#   2. Programmordner ~/Light-Butler-Helfer mit helper.py, apc_relay.py, audio_send.py, den Teilen der Mixxx-Bruecke fuer
#      Liedliste, Vorhoeren, Schaetzung und Analyse (laufen ohne Mixxx) und der Pi-Adresse.
#   3. Die App ~/Applications/Light-Butler Helfer.app (ohne Symbol im Dock, laeuft im Hintergrund).
#   4. Auf Wunsch startet sie bei jeder Anmeldung am Mac von selbst.
# Die App wird nur einmal angelegt: macOS merkt sich die Erlaubnis fuer das Mikrofon (BlackHole) pro App.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../mixxx_bridge"
BASE="$HOME/Light-Butler-Helfer"
APP="$HOME/Applications/Light-Butler Helfer.app"
AGENT="$HOME/Library/LaunchAgents/local.lightbutler.helfer.plist"
LOGDIR="$HOME/Library/Logs/Light-Butler"
PIDFILE="$HOME/.light-butler-helfer.pid"
LOCAL_DOMAIN="${S2L_DOMAIN:-local}"     # Domaene fuer einen Namen ohne Punkt (eigene: S2L_DOMAIN)

stop_helper() {
  if [ -s "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    sleep 1
  fi
}

if [ "$1" = "--uninstall" ]; then
  echo "== Light-Butler Helfer entfernen =="
  launchctl bootout "gui/$(id -u)" "$AGENT" 2>/dev/null || true
  rm -f "$AGENT"
  stop_helper
  rm -rf "$APP" "$BASE"
  echo "Entfernt. Die Python-Umgebung ~/s2l bleibt (die App Light-Butler Mixxx braucht sie eventuell)."
  exit 0
fi

echo "== Light-Butler Helfer installieren =="

# --- Python-Umgebung --------------------------------------------------------------------------------------------------
if [ ! -x "$HOME/s2l/bin/python3" ]; then
  echo "Python-Umgebung ~/s2l wird angelegt (einmalig, dauert eine Minute) ..."
  python3 -m venv "$HOME/s2l"
fi
for mod in mido:mido rtmidi:python-rtmidi numpy:numpy scipy:scipy soundfile:soundfile sounddevice:sounddevice; do
  if ! "$HOME/s2l/bin/python3" -c "import ${mod%%:*}" 2>/dev/null; then
    echo "Installiere ${mod##*:} ..."
    "$HOME/s2l/bin/pip" install --quiet "${mod##*:}" || echo "${mod##*:} konnte nicht installiert werden (Internet?)"
  fi
done

# --- Adresse des Raspberry Pi ------------------------------------------------------------------------------------------
PI="${S2L_PI:-}"
PI_DEFAULT="lightbutler.$LOCAL_DOMAIN"
[ -s "$BASE/pi_host" ] && PI_DEFAULT="$(head -n 1 "$BASE/pi_host")"
for f in "$HOME/Light-Butler-Daten/pi_host" "$HOME/Light-Butler-Daten/pi_host"; do [ -s "$f" ] && [ ! -s "$BASE/pi_host" ] && PI_DEFAULT="$(head -n 1 "$f")" && break; done
[ -s "$HOME/.light-butler-pi" ] && PI_DEFAULT="$(head -n 1 "$HOME/.light-butler-pi")"   # gemeinsame Einstellung (deploy.sh rename)
if [ -z "$PI" ]; then
  read -r -p "Adresse des Light-Butler (Raspberry Pi) [$PI_DEFAULT]: " PI
  PI="${PI:-$PI_DEFAULT}"
fi
case "$PI" in *.*) ;; *) PI="$PI.$LOCAL_DOMAIN" ;; esac

# --- Programmordner -----------------------------------------------------------------------------------------------------
mkdir -p "$BASE" "$LOGDIR"
cp "$HERE/helper.py" "$SRC/apc_relay.py" "$SRC/audio_send.py" "$SRC/pi_addr.py" "$BASE/"
# Liedliste ohne Mixxx: derselbe Teil wie in der Mixxx-Bruecke (Mixxx-Lieder aus ~/Light-Butler-Daten/mixxxdb.sqlite, MP3s im Musikordner)
cp "$SRC/mixxx_bridge.py" "$SRC/analyze_track.py" "$SRC/music_serve.py" "$SRC/stems_backup.py" "$SRC/energy_level.py" \
   "$SRC/energie_modell.json" "$SRC/key_estimate.py" "$SRC/loudness.py" "$SRC/prio.py" "$SRC/pfad.py" "$SRC/id3_tags.py" "$SRC/folder_lib.py" "$SRC/convert_mp3.py" "$SRC/tag_edit.py" "$SRC/auto_tag.py" "$SRC/dupes.py" "$SRC/folder_art.py" "$SRC/changed_log.py" "$SRC/file_check.py" "$SRC/genre_edit.py" "$SRC/cd_assist.py" "$SRC/music_excl.py" "$SRC/export_files.py" "$SRC/import_assist.py" "$SRC/klang_fp.py" "$SRC/cue_estimate.py" "$SRC/stick_hold.py" "$SRC/folder_merge.py" "$SRC/nas_mirror.py" "$SRC/fname_tags.py" "$SRC/audio_fade.py" "$SRC/mixxx_uebertragen.py" "$SRC/programs_copy.py" "$SRC/album_loose.py" "$SRC/damaged.py" "$SRC/mixxx_sterne.py" "$SRC/mixxx_sterne.sh" "$SRC/radio_play.py" "$BASE/"
mkdir -p "$BASE/stems" && cp "$SRC/../stems/stems_show.py" "$SRC/../stems/stem_curves.py" "$BASE/stems/"   # Pegelkurven-Waechter auch ohne Mixxx
echo "$PI" > "$BASE/pi_host"
echo "$PI" > "$HOME/.light-butler-pi"
cat > "$BASE/launch.sh" <<'EOF'
#!/bin/bash
# Startet den Light-Butler Helfer (APC, Ton und Liedliste an den Pi). Wird von der App aufgerufen.
BASE="$HOME/Light-Butler-Helfer"
LOGDIR="$HOME/Library/Logs/Light-Butler"
mkdir -p "$LOGDIR"
PI="$(head -n 1 "$BASE/pi_host" 2>/dev/null)"
cd "$BASE" || exit 1
exec "$HOME/s2l/bin/python3" -u helper.py "${PI:-lightbutler.local}" >> "$LOGDIR/helper.log" 2>&1
EOF
chmod +x "$BASE/launch.sh"

# --- App-Huelle (nur einmal anlegen, damit macOS die Mikrofon-Erlaubnis behaelt) ------------------------------------------------
if [ -n "$S2L_RECREATE_APP" ] || [ ! -f "$APP/Contents/MacOS/launcher" ]; then
  rm -rf "$APP"
  mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Light-Butler Helfer</string>
  <key>CFBundleDisplayName</key><string>Light-Butler Helfer</string>
  <key>CFBundleIdentifier</key><string>local.lightbutler.helfer</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Der Light-Butler Helfer liest den Ton von BlackHole und schickt ihn an die Lichtsteuerung.</string>
</dict>
</plist>
EOF
  cat > "$APP/Contents/MacOS/launcher" <<'EOF'
#!/bin/bash
# Kleiner Starter: die eigentliche Arbeit steht in ~/Light-Butler-Helfer/launch.sh (dort aktualisierbar).
exec "$HOME/Light-Butler-Helfer/launch.sh"
EOF
  chmod +x "$APP/Contents/MacOS/launcher"
  # Symbol: der Butler aus dem Panel (pi/apple-touch-icon.png), Fehler sind unkritisch
  ICON="$HERE/../../pi/apple-touch-icon.png"
  if [ -f "$ICON" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
    ICONSET="$(mktemp -d)/AppIcon.iconset"
    mkdir -p "$ICONSET"
    for s in 16 32 128 256 512; do
      sips -z $s $s "$ICON" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1 || true
      sips -z $((s*2)) $((s*2)) "$ICON" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns" >/dev/null 2>&1 || true
  fi
  touch "$APP"
  echo "App angelegt: $APP"
else
  echo "App ist schon vorhanden und bleibt unveraendert (Mikrofon-Erlaubnis bleibt erhalten)."
fi

# --- Autostart beim Anmelden ------------------------------------------------------------------------------------------
ANS="${S2L_AUTOSTART:-}"
if [ -z "$ANS" ]; then
  read -r -p "Beim Anmelden am Mac automatisch starten? [J/n]: " ANS
fi
case "$ANS" in
  n|N|nein|Nein)
    launchctl bootout "gui/$(id -u)" "$AGENT" 2>/dev/null || true
    rm -f "$AGENT"
    AUTO="nein" ;;
  *)
    mkdir -p "$(dirname "$AGENT")"
    cat > "$AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>local.lightbutler.helfer</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-g</string><string>-a</string><string>$APP</string></array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
EOF
    AUTO="ja" ;;
esac

# --- Neu starten, damit die neue Fassung laeuft --------------------------------------------------------------------------
if [ -z "$S2L_NO_OPEN" ]; then
  stop_helper
  open -g -a "$APP" 2>/dev/null || true
fi

echo
echo "Fertig."
echo "  App:        $APP   (laeuft im Hintergrund, ohne Symbol im Dock)"
echo "  Programme:  $BASE"
echo "  Pi-Adresse: $PI   (aenderbar in $BASE/pi_host)"
echo "  Autostart:  $AUTO"
echo "  Log:        ~/Library/Logs/Light-Butler/helper.log"
echo "  Liedliste:  Mixxx-Lieder aus ~/Light-Butler-Daten/mixxxdb.sqlite (Kopie der App Light-Butler Mixxx) plus MP3s im Musikordner,"
echo "              solange die App Light-Butler Mixxx nicht laeuft"
echo
echo "Fragt macOS nach dem Mikrofon-Zugriff fuer den Light-Butler Helfer: erlauben (damit liest er BlackHole)."
echo "Beenden:     pkill -f helper.py        Entfernen:  bash mac/helper/install_helper.sh --uninstall"
