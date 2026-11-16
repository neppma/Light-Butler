"""Lizenz (GPLv3), Seite Ueber Light-Butler und Sicherheitshinweis bei einer neuen Anlage (Wunsch 15.11.2026)."""
import io
import json
import os
import re
import subprocess
import tempfile
import zipfile

from _common import PI, check, finish

import pakete
import safety
import webpanel

ROOT = os.path.dirname(PI)
lic = open(os.path.join(PI, "LICENSE"), encoding="utf-8").read()
check("GNU GENERAL PUBLIC LICENSE" in lic and "Version 3, 29 June 2007" in lic and len(lic) > 30000, "pi/LICENSE: voller GPLv3-Text")
check(open(os.path.join(ROOT, "LICENSE"), encoding="utf-8").read() == lic, "LICENSE im Projekt gleich wie pi/LICENSE")

# Sicherheitshinweis: einmal pro Anlage
with tempfile.TemporaryDirectory() as d:
    check(safety.is_open(d) is True, "frisch aus dem Quelltext (keine settings.json): Hinweis offen")
    check(safety.is_open(d, simulate=True) is False, "Simulator: kein Hinweis")
    open(os.path.join(d, "settings.json"), "w").write("{}")
    check(safety.is_open(d) is False, "bestehende Anlage ohne sicherheit.json: kein Hinweis")
    open(os.path.join(d, "sicherheit.json"), "w").write('{"ok": false}\n')
    check(safety.is_open(d) is True and safety.is_open(d, simulate=True) is True, "Installation legt ok:false an: Hinweis offen")
    safety.confirm(d, now=1)
    check(json.load(open(os.path.join(d, "sicherheit.json"))) == {"ok": True, "t": 1} and safety.is_open(d) is False, "Verstanden: fuer die ganze Anlage gemerkt")
    open(os.path.join(d, "sicherheit.json"), "w").write("kaputt")
    check(safety.is_open(d) is False, "kaputte Datei: kein Hinweis (nie blockieren)")

for f in ("install_pi.sh", "install_lightbutler_mac.sh", "install_windows.ps1"):
    t = open(os.path.join(PI, f), encoding="utf-8").read()
    check("sicherheit.json" in t and "false" in t, f"{f}: neue Anlage bekommt den Hinweis")
exe = open(os.path.join(ROOT, "windows", "light_butler_exe.py"), encoding="utf-8").read()
check('sicherheit.json' in exe and '{"ok": false}' in exe, "Light-Butler.exe: neue Anlage bekommt den Hinweis")
sh = open(os.path.join(PI, "show.py"), encoding="utf-8").read()
check('if d.get("safety_ok"):' in sh and "safety.confirm(" in sh and '"safety_open": self.safety_open' in sh
      and "safety.is_open(" in sh and "simulate=a.simulate" in sh, "Show: Status safety_open, Befehl safety_ok")

page = webpanel.make_page()
check("function drawSafety()" in page and "drawSafety();" in page and "c({safety_ok:1})" in page and "href=\"/about\"" in page,
      "Panel: Fenster mit Verstanden und Link zur Seite Ueber")
js = page.split("<script>")[1].split("</script>")[0] if "<script>" in page else ""
for k in ("sf_title", "sf_intro", "sf_strobe", "sf_laser", "sf_fog", "sf_out", "sf_rig", "sf_gpl", "sf_ok", "sf_more", "h_about"):
    check(k in open(os.path.join(PI, "texts.py"), encoding="utf-8").read(), f"Text {k} (DE/EN)")

about = open(os.path.join(PI, "static", "sm", "about.html"), encoding="utf-8").read()
check('class="s2lnav" data-back="/settings" data-cur="about" data-title="h_about"' in about, "Seite Ueber: Kopfleiste")
check("https://github.com/neppma/Light-Butler" in about and "github.com/neppma/Light-Butler" in pakete.COPYRIGHT, "Verweis auf den Quelltext")
check("Programmiert mit Unterstützung von KI (Claude von Anthropic)" in about and "Claude von Anthropic" in pakete.COPYRIGHT, "Hinweis auf KI-Unterstuetzung")
check(all(x in about for x in ("Spotify", "Deezer", "Shazam", "iTunes", "MusicBrainz", "LRCLIB", "Anthropic")) and "Dienste im Internet" in about, "Markennamen und Dienste im Internet")
check("Namen anderer Hersteller" in about and all(x in about for x in ("Ableton Link", "HomeMatic", "AKAI APC mini", "ROLI LUMI Keys", "Art-Net")), "Herstellernamen nach Kategorien")
check("Copyright © 2026 Markus Nepp" in about and "lightbutler@gmx.at" in about and "GPLv3" in about, "Copyright, Projekt-Mail, Lizenz")
check("markus.nepp" not in about and "markus.nepp" not in lic, "keine private Adresse")
check("ohne jede Gewährleistung" in about and "Inter" in about and "Mixxx" in about, "ohne Gewaehrleistung, fremde Bestandteile")
check('path == "/about"' in open(os.path.join(PI, "webpanel.py"), encoding="utf-8").read() and "/LICENSE" in about + open(os.path.join(PI, "static", "sm", "about.js"), encoding="utf-8").read(),
      "Routen /about und /LICENSE")
check("h_about" in webpanel.NAV_KEYS and "['about', '/about', 'h_about']" in open(os.path.join(PI, "static", "sm", "nav.js"), encoding="utf-8").read(),
      "Menue ☰: Ueber Light-Butler")
check('<a class="seclink" href="/about"><span data-tx="h_about">' in page, "Einstellungen: Link ganz unten")
check(re.match(r"^\d{4}-\d{2}-\d{2}$", webpanel.program_stand()) is not None, "Stand: Datum der Programme")

for f in ("mac_zip", "win_zip", "pi_zip", "windows_zip", "windows_music_zip", "mac_full_zip"):
    z = zipfile.ZipFile(io.BytesIO(getattr(pakete, f)()))
    top = z.namelist()[0].split("/")[0]
    check(top + "/LICENSE" in z.namelist() and "Markus Nepp" in z.read(top + "/LIESMICH.txt").decode("utf-8", "replace"),
          f"{f}: LICENSE und Copyright im LIESMICH")

r = subprocess.run(["node", "--check", os.path.join(PI, "static", "sm", "about.js")], capture_output=True, text=True)
check(r.returncode == 0, "about.js: node --check " + r.stderr[:200])
# Wunsch 15.11.2026: Programme, mit denen der Light-Butler nichts zu tun hat, kommen in keinem sichtbaren Text vor
import glob as _glob, re as _re
_vis = [os.path.join(PI, n) for n in ("texts.py", "settings.py")] + _glob.glob(os.path.join(PI, "static", "sm", "*.html")) \
    + _glob.glob(os.path.join(PI, "static", "sm", "*.js")) + [os.path.join(os.path.dirname(PI), "docs", n) for n in ("HANDBUCH.md", "MANUAL_EN.md", "TECHNIK.md", "TECHNICAL_EN.md")]
_hit = [os.path.basename(f) for f in _vis if _re.search(r"(?i)mixed.?in.?key|serato", open(f, encoding="utf-8").read())]
check(not _hit, f"kein Mixed In Key, kein Serato in Panel und Handbuechern ({_hit})")
finish("test_lizenz_sicherheit")
