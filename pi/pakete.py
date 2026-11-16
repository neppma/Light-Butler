"""
pakete.py - Software fuer andere Rechner zum Herunterladen (Wunsch von Markus, 07.11.2026): ein neuer Mac (oder ein neuer
Benutzer) holt sich beim Light-Butler unter Einstellungen das Paket mit Mixxx-Bruecke, Helfer und Installationsskript, ein
Windows-PC das Paket fuer die Pegelkurven. Die ZIP-Dateien entstehen bei jedem Abruf neu aus den Dateien, die deploy.sh nach
~/lichtshow/pakete/mac kopiert (am Mac in der Entwicklung: der Ordner mac/ des Projekts). Nur lesen, nichts wird gespeichert.
"""
import hashlib
import io
import os
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MAC_DIRS = (os.path.join(HERE, "pakete", "mac"), os.path.join(os.path.dirname(HERE), "mac"))
WIN_DIRS = (os.path.join(HERE, "helfer"), os.path.join(os.path.dirname(HERE), "mac", "stems"))
# Light-Butler.exe (15.11.2026): fertiges ZIP vom Windows-PC; am Pi in pakete/windows (deploy.sh push), am Mac in windows/build
EXE_NAME = "light-butler-windows-exe.zip"
EXE_FILES = (os.path.join(HERE, "pakete", "windows", EXE_NAME), os.path.join(os.path.dirname(HERE), "windows", "build", EXE_NAME))


def exe_zip_path(files=EXE_FILES):
    """Pfad des abgelegten EXE-ZIP oder None (noch keins da). Nur ein echtes ZIP zaehlt."""
    for p in files:
        try:
            with open(p, "rb") as f:
                if f.read(4) == b"PK\x03\x04":
                    return p
        except OSError:
            continue
    return None
MAC_PARTS = ("mixxx_bridge", "helper", "stems")        # Unterordner wie im Projekt (die Installer finden sich darueber)
SKIP_DIRS = {"__pycache__", "analysis", "autotag", "doppelte", "energie", "tonart", "ordner", ".git"}
SKIP_EXT = (".pyc", ".tmp", ".DS_Store", ".log", ".sqlite")
WIN_FILES = ("stems_show.py", "stem_curves.py", "install_stems.ps1")

LIESMICH_MAC = """LIGHT-BUTLER FUER DEN MAC
=========================

Inhalt: Mixxx-Bruecke (App "Light-Butler Mixxx"), Light-Butler Helfer (APC, Ton, Liedliste ohne Mixxx),
Pegelkurven fuer den Showmanager, und das Installationsskript.

Einrichten:
  1. Diesen Ordner entpacken (Doppelklick auf die ZIP-Datei im Finder).
  2. Programm "Terminal" oeffnen, "cd " tippen (mit Leerzeichen), den entpackten Ordner ins Fenster ziehen, Enter.
  3. Eintippen:   bash install_mac.sh    und Enter.
Das Skript richtet Python und alle Pakete ein, fragt nach der Adresse des Light-Butler (Standard
lightbutler.local), legt beide Apps an und bietet Zusaetze an (ffmpeg, essentia, Pegelkurven). Am Ende steht,
was noch von Hand zu tun ist (Mixxx, IAC-Treiber, Mapping, BlackHole).

Spaeter aktualisieren: neues Paket vom Light-Butler holen und install_mac.sh noch einmal ausfuehren. Einstellungen,
Analysen und Vorschlaege in ~/Light-Butler-Daten bleiben erhalten.
"""

LIESMICH_WIN = """LIGHT-BUTLER: PEGELKURVEN AM WINDOWS-PC
=======================================

Rechnet die Pegelkurven (Gesang, Schlagzeug, Bass, Rest) fuer den Showmanager, mit einer NVIDIA-Grafikkarte viel
schneller als am Mac. Mac und PC teilen sich die Arbeit, keiner rechnet ein Lied doppelt.

Einrichten:
  1. Diesen Ordner entpacken (Rechtsklick auf die ZIP-Datei -> Alle extrahieren).
  2. Im entpackten Ordner: Shift + Rechtsklick in eine leere Stelle -> "In Terminal oeffnen" (oder PowerShell).
  3. Eintippen:   powershell -ExecutionPolicy Bypass -File install_stems.ps1    und Enter.
Braucht Python 3.9 bis 3.12 (python.org, beim Installieren "Add python.exe to PATH" anhaken). Das Skript legt
%USERPROFILE%\\s2l-stems an (rund 5 GB mit Torch fuer CUDA) und eine Aufgabe, die beim Anmelden ohne Fenster startet.
Meldungen: %LOCALAPPDATA%\\Light-Butler\\stems.log. Entfernen: dasselbe Skript mit -Entfernen.
"""


def _first_dir(dirs, probe):
    for d in dirs:
        if os.path.exists(os.path.join(d, probe)):
            return d
    return None


def _add(z, path, arc):
    info = zipfile.ZipInfo(arc, date_time=time.localtime(os.path.getmtime(path))[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if arc.endswith((".sh", ".command")) else 0o644   # Skripte ausfuehrbar
    info.external_attr = (0o100000 | mode) << 16
    with open(path, "rb") as f:
        z.writestr(info, f.read())


COPYRIGHT = """

LIZENZ: Light-Butler ist freie Software unter der GNU General Public License Version 3 (Datei LICENSE), ohne jede
Gewaehrleistung. Copyright (C) 2026 Markus Nepp, Kontakt: lightbutler@gmx.at
Quelltext: https://github.com/neppma/Light-Butler
Idee, Konzept, Gestaltung und Tests an der echten Anlage: Markus Nepp. Programmiert mit Unterstuetzung von KI
(Claude von Anthropic).
SICHERHEIT: Strobe kann Anfaelle ausloesen, Laser nie ins Publikum, Nebel loest Rauchmelder aus. Alles Gefaehrliche ist
bei einer neuen Anlage aus; beim ersten Oeffnen des Panels erscheint ein Sicherheitshinweis.
"""
LICENSE_FILES = (os.path.join(HERE, "LICENSE"), os.path.join(os.path.dirname(HERE), "LICENSE"))


def _license(z, prefix):
    """Lizenztext (GPLv3) oben in jedes Paket."""
    p = next((p for p in LICENSE_FILES if os.path.isfile(p)), None)
    if p:
        _add(z, p, prefix + "LICENSE")


def mac_zip(dirs=MAC_DIRS):
    """ZIP fuer den Mac: Light-Butler-Mac/{install_mac.sh, LIESMICH.txt, mixxx_bridge/, helper/, stems/}. None = Dateien fehlen."""
    base = _first_dir(dirs, "install_mac.sh")
    if base is None:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        _add(z, os.path.join(base, "install_mac.sh"), "Light-Butler-Mac/install_mac.sh")
        z.writestr("Light-Butler-Mac/LIESMICH.txt", LIESMICH_MAC)
        _license(z, "Light-Butler-Mac/")
        for part in MAC_PARTS:
            top = os.path.join(base, part)
            for root, subdirs, files in os.walk(top):
                subdirs[:] = sorted(d for d in subdirs if d not in SKIP_DIRS and not d.startswith("."))
                for name in sorted(files):
                    if name.endswith(SKIP_EXT) or name.startswith("."):
                        continue
                    p = os.path.join(root, name)
                    _add(z, p, "Light-Butler-Mac/" + os.path.relpath(p, base).replace(os.sep, "/"))
    return buf.getvalue()


def win_zip(dirs=WIN_DIRS):
    """ZIP fuer Windows: Light-Butler-Windows/{install_stems.ps1, stems_show.py, stem_curves.py, LIESMICH.txt}."""
    buf = io.BytesIO()
    found = 0
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Light-Butler-Windows/LIESMICH.txt", LIESMICH_WIN.replace("\n", "\r\n"))   # Windows-Zeilenenden
        _license(z, "Light-Butler-Windows/")
        for name in WIN_FILES:
            d = _first_dir(dirs, name)
            if d is not None:
                _add(z, os.path.join(d, name), "Light-Butler-Windows/" + name)
                found += 1
    return buf.getvalue() if found == len(WIN_FILES) else None


# ---- Pi: frische Installation (Wunsch von Markus, 12.11.2026) ----
# Ein neuer Raspberry Pi (Freund, Ersatzgeraet) bekommt alle Programme, Seiten und das Handbuch, aber keine Zustandsdateien
# (Einstellungen, Szenen, Shows, Token, Schluessel, Raumplan ...). Das ZIP entsteht bei jedem Abruf neu aus den Dateien, die
# gerade am Pi laufen: nach jedem Einspielen ist die neue Fassung dabei. own=False: neutrale Geraetedatei (alle Geraetetypen,
# keine Geraete, keine Adressen) und keine HomeMatic-Datei. own=True (Ersatzgeraet): die eigene fixtures.yaml und homematic.yaml.
PI_SKIP_DIRS = {"__pycache__", "shows", "aufnahmen", "songrec_tmp", "backups", ".git"}
PI_SKIP_FILES = {"show.conf", "backup.conf", "fixtures.yaml", "homematic.yaml", "MEINE_ANLAGE.md"}   # MEINE_ANLAGE: nur eigene Anlage
PI_SKIP_EXT = (".json", ".pyc", ".tmp", ".bak", ".log", ".zip", ".wav", ".neu", ".alt", ".sqlite", ".DS_Store")
PI_SHOW_CONF = """# Startoptionen fuer den Dienst "lichtshow" (eine Zeile, ohne Anfuehrungszeichen).
# --device NAME     Audiokarte per Namensteil, zum Beispiel --device USB (ohne: Standard-Eingang)
# --strobe          Strobe-Erlaubnis beim Start (weglassen = kein Strobo; im Panel einschaltbar)
# --web 8080        Web-Panel fuer iPad/Handy (http://<IP>:8080/)
# Weitere Optionen: ~/venv/bin/python show.py --help. Danach: sudo systemctl restart lichtshow
SHOW_ARGS=--master 1.0 --web 8080
"""
LIESMICH_PI = """LIGHT-BUTLER FUER EINEN NEUEN RASPBERRY PI
==========================================

Fuer Raspberry Pi 3, 4 oder 5 mit Raspberry Pi OS (64 Bit). Alle Programme und das Handbuch, ohne persoenliche Daten
(keine Einstellungen, Szenen, Shows, Schluessel).%s

1. SD-Karte vorbereiten (am Mac oder PC): "Raspberry Pi Imager" -> Raspberry Pi OS (64-bit). Unter "Einstellungen
   bearbeiten": Hostname (zum Beispiel lightbutler2), Benutzer admin mit Passwort, WLAN, SSH einschalten.
2. Pi starten, dieses ZIP auf den Pi kopieren (Terminal am Mac):
       scp light-butler-pi.zip admin@lightbutler2.local:
3. Am Pi (ssh admin@lightbutler2.local):
       unzip light-butler-pi.zip && cd Light-Butler-Pi && bash install_pi.sh
   Fragt einmal nach dem Passwort. Dauert beim ersten Mal 5 bis 15 Minuten.
4. Panel im Browser: http://lightbutler2.local:8080/

WICHTIG: Ein neuer Light-Butler startet mit allen Ausgaben AUS (DMX, WLED, Nanoleaf). Senden zwei Light-Butler im
selben Netz gleichzeitig, kaempfen sie ums Licht. Einschalten im Panel unter Einstellungen -> Ausgabe, wenn nur dieser
sendet. Strobe, Laser und Nebel sind wie bei jeder neuen Anlage aus.

Ersatzgeraet mit den eigenen Einstellungen: im Panel des Haupt-Pi "Juengste Sicherung des Pi" laden, auf den neuen Pi
kopieren und dort einspielen:
       cd ~/lichtshow && ~/venv/bin/python backup.py --restore ~/lichtshow-backup-....zip --only data --ausgaben-aus
       sudo systemctl restart lichtshow
--only data nimmt nur Einstellungen, Szenen, Geraete und Shows (die Programme bleiben die neuen), --ausgaben-aus laesst
die Ausgaben aus. Nanoleaf und den Schluessel des Show-Assistenten neu eintragen (sie sind nicht in der Sicherung).
Am Mac sagt   ./deploy.sh rename lightbutler2   (oder ~/.light-butler-pi), an welchen Pi Ton und Mixxx gehen.

Aktualisieren: neues ZIP vom Light-Butler holen und install_pi.sh noch einmal ausfuehren. Einstellungen, Szenen,
Shows, Geraete und show.conf bleiben, nur die Programme werden erneuert.
"""


def neutral_fixtures(text, restart="sudo systemctl restart lichtshow"):
    """fixtures.yaml ohne die eigene Anlage: alle Geraetetypen bleiben (zum Anlegen im Fixture-Editor), Geraete, Ziele und
    Adressen fallen weg. restart: wie man den Light-Butler danach neu startet (Pi: Dienst, Windows: Aufgabe)."""
    import re
    i = text.find("\nfixtures:")
    head = text[:i] if i >= 0 else text
    head = re.sub(r"\naim_targets:.*", "", head, flags=re.S) if "\naim_targets:" in head else head
    head = re.sub(r"(?m)^artnet_target:.*$", "artnet_target: 127.0.0.1        # IP deines Art-Net-Knotens (zum Beispiel OLA-Pi) eintragen", head)
    head = re.sub(r"(?m)^#.*\n", "", head, count=0) if head.startswith("#") else head
    return ("# fixtures.yaml - neue Anlage aus dem Light-Butler-Paket. Geraete im Panel anlegen (Einstellungen -> Fixtures),\n"
            "# die Geraetetypen unten stehen zur Auswahl. Die Ziel-IP oben anpassen, dann %s.\n" % restart
            + head.lstrip("\n").rstrip() + "\n\naim_targets: {}\n\nfixtures: []\n")


def _pi_docs(base):
    """Handbuecher und Technische Beschreibung: am Pi neben den Programmen, in der Entwicklung in docs/."""
    out = {}
    for n in ("HANDBUCH.md", "MANUAL_EN.md", "TECHNIK.md", "TECHNICAL_EN.md"):
        for d in (base, os.path.join(os.path.dirname(base), "docs")):
            if os.path.isfile(os.path.join(d, n)):
                out[n] = os.path.join(d, n)
                break
    return out


def _add_programs(z, base, prefix):
    """Alle Programme, Seiten und Handbuecher, ohne Zustandsdateien (gemeinsam fuer Pi- und Windows-Paket)."""
    for root, subdirs, files in os.walk(base):
        rel_root = os.path.relpath(root, base)
        subdirs[:] = sorted(d for d in subdirs if d not in PI_SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if name.startswith(".") or name.endswith(PI_SKIP_EXT) or (rel_root == "." and name in PI_SKIP_FILES):
                continue
            p = os.path.join(root, name)
            _add(z, p, prefix + os.path.relpath(p, base).replace(os.sep, "/"))
    for n, p in _pi_docs(base).items():
        if not os.path.isfile(os.path.join(base, n)):
            _add(z, p, prefix + n)


def pi_zip(base=HERE, own=False):
    """ZIP fuer einen neuen Pi: Light-Butler-Pi/{install_pi.sh, LIESMICH.txt, lichtshow/...}. None = Dateien fehlen."""
    if not os.path.isfile(os.path.join(base, "install_pi.sh")) or not os.path.isfile(os.path.join(base, "show.py")):
        return None
    buf = io.BytesIO()
    top = "Light-Butler-Pi/"
    with zipfile.ZipFile(buf, "w") as z:
        _add(z, os.path.join(base, "install_pi.sh"), top + "install_pi.sh")
        z.writestr(top + "LIESMICH.txt", LIESMICH_PI % ("\nDieses Paket ist ein ERSATZGERAET: es enthaelt die eigenen Geraete "
                                                        "(fixtures.yaml, homematic.yaml) mit ihren Adressen." if own else ""))
        _license(z, top)
        _add_programs(z, base, top + "lichtshow/")
        z.writestr(top + "lichtshow/show.conf", PI_SHOW_CONF)
        fx = os.path.join(base, "fixtures.yaml")
        with open(fx, encoding="utf-8") as f:
            text = f.read()
        z.writestr(top + "lichtshow/fixtures.yaml", text if own else neutral_fixtures(text))
        if own and os.path.isfile(os.path.join(base, "homematic.yaml")):
            _add(z, os.path.join(base, "homematic.yaml"), top + "lichtshow/homematic.yaml")
    return buf.getvalue()


# ---- Windows: frische Installation (Wunsch von Markus, 15.11.2026) ----
# Wie das Pi-Paket (dieselben Programme, keine Zustandsdateien, neutrale Geraete), dazu install_windows.ps1. Der PC startet
# mit allen Ausgaben AUS; Audio-Eingang, Geraete und Ausgaben stellt man im Panel ein.
WIN_SHOW_CONF = """# Startoptionen fuer den Light-Butler am Windows-PC (eine Zeile, ohne Anfuehrungszeichen).
# --device NAME     Audio-Eingang per Namensteil, zum Beispiel --device USB (ohne: im Panel waehlen, Einstellungen ->
#                   Verbindungen; "Musik-Rechner (Netzwerk)" = Ton vom Musik-Rechner)
# --strobe          Strobe-Erlaubnis beim Start (weglassen = kein Strobo; im Panel einschaltbar)
# --web 8080        Web-Panel fuer iPad/Handy (http://<Name-des-PC>:8080/)
# Danach neu starten: Aufgabenplanung -> Light-Butler -> Beenden und Ausfuehren (oder abmelden und anmelden).
SHOW_ARGS=--master 1.0 --web 8080
# HELFER=1          Musik-Teil des Helfers mitstarten (Musikordner, Musik-DB, Vorhoeren, Analyse, Datenpflege; Port 9025).
#                   HELFER=0, wenn ein Mac mit Mixxx-Bruecke oder Helfer diese Arbeit macht.
HELFER=1
"""
LIESMICH_WINFULL = """LIGHT-BUTLER FUER EINEN WINDOWS-PC
==================================

Die ganze Lichtsteuerung (Analyse, Szenen, Showmanager, Web-Panel) wie am Raspberry Pi, fuer Windows 10 oder 11.
Alle Programme und das Handbuch, ohne persoenliche Daten (keine Einstellungen, Szenen, Shows, Schluessel).

1. Python 3.12 von python.org installieren, beim Installieren "Add python.exe to PATH" anhaken.
2. Dieses ZIP entpacken (Rechtsklick -> Alle extrahieren).
3. Im entpackten Ordner: Shift + Rechtsklick in eine leere Stelle -> "In Terminal oeffnen" (oder PowerShell), eintippen:
       powershell -ExecutionPolicy Bypass -File install_windows.ps1
   Keine Administratorrechte noetig. Dauert beim ersten Mal ein paar Minuten.
4. Panel im Browser: http://localhost:8080/  (Handy/iPad im Heimnetz: http://<Name-des-PC>:8080/)

FIREWALL: Beim ersten Start fragt Windows evtl., ob Python im Netzwerk erreichbar sein darf. "Private Netzwerke"
zulassen (nicht "Oeffentliche"), sonst erreichen Handy, iPad und der Ton vom Mac den PC nicht. Das Panel hat keine
Anmeldung: nie ins Internet stellen.

WICHTIG: Ein neuer Light-Butler startet mit allen Ausgaben AUS (DMX, WLED, Nanoleaf). Senden zwei Light-Butler im
selben Netz gleichzeitig, kaempfen sie ums Licht. Einschalten im Panel unter Einstellungen -> Ausgabe, wenn nur dieser
sendet. Strobe, Laser und Nebel sind wie bei jeder neuen Anlage aus.

MUSIK: Der Musik-Teil des Helfers startet mit (HELFER=1 in show.conf): Musikordner einlesen (Einstellungen ->
Verbindungen -> Musikordner), Musik-Datenbank, Vorhoeren, Tempo/Tonart/Energie im Hintergrund, Datenpflege. Geloeschtes
kommt nie endgueltig weg, sondern in den Ordner "Light-Butler Papierkorb" oben auf dem jeweiligen Laufwerk. Fuer
MP3-Umwandlung, Reparatur und Shazam braucht es ffmpeg:  winget install Gyan.FFmpeg
Meldungen des Helfers: %LOCALAPPDATA%\\Light-Butler\\helfer.log. Arbeitet ein Mac mit Mixxx-Bruecke: HELFER=0.

MIXXX AM PC: Verknuepfung "Light-Butler Mixxx" (Startmenue/Desktop, wird angelegt, wenn Mixxx 2.5 in Programme liegt)
startet Mixxx mit der Mixxx-Bruecke (Tempo, Beat, Lied, Drops wie am Mac). Einmalig: loopMIDI installieren
(tobias-erichsen.de, kostenlos) und darin den Anschluss "Light-Butler" anlegen; in Mixxx Einstellungen -> Controller ->
Light-Butler aktivieren, Mapping "Light-Butler Bridge". Vor dem Start sichert sie die Mixxx-Datenbank (die letzten 5 in
%USERPROFILE%\\Light-Butler-Daten\\mixxx-sicherung). Meldungen: %LOCALAPPDATA%\\Light-Butler\\bridge.log, launcher.log.
Ton an einen anderen Licht-Rechner: VB-Cable, Stereomix oder Line-In (der Reihe nach gesucht).

Was unter Windows geht (geprueft 14./15.11.2026): Ton ueber USB-Audio oder vom Mac ueber das Netz, APC mini mk2 und
ROLI LUMI Keys per USB (ROLI Connect darf laufen), DMX ueber einen FTDI-USB-Adapter (Open DMX USB, erscheint als COM-Port)
oder Art-Net. Tempo und Takt mit aubio (wie am Pi), fehlt es, mit dem Ersatz tempo_np. Nicht unter Windows: Titelerkennung (SongRec), Zustand von
Temperatur/Spannung (nur am Pi), naechtliche Sicherung (Sicherung im Panel von Hand laden).

Startet beim Anmelden ohne Fenster (Aufgabe "Light-Butler" in der Aufgabenplanung). Meldungen:
%LOCALAPPDATA%\\Light-Butler\\show.log. Startoptionen: <Ziel>\\lichtshow\\show.conf.
Aktualisieren: neues ZIP holen und install_windows.ps1 noch einmal ausfuehren. Einstellungen, Szenen, Shows, Geraete
und show.conf bleiben, nur die Programme werden erneuert.
Entfernen: install_windows.ps1 -Entfernen (Aufgabe und Python-Umgebung; Daten bleiben in %USERPROFILE%\\Light-Butler).
"""


WIN_HELPER_PARTS = ("helper", "mixxx_bridge")           # Musik-Teil des Helfers (APC, Lumi, Ton haengen am PC direkt)


def _add_helper(z, prefix, dirs=MAC_DIRS):
    """Helfer-Programme wie im Projekt (helfer/helper/helper.py findet ../mixxx_bridge). Nur Programme, keine Daten.
    False, wenn sie fehlen (am Pi ohne ./deploy.sh push)."""
    mb = _first_dir(dirs, os.path.join("helper", "helper.py"))
    if mb is None:
        return False
    for part in WIN_HELPER_PARTS:
        for root, subdirs, files in os.walk(os.path.join(mb, part)):
            subdirs[:] = sorted(d for d in subdirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(files):
                if not name.endswith(SKIP_EXT) and not name.startswith("."):
                    p = os.path.join(root, name)
                    _add(z, p, prefix + os.path.relpath(p, mb).replace(os.sep, "/"))
    return True


def windows_zip(base=HERE, mac_dirs=MAC_DIRS):
    """ZIP fuer einen Windows-PC: Light-Butler-Windows-Voll/{install_windows.ps1, LIESMICH.txt, lichtshow/..., helfer/...}.
    None = Dateien fehlen. Immer neutrale Geraete (ein PC ist kein Ersatz-Pi). helfer/ nur, wenn die Mac-Dateien da sind."""
    if not os.path.isfile(os.path.join(base, "install_windows.ps1")) or not os.path.isfile(os.path.join(base, "show.py")):
        return None
    buf = io.BytesIO()
    top = "Light-Butler-Windows-Voll/"
    crlf = lambda s: s.replace("\r\n", "\n").replace("\n", "\r\n")       # noqa: E731  Windows-Zeilenenden fuer Editor
    with zipfile.ZipFile(buf, "w") as z:
        _add(z, os.path.join(base, "install_windows.ps1"), top + "install_windows.ps1")
        z.writestr(top + "LIESMICH.txt", crlf(LIESMICH_WINFULL))
        _license(z, top)
        _add_programs(z, base, top + "lichtshow/")
        z.writestr(top + "lichtshow/show.conf", crlf(WIN_SHOW_CONF))
        with open(os.path.join(base, "fixtures.yaml"), encoding="utf-8") as f:
            z.writestr(top + "lichtshow/fixtures.yaml",
                       neutral_fixtures(f.read(), "den Light-Butler neu starten (Aufgabenplanung -> Light-Butler)"))
        _add_helper(z, top + "helfer/", mac_dirs)
    return buf.getvalue()


LIESMICH_WINMUSIK = """LIGHT-BUTLER: WINDOWS-PC ALS MUSIK-RECHNER
==========================================

Light-Butler Helfer und Mixxx-Bruecke fuer einen Windows-PC (10 oder 11), OHNE den Light-Butler selbst: das Licht macht
der Raspberry Pi oder ein anderer Rechner im Heimnetz. Gegenstueck zum Mac-Paket light-butler-mac.zip.

1. Python 3.12 von python.org installieren, beim Installieren "Add python.exe to PATH" anhaken.
2. Mixxx 2.5 (mixxx.org) und loopMIDI (tobias-erichsen.de, kostenlos) installieren. In loopMIDI unten den Namen
   Light-Butler eintragen und auf + klicken (virtueller MIDI-Anschluss, am Mac ist das der IAC-Treiber).
3. Dieses ZIP entpacken, im entpackten Ordner ein Terminal oeffnen (Shift + Rechtsklick -> "In Terminal oeffnen"):
       powershell -ExecutionPolicy Bypass -File install_windows_musik.ps1
   Das Skript fragt nach dem Namen des Light-Butler (Standard lightbutler.local, gemerkt in
   %USERPROFILE%\\.light-butler-pi). Administratorrechte braucht es nicht.
4. In Mixxx einmal: Einstellungen -> Controller -> Light-Butler aktivieren, Mapping "Light-Butler Bridge" waehlen.
5. Mixxx ab jetzt ueber die Verknuepfung "Light-Butler Mixxx" (Startmenue/Desktop) starten: Tempo, Beat, Lied, Drops
   und Hotcues gehen an den Light-Butler. Vor jedem Start sichert sie die Mixxx-Datenbank (die letzten 5 in
   %USERPROFILE%\\Light-Butler-Daten\\mixxx-sicherung).

HELFER (Aufgabe "Light-Butler Helfer", startet beim Anmelden ohne Fenster): Liedliste, Vorhoeren (Port 9025), Analyse,
Datenpflege, APC mini mk2 und ROLI LUMI Keys an diesem PC, Ton an den Light-Butler. Ton: VB-Cable (vb-audio.com),
Stereomix (Sound-Einstellungen -> Aufnahme -> aktivieren) oder Line-In, der Reihe nach gesucht; am Light-Butler im Panel
den Audio-Eingang "Musik-Rechner (Netzwerk)" waehlen. Geloeschtes kommt in den Ordner "Light-Butler Papierkorb" oben auf dem
Laufwerk, nie endgueltig weg. ffmpeg (MP3-Umwandlung, Reparatur, Shazam): winget install Gyan.FFmpeg
Pegelkurven mit der Grafikkarte: eigenes Paket light-butler-windows.zip (install_stems.ps1).

Firewall: fragt Windows nach Python, nur "Private Netzwerke" zulassen, sonst erreicht das Panel den Vorhoer-Server nicht.
Meldungen: %LOCALAPPDATA%\\Light-Butler\\helfer.log, bridge.log, launcher.log.
Aktualisieren: neues ZIP holen und das Skript noch einmal ausfuehren (Daten bleiben).
Entfernen: powershell -ExecutionPolicy Bypass -File install_windows_musik.ps1 -Entfernen
"""
WINMUSIK_NAME = "light-butler-windows-musik.zip"


def windows_music_zip(base=HERE, mac_dirs=MAC_DIRS):
    """ZIP Windows-Musik-Rechner (15.11.2026): Light-Butler-Windows-Musik/{install_windows_musik.ps1, LIESMICH.txt, helfer/...}.
    Nur Helfer und Mixxx-Bruecke, kein Light-Butler (show.py), keine Daten. None = Dateien fehlen."""
    if not os.path.isfile(os.path.join(base, "install_windows_musik.ps1")):
        return None
    buf = io.BytesIO()
    top = "Light-Butler-Windows-Musik/"
    crlf = lambda s: s.replace("\r\n", "\n").replace("\n", "\r\n")       # noqa: E731
    with zipfile.ZipFile(buf, "w") as z:
        _add(z, os.path.join(base, "install_windows_musik.ps1"), top + "install_windows_musik.ps1")
        z.writestr(top + "LIESMICH.txt", crlf(LIESMICH_WINMUSIK))
        _license(z, top)
        if not _add_helper(z, top + "helfer/", mac_dirs):
            return None
    return buf.getvalue()


# ---- Mac als Licht-Rechner (Wunsch von Markus, 15.11.2026) ----
# Wie das Windows-Paket: dieselben Programme, keine Zustandsdateien, neutrale Geraete, alle Ausgaben aus. Helfer und
# Mixxx-Bruecke kommen am Mac aus dem eigenen Paket (install_mac.sh), damit sie nicht doppelt laufen.
MAC_SHOW_CONF = """# Startoptionen fuer den Light-Butler am Mac (eine Zeile, ohne Anfuehrungszeichen).
# --device NAME     Audio-Eingang per Namensteil, zum Beispiel --device USB oder --device BlackHole (ohne: im Panel waehlen,
#                   Einstellungen -> Verbindungen)
# --strobe          Strobe-Erlaubnis beim Start (weglassen = kein Strobo; im Panel einschaltbar)
# --web 8080        Web-Panel fuer iPad/Handy (http://<Name-des-Mac>.local:8080/)
# Danach neu starten:  launchctl kickstart -k gui/$(id -u)/light-butler.show
SHOW_ARGS=--master 1.0 --web 8080
"""
LIESMICH_MACFULL = """LIGHT-BUTLER FUER EINEN MAC
===========================

Die ganze Lichtsteuerung (Analyse, Szenen, Showmanager, Web-Panel) wie am Raspberry Pi, fuer einen Mac (Apple Silicon
oder Intel, macOS 12 oder neuer). Alle Programme und das Handbuch, ohne persoenliche Daten (keine Einstellungen, Szenen,
Shows, Schluessel).

1. python3 muss da sein: im Terminal  xcode-select --install  (oder Python 3.12 von python.org).
2. Dieses ZIP entpacken (Doppelklick im Finder).
3. Terminal oeffnen, in den entpackten Ordner wechseln (cd, dann den Ordner ins Fenster ziehen, Return) und eintippen:
       bash install_lightbutler_mac.sh
   Kein Administrator-Passwort noetig. Dauert beim ersten Mal ein paar Minuten.
4. Panel im Browser: http://localhost:8080/  (Handy/iPad im Heimnetz: http://<Name-des-Mac>.local:8080/)

TON: Beim ersten Start fragt macOS vielleicht, ob Python das Mikrofon (den Ton-Eingang) benutzen darf: erlauben. Bleibt
es still: Systemeinstellungen -> Datenschutz & Sicherheit -> Mikrofon. Den Eingang waehlst du im Panel (Einstellungen ->
Verbindungen): USB-Soundkarte am Mischpult oder BlackHole fuer den Ton von Mixxx am selben Mac.

FIREWALL: Fragt macOS, ob Python eingehende Verbindungen annehmen darf: erlauben, sonst erreichen Handy und iPad das
Panel nicht. Das Panel hat keine Anmeldung: nie ins Internet stellen.

WICHTIG: Ein neuer Light-Butler startet mit allen Ausgaben AUS (DMX, WLED, Nanoleaf). Senden zwei Light-Butler im
selben Netz gleichzeitig, kaempfen sie ums Licht. Einschalten im Panel unter Einstellungen -> Ausgabe, wenn nur dieser
sendet. Strobe, Laser und Nebel sind wie bei jeder neuen Anlage aus.

HELFER UND MIXXX: eigenes Paket "Mac: Mixxx-Bruecke und Helfer" (install_mac.sh). Laeuft alles auf demselben Mac, dort
als Adresse des Light-Butler  localhost  angeben.

Was am Mac geht: Ton ueber USB-Audio oder BlackHole, APC mini mk2 und ROLI LUMI Keys per USB, DMX ueber einen
FTDI-USB-Adapter (Open DMX USB) oder Art-Net. Nicht am Mac: Titelerkennung (SongRec), Temperatur/Spannung auf der Seite
Zustand (nur am Pi), Herunterfahren aus dem Panel.

Startet beim Anmelden von selbst (launchd, ~/Library/LaunchAgents/light-butler.show.plist) und nach einem Absturz neu.
Sicherung jede Nacht um 04:30 nach ~/Light-Butler/backups. Meldungen: ~/Library/Logs/Light-Butler/show.log.
Startoptionen: ~/Light-Butler/lichtshow/show.conf.
Aktualisieren: neues ZIP holen und install_lightbutler_mac.sh noch einmal ausfuehren. Einstellungen, Szenen, Shows,
Geraete und show.conf bleiben, nur die Programme werden erneuert.
Entfernen: bash install_lightbutler_mac.sh --entfernen (Autostart, Sicherung, Python-Umgebung; Daten bleiben).
"""
MACFULL_NAME = "light-butler-mac-voll.zip"


def mac_full_zip(base=HERE):
    """ZIP fuer einen Mac als Licht-Rechner: Light-Butler-Mac-Voll/{install_lightbutler_mac.sh, LIESMICH.txt, lichtshow/...}.
    None = Dateien fehlen. Immer neutrale Geraete, ohne Helfer (der kommt aus light-butler-mac.zip)."""
    if not os.path.isfile(os.path.join(base, "install_lightbutler_mac.sh")) or not os.path.isfile(os.path.join(base, "show.py")):
        return None
    buf = io.BytesIO()
    top = "Light-Butler-Mac-Voll/"
    with zipfile.ZipFile(buf, "w") as z:
        _add(z, os.path.join(base, "install_lightbutler_mac.sh"), top + "install_lightbutler_mac.sh")
        z.writestr(top + "LIESMICH.txt", LIESMICH_MACFULL)
        _license(z, top)
        _add_programs(z, base, top + "lichtshow/")
        z.writestr(top + "lichtshow/show.conf", MAC_SHOW_CONF)
        with open(os.path.join(base, "fixtures.yaml"), encoding="utf-8") as f:
            z.writestr(top + "lichtshow/fixtures.yaml",
                       neutral_fixtures(f.read(), "den Light-Butler neu starten (launchctl kickstart -k gui/$(id -u)/light-butler.show)"))
    return buf.getvalue()


LIESMICH_MAC += COPYRIGHT
LIESMICH_WIN += COPYRIGHT
LIESMICH_PI += COPYRIGHT.replace("%", "%%")
LIESMICH_WINFULL += COPYRIGHT
LIESMICH_WINMUSIK += COPYRIGHT
LIESMICH_MACFULL += COPYRIGHT


# ---- Stand aller Pakete (Wunsch 14.11.2026): Der Helfer am Mac kopiert Pakete und Handbuecher auf den Musik-Stick
# (Ordner Light-Butler-Programme). Damit er nicht jedes Mal alles holen muss, fragt er zuerst diesen Stand: ein Kennwort aus
# Name, Groesse und Zeit aller Dateien, die in die Pakete kommen. Neue Fassung eingespielt -> anderer Stand. Nur lesen.
def stand(base=HERE, mac_dirs=MAC_DIRS, win_dirs=WIN_DIRS):
    h = hashlib.sha1()

    def add(path, rel):
        try:
            st = os.stat(path)
        except OSError:
            return
        h.update(("%s|%d|%d\n" % (rel, st.st_size, int(st.st_mtime))).encode("utf-8"))
    for root, subdirs, files in os.walk(base):
        rel_root = os.path.relpath(root, base)
        subdirs[:] = sorted(d for d in subdirs if d not in PI_SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if name.startswith(".") or name.endswith(PI_SKIP_EXT) or (rel_root == "." and name in PI_SKIP_FILES and name not in ("fixtures.yaml", "homematic.yaml")):
                continue
            p = os.path.join(root, name)
            add(p, "pi/" + os.path.relpath(p, base))
    for n, p in sorted(_pi_docs(base).items()):
        add(p, "docs/" + n)
    ep = exe_zip_path()
    if ep is not None:
        add(ep, "exe/" + EXE_NAME)                      # neue Light-Butler.exe abgelegt: neuer Stand (Stick erneuert sie)
    mb = _first_dir(mac_dirs, "install_mac.sh")
    if mb is not None:
        add(os.path.join(mb, "install_mac.sh"), "mac/install_mac.sh")
        for part in MAC_PARTS:
            for root, subdirs, files in os.walk(os.path.join(mb, part)):
                subdirs[:] = sorted(d for d in subdirs if d not in SKIP_DIRS and not d.startswith("."))
                for name in sorted(files):
                    if not name.endswith(SKIP_EXT) and not name.startswith("."):
                        p = os.path.join(root, name)
                        add(p, "mac/" + os.path.relpath(p, mb))
    for name in WIN_FILES:
        d = _first_dir(win_dirs, name)
        if d is not None:
            add(os.path.join(d, name), "win/" + name)
    return h.hexdigest()[:16]


# Aufruf ohne laufenden Light-Butler (16.11.2026, Quelltext von GitHub): dieselben Pakete wie im Panel als Dateien.
#     python3 pi/pakete.py ZIEL [ORDNER]
CLI = {"pi": ("light-butler-pi.zip", lambda: pi_zip()),
       "windows": ("light-butler-windows-voll.zip", lambda: windows_zip()),
       "mac": ("light-butler-mac-voll.zip", lambda: mac_full_zip()),
       "musik-mac": ("light-butler-mac.zip", lambda: mac_zip()),
       "musik-windows": (WINMUSIK_NAME, lambda: windows_music_zip()),
       "pegelkurven": ("light-butler-windows.zip", lambda: win_zip())}


def main(argv):
    if len(argv) < 2 or argv[1] not in CLI:
        print("Aufruf: python3 pi/pakete.py ZIEL [ORDNER]\n"
              "  pi             Light-Butler fuer einen Raspberry Pi\n"
              "  windows        Light-Butler fuer einen Windows-PC\n"
              "  mac            Light-Butler fuer einen Mac\n"
              "  musik-mac      Musik-Rechner Mac (Mixxx-Bruecke, Helfer, Pegelkurven)\n"
              "  musik-windows  Musik-Rechner Windows (Helfer, Mixxx-Bruecke)\n"
              "  pegelkurven    Pegelkurven-Rechner Windows")
        return 2
    name, make = CLI[argv[1]]
    data = make()
    if data is None:
        print("Dateien fuer dieses Paket fehlen")
        return 1
    out = os.path.join(argv[2] if len(argv) > 2 else ".", name)
    with open(out, "wb") as f:
        f.write(data)
    print("geschrieben:", out)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv))
