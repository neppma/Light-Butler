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
finish("test_windows_exe")
