"""Statistik "nicht lesbar" (Fehlerbericht 06.11.2026: 56 gemeldet, die Liste zeigte 4): alte Eintraege (Datei fehlt, Lied seither
geaendert) zaehlen getrennt, der Link zur Liste nennt nur die, die dort auch stehen."""
import json
import os
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge as mb  # noqa: E402

import webpanel  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_nl_")
real = os.path.join(tmp, "da.mp3")
open(real, "wb").write(b"x")
lib = [{"artist": "A", "title": "Kaputt", "duration": 65.0, "bpm": 0, "kid": 0, "path": real},
       {"artist": "B", "title": "Weg", "duration": 100.0, "bpm": 120, "kid": 1, "path": real, "missing": True},
       {"artist": "C", "title": "Neu analysiert", "duration": 217.9, "bpm": 90.5, "kid": 7, "path": real}]
failed = {mb.track_key(65.0, 0, 0): "A - Kaputt: Datei nicht lesbar", mb.track_key(100.0, 120, 1): "B - Weg: Datei nicht gefunden: /Volumes/music/x.mp3",
          mb.track_key(217.942, 128.0, 13): "C - alt: Datei nicht lesbar"}
with open(os.path.join(tmp, mb.FAILED_FILE), "w", encoding="utf-8") as f:
    json.dump(failed, f)


class F:
    lib, dir = lib, tmp


check(mb.Forwarder.failed_gone(F()) == 2, "fehlende Datei und geaendertes Lied zaehlen als alte Eintraege, das echte nicht")
pg = webpanel.stats_page()
check("gone=Math.min(B.gone||0,B.fail||0),bad=(B.fail||0)-gone" in pg and "(bad?' <a href=\"/musik?f=nichtlesbar\"" in pg and "tr('stat_bg_gone')" in pg,
      "Statistik: Link nur fuer die wirklich nicht lesbaren, alte Eintraege eigens erklaert")
finish("nicht lesbar: Zaehlung")
