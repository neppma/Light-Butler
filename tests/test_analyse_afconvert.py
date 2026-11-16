"""Analyse am Mac: Dateien, an denen soundfile scheitert (AAC/m4a, manche MP3 mitten im Lied), liest decode_audio mit
afconvert aus macOS. Kann gar nichts die Datei lesen, nennt die Meldung die Datei statt "soundfile fehlt"."""
import os
import shutil
import subprocess
import sys
import tempfile

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
try:
    import numpy as np
    import scipy  # noqa: F401
    import analyze_track as at
except ImportError:
    at = None

if at is None or not shutil.which("afconvert"):
    check(True, "kein Mac mit afconvert oder ohne scipy: Test uebersprungen")
    finish("test_analyse_afconvert")
    sys.exit(0)

from scipy.io import wavfile    # noqa: E402

d = tempfile.mkdtemp()
t = np.arange(44100 * 3) / 44100.0
sig = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
wav, m4a = os.path.join(d, "ton.wav"), os.path.join(d, "Fröhliche Weihnacht Überall.m4a")
wavfile.write(wav, 44100, np.stack([sig, sig], axis=1))
subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", wav, m4a], check=True, capture_output=True)

x = at.decode_audio(m4a)
check(abs(len(x) / at.SR - 3.0) < 0.1, f"AAC mit Umlauten im Namen gelesen ({len(x) / at.SR:.2f} s)")
check(0.3 < float(np.abs(x).max()) < 0.7, "Pegel stimmt (Sinus 0,5)")

y = at.decode_afconvert(b"kein Audio", ".mp3")
check(y is None, "unlesbare Daten: None statt Absturz")

bad = os.path.join(d, "kaputt.mp4")
with open(bad, "wb") as f:
    f.write(b"\0" * 5000)
old = os.environ.get("PATH", "")
os.environ["PATH"] = "/usr/bin:/bin"                         # ohne Homebrew: kein ffmpeg
try:
    msg = ""
    try:
        at.decode_audio(bad)
    except RuntimeError as e:
        msg = str(e)
    if shutil.which("ffmpeg"):
        check(True, "ffmpeg im System: Meldung nicht pruefbar")
    else:
        check("kaputt.mp4" in msg and "nicht lesbar" in msg, "Meldung nennt die Datei")
finally:
    os.environ["PATH"] = old
shutil.rmtree(d, ignore_errors=True)
finish("test_analyse_afconvert")
