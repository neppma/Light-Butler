"""Pfad-Helfer fuer Mac und Windows.

Am Mac/Linux sind alle Funktionen genau die alten Ausdruecke (Trenner "/").
Unter Windows werden Backslashes zu "/" (Windows nimmt beide), damit Vergleiche
wie startswith(root + "/") und rel.split("/") auch dort stimmen.
"""
import os
import sys

WIN = sys.platform == "win32"


def norm(p):
    """Windows: Backslash -> "/"; sonst unveraendert."""
    if WIN and isinstance(p, str):
        return p.replace("\\", "/")
    return p


def native(p):
    """Windows: Trenner wie im System (os.path.normpath); sonst unveraendert."""
    return os.path.normpath(p) if WIN and p else p


def under(p, root):
    """p liegt in root (nicht root selbst)."""
    return bool(root) and norm(p).startswith(norm(root) + "/")


def rel(p, root):
    """Relativer Pfad mit "/" wenn p in root liegt, sonst p."""
    return norm(p)[len(norm(root)) + 1:] if under(p, root) else p


def sibling(path, name):
    """Anderer Dateiname im selben Ordner; unter Windows bleibt die Schreibweise des Pfads (Trenner) erhalten."""
    if WIN:
        return path[:max(path.rfind("/"), path.rfind("\\")) + 1] + name
    return os.path.join(os.path.dirname(path), name)


def relpath(p, root):
    """os.path.relpath, immer mit "/"."""
    return norm(os.path.relpath(p, root))


DATA_NAME = "Light-Butler-Daten"        # gemeinsame Ablage von Mixxx-App und Helfer


def daten(home=None):
    """Datenordner von Helfer und Bruecke: S2L_DATA, sonst ~/Light-Butler-Daten."""
    env = os.environ.get("S2L_DATA")
    if env:
        return env
    return os.path.join(home or os.path.expanduser("~"), DATA_NAME)
