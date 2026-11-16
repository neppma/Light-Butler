"""Vorhoer-Server am Mac (Fehlerbericht 08.11.2026): ist Port 9025 beim Start noch belegt (der Helfer gibt ihn gerade frei),
versucht die Bruecke es im Hintergrund weiter, statt ohne Vorhoeren zu laufen ("Mixxx-Bruecke laeuft nicht")."""
import json
import os
import socket
import sys
import time
import urllib.request

from _common import ROOT, check, finish

sys.path.insert(0, os.path.join(ROOT, "mac", "mixxx_bridge"))
import music_serve as ms  # noqa: E402

busy = socket.socket()
busy.bind(("0.0.0.0", 0))
busy.listen(1)
port = busy.getsockname()[1]
msgs = []
srv = ms.MusicServer([], port=port, log=msgs.append)
srv.RETRY_S = 0.2
check(srv.start(tries=1, retry_bg=True) is True and srv.srv is None, "Port belegt: True, Server folgt im Hintergrund")
time.sleep(0.5)
busy.close()                                   # der Helfer gibt den Port frei
for _ in range(50):
    if srv.srv is not None:
        break
    time.sleep(0.1)
check(srv.srv is not None, "danach laeuft der Server")
check(json.loads(urllib.request.urlopen("http://127.0.0.1:%d/ping" % port, timeout=5).read()).get("ok") is True, "und antwortet")
check(any("im Hintergrund" in m for m in msgs) and any("Port %d" % port in m and "fuer das Panel" in m for m in msgs), "Meldungen im Log")
srv.stop()

b2 = socket.socket()
b2.bind(("0.0.0.0", 0))
b2.listen(1)
s2 = ms.MusicServer([], port=b2.getsockname()[1])
check(s2.start(tries=1) is False, "ohne retry_bg wie bisher: False")
b2.close()
check("retry_bg=True" in open(os.path.join(ROOT, "mac", "mixxx_bridge", "mixxx_bridge.py"), encoding="utf-8").read(), "Bruecke nutzt es")
finish("test_vorhoeren_port")
