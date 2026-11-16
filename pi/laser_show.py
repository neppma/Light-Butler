#!/usr/bin/env python3
"""
laser_show.py - Choreografie des KTV-Lasers (34 Kanaele) fuer die Szene Laser: Faecher und Linien im Takt.

Reine Rechnung ohne Zustand: gleiche Beat-Position, gleiches Bild. Kein Einschalten: Leistung und alle Freigaben bleiben in
Show._render_laser, hier stehen nur Form, Lage und Farbe.

Vom Nutzer am Geraet gefunden (03.11.2026): Kanal 11 links/rechts, Kanal 12 oben/unten, Kanal 14 Breite vom Punkt bis zur
aufgefaecherten Linie, Kanal 15 Muster, gefallen haben 46 und 35, Kanal 6 Zoom (laut Anleitung gross bis klein). Die Muster stehen in
den Einstellungen (Gruppe Laser). Noch nicht bestaetigt: in welcher Richtung Kanal 14 aufgeht.

Jeder Phrasenteil dauert 4 Takte: Faecher auf, Wippen, Schwenken, Faecher pumpen. Break ruhig, Aufbau schliesst sich immer
schneller, Drop voll offen mit Musterwechsel auf jeden Schlag.
"""
import math

FX_DEFAULT = (46, 35, 46, 35, 46)   # Kanal 15: Muster A, B, Drop A, Drop B, Break (Einstellungen ktv_fx_*)
ZOOM_BIG, ZOOM_MID, ZOOM_SMALL = 60, 128, 200   # Kanal 6: kleiner Wert = gross
FAN_POINT, FAN_WIDE = 20, 230    # Kanal 14: Punkt bis aufgefaecherte Linie
POS_MID, POS_SWING = 64, 40      # Kanal 11 und 12: Mitte und Ausschlag im Bereich 1 bis 127
COLORS = (10, 17, 27)            # Kanal 2: rot, gruen, blau
RAINBOW = 255


def _fan(u):
    return int(round(FAN_POINT + (FAN_WIDE - FAN_POINT) * max(0.0, min(1.0, u))))


def _pos(u):
    return int(round(POS_MID + POS_SWING * max(-1.0, min(1.0, u))))


def ktv_scene(beats, state="normal", arousal=0.5, bar=4, fx_set=FX_DEFAULT):
    """Werte fuer den KTV: beats = fortlaufende Beat-Position (mit Nachkommastellen), bar = Schlaege je Takt,
    fx_set = Muster auf Kanal 15 (A, B, Drop A, Drop B, Break)."""
    b = max(0.0, beats)
    beat = int(b)
    x = b - beat                                  # Lage im Schlag 0..1
    bars = b / bar
    part = int(bars // 4) % 4                     # welches Bild, alle 4 Takte ein anderes
    phrase = int(bars // 8)
    color = COLORS[phrase % 3]
    if arousal > 0.65 and phrase % 2 == 1:
        color = RAINBOW
    fx = fx_set[0] if int(bars // 2) % 2 == 0 else fx_set[1]   # alle 2 Takte das andere Muster
    px, py = POS_MID, POS_MID
    zoom = ZOOM_MID
    if state == "drop":                           # voll offen, auf jeden Schlag das andere Muster, nach oben gezogen
        fan = _fan(1.0 - 0.35 * x)
        fx = fx_set[2] if beat % 2 == 0 else fx_set[3]
        py = _pos(-0.4 * (1.0 - x))
        color = RAINBOW
        zoom = ZOOM_BIG
    elif state == "break":                        # ruhig: schmale Linie wandert langsam ueber 2 Takte hin und her
        a = 2 * math.pi * bars / 2
        fx = fx_set[4]
        zoom = ZOOM_SMALL
        fan = _fan(0.25 + 0.1 * math.sin(a))
        px = _pos(0.7 * math.sin(a))
        py = _pos(0.3)
    elif state == "build":                        # Aufbau: schliesst sich im Takt, zum Taktende hin immer schmaler
        fan = _fan((1.0 - (bars % 1.0)) * (0.5 + 0.5 * math.cos(2 * math.pi * x)))
        py = _pos(-0.6 * (bars % 1.0))
        zoom = int(ZOOM_BIG + (ZOOM_SMALL - ZOOM_BIG) * (bars % 1.0))    # zoomt zum Taktende hin kleiner
    elif part == 0:                               # Faecher geht auf jedem Takt vom Punkt zur vollen Breite auf und zoomt mit
        fan = _fan(bars % 1.0)
        zoom = int(ZOOM_SMALL + (ZOOM_BIG - ZOOM_SMALL) * (bars % 1.0))
    elif part == 1:                               # Wippen: breite Linie nickt auf und ab, je Schlag eine Richtung
        fan = _fan(0.85)
        py = _pos(math.cos(math.pi * b))
    elif part == 2:                               # Schwenken: schmale Linie laeuft von links nach rechts und zurueck
        fan = _fan(0.35)
        px = _pos(math.sin(2 * math.pi * b / (bar * 2)))
    else:                                         # Pumpen: auf jeden Schlag voll offen, dann schnell zum Punkt
        fan = _fan(math.exp(-3.5 * x))
        py = _pos(0.5 * (-1 if beat % 2 else 1))
        zoom = int(ZOOM_BIG + (ZOOM_SMALL - ZOOM_BIG) * (1.0 - math.exp(-3.5 * x)))
    return {"group": 16, "pattern": 3, "size": zoom, "color": color, "color_speed": 120,
            "pos_x": px, "pos_y": py, "draw": fan, "effect": fx}
