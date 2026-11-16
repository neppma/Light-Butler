"""Software fuer andere Rechner (Wunsch von Markus, 07.11.2026): Einstellungen, unten, laden das Mac-Paket (Mixxx-Bruecke,
Helfer, Pegelkurven, install_mac.sh) und das Windows-Paket (Pegelkurven) als ZIP. Der Pi baut sie bei jedem Abruf neu."""
import io
import os
import subprocess
import zipfile

from _common import PI, ROOT, check, finish

import pakete
import texts
import webpanel

data = pakete.mac_zip()
check(data is not None, "Mac-Paket entsteht (Entwicklung: Ordner mac/)")
z = zipfile.ZipFile(io.BytesIO(data))
names = set(z.namelist())
need = {"Light-Butler-Mac/install_mac.sh", "Light-Butler-Mac/LIESMICH.txt", "Light-Butler-Mac/mixxx_bridge/mixxx_bridge.py",
        "Light-Butler-Mac/mixxx_bridge/install_launcher.sh", "Light-Butler-Mac/mixxx_bridge/energie_modell.json",
        "Light-Butler-Mac/mixxx_bridge/Light-Butler-Bridge.midi.xml", "Light-Butler-Mac/helper/helper.py",
        "Light-Butler-Mac/helper/install_helper.sh", "Light-Butler-Mac/stems/install_stems.sh", "Light-Butler-Mac/stems/stems_show.py"}
check(need <= names, f"Mac-Paket: Installationsskript, Bruecke, Helfer, Pegelkurven, Mapping ({sorted(need - names)})")
# alles, was install_launcher.sh und install_helper.sh kopieren, muss im Paket sein
for sh in ("mixxx_bridge/install_launcher.sh", "helper/install_helper.sh"):
    src = open(os.path.join(ROOT, "mac", sh), encoding="utf-8").read()
    import re
    used = set(re.findall(r'\$(?:HERE|SRC)/([\w.]+\.(?:py|json))', src))
    missing = [u for u in used if not any(n.endswith("/" + u) for n in names)]
    check(not missing, f"{sh}: alle kopierten Dateien im Paket ({missing})")
check(not any("__pycache__" in n or n.endswith(".pyc") or "/analysis/" in n for n in names), "keine Zwischendateien oder eigenen Daten im Paket")
check((z.getinfo("Light-Butler-Mac/install_mac.sh").external_attr >> 16) & 0o111, "Skripte ausfuehrbar")
inst = os.path.join(ROOT, "mac", "install_mac.sh")
check(subprocess.run(["bash", "-n", inst]).returncode == 0, "install_mac.sh ohne Syntaxfehler")
src = open(inst, encoding="utf-8").read()
check("pip\" install --quiet mido python-rtmidi numpy scipy soundfile sounddevice" in src and "install_launcher.sh" in src and "install_helper.sh" in src,
      "install_mac.sh: Python-Pakete, Bruecke und Helfer")
check("xcode-select --install" in src and 'S2L_SKIP_VENV=1' in src, "ohne python3: sagt, wie; Bruecke legt keine zweite Umgebung an")

w = zipfile.ZipFile(io.BytesIO(pakete.win_zip()))
check(set(w.namelist()) == {"Light-Butler-Windows/LIESMICH.txt", "Light-Butler-Windows/install_stems.ps1", "Light-Butler-Windows/stems_show.py",
                            "Light-Butler-Windows/stem_curves.py", "Light-Butler-Windows/LICENSE"}, "Windows-Paket: Pegelkurven samt Installationsskript und Lizenz")
check("\r\n" in w.read("Light-Butler-Windows/LIESMICH.txt").decode("utf-8"), "LIESMICH mit Windows-Zeilenenden")
check(pakete.mac_zip(dirs=("/gibtsnicht",)) is None and pakete.win_zip(dirs=("/gibtsnicht",)) is None, "Dateien fehlen: kein halbes Paket")

page = webpanel.settings_page()
check('href="/download/light-butler-mac.zip"' in page and 'href="/download/light-butler-windows.zip"' in page, "Einstellungen: zwei Download-Knoepfe")
_all = {}
for _n in dir(texts):
    _v = getattr(texts, _n)
    if isinstance(_v, dict):
        _all.update({k: v for k, v in _v.items() if isinstance(v, tuple)})
check(all(k in _all and len(_all[k]) == 2 for k in ("nav_soft", "dl_mac", "dl_win", "dl_hint")), "Texte deutsch und englisch")
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
dep = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
check('"/download/light-butler-mac.zip"' in api and "pakete/mac/" in dep and "mac/install_mac.sh mac/mixxx_bridge mac/helper mac/stems" in dep,
      "Pi liefert die Pakete, deploy.sh kopiert die Dateien")
finish("test_pakete")
