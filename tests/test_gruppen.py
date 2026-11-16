"""Gruppen-Manager (Wunsch von Markus, 13.11.2026): Feld Gruppe (TIT1) je Lied schreiben, nur MP3s, mit Protokoll und Zuruecknehmen;
Seite /musik/gruppen: verschieben, zusaetzlich, herausnehmen, umbenennen, aufloesen."""
import os
import subprocess
import sys
import tempfile
import time

from _common import ROOT, check, finish

tmp = os.path.realpath(tempfile.mkdtemp())
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import genre_edit as ge  # noqa: E402

P = {}
for n in ("a.mp3", "b.mp3", "c.wav"):
    P[n] = os.path.join(tmp, n)
    open(P[n], "wb").write(b"x")
LIB = [{"path": P["a.mp3"], "artist": "A", "title": "a", "genre": "", "grouping": "Après-Ski"},
       {"path": P["b.mp3"], "artist": "B", "title": "b", "genre": "", "grouping": "Après-Ski; Party"},
       {"path": P["c.wav"], "artist": "C", "title": "c", "genre": "", "grouping": ""}]
written = []


def write(f, fields):
    written.append((os.path.basename(f), dict(fields)))
    for r in LIB:
        if r["path"] == f:
            r.update(fields)


def wait(e):
    for _ in range(200):
        if (e.job_status() or {}).get("state") == "done":
            return
        time.sleep(0.02)


E = ge.GenreEditor(lambda: LIB, lambda p: p, lambda: tmp, write=write)
E.set_grouping([(P["a.mp3"], "Hütte"), (P["b.mp3"], " Party ;; Hütte "), (P["c.wav"], "X")], "„Après-Ski“ → „Hütte“")
wait(E)
check(written == [("a.mp3", {"grouping": "Hütte"}), ("b.mp3", {"grouping": "Party; Hütte"})], "nur MP3s, Gruppen sauber getrennt: " + str(written))
h = E.history()[0]
check(h["field"] == "grouping" and h["label"] == "„Après-Ski“ → „Hütte“" and h["items"][1][1] == "Après-Ski; Party", "Protokoll mit Feld, Text und alten Gruppen")
written.clear()
E.undo(h["id"])
wait(E)
check(written == [("a.mp3", {"grouping": "Après-Ski"}), ("b.mp3", {"grouping": "Après-Ski; Party"})], "Zuruecknehmen schreibt die alten Gruppen")
try:
    E.set_grouping([(P["a.mp3"], "Après-Ski")], "")
    check(False, "nichts zu aendern: Meldung")
except ValueError:
    check(True, "nichts zu aendern: Meldung")
ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('op == "group" and isinstance(d.get("pairs"), list)' in ms and 'q.get("field")' in ms and '"ops": ops' in ms, "Musik-Rechner: Befehl group, Stand je Feld")

# Seite: die Rechnung der neuen Gruppen (im Browser)
gj = open(os.path.join(ROOT, "pi", "static", "sm", "groups.js"), encoding="utf-8").read()
check(subprocess.run(["node", "--check", os.path.join(ROOT, "pi", "static", "sm", "groups.js")]).returncode == 0, "groups.js ohne Syntaxfehler")
js = gj[gj.index("  const toks = r =>"):gj.index("  const isMp3 = r =>")]
r = subprocess.run(["node", "-e", js + ";const r={grp:'Après-Ski; Party'};const cur='Après-Ski',t='Hütte';"
                    "console.log(JSON.stringify([join(toks(r).filter(g=>g!==cur).concat([t])), join(toks(r).concat(['Party'])), join(toks(r).filter(g=>g!==cur)), join(toks(r).map(g=>g===cur?'Party':g))]))"],
                   capture_output=True, text=True)
check(r.stdout.strip() == '["Party; Hütte","Après-Ski; Party","Party","Party"]', "verschieben, zusaetzlich (doppelt nur einmal), herausnehmen, umbenennen/zusammenlegen: " + r.stdout + r.stderr[-200:])
page = open(os.path.join(ROOT, "pi", "static", "sm", "groups.html"), encoding="utf-8").read()
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
check('class="s2lnav"' in page and 'id="bmove"' in page and 'id="badd"' in page and 'id="bout"' in page and 'id="bren"' in page and 'id="bdis"' in page,
      "Seite: Kopfleiste und alle Knoepfe")
check('"/musik/gruppen"' in api and 'href="/musik/gruppen"' in mh and "op: 'group'" in gj and "data-undo" in gj, "Route, Knopf in der Musik-DB, Schreiben, Zuruecknehmen")
finish("test_gruppen")
