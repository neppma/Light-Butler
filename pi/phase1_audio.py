#!/usr/bin/env python3
"""
Phase 1: Audio-Analyse mit Konsolenanzeige und CPU-Messung (Raspberry Pi 4).

Zeigt live: Pegel (RMS), Bass/Mid/High, Beat, BPM, CPU-Last, Temperatur.
Es wird noch kein Licht gesteuert.

Start:
    python3 phase1_audio.py --list            # Audiogeraete anzeigen
    python3 phase1_audio.py --device 1        # Analyse starten
    python3 phase1_audio.py --device 1 --duration 60   # 60 s Messung, dann Zusammenfassung
"""
import argparse
import queue
import sys
import time

import numpy as np
import sounddevice as sd

try:
    import aubio
except ImportError:
    aubio = None
try:
    import psutil
except ImportError:
    psutil = None

WIN = 1024  # FFT-Fenster (Samples)
BANDS = {"bass": (20, 150), "mid": (150, 2000), "high": (2000, 12000)}


def cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read()) / 1000.0
    except Exception:
        return None


class AutoGain:
    """Normiert einen Wert auf 0..1 relativ zu einem langsam abfallenden Spitzenwert.
    Macht die Analyse unabhaengig von der Fader-Stellung am Mischpult."""

    def __init__(self, decay_s, rate_hz, floor=1e-4):
        self.peak = floor
        self.floor = floor
        self.k = 0.5 ** (1.0 / (decay_s * rate_hz))  # Halbwertszeit = decay_s

    def __call__(self, x):
        self.peak = max(x, self.peak * self.k, self.floor)
        return min(x / self.peak, 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="Audiogeraete auflisten")
    ap.add_argument("--device", type=int, default=None, help="Geraete-Nummer")
    ap.add_argument("--rate", type=int, default=44100)
    ap.add_argument("--hop", type=int, default=512, help="Blockgroesse in Samples")
    ap.add_argument("--channel", type=int, default=-1,
                    help="-1 = L+R mischen, 0 = links, 1 = rechts")
    ap.add_argument("--duration", type=float, default=0, help="Sekunden, 0 = endlos")
    args = ap.parse_args()

    if args.list:
        print(sd.query_devices())
        return
    if aubio is None:
        sys.exit("aubio fehlt (siehe Installationsanleitung).")

    dev_info = sd.query_devices(args.device, "input")
    n_ch = min(2, dev_info["max_input_channels"])
    hop, rate = args.hop, args.rate
    block_rate = rate / hop

    tempo = aubio.tempo("default", WIN, hop, rate)
    tempo.set_silence(-50)

    window = np.hanning(WIN).astype(np.float32)
    freqs = np.fft.rfftfreq(WIN, 1.0 / rate)
    masks = {k: (freqs >= lo) & (freqs < hi) for k, (lo, hi) in BANDS.items()}
    gains = {k: AutoGain(8.0, block_rate) for k in BANDS}
    gain_rms = AutoGain(8.0, block_rate)

    q = queue.Queue(maxsize=200)
    stats = {"overflow": 0, "dropped": 0}

    def callback(indata, frames, time_info, status):
        if status:
            stats["overflow"] += 1
        try:
            q.put_nowait(indata.copy())
        except queue.Full:
            stats["dropped"] += 1

    proc = psutil.Process() if psutil else None
    if proc:
        proc.cpu_percent(None)

    ring = np.zeros(WIN, dtype=np.float32)
    beat_hold = 0
    last_print = 0.0
    proc_times = []
    cpu_samples = []
    t_start = time.time()

    print(f"Geraet: {dev_info['name']} | {rate} Hz | Block {hop} | Kanaele {n_ch}")
    print("Strg+C beendet.\n")

    try:
        with sd.InputStream(device=args.device, channels=n_ch, samplerate=rate,
                            blocksize=hop, dtype="float32", callback=callback):
            while True:
                if args.duration and time.time() - t_start > args.duration:
                    break
                try:
                    block = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                t0 = time.perf_counter()

                if n_ch == 1 or args.channel >= 0:
                    mono = block[:, min(max(args.channel, 0), n_ch - 1)]
                else:
                    mono = block.mean(axis=1)
                mono = np.ascontiguousarray(mono, dtype=np.float32)

                # Beat
                is_beat = bool(tempo(mono)[0])
                if is_beat:
                    beat_hold = 10          # ca. 115 ms Anzeige pro Beat
                elif beat_hold > 0:
                    beat_hold -= 1

                # Pegel + Baender
                rms = float(np.sqrt(np.mean(mono ** 2)))
                ring = np.roll(ring, -hop)
                ring[-hop:] = mono
                spec = np.abs(np.fft.rfft(ring * window)) / WIN
                bands = {k: gains[k](float(spec[m].mean())) for k, m in masks.items()}
                level = gain_rms(rms)

                proc_times.append(time.perf_counter() - t0)

                now = time.time()
                if now - last_print >= 0.1:
                    last_print = now
                    cpu = proc.cpu_percent(None) if proc else float("nan")
                    if proc:
                        cpu_samples.append(cpu)
                    temp = cpu_temp()
                    bar = lambda v: ("#" * int(v * 12)).ljust(12)
                    sys.stdout.write(
                        f"\rLvl [{bar(level)}] B [{bar(bands['bass'])}] "
                        f"M [{bar(bands['mid'])}] H [{bar(bands['high'])}] "
                        f"{'BEAT' if beat_hold > 0 else '    '} "
                        f"{tempo.get_bpm():5.1f} BPM | CPU {cpu:4.0f}% "
                        f"| {temp if temp else 0:4.1f}C | Q {q.qsize():3d} "
                        f"| ovf {stats['overflow']} drop {stats['dropped']}  ")
                    sys.stdout.flush()
    except KeyboardInterrupt:
        pass

    print("\n\n--- Zusammenfassung ---")
    if proc_times:
        pt = np.array(proc_times) * 1000
        budget = 1000.0 * hop / rate
        print(f"Rechenzeit pro Block: mittel {pt.mean():.2f} ms, "
              f"max {pt.max():.2f} ms (Budget {budget:.1f} ms)")
    if cpu_samples:
        print(f"CPU-Last des Prozesses (100% = 1 Kern): mittel {np.mean(cpu_samples):.0f}%, "
              f"max {np.max(cpu_samples):.0f}%")
    print(f"Audio-Overflows: {stats['overflow']}, verworfene Bloecke: {stats['dropped']}")
    print(f"Letztes BPM: {tempo.get_bpm():.1f}")


if __name__ == "__main__":
    main()
