"""Download "Windows-Musik-Rechner" (pakete.windows_music_zip, install_windows_musik.ps1, 15.11.2026): nur Helfer und
Mixxx-Bruecke, kein Light-Butler (show.py), keine Zustandsdateien, Skript ohne Syntaxfehler und ohne Erlaubnisse."""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from _common import PI, ROOT, check, finish

import pakete

base = tempfile.mkdtemp(prefix="s2l_winmusik_")
for n in ("show.py", "install_windows_musik.ps1", "fixtures.yaml"):
    shutil.copy(os.path.join(PI, n), base)
for n in ("settings.json", "claude.json", "nanoleaf.json", "music.json"):
    open(os.path.join(base, n), "w").write("GEHEIM")
mac = os.path.join(ROOT, "mac")

data = pakete.windows_music_zip(base, mac_dirs=(mac,))
check(data is not None, "Paket entsteht")
z = zipfile.ZipFile(io.BytesIO(data))
names = z.namelist()
top = "Light-Butler-Windows-Musik/"
check(top + "install_windows_musik.ps1" in names and top + "LIESMICH.txt" in names, "Skript und LIESMICH oben")
check(top + "helfer/helper/helper.py" in names and top + "helfer/mixxx_bridge/mixxx_bridge.py" in names and
      top + "helfer/mixxx_bridge/mixxx_start.py" in names and top + "helfer/mixxx_bridge/Light-Butler-Bridge.midi.xml" in names,
      "Helfer, Bruecke, Starter und Mixxx-Mapping")
check(not [n for n in names if n.endswith("show.py") or "/lichtshow/" in n or n.endswith("fixtures.yaml")], "ohne Light-Butler selbst")
check(not [n for n in names if n.endswith(".json") and not n.endswith("/helfer/mixxx_bridge/energie_modell.json")],
      "keine .json ausser dem Energie-Modell")
check(not [n for n in names if n.endswith((".sqlite", ".log", "install_mac.sh")) or "/stems/" in n or "/analysis/" in n],
      "keine Datenbanken, Logs, Analysen, Mac-Installer, Pegelkurven")
check(not any(b"GEHEIM" in z.read(n) for n in names), "nichts aus Zustandsdateien")
lm = z.read(top + "LIESMICH.txt").decode("utf-8")
check("\r\n" in lm and "loopMIDI" in lm and "Light-Butler" in lm and "VB-Cable" in lm and "Stereomix" in lm and "-Entfernen" in lm,
      "LIESMICH: loopMIDI, Ton-Wege, Entfernen")
check(pakete.windows_music_zip(tempfile.mkdtemp(), mac_dirs=(mac,)) is None, "fehlt das Skript: kein Paket")
check(pakete.windows_music_zip(base, mac_dirs=(tempfile.mkdtemp(),)) is None, "fehlen die Mac-Dateien: kein Paket")

ps1 = open(os.path.join(PI, "install_windows_musik.ps1"), "rb").read()
check(all(b < 128 for b in ps1), "Skript nur ASCII (PowerShell 5.1)")
txt = ps1.decode("ascii")
check("--no-stems" in txt and "Light-Butler Mixxx.lnk" in txt and "mixxx_start.py" in txt and "-Entfernen" in txt,
      "Helfer ohne Pegelkurven, Verknuepfung, Entfernen")
check("--strobe" not in txt and "show.py" not in txt and "settings.json" not in txt, "kein Light-Butler, keine Erlaubnis")
check("Contains($Ziel.ToLower())" in txt and "-ne $PID" in txt and "install_windows_musik\\.ps1" in txt,
      "beendet nur Prozesse aus dem eigenen Ordner, nie sich selbst")
if sys.platform == "win32":
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); $e.Count"
                        % os.path.join(PI, "install_windows_musik.ps1")], capture_output=True, text=True, timeout=60)
    check(r.stdout.strip() == "0", "PowerShell: keine Syntaxfehler (%s)" % r.stdout.strip())
shutil.rmtree(base, ignore_errors=True)
finish("test_windows_musik_paket")
