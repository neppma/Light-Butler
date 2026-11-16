#!/usr/bin/env python3
"""
fine.py - Feinregler unter Bewegung (Fan, Speed, Shift, Size) und Licht-Mix (Fade, Speed, Shift, Size), je Knopf eigene Werte.

Jeder Bewegungs- und Licht-Mix-Knopf merkt sich seine vier Werte (0 bis 100 %, 50 % = wie ohne Regler) in fine.json.
Center (Bewegung "home") und Static (Licht-Mix "STOP") haben keine Regler. Die Regler wirken nur, solange ihr Knopf
gewaehlt ist, nie in festen Szenen.
"""
import json
import os
import threading

from texts import MIX_PANEL, MOVES

KEYS = {"mv": ("fan", "speed", "shift", "size"), "mx": ("fade", "speed", "shift", "size")}
BUTTONS = {"mv": [m for m, _, _ in MOVES if m != "home"],          # ohne Center
           "mx": [m for m, _, _ in MIX_PANEL if m != "STOP"]}      # ohne Static
DEFAULT = 50.0


class FineStore:
    def __init__(self, path=None):
        self.path = path
        self.v = {g: {} for g in KEYS}                             # Gruppe -> Knopf -> {Regler: Wert}
        self.lock = threading.Lock()
        self.load()

    def get(self, grp, btn):
        """Die vier Werte eines Knopfes (fehlende = 50 %). None, wenn der Knopf keine Regler hat."""
        if btn not in BUTTONS.get(grp, ()):
            return None
        d = self.v[grp].get(btn, {})
        return {k: float(d.get(k, DEFAULT)) for k in KEYS[grp]}

    def set(self, grp, btn, key, val):
        if grp not in KEYS or btn not in BUTTONS[grp] or key not in KEYS[grp]:
            raise ValueError("Unbekannter Feinregler")
        val = max(0.0, min(100.0, float(val)))
        with self.lock:
            d = self.v[grp].setdefault(btn, {})
            if val == DEFAULT:
                d.pop(key, None)
                if not d:
                    self.v[grp].pop(btn, None)
            else:
                d[key] = val
        self.save()

    def load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            for g in KEYS:
                for btn, vals in (data.get(g) or {}).items():
                    btn = {"KITT": "Scanner"}.get(btn, btn)        # bis 15.11.2026 hiess der Scanner so
                    if btn in BUTTONS[g] and isinstance(vals, dict):
                        d = {k: max(0.0, min(100.0, float(vals[k]))) for k in KEYS[g] if k in vals}
                        if d:
                            self.v[g][btn] = d
        except (OSError, ValueError, TypeError, AttributeError) as e:
            print(f"Hinweis: {os.path.basename(self.path)} nicht lesbar ({e}), Feinregler auf 50 %")

    def save(self):
        if not self.path:
            return
        try:
            tmp = self.path + ".tmp"
            with self.lock, open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.v, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass
