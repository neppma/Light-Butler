"""BPM-Anzeige: oben im Kopf als ganze Zahl (Wunsch Nutzer 01.11.2026), im Tempo-Fenster das erkannte Tempo mit einer Nachkommastelle;
feste Breite, damit die Anzeige nicht springt. Der Status liefert weiter 2 Nachkommastellen (das Licht rechnet genau)."""
from _common import build, Clock, check, finish

import webpanel

page = webpanel.make_page()
check("String(Math.round(+S.beat_bpm))" in page, "Kopf zeigt BPM als ganze Zahl")
check("(+S.beat_bpm).toFixed(1)" in page, "Tempo-Fenster zeigt das erkannte Tempo mit einer Nachkommastelle")
check("toFixed(S.beat_bpm%1" not in page, "keine wechselnde Zahl der Nachkommastellen mehr")
check("#bpmtxt b{display:inline-block;width:3ch;text-align:right" in page, "BPM-Zahl hat feste Breite (3 Ziffern)")

rig, sh = build()
clk = Clock(sh)
clk.run(20)
bpm = sh.snapshot().get("beat_bpm")
check(bpm is not None, "Snapshot liefert beat_bpm")
if bpm is not None:
    check(round(bpm, 2) == bpm, f"beat_bpm hat hoechstens 2 Nachkommastellen ({bpm})")
    check(bpm == 0 or bpm == round(sh._bpm_live(), 2), "beat_bpm wird auf 2 Stellen gerundet, nicht auf 1")

finish("test_bpm_anzeige")
