"""Fehlerbericht von Markus (11.11.2026): "Filter heute importiert: die Auswahl geht immer wieder auf 0, baut sich langsam auf
5 bis 32 Eintraege auf, nie 41, dann wieder leer."

Ursache: Die Lautheits-Messung aendert die Liste am Mac alle 30 s. Kam eine neue Fassung, bevor der Pi die vorige hatte,
sammelte er neu und zeigte nur die Ablage, in der die heute importierten Lieder noch fehlten. Dazu meldete der Pi hoechstens
600 fehlende Stuecke: die Bruecke hielt das fuer "weniger als die Haelfte" und schickte nie wieder alles (Schleife).
"""
import json
import os
import sys
import tempfile

from _common import ROOT, check, finish

from mixxx_link import MixxxLink

tmp = tempfile.mkdtemp(prefix="s2l_umbau_")
p = os.path.join(tmp, "_mixxx_bibliothek.json")
with open(p, "w", encoding="utf-8") as f:                 # Ablage von gestern: ohne die neuen Lieder
    json.dump([["Alt - Eins", 100.0, "Alt", "Eins"], ["Alt - Zwei", 100.0, "Alt", "Zwei"]], f)
lk = MixxxLink(0)
lk.persist(p)


def names():
    return sorted(x["name"] for x in lk.library_full())


# Fassung v1 kommt (2 von 3 Stuecken), darin ein heute importiertes Lied
lk.feed({"type": "lib", "i": 0, "n": 3, "h": "v1", "t": [["Alt - Eins", 100.0, "Alt", "Eins"]]}, 1.0)
lk.feed({"type": "lib", "i": 1, "n": 3, "h": "v1", "t": [["Neu - Heute", 100.0, "Neu", "Heute"], ["Alt - Zwei", 100.0, "Alt", "Zwei"]]}, 1.1)
check(names() == ["Eins", "Heute", "Zwei"], "v1 halb da: das neue Lied ist sichtbar")

# neue Fassung v2, bevor v1 fertig ist (Grundlage passt nicht): der Pi sammelt neu, das neue Lied darf nicht verschwinden
lk.feed({"type": "lib", "i": 2, "n": 3, "h": "v2", "b": "falsch", "c": 1, "t": [["Neu - Morgen", 100.0, "Neu", "Morgen"]]}, 2.0)
check(lk.library_missing() == ("v2", [0, 1]), "Pi sammelt v2 neu und meldet die fehlenden Stuecke")
check(names() == ["Eins", "Heute", "Morgen", "Zwei"], "nichts verschwindet waehrend des Neu-Sammelns: " + str(names()))
lk.feed({"type": "lib", "i": 0, "n": 4, "h": "v3", "t": [["Alt - Eins", 100.0, "Alt", "Eins"]]}, 3.0)
check("Heute" in names() and "Morgen" in names(), "auch beim naechsten Neu-Sammeln nicht: " + str(names()))
# komplett: dann gilt nur noch die neue Fassung (geloeschte Lieder sind weg)
for i, t in ((1, [["Neu - Heute", 100.0, "Neu", "Heute"]]), (2, [["Neu - Morgen", 100.0, "Neu", "Morgen"]]), (3, [])):
    lk.feed({"type": "lib", "i": i, "n": 4, "h": "v3", "t": t}, 3.1)
check(lk.library_complete() and names() == ["Eins", "Heute", "Morgen"], "v3 komplett: genau ihre Lieder (Alt - Zwei geloescht): " + str(names()))

# Pi meldet, wie viele Stuecke insgesamt fehlen (nicht nur die ersten 600)
lk2 = MixxxLink(0)
lk2.feed({"type": "lib", "i": 0, "n": 2000, "h": "w", "t": [["A - B", 1.0]]}, 1.0)
h, miss = lk2.library_missing()
check(len(miss) == 600 and lk2.library_missing_count() == 1999, "600 Stuecke gemeldet, Zahl aller fehlenden 1999")
sys.path.insert(0, os.path.join(ROOT, "pi"))
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('out["missn"]' in api, "Pi schickt die Zahl aller fehlenden an den Mac")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import music_serve                            # noqa: E402
ms = music_serve.MusicServer.__new__(music_serve.MusicServer)
try:
    ms.apply_conf({"libr": "w", "miss": [1, 2, 3], "missn": 1999})
except Exception:                             # noqa: BLE001
    pass
check(ms.pi_miss == ("w", [1, 2, 3]) and ms.pi_missn == 1999, "Mac merkt sich die Zahl aller fehlenden")
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check("missn" in src and "nmiss < len(chunks) // 2" in src, "Bruecke: fehlt mehr als die Haelfte, schickt sie alles")
check("self.loud.refresh():\n                pass" in src or "if self.loud.refresh():\n                self.lib_done" not in src,
      "neue Lautheits-Werte loesen keine sofortige Neu-Uebertragung aus (die Liste geht alle 2 Minuten)")
# Lamperl in der Musik-Datenbank (Wunsch 11.11.2026): gruen vollstaendig, orange im Aufbau, grau ohne Mac
from showman.api import ShowManager          # noqa: E402


class FakeShow:
    def __init__(self, link, connected):
        self.mixxx, self.mx = link, {"connected": connected}


lk4 = MixxxLink(0)
lk4.feed({"type": "lib", "i": 0, "n": 4, "h": "z", "t": [["A - B", 1.0]]}, 1.0)
mgr = ShowManager.__new__(ShowManager)
mgr.show = FakeShow(lk4, True)
s = ShowManager.music_state(mgr)
check(s["connected"] and not s["complete"] and s["prog"][:2] == [1, 4] and s["v"] == lk4.lib_ver, "im Aufbau: 1 von 4, Stand v: " + json.dumps(s))
for i in (1, 2, 3):
    lk4.feed({"type": "lib", "i": i, "n": 4, "h": "z", "t": []}, 1.1)
s = ShowManager.music_state(mgr)
check(s["complete"] and "prog" not in s, "komplett: gruen")
mgr.show = FakeShow(MixxxLink(0), False)
check(not ShowManager.music_state(mgr)["connected"], "ohne Mac: grau")
check('"/api/musik/stand"' in api, "Route /api/musik/stand (ohne Lieder, alle 10 s)")
SMD = os.path.join(ROOT, "pi", "static", "sm")
mj = open(os.path.join(SMD, "music.js"), encoding="utf-8").read()
mh = open(os.path.join(SMD, "music.html"), encoding="utf-8").read()
check('id="liblamp"' in mh and "#liblamp.ok i" in mh and "#liblamp.build i" in mh and "function showLamp(d)" in mj and "setInterval(pollLamp, 10000)" in mj,
      "Musik-DB: Lamperl oben")
check("!d.complete && !tracks.length && !timer" in mj and "d.complete && !timer) load(true)" in mj,
      "im Aufbau springt die Liste nicht mehr, sie kommt neu, sobald sie komplett ist")
core = open(os.path.join(SMD, "core.js"), encoding="utf-8").read()
i_ask = core.index("SM.ask = ")
check("m.style.zIndex = 1000;" in core[i_ask:i_ask + 800],
      "Rueckfrage immer ganz oben (lag hinter dem Fade-Fenster, nur schwarzer Hintergrund, Fehlerbericht 11.11.2026)")
check(mh.index('id="liblamp"') < mh.index('id="sum"') < mh.index('id="mhead"') < mh.index('id="bcols"') < mh.index('id="q"')
      and mh.index('<div id="mstat">') < mh.index('id="sum"') < mh.index('</div>', mh.index('<div id="mstat">')),
      "Kopf: Lamperl und Zahlen in einer Zeile, die Knoepfe direkt ueber der Suche (Wunsch 11.11.2026)")
_ms = mh.index('<div id="mstat">')
check(mh.index('id="mhead"') < mh.index('id="hint"') and "#hint:empty { display: none; }" in mh,
      "Hinweis ohne leere Zeile, wenn nichts zu melden ist (11.11.2026); seit 14.11.2026 unter den Knoepfen, damit er sie nicht verschiebt")
finish("test_bibliothek_umbau")
