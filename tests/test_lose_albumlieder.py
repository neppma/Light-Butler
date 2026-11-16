"""Lose Album-Lieder (Wunsch von Markus, 14.11.2026): Lieder eines Albums lose im Interpreten-Ordner finden und in den
Album-Ordner verschieben, ueber die Warteschlange fuer Mixxx, nie ueberschreiben, Protokoll und Zuruecknehmen."""
import os
import sys
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import album_loose as alo                    # noqa: E402
import file_check as fc                      # noqa: E402
import music_serve                           # noqa: E402

root = os.path.join(tmp, "STICK", "musik")
F = "U-MUSIK/Artists/Falco/"
files = {F + "Falco - Zuviel Hitze.mp3": ("Einzelhaft", "Falco"), F + "Falco - Nie mehr Schule.mp3": ("Einzelhaft", "Falco"),
         F + "1982 - Einzelhaft/02 - Der Kommissar.mp3": ("Einzelhaft", "Falco"), F + "1982 - Einzelhaft/09 - Helden.mp3": ("Einzelhaft", "Falco"),
         F + "1982 - Einzelhaft/Falco - Nie mehr Schule.mp3": None,      # gleicher Name schon im Album-Ordner (nicht in Mixxx)
         F + "Falco - Jeanny.mp3": ("Falco 3", "Falco"),               # anderes Album, ohne Ordner: bleibt
         "U-MUSIK/Compilations/Hits/Falco - Rock Me.mp3": ("Einzelhaft", "Falco"),   # Sampler-Ordner: nicht darueber
         "U-MUSIK/Artists/Austria 3/Austria 3 - Zwickt's.mp3": ("Parade", "Austria 3"),
         "U-MUSIK/Artists/Austria 3/2012 - Parade/Disc/01.mp3": ("Parade", "Austria 3")}
for rel in files:
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(rel.encode())
MX = "/Mixxx/musik/"
songs = [{"path": MX + rel, "album": v[0], "artist": v[1], "title": rel.split("/")[-1][:-4], "tracknumber": "3"} for rel, v in files.items() if v]
loc = music_serve.Locator([s["path"] for s in songs], root=root, path_map=[(MX.rstrip("/"), root)])
chk = fc.FileCheck(lambda: root, lambda: songs, loc.locate, trash=lambda ps: 0, sleep=lambda s: None)

s = alo.scan(chk)
by = {a["album"]: a for a in s["albums"]}
check(s["n"] == 2 and set(by) == {"Einzelhaft", "Parade"}, "zwei Alben mit losen Liedern (Falco, Austria 3 mit Ordner 'Disc')")
ein = by["Einzelhaft"]
check(ein["target"].endswith("Falco/1982 - Einzelhaft") and ein["n_album"] == 2 and len(ein["songs"]) == 2, "Ziel ist der Album-Ordner, nur die losen Lieder")
ex = {x["title"]: x["exists"] for x in ein["songs"]}
check(ex == {"Falco - Nie mehr Schule": True, "Falco - Zuviel Hitze": False}, "gleicher Name im Ziel wird erkannt")
check(by["Parade"]["target"].endswith("Austria 3/2012 - Parade"), "Ordner 'Disc' zaehlt zum Album darueber")
check(alo.count(chk)["n"] == 3, "Zahl fuer die Datenpflege")

items = [{"path": x["path"], "file": x["file"], "target": ein["target"]} for x in ein["songs"]]
r = alo.apply(chk, items + [{"path": MX + "x", "file": "/etc/passwd", "target": "/etc"}], now=lambda: 1000)
zh = os.path.join(root, F, "1982 - Einzelhaft", "Falco - Zuviel Hitze.mp3")
check(r["moved"] == 1 and r["skipped"] == 1 and os.path.isfile(zh) and not os.path.exists(os.path.join(root, F, "Falco - Zuviel Hitze.mp3")),
      "verschoben; vorhandene Datei im Ziel nie ueberschrieben")
check(open(os.path.join(root, F, "1982 - Einzelhaft", "Falco - Nie mehr Schule.mp3"), "rb").read().endswith(b"Album-Ordner/Falco - Nie mehr Schule.mp3") is False
      and os.path.isfile(os.path.join(root, F, "Falco - Nie mehr Schule.mp3")), "das Lied mit gleichem Namen bleibt liegen")
check(len(r["errors"]) == 2, "fremde Pfade abgelehnt: " + str(r["errors"]))
q = open(fc.FileCheck.queue_path(), encoding="utf-8").read()
check(MX + F + "Falco - Zuviel Hitze.mp3\t" + MX + F + "1982 - Einzelhaft/Falco - Zuviel Hitze.mp3" in q, "Mixxx bekommt den neuen Pfad (Warteschlange)")
h = alo.history()
check(h and h[0]["n"] == 1 and h[0]["t"] == 1000, "Protokoll")
u = alo.undo(chk, 1000)
check(u["back"] == 1 and os.path.isfile(os.path.join(root, F, "Falco - Zuviel Hitze.mp3")) and not os.path.exists(zh) and alo.history()[0]["undone"],
      "Zuruecknehmen: Datei wieder am alten Platz")
try:
    alo.undo(chk, 1000)
    check(False, "zweimal zuruecknehmen abgelehnt")
except ValueError:
    check(True, "zweimal zuruecknehmen abgelehnt")

ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('u.path == "/lose"' in ms and 'urlparse(self.path).path == "/lose"' in ms, "Musik-Rechner: /lose lesen und schreiben")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("album_loose.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert album_loose.py")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
care = open(os.path.join(ROOT, "pi", "static", "sm", "care.js"), encoding="utf-8").read()
page = open(os.path.join(ROOT, "pi", "static", "sm", "lose.html"), encoding="utf-8").read()
check('"/musik/lose"' in api and "href: '/musik/lose'" in care and "mac('/lose?count=1')" in care and 'class="s2lnav"' in page, "Seite, Schritt in der Datenpflege mit Zahl")
import subprocess  # noqa: E402
check(subprocess.run(["node", "--check", os.path.join(ROOT, "pi", "static", "sm", "lose.js")]).returncode == 0, "lose.js ohne Syntaxfehler")
lj = open(os.path.join(ROOT, "pi", "static", "sm", "lose.js"), encoding="utf-8").read()
check("tagedit.js" in page and "SM.tagEdit({ path: im.dataset.tag }" in lj and 'class="cvimg"' in lj, "Cover je Lied, Antippen oeffnet Tag bearbeiten")
check(all("track" in x for x in ein["songs"]) and 'class="no"' in lj, "Tracknummer aus dem Tag je Lied")
finish("test_lose_albumlieder")
