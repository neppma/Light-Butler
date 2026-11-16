"""Sicherung der Mixxx-Datenbank (Wunsch von Markus, 08.11.2026): das Startskript der App "Light-Butler Mixxx" kopiert sie bei jedem
Start, solange Mixxx zu ist; die letzten 5 bleiben. Die Datenpflege zeigt das Datum."""
import os
import re
import subprocess
import sys
import tempfile
import time

from _common import PI, ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import music_serve as ms  # noqa: E402

inst = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
m = re.search(r'(if \[ -s "\$SRC" \]; then\n  mkdir -p "\$BASE/mixxx-sicherung".*?\nfi\n)', inst, re.S)
check(m is not None, "Sicherungsteil im Startskript gefunden")
check(inst.index('mkdir -p "$BASE/mixxx-sicherung"') < inst.index("mixxx_umbenennen.sh\" \"$SRC\"") < inst.index('"$MIXXX_BIN" --controller-debug'),
      "gesichert vor dem Umbenennen und bevor Mixxx startet")
tmp = tempfile.mkdtemp(prefix="s2l_mxbak_")
src = os.path.join(tmp, "mixxxdb.sqlite")
open(src, "wb").write(b"SQLite format 3\0" + b"x" * 100)
script = 'BASE="%s"\nSRC="%s"\n%s' % (tmp, src, m.group(1))
for i in range(7):
    subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    time.sleep(1.05)                                   # Dateiname mit Sekunden
files = sorted(os.listdir(os.path.join(tmp, "mixxx-sicherung")))
check(len(files) == 5 and all(f.startswith("mixxxdb-") for f in files), f"bei jedem Start eine Kopie, die letzten 5 bleiben ({len(files)})")
check(open(os.path.join(tmp, "mixxx-sicherung", files[-1]), "rb").read() == open(src, "rb").read(), "Kopie gleich dem Original")
r = subprocess.run(["bash", "-c", 'BASE="%s"\nSRC="%s/fehlt.sqlite"\n%s' % (tmp, tmp, m.group(1))], capture_output=True, text=True)
check(r.returncode == 0 and len(os.listdir(os.path.join(tmp, "mixxx-sicherung"))) == 5, "ohne Datenbank: nichts, kein Fehler")
b = ms.mixxx_backups(tmp)
check(b["n"] == 5 and b["t"] > time.time() - 60, "Mac meldet Zahl und Zeit der juengsten Sicherung")
check(ms.mixxx_backups(os.path.join(tmp, "leer")) == {"n": 0, "t": 0}, "noch keine Sicherung: 0")
bak = open(os.path.join(ROOT, "mac", "mixxx_bridge", "backup_mac.py"), encoding="utf-8").read()
check('"mixxxdb.sqlite*"' in bak and not re.match(r"mixxxdb\.sqlite", "mixxxdb-20261108-120000.sqlite"),
      "die woechentliche Mac-Sicherung nimmt die Kopien mit (nur die Arbeitskopie mixxxdb.sqlite bleibt draussen)")
care = open(os.path.join(PI, "static", "sm", "care.js"), encoding="utf-8").read()
check("mac('/mixxxsicherung')" in care and "automatisch gesichert" in care, "Datenpflege zeigt das Datum der letzten Sicherung")
# Sicherung des Sticks aus dem Protokoll von nas-sync.sh (Wunsch 08.11.2026)
lg = os.path.join(tmp, "nas-sync.log")
open(lg, "w", encoding="utf-8").write("""2026-11-01 10:00:00 === TESTLAUF (es wird nichts veraendert) ===
2026-11-01 10:00:01 --- Job 6/8 [copy] /Volumes/USB STICK/musik -> /Volumes/SanDisk 4T/Backup USB STICK 128GB/musik
2026-11-01 10:05:00 OK: Job 6 abgeschlossen.
2026-11-01 10:05:01 === Fertig ohne Fehler ===
2026-11-07 20:00:00 --- Job 6/8 [copy] /Volumes/USB STICK/musik -> /Volumes/SanDisk 4T/Backup USB STICK 128GB/musik
>f+++++++++ 123 U-MUSIK/a.mp3
2026-11-07 21:30:00 OK: Job 6 abgeschlossen.
2026-11-07 21:30:01 --- Job 7/8 [copy] smb://x/backups -> /tmp/y
2026-11-07 21:31:00 OK: Job 7 abgeschlossen.
2026-11-08 17:31:40 --- Job 6/8 [copy] /Volumes/USB STICK/musik -> /Volumes/SanDisk 4T/Backup USB STICK 128GB/musik
2026-11-08 17:40:00 FEHLER: rsync Exit-Code 20 bei Job 6.
""")
sb = ms.stick_backup("/Volumes/USB STICK/musik/", lg)
check(time.strftime("%Y-%m-%d %H:%M", time.localtime(sb["t"])) == "2026-11-07 21:30" and sb["ziel"].endswith("Backup USB STICK 128GB/musik"),
      "letzte erfolgreiche Stick-Sicherung aus dem Protokoll (Testlauf und abgebrochener Lauf zaehlen nicht)")
check(ms.stick_backup("/Volumes/Anders", lg)["t"] == 0 and ms.stick_backup("/Volumes/USB STICK/musik", os.path.join(tmp, "fehlt.log"))["t"] == 0,
      "anderer Ordner oder kein Protokoll: 0")
check("auto: () => V.stick" in care and "älter als 7 Tage" in care, "Datenpflege hakt die Sicherung von selbst ab (7 Tage)")
finish("test_mixxx_sicherung")
