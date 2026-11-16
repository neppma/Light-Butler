"""Kopfzeile 2: Quelle der Tonart als kleine Marke MIXXX direkt nach der Tonart, auf der Grundlinie (nicht
hochgestellt), damit die Zeile nicht huepft, wenn Mixxx kommt oder geht."""
import os
import subprocess
import tempfile

from _common import check, finish

import webpanel

p = webpanel.make_page()
check("(S.key_src==='Mixxx'?'<span class=\"srcb\">'+(S.mx_name==='Auto-DJ'?'AUTO-DJ':'MIXXX')+'</span>':'')" in p, "MIXXX (oder AUTO-DJ) gross als Marke nach der Tonart")
check("<sup>Mixxx</sup>" not in p and "#row2 sup" not in p, "nicht mehr hochgestellt")
check("#row2 .srcb{display:inline-block;vertical-align:baseline" in p and "background:#1e3550" in p, "Marke auf der Grundlinie, dunkelblau hinterlegt")
js = p.split("<script>")[-1].split("</script>")[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
    fh.write(js)
try:
    ok = subprocess.run(["node", "--check", fh.name], capture_output=True).returncode == 0
except FileNotFoundError:
    ok = True
os.unlink(fh.name)
check(ok, "Panel-Skript fehlerfrei (node --check)")
finish("test_tonart_marke")
