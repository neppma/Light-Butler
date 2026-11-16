"""Papierkorb der Shows (Wunsch von Markus 06.11.2026): geloeschte Shows sehen, zuruecklegen, endgueltig loeschen."""
import os
import tempfile
import time

from _common import PI, build, check, finish

from showman.api import ShowManager

rig, sh = build(strobe=False)
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_pk_"))
for n in ("Eins", "Zwei", "Drei"):
    mgr.op({"op": "create", "name": n})
check(mgr.op({"op": "trash_list"})["items"] == [], "leer am Anfang")
mgr.op({"op": "delete", "name": "Eins"})
time.sleep(1.05)                                   # Eintraege tragen die Sekunde im Namen
mgr.op({"op": "delete", "name": "Zwei"})
items = mgr.op({"op": "trash_list"})["items"]
check([x["name"] for x in items] == ["Zwei", "Eins"] and all(len(x["deleted"]) == 16 for x in items), "Liste: neueste zuerst, mit Datum")
r = mgr.op({"op": "trash_restore", "entry": items[1]["entry"]})
check(r["name"] == "Eins" and mgr.store.exists("Eins") and [x["name"] for x in r["items"]] == ["Zwei"], "zuruecklegen")
mgr.op({"op": "create", "name": "Zwei"})            # Name inzwischen neu vergeben
r = mgr.op({"op": "trash_restore", "entry": items[0]["entry"]})
check(r["name"] == "Zwei (zurueck)" and mgr.store.load("Zwei (zurueck)")["name"] == "Zwei (zurueck)" and mgr.store.exists("Zwei"),
      "Name schon vergeben: 'Name (zurueck)', die neue Show bleibt")
mgr.op({"op": "delete", "name": "Drei"})
e = mgr.op({"op": "trash_list"})["items"][0]["entry"]
for bad in ("../Eins", "Drei", "/etc", "..", e + "/../../x"):
    try:
        mgr.op({"op": "trash_delete", "entry": bad})
        check(False, "abgelehnt: " + bad)
    except ValueError:
        check(True, "abgelehnt: " + bad)
check(mgr.store.exists("Eins") and len(mgr.op({"op": "trash_list"})["items"]) == 1, "nichts anderes geloescht")
try:
    mgr.op({"op": "trash_delete"})
    check(False, "ohne Eintrag und ohne 'alle': Fehler")
except ValueError:
    check(True, "ohne Eintrag und ohne 'alle': nichts geloescht")
check(len(mgr.op({"op": "trash_list"})["items"]) == 1, "Papierkorb unveraendert")
check(mgr.op({"op": "trash_delete", "entry": e})["deleted"] == 1 and mgr.op({"op": "trash_list"})["items"] == [], "einzeln endgueltig")
mgr.op({"op": "delete", "name": "Eins"})
mgr.op({"op": "delete", "name": "Zwei"})
check(mgr.op({"op": "trash_delete", "all": True})["deleted"] == 2 and mgr.op({"op": "trash_list"})["items"] == [], "Papierkorb leeren")
check(mgr.store.exists("Zwei (zurueck)"), "Shows ausserhalb bleiben")
pjs = open(os.path.join(PI, "static", "sm", "play.js"), encoding="utf-8").read()
check("SM.cmd('trash_delete', { all: true })" in pjs and "lässt sich nicht rückgängig machen" in pjs and "SM.cmd('trash_restore'" in pjs,
      "Seite Shows: Papierkorb mit Zuruecklegen, Endgueltig loeschen (mit Rueckfrage) und Leeren")
finish("test_papierkorb")
