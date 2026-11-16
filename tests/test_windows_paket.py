"""Download "Windows: ganzer Light-Butler" (pakete.windows_zip, install_windows.ps1): Programme ohne Zustandsdateien,
neutrale Geraete, Windows-Startoptionen, Skript ohne Syntaxfehler."""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from _common import PI, check, finish

import pakete

# ---- Paket aus einem Testordner mit Zustandsdateien und Geheimnissen ------------------------------------------------
base = tempfile.mkdtemp(prefix="s2l_winpaket_")
for n in ("show.py", "audio.py", "tempo_np.py", "install_windows.ps1", "install_pi.sh", "fixtures.yaml"):
    shutil.copy(os.path.join(PI, n), base)
os.makedirs(os.path.join(base, "static", "sm"))
open(os.path.join(base, "static", "sm", "core.js"), "w").write("// js")
for n in ("settings.json", "claude.json", "nanoleaf.json", "scenes.json", "show.conf", "backup.conf", "homematic.yaml"):
    open(os.path.join(base, n), "w").write("GEHEIM")
os.makedirs(os.path.join(base, "shows"))
open(os.path.join(base, "shows", "meine.json"), "w").write("GEHEIM")

data = pakete.windows_zip(base)
check(data is not None, "Paket entsteht")
z = zipfile.ZipFile(io.BytesIO(data))
names = z.namelist()
top = "Light-Butler-Windows-Voll/"
check(top + "install_windows.ps1" in names and top + "LIESMICH.txt" in names, "Installationsskript und LIESMICH oben")
check(top + "lichtshow/show.py" in names and top + "lichtshow/tempo_np.py" in names and top + "lichtshow/static/sm/core.js" in names,
      "Programme und Seiten in lichtshow/")
check(not [n for n in names if n.endswith(".json") and not n.endswith("/helfer/mixxx_bridge/energie_modell.json")],
      "keine .json-Dateien (Einstellungen, Szenen, Schluessel, Token); nur das Energie-Modell des Helfers (Programmteil)")
check(not [n for n in names if "/shows/" in n] and top + "lichtshow/homematic.yaml" not in names and
      top + "lichtshow/backup.conf" not in names, "keine Shows, keine HomeMatic-Datei, keine Sicherungs-Einstellung")
check(not any(b"GEHEIM" in z.read(n) for n in names), "nichts aus den Zustandsdateien im Paket")
conf = z.read(top + "lichtshow/show.conf").decode("utf-8")
check("SHOW_ARGS=--master 1.0 --web 8080" in conf and "--strobe" not in conf.split("SHOW_ARGS=")[1] and "\r\n" in conf,
      "eigene show.conf fuer Windows: ohne Strobe, Windows-Zeilenenden")
fx = z.read(top + "lichtshow/fixtures.yaml").decode("utf-8")
check("fixtures: []" in fx and "address: 221" not in fx and "Aufgabenplanung" in fx and "systemctl" not in fx,
      "neutrale Geraete (keine eigene Anlage), Hinweis fuer Windows")
check("par_rgbw_8ch" in fx, "Geraetetypen bleiben zur Auswahl")
liesmich = z.read(top + "LIESMICH.txt").decode("utf-8")
check("\r\n" in liesmich and "Private Netzwerke" in liesmich and "AUS" in liesmich, "LIESMICH: Firewall und Ausgaben aus erklaert")
check(pakete.windows_zip(tempfile.mkdtemp()) is None, "fehlt das Skript: kein Paket")
check("HELFER=1" in conf, "show.conf: Musik-Teil des Helfers startet mit")
check(top + "helfer/helper/helper.py" in names and top + "helfer/mixxx_bridge/folder_lib.py" in names and
      top + "helfer/mixxx_bridge/prio.py" in names, "Helfer mit Musik-Teil im Paket (wie im Projekt: helper/ neben mixxx_bridge/)")
check(not [n for n in names if "/helfer/stems/" in n or n.endswith(("install_mac.sh", ".sqlite"))],
      "ohne Pegelkurven (eigenes Paket), Mac-Installer und Datenbanken")
z2 = zipfile.ZipFile(io.BytesIO(pakete.windows_zip(base, mac_dirs=(tempfile.mkdtemp(),))))
check(not [n for n in z2.namelist() if "/helfer/" in n], "ohne Mac-Dateien (Pi ohne push): Paket ohne Helfer, aber vollstaendig")

# ---- Installationsskript ----------------------------------------------------------------------------------------
ps1 = open(os.path.join(PI, "install_windows.ps1"), "rb").read()
check(all(b < 128 for b in ps1), "Skript nur ASCII (Windows PowerShell 5.1 liest ohne BOM als ANSI)")
txt = ps1.decode("ascii")
check(all('%s`": 0.0' % k in txt for k in ("ola_out", "wled_out", "nano_out")) and "if (-not (Test-Path $Settings))" in txt,
      "erste Installation: alle Ausgaben aus, vorhandene Einstellungen bleiben")
check("/XF *.json show.conf backup.conf fixtures.yaml homematic.yaml" in txt and "/XD shows" in txt,
      "Aktualisieren ueberschreibt keine Zustandsdateien")
check("LB_RESTART_EXIT" in txt and "-eq 3" in txt, "start.ps1 startet nach Neustart aus dem Panel neu (Code 3)")
check("--strobe" not in txt and "laser_unlock" not in txt, "Skript schaltet keine Erlaubnis ein")
if sys.platform == "win32":
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); $e.Count"
                        % os.path.join(PI, "install_windows.ps1")], capture_output=True, text=True, timeout=60)
    check(r.stdout.strip() == "0", "PowerShell: keine Syntaxfehler (%s)" % r.stdout.strip())

shutil.rmtree(base, ignore_errors=True)
finish("test_windows_paket")
