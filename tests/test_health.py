"""Seite Zustand /health (health.py, Herz neben dem Statistik-Knopf): CPU, RAM, Speicher, Temperatur, Strom und Show-Takt aus einem nachgebauten
/proc und /sys. Bewertung mit Ampel, fehlende Werte (Mac) stoeren nicht, und die Messung veraendert das Licht nicht."""
import json
import os
import subprocess
import tempfile
from types import SimpleNamespace

from _common import build, check, finish, Clock

import health
import webpanel

root = tempfile.mkdtemp()


def put(path, text):
    p = os.path.join(root, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


def fake_pi(temp=55.0, avail_kb=2000000, busy=None, iow=0):
    """busy: Ticks, die Kern 0 seit dem Grundstand gearbeitet hat (von 100); iow: davon auf den Speicher gewartet.
    busy=None ist der Grundstand; sonst sind alle vier Kerne 100 Ticks weiter."""
    step = 0 if busy is None else 100
    busy = busy or 0
    idle = step - busy - iow
    put("proc/stat", f"cpu  {1000 + busy} 0 0 {7000 + idle + 3 * step} {iow} 0 0 0 0 0\n"
                     f"cpu0 {250 + busy} 0 0 {1750 + idle} {iow} 0 0 0 0 0\n"
                     f"cpu1 250 0 0 {1750 + step} 0 0 0 0 0 0\ncpu2 250 0 0 {1750 + step} 0 0 0 0 0 0\ncpu3 250 0 0 {1750 + step} 0 0 0 0 0 0\nintr 1 2 3\n")
    put("proc/meminfo", f"MemTotal: 4000000 kB\nMemFree: 100000 kB\nMemAvailable: {avail_kb} kB\nSwapTotal: 102400 kB\nSwapFree: 51200 kB\n")
    put("proc/loadavg", "0.50 0.40 0.30 1/200 999\n")
    put("proc/uptime", "7265.00 100.00\n")
    put("proc/mounts", "/dev/mmcblk0p2 / ext4 rw,noatime 0 0\n/dev/mmcblk0p1 /boot/firmware vfat rw 0 0\n")
    put("proc/self/status", "Name: python\nVmRSS: 102400 kB\n")
    put("proc/self/stat", "123 (py thon) S " + " ".join(["0"] * 10) + " 100 50 0 0 0 0 7 0\n")
    put("sys/class/thermal/thermal_zone0/temp", f"{int(temp * 1000)}\n")
    put("sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "1500000\n")
    put("sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "1800000\n")
    put("sys/block/mmcblk0/stat", "1 2 3 4 5 6 2097152 8 9 10 11\n")


def run(answers):
    return lambda cmd: answers.get(cmd[0], "")


class Disk:
    def __init__(self, total=30.0, free=20.0):
        g = 1024 ** 3
        self.v = SimpleNamespace(f_blocks=int(total * g / 4096), f_bavail=int(free * g / 4096), f_frsize=4096)

    def __call__(self, path):
        return self.v


OK_RUN = run({"vcgencmd": "throttled=0x0\n", "systemctl": "0\n"})
fine_backup = lambda: {"age_h": 5.0}                            # noqa: E731


def make(run_=OK_RUN, disk=None, show=None, backups=fine_backup):
    return health.Health(show or SimpleNamespace(), run_, root=root, statvfs=disk or Disk(), backups=backups)


# ---- Messwerte ------------------------------------------------------------------------------------------------------
fake_pi()
hl = make()
d = hl.sample(100.0)
check(d["cpu"] is None and d["level"] == "ok", "erste Messung: CPU noch unbekannt (braucht zwei Staende), kein Fehlalarm")
fake_pi(busy=60, iow=10)
d = hl.sample(102.0)
check(d["cpu"]["cores"] == [60.0, 0.0, 0.0, 0.0], "CPU je Kern aus /proc/stat")
check(d["cpu"]["total"] == 15.0 or abs(d["cpu"]["total"] - 15.0) < 0.5, f"CPU gesamt ({d['cpu']['total']} %)")
check(d["cpu"]["mhz"] == 1500 and d["cpu"]["mhz_max"] == 1800 and d["cpu"]["load"] == [0.5, 0.4, 0.3], "Takt und Last")
check(d["temp"] == 55.0 and d["temp_max"] == 55.0, "Temperatur")
m = d["mem"]
check((m["total_mb"], m["avail_mb"], m["swap_total_mb"], m["swap_used_mb"], m["rss_mb"]) == (3906, 1953, 100, 50, 100), "RAM, Auslagerung, Show-Programm")
k = d["disk"]
check(k["free_gb"] == 20.0 and k["total_gb"] == 30.0 and k["kind"] == "sd" and not k["ro"], "Speicher: frei, gesamt, SD-Karte")
check(k["written_gb"] == 1.0, "geschrieben seit Pi-Start aus /sys/block")
check(d["uptime_s"] == 7265 and d["threads"] == 7 and d["power"]["uv_now"] is False, "Laufzeit, Threads (Klammer im Prozessnamen stoert nicht), Strom")
check(d["level"] == "ok" and d["issues"] == [], "alles normal: 'Mir geht's gut'")

# ---- Unterspannung und Bremsen --------------------------------------------------------------------------------------
check(health.parse_throttled("throttled=0x0") == {"uv_now": False, "thr_now": False, "uv_ever": False, "thr_ever": False}, "0x0 = alles gut")
t = health.parse_throttled("throttled=0x50005")
check(t["uv_now"] and t["thr_now"] and t["uv_ever"] and t["thr_ever"], "0x50005: Unterspannung und Bremsen, jetzt und seit dem Start")
t = health.parse_throttled("throttled=0x50000")
check(t["uv_ever"] and t["thr_ever"] and not t["uv_now"] and not t["thr_now"], "0x50000: nur frueher")
check(health.parse_throttled("") is None and health.parse_throttled("VCHI initialization failed") is None, "vcgencmd nicht lesbar: unbekannt")


def issue_keys(hl_):
    return [i["k"] for i in hl_.last["issues"]]


# ---- Bewertung ------------------------------------------------------------------------------------------------------
def scenario(run_=OK_RUN, disk=None, show=None, backups=fine_backup, **pi):
    fake_pi()
    h = make(run_, disk, show, backups)
    h.sample(100.0)
    fake_pi(**pi)
    h.sample(102.0)
    return h


h = scenario(temp=72.0)
check(h.last["level"] == "warn" and h.last["st"]["temp"] == "warn" and issue_keys(h) == ["hl_i_temp"], "72 Grad: Achtung")
h = scenario(temp=81.0)
check(h.last["level"] == "crit" and h.last["issues"][0]["v"] == 81, "81 Grad: kritisch (der Pi bremst)")
h = scenario(busy=100)
check("hl_i_cpu" in issue_keys(h) and h.last["cpu"]["total"] < 30, "ein Kern voll bei wenig Gesamtlast wird erkannt")
h = scenario(busy=0, iow=100)
check(h.last["st"]["disk"] == "warn" and "hl_i_iow" in issue_keys(h), "ein Kern wartet nur noch auf den Speicher: Achtung")
h = scenario(avail_kb=800000)
check(h.last["st"]["mem"] == "warn", "RAM unter 25 %: Achtung")
h = scenario(avail_kb=200000)
check(h.last["st"]["mem"] == "crit" and h.last["issues"][0]["v"] == 195, "RAM unter 10 %: kritisch")
h = scenario(disk=Disk(30.0, 3.0))
check(h.last["st"]["disk"] == "warn", "Speicher unter 15 %: Achtung")
h = scenario(disk=Disk(30.0, 1.0))
check(h.last["st"]["disk"] == "crit", "Speicher unter 5 %: kritisch")
h = scenario(run_=run({"vcgencmd": "throttled=0x1\n"}))
check(h.last["level"] == "crit" and "hl_i_uv_now" in issue_keys(h), "Unterspannung jetzt: kritisch")
h = scenario(run_=run({"vcgencmd": "throttled=0x10000\n"}))
check(h.last["level"] == "warn" and "hl_i_uv" in issue_keys(h), "Unterspannung frueher: Achtung")
h = scenario(run_=run({"vcgencmd": "throttled=0x0\n", "systemctl": "2\n"}))
check("hl_i_restart" in issue_keys(h) and h.last["restarts"] == 2, "automatische Neustarts werden gemeldet")
h = scenario(backups=lambda: {"age_h": 72.0})
check("hl_i_backup" in issue_keys(h), "Sicherung aelter als 2 Tage: Achtung")
h = scenario(backups=lambda: {"age_h": None})
check("hl_i_nobackup" in issue_keys(h), "keine Sicherung: Achtung")
put("proc/mounts", "/dev/sda2 / ext4 ro,noatime 0 0\n")
h = make()
h.sample(1.0)
check(h.last["level"] == "crit" and "hl_i_ro" in issue_keys(h), "schreibgeschuetzter Speicher: kritisch")
os.remove(os.path.join(root, "proc/mounts"))
h = scenario(temp=81.0, avail_kb=800000)
check([i["s"] for i in h.last["issues"]][0] == "crit", "das Schlimmste steht zuerst")
sh = SimpleNamespace(reach={"Art-Net-Gateway": True, "Theke": False, "Nanoleaf": None}, net=[{"type": "LAN", "up": True, "main": True, "speed": 1000, "signal": None}])
h = scenario(show=sh)
check(h.last["links"]["down"] == ["Theke"] and h.last["links"]["net"][0]["speed"] == 1000 and "hl_i_down" in issue_keys(h), "nicht erreichbares Geraet wird genannt")

# ---- Show-Takt ------------------------------------------------------------------------------------------------------
fs = health.FrameStats()
t = 0.0
for _ in range(80):                       # 2 s, sauber 40 Bilder/s, 5 ms Rechenzeit
    fs.note(t, t + 0.005)
    t += 0.025
fake_pi()
h = make(show=SimpleNamespace(frames=fs))
h.sample(100.0)
for _ in range(80):
    fs.note(t, t + 0.005)
    t += 0.025
d = h.sample(102.0)["frames"]
check(d["fps"] == 40.0 and d["work_ms"] == 5.0 and d["late_min"] == 0, "40 Bilder/s, 5 ms je Bild, keine Aussetzer")
check(h.last["st"]["frames"] == "ok", "Takt in Ordnung")
for _ in range(4):                        # vier Luecken von 100 ms
    t += 0.1
    fs.note(t, t + 0.005)
d = h.sample(104.0)["frames"]
check(d["late_min"] == 4 and d["late_total"] == 4 and d["gap_max_ms"] >= 100, "Aussetzer und laengste Luecke gezaehlt")
check(h.last["st"]["frames"] == "crit" and "hl_i_fps" in issue_keys(h) and "hl_i_late" in issue_keys(h), "fast keine Bilder: kritisch")
check(health.FrameStats().take()["total"] == 0 and make(show=SimpleNamespace(frames=health.FrameStats())).sample(1.0)["frames"] is None, "ohne Bilder: Takt unbekannt, kein Fehlalarm")

# ---- Verlauf der letzten Stunde -------------------------------------------------------------------------------------
fake_pi()
h = make()
for i in range(health.HIST_EVERY * health.HIST_LEN + 20):
    h.sample(float(2 * i))
info = h.info()
check(len(info["hist"]["temp"]) == health.HIST_LEN and info["hist"]["step_s"] == 10.0, "Verlauf: eine Stunde, feste Laenge")
check(len(json.dumps(info)) < 20000, "Antwort bleibt klein")

# ---- Am Mac oder ohne Rechte: leere Felder statt Absturz ------------------------------------------------------------
h = health.Health(SimpleNamespace(), lambda c: "", root=tempfile.mkdtemp(), statvfs=Disk(), backups=lambda: 1 / 0)
d = h.sample(1.0)
d = h.sample(3.0)
check(d["cpu"] is None and d["temp"] is None and d["mem"] is None and d["power"] is None and d["backup"] is None, "fehlt alles: Felder leer")
check(d["level"] == "ok" and d["disk"]["kind"] == "", "fehlt alles: kein Fehlalarm, kein Absturz")
check(health.Health(None, lambda c: "").info()["t"] is None, "vor der ersten Messung")
hw = health.Health(SimpleNamespace(), lambda c: "", root=tempfile.mkdtemp(), statvfs=None, backups=lambda: 1 / 0)
hw.sample(1.0)
check(hw._disk() is None and hw.sample(3.0)["level"] == "ok", "Windows ohne os.statvfs: kein Speicher, kein Absturz")

# ---- Zaehler in Audio und Ausgabe ------------------------------------------------------------------------------------
rig, sh = build()
check(isinstance(sh.frames, health.FrameStats), "die Show bringt ihren Bildzaehler mit")
from dmx import Output                       # noqa: E402


class BadSender:
    def send(self, data):
        raise OSError("nicht erreichbar")

    def close(self):
        pass


out = Output(rig, lambda ip: BadSender())
out._send_all({t: b"123" for t in out.senders})
check(out.send_errors == len(out.senders), "Sendefehler werden gezaehlt, die Show laeuft weiter")
sh.output = out
sh.frames.note(1.0, 1.002)
real = health.Health(sh, lambda c: "")
d = real.sample(1.0)
d = real.sample(3.0)
check(d["links"]["send_err_min"] == 0, "Sendefehler: gezaehlt wird nur die letzte Minute")
out._send_all({t: b"123" for t in out.senders})
d = real.sample(5.0)
check(d["links"]["send_err_min"] == len(out.senders) and "hl_i_send" in [i["k"] for i in d["issues"]], "neue Sendefehler: Achtung")
json.dumps(real.info())
check(True, "die Antwort laesst sich als JSON schicken")

# ---- Die Messung veraendert das Licht nicht --------------------------------------------------------------------------
def frames(with_health):
    rig_, sh_ = build(seed=3)
    h_ = health.Health(sh_, lambda c: "") if with_health else None
    out_ = []

    def each(t):
        if h_ is not None:
            sh_.frames.note(t, t + 0.001)
            if int(t * 40) % 80 == 0:
                h_.sample(t)
        out_.append(bytes(next(iter(rig_.render_all().values()))))
    Clock(sh_).run(20, each)
    return out_


check(frames(True) == frames(False), "20 s Simulator: mit Messung Bild fuer Bild gleich")

# ---- Farbe des Herzens -------------------------------------------------------------------------------------
fake_pi()
rig, sh = build()
check(sh.snapshot()["health_level"] == "ok", "Herz: ohne Messung kein Alarm")
h = health.Health(sh, OK_RUN, root=root, statvfs=Disk(), backups=fine_backup)
h.sample(100.0)
fake_pi(temp=72.0, busy=0)
h.sample(102.0)
check(sh.snapshot()["health_level"] == "warn", "Herz: Achtung kommt im Status an")
fake_pi(temp=81.0, busy=0)
h.sample(104.0)
check(sh.snapshot()["health_level"] == "crit", "Herz: kritisch kommt im Status an")
fake_pi(temp=55.0, busy=0)
h.sample(106.0)
check(sh.snapshot()["health_level"] == "ok", "Herz: wird wieder normal")
json.dumps(sh.snapshot())

# ---- Panel -----------------------------------------------------------------------------------------------------------
p = webpanel.make_page()
check("fetch('/api/health')" in p and 'id="hlbody"' in p and 'id="hlhead"' in p, "Seite Zustand hat Satz und Karten")
check('<body class="vhealth">' in webpanel.health_page() and "body.vhealth #hlsec{display:block}" in p, "eigene Seite /health")
sec = p[p.index('id="statsec"'):p.index('id="apcsec"')]
check('id="hlbody"' not in sec and 'id="statbody"' in sec, "Statistikseite zeigt nur die Musikdaten")
row1 = p[p.index('id="row1"'):p.index('id="setbtn"')]
check('<a id="hlbtn" href="/health"' in row1 and row1.index('id="hlbtn"') < row1.index('id="statbtn"'), "Herz oben rechts, direkt neben dem Statistik-Knopf")
check("#hlbtn.warn{color:#f0c040}#hlbtn.crit{color:#ff5a4d}" in p and "b.classList.toggle('crit',l==='crit')" in p and "drawHlBtn();" in p, "Herz gelb bei Achtung, rot bei Kritisch")
check("hldot" not in p and "#hlbtn{flex:none;width:30px;height:30px" in p, "kein Punkt dazu, das Herz bleibt gleich gross")
check("@media(max-width:480px){#helpbtn{display:none!important}#evslot:not(.laser) #evtext{display:none}" in p , "am Handy: Hilfe nicht im Kopf (im Menue der Kopfleiste), das Ereignisfeld zeigt nur die Farbe")
check("if(S.laser)return['alert laser',tr('ev_laser')];" in p and "#row1 #evslot.laser{font-size:10px" in p, "der Laser-Hinweis bleibt auch am Handy als Text sichtbar")
check("hb.href='/help?lang='+l" in p and "S2LNAV.set(l,TXT)" in p, "Hilfe-Knopf und Kopfleiste folgen der Sprache des Panels")
check("loadHealth()},5000)" in p, "holt alle 5 s neu, nur wenn die Seite sichtbar ist")
import texts                                 # noqa: E402
keys = {k for k, *_ in texts.catalog()}
src = open(health.__file__, encoding="utf-8").read()
import re                                    # noqa: E402
need = set(re.findall(r'"(hl_i_\w+)"', src)) | {"hl_ok", "hl_warn", "hl_crit", "hl_s_ok", "hl_s_warn", "hl_s_crit", "hl_title"}
need |= set(re.findall(r"tr\('(hl_\w+)'\)", p))
check(need <= keys, f"alle Texte deutsch und englisch vorhanden {sorted(need - keys)}")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_health")
