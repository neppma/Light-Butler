"""Stick auf die NAS spiegeln (Wunsch 10.11.2026): Probelauf zaehlt, Spiegeln macht die Ordner gleich, Geloeschtes und Ersetztes in
#recycle, Ordner nur auf der NAS bleiben, aufgeloeste Ordner nur mit Haken in den Papierkorb, der Stick bleibt unveraendert."""
import os
import subprocess
import sys
import tempfile
import time

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import nas_mirror as nm                      # noqa: E402

check(nm.parse(">f+++++++++|100|A/a.mp3\n>f.st......|50|A/b.mp3\n*deleting  |0|A/c.mp3\n*deleting  |0|A/D/\ncd+++++++++|0|A/E/\n")
      == {"new": 1, "replace": 1, "delete": 1, "bytes": 150, "deleted": ["A/c.mp3"]}, "rsync-Ausgabe zaehlen")
for bad in ("/Users/x", "/Volumes", "/Volumes/GIBTS-NICHT-123"):
    try:
        nm.check_dest(bad, "/Volumes/USB STICK/musik")
        check(False, "Ziel abgelehnt: " + bad)
    except ValueError:
        check(True, "Ziel abgelehnt: " + bad)

# Abschaltzeit der NAS und Wake-on-LAN (Wunsch 10.11.2026)
noon = time.mktime((2026, 11, 10, 23, 30, 0, 0, 0, -1))
check(round(nm.seconds_until("00:00", noon)) == 1800 and nm.seconds_until("", noon) is None and nm.seconds_until("25:00", noon) is None,
      "Zeit bis zur Abschaltung (Mitternacht), leer = nie")
st = {"t0": 0, "t1": 120, "folders": [{"bytes": 25e6 * 600}]}
check(round(nm.estimate_s(st, 25e6)) == 720, "Dauer: Probelauf-Zeit plus Menge durch Geschwindigkeit")
check(nm.norm_mac("90:9:d0:b:a:c3") == "90:09:d0:0b:0a:c3" and len(nm.wol_packet("90:09:d0:0b:0a:c3")) == 102
      and nm.wol_packet("90-09-d0-0b-0a-c3")[:6] == b"\xff" * 6, "Wake-on-LAN-Paket")
for bad in ("90:09", "zz:09:d0:0b:0a:c3"):
    try:
        nm.norm_mac(bad)
        check(False, "MAC abgelehnt: " + bad)
    except ValueError:
        check(True, "MAC abgelehnt: " + bad)
sent = []
mw = nm.Mirror(lambda: "/x")
try:
    mw.wake(send=lambda d: None)
    check(False, "ohne NAS in den Einstellungen: abgelehnt")
except ValueError:
    check(True, "ohne NAS in den Einstellungen: Wecken mit Hinweis abgelehnt")
nm.from_pi({"host": "nas.test", "mac": "90:09:d0:0b:0a:c3", "off_at": "00:00"})
nm.reachable = lambda host, port=445, timeout=2.0: True
mw.wake(send=sent.append)
time.sleep(0.3)
check(sent == [nm.wol_packet("90:09:d0:0b:0a:c3")] and mw.status()["wake"]["state"] in ("ok", "nomount"), "NAS wecken schickt das Paket an die MAC")
nm.from_pi({"host": "nas.test", "mac": "90:09:d0:0b:0a:c3", "off_at": ""})   # die Laeufe unten nicht von der echten Uhrzeit abhaengig
try:
    mw.set_conf(off_at="halb zwoelf")
    check(False, "Uhrzeit abgelehnt")
except ValueError:
    check(True, "falsche Uhrzeit abgelehnt")

if not nm.find_rsync():
    print("  (Spiegeln uebersprungen: rsync 3 fehlt hier)")
    finish("test_nas_spiegeln")
    sys.exit(0)

stick = os.path.join(tmp, "STICK")
root = os.path.join(stick, "musik")
nas = os.path.join(tmp, "NAS")


def put(base, rel, data):
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)


put(root, "U-MUSIK/a.mp3", b"neu-a")
put(root, "U-MUSIK/b.mp3", b"b")
put(stick, "musik-import/neu/x.mp3", b"x")
put(nas, "U-MUSIK/b.mp3", b"b")
put(nas, "U-MUSIK/alt.mp3", b"alt")                      # nur auf der NAS im gespiegelten Ordner: kommt weg (Papierkorb)
put(nas, "U-MUSIK/a.mp3", b"alt-a")                      # andere Fassung: wird ersetzt
put(nas, "OLDIES/o.mp3", b"o")                           # am Stick aufgeloest
put(nas, "FLAC/f.flac", b"f")                            # nur auf der NAS: bleibt
os.makedirs(os.path.join(nas, "#recycle"))                # Synology: Papierkorb der Freigabe
os.utime(os.path.join(nas, "U-MUSIK/a.mp3"), (time.time() - 86400,) * 2)   # aeltere Fassung auf der NAS (gleich gross)
os.utime(os.path.join(nas, "U-MUSIK/b.mp3"), (os.path.getmtime(os.path.join(root, "U-MUSIK/b.mp3")),) * 2)
before = {p: open(os.path.join(dp, p), "rb").read() for dp, _ds, fs in os.walk(stick) for p in fs}

m = nm.Mirror(lambda: root)
m.volumes_only = False
NAS_R = os.path.realpath(nas)
m.kind_of = lambda p: "net" if nm.inside(os.path.realpath(p), NAS_R) else "usb"   # im Test ist die NAS ein Ordner
m.set_dest(nas)
m.start("plan")
m.thread.join(30)
st = m.status()
by = {f["name"]: f for f in st["folders"]}
check(st["state"] == "planned" and set(by) == {"U-MUSIK", "musik-import"}, "Probelauf: Ordner des Sticks und der Wartebereich")
check(by["U-MUSIK"]["new"] == 0 and by["U-MUSIK"]["replace"] == 1 and by["U-MUSIK"]["delete"] == 1 and by["U-MUSIK"]["deleted"] == ["alt.mp3"],
      "Probelauf zaehlt: 1 ersetzen, 1 loeschen: " + str(by["U-MUSIK"]))
check(by["musik-import"]["new"] == 1 and not by["musik-import"]["exists"], "Wartebereich ist neu auf der NAS")
check(st["gone"] == ["OLDIES"], "aufgeloester Ordner wird angeboten (aus der Liste vom ersten Mal)")
check(open(os.path.join(nas, "U-MUSIK/a.mp3"), "rb").read() == b"alt-a" and os.path.exists(os.path.join(nas, "U-MUSIK/alt.mp3")), "Probelauf aendert nichts")

m.start("run", gone=[])
m.thread.join(30)
st = m.status()
check(st["state"] == "ok", "gespiegelt: " + str(st.get("error", "")))
check(open(os.path.join(nas, "U-MUSIK/a.mp3"), "rb").read() == b"neu-a" and not os.path.exists(os.path.join(nas, "U-MUSIK/alt.mp3"))
      and os.path.isfile(os.path.join(nas, "musik-import/neu/x.mp3")), "NAS hat den Stand des Sticks")
day = time.strftime("%Y-%m-%d")
rec = os.path.join(nas, "#recycle", "Spiegel-" + day, "U-MUSIK")
check(open(os.path.join(rec, "a.mp3"), "rb").read() == b"alt-a" and os.path.isfile(os.path.join(rec, "alt.mp3")), "Ersetztes und Geloeschtes im Papierkorb der NAS")
check(os.path.isfile(os.path.join(nas, "FLAC/f.flac")) and os.path.isfile(os.path.join(nas, "OLDIES/o.mp3")), "nur NAS und ohne Haken: bleibt")
check({p: open(os.path.join(dp, p), "rb").read() for dp, _ds, fs in os.walk(stick) for p in fs} == before, "am Stick aendert sich nichts")
check("OLDIES" in nm.load_conf()["mirrored"], "nicht weggeworfener Ordner bleibt in der Liste")

m.start("plan")
m.thread.join(30)
check(m.status()["gone"] == ["OLDIES"] and sum(f["new"] + f["replace"] + f["delete"] for f in m.status()["folders"]) == 0, "zweiter Probelauf: nichts zu tun")
m.start("run", gone=["OLDIES", "FLAC", "../x"])
m.thread.join(30)
check(not os.path.exists(os.path.join(nas, "OLDIES")) and os.path.isfile(os.path.join(nas, "#recycle", "Spiegel-" + day, "OLDIES", "o.mp3"))
      and os.path.isfile(os.path.join(nas, "FLAC/f.flac")), "mit Haken: aufgeloester Ordner in den Papierkorb, FLAC bleibt (war nie gespiegelt)")
check("OLDIES" not in nm.load_conf()["mirrored"], "aus der Liste")
m.start("plan")
m.thread.join(30)
nm.save_conf(dict(nm.load_conf(), off_at="00:00"))
m.now = lambda: time.mktime((2026, 11, 10, 23, 59, 30, 0, 0, -1))   # 30 s vor Mitternacht
check(m.status()["too_long"], "kurz vor der Abschaltung: zu knapp")
try:
    m.start("run")
    check(False, "zu knapp: abgelehnt")
except ValueError as e:
    check("Reicht nicht mehr" in str(e), "zu knapp vor der Abschaltung: Spiegeln startet nicht")
check(m.status()["plan_blocked"], "30 s vor der Abschaltung: Probelauf gesperrt")
try:
    m.st = {"state": "idle"}
    m.start("plan")
    check(False, "Probelauf zu knapp: abgelehnt")
except ValueError as e:
    check("keinen Probelauf mehr" in str(e), "Probelauf kurz vor der Abschaltung abgelehnt")
_c = nm.load_conf()
next(p for p in _c["pairs"] if p["id"] == "stick-nas")["plan_s"] = 600
nm.save_conf(_c)
m.now = lambda: time.mktime((2026, 11, 10, 23, 52, 0, 0, 0, -1))      # 8 min vorher, letzter Probelauf dauerte 10 min
check(m.status()["plan_blocked"] and m.status()["plan_need_s"] == 600, "Sperre richtet sich nach der Dauer des letzten Probelaufs")
m.now = lambda: time.mktime((2026, 11, 10, 22, 0, 0, 0, 0, -1))
check(not m.status()["plan_blocked"], "genug Zeit: Probelauf frei")
m.now = time.time
nm.save_conf(dict(nm.load_conf(), off_at=""))
m.st = {"state": "ok"}
try:
    m.start("run")
    check(False, "ohne Probelauf: abgelehnt")
except ValueError:
    check(True, "ohne neuen Probelauf: Spiegeln abgelehnt")

SM = os.path.join(ROOT, "pi", "static", "sm")
js = open(os.path.join(SM, "mirror.js"), encoding="utf-8").read()
html = open(os.path.join(SM, "mirror.html"), encoding="utf-8").read()
check("op: 'wake'" in js and "too_long" in js and 'id="nasinfo"' in html and "$('bwake').hidden = !!st.online" in js and "op: 'plan'" in js and "op: 'run', gone" in js and "/dirs?p=" in js and 'data-title="h_mirror"' in html, "Seite: Ziel, Probelauf, Spiegeln, Kopfleiste")
check("href: '/musik/spiegeln', tool: true" in open(os.path.join(SM, "care.js"), encoding="utf-8").read(), "Werkzeug in der Datenpflege")
for sh in ("mac/helper/install_helper.sh", "mac/mixxx_bridge/install_launcher.sh"):
    check("nas_mirror.py" in open(os.path.join(ROOT, sh), encoding="utf-8").read(), sh + " installiert nas_mirror.py")
# NAS-Angaben aus den Einstellungen (nicht im Quelltext)
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "nas_mirror.py"), encoding="utf-8").read()
check("nas.fritz" ".box" not in src and "90:09:d0" not in src, "keine NAS-Adresse im Quelltext")
check(nm.from_pi({"host": "nas2.local", "mac": "AA-BB-CC-DD-EE-01", "off_at": "23:30"}) and nm.load_conf()["mac"] == "aa:bb:cc:dd:ee:01"
      and not nm.from_pi({"host": "nas2.local", "mac": "aa:bb:cc:dd:ee:01", "off_at": "23:30"}), "Angaben vom Pi uebernommen (nur bei Aenderung)")
sys.path.insert(0, os.path.join(ROOT, "pi"))
from showman.api import ShowManager  # noqa: E402
check(ShowManager.music_nas_clean({"host": "nas.local", "mac": "90:9:d0:b:a:c3", "off_at": "0:00"}) == {"host": "nas.local", "mac": "90:09:d0:0b:0a:c3", "off_at": "00:00"},
      "Pi: NAS-Angaben geprueft und vereinheitlicht")
for bad in ({"host": "a b"}, {"mac": "xx"}, {"off_at": "25:00"}):
    try:
        ShowManager.music_nas_clean(bad)
        check(False, "abgelehnt: " + str(bad))
    except ValueError:
        check(True, "Pi lehnt ab: " + str(bad))
# Fehlerbericht 12.11.2026: rsync schrieb einen Dateinamen mit abgeschnittenem Umlaut (Byte 0xcc) auf stderr, die Spiegelung
# stuerzte beim Lesen ab und blieb auf "laeuft" stehen
import sys as _sys                                       # noqa: E402
m2 = nm.Mirror(lambda: root)
m2.volumes_only = False
m2.set_dest(nas)
m2.popen = lambda cmd, **kw: subprocess.Popen([_sys.executable, "-c", "import sys; sys.stderr.buffer.write(b'file has vanished: Kings of Gu\\xcc'); sys.exit(24)"], **kw)
m2.now = time.time
nm.save_conf(dict(nm.load_conf(), off_at=""))
m2.start("plan")
m2.thread.join(30)
check(m2.status()["state"] == "planned", "Probelauf mit unlesbaren Bytes: kein Absturz")
m2.start("run", gone=[])
m2.thread.join(30)
check(m2.status()["state"] == "ok", "unlesbare Bytes in der rsync-Meldung: kein Absturz, Spiegeln laeuft durch: " + str(m2.status().get("state")))
import webpanel  # noqa: E402
pg = webpanel.make_page()
check('id="nashost"' in pg and 'id="nasmac"' in pg and 'id="nasoff"' in pg and "op:'music_nas_save'" in pg, "Einstellungen: Felder fuer die NAS")
finish("test_nas_spiegeln")
