"""prio.py - Hintergrund-Prozesse mit niedriger Prioritaet (Analyse, Schaetzung, Messungen), damit Show und Panel
fluessig bleiben. Mac/Linux: os.nice wie bisher. Windows kennt os.nice nicht (15.11.2026): dort die Prozessklasse
"Niedriger als normal" (BELOW_NORMAL_PRIORITY_CLASS), ueber ctypes, ohne zusaetzliches Paket."""
import os
import sys

BELOW_NORMAL = 0x00004000


def lower_priority(nice=10, platform=None):
    """Den laufenden Prozess niedriger stellen. Fehler werden still uebergangen (die Arbeit geht trotzdem)."""
    if (platform or sys.platform) == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = wintypes.HANDLE          # 64 Bit: ohne Typen wird das Handle verfaelscht
            k32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            k32.SetPriorityClass.restype = wintypes.BOOL
            return bool(k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL))
        except (AttributeError, OSError):
            return False
    try:
        os.nice(nice)
        return True
    except (OSError, AttributeError):
        return False
