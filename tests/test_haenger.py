"""Spuerhund fuer Haenger auf der Seite Zustand (Fehlersuche 06.11.2026): findet die Stelle, die Python blockiert, und misst
die langsamsten Anfragen. Nur Messung, wirkt nicht aufs Licht."""
import os
import threading
import time

from _common import PI, check, finish

import health

sw = health.StallWatch(period=0.01, limit=0.03, here=PI)
stop = threading.Event()
t = threading.Thread(target=sw.run, args=(stop,), daemon=True)
t.start()
time.sleep(0.05)


def blockiert_lange():
    """Haelt Python am Stueck fest wie json.dumps ueber 9000 Lieder (eine C-Schleife ohne Pause)."""
    return sum(range(60_000_000))


def schuldiger():
    blockiert_lange()
    time.sleep(0.3)                                     # danach noch in der Funktion: hier sieht ihn der Spuerhund


w = threading.Thread(target=schuldiger, name="bibliothek", daemon=True)
w.start()
w.join()
time.sleep(0.05)
stop.set()
rep = sw.report(time.monotonic())
check(rep["n"] >= 1 and rep["max_ms"] >= 30, "Haenger erkannt: %s" % rep)
check(any(x["where"].startswith("bibliothek@") and ("test_haenger.py:schuldiger" in x["where"] or "test_haenger.py:blockiert_lange" in x["where"]) for x in rep["top"]),
      "Schuldiger mit Fadenname und Funktion gefunden: %s" % rep["top"][:3])
check(not any("haenger-spuerhund" in x["where"] or "health.py" in x["where"] for x in rep["top"]), "der Spuerhund zeigt nicht auf sich selbst")
check(sw.report(time.monotonic() + 120)["n"] == 0, "nach einer Minute vergessen")

rs = health.ReqStats()
rs.note("/api/musik", 1.7, 100.0)
rs.note("/api/sm/cmd stems_bulk_status", 0.09, 101.0)
rs.note("/api/sm/cmd stems_bulk_status", 0.12, 102.0)
r = rs.report(103.0)
check(r[0] == {"what": "/api/musik", "n": 1, "max_ms": 1700.0, "sum_ms": 1700} and r[1]["what"] == "/api/sm/cmd stems_bulk_status" and r[1]["n"] == 2,
      "langsamste Anfragen der letzten Minute, mit Befehl")
check(rs.report(200.0) == [], "nach einer Minute vergessen")

src = open(os.path.join(PI, "webpanel.py"), encoding="utf-8").read()
check("threading.Thread(target=hl.stall.run" in src and "hl.reqs.note(" in src and 'not path.endswith("/ws")' in src,
      "Panel startet den Spuerhund und misst jede Anfrage (ohne WebSocket)")
hsrc = open(os.path.join(PI, "health.py"), encoding="utf-8").read()
check('"stalls": self.stall.report(now), "slow_req": self.reqs.report(now)' in hsrc, "Seite Zustand liefert beides mit (/api/health)")
finish("test_haenger")
