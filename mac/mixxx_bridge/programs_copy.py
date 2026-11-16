#!/usr/bin/env python3
"""
programs_copy.py - Light-Butler-Programme am Musik-Stick (Wunsch von Markus, 14.11.2026).

Neben dem Musikordner (wie musik-backup und musik-import) legt der Helfer am Mac einen Notfall-Koffer an:
    /Volumes/STICK/Light-Butler-Programme/
        light-butler-mac.zip          Mixxx-Bruecke, Helfer, Pegelkurven (Musik-Rechner)
        light-butler-windows.zip      Pegelkurven am Windows-PC
        light-butler-windows-voll.zip ganzer Light-Butler fuer einen Windows-PC (15.11.2026)
        light-butler-windows-exe.zip  derselbe als Light-Butler.exe, ohne Python (wenn am Pi abgelegt)
        light-butler-pi.zip           neuer Pi, neutrale Einstellungen
        light-butler-pi-ersatz.zip    Ersatz-Pi mit der eigenen Geraeteliste
        lichtshow-backup-....zip      juengste Sicherung des Pi (ohne Nanoleaf-Token und Claude-Schluessel)
        Handbuch.html, Manual-EN.html, verbindungen.svg   Hilfe des Panels (im Browser oeffnen)
        Technik.html, Technical-EN.html, systemschema*.svg  Technische Beschreibung, Bilder
        Showmanager-Handbuch.pdf, Light-Butler-Broschuere.pdf
        LIESMICH.txt, stand.json
        vorher/                       die vorige Fassung (eine), falls eine neue einen Fehler hat
Der Pi meldet unter /download/stand ein Kennwort seiner Dateien; nur wenn es sich aendert (neue Fassung eingespielt), holt
der Helfer alles neu, sonst hoechstens einmal am Tag. Die Sicherung kommt, sobald am Pi eine neuere entstanden ist.
Geschrieben wird nur in diesen Ordner; fremde Dateien darin bleiben unberuehrt. Aufs Licht wirkt das nicht.
"""
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request

FOLDER = "Light-Butler-Programme"
PREV = "vorher"
STAND = "stand.json"
DAY_S = 24 * 3600.0
ITEMS = (("/download/light-butler-mac.zip", "light-butler-mac.zip"), ("/download/light-butler-windows.zip", "light-butler-windows.zip"),
         ("/download/light-butler-pi.zip", "light-butler-pi.zip"), ("/download/light-butler-pi-ersatz.zip", "light-butler-pi-ersatz.zip"),
         ("/help?lang=de", "Handbuch.html"), ("/help?lang=en", "Manual-EN.html"), ("/shows/handbuch.pdf", "Showmanager-Handbuch.pdf"),
         ("/static/sm/verbindungen.svg", "verbindungen.svg"))
OPTIONAL = (("/download/broschuere.pdf", "Light-Butler-Broschuere.pdf"),
            ("/download/light-butler-windows-voll.zip", "light-butler-windows-voll.zip"),   # Windows-PC (15.11.2026)
            ("/download/light-butler-windows-musik.zip", "light-butler-windows-musik.zip"),  # Windows-Musik-Rechner (15.11.2026)
            ("/download/light-butler-mac-voll.zip", "light-butler-mac-voll.zip"),        # Mac als Licht-Rechner (15.11.2026)
            ("/download/light-butler-windows-exe.zip", "light-butler-windows-exe.zip"),     # Light-Butler.exe, wenn abgelegt
            ("/help/technik?lang=de", "Technik.html"), ("/help/technik?lang=en", "Technical-EN.html"),   # Technische Beschreibung
            ("/static/sm/verbindungen_en.svg", "verbindungen_en.svg"),                  # Bilder der Hilfe (15.11.2026)
            ("/static/sm/systemschema.svg", "systemschema.svg"), ("/static/sm/systemschema_en.svg", "systemschema_en.svg"))   # aelterer Pi: gibt es noch nicht, fehlt dann einfach
BACKUP_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}\.zip$")
MAX_BYTES = 200 * 1024 * 1024

LIESMICH = """LIGHT-BUTLER-PROGRAMME
======================

Stand: {when} (Fassung {v})
Kopiert der Light-Butler Helfer am Musik-Rechner von selbst, sobald eine neue Fassung am Pi eingespielt ist, sonst
einmal am Tag. Hier nichts aendern: der Ordner wird ueberschrieben. Die vorige Fassung liegt in "vorher".

  light-butler-mac.zip         Musik-Rechner (Mac): Mixxx-Bruecke, Helfer, Pegelkurven.
                               Entpacken, im Terminal: bash install_mac.sh
  light-butler-windows.zip     Windows-PC: Pegelkurven mit der Grafikkarte.
                               Entpacken, PowerShell: powershell -ExecutionPolicy Bypass -File install_stems.ps1
  light-butler-windows-voll.zip  Windows-PC als Licht-Rechner: der ganze Light-Butler wie am Pi.
                               Entpacken, PowerShell: powershell -ExecutionPolicy Bypass -File install_windows.ps1
  light-butler-windows-musik.zip Windows-PC als Musik-Rechner: Helfer und Mixxx-Bruecke, Licht am Pi.
                               Entpacken, PowerShell: powershell -ExecutionPolicy Bypass -File install_windows_musik.ps1
  light-butler-windows-exe.zip   Ganzer Light-Butler als Light-Butler.exe, Python ist eingebaut: entpacken, Light-Butler.exe starten.
  light-butler-pi.zip          Neuer Raspberry Pi ohne eigene Daten (Freund, Test).
  light-butler-pi-ersatz.zip   ERSATZ fuer den eigenen Pi: mit Geraeteliste und Adressen.
                               ZIP auf den Pi kopieren, entpacken, bash install_pi.sh
  {backup}  Juengste Sicherung des Pi (Einstellungen, Szenen, Shows ...),
                               ohne Nanoleaf-Token und Claude-Schluessel (die neu eintragen).
                               Zurueckspielen am Pi: python3 ~/lichtshow/backup.py --restore DATEI
  Handbuch.html, Manual-EN.html   Hilfe des Panels auf Deutsch und Englisch (im Browser oeffnen).
  Technik.html, Technical-EN.html  Technische Beschreibung (ausfuehrlich, fuer Technik-Interessierte).
  Showmanager-Handbuch.pdf     Bedienungsanleitung des Showmanagers.
  Light-Butler-Broschuere.pdf  Kurze Vorstellung zum Weitergeben (ohne eigene Daten, Bilder mit erfundener Musik).

Pi kaputt? Neue SD-Karte mit Raspberry Pi OS (64 Bit), Benutzer admin, light-butler-pi-ersatz.zip und die Sicherung
auf den Pi kopieren, install_pi.sh ausfuehren, dann die Sicherung zurueckspielen.
"""


def folder_for(music_root):
    """Ordner neben dem Musikordner, oder '' (kein Musikordner, Stick nicht da)."""
    root = (music_root or "").rstrip("/")
    if not root or not os.path.isdir(root):
        return ""
    return os.path.join(os.path.dirname(root), FOLDER)


def _get(base, path, opener, timeout=120):
    with opener(base + path, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("zu gross: " + path)
        cd = r.headers.get("Content-Disposition", "") if hasattr(r, "headers") and r.headers is not None else ""
    return data, cd


def fix_help(html, svg_name="verbindungen.svg"):
    """Hilfe-Seite fuer den Stick: ohne Kopfleiste des Panels (braucht den Pi), Bild daneben statt vom Pi."""
    html = re.sub(r'<script src="/static/sm/nav\.js"></script>', "", html)
    html = html.replace('src="/static/sm/verbindungen.svg"', 'src="' + svg_name + '"')
    html = re.sub(r'src="/static/sm/((?:verbindungen_en|systemschema(?:_en)?)\.svg)"', r'src="\1"', html)   # liegen daneben
    for href, name in (("/help/technik?lang=de", "Technik.html"), ("/help/technik?lang=en", "Technical-EN.html"),
                       ("/help?lang=de", "Handbuch.html"), ("/help?lang=en", "Manual-EN.html")):
        html = html.replace('href="%s"' % href, 'href="%s"' % name)
    return re.sub(r'<link[^>]+href="/(?:icon\.svg|apple-touch-icon\.png)"[^>]*>', "", html)


def _load(dest):
    try:
        with open(os.path.join(dest, STAND), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write(path, data):
    tmp = path + ".lb-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def sync(base, music_root, opener=urllib.request.urlopen, now=time.time, log=print, force=False):
    """Einmal abgleichen. Rueckgabe {dir, v, new, files, backup, mb} oder None (kein Stick). Fehler am Pi: OSError."""
    dest = folder_for(music_root)
    if not dest:
        return None
    st = _load(dest)
    try:
        info = json.loads(_get(base, "/download/stand", opener, 20)[0].decode("utf-8") or "{}")
    except urllib.error.HTTPError:                              # aelterer Pi ohne Stand: einmal am Tag alles
        info = {}
    v = str(info.get("v") or "")
    have = all(os.path.isfile(os.path.join(dest, n)) for _p, n in ITEMS)
    new = force or not have or (v and v != st.get("v")) or (not v and now() - float(st.get("t") or 0) >= DAY_S)   # ohne Stand: taeglich
    files = [n for _p, n in ITEMS]
    if new:
        got = {}
        for path, name in ITEMS:                                # erst alles holen, dann schreiben: halbe Fassungen gibt es nicht
            data, _cd = _get(base, path, opener)
            if name.endswith(".html"):
                data = fix_help(data.decode("utf-8")).encode("utf-8")
            got[name] = data
        for path, name in OPTIONAL:
            try:
                data = _get(base, path, opener)[0]
                got[name] = fix_help(data.decode("utf-8")).encode("utf-8") if name.endswith(".html") else data
                files.append(name)
            except urllib.error.HTTPError:
                pass
        os.makedirs(dest, exist_ok=True)
        if have and v and st.get("v") and v != st.get("v"):    # neue Fassung: die bisherige nach "vorher" (die aeltere darin geht)
            prev = os.path.join(dest, PREV)
            os.makedirs(prev, exist_ok=True)
            for n in files + ([st["backup"]] if st.get("backup") else []) + ["LIESMICH.txt", STAND]:
                if os.path.isfile(os.path.join(dest, n)):
                    shutil.copy2(os.path.join(dest, n), os.path.join(prev, n))
        for name, data in got.items():
            _write(os.path.join(dest, name), data)
    files += [n for _p, n in OPTIONAL if n not in files and os.path.isfile(os.path.join(dest, n))]
    bk = str(info.get("backup") or "")
    backup = st.get("backup") or ""
    if bk and BACKUP_RE.match(bk) and (bk != backup or not os.path.isfile(os.path.join(dest, bk))):
        try:
            data, cd = _get(base, "/download/backup", opener)
            m = re.search(r'filename="([^"]+)"', cd or "")
            name = m.group(1) if m and BACKUP_RE.match(m.group(1)) else bk
            os.makedirs(dest, exist_ok=True)
            _write(os.path.join(dest, name), data)
            if backup and backup != name and BACKUP_RE.match(backup) and os.path.isfile(os.path.join(dest, backup)):
                prev = os.path.join(dest, PREV)                # die vorige Sicherung nach "vorher" (dort ersetzt sie die aeltere)
                os.makedirs(prev, exist_ok=True)
                for old in os.listdir(prev):
                    if old.startswith("lichtshow-backup") and old.endswith(".zip") and old != backup:
                        os.remove(os.path.join(prev, old))
                os.replace(os.path.join(dest, backup), os.path.join(prev, backup))
            backup, new = name, True
        except urllib.error.HTTPError:                          # noch keine Sicherung am Pi
            pass
    if new:
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(now()))
        _write(os.path.join(dest, "LIESMICH.txt"),
               LIESMICH.format(when=when, v=v or "?", backup=(backup or "lichtshow-backup-....zip").ljust(27)).replace("\n", "\r\n").encode("utf-8"))
        st = {"v": v, "t": now(), "backup": backup, "files": files}
        _write(os.path.join(dest, STAND), json.dumps(st, ensure_ascii=False).encode("utf-8"))
    mb = sum(os.path.getsize(os.path.join(dest, n)) for n in files + [backup] if n and os.path.isfile(os.path.join(dest, n))) / 1e6
    return {"dir": dest, "v": v, "new": bool(new), "files": files + ([backup] if backup else []), "backup": backup, "mb": round(mb, 1)}


def report(base, res, opener=urllib.request.urlopen, err=""):
    """Dem Pi melden, was am Stick liegt (Karte auf der Seite Vorab-Laeufe)."""
    d = dict(res or {}, op="programs_report", err=err)
    req = urllib.request.Request(base + "/api/sm/cmd", data=json.dumps(d).encode("utf-8"), method="POST")
    try:
        with opener(req, timeout=10) as r:
            r.read()
    except Exception:                                           # noqa: BLE001  nur Anzeige: nie stoeren
        pass
