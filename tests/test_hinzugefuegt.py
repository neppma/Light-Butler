"""Hinzugefuegt (Wunsch 11.11.2026): wann ein Lied in die Sammlung kam. Importdatum im Tag (Import-Seite), sonst Mixxx
datetime_added, sonst wann die Datei auf den Stick kam; Spalte und Filter "neu seit" in der Musik-Datenbank."""
import os
import sys
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "pi"))
import mixxx_bridge as mb                    # noqa: E402
import import_assist as ia                   # noqa: E402
import tag_edit                              # noqa: E402
import mixxx_link                            # noqa: E402

check(mb.added_epoch("2026-11-10T21:41:19.805Z") == 1794346879 and mb.added_epoch("2026-11-10") == 1794268800
      and mb.added_epoch("2024-01-11 12:00:00") == 1704974400 and mb.added_epoch("") == 0 and mb.added_epoch("Unsinn") == 0, "Datum lesen")
recs = [{"artist": "A", "title": "Import", "duration": 100, "path": os.path.join(tmp, "a.mp3"), "imported": "2026-11-11", "datetime_added": "2024-01-11T10:00:00Z"},
        {"artist": "B", "title": "Mixxx", "duration": 100, "path": os.path.join(tmp, "b.mp3"), "datetime_added": "2026-11-10T21:41:19Z"},
        {"artist": "C", "title": "Ordner", "duration": 100, "path": os.path.join(tmp, "c.mp3"), "added": 1700000000}]
for r in recs:
    open(r["path"], "wb").close()
items = {x[3]: x for ch in mb.library_chunks(recs) for x in ch}
check(items["Import"][26] == mb.added_epoch("2026-11-11") and items["Mixxx"][26] == mb.added_epoch("2026-11-10T21:41:19Z") and items["Ordner"][26] == 1700000000,
      "Importdatum vor Mixxx vor Datei")
check(mixxx_link.lib_item(items["Mixxx"])["added"] == items["Mixxx"][26] and mixxx_link.lib_item(items["Mixxx"][:26])["added"] == 0, "Pi liest es, alte Bruecke: 0")

# Import schreibt das Datum in die MP3, nur wenn noch keins drinsteht
w = []
check(ia.stamp_import("/x/a.mp3", "2026-11-11", write=lambda p, f: w.append(f), read=lambda p: {}) and w == [{"imported": "2026-11-11"}], "Import: Datum geschrieben")
check(not ia.stamp_import("/x/a.mp3", "2026-11-12", write=lambda p, f: w.append(f), read=lambda p: {"imported": "2026-11-01"}) and len(w) == 1, "vorhandenes bleibt")
check(not ia.stamp_import("/x/a.wav", write=lambda p, f: w.append(f), read=lambda p: {}), "nur MP3")
check(any(k == "imported" and fr == "TXXX:Importdatum" for k, fr, _l in tag_edit.FIELDS), "Tag-Fenster zeigt das Importdatum")
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "import_assist.py"), encoding="utf-8").read()
check("stamp(src)" in src, "Import-Seite stempelt vor dem Verschieben")
js = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("k: 'added', th: 'Hinzugefügt'" in js and "r.added < addFrom" in js and 'id="fadd"' in open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read(),
      "Musik-DB: Spalte und Filter neu seit")
html = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
check('value="heute"' in html and 'value="gestern"' in html and 'value="datum"' in html and 'id="faddv"' in html and 'id="faddb"' in html
      and "fav === 'heute'" in js and "r.added >= addTo" in js and "mid.setHours(0, 0, 0, 0)" in js and "$('faddv').value = ''" in js,
      "Filter heute, gestern und von ... bis (Kalendertage ab Mitternacht, Wunsch 11.11.2026)")
finish("test_hinzugefuegt")
