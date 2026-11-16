"""Nachgebaute HomeMatic-CCU fuer die Tests (schaltet nie wirklich). Lesen wie ReGa (Skript, Antwort id;Wert;UNREACH),
Schalten wie XML-RPC setValue. getValue gibt es absichtlich nicht: es wuerde HmIP-Geraete per Funk abfragen."""
import re


class FakeCCU:
    def __init__(self):
        self.values, self.calls, self.down = {}, [], set()
        self.reads = 0                                     # Anzahl der ReGa-Aufrufe
        self.offline = False                               # ganze CCU nicht erreichbar
        self.channels = []                                 # Kanalliste fuer "Kanaele holen": (interface, address, typ, name)

    def rega(self, script):
        if self.offline:
            raise OSError("timeout")
        self.reads += 1
        if "ID_CHANNELS" in script:                        # Kanalliste wie WriteLine(f#";"#a#";"#t#";"#n)
            return "".join(f"{i};{a};{t};{n}\n" for i, a, t, n in self.channels) + "<xml><exec>/tester.exe</exec></xml>"
        out = []
        for line in script.splitlines()[1:]:
            dp, un = re.findall(r'dom.GetObject[(]"([^"]+)"[)]', line)
            dev_id = re.search(r'Write[(]"([a-z0-9_]+);"[)]', line).group(1)
            _, addr, key = dp.split(".")
            dev = addr.split(":")[0]
            v = self.values.get((dev, key), 0.0 if key == "LEVEL" else False)
            v = f"{v:.6f}" if key == "LEVEL" else ("true" if v else "false")
            out.append(f"{dev_id};{v};{'true' if dev in self.down else 'false'}")
        return "\n".join(out) + "\n<xml><exec>/tester.exe</exec></xml>"

    def proxy(self, interface):
        ccu = self

        class P:
            def setValue(self, addr, key, val):
                if addr.split(":")[0] in ccu.down:
                    raise OSError("unreach")
                ccu.calls.append((interface, addr, key, val))
                ccu.values[(addr.split(":")[0], key)] = val
        return P()
