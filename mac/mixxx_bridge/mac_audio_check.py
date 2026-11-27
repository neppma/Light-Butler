#!/usr/bin/env python3
"""
mac_audio_check.py - Audio-Einstellungen am Mac pruefen (Wunsch von Markus 25.11.2026).

Der Ton zum Light-Butler geht ueber BlackHole. Damit er sauber und im Takt ankommt, soll stehen:
  - BlackHole auf 44,1 kHz (Mixxx stellte es beim Start auf 48 kHz, wenn dort Abtastrate 48000 eingestellt war);
  - im Multiausgangsgeraet (Ausgabe des Mac): Driftkorrektur bei jedem Geraet an, ausser beim Primaergeraet.
check() liest das nur (CoreAudio ueber ctypes, keine neuen Pakete) und liefert Warnungen als Text. Aendert nie etwas.
Der Helfer schickt sie an den Pi ("macaudio"), das Panel zeigt sie in der Hinweiszeile.
"""
import ctypes
import ctypes.util
import struct
import sys

WANT_RATE = 44100.0


def _fourcc(s):
    return struct.unpack(">I", s.encode("ascii"))[0]


class _Addr(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


class CoreAudio:
    """Nur lesen: Geraete, Namen, Abtastrate, Multiausgangs-/Aggregatgeraete und ihre Driftkorrektur."""

    def __init__(self):
        self.ca = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreAudio"))
        self.cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        self.cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]
        self.ca.AudioObjectGetPropertyDataSize.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Addr), ctypes.c_uint32,
                                                           ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        self.ca.AudioObjectGetPropertyData.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Addr), ctypes.c_uint32,
                                                       ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]

    def _addr(self, sel, scope="glob"):
        return _Addr(_fourcc(sel), _fourcc(scope), 0)

    def _get(self, obj, sel, ctype, scope="glob"):
        a = self._addr(sel, scope)
        v = ctype()
        size = ctypes.c_uint32(ctypes.sizeof(v))
        if self.ca.AudioObjectGetPropertyData(obj, ctypes.byref(a), 0, None, ctypes.byref(size), ctypes.byref(v)) != 0:
            return None
        return v.value

    def _ids(self, obj, sel):
        a = self._addr(sel)
        size = ctypes.c_uint32(0)
        if self.ca.AudioObjectGetPropertyDataSize(obj, ctypes.byref(a), 0, None, ctypes.byref(size)) != 0:
            return []
        n = size.value // 4
        arr = (ctypes.c_uint32 * n)()
        if self.ca.AudioObjectGetPropertyData(obj, ctypes.byref(a), 0, None, ctypes.byref(size), arr) != 0:
            return []
        return list(arr)

    def _str(self, obj, sel):
        ref = self._get(obj, sel, ctypes.c_void_p)
        if not ref:
            return ""
        buf = ctypes.create_string_buffer(512)
        ok = self.cf.CFStringGetCString(ref, buf, 512, 0x08000100)
        self.cf.CFRelease(ref)
        return buf.value.decode("utf-8", "replace") if ok else ""

    def devices(self):
        out = []
        for d in self._ids(1, "dev#"):
            out.append({"id": d, "name": self._str(d, "lnam"), "uid": self._str(d, "uid "),
                        "rate": self._get(d, "nsrt", ctypes.c_double),
                        "aggregate": self._get(d, "clas", ctypes.c_uint32) == _fourcc("aagg")})
        return out

    def default_output(self):
        return self._get(1, "dOut", ctypes.c_uint32)

    def subdevices(self, agg):
        """[(Name, UID, Driftkorrektur an?)] der aktiven Teilgeraete und die UID des Primaergeraets."""
        subs = []
        for s in self._ids(agg, "ownd"):                 # Teilgeraete (Klasse "asub") tragen die Driftkorrektur
            if self._get(s, "clas", ctypes.c_uint32) != _fourcc("asub"):
                continue
            drift = self._get(s, "drft", ctypes.c_uint32)
            subs.append((self._str(s, "lnam"), self._str(s, "uid "), None if drift is None else bool(drift)))
        return subs, self._str(agg, "amst")


def warnings(devs, default_id, subs_of):
    """Reine Bewertung (testbar ohne Mac). devs aus devices(), subs_of(id) -> (subs, main_uid)."""
    out = []
    bh = [d for d in devs if "blackhole" in d["name"].lower()]
    for d in bh:
        r = d.get("rate")
        if r and abs(r - WANT_RATE) > 1:
            out.append("%s steht auf %s kHz statt 44,1: in Audio-MIDI-Setup umstellen und in Mixxx unter "
                       "Einstellungen → Soundhardware die Abtastrate auf 44100 Hz" % (d["name"], ("%.1f" % (r / 1000)).replace(".", ",")))
    for d in devs:
        if not d["aggregate"]:
            continue
        subs, main_uid = subs_of(d["id"])
        if not any("blackhole" in n.lower() for n, _, _ in subs):
            continue
        if d.get("rate") and abs(d["rate"] - WANT_RATE) > 1:
            out.append("%s steht auf %s kHz statt 44,1 (Audio-MIDI-Setup)" % (d["name"], ("%.1f" % (d["rate"] / 1000)).replace(".", ",")))
        for name, uid, drift in subs:
            if uid and uid != main_uid and drift is False:
                out.append("%s: Driftkorrektur bei %s ist aus (Audio-MIDI-Setup: Schloss zu, ausser beim Primaergeraet)"
                           % (d["name"], name))
    return out


def check():
    """Warnungen als Liste von Texten; leer = alles in Ordnung oder nicht pruefbar (nicht am Mac)."""
    if sys.platform != "darwin":
        return []
    try:
        ca = CoreAudio()
        return warnings(ca.devices(), ca.default_output(), ca.subdevices)
    except Exception:                                   # noqa: BLE001  eine Pruefung darf den Helfer nie stoeren
        return []


if __name__ == "__main__":
    ca = CoreAudio()
    for d in ca.devices():
        print(d)
        if d["aggregate"]:
            print("   ", ca.subdevices(d["id"]))
    print("Warnungen:", check())
