"""Kleines Pegelmeter rechts in der zweiten Kopfzeile: Pegel, Spitze, Farbe nach dB, gestrichelt ohne Signal, rot bei
Uebersteuerung, Quelle "Line-In" oder "LAN". Antippen oeffnet den Audio-Eingang."""
import os
import subprocess
import tempfile

from _common import build, check, finish

import webpanel

rig, sh = build()
check(sh.snapshot()["lvl"] is None, "Simulator: kein Pegelmeter")


class Src:
    dev_name = "USB Audio Device: - (hw:1,0)"

    def __init__(self, inner):
        self.inner = inner

    def level(self):
        return {"rms_db": -18.0, "peak_db": -9.5, "hold_db": -6.0, "clip": False, "alive": True}

    def poll(self, now=None):
        return self.inner.poll(now)


sh.src = Src(sh.src)
s = sh.snapshot()
check(s["lvl"]["rms_db"] == -18.0 and s["lvl"]["alive"], "Pegel aus der Audio-Analyse im Status")
check(s["lvsrc"] == "line", "Quelle: Line-In")
sh.src.dev_name = "Musik-Rechner (Netzwerk)"
check(sh.snapshot()["lvsrc"] == "lan", "Quelle: LAN (Ton vom Mac)")

p = webpanel.make_page()
check('<span id="lvm" onclick="openAudio()"' in p and 'id="lvr"' in p and 'id="lvp"' in p, "Meter rechts in Zeile 2")
check("const nm=S.lvsrc==='lan'?'LAN':S.lvsrc==='bt'?'Bluetooth':'Line-In'" in p and "ls.title=nm+" in p and "ls.innerHTML=SRC_ICON[src]" in p,
      "Quelle als Symbol, Name beim Darueberfahren")
check(all(k + ":SRC_SVG(" in p for k in ("bt", "lan", "line", "hdmi")), "Symbole Bluetooth, Netzwerk, Klinkenstecker, HDMI")
check("const F=S.lvfwd" in p and "SRC_ICON[F.kind]" in p, "Weiterleitung: Pfeil und Ziel-Symbol neben der Quelle")
check("lvfwd" in sh.snapshot() and sh.snapshot()["lvfwd"] is None, "ohne Weiterleitung kein Pfeil")
check("el.classList.toggle('dead',!L.alive)" in p and "el.classList.toggle('clip'" in p, "ohne Signal gestrichelt, uebersteuert rot")
check("L.peak_db>-3?'#ff5a5a':L.peak_db>-12?'#f0c040':'#3ddc84'" in p, "Farben: gruen, gelb ab -12 dB, rot ab -3 dB")
check("function openAudio()" in p and "a.open=true" in p, "Antippen oeffnet den Audio-Eingang")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
check("const meterTxt=S.bar_len===3?" in p and "S.meter_conf>=0.35" not in p, "Takt nur, wenn das Licht in Dreiergruppen zaehlt (kein graues 3/4?)")
sh.bar_len = 3
check(sh.takt()["quantum"] == 3, "/api/takt: quantum wie das Licht")
sh.bar_len = 4
check(sh.takt()["quantum"] == 4, "sonst 4")
finish("test_pegel_zeile2")
