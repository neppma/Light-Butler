#!/usr/bin/env python3
"""
timeline.py - Timeline-Engine: Showdatei pruefen (normalize), fuer die Wiedergabe uebersetzen (compile) und zu einem
beliebigen Zeitpunkt auswerten. Reine Rechnung, ohne Rig-Ausgabe und ohne Threads.

Aufbau einer Show (show.json):
  name, bpm, beat_offset, beats_per_bar, duration, audio, grid
  groups       [{id, name, fixtures: [...]}]
  scenes       [{id, name, values: {fixture: {attr: wert}}}]
  scene_clips  [{id, t, d, scene, fade_in, fade_out}]
  tracks       [{id, target: {fixture|group}, attr, mute, keys: [{id, t, v, e}], clips: [{id, t, d, pattern, p}]}]

Werte: dimmer und einfache Kanaele 0..255, color [r, g, b, w, uv], move [u, v] (0..1 im erlaubten Bereich).
Zwischen Keyframes wird interpoliert (linear, ease_in, ease_out, ease_in_out, constant). Vor dem ersten und nach dem
letzten Keyframe gilt dessen Wert. Ein laufender Clip liegt ueber den Keyframes der Spur, seine Fades blenden dazwischen.

Zusammenfuehren je Geraet: zuerst Szenen, dann die Spuren von oben nach unten. Dimmer: der hellste Wert gewinnt (HTP),
alles andere: die unterste Spur gewinnt (LTP).
"""
import bisect
import re

from . import fixtures as fm
from . import patterns as pt

EASES = ("linear", "ease_in", "ease_out", "ease_in_out", "constant")
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")
MAX_TRACKS = 600
MAX_EVENTS = 50000            # je Spur
MAX_DURATION = 6 * 3600.0
MARK_SECTIONS = ("intro", "vers", "main", "break", "outro")   # wie mixxx_link.SECTIONS
MAX_MARK_SECTIONS = 32
MAX_MARK_CUES = 16
MAX_LYRIC_LINES = 600
MAX_LYRIC_TEXT = 20000
MASTER = "master"             # Spur der Master-Zeile: Helligkeit aller Geraete
MARK_EVENTS = ("drop", "build", "gap", "break")
MAX_MARK_EVENTS = 64
MAX_MARK_ENERGY = 400
MIN_CLIP = 0.025


def ease(kind, u):
    if kind == "linear":
        return u
    if kind == "constant":
        return 0.0
    if kind == "ease_in":
        return u * u
    if kind == "ease_out":
        return 1.0 - (1.0 - u) * (1.0 - u)
    return u * u * (3.0 - 2.0 * u)            # ease_in_out


def kind_of(attr):
    return {fm.A_COLOR: "color", fm.A_MOVE: "move", fm.A_LASER: "laser", fm.A_FOG: "fog", fm.A_NANO_FX: "nano_fx", fm.A_PANEL: "panel"}.get(attr, "scalar")


def clean_value(kind, v):
    try:
        if kind == "color":
            return list(pt.parse_color(v))
        if kind == "move":
            return [max(0.0, min(1.0, float(v[0]))), max(0.0, min(1.0, float(v[1])))]
        return max(0.0, min(255.0, float(v)))
    except (TypeError, IndexError):
        raise ValueError(f"Wert {v!r} passt nicht zur Spur ({kind})") from None


def _num(d, k, default, lo, hi):
    try:
        x = float(d.get(k, default))
    except (TypeError, ValueError):
        raise ValueError(f"{k}: keine Zahl") from None
    if x != x:
        raise ValueError(f"{k}: keine Zahl")
    return max(lo, min(hi, x))


def _id(v, prefix, seen):
    s = str(v or "")
    if not ID_RE.match(s) or s in seen:
        s = f"{prefix}{len(seen) + 1}"
        while s in seen:
            s += "x"
    seen.add(s)
    return s


def clean_lyrics(y):
    """Liedtext: Zeilen mit Zeiten und reiner Text. Nur Anzeige und Hilfe fuer den Assistenten, aufs Licht wirkt er nie."""
    lines = []
    for x in (y.get("lines") or [])[:MAX_LYRIC_LINES] if isinstance(y.get("lines"), list) else []:
        if isinstance(x, list) and len(x) == 2 and isinstance(x[0], (int, float)) and 0 <= x[0] <= MAX_DURATION:
            lines.append([round(float(x[0]), 2), str(x[1])[:200]])
    return {"lines": sorted(lines, key=lambda x: x[0]), "plain": str(y.get("plain") or "")[:MAX_LYRIC_TEXT], "source": str(y.get("source") or "")[:20],
            "title": str(y.get("title") or "")[:160], "duration": _num(y, "duration", 0.0, 0.0, MAX_DURATION)}


def clean_marks(m):
    """Abschnitte, Hotcues und Analyse des Liedes, fuer die Timeline und den Show-Assistenten: aufs Licht wirken sie nie."""
    se, cu = [], []
    for s in (m.get("se") or [])[:MAX_MARK_SECTIONS] if isinstance(m.get("se"), list) else []:
        if (isinstance(s, list) and len(s) == 3 and s[0] in MARK_SECTIONS and all(isinstance(v, (int, float)) for v in s[1:])
                and 0 <= s[1] < s[2] <= MAX_DURATION):
            se.append([s[0], round(float(s[1]), 3), round(float(s[2]), 3)])
    for c in (m.get("cu") or [])[:MAX_MARK_CUES] if isinstance(m.get("cu"), list) else []:
        if isinstance(c, (int, float)) and 0 <= c <= MAX_DURATION:
            cu.append(round(float(c), 3))
    ev = [[e[0], round(float(e[1]), 3), round(float(e[2]), 3)] for e in (m.get("ev") or [])[:MAX_MARK_EVENTS] if isinstance(m.get("ev"), list)
          and isinstance(e, list) and len(e) >= 3 and e[0] in MARK_EVENTS and all(isinstance(v, (int, float)) for v in e[1:3])] if isinstance(m.get("ev"), list) else []
    en = [max(0, min(100, int(v))) for v in m.get("en")[:MAX_MARK_ENERGY] if isinstance(v, (int, float))] if isinstance(m.get("en"), list) else []
    lvl = m.get("lvl")
    return {"se": se, "cu": sorted(cu), "ev": ev, "en": en, "lvl": int(lvl) if isinstance(lvl, (int, float)) and 1 <= lvl <= 9 else None,
            "genre": str(m.get("genre") or "")[:40], "title": str(m.get("title") or "")[:120], "fp": str(m.get("fp") or "")[:40]}


def new_show(name):
    return {"version": 1, "name": name, "bpm": 120.0, "beat_offset": 0.0, "beats_per_bar": 4, "duration": 180.0, "audio": "",
            "grid": "beat", "groups": [], "scenes": [], "scene_clips": [], "tracks": []}


def normalize(doc):
    """Showdatei pruefen und auf die bekannten Felder bringen. Wirft ValueError, wenn etwas nicht passt."""
    if not isinstance(doc, dict):
        raise ValueError("Show: kein Objekt")
    out = new_show(str(doc.get("name", ""))[:60])
    out["bpm"] = _num(doc, "bpm", 120.0, 20.0, 400.0)
    out["beat_offset"] = _num(doc, "beat_offset", 0.0, 0.0, 600.0)
    out["beats_per_bar"] = int(_num(doc, "beats_per_bar", 4, 1, 16))
    out["duration"] = _num(doc, "duration", 180.0, 1.0, MAX_DURATION)
    out["audio"] = str(doc.get("audio") or "")[:80]
    out["grid"] = str(doc.get("grid") or "beat")[:12]
    m = doc.get("mixxx")
    if isinstance(m, dict):                   # Zuordnung zu einem Lied aus Mixxx (Titel und Laenge, die MP3 selbst zaehlt immer)
        out["mixxx"] = {"on": m.get("on", True) is not False, "title": str(m.get("title") or "")[:120],
                        "dur": _num(m, "dur", 0.0, 0.0, MAX_DURATION)}
    if isinstance(doc.get("marks"), dict):
        out["marks"] = clean_marks(doc["marks"])
    if isinstance(doc.get("lyrics"), dict):
        out["lyrics"] = clean_lyrics(doc["lyrics"])
    if isinstance(doc.get("ui"), dict):
        out["ui"] = doc["ui"]
    seen = set()
    for g in doc.get("groups") or []:
        out["groups"].append({"id": _id(g.get("id"), "g", seen), "name": str(g.get("name", "Gruppe"))[:40],
                              "fixtures": [str(x) for x in (g.get("fixtures") or [])][:128]})
    for s in doc.get("scenes") or []:
        vals = {}
        for fx, attrs in (s.get("values") or {}).items():
            if isinstance(attrs, dict):
                vals[str(fx)] = {str(a): clean_value(kind_of(a), v) for a, v in attrs.items() if kind_of(a) not in ("laser", "fog", "nano_fx", "panel")}
        out["scenes"].append({"id": _id(s.get("id"), "s", seen), "name": str(s.get("name", "Szene"))[:40], "values": vals})
    for c in doc.get("scene_clips") or []:
        out["scene_clips"].append({"id": _id(c.get("id"), "sc", seen), "t": _num(c, "t", 0, 0, MAX_DURATION),
                                   "d": _num(c, "d", 4, MIN_CLIP, MAX_DURATION), "scene": str(c.get("scene", "")),
                                   "fade_in": _num(c, "fade_in", 0, 0, 600), "fade_out": _num(c, "fade_out", 0, 0, 600)})
    tracks = doc.get("tracks") or []
    if len(tracks) > MAX_TRACKS:
        raise ValueError(f"Zu viele Spuren (hoechstens {MAX_TRACKS})")
    for tr in tracks:
        tg = tr.get("target") or {}
        if tg.get("master"):                  # Master-Zeile: nur Keyframes, ohne Keyframes gar keine Spur (alte Shows bleiben gleich)
            mk = [{"id": _id(k.get("id"), "k", seen), "t": _num(k, "t", 0, 0, MAX_DURATION), "v": clean_value("scalar", k.get("v", 255)),
                   "e": k.get("e") if k.get("e") in EASES else "linear"} for k in (tr.get("keys") or [])[:MAX_EVENTS]]
            if mk and not any("master" in x["target"] for x in out["tracks"]):
                out["tracks"].append({"id": _id(tr.get("id"), "t", seen), "target": {"master": True}, "attr": MASTER, "mute": False,
                                      "keys": sorted(mk, key=lambda x: x["t"]), "clips": []})
            continue
        if tg.get("panel"):                   # Zeile Panel-Szenen: nur Clips, ohne Clips gar keine Spur
            pc = [{"id": _id(c.get("id"), "c", seen), "t": _num(c, "t", 0, 0, MAX_DURATION), "d": _num(c, "d", 4, MIN_CLIP, MAX_DURATION), "pattern": "panel_scene",
                   "label": str(c.get("label", ""))[:40], "p": pt.clean_params("panel_scene", c.get("p"))} for c in (tr.get("clips") or [])[:MAX_EVENTS] if c.get("pattern") == "panel_scene"]
            if pc and not any("panel" in x["target"] for x in out["tracks"]):
                out["tracks"].append({"id": _id(tr.get("id"), "t", seen), "target": {"panel": True}, "attr": fm.A_PANEL, "mute": False, "keys": [],
                                      "clips": sorted(pc, key=lambda x: x["t"])})
            continue
        target = {"group": str(tg["group"])} if tg.get("group") else {"fixture": str(tg.get("fixture", ""))}
        attr = str(tr.get("attr", ""))
        kind = kind_of(attr)
        keys, clips = [], []
        if len(tr.get("keys") or []) + len(tr.get("clips") or []) > MAX_EVENTS:
            raise ValueError(f"Zu viele Ereignisse auf einer Spur (hoechstens {MAX_EVENTS})")
        for k in (tr.get("keys") or []) if kind not in ("laser", "fog", "nano_fx", "panel") else []:   # Laser und Nebel nur als Clips
            e = k.get("e", "linear")
            keys.append({"id": _id(k.get("id"), "k", seen), "t": _num(k, "t", 0, 0, MAX_DURATION),
                         "v": clean_value(kind, k.get("v", 0)), "e": e if e in EASES else "linear"})
        keys.sort(key=lambda x: x["t"])
        for c in tr.get("clips") or []:
            key = str(c.get("pattern", ""))
            if key not in pt.REGISTRY:
                raise ValueError(f"Unbekanntes Muster: {key}")
            clips.append({"id": _id(c.get("id"), "c", seen), "t": _num(c, "t", 0, 0, MAX_DURATION),
                          "d": _num(c, "d", 4, MIN_CLIP, 10.0 if kind == "fog" else MAX_DURATION), "pattern": key, "label": str(c.get("label", ""))[:40],
                          "p": pt.clean_params(key, c.get("p"))})
        clips.sort(key=lambda x: x["t"])
        out["tracks"].append({"id": _id(tr.get("id"), "t", seen), "target": target, "attr": attr, "mute": bool(tr.get("mute")),
                              "keys": keys, "clips": clips})
    return out


def mix(kind, a, b, w):
    if kind == "scalar":
        return a + (b - a) * w
    return tuple(x + (y - x) * w for x, y in zip(a, b))


class CClip:
    __slots__ = ("t", "d", "end", "key", "p", "fi", "fo", "seed", "out")


class CTrack:
    """Eine uebersetzte Spur: sortierte Keyframes und Clips, schnelle Suche auch bei sehr vielen Ereignissen."""

    def __init__(self, tr, fixtures, jump=False):
        self.attr, self.kind = tr["attr"], kind_of(tr["attr"])
        self.fixtures = fixtures              # [(Fixture, Index, Anzahl, Standardwert)]
        keys = tr["keys"]
        self.kt = [k["t"] for k in keys]
        self.kv = [tuple(k["v"]) if self.kind != "scalar" else k["v"] for k in keys]
        self.ke = ["constant" if jump else k["e"] for k in keys]   # feste Stufen (Preset, Gobo) springen immer
        self.clips, self.ct, self.cmax = [], [], []
        m = 0.0
        for c in tr["clips"]:
            d = pt.REGISTRY[c["pattern"]]
            if d["out"] != self.kind:
                continue                      # Muster passt nicht zur Spur (zum Beispiel Kreis auf Farbe)
            cc = CClip()
            cc.t, cc.d, cc.end, cc.key = c["t"], c["d"], c["t"] + c["d"], c["pattern"]
            cc.p = pt.full_params(c["pattern"], c["p"])
            cc.fi, cc.fo, cc.seed, cc.out = cc.p["fade_in"], cc.p["fade_out"], pt.clip_seed(c["id"]), d["out"]
            m = max(m, cc.end)
            self.clips.append(cc)
            self.ct.append(cc.t)
            self.cmax.append(m)               # groesstes Ende bis hierher: begrenzt die Suche nach hinten

    def key_value(self, t):
        kt = self.kt
        if not kt:
            return None
        i = bisect.bisect_right(kt, t)
        if i == 0:
            return self.kv[0]
        if i >= len(kt):
            return self.kv[-1]
        t0, t1 = kt[i - 1], kt[i]
        e = self.ke[i - 1]
        if e == "constant" or t1 <= t0:
            return self.kv[i - 1]
        return mix(self.kind, self.kv[i - 1], self.kv[i], ease(e, (t - t0) / (t1 - t0)))

    def active(self, t):
        """Laufende Clips, aeltester zuerst."""
        out = []
        i = bisect.bisect_right(self.ct, t) - 1
        while i >= 0 and self.cmax[i] > t:
            c = self.clips[i]
            if c.end > t:
                out.append(c)
            i -= 1
        out.reverse()
        return out


def _default(kind, fallback):
    if kind == "color":
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    if kind == "move":
        return (0.5, 0.5)
    return float(fallback)


class Compiled:
    """Eine Show, fertig fuer die Wiedergabe. Unveraenderlich: Die Engine tauscht sie als Ganzes aus."""

    def __init__(self, doc, rig):
        self.name, self.duration = doc.get("name", ""), doc["duration"]
        self.bpm, self.beat_offset = doc["bpm"], doc["beat_offset"]
        self.warnings = []
        self.tracks = []
        self.uses_strobe = self.uses_laser = False
        self.fog_cues = []            # Nebelschuebe: (Zeit, Dauer), sortiert
        self.panel_cues = []          # Szenen aus dem Hauptpanel: (Zeit, Ende, Name)
        self.nano_cues = []           # Effekte des Nanoleaf: (Zeit, Ende, Name), sortiert
        groups = {g["id"]: g for g in doc.get("groups", [])}
        for g in fm.default_groups(rig):
            groups.setdefault(g["id"], g)
        self.master = None
        self.lyric_lines = (doc.get("lyrics") or {}).get("lines") or []
        for tr in doc["tracks"]:
            tg = tr["target"]
            if "master" in tg:
                self.master = CTrack(tr, [])
                continue
            if "panel" in tg:
                self.panel_cues.extend((x["t"], x["t"] + x["d"], x["p"].get("panel_scene", "")) for x in tr["clips"] if x["p"].get("panel_scene"))
                continue
            if tr.get("mute"):
                continue
            if "group" in tg:
                g = groups.get(tg["group"])
                if g is None:
                    self.warnings.append(f"Gruppe {tg['group']} fehlt")
                    continue
                names = g["fixtures"]
            else:
                names = [tg.get("fixture", "")]
            fxs = []
            for name in names:
                fx = rig.by_name.get(name)
                if fx is None:
                    self.warnings.append(f"Geraet {name} fehlt")
                    continue
                allowed = {a["attr"] for a in fm.attrs_for(fx)}
                if tr["attr"] not in allowed:         # Hazer, Laser, Mode-/Reset-Kanaele: nie aus einer Showdatei
                    if len(names) == 1:
                        self.warnings.append(f"{name}: Spur {tr['attr']} nicht erlaubt")
                    continue
                fxs.append(fx)
            if not fxs:
                continue
            kind = kind_of(tr["attr"])
            if kind == "nano_fx":         # laeuft auf dem Geraet, die Show waehlt ihn nur aus (Show._nano_effect_tick)
                self.nano_cues.extend((c["t"], c["t"] + c["d"], c["p"].get("nano_effect", "")) for c in tr["clips"] if c["pattern"] == "nano_effect" and c["p"].get("nano_effect"))
                continue
            if kind == "fog":             # kein Wert im Bild: Schuebe loest der Showmanager ueber den SMOKE-Weg aus
                self.fog_cues.extend((c["t"], c["d"]) for c in tr["clips"] if c["pattern"] == "fog_burst")
                continue
            # Fades blenden gegen den Grundwert: beim Dimmer immer dunkel, nicht der Standardwert des Kanals (oft 255)
            lst = [(fx, i, len(fxs), _default(kind, 0 if tr["attr"] == fm.A_DIMMER else fx.defaults.get(tr["attr"], 0))) for i, fx in enumerate(fxs)]
            ct = CTrack(tr, lst, jump=any(fm.stepped(fx, tr["attr"]) for fx in fxs))
            for cl in ct.clips:
                cl.p["bar_len"] = doc.get("beats_per_bar", 4)     # Verlauf "je Takt" (Laser-Clip)
            self.tracks.append(ct)
            if kind == "laser" and ct.clips:
                self.uses_laser = True
            if any(c.key == "strobe" for c in ct.clips) or tr["attr"] in ("strobe", "strobe_a", "strobe_b", "flash"):
                self.uses_strobe = True
        self.fog_cues.sort()
        self.scenes = []
        by_id = {s["id"]: s for s in doc.get("scenes", [])}
        for c in sorted(doc.get("scene_clips", []), key=lambda x: x["t"]):
            s = by_id.get(c["scene"])
            if s is None:
                self.warnings.append("Szene fehlt")
                continue
            vals = {}
            for fname, attrs in s["values"].items():
                fx = rig.by_name.get(fname)
                if fx is None:
                    continue
                allowed = {a["attr"] for a in fm.attrs_for(fx)}
                ok = {a: (tuple(v) if kind_of(a) != "scalar" else v) for a, v in attrs.items() if a in allowed and kind_of(a) not in ("laser", "fog")}
                if ok:
                    vals[fname] = ok
            self.scenes.append((c["t"], c["t"] + c["d"], c["fade_in"], c["fade_out"], vals))
        self._ctx = pt.Ctx()

    def beat_at(self, t):
        return (t - self.beat_offset) * self.bpm / 60.0

    def panel_scene_at(self, t):
        """Name der Panel-Szene zu dieser Zeit, sonst None."""
        for a, b, name in self.panel_cues:
            if a <= t < b:
                return name
        return None

    def nano_effect_at(self, t):
        """Name des Nanoleaf-Effekts zu dieser Zeit, sonst None."""
        for a, b, name in self.nano_cues:
            if a <= t < b:
                return name
        return None

    def master_at(self, t):
        """Helligkeit aller Geraete 0..1 aus der Master-Zeile, ohne Keyframes 1."""
        v = self.master.key_value(t) if self.master is not None else None
        return 1.0 if v is None else v / 255.0

    def evaluate(self, t, frame=0, strobe=False, only=None):
        """Alle Werte zum Zeitpunkt t: {Fixture-Name: {attr: wert}}. only = nur dieses Geraet (Anzeige im Panel)."""
        state = {}
        for t0, t1, fi, fo, vals in self.scenes:
            if not t0 <= t < t1:
                continue
            w = 1.0
            if fi > 0:
                w = min(w, (t - t0) / fi)
            if fo > 0:
                w = min(w, (t1 - t) / fo)
            for fname, attrs in vals.items():
                if only is not None and fname != only:
                    continue
                st = state.setdefault(fname, {})
                for a, v in attrs.items():
                    k = kind_of(a)
                    if w >= 1.0:
                        st[a] = v
                    else:
                        st[a] = mix(k, st.get(a, _default(k, 0)), v, w)
        beat = self.beat_at(t)
        c = pt.Ctx(beat=beat, frame=frame, strobe=strobe)
        for tr in self.tracks:
            base_key = tr.key_value(t)
            act = tr.active(t) if tr.clips else ()
            if base_key is None and not act:
                continue
            kind, attr = tr.kind, tr.attr
            for fx, i, n, dflt in tr.fixtures:
                if only is not None and fx.name != only:
                    continue
                v = base_key
                for cl in act:
                    c.u, c.sec, c.i, c.n, c.seed = (t - cl.t) / cl.d, t - cl.t, i, n, cl.seed
                    pv = pt.evaluate(cl.key, cl.p, c)
                    w = 1.0
                    if cl.fi > 0:
                        w = min(w, (t - cl.t) / cl.fi)
                    if cl.fo > 0:
                        w = min(w, (cl.end - t) / cl.fo)
                    v = pv if w >= 1.0 else mix(kind, dflt if v is None else v, pv, w)
                if v is None:
                    continue
                st = state.get(fx.name)
                if st is None:
                    st = state[fx.name] = {}
                if attr == fm.A_DIMMER and attr in st:
                    if v > st[attr]:
                        st[attr] = v
                else:
                    st[attr] = v
        return state


def compile_show(doc, rig):
    return Compiled(normalize(doc), rig)
