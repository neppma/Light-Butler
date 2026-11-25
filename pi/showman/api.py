#!/usr/bin/env python3
"""
api.py - HTTP-Routen des Showmanagers im vorhandenen Web-Panel.

  /shows                Playback-Seite (Show waehlen, Play), funktioniert ohne Editor
  /shows/edit?show=X    Show-Editor
  /static/sm/...        Dateien der Oberflaeche
  /api/sm/...           Daten und Befehle
  /api/sm/ws            WebSocket: Audio-Position vom Browser, Stand zurueck

Wie das restliche Panel ohne Anmeldung, nur im Heimnetz. Datenfluss und Show laufen getrennt: Kein Aufruf hier blockiert die
Hauptschleife, die Engine bekommt fertig uebersetzte Shows.
"""
import base64
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
import urllib.request
import zipfile
from urllib.parse import parse_qs, quote, urlparse

from . import analysis
from . import marks_bulk
from . import covers
from . import artists as artists_mod
from . import albums as albums_mod
from . import radio as radio_mod
from . import eichen
from . import local_play
from . import favorites as fav_mod
from . import stars as stars_mod
from . import missing as missing_mod
from . import stems_bulk
from . import assistant
from . import autodj
from . import fixtures as fm
from . import lyrics as ly
from . import patterns as pt
from . import room as rm
from . import ws
from .engine import MIXXX, PlaybackEngine
from . import timeline as tl
from .store import ShowStore, audio_fingerprint

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(HERE, "static", "sm")
MANUAL = os.path.join(HERE, "static", "Showmanager-Handbuch.pdf")
BROCHURE = os.path.join(HERE, "static", "Light-Butler-Broschuere.pdf")   # Broschuere (docs/broschuere/build_broschuere.py), 14.11.2026
STATIC_RE = re.compile(r"^[a-z_]+\.(js|css|html|svg)$")
# Pegelkurven-Helfer zum Herunterladen (Windows-PC): deploy.sh legt sie am Pi in helfer/, im Projekt liegen sie in mac/stems/
HELFER = ("stems_show.py", "stem_curves.py", "install_stems.ps1")
HELFER_DIRS = (os.path.join(HERE, "helfer"), os.path.join(os.path.dirname(HERE), "mac", "stems"))
CTYPES = {"js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8", "html": "text/html; charset=utf-8", "svg": "image/svg+xml"}
MAX_JSON = 64 * 1024 * 1024
MAX_PEAK_VALUES = 3000000
MX_GRACE_S = 1.5             # so lange darf das Lied fehlen oder wechseln, bevor die Show endet (kurzes Stocken, Mischen)
NANO_FX_CACHE_S = 60.0
MX_SETTLE_S = 0.5            # so lange muss ein Lied hoerbar sein, bevor seine Show startet
MX_FOREIGN_S = 3.0           # so lange muss Mixxx ein anderes Lied hoerbar spielen, bevor eine Show aus dem Browser endet


def is_empty_show(doc):
    """Noch nichts programmiert: keine Spuren mit Inhalt und keine Szenen-Clips."""
    return not doc.get("scene_clips") and not any(t.get("clips") or t.get("keys") or t.get("keyframes") for t in doc.get("tracks") or [])


def _norm(title):
    """Titel vergleichbar machen: Die Mixxx-Datenbank liefert Umlaute manchmal zerlegt (NFD)."""
    return " ".join(unicodedata.normalize("NFC", str(title or "")).casefold().split())


def _core(name):
    """Kern eines Namens ohne Klammerzusatz: "Titanium (Vorschlag KI)" und "Titanium (Future Rave Remix)" -> "titanium"."""
    return _norm(re.split(r"\s*[(\[]", str(name or ""), 1)[0])


def shows_dir():
    return os.environ.get("S2L_SHOWS_DIR") or os.path.join(HERE, "shows")


class ShowManager:
    """Hier kommen Dateiverwaltung, Engine und die laufende Show zusammen."""

    def __init__(self, show, base=None):
        self.show = show
        self.store = ShowStore(base or shows_dir())
        self.room_path = rm.room_path()                          # Raumplan (Seite /raum), Tests setzen einen eigenen Pfad
        self.engine = PlaybackEngine(show.rig)
        show.showman = self.engine
        self.current = None          # Name der geladenen Show
        self.index_cache, self.index_dirty = {}, True
        self.stem_bulk = stems_bulk.StemBulk(self.store, lambda: show.mixxx.library_full()
                                             if getattr(show, "mixxx", None) is not None and hasattr(show.mixxx, "library_full") else [],
                                             self.music_url, max_s=self.stems_max_s)   # Pegelkurven vorab fuer die Bibliothek (rechnet der Windows-PC)
        self.stem_claims = {}        # Fingerabdruck der MP3 -> (Rechner, Zeit, Show): wer gerade Pegelkurven rechnet (Mac, Windows-PC)
        self.mx_key = None           # Lied, dessen Show gerade aus Mixxx laeuft
        self.mx_block = None         # Lied, fuer das die Show von Hand beendet wurde (oder zu Ende ist)
        self.mx_foreign = None       # (Lied, seit wann): Mixxx spielt etwas anderes als die Show aus dem Browser
        self.mx_once = None          # Lied, zu dem Quick im Hauptpanel eine Show gemacht hat: sie startet einmal, auch ohne sm_mixxx_auto
        self.mx_lost_t = None
        self.mx_seen, self.mx_seen_t = None, 0.0
        self.fog_pos = None          # zuletzt gesehene Stelle (Nebelschuebe)
        self.fog_until = 0.0         # bis dahin laeuft ein Schub aus der Show
        self.key_path = os.path.join(HERE, "claude.json")   # API-Schluessel fuer den Show-Assistenten (Zustandsdatei, nie im Git)
        self.claude_opener = urllib.request.urlopen
        self.lyrics_opener = urllib.request.urlopen
        self.mac_opener = urllib.request.urlopen             # Abschnitte und Cues vom Vorhoer-Server am Mac (Quick)
        self.marks_bulk = marks_bulk.MarksBulk(self.store.base, lambda: show.mixxx.library_full()
                                               if getattr(show, "mixxx", None) is not None and hasattr(show.mixxx, "library_full") else [],
                                               self.music_url, lambda url, timeout: self.mac_opener(url, timeout=timeout))
        self.marks_bulk.resume()                               # Cue-Punkte vorab: nach einem Neustart weiter, wenn es lief
        self.covers = covers.Covers(self.store.base, lambda: show.mixxx.library_full()
                                    if getattr(show, "mixxx", None) is not None and hasattr(show.mixxx, "library_full") else [],
                                    self.music_url, lambda url, timeout: self.mac_opener(url, timeout=timeout))
        self.covers.resume()                                   # Cover vorab: nach einem Neustart weiter, wenn es lief
        self.covers.start_recheck()                            # Lieder ohne Cover alle paar Stunden wieder am Mac fragen
        self.artist_opener = None                              # Tests: eigenes Internet
        self.artists = artists_mod.Artists(self.store.base, lambda: show.mixxx.library_full()
                                           if getattr(show, "mixxx", None) is not None and hasattr(show.mixxx, "library_full") else [],
                                           opener=lambda req, timeout: (self.artist_opener or urllib.request.urlopen)(req, timeout=timeout),
                                           root=lambda: str(self._music_json().get("root") or "") if hasattr(self, "music_path") else "")
        self.albums = albums_mod.Albums(self.store.base, self.artists.library,                  # Alben (13.11.2026), wie die Interpreten
                                        opener=lambda req, timeout: (self.artist_opener or urllib.request.urlopen)(req, timeout=timeout),
                                        root=self.artists.root, artists=self.artists)
        self.stars = stars_mod.Stars(self.store.base)                                   # Sterne im Light-Butler setzen (14.11.2026)
        self.favs = fav_mod.Favorites(self.store.base, self.artists.library, artists=self.artists, albums=self.albums)   # Favoriten (14.11.2026)
        self.missing = missing_mod.Missing(self.store.base, self.artists.library)                  # Merkliste Fehlt mir (14.11.2026)
        self.favs.stars = self.stars                                                    # 5 Sterne = Favorit, auch hier gesetzte
        self.line_lock = threading.Lock()                                                # Eingang Line-In fuers Radio am Geraet
        self.line_sw, self.line_err, self.line_thread = None, "", None
        self.radio = radio_mod.Radio(self.store.base, opener=lambda req, timeout: (self.artist_opener or urllib.request.urlopen)(req, timeout=timeout))
        show.radio = self.radio                                                         # Internetradio (21.11.2026): Titel -> Licht-Stil, Matrix
        self.local = local_play.LocalPlay()
        self.eich = eichen.EichRuns()                # Eichstueck: letzter Durchlauf (Seite /eichen, nur im Speicher)
        show.local = self.local                                                         # Musik-DB spielt im Browser (21.11.2026): nur Anzeige
        show.lyric_cache = ly.LyricCache(os.path.join(self.store.base, "_liedtexte.sqlite"))  # "_": zaehlt nicht als Show, shows/ bleibt beim Einspielen unberuehrt
        self.lyric_bulk = ly.LyricBulk(show.lyric_cache, lambda: show.mixxx.library() if getattr(show, "mixxx", None) is not None else [])
        self.lyric_bulk.resume()
        if getattr(show, "mixxx", None) is not None and hasattr(show.mixxx, "persist"):
            show.mixxx.persist(os.path.join(self.store.base, "_mixxx_bibliothek.json"))   # Musik-Datenbank auch ohne Mac (Seite /musik)
        self.spent_path = os.path.join(HERE, "claude_kosten.json")   # Summe der geschaetzten Kosten (Zustandsdatei, nie im Git)
        self.music_path = os.path.join(HERE, "music.json")           # Musikordner am Mac aus dem Panel (Zustandsdatei, nie im Git)
        # Interpreten-Bilder vorab: nach einem Neustart weiter, wenn es lief. Erst hier, wo music_path steht (Fehlerbericht 13.11.2026:
        # weiter oben stuerzte der Start ab, wenn der Lauf vor dem Einspielen gestartet war)
        self.artists.resume()
        self.job, self.job_sync = None, False                   # Claude entwirft: laeuft im Hintergrund
        self.nano_fx, self.nano_fx_t = [], -1e9                 # Effekte auf dem Nanoleaf (nano_effects)

    def now(self):
        return time.time()

    def panel_scenes(self):
        """Szenen aus dem Hauptpanel, die eine Show ansteuern darf: keine Sondertasten, nicht die Szene Laser."""
        return [s.name for s in getattr(self.show, "scene_defs", []) if not s.special]

    def nano_effects(self):
        """Effekte auf dem Nanoleaf, eine Minute gemerkt. Das Geraet antwortet vielleicht nicht: dann eben keine."""
        now = self.now()
        if now - self.nano_fx_t >= NANO_FX_CACHE_S:
            self.nano_fx_t = now
            found = []
            for snd in getattr(getattr(self.show, "output", None), "senders", {}).values():
                if hasattr(snd, "set_effect"):
                    try:
                        found = snd.client.effects()
                    except OSError as e:
                        print(f"Nanoleaf-Effekte: {type(e).__name__}", flush=True)
                    except Exception as e:           # NanoleafError: nur die Art, die Adresse enthaelt den Token nicht
                        print(f"Nanoleaf-Effekte: {type(e).__name__}", flush=True)
            self.nano_fx = found
        return self.nano_fx

    def meta(self):
        rig = self.show.rig
        cat = pt.catalog()
        cat["params"]["nano_effect"] = dict(cat["params"]["nano_effect"], unit="select",
                                            options=[[e["name"], e["name"] + (" ♫" if e.get("rhythm") else "")] for e in self.nano_effects()] or [["", "Keine Effekte gefunden"]])
        scenes = self.panel_scenes()
        cat["params"]["panel_scene"] = dict(cat["params"]["panel_scene"], unit="select", options=[[n, n] for n in scenes] or [["", "Keine Szenen"]])
        return {"fixtures": fm.fixture_list(rig), "groups": fm.default_groups(rig), **cat, "library": self.store.library()["patterns"],
                "strobe": bool(self.show.strobe), "light_ms": self.show.cfg["sm_light_ms"]}

    def status(self):
        st = self.engine.status(self.now(), self.show.strobe)
        st["blackout"] = self.show.override == "blackout"
        st["laser_allowed"] = self.show.cfg["sm_laser"] > 0.5
        st["fog_allowed"] = self.show.cfg["sm_fog"] > 0.5
        st["light_ms"] = self.show.cfg["sm_light_ms"]
        return st

    # ---- Mixxx: Show zum hoerbaren Lied ----------------------------------------------------------------------
    def match(self, fp, title, dur):
        """Show zum Lied: zuerst dieselbe MP3 (Fingerabdruck), sonst der von Hand gewaehlte Titel mit passender Laenge."""
        if self.index_dirty:
            self.index_dirty = False
            self.index_cache = {e["name"]: e for e in self.store.mixxx_index(self.index_cache)}
        shows = [e for e in self.index_cache.values() if e["on"]]
        hit = [e for e in shows if fp and e["fp"] == fp]
        if not hit:
            hit = [e for e in shows if title and e["title"] and _norm(e["title"]) == _norm(title) and abs(e["dur"] - dur) <= 1.0]
        return max(hit, key=lambda e: e["mtime"]) if hit else None   # mehrere Kopien: die zuletzt gespeicherte

    def _foreign_tick(self, now, song, mx):
        """Show aus dem Showmanager (Browser besitzt die Zeit) laeuft oder steht noch mit Licht an, aber in Mixxx laeuft hoerbar
        ein anderes Lied: nach MX_FOREIGN_S endet sie, das Licht geht zurueck an AUTO und die Show des neuen Liedes darf starten
        (Fehlerbericht 06.11.2026: Hauptpanel blieb auf Cover und Liedtext der alten Show stehen)."""
        en = self.engine
        if not (en.loaded and en.owner != MIXXX and song is not None):
            self.mx_foreign = None
            return
        if self.index_dirty or not self.index_cache:
            self.index_cache = {e["name"]: e for e in self.store.mixxx_index(self.index_cache)}
            self.index_dirty = False
        e = self.index_cache.get(en.doc_name) or {}
        same = bool((mx.get("fp") and e.get("fp") == mx.get("fp"))
                    or (e.get("title") and _norm(e["title"]) == _norm(mx.get("title"))))
        if same:
            self.mx_foreign = None
            return
        if self.mx_foreign is None or self.mx_foreign[0] != song:
            self.mx_foreign = (song, now)
            return
        if now - self.mx_foreign[1] >= MX_FOREIGN_S:
            en.stop(now)
            self.mx_foreign, self.mx_block, self.mx_seen = None, None, None

    def _mx_end(self, now):
        self.engine.stop(now)
        self.mx_key, self.mx_lost_t = None, None

    def mixxx_tick(self, now):
        """Fuenfmal pro Sekunde in eigenem Thread: Show starten, ihr die Position geben, beenden. Die Hauptschleife wartet nie darauf."""
        en, mx = self.engine, self.show.mx
        running = en.loaded and en.owner == MIXXX
        if self.mx_key is not None and not running:   # Knopf SHOW, Stop oder Ende der Show: nicht gleich wieder starten
            self.mx_block, self.mx_key, self.mx_lost_t = self.mx_key, None, None
            if self.mx_once is not None:
                self.mx_once = None                   # einmal: nach dem Ende nicht wieder
        song = None
        if mx and mx.get("playing") and mx.get("deck") is not None and (mx.get("fp") or mx.get("title")):
            song = mx.get("fp") or _norm(mx.get("title"))
        self._foreign_tick(now, song, mx)
        running = en.loaded and en.owner == MIXXX
        once = self.mx_once is not None and (self.mx_once in (song, _norm(mx.get("title")) if mx else None) or (running and self.mx_key == song))
        if self.mx_once is not None and not running and song is not None and not once:
            self.mx_once = None                       # anderes Lied: Quick gilt nicht mehr
        if self.show.cfg["sm_mixxx_auto"] < 0.5 and not once:
            if running:
                self._mx_end(now)
            return
        if song is not None and song != self.mx_block:
            self.mx_block = None
        if running:
            if song == self.mx_key:
                self.mx_lost_t = None
                pos = mx["pos_f"] + max(0.0, now - mx.get("t", now)) * mx.get("rate", 1.0)
                en.report(MIXXX, pos, True, 0.0, now, mx.get("rate", 1.0))
            else:
                if self.mx_lost_t is None:
                    self.mx_lost_t = now
                if now - self.mx_lost_t >= MX_GRACE_S:
                    self._mx_end(now)
            return
        if (en.active() and en.clock.playing) or song is None or song == self.mx_block:   # Vorrang hat nur eine laufende Show am Licht, kein angehaltener Editor
            self.mx_seen = None
            return
        if song != self.mx_seen:
            self.mx_seen, self.mx_seen_t = song, now
        if now - self.mx_seen_t < MX_SETTLE_S:
            return
        e = self.match(mx.get("fp"), mx.get("title"), mx.get("dur", 0.0))
        pos = mx["pos_f"] + max(0.0, now - mx.get("t", now)) * mx.get("rate", 1.0)
        if e is None or pos >= e["duration"]:
            return
        en.load(self.store.load(e["name"]))
        self.current = e["name"]
        en.play(now, pos, True, MIXXX)
        self.mx_key, self.mx_lost_t = song, None

    def fog_tick(self, now):
        """Nebelschuebe der Show: nur beim normalen Abspielen, beim Springen nie. Pause, Stop und Springen beenden einen laufenden Schub."""
        en, c = self.engine, self.engine.compiled
        running = now < self.fog_until
        if not (en.active() and en.clock.playing and c is not None):
            self.fog_pos = None
            if running:
                self.fog_until = 0.0
                self.show.command({"fog_cue_off": True})
            return
        pos = en.position(now)
        last = self.fog_pos if self.fog_pos is not None else pos - 0.3
        self.fog_pos = pos
        if not 0.0 <= pos - last < 1.0:           # gesprungen
            if running:
                self.fog_until = 0.0
                self.show.command({"fog_cue_off": True})
            return
        for t, d in c.fog_cues:
            if last < t <= pos:
                self.fog_until = now + min(10.0, d)
                self.show.command({"fog_cue": d})

    def watch_mixxx(self):
        """Eigener Thread (webpanel.start)."""
        n = 0
        while True:
            time.sleep(0.2)
            n += 1
            if n % 150 == 0:
                self.index_dirty = True          # alle 30 s neu lesen, falls Shows am Pi kopiert wurden
            try:
                self.mixxx_tick(time.time())
                self.fog_tick(time.time())
            except (ValueError, KeyError, TypeError, OSError) as e:
                print(f"Showmanager/Mixxx: {e}", flush=True)
                self.mx_block = self.mx_seen     # kaputte Show: nicht jede 0,2 s neu versuchen

    def mixxx_songs(self, q=""):
        """Auswahl im Editor: was in den Decks liegt, und die Bibliothek (durchsuchbar)."""
        link = self.show.mixxx
        if link is None:
            return {"connected": False, "decks": [], "tracks": [], "total": 0}
        lib = link.library()
        words = _norm(q).split()
        hits = [x for x in lib if all(w in _norm(x[0]) for w in words)] if words else lib
        st = self.show.mx or {}
        return {"connected": bool(st.get("connected")), "decks": [{"title": t, "dur": d} for t, d in link.loaded()],
                "tracks": [{"title": t, "dur": d} for t, d in hits[:60]], "total": len(lib)}

    def music_conf(self):
        """Einstellungen zur Musik-Datenbank aus music.json: root = Musikordner am Mac (die Bruecke holt ihn sich alle 30 s)."""
        d = self._music_json()
        root = str(d.get("root") or "")
        excl = [str(x)[:200] for x in d.get("excl") or [] if isinstance(x, str)][:100] if isinstance(d.get("excl"), list) else []
        try:                                                        # geschaetzte Energiestufe und Tonart in die MP3s schreiben (Bruecke, Standard aus)
            ew, kw = self.show.cfg["energy_write"] > 0.5, self.show.cfg["key_write"] > 0.5
        except (AttributeError, KeyError, TypeError):
            ew = kw = False
        try:                                                        # ReplayGain in MP3s ohne Angabe schreiben (11.11.2026, Standard aus)
            rw = self.show.cfg["rg_write"] > 0.5
        except (AttributeError, KeyError, TypeError):
            rw = False
        try:                                                        # Cues ohne Mixxx: fuers Licht, in Mixxx schreiben (11.11.2026, Standard aus)
            ce, cw = self.show.cfg["cue_est"] > 0.5, self.show.cfg["cue_write"] > 0.5
        except (AttributeError, KeyError, TypeError):
            ce = cw = False
        link = getattr(self.show, "mixxx", None)                    # Fassung der Bibliothek, die der Pi komplett hat (die Bruecke
        libh = getattr(link, "lib_have_h", "") if link is not None else ""   # schickt nur, wenn ihre anders ist)
        out = {"root": root[:300], "excl": excl, "ew": ew, "kw": kw, "rw": rw, "ce": ce, "cw": cw, "libh": str(libh or "")}
        st = self.stars.pending() if getattr(self, "stars", None) is not None else []
        if st:
            out["stars"] = st                                       # Sterne fuer Mixxx: der Musik-Rechner holt und bestaetigt sie
        out["mx"] = self.show.cfg["mixxx_on"] > 0.5                 # Mixxx verwenden (aus: Musik-Rechner nimmt nur den Musikordner)
        nas = d.get("nas")
        if isinstance(nas, dict):                                  # NAS fuer das Spiegeln (Name/IP, MAC, Abschaltzeit), 10.11.2026
            out["nas"] = {k: str(nas.get(k) or "")[:64] for k in ("host", "mac", "off_at")}
        if link is not None and hasattr(link, "library_delta_ok") and link.library_delta_ok():
            out["libd"] = True                                     # die Bruecke darf nur Geaendertes schicken
        if link is not None and hasattr(link, "library_missing"):
            rh, miss = link.library_missing()
            if miss:
                out["libr"], out["miss"] = rh, miss                 # fehlende Stuecke: die Bruecke schickt nur diese nach
                if hasattr(link, "library_missing_count"):
                    out["missn"] = link.library_missing_count()     # alle fehlenden (miss hat hoechstens 600), 11.11.2026
        return out

    def _music_json(self):
        try:
            with open(self.music_path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _music_json_write(self, **kw):
        """music.json aendern, ohne die anderen Eintraege zu verlieren (Musikordner und ausgeschlossene Ordner)."""
        d = self._music_json()
        d.update(kw)
        tmp = self.music_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, self.music_path)

    def music_root_save(self, root):
        """Musikordner am Mac aus dem Panel speichern (leer = nur die Pfade aus Mixxx und MUSIC_ROOT aus config.sh)."""
        root = str(root or "").strip()[:300]
        if "\n" in root or "\0" in root:
            raise ValueError("Ungueltiger Pfad")
        self._music_json_write(root=root)
        return self.music_conf()

    @staticmethod
    def music_excl_clean(lines):
        """Ausgeschlossene Ordner (Wunsch 10.11.2026): je Zeile ein Ordner im Musikordner oder ein voller Pfad. Gleiche Regeln wie
        music_excl.clean am Mac: ohne Leerzeilen, ohne "..", ohne "/" am Ende, ohne Doppelte, hoechstens 100 zu 200 Zeichen."""
        import unicodedata
        if isinstance(lines, str):
            lines = lines.splitlines()
        if not isinstance(lines, list):
            raise ValueError("Liste erwartet")
        out, seen = [], set()
        for x in lines:
            x = unicodedata.normalize("NFC", str(x or "")).strip()
            if not x:
                continue
            if "\0" in x or len(x) > 200:
                raise ValueError("Zeile zu lang oder ungueltig: " + x[:60])
            parts = [p.strip() for p in x.split("/") if p.strip()]
            if not parts or any(p in (".", "..") for p in parts):
                raise ValueError("Ungueltiger Ordner: " + x[:60])
            x = ("/" if x.startswith("/") else "") + "/".join(parts)
            if x.casefold() not in seen:
                seen.add(x.casefold())
                out.append(x)
        if len(out) > 100:
            raise ValueError("Hoechstens 100 Ordner")
        return out

    def genre_ai(self, house, items):
        """Claude fragen (11.11.2026). Rueckgabe {map: {Genre: {to, why}}, cost_usd, spent}. Schreibt nichts."""
        from . import genre_ai
        if not isinstance(house, list) or not house:
            raise ValueError("Erst eine Hausliste anlegen (Reiter Hausliste im Genre-Editor)")
        if not isinstance(items, list) or not items:
            raise ValueError("Keine Genres zum Fragen")
        items = [x for x in items if isinstance(x, dict)][:genre_ai.MAX_GENRES]
        key = self._claude_key()
        if not key:
            raise ValueError("Kein Claude-Schluessel (im Show-Assistenten eintragen)")
        usage = {}
        try:
            answer = assistant.ask_claude(key, genre_ai.request(house, items, assistant.MODEL), timeout=180.0, opener=self.claude_opener, usage=usage)
        finally:
            cost = assistant.cost_usd(usage)
            self._add_spent(cost)
        return {"map": genre_ai.apply(house, items, answer), "cost_usd": round(cost, 4), "spent": self._spent()}

    def genre_song_ai(self, house, songs):
        """Claude-Knopf je Lied (11.11.2026): [{to, why}] je Lied. Nur Interpret, Titel, jetziges Genre gehen an Anthropic. Schreibt nichts."""
        from . import genre_ai
        if not isinstance(house, list) or not house:
            raise ValueError("Erst eine Hausliste anlegen (Reiter Hausliste im Genre-Editor)")
        songs = [x for x in songs if isinstance(x, dict)][:genre_ai.MAX_SONGS] if isinstance(songs, list) else []
        if not songs:
            raise ValueError("Kein Lied zum Fragen")
        key = self._claude_key()
        if not key:
            raise ValueError("Kein Claude-Schluessel (im Show-Assistenten eintragen)")
        usage = {}
        try:
            answer = assistant.ask_claude(key, genre_ai.song_request(house, songs, assistant.MODEL), timeout=120.0, opener=self.claude_opener, usage=usage)
        finally:
            cost = assistant.cost_usd(usage)
            self._add_spent(cost)
        return {"songs": genre_ai.song_apply(house, songs, answer), "cost_usd": round(cost, 4), "spent": self._spent()}

    @staticmethod
    def music_nas_clean(d):
        """NAS-Angaben pruefen: Name oder IP (Buchstaben, Ziffern, Punkt, Bindestrich), MAC aa:bb:cc:dd:ee:ff, Abschaltzeit HH:MM oder leer."""
        import re
        if not isinstance(d, dict):
            raise ValueError("Angaben fehlen")
        host = str(d.get("host") or "").strip()
        if host and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}", host):
            raise ValueError("NAS: Name oder IP ungueltig")
        mac = str(d.get("mac") or "").strip().lower().replace("-", ":")
        if mac:
            parts = mac.split(":")
            if len(parts) != 6 or not all(re.fullmatch(r"[0-9a-f]{1,2}", p) for p in parts):
                raise ValueError("NAS: MAC-Adresse ungueltig (zum Beispiel aa:bb:cc:dd:ee:ff)")
            mac = ":".join(p.zfill(2) for p in parts)
        off = str(d.get("off_at") or "").strip()
        if off:
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", off)
            if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
                raise ValueError("NAS: Abschaltzeit bitte als HH:MM")
            off = "%02d:%s" % (int(m.group(1)), m.group(2))
        return {"host": host, "mac": mac, "off_at": off}

    def music_nas_save(self, d):
        """NAS fuer das Spiegeln speichern; der Mac holt die Angaben mit dem Musikordner alle 30 s."""
        self._music_json_write(nas=self.music_nas_clean(d))
        return self.music_conf()

    def music_excl_save(self, lines):
        """Ausgeschlossene Ordner speichern; die Bruecke und der Helfer holen sie mit dem Musikordner alle 30 s."""
        self._music_json_write(excl=self.music_excl_clean(lines))
        return self.music_conf()

    _titles_lock = threading.Lock()

    def titles_kept(self):
        """Titel bereinigen: Lieder, deren Nummer am Anfang zum Titel gehoert ("10 Nackte Friseusen", Wunsch 07.11.2026).
        {Pfad: {"t": Titel, "src": "hand" | "netz" (gibt es laut Internet so) | "nein" (Internet fand ihn nicht so) | "offen" (du willst ihn wieder
        angeboten haben, die Internetsuche fragt nicht neu)}} in
        shows/_titel_behalten.json; aendert sich der Titel, kommt das Lied wieder in die Liste."""
        try:
            with open(os.path.join(self.store.base, "_titel_behalten.json"), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {}
        out = {}
        for k, v in (d.items() if isinstance(d, dict) else ()):
            if isinstance(v, str):
                v = {"t": v, "src": "hand"}
            if isinstance(v, dict) and v.get("src") in ("hand", "netz", "nein", "offen"):
                out[str(k)[:600]] = {"t": str(v.get("t") or "")[:300], "src": v["src"]}
        return out

    def title_keep(self, path, title, keep=True, src="hand"):
        """Titel "so lassen" merken (keep=False: wieder vergessen); src "netz"/"nein" = Ergebnis der Internetsuche."""
        path, title = str(path or "")[:600], str(title or "")[:300]
        if not path:
            raise ValueError("Pfad fehlt")
        if src not in ("hand", "netz", "nein", "offen"):
            raise ValueError("unbekannte Quelle")
        with self._titles_lock:
            d = self.titles_kept()
            if keep:
                d[path] = {"t": title, "src": src}
            else:
                d.pop(path, None)
            fn = os.path.join(self.store.base, "_titel_behalten.json")
            tmp = fn + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            os.replace(tmp, fn)
        return {"kept": d}

    def marks_from_mac(self, name):
        """Abschnitte, Hotcues, Drops und Energie des zugeordneten Mixxx-Liedes vom Mac holen (music_serve /marks) und wie aus
        einem Deck in der Show ablegen. Fehlt etwas (Mac aus, Lied nicht analysiert), ist das kein Fehler: found=False."""
        doc = self.store.load(name)
        mx = doc.get("mixxx") or {}
        music = self.music_url()
        if not mx.get("title"):
            return {"found": False, "why": "kein Mixxx-Lied zugeordnet"}
        link = self.show.mixxx
        lib = link.library_full() if link is not None and hasattr(link, "library_full") else []
        t, d = _norm(mx["title"]), float(mx.get("dur") or 0)
        cand = [x for x in lib if x.get("path") and _norm(x.get("title")) == t and (not d or abs(float(x.get("dur") or 0) - d) <= 1.0)]
        if not cand:
            return {"found": False, "why": "Lied nicht in der Bibliothek"}
        if not music and self.marks_bulk.get(min(cand, key=lambda x: abs(float(x.get("dur") or 0) - d))["path"]) is None:
            return {"found": False, "why": "Musik-Rechner nicht verbunden"}
        path = min(cand, key=lambda x: abs(float(x.get("dur") or 0) - d))["path"]
        kept = self.marks_bulk.get(path)                   # schon vorab geholt: gleich nehmen, auch ohne Mac
        if kept is not None:
            return {"found": True, "marks": self.store.save_marks(name, kept), "from": "ablage"}
        try:
            with self.mac_opener(music + "/marks?p=" + quote(path, safe=""), timeout=15) as r:
                x = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError):
            return {"found": False, "why": "Analyse am Musik-Rechner nicht da"}
        new = tl.clean_marks({"se": x.get("se") or [], "cu": x.get("cu") or [], "ev": x.get("ev") or [], "en": x.get("en") or [],
                              "lvl": x.get("lvl"), "genre": x.get("genre") or "", "title": x.get("title") or "", "fp": x.get("fp") or ""})
        return {"found": True, "marks": self.store.save_marks(name, new)}

    PV_CACHE = 600

    @staticmethod
    def _pv_clean(x):
        """Wie timeline.clean_marks, aber ohne dessen Grenzen (64 Ereignisse, 32 Abschnitte): beim Vorhoeren eines Mixes von
        2 Stunden sollen die Stellen bis zum Ende reichen (Fehlerbericht 14.11.2026). Nur Zahlen, nur Hauptteile und Drops."""
        if not isinstance(x, dict):
            return None
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        se = [[s[0], round(float(s[1]), 3), round(float(s[2]), 3)] for s in (x.get("se") or [])[:400]
              if isinstance(s, list) and len(s) >= 3 and s[0] == "main" and num(s[1]) and num(s[2])]
        cu = sorted(round(float(c), 3) for c in (x.get("cu") or [])[:36] if num(c) and c >= 0)
        ev = [[e[0], round(float(e[1]), 3), round(float(e[2]), 3)] for e in (x.get("ev") or [])[:2000]
              if isinstance(e, list) and len(e) >= 3 and e[0] == "drop" and num(e[1]) and num(e[2])][:500]
        return {"se": se, "cu": cu, "ev": ev}

    def preview_marks(self, path):
        """Vorhoeren ab der wichtigen Stelle (Wunsch 14.11.2026): Hauptteile, Hotcues und Drops eines Liedes fuer den Einstieg.
        Zuerst die Ablage des Vorab-Laufs (geht ohne Mac), sonst der Musik-Rechner (/marks ohne Fingerabdruck, schnell).
        Gemerkt im Speicher, auch "nichts da" (10 min). Aufs Licht wirkt das nie."""
        path = str(path or "")[:2000]
        if not path:
            return {}
        c = getattr(self, "_pv", None)
        if c is None:
            c = self._pv = {}
        hit = c.get(path)
        if hit and (hit[1] or time.time() - hit[0] < 600):
            return hit[2]
        m = self.marks_bulk.get(path)
        if m is not None and (len(m.get("ev") or []) >= tl.MAX_MARK_EVENTS or len(m.get("se") or []) >= tl.MAX_MARK_SECTIONS):
            kept, m = m, None                              # Ablage gekuerzt (lange Mixe, Fehlerbericht 14.11.2026): lieber vom Mac
        else:
            kept = None
        if m is None:
            music = self.music_url()
            if music:
                try:
                    with self.mac_opener(music + "/marks?nofp=1&p=" + quote(path, safe=""), timeout=8) as r:
                        m = self._pv_clean(json.loads(r.read().decode("utf-8")))
                except (OSError, ValueError):
                    m = None
            m = m or kept
        out = {"se": [s for s in m.get("se") or [] if s[0] == "main"], "cu": m.get("cu") or [],
               "ev": [e for e in m.get("ev") or [] if e[0] == "drop"]} if m else {}
        if len(c) >= self.PV_CACHE:
            c.clear()
        c[path] = (time.time(), bool(m), out)
        return out

    def lyrics_quick(self, name):
        """Liedtext fuer eine neue Show: aus dem Liedtext-Speicher (Vorab-Lauf, ohne Internet), sonst einmal bei LRCLIB.
        Nichts gefunden ist kein Fehler: die Show entsteht trotzdem. Rueckgabe {lyrics, from: cache|lrclib|none}."""
        doc = self.store.load(name)
        mx = doc.get("mixxx") or {}
        title = str(mx.get("title") or doc.get("name") or "")
        dur = float(mx.get("dur") or doc.get("duration") or 0)
        cache = getattr(self.show, "lyric_cache", None)
        e = cache.entry(title, dur) if cache is not None else None
        if e is not None:
            if not (e.get("lines") or e.get("plain")):
                return {"lyrics": None, "from": "none"}       # schon einmal gesucht, nichts gefunden: nicht wieder fragen
            y = {"lines": e["lines"], "plain": e.get("plain") or "", "source": "lrclib", "title": title, "duration": dur}
            return {"lyrics": self.store.save_lyrics(name, y), "from": "cache"}
        try:
            y = ly.fetch(title, dur, opener=self.lyrics_opener)
        except ValueError:
            return {"lyrics": None, "from": "none"}
        if cache is not None:
            cache.store(title, dur, y["lines"], y.get("plain") or "")
        return {"lyrics": self.store.save_lyrics(name, y), "from": "lrclib"}

    def _lib_item(self, path):
        link = self.show.mixxx
        lib = link.library_full() if link is not None and hasattr(link, "library_full") else []
        return next((x for x in lib if x.get("path") == path), {})

    def _lib_path(self, title, dur):
        """Pfad am Mac zu Titel und Laenge (Mixxx-Bibliothek), '' wenn unbekannt."""
        link = self.show.mixxx
        lib = link.library_full() if link is not None and hasattr(link, "library_full") else []
        t, d = _norm(title), float(dur or 0)
        if not t:
            return ""
        cand = [x for x in lib if x.get("path") and _norm(x.get("title")) == t and (not d or abs(float(x.get("dur") or 0) - d) <= 1.5)]
        return min(cand, key=lambda x: abs(float(x.get("dur") or 0) - d))["path"] if cand else ""

    def quick_check(self, title, dur):
        """Hauptpanel: gibt es zum Lied aus Mixxx schon eine Show? Sonst die Angaben fuer Quick (Lied aus der Bibliothek)."""
        if self.index_dirty or not self.index_cache:
            self.index_cache = {e["name"]: e for e in self.store.mixxx_index(self.index_cache)}
            self.index_dirty = False
        t, d = _norm(title), float(dur or 0)
        hit = [e for e in self.index_cache.values() if t and e["title"] and _norm(e["title"]) == t and (not d or abs(e["dur"] - d) <= 1.5)]
        if hit:
            return {"show": max(hit, key=lambda e: e["mtime"])["name"]}
        path = self._lib_path(title, dur)
        if not path:
            return {"show": None, "song": None}
        link = self.show.mixxx
        x = next((x for x in link.library_full() if x.get("path") == path), {})
        with self.stem_bulk.lock:
            fp = self.stem_bulk.fps.get(path)
        stems = bool(fp) and fp in self.store.stems_fps()     # Quick nur mit Spur-Kurven, wie in der Musik-Datenbank (Wunsch von Markus)
        return {"show": None, "stems": stems, "music": self.music_url(), "running": self.engine.loaded,
                "song": {"path": path, "title": x.get("title") or title, "dur": float(x.get("dur") or dur or 0),
                         "artist": x.get("artist") or "", "name": x.get("name") or "", "mp3": path.lower().endswith(".mp3")}}

    def cover(self, path="", show="", title="", dur=0.0):
        """Cover als JPEG-Bytes oder None: zum Pfad am Mac (Musik-Datenbank), zu einer Show (ihre MP3, sonst ihr Mixxx-Lied)
        oder zu Titel und Laenge (Hauptpanel, Lied aus Mixxx)."""
        if show:
            fp = self.store._audio_fp(show)
            img = (self.covers.by_fp(fp) or self.covers.from_mp3(self.store.path(show, "audio.mp3"), fp)) if fp else None
            if img is not None:
                return img                                 # Bild aus der MP3 der Show selbst: geht auch ohne Mac
            try:
                doc = self.store.load(show)
            except (ValueError, OSError):
                return None
            mx = doc.get("mixxx") or {}
            title, dur = mx.get("title") or "", mx.get("dur") or doc.get("duration") or 0
        if not path:
            path = self._lib_path(title, dur)
        return self.covers.for_path(path) if path else None

    def radio_op(self, op, d):
        r = self.radio
        if op == "radio_report":                  # Helfer: Zustand und Titelfeld
            return r.report(d)
        if op == "radio_here":                    # Browser, der selbst spielt (22.11.2026): Zustand, Eingang Line-In
            out = r.here_report(d)
            self._line_watch()
            return dict(out, line=self.line_info())
        if op == "radio_countries":
            return {"countries": r.countries()}
        if op == "radio_tags":
            return {"tags": r.tags()}
        if op == "radio_search":
            return {"stations": r.search(d.get("cc") or "", d.get("tag") or "", d.get("q") or "")}
        if op == "radio_slot_set":
            r.slot_set(d.get("n"), d.get("st"))
        elif op == "radio_slot_clear":
            r.slot_clear(d.get("n"))
        elif op == "radio_fav":
            r.fav(d.get("st"), bool(d.get("on")))
        elif op == "radio_play":
            r.play(d.get("st"), d.get("slot"), here=bool(d.get("here")), dev=d.get("dev") or "")
        elif op == "radio_stop":
            r.stop()
        elif op == "radio_vol":
            r.volume(d.get("v") if isinstance(d.get("v"), (int, float)) else 0.8)
        else:
            raise ValueError("unbekannter Befehl")
        return r.state()

    # ---- Eingang Line-In, solange ein Browser das Radio selbst spielt (Fernseher am Line-In, 22.11.2026) ----------
    def line_info(self):
        sw = getattr(self, "line_sw", None)
        return {"cur": str(getattr(getattr(self.show, "src", None), "dev_name", "") or ""), "auto": bool(sw and sw.get("to")),
                "prev": (sw or {}).get("prev") or "", "err": getattr(self, "line_err", "")}

    def line_device(self):
        """Der Line-In am Licht-Rechner: eine echte Soundkarte (USB zuerst), nie der Ton vom Musik-Rechner."""
        fn = getattr(getattr(self.show, "src", None), "list_devices", None)
        devs = [x for x in (fn() if fn else []) if x.get("index", -1) >= 0]
        if not devs:
            return ""
        rank = lambda x: (0 if "usb" in x["name"].lower() else 1 if "hw:" in x["name"].lower() else 2, x["index"])
        return sorted(devs, key=rank)[0]["name"]

    def _line_watch(self):
        """Waechter-Faden einmal starten: schaltet auf Line-In und nach dem Ende (auch Seite zu) zurueck."""
        if getattr(self, "line_thread", None) is None:
            self.line_thread = threading.Thread(target=self._line_loop, daemon=True)
            self.line_thread.start()
        self.line_tick()

    def _line_loop(self):
        while True:
            time.sleep(1.0)
            try:
                self.line_tick()
            except Exception:                         # noqa: BLE001  Waechter darf nie sterben
                pass

    def line_tick(self):
        src = getattr(self.show, "src", None)
        fn = getattr(src, "configure", None)
        if fn is None:                                # Simulator: kein Eingang
            return
        with self.line_lock:
            sw = getattr(self, "line_sw", None)
            cur = str(getattr(src, "dev_name", "") or "")
            if self.radio.here_line():
                if sw is None:
                    to = self.line_device()
                    if not to:
                        self.line_err = "Kein Line-In am Light-Butler gefunden"
                        self.line_sw = {"prev": "", "to": ""}
                    elif cur == to:
                        self.line_sw = {"prev": "", "to": to}          # war schon Line-In: danach nichts zurueckstellen
                    else:
                        try:
                            fn(device=to)
                            self.line_sw, self.line_err = {"prev": cur, "to": to}, ""
                            self.show.note = "Internetradio am Geraet: Eingang " + to
                        except ValueError as e:
                            self.line_err = str(e)[:120]
                            self.line_sw = {"prev": "", "to": ""}
            elif sw is not None:
                self.line_sw = None
                if sw.get("prev") and cur == sw.get("to"):           # nur zurueck, wenn niemand inzwischen anders gewaehlt hat
                    try:
                        fn(device=sw["prev"])
                        self.show.note = "Internetradio am Geraet beendet: Eingang wieder " + sw["prev"]
                    except ValueError as e:
                        self.line_err = str(e)[:120]

    def matrix_song_text(self, song):
        """Pixel-Matrix, Laufschrift: Interpret, Titel, Album zum laufenden Lied (Bibliothek, Internetradio oder Show)."""
        rs = song.get("radio")
        if rs:
            return {"artist": rs.get("artist") or "", "title": rs.get("title") or "", "album": ""}
        if song.get("path"):                       # Musik-DB im Browser: der Pfad ist bekannt
            x = self._lib_item(song["path"])
            return {"artist": x.get("artist") or song.get("artist") or "", "title": x.get("title") or song.get("title") or "",
                    "album": x.get("album") or song.get("album") or ""}
        title, dur = song.get("title") or "", song.get("dur") or 0
        if song.get("show"):
            try:
                mx = (self.store.load(song["show"]).get("mixxx") or {})
                title, dur = mx.get("title") or song["show"], mx.get("dur") or 0
            except (ValueError, OSError):
                title = song["show"]
        path = self._lib_path(title, dur) if title else ""
        link = self.show.mixxx
        lib = link.library_full() if path and link is not None and hasattr(link, "library_full") else []
        x = next((x for x in lib if x.get("path") == path), {})
        return {"artist": x.get("artist") or "", "title": x.get("title") or title, "album": x.get("album") or ""}

    def matrix_pictures(self, song):
        """Pixel-Matrix (wled_matrix.py): Bilder zum laufenden Lied, nacheinander [("titel"|"interpret"|"album", JPEG)].
        Nur, was es schon gibt (Cover der Lieder am Pi oder vom Musik-Rechner, Interpreten-Bild); ein gleiches Bild nur einmal.
        Laeuft im eigenen Faden der Matrix, nie im Takt der Show."""
        out = []

        def add(kind, img):
            if img and not any(img == x[1] for x in out):
                out.append((kind, bytes(img)))
        if song.get("show"):
            add("titel", self.cover(show=song["show"]))
        rs = song.get("radio")
        if rs:                                     # Internetradio: Cover (iTunes), Interpret (falls in der Sammlung), Senderlogo
            add("titel", self.radio.cover(rs.get("artist") or "", rs.get("title") or ""))
            name = artists_mod.main_name(rs.get("artist") or "")
            for k in dict.fromkeys(k for k in (artists_mod.key(name), artists_mod.key(artists_mod.split_first(name)[0])) if k):
                pa = self.artists.path(k)
                if os.path.isfile(pa):
                    with open(pa, "rb") as f:
                        add("interpret", f.read())
                    break
            add("sender", self.radio.logo(rs.get("uuid") or ""))
            return out
        path = song.get("path") or (self._lib_path(song.get("title") or "", song.get("dur") or 0) if song.get("title") else "")
        if path and not out:
            add("titel", self.covers.for_path(path))
        link = self.show.mixxx
        lib = link.library_full() if link is not None and hasattr(link, "library_full") else []
        x = next((x for x in lib if x.get("path") == path), {}) if path else {}
        name = artists_mod.main_name(x.get("artist") or "")
        for k in dict.fromkeys(k for k in (artists_mod.key(name), artists_mod.key(artists_mod.split_first(name)[0])) if k):
            p = self.artists.path(k)
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    add("interpret", f.read())
                break
        if path and str(x.get("album") or "").strip():
            first = (self.albums.songs(self.albums.key_of_path(path)).get("songs") or [{}])[0].get("path")
            if first:
                add("album", self.covers.for_path(first))
        return out

    PROG_FILE = "_programme_stick.json"

    def programs_report(self, d):
        """Meldung des Helfers: wann die Pakete und Handbuecher auf den Stick kamen. Nur Anzeige, gepruefte kurze Felder."""
        def txt(v, n=200):
            return str(v or "")[:n]
        rep = {"t": int(self.now()), "v": txt(d.get("v"), 40), "dir": txt(d.get("dir"), 300), "backup": txt(d.get("backup"), 120),
               "files": [txt(x, 120) for x in (d.get("files") or [])[:20] if isinstance(x, str)],
               "mb": round(float(d.get("mb") or 0), 1) if isinstance(d.get("mb"), (int, float)) else 0.0,
               "new": bool(d.get("new")), "err": txt(d.get("err"), 300)}
        p = os.path.join(self.store.base, self.PROG_FILE)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)
        return {"ok": True}

    def programs_state(self):
        try:
            with open(os.path.join(self.store.base, self.PROG_FILE), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def fav_conf(self):
        """Schalter der Favoriten: Herz im Hauptpanel, Herz auch in die MP3 (Bewertung) schreiben."""
        cfg = self.show.cfg
        return {"panel": cfg["fav_panel"] > 0.5, "mp3": cfg["fav_mp3"] > 0.5}

    def fav_now(self, title, dur):
        """Hauptpanel: Herz zum Lied aus Mixxx (Pfad und Stand)."""
        path = self._lib_path(title, dur) if title else ""
        st = self.favs.state() if path else {}
        fav = 2 if path in st.get("song", []) else 1 if path in st.get("ind", []) else 0
        return dict(self.fav_conf(), path=path, fav=fav, music=self.music_url())

    def music_url(self):
        """Vorhoer-Server am Mac (music_serve.py), nur solange die Bruecke verbunden ist; sonst ''."""
        link, st = self.show.mixxx, self.show.mx or {}
        alive = st.get("connected") or (hasattr(link, "mac_alive") and link.mac_alive())   # Mixxx-Bruecke oder Helfer
        if alive and getattr(link, "mac_ip", "") and getattr(link, "music_port", 0):
            return f"http://{link.mac_ip}:{link.music_port}"
        return ""

    CLAIM_S = 20 * 60.0          # so lange gilt eine Anmeldung "ich rechne diese MP3" (danach darf ein anderer Rechner)

    def stems_claim(self, name, who, take=True):
        """Mac und Windows-PC teilen sich die Pegelkurven: vor dem Rechnen meldet ein Rechner die MP3 an. ok=False, wenn
        ein anderer sie seit weniger als CLAIM_S rechnet. take=False gibt die eigene Anmeldung wieder frei."""
        fp = self.store._audio_fp(name)
        if not fp:
            raise ValueError("Keine MP3 in dieser Show")
        t = time.time()
        for k, c in list(self.stem_claims.items()):
            if t - c[1] > self.CLAIM_S:
                del self.stem_claims[k]
        cur = self.stem_claims.get(fp)
        if not take:
            if cur and cur[0] == who:
                del self.stem_claims[fp]
            return {"ok": True}
        if cur and cur[0] != who:
            return {"ok": False, "by": cur[0], "since_s": round(t - cur[1])}
        self.stem_claims[fp] = (who, t, name)
        return {"ok": True}

    def stems_busy(self, fp):
        """Wer rechnet gerade die Kurven zu dieser MP3 (Show oder Vorab-Lauf)? '' = niemand."""
        t = time.time()
        c = self.stem_claims.get(fp)
        if c and t - c[1] < self.CLAIM_S:
            return c[0]
        return self.stem_bulk.busy(fp) if fp else ""

    def stems_activity(self):
        """Fuer den Showmanager: was gerade gerechnet wird (Shows und Vorab-Lauf) und der Stand des Vorab-Laufs."""
        t = time.time()
        work = [{"who": c[0], "title": c[2] if len(c) > 2 else "", "kind": "show", "since_s": round(t - c[1])}
                for c in self.stem_claims.values() if t - c[1] < self.CLAIM_S]
        b = self.stem_bulk.status()
        work += [dict(w, kind="vorab") for w in b["work"]]
        return {"work": work, "bulk": {k: b[k] for k in ("on", "done", "total", "workers", "music", "eta_h")}}

    def stems_max_s(self):
        """Laengengrenze fuer Pegelkurven in Sekunden (Einstellung sm_stems_max_min, 0 = keine Grenze)."""
        try:
            return max(0.0, float(self.show.cfg["sm_stems_max_min"])) * 60.0
        except (KeyError, TypeError, ValueError, AttributeError):
            return stems_bulk.MAX_S

    def music_state(self):
        """Stand der Liedliste fuer das Lamperl der Musik-Datenbank (Wunsch 11.11.2026), ohne die Lieder selbst: verbunden,
        komplett, [angekommen, alle, verloren] und v = Stand (aendert sich mit jedem Stueck: die Seite holt die Liste dann neu)."""
        link = self.show.mixxx
        st = self.show.mx or {}
        alive = bool(st.get("connected")) or bool(link is not None and hasattr(link, "mac_alive") and link.mac_alive())
        complete = link.library_complete() if link is not None and hasattr(link, "library_complete") else False
        res = {"connected": alive, "complete": complete, "v": int(getattr(link, "lib_ver", 0) or 0) if link is not None else 0}
        if not complete and link is not None and hasattr(link, "library_progress"):
            res["prog"] = link.library_progress()
        return res

    def music_list(self):
        """Seite /musik: alle Lieder der Mixxx-Bibliothek mit Liedtext (aus dem Cache am Pi) und Show (aus shows/). Nur Anzeige."""
        link = self.show.mixxx
        lib = link.library_full() if link is not None and hasattr(link, "library_full") else []
        st = self.show.mx or {}
        try:
            ly_keys = self.show.lyric_cache.keys() if self.show.lyric_cache is not None else {}
        except Exception:                                      # noqa: BLE001
            ly_keys = {}
        shows, loose = {}, []
        if self.index_dirty or not self.index_cache:
            self.index_cache = {e["name"]: e for e in self.store.mixxx_index(self.index_cache)}
            self.index_dirty = False
        stems = {}                                                 # Fingerabdruck der MP3 -> Pegelkurven (Bass, Stimme, ...) am Pi vorhanden
        for e in self.index_cache.values():
            fp = str(e.get("fp") or "")
            if fp and fp not in stems:
                stems[fp] = os.path.isfile(self.store._stems_path(fp))
            has = bool(fp and stems[fp])
            if e.get("title"):
                shows.setdefault(_norm(e["title"]), []).append((float(e.get("dur") or e.get("duration") or 0), e["name"], bool(e.get("lyr")), has))
            elif float(e.get("duration") or 0) > 0:          # Show ohne gewaehltes Mixxx-Lied (per MP3 angelegt): Laenge der MP3 und Name
                loose.append((float(e["duration"]), e["name"], bool(e.get("lyr")), _norm(e["name"]), has, _core(e["name"])))
        have_fps = self.store.stems_fps()                          # Kurven aus dem Vorab-Lauf: Pfad -> Fingerabdruck (ohne Show)
        with self.stem_bulk.lock:
            bulk_fps = dict(self.stem_bulk.fps)
        cv_idx = dict(self.covers.index) if getattr(self, "covers", None) is not None else {}   # Pfad -> Fingerabdruck oder '' (kein Cover)
        out = []
        for r in lib:
            d = int(round(r["dur"]))
            name = ly.LyricCache.key(r["title"], r["dur"]).rsplit("|", 1)[0]
            lyr = 0
            for x in (d, d - 1, d + 1):
                n = ly_keys.get(f"{name}|{x}")
                if n is not None:
                    lyr = 2 if n > 0 else 1                        # 2 = Zeilen mit Zeiten, 1 = gesucht, nur Text oder nichts
                    break
            sh = [(nm, lq, hs) for du, nm, lq, hs in shows.get(_norm(r["title"]), []) if not du or abs(du - r["dur"]) <= 1.5]
            if loose:
                t, n, cn = _norm(r["title"]), _norm(r["name"]), _core(r["name"])
                sh += [(nm, lq, hs) for du, nm, lq, nn, hs, cs in loose
                       if abs(du - r["dur"]) <= 1.5 and ((len(cn) >= 4 and cn == cs) or (len(n) >= 4 and n in nn)
                                                        or re.search(r"(?<!\w)" + re.escape(nn) + r"(?!\w)", t))]   # Showname als ganzes Wort im Titel
            if any(lq for _, lq, _h in sh):
                lyr = 2                                            # Liedtext in der Showdatei
            names = sorted({nm for nm, _l, _h in sh})
            out.append({**r, "lyr": lyr, "show": names[0] if names else "", "shows": names,
                        "stems": int(any(hs for _n, _l, hs in sh) or bulk_fps.get(r.get("path") or "") in have_fps),
                        "cv": (1 if cv_idx.get(r.get("path") or "") else 0) if (r.get("path") or "") in cv_idx else -1,
                        "cvv": self.covers.mtime(cv_idx.get(r.get("path") or "")) if getattr(self, "covers", None) is not None else 0})   # Bild-Stand   # Cover: 1 ja, 0 keins, -1 noch nicht geprueft
        self.stars.settle(lib)                                       # Mixxx hat die Sterne von hier uebernommen: Eintrag weg
        out = self.stars.apply(out)
        complete = link.library_complete() if link is not None and hasattr(link, "library_complete") else False
        music = self.music_url()
        alive = bool(st.get("connected")) or bool(link is not None and hasattr(link, "mac_alive") and link.mac_alive())   # auch der Helfer
        res = {"connected": alive, "complete": complete, "n": len(out), "tracks": out, "music": music,
               "v": int(getattr(link, "lib_ver", 0) or 0) if link is not None else 0,
               "root": self.music_conf()["root"]}             # Musikordner aus den Einstellungen: die Seite kuerzt die Ordner darum
        if not complete and link is not None and hasattr(link, "library_progress"):
            res["prog"] = link.library_progress()          # [angekommen, alle]: Fortschrittsbalken, solange der Mac schickt
        return res             # Musikordner aus den Einstellungen: die Seite kuerzt die Ordner darum

    def marks(self, name):
        """Abschnitte und Cues zur Show. Liegt ihr Lied in einem Deck, kommen sie von dort und bleiben in der Showdatei, auch ohne Mixxx."""
        doc = self.store.load(name)
        audio = self.store.path(name, "audio.mp3")
        fp = audio_fingerprint(audio) if os.path.isfile(audio) else ""
        m = doc.get("mixxx") or {}
        link, old = self.show.mixxx, doc.get("marks")
        decks = link.deck_marks() if link is not None and hasattr(link, "deck_marks") else []
        hit = [x for x in decks if fp and x["fp"] == fp]
        if not hit and m.get("title"):
            hit = [x for x in decks if _norm(x["title"]) == _norm(m["title"]) and abs(x["du"] - m.get("dur", 0.0)) <= 1.0]
        if hit:
            x = hit[0]
            same = old and old["fp"] == x["fp"] and old["title"] == x["title"]   # Analyse noch nicht fertig: Vorhandenes behalten
            new = tl.clean_marks({"se": x["se"] or (old["se"] if same else []), "cu": x["cu"] or (old["cu"] if same else []),
                                  "ev": x["ev"] or (old["ev"] if same else []), "en": x["en"] or (old["en"] if same else []),
                                  "lvl": x["lvl"], "genre": x["genre"], "title": x["title"], "fp": x["fp"]})
            if new != old:
                old = self.store.save_marks(name, new)
        return {"marks": old, "warn": bool(old and old["fp"] and fp and old["fp"] != fp)}

    # ---- Show-Assistent ---------------------------------------------------------------------------------------
    def _claude_key(self):
        try:
            with open(self.key_path, encoding="utf-8") as f:
                return str(json.load(f).get("key") or "")
        except (OSError, ValueError, AttributeError):
            return ""

    def _set_claude_key(self, key):
        """Der Schluessel wird nur geschrieben, nie an das Panel zurueckgegeben."""
        key = str(key or "").strip()
        if not key:
            if os.path.exists(self.key_path):
                os.unlink(self.key_path)
            return
        if not re.match(r"^[A-Za-z0-9_-]{20,300}$", key):
            raise ValueError("Das sieht nicht wie ein API-Schluessel aus")
        fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"key": key}, f)

    def _spent(self):
        """Geschaetzte Kosten seit Beginn: {"usd", "calls"}. Keine Abrechnung und kein Guthaben, nur die Summe aus den Antworten."""
        try:
            with open(self.spent_path, encoding="utf-8") as f:
                d = json.load(f)
            return {"usd": float(d.get("usd", 0.0)), "calls": int(d.get("calls", 0))}
        except (OSError, ValueError, TypeError, AttributeError):
            return {"usd": 0.0, "calls": 0}

    def _add_spent(self, cost):
        if cost <= 0:
            return
        s = self._spent()
        s["usd"], s["calls"] = round(s["usd"] + cost, 4), s["calls"] + 1
        tmp = self.spent_path + ".neu"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(s, f)
            os.replace(tmp, self.spent_path)
        except OSError as e:                          # nur eine Anzeige: der Vorschlag entsteht trotzdem
            print(f"Claude-Kosten nicht gespeichert: {type(e).__name__}", flush=True)

    def saved_room(self):
        """Raumplan, nur wenn Markus ihn gespeichert hat: ein Vorschlag aus der Beschreibung zaehlt nicht."""
        if not os.path.isfile(self.room_path):
            return None
        r = rm.load(self.room_path, {x["name"] for x in rm.devices(self.show.rig)})
        return None if r.get("guess") else rm.lights_only(r)    # Anzeigen (Matrix, API-Anzeige) gehen den Assistenten nichts an

    def _lib_meta(self, doc):
        """Genre und Energiestufe fuer den Assistenten: aus dem Mixxx-Deck (marks), sonst aus der Bibliothek ueber Titel und
        Laenge des zugeordneten Liedes (Fehlerbericht 06.11.2026: Shows, deren Lied nie in einem Deck lag, hatten kein Genre).
        Gibt eine Kopie zurueck, die Showdatei bleibt unveraendert."""
        m = dict(doc.get("marks") or {})
        mx = doc.get("mixxx") or {}
        if m.get("genre") or not mx.get("title"):
            return doc
        link = self.show.mixxx
        lib = link.library_full() if link is not None and hasattr(link, "library_full") else []
        t, d = _norm(mx["title"]), float(mx.get("dur") or 0)
        cand = [x for x in lib if _norm(x.get("title")) == t and (not d or abs(float(x.get("dur") or 0) - d) <= 1.0) and (x.get("genre") or x.get("lvl"))]
        if not cand:
            return doc
        best = min(cand, key=lambda x: abs(float(x.get("dur") or 0) - d))
        m["genre"] = best.get("genre") or ""
        if not m.get("lvl"):
            m["lvl"] = best.get("lvl") or None
        return dict(doc, marks=m)

    def assist_info(self, name):
        """Was das Fenster des Assistenten anzeigt, bevor etwas entsteht."""
        doc = self._lib_meta(self.store.load(name))
        song = assistant.song_info(doc, self.store.load_peaks(name), self.store.load_stems(name))
        return {"stems": bool(song["sb"]), "room": self.saved_room() is not None, "title": song["title"], "genre": song["genre"], "lvl": song["lvl"], "source": song["source"], "sections": len(song["secs"]), "cues": len(song["cues"]), "hits": len(song["hits"]),
                "style": self.show.gstyles.style(song["genre"]) or "", "styles": assistant.STYLE_NAMES, "lyrics_lines": sum(1 for x in (doc.get("lyrics") or {}).get("lines") or [] if x[1]), "lyrics_text": bool((doc.get("lyrics") or {}).get("plain")), "has_key": bool(self._claude_key()), "spent": self._spent(), "nano_effects": len(self.nano_effects()),
                "strobe": bool(self.show.strobe), "laser_allowed": self.show.cfg["sm_laser"] > 0.5, "fog_allowed": self.show.cfg["sm_fog"] > 0.5}

    def _free_name(self, name):
        base = re.sub(r" \(Vorschlag( \d+)?\)$", "", name)[:44]
        for i in range(1, 1000):
            new = f"{base} (Vorschlag{'' if i == 1 else ' ' + str(i)})"
            if not self.store.exists(new) and not os.path.exists(self.store.dir(new)):
                return new
        raise ValueError("Zu viele Vorschlaege, bitte alte loeschen")

    def assist(self, d):
        """Claude entwirft: dauert Minuten, laeuft im Hintergrund, das Fenster fragt nach (assist_job). Sonst sofort."""
        if not d.get("design"):
            return self._assist(d)
        if self.job and self.job["state"] == "running":
            raise ValueError("Claude arbeitet schon an einem Vorschlag")
        self.job = job = {"state": "running", "chars": 0, "t": self.now(), "result": None, "error": ""}

        def work():
            try:
                job["result"] = self._assist(d, job)
                job["state"] = "done"
            except Exception as e:                    # auch ohne Show-Ergebnis muss das Fenster einen Grund bekommen
                job["error"], job["state"] = str(e)[:200] if isinstance(e, ValueError) else f"Vorschlag ging nicht ({type(e).__name__})", "error"
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        if self.job_sync:
            thread.join()
        return {"job": True}

    def assist_job(self):
        j = self.job or {"state": "none"}
        return {k: j.get(k) for k in ("state", "chars", "result", "error")}

    def _assist(self, d, job=None):
        """Neue Kopie der Show mit Vorschlag. Die Show selbst bleibt unberuehrt. Claude ist ein Zusatz: scheitert es, gilt die Offline-Regie."""
        name = d.get("name")
        doc = self._lib_meta(self.store.load(name))
        opts = {"style": d.get("style") or self.show.gstyles.style((doc.get("marks") or {}).get("genre")) or "", "wild": d.get("wild", 0.5),
                "seed": d.get("seed") if d.get("seed") is not None else int(time.time()),
                "ambient": bool(d.get("ambient")), "effects": [e["name"] for e in self.nano_effects()] if d.get("nano_fx", True) else [], **{k: bool(d.get(k, True)) for k in ("laser", "fog", "strobe", "move")}}
        if opts["style"] not in assistant.STYLE_NAMES:
            opts["style"] = ""
        note, used, usage = "", False, {}
        opts["panel_scenes"] = self.panel_scenes()
        want_claude = d.get("claude") or d.get("design")
        key = self._claude_key() if want_claude else ""
        if want_claude and not key:
            note = "Kein Claude-Schluessel hinterlegt, der Vorschlag ist offline entstanden."

        def refine(plan, song):
            nonlocal note, used
            if not key or d.get("design"):
                return plan
            try:
                answer = assistant.ask_claude(key, assistant.claude_request(plan, song, opts, d.get("wish")), opener=self.claude_opener, usage=usage)
            except ValueError as e:
                note = f"{e}. Der Vorschlag ist offline entstanden."
                return plan
            used = True
            note = str(answer.get("note") or "")[:400]
            return assistant.apply_claude(plan, answer)

        peaks = self.store.load_peaks(name)
        try:
            new, plan, song = assistant.suggest(doc, self.meta(), opts, peaks, refine, self.store.load_stems(name), self.saved_room())
        except Exception as e:                                    # das Panel soll den Grund zeigen, nicht nur eine abgerissene Verbindung
            print(f"Show-Assistent: {type(e).__name__}: {e}", flush=True)
            raise ValueError(f"Vorschlag ging nicht ({type(e).__name__})") from None
        if key and d.get("design"):
            meta = self.meta()
            try:
                answer = assistant.stream_claude(key, assistant.design_request(doc, meta, song, opts, d.get("wish"), d.get("lyrics")),
                                                 on_chars=(lambda n: job.__setitem__("chars", n)) if job else None, opener=self.claude_opener, usage=usage)
                tracks, dropped = assistant.apply_design(doc, answer, meta, song, opts)
                new = dict(doc, tracks=tracks, scene_clips=[], scenes=[])
                used = True
                note = str(answer.get("note") or "")[:600] + (f" ({dropped} unpassende Eintraege verworfen.)" if dropped else "") + (" Das Effektband hatte Claude vergessen, es spielt jetzt an Drops und Cues." if answer.get("_band_filled") else "")
            except ValueError as e:
                note = f"{e}. Der Vorschlag ist offline entstanden."
        cost = assistant.cost_usd(usage)
        self._add_spent(cost)
        base = self.store.load(name)                              # Genre aus der Bibliothek nur fuer den Vorschlag, nicht in die Kopie
        if base.get("marks"):
            new = dict(new, marks=base["marks"])
        else:
            new = {k: v for k, v in new.items() if k != "marks"}
        # Noch leere Show (keine Spuren, keine Szenen-Clips) und im Editor nichts Ungespeichertes: der Vorschlag kommt direkt
        # hinein, statt eine weitere Kopie anzulegen, die man danach loeschen muesste (Wunsch von Markus, 06.11.2026)
        replaced = is_empty_show(base) and not d.get("keep_copy")
        if replaced:
            target = name
        else:
            target = self._free_name(name)
            self.store.copy(name, target)
        self.store.save(target, dict(new, name=target), fixtures=fm.fixture_list(self.show.rig))
        self.index_dirty = True
        return {"show": target, "replaced": replaced, "source": song["source"], "pieces": len(plan), "claude": used, "design": bool(used and d.get("design")), "note": note, "cost_usd": round(cost, 3), "spent": self._spent()}

    # ---- Auto-DJ ------------------------------------------------------------------------------------------------
    def _library(self):
        link = self.show.mixxx
        return link.library_full() if link is not None and hasattr(link, "library_full") else []

    def autodj_op(self, d):
        """Auto-DJ: Playlist nach Regeln oder mit Claude, gemerkte Playlists in shows/_autodj.json. Nichts davon wirkt aufs Licht."""
        op = d.get("op")
        saved = autodj.Saved(os.path.join(self.store.base, "_autodj.json"))
        if op == "autodj_info":
            genres, kl = {}, {}
            for t in self._library():
                g = str(t.get("genre") or "").strip()
                if g:
                    genres[g] = genres.get(g, 0) + 1
                for k, names in (("L", t.get("lists") or ()), ("K", t.get("crates") or ()), ("G", autodj.groups_of(t))):   # Kisten und Listen aus Mixxx, Gruppen aus dem Tag
                    for n in names:
                        kl[(k, n)] = kl.get((k, n), 0) + 1
            top = sorted(genres.items(), key=lambda x: -x[1])[:80]
            crates = sorted(kl.items(), key=lambda x: ({"G": 0, "L": 1}.get(x[0][0], 2), x[0][1].lower()))[:160]   # Gruppen, Listen, Kisten
            return {"genres": [[g, n] for g, n in top], "crates": [[k + ":" + n, n, k, c] for (k, n), c in crates], "has_key": bool(self._claude_key()), "spent": self._spent(),
                    "music": self.music_url(), "saved": saved.list(), "n": len(self._library())}
        if op == "autodj_list":
            return {"saved": saved.list()}
        if op == "autodj_load":
            return saved.get(d.get("name"))
        if op == "autodj_save":
            return {"saved": saved.save(d.get("name"), d, self.now())}
        if op == "autodj_delete":
            return {"saved": saved.delete(d.get("name"))}
        if op != "autodj_plan":
            raise ValueError("Unbekannter Befehl")
        wish = d.get("wish") if isinstance(d.get("wish"), dict) else {}
        try:
            seed = int(d.get("seed") or 0)
        except (TypeError, ValueError):
            seed = 0
        lib = self._library()
        if not lib:
            raise ValueError("Keine Lieder: die Musik-Datenbank ist leer (Mixxx-Bruecke oder Helfer am Musik-Rechner noch nicht verbunden)")
        note, used, cost = "", False, 0.0
        picks = why = None
        if d.get("claude"):
            key = self._claude_key()
            if not key:
                note = "Kein Claude-Schluessel (im Show-Assistenten eintragen). Die Playlist ist nur nach Regeln entstanden."
            else:
                cands = autodj.candidates(lib, wish.get("genres") or "", int(wish.get("e_lo") or 4), int(wish.get("e_hi") or 8),
                                          exclude=wish.get("exclude") or (), xmas=autodj.wants_xmas(wish))
                pool = autodj.claude_pool(cands, wish.get("e_lo"), wish.get("e_hi"), seed)
                if not pool:
                    raise ValueError("Keine passenden Lieder (Genre oder Energie zu eng?)")
                usage = {}
                try:
                    answer = assistant.ask_claude(key, autodj.claude_request(pool, wish, assistant.MODEL), timeout=180.0,
                                                  opener=self.claude_opener, usage=usage)
                    picks, why, note = autodj.apply_claude(pool, answer)
                    used = bool(picks)
                    if not picks:
                        note = "Claude hat keine Lieder aus der Liste gewaehlt. Die Playlist ist nur nach Regeln entstanden."
                except ValueError as e:
                    note = f"{e}. Die Playlist ist nur nach Regeln entstanden."
                cost = assistant.cost_usd(usage)
                self._add_spent(cost)
        favw = self.favs.weight(lib) if autodj.fav_level(wish) else None   # Favoriten bevorzugen (Wunsch 14.11.2026)
        res = autodj.plan(lib, wish, seed, claude_picks=picks, why=why, favw=favw)
        if not res["items"]:
            raise ValueError("Keine passenden Lieder (Genre oder Energie zu eng?)")
        return dict(res, note=note, claude=used, cost_usd=round(cost, 3), spent=self._spent(), music=self.music_url())

    def op(self, d):
        """Ein Befehl aus dem Panel. Rueckgabe: Daten fuer die Antwort."""
        op = d.get("op")
        if op in ("create", "copy", "rename", "delete", "save"):
            self.index_dirty = True
        st, en, now = self.store, self.engine, self.now()
        if op == "create":
            doc = st.create(d.get("name"))
            if d.get("title"):                     # Musik-Datenbank: Show gleich dem Lied aus Mixxx zuordnen
                doc["mixxx"] = {"on": True, "title": str(d["title"])[:120], "dur": float(d.get("dur") or 0)}
                doc = st.save(d.get("name"), doc)
            return {"doc": doc}
        if op == "copy":
            return {"doc": st.copy(d.get("name"), d.get("new"))}
        if op == "rename":
            doc = st.rename(d.get("name"), d.get("new"))
            if self.current == d.get("name"):
                self.current = doc["name"]
            return {"doc": doc}
        if op == "autodj_feed":                   # Auto-DJ spielt: Decks und Plan wie die Mixxx-Bruecke (Licht folgt dem Auto-DJ)
            link = self.show.mixxx
            if link is None or not hasattr(link, "feed_autodj"):
                raise ValueError("Der Mixxx-Empfang am Light-Butler ist aus (show.conf ohne --no-mixxx starten)")
            return {"n": link.feed_autodj(d.get("msgs"))}
        if op and str(op).startswith("autodj_"):     # Auto-DJ (Seite /musik/autodj): Playlist erstellen und merken
            return self.autodj_op(d)
        if op == "trash_list":                    # Papierkorb der Shows (Seite Shows)
            return {"items": st.trash_list()}
        if op == "trash_restore":
            self.index_dirty = True
            return {"name": st.trash_restore(d.get("entry")), "items": st.trash_list()}
        if op == "trash_delete":                  # endgueltig: ein Eintrag oder alle (Rueckfrage auf der Seite)
            if d.get("all") is True:
                n = st.trash_delete(None)
            elif d.get("entry"):
                n = st.trash_delete(str(d["entry"]))
            else:
                raise ValueError("Welcher Eintrag?")
            return {"deleted": n, "items": st.trash_list()}
        if op == "delete":
            if self.current == d.get("name") and en.loaded:
                raise ValueError("Diese Show laeuft gerade")
            st.delete(d.get("name"))
            return {}
        if op == "save":
            doc = st.save(d.get("name"), d.get("doc"), fixtures=fm.fixture_list(self.show.rig), patterns=d.get("patterns", []))
            return {"doc": doc, "warnings": en.load(doc)}
        if op == "marks":
            return self.marks(d.get("name"))
        if op == "lyrics_fetch":                # nur auf Knopfdruck: braucht Internet, Titel und Interpret gehen an LRCLIB
            doc = st.load(d.get("name"))
            title = str(d.get("title") or (doc.get("marks") or {}).get("title") or (doc.get("mixxx") or {}).get("title") or doc.get("name") or "")
            return {"lyrics": st.save_lyrics(d.get("name"), ly.fetch(title, float(doc.get("duration") or 0), opener=self.lyrics_opener))}
        if op == "marks_bulk":                    # Cue-Punkte aller Lieder vorab vom Mac (Seite Statistik)
            return self.marks_bulk.start() if d.get("on") else self.marks_bulk.stop()
        if op == "marks_restore":                 # Zurueckspielen aus der Sicherung am Stick
            self.marks_bulk.restore(d.get("f"), d.get("data"))
            return {}
        if op == "marks_bulk_status":
            return self.marks_bulk.status()
        if op == "mixxx_once":                    # Quick im Hauptpanel: die neue Show einmal mit dem laufenden Lied aus Mixxx starten
            mx = self.show.mx or {}
            if not mx.get("title"):
                raise ValueError("Kein Lied aus Mixxx")
            self.index_dirty = True
            self.mx_block, self.mx_seen = None, None
            self.mx_once = _norm(mx.get("title"))
            return {"ok": True}
        if op == "covers_bulk":                   # Cover aller Lieder vorab vom Mac (Seite Statistik)
            return self.covers.start() if d.get("on") else self.covers.stop()
        if op == "covers_bulk_status":
            return self.covers.status()
        # Interpreten (Seite /musik/interpreten, 13.11.2026): Bild holen, Vorschlaege, waehlen, eigenes, entfernen, vorab
        if op == "programs_report":               # Helfer: Programme am Stick kopiert (Karte auf Vorab-Laeufe, 14.11.2026)
            return self.programs_report(d)
        if op == "stars_set":                     # Sterne setzen (14.11.2026): kommen beim naechsten Start der Mixxx-App nach Mixxx
            r = d.get("r")
            n = self.stars.set(d.get("paths") if isinstance(d.get("paths"), list) else [], r if isinstance(r, int) else -1)
            return dict(self.favs.state(), conf=self.fav_conf(), n=n)
        if op == "stars_ack":                     # Musik-Rechner: in seine Warteschlange fuer Mixxx uebernommen
            return {"n": self.stars.ack(d.get("items") if isinstance(d.get("items"), list) else [])}
        if op == "eich_result":                   # Eichstueck (Seite /eichen, 23.11.2026): Messwerte eines Durchlaufs
            return self.eich.put(d)
        if op == "local_play":                    # Musik-DB: Lied im Browser (Hauptpanel Quelle Lokal, Matrix), nie aufs Licht
            return {"local": self.local.report(d)}
        if op.startswith("radio_"):               # Internetradio (Seite /musik/radio, 21.11.2026)
            return self.radio_op(op, d)
        if op == "missing_add":                   # Merkliste Fehlt mir: Lied (Interpret, Titel, Album) oder Suchtext
            self.missing.add(d.get("a"), d.get("t"), d.get("al"), d.get("q"))
            return self.missing.state()
        if op == "missing_del":
            self.missing.remove(str(d.get("k") or ""))
            return self.missing.state()
        if op == "fav_set":                       # Herz an/aus (Lied, Album, Interpret, Genre)
            self.favs.set(str(d.get("kind") or ""), str(d.get("id") or ""), bool(d.get("on")),
                          {"name": str(d.get("name") or "")[:160], "artist": str(d.get("artist") or "")[:120]})
            return dict(self.favs.state(), conf=self.fav_conf())
        if op == "artists_bulk":
            return self.artists.start() if d.get("on") else self.artists.stop()
        if op == "artists_bulk_status":
            return self.artists.status()
        if op == "artists_retry":                 # Leere noch einmal versuchen (14.11.2026)
            return self.artists.retry_none()
        if op in ("artist_fetch", "artist_suggest", "artist_choose", "artist_upload", "artist_remove", "artist_info"):
            k = str(d.get("k") or "")[:80]
            if not artists_mod.KEY_RE.match(k):
                raise ValueError("Interpret fehlt")
            if op == "artist_fetch":
                return {"ok": self.artists.fetch(k, force=True), "img": self.artists.mtime(k)}
            if op == "artist_info":                 # Lebenslauf und Alben (aus dem Internet, 90 Tage gemerkt)
                return self.artists.info(k, refresh=bool(d.get("refresh")))
            if op == "artist_suggest":
                return {"items": self.artists.suggestions(k)}
            if op == "artist_choose":
                self.artists.choose(k, str(d.get("url") or "")[:500])
                return {"ok": True, "img": self.artists.mtime(k)}
            if op == "artist_upload":
                try:
                    data = base64.b64decode(str(d.get("data") or ""), validate=True)
                except (ValueError, TypeError):
                    raise ValueError("Bild unbrauchbar")
                self.artists.upload(k, data)
                return {"ok": True, "img": self.artists.mtime(k)}
            self.artists.remove(k)
            return {"ok": True, "img": 0}
        if op == "album_info":                    # Alben: Datum, Label, Titelliste von Deezer (90 Tage gemerkt)
            return self.albums.info(str(d.get("k") or "")[:100], refresh=bool(d.get("refresh")))
        if op == "artists_restore":               # Zurueckspielen aus der Sicherung am Stick (Bild als base64)
            try:
                data = base64.b64decode(str(d.get("data") or ""), validate=True)
            except (ValueError, TypeError):
                raise ValueError("Bild unbrauchbar")
            self.artists.restore(d.get("f"), data)
            return {}
        if op == "genre_styles":                  # Genre-Editor: Licht-Stil je Genre (eigene vor fester Zuordnung)
            gs = [str(g)[:40] for g in (d.get("genres") or [])[:300]]
            return {"styles": {g: (self.show.gstyles.style(g) or "") for g in gs}}
        if op == "genre_style_carry":             # Genre-Editor: Genre umbenannt, der Licht-Stil bleibt gleich (08.11.2026)
            src, to = [str(g)[:40] for g in (d.get("from") or [])[:200]], str(d.get("to") or "")[:40]
            if not src or not to:
                raise ValueError("Genre fehlt")
            styles = {self.show.gstyles.style(g) or "" for g in src}
            if len(styles) != 1:                   # verschiedene Stile zusammengelegt: das Ziel behaelt seinen
                return {"carried": False, "style": self.show.gstyles.style(to) or ""}
            want = styles.pop()
            if (self.show.gstyles.style(to) or "") != want:
                self.show.gstyles.set(to, want or "aus")
            return {"carried": True, "style": want}
        if op == "path_moved":                    # Dateien pruefen: Datei umbenannt, Cue-Punkte und Cover mitnehmen (08.11.2026)
            old, new = str(d.get("old") or "")[:2000], str(d.get("new") or "")[:2000]
            if not old or not new or old == new:
                raise ValueError("Pfad fehlt")
            return {"marks": self.marks_bulk.moved(old, new), "cover": self.covers.moved(old, new)}
        if op == "cover_refresh":                 # Tag bearbeiten: Cover geaendert, gleich neu vom Mac holen (sonst bis 6 h alt)
            path = str(d.get("path") or "")[:2000]
            if not path:
                raise ValueError("Pfad fehlt")
            return {"ok": self.covers.fetch(path) is True}
        if op == "covers_restore":                # Zurueckspielen aus der Sicherung am Stick (Bild als base64)
            try:
                data = base64.b64decode(str(d.get("data") or ""), validate=True)
            except (ValueError, TypeError):
                raise ValueError("Cover unbrauchbar")
            self.covers.restore(d.get("f"), data)
            return {}
        if op == "quick_meta":                  # Quick in der Musik-Datenbank: Laenge, Tempo und MP3 in die neue Show, ohne die Show zu laden
            doc = st.load(d.get("name"))
            doc["audio"] = "audio.mp3"
            if float(d.get("duration") or 0) > 0:
                doc["duration"] = float(d["duration"])
            if float(d.get("bpm") or 0) > 0:
                doc["bpm"], doc["beat_offset"] = float(d["bpm"]), float(d.get("offset") or 0)
            return {"doc": st.save(d.get("name"), doc)}
        if op == "marks_from_mac":              # Quick: Abschnitte, Cues, Drops vom Mac, ohne dass das Lied im Deck lag
            return self.marks_from_mac(d.get("name"))
        if op == "lyrics_quick":                # Quick aus der Musik-Datenbank: erst der Speicher am Pi, nur wenn nie gesucht LRCLIB
            return self.lyrics_quick(d.get("name"))
        if op == "lyric_full":
            return self.show.lyric_full(time.time())
        if op == "lyric_refetch":
            return self.show.lyric_refetch(time.time(), d.get("query"))
        if op == "lyric_sync":
            return self.show.lyric_sync(time.time(), int(d.get("i", -1)))
        if op == "lyrics_bulk":                  # alle Lieder der Bibliothek vorab holen, langsam im Hintergrund
            return self.lyric_bulk.start() if d.get("on") else self.lyric_bulk.stop()
        if op == "lyrics_bulk_status":
            return self.lyric_bulk.status()
        if op == "lyrics_clear":
            st.save_lyrics(d.get("name"), None)
            return {"lyrics": None}
        if op == "assist_info":
            return self.assist_info(d.get("name"))
        if op == "assist":
            return self.assist(d)
        if op == "assist_job":
            return self.assist_job()
        if op == "claude_key":
            self._set_claude_key(d.get("key"))
            return {"has_key": bool(self._claude_key())}
        if op == "autosave":
            st.autosave(d.get("name"), d.get("doc"))
            return {}
        if op == "live":                  # Editor: Aenderungen wirken sofort, auch ungespeichert
            if en.loaded and en.doc_name != d.get("name") and not d.get("force"):
                return {"warnings": []}   # eine andere Show laeuft gerade: nicht dazwischenfunken, erst Play hier uebernimmt
            self.current = d.get("name")
            return {"warnings": en.load(d.get("doc"))}
        if op == "title_kept":            # Titel bereinigen: "so lassen"
            return {"kept": self.titles_kept()}
        if op == "title_keep":
            return self.title_keep(d.get("path"), d.get("title"), d.get("keep", True) is not False, str(d.get("src") or "hand"))
        if op == "music_root_save":
            return self.music_root_save(d.get("root"))
        if op == "genre_ai":                       # Genre-Editor: Claude schlaegt fuer Genres ohne Ziel eins aus der Hausliste vor
            return self.genre_ai(d.get("house"), d.get("items"))
        if op == "genre_song_ai":                  # Genre-Editor: Claude-Knopf je Lied (11.11.2026)
            return self.genre_song_ai(d.get("house"), d.get("songs"))
        if op == "music_nas_save":
            return self.music_nas_save(d.get("nas"))
        if op == "music_excl_save":
            return self.music_excl_save(d.get("excl"))
        if op == "library_save":
            st.library_save(d.get("patterns") or [])
            return {}
        if op == "profile_import":
            return {"type": fm.import_profile(self.show.rig, d.get("profile"))}
        if op == "analyze":
            env = d.get("env") or []
            res = analysis.estimate_tempo(env, float(d.get("rate", 100.0)))
            return {"tempo": res}
        if op == "peaks":
            peaks = d.get("data") or {}
            if len(peaks.get("min", [])) + len(peaks.get("max", [])) > MAX_PEAK_VALUES:
                raise ValueError("Wellenform zu gross")
            st.save_peaks(d.get("name"), peaks)
            return {}
        if op == "room":                         # Raumplan: wo die Geraete stehen, nur Anzeige
            devs = rm.devices(self.show.rig)
            return {"room": rm.load(self.room_path, {x["name"] for x in devs}), "devices": devs}
        if op == "room_save":
            devs = rm.devices(self.show.rig)
            return {"room": rm.save(self.room_path, d.get("room"), {x["name"] for x in devs})}
        if op == "stems_summary":
            return st.stems_summary()
        if op == "stems":
            st.save_stems(d.get("name"), d.get("data"))
            self.stem_claims.pop(st._audio_fp(d.get("name")), None)
            return {}
        if op == "stems_bulk":                    # Kurven vorab fuer die ganze Bibliothek: an/aus (Seite Statistik)
            return self.stem_bulk.set(d.get("on"))
        if op == "stems_activity":
            return self.stems_activity()
        if op == "stems_restore":                 # Zurueckspielen aus der Sicherung am Stick: wird wie neu gerechnete Kurven geprueft
            st.save_stems_fp(str(d.get("fp") or ""), d.get("data"))
            return {}
        if op == "stems_bulk_retry":
            return self.stem_bulk.retry()
        if op == "stems_bulk_status":
            return self.stem_bulk.status()
        if op == "stems_bulk_next":               # vom rechnenden Rechner (stems_show.py --vorab)
            return self.stem_bulk.next(str(d.get("who") or "?")[:60])
        if op == "stems_bulk_fp":
            return self.stem_bulk.note_fp(str(d.get("who") or "?")[:60], str(d.get("path") or ""), str(d.get("fp") or ""))
        if op == "stems_bulk_done":
            return self.stem_bulk.done(str(d.get("who") or "?")[:60], str(d.get("path") or ""), str(d.get("fp") or ""),
                                       d.get("data"), d.get("secs"))
        if op == "stems_bulk_fail":
            return self.stem_bulk.failed(str(d.get("who") or "?")[:60], str(d.get("path") or ""), d.get("error"))
        if op in ("stems_claim", "stems_release"):     # Pegelkurven: ein Rechner meldet an, dass er diese MP3 rechnet
            return self.stems_claim(d.get("name"), str(d.get("who") or "?")[:60], op == "stems_claim")
        if op == "play":
            if d.get("name") and (d.get("reload") or en.compiled is None or self.current != d["name"]):
                doc = st.load(d["name"])
                en.load(doc)
                self.current = doc["name"]
            pos = d.get("pos")
            en.play(now, None if pos is None else max(0.0, float(pos)), d.get("light"), d.get("client"))
            return self.status()
        if op == "pause":
            pos = d.get("pos")
            en.pause(now, None if pos is None else max(0.0, float(pos)))
            return self.status()
        if op == "stop":
            en.stop(now)
            return self.status()
        if op == "seek":
            en.seek(d.get("pos", 0), now)
            return self.status()
        if op == "light":
            en.set_light(bool(d.get("on")))
            return self.status()
        if op == "report":                # Ersatz, falls der WebSocket nicht geht
            self.report(d, now)
            return self.status()
        if op == "capture":              # Szene aus dem Stand an der Abspielposition
            c = en.compiled
            if c is None:
                raise ValueError("Keine Show geladen")
            state = c.evaluate(max(0.0, float(d.get("t", 0))), 0, False)
            return {"values": {f: {a: list(v) if isinstance(v, tuple) else v for a, v in st.items()} for f, st in state.items()}}
        if op.startswith("debug_"):       # DMX-Debugger (Seite /dmx-debug), siehe dmx_debug.py
            return self.debug_op(op, d)
        if op == "light_ms":              # Licht-Versatz direkt im Editor: wirkt sofort, auch waehrend die Musik laeuft
            self.show.cfg.set("sm_light_ms", float(d.get("ms", 0)))
            return self.status()
        if op == "blackout":
            self.show.command({"blackout": bool(d.get("on"))})
            return self.status()
        if op == "values":
            return {"attrs": en.values_for(str(d.get("fixture")), float(d.get("t", 0))), "dmx": en.dmx_for(str(d.get("fixture")))}
        raise ValueError("Unbekannter Befehl")

    def debug_op(self, op, d):
        out = getattr(self.show, "output", None)
        if out is None:
            raise ValueError("Keine Ausgabe vorhanden")
        if out.debug is None:
            from dmx_debug import DmxDebug
            out.debug = DmxDebug()
        dbg = out.debug
        if op == "debug_arm":
            if d.get("on") and self.show.override == "blackout":
                raise ValueError("BLACKOUT ist an: zuerst BLACKOUT ausschalten")
            dbg.arm(bool(d.get("on")))
        elif op == "debug_set":
            dbg.set_values(d.get("values") or {})
        elif op == "debug_hold":
            dbg.set_hold(bool(d.get("on")))
        elif op == "debug_beat":
            dbg.beat()
        elif op != "debug_state":
            raise ValueError("Unbekannter Befehl")
        return {"armed": dbg.is_armed(), "hold": dbg.hold, "values": dbg.values(), "blackout": self.show.override == "blackout", "strobe": bool(self.show.strobe)}

    def report(self, d, now):
        lat = float(d.get("rtt", 0)) / 2000.0 - float(d.get("ol", 0)) / 1000.0
        self.engine.report(d.get("client"), float(d.get("pos", 0)), bool(d.get("playing")), lat, now)

    def serve_ws(self, conn):
        """Verbindung eines Browsers: Meldungen annehmen, 5-mal pro Sekunde den Stand schicken."""
        watch, next_push = None, 0.0
        while True:
            now = time.time()
            timeout = max(0.0, next_push - now)
            if conn.wait(timeout):
                msg = conn.recv()
                if msg is not None:
                    try:
                        d = json.loads(msg)
                    except ValueError:
                        continue
                    if d.get("t") == "sync":
                        self.report(d, time.time())
                        conn.send(json.dumps({"t": "pong", "ts": d.get("ts")}))
                    elif d.get("t") == "watch":
                        watch = d.get("fixture") or None
                continue
            st = self.status()
            st["t"] = "st"
            if watch:
                st["vals"] = self.engine.values_for(watch, st["pos"])
                if st["on"]:
                    st["dmx"] = self.engine.dmx_for(watch)
            conn.send(json.dumps(st))
            next_push = time.time() + 0.2


def _with_stars(mgr, d):
    """Lieder eines Albums/Interpreten mit den wirksamen Sternen (Mixxx oder hier gesetzt)."""
    if isinstance(d, dict) and isinstance(d.get("songs"), list):
        d = dict(d, songs=[dict(s, rating=mgr.stars.eff(s.get("path") or "", s.get("rating") or 0)) for s in d["songs"]])
    return d


def _qs(path):
    return parse_qs(urlparse(path).query)


def handle_get(h, mgr):
    """True, wenn der Showmanager die Anfrage beantwortet hat."""
    path = urlparse(h.path).path
    if path == "/shows" or path == "/shows/":
        return _static(h, "play.html")
    if path == "/raum":
        return _static(h, "room.html")
    if path == "/dmx-debug":
        return _static(h, "debug.html")
    if path == "/shows/edit":
        return _static(h, "editor.html")
    if path == "/musik":
        return _static(h, "music.html")
    if path == "/musik/vorschlaege":              # Auto-Tagger: Vorschlaege fuer Lieder ohne Cover (die Daten kommen vom Mac)
        return _static(h, "autotag.html")
    if path == "/musik/autodj":                   # Auto-DJ: Playlist erstellen und im Browser auflegen (Musik vom Mac)
        return _static(h, "autodj.html")
    if path == "/musik/pflege":                   # Datenpflege: alle Werkzeuge zum Bereinigen als Rezept (zaehlt nur, fuehrt hin)
        return _static(h, "care.html")
    if path == "/musik/ordner":                   # Ordner umbenennen/verschieben (der Mac benennt um, Mixxx-Warteschlange)
        return _static(h, "ordner.html")
    if path == "/musik/dateinamen":               # Tags aus dem Dateinamen eintragen (der Mac schreibt)
        return _static(h, "fnametags.html")
    if path == "/musik/spiegeln":                 # Stick auf die NAS spiegeln (der Mac rechnet und kopiert)
        return _static(h, "mirror.html")
    if path == "/musik/lose":                     # Lose Album-Lieder in ihren Album-Ordner (14.11.2026, der Mac verschiebt)
        return _static(h, "lose.html")
    if path == "/musik/aufloesen":                # Ordner aufloesen: einen Oberordner in einen anderen einsortieren (der Mac verschiebt)
        return _static(h, "merge.html")
    if path == "/musik/import":                   # Import neuer Musik aus dem Wartebereich musik-import (der Mac verschiebt)
        return _static(h, "import.html")
    if path == "/musik/cd":                       # CD-Assistent: Trackliste einfuegen, zuordnen, schreiben (der Mac schreibt)
        return _static(h, "cd.html")
    if path == "/musik/defekt":                   # Beschaedigte Dateien finden und reparieren (Musik-Rechner, 14.11.2026)
        return _static(h, "defekt.html")
    if path == "/eichen":                         # Eichstueck abspielen und die Erkennung pruefen (23.11.2026)
        return _static(h, "eichen.html")
    if path == "/eichen/eichstueck.mp3":
        _send_mp3(h, os.path.join(os.path.dirname(STATIC), "eichstueck.mp3"))
        return True
    if path == "/musik/radio":                    # Internetradio (21.11.2026)
        return _static(h, "radio.html")
    if path == "/musik/fehlt":                    # Merkliste Fehlt mir (14.11.2026)
        return _static(h, "fehlt.html")
    if path == "/software":                       # Systemschema mit Download-Symbolen (Wunsch 15.11.2026)
        return _static(h, "software.html")
    if path == "/api/sm/pakete":                  # welche Pakete es am Pi gibt (blasse Symbole auf /software)
        import pakete
        _json(h, {"exe": pakete.exe_zip_path() is not None, "winmusik": hasattr(pakete, "windows_music_zip"), "macvoll": hasattr(pakete, "mac_full_zip")})
        return True
    if path == "/musik/favoriten":                # Favoriten: Lieder, Alben, Interpreten, Genres mit Herz (14.11.2026)
        return _static(h, "favs.html")
    if path == "/musik/gruppen":                  # Gruppen-Manager: Feld Gruppe (TIT1), Lieder verschieben (13.11.2026)
        return _static(h, "groups.html")
    if path == "/musik/alben":                    # Alben mit Cover, Liedern und Titelliste (13.11.2026)
        return _static(h, "albums.html")
    if path == "/musik/interpreten":              # Interpreten mit Bild und ihren Liedern (13.11.2026)
        return _static(h, "artists.html")
    if path == "/musik/genres":                   # Genre-Editor (der Mac liest und schreibt die Genres)
        return _static(h, "genres.html")
    if path == "/musik/pruefen":                  # Dateien pruefen: Datenmuell, sonstige Dateien, Dateinamen (der Mac prueft)
        return _static(h, "check.html")
    if path == "/musik/titel":                    # Titel bereinigen: Nummern am Anfang (die Tags liest und schreibt der Mac)
        return _static(h, "titles.html")
    if path == "/musik/doppelte":                 # Doppelte Lieder vergleichen und aufraeumen (die Daten kommen vom Mac)
        return _static(h, "dupes.html")
    if path == "/api/musik/stand":                # Lamperl der Musik-Datenbank: Liste vollstaendig oder im Aufbau (11.11.2026)
        _json(h, mgr.music_state())
        return True
    if path == "/api/musik/mac":                  # nur die Adresse des Vorhoer-Servers am Mac (ohne die ganze Liedliste)
        _json(h, {"music": mgr.music_url()})
        return True
    if path == "/api/musik":
        _json_list(h, mgr.music_list(), "tracks")
        return True
    if path == "/api/musik/conf":                 # Musikordner am Mac: fuer die Einstellungsseite und die Bruecke
        _json(h, mgr.music_conf())
        return True
    if path == "/shows/handbuch.pdf":
        return _manual(h)
    if path == "/download/broschuere.pdf":           # Broschuere fuer Freunde (auch im Notfall-Koffer am Stick)
        try:
            with open(BROCHURE, "rb") as f:
                h._send(200, f.read(), "application/pdf", {"Content-Disposition": 'attachment; filename="Light-Butler-Broschuere.pdf"'})
        except OSError:
            h._send(404, b"Broschuere fehlt", "text/plain")
        return True
    if path in ("/download/light-butler-mac.zip", "/download/light-butler-windows.zip"):   # Software fuer andere Rechner
        import pakete                                 # (Einstellungen, unten): ZIP entsteht bei jedem Abruf neu
        mac = path.endswith("mac.zip")
        data = pakete.mac_zip() if mac else pakete.win_zip()
        if data is None:
            h._send(404, "Paket fehlt am Pi: ./deploy.sh push kopiert die Dateien mit".encode("utf-8"), "text/plain; charset=utf-8")
        else:
            h._send(200, data, "application/zip", {"Content-Disposition": 'attachment; filename="%s"' % path.rsplit("/", 1)[1]})
        return True
    if path == "/download/light-butler-windows-exe.zip":    # Light-Butler.exe (am Windows-PC gebaut, per deploy.sh abgelegt)
        import pakete
        p = pakete.exe_zip_path()
        if p is None:
            h._send(404, "Noch keine Light-Butler.exe am Pi: am Windows-PC bauen (windows/build_exe.py), das ZIP am Mac nach windows/build/ legen, dann ./deploy.sh push".encode("utf-8"), "text/plain; charset=utf-8")
        else:
            with open(p, "rb") as f:
                data = f.read()
            h._send(200, data, "application/zip", {"Content-Disposition": 'attachment; filename="%s"' % pakete.EXE_NAME})
        return True
    if path == "/download/light-butler-windows-voll.zip":   # ganzer Light-Butler fuer einen Windows-PC (15.11.2026)
        import pakete
        data = pakete.windows_zip()
        if data is None:
            h._send(404, "Paket fehlt am Pi: ./deploy.sh push kopiert die Dateien mit".encode("utf-8"), "text/plain; charset=utf-8")
        else:
            h._send(200, data, "application/zip", {"Content-Disposition": 'attachment; filename="light-butler-windows-voll.zip"'})
        return True
    if path == "/download/light-butler-mac-voll.zip":        # ganzer Light-Butler fuer einen Mac (15.11.2026)
        import pakete
        data = pakete.mac_full_zip()
        if data is None:
            h._send(404, "Paket fehlt am Pi: ./deploy.sh push kopiert die Dateien mit".encode("utf-8"), "text/plain; charset=utf-8")
        else:
            h._send(200, data, "application/zip", {"Content-Disposition": 'attachment; filename="light-butler-mac-voll.zip"'})
        return True
    if path == "/download/light-butler-windows-musik.zip":   # Windows-PC als Musik-Rechner: Helfer + Bruecke (15.11.2026)
        import pakete
        data = pakete.windows_music_zip()
        if data is None:
            h._send(404, "Paket fehlt am Pi: ./deploy.sh push kopiert die Dateien mit".encode("utf-8"), "text/plain; charset=utf-8")
        else:
            h._send(200, data, "application/zip", {"Content-Disposition": 'attachment; filename="light-butler-windows-musik.zip"'})
        return True
    if path in ("/download/light-butler-pi.zip", "/download/light-butler-pi-ersatz.zip"):   # neuer Pi (12.11.2026)
        import pakete
        data = pakete.pi_zip(own=path.endswith("ersatz.zip"))
        if data is None:
            h._send(404, "Paket fehlt am Pi: ./deploy.sh push kopiert die Dateien mit".encode("utf-8"), "text/plain; charset=utf-8")
        else:
            h._send(200, data, "application/zip", {"Content-Disposition": 'attachment; filename="%s"' % path.rsplit("/", 1)[1]})
        return True
    if path == "/download/stand":                  # Stand der Pakete fuer die Kopie am Stick (Helfer am Mac, 14.11.2026)
        import backup
        import pakete
        try:
            lst = backup.list_backups(backup.load_conf())
        except (OSError, ValueError):
            lst = []
        _json(h, {"v": pakete.stand(), "backup": lst[0]["name"] if lst else ""})
        return True
    if path == "/download/backup":                 # juengste Sicherung des Pi, ohne geheime Dateien (12.11.2026)
        import backup
        try:
            r = backup.download_copy()
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            r, err = None, str(e)
        else:
            err = "Noch keine Sicherung am Light-Butler (sie entsteht jede Nacht um 04:30)"
        if r is None:
            h._send(404, err.encode("utf-8"), "text/plain; charset=utf-8")
        else:
            h._send(200, r[1], "application/zip", {"Content-Disposition": 'attachment; filename="%s"' % r[0]})
        return True
    if path == "/helfer" or path.startswith("/helfer/"):
        return _helfer(h, path[len("/helfer/"):])
    if path.startswith("/static/sm/"):
        return _static(h, path[len("/static/sm/"):])
    if not path.startswith("/api/sm/"):
        return False
    q = _qs(h.path)
    name = (q.get("name") or [""])[0]
    try:
        if path == "/api/sm/ws":
            _ws(h, mgr)
        elif path == "/api/sm/audio":
            _audio(h, mgr, name)
        elif path == "/api/sm/eichen":                       # Eichstueck: Abschnitte mit Sollwerten, letzter Durchlauf
            import eichstueck
            _json(h, {"sections": eichstueck.sections(), "dur": eichstueck.DURATION, "grace": eichstueck.GRACE_S, "einsatz": eichstueck.EINSATZ_S,
                      "version": eichstueck.VERSION, "last": mgr.eich.last})
        elif path == "/api/sm/shows":
            _json(h, {"shows": mgr.store.list(), "status": mgr.status()})
        elif path == "/api/sm/show":
            _json(h, {"doc": mgr.store.load(name), "autosave": mgr.store.load_autosave(name)})
        elif path == "/api/sm/peaks":
            _json(h, mgr.store.load_peaks(name) or {})
        elif path == "/api/sm/stems":
            _json(h, mgr.store.load_stems(name) or {})
        elif path == "/api/sm/marks_list":                   # Sicherung der Cue-Punkte auf den Stick (Mixxx-Bruecke am Mac)
            _json(h, {"files": mgr.marks_bulk.files()})
        elif path == "/api/sm/marks_file":
            raw = mgr.marks_bulk.raw((_qs(h.path).get("f") or [""])[0])
            if raw is None:
                h._send(404, b"nicht gefunden", "text/plain")
            else:
                h._send(200, raw, "application/json")
        elif path == "/api/sm/preview_marks":                # Vorhoeren ab Hauptteil, Hotcue oder Drop (14.11.2026)
            _json(h, mgr.preview_marks((q.get("p") or [""])[0]))
        elif path == "/api/sm/cover":                        # Cover (Musik-Datenbank, Showmanager, Hauptpanel)
            try:
                d = float((q.get("d") or ["0"])[0] or 0)
            except ValueError:
                d = 0.0
            img = mgr.cover(path=(q.get("p") or [""])[0], show=(q.get("show") or [""])[0], title=(q.get("t") or [""])[0], dur=d)
            if img is None:
                h._send(404, b"kein Cover", "text/plain", {"Cache-Control": "max-age=60"})
            else:
                # Fehlerbericht 09.11.2026: neues Cover, die Musik-Datenbank zeigte einen Tag lang das alte (max-age). Jetzt fragt
                # der Browser jedes Mal kurz nach (ETag = Pruefsumme des Bildes), unveraendert kommt nur "304", kein Bild.
                tag = '"' + hashlib.sha1(img).hexdigest()[:16] + '"'
                if (h.headers.get("If-None-Match") or "") == tag:
                    h._send(304, b"", "image/jpeg", {"Cache-Control": "no-cache", "ETag": tag})
                else:
                    h._send(200, img, "image/png" if img[:4] == b"\x89PNG" else "image/jpeg", {"Cache-Control": "no-cache", "ETag": tag})
        elif path == "/api/sm/quick_check":                  # Hauptpanel: Quick-Knopf zum Lied aus Mixxx
            try:
                d = float((q.get("d") or ["0"])[0] or 0)
            except ValueError:
                d = 0.0
            _json(h, mgr.quick_check((q.get("t") or [""])[0], d))
        elif path == "/api/sm/programs":                     # Karte Vorab-Laeufe: Programme am Stick
            _json(h, mgr.programs_state())
        elif path == "/api/sm/stars":                        # Sterne eines Liedes (Tag-Editor)
            p = (q.get("p") or [""])[0][:2000]
            link = mgr.show.mixxx
            x = next((x for x in (link.library_full() if link is not None and hasattr(link, "library_full") else []) if x.get("path") == p), {})
            _json(h, {"r": mgr.stars.eff(p, x.get("rating") or 0)})
        elif path == "/api/sm/radio":                        # Internetradio: Plaetze, Favoriten, Zustand, Eingang am Licht-Rechner
            cur = str(getattr(getattr(mgr.show, "src", None), "dev_name", "") or "")
            _json(h, dict(mgr.radio.state(), input=cur, net=cur == "Musik-Rechner (Netzwerk)", sim=not cur, line=mgr.line_info(),
                          line_dev=mgr.line_device() if cur else ""))
        elif path == "/api/sm/radio_want":                   # Helfer am Musik-Rechner: welcher Sender spielen soll
            _json(h, mgr.radio.want_info())
        elif path in ("/api/sm/radio_logo", "/api/sm/radio_cover"):
            if path.endswith("logo"):
                img = mgr.radio.logo((q.get("u") or [""])[0])
            else:
                sg = mgr.radio.song()
                img = mgr.radio.cover(sg["artist"], sg["title"]) if sg else None
            if img is None:
                h._send(404, b"kein Bild", "text/plain", {"Cache-Control": "max-age=30"})
            else:
                ct = ("image/png" if img[:4] == b"\x89PNG" else "image/gif" if img[:3] == b"GIF" else "image/webp" if img[:4] == b"RIFF"
                      else "image/x-icon" if img[:4] == b"\x00\x00\x01\x00" else "image/jpeg")
                h._send(200, img, ct, {"Cache-Control": "max-age=3600" if path.endswith("logo") else "no-cache"})
        elif path == "/api/sm/missing":                      # Merkliste Fehlt mir (ohne das, was inzwischen da ist)
            _json(h, mgr.missing.state())
        elif path == "/api/sm/favs":                         # Favoriten: was ein Herz hat (alle Seiten)
            _json(h, dict(mgr.favs.state(), conf=mgr.fav_conf()))
        elif path == "/api/sm/favs_page":                    # Seite Favoriten: Lieder, Alben, Interpreten, Genres
            _json(h, dict(mgr.favs.page(), conf=mgr.fav_conf(), music=mgr.music_url()))
        elif path == "/api/sm/fav_now":                      # Hauptpanel: Herz zum laufenden Lied
            try:
                dn = float((q.get("d") or ["0"])[0])
            except ValueError:
                dn = 0.0
            _json(h, mgr.fav_now((q.get("t") or [""])[0][:300], dn))
        elif path == "/api/sm/artists":                      # Seite Interpreten: alle mit Zahl der Lieder und Bild-Stand
            _json(h, {"artists": mgr.artists.listing(), "alias": dict(mgr.artists.alias), "music": mgr.music_url() if hasattr(mgr, "music_url") else ""})
        elif path == "/api/sm/albums":                       # Seite Alben: alle mit Cover-Lied, Interpret, Jahr
            _json(h, {"albums": mgr.albums.listing(), "music": mgr.music_url() if hasattr(mgr, "music_url") else ""})
        elif path == "/api/sm/album":                        # ein Album mit seinen Liedern (k=) oder das Album zu einem Lied (p=)
            k = (q.get("k") or [""])[0][:100] or mgr.albums.key_of_path((q.get("p") or [""])[0][:2000])
            _json(h, _with_stars(mgr, mgr.albums.songs(k)))
        elif path == "/api/sm/artist":                       # ein Interpret mit seinen Liedern
            _json(h, _with_stars(mgr, mgr.artists.songs((q.get("k") or [""])[0][:80])))
        elif path == "/api/sm/artist_img":
            raw = mgr.artists.raw((q.get("k") or [""])[0][:80] + ".jpg")
            if raw is None:
                h._send(404, b"kein Bild", "text/plain", {"Cache-Control": "max-age=60"})
            else:
                h._send(200, raw, "image/jpeg", {"Cache-Control": "max-age=86400"})   # die Seite haengt den Stand (v=) an
        elif path == "/api/sm/artists_list":                 # Sicherung der Interpreten-Bilder auf den Stick
            _json(h, {"files": mgr.artists.files()})
        elif path == "/api/sm/artists_file":
            raw = mgr.artists.raw((q.get("f") or [""])[0])
            if raw is None:
                h._send(404, b"nicht gefunden", "text/plain")
            else:
                h._send(200, raw, "image/jpeg")
        elif path == "/api/sm/covers_list":                  # Sicherung der Cover auf den Stick (Mixxx-Bruecke am Mac)
            _json(h, {"files": mgr.covers.files()})
        elif path == "/api/sm/covers_file":
            raw = mgr.covers.raw((q.get("f") or [""])[0])
            if raw is None:
                h._send(404, b"nicht gefunden", "text/plain")
            else:
                h._send(200, raw, "image/jpeg")
        elif path == "/api/sm/stems_list":                   # Sicherung der Kurven auf den Stick (Mixxx-Bruecke am Mac)
            _json(h, {"files": mgr.store.stems_files()})
        elif path == "/api/sm/stems_file":
            raw = mgr.store.stems_raw((_qs(h.path).get("fp") or [""])[0])
            if raw is None:
                h._send(404, b"nicht gefunden", "text/plain")
            else:
                h._send(200, raw, "application/json")
        elif path == "/api/sm/stems_state":
            state = dict(mgr.store.stems_state(name), max_min=mgr.stems_max_s() / 60.0)   # Grenze fuer den Waechter (Einstellung)
            state["busy"] = mgr.stems_busy(state.get("fp") or "")     # rechnet gerade jemand (Editor zeigt es, laedt danach selbst)
            _json(h, state)
        elif path == "/api/sm/meta":
            _json(h, mgr.meta())
        elif path == "/api/sm/status":
            _json(h, mgr.status())
        elif path == "/api/sm/mixxx":
            _json(h, mgr.mixxx_songs((q.get("q") or [""])[0]))
        elif path == "/api/sm/profile":
            _json(h, fm.export_profile(mgr.show.rig, (q.get("type") or [""])[0]))
        else:
            h._send(404, b"nicht gefunden", "text/plain")
    except (ValueError, KeyError, TypeError) as e:
        _json(h, {"error": str(e)}, 400)
    return True


def handle_post(h, mgr):
    path = urlparse(h.path).path
    if not path.startswith("/api/sm/"):
        return False
    try:
        n = int(h.headers.get("Content-Length", "0"))
        if path == "/api/sm/audio":
            mgr.store.save_audio((_qs(h.path).get("name") or [""])[0], h.rfile, n)
            mgr.index_dirty = True
            _json(h, {"ok": True, "size": n})
        elif path == "/api/sm/recognize":         # Tag bearbeiten: Ausschnitt eines Liedes per Shazam (SongRec) erkennen
            import songrec_id
            tf = getattr(mgr.show, "titles", None)
            if tf is None:
                raise ValueError("Titelerkennung gibt es hier nicht (Simulator oder SongRec fehlt)")
            if n <= 0 or n > songrec_id.TAG_MAX_BYTES:
                raise ValueError("Ausschnitt fehlt oder ist zu gross")
            _json(h, songrec_id.recognize_upload(tf.cmd, h.rfile.read(n)))
        elif path == "/api/sm/cmd":
            if n > MAX_JSON:
                raise ValueError("Daten zu gross")
            d = json.loads(h.rfile.read(n) or b"{}")
            h._op = str(d.get("op") or "")[:40] if isinstance(d, dict) else ""   # fuer die Seite Zustand: Dauer je Befehl
            _json(h, mgr.op(d))
        else:
            h._send(404, b"nicht gefunden", "text/plain")
    except (ValueError, KeyError, TypeError, OSError) as e:
        h.close_connection = True
        _json(h, {"error": str(e)}, 400)
    return True


def _json(h, data, code=200):
    h._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json")


def _json_list(h, data, key):
    """Wie _json, die lange Liste data[key] aber Eintrag fuer Eintrag: json.dumps ueber 9000 Lieder auf einmal haelt die
    Show-Schleife am Pi rund eine Drittelsekunde an (Aussetzer, Fehlerbericht 06.11.2026)."""
    rest = {k: v for k, v in data.items() if k != key}
    parts = [json.dumps(x, ensure_ascii=False) for x in data.get(key) or []]
    head = json.dumps(rest, ensure_ascii=False)
    body = head[:-1] + ("," if rest else "") + json.dumps(key) + ":[" + ",".join(parts) + "]}"
    h._send(200, body.encode("utf-8"), "application/json")


def _static(h, file):
    if not STATIC_RE.match(file):
        h._send(404, b"nicht gefunden", "text/plain")
        return True
    p = os.path.join(STATIC, file)
    try:
        with open(p, "rb") as f:
            data = f.read()
    except OSError:
        h._send(404, b"nicht gefunden", "text/plain")
        return True
    h._send(200, data, CTYPES[file.rsplit(".", 1)[1]])
    return True


def parse_range(header, size):
    """'bytes=a-b' -> (start, end) oder None."""
    m = re.match(r"^bytes=(\d*)-(\d*)$", (header or "").strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None
    if m.group(1):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else size - 1
    else:
        a = max(0, size - int(m.group(2)))
        b = size - 1
    b = min(b, size - 1)
    if a > b or a >= size:
        return None
    return a, b


def _helfer(h, name):
    """Dateien des Pegelkurven-Helfers (nur die drei aus HELFER). Ohne Namen: Liste zum Herunterladen."""
    if not name:
        have = [n for n in HELFER if any(os.path.isfile(os.path.join(d, n)) for d in HELFER_DIRS)]
        h._send(200, ("\n".join(have) + "\n").encode("utf-8"), "text/plain; charset=utf-8")
        return True
    if name not in HELFER:
        h._send(404, b"nicht gefunden", "text/plain")
        return True
    for d in HELFER_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                h._send(200, f.read(), "text/plain; charset=utf-8", {"Content-Disposition": 'attachment; filename="%s"' % name})
            return True
    h._send(404, b"nicht auf dem Pi: ./deploy.sh push kopiert die Helfer mit", "text/plain; charset=utf-8")
    return True


def _manual(h):
    """Bedienungsanleitung als PDF (gebaut von docs/showmanager_handbuch/build_pdf.py)."""
    try:
        with open(MANUAL, "rb") as f:
            h._send(200, f.read(), "application/pdf", {"Content-Disposition": 'attachment; filename="Showmanager-Handbuch.pdf"'})
    except OSError:
        h._send(404, b"Bedienungsanleitung fehlt", "text/plain")
    return True


def _audio(h, mgr, name):
    """MP3 einer Show."""
    _send_mp3(h, mgr.store.path(name, "audio.mp3"))


def _send_mp3(h, p):
    """MP3 mit Range-Anfragen: Der Browser muss darin springen koennen, Safari verlangt das sogar. Status wie HTTP/1.1."""
    if not os.path.isfile(p):
        h._send(404, b"keine Musik", "text/plain")
        return
    size = os.path.getsize(p)
    rng = h.headers.get("Range")
    r = parse_range(rng, size) if rng else (0, size - 1)
    if r is None:
        h.wfile.write(f"HTTP/1.1 416 Range Not Satisfiable\r\nContent-Range: bytes */{size}\r\nConnection: close\r\n\r\n".encode())
        h.close_connection = True
        return
    a, b = r
    n = b - a + 1
    head = "206 Partial Content" if rng else "200 OK"
    extra = f"Content-Range: bytes {a}-{b}/{size}\r\n" if rng else ""
    h.wfile.write((f"HTTP/1.1 {head}\r\nContent-Type: audio/mpeg\r\nAccept-Ranges: bytes\r\nContent-Length: {n}\r\n{extra}"
                   "Cache-Control: no-cache\r\nConnection: close\r\n\r\n").encode())
    h.close_connection = True
    with open(p, "rb") as f:
        f.seek(a)
        left = n
        try:
            while left > 0:
                b_ = f.read(min(256 * 1024, left))
                if not b_:
                    break
                h.wfile.write(b_)
                left -= len(b_)
        except (BrokenPipeError, ConnectionError):
            pass                              # Browser hat gesprungen und die alte Anfrage abgebrochen


def _ws(h, mgr):
    key = h.headers.get("Sec-WebSocket-Key")
    if not key or "websocket" not in (h.headers.get("Upgrade") or "").lower():
        h._send(400, b"WebSocket erwartet", "text/plain")
        return
    h.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Accept: {ws.accept_key(key)}\r\n\r\n").encode())
    h.wfile.flush()
    h.close_connection = True
    conn = ws.Conn(h.connection)
    try:
        mgr.serve_ws(conn)
    except (ConnectionError, OSError, ValueError):
        pass
