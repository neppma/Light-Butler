"""Uebersetzungstabelle: alle Texte des Bedienbereichs (Knoepfe, Bereiche, Menues, Einstellungsgruppen) auf Deutsch
und Englisch aenderbar. Eigene Texte stehen in texts.json, nur was vom Standard abweicht. Anzeige nur als Text."""
import json
import os
import shutil
import tempfile

from _common import build, check, finish

import settings
import texts
import webpanel

cat = texts.catalog()
keys = [k for k, *_ in cat]
check(len(keys) == len(set(keys)), "jeder Text-Schluessel kommt genau einmal vor")
for need in ("mix:Scanner", "move:duck", "color:rot", "speed:slow", "aim:bank", "sun", "fog", "h_speed", "h_scenes",
             "m_sys", "m_tempo", "m_audio"):
    check(need in keys, f"Text {need} in der Tabelle")
for need in ("ev_idle", "ev_normal", "ev_gap", "st_silence", "st_tier", "mode_scene", "dim", "bpm_manual",
             "mx_off", "mx_noconn", "mx_nodeck", "mx_unknown", "mx_mismatch", "mx_plan", "mx_noevent", "w_restart",
             "mood:euphorisch", "mood:intensiv", "mood:froh", "mood:ruhig", "key_major", "key_minor"):
    check(need in keys, f"Statuszeile: Text {need} in der Tabelle")
import show as _sw
check(all(f"mood:{q}" in keys for q in _sw.QUADRANTS), "jede Stimmung hat einen uebersetzbaren Namen")
check(dict((k, (de, en)) for k, _, de, en in cat)["mx_nodeck"] == ("kein Deck hörbar", "no deck audible"), "kein Deck hoerbar / no deck audible")

# Mixxx-Meldungen tragen einen Schluessel fuer die Uebersetzung
from mixxx_link import MixxxLink
ln = MixxxLink(port=19997)
st = ln.status(1000.0, build()[1].cfg)
check(st["status_key"] in ("mx_noconn", "mx_nodeck") and st["status_key"] in keys, f"Mixxx-Status mit Schluessel ({st['status_key']})")

groups = list(dict.fromkeys(p.group for p in settings.DEFS))
check(all(f"grp:{g}" in keys for g in groups), "jede Einstellungsgruppe hat einen uebersetzbaren Namen")
check(dict((k, (de, en)) for k, _, de, en in cat)["color:gelb"] == ("Gelb", "Yellow"), "Standard: Gelb / Yellow")

# Speicher
tmp = tempfile.mkdtemp(prefix="s2l_tx_")
path = os.path.join(tmp, "texts.json")
st = texts.TextStore(path)
check(not os.path.exists(path) and st.merged()["mix:Scanner"] == ["Scanner", "Scanner"], "ohne texts.json gelten die Standardtexte")
st.set("mix:Scanner", en="Scanner light")
check(st.merged()["mix:Scanner"] == ["Scanner", "Scanner light"], "englischen Text geaendert, deutscher bleibt")
check(json.load(open(path)) == {"mix:Scanner": {"en": "Scanner light"}}, "texts.json enthaelt nur die Abweichung")
st.set("grp:Laser", de="Laser-Show", en="Laser show")
st2 = texts.TextStore(path)
check(st2.merged()["grp:Laser"] == ["Laser-Show", "Laser show"], "nach Neustart wieder geladen")
st2.set("mix:Scanner", en="Scanner")
check("mix:Scanner" not in json.load(open(path)), "zurueck auf den Standardtext = Eintrag weg")
for bad, why in ((("gibtsnicht", "x", None), "unbekannter Schluessel"), (("fog", "", None), "leerer Text"),
                 (("fog", "x" * 301, None), "zu lang")):
    try:
        st2.set(*bad)
        check(False, f"{why} abgelehnt")
    except ValueError:
        check(True, f"{why} abgelehnt")
st2.set("fog", de="NE\nBEL\t ")
check(st2.merged()["fog"][0] == "NE BEL", "Zeilenumbrueche und Tabs werden zu Leerzeichen (Umbruch nur mit |)")
st2.reset()
check(json.load(open(path)) == {} and st2.merged()["grp:Laser"] == ["Laser", "Laser"], "alle zuruecksetzen")
with open(path, "w") as f:
    f.write("{kaputt")
check(texts.TextStore(path).merged()["fog"] == ["NEBEL", "SMOKE"], "defekte texts.json: Standardtexte, kein Absturz")
shutil.rmtree(tmp, ignore_errors=True)

# Show: Befehle und Versionsnummer fuer die Panels
rig, sh = build()
r0 = sh.snapshot()["texts_rev"]
sh.command({"text_set": {"key": "move:duck", "de": "Entchen"}})
check(sh.snapshot()["texts_rev"] == r0 + 1 and sh.texts.merged()["move:duck"] == ["Entchen", "Float"], "Befehl text_set")
sh.command({"text_reset": "move:duck"})
check(sh.texts.merged()["move:duck"] == ["Ente", "Float"], "Befehl text_reset")
sh.command({"text_set": {"key": "fog", "en": "<img src=x onerror=alert(1)>"}})
check(sh.texts.merged()["fog"][1] == "<img src=x onerror=alert(1)>", "Text wird gespeichert wie eingegeben")
sh.command({"text_reset": "all"})

# Panel: Anzeige nur als Text, Tabelle in Einstellungen -> Panel
page = webpanel.make_page()
check("function tr(k){const t=TXT[k];return esc(" in page, "Texte werden vor der Anzeige maskiert (kein HTML)")
check("g.group==='Panel'" in page and "function renderTxEd(T)" in page, "Uebersetzungstabelle in der Gruppe Panel")
check("fetch('/api/texts')" in page and "S.texts_rev!==TXREV" in page, "alle Panels laden geaenderte Texte sofort")
for frag in ("tr('ev_idle')", "tr('st_silence')", "tr('st_tier')", 'data-tx="dim"', "tr('mx_off')", "m.status_key?tr(m.status_key)",
             "tr('mx_noevent')", "tr('w_restart')", "tr('bpm_manual')"):
    check(frag in page, f"Panel nutzt {frag}")
import re
used = (set(re.findall(r'data-tx="([a-z_0-9:]+)"', page)) | set(re.findall(r"tr\('([a-z_0-9:]+)'\)", page))
        | set(re.findall(r"TXT\.([a-z_0-9]+)\[", page)))
check(used and used <= set(keys), f"jeder im Panel benutzte Text steht in der Tabelle ({sorted(used - set(keys))})")
check("dataset.tx=EDIT?'done':'edit'" in page and "dataset.tx=FXEDIT?'done':'edit'" in page, "Bearbeiten/Fertig bei Szenen und Fixtures uebersetzbar")
for k in ("sc_reset", "set_all", "set_note", "fx_export", "aim_title", "save", "tempo_hint", "sys_ola",
          "off", "on", "connecting", "link_sends"):
    check(k in used, f"Panel nutzt den Text {k}")
check('data-tx="sc_reset">\'+tr(\'sc_reset\')' in page and 'data-tx="set_all">Alle auf Standard' in page,
      "Szenen- und Einstellungs-Knopf haben einen Text-Schluessel")
for fixed in ("Aenderungen wirken sofort", "'Fertig'",
              "' BPM fest", "'Automatisch: ", "' von '+R.length", "'nicht verfügbar: '"):
    check(fixed not in page, f"kein fester Text mehr: {fixed}")
# Das Merkmal fuer Uebersetzungen ist eindeutig: setLang ueberschreibt nur Elemente mit data-tk (sonst wuerden
# Regler, Eingabefelder und Auswahllisten mit data-k beim Laden der Texte geleert, wie im Bereich Haus passiert)
check("document.querySelectorAll('[data-tk]').forEach(b=>b.innerHTML=tr(b.dataset.tk))" in page
      and "querySelectorAll('[data-k]').forEach(b=>b.innerHTML" not in page, "Uebersetzung nur fuer Elemente mit data-tk")
check(page.count("data-tk") + page.count("dataset.tk") >= 4 and 'data-tk="\'+esc(x.key)' not in page,
      "Regler im Bereich Haus haben kein Uebersetzungs-Merkmal")
check("'keine Musik'" not in page and ">Stille<" not in page, "keine festen deutschen Statustexte mehr")

finish("test_texte")
