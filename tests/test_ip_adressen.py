"""IP-Adressen im Panel: WLED-Ziel-IP und Nanoleaf-IP anzeigen und aendern. Die Nanoleaf-IP kommt in
fixtures_user.json, nanoleaf.json (mit dem Token) bleibt unveraendert. Alles in einem Testordner, ohne echte Dateien."""
import json
import os
import shutil
import tempfile

from _common import PI, check, finish

import fixture_edit as fe
import webpanel
from dmx import Rig

tmp = tempfile.mkdtemp(prefix="s2l_ip_")
try:
    shutil.copy(os.path.join(PI, "fixtures.yaml"), tmp)
    yml = os.path.join(tmp, "fixtures.yaml")
    nfile = os.path.join(tmp, "nanoleaf.json")
    nano_cfg = {"host": "10.0.0.33", "token": "TESTTOKEN-nicht-echt",
                "panels": [{"id": 11, "x": 0.2, "y": 0.5}, {"id": 22, "x": 0.8, "y": 0.5}]}
    with open(nfile, "w") as f:
        json.dump(nano_cfg, f)
    raw = open(nfile).read()

    rig = Rig(yml)
    check(rig.nano["host"] == "10.0.0.33" and rig.nano_file_host == "10.0.0.33", "Nanoleaf-IP aus nanoleaf.json geladen")
    lst = webpanel.fixtures_info(rig)
    nano = next(f for f in lst if f["name"] == "nanoleaf")
    check(nano["nano_host"] == "10.0.0.33", "Fixture-Liste zeigt die Nanoleaf-IP")
    check("TESTTOKEN" not in json.dumps(lst), "Token erscheint nie in der Fixture-Liste")
    theke = next(f for f in lst if f["name"] == "theke")
    check(theke["own_target"] == "192.168.1.30", "Fixture-Liste zeigt die WLED-IP der Theke")

    # Nanoleaf-IP aendern
    for bad in ("10.0.0", "300.1.1.1", "abc"):
        try:
            fe.cmd_nano_host(rig, bad)
            check(False, f"falsche IP {bad} abgelehnt")
        except ValueError:
            check(True, f"falsche IP {bad} abgelehnt")
    fe.cmd_nano_host(rig, "10.0.0.44")
    check(fe.pending_restart(rig), "neue Nanoleaf-IP: Neustart offen")
    check(open(nfile).read() == raw, "nanoleaf.json bleibt unveraendert")
    user = json.load(open(os.path.join(tmp, "fixtures_user.json")))
    check(user.get("nano_host") == "10.0.0.44", "neue IP steht in fixtures_user.json")
    check("TESTTOKEN" not in json.dumps(user), "Token steht nicht in fixtures_user.json")

    rig2 = Rig(yml)                                       # wie nach dem Neustart
    check(rig2.nano["host"] == "10.0.0.44", "nach dem Neustart gilt die neue IP")
    check(all(f.target == "nanoleaf:10.0.0.44" for f in rig2.fixtures if f.group == "nano"), "Panels senden an die neue IP")
    check(rig2.nano["token"] == "TESTTOKEN-nicht-echt", "Token kommt weiter aus nanoleaf.json")
    check(not fe.pending_restart(rig2), "kein Neustart mehr offen")

    # zurueck auf die Adresse aus nanoleaf.json (leer)
    fe.cmd_nano_host(rig2, "")
    rig3 = Rig(yml)
    check(rig3.nano["host"] == "10.0.0.33", "leer = wieder die IP aus nanoleaf.json")

    # WLED-IP aendern (gab es schon, Fixture-Editor)
    fe.cmd_fixture_save(rig3, {"name": "theke", "target": "192.168.1.31"})
    rig4 = Rig(yml)
    check(rig4.by_name["theke"].target == "192.168.1.31", "WLED-IP der Theke geaendert")

    # Panel: Anzeige und Eingabe vorhanden
    page = webpanel.make_page()
    check("function nanoForm(f)" in page and "c({nano_host:" in page, "Panel hat ein Eingabefeld fuer die Nanoleaf-IP")
    check("S.reach_ip" in page, "Verbindungen zeigen die IP-Adressen")

    # Nanoleaf-Token: nur Eingabe, nie Anzeige, vorher am (nachgebauten) Nanoleaf geprueft
    import nanoleaf

    class FakeNano:
        answer = "ok"                                   # ok | 401 | weg
        seen = []

        def __init__(self, host, token, port=16021, timeout=3.0):
            FakeNano.seen.append((host, token))

        def info(self):
            if FakeNano.answer == "401":
                raise nanoleaf.NanoleafError("HTTP 401 bei GET /")
            if FakeNano.answer == "weg":
                raise nanoleaf.NanoleafError("10.0.0.33 nicht erreichbar (timeout)")
            return {"name": "Nanoleaf"}

    rig5 = Rig(yml)
    info = next(f for f in webpanel.fixtures_info(rig5) if f["name"] == "nanoleaf")
    check(info["nano_token_set"] is True and "TESTTOKEN" not in json.dumps(info), "Panel sieht nur 'Token hinterlegt', nie den Token")
    for bad in ("kurz", "abc def ghi jkl mno", "abcdefghijklmnop/../x", "abcdefghijklmnop?a=1"):
        try:
            fe.cmd_nano_token(rig5, bad, client=FakeNano)
            check(False, f"ungueltiger Token {bad!r} abgelehnt")
        except ValueError:
            check(True, f"ungueltiger Token {bad!r} abgelehnt")
    before = open(nfile).read()
    FakeNano.answer = "401"
    try:
        fe.cmd_nano_token(rig5, "FalscherToken12345678", client=FakeNano)
        check(False, "vom Nanoleaf abgelehnter Token wird nicht gespeichert")
    except ValueError as e:
        check(open(nfile).read() == before and "FalscherToken" not in str(e),
              "vom Nanoleaf abgelehnter Token wird nicht gespeichert (Meldung ohne Token)")
    check(not fe.pending_restart(rig5), "nach Ablehnung kein Neustart offen")
    FakeNano.answer = "ok"
    check(fe.cmd_nano_token(rig5, "NeuerToken1234567890ABCD", client=FakeNano) is True, "gueltiger Token bestaetigt")
    saved = json.load(open(nfile))
    check(saved["token"] == "NeuerToken1234567890ABCD", "Token in nanoleaf.json gespeichert")
    check(saved["host"] == "10.0.0.33" and saved["panels"] == nano_cfg["panels"], "uebriger Inhalt von nanoleaf.json bleibt")
    check(FakeNano.seen[-1][0] == "10.0.0.33", "Pruefung an der eingestellten Nanoleaf-IP")
    check(fe.pending_restart(rig5), "neuer Token: Neustart offen")
    user = json.load(open(os.path.join(tmp, "fixtures_user.json")))
    check("NeuerToken" not in json.dumps(user), "Token steht nicht in fixtures_user.json")
    info = next(f for f in webpanel.fixtures_info(rig5) if f["name"] == "nanoleaf")
    check(info["nano_token_changed"] and "NeuerToken" not in json.dumps(info), "Panel zeigt 'neu gespeichert', nicht den Token")
    FakeNano.answer = "weg"
    check(fe.cmd_nano_token(rig5, "NochEinToken1234567890", client=FakeNano) is False, "Nanoleaf aus: ungeprueft gespeichert")
    check(Rig(yml).nano["token"] == "NochEinToken1234567890", "nach dem Neustart gilt der neue Token")
    check('type="password"' in page and "c({nano_token:v})" in page, "Panel: verdecktes Eingabefeld fuer den Token")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

finish("test_ip_adressen")
