"""DMX-Monitor: eigene Seite mit allen 512 Kanaelen eines Ziels (DMX-Kette oder WLED), genau das zuletzt Gesendete,
mit den Fixtures darauf. Nur Anzeige, nichts laesst sich dort einstellen."""
import os
import subprocess
import tempfile
import time

from _common import build, check, finish, Clock

import dmx
import webpanel
from artnet_in import ArtNetIn


class Rec:
    def send(self, d):
        pass

    def close(self):
        pass


rig, sh = build(seed=3)
out = dmx.Output(rig, lambda ip: Rec())
sh.output = out
c = Clock(sh)
c.run(3)
with rig.lock:
    frames = rig.render_all()
out._send_all(frames)
st = webpanel.dmx_state(sh)
check(st["target"] == rig.target and len(st["data"]) == 512, "Standard: DMX-Kette, 512 Kanaele")
check(bytes(st["data"]) == frames[rig.target], "zeigt genau das zuletzt gesendete Bild")
check(st["targets"][0]["label"] == "DMX (Art-Net-Gateway)" and any("Effektband" in t["label"] for t in st["targets"]),
      "Auswahl: DMX-Kette und die WLED-Geraete")
check(not any(str(t["id"]).startswith("nanoleaf:") for t in st["targets"]), "Nanoleaf nicht in der Auswahl (kein DMX)")
ktv = next(f for f in st["fixtures"] if f["name"] == "laser")
check(ktv["start"] == 301 and ktv["n"] == 34 and ktv["params"][:2] == ["power", "color"], "Fixtures mit Startadresse und Kanalnamen")
check(st["src"] == "show" and st["sending"], "Quelle: Show, Ausgabe an")
eb = next(t["id"] for t in st["targets"] if "Effektband" in t["label"])
st2 = webpanel.dmx_state(sh, eb)
check(st2["target"] == eb and all((f["name"] == "effektband") for f in st2["fixtures"]), "WLED-Ziel waehlbar")
check(webpanel.dmx_state(sh, "1.2.3.4")["target"] == rig.target, "unbekanntes Ziel: DMX-Kette")
sh.cfg.set("dmx_via", 1.0)
check(webpanel.dmx_state(sh)["targets"][0]["label"] == "DMX (USB)", "Beschriftung folgt dem DMX-Weg")
sh.cfg.set("dmx_via", 0.0)
out.ext = ArtNetIn(0)
out.ext.data, out.ext.t = bytes(512), time.monotonic()
out.ext_on = True
check(webpanel.dmx_state(sh)["src"] == "artnet", "Quelle: Art-Net-Eingang, wenn er gerade steuert")
out.set_enabled(rig.target, False)
out.mode[rig.target] = "off"
check(not webpanel.dmx_state(sh)["sending"], "Ausgabe aus wird angezeigt")
sh.output = None
check(len(webpanel.dmx_state(sh)["data"]) == 512, "ohne Ausgabe (Trockenlauf): Bild aus dem Rig")

page = webpanel.dmx_page("en")
check('lang="en"' in page and "fetch('/api/dmx'" in page and 'id="grid"' in page and "Light-Butler" in page, "Seite: Raster, Abfrage, Titel")
check("\\" not in page, "keine Backslashes im Skript")
check("<input type=\"range\"" not in page and "c({" not in page, "nur Anzeige, keine Regler")
p = webpanel.make_page()
check('id="dmxmon" href="/dmx"' in p and "'/dmx?lang='+LANG" in p, "Panel: Link zum DMX-Monitor in der Sprache des Panels")
js = page.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Skript des Monitors fehlerfrei (node --check)")
finish("test_dmx_monitor")
