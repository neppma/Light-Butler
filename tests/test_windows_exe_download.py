"""Light-Butler.exe als Download (Wunsch von Markus, 15.11.2026): am Windows-PC gebaut, am Mac nach windows/build/ gelegt,
deploy.sh push kopiert sie nach pakete/windows am Pi; Download in den Einstellungen, im Paket-Stand und auf dem Stick."""
import io
import os
import sys
import tempfile
import zipfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
import pakete  # noqa: E402

tmp = tempfile.mkdtemp()
a, b = os.path.join(tmp, "a.zip"), os.path.join(tmp, "b.zip")
check(pakete.exe_zip_path((a, b)) is None, "noch keine EXE: None")
open(a, "wb").write(b"kein zip")
check(pakete.exe_zip_path((a, b)) is None, "nur ein echtes ZIP zaehlt")
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("Light-Butler/Light-Butler.exe", b"MZ")
open(b, "wb").write(buf.getvalue())
check(pakete.exe_zip_path((a, b)) == b, "abgelegtes ZIP gefunden")
check(pakete.EXE_NAME == "light-butler-windows-exe.zip" and pakete.EXE_FILES[0].endswith(os.path.join("pakete", "windows", pakete.EXE_NAME)), "Ort am Pi")
src = open(os.path.join(ROOT, "pi", "pakete.py"), encoding="utf-8").read()
check('add(ep, "exe/" + EXE_NAME)' in src, "neue EXE = neuer Paket-Stand (Stick erneuert sie)")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('"/download/light-butler-windows-exe.zip"' in api and "pakete.exe_zip_path()" in api, "Download am Pi, ohne Datei ein Hinweis")
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check('href="/download/light-butler-windows-exe.zip"' in wp and "dl_win_exe" in open(os.path.join(ROOT, "pi", "texts.py"), encoding="utf-8").read(), "Link in den Einstellungen")
dp = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
check('EXE_ZIP="${S2L_EXE_ZIP:-windows/build/light-butler-windows-exe.zip}"' in dp and 'rsync -a "$EXE_ZIP" "$PI:$DEST/pakete/windows/"' in dp, "deploy.sh push kopiert sie mit")
pc = open(os.path.join(ROOT, "mac", "mixxx_bridge", "programs_copy.py"), encoding="utf-8").read()
check('("/download/light-butler-windows-exe.zip", "light-butler-windows-exe.zip")' in pc, "Stick-Notfallordner (wenn vorhanden)")
finish("test_windows_exe_download")
