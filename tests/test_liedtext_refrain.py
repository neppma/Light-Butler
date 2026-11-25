"""Schnittstelle nur mit Refrain (Wunsch von Markus 24.11.2026): mit der Einstellung lyrics_api_chorus bekommen andere
Geraete (/api/lyrics, /api/takt) vom Liedtext nur die Zeilen, die mehrmals vorkommen (gleiche Regel wie die Pixel-Matrix),
die anderen sind leer. Aus = der ganze Text wie bisher."""
import time

from _common import build, check, finish

LINES = [[10.0, "Ich geh heut nicht nach Haus"], [14.0, "Wir tanzen bis zum Morgen hier"], [18.0, "Oh oh"],
         [20.0, "Wir tanzen bis zum Morgen hier"], [24.0, "Eine andere Strophe kommt jetzt"],
         [28.0, "Wir tanzen bis zum Morgen hier"], [32.0, ""]]
PLAIN = "Strophe eins geht so los\nRefrain hier ganz laut\n\nStrophe zwei ist anders\nRefrain hier ganz laut\nSchluss"


class FakeCache:
    def __init__(self, lines, plain):
        self.lines, self.plain = lines, plain

    def get_entry(self, title, dur, now=None):
        return {"lines": self.lines, "plain": self.plain}


rig, sh = build()
check(sh.cfg["lyrics_api_chorus"] == 0.0, "Standard aus: ganzer Text")
sh.lyric_cache = FakeCache(LINES, "")
sh.cfg.set("lyrics_auto", 1)
w0 = time.time()
sh.mx = {"connected": True, "playing": True, "deck": 1, "title": "Test - Lied", "dur": 200.0, "pos_f": 0.0, "t": w0, "rate": 1.0}
full = sh.lyrics_api(wall=w0)
check([z["text"] for z in full["zeilen"]] == [x[1] for x in LINES], "aus: alle Zeilen")

sh.cfg.set("lyrics_api_chorus", 1)
ch = sh.lyrics_api(wall=w0)
check([z["t"] for z in ch["zeilen"]] == [x[0] for x in LINES], "an: Zeiten bleiben")
check([z["text"] for z in ch["zeilen"]] == ["", LINES[1][1], "", LINES[1][1], "", LINES[1][1], ""],
      "an: nur Refrain, Strophen leer, kurzer Ruf ohne Refrain-Nachbar weg")
check(ch["liedId"] == full["liedId"] and ch["synchron"], "liedId und synchron gleich")
check(sh.takt(wall=w0)["lyrics"] is True, "/api/takt lyrics true mit Refrain")

sh.lyric_cache = FakeCache([[1.0, "Nur einmal diese Zeile"], [5.0, "Und diese auch nur einmal"]], "")
ch = sh.lyrics_api(wall=w0)
check(ch["zeilen"] == [] and sh.takt(wall=w0)["lyrics"] is False, "ohne Refrain: kein Text")

sh.lyric_cache = FakeCache([], PLAIN)
ch = sh.lyrics_api(wall=w0)
check([z["text"] for z in ch["zeilen"]] == ["Refrain hier ganz laut", "", "Refrain hier ganz laut"],
      "ohne Zeiten: Refrain-Zeilen mit Leerzeile dazwischen")
sh.cfg.set("lyrics_api_chorus", 0)
check(len(sh.lyrics_api(wall=w0)["zeilen"]) == len(PLAIN.splitlines()), "aus: ganzer Text ohne Zeiten")
finish("test_liedtext_refrain")
