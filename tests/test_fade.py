"""Fade-in/-out in MP3s (Wunsch 11.11.2026): Tags bleiben Byte fuer Byte, Original in den Papierkorb, Sammelauftrag, Seiten."""
import os
import subprocess
import sys
import tempfile
import time

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import audio_fade as af                      # noqa: E402
from convert_mp3 import find_ffmpeg          # noqa: E402

tag = b"ID3\x03\x00\x00\x00\x00\x00\x0a" + b"TIT2" + b"\x00\x00\x00\x00\x00\x00" + b"\x00" * 0
head = b"ID3\x03\x00\x00\x00\x00\x00\x05" + b"ABCDE"
v1 = b"TAG" + b"x" * 125
check(af.id3_parts(head + b"MUSIK" + v1) == (head, v1) and af.strip_tags(head + b"MUSIK" + v1) == b"MUSIK" and af.strip_tags(b"MUSIK") == b"MUSIK",
      "ID3v2 vorne und ID3v1 hinten erkannt")
check(af.af_filter(3, 5, 200) == "afade=t=in:st=0:d=3.000,afade=t=out:st=195.000:d=5.000" and af.af_filter(0, 5, 200) == "afade=t=out:st=195.000:d=5.000",
      "Filter fuer ffmpeg")
check(af.af_filter(3, 5, 200, 10, 20) == "atrim=start=10.000:end=180.000,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=3.000,afade=t=out:st=165.000:d=5.000"
      and af.af_filter(0, 0, 200, 4, 0) == "atrim=start=4.000,asetpts=PTS-STARTPTS",
      "Beschneiden: zuerst schneiden, dann Fade-in ab dem neuen Anfang, Fade-out bis zum neuen Ende (ein Durchgang)")
check(af.check_values(0, 0, 100, 3, 0) == (0, 0, 3, 0) and af.check_values(2, 3, 0, 1, 1) == (2, 3, 1, 1), "nur Schnitt ist auch ein Auftrag")
for bad in ((0, 0, 100), (-1, 0, 100), (61, 0, 100), (50, 50, 90), ("x", 0, 100), (0, 0, 100, 50, 46), (10, 10, 100, 40, 40), (0, 0, 100, -1, 0), (0, 0, 0, 601, 0)):
    try:
        af.check_values(*bad)
        check(False, "abgelehnt: " + str(bad))
    except ValueError:
        check(True, "abgelehnt: " + str(bad))

# mit nachgestelltem ffmpeg: neuer Ton, alter Tag-Block, Original in den Papierkorb
src = os.path.join(tmp, "Lied.mp3")
with open(src, "wb") as f:
    f.write(head + b"ALT" * 1000 + v1)


def fake_run(cmd, **kw):
    with open(cmd[-1], "wb") as f:
        f.write(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"NEU" * 1000)
    return type("R", (), {"returncode": 0, "stderr": b""})()


trashed = []
af.fade_file(src, 2, 3, 100, "/bin/ffmpeg", lambda ps: trashed.extend(ps) or 0, run=fake_run)
data = open(src, "rb").read()
check(data == head + b"NEU" * 1000 + v1 and trashed == [src], "Tags unveraendert, Ton neu, Original in den Papierkorb")
check(not [x for x in os.listdir(tmp) if x.startswith(".Lied")], "keine Hilfsdateien uebrig")
try:
    af.fade_file(src, 2, 3, 100, "/bin/ffmpeg", lambda ps: 1, run=fake_run)
    check(False, "Papierkorb geht nicht: abgebrochen")
except ValueError:
    check(open(src, "rb").read() == data, "Papierkorb geht nicht: Datei bleibt, wie sie war")

# echt mit ffmpeg (nur am Mac mit Homebrew)
ff = find_ffmpeg()
if ff:
    real = os.path.join(tmp, "Sinus.mp3")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-c:a", "libmp3lame", "-b:a", "192k",
                    "-metadata", "title=Sinus", "-metadata", "artist=Test", "-id3v2_version", "3", real], check=True)
    import tag_edit
    tag_edit.write_tags(real, {"grouping": "Après-Ski", "imported": "2026-11-11"})
    before = tag_edit.read_tags(real)["fields"]
    af.fade_file(real, 2, 3, 12, ff, lambda ps: 0)
    after = tag_edit.read_tags(real)["fields"]
    lvl = lambda a, b: subprocess.run([ff, "-hide_banner", "-ss", str(a), "-t", str(b), "-i", real, "-af", "astats", "-f", "null", "-"],   # noqa: E731
                                      capture_output=True, text=True).stderr
    import re
    rms = lambda s: float(re.search(r"RMS level dB: (-?[\d.]+|-inf)", s).group(1).replace("-inf", "-200"))   # noqa: E731
    check(before == after, "echte MP3: alle Tags gleich (auch Gruppe und Importdatum)")
    check(rms(lvl(0, 0.3)) < rms(lvl(5, 0.3)) - 10 and rms(lvl(11.7, 0.25)) < rms(lvl(5, 0.3)) - 10, "echte MP3: Anfang und Ende leise, Mitte laut")
    import folder_lib
    af.fade_file(real, 1, 1, 12, ff, lambda ps: 0, ca=2, cb=3)
    d2 = float(folder_lib.read_mp3(real).get("duration") or 0)
    check(abs(d2 - 7) < 0.3 and tag_edit.read_tags(real)["fields"] == before, f"echte MP3: vorne 2 s und hinten 3 s weg, 12 s -> {d2:.2f} s, Tags gleich")
else:
    print("  (echter Fade uebersprungen: ffmpeg fehlt hier)")

# Sammelauftrag
files = []
for i in range(3):
    p = os.path.join(tmp, f"S{i}.mp3")
    with open(p, "wb") as f:
        f.write(head + b"A" * 3000)
    files.append((p, p, 100.0))
files.append(("/x.wav", "/x.wav", 100.0))
done = []
j = af.Jobs(ffmpeg_fn=lambda: "/bin/ffmpeg", trash=lambda ps: 0, done=lambda p, f: done.append(p), run=fake_run)
j.start(files, 1, 2)
for _ in range(100):
    if j.status()["state"] != "run":
        break
    time.sleep(0.02)
s = j.status()
check(s["state"] == "ok" and s["ok"] == 3 and s["total"] == 3 and len(done) == 3, "Sammelauftrag: nur MP3s, eine nach der anderen")
try:
    af.Jobs(ffmpeg_fn=lambda: "", trash=lambda ps: 0).start(files, 1, 2)
    check(False, "ohne ffmpeg: abgelehnt")
except ValueError:
    check(True, "ohne ffmpeg: abgelehnt mit Hinweis")

SM = os.path.join(ROOT, "pi", "static", "sm")
core = open(os.path.join(SM, "core.js"), encoding="utf-8").read()
mj = open(os.path.join(SM, "music.js"), encoding="utf-8").read()
te = open(os.path.join(SM, "tagedit.js"), encoding="utf-8").read()
check("SM.fadeDlg = " in core and "data-gfade=" in mj and "$('bfade').onclick" in mj and 'id="bfade"' in open(os.path.join(SM, "music.html"), encoding="utf-8").read(),
      "Musik-DB: Fade fuer Gruppe und gefilterte Liste")
check("SM.fadeEditor = " in te and 'id="tgwave"' in te and "createMediaElementSource" in te, "Tag-Fenster: Wellenform mit Probehoeren")
check('id="fca"' in te and 'id="fcb"' in te and 'name="fmode"' in te and "ca: ca(), cb: cb()" in te and 'id="fdca"' in core and "fin, fout, ca, cb })" in core,
      "Beschneiden im Wellenform-Fenster und im Sammelauftrag (Wunsch 11.11.2026)")
ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('d.get("ca"), d.get("cb")' in ms, "Mac nimmt vorne/hinten weg an")
check('id="fadechip"' in open(os.path.join(SM, "music.html"), encoding="utf-8").read() and "async function pollFade()" in mj
      and "setInterval(pollFade, 3000)" in mj and "'〰 Fade läuft: '" in mj and "$('fadestop').onclick" in mj,
      "Musik-DB zeigt den laufenden Fade-Auftrag oben, mit Anhalten (Wunsch 11.11.2026)")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("audio_fade.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert audio_fade.py")
finish("test_fade")
