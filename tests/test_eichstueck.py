"""Eichstueck (Wunsch von Markus 23.11.2026): kuenstliches Pruefstueck mit festen Abschnitten (pi/eichstueck.py), Seite /eichen
spielt es im Browser und vergleicht /api/takt und /api/state mit den Sollwerten. Nur Ton und Lesen, aufs Licht wirkt nichts."""
import json
import os
import re
import subprocess
import urllib.request

import numpy as np

from _common import PI, build, check, finish
import eichstueck as E  # noqa: E402
from audio import Analyzer  # noqa: E402
from showman import eichen  # noqa: E402

# Abschnitte: lueckenlos, Sollwerte nur bekannte Felder
S = E.SECTIONS
check(S[0][0] == 0 and all(S[i][1] == S[i + 1][0] for i in range(len(S) - 1)) and E.DURATION == 180, "Abschnitte lueckenlos 0 bis 180 s")
check(all(set(w) <= {"spielt", "aktiv", "bpm", "abschnitt", "einsatz"} for *_, w in S), "Sollwerte nur spielt, aktiv, bpm, abschnitt, einsatz")
check(len({k for _, _, k, _, _ in S}) == len(S), "Schluessel eindeutig")

# Ton: fest (gleiche Datei), Stille wirklich still, Beat deutlich, ohne Beat nicht
x = E.build()
check(len(x) == E.DURATION * E.RATE and float(np.max(np.abs(x))) <= 0.9, "Laenge 180 s, nicht uebersteuert")
check(np.array_equal(x[:44100 * 40], E.build()[:44100 * 40]), "immer derselbe Ton (fester Zufall)")
for a, b, k, _, _ in S:
    if k.startswith("stille"):
        check(float(np.max(np.abs(x[a * E.RATE:b * E.RATE]))) == 0.0, "%s: ganz still" % k)
an = Analyzer(rate=E.RATE)
clar = {}
for i in range(0, len(x) - 512, 512):
    an.process(x[i:i + 512])
    t = i / E.RATE
    for a, b, k, _, _ in S:
        if a + 5 <= t < b:
            clar.setdefault(k, []).append(an.beat_clarity)
med = {k: float(np.median(v)) for k, v in clar.items()}
check(med["beat120"] > 0.6 and med["drop"] > 0.6, "Beat 120 und Drop: Schlag deutlich (%.2f, %.2f)" % (med["beat120"], med["drop"]))


def longest_clear(v, thr=0.35):
    """laengste Zeit (s) am Stueck ueber der Schwelle; je 512er-Block ein Wert"""
    best = run = 0
    for c in v:
        run = run + 1 if c >= thr else 0
        best = max(best, run)
    return best * 512 / E.RATE


for k in ("applaus", "melodie", "break", "ausklang"):
    check(med[k] < 0.2 and longest_clear(clar[k]) < 1.0,
          "%s ohne Beat: Klarheit %.2f, hoechstens 1 s ueber 0,35 (%.1f s)" % (k, med[k], longest_clear(clar[k])))
check(0.15 < med["weich95"] < 0.6, "weicher Beat: Grenzfall (%.2f)" % med["weich95"])

# fertige MP3 im Programm, passt zur Fassung
mp3 = os.path.join(PI, "static", "eichstueck.mp3")
check(os.path.isfile(mp3) and 2_000_000 < os.path.getsize(mp3) < 6_000_000, "static/eichstueck.mp3 da")
if os.path.exists("/usr/bin/afinfo"):
    out = subprocess.run(["/usr/bin/afinfo", mp3], capture_output=True, text=True).stdout
    m = re.search(r"estimated duration: ([\d.]+)", out)
    check(m and abs(float(m.group(1)) - E.DURATION) < 0.5, "MP3 dauert 180 s")

# Ergebnis vom Browser: nur bekannte Felder, Zahlen, kurze Texte
r = eichen.clean({"samples": [{"t": 1.5, "spielt": True, "aktiv": "ja", "bpm": 1e9, "abschnitt": "x" * 99, "boese": 1},
                              "kein dict"] + [{"t": 1}] * 5000, "ua": "<script>", "note": 5})
s0 = r["samples"][0]
check(s0["t"] == 1.5 and s0["spielt"] is True and s0["aktiv"] is None and s0["bpm"] is None and len(s0["abschnitt"]) == 40
      and "boese" not in s0, "Messwerte geprueft")
check(len(r["samples"]) <= eichen.MAX_SAMPLES and len(r["samples"]) > 3000 and r["note"] is None, "hoechstens MAX_SAMPLES, falsche Typen weg")

# Seite, Routen, Kopfleiste
SM = os.path.join(PI, "static", "sm")
html = open(os.path.join(SM, "eichen.html"), encoding="utf-8").read()
js = open(os.path.join(SM, "eichen.js"), encoding="utf-8").read()
check('class="s2lnav" data-back="/settings" data-cur="settings" data-title="h_eichen"' in html and "/static/sm/nav.js" in html, "Kopfleiste")
check("SM.playBar(audio" in js and "start: false" in js, "Abspiel-Leiste, ohne ab Hauptteil")
check(subprocess.run(["node", "--check", os.path.join(SM, "eichen.js")]).returncode == 0, "eichen.js ohne Syntaxfehler")
import webpanel  # noqa: E402
check('href="/eichen"' in webpanel.settings_page() and "h_eichen" in webpanel.NAV_KEYS, "Link in den Einstellungen")

rig, sh = build()
srv = webpanel.start(sh, 0)
port = srv.server_address[1] if srv is not None and hasattr(srv, "server_address") else None
if port:
    base = "http://127.0.0.1:%d" % port
    with urllib.request.urlopen(base + "/eichen", timeout=5) as rr:
        check(b"eichen.js" in rr.read(), "GET /eichen")
    req = urllib.request.Request(base + "/eichen/eichstueck.mp3", headers={"Range": "bytes=0-99"})
    with urllib.request.urlopen(req, timeout=5) as rr:
        check(rr.status == 206 and len(rr.read()) == 100 and rr.headers.get("Content-Type") == "audio/mpeg", "MP3 mit Range")
    body = json.dumps({"op": "eich_result", "samples": [{"t": 3.0, "spielt": False}], "ua": "test"}).encode()
    req = urllib.request.Request(base + "/api/sm/cmd", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as rr:
        check(json.loads(rr.read()).get("n") == 1, "Ergebnis angenommen")
    with urllib.request.urlopen(base + "/api/sm/eichen", timeout=5) as rr:
        d = json.loads(rr.read())
    check(len(d["sections"]) == len(S) and d["last"]["samples"][0]["t"] == 3.0 and d["grace"] == E.GRACE_S, "GET /api/sm/eichen: Abschnitte und letzter Durchlauf")
finish("test_eichstueck")
