"""deploy.sh push: haelt an, wenn im Ordner etwas aus main fehlt, damit auf dem Pi nichts ueberschrieben wird. Ohne Netz: rsync und ssh sind Attrappen."""
import os
import shutil
import stat
import subprocess
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp(prefix="s2l_deploy_")
repo, fake, log = os.path.join(tmp, "repo"), os.path.join(tmp, "bin"), os.path.join(tmp, "aufrufe.txt")
os.makedirs(os.path.join(repo, "tests"))
os.makedirs(fake)
shutil.copy(os.path.join(ROOT, "deploy.sh"), repo)
with open(os.path.join(repo, "tests", "run_all.sh"), "w") as f:
    f.write("exit 0\n")
for tool in ("rsync", "ssh"):
    p = os.path.join(fake, tool)
    with open(p, "w") as f:
        f.write(f'#!/bin/sh\necho {tool} >> "{log}"\n')
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
env.update(PATH=fake + os.pathsep + os.environ["PATH"], S2L_PI="admin@attrappe.invalid", S2L_PI_FILE=os.path.join(tmp, "keine"))


def git(*args):
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid", *args], cwd=repo, env=env, check=True, capture_output=True)


def push(*args, **more):
    if os.path.exists(log):
        os.unlink(log)
    r = subprocess.run(["bash", "deploy.sh", "push", *args], cwd=repo, env={**env, **more}, capture_output=True, text=True)
    calls = open(log).read().split() if os.path.exists(log) else []
    return r.returncode, r.stdout, calls


git("init", "-q", "-b", "main")
git("commit", "-q", "--allow-empty", "-m", "Anfang")
git("checkout", "-q", "-b", "chat")
rc, out, calls = push()
check(rc == 0 and "rsync" in calls and "ACHTUNG" not in out, "Zweig enthaelt alles aus main: wird kopiert")
git("commit", "-q", "--allow-empty", "-m", "Arbeit im Chat")
rc, out, calls = push()
check(rc == 0 and "rsync" in calls and "ACHTUNG" not in out, "Zweig ist weiter als main: wird kopiert")

git("checkout", "-q", "main")
git("commit", "-q", "--allow-empty", "-m", "Lumi aus dem anderen Chat")
git("checkout", "-q", "chat")
rc, out, calls = push()
check(rc == 1 and not calls, "main ist weiter: nichts wird kopiert")
check("ACHTUNG" in out and "Lumi aus dem anderen Chat" in out and "git merge main" in out, "Meldung nennt den fehlenden Commit und den Ausweg")
rc, out, calls = push("-n")
check(rc == 0 and "ACHTUNG" in out and "rsync" in calls and "Trockenlauf" in out, "Trockenlauf warnt nur")
rc, out, calls = push(S2L_OHNE_MAIN="1")
check(rc == 0 and "ACHTUNG" in out and "rsync" in calls, "mit Absicht trotzdem: warnt und kopiert")
git("merge", "-q", "--no-edit", "main")
rc, out, calls = push()
check(rc == 0 and "rsync" in calls and "ACHTUNG" not in out, "main hergeholt: wird wieder kopiert")

shutil.rmtree(os.path.join(repo, ".git"))
rc, out, calls = push()
check(rc == 0 and "rsync" in calls and "ACHTUNG" not in out, "ohne Git (Kopie des Ordners): wird kopiert wie bisher")
shutil.rmtree(tmp, ignore_errors=True)

# deploy.sh alles (Wunsch 07.11.2026): alles in einem Befehl, Neustart nur bei Programmdateien, Mixxx-App wird nie hart beendet
src = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
al = src[src.index("  alles)"):src.index('echo "Fertig." ;;')]
check(subprocess.run(["bash", "-n", os.path.join(ROOT, "deploy.sh")]).returncode == 0, "deploy.sh ohne Syntaxfehler")
check('bash "$0" push' in al and 'bash "$0" restart' in al and "if [ -n \"$PROG\" ]" in al, "alles: push (mit Tests), restart nur bei Programmdateien")
check("grep -E '\\.(py|yaml|service|sh)$'" in al and "grep -v '^static/'" in al, "Seiten (static/) brauchen keinen Neustart")
check('S2L_PI="$PI_HOST" S2L_NO_OPEN=1 bash mac/mixxx_bridge/install_launcher.sh' in al and 'S2L_AUTOSTART="$AUTO"' in al, "Mac: beide Installer ohne Rueckfragen, Autostart bleibt")
check("osascript" not in al and "pkill -f \"mixxx" not in al and 'pgrep -f "mixxx_bridge\\.py --stdin"' in al, "Mixxx-App nie hart beenden: warten, bis du sie beendest, dann neu starten")
check('pgrep -f "mixxx_bridge.py"' not in al, "nur die laufende Bruecke zaehlt (nicht jeder Befehl mit dem Dateinamen, Fehlerbericht 14.11.2026)")
finish("test_deploy")
