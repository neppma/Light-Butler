#!/usr/bin/env python3
"""
ableton_link.py - das aktuelle Tempo per Ableton Link ins Netz geben.

Der Pi nimmt als Link-Teilnehmer an der Sitzung teil und setzt deren Tempo auf die BPM, die auch das Panel oben
anzeigt (aus Mixxx oder der Audio-Erkennung). Bei Stille gilt das kleinste Tempo, das Link kennt (20 BPM).
Link findet die anderen Teilnehmer selbst ueber alle Netzwerke des Pi (LAN und WLAN, Multicast 224.76.78.75:20808).

Paket: LinkPython-extern  (im venv:  pip install LinkPython-extern), Modulname "link".
Fehlt es, laeuft die Show ganz normal weiter, im Panel steht dann ein Hinweis.
Eingeschaltet wird Link im Panel (Einstellung link_on, Standard aus).
"""
import time

MIN_BPM = 20.0                 # kleinstes Tempo in Ableton Link (bei Stille)
MAX_BPM = 999.0                # groesstes Tempo in Ableton Link
CHECK_S = 0.25                 # so oft wird das Tempo der Sitzung geprueft und bei Bedarf gesetzt
PEERS_S = 1.0                  # so oft wird die Zahl der Teilnehmer gelesen


def link_tempo(bpm):
    """Tempo fuer Link: Stille (0 oder unbekannt) = 20 BPM, sonst auf 2 Nachkommastellen, im Bereich 20 bis 999."""
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        bpm = 0.0
    if not bpm > 0:
        return MIN_BPM
    return round(max(MIN_BPM, min(MAX_BPM, bpm)), 2)


class LinkOut:
    def __init__(self, module=None, clock=time.monotonic):
        """module: das Link-Modul (nur fuer Tests austauschbar); None = "link" aus LinkPython-extern laden."""
        self.mod, self.error = module, ""
        if self.mod is None:
            try:
                import link as _link
                self.mod = _link
            except Exception as e:                       # noqa: BLE001
                self.error = f"Paket LinkPython-extern fehlt ({e.__class__.__name__})"
        self.clock = clock
        self.link = None
        self.on = False
        self.tempo = 0.0                                # zuletzt gesetztes Tempo
        self.peers = 0
        self.next_check = self.next_peers = 0.0

    @property
    def available(self):
        return self.mod is not None

    def update(self, on, bpm):
        """Einmal pro Show-Bild aufrufen. Wirft nie: ein Fehler schaltet Link ab und steht im Panel."""
        if not self.available:
            return
        try:
            self._update(bool(on), bpm)
        except Exception as e:                           # noqa: BLE001
            self.error = f"Link-Fehler: {e}"[:160]
            self._stop()
            self.mod = None                              # nicht in jedem Bild erneut versuchen

    def _update(self, on, bpm):
        now = self.clock()
        if not on:
            if self.on:
                self._stop()
            return
        target = link_tempo(bpm)
        if self.link is None:
            self.link = self.mod.Link(target)
        if not self.on:
            self.link.enabled = True
            self.on, self.next_check = True, 0.0
        if now >= self.next_check:                       # Tempo der Sitzung setzen (auch wenn ein anderer es verstellt hat)
            self.next_check = now + CHECK_S
            s = self.link.captureSessionState()
            if abs(s.tempo() - target) >= 0.005:
                s.setTempo(target, self.link.clock().micros())
                self.link.commitSessionState(s)
            self.tempo = target
        if now >= self.next_peers:
            self.next_peers = now + PEERS_S
            self.peers = int(self.link.numPeers())

    def _stop(self):
        if self.link is not None:
            try:
                self.link.enabled = False
            except Exception:                            # noqa: BLE001
                pass
        self.on, self.peers = False, 0

    def close(self):
        self._stop()

    def status(self):
        return {"available": self.available, "on": self.on, "peers": self.peers,
                "tempo": self.tempo if self.on else 0.0, "error": self.error}
