#!/usr/bin/env python3
"""
helper.py - "Light-Butler Helfer": APC mini mk2 und Ton vom MacBook an den Light-Butler (Pi), ganz ohne Mixxx.

  * APC am Mac: Tasten und Fader per UDP 9021 an den Pi, LED-Farben zurueck (apc_relay.py)
  * ROLI LUMI Keys am Mac: Noten per UDP 9023 an den Pi (apc_relay.lumi_relay)
  * Ton vom Mac: Kopie des Systemtons ueber BlackHole per UDP 9022 an den Pi, Eingang "Mac (Netzwerk)" (audio_send.py)
  * Internetradio (radio_play.py): Sender, den das Panel waehlt, spielen und per UDP 9022 an den Pi schicken (BlackHole ruht dann)
  * Liedliste ohne Mixxx (LibraryPart): Mixxx-Lieder aus der letzten Kopie der Datenbank (~/Light-Butler-Daten/mixxxdb.sqlite) und die
    MP3s im Musikordner (folder_lib.py) per UDP 9020 an die Musik-Datenbank am Pi, Vorhoeren auf Port 9025, Energie und
    Tonart schaetzen, Aufbau und Drops im Hintergrund analysieren. Derselbe Teil wie in der Mixxx-Bruecke (mixxx_bridge.Forwarder),
    nur ohne Decks. Laeuft die Bruecke (~/.light-butler-bruecke.pid), gibt der Helfer ihr diesen Teil binnen 2 s ab und
    nimmt ihn wieder auf, wenn sie endet.

Laeuft unsichtbar im Hintergrund (App "Light-Butler Helfer", auf Wunsch beim Anmelden). Solange er laeuft, steht seine
Prozessnummer in ~/.light-butler-helfer.pid; die Mixxx-Bruecke ueberlaesst ihm dann APC und Ton.

Aufruf:  python3 helper.py <Adresse des Pi>  [--no-apc] [--no-lumi] [--no-audio] [--no-library] [--no-analysis]
"""
import argparse
import os
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.join(HERE, "..", "mixxx_bridge")):    # installiert: alles in einem Ordner; im Projekt: Nachbarordner
    if p not in sys.path:
        sys.path.insert(0, p)

from apc_relay import HELPER_PID, ApcRelay, bridge_running, helper_running, lumi_relay   # noqa: E402
import pfad as _pfad                                   # Datenordner (~/Light-Butler-Daten)

S2L = _pfad.daten()   # Ordner der App "Light-Butler Mixxx" (Datenbank-Kopie,
                                                    # Analysen, config.sh); S2L_DATA wie im Rest des Helfers (Tests, Probelaeufe)
CHECK_S = 2.0                                      # so oft nachsehen, ob die Mixxx-Bruecke laeuft


def log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def claim(path=HELPER_PID):
    """Nur ein Helfer gleichzeitig. False, wenn schon einer laeuft."""
    if helper_running(path):
        return False
    with open(path, "w") as f:
        f.write(str(os.getpid()))
    return True


def release(path=HELPER_PID):
    try:
        with open(path) as f:
            mine = int(f.read().strip() or 0) == os.getpid()
        if mine:                                      # erst nach dem Schliessen loeschen (Windows: offene Datei geht nicht)
            os.remove(path)
    except (OSError, ValueError):
        pass


def config_value(name, path=os.path.join(S2L, "config.sh")):
    """Wert NAME="..." aus der config.sh der Mixxx-App (ohne sie auszufuehren), sonst ""."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep and k == name:
                    return v.strip().strip('"')
    except OSError:
        pass
    return ""


DB_CHECK_S = 60.0       # so oft schaut der Helfer, ob die Mixxx-App eine neue Kopie der Datenbank gemacht hat


class LibraryPart:
    """Liedliste, Vorhoeren, Schaetzung und Analyse ohne Mixxx: mixxx_bridge.make_forwarder mit leeren Decks.
    start()/stop() je nachdem, ob die Mixxx-Bruecke laeuft (update), tick() oft aufrufen (schickt die Liste in Stuecken)."""

    def __init__(self, pi, db=os.path.join(S2L, "mixxxdb.sqlite"), analysis_dir=os.path.join(S2L, "analysis"),
                 music_root="", background=True, pi_port=9020, music_port=9025, pi_web=8080, log=print,
                 bridge=bridge_running, make_sock=None):
        self.pi, self.db, self.dir, self.root = pi, db, analysis_dir, music_root
        self.background, self.pi_port, self.music_port, self.pi_web = background, pi_port, music_port, pi_web
        self.log, self.bridge = log, bridge
        self.make_sock = make_sock
        self.fw, self.sock, self.checked, self.yielded = None, None, -1e9, None
        self.db_mtime, self.db_checked = None, 0.0

    def args(self):
        return argparse.Namespace(send=self.pi, pi_port=self.pi_port, analysis_dir=self.dir, no_analyze=False,
                                  path_map=[], music_root=self.root, music_port=self.music_port, pi_web=self.pi_web,
                                  no_folder_lib=False, no_music_serve=False, monitor=False,
                                  db=self.db)   # daneben die Minuten-Kopie mixxxdb.live.sqlite (Abgleich Mixxx/Stick)

    def _db_mtime(self):
        try:
            return os.path.getmtime(self.db) if self.db else None
        except OSError:
            return None

    def start(self):
        import mixxx_bridge as mb
        self.db_mtime = self._db_mtime()
        import music_serve
        self.mx_off = music_serve.mixxx_off()                  # Betrieb ohne Mixxx (Einstellung am Pi): keine alte Datenbank-Kopie
        lib = mb.load_library(self.db, with_path=True) if self.db and os.path.isfile(self.db) and not self.mx_off else []
        if self.make_sock is not None:
            self.sock = self.make_sock()
        else:
            import socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.fw = mb.make_forwarder(self.args(), lib, self.sock)
        self.log(f"Liedliste ohne Mixxx: {len(lib)} Lieder aus der Mixxx-Datenbank" + ("" if lib else f" (keine Kopie in {self.db})")
                 + ", dazu der Musikordner")
        if self.background:
            self.fw.start_background()

    def stop(self):
        if self.fw is not None:
            self.fw.stop()
            self.fw = None
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def active(self):
        return self.fw is not None

    def update(self, now=None):
        """Der Helfer behaelt Liedliste, Vorhoeren und Analyse auch neben der Mixxx-Bruecke (Wunsch von Markus 08.11.2026: alles,
        was Mixxx nicht braucht, macht der Helfer; die Bruecke gibt ihm ab). Nicht gestartet: alle CHECK_S Sekunden versuchen."""
        now = time.time() if now is None else now
        if now - self.checked >= CHECK_S:
            self.checked = now
            if self.active() and now - self.db_checked >= DB_CHECK_S:
                self.db_checked = now
                mt = self._db_mtime()
                if mt is not None and self.db_mtime is not None and mt != self.db_mtime:
                    self.log("Neue Kopie der Mixxx-Datenbank (Mixxx-App gestartet): Liedliste neu laden")
                    self.stop()                            # gleich unten neu starten, mit den neuen Liedern und Kisten
                else:
                    import music_serve
                    if music_serve.mixxx_off() != getattr(self, "mx_off", False):
                        self.log("Einstellung Mixxx verwenden geaendert: Liedliste neu laden")
                        self.stop()
            if not self.active():
                try:
                    self.start()
                except Exception as e:                     # noqa: BLE001  z. B. Datenbank-Kopie defekt: in einer Minute wieder
                    self.stop()
                    self.checked = now + 60.0 - CHECK_S
                    self.log(f"Liedliste nicht gestartet: {str(e)[:120]}")
        if self.fw is not None:
            self.fw.tick()


class StemsPart:
    """Pegelkurven-Waechter (stems_show.py --watch --reserve) gehoert zum Helfer (Wunsch von Markus, 08.11.2026: alles, was Mixxx
    nicht braucht, macht standardmaessig der Helfer). Laeuft schon einer (von der Mixxx-App), startet er keinen zweiten und schaut
    jede Minute wieder: endet der andere mit der App, uebernimmt er."""
    CHECK_S = 60.0

    def __init__(self, pi, log=print, cmd=None, running=None, popen=None):
        self.pi, self.log = pi, log
        self.cmd = cmd if cmd is not None else self._cmd
        self.running = running if running is not None else self._running
        self.popen, self.proc, self.checked = popen, None, -1e9

    def _cmd(self):
        """Aufruf oder None (Pegelkurven am Mac nicht eingerichtet: ~/s2l-stems, stems/install_stems.sh)."""
        if os.environ.get("S2L_NO_STEMS"):                     # Tests
            return None
        py = os.path.expanduser("~/s2l-stems/bin/python")
        script = next((x for x in (os.path.join(HERE, "stems", "stems_show.py"), os.path.join(S2L, "stems", "stems_show.py"),
                                   os.path.join(HERE, "..", "stems", "stems_show.py")) if os.path.isfile(x)), "")
        if not (os.path.isfile(py) and os.access(py, os.X_OK) and script):
            return None
        return [py, script, "--watch", "--reserve", "--pi", self.pi]

    @staticmethod
    def _running():
        """Laeuft auf diesem Mac schon ein Waechter (zum Beispiel von der Mixxx-App)?"""
        import subprocess
        try:
            return subprocess.run(["pgrep", "-f", "stems_show.py --watch"], capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def update(self, now=None):
        now = time.time() if now is None else now
        if now - self.checked < self.CHECK_S:
            return
        self.checked = now
        if self.proc is not None and self.proc.poll() is None:
            return
        self.proc = None
        cmd = self.cmd()
        if not cmd or self.running():
            return
        try:
            if self.popen is not None:
                self.proc = self.popen(cmd)
            else:
                import subprocess
                logdir = os.path.expanduser("~/Library/Logs/Light-Butler")
                os.makedirs(logdir, exist_ok=True)
                with open(os.path.join(logdir, "stems.log"), "a") as lf:
                    self.proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            self.log("Pegelkurven-Waechter gestartet")
        except OSError as e:
            self.proc = None
            self.log(f"Pegelkurven-Waechter nicht gestartet: {e}")

    def stop(self):
        p, self.proc = self.proc, None
        if p is None or p.poll() is not None:
            return
        try:
            p.terminate()
            p.wait(5)
        except Exception:                                      # noqa: BLE001  haengt er: hart beenden
            try:
                p.kill()
            except OSError:
                pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="Light-Butler Helfer: APC, Ton und Liedliste vom Mac an den Pi")
    ap.add_argument("pi", help="Adresse des Pi, zum Beispiel lightbutler.local")
    ap.add_argument("--no-apc", action="store_true", help="APC mini mk2 nicht weiterleiten")
    ap.add_argument("--no-lumi", action="store_true", help="ROLI LUMI Keys nicht weiterleiten")
    ap.add_argument("--no-audio", action="store_true", help="Ton (BlackHole) nicht schicken")
    ap.add_argument("--audio-device", default=None, help="Teil des Namens des Ton-Eingangs (Standard: Mac BlackHole, Windows VB-Cable, Stereomix, Line-In)")
    ap.add_argument("--no-library", action="store_true", help="keine Liedliste, kein Vorhoeren, keine Schaetzung ohne Mixxx")
    ap.add_argument("--no-analysis", action="store_true", help="Aufbau und Drops nicht im Hintergrund analysieren")
    ap.add_argument("--no-stems", action="store_true", help="Pegelkurven-Waechter nicht starten")
    ap.add_argument("--no-radio", action="store_true", help="Internetradio nicht abspielen")
    ap.add_argument("--db", default=os.path.join(S2L, "mixxxdb.sqlite"), help="Kopie der Mixxx-Datenbank (von der App Light-Butler Mixxx)")
    ap.add_argument("--analysis-dir", default=os.path.join(S2L, "analysis"), help="Ordner der Analysen (wie die Mixxx-Bruecke)")
    ap.add_argument("--music-root", default=None, help="Musikordner (Reserve, der Ordner aus dem Panel geht vor; Standard MUSIC_ROOT aus config.sh)")
    ap.add_argument("--apc-port", type=int, default=9021)
    ap.add_argument("--lumi-port", type=int, default=9023)
    ap.add_argument("--audio-port", type=int, default=9022)
    a = ap.parse_args(argv)
    if not claim():
        log("Der Light-Butler Helfer laeuft schon, dieser Start wird beendet.")
        return 0
    parts, lib, stems = [], None, None
    try:
        if not a.no_apc:
            r = ApcRelay(a.pi, a.apc_port, log=log)
            if r.start():
                parts.append(r)
        if not a.no_lumi:
            r = lumi_relay(a.pi, a.lumi_port, log=log)
            if r.start():
                parts.append(r)
        radio = None
        if not a.no_radio:                                 # Internetradio (Seite /musik/radio): spielt und schickt den Ton selbst
            from radio_play import RadioPlayer
            radio = RadioPlayer(a.pi, port=a.audio_port, log=log)
            if radio.start():
                parts.append(radio)
        if not a.no_audio:
            from audio_send import AudioSender
            s = AudioSender(a.pi, a.audio_port, hint=a.audio_device, log=log,
                            mute=(radio.playing if radio is not None else None))
            if s.start():
                parts.append(s)
        if not a.no_library:
            root = a.music_root if a.music_root is not None else config_value("MUSIC_ROOT")
            lib = LibraryPart(a.pi, db=a.db, analysis_dir=a.analysis_dir, music_root=os.path.expanduser(root or ""),
                              background=not a.no_analysis and config_value("BACKGROUND_ANALYSIS") != "0", log=log)
        if not a.no_stems:
            stems = StemsPart(a.pi, log=log)
        names = [type(p).__name__ for p in parts] + (["LibraryPart"] if lib else []) + (["StemsPart"] if stems else [])
        log(f"Light-Butler Helfer laeuft ({', '.join(names) or 'nichts aktiv'}), Ziel {a.pi}")
        stop = []
        signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
        while not stop:
            if stems is not None:
                try:
                    stems.update()
                except Exception as e:                     # noqa: BLE001
                    log(f"Pegelkurven: {str(e)[:120]}")
            if lib is not None:
                try:
                    lib.update()
                except Exception as e:                     # noqa: BLE001  die Liedliste darf APC und Ton nie anhalten
                    log(f"Liedliste: {str(e)[:120]}")
            time.sleep(0.05 if lib is not None else 1.0)
    except KeyboardInterrupt:
        pass
    finally:
        if lib is not None:
            lib.stop()
        if stems is not None:
            stems.stop()
        for p in parts:
            p.stop()
        release()
        log("Light-Butler Helfer beendet")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Fehlerbericht 21.11.2026: ein in Core Audio haengender Ton-Faden hielt den Prozess nach "beendet" am Leben (PortAudio
    # raeumt beim normalen Ende auf und wartet dabei ewig). Der naechste Start hielt ihn fuer laufend und ging wieder aus.
    # Darum hart beenden, wenn alles aufgeraeumt und die Prozessdatei weg ist.
    os._exit(code or 0)
