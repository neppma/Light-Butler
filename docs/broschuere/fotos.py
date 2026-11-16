#!/usr/bin/env python3
"""
fotos.py - Bildschirmfotos fuer die Broschuere aus dem Simulator mit der Demo-Bibliothek (nie der echten Sammlung).

Vorher:  python3 docs/broschuere/demo_daten.py DEMO
         cd pi && S2L_SHOWS_DIR=DEMO python3 show.py --simulate --dry-run --web 8096 --no-midi --mixxx-port 9032
         python3 docs/broschuere/demo_mixxx.py DEMO 9032          (spielt ein erfundenes Lied vor)
Dann:    python3 docs/broschuere/fotos.py DEMO                     (braucht Google Chrome und websocket-client)
Ergebnis: docs/broschuere/bilder/*.jpg
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, "..", "..", "pi"))
from showman import albums as al   # noqa: E402

BASE = "http://localhost:8096"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333
OUT = os.path.join(HIER, "bilder")
# Vor jedem Foto: Hinweis "Musik-Rechner nicht erreichbar" weg (die Demo hat keinen Musik-Rechner), Lamperl auf "vollstaendig"
TIDY = """(() => { const w = document.getElementById('srcwarn'); if (w) w.remove();
 const wr = document.getElementById('warnrow'); if (wr) wr.style.visibility = 'hidden';
 const l = document.getElementById('liblampt'); if (l) { l.textContent = 'Liste vollständig'; l.parentElement.className = 'ok'; }
 document.querySelectorAll('.s2lplay').forEach(e => e.remove());
 document.querySelectorAll('p, div').forEach(e => { if (e.children.length < 3 && /^(Der Pi erreicht den Mac|Liste aus der Ablage)/.test((e.textContent || '').trim())) e.style.display = 'none'; });
 return 1; })()"""


class Tab:
    def __init__(self):
        req = urllib.request.Request("http://127.0.0.1:%d/json/new?about:blank" % PORT, method="PUT")
        info = json.loads(urllib.request.urlopen(req).read())
        self.ws = websocket.create_connection(info["webSocketDebuggerUrl"], timeout=60)
        self.n = 0

    def cmd(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(method + ": " + str(m["error"]))
                return m.get("result", {})

    def js(self, code):
        r = self.cmd("Runtime.evaluate", expression=code, awaitPromise=True, returnByValue=True)
        return (r.get("result") or {}).get("value")

    def shot(self, name, url, w=1400, h=860, scale=2, wait=3.5, js=None, mobile=False, full=False):
        self.cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=scale, mobile=mobile)
        self.cmd("Page.navigate", url=BASE + url)
        time.sleep(wait)
        if js:
            self.js(js)
            time.sleep(1.5)
        self.js(TIDY)
        time.sleep(0.4)
        if full:
            hh = int(self.js("document.documentElement.scrollHeight") or h)
            self.cmd("Emulation.setDeviceMetricsOverride", width=w, height=min(hh, 2600), deviceScaleFactor=scale, mobile=mobile)
            time.sleep(0.8)
        data = self.cmd("Page.captureScreenshot", format="png")["data"]
        from PIL import Image                               # als JPEG: das Projekt bleibt klein
        import io
        Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB").save(os.path.join(OUT, name + ".jpg"), "JPEG", quality=88)
        print("  ", name)


def main(demo):
    os.makedirs(OUT, exist_ok=True)
    lib = json.load(open(os.path.join(demo, "_mixxx_bibliothek.json"), encoding="utf-8"))
    x = next(x for x in lib if x[2] == "Die Almrocker")
    alb = al.album_key(x[23], x[12])
    prof = tempfile.mkdtemp(prefix="lb_chrome_")
    chrome = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=%d" % PORT, "--user-data-dir=" + prof, "--hide-scrollbars",
                               "--no-first-run", "--disable-extensions", "--lang=de-AT", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/json/version" % PORT, timeout=1)
                break
            except OSError:
                time.sleep(0.25)
        t = Tab()
        t.shot("panel", "/", 1280, 900)
        t.shot("panel_handy", "/", 390, 844, scale=3, mobile=True)
        t.shot("musik", "/musik", 1440, 860, wait=5)
        t.shot("interpreten", "/musik/interpreten#k=luna-vega", 1440, 860, wait=5)
        t.shot("alben", "/musik/alben#k=" + alb, 1440, 860, wait=5)
        t.shot("favoriten", "/musik/favoriten", 1440, 860, wait=5)
        t.shot("autodj", "/musik/autodj", 1440, 900, wait=4,
               js="(async () => { document.getElementById('brules').click(); await new Promise(r => setTimeout(r, 4000)); return 1; })()")
        t.shot("pflege", "/musik/pflege", 1280, 900, wait=3)
        t.shot("apc", "/apc", 1280, 860, wait=3)
        t.shot("dmx", "/dmx", 1280, 860, wait=3)
        t.shot("raum", "/raum", 1400, 900, wait=4)
    finally:
        chrome.terminate()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
