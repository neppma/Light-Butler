"""Regler "Ruhig bis wild" des Show-Assistenten nach der Energiestufe des Liedes vorgestellt (Wunsch von Markus, 06.11.2026)."""
import os
import subprocess

from _common import ROOT, check, finish

web = os.path.join(ROOT, "pi", "static", "sm")
out = subprocess.run(["node", "-e", "const SM=require(process.argv[1]);console.log(JSON.stringify([0,1,3,6,7,9].map(SM.wildFor)))",
                      os.path.join(web, "core.js")], capture_output=True, text=True).stdout.strip()
check(out == "[0.5,0.05,0.15,0.5,0.6,0.85]", f"Stufe 1 ruhig, 6 Mitte, 9 fast wild, ohne Stufe Mitte ({out})")
ed = open(os.path.join(web, "editor.js"), encoding="utf-8").read()
core = open(os.path.join(web, "core.js"), encoding="utf-8").read()
check("value=\"' + SM.wildFor(info.lvl) + '\"" in ed, "Fenster des Assistenten: Regler vorgestellt, frei verstellbar")
check(ed.count("wild: SM.wildFor(info.lvl)") == 1 and core.count("wild: SM.wildFor(info.lvl)") == 1, "Quick (Editor, Musik-Datenbank, Hauptpanel): derselbe Wert")
src = open(os.path.join(ROOT, "pi", "showman", "assistant.py"), encoding="utf-8").read()
check('(song["lvl"] - 6) * 0.04' not in src, "keine zweite, versteckte Verschiebung im Assistenten")
finish("Wild nach Energiestufe")
