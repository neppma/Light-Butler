"""Energie langer Stuecke (Fehlerbericht von Markus, 14.11.2026: DJ-Mix "The Concourse Project", 134 Minuten, bekam E1): fuer
die Schaetzung zaehlt die Laenge hoechstens 15 Minuten; kuerzere Lieder bleiben genau gleich."""
import json
import os
import sys

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import energy_level as el  # noqa: E402

m = el.Model.from_json(json.load(open(os.path.join(ROOT, "mac", "mixxx_bridge", "energie_modell.json"), encoding="utf-8")))
F = {"mfcc_m0": 130.2659, "mfcc_m1": 45.4131, "mfcc_m2": 11.22, "mfcc_m3": 11.2623, "mfcc_m4": -3.2025, "mfcc_m5": 5.9885, "mfcc_m6": 0.238, "mfcc_m7": 4.658, "mfcc_m8": -2.3974, "mfcc_m9": 3.1693, "mfcc_m10": -0.6425, "mfcc_m11": 4.1686, "mfcc_m12": -1.0447, "mfcc_s0": 65.9221, "mfcc_s1": 28.6061, "mfcc_s2": 17.7987, "mfcc_s3": 10.3548, "mfcc_s4": 8.702, "mfcc_s5": 7.1808, "mfcc_s6": 6.3463, "mfcc_s7": 5.9005, "mfcc_s8": 5.1893, "mfcc_s9": 4.654, "mfcc_s10": 4.4408, "mfcc_s11": 4.2332, "mfcc_s12": 4.0534, "flat_mean": 0.0222, "rolloff": 930.4557, "zcr": 0.1105, "beat_reg": 0.2419, "low_pulse": 0.3749, "minor": 0.0, "loud_mean": 42.6906, "loud_p90": 50.5069, "loud_p10": 34.1338, "loud_std": 6.6078, "loud_frac": 0.4568, "bass_rel": -4.0302, "high_rel": -18.6885, "mid_rel": -8.7425, "sub_rel": -3.3987, "cent_mean": 550.0367, "cent_std": 642.5883, "flux_mean": 442.2364, "onset_rate": 2.4687, "pulse": 0.5852, "bpm": 0.0, "dur": 8051.9837, "dyn_range": 16.3731, "loud_peak": 52.4165, "hf_flux": 362.8051}            # Messwerte des Mixes (nur Zahlen)
row = lambda **kw: {"f": dict(F, **kw), "genre": ""}
check(el.DUR_CAP_S == 900.0, "Grenze 15 Minuten")
lv = m.predict([row()])[0]
check(lv >= 6, "134-Minuten-Mix: nicht mehr E1, sondern " + str(lv))
check(m.predict([row(dur=8000.0)])[0] == m.predict([row(dur=900.0)])[0], "laenger als 15 Minuten zaehlt wie 15 Minuten")
s1, s2 = m.score([row(dur=300.0)])[0], m.score([row(dur=899.0)])[0]
check(s1 != s2, "unter 15 Minuten wirkt die Laenge weiter wie bisher")
finish("test_energie_lange_mixe")
