"""Genre-Stile: Das Genre aus Mixxx gibt in AUTO den Stil vor (Farbpalette, Tempo der Bewegung, Energie, weisse
Akzent-Blitze). Weihnachten = rot/gruen/gold, ruhig, ohne Blitze; Club = wie bisher; selbst gewaehlte Farben gehen vor;
Schalter mixxx_genre_style; ohne Mixxx unveraendert."""
from _common import build, check, finish

import show as sw
import webpanel

check(sw.genre_style("Weihnachten") == "weihnachten" and sw.genre_style("House; Other") == "club", "Genre -> Stil")
check(sw.genre_style("pop") == "party" and sw.genre_style("Klassik") == "ruhig" and sw.genre_style("Rock") == "rock",
      "Gross-/Kleinschreibung egal")
check(sw.genre_style("Other") is None and sw.genre_style("") is None and sw.genre_style(None) is None, "sonst kein Stil")
check(set(sw.GENRE_STYLE.values()) == set(sw.STYLES), "jeder Stil hat Genres")

rig, sh = build()
mx = {"plan": True, "deck": 1, "genre": "Weihnachten", "lvl": None, "connected": True, "title": "X", "want": "normal",
      "next": [], "pos": 10.0, "dur": 100.0, "status": "", "bpm": 120.0}
sh.mx = dict(mx)
check(sh._style_key() == "weihnachten", "Weihnachtslied: Stil Weihnachten")
hues = {sh._pick_hue() for _ in range(12)}
check(hues <= {0.0, 0.33, 0.11} and len(hues) >= 2, f"nur Rot, Gruen, Gold ({sorted(hues)})")
check(sh._style("flash", True) is False and sh._style("mv", 1.0) == 0.6 and sh._style("energy", 0.0) < 0,
      "ohne weisse Blitze, langsamer, ruhiger")
check(sh._mx_public()["style"] == "weihnachten", "ans Panel")

sh.auto_colors = ["blau", "magenta"]
check({sh._pick_hue() for _ in range(6)} <= {0.60, 0.88}, "selbst gewaehlte Farben gehen vor")
sh.auto_colors = []

sh.mx = dict(mx, genre="Techno")
check(sh._style_key() == "club" and sh._style("colors", None) is None, "Club: Farben nach Stimmung wie bisher")
sh.mx = dict(mx, genre="Other")
check(sh._style_key() is None and sh._style("mv", 1.0) == 1.0, "unbekanntes Genre: wie bisher")
sh.mx = dict(mx, deck=None, plan=False)
check(sh._style_key() is None, "kein Deck hoerbar: kein Stil")
sh.mx = dict(mx)
sh.cfg.set("mixxx_genre_style", 0)
check(sh._style_key() is None, "Schalter aus: kein Stil")
sh.cfg.set("mixxx_genre_style", 1)
sh.mx = None
check(sh._style_key() is None and sh._style("flash", True) is True, "ohne Mixxx: kein Stil")

p = webpanel.make_page()
check("(m.style&&tr('st_'+m.style).toLowerCase()!==String(m.genre).toLowerCase()?' → '+tr('st_'+m.style):'')" in p,
      "Panel: Stil hinter dem Genre, nur wenn er anders heisst")
check("(TXT['tier'+S.tier]?tr('tier'+S.tier):" in p, "Zeile 2: Stufe in Worten statt 'Stufe 1'")
import texts    # noqa: E402
check(texts.STATUS["tier1"] == ("Groove", "Groove") and texts.STATUS["tier3"][0] == "Vollgas", "Chillen, Groove, Party, Vollgas")

# ---- eigene Zuordnung Genre -> Stil (genre_styles.json) ---------------------------------------------------------------
import json         # noqa: E402
import os           # noqa: E402
import subprocess   # noqa: E402
import sys          # noqa: E402
import tempfile     # noqa: E402

from _common import ROOT                  # noqa: E402
from genre_style import GenreStyles       # noqa: E402
from mixxx_link import MixxxLink          # noqa: E402

d = tempfile.mkdtemp()
fn = os.path.join(d, "genre_styles.json")
gs = GenreStyles(fn)
check(gs.style("Pop") == "party" and not os.path.exists(fn), "ohne eigene Zuordnung: feste, keine Datei")
gs.set("Pop", "weihnachten")
gs.set("Other", "club")
gs.set("Klassik", "aus")
check(gs.style("pop") == "weihnachten" and gs.style("Other") == "club" and gs.style("Klassik") is None, "eigene Zuordnung gilt")
check(GenreStyles(fn).style("POP") == "weihnachten", "gespeichert und wieder geladen")
gs.set("Pop", "")
gs.set("Other", "aus")
check(gs.style("Pop") == "party" and gs.style("Other") is None, "zurueck auf Standard")
check(json.load(open(fn, encoding="utf-8")) == {"klassik": "aus"}, "Datei enthaelt nur Abweichungen")
try:
    gs.set("Pop", "disco")
    bad = False
except ValueError:
    bad = True
check(bad and gs.style("Pop") == "party", "unbekannter Stil abgelehnt")
rows = gs.table([["Pop", 1303], ["House; Other", 3], ["Weihnachten", 140]])
r0 = rows[1]
check([r["genre"] for r in rows[:3]] == ["House; Other", "Pop", "Weihnachten"] and r0 == {"genre": "Pop", "n": 1303, "default": "party", "own": "", "style": "party"},
      "Tabelle: Genres aus Mixxx zuerst, alphabetisch")
check(any(r["genre"] == "klassik" and r["own"] == "aus" and r["style"] == "" for r in rows), "Tabelle: eigene Zuordnung")
check(len({r["genre"].lower() for r in rows}) == len(rows), "jedes Genre nur einmal")

rig, sh = build()
sh.command({"genre_style": {"genre": "Weihnachten", "style": "party"}})
sh.mx = dict(mx)
check(sh._style_key() == "party", "Panel-Befehl: Weihnachten -> Party")

lk = MixxxLink(0)
lk.feed({"type": "genres", "g": [["Pop", 1303], ["Rock", 1286], "Unsinn", ["X", "y"]]}, 1000.0)
check(lk.genres == [["Pop", 1303], ["Rock", 1286]], "Pi: Genre-Liste von der Bruecke, Unsinn verworfen")

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
from mixxx_bridge import Forwarder        # noqa: E402


class Sock:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append(json.loads(data))


so = Sock()
fw = Forwarder([{"genre": "Pop"}, {"genre": "Rock"}, {"genre": "Pop"}, {"genre": ""}], so, ("pi", 9020), analyze=False)
fw.tick()
check(so.sent[0] == {"type": "genres", "g": [["Pop", 2], ["Rock", 1]]}, "Bruecke: Genres mit Anzahl, die haeufigsten zuerst")
fw.tick()
check(len(so.sent) == 2 and so.sent[1]["type"] == "stats", "dazu die Statistik, beides nur alle 30 s")

# ---- Stil von Hand (Knoepfe Stil im Panel, z. B. Live-Musik ohne Mixxx) -----------------------------------------------
rig, sh = build()
check(sh.snapshot()["style_man"] == "auto" and sh.snapshot()["style_eff"] == "", "Standard: Auto, ohne Mixxx kein Stil")
sh.command({"style": "ruhig"})
check(sh._style_key() == "ruhig" and sh._style("flash", True) is False, "Ruhig von Hand, auch ohne Mixxx")
check({sh._pick_hue() for _ in range(6)} <= {0.60, 0.75, 0.46}, "Farben des Stils")
sh.mx = dict(mx, genre="Techno")
check(sh._style_key() == "ruhig", "von Hand geht vor dem Genre aus Mixxx")
s0 = sh.snapshot()
check(s0["style_man"] == "ruhig" and s0["style_eff"] == "ruhig", "Panel: gewaehlter Stil")
sh.command({"style": "auto"})
check(sh._style_key() == "club" and sh.snapshot()["style_man"] == "auto", "Auto: wieder nach dem Genre")
sh.command({"style": "disco"})
check(sh.style_man is None, "unbekannter Stil = Auto")
check('<div class="grid" id="style">' in p and "mk('style',STYB" in p and p.index('id="speed"') < p.index('id="style"') < p.index('id="color"'),
      "Panel: Bereich Stil unter Speed, ueber den Farben")
check("mark('#style button','v',S.style_man||'auto')" in p, "gewaehlter Knopf orange, Stil aus Mixxx weiss umrandet")

check("loadGenres()" in p and "c({genre_style:{genre:r.genre,style:sel.value}})" in p, "Panel: Tabelle im Bereich Mixxx")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
# Gruppe im Tag (13.11.2026: Weihnachten ist ein Anlass): Weihnachtsgruppe oder Gruppe mit eigenem Stil geht vor dem Genre
sh.style_man = None
sh.cfg.set("mixxx_genre_style", 1)
sh.mx = dict(mx, genre="Pop", grp="Weihnachten")
check(sh._style_key() == "weihnachten", "Genre Pop, Gruppe Weihnachten: Licht Weihnachten")
sh.mx = dict(mx, genre="Pop", grp="Après-Ski; Party")
check(sh._style_key() == "party", "andere Gruppen ohne eigenen Stil aendern nichts (Genre Pop = party)")
sh.mx = dict(mx, genre="Weihnachten", grp="")
check(sh._style_key() == "weihnachten", "ohne Gruppe wie bisher")
sh.gstyles.set("Après-Ski", "club")
sh.mx = dict(mx, genre="Schlager", grp="Après-Ski")
check(sh._style_key() == "club", "Gruppe mit eigenem Stil (Genre-Stile im Panel) geht vor")
sh.gstyles.set("Après-Ski", "")
sh.cfg.set("mixxx_genre_style", 0)
sh.mx = dict(mx, genre="Pop", grp="Weihnachten")
check(sh._style_key() is None, "Schalter aus: auch keine Gruppe")
sh.cfg.set("mixxx_genre_style", 1)
import mixxx_link  # noqa: E402
src = open(mixxx_link.__file__, encoding="utf-8").read()
check('p["grp"] = str(m.get("grp") or "")[:120]' in src and 'st["grp"] = str(p.get("grp") or "")[:120]' in src, "Pi nimmt die Gruppe aus dem Plan")
import os  # noqa: E402
from _common import ROOT  # noqa: E402
br = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check('"grp": str(rec.get("grouping") or "")[:120]' in br and 'deck["plan"]["grp"] = str(rec.get("grouping") or "")[:120]' in br, "Bruecke schickt die Gruppe mit")
from showman import autodj  # noqa: E402
lib = [{"path": "/a.mp3", "dur": 200, "title": "Driving Home", "genre": "Pop", "grp": "Weihnachten", "lvl": 5, "bpm": 120},
       {"path": "/b.mp3", "dur": 200, "title": "Sommer", "genre": "Pop", "grp": "", "lvl": 5, "bpm": 120}]
c = autodj.candidates(lib)
check([t["path"] for t in c] == ["/b.mp3"] and len(autodj.candidates(lib, xmas=True)) == 2, "Auto-DJ: Gruppe Weihnachten nur auf Wunsch")
finish("test_genre_stil")
