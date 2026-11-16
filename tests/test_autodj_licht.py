"""Licht folgt dem Auto-DJ (Wunsch von Markus, 08.11.2026): die Auto-DJ-Seite meldet ihre Decks (11 = A, 12 = B) und den Plan
aus der Analyse am Mac wie die Mixxx-Bruecke. Der Pi nimmt das lauteste Deck, das Panel zeigt "Auto-DJ". Ohne Auto-DJ bleibt
alles wie bisher."""
import os
import subprocess

from _common import PI, build, check, finish

import webpanel
from mixxx_link import AUTODJ_DECKS, MixxxLink

rig, sh = build()
link = MixxxLink(0)
now = 1000.0
cfg = sh.cfg
PLAN = {"type": "plan", "d": 11, "key": "/m/lied.mp3", "title": "A - Eins", "du": 200.0,
        "ev": [["drop", 64.0, 64.0, 0.8, ""], ["build", 48.0, 64.0, 0.5, "l"], ["boese", 1, 2], "x", ["gap", 100.0]], "en": [10, 50, 90], "cu": [32.0, 64.0],
        "genre": "House", "lvl": 8, "fp": "123:abc", "ki": 22}
DECK = {"d": 11, "tl": 1, "pl": 1, "pp": 0.2, "du": 200.0, "rr": 1.0, "vo": 1.0, "bp": 128.0, "bd": 0.5, "fb": 128.0, "fk": 22}

check(AUTODJ_DECKS == (11, 12), "Auto-DJ hat eigene Decks")
check(link.feed_autodj([PLAN, DECK], now) == 2, "Plan und Deck angenommen")
st = link.status(now, cfg)
check(st["src"] == "autodj" and st["deck"] == 11 and st["plan"] and st["title"] == "A - Eins" and st["lvl"] == 8, "Status: Quelle Auto-DJ mit Plan")
check(st["bar"]["ev"] and all(e[0] in ("drop", "build") for e in st["bar"]["ev"]), "unbekannte Ereignisse aus dem Browser verworfen")
check(abs(st["pos"] - 40.0) < 0.01 and st["bpm"] == 128.0 and st["phase"] is not None, "Stelle, Tempo und Beat-Phase wie bei Mixxx")
check(st["next"] and st["next"][0]["type"] == "build", "Vorhersage: Aufbau kommt")

# fremde oder unsinnige Meldungen
check(link.feed_autodj([{"d": 1, "pl": 1, "pp": 0.5}, {"d": 12, "type": "plan", "key": "", "info": "x" * 500}, "kaputt", None], now) == 1,
      "nur Decks 11/12 (Mixxx-Decks nicht ueber den Browser)")
check(link.feed_autodj("nicht-liste", now) == 0, "Unsinn: nichts")
link.feed_autodj([dict(DECK, d=12, vo=7, rr=99, pp=-3, du="x")], now)
d12 = link.decks[12]["d"]
check(d12["vo"] == 1.0 and d12["rr"] == 1.0 and d12["pp"] == 0.0 and d12["du"] == 0.0, "Werte begrenzt")

# Mixxx und Auto-DJ zugleich: das lautere Deck gilt
link2 = MixxxLink(0)
link2.feed({"type": "plan", "d": 1, "key": "k", "title": "M - Mixxx", "du": 240.0, "ev": [], "en": []}, now)
link2.feed({"d": 1, "pp": 0.1, "du": 240.0, "rr": 1.0, "bp": 120.0, "pl": 1, "tl": 1, "vo": 0.4}, now)
check(link2.status(now, cfg)["src"] == "mixxx", "nur Mixxx: Quelle Mixxx wie bisher")
link2.feed_autodj([PLAN, DECK], now)
check(link2.status(now, cfg)["src"] == "autodj", "Auto-DJ lauter: er gilt")
link2.feed_autodj([dict(DECK, pl=0)], now)
check(link2.status(now, cfg)["src"] == "mixxx", "Auto-DJ pausiert: wieder Mixxx")

# Pause und Ende wie bei Mixxx: kein Deck hoerbar, dann nach der Wartezeit nicht mehr verbunden
link3 = MixxxLink(0)
link3.feed_autodj([PLAN, dict(DECK, pl=0)], now)
s3 = link3.status(now, cfg)
check(s3["connected"] and s3["deck"] is None, "Pause: verbunden, kein Deck hoerbar (Ruhemodus wie bei Mixxx)")
check(not link3.status(now + 5.0, cfg)["connected"], "Fenster zu (nichts mehr): nach ein paar Sekunden nicht mehr verbunden")

# Panel
sh.mx = link.status(now, cfg)
check(sh._mx_public()["src"] == "autodj", "ans Panel: Quelle")
p = webpanel.make_page()
check("(ad?'Auto-DJ':'Mixxx')" in p and "m.deck===11?'A':'B'" in p, "Panel: Auto-DJ Deck A/B statt Mixxx")
check("(S.mx_name||'Mixxx')" in p, "Panel: Tempo-Quelle Auto-DJ")
js = open(os.path.join(PI, "static", "sm", "autodj.js"), encoding="utf-8").read()
html = open(os.path.join(PI, "static", "sm", "autodj.html"), encoding="utf-8").read()
check('id="olicht"' in html and "cmd('autodj_feed'" in js and "PAUSE_S = 30" in js, "Auto-DJ-Seite: Schalter und Meldungen an den Pi")
check(subprocess.run(["node", "--check", os.path.join(PI, "static", "sm", "autodj.js")], capture_output=True).returncode == 0, "autodj.js ohne Fehler")
api = open(os.path.join(PI, "showman", "api.py"), encoding="utf-8").read()
check('op == "autodj_feed"' in api and "feed_autodj" in api, "API: autodj_feed")
finish("test_autodj_licht")
