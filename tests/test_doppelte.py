"""Doppelte Lieder finden und aufraeumen (Wunsch von Markus, 07.11.2026, Datenbankpflege): Gruppen nach Dateiname oder
Interpret und Titel bei fast gleicher Laenge, Empfehlung welche Datei bleibt, Loeschen nur auf Klick in den Papierkorb."""
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import urllib.request

from _common import ROOT, check, finish

BRIDGE = os.path.join(ROOT, "mac", "mixxx_bridge")
sys.path.insert(0, BRIDGE)
import dupes as du          # noqa: E402
import id3_tags as it       # noqa: E402
import mixxx_bridge as mb   # noqa: E402
import music_serve as ms    # noqa: E402
import tag_edit as te       # noqa: E402

# ---- Vergleichsschluessel ----
check(du.stem_key("/a/AcDc - Highway to Hell (1).mp3") == du.stem_key("/b/acdc - highway to hell.MP4") == "acdc highway to hell", "Name ohne Ordner, Endung, (1)")
check(du.stem_key("/a/Lied_pn.mp4") == "lied" and du.stem_key("/a/Lied Kopie.mp3") == "lied", "Kopie-Zusaetze weg")
check(du.stem_key("/a/Gedanken der Kraft 01.mp3") != du.stem_key("/a/Gedanken der Kraft 02.mp3"), "Teil 01 und 02 bleiben verschieden")
check(du.title_key("Ac/Dc", "Highway to Hell") == "ac dc|highway to hell" and du.title_key("", "x") == "", "Interpret und Titel, beide noetig")


def rec(p, a="", t="", d=200.0, **kw):
    return dict(path=p, artist=a, title=t, duration=d, **kw)


LIB = [rec("/m/A/AcDc - Highway to Hell.mp3", "AcDc", "Highway to Hell", 207.5),
       rec("/m/A/1979/01 - AcDc - Highway.mp3", "AcDc", "Highway to Hell", 207.9),
       rec("/m/B/Bellini - Samba.mp3", "Bellini", "Samba", 441), rec("/m/B/05 - Bellini - Samba.mp3", "Bellini", "Samba", 71),
       rec("/m/G/Gedanken 01.mp3", "G", "Gedanken", 114), rec("/m/G/Gedanken 02.mp3", "G", "Gedanken", 170),
       rec("/m/X/Lied.mp4", "X", "Lied", 200), rec("/m/X/Lied.mp3", "", "", 200.4), rec("/m/X/weg.mp3", "X", "Lied", 200, missing=True),
       rec("/m/Y/Solo.mp3", "Y", "Solo", 100)]
gs = du.groups(LIB)
paths = [sorted(r["path"] for r in g) for g in gs]
check(sorted(["/m/A/1979/01 - AcDc - Highway.mp3", "/m/A/AcDc - Highway to Hell.mp3"]) in paths, "gleicher Interpret und Titel, gleiche Laenge: eine Gruppe")
check(["/m/X/Lied.mp3", "/m/X/Lied.mp4"] in paths, "gleicher Name als MP3 und MP4: eine Gruppe (auch ohne Tags)")
check(not any("/m/B/Bellini - Samba.mp3" in p for p in paths), "andere Laenge (Reprise 441 s gegen 71 s): keine Doppelten")
check(not any("/m/G/Gedanken 01.mp3" in p for p in paths), "Album mit lauter gleichen Titeln, verschiedene Laengen: keine Doppelten")
check(not any("/m/X/weg.mp3" in p for p in paths) and len(gs) == 2, "fehlende Dateien laut Mixxx zaehlen nicht")

# ---- Angaben je Datei ----
tmp = tempfile.mkdtemp(prefix="s2l_dupes_")
AUDIO = bytes(random.Random(8).getrandbits(8) for _ in range(30000))


def mp3(name, frames):
    data = b"".join(it.frame(f, b, 3) for f, b in frames) + b"\0" * 32
    n = len(data)
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(b"ID3" + bytes([3, 0, 0, (n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127]) + data + AUDIO)
    return p


JPG = b"\xff\xd8\xff\xe0" + b"x" * 40
a = mp3("a.mp3", [(b"TIT2", it.text_body("Lied")), (b"TPE1", it.text_body("X")), (b"TALB", it.text_body("Al")), (b"APIC", b"\x00image/jpeg\x00\x03\x00" + JPG)])
os.makedirs(os.path.join(tmp, "zwei"), exist_ok=True)   # echte Doppelte liegen in verschiedenen Ordnern
b = mp3(os.path.join("zwei", "b.mp3"), [(b"TIT2", it.text_body("anderer Kopf, gleiche Musik"))])
kw = dict(energy=mb.energy_level, has_cover=lambda f: ms.find_cover(f) is not None, read_tags=te.read_tags, fingerprint=mb.audio_fingerprint)
da = du.describe(rec(a, "X", "Lied", 200, bitrate=320, samplerate=44100, cues=[1, 2], comment="8A - Energy 7"), a, **kw)
db = du.describe(rec(b, "X", "Lied", 200, bitrate=128, samplerate=48000, src="dir"), b, **kw)
check(da["cover"] and not db["cover"] and da["tags"] == 3 and db["tags"] == 1 and da["kbps"] == 320 and da["cues"] == 2 and da["lvl"] == 7,
      "Cover, Tags, Bitrate, Hotcues, Energie je Datei")
check(da["fp"] and da["fp"] == db["fp"], "gleiche Musik, anderer Kopf: gleicher Fingerabdruck")
check(da["mixxx"] and not db["mixxx"] and da["sk"] == du.stem_key(a) and da["tk"] == "x|lied", "Mixxx oder nur Ordner, Vergleichsschluessel")
dn = du.describe(rec("/fehlt.mp3"), "/fehlt.mp3", **kw)
check(dn["exists"] is False and dn["fp"] == "", "fehlende Datei: nur Grundangaben")

# ---- Auswertung im Hintergrund ----
D = du.Dupes(lambda: [rec(a, "X", "Lied", 200), rec(b, "X", "Lied", 200)], lambda p: p, **kw)
r = D.get()
for _ in range(100):
    if r["state"] == "ok":
        break
    time.sleep(0.05)
    r = D.get()
check(r["state"] == "ok" and len(r["groups"]) == 1 and len(r["groups"][0]) == 2, "Auswertung fertig, eine Gruppe")
D.forget(b)
check(D.get()["groups"] == [], "nach dem Loeschen gleich ohne die Datei (Gruppe mit einer Datei verschwindet)")

# ---- Empfehlung (dupes.js, mit node gerechnet) ----
js = os.path.join(ROOT, "pi", "static", "sm", "dupes.js")
G = [dict(path="/m/Lied.mp4", ext="mp4", kbps=128, rate=44100, dur=200, cover=False, tags=0, cues=0, lvl=0, mixxx=True, exists=True, fp="", sk="lied", tk="x|lied"),
     dict(path="/m/Lied.mp3", ext="mp3", kbps=320, rate=44100, dur=200.5, cover=True, tags=6, cues=8, lvl=7, mixxx=True, exists=True, fp="1:a", sk="lied", tk="x|lied"),
     dict(path="/m/Anders.mp3", ext="mp3", kbps=320, rate=44100, dur=260, cover=True, tags=6, cues=0, lvl=0, mixxx=True, exists=True, fp="2:b", sk="anders", tk="x|lied ii"),
     dict(path="/m/Gleich.mp3", ext="mp3", kbps=320, rate=44100, dur=200.5, cover=True, tags=6, cues=8, lvl=7, mixxx=True, exists=True, fp="1:a", sk="gleich", tk="")]
PI = {"/m/Show.mp3": {"show": "Meine Show", "stems": True}}
code = ("const D=require(process.argv[1]);const G=JSON.parse(process.argv[2]);const PI=JSON.parse(process.argv[3]);"
        "const pl=D.plan(G,p=>PI[p]);console.log(JSON.stringify({keep:pl.keep,del:[...pl.del],sug:[...pl.sug],why:pl.why,rel:pl.rel}));")
out = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out["keep"] == 1, "behalten: die MP3 mit Cover, Tags und Hotcues")
check(0 in out["del"] and "MP3 statt MP4" in out["why"]["0"] and "320 statt 128 kbit/s" in out["why"]["0"], "MP4 neben gleicher MP3: zum Loeschen, mit Gruenden")
check(2 not in out["del"] and 2 not in out["sug"] and "anderes Lied" in out["why"]["2"], "andere Laenge: kein Vorschlag (nur ueber die Kette in der Gruppe)")
check(3 in out["del"] and out["rel"]["3"] == "gleich", "gleicher Fingerabdruck: gleiche Musik, vorab angehakt")
G2 = [dict(G[1], path="/m/Show.mp3", kbps=192, cover=False, tags=2, cues=0), dict(G[1], path="/m/Besser.mp3")]
out2 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G2), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out2["keep"] == 1 and 0 not in out2["del"] and "Show" in out2["why"]["0"], "Datei mit Show wird nie vorgeschlagen")
G3 = [dict(G[1], path="/m/a.mp3", fp="1:x"), dict(G[1], path="/m/b.mp3", fp="2:y")]
out3 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G3), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out3["del"] == [] and out3["sug"] == [1] and "gleichwertig" in out3["why"]["1"], "gleichwertig: Vorschlag ohne Haken, selbst entscheiden")

# ---- Seite, Server, Pi ----
dj = open(js, encoding="utf-8").read()
check("pageItems().shown.forEach(({ g, pl }) => out.push(...markedIn(g, pl)));" in dj and "const todo = marked();" in dj,
      "Papierkorb oben nur fuer die gezeigte Seite (Filter, Suche, Seite)")
check("const PAGE = 20;" in dj and "'<div class=\"pager\">" in dj, "lange Liste in Seiten zu 20 Gruppen (Wunsch 07.11.2026)")
check("<button class=\"gdel\"" in dj and "<button class=\"gkeep\"" in dj and "const todo = markedIn(g, pl);" in dj,
      "je Gruppe: markierte loeschen oder alle behalten, danach erledigt")
check("dir = parts.join('/')" in dj, "voller Ordnerpfad (Wunsch 07.11.2026)")
check("fetch(music + '/trash'" in dj and "SM.ask(todo.length + ' Dateien in den Papierkorb des Musik-Rechners legen?" in dj, "Loeschen nur nach Rueckfrage, in den Papierkorb")
srv = ms.MusicServer([a, b], port=0, trash=lambda f: None)
srv.dupes = D
D.result, D.t = [[du.describe(rec(a, "X", "Lied", 200), a, **kw), du.describe(rec(b, "X", "Lied", 200), b, **kw)]], time.time()
check(srv.start(), "Server startet")
with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/dupes", timeout=5) as resp:
    d = json.loads(resp.read())
check(d["state"] == "ok" and len(d["groups"]) == 1, "Gruppen ueber den Server")
req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/trash", data=json.dumps({"p": b, "name": "b.mp3"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=5) as resp:
    pass
check(D.result == [], "nach dem Papierkorb: Gruppe weg")
srv.stop()
mb_src = open(os.path.join(BRIDGE, "mixxx_bridge.py"), encoding="utf-8").read()
check("fw.dupes = Dupes(lambda: fw.lib, fw._map" in mb_src and "ms.dupes = fw.dupes" in mb_src, "Bruecke richtet die Auswertung ein")
for f_ in ("install_launcher.sh", os.path.join("..", "helper", "install_helper.sh")):
    check("dupes.py" in open(os.path.join(BRIDGE, f_), encoding="utf-8").read(), f"{os.path.basename(f_)} kopiert dupes.py")
api = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
mh = open(os.path.join(ROOT, "pi", "static", "sm", "music.html"), encoding="utf-8").read()
check('if path == "/musik/doppelte":' in api and ("href: '/musik/doppelte'" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pi", "static", "sm", "care.js"), encoding="utf-8").read()), "Seite Doppelte am Pi, Knopf in der Musik-Datenbank")
check(len(du.groups([rec("/m/SAMPLES/thx.mp3", "A", "THX", 14), rec("/m/F/thx.mp3", "A", "THX", 14)])) == 1,
      "Doppelte pruefen schliesst Samples ein (nur der Tag-Assistent laesst sie aus, Wunsch 07.11.2026)")
# ---- "Alle behalten" bleibt gemerkt ----
kf = os.path.join(tmp, "behalten.json")

K = du.Dupes(lambda: [rec(a, "X", "Lied", 200), rec(b, "X", "Lied", 200)], lambda p: p, kept_file=kf, **kw)
r = K.get()
for _ in range(100):
    if r["state"] == "ok":
        break
    time.sleep(0.05)
    r = K.get()
check(len(r["groups"]) == 1, "Gruppe da")
K.keep_all([a, b])
check(K.get()["groups"] == [] and json.load(open(kf, encoding="utf-8")) == [du.Dupes.gkey([a, b])], "alle behalten: weg und gemerkt")
K2 = du.Dupes(lambda: [rec(a, "X", "Lied", 200), rec(b, "X", "Lied", 200)], lambda p: p, kept_file=kf, **kw)
r = K2.get(fresh=True)
for _ in range(100):
    if r["state"] == "ok":
        break
    time.sleep(0.05)
    r = K2.get()
check(r["groups"] == [], "nach Neustart und neuer Pruefung kommt die Gruppe nicht wieder")
try:
    K2.keep_all([a])
    check(False, "eine Datei")
except ValueError:
    check(True, "Gruppe mit einer Datei: Fehler")
srv3 = ms.MusicServer([a, b], port=0)
srv3.dupes = du.Dupes(lambda: [], lambda p: p, kept_file=os.path.join(tmp, "b2.json"))
check(srv3.start(), "Server startet")
req = urllib.request.Request(f"http://127.0.0.1:{srv3.port}/dupes", data=json.dumps({"op": "keep", "paths": [a, b]}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=5) as resp:
    check(json.loads(resp.read())["ok"] and os.path.isfile(os.path.join(tmp, "b2.json")), "alle behalten ueber den Server")
srv3.stop()
# Fehlerbericht 07.11.2026: geloeschte MP3 stand noch als "Leiche" aus Mixxx in einer Gruppe
L2 = du.Dupes(lambda: [rec(a, "X", "Lied", 200), rec("/weg/Lied.mp3", "X", "Lied", 200)], lambda p: p, kept_file=os.path.join(tmp, "b3.json"), **kw)
r = L2.get()
for _ in range(100):
    if r["state"] == "ok":
        break
    time.sleep(0.05)
    r = L2.get()
check(r["groups"] == [], "fehlende Datei zaehlt nicht: Gruppe mit nur einer echten Datei verschwindet")
check("'Datei fehlt im Ordner'" in dj and "fehlt am Mac" not in dj, "allgemein formuliert: Datei fehlt im Ordner")
check("'<div class=\"fcv\"><img class=\"cvimg\" src=\"' + esc(music + '/cover?p='" in dj and "'<div class=\"fcv none\" title=\"kein Cover\"></div>'" in dj,
      "je Datei Cover (vergroesserbar) oder leerer Rahmen (Wunsch 07.11.2026)")
check("f.size ? mb(f.size) : ''" in dj, "Dateigroesse in MB")
# Wunsch 07.11.2026: bei sonst Gleichem die laengere (nicht abgeschnitten), dann die groessere behalten
G4 = [dict(G[1], path="/m/kurz.mp3", fp="1:k", dur=211.0, size=8_400_000), dict(G[1], path="/m/lang.mp3", fp="2:l", dur=213.0, size=8_500_000)]
out4 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G4), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out4["keep"] == 1 and 0 in out4["del"] and "länger (3:33 statt 3:31)" in out4["why"]["0"], "laengere behalten, die kuerzere vorab angehakt, mit Grund")
G5 = [dict(G[1], path="/m/klein.mp3", fp="1:k", size=8_000_000), dict(G[1], path="/m/gross.mp3", fp="2:g", size=8_600_000)]
out5 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G5), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out5["keep"] == 1 and out5["sug"] == [0], "gleich lang: groessere behalten, ohne Haken (selbst entscheiden)")
G6 = [dict(G[1], path="/m/hotcues.mp3", fp="1:h", dur=211.0), dict(G[1], path="/m/ohne.mp3", fp="2:o", dur=213.0, cues=0)]
out6 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G6), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out6["keep"] == 0, "Laenge zaehlt nur bei sonst Gleichem: Hotcues gehen vor")
dh = open(os.path.join(ROOT, "pi", "static", "sm", "dupes.html"), encoding="utf-8").read()
check("box-shadow: inset 4px 0 0 #3fbf6f" in dh and "box-shadow: inset 4px 0 0 #e0423a" in dh, "behalten gruen, loeschen rot, deutlich (Wunsch 07.11.2026)")
# Frage von Markus 07.11.2026 (Britney): 48 kHz war als Grund genannt, obwohl es nicht zaehlt; entschieden haben die Hotcues
G7 = [dict(G[1], path="/m/44.mp3", fp="1:a", rate=44100, dur=212.3, cues=5), dict(G[1], path="/m/48.mp3", fp="2:b", rate=48000, dur=210.5, cues=8)]
out7 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G7), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out7["keep"] == 1 and "kHz" not in out7["why"]["0"] and "8 statt 5 Hotcues" in out7["why"]["0"] and "Achtung: diese ist 2 s länger" in out7["why"]["0"],
      "kein kHz-Grund bei 48 gegen 44,1; Hinweis, wenn die zu loeschende laenger ist")
G8 = [dict(G[1], path="/m/22.mp3", fp="1:a", rate=22050), dict(G[1], path="/m/44b.mp3", fp="2:b", rate=44100)]
out8 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G8), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out8["keep"] == 1 and "44.1 statt 22.05 kHz" in out8["why"]["0"], "echte Luecke (22 kHz) zaehlt weiter")
check("<button class=\"pb ftag\"" in dj and "SM.tagEdit({ path: f.path, dur: f.dur || 0 }, music, d =>" in dj
      and '<script src="/static/sm/tagedit.js"></script>' in open(os.path.join(ROOT, "pi", "static", "sm", "dupes.html"), encoding="utf-8").read(),
      "Doppelte: Tag-Editor je MP3 (Wunsch 07.11.2026)")
# Fehlerbericht 07.11.2026: "01/07/08 - Klangraeume Catalogue" (gleiche Tags, selber Ordner) waren keine Doppelten
KL = [rec("/m/K/01 - Klang.mp3", "K", "Klang", 142), rec("/m/K/07 - Klang.mp3", "K", "Klang", 143), rec("/m/K/08 - Klang.mp3", "K", "Klang", 142),
      rec("/m/Andere/Klang.mp3", "K", "Klang", 142)]
check(du.groups(KL[:3]) == [], "selber Ordner, andere Tracknummer: nicht doppelt")
check(any("/m/Andere/Klang.mp3" in [r["path"] for r in g] for g in du.groups(KL)), "anderer Ordner mit gleichen Tags: weiter doppelt")
G9 = [dict(G[1], path="/m/K/01 - Klang.mp3", sk="01 klang", fp="1:a"), dict(G[1], path="/m/K/07 - Klang.mp3", sk="07 klang", fp="2:b")]
out9 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G9), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out9["del"] == [] and out9["sug"] == [], "Seite: selber Ordner, anderer Name, andere Musik: kein Vorschlag")

# Wunsch 07.11.2026: Tag-Inhalte vergleichen, fehlende vor dem Loeschen in die behaltene uebernehmen
td = ("const D=require(process.argv[1]);console.log(JSON.stringify(D.tagDiff({tv:{album:'A',year:'1993',genre:'Pop',bpm:'113.426',disc:'3/16'}},"
      "{tv:{album:'B',genre:'pop',bpm:'113.42'}})))")
tdo = json.loads(subprocess.run(["node", "-e", td, js], capture_output=True, text=True).stdout)
check(tdo["take"] == {"year": "1993", "disc": "3/16"}, "uebernimmt nur, was der behaltenen fehlt")
check(tdo["diff"] == ["Album: A (behalten: B)"], "anders: nur echte Unterschiede (Gross/klein und BPM-Nachkommastellen nicht)")
check("try { await transferTags(g, pl, todo); }" in dj and "ok += await trashFiles(t);" in dj and "Sie übernimmt vorher: " in dj,
      "vor dem Loeschen (Gruppe und Seite) die fehlenden Tags uebertragen, Rueckfrage nennt sie")
check("fields: put }" in dj and "if (keep.ext !== 'mp3' || !keep.tv) return;" in dj, "nur in eine MP3 und nur fehlende Felder")
dt = du.describe(rec(a, "X", "Lied", 200), a, **kw)
check(dt["tv"].get("album") == "Al" and dt["tv"].get("title") == "Lied", "Mac schickt die Tag-Inhalte je Datei")
# Wunsch 07.11.2026 (Toni Braxton): gleichwertig, dann bleibt die Datei ohne Tracknummer vorne, die nummerierte wird vorgeschlagen
G10 = [dict(G[1], path="/m/Secrets/11 - Toni Braxton - Secrets - I Love Me Some Him.mp3", fp="1:a", dur=300.0, size=1),
       dict(G[1], path="/m/Toni Braxton/Toni Braxton - I Love Me Some Him.mp3", fp="2:b", dur=300.0, size=1)]
out10 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G10), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out10["keep"] == 1 and out10["del"] == [0] and "Dateiname ohne Tracknummer" in out10["why"]["0"], "ohne Tracknummer behalten, die nummerierte vorab angehakt")
G11 = [dict(G10[0], cues=8), dict(G10[1], cues=3)]
out11 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G11), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out11["keep"] == 0, "Tracknummer zaehlt nur bei sonst Gleichem: mehr Hotcues gehen vor")
nb = subprocess.run(["node", "-e", "const s=require('fs').readFileSync(process.argv[1],'utf8');const m=s.match(/const numbered = (p => [^;]+);/);const f=eval(m[1]);"
                     "console.log(JSON.stringify(['/a/11 - X.mp3','/a/03. X.mp3','/a/2Pac - X.mp3','/a/50 Cent - X.mp3','/a/99 Luftballons.mp3'].map(f)))", js],
                    capture_output=True, text=True).stdout.strip()
check(nb == "[true,true,false,false,false]", f"Tracknummer erkannt, Namen wie 2Pac oder 50 Cent nicht ({nb})")
tn = subprocess.run(["node", "-e", "const D=require(process.argv[1]);console.log(JSON.stringify(["
                     "D.tagDiff({path:'/a/11 - Toni.mp3',tv:{}},{path:'/b/Toni.mp3',tv:{title:'x'}}).take,"
                     "D.tagDiff({path:'/a/11 - Toni.mp3',tv:{track:'11/14'}},{path:'/b/Toni.mp3',tv:{}}).take,"
                     "D.tagDiff({path:'/a/11 - Toni.mp3',tv:{}},{path:'/b/Toni.mp3',tv:{track:'3'}}).take]))", js], capture_output=True, text=True).stdout.strip()
check(tn == '[{"track":"11"},{"track":"11/14"},{}]', f"Tracknummer aus dem Dateinamen, wenn die behaltene keine hat; das Track-Feld geht vor ({tn})")
# Fehlerbericht 07.11.2026 (Bellini "Samba De Janeiro (Reprise)"): drei verschiedene Lieder mit gleichen Titel-Tags
G12 = [dict(G[1], path="/m/Artists/Bellini/11 - Samba.mp3", sk="11 samba", fp="1:a", dur=142, tv={"album": "Ritmo Latino", "track": "11", "key": "3A", "bpm": "135.7"}),
       dict(G[1], path="/m/Comp/13 - Samba.mp3", sk="13 samba", fp="2:b", dur=142, tv={"album": "Ritmo Latino", "track": "13", "key": "8A", "bpm": "135.713"}),
       dict(G[1], path="/m/Comp2/08 - Samba.mp3", sk="08 samba", fp="3:c", dur=144, tv={"album": "Andere", "track": "8", "key": "8A", "bpm": "133.585"})]
out12 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G12), json.dumps(PI)], capture_output=True, text=True).stdout)
check(out12["del"] == [] and out12["sug"] == [], "andere Tonart, anderes Tempo, gleiches Album mit anderer Tracknummer: kein Vorschlag")
dd = subprocess.run(["node", "-e", "const D=require(process.argv[1]);const t=(x,y)=>D.differs({tv:x},{tv:y});console.log(JSON.stringify(["
                     "t({key:'Am'},{key:'8A'}),t({key:'3A'},{key:'8A'}),t({bpm:'128'},{bpm:'64'}),t({bpm:'113.426'},{bpm:'113.42'}),"
                     "t({album:'Ritmo Latino',track:'11'},{album:'Ritmo latino',track:'13/16'}),t({album:'A',track:'1'},{album:'B',track:'3'})]))", js],
                    capture_output=True, text=True).stdout.strip()
check(dd == "[false,true,false,false,true,false]", f"Gegenbeweis: Am = 8A, halbes Tempo und Nachkommastellen gleich ({dd})")
G13 = [dict(G[1], path="/m/a/Lied.mp3", fp="9:z", tv={"key": "3A"}), dict(G[1], path="/m/b/Lied.mp3", fp="9:z", tv={"key": "8A"})]
out13 = json.loads(subprocess.run(["node", "-e", code, js, json.dumps(G13), json.dumps(PI)], capture_output=True, text=True).stdout)
check("gleich" in out13["rel"].values(), "gleicher Fingerabdruck gewinnt (Byte fuer Byte dieselbe Musik)")
# Wunsch 09.11.2026: ’ und ', ‐ und - gelten als gleich (5 Doppelte im selben Ordner, nur anders geschrieben)
check(du.title_key("The Weather Girls", "It’s Raining Men") == du.title_key("The Weather Girls", "It's Raining Men")
      and du.stem_key("/a/Safri Duo - Played‐a‐Live.mp3") == du.stem_key("/a/Safri Duo - Played-A-Live.mp3")
      and not du.same_folder_other_name("/a/The Weather Girls - It’s Raining Men.mp3", "/a/The Weather Girls - It's Raining Men.mp3"),
      "Apostrophe und Striche: gleiches Lied, auch im selben Ordner")
# Fehlerbericht 09.11.2026: Loeschen ging nicht ("Objekt nicht vorhanden", Finder haengt) bei "Vü Schöner Is Des G'fühl.mp3"
import subprocess as _sp  # noqa: E402
import unicodedata as _ud  # noqa: E402
import music_serve as _ms  # noqa: E402
_t = tempfile.mkdtemp(prefix="s2l_trash_")
_f = os.path.join(_t, _ud.normalize("NFD", "Vü Schöner.mp3"))
open(_f, "wb").write(b"x")
check(_ms.disk_name(os.path.join(_t, "Vü Schöner.mp3")) == _f, "Name genau wie auf dem Laufwerk (zerlegte Umlaute)")
_bin = os.path.join(_t, "papierkorb")
_old = _ms.trash_dir_for
_ms.trash_dir_for = lambda p: _bin


def _hang(*a, **k):
    raise _sp.TimeoutExpired("osascript", 20)


_ms.to_trash(os.path.join(_t, "Vü Schöner.mp3"), run=_hang)
_ms.trash_dir_for = _old
check(not os.path.exists(_f) and len(os.listdir(_bin)) == 1, "Finder haengt: Datei selbst in den Papierkorb des Laufwerks")
# Papierkorb des Mac darf das Programm nicht oeffnen (FAT-Stick, 09.11.2026): eigener Ordner "Light-Butler Papierkorb"
_calls = []
_real = _ms._move_into


def _fake(d, p):
    _calls.append(os.path.basename(d))
    if len(_calls) == 1:
        raise PermissionError("Operation not permitted")
    return os.path.join(d, os.path.basename(p))


_ms._move_into = _fake
_ms.trash_move("/Volumes/Stick/musik/x.mp3")
_ms._move_into = _real
check(len(_calls) == 2 and _calls[1] == "Light-Butler Papierkorb", "Papierkorb gesperrt: eigener Ordner oben auf dem Stick " + str(_calls))
# Fehlerbericht 09.11.2026 (Fendrich): Umbenennen nur mit zusammengesetztem Pfad moeglich; alle Schreibweisen werden probiert
_vs = _ms._variants(os.path.join(_t, "Gefühl", "Vü.mp3"))
check(len(_vs) >= 2 and any(_ud.is_normalized("NFC", v) for v in _vs) and any(not _ud.is_normalized("NFC", v) for v in _vs),
      "Schreibweisen: zusammengesetzt und zerlegt")
_t2 = tempfile.mkdtemp(prefix="s2l_trash2_")
_f2 = os.path.join(_t2, "Vü Schöner.mp3")
open(_f2, "wb").write(b"x")
_bin2 = os.path.join(_t2, "korb")
_old2 = _ms.trash_dir_for
_ms.trash_dir_for = lambda p: _bin2
_ms.to_trash(_f2, run=lambda *a, **k: (_ for _ in ()).throw(AssertionError("Finder nicht noetig")))
_ms.trash_dir_for = _old2
check(not os.path.exists(_f2) and os.listdir(_bin2) == ["Vü Schöner.mp3"] or len(os.listdir(_bin2)) == 1, "Umlaute: ohne Finder selbst in den Papierkorb")
# Fehlerbericht 09.11.2026 (Gleiche Namen, "Kröger"): Abspielen mit zerlegten Umlauten im Pfad
_loc = _ms.Locator([os.path.join(_t, "Kröger.mp3")])
check(_loc.allowed(_ud.normalize("NFD", os.path.join(_t, "Kröger.mp3"))) and not _loc.allowed(os.path.join(_t, "Fremd.mp3")),
      "Vorhoeren: Pfad mit zerlegten Umlauten ist erlaubt, fremde Pfade nicht")
# Gleiches Album und gleiche Tracknummer, fast genau gleich lang (Wunsch 14.11.2026, Austria 3 "Der Wind"): Titel und Name egal
A3 = [{"path": "/m/A3/Austria 3 - Der Wind.mp3", "artist": "Austria 3", "title": "Der Wind", "album": "Austro Pop Parade", "tracknumber": "8", "duration": 285.78},
      {"path": "/m/A3/Disc/Austria 3 - Austria 3 - Austro Pop Parade (Austro Pop Parade).mp3", "artist": "Austria 3", "title": "Austria 3 - Austro Pop Parade",
       "album": "Austro Pop Parade", "tracknumber": "8/18", "duration": 285.88},
      {"path": "/m/B/14a.mp3", "artist": "The Beatles", "title": "I Feel Fine", "album": "The Beatles", "tracknumber": "14", "duration": 138.2},
      {"path": "/m/B/14b.mp3", "artist": "The Beatles", "title": "Run for Your Life", "album": "The Beatles", "tracknumber": "14", "duration": 139.0},
      {"path": "/m/C/x.mp3", "artist": "C", "title": "Eins", "album": "", "tracknumber": "3", "duration": 200.0},
      {"path": "/m/C/y.mp3", "artist": "C", "title": "Zwei", "album": "", "tracknumber": "3", "duration": 200.0}]
gA = [sorted(r["path"].split("/")[-1] for r in g) for g in du.groups(A3)]
check(gA == [["Austria 3 - Austria 3 - Austro Pop Parade (Austro Pop Parade).mp3", "Austria 3 - Der Wind.mp3"]],
      "gleiches Album + Track + Laenge auf 0,3 s: doppelt; 0,8 s Unterschied oder ohne Album nicht: " + str(gA))
finish("Doppelte")
