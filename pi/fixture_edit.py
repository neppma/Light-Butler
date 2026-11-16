#!/usr/bin/env python3
"""
fixture_edit.py - Fixtures im Web-Panel bearbeiten.

Aenderungen stehen in  fixtures_user.json  (neben fixtures.yaml). Die Datei fixtures.yaml mit ihren Kommentaren
bleibt unveraendert. Beim Start werden beide zusammengefuehrt:
  * edits   Aenderungen an vorhandenen Fixtures (Name, Nummer, Adresse, Gruppe, Ziel-IP)
  * added   neue Fixtures
  * removed ausgeblendete (geloeschte) Fixtures aus fixtures.yaml
  * types   eigene Geraetetypen (Kanalliste mit Beschreibung, Standardwert, Maximum)
  * desc    Kanalbeschreibungen (Typ -> Parameter -> Text)
  * nano_host  eigene IP-Adresse der Nanoleaf-Panels (leer = wie in nanoleaf.json); nanoleaf.json mit dem Token
               bleibt dabei unveraendert

Namen (name) bleiben fest, geaendert wird nur die Anzeigebezeichnung (label). Gruppen sind nur erlaubt, wenn das Geraet
zu den Auto-Effekten der Gruppe passt.
"""
import copy
import json
import os
import re
import time

import yaml

USER_FILE = "fixtures_user.json"
GROUP_LABELS = {"bars": "Docooler-Balken", "wash": "Wash", "bar": "Barlicht", "fx": "Effekt (Eyes, Derby)",
                "uv": "UV-Leiste", "spot": "Spot (Vega)", "ambient": "Ambiente (WLED)", "locked": "gesperrt (nie angesteuert)",
                "nano": "Nanoleaf"}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
PARAM_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9]{16,64}$")      # Nanoleaf-API-Key (steht in der URL, deshalb nur Buchstaben/Ziffern)
IP_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
ROLES = ["dimmer", "r", "g", "b", "w", "uv", "strobe"]          # Parameter, die das Licht kennt


def empty_user():
    return {"version": 1, "edits": {}, "added": [], "removed": [], "types": {}, "desc": {}, "nano_host": ""}


def user_path_for(yaml_path, cfg=None):
    name = (cfg or {}).get("user_file", USER_FILE)
    return name if os.path.isabs(name) else os.path.join(os.path.dirname(os.path.abspath(yaml_path)), name)


def load_user(path):
    """Gespeicherte Aenderungen laden. Fehlt die Datei oder ist sie defekt, wird 'nichts geaendert' zurueckgegeben."""
    u = empty_user()
    if not path or not os.path.exists(path):
        return u, ""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for k in u:
            if k in d and isinstance(d[k], type(u[k])):
                u[k] = d[k]
        return u, ""
    except (OSError, ValueError) as e:
        return empty_user(), f"{os.path.basename(path)} nicht lesbar: {e}"


def save_user(path, user):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(user, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def apply_user(cfg, user):
    """fixtures.yaml-Daten plus Aenderungen -> zusammengefuehrte Daten (Kopie). Defekte Eintraege werden uebersprungen."""
    c = copy.deepcopy(cfg)
    for tname, tdef in (user.get("types") or {}).items():
        if isinstance(tdef, dict) and tdef.get("map"):
            c["types"][tname] = dict(copy.deepcopy(tdef), custom=True)
    for tname, d in (user.get("desc") or {}).items():
        if tname in c["types"] and isinstance(d, dict):
            c["types"][tname].setdefault("desc", {}).update({k: v for k, v in d.items() if isinstance(v, str)})
    removed = set(user.get("removed") or [])
    out = []
    for e in c["fixtures"]:
        if e["name"] in removed:
            continue
        ed = (user.get("edits") or {}).get(e["name"])
        if ed:
            base_group = e.get("group")
            e = dict(e)
            for k in ("label", "nr", "address", "group"):
                if k in ed:
                    e[k] = ed[k]
            if e.get("group") != base_group:
                e["user_added"] = True                    # Gruppe geaendert: fehlende Kanaele werden nachsichtig behandelt
            if "target" in ed:
                if ed["target"]:
                    e["target"] = ed["target"]
                else:
                    e.pop("target", None)
        out.append(e)
    for a in user.get("added") or []:
        if isinstance(a, dict) and a.get("type") in c["types"] and a.get("name") and a["name"] not in {e["name"] for e in out}:
            out.append(dict(a, user_added=True))
    c["fixtures"] = out
    nh = user.get("nano_host")
    if nh and _ip_ok(nh):
        c["nano_host"] = nh
    return c


def _ip_ok(ip):
    m = IP_RE.match(str(ip))
    return bool(m) and all(int(x) <= 255 for x in m.groups())


def allowed_groups(tname, tdef):
    """Gruppen, die fuer diesen Geraetetyp sinnvoll sind (bestimmt, welcher Auto-Effekt das Geraet steuert)."""
    m = tdef.get("map", {})
    if tdef.get("locked"):
        return ["locked"]
    if tname == "nanoleaf_panel":
        return ["nano"]
    if "pan" in m and "tilt" in m:
        return ["spot"]
    if tname.startswith("wled_"):
        return ["ambient"]
    if "tilt1" in m:
        return ["bars", "wash", "bar", "fx", "ambient"]
    if "uv1" in m:
        return ["uv"]
    if "r1" in m or "led_r" in m or "r" in m:
        return ["wash", "bar", "fx", "ambient"]          # ambient: ruhig wie Theke und Couchtisch
    return ["locked"]


def type_summary(c):
    """Katalog der Typen fuer das Panel."""
    out = []
    for t, d in c["types"].items():
        if t == "nanoleaf_panel":
            continue
        out.append({"name": t, "channels": d["channels"], "custom": bool(d.get("custom")),
                    "groups": allowed_groups(t, d), "map": d["map"], "desc": d.get("desc", {}),
                    "defaults": d.get("defaults", {}), "limits": d.get("safe_limits", {})})
    return out


def ranges(c):
    """DMX-Bereiche je Ziel: {Ziel: [(Name, von, bis)]}."""
    r = {}
    for e in c["fixtures"]:
        t = e.get("target") or c.get("artnet_target", "")
        n = c["types"][e["type"]]["channels"]
        r.setdefault(t, []).append((e["name"], int(e["address"]), int(e["address"]) + n - 1))
    return r


def overlaps(c, name):
    """Warnungen, wenn der DMX-Bereich eines Fixtures andere Fixtures auf demselben Ziel ueberdeckt."""
    out = []
    for t, lst in ranges(c).items():
        mine = [x for x in lst if x[0] == name]
        for _, a, b in mine:
            for n2, a2, b2 in lst:
                if n2 != name and a <= b2 and a2 <= b:
                    out.append(f"Ueberschneidet sich mit {n2} (DMX {a2} bis {b2})")
    return out


def _slug(text):
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("_")
    return (s if s and s[0].isalpha() else "fx_" + s)[:28] or "fx"


def _check_fixture(c, e, tdef, tname, new):
    label = str(e.get("label", "")).strip()
    if not label or len(label) > 60:
        raise ValueError("Der Name darf nicht leer und nicht laenger als 60 Zeichen sein")
    try:
        addr = int(e["address"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Die DMX-Adresse muss eine Zahl sein") from None
    if not 1 <= addr <= 512 - tdef["channels"] + 1:
        raise ValueError(f"Die DMX-Adresse muss zwischen 1 und {512 - tdef['channels'] + 1} liegen ({tdef['channels']} Kanaele)")
    try:
        nr = int(e.get("nr", 0))
    except (TypeError, ValueError):
        raise ValueError("Die Nummer muss eine Zahl sein") from None
    if not 0 <= nr <= 999:
        raise ValueError("Die Nummer muss zwischen 0 und 999 liegen")
    grp = e.get("group", "")
    if grp not in allowed_groups(tname, tdef):
        raise ValueError("Gruppe nicht moeglich fuer diesen Typ. Erlaubt: " + ", ".join(allowed_groups(tname, tdef)))
    tgt = e.get("target")
    if tgt:
        m = IP_RE.match(str(tgt))
        if not m or any(int(x) > 255 for x in m.groups()):
            raise ValueError("Die Ziel-IP muss wie 192.168.1.30 aussehen (leer = OLA-Pi)")
    return label, addr, nr, grp, (str(tgt) if tgt else "")


def cmd_fixture_save(rig, d):
    """Neues Fixture anlegen oder ein vorhandenes aendern. Rueckgabe: (Hinweis, Warnungen, live_gesetzt)."""
    u = copy.deepcopy(rig.user)
    base = apply_user(rig.base_cfg, u)
    new = bool(d.get("new"))
    if new:
        tname = d.get("type")
        if tname not in base["types"] or tname == "nanoleaf_panel":
            raise ValueError("Unbekannter Typ")
        tdef = base["types"][tname]
        existing = {e["name"] for e in base["fixtures"]}
        name = _slug(d.get("label"))
        k, nm = 2, name
        while nm in existing:
            nm, k = f"{name}_{k}", k + 1
        e = {"name": nm, "type": tname, "label": d.get("label"), "address": d.get("address"), "group": d.get("group"),
             "nr": d.get("nr", 0)}
        if d.get("target"):
            e["target"] = d["target"]
        label, addr, nr, grp, tgt = _check_fixture(base, e, tdef, tname, True)
        entry = {"name": nm, "nr": nr, "label": label, "type": tname, "address": addr, "group": grp}
        if tgt:
            entry["target"] = tgt
        u["added"].append(entry)
        name = nm
    else:
        name = d.get("name")
        cur = next((e for e in base["fixtures"] if e["name"] == name), None)
        if cur is None:
            raise ValueError("Fixture nicht gefunden")
        tdef = base["types"][cur["type"]]
        e = dict(cur, **{k: d[k] for k in ("label", "nr", "address", "group", "target") if k in d})
        label, addr, nr, grp, tgt = _check_fixture(base, e, tdef, cur["type"], False)
        added = next((a for a in u["added"] if a["name"] == name), None)
        if added is not None:
            added.update({"label": label, "nr": nr, "address": addr, "group": grp})
            if tgt:
                added["target"] = tgt
            else:
                added.pop("target", None)
        else:
            u["edits"].setdefault(name, {}).update({"label": label, "nr": nr, "address": addr, "group": grp, "target": tgt})
    future = apply_user(rig.base_cfg, u)
    warn = overlaps(future, name)
    rig.user = u
    save_user(rig.user_path, u)
    live = False
    fx = rig.by_name.get(name)
    if fx is not None and not new:                  # Name und Nummer sofort sichtbar machen
        fx.extra["label"], fx.extra["nr"] = label, nr
        live = True
    return name, warn, live


def cmd_fixture_delete(rig, name):
    u = copy.deepcopy(rig.user)
    before = len(u["added"])
    u["added"] = [a for a in u["added"] if a["name"] != name]
    if len(u["added"]) == before:
        base_names = {e["name"] for e in rig.base_cfg["fixtures"]}
        if name not in base_names:
            raise ValueError("Fixture nicht gefunden")
        if name not in u["removed"]:
            u["removed"].append(name)
    u["edits"].pop(name, None)
    rig.user = u
    save_user(rig.user_path, u)


def cmd_fixture_restore(rig, name):
    u = copy.deepcopy(rig.user)
    if name in u["removed"]:
        u["removed"].remove(name)
    rig.user = u
    save_user(rig.user_path, u)


def cmd_desc(rig, tname, param, text):
    """Kanalbeschreibung speichern; wirkt sofort."""
    tdef = rig.cfg["types"].get(tname)
    if tdef is None or param not in tdef["map"]:
        raise ValueError("Kanal nicht gefunden")
    text = str(text or "").strip()
    if len(text) > 300:
        raise ValueError("Die Beschreibung ist zu lang (hoechstens 300 Zeichen)")
    u = copy.deepcopy(rig.user)
    u["desc"].setdefault(tname, {})[param] = text
    rig.user = u
    save_user(rig.user_path, u)
    tdef.setdefault("desc", {})[param] = text


def build_type(d):
    """Typ-Definition aus der Kanalliste des Panels bauen und pruefen."""
    chans = d.get("channels") or []
    if not 1 <= len(chans) <= 64:
        raise ValueError("Ein Typ braucht 1 bis 64 Kanaele")
    m, desc, defaults, limits = {}, {}, {}, {}
    for i, c in enumerate(chans, 1):
        p = str(c.get("param", "")).strip().lower()
        if not PARAM_RE.match(p):
            raise ValueError(f"Kanal {i}: Der Parametername muss aus Kleinbuchstaben, Ziffern und _ bestehen (zum Beispiel dimmer, r, g, b)")
        if p in m:
            raise ValueError(f"Der Parametername {p} kommt doppelt vor")
        m[p] = i
        if str(c.get("desc", "")).strip():
            desc[p] = str(c["desc"]).strip()[:300]
        try:
            dv = int(c.get("default", 0) or 0)
            mx = c.get("max")
            mx = 255 if mx in (None, "") else int(mx)
        except (TypeError, ValueError):
            raise ValueError(f"Kanal {i}: Standardwert und Maximum muessen Zahlen sein") from None
        if not (0 <= dv <= 255 and 0 <= mx <= 255):
            raise ValueError(f"Kanal {i}: Werte muessen zwischen 0 und 255 liegen")
        if dv:
            defaults[p] = dv
        if mx < 255:
            limits[p] = [0, mx]
            if dv > mx:
                raise ValueError(f"Kanal {i}: Der Standardwert liegt ueber dem Maximum")
    if any(k in m for k in "rgb") and not all(k in m for k in "rgb"):
        raise ValueError("Farbgeraete brauchen r, g und b zusammen")
    t = {"channels": len(chans), "map": m}
    for k in ("label", "maker"):                                 # Bezeichnung und Hersteller (Geraeteprofile im Showmanager)
        if str(d.get(k) or "").strip():
            t[k] = str(d[k]).strip()[:60]
    if defaults:
        t["defaults"] = defaults
    if limits:
        t["safe_limits"] = limits
    if desc:
        t["desc"] = desc
    return t


def cmd_type_save(rig, d):
    name = str(d.get("name", "")).strip().lower()
    if not NAME_RE.match(name):
        raise ValueError("Der Typname muss aus Kleinbuchstaben, Ziffern und _ bestehen, mit einem Buchstaben beginnen (zum Beispiel mein_par_8ch)")
    if name in rig.base_cfg["types"]:
        raise ValueError("Diesen Typnamen gibt es schon in fixtures.yaml, bitte einen anderen waehlen")
    t = build_type(d)
    u = copy.deepcopy(rig.user)
    base = apply_user(rig.base_cfg, u)
    if name in u["types"]:                                                  # vorhandenen eigenen Typ aendern: Kanalzahl darf nicht kollidieren
        for e in base["fixtures"]:
            if e["type"] == name and int(e["address"]) + t["channels"] - 1 > 512:
                raise ValueError(f"{e['name']} passt mit {t['channels']} Kanaelen nicht mehr in 512 Adressen")
    u["types"][name] = t
    rig.user = u
    save_user(rig.user_path, u)
    return name


def cmd_type_delete(rig, name):
    if name not in rig.user["types"]:
        raise ValueError("Nur eigene Typen lassen sich loeschen")
    future = apply_user(rig.base_cfg, rig.user)
    used = [e["name"] for e in future["fixtures"] if e["type"] == name]
    if used:
        raise ValueError("Der Typ wird noch benutzt von: " + ", ".join(used))
    u = copy.deepcopy(rig.user)
    u["types"].pop(name, None)
    u["desc"].pop(name, None)
    rig.user = u
    save_user(rig.user_path, u)


def cmd_nano_host(rig, ip):
    """IP-Adresse der Nanoleaf-Panels aendern (wirkt nach dem Neustart). Leer oder gleich nanoleaf.json = keine Aenderung."""
    ip = str(ip or "").strip()
    if ip and not _ip_ok(ip):
        raise ValueError("Die IP-Adresse muss wie 192.168.1.33 aussehen")
    if getattr(rig, "nano_file_host", None) is None:
        raise ValueError("Keine Nanoleaf-Panels eingerichtet (nanoleaf.json fehlt)")
    u = copy.deepcopy(rig.user)
    u["nano_host"] = "" if ip == rig.nano_file_host else ip
    rig.user = u
    save_user(rig.user_path, u)
    return ip or rig.nano_file_host


def cmd_nano_token(rig, token, client=None):
    """Neuen Nanoleaf-API-Key in nanoleaf.json speichern (wirkt nach dem Neustart). Der Key wird nie zurueckgegeben
    oder angezeigt. Vorher wird er am Nanoleaf geprueft: lehnt der ihn ab, wird nichts gespeichert.
    Rueckgabe: True = vom Nanoleaf bestaetigt, False = Nanoleaf nicht erreichbar (ungeprueft gespeichert)."""
    import nanoleaf
    token = str(token or "").strip()
    if not TOKEN_RE.match(token):
        raise ValueError("Der Token besteht nur aus Buchstaben und Ziffern (16 bis 64 Zeichen)")
    if not getattr(rig, "nano_path", None):
        raise ValueError("Keine Nanoleaf-Panels eingerichtet (nanoleaf.json fehlt)")
    cfg = nanoleaf.load_config(rig.nano_path)
    host = (rig.user or {}).get("nano_host") or cfg["host"]
    cl = (client or nanoleaf.Client)(host, token, cfg.get("port", 16021), timeout=2.0)
    try:
        cl.info()
        ok = True
    except nanoleaf.NanoleafError as e:
        if "HTTP 401" in str(e) or "HTTP 403" in str(e):
            raise ValueError("Der Nanoleaf nimmt diesen Token nicht an. Nichts geaendert.") from None
        ok = False
    cfg["token"] = token
    nanoleaf.save_config(cfg, rig.nano_path)
    rig.nano_token_changed = True
    return ok


def reset_user(rig):
    rig.user = empty_user()
    if os.path.exists(rig.user_path):
        os.replace(rig.user_path, rig.user_path + ".alt")


def structure(c):
    """Nur das, was einen Neustart braucht (ohne Namen und Beschreibungen)."""
    fx = sorted((e["name"], e["type"], int(e["address"]), e.get("group", ""), e.get("target", "")) for e in c["fixtures"])
    ty = {t: json.dumps(d.get("map"), sort_keys=True) + json.dumps(d.get("safe_limits"), sort_keys=True) for t, d in c["types"].items()}
    return json.dumps([fx, ty, c.get("nano_host", "")], sort_keys=True, default=str)


def pending_restart(rig):
    """Gibt es gespeicherte Aenderungen, die erst nach einem Neustart wirken?"""
    return (structure(apply_user(rig.base_cfg, rig.user)) != structure(rig.cfg)
            or bool(getattr(rig, "nano_token_changed", False)))


def next_free_address(c, channels, target=""):
    used = []
    for e in c["fixtures"]:
        if (e.get("target") or c.get("artnet_target", "")) == (target or c.get("artnet_target", "")):
            used.append((int(e["address"]), int(e["address"]) + c["types"][e["type"]]["channels"] - 1))
    addr = 1
    for a, b in sorted(used):
        if addr + channels - 1 < a:
            break
        addr = max(addr, b + 1)
    return addr if addr + channels - 1 <= 512 else 1


def export_yaml(c):
    """Zusammengefuehrte Daten als YAML-Text (Kommentare des Originals gehen dabei verloren)."""
    head = ("# fixtures.yaml - Export aus dem Web-Panel von Light-Butler, %s\n"
            "# Enthaelt alle Aenderungen aus dem Panel und die Kanalbeschreibungen (Feld desc je Typ).\n"
            "# Die Kommentare der urspruenglichen Datei sind in dieser Ausgabe nicht enthalten.\n\n" % time.strftime("%Y-%m-%d %H:%M"))
    c = copy.deepcopy(c)
    for e in c["fixtures"]:
        e.pop("user_added", None)
    return head + yaml.safe_dump(c, allow_unicode=True, sort_keys=False, default_flow_style=None, width=140)
