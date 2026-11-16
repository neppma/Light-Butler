#!/bin/bash
# Richtet am Mac die Umgebung fuer stems_show.py ein (einmalig, nur am Mac, der Pi bekommt nichts davon).
#
# Aufruf im Projektordner:  bash mac/stems/install_stems.sh
# Legt ~/s2l-stems an, rund 550 MB. Das Modell (kleiner) laedt Demucs beim ersten Lauf nach.
# Torch ist festgelegt: Mit dieser Fassung lief Demucs am M1 (05.11.2026), neuere brauchen fuers Speichern weitere Pakete.
# Wieder entfernen:  rm -r ~/s2l-stems
set -e
ENV="$HOME/s2l-stems"
PY="$(command -v python3.11 || command -v python3)"
"$PY" -c 'import sys; sys.exit(0 if (3,9) <= sys.version_info[:2] <= (3,12) else 1)' || {
  echo "Fuer Torch 2.5 braucht es Python 3.9 bis 3.12, gefunden: $("$PY" --version)"; exit 1; }
[ -x "$ENV/bin/python" ] || "$PY" -m venv "$ENV"
"$ENV/bin/pip" install -q --upgrade pip
"$ENV/bin/pip" install -q demucs "torch==2.5.1" "torchaudio==2.5.1" soundfile
"$ENV/bin/python" -c "import demucs, soundfile, torch; print('Demucs', demucs.__version__, 'Torch', torch.__version__)"
echo "Fertig. Zum Beispiel:  $ENV/bin/python mac/stems/stems_show.py --liste"
