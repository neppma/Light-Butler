"""Showmanager, Oberflaeche: Skripte fehlerfrei, Datenmodell im Browser-Code (Raster, Verschieben, Kopieren, Undo) mit node geprueft,
Seiten verlinkt und ohne Inhalte aus dem Internet."""
import json
import os
import re
import subprocess

from _common import PI, check, finish

import webpanel

SM = os.path.join(PI, "static", "sm")
files = sorted(os.listdir(SM))
check({"core.js", "timeline.js", "editor.js", "play.js", "sm.css", "editor.html", "play.html"} <= set(files), "alle Dateien da")
check(not any(f.endswith(".json") for f in files), "keine .json in der Oberflaeche (deploy.sh wuerde sie auslassen)")
for f in files:
    txt = open(os.path.join(SM, f), encoding="utf-8").read()
    check(not re.search(r"(src|href)=\"https?://|url\(https?:|import .*https?:|cdn\.", txt), f"{f}: nichts aus dem Internet, das Panel laeuft ohne")
ed = open(os.path.join(SM, "editor.html"), encoding="utf-8").read()
for i in ("bstart", "bplay", "bstop", "time", "bpmv", "bzi", "bzo", "bsave", "bload", "grid", "bundo", "bredo", "bcut", "bcopy", "bpaste", "bdel", "bmp3", "vol", "blight", "blk"):
    check(f'id="{i}"' in ed, f"Editor: Bedienelement {i}")
pl = open(os.path.join(SM, "play.html"), encoding="utf-8").read()
for i in ("pplay", "ppause", "pstop", "pstart", "plist", "wave", "blk"):
    check(f'id="{i}"' in pl, f"Playback: Bedienelement {i}")
ejs = open(os.path.join(SM, "editor.js"), encoding="utf-8").read()
for i in ("bdel", "bcut", "bloop", "bloopx", "bcopy", "bpaste", "bkey", "bundo", "bredo", "bmulti", "bzi", "bzo", "bzf"):
    check(re.search(r'<button id="%s"[^>]*><svg class="ic"' % i, ed) is not None, f"Knopf {i}: gut sichtbares Symbol")
check("let wantLight = true;" in ejs and "light: lightShown()" in ejs and ">Licht an</button>" in ed, "Play im Editor geht von Anfang an ans Licht, der Knopf schaltet es ab")
check("strobe" not in re.sub(r"(uses_strobe|st\.strobe|Strobe)", "", ejs).lower() or "set({strobe" not in ejs, "Editor schaltet die Strobe-Erlaubnis nie selbst")
check("tl.pos = position();" in ejs and "tl.linePos = playing ? p : tl.pos;" in ejs, "Linie vorziehen wirkt nur auf die Linie, gesetzte Zeiten bleiben exakt")
check("SM.cmd('light_ms'" in ejs, "Licht-Versatz direkt im Editor einstellbar")
check("Kapitel Geräte-Anleitungen" in ejs, "KTV: Link zur Anleitung im Editor")
check("c.p[k + '_to']" in ejs and "linked" in ejs, "Editor: Von und Bis, Bis geht mit, solange beide gleich sind")
tjs = open(os.path.join(SM, "timeline.js"), encoding="utf-8").read()
check('id="bmarks"' in ed and "SM.cmd('marks'" in ejs and "smmarks" in ejs, "Abschnitte und Cues: Knopf, Abfrage, Einstellung im Browser")
check("setStems" in tjs and "drawStems" in tjs and "'stems'" in tjs and "/api/sm/stems?name=" in ejs and "smstems" in ejs and "tl.setStems(null)" in ejs, "Kurven: laden, zeichnen, einklappen, bei neuer MP3 weg")
check("this.drawBands(" in tjs and "this.drawCues(" in tjs and "markAt(" in tjs, "Timeline: Baender, Cue-Linien, Einrasten")
check('id="bassist"' in ed and "SM.cmd('assist'" in ejs and 'type="password"' in ejs, "Show-Assistent: Knopf, Fenster, Schluessel verdeckt")
check("drawMaster(" in tjs and "masterRow()" in tjs and "SM.isMaster" in ejs, "Master-Zeile in der Timeline und im Editor")
check("drawPanel(" in tjs and "panelRow()" in tjs and "addPanelScene" in ejs and "onAddPanelScene" in tjs, "Zeile Panel-Szenen in der Timeline und im Editor")
check("SM.cmd('assist_job')" in ejs and 'id="amode"' in ejs and 'id="alyrics"' in ejs, "Assistent: Wahl, wer entwirft, Liedtext, Fortschritt im Hintergrund")
check("foldAll()" in tjs and "'fold'" in tjs and "this.o.onFold([...this.collapsed]);" in tjs and "!SM.isPinned(t)" in tjs, "Knopf: alle Geraete ein- und ausklappen, feste Zeilen bleiben, der Browser merkt es sich")
for page_name, html in (("Editor", ed), ("Playback", pl)):
    check('href="/shows/handbuch.pdf"' in html and 'class="rbtn"' in html, f"{page_name}: runder Knopf fuer die Bedienungsanleitung")
    check('M12 6.5v13' in html and 'm7 11 5 5 5-5' not in html, f"{page_name}: Knopf zeigt ein Buch")
pdf_path = os.path.join(PI, "static", "Showmanager-Handbuch.pdf")
check(os.path.isfile(pdf_path) and open(pdf_path, "rb").read(5) == b"%PDF-" and os.path.getsize(pdf_path) < 16 * 1024 * 1024, "Bedienungsanleitung liegt als PDF bereit")
check("laser_unlock" not in ejs and "sm_laser" not in ejs and "sm_fog" not in ejs, "Editor kann die Laser- und Nebel-Erlaubnis nicht selbst setzen")
p = webpanel.make_page()
check('<a id="smbtn" href="/shows"' in p and 'data-title="h_setpage"' in p and '<script src="/static/sm/nav.js">' in p, "Panel: Knopf oben, am Handy ueber die Kopfleiste der Einstellungen")
check("S.sm_show" in p, "Panel zeigt die laufende Show in der Hinweiszeile")

NODE_TEST = r"""
const SM = require(process.argv[1]);
const out = {};
const doc = {bpm:120,beat_offset:0.1,beats_per_bar:4,duration:60,grid:'beat',scene_clips:[],scenes:[],groups:[],tracks:[]};
out.snap = [SM.snap(1.02,doc,'beat'), SM.snap(1.3,doc,'bar'), SM.snap(1.04,doc,'off'), SM.snap(1.26,doc,'tenth'), SM.snap(-5,doc,'beat')];
out.time = [SM.fmtTime(83.5), SM.parseTime('1:23.5'), SM.parseTime('12,5'), SM.parseTime('abc'), SM.parseTime('1:2:3')];
const tr = SM.ensureTrack(doc,{fixture:'par'},'dimmer');
out.same = SM.ensureTrack(doc,{fixture:'par'},'dimmer') === tr;
const tr2 = SM.ensureTrack(doc,{fixture:'vega'},'dimmer');
const tr3 = SM.ensureTrack(doc,{fixture:'par'},'color');
out.order = doc.tracks.map(t=>t.target.fixture+'/'+t.attr);
const k1 = SM.addKey(doc,tr,10,0), k2 = SM.addKey(doc,tr,20,200,'ease_in'), c1 = SM.addClip(tr,5,2,'sine',{speed:1});
out.val = [SM.keyValueAt(tr,5), SM.keyValueAt(tr,15), SM.keyValueAt(tr,25)];
const H = new SM.History();
H.push(doc);
SM.moveEvents(doc,new Set([k1.id,c1.id]),-100);
out.moved = [SM.find(doc,c1.id).ev.t, SM.find(doc,k1.id).ev.t];
const undone = H.undo(doc);
out.undo = SM.find(undone,c1.id).ev.t;
const redone = H.redo(undone);
out.redo = SM.find(redone,c1.id).ev.t;
out.noundo = new SM.History().undo(doc);
const clip = SM.copyEvents(doc,new Set([k1.id,k2.id]));
const ids = SM.pasteEvents(doc,clip,30);
out.paste = ids.map(i=>SM.find(doc,i).ev.t).sort((a,b)=>a-b);
out.pasteUnique = !ids.includes(k1.id);
out.sorted = tr.keys.every((k,i)=>!i||tr.keys[i-1].t<=k.t);
SM.deleteEvents(doc,new Set(ids));
out.afterDelete = tr.keys.length;
out.kinds = [SM.kindOf('color'),SM.kindOf('move'),SM.kindOf('pan')];
out.hex = [SM.colorToHex([255,0,128,0,0]), SM.hexToColor('#ff0080',5,6)];
const gd = Object.assign({}, doc, {bpm:120, beat_offset:0.1, beats_per_bar:4});
out.grid = ['off','bar','beat','quarter','sec','tenth'].map(g => SM.gridLines(gd, g, 100));
out.gridFar = SM.gridLines(gd, 'beat', 1);
out.shape = [SM.shapeAt('fade_in',0.25), SM.shapeAt('fade_out',0.25), SM.shapeAt('blink',0.1,{duty:0.5}), SM.shapeAt('blink',0.9,{duty:0.5})];
out.cyc = [SM.clipCycles({d:10,pattern:'sine',p:{speed:2}},gd), SM.clipCycles({d:10,pattern:'sine',p:{repeat:3,speed:2}},gd), SM.clipCycles({d:10,pattern:'fade_in',p:{}},gd), SM.clipCycles({d:10,pattern:'sine',p:{beat_sync:1,speed:1}},gd)];
out.edge = [SM.clipEdge(198, 100, 200), SM.clipEdge(203, 100, 200), SM.clipEdge(102, 100, 200), SM.clipEdge(97, 100, 200), SM.clipEdge(150, 100, 200), SM.clipEdge(110, 100, 112), SM.clipEdge(106, 100, 112)];
const xo = t => t;
const two = [{t:100,d:50},{t:150,d:50}];
out.hit = [SM.hitClip(two, 148, xo).ev.t, SM.hitClip(two, 152, xo).ev.t, SM.hitClip(two, 96, xo).edge, SM.hitClip(two, 204, xo).edge, SM.hitClip(two, 300, xo)];
const sd = {bpm:120, grid:'beat'};
out.step = [SM.timeStep(sd), SM.timeStep({bpm:120, grid:'off'}), SM.timeStep({bpm:120, grid:'sec'})];
const md = {tracks:[{id:'a1',target:{fixture:'a'}},{id:'a2',target:{fixture:'a'}},{id:'b1',target:{fixture:'b'}},{id:'g1',target:{group:'g'}}]};
const mdIds = () => md.tracks.map(t => t.id).join(',');
out.mv = [SM.moveTarget(md,'f:a','g:g'), mdIds(), SM.moveTarget(md,'f:a','g:g'), SM.moveTarget(md,'g:g','f:b'), mdIds(), SM.moveTarget(md,'f:b',null), mdIds(), SM.moveTarget(md,'f:b',null), SM.moveTarget(md,'f:x',null)];
out.sp = SM.trackSpans({keys:[{t:5},{t:9}],clips:[{t:1,d:2}]}).map(s => [s.t0,s.t1,!!s.clip]);
out.spn = SM.trackSpans({keys:[],clips:[]}).length;
const sc = new SM.SmoothClock();
const so = [sc.update(10, 0, true), sc.update(10, 100, true), sc.update(10, 200, true), sc.update(10.15, 250, true), sc.update(10.15, 1000, true), sc.update(20, 1010, true), sc.update(20, 2000, false)];
const sf = new SM.SmoothClock();
sf.update(5, 0, true);
const fine = [1,2,3,4,5].map(i => sf.update(5 + i * 0.016, i * 16, true));
out.smooth = so; out.fine = fine;
const LP = {t0:10,t1:20,on:true};
out.loop = [SM.loopJump(19.9,20.0,LP), SM.loopJump(19.9,19.95,LP), SM.loopJump(25,25.1,LP), SM.loopJump(5,5.1,LP), SM.loopJump(null,20,LP), SM.loopJump(19.9,20.1,{...LP,on:false}), SM.loopJump(19.9,20.1,null)];
const ld = {scene_clips:[{id:'s',t:30,d:2}],tracks:[{keys:[{id:'k',t:1,v:0}],clips:[{id:'c',t:5,d:3}]}]};
out.ls = [SM.loopFromSelection(ld,new Set(['c','k'])), SM.loopFromSelection(ld,new Set(['c','s'])), SM.loopFromSelection(ld,new Set(['k'])), SM.loopFromSelection(ld,new Set())];
out.esc = SM.esc('<a href="x">&');
const samples = new Float32Array(44100*8);
for (let i=0;i<samples.length;i++) samples[i] = (i%22050<2000) ? Math.sin(i/5) : 0;
const a = SM.analyzeBuffer({numberOfChannels:1,length:samples.length,sampleRate:44100,duration:8,getChannelData:()=>samples});
out.an = [a.peaks.rate, a.peaks.min.length, a.peaks.max.length, a.env.length, Math.max(...a.peaks.max)];
console.log(JSON.stringify(out));
"""
try:
    r = subprocess.run(["node", "--version"], capture_output=True)
    has_node = r.returncode == 0
except FileNotFoundError:
    has_node = False
if has_node:
    for f in ("core.js", "timeline.js", "editor.js", "play.js"):
        check(subprocess.run(["node", "--check", os.path.join(SM, f)], capture_output=True).returncode == 0, f"{f} fehlerfrei (node --check)")
    r = subprocess.run(["node", "-e", NODE_TEST, os.path.join(SM, "core.js")], capture_output=True, text=True)
    check(r.returncode == 0, "Datenmodell laeuft unter node " + r.stderr[:300])
    o = json.loads(r.stdout)
    check(abs(o["snap"][0] - 1.1) < 1e-9 and abs(o["snap"][1] - 2.1) < 1e-9 and o["snap"][2] == 1.04 and abs(o["snap"][3] - 1.3) < 1e-9 and o["snap"][4] == 0, "Raster mit Taktanfang, Aus und Sekunden, nie vor 0")
    check(o["time"][0] == "1:23.500" and o["time"][1] == 83.5 and o["time"][2] == 12.5 and o["time"][3] is None and o["time"][4] == 3723, "Zeit anzeigen und exakt eingeben")
    check(o["same"], "Spur wird nicht doppelt angelegt")
    check(o["order"] == ["par/dimmer", "par/color", "vega/dimmer"], "Spuren eines Geraets bleiben beisammen")
    check(o["val"][0] == 0 and o["val"][2] == 200 and 0 < o["val"][1] < 200, "Keyframe-Wert an einer Stelle")
    check(o["moved"] == [0, 5], "Verschieben: Auswahl bleibt zusammen und rutscht nicht vor 0")
    check(o["undo"] == 5 and o["redo"] == 0 and o["noundo"] is None, "Undo und Redo")
    check(o["paste"] == [30, 45] and o["pasteUnique"] and o["sorted"], "Kopieren und Einfuegen mit neuen Kennungen")
    check(o["afterDelete"] == 2, "Loeschen")
    check(o["kinds"] == ["color", "move", "scalar"] and o["hex"][0] == "#ff0080" and o["hex"][1] == [255, 0, 128, 5, 6], "Farben und Spurarten")
    gr = o["grid"]
    check(gr[0] is None, "Raster aus: keine Linien")
    check(gr[1]["minor"] == 2.0 and gr[2]["minor"] == 0.5 and gr[3]["minor"] == 0.125 and gr[1]["off"] == 0.1, "Raster Takt, Beat, 1/4: eigene Abstaende, Taktanfang zaehlt")
    check(gr[4]["minor"] == 1 and gr[4]["off"] == 0 and gr[5]["minor"] == 0.1, "Raster Sekunde und 0,1 s: ab Null")
    check(o["gridFar"]["minor"] * 1 >= 5, "weit herausgezoomt: nicht zu eng")
    check(o["shape"] == [0.25, 0.75, 1, 0], "Vorschau im Clip nach der Form des Musters")
    check(o["cyc"] == [20, 3, 1, 20], "Zyklen je Clip: Geschwindigkeit, Wiederholungen, im Takt")
    check(o["edge"][:5] == ["r", "r", "l", "l", ""], "Rand eines Blocks: rechts, links, auch knapp daneben, Mitte zum Verschieben")
    check(o["edge"][5] == "r" and o["edge"][6] == "", "kurzer Block: beide Raender und eine Mitte")
    check(o["hit"][0] == 100 and o["hit"][1] == 150 and o["hit"][2] == "l" and o["hit"][3] == "r" and o["hit"][4] is None, "zwei Bloecke nebeneinander: der richtige Rand")
    check(o["step"] == [0.5, 0.1, 1], "Pfeilchen: Schritt nach Raster, ohne Raster 0,1 s")
    m_ = o["mv"]
    check(m_[0] is True and m_[1] == "b1,a1,a2,g1", "Geraet verschieben: alle seine Spuren bleiben beisammen")
    check(m_[2] is False, "schon dort: keine Aenderung, kein Undo-Schritt")
    check(m_[3] is True and m_[4] == "g1,b1,a1,a2", "Gruppe nach vorne")
    check(m_[5] is True and m_[6] == "g1,a1,a2,b1" and m_[7] is False and m_[8] is False, "ans Ende, unbekanntes Geraet tut nichts")
    check(o["sp"] == [[5, 9, False], [1, 3, True]] and o["spn"] == 0, "Mini-Spuren: Bereich der Keyframes und der Clips, leere Spur ohne")
    s_ = o["smooth"]
    check(s_[0] == 10 and abs(s_[1] - 10.1) < 1e-9 and abs(s_[2] - 10.2) < 1e-9, "Linie laeuft zwischen groben Werten weiter")
    check(s_[3] >= s_[2], "nie rueckwaerts, wenn ein neuer Wert kommt")
    check(abs(s_[4] - 10.4) < 1e-9, "ohne neue Werte hoechstens 0,25 s weiter")
    check(s_[5] == 20 and s_[6] == 20, "Sprung und Stillstand: genau der Wert")
    check(all(abs(x - (5 + (i + 1) * 0.016)) < 1e-9 for i, x in enumerate(o["fine"])), "genauer Browser: genau sein Wert")
    check(o["loop"] == [10, None, None, None, None, None, None], "Loop: nur beim Ueberschreiten des Endes zurueck, ausgeschaltet nie, dahinter nicht")
    check(o["ls"][0] == {"t0": 1, "t1": 8} and o["ls"][1] == {"t0": 5, "t1": 32} and o["ls"][2] is None and o["ls"][3] is None, "Loop aus der Auswahl")
    check('id="bloop"' in ed and "smloop:" in ejs and "loop" not in open(os.path.join(SM, "play.js"), encoding="utf-8").read().lower(), "Loop nur im Editor, nicht in der Showdatei und nicht auf der Playback-Seite")
    check("st.src === 'mixxx'" in ejs, "aus Mixxx kein Loop")
    tjs = open(os.path.join(SM, "timeline.js"), encoding="utf-8").read()
    check("if (this.userView) return;" in tjs and "this.userView = true;" in tjs, "selbst weggescrollt: die Ansicht springt beim Abspielen nicht zurueck")
    check('id="bloopx"' in ed and "function clearLoop" in ejs and "function loopArrive" in ejs, "Loop entfernen, neuer Bereich wird beim Abspielen gleich angefahren")
    check("<" not in o["esc"] and "&amp;" in o["esc"], "Texte werden maskiert")
    check(o["an"][0] == 50 and abs(o["an"][1] - 400) <= 1 and o["an"][1] == o["an"][2] and abs(o["an"][3] - 800) <= 1 and o["an"][4] > 100, "Wellenform und Huellkurve aus dem dekodierten Ton")
else:
    print("  (node fehlt, Skriptpruefung uebersprungen)")
finish("test_showmanager_js")
