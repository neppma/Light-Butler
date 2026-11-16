"""Panel, Zeile Mixxx: "Deck 1"/"Deck 2" statt nur der Nummer, hinter dem Titel die verbleibende Spielzeit (-m:ss),
bei Pitch umgerechnet auf die echte Zeit."""
from _common import build, check, finish

import webpanel

rig, sh = build()
base = {"connected": True, "deck": 2, "title": "Song", "plan": True, "want": "normal", "next": [], "pos": 60.0,
        "dur": 245.0, "rate": 1.0, "status": "", "bpm": 128.0}
sh.mx = dict(base)
check(sh._mx_public()["left"] == 185.0, "Restzeit 185 s (3:05)")
sh.mx = dict(base, rate=1.25)
check(sh._mx_public()["left"] == 148.0, "schneller abgespielt (Pitch +25 %): 148 s echte Zeit")
sh.mx = dict(base, pos=250.0)
check(sh._mx_public()["left"] == 0.0, "am Ende: 0, nie negativ")
sh.mx = dict(base, dur=0.0, deck=None)
check(sh._mx_public()["left"] is None, "kein Lied: keine Restzeit")

page = webpanel.make_page()
check("'<b>'+(ad?'Auto-DJ':'Mixxx')+'</b> '+tr('mx_deck')+' '+(ad?(m.deck===11?'A':'B'):m.deck)" in page, "Panel: Deck 1 / Deck 2 (Auto-DJ: A / B)")
check("class=\"mxleft\"" in page and "padStart(2,'0')" in page and "mid,lt+(right?' '+right:''))" in page, "Panel: Restzeit -m:ss rechts, immer sichtbar")
finish("test_mixxx_restzeit")
