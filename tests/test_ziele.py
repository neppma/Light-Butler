"""Ziele (Target for all movements) im Panel bearbeiten: neue Ziele anlegen, Namen und Position aendern, eigene Ziele
loeschen. Die festen Ziele aus fixtures.yaml lassen sich umbenennen, aber nicht loeschen. Gespeichert in aim.json."""
import json
import os
import shutil
import tempfile

from _common import build, Clock, check, finish

import webpanel

tmp = tempfile.mkdtemp(prefix="s2l_aim_")
path = os.path.join(tmp, "aim.json")
try:
    rig, sh = build(seed=9)
    sh.aim_file = path
    clk = Clock(sh)
    clk.run(2)
    keys = [a["key"] for a in sh.snapshot()["aims"]]
    check(keys[:4] == ["bank", "tisch", "tuer", "bar"], f"feste Ziele in der Reihenfolge aus fixtures.yaml ({keys})")

    # neues Ziel
    sh.command({"aim_add": "DJ-Pult"})
    snap = sh.snapshot()
    new = snap["aims"][-1]
    check(new == {"key": "dj_pult", "label": "DJ-Pult", "user": True}, f"neues Ziel angelegt ({new})")
    check(snap["aim"] == "dj_pult", "neues Ziel ist gleich ausgewaehlt (zum Einstellen der Position)")
    sh.command({"aim_set": {"vega_u": 0.2, "vega_v": 0.7, "bar": "all", "bar_t1": 90, "bar_t2": 160}})
    sh.command({"aim_save": True})
    v = sh.snapshot()["aim_vals"]
    check(v["vega_u"] == 0.2 and v["vega_v"] == 0.7 and v["bars"]["all"] == [90, 160], "Position des neuen Ziels eingestellt")
    sh.command({"aim_add": "DJ-Pult"})
    check(sh.snapshot()["aims"][-1]["key"] == "dj_pult_2", "gleicher Name: eigene Kennung")
    sh.command({"aim_add": "1. Reihe"})
    check(sh.snapshot()["aims"][-1]["key"] == "ziel_1_reihe", "Kennung beginnt immer mit einem Buchstaben")

    # umbenennen
    sh.command({"aim_rename": {"key": "dj_pult", "label": "Pult"}})
    sh.command({"aim_rename": {"key": "bank", "label": "Sofa"}})
    labels = {a["key"]: a["label"] for a in sh.snapshot()["aims"]}
    check(labels["dj_pult"] == "Pult" and labels["bank"] == "Sofa", "eigenes und festes Ziel umbenannt")
    sh.command({"aim_rename": {"key": "bank", "label": ""}})
    check({a["key"]: a["label"] for a in sh.snapshot()["aims"]}["bank"] == "", "festes Ziel: leerer Name = Standardname")
    for bad, why in (({"aim_add": "   "}, "leerer Name"), ({"aim_add": "x" * 31}, "zu langer Name"),
                     ({"aim_rename": {"key": "dj_pult", "label": ""}}, "eigenes Ziel ohne Namen"),
                     ({"aim_delete": "tisch"}, "festes Ziel loeschen"), ({"aim_delete": "gibtsnicht"}, "unbekanntes Ziel")):
        try:
            sh.command(bad)
            check(False, f"{why} abgelehnt")
        except ValueError:
            check(True, f"{why} abgelehnt")

    # gespeichert und nach dem Neustart wieder da
    saved = json.load(open(path))
    check(saved["dj_pult"]["user"] and saved["dj_pult"]["label"] == "Pult" and saved["dj_pult"]["vega"] == [0.2, 0.7],
          "aim.json enthaelt das neue Ziel mit Namen und Position")
    rig2, sh2 = build(seed=9)
    sh2.aim_file = path
    sh2.aim_targets = sh2._load_aim(rig2)
    k2 = {a["key"]: a for a in sh2.aims_info()}
    check("dj_pult" in k2 and k2["dj_pult"]["label"] == "Pult" and sh2.aim_targets["dj_pult"]["bars"] == [90, 160],
          "nach dem Neustart: Ziel mit Name und Position geladen")
    sh2.command({"aim": "dj_pult"})
    clk2 = Clock(sh2)
    clk2.run(2)
    check(sh2.snapshot()["aim"] == "dj_pult", "neues Ziel laesst sich anwaehlen")

    # loeschen
    sh.command({"aim": "dj_pult_2"})
    sh.command({"aim_delete": "dj_pult_2"})
    snap = sh.snapshot()
    check("dj_pult_2" not in [a["key"] for a in snap["aims"]] and snap["aim"] == "", "eigenes Ziel geloescht, Auswahl aufgehoben")

    # alte aim.json (nur Positionen) und fremde Eintraege
    with open(path, "w") as f:
        json.dump({"bank": {"vega": [0.1, 0.2]}, "boese": {"vega": [0, 0]}, "BAD KEY": {"user": True}}, f)
    t = sh._load_aim(rig)
    check(t["bank"]["vega"] == [0.1, 0.2] and "boese" not in t and "BAD KEY" not in t,
          "alte aim.json wird gelesen, unbekannte oder ungueltige Eintraege ignoriert")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# Panel
page = webpanel.make_page()
check('id="aim_edit"' in page and "function drawAims()" in page and "c({aim_add:" in page and "c({aim_rename:" in page
      and "c({aim_delete:" in page, "Panel: Bearbeiten, Anlegen, Umbenennen, Loeschen")
check("b.dataset.bar=k" in page and "b.dataset.k=k;" not in page, "Docooler-Auswahl nutzt kein Text-Merkmal mehr")

finish("test_ziele")
