"""Debug-Aufnahme des Toneingangs (Wunsch 12.11.2026): bei Signal eine neue WAV-Datei (mit Vorlauf), nach 3 s ohne Signal Ende,
beim naechsten Signal die naechste. Schalter im Panel, nach dem Start aus, Grenzen gegen eine volle Speicherkarte."""
import os
import sys
import tempfile
import wave

import numpy as np

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "pi"))
import recorder as rc                        # noqa: E402

tmp = tempfile.mkdtemp()
RATE, HOP = 8000, 400                        # 50 ms je Block
t = [0.0]
r = rc.Recorder(os.path.join(tmp, "aufnahmen"), RATE, threshold_db=lambda: -60.0, clock=lambda: t[0], thread=False)
quiet = np.full(HOP, 0.0003, dtype=np.float32)      # ca. -70 dB: Rauschen
loud = (0.3 * np.sin(np.arange(HOP) / 3.0)).astype(np.float32)


def feed(block, secs):
    for _ in range(int(round(secs / (HOP / RATE)))):
        t[0] += HOP / RATE
        r.feed(block)
    r.process()


feed(loud, 2)
check(r.status()["n"] == 0 and not r.on, "Start: aus, nichts aufgenommen")
r.set_on(True)
feed(quiet, 5)
check(r.status()["n"] == 0 and not r.status()["rec"], "an, aber nur Rauschen: keine Datei")
feed(loud, 4)
st = r.status()
check(st["rec"] and st["n"] == 1, "Signal: Aufnahme laeuft")
feed(quiet, 2)
check(r.status()["rec"], "kurze Pause (unter 3 s): Aufnahme laeuft weiter")
feed(quiet, 2)
st = r.status()
check(not st["rec"] and st["n"] == 1, "3 s ohne Signal: Datei zu")
f1 = os.path.join(r.base, st["files"][0]["name"])
with wave.open(f1) as w:
    dur = w.getnframes() / w.getframerate()
    ok = w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == RATE
check(ok and 1.0 + 4 + 3 - 0.2 <= dur <= 1.0 + 4 + 3.3, f"gueltige WAV: Vorlauf 1 s + Signal + Ausklang, {dur:.2f} s")
t[0] += 1.1                                  # neuer Dateiname (Sekunde)
feed(loud, 1)
feed(quiet, 4)
check(r.status()["n"] == 2, "naechstes Signal: neue Datei")

# Fehlerbericht 12.11.2026: Rauschen und Aussetzer in der Aufnahme -> direkt an der Schnittstelle, Stereo, nicht die Summe
t[0] += 1.1
lr = np.stack([loud, -0.5 * loud], axis=1)               # links und rechts verschieden (Summe waere fast still)
feed(lr, 2)
feed(np.zeros((HOP, 2), np.float32), 4)
st = r.status()
with wave.open(os.path.join(r.base, st["files"][0]["name"])) as w:
    ch = w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, ch).astype(np.float32) / 32767
k = int(1.0 * RATE) + 10                                   # nach dem Vorlauf
check(ch == 2 and abs(x[k, 0] - lr[k % HOP, 0]) < 1e-3 and abs(x[k, 1] - lr[k % HOP, 1]) < 1e-3, "Stereo: links und rechts getrennt, Werte unveraendert")
check(st["files"][0]["ch"] == 2, "Liste zeigt die Kanalzahl")
# feed() schreibt nie selbst (Ton-Faden wartet nicht), Ueberlauf wird gezaehlt
rq = rc.Recorder(os.path.join(tmp, "q"), RATE, clock=lambda: t[0], thread=False)
rq.set_on(True)
for _ in range(int(rc.MAX_QUEUE_S * RATE / HOP) + 5):
    rq.feed(loud)
check(not os.path.isdir(rq.base) and rq.dropped == 5, "feed reiht nur ein; Ueberlauf zaehlt als verworfen")
rq.set_on(False)

# Grenzen
rc.MAX_FILE_S, keep = 2.0, rc.MAX_FILE_S
t[0] += 2
feed(loud, 5.2)
rc.MAX_FILE_S = keep
check(r.status()["n"] >= 4, "zu lang: gleich die naechste Datei")
check(r.path_of("../../etc/passwd") is None and r.path_of("x.wav") is None and r.path_of(st["files"][0]["name"]), "Herunterladen nur Aufnahmen aus dem Ordner")
r.set_on(False)
check(not r.status()["rec"] and not r.on, "aus: laufende Datei zu")
check(r.delete_all() >= 4 and r.status()["n"] == 0, "Alle loeschen")
rc.MAX_TOTAL_MB = 0.00005
r.set_on(True)
for _ in range(3):
    t[0] += 1.1
    feed(loud, 1)
    feed(quiet, 4)
check(r.status()["n"] <= 2, "Ordner zu gross: die aeltesten fallen weg")
r.set_on(False)

# MP3 statt WAV (Wunsch 12.11.2026): fertige Datei im Hintergrund umwandeln, WAV erst danach weg, niedrigste Prioritaet
import shutil  # noqa: E402
rc.MAX_TOTAL_MB = 1000.0
cmd = rc.Recorder(os.path.join(tmp, "x"), RATE, thread=False, ffmpeg="ffmpeg")._cmd("a.wav", "a.mp3.tmp", 2)
check("-threads" in cmd and cmd[cmd.index("-threads") + 1] == "1" and (not shutil.which("nice") or cmd[:3] == ["nice", "-n", "19"])
      and "192k" in cmd, "Umwandeln: ein Faden, nice 19, Stereo 192 kbit/s")
if shutil.which("ffmpeg"):
    t[0] += 5
    r = rc.Recorder(os.path.join(tmp, "mp3"), RATE, threshold_db=lambda: -60.0, clock=lambda: t[0], thread=False)
    r.set_on(True)
    feed(loud, 3)
    check(r.status()["files"][0]["name"].endswith(".wav") and not r.enc_q, "laufende Aufnahme: WAV, wird nicht umgewandelt")
    feed(quiet, 4)
    st = r.status()
    check(st["files"][0].get("conv") and list(r.enc_q) == [st["files"][0]["name"]], "fertig: zum Umwandeln eingereiht")
    wav_size = st["files"][0]["size"]
    r.convert_pending()
    st = r.status()
    f = st["files"][0]
    check(len(st["files"]) == 1 and f["name"].endswith(".mp3") and f.get("mp3") and f["size"] < wav_size and 5.5 <= f["dur"] <= 7.5 and f["ch"] == 1,
          "MP3 da (kleiner, Laenge gemerkt), WAV weg: " + str(f))
    check(r.path_of(f["name"]) and st["enc"]["last"]["x"] and not st["enc"]["err"], "Herunterladen der MP3, Geschwindigkeit gemessen")
    # ffmpeg scheitert: WAV bleibt
    r.ffmpeg = "/usr/bin/false"
    t[0] += 2
    feed(loud, 1)
    feed(quiet, 4)
    r.convert_pending()
    st = r.status()
    check(any(x["name"].endswith(".wav") for x in st["files"]) and st["enc"]["err"] and not [n for n in os.listdir(r.base) if n.endswith(".tmp")],
          "Umwandeln scheitert: WAV bleibt, keine halbe MP3")
    # Neustart: halbe MP3 weg, liegengebliebene WAV wieder eingereiht
    open(os.path.join(r.base, "aufnahme-20261112-000000.mp3.tmp"), "w").write("x")
    r2 = rc.Recorder(r.base, RATE, thread=False)
    check(not [n for n in os.listdir(r.base) if n.endswith(".tmp")] and len(r2.enc_q) == 1, "nach Neustart: aufgeraeumt, WAV wieder in der Reihe")
    r2.convert_pending()
    check(all(x["name"].endswith(".mp3") for x in r2.status()["files"]), "danach alles MP3")
    check(r2.delete_all() == 2 and r2.status()["n"] == 0, "Alle loeschen nimmt auch MP3s")
lc = rc.Recorder(os.path.join(tmp, "x"), RATE, thread=False, ffmpeg="/usr/bin/lame")._cmd("a.wav", "a.mp3.tmp", 1)
check(lc[-6:] == ["/usr/bin/lame", "--quiet", "-b", "128", "--cbr", "a.wav"][:6] or lc[-7:-1] == ["/usr/bin/lame", "--quiet", "-b", "128", "--cbr", "a.wav"],
      "ohne ffmpeg: lame (Mono 128 kbit/s): " + str(lc))
nr = rc.Recorder(os.path.join(tmp, "ohne"), RATE, thread=False, ffmpeg="")
check(nr.status()["mp3"] is False, "ohne ffmpeg: bleibt WAV, das Panel sagt es")

# Anbindung
sh = open(os.path.join(ROOT, "pi", "show.py"), encoding="utf-8").read()
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
dep = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
au = open(os.path.join(ROOT, "pi", "audio.py"), encoding="utf-8").read()
check("src.raw_tap = show.recorder.feed" in sh and "self.raw_tap(indata)" in au, "Aufnahme haengt am rohen Eingang (vor Kanalwahl und Gain)")
check("show.recorder = Recorder(" in sh and 'if "rec" in d or d.get("rec_del")' in sh, "Show: Eingang angezapft, Schalter und Loeschen als Befehl")
check('self.path.startswith("/aufnahmen/")' in wp and "rec.path_of(" in wp and "id=\"aud_rec\"" in wp and "function recStat(r)" in wp,
      "Panel: Schalter, Stand und Liste zum Herunterladen im Bereich Audio-Eingang")
check('"audio/mpeg" if p.endswith(".mp3")' in wp and "wird zur MP3" in wp and "fehlt am Pi lame" in wp, "Panel: MP3 herunterladen, Stand der Umwandlung")
check("--exclude '/aufnahmen/'" in dep, "Einspielen fasst die Aufnahmen nicht an")
finish("test_debug_aufnahme")
