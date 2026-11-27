#!/usr/bin/env python3
"""
show.py - Szenen-Engine (Phase 3): verbindet Audioanalyse und DMX-Ausgabe.

    python3 show.py --simulate --dry-run          # ohne Audio und ohne Netzwerk
    python3 show.py --simulate                    # kuenstliche Musik an echte Geraete
    python3 show.py --device 1                    # echte Musik von der USB-Karte
    python3 show.py --device 1 --master 1.0 --strobe --debug

Look: ALLE Lichter nutzen dieselbe Farbe; sie wechselt nur bei Phrasenwechsel oder
Drop (Crossfade). Weisse Blitze und Strobe-Bursts treffen IMMER alle Lichter gleichzeitig.

Optionen: --strobe (Strobe-Bursts erlauben, Standard: aus), --no-white,
          --flash-every N (weisser Blitz alle N Beats, 0 = aus), --master 0..1.
Strg+C beendet mit Blackout. Laser, Hazer und gesperrte Kanaele bleiben immer 0
(dmx.py). Pan/Tilt und alle Motoren bleiben fest.

Stimmung (Heuristik, nicht exakt):
  Arousal = Tempo, Pegel, Kick-Dichte, Pegelanstieg   -> Energie der Effekte
  Valence = Helligkeit des Klangs (Spektralschwerpunkt), Tempo -> Farbwahl kalt..warm
"""
import argparse
import colorsys
import math
import copy
import json
import os
import random
import re
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from collections import deque

from audio import Analyzer, Simulator, key_label, meter_label
import laser_show
from scenes import COLORS as SCENE_COLORS
from takt import TaktClock, to_bar
from showman import latin as _latin
from showman.lyrics import line_end as lyric_end
from showman.lyrics import repeats as lyric_repeats
from genre_style import GENRE_STYLE, STYLES, GenreStyles, genre_style  # noqa: F401  (Genre-Stile aus Mixxx)
from scenes import (CYCLE_BEATS, COLOR_LABELS, KIND_LABELS, MIX_BUTTONS, MIX_LABELS, MOVE_LABELS, SPEEDS, Scene, SceneEngine,
                    default_scenes, fine_speed, load_scenes, save_scenes, scene_from_dict)
from fine import FineStore
from health import FrameStats
from settings import DEFS as SETTING_DEFS, G_HOME, Settings
from dmx import ArtNetSender, Output, PrintSender, Rig, slew

# Eine Farbe gilt fuer den ganzen Raum. Sie wechselt bei Phrase/Drop. Die Stimmung (Arousal = Energie,
# Valence = froh/duester) waehlt eine Farbfamilie, darin wird der Reihe nach gewechselt.
QUADRANTS = {
    "euphorisch": [0.07, 0.88, 0.15, 0.0, 0.93],   # Energie hoch, froh:     orange, magenta, gelb, rot, pink
    "intensiv":   [0.0, 0.88, 0.75, 0.60],         # Energie hoch, duester:  rot, magenta, violett, blau
    "froh":       [0.15, 0.07, 0.33, 0.52],        # Energie tief, froh:     gelb, orange, gruen, cyan
    "ruhig":      [0.60, 0.75, 0.46, 0.52],        # Energie tief, duester:  blau, violett, tuerkis, cyan
}
COLOR_NAMES = {"rot": 0.0, "orange": 0.07, "gelb": 0.15, "gruen": 0.33, "tuerkis": 0.46,
               "cyan": 0.52, "blau": 0.60, "violett": 0.75, "magenta": 0.88, "pink": 0.93}
WHEEL_HUES = [("red", 0.0), ("orange", 0.08), ("yellow", 0.15), ("green", 0.33),
              ("lightblue", 0.52), ("blue", 0.65), ("purple", 0.78), ("red", 1.0)]


def is_austria(sc):
    """Szene in Rot-Weiss-Rot (Farbe austria) oder mit dem Effektband-Preset 1 (Austria)."""
    return sc.color == "austria" or sc.preset == 1


def parse_device(x):
    """Audiogeraet als Nummer oder als Namensteil (z. B. USB). Der Name ist beim Booten stabiler."""
    try:
        return int(x)
    except ValueError:
        return x


def clamp01(x):
    return max(0.0, min(1.0, x))


def hsv(h, s, v):
    return colorsys.hsv_to_rgb(h % 1.0, clamp01(s), clamp01(v))


FRAME_HZ = 40.0                                          # Bilder pro Sekunde (Show und Ausgabe)
BLITZ_RATES = (1.0, 2.0, 4.0, 5.0, 40.0 / 6.0, 10.0)     # Blitze pro Sekunde mit gleichmaessigem Takt (Periode 40, 20, 10, 8, 6, 4 Bilder)


# Szenen-Automatik: Bereich in der Szenenliste (0 = vorne, 1 = hinten) je Stufe und beim Drop
SA_RANGE = {0: (0.15, 0.40), 1: (0.30, 0.60), 2: (0.50, 0.80), 3: (0.65, 0.95), "drop": (0.80, 1.00)}
SA_SKIP_NAMES = {"QUIZ"}                         # Gebrauchslicht, nie automatisch
# Befehle, die als eigene Bedienung zaehlen (beenden die automatische Szene, Pause sa_pause_s)
SA_USER_KEYS = ("scene", "auto", "blackout", "allbright", "mix", "move", "color", "speed", "aim", "beam", "blitz", "hold",
                "freeze", "build", "strobe", "rainbow", "colors", "eb_preset")
# Im Autopilot gesperrt: alles unter den Schnelleffekten. Frei bleiben STROBE, WOW!, BLINDER, FREEZE, BLACKOUT, SMOKE,
# Blitze/s, Dimmer und Gruppen-Regler, TAP/Tempo und alle Einstellungen.
PILOT_LOCKED = ("scene", "mix", "move", "speed", "color", "color_toggle", "style", "aim", "aim_set", "aim_save", "aim_add",
                "aim_rename", "aim_delete", "beam", "eb_preset", "fine", "scene_save", "scene_delete", "scene_move", "scenes_reset")
PILOT_BUTTON_COLORS = ("rot", "orange", "gelb", "gruen", "cyan", "blau", "violett", "magenta")   # Farbknoepfe mit Farbton
EB_STROBE = (8, 32)                              # Effektband-Presets mit Blitzen (Lightning, strobo): nur mit Strobe-Erlaubnis
# Speed in der Szene Laser: (Musterwechsel-Faktor, Motor-/Farbtempo, Beats je Puls)
LASER_SPEED = {"slow": (0.5, 0.6, 2.0), "mid": (1.0, 1.0, 1.0), "fast": (2.0, 1.4, 0.5)}
BEAM_GOBOS = ["open", "star", "spiral", "dots3", "triangle", "gobo5"]     # Beam: Gobo-Auswahl Open, 1 bis 5 (Vega)
BEAM_DEFAULT = {"gobo": 0, "zoom": 100.0, "roll": 50.0, "prism": 0.0}   # beim Verlassen von Auto


def beam_dmx(b):
    """Beam-Einstellung (Prozent) in Vega-Kanalwerte, nach dem Test am Geraet (30.10.2026):
    Roll: 50 % Stopp, darueber im Uhrzeigersinn (100 % am schnellsten, Kanal 129 langsam .. 12 schnell; 10 steht noch),
    darunter gegen den Uhrzeigersinn (0 % am schnellsten, Kanal 135 langsam .. 255 schnell).
    Prisma: 0 % aus, 50 % steht, darueber im Uhrzeigersinn (Kanal 194 .. 137, 100 % am schnellsten, Abstand zur Grenze 134),
    darunter gegen den Uhrzeigersinn (Kanal 195 .. 255, 1 % am schnellsten)."""
    roll, prism = float(b["roll"]), float(b["prism"])
    if abs(roll - 50.0) < 2.0:
        rot = 0                                                           # Stopp
    elif roll > 50.0:
        rot = int(round(129 - (roll - 50.0) / 50.0 * 117))               # im Uhrzeigersinn, langsam (129) .. schnell (12)
    else:
        rot = int(round(135 + (50.0 - roll) / 50.0 * 120))               # gegen den Uhrzeigersinn, langsam .. schnell
    if prism < 0.5:
        pr = 0                                                            # aus
    elif abs(prism - 50.0) < 2.0:
        pr = 70                                                           # Prisma steht (8 bis 134)
    elif prism > 50.0:
        pr = int(round(194 - (prism - 50.0) / 50.0 * 57))                # im Uhrzeigersinn, langsam (194) .. schnell (137)
    else:
        pr = int(round(195 + (50.0 - prism) / 49.0 * 60))                # gegen den Uhrzeigersinn, langsam .. schnell
    return {"gobo": BEAM_GOBOS[int(b["gobo"])], "zoom": int(round(255 * float(b["zoom"]) / 100.0)), "gobo_rot": rot, "prism": pr}


def snap_blitz(hz, limit=None):
    """Naechste erlaubte Blitzrate (ohne Strobe-Erlaubnis hoechstens `limit`)."""
    rates = [r for r in BLITZ_RATES if limit is None or r <= limit] or [BLITZ_RATES[0]]
    return min(rates, key=lambda r: abs(r - float(hz)))


def strobe_on(frame, hz, on_frames):
    """Blitz-Muster nach Bildzaehler: ganze Bilder an, Rest der Periode aus. Jeder Zyklus ist exakt gleich lang."""
    period = max(2, int(round(FRAME_HZ / hz)))
    return (frame % period) < max(1, min(int(on_frames), period - 1))


AUTO_SPEED_TIER = {"slow": 1, "mid": 2, "fast": 3}       # Tempo-Knopf im AUTO-Modus = feste Intensitaetsstufe

HOME_SETTINGS = [p for p in SETTING_DEFS if p.group == G_HOME]   # im Panel-Bereich Haus einstellbar
AIM_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")      # Kennung eines im Panel angelegten Ziels
AIM_LABEL_MAX = 30                                         # laengster Name eines Ziels

GROUP_KEYS = {"bars": "bar", "wash": "wash", "bar": "barlight", "fx": "fx", "uv": "uv", "spot": "spot",
              "ambient": "amb", "nano": "nano"}
AUTO_SOLO_KEYS = ("spot", "nano", "bar", "fx", "wash", "uv")   # AUTO "Geraete der Reihe nach": diese Gruppen wechseln sich ab
AUTO_SOLO_ORDER = ("spot", "nano", "bar", "fx", "wash")        # UV allein waere zu dunkel, Ambiente steht immer
GROUP_LABELS = [("bar", "Docooler"), ("wash", "Washes"), ("barlight", "PAR Barlicht"), ("fx", "Eyes und Derby"),
                ("uv", "UV-Leiste"), ("spot", "Vega"), ("amb", "Ambiente"), ("nano", "Nanoleaf"),
                ("api", "API")]   # API (Wunsch 23.11.2026): kein Licht, daempft nur masterDim/helligkeit in /api/takt


class Show:
    def __init__(self, rig, src, master=1.0, strobe=False, gamma=2.2, base=0.10,
                 attack=0.01, release=0.15, white=True, strobe_hz=6.0, flash_every=16, move="all", bar_sway=1.0,
                 bar_period=4.0, vega_speed=1.0, bar_style="snap", bar_every=1, colors=None, mood_log=None, energy_bias=0.0, aim_file="aim.json", settings_file="settings.json", scenes_file="scenes.json", mixxx=None, texts_file="texts.json", genre_file="genre_styles.json"):
        self.rig, self.src, self.master, self.strobe = rig, src, master, strobe
        self.showman = None                                # Showmanager (showman.engine.PlaybackEngine), vom Web-Panel gesetzt
        self.mixxx = mixxx                                  # Empfaenger der Mixxx-Bruecke (None = nicht genutzt)
        self.midi = None                                    # MIDI-Controller (APC mini mk2), falls vorhanden
        self.lumi = None                                    # ROLI LUMI Keys (lumi_ctl.py), falls vorhanden
        self.output = None                                  # Art-Net-Ausgabe (fuer den Schalter "DMX-Ausgabe zum OLA-Pi")
        self.link_out = None                                # Ableton Link (Tempo ins Netz), None = nicht verfuegbar (Trockenlauf)
        from texts import TextStore
        self.texts = TextStore(texts_file)                  # Texte des Panels (Deutsch/English, im Panel aenderbar)
        self.gstyles = GenreStyles(genre_file)              # eigene Zuordnung Genre -> Stil (im Panel aenderbar)
        self.style_man = None                               # Stil von Hand im Panel (z. B. Live-Musik), None = Auto
        self.played, self.played_last = [], None            # seit dem Start gespielte Titel aus Mixxx (Seite Statistik)
        self.titles = None                                  # Titelerkennung (songrec_id.py), None = nicht verfuegbar (Simulator)
        self.recorder = None                                # Debug-Aufnahme des Eingangs (recorder.py), None = Simulator
        self.live_genres = {}                               # von ihr erkannte Genres, fuer die Tabelle Genre-Stile
        self.started_wall = time.time()
        self.health_level = "ok"                            # Gesamtbewertung aus health.py (Farbe des Herzens)
        self.frames = FrameStats()                          # Bildtakt fuer die Seite Zustand (nur Messung, wirkt nicht aufs Licht)
        self.restart_requested = False                      # Neustart aus dem Panel (nach Aenderungen an den Fixtures)
        self.allow_poweroff = False                         # Herunterfahren aus dem Panel: nur im echten Betrieb am Pi
        self.power_mode = "pi" if sys.platform.startswith("linux") else "quit"   # Mac/Windows: Knopf beendet das Programm
        self.quit_requested = False                         # Beenden aus dem Panel (Mac/Windows, 16.11.2026)
        self.home = None                                    # HomeMatic-CCU (Bereich "Haus"), None = nicht verfuegbar
        self.home_quiet_t = self.home_music_t = None        # Automatik Wohnzimmerlicht: seit wann Stille bzw. Musik
        self.home_lit = False                               # Automatik hat das Wohnzimmerlicht bei Stille hochgedimmt
        self.home_party_s, self.home_tick_t = 0.0, None     # Musik seit dem letzten Einschalten (nur nach echter Musik an, 12.11.2026)
        self.home_last = None                               # zuletzt von der Automatik geschaltet: "on" | "off"
        self.home_send_t = None                             # Zeitpunkt des letzten Befehls der Automatik
        self.powering_off = False
        self._run_cmd = subprocess.run                      # fuer Tests austauschbar
        self.fx_pending = False                             # gespeicherte Fixture-Aenderungen, die einen Neustart brauchen
        self._fx_check()
        self.backup_info = {"running": False, "last": "", "error": ""}     # Stand der Sicherung (Panel)
        self.glevel = {k: 1.0 for k, _ in GROUP_LABELS}     # Helligkeit je Lichtgruppe (Gruppen-Fader), 1.0 = voll
        self.lyric_tap = None                               # von Hand angetippte Stelle: (Lied, Stelle, Zeit)
        self.lyric_cache = None                             # Liedzeilen je Lied aus Mixxx (showman.lyrics.LyricCache), vom Showmanager gesetzt
        self.mlyr = None                                    # Pixel-Matrix, Liedtext: (Zeit der Abfrage, Quelle) alle 0,25 s
        self.solo_i = 0                                     # AUTO "Geraete der Reihe nach": wer gerade dran ist
        self._nano_fx = None                                # gerade gewaehlter Effekt des Nanoleaf (Showmanager)
        self.mx = None                                      # letzter Stand der Mixxx-Vorhersage
        self.mx_tempo_on, self.mx_key_on = False, False     # kommen Tempo/Beat bzw. Tonart gerade von Mixxx?
        self.mx_phase_prev, self.mx_beat_count, self.beat_src = None, 0, "audio"
        self.scene_file = scenes_file                       # eigene Szenenliste (Reihenfolge, Namen, Eigenschaften)
        self.scene_defs = load_scenes(scenes_file)
        self.scene_rev, self.scene_last = 0, ""
        self.cfg = Settings(settings_file)                  # einstellbare Parameter der Auto-Erkennung
        self.safety_open = False                           # Sicherheitshinweis offen (neue Anlage, safety.py; main setzt ihn)
        from links import Links
        self.links = Links(os.path.join(os.path.dirname(os.path.abspath(settings_file)), "links.json")
                           if settings_file else None)     # eigene Links zu Geraeten (Einstellungen, 24.11.2026)
        self.fine = FineStore(os.path.join(os.path.dirname(os.path.abspath(settings_file)), "fine.json")
                              if settings_file else None)   # Feinregler je Bewegungs- und Licht-Mix-Knopf
        self.levels_path = (os.path.join(os.path.dirname(os.path.abspath(settings_file)), "levels.json")
                            if settings_file else None)     # Dimmer und Blitze pro Sekunde ueber den Neustart
        self.levels_dirty_t = None                          # seit wann ungespeicherte Aenderung
        self.wled_woken = False                             # WLED nach dem Start einmal eingeschaltet (Output.wake_wled)
        self.matrix = None                                  # Pixel-Matrix per DDP (wled_matrix.Matrix, main setzt sie)
        self.radio = None                                   # Internetradio (showman/radio.Radio, setzt der Showmanager)
        self.local = None                                   # Musik-DB spielt im Browser (showman/local_play.LocalPlay), nur Anzeige
        self.cfg.seed("energy_bias", energy_bias)
        self.cfg.seed("flash_every", flash_every)
        if hasattr(src, "silence_db"):
            self.cfg.seed("silence_db", src.silence_db)
        try:
            src.cfg = self.cfg                              # die Audio-Analyse liest Kick- und Stille-Werte live
        except AttributeError:
            pass
        self.gamma, self.base, self.attack, self.release = gamma, base, attack, release
        self.white_on, self.flash_every = white, flash_every
        self.move = move                      # all | spot | bars | off
        self.bar_sway = bar_sway              # Balken folgen dem Vega (0 = aus)
        self.bar_period = max(1.0, bar_period)   # Beats pro Faecher-Zyklus
        self.vega_speed = vega_speed          # Faktor fuer die Vega-Geschwindigkeit
        self.bar_style = bar_style            # snap = Spruenge im Takt, sine = weiche Welle
        self.bar_every = max(1, int(bar_every))   # Beats pro Sprung im snap-Stil
        self.vega_u = 0.5                     # logische Position des Vega: 0 = links, 1 = rechts
        self.mv = {}                          # aktuelle Positionen (weiche Bewegung)
        self.bpm = 0.0
        self.strobe_hz = max(2.0, min(12.0, strobe_hz))
        self.bars = [(f, i) for f in rig.group("bars") for i in range(len(f.zones()))]
        self.wash = [(f, i) for f in rig.group("wash") for i in range(len(f.zones()))]
        self.fxs = rig.group("fx")
        self.barlight = [(f, i) for f in rig.group("bar") for i in range(len(f.zones()))]
        self.uv = rig.group("uv")
        self.nano = [(f, 0) for f in rig.group("nano")]        # Nanoleaf-Panels (leer ohne nanoleaf.json)
        self.scenes = None
        self.zone_fx = [f for f in rig.fixtures if not f.locked and f.zones() and f.type != "wled_drgb"]
        # Moving Heads: der Vega und jedes Geraet in der Gruppe spot (zum Beispiel aus der Open Fixture Library)
        self.spot = [f for f in rig.fixtures if f.type == "vega_spot_60" or (f.group == "spot" and not f.locked)]
        # Ambiente (ruhig, ohne Beat): WLED-Lichter und jedes Farbgeraet in der Gruppe ambient (z. B. das PAR an der Bar)
        self.rgb_amb = [f for f in rig.fixtures if f.type == "wled_drgb" or (f.group == "ambient" and f.zones())]
        self.presets = [f for f in rig.fixtures if f.type == "wled_preset"]
        self.sm = {}
        self.last_t, self.last_dt = None, 0.025
        self.seen_beat = self.seen_kick = 0
        self.step = 0
        self.bar_len = 4                       # Beats pro Takt, nach denen das Licht gruppiert: 4 (4/4) oder 3 (3/4)
        self.kick_env = self.beat_env = self.level_s = 0.0
        self.hat_env, self.seen_hat, self.hat_t = 0.0, 0, -99.0    # Hi-Hat-Funkeln: Huellkurve, gesehene Schlaege, letzter Puls
        self.hat_panel, self._hat_rng = 0, random.Random(7)        # Nanoleaf-Panel des letzten Pulses (eigener Zufall)
        self.hat_block, self.hat_lucky, self._hat_share_rng = None, True, random.Random(11)   # Anteil: Phrase, Wuerfel, eigener Zufall
        self.hat_duck = 0.0                                        # Effektband zuruecknehmen: 0..1, gleitet weich
        self.pulse_env, self.pulse_t, self.pulse_on = 1.0, -99.0, False   # Beat-Puls: Huellkurve, letzter Puls, gerade aktiv
        self.pulse_k = 1.0                                         # Beat-Puls: Faktor fuer das Licht in AUTO (1 = aus)
        self.white_env = 0.0
        self.arousal, self.valence = 0.3, 0.5
        self.colors = list(colors) if colors else None   # feste Farbliste (Farbtoene) oder None
        self.pilot = True                                # Autopilot (Knopf AUTO): die Show bedient sich selbst, Bedienung darunter gesperrt
        self.auto_color = None                           # im AUTO-Modus gewaehlte Farbe (Panel/Controller), None = nach Stimmung
        self.auto_colors = []                            # im Panel gewaehlte Farbtoene (Mehrfachauswahl), ab 2 wechseln sie sich ab
        self.takt_mark = None                            # (Schlag, Zeit) des letzten Beats fuer /api/takt
        self.takt_enter = None                           # Schlag, ab dem der Abschnitt gilt (/api/takt)
        self.takt_ev = 0                                 # Zaehler der Abschnittswechsel (/api/takt)
        self.takt_clock = TaktClock()                    # gleichmaessige Takt-Uhr (/api/takt), nur Anzeige
        self.takt_keys = {k: False for k in self.TAKT_KEYS}   # Effekt-Tasten gedrueckt (/api/takt)
        self.takt_keys_since = {}                        # Taste -> Schlag, ab dem sie gedrueckt ist
        self.takt_keys_n = {k: 0 for k in self.TAKT_KEYS}     # so oft gedrueckt seit dem Start
        self.takt_dyn = (None, None)                     # Dynamik-Stufe (/api/takt) und ab welchem Schlag
        self.auto_rainbow = False                        # Licht-Mix Regenbogen in AUTO: Regenbogenfarben, Helligkeit nach der Musik
        self.rb_beats = 0.0                              # Fortschritt des Regenbogens in Beats
        self.auto_move = None                            # im AUTO-Modus gewaehlte Bewegung, None = nach Musik
        self.auto_speed = None                           # im AUTO-Modus gewaehltes Tempo (slow|mid|fast), None = nach Musik
        self._t_now = 0.0
        self.color_idx = -1
        self.last_color_change = -99.0
        self.sc = None                         # aktive Szene (None = Auto-Modus nach Musik)
        self.override = None                   # None | blackout | allbright
        self.freeze = False                    # Freeze: Licht und Bewegung einfrieren
        self.color_freeze = False              # Licht-Mix STOP: Licht einfrieren, Bewegung laeuft weiter
        self.build_t0 = None                   # handgestarteter Aufbau (Ausrufezeichen); None = aus
        self.wow_beats = 8.0                   # WOW!: so viele Beats dauert der Strobo-Aufbau, danach steht alles auf Maximum
        self.wow_period = 0.5                  # Beat-Laenge in s, beim Start aus dem BPM bestimmt
        self.wow_drop = True                   # WOW! loslassen = Drop (False: einfach zurueck in den vorigen Modus)
        self.build_seen = 0.0                  # letztes Lebenszeichen vom gedrueckten WOW!-Taster (Sicherheit)
        self.build_p, self.bphase = 0.0, 0.0
        self.blitz, self.blitz_hz, self.blitz_t0 = False, 5.0, 0.0   # Blitz: Strobe auf Knopfdruck, Tempo per Regler
        self.beam_man, self.beam = False, dict(BEAM_DEFAULT)  # Beam (Vega-Gobo, Zoom, Roll, Prisma): von Hand oder Auto
        self.sa = None                                      # Szenen-Automatik: {"name", "until_step"} solange sie eine Szene zeigt
        self.sa_eb = None                                   # Szenen-Automatik: {"pid", "until_step"} solange sie ein Effektband-Preset zeigt
        self.eb_man = None                                  # Effektband-Preset von Hand (Bereich Effektband im Panel), None = automatisch
        self.sa_user_t = None                               # letzte eigene Bedienung (Pause der Szenen-Automatik)
        self.sa_last = None                                 # zuletzt automatisch gewaehlte Szene (nicht zweimal hintereinander)
        self.vg_shift, self.vg_was_drop = 0, False          # Vega-Strahl in AUTO: Gobo-Versatz (Drop = naechstes Gobo)
        # Abwechslung Docooler/Vega (AUTO): Reihenfolge an der Decke = DMX-Adresse (Kette 1, 2, Vega, 5, 6)
        self.dc_order = sorted({f for f, _ in self.bars}, key=lambda f: f.address)
        self.dc_pat, self.dc_phrase, self.dc_solo, self.dc_drop_seen = None, None, 0, None
        self.cue_prev, self.cue_seq, self.cue_now = None, 0, False   # Hotcues aus Mixxx: zuletzt gesehen, Zahl der Wechsel, jetzt
        self.dc_mask, self.dc_vega = None, 1.0
        self._dc_rng = random.Random(7)                      # eigener Zufall: die uebrige Show bleibt unberuehrt
        self.beam_used = False                              # Beam hat Kanaele gesetzt, die beim Zurueck wiederhergestellt werden
        self._levels_load()                                 # Hauptdimmer, Gruppen-Dimmer, Blitze pro Sekunde, Beam (levels.json)
        self.solo = None                                           # Einzel-Strobe: {"fx", "until", "rate", "test"} oder None
        self.solo_last, self.solo_next_t = "", 0.0
        self._rng = random.Random()
        self.blitz_f = 0                                           # Bildzaehler des Blitzes (gleichmaessiger Takt)
        self.burst_f = 0                                           # Bildzaehler des Strobo-Bursts
        self.fog_last = -999.0                 # Zeit des letzten Nebelschubs (Start)
        self.fog_end = -999.0                  # Ende des laufenden bzw. letzten Nebels (Pause zaehlt ab hier)
        self._fog_clock = time.time            # Uhr fuer den Nebel (in Tests austauschbar)
        self.fog_hm_on = False                 # Nebelschub laeuft gerade ueber den HomeMatic-Schalter
        self.fog_warm_t = None                 # seit wann die Nebelmaschine heizt (-inf = beim Start schon an, also warm)
        self.fog_on_t = None                   # seit wann sie an ist (fuer das automatische Ausschalten)
        self.fog_used_t = None                 # letzter Nebelschub
        self.fog_prev_power = None             # zuletzt gelesener Zustand der Steckdose (None = noch nicht gelesen)
        self.fog_ack = False                   # Warnleiste "Rauchmelder deaktiviert?" weggetippt
        self.fog_remind = False                # Erinnerung "Rauchmelder wieder aktivieren" nach dem Ausschalten
        self.held = {}                         # gehaltene Taster (Panel/APC): Name -> letztes Lebenszeichen
        self._full = False                     # True = Master ignorieren (Sonnenbrille)
        self.lasers = [f for f in rig.fixtures if f.laser_params]   # 21 Eyes und Derby (KTV-Laser bleibt gesperrt)
        self.laser_on = False
        self.beat_t = None                     # Zeitpunkt des letzten erkannten Beats (fuer das Beat-Lamperl im Panel)
        self.reach = {}                        # Erreichbarkeit: Name -> True/False/None (vom Panel-Thread)
        self.reach_ip = {}                     # IP-Adresse je Name (fuer die Anzeige)
        self.reach_url = {}                    # Konfigurationsseite je Name (Link bei der IP-Adresse)
        self.net = []                          # Netzwerk des Raspberry (LAN/WLAN), wird vom Panel-Thread gepflegt
        self.mo = None                         # Bewegungsvorgabe der Szene
        self.manual_bpm = None
        self.takt_lvl = {k: 0.0 for k, _ in self.TAKT_BANDS}        # /api/takt pegel/baender: geglaettet
        self.takt_lvl_max = {k: deque() for k, _ in self.TAKT_BANDS}   # (Sekunde, Hoechstwert in ihr)
        self.takt_lvl_n = 0
        self.bpm_unsure = False                # Tempo noch nicht sicher (Liedanfang ohne Beat): Licht ohne Tempo, _bpm_gate
        self.bs_ref = self.bs_since = None
        self.bs_clar = deque()                 # (Zeit, Schlag-Klarheit) der letzten bpm_sure_s Sekunden
        self.bs_sure, self.bs_seen_kick, self.bs_kicks = False, 0, deque()
        self.aim = None                        # Ziel fuer alle Bewegungen: bank | tisch | tuer | bar | None (frei)
        self.aim_file = aim_file
        self.aim_targets = self._load_aim(rig)
        self.level_amb = 0.4                   # sehr traege Lautstaerke fuer die Ambiente-Lichter
        self.loud_k, self.loud_ref = 1.0, None # Helligkeit folgt Lautstaerke: Faktor, Pegel der lauten Teile (dB)
        self.amb_sent = {}
        self.cmd_lock = threading.Lock()
        self.note = ""
        self.boost = 0.0                       # kurzzeitig erhoehte Energie nach einem Drop
        self.energy_bias = energy_bias         # < 0 = insgesamt ruhiger, > 0 = lebhafter
        self.inten = 0.4
        self.tier = 1                          # 0 ruhig, 1 sanft, 2 Groove, 3 Peak
        self.tier_t = -99.0
        self.quadrant = "ruhig"
        self.hist = deque()                    # (t, db_short, high, centroid) der letzten 8 s
        self.loud_hist = deque()               # (t, db_short) alle 0,5 s, 3 Minuten lang: juengster Musikpegel
        self._loud_t = 0.0
        self.seen_weak = 0
        self.last_act = -99.0                  # Zeitpunkt des letzten Kicks oder Beats
        self.rel_idle, self.idle_floor = False, -120.0        # Stille bei Rauschen (relativ zum Musikpegel)
        self.ref_db = -30.0                    # Pegel vor einer Stille oder einem Break (fuer die Rueckkehr)
        self.db_music = None                   # Langzeit-Pegel nur aus Musik (ohne Stille), phase_v2
        self.high_s, self.build_high = 0.0, 0.0   # geglaettete Hoehen, ihr Hoechstwert im Aufbau (phase_v2: Drop nach dem Aufbau)
        self.drop_pre = None                   # drop_step: Stufe vor dem letzten Drop
        self.takt_scene, self.takt_scene_since = None, None   # /api/takt: aktive Szene und Schlag, ab dem sie gilt
        self.resume_t = -99.0                  # Zeitpunkt, an dem nach einer Stille wieder Musik begann
        self.t_first = None
        self.build_score = self.build_hold = self.build_prog = 0.0
        self.build_start = 0.0
        self.last_drop = -99.0
        self.f = None
        self.log, self.log_t = None, 0.0
        if mood_log:
            import csv
            self._logfile = open(mood_log, "w", newline="")
            self.log = csv.writer(self._logfile)
            self.log.writerow(["t", "state", "bpm", "level", "db_short", "db_long", "centroid", "high",
                               "mode", "key_conf", "kick_rate", "arousal", "valence", "quadrant", "build"])
        self.hue = self.hue_target = self._pick_hue()
        self.kick_times = deque()
        self.talk, self.talk_clar = False, deque()     # Sprache erkannt (speech_guard, 25.11.2026)
        self.talk_t = None                             # seit wann es nach Sprache aussieht
        self.mxp_t, self.mxp_kick_seen, self.mxp_music = None, 0, False   # Mixxx pausiert, aber Musik am Audio-Eingang?
        self.mxp_kicks = deque()
        self.last_flash = -99.0
        self.state, self.state_t, self.prev_state, self.below = "normal", 0.0, "normal", 0.0
        self.dim = 1.0
        self.burst_start = self.burst_until = 0.0
        self.last_burst = -99.0
        self.amb = {}
        self.pre_idx, self.pre_cur, self.pre_t, self.pre_role = {}, {}, {}, {}
        self.accent_until, self.last_accent = {}, -99.0
        self.status = ""
        self.scenes = SceneEngine(self)

    # ---- Hilfsfunktionen ---------------------------------------------------
    def smooth(self, key, target, dt, release=None, attack=None):
        """Schneller Anstieg, langsamer Abfall: ruhiger, weniger Flackern."""
        cur = self.sm.get(key, target)
        tau = (self.attack if attack is None else attack) if target > cur else \
            (self.release if release is None else release)
        cur += (1 - math.exp(-dt / tau)) * (target - cur)
        self.sm[key] = cur
        return cur

    def paint(self, fx, zi, r, g, b, w=0.0, uv=0.0):
        """Farben 0..1; Gamma-Kurve fuer wahrnehmbare Helligkeitsunterschiede."""
        k, gm = (1.0 if self._full else self.master), self.gamma
        if fx.white_mix and w:          # kein Weiss-LED: Weiss vor Gamma und Master in RGB mischen (sonst ueberschreitet es den Master)
            r, g, b = (min(1.0, c + w) for c in (r, g, b))
            w = 0.0
        vals = {key: int(round(255 * (clamp01(v) ** gm) * k))
                for key, v in (("r", r), ("g", g), ("b", b), ("w", w), ("uv", uv))}
        z = fx.zones()[zi]
        if fx.dead:
            # Defekte LEDs: nur zeigen, wenn die lebenden Kanaele zur Raumfarbe passen.
            # Beispiel: nur Rot funktioniert -> bei Gruen/Blau/Violett aus, bei Rot/Orange/Magenta an.
            alive = [c for c in ("r", "g", "b") if z.get(c) and z[c] not in fx.dead]
            tot = vals["r"] + vals["g"] + vals["b"]
            if len(alive) < 3 and tot > 0:
                fit = sum(vals[c] for c in alive) / tot
                k = 0.0 if fit < 0.45 else fit
                for c in ("r", "g", "b"):
                    vals[c] = int(vals[c] * k) if c in alive else 0
        fx.set_zone(zi, r=vals["r"], g=vals["g"], b=vals["b"], w=vals["w"], uv=vals["uv"])
        for p in fx.dead:
            if p in fx.values:
                fx.values[p] = 0

    def _acolor(self, b, x=0.5, fx=None, zi=0, hue_off=0.0):
        """Farbe fuer die Helligkeit b (0..1) nach der gewaehlten AUTO-Farbe: (r, g, b, w, uv).
        Wie die Szenen: Weiss nur ueber die Weiss-LEDs, UV nur ueber UV, Bunt nach Lage, Regenbogen laeuft durch."""
        if self.auto_rainbow:
            return (*hsv(self._rainbow_hue(fx, x), 1.0, b), 0.0, 0.0)
        c = self.auto_color
        zs = fx.zones() if fx is not None else []
        z = zs[zi] if zi < len(zs) else {}
        if c == "white":
            if "w" in z:
                return (0.0, 0.0, 0.0, b, 0.0)
            return (b, b, b, 0.0, 0.0)
        if c == "uv":
            return (0.0, 0.0, 0.0, 0.0, b if "uv" in z else 0.0)
        if c == "multi":
            return (*hsv(x * 0.85, 1.0, b), 0.0, 0.0)
        if c == "rainbow":
            bpm = self.bpm if self.bpm > 0 else 110.0
            return (*hsv(x * 0.25 + self._t_now * bpm / 60.0 / 48.0, 1.0, b), 0.0, 0.0)
        return (*hsv(self.hue + hue_off, 1.0, b), 0.0, 0.0)

    def _rainbow_hue(self, fx, x=0.5):
        """Regenbogen wie beim Licht-Mix: jedes Geraet eine Farbe der Reihe nach (DMX-Adresse), langsam weiterlaufend.
        Geraete ausserhalb der Reihenfolge (Panels, Theke, Couchtisch) nach ihrer Lage x."""
        idx = self.scenes.scan_idx.get(fx.name) if fx is not None else None
        xf = idx / (self.scenes.scan_n - 1) if idx is not None else x
        if self.auto_rainbow:                            # Regenbogen-Knopf: Feinregler Size (Verteilung) und Shift (Farbton)
            fv = self.fine.get("mx", "Regenbogen")
            return (xf * 0.9 * 2.0 ** ((fv["size"] - 50.0) / 50.0) + (fv["shift"] - 50.0) / 100.0
                    + self.rb_beats / (CYCLE_BEATS["mid"] * 4.0)) % 1.0
        return (xf * 0.9 + self.rb_beats / (CYCLE_BEATS["mid"] * 4.0)) % 1.0

    def wheel_name(self, hue):
        return min(WHEEL_HUES, key=lambda x: abs(x[1] - hue % 1.0))[0]

    # ---- Hauptupdate -----------------------------------------------------------
    def _apply_mixxx(self, f, now):
        """Tempo, Beat-Lage und Tonart aus Mixxx nehmen, solange ein Deck hoerbar spielt (sonst Audio-Erkennung)."""
        c, m = self.cfg, self.mx
        active = bool(m and m.get("connected") and m.get("deck") is not None and m.get("playing") and m.get("audible", 0) >= 0.3)
        self.mx_tempo_on = bool(active and c["mixxx_tempo"] > 0.5 and m["bpm"] > 0 and m["phase"] is not None)
        self.mx_key_on = bool(active and c["mixxx_key"] > 0.5 and m.get("fk", 0) > 0)
        if self.mx_tempo_on:
            ph = m["phase"]
            if self.mx_phase_prev is not None and ph < self.mx_phase_prev - 0.5:      # Beat-Lage ist uebergelaufen: neuer Beat
                self.mx_beat_count += 1
            self.mx_phase_prev = ph
            f = f._replace(bpm=float(m["bpm"]))
        else:
            self.mx_phase_prev = None
        if self.mx_key_on:
            fk = m["fk"]
            f = f._replace(mode=-1.0 if fk >= 13 else 1.0, key_conf=1.0, key=(fk - 1) % 12)
        return f

    def out_on(self, k):
        """Ausgabe an ein Ziel (ola, wled, nano): Schalter an und das Geraet vorhanden (Einstellung *_have, 14.11.2026)."""
        return self.cfg[k + "_out"] > 0.5 and self.cfg[k + "_have"] > 0.5

    def update(self, now):
        f = self.src.poll(now)
        dt = 0.025 if self.last_t is None else min(0.1, max(0.0, now - self.last_t))
        self.last_t, self.last_dt = now, dt
        self._t_now = now
        _latin.ENABLED = self.cfg["lyrics_latin"] > 0.5     # Liedtext nur lateinisch (Anzeige, 24.11.2026)
        self._takt_keys(now)                                # /api/takt: Effekt-Tasten (nur Anzeige)
        self._takt_level(f, dt)                             # /api/takt: Pegel und Baender der Musik (nur Anzeige)
        if self.output is not None:                        # Ausgabe zum OLA-Pi und zu den WLED-Lichtern nach den Einstellungen schalten
            self.output.set_enabled(self.rig.target, self.out_on("ola"))
            if self.override == "blackout" and getattr(self.output, "debug", None) is not None and self.output.debug.armed:
                self.output.debug.arm(False)               # DMX-Debugger: BLACKOUT geht immer vor
            if hasattr(self.output, "ext_on"):             # Art-Net-Eingang: nicht bei BLACKOUT
                self.output.ext_on = self.cfg["artnet_in"] > 0.5 and self.override != "blackout"
                self.output.ext_strobe = bool(self.strobe)
            r = self._dmx_router()
            if r is not None:                              # DMX-Weg: OLA-Pi (Art-Net) oder USB-Adapter am Pi
                r.set_via("usb" if self.cfg["dmx_via"] > 0.5 else "ola")
            for t in self._wled_targets():
                self.output.set_enabled(t, self.out_on("wled"), blackout=False)
            if not self.wled_woken and self.out_on("wled") and hasattr(self.output, "wake_wled"):
                self.wled_woken = True                         # einmal beim Start: WLED einschalten (aus vom letzten Beenden)
                self.output.wake_wled(self._wled_targets())
            for t in self._nano_targets():
                self.output.set_enabled(t, self.out_on("nano"), blackout=False)
        self.mx = self.mixxx.status(now, self.cfg) if self.mixxx is not None else None
        self._note_played()
        f = self._apply_mixxx(f, now)
        f = self._rel_silence(f, now)
        f = self._mixxx_pause(f, now)
        f = self._bpm_refine(f)
        f = self._bpm_gate(f, now)
        self._titles_tick(now, f)
        self.bpm = f.bpm
        self.f = f
        c = self.cfg

        count = self.mx_beat_count if self.mx_tempo_on else f.beat_count             # Beat-Zaehler aus Mixxx oder aubio
        src = "mixxx" if self.mx_tempo_on else "audio"
        if src != self.beat_src:                                                      # Quelle gewechselt: kein Sprung
            self.seen_beat, self.beat_src = count, src
        new_beats = max(0, count - self.seen_beat)
        new_kicks = max(0, f.kick_count - self.seen_kick)
        self.seen_beat, self.seen_kick = count, f.kick_count
        new_hats = max(0, f.hat_count - self.seen_hat)
        self.seen_hat = f.hat_count
        weak = getattr(self.src, "weak_beats", 0)                                       # Fehlerbericht 15.11.2026: aubio findet
        new_weak = max(0, weak - self.seen_weak) if src == "audio" else 0                # im Rauschen nach einem Stopp weiter Beats
        self.seen_weak = weak                                                          # (unsicher): die halten die Stille nicht auf
        if new_kicks or new_beats > new_weak:
            self.last_act = now
        if self.bpm_unsure:                       # Tempo noch nicht sicher: die Schlaege von aubio zaehlen nicht, der Kick fuehrt
            new_beats = 0
        for _ in range(new_kicks):
            self.kick_times.append(now)
            if now - self.last_flash > c["kick_flash_gap"]:  # Kick-Hell, begrenzt das Flackern
                self.kick_env = 1.0
                self.last_flash = now
        while self.kick_times and now - self.kick_times[0] > 4.0:
            self.kick_times.popleft()
        if new_beats:
            self.beat_env = 1.0
        if new_beats or (new_kicks and f.bpm <= 0):       # ohne Tempo-Erkennung blinkt das Lamperl auf den Kick
            self.beat_t = now
        self.step += new_beats if f.bpm > 0 else new_kicks
        if new_beats and f.bpm > 0:
            self.takt_mark = (self.step, now)                  # /api/takt: Schlag self.step lag genau hier (nur Anzeige)
            self.takt_clock.beat(self.step, now, self.manual_bpm or f.bpm)
        new_steps = new_beats if f.bpm > 0 else new_kicks
        self.kick_env *= math.exp(-dt / c["kick_env_decay"])
        self.beat_env *= math.exp(-dt / c["beat_env_decay"])
        self.white_env *= math.exp(-dt / 0.06)
        self.hat_env *= math.exp(-dt / 0.07)
        if (new_hats and c["hat_amount"] > 0 and not f.silent and self.state in ("normal", "build", "drop")
                and self.override is None and not self.freeze
                and now - self.hat_t >= (0.125 if self.strobe else 0.5)   # Blitzgrenze: ohne Strobe-Erlaubnis 2/s, mit 8/s
                and self._hat_gate()):
            self.hat_env, self.hat_t = 1.0, now
            if self.nano:
                self.hat_panel = self._hat_rng.randrange(len(self.nano))
        self.hat_duck += (1 - math.exp(-dt / 0.4)) * ((1.0 if now - self.hat_t < 1.0 else 0.0) - self.hat_duck)
        self._update_pulse(f, now, dt, new_beats or (new_kicks and f.bpm <= 0))
        self.level_s += (1 - math.exp(-dt / 0.3)) * (f.level - self.level_s)
        self.level_amb += (1 - math.exp(-dt / c["amb_tc"])) * (f.level - self.level_amb)

        self._update_bar(f)
        bl = self.bar_len
        self._update_mood(f, now, dt)
        self._update_state(f, now, dt)
        self._update_tier(f, now, dt)
        self._update_loud(f, dt)
        drop_start = self.state == "drop" and self.prev_state != "drop"
        if new_steps and self.step % (max(1, int(c["auto_solo_bars"])) * bl) == 0:   # immer auf einem Beat
            self.solo_i += 1
        phrase = bool(new_steps) and self.step % (8 * bl) == 0      # 8 Takte = eine Phrase
        self.cue_now = self._cue_hit()
        if self.cue_now:                                            # Hotcue ueberschritten: wie eine neue Phrase
            phrase = True
            self.cue_seq += 1
        if self.talk:                                               # Sprache: keine Phrasen (kein Szenen-/Farbwechsel, 25.11.2026)
            phrase = False
        sm_on = False                                               # Showmanager: dieses Bild kommt aus der programmierten Show
        if self.showman is not None:
            self.showman.offset = c["sm_light_ms"] / 1000.0
            if self.showman.owner == "mixxx":
                self.showman.offset += c["mixxx_lead_s"]            # derselbe Vorlauf wie Beat und Vorhersage aus Mixxx
            self.showman.tick(now)
            sm_on = self.showman.active()
        if not sm_on and not self.talk:                             # die Szenen-Automatik ruht, solange eine Show laeuft oder jemand spricht
            with self.cmd_lock:
                self._scene_auto(now, phrase, drop_start)

        # ---- eine Farbe fuer alle: Wechsel nur bei Phrase oder Drop (Crossfade) ----
        if (phrase or drop_start) and now - self.last_color_change > c["color_min_s"]:   # Mindestdauer je Farbe
            self.hue_target = self._pick_hue()
            self.last_color_change = now
        if self.auto_color in SCENE_COLORS:                   # gewaehlter Farbton gilt fuer alle Lichter
            self.hue_target = SCENE_COLORS[self.auto_color]
        if self.auto_rainbow:                                 # Regenbogen: auch Aufbau und Drop laufen durch die Farben
            self.rb_beats += dt * (self.bpm if self.bpm > 0 else 120.0) / 60.0 * fine_speed(self.fine.get("mx", "Regenbogen")["speed"])
            self.hue_target = self._rainbow_hue(None)
        d = ((self.hue_target - self.hue + 0.5) % 1.0) - 0.5
        self.hue = (self.hue + (1 - math.exp(-dt / c["hue_fade_s"])) * d) % 1.0

        # ---- gemeinsame Blitze fuer ALLE Lichter -----------------------------------
        drop_flash = clamp01(1.0 - (now - self.state_t) / 0.6) if self.state == "drop" else 0.0
        fe = int(c["flash_every"])
        if bl == 3 and fe > 0:
            fe = max(1, int(round(fe * 3 / 4)))                      # gleiche Anzahl Takte wie bei 4/4
        if (self.white_on and fe > 0 and new_steps
                and self.step % fe == 0 and self.arousal > c["flash_arousal"]
                and self._base_tier() >= 2 and self.state == "normal" and self._style("flash", True) and not self.talk):
            self.white_env = 1.6        # nach Abklingen im ersten Frame ca. 1,0
        cool = c["burst_cool_drop_s"] if drop_start else c["burst_cool_s"]
        if (self.strobe and self.state not in ("idle", "gap", "build") and not self.talk
                and now - self.last_burst > cool
                and (drop_start or (new_steps and self.step % (16 * bl) == 0 and self.arousal > 0.6))):
            self.burst_start, self.burst_until, self.last_burst = now, now + c["burst_len_s"], now
            self.burst_f = 0
            for fx in self.presets:      # Effektband: "strobo" waehrend des Bursts, danach zurueck zur Rolle
                pid = fx.extra.get("preset_drop")
                if pid and c["blitz_band_sync"] < 0.5:
                    self.pre_cur[fx.name], self.pre_t[fx.name] = pid, now
                    self.accent_until[fx.name] = max(self.accent_until.get(fx.name, 0), now + 2.0)
        if drop_start and self.strobe and c["blitz_band_sync"] < 0.5:   # Effektband: "strobo" beim Drop, danach zurueck zur Rolle
            for fx in self.presets:
                pid = fx.extra.get("preset_drop")
                if pid:
                    self.pre_cur[fx.name], self.pre_t[fx.name] = pid, now
                    self.accent_until[fx.name] = now + 2.5
        self.prev_state = self.state
        burst = self.strobe and now < self.burst_until
        burst_on = burst and strobe_on(self.burst_f, snap_blitz(self.strobe_hz), c["blitz_on_frames"])
        if burst:
            self.burst_f += 1
        flash = max(drop_flash, min(1.0, self.white_env))

        if self.build_t0 is not None and now - self.build_seen > 1.5:   # Taster nicht mehr gehalten (z. B. Handy gesperrt)
            with self.cmd_lock:
                self._manual_build(False)
        if self.held:
            with self.cmd_lock:
                self._hold_check(time.time())
        frozen = self.freeze and self.override is None        # Blackout und Sonnenbrille gehen immer vor
        building = self.build_t0 is not None and self.override is None
        cfrozen = self.color_freeze and self.override is None and not frozen and not building and not sm_on
        manual = self.override is not None or self.sc is not None or frozen or building or cfrozen or sm_on
        if not manual or (cfrozen and self.sc is None):   # STOP in AUTO: Bewegung laeuft wie in AUTO weiter
            self.mo = None
            if self.auto_move:                                 # Bewegung per Knopf vorgegeben: die Muster der Szenen nutzen
                bpm_m = self.manual_bpm or (self.bpm if self.bpm > 0 else 120.0)
                self.scenes.beatpos += dt * bpm_m / 60.0
                self.scenes.motion(self, now, Scene(move=self.auto_move, mspeed=self.auto_speed or "mid"))
        self._nano_effect_tick(now, sm_on)
        with self.rig.lock:
            if self.showman is not None and self.showman.dirty and not sm_on:
                self.showman.release()                              # Show zu Ende: Geraete zurueck, AUTO uebernimmt
            solo_key = self._auto_solo_key(sm_on)
            full = self.override == "allbright"                # Sonnenbrille: immer 100 %, auch ohne Gruppen-Fader
            for fx in self.rig.fixtures:
                key = GROUP_KEYS.get(fx.group, "")
                fx.level = 1.0 if full else self.glevel.get(key, 1.0)
                if solo_key is not None and key in AUTO_SOLO_KEYS and key != solo_key:
                    fx.level = 0.0
                if not full and fx.extra.get("fader") not in (None, key):     # zweiter Regler, zum Beispiel Barlicht: PAR Barlicht und Ambiente
                    fx.level *= self.glevel.get(fx.extra["fader"], 1.0)
            for fx in self.lasers:                             # Laser-Freigabe gilt nur fuer genau diesen Frame
                fx.laser_unlock = False
                fx.mode_unlock = False
                if fx.sound_mode is not None:
                    fx.values["mode"] = 0                      # Sound-Modus nie "haengen lassen"
            self.laser_on = False
            t_state = now - self.state_t
            sm_draw = False
            beam_on = (self.beam_man and self.override is None and not frozen and not building and not cfrozen and not sm_on
                       and not (self.sc is not None and self.sc.special == "laser"))
            if self.beam_used and not beam_on and not frozen and not cfrozen:
                self._beam_restore()                          # nach Beam von Hand: Zoom, Roll, Prisma wieder wie vorher
            if self.override == "blackout":
                self._render_blackout()
            elif self.override == "allbright":
                self._render_allbright()
            elif frozen:
                for fx in self.presets:                       # Effektband: laeuft selbst, deshalb dunkel
                    fx.set("dimmer", 0)
            elif building:
                self._render_manual_build(now, dt)
            elif cfrozen:                                     # STOP: Farben und Helligkeit bleiben stehen
                for fx in self.presets:                       # Effektband: laeuft selbst, deshalb dunkel (wie Freeze)
                    fx.set("dimmer", 0)
                if self.sc is not None:                       # Szene: nur ihre Bewegung laeuft weiter
                    bpm_m = self.manual_bpm or (self.bpm if self.bpm > 0 else 120.0)
                    self.scenes.beatpos += dt * bpm_m / 60.0
                    self.scenes.motion(self, now, self.sc)
            elif sm_on:
                sm_draw = True
                ps = self._show_panel_scene(now)
                if ps is not None:                            # Szene aus dem Panel in der Timeline: dieselbe Berechnung wie im Panel
                    own_master, self.master = self.master, self.master * self.showman.master_now(now)
                    self.scenes.render(self, now, dt, ps)
                    self.scenes.motion(self, now, ps)
                    self.master = own_master
                    self.showman.laser_live, self.showman.dirty = False, True
                else:
                    self.showman.render(now, self.master, self.strobe, c["sm_laser"] > 0.5)   # vor allen Szenen: die Szene Laser ruht dann
                self.laser_on = self.showman.laser_live       # Anzeige LASER AKTIV
            elif self.sc is not None and self.sc.special == "laser":
                self._render_laser(now, dt)                   # Lasershow: alle anderen Lichter dunkel
            elif self.aim and self.sc is None:
                self._render_aimlight()                       # Ziel: nur Vega und Docooler, weiss
            elif self.sc is not None:
                self.scenes.render(self, now, dt, self.sc)
            elif self.state == "idle":
                self._render_idle(now, dt)
            elif self.state == "gap":
                self._render_gap()
                self._render_ambient(now, dt, 0.0)            # Ambiente bleibt ruhig (kein Blinken, Grundhelligkeit)
            elif self.state == "build":
                self._render_build(now, dt)
                self._render_ambient(now, dt, 0.0)
            elif self.state == "drop" and t_state < max(0.8, c["drop_len_s"]):     # heller Effekt so lange wie die Drop-Dauer
                self._render_dropfx(now, dt, t_state)
                self._render_ambient(now, dt, 0.0)
            else:
                self._render_bars(now, dt, flash)
                self._render_wash(now, dt, flash)
                self._render_barlight(now, dt, flash)
                self._render_uv(now, dt, flash)
                self._render_fx(now, dt, flash)
                self._render_spot(now, flash)
                self._render_ambient(now, dt, 0.0)            # Ambiente blinkt nie mit (Theke, Couchtisch, Barlicht)
                self._render_nano(now, dt, flash)
            if beam_on:
                self._render_beam()                           # Beam von Hand: gilt in AUTO und allen Szenen
            if not manual:
                self._render_presets(now, flash, burst)
            if self.aim and self.override is None and not frozen and not building and not cfrozen and not sm_on:
                self._aim_isolate()                           # Ziel: alle anderen Geraete dunkel
            if not frozen and not sm_draw:
                self._render_motion(now, dt)
            if self.override != "blackout":
                self._solo_update(now, new_steps, bl, burst,
                                  self.sc is None and self.override is None and not frozen and not building
                                  and not cfrozen and not self.blitz and not self.aim and not sm_on)
            if burst and not manual:
                self._render_burst(burst_on, age=self.burst_f, hz=snap_blitz(self.strobe_hz))
            if self.blitz and self.override != "blackout":     # Blitz: alles weiss im Takt des Reglers, nach Bildzaehler
                self._render_burst(strobe_on(self.blitz_f, self._blitz_rate(), c["blitz_on_frames"]), age=self.blitz_f,
                                   hz=self._blitz_rate())
                self.blitz_f += 1
        if self.output is not None:                            # Ausgabe sendet genau dieses Bild (kein Doppeln oder Auslassen)
            self.output.delay_frames = int(round(c["light_delay_ms"] / 25.0))   # Licht-Verzoegerung (25.11.2026)
            self.output.delay_now = self.override == "blackout"
            self.output.notify()
        if self.matrix is not None:                            # Pixel-Matrix (wled_matrix.py): eigenes Ziel, liest nur den Zustand
            self._matrix_tick(now, dt, f, new_beats, new_kicks, new_hats, frozen)
        self.build_prog = clamp01((now - self.build_start) / 10.0) if self.state == "build" else 0.0
        self._write_log(f, now)
        self._fog_tick()
        if self.home is not None:
            self._home_auto(now)
        if self.levels_dirty_t is not None and time.monotonic() - self.levels_dirty_t >= 2.0:
            self._levels_save()                                # Dimmer hoechstens alle 2 s auf die SD-Karte
        if self.link_out is not None:                          # Ableton Link: angezeigtes Tempo, bei Stille 20 BPM
            self.link_out.update(self.cfg["link_on"] > 0.5, self._bpm_live())
        aim = f" | ZIEL {self.aim}" if self.aim else ""
        mode = ("BLACKOUT" if self.override == "blackout" else "ALLES HELL" if self.override == "allbright"
                else "FREEZE" if frozen else "FARB-FREEZE" if cfrozen else f"WOW {self.build_p:.2f}" if building
                else f"SHOW {self.showman.doc_name}" if sm_on else f"SZENE {self.sc.name}" if self.sc else "AUTO")
        self.status = (f"{mode}{aim} | {self.state:6s} S{self.tier} A {self.arousal:.2f} V {self.valence:.2f} {self.quadrant[:5]} "
                       f"mode {f.mode:+.1f} "
                       f"Farbe {self.hue:.2f} BPM {f.bpm:5.1f} step {self.step:4d} "
                       f"dB {f.db_short:6.1f}/{f.db_long:6.1f} kick/s {len(self.kick_times)/4.0:.1f}"
                       f"{' BURST' if burst else ''}"
                       + "".join(f" EB{self.pre_cur.get(fx.name, 0)}" for fx in self.presets))

    def _update_bar(self, f):
        """3/4 nur bei (fast) 100 % Sicherheit der Takterkennung, sonst Vierergruppen. Mit Hysterese."""
        thr = self.cfg["meter3_conf"]
        meter, conf = getattr(f, "meter", 0), getattr(f, "meter_conf", 0.0)
        if self.bar_len == 4:
            if meter == 3 and conf >= thr - 0.005:
                self.bar_len = 3
        elif meter != 3 or conf < thr - 0.25:
            self.bar_len = 4

    def quadrant_now(self):
        c = self.cfg
        h = c["quad_hyst"]
        hi_a = self.arousal >= (c["quad_a"] - h if self.quadrant in ("euphorisch", "intensiv") else c["quad_a"] + h)
        hi_v = self.valence >= (c["quad_v"] - h if self.quadrant in ("euphorisch", "froh") else c["quad_v"] + h)
        return {(True, True): "euphorisch", (True, False): "intensiv",
                (False, True): "froh", (False, False): "ruhig"}[(hi_a, hi_v)]

    def _pick_hue(self):
        if len(self.auto_colors) > 1:                        # Mehrfachauswahl im Panel: nur die gewaehlten Farben
            lst = [SCENE_COLORS[c] for c in self.auto_colors]
        elif self.colors:
            lst = self.colors
        elif self._style("colors", None):                    # Genre-Stil aus Mixxx: seine Farbpalette
            lst = self._style("colors", None)
        else:
            self.quadrant = self.quadrant_now()
            lst = QUADRANTS[self.quadrant]
        for _ in range(len(lst) + 1):
            self.color_idx += 1
            hue = lst[self.color_idx % len(lst)]
            if hue != getattr(self, "hue_target", None):
                return hue
        return lst[0]

    # ---- Stimmung -------------------------------------------------------------------
    def _update_mood(self, f, now, dt):
        """Arousal (Energie) und Valence (froh..duester) als Heuristik aus Audio-Merkmalen.
        Valence: Dur/Moll (Tonart), Tempo, Klanghelligkeit. Unsicher, deshalb kein harter Schalter."""
        c = self.cfg
        kick_rate = len(self.kick_times) / 4.0
        bpm_part = clamp01((f.bpm - c["bpm_lo"]) / c["bpm_span"]) if f.bpm > 0 else 0.4
        rise = clamp01((f.db_short - f.db_long + 6.0) / 12.0)
        ws = (c["w_bpm"], c["w_level"], c["w_kick"], c["w_rise"], c["w_high"])
        wn = sum(ws) or 1.0
        a = (ws[0] * bpm_part + ws[1] * clamp01(f.level) + ws[2] * clamp01(kick_rate / c["kick_rate_full"])
             + ws[3] * rise + ws[4] * clamp01(f.high * 1.5)) / wn
        a = clamp01(a + self.boost)
        conf = clamp01((f.key_conf - c["key_conf_min"]) / 0.4)
        mode01 = 0.5 + 0.5 * f.mode * conf                   # 0.5 = unbekannt, 1 = Dur, 0 = Moll
        tempo_v = clamp01((f.bpm - 80.0) / 80.0) if f.bpm > 0 else 0.5
        vs = (c["v_w_mode"], c["v_w_tempo"], c["v_w_bright"], c["v_w_energy"])
        vn = sum(vs) or 1.0
        v = (vs[0] * mode01 + vs[1] * tempo_v + vs[2] * f.centroid + vs[3] * a) / vn
        self.boost *= math.exp(-dt / c["boost_decay_s"])
        self.arousal += (1 - math.exp(-dt / c["arousal_tc"])) * (a - self.arousal)
        self.valence += (1 - math.exp(-dt / c["valence_tc"])) * (v - self.valence)

    # ---- Phasen: normal / break / build / gap / drop / idle ------------------------------------
    def _mixxx_pause(self, f, now):
        """Meldet Mixxx 'kein Deck hoerbar' (Pause, Ende, Fader zu), gilt das als Stille: sofort Ruhemodus, kein Drop.
        Kommt trotzdem Musik am Audio-Eingang an (mindestens mixxx_pause_kicks Kicks in 3 s nach der Pause, z. B. eine
        andere Quelle am Pult), uebernimmt die Audio-Erkennung mit Beat und BPM, bis der Eingang selbst still wird."""
        m = self.mx
        if not (m and self.cfg["mixxx_pause_idle"] > 0.5 and m.get("connected") and m.get("deck") is None):
            self.mxp_t = None
            return f
        if self.mxp_t is None:                             # Pause beginnt: nur Kicks ab jetzt zaehlen
            self.mxp_t, self.mxp_kick_seen, self.mxp_music = now, f.kick_count, False
            self.mxp_kicks.clear()
        new = max(0, f.kick_count - self.mxp_kick_seen)
        self.mxp_kick_seen = f.kick_count
        if new and not f.silent:
            self.mxp_kicks.extend([now] * new)
        while self.mxp_kicks and now - self.mxp_kicks[0] > 3.0:
            self.mxp_kicks.popleft()
        if f.silent:
            self.mxp_music = False                         # Eingang wirklich still: wieder sofortiger Ruhemodus
        elif len(self.mxp_kicks) >= self.cfg["mixxx_pause_kicks"]:
            self.mxp_music = True
        return f if self.mxp_music else f._replace(silent=True)

    def _rel_silence(self, f, now):
        """Stille auch dann erkennen, wenn der Eingang rauscht: weit unter dem juengsten Musikpegel und lange ohne Kick und Beat."""
        c = self.cfg
        if now - self._loud_t >= 0.5:
            self._loud_t = now
            self.loud_hist.append((now, f.db_short))
            while self.loud_hist and now - self.loud_hist[0][0] > 180.0:
                self.loud_hist.popleft()
        if f.silent or c["rel_silence_on"] < 0.5:
            self.rel_idle = False
            return f
        if not self.rel_idle:
            loud = max((d for _, d in self.loud_hist), default=f.db_short)
            if (now - self.last_act > c["rel_silence_s"] and f.db_short < loud - c["rel_silence_db"]
                    and self.t_first is not None and now - self.t_first > 15.0):
                self.rel_idle, self.idle_floor = True, f.db_short
        else:
            self.idle_floor = min(self.idle_floor, f.db_short)
            kicks3 = sum(1 for t in self.kick_times if now - t < 3.0)
            if f.db_short > self.idle_floor + c["rel_wake_db"] or kicks3 >= 3:
                self.rel_idle = False
        return f._replace(silent=True) if self.rel_idle else f

    def _enter(self, state, now):
        prev = self._takt_section(now) if self.state_t is not None else "normal"
        if self.state == "drop" and prev == "normal":       # Drop war schon vorbei (nach drop_len): dieser Wechsel zaehlte schon
            self.takt_ev += 1
        self.state, self.state_t = state, now
        old, self.takt_enter = self.takt_enter, self._takt_bar_at(now)   # /api/takt: neuer Abschnitt ab diesem Taktanfang (die Eins)
        if self._takt_section(now) != prev:                 # jeder Wechsel des Abschnitts zaehlt (nur Anzeige)
            self.takt_ev += 1
        else:
            self.takt_enter = old                            # gleicher Abschnitt (zum Beispiel gap -> break): bleibt, wie er war
        if state in ("gap", "break") and self.f is not None and not (prev == "gap" and self.cfg["phase_v2"] > 0.5):
            self.ref_db = self._db_long(self.f)                # Pegel vor der Pause: daran misst sich die Rueckkehr
            # (phase_v2: Pause -> Break behaelt den Pegel von vor der Pause, sonst galt die leise Musik als zurueck)
        if state == "build":
            self.build_start = now
        elif state == "drop":
            self.last_drop = now
            self.boost = self.cfg["drop_boost"]      # Energie bleibt nach dem Drop erhoeht
            self.arousal = max(self.arousal, self.cfg["drop_arousal"])
            if self.cfg["drop_step"] > 0.5:                 # Drop hebt nur eine Stufe, danach zurueck (Wunsch 23.11.2026)
                self.drop_pre = self.tier
                self.inten, self.tier_t = max(self.inten, 0.85), now
            else:
                self.inten, self.tier, self.tier_t = max(self.inten, 0.85), 3, now
            self.kick_env = 1.0
            self.build_hold = 0.0
            self.hist.clear()                        # Build-up-Erkennung beginnt neu
        elif state == "normal":
            self.below = 0.0

    PHASE_DB_TC = 8.0           # phase_v2: Gedaechtnis des Vergleichspegels (db_long der Analyse: 20 s, mit Stille)
    BUILD_RISING = 0.4          # phase_v2: ab diesem Aufbau-Wert endet ein Break nicht mit einem Drop (erst der Aufbau)
    BUILD_DROP_HIGH = 0.25      # phase_v2: so weit fallen die Hoehen am Ende des Aufbaus (Rauschen/Wirbel endet)

    def _db_long(self, f):
        """Langzeit-Pegel fuer die Phasen. phase_v2 (Eichstueck 23.11.2026): nur aus Musik, ohne Stille; db_long der Analyse
        zieht nach einer Stille noch lange nach unten (nach 30 s Beat -32 statt -26 dB), dann wurde jeder Break zum Drop.
        Kuerzeres Gedaechtnis (PHASE_DB_TC), damit auch eine leise Einleitung den Pegel vor dem Break nicht verfaelscht."""
        if self.cfg["phase_v2"] > 0.5 and self.db_music is not None:
            return self.db_music
        return f.db_long

    def _update_state(self, f, now, dt):
        if f.silent:
            self.db_music = None
        elif self.db_music is None:
            self.db_music = f.db_short
        else:
            self.db_music += (1 - math.exp(-dt / self.PHASE_DB_TC)) * (f.db_short - self.db_music)
        self.high_s += (1 - math.exp(-dt / 0.3)) * (f.high - self.high_s)
        v2 = self.cfg["phase_v2"] > 0.5
        dbl = self._db_long(f)
        self.hist.append((now, f.db_short, f.high, f.centroid))
        while self.hist and now - self.hist[0][0] > 8.0:
            self.hist.popleft()
        if self.t_first is None:
            self.t_first = now
        if f.silent:
            if self.state != "idle":
                self._enter("idle", now)
            return
        if self.state == "idle":
            self.hist.clear()                                # Musik beginnt nach Stille: die Stille darf keinen Aufbau oder Drop vortaeuschen
            self.hist.append((now, f.db_short, f.high, f.centroid))
            self.resume_t = now
            self._enter("normal", now)
        c = self.cfg
        mx = self.mx
        if mx and mx.get("plan") and c["mixxx_light"] > 0.5:         # Phasen nach der Vorhersage aus der Analyse
            if mx["want"] != self.state:
                self._enter(mx["want"], now)
            target = {"break": c["break_dim"], "idle": 0.12, "gap": 0.0}.get(self.state, 1.0)
            self.dim += (1 - math.exp(-dt / 0.6)) * (target - self.dim)
            return
        if self._talk_update(now):                        # Ansprache: keine Drops, kein Aufbau, keine Pause, kein Break
            if self.state != "normal":
                self._enter("normal", now)
            self.dim += (1 - math.exp(-dt / 0.6)) * (1.0 - self.dim)
            return
        early = (now - self.t_first < c["early_s"]       # in den ersten Sekunden keine Phasen erkennen,
                 or now - self.resume_t < c["early_s"])  # ebenso nach einer Stille (Musik beginnt von vorn)

        present = f.db_short > c["silence_db"] + 10.0        # es ist wirklich Ton da (nicht nur "leiser als vorher")
        returned = f.db_short > self.ref_db - c["return_db"]  # und der Pegel kommt wieder an die Musik von vorher heran (nicht nur Rauschen)
        recent_db = [d for t, d, h, c in self.hist if t >= now - 1.5]
        max_db = max(recent_db) if recent_db else f.db_short
        old_db = next((d for t, d, h, c in self.hist if t >= now - 2.0), f.db_short)
        t0, db0, h0, c0 = self.hist[0]
        span = now - t0
        score = 0.0
        if span > 4.0:                                   # Build-up: Pegel, Hoehen und Helligkeit steigen
            score = (0.5 * clamp01(((f.db_short - db0) / span) / 0.8)
                     + 0.25 * clamp01((f.high - h0) / 0.35)
                     + 0.25 * clamp01((f.centroid - c0) / 0.2))
        self.build_score = score
        self.build_hold = self.build_hold + dt if score > c["build_score_min"] else 0.0
        kicks_recent = sum(1 for t in self.kick_times if now - t < 1.0)
        since = now - self.state_t

        if self.state == "normal":
            self.below = self.below + dt if f.db_short < dbl - c["break_below_db"] else 0.0
            if early:
                pass
            elif self.build_hold > c["build_hold_s"] and now - self.last_drop > c["build_cooldown_s"]:
                self._enter("build", now)
            elif f.db_short < max_db - c["gap_drop_db"]:     # ploetzliche Stille
                self._enter("gap", now)
            elif self.below > c["break_hold_s"] and kicks_recent <= 1:          # leise UND ohne Kick = Break
                self._enter("break", now)
            elif (f.db_short - old_db > c["drop_jump_db"] and old_db > c["silence_db"] + 10.0
                  and now - self.last_drop > c["drop_cooldown_s"]
                  and (not v2 or kicks_recent >= 1)):   # Einsatz (nicht aus der Stille heraus); v2: nur mit Beat
                self._enter("drop", now)
        elif self.state == "break":
            kick_back = kicks_recent >= (2 if since > 2.5 else 3)
            rising = v2 and self.build_score > self.BUILD_RISING   # es baut sich auf (Wirbel zaehlt als Kick): erst der Aufbau
            if self.build_hold > c["build_hold_s"]:
                self._enter("build", now)
            elif not rising and present and returned and (kick_back or (f.db_short > (self.ref_db if v2 else dbl) - 2.5
                                                                          and (not v2 or kicks_recent >= 1))
                                                          or (since > c["break_max_s"] and not v2)):
                # v2: ein Break endet nur mit Beat im Drop (lauter ohne Kick = Aufbau), zu lang = kein Drop
                self._enter("drop", now)
            elif since > c["break_max_s"]:                    # die Musik ist waehrend des Breaks verstummt: kein Drop
                self._enter("normal", now)
        elif self.state == "build":
            self.build_high = max(self.build_high, self.high_s) if since > 0.1 else self.high_s
            if f.db_short < max_db - 8.0:
                self._enter("gap", now)
            elif (v2 and since > 2.0 and kicks_recent >= 2 and present
                  and self.high_s < self.build_high - self.BUILD_DROP_HIGH):   # Rauschen/Wirbel endet, Beat da: Drop ohne Pause
                self._enter("drop", now)
            elif since > c["build_max_s"] or (score < 0.15 and since > 4.0):
                self._enter("normal", now)
        elif self.state == "gap":
            kicked = any(t > self.state_t for t in self.kick_times)
            if present and returned and (kicked or f.db_short > dbl - 6.0 or since > c["gap_max_s"]):
                self._enter("drop", now)
            elif since > c["gap_max_s"]:                      # es bleibt still (Pause, Ende des Liedes): kein Drop
                quiet = present and kicks_recent == 0 and f.db_short < self.ref_db - c["break_below_db"]
                self._enter("break" if v2 and quiet else "normal", now)   # v2: leise ohne Kick weiter = Break
        elif self.state == "drop" and since > c["drop_len_s"]:
            self._enter("normal", now)
        target = {"break": c["break_dim"], "idle": 0.12, "gap": 0.0}.get(self.state, 1.0)
        self.dim += (1 - math.exp(-dt / 0.6)) * (target - self.dim)

    TALK_S = 6.0            # so lange muss es nach Sprache aussehen
    TALK_CLAR = 0.15        # Schlag-Klarheit darunter: kein regelmaessiger Schlag (Musik mit Beat um 0,6, weicher Beat 0,3)
    TALK_KICKS = 4          # mindestens so viele Anschlaege in 4 s (Stimme loest die Kick-Erkennung aus; Applaus, Flaechen nicht)
    TALK_END_CLAR = 0.3     # Ende: ein Schlag ist da (2 s im Mittel) ...
    TALK_END_QUIET_S = 4.0  # ... oder so lange kein Anschlag mehr

    def _talk_update(self, now):
        """Sprache erkennen (Fehlerbericht 25.11.2026: ein Sprecher am Line-In, jede Wortpause wurde zum Drop).
        Sprache = lange kein regelmaessiger Schlag (Schlag-Klarheit niedrig), aber viele Anschlaege (die Stimme loest die
        Kick-Erkennung aus). Applaus, Flaechen und Breaks haben keine Anschlaege, Musik einen regelmaessigen Schlag.
        Ohne Messung der Klarheit (Simulator) und ohne Einstellung nie: Licht wie frueher."""
        clar = getattr(self.src, "beat_clarity", None)
        if self.cfg["speech_guard"] < 0.5 or clar is None or clar < 0:
            self.talk, self.talk_t = False, None
            self.talk_clar.clear()
            return False
        self.talk_clar.append((now, float(clar)))
        while self.talk_clar and now - self.talk_clar[0][0] > self.TALK_S:
            self.talk_clar.popleft()
        kicks = len(self.kick_times)                          # Anschlaege der letzten 4 s
        if self.talk:
            recent = [c for t, c in self.talk_clar if now - t < 2.0]
            beat = bool(recent) and sum(recent) / len(recent) >= self.TALK_END_CLAR
            quiet = not self.kick_times or now - self.kick_times[-1] > self.TALK_END_QUIET_S
            if beat or quiet:
                self.talk, self.talk_t = False, None
        else:                                                 # TALK_S am Stueck: unklar UND Anschlaege (ein Beat, der
            recent = [c for t, c in self.talk_clar if now - t < 2.0]   # nach Flaeche einsetzt, ist in 2-3 s klar)
            cand = bool(recent) and sum(recent) / len(recent) < self.TALK_CLAR and kicks >= self.TALK_KICKS
            if not cand:
                self.talk_t = None
            elif self.talk_t is None:
                self.talk_t = now
            elif now - self.talk_t >= self.TALK_S:
                self.talk = True
        return self.talk

    def _update_loud(self, f, dt):
        """Helligkeit folgt Lautstaerke: Faktor fuer das normale Licht, wenn eine Passage leiser ist als das Lied sonst.
        Mit Mixxx und analysiertem Lied aus der Lautstaerkekurve der Analyse (0-100 je Lied), sonst aus dem Audiosignal
        im Vergleich zu den lauten Teilen (dB, schnell nach oben, ueber eine Minute nach unten)."""
        c = self.cfg
        if self.state in ("idle", "gap") or f.silent:
            self.loud_ref = None                                 # neue Musik: Bezug neu
        elif self.loud_ref is None or f.db_short > self.loud_ref:
            self.loud_ref = f.db_short if self.loud_ref is None else self.loud_ref + (1 - math.exp(-dt / 2.0)) * (f.db_short - self.loud_ref)
        else:
            self.loud_ref += (1 - math.exp(-dt / 60.0)) * (f.db_short - self.loud_ref)
        if c["loud_dim"] <= 0:
            self.loud_k = 1.0
            return
        d = 0.0
        if self.state == "normal":
            m = self.mx
            en = ((m.get("bar") or {}).get("en") or []) if m and m.get("plan") and m.get("deck") is not None else []
            if en and m.get("dur", 0) > 0:                        # Mixxx mit Analyse: Kurve an der Stelle (mit Vorlauf)
                i = int((m["pos"] + c["mixxx_lead_s"]) / m["dur"] * len(en))
                d = clamp01((75.0 - en[max(0, min(len(en) - 1, i))]) / 50.0)
            elif self.loud_ref is not None:                       # ohne Analyse: das Audiosignal
                d = clamp01((self.loud_ref - f.db_short - 2.0) / max(1.0, c["loud_dim_db"] - 2.0))
        target = 1.0 - c["loud_dim"] * (1.0 - c["loud_dim_min"]) * d
        self.loud_k += (1 - math.exp(-dt / 1.0)) * (target - self.loud_k)

    def _update_tier(self, f, now, dt):
        """Intensitaetsstufe mit Hysterese und Mindestdauer, damit die Muster nicht staendig wechseln."""
        rel = clamp01((f.db_short - f.db_long + 8.0) / 16.0)       # laut/leise relativ zum Song
        c = self.cfg
        raw = 0.7 * self.arousal + 0.3 * rel + c["energy_bias"] + self._track_boost() + self._style("energy", 0.0)
        self.inten += (1 - math.exp(-dt / c["inten_tc"])) * (raw - self.inten)
        up = (c["tier_up_1"], c["tier_up_2"], c["tier_up_3"])
        down = tuple(u - c["tier_hyst"] for u in up)
        new = self.tier
        if self.tier < 3 and self.inten > up[self.tier]:
            new = self.tier + 1
        elif self.tier > 0 and self.inten < down[self.tier - 1]:
            new = self.tier - 1
        if (c["drop_step"] > 0.5 and self.drop_pre is not None
                and now - self.last_drop < self.DROP_STEP_WIN * c["boost_decay_s"]):
            new = min(new, self.drop_pre)                     # nach dem Drop: nicht ueber die Stufe von vorher (der Schub hebt nicht)
        if new != self.tier and now - self.tier_t > c["tier_min_s"]:
            self.tier, self.tier_t = new, now

    def _note_played(self):
        """Titel merken, sobald ein erkanntes Lied in Mixxx hoerbar spielt (fuer die Seite Statistik, hoechstens 300)."""
        m = self.mx
        if not m or not m.get("plan") or m.get("deck") is None or not m.get("playing") or not m.get("title"):
            return
        if m["title"] != self.played_last:
            self.played_last = m["title"]
            self.played.append({"t": round(time.time()), "title": str(m["title"])[:80], "genre": str(m.get("genre") or "")[:40],
                                "lvl": m.get("lvl"), "style": self._style_key() or ""})
            del self.played[:-300]

    def _mixxx_has_title(self):
        m = self.mx
        return bool(m and m.get("plan") and m.get("deck") is not None and m.get("playing") and m.get("title"))

    def _titles_tick(self, now, f):
        """Titelerkennung (nur Anzeige, wirkt nie aufs Licht): neu erkannte Lieder kommen in die Liste auf /stats."""
        if self.titles is None:
            return
        radio = self.radio is not None and self.radio.song() is not None       # Titel kommt vom Internetradio: kein Shazam noetig
        new = self.titles.tick(now, self.cfg["songrec_on"] > 0.5, self.cfg["songrec_every"], not f.silent and not self.talk, self._mixxx_has_title() or radio)
        if new:
            if new["genre"]:
                self.live_genres[new["genre"]] = self.live_genres.get(new["genre"], 0) + 1
            name = f"{new['artist']} - {new['title']}" if new["artist"] else new["title"]
            if name != self.played_last:
                self.played_last = name
                self.played.append({"t": round(time.time()), "title": name[:80], "genre": new["genre"], "lvl": None, "style": self._style_key() or ""})
                del self.played[:-300]

    def stats_info(self):
        """Seite Statistik: Bibliothek von der Mac-App (Titel, analysiert, Energie, Tempo, Genres), je Stil, gespielte Titel."""
        lk = self.mixxx
        st = getattr(lk, "stats", None) if lk is not None else None
        out = {"lib": st, "age": round(time.time() - lk.stats_t) if st else None, "played": self.played[::-1][:200],
               "since": round(self.started_wall)}
        if st:
            styles = {k: [0, 0] for k in STYLES}
            none = [st["n"], st["a"]]                             # ohne Stil (unbekanntes Genre oder ohne Genre)
            for g, n, a in st["g"]:
                k = self.gstyles.style(g)
                if k:
                    styles[k][0] += n
                    styles[k][1] += a
                    none[0] -= n
                    none[1] -= a
            out["styles"] = styles
            out["nostyle"] = [max(0, none[0]), max(0, none[1])]
        return out

    def _style_key(self):
        """Stil von Hand im Panel, sonst Genre-Stil des laufenden Liedes aus Mixxx (nur mit erkanntem Lied, hoerbarem
        Deck und Schalter), sonst Genre-Stil aus der Titelerkennung (Schalter songrec_style), sonst None."""
        if self.style_man:
            return self.style_man
        m = self.mx
        if m and m.get("plan") and m.get("deck") is not None:
            if self.cfg["mixxx_genre_style"] < 0.5:
                return None
            return self.gstyles.style_of_groups(m.get("grp")) or self.gstyles.style(m.get("genre"))   # Gruppe (Weihnachten) vor Genre
        rs = self.radio.song() if self.radio is not None and not self._mixxx_has_title() else None
        if rs and rs.get("genre") and self.cfg["radio_style"] >= 0.5:      # Internetradio: Genre zum Titelfeld (iTunes)
            return self.gstyles.style(rs["genre"])
        song = self.titles.song if self.titles is not None and self.titles.active else None
        if song and self.cfg["songrec_style"] >= 0.5:
            return self.gstyles.style(song["genre"])
        return None

    def _style(self, what, default):
        k = self._style_key()
        return STYLES[k].get(what, default) if k else default        # nicht jeder Stil legt jede Eigenschaft fest

    def _cue_hit(self):
        """True im Bild, in dem das laufende Lied in Mixxx ueber den naechsten Hotcue laeuft (nur vorwaerts um genau einen,
        nicht beim Springen oder Liedwechsel). Nur mit Plan und Einstellung mixxx_cue_change."""
        m, c = self.mx, self.cfg
        if not m or not m.get("plan") or not m.get("playing") or c["mixxx_cue_change"] < 0.5 or "cue_n" not in m:
            self.cue_prev = None
            return False
        cur = (m.get("cue_id"), m["cue_n"])
        prev, self.cue_prev = self.cue_prev, cur
        return prev is not None and prev[0] == cur[0] and cur[1] == prev[1] + 1

    def _track_boost(self):
        """Zuschlag zur Energie nach der Energiestufe (1 bis 9) des laufenden Liedes aus Mixxx: je Stufe ueber der Mitte
        mehr, darunter weniger. Nur solange ein Deck mit erkanntem Lied hoerbar spielt; ohne Mixxx oder Stufe immer 0."""
        m = self.mx
        if not m or not m.get("plan") or m.get("deck") is None:
            return 0.0
        lvl = m.get("lvl")
        if lvl is None:
            return 0.0
        return (min(lvl, 10) - self.cfg["mixxx_energy_mid"]) * self.cfg["mixxx_energy_w"]

    def _base_tier(self):
        """Stufe nach der Musik, oder die per Tempo-Knopf vorgegebene (Langsam = 1, Mittel = 2, Schnell = 3)."""
        return AUTO_SPEED_TIER.get(self.auto_speed, self.tier) if self.sc is None else self.tier

    def _matrix_tick(self, now, dt, f, new_beats, new_kicks, new_hats, frozen):
        """Zustand der Show fuer die Pixel-Matrix. Liest nur, aendert nichts am uebrigen Licht."""
        c = "hue"
        if self.auto_rainbow or self.auto_color == "rainbow":
            c = "rainbow"
        elif self.auto_color in ("white", "uv", "multi"):
            c = self.auto_color
        st = self.state
        if st == "drop" and now - self.state_t >= max(0.8, self.cfg["drop_len_s"]):
            st = "normal"
        quiet = f.silent or self.override is not None or frozen
        s = {"t": now, "dt": dt, "bpm": self.bpm, "beat": bool(new_beats) and not quiet, "kick": bool(new_kicks) and not quiet,
             "hat": bool(new_hats) and not quiet and self.cfg["hat_amount"] > 0, "level": self.level_s,
             "bass": f.bass, "mid": f.mid, "high": f.high, "hue": self.hue, "cmode": c, "state": st, "tier": self.eff_tier(),
             "build_p": self.build_prog, "phrase": self.step // (8 * max(1, self.bar_len)), "strobe": bool(self.strobe),
             "override": self.override, "frozen": frozen, "master": self.master * self.loud_k,
             "dark": self.sc is not None and self.sc.special == "laser",
             "master_raw": self.master,                            # Matrix mit eigener Huellkurve: ohne loud_k
             "loud": (1.0 if self.loud_ref is None or f.silent else      # 1 = so laut wie die lauten Teile, 0 = pm_loud_db leiser
                      clamp01(1.0 - (self.loud_ref - f.db_short) / max(1.0, self.cfg["pm_loud_db"])))}
        m = self.mx or {}
        if self.showman is not None and self.showman.active() and self.showman.doc_name:
            s["song"] = {"show": self.showman.doc_name}            # Bilder zum Lied: Show mit eigener MP3
        elif m.get("connected") and m.get("deck") is not None and m.get("title"):
            s["song"] = {"title": m["title"], "dur": m.get("dur") or 0}
        elif self.local is not None and self.local.song() is not None:
            s["song"] = self.local.song()                          # Musik-DB im Browser: Bilder und Text ueber den Pfad
        elif self.radio is not None and self.radio.song() is not None:
            rs = self.radio.song()
            s["song"] = {"title": rs["artist"] + " - " + rs["title"] + ("" if rs.get("done") else " (sucht)"), "radio": rs}   # Cover kommt nach
        if self.cfg["pm_lyrics"] > 0.5:
            s["lyric"] = self._matrix_lyric(now)
        try:
            self.matrix.tick(s, self.cfg)
        except Exception as e:                                  # noqa: BLE001  die Matrix darf die Show nie anhalten
            self.note = f"Pixel-Matrix: {e}"
            self.matrix = None

    DROP_STEP_WIN = 2.0         # drop_step: so viele Abklingzeiten (boost_decay_s) nach dem Drop haelt die Stufe von vorher

    def eff_tier(self):
        """Wirksame Stufe: Break = ruhig, Build/Drop = Peak. drop_step (Wunsch 23.11.2026, ruhiges Lied, jeder Refrain ein
        Drop, danach 20 s Vollgas): Build/Drop nur eine Stufe ueber der Stufe davor, danach zurueck auf sie."""
        if self.state == "break":
            return 0
        if self.talk and self.sc is None and self.auto_speed not in AUTO_SPEED_TIER:
            return 0                                     # Sprache: ruhig (Effektband ruhig, keine Blitze), Tempo von Hand geht vor
        if self.state in ("build", "drop"):
            if self.cfg["drop_step"] > 0.5:
                pre = self.drop_pre if (self.state == "drop" and self.drop_pre is not None) else self.tier
                return min(3, pre + 1)
            return 3
        return self._base_tier()

    def _write_log(self, f, now):
        if self.log is None or now - self.log_t < 1.0:
            return
        self.log_t = now
        self.log.writerow([f"{now - (self.t_first or now):.1f}", self.state, f"{f.bpm:.1f}", f"{f.level:.2f}",
                           f"{f.db_short:.1f}", f"{f.db_long:.1f}", f"{f.centroid:.2f}", f"{f.high:.2f}",
                           f"{f.mode:+.2f}", f"{f.key_conf:.2f}", f"{len(self.kick_times)/4.0:.1f}",
                           f"{self.arousal:.2f}", f"{self.valence:.2f}", self.quadrant,
                           f"{self.build_score:.2f}"])
        self._logfile.flush()

    @staticmethod
    def _beam_merge(cur, b):
        """Beam-Werte pruefen und in cur uebernehmen (Teile genuegen, Gobo 0 bis 5, sonst 0 bis 100 %)."""
        if not isinstance(b, dict):
            raise ValueError("Beam: auto oder Werte erwartet")
        nb = dict(BEAM_DEFAULT)
        nb.update(cur or {})
        for k, v in b.items():
            if k not in BEAM_DEFAULT:
                raise ValueError(f"Beam: unbekannter Wert {k}")
            if k == "gobo":
                nb[k] = max(0, min(len(BEAM_GOBOS) - 1, int(v)))
            else:
                nb[k] = max(0.0, min(100.0, float(v)))
        return nb

    def _levels_load(self):
        """Hauptdimmer, Gruppen-Dimmer und Blitze pro Sekunde aus levels.json (fehlt sie oder ist sie defekt: Startwerte).
        Die Strobe-Erlaubnis wird nie gespeichert, ohne sie bleibt es bei hoechstens 3 Blitzen pro Sekunde (_blitz_rate)."""
        if not self.levels_path or not os.path.exists(self.levels_path):
            return
        try:
            with open(self.levels_path, encoding="utf-8") as f:
                d = json.load(f)
            if "master" in d:
                self.master = max(0.0, min(1.0, float(d["master"])))
            for k, v in (d.get("glevel") or {}).items():
                if k in self.glevel:
                    self.glevel[k] = max(0.0, min(1.0, float(v)))
            if "blitz_hz" in d:
                self.blitz_hz = snap_blitz(float(d["blitz_hz"]))
            if isinstance(d.get("beam"), dict):
                self.beam = self._beam_merge(None, d["beam"])
                self.beam_man = False                  # Start immer im Autopilot, die Werte bleiben gemerkt
        except (OSError, ValueError, TypeError, AttributeError) as e:
            print(f"Hinweis: levels.json nicht lesbar ({e}), Dimmer auf Startwerten")

    def _levels_save(self):
        self.levels_dirty_t = None
        if not self.levels_path:
            return
        try:
            tmp = self.levels_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"master": round(self.master, 3), "glevel": {k: round(v, 3) for k, v in self.glevel.items()},
                           "blitz_hz": self.blitz_hz, "beam": self.beam,
                           "beam_man": self.beam_man}, f, indent=1)
            os.replace(tmp, self.levels_path)
        except OSError:
            pass

    def close(self):
        if self.levels_dirty_t is not None:
            self._levels_save()
        if self.matrix is not None:                             # Dienstende: Matrix schwarz
            self.matrix.close()
        if self.fog_hm_on:                                      # Dienstende: Nebelschub sofort aus
            self.fog_hm_on = False
            try:
                self.home.fog_fire(False, wait=True)
            except Exception:                                  # noqa: BLE001
                pass
        if self.home is not None:
            self.home.stop()
        if self.link_out is not None:
            self.link_out.close()
        if self.log is not None:
            self._logfile.close()

    # ---- Gruppen: alle in derselben Farbe, Unterschiede nur in Helligkeit/Muster ------------
    def _render_bars(self, now, dt, flash):
        """Docooler. Stufe 0: langsames Atmen | 1: weiche Welle ueber die Zonen |
        2: ganz hell/aus, jede Zone wechselt alle 2 Beats | 3: wechselt jeden Beat."""
        n = max(1, len(self.bars))
        tier = self.eff_tier()
        mask = self._dc_update(dt)
        bpm = self.bpm if self.bpm > 0 else 110.0
        half = 2 if self.bar_len == 4 else self.bar_len             # "alle 2 Beats" bzw. alle 3 Beats (ein Takt) bei 3/4
        for i, (fx, zi) in enumerate(self.bars):
            if tier == 0:
                tgt = 0.35 * (0.5 + 0.5 * math.sin(2 * math.pi * (now / 8.0 + i / n)))
                b = self.smooth(f"bar{i}", tgt, dt, release=0.5, attack=0.3)
            elif tier == 1:
                ph = now * bpm / 60.0 / self.bar_len - i / n
                tgt = 0.8 * max(0.0, math.sin(2 * math.pi * ph)) ** 2
                b = self.smooth(f"bar{i}", tgt, dt, release=0.3, attack=0.12)
            else:
                k = self.step if tier == 3 else self.step // half
                b = self.smooth(f"bar{i}", 1.0 if (i + k) % 2 == 0 else 0.0, dt, release=0.08)
            if mask is not None:
                b *= mask.get(fx, 1.0)
            b *= self.loud_k * self.pulse_k                          # Helligkeit folgt Lautstaerke und Beat-Puls (Blitze bleiben voll)
            r, g, bl, wv, uvc = self._acolor(b, i / max(1, n - 1), fx, zi)
            self.paint(fx, zi, max(r, flash), max(g, flash), max(bl, flash), w=max(wv, flash), uv=uvc)
            fx.set("strobe", 0)

    # ---- Abwechslung Docooler/Vega (AUTO) ------------------------------------------------------------
    DC_POOLS = {0: ("solo", "aussen", "innen"),                  # ruhig: meist 1 oder 2 Docooler
                1: ("aussen", "innen", "wandern", "seiten"),
                2: ("wechsel", "seiten", "aussen", "innen")}

    def _dc_pick(self, tier):
        pool = [p for p in self.DC_POOLS[tier] if p != self.dc_pat] or list(self.DC_POOLS[tier])
        self.dc_pat = self._dc_rng.choice(pool)
        if self.dc_pat == "solo":
            self.dc_solo = self._dc_rng.randrange(len(self.dc_order))

    def _dc_targets(self, tier):
        """Ziel je Position (0 = links aussen ... n-1 = rechts aussen): 1 = an, 0 = dunkel."""
        n, bl, pat = len(self.dc_order), self.bar_len, self.dc_pat
        outer = {0, n - 1}
        if pat == "wechsel":                                     # aussen und innen wechseln jeden Takt
            pat = "aussen" if (self.step // bl) % 2 == 0 else "innen"
        if pat == "solo":
            return [1.0 if i == self.dc_solo else 0.0 for i in range(n)]
        if pat == "aussen":
            return [1.0 if i in outer else 0.0 for i in range(n)]
        if pat == "innen":
            return [0.0 if i in outer else 1.0 for i in range(n)]
        if pat == "wandern":                                     # einzeln, von aussen nach innen: 1, 6, 2, 5
            seq = []
            lo, hi = 0, n - 1
            while lo <= hi:
                seq += [lo] if lo == hi else [lo, hi]
                lo, hi = lo + 1, hi - 1
            cur = seq[(self.step // 2) % len(seq)]
            return [1.0 if i == cur else 0.0 for i in range(n)]
        # seiten: linke und rechte Haelfte im Wechsel, jeden Takt
        left = (self.step // bl) % 2 == 0
        return [1.0 if (i < n / 2) == left else 0.0 for i in range(n)]

    def _dc_update(self, dt):
        """Gruppierung der Docooler (Einstellung dc_mix): alle dc_mix_bars Takte und nach jedem Drop eine neue, je nach
        Stufe aus einer anderen Auswahl. Liefert den Faktor je Docooler (weich ueberblendet) oder None = alle wie bisher
        (Stufe 3, Drop, Einstellung aus). Setzt dazu dc_vega: der Vega in der Mitte leuchtet, wenn die inneren dunkel sind."""
        tier = self.eff_tier()
        new_drop = self.dc_drop_seen != self.last_drop
        self.dc_drop_seen = self.last_drop
        if self.cfg["dc_mix"] < 0.5 or tier >= 3 or len(self.dc_order) < 2:
            self.dc_mask = None
            if new_drop:
                self.dc_pat = None                               # nach dem Drop gleich eine neue Gruppierung
            return None
        phrase = (self.step // (max(1, int(self.cfg["dc_mix_bars"])) * self.bar_len), self.cue_seq)   # auch nach einem Hotcue neu
        if self.dc_pat not in self.DC_POOLS[tier] or phrase != self.dc_phrase or new_drop:
            self._dc_pick(tier)
        self.dc_phrase = phrase
        tg = self._dc_targets(tier)
        rel = 0.08 if tier >= 2 else 0.3
        m = {f: self.smooth(f"dcm{j}", tg[j], dt, release=rel, attack=rel) for j, f in enumerate(self.dc_order)}
        self.dc_mask = m
        inner = [m[f] for j, f in enumerate(self.dc_order) if 0 < j < len(self.dc_order) - 1] or list(m.values())
        free = 1.0 - sum(inner) / len(inner)
        self.dc_vega = free * (0.6 if tier == 0 else 1.0)       # ruhig: nur sanft dazu
        return m

    def _render_wash(self, now, dt, flash):
        """4in1-Washes: nur ab Stufe 2. Stufe 2: Paare im Wechsel alle 2 Beats, Stufe 3: jeden Beat."""
        tier = self.eff_tier()
        pos = self.step % self.bar_len                                 # Zaehlzeit im Takt (0 = die Eins)
        for i, (fx, zi) in enumerate(self.wash):
            if tier < 2:
                hit, peak = False, 0.0
            elif tier == 2:
                hit = pos == (0 if i % 2 == 0 else 2)
                peak = 0.95 * self.beat_env if hit else 0.0
            else:
                hit = (self.step % 2 == 0) == (i % 2 == 0)
                if self.bar_len == 4:
                    hit = (self.step % 4) in ((0, 2) if i % 2 == 0 else (1, 3))
                peak = max(0.95 * self.beat_env, 0.6 * self.kick_env) if hit else 0.0
            b = self.smooth(f"wash{i}", self.dim * self.loud_k * self.pulse_k * peak, dt)
            r, g, bl, wv, uvc = self._acolor(b, i / max(1, len(self.wash) - 1), fx, zi)
            uv = (0.8 * self.kick_env if (tier >= 3 and hit) else 0.0) + flash
            if not self._style("uv", True):
                uv = 0.0                                                 # Stil ohne UV (Weihnachten)
            self.paint(fx, zi, max(r, flash), max(g, flash), max(bl, flash), w=max(wv, flash), uv=max(uv * self.dim, uvc))

    def _auto_solo_key(self, sm_on):
        """AUTO "Geraete der Reihe nach": Schluessel der Gruppe, die dran ist, sonst None (alle wie immer, auch beim Drop)."""
        if self.cfg["auto_solo"] < 0.5 or sm_on or self.sc is not None or self.override or self.state not in ("normal", "break", "build"):
            return None
        order = [k for k in AUTO_SOLO_ORDER if k != "nano" or self.nano]
        return order[self.solo_i % len(order)]

    def _lyric_source(self, now):
        """Woher der Liedtext gerade kommt: {src, name, lines, plain, pos}, sonst None. pos None = Stelle im Lied unbekannt. Liest nur, das Licht wartet nie."""
        if self.showman is not None and self.showman.active():
            lines, pos = self.showman.lyric_pos(now)
            return {"src": "show", "name": self.showman.doc_name, "lines": lines, "plain": "", "pos": pos}
        if self.cfg["lyrics_auto"] < 0.5 or self.lyric_cache is None:
            return None
        m = self.mx
        if m and m.get("playing") and m.get("deck") is not None and m.get("title"):
            e = self.lyric_cache.get_entry(m["title"], m.get("dur", 0.0), now)
            return {"src": "mixxx", "name": m["title"], "dur": m.get("dur", 0.0), "lines": e["lines"], "plain": e["plain"],
                    "pos": m.get("pos_f", 0.0) + max(0.0, now - m.get("t", now)) * m.get("rate", 1.0)}
        song = self.titles.song if self.titles is not None else None             # Musik ohne Mixxx: was die Titelerkennung gefunden hat
        if not song or self.state == "idle" or self.talk:                       # Sprache: kein Liedtext (25.11.2026)
            return None
        name = f"{song['artist']} - {song['title']}" if song.get("artist") else song["title"]
        e = self.lyric_cache.get_entry(name, 0.0, now)
        pos = None
        if self.lyric_tap and self.lyric_tap[0] == name:                         # von Hand angetippt: gilt, solange das Lied laeuft
            pos = self.lyric_tap[1] + now - self.lyric_tap[2]
        elif "offset" in song:
            pos = song["offset"] + now - song["pos_t"]
        return {"src": "live", "name": name, "dur": 0.0, "lines": e["lines"], "plain": e["plain"], "pos": pos}

    def _matrix_lyric(self, now):
        """Pixel-Matrix (21.11.2026): die gesungene Zeile mit Anfang, Ende, Stelle und ob sie zum Refrain gehoert
        (Zeile kommt im Lied mehrmals vor). Fragt die Quelle hoechstens alle 0,25 s, dazwischen laeuft die Stelle weiter."""
        if self.mlyr is None or not (0 <= now - self.mlyr[0] < 0.25):
            try:
                src = self._lyric_source(now)
            except Exception:                                   # noqa: BLE001  Liedtext haelt die Matrix nie auf
                src = None
            if src and src["pos"] is not None and src["lines"]:
                key = (src["name"], len(src["lines"]))
                rep = self.mlyr[3] if self.mlyr is not None and self.mlyr[2] == key else lyric_repeats(src["lines"])
                self.mlyr = (now, src, key, rep)
            else:
                self.mlyr = (now, None, None, None)
        t0, src, _, rep = self.mlyr
        if src is None:
            return None
        s = dict(src, pos=src["pos"] + (now - t0))
        i = self._lyric_index(s)
        if i < 0:
            return None
        return {"text": s["lines"][i][1], "t0": s["lines"][i][0], "t1": lyric_end(s["lines"], i), "pos": s["pos"],
                "chorus": i in rep, "i": i}

    @staticmethod
    def _lyric_index(s):
        """Nummer der aktuellen Zeile, sonst -1."""
        if not s or s["pos"] is None:
            return -1
        cur = -1
        for i, x in enumerate(s["lines"]):
            if x[0] > s["pos"]:
                break
            cur = i if s["pos"] < lyric_end(s["lines"], i) and x[1] else -1
        return cur

    def lyric_line(self, now):
        s = self._lyric_source(now)
        i = self._lyric_index(s)
        return s["lines"][i][1] if i >= 0 else ""

    def lyric_status(self, now):
        """Fuer den Status im Panel: Zeile, Nummer, gibt es Text zum Mitlesen, darf man antippen."""
        s = self._lyric_source(now)
        i = self._lyric_index(s)
        return {"lyric": s["lines"][i][1] if i >= 0 else "", "lyric_i": i, "lyric_avail": bool(s and (s["lines"] or s["plain"])), "lyric_key": s["name"] if s else "",
                "lyric_tap": bool(s and s["src"] == "live" and s["lines"]), "lyric_again": bool(s and s["src"] != "show"),
                "lyric_msg": self.lyric_cache.msg if self.lyric_cache is not None and s and s["src"] != "show" else ""}

    def lyric_full(self, now):
        """Der ganze Text zum Aufklappen."""
        s = self._lyric_source(now)
        return {"src": s["src"], "name": s["name"], "lines": s["lines"], "plain": s["plain"]} if s else {"src": "", "name": "", "lines": [], "plain": ""}

    def lyric_refetch(self, now, query=None):
        """Knopf Text neu suchen: fuer das laufende Lied aus Mixxx oder der Titelerkennung. In einer Show gibt es dafuer den Knopf im Editor."""
        s = self._lyric_source(now)
        if not s or s["src"] == "show":
            raise ValueError("Gerade laeuft kein Lied, zu dem sich der Text suchen laesst")
        self.lyric_cache.refetch(s["name"], s["dur"], str(query or "").strip()[:160] or None)
        self.lyric_tap = None
        return {"ok": True, "name": s["name"]}

    def lyric_sync(self, now, i):
        """Antippen: Diese Zeile wird gerade gesungen. Nur ohne Mixxx und Show, dort kennt der Pi die Stelle selbst."""
        s = self._lyric_source(now)
        if not s or s["src"] != "live" or not 0 <= i < len(s["lines"]):
            raise ValueError("Hier laesst sich die Stelle nicht antippen")
        self.lyric_tap = (s["name"], s["lines"][i][0], now)
        return {"ok": True}

    def _show_panel_scene(self, now):
        """Szene aus dem Panel, die die Show gerade will. Nur normale Szenen: die Szene Laser und Sondertasten nie, Laser gehen nur ueber Laser-Clips."""
        name = self.showman.panel_scene(now)
        return next((s for s in self.scene_defs if s.name == name and not s.special), None) if name else None

    def _nano_effect_tick(self, now, sm_on):
        """Showmanager: Effekt des Nanoleaf waehlen oder zurueck zu den Einzelpanels. BLACKOUT, ALLES HELL und FREEZE gehen vor."""
        if self.showman is None or self.output is None:
            return
        want = self.showman.nano_effect(now) if sm_on and not self.override and not self.freeze else None
        if want != self._nano_fx:
            self._nano_fx = want
            for snd in self.output.senders.values():
                if hasattr(snd, "set_effect"):
                    snd.set_effect(want)

    def _render_nano(self, now, dt, flash):
        """Nanoleaf-Panels: folgen der Stimmung wie die Ambiente-Lichter, aber raeumlich (Lage der Panels).
        Stufe 0: langsame Farbwolke | 1: wandernde Welle | 2: Lichtband im Takt | 3: linke/rechte Haelfte im Wechsel."""
        if not self.nano:
            return
        tier = self.eff_tier()
        bpm = self.bpm if self.bpm > 0 else 110.0
        bl = self.bar_len
        for fx, zi in self.nano:
            x = fx.extra.get("x", 0.5)
            if tier == 0:
                tgt = 0.45 + 0.20 * math.sin(2 * math.pi * (now / 12.0 - x))
            elif tier == 1:
                tgt = 0.30 + 0.55 * max(0.0, math.sin(2 * math.pi * (now * bpm / 60.0 / (2 * bl) - x))) ** 2
            elif tier == 2:
                pos = (now * bpm / 60.0 / (2 * bl)) % 1.0
                d = min(abs(x - pos), 1.0 - abs(x - pos))
                tgt = 0.20 + 0.80 * math.exp(-(d / 0.22) ** 2) * (0.5 + 0.5 * self.beat_env)
            else:
                on = (x < 0.5) == (self.step % 2 == 0)
                tgt = max(0.25, (0.95 * self.beat_env if on else 0.15) + 0.6 * self.kick_env * (1.0 if on else 0.4))
            b = self.smooth(f"nano{fx.name}", self.dim * self.loud_k * self.pulse_k * tgt, dt, release=0.25, attack=0.08)
            if self.cfg["hat_nano"] >= 0.5 and self.nano[self.hat_panel % len(self.nano)][0] is fx:
                b = max(b, self.cfg["hat_amount"] * self.hat_env * self.dim)   # Hi-Hat-Funkeln: dieses Panel leuchtet auf
            if self.auto_color == "uv":                         # UV: die Panels bleiben dunkel (ihr Blau stoert das UV-Licht)
                self.paint(fx, zi, 0, 0, 0)
                continue
            r, g, bb, wv, uvc = self._acolor(b, x, fx, zi, hue_off=(0.06 * x if tier >= 1 else 0.0))
            self.paint(fx, zi, max(r, flash), max(g, flash), max(bb, flash))

    def _section(self):
        """Abschnitt des Liedes laut Analyse (intro, vers, main, break, outro); "" ohne Analyse oder ohne Abschnitte."""
        m = self.mx
        return (m.get("section") or "") if m and m.get("plan") else ""

    def _in_main(self):
        """Hauptteil des Liedes: laut Analyse, sonst geschaetzt (Drop oder ab der Stufe Party)."""
        s = self._section()
        return s == "main" if s else (self.state == "drop" or self.eff_tier() >= 2)

    def _hat_gate(self):
        """Darf das Hi-Hat-Funkeln jetzt? Nur im Hauptteil (hat_main) und Anteil der Phrasen (hat_share, je 8 Takte gewuerfelt)."""
        c = self.cfg
        if c["hat_main"] >= 0.5 and not self._in_main():
            return False
        if c["hat_share"] >= 100.0:
            return True
        block = self.step // (8 * self.bar_len)
        if block != self.hat_block:
            self.hat_block, self.hat_lucky = block, self._hat_share_rng.random() * 100.0 < c["hat_share"]
        return self.hat_lucky

    def _update_pulse(self, f, now, dt, beat):
        """Beat-Puls: dieselben Beats wie das Lamperl im Panel. Auf dem Beat volle Helligkeit, dazwischen dunkler.
        Blitzgrenze wie beim Funkeln: ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde; bei schnellen Liedern
        faellt dadurch jeder zweite Beat aus, der Puls bleibt aber auf dem Beat."""
        c = self.cfg
        self.pulse_on = (max(c["beat_pulse"], c["beat_pulse_eb"]) > 0 and not f.silent and self.state in ("normal", "drop")
                         and self.override is None and self.sc is None and not self.freeze
                         and self.beat_t is not None and now - self.beat_t < 2.0)   # ohne Beat nicht dunkel stehen bleiben
        if not self.pulse_on:
            self.pulse_env, self.pulse_k = 1.0, 1.0
            return
        self.pulse_env *= math.exp(-dt / 0.18)
        if beat and now - self.pulse_t >= (0.0 if self.strobe else 0.5):
            self.pulse_env, self.pulse_t = 1.0, now
        self.pulse_k = 1.0 - c["beat_pulse"] / 100.0 * (1.0 - self.pulse_env)

    def _hat_puls(self, fx):
        """Zusaetzliche Helligkeit beim Hi-Hat-Funkeln fuer Derby, 21 Eyes und Vega: hoechstens 60 % (weicher Puls,
        klingt in 0,1 s ab, kein harter Blitz); 0 fuer alle anderen Geraete und abgeschaltete."""
        key = {"derby_4in1_15ch": "hat_derby", "eyes_21": "hat_eyes", "vega_spot_60": "hat_vega"}.get(fx.type)
        if not key or self.cfg[key] < 0.5:
            return 0.0
        return 0.60 * self.cfg["hat_amount"] * self.hat_env * self.dim

    def _render_barlight(self, now, dt, flash):
        """Ambiente in der Bar (Glaeser, Flaschen): sanft, folgt nur dem Pegel, kein Beat-Pulsieren."""
        for i, (fx, zi) in enumerate(self.barlight):
            b = self.smooth(f"barlight{i}", self.dim * self.loud_k * (0.30 + 0.30 * self.level_s), dt * 0.4)
            r, g, bl, wv, uvc = self._acolor(b, 0.5, fx, zi)
            self.paint(fx, zi, max(r, flash), max(g, flash), max(bl, flash), w=max(wv, flash))
            fx.set("strobe", 0)

    def _render_uv(self, now, dt, flash):
        tier = self.eff_tier()
        no_uv = not self._style("uv", True)                  # Stil ohne UV (Weihnachten): UV-Leiste aus, auch beim Blitz
        row = self.step % min(self.bar_len, 4)
        base = 0.0 if no_uv else (self.cfg["uv_base"] / 100.0) ** (1.0 / self.gamma)   # Prozent am Kanal: paint rechnet die Kurve wieder ein
        for fx in self.uv:
            for zi in range(len(fx.zones())):
                if tier == 0:
                    v = 0.0
                elif tier == 1:                       # langsames Wandern, weich
                    v = 0.35 * max(0.0, math.sin(2 * math.pi * (now / 6.0 - zi / 4.0))) ** 2
                elif tier == 2:                       # eine Reihe alle 2 Beats
                    if self.bar_len == 4:
                        v = 1.0 * self.beat_env if (zi == (self.step // 2) % 4 and self.step % 2 == 0) else 0.0
                    else:                                  # 3/4: eine Reihe pro Takt auf der Eins
                        v = 1.0 * self.beat_env if (zi == (self.step // 3) % 4 and self.step % 3 == 0) else 0.0
                else:
                    v = max(0.5 * self.kick_env, 1.0 * self.beat_env if zi == row else 0.0)
                if no_uv:
                    v = 0.0
                v = self.smooth(f"uv{zi}", self.dim * self.loud_k * self.pulse_k * v, dt, release=0.3 if tier <= 1 else None,
                                attack=0.15 if tier <= 1 else None)
                self.paint(fx, zi, 0, 0, 0, uv=v if no_uv else max(v, flash, base))
            fx.set("strobe", 0)

    def _render_fx(self, now, dt, flash):
        tier = self.eff_tier()
        for fx in self.fxs:
            if tier >= 3:
                tgt = max(0.9 * self.kick_env, 0.25 * self.beat_env)
            elif tier == 2:
                tgt = 0.9 * self.beat_env if self.step % self.bar_len == 0 else 0.0   # nur auf der Eins
            else:
                tgt = 0.0
            b = self.smooth("fx" + fx.name, self.dim * self.loud_k * self.pulse_k * tgt, dt)
            b = min(1.0, b + self._hat_puls(fx))                       # Hi-Hat-Funkeln (Derby, 21 Eyes)
            for zi in range(len(fx.zones())):
                r, g, bl, wv, uvc = self._acolor(b, 0.5, fx, zi)
                self.paint(fx, zi, max(r, flash), max(g, flash), max(bl, flash), w=max(wv, flash), uv=uvc)

    def _beam_restore(self):
        self.beam_used = False
        for fx in self.spot:
            for k in ("zoom", "gobo_rot", "prism"):
                if k in fx.map:
                    fx.set(k, fx.defaults.get(k, 0))

    def _render_beam(self):
        self.beam_used = True
        vals = beam_dmx(self.beam)
        for fx in self.spot:
            if "gobo" not in fx.map:
                continue
            fx.preset("gobo", vals["gobo"])
            for k in ("zoom", "gobo_rot", "prism"):
                if k in fx.map:
                    fx.set(k, vals[k])

    def _render_spot(self, now, flash=0.0):
        for fx in self.spot:
            tier = self.eff_tier()
            if tier <= 1:                              # ruhig/sanft: langsames Atmen
                per = 6.0 if tier == 0 else 4.0
                tgt = 0.15 + 0.35 * (0.5 + 0.5 * math.sin(2 * math.pi * now / per))
            else:                                      # Treffer im Takt, dazwischen dunkel
                hit = tier >= 3 or (self.step % self.bar_len) % 2 == 0
                tgt = max(1.0 * self.beat_env, 0.8 * self.kick_env) ** 1.3 if hit else 0.0   # steiler Abfall
            if self.dc_mask is not None:                 # Abwechslung: Vega leuchtet, wo die Mitte dunkel ist
                tgt *= self.dc_vega
            tgt *= self.loud_k * self.pulse_k
            hp = self._hat_puls(fx) * (self.dc_vega if self.dc_mask is not None else 1.0)   # Abwechslung gilt auch fuers Funkeln
            lvl = max(min(1.0, self.smooth("vega", tgt, self.last_dt, release=0.2) + hp), flash)
            fx.set("dimmer", 255 * (clamp01(lvl) ** self.gamma) * self.master)
            fx.set("shutter", 255)
            fx.preset("colorwheel", "white" if (flash > 0.3 or self.auto_color == "white") else self._wheel_auto(now, fx))
            gobos = ["open", "star", "spiral", "dots3", "triangle"]
            gname = gobos[(self.step // (16 * self.bar_len)) % len(gobos)] if self.eff_tier() >= 2 else "open"
            fx.preset("gobo", gname)
            fx.set("gobo_rot", 100 if (gname != "open" and self.eff_tier() >= 2) else 0)  # langsam vorwaerts
        if self.cfg["vega_live"] > 0.5:
            self._vega_beam_auto(now)

    def _vega_beam_auto(self, now):
        """Vega-Strahl in AUTO (Einstellung vega_live): Gobo, Drehung, Prisma und Zoom nach Stufe, Tempo und Phase.
        Ruhig: offen, keine Drehung. Hohe Energie: Gobo 1 bis 5 im Wechsel (alle 16 Takte, beim Drop sofort das naechste),
        Drehung nach Stufe und Tempo, Richtung wechselt alle 2 Phrasen. Aufbau: Strahl enger, ab 2 s Prisma.
        Drop: Prisma dreht schnell, Gobo dreht schnell. Werte wie im Bereich Beam (beam_dmx)."""
        bl = self.bar_len
        drop = self.state == "drop" and now - self.state_t < max(0.8, self.cfg["drop_len_s"])
        build = self.state == "build"
        if drop and not self.vg_was_drop:
            self.vg_shift += 1                                   # Drop: gleich das naechste Gobo
        self.vg_was_drop = drop
        tier = self.eff_tier()
        b = {"gobo": 0, "zoom": 100.0, "roll": 50.0, "prism": 0.0}
        if tier >= 2 or build or drop:
            b["gobo"] = 1 + ((self.step // (16 * bl)) + self.vg_shift) % 5
            sp = 0.9 if drop else (0.3 + 0.5 * self.build_prog) if build else (0.55 if tier >= 3 else 0.3)
            sp = min(1.0, max(0.1, sp * max(0.7, min(1.3, (self.bpm or 120.0) / 128.0))))
            dirn = 1.0 if (self.step // (16 * bl)) % 2 == 0 else -1.0
            b["roll"] = 50.0 + dirn * 50.0 * sp
            if drop:
                b["prism"] = 90.0                                # Prisma dreht schnell (im Uhrzeigersinn)
            elif build and self.build_prog > 0.2:
                b["prism"] = 50.0                                # Prisma steht (ab 2 s Aufbau)
            if build:
                b["zoom"] = 100.0 - 40.0 * self.build_prog      # Aufbau: Strahl wird enger
        vals = beam_dmx(b)
        self.beam_used = True                                    # Szene, Stille usw.: Zoom, Drehung, Prisma wieder auf Standard
        for fx in self.spot:
            if "gobo" not in fx.map:
                continue
            fx.preset("gobo", vals["gobo"])
            for k in ("zoom", "gobo_rot", "prism"):
                if k in fx.map:
                    fx.set(k, vals[k])

    def _wheel_auto(self, now, fx=None):
        """Farbe des Vega-Farbrads nach der gewaehlten AUTO-Farbe."""
        if self.auto_rainbow:
            return self.wheel_name(self._rainbow_hue(fx))
        c = self.auto_color
        if c == "uv":
            return "purple"
        if c == "multi":
            return self.wheel_name((self.step * 0.11) % 1.0)
        if c == "rainbow":
            return self.wheel_name((now * 0.08) % 1.0)
        return self.wheel_name(self.hue)

    def _render_ambient(self, now, dt, flash):
        """Theke/Couchtisch (WLED): ruhig, sehr langsame Lautstaerke, kein Beat-Pulsieren.
        Totband: Werte werden nur gesendet, wenn sie sich merklich aendern (kein Flackern)."""
        for ai, fx in enumerate(self.rgb_amb):
            b = max(self.dim * self.loud_k * (0.35 + 0.25 * self.level_amb), self.cfg["amb_idle"])   # nie dunkler als die Grundhelligkeit
            tgt = self._acolor(b, ai / max(1, len(self.rgb_amb) - 1), fx, 0)[:3]
            if self.auto_color == "white":
                tgt = (b, b, b)
            cur = self.amb.get(fx.name, tgt)
            k = 1 - math.exp(-dt / 1.0)
            cur = tuple(c + k * (t - c) for c, t in zip(cur, tgt))
            self.amb[fx.name] = cur
            col = [max(c, flash) for c in cur]
            vals = [int(255 * clamp01(c) * self.master) for c in col]
            old = self.amb_sent.get(fx.name)
            if old is None or flash > 0.05 or max(abs(a - b2) for a, b2 in zip(vals, old)) >= 3:
                self.amb_sent[fx.name] = vals
            fx.set_color(*self.amb_sent[fx.name])
            fx.set("dimmer", 255)
            if "strobe" in fx.map:
                fx.set("strobe", 0)

    def eb_roles(self, fx):
        """Rollen der Effektband-Presets (fixtures.yaml). Mit "Effektband ohne Ton" ohne die soundgesteuerten Presets
        (preset_sound); bleibt eine Rolle leer, das erste nicht soundgesteuerte Preset aus preset_list."""
        roles = fx.extra.get("preset_roles", {})
        if self.cfg["eb_no_sound"] < 0.5:
            return roles
        snd = set(fx.extra.get("preset_sound") or [])
        spare = [p for p in fx.extra.get("preset_list", []) if p not in snd and p not in EB_STROBE][:1]
        return {r: [p for p in lst if p not in snd] or spare for r, lst in roles.items()}

    def eb_no_sound(self, fx, pid):
        """Festes Preset (z. B. aus einer Szene): soundgesteuert und Effektband ohne Ton -> 0 (dann waehlt die Rolle)."""
        return 0 if self.cfg["eb_no_sound"] >= 0.5 and pid in set(fx.extra.get("preset_sound") or []) else pid

    def _eb_manual(self):
        """Effektband-Preset von Hand, falls gewaehlt und erlaubt (Blitz-Presets nur mit Strobe-Erlaubnis)."""
        if self.eb_man and (self.strobe or self.eb_man not in EB_STROBE):
            return self.eb_man
        return None

    def _eb_names(self):
        fx = self.presets[0] if self.presets else None
        names = (fx.extra.get("preset_names") or {}) if fx else {}
        return [[int(k), str(v)] for k, v in sorted(names.items(), key=lambda kv: int(kv[0]))]

    def _render_presets(self, now, flash, burst):
        for fx in self.presets:
            roles = self.eb_roles(fx)
            name = fx.name
            if self.state == "idle":
                role = None                                    # Stille: Effektband dunkel, kein Preset-Wechsel
            elif self.eff_tier() == 0:
                role = "calm"
            elif self.eff_tier() == 1:
                role = "warm"
            else:
                role = "party"
            pid = self.pre_cur.get(name)
            dwell = now - self.pre_t.get(name, -99.0)
            if self.accent_until.get(name, 0) > now:
                pass  # Akzent oder Weiss-Burst laeuft noch
            else:
                if self.accent_until.get(name, 0):  # Akzent vorbei: sofort zurueck zur Rolle
                    self.accent_until[name] = 0
                    self.pre_role[name] = None
                    dwell = 99.0
                if self.state == "drop" and now - self.last_accent > 15 and roles.get("accent") \
                        and not burst:
                    pid = roles["accent"][int(now) % len(roles["accent"])]
                    self.pre_cur[name], self.pre_t[name] = pid, now
                    self.accent_until[name], self.last_accent = now + 3.0, now
                elif self.talk:                                # Sprache: ein ruhiges Preset, kein Wechsel (25.11.2026)
                    if self.pre_role.get(name) != "calm" and roles.get("calm"):
                        self.pre_idx[name] = 0
                        self.pre_cur[name], self.pre_t[name] = roles["calm"][0], now
                        self.pre_role[name] = "calm"
                elif roles.get(role) and (pid is None or (role != self.pre_role.get(name) and dwell > 20)
                                          or dwell > 45):
                    lst = roles[role]
                    self.pre_idx[name] = (self.pre_idx.get(name, -1) + 1) % len(lst)
                    self.pre_cur[name], self.pre_t[name] = lst[self.pre_idx[name]], now
                    self.pre_role[name] = role
            man = self._eb_manual()
            if man:
                fx.set("preset", man)                                    # von Hand im Panel gewaehlt
            elif self.sa_eb is not None and self.accent_until.get(name, 0) <= now and not self.talk:
                fx.set("preset", self.sa_eb["pid"])                      # Szenen-Automatik: passendes Preset fuer ein paar Takte
            elif self.auto_rainbow and self.accent_until.get(name, 0) <= now and not self.talk:
                fx.set("preset", 13)                                     # Regenbogen (wie im Licht-Mix)
            else:
                fx.set("preset", self.pre_cur.get(name, 0))
            lvl = {"idle": 0.0, "break": 0.3, "gap": 0.0}.get(self.state, (0.5 + 0.5 * self.level_s) * self.loud_k)
            if man and self.state in ("idle", "gap"):
                lvl = 0.5                                                # von Hand gewaehlt: auch in der Stille zu sehen (gedimmt)
            if self.state == "build":
                lvl = 0.5 + 0.5 * self.build_prog
            elif self.state == "drop" and now - self.state_t < max(0.8, self.cfg["drop_len_s"]):
                lvl = 1.0
            if flash > 0.5:
                lvl = 1.0
            elif (self.state == "normal" or (self.state == "drop" and now - self.state_t >= max(0.8, self.cfg["drop_len_s"]))) \
                    and self.accent_until.get(name, 0) <= now and not burst and self.sc is None and self.override is None:
                lvl *= 1.0 - self.cfg["hat_eb_duck"] / 100.0 * self.hat_duck     # Funkeln soll sichtbar bleiben
                if self.pulse_on:
                    lvl *= 1.0 - self.cfg["beat_pulse_eb"] / 100.0 * (1.0 - self.pulse_env)
            fx.set("dimmer", 255 * lvl * self.master)

    # ---- Bewegung --------------------------------------------------------------------------
    WAYPOINTS = [(0.1, 0.15), (0.9, 0.15), (0.9, 0.85), (0.1, 0.85), (0.5, 0.5),
                 (0.1, 0.5), (0.9, 0.5), (0.5, 0.1), (0.5, 0.9)]

    def _render_motion(self, now, dt):
        idle = self.state == "idle"
        a = max(self.arousal, 0.9) if self.state in ("drop", "build") else self.arousal
        tier = self.eff_tier()
        aim = self.aim_targets.get(self.aim) if self.aim else None
        if self.move in ("all", "spot"):
            for fx in self.spot:
                if not fx.move16:
                    continue
                st = self.mv.setdefault(fx.name, {})
                lo_p, hi_p = fx.move16["pan"]
                lo_t, hi_t = fx.move16["tilt"]
                verified = bool(fx.extra.get("limits_verified", False))
                mo = self.mo
                if verified and (not idle or aim is not None):
                    if mo is not None and mo.get("hold"):
                        u, v, rate = 0.5, 0.5, 0.0
                    elif aim is not None:                         # Ziel: Bank, Tisch, Tuer, Bar
                        u, v = aim["vega"]
                        rate = 40.0 * self.vega_speed
                    elif mo is not None and mo.get("stop"):       # Stop: bleibt genau dort stehen
                        u, v, rate = 0.5, 0.5, 0.0
                    elif mo is not None:
                        u, v, rate = mo["u"], mo["v"], mo["rate"]
                    elif self.state == "gap":
                        u, v, rate = 0.5, 0.5, 0.0                    # in der Stille stehen bleiben
                    elif self.state == "drop":
                        t = now - self.state_t                        # schneller Schwenk von Ecke zu Ecke
                        u, v, rate = (0.05 if int(t / 0.5) % 2 == 0 else 0.95), 0.25, 90.0
                    elif self.state == "build":
                        u, v = self.WAYPOINTS[(self.step // 2) % len(self.WAYPOINTS)]
                        rate = 60.0
                    elif tier <= 1:                               # ruhig/sanft: langsame Kurve
                        p1, p2, rate = (24.0, 17.0, 10.0) if tier == 0 else (14.0, 10.0, 14.0)
                        u = 0.5 + 0.38 * math.sin(2 * math.pi * now / p1)
                        v = 0.5 + 0.33 * math.sin(2 * math.pi * now / p2 + 1.0)
                    else:                                         # im Takt von Punkt zu Punkt
                        per = self.bar_len if tier == 3 else 2 * self.bar_len
                        u, v = self.WAYPOINTS[(self.step // per) % len(self.WAYPOINTS)]
                        rate = 45.0 if tier == 3 else 25.0
                else:
                    u, v, rate = 0.5, 0.5, 10.0                   # Parkposition
                if mo is not None and mo.get("hold"):
                    pass                                          # Blackout: Position halten
                if fx.mirror["pan"]:      # Richtung spiegeln (links <-> rechts)
                    u = 1.0 - u
                if fx.mirror["tilt"]:
                    v = 1.0 - v
                tp = lo_p + u * (hi_p - lo_p)
                tt = lo_t + v * (hi_t - lo_t)
                rate *= self.vega_speed * self._style("mv", 1.0)        # Genre-Stil: ruhiger oder lebhafter
                st["pan"] = slew(st.get("pan", (lo_p + hi_p) / 2), tp, rate * 256, dt)
                st["tilt"] = slew(st.get("tilt", (lo_t + hi_t) / 2), tt, rate * 256, dt)
                for ax in ("pan", "tilt"):
                    c = int(max(fx.move16[ax][0], min(fx.move16[ax][1], st[ax])))
                    fx.set(ax, c >> 8)
                    fx.set(ax + "_fine", c & 255)
                u_phys = (st["pan"] - lo_p) / max(1.0, hi_p - lo_p)
                self.vega_u = max(0.0, min(1.0, 1.0 - u_phys if fx.mirror["pan"] else u_phys))
        if self.move in ("all", "bars"):
            bpm = self.bpm if self.bpm > 0 else 120.0
            calm = 0.4 if self.state == "break" else 1.0
            amp_f = 0.0 if idle else (3 + 5 * tier + 4 * a) * calm         # Faecher im Takt
            amp_s = 0.0 if idle else self.bar_sway * (8 + 16 * a) * calm    # Schwenk wie der Vega
            sway = (0.5 - self.vega_u) * 2.0 * amp_s      # > 0 = nach links, < 0 = nach rechts
            same = None
            fixtures = [f for f in self.rig.group("bars") if "tilt1" in f.map]
            half_b = 2 if self.bar_len == 4 else self.bar_len          # Beats pro Sprung bei mittlerer Stufe
            for i, fx in enumerate(fixtures):
                ang = 2 * math.pi * now * bpm / 60.0 / (self.bar_period * self.bar_len / 4.0 * (2 if tier <= 1 else 1)) + i * math.pi / 2
                fan = amp_f * math.sin(ang)
                rate = 120.0
                if self.bar_style == "snap" and tier >= 2 and not idle:
                    # Spruenge im Takt: das Geraet faehrt mit seiner eigenen Hoechstgeschwindigkeit
                    k = self.step // (self.bar_every * (1 if tier == 3 else half_b))
                    sgn = 1.0 if (k + i) % 2 == 0 else -1.0
                    fan = sgn * (8 + 20 * a) * calm
                    rate = 255.0
                    sw_eff = sway * 0.6
                else:
                    sw_eff = sway
                same = fx.extra.get("tilt_mode", "opposite") == "same"
                if aim is not None and not (self.mo is not None and self.mo.get("hold")):
                    pair = aim.get("bars_per", {}).get(fx.name) or aim["bars"]
                    st = self.mv.setdefault(fx.name, {})
                    st["t1"] = slew(st.get("t1", 127.0), pair[0], 60.0, dt)
                    st["t2"] = slew(st.get("t2", 127.0), pair[1], 60.0, dt)
                    fx.set("tilt1", st["t1"])
                    fx.set("tilt2", st["t2"])
                    continue
                if self.mo is not None:
                    if self.mo.get("hold") or self.mo.get("stop"):
                        continue
                    sh = self.mo.get("shift", 0.0)                # Feinregler Shift: Versatz der Arme gegeneinander
                    fan = self.mo["fan_amp"] * math.sin(self.mo["fan_phase"] + i * (math.pi / 2 + sh))
                    if self.mo.get("sway_sin"):                   # Ente: alle Arme gemeinsam parallel (mit Shift versetzt)
                        sw_eff = self.mo["sway_amp"] * math.sin(self.mo["fan_phase"] + i * sh)
                    else:
                        sw_eff = (0.5 - self.vega_u) * 2.0 * self.mo["sway_amp"]
                    rate = self.mo["bar_rate"]
                # tilt_mode same: gleiche Werte = Faecher (beobachtet), gegensaetzliche = Schwenk
                #   Tilt1 hoch + Tilt2 runter = beide Balken nach LINKS
                if same:
                    t1, t2 = 127.0 + fan + sw_eff, 127.0 + fan - sw_eff
                else:
                    t1, t2 = 127.0 + fan + sw_eff, 127.0 - fan + sw_eff
                st = self.mv.setdefault(fx.name, {})
                st["t1"] = slew(st.get("t1", 127.0), t1, rate, dt)
                st["t2"] = slew(st.get("t2", 127.0), t2, rate, dt)
                fx.set("tilt1", st["t1"])
                fx.set("tilt2", st["t2"])

    def _blitz_skip(self, fx, hz):
        """Strobe schneller als fuer die Gruppe eingestellt (Einstellung "Strobe: ... blitzt bis")? Dann bleibt sie dunkel."""
        if hz is None:
            return False
        k = GROUP_KEYS.get(fx.group)
        lim = int(round(self.cfg[f"strobe_max_{k}"])) if k else len(BLITZ_RATES)
        return lim < len(BLITZ_RATES) and (lim == 0 or hz > BLITZ_RATES[lim - 1] + 0.01)

    def _render_burst(self, on, level=1.0, age=99, steady=False, hz=None):
        """Strobe-Burst: ALLE Lichter gleichzeitig weiss (mit Helligkeit level), dazwischen alles dunkel.
        age: Bilder seit dem Start. Der Effektband bekommt in den ersten 4 Bildern (100 ms) nur das Preset (Solid weiss) und
        bleibt dunkel, damit WLED es laden kann, bevor er im Takt der anderen mitblitzt."""
        sync = self.cfg["blitz_band_sync"] > 0.5
        amb = set(id(f) for f in self.rgb_amb)
        for fx in self.rig.fixtures:
            if fx.locked:
                continue
            if id(fx) in amb:                                     # Ambiente (Theke, Couchtisch, Barlicht): beim Strobe ruhig aus
                fx.set_color(0, 0, 0)
                if "strobe" in fx.map:
                    fx.set("strobe", 0)
                continue
            zs = fx.zones()
            if not fx.blitz_ok and not steady:                  # zu traege fuer schnelles Ein/Aus (4in1-Washes): beim Strobe dunkel
                for zi in range(len(zs)):
                    self.paint(fx, zi, 0, 0, 0)
                if not zs and "dimmer" in fx.map and "preset" not in fx.map:
                    fx.set("dimmer", 0)
                continue
            if not steady and self._blitz_skip(fx, hz):        # Strobe zu schnell fuer diese Gruppe: dunkel
                for zi in range(len(zs)):
                    self.paint(fx, zi, 0, 0, 0)
                if not zs and "dimmer" in fx.map:
                    fx.set("dimmer", 0)
                continue
            if zs:
                for zi in range(len(zs)):
                    if on:
                        self.paint(fx, zi, level, level, level, w=level, uv=level if "uv1" in fx.map else 0.0)
                    else:
                        self.paint(fx, zi, 0, 0, 0)
            elif "dimmer" in fx.map and "preset" not in fx.map:
                fx.set("dimmer", 255 * self.master * level if on else 0)
                if on and "colorwheel" in fx.map:
                    fx.preset("colorwheel", "white")
            if "preset" in fx.map:
                if sync:
                    fx.set("preset", fx.extra.get("preset_blitz", 35))          # Solid weiss, Helligkeit im Takt wie alle anderen
                    fx.set("dimmer", 255 * self.master * level if (on and age >= 4) else 0)
                else:
                    fx.set("dimmer", 255 * self.master * level if on else 0)

    # ---- Bedienung (Web-Panel) ----------------------------------------------------------------
    def command(self, d):
        """Befehle vom Web-Panel; thread-sicher. Rueckgabe: Hinweistext."""
        with self.cmd_lock:
            self.note = ""
            if isinstance(d.get("mix"), str):                  # alter Name aus gespeicherten Tasten (KITT -> Scanner)
                from scenes import renamed
                d = dict(d, mix=renamed(d["mix"]))
            if d.get("safety_ok"):                             # Sicherheitshinweis bestaetigt (einmal pro Anlage)
                import safety
                safety.confirm(os.path.dirname(os.path.abspath(self.cfg.path or "settings.json")))
                self.safety_open = False
                d = {k: v for k, v in d.items() if k != "safety_ok"}
            if self.showman is not None and self.showman.active():
                if "auto" in d:                                # Knopf SHOW (AUTO): Show beenden, zurueck zur Musiksteuerung
                    self.showman.stop(self.last_t if self.last_t is not None else time.time())
                    self._pilot_on()
                    d = {k: v for k, v in d.items() if k != "auto"}
                if any(k in d for k in PILOT_LOCKED):          # gesperrt wie beim Autopilot, auch vom APC mini
                    d = {k: v for k, v in d.items() if k not in PILOT_LOCKED}
                    self.note = "Show aktiv: zum Bedienen die Show beenden"
            if self.pilot and "auto" not in d and any(k in d for k in PILOT_LOCKED):
                d = {k: v for k, v in d.items() if k not in PILOT_LOCKED}   # gesperrt: wirkt nicht, auch nicht vom APC mini
                self.note = "Auto aktiv: zum Bedienen AUTO ausschalten"
            if any(k in d for k in SA_USER_KEYS):             # eigene Bedienung: Szenen-Automatik beenden und pausieren
                self.sa_user_t = time.monotonic()
                if self.sa is not None:
                    if self.sc is not None and self.sc.name == self.sa["name"]:
                        self.sc = None                         # die Taste wirkt dann wie in AUTO
                    self.sa = None
            if "scene" in d:
                self._set_scene(d["scene"])
            if "auto" in d:                                    # AUTO: True/False oder "toggle" (Knopf)
                on = (not self.pilot) if d["auto"] == "toggle" else bool(d["auto"])
                if on:
                    self._pilot_on()
                elif self.pilot:
                    self._pilot_off()
            if "blackout" in d:
                self.override = "blackout" if d["blackout"] else None
            if "allbright" in d:
                self.override = "allbright" if d["allbright"] else None
            if "rec" in d or d.get("rec_del"):                 # Debug-Aufnahme des Eingangs (12.11.2026)
                rec = getattr(self, "recorder", None)
                if rec is None:
                    raise ValueError("Aufnahme gibt es nur mit echtem Eingang (nicht im Simulator)")
                if "rec" in d:
                    rec.set_on(bool(d["rec"]))
                if d.get("rec_del"):
                    rec.delete_all()
            if "wlan" in d:                                    # WLAN des Licht-Rechners an/aus (wlan.py, 25.11.2026)
                import wlan
                on_ = bool((d["wlan"] or {}).get("on")) if isinstance(d["wlan"], dict) else bool(d["wlan"])
                wlan.manager().check(on_)
                self.cfg.set("wlan_trennen", 0.0 if on_ else 1.0)   # bleibt ueber einen Neustart, der Waechter haelt es
                wlan.manager().apply(on_)
            if "bt" in d:                                      # Bluetooth: sichtbar, suchen, koppeln, verbinden (bt_audio.py, 24.11.2026)
                import bt_audio
                b_ = d["bt"] if isinstance(d["bt"], dict) else {}
                if b_.get("op") == "out":                      # Ton weiterleiten an eine Ausgabe (25.11.2026), "" = aus
                    fn = getattr(self.src, "set_net_out" if b_.get("src") == "net" else "set_bt_out", None)
                    if fn is None:
                        raise ValueError("Weiterleitung gibt es nur mit echtem Eingang (nicht im Simulator)")
                    fn(b_.get("dev") or "")
                else:
                    bt_audio.manager().command(b_)
            if "audio" in d:                                   # Audio-Eingang waehlen, Gain, Kanal, Hardware-Regler
                fn = getattr(self.src, "configure", None)
                if fn is None:
                    raise ValueError("Audio-Eingang gibt es nur mit echtem Eingang (nicht im Simulator)")
                a_ = d["audio"]
                if a_.get("rescan") and hasattr(self.src, "rescan"):   # Soundkarten neu suchen (USB-Geraet nach dem Start eingesteckt)
                    self.src.rescan()
                fn(device=a_.get("device"), gain_db=a_.get("gain_db"), channel=a_.get("channel"), hw=a_.get("hw"))
            if "scene_save" in d:
                self._scene_save(d["scene_save"].get("orig"), d["scene_save"].get("scene", {}), d["scene_save"].get("after"))
            if "scene_delete" in d:
                self._scene_delete(d["scene_delete"])
            if "scene_move" in d:
                self._scene_move(d["scene_move"]["name"], int(d["scene_move"].get("delta", 0)))
            if d.get("scenes_reset"):
                self._scenes_reset()
            if "set" in d:                                     # Einstellungen der Auto-Erkennung aendern
                for k, v in d["set"].items():
                    self.cfg.set(k, v)
            if "reset" in d:
                self.cfg.reset(None if d["reset"] == "all" else d["reset"])
            if "link_add" in d:                                # eigene Links zu Geraeten im Heimnetz (links.json, 24.11.2026)
                self.links.add(d["link_add"])
            if "link_del" in d:
                self.links.remove(d["link_del"])
            if "matrix_ip" in d:                               # Adresse der Pixel-Matrix (matrix.json), leer = keine
                if self.matrix is None:
                    raise ValueError("Pixel-Matrix nicht verfuegbar")
                h = self.matrix.set_host(d["matrix_ip"])
                self.note = f"Pixel-Matrix: {h}" if h else "Pixel-Matrix: keine Adresse"
            if "solo_test" in d:                               # Einzel-Strobe eines Fixtures 3 s lang ausprobieren
                if not self.strobe:
                    raise ValueError("Zuerst die Strobe-Erlaubnis einschalten (Knopf STROBE erlaubt oben)")
                fx = self.rig.by_name.get(d["solo_test"])
                if fx is None or not fx.tdef.get("hw_strobe") or fx.locked:
                    raise ValueError("Dieses Geraet hat keinen Einzel-Strobe")
                if self.solo is not None:
                    self._solo_end(self.solo["fx"])
                t0 = self.last_t if self.last_t is not None else time.time()
                self.solo = {"fx": fx, "until": t0 + 3.0, "rate": self.cfg["solo_rate"], "test": True}
                self.note = f"Einzel-Strobe {fx.extra.get('label', fx.name)} fuer 3 Sekunden"
            if "eb_preset" in d:                               # Effektband-Preset von Hand; 0 oder nochmal tippen = automatisch
                pid = int(d["eb_preset"] or 0)
                if pid and pid not in {k for k, _ in self._eb_names()}:
                    raise ValueError("Unbekanntes Effektband-Preset")
                if pid in EB_STROBE and not self.strobe:
                    raise ValueError("Dieses Preset blitzt: zuerst die Strobe-Erlaubnis einschalten")
                self.eb_man = None if (not pid or pid == self.eb_man) else pid
            if "beam" in d:                                    # Beam: "auto" oder {gobo, zoom, roll, prism} (Teile genuegen)
                if d["beam"] == "auto":
                    self.beam_man = False                      # Werte bleiben gemerkt fuer das naechste Mal
                else:
                    self.beam, self.beam_man = self._beam_merge(self.beam, d["beam"]), True
            if "blitz_hz" in d:
                self.blitz_hz = snap_blitz(d["blitz_hz"])
            if "blitz" in d:
                on = (not self.blitz) if d["blitz"] == "toggle" else bool(d["blitz"])
                if on and not self.blitz:
                    self.blitz_t0 = self.last_t if self.last_t is not None else time.time()
                    self.blitz_f = 0
                self.blitz = on
            if self.blitz and not self.strobe and self.blitz_hz > 3.0:
                self.note = "Strobe nicht erlaubt: Blitz auf 3 pro Sekunde begrenzt"
            if "freeze" in d:
                self.freeze = bool(d["freeze"]) if d["freeze"] != "toggle" else not self.freeze
                self.note = "Freeze: Licht und Bewegung eingefroren" if self.freeze else "Freeze aus"
            if "build" in d:
                self._manual_build(d["build"])
            if d.get("build_keep") and self.build_t0 is not None:     # Taster wird noch gehalten
                self.build_seen = self.last_t if self.last_t is not None else time.time()
            if "fog_power" in d:                               # Nebelmaschine ein (nach der Rueckfrage) oder Aufheizen abbrechen
                if d["fog_power"]:
                    self._fog_power_on(self._fog_clock())
                else:
                    self._fog_power_off()
            if "fog_ack" in d:                                 # Warnleiste bzw. Erinnerung Rauchmelder weggetippt
                if d["fog_ack"] == "off":
                    self.fog_remind = False
                else:
                    self.fog_ack = True
            if "fog_cue" in d:                                 # Nebelschub aus einer Show
                self._fog_cue(float(d["fog_cue"]))
            if d.get("fog_cue_off"):
                self._fog_stop(self._fog_clock())
            if d.get("fog"):
                self._fog()
            if "hold" in d:                                    # Taster (Panel/APC): nur solange gedrueckt
                self._hold(d["hold"].get("name"), bool(d["hold"].get("on")))
            if d.get("hold_keep"):
                now_w = time.time()
                for n in d["hold_keep"]:
                    if n in self.held:
                        self.held[n] = now_w
            if "aim" in d:
                self.aim = d["aim"] if d["aim"] in self.aim_targets else None
            if "aim_set" in d and self.aim:
                self._aim_set(d["aim_set"])
            if d.get("aim_save"):
                self._save_aim()
            if "aim_add" in d:                                 # Ziele im Panel bearbeiten
                self._aim_add(d["aim_add"])
            if "aim_rename" in d:
                self._aim_rename(d["aim_rename"].get("key"), d["aim_rename"].get("label"))
            if "aim_delete" in d:
                self._aim_delete(d["aim_delete"])
            if "master" in d:
                self.master = max(0.0, min(1.0, float(d["master"])))
            if "glevel" in d:                                  # Gruppen-Helligkeit: {"bar": 0.5, ...}
                for k, v in d["glevel"].items():
                    if k in self.glevel:
                        self.glevel[k] = max(0.0, min(1.0, float(v)))
            if d.get("glevel_reset"):
                self.glevel = {k: 1.0 for k, _ in GROUP_LABELS}
            if ("master" in d or "glevel" in d or "blitz_hz" in d or "beam" in d or d.get("glevel_reset")) and self.levels_dirty_t is None:
                self.levels_dirty_t = time.monotonic()         # gespeichert wird gesammelt (Fader am APC mini senden viel)
            if any(k in d for k in ("fx_save", "fx_delete", "fx_restore", "fx_desc", "type_save", "type_import", "type_delete", "fx_reset", "restart", "nano_host", "nano_token", "nano_pair", "artnet_target")):
                self._fixture_cmd(d)
            if d.get("backup"):                                # Sicherung jetzt starten (laeuft im Hintergrund)
                self._backup_now()
            if "home" in d:                                    # HomeMatic: Steckdose schalten oder Licht dimmen
                if self.home is None:
                    raise ValueError("Die HomeMatic-Anbindung laeuft nur im echten Betrieb am Licht-Rechner")
                h = d["home"]
                self.home.set(h.get("id"), on=h.get("on"), level=h.get("level"))
            if "power_on" in d:                                # Name in der roten Warnung angetippt: seine Steckdosen ein
                if self.home is None:
                    raise ValueError("Die HomeMatic-Anbindung laeuft nur im echten Betrieb am Licht-Rechner")
                self._power_on(d["power_on"])
            if "fine" in d:                                    # Feinregler: Wert fuer den gerade gewaehlten Knopf
                f = d["fine"]
                g = str(f.get("grp"))
                if g not in ("mv", "mx") or f.get("btn") != self._fine_active(self.sc, g):
                    raise ValueError("Dieser Knopf ist nicht mehr gewaehlt")
                self.fine.set(g, f["btn"], str(f.get("key")), f.get("v"))
            if "home_edit" in d or "home_scan" in d:           # HomeMatic im Panel einstellen (homematic_user.json)
                if self.home is None:
                    raise ValueError("Die HomeMatic-Anbindung laeuft nur im echten Betrieb am Licht-Rechner")
                if d.get("home_scan"):
                    self.home.scan()
                if "home_edit" in d:
                    old_pw = self._fog_power()
                    self.home.edit(d["home_edit"])
                    if self._fog_power() != old_pw:            # andere Nebel-Steckdose: Zustand neu lesen (an = warm)
                        self.fog_prev_power, self.fog_warm_t, self.fog_on_t = None, None, None
                        self.fog_remind = self.fog_ack = False
                    self.note = "Gespeichert."
            if d.get("poweroff") == "JA":                      # Pi herunterfahren (Knopf im Panel, mit Rueckfrage)
                self._poweroff()
            if "apc_key" in d or "apc_reset" in d:             # APC-Tasten umbelegen (Seite /apc)
                import apc_view
                mc = apc_view.controller(self)
                if "apc_reset" in d:
                    mc.reset_keys()
                else:
                    mc.set_key(d["apc_key"].get("sec"), d["apc_key"].get("key"), d["apc_key"].get("act"))
            if "lumi_key" in d or "lumi_reset" in d:           # Lumi-Tasten umbelegen (Seite /lumi)
                import lumi_view
                lc = lumi_view.controller(self)
                if "lumi_reset" in d:
                    lc.reset_keys()
                else:
                    lc.set_key(d["lumi_key"].get("note"), d["lumi_key"].get("act"))
            if "midi" in d:                                    # Befehle an den MIDI-Controller (LED-Test usw.)
                if self.midi is None:
                    raise ValueError("Kein MIDI-Controller aktiv")
                self.midi.command(d["midi"])
                if self.lumi is not None:
                    self.lumi.command(d["midi"])
            if "strobe" in d:
                self.strobe = bool(d["strobe"])
            if "text_set" in d:                                # Uebersetzungstabelle im Panel
                t = d["text_set"]
                self.texts.set(t.get("key"), t.get("de"), t.get("en"))
            if "style" in d:                                   # Stil von Hand (Knoepfe Stil), "auto" = nach Mixxx-Genre
                self.style_man = d["style"] if d["style"] in STYLES else None
            if "genre_style" in d:                             # eigene Zuordnung Genre -> Stil im Panel
                g = d["genre_style"]
                self.gstyles.set(g.get("genre"), g.get("style") or "")
            if "text_reset" in d:
                self.texts.reset(None if d["text_reset"] == "all" else d["text_reset"])
            if "color_toggle" in d:
                self._toggle_color(d["color_toggle"])
            if "bpm" in d:
                self.manual_bpm = None if d["bpm"] in (None, "auto", 0) else max(60.0, min(200.0, float(d["bpm"])))
            for key in ("mix", "move", "speed", "color"):
                if key in d:
                    self._edit_scene(key, d[key])
            return self.note

    def _manual_build(self, on):
        """WOW!: aufbauender Strobo-Effekt im BPM-Raster, startet auf dem naechsten Beat. Nochmal tippen = Drop."""
        now = self.last_t if self.last_t is not None else time.time()
        building = self.build_t0 is not None
        if on == "toggle":
            on = not building
        if on and not building:
            bpm = self.manual_bpm or (self.bpm if self.bpm > 0 else 120.0)
            self.wow_period = 60.0 / max(60.0, min(200.0, bpm))
            ref = self.beat_t if (self.beat_t is not None and 0 <= now - self.beat_t < 3.0) else now
            k = math.ceil((now - ref) / self.wow_period) if now > ref else 0
            self.build_t0 = ref + k * self.wow_period          # naechster Beat auf dem erkannten Raster
            self.build_p, self.bphase = 0.0, 0.0
            self.build_seen = now
            self.freeze = False
            self.note = "WOW! gestartet" + ("" if self.strobe else " (Strobe nicht erlaubt: ruhigere Blitze)")
        elif not on and building:
            reached = self.build_p
            self.build_t0 = None
            if reached > 0.3 and self.wow_drop:                # Taster losgelassen, Aufbau weit genug: Drop
                self._enter("drop", now)
                self.note = "Drop!"
            else:
                self.note = "WOW! abgebrochen"

    def _fog_power(self):
        """id der Steckdose der Nebelmaschine in der HomeMatic-Anbindung, sonst None (Simulator, keine CCU)."""
        if self.home is None:
            return None
        dev = self.home.ccu.get("fog_power")
        return dev if dev in self.home.by_id else None

    def _fog_ready(self, now):
        """(bereit, Restzeit Aufheizen in s, Grund). Ohne Steckdose (Simulator) immer bereit."""
        pw = self._fog_power()
        if pw is None:
            return True, 0.0, ""
        st = self.home.state.get(pw, {})
        if st.get("on") is not True or self.fog_warm_t is None:
            return False, 0.0, "aus"
        left = self.fog_warm_t + self.cfg["fog_warm_min"] * 60.0 - now
        if left > 0:
            return False, left, "heizt"
        if self.cfg["fog_via"] > 0.5 and not self.home.fog_state.get("ok"):
            return False, 0.0, "schalter"                       # warm, aber der Nebelschub-Schalter meldet sich noch nicht
        return True, 0.0, ""

    def _fog(self, hold=None):
        """Nebel nur per Knopf: hoechstens 10 s am Stueck, danach Mindestpause (ab dem Ende). Ist die Nebelmaschine
        (HomeMatic-Steckdose) aus, schaltet der erste Druck sie ein; Nebel gibt es erst nach der Aufheizzeit.
        Ausgeloest ueber DMX (Hazer) oder den HomeMatic-Schalter Nebelschub (Einstellung fog_via, mit ON_TIME-Sicherung).
        hold=None: fester Schub (Einstellung seconds); True: laeuft, solange gehalten (max. 10 s); False: sofort aus."""
        now = self._fog_clock()
        hz = next((fx for fx in self.rig.fixtures if fx.type == "hazer" and fx.manual_ok), None)
        if hold is False:
            self._fog_stop(now)
            return
        if now < self.fog_end:
            return                                              # laeuft schon
        wait = self.fog_end + self._fog_cool() - now
        if wait > 0:
            self.note = f"Nebel: bitte noch {wait:.0f} s warten"
            return
        pw = self._fog_power()
        if pw is not None and self.home.state.get(pw, {}).get("on") is not True:
            self._fog_power_on(now)
            return
        ready, left, why = self._fog_ready(now)
        if not ready:
            self.note = (f"Nebelmaschine heizt noch {int(left // 60)}:{int(left % 60):02d}" if why == "heizt"
                         else "Nebelmaschine: warte auf den Schalter Nebelschub")
            return
        cfg = hz.tdef.get("burst", {}) if hz is not None else {}
        secs = 10.0 if hold else max(0.5, min(10.0, float(cfg.get("seconds", 3.0))))
        if self._fog_fire(now, secs, hz, cfg):
            self.note = "Nebel, solange gedrueckt (hoechstens 10 s)" if hold else f"Nebelschub {secs:.0f} s"

    def _fog_fire(self, now, secs, hz, cfg):
        """Nebelschub ausloesen: ueber DMX oder den HomeMatic-Schalter (mit ON_TIME). Immer mit allen Grenzen geprueft vom Aufrufer."""
        if self.cfg["fog_via"] > 0.5:                           # ueber den HomeMatic-Schalter Nebelschub
            if self.home is None or not self.home.fog_trigger:
                self.note = "Nebel ueber HomeMatic: keine CCU bzw. kein Schalter Nebelschub"
                return False
            if not self.home.fog_state.get("ok"):
                self.note = "Nebel: Schalter Nebelschub nicht erreichbar"
                return False
            try:
                self.home.fog_fire(True, secs)
            except ValueError as e:
                self.note = f"Nebel: {e}"
                return False
            self.fog_hm_on = True
        else:
            if hz is None:
                self.note = "Kein Hazer konfiguriert"
                return False
            if not hz.manual({"pump": cfg.get("pump", 150), "fan": cfg.get("fan", 100)}, secs):
                return False
        self.fog_last, self.fog_end, self.fog_used_t = now, now + secs, now
        return True

    def _fog_cue(self, secs):
        """Nebelschub aus einer Show (vom Nutzer am 03.11.2026 freigegeben, Einstellung sm_fog). Dieselben Grenzen wie der Knopf:
        hoechstens 10 s, Mindestpause. Anders als der Knopf schaltet er die Maschine nie ein und entfaellt, wenn sie nicht bereit ist."""
        if self.cfg["sm_fog"] < 0.5 or self.override == "blackout":
            return False
        now = self._fog_clock()
        if now < self.fog_end or self.fog_end + self._fog_cool() > now:
            self.note = "Nebel aus der Show entfaellt: Mindestpause noch nicht um"
            return False
        ready, _, why = self._fog_ready(now)
        if not ready:
            self.note = f"Nebel aus der Show entfaellt: Nebelmaschine {'heizt noch' if why == 'heizt' else 'nicht bereit'}"
            return False
        hz = next((fx for fx in self.rig.fixtures if fx.type == "hazer" and fx.manual_ok), None)
        cfg = hz.tdef.get("burst", {}) if hz is not None else {}
        return self._fog_fire(now, max(1.0, min(10.0, secs)), hz, cfg)

    def _fog_power_on(self, now):
        """Steckdose der Nebelmaschine einschalten (Aufheizen beginnt). Im Panel erst nach der Rueckfrage zu den Rauchmeldern."""
        pw = self._fog_power()
        if pw is None:
            raise ValueError("Keine Steckdose fuer die Nebelmaschine (HomeMatic)")
        st = self.home.state.get(pw, {})
        if st.get("on") is True:
            return
        if st.get("ok") is False:
            self.note = "Nebelmaschine: Steckdose nicht erreichbar"
            return
        try:
            self.home.set(pw, on=True)
        except ValueError as e:
            self.note = f"Nebelmaschine: {e}"
            return
        self.fog_warm_t = self.fog_on_t = now
        self.fog_prev_power = True
        self.fog_ack, self.fog_remind = False, False             # Warnleiste Rauchmelder wieder zeigen
        self.note = f"Nebelmaschine wird eingeschaltet, heizt {self.cfg['fog_warm_min']:g} min auf"

    def _fog_power_off(self):
        """Aufheizen abbrechen: Steckdose der Nebelmaschine aus (nochmal SMOKE beim Aufheizen, mit Rueckfrage im Panel)."""
        pw = self._fog_power()
        if pw is None:
            raise ValueError("Keine Steckdose fuer die Nebelmaschine (HomeMatic)")
        self._fog_stop(self._fog_clock())
        try:
            self.home.set(pw, on=False)
        except ValueError as e:
            self.note = f"Nebelmaschine: {e}"
            return
        self.fog_warm_t = None
        self.fog_remind, self.fog_ack = True, False              # an die Rauchmelder erinnern
        self.fog_prev_power = False
        self.note = "Nebelmaschine ausgeschaltet"

    def _fog_stop(self, now):
        """Nebel sofort aus (DMX und HomeMatic), die Pause beginnt jetzt."""
        for fx in self.rig.fixtures:
            if fx.type == "hazer" and fx.manual_ok:
                fx.manual_vals = None
        if self.fog_hm_on:
            self.fog_hm_on = False
            try:
                self.home.fog_fire(False)
            except Exception:                                  # noqa: BLE001
                pass
        if now < self.fog_end:
            self.fog_end = now

    def _fog_tick(self):
        """Jedes Bild: Schub ueber HomeMatic beenden, Blackout stoppt Nebel, Steckdose beobachten, automatisch ausschalten."""
        now = self._fog_clock()
        if self.fog_hm_on and (now >= self.fog_end or self.override == "blackout"):
            self._fog_stop(now)
        pw = self._fog_power()
        if pw is None:
            return
        on = self.home.state.get(pw, {}).get("on")
        if on is False and self.fog_prev_power is True:
            self.fog_remind, self.fog_ack = True, False          # Maschine aus: an die Rauchmelder erinnern
        if on is True and self.fog_prev_power is not True:
            self.fog_remind = False
            if self.fog_prev_power is None:                     # beim Start der Show schon an: gilt als warm
                self.fog_warm_t = float("-inf")
            else:                                               # von Hand eingeschaltet: heizt ab jetzt
                self.fog_warm_t = now
            self.fog_on_t = now
        elif on is False:
            self.fog_warm_t = None
        if on is not None:
            self.fog_prev_power = on
        mins = self.cfg["fog_off_min"]
        if (on is True and mins > 0 and now >= self.fog_end and self.fog_on_t is not None
                and now - max(self.fog_on_t, self.fog_used_t or self.fog_on_t) > mins * 60.0):
            self.fog_on_t = now                                 # nicht jedes Bild neu senden
            try:
                self.home.set(pw, on=False)
                self.note = "Nebelmaschine nach langer Pause ausgeschaltet"
            except ValueError:
                pass

    def _fog_note(self):
        """Hinweisleiste im Panel: "on" = Maschine an (Rauchmelder deaktiviert?), "off" = gerade aus (wieder aktivieren)."""
        pw = self._fog_power()
        if pw is None:
            return ""
        if self.home.state.get(pw, {}).get("on") is True:
            return "" if self.fog_ack else "on"
        return "off" if self.fog_remind else ""

    def _fog_status(self):
        """Zustand des SMOKE-Knopfs: off | heat | ready | fire | pause | err, mit Restzeit und Fortschritt (0..1)."""
        now = self._fog_clock()
        via = "HM" if self.cfg["fog_via"] > 0.5 else "DMX"
        if now < self.fog_end:
            return {"st": "fire", "left": round(self.fog_end - now, 1), "prog": 1.0 - (self.fog_end - now) / 10.0, "via": via}
        wait = self.fog_end + self._fog_cool() - now
        if wait > 0:
            return {"st": "pause", "left": round(wait), "prog": wait / self._fog_cool(), "via": via}
        if via == "HM" and (self.home is None or not self.home.fog_trigger):
            return {"st": "err", "err": "ccu", "via": via}
        pw = self._fog_power()
        if pw is not None:
            st = self.home.state.get(pw, {})
            if st.get("ok") is False:
                return {"st": "err", "err": "power", "via": via}
            if st.get("on") is not True or self.fog_warm_t is None:
                return {"st": "off", "via": via}
            ready, left, why = self._fog_ready(now)
            if not ready:
                total = max(1.0, self.cfg["fog_warm_min"] * 60.0)
                return {"st": "heat", "left": round(left), "prog": 1.0 - left / total if why == "heizt" else 1.0,
                        "wait_sw": why == "schalter", "via": via}
        return {"st": "ready", "via": via}

    HOLD_KEYS = ("blitz", "blackout", "allbright", "freeze", "fog")
    HOLD_TIMEOUT = 1.5                                          # so lange ohne Lebenszeichen: Taster gilt als losgelassen

    def _hold(self, name, on):
        """Taster: wirkt nur, solange gedrueckt. Panel und APC melden alle 0,4 s, dass er noch gehalten wird."""
        if name not in self.HOLD_KEYS:
            raise ValueError("Unbekannter Taster")
        if on:
            self.held[name] = time.time()
        else:
            self.held.pop(name, None)
        if name == "blitz":
            if on and not self.blitz:
                self.blitz_t0 = self.last_t if self.last_t is not None else time.time()
                self.blitz_f = 0
            self.blitz = on
        elif name in ("blackout", "allbright"):
            if on:
                self.override = name
            elif self.override == name:
                self.override = None
        elif name == "freeze":
            self.freeze = on
        elif name == "fog":
            self._fog(hold=on)

    def _hold_check(self, now):
        """Kommt kein Lebenszeichen mehr (Handy gesperrt, Verbindung weg), den Taster loslassen."""
        for name, seen in list(self.held.items()):
            if now - seen > self.HOLD_TIMEOUT:
                self._hold(name, False)

    def _load_aim(self, rig):
        """Ziele aus fixtures.yaml (fest) plus aim.json: geaenderte Positionen, eigene Namen (label) und im Panel
        angelegte Ziele (user). Feste Ziele lassen sich umbenennen, aber nicht loeschen (Szenen und APC mini nutzen sie)."""
        targets = {k: {"vega": list(v.get("vega", [0.5, 0.5])), "bars": list(v.get("bars", [127, 127])),
                       "bars_per": {n: list(p) for n, p in v.get("bars_per", {}).items()}}
                   for k, v in (rig.cfg.get("aim_targets") or {}).items()}
        try:
            with open(self.aim_file, encoding="utf-8") as fh:
                for k, v in json.load(fh).items():
                    if not isinstance(v, dict):
                        continue
                    if k not in targets:
                        if not (v.get("user") and AIM_KEY_RE.match(str(k))):
                            continue
                        targets[k] = {"vega": [0.5, 0.5], "bars": [127, 127], "bars_per": {}, "user": True}
                    targets[k].update({kk: vv for kk, vv in v.items() if kk in ("vega", "bars", "bars_per")})
                    if isinstance(v.get("label"), str) and v["label"].strip():
                        targets[k]["label"] = v["label"].strip()[:AIM_LABEL_MAX]
        except (OSError, ValueError):
            pass
        return targets

    def _aim_label_check(self, label):
        label = " ".join(str(label or "").split())
        if not label:
            raise ValueError("Bitte einen Namen fuer das Ziel eingeben")
        if len(label) > AIM_LABEL_MAX:
            raise ValueError(f"Der Name darf hoechstens {AIM_LABEL_MAX} Zeichen lang sein")
        return label

    def _aim_add(self, label):
        """Neues Ziel anlegen (Mitte), es wird gleich ausgewaehlt, damit die Position eingestellt werden kann."""
        label = self._aim_label_check(label)
        base = re.sub(r"[^a-z0-9]+", "_", label.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                      .replace("ß", "ss")).strip("_")[:20] or "ziel"
        if not base[0].isalpha():
            base = "ziel_" + base
        key, n = base, 2
        while key in self.aim_targets:
            key, n = f"{base}_{n}", n + 1
        self.aim_targets[key] = {"vega": [0.5, 0.5], "bars": [127, 127], "bars_per": {}, "user": True, "label": label}
        self.aim = key
        self._save_aim()
        self.note = f"Ziel {label} angelegt. Position mit den Reglern einstellen und Speichern."

    def _aim_rename(self, key, label):
        t = self.aim_targets.get(key)
        if t is None:
            raise ValueError("Unbekanntes Ziel")
        if not t.get("user") and not str(label or "").strip():
            t.pop("label", None)                            # festes Ziel: leer = wieder der Name aus der Uebersetzungstabelle
        else:
            t["label"] = self._aim_label_check(label)
        self._save_aim()

    def _aim_delete(self, key):
        t = self.aim_targets.get(key)
        if t is None:
            raise ValueError("Unbekanntes Ziel")
        if not t.get("user"):
            raise ValueError("Die festen Ziele (Bank, Tisch, Tuer, Bar) lassen sich nicht loeschen, nur umbenennen")
        del self.aim_targets[key]
        if self.aim == key:
            self.aim = None
        self._save_aim()
        self.note = "Ziel geloescht"

    def aims_info(self):
        return [{"key": k, "label": t.get("label", ""), "user": bool(t.get("user"))} for k, t in self.aim_targets.items()]

    def _aim_set(self, vals):
        t = self.aim_targets[self.aim]
        if "vega_u" in vals or "vega_v" in vals:
            t["vega"] = [max(0.0, min(1.0, float(vals.get("vega_u", t["vega"][0])))),
                         max(0.0, min(1.0, float(vals.get("vega_v", t["vega"][1]))))]
        if "bar_t1" in vals or "bar_t2" in vals:
            name = vals.get("bar", "all")
            cur = t["bars_per"].get(name) if name != "all" else None
            cur = cur or t["bars"]
            pair = [max(10.0, min(220.0, float(vals.get("bar_t1", cur[0])))),
                    max(10.0, min(220.0, float(vals.get("bar_t2", cur[1]))))]
            if name == "all":
                t["bars"], t["bars_per"] = pair, {}
            else:
                t["bars_per"][name] = pair

    def _save_aim(self):
        try:
            with open(self.aim_file, "w", encoding="utf-8") as fh:
                json.dump(self.aim_targets, fh, indent=1)
            self.note = f"Ziele gespeichert ({self.aim_file})"
        except OSError as e:
            self.note = f"Speichern fehlgeschlagen: {e}"

    def _sa_candidates(self):
        """Szenen, die die Automatik waehlen darf, mit ihrer Stelle in der Liste (0 = vorne, 1 = hinten)."""
        n = max(1, len(self.scene_defs) - 1)
        out = []
        for i, sc in enumerate(self.scene_defs):
            if sc.special or sc.name in SA_SKIP_NAMES:          # nie: Laser, Ziele, All off, RESET (Sicherheit/Gebrauchslicht)
                continue
            if not self.strobe and (sc.mix in ("strobe", "lightning") or sc.preset in (8, 32)):
                continue                                         # Strobe-Szenen nur mit Strobe-Erlaubnis
            if is_austria(sc):
                continue                                         # Austria nur beim Drop eines Austria-Liedes (_scene_auto)
            out.append((i / n, sc))
        return out

    def _austria_song(self):
        """Laeuft in Mixxx ein Lied mit "Austria" oder "Oesterreich" im Titel?"""
        m = self.mx
        if not m or not m.get("plan") or m.get("deck") is None:
            return False
        t = unicodedata.normalize("NFC", str(m.get("title") or "")).lower()   # macOS: "Ö" oft als "O" plus Punkte (NFD)
        return any(w in t for w in ("austria", "österreich", "oesterreich"))

    def _sa_pick(self, key):
        lo, hi = SA_RANGE[key]
        cands = [(p, sc) for p, sc in self._sa_candidates() if sc.name != self.sa_last]
        if not cands:
            return None
        inside = [sc for p, sc in cands if lo <= p <= hi]
        if inside:
            return self._rng.choice(inside)
        mid = (lo + hi) / 2.0                                    # nichts im Bereich: die naechstgelegene erlaubte Szene
        return min(cands, key=lambda ps: abs(ps[0] - mid))[1]

    def _sa_pick_preset(self, key):
        """Effektband-Preset fuer die Szenen-Automatik nach der Stufe (Rollen in fixtures.yaml: calm, warm, party)."""
        if not self.presets:
            return None
        fx = self.presets[0]
        roles = self.eb_roles(fx)
        lst = [p for p in roles.get({0: "calm", 1: "warm"}.get(key, "party"), [])
               if p != fx.values.get("preset") and (self.strobe or p not in EB_STROBE)]
        return self._rng.choice(lst) if lst else None

    def _scene_auto(self, now, phrase, drop_start):
        """Szenen-Automatik: in AUTO ab und zu kurz eine Szene nach der Stufe im Lied (siehe SA_RANGE)."""
        c = self.cfg
        austria_cue = self.cue_now and c["sa_on"] >= 0.5 and self._austria_song()   # Hotcue im Austria-Lied: Austria-Szene
        if self.sa_eb is not None and (c["sa_on"] < 0.5 or self.state not in ("normal", "build", "drop")
                                       or self.eb_man or self.step >= self.sa_eb["until_step"]):
            self.sa_eb = None                                    # Effektband-Preset der Automatik vorbei
        if self.sa is not None:                                  # laeuft: Ende nach Zeit, Stille/Break oder anderer Bedienung
            if (self.sc is None or self.sc.name != self.sa["name"] or c["sa_on"] < 0.5
                    or self.state in ("idle", "gap", "break") or self.override is not None
                    or self.step >= self.sa["until_step"]
                    or (drop_start and c["sa_drop"] > 0.5 and not self.sa["drop"])   # Drop: gleich die Drop-Szene
                    or austria_cue):                                                  # Austria-Lied: an jedem Hotcue neu
                if self.sc is not None and self.sc.name == self.sa["name"]:
                    self.sc = None
                self.sa = None
            if self.sa is not None or not (drop_start or austria_cue):
                return
        if (not self.pilot or c["sa_on"] < 0.5 or self.sc is not None or self.override is not None or self.aim or self.freeze
                or self.build_t0 is not None or self.color_freeze or self.auto_move or self.auto_rainbow
                or (self.auto_color and self.auto_color != "auto") or len(self.auto_colors) > 1
                or self.state not in ("normal", "build", "drop")):
            return
        if self.sa_user_t is not None and time.monotonic() - self.sa_user_t < c["sa_pause_s"]:
            return
        bl = self.bar_len
        if drop_start and c["sa_drop"] > 0.5:
            key = "drop"
            per = 60.0 / (self.bpm if self.bpm > 0 else 120.0)
            steps = max(bl, int(round(max(0.8, c["drop_len_s"]) / per)))
        elif austria_cue:
            key = "cue"                                          # Austria-Lied, Hotcue: Austria fuer einige Takte
            steps = bl * max(1, int(c["sa_bars"]))
        elif phrase and self.sa_eb is None and self._rng.random() * 100.0 < c["sa_prob"]:
            key = 3 if self.state in ("build", "drop") else max(0, min(3, int(self._base_tier())))
            steps = bl * self._rng.randint(1, max(1, int(c["sa_bars"])))
            if self._rng.random() * 100.0 < c["sa_eb_share"] and not self.eb_man:
                pid = self._sa_pick_preset(key)                  # statt einer Szene nur ein passendes Effektband-Preset
                if pid:
                    self.sa_eb = {"pid": pid, "until_step": self.step + steps}
                return
        else:
            return
        sc = self._sa_pick(key) if key != "cue" else None
        if key in ("drop", "cue") and self._austria_song():      # Drop oder Hotcue im Austria-Lied: die Szene Austria
            sc = next((s for s in self.scene_defs if is_austria(s) and not s.special), sc)
        if sc is None:
            return
        self.sc = sc.copy()
        self.scenes.beatpos = 0.0
        self.sa = {"name": sc.name, "until_step": self.step + steps, "drop": key == "drop"}
        self.sa_last = sc.name

    def _set_scene(self, name):
        sc = next((s for s in self.scene_defs if s.name == name), None)
        if sc is None:
            self.note = f"Unbekannte Szene {name}"
            return
        if sc.special == "blackout":                       # nochmal tippen = Blackout aus, zurueck zu Auto
            self.override = None if self.override == "blackout" else "blackout"
        elif sc.special == "auto":
            self._pilot_on()
        elif sc.special.startswith("aim:"):
            key = sc.special[4:]
            self.aim = None if self.aim == key else key       # nochmal tippen = wieder frei
        elif self.sc is not None and self.sc.name == name and self.override is None:
            self.sc = None                                    # aktive Szene nochmal tippen = aus, zurueck in den Auto-Modus
            self.note = "Szene aus"
        else:
            self.sc, self.override = sc.copy(), None
            self.color_freeze = False
            self.scenes.beatpos = 0.0
            if sc.special == "laser":
                self.note = ("LASER AN (" + self._laser_mode_text() + ") - nicht auf Personen oder in Augenhoehe richten. "
                             "Nochmal tippen = aus")

    # ---- Szenen bearbeiten (Panel) --------------------------------------------------------------
    def _scene_names(self, skip=None):
        return {s.name for s in self.scene_defs if s.name != skip}

    def _scene_save(self, orig, d, after=None):
        d = dict(d)
        defs = list(self.scene_defs)
        idx = next((i for i, s in enumerate(defs) if s.name == orig), None) if orig else None
        if orig and idx is None:
            raise KeyError(f"Szene {orig} nicht gefunden")
        base = defs[idx] if idx is not None else Scene(name="Neue Szene", move="auto")
        if base.special:                                   # Spezialszenen: nur Name aenderbar
            d = {"name": d["name"]} if "name" in d else {}
        new = scene_from_dict(d, base)
        taken = self._scene_names(skip=orig)
        if new.name in taken:                              # Namen muessen eindeutig sein
            n = 2
            while f"{new.name} {n}" in taken:
                n += 1
            new = new.copy(name=f"{new.name} {n}")
        if idx is not None:
            defs[idx] = new
        else:
            pos = next((i + 1 for i, s in enumerate(defs) if s.name == after), len(defs)) if after else len(defs)
            defs.insert(pos, new)
        self.scene_defs = defs
        if orig and self.sc is not None and self.sc.name == orig and not new.special:
            self.sc = new.copy(mixbtn=self.sc.mixbtn)      # laufende Szene sofort mit den neuen Eigenschaften
        elif orig and self.sc is not None and self.sc.name == orig:
            self.sc = self.sc.copy(name=new.name)
        self._scenes_changed(new.name)

    def _scene_delete(self, name):
        defs = [s for s in self.scene_defs if s.name != name]
        if len(defs) == len(self.scene_defs):
            raise KeyError(f"Szene {name} nicht gefunden")
        self.scene_defs = defs
        if self.sc is not None and self.sc.name == name:
            self.sc = None                                 # geloeschte Szene war aktiv: zurueck in den Auto-Modus
        self._scenes_changed("")

    def _scene_move(self, name, delta):
        defs = list(self.scene_defs)
        i = next((k for k, s in enumerate(defs) if s.name == name), None)
        if i is None:
            raise KeyError(f"Szene {name} nicht gefunden")
        j = max(0, min(len(defs) - 1, i + delta))
        defs.insert(j, defs.pop(i))
        self.scene_defs = defs
        self._scenes_changed(name)

    def _scenes_reset(self):
        self.scene_defs = default_scenes()
        if self.sc is not None and not any(s.name == self.sc.name for s in self.scene_defs):
            self.sc = None
        if self.scene_file and os.path.exists(self.scene_file):
            try:
                os.remove(self.scene_file)
            except OSError:
                pass
        self.scene_rev += 1
        self.scene_last = ""
        self.note = "Szenen auf Standard zurueckgesetzt"

    def _scenes_changed(self, last):
        save_scenes(self.scene_file, self.scene_defs)
        self.scene_rev += 1
        self.scene_last = last

    def scenes_info(self):
        from scenes import scene_to_dict
        eb = next((f for f in self.rig.fixtures if f.type == "wled_preset"), None)
        names = (eb.extra.get("preset_names") or {}) if eb else {}
        presets = [[0, "automatisch (nach Tempo)"]] + [[int(k), f"{k}: {v}"] for k, v in sorted(names.items(), key=lambda kv: int(kv[0]))]
        return {"rev": self.scene_rev, "scenes": [scene_to_dict(s) for s in self.scene_defs],
                "options": {"mixes": MIX_LABELS, "speeds": SPEEDS, "colors": COLOR_LABELS, "moves": MOVE_LABELS,
                            "kinds": KIND_LABELS, "presets": presets}}

    def _pilot_on(self):
        """Autopilot an: alle Vorgaben von Hand weg, das Licht laeuft wieder ganz nach der Musik."""
        self.pilot = True
        self.sc, self.override = None, None
        self.auto_rainbow = self.color_freeze = False
        self.freeze, self.build_t0 = False, None
        self.auto_color, self.auto_colors, self.auto_move, self.auto_speed = None, [], None, None
        self.aim, self.beam_man, self.eb_man, self.style_man = None, False, None, None

    def _pilot_off(self):
        """Autopilot aus: was gerade markiert ist, bleibt als eigene Auswahl stehen, das Licht springt nicht."""
        if self.sc is None:
            self.auto_color = self._pilot_color()
            self.auto_colors = [self.auto_color]
            self.auto_speed, self.auto_move = self._pilot_speed(), self._pilot_move()
        self.style_man = self._style_key()
        if self.presets and self.presets[0].values.get("dimmer", 0) > 0:
            pid = int(self.presets[0].values.get("preset", 0))
            if pid in {k for k, _ in self._eb_names()} and pid not in EB_STROBE:
                self.eb_man = pid
        self.sa, self.sa_eb = None, None
        self.pilot = False

    def _pilot_color(self):
        """Farbknopf, der dem Farbton der Show am naechsten liegt (nur Anzeige, das Licht aendert sich dadurch nicht)."""
        dist = lambda c: min(abs(SCENE_COLORS[c] - self.hue_target) % 1.0, 1.0 - abs(SCENE_COLORS[c] - self.hue_target) % 1.0)
        return min(PILOT_BUTTON_COLORS, key=dist)

    def _pilot_speed(self):
        return {0: "slow", 1: "slow", 2: "mid"}.get(int(self.eff_tier()), "fast")

    def _pilot_move(self):
        """Bewegungsknopf, der der Musik-Bewegung am aehnlichsten ist (Annaeherung, siehe _render_motion)."""
        if self.state == "drop":
            return "sweep"
        return "random" if self.state == "build" or self.eff_tier() >= 2 else "duck"

    def _toggle_color(self, value):
        """Panel: Farbton an- oder abwaehlen (Mehrfachauswahl, nur AUTO). Eine Farbe wirkt wie bisher fest,
        ab zwei wechseln sich die gewaehlten Farben bei Phrase und Drop ab. Keine Farbe mehr = Auto (nach Stimmung).
        Auto, Weiss und UV sowie Szenen bleiben Einzelauswahl."""
        if self.sc is not None or value not in SCENE_COLORS:
            self._edit_scene("color", value)
            return
        self.override = None
        self.auto_rainbow = self.color_freeze = False
        sel = list(self.auto_colors)
        added = value not in sel
        sel = sel + [value] if added else [c for c in sel if c != value]
        self.auto_colors = sel
        self.auto_color = sel[0] if len(sel) == 1 else None
        if len(sel) > 1:                                   # sofort eine gewaehlte Farbe zeigen, dann abwechseln
            hues = [SCENE_COLORS[c] for c in sel]
            if added or getattr(self, "hue_target", None) not in hues:
                self.hue_target = SCENE_COLORS[value] if added else hues[0]
                self.color_idx = sel.index(value) if added else 0
                self.last_color_change = self.last_t if self.last_t is not None else time.time()

    def _edit_scene(self, key, value):
        if key == "mix" and value == "STOP":
            # STOP: wie Freeze, aber nur das Licht; die Bewegung der Geraete laeuft weiter. Nochmal = aus
            self.override = None
            self.color_freeze = not self.color_freeze
            return
        if key == "mix" and MIX_BUTTONS.get(value, {}).get("mix") == "rainbow":
            # Regenbogen: bleibt in AUTO (Helligkeit nach der Musik), nur die Farben laufen durch; nochmal = aus
            on = self.color_freeze or not (self.sc is None and self.auto_rainbow)
            self.color_freeze = False
            self.sc, self.override = None, None
            self.auto_rainbow = on
            if on:
                self.auto_color, self.auto_colors = None, []
            return
        if key == "mix":
            self.auto_rainbow = False
        if key in ("mix", "color"):
            self.color_freeze = False
        if key == "color" and self.sc is None:             # AUTO: Farbe nur vorgeben, die Effekte laufen weiter
            self.override = None
            self.auto_rainbow = False
            self.auto_color = None if value in ("auto", "", None) else value
            self.auto_colors = [value] if value in SCENE_COLORS else []
            return
        if key in ("move", "speed") and self.sc is None:   # AUTO: Bewegung/Tempo vorgeben, das Licht laeuft weiter nach der Musik
            self.override = None
            if key == "move":
                new = None if value in ("auto", "", None) or value == self.auto_move else value   # nochmal tippen = nach der Musik
                self.auto_move = new
            else:                                          # Speed: Auto (nach der Musik), Low, Med oder Hot, immer genau eins
                self.auto_speed = value if value in AUTO_SPEED_TIER else None
            return
        if key == "mix" and self.sc is not None and value and value == self.sc.mixbtn:   # nochmal tippen = zurueck zu AUTO
            self.sc, self.override = None, None
            return
        if self.sc is None:
            self.sc = Scene(name="Eigene", move="auto")
            if self.auto_speed:                            # gewaehlte Geschwindigkeit gilt auch im Licht-Mix
                self.sc.speed = self.sc.mspeed = self.auto_speed
        self.override = None
        sc = self.sc
        if key == "move" and value and value == sc.move:   # nochmal tippen = Bewegung wieder nach der Musik
            value = "auto"
        if key == "mix":
            sc.name = "Eigene"
            sc.names, sc.kinds, sc.vega_pos = (), (), ()
            sc.mixbtn = value if value in MIX_BUTTONS else ""
            opts = MIX_BUTTONS.get(value, {"mix": value})
            for k, v in opts.items():
                setattr(sc, k, v)
        elif key == "move":
            sc.name, sc.move, sc.vega_pos = "Eigene", value, ()
        elif key == "speed":
            if sc.name != "Eigene" and sc.special != "laser":   # feste Szene behaelt ihr Tempo (Ausnahme: Szene Laser)
                return
            if value in AUTO_SPEED_TIER:                   # Low/Med/Hot: bleibt auch nach dem Mix (zurueck in AUTO) erhalten
                sc.speed = sc.mspeed = value
                self.auto_speed = value
            else:                                          # Auto: keine eigene Wahl, Muster laufen mit Med
                self.auto_speed = None
                sc.speed = sc.mspeed = "mid"
        elif key == "color":
            sc.name, sc.color = "Eigene", value

    def snapshot(self):
        d = self._snapshot()
        d["pilot"] = self.pilot and not d["sm_show"]
        if d["sm_show"]:                                   # Show: kein Knopf ist gedrueckt, die Musiksteuerung ruht
            d.update(color="", colors=[], speed="auto", move="", mix="", mixbtn="", scene="", style_man="auto", style_eff="")
        elif self.pilot:                                   # Autopilot: zeigen, welche Knoepfe er gerade "drueckt"
            d["style_man"] = self._style_key() or "auto"
            if self.sc is None:
                d["color"], d["colors"] = self._pilot_color(), []
                d["speed"], d["move"] = self._pilot_speed(), self._pilot_move()
        return d

    def _snapshot(self):
        sc = self.sc
        f = self.f
        sm_on = self.showman is not None and self.showman.active()
        return {"mode": "blackout" if self.override == "blackout" else "allbright" if self.override == "allbright"
                else "show" if sm_on else "scene" if sc else "auto",
                "scene": sc.name if sc else "", "mix": sc.mix if sc else "", "mixbtn": "STOP" if self.color_freeze else sc.mixbtn if sc else ("Regenbogen" if self.auto_rainbow else ""), "move": sc.move if sc else (self.auto_move or ""),
                "speed": (sc.speed if sc.name != "Eigene" else (self.auto_speed or "auto")) if sc else (self.auto_speed or "auto"), "color": sc.color if sc else (self.auto_color or ("" if (self.auto_colors or self.auto_rainbow) else "auto")),
                "colors": [] if sc else list(self.auto_colors),
                "style_man": self.style_man or "auto", "style_eff": self._style_key() or "",
                "master": round(self.master, 2), "strobe": self.strobe,
                "talk": self.talk,
                "mac_audio": self.mixxx.mac_audio_warn() if getattr(self.mixxx, "mac_audio_warn", None) else [],
                "sm_show": self.showman.doc_name if self.showman is not None and self.showman.active() else "",
                "radio": self.radio.panel() if self.radio is not None else None,
                "local": self.local.panel() if self.local is not None else None,
                "dmx_debug": bool(getattr(self.output, "debug", None) is not None and self.output.debug.is_armed()),
                "glevel": {k: round(v, 2) for k, v in self.glevel.items()},
                "bpm": round(self.manual_bpm or self._bpm_show(), 1), "bpm_manual": self.manual_bpm is not None,
                "state": self.state, "tier": self._base_tier(), "mood": self.quadrant, "note": self.note,
                "key": key_label(getattr(self.f, "key", -1), self.f.mode) if self.f is not None else "",
                "key_conf": round(self.f.key_conf, 2) if self.f is not None else 0.0,
                "bar_len": self.bar_len, "scene_rev": self.scene_rev, "scene_last": self.scene_last,
                "meter": meter_label(getattr(self.f, "meter", 0)) if self.f is not None else "",
                "meter_conf": round(getattr(self.f, "meter_conf", 0.0), 2) if self.f is not None else 0.0,
                "key_sure": bool(self.f is not None and self.f.key_conf >= self.cfg["key_conf_min"]),
                "aim": self.aim or "", "aim_vals": self._aim_vals(), "aims": self.aims_info(),
                "beam": {"auto": not self.beam_man, "vals": self.beam},
                "autoscene": self.sa["name"] if self.sa is not None else "",
                "eb": {"cur": int(self.presets[0].values.get("preset", 0)) if self.presets else 0,
                       "on": bool(self.presets and self.presets[0].values.get("dimmer", 0) > 0),
                       "man": self.eb_man or 0, "auto": self.sa_eb["pid"] if self.sa_eb is not None else 0,
                       "names": self._eb_names(), "strobe_ids": list(EB_STROBE), "no_sound": self.cfg["eb_no_sound"] >= 0.5,
                       "sound_ids": [int(i) for i in (self.presets[0].extra.get("preset_sound") or [])] if self.presets else []},
                "blitz": self.blitz, "blitz_hz": round(self.blitz_hz, 1), "blitz_eff": round(self._blitz_rate(), 1),
                "fx_pending": self.fx_pending,
                "artnet": self._artnet_info(),
                "solo": (self.solo["fx"].extra.get("label", self.solo["fx"].name) if self.solo else ""),
                "ola_out": bool(self.cfg["ola_out"] > 0.5),
                "ola_sending": True if self.output is None else self.output.is_sending(self.rig.target),
                "dmx_via": "usb" if self.cfg["dmx_via"] > 0.5 else "ola", "dmx_usb": self.dmx_usb_status(),
                "artin": self._artin_status(),
                "wled_out": bool(self.cfg["wled_out"] > 0.5),
                "nano_out": bool(self.cfg["nano_out"] > 0.5), "nano_present": bool(self._nano_targets()),
                "ola_have": self.cfg["ola_have"] > 0.5, "wled_have": self.cfg["wled_have"] > 0.5, "nano_have": self.cfg["nano_have"] > 0.5,
                "link_on": bool(self.cfg["link_on"] > 0.5),
                "lang": "en" if self.cfg["ui_lang"] > 0.5 else "de", "texts_rev": self.texts.rev,
                "ui_hints": bool(self.cfg["ui_hints"] > 0.5),
                "powering_off": self.powering_off, "poweroff_ok": self.allow_poweroff, "power_mode": self.power_mode, "safety_open": self.safety_open,
                "home": self.home.status() if self.home is not None else None,
                "power_for": self._power_for(),
                "power_off": self._power_off() if self.home is not None else [],
                "fine": self._fine_public(sc),
                "home_cfg": [{"key": p.key, "label": p.label, "value": self.cfg[p.key], "lo": p.lo, "hi": p.hi,
                              "step": p.step, "unit": p.unit} for p in HOME_SETTINGS] if self.home is not None else None,
                "link": self.link_out.status() if self.link_out is not None else {"available": False, "error": "im Trockenlauf aus"},
                "wled_sending": True if self.output is None else all(self.output.is_sending(t) for t in self._wled_targets()),
                **self.lyric_status(time.time()), "backup": dict(self.backup_info), "health_level": self.health_level, "mx": self._mx_public(), "sr": self.titles.public() if self.titles is not None else None, "tempo_src": "Mixxx" if self.mx_tempo_on else "Audio",
                "key_src": "Mixxx" if self.mx_key_on else "Audio", "mx_name": "Auto-DJ" if (self.mx or {}).get("src") == "autodj" else "Mixxx",
                "reach": self.reach, "reach_ip": self.reach_ip, "reach_url": self.reach_url, "net": self.net, "drop": self.state == "drop", "laser": self.laser_on,
                "beat_ago": None if self.beat_t is None else round(max(0.0, time.time() - self.beat_t), 3),
                "beat_bpm": round(self._bpm_show(), 2),
                "beat_clear": round(float(getattr(self.src, "beat_clarity", -1.0)), 2), "bpm_unsure": self.bpm_unsure,
                "freeze": self.freeze, "color_freeze": self.color_freeze, "build": self.build_t0 is not None, "build_p": round(self.build_p, 2),
                "fog_on": self._fog_clock() < self.fog_end,
                "fog_wait": 0 if self._fog_clock() < self.fog_end else max(0, round(self.fog_end + self._fog_cool() - self._fog_clock())),
                "fog_st": self._fog_status(),
                "fog_note": self._fog_note(),
                "lvl": self.src.level() if hasattr(self.src, "level") else None,          # kleines Pegelmeter in Zeile 2
                "lvsrc": ("lan" if getattr(self.src, "dev_name", "") in ("Musik-Rechner (Netzwerk)", "Mac (Netzwerk)")
                          else "bt" if getattr(self.src, "dev_name", "") == "Bluetooth" else "line"),
                "lvfwd": self.src.fwd_state() if hasattr(self.src, "fwd_state") else None,   # Weiterleitung (25.11.2026)
                "held": sorted(self.held)}

    # ---- Einzel-Strobe (AUTO): EIN Fixture blitzt ueber seinen eigenen Strobe-Kanal ------------------------
    def _solo_candidates(self):
        amb = set(id(f) for f in self.rgb_amb)                  # Ambiente (z. B. Barlicht) blitzt nie einzeln
        return [fx for fx in self.rig.fixtures if fx.tdef.get("hw_strobe") and not fx.locked and id(fx) not in amb]

    def _solo_values(self, fx, rate):
        hs = fx.tdef["hw_strobe"]
        r = clamp01(rate)
        out = {}
        if "value" in hs:
            out[hs["param"]] = hs["value"]
        elif "param" in hs:
            out[hs["param"]] = int(round(hs["lo"] + r * (hs["hi"] - hs["lo"])))
        sp = hs.get("speed")
        if sp:
            out[sp["param"]] = int(round(sp["lo"] + r * (sp["hi"] - sp["lo"])))
        out.update(hs.get("set", {}))
        return out

    def _solo_apply(self, fx, rate):
        """Fixture auf volle Helligkeit in der aktuellen Farbe stellen und seinen Strobe-Kanal aktivieren."""
        hs = fx.tdef["hw_strobe"]
        zs = fx.zones()
        if zs:
            for zi in range(len(zs)):
                r, g, bl, wv, uvc = self._acolor(1.0, 0.5, fx, zi)
                self.paint(fx, zi, r, g, bl, w=wv, uv=1.0 if "uv1" in fx.map else uvc)
        elif "dimmer" in fx.map:
            fx.set("dimmer", 255 * self.master)
            if "colorwheel" in fx.map and fx.presets:
                fx.preset("colorwheel", self._wheel_auto(self._t_now))
        for k, v in self._solo_values(fx, rate).items():
            if k in fx.map:
                fx.set(k, v)
        fx.hw_unlock = set(hs.get("unlock", []))

    def _solo_end(self, fx):
        hs = fx.tdef.get("hw_strobe") or {}
        params = set(self._solo_values(fx, 0.0))
        for p in params:
            if p in fx.map:
                fx.set(p, fx.defaults.get(p, 0))
        fx.hw_unlock = set()

    def _solo_update(self, now, new_steps, bl, burst, active_ok):
        """Einzel-Strobe starten, anwenden und beenden. Nur mit Strobe-Erlaubnis, nur im AUTO-Modus (Test: immer)."""
        c = self.cfg
        for fx in self.rig.fixtures:
            if fx.hw_unlock:
                fx.hw_unlock = set()
        if self.solo is not None:
            fx, test = self.solo["fx"], self.solo.get("test")
            stop = (not self.strobe or now >= self.solo["until"]
                    or (not test and (not active_ok or burst or self.state not in ("normal", "drop"))))
            if stop:
                self._solo_end(fx)
                self.solo = None
            else:
                self._solo_apply(fx, self.solo["rate"])
                return
        if (not self.strobe or c["solo_on"] < 0.5 or not active_ok or burst or not new_steps
                or self.state not in ("normal", "drop") or self._base_tier() < c["solo_min_tier"]
                or now < self.solo_next_t or self.step % max(1, int(c["solo_every"]) * bl) != 0
                or self._rng.random() > c["solo_prob"]):
            return
        cands = [fx for fx in self._solo_candidates() if fx.name != self.solo_last] or self._solo_candidates()
        if not cands:
            return
        fx = self._rng.choice(cands)
        per = 60.0 / (self.bpm if self.bpm > 0 else 120.0)
        until = now + c["solo_beats"] * per
        self.solo = {"fx": fx, "until": until, "rate": c["solo_rate"]}
        self.solo_last, self.solo_next_t = fx.name, until + 1.0
        self._solo_apply(fx, c["solo_rate"])

    def _fx_check(self):
        try:
            import fixture_edit as fe
            self.fx_pending = bool(self.rig.user is not None and fe.pending_restart(self.rig))
        except Exception:                                   # noqa: BLE001
            self.fx_pending = False

    def _artnet_info(self):
        """Art-Net-Gateway fuers Panel (Einstellungen, Verbindungen): jetzt, nach dem Neustart, aus fixtures.yaml."""
        import fixture_edit as fe
        try:
            return fe.artnet_info(self.rig)
        except Exception:                                       # noqa: BLE001
            return {"now": self.rig.target, "next": self.rig.target, "file": self.rig.target}

    def _fixture_cmd(self, d):
        """Fixtures im Panel bearbeiten (Aenderungen stehen in fixtures_user.json, ein Neustart uebernimmt sie)."""
        import fixture_edit as fe
        if self.rig.user is None:
            raise ValueError("Das Bearbeiten der Fixtures ist nicht verfuegbar")
        if "fx_save" in d:
            name, warn, live = fe.cmd_fixture_save(self.rig, d["fx_save"])
            self._fx_check()
            self.note = "Gespeichert."
            if live:
                self.note += " Name und Nummer gelten sofort" + (", die uebrigen Aenderungen nach dem Neustart." if self.fx_pending else ".")
            elif self.fx_pending:
                self.note += " Die Aenderungen gelten nach dem Neustart."
            if warn:
                self.note += " Achtung: " + "; ".join(warn)
        if "fx_delete" in d:
            fe.cmd_fixture_delete(self.rig, d["fx_delete"])
            self._fx_check()
            self.note = "Fixture entfernt. Wirkt nach dem Neustart."
        if "fx_restore" in d:
            fe.cmd_fixture_restore(self.rig, d["fx_restore"])
            self._fx_check()
            self.note = "Fixture wieder eingeblendet. Wirkt nach dem Neustart."
        if "fx_desc" in d:
            x = d["fx_desc"]
            fe.cmd_desc(self.rig, x.get("type"), x.get("param"), x.get("text"))
        if "type_save" in d:
            nm = fe.cmd_type_save(self.rig, d["type_save"])
            self._fx_check()
            self.note = f"Typ {nm} gespeichert. Er ist jetzt beim Hinzufuegen waehlbar."
        if "type_import" in d:
            nm, notes = fe.cmd_type_import(self.rig, d["type_import"])
            self._fx_check()
            self.note = f"Typ {nm} aus der Datenbank gespeichert. Er ist jetzt beim Hinzufuegen waehlbar." + (" " + " ".join(notes[:2]) if notes else "")
        if "type_delete" in d:
            fe.cmd_type_delete(self.rig, d["type_delete"])
            self._fx_check()
            self.note = "Typ geloescht"
        if "nano_host" in d:
            ip = fe.cmd_nano_host(self.rig, d["nano_host"])
            self._fx_check()
            self.note = f"Nanoleaf-IP {ip} gespeichert." + (" Sie gilt nach dem Neustart." if self.fx_pending else "")
        if "nano_token" in d:
            ok = fe.cmd_nano_token(self.rig, d["nano_token"])
            self._fx_check()
            self.note = ("Neuer Nanoleaf-Token gespeichert (vom Nanoleaf bestaetigt)." if ok else
                         "Neuer Nanoleaf-Token gespeichert, aber der Nanoleaf war nicht erreichbar (ungeprueft).") \
                + " Er gilt nach dem Neustart."
        if "artnet_target" in d:
            ip = fe.cmd_artnet_target(self.rig, d["artnet_target"])
            self._fx_check()
            self.note = f"Art-Net-Gateway {ip} gespeichert." + (" Es gilt nach dem Neustart." if self.fx_pending else "")
        if "nano_pair" in d:
            name, n = fe.cmd_nano_pair(self.rig, d["nano_pair"])
            self._fx_check()
            self.note = f"Nanoleaf gekoppelt: {name}, {n} Panels. Gilt nach dem Neustart."
        if d.get("fx_reset"):
            fe.reset_user(self.rig)
            self._fx_check()
            self.note = "Alle Aenderungen verworfen (fixtures.yaml gilt wieder). Wirkt nach dem Neustart."
        if d.get("restart"):
            self.restart_requested = True
            self.note = "Neustart ..."

    POWEROFF = ["sudo", "-n", "/usr/sbin/poweroff"]

    def _poweroff(self):
        """Pi sauber herunterfahren: Licht sofort aus, dann poweroff. Braucht die Freigabe aus install_poweroff.sh
        (admin darf nur diesen Befehl ohne Passwort). Im Simulator/Trockenlauf gesperrt."""
        if self.power_mode == "quit":                          # Mac/Windows: nur den Light-Butler beenden, nie den Rechner
            self.override = "blackout"
            self.powering_off = True
            self.note = "Der Light-Butler wird beendet"

            def stop_later():
                time.sleep(1.5)                                # Antwort ans Panel noch abschicken
                self.quit_requested = True
            threading.Thread(target=stop_later, daemon=True).start()
            return
        if not self.allow_poweroff:
            raise ValueError("Herunterfahren geht nur am Pi im echten Betrieb (nicht im Simulator)")
        try:
            ok = self._run_cmd(["sudo", "-n", "-l", "/usr/sbin/poweroff"], capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        if not ok:
            raise ValueError("Herunterfahren ist noch nicht eingerichtet. Am Pi einmal ausfuehren: "
                             "sudo bash ~/lichtshow/install_poweroff.sh")
        self.override = "blackout"                             # Licht sofort aus (Laser ohnehin aus)
        self.powering_off = True
        self.note = "Der Pi faehrt herunter"

        def later():
            time.sleep(1.5)                                    # Antwort ans Panel noch abschicken
            try:
                self._run_cmd(self.POWEROFF, capture_output=True, timeout=30)
            except (OSError, subprocess.SubprocessError) as e:
                self.powering_off = False
                self.note = f"Herunterfahren fehlgeschlagen: {e}"[:150]
        threading.Thread(target=later, daemon=True).start()

    def _backup_now(self):
        if self.backup_info["running"]:
            self.note = "Sicherung laeuft schon"
            return
        self.backup_info = {"running": True, "last": "", "error": ""}

        def work():
            try:
                import backup
                cfg = backup.load_conf()
                path, n = backup.create(cfg, reason="Panel")
                ok, msg = backup.verify(path)
                extra = backup.copy_out(cfg, path)
                backup.prune(cfg)
                text = f"{os.path.basename(path)}: {n} Dateien, {os.path.getsize(path) // 1024} KB" + (f" - {extra}" if extra else "")
                backup.log(cfg, "Sicherung (Panel) " + text)
                self.backup_info = {"running": False, "last": text, "error": "" if ok else msg}
            except Exception as e:                              # noqa: BLE001
                self.backup_info = {"running": False, "last": "", "error": str(e)[:150]}
        threading.Thread(target=work, daemon=True).start()
        self.note = "Sicherung gestartet"

    def takt(self, wall=None):
        """Takt fuer andere Geraete (/api/takt, Wunsch 23.11.2026: Fernseher zeigt Muster im Takt). Nur lesen.
        beat = Zaehlzeit der Show (Vielfaches von quantum = die Eins, wie das Licht zaehlt) mit Nachkommastellen zum
        Zeitpunkt zeit (Unix-ms), aus der gleichmaessigen Takt-Uhr (takt.TaktClock: erkannte Schlaege geglaettet).
        Nicht die Zeitachse von Ableton Link: deren Schlaege liegen nicht auf der Musik. aktiv erst bei stabilem Tempo."""
        wall = time.time() if wall is None else wall
        clk, q = self.takt_clock, max(1, int(self.bar_len))
        live = self.manual_bpm or self._bpm_live()
        aktiv = bool(live and live > 0 and clk.stable(wall))
        f = self.f
        # spielt = Musik da, auch ohne Beat (Eichstueck 23.11.2026: Applaus und Melodie galten sonst als "spielt nicht")
        spielt = bool(f is not None and not f.silent and self.state != "idle" and self.override != "blackout")
        b = clk.at(wall)
        d = {"version": 1, "aktiv": aktiv, "spielt": spielt, "bpm": round(clk.bpm if aktiv else float(live or 0.0), 2), "quantum": q,
             "beat": round(b if b is not None else float(self.step), 3), "zeit": round(wall * 1000.0, 1)}
        st = self._style_key()
        if st:
            d["stil"] = st
        sec, seit, over = self._takt_now(wall)
        d["sprache"] = bool(self.talk)                    # jemand spricht (speech_guard, 25.11.2026): keine Drops
        d["abschnitt"] = sec
        if seit is not None:
            d["abschnittSeit"] = seit
        d["ereignis"] = self.takt_ev + (1 if over else 0)
        mx = self.mx or {}
        d["quelleAbschnitt"] = "analyse" if (mx.get("plan") and self.cfg["mixxx_light"] > 0.5) else "live"
        nd = self._takt_next_drop(wall)
        if nd is not None:
            d["naechsterDrop"] = nd
        d["energie"] = round(clamp01(self.arousal), 2) if spielt else 0.0
        sg = self._takt_song(wall)                        # Liedtext fuer den Fernseher (23.11.2026)
        if sg is not None:
            d["liedId"] = sg["id"]
            if sg["pos"] is not None:
                d["liedPosition"] = round(sg["pos"], 2)
        d["lyrics"] = bool(sg and (sg["lines"] or sg["plain"]))
        dyn, dseit = self.takt_dyn
        if dyn:
            d["dynamik"] = dyn
            if dseit is not None:
                d["dynamikSeit"] = dseit
        d["tasten"] = dict(self.takt_keys)
        d["tastenSeit"] = dict(self.takt_keys_since)
        d["tastenZaehler"] = dict(self.takt_keys_n)
        if self.blitz:                                     # Blitze pro Sekunde, genau wie das Licht blitzt (mit der Grenze ohne Erlaubnis)
            d["strobeHz"] = round(float(self._blitz_rate()), 2)
        if self.build_t0 is not None:                      # Stand der WOW!-Steigerung, derselbe Wert, mit dem das Licht rechnet
            d["wowProzent"] = int(round(clamp01(self.build_p) * 100))
        d["farben"] = self._takt_colors()
        if self.takt_scene:                                # Szene, Effektband, Bewegung (Wunsch 24.11.2026): fehlen, wenn nichts laeuft
            d["szene"] = self.takt_scene
            if self.takt_scene_since is not None:
                d["szeneSeit"] = round(self.takt_scene_since, 3)
        eff = self._takt_effect()
        if eff:
            d["effekt"] = eff
        mv = self._takt_move()
        if mv:
            d["bewegung"] = mv
        api = clamp01(self.glevel.get("api", 1.0))        # Gruppen-Regler API: daempft beide Werte fuer andere Geraete
        d["helligkeit"] = round(clamp01(self.master * self.loud_k) * api if self.override != "blackout" else 0.0, 2)
        d["masterDim"] = int(round(clamp01(self.master) * api * 100))   # General Dimmer x API-Regler in %
        lv = self._takt_levels()                           # Pegel und Baender der Musik (ohne Musik weggelassen)
        if lv:
            d.update(lv)   # Stand des General Dimmers in %, ohne Lautstaerke und BLACKOUT
        tl = self._takt_title()
        if tl:
            d["titel"] = tl
        if self.link_out is not None and getattr(self.link_out, "on", False):
            d["teilnehmer"] = int(self.link_out.peers)
        d["jetzt"] = round(time.time() * 1000.0, 1)
        return d

    def _takt_song(self, now):
        """Laufendes Lied mit Liedtext fuer /api/takt und /api/lyrics: {id, name, lines, plain, pos, sync, quelle} oder None.
        Wie der Liedtext im Panel (Show, Mixxx/Auto-DJ, Titelerkennung), dazu Musik-DB im Browser und Internetradio
        (dort ist die Stelle im Lied unbekannt: pos None, nur der Text). Liest nur; geholt wird wie immer nur mit lyrics_auto."""
        try:
            s = self._lyric_source(now)
        except Exception:                                   # noqa: BLE001  Liedtext haelt nie etwas auf
            s = None
        radio = False
        if s is None and self.cfg["lyrics_auto"] > 0.5 and self.lyric_cache is not None:
            lp = self.local.panel() if self.local is not None else None
            rs = self.radio.song() if self.radio is not None else None
            if lp:
                name = (lp["artist"] + " - " if lp.get("artist") else "") + lp["title"]
                e = self.lyric_cache.get_entry(name, lp.get("dur") or 0.0, now)
                s = {"src": "local", "name": name, "dur": lp.get("dur") or 0.0, "lines": e["lines"], "plain": e["plain"], "pos": lp["pos"]}
            elif rs:
                name = rs["artist"] + " - " + rs["title"]
                e = self.lyric_cache.get_entry(name, 0.0, now)
                s, radio = {"src": "radio", "name": name, "dur": 0.0, "lines": e["lines"], "plain": e["plain"], "pos": None}, True
        if s is None:
            return None
        import hashlib
        lid = hashlib.sha1(("%s|%d" % (s["name"], round(s.get("dur") or 0.0))).encode("utf-8")).hexdigest()[:8]
        lines, plain = s["lines"] or [], s.get("plain") or ""
        if self.cfg["lyrics_api_chorus"] > 0.5:
            lines, plain = self._chorus_only(lines, plain)
        return {"id": lid, "name": s["name"], "lines": lines, "plain": plain,
                "pos": None if radio else s.get("pos"), "sync": bool(s["lines"]) and not radio,
                "quelle": "show" if s["src"] == "show" else "lrclib"}

    @staticmethod
    def _chorus_only(lines, plain):
        """Einstellung lyrics_api_chorus (Wunsch von Markus 24.11.2026): fuer die Schnittstelle nur der Refrain, gleiche Regel
        wie auf der Pixel-Matrix (lyrics.repeats). Mit Zeiten werden die anderen Zeilen leer (Pause, die Zeit bleibt), ohne
        Zeiten bleibt zwischen den Refrain-Bloecken eine Leerzeile. Kein Refrain = kein Text."""
        if lines:
            rep = lyric_repeats(lines)
            out = [[t, x if i in rep else ""] for i, (t, x) in enumerate(lines)]
            return (out if any(x for _, x in out) else []), ""
        rows = [x.strip() for x in str(plain).splitlines()]
        rep = lyric_repeats([[0.0, x] for x in rows])
        out = []
        for i, x in enumerate(rows):
            if i in rep:
                out.append(x)
            elif out and out[-1]:
                out.append("")
        return [], "\n".join(out).strip("\n")

    def lyrics_api(self, wall=None):
        """GET /api/lyrics: alle Zeilen des laufenden Liedes (Zeit in s ab Liedanfang, leer = Pause), liedId wie /api/takt."""
        wall = time.time() if wall is None else wall
        sg = self._takt_song(wall)
        if sg is None:
            return {"version": 1, "liedId": "", "titel": "", "synchron": False, "quelle": "", "zeilen": []}
        if sg["sync"]:
            rows = [{"t": round(float(t), 2), "text": str(x)} for t, x in sg["lines"]]
        elif sg["lines"]:
            rows = [{"text": str(x)} for _, x in sg["lines"]]
        else:
            rows = [{"text": x.strip()} for x in sg["plain"].splitlines()]
        return {"version": 1, "liedId": sg["id"], "titel": sg["name"].replace(" - ", " – ", 1), "synchron": sg["sync"] and bool(rows),
                "quelle": sg["quelle"] if rows else "", "zeilen": rows}

    TAKT_LVL_TC = 0.25            # /api/takt pegel/baender: Glaettung
    TAKT_LVL_WIN = 30             # ... bezogen auf den Hoechstwert der letzten so vielen Sekunden
    TAKT_LVL_DB = 30.0            # ... in dB: so viel leiser als der Hoechstwert = 0 (das Ohr hoert logarithmisch)
    TAKT_BANDS = (("level", "pegel"), ("bass", "bass"), ("mid", "mitten"), ("high", "hoehen"))

    def _takt_level(self, f, dt):
        """Pegel der Musik fuer /api/takt (Wunsch Bravia-Dashboard 23.11.2026), unabhaengig von Master und loud_k: je Band
        der ungewichtete Pegel der Analyse (Analyzer.raw_lvl, im Simulator die Merkmale), ueber TAKT_LVL_TC geglaettet, geteilt
        durch den Hoechstwert der letzten TAKT_LVL_WIN Sekunden (je Sekunde ein Hoechstwert), in dB (TAKT_LVL_DB leiser = 0).
        Leise aufgenommene Lieder wirken so nicht schwach, beim Ausklingen geht es gegen 0. Nur lesen."""
        raw = getattr(self.src, "raw_lvl", None)
        if not isinstance(raw, dict):
            raw = {"level": f.level, "bass": f.bass, "mid": f.mid, "high": f.high}
        a = 1 - math.exp(-dt / self.TAKT_LVL_TC)
        self.takt_lvl_n += 1
        sec = self.takt_lvl_n // 40                      # Bilder zu 25 ms: 40 je Sekunde
        for k, _ in self.TAKT_BANDS:
            v = 0.0 if f.silent else max(0.0, float(raw.get(k, 0.0)))
            self.takt_lvl[k] += a * (v - self.takt_lvl[k])
            q = self.takt_lvl_max[k]
            if q and q[-1][0] == sec:
                if self.takt_lvl[k] > q[-1][1]:
                    q[-1] = (sec, self.takt_lvl[k])
            else:
                q.append((sec, self.takt_lvl[k]))
            while q and q[0][0] <= sec - self.TAKT_LVL_WIN:
                q.popleft()

    def _takt_levels(self):
        """{"pegel": 0..1, "baender": {...}} oder None (ohne Musik)."""
        f = self.f
        if f is None or f.silent or self.state == "idle" or f.db_short <= self.cfg["silence_db"]:
            return None
        out = {}
        for k, name in self.TAKT_BANDS:
            top = max((m for _, m in self.takt_lvl_max[k]), default=0.0)
            r = self.takt_lvl[k] / top if top > 1e-9 else 0.0
            out[name] = round(clamp01(1.0 + 20.0 * math.log10(r) / self.TAKT_LVL_DB), 3) if r > 1e-6 else 0.0
        return {"pegel": out["pegel"], "baender": {n: out[n] for _, n in self.TAKT_BANDS[1:]}}

    TAKT_KEYS = ("strobe", "wow", "sonnenbrille", "freeze", "blackout", "nebel")

    def _takt_scene(self):
        """Name der aktiven Szene (von Hand oder Szenen-Automatik), sonst None. Nur Anzeige."""
        if self.sc is not None:
            return self.sc.name
        return self.sa["name"] if self.sa is not None else None

    def _takt_move(self):
        """Laufender Bewegungseffekt fuer /api/takt (wie die markierten Knoepfe im Panel), None bei Stop."""
        from takt_liste import MOVE_NAMES
        m = self.sc.move if self.sc is not None else (self.auto_move or "auto")
        if m == "auto":
            m = self._pilot_move()                           # Bewegung nach der Musik: der aehnlichste Knopf
        return None if m in ("home", "", None) else MOVE_NAMES.get(m, m)

    def _takt_effect(self):
        """Name der Voreinstellung, die gerade auf dem Effektband laeuft, None wenn aus."""
        if not self.presets or self.presets[0].values.get("dimmer", 0) <= 0:
            return None
        cur = int(self.presets[0].values.get("preset", 0))
        return dict(self._eb_names()).get(cur) if cur > 0 else None

    def _takt_keys(self, now):
        """Effekt-Tasten fuer /api/takt, je Bild aus dem Zustand gelesen (Panel, APC, Lumi gleich): gedrueckt, ab welchem
        Schlag, wie oft. Nur Anzeige."""
        sz = self._takt_scene()                              # Szene: ab welchem Schlag (szeneSeit)
        if sz != self.takt_scene:
            self.takt_scene, self.takt_scene_since = sz, (self._takt_beat_at(now) if sz else None)
        cur = {"strobe": bool(self.blitz), "wow": self.build_t0 is not None, "sonnenbrille": self.override == "allbright",
               "freeze": bool(self.freeze), "blackout": self.override == "blackout", "nebel": "fog" in self.held}
        for k, on in cur.items():
            if on and not self.takt_keys[k]:
                self.takt_keys_n[k] += 1
                b = self.takt_clock.at(now)
                if b is not None:
                    self.takt_keys_since[k] = round(b, 3)
            elif not on:
                self.takt_keys_since.pop(k, None)
        self.takt_keys = cur
        dyn = self._takt_dyn()                              # Dynamik-Stufe wie fuers Licht: Wechsel ab dem naechsten Taktanfang
        if dyn != self.takt_dyn[0]:
            self.takt_dyn = (dyn, self._takt_bar_at(now) if dyn else None)

    TAKT_DYN = {0: "langsam", 1: "langsam", 2: "mittel", 3: "schnell"}

    def _takt_dyn(self):
        """langsam (Chillen, Groove), mittel (Party) oder schnell (Vollgas): die Stufe, mit der das Licht gerade laeuft
        (eff_tier: Break ruhig, Aufbau und Drop voll, sonst nach der Musik oder dem Tempo-Knopf). Ohne Musik None."""
        if self.state == "idle" or self.f is None or self.f.silent:
            return None
        return self.TAKT_DYN.get(self.eff_tier())

    def _takt_beat_at(self, t):
        """Ganzer Schlag der Takt-Uhr am naechsten an Zeitpunkt t, oder None ohne Uhr."""
        b = self.takt_clock.at(t)
        return None if b is None else float(round(b))

    def _takt_bar_at(self, t):
        """Taktanfang (die Eins) am naechsten an Zeitpunkt t, oder None ohne Uhr."""
        b = self.takt_clock.at(t)
        return None if b is None else to_bar(b, self.bar_len)

    TAKT_SECTION = {"build": "aufbau", "drop": "drop", "break": "break", "gap": "break"}
    TAKT_DROP_BARS = 4                                   # Drop mindestens 4 Takte melden (Rueckmeldung Dashboard)

    def _takt_drop_end(self):
        """Schlag, ab dem ein Drop als vorbei gilt: nach drop_len und mindestens 4 Takten, auf einem Taktanfang. None ohne Uhr."""
        start = self.takt_enter if self.takt_enter is not None else self._takt_bar_at(self.state_t)
        by_time = self.takt_clock.at(self.state_t + max(0.8, self.cfg["drop_len_s"]))
        if start is None or by_time is None:
            return None
        q = max(1, int(self.bar_len))
        return max(start + self.TAKT_DROP_BARS * q, to_bar(by_time + q / 2.0 - 0.001, q))

    def _takt_now(self, now):
        """(Abschnitt, ab Schlag, Drop gerade von selbst vorbei) wie das Licht; die Pause vor dem Drop zaehlt als break."""
        st = self.state
        seit = self.takt_enter if self.takt_enter is not None else self._takt_bar_at(self.state_t)
        if st == "drop":
            end, b = self._takt_drop_end(), self.takt_clock.at(now)
            over = (b >= end) if (end is not None and b is not None) else now - self.state_t >= max(0.8, self.cfg["drop_len_s"])
            if over:
                return "normal", end, True
            return "drop", seit, False
        return self.TAKT_SECTION.get(st, "normal"), seit, False

    def _takt_section(self, now):
        return self._takt_now(now)[0]

    def _takt_next_drop(self, now):
        """Schlag des naechsten Drops, wenn die Analyse des Liedes (Mixxx-Plan) ihn kennt, sonst None."""
        m = self.mx or {}
        if not (m.get("connected") and m.get("plan") and self.mx_tempo_on):
            return None
        nxt = next((u for u in (m.get("next") or []) if u.get("type") == "drop"), None)
        if nxt is None:
            return None
        return self._takt_beat_at(now + float(nxt.get("in") or 0.0))

    def _takt_colors(self):
        """1 bis 4 Farben wie das Licht gerade: gewaehlte Farbtoene, sonst der Farbton der Stimmung (Weiss, UV, Bunt eigens)."""
        import colorsys
        hx = lambda h, s=1.0, v=1.0: "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb(h % 1.0, s, v))
        c = self.auto_color
        if c == "white":
            return ["#ffffff"]
        if c == "uv":
            return [hx(0.78, 1.0, 0.8)]
        if self.auto_rainbow or c == "rainbow":
            return [hx(self.hue + k / 4.0) for k in range(4)]
        hues = [SCENE_COLORS[x] for x in self.auto_colors if x in SCENE_COLORS][:4]
        if hues:
            return [hx(h) for h in hues]
        if c == "multi":
            return [hx(self.hue), hx(self.hue + 0.5)]
        return [hx(self.hue), hx(self.hue + 0.08)]

    def _takt_title(self):
        m = self.mx or {}
        if m.get("connected") and m.get("deck") is not None and m.get("title"):
            return (m.get("artist") + " – " if m.get("artist") else "") + m["title"]
        if self.local is not None and self.local.song() is not None:
            ls = self.local.song()
            return (ls["artist"] + " – " if ls.get("artist") else "") + ls["title"]
        if self.radio is not None and self.radio.song() is not None:
            rs = self.radio.song()
            return rs["artist"] + " – " + rs["title"]
        song = self.titles.song if self.titles is not None and getattr(self.titles, "active", False) else None
        if isinstance(song, dict) and song.get("title"):
            return (song.get("artist") + " – " if song.get("artist") else "") + song["title"]
        return ""

    BPM_FINE_TOL = 0.04          # feines Tempo gilt nur so nahe an aubio (halb/doppelt eingeschlossen)

    def _bpm_refine(self, f):
        """Eichstueck 23.11.2026: aubio rastet auf seine Blockgroesse ein (am Pi 121,7 statt 120, 96 statt 95). Liegt das feine
        Tempo aus der Schlag-Klarheit (beat_clarity.py, Analyzer.bpm_fine) hoechstens BPM_FINE_TOL neben aubio (auch halb oder
        doppelt), gilt es, in aubios Oktave. Die Schlaege selbst bleiben von aubio. Nicht bei Mixxx-Tempo, von Hand, bpm_fine 0."""
        fine = getattr(self.src, "bpm_fine", 0.0) or 0.0
        if fine <= 0 or f.bpm <= 0 or self.cfg["bpm_fine"] < 0.5 or self.mx_tempo_on or self.manual_bpm is not None:
            return f
        for k in (1.0, 2.0, 0.5):
            if abs(f.bpm / (fine * k) - 1.0) <= self.BPM_FINE_TOL:
                return f._replace(bpm=fine * k)
        return f

    BPM_SURE_TOL = 0.03          # so weit darf das erkannte Tempo schwanken (halb/doppelt zaehlt als gleich)
    BPM_SURE_KICK_WIN = 4.0      # ohne Klarheits-Messung (Simulator): Kicks in diesem Fenster belegen den Beat
    BPM_SURE_KICKS = 3
    BPM_SURE_LONG = 3.0          # ohne Klarheits-Messung und ohne Kicks: so viel mal laenger warten

    def _bpm_gate(self, f, now):
        """Wunsch von Markus 23.11.2026: in einer Einleitung ohne Beat (Klatschen, leise Trompete, eine Minute lang) meldet
        aubio trotzdem ein Tempo (oft 120-130, das bevorzugt es), das Licht wird unruhig. Das Tempo aus dem Audio gilt erst,
        wenn die Schlag-Klarheit (beat_clarity.py, Analyzer.beat_clarity) im Mittel der letzten bpm_sure_s Sekunden mindestens
        bpm_clear war und das Tempo dabei gleich blieb. Ohne diese Messung (Simulator): gleiches Tempo plus Kicks, ohne Kicks das BPM_SURE_LONG-fache.
        Bis dahin rechnet das Licht wie ohne Tempo-Erkennung (BPM 0: der Kick fuehrt, Anzeige --). Einmal sicher, bleibt es
        bis zur naechsten Stille oder einem anderen Tempo (Breaks im Lied nicht). Mixxx, Tempo von Hand, bpm_sure_s 0: aus."""
        wait = self.cfg["bpm_sure_s"]
        nk = max(0, f.kick_count - self.bs_seen_kick)
        self.bs_seen_kick = f.kick_count
        for _ in range(min(nk, 50)):
            self.bs_kicks.append(now)
        while self.bs_kicks and now - self.bs_kicks[0] > self.BPM_SURE_KICK_WIN:
            self.bs_kicks.popleft()
        clar = getattr(self.src, "beat_clarity", None)
        if clar is not None:                      # Klarheit der letzten bpm_sure_s Sekunden (Mittelwert, Eichstueck 23.11.2026:
            self.bs_clar.append((now, float(clar)))   # ein weicher Beat schwankt um die Schwelle, ununterbrochen war zu streng)
            while self.bs_clar and now - self.bs_clar[0][0] > max(wait, 0.5):
                self.bs_clar.popleft()
        if wait <= 0 or self.mx_tempo_on or self.manual_bpm is not None:
            self.bpm_unsure = False
            return f
        if f.silent or f.bpm <= 0:                # Stille: danach beginnt die Pruefung neu
            self.bs_ref = self.bs_since = None
            self.bs_sure = self.bpm_unsure = False
            return f
        r = f.bpm / self.bs_ref if self.bs_ref else 0.0
        while 0 < r < 0.75:
            r *= 2.0
        while r >= 1.5:
            r /= 2.0
        if self.bs_ref is None or abs(r - 1.0) > self.BPM_SURE_TOL:
            self.bs_since, self.bs_sure = now, False   # neues Tempo: wieder warten
        self.bs_ref = f.bpm
        held = now - self.bs_since
        if not self.bs_sure:
            if clar is not None:
                cl = [c for _, c in self.bs_clar]
                full = bool(self.bs_clar) and now - self.bs_clar[0][0] >= wait - 0.1
                self.bs_sure = held >= wait and full and sum(cl) / len(cl) >= self.cfg["bpm_clear"]
            elif held >= wait and (len(self.bs_kicks) >= self.BPM_SURE_KICKS or held >= wait * self.BPM_SURE_LONG):
                self.bs_sure = True
        self.bpm_unsure = not self.bs_sure
        return f._replace(bpm=0.0) if self.bpm_unsure else f

    def _bpm_live(self):
        """Erkanntes Tempo fuer die Anzeige. Bei Stille oder wenn seit 4 Sekunden kein Beat kam, 0 (Anzeige --)
        statt des zuletzt erkannten Wertes."""
        f = self.f
        if f is None or self.state == "idle" or self.beat_t is None:
            return 0.0
        ref = self.last_t if self.last_t is not None else time.time()
        return f.bpm if ref - self.beat_t < 4.0 else 0.0

    def _bpm_show(self):
        """Tempo fuer die Anzeige (BPM-Zahl und Lamperl im Panel): spielt ein Deck von Mixxx oder vom Auto-DJ hoerbar, dessen Tempo,
        auch ohne Ton am Eingang (Wunsch von Markus 08.11.2026; das Licht bleibt dann im Ruhemodus). Sonst wie _bpm_live."""
        if self.mx_tempo_on and self.f is not None and self.f.bpm > 0 and self.beat_t is not None:
            ref = self.last_t if self.last_t is not None else time.time()
            if ref - self.beat_t < 4.0:
                return self.f.bpm
        return self._bpm_live()

    def _dmx_router(self):
        """Hauptausgang der DMX-Kette (dmx_usb.DmxRouter), None im Trockenlauf und ohne Ausgabe."""
        snd = self.output.senders.get(self.rig.target) if self.output is not None else None
        return snd if hasattr(snd, "set_via") else None

    def _power_for(self):
        """Steckdosen je Geraet der Verbindungsliste (homematic.yaml, ccu.power_for, eine id oder eine Liste):
        Name -> ids, Beschriftung, alle an. Das Panel macht damit den Namen in der roten Warnung antippbar."""
        if self.home is None:
            return {}
        out = {}
        for key in ("power_for", "power_watch"):           # power_watch: Geraete ohne Erreichbarkeit (DMX-Bus, Musikanlage)
            for name, devs in (self.home.ccu.get(key) or {}).items():
                ids = [devs] if isinstance(devs, str) else list(devs or [])
                ok = [i for i in ids if i != self.home.ccu.get("fog_power")      # Nebelmaschine nie von hier (Rauchmelder-Rueckfrage)
                      and (self.home.by_id.get(i) or {}).get("kind") == "switch"]
                if ok:
                    out[str(name)] = {"ids": ok, "label": ", ".join(self.home.by_id[i]["label"] for i in ok),
                                      "on": all(self.home.state.get(i, {}).get("on") for i in ok), "watch": key == "power_watch"}
        return out

    def _power_off(self):
        """Namen aus power_watch, deren Steckdose sicher aus ist (CCU hat geantwortet): oben rot "<Name> aus"."""
        out = []
        for name, p in self._power_for().items():
            st = [self.home.state.get(i, {}) for i in p["ids"]]
            if p["watch"] and any(s.get("ok") and s.get("on") is False for s in st):
                out.append(name)
        return out

    def _power_on(self, name):
        """Panel: Steckdosen eines Geraets aus power_for oder power_watch einschalten (nur einschalten)."""
        p = self._power_for().get(str(name))
        if p is None:
            raise ValueError("Fuer dieses Geraet ist keine Steckdose eingetragen")
        for i in p["ids"]:
            self.home.set(i, on=True)

    def _artin_status(self):
        """Art-Net-Eingang fuers Panel: None = aus."""
        if self.cfg["artnet_in"] < 0.5:
            return None
        ext = getattr(self.output, "ext", None) if self.output is not None else None
        if ext is None:
            return {"active": False, "src": "", "frames": 0, "error": "dry"}
        st = ext.status()
        st["active"] = bool(st["active"] and self.override != "blackout")
        return st

    def dmx_usb_status(self):
        """Zustand des USB-DMX-Adapters fuers Panel, None solange der Weg OLA-Pi gewaehlt ist."""
        if self.cfg["dmx_via"] < 0.5:
            return None
        r = self._dmx_router()
        if r is None:
            return {"ok": False, "port": "", "err": "dry", "detail": "", "channels": self.rig.dmx_channels(), "frames": 0}
        st = r.status()["usb"]
        if st is None:
            return {"ok": False, "port": "", "err": "wait", "detail": "", "channels": self.rig.dmx_channels(), "frames": 0}
        return st

    def _wled_targets(self):
        """Art-Net-Ziele der WLED-Lichter: alle Ziele ausser dem OLA-Pi und den Nanoleaf-Panels."""
        return [t for t in self.rig.targets() if t != self.rig.target and not str(t).startswith("nanoleaf:")]

    def _nano_targets(self):
        """Ziel der Nanoleaf-Panels (leer ohne nanoleaf.json)."""
        return [t for t in self.rig.targets() if str(t).startswith("nanoleaf:")]

    def _fine_active(self, sc, grp):
        """Knopf, dessen Feinregler gerade wirken (None: keiner, feste Szene, Center oder Static)."""
        if grp == "mv":
            btn = self.auto_move if sc is None else (sc.move if sc.name == "Eigene" else None)
        else:
            btn = None if self.color_freeze else ("Regenbogen" if self.auto_rainbow else None) if sc is None else sc.mixbtn
        return btn if self.fine.get(grp, btn) is not None else None

    def _fine_public(self, sc):
        out = {}
        for g in ("mv", "mx"):
            btn = self._fine_active(sc, g)
            out[g] = {"btn": btn, "vals": self.fine.get(g, btn)} if btn else None
        return out

    def _mx_public(self):
        """Kurzfassung der Mixxx-Vorhersage fuer das Panel."""
        m = self.mx
        if m is None:
            return None
        return {"connected": m["connected"], "deck": m["deck"], "title": m["title"], "plan": m["plan"], "want": m["want"],
                "next": m["next"][:2], "pos": m["pos"], "dur": m["dur"], "status": m["status"],
                "lvl": m.get("lvl"), "lvl_est": bool(m.get("lvl_est")), "genre": m.get("genre", ""), "style": self._style_key(),
                "use": bool(self.cfg["mixxx_light"] > 0.5), "bpm": m["bpm"],
                "left": round(max(0.0, (m["dur"] - m["pos"]) / (m.get("rate") or 1.0)), 1) if m.get("dur", 0) > 0 else None,
                "el": round(max(0.0, m["pos"]) / (m.get("rate") or 1.0), 1) if m.get("dur", 0) > 0 else None,   # gespielt (echte Zeit)
                "tot": round(m["dur"] / (m.get("rate") or 1.0), 1) if m.get("dur", 0) > 0 else None,           # Laenge beim aktuellen Pitch
                "bar": m.get("bar"), "sec": m.get("section", ""), "src": m.get("src", "mixxx")}

    def _laser_mode_text(self):
        lm = int(round(self.cfg["laser_mode"]))
        if lm == 0:
            return "Light-Butler steuert per DMX"
        key = "sound_mode" if lm == 1 else "auto_mode"
        fehlt = [f.name for f in self.lasers if f.type in ("eyes_21", "derby_4in1_15ch") and getattr(f, key) is None]
        name = "Sound-to-Light" if lm == 1 else "eigene Auto-Show"
        return name + (f"; {', '.join(fehlt)} dafuer per DMX vom Light-Butler" if fehlt else "")

    def _blitz_rate(self):
        """Blitze pro Sekunde; ohne Strobe-Erlaubnis hoechstens 3 (Schutz vor Lichtempfindlichkeit)."""
        return snap_blitz(self.blitz_hz, None if self.strobe else 3.0)

    def _fog_cool(self):
        for fx in self.rig.fixtures:
            if fx.type == "hazer":
                return float(fx.tdef.get("burst", {}).get("cooldown", 20.0))
        return 20.0

    def _aim_vals(self):
        t = self.aim_targets.get(self.aim) if self.aim else None
        if not t:
            return {}
        bars = {"all": [round(t["bars"][0]), round(t["bars"][1])]}
        for f in self.rig.group("bars"):
            if "tilt1" in f.map:
                p = t["bars_per"].get(f.name) or t["bars"]
                bars[f.name] = [round(p[0]), round(p[1])]
        return {"vega_u": round(t["vega"][0], 3), "vega_v": round(t["vega"][1], 3), "bars": bars}

    def _render_blackout(self):
        for fx in self.rig.fixtures:
            if not fx.locked:
                fx.blackout()
            elif fx.manual_ok:
                fx.manual_vals = None              # laufender Nebelschub endet sofort
        for fx in self.presets:
            fx.set("dimmer", 0)
        self.mo = {"hold": True}

    def _render_laser(self, now, dt):
        """Szene Laser: alle Lichter dunkel, nur die Laser von 21 Eyes und Derby laufen zur Musik.
        Sicherheit: Freigabe gilt pro Frame; ohne Musik (idle), bei Freeze, Blackout, anderer Szene oder
        Programmende sind alle Laserkanaele sofort 0. Der KTV-Laser bleibt gesperrt (Belegung unbekannt)."""
        for fx in self.rig.fixtures:
            if not fx.locked:
                fx.blackout()                                 # setzt auch laser_unlock zurueck
        for fx in self.presets:
            fx.set("dimmer", 0)
        for fx in self.rgb_amb:
            fx.set_color(0, 0, 0)
        self.mo = {"stop": True}
        if self.state == "idle":                              # keine Musik: Strahlen waeren starr -> aus
            for fx in self.lasers:
                for p in fx.laser_params:
                    fx.values[p] = 0
            return
        a, bl, c = self.arousal, self.bar_len, self.cfg
        lm = int(round(self.cfg["laser_mode"]))                # 0 = Pi steuert per DMX, 1 = Sound-to-Light intern, 2 = eigene Auto-Show
        sound = lm == 1
        brk = self.state == "break"
        drop = self.state == "drop"
        lvl = 255
        spd = self.sc.speed if self.sc is not None and self.sc.speed in LASER_SPEED else "mid"
        st = int(self.step * LASER_SPEED[spd][0])             # Musterwechsel: Low halb so oft, Hot doppelt so oft
        gate = self._laser_gate(now, spd)                       # Puls im Takt: an kurz nach dem Beat, dann aus
        mot = LASER_SPEED[spd][1]                               # Motoren und Farbwechsel langsamer / schneller
        for fx in self.lasers:
            fx.laser_unlock = True
            target = fx.sound_mode if lm == 1 else fx.auto_mode if lm == 2 else None
            if target is not None and fx.type in ("eyes_21", "derby_4in1_15ch"):
                for p in fx.laser_params:                      # internes Programm: der Laser steuert sich selbst
                    fx.values[p] = 0
                fx.values["mode"] = int(target)
                fx.mode_unlock = True
                continue
            if fx.type == "eyes_21":
                combos = [(1, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1), (1, 1, 1, 0), (0, 0, 1, 1), (1, 1, 0, 1), (1, 1, 1, 1)]
                c = combos[(st // bl) % len(combos)]
                if drop:
                    c = (1, 1, 1, 1)
                elif a > 0.6 and not brk:                     # hohe Energie: die beiden Rot-Laser wechseln im Takt
                    c = (c[0] * (st % 2 == 0), c[1] * (st % 2 == 1), c[2], c[3])
                for p, on in zip(("laser_red1", "laser_red2", "laser_green", "laser_blue"), c):
                    fx.values[p] = lvl if (on and gate) else 0
                fx.values["motor_speed"] = 20 if brk else min(255, int((40 + 160 * a) * mot))
                fx.values["mode"] = 0
            elif fx.type == "laser_ktv34":
                # Profi-Modus: Pi steuert ueber die Choreografie in laser_show.py; Sound-to-Light ueber Kanal 15 (251 bis 255)
                fx.values["power"] = 255 if gate else 0
                if sound:
                    fx.values.update(group=16, pattern=3, size=128, color=255, color_speed=120, effect=253)
                else:
                    per = 60.0 / (self.bpm if self.bpm > 0 else 120.0)
                    frac = clamp01((now - self.beat_t) / per) if self.beat_t is not None else 0.0
                    fx_set = (c["ktv_fx_a"], c["ktv_fx_b"], c["ktv_fx_drop_a"], c["ktv_fx_drop_b"], c["ktv_fx_break"])
                    fx.values.update(laser_show.ktv_scene((self.step + frac) * LASER_SPEED[spd][0], self.state, a, bl, [int(v) for v in fx_set]))
            elif fx.type == "laser_ktv":
                # 6CH-Modus: Ein, Effektgruppe, Effekt, Musterfarbe, Farbgeschwindigkeit, Sound-to-Light
                phrase = st // (2 * bl)
                grp = (st // (4 * bl)) % 7                                   # 6 Liniengruppen, dann die Animationsgruppe
                fx.values["power"] = 255 if gate else 0
                fx.values["group"] = 224 if grp == 6 else grp * 32 + 16
                fx.values["effect"] = 6 + ((phrase * 7) % 41) * 6 + 3   # alle 8 Beats ein anderer Effekt (41 Stueck)
                if drop or (a > 0.65 and not brk and phrase % 2 == 1):
                    fx.values["color"] = 255                            # bunt (Werkseinstellung)
                else:
                    fx.values["color"] = (10, 17, 27)[phrase % 3]       # rot, gruen, blau
                fx.values["color_speed"] = min(255, int((80 + 175 * a) * mot))
                # Kanal 6: ab 128 Sound-to-Light (das Geraet hoert mit), darunter Auto-Modus mit einstellbarer Geschwindigkeit
                fx.values["auto"] = 255 if sound else int(self.cfg["ktv_auto_speed"])
            elif fx.type == "derby_4in1_15ch":
                eff = (st // (4 * bl)) % 16                         # alle 16 Beats ein anderer der 16 Laser-Effekte
                fx.values["laser_effect"] = 16 + eff * 15 + 7
                which = (st // (2 * bl)) % 3                         # rot / gruen / beide
                fx.values["laser_red"] = lvl if gate and (which in (0, 2) or drop) else 0
                fx.values["laser_green"] = lvl if gate and (which in (1, 2) or drop) else 0
                fx.values["laser_red8"] = lvl if gate and ((a > 0.55 and not brk) or drop) else 0
                fx.values["laser_motor"] = min(255, 192 + int(60 * a * mot)) if not brk else 192
                fx.values["speed"] = min(255, int((60 + 150 * a) * mot))
                fx.values["mode"] = 0
        self.laser_on = True

    def _laser_gate(self, now, spd):
        """Laser-Puls im Takt (Szene Laser, Pi steuert): an ab dem Beat fuer laser_duty des Pulsabstands, dann aus.
        Low alle 2 Beats, Med jeder Beat, Hot jeder halbe Beat (nur mit Strobe-Erlaubnis). Ohne Strobe-Erlaubnis
        hoechstens 2 Pulse pro Sekunde (Sicherheitsregel wie beim Blitz)."""
        duty = self.cfg["laser_duty"] / 100.0
        if duty >= 0.999 or self.beat_t is None:
            return True
        per = 60.0 / (self.bpm if self.bpm > 0 else 120.0)
        beats = LASER_SPEED[spd][2] if (self.strobe or spd != "fast") else 1.0
        while not self.strobe and per * beats < 0.5:
            beats *= 2.0
        since = now - self.beat_t
        if beats >= 2.0 and self.step % int(beats) != 0:      # Low: nur jeder zweite Beat startet einen Puls
            since += per * (self.step % int(beats))
        if since > per * beats * 1.5:                           # lange kein Beat: aus statt Dauerlicht
            return False
        return (since % (per * beats)) < duty * per * beats

    def _render_aimlight(self):
        """Ziel (Bank, Tisch, Tuer, Bar): Vega und Docooler leuchten den Bereich weiss an (Docooler nur Weiss-LEDs)."""
        for fx, zi in self.bars:
            self.paint(fx, zi, 0, 0, 0, w=1.0)
            if "strobe" in fx.map:
                fx.set("strobe", 0)
        for fx in self.spot:
            fx.set("dimmer", 255 * self.master)
            fx.set("shutter", 255)
            fx.preset("colorwheel", "white")
            fx.preset("gobo", "open")
            fx.set("gobo_rot", 0)

    def _aim_isolate(self):
        """Ziel: alles ausser Vega und Docooler dunkel (auch Ambiente und Effektband)."""
        for fx in self.rig.fixtures:
            if fx.locked or fx.group in ("bars", "spot"):
                continue
            fx.blackout()
        for fx in self.presets:
            fx.set("dimmer", 0)
        for fx in self.rgb_amb:
            fx.set_color(0, 0, 0)

    def _render_allbright(self):
        """Sonnenbrille: alles in Weiss, 100 % Helligkeit, egal wie der General Dimmer steht."""
        self._full = True
        try:
            self._allbright_paint()
        finally:
            self._full = False

    def _allbright_paint(self):
        for fx, zi in self.bars + self.wash + self.barlight + self.nano:
            self.paint(fx, zi, 1, 1, 1, w=1.0)
            if "strobe" in fx.map:
                fx.set("strobe", 0)
        for fx in self.fxs:
            for zi in range(len(fx.zones())):
                self.paint(fx, zi, 1, 1, 1, w=1.0)
        for fx in self.uv:
            for zi in range(len(fx.zones())):
                self.paint(fx, zi, 0, 0, 0, uv=1.0)
        for fx in self.rgb_amb:
            fx.set_color(255, 255, 255)
            fx.set("dimmer", 255)
        for fx in self.spot:
            fx.set("dimmer", 255)
            fx.set("shutter", 255)
            fx.preset("colorwheel", "white")
            fx.preset("gobo", "open")
        for fx in self.presets:
            fx.set("preset", 35)                 # Solid weiss, nur hier bewusst
            fx.set("dimmer", 255)
        self.mo = {"u": 0.5, "v": 0.5, "rate": 30.0, "fan_amp": 0.0, "fan_phase": 0.0,
                   "sway_amp": 0.0, "bar_rate": 120.0}

    def _render_gap(self):
        """Die Stille vor dem Drop: alles dunkel."""
        for fx in self.rig.fixtures:
            if not fx.locked:
                fx.blackout()

    def _paint_all(self, r, g, b, uv_level, strobe0=True):
        for fx in self.zone_fx:
            for zi in range(len(fx.zones())):
                if "uv1" in fx.map:
                    self.paint(fx, zi, 0, 0, 0, uv=uv_level)
                else:
                    self.paint(fx, zi, r, g, b)
            if strobe0 and "strobe" in fx.map:
                fx.set("strobe", 0)
        for fx in self.rgb_amb:
            fx.set_color(*[255 * clamp01(c) * self.master for c in (r, g, b)])
            fx.set("dimmer", 255)

    def _render_manual_build(self, now, dt):
        """WOW!: Strobo im BPM-Raster. Je 2 Beats doppelt so schnell (1/4, 1/8, 1/16, 1/32 Noten) und heller,
        zuletzt dauerhaft volles Weiss. Zu schnelle Stufen werden bei hohem Tempo bzw. ohne Strobe-Erlaubnis
        uebersprungen (max. 12 bzw. 3 Blitze pro Sekunde)."""
        per = self.wow_period
        bt = (now - self.build_t0) / per                       # Beats seit dem Start (vor dem Start < 0)
        prog = clamp01(bt / self.wow_beats)
        self.build_p = prog
        self.bphase += dt * (0.05 + 1.5 * prog)                # Bewegungstempo waechst mit
        cap = 12.0 if self.strobe else 3.0
        base = (1, 2, 4, 8)[max(0, min(3, int(bt // 2)))] if bt >= 0 else 1
        mult = base
        while mult > 1 and per / mult < 1.0 / cap:
            mult //= 2
        solid = bt >= self.wow_beats or (bt >= self.wow_beats - 2 and mult < base)   # Endstufe: Dauerlicht
        lvl = 0.55 + 0.45 * prog
        if bt < 0:
            self._render_burst(False)                          # bis zum naechsten Beat dunkel
        elif solid:
            self._render_burst(True, 1.0, steady=True)
        else:
            cyc = per / mult
            pos = (bt * mult) % 1.0
            on = pos * cyc < max(0.03, min(0.07, 0.5 * cyc))
            self._render_burst(on, lvl, hz=mult / per)
        for fx in self.spot:
            fx.set("shutter", 255)
            fx.preset("gobo", "open")
        for fx in self.presets:
            roles = self.eb_roles(fx)
            if self.strobe and self.cfg["blitz_band_sync"] > 0.5:
                pid = fx.extra.get("preset_blitz", 35)                     # synchron: Solid weiss, die Helligkeit takten wir selbst
            else:
                pid = fx.extra.get("preset_drop") if self.strobe else (roles.get("party") or [0])[0]
            if pid:
                fx.set("preset", pid)
        ph = 2 * math.pi * self.bphase
        self.mo = {"u": 0.5 + 0.45 * math.sin(ph), "v": 0.5 + 0.3 * math.sin(1.3 * ph + 1.0),
                   "rate": 10.0 + 70.0 * prog, "fan_amp": 6.0 + 38.0 * prog, "fan_phase": 2.0 * ph,
                   "sway_amp": 0.0, "bar_rate": 255.0 if prog > 0.6 else 120.0}

    def _render_build(self, now, dt):
        """Aufbau: alle Lichter gemeinsam, Pulse werden schneller und heller (bis 3 Hz, mit --strobe bis 7 Hz)."""
        p = self.build_prog
        hz = min(7.0 if self.strobe else 3.0, 1.0 + 4.0 * p)
        on = ((now * hz) % 1.0) < 0.5
        b = self.smooth("build", (0.30 + 0.70 * p) if on else 0.0, self.last_dt, release=0.05)
        r, g, bl = hsv(self.hue, 1.0, b)
        self._paint_all(r, g, bl, b)
        for fx in self.spot:
            fx.set("dimmer", 255 * (clamp01(b) ** self.gamma) * self.master)
            fx.set("shutter", 255)
            fx.preset("colorwheel", self.wheel_name(self.hue))
        if self.cfg["vega_live"] > 0.5:
            self._vega_beam_auto(now)

    def _render_dropfx(self, now, dt, t):
        """Drop: weisser Einschlag (0,6 s), dann volle Farbe und Helligkeit fuer die ganze Drop-Dauer (Einstellung
        "Drop: Dauer"), im Takt leicht pulsierend, in der letzten Sekunde weich ausgeblendet."""
        total = max(0.8, self.cfg["drop_len_s"])
        fl = clamp01(1.0 - t / 0.6)
        fade = clamp01((total - t) / min(1.0, 0.3 * total))          # Ausblenden am Ende
        lvl = (0.9 + 0.1 * self.beat_env) * fade                       # sehr hell, im Takt leicht lebendig
        r, g, bl = hsv(self.hue, 1.0, 1.0)
        r, g, bl = r * lvl, g * lvl, bl * lvl
        for fx in self.zone_fx:
            for zi in range(len(fx.zones())):
                if "uv1" in fx.map:
                    self.paint(fx, zi, 0, 0, 0, uv=lvl)
                else:
                    self.paint(fx, zi, max(r, fl), max(g, fl), max(bl, fl), w=max(fl, 0.0),
                               uv=0.8 * lvl if t < 0.5 else 0.0)
            if "strobe" in fx.map:
                fx.set("strobe", 0)
        for fx in self.rgb_amb:
            fx.set_color(*[255 * clamp01(c) * self.master for c in (max(r, fl), max(g, fl), max(bl, fl))])
            fx.set("dimmer", 255)
        for fx in self.spot:
            fx.set("dimmer", 255 * self.master * max(lvl, fl))
            fx.set("shutter", 255)
            fx.preset("colorwheel", "white" if fl > 0.3 else self.wheel_name(self.hue))
        if self.cfg["vega_live"] > 0.5:
            self._vega_beam_auto(now)

    PARTY_LIGHTS = ("Art-Net-Gateway", "DMX-USB", "Effektband", "Theke", "Couchtisch", "Nanoleaf")

    def _home_auto(self, now):
        """Wohnzimmerlicht: laenger Stille -> hochdimmen (Partylichter dunkel statt Atmen); Musik und mindestens ein
        Partylicht erreichbar -> aus. Geschaltet wird nur beim Wechsel, Handbetrieb dazwischen bleibt."""
        c = self.cfg
        dev = self.home.ccu.get("room_light")
        if c["home_auto"] < 0.5 or dev not in self.home.by_id:
            self.home_lit = False
            return
        dt = 0.0 if self.home_tick_t is None else max(0.0, min(1.0, now - self.home_tick_t))
        self.home_tick_t = now
        if self.state == "idle":
            self.home_music_t = None
            if self.home_quiet_t is None:
                self.home_quiet_t = now
            # an nur nach echter Musik (Fehlerbericht 12.11.2026: mit richtiger Stille-Schwelle ging das Licht bei jedem
            # Geraeusch am Eingang an und aus)
            party = self.home_party_s >= c["home_party_min"] * 60.0
            if now - self.home_quiet_t >= c["home_idle_s"] and self.home_last != "on" and party:
                if self._home_send(now, dev, level=c["home_idle_level"] / 100.0):
                    self.home_last, self.home_lit = "on", True
                    self.home_party_s = 0.0
        else:
            self.home_quiet_t = None
            self.home_lit = False
            self.home_party_s += dt
            if self.home_music_t is None:
                self.home_music_t = now
            if (now - self.home_music_t >= c["home_music_s"] and self.home_last != "off"
                    and any(self.reach.get(n) for n in self.PARTY_LIGHTS)):
                if self._home_send(now, dev, on=False):
                    self.home_last = "off"

    HOME_GAP_S = 30.0                                     # Automatik: hoechstens ein Befehl alle 30 s (Duty Cycle der CCU)

    def _home_send(self, now, dev, on=None, level=None):
        """Ein Befehl der Automatik. Steht das Licht schon so (laut CCU), wird nichts gesendet. True = erledigt."""
        if self.home_send_t is not None and now - self.home_send_t < self.HOME_GAP_S:
            return False                                  # spaeter nochmal versuchen
        st = self.home.state.get(dev, {})
        want = level if level is not None else 0.0
        if st.get("level") is not None and abs(st["level"] - want) < 0.01:
            return True
        self.home_send_t = now
        try:
            self.home.set(dev, on=on, level=level, ramp_s=self.cfg["home_ramp_s"])   # langsam ein- und ausdimmen (12.11.2026)
        except ValueError:                                # Grenze fuer Schaltbefehle erreicht
            return False
        return True

    def _render_idle(self, now, dt):
        """Keine Musik: sehr dezentes, langsames Atmen (Docooler, Washes, Barlicht, Ambiente), Rest dunkel,
        auch die Nanoleaf-Panels."""
        if self.home_lit:                                 # Wohnzimmerlicht ist an: Partylichter dunkel statt Atmen
            for fx, zi in self.bars + self.wash + self.barlight + self.nano:
                self.paint(fx, zi, 0, 0, 0)
            for fx in self.uv + self.fxs:
                fx.blackout()
            for fx in self.spot:
                fx.set("dimmer", 0)
            for fx in self.rgb_amb:
                fx.set_color(0, 0, 0)
            return
        breath = 0.5 + 0.5 * math.sin(now * 0.25)
        hue = (now * 0.01) % 1.0
        for fx, zi in self.bars + self.wash + self.barlight:
            r, g, b = hsv(hue, 1.0, 0.06 + 0.1 * breath)
            self.paint(fx, zi, r, g, b)
        for fx, zi in self.nano:                          # Nanoleaf bei Stille ganz dunkel
            self.paint(fx, zi, 0, 0, 0)
        for fx in self.uv + self.fxs:
            fx.blackout()
        for fx in self.spot:
            fx.set("dimmer", 0)
        for fx in self.rgb_amb:                           # Ambiente: ruhig in der Grundhelligkeit, Farbe wandert langsam
            r, g, b = hsv(hue, 0.85, max(0.12, self.cfg["amb_idle"]) * (0.9 + 0.1 * breath))
            fx.set_color(*[255 * c * self.master for c in (r, g, b)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="fixtures.yaml")
    ap.add_argument("--target", help="Ziel-IP des OLA-Pi ueberschreiben")
    ap.add_argument("--dmx-port", help="Geraetedatei des USB-DMX-Adapters (z. B. /dev/ttyUSB0), sonst automatisch suchen")
    ap.add_argument("--device", type=parse_device,
                    help="Audiogeraet: Nummer oder Namensteil, z. B. USB (siehe phase1_audio.py --list)")
    ap.add_argument("--rate", type=int, default=44100)
    ap.add_argument("--silence-db", type=float, default=-60.0)
    ap.add_argument("--simulate", action="store_true", help="kuenstliche Musik statt Audio")
    ap.add_argument("--dry-run", action="store_true", help="kein Netzwerk, nur Ausgabe")
    ap.add_argument("--master", type=float, default=1.0)
    ap.add_argument("--strobe", action="store_true", help="Strobe-Bursts erlauben")
    ap.add_argument("--gamma", type=float, default=2.2, help="Helligkeitskurve (hoeher = mehr Kontrast)")
    ap.add_argument("--base", type=float, default=0.10, help="Grundhelligkeit zwischen den Schlaegen 0..1")
    ap.add_argument("--attack", type=float, default=0.01, help="Anstiegszeit in s")
    ap.add_argument("--release", type=float, default=0.15, help="Abfallzeit in s (hoeher = ruhiger)")
    ap.add_argument("--no-white", action="store_true", help="keine weissen Akzent-Blitze")
    ap.add_argument("--flash-every", type=int, default=16,
                    help="weisser Blitz alle N Beats (0 = aus, Standard 16)")
    ap.add_argument("--strobe-hz", type=float, default=6.0, help="Blitzrate im Strobe-Burst (2..12)")
    ap.add_argument("--move", choices=["all", "spot", "bars", "off"], default="all",
                    help="Bewegung: Vega-Spot und/oder Docooler-Tilt (Standard: all)")
    ap.add_argument("--bar-sway", type=float, default=1.0,
                    help="Schwenk der Docooler-Balken passend zur Vega-Position (0 = aus)")
    ap.add_argument("--bar-period", type=float, default=4.0,
                    help="Beats pro Faecher-Zyklus der Docooler (kleiner = schneller, Standard 4)")
    ap.add_argument("--vega-speed", type=float, default=1.0,
                    help="Faktor fuer die Vega-Geschwindigkeit (z. B. 1.5 = schneller)")
    ap.add_argument("--bar-style", choices=["snap", "sine"], default="snap",
                    help="Docooler: snap = Spruenge im Takt (Standard), sine = weiche Welle")
    ap.add_argument("--bar-every", type=int, default=1,
                    help="snap-Stil: Beats pro Sprung (2 = langsamer, wenn die Motoren nicht mitkommen)")
    ap.add_argument("--colors", help="feste Farbliste, z. B. blau,cyan,violett (rot, orange, gelb, gruen, "
                                     "tuerkis, cyan, blau, violett, magenta, pink); sonst nach Stimmung")
    ap.add_argument("--energy-bias", type=float, default=0.0,
                    help="-0.3..0.3: negativ = insgesamt ruhiger (weniger Blinken), positiv = lebhafter")
    ap.add_argument("--web", type=int, default=0, metavar="PORT",
                    help="Web-Panel fuer iPad/Handy auf diesem Port starten (z. B. 8080), 0 = aus")
    ap.add_argument("--aim-file", default="aim.json", help="gespeicherte Zielpositionen (Bank, Tisch, Tuer, Bar)")
    ap.add_argument("--no-midi", action="store_true", help="MIDI-Controller (APC mini mk2) nicht benutzen")
    ap.add_argument("--midi-net-port", type=int, default=9021,
                    help="UDP-Port fuer den APC am Mac (ueber die Mixxx-Bruecke), 0 = aus")
    ap.add_argument("--midi-map", default="midimap.json", help="Belegung des MIDI-Controllers (optional)")
    ap.add_argument("--lumi-net-port", type=int, default=9023, help="UDP-Port fuer den ROLI LUMI Keys am Mac, 0 = aus")
    ap.add_argument("--lumi-map", default="lumimap.json", help="Belegung des ROLI LUMI Keys (optional)")
    ap.add_argument("--audio-file", default="audio.json", help="gespeicherte Eingangswahl (Geraet, Gain, Kanal) aus dem Panel")
    ap.add_argument("--mixxx-port", type=int, default=9020, help="UDP-Port, auf dem die Mixxx-Bruecke (Mac) sendet")
    ap.add_argument("--no-mixxx", action="store_true", help="Empfaenger fuer die Mixxx-Bruecke nicht starten")
    ap.add_argument("--songrec-cmd", default="/snap/bin/songrec", help="Aufruf von SongRec fuer die Titelerkennung (einschalten im Panel)")
    ap.add_argument("--settings", default="settings.json", help="gespeicherte Einstellungen der Auto-Erkennung (aus dem Panel)")
    ap.add_argument("--scenes-file", default="scenes.json", help="eigene Szenenliste (aus dem Panel bearbeitbar)")
    ap.add_argument("--mood-log", help="Stimmungs-Merkmale jede Sekunde in eine CSV-Datei schreiben")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    rig = Rig(a.config)
    if a.target:
        rig.target = a.target
    rig.dmx_port = a.dmx_port
    problems = rig.check()
    if problems:
        sys.exit("YAML-Probleme: " + "; ".join(problems))
    if not a.simulate and a.device is None:            # neue Anlage (Pi- und Windows-Paket): im Panel gewaehlter Eingang,
        print("Hinweis: kein --device, Audio-Eingang aus dem Panel oder Standard-Eingang des Rechners.")   # sonst Standard

    colors = None
    if a.colors:
        try:
            colors = [COLOR_NAMES[c.strip().lower()] for c in a.colors.split(",") if c.strip()]
        except KeyError as e:
            sys.exit(f"Unbekannte Farbe {e}. Erlaubt: {', '.join(COLOR_NAMES)}")
    src = Simulator() if a.simulate else Analyzer(a.device, a.rate, silence_db=a.silence_db, audio_file=a.audio_file)
    link = None
    if not a.no_mixxx:
        from mixxx_link import MixxxLink
        link = MixxxLink(a.mixxx_port)
        if link.start():
            print(f"Mixxx-Empfaenger lauscht auf UDP-Port {a.mixxx_port}")
        else:
            print(f"Hinweis: Mixxx-Empfaenger nicht gestartet ({link.error})")
            link = None
    show = Show(rig, src, master=max(0.0, min(1.0, a.master)), strobe=a.strobe,
                gamma=a.gamma, base=a.base, attack=a.attack, release=a.release,
                white=not a.no_white, strobe_hz=a.strobe_hz, flash_every=a.flash_every,
                move=a.move, bar_sway=a.bar_sway, bar_period=a.bar_period,
                vega_speed=a.vega_speed, bar_style=a.bar_style, bar_every=a.bar_every,
                colors=colors, mood_log=a.mood_log, energy_bias=max(-0.3, min(0.3, a.energy_bias)), aim_file=a.aim_file, settings_file=a.settings, scenes_file=a.scenes_file, mixxx=link)
    from dmx import make_sender as _mk
    out = Output(rig, lambda ip: _mk(rig, ip, a.dry_run))
    show.output = out
    from wled_matrix import Matrix                              # Pixel-Matrix (Einstellung pm_on, Standard aus)
    show.matrix = Matrix(os.path.join(os.path.dirname(os.path.abspath(a.settings)), "matrix.json") if a.settings else None,
                         dry=a.dry_run)
    if not a.simulate:                                          # Titelerkennung: im Panel einschalten, sonst ruht sie
        from songrec_id import TitleFinder
        show.titles = TitleFinder(a.rate, cmd=a.songrec_cmd)
        from recorder import Recorder                          # Debug-Aufnahme bei Signal (12.11.2026), Schalter im Panel, Start: aus
        show.recorder = Recorder(os.path.join(os.path.dirname(os.path.abspath(__file__)), "aufnahmen"), a.rate,
                                 threshold_db=lambda: show.cfg["silence_db"], log=print)

        src.tap = show.titles.feed
        src.raw_tap = show.recorder.feed                       # direkt an der Schnittstelle, alle Kanaele (Stereo)
    if not a.dry_run:                                           # Art-Net-Eingang, wirkt nur mit Einstellung artnet_in
        from artnet_in import ArtNetIn
        out.ext = ArtNetIn(rig.universe)
        if not out.ext.start():
            print(f"Hinweis: Art-Net-Eingang nicht moeglich ({out.ext.error})")
    show.allow_poweroff = (not a.dry_run) and sys.platform.startswith("linux")   # nie den Mac im Simulator
    import safety
    show.safety_open = safety.is_open(os.path.dirname(os.path.abspath(show.cfg.path or "settings.json")), simulate=a.simulate)
    if not a.dry_run:                                           # HomeMatic-CCU (Bereich "Haus"), nur im echten Betrieb
        try:
            from homematic import Home, default_path
            show.home = Home(default_path())                    # ohne homematic.yaml leer, einrichten im Panel (27.11.2026)
            show.home.start()
        except Exception as e:                                  # noqa: BLE001
            print(f"Hinweis: HomeMatic nicht verfuegbar ({e})")
    if not a.dry_run:                                           # Ableton Link nur im echten Betrieb (eingeschaltet im Panel)
        from ableton_link import LinkOut
        show.link_out = LinkOut()
        if not show.link_out.available:
            print(f"Hinweis: Ableton Link nicht verfuegbar ({show.link_out.error})")
    print(f"Show startet ({'Simulator' if a.simulate else 'Audio'}, "
          f"{'Trockenlauf' if a.dry_run else 'Art-Net an ' + ', '.join(rig.targets())}, "
          f"Master {show.master:.2f}, Strobe {'an' if a.strobe else 'aus'}). Strg+C beendet.")
    if a.move in ("all", "spot"):
        for fx in show.spot:
            if fx.move16 and not fx.extra.get("limits_verified", False):
                print(f"HINWEIS: {fx.name} bleibt an der Parkposition, solange 'limits_verified' in der "
                      "fixtures.yaml nicht auf true steht (erst phase2_test.py --move-test pruefen).")
    def _term(signum, frame):            # systemd sendet SIGTERM: sauber beenden (Blackout)
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _term)
    for attempt in range(20):             # beim Booten ist die USB-Karte manchmal noch nicht bereit
        try:
            src.start()
            break
        except Exception as e:            # noqa: BLE001
            print(f"Audio nicht bereit ({e}); neuer Versuch in 3 s ({attempt + 1}/20)", flush=True)
            time.sleep(3)
    else:
        sys.exit("Audiogeraet nicht verfuegbar.")
    out.start()
    mc = None
    if not a.no_midi:
        try:
            from midi_ctl import MidiController
            import mido  # noqa: F401
            mc = MidiController(show, a.midi_map)
            if a.midi_net_port:                                 # APC am Mac: Tasten und LEDs ueber das Netzwerk
                from midi_net import NetMidi
                mc.net = NetMidi(a.midi_net_port)
                if not mc.net.start():
                    print(f"Hinweis: APC ueber den Mac nicht moeglich ({mc.net.error})")
                    mc.net = None
            show.midi = mc
            mc.start()
            print("MIDI-Controller: warte auf APC mini mk2 (USB am Pi" + (f" oder am Mac, UDP {a.midi_net_port})" if mc.net else ")"))
            from lumi_ctl import LumiController
            lc = LumiController(show, a.lumi_map)
            if a.lumi_net_port:                                 # Lumi am Mac: Noten ueber das Netzwerk
                from midi_net import NetMidi
                lc.net = NetMidi(a.lumi_net_port)
                if not lc.net.start():
                    print(f"Hinweis: Lumi ueber den Mac nicht moeglich ({lc.net.error})")
                    lc.net = None
            show.lumi = lc
            lc.start()
        except ImportError:
            print("Hinweis: MIDI-Controller nicht benutzt (mido fehlt: sudo apt install python3-mido python3-rtmidi)")
    if not a.dry_run:                                          # WLAN-Schalter: Waechter schaltet es wieder ein, wenn das Kabel fehlt
        import wlan
        wlan.manager().want_off = lambda: show.cfg["wlan_trennen"] > 0.5
        wlan.manager().start_watch()
    if a.web:
        import webpanel
        webpanel.start(show, a.web)
    last_dbg = 0.0
    try:
        nxt = time.perf_counter()
        while True:
            now = time.time()
            t0 = time.perf_counter()
            show.update(now)
            show.frames.note(t0, time.perf_counter())
            if a.debug and now - last_dbg > 0.5:
                last_dbg = now
                print("\r" + show.status, end="", flush=True)
            nxt += 0.025
            time.sleep(max(0.0, nxt - time.perf_counter()))
            if show.restart_requested or show.quit_requested:
                break
    except KeyboardInterrupt:
        print("\nEnde, Blackout.")
    finally:
        if mc is not None:
            mc.stop()
        src.stop()
        out.stop()
        show.close()
    if show.quit_requested:                                     # Knopf im Panel (Mac/Windows): Ende mit Code 0, kein Neustart
        print("Beendet aus dem Panel, Blackout.", flush=True)
    if show.restart_requested:                                  # Neustart ohne den Dienst zu beenden (Aenderungen an den Fixtures)
        print("Neustart ...", flush=True)
        restart_self()


def restart_cmd(argv=None, exe=None):
    """Befehl fuer den Neustart: dasselbe Python mit demselben Skript und denselben Optionen."""
    argv = sys.argv if argv is None else argv
    exe = exe or sys.executable
    return [exe, os.path.abspath(argv[0])] + list(argv[1:])


RESTART_CODE = 3                                    # Windows mit start.ps1: "bitte neu starten"


def restart_self(platform=None, execv=None, popen=None, exit_=None, env=None):
    """Am Pi (Linux) und Mac ersetzt os.execv den Prozess (gleiche Prozessnummer, systemd merkt nichts).
    Windows hat kein echtes execv (es zerlegt Pfade mit Leerzeichen falsch). Laeuft der Light-Butler aus start.ps1
    (Installation, LB_RESTART_EXIT gesetzt), endet er mit Code 3 und start.ps1 startet ihn neu, mit demselben Log.
    Sonst einen neuen Prozess starten und diesen beenden; Port und Geraete sind dann schon frei (show.close, out.stop)."""
    cmd = restart_cmd()
    if (platform or sys.platform) == "win32":
        if (os.environ if env is None else env).get("LB_RESTART_EXIT"):
            (exit_ or sys.exit)(RESTART_CODE)
            return
        (popen or subprocess.Popen)(cmd, close_fds=True)
        (exit_ or sys.exit)(0)
    else:
        (execv or os.execv)(cmd[0], cmd)


if __name__ == "__main__":
    main()
