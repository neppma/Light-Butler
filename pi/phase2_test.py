#!/usr/bin/env python3
"""
Phase 2: Testprogramm fuer Art-Net, Fixture-Mapping und Sicherheitslogik.
Noch ohne Audio.

    python3 phase2_test.py --check                 # YAML pruefen (Adressen, Kanaele)
    python3 phase2_test.py --list                  # Fixtures anzeigen
    python3 phase2_test.py --dry-run --test        # Trockenlauf ohne Netzwerk
    python3 phase2_test.py --test --fixture docooler_1
    python3 phase2_test.py --test --group wash --hold 2
    python3 phase2_test.py --chase --bpm 120 --seconds 30
    python3 phase2_test.py --blackout              # alles dunkel senden
    python3 phase2_test.py --move-test --fixture vega      # Vega langsam an die Eckpunkte
    python3 phase2_test.py --move-test --fixture docooler_1
    python3 phase2_test.py --move-test --fixture docooler_1 --jump   # Motorgeschwindigkeit pruefen

Strg+C beendet jeden Test mit Blackout.
Laser, Hazer und gesperrte Kanaele bleiben IMMER auf 0 (siehe dmx.py).
"""
import argparse
import sys
import time

from dmx import ArtNetSender, Output, PrintSender, Rig, slew

COLORS = [("ROT", dict(r=255)), ("GRUEN", dict(g=255)), ("BLAU", dict(b=255)),
          ("WEISS", dict(w=255)), ("UV", dict(uv=255))]


def wait(sec):
    time.sleep(sec)


def test_fixture(rig, fx, hold):
    print(f"\n== {fx.name} ({fx.type}, Adresse {fx.address}, Gruppe {fx.group})")
    if fx.locked:
        print("   gesperrt (Laser/Hazer): sendet nur 0, nichts zu testen")
        return
    if fx.type == "vega_spot_60":
        test_vega(rig, fx, hold)
        return
    if "preset" in fx.map:
        ids = fx.extra.get("preset_list", [])
        with rig.lock:
            fx.set("dimmer", 255)
        if not ids:
            print("   keine preset_list in der YAML: sende nur Helligkeit 255, Preset 0")
            wait(hold)
        for pid in ids:
            with rig.lock:
                fx.set("preset", pid)
            name = fx.extra.get("preset_names", {}).get(pid, "")
            print(f"   Preset {pid} {name}")
            wait(hold)
        with rig.lock:
            fx.set("preset", 0)
            fx.blackout()
        return
    zones = fx.zones()
    if not zones:
        print("   keine Farbzonen")
        return
    for zi, z in enumerate(zones):
        for label, kw in COLORS:
            key = next(iter(kw))
            if key not in z:
                continue
            with rig.lock:
                fx.blackout()
                fx.set_zone(zi, **kw)
            print(f"   Zone {zi + 1}: {label}")
            wait(hold)
        with rig.lock:
            fx.blackout()


def test_vega(rig, fx, hold):
    print("   Pan/Tilt bleiben fest. Shutter offen (255), Dimmer 255.")
    with rig.lock:
        fx.set("dimmer", 255)
        fx.set("shutter", 255)
    for name in fx.presets.get("colorwheel", {}):
        with rig.lock:
            fx.preset("colorwheel", name)
        print(f"   Farbrad: {name}")
        wait(hold)
    with rig.lock:
        fx.preset("colorwheel", "white")
    for name in fx.presets.get("gobo", {}):
        with rig.lock:
            fx.preset("gobo", name)
        print(f"   Gobo: {name}")
        wait(hold)
    with rig.lock:
        fx.preset("gobo", "open")
        fx.blackout()


def goto(rig, fx, targets, rate):
    """Faehrt Positionen {param: wert16 oder wert8} langsam an. Rate in DMX-Einheiten/s."""
    cur = {k: float(v) for k, v in fx.__dict__.setdefault("_mt", {}).items()}
    for k, v in targets.items():
        cur.setdefault(k, float(v[1]))
    while True:
        done = True
        for k, (scale, tgt) in targets.items():
            cur[k] = slew(cur[k], tgt, rate * scale, 0.025)
            done = done and abs(cur[k] - tgt) < 0.5
            c = int(cur[k])
            with rig.lock:
                if scale == 256:
                    fx.set(k, c >> 8)
                    fx.set(k + "_fine", c & 255)
                else:
                    fx.set(k, c)
        fx._mt = cur
        if done:
            return
        wait(0.025)


def move_test(rig, name, hold, rate=15.0, jump=False):
    fx = rig[name]
    hold = max(hold, 3.0)
    if fx.move16:
        lo_p, hi_p = fx.move16["pan"]
        lo_t, hi_t = fx.move16["tilt"]
        print(f"== {fx.name}: erlaubter Bereich Pan {lo_p >> 8}..{hi_p >> 8}, Tilt {lo_t >> 8}..{hi_t >> 8}")
        print("   Annahme: horizontal = Pan (links -> rechts), vertikal = Tilt (oben -> unten) wie im")
        print("   Raster. Achte darauf, wohin der Strahl zeigt und ob er in den erlaubten")
        print("   Raum bleibt. Falls gespiegelt: pan_invert / tilt_invert in der YAML umstellen.")
        with rig.lock:
            fx.set("dimmer", 150)
            fx.set("shutter", 255)
            fx.preset("colorwheel", "white")
            fx.set("pt_speed", 0)
        pts = [("Mitte", 0.5, 0.5), ("links-oben", 0.0, 0.0), ("rechts-oben", 1.0, 0.0),
               ("rechts-unten", 1.0, 1.0), ("links-unten", 0.0, 1.0), ("Mitte", 0.5, 0.5)]
        for label, u, v in pts:
            uu = 1.0 - u if fx.mirror["pan"] else u
            vv = 1.0 - v if fx.mirror["tilt"] else v
            tp = lo_p + uu * (hi_p - lo_p)
            tt = lo_t + vv * (hi_t - lo_t)
            print(f"   -> {label:12s} Pan {tp / 256:5.1f}  Tilt {tt / 256:5.1f}")
            goto(rig, fx, {"pan": (256, tp), "tilt": (256, tt)}, rate=8.0)
            wait(hold)
        with rig.lock:
            fx.blackout()
    elif "tilt1" in fx.map:
        lo, hi = fx.limits["tilt1"]
        print(f"== {fx.name}: Tilt-Test, erlaubter Bereich {lo}..{hi} (0..255 = 0..270 Grad)")
        same = fx.extra.get("tilt_mode", "opposite") == "same"
        print("   Es leuchten nur die weissen LEDs (W). Beobachte beide Haelften (Zelle 1 / Zelle 2).")
        print(f"   tilt_mode in der YAML: {'same' if same else 'opposite'} "
              "(same = gleiche DMX-Werte ergeben in Wirklichkeit den Faecher).")
        with rig.lock:
            fx.set("dimmer", 255)
            for zi in range(len(fx.zones())):
                fx.set_zone(zi, w=200)
        fan = [(hi, hi), (lo, lo)] if same else [(hi, lo), (lo, hi)]
        par = [(hi, lo), (lo, hi)] if same else [(hi, hi), (lo, lo)]
        steps = [("Mitte", 127, 127),
                 ("FAECHER 1" + (": Balken kippen ZUSAMMEN (beobachtet)" if same else ""), *fan[0]),
                 ("FAECHER 2" + (": Balken kippen AUSEINANDER (beobachtet)" if same else ""), *fan[1]),
                 ("Mitte", 127, 127),
                 ("PARALLEL 1 (beide Balken bleiben parallel)", *par[0]),
                 ("PARALLEL 2", *par[1]),
                 ("Mitte", 127, 127)]
        if jump:
            print("   SPRUNGTEST: die Balken bekommen Befehle OHNE Verzoegerung (Faecher zusammen <-> auseinander).")
            print("   Beobachte, wie lange sie bis zur Endlage brauchen (Stoppuhr/Video). Je 3 Spruenge.")
            steps = [("Mitte", 127, 127)]
            for _ in range(3):
                steps += [("SPRUNG zusammen", *fan[0]), ("SPRUNG auseinander", *fan[1])]
            steps.append(("Mitte", 127, 127))
            rate = 1000.0
            hold = 2.5
        for label, a, b in steps:
            print(f"   -> {label}: Tilt1 {a}, Tilt2 {b}")
            goto(rig, fx, {"tilt1": (1, a), "tilt2": (1, b)}, rate=rate)
            wait(hold)
        with rig.lock:
            fx.blackout()
    else:
        print(f"{fx.name}: kein beweglicher Teil")


def chase(rig, bpm, seconds):
    """Einfacher Lauflicht-Test mit festem Tempo (kein Audio)."""
    palette = [(255, 0, 0), (255, 120, 0), (0, 255, 0), (0, 120, 255), (160, 0, 255)]
    lights = [f for f in rig.fixtures if not f.locked and f.zones()
              and f.group in ("bars", "wash", "uv", "fx")]
    period = 60.0 / bpm
    t0, step = time.time(), 0
    print(f"Chase mit {bpm} BPM ueber {len(lights)} Fixtures. Strg+C beendet.")
    while seconds <= 0 or time.time() - t0 < seconds:
        col = palette[(step // len(lights)) % len(palette)]
        with rig.lock:
            for f in lights:
                f.blackout()
            f = lights[step % len(lights)]
            if "uv1" in f.map:
                f.set_color(uv=255)
            else:
                f.set_color(*col)
        step += 1
        wait(period)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="fixtures.yaml")
    ap.add_argument("--target", help="Ziel-IP ueberschreiben")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="kein Netzwerk, nur Ausgabe")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--chase", action="store_true")
    ap.add_argument("--blackout", action="store_true")
    ap.add_argument("--move-test", action="store_true", help="Bewegungstest (langsam, innerhalb der Limits)")
    ap.add_argument("--rate", type=float, default=15.0, help="Move-Test: Geschwindigkeit in DMX-Einheiten/s")
    ap.add_argument("--jump", action="store_true", help="Move-Test Docooler: Spruenge ohne Verzoegerung (misst die Motorgeschwindigkeit)")
    ap.add_argument("--group")
    ap.add_argument("--fixture")
    ap.add_argument("--hold", type=float, default=2.0, help="Sekunden pro Schritt")
    ap.add_argument("--bpm", type=float, default=120)
    ap.add_argument("--seconds", type=float, default=30)
    a = ap.parse_args()

    rig = Rig(a.config)

    if a.check or a.list:
        for f in rig.fixtures:
            print(f"{f.address:4d}-{f.address + f.n - 1:<4d} {f.name:<12s} "
                  f"{f.type:<18s} Gruppe {f.group:<8s} -> {f.target or rig.target}")
        problems = rig.check()
        print("\nPruefung:", "OK, keine Probleme" if not problems else "")
        for p in problems:
            print("  PROBLEM:", p)
        print(f"Universe {rig.universe}, Ziel {a.target or rig.target}")
        return 1 if problems else 0

    if not (a.test or a.chase or a.blackout or a.move_test):
        ap.print_help()
        return 0

    if a.target:
        rig.target = a.target
    from dmx import make_sender as _mk
    out = Output(rig, lambda ip: _mk(rig, ip, a.dry_run))
    print(f"Sende {'(Trockenlauf) ' if a.dry_run else ''}an {', '.join(rig.targets())}"
          f", Universe {rig.universe}. Alles startet dunkel.")
    out.start()
    try:
        if a.blackout:
            wait(1)
        elif a.chase:
            chase(rig, a.bpm, a.seconds)
        elif a.move_test:
            move_test(rig, a.fixture or "vega", a.hold, a.rate, a.jump)
        elif a.test:
            if a.fixture:
                targets = [rig[a.fixture]]
            elif a.group:
                targets = rig.group(a.group)
            else:
                targets = rig.fixtures
            for fx in targets:
                test_fixture(rig, fx, a.hold)
            print("\nTest fertig.")
    except KeyboardInterrupt:
        print("\nAbbruch, Blackout.")
    finally:
        out.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
