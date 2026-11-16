"""Import neuer Musik aus dem Wartebereich musik-import (Wunsch 10.11.2026): lesen, Ziel vorschlagen, gibt es das Lied schon,
verschieben, ersetzen, wegwerfen. Nie etwas ueberschreiben, nur im Musikordner, Vorhoeren und Tags fuer den Wartebereich."""
import json
import os
import sys
import tempfile
import urllib.request

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import import_assist as ia                   # noqa: E402
import music_serve                           # noqa: E402

stick = os.path.join(tmp, "STICK")
root = os.path.join(stick, "musik")
imp = os.path.join(stick, "musik-import")
os.makedirs(os.path.join(root, "U-MUSIK", "Artists", "Andreas Gabalier"))
os.makedirs(os.path.join(root, "U-MUSIK", "Artists", "Almklausi & Specktakel"))
os.makedirs(os.path.join(root, "OLDIES", "Artists"))
os.makedirs(os.path.join(root, "SAMPLES"))
os.makedirs(os.path.join(imp, "neu"))
os.makedirs(os.path.join(imp, "gibt es schon"))
old = os.path.join(root, "U-MUSIK", "Artists", "Andreas Gabalier", "Andreas Gabalier - Hulapalu.mp3")
with open(old, "wb") as f:
    f.write(b"alt" * 100)
INFO = {"Hulapalu.mp3": ("Andreas Gabalier", "Hulapalu"), "Mama.mp3": ("Almklausi", "Mama Laudaaa"),
        "Neu.mp3": ("Tobee", "Helikopter 117"), "Weg.mp3": ("X", "Weg")}
files = {"gibt es schon/Hulapalu.mp3": b"n" * 200, "neu/Mama.mp3": b"m" * 50, "neu/Neu.mp3": b"t" * 60, "neu/Weg.mp3": b"w" * 10}
for rel, data in files.items():
    with open(os.path.join(imp, rel), "wb") as f:
        f.write(data)


def read(p):
    a, t = INFO.get(os.path.basename(p), ("Sonst", os.path.basename(p)))
    return {"artist": a, "title": t, "duration": 180.0, "bitrate": 320, "album": "", "genre": ""}


lib = [{"path": old, "artist": "Andreas Gabalier", "title": "Andreas Gabalier - Hulapalu", "duration": 181.0, "bitrate": 320}]
check(ia.import_dir(root) == imp and ia.import_dir(root + "/") == imp, "Wartebereich liegt neben dem Musikordner")
check(ia.tops(root) == ["OLDIES", "U-MUSIK"], "Oberordner mit Artists zur Auswahl")
s = ia.scan(root, lambda: lib, "U-MUSIK", read=read)
by = {x["file"]: x for f in s["folders"] for x in f["songs"]}
check(s["n"] == 4 and [f["name"] for f in s["folders"]] == ["neu", "gibt es schon"], "alle Lieder je Ordner (feste Reihenfolge, neu zuerst)")
check(by["Hulapalu.mp3"]["dup"] and by["Hulapalu.mp3"]["dup"]["path"] == old and by["Hulapalu.mp3"]["exists"], "gibt es schon: Gegenstueck gefunden, Ziel belegt")
check(by["Mama.mp3"]["target"] == "U-MUSIK/Artists/Almklausi & Specktakel/Almklausi - Mama Laudaaa.mp3" or
      by["Mama.mp3"]["target"].startswith("U-MUSIK/Artists/Almklausi/"), "Vorschlag nach dem Muster Artists/Interpret/Interpret - Titel")
check(by["Neu.mp3"]["target"] == "U-MUSIK/Artists/Tobee/Tobee - Helikopter 117.mp3" and not by["Neu.mp3"]["dup"], "neuer Interpret: neuer Ordner")
check(ia.suggest("andreas gabalier", "X", "U-MUSIK", ia.artist_dirs(root, "U-MUSIK")).startswith("U-MUSIK/Artists/Andreas Gabalier/"),
      "vorhandener Interpreten-Ordner, Gross/klein egal")
check(ia.suggest("Almklausi, Specktakel", "Y", "U-MUSIK", {"almklausi": "Almklausi"}).startswith("U-MUSIK/Artists/Almklausi/"),
      "mehrere Interpreten: Ordner des ersten, wenn es ihn gibt")
check(ia.count(root) == 4, "Datenpflege zaehlt die Lieder im Wartebereich")
_w = os.path.join(ia.import_dir(root), "Miss Monique - Look at You.wav")
open(_w, "wb").write(b"RIFF")
open(os.path.join(ia.import_dir(root), "._Miss Monique - Look at You.wav"), "wb").write(b"x")
check(ia.count(root) == 5, "Fehlerbericht 12.11.2026: lose WAV zaehlt mit (macOS-Hilfsdateien ._ nicht)")
os.remove(_w)
os.remove(os.path.join(ia.import_dir(root), "._Miss Monique - Look at You.wav"))

# ---- ausfuehren ----
trashed = []


def trash(ps):
    for p in ps:
        trashed.append(p)
        os.remove(p)
    return 0


for bad in ("../x.mp3", "U-MUSIK/a.wav", "U-MUSIK/a:b.mp3", "x.mp3"):
    r = ia.apply(root, [{"path": os.path.join(imp, "neu", "Neu.mp3"), "do": "move", "target": bad}], trash=trash, stamp=None)
    check(r["moved"] == 0 and r["errors"], "Ziel abgelehnt: " + bad)
r = ia.apply(root, [{"path": "/etc/passwd", "do": "trash"}], trash=trash, stamp=None)
check(r["errors"] and not trashed, "nur Dateien aus dem Wartebereich")
r = ia.apply(root, [{"path": os.path.join(imp, "neu", "Neu.mp3"), "do": "move", "target": by["Neu.mp3"]["target"]},
                    {"path": os.path.join(imp, "gibt es schon", "Hulapalu.mp3"), "do": "move", "target": by["Hulapalu.mp3"]["target"]},
                    {"path": os.path.join(imp, "neu", "Weg.mp3"), "do": "trash"}], trash=trash, stamp=None)
check(r["moved"] == 2 and r["trashed"] == 1 and not r["errors"], "verschoben und weggeworfen: " + json.dumps(r["errors"]))
check(os.path.isfile(os.path.join(root, "U-MUSIK/Artists/Tobee/Tobee - Helikopter 117.mp3")) and not os.path.exists(os.path.join(imp, "neu", "Neu.mp3")),
      "neuer Ordner angelegt, Datei verschoben")
check(open(old, "rb").read() == b"alt" * 100 and os.path.isfile(old[:-4] + " (2).mp3"), "belegtes Ziel: nie ueberschrieben, neue mit (2)")
check(os.path.isdir(os.path.join(imp, "neu")), "leere Ordner im Wartebereich bleiben")

# ersetzen: altes in den Papierkorb, neues an seinen Platz
with open(os.path.join(imp, "neu", "Hula2.mp3"), "wb") as f:
    f.write(b"x" * 300)
r = ia.apply(root, [{"path": os.path.join(imp, "neu", "Hula2.mp3"), "do": "replace", "target": "U-MUSIK/Artists/Andreas Gabalier/Andreas Gabalier - Hulapalu.mp3",
                     "dup": old}], locate=lambda p: p if os.path.exists(p) else None, trash=trash, stamp=None)
check(r["replaced"] == 1 and old in trashed and open(old, "rb").read() == b"x" * 300, "ersetzen: altes im Papierkorb, neues an seinem Platz")

# ---- Musik-Server: Vorhoeren im Wartebereich, sonst nichts ----
loc = music_serve.Locator([], root=root)
with open(os.path.join(imp, "neu", "Hoer.mp3"), "wb") as f:
    f.write(b"h" * 20)
check(loc.locate(os.path.join(imp, "neu", "Hoer.mp3")) and loc.locate(os.path.join(stick, "anders.mp3")) is None
      and loc.locate(os.path.join(imp, "..", "musik-import", "neu", "Hoer.mp3")) is None, "Vorhoeren und Tags: nur Dateien im Wartebereich")
srv = music_serve.MusicServer([], port=0, root=root)
srv.start()
base = f"http://127.0.0.1:{srv.srv.server_address[1]}"
with urllib.request.urlopen(base + "/import?count=1", timeout=5) as rr:
    check(json.loads(rr.read())["n"] == ia.count(root), "Server: /import?count=1")
srv.stop()

# ---- lose Dateien einsortieren (Wunsch 10.11.2026) ----
INFO.update({"L1.mp3": ("Andreas Gabalier", "Hulapalu (Radio Edit)"), "L2.mp3": ("Andreas Gabalier", "Hulapalu"),
             "L3.mp3": ("Ikke Hüftgold", "Hulapalu"), "L4.mp3": ("Neu", "Ganz neu")})
DUR = {"L1.mp3": 182.0, "L2.mp3": 260.0, "L3.mp3": 180.0, "L4.mp3": 200.0}


def read2(p):
    d = read(p)
    d["duration"] = DUR.get(os.path.basename(p), 180.0)
    return d


for n in ("L1.mp3", "L2.mp3", "L3.mp3", "L4.mp3", "Andere - Datei.m4a", "Bild.jpg"):
    with open(os.path.join(imp, n), "wb") as f:
        f.write(b"z" * 10)
os.makedirs(os.path.join(imp, "gibt es schon"), exist_ok=True)
with open(os.path.join(imp, "gibt es schon", "L1.mp3"), "wb") as f:
    f.write(b"q")                                         # gleicher Name schon im Zielordner: nie ueberschreiben
lib2 = [{"path": old, "artist": "Andreas Gabalier", "title": "Andreas Gabalier - Hulapalu", "duration": 181.0, "bitrate": 320}]
check(ia.scan(root, lambda: lib2, "U-MUSIK", read=read2)["loose"] == 5, "Seite zaehlt die losen Dateien (Bild nicht)")
check(all(x["folder"] for f in ia.scan(root, lambda: lib2, "U-MUSIK", read=read2)["folders"] for x in f["songs"]), "lose Dateien stehen in keinem Reiter")
r = ia.sort_loose(root, lambda: lib2, read=read2, now=os.path.getmtime(os.path.join(imp, "L4.mp3")) + 1)
check(r["wait"] == 5 and not r["moved"], "eben erst kopiert: bleibt noch liegen")
r = ia.sort_loose(root, lambda: lib2, read=read2, now=os.path.getmtime(os.path.join(imp, "L4.mp3")) + 60)
check(r["moved"] == {"gibt es schon": 1, "gibt es schon, andere Länge": 1, "gleicher Titel, anderer Interpret": 1, "neu": 1, "nicht MP3": 1},
      "einsortiert nach den Regeln: " + json.dumps(r, ensure_ascii=False))
check(os.path.isfile(os.path.join(imp, "gibt es schon", "L1 (2).mp3")) and open(os.path.join(imp, "gibt es schon", "L1.mp3"), "rb").read() == b"q",
      "gleicher Name im Ziel: (2), nichts ueberschrieben")
check(os.path.isfile(os.path.join(imp, "Bild.jpg")) and ia.loose_files(root) == [], "Bilder bleiben liegen, keine Musik mehr lose")
s2 = ia.scan(root, lambda: lib2, "U-MUSIK", read=read2)
check(s2["other_n"] == 1 and s2["loose"] == 0, "Seite: andere Formate gezaehlt")
check("op: 'sort'" in open(os.path.join(ROOT, "pi", "static", "sm", "import.js"), encoding="utf-8").read(), "Seite: Knopf Einsortieren")

# ---- Seite ----
SM = os.path.join(ROOT, "pi", "static", "sm")
js = open(os.path.join(SM, "import.js"), encoding="utf-8").read()
html = open(os.path.join(SM, "import.html"), encoding="utf-8").read()
check("'/cover?p=' + encodeURIComponent(s.path)" in js and "class=\"cvimg" in js and "dupcv" in js, "Cover je Lied und beim vorhandenen Lied")
check("SM.playBar(audio" in js and "SM.tagEdit(" in js and "'/import'" in js, "Seite: Leiste zum Vorhoeren, Tag-Fenster, Ausfuehren")
check("const PAGE = 20" in js and "for (const { s } of shown().list)" in js and 'id="itabs"' in html and "data-tab=" in js,
      "Reiter je Ordner, Seiten zu 20, Ausfuehren nur fuer die gezeigte Seite")
check('class="s2lnav"' in html and 'data-title="h_import"' in html and "tagedit.js" in html, "Seite: Kopfleiste und Tag-Fenster geladen")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('path == "/musik/import"' in api and "'/musik/import'" in open(os.path.join(SM, "care.js"), encoding="utf-8").read(), "Route und Schritt in der Datenpflege")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("import_assist.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert import_assist.py")
# ---- Ordner anlegen, fremde Ordner (Archiv) einsortieren, nur vier Reiter (Wunsch 11.11.2026) ----
stick3 = os.path.join(tmp, "STICK3")
root3 = os.path.join(stick3, "musik")
imp3 = os.path.join(stick3, "musik-import")
os.makedirs(os.path.join(root3, "U-MUSIK", "Artists"))
s3 = ia.scan(root3, lambda: [], "U-MUSIK", read=read2)
check(sorted(s3["made"]) == sorted(["musik-import"] + list(ia.CATS)) and all(os.path.isdir(os.path.join(imp3, c)) for c in ia.CATS)
      and not s3.get("missing"), "fehlender Wartebereich und die vier Ordner beim Oeffnen angelegt: " + json.dumps(s3["made"], ensure_ascii=False))
check(ia.ensure_dirs(root3) == [], "zweites Mal: nichts mehr anzulegen")
check(ia.ensure_dirs(os.path.join(tmp, "WEG", "musik")) == [] and not os.path.exists(os.path.join(tmp, "WEG")),
      "Musikordner nicht da (Stick abgezogen): nichts anlegen")
arch = os.path.join(imp3, "Archiv")
for rel in ("Compilations/Chartmix 3/L1.mp3", "Compilations/Chartmix 3/L4.mp3", "Artists/X/L2.mp3", "Artists/X/Andere - Datei.m4a", "Artists/Y/cover.jpg"):
    os.makedirs(os.path.dirname(os.path.join(arch, rel)), exist_ok=True)
    with open(os.path.join(arch, rel), "wb") as f:
        f.write(b"z" * 10)
with open(os.path.join(arch, "Compilations", "Chartmix 3", ".DS_Store"), "wb") as f:
    f.write(b"x")
with open(os.path.join(arch, "Compilations", "Chartmix 3", "._L1.mp3"), "wb") as f:
    f.write(b"x")
os.makedirs(os.path.join(imp3, "neu", "Unterordner"))
with open(os.path.join(imp3, "neu", "Unterordner", "L3.mp3"), "wb") as f:
    f.write(b"z" * 10)
s3 = ia.scan(root3, lambda: lib2, "U-MUSIK", read=read2)
check([f["name"] for f in s3["folders"]] == ["neu"] and s3["foreign"] == 4 and s3["foreign_dirs"] == ["Archiv"],
      "Archiv ist kein Reiter (auch nicht seine Unterordner), seine Dateien gezaehlt; Unterordner von neu zaehlen zu neu: "
      + json.dumps([f["name"] for f in s3["folders"]], ensure_ascii=False))
l3 = s3["folders"][0]["songs"][0]
check(l3["file"] == "L3.mp3" and [c["artist"] for c in l3.get("rivals", [])] == ["Andreas Gabalier"] and l3["rivals"][0]["path"] and l3["dup"] is None,
      "gleicher Titel, anderer Interpret: das vorhandene Lied steht dabei (zum Vorhoeren): " + json.dumps(l3.get("rivals"), ensure_ascii=False))
js_r = open(os.path.join(ROOT, "pi", "static", "sm", "import.js"), encoding="utf-8").read()
check("data-pr=" in js_r and "s.rivals" in js_r and "Gleicher Titel: <b>" in js_r, "Seite: Konkurrenztitel mit Cover und Vorhoeren")
r3 = ia.sort_loose(root3, lambda: lib2, read=read2, now=9e9)
check(r3["moved"] == {"gibt es schon": 1, "gibt es schon, andere Länge": 1, "neu": 1, "nicht MP3": 1},
      "Archiv einsortiert, auch aus Unterordnern: " + json.dumps(r3, ensure_ascii=False))
check(not os.path.exists(os.path.join(arch, "Compilations")) and os.path.isfile(os.path.join(arch, "Artists", "Y", "cover.jpg"))
      and not os.path.exists(os.path.join(arch, "Artists", "X")) and r3["removed"] == 3,
      "leere Ordner geloescht (Finder-Reste zaehlen nicht), Ordner mit Bild bleibt")
check(os.path.isfile(os.path.join(imp3, "neu", "Unterordner", "L3.mp3")), "in den vier Ordnern wird nichts umgeraeumt")
js3 = open(os.path.join(ROOT, "pi", "static", "sm", "import.js"), encoding="utf-8").read()
check("data.foreign_dirs" in js3 and "r.removed" in js3 and "data.made" in js3, "Seite: Hinweis auf Archiv, geloeschte und neu angelegte Ordner")
# Fehlerbericht 11.11.2026: leere Archiv-Ordner blieben stehen (Begleitdateien ._Name kamen einen Augenblick spaeter mit)
for leaf in ("Archiv2/Artists/Abba", "Archiv2/Artists/Scooter"):
    os.makedirs(os.path.join(imp3, leaf))
with open(os.path.join(imp3, "Archiv2", "Artists", ".DS_Store"), "wb") as f:
    f.write(b"x")
_real_rmdir, _fails = os.rmdir, {"n": 0}


def _rmdir_once_busy(d):
    if d.endswith("Abba") and _fails["n"] == 0:
        _fails["n"] += 1
        raise OSError(66, "Directory not empty")
    _real_rmdir(d)


ia.os.rmdir = _rmdir_once_busy
_waits = []
n_, left_ = ia.clean_foreign(root3, sleep=_waits.append)
ia.os.rmdir = _real_rmdir
check(n_ == 4 and left_ == [] and _waits == [1.0] and not os.path.exists(os.path.join(imp3, "Archiv2")),
      "erster Versuch scheitert: nach einer Sekunde noch einmal, dann ist alles weg: %s %s" % (n_, left_))
os.makedirs(os.path.join(imp3, "Archiv3", "Leer"))
os.makedirs(os.path.join(imp3, "Archiv3", "Voll"))
with open(os.path.join(imp3, "Archiv3", "Voll", "X.mp3"), "wb") as f:
    f.write(b"z")
s4 = ia.scan(root3, lambda: lib2, "U-MUSIK", read=read2)
check(os.path.isdir(os.path.join(imp3, "Archiv3", "Leer")) and s4["foreign"] == 1, "Ordner mit Musik wird beim Oeffnen nicht angefasst")
os.remove(os.path.join(imp3, "Archiv3", "Voll", "X.mp3"))
s4 = ia.scan(root3, lambda: lib2, "U-MUSIK", read=read2)
check(s4["cleaned"] == 3 and not os.path.exists(os.path.join(imp3, "Archiv3")), "beim Oeffnen der Seite: leere Reste vom letzten Mal weg")
ia.os.rmdir = lambda d: (_ for _ in ()).throw(OSError(16, "Resource busy"))
os.makedirs(os.path.join(imp3, "Archiv4"))
n_, left_ = ia.clean_foreign(root3, tries=2, sleep=lambda s: None)
ia.os.rmdir = _real_rmdir
check(n_ == 0 and left_ and "busy" in left_[0][1], "bleibt einer stehen: Ordner und Grund werden gemeldet")
check("r.left && r.left.length" in open(os.path.join(ROOT, "pi", "static", "sm", "import.js"), encoding="utf-8").read(), "Seite zeigt, was stehen blieb")

# Fehlerbericht 11.11.2026: "Tom Lang - 13 - Tom Lang - Mediator" landete bei "gleicher Titel, anderer Interpret" (Power Traxx of Ibiza - 13)
byt_t = ia.lib_index([{"path": "/m/PT.mp3", "artist": "Power Traxx of Ibiza", "title": "13", "duration": 253.0},
                      {"path": "/m/TL.mp3", "artist": "Tom Lang", "title": "Mediator", "duration": 300.0},
                      {"path": "/m/MP.mp3", "artist": "Maximum P2 Dance", "title": "Maximum P2 Dance", "duration": 200.0}])
check(ia._title_key("13 - Tom Lang - Mediator", "Tom Lang") == "mediator" and ia._title_key("01. Hulapalu (Radio Edit)", "X") == "hulapalu"
      and ia._title_key("99 Luftballons", "Nena") == "99luftballons" and ia._title_key("1999", "Prince") == "1999",
      "Tracknummer und eigener Interpret am Anfang zaehlen nicht, Zahlen im Titel schon")
check(ia.classify(byt_t, "Tom Lang", "13 - Tom Lang - Mediator", 300.0)[0] == ia.CAT_SAME, "Tom Lang - Mediator: kein Treffer mehr bei Power Traxx - 13")
check(ia.classify(byt_t, "Maximum P2 Dance", "11 - Maximum P2 Dance - Maximum P2 Dance", 200.0)[0] == ia.CAT_NEW,
      "Titel gleich Interpret (Albumname in beiden Feldern): nichts zu vergleichen")
check(ia.bad_tag("Tom Lang", "13 - Tom Lang - Mediator") and ia.bad_tag("Maximum P2 Dance", "Maximum P2 Dance")
      and not ia.bad_tag("Nena", "99 Luftballons") and not ia.bad_tag("Prince", "1999"), "unbrauchbare Tags erkannt")
check("s.badtag" in open(os.path.join(ROOT, "pi", "static", "sm", "import.js"), encoding="utf-8").read(), "Seite: Hinweis Tag pruefen")

# Ordner "nicht MP3": ansehen und in MP3 umwandeln (Wunsch 12.11.2026)
import time                                  # noqa: E402
import convert_mp3 as cmp                    # noqa: E402
od = ia.other_dir(root)
os.makedirs(od, exist_ok=True)
open(os.path.join(od, "Miss Monique - Look at You.wav"), "wb").write(b"RIFF" + b"x" * 100)
open(os.path.join(od, "._Miss Monique - Look at You.wav"), "wb").write(b"x")
open(os.path.join(od, "liesmich.txt"), "wb").write(b"x")
fs = {f["name"]: f for f in ia.other_files(root)}
check({"Miss Monique - Look at You.wav", "liesmich.txt"} <= set(fs) and not any(n.startswith(".") for n in fs) and fs["Miss Monique - Look at You.wav"]["can"] and not fs["liesmich.txt"]["can"],
      "Liste 'nicht MP3' ohne macOS-Hilfsdateien, WAV umwandelbar, Text nicht")
for bad in ("../x.wav", ".hidden.wav", "fehlt.wav"):
    try:
        ia.other_path(root, bad)
        check(False, "kein Pfad von aussen: " + bad)
    except ValueError:
        pass


def fake_conv(src):
    dst = cmp.target_for(src)
    open(dst, "wb").write(b"ID3")
    return dst


ia._other_jobs = None
trashed = []
jb = ia.other_jobs(lambda: root, convert_fn=fake_conv, trash=lambda ps: trashed.extend(ps) or 0)
_ff, cmp.find_ffmpeg = cmp.find_ffmpeg, lambda: "/bin/true"
res = ia.other_convert(root, ["Miss Monique - Look at You.wav", "liesmich.txt"], jb)
cmp.find_ffmpeg = _ff
check(res["liesmich.txt"]["state"] == "err", "Text: wird nicht umgewandelt")
for _ in range(200):
    if jb.status(os.path.join(od, "Miss Monique - Look at You.wav")).get("state") == "ok":
        break
    time.sleep(0.01)
loose = [os.path.basename(x) for x in ia.loose_files(root)]
check("Miss Monique - Look at You.mp3" in loose and not os.path.exists(os.path.join(od, "Miss Monique - Look at You.mp3")),
      "fertige MP3 liegt lose im Wartebereich (fuer Einsortieren)")
check(trashed == [os.path.join(od, "Miss Monique - Look at You.wav")], "Wunsch 12.11.2026: MP3 fertig -> Original in den Papierkorb")
_ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
_ij = open(os.path.join(ROOT, "pi", "static", "sm", "import.js"), encoding="utf-8").read()
check('"other_convert", "other_trash"' in _ms and 'get("other")' in _ms and "fc.to_trash_many(paths)" in _ms, "Mac: Liste, Umwandeln, Original in den Papierkorb")
check("mac('/import?other=1')" in _ij and "op: 'other_convert'" in _ij and "op: 'other_trash'" in _ij and "SM.ask(" in _ij, "Seite: Ansehen und umwandeln, Papierkorb mit Rueckfrage")

check("else if (othRun) load();" in _ij and "else if (other.some(f => f.state === 'ok')) load();" not in _ij,
      "Fehlerbericht 12.11.2026: nach dem Umwandeln nur einmal neu laden (vorher Endlosschleife, Cover flimmerte)")

finish("test_import")
