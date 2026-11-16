"""Hilfe-Knopf: Das Handbuch (docs/HANDBUCH.md, auf dem Pi HANDBUCH.md) als Seite /help. Ereignisfeld: Blackout,
Blinder und Smoke werden oben angezeigt wie Freeze, Strobe und WOW!."""
import os

from _common import ROOT, check, finish

import texts
import webpanel

page = webpanel.make_page()
check('<a id="helpbtn" href="/help" title=' in page, "kleiner Hilfe-Knopf oben rechts oeffnet /help im selben Tab")

html, toc = webpanel.markdown_to_html("# Titel\n\n## Teil A\n\nText mit **fett** und `code`.\n\n- eins\n- zwei\n\n"
                                      "1. erst\n2. dann\n\n| A | B |\n| --- | --- |\n| x | <b>y</b> |\n\n## Teil B\n\n<script>alert(1)</script>")
check("<h1" in html and html.count("<h2") == 2 and [t for _, t in toc] == ["Teil A", "Teil B"], "Ueberschriften und Inhaltsverzeichnis")
check("<b>fett</b>" in html and "<code>code</code>" in html, "fett und Code")
check("<ul><li>eins</li><li>zwei</li></ul>" in html and "<ol><li>erst</li><li>dann</li></ol>" in html, "Listen")
check("<table><tr><th>A</th><th>B</th></tr><tr><td>x</td><td>&lt;b&gt;y&lt;/b&gt;</td></tr></table>" in html, "Tabelle, Inhalt maskiert")
check("<script>" not in html and "&lt;script&gt;" in html, "HTML im Handbuch wird nur als Text gezeigt")
cb, _ = webpanel.markdown_to_html("Vorher\n\n```\ncd ~/x\npython3 a.py --all <b>\n```\n\nNachher")
check("<pre><code>cd ~/x\npython3 a.py --all &lt;b&gt;</code></pre>" in cb and "<p>Nachher</p>" in cb, "Code-Block bleibt zeilenweise, maskiert")

path = os.path.join(ROOT, "docs", "HANDBUCH.md")
check(os.path.exists(path), "docs/HANDBUCH.md vorhanden")
hp = webpanel.help_page()
n_h2 = sum(1 for line in open(path, encoding="utf-8") if line.startswith("## "))
check(hp.count("<nav>") == 1 and hp.count('href="#k') == n_h2 and n_h2 > 5, f"Hilfe-Seite mit {n_h2} Kapiteln im Inhaltsverzeichnis")
emb = webpanel.markdown_to_html("## X\n\n&#91;embedded content: Aufbau\\]\n")[0]
check("embedded content" in emb and 'class="emb"' in emb, "Export-Ueberbleibsel unauffaellig dargestellt")
deploy = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
check(deploy.count("docs/HANDBUCH.md") >= 2, "deploy.sh kopiert das Handbuch mit auf den Pi")

# Ereignisfeld
keys = {k for k, *_ in texts.catalog()}
for k in ("ev_blackout", "ev_sun", "ev_fog"):
    check(k in keys, f"Text {k} in der Uebersetzungstabelle")
check("if(S.mode==='blackout')return['blk',tr('ev_blackout')];" in page and "if(S.mode==='allbright')return['sun',tr('ev_sun')];" in page
      and "if(S.fog_on)return['fogs',tr('ev_fog')];" in page, "Ereignisfeld zeigt Blackout, Blinder und Smoke")
i = {k: page.index(k) for k in ("tr('ev_blackout')", "tr('ev_sun')", "tr('freeze')];", "tr('ev_blitz')", "tr('ev_fog')", "tr('ev_drop')")}
check(max(i["tr('ev_blackout')"], i["tr('ev_sun')"], i["tr('freeze')];"], i["tr('ev_blitz')"], i["tr('ev_fog')"]) < i["tr('ev_drop')"],
      "selbst gedrueckte Knoepfe haben im Ereignisfeld Vorrang vor dem automatischen Drop")
check("#evslot.blk{" in page and "#evslot.sun{" in page and "#evslot.fogs{" in page, "eigene Farben fuer die drei Anzeigen")

# 08.11.2026: Schema Geraete, Programme und Verbindungen als Bild im Handbuch
import xml.dom.minidom  # noqa: E402
_h, _ = webpanel.markdown_to_html("Text\n\n![Schema](/static/sm/verbindungen.svg)\n\n![x](http://fremd/x.svg)")
check('<p class="img"><img src="/static/sm/verbindungen.svg" alt="Schema"></p>' in _h and "fremd" not in _h.split("<img")[-1].split(">")[0] and "<img src=\"http" not in _h,
      "Bild im Handbuch: nur aus /static, fremde Adressen nicht als Bild")
for _f in ("verbindungen.svg", "verbindungen_en.svg"):
    _p = os.path.join(ROOT, "pi", "static", "sm", _f)
    check(os.path.isfile(_p) and xml.dom.minidom.parse(_p).documentElement.tagName == "svg", _f + " vorhanden und gueltig")
check("(/static/sm/verbindungen.svg)" in open(os.path.join(ROOT, "docs", "TECHNIK.md"), encoding="utf-8").read()
      and "(/static/sm/verbindungen_en.svg)" in open(os.path.join(ROOT, "docs", "TECHNICAL_EN.md"), encoding="utf-8").read(), "Verbindungs-Schema in beiden Fassungen der Technischen Beschreibung")
finish("test_hilfe")
