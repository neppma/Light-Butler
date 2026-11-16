"""Mixxx-App und Light-Butler Helfer nutzen dieselbe Ablage in ~/Light-Butler-Daten (Fehlerbericht 07.11.2026: der Helfer hatte eigene
Vorschlaege, Energie- und Tonart-Messungen in seinem Programmordner und mass 423 Lieder neu). Fruehere Daten des Helfers werden
einmal uebernommen, ohne etwas zu verlieren."""
import json
import os
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import auto_tag      # noqa: E402
import dupes         # noqa: E402
import energy_level  # noqa: E402
import folder_lib    # noqa: E402
import key_estimate  # noqa: E402
import mixxx_bridge as mb  # noqa: E402

data = os.environ["S2L_DATA"]
check(data.startswith(tempfile.gettempdir()) or "s2l_daten_" in data, "Tests schreiben nie in die echte Ablage")
for mod, sub in ((auto_tag.DATA_DIR, "autotag"), (energy_level.DATA_DIR, "energie"), (key_estimate.DATA_DIR, "tonart"),
                 (folder_lib.DATA_DIR, "ordner"), (os.path.dirname(dupes.KEPT_FILE), "doppelte")):
    check(mod == os.path.join(data, sub), f"{sub}: gemeinsame Ablage, nicht der Programmordner")

tmp = tempfile.mkdtemp(prefix="s2l_merge_")
helper, root = os.path.join(tmp, "Light-Butler-Helfer"), os.path.join(tmp, "Light-Butler")


def put(base, rel, content):
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content))


put(root, "autotag/vorschlaege.json", {"on": True, "items": {"/a": {"state": "offen", "t": 1}, "/b": {"state": "erledigt", "t": 1}}})
put(helper, "autotag/vorschlaege.json", {"on": False, "auto": True, "items": {"/a": {"state": "erledigt", "t": 2}, "/b": {"state": "offen", "t": 5},
                                                                              "/c": {"state": "offen", "t": 3}}})
put(root, "energie/merkmale.jsonl", '{"p": 1}\n{"p": 2}\n')
put(helper, "energie/merkmale.jsonl", '{"p": 2}\n{"p": 3}\n')
put(helper, "tonart/tonarten.jsonl", '{"k": 1}\n')
put(root, "doppelte/behalten.json", ["x|y"])
put(helper, "doppelte/behalten.json", ["x|y", "u|v"])
put(root, "energie/geschrieben.json", {"/a": 5})
put(helper, "energie/geschrieben.json", {"/a": 6, "/b": 7})
n = mb.merge_old_data(helper, root)
rd = lambda rel: open(os.path.join(root, rel), encoding="utf-8").read()   # noqa: E731
v = json.loads(rd("autotag/vorschlaege.json"))
check(v["items"]["/a"]["state"] == "erledigt" and v["items"]["/b"]["state"] == "erledigt" and "/c" in v["items"] and v["on"] and v["auto"],
      "Vorschlaege: erledigt geht vor offen, neue dazu, Schalter bleiben an")
check(rd("energie/merkmale.jsonl").splitlines() == ['{"p": 1}', '{"p": 2}', '{"p": 3}'], "Messwerte: fehlende Zeilen angehaengt, keine doppelt")
check(rd("tonart/tonarten.jsonl") == '{"k": 1}\n', "fehlende Datei: kopiert")
check(json.loads(rd("doppelte/behalten.json")) == ["x|y", "u|v"] and json.loads(rd("energie/geschrieben.json")) == {"/a": 5, "/b": 7},
      "alle behalten: vereinigt; geschrieben: vorhandene bleiben, neue dazu")
check(n >= 5 and os.path.isdir(os.path.join(helper, "autotag.uebernommen")) and not os.path.exists(os.path.join(helper, "autotag")),
      "alter Ordner danach umbenannt (nicht geloescht)")
check(mb.merge_old_data(helper, root) == 0, "zweiter Start: nichts mehr zu tun")
proj = os.path.join(tmp, "projekt")
put(proj, "autotag/vorschlaege.json", {"items": {}})
check(mb.merge_old_data(proj, root) == 0 and os.path.isdir(os.path.join(proj, "autotag")), "nur im Ordner des Helfers, nie anderswo")
finish("test_gemeinsame_ablage")
