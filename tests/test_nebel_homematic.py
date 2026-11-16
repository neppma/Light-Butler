"""SMOKE-Knopf mit HomeMatic: ist die Nebelmaschine (Steckdose) aus, schaltet der erste Druck sie ein, Nebel gibt es erst
nach der Aufheizzeit (und bei HomeMatic, wenn der Schalter Nebelschub erreichbar ist). Ausgeloest ueber DMX oder den
Schalter Nebelschub (Einstellung fog_via) mit ON_TIME-Sicherung; Loslassen, 10 s, Blackout und Dienstende schalten aus.
Nach 30 min ohne Nebel geht die Maschine aus. Mit nachgebauter CCU, es wird nie wirklich geschaltet."""
import os
import tempfile
import time

from _common import PI, build, Clock, check, finish

import homematic
from _homematic_fake import FakeCCU

POWER, TRIG = "ABC0000001", "ABC0000002"


def setup(power_on=False, via=1):
    fake = FakeCCU()
    fake.values[(POWER, "STATE")] = power_on
    home = homematic.Home(os.path.join(PI, "homematic.beispiel.yaml"), proxy=fake.proxy, rega=fake.rega, log=lambda m: None,
                          user_path=os.path.join(tempfile.mkdtemp(), "hu.json"))
    home.poll()
    rig, sh = build(seed=3)
    sh.home = home
    sh.cfg.set("fog_via", via)
    T = [1000.0]
    sh._fog_clock = lambda: T[0]
    clk = Clock(sh)
    clk.run(0.1)
    return fake, home, rig, sh, clk, T


def press(sh, on=True):
    sh.command({"hold": {"name": "fog", "on": on}})
    time.sleep(0.05)                                         # Schaltbefehle laufen im Hintergrund


def sent(fake, addr):
    return [(k, v) for i, a, k, v in fake.calls if a.startswith(addr)]


check(homematic.load_config(os.path.join(PI, "homematic.beispiel.yaml"))[0]["fog_trigger"] == {"interface": "BidCos-RF", "address": "ABC0000002:1"},
      "Nebelschub als fog_trigger eingetragen (Kanal 1, nicht als Panel-Kanal)")

# ---- Maschine aus: erster Druck schaltet ein, dann Aufheizen ----
fake, home, rig, sh, clk, T = setup(power_on=False)
fake.down.add(TRIG)                                          # Schalter stromlos, solange die Maschine aus ist
home.poll()
check(sh.snapshot()["fog_st"]["st"] == "off", "Maschine aus: Knopf zeigt aus")
press(sh)
press(sh, False)
check(sent(fake, POWER) == [("STATE", True)] and not sent(fake, TRIG), "erster Druck: Steckdose ein, kein Nebel")
st = sh.snapshot()["fog_st"]
check(st["st"] == "heat" and 230 <= st["left"] <= 240, f"heizt auf ({st['left']} s)")
hz = next(f for f in rig.fixtures if f.type == "hazer")
T[0] += 100
press(sh)
note = sh.note
press(sh, False)
check(not sent(fake, TRIG) and hz.manual_vals is None and "heizt noch 2:20" in note, f"waehrend des Aufheizens kein Nebel ({note})")
T[0] += 150
clk.run(0.05)
st = sh.snapshot()["fog_st"]
check(st["st"] == "heat" and st.get("wait_sw"), "warm, aber Schalter Nebelschub noch nicht erreichbar: wartet")
fake.down.discard(TRIG)
home.poll()
clk.run(0.05)
check(sh.snapshot()["fog_st"] == {"st": "ready", "via": "HM"}, "bereit ueber HomeMatic")

# ---- Nebelschub ueber HomeMatic ----
press(sh)
check(sent(fake, TRIG) == [("ON_TIME", 10.0), ("STATE", True)], "Schub: erst ON_TIME 10 s (Sicherung), dann ein")
check(hz.manual_vals is None, "HomeMatic: der DMX-Hazer bleibt aus")
check(sh.snapshot()["fog_st"]["st"] == "fire", "Knopf zeigt: nebelt")
T[0] += 4
press(sh, False)
check(sent(fake, TRIG)[-1] == ("STATE", False) and not sh.fog_hm_on, "Loslassen: sofort aus")
st = sh.snapshot()["fog_st"]
check(st["st"] == "pause" and 19 <= st["left"] <= 20, f"danach Pause ({st['left']} s)")
press(sh)
check(len(sent(fake, TRIG)) == 3, "waehrend der Pause kein neuer Schub")
press(sh, False)
T[0] += 21
press(sh)
T[0] += 10.1
clk.run(0.05)
time.sleep(0.05)
check(sent(fake, TRIG)[-1] == ("STATE", False) and not sh.fog_hm_on, "nach 10 s von selbst aus (auch wenn noch gehalten)")
press(sh, False)
T[0] += 21
press(sh)
sh.command({"blackout": True})
clk.run(0.05)
time.sleep(0.05)
check(sent(fake, TRIG)[-1] == ("STATE", False), "Blackout: Nebelschub sofort aus")
sh.command({"blackout": False})
press(sh, False)
T[0] += 21
press(sh)
home.sends = [time.monotonic()] * 20                         # Befehlsgrenze erreicht
press(sh, False)
check(sent(fake, TRIG)[-1] == ("STATE", False), "Aus wird nie durch die Befehlsgrenze blockiert")
home.sends = []
T[0] += 21
press(sh)
sh.close()
time.sleep(0.05)
check(sent(fake, TRIG)[-1] == ("STATE", False), "Dienstende: Nebelschub aus")

# ---- automatisch aus nach 30 min ohne Nebel ----
fake, home, rig, sh, clk, T = setup(power_on=True)
clk.run(0.05)
check(sh.snapshot()["fog_st"]["st"] == "ready", "Maschine beim Start schon an: gilt als warm")
T[0] += 29 * 60
clk.run(0.05)
check(not sent(fake, POWER), "nach 29 min noch an")
T[0] += 2 * 60
clk.run(0.05)
time.sleep(0.05)
check(sent(fake, POWER) == [("STATE", False)], "nach 30 min ohne Nebel: Steckdose aus")
sh.cfg.set("fog_off_min", 0)
fake2, home2, rig2, sh2, clk2, T2 = setup(power_on=True)
sh2.cfg.set("fog_off_min", 0)
T2[0] += 5 * 3600
clk2.run(0.05)
check(not sent(fake2, POWER), "0 = nie automatisch aus")

# ---- DMX ----
fake, home, rig, sh, clk, T = setup(power_on=True, via=0)
hz = next(f for f in rig.fixtures if f.type == "hazer")
press(sh)
check(hz.manual_vals and hz.manual_vals.get("pump") == 150 and not sent(fake, TRIG), "DMX: Hazer-Kanaele, kein HomeMatic-Schub")
check(sh.snapshot()["fog_st"]["via"] == "DMX", "Knopf zeigt DMX")
press(sh, False)
check(hz.manual_vals is None, "DMX: Loslassen aus")

# ---- Simulator ohne CCU ----
rig3, sh3 = build(seed=3)
check(sh3.snapshot()["fog_st"]["st"] == "ready", "Simulator ohne CCU: wie bisher sofort bereit (DMX)")
sh3.cfg.set("fog_via", 1)
check(sh3.snapshot()["fog_st"] == {"st": "err", "err": "ccu", "via": "HM"}, "HomeMatic ohne CCU: Fehler am Knopf")

# ---- Rauchmelder: Rueckfrage, Warnleiste, Erinnerung ----
fake, home, rig, sh, clk, T = setup(power_on=False)
clk.run(0.05)
check(sh.snapshot()["fog_note"] == "", "Maschine aus: keine Leiste")
sh.command({"fog_power": True})
time.sleep(0.05)
check(sent(fake, POWER) == [("STATE", True)] and sh.snapshot()["fog_st"]["st"] == "heat", "Einschalten nach der Rueckfrage (Panel)")
check(sh.snapshot()["fog_note"] == "on", "Leiste: Rauchmelder deaktiviert?")
sh.command({"fog_ack": "on"})
check(sh.snapshot()["fog_note"] == "", "OK tippen: Leiste weg")
fake.values[(POWER, "STATE")] = False                       # Maschine geht aus (Automatik oder von Hand)
home.poll()
clk.run(0.05)
check(sh.snapshot()["fog_note"] == "off", "nach dem Ausschalten: an die Rauchmelder erinnern")
sh.command({"fog_ack": "off"})
check(sh.snapshot()["fog_note"] == "", "Erinnerung weggetippt")
sh.command({"fog_power": True})
time.sleep(0.05)
check(sh.snapshot()["fog_note"] == "on", "wieder eingeschaltet: Leiste kommt wieder")
check(sh.snapshot()["fog_st"]["st"] == "heat", "heizt wieder")
sh.command({"fog_power": False})                             # nochmal SMOKE beim Aufheizen (nach der Rueckfrage)
time.sleep(0.05)
check(sent(fake, POWER)[-1] == ("STATE", False) and sh.snapshot()["fog_st"]["st"] == "off", "Aufheizen abgebrochen: Steckdose aus")
check(sh.snapshot()["fog_note"] == "off", "danach Erinnerung an die Rauchmelder")
fake6, home6, rig6, sh6, clk6, T6 = setup(power_on=True)
clk6.run(0.05)
check(sh6.snapshot()["fog_note"] == "on", "beim Start schon an: Leiste auch")

import webpanel
page = webpanel.make_page()
check("if(F.st==='off'){e.preventDefault();" in page and "confirm(TXT.fog_power_q[LANG==='de'?0:1]))c({fog_power:true})" in page,
      "Panel: Rueckfrage vor dem Einschalten der Nebelmaschine")
check("if(F.st==='heat'){e.preventDefault();if(confirm(TXT.fog_cancel_q[LANG==='de'?0:1]))c({fog_power:false})" in page,
      "Panel: nochmal tippen beim Aufheizen bricht ab (mit Rueckfrage)")
check('id="fognote"' in page and "c({fog_ack:S.fog_note||'on'})" in page, "Panel: Warnleiste mit OK")
check("function drawFog()" in page and "fg.classList.toggle('fst-'+k,F.st===k)" in page and "class=\"fbar\"" in page,
      "Panel: SMOKE-Knopf mit Zustaenden und Fortschrittsbalken")
finish("test_nebel_homematic")
