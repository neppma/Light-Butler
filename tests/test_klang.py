"""Klang pruefen beim Import (Wunsch 11.11.2026): gleiche Musik unter anderem Namen und mit anderer Bitrate erkennen
("01 - Future Trance 13 - Techno.mp3", 128 kbit/s = "Aquagen - Partyalarm (Radio Mix).mp3", 320 kbit/s). Chromaprint (fpcalc);
ohne fpcalc hier nachgestellt."""
import json
import os
import random
import subprocess
import sys
import tempfile
import time

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import klang_fp as kf                       # noqa: E402
import import_assist as ia                  # noqa: E402

rnd = random.Random(7)
a = [rnd.getrandbits(32) for _ in range(700)]
b = [x ^ (1 << rnd.randrange(32)) if rnd.random() < 0.5 else x for x in a]      # rund 1,5 % der Bits anders (andere Kodierung)
other = [rnd.getrandbits(32) for _ in range(700)]
check(kf.similarity(a, a) == 1.0 and kf.similarity(a, b) > 0.95, "gleiche Aufnahme: aehnlich")
check(kf.similarity(a[10:], a) == 1.0, "Versatz am Anfang (andere Stille): trotzdem gleich")
check(kf.similarity(a, other) < 0.6 and kf.similarity(a, []) == 0.0 and kf.similarity(a[:20], a[:20]) == 0.0, "fremdes Lied, leer oder zu kurz: kein Treffer")
check(kf.candidates(219.5, [{"path": "/x", "duration": 219.51}, {"path": "/y", "duration": 223.0}, {"path": "/z", "duration": 218.0}]) == [
      {"path": "/x", "duration": 219.51}, {"path": "/z", "duration": 218.0}], "nur fast gleich lange Lieder, die aehnlichste zuerst")

# Auftrag mit nachgestelltem fpcalc: Import-Datei mit anderem Namen hat denselben Klang wie ein Lied am Stick
stick = os.path.join(tmp, "STICK")
root = os.path.join(stick, "musik")
os.makedirs(os.path.join(root, "U-MUSIK", "Compilations", "Future Trance 13"))
ia.ensure_dirs(root)
imp = ia.import_dir(root)
lib_file = os.path.join(root, "U-MUSIK", "Compilations", "Future Trance 13", "Aquagen - Partyalarm.mp3")
new_file = os.path.join(imp, ia.CAT_NEW, "01 - Future Trance 13 - Techno.mp3")
fremd = os.path.join(imp, ia.CAT_NEW, "Ganz - Anders.mp3")
for p in (lib_file, new_file, fremd):
    with open(p, "wb") as f:
        f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 50)
FP = {lib_file: a, new_file: b, fremd: other}
calls = []


def fake_fpcalc(cmd, **kw):
    calls.append(cmd[-1])
    return type("R", (), {"stdout": json.dumps({"duration": 219.5, "fingerprint": FP[cmd[-1]]}).encode()})()


import folder_lib                           # noqa: E402
folder_lib.read_mp3 = lambda p: {"duration": 219.51}
songs = [{"path": lib_file, "artist": "Aquagen", "title": "Partyalarm (Und ab geht's) (Radio Mix)", "duration": 219.51, "bitrate": 320}]
ck = kf.Checker(base=os.path.join(tmp, "klang"), fpcalc_fn=lambda: "/x/fpcalc", run=fake_fpcalc, ffmpeg_fn=lambda: "")
ck.start(root, lambda: songs, lambda p: p)
for _ in range(1000):
    if ck.status()["state"] != "run":
        break
    time.sleep(0.02)
st = ck.status()
moved = os.path.join(imp, ia.CAT_SAME, "01 - Future Trance 13 - Techno.mp3")
check(st["state"] == "ok" and st["found"] == 1 and st["total"] == 2 and os.path.isfile(moved) and not os.path.exists(new_file) and os.path.isfile(fremd),
      "gleicher Klang: nach 'gibt es schon' verschoben, das fremde Lied bleibt: " + json.dumps(st))
hit = kf.hit_for(moved, base=os.path.join(tmp, "klang"))
check(hit and hit["path"] == lib_file and hit["score"] > 0.95 and hit["artist"] == "Aquagen", "Treffer gemerkt: " + json.dumps(hit))
n0 = len(calls)
ck2 = kf.Checker(base=os.path.join(tmp, "klang"), fpcalc_fn=lambda: "/x/fpcalc", run=fake_fpcalc, ffmpeg_fn=lambda: "")
ck2.start(root, lambda: songs, lambda p: p)
for _ in range(1000):
    if ck2.status()["state"] != "run":
        break
    time.sleep(0.02)
check(len(calls) == n0, "zweiter Durchgang: schon gepruefte Dateien werden nicht noch einmal gerechnet")
try:
    kf.Checker(fpcalc_fn=lambda: "").start(root, [], None)
    check(False, "ohne Chromaprint abgelehnt")
except ValueError as e:
    check("brew install chromaprint" in str(e), "ohne Chromaprint: Hinweis, wie man es installiert")

# Fehlerbericht 11.11.2026: "Mike && the Mechanics Over My Shoulder" (VBR ohne Kopf) meldete 1308 s statt 220 s und kam gar nicht
# in die Auswahl. Jetzt zaehlt die echte Laenge (ffmpeg dekodiert einmal ganz).
check(kf.real_duration("/x.mp3", "/bin/ffmpeg", run=lambda c, **k: type("R", (), {"stderr": b"size=N/A time=00:00:10.00 x\nsize=N/A time=00:03:39.89 bitrate=N/A"})()) == 219.89
      and kf.real_duration("/x.mp3", "", run=None) == 0.0, "echte Laenge aus der letzten Zeitangabe von ffmpeg")
vbr = os.path.join(imp, ia.CAT_NEW, "02 - Sunshine Feeling - Over - Mike && the Mechanics Over My Shoulder.mp3")
mm = os.path.join(root, "U-MUSIK", "Compilations", "Future Trance 13", "Mike + The Mechanics - Over My Shoulder.mp3")
for p_ in (vbr, mm):
    with open(p_, "wb") as f:
        f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 60)
c_ = [rnd.getrandbits(32) for _ in range(700)]
FP[vbr], FP[mm] = c_, c_
folder_lib.read_mp3 = lambda p: {"duration": 1308.18 if p == vbr else 219.9}


def fake_both(cmd, **kw):
    if cmd[-1] == "-":                         # ffmpeg: echte Laenge
        return type("R", (), {"stderr": b"size=N/A time=00:03:39.89 bitrate=N/A"})()
    return fake_fpcalc(cmd, **kw)


songs2 = songs + [{"path": mm, "artist": "Mike + The Mechanics", "title": "Over My Shoulder", "duration": 219.9, "bitrate": 320}]
ck3 = kf.Checker(base=os.path.join(tmp, "klang"), fpcalc_fn=lambda: "/x/fpcalc", run=fake_both, ffmpeg_fn=lambda: "/x/ffmpeg")
ck3.start(root, lambda: songs2, lambda p: p)
for _ in range(1000):
    if ck3.status()["state"] != "run":
        break
    time.sleep(0.02)
check(os.path.isfile(os.path.join(imp, ia.CAT_SAME, os.path.basename(vbr))) and not os.path.exists(vbr),
      "falsche geschaetzte Laenge: mit der echten gefunden und nach 'gibt es schon' verschoben: " + json.dumps(ck3.status()))

# Import-Seite: das Lied steht mit dem vorhandenen Gegenstueck (gleicher Klang) da
kf.DATA_DIR = os.path.join(tmp, "klang")
_orig_load = kf.load_results
kf.load_results = lambda base=None: _orig_load(os.path.join(tmp, "klang"))
s = ia.scan(root, lambda: songs, "U-MUSIK", read=lambda p: {"artist": "Future Trance 13", "title": "Techno", "duration": 219.51})
rec = next(x for f in s["folders"] for x in f["songs"] if x["file"].startswith("01 - Future"))
check(rec["folder"] == ia.CAT_SAME and rec.get("klang", 0) > 0.95 and rec["dup"]["path"] == lib_file, "Import-Seite: gleicher Klang mit dem vorhandenen Lied")
js = open(os.path.join(ROOT, "pi", "static", "sm", "import.js"), encoding="utf-8").read()
html = open(os.path.join(ROOT, "pi", "static", "sm", "import.html"), encoding="utf-8").read()
check('id="bklang"' in html and "op: 'klang'" in js and "/import?klang=1" in js and "Gleicher Klang</b>" in js, "Seite: Knopf Klang pruefen, Fortschritt, Treffer")
check("f !== klangFound && !busy && Date.now() - klangLoadT > 10000" in js,
      "waehrend der Pruefung: neue Treffer gleich aus 'neu' nehmen (hoechstens alle 10 s neu laden; Fehlerbericht 11.11.2026)")
check(html.index('id="bklang"') < html.index('id="bklangstop"') < html.index('id="klangt"') and "$('bklangstop').disabled = !run" in js,
      "Anhalten fest rechts neben Klang pruefen, der wechselnde Text dahinter (Knoepfe springen nicht, Wunsch 11.11.2026)")
_mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
_mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check(_mh.index('id="fadestop"') < _mh.index('id="fadechipt"') and "$('fadestop').hidden" not in _mj, "Fade-Anzeige: Stopp vor dem Liednamen, ausgegraut statt versteckt")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("klang_fp.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert klang_fp.py")

# echt mit fpcalc und ffmpeg (nur am Mac, wenn installiert): gleiches Rauschen mit 128 und 320 kbit/s, anderes Rauschen
ff = kf.find_fpcalc()
from convert_mp3 import find_ffmpeg         # noqa: E402
fm = find_ffmpeg()
if ff and fm:
    def mk(name, seed, br):
        p = os.path.join(tmp, name)
        subprocess.run([fm, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"anoisesrc=d=40:c=pink:seed={seed}",
                        "-af", "volume=0.5,tremolo=f=2:d=0.9", "-c:a", "libmp3lame", "-b:a", br, p], check=True)
        return kf.raw_fp(p, ff)
    x1, x2, y = mk("a128.mp3", 1, "128k"), mk("a320.mp3", 1, "320k"), mk("b320.mp3", 2, "320k")
    s_same, s_other = kf.similarity(x1, x2), kf.similarity(x1, y)
    check(s_same >= kf.SAME and s_other < kf.SAME, f"echt (Chromaprint): gleiche Musik 128/320 kbit/s {s_same}, andere {s_other}")
else:
    print("  (echter Klang-Vergleich uebersprungen: fpcalc oder ffmpeg fehlt hier)")
# Meldung nach dem Abgleich je nach Zahl (Wunsch 12.11.2026: "0 Lieder ... sie liegen jetzt in" war verwirrend)
import shutil as _sh, subprocess as _sp  # noqa: E402,E401
_ij = open(os.path.join(ROOT, "pi", "static", "sm", "import.js"), encoding="utf-8").read()
_m = _ij[_ij.index("const klangDone = "):]
_m = _m[:_m.index(");\n") + 2]
if _sh.which("node"):
    _o = _sp.run(["node", "-e", _m.replace("const klangDone", "var klangDone") + "; console.log([0, 1, 3].map(n => klangDone(n, 9)).join('|'))"],
                 capture_output=True, text=True).stdout.strip().split("|")
    check(len(_o) == 3 and "Keines gibt es schon" in _o[0] and "liegen" not in _o[0] and "1 Lied gibt es schon" in _o[1] and "es liegt" in _o[1]
          and "3 Lieder" in _o[2] and "sie liegen" in _o[2], "Meldung passt zur Zahl: " + str(_o))
finish("test_klang")
