"""APC mini, Scene-Launch-Tasten 5 bis 8: Speed Auto, TAP Tempo, Beam Auto, Effektband Auto (mit LED)."""
from _common import build, check, finish, Clock

from midi_ctl import MidiController

rig, sh = build(seed=3)
Clock(sh).run(1)
m = MidiController(sh, map_path=None)
m._raw = lambda *a: None
btn = m.map["buttons"]
note = {v.get("cmd") or "speed:" + v.get("speed", ""): int(k) for k, v in btn.items()}


def press(n):
    m.press(n, True)
    m.press(n, False)


check(not any(k in note for k in ("speed:auto", "beam_auto", "eb_auto")), "keine Auto-Tasten mehr rechts")
t0 = 1000.0
n = 0
for i in range(5):
    n = m._tap(t0 + i * 0.5)
check(n == 5 and sh.manual_bpm == 120.0, "TAP: 5 Schlaege im Abstand 0,5 s = 120 BPM")
check(m._btn_led({"cmd": "tap"}, sh.snapshot(), None) == 1, "TAP-LED an, solange das Tempo von Hand steht")
check(m._tap(t0 + 10) == 1, "nach 2 s Pause beginnt die Zaehlung neu")
finish("test_apc_rechts")
