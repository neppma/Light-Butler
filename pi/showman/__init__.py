"""
showman - DMX-Showmanager: Lichtshows zu einer MP3 programmieren und synchron abspielen (Seiten /shows und /shows/edit).

Module (jedes einzeln testbar, Aufbau in docs/SHOWMANAGER.md):
  patterns   Pattern-Generator: fertige Lichtmuster als reine Funktionen der Zeit
  timeline   Timeline-Engine: Showdatei pruefen, uebersetzen, Keyframes und Patterns zu einem Zeitpunkt auswerten
  clock      Synchronisation: Uhr der Show, folgt der Audio-Position des Browsers ohne Drift
  engine     DMX-Playback-Engine: schreibt die Werte in den Rig, im Takt der Show, mit allen Sicherheitsgrenzen
  fixtures   Fixture-Manager: was der Rig anbietet (Spuren, Gruppen, Profile)
  store      Show-Dateiverwaltung: Ordner je Show unter shows/
  analysis   Tempo und Beat-Raster aus der Huellkurve der Musik
  ws         kleiner WebSocket nach RFC 6455 (ohne neue Abhaengigkeit)
  api        HTTP-Routen im vorhandenen Web-Panel

Die Show (show.py) kennt nur engine.PlaybackEngine ueber Show.showman. Ohne gestartete Show bleibt das Licht Bild fuer Bild gleich.
"""
