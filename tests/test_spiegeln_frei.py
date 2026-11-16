"""Spiegeln mit freier Quelle und freiem Ziel (Wunsch 12.11.2026): Vorlagen Stick -> NAS, NAS -> Stick, Stick -> Ersatzstick,
Laufwerke aus "mount", Ordner-Auswahl, Papierkorb am Stick, Platz am Ziel, FAT32, Bestaetigung bei vielen Loeschungen, Sperre beim
Schreiben auf den Musik-Stick, Dauer je Weg."""
import os
import sys
import tempfile
import time

from _common import ROOT, check, finish

tmp = os.path.realpath(tempfile.mkdtemp())
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import nas_mirror as nm                      # noqa: E402
import stick_hold                            # noqa: E402

# frueheres Ziel und gemessene Geschwindigkeit werden zur Vorlage Stick -> NAS
nm.save_conf({"dest": "/Volumes/music", "mirrored": ["U-MUSIK"], "last": 5, "speed": 31e6})
c = nm.load_conf()
ps = nm.Mirror.pairs_of(c)
check([p["id"] for p in ps] == ["stick-nas", "nas-stick", "stick-ersatz", "stick-mac"] and ps[0]["dst"] == "/Volumes/music" and ps[0]["src"] == nm.MUSIC
      and ps[1]["src"] == "/Volumes/music" and ps[1]["dst"] == nm.MUSIC and ps[0]["mirrored"] == ["U-MUSIK"] and c["speeds"]["usb>net"] == 31e6,
      "vier feste Vorlagen, Stick -> NAS uebernimmt das fruehere Ziel und die Geschwindigkeit")

# Laufwerke aus "mount"
MOUNT = """/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)
/dev/disk3s3 on /Volumes/Recovery (apfs, local, journaled, nobrowse)
/dev/disk5s1 on /Volumes/Install X (hfs, local, nodev, nosuid, read-only, noowners, quarantine, mounted by m)
/dev/disk4s1 on /Volumes/USB STICK (msdos, local, nodev, nosuid, noowners, noatime, fskit)
//Markus%20Nepp@nas._smb._tcp.local/music on /Volumes/music (smbfs, nodev, nosuid, mounted by m)
"""
dv = nm.drives("/Volumes/USB STICK/musik", run=lambda: MOUNT, isdir=lambda p: True)
by = {d["name"]: d for d in dv}
check(set(by) == {"USB STICK", "music", "Install X", "Dieser Mac"} and dv[-1]["kind"] == "int" and by["music"]["kind"] == "net" and by["music"]["host"] == "nas"
      and by["USB STICK"]["fs_name"] == "FAT32" and by["USB STICK"]["music"] and by["Install X"]["ro"] and not by["USB STICK"]["ro"],
      "Laufwerke: ohne Systemplatte und Recovery, Netz, FAT32, Musik-Stick, schreibgeschuetzt")
check(dv[0]["name"] == "USB STICK" and dv[1]["name"] == "music", "Musik-Stick zuerst, dann die NAS")

for s_, d_ in (("/Volumes/A/x", "/Volumes/A/x"), ("/Volumes/A", "/Volumes/A/x"), ("/Volumes/A/x/y", "/Volumes/A/x")):
    try:
        nm.check_pair(s_, d_, volumes_only=False)
        check(False, "abgelehnt: " + s_ + " -> " + d_)
    except ValueError:
        check(True, "Quelle und Ziel ineinander abgelehnt: " + s_ + " -> " + d_)


def put(base, rel, data=b"x"):
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)


STICK, ERS, NAS = os.path.join(tmp, "STICK"), os.path.join(tmp, "ERSATZ"), os.path.join(tmp, "NAS")
root = os.path.join(STICK, "musik")
put(root, "U-MUSIK/a.mp3", b"a")
put(root, "OLDIES/o.mp3", b"o")
put(STICK, "musik-import/x.mp3", b"x")
os.makedirs(ERS)
put(NAS, "U-MUSIK/a.mp3", b"a")
put(NAS, "U-MUSIK/n.mp3", b"nur-nas")
put(NAS, "FLAC/f.flac", b"f")
put(NAS, "musik-import/y.mp3", b"y")


def vol(p):
    for v in (STICK, ERS, NAS):
        if nm.inside(p, v):
            return v
    return p.rstrip("/")


m = nm.Mirror(lambda: root)
m.volumes_only = False
m.vol_of = vol
m.kind_of = lambda p: "net" if nm.inside(p, NAS) else "usb"
m.drives = lambda: []

# Interne Festplatte des Musik-Rechners (Wunsch 13.11.2026): nur im Benutzerordner
_home = os.environ.get("HOME")
H = os.path.join(tmp, "home")
os.makedirs(os.path.join(H, "Music"))
os.environ["HOME"] = H
check(nm.home() == H and nm.allowed(H + "/Musik-Spiegel/musik") and nm.allowed("/Volumes/X/musik") and not nm.allowed(H)
      and not nm.allowed(H + "/Library/x") and not nm.allowed(H + "/.Trash") and not nm.allowed("/Users/andere/x") and not nm.allowed("/tmp/x"),
      "erlaubt: Laufwerke und Ordner im Benutzerordner, nicht er selbst, Library, Papierkorb, fremde Ordner")
check(nm.volume_of(H + "/Musik-Spiegel/musik") == H and nm.volume_of("/Volumes/X/musik") == "/Volumes/X", "Laufwerk des Mac-Ordners = Benutzerordner")
c_ = {"pairs": [{"id": "stick-nas", "src": nm.MUSIC, "dst": "/Volumes/music"}, {"id": "stick-ersatz", "src": nm.MUSIC, "dst": ""}, {"id": "eigen-1", "src": "a", "dst": "b"}]}
check([p["id"] for p in nm.Mirror.pairs_of(c_)] == ["stick-nas", "stick-ersatz", "stick-mac", "eigen-1"], "gespeicherte Vorlagen bekommen Stick -> Mac dazu")
try:
    nm.check_pair("/Volumes/X/musik", H, volumes_only=True)
    check(False, "Benutzerordner selbst als Ziel abgelehnt")
except ValueError:
    check(True, "Benutzerordner selbst als Ziel abgelehnt")
stick = os.path.join(tmp, "Volumes", "STICK")
os.makedirs(os.path.join(stick, "musik", "POP"))
_conf = nm.load_conf()
mm = nm.Mirror(lambda: os.path.join(stick, "musik"))
mm.volumes_only = False
mm.vol_of = lambda p: stick if nm.inside(p, stick) else nm.volume_of(p)
_dv = nm.drives("", run=lambda: "")
mm.drives = lambda: _dv
check(mm.mac_dir() == os.path.join(H, "Musik-Spiegel", "musik") and mm.resolve(nm.MAC) == mm.mac_dir(), "Ziel von Stick -> Mac: ~/Musik-Spiegel/musik")
mm.select("stick-mac")
st_ = mm.status()
check(st_["src"] == os.path.join(stick, "musik") and st_["dst"] == mm.mac_dir() and st_["dst_drive"] == H and not st_.get("pair_err")
      and st_["trash_name"] == "Spiegel-Papierkorb" and st_["route"] == "usb>int" and st_["speed"] == 30e6,
      "Stick -> Mac: Ziel noch nicht da, gilt trotzdem; Papierkorb im Benutzerordner, eigener Weg: " + str(st_.get("pair_err")) + " " + str(st_.get("route")))
check(mm.trash_dir(mm.mac_dir()) == os.path.join(H, "Spiegel-Papierkorb"), "Papierkorb ~/Spiegel-Papierkorb")
mm.set_drive("dst", H)
_p = {p["id"]: p for p in nm.load_conf()["pairs"]}
check(_p["stick-mac"]["dst"] == nm.MAC, "Laufwerk Dieser Mac waehlen: ~/Musik-Spiegel/musik")
mm.set_drive("src", H)
check(mm.status()["src"] == os.path.join(H, "Music"), "als Quelle ohne Spiegel-Ordner: ~/Music")
nm.save_conf(_conf)
os.environ["HOME"] = _home
mj_ = open(os.path.join(ROOT, "pi", "static", "sm", "mirror.js"), encoding="utf-8").read()
ms_ = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check("d.kind === 'int' ? 'interne Festplatte' :" in mj_ and 'if dv["kind"] != "usb":' in ms_, "Auswerfen bei der internen Festplatte grau und vom Server abgelehnt")

# NAS schlaeft (Freigabe nicht verbunden): gilt trotzdem als NAS, damit "NAS wecken" erscheint (Fehlerbericht 13.11.2026)
_conf2 = nm.load_conf()
c2 = dict(_conf2, smb_path="/Volumes/music", host="nas.local", mac="90:09:d0:0b:0a:c3")
nm.save_conf(c2)
mw = nm.Mirror(lambda: os.path.join(stick, "musik"))
mw.volumes_only = False
mw.drives = lambda: []
check(mw.kind_of("/Volumes/music") == "net" and mw.kind_of("/Volumes/music/x") == "net" and mw.kind_of("/Volumes/ANDERS") == "usb",
      "nicht verbundene NAS-Freigabe gilt als NAS")
mw.select("stick-nas")
_p2 = nm.load_conf()
_p2["pairs"][[p["id"] for p in _p2["pairs"]].index("stick-nas")]["dst"] = "/Volumes/music"
nm.save_conf(_p2)
mw._online = lambda h, p: False
st2 = mw.status()
check(st2["nas"] and not st2["online"] and st2["host"] == "nas.local", "NAS schlaeft: Zeile mit Wecken sichtbar: " + str((st2["nas"], st2["online"])))
nm.save_conf(_conf2)

# Groesse vor dem Probelauf (Wunsch 13.11.2026): Quelle minus was am Ziel schon liegt, rot, wenn schon das nicht passt
zv = os.path.join(tmp, "Volumes", "ZIEL")
os.makedirs(os.path.join(zv, "musik", "POP"))
_conf3 = nm.load_conf()
ms3 = nm.Mirror(lambda: os.path.join(stick, "musik"))
ms3.volumes_only = False
ms3.vol_of = lambda p: stick if nm.inside(p, stick) else zv if nm.inside(p, zv) else nm.volume_of(p)
FREE = {"v": 50e9}
ms3.drives = lambda: [{"path": stick, "name": "STICK", "kind": "usb", "fs": "msdos", "fs_name": "FAT32", "ro": False, "total": 128e9, "free": 1e9, "music": True},
                      {"path": zv, "name": "ZIEL", "kind": "usb", "fs": "msdos", "fs_name": "FAT32", "ro": False, "total": 128e9, "free": FREE["v"], "music": False}]
SZ = {os.path.join(stick, "musik", "POP"): 90e9, os.path.join(zv, "musik", "POP"): 20e9}
ms3.du = lambda p, lim=0: SZ.get(p, 0)
ms3.select("stick-ersatz")
ms3.set_folder("dst", os.path.join(zv, "musik"))
ms3.status()
for _ in range(200):
    if ms3.size_thread is None or not ms3.size_thread.is_alive():
        break
    time.sleep(0.01)
st3 = ms3.status()
check(st3["src_size"] == 90e9 and st3["dst_have"] == 20e9 and st3["pre_need"] == 70e9 and st3["pre_fits"] is False and not st3["sizing"],
      "vor dem Probelauf: 90 GB gewaehlt, 20 GB am Ziel, mindestens 70 GB, bei 50 GB frei: passt sicher nicht")
FREE["v"] = 80e9
check(ms3.status()["pre_fits"] is True, "bei 80 GB frei: passt voraussichtlich")
nm.save_conf(_conf3)
mjs3 = open(os.path.join(ROOT, "pi", "static", "sm", "mirror.js"), encoding="utf-8").read()
mh3 = open(os.path.join(ROOT, "pi", "static", "sm", "mirror.html"), encoding="utf-8").read()
check("passt sicher nicht" in mjs3 and "$('arrow').classList.toggle('no', !!noFit)" in mjs3 and '.arrow.no::after { content: "✕"' in mh3,
      "Seite: Mindestbedarf, rot, Pfeil durchgestrichen")

# Abgebrochener erster Lauf (Fehlerbericht 13.11.2026): die Auswahl bleibt, auch wenn am Ziel erst ein Teil liegt
q = os.path.join(tmp, "Volumes", "Q", "Firma")
z = os.path.join(tmp, "Volumes", "Z")
for n_ in ("Bilder", "Desktop", "Screenshots"):
    os.makedirs(os.path.join(q, n_))
os.makedirs(z)
_conf4 = nm.load_conf()
mf = nm.Mirror(lambda: os.path.join(stick, "musik"))
mf.volumes_only = False
mf.drives = lambda: []
mf.vol_of = lambda p: z if nm.inside(p, z) else os.path.dirname(q) if nm.inside(p, q) else p
mf.add_pair("Test")
mf.set_folder("src", q)
mf.set_folder("dst", z)
check(mf.status()["sel"] == ["Bilder", "Desktop", "Screenshots"], "Ziel leer: alle gewaehlt")
mf.rename_pair(mf.status()["pair"], "Firmen-PC")
check([p["name"] for p in mf.status()["pairs"] if p["id"] == mf.status()["pair"]] == ["Firmen-PC"], "eigene Vorlage umbenannt")
for _pid, _nm in (("stick-nas", "X"), (mf.status()["pair"], "  ")):
    try:
        mf.rename_pair(_pid, _nm)
        check(False, "abgelehnt: " + _pid)
    except ValueError:
        check(True, "Umbenennen abgelehnt: feste Vorlage oder leerer Name (" + _pid + ")")
mf.find = None
_fr = nm.find_rsync
nm.find_rsync = lambda: "/bin/false"
try:
    mf.start("plan")
except ValueError:
    pass
nm.find_rsync = _fr
if mf.thread is not None:
    mf.thread.join(10)
os.makedirs(os.path.join(z, "Bilder"))                 # erster Lauf nach "Bilder" abgebrochen
check(mf.status()["sel"] == ["Bilder", "Desktop", "Screenshots"], "nach Abbruch: Auswahl bleibt, nichts faellt still heraus: " + str(mf.status()["sel"]))
nm.save_conf(_conf4)

mh5 = open(os.path.join(ROOT, "pi", "static", "sm", "mirror.html"), encoding="utf-8").read()
mj5 = open(os.path.join(ROOT, "pi", "static", "sm", "mirror.js"), encoding="utf-8").read()
check('id="pnew"' in mh5 and "mac('/export', { op: 'mkdir', parent: pick.path" in mj5 and "showPick(d.path)" in mj5,
      "Ordner-Auswahl: Neuer Ordner anlegen und gleich oeffnen (Wunsch 13.11.2026)")
check("const off = av.filter(f => !f.sel);" in mj5 and 'id="offall"' in mj5, "nicht angehakte Ordner stehen als Hinweis da, mit Knopf Auch anhaken")
check("op: 'pair_rename'" in mj5 and 'id="pren"' in mj5 and 'op == "pair_rename"' in open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read(), "Knopf Umbenennen auf der Seite und am Server")
check("$('foldbox').open = true" in mj5 and "#foldbox > summary {" in mh5, "Ordnerliste als Knopf, klappt bei nicht angehakten Ordnern von selbst auf")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import export_files as ef  # noqa: E402
_eh = os.environ.get("HOME")
os.environ["HOME"] = os.path.join(tmp, "home")
_new = ef.mkdir(os.path.join(tmp, "home"), "Backup Firmen PC")
os.environ["HOME"] = _eh
check(os.path.isdir(_new) and _new.endswith("/Backup Firmen PC"), "Ordner mit Leerzeichen angelegt")

# NAS-Freigabe jetzt als anderer Benutzer verbunden: Adresse fuers Wecken wird uebernommen (13.11.2026)
_conf6 = nm.load_conf()
nm.save_conf(dict(_conf6, smb="smb://Markus%20Nepp@nas._smb._tcp.local/music", smb_path="/Volumes/music"))
mu = nm.Mirror(lambda: os.path.join(stick, "musik"))
mu.volumes_only = False
mu.drives = lambda: [{"path": "/Volumes/music", "name": "music", "kind": "net", "fs": "smbfs", "fs_name": "Netz (SMB)", "ro": False, "total": 1e12,
                      "free": 5e11, "host": "nas", "src": "//neppma@nas._smb._tcp.local/music", "music": False}]
mu.status()
check(nm.load_conf()["smb"] == "smb://neppma@nas._smb._tcp.local/music", "Wecken nimmt den neuen Benutzer")
nm.save_conf(_conf6)

if not nm.find_rsync():
    print("  (Spiegeln uebersprungen: rsync 3 fehlt hier)")
    finish("test_spiegeln_frei")
    sys.exit(0)

# Stick -> Ersatzstick: Ziel-Ordner gibt es noch nicht, Wartebereich daneben, Papierkorb ganz oben am Stick
m.select("stick-ersatz")
st = m.set_folder("dst", os.path.join(ERS, "musik"))
check(st["dst"] == os.path.join(ERS, "musik") and st["src_music"] and st["route"] == "usb>usb" and st["trash_name"] == nm.TRASH_LOCAL
      and st["speed"] == nm.DEFAULT_SPEEDS["usb>usb"] and not st["speed_measured"], "Ersatzstick: Weg usb>usb, angenommene Geschwindigkeit")
check(set(st["sel"]) == {"U-MUSIK", "OLDIES", "musik-import"}, "vom Musikordner: alle Ordner und der Wartebereich")
m.start("plan")
m.thread.join(30)
st = m.status()
check(st["state"] == "planned" and st["same"] and sum(f["new"] for f in st["folders"]) == 3 and not os.path.exists(os.path.join(ERS, "musik")),
      "Probelauf gegen einen Ordner, den es noch nicht gibt: zaehlt alles als neu, legt nichts an")
check(st["eta_s"] is not None and st["fits"], "Dauer geschaetzt, Platz passt")
m.start("run")
m.thread.join(30)
st = m.status()
check(st["state"] == "ok" and os.path.isfile(os.path.join(ERS, "musik/U-MUSIK/a.mp3")) and os.path.isfile(os.path.join(ERS, "musik-import/x.mp3")),
      "Ersatzstick gespiegelt, musik-import neben dem Musikordner: " + str(st.get("error", "")))
os.remove(os.path.join(root, "U-MUSIK/a.mp3"))
put(root, "U-MUSIK/b.mp3", b"b")
m.start("plan")
m.thread.join(30)
m.start("run")
m.thread.join(30)
day = time.strftime("%Y-%m-%d")
check(os.path.isfile(os.path.join(ERS, nm.TRASH_LOCAL, "Spiegel-" + day, "musik", "U-MUSIK", "a.mp3"))
      and not os.path.exists(os.path.join(ERS, "musik/U-MUSIK/a.mp3")), "Geloeschtes am Stick in Spiegel-Papierkorb/Spiegel-Datum")
check(nm.load_conf()["pairs"][2]["last"] > 0 and "OLDIES" in nm.load_conf()["pairs"][2]["mirrored"], "Vorlage merkt sich Zeit und Ordner")

# Auswahl: abgehakt bleibt ab, neuer Ordner an der Quelle kommt dazu
m.set_sel(["U-MUSIK", "musik-import"])
put(root, "NEU/z.mp3")
check(set(m.status()["sel"]) == {"U-MUSIK", "musik-import", "NEU"}, "Haken gemerkt, neuer Ordner gewaehlt")
m.start("plan")
m.thread.join(30)
m.set_sel(["U-MUSIK"])
try:
    m.start("run")
    check(False, "andere Auswahl: abgelehnt")
except ValueError as e:
    check("Probelauf" in str(e), "Auswahl geaendert: erst wieder der Probelauf")

# NAS -> Stick: nur Ordner, die es am Stick schon gibt; der Wartebereich der NAS kommt neben den Musikordner
m.select("nas-stick")
m.set_folder("src", NAS)
st = m.status()
check(st["dst_music"] and set(st["sel"]) == {"U-MUSIK", "musik-import"} and "FLAC" not in st["sel"] and st["route"] == "net>usb",
      "NAS -> Stick: FLAC nicht gewaehlt (gibt es am Stick nicht): " + str(st["sel"]))
check(dict((n, t) for n, _s, t in m.items(NAS, root))["musik-import"] == os.path.join(STICK, "musik-import"), "Wartebereich neben den Musikordner")
holds, done = [], []
_orig_hold, _orig_vol = stick_hold.hold, nm.stick_vol
stick_hold.hold = lambda v, ejected=False, by="": (holds.append((v, by)), _orig_hold(v, ejected, by))
nm.stick_vol = lambda p: STICK if nm.inside(p, STICK) else ""
m.on_done = lambda: done.append(1)
m.start("plan")
m.thread.join(30)
check(m.status()["to_music"], "Ziel ist der Musik-Stick: Hinweis")
m.start("run")
m.thread.join(30)
st = m.status()
check(st["state"] == "ok" and holds == [(STICK, "spiegeln")] and not stick_hold.state() and done == [1],
      "auf den Musik-Stick: gesperrt (Analyse ruht), danach frei und Ordner neu eingelesen: " + str(holds))
check(os.path.isfile(os.path.join(root, "U-MUSIK/n.mp3")) and os.path.isfile(os.path.join(STICK, "musik-import/y.mp3"))
      and not os.path.exists(os.path.join(root, "FLAC")), "Stick hat den Stand der NAS, FLAC nicht mitgekommen")
stick_hold.hold = _orig_hold
nm.stick_vol = _orig_vol
stick_hold.hold(STICK)                                      # fremde Sperre (Auswerfen): Spiegeln haelt an
check(m._blocked((NAS, root)), "Stick wird ausgeworfen: Spiegeln hoert auf")
stick_hold.hold(STICK, by="spiegeln")
check(not m._blocked((NAS, root)), "eigene Sperre haelt nicht an")
stick_hold.release()

# viele Loeschungen: eigene Bestaetigung
for k in range(25):
    put(NAS, f"U-MUSIK/viel{k}.mp3")
m.select("stick-nas")
m.set_folder("dst", NAS)
m.set_sel(["U-MUSIK"])
m.start("plan")
m.thread.join(30)
st = m.status()
check(st["del_total"] >= 25, "Probelauf zaehlt die Loeschungen")
try:
    m.start("run")
    check(False, "ohne Bestaetigung abgelehnt")
except ValueError as e:
    check("bestätigen" in str(e), "ab 20 Loeschungen: ohne Bestaetigung kein Spiegeln")
# zu wenig Platz, FAT32
m.drive_of = lambda p: {"path": NAS, "name": "NAS", "free": 10, "total": 100, "fs": "msdos", "kind": "net", "ro": False} if nm.inside(p, NAS) else None
check(not m.status()["fits"], "zu wenig Platz erkannt")
try:
    m.start("run", confirm_del=True)
    check(False, "zu wenig Platz: abgelehnt")
except ValueError as e:
    check("Platz" in str(e), "zu wenig Platz: Spiegeln startet nicht")
m.drive_of = lambda p: {"path": NAS, "name": "NAS", "free": None, "total": None, "fs": "msdos", "kind": "usb", "ro": True} if nm.inside(p, NAS) else None
try:
    m.set_folder("dst", os.path.join(NAS, "U-MUSIK"))
    check(False, "schreibgeschuetzt abgelehnt")
except ValueError:
    check(True, "schreibgeschuetztes Laufwerk kann kein Ziel sein")
check(nm.parse(">f+++++++++|5000000000|A/gross.wav\n")["big"] == 1, "Dateien ab 4 GB gezaehlt (FAT32)")
del m.drive_of
m.start("run", confirm_del=True)
m.thread.join(30)
check(m.status()["state"] == "ok" and not os.path.exists(os.path.join(NAS, "U-MUSIK/viel3.mp3")), "mit Bestaetigung gespiegelt")

# Rest der Dauer waehrend des Laufs
m.st = {"state": "run", "pair_id": "stick-nas", "src_p": root, "dst_p": NAS, "t0": time.time() - 100,
        "folders": [{"name": "A", "bytes": 1e9}, {"name": "B", "bytes": 3e9}], "done": ["A"]}
check(abs(m.status()["rest_s"] - 300) < 15, "noch etwa: aus dem schon Geschafften (1 GB in 100 s, 3 GB offen = 300 s): " + str(m.status()["rest_s"]))

# eigene Vorlage
m.st = {"state": "idle"}
st = m.add_pair("Stick → Platte")
check(st["pair"] == "eigen-1" and st["src_music"], "eigene Vorlage uebernimmt Quelle und Ziel")
try:
    m.del_pair("stick-nas")
    check(False, "feste Vorlage bleibt")
except ValueError:
    check(True, "feste Vorlagen lassen sich nicht loeschen")
check(m.del_pair("eigen-1")["pair"] == "stick-nas", "eigene Vorlage geloescht")

SM = os.path.join(ROOT, "pi", "static", "sm")
js = open(os.path.join(SM, "mirror.js"), encoding="utf-8").read()
html = open(os.path.join(SM, "mirror.html"), encoding="utf-8").read()
check('id="ssrc"' in html and 'id="sdst"' in html and 'class="arrow"' in html and 'id="space"' in html and 'id="bstop" disabled' in html,
      "Seite: Auswahllisten, Pfeil, Platz am Ziel, Anhalten am festen Platz")
check("op: 'drive', side: 'src'" in js and "op: 'pair'" in js and "op: 'sel'" in js and "confirm_del: many" in js and "rest_s" in js
      and "fertig gegen" in js and "speed_measured" in js, "Seite: Vorlagen, Laufwerke, Ordner, Bestaetigung, Dauer")
ms = open(os.path.join(ROOT, "mac", "mixxx_bridge", "music_serve.py"), encoding="utf-8").read()
check('op == "drive"' in ms and 'op == "pair_add"' in ms and "confirm_del=bool(" in ms, "Mac: Befehle fuer Vorlagen, Laufwerke, Bestaetigung")
finish("test_spiegeln_frei")
