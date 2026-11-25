#!/usr/bin/env python3
"""
texts.py - Texte des Web-Panels auf Deutsch und Englisch, im Panel aenderbar.

Jeder Text hat einen festen Schluessel (z. B. "mix:Scanner", "h_speed", "m_sys", "grp:Laser") und einen deutschen und
englischen Standard. Welche Sprache gilt, waehlt die Einstellung ui_lang. Eigene Texte aus der Uebersetzungstabelle
(Einstellungen -> Panel) stehen in texts.json; dort steht nur, was vom Standard abweicht. Ein senkrechter Strich |
ist ein Zeilenumbruch auf dem Knopf. Die Texte werden im Panel nur als Text angezeigt, nie als HTML.
"""
import json
import os
import threading

# Knoepfe im Bedienbereich: (interne Kennung, Deutsch, English). Die Kennung bleibt fest (APC mini, Szenen).
MOVES = [("duck", "Ente", "Float"), ("home", "Stop", "Center"), ("random", "Zufall", "Random"), ("sweep", "Besen", "Sweep"),
         ("circle", "Kreis", "Circle"), ("vertical", "Rauf-Runter", "Tilt"), ("horizontal", "Rechts-Links", "Pan"),
         ("fan", "Schwimmer", "Swim")]
COLORS = [("auto", "Auto", "Auto"), ("rot", "Rot", "Red"), ("orange", "Orange", "Orange"), ("gelb", "Gelb", "Yellow"),
          ("gruen", "Grün", "Green"), ("cyan", "Cyan", "Cyan"), ("blau", "Blau", "Blue"), ("violett", "Violett", "Violet"),
          ("magenta", "Magenta", "Magenta"), ("white", "Weiß", "White"), ("uv", "UV", "UV")]
SPEEDS = [("auto", "Auto", "Auto"), ("slow", "Langsam", "Low"), ("mid", "Mittel", "Med"), ("fast", "Schnell", "Hot")]
AIMS = [("", "Frei", "Free"), ("bank", "Bank (Sofa)", "Couch"), ("tisch", "Tisch", "Table"), ("tuer", "Tür", "Door"),
        ("bar", "Bar", "Bar")]
# Licht-Mix-Knoepfe: Reihenfolge im Panel. Links die interne Kennung (MIX_BUTTONS, auch fuer den APC mini,
# midimap.json und gespeicherte Szenen).
MIX_PANEL = [("Discokugel", "Discokugel", "Disco"), ("Karussell", "Karussell", "Carousel"),
             ("Sternenhimmel", "Sternenhimmel", "Sparkle"), ("STOP", "STOP", "Static"),
             ("nach aussen", "nach außen", "Chase-Out"), ("nach innen", "nach innen", "Chase-In"),
             ("Scanner", "Scanner", "Scanner"), ("Regenbogen", "Regenbogen", "Rainbow")]

# feste Texte (data-tx im HTML): Schluessel -> (Deutsch, English)
TOP = {"auto": ("AUTO", "AUTO"), "black": ("BLACK|OUT", "BLACK|OUT"), "sun": ("SONNEN|BRILLE", "BLINDER"),
       "strobe_hdr": ("STROBE", "STROBE"), "strobe_ok": ("erlaubt", "allowed"), "yes": ("JA", "YES"), "no": ("nein", "no"),
       "strobe_perm": ("Strobe-Erlaubnis", "Strobe permission"),
       "strobe_perm_desc": ("Erst mit Erlaubnis sind mehr als 3 Blitze pro Sekunde, der Strobo-Burst und der Einzel-Strobe möglich. Schnelles Blitzen kann Anfälle auslösen. Nach einem Neustart gilt wieder die Vorgabe aus show.conf.",
                            "Only with permission are more than 3 flashes per second, the strobe burst and the single strobe possible. Fast flashing can trigger seizures. After a restart the default from show.conf applies again."),
       "fog": ("NEBEL", "SMOKE"), "fog_on": ("läuft", "on"), "fog_off": ("aus · tippen", "off · tap"), "fog_heat": ("heizt", "heating"),
       "fog_waitsw": ("warte auf Schalter", "waiting for switch"), "fog_ready": ("bereit", "ready"), "fog_pause": ("Pause", "pause"), "fog_err_ccu": ("keine CCU", "no CCU"), "fog_err_power": ("Steckdose", "socket"),
       "pwr_off": ("aus", "off"),
       "pwr_q": ("%s einschalten? (Steckdose: %l)", "Switch on %s? (socket: %l)"),
       "fog_power_q": ("Nebelmaschine einschalten?\n\nRauchmelder im Raum vorher deaktivieren!", "Switch on the fog machine?\n\nDeactivate the smoke detectors in the room first!"),
       "fog_cancel_q": ("Aufheizen abbrechen und die Nebelmaschine ausschalten?", "Cancel warming up and switch the fog machine off?"),
       "fog_note_on": ("⚠ Nebel: Rauchmelder deaktiviert?", "⚠ Fog: smoke detectors deactivated?"),
       "fog_note_off": ("✓ Nebelmaschine aus: Rauchmelder wieder aktivieren", "✓ Fog machine off: reactivate the smoke detectors"),
       "ok": ("OK", "OK"), "freeze": ("FREEZE", "FREEZE"), "wow": ("WOW!", "WOW!"),
       "blitz": ("STROBE", "STROBE")}
STYLE_BTNS = [("auto", "Auto", "Auto"), ("weihnachten", "Weihnachten", "Christmas"), ("club", "Club", "Club"),
              ("party", "Party", "Party"), ("rock", "Rock", "Rock"), ("ruhig", "Ruhig", "Calm")]
HEADS = {"h_style": ("Stil", "Style"), "h_speed": ("Geschwindigkeit", "Speed"), "h_beam": ("Lichtstrahl", "Beam"), "h_eb": ("Effektband", "Effect strip"), "h_mix": ("Licht-Mix", "Light Mix"), "h_move": ("Bewegung", "Movement"),
         "h_color": ("Farbe", "Color"), "h_aim": ("Ziel für alle Bewegungen", "Target for all movements"),
         "h_scenes": ("Szenen", "Scenes"), "h_settings": ("Einstellungen (Auto-Erkennung)", "Settings (auto detection)"),
         "h_fixtures": ("Fixtures", "Fixtures"), "h_room": ("Raumplan", "Room plan"), "h_matrix": ("Pixel-Matrix", "Pixel matrix"), "h_music": ("Musik-Datenbank", "Music library"), "music_host": ("Musik-Rechner", "music computer"), "h_autotag": ("Tag-Vorschläge", "Tag suggestions"), "h_dupes": ("Doppelte", "Duplicates"), "h_titles": ("Titel bereinigen", "Clean up titles"), "h_check": ("Dateien prüfen", "Check files"), "h_genres": ("Genres", "Genres"), "h_cd": ("CD-Assistent", "CD assistant"), "h_folders": ("Ordner umbenennen", "Rename folders"), "h_import": ("Import", "Import"), "h_merge": ("Ordner auflösen", "Dissolve folder"), "h_lose": ("Lose Album-Lieder", "Loose album songs"), "h_mirror": ("Spiegeln", "Mirror"), "h_fnametags": ("Tags aus Dateinamen", "Tags from file names"), "h_care": ("Datenpflege", "Library care"), "h_pre": ("Vorab-Läufe", "Runs in advance"), "h_autodj": ("Auto-DJ", "Auto DJ"), "h_radio": ("Internetradio", "Internet radio"), "h_artists": ("Interpreten", "Artists"), "h_albums": ("Alben", "Albums"), "h_favs": ("Favoriten", "Favourites"), "h_missing": ("Fehlt mir", "Missing songs"), "h_damaged": ("Beschädigte Dateien", "Damaged files"), "h_groups": ("Gruppen", "Groups"),
         "bz_label": ("Blitze/s", "Flashes/s"), "bz_max": ("max. 3 ohne Erlaubnis", "max. 3 without permission"),
         "color_hint": ("Mehrere Farben antippen: Sie wechseln sich bei jeder Phrase und jedem Drop ab. Nochmal antippen nimmt eine Farbe wieder weg, ohne Farbe folgt sie der Stimmung.",
                        "Tap several colors: they alternate on every phrase and drop. Tap again to remove a color; with no color selected, it follows the mood.")}
MENUS = {"m_home": ("Haus", "Home"), "m_gl": ("Gruppen-Helligkeit", "Group brightness"),
         "gl_btn": ("Gruppen", "Groups"), "gl_mod": ("geändert", "changed"), "m_tempo": ("Tempo (manuell)", "Tempo (manual)"),
         "m_sys": ("Verbindungen", "Connections"), "m_gen": ("Einstellungen allgemein", "General settings"), "apc_title": ("APC mini · Belegung", "APC mini · Mapping"), "apc_page": ("Belegung als Grafik", "Mapping as a picture"),
         "apc_main": ("Hauptseite", "Main page"), "apc_colors": ("Farbseite", "Colour page"), "apc_free": ("frei", "free"),
         "lumi_title": ("ROLI Lumi · Belegung", "ROLI Lumi · Mapping"), "lumi_win": ("Seite", "Page"), "apc_pick": ("Pad, Taste oder Fader antippen oder am APC betätigen, dann die Belegung wählen. Sie wirkt sofort.", "Tap a pad, button or fader or use it on the APC, then choose the assignment. It takes effect at once."),
         "apc_reset_q": ("Eigene APC-Belegung löschen und Standard wiederherstellen?", "Delete the custom APC mapping and restore the default?"), "apc_lg_scene": ("Szenen", "Scenes"), "apc_lg_aim": ("Ziele", "Aim positions"), "apc_lg_fader": ("Fader", "Faders"), "lumi_edit": ("Umbelegen", "Remap"), "lumi_done": ("Fertig", "Done"), "lumi_pick": ("Taste antippen oder am Lumi drücken, dann die Belegung wählen. Sie wirkt sofort.", "Tap a key or press it on the Lumi, then choose the assignment. It takes effect at once."),
         "lumi_key": ("Note", "Note"), "lumi_free": ("frei", "free"), "lumi_reset": ("Standard wiederherstellen", "Restore default"), "lumi_reset_q": ("Eigene Belegung löschen und Standard wiederherstellen?", "Delete the custom mapping and restore the default?"),
         "lumi_stale": ("Die Tasten am Lumi leuchten noch in den alten Farben: Lumi-Programm neu herunterladen und im ROLI Dashboard auf den Lumi ziehen.", "The keys on the Lumi still show the old colours: download the Lumi program again and drag it onto the Lumi in ROLI Dashboard."), "lumi_dl": ("⬇ Lumi-Programm", "⬇ Lumi program"),
         "lumi_hint": ("Die Pfeile zeigen die übrigen Seiten, wie die Pfeile am Lumi. Gedrückte Tasten blitzen auf. Die Tasten am Gerät zeigen diese Farben, wenn das Lumi-Programm geladen ist (Knopf oben, Datei im ROLI Dashboard auf den Lumi ziehen). Ändern mit dem Knopf Umbelegen.", "The arrows show the other pages, like the arrows on the Lumi. Pressed keys flash. The keys on the device show these colours when the Lumi program is loaded (button above, drag the file onto the Lumi in ROLI Dashboard). Change the mapping with the Remap button."),
         "lumi_lg_color": ("Farben", "Colours"), "lumi_lg_fx": ("Schnelleffekte", "Quick effects"), "lumi_lg_speed": ("Speed", "Speed"), "lumi_lg_move": ("Bewegung", "Movement"),
         "lumi_lg_mix": ("Licht-Mix", "Light mix"), "lumi_lg_scene": ("Szenen", "Scenes"), "lumi_lg_black": ("Blackout", "Blackout"),
         "apc_conn": ("verbunden", "connected"), "apc_noconn": ("nicht verbunden", "not connected"),
         "apc_hint": ("Pads in ihrer LED-Farbe wie am Gerät, gedrückte Tasten blitzen kurz auf. Ändern mit dem Knopf Umbelegen.", "Pads in their LED colour as on the device, pressed buttons flash briefly. Change the mapping with the Remap button."), "h_setpage": ("Einstellungen", "Settings"),
         "hl_title": ("Zustand des Light-Butler", "Light-Butler health"), "nav_back": ("Zurück", "Back"), "nav_home": ("Panel", "Panel"), "nav_menu": ("Menü", "Menu"),
         "h_health": ("Zustand", "Health"), "h_help": ("Hilfe", "Help"), "h_editor": ("Show-Editor", "Show editor"),
         "nav_devices": ("Geräte", "Devices"), "nav_tech": ("Technik", "Tools"),
         "nav_soft": ("Software für andere Rechner", "Software for other computers"),
         "h_software": ("Systemschema und Downloads", "System diagram and downloads"),
         "sw_hint": ("Welcher Teil gehört auf welchen Rechner? Im Schema das Symbol antippen, dann kommt das passende Paket.", "Which part belongs on which computer? Tap the symbol in the diagram to get the matching package."),
         "dl_mac": ("Mac: Mixxx-Brücke und Helfer (ZIP)", "Mac: Mixxx bridge and helper (ZIP)"),
         "dl_win": ("Windows: Pegelkurven (ZIP)", "Windows: level curves (ZIP)"),
         "dl_win_full": ("Windows: ganzer Light-Butler (ZIP)", "Windows: complete Light-Butler (ZIP)"),
         "dl_mac_full": ("Mac: ganzer Light-Butler (ZIP)", "Mac: complete Light-Butler (ZIP)"),
         "dl_win_exe": ("Windows: Light-Butler.exe ohne Python (ZIP)", "Windows: Light-Butler.exe without Python (ZIP)"),
         "dl_pi": ("Pi: frische Installation (ZIP)", "Pi: fresh installation (ZIP)"),
         "dl_pi_own": ("Pi: Ersatzgerät mit meinen Geräten (ZIP)", "Pi: spare unit with my devices (ZIP)"),
         "dl_pi_hint": ("Neuer Raspberry Pi (Pi OS 64 Bit): ZIP auf den Pi kopieren, entpacken, bash install_pi.sh. Ohne persönliche Daten; das Ersatzgerät enthält zusätzlich deine Geräte mit ihren Adressen. Startet mit allen Ausgaben aus.", "New Raspberry Pi (Pi OS 64-bit): copy the ZIP to the Pi, unpack it, bash install_pi.sh. Without personal data; the spare unit also contains your devices with their addresses. Starts with all outputs off."),
         "dl_backup": ("Jüngste Sicherung des Light-Butler (ZIP)", "Latest backup of the Light-Butler (ZIP)"),
         "dl_backup_hint": ("Die Sicherung entsteht jede Nacht um 04:30 am Light-Butler. Zum Aufheben auf einem anderen Gerät, ohne Nanoleaf-Token und Claude-Schlüssel.", "The backup is made every night at 04:30 on the Light-Butler. To keep on another device, without the Nanoleaf token and the Claude key."),
         "dl_hint": ("Für einen neuen Rechner: entpacken, LIESMICH.txt lesen, das Installationsskript richtet alles samt Python-Paketen ein.",
                     "For a new computer: unpack, read LIESMICH.txt, the install script sets up everything including the Python packages."), "hl_help": ("Hilfe (Handbuch)", "Help (manual)"), "hl_ok": ("Mir geht's gut", "I'm doing fine"),
         "sf_title": ("Bevor es losgeht: Sicherheit", "Before you start: safety"),
         "sf_intro": ("Der Light-Butler steuert Geräte, die Menschen gefährden können. Er schaltet nichts Gefährliches von selbst ein. Was du freigibst, verantwortest du.", "The Light-Butler controls devices that can endanger people. It never switches anything dangerous on by itself. Whatever you enable is your responsibility."),
         "sf_strobe": ("Strobe und schnelles Blitzen können epileptische Anfälle auslösen. Die Strobe-Erlaubnis ist aus; schalte sie nur ein, wenn alle Gäste Bescheid wissen.", "Strobe and fast flashing can trigger epileptic seizures. Strobe permission is off; only switch it on when all guests know about it."),
         "sf_laser": ("Laser nie in Augenhöhe und nie ins Publikum richten. Laser sind gesperrt, bis du sie ausdrücklich freigibst.", "Never aim lasers at eye level or into the audience. Lasers are locked until you explicitly enable them."),
         "sf_fog": ("Nebel löst Rauchmelder aus und kann Atemwege reizen. Er kommt nur auf Knopfdruck, in kurzen Schüben.", "Fog sets off smoke detectors and can irritate the airways. It only comes at the press of a button, in short bursts."),
         "sf_out": ("Alle Ausgaben sind aus, bis du sie unter Einstellungen → Ausgabe einschaltest. So kämpfen nie zwei Steuerungen um dasselbe Licht.", "All outputs are off until you switch them on under Settings → Output. That way two controllers never fight over the same light."),
         "sf_rig": ("Geräte, Kabel und Stative musst du selbst sicher aufstellen. Die Software kann das nicht prüfen.", "You have to set up devices, cables and stands safely yourself. The software cannot check that."),
         "sf_gpl": ("Light-Butler ist freie Software (GPLv3) und kommt ohne jede Gewährleistung.", "Light-Butler is free software (GPLv3) and comes without any warranty."),
         "sf_ok": ("Verstanden", "Understood"), "sf_more": ("Über Light-Butler", "About Light-Butler"),
         "h_about": ("Über Light-Butler", "About Light-Butler"),
         "mylinks": ("Eigene Links", "Own links"), "ml_next": ("Weiter", "Next"), "ml_save": ("Speichern", "Save"),
         "ml_hint": ("Ein Gerät im Heimnetz mit eigener Webseite (zum Beispiel ein Dashboard am Fernseher): Adresse und Port eintragen (oder eine ganze Adresse mit Pfad einfügen, zum Beispiel http://localhost:8123/party-sender.html; localhost ist das Gerät, auf dem du tippst), Weiter, Namen vergeben. Der Knopf öffnet die Seite in einem neuen Tab.", "A device in the home network with its own web page (for example a dashboard on the TV): enter address and port (or paste a whole address with a path, for example http://localhost:8123/party-sender.html; localhost is the device you tap on), Next, give it a name. The button opens the page in a new tab."),
         "h_eichen": ("Eichstück: Erkennung prüfen", "Test piece: check the detection"),
         "hl_warn": ("Mir geht's ganz gut, aber:", "I'm OK, but:"), "hl_crit": ("Mir geht's nicht gut:", "I'm not doing well:"),
         "hl_wait": ("Messe gerade ...", "Measuring ..."),
         "hl_s_ok": ("OK", "OK"), "hl_s_warn": ("Achtung", "Warning"), "hl_s_crit": ("Kritisch", "Critical"),
         "hl_pi_up": ("Licht-Rechner läuft seit", "Lighting computer up for"), "hl_show_up": ("Show läuft seit", "Show up for"),
         "hl_frames": ("Show-Takt", "Show timing"), "hl_fps": ("Bilder/s (Soll 40)", "frames/s (target 40)"),
         "hl_work": ("ms Rechenzeit je Bild (von 25)", "ms of work per frame (of 25)"),
         "hl_late": ("Aussetzer letzte Minute", "dropouts last minute"), "hl_late_all": ("Aussetzer seit Start", "dropouts since start"),
         "hl_worst": ("Längste Lücke (letzte Minute)", "Longest gap (last minute)"),
         "hl_cpu": ("CPU", "CPU"), "hl_cpu_all": ("gesamt", "total"), "hl_core": ("Kern", "Core"), "hl_load": ("Last 1/5/15 min", "Load 1/5/15 min"),
         "hl_clock": ("Takt", "Clock"), "hl_showcpu": ("Show-Programm", "Show program"), "hl_onecore": ("eines Kerns", "of one core"),
         "hl_iowait": ("Warten auf Speicher", "Waiting for storage"),
         "hl_temp": ("Temperatur", "Temperature"), "hl_tnow": ("CPU", "CPU"), "hl_tmax": ("Höchstwert seit Start", "peak since start"),
         "hl_tlimit": ("Der Pi bremst sich ab 80 °C selbst", "The Pi throttles itself from 80 °C"),
         "hl_hour": ("Letzte Stunde", "Last hour"), "hl_ago": ("vor # min", "# min ago"), "hl_now": ("jetzt", "now"),
         "hl_mem": ("RAM", "RAM"), "hl_free": ("frei", "free"), "hl_of": ("von", "of"), "hl_swap": ("Auslagerung", "Swap"),
         "hl_showmem": ("Show-Programm", "Show program"), "hl_grow": ("seit Start", "since start"),
         "hl_disk": ("Speicher", "Storage"), "hl_sd": ("Speicher (SD-Karte)", "Storage (SD card)"), "hl_ssd": ("Speicher (SSD)", "Storage (SSD)"),
         "hl_written": ("Geschrieben seit Rechner-Start", "Written since computer start"), "hl_backup": ("Letzte Sicherung", "Last backup"),
         "hl_h_ago": ("vor # h", "# h ago"), "hl_nobackup": ("keine gefunden", "none found"), "hl_ro": ("schreibgeschützt!", "read-only!"),
         "hl_sys": ("Strom und Verbindungen", "Power and connections"), "hl_power": ("Stromversorgung", "Power supply"),
         "hl_power_ok": ("in Ordnung", "fine"), "hl_power_uv": ("Unterspannung", "under-voltage"), "hl_power_thr": ("gebremst", "throttled"),
         "hl_power_ever": ("seit Pi-Start", "since Pi start"), "hl_restarts": ("Automatische Neustarts", "Automatic restarts"),
         "hl_devices": ("Geräte", "Devices"), "hl_all_reach": ("alle erreichbar", "all reachable"), "hl_notreach": ("nicht erreichbar:", "not reachable:"),
         "hl_network": ("Netzwerk", "Network"), "hl_mixxx": ("Mixxx", "Mixxx"), "hl_conn": ("verbunden", "connected"), "hl_noconn": ("nicht verbunden", "not connected"),
         "hl_audio": ("Audio-Aussetzer (Minute)", "Audio dropouts (minute)"), "hl_send": ("Sendefehler (Minute)", "Send errors (minute)"),
         "hl_i_temp": ("CPU-Temperatur # °C", "CPU temperature # °C"), "hl_i_cpu": ("Ein CPU-Kern ist zu # % belegt", "One CPU core is # % busy"),
         "hl_i_iow": ("Die CPU wartet zu # % auf den Speicher, die Karte ist langsam", "The CPU spends # % waiting for storage, the card is slow"),
         "hl_i_mem": ("Nur noch # MB RAM frei", "Only # MB RAM free"), "hl_i_disk": ("Nur noch # GB Speicher frei", "Only # GB storage free"),
         "hl_i_ro": ("Der Speicher ist schreibgeschützt, die Karte hat vermutlich Fehler", "Storage is read-only, the card probably has errors"),
         "hl_i_fps": ("Nur # Bilder/s statt 40", "Only # frames/s instead of 40"), "hl_i_work": ("Ein Bild braucht # ms von 25 ms", "A frame takes # ms of 25 ms"),
         "hl_i_late": ("# Aussetzer in der letzten Minute", "# dropouts in the last minute"),
         "hl_i_uv_now": ("Unterspannung gerade jetzt: Netzteil oder Kabel prüfen", "Under-voltage right now: check power supply or cable"),
         "hl_i_uv": ("Unterspannung seit dem Pi-Start: Netzteil oder Kabel prüfen", "Under-voltage since Pi start: check power supply or cable"),
         "hl_i_thr_now": ("Die CPU wird gerade gebremst", "The CPU is being throttled right now"),
         "hl_i_thr": ("Die CPU wurde seit dem Pi-Start gebremst", "The CPU was throttled since Pi start"),
         "hl_i_aerr": ("Der Audio-Eingang meldet einen Fehler", "The audio input reports an error"),
         "hl_i_audio": ("# Audio-Aussetzer in der letzten Minute", "# audio dropouts in the last minute"),
         "hl_i_send": ("# Sendefehler ans Licht in der letzten Minute", "# send errors to the lights in the last minute"),
         "hl_i_down": ("Nicht erreichbar: #", "Not reachable: #"), "hl_i_restart": ("Der Dienst ist # mal von selbst neu gestartet", "The service restarted itself # times"),
         "hl_i_backup": ("Letzte Sicherung vor # Stunden", "Last backup # hours ago"), "hl_i_nobackup": ("Keine Sicherung gefunden", "No backup found"),
         "stat_title": ("Statistik", "Statistics"), "stat_lib": ("Mixxx-Bibliothek", "Mixxx library"),
         "stat_tracks": ("Titel", "Tracks"), "stat_done": ("analysiert", "analysed"), "stat_hours": ("Stunden Musik", "hours of music"),
         "stat_cues": ("mit Hotcues", "with hotcues"), "stat_styles": ("Stile", "Styles"), "stat_energy": ("Energie aus dem Tag", "Energy from the tag"),
         "stat_none": ("ohne", "none"), "stat_bpm": ("Tempo (BPM)", "Tempo (BPM)"), "stat_genres": ("Genres", "Genres"),
         "stat_played": ("Gespielt seit dem Start", "Played since start"), "stat_noplay": ("Noch kein erkannter Titel gespielt.", "No recognized track played yet."),
         "stat_nolib": ("Noch keine Daten vom Musik-Rechner. Die Mixxx-Brücke schickt die Statistik alle 30 Sekunden, sobald sie läuft (aktuelle Version: install_launcher.sh).", "No data from the music computer yet. The Mixxx bridge sends the statistics every 30 seconds while it runs (current version: install_launcher.sh)."),
         "stat_age": ("Stand vom Musik-Rechner: vor # s", "Music computer data: # s ago"), "stat_files": ("Dateitypen", "File types"),
         "stat_bg": ("Hintergrund-Analyse", "Background analysis"), "stat_bg_run": ("läuft", "running"), "stat_bg_pause": ("pausiert (Lied in Mixxx hat Vorrang)", "paused (track in Mixxx has priority)"),
         "stat_bg_end": ("fertig", "finished"), "stat_bg_off": ("aus (config.sh: BACKGROUND_ANALYSIS)", "off (config.sh: BACKGROUND_ANALYSIS)"),
         "stat_bg_line": ("# von # Liedern in dieser Sitzung analysiert, # nicht lesbar", "# of # tracks analysed in this session, # unreadable"), "stat_bg_gone": ("Dazu # alte Einträge: die Datei gibt es nicht mehr (alter Pfad in Mixxx) oder das Lied wurde seither geändert. Sie stehen nicht in der Liste", "Plus # old entries: the file no longer exists (old path in Mixxx) or the track has changed since. They are not in the list"), "m_backup": ("Sicherung", "Backup"),
         "m_midi": ("MIDI-Controller (APC mini mk2)", "MIDI controller (APC mini mk2)"), "m_audio": ("Audio-Eingang", "Audio input")}
# Statuszeilen oben (Ereignisfeld, Modus-Zeile, Dimmer, Mixxx-Zeile, Warnungen)
STATUS = {"ev_idle": ("keine Musik", "no music"), "ev_normal": ("normal", "normal"), "ev_build": ("AUFBAU", "BUILD-UP"),
          "ev_gap": ("STILLE", "SILENCE"), "ev_break": ("BREAK", "BREAK"), "ev_drop": ("DROP !", "DROP !"),
          "ev_laser": ("LASER AKTIV", "LASER ACTIVE"),
          "ev_blackout": ("BLACKOUT", "BLACKOUT"), "ev_sun": ("SONNENBRILLE", "BLINDER"), "ev_fog": ("NEBEL", "SMOKE"), "ev_blitz": ("BLITZ", "STROBE"), "ev_solo": ("SOLO", "SOLO"),
          "mode_scene": ("Szene:", "Scene:"), "mode_manual": ("MANUELL", "MANUAL"), "pilot_locked": ("Auto aktiv: zum Bedienen AUTO ausschalten", "Auto is on: turn AUTO off to operate"), "mode_blackout": ("BLACKOUT", "BLACKOUT"), "mode_allbright": ("ALLES HELL", "FULL BRIGHT"),
          "st_silence": ("Stille", "Silence"), "st_tier": ("Stufe", "Level"),
          "tier0": ("Chillen", "Chill"), "tier1": ("Groove", "Groove"), "tier2": ("Party", "Party"), "tier3": ("Vollgas", "Peak"), "st_meter3": ("3er", "3/4"),
          "key_major": ("Dur", "major"), "key_minor": ("Moll", "minor"),
          "mood:euphorisch": ("euphorisch", "euphoric"), "mood:intensiv": ("intensiv", "intense"),
          "mood:froh": ("froh", "happy"), "mood:ruhig": ("ruhig", "calm"),
          "dim": ("General Dimmer", "General Dimmer"), "bpm_manual": ("manuell", "manual"),
          "sr_label": ("Live", "Live"), "sr_wait": ("wartet auf Musik", "waiting for music"), "sr_search": ("suche ...", "searching ..."),
          "sr_nomatch": ("nicht erkannt", "not recognized"), "sr_offline": ("kein Internet", "no internet"),
          "sr_missing": ("SongRec nicht gefunden", "SongRec not found"), "sr_error": ("Fehler bei der Erkennung", "Recognition error"),
          "mx_off": ("nicht aktiv", "not active"), "mx_noconn": ("nicht verbunden", "not connected"),
          "mx_nodeck": ("kein Deck hörbar", "no deck audible"), "mx_deck": ("Deck", "Deck"),
          "mx_unknown": ("Lied nicht erkannt oder noch nicht analysiert", "Track not recognized or not analyzed yet"),
          "mx_mismatch": ("Plan passt nicht zum geladenen Lied", "Plan does not match the loaded track"),
          "mx_plan": ("Plan aktiv", "Plan active"), "mx_noevent": ("kein Ereignis", "no event"),
          "st_weihnachten": ("Weihnachten", "Christmas"), "st_club": ("Club", "Club"),
          "st_party": ("Party", "Party"), "st_rock": ("Rock", "Rock"), "st_ruhig": ("Ruhig", "Calm"),
          "st_aus": ("kein Stil", "no style"), "st_def": ("Standard", "Default"),
          "gs_title": ("Genre-Stile", "Genre styles"),
          "gs_desc": ("Welcher Stil zu welchem Genre aus Mixxx gehört. Standard = feste Zuordnung (siehe Handbuch), kein Stil = Licht wie bisher. Eigene Zuordnungen sind orange und gelten sofort. Die Liste der Genres kommt vom Musik-Rechner.",
                      "Which style belongs to which genre from Mixxx. Default = built-in mapping (see manual), no style = light as before. Your own choices are orange and apply immediately. The list of genres comes from the music computer."),
          "mx_drop": ("Drop", "Drop"), "mx_build": ("Aufbau", "Build-up"), "mx_gap": ("Stille", "Silence"),
          "w_allok": ("Alle Geräte erreichbar", "All devices reachable"), "w_restart": ("NEUSTART OFFEN", "RESTART PENDING"), "w_dmx": ("DMX AUS", "DMX OFF"), "w_artin": ("ART-NET EXTERN", "ART-NET EXTERNAL"), "w_show": ("SHOW LÄUFT", "SHOW RUNNING"), "w_dmxdebug": ("DMX-DEBUG AN", "DMX DEBUG ON"), "h_dmxdebug": ("DMX-Debugger", "DMX debugger"), "mode_show": ("SHOW", "SHOW"), "sm_locked": ("Show aktiv: Zum Bedienen die Show beenden (Knopf SHOW)", "Show is running: end it to operate (button SHOW)"), "h_showman": ("Showmanager", "Show manager"), "w_wled": ("WLED AUS", "WLED OFF"),
          "w_nano": ("NANOLEAF AUS", "NANOLEAF OFF")}
# weitere Texte auf der Hauptseite und in den Menues Tempo und Verbindungen
PAGE = {"connecting": ("Verbinde ...", "Connecting ..."), "edit": ("✎ Bearbeiten", "✎ Edit"), "done": ("Fertig", "Done"),
        "save": ("Speichern", "Save"), "auto_btn": ("Erkannt", "Detected"), "off": ("Aus", "Off"), "on": ("An", "On"), "not_have": ("Nicht vorhanden", "Not present"),
        "sc_reset": ("Szenen auf Standard zurücksetzen", "Reset scenes to default"),
        "sc_reset_q": ("Alle Szenen auf die Standard-Szenen zurücksetzen? Eigene Szenen und Änderungen gehen verloren.",
                       "Reset all scenes to the default scenes? Your own scenes and changes will be lost."),
        "set_all": ("Alle auf Standard", "All to default"),
        "set_all_q": ("Alle Einstellungen auf Standard zurücksetzen?", "Reset all settings to default?"),
        "set_note": ("Änderungen wirken sofort und bleiben gespeichert.", "Changes take effect immediately and are saved."),
        "fx_export": ("⬇ Export (YAML)", "⬇ Export (YAML)"),
        "pw_devs": ("Noch eingeschaltet:", "Still on:"), "pw_dev_off": ("ausschalten", "off"),
        "pw_cancel": ("Abbrechen", "Cancel"), "pw_go": ("Herunterfahren", "Shut down"),
        "pw_go_quit": ("Beenden", "Quit"),
        "pw_q_quit": ("Den Light-Butler jetzt beenden? Das Licht geht sofort aus, der Rechner bleibt an.",
                      "Quit the Light-Butler now? The lights go off immediately, the computer stays on."),
        "pw_done_quit": ("Der Light-Butler ist beendet. Neu starten: über das Light-Butler-Symbol (Desktop, Startmenü oder Programme).",
                         "The Light-Butler has quit. To start it again use the Light-Butler icon (desktop, Start menu or Applications)."),
        "pw_q": ("Den Pi jetzt herunterfahren? Das Licht geht sofort aus. Danach kannst du den Strom trennen.",
                 "Shut down the Pi now? The lights go off immediately. Afterwards you can unplug the power."),
        "pw_done": ("Der Pi fährt herunter. Warte etwa 30 Sekunden, bis die grüne LED am Pi nicht mehr blinkt, dann kannst du den Strom trennen. Zum Einschalten den Strom wieder anstecken.",
                    "The Pi is shutting down. Wait about 30 seconds until the green LED on the Pi stops blinking, then you can unplug the power. To start it again, plug the power back in."),
        "home_na": ("Die HomeMatic-Anbindung läuft nur im echten Betrieb am Licht-Rechner.", "The HomeMatic connection only runs in live operation on the lighting computer."),
        "home_unreach": ("nicht erreichbar", "unreachable"),
        "home_auto_h": ("Automatik Wohnzimmerlicht", "Automatic living room light"),
        "home_set_h": ("Einstellungen: CCU und Kanäle", "Settings: CCU and channels"),
        "home_host": ("Adresse der CCU", "CCU address"), "home_save": ("Speichern", "Save"),
        "home_chan": ("Kanäle im Panel (Name antippen zum Ändern)", "Channels in the panel (tap a name to change it)"),
        "home_del": ("Entfernen", "Remove"), "home_del_q": ("Diesen Kanal aus dem Panel entfernen?", "Remove this channel from the panel?"),
        "home_scan": ("Kanäle von der CCU holen", "Get channels from the CCU"), "home_scanning": ("Liste wird geholt …", "Fetching list …"),
        "home_add": ("+ Hinzufügen", "+ Add"), "home_have": ("schon da", "added"), "home_none": ("Keine passenden Kanäle gefunden.", "No suitable channels found."),
        "home_switch": ("Steckdose", "Switch"), "home_dimmer": ("Dimmer", "Dimmer"),
        "f_mv_fan": ("Fan", "Fan"), "f_mv_speed": ("Speed", "Speed"), "f_mv_shift": ("Shift", "Shift"), "f_mv_size": ("Size", "Size"),
        "eb_auto": ("Auto", "Auto"),
        "eb_hint": ("Preset antippen = Effektband zeigt es (auch in der Stille, gedimmt). Nochmal tippen = wieder automatisch. Grün umrandet = läuft gerade, AUTO = von der Szenen-Automatik gewählt. ♫ = reagiert auf Musik (Mikrofon des Effektbands).",
                    "Tap a preset = the strip shows it (also during silence, dimmed). Tap again or Auto = automatic again. Green outline = running now, AUTO = chosen by the scene automation. ♫ = reacts to the music (the strip's microphone)."),
        "beam_auto": ("Von Hand", "Manual"), "beam_gobo": ("Gobo", "Gobo"), "beam_open": ("Offen", "Open"),
        "beam_zoom": ("Zoom", "Zoom"), "beam_roll": ("Roll", "Roll"), "beam_prism": ("Prisma", "Prism"),
        "f_mx_fade": ("Fade", "Fade"), "f_mx_speed": ("Speed", "Speed"), "f_mx_shift": ("Shift", "Shift"), "f_mx_size": ("Size", "Size"),
        "ha_home_auto": ("Automatik", "Automatic"), "ha_home_idle_s": ("Licht an nach Stille von", "Light on after silence of"),
        "ha_home_idle_level": ("Helligkeit bei Stille", "Brightness during silence"),
        "ha_home_party_min": ("Licht an nur nach Musik von", "Light on only after music for"),
        "ha_home_ramp_s": ("Dimmzeit (langsam ein und aus)", "Dimming time (slow on and off)"),
        "ha_home_music_s": ("Licht aus nach Musik von", "Light off after music for"),
        "aim_new": ("+ Ziel", "+ Target"), "aim_new_q": ("Name des neuen Ziels:", "Name of the new target:"),
        "aim_name": ("Name", "Name"), "aim_rename": ("Namen speichern", "Save name"), "aim_del": ("Ziel löschen", "Delete target"),
        "aim_del_q": ("Dieses Ziel löschen?", "Delete this target?"), "aim_all": ("Alle", "All"),
        "aim_edit_hint": ("Ziel antippen zum Bearbeiten. Die Position stellst du mit den Reglern darunter ein und tippst dann auf Speichern.",
                          "Tap a target to edit it. Set its position with the sliders below, then tap Save."),
        "aim_fixed_hint": ("Festes Ziel: lässt sich umbenennen, aber nicht löschen (Szenen und APC mini nutzen es). Leerer Name = Standardname.",
                           "Built-in target: can be renamed but not deleted (scenes and the APC mini use it). Empty name = default name."),
        "aim_title": ("Position einstellen:", "Set position:"), "aim_vu": ("Moving Head links ↔ rechts", "Moving head left ↔ right"),
        "aim_vv": ("Moving Head oben ↔ unten", "Moving head up ↔ down"), "aim_bar": ("Spider wählen:", "Select spider:"),
        "aim_t1": ("Spider Tilt 1", "Spider tilt 1"), "aim_t2": ("Spider Tilt 2", "Spider tilt 2"),
        "tempo_auto": ("Automatisch:", "Automatic:"), "tempo_manual": ("Manuell:", "Manual:"),
        "tempo_detected": ("erkannt", "detected"), "tempo_fixed": ("BPM fest", "BPM fixed"),
        "tempo_hint": ("Von Hand gestelltes Tempo wirkt auf Szenen und WOW!, nicht auf AUTO. TAP: 4- bis 8-mal im Takt tippen. Außerhalb tippen schließt.",
                       "A manually set tempo affects scenes and WOW!, not AUTO. TAP: tap 4 to 8 times in time. Tap outside to close."),
        "tp_title": ("Tempo", "Tempo"), "tap_btn": ("TAP im Takt", "TAP in time"),
        "sys_of": ("von", "of"), "sys_reach": ("erreichbar", "reachable"), "sys_missing": ("fehlt", "missing"),
        "sys_dmx_off": ("DMX aus", "DMX off"), "sys_wled_off": ("WLED aus", "WLED off"), "sys_nano_off": ("Nanoleaf aus", "Nanoleaf off"),
        "sys_ola": ("DMX-Ausgabe", "DMX output"),
        "sys_music": ("Musikordner am Musik-Rechner (zum Beispiel USB-Stick)", "Music folder on the music computer (for example a USB stick)"),
        "sys_music_hint": ("(für Vorhören und „+ Show“ in der Musik-Datenbank; die Mixxx-Brücke holt ihn sich alle 30 s)",
                           "(for preview and \u201e+ Show\u201c in the music library; the Mixxx bridge picks it up every 30 s)"),
        "sys_excl": ("Ausgeschlossene Ordner", "Excluded folders"),
        "sys_eject": ("⏏ Stick auswerfen", "⏏ Eject stick"),
        "sys_nas": ("NAS (für „Spiegeln“)", "NAS (for mirroring)"),
        "sys_excl_hint": ("(je Zeile ein Ordner im Musikordner, etwa APRES SKI: der Light-Butler liest ihn nicht ein und ändert nichts darin; Mixxx sieht ihn trotzdem)",
                          "(one folder inside the music folder per line, e.g. APRES SKI: the Light-Butler never reads or changes it; Mixxx still sees it)"),
        "sys_via": ("DMX-Weg", "DMX route"),
        "sys_artin": ("Art-Net-Eingang", "Art-Net input"),
        "sys_dmxmon": ("DMX-Monitor", "DMX monitor"),
        "sys_artin_hint": ("(für ein anderes Lichtprogramm; Laser, Nebel und ohne Erlaubnis Strobe bleiben gesperrt)",
                           "(for another lighting program; lasers, fog and, without permission, strobe stay locked)"),
        "artin_rx": ("empfängt von", "receiving from"), "artin_wait": ("wartet auf Daten (UDP 6454)", "waiting for data (UDP 6454)"),
        "sys_via_hint": ("(USB = FTDI-Adapter direkt an diesem Licht-Rechner, ohne Art-Net-Gateway)", "(USB = FTDI adapter plugged straight into this lighting computer, no Art-Net gateway)"),
        "via_ola": ("Art-Net-Gateway", "Art-Net gateway"), "via_usb": ("USB-Adapter", "USB adapter"),
        "usb_ch": ("Kanäle", "channels"),
        "usb_e_wait": ("Adapter wird gesucht …", "looking for the adapter …"),
        "usb_e_dry": ("Trockenlauf, kein Adapter", "dry run, no adapter"),
        "usb_e_nomod": ("Paket pyserial fehlt am Licht-Rechner", "package pyserial missing on the lighting computer"),
        "usb_e_notfound": ("Kein FTDI-Adapter gefunden", "no FTDI adapter found"),
        "usb_e_open": ("Adapter lässt sich nicht öffnen", "cannot open the adapter"),
        "usb_e_write": ("Verbindung zum Adapter abgebrochen", "connection to the adapter lost"),
        "sys_ola_hint": ("(aus = andere Art-Net-Sender können ihn nutzen)", "(off = other Art-Net senders can use it)"),
        "sys_wled": ("Ausgabe an die WLED-Lichter", "Output to the WLED lights"),
        "sys_wled_hint": ("(Effektband, Theke, Couchtisch; aus = sie sind frei für die WLED-App)", "(effect strip, bar, coffee table; off = free for the WLED app)"),
        "sys_nano": ("Ausgabe an die Nanoleaf-Panels", "Output to the Nanoleaf panels"),
        "sys_nano_hint": ("(aus = Panels gehen zurück auf ihren Effekt und sind frei für die Nanoleaf-App)", "(off = panels return to their effect and are free for the Nanoleaf app)"),
        "sys_link": ("Ableton Link", "Ableton Link"),
        "sys_link_hint": ("(Tempo per LAN und WLAN an Link-Geräte, bei Stille 20 BPM)", "(tempo via LAN and Wi-Fi to Link devices, 20 BPM in silence)"),
        "link_na": ("nicht verfügbar:", "not available:"), "link_sends": ("sendet", "sends"), "link_to": ("an", "to"),
        "link_dev1": ("Gerät", "device"), "link_devn": ("Geräte", "devices")}
# Einstellungsgruppen (Namen wie in settings.py) -> (Deutsch, English)
GROUPS = {"Nebel": ("Nebel", "Fog"), "Pixel-Matrix": ("Pixel-Matrix", "Pixel matrix"), "Moving-Head-Strahl": ("Moving-Head-Strahl", "Moving head beam"), "Szenen-Automatik": ("Szenen-Automatik", "Scene automation"), "Eingang und Stille": ("Eingang und Stille", "Input and silence"), "Kick und Beat": ("Kick und Beat", "Kick and beat"),
          "Stimmung: Energie": ("Stimmung: Energie", "Mood: energy"),
          "Stimmung: Farbe und Tonart": ("Stimmung: Farbe und Tonart", "Mood: color and key"),
          "Phasen: Break, Build, Drop": ("Phasen: Break, Build, Drop", "Phases: break, build, drop"),
          "Intensitaetsstufen": ("Intensitätsstufen", "Intensity levels"),
          "Weisse Blitze und Strobo": ("Weiße Blitze und Strobo", "White flashes and strobe"),
          "Ambiente": ("Ambiente", "Ambience"), "Takt": ("Takt", "Meter"), "Mixxx-Vorhersage": ("Mixxx-Vorhersage", "Mixxx prediction"),
          "Laser": ("Laser", "Laser"), "Ausgabe": ("Ausgabe", "Output"), "Panel": ("Panel", "Panel"), "Haus": ("Haus", "Home"),
          "Titelerkennung": ("Titelerkennung", "Track recognition")}

MAX_LEN = 300                                  # laengster erlaubter Text (der Farb-Hinweis ist der laengste)


def catalog():
    """Alle Texte: [(Schluessel, Bereich in der Tabelle, Deutsch, English)] in der Reihenfolge der Tabelle."""
    out = [(k, "Statuszeilen oben", de, en) for k, (de, en) in STATUS.items()]
    out += [(k, "Knöpfe oben", de, en) for k, (de, en) in TOP.items()]
    for prefix, cat, items in (("speed", "Geschwindigkeit", SPEEDS), ("mix", "Licht-Mix", MIX_PANEL),
                               ("move", "Bewegung", MOVES), ("color", "Farbe", COLORS), ("aim", "Ziel", AIMS),
                               ("style", "Stil", STYLE_BTNS)):
        out += [(f"{prefix}:{k}", cat, de, en) for k, de, en in items]
    out += [(k, "Überschriften und Hinweise", de, en) for k, (de, en) in HEADS.items()]
    out += [(k, "Menüs", de, en) for k, (de, en) in MENUS.items()]
    out += [(k, "Weitere Texte (Szenen, Einstellungen, Tempo, Verbindungen)", de, en) for k, (de, en) in PAGE.items()]
    try:
        import settings
        names = list(dict.fromkeys(p.group for p in settings.DEFS))
    except Exception:                                  # noqa: BLE001
        names = list(GROUPS)
    out += [(f"grp:{g}", "Einstellungs-Gruppen", *GROUPS.get(g, (g, g))) for g in names]
    return out


class TextStore:
    """Eigene Texte (texts.json). path=None: nur im Speicher (Tests)."""

    def __init__(self, path="texts.json"):
        self.path, self.lock, self.rev = path, threading.Lock(), 0
        self.defaults = {k: (de, en) for k, _, de, en in catalog()}
        self.own = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                for k, v in (d.items() if isinstance(d, dict) else ()):
                    k = {"mix:KITT": "mix:Scanner"}.get(k, k)          # bis 15.11.2026 hiess der Scanner so
                    if k in self.defaults and isinstance(v, dict):
                        self.own[k] = {lang: str(v[lang])[:MAX_LEN] for lang in ("de", "en") if isinstance(v.get(lang), str)}
            except (OSError, ValueError) as e:
                print(f"Hinweis: {os.path.basename(path)} nicht lesbar ({e}), es gelten die Standardtexte")

    def merged(self):
        """{Schluessel: [Deutsch, English]} mit den eigenen Texten."""
        with self.lock:
            return {k: [self.own.get(k, {}).get("de", de), self.own.get(k, {}).get("en", en)]
                    for k, (de, en) in self.defaults.items()}

    def table(self):
        """Fuer die Uebersetzungstabelle im Panel."""
        m = self.merged()
        return [{"key": k, "cat": cat, "de0": de, "en0": en, "de": m[k][0], "en": m[k][1]} for k, cat, de, en in catalog()]

    def set(self, key, de=None, en=None):
        if key not in self.defaults:
            raise ValueError("Unbekannter Text")
        new = {}
        for lang, val, std in (("de", de, self.defaults[key][0]), ("en", en, self.defaults[key][1])):
            if val is None:
                val = self.own.get(key, {}).get(lang, std)
            val = " ".join(str(val).split())             # keine Steuerzeichen oder Zeilenumbrueche (dafuer |)
            if not val:
                raise ValueError("Der Text darf nicht leer sein (zum Zuruecksetzen den Pfeil benutzen)")
            if len(val) > MAX_LEN:
                raise ValueError(f"Der Text darf hoechstens {MAX_LEN} Zeichen lang sein")
            if val != std:
                new[lang] = val
        with self.lock:
            if new:
                self.own[key] = new
            else:
                self.own.pop(key, None)
        self._save()

    def reset(self, key=None):
        """Einen Text (oder mit key=None alle) auf den Standard zuruecksetzen."""
        with self.lock:
            if key is None:
                self.own = {}
            elif key in self.defaults:
                self.own.pop(key, None)
            else:
                raise ValueError("Unbekannter Text")
        self._save()

    def _save(self):
        self.rev += 1
        if not self.path:
            return
        with self.lock:
            data = dict(self.own)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.path)
