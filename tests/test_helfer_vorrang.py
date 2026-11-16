"""Helfer hat Vorrang (Wunsch von Markus, 08.11.2026): alles, was Mixxx nicht braucht (Liedliste, Vorhoeren, Analyse, Auto-Tagger,
Ordner-Liste, Kurven-Sicherung), macht der Light-Butler Helfer. Die Mixxx-Bruecke liest dann nur Mixxx mit und uebernimmt erst,
wenn der Helfer 30 s weg ist; kommt er wieder, gibt sie ab."""
import argparse
import os
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import mixxx_bridge as mb  # noqa: E402

tmp = tempfile.mkdtemp(prefix="s2l_vorrang_")
up = {"v": True}
mb._helper_up = lambda: up["v"]
args = argparse.Namespace(send=None, pi_port=9020, analysis_dir=os.path.join(tmp, "a"), no_analyze=False, path_map=[],
                          music_root=tmp, no_folder_lib=False, no_music_serve=False, monitor=False, energy_est=False,
                          yield_to_helper=True, background_analysis=False)
lib = [{"id": 1, "artist": "A", "title": "Eins", "duration": 200.0, "bpm": 120.0, "kid": 1, "path": os.path.join(tmp, "a.mp3")}]
fw = mb.make_forwarder(args, lib, None)
check(fw.lib_off and fw.folder is None and fw.music is None, "Helfer laeuft beim Start: die Bruecke macht keine Liste, kein Vorhoeren")
sent = []
fw._send = lambda n, m: sent.append(m)
fw.lib_chunks = []
fw.tick()
check(not any(m.get("type") in ("lib", "libhash", "genres", "stats") for m in sent),
      "die Bruecke schickt dann nichts zur Bibliothek (kein Durcheinander mit dem Helfer)")

up["v"] = False
fw.role_t = 0.0                                # tick() oben lief mit der echten Uhr
fw.lib_role_tick(100.0)
check(fw.lib_off, "Helfer gerade weg: noch nicht uebernehmen")
fw.lib_role_tick(115.0)
check(fw.lib_off, "erst nach 30 s")
fw.lib_role_tick(131.0)
check(not fw.lib_off and fw.folder is not None, "Helfer 30 s weg: die Bruecke uebernimmt (Ordner-Liste laeuft)")

up["v"] = True
fw.lib_role_tick(145.0)
check(fw.lib_off and fw.folder is None and fw.music is None, "Helfer wieder da: die Bruecke gibt ab")

# Helfer selbst (ohne yield_to_helper) und alte Aufrufe: immer alles
args2 = argparse.Namespace(**dict(vars(args), yield_to_helper=False))
fw2 = mb.make_forwarder(args2, lib, None)
check(not fw2.lib_off and fw2.folder is not None, "im Helfer selbst: immer der Bibliotheks-Teil")
fw2.lib_role_tick(1000.0)
check(not fw2.lib_off, "der Helfer gibt nie an sich selbst ab")
src = open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read()
check('dest="yield_to_helper", action="store_false", default=True' in src, "die Bruecke gibt standardmaessig ab (--alles-selbst schaltet das aus)")
check(src.count('and not fw.lib_off:') == 2, "Hintergrund-Analyse startet in der Bruecke nur ohne Helfer")
import auto_tag  # noqa: E402
at = auto_tag.AutoTagger(lambda: [], base=os.path.join(tmp, "at"))
at.start()
at.pause()
check(at.on and getattr(at, "paused", False), "Auto-Tagger anhalten beim Abgeben, ohne sich 'aus' zu merken")
finish("test_helfer_vorrang")
