"""APC mini mk2: Reihe 1 wie die Knopfreihe im Panel: AUTO, Strobe, Wow, Blinder, Freeze, Blackout (halten), Smoke, BPM; Reihe 2
Bewegung; Reihe 3 Licht-Mix (mit Scanner); Reihe 4 bis 8 Szenen 1 bis 40. SHIFT halten = Farben. Rechts Low, Med,
Hot, Laser. Unten Ziele wie bisher. LEDs: aus rot (Reihe 1 gelb, AUTO blau), aktiv gruen. Ohne Hardware getestet."""
from _common import build, Clock, check, finish

import midi_ctl as mc
from midi_ctl import MidiController, PALETTE, pad_note

RED, GREEN, YELLOW, BLUE = PALETTE["rot"], PALETTE["gruen"], PALETTE["gelb"], PALETTE["blau"]

rig, sh = build(seed=10)
clk = Clock(sh)
clk.run(5)
m = MidiController(sh, map_path=None)
leds = {}
m._raw = lambda note, vel, ch: leds.__setitem__(note, (vel, ch))      # statt USB: LED-Werte merken


def pad(row, col, pressed=True):
    m.press(pad_note(row, col), pressed)


def led(row, col):
    m.refresh_leds(sh.snapshot())
    return leds.get(pad_note(row, col))


p1 = m.map["pads1"]
row = lambda r: [p1.get(str(pad_note(r, c))) for c in range(8)]
check([a["cmd"] for a in row(0)] == ["auto", "blitz", "wow", "allbright", "freeze", "blackout", "fog", "beat"],
      "Reihe 1: AUTO, Strobe, Wow, Blinder, Freeze, Blackout, Smoke, BPM (wie im Panel)")
AUTO, STROBE, BLACK = (mc.TOP_ROW.index(k) for k in ("auto", "blitz", "blackout"))
check([a["move"] for a in row(1)] == ["duck", "home", "random", "sweep", "circle", "vertical", "horizontal", "fan"],
      "Reihe 2: Float, Center, Random, Sweep, Circle, Tilt, Pan, Swim")
check([a["mix"] for a in row(2)] == ["Discokugel", "Karussell", "Sternenhimmel", "STOP", "nach aussen", "nach innen", "Scanner", "Regenbogen"],
      "Reihe 3: Disco, Carousel, Sparkle, Static, Chase-Out, Chase-In, Scanner, Rainbow")
check([p1[str(pad_note(3 + i // 8, i % 8))]["scene_index"] for i in range(40)] == list(range(40)), "Reihe 4 bis 8: Szenen 1 bis 40")
btn = m.map["buttons"]
check([btn.get(str(n)) for n in range(112, 116)] == [{"speed": "slow"}, {"speed": "mid"}, {"speed": "fast"}, {"cmd": "laser"}]
      and [btn.get(str(n)) for n in range(116, 120)] == [None, {"cmd": "tap"}, None, None],
      "rechts: Low, Med, Hot, Laser, frei, TAP, frei, frei")
check([btn.get(str(n)) for n in range(100, 104)] == [{"aim": "bank"}, {"aim": "tisch"}, {"aim": "tuer"}, {"aim": "bar"}],
      "unten: Ziele wie bisher")

# Reihe 1 wirkt wie die Knoepfe im Panel
pad(0, STROBE)
check(sh.snapshot()["blitz"] is True and led(0, STROBE)[0] == GREEN, "Strobe gedrueckt: blitzt, Pad gruen")
pad(0, STROBE, False)
check(sh.snapshot()["blitz"] is False and led(0, STROBE)[0] == YELLOW, "Strobe losgelassen: aus, Pad gelb")
pad(0, BLACK)
check(sh.snapshot()["mode"] == "blackout" and led(0, BLACK)[0] == GREEN, "Blackout gedrueckt: dunkel, Pad gruen")
pad(0, BLACK, False)
check(sh.snapshot()["mode"] == "auto" and led(0, BLACK)[0] == YELLOW, "Blackout losgelassen: vorbei, Pad gelb")
pad(0, BLACK)
pad(0, AUTO)
check(sh.snapshot()["pilot"] and led(0, AUTO)[0] == GREEN, "AUTO: Autopilot an, Pad gruen")
sh.pilot = False
pad(2, 6)
check(sh.snapshot()["mixbtn"] == "Scanner" and led(0, AUTO)[0] == BLUE, "Scanner gewaehlt, AUTO-Pad blau (nicht aktiv)")
check(led(2, 6)[0] == GREEN and led(2, 0)[0] == RED, "aktiver Mix gruen, andere rot")
pad(2, 6)
pad(1, 4)
check(sh.snapshot()["move"] == "circle" and led(1, 4)[0] == GREEN, "Bewegung Circle gewaehlt, Pad gruen")
pad(1, 4)
pad(3, 1)
name = sh.scene_defs[1].name
check(sh.snapshot()["scene"] == name and led(3, 1) == (GREEN, mc.CH_PULSE), f"Pad Szene 2 waehlt {name}, pulsiert gruen")
check(led(3, 2)[0] == RED, "andere Szenen rot")
pad(3, 1)

# rechte Tasten: Tempo
m.press(114, True)
check(sh.snapshot()["speed"] == "fast", "rechte Taste 3: Hot")
m.refresh_leds(sh.snapshot())
check(leds.get(114) == (1, 0) and leds.get(112) == (0, 0), "Hot leuchtet, Low aus")
m.press(114, True)

# BPM blinkt im Takt
m.sent.clear()
sh.beat_t = (sh.beat_t or 0) + 1.0
m._beat(1000.0)
check(leds.get(pad_note(0, 7))[0] == GREEN, "BPM blinkt beim Beat gruen")
m._beat(1000.5)
check(leds.get(pad_note(0, 7))[0] == RED, "BPM danach wieder rot")

# SHIFT: Farben
m.press(mc.SHIFT_NOTE, True)
check(m._pads() is m.map["pads2"], "SHIFT gehalten: Farbseite")
pad(0, 1)
check(sh.snapshot()["colors"] == ["rot"], "Pad 2 mit SHIFT: Farbe Rot")
check(led(0, 1) == (PALETTE["rot"], mc.CH_FULL) and led(0, 7) == (PALETTE["violett"], mc.CH_DIM), "Farben in echter Farbe, gewaehlte hell")
check(led(4, 0) == (0, 0), "unbelegte Pads aus")
m.press(mc.SHIFT_NOTE, False)
check(m._pads() is m.map["pads1"] and led(0, STROBE)[0] == YELLOW, "SHIFT losgelassen: wieder Hauptseite")
pad(1, 0)
check(sh.snapshot()["colors"] == ["rot"] and sh.snapshot()["move"] == "duck", "ohne SHIFT wirkt das Pad wieder als Float")

# Seite 2 ueber die untere Taste bleibt moeglich
m.press(107, True)
check(m._pads() is m.map["pads2"], "Taste Seite 2: Farbseite fest")
m.press(106, True)
check(m._pads() is m.map["pads1"], "Taste Seite 1: Hauptseite")

finish("test_apc_belegung")
