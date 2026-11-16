"""Szene Austria (rot-weiss-rot, Effektband-Preset 1 "Austria"): Die Szenen-Automatik waehlt sie nie von selbst, ausser
beim Drop eines Liedes aus Mixxx mit "Austria" oder "Oesterreich" im Titel - dann immer. Von Hand bleibt sie waehlbar."""
from _common import build, check, finish, Clock

import show as sw

rig, sh = build(strobe=True, pilot=True)
names = [sc.name for _, sc in sh._sa_candidates()]
check("Austria" not in names and names, "Szenen-Automatik: Austria nicht unter den Kandidaten")
check(sw.is_austria(next(s for s in sh.scene_defs if s.name == "Austria")), "Szene Austria erkannt (Farbe/Preset 1)")

picked = set()
for i in range(400):
    for key in (0, 1, 2, 3, "drop"):
        sc = sh._sa_pick(key)
        picked.add(sc.name if sc else None)
check("Austria" not in picked, "auch bei vielen Zuegen nie Austria")


def drop_scene(title):
    rig, sh = build(strobe=True, seed=2, pilot=True)
    sh.cfg.set("sa_on", 1)
    sh.cfg.set("sa_drop", 1)
    sh.mx = {"plan": True, "deck": 1, "title": title}
    sh.sc, sh.sa = None, None
    sh._scene_auto(1000.0, False, True)                      # Drop beginnt
    return sh.sc.name if sh.sc else None, sh


name, sh2 = drop_scene("Rainhard Fendrich - I Am From Austria")
check(name == "Austria", f"Drop im Austria-Lied: Szene Austria ({name})")
eb = sh2.presets[0]
Clock(sh2).run(0.5)
check(int(eb.values.get("preset", 0)) == 1, "dabei Effektband-Preset 1 (Austria)")
name, _ = drop_scene("STS - Großvater (Österreich-Version)")
check(name == "Austria", "Titel mit Österreich: ebenso")
name, _ = drop_scene("Charlotte de Witte - Doppler")
check(name not in (None, "Austria"), f"Drop in einem anderen Lied: eine andere Szene ({name})")

rig, sh = build(pilot=True)
sh.mx = {"plan": True, "deck": 1, "title": "I Am From Austria"}
sh.sc, sh.sa = None, None
sh._scene_auto(1000.0, True, False)                          # nur Phrase, kein Drop
check(sh.sc is None or sh.sc.name != "Austria", "im Austria-Lied ohne Drop: keine Austria-Szene")
sh.pilot = False
sh.command({"scene": "Austria"})
check(sh.sc is not None and sh.sc.name == "Austria", "von Hand: Austria waehlbar wie bisher")

# ---- Fehler 01.11.2026: Titel aus der Mixxx-Datenbank mit zerlegtem "Ö" (NFD, wie macOS es speichert) -------------
import unicodedata    # noqa: E402

nfd = unicodedata.normalize("NFD", "S.T.S. - I Bin Aus Österreich")
check(nfd != "S.T.S. - I Bin Aus Österreich", "Testtitel ist wirklich zerlegt (NFD)")
name, _ = drop_scene(nfd)
check(name == "Austria", "Drop in 'I Bin Aus Österreich' (zerlegtes Ö): Austria")

# ---- Austria auch an jedem Hotcue eines Austria-Liedes ---------------------------------------------------------------
def cue_scene(title, running=None):
    rig, sh = build(strobe=True, seed=3, pilot=True)
    sh.cfg.set("sa_on", 1)
    sh.mx = {"plan": True, "deck": 1, "title": title}
    sh.sc, sh.sa = None, None
    if running:                                                # eine andere automatische Szene laeuft gerade
        sc = next(s for s in sh.scene_defs if s.name == running)
        sh.sc, sh.sa = sc.copy(), {"name": running, "until_step": sh.step + 999, "drop": False}
    sh.cue_now = True
    sh._scene_auto(1000.0, True, False)
    return (sh.sc.name if sh.sc else None), sh


name, sh3 = cue_scene(nfd)
check(name == "Austria" and sh3.sa["until_step"] == sh3.step + sh3.bar_len * int(sh3.cfg["sa_bars"]),
      "Hotcue im Austria-Lied: Austria fuer 'hoechstens Takte'")
other = sh3._sa_candidates()[0][1].name
name, _ = cue_scene("I Am From Austria", running=other)
check(name == "Austria", f"Hotcue: ersetzt eine laufende automatische Szene ({other})")
name, _ = cue_scene("Charlotte de Witte - Doppler")
check(name != "Austria", f"Hotcue in einem anderen Lied: kein Austria ({name})")
rig, sh4 = build(pilot=True)
sh4.cfg.set("sa_on", 0)
sh4.mx = {"plan": True, "deck": 1, "title": "I Am From Austria"}
sh4.sc, sh4.sa, sh4.cue_now = None, None, True
sh4._scene_auto(1000.0, True, False)
check(sh4.sc is None, "Szenen-Automatik aus: auch im Austria-Lied nichts")
finish("test_austria")
