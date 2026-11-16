AKAI APC mini mk2 an der Lichtsteuerung
=======================================

EINRICHTEN (auf dem Raspberry Pi)
---------------------------------
1. Pakete installieren (einmalig):
      sudo apt install -y python3-mido python3-rtmidi
   Falls der Dienst eine eigene Python-Umgebung nutzt:  pip install mido python-rtmidi   (in dieser Umgebung)
2. Dateien nach ~/lichtshow/ kopieren: midi_ctl.py, show.py, dmx.py, webpanel.py
3. Controller per USB anstecken. Pruefen:   aconnect -l      (es muss 'APC mini mk2' mit zwei Ports erscheinen)
4. Dienst neu starten:   sudo systemctl restart lichtshow
5. Im Panel: Bereich "MIDI-Controller (APC mini mk2)" aufklappen. Es muss "verbunden" stehen.

Mit --no-midi in show.conf schaltest du die Funktion aus, mit --midi-map <Datei> nutzt du eine andere Belegungsdatei.


BELEGUNG (Standard)
-------------------
Pads (8x8), Hauptseite (von oben nach unten):
      Reihe 1:     AUTO, Strobe, Wow, Blinder (Sonnenbrille), Freeze, Blackout, Smoke, BPM
                   Alle ausser AUTO und BPM sind Taster: sie wirken nur, solange du drueckst.
                   Smoke: Nebel solange gedrueckt, hoechstens 10 s am Stueck, danach 20 s Pause.
                   BPM blinkt im Takt (auf der Eins etwas laenger).
      Reihe 2:     Bewegung  (Float, Center, Random, Sweep, Circle, Tilt, Pan, Swim)
      Reihe 3:     Licht-Mix (Disco, Carousel, Sparkle, Static, Chase-Out, Chase-In, Scanner, Rainbow)
      Reihe 4 - 8: Szenen 1 bis 40 in der Reihenfolge des Panels, links oben beginnend, zeilenweise
  Farben der Pads: nicht aktiv rot (Reihe 1 gelb, AUTO blau), aktiv gruen, aktive Szene pulsiert gruen.

  SHIFT (Taste rechts unten) gedrueckt halten: die Pads zeigen die Farben
      Reihe 1: (frei), Rot, Orange, Gelb, Gruen, Cyan, Blau, Violett
      Reihe 2: Magenta, Weiss, UV
  Die Pads leuchten in der echten Farbe, gewaehlte hell. Ein Pad waehlt genau eine Farbe (mehrere Farben
  gleichzeitig nur im Panel; im Panel gewaehlte Farben leuchten hier ebenfalls hell).
  SHIFT loslassen: wieder die Hauptseite.

Tasten rechts (von oben nach unten):
  Low, Med, Hot (Speed; die aktive Taste nochmal druecken = Auto, nach der Musik), Laser-Szene,
  (frei), TAP Tempo (4- bis 8-mal im Takt), (frei), (frei)
  AUTO schaltet den Autopilot ein und aus. Ist er an, wirken nur Reihe 1, TAP, Seitenwechsel und Fader.

Tasten unten (von links nach rechts):
  Ziel Bank, Tisch, Tuer, Bar, Laser, (frei), Hauptseite, Farbseite
  (Farbseite = die Farben bleiben stehen, auch ohne SHIFT; Hauptseite = zurueck)

Fader:
  1 Docooler, 2 Washes, 3 PAR Barlicht, 4 Eyes und Derby, 5 UV-Leiste, 6 Vega, 7 Ambiente, 8 Nanoleaf
  9 General Dimmer
  Die Fader haben eine Uebernahme: Ein Wert wirkt erst, wenn der Fader den aktuellen Stand erreicht
  (Fader auf den Stand ziehen/schieben). Aenderst du etwas im Panel, muss der Fader neu "einfangen".
  Die Gruppen-Helligkeit gibt es auch im Panel (Gruppen-Helligkeit unter dem General Dimmer).
  Gruppen-Fader wirken nur auf das Licht, nie auf die Laser. Die Sonnenbrille ignoriert sie (immer 100 %).


ABGLEICH BEIM ERSTEN MAL
-------------------------
1. Panel -> MIDI-Controller -> "LED-Test 1-64": Pad n leuchtet in Farbe n. Notiere, welche Zahlen Rot, Gruen, Blau ... sind,
   falls die Farben der Szenen nicht stimmen. Dann lassen sich in midimap.json die Farbnummern anpassen ("palette").
2. Panel -> MIDI-Controller -> "Tasten-Test": die runden Tasten leuchten nacheinander (erst rechts, dann unten),
   das Panel zeigt dazu die Note. So siehst du, ob Note 112 oben oder unten liegt (Standard: 112 = oben).
   Stimmt die Reihenfolge der rechten Tasten nicht (Low sitzt unten statt oben), in midimap.json eintragen:
      {"scene_top_note": 119}
   (Standard ist 112 = oberste Taste.)
3. Der Monitor im Panel zeigt jede gedrueckte Taste mit ihrer Nummer und dem Port ("Control" = Port 0, "Notes" = Port 1).


EIGENE BELEGUNG (midimap.json neben show.py)
--------------------------------------------
Nur das aendern, was abweicht. Beispiel:
{
  "scene_top_note": 112,
  "palette": {"rot": 5, "blau": 45},
  "pads1": { "56": {"scene": "All off"}, "57": null },
  "pads2": { "0": {"color": "uv"} },
  "buttons": { "104": {"cmd": "laser"} },
  "faders": { "55": {"fader": "blitz_hz"}, "48": {"fader": "group", "group": "bar"} }
}
Pad-Nummer: unten links 0, oben links 56, oben rechts 63. Taste unten 100 bis 107, rechts 112 bis 119, Fader 48 bis 56.
"pads1" ist die Hauptseite, "pads2" die Farbseite (SHIFT).
Aktionen:  {"scene": "Name"}  {"scene_index": 3}  {"color": "rot"}  {"move": "duck"}  {"mix": "Scanner"}  {"speed": "fast"}  (auch auf Tasten)
           {"aim": "bank"}  {"cmd": "auto|blackout|allbright|freeze|blitz|wow|fog|laser|beat|page1|page2"}
Fader:     {"fader": "master"}  {"fader": "group", "group": "bar|wash|barlight|fx|uv|spot|amb|nano"}  {"fader": "blitz_hz"}
Zuordnung laden: Panel -> MIDI-Controller -> "Belegung neu laden" (kein Neustart noetig). null entfernt eine Belegung.
