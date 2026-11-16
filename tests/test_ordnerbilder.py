"""Ordnerbilder in die MP3s (Wunsch von Markus, 08.11.2026): nur in MP3s ohne eigenes Bild, ein vorhandenes nie ueberschreiben,
die Musik bleibt gleich."""
import json
import os
import struct
import sys
import tempfile
import time
import urllib.request

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import folder_art as fa  # noqa: E402
import music_serve as ms  # noqa: E402
import tag_edit as te  # noqa: E402

JPG = b"\xff\xd8\xff\xe0" + b"ordner" * 40
OWN = b"\xff\xd8\xff\xe0" + b"eigenes" * 40
AUDIO = b"\xff\xfb\x90\x00" + bytes(range(256)) * 8


def id3(frames):
    body = b"".join(frames)
    n = len(body)
    return b"ID3\x03\x00\x00" + bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F]) + body


def fr(fid, body):
    return fid + struct.pack(">I", len(body)) + b"\0\0" + body


tmp = tempfile.mkdtemp(prefix="s2l_ordnerbild_")
alb = os.path.join(tmp, "Album")
os.makedirs(alb)
with open(os.path.join(alb, "Folder.jpg"), "wb") as f:
    f.write(JPG)
files = {
    "ohne": id3([fr(b"TIT2", b"\0Ohne")]) + AUDIO,                                     # kein Bild -> bekommt das Ordnerbild
    "kein_tag": AUDIO,                                                                 # gar kein ID3 -> bekommt es auch
    "link": id3([fr(b"APIC", b"\0-->\0\3\0AlbumArtSmall.jpg\0")]) + AUDIO,             # nur Dateiname (Windows Media Player)
    "eigenes": id3([fr(b"APIC", b"\0image/jpeg\0\3\0" + OWN)]) + AUDIO,               # eigenes Bild: nie anfassen
}
paths = {}
for k, data in files.items():
    paths[k] = os.path.join(alb, k + ".mp3")
    with open(paths[k], "wb") as f:
        f.write(data)
leer = os.path.join(tmp, "OhneBild")
os.makedirs(leer)
paths["leer"] = os.path.join(leer, "lied.mp3")
with open(paths["leer"], "wb") as f:
    f.write(AUDIO)

check(not fa.has_image(paths["ohne"], ms.looks_like_image) and not fa.has_image(paths["link"], ms.looks_like_image)
      and fa.has_image(paths["eigenes"], ms.looks_like_image), "Bild in der MP3 erkannt, Dateiname im APIC zaehlt nicht")
check(ms.folder_image(alb)[2] == "Folder.jpg" and ms.folder_image(leer) is None, "Bild im Ordner")

srv = ms.MusicServer(list(paths.values()), port=0)
art = srv.folderart
check(art is not None, "Mac-Server hat die Ordnerbilder")
art.scan()
art.thread.join(10)
st = art.status()
found = sorted(os.path.basename(x["path"]) for x in st["items"])
check(st["state"] == "ready" and found == ["kein_tag.mp3", "link.mp3", "ohne.mp3"] and all(x["image"] == "Folder.jpg" for x in st["items"]),
      "Suche: nur MP3s ohne eigenes Bild in Ordnern mit Bild")
before = open(paths["eigenes"], "rb").read()
open(paths["ohne"], "ab").close()
# zwischen Suche und Schreiben bekommt eine Datei ein eigenes Bild: dann bleibt es
te.write_tags(paths["link"], cover=OWN)
art.write()
art.thread.join(10)
st = art.status()
check(st["state"] == "ready" and st["n"] == 0 and st["written"] == 2 and not st["errors"], "geschrieben, Liste danach leer")
for k in ("ohne", "kein_tag"):
    data = open(paths[k], "rb").read()
    check(fa.has_image(paths[k], ms.looks_like_image) and JPG in data and data.endswith(AUDIO), k + ": Ordnerbild drin, Musik gleich")
check(te.read_tags(paths["ohne"])["fields"].get("title") == "Ohne", "andere Tags bleiben")
check(open(paths["eigenes"], "rb").read() == before, "eigenes Bild: Datei unveraendert")
check(OWN in open(paths["link"], "rb").read() and JPG not in open(paths["link"], "rb").read(),
      "inzwischen eigenes Bild bekommen: nicht ueberschrieben (Pruefung direkt vor dem Schreiben)")
check(open(paths["leer"], "rb").read() == AUDIO, "Ordner ohne Bild: nichts geaendert")

# HTTP wie die Seite
srv.start()
base = "http://127.0.0.1:%d" % srv.port
for _ in range(50):
    if srv.port:
        break
    time.sleep(0.05)
base = "http://127.0.0.1:%d" % srv.port
d = json.loads(urllib.request.urlopen(base + "/folderart", timeout=5).read())
check(d.get("state") == "ready", "GET /folderart: Stand")
req = urllib.request.Request(base + "/folderart", data=json.dumps({"op": "kaputt"}).encode(), method="POST")
try:
    urllib.request.urlopen(req, timeout=5)
    check(False, "unbekannter Befehl abgelehnt")
except urllib.error.HTTPError as e:
    check(e.code == 400, "unbekannter Befehl abgelehnt")
srv.stop()

html = open(os.path.join(ROOT, "pi", "static", "sm", "autotag.html"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "pi", "static", "sm", "autotag.js"), encoding="utf-8").read()
check('id="fart"' in html and "nie überschrieben" in html and "/folderart" in js, "Seite Tag-Vorschlaege: Bereich Ordnerbilder")

for inst in ("mac/mixxx_bridge/install_launcher.sh", "mac/helper/install_helper.sh"):
    check("folder_art.py" in open(os.path.join(ROOT, inst), encoding="utf-8").read(), inst + " kopiert folder_art.py")

check("JSON.parse(await r.text())" in js and "alte Fassung" in js, "alte Bruecke (Text statt JSON): verstaendlicher Hinweis statt JSON-Fehler")

finish("test_ordnerbilder")
