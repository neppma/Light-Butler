#!/bin/bash
# Light-Butler am Mac einrichten: Mixxx-Bruecke (App "Light-Butler Mixxx") und Light-Butler Helfer, mit allen Python-Paketen.
# Fuer einen neuen Mac oder einen neuen Benutzer (Paket zum Herunterladen am Light-Butler: Einstellungen, unten).
#
# Aufruf im entpackten Ordner, im Programm "Terminal":
#     bash install_mac.sh
#
# Was passiert (jeder Schritt sagt, was er tut; nichts wird ohne Rueckfrage zusaetzlich installiert):
#   1. Python pruefen (macOS bringt python3 mit den Entwicklerwerkzeugen mit)
#   2. Python-Umgebung ~/s2l mit mido, python-rtmidi, numpy, scipy, soundfile, sounddevice
#   3. Adresse des Light-Butler (Raspberry Pi) abfragen
#   4. App "Light-Butler Mixxx" (Bruecke) und Light-Butler Helfer einrichten
#   5. Auf Wunsch: ffmpeg (Homebrew), essentia (~/s2l-key, genauere Tonart und BPM), Pegelkurven (~/s2l-stems, rund 550 MB)
#   6. Was danach noch von Hand zu tun ist (Mixxx, IAC-Treiber, Mapping, BlackHole)
#
# Ohne Rueckfragen (zum Beispiel zum Ausprobieren):  S2L_PI=lightbutler.local S2L_AUTOSTART=j S2L_EXTRAS=n bash install_mac.sh
# S2L_SKIP_PIP=1 legt die Umgebung an, ohne Pakete aus dem Internet zu holen (nur zum Pruefen des Ablaufs).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV="$HOME/s2l"
ask() {                                    # ask "Frage" Standard -> j oder n (S2L_EXTRAS gibt die Antwort fuer alle Zusaetze vor)
  local a="${S2L_EXTRAS:-}"
  if [ -z "$a" ]; then read -r -p "$1 [j/N]: " a; fi
  case "$a" in j|J|ja|Ja|y|Y) return 0 ;; *) return 1 ;; esac
}

echo "== Light-Butler am Mac einrichten =="
echo

# --- 1. Python ------------------------------------------------------------------------------------------------------
echo "== 1/6 Python =="
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import venv" 2>/dev/null; then
  echo "python3 fehlt. macOS bietet es mit den Entwicklerwerkzeugen an: im Terminal"
  echo "    xcode-select --install"
  echo "ausfuehren, bestaetigen, warten, dann dieses Skript noch einmal starten."
  exit 1
fi
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "python3 $PYV gefunden."

# --- 2. Python-Umgebung --------------------------------------------------------------------------------------------
echo; echo "== 2/6 Python-Umgebung ~/s2l =="
if [ ! -x "$ENV/bin/python3" ]; then
  python3 -m venv "$ENV"
  echo "angelegt: $ENV"
fi
if [ -z "$S2L_SKIP_PIP" ]; then
  echo "Pakete installieren (einmalig, dauert ein, zwei Minuten) ..."
  "$ENV/bin/pip" install --quiet --upgrade pip
  "$ENV/bin/pip" install --quiet mido python-rtmidi numpy scipy soundfile sounddevice
  "$ENV/bin/python3" -c "import mido, rtmidi, numpy, scipy, soundfile, sounddevice" && echo "Pakete in Ordnung."
else
  echo "(S2L_SKIP_PIP: Pakete nicht geholt)"
fi

# --- 3. Adresse des Light-Butler ------------------------------------------------------------------------------------
echo; echo "== 3/6 Adresse des Light-Butler =="
PI="${S2L_PI:-}"
DEF="lightbutler.local"
[ -s "$HOME/.light-butler-pi" ] && DEF="$(head -n 1 "$HOME/.light-butler-pi")"
if [ -z "$PI" ]; then read -r -p "Adresse des Light-Butler (Raspberry Pi) [$DEF]: " PI; fi
PI="${PI:-$DEF}"
case "$PI" in *.*) ;; *) PI="$PI.${S2L_DOMAIN:-local}" ;; esac
echo "$PI" > "$HOME/.light-butler-pi"
if curl -s -m 3 "http://$PI:8080/api/musik/conf" >/dev/null 2>&1; then echo "$PI antwortet."; else echo "Hinweis: $PI antwortet gerade nicht (Pi aus oder anderer Name?). Geht trotzdem weiter."; fi

# --- 4. Bruecke und Helfer ------------------------------------------------------------------------------------------
echo; echo "== 4/6 App \"Light-Butler Mixxx\" und Light-Butler Helfer =="
S2L_PI="$PI" S2L_SKIP_VENV=1 S2L_NO_OPEN="${S2L_NO_OPEN:-}" bash "$HERE/mixxx_bridge/install_launcher.sh" | tail -4
S2L_PI="$PI" S2L_AUTOSTART="${S2L_AUTOSTART:-}" S2L_NO_OPEN="${S2L_NO_OPEN:-}" bash "$HERE/helper/install_helper.sh" | tail -3

# --- 5. Zusaetze ----------------------------------------------------------------------------------------------------
echo; echo "== 5/6 Zusaetze (alle freiwillig) =="
if command -v ffmpeg >/dev/null 2>&1 || [ -x /opt/homebrew/bin/ffmpeg ] || [ -x /usr/local/bin/ffmpeg ]; then
  echo "ffmpeg ist da (→ MP3 umwandeln, Shazam im Tag-Fenster und bei den Tag-Vorschlaegen)."
elif command -v brew >/dev/null 2>&1; then
  if ask "ffmpeg mit Homebrew installieren? (fuer → MP3 und Shazam)"; then brew install ffmpeg; fi
else
  echo "ffmpeg fehlt (→ MP3, Shazam). Dafuer zuerst Homebrew von https://brew.sh einrichten, dann:  brew install ffmpeg"
fi
if [ -x "$HOME/s2l-key/bin/python" ] && "$HOME/s2l-key/bin/python" -c "import essentia" 2>/dev/null; then
  echo "essentia ist da (~/s2l-key, genauere Tonart und BPM)."
elif ask "essentia fuer genauere Tonart und BPM einrichten? (~/s2l-key, rund 150 MB)"; then
  python3 -m venv "$HOME/s2l-key"
  "$HOME/s2l-key/bin/pip" install --quiet --upgrade pip
  "$HOME/s2l-key/bin/pip" install --quiet essentia numpy && echo "essentia eingerichtet." || echo "essentia ging nicht (fuer diese Python-Fassung gibt es eventuell kein Paket); ohne geht es mit dem einfacheren Verfahren."
fi
if [ -x "$HOME/s2l-stems/bin/python" ]; then
  echo "Pegelkurven sind eingerichtet (~/s2l-stems)."
elif ask "Pegelkurven (Demucs) einrichten? (~/s2l-stems, rund 550 MB, rechnet Kurven fuer den Showmanager)"; then
  bash "$HERE/stems/install_stems.sh" || echo "Pegelkurven gingen nicht (Python 3.9 bis 3.12 noetig), spaeter: bash stems/install_stems.sh"
fi

# --- 6. Von Hand ----------------------------------------------------------------------------------------------------
echo; echo "== 6/6 Noch von Hand =="
[ -d /Applications/Mixxx.app ] && echo "  ✓ Mixxx ist installiert." || echo "  • Mixxx 2.5 von https://mixxx.org laden und nach /Applications ziehen."
echo "  • IAC-Treiber: Programm \"Audio-MIDI-Setup\" -> Fenster -> MIDI-Studio -> IAC-Treiber -> \"Geraet ist online\"."
echo "  • Mixxx-Mapping: die Dateien mixxx_bridge/Light-Butler-Bridge.midi.xml und Light-Butler-Bridge-scripts.js in den"
echo "    Mixxx-Ordner controllers kopieren (siehe mixxx_bridge/README.txt), in Mixxx unter Einstellungen -> Controller waehlen."
echo "  • Ton vom Mac an den Pi (Spotify, YouTube): BlackHole 2ch einrichten (https://existential.audio/blackhole oder"
echo "    brew install blackhole-2ch), fragt macOS nach dem Mikrofon fuer den Helfer: erlauben."
echo "  • Musikordner am Light-Butler eintragen: Panel -> Einstellungen -> Verbindungen."
echo
echo "Fertig. Starten: App \"Light-Butler Mixxx\" in ~/Applications (Mixxx mit Bruecke). Der Helfer laeuft im Hintergrund."
