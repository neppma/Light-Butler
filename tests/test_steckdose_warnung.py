"""Rote Warnung oben im Panel: ist ein Geraet mit eigener HomeMatic-Steckdose (homematic.yaml, ccu.power_for, eine id
oder eine Liste) nicht erreichbar, schaltet ein Tipp auf seinen Namen nach Rueckfrage die Steckdose(n) ein
(Nanoleaf; Effektband mit Effektband 1 und 2)."""
import os
import subprocess
import tempfile

import yaml

from _common import PI, build, check, finish

import webpanel

cfg = yaml.safe_load(open(os.path.join(PI, "homematic.beispiel.yaml"), encoding="utf-8"))
check(cfg["ccu"].get("power_for") == {"Nanoleaf": "nanoleaf", "Effektband": ["effektband1", "effektband2"]},
      "homematic.yaml: Nanoleaf und Effektband (zwei Steckdosen)")
check(cfg["ccu"].get("power_watch") == {"Derby und Bar": "derby_bar", "Musik": "musik"},
      "homematic.yaml: Derby und Bar sowie Musik werden ueber ihre Steckdose ueberwacht")
ids = {d["id"] for d in cfg["devices"]}
check({"nanoleaf", "effektband1", "effektband2", "derby_bar", "musik"} <= ids, "alle Steckdosen sind eingetragen")

rig, sh = build()
check(sh.snapshot()["power_for"] == {}, "ohne HomeMatic (Simulator): nichts antippbar")


class FakeHome:
    ccu = {"power_for": {"Nanoleaf": "nanoleaf", "Effektband": ["effektband1", "effektband2"], "Theke": "fehlt",
                         "Nebel": "nebelmaschine", "Licht": "licht_wz"},
           "power_watch": {"Derby und Bar": "derby_bar", "Musik": "musik"},
           "fog_power": "nebelmaschine"}
    by_id = {"nanoleaf": {"id": "nanoleaf", "label": "Nanoleaf", "kind": "switch"},
             "effektband1": {"id": "effektband1", "label": "Effektband 1", "kind": "switch"},
             "effektband2": {"id": "effektband2", "label": "Effektband 2", "kind": "switch"},
             "nebelmaschine": {"id": "nebelmaschine", "label": "Nebelmaschine (Strom)", "kind": "switch"},
             "licht_wz": {"id": "licht_wz", "label": "Wohnzimmerlicht", "kind": "dimmer"},
             "derby_bar": {"id": "derby_bar", "label": "Derby und Bar", "kind": "switch"},
             "musik": {"id": "musik", "label": "Musik", "kind": "switch"}}
    state = {"nanoleaf": {"on": False}, "effektband1": {"on": True}, "effektband2": {"on": False},
             "derby_bar": {"on": False, "ok": True}, "musik": {"on": None, "ok": False}}
    calls = []

    def status(self):
        return {}

    def set(self, dev_id, on=None, level=None, wait=False):
        self.calls.append((dev_id, on))


sh.home = FakeHome()
pf = sh.snapshot()["power_for"]
check(set(pf) == {"Nanoleaf", "Effektband", "Derby und Bar", "Musik"},
      "nur gueltige Steckdosen; nie die Nebelmaschine, keine Dimmer, keine unbekannten")
check(pf["Effektband"] == {"ids": ["effektband1", "effektband2"], "label": "Effektband 1, Effektband 2", "on": False, "watch": False},
      "Effektband: beide Steckdosen, 'an' nur wenn beide an")
check(sh.snapshot()["power_off"] == ["Derby und Bar"], "Steckdose sicher aus: 'Derby und Bar aus' (Musik unbekannt: keine Warnung)")
FakeHome.state["musik"] = {"on": False, "ok": True}
check(sh.snapshot()["power_off"] == ["Derby und Bar", "Musik"], "Musikanlage aus: Warnung")
FakeHome.state["derby_bar"] = {"on": True, "ok": True}
check(sh.snapshot()["power_off"] == ["Musik"], "Derby und Bar wieder an: Warnung weg")
sh.command({"power_on": "Musik"})
check(sh.home.calls == [("musik", True)], "Tipp auf 'Musik aus' schaltet die Musikanlage ein")
sh.home.calls.clear()
sh.command({"power_on": "Effektband"})
check(sh.home.calls == [("effektband1", True), ("effektband2", True)], "Tipp auf Effektband schaltet beide ein")
sh.home.calls.clear()
sh.command({"power_on": "Nanoleaf"})
check(sh.home.calls == [("nanoleaf", True)], "Tipp auf Nanoleaf schaltet seine Steckdose ein")
try:
    sh.command({"power_on": "Nebel"})
    check(False, "Nebelmaschine abgelehnt")
except ValueError:
    check(sh.home.calls == [("nanoleaf", True)], "Nebelmaschine abgelehnt")

p = webpanel.make_page()
check("(S.power_for||{})[n]?'<u class=\"wc pwr\" data-pw=\"'+esc(n)+'\"" in p, "Name in der Warnung antippbar, wenn eine Steckdose da ist")
check("wr.querySelectorAll('[data-pw]').forEach(e=>e.onclick=()=>powerOn(e.dataset.pw))" in p, "Tipp ruft powerOn")
check("if(confirm(TXT.pwr_q[LANG==='de'?0:1]" in p and "c({power_on:n})" in p, "mit Rueckfrage, schaltet nur ein")
check("const poff=(S.power_off||[]).filter(n=>!down.includes(n)),warnl=down.concat(poff);" in p and "tr('pwr_off')" in p,
      "Panel: Steckdose aus erscheint in der Hinweiszeile als '<Name> aus'")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_steckdose_warnung")
