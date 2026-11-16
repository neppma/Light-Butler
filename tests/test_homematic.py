"""HomeMatic-CCU (Bereich "Haus"): Steckdosen schalten, Wohnzimmerlicht dimmen, Zustand lesen. Mit nachgebauter CCU,
es wird nie wirklich geschaltet. Nebelschub ist bewusst nicht dabei."""
import os
import time

from _common import PI, build, Clock, check, finish

import homematic
import webpanel


from _homematic_fake import FakeCCU


path = os.path.join(PI, "homematic.beispiel.yaml")
ccu_cfg, devs = homematic.load_config(path)
ids = [d["id"] for d in devs]
check(ids == ["licht_wz", "nanoleaf", "effektband1", "effektband2", "disco", "derby_bar", "musik", "nebelmaschine"], f"Geraete aus homematic.yaml ({ids})")
check(ccu_cfg["host"] == "192.168.1.20" and ccu_cfg["ports"] == {"HmIP-RF": 2010, "BidCos-RF": 2001}, "CCU-Adresse und Ports")
check("ABC0000002" not in open(path).read().split("# Bewusst NICHT hier")[0] + "".join(d["address"] for d in devs),
      "Nebelschub (ABC0000002) ist nicht schaltbar")

fake = FakeCCU()
fake.values[("000A1B2C3D4E01", "LEVEL")] = 0.12
fake.values[("000A1B2C3D4E02", "STATE")] = True
home = homematic.Home(path, proxy=fake.proxy, rega=fake.rega, log=lambda m: None)
home.poll()
st = {d["id"]: d for d in home.status()["devices"]}
check(st["licht_wz"]["level"] == 0.12 and st["licht_wz"]["on"] and st["nanoleaf"]["on"] and st["disco"]["on"] is False,
      "Zustand gelesen: Licht 12 %, Nanoleaf an, Disco aus")

home.set("disco", on=True, wait=True)
check(fake.calls[-1] == ("HmIP-RF", "000A1B2C3D4E05:3", "STATE", True), "Disco einschalten: STATE True an den Schaltkanal")
home.set("licht_wz", level=0.6, wait=True)
check(fake.calls[-1] == ("HmIP-RF", "000A1B2C3D4E01:4", "LEVEL", 0.6), "Licht auf 60 %: LEVEL 0.6 an den Dimmerkanal")
home.set("licht_wz", on=False, wait=True)
check(fake.calls[-1][3] == 0.0, "Licht aus: LEVEL 0")
home.set("licht_wz", on=True, wait=True)
check(fake.calls[-1][3] == 0.6, "Licht an: wieder die letzte Helligkeit (60 %)")
home.set("nebelmaschine", on=False, wait=True)
check(fake.calls[-1] == ("BidCos-RF", "ABC0000001:1", "STATE", False), "Nebelmaschine (BidCos) schalten")
for bad in (("gibtsnicht", True, None), ("disco", None, None)):
    try:
        home.set(bad[0], on=bad[1], level=bad[2], wait=True)
        check(False, f"abgelehnt: {bad}")
    except ValueError:
        check(True, f"abgelehnt: {bad}")
home.set("licht_wz", level=5, wait=True)
check(fake.calls[-1][3] == 1.0, "Helligkeit auf 0 bis 100 % begrenzt")

fake.down.add("000A1B2C3D4E07")
home.poll()
st = {d["id"]: d for d in home.status()["devices"]}
check(st["musik"]["ok"] is False and "Musik" in home.status()["error"], "nicht erreichbares Geraet wird gemeldet")
home.set("musik", on=True, wait=True)
check({d["id"]: d for d in home.status()["devices"]}["musik"]["ok"] is False, "Schalten eines nicht erreichbaren Geraets: Fehler statt Absturz")

# Show: Befehl und Status
rig, sh = build()
Clock(sh).run(1)
try:
    sh.command({"home": {"id": "disco", "on": True}})
    check(False, "Simulator: Haus nicht verfuegbar")
except ValueError:
    check(sh.snapshot()["home"] is None, "Simulator/Trockenlauf: keine CCU-Verbindung, Befehl abgelehnt")
sh.home = home
n = len(fake.calls)
sh.command({"home": {"id": "effektband1", "on": True}})
time.sleep(0.3)
check(fake.calls[n:] == [("HmIP-RF", "000A1B2C3D4E03:3", "STATE", True)], "Befehl aus dem Panel schaltet im Hintergrund")
check(any(d["id"] == "effektband1" and d["on"] for d in sh.snapshot()["home"]["devices"]), "Status zeigt den neuen Zustand sofort")

page = webpanel.make_page()
check('<details id="homebox"' in page and 'data-tx="m_home"' in page and "function drawHome()" in page
      and "c({home:{id:id,level:sl.value/100}})" in page, "Panel: Bereich Haus mit Regler und Knoepfen")

finish("test_homematic")
