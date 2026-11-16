"""
build_exe.py - baut Light-Butler.exe fuer Windows (PyInstaller) und das ZIP zum Weitergeben.

Aufruf am Windows-PC im Projektordner (eigene Bau-Umgebung, damit die Entwicklung sauber bleibt):
    py -3.12 -m venv .venv-build
    .venv-build\\Scripts\\python -m pip install pyinstaller numpy pyyaml sounddevice mido python-rtmidi pyserial
    .venv-build\\Scripts\\python windows\\build_exe.py
Ergebnis: windows\\build\\dist\\Light-Butler\\ (Light-Butler.exe, _internal\\, lichtshow\\, LIESMICH.txt) und
windows\\build\\light-butler-windows-exe.zip.

Die Exe enthaelt nur Python und die Pakete. Die Programme liegen offen in lichtshow\\ (aus pakete.windows_zip: ohne
Zustandsdateien, neutrale Geraete), weil der Light-Butler Einstellungen, Szenen und Shows neben sich speichert.
Welche Module die Exe braucht, liest dieses Skript aus den import-Zeilen aller Programme (ast); eigene Module
werden nicht eingefroren, sonst wuerden sie die Dateien in lichtshow\\ ueberdecken.
"""
import ast
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PI = os.path.join(ROOT, "pi")
OUT = os.path.join(ROOT, "windows", "build")
NAME = "Light-Butler"
EXTRA = ["serial.tools.list_ports", "serial.tools.list_ports_windows", "rtmidi", "mido.backends.rtmidi",
         "sounddevice", "_cffi_backend", "numpy.fft", "yaml", "soundfile", "scipy.signal", "scipy.io.wavfile",
         "multiprocessing.spawn", "multiprocessing.pool"]

LIESMICH_EXE = """LIGHT-BUTLER ALS PROGRAMM FUER WINDOWS
======================================

Die ganze Lichtsteuerung (Analyse, Szenen, Showmanager, Web-Panel) wie am Raspberry Pi, fuer Windows 10 oder 11.
Python ist eingebaut, es muss nichts installiert werden.

1. Dieses ZIP in einen eigenen Ordner entpacken, zum Beispiel Dokumente\\Light-Butler (nicht nach "Programme",
   dort darf der Light-Butler seine Einstellungen nicht speichern).
2. Light-Butler.exe doppelklicken. Windows zeigt beim ersten Mal evtl. "Der Computer wurde durch Windows geschuetzt":
   "Weitere Informationen" -> "Trotzdem ausfuehren" (die Exe ist nicht kaeuflich signiert).
3. Fragt Windows nach der Firewall: "Private Netzwerke" zulassen (nicht "Oeffentliche"), sonst erreichen Handy, iPad
   und der Ton vom Mac den PC nicht. Das Panel hat keine Anmeldung: nie ins Internet stellen.
4. Panel im Browser: http://localhost:8080/  (Handy/iPad im Heimnetz: http://<Name-des-PC>:8080/)
Das schwarze Fenster zeigt die Meldungen; schliessen = Light-Butler beenden.

WICHTIG: Ein neuer Light-Butler startet mit allen Ausgaben AUS (DMX, WLED, Nanoleaf). Senden zwei Light-Butler im
selben Netz gleichzeitig, kaempfen sie ums Licht. Einschalten im Panel unter Einstellungen -> Ausgabe, wenn nur dieser
sendet. Strobe, Laser und Nebel sind wie bei jeder neuen Anlage aus.

MUSIK: Der Musik-Teil des Helfers startet mit (HELFER=1 in lichtshow\\show.conf, HELFER=0 schaltet ihn ab): Musikordner
(Einstellungen -> Verbindungen), Musik-Datenbank, Vorhoeren, Tempo/Tonart/Energie, Datenpflege. Geloeschtes kommt in den
Ordner "Light-Butler Papierkorb" oben auf dem Laufwerk, nie endgueltig weg. ffmpeg (MP3-Umwandlung, Reparatur, Shazam):
winget install Gyan.FFmpeg. Meldungen: %LOCALAPPDATA%\\Light-Butler\\helfer.log.

MIXXX AM PC: Verknuepfung anlegen: Ziel Light-Butler.exe helfer\\mixxx_bridge\\mixxx_start.py
- startet Mixxx mit der Mixxx-Bruecke (Tempo, Beat, Lied, Drops wie am Mac). Einmalig: loopMIDI installieren
(tobias-erichsen.de, kostenlos) und darin den Anschluss "Light-Butler" anlegen; in Mixxx Einstellungen -> Controller ->
Light-Butler aktivieren, Mapping "Light-Butler Bridge". Vor dem Start sichert sie die Mixxx-Datenbank (die letzten 5 in
%USERPROFILE%\\Light-Butler-Daten\\mixxx-sicherung). Meldungen: %LOCALAPPDATA%\\Light-Butler\\bridge.log, launcher.log.
Ton an einen anderen Licht-Rechner: VB-Cable, Stereomix oder Line-In (der Reihe nach gesucht).

Startoptionen: lichtshow\\show.conf (SHOW_ARGS=...), zum Beispiel --device USB fuer den Audio-Eingang.
Einstellungen, Szenen, Shows und Geraete liegen in lichtshow\\ neben den Programmen.
Aktualisieren: neues ZIP holen, Light-Butler.exe, _internal\\ und die Programme in lichtshow\\ ersetzen;
*.json, show.conf, fixtures.yaml, homematic.yaml und den Ordner shows\\ behalten.
Beim Anmelden starten: Verknuepfung zu Light-Butler.exe in den Autostart-Ordner legen (Windows+R, shell:startup).
"""


HELPER_DIRS = [os.path.join(ROOT, "mac", "helper"), os.path.join(ROOT, "mac", "mixxx_bridge")]   # Musik-Teil (15.11.2026)


def local_modules():
    names = set()
    for d in [PI] + HELPER_DIRS:
        names |= {os.path.splitext(n)[0] for n in os.listdir(d) if n.endswith(".py")}
        names |= {n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n)) and
                  os.path.isfile(os.path.join(d, n, "__init__.py"))}
    return names


def used_modules():
    """Alle absoluten Importe der Programme und des Helfers (Paket.Modul), ohne die eigenen."""
    own, mods = local_modules(), set()
    for root, dirs, files in [w for d in [PI] + HELPER_DIRS for w in os.walk(d)]:
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "static", "shows")]
        for n in files:
            if not n.endswith(".py"):
                continue
            try:
                tree = ast.parse(open(os.path.join(root, n), encoding="utf-8").read())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods |= {a.name for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mods.add(node.module)
    return sorted(m for m in mods if m.split(".")[0] not in own)


def available(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def write_deps(path):
    mods = [m for m in used_modules() + EXTRA if available(m)]
    missing = [m for m in used_modules() if not available(m)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("# automatisch erzeugt von build_exe.py: Module, die die Programme in lichtshow\\ brauchen\n")
        for m in sorted(set(mods)):
            f.write("try:\n    import %s  # noqa\nexcept Exception:\n    pass\n" % m)
    return sorted(set(mods)), missing


def main():
    import PyInstaller.__main__ as pyi                      # nur in der Bau-Umgebung
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    deps = os.path.join(OUT, "_lb_deps.py")
    mods, missing = write_deps(deps)
    print("Module fuer die Exe: %d, nicht installiert (optional): %s" % (len(mods), ", ".join(missing) or "-"))
    pyi.run([os.path.join(ROOT, "windows", "light_butler_exe.py"), "--name", NAME, "--onedir", "--console", "--noconfirm",
             "--distpath", os.path.join(OUT, "dist"), "--workpath", os.path.join(OUT, "work"), "--specpath", OUT,
             "--paths", OUT, "--hidden-import", "_lb_deps", "--collect-all", "sounddevice", "--collect-all", "rtmidi",
             "--collect-all", "soundfile", "--collect-all", "aubio",
             "--log-level", "WARN"])
    dist = os.path.join(OUT, "dist", NAME)
    sys.path.insert(0, PI)
    import pakete
    z = zipfile.ZipFile(io.BytesIO(pakete.windows_zip(PI)))
    for sub in ("lichtshow", "helfer"):                     # Programme und Musik-Teil des Helfers, offen neben der Exe
        pre = "Light-Butler-Windows-Voll/%s/" % sub
        for n in z.namelist():
            if n.startswith(pre) and not n.endswith("/"):
                dest = os.path.join(dist, sub, *n[len(pre):].split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(z.read(n))
    with open(os.path.join(dist, "LIESMICH.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(LIESMICH_EXE + pakete.COPYRIGHT)
    shutil.copy(os.path.join(ROOT, "LICENSE"), os.path.join(dist, "LICENSE"))   # GPLv3 oben, wie in den anderen Paketen
    zpath = os.path.join(OUT, "light-butler-windows-exe.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zo:
        for root, _dirs, files in os.walk(dist):
            for n in files:
                p = os.path.join(root, n)
                zo.write(p, os.path.join(NAME, os.path.relpath(p, dist)))
    print("Fertig: %s (%.0f MB)" % (zpath, os.path.getsize(zpath) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
