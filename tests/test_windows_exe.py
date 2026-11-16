"""Startprogramm der Windows-Exe (windows/light_butler_exe.py): show.conf, erster Start (Ausgaben aus), Neustart (Code 3).
Ohne PyInstaller: das Startprogramm wird direkt aufgerufen, show.py durch eine Attrappe ersetzt."""
import os
import shutil
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "windows"))
import light_butler_exe as lbe  # noqa: E402

base = tempfile.mkdtemp(prefix="s2l_exe_")
prog = os.path.join(base, "lichtshow")
os.makedirs(prog)
open(os.path.join(prog, "show.py"), "w").write("# Attrappe\n")
open(os.path.join(prog, "show.conf"), "w", encoding="utf-8").write(
    "# Kommentar\nSHOW_ARGS=--master 0.5 --web 8080\nSHOW_ARGS=--master 1.0 --device \"Mac (Netzwerk)\" --web 8080\n")
check(lbe.show_args(prog) == ["--master", "1.0", "--device", "Mac (Netzwerk)", "--web", "8080"],
      "show.conf: letzte SHOW_ARGS-Zeile, Anfuehrungszeichen fuer Namen mit Leerzeichen")
check(lbe.show_args(tempfile.mkdtemp()) == [], "ohne show.conf: keine Optionen")

lbe.base_dir = lambda: base
cwd = os.getcwd()
seen = {}


def run_ok(path, run_name):
    seen.update(path=path, argv=list(sys.argv), env=os.environ.get("LB_RESTART_EXIT"), cwd=os.getcwd())


old_argv = sys.argv
try:
    code = lbe.main(["--dry-run"], run=run_ok, popen=lambda c: seen.setdefault("popen", c))
    check(code == 0 and seen["path"] == os.path.join(prog, "show.py") and os.path.samefile(seen["cwd"], prog),
          "startet lichtshow/show.py im Ordner lichtshow")
    check(seen["argv"][1:] == ["--master", "1.0", "--device", "Mac (Netzwerk)", "--web", "8080", "--dry-run"],
          "Optionen aus show.conf, dann von der Befehlszeile")
    check(seen["env"] == "1" and "popen" not in seen, "LB_RESTART_EXIT gesetzt, kein Neustart ohne Code 3")
    st = open(os.path.join(prog, "settings.json")).read()
    check('"ola_out": 0.0' in st and '"wled_out": 0.0' in st and '"nano_out": 0.0' in st, "erster Start: alle Ausgaben aus")

    open(os.path.join(prog, "settings.json"), "w").write('{"ola_out": 1.0}')
    lbe.main([], run=run_ok)
    check(open(os.path.join(prog, "settings.json")).read() == '{"ola_out": 1.0}', "vorhandene Einstellungen bleiben")

    def run_restart(path, run_name):
        raise SystemExit(lbe.RESTART_CODE)
    calls = []
    code = lbe.main(["--dry-run"], run=run_restart, popen=lambda c: calls.append(c))
    check(code == 0 and len(calls) == 1 and calls[0][-1] == "--dry-run", "Code 3: neu starten mit denselben Befehlszeilen-Optionen")

    def run_fail(path, run_name):
        raise SystemExit("YAML-Probleme: x")
    calls = []
    check(lbe.main([], run=run_fail, popen=lambda c: calls.append(c)) == 1 and not calls, "Fehler beim Start: Code 1, kein Neustart")

    os.chdir(cwd)                                         # Windows: den aktuellen Ordner kann man nicht loeschen
    shutil.rmtree(prog)
    check(lbe.main([], run=run_ok) == 1, "ohne lichtshow/show.py: Hinweis und Code 1")
finally:
    sys.argv = old_argv
    os.chdir(cwd)
    os.environ.pop("LB_RESTART_EXIT", None)
    shutil.rmtree(base, ignore_errors=True)

src = open(os.path.join(ROOT, "windows", "build_exe.py"), encoding="utf-8").read()
check('"--onedir"' in src and "_lb_deps" in src and "windows_zip" in src, "Bau: ein Ordner, Module aus den Programmen, lichtshow aus dem Paket")

# Installer (16.11.2026): Symbole starten mit --browser, das Panel oeffnet sich; Neustart und Autostart ohne
check(lbe.panel_port(["--master", "1.0", "--web", "8080"]) == 8080 and lbe.panel_port(["--web=9000"]) == 9000
      and lbe.panel_port(["--dry-run"]) == 0 and lbe.panel_port(["--web", "x"]) == 0, "Port des Panels aus den Optionen")


class FakeTimer:
    made = []

    def __init__(self, delay, fn, args):
        FakeTimer.made.append((delay, fn, args))

    def start(self):
        pass


base2 = tempfile.mkdtemp(prefix="s2l_exe_")
prog2 = os.path.join(base2, "lichtshow")
os.makedirs(prog2)
open(os.path.join(prog2, "show.py"), "w").write("# Attrappe\n")
open(os.path.join(prog2, "show.conf"), "w", encoding="utf-8").write("SHOW_ARGS=--master 1.0 --web 8080\n")
lbe.base_dir = lambda: base2
try:
    seen.clear()
    calls = []

    def run_restart2(path, run_name):
        seen.update(argv=list(sys.argv))
        raise SystemExit(lbe.RESTART_CODE)
    lbe.main(["--browser"], run=run_restart2, popen=lambda c: calls.append(c), timer=FakeTimer)
    check(FakeTimer.made and FakeTimer.made[0][2] == ["http://localhost:8080/"], "--browser: Panel im Browser")
    check("--browser" not in seen["argv"] and calls and "--browser" not in calls[0], "--browser geht nicht an show.py und nicht in den Neustart")
    FakeTimer.made.clear()
    lbe.main([], run=run_ok, timer=FakeTimer)
    check(not FakeTimer.made, "ohne --browser (Autostart): kein Browser")
finally:
    sys.argv = old_argv
    os.chdir(cwd)
    os.environ.pop("LB_RESTART_EXIT", None)
    shutil.rmtree(base2, ignore_errors=True)

iss = open(os.path.join(ROOT, "windows", "light-butler.iss"), encoding="utf-8-sig").read()
check("PrivilegesRequired=lowest" in iss and "{localappdata}\\Programs\\Light-Butler" in iss, "Installer ohne Administrator, im Benutzerordner")
check(iss.count("onlyifdoesntexist") == 2 and "Excludes: \"\\lichtshow\\fixtures.yaml,\\lichtshow\\show.conf\"" in iss,
      "Update ueberschreibt fixtures.yaml und show.conf nicht")
check('Source: "build\\dist\\Light-Butler\\*"' in iss and "OutputBaseFilename=Light-Butler-Setup" in iss and 'NAME = "Light-Butler"' in src
      and 'OUT = os.path.join(ROOT, "windows", "build")' in src, "Installer nimmt die Exe aus build_exe.py")
check(iss.count('Parameters: "--browser"') == 3 and "{userstartup}" in iss and "unchecked" in iss, "Symbole mit Browser, Autostart ohne, Autostart nur auf Wunsch")
_files = [ln for ln in iss.splitlines() if ln.startswith("Source:")]
check(len(_files) == 3 and not any(w in ln for ln in _files for w in (".json", "shows")), "keine Einstellungen im Installer")
wf = open(os.path.join(ROOT, ".github", "workflows", "windows-setup.yml"), encoding="utf-8").read()
check("windows/build_exe.py" in wf and "windows\\light-butler.iss" in wf and "gh release upload" in wf
      and "Light-Butler-Setup.exe" in wf and "types: [published]" in wf, "GitHub baut den Installer und haengt ihn an das Release")
check(all(x in src for x in ("COLLECT", "if available(m)")), "nur installierte Pakete einsammeln (aubio optional)")

# Musik-Rechner (16.11.2026): --musik startet den Helfer ohne Fenster, --helfer-musik mit der Adresse aus ~/.light-butler-pi
home = tempfile.mkdtemp(prefix="s2l_home_")
check(lbe.pi_host(home) == "lightbutler.local", "ohne Datei: lightbutler.local")
open(os.path.join(home, ".light-butler-pi"), "w").write("licht.example\n")
check(lbe.pi_host(home) == "licht.example", "Adresse aus .light-butler-pi")
open(os.path.join(home, ".light-butler-pi"), "w").write("a b;rm\n")
check(lbe.pi_host(home) == "lightbutler.local", "ungueltige Adresse: Standard")
base3 = tempfile.mkdtemp(prefix="s2l_exe_")
os.makedirs(os.path.join(base3, "helfer", "helper"))
open(os.path.join(base3, "helfer", "helper", "helper.py"), "w").write("# Attrappe\n")
lbe.base_dir = lambda: base3
_old_pi = lbe.pi_host
lbe.pi_host = lambda home=None: "licht.example"
try:
    started = []
    check(lbe.main(["--musik"], popen=lambda c, **k: started.append(c)) == 0 and started and started[0][-1] == "--helfer-musik",
          "--musik: Helfer als eigener Prozess")
    seen.clear()

    def run_h(path, run_name):
        seen.update(argv=list(sys.argv))
    lbe.main(["--helfer-musik"], run=run_h)
    check(seen["argv"][1:] == ["licht.example", "--no-stems"], "Helfer mit Adresse, APC/Lumi/Ton an: " + str(seen["argv"][1:]))
finally:
    lbe.pi_host = _old_pi
    sys.argv = old_argv
    os.chdir(cwd)
    shutil.rmtree(base3, ignore_errors=True)
    shutil.rmtree(home, ignore_errors=True)
mi = open(os.path.join(ROOT, "windows", "light-butler-musik.iss"), encoding="utf-8-sig").read()
check("PrivilegesRequired=lowest" in mi and 'Excludes: "\\lichtshow,\\LIESMICH.txt"' in mi and "OutputBaseFilename=Light-Butler-Musik-Setup" in mi,
      "Musik-Installer: ohne Administrator, ohne lichtshow")
check("mixxx_start.py" in mi and 'Parameters: "--musik"' in mi and ".light-butler-pi" in mi and "CreateInputQueryPage" in mi,
      "Musik-Installer: Adresse abfragen, Helfer und Mixxx-Symbol")
check(mi.split("AppId=")[1][:40] != iss.split("AppId=")[1][:40], "eigene AppId (beide nebeneinander installierbar)")
check("light-butler-musik.iss" in wf and "Light-Butler-Musik-Setup.exe" in wf, "GitHub baut auch den Musik-Installer")
finish("test_windows_exe")
