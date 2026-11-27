"""Gleiche Kopfleiste auf allen Unterseiten (static/sm/nav.js): zurueck eine Ebene hoeher, Panel, Menue mit den Hauptseiten."""
import os
import re
import subprocess

from _common import PI, check, finish

import texts
import webpanel

SM = os.path.join(PI, "static", "sm")
rd = lambda n: open(os.path.join(SM, n), encoding="utf-8").read()
nav = rd("nav.js")

# jede Seite: (Name, HTML, zurueck, Menuepunkt, Titel-Schluessel)
PAGES = [("Einstellungen", webpanel.settings_page(), "/", "settings", "h_setpage"),
         ("Zustand", webpanel.health_page(), "/", "health", "hl_title"),
         ("Statistik", webpanel.stats_page(), "/", "stats", "stat_title"),
         ("Fixtures", webpanel.fixtures_page(), "/settings", "settings", "h_fixtures"),
         ("APC", webpanel.apc_page(), "/settings", "settings", "apc_title"),
         ("Lumi", webpanel.lumi_page(), "/settings", "settings", "lumi_title"),
         ("DMX-Monitor", webpanel.dmx_page(), "/settings", "settings", "sys_dmxmon"),
         ("Hilfe", webpanel.help_page(), "/", "help", "h_help"),
         ("Showmanager", rd("play.html"), "/", "shows", "h_showman"),
         ("Show-Editor", rd("editor.html"), "/shows", "shows", "h_editor"),
         ("Musik", rd("music.html"), "/", "musik", "h_music"),
         ("Tag-Vorschlaege", rd("autotag.html"), "/musik", "musik", "h_autotag"),
         ("Doppelte", rd("dupes.html"), "/musik", "musik", "h_dupes"),
         ("Titel bereinigen", rd("titles.html"), "/musik", "musik", "h_titles"),
         ("Dateien pruefen", rd("check.html"), "/musik", "musik", "h_check"),
         ("Datenpflege", rd("care.html"), "/musik", "musik", "h_care"),
         ("Auto-DJ", rd("autodj.html"), "/musik", "autodj", "h_autodj"),
         ("Raumplan", rd("room.html"), "/", "raum", "h_room"),
         ("DMX-Debugger", rd("debug.html"), "/settings", "settings", "h_dmxdebug")]
for name, html, back, cur, tk in PAGES:
    check(f'class="s2lnav" data-back="{back}" data-cur="{cur}" data-title="{tk}"' in html, f"{name}: Kopfleiste, zurueck nach {back}")
    check('<script src="/static/sm/nav.js"></script>' in html, f"{name}: laedt nav.js")
    check("&larr; Panel" not in html and "<button>Panel</button>" not in html, f"{name}: keine alten Panel-Links mehr")

check(not re.search(r'class="s2lnav"[^>]*data-tk=', webpanel.make_page() + "".join(h for _, h, *_ in PAGES)), "Kopfleiste nutzt nicht data-tk (das ueberschreibt das Panel beim Sprachwechsel)")
check("s2lnav" not in webpanel.make_page().split('<div id="setsec">')[0], "Hauptseite selbst bleibt ohne Kopfleiste (Symbole oben wie bisher)")

# Menue: dieselben Hauptseiten, zweite Ebene nur ueber die Einstellungen (Wunsch von Markus)
menu = re.findall(r"\['(\w+)', '([^']+)', '(\w+)'", nav)
check([m[0] for m in menu] == ["panel", "shows", "musik", "artists", "albums", "favs", "autodj", "radio", "raum", "stats", "health", "settings", "help", "about"], "Menue: Panel, Showmanager, Musik, Interpreten, Alben, Favoriten, Auto-DJ, Internetradio, Raum, Statistik, Zustand, Einstellungen, Hilfe, Ueber")
check(not any(u in ("/fixtures", "/apc", "/lumi", "/dmx", "/dmx-debug") for _, u, _ in menu), "Fixtures, APC, Lumi und DMX nicht im Menue")
check("history.back()" in nav and "r.origin === location.origin" in nav and "if (cameFromPanel())" in nav,
      "Pfeil: zurueck zur vorigen Seite, nur wenn sie vom Panel kam, sonst data-back (Wunsch von Markus)")
check("r.pathname !== location.pathname" in nav, "von Show zu Show (Assistent): Pfeil fuehrt zur Showliste statt in die vorige Show")
ejs = rd("editor.js")
pjs = rd("play.js")
check("go.onclick = () => { closeModals();" in ejs and "if (e.persisted) { closeModals(); if (!dirty) location.reload(); }" in ejs,
      "Editor: Fenster zu vor dem Wechsel, aus dem Zwischenspeicher neu geladen (Assistent-Fenster kam wieder)")
check("if (e.persisted) refresh()" in pjs and "visibilitychange" in pjs, "Showliste: nach Zurueck neu geladen, neue Shows erscheinen")
core = rd("core.js")
check("SM.ask = (text, value, okLabel)" in core and all(x not in pjs + rd("music.js") for x in ("confirm(", "prompt(", "alert(")),
      "Seite Shows und Musik-Datenbank: eigene Rueckfrage statt Browser-Dialog (Safari kann die blockieren, Show liess sich nicht loeschen)")
check('<script src="/static/sm/core.js"></script>' in rd("music.html"), "Musik-Datenbank laedt core.js fuer die Rueckfrage")
check("'/help?lang=' + lang" in nav, "Hilfe im Menue in der Sprache des Panels")
check("Escape" in nav and "closest('.s2l-m')" in nav, "Menue schliesst mit Escape und Antippen daneben")

# Texte: jeder Schluessel der Kopfleiste steht in texts.py (Uebersetzungstabelle) und kommt ueber /api/nav
cat = {k for k, *_ in texts.catalog()}
check(all(k in cat for k in webpanel.NAV_KEYS), "alle Texte der Kopfleiste in der Uebersetzungstabelle")
check(all(f"'{k}'" in nav or f"{k}:" in nav for k in ("nav_back", "nav_home", "nav_menu")), "nav.js hat Standardtexte, falls /api/nav nicht antwortet")


class FakeShow:
    def __init__(self, en):
        self.cfg = {"ui_lang": 1.0 if en else 0.0}
        self.texts = texts.TextStore(None)


d = webpanel.nav_info(FakeShow(True))
check(d["lang"] == "en" and d["texts"]["h_setpage"] == ["Einstellungen", "Settings"], "/api/nav: Sprache und Texte (Deutsch, English)")
check(webpanel.nav_info(FakeShow(False))["lang"] == "de", "/api/nav: Deutsch")
t = FakeShow(False); t.texts.set("h_room", de="Raum")
check(webpanel.nav_info(t)["texts"]["h_room"][0] == "Raum", "/api/nav: eigene Texte gelten")

# Einstellungen: Seiten geordnet in Geraete und Technik, Show, Musik und Hilfe nur im Menue
p = webpanel.settings_page()
g = p.index('data-tx="nav_devices"'); te = p.index('data-tx="nav_tech"')
L = lambda u: p.index('class="seclink" href="' + u + '"')
bed = p.index('data-cat="bed"')
check(g < L("/fixtures") < L("/raum") < te < L("/dmx") < L("/dmx-debug") < bed < L("/apc") < L("/lumi"),
      "Einstellungen: Geraete (Fixtures, Raum), Technik (DMX-Monitor, DMX-Debugger), APC und Lumi unter Bedienung")
check('class="seclink" href="/shows"' not in p and 'class="seclink" href="/musik"' not in p and 'id="helplink"' not in p, "Showmanager, Musik und Hilfe nicht mehr in der Liste")

# Editor: der Knopf fuer die linke Leiste ist kein zweites Menue-Symbol mehr
e = rd("editor.html")
check('<button id="bleft"' in e and '<button id="bleft" title="Geräte und Muster">☰' not in e, "Editor: linke Leiste mit eigenem Symbol, nicht ☰")

r = subprocess.run(["node", "--check", os.path.join(SM, "nav.js")], capture_output=True, text=True)
check(r.returncode == 0, "nav.js: node --check " + r.stderr.strip()[:200])

# Jeder Menue-Eintrag hat ein Symbol (Fehlerbericht 14.11.2026: "undefined" vor Favoriten)
import re as _re
_nav = open(os.path.join(PI, "static", "sm", "nav.js"), encoding="utf-8").read()
_ic = set(_re.findall(r"^    ([a-z]+): '", _nav[_nav.index("const IC = {"):_nav.index("const MENU")], _re.M))
_menu = _nav[_nav.index("const MENU = ["):_nav.index("const DEF")]
_need = [(b or a) for a, b in _re.findall(r"\['([a-z]+)', '[^']*', '[a-z_]+'(?:, '([a-z]+)')?\]", _menu)]
check(len(_need) >= 10 and not [x for x in _need if x not in _ic], "jeder Menue-Eintrag hat ein Symbol: fehlt " + str([x for x in _need if x not in _ic]))
check("(IC[ic || id] || '')" in _nav, "ohne Symbol nie 'undefined'")
finish("test_kopfleiste")
