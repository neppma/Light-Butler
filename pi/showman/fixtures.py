#!/usr/bin/env python3
"""
fixtures.py - Fixture-Manager des Showmanagers: was der Rig fuer die Timeline anbietet.

Geraete anlegen und bearbeiten geht weiter ueber die vorhandene Seite /fixtures (fixture_edit.py, fixtures_user.json).
Hier kommt dazu: Spuren je Geraet, vorgegebene Gruppen und Geraeteprofile als JSON (Export und Import).

SICHERHEIT: Hazer-, Laser- und Mode-/Reset-Kanaele (safe_limits) werden nie als einzelne Spur angeboten. timeline.compile
verwirft sie auch, wenn eine Showdatei sie von Hand enthaelt, und Fixture.write sperrt sie in jedem Bild ohnehin. Laser und
Nebel gibt es nur als eigene Spuren "laser" und "fog" (vom Nutzer am 03.11.2026 freigegeben), Sperren in engine.py und Show._fog_cue.
"""
import fixture_edit as fe

# Virtuelle Spuren: gelten fuer jede passende Hardware
A_DIMMER, A_COLOR, A_MOVE, A_LASER, A_FOG = "dimmer", "color", "move", "laser", "fog"
A_PANEL = "panel_scene"       # Szene aus dem Hauptpanel, fuer eine gewisse Zeit
A_NANO_FX = "nano_fx"         # eigener Effekt des Nanoleaf: laeuft auf dem Geraet, nicht je Panel
ATTR_LABELS = {A_DIMMER: "Dimmer", A_COLOR: "Farbe", A_MOVE: "Bewegung", "pan": "Pan", "tilt": "Tilt", "tilt1": "Tilt 1",
               "tilt2": "Tilt 2", "colorwheel": "Farbrad", "gobo": "Gobo", "gobo_rot": "Gobo-Rotation", "zoom": "Zoom",
               "prism": "Prisma", "shutter": "Shutter", "strobe": "Strobe", "strobe_a": "Strobe A", "strobe_b": "Strobe B",
               "flash": "Blitz", "preset": "WLED-Preset", "pt_speed": "Pan/Tilt-Tempo", "r": "Rot", "g": "Grün", "b": "Blau",
               "w": "Weiß", "uv": "UV", "led_motor": "LED-Motor", "speed": "Tempo", "fan": "Lüfter"}
# Betriebsart-Kanaele: Grenzen gelten, sinnvolle Werte gibt es dort nicht zu programmieren
HIDDEN = {"mode", "function", "auto", "auto_speed", "auto_play", "auto_run", "speed_mode", "reset", "func_speed", "colorwheel_mode"}
FINE = {"pan_fine", "tilt_fine"}


# Namen der festen Stufen am Geraet (presets in fixtures.yaml)
STOP_LABELS = {"white": "Weiß", "red": "Rot", "yellow": "Gelb", "blue": "Blau", "green": "Grün", "orange": "Orange", "purple": "Lila",
               "lightblue": "Hellblau", "open": "Offen", "star": "Stern", "spiral": "Spirale", "dots3": "Drei Punkte",
               "triangle": "Dreieck", "gobo5": "Fünf Punkte"}
EB_FLASH = (8, 32)         # wie show.EB_STROBE: blitzende Effektband-Presets


def options_for(fx, param):
    """Feste Stufen eines Kanals fuer die Auswahlliste: [{v, label}] oder None. Solche Spuren springen, sie blenden nie ueber."""
    if param == "preset":
        names = fx.extra.get("preset_names") or {}
        if not names:
            return None
        sound = set(fx.extra.get("preset_sound") or [])
        return [{"v": int(k), "label": f"{k} {v}" + (" ♫" if int(k) in sound else "") + (" ⚡" if int(k) in EB_FLASH else "")}
                for k, v in sorted(names.items(), key=lambda kv: int(kv[0]))]
    stops = fx.presets.get(param) if isinstance(fx.presets, dict) else None
    if not stops:
        return None
    return [{"v": int(v), "label": STOP_LABELS.get(k, k)} for k, v in sorted(stops.items(), key=lambda kv: kv[1])]


def stepped(fx, param):
    return param == "preset" or options_for(fx, param) is not None


def allowed_params(fx):
    """Kanaele, die eine Spur steuern darf."""
    if fx.locked:
        return []
    out = []
    for p in fx.map:
        if p in fx.locked_params or p in fx.laser_params or p in HIDDEN or p in FINE or p in (A_COLOR, A_MOVE, A_LASER, A_FOG):
            continue
        lim = fx.limits.get(p)
        if lim and p not in ("pan", "tilt", "tilt1", "tilt2") and lim[1] <= 50:
            continue                                   # eng begrenzter Sonderkanal
        out.append(p)
    return out


def move_params(fx):
    """Welche Kanaele folgen der Spur Bewegung: (u-Kanaele, v-Kanaele)."""
    pu = [p for p in ("pan",) if p in fx.map and p not in fx.locked_params]
    pv = [p for p in ("tilt", "tilt1", "tilt2") if p in fx.map and p not in fx.locked_params]
    return pu, pv


def attrs_for(fx):
    """Spuren eines Geraets: [{attr, label, kind, lo, hi}]. Kind: scalar, color oder move."""
    if fx.locked:
        return [{"attr": A_FOG, "label": "Nebel", "kind": "fog", "lo": 0, "hi": 0}] if getattr(fx, "fog", False) else []
    out = []
    if fx.type == "nanoleaf_panel":
        out.append({"attr": A_NANO_FX, "label": "Effekt", "kind": "nano_fx", "lo": 0, "hi": 0})
    has_zones = bool(fx.zones())
    if fx.laser_params:
        out.append({"attr": A_LASER, "label": "Laser", "kind": "laser", "lo": 0, "hi": 0})
    if has_zones or "dimmer" in fx.map:
        out.append({"attr": A_DIMMER, "label": ATTR_LABELS[A_DIMMER], "kind": "scalar", "lo": 0, "hi": 255})
    if has_zones:
        out.append({"attr": A_COLOR, "label": ATTR_LABELS[A_COLOR], "kind": "color", "lo": 0, "hi": 255})
    pu, pv = move_params(fx)
    if (pu or pv) and not (fx.move16 and not fx.extra.get("limits_verified", False)):
        out.append({"attr": A_MOVE, "label": ATTR_LABELS[A_MOVE], "kind": "move", "lo": 0, "hi": 255})
    zone_params = {p for z in fx.zones() for p in z.values()}
    for p in allowed_params(fx):
        if p == "dimmer":
            continue
        if fx.move16 and p in ("pan", "tilt") and not fx.extra.get("limits_verified", False):
            continue                                   # Vega bleibt an der Parkposition, bis die Grenzen bestaetigt sind
        lo, hi = fx.limits.get(p, (0, 255))
        lb = ATTR_LABELS.get(p) or p
        e = {"attr": p, "label": lb, "kind": "scalar", "lo": lo, "hi": hi, "raw": True, "zone": p in zone_params}
        opts = options_for(fx, p)
        if stepped(fx, p):
            e["stepped"] = True
        if opts:
            e["options"] = opts
        out.append(e)
    return out


def fixture_list(rig):
    """Fixture-Browser: alle Geraete mit Adresse und Spuren. Gesperrte stehen dabei, ohne Spuren."""
    out = []
    for fx in rig.fixtures:
        out.append({"name": fx.name, "label": fx.extra.get("label", fx.name), "nr": fx.extra.get("nr"), "type": fx.type,
                    "maker": fx.tdef.get("maker", ""), "address": fx.address, "channels": fx.n, "group": fx.group,
                    "target": fx.target or "", "locked": fx.locked, "attrs": attrs_for(fx),
                    "map": [{"param": p, "ch": c, "locked": p in fx.locked_params or fx.locked, "limit": fx.limits.get(p)}
                            for p, c in sorted(fx.map.items(), key=lambda kv: kv[1])],
                    "desc": fx.tdef.get("desc", {})})
    return out


def default_groups(rig):
    """Vorgegebene Gruppen aus dem Rig (ohne gesperrte Geraete)."""
    out = []
    for g in rig.groups():
        members = [f.name for f in rig.group(g) if not f.locked and attrs_for(f)]
        if members and g != "locked":
            out.append({"id": "rig_" + g, "name": fe.GROUP_LABELS.get(g, g), "fixtures": members, "builtin": True})
    return out


def export_profile(rig, tname):
    """Geraeteprofil als JSON: Kanalliste wie in der Fixture-Seite."""
    t = rig.cfg["types"].get(tname)
    if t is None:
        raise ValueError("Unbekannter Geraetetyp")
    return {"format": "lightbutler-profile-1", "name": tname, "label": t.get("label", tname), "maker": t.get("maker", ""),
            "channels": [{"param": p, "desc": t.get("desc", {}).get(p, ""), "default": t.get("defaults", {}).get(p, 0),
                          "max": t.get("safe_limits", {}).get(p, [0, 255])[1]}
                         for p, _ in sorted(t["map"].items(), key=lambda kv: kv[1])]}


def import_profile(rig, data):
    """Geraeteprofil einlesen: wird ein eigener Typ in fixtures_user.json. Bestehende Typen aus fixtures.yaml bleiben unberuehrt."""
    if not isinstance(data, dict) or data.get("format") != "lightbutler-profile-1":
        raise ValueError("Kein Geraeteprofil (format lightbutler-profile-1)")
    name = fe._slug(str(data.get("name") or data.get("label") or "profil"))
    if not fe.NAME_RE.match(name):
        name = "profil_" + name
    return fe.cmd_type_save(rig, {"name": name, "label": str(data.get("label") or name)[:60],
                                  "maker": str(data.get("maker") or "")[:60], "channels": data.get("channels")})
