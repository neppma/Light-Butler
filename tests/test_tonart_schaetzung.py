"""Tonart fuer Lieder ohne Tonart in Mixxx (Wunsch von Markus, 07.11.2026): TKEY der Datei, sonst Schaetzung (essentia, sonst
numpy), Kennzeichen "~" bis ins Panel, Schreiben ins TKEY nur mit Schalter und nie ueber eine vorhandene Tonart. Dazu die
Spalte "Energie geschaetzt" in der Musik-Datenbank zum Vergleichen mit Mixed In Key."""
import json
import os
import random
import sys
import tempfile

import numpy as np

from _common import ROOT, check, finish

BRIDGE = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BRIDGE)
import id3_tags as it            # noqa: E402
import key_estimate as ke        # noqa: E402
import mixxx_bridge as mb        # noqa: E402
import mixxx_link                # noqa: E402
from showman import store        # noqa: E402

# ---- Schreibweisen: wie die Bruecke, dazu "A minor" (essentia) ----
for t in ("8A", "12B", "1m", "5d", "Fm", "F#m", "Bb", "H", "Am", "", "x", "13A"):
    check(ke.kid_from_text(t) == mb.key_id_from_text(t), f"Tonart {t!r} wie in der Bruecke")
check(ke.kid_from_text("A minor") == ke.kid_from_text("Am") == 22 and ke.kid_from_text("C major") == 1 and ke.kid_from_text("Eb minor") == 16,
      "essentia-Schreibweise verstanden")
check(all(ke.kid_from_text(ke.camelot(k)) == k for k in range(1, 25)) and ke.camelot(0) == "" and ke.camelot(22) == "8A" and ke.camelot(1) == "8B",
      "Camelot hin und zurueck fuer alle 24 Tonarten")

# ---- numpy-Schaetzung: Dreiklang erkannt ----
sr = 22050
t = np.arange(sr * 12) / sr
for root, minor, kid in ((9, True, 22), (0, False, 1), (7, False, 8)):
    third = 3 if minor else 4
    x = sum(np.sin(2 * np.pi * 220.0 * 2 ** ((root - 9 + iv) / 12.0) * t) for iv in (0, third, 7, 12)).astype(np.float32)
    check(ke.key_from_chroma(ke.chroma(x, sr)) == kid, f"Dreiklang {ke.camelot(kid)} aus dem Klang erkannt")
check(ke.key_from_chroma(np.ones(12)) == 0, "keine Tonart in flachem Spektrum")

# ---- ID3 lesen und schreiben ----
tmp = tempfile.mkdtemp(prefix="s2l_tonart_")
AUDIO = bytes(random.Random(9).getrandbits(8) for _ in range(200000))


def id3(frames, pad=0, ver=3):
    data = b"".join(it.frame(fid, body, ver) for fid, body in frames) + b"\0" * pad
    n = len(data)
    return b"ID3" + bytes([ver, 0, 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127]) + data


def mp3(name, tag):
    p = os.path.join(tmp, name)
    with open(p, "wb") as fh:
        fh.write(tag + AUDIO)
    return p


def audio_of(p):
    r = it.read(p)
    with open(p, "rb") as fh:
        fh.seek(10 + r[1] if r[1] else 0)
        return fh.read()


a = mp3("mit_tkey.mp3", id3([(b"TKEY", it.text_body("10B")), (b"TIT2", it.text_body("Lied"))], pad=256))
check(it.read_text(a, b"TKEY") == "10B" and ke.measure_one({"path": "/m/a", "file": a}) == {"path": "/m/a", "kid": ke.kid_from_text("10B"), "src": "tag", "v": ke.KEY_VERSION},
      "TKEY der Datei geht vor jeder Schaetzung")
raw_a = open(a, "rb").read()
check(ke.write_key_tag(a, 22) == "vorhanden" and open(a, "rb").read() == raw_a, "vorhandene Tonart nie ueberschrieben")
b = mp3("ohne.mp3", id3([(b"TIT2", it.text_body("Lied"))], pad=512, ver=4))
fpb = store.audio_fingerprint(b)
check(ke.write_key_tag(b, 22) == "ok" and it.read_text(b, b"TKEY") == "8A", "geschaetzte Tonart als Camelot ins TKEY, ohne Wellenlinie")
check(audio_of(b) == AUDIO and store.audio_fingerprint(b) == fpb and it.read_text(b, b"TIT2") == "Lied", "Musik, Fingerabdruck und andere Felder gleich")
check(ke.write_key_tag(b, 22) == "gleich", "zweites Mal: nichts zu tun")
check(ke.write_key_tag(b, 1) == "ok" and it.read_text(b, b"TKEY") == "8B" and sum(1 for f in it.read(b)[2] if f[0] == b"TKEY") == 1,
      "eigene Schaetzung darf ersetzt werden, nur ein TKEY")
c = mp3("leer.mp3", b"")
check(ke.write_key_tag(c, 5) == "ok" and audio_of(c) == AUDIO and it.read_text(c, b"TKEY") == ke.camelot(5), "MP3 ohne Kopf: Kopf vorangestellt")
check(ke.write_key_tag(os.path.join(tmp, "x.flac"), 5) == "keine MP3" and ke.write_key_tag(b, 0) == "Tonart ungueltig", "nur MP3, nur gueltige Tonart")

# ---- Schaetzer in der Bruecke ----
base = os.path.join(tmp, "tonart")
os.makedirs(base)
with open(os.path.join(base, ke.KEYS_FILE), "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"path": "/m/tag", "kid": 3, "src": "tag"}) + "\n")
    fh.write(json.dumps({"path": "/m/ess", "kid": 22, "src": "essentia", "v": 2}) + "\n")
    fh.write(json.dumps({"path": "/m/kaputt", "kid": 0, "src": "err"}) + "\n")
    fh.write(json.dumps({"path": "/m/alt", "kid": 5, "src": "essentia"}) + "\n")
    fh.write(json.dumps({"path": "/m/rauschen", "kid": 0, "src": "unsicher", "st": 0.4, "v": 2}) + "\n")
kest = ke.KeyEstimator(base=base, ess_py="")
check("/m/alt" not in kest.keys, "Schaetzung von frueher (ohne Grenzen) wird neu gemessen")
check(kest.key("/m/rauschen") == (0, 2), "nicht eindeutig: keine Tonart, Kennzeichen 2")
check(ke.judge(22, 0.9, 200.0) == (22, "") and ke.judge(22, 0.5, 200.0) == (0, "unsicher") and ke.judge(22, 0.9, 13.0) == (0, "unsicher")
      and ke.judge(1, 0.83, 8052.0) == (0, "unsicher") and ke.judge(8, None, 200.0) == (8, ""),
      "unsicher bei geringer Sicherheit, Geraeusch-Schnipsel und ganzem DJ-Set (Fehlerbericht 07.11.2026)")
check(kest.key("/m/tag") == (3, False) and kest.key("/m/ess") == (22, True) and kest.key("/m/kaputt") == (0, False) and kest.key("/m/neu") == (0, False),
      "aus der Datei = nicht geschaetzt, essentia = geschaetzt, unlesbar = keine")
check(kest.python() == sys.executable and ke.KeyEstimator(base=base, ess_py=sys.executable).python() == sys.executable,
      "ohne ~/s2l-key: numpy mit dem Python der Bruecke")
lib = [{"path": "/m/rauschen", "artist": "A", "title": "Rauschen", "duration": 100.0, "kid": 0, "key": ""},
       {"path": "/m/ess", "artist": "A", "title": "Geschaetzt", "duration": 100.0, "kid": 0, "key": ""},
       {"path": "/m/mixxx", "artist": "A", "title": "Mixxx", "duration": 100.0, "kid": 9, "key": "4B"},
       {"path": "/m/tag", "artist": "A", "title": "Tag", "duration": 100.0, "kid": 0, "key": ""}]
items = {x[3]: x for ch in mb.library_chunks(lib, kest=kest) for x in ch}
check(items["Geschaetzt"][5:7] == ["8A", 22] and items["Geschaetzt"][17] == 1, "Bibliothek: geschaetzte Tonart mit Kennzeichen")
check(items["Mixxx"][5:7] == ["4B", 9] and items["Mixxx"][17] == 0 and items["Tag"][6] == 3 and items["Tag"][17] == 0, "Mixxx geht vor, Tonart aus der Datei ohne Kennzeichen")
check(items["Rauschen"][6] == 0 and items["Rauschen"][17] == 2 and mixxx_link.lib_item(items["Rauschen"])["kest"] == 2,
      "nicht bestimmbar bis zum Pi (Panel: ?)")
li = mixxx_link.lib_item(items["Geschaetzt"])
check(li["kest"] == 1 and li["kid"] == 22 and mixxx_link.lib_item(items["Mixxx"])["kest"] == 0 and mixxx_link.lib_item(["T", 1.0])["kest"] == 0,
      "Pi liest das Kennzeichen, alte Bruecke: nicht geschaetzt")
fw = mb.Forwarder(lib, None, None, analysis_dir=tmp, analyze=False)
fw.kest = kest
started = []
kest.start = lambda songs: started.append(songs) or 0
kest.running = lambda: False
fw.key_tick()
check(started and sorted(s["path"] for s in started[0] if s["need_key"]) == ["/m/ess", "/m/rauschen", "/m/tag"], "nur Lieder ohne Tonart in Mixxx werden gemessen")

# ---- Schreiben in der Bruecke ----
kest2 = ke.KeyEstimator(base=base, ess_py="")
kest2.keys = {"/m/b": (5, "essentia"), "/m/a": (22, "essentia"), "/m/t": (3, "tag"), "/m/deck": (4, "numpy"), "/m/u": (0, "unsicher")}
d = mp3("deck.mp3", b"")
raw_d = open(d, "rb").read()
u = mp3("unsicher.mp3", b"")
raw_u = open(u, "rb").read()
kest2.write_tick([("/m/b", b), ("/m/a", a), ("/m/t", c), ("/m/deck", d), ("/m/u", u)], busy=lambda p: p == "/m/deck", gap_s=0)
kest2.writer.join(5)
check(kest2.written.get("/m/b") == 5 and kest2.written.get("/m/a") == "vorhanden" and "/m/t" not in kest2.written and "/m/deck" not in kest2.written
      and open(d, "rb").read() == raw_d, "nur geschaetzte, Lied im Deck ausgelassen, vorhandene Tonart gemerkt")
check("/m/u" not in kest2.written and open(u, "rb").read() == raw_u, "nicht bestimmbar: nichts in die Datei, auch kein Platzhalter")
check(json.load(open(os.path.join(base, ke.WRITTEN_FILE), encoding="utf-8"))["/m/b"] == 5, "gemerkt in geschrieben.json")

# ---- Pi: Schalter, Tonart fuer das Licht nur ohne Tonart aus Mixxx ----
import music_serve as ms   # noqa: E402
srv = ms.MusicServer([], port=0)
check(srv.key_write is False, "Bruecke: ohne Antwort vom Pi wird nichts geschrieben")
srv.apply_conf({"root": "", "ew": False, "kw": True})
check(srv.key_write is True and srv.energy_write is False, "Schalter key_write unabhaengig von energy_write")
src_set = open(os.path.join(ROOT, "pi", "settings.py"), encoding="utf-8").read()
check('"key_write"' in src_set, "Einstellung key_write")
import settings  # noqa: E402
spec = {p.key: p for p in settings.DEFS}
check(spec["key_write"].default == 0.0 and spec["energy_write"].default == 0.0, "beide Schalter Standard aus")
link_src = open(os.path.join(ROOT, "pi", "mixxx_link.py"), encoding="utf-8").read()
check('if not st["fk"] and isinstance(ki, int) and 1 <= ki <= 24' in link_src, "Licht: Tonart aus der Bruecke nur, wenn Mixxx keine kennt")
inst = open(os.path.join(BRIDGE, "install_launcher.sh"), encoding="utf-8").read()
check('"$HERE/key_estimate.py"' in inst and '"$HERE/id3_tags.py"' in inst, "install_launcher.sh kopiert die neuen Dateien")

# ---- Energie geschaetzt neben Mixed In Key ----
import energy_level as el   # noqa: E402


class _E:
    def level(self, p):
        return {"/m/mik": 6, "/m/ohne": 4}.get(p)


elib = [{"path": "/m/mik", "artist": "A", "title": "MIK", "duration": 9.0, "comment": "8A - Energy 7"},
        {"path": "/m/ohne", "artist": "A", "title": "Ohne", "duration": 9.0}]
ei = {x[3]: x for ch in mb.library_chunks(elib, est=_E()) for x in ch}
check(ei["MIK"][8] == 7 and ei["MIK"][16] == 6 and ei["Ohne"][8] == 4 and ei["Ohne"][16] == 4, "Original bleibt, Schaetzung extra zum Vergleichen")
check(mixxx_link.lib_item(ei["MIK"])["elv"] == 6 and mixxx_link.lib_item(ei["MIK"])["lvl"] == 7 and mixxx_link.lib_item(["T", 1.0])["elv"] == 0,
      "Pi liest beide Werte")
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
check("k: 'elv', th: 'E geschätzt'" not in mj and "(r.kest ? '~' : '')" in mj and "if (r.kest === 2) return '<span class=\"dim\">?</span>'" in mj, "Musik-Datenbank: Spalte Energie geschaetzt ausgeblendet (09.11.2026), Tonart mit ~")
check(el is not None, "")
finish("Tonart-Schaetzung")
