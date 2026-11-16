"""Light-Butler-Programme am Musik-Stick (Wunsch von Markus, 14.11.2026): der Helfer legt neben dem Musikordner die Pakete
(Mac, Windows, Pi, Pi-Ersatz), die juengste Sicherung, beide Handbuecher und das Showmanager-Handbuch ab, holt alles nur bei
neuer Fassung (Stand vom Pi), behaelt die vorige in "vorher" und meldet den Stand an den Pi (Karte auf Vorab-Laeufe)."""
import io
import json
import os
import sys
import tempfile
import time
import urllib.error

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "pi"))
import programs_copy as pc  # noqa: E402
import pakete               # noqa: E402

PI = {"v": "aaaa", "backup": "lichtshow-backup-2026-11-14_0430.zip"}
calls = []


class Resp(io.BytesIO):
    def __init__(self, data, cd=""):
        super().__init__(data)
        self.headers = {"Content-Disposition": cd}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(req, timeout=0):
    url = req.full_url if hasattr(req, "full_url") else req
    calls.append(url)
    path = url.split("8080", 1)[1]
    if path == "/download/stand":
        return Resp(json.dumps(PI).encode())
    if path == "/download/backup":
        return Resp(b"PK-backup-" + PI["backup"].encode(), 'attachment; filename="%s"' % PI["backup"])
    if path.startswith("/help"):
        return Resp(('<html><link rel="icon" href="/icon.svg"><img src="/static/sm/verbindungen.svg"><script src="/static/sm/nav.js"></script>' + path + PI["v"]).encode())
    if path == "/api/sm/cmd":
        calls.append(json.loads(req.data.decode()))
        return Resp(b"{}")
    return Resp(("inhalt " + path + " " + PI["v"]).encode())


base = "http://pi:8080"
tmp = tempfile.mkdtemp(prefix="s2l_prog_")
root = os.path.join(tmp, "USB STICK", "musik")
os.makedirs(root)
check(pc.sync(base, os.path.join(tmp, "fehlt"), opener) is None, "ohne Stick: nichts")
t0 = [1794600000.0]
r = pc.sync(base, root, opener, now=lambda: t0[0])
d = os.path.join(tmp, "USB STICK", "Light-Butler-Programme")
check(r["dir"] == d and r["new"] and os.path.isdir(d), "Ordner neben dem Musikordner")
names = sorted(os.listdir(d))
for n in ("light-butler-mac.zip", "light-butler-windows.zip", "light-butler-pi.zip", "light-butler-pi-ersatz.zip", "Handbuch.html", "Manual-EN.html",
          "Showmanager-Handbuch.pdf", "verbindungen.svg", "LIESMICH.txt", "stand.json", PI["backup"], "Light-Butler-Broschuere.pdf"):
    check(n in names, "am Stick: " + n)
h = open(os.path.join(d, "Handbuch.html"), encoding="utf-8").read()
check('src="verbindungen.svg"' in h and "nav.js" not in h and "icon.svg" not in h and "lang=de" in h, "Hilfe deutsch fuer den Stick (Bild daneben, ohne Kopfleiste)")
check("lang=en" in open(os.path.join(d, "Manual-EN.html"), encoding="utf-8").read(), "Hilfe englisch")
_fh = pc.fix_help('<a href="/help/technik?lang=de">T</a><a href="/help?lang=en">H</a><img src="/static/sm/systemschema_en.svg">')
check('href="Technik.html"' in _fh and 'href="Manual-EN.html"' in _fh and 'src="systemschema_en.svg"' in _fh, "Stick: Links zwischen Handbuch und Technik, Bilder daneben")
check(("/help/technik?lang=de", "Technik.html") in pc.OPTIONAL and ("/static/sm/systemschema.svg", "systemschema.svg") in pc.OPTIONAL, "Technische Beschreibung und Systemschema auf den Stick")
li = open(os.path.join(d, "LIESMICH.txt"), encoding="utf-8", newline="").read()
check("install_pi.sh" in li and PI["backup"] in li and "backup.py --restore" in li and "\r\n" in li, "LIESMICH mit Anleitung und Sicherung")
n0 = len(calls)
r = pc.sync(base, root, opener, now=lambda: t0[0] + 1800)
check(not r["new"] and len(calls) == n0 + 1, "gleicher Stand: nur der Stand wird gefragt, nichts neu geholt")
PI["v"] = "bbbb"
r = pc.sync(base, root, opener, now=lambda: t0[0] + 3600)
check(r["new"] and "bbbb" in open(os.path.join(d, "light-butler-mac.zip")).read()
      and "aaaa" in open(os.path.join(d, "vorher", "light-butler-mac.zip")).read(), "neue Fassung: neu geholt, vorige in vorher")
PI["v"] = "cccc"
pc.sync(base, root, opener, now=lambda: t0[0] + 7200)
check("bbbb" in open(os.path.join(d, "vorher", "light-butler-mac.zip")).read(), "vorher hat immer nur die vorige Fassung")
old = PI["backup"]
PI["backup"] = "lichtshow-backup-2026-11-15_0430.zip"
pc.sync(base, root, opener, now=lambda: t0[0] + 90000)
check(os.path.isfile(os.path.join(d, PI["backup"])) and not os.path.isfile(os.path.join(d, old)) and os.path.isfile(os.path.join(d, "vorher", old)),
      "neue Sicherung am Pi: neue am Stick, vorige in vorher")
check(not any(f.endswith(".lb-tmp") for f in os.listdir(d)), "keine Hilfsdateien liegen geblieben")
open(os.path.join(d, "eigene-notiz.txt"), "w").write("x")
PI["v"] = "dddd"
pc.sync(base, root, opener, now=lambda: t0[0] + 100000)
check(os.path.isfile(os.path.join(d, "eigene-notiz.txt")), "fremde Dateien im Ordner bleiben")
pc.report(base, {"dir": d, "v": "dddd", "files": ["a"], "mb": 9.5, "backup": PI["backup"]}, opener)
rep = [c for c in calls if isinstance(c, dict)][-1]
check(rep["op"] == "programs_report" and rep["v"] == "dddd" and rep["mb"] == 9.5, "Meldung an den Pi")

# Pi: Stand der Pakete aendert sich mit einer Datei
pd = tempfile.mkdtemp(prefix="s2l_pk_")
for n in ("show.py", "install_pi.sh", "fixtures.yaml"):
    open(os.path.join(pd, n), "w").write("x")
os.makedirs(os.path.join(pd, "shows"))
v1 = pakete.stand(base=pd, mac_dirs=(), win_dirs=())
open(os.path.join(pd, "shows", "_x.json"), "w").write("{}")
open(os.path.join(pd, "settings.json"), "w").write("{}")
check(pakete.stand(base=pd, mac_dirs=(), win_dirs=()) == v1, "Stand: Zustandsdateien und Shows zaehlen nicht")
time.sleep(0.01)
open(os.path.join(pd, "show.py"), "w").write("neu, laenger")
check(pakete.stand(base=pd, mac_dirs=(), win_dirs=()) != v1, "Stand: neue Programmdatei -> neuer Stand")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('"/download/stand"' in api and 'op == "programs_report"' in api and '"/api/sm/programs"' in api, "Pi: Stand, Meldung, Karte")
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check('id="prstick"' in wp and "loadPrStick();" in wp, "Karte Programme am Stick auf Vorab-Laeufe")
sb = open(os.path.join(ROOT, "mac", "mixxx_bridge", "stems_backup.py"), encoding="utf-8").read()
check("self.programs()" in sb and "programs_copy.sync(" in sb, "laeuft im Sicherungslauf (alle 30 min, Stick-Sperre beachtet)")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("programs_copy.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert programs_copy.py")
import nas_mirror  # noqa: E402
check("Light-Butler-Programme" in nas_mirror.BESIDE, "Spiegeln nimmt den Ordner mit")
check("Light-Butler-Broschuere.pdf" in r["files"], "Broschuere in der Meldung")
check('"/download/broschuere.pdf"' in api and os.path.isfile(os.path.join(ROOT, "pi", "static", "Light-Butler-Broschuere.pdf")), "Broschuere am Pi zum Herunterladen")
finish("test_programme_stick")
