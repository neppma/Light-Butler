"""Audio-Eingang Bluetooth (Wunsch von Markus 24.11.2026): der Pi als Bluetooth-Empfaenger. Ohne Hardware: bluetoothctl und
bluez-alsa werden nachgespielt (Befehle, Ausgaben, rohe Samples). Geprueft: Kopplungs-Fragen nur im Fenster mit "yes",
gekoppelte Geraete vertraut, Befehle und Adressen gepruefte, Stand fuer das Panel, Umrechnung 48 -> 44,1 kHz ohne
Spruenge zwischen Bloecken, Eingang liefert Bloecke wie eine Soundkarte und die Analyse erkennt die Musik."""
import io
import time

import numpy as np

from _common import audio, check, finish

import bt_audio
from bt_audio import BT_NAME, BtAudioIn, BtManager, Resampler, find_pcm, parse_info, pcm_format

MAC = "AA:BB:CC:11:22:33"


class FakeProc:
    def __init__(self):
        self.sent = []
        self.stdin = self
        self.stdout = io.BytesIO(b"")

    def write(self, b):
        self.sent.append(b.decode().strip())

    def flush(self):
        pass

    def poll(self):
        return None

    def terminate(self):
        pass


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


INFO = """Device AA:BB:CC:11:22:33 (public)
	Name: Markus iPhone
	Alias: Markus iPhone
	Paired: yes
	Trusted: yes
	Connected: yes
	UUID: Audio Source              (0000110a-0000-1000-8000-00805f9b34fb)
"""


def runner(cmd, timeout=0):
    if cmd[:2] == ["bluetoothctl", "show"]:
        return 0, "Controller D8:3A:DD:00:00:01 (public)\n\tPowered: yes\n\tPowerState: on\n\tDiscoverable: no\n"
    if cmd[:2] == ["bluetoothctl", "devices"]:
        return 0, "Device %s Markus iPhone\n" % MAC
    if cmd[:2] == ["bluetoothctl", "info"]:
        return 0, INFO
    return 1, ""


clk = Clock()
proc = FakeProc()
m = BtManager(runner=runner, spawn=lambda: proc, clock=clk, tools=(True, True))
m.ensure()
check(proc.sent[:2] == ["agent NoInputNoOutput", "default-agent"] and "power on" in proc.sent, "Agent angemeldet, Bluetooth an")
check(any(x.startswith("system-alias Light-Butler") for x in proc.sent), "Name Light-Butler in der Liste des Handys")

# Kopplungs-Fragen: ohne Fenster abgelehnt, mit Fenster bestaetigt (Fragen kommen ohne Zeilenumbruch, in Stuecken)
proc.sent.clear()
m.feed("\x1b[0;94m[agent]\x1b[0m Authorize service 0000110d-0000-1000-8000-00805f9b34fb ")
m.feed("(yes/no): ")
check(proc.sent == ["no"] and "abgelehnt" in m.msg, "ohne Sichtbar-Fenster: fremde Kopplung abgelehnt")
m.visible(True)
check("discoverable on" in proc.sent and "pairable on" in proc.sent and m.status()["visible"] == bt_audio.WINDOW_S, "Sichtbar machen: 3 min sichtbar und koppelbar")
proc.sent.clear()
m.feed("[agent] Confirm passkey 123456 (yes/no): ")
check(proc.sent == ["yes"], "im Fenster: Kopplung bestaetigt")
proc.sent.clear()
m.devices.pop(MAC, None)                                 # neues Geraet, noch nicht vertraut
m.feed("[NEW] Device %s Markus iPhone\n[CHG] Device %s Paired: yes\n" % (MAC, MAC))
check("trust " + MAC in proc.sent, "frisch gekoppelt (im Fenster): Geraet wird vertraut (kuenftig ohne Rueckfrage)")
check(m.msg.startswith("Gekoppelt"), "nach der Kopplung: Meldung Gekoppelt statt Kopple mit")
clk.t += bt_audio.MSG_S + 1
check(m.status()["msg"] == "" and m.status()["error"] == "", "alte Meldungen verschwinden nach 20 s (Fehlerbericht 25.11.2026)")
clk.t -= bt_audio.MSG_S + 1
# Kopplung vom Handy, Ereignis verpasst (Test 25.11.2026: Trusted no, "Access denied"): der Stand holt das Vertrauen nach
INFO_UNTRUSTED = INFO.replace("Trusted: yes", "Trusted: no")
m2 = BtManager(runner=lambda c, t=0: (0, INFO_UNTRUSTED) if c[:2] == ["bluetoothctl", "info"] else runner(c, t), spawn=lambda: proc,
               clock=clk, tools=(True, True))
m2.ensure()
proc.sent.clear()
m2.refresh(force=True)
check("trust " + MAC not in proc.sent, "ausserhalb des Fensters: kein automatisches Vertrauen")
m2.visible(True)
proc.sent.clear()
m2.refresh(force=True)
check(proc.sent.count("trust " + MAC) == 1, "im Fenster gekoppelt, nicht vertraut: wird vertraut")
m2.refresh(force=True)
check(proc.sent.count("trust " + MAC) == 1, "nur einmal")
check(isinstance(m2.status()["answers"], list), "Antworten auf Kopplungsfragen fuers Panel")
clk.t += bt_audio.WINDOW_S + 1
proc.sent.clear()
st = m.status()
check(st["visible"] == 0 and "pairable off" in proc.sent, "nach 3 min wieder nicht koppelbar")
m.devices[MAC]["paired"] = True
proc.sent.clear()
m.feed("[agent] Authorize service 0000110d for %s (yes/no): " % MAC)
check(proc.sent == ["yes"], "gekoppeltes Geraet darf sich auch spaeter verbinden")

# Befehle
proc.sent.clear()
m.command({"op": "scan"})
check("scan on" in proc.sent and m.status()["scanning"] > 0, "Suchen")
clk.t += bt_audio.SCAN_S + 1
m.status()
check("scan off" in proc.sent, "Suche endet von selbst")
proc.sent.clear()
m.command({"op": "connect", "mac": MAC.lower()})
check(proc.sent[-1] == "connect " + MAC, "Verbinden (Adresse in Grossbuchstaben)")
for bad in ({"op": "pair", "mac": "AA:BB; rm -rf /"}, {"op": "connect", "mac": ""}, {"op": "foo"}):
    try:
        m.command(bad)
        ok = False
    except ValueError:
        ok = True
    check(ok, "abgelehnt: %s" % bad)
m.command({"op": "pair", "mac": MAC})
check(proc.sent[-1] == "pair " + MAC and m.window_open(), "Koppeln von hier: Rueckfragen dieser Kopplung werden beantwortet")
st = m.status()
d = st["devices"][0]
check(st["powered"] and not st["blocked"] and d["name"] == "Markus iPhone" and d["paired"] and d["connected"] and d["audio"],
      "Stand fuer das Panel: Adapter an, Geraet gekoppelt und verbunden")
m.command({"op": "remove", "mac": MAC})
check(proc.sent[-1] == "remove " + MAC, "Entfernen")

nm = BtManager(runner=runner, spawn=lambda: proc, clock=clk, tools=(False, False))
try:
    nm.visible(True)
    ok = False
except ValueError as e:
    ok = "bluetooth_setup.sh" in str(e)
check(ok and nm.status()["tools"] is False, "ohne Einrichtung: Hinweis auf bluetooth_setup.sh")
st = BtManager(runner=lambda c, t=0: (0, "Controller x\n\tPowered: no\n\tPowerState: off-blocked\n"), spawn=lambda: proc,
               clock=clk, tools=(True, True)).status()
check(st["blocked"] and not st["powered"], "Funk gesperrt wird erkannt")

# bluez-alsa: PCM finden, Format lesen
PCMS = "/org/bluealsa/hci0/dev_AA_BB_CC_11_22_33/a2dpsnk/source\n"
path, mac = find_pcm(lambda c, t=0: (0, PCMS))
check(path == PCMS.strip() and mac == MAC, "verbundenes Handy als PCM gefunden")
check(find_pcm(lambda c, t=0: (0, "/org/bluealsa/hci0/dev_AA_BB_CC_11_22_33/a2dpsrc/sink\n")) == (None, None), "nur Empfang zaehlt")
check(pcm_format("Format: S16_LE\nChannels: 2\nRate: 48000\n") == (48000, 2), "Format aus bluealsa-cli info")
check(pcm_format("Format: S16_LE\nChannels: 2\nSampling: 44100 Hz\n") == (44100, 2), "aeltere Schreibweise Sampling")
check(parse_info("A: 1\nB: x: y\n") == {"A": "1", "B": "x: y"}, "Schluessel: Wert")

# Umrechnung fortlaufend: in Stuecken = am Stueck
t = np.arange(48000) / 48000.0
x = np.stack([np.sin(2 * np.pi * 440 * t)] * 2, axis=1).astype(np.float32)
whole = Resampler(48000, 44100).feed(x)
r = Resampler(48000, 44100)
parts = np.concatenate([r.feed(x[i:i + 777]) for i in range(0, len(x), 777)])
n = min(len(whole), len(parts))
check(abs(len(parts) - 44100) <= 2 and np.max(np.abs(whole[:n] - parts[:n])) < 1e-5, "48 -> 44,1 kHz: in Stuecken gleich wie am Stueck, keine Spruenge")
ref = np.sin(2 * np.pi * 440 * np.arange(n) / 44100.0)
check(np.max(np.abs(parts[:n, 0] - ref)) < 0.01, "Ton bleibt 440 Hz")
same = Resampler(44100, 44100)
check(same.feed(x[:100]) is not None and len(same.feed(x[:100])) == 100, "gleiche Rate: unveraendert")


# Eingang: Musik vom Handy (int16, 48 kHz) -> Bloecke zu 512 Samples
def music(n, sr):
    tt = np.arange(n) / sr
    beat = 60 / 128.0
    ph = tt % beat
    y = 0.8 * np.sin(2 * np.pi * (50 + 90 * np.exp(-ph * 40)) * ph) * np.exp(-ph * 12) + 0.25 * np.sin(2 * np.pi * 55 * tt)
    return np.stack([y, y], axis=1)


raw = (music(48000 * 8, 48000) * 20000).astype("<i2").tobytes()


class Pcm:
    def __init__(self, data):
        self.stdout = io.BytesIO(data)

    def terminate(self):
        pass


def pcm_runner(cmd, timeout=0):
    if cmd[:2] == ["bluealsa-cli", "list-pcms"]:
        return 0, PCMS
    if cmd[:2] == ["bluealsa-cli", "info"]:
        return 0, "Format: S16_LE\nChannels: 2\nRate: 48000\n"
    return 1, ""


blocks = []
bi = BtAudioIn(blocks.append, 44100, 512, runner=pcm_runner, opener=lambda p: Pcm(raw), names=lambda mac: "Markus iPhone")
bi._run = True
check(bi.once() is True, "verbundenes Handy gelesen")
check(blocks and all(b.shape == (512, 2) for b in blocks) and abs(len(blocks) * 512 - 44100 * 8) < 1024,
      "Bloecke wie von der Soundkarte, 8 s bei 44,1 kHz")
st = bi.status()
check(st["alive"] and st["src"] == "Markus iPhone" and st["rate"] == 48000, "Stand: empfaengt von Markus iPhone, 48 kHz")
bi2 = BtAudioIn(blocks.append, 44100, 512, runner=lambda c, t=0: (0, ""), opener=None)
bi2._run = True
check(bi2.once() is False and not bi2.status()["connected"], "kein Handy verbunden: wartet")

# Ende zu Ende: Analyzer mit Eingang Bluetooth
audio.Analyzer.bt_opts = {"runner": pcm_runner, "opener": lambda p: Pcm(raw)}
an = audio.Analyzer(BT_NAME, 44100, 512)
an.start()
deadline = time.time() + 15
while time.time() < deadline and an._bt.blocks < len(blocks) - 4:
    time.sleep(0.1)
time.sleep(0.3)
check(an.dev_name == BT_NAME and an.audio_info()["bt"]["connected"], "Analyzer: Eingang Bluetooth laeuft")
check(an.kick_count >= 8, "Analyse erkennt die Kicks vom Handy (%d)" % an.kick_count)
an.stop()
check(an._bt is None, "Beenden schliesst den Bluetooth-Eingang")
audio.Analyzer.bt_opts = {}

orig = bt_audio.available
bt_audio.available = lambda: (True, True)
names = [d["name"] for d in audio.Analyzer("default", 44100, 512).list_devices()]
bt_audio.available = lambda: (False, False)
names2 = [d["name"] for d in audio.Analyzer("default", 44100, 512).list_devices()]
bt_audio.available = orig
check(BT_NAME in names and BT_NAME not in names2, "Eingang Bluetooth nur in der Liste, wenn eingerichtet")
import inspect  # noqa: E402
import webpanel  # noqa: E402
pg = webpanel.make_page()
check("B.platform!=='linux'" in pg and "Bluetooth-Empfang gibt es nur am Raspberry Pi" in pg,
      "Windows und Mac: statt Einrichtungs-Hinweis nur ein Satz")
check('info["platform"] = sys.platform' in inspect.getsource(webpanel), "/api/bt meldet das Betriebssystem")
finish("test_bluetooth")
