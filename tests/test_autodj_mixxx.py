"""Auto-DJ -> Mixxx (Wunsch von Markus, 08.11.2026): die Playlist als M3U8-Datei am Mac, Mixxx importiert sie von Hand.
Nur Lieder der Bibliothek, nur in den eigenen Ordner, Mixxx selbst bleibt unberuehrt."""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import music_serve as ms  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_m3u_")
ms.M3U_DIR = os.path.join(tmp, "Light-Butler Playlists")
songs = []
for n in ("eins", "zwei"):
    p = os.path.join(tmp, "musik", n + ".mp3")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"\xff\xfb" + b"\0" * 100)
    songs.append(p)
loc = ms.Locator(songs)
f, n, miss = ms.write_m3u("Party: 8.11/Abend", [{"p": songs[0], "t": "A - Eins\nzwei", "d": 200.4}, {"p": "/fremd/x.mp3"},
                                               {"p": songs[1], "t": "B - Zwei", "d": 180}], loc.locate)
txt = open(f, encoding="utf-8").read().splitlines()
check(os.path.dirname(f) == ms.M3U_DIR and os.path.basename(f) == "Party 8.11 Abend.m3u8", "Datei im eigenen Ordner, Name ohne Sonderzeichen")
check(txt == ["#EXTM3U", "#PLAYLIST:Party 8.11 Abend", "#EXTINF:200,A - Eins zwei", songs[0], "#EXTINF:180,B - Zwei", songs[1]],
      "M3U8: Reihenfolge, Laenge, Titel, Pfade wie am Mac")
check(n == 2 and miss == ["/fremd/x.mp3"], "Lieder ausserhalb der Bibliothek kommen nicht hinein")
try:
    ms.write_m3u("leer", [{"p": "/fremd/y.mp3"}], loc.locate)
    check(False, "ohne erreichbares Lied: Fehler")
except ValueError:
    check(True, "ohne erreichbares Lied: Fehler")

srv = ms.MusicServer(songs, port=0)
srv.start()
base = "http://127.0.0.1:%d" % srv.port
req = urllib.request.Request(base + "/m3u", data=json.dumps({"name": "Test", "items": [{"p": songs[1], "t": "B", "d": 1}]}).encode(), method="POST")
d = json.loads(urllib.request.urlopen(req, timeout=5).read())
check(d.get("ok") and d.get("n") == 1 and os.path.isfile(d.get("file", "")), "POST /m3u schreibt die Datei")
try:
    urllib.request.urlopen(urllib.request.Request(base + "/m3u", data=b"{}", method="POST"), timeout=5)
    check(False, "ohne Lieder abgelehnt")
except urllib.error.HTTPError as e:
    check(e.code == 400, "ohne Lieder abgelehnt")
srv.stop()

html = open(os.path.join(ROOT, "pi", "static", "sm", "autodj.html"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "pi", "static", "sm", "autodj.js"), encoding="utf-8").read()
check('id="bmixxx"' in html and "music + '/m3u'" in js and "Wiedergabeliste importieren" in js, "Auto-DJ: Knopf → Mixxx mit Anleitung")
finish("test_autodj_mixxx")
