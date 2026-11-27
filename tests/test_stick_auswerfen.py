"""Stick auswerfen aus dem Panel (Wunsch 10.11.2026): Sperre fuer Helfer und Bruecke, warten auf offene Dateien, diskutil eject,
blockierenden Prozess melden, nach dem Wiederanstecken weiterarbeiten."""
import os
import sys
import tempfile
import time
import types

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import stick_hold as sh                      # noqa: E402
import music_serve                           # noqa: E402
import folder_lib                            # noqa: E402

check(sh.volume_of("/Volumes/USB STICK/musik") == "/Volumes/USB STICK" and sh.volume_of("/Users/x/musik") == "", "Laufwerk des Musikordners")
check(not sh.held(), "ohne Sperre frei")
sh.hold("/Volumes/USB STICK")
check(sh.held() and sh.held("/Volumes/USB STICK/musik/a.mp3") and not sh.held("/Volumes/music/a.mp3"), "Sperre gilt nur fuer dieses Laufwerk")
loc = music_serve.Locator(["/Volumes/USB STICK/musik/a.mp3"], root="/Volumes/USB STICK/musik")
check(loc.locate("/Volumes/USB STICK/musik/a.mp3") is None, "gesperrt: Vorhoeren und Tags liefern nichts")
fl = folder_lib.FolderLib(base=os.path.join(tmp, "fl"))
check(not fl.due("/Volumes/USB STICK/musik", now=1e12), "gesperrt: Ordner-Liste liest nicht ein")
sh.release()
check(not sh.held() and fl.due("/Volumes/USB STICK/musik", now=1e12), "Sperre weg: alles wieder frei")

# haengengebliebene Sperre, wieder angesteckt
vol = os.path.join(tmp, "STICK")
os.makedirs(vol)
sh._write({"vol": vol, "t": time.time() - 700, "ejected": False})
check(sh.tick() and not sh.held(), "Auswerfen nie fertig geworden: Sperre nach 10 Minuten weg")
sh.hold(vol, ejected=True)
check(sh.tick() and not sh.held(), "ausgeworfen und wieder angesteckt: weiterarbeiten")

# lsof und diskutil (nachgestellt)
LSOF = "p123\nfcwd\nn/Users/x\nf5\nn/Volumes/USB STICK/musik/a.mp3\nf6\nn/Volumes/USB STICK2/x.mp3\n"
check(sh.open_files("/Volumes/USB STICK", [1], run=lambda *a, **k: types.SimpleNamespace(stdout=LSOF)) == ["/Volumes/USB STICK/musik/a.mp3"],
      "offene Dateien nur auf diesem Laufwerk (nicht USB STICK2)")


def fake(open_rounds, ok, ps="/Applications/Mixxx.app/Contents/MacOS/mixxx"):
    calls = {"lsof": 0, "eject": 0}

    def run(cmd, **kw):
        if cmd[0].endswith("lsof"):
            calls["lsof"] += 1
            return types.SimpleNamespace(stdout=f"n{vol}/musik/a.mp3\n" if calls["lsof"] <= open_rounds else "")
        if cmd[0].endswith("diskutil"):
            calls["eject"] += 1
            return types.SimpleNamespace(returncode=0 if ok else 1, stdout="Volume ejected" if ok else "",
                                         stderr="" if ok else "Unmount of disk4 failed: at least one volume could not be unmounted\nUnmount was dissented by PID 4711 (mixxx)")
        if cmd[0].endswith("ps"):
            return types.SimpleNamespace(stdout=ps + "\n")
        return types.SimpleNamespace(stdout="", returncode=0, stderr="")
    return run, calls


run, calls = fake(2, True)
ej = sh.Eject(run=run, sleep=lambda s: None, pids=lambda: [1])
ej._run(vol)
st = ej.status() if False else dict(ej.st)
check(calls["lsof"] == 3 and calls["eject"] == 1 and st["state"] == "ok", "wartet, bis keine Datei mehr offen ist, dann auswerfen")
v = sh.state()
check(v and v["ejected"] and sh.held(), "ausgeworfen: Sperre bleibt, bis er wieder da ist")
sh.release()

run, calls = fake(0, False)
ej = sh.Eject(run=run, sleep=lambda s: None, pids=lambda: [1])
ej._run(vol)
check(ej.st["state"] == "err" and "mixxx (PID 4711)" in ej.st["error"] and "Mixxx beenden" in ej.st["error"] and not sh.held(),
      "Mixxx blockiert: Meldung mit Hinweis, Sperre wieder weg: " + ej.st.get("error", ""))
try:
    sh.Eject().start("/Users/x/musik")
    check(False, "Musikordner nicht auf einem Laufwerk: abgelehnt")
except ValueError:
    check(True, "Musikordner nicht auf einem Laufwerk: abgelehnt")

# Anderes Laufwerk (Seite Spiegeln, 12.11.2026): ohne Sperre, Helfer und Bruecke arbeiten am Musik-Stick weiter
run, calls = fake(0, True)
ej = sh.Eject(run=run, sleep=lambda s: None, pids=lambda: [1])
ej._run("/Volumes/ERSATZ", False)
check(ej.st["state"] == "ok" and calls["eject"] == 1 and not sh.held(), "Ersatzstick ausgeworfen, keine Sperre")
run, calls = fake(0, False)
ej = sh.Eject(run=run, sleep=lambda s: None, pids=lambda: [1])
sh.hold(vol, by="spiegeln")
ej._run("/Volumes/ERSATZ", False)
check(ej.st["state"] == "err" and sh.mine("spiegeln"), "Fehler beim Ersatzstick: fremde Sperre bleibt")
sh.release()
for bad in ("/Users/x", "/Volumes/ERSATZ/musik", "/Volumes"):
    try:
        sh.Eject().start(vol + "/musik", vol=bad)
        check(False, "abgelehnt: " + bad)
    except ValueError:
        check(True, "nur ganze Laufwerke unter /Volumes: " + bad)
ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('start(loc.root, vol=vol or None)' in ms and 'dv["kind"] == "net"' in ms and 'mst.get("state") in ("plan", "run")' in ms,
      "Server: nur verbundene, keine Netzlaufwerke, nicht waehrend des Spiegelns")
mh = open(os.path.join(ROOT, "pi", "static", "sm", "mirror.html"), encoding="utf-8").read()
mjs = open(os.path.join(ROOT, "pi", "static", "sm", "mirror.js"), encoding="utf-8").read()
check('id="ejsrc" disabled' in mh and 'id="ejdst" disabled' in mh and "SM.ejectStick(music," in mjs and "b.disabled = !!why" in mjs,
      "Seite Spiegeln: Knopf je Seite, fester Platz, ausgegraut")

# Musikordner auf einen anderen Stick umgestellt: Sperre des ausgeworfenen weg (Fehlerbericht 12.11.2026)
sh.hold("/Volumes/ALT", ejected=True)
check(not sh.moved("/Volumes/ALT/musik") and sh.held(), "gleicher Stick: Sperre bleibt")
check(not sh.moved("/Volumes/GIBTSNICHT/musik") and sh.held(), "neuer Stick nicht angesteckt: Sperre bleibt")
_isdir = os.path.isdir
os.path.isdir = lambda p: p == "/Volumes/NEU" or _isdir(p)
check(sh.moved("/Volumes/NEU/musik") and not sh.held(), "anderer angesteckter Stick: Sperre weg")
sh.hold("/Volumes/ALT", by="spiegeln")
check(not sh.moved("/Volumes/NEU/musik") and sh.held(), "laufende Sperre (nicht ausgeworfen) bleibt")
os.path.isdir = _isdir
sh.release()
check("stick_hold.moved(new)" in open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read(),
      "Musikordner vom Pi uebernehmen hebt sie auf")

# Panel
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
core = open(os.path.join(ROOT, "pi", "static", "sm", "core.js"), encoding="utf-8").read()
sys.path.insert(0, os.path.join(ROOT, "pi"))
import webpanel                              # noqa: E402
pg = webpanel.make_page()
check("SM.ejectStick = " in core and "SM.ejectStick(music" in mj and 'id="beject"' in open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read(),
      "Musik-Datenbank: Knopf Stick auswerfen")
check('id="meject"' in pg and "async function ejectStick()" in pg and pg.find('id="mrootrow"') < pg.find('id="meject"') < pg.find('id="mexclrow"'),
      "Einstellungen: Knopf unter dem Musikordner")
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("def stick_pause(self)" in src and "stick_hold.tick(now)" in src, "Bruecke und Helfer halten Analyse und Messungen an")
for sh_ in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("stick_hold.py" in open(os.path.join(ROOT, sh_), encoding="utf-8").read(), sh_ + " installiert stick_hold.py")
dep = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
check('for _try in 1 2 3' in dep and 'pgrep -f "helper.py"' in dep, "Einspielen prueft, ob der Helfer wirklich wieder laeuft (Fehlerbericht 11.11.2026)")
check('TESTLOG="${TMPDIR:-/tmp}/lightbutler-tests.log"' in dep and "/FEHLER|Traceback/" in dep, "Einspielen zeigt, welcher Test fehlschlug (Fehlerbericht 11.11.2026)")
ms_src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('st["root"], st["root_ok"] = root, bool(root) and os.path.isdir(root)' in ms_src and "SM.sourceCheck = async" in core
      and "Musik-Datenquelle nicht erreichbar" in core and "/^\\/musik/.test(location.pathname)" in core and "Mac nicht erreichbar" not in core
      and "SM.hostName = async" in core and "(d.texts || {}).music_host" in core and "Array.isArray(v)" in core,
      "Hinweis oben auf allen Musik-Seiten, wenn Musik-Rechner oder Musikordner (Stick) fehlt; Name aus der Uebersetzungstabelle (Wunsch 12.11.2026)")
import texts as _tx
check(_tx.HEADS["music_host"][0] == "Musik-Rechner" and any(k == "music_host" for k, *_ in _tx.catalog()) and "music_host" in webpanel.NAV_KEYS, "Begriff Musik-Rechner, in der Uebersetzungstabelle aenderbar, kommt mit /api/nav")
finish("test_stick_auswerfen")
