"""Seite "APC mini · Belegung" (/apc): das ganze Board mit aktueller Belegung, LED-Farben wie am Geraet, allen 8
Scene-Launch-Tasten (frei = "frei"), der unteren Reihe, SHIFT und 9 Fadern mit Wert. Gedrueckte Tasten blitzen auf."""
import os
import subprocess
import tempfile

from _common import build, check, finish, Clock

import apc_view
import webpanel
from midi_ctl import CH_PULSE, PALETTE, MidiController, pad_note

rig, sh = build(seed=3, pilot=True)
Clock(sh).run(1)
st = apc_view.state(sh)
p1 = st["pages"]["pads1"]
check(len(p1) == 8 and all(len(r) == 8 for r in p1), "8 x 8 Pads")
check([c["act"]["cmd"] for c in p1[0]] == ["auto", "blitz", "wow", "allbright", "freeze", "blackout", "fog", "beat"],
      "Reihe 1 wie im Panel")
check(p1[3][1]["nr"] == 2 and p1[3][1]["scene"] == sh.scene_defs[1].name, "Szenen-Pads mit Nummer und Name")
check(p1[0][0]["color"] == apc_view.CSS["gruen"], "AUTO aktiv: gruen wie am Geraet")
check(p1[0][1]["color"] == apc_view.CSS["gelb"], "Strobe nicht aktiv: gelb")
check(len(st["right"]) == 8 and st["right"][0]["act"] == {"speed": "slow"} and st["right"][5]["act"] == {"cmd": "tap"},
      "alle 8 Scene-Launch-Tasten")
check(len(st["bottom"]) == 8 and st["bottom"][0]["act"] == {"aim": "bank"}, "untere Reihe: Ziele usw.")
check(len(st["faders"]) == 9 and st["faders"][8]["act"] == {"fader": "master"} and st["faders"][8]["value"] == round(sh.master, 2),
      "9 Fader, der letzte ist Master mit Wert")
p2 = st["pages"]["pads2"]
check(p2[0][1]["act"] == {"color": "rot"} and p2[0][1]["color"] == apc_view.CSS["rot"], "Farbseite in echten Farben")
check(not st["connected"] and not st["midi_running"], "ohne Controller: Belegung trotzdem sichtbar, 'nicht verbunden'")

# gedrueckte Taste: Zaehler fuer das Aufblitzen
m = MidiController(sh, map_path=None)
m._raw = lambda *a: None
sh.midi = m


class Msg:
    type, note, velocity = "note_on", pad_note(1, 0), 127


m.handle(Msg())
st = apc_view.state(sh)
check(st["last"][-1]["seq"] == 1 and st["last"][-1]["what"] == f"Note {pad_note(1, 0)}", "gedrueckte Taste mit Zaehler")
check(apc_view.css_of(PALETTE["blau"]) == apc_view.CSS["blau"] and apc_view.css_of(0) is None, "LED-Farbe -> Browserfarbe")
check(apc_view.LEVEL[CH_PULSE] == 1.0, "pulsierende Pads voll hell")

p = webpanel.make_page()
check('<a href="/apc"' in p and '<a class="seclink" href="/apc">' in p, "Links im MIDI-Bereich und auf der Einstellungsseite")
check("body.vapc>*:not(#apcsec)" in p and '<body class="vapc">' in webpanel.apc_page(), "eigene Seite /apc")
check("apcFlash('n'+m[1])" in p and "apcFlash('cc'+m[1])" in p, "gedrueckte Pads/Tasten und Fader blitzen auf")
check(".abtn,#apcshift{border-radius:3px" in p, "Tasten quadratisch (nicht rund)")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_apc_seite")
