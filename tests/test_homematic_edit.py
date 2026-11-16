"""HomeMatic im Panel einstellen: Adresse der CCU, Namen der Kanaele, Kanaele hinzufuegen (nur aus der Kanalliste der CCU)
und entfernen. Alles steht in homematic_user.json, homematic.yaml bleibt unveraendert. Der Nebelschub ist nie schaltbar.
Mit nachgebauter CCU, es wird nie wirklich geschaltet."""
import json
import os
import tempfile

from _common import PI, ROOT, build, Clock, check, finish

import homematic
import webpanel
from _homematic_fake import FakeCCU

path = os.path.join(PI, "homematic.beispiel.yaml")
yaml_text = open(path, encoding="utf-8").read()
tmp = tempfile.mkdtemp()
upath = os.path.join(tmp, "homematic_user.json")
fake = FakeCCU()
fake.channels = [
    ("BidCos-RF", "ABC0000002:1", "SWITCH", "Nebelschub:1"),
    ("HmIP-RF", "003160C999C836:3", "SWITCH_TRANSMITTER", "LS VZ Status Hauplicht:3"),
    ("HmIP-RF", "003160C999C836:7", "SWITCH_TRANSMITTER", "LS VZ Status Vitrine:7"),
    ("BidCos-RF", "ABC0000003:1", "DIMMER", "LS AZ Licht Dimmer:1"),
    ("HmIP-RF", "000A1B2C3D4E05:2", "SWITCH_TRANSMITTER", "FSD WZ Disco Status:2"),
    ("HmIP-RF", "0007E0C99D3D40:2", "ALARM_COND_SWITCH_TRANSMITTER", "Rauchmelder:2"),
    ("HmIPW", "000ABC12345678:2", "SWITCH_TRANSMITTER", "Unbekannte Schnittstelle:2"),
]


def mk():
    return homematic.Home(path, proxy=fake.proxy, rega=fake.rega, log=lambda m: None, user_path=upath)


home = mk()
base_ids = [d["id"] for d in home.devices]
check(home.ccu["host"] == "192.168.1.20" and len(base_ids) == 8 and not os.path.exists(upath), "ohne Aenderungen: wie homematic.yaml")

# ---- Adresse der CCU ----
for bad in ("http://192.168.1.20", "1.2.3.4;rm", "a b", "x" * 80):
    try:
        home.edit({"host": bad})
        check(False, f"Adresse abgelehnt: {bad!r}")
    except ValueError:
        check(True, f"Adresse abgelehnt: {bad[:20]!r}")
home.edit({"host": "192.168.1.99"})
check(home.ccu["host"] == "192.168.1.99" and home.status()["host"] == "192.168.1.99", "neue Adresse gilt sofort")
check(json.load(open(upath))["host"] == "192.168.1.99" and mk().ccu["host"] == "192.168.1.99", "Adresse gespeichert, gilt nach Neustart")
home.edit({"host": "192.168.1.20"})
check(json.load(open(upath))["host"] == "" and home.ccu["host"] == "192.168.1.20", "zurueck auf die Adresse aus homematic.yaml")

# ---- Namen ----
home.edit({"label": {"id": "disco", "text": "  Discokugel  "}})
check({d["id"]: d["label"] for d in home.status()["devices"]}["disco"] == "Discokugel", "Name geaendert, sofort im Status")
check({d["id"]: d["label"] for d in mk().devices}["disco"] == "Discokugel", "Name bleibt nach Neustart")
for bad in ({"id": "disco", "text": "  "}, {"id": "gibtsnicht", "text": "X"}):
    try:
        home.edit({"label": bad})
        check(False, f"Name abgelehnt: {bad}")
    except ValueError:
        check(True, f"Name abgelehnt: {bad}")
home.edit({"label": {"id": "musik", "text": "M" * 100}})
check(len(home.by_id["musik"]["label"]) == homematic.LABEL_MAX, "Name auf 40 Zeichen begrenzt")
home.set("disco", on=True, wait=True)
check(fake.calls[-1] == ("HmIP-RF", "000A1B2C3D4E05:3", "STATE", True), "umbenannter Kanal schaltet wie vorher")

# ---- Kanaele holen und hinzufuegen ----
try:
    home.edit({"add": {"interface": "HmIP-RF", "status": "003160C999C836:3"}})
    check(False, "Hinzufuegen ohne Kanalliste abgelehnt")
except ValueError:
    check(True, "Hinzufuegen ohne Kanalliste abgelehnt")
home.scan(wait=True)
found = home.status()["found"]
addrs = {f["status"]: f for f in found}
check("ABC0000002:1" not in addrs, "Nebelschub wird nie angeboten")
check("0007E0C99D3D40:2" not in addrs and "000ABC12345678:2" not in addrs, "nur Steckdosen und Dimmer der bekannten Schnittstellen")
check(addrs["003160C999C836:3"]["address"] == "003160C999C836:4" and addrs["003160C999C836:7"]["address"] == "003160C999C836:8",
      "HmIP: geschaltet wird der Kanal nach dem Statuskanal")
check(addrs["ABC0000003:1"]["address"] == "ABC0000003:1" and addrs["ABC0000003:1"]["kind"] == "dimmer", "BidCos-Dimmer: ein Kanal")
check(addrs["003160C999C836:3"]["label"] == "LS VZ Hauplicht", "Vorschlag fuer den Namen ohne 'Status' und ':3'")
home.edit({"add": {"interface": "HmIP-RF", "status": "003160C999C836:3"}})
new = home.devices[-1]
check(new["id"] == "ls_vz_hauplicht" and new["address"] == "003160C999C836:4" and new["kind"] == "switch", f"Kanal hinzugefuegt ({new['id']})")
fake.values[("003160C999C836", "STATE")] = True
home.poll()
check({d["id"]: d for d in home.status()["devices"]}["ls_vz_hauplicht"]["on"] is True, "neuer Kanal: Zustand wird gelesen")
home.set("ls_vz_hauplicht", on=False, wait=True)
check(fake.calls[-1] == ("HmIP-RF", "003160C999C836:4", "STATE", False), "neuer Kanal schaltet")
home.edit({"add": {"interface": "BidCos-RF", "status": "ABC0000003:1"}})
check(home.by_id[home.devices[-1]["id"]]["kind"] == "dimmer", "Dimmer hinzugefuegt")
try:
    home.edit({"add": {"interface": "HmIP-RF", "status": "003160C999C836:3"}})
    check(False, "doppelt abgelehnt")
except ValueError:
    check(True, "derselbe Kanal kann nicht zweimal hinein")
home.found.append({"interface": "BidCos-RF", "status": "ABC0000002:1", "address": "ABC0000002:1", "kind": "switch",
                   "name": "Nebelschub", "label": "Nebelschub"})
try:
    home.edit({"add": {"interface": "BidCos-RF", "status": "ABC0000002:1"}})
    check(False, "Nebelschub abgelehnt")
except ValueError:
    check(True, "Nebelschub laesst sich auch untergeschoben nicht hinzufuegen")
u = json.load(open(upath))
u["added"].append({"id": "nebel", "label": "Nebel", "kind": "switch", "interface": "BidCos-RF", "address": "ABC0000002:1",
                   "status": "ABC0000002:1"})
json.dump(u, open(upath, "w"))
check("nebel" not in mk().by_id, "Nebelschub von Hand in homematic_user.json: wird ignoriert")
u["added"].pop()
json.dump(u, open(upath, "w"))
check(homematic.forbidden("abc0000002:1"), "Sperre auch bei Kleinschreibung")

# ---- Entfernen und wieder hinzufuegen ----
home.edit({"remove": "disco"})
check("disco" not in home.by_id and "disco" in json.load(open(upath))["removed"], "Kanal aus homematic.yaml entfernt (nur ausgeblendet)")
home.edit({"add": {"interface": "HmIP-RF", "status": "000A1B2C3D4E05:2"}})
check("disco" in home.by_id and home.by_id["disco"]["address"] == "000A1B2C3D4E05:3", "wieder hinzugefuegt: derselbe Kanal mit seiner id")
home.edit({"remove": "ls_vz_hauplicht"})
check("ls_vz_hauplicht" not in home.by_id and all(a["id"] != "ls_vz_hauplicht" for a in json.load(open(upath))["added"]),
      "hinzugefuegter Kanal entfernt")
try:
    home.edit({"remove": "gibtsnicht"})
    check(False, "unbekannt")
except ValueError:
    check(True, "Entfernen eines unbekannten Kanals abgelehnt")
h2 = mk()
check([d["id"] for d in h2.devices] == [d["id"] for d in home.devices], "nach Neustart dieselben Kanaele")
check(open(path, encoding="utf-8").read() == yaml_text, "homematic.yaml bleibt unveraendert")

open(upath, "w").write("{kaputt")
check([d["id"] for d in mk().devices] == base_ids, "defekte homematic_user.json: wie homematic.yaml")
os.remove(upath)

fake.offline = True
h3 = mk()
h3.scan(wait=True)
check(h3.found is None and "Kanalliste" in h3.status()["error"] and not h3.scanning, "CCU nicht erreichbar: Fehler statt Absturz")
fake.offline = False

# ---- Show und Panel ----
rig, sh = build()
Clock(sh).run(0.5)
for cmd in ({"home_scan": 1}, {"home_edit": {"host": "1.2.3.4"}}):
    try:
        sh.command(cmd)
        check(False, "Simulator")
    except ValueError:
        check(True, f"Simulator: {list(cmd)[0]} abgelehnt")
sh.home = mk()
sh.command({"home_scan": 1})
import time
for _ in range(50):
    if sh.home.found is not None:
        break
    time.sleep(0.02)
check(sh.snapshot()["home"]["found"] and sh.snapshot()["home"]["host"] == "192.168.1.20", "Panel bekommt Kanalliste und Adresse")
sh.command({"home_edit": {"label": {"id": "musik", "text": "Anlage"}}})
d = {x["id"]: x for x in sh.snapshot()["home"]["devices"]}
check(d["musik"]["label"] == "Anlage" and d["musik"]["addr"] == "000A1B2C3D4E07:3" and sh.note == "Gespeichert.", "Befehl aus dem Panel")
os.remove(upath)

page = webpanel.make_page()
check("function drawHomeEdit(box)" in page and "c({home_edit:{host:" in page and "c({home_scan:1})" in page
      and "c({home_edit:{add:{interface:f.interface,status:f.status}}})" in page, "Panel: Einstellungen im Bereich Haus")
dep = open(os.path.join(ROOT, "deploy.sh")).read()
check("--exclude '*.json'" in dep, "deploy.sh ueberschreibt homematic_user.json nie")
import backup
check("*.json" in backup.INCLUDE, "homematic_user.json ist in der Sicherung")

finish("test_homematic_edit")
