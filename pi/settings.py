#!/usr/bin/env python3
"""
settings.py - einstellbare Parameter der automatischen Musik-Erkennung.

Alle Werte stehen hier mit Standardwert, Bereich und Beschreibung. Die Show (show.py) und die
Audio-Analyse (audio.py) lesen sie live aus `cfg["name"]`. Im Web-Panel (Bereich "Einstellungen")
koennen sie angesehen und geaendert werden. Geaenderte Werte werden in settings.json gespeichert
und beim naechsten Start wieder geladen. Nicht geaenderte Werte bleiben auf dem Standard.
"""
import json
import os
import threading
from collections import namedtuple

P = namedtuple("P", "group key label desc default lo hi step unit")

G_AUDIO = "Eingang und Stille"
G_KICK = "Kick und Beat"
G_ENERGY = "Stimmung: Energie"
G_COLOR = "Stimmung: Farbe und Tonart"
G_PHASE = "Phasen: Break, Build, Drop"
G_TIER = "Intensitaetsstufen"
G_FLASH = "Weisse Blitze und Strobo"
G_AMB = "Ambiente"
G_METER = "Takt"
G_MIXXX = "Mixxx-Vorhersage"
G_LASER = "Laser"
G_OUT = "Ausgabe"
G_PANEL = "Panel"
G_HOME = "Haus"
G_SONG = "Titelerkennung"
G_SCAUTO = "Szenen-Automatik"
G_FOG = "Nebel"
G_VEGA = "Moving-Head-Strahl"

DEFS = [
    # ---- Eingang und Stille -----------------------------------------------------------------
    P(G_AUDIO, "silence_db", "Stille-Schwelle", "Unter diesem Pegel gilt das Signal als Stille. Niedriger = empfindlicher.",
      -60.0, -90.0, -30.0, 1.0, "dB"),
    P(G_AUDIO, "silence_hold_s", "Stille erst nach", "So lange muss es still sein, bis 'keine Musik' erkannt wird und das Licht in den Ruhemodus geht.",
      3.0, 0.5, 10.0, 0.5, "s"),
    P(G_AUDIO, "rel_silence_on", "Stille auch bei Rauschen erkennen", "An: Auch wenn der Eingang rauscht oder brummt (lauter als die Stille-Schwelle), gilt es als Stille, sobald weit unter dem Musikpegel und ohne Kick und Beat. Aus: nur die Stille-Schwelle zaehlt.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_AUDIO, "rel_silence_db", "Stille (relativ): Abstand zur Musik", "So viel leiser als die zuletzt gespielte Musik muss das Signal sein, damit es als Stille gilt.",
      25.0, 10.0, 50.0, 1.0, "dB"),
    P(G_AUDIO, "rel_silence_s", "Stille (relativ): ohne Kick und Beat seit", "So lange darf es keinen Kick und Beat gegeben haben, bevor die relative Stille greift.",
      6.0, 2.0, 20.0, 0.5, "s"),
    P(G_AUDIO, "rel_wake_db", "Stille (relativ): Musik erkannt ab", "So viel lauter als der Rauschpegel muss das Signal werden (oder es kommen Kicks), damit wieder Musik gilt.",
      12.0, 6.0, 30.0, 1.0, "dB"),
    # ---- Kick und Beat ----------------------------------------------------------------------
    P(G_KICK, "kick_bass_min", "Kick: Mindest-Bass", "Wie stark der Bass mindestens sein muss, damit ein Schlag als Kick zaehlt. Hoeher = weniger Kicks.",
      0.45, 0.10, 0.90, 0.01, ""),
    P(G_KICK, "kick_ratio", "Kick: Schaerfe", "Der Bass muss so oft ueber dem Durchschnitt der letzten halben Sekunde liegen. Hoeher = nur harte Kicks.",
      1.5, 1.1, 3.0, 0.05, "x"),
    P(G_KICK, "hat_amount", "Hi-Hat-Funkeln", "Hi-Hat, Shaker, Clap und Snare lassen Derby, 21 Eyes und den Moving Head kurz aufleuchten (weicher Puls, hoechstens 60 % heller, klingt in 0,1 s ab). Ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde, mit ihr hoechstens 8. Nur in AUTO. Das Barlicht (Arbeitslicht) pulsiert nie. 0 = aus.",
      0.5, 0.0, 1.0, 0.05, ""),
    P(G_KICK, "hat_derby", "Hi-Hat-Funkeln: Derby", "Derby pulsiert auf Hi-Hat und Clap.", 1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_KICK, "hat_eyes", "Hi-Hat-Funkeln: 21 Eyes", "21 Eyes Party Light pulsiert auf Hi-Hat und Clap.", 1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_KICK, "hat_vega", "Hi-Hat-Funkeln: Moving Head", "Der Moving Head pulsiert auf Hi-Hat und Clap, zwischen seinen Treffern auf den Beat.", 1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_KICK, "hat_nano", "Hi-Hat-Funkeln: Nanoleaf", "Bei jedem Schlag leuchtet ein zufaelliges Nanoleaf-Panel kurz voll auf (ueber dem laufenden Effekt).", 0.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_KICK, "hat_share", "Hi-Hat-Funkeln: Anteil", "Wie oft das Funkeln kommt. Zu Beginn jeder Phrase (8 Takte) wird neu gewuerfelt, ob es in dieser Phrase laeuft: 100 % = immer, 30 % = ungefaehr jede dritte Phrase.",
      100.0, 0.0, 100.0, 5.0, "%"),
    P(G_KICK, "hat_main", "Hi-Hat-Funkeln: nur im Hauptteil", "Das Funkeln kommt nur im vollen Teil des Liedes (laut Analyse aus Mixxx, Abschnitt Hauptteil), nicht in Intro, Strophe, Break und Outro. Ohne Analyse: ab der Stufe Party.",
      0.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_KICK, "hat_eb_duck", "Hi-Hat-Funkeln: Effektband zuruecknehmen", "Solange es funkelt, wird das Effektband um so viel dunkler, damit es das Funkeln nicht ueberstrahlt. Beim Drop bleibt es voll. 0 = aus.",
      0.0, 0.0, 90.0, 5.0, "%"),
    P(G_KICK, "hat_ratio", "Hi-Hat: Schaerfe", "Die Hoehen muessen so oft ueber ihrem Durchschnitt der letzten Viertelsekunde liegen, damit ein Schlag zaehlt. Hoeher = nur deutliche Schlaege, niedriger = auch leise Hi-Hats.",
      1.6, 1.1, 3.0, 0.05, "x"),
    P(G_KICK, "hat_min", "Hi-Hat: Mindestpegel", "So stark muessen die Hoehen mindestens sein (0..1, im Verhaeltnis zum lautesten Moment der letzten Sekunden).",
      0.25, 0.05, 0.90, 0.01, ""),
    P(G_KICK, "kick_gap_s", "Kick: Mindestabstand", "Kleinster Abstand zwischen zwei erkannten Kicks.",
      0.28, 0.10, 0.60, 0.01, "s"),
    P(G_KICK, "kick_flash_gap", "Kick-Aufhellung: Mindestabstand", "Kleinster Abstand zwischen zwei Aufhellungen auf den Kick (begrenzt das Flackern).",
      0.30, 0.10, 1.00, 0.05, "s"),
    P(G_KICK, "kick_env_decay", "Nachleuchten nach Kick", "Wie lange die Kick-Aufhellung abklingt. Kleiner = knackiger.",
      0.22, 0.05, 1.00, 0.01, "s"),
    P(G_KICK, "auto_solo", "Geraete der Reihe nach", "Wie im Show-Assistenten: In AUTO spielt immer nur eine Gruppe (Moving Head, Nanoleaf, Spider, Eyes/Derby, Washes), der Wechsel kommt auf dem Beat, das Ambiente bleibt. Bei Drop und Stille arbeiten alle wie immer. 0 = aus.",
      0.0, 0, 1, 1, ""),
    P(G_KICK, "auto_solo_bars", "Geraete der Reihe nach: Takte", "So viele Takte bleibt eine Gruppe dran, bevor die naechste kommt.",
      2.0, 1, 16, 1, "Takte"),
    P(G_KICK, "beat_pulse", "Beat-Puls: Licht", "Spider, Washes, UV, Derby, 21 Eyes, Moving Head und Nanoleaf pulsieren im Takt des Beat-Lamperls: auf dem Beat volle Helligkeit, dazwischen um so viel dunkler. Nur in AUTO, Ambiente nie. Ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde (bei schnellen Liedern jeder zweite Beat). 0 = aus.",
      0.0, 0.0, 70.0, 5.0, "%"),
    P(G_KICK, "beat_pulse_eb", "Beat-Puls: Effektband", "Das Effektband pulsiert im Takt: auf dem Beat volle Helligkeit, dazwischen um so viel dunkler. Gleiche Grenzen wie beim Licht. 0 = aus.",
      0.0, 0.0, 70.0, 5.0, "%"),
    P(G_KICK, "beat_env_decay", "Nachleuchten nach Beat", "Wie lange die Beat-Aufhellung abklingt.",
      0.25, 0.05, 1.00, 0.01, "s"),
    # ---- Stimmung: Energie ------------------------------------------------------------------
    P(G_ENERGY, "arousal_tc", "Energie: Traegheit", "Wie langsam sich die erkannte Energie anpasst. Kleiner = reagiert schneller auf Wechsel.",
      8.0, 2.0, 30.0, 1.0, "s"),
    P(G_ENERGY, "w_bpm", "Gewicht Tempo", "Wie stark das Tempo (BPM) in die Energie eingeht. Alle Gewichte werden automatisch normiert.",
      0.30, 0.0, 1.0, 0.05, ""),
    P(G_ENERGY, "w_level", "Gewicht Lautstaerke", "Wie stark die Lautstaerke in die Energie eingeht.",
      0.25, 0.0, 1.0, 0.05, ""),
    P(G_ENERGY, "w_kick", "Gewicht Kick-Dichte", "Wie stark die Anzahl der Kicks pro Sekunde in die Energie eingeht.",
      0.20, 0.0, 1.0, 0.05, ""),
    P(G_ENERGY, "w_rise", "Gewicht Pegelanstieg", "Wie stark ein ansteigender Pegel in die Energie eingeht.",
      0.15, 0.0, 1.0, 0.05, ""),
    P(G_ENERGY, "w_high", "Gewicht Hoehen", "Wie stark die Hoehenanteile (Hihats, Becken) in die Energie eingehen.",
      0.10, 0.0, 1.0, 0.05, ""),
    P(G_ENERGY, "bpm_lo", "Tempo: ab hier lebhaft", "Unter diesem Tempo zaehlt das Tempo als ruhig.",
      70.0, 40.0, 120.0, 1.0, "BPM"),
    P(G_ENERGY, "bpm_span", "Tempo: Bereich bis sehr lebhaft", "So viele BPM ueber dem Wert oben ist das Tempo voll lebhaft.",
      100.0, 40.0, 160.0, 5.0, "BPM"),
    P(G_ENERGY, "kick_rate_full", "Kick-Dichte: voll bei", "Bei so vielen Kicks pro Sekunde gilt die Kick-Dichte als maximal.",
      3.0, 1.0, 6.0, 0.5, "/s"),
    P(G_ENERGY, "loud_dim", "Helligkeit folgt Lautstaerke", "Wird eine Passage leiser als das Lied sonst, wird das normale Licht dunkler (Blitze, Drop, Blinder und WOW! bleiben voll). 0 = aus, 1 = volle Wirkung bis zur Untergrenze. Mit Mixxx und analysiertem Lied zaehlt die Lautstaerkekurve der Analyse, sonst das Audiosignal.",
      0.5, 0.0, 1.0, 0.05, ""),
    P(G_ENERGY, "loud_dim_min", "Helligkeit folgt Lautstaerke: Untergrenze", "So hell bleibt das Licht bei voller Wirkung hoechstens gedimmt (dunkler wird es nur in Break und Stille).",
      0.40, 0.10, 1.0, 0.05, ""),
    P(G_ENERGY, "loud_dim_db", "Helligkeit folgt Lautstaerke: volle Wirkung ab", "So viel leiser als die lauten Teile des Liedes muss es sein fuer die volle Wirkung. Bis 2 dB leiser aendert sich nichts.",
      14.0, 6.0, 30.0, 1.0, "dB"),
    P(G_ENERGY, "energy_bias", "Gesamt ruhiger / lebhafter", "Verschiebt alle Intensitaetsstufen. Minus = insgesamt ruhiger, plus = lebhafter.",
      0.0, -0.3, 0.3, 0.02, ""),
    P(G_ENERGY, "drop_boost", "Energie-Schub nach Drop", "Um wie viel die Energie nach einem Drop kurz erhoeht wird.",
      0.30, 0.0, 0.6, 0.05, ""),
    P(G_ENERGY, "boost_decay_s", "Energie-Schub: Abklingzeit", "Wie lange der Schub nach dem Drop abklingt.",
      10.0, 2.0, 30.0, 1.0, "s"),
    P(G_ENERGY, "drop_arousal", "Energie beim Drop mindestens", "Auf diesen Wert wird die Energie bei einem Drop mindestens gesetzt.",
      0.78, 0.40, 1.00, 0.02, ""),
    # ---- Stimmung: Farbe und Tonart ---------------------------------------------------------
    P(G_COLOR, "valence_tc", "Stimmung: Traegheit", "Wie langsam sich die erkannte Stimmung (froh/duester) anpasst.",
      15.0, 3.0, 60.0, 1.0, "s"),
    P(G_COLOR, "key_conf_min", "Tonart: Mindestsicherheit", "Ab dieser Sicherheit wird Dur/Moll fuer die Stimmung genutzt. Darunter gilt 'unbekannt'.",
      0.40, 0.10, 0.80, 0.02, ""),
    P(G_COLOR, "v_w_mode", "Gewicht Dur/Moll", "Wie stark Dur (froh) oder Moll (duester) die Stimmung bestimmt. Gewichte werden normiert.",
      0.45, 0.0, 1.0, 0.05, ""),
    P(G_COLOR, "v_w_tempo", "Gewicht Tempo (Stimmung)", "Wie stark das Tempo die Stimmung bestimmt.",
      0.20, 0.0, 1.0, 0.05, ""),
    P(G_COLOR, "v_w_bright", "Gewicht Klanghelligkeit", "Wie stark ein heller Klang die Stimmung bestimmt.",
      0.20, 0.0, 1.0, 0.05, ""),
    P(G_COLOR, "v_w_energy", "Gewicht Energie (Stimmung)", "Wie stark die Energie die Stimmung bestimmt.",
      0.15, 0.0, 1.0, 0.05, ""),
    P(G_COLOR, "quad_a", "Farbfamilie: Energie-Grenze", "Ab dieser Energie gilt ein Stueck als energiegeladen (euphorisch/intensiv).",
      0.50, 0.30, 0.70, 0.01, ""),
    P(G_COLOR, "quad_v", "Farbfamilie: Stimmungs-Grenze", "Ab dieser Stimmung gilt ein Stueck als froh (euphorisch/froh).",
      0.50, 0.30, 0.70, 0.01, ""),
    P(G_COLOR, "quad_hyst", "Farbfamilie: Hysterese", "Abstand, damit die Farbfamilie nicht dauernd hin und her springt.",
      0.04, 0.0, 0.10, 0.01, ""),
    P(G_COLOR, "color_min_s", "Farbe: Mindestdauer", "So lange bleibt eine Farbe mindestens stehen, bevor sie bei Phrase oder Drop wechseln darf.",
      8.0, 2.0, 60.0, 1.0, "s"),
    P(G_COLOR, "hue_fade_s", "Farbwechsel: Ueberblendzeit", "Wie lange die Ueberblendung zur neuen Farbe dauert.",
      1.0, 0.2, 5.0, 0.1, "s"),
    # ---- Phasen -----------------------------------------------------------------------------
    P(G_PHASE, "early_s", "Anlaufzeit ohne Phasen", "In den ersten Sekunden nach dem Start werden keine Phasen erkannt.",
      12.0, 0.0, 60.0, 1.0, "s"),
    P(G_PHASE, "break_below_db", "Break: so viel leiser", "So viel leiser als der Song-Durchschnitt muss es sein, damit ein Break erkannt wird.",
      7.0, 3.0, 15.0, 0.5, "dB"),
    P(G_PHASE, "break_hold_s", "Break: Mindestdauer leise", "So lange muss es leise (und ohne Kick) sein, bis ein Break beginnt.",
      1.5, 0.5, 5.0, 0.1, "s"),
    P(G_PHASE, "break_max_s", "Break: laengstens", "Nach dieser Zeit wird ein Break spaetestens beendet (Drop).",
      30.0, 10.0, 90.0, 5.0, "s"),
    P(G_PHASE, "break_dim", "Break: Helligkeit", "Wie hell das Licht im Break ist. 0 = dunkel.",
      0.20, 0.0, 0.60, 0.05, ""),
    P(G_PHASE, "build_score_min", "Build-up: Mindest-Anstieg", "Wie deutlich Pegel, Hoehen und Helligkeit ansteigen muessen. Hoeher = weniger Build-ups.",
      0.55, 0.30, 0.90, 0.01, ""),
    P(G_PHASE, "build_hold_s", "Build-up: Mindestdauer", "So lange muss der Anstieg anhalten, bis ein Build-up erkannt wird.",
      1.5, 0.5, 5.0, 0.1, "s"),
    P(G_PHASE, "build_cooldown_s", "Build-up: Pause nach Drop", "So lange nach einem Drop wird kein neuer Build-up erkannt.",
      10.0, 3.0, 30.0, 1.0, "s"),
    P(G_PHASE, "build_max_s", "Build-up: laengstens", "Nach dieser Zeit endet ein Build-up auch ohne Drop.",
      24.0, 8.0, 60.0, 1.0, "s"),
    P(G_PHASE, "gap_drop_db", "Pause (Stille vor dem Drop): Pegelsturz", "So stark muss der Pegel ploetzlich fallen, damit eine kurze Stille erkannt wird.",
      10.0, 4.0, 20.0, 0.5, "dB"),
    P(G_PHASE, "return_db", "Rueckkehr nach Stille oder Break: Abstand", "Ein Drop nach einer Stille oder einem Break entsteht nur, wenn der Pegel wieder bis auf so viel an den Pegel vor der Pause herankommt. Verhindert Drops bei Rauschen und in leiseren Passagen mit weiterlaufendem Beat.",
      6.0, 3.0, 30.0, 1.0, "dB"),
    P(G_PHASE, "gap_max_s", "Pause: laengstens", "Nach dieser Zeit endet die kurze Stille spaetestens mit einem Drop.",
      2.5, 1.0, 6.0, 0.5, "s"),
    P(G_PHASE, "drop_jump_db", "Drop: Pegelsprung", "So stark muss der Pegel binnen 2 s steigen, damit ein Einsatz als Drop gilt.",
      5.0, 2.0, 12.0, 0.5, "dB"),
    P(G_PHASE, "drop_cooldown_s", "Drop: Pause danach", "So lange nach einem Drop wird kein neuer Einsatz-Drop erkannt.",
      12.0, 4.0, 40.0, 1.0, "s"),
    P(G_PHASE, "drop_len_s", "Drop: Dauer", "So lange dauert die Drop-Phase mit der hellen Show.",
      2.5, 1.0, 6.0, 0.5, "s"),
    # ---- Intensitaetsstufen -----------------------------------------------------------------
    P(G_TIER, "tier_up_1", "Stufe 1 (sanft) ab", "Ab dieser Intensitaet geht es von ruhig auf sanft.",
      0.38, 0.10, 0.95, 0.01, ""),
    P(G_TIER, "tier_up_2", "Stufe 2 (Groove) ab", "Ab dieser Intensitaet geht es auf Groove.",
      0.55, 0.10, 0.95, 0.01, ""),
    P(G_TIER, "tier_up_3", "Stufe 3 (Peak) ab", "Ab dieser Intensitaet geht es auf Peak.",
      0.75, 0.10, 0.95, 0.01, ""),
    P(G_TIER, "tier_hyst", "Stufen: Hysterese", "Abstand zwischen Hoch- und Runterschalten, damit die Stufen nicht flattern.",
      0.06, 0.0, 0.15, 0.01, ""),
    P(G_TIER, "tier_min_s", "Stufen: Mindestdauer", "So lange bleibt eine Stufe mindestens bestehen.",
      6.0, 1.0, 30.0, 1.0, "s"),
    P(G_TIER, "inten_tc", "Intensitaet: Traegheit", "Wie langsam die Intensitaet der Energie folgt.",
      3.0, 0.5, 15.0, 0.5, "s"),
    # ---- Weisse Blitze und Strobo -----------------------------------------------------------
    P(G_FLASH, "blitz_on_frames", "Blitzdauer", "So lange leuchtet ein Blitz (Blitz-Knopf und Strobo-Burst), in Bildern zu 25 ms. 2 = 50 ms. Kuerzer wirkt haerter.",
      2.0, 1.0, 8.0, 1.0, "Bilder"),
    P(G_FLASH, "blitz_band_sync", "Effektband blitzt synchron", "An: Beim Blitz, Strobo-Burst und bei WOW! steht der Effektband auf Preset 35 (Solid weiss) und blitzt im Takt mit allen anderen. In WLED muss dazu die Uebergangszeit auf 0 stehen (Config, LED Preferences). Aus: das WLED-eigene Strobo-Preset, das nicht synchron laeuft.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_FLASH, "solo_on", "Einzel-Strobe im AUTO-Modus", "An: Im AUTO-Modus blitzt ab und zu EIN Fixture ueber seinen eigenen Strobe-Kanal, waehrend die anderen normal weiterlaufen. Wirkt nur mit der Strobe-Erlaubnis.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_FLASH, "solo_every", "Einzel-Strobe: alle ... Takte", "Alle wie viele Takte ein Einzel-Strobe starten darf (sofern Stufe und Zufall passen).",
      4.0, 1.0, 16.0, 1.0, "Takte"),
    P(G_FLASH, "solo_prob", "Einzel-Strobe: Wahrscheinlichkeit", "Chance, dass es zu diesem Zeitpunkt wirklich einen Einzel-Strobe gibt.",
      0.6, 0.1, 1.0, 0.05, ""),
    P(G_FLASH, "solo_beats", "Einzel-Strobe: Dauer", "So viele Beats blitzt das ausgewaehlte Fixture.",
      4.0, 1.0, 8.0, 1.0, "Beats"),
    P(G_FLASH, "solo_min_tier", "Einzel-Strobe: ab Stufe", "Erst ab dieser Intensitaetsstufe gibt es Einzel-Strobes (3 = nur bei voller Dynamik).",
      3.0, 1.0, 3.0, 1.0, ""),
    P(G_FLASH, "solo_rate", "Einzel-Strobe: Geschwindigkeit", "0,1 = langsam, 1 = schnell (Bereich des Strobe-Kanals des jeweiligen Geraets).",
      0.6, 0.1, 1.0, 0.05, ""),
    P(G_FLASH, "flash_every", "Weisser Blitz alle", "Alle so viele Beats ein weisser Akzent-Blitz bei hoher Energie. 0 = aus.",
      16.0, 0.0, 64.0, 1.0, "Beats"),
    P(G_FLASH, "flash_arousal", "Weisser Blitz ab Energie", "Mindest-Energie fuer die weissen Akzent-Blitze.",
      0.45, 0.20, 0.90, 0.01, ""),
    P(G_FLASH, "burst_cool_s", "Strobo-Burst: Pause", "Mindestabstand zwischen zwei automatischen Strobo-Bursts (nur mit Strobe-Erlaubnis).",
      30.0, 10.0, 120.0, 5.0, "s"),
    P(G_FLASH, "burst_cool_drop_s", "Strobo-Burst: Pause bei Drop", "Mindestabstand, wenn der Burst durch einen Drop ausgeloest wird.",
      12.0, 5.0, 60.0, 1.0, "s"),
    P(G_FLASH, "burst_len_s", "Strobo-Burst: Dauer", "So lange dauert ein automatischer Strobo-Burst.",
      1.0, 0.3, 3.0, 0.1, "s"),
] + [
    P(G_FLASH, f"strobe_max_{k}", f"Strobe-Grenze: {label}",
      f"Bis zu dieser Strobe-Stufe (Blitze pro Sekunde) blitzt die Gruppe {label} beim allgemeinen Strobe mit "
      "(Strobe-Knopf, Strobo-Burst, WOW!). Bei schnellerem Strobe bleibt sie dunkel, zum Beispiel wenn sie nicht mehr "
      "mitkommt. nie = blitzt nie mit. 10 = blitzt immer mit (Standard)."
      + (" Die Washes blitzen grundsaetzlich nicht (zu traege)." if k == "wash" else ""),
      6.0, 0.0, 6.0, 1.0, "switch:nie|1|2|4|5|6,7|10")
    for k, label in (("bar", "Spider"), ("wash", "Washes"), ("barlight", "PAR Barlicht"), ("fx", "Eyes und Derby"),
                     ("uv", "UV-Leiste"), ("spot", "Moving Head"), ("amb", "Ambiente (WLED)"), ("nano", "Nanoleaf"))
] + [
    # ---- Takt -------------------------------------------------------------------------------
    P(G_METER, "meter3_conf", "3/4: Dreiergruppen ab Sicherheit", "Erst ab dieser Sicherheit der Takterkennung zaehlt das Licht in Dreiergruppen (3/4). 1,00 = nur bei 100 %. Darunter bleibt es bei Vierergruppen.",
      1.0, 0.50, 1.0, 0.01, ""),
    # ---- Mixxx-Vorhersage ---------------------------------------------------------------------
    P(G_MIXXX, "mixxx_light", "Vorhersage fuers Licht nutzen", "0 = nur im Panel anzeigen, 1 = Break, Aufbau, Stille und Drop vom Licht nach der Vorhersage aus der Analyse steuern. Wirkt nur, wenn Mixxx verbunden und das Lied analysiert ist.",
      0.0, 0.0, 1.0, 1.0, "switch:nur anzeigen|Licht folgt"),
    P(G_MIXXX, "mixxx_tempo", "Tempo und Beat von Mixxx", "1 = Tempo (BPM) und die Lage im Beat kommen von Mixxx statt aus dem Audio, solange ein Deck hoerbar spielt. Genauer, auch mit Sync und Pitch.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_MIXXX, "mixxx_key", "Tonart von Mixxx", "1 = Tonart (Dur/Moll) kommt aus der Mixxx-Analyse statt aus dem Audio, solange ein Deck hoerbar spielt.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_MIXXX, "mixxx_shift_s", "Zeitverschiebung der Ereignisse", "Verschiebt Aufbau, Stille und Drop aus der Analyse. Plus = spaeter, minus = frueher. Loest das Licht zu frueh aus: Wert erhoehen. Nur zum Feinabstimmen, die Analyse selbst kann einzelne Lieder ungenau setzen.",
      0.0, -3.0, 3.0, 0.05, "s"),
    P(G_MIXXX, "mixxx_pause_idle", "Ruhemodus, wenn Mixxx pausiert", "An: Meldet Mixxx kein hoerbares Deck (Pause, Ende des Liedes, Fader zu), geht das Licht sofort in den Ruhemodus, ohne auf das Audiosignal zu warten. So gibt es beim Pausieren keinen falschen Drop. Kommt trotzdem Musik am Eingang an (andere Quelle am Pult), uebernimmt nach wenigen Kicks die Audio-Erkennung mit Beat und BPM (siehe 'Mixxx pausiert: Musik am Eingang ab'). Aus: nur das Audiosignal entscheidet.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_MIXXX, "mixxx_pause_kicks", "Mixxx pausiert: Musik am Eingang ab", "Meldet Mixxx kein hoerbares Deck, kommen aber mindestens so viele Kicks in 3 Sekunden am Audio-Eingang an (zum Beispiel Musik aus einer anderen Quelle am Pult), uebernimmt die Audio-Erkennung mit Beat und BPM. Niedriger = schneller, hoeher = sicherer gegen Rauschen.",
      4.0, 2.0, 8.0, 1.0, "Kicks"),
    P(G_MIXXX, "mixxx_drop_min", "Drop nach Break: Mindeststaerke", "Ab dieser Staerke aus der Analyse gilt ein Einsatz nach einem Break als Drop.",
      0.35, 0.10, 0.90, 0.01, ""),
    P(G_MIXXX, "mixxx_lift_min", "Einsatz ohne Break: Mindeststaerke", "Ab dieser Staerke gilt ein lauter Einsatz ohne Break (Strophe zu Refrain) als Drop. Hoeher = weniger solche Einsaetze.",
      0.30, 0.10, 0.90, 0.01, ""),
    P(G_MIXXX, "mixxx_lead_s", "Vorlauf (Beat und Vorhersage)", "So viel frueher (plus) oder spaeter (minus) reagiert das Licht auf Mixxx' Beat und die Vorhersage. Blitzt das Licht vor dem Schlag: Wert senken, danach: erhoehen. Mixxx meldet die Position etwas vor dem hoerbaren Ton (Audioausgabe).",
      0.05, -0.20, 0.50, 0.01, "s"),
    P(G_MIXXX, "mixxx_cue_snap_s", "Drops auf Hotcues einrasten", "Liegt ein Drop aus der Analyse hoechstens so weit neben einem Hotcue (oft taktgenau an Abschnittswechseln gesetzt), rueckt er genau auf den Hotcue. 0 = aus.",
      1.5, 0.0, 3.0, 0.1, "s"),
    P(G_MIXXX, "mixxx_cue_change", "Wechsel an Hotcues", "Laeuft das Lied ueber einen Hotcue (Abschnittswechsel), wechselt die Show wie nach 8 Takten: neue Farbe, neue Lichtmischung, eventuell eine Szene. 1 = an, 0 = aus.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_MIXXX, "mixxx_genre_style", "Genre-Stile", "An: das Genre aus Mixxx gibt in AUTO den Stil vor. Weihnachten = rot, gruen, gold, ruhig, ohne weisse Blitze; Club (EDM, House, Techno, Trance) = wie bisher; Party (Pop, Schlager, Austropop, Latin, Reggae) = bunt und lebhaft; Rock (Rock, Metal, Blues) = rot, orange, kraeftig; ruhig (Klassik, Ambient, Soundtrack, Jazz) = blau, violett, langsam, ohne weisse Blitze. Selbst gewaehlte Farben im Panel gehen vor.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_MIXXX, "mixxx_energy_w", "Gewicht Mixxx-Energie", "Energiestufe des Liedes aus Mixxx (Kommentar wie 'Energy 7', Crate 'Energy 9' oder Trackfarbe): je Stufe ueber der Mitte wird die Energie um diesen Wert angehoben, je Stufe darunter gesenkt. Bei 0,03 und Mitte 6: Energy 9 = +0,09, Energy 3 = -0,09. 0 = aus.",
      0.03, 0.0, 0.10, 0.005, ""),
    P(G_MIXXX, "mixxx_energy_mid", "Mitte Mixxx-Energie", "Diese Energiestufe aendert nichts; darueber mehr, darunter weniger Licht.",
      6, 1, 9, 1, ""),
    P(G_MIXXX, "mixxx_stale_s", "Verbindung gilt als weg nach", "Kommt so lange nichts mehr aus Mixxx, faellt das Licht auf die Audio-Erkennung zurueck.",
      2.0, 0.5, 10.0, 0.5, "s"),
    # ---- Ausgabe ------------------------------------------------------------------------------
    P(G_OUT, "ola_out", "DMX-Ausgabe", "An: Light-Butler sendet an die DMX-Geraete (ueber das Art-Net-Gateway oder den USB-Adapter, siehe 'DMX-Weg'). Aus: Es wird nichts mehr gesendet (vorher gehen einige Blackout-Bilder raus), damit andere Art-Net-Sender das Art-Net-Gateway nutzen koennen. WLED und Nanoleaf bleiben davon unberuehrt. Die Wahl bleibt nach einem Neustart erhalten.",
      1.0, 0.0, 1.0, 1.0, "switch:Aus (Gateway frei)|An (sendet)"),
    P(G_OUT, "ola_have", "DMX-Geraete vorhanden", "Nein: Diese Anlage hat keine DMX-Geraete (Art-Net-Gateway oder USB-Adapter). Dann wird nichts gesendet, oben steht keine Warnung, und der Light-Butler prueft auch nicht, ob das Geraet erreichbar ist (kein rotes 'fehlt'). Fuers Licht wie 'Ausgabe aus'. Ja: wie bisher, mit dem Schalter Ausgabe an/aus. In den Verbindungen ist das der Knopf 'Nicht vorhanden'.",
      1.0, 0.0, 1.0, 1.0, "switch:Nein (nicht vorhanden)|Ja"),
    P(G_OUT, "dmx_via", "DMX-Weg", "Art-Net-Gateway: Art-Net ueber das Netzwerk zum Gateway, das die DMX-Geraete ansteuert. USB-Adapter: Der FTDI-DMX-Adapter (Open DMX USB) steckt direkt an diesem Licht-Rechner, ein Gateway wird nicht gebraucht. Beim Umschalten bekommt der bisherige Weg einige Blackout-Bilder. Der Adapter darf nur an einem Licht-Rechner stecken. Die Wahl bleibt nach einem Neustart erhalten.",
      0.0, 0.0, 1.0, 1.0, "switch:Art-Net-Gateway|USB-Adapter"),
    P(G_OUT, "artnet_in", "Art-Net-Eingang", "An: Der Light-Butler nimmt Art-Net auf UDP 6454 an (Universe der DMX-Kette) und gibt es statt der Show an die DMX-Geraete weiter, wie ein Art-Net-Gateway. Immer abgesichert: Laser und Hazer bleiben aus, Grenzen der Mode-Kanaele gelten, ohne Strobe-Erlaubnis keine Strobe-Kanaele. BLACKOUT wirkt weiter. Kommt 3 s nichts mehr, uebernimmt wieder die Show. WLED und Nanoleaf steuert weiter die Show.",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_OUT, "wled_out", "Ausgabe an die WLED-Lichter", "An: Light-Butler steuert die WLED-LED-Streifen. Aus: Es wird nichts mehr an die WLED-Geraete gesendet, sie kehren zu ihrem eigenen Zustand zurueck und lassen sich anderweitig steuern (zum Beispiel per WLED-App). Die DMX-Ausgabe und die Nanoleaf-Panels sind davon unberuehrt. Die Wahl bleibt nach einem Neustart erhalten.",
      1.0, 0.0, 1.0, 1.0, "switch:Aus (WLED frei)|An (sendet)"),
    P(G_OUT, "wled_have", "WLED-Lichter vorhanden", "Nein: Diese Anlage hat keine WLED-Lichter (Wunsch 14.11.2026). Dann wird nichts gesendet, oben steht keine Warnung, und der Light-Butler prueft auch nicht, ob das Geraet erreichbar ist (kein rotes 'fehlt'). Fuers Licht wie 'Ausgabe aus'. Ja: wie bisher, mit dem Schalter Ausgabe an/aus. In den Verbindungen ist das der Knopf 'Nicht vorhanden'.",
      1.0, 0.0, 1.0, 1.0, "switch:Nein (nicht vorhanden)|Ja"),
    P(G_OUT, "sm_light_ms", "Showmanager: Licht-Versatz", "Programmierte Shows: So viele Millisekunden laeuft das Licht der Musik voraus (negativ: hinterher). Zum Ausgleich von Verzoegerungen, zum Beispiel Bluetooth-Lautsprecher (etwa +150 bis +250) oder langsamer Moving-Head.",
      0.0, -1000.0, 1000.0, 5.0, "ms"),
    P(G_OUT, "sm_stems_max_min", "Pegelkurven bis Liedlaenge", "Spur-Kurven (Bass, Stimme, Schlagzeug ...) rechnen die Musik-Rechner (Mac oder Windows-PC) nur fuer MP3s bis zu dieser Laenge, fuer Shows und fuer den Vorab-Lauf der ganzen Bibliothek. Laengere (Mitschnitte, Mixe) brauchen viel Rechenzeit, je Lied etwa das 1,5-Fache der Laenge am Musik-Rechner. 0 = keine Grenze. Eine beim Namen genannte Show wird immer gerechnet.",
      10.0, 0.0, 60.0, 1.0, "min"),
    P(G_OUT, "sm_mixxx_auto", "Shows aus Mixxx automatisch starten", "An: Spielt in Mixxx hoerbar ein Lied, zu dem es eine Show gibt, uebernimmt sie das Licht ohne Rueckfrage und folgt dem Deck, auch bei Pitch und Spruengen. Beim Mischen wechselt sie, sobald das andere Deck lauter ist. Pause oder leise: zurueck zu AUTO. Der Knopf SHOW beendet sie fuer dieses Lied. Die Strobe-Erlaubnis bleibt davon unberuehrt.",
      0.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_OUT, "sm_laser", "Laser in Shows erlauben", "An: Laser-Clips aus dem Showmanager laufen, auch wenn die Show aus Mixxx startet. Aus: Die Laser bleiben in Shows aus, der Rest der Show laeuft. Nur waehrend die Musik wirklich laeuft, sofort aus bei Pause, Springen, Stop, BLACKOUT, FREEZE und ohne Meldung vom Browser oder von Mixxx. Nie auf Personen oder in Augenhoehe richten: Die Software weiss nicht, wohin der Strahl zeigt.",
      0.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_OUT, "sm_fog", "Nebel in Shows erlauben", "An: Nebelschuebe aus dem Showmanager werden ausgeloest, auch wenn die Show aus Mixxx startet, auf demselben Weg wie der SMOKE-Knopf: hoechstens 10 s, danach die Mindestpause. Die Show schaltet die Nebelmaschine nie selbst ein. Ist sie aus, kalt oder die Pause nicht um, entfaellt der Schub. Vorsicht Rauchmelder.",
      0.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_OUT, "eb_no_sound", "Effektband ohne Ton", "An: Am Mikrofon des Effektbands liegt kein Ton an. Die Automatik waehlt dann keine soundgesteuerten Presets (mit ♫, sie blieben ohne Ton stehen), sondern nur die anderen. Gilt fuer AUTO, Drop-Akzente, Szenen-Automatik und feste Szenen; von Hand gewaehlte Presets bleiben, wie du sie waehlst.",
      0.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_OUT, "nano_out", "Ausgabe an die Nanoleaf-Panels", "An: Light-Butler steuert die Nanoleaf Light Panels. Aus: Es wird nichts mehr gesendet, die Panels gehen dunkel und bekommen ihren vorherigen Effekt zurueck, damit sie sich anderweitig steuern lassen (zum Beispiel per Nanoleaf-App). Art-Net-Gateway und WLED sind davon unberuehrt. Die Wahl bleibt nach einem Neustart erhalten.",
      1.0, 0.0, 1.0, 1.0, "switch:Aus (Panels frei)|An (sendet)"),
    P(G_OUT, "nano_have", "Nanoleaf-Panels vorhanden", "Nein: Diese Anlage hat keine Nanoleaf-Panels (Wunsch 14.11.2026). Dann wird nichts gesendet, oben steht keine Warnung, und der Light-Butler prueft auch nicht, ob das Geraet erreichbar ist (kein rotes 'fehlt'). Fuers Licht wie 'Ausgabe aus'. Ja: wie bisher, mit dem Schalter Ausgabe an/aus. In den Verbindungen ist das der Knopf 'Nicht vorhanden'.",
      1.0, 0.0, 1.0, 1.0, "switch:Nein (nicht vorhanden)|Ja"),
    P(G_HOME, "home_auto", "Wohnzimmerlicht automatisch", "An: Ist laenger keine Musik (siehe 'Stille ab'), dimmt die Show das Wohnzimmerlicht hoch, und die Partylichter bleiben dunkel statt zu atmen. Laeuft wieder Musik und ist mindestens ein Partylicht erreichbar (Art-Net-Gateway, WLED-Streifen oder Nanoleaf), schaltet sie das Wohnzimmerlicht aus. Geschaltet wird nur beim Wechsel; was du dazwischen selbst schaltest, bleibt.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_HOME, "home_party_min", "Wohnzimmerlicht an: nur nach Musik von", "Das Wohnzimmerlicht geht bei Stille nur an, wenn vorher insgesamt mindestens so lange Musik gelaufen ist (eine Party, nicht bloss Rauschen oder ein Geraeusch am Eingang). Danach zaehlt es wieder von vorn. 0 = wie frueher, schon nach kurzer Musik.",
      5.0, 0.0, 60.0, 1.0, "min"),
    P(G_HOME, "home_idle_s", "Wohnzimmerlicht an: Stille ab", "So lange muss keine Musik laufen (Ruhemodus), bis das Wohnzimmerlicht hochgedimmt wird.",
      10.0, 3.0, 600.0, 1.0, "s"),
    P(G_HOME, "home_idle_level", "Wohnzimmerlicht: Helligkeit bei Stille", "Auf diese Helligkeit wird das Wohnzimmerlicht bei Stille gedimmt.",
      60.0, 5.0, 100.0, 5.0, "%"),
    P(G_HOME, "home_ramp_s", "Wohnzimmerlicht: Dimmzeit", "So langsam dimmt die Automatik das Wohnzimmerlicht hoch und wieder aus (Rampe des Dimmers). 0 = sofort. Gilt nur fuer die Automatik, nicht fuer den Regler im Bereich Haus.",
      5.0, 0.0, 60.0, 1.0, "s"),
    P(G_HOME, "home_music_s", "Wohnzimmerlicht aus: Musik seit", "So lange muss wieder Musik laufen, bis das Wohnzimmerlicht ausgeschaltet wird (kurze Geraeusche loesen nichts aus).",
      30.0, 0.5, 120.0, 0.5, "s"),
    # ---- Nebel: nur per SMOKE-Knopf. Steckdose der Nebelmaschine, Aufheizen, Schub ueber DMX oder HomeMatic ----
    P(G_FOG, "fog_via", "Nebel ueber", "Womit der SMOKE-Knopf den Nebelschub ausloest: DMX (Hazer-Kanaele) oder den HomeMatic-Schalter Nebelschub (wenn das DMX-Empfangsmodul spinnt). Beim HomeMatic-Schalter geht jeder Schub nach hoechstens 10 s von selbst aus, auch wenn der Aus-Befehl verloren geht.",
      0.0, 0.0, 1.0, 1.0, "switch:DMX|HomeMatic"),
    P(G_FOG, "fog_warm_min", "Nebel: Aufheizzeit", "So lange muss die Nebelmaschine nach dem Einschalten heizen, bevor SMOKE Nebel gibt. Bei HomeMatic muss zusaetzlich der Schalter Nebelschub erreichbar sein. War die Maschine beim Start der Show schon an, gilt sie als warm.",
      4.0, 0.0, 15.0, 0.5, "min"),
    P(G_FOG, "fog_off_min", "Nebel: Maschine aus nach", "So lange ohne Nebel, dann schaltet die Show die Steckdose der Nebelmaschine wieder aus. 0 = nie.",
      30.0, 0.0, 120.0, 5.0, "min"),
    # ---- Abwechslung Docooler/Vega in AUTO ----
    P(G_TIER, "dc_mix", "Abwechslung Spider/Moving Head", "An: In AUTO leuchten die Spider nicht immer alle, sondern in wechselnden Gruppierungen (nur die aeusseren, nur die inneren, einzeln wandernd, links gegen rechts, einer allein). Der Moving Head in der Mitte leuchtet vor allem, wenn die inneren Spider dunkel sind, ruhig nur sanft. Stufe 3 und Drop: alle wie bisher. Aus: alle Spider immer, Moving Head unabhaengig.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_TIER, "dc_mix_bars", "Abwechslung: neue Gruppierung alle", "Nach so vielen Takten wechselt die Gruppierung der Spider, nach jedem Drop sofort.",
      8.0, 2.0, 32.0, 1.0, "Takte"),
    # ---- Vega-Strahl in AUTO (Gobo, Drehung, Prisma, Zoom), gilt nur solange Beam auf Auto steht ----
    P(G_VEGA, "vega_live", "Moving-Head-Strahl lebendig", "An: In AUTO wechselt der Moving Head bei hoher Energie durch alle fuenf Gobos (beim Drop sofort das naechste), die Drehung folgt Stufe und Tempo und wechselt alle 2 Phrasen die Richtung, im Aufbau wird der Strahl enger und das Prisma kommt dazu, beim Drop dreht das Prisma schnell. Ruhig: Gobo offen. Aus: wie frueher (nur Gobo-Wechsel, feste Drehung).",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    # ---- Szenen-Automatik: AUTO drueckt ab und zu selbst eine Szene (nach der Stufe im Lied) ----
    P(G_SCAUTO, "sa_on", "Szenen-Automatik", "An: In AUTO waehlt die Show ab und zu selbst kurz eine Szene, nach ihrer Stelle in deiner Szenenliste: ruhige Musik vorne, wilde Musik und Drops hinten. Nie die Szene Laser, keine Ziel-Szenen (Bank, Tisch, Tuer, Bar), nicht All off, RESET und QUIZ, Strobe-Szenen nur mit Strobe-Erlaubnis. Nicht in Stille und Break. Sobald du selbst etwas drueckst, pausiert sie.",
      0.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_SCAUTO, "sa_prob", "Szenen-Automatik: wie oft", "Wahrscheinlichkeit, dass am Anfang einer Phrase (8 Takte) eine Szene kommt. 100 % = jede Phrase.",
      35.0, 5.0, 100.0, 5.0, "%"),
    P(G_SCAUTO, "sa_eb_share", "Szenen-Automatik: Anteil Effektband-Presets", "So oft waehlt die Automatik statt einer Szene nur ein passendes Effektband-Preset (das restliche Licht laeuft in AUTO weiter). 0 % = nur Szenen, 100 % = nur Effektband-Presets.",
      40.0, 0.0, 100.0, 5.0, "%"),
    P(G_SCAUTO, "sa_bars", "Szenen-Automatik: hoechstens Takte", "So lange laeuft eine Szene hoechstens (zufaellig 1 Takt bis zu diesem Wert), danach geht es in AUTO weiter.",
      4.0, 1.0, 8.0, 1.0, "Takte"),
    P(G_SCAUTO, "sa_drop", "Szenen-Automatik: Szene beim Drop", "An: Beim Drop (auch vorhergesagt aus Mixxx) kommt eine der wildesten Szenen vom Ende der Liste, so lange wie der Drop dauert.",
      1.0, 0.0, 1.0, 1.0, "switch:aus|an"),
    P(G_SCAUTO, "sa_pause_s", "Szenen-Automatik: Pause nach eigener Bedienung", "So lange waehlt die Automatik keine Szene, nachdem du selbst etwas gedrueckt hast (Szene, Licht-Mix, Bewegung, Farbe, Speed, Blackout, Blinder, Beam ...).",
      120.0, 10.0, 900.0, 10.0, "s"),
    P(G_PANEL, "ui_lang", "Sprache der Knoepfe", "Sprache der Knoepfe und Ueberschriften im Bedienbereich (Geschwindigkeit, Licht-Mix, Bewegung, Farbe, Ziel und die grossen Knoepfe oben). Einstellungen und Hinweise bleiben deutsch. Gilt fuer alle Geraete, die das Panel offen haben.",
      1.0, 0.0, 1.0, 1.0, "switch:Deutsch|English"),
    P(G_PANEL, "ui_hints", "Hinweistexte im Panel anzeigen", "Ja: die grauen Hinweiszeilen im Panel sind sichtbar (zum Beispiel unter dem Effektband, bei Tempo, Farbe und in den Verbindungen). Nein: sie verschwinden, das Panel wird kuerzer und ruhiger. Die Beschreibungen in den Einstellungen bleiben immer sichtbar. Gilt fuer alle Geraete, die das Panel offen haben.",
      1.0, 0.0, 1.0, 1.0, "switch:Nein|Ja"),
    P(G_PANEL, "fav_panel", "Herz im Hauptpanel", "An: Neben dem Cover des laufenden Liedes steht ein Herz. Antippen markiert das Lied als Favorit (oder nimmt es wieder heraus), so wie in der Musik-Datenbank. Aus: kein Herz im Hauptpanel, die Favoriten bleiben. Aufs Licht wirkt das nie.",
      1.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_PANEL, "fav_mp3", "Favoriten auch in die MP3 schreiben", "An: Ein Herz bei einem Lied schreibt der Musik-Rechner zusaetzlich als Bewertung 5 Sterne (POPM) in die MP3, Herz weg = Bewertung weg. Andere Programme (Mp3tag, MusicBee, foobar, Windows) zeigen das. Jede Aenderung aendert die Datei, beim naechsten Spiegeln wird sie neu kopiert. Aus: Favoriten stehen nur am Light-Butler. Die bisherigen Herzen schreibt der Knopf auf der Seite Favoriten nachtraeglich.",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_OUT, "link_on", "Ableton Link", "An: Der Light-Butler gibt das aktuelle Tempo (wie oben im Panel angezeigt) per Ableton Link ins Netz, ueber LAN und WLAN. Bei Stille sendet er das kleinste Link-Tempo, 20 BPM. Andere Link-Geraete (Ableton Live, Apps, Synthesizer) uebernehmen das Tempo. Aus: Der Light-Butler nimmt nicht an Link teil. Die Wahl bleibt nach einem Neustart erhalten.",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An (sendet Tempo)"),
    # ---- Titelerkennung ------------------------------------------------------------------------
    P(G_SONG, "mixxx_on", "Mixxx verwenden", "An: Die DJ-Software Mixxx gehoert dazu (Liedliste, Hotcues, Kisten, Sterne, Abgleich mit dem Stick). Aus: Betrieb ohne Mixxx: das Panel blendet alles aus, was nur mit Mixxx geht, Hinweise und Texte nennen Mixxx nicht mehr, der Musik-Rechner nimmt die Lieder nur aus dem Musikordner. In Mixxx wird dabei nichts geaendert oder geloescht; wieder an = alles wie vorher. Aufs Licht wirkt der Schalter nicht.",
      1.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_SONG, "lyrics_auto", "Liedtext zum laufenden Lied holen", "An: Zum Lied aus Mixxx oder aus der Titelerkennung sucht der Light-Butler einmal den Text bei LRCLIB und zeigt die aktuelle Zeile im Hauptpanel. Titel und Interpret gehen dorthin, keine Musik. Mit Internet, jedes Lied nur einmal, das Licht wartet nie darauf. Bei einer laufenden Show gilt deren Liedtext auch ohne diesen Schalter. 0 = aus.",
      0.0, 0, 1, 1, ""),
    P(G_SONG, "songrec_on", "Titel und Interpret erkennen (SongRec)", "An: Laeuft Musik und Mixxx spielt nicht, erkennt der Light-Butler Titel und Interpret ueber SongRec und zeigt sie im Panel und auf der Statistik-Seite. Dazu geht regelmaessig ein Fingerabdruck der letzten 12 s Ton an den Online-Dienst von Shazam (keine Aufnahme). Braucht Internet und das Programm SongRec auf dem Licht-Rechner. Das Licht aendert sich nur ueber den Genre-Stil (Schalter unten).",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_SONG, "songrec_every", "Abstand der Anfragen", "So oft fragt der Light-Butler nach dem Titel, solange Musik laeuft. Kuerzer findet neue Lieder schneller, schickt aber mehr Anfragen und kann von Shazam gebremst werden.",
      40.0, 20.0, 300.0, 5.0, "s"),
    P(G_SONG, "songrec_style", "Erkanntes Genre gibt den Stil vor", "An: Das Genre des erkannten Liedes gibt in AUTO den Stil vor (Farbpalette, Bewegung, Energie, weisse Blitze nur seltener), genau wie das Genre aus Mixxx. Zuordnung in der Tabelle Genre-Stile. Ein Stil von Hand und Mixxx gehen vor. Wirkt nur mit eingeschalteter Titelerkennung.",
      1.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_SONG, "energy_write", "Geschaetzte Energiestufe in die MP3 schreiben", "Lieder ohne Stufe im Tag bekommen am Musik-Rechner eine geschaetzte Stufe (im Panel mit Wellenlinie, zum Beispiel E6~). An: Die Mixxx-Bruecke schreibt sie in die MP3-Datei (ID3-Feld EnergyLevel, dazu der Vermerk geschaetzt). Die Musik selbst und die Zuordnung der Shows bleiben gleich. Eine vorhandene Stufe im Tag wird nie ueberschrieben. Aus: Die Schaetzung bleibt nur im Light-Butler. Mixxx zeigt das Feld nicht an.",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_SONG, "key_write", "Geschaetzte Tonart und BPM in die MP3 schreiben", "Lieder ohne Tonart oder BPM in Mixxx bekommen am Musik-Rechner die Werte aus der Datei (Felder TKEY, TBPM) oder, wenn dort keine stehen, geschaetzte (essentia, im Panel mit Wellenlinie). An: Die Mixxx-Bruecke schreibt die geschaetzte Tonart als Camelot (zum Beispiel 8A) ins Feld TKEY und die geschaetzten BPM ins Feld TBPM der MP3, dazu den Vermerk geschaetzt. Die Musik selbst und die Zuordnung der Shows bleiben gleich. Eine vorhandene Tonart oder BPM in der Datei wird nie ueberschrieben. Aus: Die Schaetzung bleibt nur im Light-Butler.",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_SONG, "cue_est", "Cues ohne Mixxx fuers Licht", "Fuer Lieder ohne Hotcues in Mixxx: An: Der Musik-Rechner nimmt die Cues aus der MP3 (falls ein anderes Programm sie dort gespeichert hat) oder schaetzt sie aus der eigenen Analyse (erster Beat bzw. Ende des Intros, deutliche Drops, Anfaenge von Vers, Hauptteil, Break und Outro, auf den Takt gerastet, hoechstens 8). Das Licht nutzt sie wie Hotcues aus Mixxx: Drops rasten darauf ein, an einem Cue wechselt das Licht wie bei einer neuen Phrase. Hotcues aus Mixxx gehen immer vor. Aus: wie bisher nur die Hotcues aus Mixxx.",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_SONG, "cue_write", "Geschaetzte Cues in Mixxx schreiben", "An: Die App Light-Butler Mixxx schreibt beim Start, bevor Mixxx laeuft, in Lieder ganz ohne Hotcues die Cues aus der MP3 oder die geschaetzten (wie bei Cues ohne Mixxx fuers Licht), mit Sicherungskopie der Mixxx-Datenbank. Sie heissen LB Start, LB Drop, LB Hauptteil ... und sind lila, damit du sie von deinen eigenen unterscheidest. Lieder mit eigenen Hotcues bleiben unberuehrt. Loeschst du LB-Cues in Mixxx, kommen sie bei diesem Lied nie wieder. Aus: In Mixxx wird nichts geschrieben.",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    P(G_SONG, "rg_write", "ReplayGain in die MP3 schreiben", "Der Musik-Rechner misst die Lautheit jedes Liedes (EBU R128, wie Radio und Spotify; Spalte Lautheit in der Musik-Datenbank). An: Die Mixxx-Bruecke schreibt dazu die ReplayGain-Angabe (REPLAYGAIN_TRACK_GAIN und _PEAK, Bezug -18 LUFS) in die MP3, damit Mixxx und andere Player gleich laut abspielen. Nur in Dateien, in denen noch keine ReplayGain-Angabe steht; eine vorhandene bleibt, wie sie ist. Die Musik selbst und die Zuordnung der Shows bleiben gleich. Aus: Die Messung bleibt nur im Light-Butler (Vorhoeren und Auto-DJ gleichen trotzdem an).",
      0.0, 0.0, 1.0, 1.0, "switch:Aus|An"),
    # ---- Laser --------------------------------------------------------------------------------
    P(G_LASER, "laser_mode", "Laser-Betrieb", "Wie die Laser in der Szene Laser laufen. Light-Butler steuert (DMX): der Light-Butler schaltet Farben, Effekte und Tempo im Takt (KTV ueber Muster und Gruppe, 21 Eyes und Derby direkt). Sound-to-Light: die Laser nutzen ihr eigenes Mikrofon (KTV Sound-Modus, Eyes DJ Sound, Derby Tonsteuerung). Auto: Eyes macht seine eigene Show ohne Mikrofon (Programm AUTO); KTV und Derby laufen dann wie bei 'Light-Butler steuert'.",
      1.0, 0.0, 2.0, 1.0, "switch:Light-Butler steuert (DMX)|Sound-to-Light (intern)|Auto (eigene Show)"),
    P(G_LASER, "laser_duty", "Laser: Puls-Anteil", "Gilt nur bei 'Light-Butler steuert'. Die Laser pulsieren im Takt: nach jedem Puls sind sie so lange an (Anteil am Abstand zwischen zwei Pulsen), danach aus bis zum naechsten. 100 % = immer an. Wie oft gepulst wird, waehlt Speed: Low alle 2 Beats, Med jeder Beat, Hot jeder halbe Beat (nur mit Strobe-Erlaubnis, sonst jeder Beat). Ohne Strobe-Erlaubnis hoechstens 2 Pulse pro Sekunde.",
      40.0, 10.0, 100.0, 5.0, "%"),
    P(G_LASER, "ktv_fx_a", "KTV-Muster A", "Normalbetrieb: wechselt alle 2 Takte mit Muster B. Kanal 15 des KTV in der Szene Laser bei \"Light-Butler steuert\". Mit dem DMX-Debugger findest du schoene Werte (Kanal 315), je 2 Werte ein Effekt. Hoechstens 244, darueber laufen Selbstlauf und Sound.",
      46.0, 0.0, 244.0, 1.0, ""),
    P(G_LASER, "ktv_fx_b", "KTV-Muster B", "Normalbetrieb: wechselt alle 2 Takte mit Muster A. Kanal 15 des KTV in der Szene Laser bei \"Light-Butler steuert\". Mit dem DMX-Debugger findest du schoene Werte (Kanal 315), je 2 Werte ein Effekt. Hoechstens 244, darueber laufen Selbstlauf und Sound.",
      35.0, 0.0, 244.0, 1.0, ""),
    P(G_LASER, "ktv_fx_drop_a", "KTV-Muster Drop A", "Beim Drop: wechselt auf jeden Schlag mit Drop B. Kanal 15 des KTV in der Szene Laser bei \"Light-Butler steuert\". Mit dem DMX-Debugger findest du schoene Werte (Kanal 315), je 2 Werte ein Effekt. Hoechstens 244, darueber laufen Selbstlauf und Sound.",
      46.0, 0.0, 244.0, 1.0, ""),
    P(G_LASER, "ktv_fx_drop_b", "KTV-Muster Drop B", "Beim Drop: wechselt auf jeden Schlag mit Drop A. Kanal 15 des KTV in der Szene Laser bei \"Light-Butler steuert\". Mit dem DMX-Debugger findest du schoene Werte (Kanal 315), je 2 Werte ein Effekt. Hoechstens 244, darueber laufen Selbstlauf und Sound.",
      35.0, 0.0, 244.0, 1.0, ""),
    P(G_LASER, "ktv_fx_break", "KTV-Muster Break", "Im Break, die ruhige Linie. Kanal 15 des KTV in der Szene Laser bei \"Light-Butler steuert\". Mit dem DMX-Debugger findest du schoene Werte (Kanal 315), je 2 Werte ein Effekt. Hoechstens 244, darueber laufen Selbstlauf und Sound.",
      46.0, 0.0, 244.0, 1.0, ""),
    P(G_LASER, "ktv_auto_speed", "KTV-Laser: Auto-Geschwindigkeit", "Gilt nur im 6-Kanal-Modus des KTV (Reserve), im 34-Kanal-Modus ohne Wirkung. Wert fuer Kanal 6 des KTV-Lasers im Auto-Modus (laut Notiz: 0 = schnell, 1 bis 127 Geschwindigkeit). Bitte ausprobieren, in welche Richtung er schneller wird.",
      40.0, 0.0, 127.0, 1.0, ""),
    # ---- Ambiente ---------------------------------------------------------------------------
    P(G_AMB, "amb_tc", "Ambiente: Traegheit", "Wie traege die Ambiente-Lichter (Theke, Couchtisch) der Lautstaerke folgen.",
      4.0, 0.5, 20.0, 0.5, "s"),
    P(G_AMB, "uv_base", "UV-Leiste: Grundhelligkeit", "So hell leuchtet die UV-Leiste im AUTO-Modus mindestens, solange Musik laeuft, die Musik pulst obendrauf. 0 = aus: Sie pulst nur nach der Musik und ist dazwischen dunkel. Der Regler UV-Leiste und der General Dimmer wirken darauf, bei Stille, im Aufbau und beim Stil Weihnachten bleibt sie wie gehabt.",
      0.0, 0.0, 100.0, 1.0, "%"),
    P(G_AMB, "amb_idle", "Ambiente: Grundhelligkeit", "Theke, Couchtisch und Barlicht (Gruppe ambient) leuchten nie dunkler als das, auch in Stille und Pausen. Sie blinken nie mit; beim Strobe gehen sie fuer den Kontrast aus. 0 = Ambiente darf ganz dunkel werden.",
      0.25, 0.0, 0.6, 0.05, ""),
]


class Settings:
    def __init__(self, path="settings.json"):
        self.defs = {d.key: d for d in DEFS}
        self.v = {d.key: d.default for d in DEFS}
        self.path = path
        self.saved = set()
        self.lock = threading.Lock()
        self.load()

    def __getitem__(self, key):
        return self.v[key]

    # ---- Werte aendern ------------------------------------------------------------------------
    def _clamp(self, d, val):
        val = max(d.lo, min(d.hi, float(val)))
        if d.step >= 1.0 and float(d.step).is_integer():
            val = float(round(val))
        else:
            val = round(round(val / d.step) * d.step, 6)
        return max(d.lo, min(d.hi, val))

    def set(self, key, val):
        d = self.defs.get(key)
        if d is None:
            raise KeyError(f"unbekannte Einstellung {key}")
        with self.lock:
            self.v[key] = self._clamp(d, val)
            self.saved.add(key) if self.v[key] != d.default else self.saved.discard(key)
        self.save()

    def seed(self, key, val):
        """Startwert aus der Kommandozeile uebernehmen, solange nichts Gespeichertes dagegen spricht."""
        d = self.defs.get(key)
        if d is not None and key not in self.saved:
            self.v[key] = self._clamp(d, val)

    def reset(self, key=None):
        with self.lock:
            for k in ([key] if key else list(self.v)):
                if k in self.defs:
                    self.v[k] = self.defs[k].default
                    self.saved.discard(k)
        self.save()

    # ---- Speichern / Laden --------------------------------------------------------------------
    def load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            for k, val in data.items():
                d = self.defs.get(k)
                if d is not None:
                    self.v[k] = self._clamp(d, val)
                    if self.v[k] != d.default:
                        self.saved.add(k)
        except (OSError, ValueError, TypeError):
            pass

    def save(self):
        if not self.path:
            return
        data = {k: self.v[k] for k in self.saved}
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ---- Fuer das Panel -----------------------------------------------------------------------
    def info(self):
        groups, order = {}, []
        for d in DEFS:
            if d.group not in groups:
                groups[d.group] = []
                order.append(d.group)
            groups[d.group].append({"key": d.key, "label": d.label, "desc": d.desc, "value": self.v[d.key],
                                    "default": d.default, "lo": d.lo, "hi": d.hi, "step": d.step, "unit": d.unit,
                                    "mod": self.v[d.key] != d.default})
        return [{"group": g, "items": groups[g]} for g in order]
