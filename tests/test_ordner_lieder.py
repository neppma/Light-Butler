"""Zweite Liedquelle der Bruecke (Wunsch von Markus, 07.11.2026): MP3s im Musikordner ohne Mixxx-Eintrag. Die Bruecke liest
Titel, Interpret, Laenge, Tonart (TKEY) und Energie (TXXX EnergyLevel) aus der Datei, gibt die Lieder an Energie- und
Tonart-Schaetzung und an die Musik-Datenbank (Feld 19 "src", Spalte Quelle). Ohne Mixxx-Datenbank laeuft sie mit dieser Liste."""
import argparse
import json
import os
import sys
import tempfile

from _common import ROOT, check, finish

BRIDGE = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BRIDGE)
import folder_lib as fl          # noqa: E402
import id3_tags as it            # noqa: E402
import mixxx_bridge as mb        # noqa: E402
import mixxx_link                # noqa: E402
from music_serve import Locator  # noqa: E402

HDR = b"\xff\xfb\x90\x00"                  # MPEG1 Layer III, 128 kbit/s, 44,1 kHz, Stereo: 417 Byte je Bild
FRAME = 417


def mpeg(frames, xing=0):
    """frames MPEG-Bilder (Inhalt leer); xing > 0: erstes Bild ist ein Xing-Kopf mit dieser Bildzahl (VBR)."""
    first = bytearray(HDR + bytes(FRAME - 4))
    if xing:
        first[36:40] = b"Xing"
        first[40:44] = (1).to_bytes(4, "big")
        first[44:48] = xing.to_bytes(4, "big")
    return bytes(first) + (HDR + bytes(FRAME - 4)) * (frames - 1)


def mp3(path, frames=100, tags=None, xing=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(mpeg(frames, xing))
    if tags:
        data = b"".join(it.frame(fid, body, 3) for fid, body in tags)
        it.write(path, 3, 0, data)


tmp = tempfile.mkdtemp(prefix="s2l_ordner_")
root = os.path.join(tmp, "Musik")
base = os.path.join(tmp, "daten")

# ---- MPEG-Kopf: Laenge und Bitrate ----
p_cbr = os.path.join(root, "House", "Daft - One.mp3")
mp3(p_cbr, 1000, [(b"TIT2", it.text_body("One More")), (b"TPE1", it.text_body("Daft")), (b"TCON", it.text_body("(35)House")),
                  (b"TBPM", it.text_body("124")), (b"TKEY", it.text_body("8A")), (b"TXXX", it.txxx_body("EnergyLevel", "7"))])
info = fl.read_mp3(p_cbr)
check(abs(info["duration"] - 1000 * 1152 / 44100.0) < 0.1 and info["bitrate"] == 128, f"Laenge und Bitrate bei konstanter Bitrate ({info['duration']} s)")
check(info["title"] == "One More" and info["artist"] == "Daft" and info["genre"] == "House" and info["bpm"] == 124.0,
      "Titel, Interpret, Genre (ohne Nummer) und BPM aus den Tags")
check(info["tkey"] == "8A" and not info["key_est"] and info["elvl"] == 7 and not info["elvl_est"], "Tonart und Energie aus der Datei, nicht geschaetzt")

p_vbr = os.path.join(root, "House", "vbr.mp3")
mp3(p_vbr, 20, [(b"TIT2", it.text_body("Lang")), (b"TXXX", it.txxx_body("EnergyLevel", "6")),
                (b"TXXX", it.txxx_body("EnergyLevelSource", "Light-Butler (geschaetzt)")),
                (b"TKEY", it.text_body("5A")), (b"TXXX", it.txxx_body("KeySource", "Light-Butler (geschaetzt)"))], xing=8000)
info = fl.read_mp3(p_vbr)
check(abs(info["duration"] - 8000 * 1152 / 44100.0) < 0.01, f"Laenge aus dem Xing-Kopf ({info['duration']} s)")
check(info["elvl"] == 6 and info["elvl_est"] and info["key_est"], "vom Light-Butler geschriebene Werte als geschaetzt erkannt")

p_name = os.path.join(root, "Rock", "Band - Lied ohne Tags.mp3")
mp3(p_name, 200)
info = fl.read_mp3(p_name)
check(info["artist"] == "Band" and info["title"] == "Lied ohne Tags", "ohne Tags: Interpret und Titel aus dem Dateinamen")

check(fl._frame(b"\xff\xfb\x90\x00")[:3] == (417, 44100, 128) and fl._frame(b"\xff\xfd\x90\x00") is None and fl._frame(b"abcd") is None,
      "MPEG-Kopf: nur Layer III")

# ---- Ordner einlesen: Mixxx-Lieder, versteckte und kaputte Dateien bleiben weg ----
p_mixxx = os.path.join(root, "Pop", "In Mixxx.mp3")
mp3(p_mixxx, 100, [(b"TIT2", it.text_body("Schon in Mixxx"))])
mp3(os.path.join(root, "Pop", "._In Mixxx.mp3"), 10)
mp3(os.path.join(root, ".versteckt", "x.mp3"), 10)
with open(os.path.join(root, "Pop", "kaputt.mp3"), "wb") as f:
    f.write(b"keine Musik" * 50)
with open(os.path.join(root, "Pop", "liesmich.txt"), "w") as f:
    f.write("x")

logs = []
lib_dir = fl.FolderLib(base=base, log=logs.append, key_id_from_text=mb.key_id_from_text)
check(lib_dir.due(root) and not lib_dir.due(""), "Durchgang faellig, sobald ein Musikordner bekannt ist")
lib_dir.start(root, ["/Volumes/ALT/musik/pop/IN MIXXX.mp3"], wait=True)   # Mixxx kennt die Datei unter anderem Laufwerk
songs = {os.path.basename(r["path"]): r for r in lib_dir.songs}
check(set(songs) == {"Daft - One.mp3", "vbr.mp3", "Band - Lied ohne Tags.mp3"}, f"nur Lieder ohne Mixxx-Eintrag, ohne ._ und Versteckte ({sorted(songs)})")
# Mixxx fuehrt die Datei als fehlend, sie liegt aber da: als Ordner-Lied in die Liste (Fehlerbericht 07.11.2026)
_fwm = mb.Forwarder([{"path": p_mixxx, "duration": 1.0, "missing": True}], None, None, analysis_dir=os.path.join(base, "anm"), analyze=False)
_seen = []
_fwm.folder = type("F", (), {"ver": 0, "due": lambda self, root, now=None: True, "start": lambda self, root, known: _seen.extend(known), "songs": []})()
_fwm.folder_root = root
_fwm.folder_tick(now=1.0)
check(p_mixxx not in _seen, "in Mixxx als fehlend markiert: zaehlt nicht als Mixxx-Lied, die Ordner-Liste nimmt die Datei auf")
check(lib_dir.ver == 1 and any("1 ohne lesbares MPEG-Bild" in x for x in logs), "kaputte Datei gezaehlt, nicht gelistet")
r = songs["Daft - One.mp3"]
check(r["src"] == "dir" and r["kid"] == mb.key_id_from_text("8A") and r["key"] == "8A" and r["genre"] == "House", "Lied wie aus Mixxx, mit Quelle Ordner")
check(mb.energy_level(r) == 7 and mb.level_of(r) == (7, False), "Energie aus TXXX EnergyLevel zaehlt wie Mixed In Key")
v = songs["vbr.mp3"]
check(v["kid"] == 0 and mb.energy_level(v) is None and mb.level_of(v) == (6, True), "selbst geschaetzte Werte: Schaetzung neu fragen, sonst Wert aus der Datei mit ~")
check(os.path.isfile(os.path.join(base, fl.CACHE_FILE)), "Zwischenspeicher geschrieben")
check(lib_dir.file_tags == {fl.tail(p_mixxx): {"title": "Schon in Mixxx", "artist": "", "genre": "", "album": "", "tracknumber": "", "gnum": "", "grouping": "", "imported": ""}} and lib_dir.scan_t > 0,
      "Mixxx-Lied: Tags aus der Datei gemerkt (die Liste zeigt sie statt der alten Mixxx-Werte), Datei ohne Titel-Tag nicht")
# Bruecke: Werte aus der Datei gehen vor Mixxx, leeres Genre behaelt Mixxx; selbst geschriebene bis zum naechsten Durchgang
_fw = mb.Forwarder([{"path": "/Volumes/ALT/musik/pop/In Mixxx.mp3", "duration": 1.0, "artist": "Alt", "title": "Alt", "genre": "Pop"}],
                   None, None, analysis_dir=os.path.join(base, "an"), analyze=False)
_fw.folder = lib_dir
_r = _fw.lib_with_tags()[0]
_st = _fw.status(now=lib_dir.done_t + 30)
check(_st["tags"]["busy"] is False and _st["tags"]["files"] == lib_dir.n_files > 0 and _st["tags"]["ago"] == 30 and _st["tags"]["done"] == _st["tags"]["total"],
      "Statusanzeige: Tags gelesen, vor 30 s, alle Dateien")
_fw.lib_chunks, _fw.lib_total, _fw.lib_done = [(3, []), (4, [])], 5, 100.0
check(_fw.status(now=200.0)["send"] == {"busy": True, "sent": 3, "n": 5, "total": 5, "kind": "", "next": 0, "same": False, "pi": False}, "Statusanzeige: Liste wird geschickt, Teil 3 von 5")
_fw.lib_chunks = []
check(_fw.status(now=200.0)["send"] == {"busy": False, "sent": 5, "n": 5, "total": 5, "kind": "", "next": 500, "same": False, "pi": False}, "Statusanzeige: geschickt, naechster Durchgang in 500 s")
check('if u.path == "/status":' in open(os.path.join(os.path.dirname(fl.__file__), "music_serve.py"), encoding="utf-8").read()
      and "await fetch(music + '/status')" in open(os.path.join(os.path.dirname(fl.__file__), "..", "..", "pi", "static", "sm", "music.js"), encoding="utf-8").read(),
      "Mac liefert /status, die Musik-Datenbank fragt nach")
# nach dem Start: erst die Tags lesen, dann die Liste schicken (sonst ging sie mit den alten Mixxx-Werten raus)
_fw4 = mb.Forwarder([{"path": "/x/a.mp3", "duration": 1.0, "artist": "A", "title": "B"}], None, None, analysis_dir=os.path.join(base, "an4"), analyze=False)
_fw4.folder = type("F", (), {"ver": 0, "due": lambda self, root, now=None: False, "songs": [], "file_tags": {}})()
_fw4.folder_t = 1e18
_fw4.tick()
check(not getattr(_fw4, "lib_chunks", None), "Tags noch nicht gelesen: Liste wartet")
_fw4.folder.ver = 1
_fw4.folder_t, _fw4.lib_sent = 0, 0
_fw4.tick()
check(getattr(_fw4, "lib_total", 0) == 256 and getattr(_fw4, "lib_h", ""), "Tags gelesen: Liste geht los (feste Stuecke, mindestens 256)")
# nur schicken, wenn der Pi eine andere Fassung hat; verlorene Stuecke einzeln (Wunsch 07.11.2026)
_lib5 = [{"path": f"/x/{k}.mp3", "duration": 100.0 + k, "artist": "Band %03d" % k, "title": "Lied " + "x" * 200} for k in range(30)]
_fw5 = mb.Forwarder(_lib5, None, None, analysis_dir=os.path.join(base, "an5"), analyze=False)
_fw5.music = type("M", (), {"pi_libh": "", "pi_miss": ("", []), "port": 0})()
_fw5.folder_t = 1e18


def _t5():
    _fw5.lib_sent, _fw5.lib_done = 0, -1e9
    _fw5.tick()


_t5()                                     # (die ersten zwei Stuecke gehen im selben Takt raus; 30 Lieder zu je 3)
_n5 = _fw5.lib_total
check(_n5 == 256 and len(_fw5.lib_chunks) == _n5 - 3 and _fw5.lib_h, f"Pi hat eine andere Fassung: alles schicken ({_n5} Stuecke)")
_fw5.lib_chunks = []
_fw5.music.pi_libh = _fw5.lib_h
_t5()
check(not _fw5.lib_chunks and _fw5.lib_same, "Pi hat dieselbe Fassung: nichts schicken")
_fw5.music.pi_libh, _fw5.music.pi_miss = "alt", (_fw5.lib_h, [1, 2, 7, 9])
_t5()
check([i for i, _ in _fw5.lib_chunks] == [9], "Pi meldet fehlende Stuecke: nur diese nachschicken (1, 2, 7 schon unterwegs, 9 folgt)")
# Titel geaendert: nur das Stueck mit diesem Lied (feste Stuecke zu 3 Liedern), auf der Fassung am Pi aufbauend
_h_alt = _fw5.lib_h
_fw5.lib_chunks, _fw5.music.pi_libh, _fw5.music.pi_miss, _fw5.music.pi_libd = [], _h_alt, ("", []), True
_lib5[13]["title"] = "Ganz anderer Titel, viel laenger als vorher " * 3
_t5()
check(_fw5.lib_base == _h_alt and _fw5.lib_cnt == 1 and _fw5.lib_h != _h_alt, "ein Titel geaendert: nur 1 Stueck schicken, mit der Fassung am Pi als Grundlage")
check(_fw5.status()["send"]["kind"] == "geaenderte" and _fw5.status()["send"]["n"] == 1 and _fw5.status()["send"]["total"] == _n5, "Statusanzeige: nur Geaenderte, 1 von 1")
_fw5.music.pi_libd = False
_t5()
check(len(_fw5.lib_chunks) == _n5 - 3 and not _fw5.lib_base, "Pi kann nichts einbauen (nach Neustart): alles schicken")
# Lied geloescht oder dazu: nur sein Stueck aendert sich (feste Plaetze nach dem Pfad, Fehlerbericht 07.11.2026)
_c1 = mb.library_chunks(_lib5, buckets=256)
_c2 = mb.library_chunks(_lib5[:7] + _lib5[8:], buckets=256)
_c3 = mb.library_chunks(_lib5 + [{"path": "/x/neu.mp3", "duration": 50.0, "artist": "Neu", "title": "Neu"}], buckets=256)
check(len(_c1) == len(_c2) == len(_c3) == 256 and sum(a != b for a, b in zip(_c1, _c2)) == 1 and sum(a != b for a, b in zip(_c1, _c3)) == 1,
      "Lied geloescht oder neu: genau ein Stueck anders, nicht alle dahinter")
check(mb.bucket_count(9319) == 4096 and mb.bucket_count(100) == 256, "Zahl der Stuecke: Zweierpotenz, rund 2,5 Lieder je Stueck")
_big = [{"path": f"/v/{k}.mp3", "duration": 1.0, "artist": "A" * 50, "title": "T" * 70} for k in range(40)]
check(max(len(json.dumps(c, separators=(",", ":"))) for c in mb.library_chunks(_big, buckets=4)) <= mb.BUCKET_MAX + 10,
      "volles Stueck: Lied kommt ins naechste, kein Paket ueber 4096 Byte")
# Helfer-Fall: Pi sammelt _h_v (fast fertig, Stueck 6 fehlt), die Liste aendert sich schon wieder (Energie-Schaetzung laeuft)
_h_v = _fw5.lib_h
_fw5.lib_chunks, _fw5.music.pi_libh, _fw5.music.pi_libd, _fw5.music.pi_miss = [], "alt", False, (_h_v, [6])
_lib5[2]["title"] = "Schon wieder anders"
_t5()
check(_fw5.lib_base == _h_v and _fw5.lib_cnt == 2 and _fw5.lib_kind == "geaenderte",
      "neue Fassung vor fertiger alter: das geaenderte Stueck und das fehlende auf der fast fertigen Fassung, nicht alles")
_li = open(os.path.join(os.path.dirname(fl.__file__), "install_launcher.sh"), encoding="utf-8").read()
check('"$BASE/mixxxdb.live.sqlite$X"' in _li and 'kill "$LIVE_PID"' in _li and '"mixxxdb.live.sqlite")' in open(mb.__file__, encoding="utf-8").read(),
      "Startskript kopiert die aktuelle Mixxx-Datenbank jede Minute, die Bruecke liest diese Kopie")
check(_r["title"] == "Schon in Mixxx" and _r["artist"] == "Alt" and _r["genre"] == "Pop" and _fw.lib[0]["title"] == "Alt",
      "Liste mit Titel aus der Datei, leere Felder (Interpret, Genre) aus Mixxx, Mixxx-Liste selbst unveraendert")

lib2 = fl.FolderLib(base=base, log=logs.append, key_id_from_text=mb.key_id_from_text)
lib2.start(root, [], wait=True)
check(len(lib2.songs) == 4 and "0 neu gelesen" in logs[-1], f"zweiter Durchgang: alles aus dem Zwischenspeicher, auch das bisherige Mixxx-Lied ({logs[-1]})")
check(not lib2.due(root) and lib2.due(root, now=lib2.t + fl.RESCAN_S + 1) and lib2.due(root + "/House"), "neuer Durchgang nach 10 Minuten oder anderem Ordner")

# ---- Musik-Datenbank: Feld 19 am Ende, Pi liest es ----
mixxx_rec = {"artist": "M", "title": "Aus Mixxx", "duration": 200.0, "bpm": 120.0, "key": "8A", "kid": 22, "comment": "8A - Energy 5",
             "crates": [], "cues": [], "path": "/nirgends/aus_mixxx.mp3", "bitrate": 320}
chunks = mb.library_chunks([mixxx_rec] + lib_dir.songs)
items = {x[3]: x for c in chunks for x in c}
check(len(items["One More"]) >= 19 and items["One More"][18] == 1 and items["Aus Mixxx"][18] == 0, "Feld 19: 1 = aus dem Ordner, 0 = aus Mixxx")
check(items["One More"][8] == 7 and items["One More"][15] == 0 and items["One More"][13] == 128, "Energie 7 nicht geschaetzt, Bitrate dabei")
check(items["Lang"][8] == 6 and items["Lang"][15] == 1 and items["Lang"][16] == 6, "geschaetzte Energie aus der Datei mit ~ und in der Vergleichsspalte")
d = mixxx_link.lib_item(items["One More"])
check(d["src"] == 1 and mixxx_link.lib_item(items["Aus Mixxx"])["src"] == 0, "Pi: src aus dem Feld")
check(mixxx_link.lib_item(items["Aus Mixxx"][:18])["src"] == 0 and mixxx_link.lib_item(["A - B", 100.0])["src"] == 0, "Pi: aeltere Bruecke ohne Feld = Mixxx")
check(list(d) == list(mixxx_link.LIB_FIELDS), "Pi: Reihenfolge der Felder wie LIB_FIELDS (Ablage am Pi)")


# ---- Forwarder: Ordner-Lieder kommen dazu, Vorhoeren darf sie liefern, Schaetzung bekommt sie ----
class Music:
    def __init__(self):
        self.loc = Locator([mixxx_rec["path"]], root)
        self.port = 9025


fw = mb.Forwarder([mixxx_rec], None, None, analysis_dir=os.path.join(tmp, "analysis"), analyze=False)
fw.folder = fl.FolderLib(base=base, key_id_from_text=mb.key_id_from_text)
fw.music = Music()
fw.folder_tick()
fw.folder.thread.join()
fw.folder_tick()
paths = {r["path"] for r in fw.lib}
check(len(fw.lib) == 5 and p_cbr in paths and mixxx_rec["path"] in paths and len(fw.mixxx_lib) == 1, "Bibliothek = Mixxx plus Ordner")
check(fw.music.loc.allowed(p_name) and fw.music.loc.locate(p_name) == p_name, "Vorhoeren liefert Ordner-Lieder")
es = {s["path"] for s in fw.energy_songs()}
check(p_name in es and p_vbr in es and p_cbr not in es, "Energie-Schaetzung bekommt Ordner-Lieder ohne eigene Stufe")
check(fw.stats()["n"] == 5, "Statistik zaehlt Ordner-Lieder mit")

# ---- ohne Mixxx-Datenbank ----
ns = argparse.Namespace(db=os.path.join(tmp, "fehlt.sqlite"), send="127.0.0.1", no_folder_lib=False)
import contextlib  # noqa: E402
import io  # noqa: E402
_err = io.StringIO()                                     # Hinweis der Bruecke hier stumm (verwirrte beim Push, Frage von Markus 07.11.2026)
with contextlib.redirect_stderr(_err):
    check(mb.open_library(ns) == [], "Datenbank fehlt: leere Mixxx-Liste, die Bruecke laeuft mit dem Ordner")
    check(mb.open_library(argparse.Namespace(db=None, send="127.0.0.1", no_folder_lib=False)) == [], "ohne --db, aber mit --send: Ordner-Liste")
check("nur Lieder aus dem Musikordner" in _err.getvalue(), "Bruecke meldet den Fall (im echten Betrieb im Protokoll)")
check(mb.open_library(argparse.Namespace(db=None, send=None, no_folder_lib=False)) is None, "nur Anzeige: keine Bibliothek")
try:
    mb.open_library(argparse.Namespace(db=ns.db, send="x", no_folder_lib=True))
    check(False, "ohne Ordner-Liste und ohne Datenbank: Abbruch mit Meldung")
except SystemExit as e:
    check("nicht gefunden" in str(e), "ohne Ordner-Liste und ohne Datenbank: Abbruch mit Meldung")
fw0 = mb.Forwarder([], None, None, analysis_dir=os.path.join(tmp, "analysis"), analyze=False)
fw0.folder, fw0.folder_root = fl.FolderLib(base=base, key_id_from_text=mb.key_id_from_text), root
fw0.folder_tick()
fw0.folder.thread.join()
fw0.folder_tick()
check(len(fw0.lib) == 4 and len(mb.library_chunks(fw0.lib)[0]) == 4, "ohne Mixxx: Musikordner aus config.sh, alle vier Lieder an den Pi")

# ---- Oberflaeche und Installation ----
js = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
html = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
check("k: 'src', mx: 1, th: 'Quelle'" in js and "fsrc && !r.src" in js and 'id="fsrc"' in html, "Musik-Datenbank: Spalte Quelle und Filter nur Ordner")
sh = open(os.path.join(BRIDGE, "install_launcher.sh"), encoding="utf-8").read()
check('"$HERE/folder_lib.py"' in sh and "DBARG" in sh, "Starter kopiert folder_lib.py und startet auch ohne Datenbank")

finish("Ordner-Lieder")
