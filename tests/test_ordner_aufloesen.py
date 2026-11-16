"""Ordner aufloesen (Wunsch 10.11.2026): OLDIES nach U-MUSIK einsortieren, nach Interpret, ueber die Warteschlange fuer Mixxx,
Gruppe eintragen, leere Ordner weg, nie ueberschreiben."""
import os
import sys
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import folder_merge as fm                    # noqa: E402
import file_check as fc                      # noqa: E402
import music_serve                           # noqa: E402
import stick_hold                            # noqa: E402

root = os.path.join(tmp, "STICK", "musik")
files = {"OLDIES/Artists/Abba/Abba - Waterloo.mp3": b"w", "OLDIES/Artists/Abba/Abba - Dancing Queen.mp3": b"d",
         "OLDIES/Artists/Bill Ramsey/Bill Ramsey - Zuckerpuppe.mp3": b"z", "OLDIES/Artists/X/X - Weg.mp3": b"x",
         "OLDIES/Artists/Abba/.DS_Store": b"", "U-MUSIK/Artists/ABBA/ABBA - Waterloo.mp3": b"alt",
         "U-MUSIK/Artists/Bill Ramsey/Bill Ramsey - Zuckerpuppe.mp3": b"anders"}
for rel, data in files.items():
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
MX = "/Mixxx/musik/"                                       # Mixxx kennt den Stick unter anderem Pfad
songs = [{"path": MX + rel, "artist": rel.split("/")[-1].split(" - ")[0], "title": rel.split(" - ")[-1][:-4], "duration": 180.0, "bitrate": 320,
          "grouping": "OLDIES" if rel.startswith("OLDIES") else "U-MUSIK"} for rel in files if rel.endswith(".mp3")]
songs[-1]["duration"] = 250.0                              # Zuckerpuppe in U-MUSIK: andere Laenge, trotzdem gleiches Lied
loc = music_serve.Locator([s["path"] for s in songs], root=root, path_map=[(MX.rstrip("/"), root)])
chk = fc.FileCheck(lambda: root, lambda: songs, loc.locate, trash=lambda ps: 0, sleep=lambda s: None)

s = fm.scan(chk, "OLDIES", "U-MUSIK")
by = {x["title"]: x for x in s["songs"]}
check(s["n"] == 4 and "OLDIES" in s["tops"] and "U-MUSIK" in s["tops"], "alle Lieder des Ordners, Ordner zur Auswahl")
check(by["Waterloo"]["target"] == "U-MUSIK/Artists/ABBA/Abba - Waterloo.mp3" and by["Waterloo"]["dup"], "vorhandener Interpreten-Ordner (ABBA), Lied gibt es schon")
check(by["Zuckerpuppe"]["dup"] and by["Dancing Queen"]["dup"] is None, "gleiches Lied mit anderer Laenge erkannt, neues ohne")
check(by["Weg"]["target"] == "U-MUSIK/Artists/X/X - Weg.mp3", "neuer Interpret: neuer Ordner")
for bad in (("OLDIES", "OLDIES"), ("../x", "U-MUSIK"), ("GIBTSNICHT", "U-MUSIK")):
    try:
        fm.scan(chk, *bad)
        check(False, "abgelehnt: " + str(bad))
    except ValueError:
        check(True, "abgelehnt: " + str(bad))

# vorgemerkte Umbenennung zeigt schon auf eine Datei: Kette wird umgestellt
q = fc.FileCheck.queue_path()
os.makedirs(os.path.dirname(q), exist_ok=True)
with open(q, "w", encoding="utf-8") as f:
    f.write("/Mixxx/musik/OLDIES/Artists/Abba/Abba - DQ alt.mp3\t" + MX + "OLDIES/Artists/Abba/Abba - Dancing Queen.mp3\n")
written = []


def wg(path, group):
    written.append((os.path.basename(path), group))
    return True


trashed = []


def trash(ps):
    for p in ps:
        trashed.append(p)
        os.remove(p)
    return 0


items = [{"path": by[t]["path"], "file": by[t]["file"], "do": d, "target": by[t]["target"], "dup": (by[t]["dup"] or {}).get("path", "")}
         for t, d in (("Dancing Queen", "move"), ("Zuckerpuppe", "move"), ("Waterloo", "trash"), ("Weg", "move"))]
items.append({"path": by["Weg"]["path"], "file": by["Weg"]["file"], "do": "move", "target": "OLDIES/x.mp3"})
r = fm.apply(chk, "OLDIES", items, group="OLDIES", trash=trash, write_group=wg)
check(r["moved"] == 3 and r["trashed"] == 1 and len(r["errors"]) == 1, "verschoben, weggeworfen; zweimal dieselbe Datei geht nicht: " + str(r))
check(os.path.isfile(os.path.join(root, "U-MUSIK/Artists/ABBA/Abba - Dancing Queen.mp3")), "in den vorhandenen Interpreten-Ordner")
check(open(os.path.join(root, "U-MUSIK/Artists/Bill Ramsey/Bill Ramsey - Zuckerpuppe.mp3"), "rb").read() == b"anders"
      and os.path.isfile(os.path.join(root, "U-MUSIK/Artists/Bill Ramsey/Bill Ramsey - Zuckerpuppe (2).mp3")), "nie ueberschrieben: (2)")
check(not os.path.exists(os.path.join(root, "OLDIES")) and r["removed_dirs"] >= 4, "leerer Ordner weg (samt .DS_Store)")
lines = [ln.rstrip("\n").split("\t") for ln in open(q, encoding="utf-8")]
check(["/Mixxx/musik/OLDIES/Artists/Abba/Abba - DQ alt.mp3", MX + "U-MUSIK/Artists/ABBA/Abba - Dancing Queen.mp3"] in lines,
      "wartende Umbenennung auf das neue Ziel umgestellt (keine Kette ins Leere)")
check([MX + "OLDIES/Artists/X/X - Weg.mp3", MX + "U-MUSIK/Artists/X/X - Weg.mp3"] in lines, "Mixxx-Pfad mit dem Anfang, den Mixxx kennt")
check(len(written) == 3 and all(g == "OLDIES" for _n, g in written), "Gruppe bei den verschobenen eingetragen")

# Gruppe nur, wo sie fehlt
calls = []
te = type("TE", (), {"read_tags": staticmethod(lambda p: {"fields": {"grouping": "U-MUSIK; OLDIES" if "a" in p else "U-MUSIK"}}),
                     "write_tags": staticmethod(lambda p, f: calls.append(f))})
w = fm.group_writer(te)
check(w("/x/a.mp3", "oldies") is False and w("/x/b.mp3", "OLDIES") is True and calls == [{"grouping": "U-MUSIK; OLDIES"}], "Gruppe nur dazu, wenn sie fehlt")

stick_hold.hold("/Volumes/X")
try:
    fm.apply(chk, "U-MUSIK", [])
    check(False, "Stick ausgeworfen: abgelehnt")
except ValueError:
    check(True, "Stick ausgeworfen: abgelehnt")
stick_hold.release()

SM = os.path.join(ROOT, "pi", "static", "sm")
js = open(os.path.join(SM, "merge.js"), encoding="utf-8").read()
html = open(os.path.join(SM, "merge.html"), encoding="utf-8").read()
check("SM.playBar(audio" in js and "SM.tagEdit(" in js and "const PAGE = 20" in js and "'/merge'" in js and "/cover?p=" in js, "Seite: Leiste, Tag, Seiten, Cover")
check('class="s2lnav"' in html and 'data-title="h_merge"' in html and 'id="grpon"' in html, "Seite: Kopfleiste und Gruppe eintragen")
check("href: '/musik/aufloesen', tool: true" in open(os.path.join(SM, "care.js"), encoding="utf-8").read()
      and 'path == "/musik/aufloesen"' in open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read(), "Werkzeug in der Datenpflege und Route")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("folder_merge.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert folder_merge.py")
finish("test_ordner_aufloesen")
