"""HomeMatic ohne homematic.yaml (neue Installation, Windows, Mac, 27.11.2026): die Anbindung startet leer, ohne Adresse
wird nie gelesen oder geschaltet. Adresse, Kanaele und die Rollen (Steckdose der Nebelmaschine, Wohnzimmerlicht) kommen aus
dem Panel und stehen in homematic_user.json. Mit Datei kann die Rolle im Panel ueberschrieben werden ("keine" = SMOKE
feuert sofort ueber DMX). Mit nachgebauter CCU, es wird nie wirklich geschaltet."""
import json
import os
import tempfile
import time

from _common import PI, build, Clock, check, finish

import homematic
from _homematic_fake import FakeCCU

tmp = tempfile.mkdtemp()
upath = os.path.join(tmp, "homematic_user.json")
nofile = os.path.join(tmp, "homematic.yaml")                 # gibt es nicht
fake = FakeCCU()
fake.channels = [
    ("HmIP-RF", "003160C999C836:3", "SWITCH_TRANSMITTER", "Nebelmaschine Status:3"),
    ("HmIP-RF", "003160C999C837:3", "DIMMER_TRANSMITTER", "Wohnzimmer Dimmer:3"),
]


def mk(path=nofile, up=upath):
    return homematic.Home(path, proxy=fake.proxy, rega=fake.rega, log=lambda m: None, user_path=up)


# ---- ohne Datei: leer, nichts senden ----
home = mk()
st = home.status()
check(not home.has_file and st["file"] is False and st["host"] == "" and st["devices"] == [], "ohne Datei: leer, ohne Adresse")
check(st["roles"] == {"fog_power": "", "room_light": ""}, "ohne Datei: keine Rollen")
home.poll()
check(fake.reads == 0 and home.error == "", "ohne Adresse wird nichts gelesen, kein Fehler")
for f, what in ((lambda: home.scan(wait=True), "Kanaele holen"),):
    try:
        f()
        check(False, f"{what} ohne Adresse abgelehnt")
    except ValueError:
        check(True, f"{what} ohne Adresse abgelehnt")
check(fake.reads == 0, "auch beim Kanaele holen nichts gesendet")

# ---- einrichten im Panel ----
home.edit({"host": "192.168.1.99"})
home.scan(wait=True)
names = [f["name"] for f in home.found]
check(len(names) == 2, "Kanalliste von der CCU")
for f in home.found:
    home.edit({"add": {"interface": f["interface"], "status": f["status"]}})
ids = {d["label"]: d["id"] for d in home.devices}
sw, dim = ids["Nebelmaschine"], ids["Wohnzimmer Dimmer"]
for bad, why in (({"role": "fog_power", "id": dim}, "Dimmer als Nebel-Steckdose"), ({"role": "fog_power", "id": "gibtsnicht"}, "unbekannter Kanal"),
                 ({"role": "fog_trigger", "id": sw}, "unbekannte Rolle (Nebelschub nie)")):
    try:
        home.edit({"role": bad})
        check(False, f"abgelehnt: {why}")
    except ValueError:
        check(True, f"abgelehnt: {why}")
home.edit({"role": {"role": "fog_power", "id": sw}})
home.edit({"role": {"role": "room_light", "id": dim}})
check(home.ccu["fog_power"] == sw and home.ccu["room_light"] == dim, "Rollen gelten sofort")
u = json.load(open(upath))
check(u["roles"] == {"fog_power": sw, "room_light": dim} and u["host"] == "192.168.1.99", "gespeichert in homematic_user.json")
h2 = mk()
check(h2.ccu["fog_power"] == sw and h2.status()["roles"]["room_light"] == dim and len(h2.devices) == 2, "nach Neustart gleich")
home.edit({"remove": sw})
check(home.status()["roles"]["fog_power"] == "", "entfernter Kanal: Rolle zeigt keine")


# ---- mit Datei: Rolle im Panel auf "keine" = SMOKE sofort ueber DMX ----
def setup():
    f = FakeCCU()
    home = homematic.Home(os.path.join(PI, "homematic.beispiel.yaml"), proxy=f.proxy, rega=f.rega, log=lambda m: None,
                          user_path=os.path.join(tempfile.mkdtemp(), "hu.json"))
    home.poll()
    rig, sh = build(seed=3)
    sh.home = home
    sh.cfg.set("fog_via", 0)
    T = [1000.0]
    sh._fog_clock = lambda: T[0]
    clk = Clock(sh)
    clk.run(0.1)
    return f, home, rig, sh, clk


f, home, rig, sh, clk = setup()
check(home.status()["roles"]["fog_power"] == "nebelmaschine" and home.status()["file"], "mit Datei: Steckdose aus homematic.yaml")
check(sh.snapshot()["fog_st"]["st"] == "off", "Steckdose aus: SMOKE zeigt aus")
sh.command({"home_edit": {"role": {"role": "fog_power", "id": ""}}})
check(home.ccu["fog_power"] == "" and sh._fog_power() is None, "im Panel auf keine gestellt")
hz = next(x for x in rig.fixtures if x.type == "hazer")
sh.command({"hold": {"name": "fog", "on": True}})
time.sleep(0.05)
clk.run(0.05)
check(hz.manual_vals is not None and not f.calls, "SMOKE nebelt sofort ueber DMX, Steckdose nicht angefasst")
sh.command({"hold": {"name": "fog", "on": False}})
clk.run(0.05)
check(hz.manual_vals is None, "Loslassen: aus")
sh.command({"home_edit": {"role": {"role": "fog_power", "id": "nebelmaschine"}}})
check(sh._fog_power() == "nebelmaschine" and sh.fog_warm_t is None and sh.fog_prev_power is None,
      "wieder eingetragen: Zustand der Steckdose wird neu gelesen")

finish("test_homematic_ohne_datei")
