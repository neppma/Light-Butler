"""Pi herunterfahren aus dem Panel: nur im echten Betrieb am Pi, nur mit Bestaetigung, nur mit der Freigabe aus
install_poweroff.sh. Licht sofort aus, dann poweroff. Hier mit nachgebautem Befehlsaufruf (faehrt nie wirklich herunter)."""
import os
import subprocess
import time

from _common import ROOT, build, Clock, check, finish

import texts
import webpanel

calls = []


class R:
    def __init__(self, rc):
        self.returncode = rc


def fake(allowed):
    def run(cmd, **kw):
        calls.append(list(cmd))
        return R(0 if (allowed or "-l" not in cmd) else 1)
    return run


rig, sh = build(seed=14)
Clock(sh).run(2)
sh.power_mode = "pi"                     # Verhalten am Pi (die Tests laufen auch am Mac und unter Windows)

# Simulator / Trockenlauf: gesperrt
sh._run_cmd = fake(True)
try:
    sh.command({"poweroff": "JA"})
    check(False, "im Simulator gesperrt")
except ValueError as e:
    check("Simulator" in str(e) and not calls, "im Simulator gesperrt, kein Befehl ausgefuehrt")

sh.allow_poweroff = True
sh.command({"poweroff": True})
sh.command({"poweroff": "ja bitte"})
check(not calls and not sh.powering_off, "ohne genaue Bestaetigung passiert nichts")

# Freigabe fehlt
sh._run_cmd = fake(False)
try:
    sh.command({"poweroff": "JA"})
    check(False, "ohne Freigabe abgelehnt")
except ValueError as e:
    check("install_poweroff.sh" in str(e) and not sh.powering_off and calls[-1] == ["sudo", "-n", "-l", "/usr/sbin/poweroff"],
          "ohne Freigabe: Hinweis auf install_poweroff.sh, nichts heruntergefahren")

# mit Freigabe
calls.clear()
sh._run_cmd = fake(True)
sh.command({"poweroff": "JA"})
snap = sh.snapshot()
check(snap["mode"] == "blackout" and snap["powering_off"], "Licht sofort aus, Status 'faehrt herunter'")
time.sleep(2.0)
check(calls[-1] == ["sudo", "-n", "/usr/sbin/poweroff"], "danach genau sudo -n /usr/sbin/poweroff")
check(all(c[0] == "sudo" for c in calls) and len(calls) == 2, "keine anderen Befehle")

# Panel und Einrichtung
page = webpanel.make_page()
check('id="powerbtn" onclick="powerOff()"' in page and 'data-tx="pw_q"' in page and 'onclick="pwGo()"' in page and "c({poweroff:'JA'})" in page,
      "Knopf oben rechts mit Rueckfrage im eigenen Fenster")
check("document.getElementById('pwdlg').style.display='flex';pwDraw()}" in page and "pwGo" not in page.split("function powerOff(")[1].split("}")[0],
      "der Knopf oeffnet nur das Fenster, heruntergefahren wird erst mit Herunterfahren")
check("const PW_OFF=['nanoleaf','effektband1','effektband2','derby_bar','musik','nebelmaschine'];" in page,
      "Ausschalt-Knoepfe nur fuer Nanoleaf, Effektband 1 und 2, Derby, Musik und den Strom der Nebelmaschine")
check("PW_OFF.includes(d.id)&&d.on===true" in page and "c({home:{id:x.dataset.id,on:false}})" in page,
      "nur was laut CCU noch an ist, bekommt einen Knopf, und der kann nur ausschalten")
check("fog_trigger" not in page[page.index("const PW_OFF="):page.index("function pwDevs")] and "on:true" not in page[page.index("function pwDraw"):page.index("function powerOff")],
      "das Fenster schaltet nur aus, der Nebelschub ist nie dabei")
keys = {k for k, *_ in texts.catalog()}
check({"pw_q", "pw_done", "pw_devs", "pw_dev_off", "pw_cancel", "pw_go"} <= keys, "Texte in der Uebersetzungstabelle")
script = os.path.join(ROOT, "pi", "install_poweroff.sh")
check(subprocess.run(["bash", "-n", script]).returncode == 0, "install_poweroff.sh ohne Syntaxfehler")
body = open(script).read()
check('NOPASSWD: /usr/sbin/poweroff"' in body and "visudo -cf" in body and "NOPASSWD: ALL" not in body,
      "Freigabe nur fuer /usr/sbin/poweroff, vorher mit visudo geprueft")


# Mac/Windows (16.11.2026): der Knopf beendet nur den Light-Butler (nie den Rechner), auch im Simulator
rig2, sh2 = build(seed=15)
Clock(sh2).run(2)
calls.clear()
sh2._run_cmd = fake(True)
sh2.power_mode = "quit"
check(sh2.snapshot()["power_mode"] == "quit", "Status: Knopf beendet das Programm")
sh2.command({"poweroff": "ja bitte"})
check(not sh2.powering_off, "ohne genaue Bestaetigung passiert nichts")
sh2.command({"poweroff": "JA"})
check(sh2.snapshot()["mode"] == "blackout" and sh2.powering_off and not sh2.quit_requested, "Licht sofort aus")
time.sleep(2.0)
check(sh2.quit_requested and not calls, "danach Programm-Ende, kein Befehl an den Rechner")
src = open(os.path.join(ROOT, "pi", "show.py"), encoding="utf-8").read()
check("if show.restart_requested or show.quit_requested:" in src and 'self.power_mode = "pi" if sys.platform.startswith("linux") else "quit"' in src,
      "Hauptschleife endet, nur Linux (Pi) faehrt herunter")
check({"pw_q_quit", "pw_go_quit", "pw_done_quit"} <= {r[0] for r in texts.catalog()} and "pwQuit()" in webpanel.make_page(),
      "Panel: eigene Rueckfrage zum Beenden")
finish("test_poweroff")
