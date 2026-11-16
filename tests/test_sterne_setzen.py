"""Sterne im Light-Butler setzen (Wunsch von Markus, 14.11.2026): Pi merkt sie und zeigt sie sofort, der Musik-Rechner holt
sie in seine Warteschlange und bestaetigt, beim Start der Mixxx-App traegt mixxx_sterne.py sie in die Mixxx-Datenbank ein
(Mixxx zu, Sicherung, Journal = nichts anfassen, Weg ueber eine Kopie), danach faellt der Eintrag am Pi weg."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "pi"))
import mixxx_sterne as ms                    # noqa: E402
from showman import stars as stm            # noqa: E402
from showman import favorites as fv          # noqa: E402

# ---- Pi ----
S = stm.Stars(os.path.join(tmp, "shows"), now=lambda: 1000)
check(S.set(["/m/a.mp3", "/m/b.mp3"], 3) == 2 and S.eff("/m/a.mp3", 0) == 3 and S.eff("/m/c.mp3", 2) == 2, "setzen, wirksamer Wert")
for bad in (7, -1, True, "3"):
    try:
        S.set(["/m/a.mp3"], bad)
        check(False, "abgelehnt: " + repr(bad))
    except ValueError:
        check(True, "abgelehnt: " + repr(bad))
rows = S.apply([{"path": "/m/a.mp3", "rating": 0}, {"path": "/m/c.mp3", "rating": 4}])
check(rows[0]["rating"] == 3 and rows[1]["rating"] == 4, "Liste zeigt die Sterne von hier")
pend = S.pending()
check(sorted(p[0] for p in pend) == ["/m/a.mp3", "/m/b.mp3"] and all(p[1] == 3 and p[2] == 1000 for p in pend), "offen fuer den Musik-Rechner")
check(S.ack([["/m/a.mp3", 3, 1000], ["/m/b.mp3", 5, 1000]]) == 1 and [p[0] for p in S.pending()] == ["/m/b.mp3"], "Bestaetigen nur bei gleichem Wert und Zeit")
check(S.settle([{"path": "/m/a.mp3", "rating": 3}, {"path": "/m/b.mp3", "rating": 3}]) == 1 and "/m/a.mp3" not in S.d and "/m/b.mp3" in S.d,
      "Mixxx hat den Wert: Eintrag weg (nur bestaetigte)")
S2 = stm.Stars(os.path.join(tmp, "shows"))
check(S2.eff("/m/b.mp3", 0) == 3, "nach Neustart gemerkt")
F = fv.Favorites(os.path.join(tmp, "shows"), lambda: [{"path": "/m/b.mp3", "name": "B", "rating": 0}])
F.stars = S2
S2.set(["/m/b.mp3"], 5)
check(F.state()["song"] == ["/m/b.mp3"], "hier gesetzte 5 Sterne = Favorit")

# ---- Musik-Rechner: Warteschlange ----
ok = ms.add([["/m/x.mp3", 4, 10], ["/m/x.mp3", 2, 5], ["bad", 9, 1], ["/m/y.mp3", 1, 10]])
check(ms.load() == {"/m/x.mp3": [4, 10], "/m/y.mp3": [1, 10]} and len(ok) == 3, "Warteschlange: neuer gewinnt, Unsinn verworfen")

# ---- Mixxx-Datenbank ----
db = os.path.join(tmp, "mixxx", "mixxxdb.sqlite")
os.makedirs(os.path.dirname(db))
con = sqlite3.connect(db)
con.execute("CREATE TABLE track_locations (id INTEGER PRIMARY KEY, location TEXT)")
con.execute("CREATE TABLE library (id INTEGER PRIMARY KEY, location INTEGER, rating INTEGER)")
nfd = unicodedata.normalize("NFD", "/m/Österreich.mp3")
for i, p in enumerate(["/m/x.mp3", nfd, "/m/andere.mp3"], 1):
    con.execute("INSERT INTO track_locations VALUES (?, ?)", (i, p))
    con.execute("INSERT INTO library VALUES (?, ?, 0)", (i, i))
con.commit()
con.close()
ms.add([["/m/Österreich.mp3", 5, 11]])
open(db + "-journal", "w").close()
r = ms.apply(db, log=lambda t: None)
check(r["done"] == 0 and r["left"] == 3, "Journal daneben (Mixxx nicht sauber zu): nichts angefasst")
os.remove(db + "-journal")
r = ms.apply(db, log=lambda t: None)
rat = dict(sqlite3.connect(db).execute("SELECT location, rating FROM library").fetchall())
check(r["done"] == 2 and r["unknown"] == 1 and rat == {1: 4, 2: 5, 3: 0}, "eingetragen (Umlaut NFD/NFC egal), unbekanntes faellt heraus: " + str(r))
check(ms.load() == {} and os.path.isfile(os.path.join(ms.data_dir(), "mixxxdb-vor-sterne.sqlite")), "Warteschlange leer, Sicherung da")
ms.add([["/m/andere.mp3", 2, 20]])
r = ms.apply(db, log=lambda t: None, force_copy=True)
rat = dict(sqlite3.connect(db).execute("SELECT location, rating FROM library").fetchall())
check(r["done"] == 1 and rat[3] == 2, "Weg ueber eine Kopie (Datenbank direkt nicht erlaubt)")
# Startskript (Fehlerbericht 14.11.2026: Python darf den Ordner von Mixxx nicht oeffnen, cp im Skript schon)
sh = os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_sterne.sh")
ms.add([["/m/x.mp3", 1, 30], ["/m/gibtsnicht.mp3", 2, 30]])
env = dict(os.environ, S2L_DATA=os.environ["S2L_DATA"])
out = subprocess.run(["bash", sh, db], capture_output=True, text=True, env=env)
rat = dict(sqlite3.connect(db).execute("SELECT location, rating FROM library").fetchall())
check(rat[1] == 1 and ms.load() == {} and "eingetragen: 1" in out.stdout and "1 ohne Lied" in out.stdout,
      "Skript: cp holt, Python traegt in die Kopie ein, cp zurueck: " + out.stdout + out.stderr)
check(not os.path.exists(os.path.join(ms.data_dir(), ".arbeit.sqlite")) and not os.path.exists(os.path.join(ms.data_dir(), ".erledigt.json")), "Skript raeumt auf")
ms.add([["/m/x.mp3", 5, 40]])
open(db + "-journal", "w").close()
out = subprocess.run(["bash", sh, db], capture_output=True, text=True, env=env)
check("nicht sauber beendet" in out.stdout and ms.load() == {"/m/x.mp3": [5, 40]}, "Skript: Journal daneben, nichts angefasst")
os.remove(db + "-journal")
out = subprocess.run(["bash", sh, os.path.join(tmp, "fehlt", "mixxxdb.sqlite")], capture_output=True, text=True, env=env)
check("nicht gefunden" in out.stdout and ms.load() == {"/m/x.mp3": [5, 40]}, "Skript: keine Datenbank, bleibt fuer spaeter")
src_ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_sterne.py"), encoding="utf-8").read()
check("shutil.copy2(db" not in src_ms and '"--kopie"' in src_ms and '"--fertig"' in src_ms, "Python oeffnet im Startskript nur die Arbeitskopie")

# ---- Verdrahtung ----
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('op == "stars_set"' in api and 'op == "stars_ack"' in api and 'out["stars"] = st' in api and "self.stars.apply(out)" in api and '"/api/sm/stars"' in api,
      "Pi: setzen, bestaetigen, holen, Liste, Tag-Editor")
srv = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check("def take_stars(" in srv and '"op": "stars_ack"' in srv, "Musik-Rechner holt und bestaetigt")
la = open(os.path.join(ROOT, "mac", "mixxx_bridge", "install_launcher.sh"), encoding="utf-8").read()
check(la.index('mixxx_umbenennen.sh" "$SRC"') < la.index('bash "$BASE/mixxx_sterne.sh" "$SRC"') < la.index('cp "$SRC" "$BASE/mixxxdb.sqlite.neu"'),
      "Startskript: nach dem Umbenennen, bevor die Bruecke die Datenbank liest (Mixxx noch zu)")
for shf in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("mixxx_sterne.py" in open(os.path.join(ROOT, shf), encoding="utf-8").read() and "mixxx_sterne.sh" in open(os.path.join(ROOT, shf), encoding="utf-8").read(),
          shf + " installiert mixxx_sterne.py und .sh")
SM = os.path.join(ROOT, "pi", "static", "sm")
src = {f: open(os.path.join(SM, f), encoding="utf-8").read() for f in ("core.js", "music.js", "artists.js", "albums.js", "tagedit.js")}
check("SM.starsHtml = " in src["core.js"] and "SM.starSet = " in src["core.js"] and "SM.starsPick = " in src["core.js"], "gemeinsame Sterne in core.js")
check("SM.starsHtml(r.path, r.rating)" in src["music.js"] and "SM.starsPick(b)" in src["artists.js"] and "SM.starsPick(b)" in src["albums.js"]
      and "SM.starsHtml(r.path, d.r, 'big')" in src["tagedit.js"], "Musik-DB, Interpreten, Alben (Alle ★), Tag-Editor")
for f in src:
    check(subprocess.run(["node", "--check", os.path.join(SM, f)]).returncode == 0, f + " ohne Syntaxfehler")
finish("test_sterne_setzen")
