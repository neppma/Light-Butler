"""Knoepfe im Bedienbereich zweisprachig (Einstellung ui_lang: Deutsch oder English, Standard English).
Feste Reihenfolge; die interne Kennung (fuer den APC mini, midimap.json und gespeicherte Szenen) bleibt unveraendert."""
import json
import re

from _common import build, check, finish

import settings
import webpanel
from midi_ctl import MIX_ORDER
from scenes import MIX_BUTTONS
from scenes import MOVES as SCENE_MOVES

# Licht-Mix
check([en for _, _, en in webpanel.MIX_PANEL] == ["Disco", "Carousel", "Sparkle", "Static", "Chase-Out", "Chase-In", "Scanner", "Rainbow"],
      "Licht-Mix englisch: Beschriftung und Reihenfolge wie gewuenscht")
check([de for _, de, _ in webpanel.MIX_PANEL] == ["Discokugel", "Karussell", "Sternenhimmel", "STOP", "nach außen", "nach innen", "Scanner", "Regenbogen"],
      "Licht-Mix deutsch: die bisherigen Namen")
check(sorted(k for k, *_ in webpanel.MIX_PANEL) == sorted(MIX_BUTTONS), "jeder Licht-Mix hat genau einen Knopf")
check(set(MIX_ORDER) <= set(MIX_BUTTONS), "APC-mini-Belegung nutzt weiter die internen Kennungen")

# Bewegung
check([en for _, _, en in webpanel.MOVES] == ["Float", "Center", "Random", "Sweep", "Circle", "Tilt", "Pan", "Swim"],
      "Bewegung englisch: Beschriftung und Reihenfolge wie gewuenscht")
check([de for _, de, _ in webpanel.MOVES] == ["Ente", "Stop", "Zufall", "Besen", "Kreis", "Rauf-Runter", "Rechts-Links", "Schwimmer"],
      "Bewegung deutsch: die bisherigen Namen")
check(all(k in SCENE_MOVES for k, *_ in webpanel.MOVES), "Bewegung: interne Kennungen unveraendert")

# Geschwindigkeit, Farben, Ziel
check([(de, en) for _, de, en in webpanel.SPEEDS] == [("Auto", "Auto"), ("Langsam", "Low"), ("Mittel", "Med"), ("Schnell", "Hot")],
      "Geschwindigkeit DE/EN, mit Auto")
check([en for _, _, en in webpanel.COLORS] == ["Auto", "Red", "Orange", "Yellow", "Green", "Cyan", "Blue", "Violet", "Magenta", "White", "UV"],
      "Farben englisch")
check([de for _, de, _ in webpanel.COLORS] == ["Auto", "Rot", "Orange", "Gelb", "Grün", "Cyan", "Blau", "Violett", "Magenta", "Weiß", "UV"],
      "Farben deutsch")
check(len(webpanel.AIMS) == 5 and all(len(a) == 3 for a in webpanel.AIMS), "Ziel-Knoepfe DE/EN")

# feste Texte
import texts
T = texts.TOP
check(T["sun"] == ("SONNEN|BRILLE", "BLINDER") and T["fog"] == ("NEBEL", "SMOKE"), "BLINDER/SONNENBRILLE und SMOKE/NEBEL")
check(all(de and en for _, _, de, en in texts.catalog()), "jeder Text hat Deutsch und Englisch")

# Einstellung und Status
d = {p.key: p for p in settings.DEFS}
check("ui_lang" in d and d["ui_lang"].default == 1.0 and d["ui_lang"].unit == "switch:Deutsch|English",
      "Einstellung Sprache: Deutsch oder English, Standard English")
rig, sh = build()
check(sh.snapshot()["lang"] == "en", "Status meldet Sprache en")
sh.cfg.set("ui_lang", 0.0)
check(sh.snapshot()["lang"] == "de", "nach Umstellen: Sprache de")

# Panel
page = webpanel.make_page()
m = re.search(r"const MIXP=(\[.*?\]\]),", page)
check(m is not None and json.loads(m.group(1)) == [list(x) for x in webpanel.MIX_PANEL], "Panel bekommt Kennung und beide Beschriftungen")
check("setLang(S.lang)" in page and "function tr(k)" in page and "function tx(" not in page and "mk('speed',SPEEDS" in page and "function drawAims()" in page, "Panel schaltet die Sprache nach dem Status um")
for k in ("h_speed", "h_mix", "h_move", "h_color", "h_aim", "sun", "bz_label", "color_hint", "auto", "black", "freeze",
          "cat_licht", "h_fixtures", "gl_btn", "m_backup", "m_midi", "m_audio"):
    check(f'data-tx="{k}"' in page, f"Text {k} im Panel umschaltbar")

finish("test_mix_namen")
