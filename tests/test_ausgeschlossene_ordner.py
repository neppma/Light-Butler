"""Ausgeschlossene Ordner im Musikordner (Wunsch 10.11.2026): was im Panel unter Einstellungen -> Verbindungen steht, liest der
Light-Butler am Mac nicht ein, prueft nicht, analysiert nicht und liefert es nicht zum Vorhoeren."""
import os
import socket
import sys
import tempfile
import unicodedata

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import music_excl                            # noqa: E402
import folder_lib                            # noqa: E402
import music_serve                           # noqa: E402
import mixxx_bridge as mb                    # noqa: E402
from file_check import FileCheck             # noqa: E402

# ---- Liste bereinigen ----
check(music_excl.clean(["APRES SKI", " FUN/ ", "", "fun", "a/../b", "/Volumes/X/Y/", "./x", "KINDER//Duplicates"])
      == ["APRES SKI", "FUN", "/Volumes/X/Y", "KINDER/Duplicates"], "bereinigt: Leerzeilen, Doppelte, '..', '/' am Ende")
check(music_excl.clean("A\nB\n") == ["A", "B"] and music_excl.clean(None) == [] and music_excl.clean([3, "x"]) == ["x"], "Text oder Liste")
check(len(music_excl.clean(["d%d" % i for i in range(300)])) == music_excl.MAX_LINES, "hoechstens 100")

# ---- merken ----
check(music_excl.get() == [], "ohne Datei: leer")
v0 = music_excl.version()
music_excl.set_list(["APRES SKI", "KINDERMUSIK/Duplicates"])
check(music_excl.version() == v0 + 1, "neue Liste zaehlt die Fassung hoch")
music_excl.set_list(["APRES SKI", "KINDERMUSIK/Duplicates"])
check(music_excl.version() == v0 + 1, "gleiche Liste: keine neue Fassung")
music_excl.reset()
check(music_excl.get() == ["APRES SKI", "KINDERMUSIK/Duplicates"], "nach dem Neustart aus ausschluss.json")

# ---- Pfade pruefen ----
root = "/Volumes/USB STICK/musik"
f = music_excl.matcher(root)
check(f(root + "/APRES SKI/Lied.mp3") and f(root + "/apres ski/x/y.mp3") and f(root + "/APRES SKI"), "im Ordner, Gross/klein egal")
check(not f(root + "/APRES SKIER/Lied.mp3") and not f(root + "/U-MUSIK/APRES SKI/a.mp3") and not f("/anders/APRES SKI/a.mp3"),
      "nur genau dieser Ordner im Musikordner")
check(f(root + "/KINDERMUSIK/Duplicates/a.mp3") and not f(root + "/KINDERMUSIK/Artists/a.mp3"), "Unterordner")
music_excl.set_list(["Klangräume"])
check(music_excl.is_excluded(root + "/" + unicodedata.normalize("NFD", "Klangräume") + "/a.mp3", root), "Umlaut zerlegt gilt gleich")
check(not music_excl.is_excluded(root + "/Klangräume/a.mp3", ""), "ohne Musikordner greifen relative Eintraege nicht")

# ---- Ordner-Liste und Dateipruefung ----
mdir = os.path.join(tmp, "musik")
for d in ("APRES SKI", "U-MUSIK", "KINDERMUSIK/Duplicates", "KINDERMUSIK/Artists"):
    os.makedirs(os.path.join(mdir, d))
for p in ("APRES SKI/a.mp3", "APRES SKI/Thumbs.db", "U-MUSIK/b.mp3", "KINDERMUSIK/Duplicates/c.mp3", "KINDERMUSIK/Artists/d.mp3"):
    with open(os.path.join(mdir, p), "wb") as fh:
        fh.write(b"\0" * 10)
music_excl.set_list(["APRES SKI", "KINDERMUSIK/Duplicates"])
got = sorted(os.path.relpath(p, mdir).replace(os.sep, "/") for p in folder_lib.walk_mp3(mdir))
check(got == ["KINDERMUSIK/Artists/d.mp3", "U-MUSIK/b.mp3"], "Ordner-Liste liest ausgeschlossene Ordner nicht ein")
fl = folder_lib.FolderLib(base=os.path.join(tmp, "fl"))
fl.root, fl.t, fl.excl_ver = mdir, 1e12, music_excl.version()
check(not fl.due(mdir, now=1e12), "gleiche Liste: kein neuer Durchgang")
music_excl.set_list(["APRES SKI"])
check(fl.due(mdir, now=1e12), "andere Liste: gleich neu einlesen")
music_excl.set_list(["APRES SKI", "KINDERMUSIK/Duplicates"])

fc = FileCheck(lambda: mdir, lambda: [], lambda p: p, trash=lambda ps: None, sleep=lambda s: None)
fc._scan()
seen = [os.path.relpath(p, mdir).replace(os.sep, "/") for ps in fc.index.values() for p in ps] + [os.path.relpath(p, mdir).replace(os.sep, "/") for p in fc.junk + fc.other]
check(seen and not any(x.startswith("APRES SKI") or x.startswith("KINDERMUSIK/Duplicates") for x in seen),
      "Dateipruefung schaut nicht hinein (kein Thumbs.db, keine Namen)")
check(any(x == "U-MUSIK/b.mp3" for x in seen), "der Rest wird geprueft")

# ---- Vorhoeren ----
loc = music_serve.Locator([os.path.join(mdir, "APRES SKI/a.mp3"), os.path.join(mdir, "U-MUSIK/b.mp3")], root=mdir)
check(loc.locate(os.path.join(mdir, "APRES SKI/a.mp3")) is None and loc.locate(os.path.join(mdir, "U-MUSIK/b.mp3")), "Vorhoeren liefert sie nicht")

# ---- Mixxx-Lieder in der Liste ----
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
lib = [{"path": "/Mixxx/musik/APRES SKI/a.mp3", "duration": 100.0, "bpm": 120.0, "kid": 1},
       {"path": "/Mixxx/musik/U-MUSIK/b.mp3", "duration": 100.0, "bpm": 121.0, "kid": 1}]
fw = mb.Forwarder(lib, s, ("127.0.0.1", 9), analysis_dir=os.path.join(tmp, "an"), path_map=[("/Mixxx/musik", mdir)], analyze=False)
out = fw.excl_filter(lib, mdir)
check([r["path"] for r in out] == ["/Mixxx/musik/U-MUSIK/b.mp3"] and fw.excl_n == 1, "Mixxx-Lied im ausgeschlossenen Ordner faellt weg (Pfad am Mac)")


class FL:
    def __init__(self):
        self.ver, self.songs, self.calls = 1, [{"path": os.path.join(mdir, "KINDERMUSIK/Artists/d.mp3")}], []

    def due(self, root, now=None):
        return False


fw.folder, fw.folder_root = FL(), mdir
fw.folder_tick()
check(sorted(r["path"] for r in fw.lib) == sorted(["/Mixxx/musik/U-MUSIK/b.mp3", os.path.join(mdir, "KINDERMUSIK/Artists/d.mp3")]),
      "folder_tick: Liste ohne ausgeschlossene Lieder")
music_excl.set_list([])
fw.folder_tick()
check(len(fw.lib) == 3, "Ordner aus der Liste genommen: Lied ist wieder da")

# ---- Liste vom Pi ----
srv = music_serve.MusicServer([], port=0)
srv.apply_conf({"root": mdir, "excl": ["FUN", "FREE"]})
check(music_excl.get() == ["FUN", "FREE"], "Bruecke uebernimmt die Liste vom Pi")
srv.apply_conf({"root": mdir})
check(music_excl.get() == ["FUN", "FREE"], "alter Pi ohne Liste: bleibt wie gemerkt")
rows = music_excl.status(mdir, ["APRES SKI", "GIBTS NICHT"])
check(rows == [{"dir": "APRES SKI", "found": True, "mp3": 1}, {"dir": "GIBTS NICHT", "found": False, "mp3": 0}], "Stand je Ordner fuer die Einstellungen")
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('u.path == "/excl"' in src, "Mac liefert den Stand unter /excl")

for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("music_excl.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert music_excl.py")

finish("test_ausgeschlossene_ordner")
