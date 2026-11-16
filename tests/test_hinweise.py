"""Einstellung Panel -> Hinweistexte im Panel anzeigen (Ja/Nein): bei Nein verschwinden die grauen Hinweiszeilen."""
from _common import build, check, finish

import webpanel

rig, sh = build()
check(sh.cfg["ui_hints"] == 1.0 and sh.snapshot()["ui_hints"] is True, "Standard: Hinweise sichtbar")
sh.cfg.set("ui_hints", 0.0)
check(sh.snapshot()["ui_hints"] is False, "Nein: Status meldet es dem Panel")
p = webpanel.make_page()
check("document.body.classList.toggle('nohints',S.ui_hints===false)" in p, "Panel schaltet die Hinweise um")
check('body.nohints [data-tx$="_hint"],body.nohints .scnote,body.nohints .hint{display:none!important}' in p,
      "versteckt alle Hinweiszeilen (Schluessel ..._hint und Bearbeiten-Hinweise)")
hints = [k for k in ("eb_hint", "tempo_hint", "color_hint", "sys_ola_hint", "sys_wled_hint") if f'data-tx="{k}"' in p]
check(len(hints) == 5, "die grauen Zeilen tragen Schluessel auf _hint")
import settings
check(next(x for x in settings.DEFS if x.key == "ui_hints").group == "Panel", "Schalter steht in der Gruppe Panel")
finish("test_hinweise")
