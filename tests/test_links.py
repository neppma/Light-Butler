"""Eigene Links zu Geraeten im Heimnetz (Wunsch von Markus 24.11.2026): in den Einstellungen Adresse, Port, Name; der Knopf
oeffnet die Seite in einem neuen Tab. Gespeichert in links.json, nur Adressen im eigenen Netz."""
import json
import os
import subprocess
import tempfile
import urllib.request

from _common import build, check, finish
import links  # noqa: E402
import webpanel  # noqa: E402

tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "links.json")
L = links.Links(path)
a = L.add({"host": "192.168.1.31", "port": "8080", "name": "TV-Dashboard"})
b = L.add({"host": "http://localhost:8123/party-sender.html", "name": "Party-Sender"})
c = L.add({"host": "lightbutler.local"})
check(links.Links.url(a) == "http://192.168.1.31:8080/" and a["name"] == "TV-Dashboard", "IP und Port")
check(links.Links.url(b) == "http://localhost:8123/party-sender.html", "ganze Adresse mit Pfad (localhost)")
check(links.Links.url(c) == "http://lightbutler.local/" and c["name"] == "lightbutler.local", "lokaler Name, ohne Name: Adresse")
check(links.clean_host("tv.box") == "tv.box", "Name vom Heimrouter (.box)")
check(links.Links(path).public()[1]["url"] == "http://localhost:8123/party-sender.html", "gespeichert in links.json, wieder geladen")
for bad, why in (({"host": "google.com"}, "Internetname"), ({"host": "8.8.8.8"}, "oeffentliche IP"), ({"host": "192.168.1.5", "port": "99999"}, "Port"),
                 ({"host": "ftp://192.168.1.5"}, "anderes Protokoll"), ({"host": "192.168.1.5/<script>"}, "Pfad mit Sonderzeichen"),
                 ({"host": ""}, "leer"), ({"host": "javascript:alert(1)"}, "javascript:")):
    try:
        L.add(bad)
        check(False, "abgelehnt: " + why)
    except ValueError:
        check(True, "abgelehnt: " + why)
L.remove(1)
check([x["name"] for x in links.Links(path).items] == ["TV-Dashboard", "lightbutler.local"], "entfernen")
for i in range(30):
    try:
        L.add({"host": "192.168.1.%d" % (i + 2)})
    except ValueError:
        break
check(len(L.items) == links.MAX_LINKS, "hoechstens %d Links" % links.MAX_LINKS)
with open(path, "w") as f:
    f.write('{"links": [{"name": "x", "host": "8.8.8.8"}, {"name": "ok", "host": "10.0.0.2", "port": 81}]}')
check([x["name"] for x in links.Links(path).items] == ["ok"], "Datei: ungueltige Eintraege fallen weg")

# Show und Panel
rig, sh = build()
sh.command({"link_add": {"host": "192.168.1.31", "port": "8080", "name": "TV-Dashboard"}})
check(sh.links.public()[0]["url"] == "http://192.168.1.31:8080/", "Befehl link_add")
page = webpanel.settings_page()
check('id="ml_host"' in page and 'id="ml_port"' in page and 'id="ml_name"' in page and "loadLinks()" in page, "Felder in den Einstellungen")
srv = webpanel.start(sh, 0)
port = srv.server_address[1] if srv is not None and hasattr(srv, "server_address") else None
if port:
    with urllib.request.urlopen("http://127.0.0.1:%d/api/links" % port, timeout=5) as r:
        check(json.loads(r.read())["links"][0]["name"] == "TV-Dashboard", "GET /api/links")
    req = urllib.request.Request("http://127.0.0.1:%d/api/cmd" % port, data=json.dumps({"link_add": {"host": "google.com"}}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
        check(False, "Internetadresse ueber die Schnittstelle abgelehnt")
    except urllib.error.HTTPError as e:
        check(e.code >= 400, "Internetadresse ueber die Schnittstelle abgelehnt")
js = webpanel.make_page().split("<script>")[-1].split("</script>")[0]
jf = os.path.join(tmp, "p.js")
open(jf, "w").write(js)
check(subprocess.run(["node", "--check", jf]).returncode == 0, "Panel-JavaScript ohne Syntaxfehler")
finish("test_links")
