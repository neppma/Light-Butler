#!/usr/bin/env python3
"""Alle Tests ohne Hardware, wie tests/run_all.sh, aber ohne Bash (Windows, auch am Mac und Pi lauffaehig).

Aufruf im Projektordner:  python tests/run_all.py            alle Tests
                          python tests/run_all.py -k stems   nur Tests mit "stems" im Namen
                          python tests/run_all.py -q         nur Fehler und Zusammenfassung zeigen
Endet mit "ALLES IN ORDNUNG" oder "FEHLER, siehe oben" und Rueckgabewert 1.
"""
import argparse
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMEOUT_S = 600

# Nur am Mac sinnvoll: pruefen Bash-Skripte (deploy.sh, Installer, Mixxx-App-Skripte), rsync/mount oder biegen HOME um.
# Unter Windows werden diese Tests uebersprungen und genannt. Der Musik-Teil des Helfers laeuft seit 15.11.2026 auch unter
# Windows; seine Tests (Ordner, Import, CD-Assistent, Doppelte, Export ...) laufen deshalb hier mit.
MAC_ONLY = {
    "test_dateien_pruefen.py": "mixxx_umbenennen.sh (Bash, Mixxx-App am Mac)",
    "test_deploy.py": "deploy.sh (Bash, rsync, ssh)",
    "test_helfer_liedliste.py": "mac/helper (biegt HOME um; unter Windows gilt USERPROFILE, der Test schriebe sonst in den echten Benutzerordner)",
    "test_helfer.py": "mac/helper (install_helper.sh)",
    "test_mixxx_sicherung.py": "install_launcher.sh (Bash, Mixxx-App am Mac)",
    "test_mixxx_uebertragen.py": "install_launcher.sh (Bash, Mixxx-App am Mac)",
    "test_pakete.py": "install_mac.sh (Bash)",
    "test_pi_paket.py": "pi/install_pi.sh (Bash, Paket fuer einen neuen Pi)",
    "test_poweroff.py": "install_poweroff.sh (Bash, Pi)",
    "test_spiegeln_frei.py": "mac/mixxx_bridge/nas_mirror.py (rsync, mount)",
    "test_sterne_setzen.py": "mac/mixxx_bridge/mixxx_sterne.sh (Bash)",
    "test_umbenennen.py": "pi/rename_host.sh, deploy.sh (Bash)",
}


def run(cmd, cwd, quiet):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=TIMEOUT_S)
        out, code = r.stdout.decode("utf-8", "replace").replace("\r\n", "\n"), r.returncode
    except subprocess.TimeoutExpired as e:
        out, code = (e.stdout or b"").decode("utf-8", "replace") + "\nZEITLIMIT %d s" % TIMEOUT_S, -1
    if not quiet or code:
        sys.stdout.write(out if out.endswith("\n") or not out else out + "\n")
    return code, time.time() - t0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Alle Tests ohne Hardware")
    ap.add_argument("-k", help="nur Tests, deren Dateiname diesen Text enthaelt")
    ap.add_argument("-q", action="store_true", help="Ausgabe nur bei Fehlern")
    a = ap.parse_args(argv)
    py = sys.executable
    failed = []
    if not a.k:
        print("== Dateipruefung (YAML, Adressen, Kanaele)", flush=True)
        code, _ = run([py, "phase2_test.py", "--check"], os.path.join(ROOT, "pi"), a.q)
        if code:
            failed.append("phase2_test.py --check")
    tests = sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
    if a.k:
        tests = [t for t in tests if a.k in os.path.basename(t)]
    skipped = []
    for t in tests:
        name = "tests/" + os.path.basename(t)
        if sys.platform == "win32" and os.path.basename(t) in MAC_ONLY:
            skipped.append(name)
            print("\n== %s  (uebersprungen: nur Mac, %s)" % (name, MAC_ONLY[os.path.basename(t)]), flush=True)
            continue
        print("\n== %s" % name, flush=True)
        code, secs = run([py, name], ROOT, a.q)
        if code:
            failed.append(name)
            print("-- FEHLGESCHLAGEN (%d) nach %.0f s" % (code, secs), flush=True)
    print()
    if skipped:
        print("%d Tests nur fuer den Mac uebersprungen: %s" % (len(skipped), ", ".join(s[6:] for s in skipped)))
    if failed:
        print("%d von %d fehlgeschlagen:" % (len(failed), len(tests) + (0 if a.k else 1)))
        for f in failed:
            print("  " + f)
        print("FEHLER, siehe oben")
        return 1
    print("ALLES IN ORDNUNG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
