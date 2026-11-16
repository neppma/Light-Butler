"""Showmanager mit Mixxx: Anzeige SHOW, Knopf und Sperre im Panel, Fingerabdruck, Show startet und folgt dem hoerbaren Deck."""
import os
import shutil
import sys
import tempfile

from _common import DT, ROOT, Clock, build, check, finish, ch

import webpanel
from mixxx_link import MixxxLink
from showman import timeline as tl
from showman.api import ShowManager
from showman.engine import MIXXX
from showman.store import audio_fingerprint

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge                                               # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_mx_")


def track(fx, attr, keys):
    return {"target": {"fixture": fx}, "attr": attr, "keys": [{"t": t, "v": v, "e": "linear"} for t, v in keys], "clips": []}


# ---- Fingerabdruck ----------------------------------------------------------------------------------------------
def mp3(path, audio, tag=b"", id3v1=False):
    head = b""
    if tag:
        n = len(tag)
        head = b"ID3\x04\x00\x00" + bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F]) + tag
    with open(path, "wb") as f:
        f.write(head + audio + (b"TAG" + bytes(125) if id3v1 else b""))


audio = bytes(range(256)) * 4000
a, b, c = (os.path.join(tmp, n) for n in ("a.mp3", "b.mp3", "c.mp3"))
mp3(a, audio)
mp3(b, audio, tag=b"Energy 7" * 50, id3v1=True)
mp3(c, audio[:-1000])
check(audio_fingerprint(a) == audio_fingerprint(b), "andere Tags: derselbe Fingerabdruck")
check(audio_fingerprint(a) != audio_fingerprint(c), "andere Musiklaenge: anderer Fingerabdruck")
check(audio_fingerprint(b) == mixxx_bridge.audio_fingerprint(b), "Pi und Mac rechnen gleich")

lib = [{"artist": f"A{i}", "title": "Ö" * 30, "duration": 200.0} for i in range(500)]
ch_ = mixxx_bridge.library_chunks(lib)
import json
check(len(ch_) > 1 and sum(len(x) for x in ch_) == 500, "Bibliothek in Stuecken")
check(all(len(json.dumps({"type": "lib", "i": 999, "n": 999, "t": x}, separators=(",", ":"))) < 4096 for x in ch_), "jedes Stueck passt in ein Paket")


# ---- Aufbau ------------------------------------------------------------------------------------------------------
def setup(auto=1.0):
    link = MixxxLink(0)
    rig, sh = build(strobe=False, mixxx=link)
    base = tempfile.mkdtemp(dir=tmp)
    mgr = ShowManager(sh, base)
    sh.cfg.set("sm_mixxx_auto", auto)
    sh.cfg.set("mixxx_lead_s", 0.0)
    return link, rig, sh, mgr


def make(mgr, name, title="", dur=0.0, fp_from=None, on=True, duration=240.0, v=200):
    doc = mgr.store.create(name)
    doc.update(duration=duration, tracks=[track("vega", "dimmer", [(0, 0), (240, 240)]), track("par", "dimmer", [(0, v)])])
    doc["mixxx"] = {"title": title, "dur": dur, "on": on}
    if fp_from:
        shutil.copy(fp_from, mgr.store.path(name, "audio.mp3"))
    mgr.store.save(name, doc)
    mgr.index_dirty = True


class Rig:
    """Simuliert Mixxx: Deck-Meldungen, Plan und laufende Zeit."""

    def __init__(self, link, sh, mgr):
        self.link, self.sh, self.mgr = link, sh, mgr
        self.c = Clock(sh)
        self.n = 0

    def plan(self, d, title, du, fp=""):
        self.link.feed({"type": "plan", "d": d, "key": title, "title": title, "du": du, "ev": [], "en": [], "fp": fp}, self.c.t)

    def deck(self, d, pos, du=240.0, rate=1.0, playing=1, vo=1.0):
        self.link.feed({"d": d, "pp": pos / du, "du": du, "rr": rate, "bp": 128.0, "pl": playing, "tl": 1, "vo": vo}, self.c.t)

    def run(self, sec, each=None):
        for _ in range(int(round(sec / DT))):
            if each:
                each()
            self.c.run(DT)
            self.n += 1
            if self.n % 8 == 0:
                self.mgr.mixxx_tick(self.c.t)


# ---- Panel: SHOW statt AUTO ---------------------------------------------------------------------------------------
print("Panel")
link, rig, sh, mgr = setup(0.0)
make(mgr, "S1")
e = mgr.engine
c = Clock(sh)
sh.command({"auto": True})
snap = sh.snapshot()
check(snap["mode"] == "auto" and snap["pilot"], "vor der Show: AUTO")
e.load(mgr.store.load("S1"))
e.play(c.t, 0.0, False, "b1")
c.run(0.2)
check(sh.snapshot()["mode"] == "auto", "Licht aus: das Panel bleibt zu Recht bei AUTO")
e.set_light(True)
c.run(0.2)
snap = sh.snapshot()
check(snap["mode"] == "show" and snap["sm_show"] == "S1" and not snap["pilot"], "Licht an: Betriebsart SHOW, nicht AUTO")
check(snap["color"] == "" and snap["speed"] == "auto" and snap["move"] == "" and snap["mixbtn"] == "", "keine Knoepfe von AUTO markiert")
sh.command({"color": "rot"})
check(sh.auto_color != "rot" and sh.note.startswith("Show aktiv"), "Farbe gesperrt, mit Hinweis")
sh.command({"move": "Kreis"})
check(sh.auto_move != "Kreis", "Bewegung gesperrt")
sh.command({"master": 0.5})
check(sh.master == 0.5, "General Dimmer bleibt frei")
sh.master = 1.0
sh.command({"blackout": True})
c.run(0.1)
check(sh.snapshot()["mode"] == "blackout", "BLACKOUT bleibt frei und wird angezeigt")
sh.command({"blackout": False})
c.run(0.1)
check(sh.snapshot()["mode"] == "show", "danach wieder SHOW")
sh.sa = None
before = sh.sc
c.run(40.0)
check(sh.sc is before and sh.sa is None, "Szenen-Automatik ruht waehrend der Show")
sh.command({"auto": "toggle"})
c.run(0.1)
snap = sh.snapshot()
check(not e.loaded and not e.active() and snap["mode"] == "auto" and snap["pilot"], "Knopf SHOW beendet die Show: zurueck zu AUTO")
check(not sh.status.startswith("SHOW"), "Hauptschleife wieder bei AUTO")
sh.command({"color": "rot"})
check(sh.note != "Show aktiv: zum Bedienen die Show beenden", "Sperre der Show aufgehoben")
page = webpanel.make_page()
for s_ in ("S.mode==='show'", "TXT.mode_show", "tr('mode_show')", "S.sm_show", "['smshow',", "#evslot.smshow"):
    check(s_ in page, f"Panel kennt {s_}")

# ---- Mixxx: Start, Folgen, Ende ----------------------------------------------------------------------------------
print("Mixxx")
link, rig, sh, mgr = setup(1.0)
make(mgr, "Mit MP3", fp_from=b)
make(mgr, "Mit Titel", title="Künstler - Lied", dur=240.0)
e = mgr.engine
m = Rig(link, sh, mgr)
check(mgr.match(audio_fingerprint(a), "", 0)["name"] == "Mit MP3", "Fund ueber die MP3, auch mit anderen Tags")
check(mgr.match("", "KÜNSTLER -  Lied", 240.4)["name"] == "Mit Titel", "Fund ueber den gewaehlten Titel")
nfd = "Künstler - Lied"
check(mgr.match("", nfd, 240.0)["name"] == "Mit Titel", "Titel mit zerlegten Umlauten (NFD)")
check(mgr.match("", "Künstler - Lied", 300.0) is None, "andere Laenge: kein Treffer (Remix)")
check(mgr.match("0:nix", "Fremd", 240.0) is None, "fremdes Lied: keine Show")

m.plan(1, "Fremd", 240.0)
m.run(1.5, lambda: m.deck(1, 10.0))
check(not e.loaded, "Lied ohne Show: AUTO bleibt")
m.plan(1, "Künstler - Lied", 240.0)
pos = [20.0]


def adv(rate=1.0):
    def f():
        pos[0] += DT * rate
        m.deck(1, pos[0], rate=rate)
    return f


m.run(0.3, adv())
check(not e.loaded, "erst nach kurzer Zeit (kein Starten beim Durchblaettern)")
m.run(1.0, adv())
check(e.loaded and e.owner == MIXXX and e.active() and e.light, "Lied mit Show: sie uebernimmt das Licht")
check(sh.snapshot()["mode"] == "show" and sh.snapshot()["sm_show"] == "Mit Titel", "Panel zeigt SHOW")
check(e.status(m.c.t)["src"] == "mixxx", "Quelle Mixxx")
check(sh.strobe is False, "Strobe-Erlaubnis bleibt unberuehrt")
m.run(10.0, adv())
check(abs(e.position(m.c.t) - pos[0]) < 0.05, f"folgt dem Deck (Abweichung {abs(e.position(m.c.t) - pos[0]) * 1000:.0f} ms)")
check(abs(ch(rig, "vega", "dimmer") - pos[0]) < 1.5, "Licht passt zur Stelle im Lied")
m.run(20.0, adv(1.08))
check(abs(e.position(m.c.t) - pos[0]) < 0.05 and e.clock.jumps == 0, f"Pitch +8 %: folgt ohne Spruenge ({abs(e.position(m.c.t) - pos[0]) * 1000:.0f} ms)")
pos[0] = 100.0
m.run(1.0, adv())
check(abs(e.position(m.c.t) - pos[0]) < 0.05, "Sprung im Lied: folgt")
m.run(1.0, lambda: m.deck(1, pos[0], playing=0))
check(e.loaded, "kurzes Stocken: Show bleibt")
m.run(1.5, lambda: m.deck(1, pos[0], playing=0))
check(not e.loaded and sh.snapshot()["mode"] != "show", "Pause in Mixxx: zurueck zu AUTO")
m.run(2.0, adv())
check(e.loaded and e.owner == MIXXX and abs(e.position(m.c.t) - pos[0]) < 0.05, "weiter in Mixxx: Show setzt an der richtigen Stelle ein")

# Knopf SHOW: fuer dieses Lied Schluss, beim naechsten wieder
sh.command({"auto": "toggle"})
m.run(3.0, adv())
check(not e.loaded and sh.snapshot()["mode"] == "auto", "Knopf SHOW: Show bleibt fuer dieses Lied aus")
m.plan(1, "Fremd", 240.0)
m.run(1.0, adv())
m.plan(1, "Künstler - Lied", 240.0)
m.run(1.5, adv())
check(e.loaded, "dasselbe Lied spaeter wieder: Show startet")

# Mischen: das lautere Deck entscheidet, es laeuft genau eine Show
make(mgr, "Zweite", title="Zwei - Lied", dur=200.0, v=50)
m.plan(2, "Zwei - Lied", 200.0)
pos2 = [30.0]
vol = {"a": 1.0, "b": 0.0}
starts = []


def mix():
    pos[0] += DT
    pos2[0] += DT
    vol["a"] = max(0.0, vol["a"] - DT / 8.0)
    vol["b"] = min(1.0, vol["b"] + DT / 8.0)
    m.deck(1, pos[0], vo=vol["a"])
    m.deck(2, pos2[0], du=200.0, vo=vol["b"])
    if not starts or starts[-1] != e.doc_name:
        starts.append(e.doc_name)


m.run(3.0, mix)
check(e.doc_name == "Mit Titel", "beim Mischen: zuerst noch das laute Deck")
m.run(7.0, mix)
check(e.doc_name == "Zweite" and e.loaded and starts == ["Mit Titel", "Zweite"], f"Show wechselt genau einmal {starts}")
check(abs(e.position(m.c.t) - pos2[0]) < 0.05, "neue Show an der richtigen Stelle")

# Nicht dazwischenfunken
link, rig, sh, mgr = setup(1.0)
make(mgr, "Hand")
make(mgr, "Mx", title="Mx - Lied", dur=240.0)
e = mgr.engine
m = Rig(link, sh, mgr)
e.load(mgr.store.load("Hand"))
e.play(m.c.t, 0.0, True, "browser")
m.plan(1, "Mx - Lied", 240.0)
m.run(2.0, lambda: m.deck(1, 5.0))
check(e.doc_name == "Hand" and e.owner == "browser", "Show aus dem Browser mit Licht an hat Vorrang")
mgr.op({"op": "live", "name": "Andere", "doc": mgr.store.load("Mx")})
check(e.doc_name == "Hand", "Editor einer anderen Show funkt nicht dazwischen")
e.stop(m.c.t)
# Editor angehalten oder mit Licht aus: darf Mixxx nicht aufhalten (Fehlerbericht)
for playing, light in ((False, False), (True, False), (False, True)):
    link, rig, sh, mgr = setup(1.0)
    make(mgr, "Editor")
    make(mgr, "Mx", title="Mx - Lied", dur=240.0)
    e = mgr.engine
    m = Rig(link, sh, mgr)
    e.load(mgr.store.load("Editor"))
    e.play(m.c.t, 15.0, light, "browser")
    if not playing:
        e.pause(m.c.t)
    m.plan(1, "Mx - Lied", 240.0)
    m.run(1.5, lambda: m.deck(1, 5.0))
    check(e.doc_name == "Mx" and e.owner == MIXXX and e.active() and sh.snapshot()["mode"] == "show",
          f"Editor ({'laeuft' if playing else 'Pause'}, Licht {'an' if light else 'aus'}): Mixxx uebernimmt")
    check(not e.report("browser", 15.0, True, 0.0, m.c.t), "Meldungen des Editors zaehlen dann nicht mehr")
# Schalter
link, rig, sh, mgr = setup(0.0)
make(mgr, "Mx", title="Mx - Lied", dur=240.0)
e = mgr.engine
m = Rig(link, sh, mgr)
m.plan(1, "Mx - Lied", 240.0)
m.run(2.0, lambda: m.deck(1, 5.0))
check(not e.loaded, "Schalter aus (Standard): nichts startet von allein")
check(sh.cfg.info and [i for g in sh.cfg.info() for i in g["items"] if i["key"] == "sm_mixxx_auto"][0]["default"] == 0.0, "Standard ist aus")
sh.cfg.set("sm_mixxx_auto", 1.0)
m.run(1.0, lambda: m.deck(1, 5.0))
check(e.loaded, "Schalter an: startet")
sh.cfg.set("sm_mixxx_auto", 0.0)
m.run(0.5, lambda: m.deck(1, 5.0))
check(not e.loaded, "Schalter aus: Show endet")
# Abgeschaltete Show, zu kurze Show
link, rig, sh, mgr = setup(1.0)
make(mgr, "Aus", title="Aus - Lied", dur=240.0, on=False)
make(mgr, "Kurz", title="Kurz - Lied", dur=240.0, duration=30.0)
e = mgr.engine
m = Rig(link, sh, mgr)
m.plan(1, "Aus - Lied", 240.0)
m.run(1.5, lambda: m.deck(1, 5.0))
check(not e.loaded, "Haken 'startet aus Mixxx' aus: bleibt aus")
m.plan(1, "Kurz - Lied", 240.0)
m.run(1.5, lambda: m.deck(1, 100.0))
check(not e.loaded, "Stelle hinter dem Ende der Show: startet nicht")
pos3 = [29.0]


def adv3():
    pos3[0] += DT
    m.deck(1, pos3[0])


m.run(4.0, adv3)
check(not e.loaded and sh.snapshot()["mode"] != "show", "Show kuerzer als das Lied: endet, AUTO uebernimmt, kein neuer Start")
# Sperren gelten auch hier
link, rig, sh, mgr = setup(1.0)
doc = mgr.store.create("Boese")
doc.update(duration=240.0, tracks=[track("laser", "power", [(0, 255)]), track("hazer", "pump", [(0, 255)]), track("vega", "dimmer", [(0, 200)])])
doc["mixxx"] = {"title": "B - L", "dur": 240.0}
mgr.store.save("Boese", doc)
mgr.index_dirty = True
e = mgr.engine
m = Rig(link, sh, mgr)
m.plan(1, "B - L", 240.0)
m.run(1.5, lambda: m.deck(1, 5.0))
check(e.active() and ch(rig, "vega", "dimmer") == 200, "Show laeuft")
check(ch(rig, "laser", "power") == 0 and ch(rig, "hazer", "pump") == 0, "Laser und Hazer bleiben auch aus Mixxx aus")
check(tl.normalize(doc)["mixxx"]["title"] == "B - L", "Zuordnung bleibt in der Showdatei")

# Auswahl im Editor
link, rig, sh, mgr = setup(0.0)
link.feed({"type": "lib", "i": 1, "n": 2, "t": [["Bär - Zwei", 100.0]]}, 1.0)
link.feed({"type": "lib", "i": 0, "n": 2, "t": [["Aha - Eins", 90.0], "kaputt"]}, 1.0)
link.feed({"type": "plan", "d": 1, "key": "k", "title": "Im Deck", "du": 50.0, "ev": []}, 1.0)
r = mgr.mixxx_songs()
check(r["total"] == 2 and [t["title"] for t in r["tracks"]] == ["Aha - Eins", "Bär - Zwei"] and r["decks"][0]["title"] == "Im Deck", "Liste aus der Bibliothek und den Decks")
check([t["title"] for t in mgr.mixxx_songs("bar")["tracks"]] == [] and [t["title"] for t in mgr.mixxx_songs("BÄR")["tracks"]] == ["Bär - Zwei"], "Suche")
rig2, sh2 = build()
check(ShowManager(sh2, tempfile.mkdtemp(dir=tmp)).mixxx_songs()["connected"] is False, "ohne Mixxx-Empfaenger: leere Liste")

# ---- Abschnitte und Cues in der Timeline ----------------------------------------------------------------------------
link, rig, sh, mgr = setup()
sh.cfg.set("mixxx_shift_s", 0.5)
make(mgr, "Ohne", title="Andere - Sache", dur=100.0)
check(mgr.op({"op": "marks", "name": "Ohne"}) == {"marks": None, "warn": False}, "kein Lied im Deck: nichts einzuzeichnen")
SE = [["intro", 0.0, 20.0], ["main", 20.0, 90.0], ["quatsch", 90.0, 95.0], ["outro", 95.0, 90.0]]
plan = {"type": "plan", "d": 1, "key": "k", "title": "Lied - Eins", "du": 100.0, "ev": [], "se": SE, "cu": [50.0, 20.0, "x", -1], "fp": ""}
link.feed(dict(plan), 1.0)
check(mgr.op({"op": "marks", "name": "Ohne"})["marks"] is None, "anderes Lied im Deck: keine fremden Cues")
make(mgr, "Titel", title="Lied - Eins", dur=100.5)
before = mgr.store.load("Titel")["tracks"]
r = mgr.op({"op": "marks", "name": "Titel"})
check(r["marks"]["se"] == [["intro", 0.0, 20.0], ["main", 20.0, 90.0]], "Abschnitte ohne Unsinn und ohne den Licht-Versatz von Mixxx")
check(r["marks"]["cu"] == [20.0, 50.0], "Cues sortiert, Unsinn verworfen")
saved = mgr.store.load("Titel")
check(saved["marks"] == r["marks"] and saved["tracks"] == before, "bleiben in der Showdatei, sonst aendert sich nichts")
link.feed({"type": "plan", "d": 1, "key": ""}, 2.0)
check(mgr.op({"op": "marks", "name": "Titel"})["marks"] == r["marks"], "Lied ausgeworfen: Einzeichnungen bleiben, auch ohne Mixxx")
link.feed(dict(plan, se=[], cu=[]), 3.0)
check(mgr.op({"op": "marks", "name": "Titel"})["marks"]["se"] == r["marks"]["se"], "Analyse noch nicht fertig: Vorhandenes bleibt")
link.feed(dict(plan, cu=[33.0]), 4.0)
check(mgr.op({"op": "marks", "name": "Titel"})["marks"]["cu"] == [33.0], "neue Cues aus dem Deck ersetzen die alten")
a1, a2 = os.path.join(tmp, "m1.mp3"), os.path.join(tmp, "m2.mp3")
mp3(a1, b"A" * 5000)
mp3(a2, b"B" * 5000)
make(mgr, "Datei", fp_from=a1)
link.feed(dict(plan, title="Ganz - Anders", fp=audio_fingerprint(a1)), 5.0)
r = mgr.op({"op": "marks", "name": "Datei"})
check(r["marks"]["cu"] == [20.0, 50.0] and r["warn"] is False, "Fund ueber die MP3, ohne gewaehlten Titel")
shutil.copy(a2, mgr.store.path("Datei", "audio.mp3"))
check(mgr.op({"op": "marks", "name": "Datei"})["warn"] is True, "andere MP3 als die Quelle der Cues: Warnung")
d = mgr.store.load("Datei")
d2 = tl.normalize(dict(d, marks={"se": "kaputt", "cu": [1, 2]}))
check(d2["marks"]["se"] == [] and d2["marks"]["cu"] == [1.0, 2.0], "kaputte Datei wird bereinigt")
check("marks" not in tl.normalize(mgr.store.load("Ohne")), "alte Shows ohne Einzeichnungen bleiben unveraendert")
from showman.timeline import MARK_SECTIONS                       # noqa: E402
from mixxx_link import SECTIONS                                  # noqa: E402
check(MARK_SECTIONS == SECTIONS, "dieselben Abschnitte wie im Mixxx-Empfaenger")
shutil.rmtree(tmp, ignore_errors=True)
finish("test_showmanager_mixxx")
