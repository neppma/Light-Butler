"""Pi umbenennen: ./deploy.sh rename NAME stellt den Rechnernamen am Pi um (rename_host.sh, mit sudo) und traegt den
neuen Namen am Mac ueberall ein (~/.light-butler-pi, Mixxx-App, Light-Butler Helfer). Getestet im Trockenlauf
(S2L_DRY=1: ssh und scp werden nur angezeigt) mit einem eigenen HOME, nichts am echten Pi oder Mac."""
import os
import subprocess
import tempfile

from _common import ROOT, check, finish

DEPLOY = os.path.join(ROOT, "deploy.sh")
home = tempfile.mkdtemp()


def run(*args, **env):
    e = dict(os.environ, HOME=home, S2L_DRY="1", S2L_YES="1", **env)
    e.pop("S2L_PI", None)
    return subprocess.run(["bash", DEPLOY, *args], capture_output=True, text=True, env=e)


r = run("where")
check(r.stdout.strip() == "admin@lightbutler.local", "ohne Einstellung: lightbutler.local")
open(os.path.join(home, ".light-butler-pi"), "w").write("anderer.local\n")
check(run("where").stdout.strip() == "admin@anderer.local", "Pi aus ~/.light-butler-pi (gemeinsam fuer alle Mac-Teile)")
open(os.path.join(home, ".light-butler-pi"), "w").write("lightbutler.local\n")

for bad in ("Light_Butler", "-x", "x-", "Gross", ""):
    rr = run("rename", bad)
    check(rr.returncode != 0 and "ssh" not in rr.stdout, f"ungueltiger Name abgelehnt: {bad!r}")

os.makedirs(os.path.join(home, "Light-Butler"))
os.makedirs(os.path.join(home, "Light-Butler-Helfer"))
open(os.path.join(home, "Light-Butler", "pi_host"), "w").write("lightbutler.local\n")
open(os.path.join(home, "Light-Butler", "config.sh"), "w").write('PI="lightbutler.local"\nMIXXX_BIN="/x"\n')
open(os.path.join(home, "Light-Butler-Helfer", "pi_host"), "w").write("lightbutler.local\n")
r = run("rename", "lightbutler")
check(r.returncode == 0, "Umbenennen laeuft durch")
check("scp pi/rename_host.sh admin@lightbutler.local:lichtshow/rename_host.sh" in r.stdout
      and "ssh -t admin@lightbutler.local sudo bash lichtshow/rename_host.sh lightbutler" in r.stdout,
      "kopiert rename_host.sh und ruft es mit sudo auf (Passwort tippt der Nutzer)")
rd = lambda *p: open(os.path.join(home, *p)).read()
check(rd(".light-butler-pi").strip() == "lightbutler.local", "neuer Name gemerkt, Domaene bleibt")
check(rd("Light-Butler", "pi_host").strip() == "lightbutler.local" and 'PI="lightbutler.local"' in rd("Light-Butler", "config.sh")
      and 'MIXXX_BIN="/x"' in rd("Light-Butler", "config.sh"), "Mixxx-App: neuer Name, Rest unveraendert")
check(rd("Light-Butler-Helfer", "pi_host").strip() == "lightbutler.local", "Helfer: neuer Name")
check(run("where").stdout.strip() == "admin@lightbutler.local", "deploy.sh spricht danach den neuen Namen an")

sh = os.path.join(ROOT, "pi", "rename_host.sh")
check(subprocess.run(["bash", "-n", sh]).returncode == 0, "rename_host.sh: Syntax in Ordnung")
txt = open(sh).read()
check("hostnamectl set-hostname" in txt and "127.0.1.1" in txt and "systemd-run --on-active=5" in txt,
      "Pi: hostnamectl, /etc/hosts, Neustart als eigener Auftrag")
bad = subprocess.run(["bash", sh, "Bad_Name"], capture_output=True, text=True)
check(bad.returncode == 2, "rename_host.sh lehnt ungueltige Namen ab, bevor es etwas aendert")
for f in ("install_launcher.sh", "../helper/install_helper.sh"):
    t = open(os.path.join(ROOT, "mac", "mixxx_bridge", f)).read()
    check('"$HOME/.light-butler-pi"' in t, f"{os.path.basename(f)} liest und schreibt die gemeinsame Einstellung")
finish("test_umbenennen")
