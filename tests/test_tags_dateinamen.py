"""Tags aus dem Dateinamen (Wunsch 10.11.2026): Muster, Vorschau nur fuer leere Felder, schreiben nur die gewaehlten Felder;
Zahnraeder der Werkzeuge in der Datenpflege gross."""
import os
import sys
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import fname_tags as ft                      # noqa: E402
import file_check as fc                      # noqa: E402
import music_serve                           # noqa: E402

P = ft.parse
check(P("19th Floor - Bobby Richards.mp3", "t-a") == {"title": "19th Floor", "artist": "Bobby Richards"}, "Titel - Interpret")
check(P("Abba - Waterloo.mp3", "a-t") == {"artist": "Abba", "title": "Waterloo"}, "Interpret - Titel")
check(P("03 - Abba - Waterloo.mp3", "n-a-t") == {"artist": "Abba", "title": "Waterloo", "track": "3"}, "Nr - Interpret - Titel")
check(P("07. Intro.mp3", "n-t") == {"title": "Intro", "track": "7"}, "Nr - Titel")
check(P("a - b - c.mp3", "a-t") == {"artist": "a", "title": "b - c"} and P("Ohne Strich.mp3", "a-t") == {}, "mehrere Striche, ohne Strich nichts")
check(P("ambient-inspiration-136110.mp3", "p") == {"title": "Ambient Inspiration"}, "Pixabay-Name")
check(P("Lied_mit_Unterstrich.mp3", "t") == {"title": "Lied mit Unterstrich"}, "nur Titel")

root = os.path.join(tmp, "musik")
files = {"FREE/19th Floor - Bobby Richards.mp3": {}, "FREE/Across The Pier - VYEN.mp3": {"artist": "VYEN", "title": "", "track": ""},
         "FREE/Fertig - Ich.mp3": {"artist": "Ich", "title": "Fertig", "track": ""}, "U-MUSIK/Abba - Waterloo.mp3": {}}
for rel in files:
    os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
    open(os.path.join(root, rel), "wb").close()
songs = [{"path": os.path.join(root, rel), "duration": 120.0} for rel in files]
loc = music_serve.Locator([s["path"] for s in songs], root=root)
chk = fc.FileCheck(lambda: root, lambda: songs, loc.locate, trash=lambda ps: 0, sleep=lambda s: None)
read = lambda f: dict({"artist": "", "title": "", "track": ""}, **files[os.path.relpath(f, root).replace(os.sep, "/")])   # noqa: E731
check(ft.dirs(chk) == [("FREE", 3), ("U-MUSIK", 1)], "Ordner zur Auswahl mit Zahl")
s = ft.scan(chk, "FREE", "t-a", read=read)
by = {x["rel"].split("/")[-1]: x for x in s["songs"]}
check(s["n"] == 3 and s["todo"] == 2, "nur dieser Ordner, bei zweien kommt etwas dazu")
check(by["19th Floor - Bobby Richards.mp3"]["change"] == {"title": "19th Floor", "artist": "Bobby Richards"}, "leeres Tag: alles")
check(by["Across The Pier - VYEN.mp3"]["change"] == {"title": "Across The Pier"}, "vorhandener Interpret bleibt, nur der leere Titel")
check(by["Fertig - Ich.mp3"]["change"] == {}, "alles da: nichts zu tun")
s2 = ft.scan(chk, "FREE", "a-t", overwrite=True, read=read)
check({x["rel"].split("/")[-1]: x for x in s2["songs"]}["Fertig - Ich.mp3"]["change"] == {"artist": "Fertig", "title": "Ich"}, "mit Haken: auch vorhandene ueberschreiben")
for bad in (("../x", "a-t"), ("FREE", "zz"), ("GIBTS", "a-t")):
    try:
        ft.scan(chk, *bad, read=read)
        check(False, "abgelehnt: " + str(bad))
    except ValueError:
        check(True, "abgelehnt: " + str(bad))
done = []
r = ft.apply(chk, [{"path": by["19th Floor - Bobby Richards.mp3"]["path"], "file": by["19th Floor - Bobby Richards.mp3"]["file"],
                    "fields": {"title": "19th Floor", "artist": "Bobby Richards", "genre": "boese"}},
                   {"path": "/etc/passwd", "file": "/etc/passwd", "fields": {"title": "x"}}],
             write=lambda f, fl: done.append((os.path.basename(f), fl)), on_written=lambda p, f: None)
check(r["written"] == 1 and len(r["errors"]) == 1 and done == [("19th Floor - Bobby Richards.mp3", {"title": "19th Floor", "artist": "Bobby Richards"})],
      "schreibt nur Interpret/Titel/Track, nur Dateien der Bibliothek")

SM = os.path.join(ROOT, "pi", "static", "sm")
js = open(os.path.join(SM, "fnametags.js"), encoding="utf-8").read()
html = open(os.path.join(SM, "fnametags.html"), encoding="utf-8").read()
check("SM.playBar(audio" in js and "SM.tagEdit(" in js and "const PAGE = 20" in js and "/cover?p=" in js and 'data-title="h_fnametags"' in html, "Seite: Leiste, Tag, Seiten, Cover, Kopfleiste")
care = open(os.path.join(SM, "care.js"), encoding="utf-8").read()
check("href: '/musik/dateinamen', tool: true" in care and "' tool' :" in care and ".nr.tool { font-size: 22px" in open(os.path.join(SM, "care.html"), encoding="utf-8").read(),
      "Werkzeug in der Datenpflege, Zahnrad gross im Kreis")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("fname_tags.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert fname_tags.py")
finish("test_tags_dateinamen")
