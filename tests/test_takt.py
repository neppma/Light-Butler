"""Schnittstelle /api/takt (Wunsch von Markus 23.11.2026, Auftrag aus dem Projekt Bravia-Dashboard): der Fernseher zeigt
Muster im Takt. Nur lesen; beat ist die Zaehlzeit der Show (Vielfaches von quantum = die Eins), zeit der Augenblick dazu
in Unix-ms; das Licht bleibt Bild fuer Bild gleich."""
import json
import re
import time
import urllib.request

from _common import build, check, finish

rig, sh = build()
d = sh.takt()
for k in ("version", "aktiv", "spielt", "bpm", "quantum", "beat", "zeit", "jetzt", "farben", "helligkeit"):
    check(k in d, "Feld %s da" % k)
check(d["version"] == 1 and d["aktiv"] is False and d["spielt"] is False, "vor der Musik: aktiv false, trotzdem eine Antwort")

t = 1795423000.0
for i in range(40 * 40):                         # 40 s Simulator
    sh.update(t + i * 0.025)
now = t + 1600 * 0.025
d = sh.takt(wall=now)
check(d["aktiv"] and d["spielt"] and 60 < d["bpm"] < 200, "Musik laeuft: aktiv, spielt, Tempo %s" % d["bpm"])
raw = sh.takt_mark[0] + (now - sh.takt_mark[1]) * d["bpm"] / 60
check(d["quantum"] in (3, 4) and abs(d["zeit"] - now * 1000) < 0.2 and abs(d["beat"] - raw) < 0.3,
      "beat mit Nachkommastellen zum Zeitpunkt zeit, nahe am erkannten Schlag (%.2f / %.2f)" % (d["beat"], raw))
check(1 <= len(d["farben"]) <= 4 and all(re.match(r"^#[0-9a-f]{6}$", c) for c in d["farben"]), "Farben als #rrggbb: %s" % d["farben"])
check(0.0 <= d["helligkeit"] <= 1.0, "Helligkeit 0..1")
check(abs(d["jetzt"] - time.time() * 1000) < 2000, "jetzt = Uhr beim Absenden")
b1, z1 = d["beat"], d["zeit"]
for i in range(1600, 1600 + 40 * 5):              # 5 s weiter
    sh.update(t + i * 0.025)
d2 = sh.takt(wall=t + 1800 * 0.025)
pred = b1 + (d2["zeit"] - z1) * d["bpm"] / 60000
check(abs(d2["beat"] - pred) < 1.0, "beat waechst mit dem Tempo: %.2f statt %.2f" % (d2["beat"], pred))

check(d2["abschnitt"] in ("normal", "break", "aufbau", "drop") and 0.0 <= d2["energie"] <= 1.0, "Abschnitt und Energie: %s, %s" % (d2["abschnitt"], d2["energie"]))
check("naechsterDrop" not in d2, "ohne Analyse (Mixxx-Plan): kein naechsterDrop")
# Abschnitt wechselt: gilt ab dem naechsten Taktanfang (die Eins)
from takt import to_bar                           # noqa: E402
tt = t + 1800 * 0.025
q = d2["quantum"]
check("abschnittSeit" in d2, "abschnittSeit immer dabei, auch bei normal")
sh._enter("build", tt)
d3 = sh.takt(wall=tt)
exp = to_bar(sh.takt_clock.at(tt), q)
check(d3["abschnitt"] == "aufbau" and d3["abschnittSeit"] == exp and d3["abschnittSeit"] % q == 0,
      "Aufbau ab Taktanfang %s" % d3.get("abschnittSeit"))
sh._enter("gap", tt)
check(sh.takt(wall=tt)["abschnitt"] == "break", "kurze Pause vor dem Drop zaehlt als break")
sh._enter("drop", tt)
seit = sh.takt(wall=tt)["abschnittSeit"]
spb = 60.0 / sh.takt_clock.bpm
t15 = tt + (seit + 15 - sh.takt_clock.at(tt)) * spb          # 15 Schlaege nach Beginn des Drops
check(sh.takt(wall=tt + 0.1)["abschnitt"] == "drop" and sh.takt(wall=t15)["abschnitt"] == "drop",
      "Drop mindestens 4 Takte (nach 15 Schlaegen noch drop)")
dn = sh.takt(wall=tt + 60)
check(dn["abschnitt"] == "normal" and dn["abschnittSeit"] >= seit + 16 and dn["abschnittSeit"] % q == 0,
      "danach normal ab einem Taktanfang (%s, Drop ab %s)" % (dn["abschnittSeit"], seit))
# Ereignis-Zaehler: jeder Wechsel zaehlt, auch ein kurzer Break zwischen zwei Abfragen
e0 = sh.takt(wall=tt + 60)["ereignis"]           # Drop vorbei -> normal (zaehlt schon)
sh._enter("normal", tt + 60)
check(sh.takt(wall=tt + 60)["ereignis"] == e0, "Drop vorbei, dann normal: derselbe Wechsel, keine Doppelzaehlung")
sh._enter("break", tt + 61)
sh._enter("normal", tt + 62)                     # kurzer Break, keine Abfrage dazwischen
check(sh.takt(wall=tt + 62)["ereignis"] == e0 + 2, "kurzer Break geht nicht verloren (+2)")
sh._enter("drop", tt + 63)
e1 = sh.takt(wall=tt + 63)["ereignis"]
sh._enter("break", tt + 63.3)                    # Drop noch nicht vorbei, gleich Break
check(sh.takt(wall=tt + 63.3)["ereignis"] == e1 + 1, "Drop direkt in Break: +1")
check(sh.takt(wall=tt)["quelleAbschnitt"] == "live", "ohne Analyse: live am Ton erkannt")
# Mixxx kennt den naechsten Drop in 8 s
sh.mx, sh.mx_tempo_on = {"connected": True, "plan": True, "next": [{"type": "build", "in": 2.0}, {"type": "drop", "in": 8.0}]}, True
d4 = sh.takt(wall=tt)
exp = round(sh.takt_clock.at(tt + 8.0))
check(d4.get("naechsterDrop") == exp, "naechsterDrop = Schlag in 8 s: %s statt %s" % (d4.get("naechsterDrop"), exp))
check(d4["quelleAbschnitt"] == ("analyse" if sh.cfg["mixxx_light"] > 0.5 else "live"), "Quelle folgt der Einstellung mixxx_light")
sh.cfg.set("mixxx_light", 1)
check(sh.takt(wall=tt)["quelleAbschnitt"] == "analyse", "Licht nach der Analyse: analyse")
sh.cfg.set("mixxx_light", 0)
check(sh.takt(wall=tt)["quelleAbschnitt"] == "live", "Analyse nur angezeigt: live")
sh.mx, sh.mx_tempo_on = None, False

# Takt-Uhr allein: glaettet die Schwankung der Erkennung, meldet erst stabiles Tempo
import random                                     # noqa: E402
from takt import TaktClock                        # noqa: E402
rnd = random.Random(3)
ck, bpm, errs_raw, errs = TaktClock(), 125.0, [], []
for n in range(200):
    true_t = 100.0 + n * 60 / bpm
    ck.beat(n, true_t + rnd.uniform(-0.06, 0.06), bpm + rnd.uniform(-0.4, 0.4))
    if n > 20:
        errs.append(abs(ck.at(true_t + 0.2) - (n + 0.2 * bpm / 60)))
check(max(errs) < 0.08 and sum(errs) / len(errs) < 0.04, "Uhr ruhig: mittel %.3f, hoechstens %.3f Schlaege daneben" % (sum(errs) / len(errs), max(errs)))
ck = TaktClock()
for n in range(4):
    ck.beat(n, 10 + n * 60 / 166.0, 166.0)       # Liedanfang: doppelt erkanntes Tempo
for n in range(4, 30):
    ck.beat(n, 11.5 + (n - 4) * 0.48, 125.0)
check(not ck.stable(11.5 + 2.0) and ck.stable(11.5 + 3.5) and abs(ck.bpm - 125) < 0.5, "Tempo-Sprung am Liedanfang: erst nach 3 s stabil")
check(not ck.stable(11.5 + 25 * 0.48 + 5), "ohne Schlag 4 s: nicht mehr aktiv")
check(to_bar(309, 4) == 308 and to_bar(294, 4) == 296 and to_bar(7, 3) == 6, "auf Taktanfang runden")

# Effekt-Tasten (23.11.2026): gedrueckt, ab welchem Schlag, wie oft
ft = [t + 2000 * 0.025]


def frames(n):
    for _ in range(n):
        ft[0] += 0.025
        sh.update(ft[0])


d = sh.takt(wall=ft[0])
check(set(d["tasten"]) == {"strobe", "wow", "sonnenbrille", "freeze", "blackout", "nebel"} and not any(d["tasten"].values()),
      "alle Tasten immer dabei, keine gedrueckt")
check(d["tastenSeit"] == {} and all(v == 0 for v in d["tastenZaehler"].values()), "noch nie gedrueckt")
for name, key in (("blitz", "strobe"), ("allbright", "sonnenbrille"), ("freeze", "freeze"), ("blackout", "blackout")):
    sh.command({"hold": {"name": name, "on": True}})
    frames(3)
    d = sh.takt(wall=ft[0])
    check(d["tasten"][key] and d["tastenZaehler"][key] == 1 and key in d["tastenSeit"], "%s gedrueckt: true, Zaehler 1, Schlag %s" % (key, d["tastenSeit"].get(key)))
    sh.command({"hold": {"name": name, "on": False}})
    frames(1)
    d = sh.takt(wall=ft[0])
    check(not d["tasten"][key] and key not in d["tastenSeit"], "%s losgelassen: sofort false" % key)
    sh.command({"hold": {"name": name, "on": True}})
    frames(1)
    sh.command({"hold": {"name": name, "on": False}})
    frames(1)
    check(sh.takt(wall=ft[0])["tastenZaehler"][key] == 2, "%s kurz angetippt: Zaehler 2" % key)
sh.command({"build": True})
frames(3)
check(sh.takt(wall=ft[0])["tasten"]["wow"], "WOW! gedrueckt")
sh.command({"build": False})
frames(2)
check(not sh.takt(wall=ft[0])["tasten"]["wow"] and sh.takt(wall=ft[0])["tastenZaehler"]["wow"] == 1, "WOW! losgelassen, einmal gezaehlt")
sh.held["fog"] = time.time()                      # Nebeltaste (rote Taste) gehalten
frames(1)
check(sh.takt(wall=ft[0])["tasten"]["nebel"], "Nebeltaste gedrueckt")
sh.held.pop("fog")
frames(1)
check(not sh.takt(wall=ft[0])["tasten"]["nebel"] and sh.takt(wall=ft[0])["tastenZaehler"]["nebel"] == 1, "Nebeltaste losgelassen")

# Liedtext fuer den Fernseher (23.11.2026): liedId, liedPosition, lyrics und /api/lyrics
import types                                      # noqa: E402
LINES = [[12.4, "Erste Zeile"], [16.85, "Zweite Zeile"], [21.1, ""], [24.0, "Dritte Zeile"]]


class FakeCache:
    def __init__(self):
        self.asked = []

    def get_entry(self, title, dur, now=None):
        self.asked.append((title, dur))
        return {"lines": LINES, "plain": ""} if "Calling" in title else {"lines": [], "plain": ""}


d = sh.takt(wall=ft[0])
check("liedId" not in d and d["lyrics"] is False, "ohne Lied: keine liedId, lyrics false")
L = sh.lyrics_api(wall=ft[0])
check(L["version"] == 1 and L["zeilen"] == [] and L["synchron"] is False, "/api/lyrics ohne Lied: 200 mit leeren Zeilen")
sh.lyric_cache = FakeCache()
sh.cfg.set("lyrics_auto", 1)
w0 = ft[0]
sh.mx = {"connected": True, "playing": True, "deck": 1, "title": "Hannah Wants - Calling", "dur": 210.0, "pos_f": 70.0, "t": w0, "rate": 1.0}
d1 = sh.takt(wall=w0 + 3.42)
check(d1["lyrics"] and len(d1["liedId"]) == 8 and abs(d1["liedPosition"] - 73.42) < 0.01, "Mixxx: liedId, liedPosition 73.42, lyrics true")
d2 = sh.takt(wall=w0 + 5.42)
check(d2["liedId"] == d1["liedId"] and abs(d2["liedPosition"] - d1["liedPosition"] - 2.0) < 0.01, "liedPosition steigt je Sekunde um 1")
L = sh.lyrics_api(wall=w0 + 5.42)
check(L["liedId"] == d1["liedId"] and L["synchron"] and L["quelle"] == "lrclib" and L["titel"] == "Hannah Wants – Calling", "/api/lyrics passt zu /api/takt")
check(L["zeilen"][0] == {"t": 12.4, "text": "Erste Zeile"} and L["zeilen"][2] == {"t": 21.1, "text": ""}, "Zeilen mit Zeit, leer = Pause")
sh.mx = dict(sh.mx, title="Anderer - Titel", dur=180.0)
d3 = sh.takt(wall=w0 + 6)
check(d3["liedId"] != d1["liedId"] and d3["lyrics"] is False, "Liedwechsel: neue liedId, ohne Text lyrics false")
sh.mx = None
sh.radio = types.SimpleNamespace(song=lambda: {"artist": "Hannah Wants", "title": "Calling", "genre": "", "station": "X", "uuid": "", "done": True})
d4 = sh.takt(wall=w0 + 7)
L = sh.lyrics_api(wall=w0 + 7)
check("liedPosition" not in d4 and d4["lyrics"] and L["synchron"] is False and "t" not in L["zeilen"][0],
      "Internetradio: keine liedPosition, Text ohne Zeiten")
sh.radio = None
LP = {"title": "Calling", "artist": "Hannah Wants", "genre": "", "path": "/m/c.mp3", "dur": 210.0, "pos": 40.5}
sh.local = types.SimpleNamespace(panel=lambda: LP, song=lambda: dict(LP, album=""))
d5 = sh.takt(wall=w0 + 8)
check(abs(d5["liedPosition"] - 40.5) < 0.01 and sh.lyrics_api(wall=w0 + 8)["synchron"], "Musik-DB im Browser: Position und Zeilen")
sh.local = None
sh.cfg.set("lyrics_auto", 0)
sh.mx = {"connected": True, "playing": True, "deck": 1, "title": "Hannah Wants - Calling", "dur": 210.0, "pos_f": 70.0, "t": w0, "rate": 1.0}
n = len(sh.lyric_cache.asked)
check(sh.takt(wall=w0 + 9)["lyrics"] is False and len(sh.lyric_cache.asked) == n, "Liedtext automatisch aus: nichts geholt")
sh.mx, sh.lyric_cache = None, None

# Dynamik-Stufe (23.11.2026): dieselbe Stufe wie das Licht
frames(2)
d = sh.takt(wall=ft[0])
check(d.get("dynamik") == {0: "langsam", 1: "langsam", 2: "mittel", 3: "schnell"}[sh.eff_tier()] and d["dynamikSeit"] % d["quantum"] == 0,
      "dynamik wie eff_tier (%s), ab Taktanfang %s" % (d.get("dynamik"), d.get("dynamikSeit")))
for speed, want in (("slow", "langsam"), ("mid", "mittel"), ("fast", "schnell")):
    sh.auto_speed = speed
    sh.state = "normal"
    frames(1)
    check(sh.takt(wall=ft[0]).get("dynamik") == want, "Tempo-Knopf %s: dynamik %s sofort" % (speed, want))
sh.auto_speed = "slow"
sh.state = "drop"
frames(1)
check(sh.takt(wall=ft[0]).get("dynamik") == "schnell", "Drop: schnell wie das Licht")
sh.state = "idle"
frames(1)
check("dynamik" not in sh.takt(wall=ft[0]) and "dynamikSeit" not in sh.takt(wall=ft[0]), "ohne Musik: dynamik fehlt")
sh.auto_speed, sh.state = None, "normal"
frames(2)

sh.auto_color = "white"
check(sh.takt()["farben"] == ["#ffffff"], "Weiss")
import scenes                                     # noqa: E402
sh.auto_color, sh.auto_colors = None, list(scenes.COLORS)[:2]
check(len(sh.takt()["farben"]) == 2, "gewaehlte Farben: so viele wie gewaehlt")
sh.auto_colors = []
sh.command({"blackout": True})
check(sh.takt()["helligkeit"] == 0.0 and not sh.takt()["spielt"], "BLACKOUT: Helligkeit 0, spielt nicht")
sh.command({"blackout": False})

# Route im Panel: JSON, CORS fuer die Vorschau, no-store
import webpanel                                   # noqa: E402
srv = webpanel.start(sh, 0)
port = srv.server_address[1] if srv is not None and hasattr(srv, "server_address") else None
if port:
    with urllib.request.urlopen("http://127.0.0.1:%d/api/takt" % port, timeout=5) as r:
        body, hd = json.loads(r.read()), r.headers
    check(body["version"] == 1, "GET /api/takt liefert JSON")
    with urllib.request.urlopen("http://127.0.0.1:%d/api/lyrics" % port, timeout=5) as r:
        lb, lh = json.loads(r.read()), r.headers
    check(lb["version"] == 1 and "zeilen" in lb and lh.get("Access-Control-Allow-Origin") == "*" and lh.get("Cache-Control") == "no-store",
          "GET /api/lyrics: JSON, CORS *, no-store")
    check(hd.get("Access-Control-Allow-Origin") == "*" and hd.get("Cache-Control") == "no-store"
          and hd.get("Content-Type", "").startswith("application/json"), "Header: CORS *, no-store, JSON")
else:
    src = open(webpanel.__file__, encoding="utf-8").read()
    check('"/api/takt"' in src and '"Access-Control-Allow-Origin": "*"' in src, "Route /api/takt mit CORS im Panel")
# Gruppen-Regler API (Wunsch 23.11.2026): daempft masterDim und helligkeit, kein Licht
rig, sh = build()
t = 1795426000.0
for i in range(200):
    sh.update(t + i * 0.025)
sh.command({"master": 0.8})
h1 = sh.takt()["helligkeit"]
sh.command({"glevel": {"api": 0.5}})
d = sh.takt()
check(d["masterDim"] == 40, "Dimmer 80 %%, API 50 %%: masterDim 40 (%s)" % d["masterDim"])
check(abs(d["helligkeit"] - round(h1 * 0.5, 2)) <= 0.011, "helligkeit halb so gross (%s statt %s)" % (d["helligkeit"], h1))
check("api" in sh.snapshot()["glevel"], "API-Regler im Stand (Panel)")
import random  # noqa: E402

frames = []
for api in (1.0, 0.0):                            # zwei gleiche Shows, eine mit API-Regler 0: Bild fuer Bild gleich
    random.seed(5)
    rA, sA = build(seed=2)
    sA.command({"glevel": {"api": api}})
    fr = []
    for i in range(300):
        sA.update(t + i * 0.025)
        fr.append(b"".join(bytes(rA.render_all()[k]) for k in sorted(rA.render_all())))
    frames.append(fr)
check(frames[0] == frames[1], "API-Regler aendert kein Licht (300 Bilder gleich)")
sh.command({"glevel_reset": True})
check(sh.takt()["masterDim"] == 80, "Alle auf 100 %: API wieder 100")

# spielt ohne Tempo (Eichstueck 23.11.2026): Musik ohne Beat (Applaus, Melodie) ist trotzdem Musik
from takt import TaktClock  # noqa: E402
rig, sh = build()
t0 = 1795424000.0
for i in range(40 * 20):
    sh.update(t0 + i * 0.025)
sh.takt_clock = TaktClock()                       # kein Tempo bekannt, Musik laeuft weiter
d = sh.takt(t0 + 800 * 0.025)
check(d["spielt"] is True and d["aktiv"] is False, "Musik ohne bekanntes Tempo: spielt true, aktiv false")
# strobeHz und wowProzent (Wunsch Bravia-Dashboard 23.11.2026): nur solange die Taste aktiv ist
rig, sh = build()
d = sh.takt()
check("strobeHz" not in d and "wowProzent" not in d, "ohne Strobe und WOW!: Felder fehlen")
sh.command({"blitz_hz": 6.7})
sh.command({"blitz": True})
d = sh.takt()
check(abs(d.get("strobeHz", 0) - sh._blitz_rate()) < 0.01 and d["strobeHz"] > 0, "strobeHz = Blitze pro Sekunde des Lichts (%s)" % d.get("strobeHz"))
sh.strobe = False
check(sh.takt()["strobeHz"] <= 3.0, "ohne Strobe-Erlaubnis hoechstens 3 wie das Licht")
sh.command({"blitz": False})
check("strobeHz" not in sh.takt(), "Strobe los: strobeHz fehlt")
t = 1795425000.0
for i in range(200):                              # 5 s Musik, damit WOW! ein Tempo hat
    sh.update(t + i * 0.025)
sh.command({"build": True})
check(sh.takt().get("wowProzent") == 0, "WOW! gedrueckt: 0 %% (%s)" % sh.takt().get("wowProzent"))
t += 200 * 0.025
for i in range(2, 200):
    sh.command({"build_keep": True})
    sh.update(t + i * 0.025)
w = sh.takt().get("wowProzent")
check(isinstance(w, int) and 0 < w <= 100 and w == int(round(sh.build_p * 100)), "WOW! steigt, gleicher Wert wie das Licht (%s %%)" % w)
sh.command({"build": False})
sh.update(t + 201 * 0.025)
check("wowProzent" not in sh.takt(), "WOW! los: wowProzent fehlt")
# masterDim (Wunsch Bravia-Dashboard 23.11.2026): Stand des General Dimmers in %, immer dabei, sofort neu
rig, sh = build()
check(sh.takt()["masterDim"] == 100, "masterDim ohne Musik dabei: 100")
for v, want in ((0.65, 65), (0.0, 0), (0.333, 33), (1.0, 100)):
    sh.command({"master": v})
    check(sh.takt()["masterDim"] == want, "General Dimmer %.3f: masterDim %d" % (v, want))
sh.command({"master": 0.5})
sh.command({"blackout": True})
check(sh.takt()["masterDim"] == 50, "BLACKOUT: masterDim bleibt der Reglerstand")
finish("test_takt")
