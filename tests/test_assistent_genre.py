"""Show-Assistent: Genre und Energiestufe auch fuer Shows, deren Lied nie in einem Mixxx-Deck lag (Fehlerbericht von Markus
06.11.2026: "kein Genre bekannt" bei jeder Show, obwohl Mixxx ein Genre kennt). Dann kommt es aus der Bibliothek."""
import os
import tempfile

from _common import build, check, finish

from mixxx_link import MixxxLink
from showman.api import ShowManager

link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_gen_"))
mgr.music_path = os.path.join(tempfile.mkdtemp(), "keins.json")
link.feed({"type": "lib", "i": 0, "n": 1, "t": [
    ["Abba - Dancing Queen", 230.5, "Abba", "Dancing Queen", 101.0, "A", 0, "Pop", 6, "a.mp3", 0, 1, "/m/u/a.mp3"],
    ["Abba - Dancing Queen", 230.4, "Abba", "Dancing Queen", 101.0, "A", 0, "Oldies", 5, "a.mp3", 0, 1, "/m/o/a.mp3"],
    ["Abba - Dancing Queen", 231.4, "Abba", "Dancing Queen", 100.0, "A", 0, "Pop", 7, "v.mp3", 0, 1, "/m/v.mp3"]]}, 1.0)
mgr.op({"op": "create", "name": "Abba"})
doc = mgr.store.load("Abba")
doc["mixxx"] = {"on": True, "title": "Abba - Dancing Queen", "dur": 230.4}
mgr.store.save("Abba", doc)
info = mgr.assist_info("Abba")
check(info["genre"] == "Oldies" and info["lvl"] == 5, "ohne Mixxx-Deck: Genre und Stufe aus der Bibliothek, das Lied mit der passenden Laenge: %s %s" % (info["genre"], info["lvl"]))
check(info["style"] == (sh.gstyles.style("Oldies") or ""), "Stil folgt dem Genre wie sonst")
check(mgr.store.load("Abba").get("marks") in (None, {}) or not (mgr.store.load("Abba").get("marks") or {}).get("se"), "Showdatei bleibt unveraendert")
# Leere Show: Vorschlag direkt hinein statt einer weiteren Kopie (Wunsch von Markus 06.11.2026)
names0 = {x["name"] for x in mgr.store.list()}
res = mgr._assist({"name": "Abba", "claude": False})
filled = mgr.store.load("Abba")
check(res["show"] == "Abba" and res["replaced"] and {x["name"] for x in mgr.store.list()} == names0, "leere Show: Vorschlag in derselben Show, keine neue Datei")
check(any(t.get("clips") or t.get("keys") for t in filled["tracks"]) and filled["name"] == "Abba" and filled["mixxx"]["title"] == "Abba - Dancing Queen",
      "Spuren drin, Name und Mixxx-Lied bleiben")
check(not filled.get("marks"), "Vorschlag: das nachgeschlagene Genre landet nicht als halbe Analyse in der Datei")
check(mgr.marks("Abba")["marks"] in (None, {}), "Show laesst sich wie jede oeffnen (marks ohne Fehler)")
res2 = mgr._assist({"name": "Abba", "claude": False})
check(res2["show"] != "Abba" and not res2["replaced"] and mgr.store.load("Abba")["tracks"] == filled["tracks"], "Show mit Spuren: Vorschlag als Kopie, das Original bleibt")
mgr.op({"op": "create", "name": "Leer2"})
res3 = mgr._assist({"name": "Leer2", "claude": False, "keep_copy": True})
check(res3["show"] != "Leer2" and not res3["replaced"], "Ungespeichertes im Editor (keep_copy): lieber eine Kopie")
ejs = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi", "static", "sm", "editor.js"), encoding="utf-8").read()
check("keep_copy: !emptyShow" in ejs and "if (r.replaced) { dirty = false; location.reload(); }" in ejs, "Editor: sagt vorher, wohin der Vorschlag kommt, laedt danach neu")
mgr.op({"op": "create", "name": "Ohne"})
check(mgr.assist_info("Ohne")["genre"] == "", "Show ohne Mixxx-Lied: weiter kein Genre")
doc2 = mgr.store.load("Abba")
doc2["marks"] = {"se": [], "cu": [], "ev": [], "en": [], "lvl": 9, "genre": "Disco", "title": "Abba - Dancing Queen", "fp": ""}
mgr.store.save("Abba", doc2)
check(mgr.assist_info("Abba")["genre"] == "Disco", "Genre aus dem Mixxx-Deck geht vor")
finish("test_assistent_genre")
