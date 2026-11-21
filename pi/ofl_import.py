#!/usr/bin/env python3
"""
ofl_import.py - Geraetetypen aus der Open Fixture Library (open-fixture-library.org) uebernehmen (Wunsch von Markus, 21.11.2026).

Zwei Wege, beide enden in einem eigenen Geraetetyp in fixtures_user.json (wie "Geraetetypen -> + Neuer Typ"):
  * Datenbank: Hersteller -> Geraet -> Modus aus dem Panel waehlen. Der Licht-Rechner fragt die Datenbank nur auf
    Knopfdruck ab (Liste der Hersteller, Geraete eines Herstellers, ein Geraet), es geht nichts Eigenes hinaus.
  * Datei: eine OFL-Datei (.json, auf der Seite des Geraets "Download -> OFL") oder eine QLC+-Datei (.qxf).

Die Dateien sind fremde, ungepruefte Daten. Daraus wird nur ein Typ mit Kanalnamen, Standardwerten und Grenzen gebaut,
alles gegen die Sicherheitsregeln:
  * Laser (Kategorie "Laser") und Nebel/Hazer (Kategorie "Smoke"/"Hazer" oder Nebel-Kanal): ganzer Typ gesperrt
    (locked, Gruppe "gesperrt", sendet immer 0). Nie Laser-Freigabe (laser_channels), nie Handbetrieb (manual_allowed).
  * Kanaele mit "laser" im Namen in anderen Geraeten: gesperrt (locked_channels), immer 0.
  * Strobe-/Shutter-Kanaele: fest auf den Bereich "offen" (sonst "keine Funktion", sonst 0), damit nie ein Strobo
    laeuft (kein Einzel-Strobe, keine Ausnahme). Ohne bekannten Ruhewert ein Hinweis zum Pruefen am Geraet.
  * Programm-, Sound-, Reset- und Wartungskanaele (Effect, Maintenance, Generic ...): fest auf "keine Funktion".
  * Kanaele, die das Licht nicht kennt, heissen x_..., damit das Licht sie nie anspricht; sie bleiben beim Standardwert.
Matrix-Modi (Pixel-Vorlagen) werden nicht unterstuetzt.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://open-fixture-library.org"
AGENT = "Light-Butler Lichtsteuerung"
MAX_BYTES = 2_000_000
CACHE_S = 24 * 3600
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
WHEEL_NAMES = ("white", "red", "yellow", "blue", "green", "orange", "purple", "lightblue")
GOBO_NAMES = ("star", "spiral", "dots3", "triangle", "gobo5")
COLOR_PARAM = {"red": "r", "green": "g", "blue": "b", "white": "w", "cold white": "w", "uv": "uv",
               "warm white": "ww", "amber": "amber", "lime": "lime", "cyan": "cyan", "magenta": "magenta",
               "yellow": "yellow", "indigo": "indigo"}
# Kanalarten, die eigene Programme, Ton-Steuerung, Reset oder Einstellungen am Geraet ausloesen koennen
RISKY = {"Effect", "SoundSensitivity", "Maintenance", "Generic", "ColorPreset", "ColorTemperature",
         "PanContinuous", "TiltContinuous", "BladeInsertion", "BladeRotation", "BladeSystemRotation", "IrisEffect",
         "FrostEffect", "BeamPosition"}
WHEEL = {"WheelSlot", "WheelRotation", "WheelShake", "WheelSlotRotation"}
STROBE = {"ShutterStrobe", "StrobeSpeed", "StrobeDuration"}
FOG = {"Fog", "FogOutput", "FogType"}


# ---- Abruf aus der Datenbank -------------------------------------------------------------------------------
class Catalog:
    """Fragt die Open Fixture Library ab und merkt sich die Antworten einen Tag im Speicher."""

    def __init__(self, opener=urllib.request.urlopen, timeout=10.0):
        self.opener, self.timeout, self.cache = opener, timeout, {}

    def _get(self, path, body=None):
        ck = path + ("?" + json.dumps(body, sort_keys=True) if body is not None else "")
        hit = self.cache.get(ck)
        if hit and time.time() - hit[0] < CACHE_S:
            return hit[1]
        hdr = {"User-Agent": AGENT, "Accept": "application/json"}
        data = None
        if body is not None:
            hdr["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        req = urllib.request.Request(BASE + path, data=data, headers=hdr)
        try:
            with self.opener(req, timeout=self.timeout) as r:
                raw = r.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as e:
            raise ValueError("In der Fixture-Datenbank nicht gefunden" if e.code == 404 else "Fixture-Datenbank: Fehler %d" % e.code) from None
        except Exception as e:                                   # noqa: BLE001
            raise ValueError("Die Fixture-Datenbank ist nicht erreichbar (Internet am Licht-Rechner?): %s" % e) from None
        if len(raw) > MAX_BYTES:
            raise ValueError("Antwort der Datenbank zu gross")
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ValueError("Antwort der Datenbank nicht lesbar") from None
        if len(self.cache) > 500:
            self.cache.clear()
        self.cache[ck] = (time.time(), data)
        return data

    def manufacturers(self):
        d = self._get("/api/v1/manufacturers")
        out = [{"key": k, "name": str(v.get("name") or k)[:60], "count": int(v.get("fixtureCount") or 0)}
               for k, v in (d.items() if isinstance(d, dict) else []) if KEY_RE.match(str(k)) and isinstance(v, dict)]
        return sorted(out, key=lambda x: x["name"].lower())

    def search(self, q, man=""):
        """Suche in der ganzen Datenbank (wie das Suchfeld auf open-fixture-library.org), auf Wunsch nur bei einem Hersteller."""
        q = " ".join(str(q or "").split())[:60]
        if len(q) < 2:
            raise ValueError("Bitte mindestens 2 Zeichen eingeben")
        if man and not KEY_RE.match(str(man)):
            raise ValueError("Unbekannter Hersteller")
        d = self._get("/api/v1/get-search-results", {"searchQuery": q, "manufacturersQuery": [man] if man else [], "categoriesQuery": []})
        out = []
        for f in d if isinstance(d, list) else []:
            k = str(f.get("key", "")) if isinstance(f, dict) else ""
            m, _, fx = k.partition("/")
            if KEY_RE.match(m) and KEY_RE.match(fx):
                out.append({"man": m, "key": fx, "name": str(f.get("name") or k)[:100]})
        return out[:300]

    def fixtures(self, man):
        if not KEY_RE.match(str(man or "")):
            raise ValueError("Unbekannter Hersteller")
        d = self._get("/api/v1/manufacturers/" + urllib.parse.quote(man))
        out = []
        for f in (d.get("fixtures") if isinstance(d, dict) else None) or []:
            if isinstance(f, dict) and KEY_RE.match(str(f.get("key", ""))):
                out.append({"key": f["key"], "name": str(f.get("name") or f["key"])[:80],
                            "categories": [str(c)[:30] for c in (f.get("categories") or [])][:8]})
        return {"name": str(d.get("name") or man)[:60] if isinstance(d, dict) else man, "fixtures": out}

    def fixture(self, man, key):
        if not (KEY_RE.match(str(man or "")) and KEY_RE.match(str(key or ""))):
            raise ValueError("Unbekanntes Geraet")
        d = self._get("/%s/%s.json" % (urllib.parse.quote(man), urllib.parse.quote(key)))
        if not isinstance(d, dict) or not isinstance(d.get("modes"), list):
            raise ValueError("Geraet nicht gefunden")
        return d


# ---- Lesen der Dateien -------------------------------------------------------------------------------------
def _num(v, default=0):
    """DMX-Wert aus OFL ("50%", 127, "127") -> 0..255."""
    try:
        if isinstance(v, str) and v.strip().endswith("%"):
            return max(0, min(255, int(round(float(v.strip()[:-1]) * 2.55))))
        return max(0, min(255, int(v)))
    except (TypeError, ValueError):
        return default


def _caps(ch):
    caps = [ch["capability"]] if isinstance(ch.get("capability"), dict) else ch.get("capabilities") or []
    out = []
    for c in caps:
        if not isinstance(c, dict) or not isinstance(c.get("type"), str):
            continue
        rng = c.get("dmxRange") if isinstance(c.get("dmxRange"), list) and len(c["dmxRange"]) == 2 else [0, 255]
        out.append(dict(c, lo=_num(rng[0]), hi=_num(rng[1], 255)))
    return out


def _pixel_keys(fx):
    """Pixel einer Matrix in der Reihenfolge X, dann Y, dann Z (nur das, was die Datei angibt)."""
    mx = fx.get("matrix") if isinstance(fx.get("matrix"), dict) else {}
    if isinstance(mx.get("pixelKeys"), list):
        out = []
        for z in mx["pixelKeys"]:
            for y in z if isinstance(z, list) else []:
                out += [str(k) for k in (y if isinstance(y, list) else []) if k is not None]
        return out
    pc = mx.get("pixelCount")
    if isinstance(pc, list) and len(pc) == 3 and all(isinstance(n, int) for n in pc):
        if pc[1] == 1 and pc[2] == 1 and 1 <= pc[0] <= 64:
            return [str(i) for i in range(1, pc[0] + 1)]
        raise ValueError("Matrix mit mehreren Reihen wird nicht unterstuetzt, bitte einen anderen Modus waehlen")
    return []


def _natural(k):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", k)]


def expand(fx, chans):
    """Kanalliste eines Modus mit aufgeloesten Matrix-Einschueben (insert: matrixChannels) -> Liste von Kanalnamen."""
    out = []
    groups = ((fx.get("matrix") or {}).get("pixelGroups") or {}) if isinstance(fx.get("matrix"), dict) else {}
    for c in chans:
        if c is None or isinstance(c, str):
            out.append(c)
            continue
        if not isinstance(c, dict) or c.get("insert") != "matrixChannels" or not isinstance(c.get("templateChannels"), list):
            raise ValueError("Unbekannter Eintrag in der Kanalliste")
        rf = c.get("repeatFor")
        if isinstance(rf, list):
            px = [str(k) for k in rf]
        elif rf == "eachPixelGroup":
            px = list(groups)
        elif rf in ("eachPixelXYZ", "eachPixelXZY", "eachPixelYXZ", "eachPixelYZX", "eachPixelZXY", "eachPixelZYX"):
            px = _pixel_keys(fx)
        elif rf == "eachPixelABC":
            px = sorted(_pixel_keys(fx), key=_natural)
        else:
            raise ValueError("Matrix-Modus wird nicht unterstuetzt, bitte einen anderen Modus waehlen")
        tcs = [str(t) for t in c["templateChannels"] if t is not None]
        if c.get("channelOrder") == "perChannel":
            out += [t.replace("$pixelKey", k) for t in tcs for k in px]
        else:
            out += [t.replace("$pixelKey", k) for k in px for t in tcs]
    return out


def _channel(fx, key):
    """Kanal nach Namen: aus availableChannels oder aus einer Matrix-Vorlage (templateChannels mit $pixelKey)."""
    av = fx.get("availableChannels") if isinstance(fx.get("availableChannels"), dict) else {}
    if key in av:
        return av[key]
    targets = []                                             # umschaltbarer Kanal (switchChannels): alle Ziele zusammen
    for ch in av.values():
        for c in (ch.get("capabilities") or []) if isinstance(ch, dict) else []:
            sw = c.get("switchChannels") if isinstance(c, dict) else None
            if isinstance(sw, dict) and isinstance(sw.get(key), str) and sw[key] in av and sw[key] not in targets:
                targets.append(sw[key])
    if targets:
        caps = []
        for t in targets:
            caps += _caps(av[t])
        return {"capabilities": [dict(c, dmxRange=[c["lo"], c["hi"]]) for c in caps], "switch": True}
    for t, ch in (fx.get("templateChannels") or {}).items():
        if "$pixelKey" in t:
            a, b = t.split("$pixelKey", 1)
            if key.startswith(a) and key.endswith(b) and len(key) > len(a) + len(b):
                return ch
    return None


def _fine_aliases(fx):
    fine = {}
    av = fx.get("availableChannels") if isinstance(fx.get("availableChannels"), dict) else {}
    for k, ch in av.items():
        if isinstance(ch, dict):
            for a in ch.get("fineChannelAliases") or []:
                fine[str(a)] = k
    return fine


def modes(fx):
    """Modi eines Geraets fuer die Auswahl: [{name, channels}]"""
    out = []
    for m in fx.get("modes") or []:
        if isinstance(m, dict) and isinstance(m.get("channels"), list):
            try:
                n, bad = len(expand(fx, m["channels"])), False
            except ValueError:
                n, bad = len(m["channels"]), True
            out.append({"name": str(m.get("name") or m.get("shortName") or "?")[:60], "channels": n, "matrix": bad})
    return out


def _slug(text, n=24):
    s = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
               .replace("ß", "ss")).strip("_")
    return s[:n].strip("_") or "k"


def _rng_of(caps, pred):
    for c in caps:
        if pred(c):
            return [c["lo"], c["hi"]]
    return None


def _hue_name(hexes):
    """Farbe eines Farbrad-Fachs -> Name der Light-Butler-Farbe (white, red, ...)."""
    try:
        h = str(hexes[0]).lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (IndexError, ValueError, TypeError):
        return None
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 0.2:
        return "white"
    if mx == r:
        hue = (60 * ((g - b) / (mx - mn))) % 360
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn)) + 120
    else:
        hue = 60 * ((r - g) / (mx - mn)) + 240
    if mn > 0.55:
        return "lightblue" if 170 <= hue <= 260 else "white"
    for lim, name in ((15, "red"), (45, "orange"), (75, "yellow"), (165, "green"), (200, "lightblue"),
                      (255, "blue"), (330, "purple"), (360, "red")):
        if hue < lim:
            return name
    return "red"


def _wheel_presets(caps, wheels, kind, wname):
    """Farbrad/Goborad: Namen der Light-Butler-Presets -> DMX-Wert (Mitte des Fachs). Fehlende Namen = offen."""
    slots = ((wheels or {}).get(wname) or {}).get("slots") or []
    found = []
    for c in caps:
        if c["type"] != "WheelSlot":
            continue
        n = c.get("slotNumber")
        if not isinstance(n, (int, float)) or n != int(n) or not 1 <= n <= len(slots):
            continue
        s = slots[int(n) - 1] if isinstance(slots[int(n) - 1], dict) else {}
        found.append((s.get("type"), s, (c["lo"] + c["hi"]) // 2))
    if not found:
        return None
    open_v = next((v for t, _, v in found if t == "Open"), found[0][2])
    if kind == "colorwheel":
        p = {}
        for t, s, v in found:
            nm = "white" if t == "Open" else _hue_name(s.get("colors") or []) if t == "Color" else None
            if nm and nm not in p:
                p[nm] = v
        return {n: p.get(n, open_v) for n in WHEEL_NAMES}
    gobos = [v for t, _, v in found if t not in ("Open", None)]
    p = {"open": open_v}
    for i, n in enumerate(GOBO_NAMES):
        p[n] = gobos[i % len(gobos)] if gobos else open_v
    return p


def convert(fx, mode_index, maker=""):
    """OFL-Geraet (dict) und Nummer des Modus -> (Typ fuer fixtures_user.json, Hinweise). Wirft ValueError."""
    import fixture_export
    if fixture_export.is_lb(fx):                                   # eigene Light-Butler-Datei (Export je Fixture)
        if mode_index != 0:
            raise ValueError("Unbekannter Modus")
        return fixture_export.lb_to_type(fx)
    ms = [m for m in fx.get("modes") or [] if isinstance(m, dict) and isinstance(m.get("channels"), list)]
    if not isinstance(mode_index, int) or not 0 <= mode_index < len(ms):
        raise ValueError("Unbekannter Modus")
    mode = ms[mode_index]
    chans = expand(fx, mode["channels"])
    if not 1 <= len(chans) <= 64:
        raise ValueError("Ein Typ braucht 1 bis 64 Kanaele (dieser Modus hat %d)" % len(chans))
    fine = _fine_aliases(fx)
    avail = {k: _channel(fx, k) for k in chans if k is not None and _channel(fx, k) is not None}
    cats = [str(c) for c in fx.get("categories") or []]
    laser_px = set()
    for g, keys in (((fx.get("matrix") or {}).get("pixelGroups") or {}) if isinstance(fx.get("matrix"), dict) else {}).items():
        if "laser" in str(g).lower() and isinstance(keys, list):
            laser_px |= {str(k) for k in keys}
    notes = []
    whole_lock = None
    def is_laser(key):
        return "laser" in str(key).lower() or any(str(key).startswith(k + " ") or str(key).endswith(" " + k) for k in laser_px)

    if "Laser" in cats and (len(cats) == 1 or not any(is_laser(k) for k in chans if k)):
        whole_lock = "Laser: der Typ bleibt ganz gesperrt und sendet immer 0 (Sicherheitsregel)."
    elif "Smoke" in cats or "Hazer" in cats:
        whole_lock = "Nebel/Hazer: der Typ bleibt gesperrt. Fuer den Nebel-Knopf den mitgelieferten Typ hazer nehmen."
    for key in chans:
        if key in avail and any(c["type"] in FOG for c in _caps(avail[key])):
            whole_lock = whole_lock or "Nebel-Kanal gefunden: der Typ bleibt gesperrt. Fuer den Nebel-Knopf den Typ hazer nehmen."
    # Farben zaehlen: zwei oder mehr gleiche Farbkanaele = Zellen (r1, g1, ... r2, g2, ...)
    color_of = {}
    for key in chans:
        ch = avail.get(key) if key else None
        if isinstance(ch, dict):
            cs = [c for c in _caps(ch) if c["type"] != "NoFunction"]
            if len(cs) == 1 and cs[0]["type"] == "ColorIntensity":
                color_of[key] = COLOR_PARAM.get(str(cs[0].get("color", "")).lower())
    count = {}
    for p in color_of.values():
        if p:
            count[p] = count.get(p, 0) + 1
    cells = max([count.get(p, 0) for p in ("r", "g", "b")] + [0]) >= 2
    uv_rows = not cells and count.get("uv", 0) >= 2 and not any(count.get(p) for p in ("r", "g", "b"))
    if count.get("ww") and not count.get("w"):
        color_of = {k: ("w" if v == "ww" else v) for k, v in color_of.items()}
    seen_color = {}
    m, desc, defaults, limits, presets, locked = {}, {}, {}, {}, {}, []
    used = set()

    def uniq(p):
        q, i = p, 2
        while q in used:
            q, i = "%s%d" % (p, i), i + 1
        used.add(q)
        return q

    params = [None] * len(chans)
    for idx, key in enumerate(chans):                       # erst alle groben Kanaele, die feinen danach
        if key is None:
            params[idx] = uniq("x_frei_%d" % (idx + 1))
            continue
        if key in fine and key not in avail:
            continue
        ch = avail.get(key)
        if not isinstance(ch, dict):
            raise ValueError("Kanal %s fehlt in der Datei" % key)
        caps = _caps(ch)
        real = {c["type"] for c in caps} - {"NoFunction"}
        nm = str(key)[:60]
        dv = _num(ch.get("defaultValue", 0))
        risky_caps = real & (RISKY | FOG)
        if is_laser(key) and not whole_lock:
            p = uniq("x_" + _slug(nm, 20))
            locked.append(p)
            desc[p] = nm + ": Laser, gesperrt (immer 0)"
        elif real == {"Intensity"}:
            p = uniq("dimmer")
            desc[p] = nm
        elif real == {"ColorIntensity"} and color_of.get(key):
            c = color_of[key]
            if (cells and c in ("r", "g", "b", "w", "uv")) or (uv_rows and c == "uv"):
                seen_color[c] = seen_color.get(c, 0) + 1
                p = uniq("%s%d" % (c, seen_color[c]))
            else:
                p = uniq(c if c in ("r", "g", "b", "w", "uv") else "x_" + c)
            desc[p] = nm
        elif real in ({"Pan"}, {"Tilt"}):
            ax = "pan" if real == {"Pan"} else "tilt"
            p = uniq(ax)
            desc[p] = nm
            dv = _num(ch.get("defaultValue", "50%"), 127)
        elif real and real <= STROBE:
            safe = (_rng_of(caps, lambda c: c.get("shutterEffect") == "Open")
                    or _rng_of(caps, lambda c: c["type"] == "NoFunction")
                    or _rng_of(caps, lambda c: c.get("shutterEffect") == "Closed"))
            if safe is None:
                safe = [0, 0]
                notes.append("%s: in der Datenbank steht kein Wert ohne Strobo, der Kanal steht fest auf 0. Bitte am Geraet pruefen." % nm)
            p = uniq("shutter" if safe[1] == 255 else "strobe")
            limits[p] = safe
            dv = safe[1] if safe[1] == 255 else safe[0]
            desc[p] = "%s: fest auf %d bis %d (ohne Strobo)" % (nm, safe[0], safe[1])
        elif "WheelSlot" in real and real <= WHEEL:
            wn = next((c.get("wheel") for c in caps if c.get("wheel")), key)
            slots = ((fx.get("wheels") or {}).get(wn) or {}).get("slots") or []
            is_color = any(isinstance(s, dict) and s.get("type") == "Color" for s in slots)
            kind = "colorwheel" if is_color else "gobo"
            pr = _wheel_presets(caps, fx.get("wheels"), kind, wn)
            if kind not in used and pr:
                p = uniq(kind)
                presets[p] = pr
                dv = pr["white" if kind == "colorwheel" else "open"]
            else:
                p = uniq("x_" + _slug(nm, 20))
            desc[p] = nm
        elif real <= {"WheelSlotRotation"} and real and "gobo_rot" not in used:
            p = uniq("gobo_rot")
            stop = _rng_of(caps, lambda c: c["type"] == "NoFunction" or c.get("speed") == "stop")
            dv = stop[0] if stop else 0
            desc[p] = nm
        elif real in ({"Zoom"}, {"Focus"}, {"PanTiltSpeed"}, {"Iris"}, {"Frost"}):
            p = uniq({"Zoom": "zoom", "Focus": "focus", "PanTiltSpeed": "pt_speed", "Iris": "iris", "Frost": "frost"}[next(iter(real))])
            desc[p] = nm
        elif real and real <= {"Prism", "PrismRotation"} and "prism" not in used:
            p = uniq("prism")
            off = _rng_of(caps, lambda c: c["type"] == "NoFunction")
            dv = off[0] if off else 0
            desc[p] = nm
        else:
            p = uniq("x_" + _slug(nm, 20))
            if (risky_caps or not real) and ch.get("switch"):
                safe = [0, 0]                                 # umschaltbarer Kanal: Bereiche gelten je nach anderem Kanal
                notes.append("%s: wechselt je nach anderem Kanal die Bedeutung, steht fest auf 0." % nm)
                limits[p] = safe
                dv = 0
                desc[p] = "%s: fest auf 0 (keine Programme)" % nm
            elif risky_caps or not real:
                safe = (_rng_of([c for c in caps if c["lo"] <= dv <= c["hi"]], lambda c: c["type"] == "NoFunction")
                        or _rng_of(caps, lambda c: c["type"] == "NoFunction")
                        or _rng_of(caps, lambda c: c["type"] not in RISKY | FOG | STROBE))
                if safe is None:
                    safe = [0, 0]
                    if caps:
                        notes.append("%s: kein Wert ohne Programm bekannt, der Kanal steht fest auf 0. Bitte am Geraet pruefen." % nm)
                limits[p] = safe
                dv = min(max(dv, safe[0]), safe[1])
                desc[p] = "%s: fest auf %d bis %d (keine Programme)" % (nm, safe[0], safe[1])
            else:
                desc[p] = nm + " (vom Licht nicht benutzt)"
        params[idx] = p
        if dv:
            defaults[p] = dv
    for idx, key in enumerate(chans):                       # feine Kanaele: pan_fine, tilt_fine, dimmer_fine ...
        if params[idx] is None:
            coarse = fine[key]
            ci = next((i for i, k in enumerate(chans) if k == coarse), None)
            base = params[ci] if ci is not None else "x_" + _slug(coarse, 15)
            p = uniq((base if base.startswith("x_") or base in ("pan", "tilt") else "x_" + base) + "_fine")
            params[idx] = p
            desc[p] = str(key)[:60] + " (fein)"
    for i, p in enumerate(params, 1):
        m[p] = i
    if any(k in m for k in "rgb") and not all(k in m for k in "rgb"):
        for k in "rgb":                                       # unvollstaendige Farbe: das Licht kann sie nicht mischen
            if k in m:
                old = k
                new = uniq("x_" + k)
                m[new] = m.pop(old)
                desc[new] = desc.pop(old, old)
        notes.append("Nicht alle drei Farben Rot, Gruen, Blau vorhanden: die Farbkanaele bleiben unbenutzt.")
    if any(k in m for k in ("r", "r1", "uv1")) and "dimmer" in m:
        defaults["dimmer"] = 255                              # Farbgeraete: Licht kommt aus den Farbkanaelen
    name = str(fx.get("name") or "Geraet")[:50]
    t = {"channels": len(chans), "map": m, "label": ("%s (%s)" % (name, str(mode.get("shortName") or mode.get("name") or ""))[:60]),
         "desc": {k: v[:300] for k, v in desc.items()}}
    if maker:
        t["maker"] = str(maker)[:60]
    if defaults:
        t["defaults"] = {k: v for k, v in defaults.items() if k in m}
    if limits:
        t["safe_limits"] = {k: v for k, v in limits.items() if k in m}
    if presets:
        t["presets"] = presets
    if whole_lock:
        t["locked"] = True
        notes.insert(0, whole_lock)
    elif locked:
        t["locked_channels"] = [p for p in locked if p in m]
        notes.append("Laser-Kanaele gesperrt: " + ", ".join(t["locked_channels"]))
    if "pan" in m and "tilt" in m:
        notes.append("Moving Head: leuchtet in AUTO wie der Vega, bleibt aber in der Mittelstellung. Bewegen braucht eingemessene "
                     "Grenzen (limits_norm in fixtures.yaml, wie beim Vega).")
    return t, notes


# ---- QLC+ (.qxf) -> OFL-aehnlich ------------------------------------------------------------------------------
QLC_PRESET = {"IntensityMasterDimmer": ("Intensity", None), "IntensityDimmer": ("Intensity", None),
              "IntensityRed": ("ColorIntensity", "Red"), "IntensityGreen": ("ColorIntensity", "Green"),
              "IntensityBlue": ("ColorIntensity", "Blue"), "IntensityWhite": ("ColorIntensity", "White"),
              "IntensityUV": ("ColorIntensity", "UV"), "IntensityAmber": ("ColorIntensity", "Amber"),
              "IntensityLime": ("ColorIntensity", "Lime"), "IntensityCyan": ("ColorIntensity", "Cyan"),
              "IntensityMagenta": ("ColorIntensity", "Magenta"), "IntensityYellow": ("ColorIntensity", "Yellow"),
              "PositionPan": ("Pan", None), "PositionTilt": ("Tilt", None), "ShutterStrobeSlowFast": ("ShutterStrobe", None),
              "ShutterStrobeFastSlow": ("ShutterStrobe", None), "BeamZoomSmallBig": ("Zoom", None),
              "BeamZoomBigSmall": ("Zoom", None), "BeamFocusNearFar": ("Focus", None), "BeamFocusFarNear": ("Focus", None),
              "SpeedPanTiltFastSlow": ("PanTiltSpeed", None), "SpeedPanTiltSlowFast": ("PanTiltSpeed", None)}
QLC_FINE = {"PositionPanFine": "PositionPan", "PositionTiltFine": "PositionTilt", "IntensityMasterDimmerFine": "IntensityMasterDimmer",
            "IntensityDimmerFine": "IntensityDimmer"}
QLC_GROUP = {"Intensity": "Intensity", "Pan": "Pan", "Tilt": "Tilt", "Shutter": "ShutterStrobe", "Speed": "Speed",
             "Gobo": "WheelSlot", "Colour": "WheelSlot", "Prism": "Prism", "Beam": "Zoom", "Effect": "Effect",
             "Maintenance": "Maintenance", "Nothing": "NoFunction"}


def qxf_to_ofl(text):
    """QLC+-Geraetedatei (XML) -> dict im Aufbau der OFL-Dateien (nur was convert braucht)."""
    if len(text) > MAX_BYTES or "<!ENTITY" in text:
        raise ValueError("Datei nicht lesbar")
    text = re.sub(r"<!DOCTYPE\s+FixtureDefinition\s*>", "", text, count=1)   # so beginnt jede QLC+-Datei
    if "<!DOCTYPE" in text:                                                    # andere DOCTYPEs (mit eigenen Regeln) nie
        raise ValueError("Datei nicht lesbar")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise ValueError("Die QLC+-Datei ist kein gueltiges XML") from None

    def tag(e):
        return e.tag.split("}")[-1]

    def kids(e, name):
        return [c for c in e if tag(c) == name]

    fx = {"name": "", "categories": [], "availableChannels": {}, "modes": [], "wheels": {}}
    maker = ""
    for c in root:
        if tag(c) == "Manufacturer":
            maker = (c.text or "").strip()
        elif tag(c) == "Model":
            fx["name"] = (c.text or "").strip()
        elif tag(c) == "Type":
            t = (c.text or "").strip()
            fx["categories"] = [{"Moving Head": "Moving Head", "Laser": "Laser", "Hazer": "Hazer", "Smoke": "Smoke",
                                 "Strobe": "Strobe", "Color Changer": "Color Changer"}.get(t, "Other")]
    fine_pending = []
    for ch in kids(root, "Channel"):
        name = ch.get("Name") or ""
        preset = ch.get("Preset") or ""
        d = {}
        if preset in QLC_FINE:
            fine_pending.append((name, QLC_FINE[preset]))
            d = {"capability": {"type": "Generic"}, "_preset": preset}
        elif preset in QLC_PRESET:
            t, col = QLC_PRESET[preset]
            d = {"capability": {"type": t, **({"color": col} if col else {})}, "_preset": preset}
        else:
            grp = next((g for g in kids(ch, "Group")), None)
            gname = (grp.text or "").strip() if grp is not None else ""
            colour = next(((c.text or "").strip() for c in kids(ch, "Colour")), "")
            if gname == "Intensity" and colour:
                d = {"capability": {"type": "ColorIntensity", "color": colour.title() if colour != "UV" else "UV"}}
            caps = []
            for cap in kids(ch, "Capability"):
                lo, hi = _num(cap.get("Min", 0)), _num(cap.get("Max", 255), 255)
                pr = cap.get("Preset") or ""
                txt = (cap.text or "").strip()
                if pr == "ShutterOpen" or (gname == "Shutter" and txt.lower() in ("open", "shutter open")):
                    caps.append({"dmxRange": [lo, hi], "type": "ShutterStrobe", "shutterEffect": "Open"})
                elif pr == "ShutterClose" or (gname == "Shutter" and txt.lower() in ("closed", "shutter closed", "blackout")):
                    caps.append({"dmxRange": [lo, hi], "type": "ShutterStrobe", "shutterEffect": "Closed"})
                elif txt.lower() in ("no function", "nothing", "none", "off", "no effect", "open") and gname not in ("Gobo", "Colour"):
                    caps.append({"dmxRange": [lo, hi], "type": "NoFunction"})
                else:
                    caps.append({"dmxRange": [lo, hi], "type": QLC_GROUP.get(gname, "Generic")})
            if not d:
                if caps and gname not in ("Intensity", "Pan", "Tilt"):
                    d = {"capabilities": caps}
                else:
                    d = {"capability": {"type": QLC_GROUP.get(gname, "Generic")}}
        fx["availableChannels"][name] = d
    for name, coarse_preset in fine_pending:                        # feine Kanaele dem groben zuordnen
        coarse = next((k for k, v in fx["availableChannels"].items() if v.get("_preset") == coarse_preset), None)
        if coarse:
            fx["availableChannels"][coarse].setdefault("fineChannelAliases", []).append(name)
            fx["availableChannels"].pop(name, None)
    for v in fx["availableChannels"].values():
        v.pop("_preset", None)
    for mode in kids(root, "Mode"):
        lst = sorted(((int(c.get("Number", 0)), (c.text or "").strip()) for c in kids(mode, "Channel")), key=lambda x: x[0])
        fx["modes"].append({"name": mode.get("Name") or "Modus", "channels": [n for _, n in lst]})
    if not fx["modes"]:
        raise ValueError("Die QLC+-Datei enthaelt keinen Modus")
    return fx, maker


def read_file(text):
    """Inhalt einer hochgeladenen Datei (OFL-JSON, Light-Butler-JSON oder QLC+-XML) -> (Geraet als dict, Hersteller)."""
    s = str(text or "").lstrip("﻿").strip()
    if len(s) > MAX_BYTES:
        raise ValueError("Die Datei ist zu gross")
    if s.startswith("<"):
        return qxf_to_ofl(s)
    try:
        d = json.loads(s)
    except ValueError:
        raise ValueError("Die Datei ist weder eine OFL-Datei (.json) noch eine QLC+-Datei (.qxf)") from None
    import fixture_export
    if fixture_export.is_lb(d):                                            # eigene Light-Butler-Datei
        return d, str(d.get("maker") or "")[:60]
    if not isinstance(d, dict) or not isinstance(d.get("modes"), list) or not isinstance(d.get("availableChannels"), dict):
        raise ValueError("Keine Geraetedatei der Open Fixture Library (es fehlen modes oder availableChannels)")
    mk = d.get("manufacturerKey") or ""
    return d, str(mk)[:60]


def type_name(maker, fx_name, mode_name, taken):
    base = _slug("ofl_" + (maker or "") + "_" + (fx_name or "") + "_" + (mode_name or ""), 28)
    if not base[0].isalpha():
        base = "ofl_" + base
    base = base[:28]
    name, i = base, 2
    while name in taken:
        name, i = "%s_%d" % (base[:26], i), i + 1
    return name
