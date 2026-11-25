"""/api/takt Erweiterung 8 (Wunsch Bravia-Dashboard 24.11.2026): szene, szeneSeit, effekt, bewegung; GET /api/liste mit
Szenen, Effekten des Effektbands und Bewegungsarten samt kurzer Beschreibung. Nur lesen, das Licht bleibt gleich."""
import json
import urllib.request

from _common import build, check, finish
import takt_liste  # noqa: E402

rig, sh = build()
t = 1795440000.0
for i in range(400):
    sh.update(t + i * 0.025)
d = sh.takt(t + 400 * 0.025)
check("szene" not in d and "szeneSeit" not in d, "AUTO ohne Szene: szene fehlt")
check(isinstance(d.get("bewegung"), str) and d["bewegung"] in takt_liste.MOVE_NAMES.values(), "bewegung nach der Musik: %s" % d.get("bewegung"))
names = dict(sh._eb_names())
check(d.get("effekt") is None or d["effekt"] in names.values(), "effekt ist ein Name des Effektbands (%s)" % d.get("effekt"))

sh.command({"scene": "Super Chill"})
for i in range(400, 440):
    sh.update(t + i * 0.025)
d = sh.takt(t + 440 * 0.025)
check(d.get("szene") == "Super Chill", "Szene von Hand: szene = Name")
check(isinstance(d.get("szeneSeit"), float) and d["szeneSeit"] <= d["beat"] + 0.01, "szeneSeit: Schlag, ab dem sie gilt")
check(d.get("bewegung") == "Ruhig", "Bewegung der Szene: Ruhig")
first = d["szeneSeit"]
sh.command({"scene": "Strobe White"})
for i in range(440, 480):
    sh.update(t + i * 0.025)
d = sh.takt(t + 480 * 0.025)
check(d.get("szene") == "Strobe White" and "bewegung" not in d, "Szene mit Stop: bewegung fehlt")
check(d["szeneSeit"] > first, "neue Szene: neues szeneSeit")
sh.command({"auto": True})
for i in range(480, 500):
    sh.update(t + i * 0.025)
check("szene" not in sh.takt(t + 500 * 0.025), "zurueck in AUTO: szene fehlt")

# Liste
L = takt_liste.liste(sh)
check(len(L["szenen"]) == len(sh.scene_defs) >= 30, "alle Szenen (%d)" % len(L["szenen"]))
check(all(x["beschreibung"] for x in L["szenen"] + L["effekte"] + L["bewegungen"]), "jede mit Beschreibung")
check(len(L["bewegungen"]) == 10, "alle Bewegungsarten")
sc = {x["name"]: x["beschreibung"] for x in L["szenen"]}
check("rot" in sc["rot"].lower() and "ruhig" in sc["rot"], "Szene rot: rot, ruhig (%s)" % sc["rot"])
check("Blitze" in sc["Strobe White"] and "Weiss" in sc["Strobe White"], "Strobe White: weiss, Blitze (%s)" % sc["Strobe White"])
check(takt_liste.eb_descr("Solid weiß").startswith("weiss") and takt_liste.eb_descr("Scanner").startswith("rot")
      and takt_liste.eb_descr("DEMO (Playlist)").startswith("wechselnde"), "Effektband-Namen gefunden (Umlaute, Zusaetze)")
known = [n for n in ["Austria", "Scanner", "Fairy", "Fire", "Fireworks Starburst", "Gravimeter", "Juggle", "Lightning",
                     "Meteor Smooth", "Midnoise", "Phased", "Popcorn", "Pride 2015", "Rain", "Scan", "Weihnachten",
                     "DJ Light", "Gravfreq", "Gravcenter", "Juggles", "DEMO (Playlist)", "Noisefire", "Noisemeter",
                     "Puddlepeak", "Ripple Peak", "M-Club (Playlist)", "Rot BPM", "Blink", "Solid blau", "Ripple Peak 2",
                     "Solid red", "strobo", "Android", "Solid grün", "Solid weiß", "M-Club Effekt (Playlist)", "Sparkle",
                     "Karussell", "Disco"] if takt_liste.eb_descr(n) == "Effekt des Effektbands"]
check(not known, "alle 39 Effekte des Effektbands beschrieben %s" % known)

import webpanel  # noqa: E402
srv = webpanel.start(sh, 0)
port = srv.server_address[1] if srv is not None and hasattr(srv, "server_address") else None
if port:
    with urllib.request.urlopen("http://127.0.0.1:%d/api/liste" % port, timeout=5) as r:
        body, hd = json.loads(r.read()), r.headers
    check(body["version"] == 1 and body["szenen"] and hd.get("Access-Control-Allow-Origin") == "*", "GET /api/liste: JSON, CORS")
finish("test_takt_szene")
