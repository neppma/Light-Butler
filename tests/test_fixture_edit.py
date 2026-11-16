"""Fixture-Editor: Aenderungen in fixtures_user.json, Pruefungen, Export. Arbeitet in einem Temp-Ordner."""
import os
import shutil
import sys
import tempfile
import yaml
from _common import PI, check, finish

tmp = tempfile.mkdtemp()
shutil.copy(os.path.join(PI, "fixtures.yaml"), tmp)
import fixture_edit as fe                    # noqa: E402
from dmx import Rig                          # noqa: E402

rig = Rig(os.path.join(tmp, "fixtures.yaml"))
check(rig.user is not None, "Rig laedt ohne fixtures_user.json")
name, warn, live = fe.cmd_fixture_save(rig, {"name": "docooler_2", "label": "Docooler Test", "nr": 2, "address": 21, "group": "bars"})
check(live and rig["docooler_2"].extra["label"] == "Docooler Test", "Name aendern wirkt sofort")
for bad, text in (({"name": "eyes", "label": "Eyes", "nr": 12, "address": 201, "group": "spot"}, "unpassende Gruppe"),
                  ({"name": "eyes", "label": "Eyes", "nr": 12, "address": 600, "group": "fx"}, "Adresse ausserhalb"),
                  ({"name": "eyes", "label": " ", "nr": 12, "address": 201, "group": "fx"}, "leerer Name"),
                  ({"name": "theke", "label": "T", "nr": 14, "address": 421, "group": "ambient", "target": "300.1.1.1"}, "falsche IP")):
    try:
        fe.cmd_fixture_save(rig, bad)
        check(False, f"{text} muss abgelehnt werden")
    except ValueError:
        check(True, f"{text} wird abgelehnt")
fe.cmd_fixture_save(rig, {"new": True, "type": "led_4in1_rgbuv", "label": "Wash Neu", "nr": 19, "address": 161 + 20, "group": "wash"})
fe.cmd_type_save(rig, {"name": "mein_par_6ch", "channels": [{"param": "dimmer", "default": 255}, {"param": "r"}, {"param": "g"},
                                                            {"param": "b"}, {"param": "mode", "max": 10}, {"param": "speed"}]})
fe.cmd_fixture_delete(rig, "par")
check(fe.pending_restart(rig), "neue und entfernte Fixtures brauchen einen Neustart")
text = fe.export_yaml(fe.apply_user(rig.base_cfg, rig.user))
y = yaml.safe_load(text)
names = [f["name"] for f in y["fixtures"]]
check("wash_neu" in names and "par" not in names and "mein_par_6ch" in y["types"] and "user_added" not in text,
      "Export-YAML enthaelt die Aenderungen und ist gueltig")
rig2 = Rig(os.path.join(tmp, "fixtures.yaml"))
check("wash_neu" in rig2.by_name and "par" not in rig2.by_name, "nach dem Neuladen gelten die Aenderungen")
shutil.rmtree(tmp)
finish("test_fixture_edit")
