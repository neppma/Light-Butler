"""Beschaedigte Dateien (Wunsch von Markus, 14.11.2026): der Musik-Rechner prueft jede Datei mit afinfo (Abspielmodul von
macOS, wie Mixxx am Mac), nur neue oder geaenderte; reparieren nur MP3, nur auf Klick, ffmpeg ohne Neukodieren, das Original
erst in den Papierkorb, wenn macOS die neue Fassung lesen kann und die Laenge passt."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types

from _common import ROOT, check, finish

tmp = os.path.realpath(tempfile.mkdtemp())
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import damaged as dm  # noqa: E402

real_platform = dm.PLATFORM
dm.PLATFORM = "darwin"                         # dieser Teil stellt afinfo (Mac) nach; der Windows-Weg steht am Ende

music = os.path.join(tmp, "musik")
os.makedirs(music)
for n in ("gut.mp3", "kaputt.mp3", "kaputt.m4a", "zukurz.mp3"):
    open(os.path.join(music, n), "wb").write(b"x" * 4000)
LIB = [{"path": os.path.join(music, n)} for n in ("gut.mp3", "kaputt.mp3", "kaputt.m4a", "zukurz.mp3")] + [{"path": os.path.join(music, "weg.mp3")}]
calls, trashed = [], []
BAD = {"kaputt.mp3", "kaputt.m4a", "zukurz.mp3"}


def run(cmd, **kw):
    calls.append(cmd)
    f = cmd[-1]
    b = os.path.basename(f)
    if cmd[0] == "/usr/bin/afinfo":
        if b in BAD:
            return types.SimpleNamespace(returncode=1, stdout="Fail: AudioFileOpenURL failed", stderr="")
        d = "40.0" if "zukurz" in b else "65.02"
        return types.SimpleNamespace(returncode=0, stdout="estimated duration: %s sec" % d, stderr="")
    if cmd[0].endswith("ffprobe"):
        return types.SimpleNamespace(returncode=0, stdout="65.03\n", stderr="")
    if cmd[0].endswith("ffmpeg"):
        shutil.copyfile(cmd[cmd.index("-i") + 1], f)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    raise AssertionError(cmd)


def trash(f):
    trashed.append(os.path.basename(f))
    os.rename(f, f + ".papierkorb")


D = dm.Damaged(lambda: LIB, lambda p: p, run=run, ffmpeg=lambda: "/x/ffmpeg", trash=trash, base=os.path.join(tmp, "daten", "defekt"), gap_s=0)
D.scan_t = 0
D.scan_once()
g = D.get()
check(sorted(os.path.basename(x["path"]) for x in g["items"]) == ["kaputt.m4a", "kaputt.mp3", "zukurz.mp3"] and g["n"] == 3, "gefunden: was macOS nicht oeffnen kann")
check([x["mp3"] for x in g["items"]] == [False, True, True], "nur MP3 reparierbar")
n0 = len(calls)
D.scan_once()
check(len(calls) == n0, "zweiter Durchgang: nichts Unveraendertes noch einmal")
check(dm.Damaged(lambda: LIB, lambda p: p, run=run, base=os.path.join(tmp, "daten", "defekt")).get()["n"] == 3, "nach Neustart gemerkt")

# Reparieren: die Hilfsdatei liest macOS (nicht in BAD), Laenge passt -> Original in den Papierkorb, neue an seinen Platz
k = os.path.join(music, "kaputt.mp3")
check(D.repair_file(k) == "ok" and trashed == ["kaputt.mp3"] and os.path.isfile(k), "repariert, Original im Papierkorb, Name gleich")
check(not [f for f in os.listdir(music) if "lb-tmp" in f], "keine Hilfsdatei bleibt liegen")
ff = [c for c in calls if c[0].endswith("ffmpeg")][-1]
check(ff[ff.index("-c") + 1] == "copy" and "-map" in ff, "ffmpeg ohne Neukodieren, alle Teile (Cover)")
check(D.get()["n"] == 2, "repariert: nicht mehr auf der Liste")
z = os.path.join(music, "zukurz.mp3")
r = D.repair_file(z)
check(r.startswith("Länge passt nicht") and "zukurz.mp3" not in trashed and os.path.isfile(z), "Laenge passt nicht: Original bleibt: " + r)
check(D.repair_file(os.path.join(music, "kaputt.m4a")).startswith("nur MP3") and D.repair_file(os.path.join(music, "gut.mp3")).startswith("nicht als"), "nur bekannte, nur MP3")
D2 = dm.Damaged(lambda: LIB, lambda p: p, run=run, ffmpeg=lambda: "", trash=trash, base=os.path.join(tmp, "daten", "defekt"))
check(D2.repair_file(z).startswith("ffmpeg fehlt"), "ohne ffmpeg: Hinweis")
D._mark(z, r)
D.repair([z])
for _ in range(100):
    if D.job["state"] == "done":
        break
    time.sleep(0.02)
check(D.job["done"] == 1 and D.job["ok"] == 0 and D.job["err"].startswith("Länge"), "Auftrag im Hintergrund mit Stand")
check(D.trash_file(z)["ok"] and "zukurz.mp3" in trashed and D.get()["n"] == 1, "nicht reparierbare in den Papierkorb")

# Verdrahtung
srv = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('u.path == "/defekt"' in srv and 'path == "/defekt"' in srv and "dm.repair(" in srv and "dm.trash_file(" in srv, "music_serve /defekt")
br = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("from damaged import Damaged" in br and "ms.damaged = fw.damaged" in br, "Bruecke und Helfer (setup_library)")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("damaged.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert damaged.py")
SMD = os.path.join(ROOT, "pi", "static", "sm")
care = open(os.path.join(SMD, "care.js"), encoding="utf-8").read()
check("href: '/musik/defekt'" in care and "mac('/defekt?count=1')" in care, "Datenpflege-Schritt mit Zahl")
check('"/musik/defekt"' in open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read(), "Seite am Pi")
check(subprocess.run(["node", "--check", os.path.join(SMD, "defekt.js")]).returncode == 0, "defekt.js ohne Syntaxfehler")
# ---- Windows (15.11.2026): kein afinfo; ffmpeg dekodiert probehalber, ohne ffmpeg wird nichts als defekt gemerkt ----------
dm.PLATFORM = real_platform
seen = []


def wrun(cmd, **kw):
    seen.append(cmd)
    if "ffprobe" in cmd[0]:
        return types.SimpleNamespace(returncode=0, stdout="181.5\n", stderr="")
    return types.SimpleNamespace(returncode=1 if "kaputt" in cmd[cmd.index("-i") + 1] else 0, stdout="", stderr="")


ok, dur = dm.win_check(os.path.join(music, "gut.mp3"), wrun, which=lambda n: "C:/ff/ffmpeg.exe")
check(ok is True and dur == 181.5 and seen[0][:3] == ["C:/ff/ffmpeg.exe", "-v", "error"] and "-t" in seen[0] and "null" in seen[0],
      "Windows: ffmpeg dekodiert den Anfang, Laenge ueber ffprobe")
check(dm.win_check(os.path.join(music, "kaputt.mp3"), wrun, which=lambda n: "ff")[0] is False, "Windows: unlesbar = defekt")
check(dm.win_check("x.mp3", wrun, which=lambda n: None) == (None, None), "Windows ohne ffmpeg: nicht pruefbar (None)")
check(dm.afinfo("x.mp3", wrun, platform="win32") is not None and dm.afinfo.__defaults__ is not None, "afinfo nimmt unter Windows win_check")
old_which = dm.shutil.which
dm.shutil.which = lambda n: None
dm.PLATFORM = "win32"
try:
    D3 = dm.Damaged(lambda: LIB, lambda p: p, run=wrun, base=os.path.join(tmp, "daten", "defekt3"), gap_s=0)
    D3.scan_once()
    check(D3.get()["n"] == 0, "Windows ohne ffmpeg: keine Datei als defekt gemerkt")
finally:
    dm.shutil.which, dm.PLATFORM = old_which, real_platform
finish("test_beschaedigte_dateien")
