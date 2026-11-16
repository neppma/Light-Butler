"""Einstellungen -> Software fuer andere Rechner: juengste Sicherung des Pi herunterladen (Wunsch 12.11.2026). Das Panel hat
keine Anmeldung, darum ohne die geheimen Dateien (Nanoleaf-Token, Schluessel des Show-Assistenten); die Kopie bleibt pruefbar."""
import io
import json
import os
import sys
import tempfile
import time
import zipfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
import backup                                # noqa: E402

tmp = tempfile.mkdtemp()
cfg = dict(backup.DEFAULTS, dir=tmp)
check(backup.download_copy(cfg) is None, "noch keine Sicherung: nichts")


def make(name, files):
    man = {"created": "x", "files": []}
    with zipfile.ZipFile(os.path.join(tmp, name), "w") as z:
        for arc, data in files.items():
            z.writestr(arc, data)
            man["files"].append({"name": arc, "size": len(data), "sha256": backup.sha256(data=data)})
        z.writestr("manifest.json", json.dumps(man))


make(backup.PREFIX + "2026-11-11_043444.zip", {"lichtshow/settings.json": b"{}"})
time.sleep(0.01)
make(backup.PREFIX + "2026-11-12_043448.zip", {"lichtshow/settings.json": b'{"a": 1}', "lichtshow/nanoleaf.json": b'{"token": "GEHEIM"}',
                                              "lichtshow/claude.json": b'{"key": "GEHEIM"}', "lichtshow/shows/x/show.json": b"{}"})
name, data = backup.download_copy(cfg)
z = zipfile.ZipFile(io.BytesIO(data))
names = set(z.namelist())
check(name.endswith("2026-11-12_043448.zip"), "die juengste Sicherung")
check("lichtshow/nanoleaf.json" not in names and "lichtshow/claude.json" not in names and b"GEHEIM" not in data,
      "ohne Nanoleaf-Token und Claude-Schluessel")
check({"lichtshow/settings.json", "lichtshow/shows/x/show.json", "OHNE_SCHLUESSEL.txt"} <= names, "alles andere drin, mit Hinweis")
p = os.path.join(tmp, "dl.zip")
open(p, "wb").write(data)
ok, msg = backup.verify(p)
check(ok, "Kopie besteht die Pruefung (--verify): " + msg)
check(zipfile.ZipFile(os.path.join(tmp, backup.PREFIX + "2026-11-12_043448.zip")).read("lichtshow/nanoleaf.json") == b'{"token": "GEHEIM"}',
      "Sicherung am Pi bleibt unveraendert")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check('path == "/download/backup"' in api and "backup.download_copy()" in api, "Route /download/backup")
check('href="/download/backup" download' in wp and 'data-tx="dl_backup"' in wp, "Einstellungen, ganz unten: Link zum Herunterladen")
finish("test_backup_download")
