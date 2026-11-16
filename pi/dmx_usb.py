#!/usr/bin/env python3
"""
dmx_usb.py - DMX direkt ueber einen einfachen FTDI-Adapter am Light-Butler-Pi (statt Art-Net zum OLA-Pi).

Unterstuetzt Adapter OHNE eigenen Prozessor (Enttec Open DMX USB und Nachbauten, FTDI FT232R, USB-ID 0403:6001).
Der Pi erzeugt das DMX-Signal selbst, so wie es das OLA-Plugin "FTDI USB DMX" auf dem OLA-Pi macht:
Break (mind. 88 us), Mark after Break, Startcode 0, dann die Kanaele mit 250 kBaud, 8 Datenbits, 2 Stopbits.

Die Sicherheitslogik (Laser-Sperre, safe_limits, Strobe-Grenzen) steckt in dmx.Fixture.write und der Show; hier
werden nur die fertigen Bytes uebertragen, genau dieselben, die sonst per Art-Net zum OLA-Pi gingen.

Braucht das Paket pyserial (nur am Pi):  /home/admin/venv/bin/pip install pyserial
"""
import threading
import time

FTDI_VID, FTDI_PID = 0x0403, 0x6001
BAUD = 250000
BYTE_S = 11.0 / BAUD          # ein Byte auf der Leitung: Startbit, 8 Daten, 2 Stopbits = 44 us
BREAK_S = 0.00011             # Break: DMX verlangt mindestens 88 us
MAB_S = 0.00002               # Mark after Break: mindestens 8 us


def find_port(serial_mod):
    """Geraetedatei des ersten FTDI-Adapters (z. B. /dev/ttyUSB0), sonst None."""
    try:
        from serial.tools import list_ports
        ports = list_ports.comports()
    except Exception:                                   # noqa: BLE001
        ports = getattr(serial_mod, "fake_ports", [])
    for p in ports:
        if getattr(p, "vid", None) == FTDI_VID and getattr(p, "pid", None) == FTDI_PID:
            return p.device
    return None


class OpenDmxSender:
    """Sender fuer dmx.Output: send(data) und close(), dazu status() fuer das Panel.

    Ein eigener Thread uebertraegt jedes Show-Bild genau einmal (ein Bild mit 300 Kanaelen dauert etwa 13 ms, die
    Show liefert alle 25 ms eins). Kommt 0,5 s lang kein neues Bild, wiederholt er das letzte, denn die Geraete
    brauchen einen laufenden Datenstrom. Fehlt der Adapter oder bricht die Verbindung ab, sucht er alle 2 s neu;
    die Show laeuft dabei ungestoert weiter.
    """
    RETRY_S = 2.0
    KEEP_S = 0.5

    def __init__(self, port=None, channels=512, serial_mod=None, threaded=True):
        self.port_cfg = port or None
        self.n = max(24, min(512, int(channels)))      # DMX verlangt mindestens 24 Kanaele pro Bild
        self.serial = serial_mod
        self.threaded = threaded
        self.ser = None
        self.port = ""
        self.err, self.detail = "wait", ""              # Fehlerkennung fuers Panel (uebersetzt): wait|nomod|notfound|open|write
        self.next_try = 0.0
        self.frames = 0
        self._frame = None
        self._new = threading.Event()
        self._lock = threading.Lock()
        self._run = False
        self._thread = None

    def status(self):
        return {"ok": self.ser is not None, "port": self.port, "err": "" if self.ser is not None else self.err,
                "detail": self.detail, "channels": self.n, "frames": self.frames}

    # ---- Schnittstelle fuer dmx.Output ------------------------------------------------------------
    def send(self, data):
        f = bytes(data[:self.n])
        if len(f) < self.n:
            f += bytes(self.n - len(f))
        if not self.threaded:
            self.transmit(f)
            return
        with self._lock:
            self._frame = f
        if self._thread is None:
            self._run = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        self._new.set()

    def close(self):
        """Thread beenden, das zuletzt uebergebene Bild (beim Beenden ein Blackout) noch senden, Adapter freigeben."""
        self._run = False
        self._new.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._lock:
            f = self._frame
        if f is not None and self.ser is not None:
            self.transmit(f)
        self._drop()

    # ---- Uebertragung -----------------------------------------------------------------------------
    def _loop(self):
        while self._run:
            self._new.wait(self.KEEP_S)
            self._new.clear()
            with self._lock:
                f = self._frame
            if f is not None and self._run:
                if not self.transmit(f) and self.ser is None:
                    time.sleep(0.05)                    # ohne Adapter nicht im Kreis laufen

    def transmit(self, frame):
        """Ein DMX-Bild uebertragen (Break, MAB, Startcode 0, Kanaele). True = gesendet."""
        if self.ser is None and not self._open():
            return False
        ser = self.ser
        try:
            ser.break_condition = True
            time.sleep(BREAK_S)
            ser.break_condition = False
            time.sleep(MAB_S)
            t0 = time.perf_counter()
            pkt = b"\x00" + bytes(frame)
            ser.write(pkt)
            ser.flush()
            rest = t0 + len(pkt) * BYTE_S - time.perf_counter()
            if rest > 0:                                # das letzte Byte muss draussen sein, bevor der naechste Break kommt
                time.sleep(rest)
            self.frames += 1
            return True
        except (OSError, ValueError) as e:              # serial.SerialException ist ein OSError: Adapter abgezogen
            self.err, self.detail = "write", str(e)[:120]
            self._drop()
            return False

    def _open(self):
        now = time.monotonic()
        if now < self.next_try:
            return False
        self.next_try = now + self.RETRY_S
        mod = self.serial
        if mod is None:
            try:
                import serial as mod
            except ImportError:
                self.err, self.detail = "nomod", ""
                return False
            self.serial = mod
        port = self.port_cfg or find_port(mod)
        if not port:
            self.err, self.detail = "notfound", ""
            return False
        try:
            self.ser = mod.Serial(port, BAUD, bytesize=8, parity="N", stopbits=2, timeout=0, write_timeout=0.2)
        except (OSError, ValueError) as e:
            self.ser = None
            self.err, self.detail = "open", f"{port}: {e}"[:120]
            return False
        self.port, self.err, self.detail = port, "", ""
        return True

    def _drop(self):
        ser, self.ser = self.ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:                           # noqa: BLE001
                pass


class DmxRouter:
    """Hauptausgang fuer die DMX-Kette: Art-Net zum OLA-Pi ("ola") oder direkt ueber den USB-Adapter ("usb").

    Umschaltbar im laufenden Betrieb (Einstellung dmx_via). Der bisherige Weg bekommt danach noch einige
    Blackout-Bilder, damit dort keine alten Werte haengen bleiben; der USB-Adapter wird anschliessend freigegeben.
    """
    BLANK = 6

    def __init__(self, ola, make_usb):
        self.ola, self.make_usb = ola, make_usb
        self.usb = None
        self.via = "ola"
        self.blank = {}
        self._lock = threading.Lock()

    def set_via(self, via):
        via = "usb" if via == "usb" else "ola"
        with self._lock:
            if via == self.via:
                return
            self.blank[self.via] = self.BLANK
            self.blank.pop(via, None)
            self.via = via

    def _path(self, p):
        if p == "ola":
            return self.ola
        if self.usb is None:
            self.usb = self.make_usb()
        return self.usb

    def send(self, data):
        with self._lock:
            via, blank = self.via, list(self.blank.items())
        for p, _ in blank:
            try:
                self._path(p).send(bytes(len(data)))
            except OSError:
                pass
            done = False
            with self._lock:
                if p in self.blank:
                    self.blank[p] -= 1
                    if self.blank[p] <= 0:
                        del self.blank[p]
                        done = True
            if done and p == "usb" and self.usb is not None:
                usb, self.usb = self.usb, None
                usb.close()
        self._path(via).send(data)

    def status(self):
        usb = self.usb.status() if self.usb is not None else None
        return {"via": self.via, "usb": usb}

    def close(self):
        self.ola.close()
        if self.usb is not None:
            self.usb.close()
