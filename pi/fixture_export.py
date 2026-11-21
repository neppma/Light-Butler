#!/usr/bin/env python3
"""
fixture_export.py - Geraetetyp eines Fixtures als Datei ausgeben (Knopf "Export" je Fixture auf /fixtures).

Vier Formate:
  lb    Light-Butler-Datei (JSON): der ganze Typ mit Beschreibungen, Standardwerten, Grenzen und Sperren.
        Laesst sich ueber "Oder Datei importieren" wieder einlesen (lb_to_type). Beim Einlesen gelten dieselben
        Regeln wie bei der Open Fixture Library: keine Laser-Freigabe, kein Einzel-Strobe, keine Ruhewerte,
        kein Handbetrieb; Laser-Kanaele werden gesperrte Kanaele (Sicherheitsregeln 2, 4, 5).
  ofl   Open Fixture Library (JSON, Aufbau der Datenbank), zum Einreichen oder Umwandeln auf open-fixture-library.org.
  qxf   QLC+-Geraetedatei (XML).
  yaml  Ausschnitt im Aufbau der fixtures.yaml (Typ und Fixture).
Bei OFL und QLC+ werden die Kanaele nur grob beschrieben; Sperren und Grenzen stehen dort nur als Kommentar.
Nur lesend: es wird nichts gespeichert und nichts gesendet.
"""
import copy
import json
import re
import time
from xml.sax.saxutils import escape, quoteattr

import yaml

FORMATS = {"lb": ("lightbutler.json", "application/json"), "ofl": ("ofl.json", "application/json"),
           "qxf": ("qxf", "application/xml"), "yaml": ("yaml", "text/yaml")}
LB_KIND = "geraetetyp"
COLORS = {"r": "Red", "g": "Green", "b": "Blue", "w": "White", "uv": "UV", "a": "Amber"}
ROLE_EN = {"dimmer": "Dimmer", "pan": "Pan", "tilt": "Tilt", "pan_fine": "Pan fine", "tilt_fine": "Tilt fine",
           "shutter": "Shutter", "strobe": "Strobe", "colorwheel": "Color wheel", "gobo": "Gobo", "gobo_rot": "Gobo rotation",
           "prism": "Prism", "zoom": "Zoom", "focus": "Focus", "pt_speed": "Pan/Tilt speed"}
QLC_PRESET = {"dimmer": "IntensityMasterDimmer", "pan": "PositionPan", "pan_fine": "PositionPanFine", "tilt": "PositionTilt",
              "tilt_fine": "PositionTiltFine", "zoom": "BeamZoomSmallBig", "focus": "BeamFocusNearFar",
              "pt_speed": "SpeedPanTiltFastSlow"}
QLC_COLOR = {"r": "IntensityRed", "g": "IntensityGreen", "b": "IntensityBlue", "w": "IntensityWhite", "uv": "IntensityUV",
             "a": "IntensityAmber"}
QLC_GROUP = {"shutter": "Shutter", "strobe": "Shutter", "colorwheel": "Colour", "gobo": "Gobo", "gobo_rot": "Gobo",
             "prism": "Prism"}
SAFE_KEYS = ("channels", "map", "desc", "defaults", "safe_limits", "label", "maker", "presets", "locked", "locked_channels")
FOG_RE = re.compile(r"(^|_)(fog|haze|hazer|smoke|nebel)")


def _cell(p):
    """r3 -> ("r", 3), dimmer2 -> ("dimmer", 2), sonst (p, 0)."""
    m = re.match(r"^(r|g|b|w|uv|a|dimmer)(\d+)$", p)
    return (m.group(1), int(m.group(2))) if m else (p, 0)


def _params(t):
    return [p for p, _ in sorted(t["map"].items(), key=lambda x: x[1])]


def _locked(t):
    return set(t["map"]) if t.get("locked") else set(t.get("locked_channels") or []) | set(t.get("laser_channels") or [])


def _is_laser(t):
    return bool(t.get("laser_channels")) or any("laser" in p for p in t["map"])


def _is_fog(t):
    return any(FOG_RE.search(p) for p in t["map"]) or "burst" in t


def find(c, fx_name):
    """Fixture und Typ aus den zusammengefuehrten Daten (fixture_edit.apply_user)."""
    e = next((x for x in c["fixtures"] if x["name"] == fx_name), None)
    if e is None:
        raise ValueError("Fixture nicht gefunden")
    t = c["types"].get(e["type"])
    if not t or not t.get("map"):
        raise ValueError("Typ nicht gefunden")
    return e, e["type"], t


def file_name(e, tname, fmt):
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", str(e.get("label") or tname)).strip("_")[:40] or tname
    return "%s.%s" % (base, FORMATS[fmt][0])


def model_name(e, tname, t):
    return str(t.get("label") or e.get("label") or tname)[:80]


def _channel_name(p, t):
    """Lesbarer, englischer Kanalname fuer OFL und QLC+ (wie die Datenbank), Zellen mit Nummer."""
    base, n = _cell(p)
    if base in COLORS:
        name = COLORS[base]
    elif base in ROLE_EN:
        name = ROLE_EN[base]
    else:
        name = (t.get("desc") or {}).get(p) or p
        name = re.sub(r"\s+", " ", str(name)).strip()[:40].strip() or p
    return "%s %d" % (name, n) if n else name


def _names(t):
    out, seen = {}, set()
    for p in _params(t):
        n, i = _channel_name(p, t), 2
        cand = n
        while cand.lower() in seen:
            cand, i = "%s (%d)" % (n, i), i + 1
        seen.add(cand.lower())
        out[p] = cand
    return out


def _comment(p, t):
    bits = []
    d = (t.get("desc") or {}).get(p)
    if d:
        bits.append(str(d)[:200])
    if p in _locked(t):
        bits.append("Light-Butler: gesperrt (sendet immer 0)")
    lim = (t.get("safe_limits") or {}).get(p)
    if lim:
        bits.append("Light-Butler: nur %d-%d" % (lim[0], lim[1]))
    return " · ".join(bits)


# ---- Light-Butler-Datei -------------------------------------------------------------------------------------
def to_lb(c, fx_name):
    e, tname, t = find(c, fx_name)
    tt = copy.deepcopy(t)
    tt.pop("custom", None)
    tt.pop("ofl", None)
    fx = {k: e[k] for k in ("label", "group", "address", "nr") if k in e}
    return {"lightbutler": LB_KIND, "version": 1, "name": tname, "maker": str(t.get("maker") or "")[:60],
            "model": model_name(e, tname, t), "exported": time.strftime("%Y-%m-%d"), "type": tt, "fixture": fx,
            "modes": [{"name": "Light-Butler-Typ %s" % tname, "channels": _params(t)}]}


def is_lb(d):
    return isinstance(d, dict) and d.get("lightbutler") == LB_KIND and isinstance(d.get("type"), dict)


def lb_to_type(d):
    """Light-Butler-Datei -> (Typ fuer fixtures_user.json, Hinweise). Uebernimmt nur die sicheren Felder."""
    src = d["type"]
    if not isinstance(src.get("map"), dict) or not src["map"]:
        raise ValueError("Die Light-Butler-Datei enthaelt keine Kanalliste")
    t = {k: copy.deepcopy(src[k]) for k in SAFE_KEYS if k in src}
    if not t.get("label") and d.get("model"):
        t["label"] = str(d["model"])[:60]
    if not t.get("maker") and d.get("maker"):
        t["maker"] = str(d["maker"])[:60]
    for k in ("label", "maker"):
        if k in t:
            t[k] = str(t[k])[:60]
    if isinstance(t.get("desc"), dict):
        t["desc"] = {str(p): str(v)[:300] for p, v in t["desc"].items() if p in t["map"]}
    notes = []
    lc = set(t.get("locked_channels") or []) | {p for p in src.get("laser_channels") or [] if p in t["map"]}
    if lc:
        t["locked_channels"] = sorted(p for p in lc if p in t["map"])
    if _is_fog(src) or src.get("locked"):
        t["locked"] = True
        notes.append("Nebelgeraet oder gesperrter Typ: wird nie angesteuert (bleibt gesperrt).")
    if src.get("laser_channels"):
        notes.append("Laser-Kanaele sind gesperrt und senden immer 0. Eine Laser-Freigabe wird nicht uebernommen.")
    dropped = sorted(set(src) - set(SAFE_KEYS) - {"custom", "ofl", "laser_channels"})
    if dropped:
        notes.append("Nicht uebernommen (nur in fixtures.yaml moeglich): " + ", ".join(dropped) + ".")
    if "locked" in t and t["locked"] is not True:
        t.pop("locked")
    return t, notes


# ---- Open Fixture Library ------------------------------------------------------------------------------------
def _ofl_cap(p, t):
    base, _ = _cell(p)
    if p in _locked(t):
        return {"type": "Generic"}
    if base == "dimmer":
        return {"type": "Intensity"}
    if base in COLORS:
        return {"type": "ColorIntensity", "color": COLORS[base]}
    if p == "pan":
        return {"type": "Pan", "angleStart": "0%", "angleEnd": "100%"}
    if p == "tilt":
        return {"type": "Tilt", "angleStart": "0%", "angleEnd": "100%"}
    if p == "zoom":
        return {"type": "Zoom", "angleStart": "narrow", "angleEnd": "wide"}
    if p == "focus":
        return {"type": "Focus", "distanceStart": "near", "distanceEnd": "far"}
    if p == "prism":
        return {"type": "Prism"}
    if p == "pt_speed":
        return {"type": "PanTiltSpeed", "speedStart": "fast", "speedEnd": "slow"}
    return {"type": "Generic"}


def to_ofl(c, fx_name):
    e, tname, t = find(c, fx_name)
    names = _names(t)
    ps = _params(t)
    fine = {"pan_fine": "pan", "tilt_fine": "tilt"}
    avail = {}
    for p in ps:
        if p in fine and fine[p] in t["map"]:
            continue
        cap = _ofl_cap(p, t)
        com = _comment(p, t)
        if com:
            cap["comment"] = com
        ch = {"capability": cap}
        dv = (t.get("defaults") or {}).get(p)
        if dv and p not in _locked(t):
            ch["defaultValue"] = int(dv)
        for fp, cp in fine.items():
            if cp == p and fp in t["map"]:
                ch["fineChannelAliases"] = [names[fp]]
        avail[names[p]] = ch
    cats = []
    if _is_laser(t):
        cats.append("Laser")
    if _is_fog(t):
        cats.append("Hazer")
    if "pan" in t["map"] and "tilt" in t["map"]:
        cats.append("Moving Head")
    if any(_cell(p)[0] in ("r", "g", "b") for p in t["map"]):
        cats.append("Color Changer")
    if not cats:
        cats.append("Dimmer" if all(_cell(p)[0] == "dimmer" for p in t["map"]) else "Other")
    today = time.strftime("%Y-%m-%d")
    out = {"$schema": "https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library/master/schemas/fixture.json",
           "name": model_name(e, tname, t), "categories": cats,
           "meta": {"authors": ["Light-Butler"], "createDate": today, "lastModifyDate": today},
           "comment": "Export aus Light-Butler (Typ %s). Sperren und Grenzen stehen nur in den Kommentaren." % tname,
           "availableChannels": avail,
           "modes": [{"name": "%d-channel" % t["channels"], "shortName": "%dch" % t["channels"],
                      "channels": [names[p] for p in ps]}]}
    if t.get("maker"):
        out["manufacturerKey"] = re.sub(r"[^a-z0-9]+", "-", str(t["maker"]).lower()).strip("-")[:60]
    return out


# ---- QLC+ ----------------------------------------------------------------------------------------------------
def to_qxf(c, fx_name):
    e, tname, t = find(c, fx_name)
    names = _names(t)
    ps = _params(t)
    if _is_laser(t):
        kind = "Laser"
    elif _is_fog(t):
        kind = "Hazer"
    elif "pan" in t["map"] and "tilt" in t["map"]:
        kind = "Moving Head"
    elif any(_cell(p)[0] in ("r", "g", "b") for p in t["map"]):
        kind = "Color Changer"
    elif all(_cell(p)[0] == "dimmer" for p in t["map"]):
        kind = "Dimmer"
    else:
        kind = "Other"
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE FixtureDefinition>",
             '<FixtureDefinition xmlns="http://www.qlcplus.org/FixtureDefinition">',
             " <Creator>", "  <Name>Light-Butler</Name>", "  <Version>1</Version>", "  <Author>Light-Butler</Author>", " </Creator>",
             " <Manufacturer>%s</Manufacturer>" % escape(str(t.get("maker") or "Generic")),
             " <Model>%s</Model>" % escape(model_name(e, tname, t)), " <Type>%s</Type>" % kind]
    for p in ps:
        base, _ = _cell(p)
        n = names[p]
        dv = 0 if p in _locked(t) else int((t.get("defaults") or {}).get(p, 0) or 0)
        da = ' Default="%d"' % dv if dv else ""
        com = _comment(p, t)
        preset = None if p in _locked(t) else (QLC_COLOR.get(base) or (QLC_PRESET.get(p) if base != "dimmer" or p == "dimmer"
                                                                         else "IntensityDimmer"))
        if preset:
            lines.append(" <Channel Name=%s%s Preset=%s/>" % (quoteattr(n), da, quoteattr(preset)))
            continue
        grp = "Maintenance" if p in _locked(t) else QLC_GROUP.get(p, "Effect")
        lines.append(" <Channel Name=%s%s>" % (quoteattr(n), da))
        lines.append('  <Group Byte="0">%s</Group>' % grp)
        lines.append('  <Capability Min="0" Max="255">%s</Capability>' % escape(com or n))
        lines.append(" </Channel>")
    lines.append(' <Mode Name=%s>' % quoteattr("%d Channel" % t["channels"]))
    for i, p in enumerate(ps):
        lines.append('  <Channel Number="%d">%s</Channel>' % (i, escape(names[p])))
    lines += [" </Mode>", "</FixtureDefinition>", ""]
    return "\n".join(lines)


# ---- YAML ----------------------------------------------------------------------------------------------------
def to_yaml(c, fx_name):
    e, tname, t = find(c, fx_name)
    tt = copy.deepcopy(t)
    tt.pop("custom", None)
    ee = {k: v for k, v in e.items() if k != "user_added"}
    head = ("# %s - Export aus Light-Butler, %s\n# Typ und Fixture im Aufbau der fixtures.yaml (Abschnitte types und fixtures).\n\n"
            % (e.get("label") or tname, time.strftime("%Y-%m-%d %H:%M")))
    return head + yaml.safe_dump({"types": {tname: tt}, "fixtures": [ee]}, allow_unicode=True, sort_keys=False,
                                 default_flow_style=None, width=140)


def export(c, fx_name, fmt):
    """-> (Dateiname, Inhalt als Bytes, Inhaltstyp)."""
    if fmt not in FORMATS:
        raise ValueError("Unbekanntes Format")
    e, tname, _ = find(c, fx_name)
    if fmt == "lb":
        body = json.dumps(to_lb(c, fx_name), ensure_ascii=False, indent=1)
    elif fmt == "ofl":
        body = json.dumps(to_ofl(c, fx_name), ensure_ascii=False, indent=2)
    elif fmt == "qxf":
        body = to_qxf(c, fx_name)
    else:
        body = to_yaml(c, fx_name)
    return file_name(e, tname, fmt), body.encode("utf-8"), FORMATS[fmt][1] + "; charset=utf-8"
