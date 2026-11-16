"""
build_app.py - baut Light-Butler.app und Light-Butler.dmg fuer den Mac (PyInstaller, 16.11.2026).

Aufruf am Mac (GitHub Actions: .github/workflows/mac-dmg.yml) mit einem Python, das tkinter hat (python.org):
    python3 -m venv .venv-build && .venv-build/bin/pip install pyinstaller numpy pyyaml sounddevice mido python-rtmidi pyserial
    .venv-build/bin/python mac/app/build_app.py [VERSION]
Ergebnis: mac/app/build/dist/Light-Butler.app und mac/app/build/Light-Butler.dmg (App zum Ziehen in "Programme").

Die App enthaelt Python und die Pakete; die Programme (lichtshow aus pakete.mac_full_zip: neutrale Geraete, ohne
Zustandsdateien; helfer aus pakete.windows_zip: Musik-Teil) liegen in Contents/Resources und werden beim Start nach
~/Light-Butler kopiert (light_butler_mac.py). Ohne bezahlte Apple-Unterschrift: beim ersten Oeffnen
Systemeinstellungen -> Datenschutz & Sicherheit -> "Dennoch oeffnen".
"""
import io
import os
import plistlib
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PI = os.path.join(ROOT, "pi")
OUT = os.path.join(HERE, "build")
NAME = "Light-Butler"
BUNDLE_ID = "local.lightbutler.app"
MIC_TEXT = ("Der Light-Butler hört die Musik über den Audio-Eingang und steuert danach das Licht. "
            "Light-Butler listens to the music on the audio input to drive the lights.")
sys.path.insert(0, os.path.join(ROOT, "windows"))
import build_exe  # noqa: E402   gleiche Modul-Liste wie die Windows-Exe


def unpack(data, prefix, dest):
    """Dateien unter prefix aus einem ZIP (Bytes) nach dest."""
    z = zipfile.ZipFile(io.BytesIO(data))
    n = 0
    for name in z.namelist():
        if name.startswith(prefix) and not name.endswith("/"):
            p = os.path.join(dest, *name[len(prefix):].split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(z.read(name))
            n += 1
    return n


def main(argv):
    version = (argv[1] if len(argv) > 1 else "0.0").lstrip("v") or "0.0"
    import PyInstaller.__main__ as pyi                      # nur in der Bau-Umgebung
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    deps = os.path.join(OUT, "_lb_deps.py")
    build_exe.OUT = OUT
    mods, missing = build_exe.write_deps(deps)
    print("Module fuer die App: %d, nicht installiert (optional): %s" % (len(mods), ", ".join(missing) or "-"))
    pyi.run([os.path.join(HERE, "light_butler_mac.py"), "--name", NAME, "--windowed", "--onedir", "--noconfirm",
             "--distpath", os.path.join(OUT, "dist"), "--workpath", os.path.join(OUT, "work"), "--specpath", OUT,
             "--paths", OUT, "--paths", os.path.join(ROOT, "windows"), "--hidden-import", "_lb_deps",
             "--hidden-import", "light_butler_exe", "--hidden-import", "tkinter",
             "--osx-bundle-identifier", BUNDLE_ID, "--icon", os.path.join(HERE, "light-butler.icns")]
            + [x for m in build_exe.COLLECT if build_exe.available(m) for x in ("--collect-all", m)]
            + ["--log-level", "WARN"])
    app = os.path.join(OUT, "dist", NAME + ".app")
    res = os.path.join(app, "Contents", "Resources")
    sys.path.insert(0, PI)
    import pakete
    n1 = unpack(pakete.mac_full_zip(PI), "Light-Butler-Mac-Voll/lichtshow/", os.path.join(res, "lichtshow"))
    n2 = unpack(pakete.windows_zip(PI), "Light-Butler-Windows-Voll/helfer/", os.path.join(res, "helfer"))
    print("Programme in der App: lichtshow %d Dateien, helfer %d Dateien" % (n1, n2))
    if not n1 or not n2:
        sys.exit("Programme fehlen")
    shutil.copy(os.path.join(ROOT, "LICENSE"), os.path.join(res, "LICENSE"))
    info_p = os.path.join(app, "Contents", "Info.plist")
    with open(info_p, "rb") as f:
        info = plistlib.load(f)
    info.update({"CFBundleDisplayName": NAME, "CFBundleShortVersionString": version, "CFBundleVersion": version,
                 "NSMicrophoneUsageDescription": MIC_TEXT, "NSHumanReadableCopyright": "© 2026 Markus Nepp, GPLv3",
                 "LSMinimumSystemVersion": "11.0", "NSHighResolutionCapable": True})
    with open(info_p, "wb") as f:
        plistlib.dump(info, f)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)   # ohne bezahlte Unterschrift (ad hoc)
    stage = os.path.join(OUT, "dmg")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    subprocess.run(["ditto", app, os.path.join(stage, NAME + ".app")], check=True)
    os.symlink("/Applications", os.path.join(stage, "Programme"))
    with open(os.path.join(stage, "LIESMICH.txt"), "w", encoding="utf-8") as f:
        f.write(LIESMICH + pakete.COPYRIGHT)
    dmg = os.path.join(OUT, NAME + ".dmg")
    subprocess.run(["hdiutil", "create", "-volname", NAME, "-srcfolder", stage, "-ov", "-format", "UDZO", dmg], check=True)
    print("Fertig: %s (%.0f MB)" % (dmg, os.path.getsize(dmg) / 1e6))
    return 0


LIESMICH = """LIGHT-BUTLER FUER DEN MAC
=========================

1. Light-Butler auf "Programme" ziehen.
2. Light-Butler in "Programme" doppelklicken. Beim ersten Mal sagt macOS, die App sei nicht geprueft (sie hat keine
   bezahlte Apple-Unterschrift): Systemeinstellungen -> Datenschutz & Sicherheit -> ganz unten "Dennoch oeffnen".
3. macOS fragt nach dem Mikrofon: erlauben, sonst hoert der Light-Butler keine Musik. Fragt die Firewall, zulassen.
4. Das Panel oeffnet sich im Browser (http://localhost:8080/, Handy/iPad im Heimnetz: http://<Name-des-Mac>:8080/).

Ein kleines Fenster zeigt den Zustand: "Panel oeffnen", "Beenden" (Licht aus). Fenster schliessen = laeuft weiter.
Beim Anmelden starten: Rechtsklick auf das Symbol im Dock -> Optionen -> Bei der Anmeldung oeffnen.
Einstellungen, Szenen, Shows und Geraete liegen in ~/Light-Butler, Meldungen in ~/Library/Logs/Light-Butler.
Ein neuer Light-Butler startet mit allen Ausgaben AUS (DMX, WLED, Nanoleaf): Geraete im Panel unter Einstellungen ->
Fixtures anlegen, dann die Ausgaben einschalten. Strobe, Laser und Nebel sind wie bei jeder neuen Anlage aus.
Aktualisieren: neue App auf "Programme" ziehen und ersetzen; Einstellungen und Shows bleiben.

"""


if __name__ == "__main__":
    sys.exit(main(sys.argv))
