"""Showmanager: Laser und Nebel in Shows (vom Nutzer am 03.11.2026 freigegeben, auch beim Start aus Mixxx). Nur mit Hakerl, nur
waehrend die Musik wirklich laeuft, sofort aus bei Pause, Springen, Stop, BLACKOUT, FREEZE und ohne Meldung der Zeitquelle."""
import os
import tempfile

from _common import DT, Clock, build, check, ch, finish, ktv6_config

from mixxx_link import MixxxLink
from showman import timeline as tl
from showman.api import ShowManager
from showman.engine import MIXXX, LIVE_S


def clip(t, d, pattern, **p):
    return {"id": f"c{t}{pattern}", "t": t, "d": d, "pattern": pattern, "p": p}


def laser_track(fx, *clips):
    return {"target": {"fixture": fx}, "attr": "laser", "keys": [], "clips": list(clips)}


def setup(laser=1.0, fog=1.0, strobe=True, mixxx=None, config=None):
    rig, sh = build(strobe=strobe, mixxx=mixxx, config=config)
    mgr = ShowManager(sh, tempfile.mkdtemp(prefix="s2l_ln_"))
    sh.cfg.set("sm_laser", laser)
    sh.cfg.set("sm_fog", fog)
    return rig, sh, mgr


def doc(tracks, duration=60.0):
    d = tl.new_show("LN")
    d.update(duration=duration, bpm=120.0, tracks=tracks)
    return d


BEAMS = {"eyes": ["laser_red1", "laser_red2", "laser_green", "laser_blue"], "derby": ["laser_red", "laser_green", "laser_red8"], "laser": ["power"]}
ALL = [laser_track(f, clip(0, 60, "laser")) for f in BEAMS]


def lit(rig, fx):
    return any(ch(rig, fx, p) for p in BEAMS[fx])


def all_off(rig):
    """Alle Laser-Kanaele wie im gesperrten Zustand."""
    f = rig.render()
    return all(f[x.address - 1 + x.map[p] - 1] == x.rest.get(p, 0) for x in rig.fixtures if x.laser_params for p in x.laser_params)


def start(tracks, owner=None, **kw):
    rig, sh, mgr = setup(**kw)
    e = mgr.engine
    c = Clock(sh)
    e.load(doc(tracks))
    e.play(c.t, 0.0, True, owner)
    return rig, sh, mgr, e, c


# ---- Master-Zeile -------------------------------------------------------------------------------------------------------
print("Master-Zeile")


def master_track(*keys):
    return {"target": {"master": True}, "attr": "master", "keys": [{"t": t, "v": v, "e": "linear"} for t, v in keys], "clips": [clip(0, 9, "blink")]}


DIM = {"target": {"fixture": "rgbuv_7"}, "attr": "dimmer", "keys": [{"t": 0, "v": 200, "e": "constant"}], "clips": []}
n = tl.normalize(doc([master_track((0, 255), (10, 0)), master_track((0, 1))]))
check([t["attr"] for t in n["tracks"]] == ["master"] and n["tracks"][0]["clips"] == [] and len(n["tracks"][0]["keys"]) == 2, "nur eine Master-Spur, nur Keyframes")
check(tl.normalize(doc([master_track()]))["tracks"] == [], "ohne Keyframes keine Spur in der Datei")
check(tl.normalize(n) == n, "bleibt beim Speichern gleich")
rig, sh, mgr, e, c = start([DIM])
c.run(0.5)
plain = ch(rig, "rgbuv_7", "r")
check(plain > 0 and e.compiled.master_at(5.0) == 1.0, "ohne Master: unveraendert")
rig, sh, mgr, e, c = start([DIM, master_track((0, 128))])
c.run(0.5)
check(abs(ch(rig, "rgbuv_7", "r") - plain * 128 / 255) <= 2, "Master 50 %: halb so hell")
sh.master = 0.5
c.run(DT)
check(abs(ch(rig, "rgbuv_7", "r") - plain * 64 / 255) <= 2, "Dimmer im Panel wirkt zusaetzlich")
check(e.compiled.master_at(0.0) == 128 / 255, "Wert aus dem Keyframe")
rig, sh, mgr, e, c = start([DIM, master_track((0, 255), (10, 0))])
check(abs(e.compiled.master_at(5.0) - 0.5) < 0.01 and e.compiled.master_at(11.0) == 0.0, "Keyframes blenden, danach bleibt der letzte Wert")
rig, sh, mgr, e, c = start(ALL + [DIM, master_track((0, 0))])
c.run(0.5)
check(ch(rig, "rgbuv_7", "r") == 0 and ch(rig, "laser", "power") == 255, "Master 0 %: Licht aus, die Laser-Leistung folgt weiter ihrem Clip")
check(not e.compiled.warnings, "Engine kennt die Master-Spur")

# ---- Hakerl ---------------------------------------------------------------------------------------------------------
print("Hakerl")
rig, sh = build()
check(sh.cfg["sm_laser"] == 0.0 and sh.cfg["sm_fog"] == 0.0, "Standard: Laser und Nebel aus")
rig, sh, mgr, e, c = start(ALL, laser=0.0)
c.run(1.0)
check(e.active() and all_off(rig) and not sh.snapshot()["laser"], "Hakerl aus: Laser bleiben aus, die Show laeuft")
sh.cfg.set("sm_laser", 1.0)
c.run(0.5)
check(all(lit(rig, f) for f in BEAMS) and sh.snapshot()["laser"], "Hakerl an: Laser laufen, Anzeige LASER AKTIV")
sh.cfg.set("sm_laser", 0.0)
c.run(DT)
check(all_off(rig) and not sh.snapshot()["laser"], "Hakerl aus: im naechsten Bild aus")

# ---- Sofort aus ------------------------------------------------------------------------------------------------------
print("Sofort aus")
rig, sh, mgr, e, c = start(ALL)
c.run(0.5)
check(lit(rig, "eyes"), "laeuft")
check(ch(rig, "laser", "power") == 255 and ch(rig, "eyes", "mode") == 0 and ch(rig, "derby", "mode") == 0, "Leistung an, Mode-Kanaele im sicheren Bereich")
e.pause(c.t)
c.run(DT)
check(all_off(rig), "Pause: im naechsten Bild aus")
e.play(c.t, None, True, None)
c.run(DT)
check(lit(rig, "eyes"), "weiter: wieder an")
e.seek(30.0, c.t)
c.run(DT)
check(all_off(rig), "Springen: aus")
c.run(0.6)
check(lit(rig, "eyes"), "kurz danach wieder an")
sh.command({"blackout": True})
c.run(DT)
check(all_off(rig) and not sh.snapshot()["laser"], "BLACKOUT: aus")
sh.command({"blackout": False})
c.run(DT)
sh.command({"freeze": True})
c.run(DT)
check(all_off(rig), "FREEZE: aus")
sh.command({"freeze": False})
c.run(DT)
sh.command({"allbright": True})
c.run(DT)
check(all_off(rig), "ALLES HELL: aus")
sh.command({"allbright": False})
c.run(DT)
check(lit(rig, "eyes"), "danach wieder an")
e.stop(c.t)
c.run(DT)
check(all_off(rig) and not rig["eyes"].laser_unlock, "Stop: aus, Freigabe zurueck")
f = rig.render()
check(not any(f[300:334]), "KTV danach wieder alle Kanaele 0")
# Licht aus: nur anhoeren
rig, sh, mgr, e, c = start(ALL)
e.set_light(False)
c.run(DT)
check(all_off(rig), "Licht aus: Laser aus")
# Ende der Show
rig, sh, mgr, e, c = start(ALL)
e.seek(59.9, c.t)
c.run(0.5)
check(not e.loaded and all_off(rig), "Ende der Show: aus")
# Zeitquelle meldet sich nicht mehr
rig, sh, mgr, e, c = start(ALL, owner="browser")
for _ in range(20):
    c.run(0.2)
    e.report("browser", e.position(c.t), True, 0.0, c.t)
check(lit(rig, "eyes"), "Browser meldet sich: an")
c.run(LIVE_S + 0.1)
check(all_off(rig) and e.active(), "Browser weg: Laser aus, das restliche Licht laeuft weiter")
e.report("browser", e.position(c.t), True, 0.0, c.t)
c.run(DT)
check(lit(rig, "eyes"), "Browser wieder da: wieder an")
# KTV im 34-Kanal-Modus: Werte direkt, ohne Anstoss und ohne Selbstlauf (am Geraet bestaetigt: Muster bleibt stabil)
rig, sh, mgr, e, c = start([laser_track("laser", clip(0, 60, "laser", ktv_group="3", ktv_effect=5, ktv_size=90, ktv_zoom=30, ktv_rotate=200, ktv_pos_x=20, ktv_pos_y=40, ktv_wave=64, laser_color="gruen", laser_tempo=77))])
first = []
c.run(0.3, lambda t: first.append((ch(rig, "laser", "power"), ch(rig, "laser", "group"), ch(rig, "laser", "pattern"))))
check(first[0] == (255, 80, 33) and set(first) == {(255, 80, 33)}, "gleich beim ersten Bild die gewaehlten Werte, kein Anstoss")
for p, v in (("color", 17), ("color_speed", 77), ("group", 80), ("pattern", 33), ("size", 90), ("zoom", 30), ("rotate", 200), ("pos_x", 20), ("pos_y", 40), ("wave_x", 64), ("effect", 0), ("effect_speed", 0), ("grating", 0), ("b_group", 0), ("draw_a", 0), ("draw_b", 0)):
    check(ch(rig, "laser", p) == v, f"KTV 34 Kanaele: {p} = {v}")
rig, sh, mgr, e, c = start([laser_track("laser", clip(0, 60, "laser", ktv_fan=120, ktv_fx=46))])
c.run(0.1)
check(ch(rig, "laser", "draw") == 120 and ch(rig, "laser", "effect") == 46, "Faecher und Effekt am Clip")
rig, sh, mgr, e, c = start([laser_track("laser", clip(0, 60, "laser", ktv_fx=250))])
c.run(0.1)
check(ch(rig, "laser", "effect") <= 244, "Effekt am Clip nie im Selbstlauf- oder Sound-Bereich")
rig, sh, mgr, e, c = start([laser_track("laser", clip(0, 60, "laser", ktv_group="anim", ktv_effect=42))])
c.run(0.1)
check(ch(rig, "laser", "group") == 224 and ch(rig, "laser", "pattern") == 255, "Animationsgruppe, letztes Muster im Bereich")
rig, sh, mgr, e, c = start([laser_track("laser", clip(0, 60, "laser", ktv_kick_at=1, ktv_kick_len=2, ktv_auto=5))])
c.run(0.1)
check(ch(rig, "laser", "power") == 255, "alte Clips mit Anstoss-Werten laufen weiter")
check("ktv_kick_len" not in tl.normalize(doc([laser_track("laser", clip(0, 60, "laser", ktv_kick_len=2))]))["tracks"][0]["clips"][0]["p"], "alte Anstoss-Werte fallen beim Speichern weg")

# Verlaeufe im Clip: von klein auf gross, im Takt, nach einem Sprung sofort richtig
def fan_at(sec, **p):
    rig, sh, mgr, e, c = start([laser_track("laser", clip(0, 40, "laser", **p))])
    e.seek(sec, c.t)
    e.hold_until = 0.0
    c.run(0.1)
    return rig, ch(rig, "laser", "draw")


_, v = fan_at(20.0, ktv_fan=20, ktv_fan_to=220)
check(abs(v - 120) <= 2, f"Einmal: Mitte des Clips, Mitte des Verlaufs ({v})")
_, v = fan_at(0.0, ktv_fan=20, ktv_fan_to=220)
check(v <= 24, f"Einmal: am Anfang der Von-Wert ({v})")
_, v = fan_at(39.8, ktv_fan=20, ktv_fan_to=220)
check(v >= 215, f"Einmal: am Ende der Bis-Wert ({v})")
_, v = fan_at(10.0, ktv_fan=0, ktv_fan_to=200, ktv_sweep="pingpong", ktv_sweep_n=1)
check(abs(v - 100) <= 2, f"Hin und her: bei einem Viertel halb offen ({v})")
_, v = fan_at(20.0, ktv_fan=0, ktv_fan_to=200, ktv_sweep="pingpong", ktv_sweep_n=1)
check(v >= 198, f"Hin und her: in der Mitte ganz offen ({v})")
_, v = fan_at(30.0, ktv_fan=0, ktv_fan_to=200, ktv_sweep="pingpong", ktv_sweep_n=1)
check(abs(v - 100) <= 2, f"Hin und her: wieder zurueck ({v})")
_, a = fan_at(19.95, ktv_fan=0, ktv_fan_to=200, ktv_sweep="beat")        # 120 BPM: 2 Beats je Sekunde; gemessen 0,1 s nach dem Sprung
_, b = fan_at(20.15, ktv_fan=0, ktv_fan_to=200, ktv_sweep="beat")
check(a <= 40 and 90 <= b <= 110, f"Im Takt: am Schlag zu, im halben Beat halb offen ({a}, {b})")
_, b2 = fan_at(21.0, ktv_fan=0, ktv_fan_to=200, ktv_sweep="bar")
_, b3 = fan_at(21.0, ktv_fan=0, ktv_fan_to=200, ktv_sweep="beat")
check(b2 != b3, "je Takt laeuft anders als je Beat")
_, e1 = fan_at(10.0, ktv_fan=0, ktv_fan_to=200, ktv_ease="ease_in")
check(10 <= e1 <= 14, f"Uebergang Ease In ({e1})")
_, e2 = fan_at(5.0, ktv_fan=10, ktv_fan_to=200, ktv_ease="constant")
_, e3 = fan_at(30.0, ktv_fan=10, ktv_fan_to=200, ktv_ease="constant")
check(e2 == 10 and e3 == 200, "Uebergang Konstant springt")
rig, v = fan_at(20.0, ktv_size=200, ktv_size_to=60, ktv_pos_y=40, ktv_pos_y_to=90, ktv_pos_x=30, ktv_pos_x_to=100, ktv_rotate=10, ktv_rotate_to=110)
check(abs(ch(rig, "laser", "size") - 130) <= 2 and abs(ch(rig, "laser", "pos_y") - 65) <= 2 and abs(ch(rig, "laser", "pos_x") - 65) <= 2 and abs(ch(rig, "laser", "rotate") - 60) <= 2, "Zoom, Positionen und Drehung laufen mit")
rig, _ = fan_at(20.0, ktv_fan=120, ktv_size=90)
check(ch(rig, "laser", "draw") == 120 and ch(rig, "laser", "size") == 90, "alter Clip ohne Bis-Wert: fester Wert wie bisher")
doc1 = tl.normalize(doc([laser_track("laser", clip(0, 40, "laser", ktv_fan=120))]))
check(doc1["tracks"][0]["clips"][0]["p"]["ktv_fan_to"] == 120, "beim Speichern: Bis = Von")
check(not tl.normalize(doc([laser_track("laser", clip(0, 40, "laser"))]))["tracks"][0]["clips"][0]["p"]["ktv_fan_to"], "neuer Clip ohne Verlauf")
try:
    tl.normalize(doc([laser_track("laser", clip(0, 40, "laser", ktv_sweep="gibtsnicht"))]))
    check(False, "falscher Ablauf abgelehnt")
except ValueError:
    check(True, "falscher Ablauf abgelehnt")
# Sperren gelten auch im Verlauf
rig, sh, mgr, e, c = start([laser_track("laser", clip(0, 40, "laser", ktv_fan=0, ktv_fan_to=200, ktv_sweep="beat"))])
c.run(1.0)
e.pause(c.t)
c.run(DT)
check(not any(rig.render()[300:334]), "Pause im Verlauf: alles 0")

# KTV zurueckgestellt auf 6 Kanaele: Gruppe, Effekt und kurzer Anstoss wirken weiter
K6 = ktv6_config()


def start6(tracks):
    rig, sh, mgr = setup(config=K6)
    e = mgr.engine
    c = Clock(sh)
    e.load(doc(tracks))
    e.play(c.t, 0.0, True, None)
    return rig, sh, e, c


rig, sh, e, c = start6([laser_track("laser", clip(0, 60, "laser", ktv_group="3", ktv_effect=5))])
seq = []
c.run(0.7, lambda t: seq.append((ch(rig, "laser", "power"), ch(rig, "laser", "group"), ch(rig, "laser", "effect"))))
check(seq[0] == (0, 80, 33) and seq[-1] == (255, 80, 33), "6 Kanaele: erst ohne Strahl, am Ende die gewaehlten Werte")
check(any(s[0] == 255 and s[1] != 80 for s in seq), "6 Kanaele: dazwischen kurz andere Werte")
check(ch(rig, "laser", "auto") < 128, "6 Kanaele: Kanal 6 nie im Sound-to-Light-Bereich")
# Clip-Grenzen, Pulse
rig, sh, mgr, e, c = start([laser_track("eyes", clip(2, 1, "laser", laser_color="gruen"))])
c.run(1.0)
check(all_off(rig), "vor dem Clip: aus")
c.run(1.5)
check(ch(rig, "eyes", "laser_green") == 255 and ch(rig, "eyes", "laser_red1") == 0, "im Clip: gewaehlte Farbe")
c.run(1.0)
check(all_off(rig), "nach dem Clip: aus")
rig, sh, mgr, e, c = start([laser_track("eyes", clip(0, 60, "laser", laser_pulse=4, duty=0.5))], strobe=False)
times, prev = [], 0


def each(t):
    global prev
    v = ch(rig, "eyes", "laser_green")
    if v and not prev:
        times.append(t)
    prev = v


c.run(5.0, each)
worst = max(sum(1 for x in times if a <= x < a + 1.0) for a in times)
check(worst <= 2, f"ohne Strobe-Erlaubnis hoechstens 2 Pulse/s, auch bei 8/s programmiert (gemessen {worst})")
check(sh.strobe is False, "Erlaubnis bleibt aus")
# Einzelne Kanaele bleiben gesperrt
rig, sh, mgr, e, c = start([{"target": {"fixture": "laser"}, "attr": "power", "keys": [{"t": 0, "v": 255}], "clips": []},
                            {"target": {"fixture": "eyes"}, "attr": "laser_green", "keys": [{"t": 0, "v": 255}], "clips": []},
                            {"target": {"fixture": "hazer"}, "attr": "pump", "keys": [{"t": 0, "v": 255}], "clips": []},
                            {"target": {"fixture": "eyes"}, "attr": "mode", "keys": [{"t": 0, "v": 200}], "clips": []}])
c.run(0.5)
check(all_off(rig) and ch(rig, "hazer", "pump") == 0 and ch(rig, "eyes", "mode") <= 30, "einzelne Kanaele aus einer Datei wirken auch mit Hakerl nicht")
check(tl.normalize(doc([laser_track("eyes"), {"target": {"fixture": "eyes"}, "attr": "laser", "keys": [{"t": 1, "v": 5}], "clips": []}]))["tracks"][1]["keys"] == [], "Laser-Spur ohne Keyframes")
rig, sh, mgr, e, c = start([laser_track("derby", clip(0, 60, "laser"))])
c.run(0.5)
check(ch(rig, "derby", "mode") <= 10 and ch(rig, "derby", "laser_red") == 255, "Derby: Mode bleibt in der Grenze")

# ---- Mixxx -----------------------------------------------------------------------------------------------------------
print("Mixxx")
link = MixxxLink(0)
rig, sh, mgr = setup(mixxx=link)
sh.cfg.set("sm_mixxx_auto", 1.0)
sh.cfg.set("mixxx_lead_s", 0.0)
d = mgr.store.create("Mx")
d.update(duration=240.0, bpm=120.0, tracks=[laser_track("eyes", clip(0, 240, "laser"))])
d["mixxx"] = {"title": "A - B", "dur": 240.0}
mgr.store.save("Mx", d)
mgr.index_dirty = True
e = mgr.engine
c = Clock(sh)
pos = [10.0]


def run(sec, playing=1):
    for i in range(int(round(sec / DT))):
        if playing:
            pos[0] += DT
        link.feed({"d": 1, "pp": pos[0] / 240.0, "du": 240.0, "rr": 1.0, "bp": 120.0, "pl": playing, "tl": 1, "vo": 1.0}, c.t)
        c.run(DT)
        if i % 8 == 0:
            mgr.mixxx_tick(c.t)


link.feed({"type": "plan", "d": 1, "key": "k", "title": "A - B", "du": 240.0, "ev": [], "en": []}, c.t)
run(1.5)
check(e.owner == MIXXX and lit(rig, "eyes"), "aus Mixxx gestartet: Laser laufen")
run(0.9, playing=0)
check(e.loaded and all_off(rig), "Pause in Mixxx: Laser sofort aus, auch wenn die Show noch kurz weiterlaeuft")
run(1.0, playing=0)
check(not e.loaded, "danach zurueck zu AUTO")

# ---- Nebel ------------------------------------------------------------------------------------------------------------
print("Nebel")


def fog_track(*clips):
    return {"target": {"fixture": "hazer"}, "attr": "fog", "keys": [], "clips": list(clips)}


def run_fog(c, mgr, sec):
    for i in range(int(round(sec / DT))):
        c.run(DT)
        if i % 8 == 0:
            mgr.fog_tick(c.t)


d_ = tl.normalize(doc([fog_track(clip(2, 3, "fog_burst"), clip(4, 99, "fog_burst"))]))
check(d_["tracks"][0]["clips"][1]["d"] == 10.0, "Schub in der Datei hoechstens 10 s")
rig, sh, mgr, e, c = start([fog_track(clip(2, 3, "fog_burst"))], fog=0.0)
run_fog(c, mgr, 3.0)
check(ch(rig, "hazer", "pump") == 0, "Hakerl aus: kein Nebel")
rig, sh, mgr, e, c = start([fog_track(clip(2, 3, "fog_burst"))])
sh._fog_clock = lambda: c.t
run_fog(c, mgr, 1.0)
check(ch(rig, "hazer", "pump") == 0, "vor dem Schub: kein Nebel")
check(e.compiled.fog_cues == [(2, 3)] and e.status(c.t)["uses_fog"], "Schub in der Show gefunden")
run_fog(c, mgr, 1.3)
check(ch(rig, "hazer", "pump") == 150 and ch(rig, "hazer", "fan") == 100, "am Clip: Nebel mit den Werten des SMOKE-Knopfs")
e.pause(c.t)
mgr.fog_tick(c.t)
c.run(DT)
check(ch(rig, "hazer", "pump") == 0, "Pause beendet den Schub")
# Springen ueber einen Schub loest ihn nicht aus
rig, sh, mgr, e, c = start([fog_track(clip(5, 3, "fog_burst"))])
sh._fog_clock = lambda: c.t
run_fog(c, mgr, 0.5)
e.seek(20.0, c.t)
run_fog(c, mgr, 1.0)
check(ch(rig, "hazer", "pump") == 0, "Springen ueber den Schub: kein Nebel")
# Mindestpause
rig, sh, mgr = setup()
sh._fog_clock = lambda: 1000.0
check(sh._fog_cue(3.0) is True and sh.fog_end == 1003.0, "erster Schub laeuft")
check(sh._fog_cue(3.0) is False, "waehrend des Schubs: kein zweiter")
sh._fog_clock = lambda: 1010.0
check(sh._fog_cue(3.0) is False and "Mindestpause" in sh.note, "vor Ablauf der Pause: entfaellt mit Hinweis")
sh._fog_clock = lambda: 1003.0 + sh._fog_cool() + 0.1
check(sh._fog_cue(30.0) is True and abs(sh.fog_end - sh._fog_clock() - 10.0) < 1e-6, "danach wieder, hoechstens 10 s")
# BLACKOUT, kalte Maschine
rig, sh, mgr = setup()
sh.command({"blackout": True})
check(sh._fog_cue(3.0) is False, "BLACKOUT: kein Schub")
rig, sh, mgr = setup()
sh._fog_ready = lambda now: (False, 60.0, "heizt")
calls = []
sh._fog_power_on = lambda now: calls.append(now)
check(sh._fog_cue(3.0) is False and "heizt" in sh.note and not calls, "kalte Maschine: Schub entfaellt, sie wird nicht eingeschaltet")
rig, sh, mgr = setup()
sh.cfg.set("sm_fog", 0.0)
check(sh._fog_cue(3.0) is False, "Hakerl aus: kein Schub")
# Knopf unveraendert
rig, sh, mgr = setup(fog=0.0)
sh.command({"fog": True})
check(ch(rig, "hazer", "pump") == 150, "SMOKE-Knopf wirkt wie bisher, auch ohne Hakerl")
finish("test_showmanager_laser_nebel")
