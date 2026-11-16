#!/usr/bin/env python3
"""
demo_mixxx.py - spielt dem Simulator ein laufendes Lied aus der Demo-Bibliothek vor (wie die Mixxx-Bruecke, per UDP),
damit das Hauptpanel in der Broschuere Titel, Cover, Liedverlauf und Herz zeigt. Nur fuer die Bildschirmfotos.
Aufruf:  python3 docs/broschuere/demo_mixxx.py DEMO_ORDNER [PORT]
"""
import json
import socket
import sys
import time

dest = sys.argv[1]
port = int(sys.argv[2]) if len(sys.argv) > 2 else 9032
lib = json.load(open(dest + "/_mixxx_bibliothek.json", encoding="utf-8"))
song = next(x for x in lib if x[2] == "Luna Vega")
title, du, artist, name, bpm, key, kid, genre, lvl = song[0], song[1], song[2], song[3], song[4], song[5], song[6], song[7], song[8]
plan = {"type": "plan", "d": 1, "key": song[12], "title": title, "du": du, "bpm": bpm, "ki": kid, "genre": genre, "lvl": lvl,
        "ev": [["build", 52.0, 68.0, 0, ""], ["drop", 68.0, 68.0, 0.9, "b"], ["break", 120.0, 136.0, 0, ""], ["drop", 152.0, 152.0, 0.8, "b"]],
        "en": [20, 30, 45, 60, 75, 90, 95, 92, 60, 40, 70, 95, 98, 90, 80, 60, 40, 25],
        "se": [["intro", 0, 20], ["vers", 20, 52], ["main", 68, 120], ["break", 120, 136], ["main", 152, du - 20], ["outro", du - 20, du]]}
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
t0 = time.time() - 75.0                      # mitten im ersten Drop
last_plan = 0.0
while True:
    now = time.time()
    if now - last_plan > 2.0:
        s.sendto(json.dumps(plan).encode(), ("127.0.0.1", port))
        last_plan = now
    pos = ((now - t0) % du) / du
    s.sendto(json.dumps({"d": 1, "pp": pos, "du": du, "rr": 1.0, "bp": bpm, "pl": 1, "tl": 1, "vo": 1.0}).encode(), ("127.0.0.1", port))
    time.sleep(0.1)
