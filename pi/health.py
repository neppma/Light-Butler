#!/usr/bin/env python3
"""
health.py - wie es dem Light-Butler selbst geht (Seite /health, Herz neben dem Statistik-Knopf).

Liest nur: /proc und /sys (CPU, RAM, Temperatur, Speicher), vcgencmd (Unterspannung, Bremsen), systemctl (Neustarts des
Dienstes), dazu den Bildtakt der Show (FrameStats). Sendet nichts ans Licht und schreibt keine Dateien. Fehlt etwas, etwa
am Mac, bleibt das Feld None und das Panel zeigt einen Strich. Die Grenzen sind Eigenschaften des Raspberry Pi 4 und
keine Show-Einstellungen, darum stehen sie hier und nicht in settings.py.
"""
import os
import re
import sys
import threading
import time
from collections import deque

SAMPLE_S = 2.0                     # alle 2 s messen
HIST_EVERY = 5                     # jede 5. Messung (10 s) in den Verlauf
HIST_LEN = 360                     # 360 Punkte = die letzte Stunde
SLOW_EVERY = 30                    # vcgencmd, systemctl und Sicherung nur jede Minute (braucht je einen eigenen Prozess)
TARGET_FPS = 40.0                  # wie FRAME_HZ in show.py
BUDGET_MS = 25.0                   # Zeit fuer ein Bild
LATE_S = 0.050                     # mehr als 50 ms zwischen zwei Bildern (2 Bilder) = sichtbarer Aussetzer

# Grenzen (Achtung, Kritisch). Der Pi 4 bremst sich ab 80 Grad leicht und ab 85 Grad stark selbst.
TEMP = (70.0, 80.0)
CORE = (85.0, 98.0)                # staerkster Kern, Mittel ueber 10 s: die Show ist Python und nutzt praktisch einen Kern
IOWAIT = (20.0, 40.0)              # Warten auf den Speicher in Prozent aller Kerne (25 = ein Kern wartet nur noch): hoch = Karte langsam oder am Ende
MEM_FREE = (25.0, 10.0)            # RAM verfuegbar in Prozent
DISK_FREE = (15.0, 5.0)            # Speicher frei in Prozent
FPS = (36.0, 30.0)
WORK = (15.0, 22.0)                # Rechenzeit je Bild in ms, Mittel
LATE = (3, 30)                     # Aussetzer in der letzten Minute
BACKUP_H = 48.0                    # die Sicherung laeuft taeglich: nach 2 Tagen stimmt etwas nicht


class FrameStats:
    """Takt der Show, von der Hauptschleife mit note() gefuettert. Sehr klein, damit das Messen den Takt nicht stoert."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last = None
        self.total = self.late_total = 0
        self._reset()

    def _reset(self):
        self.n, self.late, self.work_sum, self.work_max, self.gap_max = 0, 0, 0.0, 0.0, 0.0

    def note(self, start, end):
        """start und end: time.perf_counter() vor und nach Show.update()."""
        with self._lock:
            gap = 0.0 if self._last is None else start - self._last
            self._last = start
            work = end - start
            self.n += 1
            self.total += 1
            self.work_sum += work
            self.work_max = max(self.work_max, work)
            self.gap_max = max(self.gap_max, gap)
            if gap > LATE_S:
                self.late += 1
                self.late_total += 1

    def take(self):
        """Zahlen seit dem letzten Aufruf abholen."""
        with self._lock:
            out = {"n": self.n, "late": self.late, "work_sum": self.work_sum, "work_max": self.work_max,
                   "gap_max": self.gap_max, "total": self.total, "late_total": self.late_total}
            self._reset()
        return out


class StallWatch:
    """Spuerhund fuer Haenger (Fehlersuche 06.11.2026): ein eigener Faden schlaeft 20 ms. Wacht er mehr als 60 ms zu spaet
    auf, hat jemand Python blockiert (z. B. json.dumps ueber eine riesige Liste), und er merkt sich, wo die anderen Faeden
    gerade stehen: der Schuldige ist meist noch in derselben Funktion. Nur Messung, wirkt nicht aufs Licht."""

    def __init__(self, period=0.02, limit=0.06, window=60.0, here=None):
        self.period, self.limit, self.window = period, limit, window
        self.here = here or os.path.dirname(os.path.abspath(__file__))
        self.events = deque()                       # (Zeit, Verspaetung in s, [Orte])
        self.lock = threading.Lock()
        self.ident = None

    def _where(self, frame):
        """Innerste Stelle im eigenen Programm (pi/), sonst die innerste ueberhaupt: 'datei.py:funktion:zeile'."""
        first = None
        f = frame
        while f is not None:
            fn = f.f_code.co_filename
            loc = f"{os.path.basename(fn)}:{f.f_code.co_name}:{f.f_lineno}"
            first = first or loc
            if fn.startswith(self.here) and not fn.endswith("health.py"):
                return loc
            f = f.f_back
        return first or "?"

    def note(self, late, frames, names, now):
        """Einen Haenger festhalten. frames = sys._current_frames(), names = Faden-Nummer -> Name."""
        where = sorted({f"{names.get(t, t)}@{self._where(fr)}" for t, fr in frames.items() if t != self.ident})
        with self.lock:
            self.events.append((now, late, where))
            while self.events and now - self.events[0][0] > self.window:
                self.events.popleft()

    def report(self, now):
        """Die haeufigsten Stellen der letzten Minute: [{where, n, max_ms}], dazu Anzahl und laengster Haenger."""
        with self.lock:
            ev = [e for e in self.events if now - e[0] <= self.window]
        count = {}
        for _t, late, where in ev:
            for w in where:
                n, mx = count.get(w, (0, 0.0))
                count[w] = (n + 1, max(mx, late))
        top = sorted(count.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[:8]
        return {"n": len(ev), "max_ms": round(max((e[1] for e in ev), default=0.0) * 1000.0, 1),
                "top": [{"where": w, "n": n, "max_ms": round(mx * 1000.0, 1)} for w, (n, mx) in top]}

    def run(self, stop=None):
        self.ident = threading.get_ident()
        while stop is None or not stop.is_set():
            t0 = time.perf_counter()
            time.sleep(self.period)
            late = time.perf_counter() - t0 - self.period
            if late > self.limit:
                names = {t.ident: t.name for t in threading.enumerate()}
                self.note(late, sys._current_frames(), names, time.monotonic())


class ReqStats:
    """Wie lange die Anfragen ans Panel dauern (Fehlersuche): die langsamsten der letzten Minute je Adresse und Befehl."""

    def __init__(self, window=60.0):
        self.window, self.items, self.lock = window, deque(), threading.Lock()

    def note(self, key, dt, now):
        with self.lock:
            self.items.append((now, key, dt))
            while self.items and now - self.items[0][0] > self.window:
                self.items.popleft()

    def report(self, now):
        with self.lock:
            it = [x for x in self.items if now - x[0] <= self.window]
        agg = {}
        for _t, k, dt in it:
            n, mx, tot = agg.get(k, (0, 0.0, 0.0))
            agg[k] = (n + 1, max(mx, dt), tot + dt)
        top = sorted(agg.items(), key=lambda kv: -kv[1][1])[:8]
        return [{"what": k, "n": n, "max_ms": round(mx * 1000.0, 1), "sum_ms": round(tot * 1000.0)} for k, (n, mx, tot) in top]


def clk_tck():
    """Takte pro Sekunde der Zeiten in /proc. Windows kennt os.sysconf nicht: dann der Linux-Standard 100."""
    try:
        return os.sysconf("SC_CLK_TCK")
    except (AttributeError, ValueError, OSError):
        return 100


def _text(root, path):
    try:
        with open(os.path.join(root, path.lstrip("/"))) as f:
            return f.read()
    except OSError:
        return ""


def read_cpu_times(root):
    """Liste (Gesamt, dann je Kern) aus /proc/stat mit (Summe, Leerlauf, Warten auf Speicher)."""
    out = []
    for line in _text(root, "proc/stat").splitlines():
        p = line.split()
        if p and p[0].startswith("cpu"):
            try:
                v = [int(x) for x in p[1:9]]
            except ValueError:
                continue
            if len(v) >= 5:
                out.append((sum(v), v[3], v[4]))
    return out


def read_kv_kb(text):
    """'Name:  123 kB' -> {Name: 123}"""
    out = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        p = v.split()
        if p and p[0].isdigit():
            out[k] = int(p[0])
    return out


def read_num(root, path, scale=1.0):
    try:
        return float(_text(root, path).split()[0]) * scale
    except (IndexError, ValueError):
        return None


def read_root_dev(root):
    """Das Laufwerk des Wurzelverzeichnisses: (Geraet, schreibgeschuetzt?). Geraet zum Beispiel mmcblk0 oder sda."""
    for line in _text(root, "proc/mounts").splitlines():
        p = line.split()
        if len(p) >= 4 and p[1] == "/" and p[0] != "rootfs":
            m = re.match(r"/dev/(mmcblk\d+|nvme\d+n\d+|[a-z]+?)(p?\d+)?$", p[0])
            dev = m.group(1) if m else ""
            if dev == "root" or not dev or not os.path.isdir(os.path.join(root, "sys/block", dev)):
                dev = next((d for d in ("mmcblk0", "nvme0n1", "sda") if os.path.isdir(os.path.join(root, "sys/block", d))), "")
            return dev, "ro" in p[3].split(",")
    return "", False


def parse_throttled(text):
    """Ausgabe von vcgencmd get_throttled. None = nicht lesbar. Bit 0 Unterspannung, 1 und 2 gebremst, 3 Temperaturgrenze;
    16 bis 19 dasselbe seit dem Start des Pi."""
    m = re.search(r"throttled=0x([0-9a-fA-F]+)", text or "")
    if not m:
        return None
    v = int(m.group(1), 16)
    return {"uv_now": bool(v & 0x1), "thr_now": bool(v & 0xE), "uv_ever": bool(v & 0x10000), "thr_ever": bool(v & 0xE0000)}


def _level(v, limits, low_is_bad=False):
    if v is None:
        return "na"
    warn, crit = limits
    if low_is_bad:
        return "crit" if v < crit else "warn" if v < warn else "ok"
    return "crit" if v >= crit else "warn" if v >= warn else "ok"


def _r(v, n=1):
    return None if v is None else round(v, n)


class Health:
    """Misst mit sample() (alle 2 s aus dem Panel-Thread), info() liefert den letzten Stand fuer /api/health."""

    def __init__(self, show, run, root="/", statvfs=getattr(os, "statvfs", None), disk_path=".", backups=None):
        # Windows kennt os.statvfs nicht: dann keine Angaben zum Speicher (am Pi unveraendert)
        self.show, self.run, self.root, self.statvfs, self.disk_path = show, run, root, statvfs, disk_path
        self.backups = backups or _last_backup
        self.stall, self.reqs = StallWatch(), ReqStats()     # Fehlersuche Haenger: wer blockiert, welche Anfrage dauert lange
        self.prev_cpu, self.prev_proc, self.prev_t = None, None, None
        self.cores = deque(maxlen=5)            # die letzten 10 s je Kern (die Bewertung soll nicht bei jeder Spitze anspringen)
        self.totals = deque(maxlen=HIST_EVERY)
        self.frames = deque(maxlen=30)          # die letzte Minute Bildtakt
        self.errs = deque(maxlen=30)            # die letzte Minute Zaehlerstaende Audio und Senden
        self.hist_cpu = deque(maxlen=HIST_LEN)
        self.hist_temp = deque(maxlen=HIST_LEN)
        self.count = 0
        self.temp_max = None
        self.rss_start = None
        self.power, self.restarts, self.backup = None, None, None
        self.last = {"t": None}

    # ---- Einzelne Messungen ------------------------------------------------------------------------------------------
    def _cpu(self):
        cur = read_cpu_times(self.root)
        prev, self.prev_cpu = self.prev_cpu, cur
        if not cur or not prev or len(prev) != len(cur):
            return None
        use, wait = [], 0.0
        for i, ((a, idle, iow), (a0, idle0, iow0)) in enumerate(zip(cur, prev)):
            d = a - a0
            use.append(100.0 * (d - (idle - idle0) - (iow - iow0)) / d if d > 0 else 0.0)
            if i == 0:
                wait = 100.0 * (iow - iow0) / d if d > 0 else 0.0
        self.cores.append(use[1:])
        self.totals.append(use[0])
        n = len(self.cores)
        avg = [sum(c[i] for c in self.cores) / n for i in range(len(use) - 1)]
        load = _text(self.root, "proc/loadavg").split()[:3]
        try:
            load = [float(x) for x in load]
        except ValueError:
            load = []
        return {"total": _r(use[0]), "cores": [_r(x) for x in use[1:]], "busiest": _r(max(avg)) if avg else None,
                "iowait": _r(wait), "load": load,
                "mhz": _r(read_num(self.root, "sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", 0.001), 0),
                "mhz_max": _r(read_num(self.root, "sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", 0.001), 0)}

    def _mem(self):
        m = read_kv_kb(_text(self.root, "proc/meminfo"))
        rss = read_kv_kb(_text(self.root, "proc/self/status")).get("VmRSS")
        if rss is not None and self.rss_start is None:
            self.rss_start = rss
        if "MemTotal" not in m or "MemAvailable" not in m:
            return None
        return {"total_mb": round(m["MemTotal"] / 1024), "avail_mb": round(m["MemAvailable"] / 1024),
                "swap_total_mb": round(m.get("SwapTotal", 0) / 1024),
                "swap_used_mb": round((m.get("SwapTotal", 0) - m.get("SwapFree", 0)) / 1024),
                "rss_mb": round(rss / 1024) if rss is not None else None,
                "rss_grow_mb": round((rss - self.rss_start) / 1024) if rss is not None else None}

    def _disk(self):
        if self.statvfs is None:
            return None
        try:
            v = self.statvfs(self.disk_path)
        except OSError:
            return None
        dev, ro = read_root_dev(self.root)
        sectors = None
        if dev:
            try:
                sectors = int(_text(self.root, f"sys/block/{dev}/stat").split()[6])       # geschrieben, in 512-Byte-Sektoren
            except (IndexError, ValueError):
                pass
        gb = 1024.0 ** 3
        return {"total_gb": _r(v.f_blocks * v.f_frsize / gb), "free_gb": _r(v.f_bavail * v.f_frsize / gb), "ro": ro,
                "kind": "sd" if dev.startswith("mmc") else "ssd" if dev else "",
                "written_gb": _r(sectors * 512 / gb) if sectors is not None else None}

    def _proc_cpu(self, now):
        """CPU der Show in Prozent eines Kerns (100 = ein Kern ganz belegt)."""
        p = _text(self.root, "proc/self/stat").rpartition(")")[2].split()
        try:
            ticks, threads = int(p[11]) + int(p[12]), int(p[17])
        except (IndexError, ValueError):
            return None, None
        prev, self.prev_proc = self.prev_proc, (ticks, now)
        if prev is None or now <= prev[1]:
            return None, threads
        return _r(100.0 * (ticks - prev[0]) / clk_tck() / (now - prev[1])), threads

    def _frames(self, now, dur):
        fs = getattr(self.show, "frames", None)
        if fs is None:
            return None
        w = fs.take()
        if dur is None:                                  # erste Messung: Dauer des Fensters unbekannt
            return None
        self.frames.append((w["n"], w["late"], w["work_sum"], w["work_max"], w["gap_max"], dur))
        recent = list(self.frames)[-5:]
        n, secs = sum(x[0] for x in recent), sum(x[5] for x in recent)
        if not w["total"]:
            return None
        return {"fps": _r(n / secs) if secs > 0 else None, "work_ms": _r(1000.0 * sum(x[2] for x in recent) / n) if n else None,
                "work_max_ms": _r(1000.0 * max(x[3] for x in self.frames)),
                "gap_max_ms": _r(1000.0 * max(x[4] for x in self.frames)),
                "late_min": sum(x[1] for x in self.frames), "late_total": w["late_total"], "total": w["total"]}

    def _links(self):
        """Audio, Senden, Erreichbarkeit: was die Show schon weiss, nur zusammengetragen."""
        sh = self.show
        src, out = getattr(sh, "src", None), getattr(sh, "output", None)
        xruns = getattr(src, "xruns", None)
        qdrops = getattr(src, "q_drops", None)
        sends = getattr(out, "send_errors", None)
        self.errs.append(((xruns or 0) + (qdrops or 0), sends or 0))
        reach = getattr(sh, "reach", None) or {}
        lk = getattr(sh, "mixxx", None)
        return {"audio_err_min": self.errs[-1][0] - self.errs[0][0] if xruns is not None else None,
                "audio_error": getattr(src, "error", "") or "",
                "send_err_min": self.errs[-1][1] - self.errs[0][1] if sends is not None else None,
                "down": sorted(k for k, v in reach.items() if v is False),
                "known": sum(1 for v in reach.values() if v is not None),
                "net": [{"type": n.get("type"), "up": n.get("up"), "main": n.get("main"), "speed": n.get("speed"), "signal": n.get("signal")}
                        for n in (getattr(sh, "net", None) or []) if n.get("up")],
                "mixxx": (time.time() - lk.last_rx < 3.0) if lk is not None else None}

    def _slow(self):
        """Selten, weil jeweils ein eigener Prozess laeuft."""
        self.power = parse_throttled(self.run(["vcgencmd", "get_throttled"]))
        txt = self.run(["systemctl", "show", "lichtshow", "-p", "NRestarts", "--value"]).strip()
        self.restarts = int(txt) if txt.isdigit() else None
        try:
            self.backup = self.backups()
        except Exception:                                # noqa: BLE001 - die Anzeige darf nie etwas stoeren
            self.backup = None

    # ---- Bewertung ---------------------------------------------------------------------------------------------------
    @staticmethod
    def rate(d):
        """Aus den Messwerten: Ampel je Karte und die Liste der Probleme (schlimmste zuerst, Schluessel fuer texts.py)."""
        st, issues = {}, []

        def add(card, lvl, key, v=None):
            order = ("na", "ok", "warn", "crit")
            if order.index(lvl) > order.index(st.get(card, "na")):
                st[card] = lvl
            if lvl in ("warn", "crit") and key:
                issues.append({"s": lvl, "k": key, "v": v})

        c, m, k, f, p, l = d.get("cpu"), d.get("mem"), d.get("disk"), d.get("frames"), d.get("power"), d.get("links") or {}
        add("temp", _level(d.get("temp"), TEMP), "hl_i_temp", _r(d.get("temp"), 0))
        add("cpu", _level(c and c["busiest"], CORE), "hl_i_cpu", c and _r(c["busiest"], 0))
        add("disk", _level(c and c["iowait"], IOWAIT), "hl_i_iow", c and _r(c["iowait"], 0))
        if m:
            add("mem", _level(100.0 * m["avail_mb"] / m["total_mb"] if m["total_mb"] else None, MEM_FREE, True), "hl_i_mem", m["avail_mb"])
        if k:
            add("disk", _level(100.0 * k["free_gb"] / k["total_gb"] if k["total_gb"] else None, DISK_FREE, True), "hl_i_disk", k["free_gb"])
            add("disk", "crit" if k["ro"] else "ok", "hl_i_ro")
        if f:
            add("frames", _level(f["fps"], FPS, True), "hl_i_fps", f["fps"])
            add("frames", _level(f["work_ms"], WORK), "hl_i_work", f["work_ms"])
            add("frames", _level(f["late_min"], LATE), "hl_i_late", f["late_min"])
        if p:
            add("sys", "crit" if p["uv_now"] else "warn" if p["uv_ever"] else "ok", "hl_i_uv_now" if p["uv_now"] else "hl_i_uv")
            add("sys", "crit" if p["thr_now"] else "warn" if p["thr_ever"] else "ok", "hl_i_thr_now" if p["thr_now"] else "hl_i_thr")
        if l.get("audio_error"):
            add("sys", "crit", "hl_i_aerr")
        if l.get("audio_err_min"):
            add("sys", "warn", "hl_i_audio", l["audio_err_min"])
        if l.get("send_err_min"):
            add("sys", "warn", "hl_i_send", l["send_err_min"])
        if l.get("known"):
            add("sys", "warn" if l.get("down") else "ok", "hl_i_down", ", ".join(l.get("down") or []))
        if d.get("restarts") is not None:
            add("sys", "warn" if d["restarts"] else "ok", "hl_i_restart", d["restarts"])
        b = d.get("backup")
        if b is not None:
            if b.get("age_h") is None:
                add("disk", "warn", "hl_i_nobackup")
            else:
                add("disk", "warn" if b["age_h"] > BACKUP_H else "ok", "hl_i_backup", _r(b["age_h"], 0))
        issues.sort(key=lambda i: i["s"] != "crit")
        worst = "crit" if any(i["s"] == "crit" for i in issues) else "warn" if issues else "ok"
        return worst, st, issues

    # ---- Messen und ausgeben -----------------------------------------------------------------------------------------
    def sample(self, now=None):
        now = time.monotonic() if now is None else now
        dur = (now - self.prev_t) if self.prev_t is not None else None
        self.prev_t = now
        if self.count % SLOW_EVERY == 0:
            self._slow()
        temp = read_num(self.root, "sys/class/thermal/thermal_zone0/temp", 0.001)
        if temp is not None:
            self.temp_max = temp if self.temp_max is None else max(self.temp_max, temp)
        cpu = self._cpu()
        pcpu, threads = self._proc_cpu(now)
        up = read_num(self.root, "proc/uptime")
        started = getattr(self.show, "started_wall", None)
        d = {"t": round(time.time()), "uptime_s": _r(up, 0), "show_s": round(time.time() - started) if started else None,
             "cpu": cpu, "temp": _r(temp), "temp_max": _r(self.temp_max), "mem": self._mem(), "disk": self._disk(),
             "proc_cpu": pcpu, "threads": threads, "frames": self._frames(now, dur), "power": self.power,
             "restarts": self.restarts, "backup": self.backup, "links": self._links(),
             "stalls": self.stall.report(now), "slow_req": self.reqs.report(now)}
        d["level"], d["st"], d["issues"] = self.rate(d)
        self.show.health_level = d["level"]              # Farbe des Herzens auf der Hauptseite
        self.count += 1
        if self.count % HIST_EVERY == 0:
            self.hist_cpu.append(_r(sum(self.totals) / len(self.totals), 0) if self.totals else None)
            self.hist_temp.append(_r(temp))
        self.last = d
        return d

    def info(self):
        return dict(self.last, hist={"cpu": list(self.hist_cpu), "temp": list(self.hist_temp), "step_s": SAMPLE_S * HIST_EVERY})


def _last_backup():
    """Alter der neuesten Sicherung in Stunden; age_h None = es gibt keine."""
    import backup
    items = backup.list_backups(backup.load_conf())
    if not items:
        return {"age_h": None}
    t = time.mktime(time.strptime(items[0]["time"], "%Y-%m-%d %H:%M"))
    return {"age_h": max(0.0, (time.time() - t) / 3600.0)}


def watch(hl, every=SAMPLE_S):
    while True:
        try:
            hl.sample()
        except Exception:                                # die Anzeige darf nie etwas stoeren
            pass
        time.sleep(every)
