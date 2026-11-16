"""Lauftext fuer lange Albumtitel bei den Interpreten (Wunsch von Markus, 14.11.2026): Kachel bleibt so breit wie das Cover,
zu lange Titel gleiten hin und zurueck (SM.marquee), mit "Bewegung reduzieren" zweizeilig."""
import os
import subprocess

from _common import ROOT, check, finish

SM = os.path.join(ROOT, "pi", "static", "sm")
rd = lambda f: open(os.path.join(SM, f), encoding="utf-8").read()
core, art, css, html = rd("core.js"), rd("artists.js"), rd("sm.css"), rd("artists.html")
check("SM.marquee = " in core and "scrollWidth - el.clientWidth" in core, "Lauftext misst nur zu lange Titel")
check(art.count('class="at mq"><span>') == 2 and "SM.marquee($('myalb'))" in art and "SM.marquee($('ainfo'))" in art, "eigene und Deezer-Alben laufen")
check("@keyframes lbmq" in css and "prefers-reduced-motion: reduce) {\n  .mq.run" in css, "Animation, zweizeilig bei Bewegung reduzieren")
check("width: 92px; min-width: 0;" in html, "Kachel waechst nicht mit dem Titel")
for f in ("core.js", "artists.js"):
    check(subprocess.run(["node", "--check", os.path.join(SM, f)]).returncode == 0, f + " ohne Syntaxfehler")
finish("test_lauftext")
