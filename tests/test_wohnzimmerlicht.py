"""Automatik Wohnzimmerlicht (HomeMatic): laenger Stille -> hochdimmen, Partylichter dunkel statt Atmen; Musik und
mindestens ein Partylicht erreichbar -> aus. Nur beim Wechsel, Handbetrieb dazwischen bleibt. Nachgebaute CCU."""
import os

from _common import PI, build, Clock, check, finish

import homematic
import webpanel
from _homematic_fake import FakeCCU

fake = FakeCCU()
home = homematic.Home(os.path.join(PI, "homematic.beispiel.yaml"), proxy=fake.proxy, rega=fake.rega, log=lambda m: None)
rig, sh = build(seed=15)
sh.home = home
clk = Clock(sh)
sets = lambda: [c for c in fake.calls if c[1].startswith("000A1B2C3D4E01") and c[2] != "RAMP_TIME"]
ramps = lambda: [c for c in fake.calls if c[1].startswith("000A1B2C3D4E01") and c[2] == "RAMP_TIME"]


def run(state, secs, reach=None):
    sh.reach = reach if reach is not None else {"Art-Net-Gateway": True}
    t = [clk.t]
    for _ in range(int(secs / 0.025)):
        t[0] += 0.025
        sh.state = state
        sh._home_auto(t[0])
    clk.t = t[0]


sh.cfg.set("home_party_min", 0)                             # erst das Verhalten von frueher (sofort, 3 s Musik bis aus)
sh.cfg.set("home_music_s", 3)
run("idle", 9.0)
home_calls = sets()
check(home_calls == [], "Stille unter 10 s: nichts geschaltet")
run("idle", 1.5)
import time; time.sleep(0.2)
check(sets() == [("HmIP-RF", "000A1B2C3D4E01:4", "LEVEL", 0.6)], f"nach 10 s Stille: Licht auf 60 % ({sets()})")
check(sh.home_lit, "Partylichter dunkel statt Atmen")
run("idle", 30)
time.sleep(0.1)
check(len(sets()) == 1, "in der Stille nur einmal geschaltet")

run("normal", 2.0)
time.sleep(0.1)
check(len(sets()) == 1 and not sh.home_lit, "Musik unter 3 s: Licht bleibt an")
run("normal", 1.5)
time.sleep(0.2)
check(sets()[-1] == ("HmIP-RF", "000A1B2C3D4E01:4", "LEVEL", 0.0), "Musik ab 3 s und OLA erreichbar: Licht aus")
home.set("licht_wz", level=0.3, wait=True)                 # du schaltest es waehrend der Musik selbst wieder an
n = len(sets())
run("normal", 20)
time.sleep(0.1)
check(len(sets()) == n, "Handbetrieb waehrend der Musik bleibt (kein Gegen-Schalten)")

# keine Partylichter erreichbar: Licht bleibt bei Musik an
run("normal", 30)                                           # Mindestabstand zum letzten Befehl der Automatik
run("idle", 11)
time.sleep(0.1)
n = len(sets())
run("normal", 10, reach={"Art-Net-Gateway": False, "Effektband": False, "Nanoleaf": None})
time.sleep(0.1)
check(len(sets()) == n, "Musik, aber kein Partylicht erreichbar: Wohnzimmerlicht bleibt an")
run("normal", 30, reach={"Nanoleaf": True})
time.sleep(0.2)
check(sets()[-1][3] == 0.0, "sobald ein Partylicht (Nanoleaf) erreichbar ist: aus")

# Einstellungen
sh.cfg.set("home_idle_s", 30)
sh.cfg.set("home_idle_level", 40)
run("normal", 30)
run("idle", 29)
time.sleep(0.1)
n = len(sets())
run("idle", 2)
time.sleep(0.2)
check(len(sets()) == n + 1 and sets()[-1][3] == 0.4, "eingestellt: nach 30 s auf 40 %")
sh.cfg.set("home_auto", 0)
run("normal", 10)
time.sleep(0.1)
check(len(sets()) == n + 1 and not sh.home_lit, "Automatik aus: nichts wird geschaltet")

# Duty Cycle der CCU (Fehlerbericht: CCU2 bei 99 %): keine Dauerbefehle, Lesen ohne Funk
sh.cfg.set("home_auto", 1)
sh.cfg.set("home_idle_s", 10)
sh.cfg.set("home_music_s", 3)
run("normal", 60)
n = len(sets())
for _ in range(20):                                         # Musik und Stille wechseln dauernd (z. B. Rauschen am Eingang)
    run("idle", 11)
    run("normal", 4)
time.sleep(0.2)
check(2 <= len(sets()) - n <= 11, f"staendiger Wechsel Stille/Musik (5 min): hoechstens ein Befehl alle 30 s ({len(sets()) - n})")
fake.values[("000A1B2C3D4E01", "LEVEL")] = 0.0
home.poll()
sh.home_last, sh.home_send_t = None, None
n = len(sets())
run("normal", 10)
time.sleep(0.1)
check(len(sets()) == n and sh.home_last == "off", f"Licht laut CCU schon aus: kein Befehl gesendet ({sets()[n:]}, {home.state['licht_wz']}, {sh.home_last})")
r0 = fake.reads
home.poll()
check(fake.reads == r0 + 1, "Zustand aller Geraete mit einem einzigen ReGa-Aufruf gelesen")
check(not hasattr(fake.proxy("HmIP-RF"), "getValue"), "kein getValue (wuerde HmIP-Geraete per Funk abfragen)")
src = open(os.path.join(PI, "homematic.py")).read()
check("getValue" not in src.split('"""', 2)[2], "homematic.py ruft getValue nirgends auf")
home.sends.clear()
ok = 0
for i in range(30):
    try:
        home.set("disco", on=bool(i % 2), wait=True)
        ok += 1
    except ValueError:
        pass
check(ok == homematic.MAX_SENDS and "Duty Cycle" in home.status()["error"], f"hoechstens {homematic.MAX_SENDS} Schaltbefehle pro Minute ({ok})")
home.sends = [t - 61 for t in home.sends]
home.set("disco", on=False, wait=True)
check(fake.calls[-1][1].startswith("000A1B2C3D4E05"), "nach einer Minute geht es wieder")
home.sends = [t - 61 for t in home.sends]
for _ in range(homematic.MAX_SENDS):
    home.set("disco", on=True, wait=True)
sh.home_last, sh.home_send_t = None, None
run("idle", 11)
check(sh.home_last is None, "Grenze erreicht: Automatik versucht es spaeter, ohne Absturz")
logs = []
home.log = logs.append
home.sends.clear()
home.set("licht_wz", level=0.25, wait=True)
check(logs == ["HomeMatic: Wohnzimmerlicht LEVEL=0.25"], f"jeder Schaltbefehl steht im Log ({logs})")
home.log = lambda m: None
fake.offline = True
home.poll()
check(all(d["ok"] is False for d in home.status()["devices"]) and "ReGa" in home.status()["error"], "CCU nicht erreichbar: gemeldet")
fake.offline = False
home.sends.clear()
sh.home_lit = False

# Ruhemodus ohne Atmen, solange das Licht an ist
sh.cfg.set("home_auto", 1)
sh.home_lit = True
sh._render_idle(clk.t, 0.025)
COLOR = ("r", "g", "b", "w", "uv", "r1", "g1", "b1", "w1", "r2", "g2", "b2", "w2")
lit = max(v for fx, _ in sh.bars + sh.wash + sh.barlight for p, v in fx.values.items() if p in COLOR)
check(lit == 0, "Wohnzimmerlicht an: Partylichter ganz dunkel")
sh.home_lit = False
breath = []
for k in range(80):
    sh._render_idle(clk.t + k * 0.5, 0.025)
    breath.append(max(v for fx, _ in sh.bars for p, v in fx.values.items() if p in ("r", "g", "b", "r1", "g1", "b1")))
check(max(breath) > 0, "ohne Wohnzimmerlicht: Atmen wie bisher")

# Verbindungen: CCU mit IP
src = open(os.path.join(PI, "webpanel.py")).read()
check('hosts.append(("CCU", show.home.ccu["host"]' in src, "Verbindungen zeigen die CCU mit IP und erreichbar/nicht erreichbar")

# im Panel-Bereich Haus einstellbar
import texts
cfg = sh.snapshot()["home_cfg"]
check([x["key"] for x in cfg] == ["home_auto", "home_party_min", "home_idle_s", "home_idle_level", "home_ramp_s", "home_music_s"], "Status liefert die Werte der Automatik")
sh.command({"set": {"home_idle_s": 45, "home_idle_level": 80, "home_music_s": 5}})
cfg = {x["key"]: x["value"] for x in sh.snapshot()["home_cfg"]}
check(cfg["home_idle_s"] == 45 and cfg["home_idle_level"] == 80 and cfg["home_music_s"] == 5, "Werte aus dem Bereich Haus geaendert")
keys = {k for k, *_ in texts.catalog()}
check({"home_auto_h", "ha_home_auto", "ha_home_party_min", "ha_home_ramp_s", "ha_home_idle_s", "ha_home_idle_level", "ha_home_music_s"} <= keys, "Texte in der Uebersetzungstabelle")
page = webpanel.make_page()
check("function drawHomeAuto(box)" in page and "c({set:{[k]:+sl.value}})" in page, "Panel: Regler der Automatik im Bereich Haus")

# Fehlerbericht 12.11.2026: mit richtiger Stille-Schwelle ging das Licht bei jedem Geraeusch am Eingang an und aus.
# Neu: an nur nach echter Musik (home_party_min), aus erst nach 30 s Musik (Standard).
import settings as _st
_d = {p.key: p for p in _st.DEFS}
check(_d["home_party_min"].default == 5.0 and _d["home_music_s"].default == 30.0, "Standard: 5 min Musik vor dem Einschalten, 30 s Musik bis aus")
rig2, sh2 = build(seed=16)
fake2 = FakeCCU()
sh2.home = homematic.Home(os.path.join(PI, "homematic.beispiel.yaml"), proxy=fake2.proxy, rega=fake2.rega, log=lambda m: None)
sets2 = lambda: [c_ for c_ in fake2.calls if c_[1].startswith("000A1B2C3D4E01") and c_[2] != "RAMP_TIME"]   # noqa: E731
t2 = [1000.0]


def run2(state, secs):
    sh2.reach = {"Art-Net-Gateway": True}
    for _ in range(int(secs / 0.025)):
        t2[0] += 0.025
        sh2.state = state
        sh2._home_auto(t2[0])
    time.sleep(0.15)


run2("idle", 60)
check(sets2() == [], "nur Stille (Rauschen), nie Musik: Licht bleibt aus")
run2("normal", 20)
run2("idle", 60)
check(sets2() == [], "20 s Geraeusch, dann Stille: Licht bleibt aus")
run2("normal", 290)
run2("idle", 15)
check(sets2() and sets2()[-1][3] == 0.6, "nach gut 5 Minuten Musik und Stille: Licht an")
n2 = len(sets2())
run2("normal", 20)
check(len(sets2()) == n2, "20 s Geraeusch in der Stille: Licht bleibt an (aus erst nach 30 s Musik)")
run2("normal", 15)
check(sets2()[-1][3] == 0.0, "nach 30 s Musik: aus")
run2("idle", 60)
check(sets2()[-1][3] == 0.0, "danach wieder nur kurz Musik: bei Stille nicht gleich wieder an (zaehlt von vorn)")

# langsam ein- und ausdimmen (Wunsch 12.11.2026): RAMP_TIME vor LEVEL, einstellbar, 0 = sofort; Handbetrieb ohne Rampe
check(_d["home_ramp_s"].default == 5.0, "Standard: 5 s Dimmzeit")
seq = [c_[2] for c_ in fake2.calls if c_[1].startswith("000A1B2C3D4E01")]
check(seq[:2] == ["RAMP_TIME", "LEVEL"] and [c_[3] for c_ in fake2.calls if c_[2] == "RAMP_TIME"][0] == 5.0, "Automatik: erst Dimmzeit 5 s, dann Helligkeit: " + str(seq[:4]))
n_r = len([c_ for c_ in fake2.calls if c_[2] == "RAMP_TIME"])
sh2.home.set("licht_wz", level=0.4, wait=True)
check(len([c_ for c_ in fake2.calls if c_[2] == "RAMP_TIME"]) == n_r, "von Hand (Regler im Bereich Haus): ohne Rampe wie bisher")
sh2.home.set("licht_wz", level=0.2, wait=True, ramp_s=0)
check(len([c_ for c_ in fake2.calls if c_[2] == "RAMP_TIME"]) == n_r, "Dimmzeit 0: sofort, keine Rampe gesendet")

finish("test_wohnzimmerlicht")
