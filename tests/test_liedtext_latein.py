"""Liedtext nur in lateinischer Schrift (Wunsch von Markus 24.11.2026): Zeilen in anderen Schriften waren im Panel, auf
der Matrix und ueber die Schnittstelle nicht lesbar. showman/latin.py, angewendet beim Holen (lyrics.to_lyrics), beim
Lesen aus dem Zwischenspeicher (LyricCache.entry, auch alte Eintraege) und beim Laden von Shows (timeline.clean_lyrics)."""
import os
import tempfile

from _common import check, finish
from showman import latin, lyrics, timeline  # noqa: E402

check(latin.line("Grüß Gott, schöne Straße!") == "Grüß Gott, schöne Straße!", "Deutsch mit Umlauten und ß bleibt")
check(latin.line("Señor, ¿qué pasa? Je t'aime, café") == "Señor, ¿qué pasa? Je t'aime, café", "Akzente bleiben")
check(latin.line('I said: "Yeah!" (x2) - 100 €') == 'I said: "Yeah!" (x2) - 100 €', "Satzzeichen, Ziffern, Euro bleiben")
for s in ("حبيبي يا نور العين", "我爱你 我爱你", "Привет мир", "baby 我爱你 我爱你 我爱你", "שלום עולם", "こんにちは"):
    check(latin.line(s) == "", "andere Schrift faellt weg: %s" % s)
check(latin.line("Love ❤️ you 🎉") == "Love you", "Emojis fallen weg")
check(latin.line("Oh baby, I love you so much мир") == "Oh baby, I love you so much", "einzelnes fremdes Wort in lateinischer Zeile faellt weg")
check(latin.line("Oh oh oh, привет") == "", "halb fremde Zeile faellt ganz weg")
check(latin.lines([[1.0, "Hallo"], [2.0, "我爱你"], [3.0, ""]]) == [[1.0, "Hallo"], [2.0, ""], [3.0, ""]], "Zeiten bleiben, fremde Zeile leer")
check(latin.lines([[1.0, "我爱你"], [2.0, "حبيبي"]]) == [], "ganz fremdes Lied: kein Liedtext")
check(latin.plain("Hallo\n我爱你\n\nWelt") == "Hallo\n\nWelt", "reiner Text: fremde Zeilen weg, Strophen bleiben")

rec = {"syncedLyrics": "[00:01.00]Hallo\n[00:02.00]我爱你\n[00:03.00]Welt", "plainLyrics": "Hallo\n我爱你\nWelt", "duration": 100,
       "artistName": "A", "trackName": "B"}
y = lyrics.to_lyrics(rec, 100)
check([x[1] for x in y["lines"]] == ["Hallo", "我爱你", "Welt"], "neu geholt: gespeichert wird der ganze Text")

tmp = tempfile.mkdtemp()
cache = lyrics.LyricCache(os.path.join(tmp, "l.sqlite"), opener=None)
cache.store("A - B", 100, [[1.0, "Hallo"], [2.0, "我爱你"]], "")
e = cache.entry("A - B", 100)
check(e["lines"] == [[1.0, "Hallo"], [2.0, ""]], "aus dem Zwischenspeicher (alter Eintrag): gefiltert")
cache.store("C - D", 100, [[1.0, "我爱你"]], "")
check(cache.entry("C - D", 100)["lines"] == [], "alter Eintrag ganz fremd: kein Liedtext")
c = timeline.clean_lyrics({"lines": [[1, "Hallo"], [2, "Привет"]], "plain": "Hallo\nПривет"})
check(c["lines"][1][1] == "Привет", "Show-Datei: gespeichert wird der ganze Text")

# Haken aus: alles wieder sichtbar, auch aus dem Zwischenspeicher
latin.ENABLED = False
check(cache.entry("A - B", 100)["lines"] == [[1.0, "Hallo"], [2.0, "我爱你"]], "lyrics_latin aus: alles sichtbar")
check(latin.plain("Hallo\n我爱你") == "Hallo\n我爱你" and latin.line("Привет") == "Привет", "aus: nichts gefiltert")
latin.ENABLED = True

# Show: Einstellung und Anzeige im Panel
from _common import build  # noqa: E402

rig, sh = build()
check(sh.cfg["lyrics_latin"] == 1.0, "Standard an")
sh.cfg.set("lyrics_latin", 0.0)
sh.update(1795450000.0)
check(latin.ENABLED is False, "Show setzt den Schalter je Bild")
sh.cfg.set("lyrics_latin", 1.0)
sh.update(1795450000.025)
check(latin.ENABLED is True, "wieder an")
finish("test_liedtext_latein")
