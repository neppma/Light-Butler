"""Download "Pi: frische Installation" (Wunsch 12.11.2026): ein neuer Raspberry Pi (Freund, Ersatzgeraet) bekommt alle Programme
ohne persoenliche Daten, das Installationsskript richtet alles ein, ohne Vorhandenes zu ueberschreiben, und startet mit allen
Ausgaben aus (zwei Light-Butler duerfen nie gleichzeitig senden)."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from _common import ROOT, check, finish

PI = os.path.join(ROOT, "pi")
sys.path.insert(0, PI)
import backup                                # noqa: E402
import dmx                                   # noqa: E402
import pakete                                # noqa: E402

tmp = tempfile.mkdtemp()
# Programmordner wie am Pi, mit Zustandsdateien, die nie ins Paket duerfen
base = os.path.join(tmp, "lichtshow")
shutil.copytree(PI, base, ignore=shutil.ignore_patterns("__pycache__", "shows", "aufnahmen", "*.json"))
for n, data in {"settings.json": '{"ola_out": 1}', "nanoleaf.json": '{"token": "GEHEIM"}', "claude.json": '{"key": "GEHEIM"}',
                "raum.json": "{}", "backup.conf": "{}"}.items():
    open(os.path.join(base, n), "w").write(data)
for n in ("HANDBUCH.md", "MANUAL_EN.md"):                # am Pi liegen die Handbuecher neben den Programmen
    shutil.copy(os.path.join(ROOT, "docs", n), os.path.join(base, n))
open(os.path.join(base, "show.conf"), "w").write("SHOW_ARGS=--device USB --strobe --web 8080\n")
os.makedirs(os.path.join(base, "shows", "Titanium"))
open(os.path.join(base, "shows", "Titanium", "show.json"), "w").write("{}")
os.makedirs(os.path.join(base, "pakete", "mac"))
open(os.path.join(base, "pakete", "mac", "install_mac.sh"), "w").write("#!/bin/bash\n")

data = pakete.pi_zip(base)
z = zipfile.ZipFile(io.BytesIO(data))
names = z.namelist()
L = "Light-Butler-Pi/lichtshow/"
check("Light-Butler-Pi/install_pi.sh" in names and "Light-Butler-Pi/LIESMICH.txt" in names and L + "show.py" in names
      and L + "static/sm/core.js" in names and L + "HANDBUCH.md" in names and L + "pakete/mac/install_mac.sh" in names,
      "Programme, Seiten, Handbuch und Mac-Paket drin")
check(not [n for n in names if n.endswith(".json")] and b"GEHEIM" not in data and not [n for n in names if "/shows/" in n],
      "keine Zustandsdateien, keine Schluessel, keine Shows")
_args = [x for x in z.read(L + "show.conf").decode().splitlines() if x.startswith("SHOW_ARGS=")]
check(len(_args) == 1 and "--strobe" not in _args[0] and "--device" not in _args[0], "show.conf neutral, ohne Strobe-Erlaubnis: " + str(_args))
fx = z.read(L + "fixtures.yaml").decode("utf-8")
check("192.168." not in fx and L + "homematic.yaml" not in names, "frische Installation: keine eigenen Adressen, kein HomeMatic")
open(os.path.join(tmp, "fx.yaml"), "w").write(fx)
rig = dmx.Rig(os.path.join(tmp, "fx.yaml"))
check(len(rig.fixtures) == 0 and "docooler_90w" in (rig.cfg.get("types") or {}), "neutrale Geraetedatei laedt: keine Geraete, alle Typen")
own = zipfile.ZipFile(io.BytesIO(pakete.pi_zip(base, own=True)))
check(own.read(L + "fixtures.yaml") == open(os.path.join(PI, "fixtures.yaml"), "rb").read() and (L + "homematic.yaml" in own.namelist()) == os.path.isfile(os.path.join(PI, "homematic.yaml"))
      and not [n for n in own.namelist() if n.endswith(".json")], "Ersatzgeraet: eigene Geraete, aber auch keine Zustandsdateien")
check(own.getinfo("Light-Butler-Pi/install_pi.sh").external_attr >> 16 & 0o111, "Skript ausfuehrbar")

# Installationsskript im Testmodus (ohne apt, venv und systemd)
if shutil.which("rsync"):
    home = os.path.join(tmp, "home")
    os.makedirs(home)
    z.extractall(home)
    units = os.path.join(tmp, "units")
    os.makedirs(units)
    env = dict(os.environ, S2L_NO_SYSTEM="1", S2L_HOME=home, S2L_SUDO="", S2L_UNIT_DIR=units)
    r = subprocess.run(["bash", os.path.join(home, "Light-Butler-Pi", "install_pi.sh")], env=env, capture_output=True, text=True)
    dest = os.path.join(home, "lichtshow")
    check(r.returncode == 0 and os.path.isfile(os.path.join(dest, "show.py")), "Installation laeuft durch: " + r.stderr[-300:])
    st = json.load(open(os.path.join(dest, "settings.json")))
    check(st == {"ola_out": 0.0, "wled_out": 0.0, "nano_out": 0.0}, "erster Start: alle Ausgaben aus")
    unit = open(os.path.join(units, "lichtshow.service")).read()
    check(dest in unit and os.path.join(home, "venv") in unit and "/home/admin" not in unit, "Dienst mit Benutzer und Ordnern dieses Pi")
    # zweiter Lauf = aktualisieren: Eigenes bleibt
    open(os.path.join(dest, "settings.json"), "w").write('{"ola_out": 1.0}')
    open(os.path.join(dest, "fixtures.yaml"), "a").write("# eigene Aenderung\n")
    open(os.path.join(dest, "show.conf"), "w").write("SHOW_ARGS=--web 8080 --device USB\n")
    open(os.path.join(dest, "scenes.json"), "w").write("{}")
    r = subprocess.run(["bash", os.path.join(home, "Light-Butler-Pi", "install_pi.sh")], env=env, capture_output=True, text=True)
    check(r.returncode == 0 and open(os.path.join(dest, "settings.json")).read() == '{"ola_out": 1.0}'
          and open(os.path.join(dest, "fixtures.yaml")).read().endswith("# eigene Aenderung\n")
          and "--device USB" in open(os.path.join(dest, "show.conf")).read() and os.path.isfile(os.path.join(dest, "scenes.json")),
          "noch einmal ausfuehren: Einstellungen, Geraete, Startoptionen und Szenen bleiben")
else:
    print("  (rsync fehlt: Installationsskript nicht ausprobiert)")

# Ersatzgeraet: Sicherung einspielen, Ausgaben bleiben aus
bk = os.path.join(tmp, "bk")
os.makedirs(bk)
open(os.path.join(bk, "settings.json"), "w").write('{"ola_out": 1.0, "beat_pulse": 1.0}')
backup.outputs_off(bk)
check(json.load(open(os.path.join(bk, "settings.json"))) == {"ola_out": 0.0, "beat_pulse": 1.0, "wled_out": 0.0, "nano_out": 0.0},
      "--ausgaben-aus: Ausgaben aus, andere Einstellungen bleiben")
src = open(os.path.join(PI, "backup.py"), encoding="utf-8").read()
check('"--ausgaben-aus"' in src and "off=a.ausgaben_aus" in src, "Wiederherstellen mit --ausgaben-aus")
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
wp = open(os.path.join(PI, "webpanel.py"), encoding="utf-8").read()
check('"/download/light-butler-pi.zip", "/download/light-butler-pi-ersatz.zip"' in api and "pakete.pi_zip(own=" in api, "Routen fuer beide Pakete")
check('href="/download/light-butler-pi.zip" download' in wp and 'href="/download/light-butler-pi-ersatz.zip" download' in wp,
      "Einstellungen, ganz unten: beide Links")
finish("test_pi_paket")
