"""Lautheit (Wunsch 11.11.2026): am Mac messen (EBU R128, ffmpeg), Spalte und Filter in der Musik-Datenbank, Vorhoeren und
Auto-DJ gleich laut, ReplayGain nur mit Einstellung und nur in Dateien ohne Angabe."""
import json
import os
import subprocess
import sys
import tempfile
import time

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "pi"))
import loudness as ld                        # noqa: E402
import id3_tags as it                        # noqa: E402
import mixxx_bridge as mb                    # noqa: E402
import music_serve                           # noqa: E402
from convert_mp3 import find_ffmpeg          # noqa: E402

OUT = """[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:          -8.4 LUFS
    Threshold: -18.6 LUFS

  True peak:
    Peak:        0.7 dBFS
"""
check(ld.parse_ebur128(OUT) == (-8.4, 0.7), "ffmpeg-Ausgabe gelesen: LUFS und echte Spitze")
check(ld.parse_ebur128("I: -inf LUFS\n") is None and ld.parse_ebur128("nix") is None, "Stille oder kaputt: kein Wert")


def mp3(name, frames=b""):
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" + b"\x00" * 4000)
    if frames:
        it.write(p, 3, 0, frames)
    return p


plain = mp3("ohne.mp3")
foreign = mp3("fremd.mp3", it.frame(b"TXXX", it.txxx_body("REPLAYGAIN_TRACK_GAIN", "-7.10 dB"), 3))
rva = mp3("rva.mp3", it.frame(b"RVA2", b"track\x00\x01\xff\x00\x00", 3))
check(ld.rg_present(plain) == (False, False) and ld.rg_present(foreign) == (True, False) and ld.rg_present(rva)[0], "vorhandene ReplayGain-Angabe erkannt (TXXX und RVA2)")

check(ld.write_rg_tag(foreign, -9.0, -0.5) == "vorhanden" and ld.write_rg_tag(rva, -9.0, -0.5) == "vorhanden", "fremde Angabe bleibt, wie sie ist (Wunsch 11.11.2026)")
check(ld.write_rg_tag(plain, -9.0, -0.5) == "ok", "ohne Angabe: geschrieben")
fr = {it.txxx_desc(b): ld._txxx_value(b) for fid, fl, raw, b in it.read(plain)[2] if fid == b"TXXX"}
check(fr.get("replaygain_track_gain") == "-9.00 dB" and fr.get("replaygain_track_peak") == "0.944061" and "replaygainsource" in fr,
      "Bezug -18 LUFS, Spitze linear, Vermerk Light-Butler: " + json.dumps(fr))
check(ld.write_rg_tag(plain, -9.0, -0.5) == "gleich" and ld.write_rg_tag(plain, -10.0, -0.5) == "ok", "eigene Angabe darf erneuert werden")
check(ld.rg_present(plain) == (True, True), "eigene Angabe als eigene erkannt")
with open(plain, "rb") as f:
    check(f.read()[-4004:] == b"\xff\xfb\x90\x00" + b"\x00" * 4000, "die Musik dahinter bleibt Byte fuer Byte gleich")
check(ld.write_rg_tag(os.path.join(tmp, "x.wav"), -9, 0) == "keine MP3" and ld.write_rg_tag(plain, "x", 0) == "Wert ungueltig", "nur MP3, nur Zahlen")


def fake_run(cmd, **kw):
    return type("R", (), {"stderr": OUT.encode(), "returncode": 0})()


m = ld.measure_one({"path": "/lib/a.mp3", "file": foreign}, "/bin/ffmpeg", run=fake_run)
check(m["lufs"] == -8.4 and m["tp"] == 0.7 and m["rg"] == 1 and m["v"] == ld.VERSION, "messen: Werte und fremde ReplayGain vermerkt")
m2 = ld.measure_one({"path": "/lib/b.mp3", "file": "/gibt/es/nicht.mp3"}, "/bin/ffmpeg", run=lambda *a, **k: (_ for _ in ()).throw(OSError("weg")))
check("err" in m2 and "lufs" not in m2, "unlesbar: Fehler vermerkt, kein Wert")

# Ablage, Lesen, Schreiben nur ohne Angabe
L = ld.Loudness(base=os.path.join(tmp, "laut"), ffmpeg_fn=lambda: "")
os.makedirs(L.base, exist_ok=True)
with open(L.path, "w", encoding="utf-8") as f:
    for r in ({"path": "/lib/ohne.mp3", "lufs": -12.0, "tp": -1.0, "rg": 0}, {"path": "/lib/fremd.mp3", "lufs": -7.0, "tp": 0.2, "rg": 1},
              {"path": "/lib/kaputt.mp3", "err": "nicht messbar"}):
        f.write(json.dumps(r) + "\n")
check(L.refresh() and L.get("/lib/ohne.mp3") == (-12.0, -1.0, 0) and L.get("/lib/fremd.mp3")[2] == 1 and L.get("/lib/kaputt.mp3") is None, "Werte gelesen")
check(L.start([{"path": "/lib/neu.mp3"}]) == 0, "ohne ffmpeg wird nicht gemessen")
plain2 = mp3("ohne2.mp3")
L.write_tick([("/lib/ohne.mp3", plain2), ("/lib/fremd.mp3", foreign)], gap_s=0)
L.writer.join(5)
check(L.written == {"/lib/ohne.mp3": "ok"} and ld.rg_present(plain2) == (True, True) and L.get("/lib/ohne.mp3")[2] == 2,
      "geschrieben nur ins Lied ohne Angabe, danach als 'von uns' gekennzeichnet: " + json.dumps(L.written))

# zum Pi
rec = {"artist": "A", "title": "T", "duration": 200.0, "path": "/lib/ohne.mp3"}
item = [x for ch in mb.library_chunks([rec], loud=L) for x in ch][0]
check(item[27:30] == [-12.0, -1.0, 2], "Bibliothek: Felder 28 bis 30 (LUFS, Spitze, ReplayGain): " + str(item[27:]))
import mixxx_link                            # noqa: E402
d = mixxx_link.lib_item(item)
check(d["lufs"] == -12.0 and d["tp"] == -1.0 and d["rgt"] == 2, "Pi liest die Lautheit")
bad = mixxx_link.lib_item(item[:27] + ["laut", 99, 7])
old = mixxx_link.lib_item(item[:27])
check(bad["lufs"] == 0 and bad["tp"] == 0 and bad["rgt"] == 0 and old["lufs"] == 0, "Unsinn oder alte Bruecke: keine Werte")

ms = music_serve.MusicServer.__new__(music_serve.MusicServer)
for k in ("energy_write", "key_write", "rg_write"):
    setattr(ms, k, False)
try:
    ms.apply_conf({"rw": True})
except Exception:                            # noqa: BLE001  (der Rest von apply_conf braucht mehr Aufbau)
    pass
check(ms.rg_write is True, "Mac uebernimmt die Einstellung rg_write vom Pi")
import settings                              # noqa: E402
p = next(x for x in settings.DEFS if x.key == "rg_write")
check(p.default == 0.0 and "vorhandene bleibt" in p.desc, "Einstellung ReplayGain schreiben: Standard aus")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('"rw": rw' in api, "Pi schickt rw an den Mac")
from showman import autodj                   # noqa: E402
check(autodj.item({"path": "/a", "lufs": -9.5, "tp": -0.3})["lufs"] == -9.5, "Auto-DJ bekommt die Lautheit je Lied")

# echte Messung (nur am Mac mit Homebrew)
ff = find_ffmpeg()
if ff:
    real = os.path.join(tmp, "sinus.mp3")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-c:a", "libmp3lame", "-b:a", "192k", real], check=True)
    r = ld.measure_one({"path": real}, ff)
    check(abs(r.get("lufs", 0) + 22.0) < 1.0 and r.get("tp", 0) < -15, "echte Messung: Sinus bei -22 LUFS: " + json.dumps(r))
    L2 = ld.Loudness(base=os.path.join(tmp, "laut2"), ffmpeg_fn=lambda: ff)
    check(L2.start([{"path": real}]) == 1, "Messung im eigenen Prozess gestartet")
    for _ in range(100):
        if not L2.running():
            break
        time.sleep(0.1)
    check(L2.refresh() and abs(L2.get(real)[0] + 22.0) < 1.0, "Ergebnis aus dem Prozess gelesen")
else:
    print("  (echte Messung uebersprungen: ffmpeg fehlt hier)")

SM = os.path.join(ROOT, "pi", "static", "sm")
core = open(os.path.join(SM, "core.js"), encoding="utf-8").read()
mj = open(os.path.join(SM, "music.js"), encoding="utf-8").read()
mh = open(os.path.join(SM, "music.html"), encoding="utf-8").read()
aj = open(os.path.join(SM, "autodj.js"), encoding="utf-8").read()
ah = open(os.path.join(SM, "autodj.html"), encoding="utf-8").read()
check("SM.loudDb = " in core and "SM.LOUD_TARGET = -14" in core, "Ziel -14 LUFS")
node = subprocess.run(["node", "-e", "global.window={};" + "const SM={};" + core[core.index("SM.LOUD_TARGET"):core.index("SM.ejectStick")]
                       + "console.log(JSON.stringify([SM.loudDb(-8,0.5,false),SM.loudDb(-20,-10,false),SM.loudDb(-20,-10,true),SM.loudDb(-20,-3,true),SM.loudDb(0,0,true)]))"],
                      capture_output=True, text=True)
check(node.stdout.strip() == "[-6,0,6,2,0]", "laut: leiser; leise: nur im Auto-DJ lauter, nie ueber -1 dB Spitze: " + node.stdout.strip() + node.stderr[-200:])
check("k: 'lufs'" in mj and "k: 'tp'" in mj and 'id="lmin"' in mh and 'id="lnone"' in mh and "$('lnone').checked = false" in mj, "Musik-DB: Spalten und Filter")
check('id="vnorm"' in mh and "SM.loudDb(cur.lufs, cur.tp, false)" in mj, "Vorhoeren gleich laut (abschaltbar)")
check('id="onorm"' in ah and "d.hp.connect(d.norm); d.norm.connect(d.gain)" in aj and "SM.loudDb(it.lufs, it.tp, true)" in aj, "Auto-DJ gleich laut")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("loudness.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert loudness.py")
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("def loud_tick(self)" in src and "self.loud_tick()" in src and "fw.loud = Loudness(" in src, "Bruecke und Helfer messen im Hintergrund")
finish("test_lautheit")
