# Showmanager: Architektur

Der Showmanager ist eine Unterseite des Web-Panels (`/shows`, `/shows/edit?show=NAME`). Mit ihm programmierst du eine Lichtshow zu einer MP3 und spielst sie synchron ab. Bedienung siehe `HANDBUCH.md`, Kapitel „Showmanager“.

## Grundsatz: auf die vorhandene Anlage aufsetzen

Die Show schreibt nur in die vorhandenen `Fixture`-Objekte. `Fixture.write`, `Rig.render_all`, `Output`, `DmxRouter`, OLA-Pi, USB-Adapter, WLED und Nanoleaf bleiben unverändert. Deshalb gelten alle Sperren automatisch, und alle Ausgabewege funktionieren wie bisher.

```
Browser (Handy, iPad, Mac)                         Raspberry Pi
+------------------------------+                   +--------------------------------------------------+
| <audio> spielt die MP3       |  Position 5x/s    | Web-Threads (webpanel.py -> showman/api.py)      |
| = Master-Zeitbasis           | ---WebSocket--->  |   clock.py: Uhr folgt der Audio-Position         |
|                              |                   |   store.py: Ordner unter shows/                  |
| Editor: Timeline, Patterns   |  ganze Show       |   timeline.py: prüfen und übersetzen             |
| Playback: Show wählen, Play  | ---HTTP-------->  |                 |  fertige Show (atomar getauscht)|
+------------------------------+                   |                 v                                |
                                                   | Hauptschleife 40 Hz: Show.update(now)            |
                                                   |   engine.py: Werte zur Uhrzeit, Blitz-Grenze     |
                                                   |   Fixture.write: Laser, Hazer, safe_limits       |
                                                   |   Output: jedes Bild genau einmal                |
                                                   |     -> OLA-Pi / USB-DMX, WLED, Nanoleaf          |
                                                   +--------------------------------------------------+
```

## Module

| Datei | Aufgabe | Test |
| --- | --- | --- |
| `pi/showman/patterns.py` | Pattern-Generator: 25 Muster als reine Funktionen der Zeit | `tests/test_showmanager.py` |
| `pi/showman/timeline.py` | Showdatei prüfen, übersetzen, Keyframes und Clips auswerten, zusammenführen | ebenso |
| `pi/showman/clock.py` | Uhr der Show: folgt dem Browser, sanft nachgezogen, läuft ohne Browser frei | ebenso |
| `pi/showman/engine.py` | DMX-Playback-Engine: schreibt in den Rig, Strobe-Grenzen | ebenso |
| `pi/showman/fixtures.py` | Fixture-Manager: Spuren je Gerät, Gruppen, Profile (Anlegen weiter über `/fixtures`) | ebenso |
| `pi/showman/store.py` | Show-Dateiverwaltung | ebenso |
| `pi/showman/analysis.py` | Tempo und Beat-Raster aus der Hüllkurve | ebenso |
| `pi/showman/ws.py` | WebSocket nach RFC 6455, ohne neue Abhängigkeit | ebenso |
| `pi/showman/api.py` | HTTP-Routen im vorhandenen Panel | ebenso |
| `pi/static/sm/core.js` | Datenmodell, Undo, Raster, Verbindung zum Pi | `tests/test_showmanager_js.py` (mit node) |
| `pi/static/sm/timeline.js` | Timeline: Zeichnen auf Canvas, Maus und Touch | im Browser |
| `pi/static/sm/editor.js` | Editor: Leisten, Eigenschaften, Import | im Browser |
| `pi/static/sm/play.js` | Playback-Seite | im Browser |

Geänderte vorhandene Dateien: `show.py` (Aufruf der Engine in `update`, sonst Bild für Bild gleich), `webpanel.py` (Routen, Knopf, Hinweis), `settings.py` (`sm_light_ms`), `texts.py`, `fixture_edit.py` (Hersteller beim Typ), `backup.py` (Shows ohne MP3), `deploy.sh` (lässt `shows/` aus), `.gitignore`.

## Synchronisation

- **Zeitbasis:** Das `<audio>`-Element im Browser. Er meldet 5-mal pro Sekunde `currentTime` über den WebSocket.
- **Netzlaufzeit:** Der Browser misst die Antwortzeit und schickt sie mit. Der Pi rechnet die halbe Laufzeit hinzu und zieht die Verzögerung der Tonausgabe ab, soweit der Browser sie kennt.
- **Regler:** Die Uhr läuft zwischen den Meldungen selbst. Kleine Fehler gleicht sie über das Tempo aus (höchstens ±4 %), damit nichts springt. Zwei Meldungen in Folge mehr als 0,3 s daneben: Sprung. Der Median der letzten Meldungen filtert Ausreißer. Weil der Regler den Fehler immer gegen 0 zieht, gibt es keine Drift (Test: 1 Stunde, Browser 0,1 % schneller, Netz ±30 ms: Abweichung unter 50 ms).
- **Browser weg:** Nach 2 s ohne Meldung läuft die Uhr mit Tempo 1 frei weiter. Die Ausgabe hängt nie am Browser, sie läuft in der Hauptschleife.
- **Fester Versatz:** Einstellung `sm_light_ms`, zum Beispiel für Bluetooth-Lautsprecher, deren Verzögerung der Browser nicht kennt.

## Mixxx als Zeitbasis

- **Erkennung:** Die Brücke schickt im Plan den Fingerabdruck der MP3 (`audio_fingerprint`, ohne Tags, gleiche Rechnung in `store.py` und `mixxx_bridge.py`) und nach und nach die Titel der Bibliothek (`type: lib`, je Paket unter 4096 Byte). `ShowManager.match`: zuerst Fingerabdruck, sonst der gewählte Titel (`mixxx` in `show.json`) mit Länge ±1 s.
- **Ablauf:** `ShowManager.mixxx_tick` läuft 5-mal pro Sekunde in eigenem Thread (Laden von der SD-Karte darf die Hauptschleife nie aufhalten) und liest `Show.mx`. Besitzer der Zeitbasis ist dann `MIXXX`. Der Regler der Uhr arbeitet um das Tempo des Decks herum (`base`), Pitch erzeugt deshalb keine Sprünge.
- **Abschnitte und Cues:** `ShowManager.marks` (Befehl `marks`, der Editor fragt alle 5 s) holt `se` und `cu` aus `MixxxLink.deck_marks`, ohne `mixxx_shift_s`, und schreibt sie mit `store.save_marks` als `marks` in `show.json`, ohne ungespeicherte Änderungen im Editor anzufassen. Nur Anzeige und Einrasten (`Timeline.markAt`), `Compiled` liest sie nicht.
- **Schalter:** `sm_mixxx_auto`, Standard aus. Eine Show aus dem Browser hat nur Vorrang, solange sie mit Licht an spielt. Nach dem Knopf SHOW bleibt das Lied gesperrt (`mx_block`), bis ein anderes läuft.

## Master-Zeile

Spur mit dem Ziel `{"master": true}` und dem Attribut `master`, nur Keyframes, ohne Keyframes nicht in der Datei. `Compiled.master_at` liefert 0..1, `PlaybackEngine.render` multipliziert es mit dem Dimmer des Panels. Die Timeline zeigt sie fest unter den Szenen (`masterRow`). Laser-Leistung und Nebel bleiben davon unberührt.

## Show-Assistent

`assistant.py` trennt Aufbau (`song_info`, `segments`), Regie (`direct`, optional `apply_claude`) und Spuren (`render`). Die Analyse aus Mixxx liegt in `marks` (`se`, `cu`, `ev`, `en`, `lvl`, `genre`), ohne sie schätzt `sections_from_energy` aus `peaks.json`. `render` setzt keine Einzelkanäle und keine Szenen; Laser und Nebel bleiben Clips, die Engine lässt sie nur mit `sm_laser` und `sm_fog` durch. Claude nutzt bewusst `urllib` statt des SDK, damit am Pi kein neues Paket nötig ist. Ein echter Aufruf lief laut Nutzer am 05.11.2026 durch, die Tests stellen die Antwort nach.

## Sicherheit

| Regel | Umsetzung |
| --- | --- |
| Laser | Freigabe des Nutzers vom 03.11.2026, auch beim Start aus Mixxx. Einzelne Laser-Kanäle sind keine Spuren und werden auch aus einer von Hand geänderten Datei verworfen. Nur Laser-Clips, nur mit `sm_laser` (Standard aus), `laser_unlock` nur für ein Bild und nur wenn `engine._laser_ok`: Musik läuft, Zeitquelle meldet sich (0,6 s), nicht kurz nach einem Sprung. BLACKOUT, FREEZE, ALLES HELL und WOW! rufen die Engine gar nicht erst auf. Mode-Kanäle bleiben in `safe_limits` |
| `safe_limits` | Mode- und Reset-Kanäle sind keine Spuren, `Fixture.write` begrenzt in jedem Bild, `hw_unlock` wird nie gesetzt |
| Strobe | Ohne Erlaubnis: Strobe-Kanäle aus (`EXT_NO_STROBE`), blitzende Effektband-Presets aus, `FlashLimiter` lässt je Kanal höchstens 2 Anstiege pro Sekunde durch, egal aus welchem Muster oder welchen Keyframes. Die Erlaubnis schaltet der Showmanager nie selbst ein |
| Hazer | Freigabe des Nutzers vom 03.11.2026, auch beim Start aus Mixxx. Nur Clips `fog_burst`, nur mit `sm_fog` (Standard aus), `Show._fog_cue` nimmt denselben Weg wie der Knopf: höchstens 10 s, Mindestpause, HomeMatic mit ON_TIME. Schaltet die Maschine nie ein, entfällt wenn sie nicht bereit ist. Die Engine fasst den Hazer nicht an, der Nebel-Knopf wirkt weiter |
| Vorrang | BLACKOUT, ALLES HELL, FREEZE und WOW! liegen in `Show.update` vor der Show |
| Vega | Ohne `limits_verified` keine Pan/Tilt-Spuren |
| Keine Ausgabe von allein | Nur Play schaltet die Show ans Licht, im Editor und auf der Playback-Seite ist „Licht an“ der Standard, „Licht aus“ heißt nur anhören. Das Öffnen einer Seite ändert nichts. Nach Stop oder Ende wieder AUTO |

## Bewusste Abweichungen vom Pflichtenheft

- **Kein FastAPI oder Flask:** Das Panel läuft auf `http.server` aus der Standardbibliothek. Der WebSocket ist ein kleines eigenes Modul, damit keine neue Abhängigkeit auf den Pi muss.
- **Kein WaveSurfer.js:** Die Wellenform muss mit der Timeline zoomen und scrollen, außerdem soll das Panel ohne Internet laufen. Der Browser dekodiert die MP3 einmal beim Import und speichert die Spitzenwerte (`peaks.json`), deshalb muss ein Handy beim Öffnen nicht das ganze Lied dekodieren. Falls gewünscht, lässt sich WaveSurfer später lokal einbinden.
- **Musik im Browser, nicht am Pi:** Wie gewünscht. Der Knopf „Ton woanders“ auf der Playback-Seite lässt die Show nach der Uhr des Pi laufen. Ein Abspielen direkt am Pi bräuchte einen MP3-Decoder und einen Tonausgang am Pi.
- **Fixtures:** Geräte anlegen geht über die vorhandene Seite `/fixtures`, damit es nur eine Quelle gibt. `fixtures.json` in der Show ist nur eine Kopie zum Nachsehen.

## Noch offen

- Noch nicht an echter Hardware und nicht mit echten MP3s auf dem iPad geprüft. Die Timing-Werte stammen aus dem Simulator.
- Mixxx-Automatik nur mit nachgespielten Mixxx-Meldungen geprüft, die neue Brücke lief noch nicht am Mac. Lieder ohne Analyse werden nicht erkannt.
- Der Editor ist nur auf Deutsch.
- Das Tempo ist je Show fest (keine Tempowechsel im Lied).
- Der Hersteller lässt sich bisher nur über ein Profil setzen, nicht im Typ-Formular von `/fixtures`.
- Import von Profilen fremder Formate (zum Beispiel GDTF, QLC+) ist vorbereitet (`fixtures.import_profile`), aber nur für das eigene JSON-Format gebaut.
