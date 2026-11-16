"""DMX-Debugger (vom Nutzer am 03.11.2026 ausdruecklich verlangt, ohne Sperren): roh auf die DMX-Kette, aber mit Totmann,
BLACKOUT geht vor, nach dem Start aus, WLED und Nanoleaf unberuehrt."""
import os
import tempfile
import time

from _common import PI, Clock, build, check, ch, finish

import dmx
import webpanel
from dmx_debug import DmxDebug, TIMEOUT_S
from showman.api import ShowManager


class Rec:
    def __init__(self):
        self.sent = []

    def send(self, d):
        self.sent.append(bytes(d))

    def close(self):
        pass


clk = [100.0]
d = DmxDebug(lambda: clk[0])
check(d.frame() is None and not d.armed, "Start: aus")
check(d.set_values({181: 255}) is False and d.values()[180] == 0, "aus: Setzen wirkt nicht")
d.arm(True)
check(d.frame() == bytes(512), "Einschalten: alles 0")
d.set_values({"181": 255, 182: 300, 283: -5})
f = d.frame()
check(f[180] == 255 and f[181] == 255 and f[282] == 0, "Werte gesetzt und begrenzt")
try:
    d.set_values({600: 1})
    check(False, "Kanal 600 abgelehnt")
except ValueError:
    check(True, "Kanal 600 abgelehnt")
d.set_hold(True)
check(d.frame() == bytes(512) and d.values()[180] == 255, "Kurz dunkel: alles 0, Werte bleiben gemerkt")
d.set_values({182: 77})
check(d.frame() == bytes(512), "auch beim Verstellen waehrend des Haltens bleibt es dunkel")
d.set_hold(False)
f = d.frame()
check(f[180] == 255 and f[181] == 77, "Loslassen: die eingestellten Werte kommen zurueck")
d.set_values({182: 255})
d.set_hold(True)
clk[0] += TIMEOUT_S + 0.1
check(d.frame() is None and d.hold is False, "Totmann auch beim Halten: aus und danach nichts haengt")
d.arm(True)
d.set_values({181: 255, 182: 255})
d.arm(False)
d.set_hold(True)
check(d.hold is False, "ausgeschaltet: Taster wirkungslos")
d.arm(True)
d.set_values({"181": 255, 182: 300})
clk[0] += TIMEOUT_S - 0.1
d.beat()
clk[0] += TIMEOUT_S - 0.1
check(d.frame() is not None, "Seite meldet sich: bleibt an")
clk[0] += TIMEOUT_S + 0.1
check(d.frame() is None and not d.armed, "Totmann: ohne Meldung aus")
d.arm(True)
check(d.values()[180] == 0, "nach Totmann wieder alles 0, nichts bleibt an")

# Durch die echte Ausgabe
rig, sh = build(strobe=False)
recs = {}


def mk(ip):
    recs[ip] = Rec()
    return recs[ip]


out = dmx.Output(rig, mk)
sh.output = out
c = Clock(sh)
mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_dbg_"))
check(mgr.op({"op": "debug_state"})["armed"] is False, "Start ueber das Panel: aus")
out.start()
try:
    c.run(0.3)
    r = mgr.op({"op": "debug_arm", "on": True})
    check(r["armed"] and sh.snapshot()["dmx_debug"], "einschalten, Panel zeigt es")
    mgr.op({"op": "debug_set", "values": {181: 255, 182: 80, 281: 150, 13: 250, 162: 77}})
    time.sleep(0.15)
    sh.update(c.t)
    time.sleep(0.15)
    last = recs[rig.target].sent[-1]
    check(last[180] == 255 and last[181] == 80, "Laser-Kanaele roh auf dem Bus")
    check(last[280] == 150 and last[12] == 250, "auch Hazer und Reset: allgemeiner Debugger wie verlangt")
    check(sum(1 for v in last if v) == 5, "alle anderen Kanaele 0, die Show ruht auf der DMX-Kette")
    check(rig["laser"].laser_unlock is False and ch(rig, "laser", "power") == 0, "der Rig selbst bleibt gesperrt: Aus heisst sofort sicher")
    wled = rig["theke"].target
    check(wled in recs and recs[wled].sent and bytes(recs[wled].sent[-1]) != last, "WLED bleibt bei der Show")
    check(mgr.op({"op": "debug_beat"})["armed"], "Meldung der Seite")
    r = mgr.op({"op": "debug_hold", "on": True})
    sh.update(c.t)
    time.sleep(0.15)
    check(r["hold"] and recs[rig.target].sent[-1] == bytes(512) and r["values"][180] == 255, "Taster am Bus: wirklich alle Kanaele 0, Regler bleiben")
    r = mgr.op({"op": "debug_hold", "on": False})
    sh.update(c.t)
    time.sleep(0.15)
    check(not r["hold"] and recs[rig.target].sent[-1][180] == 255, "Loslassen: Werte wieder auf dem Bus")
    sh.command({"blackout": True})
    sh.update(c.t + 0.1)
    time.sleep(0.15)
    sh.update(c.t + 0.2)
    time.sleep(0.15)
    last = recs[rig.target].sent[-1]
    check(not out.debug.armed and last[180] == 0 and last[280] == 0 and last[181] == 0 and last[300] == 0, "BLACKOUT: Debug aus, Laser 0")
    try:
        mgr.op({"op": "debug_arm", "on": True})
        check(False, "bei BLACKOUT nicht einschaltbar")
    except ValueError:
        check(True, "bei BLACKOUT nicht einschaltbar")
    sh.command({"blackout": False})
    mgr.op({"op": "debug_arm", "on": True})
    mgr.op({"op": "debug_set", "values": {181: 255}})
    mgr.op({"op": "debug_arm", "on": False})
    sh.update(c.t + 0.3)
    time.sleep(0.15)
    check(recs[rig.target].sent[-1][180] == 0, "Ausschalten: sofort wieder die Show, Laser gesperrt")
    mgr.op({"op": "debug_arm", "on": True})
    mgr.op({"op": "debug_set", "values": {181: 255}})
finally:
    out.stop()
check(not out.debug.armed and recs[rig.target].sent[-1][180] == 0, "Dienstende: aus, Laser 0")

html = open(os.path.join(PI, "static", "sm", "debug.html"), encoding="utf-8").read()
js = open(os.path.join(PI, "static", "sm", "debug.js"), encoding="utf-8").read()
check("Ohne Sperren" in html and "/static/sm/debug.js" in html, "Seite warnt deutlich")
check('id="hold"' in html and "debug_hold" in js and "lostpointercapture" in js, "Taster Kurz dunkel, auch bei verlorenem Finger")
check("debug_beat" in js and "sendBeacon" in js and "Alle Kanäle 1 bis 512" in js, "Seite: Totmann, Abmelden beim Schliessen, alle Kanaele")
p = webpanel.make_page()
check('href="/dmx-debug"' in p and "S.dmx_debug" in p, "Panel: Link und Warnung")
finish("test_dmx_debug")
