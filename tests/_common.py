"""Gemeinsame Hilfen fuer die Tests: Pfad zu pi/, Show ohne Hardware, Kanalwerte lesen."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.environ.get("S2L_DATA"):            # Mac-Teile legen ihre Daten sonst in ~/Light-Butler-Daten ab: Tests nie in die echte Ablage
    import tempfile as _tf
    os.environ["S2L_DATA"] = _tf.mkdtemp(prefix="s2l_daten_")
os.environ["S2L_NO_STEMS"] = "1"              # Tests starten nie den echten Pegelkurven-Waechter (Helfer)
PI = os.path.join(ROOT, "pi")
if PI not in sys.path:
    sys.path.insert(0, PI)
os.chdir(PI)            # Show und Rig suchen ihre Dateien relativ zum Arbeitsordner

import audio                                   # noqa: E402
from audio import Simulator                    # noqa: E402
from dmx import Rig                            # noqa: E402
import show as sw                              # noqa: E402

DT = 0.025                                     # ein Bild der Show


def ktv6_config():
    """Aufbau mit dem KTV im 6-Kanal-Modus (Adresse 181), falls am Geraet zurueckgestellt wird: temporaere fixtures.yaml."""
    import tempfile

    import yaml
    with open(os.path.join(PI, "fixtures.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    e = next(x for x in cfg["fixtures"] if x["name"] == "laser")
    e["type"], e["address"] = "laser_ktv", 181
    cfg["nanoleaf_file"] = ""
    path = os.path.join(tempfile.mkdtemp(prefix="s2l_ktv6_"), "fixtures.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    return path


def build(strobe=True, seed=1, source=None, mixxx=None, pilot=False, config=None):
    """Show mit nachgebauter Musik, ohne Netzwerk, ohne gespeicherte Dateien."""
    rig = Rig(config or os.path.join(PI, "fixtures.yaml"))
    rig["vega"].extra["limits_verified"] = True
    sh = sw.Show(rig, source or Simulator(), aim_file=os.devnull, strobe=strobe, settings_file=None,
                 scenes_file=None, mixxx=mixxx, texts_file=None, genre_file=None)
    sh._rng.seed(seed)
    sh.pilot = pilot                           # die meisten Tests bedienen von Hand
    return rig, sh


def zurueck(sh):
    """Alle Vorgaben weg wie mit AUTO, danach wieder von Hand bedienbar, ohne die Anzeige zu uebernehmen."""
    sh.command({"auto": True})
    sh.pilot = False


def ch(rig, name, param):
    f = rig[name]
    return rig.render_all()[f.target or rig.target][f.address - 1 + f.map[param] - 1]


class Clock:
    def __init__(self, sh, t0=1000.0):
        self.sh, self.t = sh, t0
        sh.update(t0)

    def run(self, sec, each=None):
        for _ in range(int(round(sec / DT))):
            self.t += DT
            self.sh.update(self.t)
            if each:
                each(self.t)


def check(cond, text):
    print(("  ok     " if cond else "  FEHLER ") + text)
    if not cond:
        check.failed += 1


check.failed = 0


def finish(name):
    if check.failed:
        print(f"{name}: {check.failed} Pruefung(en) fehlgeschlagen")
        sys.exit(1)
    print(f"{name}: alles in Ordnung")
