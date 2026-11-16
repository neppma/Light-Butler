"""Cover der Lieder (Wunsch von Markus, 06.11.2026): der Mac holt das Bild aus MP3 (ID3), MP4 (covr) oder dem Ordner, der Pi
legt es je Fingerabdruck ab und zeigt es in Musik-Datenbank, Showmanager und Hauptpanel; Sicherung auf den Stick."""
import base64
import io
import json
import os
import struct
import sys
import tempfile
import urllib.error
import urllib.parse

from _common import ROOT, build, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import music_serve as ms  # noqa: E402
import stems_backup as sb  # noqa: E402
from mixxx_link import MixxxLink  # noqa: E402
from showman import covers as cv  # noqa: E402
from showman import store as stmod  # noqa: E402
from showman.api import ShowManager, handle_get  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_cover_")
JPG = b"\xff\xd8\xff\xe0" + b"bild" * 50
PNG = b"\x89PNG\r\n\x1a\n" + b"png!" * 20


# ---- Mac: Bild aus der Datei ----
def id3(frames, ver=3):
    body = b"".join(frames)
    n = len(body)
    ss = bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])
    return b"ID3" + bytes([ver, 0, 0]) + ss + body


def apic(img, ptype=3, desc=b"", enc=0):
    body = bytes([enc]) + b"image/jpeg\0" + bytes([ptype]) + desc + (b"\0\0" if enc in (1, 2) else b"\0") + img
    return b"APIC" + struct.pack(">I", len(body)) + b"\0\0" + body


tag = id3([b"TIT2" + struct.pack(">I", 6) + b"\0\0" + b"\0Titel", apic(PNG, ptype=0), apic(JPG, ptype=3, desc=b"F\0r\0", enc=1)])
c = ms.id3_cover(tag + b"\xff\xfb" + b"\0" * 100)
check(c is not None and c[0] == JPG and c[1] == "image/jpeg", "MP3: Vorderseite (Typ 3) vor anderen Bildern, UTF-16-Beschreibung")
check(ms.id3_cover(id3([apic(PNG, ptype=0)]))[1] == "image/png", "MP3: sonst das erste Bild, PNG erkannt")
check(ms.id3_cover(b"\xff\xfb" + b"\0" * 50) is None, "MP3 ohne ID3: kein Bild")
mp4 = b"\0\0\0\x18ftypM4A " + b"\0" * 8 + struct.pack(">I", 8 + 16 + len(JPG)) + b"covr" + struct.pack(">I", 16 + len(JPG)) + b"data" + struct.pack(">I", 13) + b"\0\0\0\0" + JPG
check(ms.mp4_cover(mp4) == (JPG, "image/jpeg"), "MP4: Bild aus covr/data")
d = os.path.join(tmp, "album")
os.makedirs(d)
with open(os.path.join(d, "lied.mp3"), "wb") as f:
    f.write(b"\xff\xfb" + b"\0" * 400)
with open(os.path.join(d, "Folder.jpg"), "wb") as f:
    f.write(JPG)
with open(os.path.join(d, "._cover.jpg"), "wb") as f:
    f.write(b"mac-muell")
check(ms.find_cover(os.path.join(d, "lied.mp3")) == (JPG, "image/jpeg"), "ohne Bild in der Datei: folder.jpg im Ordner (nicht ._-Dateien)")
mp3 = os.path.join(d, "mit.mp3")
with open(mp3, "wb") as f:
    f.write(tag + b"\xff\xfb" + b"\1" * 300)
check(ms.find_cover(mp3)[0] == JPG, "Bild in der Datei geht vor dem Ordner")
check(ms.audio_fp(mp3) == stmod.audio_fingerprint(mp3), "Fingerabdruck am Mac wie am Pi (Dateiname der Sicherung)")
# 08.11.2026: APIC mit nur einem Dateinamen (alter Windows Media Player: "AlbumArtSmall.jpg", MIME "-->") ist kein Cover
link = b"\0-->\0\3\0AlbumArtSmall.jpg\0"
link_frame = b"APIC" + struct.pack(">I", len(link)) + b"\0\0" + link
check(ms.id3_cover(id3([link_frame])) is None, "APIC nur mit Dateiname: kein Bild aus der Datei")
d2 = os.path.join(tmp, "wmp")
os.makedirs(d2)
with open(os.path.join(d2, "lied.mp3"), "wb") as f:
    f.write(id3([link_frame]) + b"\xff\xfb" + b"\0" * 300)
BIG = b"\xff\xd8\xff\xe0" + b"gross" * 200
with open(os.path.join(d2, "AlbumArtSmall.jpg"), "wb") as f:
    f.write(JPG)
with open(os.path.join(d2, "AlbumArt_{ABC}_Large.jpg"), "wb") as f:
    f.write(BIG)
check(ms.find_cover(os.path.join(d2, "lied.mp3")) == (BIG, "image/jpeg"), "dann das Bild im Ordner, AlbumArt* zaehlt, das groesste gewinnt")
with open(os.path.join(d2, "AlbumArt_{ABC}_Large.jpg"), "wb") as f:
    f.write(b"kein bild, nur text" * 20)
check(ms.find_cover(os.path.join(d2, "lied.mp3")) is None, "Ordnerbild, das kein Bild ist: kein Cover")

# ---- Pi: holen, ablegen, Vorab-Lauf ----
FP = "300:0123456789abcdef"
LIB = [{"title": "A - Eins", "dur": 200.0, "path": "/m/eins.mp3"}, {"title": "B - Zwei", "dur": 210.0, "path": "/m/zwei.mp3"},
       {"title": "C - Ohne", "dur": 220.0, "path": "/m/ohne.mp3"}]
music = ["http://mac:9025"]
asked = []


class R(io.BytesIO):
    def __init__(self, data, headers):
        super().__init__(data)
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def mac(url, timeout=0):
    p = urllib.parse.unquote(url.split("p=")[1])
    asked.append(p)
    if p == "/m/ohne.mp3":
        raise urllib.error.HTTPError(url, 404, "kein Cover", {}, None)
    if p == "/m/neu.mp3":                                     # gerade umbenannt, der Mac kennt die Datei noch nicht
        raise urllib.error.HTTPError(url, 410, "Datei nicht gefunden", {}, None)
    return R(JPG, {"X-FP": FP if p == "/m/eins.mp3" else "310:fedcba9876543210"})


base = os.path.join(tmp, "shows")
os.makedirs(base)
co = cv.Covers(base, lambda: LIB, lambda: music[0], mac)
check(co.for_path("/m/eins.mp3") == JPG and os.path.isfile(os.path.join(base, "_covers", "300_0123456789abcdef.jpg")),
      "beim ersten Anzeigen vom Mac geholt, Datei = Fingerabdruck")
n = len(asked)
check(co.for_path("/m/eins.mp3") == JPG and len(asked) == n, "danach aus der Ablage, ohne Mac")
check(co.for_path("/m/ohne.mp3") is None and co.for_path("/m/ohne.mp3") is None and asked.count("/m/ohne.mp3") == 1,
      "Lied ohne Cover: gemerkt, nicht bei jedem Anzeigen wieder fragen")
check(co.fetch("/m/neu.mp3") is False and "/m/neu.mp3" not in co.index,
      "Datei dem Mac noch unbekannt (410): nicht als 'ohne Cover' gemerkt (Fehlerbericht 09.11.2026: 6 h schwarz)")
music[0] = ""
check(co.for_path("/m/zwei.mp3") is None and "/m/zwei.mp3" not in co.index, "Mac aus: nichts, auch nichts gemerkt")
music[0] = "http://mac:9025"
co2 = cv.Covers(base, lambda: LIB, lambda: music[0], mac)
check(co2.index.get("/m/eins.mp3") == FP and co2.index.get("/m/ohne.mp3") == "", "Zuordnung Pfad -> Fingerabdruck ueberlebt einen Neustart")
cv.GAP_S = 0.0
co2.start()
co2.thread.join(5)
s = co2.status()
check(s["done"] == 2 and s["none"] == 1 and s["done_all"] and not s["running"] and co2._flag() is False, "Vorab-Lauf: alle angesehen, dann aus")
check([x[0] for x in co2.files()] == ["300_0123456789abcdef.jpg", "310_fedcba9876543210.jpg"], "Liste fuer die Sicherung")

# 08.11.2026: Lied ohne Cover bekommt spaeter eins (Auto-Tagger am Mac): das Nachschauen findet es von selbst
cv.RECHECK_GAP_S = 0.0
t_now = [1000.0]
co3 = cv.Covers(base, lambda: LIB, lambda: music[0], lambda url, timeout=0: mac_later(url), now=lambda: t_now[0])
later = {"on": False}


def mac_later(url):
    p = urllib.parse.unquote(url.split("p=")[1])
    if p == "/m/ohne.mp3" and later["on"]:
        return R(PNG.replace(b"png!", b"neu!"), {"X-FP": "320:aaaaaaaaaaaaaaaa"})
    return mac(url)


check(co3.index.get("/m/ohne.mp3") == "" and co3.recheck_once() == 0, "Nachschauen: noch kein Cover")
later["on"] = True
check(co3.recheck_once() == 0, "gerade gefragt: nicht gleich wieder")
t_now[0] += cv.NONE_RETRY_S + 1
check(co3.recheck_once() == 1 and co3.index.get("/m/ohne.mp3") == "320:aaaaaaaaaaaaaaaa", "spaeter: neues Cover gefunden und gemerkt")
music[0] = ""
co3.index["/m/zwei.mp3"] = ""
check(co3.recheck_once() is None, "Mac aus: Nachschauen meldet es, nichts gemerkt")
music[0] = "http://mac:9025"
check("start_recheck()" in open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read(), "Nachschauen startet mit dem Showmanager")
check(co2.raw("../settings.json") is None and co2.raw("300_0123456789abcdef.jpg") == JPG, "nur gueltige Dateinamen, kein Pfad von aussen")
try:
    co2.save(FP, b"<html>")
    check(False, "kein Bild abgelehnt")
except ValueError:
    check(True, "kein Bild abgelehnt")

# ---- Showmanager: Show, Titel aus Mixxx, Web ----
link = MixxxLink(0)
rig, sh = build(strobe=False, mixxx=link)
sdir = os.path.join(tmp, "sm")
mgr = ShowManager(sh, sdir)
link.feed({"type": "lib", "i": 0, "n": 1, "t": [["A - Eins", 200.0, "A", "Eins", 128.0, "Am", 22, "Pop", 6, "eins.mp3", 2, 1, "/m/eins.mp3"]]}, 1.0)
mgr.music_url = lambda: music[0]
mgr.mac_opener = mac
mgr.covers.music = mgr.music_url
check(mgr.cover(title="a - eins", dur=200.4) == JPG, "Hauptpanel: Lied aus Mixxx ueber Titel und Laenge")
mgr.op({"op": "create", "name": "Eins", "title": "A - Eins", "dur": 200.0})
check(mgr.cover(show="Eins") == JPG, "Show ohne eigene MP3: Cover ueber ihr Mixxx-Lied")
check(mgr.cover(title="Unbekannt", dur=100) is None, "unbekanntes Lied: kein Cover")
check(mgr.op({"op": "covers_bulk_status"})["total"] == 1, "Stand fuer die Seite Statistik")
# Show mit eigener MP3 (Cover eingebettet): geht ohne Mac und ohne Vorab-Lauf, das Bild kommt aus der MP3 am Pi
mgr.op({"op": "create", "name": "Eigene"})
with open(mgr.store.path("Eigene", "audio.mp3"), "wb") as f:
    f.write(tag + b"\xff\xfb" + b"\2" * 500)
music[0] = ""
check(mgr.cover(show="Eigene") == JPG and mgr.covers.by_fp(mgr.store._audio_fp("Eigene")) == JPG, "Show: Cover aus ihrer eigenen MP3, ohne Mac, gemerkt")
mgr.op({"op": "create", "name": "Nackt"})
with open(mgr.store.path("Nackt", "audio.mp3"), "wb") as f:
    f.write(b"\xff\xfb" + b"\3" * 500)
check(mgr.cover(show="Nackt") is None and mgr.store._audio_fp("Nackt") in mgr.covers.no_mp3, "MP3 ohne Bild: einmal versucht, gemerkt")
music[0] = "http://mac:9025"
check(cv.mp3_image(mp3) == JPG and cv.id3_image(id3([apic(PNG, ptype=0)])) == PNG, "Pi liest ID3 wie der Mac")
mgr.op({"op": "covers_restore", "f": "310_fedcba9876543210.jpg", "data": base64.b64encode(JPG).decode()})
check(mgr.covers.by_fp("310:fedcba9876543210") == JPG, "Zurueckspielen aus der Sicherung")


class H:
    def __init__(self, path, headers=None):
        self.path, self.out, self.headers = path, None, headers or {}

    def _send(self, code, body, ctype, extra=None):
        self.out = (code, body, ctype, extra or {})


h = H("/api/sm/cover?p=" + urllib.parse.quote("/m/eins.mp3"))
handle_get(h, mgr)
check(h.out[0] == 200 and h.out[1] == JPG and h.out[2] == "image/jpeg" and h.out[3].get("Cache-Control") == "no-cache" and h.out[3].get("ETag"),
      "Web: Bild mit ETag, der Browser fragt jedes Mal nach (Fehlerbericht 09.11.2026: neues Cover kam einen Tag nicht)")
h2 = H("/api/sm/cover?p=" + urllib.parse.quote("/m/eins.mp3"), {"If-None-Match": h.out[3]["ETag"]})
handle_get(h2, mgr)
check(h2.out[0] == 304 and h2.out[1] == b"", "unveraendert: nur 304, kein Bild")
h = H("/api/sm/cover?t=Nix&d=1")
handle_get(h, mgr)
check(h.out[0] == 404, "Web: ohne Cover 404")
h = H("/api/sm/covers_list")
handle_get(h, mgr)
check(json.loads(h.out[1])["files"][0][0] == "300_0123456789abcdef.jpg", "Web: Liste fuer die Sicherung")

# ---- Sicherung auf den Stick ----
pi_files = {"300_0123456789abcdef.jpg": JPG, "../boese.jpg": b"x"}


def pi(url, timeout=0):
    if url.endswith("/api/sm/covers_list"):
        return R(json.dumps({"files": [[k, len(v)] for k, v in pi_files.items()]}).encode(), {})
    return R(pi_files[urllib.parse.unquote(url.split("f=")[1])], {})


dest = os.path.join(tmp, "stick", "musik-backup", "Light-Butler-Covers")
check(sb.sync_covers("http://pi", dest, pi) == (1, 2) and os.listdir(dest) == ["300_0123456789abcdef.jpg"], "Stick: Cover mit Fingerabdruck als Name, fremde Namen nicht")
check(sb.sync_covers("http://pi", dest, pi)[0] == 0, "Stick: nur Neues kopieren")
check(sb.COVERS_FOLDER == os.path.join("musik-backup", "Light-Butler-Covers"), "eigener Ordner neben Kurven und Cues")
# Frage von Markus 07.11.2026: geaendertes Cover (Tag-Fenster, Auto-Tagger, erzeugt) muss auch auf den Stick, der Name bleibt gleich
check(len(json.loads(h.out[1])["files"][0]) == 3, "Liste fuer die Sicherung mit Aenderungszeit")
pi_t = {"300_0123456789abcdef.jpg": (JPG, 1000)}


def pi2(url, timeout=0):
    if url.endswith("/api/sm/covers_list"):
        return R(json.dumps({"files": [[k, len(v), t] for k, (v, t) in pi_t.items()]}).encode(), {})
    return R(pi_t[urllib.parse.unquote(url.split("f=")[1])][0], {})


dest2 = os.path.join(tmp, "stick2")
check(sb.sync_covers("http://pi", dest2, pi2)[0] == 1 and sb.sync_covers("http://pi", dest2, pi2)[0] == 0, "Stick: kopiert, dann gleich")
NEU = JPG[:-4] + b"neu!"                                       # neues Cover, genau gleich gross
pi_t["300_0123456789abcdef.jpg"] = (NEU, 2000)
check(sb.sync_covers("http://pi", dest2, pi2)[0] == 1 and open(os.path.join(dest2, "300_0123456789abcdef.jpg"), "rb").read() == NEU,
      "geaendertes Cover gleicher Groesse: trotzdem auf den Stick")
check(sb.sync_covers("http://pi", dest2, pi)[0] in (0, 1), "aeltere Pi-Liste ohne Zeit: weiter nur nach Groesse")

# ---- Anzeige ----
import webpanel  # noqa: E402
pg = webpanel.stats_page()
check('id="cvbulk"' in pg and "cvBulkCmd({op:'covers_bulk',on:!s.running})" in pg, "Seite Statistik: Karte Cover vorab holen")
main = webpanel.make_page()
check('id="pcover"' in main and "/api/sm/cover?t=" in main and "'/api/sm/cover?show='+encodeURIComponent(sh)" in main, "Hauptpanel: Cover zum Lied aus Mixxx und zur laufenden Show")
web = os.path.join(ROOT, "pi", "static", "sm")
check("/api/sm/cover?p=" in open(os.path.join(web, "music.js"), encoding="utf-8").read(), "Musik-Datenbank: Spalte Cover")
check("plcover" in open(os.path.join(web, "play.js"), encoding="utf-8").read() and "/api/sm/cover?show=" in open(os.path.join(web, "play.js"), encoding="utf-8").read()
      and "/api/sm/cover?show=" in open(os.path.join(web, "editor.js"), encoding="utf-8").read(), "Showliste und Editor: Cover")
# Mac meldet geaenderte Dateien (Ordner-Liste) -> Pi holt das Cover neu (09.11.2026)
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import folder_lib as fl  # noqa: E402
import mixxx_bridge as mbr  # noqa: E402
fdir = tempfile.mkdtemp(prefix="s2l_cvchg_")
fa, fb = os.path.join(fdir, "a.mp3"), os.path.join(fdir, "b.mp3")
for q in (fa, fb):
    open(q, "wb").write(b"\xff\xfb\x90\x00" + b"\x00" * 400)
lib_f = fl.FolderLib(base=os.path.join(fdir, "d"))
got = []
lib_f.on_changed = got.append
lib_f.start(fdir, wait=True)
check(got == [], "erster Durchgang: nichts gemeldet")
open(fa, "ab").write(b"\x00" * 10)
lib_f.start(fdir, wait=True)
check(got == [[fa]], "geaenderte Datei gemeldet: " + str(got))
posted = []
mbr.cover_refresh_bg("http://pi", ["/m/x.mp3", "/m/y.mp3"], post=posted.append, gap_s=0).join(5)
check(posted == ["/m/x.mp3", "/m/y.mp3"], "an den Pi: cover_refresh je Datei")
# Wunsch 09.11.2026: neues Cover in der Musik-Datenbank sofort, ohne die Seite neu zu laden
mjs = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("'&v=' + (r.cvv || 0)" in mjs and "r.cvv = Date.now();" in mjs and "t.cvv," in mjs, "Musik-DB: Bild-Stand in der Adresse, nach Tag bearbeiten sofort neu")
fpx = "310:fedcba9876543210"
t0 = mgr.covers.mtime(fpx)
mgr.covers.save(fpx, JPG)
check(mgr.covers.mtime(fpx) >= t0 and mgr.covers.mtime("") == 0, "Pi: Zeitstempel je Bild, nach dem Speichern neu")
import subprocess  # noqa: E402
_cc = subprocess.run(["node", "-e", "global.window=global;require(process.argv[1]);const S=window.SM;console.log(JSON.stringify(['/a/x.mp3','/a/y.M4A','/a/THX Intro.wav','/a/z.flac',''].map(S.canCover)))",
                      os.path.join(web, "core.js")], capture_output=True, text=True)
check(_cc.stdout.strip() == "[true,true,false,false,false]", "nur MP3/MP4/M4A/AAC koennen ein Cover tragen: " + _cc.stdout + _cc.stderr[-200:])
_care = open(os.path.join(web, "care.js"), encoding="utf-8").read()
check("t.cv === 0 && SM.canCover(t.path)" in _care and "!SM.canCover(r.path)" in open(os.path.join(web, "music.js"), encoding="utf-8").read(),
      "Datenpflege und Filter ohne Cover zaehlen WAV nicht mit (Wunsch 09.11.2026)")
finish("Cover")
