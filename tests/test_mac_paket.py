"""Mac als Licht-Rechner (Wunsch 15.11.2026): Paket light-butler-mac-voll.zip mit install_lightbutler_mac.sh."""
import io
import os
import re
import subprocess
import sys
import zipfile

from _common import PI, check, finish

import pakete
import webpanel

data = pakete.mac_full_zip()
check(data is not None, "Paket entsteht")
z = zipfile.ZipFile(io.BytesIO(data))
names = z.namelist()
top = "Light-Butler-Mac-Voll/"
check(all(n.startswith(top) for n in names), "alles in einem Ordner")
for n in ("install_lightbutler_mac.sh", "LIESMICH.txt", "lichtshow/show.py", "lichtshow/show.conf", "lichtshow/fixtures.yaml",
          "lichtshow/HANDBUCH.md", "lichtshow/MANUAL_EN.md", "lichtshow/tempo_np.py"):
    check(top + n in names, f"enthaelt {n}")
STATE = ("settings.json", "scenes.json", "nanoleaf.json", "claude.json", "fixtures_user.json", "raum.json", "backup.conf",
         "homematic.yaml", "midimap.json", "texts.json", "music.json")
check(not [n for n in names if os.path.basename(n) in STATE or "/shows/" in n], "keine Zustandsdateien, keine Shows")
check(not [n for n in names if "/helfer/" in n or "mixxx_bridge" in n], "ohne Helfer (der kommt aus light-butler-mac.zip)")
conf = z.read(top + "lichtshow/show.conf").decode()
check("--strobe" not in re.findall(r"(?m)^SHOW_ARGS=.*$", conf)[0], "show.conf ohne Strobe-Erlaubnis")
fx = z.read(top + "lichtshow/fixtures.yaml").decode()
check("fixtures: []" in fx and "light-butler.show" in fx, "neutrale Geraete, Neustart-Hinweis fuer den Mac")

sh = open(os.path.join(PI, "install_lightbutler_mac.sh"), encoding="utf-8").read()
if sys.platform != "win32":                      # unter Windows ist bash oft das WSL-bash ohne Windows-Pfade
    check(subprocess.run(["bash", "-n", os.path.join(PI, "install_lightbutler_mac.sh")]).returncode == 0, "Skript: bash -n")
check('"ola_out": 0.0' in sh and '"wled_out": 0.0' in sh and '"nano_out": 0.0' in sh and '[ ! -f "$DEST/settings.json" ]' in sh,
      "neue Anlage: alle Ausgaben aus, vorhandene Einstellungen bleiben")
check("--exclude '*.json' --exclude show.conf --exclude backup.conf --exclude fixtures.yaml --exclude homematic.yaml" in sh
      and "--exclude shows/" in sh and "--delete" not in sh, "Zustandsdateien und Shows nie ueberschrieben oder geloescht")
check("--strobe" not in sh.split("SHOW_ARGS")[0] or "strobe" not in sh.lower().split("strobe-erlaubnis")[0], "Skript setzt keine Strobe-Erlaubnis")
check("sudo" not in sh, "kein Administrator-Passwort")
check("light-butler.show" in sh and "<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>" in sh and "RunAtLoad" in sh,
      "Autostart ueber launchd, Neustart nach Absturz")
check("light-butler.backup" in sh and "<key>Hour</key><integer>4</integer><key>Minute</key><integer>30</integer>" in sh and "backup.py</string><string>--auto" in sh,
      "Sicherung jede Nacht 04:30")
rm = sh.split('if [ "$REMOVE" = 1 ]; then')[1].split("fi")[0]
check('rm -rf "$VENV"' in rm and "$DEST" not in rm.replace('Programme und Daten bleiben in $DEST', ""), "--entfernen loescht nie die Daten")
check("exec \"$HERE/venv/bin/python3\" -u show.py $ARGS" in sh, "start.sh startet show.py mit show.conf")

check(webpanel.ping_cmd("1.2.3.4", "darwin") == ["ping", "-c", "1", "-W", "1000", "1.2.3.4"], "Ping am Mac: -W in Millisekunden")
check(webpanel.ping_cmd("1.2.3.4", "linux") == ["ping", "-c", "1", "-W", "1", "1.2.3.4"], "Ping am Pi unveraendert")
au = open(os.path.join(PI, "audio.py"), encoding="utf-8").read()
check('sys.platform in ("win32", "darwin")' in au, "Mac ohne aubio: Tempo mit tempo_np")
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
check('path == "/download/light-butler-mac-voll.zip"' in api and "pakete.mac_full_zip()" in api and '"macvoll"' in api, "Download und Stand fuer /software")
check('href="/download/light-butler-mac-voll.zip" download><span data-tx="dl_mac_full">' in webpanel.make_page(), "Link in den Einstellungen")
pc = open(os.path.join(PI, "..", "mac", "mixxx_bridge", "programs_copy.py"), encoding="utf-8").read()
check('"/download/light-butler-mac-voll.zip"' in pc, "auch auf dem Stick")
finish("test_mac_paket")
