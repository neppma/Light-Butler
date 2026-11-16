"""Handbuch auf Deutsch (docs/HANDBUCH.md) und Englisch (docs/MANUAL_EN.md). Der Hilfe-Knopf oeffnet die Fassung in der
Sprache des Panels. Beide Fassungen muessen gleich aufgebaut sein (Kapitel, Tabellenzeilen, Codebloecke): wer eine aendert,
muss die andere mitziehen."""
import os

from _common import ROOT, check, finish

import webpanel

de_p, en_p = (os.path.join(ROOT, "docs", n) for n in ("HANDBUCH.md", "MANUAL_EN.md"))
check(os.path.exists(en_p), "docs/MANUAL_EN.md vorhanden")
de, en = (open(p, encoding="utf-8").read().splitlines() for p in (de_p, en_p))


def shape(lines):
    return {"kapitel": sum(1 for x in lines if x.startswith("## ")),
            "tabellenzeilen": sum(1 for x in lines if x.startswith("|")),
            "code": sum(1 for x in lines if x.startswith("```")),
            "listen": sum(1 for x in lines if x.lstrip().startswith(("- ", "* ")) or x[:3].rstrip(".").isdigit())}


sd, se = shape(de), shape(en)
for k in sd:
    check(sd[k] == se[k], f"gleich aufgebaut: {k} (de {sd[k]}, en {se[k]})")
# Technische Beschreibung (15.11.2026: das fruehere ausfuehrliche Handbuch) ebenso zweisprachig gleich aufgebaut
td, te = (open(os.path.join(ROOT, "docs", n), encoding="utf-8").read().splitlines() for n in ("TECHNIK.md", "TECHNICAL_EN.md"))
std, ste = shape(td), shape(te)
for k in std:
    check(std[k] == ste[k], f"Technik gleich aufgebaut: {k} (de {std[k]}, en {ste[k]})")
check(td[0] == "# Light-Butler – Technische Beschreibung" and te[0] == "# Light-Butler – Technical description", "Titel der Technischen Beschreibung")
check(not any(w in "\n".join(te) for w in (" und ", " oder ", " nicht ", "Einstellungen →")), "keine deutschen Fuellwoerter in der englischen Technik")
check(len("\n".join(de)) < len("\n".join(td)) / 3, "Handbuch deutlich kuerzer als die Technische Beschreibung")
check(en[0] == "# Light-Butler – User Manual", "englischer Titel")
check("## Geräte einbinden" in td and "## Adding devices" in te, "Kapitel Geraete einbinden in der Technischen Beschreibung")
check(not any(w in "\n".join(en) for w in (" und ", " oder ", " nicht ", "Einstellungen →")), "keine deutschen Fuellwoerter im englischen Text")

hd, he = webpanel.help_page("de"), webpanel.help_page("en")
check('<html lang="de">' in hd and "Benutzerhandbuch" in hd and "Light-Butler - Handbuch" in hd, "Hilfe-Seite deutsch")
check(hd.index('class="cover"') < hd.index("<nav>") and "Markus Nepp" in hd and "Unterstützung von KI" in hd, "Deckblatt mit Name und KI-Hinweis vor dem Inhaltsverzeichnis")
check('class="cover"' in he and "Markus Nepp" in he and "help of AI" in he, "englisches Deckblatt")
check('<html lang="en">' in he and "User Manual" in he and "Light-Butler - Manual" in he and 'title="to top"' in he, "Hilfe-Seite englisch")
check(he.count('href="#k') == sd["kapitel"], "englisches Inhaltsverzeichnis mit allen Kapiteln")
old = webpanel.HELP_FILES_EN
webpanel.HELP_FILES_EN = ["/gibt/es/nicht.md"]
check("Benutzerhandbuch" in webpanel.help_page("en"), "fehlt die englische Fassung: deutsches Handbuch")
webpanel.HELP_FILES_EN = old

page = webpanel.make_page()
check("hb.href='/help?lang='+l" in page, "Hilfe-Knopf folgt der Sprache des Panels")
src = open(os.path.join(ROOT, "pi", "webpanel.py"), encoding="utf-8").read()
check('self.path.startswith("/help?")' in src and 'help_page("en" if lang == "en" else "de")' in src, "Server liefert /help?lang=de|en")
deploy = open(os.path.join(ROOT, "deploy.sh"), encoding="utf-8").read()
check(deploy.count("docs/MANUAL_EN.md") >= 2, "deploy.sh kopiert das englische Handbuch mit auf den Pi")
check(deploy.count("docs/TECHNIK.md docs/TECHNICAL_EN.md") >= 2, "deploy.sh kopiert die Technische Beschreibung")
th, the = webpanel.help_page("de", technik=True), webpanel.help_page("en", technik=True)
check("Technische Beschreibung" in th and 'href="/help?lang=de"' in th and "Technical description" in the and 'href="/help?lang=en"' in the,
      "Seite Technische Beschreibung mit Link zurueck zum Handbuch")
check('href="/help/technik?lang=de"' in hd and 'href="/help/technik?lang=en"' in he, "Handbuch verlinkt oben die Technische Beschreibung")
check('self.path.startswith("/help/technik?")' in src and "technik=True" in src, "Route /help/technik")
import pakete
check({"TECHNIK.md", "TECHNICAL_EN.md"} <= set(pakete._pi_docs(os.path.join(ROOT, "pi"))), "Technische Beschreibung in den Paketen")
finish("test_handbuch_en")
