"""Showmanager zeigt, ob und wo gerade Spur-Kurven gerechnet werden, und der Editor blendet fertige Kurven von selbst ein
(Wunsch von Markus, 06.11.2026)."""
import base64
import os
import tempfile
import time
import types

from _common import ROOT, check, finish

from showman import api
from showman import stems_bulk as sb
from showman import store as st

tmp = tempfile.mkdtemp(prefix="s2l_anz_")
store = st.ShowStore(os.path.join(tmp, "shows"))
store.create("Lied")
with open(store.path("Lied", "audio.mp3"), "wb") as f:
    f.write(b"\xff\xfb\x90\x00" + bytes(range(256)) * 400)
fp = store._audio_fp("Lied")


def data(dur=10.0):
    c = base64.b64encode(bytes(int(dur * st.STEM_RATE))).decode()
    return {"v": 1, "rate": st.STEM_RATE, "db_min": -60, "duration": dur, "offset_ms": 0.0, "corr": None, "fp": fp, "model": "htdemucs",
            "created": "x", "curves": {k: c for k in st.STEM_CURVES}}


lst = {s["name"]: s for s in store.list()}
check(lst["Lied"]["stems"] is False, "Showliste: noch keine Kurven")

LIB = [{"title": "Lied", "dur": 200.0, "path": "/m/lied.mp3"}]
bulk = sb.StemBulk(store, lambda: LIB, lambda: "http://mac:9025")
mgr = types.SimpleNamespace(store=store, stem_claims={}, CLAIM_S=api.ShowManager.CLAIM_S, stem_bulk=bulk)
busy = lambda f: api.ShowManager.stems_busy(mgr, f)            # noqa: E731
act = lambda: api.ShowManager.stems_activity(mgr)              # noqa: E731
check(busy(fp) == "" and act()["work"] == [], "niemand rechnet")
api.ShowManager.stems_claim(mgr, "Lied", "MAC")
check(busy(fp) == "MAC" and act()["work"][0] == {"who": "MAC", "title": "Lied", "kind": "show", "since_s": 0}, "Show wird gerechnet: Rechner und Show")
api.ShowManager.stems_claim(mgr, "Lied", "MAC", False)
bulk.set(True)
bulk.next("PC")
check(busy(fp) == "" and act()["work"][0]["kind"] == "vorab", "Vorab-Lauf: angezeigt, die Show ist erst betroffen, wenn der PC die MP3 kennt")
bulk.note_fp("PC", "/m/lied.mp3", fp)
check(busy(fp) == "PC", "PC hat die MP3 der Show geholt: die Show zeigt, dass er rechnet")
check(act()["bulk"]["on"] is True and act()["bulk"]["total"] == 1, "Stand des Vorab-Laufs dabei")
bulk.done("PC", "/m/lied.mp3", fp, data())
check(busy(fp) == "" and {s["name"]: s for s in store.list()}["Lied"]["stems"] is True, "fertig: niemand rechnet, Showliste zeigt Kurven")
mgr.stem_claims[fp] = ("MAC", time.time() - api.ShowManager.CLAIM_S - 1, "Lied")
check(busy(fp) == "" and act()["work"] == [], "alte Anmeldung (abgestuerzter Rechner) zaehlt nicht")

asrc = open(os.path.join(ROOT, "pi", "showman", "api.py"), encoding="utf-8").read()
check('state["busy"] = mgr.stems_busy(state.get("fp") or "")' in asrc and 'op == "stems_activity"' in asrc, "Pi liefert busy und die Uebersicht")

sm = os.path.join(ROOT, "pi", "static", "sm")
ejs = open(os.path.join(sm, "editor.js"), encoding="utf-8").read()
ehtml = open(os.path.join(sm, "editor.html"), encoding="utf-8").read()
check('<span id="stemst"' in ehtml and "setInterval(pollStems, 15000)" in ejs, "Editor fragt alle 15 s nach")
check("if (s.current && (stemsCreated == null || (s.created || '') !== stemsCreated))" in ejs and "await loadStems();" in ejs,
      "Editor laedt fertige oder neuere Kurven von selbst")
check("rechnet …" in ejs and "MP3 zu lang" in ejs and "noch keine" in ejs, "Hinweis: rechnet, zu lang, noch keine")
check("tl.setStems(null); stemsCreated = null;" in ejs, "andere MP3: alte Kurven verschwinden")
pjs = open(os.path.join(sm, "play.js"), encoding="utf-8").read()
phtml = open(os.path.join(sm, "play.html"), encoding="utf-8").read()
check('id="stemact"' in phtml and "setInterval(pollStemAct, 10000)" in pjs and "SM.cmd('stems_activity')" in pjs, "Seite Shows: Zeile mit dem Stand, alle 10 s")
check("Kurven werden gerechnet" in pjs and "Kurven ✓" in pjs and "stemNote(s)" in pjs, "Liste: je Show Kurven da oder in Arbeit")
finish("test_stems_anzeige")
