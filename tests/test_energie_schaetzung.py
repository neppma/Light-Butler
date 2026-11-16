"""Geschaetzte Energiestufe fuer Lieder ohne Mixed In Key (Wunsch von Markus, 07.11.2026): Modell, Schaetzer in der Bruecke,
Kennzeichen "geschaetzt" bis ins Panel, Schreiben in die MP3 nur mit Schalter, nie ueber Mixed In Key, Musik bleibt gleich."""
import json
import os
import random
import sys
import tempfile

import numpy as np

from _common import ROOT, check, finish

BRIDGE = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BRIDGE)
import energy_level as el          # noqa: E402
import mixxx_bridge as mb          # noqa: E402
import mixxx_link                  # noqa: E402
import settings                    # noqa: E402
from showman import covers, store  # noqa: E402

# ---- Messen: alle Merkmale, auch bei kurzem Signal ----
t = np.arange(el.SR * 20) / el.SR
x = (0.3 * np.sin(2 * np.pi * 110 * t) * (np.sin(2 * np.pi * 2 * t) > 0) + 0.05 * np.random.RandomState(1).randn(len(t))).astype(np.float32)
f = el.measure(x, 120.0, 14)
check(all(k in f and np.isfinite(f[k]) for k in el.FEATS) and f["minor"] == 1.0 and "mfcc_s12" in f, "alle Merkmale gemessen")
try:
    el.measure(x[:el.SR], 120.0, 1)
    check(False, "zu kurz muss abgelehnt werden")
except ValueError:
    check(True, "Lied zu kurz: Fehler statt Unsinn")

# ---- Modell: lernen, speichern, laden, gleiche Schaetzung ----
rng = random.Random(3)
rows = []
for i in range(120):
    lv = 1 + i % 9
    ff = {k: rng.gauss(0, 1) for k in el.FEATS}
    ff["loud_mean"] = lv * 2.0 + rng.gauss(0, 0.3)
    ff.update({f"mfcc_m{j}": rng.gauss(0, 1) for j in range(el.N_MFCC)})
    ff.update({f"mfcc_s{j}": rng.gauss(0, 1) for j in range(el.N_MFCC)})
    rows.append({"path": f"/Volumes/S2L-TEST-GIBTS-NICHT/{i}.mp3", "lvl": lv, "genre": "house" if i % 2 else "pop", "f": ff})
m = el.Model().fit(rows, lam=1.0, genres=["house"])
m2 = el.Model.from_json(json.loads(json.dumps(m.to_json())))
check(list(m.predict(rows)) == list(m2.predict(rows)), "Modell nach Speichern und Laden gleich")
check((m.predict(rows) == np.array([r["lvl"] for r in rows])).mean() > 0.8, "klares Merkmal: Stufen gefunden")
try:
    el.Model.from_json(dict(m.to_json(), feats=["x"]))
    check(False, "fremdes Modell muss abgelehnt werden")
except ValueError:
    check(True, "Modell mit anderen Merkmalen abgelehnt")
real = os.path.join(BRIDGE, "energie_modell.json")
check(os.path.isfile(real) and el.Model.from_json(json.load(open(real, encoding="utf-8"))) is not None, "geeichtes Modell liegt bei der Bruecke")
inst = open(os.path.join(BRIDGE, "install_launcher.sh"), encoding="utf-8").read()
check('"$HERE/energy_level.py"' in inst and '"$HERE/energie_modell.json"' in inst, "install_launcher.sh kopiert Programm und Modell")

# ---- Schaetzer: liest Messwerte nach, auch halbe Zeilen erst spaeter ----
tmp = tempfile.mkdtemp(prefix="s2l_energie_")
mp = os.path.join(tmp, "modell.json")
json.dump(m.to_json(), open(mp, "w"))
fp_ = os.path.join(tmp, el.FEATS_FILE)
with open(fp_, "w", encoding="utf-8") as fh:
    for r in rows[:10]:
        fh.write(json.dumps(r) + "\n")
    fh.write(json.dumps({"path": "/kaputt.mp3", "err": "nicht lesbar"}) + "\n")
est = el.Estimator(base=tmp, model_path=mp)
check(len(est.est) == 10 and "/kaputt.mp3" in est.measured and est.level("/kaputt.mp3") is None, "Messwerte geschaetzt, unlesbare gemerkt")
with open(fp_, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rows[10])[:40])
check(not est.refresh() and len(est.est) == 10, "halbe Zeile wartet")
with open(fp_, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rows[10])[40:] + "\n")
check(est.refresh() and est.level(rows[10]["path"]) == int(m.predict([rows[10]])[0]), "Rest der Zeile kommt beim naechsten Mal")
check(el.Estimator(base=tmp, model_path=os.path.join(tmp, "fehlt.json")).level(rows[0]["path"]) is None, "ohne Modell: keine Schaetzung")

# ---- Bruecke: Mixed In Key geht vor, Schaetzung mit Kennzeichen ----
p0 = rows[0]["path"]
mik = {"path": p0, "comment": "8A - Energy 4", "artist": "A", "title": "Mit MIK", "duration": 200.0}
none = {"path": p0, "artist": "A", "title": "Ohne", "duration": 200.0}
check(mb.level_of(mik, est) == (4, False), "Stufe von Mixed In Key geht vor")
check(mb.level_of(none, est) == (est.level(p0), True), "sonst die Schaetzung, als geschaetzt markiert")
check(mb.level_of(none, None) == (None, False) and mb.level_of(dict(none, path="/unbekannt"), est) == (None, False), "ohne Schaetzung: keine Stufe")
items = [x for ch in mb.library_chunks([mik, none], est=est) for x in ch]
by = {x[3]: x for x in items}
check(by["Mit MIK"][8] == 4 and by["Mit MIK"][15] == 0 and by["Ohne"][8] == est.level(p0) and by["Ohne"][15] == 1,
      "Bibliothek: Stufe in Feld 9, Kennzeichen geschaetzt als letztes Feld")
check(mixxx_link.lib_item(by["Ohne"])["est"] == 1 and mixxx_link.lib_item(by["Mit MIK"])["est"] == 0
      and mixxx_link.lib_item(["T", 1.0])["est"] == 0, "Pi liest das Kennzeichen, alte Bruecke: nicht geschaetzt")
fw = mb.Forwarder([none], None, None, analysis_dir=tmp, analyze=False)
fw.est = est
check(fw.energy_songs() == [{"path": p0, "file": p0, "bpm": 0.0, "kid": 0, "genre": ""}], "nur Lieder ohne Mixed In Key werden gemessen")
fw.lib = [mik]
check(fw.energy_songs() == [], "Lied mit Mixed In Key: nicht messen")

# ---- Schalter am Pi: Standard aus, an die Bruecke ueber /api/musik/conf ----
spec = next(p for p in settings.DEFS if p.key == "energy_write")
src_set = open(os.path.join(ROOT, "pi", "settings.py"), encoding="utf-8").read()
check('"energy_write"' in src_set and (spec is None or spec.default == 0.0), "Einstellung energy_write, Standard aus")
import music_serve as ms   # noqa: E402
srv = ms.MusicServer([], port=0)
check(srv.energy_write is False, "Bruecke: ohne Antwort vom Pi wird nichts geschrieben")
srv.apply_conf({"root": "", "ew": True})
check(srv.energy_write is True, "Schalter an: Bruecke schreibt")
srv.apply_conf({"root": "", "ew": "ja"})
check(srv.energy_write is False, "nur echtes true schaltet ein")
api_src = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('"ew": ew' in api_src and 'cfg["energy_write"] > 0.5' in api_src, "Pi schickt den Schalter mit dem Musikordner")


# ---- In die MP3 schreiben ----
def id3(frames, pad=0, ver=3):
    data = b"".join(fid + (len(b).to_bytes(4, "big") if ver == 3 else bytes([(len(b) >> 21) & 127, (len(b) >> 14) & 127, (len(b) >> 7) & 127, len(b) & 127]))
                    + b"\0\0" + b for fid, b in frames) + b"\0" * pad
    n = len(data)
    return b"ID3" + bytes([ver, 0, 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127]) + data


AUDIO = bytes(random.Random(5).getrandbits(8) for _ in range(300000))
JPG = b"\xff\xd8\xff\xe0" + b"bild" * 50


def mp3(name, tag):
    p = os.path.join(tmp, name)
    with open(p, "wb") as fh:
        fh.write(tag + AUDIO)
    return p


def frames_of(p):
    with open(p, "rb") as fh:
        h = fh.read(10)
        n = (h[6] & 127) << 21 | (h[7] & 127) << 14 | (h[8] & 127) << 7 | (h[9] & 127)
        tag = fh.read(n)
        rest = fh.read()
    out, pos = [], 0
    while pos + 10 <= len(tag) and tag[pos:pos + 4].strip(b"\0"):
        raw = tag[pos + 4:pos + 8]
        s = (raw[0] & 127) << 21 | (raw[1] & 127) << 14 | (raw[2] & 127) << 7 | (raw[3] & 127) if h[3] == 4 else int.from_bytes(raw, "big")
        out.append((tag[pos:pos + 4], tag[pos + 10:pos + 10 + s]))
        pos += 10 + s
    return out, rest


apic = b"\0image/jpeg\0\x03\0" + JPG
a = mp3("platz.mp3", id3([(b"TIT2", b"\0Titel"), (b"APIC", apic)], pad=4096))
fpa = store.audio_fingerprint(a)
size0 = os.path.getsize(a)
check(el.write_energy_tag(a, 6) == "ok", "MP3 mit Fuellbytes: geschrieben")
fr, rest = frames_of(a)
check(rest == AUDIO and os.path.getsize(a) == size0, "nur der Kopf ueberschrieben, Musik und Groesse gleich")
check((b"TXXX", b"\0EnergyLevel\x006") in fr and (b"TXXX", b"\0EnergyLevelSource\0" + el.SRC_VALUE.encode()) in fr
      and (b"TIT2", b"\0Titel") in fr, "EnergyLevel wie Mixed In Key, Vermerk geschaetzt, andere Felder bleiben")
check(store.audio_fingerprint(a) == fpa and mb.audio_fingerprint(a) == fpa, "Fingerabdruck gleich: Shows, Kurven und Cover passen weiter")
check(covers.mp3_image(a) == JPG, "Cover bleibt lesbar")
check(el.write_energy_tag(a, 6) == "gleich", "zweites Mal: nichts zu tun")
check(el.write_energy_tag(a, 7) == "ok" and sum(1 for x in frames_of(a)[0] if x[0] == b"TXXX") == 2
      and (b"TXXX", b"\0EnergyLevel\x007") in frames_of(a)[0], "neue Schaetzung ersetzt die alte, kein doppelter Eintrag")

b = mp3("eng.mp3", id3([(b"TIT2", b"\0Titel")], pad=0, ver=4))
check(el.write_energy_tag(b, 3) == "ok", "ID3v2.4 ohne Platz: Datei neu geschrieben")
fr, rest = frames_of(b)
check(rest == AUDIO and (b"TXXX", b"\0EnergyLevel\x003") in fr and not [n for n in os.listdir(tmp) if n.endswith(".lb-tmp")],
      "Musik gleich, keine Hilfsdatei uebrig")
c = mp3("ohne.mp3", b"")
fpc = store.audio_fingerprint(c)
check(el.write_energy_tag(c, 5) == "ok" and frames_of(c)[1] == AUDIO and store.audio_fingerprint(c) == fpc, "MP3 ohne Kopf: Kopf vorangestellt, Fingerabdruck gleich")
d = mp3("mik.mp3", id3([(b"TXXX", b"\0EnergyLevel\x008")], pad=512))
raw_d = open(d, "rb").read()
check(el.write_energy_tag(d, 5) == "mik" and open(d, "rb").read() == raw_d, "Stufe von Mixed In Key nie ueberschrieben")
e = mp3("alt.mp3", b"ID3\x02\0\0\0\0\0\x10" + b"\0" * 16)
raw_e = open(e, "rb").read()
check(el.write_energy_tag(e, 5).startswith("ID3v2.2") and open(e, "rb").read() == raw_e, "unbekannte Form: Datei unberuehrt")
check(el.write_energy_tag(os.path.join(tmp, "x.m4a"), 5) == "keine MP3" and el.write_energy_tag(a, 0) == "Stufe ungueltig", "nur MP3, nur Stufe 1-9")

# ---- Schreiben in der Bruecke: einmal je Lied, nicht im Deck, Fehler nicht wiederholen ----
est2 = el.Estimator(base=tmp, model_path=mp)
est2.est = {"/m/a": 4, "/m/b": 5, "/m/d": 6, "/m/x": 2}
est2.write_tick([("/m/a", c), ("/m/b", b), ("/m/d", d), ("/m/x", os.path.join(tmp, "x.wav"))], busy=lambda p: p == "/m/b", gap_s=0)
est2.writer.join(5)
check(est2.written.get("/m/a") == 4 and "/m/b" not in est2.written and est2.written.get("/m/d") == "mik" and "/m/x" not in est2.written,
      "geschrieben, Lied im Deck ausgelassen, Mixed In Key gemerkt, keine MP3 uebergangen")
check(json.load(open(os.path.join(tmp, el.WRITTEN_FILE), encoding="utf-8"))["/m/a"] == 4, "gemerkt in geschrieben.json")
before = open(c, "rb").read()
est2.write_tick([("/m/a", c), ("/m/d", d)], gap_s=0)
check(est2.writer.is_alive() is False and open(c, "rb").read() == before, "nichts doppelt geschrieben")

# ---- Panel: E6~ ----
mj = open(os.path.join(ROOT, "pi", "static", "sm", "music.js"), encoding="utf-8").read()
wp = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check("(r.est && lvl ? '~' : '')" in mj and "(m.lvl_est?'~':'')" in wp, "Musik-Datenbank und Hauptpanel zeigen geschaetzt als E6~")
finish("Energie-Schaetzung")
