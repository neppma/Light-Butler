"""
light_butler_exe.py - Startprogramm fuer Light-Butler.exe (Windows, Wunsch von Markus, 15.11.2026).

Die Exe (PyInstaller, windows/build_exe.py) enthaelt nur Python und die Pakete (numpy, PyYAML, sounddevice, mido,
python-rtmidi, pyserial). Die Programme des Light-Butler liegen als normale Dateien im Ordner "lichtshow" neben der Exe:
genau wie am Pi, mit Einstellungen, Szenen und Shows daneben. Dieses Startprogramm
  - legt beim ersten Start die Einstellungen an: alle Ausgaben AUS (DMX, WLED, Nanoleaf),
  - liest die Startoptionen aus lichtshow/show.conf (SHOW_ARGS=...), weitere Optionen von der Befehlszeile,
  - startet lichtshow/show.py in diesem Python und startet neu, wenn das Panel einen Neustart verlangt (Code 3).
"""
import os
import runpy
import shlex
import subprocess
import sys

RESTART_CODE = 3
FIRST_SETTINGS = '{\n "ola_out": 0.0,\n "wled_out": 0.0,\n "nano_out": 0.0\n}\n'


def base_dir():
    """Ordner der Exe (gebaut) bzw. dieses Skripts (Entwicklung)."""
    return os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))


def show_args(prog, conf_name="show.conf"):
    """SHOW_ARGS aus show.conf (letzte Zeile gewinnt), wie start.ps1 und der Dienst am Pi."""
    args = []
    try:
        with open(os.path.join(prog, conf_name), encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("SHOW_ARGS="):
                    args = shlex.split(s[len("SHOW_ARGS="):], posix=False)
    except OSError:
        pass
    return [a.strip('"') for a in args]


def first_run(prog):
    """Neue Anlage: alle Ausgaben aus. Vorhandene Einstellungen bleiben unberuehrt."""
    p = os.path.join(prog, "settings.json")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write(FIRST_SETTINGS)
        with open(os.path.join(prog, "sicherheit.json"), "w", encoding="utf-8") as f:   # Sicherheitshinweis (safety.py)
            f.write('{"ok": false}\n')
        return True
    return False


def panel_port(args):
    """Port des Web-Panels aus den Startoptionen (--web 8080 oder --web=8080), 0 = kein Panel."""
    for i, a in enumerate(args):
        val = args[i + 1] if a == "--web" and i + 1 < len(args) else (a[6:] if a.startswith("--web=") else None)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                return 0
    return 0


def open_panel_later(port, delay=4.0, timer=None):
    """Startmenue und Desktop-Symbol (Option --browser, 16.11.2026): Panel im Browser oeffnen, sobald es laeuft."""
    import threading
    import webbrowser
    t = (timer or threading.Timer)(delay, webbrowser.open, ["http://localhost:%d/" % port])
    t.daemon = True
    t.start()
    return t


HELPER_ARGS = ["127.0.0.1", "--no-apc", "--no-lumi", "--no-audio", "--no-stems"]   # APC, Lumi, Ton haengen am PC direkt
MUSIK_ARGS = ["--no-stems"]          # Musik-Rechner (16.11.2026): Helfer mit APC, Lumi und Ton an einen anderen Light-Butler
PI_FILE = ".light-butler-pi"         # Adresse des Light-Butler, schreibt der Installer (wie install_mac.sh und deploy.sh)


def pi_host(home=None):
    """Adresse des Light-Butler aus ~/.light-butler-pi (erste Zeile), sonst lightbutler.local."""
    try:
        with open(os.path.join(home or os.path.expanduser("~"), PI_FILE), encoding="utf-8") as f:
            h = f.readline().strip()
        if h and all(c.isalnum() or c in "._-" for c in h):
            return h
    except OSError:
        pass
    return "lightbutler.local"


def helper_on(prog, helper):
    """HELFER=1 (Standard) in show.conf und der Helfer liegt bei der Exe."""
    if not os.path.isfile(helper):
        return False
    val = "1"
    try:
        with open(os.path.join(prog, "show.conf"), encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("HELFER="):
                    val = line.strip()[len("HELFER="):].strip()
    except OSError:
        pass
    return val != "0"


def run_script(argv, run=None):
    """Die Exe als Python: "Light-Butler.exe skript.py ..." fuehrt skript.py aus. So starten Helfer und Bruecke ihre Messungen
    (Lautheit, Tonart: [sys.executable, skript.py, ...]); in der Exe ist sys.executable die Exe selbst."""
    script = os.path.abspath(argv[0])
    d = os.path.dirname(script)
    if d not in sys.path:
        sys.path.insert(0, d)
    sys.argv = [script] + list(argv[1:])
    try:
        (run or runpy.run_path)(script, run_name="__main__")
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return 0


def start_helper(base, popen=None, mode="--helfer"):
    """Musik-Teil des Helfers als eigenen Prozess ohne Fenster starten (Log %LOCALAPPDATA%\\Light-Butler\\helfer.log)."""
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA") or base, "Light-Butler")
    os.makedirs(log_dir, exist_ok=True)
    exe = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
    log = open(os.path.join(log_dir, "helfer.log"), "a", encoding="utf-8")
    flags = 0x08000000 if sys.platform == "win32" else 0                    # CREATE_NO_WINDOW
    return (popen or subprocess.Popen)(exe + [mode], stdout=log, stderr=subprocess.STDOUT, creationflags=flags)


def main(argv=None, run=None, popen=None, timer=None):
    argv = sys.argv[1:] if argv is None else argv
    base = base_dir()
    helper = os.path.join(base, "helfer", "helper", "helper.py")
    if argv and argv[0].lower().endswith(".py") and os.path.isfile(argv[0]):
        return run_script(argv, run)
    if argv and argv[0] == "--musik":                  # Musik-Rechner: Helfer ohne Fenster starten, dieses Fenster schliesst sich
        start_helper(base, popen, "--helfer-musik")
        print("Light-Butler Helfer gestartet, Ziel %s (Log: %%LOCALAPPDATA%%\\Light-Butler\\helfer.log)" % pi_host(), flush=True)
        return 0
    if argv and argv[0] == "--helfer-musik":
        os.environ.setdefault("PYTHONUTF8", "1")
        return run_script([helper, pi_host()] + MUSIK_ARGS + list(argv[1:]), run)
    if argv and argv[0] == "--helfer":
        os.environ.setdefault("PYTHONUTF8", "1")
        return run_script([helper] + HELPER_ARGS + list(argv[1:]), run)
    browser = "--browser" in argv                          # nur beim Start vom Symbol, nie beim Neustart
    argv = [a for a in argv if a != "--browser"]
    prog = os.path.join(base, "lichtshow")
    if not os.path.isfile(os.path.join(prog, "show.py")):
        print("Ordner 'lichtshow' mit show.py fehlt neben Light-Butler.exe (ZIP vollstaendig entpacken).")
        return 1
    if first_run(prog):
        print("Neue Anlage: alle Ausgaben AUS (DMX, WLED, Nanoleaf). Einschalten im Panel: Einstellungen -> Ausgabe.")
    args = show_args(prog) + list(argv)
    if not os.environ.get("LB_HELPER_STARTED") and helper_on(prog, helper):   # nur beim ersten Start, nicht nach Neustart
        try:
            start_helper(base, popen)
            os.environ["LB_HELPER_STARTED"] = "1"
            print("Musik-Teil des Helfers gestartet (Log: %LOCALAPPDATA%\\Light-Butler\\helfer.log)", flush=True)
        except OSError as e:
            print("Helfer liess sich nicht starten: %s" % e, flush=True)
    if browser and panel_port(args):
        open_panel_later(panel_port(args), timer=timer)
    os.chdir(prog)
    if prog not in sys.path:
        sys.path.insert(0, prog)
    os.environ["LB_RESTART_EXIT"] = "1"                 # Neustart aus dem Panel: show.py endet mit Code 3
    os.environ.setdefault("PYTHONUTF8", "1")
    print("Light-Butler: show.py " + " ".join(args), flush=True)
    sys.argv = [os.path.join(prog, "show.py")] + args
    code = 0
    try:
        (run or runpy.run_path)(sys.argv[0], run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if e.code not in (None, 0) and not isinstance(e.code, int):
            print(e.code)
    if code == RESTART_CODE:                            # neu starten: frisches Python, gleiche Optionen von der Befehlszeile
        print("Neustart ...", flush=True)
        exe = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
        (popen or subprocess.Popen)(exe + list(argv))
        return 0
    return code


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()                    # Exe: Hintergrund-Prozesse (Analyse, Schaetzung) starten sich so
    sys.exit(main())
