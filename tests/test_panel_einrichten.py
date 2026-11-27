"""Einrichten ohne Datei (27.11.2026): Adresse des Art-Net-Gateways im Panel (fixtures_user.json, gilt nach dem
Neustart, fixtures.yaml bleibt) und Nanoleaf koppeln (Token vom Geraet, Panels lesen, nanoleaf.json schreiben, Token nie
im Panel). Alles in einem Testordner, mit nachgebautem Nanoleaf, ohne Netzwerk."""
import json
import os
import shutil
import tempfile

from _common import PI, build, check, finish

import fixture_edit as fe
import nanoleaf
import webpanel
from dmx import Rig

tmp = tempfile.mkdtemp(prefix="s2l_einr_")
try:
    shutil.copy(os.path.join(PI, "fixtures.yaml"), tmp)
    yml = os.path.join(tmp, "fixtures.yaml")
    raw_yaml = open(yml).read()
    rig = Rig(yml)
    base = rig.target
    check(rig.nano is None and rig.nano_path is None, "Testordner ohne nanoleaf.json")

    # ---- Art-Net-Gateway ----
    info = fe.artnet_info(rig)
    check(info == {"now": base, "next": base, "file": base}, "Anzeige: Adresse aus fixtures.yaml")
    for bad in ("1.2.3", "300.1.1.1", "a.b.c.d", "10.0.0.1; rm"):
        try:
            fe.cmd_artnet_target(rig, bad)
            check(False, f"abgelehnt: {bad}")
        except ValueError:
            check(True, f"abgelehnt: {bad}")
    check(fe.cmd_artnet_target(rig, "10.0.0.45") == "10.0.0.45", "neue Adresse gespeichert")
    check(fe.pending_restart(rig) and fe.artnet_info(rig)["next"] == "10.0.0.45" and rig.target == base, "gilt erst nach dem Neustart")
    check(json.load(open(os.path.join(tmp, "fixtures_user.json")))["artnet_target"] == "10.0.0.45", "steht in fixtures_user.json")
    check(open(yml).read() == raw_yaml, "fixtures.yaml unveraendert")
    rig2 = Rig(yml)
    check(rig2.target == "10.0.0.45" and "10.0.0.45" in rig2.targets() and not fe.pending_restart(rig2), "nach dem Neustart benutzt")
    fe.cmd_artnet_target(rig2, base)
    check(json.load(open(os.path.join(tmp, "fixtures_user.json")))["artnet_target"] == "" and Rig(yml).target == base,
          "gleiche Adresse wie in der Datei: Aenderung weg")

    # ---- Nanoleaf koppeln ----
    LAYOUT = {"positionData": [{"panelId": 7, "x": 0, "y": 0, "shapeType": 0}, {"panelId": 9, "x": 100, "y": 0, "shapeType": 0},
                               {"panelId": 1, "x": 50, "y": 50, "shapeType": 12}]}

    class FakeNano:
        fail = False

        def __init__(self, host, token, port=16021, timeout=3.0):
            self.host, self.token = host, token

        def info(self):
            if FakeNano.fail:
                raise nanoleaf.NanoleafError("HTTP 401 bei GET /")
            return {"name": "Testpanels", "model": "NL22", "firmwareVersion": "1.0"}

        def layout(self):
            return LAYOUT

    TOKEN = "PairTokenAbc1234567890xyz"

    def not_ready(host):
        raise ValueError("Der Nanoleaf ist nicht im Koppel-Modus")

    for bad, post, why in (("10.0.0.300", lambda h: TOKEN, "falsche IP"), ("10.0.0.60", not_ready, "nicht im Koppel-Modus"),
                           ("10.0.0.60", lambda h: "x/../y", "ungueltiger Schluessel")):
        try:
            fe.cmd_nano_pair(rig2, bad, post=post, client=FakeNano)
            check(False, f"abgelehnt: {why}")
        except ValueError:
            check(True, f"abgelehnt: {why}")
    FakeNano.fail = True
    try:
        fe.cmd_nano_pair(rig2, "10.0.0.60", post=lambda h: TOKEN, client=FakeNano)
        check(False, "Panels nicht lesbar: abgelehnt")
    except ValueError:
        check(True, "Panels nicht lesbar: abgelehnt")
    FakeNano.fail = False
    nfile = os.path.join(tmp, "nanoleaf.json")
    check(not os.path.exists(nfile), "bei Fehlern nichts gespeichert")
    name, n = fe.cmd_nano_pair(rig2, "10.0.0.60", post=lambda h: TOKEN, client=FakeNano)
    check(name == "Testpanels" and n == 2, "gekoppelt: 2 leuchtende Panels (Controller zaehlt nicht)")
    cfg = json.load(open(nfile))
    check(cfg["host"] == "10.0.0.60" and cfg["token"] == TOKEN and cfg["protocol"] == "v1", "nanoleaf.json geschrieben")
    check(fe.pending_restart(rig2), "gilt nach dem Neustart")
    rig3 = Rig(yml)
    check(rig3.nano is not None and len(rig3.group("nano")) == 2 and any(t.startswith("nanoleaf:10.0.0.60") for t in rig3.targets()),
          "nach dem Neustart: Nanoleaf-Panels da")
    cfg["fps"] = 15
    json.dump(cfg, open(nfile, "w"))
    fe.cmd_nano_pair(rig3, "10.0.0.61", post=lambda h: "NochmalToken1234567890", client=FakeNano)
    cfg = json.load(open(nfile))
    check(cfg["host"] == "10.0.0.61" and cfg["token"] == "NochmalToken1234567890" and cfg["fps"] == 15, "neu koppeln: eigene Einstellungen bleiben")

    # ---- Panel ----
    page = webpanel.make_page()
    check('id="artip"' in page and "c({artnet_target:" in page and "c({nano_pair:" in page, "Panel: Felder unter Verbindungen")
    rig_s, sh = build(seed=3)
    snap = sh.snapshot()
    check(set(snap["artnet"]) == {"now", "next", "file"}, "Status meldet das Art-Net-Gateway")
    check(TOKEN not in json.dumps(snap, default=str) and "NochmalToken" not in json.dumps(snap, default=str), "Token nie im Status")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

finish("test_panel_einrichten")
