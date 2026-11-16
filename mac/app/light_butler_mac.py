"""
light_butler_mac.py - Startprogramm der Mac-App Light-Butler.app (16.11.2026, Gegenstueck zu windows/light_butler_exe.py).

Die App (PyInstaller, mac/app/build_app.py, als DMG zum Reinziehen in "Programme") enthaelt Python und alle Pakete. Die
Programme liegen in der App unter Contents/Resources/lichtshow und helfer; beim Start kopiert dieses Programm sie nach
~/Light-Butler (wie install_lightbutler_mac.sh), denn dort speichert der Light-Butler Einstellungen, Szenen und Shows.
Was der Anlage gehoert (*.json, show.conf, backup.conf, fixtures.yaml, homematic.yaml, shows/), wird nie ueberschrieben.

Ablauf: ein kleines Fenster (tkinter) mit "Panel oeffnen" und "Beenden"; der Light-Butler selbst laeuft als eigener Prozess
(dieselbe App mit --show), ebenso der Musik-Teil des Helfers (--helfer). Beenden im Fenster oder im Dock schickt SIGTERM:
show.py macht sauber Blackout. Neustart aus dem Panel (Code 3) startet den Prozess neu.
"""
import os
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _d in (HERE, os.path.join(os.path.dirname(os.path.dirname(HERE)), "windows")):
    if _d not in sys.path:
        sys.path.insert(0, _d)
import light_butler_exe as lbe  # noqa: E402   gemeinsame Teile (show.conf, erster Start, Skripte, Helfer)

KEEP_EXT = (".json",)
KEEP_NAMES = {"show.conf", "backup.conf", "fixtures.yaml", "homematic.yaml"}
KEEP_DIRS = {"shows"}
STAND = ".light-butler-stand"


def home_dir():
    """Ordner der Anlage: LB_HOME (Tests), sonst ~/Light-Butler."""
    return os.environ.get("LB_HOME") or os.path.join(os.path.expanduser("~"), "Light-Butler")


def bundle_dir():
    """Contents/Resources der App (gebaut) bzw. ein Ordner mit lichtshow/ und helfer/ (Entwicklung: LB_BUNDLE)."""
    if os.environ.get("LB_BUNDLE"):
        return os.environ["LB_BUNDLE"]
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Resources")
    return HERE


def _stand(src):
    """Kennung der mitgelieferten Programme (Groesse und Zeit aller Dateien), damit nur nach einem Update kopiert wird."""
    n, t = 0, 0
    for root, _d, files in os.walk(src):
        for f in files:
            st = os.stat(os.path.join(root, f))
            n += st.st_size
            t = max(t, int(st.st_mtime))
    return "%d-%d" % (n, t)


def sync(src, dest):
    """Programme von src nach dest kopieren; was der Anlage gehoert, nie ueberschreiben (beim ersten Mal anlegen).
    Rueckgabe: Zahl kopierter Dateien (0 = schon aktuell)."""
    if not os.path.isdir(src):
        return 0
    mark = os.path.join(dest, STAND)
    stand = _stand(src)
    try:
        if open(mark, encoding="utf-8").read().strip() == stand:
            return 0
    except OSError:
        pass
    n = 0
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        if rel.split(os.sep)[0] in KEEP_DIRS:
            continue
        for f in files:
            s = os.path.join(root, f)
            d = os.path.join(dest, rel, f) if rel != "." else os.path.join(dest, f)
            keep = f in KEEP_NAMES or f.endswith(KEEP_EXT)
            if keep and os.path.exists(d):
                continue
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            n += 1
    with open(mark, "w", encoding="utf-8") as fh:
        fh.write(stand + "\n")
    return n


def child(args, log_name):
    """Dieselbe App als eigener Prozess (frozen: die Exe, sonst python + dieses Skript), Ausgabe ins Log."""
    log_dir = os.path.join(os.path.expanduser("~"), "Library", "Logs", "Light-Butler")
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, log_name), "a", encoding="utf-8")
    exe = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
    env = dict(os.environ, PYTHONUTF8="1")
    return subprocess.Popen(exe + args, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)


def run_show(argv, run=None):
    """--show: show.py aus ~/Light-Butler/lichtshow in diesem Python (wie die Exe unter Windows, ohne Helfer)."""
    os.environ["LB_HELPER_STARTED"] = "1"                 # den Helfer startet das Fenster selbst
    lbe.base_dir = lambda: home_dir()
    restart = []
    code = lbe.main(list(argv), run=run, popen=lambda c: restart.append(c))
    return lbe.RESTART_CODE if restart else code          # Neustart macht das Fenster (startet --show neu)


class App:
    """Kleines Fenster: Zustand, Panel oeffnen, Beenden. Haelt Light-Butler und Helfer am Laufen."""

    def __init__(self, port):
        import tkinter as tk
        self.tk = tk
        self.port = port
        self.show = None
        self.helper = None
        self.stopping = False
        self.root = tk.Tk()
        self.root.title("Light-Butler")
        self.root.geometry("380x170")
        self.root.resizable(False, False)
        tk.Label(self.root, text="Light-Butler", font=("Helvetica", 20, "bold")).pack(pady=(14, 2))
        self.status = tk.Label(self.root, text="startet ...", fg="#555")
        self.status.pack()
        row = tk.Frame(self.root)
        row.pack(pady=14)
        tk.Button(row, text="Panel öffnen", width=14, command=self.open_panel).pack(side="left", padx=6)
        tk.Button(row, text="Beenden", width=10, command=self.quit).pack(side="left", padx=6)
        tk.Label(self.root, text="Fenster schließen = weiter im Hintergrund · Beenden = Licht aus", fg="#888",
                 font=("Helvetica", 10)).pack()
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        try:
            self.root.createcommand("tk::mac::Quit", self.quit)              # Dock -> Beenden, Cmd-Q
            self.root.createcommand("tk::mac::ReopenApplication", self.root.deiconify)
        except tk.TclError:
            pass

    def open_panel(self):
        import webbrowser
        webbrowser.open("http://localhost:%d/" % self.port)

    def start_show(self):
        self.show = child(["--show"], "show.log")

    def tick(self):
        if self.stopping:
            return
        code = self.show.poll() if self.show else None
        if self.show and code is not None:
            if code == lbe.RESTART_CODE:
                self.status.config(text="startet neu ...")
                self.start_show()
            else:
                self.status.config(text="beendet (Code %s), siehe ~/Library/Logs/Light-Butler/show.log" % code)
                self.show = None
        elif self.show:
            self.status.config(text="läuft · Panel: http://localhost:%d/" % self.port)
        self.root.after(1000, self.tick)

    def quit(self):
        self.stopping = True
        self.status.config(text="Licht aus, beendet ...")
        self.root.update()
        for p in (self.show, self.helper):
            if p and p.poll() is None:
                p.send_signal(signal.SIGTERM)
        t0 = time.time()
        for p in (self.show, self.helper):
            while p and p.poll() is None and time.time() - t0 < 8:
                time.sleep(0.1)
            if p and p.poll() is None:
                p.kill()
        self.root.destroy()

    def run(self, helper):
        self.start_show()
        if helper:
            self.helper = child(["--helfer"], "helfer.log")
        if not os.environ.get("LB_NO_BROWSER"):            # Tests: kein Browser
            self.root.after(4000, self.open_panel)
        self.root.after(1000, self.tick)
        self.root.mainloop()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    argv = [a for a in argv if not a.startswith("-psn_")]   # aeltere macOS-Fassungen haengen das beim Start aus dem Finder an
    home = home_dir()
    if argv and argv[0].lower().endswith(".py") and os.path.isfile(argv[0]):
        return lbe.run_script(argv)                          # Messungen von Helfer und Bruecke: [sys.executable, skript.py]
    if argv and argv[0] == "--show":
        return run_show(argv[1:])
    if argv and argv[0] == "--helfer":
        os.environ.setdefault("PYTHONUTF8", "1")
        return lbe.run_script([os.path.join(home, "helfer", "helper", "helper.py")] + lbe.HELPER_ARGS + list(argv[1:]))
    src = bundle_dir()
    os.makedirs(home, exist_ok=True)
    for sub in ("lichtshow", "helfer"):
        sync(os.path.join(src, sub), os.path.join(home, sub))
    prog = os.path.join(home, "lichtshow")
    if not os.path.isfile(os.path.join(prog, "show.py")):
        print("lichtshow/show.py fehlt in %s" % home)
        return 1
    lbe.first_run(prog)
    port = lbe.panel_port(lbe.show_args(prog)) or 8080
    helper = lbe.helper_on(prog, os.path.join(home, "helfer", "helper", "helper.py"))
    App(port).run(helper)
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
