"""Ein Befehl fuer den Pi (Wunsch von Markus, 17.11.2026, statt eines 1-GB-Images): pi/install_online.sh holt light-butler-pi.zip
aus dem neuesten Release, packt es nach ~/Light-Butler-Pi aus (altes Paket beiseite, nie geloescht) und startet install_pi.sh.
Hier ohne Internet (file://) und ohne Installation (S2L_NO_RUN)."""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from _common import ROOT, check, finish

PI = os.path.join(ROOT, "pi")
SH = os.path.join(PI, "install_online.sh")
sys.path.insert(0, PI)
import pakete  # noqa: E402

txt = open(SH, encoding="utf-8").read()
check(subprocess.run(["bash", "-n", SH]).returncode == 0, "Skript ohne Syntaxfehler")
check("releases/latest/download/light-butler-pi.zip" in txt and "/dev/tty" in txt and "aarch64" in txt,
      "neuestes Release, Eingabe vom Terminal, nur 64-Bit-Pi")

tmp = tempfile.mkdtemp()
base = os.path.join(tmp, "lichtshow")
shutil.copytree(PI, base, ignore=shutil.ignore_patterns("__pycache__", "shows", "aufnahmen", "*.json"))
for n in ("HANDBUCH.md", "MANUAL_EN.md"):
    shutil.copy(os.path.join(ROOT, "docs", n), os.path.join(base, n))
zp = os.path.join(tmp, "light-butler-pi.zip")
open(zp, "wb").write(pakete.pi_zip(base))
home = os.path.join(tmp, "home")
os.makedirs(os.path.join(home, "Light-Butler-Pi"))
open(os.path.join(home, "Light-Butler-Pi", "alt.txt"), "w").write("x")
env = dict(os.environ, S2L_ZIP_URL="file://" + zp, S2L_HOME=home, S2L_NO_RUN="1", S2L_SKIP_ARCH="1")
r = subprocess.run(["bash", SH], env=env, capture_output=True, text=True)
check(r.returncode == 0 and os.path.isfile(os.path.join(home, "Light-Butler-Pi", "install_pi.sh"))
      and os.path.isfile(os.path.join(home, "Light-Butler-Pi", "lichtshow", "show.py")), "Paket ausgepackt: " + r.stdout[-200:] + r.stderr[-300:])
check(os.path.isfile(os.path.join(home, "Light-Butler-Pi.alt", "alt.txt")), "altes Paket beiseite, nicht geloescht")

# Fremdes ZIP (Datei ausserhalb von Light-Butler-Pi/) wird nicht ausgepackt
bad = os.path.join(tmp, "boese.zip")
with zipfile.ZipFile(bad, "w") as z:
    z.writestr("Light-Butler-Pi/install_pi.sh", "echo")
    z.writestr("../ausserhalb.txt", "x")
home2 = os.path.join(tmp, "home2")
os.makedirs(home2)
r = subprocess.run(["bash", SH], env=dict(env, S2L_ZIP_URL="file://" + bad, S2L_HOME=home2), capture_output=True, text=True)
check(r.returncode != 0 and not os.path.exists(os.path.join(tmp, "ausserhalb.txt")) and not os.path.exists(os.path.join(home2, "Light-Butler-Pi")),
      "fremdes Paket abgelehnt")

# Ohne S2L_SKIP_ARCH auf dem Mac: kein Pi -> Abbruch mit Hinweis
if os.uname().machine != "aarch64" or sys.platform == "darwin":
    e2 = {k: v for k, v in env.items() if k != "S2L_SKIP_ARCH"}
    r = subprocess.run(["bash", SH], env=e2, capture_output=True, text=True)
    check(r.returncode != 0 and "64-Bit" in r.stdout, "kein Pi: Abbruch mit Hinweis")

for f in ("README.md", "README.de.md", "docs/HANDBUCH.md", "docs/MANUAL_EN.md"):
    check("pi/install_online.sh | bash" in open(os.path.join(ROOT, f), encoding="utf-8").read(), f + " nennt den Befehl")
shutil.rmtree(tmp, ignore_errors=True)
finish("test_install_online")
