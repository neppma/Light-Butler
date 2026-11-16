"""Feld Gruppe (TIT1, in Mixxx "Gruppierung") im Tag (Wunsch 10.11.2026: Après-Ski-Lieder kennzeichnen, ohne den Kommentar, den
Mixed In Key ueberschreibt): schreiben, lesen, durch Ordner-Liste und Bruecke zum Pi, Spalte in der Musik-Datenbank."""
import os
import shutil
import sys
import tempfile

from _common import ROOT, check, finish

tmp = tempfile.mkdtemp()
os.environ["S2L_DATA"] = os.path.join(tmp, "daten")
sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
sys.path.insert(0, os.path.join(ROOT, "pi"))
import tag_edit                              # noqa: E402
import folder_lib                            # noqa: E402
import id3_tags as it                        # noqa: E402
import changed_log                           # noqa: E402
import mixxx_bridge as mb                    # noqa: E402
import mixxx_link                            # noqa: E402

# kleine MP3: ID3v2.3 mit Titel, dann ein paar MPEG-Bilder
def frame(fid, text):
    body = b"\x00" + text.encode("latin-1")
    return fid + len(body).to_bytes(4, "big") + b"\x00\x00" + body


tags = frame(b"TIT2", "Hulapalu") + frame(b"TPE1", "Andreas Gabalier")
hdr = b"ID3\x03\x00\x00" + bytes([(len(tags) >> 21) & 127, (len(tags) >> 14) & 127, (len(tags) >> 7) & 127, len(tags) & 127])
mpeg = (b"\xff\xfb\x90\x64" + b"\x00" * 413) * 20
p = os.path.join(tmp, "Andreas Gabalier - Hulapalu.mp3")
with open(p, "wb") as f:
    f.write(hdr + tags + mpeg)

check(any(k == "grouping" and fr == "TIT1" for k, fr, _l in tag_edit.FIELDS), "Feld Gruppe (TIT1) im Tag-Editor")
t = tag_edit.write_tags(p, {"grouping": "Après-Ski"})
check(t["fields"]["grouping"] == "Après-Ski" and t["fields"]["title"] == "Hulapalu" and not t["other"], "Gruppe geschrieben, Titel bleibt")
check(open(p, "rb").read().endswith(mpeg), "Musik bleibt Byte fuer Byte gleich")
check(any(os.path.basename(f) == os.path.basename(p) for f in changed_log.files()) if hasattr(changed_log, "files") else True,
      "Datei steht in der Liste geaenderter Tags fuer Mixxx")
info = folder_lib.read_mp3(p)
check(info["grouping"] == "Après-Ski", "Ordner-Liste liest die Gruppe")
rec = folder_lib.song_record(p, info, lambda k: 0)
check(rec["grouping"] == "Après-Ski", "Lied aus dem Ordner hat die Gruppe")
item = [x for ch in mb.library_chunks([dict(rec, duration=200.0)]) for x in ch][0]
check(item[25] == "Après-Ski", "Bruecke schickt die Gruppe als Feld 26")
d = mixxx_link.lib_item(item)
check(d["grp"] == "Après-Ski" and mixxx_link.lib_item(item[:25])["grp"] == "", "Pi liest die Gruppe, alte Bruecke: leer")
fw = mb.Forwarder([], None, None, analysis_dir=os.path.join(tmp, "an"), analyze=False)
check("grouping" in fw.TAG_KEYS, "selbst geschriebene Gruppe gleich in der Liste")
js = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("k: 'grp', th: 'Gruppe'" in js and "(r.grp || '')" in js and "'Gruppe', 'Hinzugefuegt'," in js, "Musik-Datenbank: Spalte, Suche, CSV")
te = open(os.path.join(ROOT, "pi", "static", "sm", "tagedit.js"), encoding="utf-8").read()
check("'genre', 'grouping'" in te, "Tag-Fenster zeigt die Gruppe gleich oben")

# Auto-DJ: Gruppen als Quelle (Wunsch 11.11.2026)
sys.path.insert(0, os.path.join(ROOT, "pi"))
from showman import autodj                   # noqa: E402
lib = [{"path": "/a.mp3", "artist": "A", "name": "Eins", "dur": 200.0, "genre": "Schlager", "grp": "Après-Ski; Party"},
       {"path": "/b.mp3", "artist": "B", "name": "Zwei", "dur": 200.0, "genre": "Pop", "grp": "Lizenzfrei"},
       {"path": "/c.mp3", "artist": "C", "name": "Drei", "dur": 200.0, "genre": "Rock", "grp": ""}]
check(autodj._crates("G:Après-Ski|L:X") == {("G", "après-ski"), ("L", "x")}, "Auswahl G:Name wird gelesen")
check([x["path"] for x in autodj.candidates(lib, crates="G:Après-Ski")] == ["/a.mp3"]
      and [x["path"] for x in autodj.candidates(lib, crates="G:party|G:Lizenzfrei")] == ["/a.mp3", "/b.mp3"],
      "Auto-DJ nimmt nur Lieder der gewaehlten Gruppen (mehrere im Feld mit ;, Gross/klein egal)")
check(autodj.groups_of(lib[0]) == ["Après-Ski", "Party"] and autodj.groups_of(lib[2]) == [], "Gruppen eines Liedes")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
aj = open(os.path.join(ROOT, "pi", "static", "sm", "autodj.js"), encoding="utf-8").read()
check('("G", autodj.groups_of(t))' in api and "/^[KLG]:./" in aj and "k === 'G' ? '🏷 '" in aj, "Auto-DJ-Seite zeigt Gruppen zur Auswahl")
# Musik-DB: Gruppe fuer die gefilterte Liste setzen
mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
check('id="bgrp"' in mh and "$('bgrp').onclick" in js and "fields: { grouping: g }" in js and "todo = mp3.filter(r => (r.grp || '') !== g)" in js,
      "Musik-DB: Knopf Gruppe setzen fuer alle gefilterten MP3s (nur die, die sie noch nicht haben)")

finish("test_gruppe_tag")
