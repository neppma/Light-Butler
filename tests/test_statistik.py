"""Seite Statistik (/stats, runder Knopf neben dem Zahnrad): Die Mac-Bruecke schickt alle 30 s die Statistik der
Bibliothek (Titel, davon analysiert, Energie E1-E9, Hotcues, Tempo, Dateitypen, Spielzeit, je Genre Anzahl und
analysiert). Der Pi rechnet daraus die Zahlen je Stil und merkt sich die seit dem Start gespielten Titel.
Dazu: im Stil Weihnachten bleibt das UV-Licht aus."""
import json
import os
import subprocess
import sys
import tempfile
import time

from _common import ROOT, build, check, finish, Clock

import webpanel
from mixxx_link import MixxxLink, clean_stats

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from mixxx_bridge import Forwarder, track_key    # noqa: E402

# ---- Mac: Statistik der Bibliothek --------------------------------------------------------------------------------
d = tempfile.mkdtemp()
lib = [{"duration": 200.0, "bpm": 128.0, "kid": 1, "genre": "Techno", "comment": "8A - Energy 9", "cues": [1.0], "filetype": "mp3"},
       {"duration": 180.0, "bpm": 95.0, "kid": 2, "genre": "Weihnachten", "comment": "1A - Energy 2", "cues": [], "filetype": "MP3"},
       {"duration": 3600.0, "bpm": 0.0, "kid": 0, "genre": "", "filetype": "mp4"}]
open(os.path.join(d, track_key(200.0, 128.0, 1) + ".json"), "w").write("{}")
fw = Forwarder(lib, None, None, analysis_dir=d, analyze=False)
st = fw.stats()
check(st["type"] == "stats" and st["n"] == 3 and st["a"] == 1, "3 Titel, 1 analysiert (Datei im Analyse-Ordner)")
check(st["e"][8] == 1 and st["e"][1] == 1 and st["e"][9] == 1, "Energie: E9, E2 und einer ohne")
check(st["cu"] == 1 and st["ft"] == {"mp3": 2, "mp4": 1} and st["h"] == 1.1, "Hotcues, Dateitypen, Stunden")
check(st["bpm"][6] == 1 and st["bpm"][3] == 1 and st["bpm"][0] == 1, "Tempo in 10er-Schritten (128 -> 120-129, 95 -> 90-99, 0 -> unter 70)")
check(st["g"] == [["Techno", 1, 1], ["Weihnachten", 1, 0]], "je Genre Anzahl und analysiert")
check(len(json.dumps(Forwarder([dict(lib[0], genre=f"Genre {i}") for i in range(300)], None, None, analysis_dir=d,
                                 analyze=False).stats())) < 9000, "auch mit vielen Genres ein kleines UDP-Paket")

# ---- Pi: empfangen, pruefen, je Stil ---------------------------------------------------------------------------------
lk = MixxxLink(0)
lk.feed(dict(st, g=st["g"] + ["Unsinn", ["x", "y", 1]], n=-5), 1000.0)
check(lk.stats["n"] == 0 and len(lk.stats["g"]) == 2 and lk.stats_t == 1000.0, "Pi: Statistik geprueft (Unsinn verworfen)")
check(clean_stats({"e": [1, "x", 3]})["e"] == [1, 0, 3], "Zahlenlisten: Unsinn = 0")

rig, sh = build()
check(sh.stats_info()["lib"] is None, "ohne Mixxx: noch keine Daten")
lk.stats, lk.stats_t = clean_stats(st), time.time()
sh.mixxx = lk
info = sh.stats_info()
check(info["styles"]["club"] == [1, 1] and info["styles"]["weihnachten"] == [1, 0], "je Stil: Club 1 (analysiert), Weihnachten 1")
check(info["nostyle"] == [1, 0], "ohne Genre: kein Stil")
sh.command({"genre_style": {"genre": "Techno", "style": "rock"}})
check(sh.stats_info()["styles"]["rock"] == [1, 1], "eigene Zuordnung zaehlt mit")

# ---- Pi: gespielte Titel ------------------------------------------------------------------------------------------------
sh.mixxx = None
mx = {"plan": True, "deck": 1, "playing": True, "title": "A - Eins", "genre": "Weihnachten", "lvl": 2}
sh.mx = dict(mx)
sh._note_played()
sh._note_played()
sh.mx = dict(mx, title="B - Zwei", genre="Techno", lvl=9)
sh._note_played()
sh.mx = dict(mx, title="C - Pause", playing=False)
sh._note_played()
pl = sh.stats_info()["played"]
check([p["title"] for p in pl] == ["B - Zwei", "A - Eins"], "gespielte Titel, neuester zuerst, nicht doppelt, nur hoerbar")
check(pl[1]["style"] == "weihnachten" and pl[0]["lvl"] == 9, "mit Stil und Energie")

# ---- Weihnachten ohne UV -----------------------------------------------------------------------------------------------
rig, sh = build()
sh.command({"style": "weihnachten"})
uv = []
Clock(sh).run(40, lambda t: uv.extend(fx.values["uv"] for fx in rig.fixtures if "uv" in fx.values))
check(uv and max(uv) == 0, "Stil Weihnachten: UV-Licht aus")
rig, sh = build()
uv = []
Clock(sh).run(40, lambda t: uv.extend(fx.values["uv"] for fx in rig.fixtures if "uv" in fx.values))
check(max(uv) > 0, "ohne Stil: UV wie bisher")
for key in ("club", "party", "rock", "ruhig"):                 # Fehler 01.11.2026: Stile ohne "uv" stuerzten ab (KeyError)
    rig, sh = build()
    sh.command({"style": key})
    Clock(sh).run(20)
    check(sh._style("uv", True) is True, f"Stil {key}: laeuft 20 s ohne Fehler, UV erlaubt")

# ---- Panel ---------------------------------------------------------------------------------------------------------------
p = webpanel.make_page()
check('<a id="statbtn" href="/stats"' in p and p.index('id="statbtn"') < p.index('id="setbtn"'), "runder Knopf links neben dem Zahnrad")
check('<body class="vstat">' in webpanel.stats_page() and "body.vstat #statsec{display:block}" in p, "eigene Seite /stats")
check("fetch('/api/stats')" in p and "setInterval(()=>{if(!document.hidden)loadStats()},10000)" in p, "Seite holt alle 10 s neu")
# Wunsch 12.11.2026: Vorab-Laeufe aus der Statistik in die Datenpflege (eigene Seite /musik/vorab)
_st = p[p.index('id="statsec"'):p.index('id="presec"')]
_pr = p[p.index('id="presec"'):p.index('id="apcsec"')]
check(all(k not in _st for k in ("lybulk", "mkbulk", "cvbulk", "stemstat", "stbulk")) and all(('id="' + k + '"') in _pr for k in ("lybulk", "mkbulk", "cvbulk", "stemstat", "stbulk")),
      "Vorab-Karten stehen nur noch auf der Seite Vorab-Laeufe")
check('<body class="vpre">' in webpanel.pre_page() and "body.vpre #presec{display:block}" in p and 'data-back="/musik/pflege"' in _pr, "eigene Seite, zurueck zur Datenpflege")
check("if(document.body.classList.contains('vpre')){loadPre()" in p and "loadLyBulk()" not in p[p.index("async function loadStats"):p.index("function loadPre")], "Statistik holt die Vorab-Laeufe nicht mehr")
_wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
_cj = open(os.path.join(ROOT, "pi", "static", "sm", "care.js"), encoding="utf-8").read()
check("if(bc.contains('vpre'))loadPre();if(bc.contains('vstat'))loadStats()}" in p, "Karten neu in der Sprache des Panels, sobald sie bekannt ist (vorher kurz Englisch)")
check('self.path == "/musik/vorab"' in _wp and '"h_pre"' in _wp and 'href="/musik/vorab">Öffnen</a>' in _cj, "Route und Knopf Oeffnen in der Datenpflege")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_statistik")
