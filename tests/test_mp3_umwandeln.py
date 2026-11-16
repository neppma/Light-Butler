"""MP4, WAV ... auf Knopfdruck in eine MP3 umwandeln (Wunsch von Markus, 07.11.2026): ffmpeg am Mac, MP3 mit gleichem Namen
daneben, Original bleibt, nie ueber eine vorhandene Datei, nur Dateien der Bibliothek, Knopf in der Musik-Datenbank."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

from _common import ROOT, check, finish

BRIDGE = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BRIDGE)
import convert_mp3 as cm   # noqa: E402
import music_serve as ms   # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_mp3_")


def make_wav(name, secs=2):
    p = os.path.join(tmp, name)
    with wave.open(p, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(bytes(4 * 44100 * secs))
    return p


# ---- Aufruf: nie ueber eine Shell, 320 kbit/s, Angaben und Cover aus der Quelle ----
cmd = cm.command("/x/ffmpeg", "/m/a b.mp4", "/m/.a b.mp3.lb-tmp", cover=2)
check(isinstance(cmd, list) and cmd[0] == "/x/ffmpeg" and "/m/a b.mp4" in cmd and cmd[-1] == "/m/.a b.mp3.lb-tmp", "Aufruf als Liste, Pfade unveraendert")
check(cmd[cmd.index("-b:a") + 1] == "320k" and "libmp3lame" in cmd and cmd[cmd.index("-map_metadata") + 1] == "0"
      and cmd[cmd.index("-id3v2_version") + 1] == "3", "320 kbit/s, Titel und Interpret aus der Quelle, ID3v2.3")
check("0:2" in cmd and "attached_pic" in cmd and "0:2" not in cm.command("/x/ffmpeg", "a", "b", cover=None), "Cover nur mit Bild-Strom")
check(cm.target_for("/m/Lied.MP4") == "/m/Lied.mp3" and cm.can_convert("/m/x.wav") and cm.can_convert("/m/x.M4A") and not cm.can_convert("/m/x.mp3"),
      "Ziel daneben mit Endung .mp3, MP3 wird nicht umgewandelt")


class Run:
    """ffprobe/ffmpeg nachgestellt: probe = Ausgabe von ffprobe, fail_cover = mit Bild scheitern."""

    def __init__(self, probe="", fail_cover=False, fail=False):
        self.probe, self.fail_cover, self.fail, self.calls = probe, fail_cover, fail, []

    def __call__(self, c, **kw):
        self.calls.append(c)
        if c[0].endswith("ffprobe"):
            return subprocess.CompletedProcess(c, 0, self.probe.encode(), b"")
        if self.fail or (self.fail_cover and "attached_pic" in c):
            return subprocess.CompletedProcess(c, 1, b"", b"Fehler im Codec\nStream map nicht passend")
        with open(c[-1], "wb") as f:
            f.write(b"\xff\xfb" + b"x" * 4000)
        return subprocess.CompletedProcess(c, 0, b"", b"")


fake = os.path.join(tmp, "ffmpeg")
for n in ("ffmpeg", "ffprobe"):
    open(os.path.join(tmp, n), "w").close()
src = make_wav("Lied.wav")
raw = open(src, "rb").read()
r = Run(probe="0,h264,0\n1,mjpeg,0\n2,png,1\n")
check(cm.cover_stream(fake, src, r) == 2, "Cover: Bild mit Kennzeichen Cover geht vor, Video zaehlt nicht")
check(cm.cover_stream(fake, src, Run(probe="0,h264,0\n")) is None and cm.cover_stream(fake, src, Run(probe="1,mjpeg,0\n")) == 1, "ohne Bild kein Cover")
dst = cm.convert(src, ffmpeg=fake, run=r)
check(dst == os.path.join(tmp, "Lied.mp3") and os.path.isfile(dst) and open(src, "rb").read() == raw, "MP3 daneben, Original unveraendert")
check(not [n for n in os.listdir(tmp) if n.endswith(".lb-tmp")], "keine Hilfsdatei uebrig")
mp3_before = open(dst, "rb").read()
try:
    cm.convert(src, ffmpeg=fake, run=Run())
    check(False, "vorhandene MP3 darf nicht ueberschrieben werden")
except cm.ConvertError as e:
    check("gibt es schon" in str(e) and open(dst, "rb").read() == mp3_before, "vorhandene MP3 nie ueberschrieben")
src2 = make_wav("Video.mp4")
r2 = Run(probe="0,h264,0\n1,mjpeg,0\n", fail_cover=True)
check(cm.convert(src2, ffmpeg=fake, run=r2).endswith("Video.mp3") and sum(1 for c in r2.calls if c[0] == fake) == 2
      and "attached_pic" not in r2.calls[-1], "Bild geht nicht: zweiter Versuch nur mit Ton")
src3 = make_wav("Kaputt.wav")
try:
    cm.convert(src3, ffmpeg=fake, run=Run(fail=True))
    check(False, "Fehler muss gemeldet werden")
except cm.ConvertError as e:
    check("Stream map" in str(e) and not os.path.exists(os.path.join(tmp, "Kaputt.mp3"))
          and not [n for n in os.listdir(tmp) if n.endswith(".lb-tmp")], "Fehler von ffmpeg gemeldet, keine halbe Datei")
for bad, why in ((os.path.join(tmp, "x.mp3"), "Dateiart"), (os.path.join(tmp, "fehlt.wav"), "nicht gefunden")):
    try:
        cm.convert(bad, ffmpeg=fake, run=Run())
        check(False, why)
    except cm.ConvertError as e:
        check(why in str(e), f"abgelehnt: {why}")
try:
    cm.convert(src3, ffmpeg="", run=Run())
    check(False, "ohne ffmpeg")
except cm.ConvertError as e:
    check("brew install ffmpeg" in str(e), "ohne ffmpeg: Hinweis, wie man es installiert")

# ---- echtes ffmpeg, wenn am Mac installiert ----
ff = cm.find_ffmpeg()
if ff:
    real = make_wav("Echt.wav", secs=3)
    out = cm.convert(real)
    check(os.path.getsize(out) > 50000 and open(out, "rb").read(3) in (b"ID3", b"\xff\xfb"[:3]), "echtes ffmpeg: MP3 geschrieben")
else:
    check(True, "ffmpeg nicht installiert: echter Durchlauf uebersprungen")

# ---- Hintergrund: eine nach der anderen, Stand abfragbar ----
seen = []
jobs = cm.Jobs(done=lambda s, d: seen.append((s, d)), convert_fn=lambda s: (time.sleep(0.05), s[:-4] + ".mp3")[1])
check(jobs.start("/m/a", "/x/a.wav")["state"] == "wait" and jobs.start("/m/a", "/x/a.wav")["state"] in ("wait", "run"), "zweiter Klick startet nicht doppelt")
jobs.start("/m/b", "/x/b.wav")
for _ in range(100):
    if jobs.status("/m/b").get("state") == "ok":
        break
    time.sleep(0.02)
check(jobs.status("/m/a")["state"] == "ok" and jobs.status("/m/b")["out"] == "/x/b.mp3" and len(seen) == 2 and jobs.status("/m/c") == {"state": ""},
      "beide fertig, Nacharbeit fuer jede, unbekanntes Lied ohne Stand")
ej = cm.Jobs(convert_fn=lambda s: (_ for _ in ()).throw(cm.ConvertError("geht nicht")))
ej.start("/m/e", "/x/e.wav")
for _ in range(100):
    if ej.status("/m/e").get("state") == "err":
        break
    time.sleep(0.02)
check(ej.status("/m/e") == {"state": "err", "error": "geht nicht", "t": ej.status("/m/e")["t"]}, "Fehler mit Grund im Stand")

# ---- Vorhoer-Server: nur Dateien der Bibliothek, nur mit passendem Namen ----
lib_wav = make_wav("Bib.wav")
lib_mp3 = os.path.join(tmp, "Lied.mp3")
srv = ms.MusicServer([lib_wav, lib_mp3, src3], port=0)
done = []
srv.on_converted = lambda s, d: done.append(d)
srv.jobs = cm.Jobs(done=lambda s, d: srv.on_converted(s, d), convert_fn=lambda s: cm.convert(s, ffmpeg=fake, run=Run()))
cm_find = cm.find_ffmpeg
cm.find_ffmpeg = lambda: fake
check(srv.start(), "Server startet")
base = f"http://127.0.0.1:{srv.port}"


def post(path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


check(post("/convert", {"p": "/fremd/x.wav", "name": "x.wav"})[0] == 404, "Datei ausserhalb der Bibliothek: abgelehnt")
check(post("/convert", {"p": lib_wav, "name": "anders.wav"})[0] == 400, "falscher Dateiname: abgelehnt")
check(post("/convert", {"p": lib_mp3, "name": "Lied.mp3"})[0] == 400, "MP3 wird nicht umgewandelt")
code, j = post("/convert", {"p": lib_wav, "name": "Bib.wav"})
check(code == 202 and j["state"] in ("wait", "run", "ok"), "Umwandlung gestartet")
for _ in range(100):
    with urllib.request.urlopen(base + "/convert?p=" + urllib.request.quote(lib_wav, safe=""), timeout=5) as resp:
        st = json.loads(resp.read())
    if st.get("state") == "ok":
        break
    time.sleep(0.05)
check(st.get("state") == "ok" and st.get("name") == "Bib.mp3" and os.path.isfile(os.path.join(tmp, "Bib.mp3")) and done, "fertig, MP3 daneben, Bruecke benachrichtigt")
with open(os.path.join(tmp, "Kaputt.mp3"), "wb") as f:
    f.write(b"schon da")
check(post("/convert", {"p": src3, "name": "Kaputt.wav"})[0] == 409 and open(os.path.join(tmp, "Kaputt.mp3"), "rb").read() == b"schon da",
      "MP3 gibt es schon: abgelehnt, nichts ueberschrieben")
with urllib.request.urlopen(base + "/convert?p=" + urllib.request.quote("/fremd/x.wav", safe=""), timeout=5) as resp:
    check(json.loads(resp.read()) == {"state": ""}, "Stand nur fuer Dateien der Bibliothek")
srv.stop()
cm.find_ffmpeg = cm_find

# ---- Bruecke, Installation, Panel ----
mb_src = open(os.path.join(BRIDGE, "mixxx_bridge.py"), encoding="utf-8").read()
check('ms.on_converted = lambda src, dst: fw.folder is not None and setattr(fw.folder, "t", 0.0)' in mb_src, "neue MP3: Musikordner gleich neu einlesen")
for f in ("install_launcher.sh", os.path.join("..", "helper", "install_helper.sh")):
    check("convert_mp3.py" in open(os.path.join(BRIDGE, f), encoding="utf-8").read(), f"{os.path.basename(f)} kopiert convert_mp3.py")
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("const CONV_EXT = ['mp4', 'm4a', 'wav'" in mj and "(CONV_EXT.includes(String(r.ext || '').toLowerCase()) && (r._cv || !hasMp3(r)) ? '<span class=\"cvw\" data-cvw=\"' + r._i + '\">' + convButton(r, canPlay) + '</span>' : '')" in mj
      and "function redrawConv(r)" in mj
      and "fetch(music + '/convert', { method: 'POST'" in mj and "else if (b.dataset.conv != null) convertRow(all[+b.dataset.conv]);" in mj,
      "Musik-Datenbank: Knopf → MP3 nur bei umwandelbaren Dateien")
# Fehlerbericht 07.11.2026: Knopf fehlte, weil der Typ gross geschrieben ist ("MP4"). Die Zelle echt rechnen.
import re as _re  # noqa: E402
ext_of = _re.search(r"const extOf = (p => \{.*?\});", mj).group(1)
cell = subprocess.run(["node", "-e", "const extOf=" + ext_of + ";const CONV_EXT=['mp4','m4a','wav','aif','aiff','flac','aac','ogg'];"
                       "for (const p of ['/m/a.mp4','/m/b.MP4','/m/c.wav','/m/d.mp3']) console.log(CONV_EXT.includes(String(extOf(p)||'').toLowerCase()))"],
                      capture_output=True, text=True).stdout.split()
check(cell == ["true", "true", "true", "false"], f"Knopf → MP3 bei MP4 und WAV, auch gross geschrieben, nicht bei MP3 ({cell})")
check("const fileWord = r => (r.ext ? String(r.ext).toUpperCase() + '-Datei' : 'Datei');" in mj and "fileWord(r) + ' am Musik-Rechner in den Papierkorb legen" in mj
      and "MP3 am Mac in den Papierkorb legen" not in mj, "Mistkuebel nennt den Dateityp (MP4-Datei, WAV-Datei), nicht immer MP3 (Wunsch 07.11.2026)")
finish("MP3 umwandeln")
