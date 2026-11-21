"""Pixel-Matrix (21.11.2026): antwortet sie nicht (aus, ausgesteckt), sendet der Pi nichts und rechnet nur fuer die Vorschau."""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import DT, build, check, finish  # noqa: E402

import settings                                  # noqa: E402
import webpanel                                  # noqa: E402
import wled_matrix as wm                         # noqa: E402

cfg = settings.Settings(os.devnull)
cfg.set("pm_on", 1)
mt = wm.Matrix(None, dry=False)
mt.host = "192.0.2.10"
sent = []
mt.sender = types.SimpleNamespace(send=lambda d: sent.append(len(d)), close=lambda: None, sent=0, errors=0)
renders = []
orig = mt.fx.render
mt.fx.render = lambda s: (renders.append(1), orig(s))[1]
S = {"dt": DT, "bpm": 120, "state": "normal", "tier": 1, "hue": 0.3}
for i in range(10):
    mt.tick(dict(S, t=i * DT), cfg)
check(len(sent) == 10, "ungeprueft: sendet")
mt.set_reachable(False)
check(mt.sender is None, "antwortet nicht: Socket zu")
n, r = len(sent), len(renders)
for i in range(40):
    mt.tick(dict(S, t=1 + i * DT), cfg)
check(len(sent) == n and len(renders) == r, "antwortet nicht: kein Senden, kein Rechnen")
mt.preview_until = 1e9
mt.tick(dict(S, t=3.0), cfg)
check(len(renders) == r + 1 and len(sent) == n, "Seite offen: Vorschau rechnet, sendet aber nicht")
check(mt.info(cfg, 3.0)["reach"] is False, "Seite sieht: antwortet nicht")
mt.preview_until = 0
mt.set_reachable(True)
got = []
wm.DdpSender = lambda host, port: types.SimpleNamespace(send=lambda d: got.append(host), close=lambda: None, sent=0, errors=0)
mt.tick(dict(S, t=4.0), cfg)
check(got == ["192.0.2.10"], "wieder da: sendet sofort weiter")
mt.set_reachable(False)
mt.set_host("192.0.2.11")
check(mt.reachable is None, "neue Adresse: gleich versuchen")

# _watch_hosts: prueft die Matrix nur, wenn Senden an ist
rig, sh = build(seed=3)
sh.matrix = wm.Matrix(None, dry=False)
sh.matrix.host = "192.0.2.10"
asked = []
orig_r, orig_sleep = webpanel._reachable, webpanel.time.sleep


class Stop(Exception):
    pass


def one_round(on):
    sh.cfg.set("pm_on", on)
    asked.clear()

    def stop(_):
        raise Stop
    webpanel._reachable = lambda ip, port: (asked.append(ip), False)[1]
    webpanel.time.sleep = stop
    try:
        webpanel._watch_hosts(sh)
    except Stop:
        pass
    finally:
        webpanel._reachable, webpanel.time.sleep = orig_r, orig_sleep


one_round(1)
check("192.0.2.10" in asked and sh.reach.get("Pixel-Matrix") is False and sh.matrix.reachable is False,
      "Senden an: Matrix wird geprueft und als fehlend gemeldet")
one_round(0)
check("192.0.2.10" not in asked and "Pixel-Matrix" not in sh.reach and sh.matrix.reachable is None,
      "Senden aus: keine Pruefung, keine Warnung")
finish("test_matrix_erreichbar")
