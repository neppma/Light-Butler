"""
safety.py - Sicherheitshinweis bei einer neuen Anlage (Wunsch von Markus, 15.11.2026): einmal pro Anlage, nicht pro Geraet.

Gemerkt in sicherheit.json neben settings.json ({"ok": true, "t": Zeit}). Die Installationsskripte (Pi, Windows, Mac,
Light-Butler.exe) legen {"ok": false} an, dann zeigt das Panel den Hinweis, bis jemand "Verstanden" drueckt. Fehlt die Datei,
ist es eine bestehende Anlage (kein Hinweis), ausser es gibt auch noch keine settings.json (frisch aus dem Quelltext) und es
ist kein Simulator. Aufs Licht wirkt das nie.
"""
import json
import os
import time

FILE = "sicherheit.json"


def is_open(base, simulate=False):
    p = os.path.join(base, FILE)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return not bool(json.load(f).get("ok"))
        except (OSError, ValueError, AttributeError):
            return False
    return (not simulate) and not os.path.exists(os.path.join(base, "settings.json"))


def confirm(base, now=None):
    p = os.path.join(base, FILE)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"ok": True, "t": int(now if now is not None else time.time())}, f)
    os.replace(tmp, p)
