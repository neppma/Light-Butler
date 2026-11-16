"""Mac-App Light-Butler.app (16.11.2026, mac/app/light_butler_mac.py): Programme aus der App nach ~/Light-Butler kopieren,
ohne was der Anlage gehoert; Neustart aus dem Panel; Bau mit PyInstaller und DMG bei GitHub. Ohne PyInstaller getestet."""
import os
import shutil
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "app"))
import light_butler_mac as lbm  # noqa: E402

src = tempfile.mkdtemp(prefix="lb_app_src_")
dest = tempfile.mkdtemp(prefix="lb_app_home_")
try:
    for rel, txt in (("show.py", "neu"), ("show.conf", "SHOW_ARGS=--web 8080\n"), ("fixtures.yaml", "neutral"),
                     ("static/sm/core.js", "js"), ("__pycache__/x.pyc", "x"), ("shows/demo/show.json", "{}")):
        p = os.path.join(src, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(txt)
    n = lbm.sync(src, dest)
    check(n == 4 and os.path.isfile(os.path.join(dest, "static", "sm", "core.js")) and open(os.path.join(dest, "fixtures.yaml")).read() == "neutral",
          "erster Start: Programme, Startoptionen und Geraete angelegt (%d)" % n)
    check(not os.path.exists(os.path.join(dest, "__pycache__")) and not os.path.exists(os.path.join(dest, "shows")), "ohne __pycache__ und shows/")
    check(lbm.sync(src, dest) == 0, "zweiter Start ohne Update: nichts kopiert")
    open(os.path.join(dest, "fixtures.yaml"), "w").write("meine Geraete")
    open(os.path.join(dest, "show.conf"), "w").write("SHOW_ARGS=--web 9000\n")
    open(os.path.join(dest, "settings.json"), "w").write('{"ola_out": 1}')
    open(os.path.join(src, "show.py"), "w").write("neuer als neu")
    open(os.path.join(src, "settings.json"), "w").write("{}")
    os.utime(os.path.join(src, "show.py"), (2e9, 2e9))
    lbm.sync(src, dest)
    check(open(os.path.join(dest, "show.py")).read() == "neuer als neu", "Update: Programme ersetzt")
    check(open(os.path.join(dest, "fixtures.yaml")).read() == "meine Geraete" and "9000" in open(os.path.join(dest, "show.conf")).read()
          and open(os.path.join(dest, "settings.json")).read() == '{"ola_out": 1}', "Update: Geraete, Startoptionen und Einstellungen bleiben")
finally:
    shutil.rmtree(src, ignore_errors=True)
    shutil.rmtree(dest, ignore_errors=True)

home = tempfile.mkdtemp(prefix="lb_app_home_")
os.environ["LB_HOME"] = home
try:
    check(lbm.home_dir() == home, "LB_HOME fuer Tests, sonst ~/Light-Butler")
    os.makedirs(os.path.join(home, "lichtshow"))
    open(os.path.join(home, "lichtshow", "show.py"), "w").write("# Attrappe\n")
    open(os.path.join(home, "lichtshow", "settings.json"), "w").write("{}")

    def run_restart(path, run_name):
        raise SystemExit(lbm.lbe.RESTART_CODE)
    cwd = os.getcwd()
    try:
        check(lbm.run_show(["--dry-run"], run=run_restart) == lbm.lbe.RESTART_CODE, "Neustart aus dem Panel: Code 3 an das Fenster")
        check(lbm.run_show([], run=lambda p, run_name: None) == 0, "normales Ende: Code 0")
    finally:
        os.chdir(cwd)
finally:
    os.environ.pop("LB_HOME", None)
    os.environ.pop("LB_RESTART_EXIT", None)
    shutil.rmtree(home, ignore_errors=True)
    del os.environ["LB_HELPER_STARTED"]
check(os.path.expanduser("~") in lbm.home_dir() and lbm.home_dir().endswith("Light-Butler"), "Standard ~/Light-Butler (wie install_lightbutler_mac.sh)")

b = open(os.path.join(ROOT, "mac", "app", "build_app.py"), encoding="utf-8").read()
check('"--windowed"' in b and "NSMicrophoneUsageDescription" in b and "mac_full_zip" in b and "codesign" in b and "hdiutil" in b
      and "light-butler.icns" in b, "Bau: App mit Fenster, Mikrofon-Text, neutrale Programme, Ad-hoc-Unterschrift, DMG, Symbol")
check(os.path.getsize(os.path.join(ROOT, "mac", "app", "light-butler.icns")) > 10000, "Mac-Symbol vorhanden")
src_app = open(os.path.join(ROOT, "mac", "app", "light_butler_mac.py"), encoding="utf-8").read()
check("tk::mac::Quit" in src_app and "SIGTERM" in src_app, "Beenden im Dock: Licht-Prozess bekommt SIGTERM (Blackout)")
wf = open(os.path.join(ROOT, ".github", "workflows", "mac-dmg.yml"), encoding="utf-8").read()
check("mac/app/build_app.py" in wf and "gh release upload" in wf and "Light-Butler.dmg" in wf and "types: [published]" in wf,
      "GitHub baut die DMG und haengt sie an das Release")
check("elif code == 0:" in src_app and "self.quit()" in src_app.split("elif code == 0:")[1][:200], "Beenden aus dem Panel: ganze App beendet")
finish("test_mac_app")
