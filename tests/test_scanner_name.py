"""Licht-Mix KITT heisst seit 15.11.2026 Scanner. Gespeicherte Dateien mit dem alten Namen wirken weiter."""
import json
import os
import tempfile

from _common import build, check, finish

import fine
import lumi_ctl
import midi_ctl
import scenes
import texts

check(scenes.renamed("KITT") == "Scanner" and scenes.renamed("kitt") == "scanner" and scenes.renamed("Disco") == "Disco", "Namen uebersetzt")
check("Scanner" in scenes.MIX_BUTTONS and "KITT" not in scenes.MIX_BUTTONS, "Knopf heisst Scanner")
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "midimap.json")
    json.dump({"pads1": {"50": {"mix": "KITT"}}}, open(p, "w"))
    m, err = midi_ctl.load_map(p)
    check(not err and m["pads1"]["50"] == {"mix": "Scanner"}, "APC: alte Taste mit KITT wird Scanner")
    p = os.path.join(d, "lumimap.json")
    json.dump({"keys": {"40": {"mix": "KITT"}}}, open(p, "w"))
    m, err = lumi_ctl.load_map(p)
    check(m["keys"]["40"] == {"mix": "Scanner"}, "Lumi: alte Taste mit KITT wird Scanner")
    p = os.path.join(d, "fine.json")
    json.dump({"mx": {"KITT": {"size": 10}}}, open(p, "w"))
    check(fine.FineStore(p).get("mx", "Scanner")["size"] == 10.0, "Feinregler des alten KITT gelten fuer Scanner")
    p = os.path.join(d, "texts.json")
    json.dump({"mix:KITT": {"de": "Lauf"}}, open(p, "w"))
    check(texts.TextStore(p).merged()["mix:Scanner"][0] == "Lauf", "eigener Text des alten KITT gilt fuer Scanner")
    check(scenes.scene_from_dict({"name": "x", "mix": "kitt"}).mix == "scanner", "Szene mit altem Muster kitt")
rig, sh = build()
sh.command({"mix": "KITT"})
check(sh.snapshot()["mixbtn"] == "Scanner", "Befehl mit altem Namen waehlt Scanner")
finish("test_scanner_name")
