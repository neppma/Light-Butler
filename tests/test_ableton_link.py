"""Ableton Link: der Pi gibt das angezeigte Tempo ins Netz, bei Stille 20 BPM. Standard aus, im Panel schaltbar.
Mit einem nachgebauten Link-Modul (das echte Paket LinkPython-extern ist fuer die Tests nicht noetig)."""
import sys

from _common import build, Clock, check, finish

import settings
import webpanel
from ableton_link import LinkOut, link_tempo


class FakeLink:
    """Nachbau von link.Link aus LinkPython-extern (nur was ableton_link.py benutzt)."""
    instances = []

    def __init__(self, bpm):
        self.session_tempo, self.enabled, self.commits, self.peers = float(bpm), False, 0, 2
        FakeLink.instances.append(self)

    class _State:
        def __init__(self, owner):
            self.owner, self.t = owner, owner.session_tempo

        def tempo(self):
            return self.t

        def setTempo(self, bpm, micros):
            self.t = bpm

    class _Clock:
        def micros(self):
            return 0

    def captureSessionState(self):
        return FakeLink._State(self)

    def commitSessionState(self, s):
        self.session_tempo, self.commits = s.t, self.commits + 1

    def clock(self):
        return FakeLink._Clock()

    def numPeers(self):
        return self.peers


class FakeModule:
    Link = FakeLink


# Tempo-Regel
check(link_tempo(0) == 20.0 and link_tempo(None) == 20.0 and link_tempo(-5) == 20.0, "Stille oder kein Tempo = 20 BPM")
check(link_tempo(128.004) == 128.0 and link_tempo(127.456) == 127.46, "Tempo auf 2 Nachkommastellen")
check(link_tempo(5000) == 999.0 and link_tempo(12) == 20.0, "Tempo im Link-Bereich 20 bis 999")

# Standard: aus
d = {p.key: p for p in settings.DEFS}
check("link_on" in d and d["link_on"].default == 0.0, "Einstellung link_on vorhanden, Standard aus")

# Fehlt das Paket: Show laeuft, Panel zeigt Hinweis
saved = sys.modules.get("link")
sys.modules["link"] = None                                # so tun, als waere das Paket nicht installiert
try:
    lo = LinkOut()
finally:
    if saved is None:
        del sys.modules["link"]
    else:
        sys.modules["link"] = saved
lo.update(True, 128.0)
check(lo.status()["available"] is False and "LinkPython-extern" in lo.error, "fehlendes Paket: Hinweis statt Absturz")

# Show mit nachgebautem Link
rig, sh = build(seed=7)
t = [0.0]
sh.link_out = LinkOut(module=FakeModule, clock=lambda: t[0])
clk = Clock(sh)


def tick(_):
    t[0] += 0.025


clk.run(20, each=tick)
check(not FakeLink.instances, "Link aus (Standard): keine Link-Sitzung")
sh.cfg.set("link_on", 1.0)
clk.run(2, each=tick)
lk = FakeLink.instances[-1] if FakeLink.instances else None
check(lk is not None and lk.enabled, "Link an: Sitzung aktiv")
check(lk is not None and abs(lk.session_tempo - round(sh._bpm_live(), 2)) < 0.01 and lk.session_tempo > 20,
      f"Link-Tempo = angezeigtes Tempo ({lk.session_tempo if lk else '-'} / {sh._bpm_live():.2f})")
snap = sh.snapshot()
check(snap["link_on"] and snap["link"]["on"] and snap["link"]["peers"] == 2, "Panel-Status: an, 2 Geraete")

# jemand anderes verstellt das Tempo: der Pi setzt es wieder
lk.session_tempo = 90.0
clk.run(0.5, each=tick)
check(abs(lk.session_tempo - round(sh._bpm_live(), 2)) < 0.01, "fremde Tempoaenderung wird wieder auf das Pi-Tempo gesetzt")
n = lk.commits
clk.run(5, each=tick)
check(lk.commits - n <= 5 * 4, "Tempo wird hoechstens 4-mal pro Sekunde gesetzt")

# Stille: 20 BPM
live = sh._bpm_live
sh._bpm_live = lambda: 0.0                                # Anzeige "--" (Stille, kein Beat seit 4 s)
clk.run(0.5, each=tick)
check(lk.session_tempo == 20.0, f"Stille: Link sendet 20 BPM ({lk.session_tempo})")
sh._bpm_live = live
clk.run(0.5, each=tick)
check(lk.session_tempo > 20.0, "Musik wieder da: Link sendet wieder das Tempo")

# ausschalten
sh.cfg.set("link_on", 0.0)
clk.run(0.5, each=tick)
check(not lk.enabled and not sh.snapshot()["link"]["on"], "Link aus: Sitzung verlassen")
sh.close()

# Fehler im Link-Modul legt die Show nicht lahm
class Broken:
    class Link:
        def __init__(self, bpm):
            raise RuntimeError("kaputt")


sh.link_out = LinkOut(module=Broken, clock=lambda: t[0])
sh.cfg.set("link_on", 1.0)
clk.run(1, each=tick)
check("kaputt" in sh.snapshot()["link"]["error"] and not sh.link_out.available, "Link-Fehler: Show laeuft weiter, Hinweis im Panel")

# Panel
page = webpanel.make_page()
check('id="link_on"' in page and "c({set:{link_on:1}})" in page, "Panel: Schalter fuer Ableton Link")

finish("test_ableton_link")
