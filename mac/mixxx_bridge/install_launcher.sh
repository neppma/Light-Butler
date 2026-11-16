#!/bin/bash
# Installiert die App "Light-Butler Mixxx": ein Klick startet Mixxx zusammen mit der Bruecke zum Raspberry Pi.
#
# Aufruf (einmal, im Ordner mixxx_bridge, in Terminal):
#     bash install_launcher.sh
#
# Was passiert:
#   1. Der Programmordner ~/Light-Butler-Daten wird angelegt (Bruecke, Analyse-Programm, Analyse-Ergebnisse, Datenbank-Kopie).
#   2. Die App ~/Applications/Light-Butler Mixxx.app wird erzeugt und im Finder angezeigt. Per Doppelklick oder aus dem Dock startbar.
#   3. Bei jedem Start wird die Mixxx-Datenbank neu kopiert, damit neue Lieder sofort bekannt sind.
#
# Die App wird auf deinem Mac erzeugt und ist deshalb nicht durch macOS gesperrt.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="${S2L_DATA:-$HOME/Light-Butler-Daten}"   # Datenordner
APP="$HOME/Applications/Light-Butler Mixxx.app"
MIXXX_BIN_DEFAULT="/Applications/Mixxx.app/Contents/MacOS/mixxx"

echo "== Light-Butler Mixxx installieren =="

# --- Python-Umgebung ---------------------------------------------------------------------------------------------
if [ ! -f "$HOME/s2l/bin/activate" ] && [ -z "$S2L_SKIP_VENV" ]; then
  echo "Python-Umgebung ~/s2l fehlt, wird angelegt (einmalig, dauert eine Minute) ..."
  python3 -m venv "$HOME/s2l"
  # shellcheck disable=SC1091
  source "$HOME/s2l/bin/activate"
  pip install --quiet mido python-rtmidi numpy scipy soundfile sounddevice
fi
# Ton vom Mac an den Pi (audio_send.py) braucht sounddevice; in aelteren Umgebungen nachinstallieren
if [ -x "$HOME/s2l/bin/python3" ] && ! "$HOME/s2l/bin/python3" -c "import sounddevice" 2>/dev/null; then
  echo "Installiere sounddevice fuer die Ton-Weiterleitung ..."
  "$HOME/s2l/bin/pip" install --quiet sounddevice || echo "sounddevice konnte nicht installiert werden (Internet?)"
fi

# --- Adresse des Raspberry Pi --------------------------------------------------------------------------------------
# Lokale Domaene fuer einen Namen ohne Punkt (Standard local, eigene per S2L_DOMAIN): Standard lightbutler.local. Die letzte Eingabe merkt sich die Datei pi_host.
PI="${S2L_PI:-}"
LOCAL_DOMAIN="${S2L_DOMAIN:-local}"
PI_DEFAULT="lightbutler.$LOCAL_DOMAIN"
[ -s "$BASE/pi_host" ] && PI_DEFAULT="$(head -n 1 "$BASE/pi_host")"
[ -s "$HOME/.light-butler-pi" ] && PI_DEFAULT="$(head -n 1 "$HOME/.light-butler-pi")"   # gemeinsame Einstellung (deploy.sh rename)
if [ -z "$PI" ]; then
  read -r -p "Adresse des Raspberry Pi [$PI_DEFAULT]: " PI
  PI="${PI:-$PI_DEFAULT}"
fi
case "$PI" in *.*) ;; *) PI="$PI.$LOCAL_DOMAIN" ;; esac      # nur der Name (lightbutler): Domaene anhaengen
mkdir -p "$BASE" && echo "$PI" > "$BASE/pi_host" && echo "$PI" > "$HOME/.light-butler-pi"

# --- Programmordner --------------------------------------------------------------------------------------------------
mkdir -p "$BASE/analysis"
cp "$HERE/mixxx_bridge.py" "$HERE/analyze_track.py" "$HERE/backup_mac.py" "$HERE/apc_relay.py" "$HERE/audio_send.py" "$HERE/music_serve.py" "$HERE/stems_backup.py" "$HERE/energy_level.py" "$HERE/energie_modell.json" "$HERE/key_estimate.py" "$HERE/loudness.py" "$HERE/prio.py" "$HERE/pfad.py" "$HERE/id3_tags.py" "$HERE/folder_lib.py" "$HERE/convert_mp3.py" "$HERE/tag_edit.py" "$HERE/auto_tag.py" "$HERE/dupes.py" "$HERE/folder_art.py" "$HERE/changed_log.py" "$HERE/file_check.py" "$HERE/genre_edit.py" "$HERE/cd_assist.py" "$HERE/music_excl.py" "$HERE/export_files.py" "$HERE/import_assist.py" "$HERE/klang_fp.py" "$HERE/cue_estimate.py" "$HERE/stick_hold.py" "$HERE/folder_merge.py" "$HERE/nas_mirror.py" "$HERE/fname_tags.py" "$HERE/audio_fade.py" "$HERE/mixxx_umbenennen.sh" "$HERE/mixxx_uebertragen.py" "$HERE/programs_copy.py" "$HERE/album_loose.py" "$HERE/damaged.py" "$HERE/mixxx_sterne.py" "$HERE/mixxx_sterne.sh" "$HERE/mixxx_start.py" "$BASE/"
mkdir -p "$BASE/stems" && cp "$HERE/../stems/stems_show.py" "$HERE/../stems/stem_curves.py" "$BASE/stems/"   # Pegelkurven (Waechter)
if [ -d "$HERE/analysis" ] && [ "$(ls -A "$HERE/analysis" 2>/dev/null)" ]; then
  cp -n "$HERE/analysis/"*.json "$BASE/analysis/" 2>/dev/null || true
  echo "Vorhandene Analysen uebernommen: $(ls "$BASE/analysis" | wc -l | tr -d ' ') Dateien"
fi
if [ -f "$HOME/Downloads/mixxxdb.sqlite" ] && [ ! -f "$BASE/mixxxdb.sqlite" ]; then
  cp "$HOME/Downloads/mixxxdb.sqlite" "$BASE/mixxxdb.sqlite"
fi
BG_OLD=$(sed -n 's/^BACKGROUND_ANALYSIS="*\([01]\)"*.*/\1/p' "$BASE/config.sh" 2>/dev/null | head -1)   # eigene Wahl behalten
MR_OLD=$(sed -n 's/^MUSIC_ROOT="\(.*\)"$/\1/p' "$BASE/config.sh" 2>/dev/null | head -1)
ST_OLD=$(sed -n 's/^STEMS_AUTO="*\([01]\)"*.*/\1/p' "$BASE/config.sh" 2>/dev/null | head -1)
cat > "$BASE/config.sh" <<EOF
# Einstellungen der App (kann von Hand geaendert werden)
PI="$PI"
MIXXX_BIN="${S2L_MIXXX_BIN:-$MIXXX_BIN_DEFAULT}"
# 1 = noch nicht analysierte Lieder im Hintergrund analysieren (niedrige Prioritaet, Lieder in Mixxx haben Vorrang), 0 = aus
BACKGROUND_ANALYSIS="${BG_OLD:-1}"
# Musikordner am Mac (USB-Stick oder NAS) fuer Vorhoeren und "Show anlegen" im Panel, nur Reserve: Im Panel unter
# Einstellungen -> Verbindungen eingetragen gilt der Ordner von dort. Leer = nur die Pfade aus Mixxx.
MUSIC_ROOT="${MR_OLD:-}"
# 1 = Pegelkurven (Bass, Stimme, ...) fuer neue Shows von selbst rechnen, solange die App laeuft, auch neben Mixxx
#     (belastet alle Kerne rund 1,5-mal die Liedlaenge; braucht ~/s2l-stems aus mac/stems/install_stems.sh). 0 = aus
STEMS_AUTO="${ST_OLD:-1}"
EOF

# --- App-Huelle ------------------------------------------------------------------------------------------------------
# --- Starter-Skript: liegt in ~/Light-Butler-Daten und wird bei jedem Lauf aktualisiert, die App selbst bleibt unveraendert ----------
cat > "$BASE/launch.sh" <<'EOF'
#!/bin/bash
# Startet Mixxx und die Bruecke. Beendest du Mixxx, beendet sich die Bruecke von selbst.
BASE="$(cd "$(dirname "$0")" && pwd)"            # Datenordner (dort liegt dieses Skript)
LOGDIR="$HOME/Library/Logs/Light-Butler"
mkdir -p "$LOGDIR"
exec >> "$LOGDIR/launcher.log" 2>&1
echo "=== $(date) Start"

dialog() {
  osascript -e "display dialog \"$1\" with title \"Light-Butler Mixxx\" buttons {\"OK\"} default button \"OK\" with icon caution" >/dev/null 2>&1
}

# shellcheck disable=SC1091
source "$BASE/config.sh"

if pgrep -x mixxx >/dev/null 2>&1; then
  dialog "Mixxx laeuft schon. Bitte Mixxx beenden und diese App danach starten (die Bruecke braucht einen frischen Start von Mixxx)."
  exit 0
fi
if [ ! -x "$MIXXX_BIN" ]; then
  dialog "Mixxx wurde nicht gefunden: $MIXXX_BIN. Pfad in $BASE/config.sh anpassen."
  exit 1
fi
if [ ! -f "$HOME/s2l/bin/activate" ]; then
  dialog "Die Python-Umgebung ~/s2l fehlt. Bitte install_launcher.sh nochmal ausfuehren."
  exit 1
fi
# shellcheck disable=SC1091
source "$HOME/s2l/bin/activate"

# Datenbank neu kopieren, damit neue Lieder bekannt sind (ohne Erlaubnis bleibt die alte Kopie)
SRC="$HOME/Library/Containers/org.mixxx.mixxx/Data/Library/Application Support/Mixxx/mixxxdb.sqlite"
[ -f "$SRC" ] || SRC="$HOME/Library/Application Support/Mixxx/mixxxdb.sqlite"
# Sicherung der Mixxx-Datenbank bei jedem Start, solange Mixxx sicher zu ist (Hotcues, Kisten, Playlists stehen nur dort;
# Wunsch von Markus 08.11.2026). Die letzten 5 bleiben, die woechentliche Mac-Sicherung (backup_mac.py) nimmt sie mit.
if [ -s "$SRC" ]; then
  mkdir -p "$BASE/mixxx-sicherung"
  if cp "$SRC" "$BASE/mixxx-sicherung/mixxxdb-$(date +%Y%m%d-%H%M%S).sqlite" 2>/dev/null; then
    ls -1t "$BASE/mixxx-sicherung"/mixxxdb-*.sqlite 2>/dev/null | tail -n +6 | while read -r old; do rm -f "$old"; done
    echo "Mixxx-Datenbank gesichert"
  else
    echo "Mixxx-Datenbank nicht gesichert (kein Zugriff)"
  fi
fi
# Umbenennungen von "Dateien pruefen" in Mixxx nachziehen, solange Mixxx noch zu ist (Hotcues und Kisten bleiben)
[ -f "$BASE/mixxx_umbenennen.sh" ] && bash "$BASE/mixxx_umbenennen.sh" "$SRC"
# Sterne aus dem Light-Butler eintragen, solange Mixxx noch zu ist (14.11.2026)
[ -f "$BASE/mixxx_sterne.sh" ] && bash "$BASE/mixxx_sterne.sh" "$SRC"
if cp "$SRC" "$BASE/mixxxdb.sqlite.neu" 2>/dev/null; then
  mv "$BASE/mixxxdb.sqlite.neu" "$BASE/mixxxdb.sqlite"
  echo "Datenbank aktualisiert"
else
  echo "Datenbank nicht kopierbar, alte Kopie wird genutzt"
fi
DBARG=1
if [ ! -f "$BASE/mixxxdb.sqlite" ]; then
  # ohne Mixxx-Datenbank laeuft die Bruecke mit den Liedern aus dem Musikordner (folder_lib.py), Erkennung der Decks gibt es dann nicht
  echo "Mixxx-Datenbank fehlt: nur Lieder aus dem Musikordner (mixxxdb.sqlite im Finder nach $BASE kopieren, siehe README)"
  DBARG=""
fi

cd "$BASE" || exit 1
# Sicherung der Analysen im Hintergrund, hoechstens einmal pro Woche
python3 backup_mac.py --if-older 7 >> "$LOGDIR/backup.log" 2>&1 &
BG=""
[ "${BACKGROUND_ANALYSIS:-1}" = "1" ] && BG="--background-analysis"   # noch nicht analysierte Lieder im Hintergrund
# Pegelkurven-Waechter: rechnet neue Shows von selbst (stems.log), endet mit der App
STEMS_PID=""
# laeuft schon einer (der Light-Butler Helfer haelt ihn standardmaessig am Laufen), keinen zweiten starten
if [ "${STEMS_AUTO:-1}" = "1" ] && [ -x "$HOME/s2l-stems/bin/python" ] && [ -f "$BASE/stems/stems_show.py" ] && ! pgrep -f "stems_show.py --watch" >/dev/null 2>&1; then
  "$HOME/s2l-stems/bin/python" "$BASE/stems/stems_show.py" --watch --reserve --pi "$PI" >> "$LOGDIR/stems.log" 2>&1 &
  STEMS_PID=$!
  echo "Pegelkurven-Waechter gestartet (PID $STEMS_PID)"
fi
# Abgleich Mixxx/Stick in der Musik-Datenbank: aktuelle Mixxx-Datenbank jede Minute kopieren. Die Bruecke (Python) darf den
# Mixxx-Ordner nicht lesen ("Operation not permitted"), dieses Skript schon (Fehlerbericht 07.11.2026). Nur lesen, Mixxx bleibt unberuehrt.
( while :; do
    for X in "" "-wal"; do
      if [ -f "$SRC$X" ]; then
        cp "$SRC$X" "$BASE/mixxxdb.live.sqlite$X.neu" 2>/dev/null && mv "$BASE/mixxxdb.live.sqlite$X.neu" "$BASE/mixxxdb.live.sqlite$X"
      else
        rm -f "$BASE/mixxxdb.live.sqlite$X"
      fi
    done
    sleep 60
  done ) &
LIVE_PID=$!
trap '[ -n "$STEMS_PID" ] && kill "$STEMS_PID" 2>/dev/null; kill "$LIVE_PID" 2>/dev/null' EXIT
# Mixxx-Ausgabe an die Bruecke geben; Warnungen und Fehler von Mixxx zusaetzlich in mixxx_errors.log festhalten
"$MIXXX_BIN" --controller-debug 2>&1 | tee >(grep -i -E "warning|error|critical|cannot|denied|failed|not found" >> "$LOGDIR/mixxx_errors.log") | python3 mixxx_bridge.py --stdin \
    ${DBARG:+--db "$BASE/mixxxdb.sqlite"} --send "$PI" --analysis-dir "$BASE/analysis" --music-root "${MUSIC_ROOT:-}" $BG >> "$LOGDIR/bridge.log" 2>&1
echo "=== $(date) Ende"
EOF
chmod +x "$BASE/launch.sh"

# --- App-Huelle: nur anlegen, wenn es sie nicht gibt (oder sie noch die alte Bauart hat). ----------------------------------------
# Warum: macOS merkt sich Erlaubnisse (Festplattenvollzugriff, Netzlaufwerke) pro App. Wird die App bei jedem Lauf neu
# erzeugt, verlangt macOS die Erlaubnis jedes Mal wieder. Darum bleibt die App ab jetzt unveraendert, nur launch.sh wird aktualisiert.
if [ -n "$S2L_RECREATE_APP" ] || [ ! -f "$APP/Contents/MacOS/launcher" ] || ! grep -q "launch.sh" "$APP/Contents/MacOS/launcher" 2>/dev/null; then
  CREATE_APP=1
else
  CREATE_APP=""
  echo "App ist schon vorhanden und bleibt unveraendert (Erlaubnisse bleiben erhalten). Nur $BASE/launch.sh wurde aktualisiert."
fi
if [ -n "$CREATE_APP" ]; then
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Light-Butler Mixxx</string>
  <key>CFBundleDisplayName</key><string>Light-Butler Mixxx</string>
  <key>CFBundleIdentifier</key><string>local.lightbutler.mixxx</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
$( [ -n "$S2L_HIDE_DOCK" ] && echo "  <key>LSUIElement</key><true/>" )
</dict>
</plist>
EOF

cat > "$APP/Contents/MacOS/launcher" <<'EOF'
#!/bin/bash
# Kleiner Starter: die eigentliche Arbeit steht in launch.sh im Datenordner (dort aktualisierbar, ohne die App zu veraendern).
D="$HOME/Light-Butler-Daten"
exec "$D/launch.sh"
EOF
chmod +x "$APP/Contents/MacOS/launcher"
fi

# --- Symbol (optional, Fehler sind unkritisch), nur fuer eine neu erzeugte App --------------------------------------------
if [ -n "$CREATE_APP" ]; then
python3 - "$APP/Contents/Resources" <<'EOF' 2>/dev/null || true
import struct, sys, zlib, os
out = sys.argv[1]
N = 1024
def px(x, y):
    # dunkler Hintergrund mit sieben farbigen Balken (wie ein Pegelanzeiger)
    r = g = b = 0
    cx, cy = x / N, y / N
    base = (28, 30, 44)
    r, g, b = base
    inside = (0.08 <= cx <= 0.92 and 0.08 <= cy <= 0.92)
    if not inside:
        return (0, 0, 0, 0)
    heights = [0.35, 0.6, 0.45, 0.8, 0.55, 0.7, 0.4]
    cols = [(255, 80, 80), (255, 170, 60), (240, 220, 70), (90, 220, 120), (70, 200, 230), (110, 140, 255), (190, 110, 255)]
    bw = 0.84 / 7
    k = int((cx - 0.08) / bw)
    if 0 <= k < 7:
        local = (cx - 0.08) - k * bw
        if 0.15 * bw <= local <= 0.85 * bw and cy >= 0.9 - 0.7 * heights[k] - 0.05 and cy <= 0.88:
            return cols[k] + (255,)
    return base + (255,)
raw = bytearray()
for y in range(N):
    raw.append(0)
    for x in range(N):
        raw.extend(px(x, y))
def chunk(t, d):
    c = struct.pack(">I", len(d)) + t + d
    return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")
open(os.path.join(out, "icon_1024.png"), "wb").write(png)
EOF
if [ -f "$APP/Contents/Resources/icon_1024.png" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  ICONSET="$(mktemp -d)/AppIcon.iconset"
  mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$APP/Contents/Resources/icon_1024.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1
    sips -z $((s*2)) $((s*2)) "$APP/Contents/Resources/icon_1024.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns" >/dev/null 2>&1 || true
fi
rm -f "$APP/Contents/Resources/icon_1024.png"
touch "$APP"
fi

echo
echo "Fertig."
echo "  App:        $APP"
echo "  Programme:  $BASE   (Analysen in $BASE/analysis)"
echo "  Pi-Adresse: $PI   (aenderbar in $BASE/config.sh)"
echo "  Log:        ~/Library/Logs/Light-Butler/bridge.log"
echo "  Sicherung:  ~/Documents/Light-Butler-Backups (automatisch, hoechstens woechentlich beim Start)"
echo
echo "Starten:"
echo "  - Der Finder zeigt jetzt die App an (Fenster mit markiertem Symbol). Doppelklick startet sie."
echo "  - Direkt im Terminal:   open ~/Applications/Light-Butler\ Mixxx.app"
echo "  - Ins Dock: das Symbol aus dem Finder-Fenster auf das Dock ziehen."
echo "  - Oder Spotlight: Cmd+Leertaste, 'Light-Butler' tippen."
if [ -z "$S2L_NO_OPEN" ] && command -v open >/dev/null 2>&1; then
  open -R "$APP" 2>/dev/null || true
fi
